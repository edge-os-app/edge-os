"""Pure proof builder for in-app trade controls 4-8 and 10-12.

It turns recorded results into control proof artifacts and their SHA-256 in the shape ``check_release``
reads: ``{"state": "ENFORCED", "evidence_class": "PROVIDER_ACTUAL", "proof_sha256": <hash>}``. The inputs are
the authored release, the Privy outcome records of the sealed control-proof packet (saved by
``actual_runner``) and the chain records (saved by ``chain_proof``). It makes no request and reads no
credential; the command reads three local paths and writes one new directory.

A control is proven only when every rule below holds. Anything else leaves it in ``unproven`` with a fixed
reason, and no state is produced for it. Three controls are ``decision_required`` even when their evidence is
complete, because the provider covers only part of the control: their artifact and hash are produced, but no
state, until the builder decides. ``opaque_program`` is never proven here: neither the Privy policy nor the
entrypoint bounds the program bytes. See ``docs/qualification/inapp-trade/CONTROL_PROOFS_PLAN.md``.

The artifacts are only as authentic as the records. Chain records can be re-checked by anyone at the pinned
block; Privy records cannot, so the controller commits the raw store with the artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scripts.privy_unfunded_proof import chain_proof
from scripts.privy_unfunded_proof.actual_packet import (
    ACTUAL_EVIDENCE_CLASS,
    CONTROL_PROOF_ORDER,
    PROVIDER_PROOF_UNQUALIFIED,
    CONTROL_PROOF_PACKET,
    UNFUNDED_POLICY_PROFILE_ID,
)
from scripts.privy_unfunded_proof.specimens import canonical_json

ARTIFACT_SCHEMA = "edge-os.inapp-control-proof/1"
CONTROLS = ("input_output_assets", "raw_input", "recipient", "minimum_output", "fees", "gas_action_capacity",
            "expiry_freshness", "opaque_program")
TRANSFER_TOPIC = "0x" + chain_proof.keccak(text="Transfer(address,address,uint256)").hex()
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_QUANTITY = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)")
_ACTIVE_STEPS = ("approve", "swap", "revoke")

# Each proven artifact states what its evidence shows and what it does not.
_CLAIMS: Mapping[str, tuple[str, ...]] = {
    "input_output_assets": (
        "The deployed entrypoint, simulated at the pinned block, refuses the release swap when the intent names "
        "WMON (the input token) as the output token, or MOE (not approved) as the input token; the release "
        "tokens succeed.",
        "The Privy policy refuses an approval of the entrypoint on MOE, so the agent cannot give the entrypoint "
        "an input allowance on a token other than WMON (rule R2 allows WMON only).",
    ),
    "raw_input": (
        "The release swap's output equals the pool formula for the approved input at the pinned reserves, which "
        "is consistent with exactly that input being swapped.",
        "With an allowance of exactly the approved input, an intent one unit above it reverts, which is "
        "consistent with the entrypoint pulling the full intent amount through the allowance.",
    ),
    "recipient": (
        "A call trace of the release swap shows that the whole MOE output reaches the wallet (msg.sender), that "
        "the wallet pays exactly the input, that no other address gains MOE, and that no address gains WMON "
        "except the pool and the pinned fee recipients, each at most its pinned share of the input (1.00% and "
        "0.35%).",
        "The Privy policy refuses executeSwapWithReceiver even with the wallet as receiver, and refuses an MOE "
        "transfer, so the agent can sign neither another receiver nor a later move of the output.",
    ),
    "minimum_output": (
        "At the pinned block the release swap (zero fees) succeeds with the minimum equal to its output and "
        "reverts with the minimum one unit above it: the deployed entrypoint enforces the minimum exactly.",
    ),
    "fees": (
        "With the release's zero fees the output equals the pool formula, so no fee is taken.",
        "A fee of 10001 bps reverts where 100 bps succeeds, and a fee of 5000 bps plus a referrer fee of 5001 "
        "bps reverts where 5000 plus 4999 succeeds: the deployed entrypoint reads the fee fields and bounds "
        "their sum at 10000 bps; the 100 bps fee lowers the output.",
    ),
    "gas_action_capacity": (
        "At the pinned block each step's gas limit is at least ceil(1.2 x eth_estimateGas), the swap succeeds "
        "at its release gas limit, twice the base fee plus the priority fee fits the release maximum fee, and "
        "the budget covers every step's limit at that fee.",
    ),
    "expiry_freshness": (
        "Privy refuses the in-policy release swap when its privy-request-expiry is past. The app sends the "
        "release's request_expires_at, which is the intent expiry valid_until, as that header, so no "
        "signature is issued after valid_until.",
    ),
}
_LIMITS: Mapping[str, tuple[str, ...]] = {
    "input_output_assets": (
        "The Privy policy does not bind tokenUserBuys or tokenUserSells. The output token has no provider "
        "bound: the host names it, and the test shows only that the entrypoint refuses the input token as "
        "output, not that it refuses every other token.",
        "The Privy row covers new approvals only; an allowance on another token granted before the policy is "
        "not covered.",
        "The simulation shows one block; the router is mutable by its owner, so the release's router recheck "
        "still applies before the run.",
    ),
    "raw_input": (
        "The Privy policy caps the approval at 70 WMON, not at the release input; the host approves exactly "
        "the input.",
        "Storage overrides fund the simulation; the live trade needs the real balance and allowance.",
    ),
    "recipient": (
        "The trace depends on the node's debug_traceCall with state overrides; it is one block.",
        "The two fee recipients and their bounds are pinned from the controller's live trace of 2026-10-23, not "
        "from source: no pair source or ABI in this repository names them or their rates. When the trace pays "
        "them, the artifact is decision_required (FEE_RECIPIENTS_OBSERVED_NOT_SOURCE_BOUND) and lists each "
        "observed recipient and amount. The bounds are what was observed; no provider bounds them.",
        "The trace covers the release's zero-fee calldata. The Privy policy does not bind the fee fields, so a "
        "host-encoded fee collector could take up to 100% of the output; only the host's zero-fee encoding "
        "(control fees, itself a builder decision) prevents it.",
        "Only WMON and MOE Transfer logs are counted; the trace check also refuses any frame that moves native "
        "value.",
        "A different program could route value elsewhere; that is the opaque_program control.",
    ),
    "minimum_output": (
        "The host computes the minimum from its own reserves read; the Privy policy does not bind it.",
        "The pool can move between the read and the trade; the check then reverts the swap.",
        "The boundary is tested with the release's zero fees only.",
    ),
    "fees": (
        "The control also requires the fee values, collector and referrer to equal the adopted (zero) values. "
        "No provider enforces that: the Privy policy does not bind the fee fields, and a nonzero fee up to "
        "10000 bps with any collector would be signed and would execute. Only the host encodes zero fees.",
    ),
    "gas_action_capacity": (
        "The estimate is for the pinned block; a later state change is covered only by the 1.2 margin.",
        "The action, attempt, signer and broadcast counts are host limits (LOCAL_TESTED), not provider limits.",
    ),
    "expiry_freshness": (
        "Control 11 is defined at the HOST layer (quote age, input age, intent and mandate expiry). This proof "
        "covers the provider-side signing cutoff only.",
        "The quote age (30 s) and input age (60 s) are host checks; the provider cannot see the quote time.",
        "The Flow intent has no on-chain deadline; after signing, the minimum output is the on-chain protection.",
        "The expiry row has no same-calldata allow twin in this packet; that its body is in policy rests on rule "
        "R3 and the v3 row raw.allow_swap_zero_value. The refusal is read from an error code that says the "
        "request or its authorization signature expired (400 request_expired, or such a code on a 401); the "
        "capture saves that code. If the row was re-run alone, the record cites the earlier store by hash.",
    ),
}


# Complete evidence that covers only part of the control. Adopting it as the control's proof is a builder decision.
DECISION_REQUIRED: Mapping[str, str] = {
    "input_output_assets": "OUTPUT_TOKEN_NOT_PROVIDER_BOUND",
    "fees": "FEE_VALUES_NOT_PROVIDER_BOUND",
    "expiry_freshness": "PROVIDER_COVERS_SIGNING_CUTOFF_ONLY",
}


# Complete evidence whose own findings need a builder decision: the release swap paid the observed fee recipients,
# which this repository cannot justify. A trace that pays only the pool and the wallet stays ENFORCED.
FEE_RECIPIENTS_DECISION = "FEE_RECIPIENTS_OBSERVED_NOT_SOURCE_BOUND"


def _evidence_decision(name: str, findings: Mapping[str, Any]) -> str | None:
    return FEE_RECIPIENTS_DECISION if name == "recipient" and findings.get("fee_transfers") else None


class ProofRefused(ValueError):
    """The inputs cannot be evaluated at all. ``code`` is fixed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Unproven(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _uint(value: Any) -> int | None:
    if type(value) is not str or re.fullmatch(r"0x[0-9a-fA-F]{64}", value) is None:
        return None
    return int(value, 16)


def _quantity(value: Any) -> int | None:
    return int(value, 16) if type(value) is str and _QUANTITY.fullmatch(value) else None


def _word_address(value: Any) -> str | None:
    number = _uint(value)
    return None if number is None or number >= 2**160 else "0x" + f"{number:040x}"


def required_gas_limit(estimate: int) -> int:
    """`ceil(estimate * 1.2)`, the release rule."""
    return (estimate * 6 + 4) // 5


def pool_formula(amount: int, reserve_in: int, reserve_out: int) -> int:
    kept = 10**6 - chain_proof.PROGRAM_FEE_PPM
    return amount * kept * reserve_out // (reserve_in * 10**6 + amount * kept)


def authored_binding_sha256(authored: Mapping[str, Any]) -> str:
    """The authored facts the proofs rest on. The controls are excluded, so adopting a proof keeps it valid."""
    release = authored["release"]
    return _sha256({
        "release": {key: release[key] for key in ("release_id", "chain_id", "wallet_id", "wallet_address",
                                                   "signer_id", "policy_id", "policy_content_sha256",
                                                   "deployment", "route", "quote", "gas", "transaction",
                                                   "limits", "valid_until")},
        "facts": {key: authored["facts"][key] for key in ("start", "active_steps", "gas_limits", "code_sha256")},
    })


# ---------------------------------------------------------------- chain records


def _check_chain_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Every record must be the frozen operation for its recorded block and baseline, in the frozen order."""
    if (not isinstance(records, Sequence) or len(records) != len(chain_proof.OPERATION_ORDER)
            or [r.get("op_id") if isinstance(r, Mapping) else None for r in records]
            != list(chain_proof.OPERATION_ORDER)):
        raise ProofRefused("CHAIN_RECORDS_INCOMPLETE")
    by_id = {record["op_id"]: record for record in records}
    block = by_id["chain.block"]
    block_tag = None
    if block.get("status") == "RESULT" and isinstance(block.get("result"), Mapping) \
            and _quantity(block["result"].get("number")) is not None:
        block_tag = block["result"]["number"]
    probe = by_id["chain.swap_probe"]
    baseline = _uint(probe.get("result")) if probe.get("status") == "RESULT" else None
    baseline = baseline if baseline else None
    for op_id in chain_proof.OPERATION_ORDER:
        record, operation = by_id[op_id], chain_proof.OPERATIONS[op_id]
        skipped = ((op_id not in ("chain.chain_id", "chain.block") and block_tag is None)
                   or (op_id in chain_proof.DEPENDS_ON_BASELINE and baseline is None))
        if record.get("method") != operation.method or record.get("expect") != operation.expect:
            raise ProofRefused("CHAIN_RECORD_MISMATCH")
        if skipped:
            if record.get("status") != "SKIPPED" or record.get("params") is not None:
                raise ProofRefused("CHAIN_RECORD_MISMATCH")
            continue
        params = chain_proof.operation_params(op_id, block_tag=block_tag or "latest", baseline_output=baseline)
        if (record.get("status") not in ("RESULT", "RPC_ERROR", "REPLY_LOST") or record.get("params") != params
                or record.get("request_sha256") != chain_proof.request_sha256(operation.method, params)):
            raise ProofRefused("CHAIN_RECORD_MISMATCH")
    return by_id


class _Chain:
    def __init__(self, authored: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]) -> None:
        self.authored, self.by_id = authored, by_id
        self.used: set[str] = set()

    def record(self, op_id: str) -> Mapping[str, Any]:
        self.used.add(op_id)
        return self.by_id[op_id]

    def result(self, op_id: str) -> Any:
        record = self.record(op_id)
        if record.get("status") != "RESULT":
            raise _Unproven("CHAIN_PRECONDITION_FAILED")
        return record["result"]

    def success(self, op_id: str) -> int:
        """A simulation that returned one uint256 word."""
        record = self.record(op_id)
        value = _uint(record.get("result")) if record.get("status") == "RESULT" else None
        if value is None:
            raise _Unproven("CHAIN_RESULT_CONTRARY")
        return value

    def reverted(self, op_id: str) -> None:
        record = self.record(op_id)
        error = record.get("error")
        if record.get("status") != "RPC_ERROR" or not isinstance(error, Mapping) or error.get("reverted") is not True:
            raise _Unproven("CHAIN_RESULT_CONTRARY")

    def preconditions(self) -> dict[str, Any]:
        """The deployment, the pool and the overrides are what the release names, and the baseline succeeded."""
        release, facts = self.authored["release"], self.authored["facts"]
        deployment = release["deployment"]
        codes = {"chain.code_entrypoint": deployment["entrypoint_code_sha256"],
                 "chain.code_router": deployment["router_code_sha256"],
                 "chain.code_wmon": facts["code_sha256"]["wmon"], "chain.code_pool": facts["code_sha256"]["pool"]}
        if self.result("chain.chain_id") != hex(chain_proof.CHAIN_ID):
            raise _Unproven("CHAIN_PRECONDITION_FAILED")
        block = self.result("chain.block")
        if (not isinstance(block, Mapping) or _quantity(block.get("number")) is None
                or _quantity(block.get("baseFeePerGas")) is None
                or type(block.get("hash")) is not str or re.fullmatch(r"0x[0-9a-fA-F]{64}", block["hash"]) is None):
            raise _Unproven("CHAIN_PRECONDITION_FAILED")
        for op_id, expected in codes.items():
            code = self.result(op_id)
            if (type(code) is not str or re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", code) is None
                    or hashlib.sha256(bytes.fromhex(code[2:])).hexdigest() != expected):
                raise _Unproven("CHAIN_PRECONDITION_FAILED")
        if (_word_address(self.result("chain.get_router")) != chain_proof.ROUTER.lower()
                or _word_address(self.result("chain.pool_token0")) != chain_proof.WMON.lower()
                or _word_address(self.result("chain.pool_token1")) != chain_proof.MOE.lower()):
            raise _Unproven("CHAIN_PRECONDITION_FAILED")
        reserves = self.result("chain.pool_reserves")
        if type(reserves) is not str or re.fullmatch(r"0x[0-9a-fA-F]{192}", reserves) is None:
            raise _Unproven("CHAIN_PRECONDITION_FAILED")
        reserve_wmon, reserve_moe = int(reserves[2:66], 16), int(reserves[66:130], 16)
        if (_uint(self.result("chain.override_balance")) != 2 * chain_proof.INPUT_RAW
                or _uint(self.result("chain.override_allowance")) != chain_proof.INPUT_RAW
                or reserve_wmon <= 0 or reserve_moe <= 0):
            raise _Unproven("CHAIN_PRECONDITION_FAILED")
        try:
            output = self.success("chain.swap_probe")
        except _Unproven:
            raise _Unproven("CHAIN_PRECONDITION_FAILED") from None
        if output <= 0:
            raise _Unproven("CHAIN_PRECONDITION_FAILED")
        return {"block_number": int(block["number"], 16), "block_hash": block["hash"],
                "base_fee_per_gas": int(block["baseFeePerGas"], 16), "reserve_wmon": reserve_wmon,
                "reserve_moe": reserve_moe, "baseline_output": output,
                "formula_output": pool_formula(chain_proof.INPUT_RAW, reserve_wmon, reserve_moe)}

    def evidence(self) -> list[dict[str, Any]]:
        items = []
        for op_id in sorted(self.used):
            record = self.by_id[op_id]
            error = record.get("error")
            items.append({"kind": "chain", "operation": op_id, "method": record["method"],
                          "request_sha256": record.get("request_sha256"), "record_sha256": _sha256(record),
                          "status": record.get("status"),
                          "reverted": error.get("reverted") if isinstance(error, Mapping) else None})
        return items


def _trace_findings(trace: Any, output: int) -> dict[str, Any]:
    """Net token movements of the release swap trace.

    Only the wallet may gain MOE, exactly the output. The wallet pays exactly the input in WMON. Only the pool and
    the pinned fee recipients may gain WMON, each recipient at most its pinned bound. Anything else is refused.
    """
    wallet, entry = chain_proof.WALLET.lower(), chain_proof.ENTRYPOINT.lower()
    tokens = {chain_proof.WMON.lower(), chain_proof.MOE.lower()}
    if (not isinstance(trace, Mapping) or trace.get("type") != "CALL" or "error" in trace
            or str(trace.get("from", "")).lower() != wallet or str(trace.get("to", "")).lower() != entry
            or trace.get("input") != chain_proof.swap_calldata(min_output_raw=output)
            or _uint(trace.get("output")) != output):
        raise _Unproven("TRACE_TRANSFERS_INVALID")
    net: dict[str, dict[str, int]] = {token: {} for token in tokens}
    touched: set[str] = set()
    frames, transfers = [trace], 0
    while frames:
        frame = frames.pop()
        if (not isinstance(frame, Mapping) or "error" in frame or type(frame.get("to")) is not str
                or frame.get("value", "0x0") not in ("0x0", None)):
            raise _Unproven("TRACE_TRANSFERS_INVALID")
        touched.add(frame["to"].lower())
        for log in frame.get("logs") or []:
            topics = log.get("topics") if isinstance(log, Mapping) else None
            if not isinstance(topics, list) or not topics or topics[0] != TRANSFER_TOPIC:
                continue
            token = str(log.get("address", "")).lower()
            amount = _uint(log.get("data"))
            sender, receiver = (_word_address(topics[1]), _word_address(topics[2])) if len(topics) == 3 else (None, None)
            if token not in tokens or amount is None or sender is None or receiver is None:
                raise _Unproven("TRACE_TRANSFERS_INVALID")
            net[token][sender] = net[token].get(sender, 0) - amount
            net[token][receiver] = net[token].get(receiver, 0) + amount
            transfers += 1
        frames.extend(frame.get("calls") or [])
    moe, wmon = net[chain_proof.MOE.lower()], net[chain_proof.WMON.lower()]
    pool = chain_proof.POOL.lower()
    wmon_gains = {address: value for address, value in wmon.items() if value > 0}
    fee_gains = {address: value for address, value in wmon_gains.items() if address != pool}
    if (transfers == 0
            or {address for address, value in moe.items() if value > 0} != {wallet} or moe[wallet] != output
            or wmon.get(wallet) != -chain_proof.INPUT_RAW
            or any(address not in chain_proof.OBSERVED_FEE_RECIPIENTS_PPM
                   or value > fee_bound_raw(address) for address, value in fee_gains.items())):
        raise _Unproven("TRACE_TRANSFERS_INVALID")
    return {"moe_received_by_wallet_raw": str(output), "wmon_paid_by_wallet_raw": str(chain_proof.INPUT_RAW),
            "wmon_received_by_pool_raw": str(wmon_gains.get(pool, 0)),
            "fee_transfers": [{"token": chain_proof.WMON, "recipient": address, "amount_raw": str(value),
                               "bound_ppm_of_input": chain_proof.OBSERVED_FEE_RECIPIENTS_PPM[address],
                               "bound_raw": str(fee_bound_raw(address))}
                              for address, value in sorted(fee_gains.items())],
            "transfer_logs": transfers, "touched_addresses": sorted(touched)}


def fee_bound_raw(recipient: str) -> int:
    """The most WMON one pinned fee recipient may gain from the release swap: its ppm of the input, rounded down."""
    return chain_proof.INPUT_RAW * chain_proof.OBSERVED_FEE_RECIPIENTS_PPM[recipient] // 10**6


# ---------------------------------------------------------------- privy records


def _expected_reply(specimen_id: str) -> tuple[str, str]:
    expected = CONTROL_PROOF_PACKET.specimen_expected[specimen_id]
    return {"ALLOW": ("ALLOW", "SIGNED_FIELDS_MATCH"), "EXPIRY_REFUSAL": ("UNKNOWN", "EXPIRY_REFUSAL"),
            "POLICY_DENY": ("POLICY_DENY", "PRIVY_POLICY_VIOLATION")}[expected]


class _Privy:
    def __init__(self, records: Mapping[str, Mapping[str, Any]], captures: Mapping[str, str],
                 earlier: Mapping[str, Mapping[str, Any]]) -> None:
        self.records, self.captures, self.earlier = records, captures, earlier
        self.used: set[str] = set()

    def _rerun_valid(self, specimen_id: str, record: Mapping[str, Any]) -> bool:
        """A record without ``rerun_of`` stands alone. A re-run expiry record must cite, by hash, the earlier
        store's positive control and its own earlier attempt, which ended UNKNOWN / UNRECOGNIZED_REPLY."""
        rerun = record.get("rerun_of")
        earlier = self.earlier.get(specimen_id)
        if rerun is None:
            return earlier is None
        positive = self.records.get(CONTROL_PROOF_ORDER[0])
        return (CONTROL_PROOF_PACKET.specimen_expected[specimen_id] == "EXPIRY_REFUSAL"
                and isinstance(rerun, Mapping) and isinstance(earlier, Mapping) and isinstance(positive, Mapping)
                and set(rerun) == {"earlier_outcome_record_sha256", "positive_control_outcome_record_sha256"}
                and rerun["earlier_outcome_record_sha256"] == _sha256(earlier)
                and rerun["positive_control_outcome_record_sha256"] == _sha256(positive)
                and earlier.get("specimen_id") == specimen_id and earlier.get("outcome") == "UNKNOWN"
                and earlier.get("reason") == "UNRECOGNIZED_REPLY"
                and earlier.get("packet_id") == CONTROL_PROOF_PACKET.packet_id
                and earlier.get("request_sha256") == record.get("request_sha256"))

    def _valid(self, specimen_id: str) -> bool:
        packet, record = CONTROL_PROOF_PACKET, self.records.get(specimen_id)
        outcome, reason = _expected_reply(specimen_id)
        return (isinstance(record, Mapping) and record.get("specimen_id") == specimen_id
                and record.get("profile") == "raw" and record.get("packet_id") == packet.packet_id
                and record.get("reply_profile_id") == UNFUNDED_POLICY_PROFILE_ID
                and record.get("policy_id") == packet.profile_policies["raw"]
                and record.get("policy_sha256") == packet.profile_policy_sha256["raw"]
                and record.get("request_sha256") == packet.requests[specimen_id].request_sha256
                and record.get("expected") == packet.specimen_expected[specimen_id]
                and record.get("outcome") == outcome and record.get("reason") == reason
                and record.get("matches_expectation") is True
                and record.get("evidence_class") == ACTUAL_EVIDENCE_CLASS
                and record.get("provider_proof") == PROVIDER_PROOF_UNQUALIFIED
                and (outcome != "ALLOW" or (type(record.get("signed_bytes_sha256")) is str
                                            and re.fullmatch(r"sha256:[0-9a-f]{64}", record["signed_bytes_sha256"])
                                            is not None))
                and type(record.get("capture_record_sha256")) is str
                and _HEX64.fullmatch(record["capture_record_sha256"]) is not None
                and self.captures.get(specimen_id) == record["capture_record_sha256"]
                and self._rerun_valid(specimen_id, record))

    def refused(self, specimen_id: str) -> None:
        """The row's provider reply matched, after the packet's positive control signed in policy."""
        positive = CONTROL_PROOF_ORDER[0]
        if not (self._valid(positive) and self._valid(specimen_id)):
            raise _Unproven("PRIVY_RECORD_INVALID")
        self.used.update({positive, specimen_id})

    def evidence(self) -> list[dict[str, Any]]:
        return [{"kind": "privy", "operation": specimen_id,
                 "request_sha256": self.records[specimen_id]["request_sha256"],
                 "record_sha256": _sha256(self.records[specimen_id]),
                 "capture_record_sha256": self.records[specimen_id]["capture_record_sha256"],
                 "outcome": self.records[specimen_id]["outcome"], "reason": self.records[specimen_id]["reason"],
                 **({"rerun_of": dict(self.records[specimen_id]["rerun_of"])}
                    if "rerun_of" in self.records[specimen_id] else {})}
                for specimen_id in sorted(self.used)]


# ---------------------------------------------------------------- per-control rules


def _input_output_assets(chain: _Chain, privy: _Privy, base: dict[str, Any]) -> dict[str, Any]:
    chain.reverted("chain.swap_wrong_output")
    chain.reverted("chain.swap_wrong_input")
    privy.refused("raw.ctl_deny_approve_moe_entrypoint")
    return {"input_token": chain_proof.WMON, "output_token": chain_proof.MOE,
            "baseline_output_raw": str(base["baseline_output"])}


def _raw_input(chain: _Chain, privy: _Privy, base: dict[str, Any]) -> dict[str, Any]:
    chain.record("chain.pool_reserves")
    if base["baseline_output"] != base["formula_output"]:
        raise _Unproven("CHAIN_RESULT_CONTRARY")
    chain.reverted("chain.swap_input_above_allowance")
    return {"input_raw": str(chain_proof.INPUT_RAW), "baseline_output_raw": str(base["baseline_output"]),
            "formula_output_raw": str(base["formula_output"]), "reserve_wmon_raw": str(base["reserve_wmon"]),
            "reserve_moe_raw": str(base["reserve_moe"])}


def _recipient(chain: _Chain, privy: _Privy, base: dict[str, Any]) -> dict[str, Any]:
    privy.refused("raw.ctl_deny_swap_receiver_wallet")
    privy.refused("raw.ctl_deny_moe_transfer_sink")
    record = chain.record("chain.swap_trace")
    if record.get("status") != "RESULT":
        raise _Unproven("TRACE_UNAVAILABLE")
    return {"recipient": chain_proof.WALLET, **_trace_findings(record.get("result"), base["baseline_output"])}


def _minimum_output(chain: _Chain, privy: _Privy, base: dict[str, Any]) -> dict[str, Any]:
    if chain.success("chain.swap_min_equal") != base["baseline_output"]:
        raise _Unproven("CHAIN_RESULT_CONTRARY")
    chain.reverted("chain.swap_min_above")
    return {"accepted_minimum_raw": str(base["baseline_output"]),
            "refused_minimum_raw": str(base["baseline_output"] + 1)}


def _fees(chain: _Chain, privy: _Privy, base: dict[str, Any]) -> dict[str, Any]:
    chain.record("chain.pool_reserves")
    if base["baseline_output"] != base["formula_output"]:
        raise _Unproven("CHAIN_RESULT_CONTRARY")
    chain.reverted("chain.swap_fee_over_bound")
    chain.reverted("chain.swap_fee_sum_over_bound")
    if chain.success("chain.swap_fee_sum_at_bound") <= 0:
        raise _Unproven("CHAIN_RESULT_CONTRARY")
    charged = chain.success("chain.swap_fee_charged")
    if not 0 < charged < base["baseline_output"]:
        raise _Unproven("CHAIN_RESULT_CONTRARY")
    return {"zero_fee_output_raw": str(base["baseline_output"]), "formula_output_raw": str(base["formula_output"]),
            "fee_bps_charged": chain_proof.FEE_CHARGED_BPS, "charged_output_raw": str(charged),
            "fee_bps_refused": chain_proof.FEE_OVER_BOUND_BPS,
            "fee_and_referrer_bps_refused": list(chain_proof.FEE_SUM_SPLIT_BPS),
            "fee_and_referrer_bps_accepted": list(chain_proof.FEE_SUM_AT_BOUND_BPS)}


def _gas_action_capacity(chain: _Chain, privy: _Privy, base: dict[str, Any], authored: Mapping[str, Any]
                         ) -> dict[str, Any]:
    release, facts = authored["release"], authored["facts"]
    gas, limits = release["gas"], facts["gas_limits"]
    chain.record("chain.block")
    estimates = {}
    for step in _ACTIVE_STEPS:
        value = _quantity(chain.result(f"chain.estimate_{step}"))
        if value is None or value <= 0:
            raise _Unproven("CHAIN_RESULT_CONTRARY")
        estimates[step] = value
    if chain.success("chain.swap_at_release_gas") != base["baseline_output"]:
        raise _Unproven("CHAIN_RESULT_CONTRARY")
    if any(limits[step] < required_gas_limit(estimates[step]) for step in _ACTIVE_STEPS):
        raise _Unproven("GAS_LIMIT_BELOW_ESTIMATE_MARGIN")
    if 2 * base["base_fee_per_gas"] + gas["max_priority_fee_per_gas"] > gas["max_fee_per_gas"]:
        raise _Unproven("BASE_FEE_ABOVE_RELEASE_FEE")
    if facts["active_steps"] != list(_ACTIVE_STEPS) or \
            int(gas["budget_raw"]) < sum(limits[step] for step in _ACTIVE_STEPS) * gas["max_fee_per_gas"]:
        raise _Unproven("GAS_BUDGET_SHORT")
    return {"estimates": estimates, "gas_limits": {step: limits[step] for step in _ACTIVE_STEPS},
            "required_limits": {step: required_gas_limit(estimates[step]) for step in _ACTIVE_STEPS},
            "base_fee_per_gas": base["base_fee_per_gas"], "max_fee_per_gas": gas["max_fee_per_gas"],
            "max_priority_fee_per_gas": gas["max_priority_fee_per_gas"], "budget_raw": gas["budget_raw"]}


def _expiry_freshness(privy: _Privy, authored: Mapping[str, Any]) -> dict[str, Any]:
    release = authored["release"]
    marker = {"$fill": "valid_until"}
    if not (release["transaction"]["request_expires_at"] == release["valid_until"] == marker
            == release["route"]["freshness"]["intent_expires_at"]):
        raise _Unproven("AUTHORED_EXPIRY_NOT_BOUND")
    privy.refused("raw.ctl_deny_expired_request")
    return {"expired_request_header_ms": dict(CONTROL_PROOF_PACKET.requests["raw.ctl_deny_expired_request"]
                                              .headers)["privy-request-expiry"],
            "signing_cutoff": "release.transaction.request_expires_at = valid_until = intent_expires_at"}


def _artifact(name: str, authored: Mapping[str, Any], chain: _Chain | None, privy: _Privy | None,
              base: dict[str, Any] | None, findings: dict[str, Any], *, state: str,
              evidence_class: str | None, claims: tuple[str, ...], limits: tuple[str, ...],
              decision: str | None = None) -> dict[str, Any]:
    packet = CONTROL_PROOF_PACKET
    return {
        "schema": ARTIFACT_SCHEMA, "control": name, "state": state, "evidence_class": evidence_class,
        "decision_required": decision,
        "release_id": authored["release"]["release_id"], "authored_binding_sha256": authored_binding_sha256(authored),
        "chain": None if base is None else {"chain_id": chain_proof.CHAIN_ID, "block_number": base["block_number"],
                                            "block_hash": base["block_hash"]},
        "privy": None if privy is None or not privy.used else {
            "packet_id": packet.packet_id, "policy_id": packet.profile_policies["raw"],
            "policy_sha256": packet.profile_policy_sha256["raw"], "reply_profile_id": UNFUNDED_POLICY_PROFILE_ID},
        "evidence": (chain.evidence() if chain is not None else []) + (privy.evidence() if privy is not None else []),
        "findings": findings, "claims": list(claims), "limits": list(limits),
    }


def build_control_proofs(*, authored: Mapping[str, Any], privy_records: Mapping[str, Mapping[str, Any]],
                         privy_capture_sha256: Mapping[str, str],
                         chain_records: Sequence[Mapping[str, Any]],
                         privy_earlier_records: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Proofs for the controls the records prove, and a fixed reason for every other control.

    ``privy_capture_sha256`` maps each specimen id to the SHA-256 of its saved capture file; an outcome record
    counts only when its ``capture_record_sha256`` equals it. ``privy_earlier_records`` holds the earlier
    outcome record of a row that was re-run alone (the expiry row only); the re-run record must cite it.
    """
    earlier = privy_earlier_records or {}
    if not chain_proof.release_inputs_match(authored):
        raise ProofRefused("AUTHORED_NOT_FROZEN_INPUTS")
    by_id = _check_chain_records(chain_records)
    proven: dict[str, dict[str, Any]] = {}
    decision_required: dict[str, dict[str, Any]] = {}
    unproven: dict[str, dict[str, Any]] = {}

    def attempt(name: str, rule: Any, needs_chain: bool = True) -> None:
        chain, privy = _Chain(authored, by_id), _Privy(privy_records, privy_capture_sha256, earlier)
        try:
            base = chain.preconditions() if needs_chain else None
            findings = rule(chain, privy, base)
        except _Unproven as missing:
            unproven[name] = {"reason": missing.reason}
            return
        decision = DECISION_REQUIRED.get(name) or _evidence_decision(name, findings)
        artifact = _artifact(name, authored, chain if needs_chain else None, privy, base, findings,
                             state="DECISION_REQUIRED" if decision else "ENFORCED", evidence_class="PROVIDER_ACTUAL",
                             claims=_CLAIMS[name], limits=_LIMITS[name], decision=decision)
        entry = {"artifact": artifact, "proof_sha256": _sha256(artifact)}
        if decision:
            decision_required[name] = {**entry, "reason": decision}
        else:
            proven[name] = entry

    attempt("input_output_assets", _input_output_assets)
    attempt("raw_input", _raw_input)
    attempt("recipient", _recipient)
    attempt("minimum_output", _minimum_output)
    attempt("fees", _fees)
    attempt("gas_action_capacity", lambda c, p, b: _gas_action_capacity(c, p, b, authored))
    attempt("expiry_freshness", lambda c, p, b: _expiry_freshness(p, authored), needs_chain=False)
    support = _opaque_support(authored, by_id)
    unproven["opaque_program"] = {"reason": "NO_PROVIDER_BOUND_ON_PROGRAM_BYTES",
                                  "supporting_evidence_sha256": None if support is None else _sha256(support)}
    return {
        "schema": "edge-os.inapp-control-proofs/1",
        "proven": {name: proven[name] for name in CONTROLS if name in proven},
        "controls": {name: {"state": "ENFORCED", "evidence_class": "PROVIDER_ACTUAL",
                            "proof_sha256": proven[name]["proof_sha256"]} for name in CONTROLS if name in proven},
        "decision_required": {name: decision_required[name] for name in CONTROLS if name in decision_required},
        "unproven": {name: unproven[name] for name in CONTROLS if name in unproven},
        "supporting": {} if support is None else {"opaque_program": {"artifact": support,
                                                                     "sha256": _sha256(support)}},
    }


def _opaque_support(authored: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    """Evidence of what the one approved program does, for a builder decision. It is not a control proof."""
    chain = _Chain(authored, by_id)
    try:
        base = chain.preconditions()
        record = chain.record("chain.swap_trace")
        if record.get("status") != "RESULT":
            return None
        findings = _trace_findings(record.get("result"), base["baseline_output"])
    except _Unproven:
        return None
    allowed = {address.lower() for address in (chain_proof.ENTRYPOINT, chain_proof.ROUTER, chain_proof.POOL,
                                                chain_proof.WMON, chain_proof.MOE)}
    if not set(findings["touched_addresses"]) <= allowed:
        return None
    return _artifact("opaque_program", authored, chain, None, base,
                     {"program_hex": chain_proof.PROGRAM_HEX, **findings}, state="UNPROVEN_SUPPORT",
                     evidence_class=None,
                     claims=("The approved program, simulated at the pinned block, calls only the entrypoint, "
                             "router, pool, WMON and MOE, and pays the whole output to the wallet.",),
                     limits=("Neither the Privy policy nor the entrypoint bounds the program bytes; only the "
                             "host's exact program check does. This is not a provider bound.",))


# ---------------------------------------------------------------- command


def load_privy_store(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """The outcome records and the SHA-256 of each saved capture file of the control-proof packet."""
    records, captures = {}, {}
    for specimen_id in CONTROL_PROOF_ORDER:
        outcome, capture = root / f"{specimen_id}.outcome.json", root / f"{specimen_id}.capture.json"
        if outcome.exists():
            records[specimen_id] = json.loads(outcome.read_text(encoding="utf-8"))
        if capture.exists():
            captures[specimen_id] = hashlib.sha256(capture.read_bytes()).hexdigest()
    return records, captures


def merge_expiry_rerun(records: dict[str, Any], captures: dict[str, str], rerun_root: Path
                       ) -> dict[str, Any]:
    """Replace the expiry row with its re-run from a separate store; return the earlier record it supersedes.

    The re-run store must hold the expiry row's outcome and capture and no other row's outcome.
    """
    rerun_records, rerun_captures = load_privy_store(rerun_root)
    expiry = [sid for sid in CONTROL_PROOF_ORDER if CONTROL_PROOF_PACKET.specimen_expected[sid] == "EXPIRY_REFUSAL"]
    if set(rerun_records) != set(expiry) or set(rerun_captures) != set(expiry) or not set(expiry) <= set(records):
        raise ProofRefused("RERUN_STORE_INVALID")
    earlier = {sid: records[sid] for sid in expiry}
    records.update(rerun_records)
    captures.update(rerun_captures)
    return earlier


def load_chain_store(root: Path) -> list[Any]:
    saved = json.loads((root / chain_proof.RESULTS_FILE).read_text(encoding="utf-8"))
    if not isinstance(saved, dict) or saved.get("schema") != chain_proof.RESULTS_SCHEMA:
        raise ProofRefused("CHAIN_RESULTS_SCHEMA_INVALID")
    return saved.get("operations")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.privy_unfunded_proof.control_proofs")
    parser.add_argument("--authored", type=Path, required=True)
    parser.add_argument("--privy-store", type=Path, required=True)
    parser.add_argument("--chain-store", type=Path, required=True)
    parser.add_argument("--privy-rerun-store", type=Path,
                        help="the store of the expiry row re-run alone (actual_run --rerun-expiry-from)")
    parser.add_argument("--out", type=Path, required=True, help="a new directory for the proof artifacts")
    args = parser.parse_args(argv)
    if args.out.exists():
        print(json.dumps({"status": "REFUSED", "code": "OUT_ALREADY_EXISTS"}))
        return 2
    try:
        records, captures = load_privy_store(args.privy_store)
        earlier = (merge_expiry_rerun(records, captures, args.privy_rerun_store)
                   if args.privy_rerun_store is not None else None)
        result = build_control_proofs(authored=json.loads(args.authored.read_text(encoding="utf-8")),
                                      privy_records=records, privy_capture_sha256=captures,
                                      chain_records=load_chain_store(args.chain_store),
                                      privy_earlier_records=earlier)
    except ProofRefused as refused:
        print(json.dumps({"status": "REFUSED", "code": refused.code}))
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "REFUSED", "code": "INPUT_UNREADABLE"}))
        return 2
    try:
        args.out.mkdir(parents=True)
    except FileExistsError:
        print(json.dumps({"status": "REFUSED", "code": "OUT_ALREADY_EXISTS"}))
        return 2
    for name, proof in {**result["proven"], **result["decision_required"]}.items():
        chain_proof.write_new(args.out / f"{name}.proof.json", canonical_json(proof["artifact"]))
    for name, support in result["supporting"].items():
        chain_proof.write_new(args.out / f"{name}.support.json", canonical_json(support["artifact"]))
    summary = {"status": "BUILT", "controls": result["controls"],
               "decision_required": {name: {"reason": entry["reason"], "proof_sha256": entry["proof_sha256"]}
                                     for name, entry in result["decision_required"].items()},
               "unproven": result["unproven"]}
    chain_proof.write_new(args.out / "controls.json", canonical_json(summary))
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
