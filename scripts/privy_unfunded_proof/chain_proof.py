"""Read-only Monad chain operations for the in-app trade control proofs.

LOCAL code; the controller runs it. Every operation is a read: ``eth_chainId``, ``eth_getBlockByNumber``,
``eth_getCode``, ``eth_call``, ``eth_estimateGas`` and ``debug_traceCall``. The client has no send path and
refuses every other method, sender, target, value, field and state override before any I/O. The calls
simulate the release's exact swap against the deployed entrypoint at one pinned block, with temporary
storage overrides for the wallet's WMON balance and entrypoint allowance (WMON slots ``3`` and ``4``, as in
``scripts/operator_trade/dry_run.py``); the approve estimate overrides only the balance. An override changes only the simulation; nothing is signed or sent.

Each negative simulation changes exactly one intent or fee word of the baseline swap. Its positive twin
runs at the same block with the same overrides. ``control_proofs`` turns the saved records into control
proofs. See ``docs/qualification/inapp-trade/CONTROL_PROOFS_PLAN.md``.

Provider error text and the endpoint are never saved or printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eth_utils import keccak

from edge_os_api.execution.original_transaction import ReplyLost, RpcError
from edge_os_api.execution.transaction_rpc_client import json_bytes, post_json, validate_bounds

# The release's frozen facts (docs/qualification/inapp-trade/release.authored.json). `release_inputs_match`
# refuses an authored release whose values differ.
CHAIN_ID = 143
WALLET = "0x91BB52A63c91986813288965e4681FF111De1b63"
ENTRYPOINT = "0xb3e6778480b2E488385E8205eA05E20060B813cb"
ROUTER = "0x2f84fb8982073f39ba47c7fcc29119af074abbcb"
WMON = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"
MOE = "0xd8e004acba279417c04c0633cb5a21ceca207777"
POOL = "0x97199b34564911936bc850ac45ede785892b5aad"
SINK = "0x000000000000000000000000000000000000dead"
ZERO_ADDRESS = "0x" + "0" * 40
PROGRAM_HEX = "0x023bd359c1119da7da1d913d1c4d2b7c461115433a01ffff0097199b34564911936bc850ac45ede785892b5aad00003e80"
PROGRAM_FEE_PPM = 16000
INPUT_RAW = 10 * 10**18
SWAP_GAS_LIMIT = 700_000

EXECUTE_SWAP_SELECTOR = "0xce1e7030"
APPROVE_SELECTOR = "0x095ea7b3"
BALANCE_OF_SELECTOR = "0x70a08231"
ALLOWANCE_SELECTOR = "0xdd62ed3e"
TOKEN0_SELECTOR = "0x0dfe1681"
TOKEN1_SELECTOR = "0xd21220a7"
RESERVES_SELECTOR = "0x0902f1ac"
GET_ROUTER_SELECTOR = "0x" + keccak(text="getRouter()")[:4].hex()

BALANCE_SLOT = 3
ALLOWANCE_SLOT = 4
FEE_CHARGED_BPS = 100
FEE_OVER_BOUND_BPS = 10001
# feeBps + referrerFeeBps = 10001: the sum bound, with both fee recipients set.
FEE_SUM_SPLIT_BPS = (5000, 5001)

RPC_URL_ENV = "EDGE_OS_CONTROL_PROOF_RPC_URL"
RESULTS_FILE = "chain_results.json"
RESULTS_SCHEMA = "edge-os.inapp-control-proof-chain-results/1"
READ_ONLY_METHODS = ("eth_chainId", "eth_getBlockByNumber", "eth_getCode", "eth_call", "eth_estimateGas",
                     "debug_traceCall")
MAX_RESPONSE_BYTES = 1_000_000
TIMEOUT_SECONDS = 30.0

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_QUANTITY = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)")
_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_DATA = re.compile(r"0x(?:[0-9a-fA-F]{2})*")
_TARGETS = frozenset({ENTRYPOINT.lower(), WMON.lower(), POOL.lower(), ROUTER.lower()})
_CALL_TARGETS = frozenset({ENTRYPOINT.lower(), WMON.lower(), POOL.lower()})


class ChainRefused(Exception):
    """Refused before any I/O. ``code`` is fixed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _address_word(value: str) -> str:
    return value[2:].lower().rjust(64, "0")


def _word(value: int) -> str:
    return f"{value:064x}"


def _mapping_slot(key: str, base: int) -> bytes:
    return keccak(bytes.fromhex(_address_word(key)) + base.to_bytes(32, "big"))


def balance_slot(owner: str) -> str:
    return "0x" + _mapping_slot(owner, BALANCE_SLOT).hex()


def allowance_slot(owner: str, spender: str) -> str:
    return "0x" + keccak(bytes.fromhex(_address_word(spender)) + _mapping_slot(owner, ALLOWANCE_SLOT)).hex()


# The wallet holds twice the input, so only the allowance (exactly the input) can bound what the entrypoint pulls.
STATE_OVERRIDES: Mapping[str, Any] = {WMON: {"stateDiff": {
    balance_slot(WALLET): "0x" + _word(2 * INPUT_RAW),
    allowance_slot(WALLET, ENTRYPOINT): "0x" + _word(INPUT_RAW),
}}}
# The approve estimate starts from a zero allowance, as the live approve does, so it prices the 0 -> input write.
APPROVE_OVERRIDES: Mapping[str, Any] = {WMON: {"stateDiff": {balance_slot(WALLET): "0x" + _word(2 * INPUT_RAW)}}}
TRACE_CONFIG: Mapping[str, Any] = {"tracer": "callTracer", "tracerConfig": {"withLog": True},
                                   "stateOverrides": STATE_OVERRIDES}
# The client compares requests with these sealed bytes, and every request is built from fresh copies of them,
# so a later change to the mappings above in the process cannot widen what the client sends.
_SEALED_OVERRIDES = (json_bytes(STATE_OVERRIDES), json_bytes(APPROVE_OVERRIDES))
_SEALED_TRACE_CONFIG = json_bytes(TRACE_CONFIG)


def _fresh(sealed: bytes) -> Any:
    return json.loads(sealed)


def swap_calldata(*, min_output_raw: int, buy: str = MOE, sell: str = WMON, amount: int = INPUT_RAW,
                  fee_bps: int = 0, fee_collector: str = ZERO_ADDRESS, referrer_fee_bps: int = 0,
                  referrer: str = ZERO_ADDRESS, program_hex: str = PROGRAM_HEX) -> str:
    """`executeSwap(SwapIntent, FeeCollection, bytes)` in the layout of the app's `build_calldata_hex`."""
    program = program_hex[2:]
    length = len(program) // 2
    padded = program + "0" * ((64 - len(program) % 64) % 64)
    return (EXECUTE_SWAP_SELECTOR + _address_word(buy) + _word(min_output_raw) + _address_word(sell)
            + _word(amount) + _address_word(fee_collector) + _word(fee_bps) + _address_word(referrer)
            + _word(referrer_fee_bps) + _word(0) + _word(10 * 32) + _word(length) + padded)


def approve_calldata(spender: str, amount: int) -> str:
    return APPROVE_SELECTOR + _address_word(spender) + _word(amount)


@dataclass(frozen=True)
class ChainOperation:
    op_id: str
    method: str
    expect: str  # RESULT (a read), SUCCESS (a simulation that must not revert) or REVERT


_OPERATIONS = (
    ChainOperation("chain.chain_id", "eth_chainId", "RESULT"),
    ChainOperation("chain.block", "eth_getBlockByNumber", "RESULT"),
    ChainOperation("chain.code_entrypoint", "eth_getCode", "RESULT"),
    ChainOperation("chain.code_router", "eth_getCode", "RESULT"),
    ChainOperation("chain.code_wmon", "eth_getCode", "RESULT"),
    ChainOperation("chain.code_pool", "eth_getCode", "RESULT"),
    ChainOperation("chain.get_router", "eth_call", "RESULT"),
    ChainOperation("chain.pool_token0", "eth_call", "RESULT"),
    ChainOperation("chain.pool_token1", "eth_call", "RESULT"),
    ChainOperation("chain.pool_reserves", "eth_call", "RESULT"),
    ChainOperation("chain.override_balance", "eth_call", "RESULT"),
    ChainOperation("chain.override_allowance", "eth_call", "RESULT"),
    ChainOperation("chain.swap_probe", "eth_call", "SUCCESS"),
    ChainOperation("chain.swap_min_equal", "eth_call", "SUCCESS"),
    ChainOperation("chain.swap_min_above", "eth_call", "REVERT"),
    ChainOperation("chain.swap_input_above_allowance", "eth_call", "REVERT"),
    ChainOperation("chain.swap_wrong_output", "eth_call", "REVERT"),
    ChainOperation("chain.swap_wrong_input", "eth_call", "REVERT"),
    ChainOperation("chain.swap_fee_over_bound", "eth_call", "REVERT"),
    ChainOperation("chain.swap_fee_sum_over_bound", "eth_call", "REVERT"),
    ChainOperation("chain.swap_fee_charged", "eth_call", "SUCCESS"),
    ChainOperation("chain.swap_trace", "debug_traceCall", "SUCCESS"),
    ChainOperation("chain.estimate_approve", "eth_estimateGas", "RESULT"),
    ChainOperation("chain.estimate_swap", "eth_estimateGas", "RESULT"),
    ChainOperation("chain.estimate_revoke", "eth_estimateGas", "RESULT"),
    ChainOperation("chain.swap_at_release_gas", "eth_call", "SUCCESS"),
)
OPERATION_ORDER: tuple[str, ...] = tuple(op.op_id for op in _OPERATIONS)
OPERATIONS: Mapping[str, ChainOperation] = {op.op_id: op for op in _OPERATIONS}
# These use the baseline output R that `chain.swap_probe` returned; without it they are skipped, never guessed.
DEPENDS_ON_BASELINE = ("chain.swap_min_equal", "chain.swap_min_above", "chain.swap_trace", "chain.estimate_swap",
                       "chain.swap_at_release_gas")


def _wallet_call(to: str, data: str, gas: int | None = None) -> dict[str, Any]:
    call: dict[str, Any] = {"from": WALLET, "to": to, "value": "0x0", "data": data}
    if gas is not None:
        call["gas"] = hex(gas)
    return call


def operation_params(op_id: str, *, block_tag: str, baseline_output: int | None) -> list[Any]:
    """The exact frozen params of one operation for one pinned block and one recorded baseline output."""
    overrides, approve_overrides = _fresh(_SEALED_OVERRIDES[0]), _fresh(_SEALED_OVERRIDES[1])
    swap = lambda **fields: _wallet_call(ENTRYPOINT, swap_calldata(**fields))  # noqa: E731
    if op_id in DEPENDS_ON_BASELINE and baseline_output is None:
        raise ChainRefused("BASELINE_OUTPUT_MISSING")
    r = baseline_output or 0
    plan: dict[str, list[Any]] = {
        "chain.chain_id": [],
        "chain.block": ["latest", False],
        "chain.code_entrypoint": [ENTRYPOINT, block_tag],
        "chain.code_router": [ROUTER, block_tag],
        "chain.code_wmon": [WMON, block_tag],
        "chain.code_pool": [POOL, block_tag],
        "chain.get_router": [{"to": ENTRYPOINT, "data": GET_ROUTER_SELECTOR}, block_tag],
        "chain.pool_token0": [{"to": POOL, "data": TOKEN0_SELECTOR}, block_tag],
        "chain.pool_token1": [{"to": POOL, "data": TOKEN1_SELECTOR}, block_tag],
        "chain.pool_reserves": [{"to": POOL, "data": RESERVES_SELECTOR}, block_tag],
        "chain.override_balance": [{"to": WMON, "data": BALANCE_OF_SELECTOR + _address_word(WALLET)},
                                   block_tag, overrides],
        "chain.override_allowance": [{"to": WMON, "data": ALLOWANCE_SELECTOR + _address_word(WALLET)
                                      + _address_word(ENTRYPOINT)}, block_tag, overrides],
        "chain.swap_probe": [swap(min_output_raw=1), block_tag, overrides],
        "chain.swap_min_equal": [swap(min_output_raw=r), block_tag, overrides],
        "chain.swap_min_above": [swap(min_output_raw=r + 1), block_tag, overrides],
        "chain.swap_input_above_allowance": [swap(min_output_raw=1, amount=INPUT_RAW + 1), block_tag, overrides],
        "chain.swap_wrong_output": [swap(min_output_raw=1, buy=WMON), block_tag, overrides],
        "chain.swap_wrong_input": [swap(min_output_raw=1, sell=MOE), block_tag, overrides],
        "chain.swap_fee_over_bound": [swap(min_output_raw=1, fee_bps=FEE_OVER_BOUND_BPS, fee_collector=SINK),
                                      block_tag, overrides],
        "chain.swap_fee_sum_over_bound": [swap(min_output_raw=1, fee_bps=FEE_SUM_SPLIT_BPS[0], fee_collector=SINK,
                                               referrer_fee_bps=FEE_SUM_SPLIT_BPS[1], referrer=SINK),
                                          block_tag, overrides],
        "chain.swap_fee_charged": [swap(min_output_raw=1, fee_bps=FEE_CHARGED_BPS, fee_collector=SINK),
                                   block_tag, overrides],
        "chain.swap_trace": [swap(min_output_raw=r), block_tag, _fresh(_SEALED_TRACE_CONFIG)],
        "chain.estimate_approve": [_wallet_call(WMON, approve_calldata(ENTRYPOINT, INPUT_RAW)), block_tag,
                                   approve_overrides],
        "chain.estimate_swap": [swap(min_output_raw=r), block_tag, overrides],
        "chain.estimate_revoke": [_wallet_call(WMON, approve_calldata(ENTRYPOINT, 0)), block_tag, overrides],
        "chain.swap_at_release_gas": [_wallet_call(ENTRYPOINT, swap_calldata(min_output_raw=r), SWAP_GAS_LIMIT),
                                      block_tag, overrides],
    }
    return plan[op_id]


def request_sha256(method: str, params: Any) -> str:
    return hashlib.sha256(json_bytes({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})).hexdigest()


def release_inputs_match(authored: Mapping[str, Any]) -> bool:
    """Whether the frozen chain inputs above are exactly the authored release's values."""
    try:
        release = authored["release"]
        route, quote, gas = release["route"], release["quote"], release["gas"]
        return bool(
            release["chain_id"] == CHAIN_ID and release["wallet_address"] == WALLET == route["recipient"]
            and route["entrypoint_address"] == ENTRYPOINT and route["selector"] == EXECUTE_SWAP_SELECTOR
            and route["method"] == "EXECUTE_SWAP"
            and release["deployment"]["router_address"] == ROUTER
            and route["input_asset"]["token_address"] == WMON == quote["token0_address"]
            and route["output_asset"]["token_address"] == MOE == quote["token1_address"]
            and quote["pool_address"] == POOL and quote["direction"] == 0
            and quote["program_fee_ppm"] == PROGRAM_FEE_PPM and route["approved_program_hex"] == PROGRAM_HEX
            and route["approved_input_raw"] == str(INPUT_RAW) == route["approved_allowance_raw"]
            and route["fees"] == {"fee_bps": 0, "referrer_fee_bps": 0, "fee_collector_address": ZERO_ADDRESS,
                                  "referrer_address": ZERO_ADDRESS, "is_in_token_fee": False}
            and gas["gas_limit"] == SWAP_GAS_LIMIT and authored["facts"]["gas_limits"]["swap"] == SWAP_GAS_LIMIT)
    except (KeyError, TypeError):
        return False


# ---------------------------------------------------------------- the read-only client


def _tag(value: Any) -> bool:
    return value == "latest" or (type(value) is str and _QUANTITY.fullmatch(value) is not None)


def _call_ok(call: Any, *, allow_gas: bool) -> bool:
    if type(call) is not dict:
        return False
    keys = set(call)
    if keys not in ({"to", "data"}, {"from", "to", "value", "data"}) and not (
            allow_gas and keys == {"from", "to", "value", "data", "gas"}):
        return False
    if type(call["to"]) is not str or call["to"].lower() not in _CALL_TARGETS:
        return False
    if "from" in call and (call["from"] != WALLET or call["value"] != "0x0"):
        return False
    if type(call["data"]) is not str or _DATA.fullmatch(call["data"]) is None:
        return False
    return "gas" not in call or (type(call["gas"]) is str and _QUANTITY.fullmatch(call["gas"]) is not None)


def _sealed(value: Any) -> bytes | None:
    try:
        return json_bytes(value)
    except (TypeError, ValueError):
        return None


def _allowed(method: str, params: Any) -> bool:
    if type(params) is not list:
        return False
    if method == "eth_chainId":
        return params == []
    if method == "eth_getBlockByNumber":
        return params == ["latest", False]
    if method == "eth_getCode":
        return (len(params) == 2 and type(params[0]) is str and params[0].lower() in _TARGETS
                and _tag(params[1]) and params[1] != "latest")
    if method in ("eth_call", "eth_estimateGas"):
        return (len(params) in (2, 3) and _call_ok(params[0], allow_gas=method == "eth_call")
                and _tag(params[1]) and params[1] != "latest"
                and (len(params) == 2 or _sealed(params[2]) in _SEALED_OVERRIDES))
    if method == "debug_traceCall":
        return (len(params) == 3 and _call_ok(params[0], allow_gas=False) and "from" in params[0]
                and _tag(params[1]) and params[1] != "latest" and _sealed(params[2]) == _SEALED_TRACE_CONFIG)
    return False


@dataclass(frozen=True)
class ChainReply:
    status: str  # RESULT, RPC_ERROR or REPLY_LOST
    result: Any = None
    error: Mapping[str, Any] | None = None


class ReadOnlyChainClient:
    """One bounded JSON-RPC read per call. There is no send, sign or state-changing method."""

    def __init__(self, *, transport: Any, endpoint: str, timeout_seconds: float = TIMEOUT_SECONDS,
                 max_response_bytes: int = MAX_RESPONSE_BYTES,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        try:
            validate_bounds(endpoint=endpoint, deadline=1.0, timeout=timeout_seconds,
                            request_bytes=1, response_bytes=max_response_bytes)
        except Exception as error:  # noqa: BLE001 - the endpoint value never enters the error text
            raise ChainRefused("RPC_ENDPOINT_INVALID") from error
        self._transport, self._endpoint = transport, endpoint
        self._timeout, self._max_response_bytes, self._monotonic = timeout_seconds, max_response_bytes, monotonic

    def __repr__(self) -> str:
        return "ReadOnlyChainClient(endpoint=<redacted>)"

    def call(self, method: str, params: list[Any]) -> ChainReply:
        if method not in READ_ONLY_METHODS:
            raise ChainRefused("CHAIN_METHOD_NOT_ALLOWED")
        if not _allowed(method, params):
            raise ChainRefused("CHAIN_CALL_INVALID")
        wire = json_bytes({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        lost = False
        reply: Any = None
        try:
            reply = post_json(http=self._transport, endpoint=self._endpoint, wire=wire,
                              headers={"content-type": "application/json"},
                              deadline=self._monotonic() + self._timeout, timeout=self._timeout,
                              max_response_bytes=self._max_response_bytes, monotonic=self._monotonic, cancel=None,
                              secrets=(self._endpoint,))
        except (ReplyLost, RpcError):
            lost = True
        if lost or type(reply) is not dict or reply.get("jsonrpc") != "2.0" or reply.get("id") != 1:
            return ChainReply("REPLY_LOST")
        if set(reply) == {"jsonrpc", "id", "result"}:
            return ChainReply("RESULT", result=reply["result"])
        if set(reply) == {"jsonrpc", "id", "error"} and type(reply["error"]) is dict:
            return ChainReply("RPC_ERROR", error=_error(reply["error"]))
        return ChainReply("REPLY_LOST")


def _error(error: Mapping[str, Any]) -> dict[str, Any]:
    """A fixed summary: the code, a revert verdict, bounded revert data and a hash of the message."""
    code = error.get("code") if type(error.get("code")) is int else None
    message = error.get("message")
    data = error.get("data")
    reverted = code == 3 or (type(message) is str and "revert" in message.lower())
    return {"code": code, "reverted": reverted,
            "data": data if type(data) is str and _DATA.fullmatch(data) and len(data) <= 2050 else None,
            "message_sha256": (hashlib.sha256(message.encode("utf-8")).hexdigest()
                               if type(message) is str else None)}


def _uint(result: Any) -> int | None:
    if type(result) is not str or _DATA.fullmatch(result) is None or len(result) != 66:
        return None
    return int(result, 16)


def run_chain_operations(client: ReadOnlyChainClient, *, clock: Callable[[], str]) -> list[dict[str, Any]]:
    """Run every operation once, in order, at one pinned block. A failed read is recorded, never retried."""
    records: list[dict[str, Any]] = []
    block_tag: str | None = None
    baseline: int | None = None
    for op_id in OPERATION_ORDER:
        operation = OPERATIONS[op_id]
        record: dict[str, Any] = {"op_id": op_id, "method": operation.method, "expect": operation.expect}
        if (op_id != "chain.chain_id" and op_id != "chain.block" and block_tag is None) or (
                op_id in DEPENDS_ON_BASELINE and baseline is None):
            records.append({**record, "params": None, "request_sha256": None, "status": "SKIPPED",
                            "result": None, "error": None, "at": clock()})
            continue
        params = operation_params(op_id, block_tag=block_tag or "latest", baseline_output=baseline)
        reply = client.call(operation.method, params)
        records.append({**record, "params": params, "request_sha256": request_sha256(operation.method, params),
                        "status": reply.status, "result": reply.result if reply.status == "RESULT" else None,
                        "error": dict(reply.error) if reply.error is not None else None, "at": clock()})
        if op_id == "chain.block" and reply.status == "RESULT" and type(reply.result) is dict \
                and type(reply.result.get("number")) is str and _QUANTITY.fullmatch(reply.result["number"]):
            block_tag = reply.result["number"]
        if op_id == "chain.swap_probe" and reply.status == "RESULT":
            value = _uint(reply.result)
            baseline = value if value is not None and value > 0 else None
    return records


# ---------------------------------------------------------------- operator command


def _transport() -> Any:
    from edge_os_api.research_history.http_clients.http_transport import StdlibHttpTransport

    return StdlibHttpTransport()


def _clock() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_new(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the read-only chain operations of the control proofs once.")
    parser.add_argument("--dry-run", action="store_true", help="list the operations; read nothing")
    parser.add_argument("--store", type=Path, help="a new directory for the one results file")
    args = parser.parse_args(argv)
    if args.dry_run:
        for op_id in OPERATION_ORDER:
            print(f"{op_id} method={OPERATIONS[op_id].method} expect={OPERATIONS[op_id].expect}")
        return 0
    if args.store is None:
        print("STORE_REQUIRED: pass a new --store directory")
        return 2
    if args.store.exists():
        print("STORE_ALREADY_EXISTS: one run uses one new store")
        return 2
    endpoint = os.environ.get(RPC_URL_ENV, "")
    if not endpoint:
        print(f"RPC_URL_MISSING: set {RPC_URL_ENV}")
        return 2
    try:
        client = ReadOnlyChainClient(transport=_transport(), endpoint=endpoint)
    except ChainRefused as refused:
        print(f"REFUSED {refused.code}")
        return 2
    records = run_chain_operations(client, clock=_clock)
    args.store.mkdir(parents=True, exist_ok=False)
    _write_new(args.store / RESULTS_FILE,
               json.dumps({"schema": RESULTS_SCHEMA, "operations": records}, sort_keys=True,
                          separators=(",", ":")).encode("utf-8"))
    for record in records:
        error = record["error"] or {}
        print(f"{record['op_id']} expect={record['expect']} status={record['status']} "
              f"reverted={str(error.get('reverted', False)).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
