"""Pure proof builder for in-app trade controls 4-8 and 10-12. Recorded fakes only; no network."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from edge_os_api.execution import inapp_trade_release as inapp
from edge_os_api.execution import operating_release
from edge_os_api.execution.operating_release import check_release, release_sha256
from scripts.privy_unfunded_proof import chain_proof, control_proofs
from scripts.privy_unfunded_proof.actual_packet import CONTROL_PROOF_PACKET
from scripts.privy_unfunded_proof.specimens import canonical_json

from tests.privy_unfunded_proof._control_support import (
    BASE_FEE,
    LIVE_FEE_PAYOUTS,
    TRANSFER_TOPIC,
    authored,
    pool_output,
    privy_captures,
    privy_records,
    recorded_chain,
    replaced,
)

PROVEN = ("raw_input", "recipient", "minimum_output", "gas_action_capacity")
DECISION = ("input_output_assets", "fees", "expiry_freshness")


def _build(**changes):  # noqa: ANN003, ANN202
    arguments = {"authored": authored(), "privy_records": privy_records(), "privy_capture_sha256": privy_captures(),
                 "chain_records": recorded_chain()}
    arguments.update(changes)
    return control_proofs.build_control_proofs(**arguments)


# ---------------------------------------------------------------- full recorded run


def test_a_matching_recorded_run_proves_four_controls_leaves_three_to_the_builder_and_never_the_program() -> None:
    result = _build()
    assert set(result["proven"]) == set(PROVEN)
    assert set(result["unproven"]) == {"opaque_program"}
    assert result["unproven"]["opaque_program"]["reason"] == "NO_PROVIDER_BOUND_ON_PROGRAM_BYTES"
    support = result["supporting"]["opaque_program"]
    assert result["unproven"]["opaque_program"]["supporting_evidence_sha256"] == support["sha256"]
    assert support["sha256"] == hashlib.sha256(canonical_json(support["artifact"])).hexdigest()
    assert support["artifact"]["evidence_class"] is None and support["artifact"]["state"] == "UNPROVEN_SUPPORT"
    assert {name: entry["reason"] for name, entry in result["decision_required"].items()} == {
        "input_output_assets": "OUTPUT_TOKEN_NOT_PROVIDER_BOUND", "fees": "FEE_VALUES_NOT_PROVIDER_BOUND",
        "expiry_freshness": "PROVIDER_COVERS_SIGNING_CUTOFF_ONLY"}
    for name in DECISION:
        entry = result["decision_required"][name]
        assert entry["artifact"]["state"] == "DECISION_REQUIRED"
        assert entry["artifact"]["decision_required"] == entry["reason"]
        assert entry["proof_sha256"] == hashlib.sha256(canonical_json(entry["artifact"])).hexdigest()
        assert name not in result["controls"]
    for name in PROVEN:
        proof = result["proven"][name]
        assert proof["proof_sha256"] == hashlib.sha256(canonical_json(proof["artifact"])).hexdigest()
        assert result["controls"][name] == {"state": "ENFORCED", "evidence_class": "PROVIDER_ACTUAL",
                                            "proof_sha256": proof["proof_sha256"]}
        assert proof["artifact"]["control"] == name
        assert proof["artifact"]["schema"] == control_proofs.ARTIFACT_SCHEMA
        assert proof["artifact"]["limits"]
        assert proof["artifact"]["state"] == "ENFORCED" and proof["artifact"]["decision_required"] is None
    assert set(result["controls"]) == set(PROVEN)


def test_the_builder_is_deterministic_and_binds_every_record() -> None:
    first, second = _build(), _build()
    assert first == second
    chain = {record["op_id"]: record for record in recorded_chain()}
    evidence = first["proven"]["minimum_output"]["artifact"]["evidence"]
    assert {item["operation"] for item in evidence} >= {"chain.swap_min_equal", "chain.swap_min_above"}
    for item in evidence:
        if item["kind"] == "chain":
            assert item["record_sha256"] == hashlib.sha256(canonical_json(chain[item["operation"]])).hexdigest()


def test_each_artifact_cites_its_operations() -> None:
    result = _build()
    cited = {name: {item["operation"] for item in proof["artifact"]["evidence"]}
             for name, proof in {**result["proven"], **result["decision_required"]}.items()}
    assert {"chain.swap_wrong_output", "chain.swap_wrong_input",
            "raw.ctl_deny_approve_moe_entrypoint"} <= cited["input_output_assets"]
    assert {"chain.swap_probe", "chain.pool_reserves", "chain.swap_input_above_allowance"} <= cited["raw_input"]
    assert {"chain.swap_trace", "raw.ctl_deny_swap_receiver_wallet",
            "raw.ctl_deny_moe_transfer_sink"} <= cited["recipient"]
    assert {"chain.swap_fee_over_bound", "chain.swap_fee_sum_over_bound", "chain.swap_fee_sum_at_bound",
            "chain.swap_fee_charged"} <= cited["fees"]
    assert {"chain.estimate_approve", "chain.estimate_swap", "chain.estimate_revoke", "chain.block",
            "chain.swap_at_release_gas"} <= cited["gas_action_capacity"]
    assert cited["expiry_freshness"] >= {"raw.ctl_allow_revoke_zero", "raw.ctl_deny_expired_request"}


def test_findings_record_the_formula_and_the_pinned_block() -> None:
    artifact = _build()["proven"]["raw_input"]["artifact"]
    assert artifact["chain"] == {"chain_id": 143, "block_number": 0x6D00000, "block_hash": "0x" + "ab" * 32}
    assert artifact["findings"]["baseline_output_raw"] == str(pool_output(chain_proof.INPUT_RAW))
    assert artifact["findings"]["formula_output_raw"] == artifact["findings"]["baseline_output_raw"]
    gas = _build()["proven"]["gas_action_capacity"]["artifact"]["findings"]
    assert gas["estimates"] == {"approve": 46_000, "swap": 544_967, "revoke": 30_000}
    assert gas["base_fee_per_gas"] == BASE_FEE


# ---------------------------------------------------------------- check_release accepts the produced controls


def test_produced_controls_drop_in_to_the_release_shape() -> None:
    result = _build()
    value = authored()
    value["release"]["controls"].update(result["controls"])
    fill = {"quote_endpoint": "https://relay.example.test/rpc", "broadcast_endpoint": "https://b.example.test/rpc",
            "observer_endpoint": "https://o.example.test/rpc", "valid_until": "2026-11-01T00:00:00Z",
            "mandate_expires_at": "2026-11-01T00:00:00Z", "abi_sha256": "a" * 64,
            "mutable_router_proof_sha256": "b" * 64,
            "reserves": {"block_number": 1, "reserve_wmon": "1000000000000000000000000",
                         "reserve_moe": "75000000000000000000000000"},
            "gas_estimates": {"approve": 46000, "swap": 544967, "revoke": 30000}}
    release = inapp.complete_release(value, fill)
    # Controls 1-3 and 9 wait on the recorded v3 result, 4 and 11 on a builder decision, 12 stays unproven.
    assert inapp.unqualified_controls(release) == ["approvals", "chain", "entrypoint_method", "expiry_freshness",
                                                   "fees", "input_output_assets", "opaque_program",
                                                   "wallet_signer_binding"]
    digest = release_sha256(release)
    import datetime as dt
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(operating_release, "APPROVED_ACTUAL_RELEASES",
                      {release.content()["release_id"]: digest})
        with pytest.raises(operating_release.ReleaseRefused) as caught:
            check_release(release, expected_sha256=digest, now=dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc))
    assert str(caught.value) == "EXECUTION_CONTROL_UNQUALIFIED"


# ---------------------------------------------------------------- fail-closed per control


@pytest.mark.parametrize(("op_id", "control", "fields"), [
    ("chain.swap_wrong_output", "input_output_assets", {"status": "RESULT", "result": "0x" + "00" * 31 + "01", "error": None}),
    ("chain.swap_wrong_input", "input_output_assets", {"error": {"code": -32602, "reverted": False, "data": None,
                                                                  "message_sha256": None}}),
    ("chain.swap_input_above_allowance", "raw_input", {"status": "RESULT", "result": "0x" + "00" * 31 + "01",
                                                       "error": None}),
    ("chain.swap_min_above", "minimum_output", {"status": "RESULT", "result": "0x" + "00" * 31 + "01", "error": None}),
    ("chain.swap_min_equal", "minimum_output", {"status": "RPC_ERROR", "result": None,
                                                "error": {"code": 3, "reverted": True, "data": None,
                                                          "message_sha256": None}}),
    ("chain.swap_fee_over_bound", "fees", {"status": "RESULT", "result": "0x" + "00" * 31 + "01", "error": None}),
    ("chain.swap_fee_sum_over_bound", "fees", {"status": "RESULT", "result": "0x" + "00" * 31 + "01",
                                               "error": None}),
    ("chain.swap_fee_sum_at_bound", "fees", {"status": "RPC_ERROR", "result": None,
                                             "error": {"code": 3, "reverted": True, "data": None,
                                                       "message_sha256": None}}),
    ("chain.estimate_swap", "gas_action_capacity", {"result": hex(600_000)}),
    ("chain.swap_at_release_gas", "gas_action_capacity", {"status": "RPC_ERROR", "result": None,
                                                          "error": {"code": 3, "reverted": True, "data": None,
                                                                    "message_sha256": None}}),
    ("chain.block", "gas_action_capacity", {"result": {"number": hex(0x6D00000), "hash": "0x" + "ab" * 32,
                                                       "baseFeePerGas": hex(101_000_000_000)}}),
])
def test_a_contrary_chain_result_leaves_its_control_unproven(op_id: str, control: str, fields: dict) -> None:
    result = _build(chain_records=replaced(recorded_chain(), op_id, **fields))
    assert control not in result["proven"] and control not in result["controls"]
    assert control not in result["decision_required"]
    assert result["unproven"][control]["reason"]


def test_a_fee_that_takes_nothing_is_not_proof_that_fee_fields_are_honoured() -> None:
    probe = next(r for r in recorded_chain() if r["op_id"] == "chain.swap_probe")
    result = _build(chain_records=replaced(recorded_chain(), "chain.swap_fee_charged", result=probe["result"]))
    assert "fees" not in result["decision_required"]
    assert result["unproven"]["fees"]["reason"] == "CHAIN_RESULT_CONTRARY"


def test_an_output_that_differs_from_the_formula_proves_neither_input_nor_fees() -> None:
    records = recorded_chain()
    reserves = next(r for r in records if r["op_id"] == "chain.pool_reserves")["result"]
    other = "0x" + f"{int(reserves[2:66], 16) * 2:064x}" + reserves[66:]
    result = _build(chain_records=replaced(records, "chain.pool_reserves", result=other))
    assert result["unproven"]["raw_input"]["reason"] == "CHAIN_RESULT_CONTRARY"
    assert result["unproven"]["fees"]["reason"] == "CHAIN_RESULT_CONTRARY"
    assert "minimum_output" in result["proven"]


def test_a_changed_baseline_output_breaks_every_dependent_request() -> None:
    records = recorded_chain()
    changed = "0x" + f"{pool_output(chain_proof.INPUT_RAW) - 1:064x}"
    with pytest.raises(control_proofs.ProofRefused) as caught:
        _build(chain_records=replaced(records, "chain.swap_probe", result=changed))
    assert caught.value.code == "CHAIN_RECORD_MISMATCH"


def test_a_missing_trace_leaves_only_the_recipient_unproven() -> None:
    result = _build(chain_records=recorded_chain(debug_supported=False))
    assert "recipient" not in result["proven"]
    assert result["unproven"]["recipient"]["reason"] == "TRACE_UNAVAILABLE"
    assert set(result["proven"]) == set(PROVEN) - {"recipient"}
    assert result["unproven"]["opaque_program"]["supporting_evidence_sha256"] is None
    assert result["supporting"] == {}


def test_a_trace_without_logs_leaves_the_recipient_unproven() -> None:
    result = _build(chain_records=recorded_chain(trace_logs=False))
    assert result["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"


def test_a_trace_that_moves_native_value_leaves_the_recipient_unproven() -> None:
    records = recorded_chain()
    trace = next(r for r in records if r["op_id"] == "chain.swap_trace")["result"]
    changed = copy.deepcopy(trace)
    changed["calls"][1]["calls"][0]["value"] = "0x1"
    result = _build(chain_records=replaced(records, "chain.swap_trace", result=changed))
    assert result["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"


def test_a_trace_that_pays_another_address_leaves_the_recipient_unproven() -> None:
    records = recorded_chain()
    trace = next(r for r in records if r["op_id"] == "chain.swap_trace")["result"]
    changed = copy.deepcopy(trace)
    changed["logs"][0]["topics"][2] = "0x" + "00" * 12 + "000000000000000000000000000000000000dead"
    result = _build(chain_records=replaced(records, "chain.swap_trace", result=changed))
    assert result["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"


# ---------------------------------------------------------------- recipient: the live trace's fee payouts

FEE_1, FEE_2 = LIVE_FEE_PAYOUTS


def _fee_trace(**payouts: int):  # noqa: ANN003, ANN202
    """Chain records whose trace pays the pool's WMON fee payouts (default: the live trace's)."""
    return recorded_chain(pool_fee_payouts=payouts or dict(LIVE_FEE_PAYOUTS))


def _with_pool_log(records, token: str, receiver: str, amount: int):  # noqa: ANN001, ANN202
    """Add one Transfer from the pool to the trace's pool frame."""
    trace = copy.deepcopy(next(r for r in records if r["op_id"] == "chain.swap_trace")["result"])
    word = lambda address: "0x" + address[2:].lower().rjust(64, "0")  # noqa: E731
    trace["calls"][1]["calls"][0]["logs"].insert(0, {
        "address": token, "topics": [TRANSFER_TOPIC, word(chain_proof.POOL), word(receiver)],
        "data": "0x" + amount.to_bytes(32, "big").hex()})
    return replaced(records, "chain.swap_trace", result=trace)


def test_the_pinned_fee_bounds_are_the_live_trace_shares_of_the_input() -> None:
    assert dict(chain_proof.OBSERVED_FEE_RECIPIENTS_PPM) == {FEE_1: 10_000, FEE_2: 3_500}
    assert {address: control_proofs.fee_bound_raw(address) for address in LIVE_FEE_PAYOUTS} == LIVE_FEE_PAYOUTS
    assert chain_proof.INPUT_RAW - sum(LIVE_FEE_PAYOUTS.values()) == 9_865_000_000_000_000_000


def test_the_live_trace_shape_makes_the_recipient_a_builder_decision_with_every_payout_listed() -> None:
    result = _build(chain_records=_fee_trace())
    assert "recipient" not in result["proven"] and "recipient" not in result["controls"]
    assert "recipient" not in result["unproven"]
    entry = result["decision_required"]["recipient"]
    assert entry["reason"] == "FEE_RECIPIENTS_OBSERVED_NOT_SOURCE_BOUND"
    artifact = entry["artifact"]
    assert artifact["state"] == "DECISION_REQUIRED" and artifact["decision_required"] == entry["reason"]
    assert entry["proof_sha256"] == hashlib.sha256(canonical_json(artifact)).hexdigest()
    findings = artifact["findings"]
    assert findings["fee_transfers"] == [
        {"token": chain_proof.WMON, "recipient": FEE_2, "amount_raw": "35000000000000000",
         "bound_ppm_of_input": 3500, "bound_raw": "35000000000000000"},
        {"token": chain_proof.WMON, "recipient": FEE_1, "amount_raw": "100000000000000000",
         "bound_ppm_of_input": 10000, "bound_raw": "100000000000000000"}]
    assert findings["wmon_received_by_pool_raw"] == "9865000000000000000"
    assert findings["wmon_paid_by_wallet_raw"] == str(chain_proof.INPUT_RAW)
    assert findings["moe_received_by_wallet_raw"] == str(pool_output(chain_proof.INPUT_RAW))
    assert set(result["proven"]) == set(PROVEN) - {"recipient"}


def test_a_trace_without_fee_payouts_keeps_the_recipient_enforced() -> None:
    result = _build()
    findings = result["proven"]["recipient"]["artifact"]["findings"]
    assert findings["fee_transfers"] == []
    assert findings["wmon_received_by_pool_raw"] == str(chain_proof.INPUT_RAW)


def test_a_payout_below_its_bound_is_listed_and_one_unit_above_is_refused() -> None:
    below = _build(chain_records=_fee_trace(**{FEE_1: 1, FEE_2: LIVE_FEE_PAYOUTS[FEE_2]}))
    assert below["decision_required"]["recipient"]["artifact"]["findings"]["fee_transfers"][1]["amount_raw"] == "1"
    for address in LIVE_FEE_PAYOUTS:
        over = dict(LIVE_FEE_PAYOUTS, **{address: LIVE_FEE_PAYOUTS[address] + 1})
        result = _build(chain_records=_fee_trace(**over))
        assert result["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"
        assert "recipient" not in result["decision_required"]


def test_a_payout_split_into_two_logs_is_bounded_by_its_net_sum() -> None:
    records = _with_pool_log(_fee_trace(), chain_proof.WMON, FEE_2, 1)
    assert _build(chain_records=records)["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"


@pytest.mark.parametrize("receiver", ["0x000000000000000000000000000000000000dead", chain_proof.ROUTER,
                                      chain_proof.ENTRYPOINT, "0x" + "00" * 20])
def test_any_wmon_gain_to_an_unpinned_address_is_refused(receiver: str) -> None:
    for records in (recorded_chain(), _fee_trace()):
        changed = _with_pool_log(records, chain_proof.WMON, receiver, 1)
        result = _build(chain_records=changed)
        assert result["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"
        assert "recipient" not in result["decision_required"] and "recipient" not in result["proven"]


def test_a_fee_paid_to_an_unpinned_address_in_place_of_a_pinned_one_is_refused() -> None:
    swapped = {"0x000000000000000000000000000000000000dead" if address == FEE_1 else address: value
               for address, value in LIVE_FEE_PAYOUTS.items()}
    result = _build(chain_records=_fee_trace(**swapped))
    assert result["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"


@pytest.mark.parametrize("receiver", [FEE_1, FEE_2, chain_proof.ROUTER,
                                      "0x000000000000000000000000000000000000dead"])
def test_any_moe_that_does_not_go_to_the_wallet_is_refused(receiver: str) -> None:
    records = _fee_trace()
    trace = copy.deepcopy(next(r for r in records if r["op_id"] == "chain.swap_trace")["result"])
    word = lambda address: "0x" + address[2:].lower().rjust(64, "0")  # noqa: E731
    trace["logs"].append({"address": chain_proof.MOE,
                          "topics": [TRANSFER_TOPIC, word(chain_proof.ENTRYPOINT), word(receiver)],
                          "data": "0x" + (1).to_bytes(32, "big").hex()})
    trace["calls"][1]["logs"][1]["data"] = "0x" + (pool_output(chain_proof.INPUT_RAW) + 1).to_bytes(32, "big").hex()
    trace["calls"][1]["calls"][0]["logs"][-1]["data"] = trace["calls"][1]["logs"][1]["data"]
    result = _build(chain_records=replaced(records, "chain.swap_trace", result=trace))
    assert result["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"


def test_a_pinned_fee_recipient_that_gains_moe_is_refused() -> None:
    records = _with_pool_log(_fee_trace(), chain_proof.MOE, FEE_1, 1)
    assert _build(chain_records=records)["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"


def test_the_wallet_must_pay_exactly_the_input_even_with_fee_payouts() -> None:
    records = _fee_trace()
    trace = copy.deepcopy(next(r for r in records if r["op_id"] == "chain.swap_trace")["result"])
    trace["calls"][0]["logs"][0]["data"] = "0x" + (chain_proof.INPUT_RAW + 1).to_bytes(32, "big").hex()
    result = _build(chain_records=replaced(records, "chain.swap_trace", result=trace))
    assert result["unproven"]["recipient"]["reason"] == "TRACE_TRANSFERS_INVALID"


def test_overrides_that_did_not_take_effect_prove_no_contract_control() -> None:
    result = _build(chain_records=recorded_chain(state_overrides_honoured=False))
    for name in ("input_output_assets", "raw_input", "recipient", "minimum_output", "fees", "gas_action_capacity"):
        assert name not in result["proven"]
        assert result["unproven"][name]["reason"] == "CHAIN_PRECONDITION_FAILED"
    assert "expiry_freshness" in result["decision_required"]


@pytest.mark.parametrize("op_id", ["chain.code_entrypoint", "chain.code_router", "chain.get_router",
                                   "chain.pool_token0", "chain.chain_id"])
def test_a_changed_deployment_proves_no_contract_control(op_id: str) -> None:
    value = {"chain.code_entrypoint": "0x6000", "chain.code_router": "0x6000",
             "chain.get_router": "0x" + "00" * 12 + "11" * 20, "chain.pool_token0": "0x" + "00" * 12 + "22" * 20,
             "chain.chain_id": "0x279f"}[op_id]
    result = _build(chain_records=replaced(recorded_chain(), op_id, result=value))
    for name in ("input_output_assets", "raw_input", "recipient", "minimum_output", "fees", "gas_action_capacity"):
        assert result["unproven"][name]["reason"] == "CHAIN_PRECONDITION_FAILED"


def test_records_whose_requests_differ_from_the_frozen_operations_are_refused() -> None:
    records = recorded_chain()
    tampered = replaced(records, "chain.swap_min_above",
                        params=[{"from": chain_proof.WALLET, "to": chain_proof.ENTRYPOINT, "value": "0x0",
                                 "data": chain_proof.swap_calldata(min_output_raw=10**30)},
                                hex(0x6D00000), chain_proof.STATE_OVERRIDES])
    with pytest.raises(control_proofs.ProofRefused) as caught:
        _build(chain_records=tampered)
    assert caught.value.code == "CHAIN_RECORD_MISMATCH"


def test_missing_or_reordered_chain_records_are_refused() -> None:
    records = recorded_chain()
    for broken in (records[:-1], list(reversed(records)), records + [records[0]]):
        with pytest.raises(control_proofs.ProofRefused) as caught:
            _build(chain_records=broken)
        assert caught.value.code == "CHAIN_RECORDS_INCOMPLETE"


def test_an_authored_release_with_other_values_is_refused() -> None:
    value = authored()
    value["release"]["route"]["output_asset"]["token_address"] = chain_proof.WMON
    with pytest.raises(control_proofs.ProofRefused) as caught:
        _build(authored=value)
    assert caught.value.code == "AUTHORED_NOT_FROZEN_INPUTS"


@pytest.mark.parametrize(("specimen_id", "control", "change"), [
    ("raw.ctl_deny_approve_moe_entrypoint", "input_output_assets", {"outcome": "ALLOW", "matches_expectation": False}),
    ("raw.ctl_deny_swap_receiver_wallet", "recipient", {"outcome": "UNKNOWN", "reason": "SEND_LOST",
                                                        "matches_expectation": False}),
    ("raw.ctl_deny_moe_transfer_sink", "recipient", {"request_sha256": "0" * 64}),
    ("raw.ctl_deny_expired_request", "expiry_freshness", {"outcome": "BREACH", "matches_expectation": False}),
    ("raw.ctl_deny_expired_request", "expiry_freshness", {"packet_id": "8255d003097fd1a0216a6b64c48637f2ef745c7ebbe73035d0b8929403500528"}),
    ("raw.ctl_deny_moe_transfer_sink", "recipient", {"evidence_class": "PROVIDER_ACTUAL"}),
    ("raw.ctl_deny_moe_transfer_sink", "recipient", {"provider_proof": "QUALIFIED"}),
    ("raw.ctl_allow_revoke_zero", "expiry_freshness", {"signed_bytes_sha256": None}),
])
def test_a_privy_record_that_does_not_match_leaves_its_control_unproven(specimen_id: str, control: str,
                                                                       change: dict) -> None:
    result = _build(privy_records=privy_records(**{specimen_id: change}))
    assert control not in result["proven"] and control not in result["decision_required"]
    assert result["unproven"][control]["reason"] == "PRIVY_RECORD_INVALID"


def test_an_outcome_record_without_its_saved_capture_does_not_count() -> None:
    captures = privy_captures()
    captures["raw.ctl_deny_moe_transfer_sink"] = "0" * 64
    result = _build(privy_capture_sha256=captures)
    assert result["unproven"]["recipient"]["reason"] == "PRIVY_RECORD_INVALID"
    del captures["raw.ctl_deny_moe_transfer_sink"]
    assert _build(privy_capture_sha256=captures)["unproven"]["recipient"]["reason"] == "PRIVY_RECORD_INVALID"


def test_without_the_positive_control_no_privy_refusal_counts() -> None:
    records = privy_records()
    del records["raw.ctl_allow_revoke_zero"]
    result = _build(privy_records=records)
    for name in ("input_output_assets", "recipient", "expiry_freshness"):
        assert result["unproven"][name]["reason"] == "PRIVY_RECORD_INVALID"
    assert {"raw_input", "minimum_output", "gas_action_capacity"} <= set(result["proven"])
    assert "fees" in result["decision_required"]


def test_a_changed_gas_limit_in_the_authored_release_is_judged_against_the_estimate() -> None:
    value = authored()
    value["facts"]["gas_limits"]["approve"] = 50_000  # below ceil(46000 * 1.2) = 55200
    result = _build(authored=value)
    assert result["unproven"]["gas_action_capacity"]["reason"] == "GAS_LIMIT_BELOW_ESTIMATE_MARGIN"


# ---------------------------------------------------------------- command


def test_command_reads_a_privy_store_and_a_chain_results_file(tmp_path: Path,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    privy_dir = tmp_path / "privy"
    privy_dir.mkdir()
    for specimen_id, record in privy_records().items():
        (privy_dir / f"{specimen_id}.outcome.json").write_text(json.dumps(record), encoding="utf-8")
        (privy_dir / f"{specimen_id}.capture.json").write_bytes(specimen_id.encode())
    chain_dir = tmp_path / "chain"
    chain_dir.mkdir()
    (chain_dir / chain_proof.RESULTS_FILE).write_text(
        json.dumps({"schema": chain_proof.RESULTS_SCHEMA, "operations": recorded_chain()}), encoding="utf-8")
    authored_path = tmp_path / "authored.json"
    authored_path.write_text(json.dumps(authored()), encoding="utf-8")
    out_dir = tmp_path / "proofs"
    code = control_proofs.main(["--authored", str(authored_path), "--privy-store", str(privy_dir),
                                "--chain-store", str(chain_dir), "--out", str(out_dir)])
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed["controls"]) == set(PROVEN)
    for name in PROVEN:
        saved = (out_dir / f"{name}.proof.json").read_bytes()
        assert hashlib.sha256(saved).hexdigest() == printed["controls"][name]["proof_sha256"]
    for name in DECISION:
        saved = (out_dir / f"{name}.proof.json").read_bytes()
        assert hashlib.sha256(saved).hexdigest() == printed["decision_required"][name]["proof_sha256"]
    support = (out_dir / "opaque_program.support.json").read_bytes()
    assert hashlib.sha256(support).hexdigest() == printed["unproven"]["opaque_program"]["supporting_evidence_sha256"]
    assert printed["unproven"]["opaque_program"]["reason"] == "NO_PROVIDER_BOUND_ON_PROGRAM_BYTES"
    assert control_proofs.main(["--authored", str(authored_path), "--privy-store", str(privy_dir),
                                "--chain-store", str(chain_dir), "--out", str(out_dir)]) == 2


def test_the_builder_module_makes_no_network_or_process_call() -> None:
    import ast

    tree = ast.parse(Path(control_proofs.__file__).read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in getattr(node, "names", [])}
    modules = {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not ({"socket", "http", "urllib", "subprocess", "requests", "httpx"} & (imported | modules))
    assert CONTROL_PROOF_PACKET.packet_id in json.dumps(_build()["proven"]["recipient"]["artifact"])
