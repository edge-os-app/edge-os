"""One K2 quote over the existing transport. K3 buildResponse remains unsupported."""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from edge_os_api.execution.original_transaction import RpcError
from edge_os_api.execution.transaction_rpc_client import json_bytes, post_json, request_stopped, validate_bounds
from edge_os_api.kuru_flow import ResponseProvenance
from edge_os_api.kuru_flow.quote_schema import parse_quote_response
from edge_os_api.kuru_flow.types import canonical_raw, is_address
from edge_os_api.research_history.http_clients.http_transport import HttpTransport


@dataclass(frozen=True)
class QuoteAvailability:
    request_sha256: str
    requested_at: dt.datetime
    received_at: dt.datetime
    evidence_class: str
    provider_created_at: dt.datetime | None = None


def _raw(value: Any) -> bool:
    return type(value) is str and len(value) <= 78 and canonical_raw(value) and int(value) < 2**256


class KuruQuoteClient:
    """Frozen accepted request, one quote call, no token generation or refresh."""

    def __init__(self, *, endpoint: str, bearer_token: str, accepted_request: Mapping[str, Any],
                 slippage_bps: int, http: HttpTransport, deadline_monotonic: float, connect_timeout_seconds: float,
                 max_request_bytes: int, max_response_bytes: int, evidence_class: str,
                 cancel: Callable[[], bool] | None = None, monotonic: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)) -> None:
        validate_bounds(endpoint=endpoint, deadline=deadline_monotonic, timeout=connect_timeout_seconds,
                        request_bytes=max_request_bytes, response_bytes=max_response_bytes)
        parts = urlsplit(endpoint)
        if (parts.path != "/api/quote" or parts.query or (parts.hostname != "ws.kuru.io"
                and not parts.hostname.endswith(".invalid"))):
            raise ValueError("QUOTE_ENDPOINT_UNSUPPORTED")
        if type(bearer_token) is not str or not re.fullmatch(r"[A-Za-z0-9._~-]{1,8192}", bearer_token):
            raise ValueError("QUOTE_TOKEN_INVALID")
        if type(slippage_bps) is not int or not 1 <= slippage_bps <= 10000:
            raise ValueError("QUOTE_SLIPPAGE_INVALID")
        if evidence_class not in ("SYNTHETIC_FIXTURE", "PROVIDER_UNQUALIFIED"):
            raise ValueError("QUOTE_EVIDENCE_INVALID")
        invalid = False
        frozen = b""
        try:
            r = dict(accepted_request)
            invalid = (set(r) != {"chain_id", "sell_token", "buy_token", "amount", "user"}
                or type(r["chain_id"]) is not int or r["chain_id"] != 143
                or not all(type(r[x]) is str and is_address(r[x]) and int(r[x], 16) != 0 for x in ("sell_token", "buy_token", "user"))
                or r["sell_token"].lower() == r["buy_token"].lower() or not _raw(r["amount"]) or r["amount"] == "0")
            frozen = json_bytes(r)
            wire = json_bytes({"userAddress": r["user"], "tokenIn": r["sell_token"], "tokenOut": r["buy_token"],
                               "amount": r["amount"], "slippageTolerance": slippage_bps})
            invalid = invalid or len(wire) > max_request_bytes
        except Exception:
            invalid = True
        if invalid:
            raise ValueError("QUOTE_REQUEST_INVALID")
        self._accepted, self._wire, self._endpoint, self._token = frozen, wire, endpoint, bearer_token
        self._http, self._deadline, self._timeout = http, deadline_monotonic, connect_timeout_seconds
        self._max_response_bytes, self._evidence = max_response_bytes, evidence_class
        self._cancel, self._monotonic, self._clock = cancel, monotonic, wall_clock
        self._used, self._lock, self._observation = False, threading.Lock(), None

    def __repr__(self) -> str:
        return "KuruQuoteClient(schema='TRANSACTION_CALLDATA', mounted=False)"

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
        started = self._now()
        reply = post_json(http=self._http, endpoint=self._endpoint, wire=self._wire,
                          headers={"authorization": "Bearer " + self._token, "content-type": "application/json"},
                          deadline=self._deadline, timeout=self._timeout, max_response_bytes=self._max_response_bytes,
                          monotonic=self._monotonic, cancel=self._cancel, secrets=(self._token,))
        finished = self._now()
        valid = False
        try:
            keys = {"type", "status", "output", "minOut", "transaction", "gasPrices"}
            tx, gas = reply.get("transaction"), reply.get("gasPrices")
            valid = (set(reply) == keys and type(reply["type"]) is str and bool(reply["type"])
                and reply["status"] == "success" and _raw(reply["output"]) and _raw(reply["minOut"])
                and 0 < int(reply["minOut"]) <= int(reply["output"])
                and type(tx) is dict and set(tx) == {"to", "calldata", "value"}
                and type(tx["to"]) is str and is_address(tx["to"]) and _raw(tx["value"]) and tx["value"] == "0"
                and type(tx["calldata"]) is str and re.fullmatch(r"(?:[0-9a-fA-F]{2}){4,8192}", tx["calldata"]) is not None
                and type(gas) is dict and set(gas) == {"slow", "standard", "fast", "rapid", "extreme"}
                and all(_raw(v) for v in gas.values()) and finished >= started)
            if valid:
                valid = not parse_quote_response(reply, ResponseProvenance.AUTHORED).reasons
        except Exception:
            valid = False
        if not valid:
            raise RpcError("QUOTE_K2_REPLY_UNSUPPORTED")
        if request_stopped(cancel=self._cancel, monotonic=self._monotonic, deadline=self._deadline):
            raise RpcError("QUOTE_REPLY_AFTER_STOP")
        self._observation = QuoteAvailability(hashlib.sha256(self._wire).hexdigest(), started, finished, self._evidence)
        return reply

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
