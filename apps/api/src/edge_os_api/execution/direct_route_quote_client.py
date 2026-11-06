"""Release-selected direct Kuru Flow quote source.

This source calls the Flow entrypoint directly with a one-pool V2 program that the
release pins. It makes exactly one read: ``getReserves()`` on that pool at the
latest block. It computes the expected output locally, refuses on slippage, and
builds the entrypoint calldata from release fields only. It loads no credential,
signs nothing and sends nothing.

The result is the same ``TRANSACTION_CALLDATA`` shape the existing preparation,
decoding and original-transaction paths accept, so those checks stay unchanged.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from edge_os_api.execution.kuru_quote_client import QuoteAvailability
from edge_os_api.execution.original_transaction import RpcError
from edge_os_api.execution.transaction_rpc_client import (
    json_bytes,
    post_json,
    request_stopped,
    validate_bounds,
)
from edge_os_api.kuru_flow.types import canonical_raw, is_address

DIRECT_QUOTE_SOURCE = "DIRECT_V2_PROGRAM"
EXECUTE_SWAP_SELECTOR = "0xce1e7030"
RESERVES_SELECTOR = "0x0902f1ac"
PROGRAM_FEE_SCALE = 10**6
MAX_PRE_SIGN_TOLERANCE_BPS = 50
MAX_RAW_DIGITS = 78
_ZERO_ADDRESS = "0x" + "0" * 40
_RESERVES_REPLY = re.compile(r"0x(?:[0-9a-fA-F]{64}){3}")
_RESERVES_WORDS = 3


def _address_word(value: str) -> bytes:
    return b"\x00" * 12 + bytes.fromhex(value[2:])


def _uint_word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _raw(value: Any) -> bool:
    return (type(value) is str and len(value) <= MAX_RAW_DIGITS and canonical_raw(value)
            and 0 < int(value) < 2**256)


def build_program_hex(*, input_token: str, pool_address: str, direction: int, fee_ppm: int) -> str:
    """The exact one-hop V2 program from `KuruFlow.sol` (source commit 70bc0c93c0)."""
    if not is_address(input_token) or not is_address(pool_address):
        raise ValueError("PROGRAM_ADDRESS_INVALID")
    if type(direction) is not int or direction not in (0, 1):
        raise ValueError("PROGRAM_DIRECTION_INVALID")
    if type(fee_ppm) is not int or not 0 < fee_ppm < PROGRAM_FEE_SCALE:
        raise ValueError("PROGRAM_FEE_INVALID")
    raw = (bytes([0x02]) + bytes.fromhex(input_token[2:]) + bytes([0x01]) + (0xFFFF).to_bytes(2, "big")
           + bytes([0x00]) + bytes.fromhex(pool_address[2:]) + bytes([direction]) + fee_ppm.to_bytes(3, "big"))
    return "0x" + raw.hex()


def quote_meets_release_minimum(*, output: int, slippage_bps: int, approved_min_output_raw: int,
                                pre_sign_tolerance_bps: int) -> bool:
    """The live floor may sit at most `pre_sign_tolerance_bps` below the release minimum."""
    floor = output * (10000 - slippage_bps) // 10000
    return floor * 10000 >= approved_min_output_raw * (10000 - pre_sign_tolerance_bps)


@dataclass(frozen=True)
class DirectRoutePins:
    """The release fields this source may use. Nothing outside these values enters calldata."""

    endpoint: str
    pool_address: str
    token0_address: str
    token1_address: str
    direction: int
    program_fee_ppm: int
    approved_program_hex: str
    approved_input_raw: str
    approved_min_output_raw: str
    entrypoint_address: str
    input_token: str
    output_token: str
    pre_sign_tolerance_bps: int = 0

    def __post_init__(self) -> None:
        addresses = (self.pool_address, self.token0_address, self.token1_address,
                     self.entrypoint_address, self.input_token, self.output_token)
        if not all(type(value) is str and is_address(value) for value in addresses):
            raise ValueError("DIRECT_PIN_ADDRESS_INVALID")
        if self.token0_address.lower() == self.token1_address.lower():
            raise ValueError("DIRECT_PIN_TOKEN_ORDER_INVALID")
        if type(self.direction) is not int or self.direction not in (0, 1):
            raise ValueError("DIRECT_PIN_DIRECTION_INVALID")
        expected0, expected1 = ((self.input_token, self.output_token) if self.direction == 0
                                else (self.output_token, self.input_token))
        if self.token0_address.lower() != expected0.lower() or self.token1_address.lower() != expected1.lower():
            raise ValueError("DIRECT_PIN_TOKEN_ORDER_INVALID")
        if not _raw(self.approved_input_raw) or not _raw(self.approved_min_output_raw):
            raise ValueError("DIRECT_PIN_AMOUNT_INVALID")
        if type(self.pre_sign_tolerance_bps) is not int \
                or not 0 <= self.pre_sign_tolerance_bps <= MAX_PRE_SIGN_TOLERANCE_BPS:
            raise ValueError("DIRECT_PIN_TOLERANCE_INVALID")
        try:
            validate_bounds(endpoint=self.endpoint, deadline=1.0, timeout=1.0, request_bytes=1, response_bytes=1)
        except Exception as error:
            raise ValueError("DIRECT_PIN_ENDPOINT_INVALID") from error
        parts = urlsplit(self.endpoint)
        if parts.scheme != "https" or parts.path != "/rpc" or parts.query or parts.fragment:
            raise ValueError("DIRECT_PIN_ENDPOINT_INVALID")
        built = build_program_hex(input_token=self.input_token, pool_address=self.pool_address,
                                  direction=self.direction, fee_ppm=self.program_fee_ppm)
        if type(self.approved_program_hex) is not str or self.approved_program_hex.lower() != built:
            raise ValueError("DIRECT_PIN_PROGRAM_MISMATCH")

    @classmethod
    def from_release(cls, release: Mapping[str, Any]) -> "DirectRoutePins":
        quote, route = release["quote"], release["route"]
        return cls(endpoint=quote["endpoint"], pool_address=quote["pool_address"],
                   token0_address=quote["token0_address"], token1_address=quote["token1_address"],
                   direction=quote["direction"], program_fee_ppm=quote["program_fee_ppm"],
                   approved_program_hex=route["approved_program_hex"],
                   approved_input_raw=route["approved_input_raw"],
                   approved_min_output_raw=route["approved_min_output_raw"],
                   entrypoint_address=route["entrypoint_address"],
                   input_token=route["input_asset"]["token_address"],
                   output_token=route["output_asset"]["token_address"],
                   pre_sign_tolerance_bps=quote.get("pre_sign_tolerance_bps", 0))


def build_calldata_hex(pins: DirectRoutePins) -> str:
    """The exact `executeSwap(SwapIntent, FeeCollection, bytes)` call for these pins."""
    program = bytes.fromhex(pins.approved_program_hex[2:])
    padding = (32 - len(program) % 32) % 32
    head = b"".join((
        _address_word(pins.output_token), _uint_word(int(pins.approved_min_output_raw)),
        _address_word(pins.input_token), _uint_word(int(pins.approved_input_raw)),
        _address_word(_ZERO_ADDRESS), _uint_word(0), _address_word(_ZERO_ADDRESS), _uint_word(0),
        _uint_word(0), _uint_word(10 * 32),
    ))
    body = head + _uint_word(len(program)) + program + b"\x00" * padding
    return EXECUTE_SWAP_SELECTOR + body.hex()


class DirectRouteQuoteClient:
    """One frozen request, one reserves read, local output formula, exact approved minimum."""

    def __init__(self, pins: DirectRoutePins, *, accepted_request: Mapping[str, Any], slippage_bps: int,
                 http: Any, deadline_monotonic: float, connect_timeout_seconds: float, max_request_bytes: int,
                 max_response_bytes: int, evidence_class: str, cancel: Callable[[], bool] | None = None,
                 monotonic: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)) -> None:
        validate_bounds(endpoint=pins.endpoint, deadline=deadline_monotonic, timeout=connect_timeout_seconds,
                        request_bytes=max_request_bytes, response_bytes=max_response_bytes)
        if type(slippage_bps) is not int or not 1 <= slippage_bps <= 10000:
            raise ValueError("QUOTE_SLIPPAGE_INVALID")
        if evidence_class not in ("SYNTHETIC_FIXTURE", "PROVIDER_UNQUALIFIED"):
            raise ValueError("QUOTE_EVIDENCE_INVALID")
        invalid = False
        frozen = b""
        try:
            request = dict(accepted_request)
            invalid = (set(request) != {"chain_id", "sell_token", "buy_token", "amount", "user"}
                or type(request["chain_id"]) is not int or request["chain_id"] != 143
                or not all(type(request[x]) is str and is_address(request[x]) and int(request[x], 16) != 0
                           for x in ("sell_token", "buy_token", "user"))
                or request["sell_token"].lower() != pins.input_token.lower()
                or request["buy_token"].lower() != pins.output_token.lower()
                or request["amount"] != pins.approved_input_raw)
            frozen = json_bytes(request)
        except Exception:
            invalid = True
        if invalid:
            raise ValueError("QUOTE_REQUEST_INVALID")
        self._pins, self._accepted = pins, frozen
        self._wire = json_bytes({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                 "params": [{"to": pins.pool_address, "data": RESERVES_SELECTOR}, "latest"]})
        self._slippage, self._calldata = slippage_bps, build_calldata_hex(pins)
        self._http, self._deadline, self._timeout = http, deadline_monotonic, connect_timeout_seconds
        self._max_request_bytes, self._max_response_bytes = max_request_bytes, max_response_bytes
        self._evidence, self._cancel = evidence_class, cancel
        self._monotonic, self._clock = monotonic, wall_clock
        self._used, self._lock, self._observation = False, threading.Lock(), None

    def __repr__(self) -> str:
        return "DirectRouteQuoteClient(source='DIRECT_V2_PROGRAM', mounted=False)"

    @property
    def observation(self) -> QuoteAvailability | None:
        return self._observation

    def quote(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        accepted = False
        with self._lock:
            if not self._used:
                self._used = True
                try:
                    accepted = json_bytes(dict(request)) == self._accepted
                except Exception:
                    pass
        if not accepted:
            raise RpcError("QUOTE_REQUEST_NOT_ACCEPTED")
        if len(self._wire) > self._max_request_bytes:
            raise RpcError("QUOTE_REQUEST_OVERSIZED")
        started = self._now()
        reply = post_json(http=self._http, endpoint=self._pins.endpoint, wire=self._wire,
                          headers={"content-type": "application/json"}, deadline=self._deadline,
                          timeout=self._timeout, max_response_bytes=self._max_response_bytes,
                          monotonic=self._monotonic, cancel=self._cancel)
        finished = self._now()
        output = None
        try:
            result = reply.get("result")
            valid = (set(reply) == {"jsonrpc", "id", "result"} and reply["jsonrpc"] == "2.0"
                     and reply["id"] == 1 and type(result) is str and _RESERVES_REPLY.fullmatch(result) is not None
                     and finished >= started)
            if valid:
                words = [int(result[2 + index * 64:2 + (index + 1) * 64], 16) for index in range(_RESERVES_WORDS)]
                reserve_in, reserve_out = ((words[0], words[1]) if self._pins.direction == 0
                                           else (words[1], words[0]))
                if reserve_in <= 0 or reserve_out <= 0:
                    raise RpcError("QUOTE_RESERVES_EMPTY")
                amount = int(self._pins.approved_input_raw)
                fee = self._pins.program_fee_ppm
                output = amount * (PROGRAM_FEE_SCALE - fee) * reserve_out // (
                    reserve_in * PROGRAM_FEE_SCALE + amount * (PROGRAM_FEE_SCALE - fee))
                if output <= 0:
                    raise RpcError("QUOTE_OUTPUT_ZERO")
                if not quote_meets_release_minimum(
                        output=output, slippage_bps=self._slippage,
                        approved_min_output_raw=int(self._pins.approved_min_output_raw),
                        pre_sign_tolerance_bps=self._pins.pre_sign_tolerance_bps):
                    raise RpcError("QUOTE_SLIPPAGE_EXCEEDED")
        except RpcError:
            raise
        except Exception:
            output = None
        if output is None:
            raise RpcError("QUOTE_RESERVES_UNSUPPORTED")
        if request_stopped(cancel=self._cancel, monotonic=self._monotonic, deadline=self._deadline):
            raise RpcError("QUOTE_REPLY_AFTER_STOP")
        self._observation = QuoteAvailability(hashlib.sha256(self._wire).hexdigest(), started, finished, self._evidence)
        return {"status": "success", "output": str(output),
                "minOut": self._pins.approved_min_output_raw,
                "transaction": {"to": self._pins.entrypoint_address, "calldata": self._calldata, "value": "0"}}

    def _now(self) -> dt.datetime:
        moment = None
        try:
            value = self._clock()
            if isinstance(value, dt.datetime) and value.tzinfo is not None and value.utcoffset() == dt.timedelta(0):
                moment = value
        except Exception:
            pass
        if moment is None:
            raise RpcError("QUOTE_CLOCK_UNAVAILABLE")
        return moment
