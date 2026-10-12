"""Offline clients that replay the authored original-transaction recordings (local and test only).

They answer the native shapes the application seams expect (Kuru Flow route quote, Privy `eth_signTransaction`,
Ethereum JSON-RPC) from `edge-os.original-transaction-recordings/1`. They open no socket and read no credential.
Every call that reaches a client is appended to `calls.jsonl`, and every accepted broadcast to `broadcasts.jsonl`,
both in the recordings directory, so restarted processes share one recorded chain and a verifier can count calls
apart from HTTP or UI responses.

The reserved wallet-id marker `fx-lost-sign` selects one authored fault: the signer reply is lost after signing.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edge_os_api.execution.original_transaction import (
    BALANCE_OF_SELECTOR,
    DECIMALS_SELECTOR,
    OriginalClients,
    ReplyLost,
    RouteProfile,
    RpcError,
    signing_request_key,
)

RECORDINGS_FILE = "original_transaction_v1.json"
MARKER_LOST_SIGN = "fx-lost-sign"


class RecordedLog:
    """An append-only JSON-lines record shared by every process that uses the same directory."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def append(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._path.exists():
                return []
            return [json.loads(line) for line in self._path.read_text().splitlines() if line]


@dataclass
class OriginalRecordings:
    """The loaded recording, its route profile, and the shared call and broadcast logs."""

    data: dict[str, Any]
    profile: RouteProfile
    calls: RecordedLog
    broadcasts: RecordedLog

    @classmethod
    def load(cls, directory: str | Path) -> "OriginalRecordings":
        root = Path(directory)
        data = json.loads((root / RECORDINGS_FILE).read_text())
        if data.get("schema") != "edge-os.original-transaction-recordings/1" or data.get("label") != "AUTHORED":
            raise ValueError("not an authored original-transaction recording")
        return cls(data=data, profile=RouteProfile.from_mapping(data["route_profile"]),
                   calls=RecordedLog(root / "calls.jsonl"), broadcasts=RecordedLog(root / "broadcasts.jsonl"))

    def clients(self, clock: Callable[[], dt.datetime]) -> OriginalClients:
        return OriginalClients(route=RecordedRouteClient(self), signer=RecordedSignerClient(self),
                               broadcast=RecordedBroadcastRpc(self), observer=RecordedObservationRpc(self, clock))

    def call_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.calls.entries():
            counts[entry["call"]] = counts.get(entry["call"], 0) + 1
        return counts


class RecordedRouteClient:
    def __init__(self, recordings: OriginalRecordings) -> None:
        self._recordings = recordings

    def quote(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self._recordings.calls.append({"call": "route.quote", "sell": request.get("sell_token"),
                                       "amount": request.get("amount")})
        for route in self._recordings.data["routes"]:
            wanted = route["request"]
            if (str(wanted["sell_token"]).lower(), str(wanted["buy_token"]).lower(), wanted["amount"]) == (
                    str(request.get("sell_token")).lower(), str(request.get("buy_token")).lower(),
                    request.get("amount")):
                return route["response"]
        return {"status": "error", "error": "NO_ROUTE"}


class RecordedSignerClient:
    """Privy `POST /v1/wallets/{wallet_id}/rpc`. A request with no recording is refused with an error body."""

    def __init__(self, recordings: OriginalRecordings) -> None:
        self._recordings = recordings

    def rpc(self, wallet_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        transaction = (body.get("params") or {}).get("transaction") or {}
        key = signing_request_key(transaction) if body.get("method") == "eth_signTransaction" else None
        self._recordings.calls.append({"call": "signer.rpc", "wallet_id": wallet_id, "request_key": key})
        response = next((item["response"] for item in self._recordings.data["signatures"]
                         if item["request_key"] == key), None)
        if response is None:
            return {"error": {"code": "invalid_request", "message": "no authored signature for this request"}}
        if MARKER_LOST_SIGN in wallet_id:
            raise ReplyLost("authored: the signer reply was lost after signing")
        return response


class RecordedBroadcastRpc:
    """`eth_getTransactionCount` and `eth_sendRawTransaction` over the shared recorded chain."""

    def __init__(self, recordings: OriginalRecordings) -> None:
        self._recordings = recordings

    def call(self, method: str, params: list[Any]) -> Any:
        self._recordings.calls.append({"call": f"broadcast.{method}"})
        if method == "eth_getTransactionCount":
            address = str(params[0]).lower()
            return hex(sum(1 for entry in self._recordings.broadcasts.entries() if entry["sender"] == address))
        if method == "eth_sendRawTransaction":
            raw = str(params[0])
            tx_hash = self._recordings.data["transaction_hashes"].get(raw)
            if tx_hash is None:
                raise RpcError("authored: transaction rejected")
            if not any(entry["hash"] == tx_hash for entry in self._recordings.broadcasts.entries()):
                sender = str(self._recordings.data["receipts"][tx_hash]["from"]).lower()
                self._recordings.broadcasts.append({"hash": tx_hash, "sender": sender})
            return tx_hash
        raise RpcError(f"authored: unsupported method {method}")


class RecordedObservationRpc:
    """Receipts and holdings reads. A receipt exists only for a hash the recorded chain accepted.

    The finalized block's time is the replay clock minus the recording's authored `age_seconds`: an authored age,
    not a claim that any chain was read now.
    """

    def __init__(self, recordings: OriginalRecordings, clock: Callable[[], dt.datetime]) -> None:
        self._recordings = recordings
        self._clock = clock

    def call(self, method: str, params: list[Any]) -> Any:
        self._recordings.calls.append({"call": f"observer.{method}"})
        data = self._recordings.data
        holdings = data["holdings"]
        wallet = str(data["wallet_address"]).lower()
        if method == "eth_chainId":
            return hex(int(data["chain_id"]))
        if method == "eth_getTransactionReceipt":
            tx_hash = str(params[0]).lower()
            accepted = any(entry["hash"] == tx_hash for entry in self._recordings.broadcasts.entries())
            return data["receipts"].get(tx_hash) if accepted else None
        if method == "eth_getBlockByNumber":
            moment = int(self._clock().timestamp()) - int(holdings["age_seconds"])
            return {"number": holdings["block_number"], "timestamp": hex(moment)}
        if method == "eth_getBalance":
            return holdings["native"] if str(params[0]).lower() == wallet else None
        if method == "eth_call":
            target = str(params[0].get("to", "")).lower()
            call_data = str(params[0].get("data", "")).lower()
            tokens = {token.lower(): value for token, value in holdings["tokens"].items()}
            decimals = {token.lower(): value for token, value in holdings["decimals"].items()}
            if target not in tokens:
                return None
            if call_data == DECIMALS_SELECTOR:
                return hex(int(decimals[target]))
            if call_data == BALANCE_OF_SELECTOR + "0" * 24 + wallet[2:]:
                return tokens[target]
            return None
        raise RpcError(f"authored: unsupported method {method}")
