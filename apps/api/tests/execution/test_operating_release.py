"""Test-owned synthetic authority never approves an actual operating release."""

import copy
import datetime as dt
import socket
import pytest
from edge_os_api.execution import operating_release
from edge_os_api.execution.operating_release import OperatingRelease, check_release, release_sha256
from edge_os_api.execution.operating_release import CONTROLS, ReleaseRefused, release_steps




NOW = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)


def definition():
    address = "0x" + "1" * 40
    return {
        "release_id": "synthetic-release-a", "kind": "SYNTHETIC_FIXTURE", "evidence_class": "SYNTHETIC_FIXTURE",
        "purpose": "CONTROLLED_ONE_ACTION_QUALIFICATION", "chain_id": 143,
        "wallet_id": "synthetic-wallet-a", "wallet_address": address, "signer_id": "synthetic-signer-a",
        "policy_id": "synthetic-policy-a", "policy_owner_id": "synthetic-owner-a",
        "policy_content_sha256": "a" * 64, "independent_proof_sha256": "b" * 64,
        "deployment": {"source_commit": "c" * 40, "entrypoint_code_sha256": "d" * 64,
            "router_address": "0x" + "4" * 40, "router_code_sha256": "e" * 64, "abi_sha256": "f" * 64,
            "mutable_router_proof_sha256": "1" * 64},
        "route": {"network_id": "monad:143", "entrypoint_address": "0x" + "5" * 40,
            "method": "EXECUTE_SWAP", "selector": "0x12345678",
            "input_asset": {"asset_id": "monad:143/0x" + "2" * 40, "token_address": "0x" + "2" * 40, "decimals": 6},
            "output_asset": {"asset_id": "monad:143/0x" + "3" * 40, "token_address": "0x" + "3" * 40, "decimals": 18},
            "recipient": address, "approved_input_raw": "200", "approved_min_output_raw": "290",
            "approved_program_hex": "0xdeadbeef", "fees": {"fee_bps": 0, "referrer_fee_bps": 0,
                "fee_collector_address": address, "referrer_address": address, "is_in_token_fee": False},
            "approved_allowance_raw": "200", "freshness": {"max_quote_age_seconds": 30, "max_input_age_seconds": 60,
                "intent_expires_at": "2026-10-18T00:01:00Z", "mandate_expires_at": "2026-10-18T00:02:00Z"},
            "supported_schema_variants": ["TRANSACTION_CALLDATA"]},
        "quote": {"endpoint": "https://quote.invalid/api/quote", "credential_slot": "synthetic-quote-token", "slippage_bps": 50},
        "broadcast": {"role": "broadcast", "destination_id": "broadcast-a", "endpoint": "https://broadcast.invalid/rpc", "credential_slot": "synthetic-broadcast"},
        "observer": {"role": "observer", "destination_id": "observer-a", "endpoint": "https://observer.invalid/rpc", "credential_slot": "synthetic-observer"},
        "transaction": {"type": 2, "value_raw": "0", "signer_method": "eth_signTransaction", "request_expires_at": "2026-10-18T00:01:00Z"},
        "gas": {"gas_limit": 200000, "max_fee_per_gas": 10, "max_priority_fee_per_gas": 2, "budget_raw": "2000000"},
        "limits": {"actions": 1, "attempts": 1, "broadcasts": 1, "quote_requests": 1, "signer_requests": 1,
            "observer_requests": 20, "max_request_bytes": 4096, "max_response_bytes": 16384, "deadline_seconds": 30},
        "valid_until": "2026-10-18T00:01:00Z", "finality": "finalized",
        "controls": {name: {"state": "ENFORCED", "evidence_class": "SYNTHETIC_FIXTURE", "proof_sha256": "b" * 64}
            for name in ("chain", "wallet_signer_binding", "entrypoint_method", "input_output_assets", "raw_input", "recipient",
                         "minimum_output", "fees", "approvals", "gas_action_capacity", "expiry_freshness", "opaque_program")},
    }


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


def test_release_owns_nested_meaning_and_hash_and_refuses_actual_approval():
    source = definition()
    release = OperatingRelease(source)
    before = release_sha256(release)
    source["route"]["approved_input_raw"] = "999"
    view = release.content()
    view["controls"]["opaque_program"]["state"] = "UNKNOWN"
    assert release.content()["route"]["approved_input_raw"] == "200"
    assert release.content()["controls"]["opaque_program"]["state"] == "ENFORCED"
    assert release_sha256(release) == before
    assert check_release(release, expected_sha256=before, now=NOW,
                         synthetic_approvals={"synthetic-release-a": before}) == before



@pytest.mark.parametrize("change", [
    lambda d: d.update(chain_id=True), lambda d: d.update(chain_id=10143), lambda d: d.update(wallet_id=""),
    lambda d: d.update(wallet_address="0x" + "9" * 40), lambda d: d.update(policy_owner_id=d["signer_id"]),
    lambda d: d.pop("independent_proof_sha256"), lambda d: d.update(policy_content_sha256="UNKNOWN"),
    lambda d: d["broadcast"].update(role="observer"), lambda d: d["observer"].update(endpoint=d["broadcast"]["endpoint"]),
    lambda d: d["observer"].update(destination_id=d["broadcast"]["destination_id"]),
    lambda d: d["route"].update(supported_schema_variants=["BUILD_RESPONSE"]),
    lambda d: d["route"]["input_asset"].update(decimals=True), lambda d: d["route"]["fees"].update(fee_bps=1.0),
    lambda d: d["limits"].update(broadcasts=2), lambda d: d["limits"].update(actions=True),
    lambda d: d["limits"].update(deadline_seconds=1.5), lambda d: d["gas"].update(gas_limit=None),
    lambda d: d["gas"].update(budget_raw="1999999"), lambda d: d.update(autonomous_exit_qualified=True),
    lambda d: d["controls"].pop("opaque_program"), lambda d: d.update(finality="latest"),
])
def test_malformed_or_drifting_authority_refused_without_io(change):
    source = definition()
    change(source)
    with pytest.raises(ReleaseRefused) as error:
        OperatingRelease(source)
    assert error.value.__context__ is None and error.value.__cause__ is None


@pytest.mark.parametrize("control", sorted(CONTROLS))
def test_each_unresolved_control_preserved_and_blocks_admission(control):
    source = definition()
    source["controls"][control] = {"state": "UNKNOWN", "evidence_class": "NOT_RUN", "proof_sha256": None}
    release = OperatingRelease(source)
    digest = release_sha256(release)
    assert release.content()["controls"][control]["state"] == "UNKNOWN"
    with pytest.raises(ReleaseRefused, match="CONTROL_UNQUALIFIED"):
        check_release(release, expected_sha256=digest, now=NOW, synthetic_approvals={source["release_id"]: digest})


def test_expiry_hash_and_approval_each_fail_closed():
    release = OperatingRelease(definition())
    digest = release_sha256(release)
    for options in (
        {"expected_sha256": "0" * 64, "now": NOW, "synthetic_approvals": {"synthetic-release-a": digest}},
        {"expected_sha256": digest, "now": NOW, "synthetic_approvals": {}},
        {"expected_sha256": digest, "now": NOW + dt.timedelta(minutes=1), "synthetic_approvals": {"synthetic-release-a": digest}},
        {"expected_sha256": digest, "now": NOW.replace(tzinfo=None), "synthetic_approvals": {"synthetic-release-a": digest}},
    ):
        with pytest.raises(ReleaseRefused):
            check_release(release, **options)


def test_caller_hash_or_test_approval_cannot_approve_actual_release(monkeypatch):
    source = definition()
    source.update(kind="ACTUAL", evidence_class="PROVIDER_ACTUAL")
    source["quote"]["endpoint"] = "https://ws.kuru.io/api/quote"
    source["broadcast"]["endpoint"] = "https://broadcast.example/rpc"
    source["observer"]["endpoint"] = "https://observer.example/rpc"
    for control in source["controls"].values():
        control["evidence_class"] = "PROVIDER_ACTUAL"
    release = OperatingRelease(source)
    digest = release_sha256(release)
    monkeypatch.setenv("APPROVED_ACTUAL_RELEASE", digest)
    for approvals in (None, {source["release_id"]: digest}):
        with pytest.raises(ReleaseRefused, match="ACTUAL_EXECUTION_RELEASE_NOT_APPROVED"):
            check_release(release, expected_sha256=digest, now=NOW, synthetic_approvals=approvals)


def test_hash_covers_nested_route_limits_policy_and_control_proof():
    original = definition()
    digest = release_sha256(OperatingRelease(original))
    for change in (lambda d: d["route"].update(approved_program_hex="0xfeedface"),
                   lambda d: d["limits"].update(observer_requests=21),
                   lambda d: d.update(policy_content_sha256="9" * 64),
                   lambda d: d["controls"]["opaque_program"].update(proof_sha256="8" * 64)):
        changed = copy.deepcopy(original)
        change(changed)
        assert release_sha256(OperatingRelease(changed)) != digest


@pytest.mark.parametrize("seconds,admitted", [(-1, False), (0, False), (1, True)])
def test_signer_request_expiry_is_enforced_before_release_expiry(seconds, admitted):
    source = definition()
    source["transaction"]["request_expires_at"] = (NOW + dt.timedelta(seconds=seconds)).isoformat()
    release = OperatingRelease(source)
    digest = release_sha256(release)
    options = {"expected_sha256": digest, "now": NOW, "synthetic_approvals": {source["release_id"]: digest}}
    if admitted:
        assert check_release(release, **options) == digest
    else:
        with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_EXPIRED"):
            check_release(release, **options)


def test_saved_identity_binding_cannot_retarget_an_approved_release():
    from edge_os_api.execution.operating_release import BoundRelease
    identity = {"owner_id": "owner-a", "agent_id": "agent-a", "wallet_id": "synthetic-wallet-a",
        "wallet_address": "0x" + "1" * 40, "network_id": "monad:143", "strategy_id": "strategy-a",
        "publication_revision_id": "revision-a", "execution_revision_id": "execution-a",
        "market_binding_id": "market-a", "content_sha256": "1" * 64, "manifest_sha256": "2" * 64,
        "consent_adoption_id": "consent-a", "consent_hash": "sha256:" + "3" * 64,
        "review_hash": "sha256:" + "4" * 64, "terms_hash": "sha256:" + "5" * 64}
    release = OperatingRelease(definition())
    bound = BoundRelease(release, identity, position_inventory_proof_sha256="6" * 64,
                         market_proof_sha256="7" * 64, finality_proof_sha256="8" * 64)
    approvals = {bound.sha256: release_sha256(release)}
    assert bound.admit(identity, now=NOW, synthetic_bindings=approvals) == bound.sha256
    for field in identity:
        with pytest.raises(ReleaseRefused, match="BINDING_MISMATCH"):
            bound.admit({**identity, field: "foreign"}, now=NOW, synthetic_bindings=approvals)
    identity["owner_id"] = "foreign"
    assert bound.identity()["owner_id"] == "owner-a"
    with pytest.raises(ReleaseRefused):
        bound.admit(bound.identity(), now=NOW, synthetic_bindings={})


def test_bound_release_requires_independent_inventory_market_and_finality_proofs():
    from edge_os_api.execution.operating_release import BoundRelease
    with pytest.raises(ReleaseRefused):
        BoundRelease(OperatingRelease(definition()), {}, position_inventory_proof_sha256=None,
                     market_proof_sha256="7" * 64, finality_proof_sha256="8" * 64)


# ------------------------------------------------------------------------------------------- step limits (CLOUD-A6B)

# The canonical hash of `definition()` before step limits existed (base c0d59cae). A single-action release keeps it.
SINGLE_ACTION_SHA256 = "7fee779da86b253cb67370b1f13d77c27e1f9abc6025cd809cacd74de0063b30"
STEPS = ["approve", "swap", "revoke"]


def step_definition():
    """A release that names its three steps, each with its own single signer request and broadcast."""
    source = definition()
    limits = source["limits"]
    del limits["signer_requests"], limits["broadcasts"]
    limits["steps"] = [{"step": name, "signer_requests": 1, "broadcasts": 1} for name in STEPS]
    return source


def test_a_single_action_release_is_admitted_byte_identically():
    release = OperatingRelease(definition())
    assert release_sha256(release) == SINGLE_ACTION_SHA256
    assert release.content()["limits"] == definition()["limits"]
    assert release_steps(release) is None
    assert check_release(release, expected_sha256=SINGLE_ACTION_SHA256, now=NOW,
                         synthetic_approvals={"synthetic-release-a": SINGLE_ACTION_SHA256}) == SINGLE_ACTION_SHA256


def test_a_release_naming_approve_swap_revoke_with_per_step_limits_is_admitted():
    release = OperatingRelease(step_definition())
    digest = release_sha256(release)
    assert digest != SINGLE_ACTION_SHA256
    assert release_steps(release) == ("approve", "swap", "revoke")
    assert release.content()["limits"]["steps"] == [
        {"step": "approve", "signer_requests": 1, "broadcasts": 1},
        {"step": "swap", "signer_requests": 1, "broadcasts": 1},
        {"step": "revoke", "signer_requests": 1, "broadcasts": 1}]
    assert check_release(release, expected_sha256=digest, now=NOW,
                         synthetic_approvals={"synthetic-release-a": digest}) == digest


def _step(index: int, **changes):
    def change(d):
        d["limits"]["steps"][index].update(changes)
    return change


@pytest.mark.parametrize("change", [
    lambda d: d["limits"].update(steps=[]),
    lambda d: d["limits"].update(steps=d["limits"]["steps"][::-1]),
    lambda d: d["limits"].update(steps=d["limits"]["steps"][:2]),
    lambda d: d["limits"].update(steps=d["limits"]["steps"][1:]),
    lambda d: d["limits"].update(steps=[d["limits"]["steps"][1]]),
    lambda d: d["limits"]["steps"].append({"step": "revoke", "signer_requests": 1, "broadcasts": 1}),
    lambda d: d["limits"]["steps"].insert(0, {"step": "wrap", "signer_requests": 1, "broadcasts": 1}),
    lambda d: d["limits"]["steps"].__setitem__(1, {"step": "approve", "signer_requests": 1, "broadcasts": 1}),
    lambda d: d["limits"].update(steps={"approve": 1, "swap": 1, "revoke": 1}),
    lambda d: d["limits"].update(steps=STEPS),
    lambda d: d["limits"].update(steps=None),
    _step(0, signer_requests=2), _step(1, broadcasts=2), _step(2, signer_requests=0), _step(2, broadcasts=0),
    _step(0, signer_requests=True), _step(1, broadcasts=1.0), _step(1, broadcasts="1"), _step(0, step="APPROVE"),
    _step(1, gas_limit=700000), _step(2, step=None),
    lambda d: d["limits"]["steps"][0].pop("broadcasts"), lambda d: d["limits"]["steps"][2].pop("signer_requests"),
    lambda d: d["limits"]["steps"][1].pop("step"),
    lambda d: d["limits"].update(signer_requests=1), lambda d: d["limits"].update(broadcasts=1),
    lambda d: d["limits"].update(signer_requests=3, broadcasts=3),
    lambda d: d["limits"].update(attempts=3), lambda d: d["limits"].update(quote_requests=2),
    lambda d: d["limits"].update(actions=0), lambda d: d["limits"].pop("observer_requests"),
    lambda d: d["limits"].update(deadline_seconds=True),
])
def test_any_other_step_limit_shape_is_refused(change):
    source = step_definition()
    change(source)
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_INVALID"):
        OperatingRelease(source)


@pytest.mark.parametrize("change", [
    lambda d: d["limits"].update(signer_requests=3), lambda d: d["limits"].update(broadcasts=3),
    lambda d: d["limits"].pop("signer_requests"), lambda d: d["limits"].pop("broadcasts"),
    lambda d: d["limits"].update(steps=None),
    lambda d: d["limits"].update(steps=[{"step": n, "signer_requests": 1, "broadcasts": 1} for n in STEPS]),
])
def test_a_single_action_release_keeps_its_exact_limits(change):
    source = definition()
    change(source)
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_INVALID"):
        OperatingRelease(source)


# ------------------------------------------------- builder-accepted control decisions (CONTROL-ADOPT-L1)

DECISION = ("fees", "FEE_VALUES_NOT_PROVIDER_BOUND", "a" * 64)


def actual_definition():
    """The synthetic shape, made ACTUAL. The endpoints and evidence class are test inputs only."""
    source = definition()
    source.update(kind="ACTUAL", evidence_class="PROVIDER_ACTUAL")
    source["quote"]["endpoint"] = "https://ws.kuru.io/api/quote"
    source["broadcast"]["endpoint"] = "https://broadcast.example/rpc"
    source["observer"]["endpoint"] = "https://observer.example/rpc"
    for control in source["controls"].values():
        control.update(state="ENFORCED", evidence_class="PROVIDER_ACTUAL", proof_sha256="b" * 64)
    return source


def decision_definition():
    source = actual_definition()
    name, reason, proof = DECISION
    source["controls"][name] = {"state": "DECISION_ACCEPTED", "evidence_class": "BUILDER_DECISION",
                                "proof_sha256": proof, "decision_reason": reason}
    return source


def admit(monkeypatch, release, *, decisions=frozenset({DECISION}), registered=True):
    digest = release_sha256(release)
    monkeypatch.setattr(operating_release, "APPROVED_CONTROL_DECISIONS", decisions)
    monkeypatch.setattr(operating_release, "APPROVED_ACTUAL_RELEASES",
                        {release.content()["release_id"]: digest} if registered else {})
    return check_release(release, expected_sha256=digest, now=NOW)


def test_a_registered_decision_admits_only_its_exact_triple(monkeypatch):
    release = OperatingRelease(decision_definition())
    control = release.content()["controls"]["fees"]
    assert control == {"state": "DECISION_ACCEPTED", "evidence_class": "BUILDER_DECISION",
                       "proof_sha256": "a" * 64, "decision_reason": "FEE_VALUES_NOT_PROVIDER_BOUND"}
    assert admit(monkeypatch, release) == release_sha256(release)


@pytest.mark.parametrize("change", [
    {"decision_reason": "FEE_VALUES_PROVIDER_BOUND"}, {"proof_sha256": "c" * 64},
])
def test_a_changed_decision_reason_or_hash_refuses(monkeypatch, change):
    source = decision_definition()
    source["controls"]["fees"].update(change)
    release = OperatingRelease(source)
    with pytest.raises(ReleaseRefused, match="EXECUTION_CONTROL_UNQUALIFIED"):
        admit(monkeypatch, release)


def test_a_changed_decision_control_name_refuses(monkeypatch):
    source = decision_definition()
    source["controls"]["fees"], source["controls"]["recipient"] = (
        source["controls"]["recipient"], source["controls"]["fees"])
    release = OperatingRelease(source)
    with pytest.raises(ReleaseRefused, match="EXECUTION_CONTROL_UNQUALIFIED"):
        admit(monkeypatch, release)


def test_an_unregistered_decision_refuses_the_control_check(monkeypatch):
    release = OperatingRelease(decision_definition())
    with pytest.raises(ReleaseRefused, match="EXECUTION_CONTROL_UNQUALIFIED"):
        admit(monkeypatch, release, decisions=frozenset())


def test_a_decision_needs_an_actual_release_and_the_builder_evidence_class():
    source = decision_definition()
    source["controls"]["fees"]["evidence_class"] = "PROVIDER_ACTUAL"
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_INVALID"):
        OperatingRelease(source)
    source = decision_definition()
    source["controls"]["fees"]["decision_reason"] = "has a space"
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_INVALID"):
        OperatingRelease(source)


def test_a_decision_under_a_synthetic_release_refuses_at_construction():
    source = definition()
    source["controls"]["fees"] = {"state": "DECISION_ACCEPTED", "evidence_class": "BUILDER_DECISION",
                                  "proof_sha256": "a" * 64, "decision_reason": "FEE_VALUES_NOT_PROVIDER_BOUND"}
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_INVALID"):
        OperatingRelease(source)


def test_a_decision_labelled_enforced_refuses(monkeypatch):
    source = decision_definition()
    source["controls"]["fees"] = {"state": "ENFORCED", "evidence_class": "PROVIDER_ACTUAL",
                                  "proof_sha256": "a" * 64}
    release = OperatingRelease(source)
    with pytest.raises(ReleaseRefused, match="EXECUTION_CONTROL_UNQUALIFIED"):
        admit(monkeypatch, release)


def test_a_decision_proof_relabelled_on_an_enforced_control_refuses(monkeypatch):
    source = actual_definition()
    source["controls"]["fees"]["proof_sha256"] = DECISION[2]
    release = OperatingRelease(source)
    with pytest.raises(ReleaseRefused, match="EXECUTION_CONTROL_UNQUALIFIED"):
        admit(monkeypatch, release)


def test_a_registered_decision_proof_on_a_different_enforced_control_refuses(monkeypatch):
    source = actual_definition()
    source["controls"]["gas_action_capacity"]["proof_sha256"] = DECISION[2]
    release = OperatingRelease(source)
    with pytest.raises(ReleaseRefused, match="EXECUTION_CONTROL_UNQUALIFIED"):
        admit(monkeypatch, release)


def test_a_copied_decision_triple_in_an_unregistered_release_refuses(monkeypatch):
    release = OperatingRelease(decision_definition())
    with pytest.raises(ReleaseRefused, match="ACTUAL_EXECUTION_RELEASE_NOT_APPROVED"):
        admit(monkeypatch, release, registered=False)


def test_control_is_qualified_is_the_shared_rule(monkeypatch):
    release = OperatingRelease(decision_definition())
    content = release.content()
    monkeypatch.setattr(operating_release, "APPROVED_CONTROL_DECISIONS", frozenset({DECISION}))
    assert operating_release.control_is_qualified("fees", content["controls"]["fees"], content) is True
    assert operating_release.control_is_qualified("recipient", content["controls"]["recipient"], content) is True
    changed = dict(content["controls"]["fees"], decision_reason="FEE_VALUES_PROVIDER_BOUND")
    assert operating_release.control_is_qualified("fees", changed, content) is False
