"""One bounded JSON-RPC client for the operator reads, receipt polls and the single raw send.

This client is stricter than a general node client: one request per call, an exact method allowlist,
an exact reply shape, no retry, no redirect and no other endpoint. Provider text never enters an
error, and the endpoint is never returned or printed.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from eth_utils import keccak

from edge_os_api.execution.original_transaction import ReplyLost, RpcError
from edge_os_api.execution.transaction_rpc_client import json_bytes, post_json, validate_bounds

from scripts.operator_trade.errors import OperatorError

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_QUANTITY = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)")
_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_DATA = re.compile(r"0x(?:[0-9a-fA-F]{2})*")
_SIGNED = re.compile(r"0x(?:[0-9a-fA-F]{2})+")

READ_ONLY_METHODS = frozenset({
    "eth_chainId", "eth_blockNumber", "eth_getBalance", "eth_call", "eth_getCode",
    "eth_getTransactionCount", "eth_getBlockByNumber", "eth_getTransactionReceipt",
    "eth_maxPriorityFeePerGas",
})
WRITE_METHODS = frozenset({"eth_sendRawTransaction"})


def _tag(value: Any) -> bool:
    return value == "latest" or (type(value) is str and _QUANTITY.fullmatch(value) is not None)


def _allowed(method: str, params: Any) -> bool:
    if type(params) is not list:
        return False
    if method == "eth_chainId":
        return params == []
    if method == "eth_blockNumber":
        return params == []
    if method == "eth_maxPriorityFeePerGas":
        return params == []
    if method == "eth_getBalance":
        return (len(params) == 2 and type(params[0]) is str and _ADDRESS.fullmatch(params[0]) is not None
                and _tag(params[1]))
    if method == "eth_getCode":
        return (len(params) == 2 and type(params[0]) is str and _ADDRESS.fullmatch(params[0]) is not None
                and _tag(params[1]))
    if method == "eth_getTransactionCount":
        return (len(params) == 2 and type(params[0]) is str and _ADDRESS.fullmatch(params[0]) is not None
                and params[1] == "pending")
    if method == "eth_getBlockByNumber":
        return len(params) == 2 and _tag(params[0]) and params[1] is False
    if method == "eth_getTransactionReceipt":
        return len(params) == 1 and type(params[0]) is str and _HASH.fullmatch(params[0]) is not None
    if method == "eth_call":
        if len(params) != 2 or not _tag(params[1]) or type(params[0]) is not dict:
            return False
        call = params[0]
        return (set(call) == {"to", "data"} and type(call["to"]) is str and _ADDRESS.fullmatch(call["to"]) is not None
                and type(call["data"]) is str and _DATA.fullmatch(call["data"]) is not None)
    if method == "eth_sendRawTransaction":
        return len(params) == 1 and type(params[0]) is str and _SIGNED.fullmatch(params[0]) is not None
    return False


def _quantity(value: Any) -> int | None:
    if type(value) is not str or _QUANTITY.fullmatch(value) is None:
        return None
    return int(value, 16)


class OperatorRpc:
    def __init__(self, *, transport: Any, endpoint: str, timeout_seconds: float = 30.0,
                 max_response_bytes: int = 1_000_000,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        try:
            validate_bounds(endpoint=endpoint, deadline=1.0, timeout=timeout_seconds,
                            request_bytes=1, response_bytes=max_response_bytes)
        except Exception as error:  # noqa: BLE001 - a bad endpoint value never enters the error text
            raise OperatorError("RPC_ENDPOINT_INVALID") from error
        self._transport = transport
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._monotonic = monotonic

    def __repr__(self) -> str:
        return "OperatorRpc(endpoint=<redacted>)"

    def call(self, method: str, params: list[Any]) -> Any:
        if method in WRITE_METHODS or method not in READ_ONLY_METHODS:
            raise OperatorError("RPC_METHOD_NOT_ALLOWED")
        return self._request(method, params)

    def send_raw(self, signed_hex: str) -> str:
        result = self._request("eth_sendRawTransaction", [signed_hex])
        expected = "0x" + keccak(bytes.fromhex(signed_hex[2:])).hex()
        if type(result) is not str or result.lower() != expected:
            raise OperatorError("RPC_HASH_INVALID")
        return result

    def _request(self, method: str, params: list[Any]) -> Any:
        if not _allowed(method, params):
            raise OperatorError("RPC_CALL_INVALID", method)
        wire = json_bytes({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        secrets = (params[0],) if method == "eth_sendRawTransaction" else ()
        try:
            reply = post_json(
                http=self._transport, endpoint=self._endpoint, wire=wire,
                headers={"content-type": "application/json"},
                deadline=self._monotonic() + self._timeout, timeout=self._timeout,
                max_response_bytes=self._max_response_bytes, monotonic=self._monotonic,
                cancel=None, secrets=secrets,
            )
        except ReplyLost as error:
            raise OperatorError("RPC_REPLY_LOST") from error
        except RpcError as error:
            raise OperatorError("RPC_REFUSED", str(error)) from error
        if type(reply) is not dict or reply.get("jsonrpc") != "2.0" or type(reply.get("id")) is not int \
                or reply.get("id") != 1:
            raise OperatorError("RPC_REPLY_UNRECOGNIZED")
        if set(reply) == {"jsonrpc", "id", "error"}:
            error = reply["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise OperatorError("RPC_REFUSED", str(code) if type(code) is int else "")
        if set(reply) != {"jsonrpc", "id", "result"}:
            raise OperatorError("RPC_REPLY_UNRECOGNIZED")
        return self._validate(method, reply["result"])

    @staticmethod
    def _validate(method: str, result: Any) -> Any:
        if method in ("eth_chainId", "eth_blockNumber", "eth_getBalance", "eth_getTransactionCount",
                      "eth_maxPriorityFeePerGas"):
            if _quantity(result) is None:
                raise OperatorError("RPC_QUANTITY_INVALID", method)
            return result
        if method == "eth_getCode":
            if type(result) is not str or _DATA.fullmatch(result) is None:
                raise OperatorError("RPC_CODE_INVALID")
            return result
        if method == "eth_call":
            if type(result) is not str or _DATA.fullmatch(result) is None:
                raise OperatorError("RPC_CALL_REPLY_INVALID")
            return result
        if method == "eth_getBlockByNumber":
            if type(result) is not dict or "baseFeePerGas" not in result:
                raise OperatorError("RPC_BLOCK_INVALID")
            if _quantity(result["baseFeePerGas"]) is None:
                raise OperatorError("RPC_QUANTITY_INVALID", "baseFeePerGas")
            return result
        if method == "eth_getTransactionReceipt":
            if result is None:
                return None
            if type(result) is not dict:
                raise OperatorError("RPC_RECEIPT_INVALID")
            for field in ("status", "blockNumber", "gasUsed"):
                if _quantity(result.get(field)) is None:
                    raise OperatorError("RPC_RECEIPT_INVALID", field)
            if result["status"] not in ("0x0", "0x1"):
                raise OperatorError("RPC_RECEIPT_STATUS_INVALID")
            return result
        if method == "eth_sendRawTransaction":
            if type(result) is not str or _HASH.fullmatch(result) is None:
                raise OperatorError("RPC_HASH_INVALID")
            return result
        raise OperatorError("RPC_METHOD_NOT_ALLOWED")
