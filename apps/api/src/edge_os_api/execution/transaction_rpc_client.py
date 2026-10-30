"""Finite, exact-request RPC clients. No retry, replacement or runtime mount."""
from __future__ import annotations

import json
import math
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from eth_utils import keccak

from edge_os_api.execution.original_transaction import (
    BALANCE_OF_SELECTOR, DECIMALS_SELECTOR, ReplyLost, RpcError,
)
from edge_os_api.research_history.http_clients.client_config import validate_endpoint
from edge_os_api.research_history.http_clients.http_transport import HttpResponse, HttpTransport

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_QUANTITY = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)")
_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_DATA = re.compile(r"0x(?:[0-9a-fA-F]{2})*")
OBSERVER_METHODS = frozenset({"eth_chainId", "eth_getTransactionReceipt", "eth_getBlockByNumber", "eth_getBalance", "eth_call"})


def json_bytes(value: Any) -> bytes:
    """Canonical request bytes; reject non-JSON types and non-finite numbers."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("duplicate JSON field")
    return dict(pairs)


def _invalid_constant(value: str) -> None:
    raise ValueError("non-JSON constant")


def _parse(raw: bytes) -> Any:
    result = None
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                            parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        pass
    return result


def _matches(pattern: re.Pattern[str], value: Any) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def validate_bounds(*, endpoint: str, deadline: float, timeout: float, request_bytes: int, response_bytes: int) -> None:
    """Check local finite limits without reading time, credentials or network."""
    invalid = False
    try:
        validate_endpoint(endpoint)
    except Exception:
        invalid = True
    if invalid:
        raise ValueError("CLIENT_ENDPOINT_INVALID")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (deadline, timeout)) or timeout <= 0:
        raise ValueError("CLIENT_TIME_BOUND_INVALID")
    if any(type(x) is not int or x <= 0 for x in (request_bytes, response_bytes)):
        raise ValueError("CLIENT_BYTE_BOUND_INVALID")


def request_stopped(*, cancel: Callable[[], bool] | None, monotonic: Callable[[], float], deadline: float) -> bool:
    """Treat invalid, expired or failing stop observations as stopped."""
    stopped = True
    try:
        flag = False if cancel is None else cancel()
        now = monotonic()
        stopped = type(flag) is not bool or flag or type(now) not in (int, float) or not math.isfinite(now) or now >= deadline
    except Exception:
        pass
    return stopped


def post_json(*, http: HttpTransport, endpoint: str, wire: bytes, headers: Mapping[str, str],
              deadline: float, timeout: float, max_response_bytes: int, monotonic: Callable[[], float],
              cancel: Callable[[], bool] | None, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    """One bounded transport call with sanitized errors, including their cause and context."""
    stopped = request_stopped(cancel=cancel, monotonic=monotonic, deadline=deadline)
    if stopped:
        raise RpcError("CLIENT_STOPPED_BEFORE_SEND")
    response = None
    lost = False
    try:
        response = http.request(method="POST", url=endpoint, headers=dict(headers), body=wire,
                                timeout=timeout, deadline=deadline,
                                max_response_bytes=max_response_bytes, cancel=cancel)
    except Exception:
        lost = True
    if lost:
        raise ReplyLost("CLIENT_REPLY_LOST")
    stopped = request_stopped(cancel=cancel, monotonic=monotonic, deadline=deadline)
    if stopped:
        raise ReplyLost("CLIENT_REPLY_AFTER_STOP")
    parsed = None
    try:
        if (isinstance(response, HttpResponse) and type(response.status) is int and response.status == 200
                and isinstance(response.headers, Mapping) and type(response.body) is bytes
                and len(response.body) <= max_response_bytes):
            encoding = [value for key, value in response.headers.items() if key.lower() == "content-encoding"]
            lengths = [value for key, value in response.headers.items() if key.lower() == "content-length"]
            framing_ok = not lengths or (len(lengths) == 1 and type(lengths[0]) is str
                and re.fullmatch(r"0|[1-9][0-9]*", lengths[0]) is not None and int(lengths[0]) == len(response.body))
            if framing_ok and (not encoding or encoding == ["identity"]):
                parsed = _parse(response.body)
                text = json.dumps([parsed, dict(response.headers)], ensure_ascii=True).lower()
                if any(secret and secret.lower() in text for secret in secrets):
                    parsed = None
    except Exception:
        parsed = None
    if type(parsed) is not dict:
        raise RpcError("CLIENT_REPLY_REFUSED")
    if request_stopped(cancel=cancel, monotonic=monotonic, deadline=deadline):
        raise ReplyLost("CLIENT_REPLY_AFTER_STOP")
    return parsed


def _tag(value: Any) -> bool:
    return value == "finalized" or _matches(_QUANTITY, value)


def _allowed(role: str, method: Any, params: Any) -> bool:
    if type(params) is not list or type(method) is not str:
        return False
    if role == "broadcast":
        if method == "eth_getTransactionCount":
            return len(params) == 2 and _matches(_ADDRESS, params[0]) and params[1] == "pending"
        return (method == "eth_sendRawTransaction" and len(params) == 1 and _matches(_DATA, params[0])
                and 2 < len(params[0]) <= 16386)
    if method not in OBSERVER_METHODS:
        return False
    if method == "eth_chainId":
        return params == []
    if method == "eth_getTransactionReceipt":
        return len(params) == 1 and _matches(_HASH, params[0])
    if method == "eth_getBlockByNumber":
        return len(params) == 2 and _tag(params[0]) and params[1] is False
    if method == "eth_getBalance":
        return len(params) == 2 and _matches(_ADDRESS, params[0]) and _tag(params[1])
    if len(params) != 2 or not _tag(params[1]) or type(params[0]) is not dict or set(params[0]) != {"to", "data"}:
        return False
    target, data = params[0]["to"], params[0]["data"]
    return (_matches(_ADDRESS, target) and type(data) is str
            and (data == DECIMALS_SELECTOR or re.fullmatch(BALANCE_OF_SELECTOR + r"0{24}[0-9a-fA-F]{40}", data) is not None))


class TransactionRpcClient:
    """One frozen ordered call plan, with a separate destination and role for each client."""

    def __init__(self, *, role: str, destination_id: str, endpoint: str,
                 plan: Sequence[tuple[str, list[Any] | None]], http: HttpTransport, deadline_monotonic: float,
                 connect_timeout_seconds: float, max_request_bytes: int, max_response_bytes: int,
                 cancel: Callable[[], bool] | None = None, monotonic: Callable[[], float] = time.monotonic,
                 original_bytes: Callable[[], str] | None = None) -> None:
        validate_bounds(endpoint=endpoint, deadline=deadline_monotonic, timeout=connect_timeout_seconds,
                        request_bytes=max_request_bytes, response_bytes=max_response_bytes)
        if (role not in ("broadcast", "observer") or type(destination_id) is not str
                or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", destination_id) is None):
            raise ValueError("RPC_DESTINATION_INVALID")
        frozen = []
        invalid = False
        try:
            if not plan or len(plan) > 128:
                invalid = True
            for index, (method, params) in enumerate(plan):
                saved_original = role == "broadcast" and method == "eth_sendRawTransaction" and params is None and callable(original_bytes)
                if not saved_original and not _allowed(role, method, params):
                    invalid = True
                wire = json_bytes({"jsonrpc": "2.0", "id": index + 1, "method": method, "params": params})
                if len(wire) > max_request_bytes:
                    invalid = True
                frozen.append(wire)
            if role == "broadcast" and [json.loads(w)["method"] for w in frozen] not in (
                    ["eth_getTransactionCount"], ["eth_sendRawTransaction"],
                    ["eth_getTransactionCount", "eth_sendRawTransaction"]):
                invalid = True
        except Exception:
            invalid = True
        if invalid:
            raise ValueError("RPC_PLAN_INVALID")
        if original_bytes is not None and (role != "broadcast" or not callable(original_bytes)):
            raise ValueError("RPC_ORIGINAL_BINDING_INVALID")
        self._original_bytes, self._max_request_bytes = original_bytes, max_request_bytes
        self._role, self._destination_id = role, destination_id
        self._endpoint, self._plan, self._http = endpoint, tuple(frozen), http
        self._deadline, self._timeout = deadline_monotonic, connect_timeout_seconds
        self._max_response_bytes, self._cancel, self._monotonic = max_response_bytes, cancel, monotonic
        self._index, self._lock = 0, threading.Lock()

    @property
    def role(self) -> str:
        return self._role

    @property
    def destination_id(self) -> str:
        return self._destination_id

    def __repr__(self) -> str:
        return f"TransactionRpcClient(role={self.role!r}, destination_id={self.destination_id!r})"

    def call(self, method: str, params: list[Any]) -> Any:
        if not _allowed(self._role, method, params):
            raise RpcError("RPC_CALL_NOT_ALLOWED")
        wire = None
        with self._lock:
            try:
                if self._index < len(self._plan):
                    slot = self._index
                    expected = self._plan[slot]
                    frozen = json.loads(expected)
                    if frozen["method"] == method and frozen["params"] is None:
                        self._index = slot + 1
                        if not request_stopped(cancel=self._cancel, monotonic=self._monotonic, deadline=self._deadline):
                            saved = self._original_bytes()
                            if _allowed("broadcast", method, [saved]):
                                frozen["params"] = [saved]
                                expected = json_bytes(frozen)
                    supplied = json_bytes({"jsonrpc": "2.0", "id": frozen["id"], "method": method, "params": params})
                    if supplied == expected and len(expected) <= self._max_request_bytes:
                        wire = expected
                        self._index = slot + 1
            except Exception:
                pass
        if wire is None:
            raise RpcError("RPC_CALL_NOT_IN_PLAN")
        request = json.loads(wire)
        secrets = (request["params"][0],) if method == "eth_sendRawTransaction" else ()
        reply = post_json(http=self._http, endpoint=self._endpoint, wire=wire, headers={"content-type": "application/json"},
                          deadline=self._deadline, timeout=self._timeout, max_response_bytes=self._max_response_bytes,
                          monotonic=self._monotonic, cancel=self._cancel, secrets=secrets)
        if (set(reply) != {"jsonrpc", "id", "result"} or reply["jsonrpc"] != "2.0"
                or type(reply["id"]) is not int or reply["id"] != request["id"]):
            raise RpcError("RPC_REPLY_UNRECOGNIZED")
        result = reply["result"]
        if method in ("eth_chainId", "eth_getTransactionCount", "eth_getBalance") and not _matches(_QUANTITY, result):
            raise RpcError("RPC_QUANTITY_INVALID")
        if method == "eth_sendRawTransaction":
            expected_hash = "0x" + keccak(bytes.fromhex(request["params"][0][2:])).hex()
            if not _matches(_HASH, result) or result.lower() != expected_hash:
                raise RpcError("RPC_HASH_INVALID")
        if method == "eth_call" and not (type(result) is str and re.fullmatch(r"0x[0-9a-fA-F]{64}", result)):
            raise RpcError("RPC_WORD_INVALID")
        if method in ("eth_getBlockByNumber", "eth_getTransactionReceipt") and result is not None:
            result = _observation_result(method, result)
            for key in ("number", "timestamp", "gasLimit", "gasUsed", "baseFeePerGas", "blockNumber", "status", "effectiveGasPrice", "transactionIndex", "cumulativeGasUsed", "type"):
                if key in result and not _matches(_QUANTITY, result[key]):
                    raise RpcError("RPC_QUANTITY_INVALID")
        if request_stopped(cancel=self._cancel, monotonic=self._monotonic, deadline=self._deadline):
            raise ReplyLost("RPC_REPLY_AFTER_STOP")
        return result


def _observation_result(method: str, result: Any) -> dict[str, Any]:
    block = method == "eth_getBlockByNumber"
    required = {"number", "hash", "timestamp"} if block else {
        "blockHash", "blockNumber", "transactionHash", "from", "to", "status", "gasUsed", "effectiveGasPrice", "logs"}
    known = required | ({"baseFeePerGas", "parentHash", "sha3Uncles", "miner", "stateRoot", "transactionsRoot",
        "receiptsRoot", "logsBloom", "difficulty", "totalDifficulty", "size", "gasLimit", "gasUsed", "extraData",
        "mixHash", "nonce", "uncles", "transactions", "withdrawals", "withdrawalsRoot", "blobGasUsed", "excessBlobGas",
        "parentBeaconBlockRoot", "requestsHash"} if block else {
        "type", "transactionIndex", "cumulativeGasUsed", "contractAddress", "logsBloom"})
    if type(result) is not dict or not required <= set(result) <= known:
        raise RpcError("RPC_OBJECT_INVALID")
    for key in ({"hash"} if block else {"blockHash", "transactionHash"}):
        if not _matches(_HASH, result[key]):
            raise RpcError("RPC_HASH_INVALID")
    if not block:
        if not all(_matches(_ADDRESS, result[key]) for key in ("from", "to")) or result["status"] not in ("0x0", "0x1"):
            raise RpcError("RPC_RECEIPT_INVALID")
        if type(result["logs"]) is not list:
            raise RpcError("RPC_LOG_INVALID")
        for log in result["logs"]:
            fields = {"address", "topics", "data", "blockNumber", "transactionHash", "transactionIndex", "blockHash", "logIndex", "removed"}
            if (type(log) is not dict or set(log) != fields or not _matches(_ADDRESS, log["address"])
                    or type(log["topics"]) is not list or not all(_matches(_HASH, x) for x in log["topics"])
                    or not _matches(_DATA, log["data"]) or type(log["removed"]) is not bool
                    or not all(_matches(_QUANTITY, log[x]) for x in ("blockNumber", "transactionIndex", "logIndex"))
                    or not all(_matches(_HASH, log[x]) for x in ("blockHash", "transactionHash"))):
                raise RpcError("RPC_LOG_INVALID")
    retained = required | {"baseFeePerGas"}
    if not block:
        retained.add("transactionIndex")
    return {key: value for key, value in result.items() if key in retained}
