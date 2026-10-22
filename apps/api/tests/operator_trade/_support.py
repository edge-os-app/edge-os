"""Synthetic fixtures for the operator-trade tests. Every reply is authored; nothing is fetched."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eth_utils import keccak

from edge_os_api.execution.original_transaction import BALANCE_OF_SELECTOR, RpcError

WALLET = "0x91BB52A63c91986813288965e4681FF111De1b63"
WALLET_ID = "bsb2feecuxl81dl5jz4u9xxo"
WMON = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"
MOE = "0xd8e004acba279417c04c0633cb5a21ceca207777"
POOL = "0x97199b34564911936bc850ac45ede785892b5aad"
ENTRYPOINT = "0xb3e6778480b2E488385E8205eA05E20060B813cb"
ZERO = "0x" + "0" * 40
CHAIN_ID = 143
INPUT = 50 * 10**18

FAKE_CODE = {"entrypoint": "0x60016000", "wmon": "0x60026000", "pool": "0x60036000"}


def code_sha256(code_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(code_hex[2:])).hexdigest()


def trade_dict(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "version": 1,
        "chain_id": CHAIN_ID,
        "wallet_address": WALLET,
        "wallet_id": WALLET_ID,
        "wmon": WMON,
        "moe": MOE,
        "pool": POOL,
        "entrypoint": ENTRYPOINT,
        "token0": WMON,
        "token1": MOE,
        "direction": 0,
        "program_fee_ppm": 16000,
        "input_raw": str(INPUT),
        "slippage_bps": 100,
        "usd_ceiling": "2.00",
        "mon_usd_price": "0.02",
        "gas_limits": {"wrap": 60000, "approve": 60000, "swap": 400000, "revoke": 60000},
        "code_sha256": {role: code_sha256(code) for role, code in FAKE_CODE.items()},
        "receipt_timeout_seconds": 5,
        "receipt_poll_seconds": 1,
    }
    value.update(overrides)
    return value


def write_trade(path: Path, **overrides: Any) -> tuple[Path, str]:
    data = trade_dict(**overrides)
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


class FakeSigner:
    def __init__(self, signed: str) -> None:
        self.signed = signed
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, wallet_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((wallet_id, body))
        return {"data": {"signed_transaction": self.signed, "encoding": "rlp"}}


class RefusingSigner:
    def __init__(self, reason: str = "QUANTITY_UNSUPPORTED") -> None:
        self.reason = reason
        self.calls = 0

    def rpc(self, wallet_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"error": {"code": "LOCAL_UNSENT", "reason": self.reason}}


def signed_for(tag: str) -> str:
    return "0x" + keccak(tag.encode("utf-8")).hex()


@dataclass
class FakeRpc:
    native_balance: int = 10**21
    wmon_balance: int = 0
    moe_balance: int = 0
    allowance: int = 0
    reserve_wmon: int = 862430562121790033386323
    reserve_moe: int = 65519655595145240989629270
    nonce: int = 7
    base_fee: int = 10**9
    priority_fee: int = 10**9
    code: dict[str, str] = field(default_factory=lambda: dict(FAKE_CODE))
    simulation_output: int = 3_737_556_748_405_128_021_448
    receipt_status: str = "0x1"
    receipt_after: int = 0
    receipt_timeout: bool = False
    send_error: Exception | None = None
    send_errors: dict[int, Exception] = field(default_factory=dict)
    receipt_statuses: list[str] = field(default_factory=list)
    receipt_timeout_at: set[int] = field(default_factory=set)
    fail_methods: set[str] = field(default_factory=set)
    reverting_swap: bool = False
    calls: list[tuple[str, Any]] = field(default_factory=list)
    sent: list[str] = field(default_factory=list)
    receipts: dict[str, dict[str, Any]] = field(default_factory=dict)
    receipt_polls: int = 0
    timeout_hashes: set[str] = field(default_factory=set)
    wmon_series: list[int] = field(default_factory=list)
    moe_series: list[int] = field(default_factory=list)
    on_send: Callable[[str], None] | None = None

    def _quantity(self, value: int) -> str:
        return hex(value)

    def call(self, method: str, params: Any) -> Any:
        self.calls.append((method, params))
        if method in self.fail_methods:
            raise RpcError("FAKE_METHOD_FAILED")
        if method == "eth_chainId":
            return hex(CHAIN_ID)
        if method == "eth_blockNumber":
            return "0x10"
        if method == "eth_getBalance":
            return self._quantity(self.native_balance)
        if method == "eth_getTransactionCount":
            return self._quantity(self.nonce)
        if method == "eth_getBlockByNumber":
            return {"number": "0x10", "hash": "0x" + "1" * 64, "timestamp": "0x1",
                    "baseFeePerGas": self._quantity(self.base_fee)}
        if method == "eth_maxPriorityFeePerGas":
            return self._quantity(self.priority_fee)
        if method == "eth_getCode":
            role = self._role(params[0])
            return self.code[role]
        if method == "eth_getTransactionReceipt":
            self.receipt_polls += 1
            tx_hash = params[0]
            if self.receipt_timeout or tx_hash in self.timeout_hashes or self.receipt_polls <= self.receipt_after:
                return None
            return self.receipts.get(tx_hash, self._receipt(tx_hash))
        if method == "eth_call":
            return self._eth_call(params)
        raise RpcError("FAKE_METHOD_UNKNOWN")

    def _role(self, address: str) -> str:
        for role, value in (("entrypoint", ENTRYPOINT), ("wmon", WMON), ("pool", POOL)):
            if address.lower() == value.lower():
                return role
        return "pool"

    def _eth_call(self, params: Any) -> Any:
        call = params[0]
        data = call["data"]
        to = call["to"].lower()
        if data == BALANCE_OF_SELECTOR + "0" * 24 + WALLET[2:].lower():
            if to == WMON.lower():
                if self.wmon_series:
                    return "0x" + self.wmon_series.pop(0).to_bytes(32, "big").hex()
                return "0x" + self.wmon_balance.to_bytes(32, "big").hex()
            if self.moe_series:
                return "0x" + self.moe_series.pop(0).to_bytes(32, "big").hex()
            return "0x" + self.moe_balance.to_bytes(32, "big").hex()
        if data.startswith("0xdd62ed3e"):
            return "0x" + self.allowance.to_bytes(32, "big").hex()
        if data == "0x0dfe1681":
            return "0x" + "0" * 24 + WMON[2:].lower()
        if data == "0xd21220a7":
            return "0x" + "0" * 24 + MOE[2:].lower()
        if data == "0x0902f1ac":
            return "0x" + self.reserve_wmon.to_bytes(32, "big").hex() + self.reserve_moe.to_bytes(32, "big").hex() + "0" * 64
        if data.startswith("0xce1e7030"):
            if self.reverting_swap:
                raise RpcError("FAKE_REVERT")
            return "0x" + self.simulation_output.to_bytes(32, "big").hex()
        if data.startswith("0xd0e30db0") or data.startswith("0x095ea7b3"):
            return "0x" + "0" * 63 + "1"
        return "0x"

    def send_raw(self, signed: str) -> str:
        index = len(self.sent)
        self.sent.append(signed)
        if self.on_send is not None:
            self.on_send(signed)
        if self.send_error is not None:
            raise self.send_error
        if index in self.send_errors:
            raise self.send_errors[index]
        tx_hash = "0x" + keccak(bytes.fromhex(signed[2:])).hex()
        if index in self.receipt_timeout_at:
            self.timeout_hashes.add(tx_hash)
        else:
            status = self.receipt_statuses.pop(0) if self.receipt_statuses else self.receipt_status
            self.receipts[tx_hash] = self._receipt(tx_hash, status)
        return tx_hash

    def _receipt(self, tx_hash: str, status: str | None = None) -> dict[str, Any]:
        return {"transactionHash": tx_hash, "status": self.receipt_status if status is None else status, "blockNumber": "0x11",
                "gasUsed": "0x5208", "blockHash": "0x" + "2" * 64, "from": WALLET, "to": ENTRYPOINT}


class FakeTransport:
    """Structural HttpTransport for indirect tests. It records and never opens a socket."""

    def __init__(self, replies: list[dict[str, Any]] | None = None) -> None:
        self.replies = list(replies or [])
        self.requests: list[dict[str, Any]] = []

    def request(self, *, method: str, url: str, headers: dict[str, str], body: bytes,
                timeout: float, deadline: float, max_response_bytes: int,
                cancel: Callable[[], bool] | None = None) -> Any:
        raise AssertionError("no transport call is allowed in this test")


def make_signer_factory(signed_by_step: dict[str, str], created: list[FakeSigner] | None = None):
    def factory(step: str, nonce: int) -> FakeSigner:
        signer = FakeSigner(signed_by_step[step])
        if created is not None:
            created.append(signer)
        return signer

    return factory


def clock_pair() -> tuple[Callable[[], float], Callable[[float], None]]:
    value = [0.0]

    def now() -> float:
        return value[0]

    def sleep(seconds: float) -> None:
        value[0] += seconds

    return now, sleep


class FakePrivyTransport:
    """A response-only HTTPS transport for the real Privy signer adapter. It never opens a socket."""

    def __init__(self, signed: list[str]) -> None:
        self.signed = list(signed)
        self.urls: list[str] = []
        self.bodies: list[bytes] = []

    def request(self, *, method: str, url: str, headers: dict[str, str], body: bytes,
                timeout: float, deadline: float, max_response_bytes: int,
                cancel: Callable[[], bool] | None = None) -> Any:
        from edge_os_api.research_history.http_clients.http_transport import HttpResponse

        self.urls.append(url)
        self.bodies.append(body)
        payload = {"method": "eth_signTransaction",
                   "data": {"signed_transaction": self.signed[len(self.urls) - 1], "encoding": "rlp"}}
        return HttpResponse(status=200, headers={"content-type": "application/json"},
                            body=json.dumps(payload).encode("utf-8"))


def write_p256_key(path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))


SMALL_INPUT = 10**15


def small_trade_dict(**overrides: Any) -> dict[str, Any]:
    value = trade_dict(input_raw=str(SMALL_INPUT))
    value.update(overrides)
    return value


def _signer_body(value: int) -> dict[str, Any]:
    return {"method": "eth_signTransaction", "params": {"transaction": {
        "type": 2, "chain_id": 143, "nonce": 0, "to": WMON, "value": value, "data": "0xd0e30db0",
        "gas_limit": 60000, "max_fee_per_gas": 3_000_000_000, "max_priority_fee_per_gas": 1_000_000_000}}}


def current_signer_refuses_large_quantity() -> bool:
    """Check the installed signer's actual behavior instead of inferring it from a version or comment."""
    import time

    from cryptography.hazmat.primitives.asymmetric import ec

    from edge_os_api.execution.privy_signer import PrivySignerClient, make_p256_authorizer

    key = ec.generate_private_key(ec.SECP256R1())
    signer = PrivySignerClient(
        app_id="operator-test", app_secret="operator-test-secret",
        authorize=make_p256_authorizer(private_key=key), request_id="operator-test-request",
        request_expiry_ms=time.time_ns() // 1_000_000 + 300_000,
        http=FakePrivyTransport([signed_for("wrap")]), connect_timeout_seconds=1.0,
        deadline_monotonic=time.monotonic() + 60.0, max_response_bytes=65536,
    )
    reply = signer.rpc(WALLET_ID, _signer_body(INPUT))
    return "error" in reply


def make_real_signer_factory(signed: list[str], key_path: Path, transport: FakePrivyTransport):
    import time

    from cryptography.hazmat.primitives import serialization

    from edge_os_api.execution.privy_signer import PrivySignerClient, make_p256_authorizer

    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)

    def factory(step: str, nonce: int) -> PrivySignerClient:
        return PrivySignerClient(
            app_id="operator-test", app_secret="operator-test-secret",
            authorize=make_p256_authorizer(private_key=key),
            request_id=f"operator-test-{step}-{nonce}",
            request_expiry_ms=time.time_ns() // 1_000_000 + 300_000,
            http=transport, connect_timeout_seconds=1.0,
            deadline_monotonic=time.monotonic() + 60.0, max_response_bytes=65536,
        )

    return factory
