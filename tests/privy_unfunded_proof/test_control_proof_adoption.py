"""The committed stores rebuild the seven proofs and the control 12 decision. Recorded files only; no network."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from scripts.privy_unfunded_proof import chain_proof, control_proofs
from scripts.privy_unfunded_proof.specimens import canonical_json

REPO = Path(__file__).resolve().parents[2]
AUTHORED = REPO / "docs/qualification/inapp-trade/release.authored.json"
PROOFS = REPO / "docs/qualification/inapp-trade/control-proofs"
PRIVY = PROOFS / "stores/privy-store-1"
CHAIN = PROOFS / "stores/chain-store-1"
DECISION = {"input_output_assets", "fees", "recipient", "expiry_freshness", "opaque_program"}
PROVEN = {"raw_input", "minimum_output", "gas_action_capacity"}
PROOFS_4 = {
    "expiry_freshness.proof.json": "c638035f9f5d42651b53da6d7082ea0e3ec6b1f70db5e76781ce347c1d92b5e7",
    "fees.proof.json": "6232e2a96d9623fa7a442dc36bdb8f467085805ee685adf9b8ada314bcbf1675",
    "gas_action_capacity.proof.json": "f5a5e82b8edd172c8beb798de26b2c117344ec6879b248be5504a36d0f3d7e29",
    "input_output_assets.proof.json": "b7c303f625ff3a094c79f81f004fb5a65bdb81599a5a495faafc919292164c33",
    "minimum_output.proof.json": "0dcee961871eb38e76079747cd5ffdf55956ed580ffc97e663d2ba8d7b5d94da",
    "raw_input.proof.json": "82c542a72664efd5d4a83bc674be8d6fc45e976538fe8b65bcf36945192cf40c",
    "recipient.proof.json": "4eaa956243fd0d92d767f73620e89b5685538b34bd4c7bab77259f0d17efc8bb",
}
UNEXPECTED = "0x" + "d" * 40


def _chain_records() -> list[dict]:
    return copy.deepcopy(control_proofs.load_chain_store(CHAIN))


def _build(chain_records: list | None = None) -> dict:
    records, captures = control_proofs.load_privy_store(PRIVY)
    earlier = control_proofs.merge_expiry_rerun(records, captures, PRIVY)
    expiry_captures = control_proofs.load_expiry_captures(PRIVY)
    return control_proofs.build_control_proofs(
        authored=json.loads(AUTHORED.read_text(encoding="utf-8")),
        privy_records=records, privy_capture_sha256=captures,
        chain_records=_chain_records() if chain_records is None else chain_records,
        privy_earlier_records=earlier, privy_expiry_captures=expiry_captures)


def _trace(records: list[dict]) -> dict:
    return next(record["result"] for record in records if record["op_id"] == "chain.swap_trace")


def _topic(address: str) -> str:
    return "0x" + address[2:].lower().rjust(64, "0")


def _extra_call(frame_type: str = "CALL", *, caller: str = chain_proof.ENTRYPOINT,
                target: str = UNEXPECTED, value: str = "0x0") -> dict:
    return {"type": frame_type, "from": caller, "to": target, "value": value, "input": "0x", "output": "0x",
            "gas": "0x1", "gasUsed": "0x1"}


def test_the_committed_stores_rebuild_the_seven_proofs_and_the_program_decision() -> None:
    result = _build()
    assert set(result["proven"]) == PROVEN
    assert set(result["decision_required"]) == DECISION
    assert result["unproven"] == {} and result["supporting"] == {}
    for name in PROVEN:
        saved = (PROOFS / "proofs-4" / f"{name}.proof.json").read_bytes()
        assert hashlib.sha256(saved).hexdigest() == PROOFS_4[f"{name}.proof.json"]
        assert canonical_json(result["proven"][name]["artifact"]) == saved
    for name in DECISION - {"opaque_program"}:
        saved = (PROOFS / "proofs-4" / f"{name}.proof.json").read_bytes()
        assert hashlib.sha256(saved).hexdigest() == PROOFS_4[f"{name}.proof.json"]
        assert canonical_json(result["decision_required"][name]["artifact"]) == saved
    opaque = result["decision_required"]["opaque_program"]["artifact"]
    assert canonical_json(opaque) == (PROOFS / "proofs-5" / "opaque_program.proof.json").read_bytes()
    assert result["decision_required"]["opaque_program"]["reason"] == "PROGRAM_BOUND_BY_HOST_AND_TRACE_ONLY"


def test_the_program_decision_lists_every_touched_address_and_labels() -> None:
    findings = _build()["decision_required"]["opaque_program"]["artifact"]["findings"]
    assert findings["host_program_check"]["match"] is True
    assert len(findings["touched_addresses"]) == 11
    labels = {entry["address"]: (entry["frame_types"], entry["label"]) for entry in findings["touched"]}
    assert labels[chain_proof.POOL.lower()][0] == ["CALL", "STATICCALL"]
    assert labels[chain_proof.POOL.lower()][1] == "called contract"
    for address in findings["delegate_targets"]:
        assert labels[address][0] == ["DELEGATECALL"]
        assert labels[address][1] == "proxy implementation, observed at this block, owner-upgradeable"
    assert labels["0x71f846a560a4d68f53e5bd34ed084e7992f171c7"] == (["STATICCALL"], "read-only")
    assert {entry["recipient"] for entry in findings["fee_transfers"]} == {
        "0x681c3f796ae388026634c26025504d7c45248998", "0xe1c8b73343f5a83ebe165be90470d84b00e33022"}
    assert chain_proof.ENTRYPOINT.lower() in findings["call_targets"]
    assert "0xe1c8b73343f5a83ebe165be90470d84b00e33022" in findings["call_targets"]


def test_an_unexpected_call_target_refuses_the_program_decision() -> None:
    records = _chain_records()
    _trace(records)["calls"].append(_extra_call())
    result = _build(records)
    assert result["unproven"]["opaque_program"]["reason"] == "UNEXPECTED_CALL_TARGET"


def test_a_delegatecall_from_the_program_frame_refuses() -> None:
    records = _chain_records()
    _trace(records)["calls"].append(_extra_call("DELEGATECALL", caller=chain_proof.WALLET,
                                                target=chain_proof.ENTRYPOINT))
    assert _build(records)["unproven"]["opaque_program"]["reason"] == "FRAME_CALLER_MISMATCH"


def test_a_create_frame_refuses() -> None:
    records = _chain_records()
    _trace(records)["calls"].append(_extra_call("CREATE"))
    assert _build(records)["unproven"]["opaque_program"]["reason"] == "UNEXPECTED_FRAME_TYPE"


def test_a_value_bearing_frame_refuses() -> None:
    records = _chain_records()
    _trace(records)["calls"].append(_extra_call(target=chain_proof.WMON, value="0x1"))
    assert "opaque_program" in _build(records)["unproven"]


def test_an_unpinned_transfer_recipient_refuses() -> None:
    records = _chain_records()
    trace = _trace(records)
    trace["logs"].append({"address": chain_proof.WMON, "topics": [
        control_proofs.TRANSFER_TOPIC, _topic(chain_proof.POOL), _topic(UNEXPECTED)],
        "data": "0x" + (1).to_bytes(32, "big").hex()})
    assert "opaque_program" in _build(records)["unproven"]


def test_a_value_in_a_nested_frame_refuses() -> None:
    records = _chain_records()
    trace = _trace(records)
    trace["calls"][0]["value"] = "0x1"
    assert "opaque_program" in _build(records)["unproven"]


def test_a_frame_without_a_valid_address_refuses() -> None:
    records = _chain_records()
    _trace(records)["calls"].append(_extra_call(target="0xnot-an-address"))
    assert "opaque_program" in _build(records)["unproven"]
