"""Test-owned synthetic authority never approves an actual operating release."""

import copy
import datetime as dt
import socket
import pytest
from edge_os_api.execution.operating_release import OperatingRelease, check_release, release_sha256
from edge_os_api.execution.operating_release import CONTROLS, ReleaseRefused




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
