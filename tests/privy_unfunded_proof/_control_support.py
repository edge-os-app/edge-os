"""Recorded doubles for the control-proof tests. Every reply is authored here; nothing is fetched.

``FakeChain`` answers the read-only JSON-RPC calls of ``chain_proof`` from a tiny authored model of the
deployed entrypoint: the direct V2 pool formula, the intent tokens, the allowance, the fee bound and the
minimum output. The model is a recorded fake, not a claim about the real contract. ``privy_store``
writes Privy outcome records shaped exactly as ``actual_runner`` saves them.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from eth_utils import keccak

from edge_os_api.research_history.http_clients.http_transport import HttpResponse
from scripts.privy_unfunded_proof import chain_proof
from scripts.privy_unfunded_proof.actual_packet import (
    ACTUAL_EVIDENCE_CLASS,
    CONTROL_PROOF_ORDER,
    CONTROL_PROOF_PACKET,
    PROVIDER_PROOF_UNQUALIFIED,
    UNFUNDED_POLICY_PROFILE_ID,
)

REPO = Path(__file__).resolve().parents[2]
AUTHORED_PATH = REPO / "docs/qualification/inapp-trade/release.authored.json"
SOURCE_DIR = REPO / "docs/qualification/kuru-deployed-source"

RESERVE_WMON = 1_000_000 * 10**18
RESERVE_MOE = 75_000_000 * 10**18
BLOCK = 0x6D00000
BLOCK_HASH = "0x" + "ab" * 32
BASE_FEE = 100_000_000_000
ESTIMATES = {"approve": 46_000, "swap": 544_967, "revoke": 30_000}
FAKE_CODE = {"wmon": "0x60026000", "pool": "0x60036000"}
TRANSFER_TOPIC = "0x" + keccak(text="Transfer(address,address,uint256)").hex()


def _runtime(name: str) -> str:
    return "0x" + (SOURCE_DIR / name).read_text(encoding="ascii").strip().removeprefix("0x")


ENTRYPOINT_CODE = _runtime("entrypoint-runtime-block-0x6c1db44.hex")
ROUTER_CODE = _runtime("current-router-runtime-block-0x6c1db44.hex")


def code_sha256(code_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(code_hex[2:])).hexdigest()


def authored() -> dict[str, Any]:
    """The real authored release, with the WMON and pool code hashes of the fake chain's code."""
    value = json.loads(AUTHORED_PATH.read_text(encoding="utf-8"))
    value["facts"]["code_sha256"]["wmon"] = code_sha256(FAKE_CODE["wmon"])
    value["facts"]["code_sha256"]["pool"] = code_sha256(FAKE_CODE["pool"])
    return value


def pool_output(amount: int) -> int:
    kept = 10**6 - chain_proof.PROGRAM_FEE_PPM
    return amount * kept * RESERVE_MOE // (RESERVE_WMON * 10**6 + amount * kept)


def _word(value: int) -> str:
    return "0x" + value.to_bytes(32, "big").hex()


def _address(word: str) -> str:
    return "0x" + word[-40:]


def _topic_address(address: str) -> str:
    return "0x" + address[2:].lower().rjust(64, "0")


class Revert(Exception):
    pass


class FakeChain:
    """An authored JSON-RPC peer. ``overrides`` replace a reply per op-shaped key for negative tests."""

    def __init__(self, *, trace_logs: bool = True, state_overrides_honoured: bool = True,
                 debug_supported: bool = True, pool_fee_payouts: dict[str, int] | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.trace_logs = trace_logs
        # WMON the pool pays out of the input in the trace, as in the live trace of 2026-10-23.
        self.pool_fee_payouts = pool_fee_payouts or {}
        self.state_overrides_honoured = state_overrides_honoured
        self.debug_supported = debug_supported
        self.replace: dict[str, Any] = {}

    # -- HttpTransport seam
    def request(self, *, method: str, url: str, headers: dict, body: bytes, timeout: float, deadline: float,
                max_response_bytes: int, cancel: Any = None) -> HttpResponse:
        wire = json.loads(body)
        self.requests.append(wire)
        reply = self._answer(wire["method"], wire["params"])
        raw = json.dumps({"jsonrpc": "2.0", "id": wire["id"], **reply}).encode("utf-8")
        return HttpResponse(status=200, headers={"content-type": "application/json"}, body=raw)

    def _answer(self, method: str, params: list[Any]) -> dict[str, Any]:
        try:
            result = self._result(method, params)
        except Revert:
            return {"error": {"code": 3, "message": "execution reverted", "data": "0x08c379a0" + "00" * 4}}
        except NotImplementedError:
            return {"error": {"code": -32601, "message": "the method does not exist"}}
        return {"result": result}

    def _overrides_ok(self, params: list[Any]) -> bool:
        return self.state_overrides_honoured and len(params) == 3

    def _result(self, method: str, params: list[Any]) -> Any:
        key = f"{method}:{json.dumps(params, sort_keys=True)}"
        if key in self.replace:
            value = self.replace[key]
            if isinstance(value, Exception):
                raise value
            return value
        if method == "eth_chainId":
            return "0x8f"
        if method == "eth_getBlockByNumber":
            return {"number": hex(BLOCK), "hash": BLOCK_HASH, "baseFeePerGas": hex(BASE_FEE),
                    "transactions": []}
        if method == "eth_getCode":
            address = params[0].lower()
            return {chain_proof.ENTRYPOINT.lower(): ENTRYPOINT_CODE, chain_proof.ROUTER.lower(): ROUTER_CODE,
                    chain_proof.WMON.lower(): FAKE_CODE["wmon"],
                    chain_proof.POOL.lower(): FAKE_CODE["pool"]}[address]
        if method == "eth_call":
            call = params[0]
            if "gas" in call and int(call["gas"], 16) < ESTIMATES["swap"]:
                raise Revert()
            return self._call(call, params)
        if method == "eth_estimateGas":
            call = params[0]
            self._call(call, params)
            if call["to"].lower() == chain_proof.ENTRYPOINT.lower():
                return hex(ESTIMATES["swap"])
            amount = int(call["data"][-64:], 16)
            if amount and self._overrides_ok(params) and chain_proof.allowance_slot(
                    chain_proof.WALLET, chain_proof.ENTRYPOINT) in params[2][chain_proof.WMON]["stateDiff"]:
                return hex(ESTIMATES["approve"] - 20_000)  # a same-value write is cheaper than the live 0 -> input
            return hex(ESTIMATES["approve"] if amount else ESTIMATES["revoke"])
        if method == "debug_traceCall":
            if not self.debug_supported:
                raise NotImplementedError
            call = params[0]
            output = self._call(call, [call, params[1], params[2]["stateOverrides"]])
            return self._trace(call, output)
        raise NotImplementedError

    def _call(self, call: dict[str, Any], params: list[Any]) -> str:
        to, data = call["to"].lower(), call["data"]
        if to == chain_proof.ENTRYPOINT.lower() and data == chain_proof.GET_ROUTER_SELECTOR:
            return _word(int(chain_proof.ROUTER, 16))
        if to == chain_proof.POOL.lower():
            return {chain_proof.TOKEN0_SELECTOR: _word(int(chain_proof.WMON, 16)),
                    chain_proof.TOKEN1_SELECTOR: _word(int(chain_proof.MOE, 16)),
                    chain_proof.RESERVES_SELECTOR: _word(RESERVE_WMON)[:66] + _word(RESERVE_MOE)[2:]
                    + _word(1)[2:]}[data]
        if to == chain_proof.WMON.lower():
            if data.startswith(chain_proof.BALANCE_OF_SELECTOR):
                return _word(2 * chain_proof.INPUT_RAW if self._overrides_ok(params) else 0)
            if data.startswith(chain_proof.ALLOWANCE_SELECTOR):
                funded = self._overrides_ok(params) and chain_proof.allowance_slot(
                    chain_proof.WALLET, chain_proof.ENTRYPOINT) in params[2][chain_proof.WMON]["stateDiff"]
                return _word(chain_proof.INPUT_RAW if funded else 0)
            if data.startswith(chain_proof.APPROVE_SELECTOR):
                return _word(1)
        if to == chain_proof.ENTRYPOINT.lower() and data.startswith(chain_proof.EXECUTE_SWAP_SELECTOR):
            return _word(self._swap(data, self._overrides_ok(params)))
        raise Revert()

    def _swap(self, data: str, funded: bool) -> int:
        words = [data[10 + 64 * i: 10 + 64 * (i + 1)] for i in range(10)]
        buy, minimum, sell, amount = _address(words[0]), int(words[1], 16), _address(words[2]), int(words[3], 16)
        fee_bps, referrer_bps = int(words[5], 16), int(words[7], 16)
        allowance = chain_proof.INPUT_RAW if funded else 0
        if sell.lower() != chain_proof.WMON.lower() or amount > allowance:
            raise Revert()
        if fee_bps + referrer_bps > 10000:
            raise Revert()
        output = pool_output(amount)
        user = output - output * (fee_bps + referrer_bps) // 10000
        if buy.lower() != chain_proof.MOE.lower() or user < minimum:
            raise Revert()
        return user

    def _trace(self, call: dict[str, Any], output: str) -> dict[str, Any]:
        amount = int(call["data"][10 + 64 * 3: 10 + 64 * 4], 16)
        out = int(output, 16)
        wallet, entry, router, pool = (chain_proof.WALLET, chain_proof.ENTRYPOINT, chain_proof.ROUTER,
                                       chain_proof.POOL)

        def transfer(token: str, sender: str, receiver: str, value: int) -> dict[str, Any]:
            return {"address": token, "topics": [TRANSFER_TOPIC, _topic_address(sender), _topic_address(receiver)],
                    "data": _word(value)}

        inner = {"type": "CALL", "from": entry, "to": router, "value": "0x0", "input": "0x", "output": "0x",
                 "gas": "0x1", "gasUsed": "0x1",
                 "calls": [{"type": "CALL", "from": router, "to": pool, "value": "0x0", "input": "0x",
                            "output": "0x", "gas": "0x1", "gasUsed": "0x1",
                            "logs": ([transfer(chain_proof.WMON, pool, recipient, value)
                                      for recipient, value in self.pool_fee_payouts.items()]
                                     + [transfer(chain_proof.MOE, pool, router, out)]) if self.trace_logs else []}],
                 "logs": ([transfer(chain_proof.WMON, entry, pool, amount),
                           transfer(chain_proof.MOE, router, entry, out)] if self.trace_logs else [])}
        return {"type": "CALL", "from": wallet, "to": entry, "value": "0x0", "input": call["data"],
                "output": output, "gas": "0x1", "gasUsed": "0x1",
                "calls": [{"type": "CALL", "from": entry, "to": chain_proof.WMON, "value": "0x0", "input": "0x",
                           "output": _word(1), "gas": "0x1", "gasUsed": "0x1",
                           "logs": [transfer(chain_proof.WMON, wallet, entry, amount)] if self.trace_logs else []},
                          inner],
                "logs": [transfer(chain_proof.MOE, entry, wallet, out)] if self.trace_logs else []}


# The net WMON fee payouts of the controller's live chain.swap_trace (2026-10-23): 1.00% and 0.35% of the 10 WMON
# input. The pool kept 9.865 WMON.
LIVE_FEE_PAYOUTS = {"0xe1c8b73343f5a83ebe165be90470d84b00e33022": 100_000_000_000_000_000,
                    "0x681c3f796ae388026634c26025504d7c45248998": 35_000_000_000_000_000}


def chain_client(fake: FakeChain) -> chain_proof.ReadOnlyChainClient:
    return chain_proof.ReadOnlyChainClient(transport=fake, endpoint="https://rpc.example.test/rpc")


def recorded_chain(**fake_options: Any) -> list[dict[str, Any]]:
    fake = FakeChain(**fake_options)
    return chain_proof.run_chain_operations(chain_client(fake), clock=lambda: "2026-10-24T00:00:00Z")


def privy_records(**changes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Outcome records shaped as ``actual_runner`` saves them for a matching live run of the control packet."""
    packet = CONTROL_PROOF_PACKET
    records: dict[str, dict[str, Any]] = {}
    for specimen_id in CONTROL_PROOF_ORDER:
        expected = packet.specimen_expected[specimen_id]
        if expected == "ALLOW":
            outcome, reason = "ALLOW", "SIGNED_FIELDS_MATCH"
        elif expected == "EXPIRY_REFUSAL":
            outcome, reason = "UNKNOWN", "EXPIRY_REFUSAL"
        else:
            outcome, reason = "POLICY_DENY", "PRIVY_POLICY_VIOLATION"
        record = {
            "specimen_id": specimen_id, "profile": "raw", "packet_id": packet.packet_id,
            "reply_profile_id": UNFUNDED_POLICY_PROFILE_ID, "policy_id": packet.profile_policies["raw"],
            "policy_sha256": packet.profile_policy_sha256["raw"],
            "request_sha256": packet.requests[specimen_id].request_sha256, "expected": expected,
            "outcome": outcome, "reason": reason, "matches_expectation": True,
            "capture_record_sha256": hashlib.sha256(specimen_id.encode()).hexdigest(),
            "evidence_class": ACTUAL_EVIDENCE_CLASS, "provider_proof": PROVIDER_PROOF_UNQUALIFIED,
            "completed_at": "2026-10-24T00:00:00Z",
        }
        if outcome == "ALLOW":
            record["signed_bytes_sha256"] = "sha256:" + "cd" * 32
        record.update(changes.get(specimen_id, {}))
        records[specimen_id] = record
    return records


def privy_captures() -> dict[str, str]:
    """The SHA-256 of each saved capture file; ``privy_records`` cites the same values."""
    return {specimen_id: hashlib.sha256(specimen_id.encode()).hexdigest() for specimen_id in CONTROL_PROOF_ORDER}


def replaced(records: list[dict[str, Any]], op_id: str, **fields: Any) -> list[dict[str, Any]]:
    copied = copy.deepcopy(records)
    for record in copied:
        if record["op_id"] == op_id:
            record.update(fields)
    return copied
