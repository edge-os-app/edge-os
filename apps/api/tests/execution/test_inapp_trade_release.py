"""The authored in-app WMON -> MOE release for the builder's agent wallet.

Pure: no database, socket, provider, signer or credential. The authored file is read from
`docs/qualification/inapp-trade/release.authored.json`. The fills below are test inputs, labelled as such; the
real fills come from the controller's dry run and the builder's sign-in (see `INAPP_TRADE_RELEASE.md`).
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import socket
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from edge_os_api.execution import inapp_trade_release as inapp
from edge_os_api.execution import operating_release
from edge_os_api.execution.direct_route_quote_client import DirectRoutePins, DirectRouteQuoteClient, build_program_hex
from edge_os_api.execution.operating_release import CONTROLS, ReleaseRefused, check_release, release_sha256, release_steps
from edge_os_api.kuru_flow.flow_calldata import decode_flow_call
from scripts.privy_unfunded_proof import actual_packet

from execution.test_direct_route_quote_client import Http, reserves_reply

AUTHORED_PATH = Path(__file__).resolve().parents[4] / "docs/qualification/inapp-trade/release.authored.json"
NOW = dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)
WMON = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"
MOE = "0xd8e004acba279417c04c0633cb5a21ceca207777"
POOL = "0x97199b34564911936bc850ac45ede785892b5aad"
ENTRYPOINT = "0xb3e6778480b2E488385E8205eA05E20060B813cb"
WALLET = "0x91BB52A63c91986813288965e4681FF111De1b63"
# Policy-owned controls: the sealed packet is LOCAL_TESTED until its v3 live result is recorded in the repository.
POLICY_OWNED = {"chain", "wallet_signer_binding", "entrypoint_method", "approvals"}
# Test inputs only. Real reserves, estimates, endpoints and proofs come from the controller's recorded reads.
RESERVE_WMON, RESERVE_MOE = 4_000 * 10**18, 9_000_000 * 10**18


def authored() -> dict:
    return json.loads(AUTHORED_PATH.read_text(encoding="utf-8"))


def fill(**changes) -> dict:
    value = {
        "quote_endpoint": "https://quote-relay.example/rpc",
        "broadcast_endpoint": "https://broadcast-relay.example/rpc",
        "observer_endpoint": "https://observer-relay.example/rpc",
        "valid_until": "2026-10-24T00:00:00Z", "mandate_expires_at": "2026-10-25T00:00:00Z",
        "abi_sha256": "a" * 64, "mutable_router_proof_sha256": "b" * 64,
        "reserves": {"block_number": 1, "reserve_wmon": str(RESERVE_WMON), "reserve_moe": str(RESERVE_MOE)},
        "gas_estimates": {"approve": 46000, "swap": 544967, "revoke": 26000},
    }
    value.update(changes)
    return value


def identity() -> dict:
    return {"owner_id": "11111111-1111-4111-8111-111111111111", "agent_id": "agent-test",
            "wallet_id": "bsb2feecuxl81dl5jz4u9xxo", "wallet_address": WALLET, "network_id": "monad:143",
            "strategy_id": "strategy-test", "publication_revision_id": "22222222-2222-4222-8222-222222222222",
            "execution_revision_id": "execution-test", "market_binding_id": "market-test",
            "content_sha256": "1" * 64, "manifest_sha256": "2" * 64,
            "consent_adoption_id": "33333333-3333-4333-8333-333333333333",
            "consent_hash": "sha256:" + "3" * 64, "review_hash": "sha256:" + "4" * 64,
            "terms_hash": "sha256:" + "5" * 64}


def binding_fill(**changes) -> dict:
    value = {"identity": identity(), "position_inventory_proof_sha256": "6" * 64, "market_proof_sha256": "7" * 64,
             "finality_proof_sha256": "8" * 64, "exit_capacity_proof_sha256": None, "valuation_proof_sha256": None,
             "cost_model_proof_sha256": None, "market_profile": None}
    value.update(changes)
    return value


def register(monkeypatch, release, binding=None) -> None:
    monkeypatch.setattr(operating_release, "APPROVED_ACTUAL_RELEASES",
                        {release.content()["release_id"]: release_sha256(release)})
    if binding is not None:
        monkeypatch.setattr(operating_release, "APPROVED_ACTUAL_BINDINGS", {binding.sha256: release_sha256(release)})


def all_controls_proven(source: dict) -> dict:
    """A hypothetical: what the release would carry once every control has provider-actual proof."""
    changed = copy.deepcopy(source)
    for control in changed["release"]["controls"].values():
        control.update(state="ENFORCED", evidence_class="PROVIDER_ACTUAL", proof_sha256="9" * 64)
    return changed


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


def test_authored_release_names_the_one_builder_wallet_policy_and_pinned_route():
    source = authored()
    release, facts = source["release"], source["facts"]
    assert (release["wallet_id"], release["wallet_address"], release["signer_id"], release["policy_id"],
            release["policy_owner_id"], release["policy_content_sha256"]) == (
        actual_packet.WALLET_ID, actual_packet.WALLET_ADDRESS, actual_packet.EXECUTOR_ID, actual_packet.POLICY_ID,
        actual_packet.POLICY_OWNER_ID, actual_packet.POLICY_BODY_SHA256)
    assert release["independent_proof_sha256"] == actual_packet.SEALED_PACKET_SHA256
    assert actual_packet.SEALED_PACKET_SHA256 in actual_packet.CODE_OWNED_PACKET_APPROVALS
    assert release["kind"] == "ACTUAL" and release["chain_id"] == 143
    route, quote = release["route"], release["quote"]
    assert route["recipient"] == release["wallet_address"]
    assert (route["input_asset"]["token_address"], route["output_asset"]["token_address"]) == (WMON, MOE)
    assert route["entrypoint_address"] == ENTRYPOINT and route["selector"] == "0xce1e7030"
    assert (quote["source"], quote["pool_address"], quote["token0_address"], quote["token1_address"],
            quote["direction"], quote["program_fee_ppm"], quote["slippage_bps"],
            quote["pre_sign_tolerance_bps"]) == (
        "DIRECT_V2_PROGRAM", POOL, WMON, MOE, 0, 16000, 100, 50)
    assert route["approved_program_hex"] == build_program_hex(input_token=WMON, pool_address=POOL, direction=0,
                                                              fee_ppm=16000)
    assert route["approved_input_raw"] == route["approved_allowance_raw"] == str(10 * 10**18)
    assert int(route["approved_input_raw"]) <= 70 * 10**18  # Privy R2 approve cap
    assert release["deployment"]["entrypoint_code_sha256"] == facts["code_sha256"]["entrypoint"]
    assert facts["code_sha256"] == {
        "entrypoint": "da214086b3c9bc283c9fe99966baf01a5b97ad8f6f3a7313d37f89008594e1cf",
        "wmon": "1ba3ee06b3e4cd7beea3f1899cac23edb47876c45fceb320245d092ed2bfd187",
        "pool": "aae0c2751bc188e73da0773ae6f6b951aadb7dde6ccb0c0b22595a7f1541644d"}
    assert facts["gas_limits"] == {"wrap": 60000, "approve": 70000, "swap": 700000, "revoke": 70000}
    assert release["gas"]["gas_limit"] == facts["gas_limits"]["swap"]


def test_no_control_claims_provider_proof_the_repository_does_not_record():
    controls = authored()["release"]["controls"]
    assert all(control["evidence_class"] != "PROVIDER_ACTUAL" for control in controls.values())
    for name in POLICY_OWNED:
        assert controls[name] == {"state": "ENFORCED", "evidence_class": "LOCAL_TESTED",
                                  "proof_sha256": actual_packet.SEALED_PACKET_SHA256}


def test_owner_agent_and_consent_ids_are_never_authored():
    text = AUTHORED_PATH.read_text(encoding="utf-8")
    for name in ("owner_id", "agent_id", "consent_adoption_id"):
        assert f'"{name}"' not in text


def test_completed_release_validates_with_a_stable_hash_and_refuses_while_unregistered():
    release = inapp.complete_release(authored(), fill())
    digest = release_sha256(release)
    assert release_sha256(inapp.complete_release(authored(), fill())) == digest
    assert operating_release.APPROVED_ACTUAL_RELEASES == {} and operating_release.APPROVED_ACTUAL_BINDINGS == {}
    with pytest.raises(ReleaseRefused, match="ACTUAL_EXECUTION_RELEASE_NOT_APPROVED"):
        check_release(release, expected_sha256=digest, now=NOW)
    with pytest.raises(ReleaseRefused, match="ACTUAL_EXECUTION_RELEASE_NOT_APPROVED"):
        check_release(release, expected_sha256=digest, now=NOW, synthetic_approvals={"x": digest})


def test_pending_registry_line_reaches_the_control_check_and_the_honest_controls_refuse(monkeypatch):
    release = inapp.complete_release(authored(), fill())
    register(monkeypatch, release)
    with pytest.raises(ReleaseRefused, match="EXECUTION_CONTROL_UNQUALIFIED"):
        check_release(release, expected_sha256=release_sha256(release), now=NOW)
    assert inapp.unqualified_controls(release) == sorted(CONTROLS)


def test_release_admits_its_exact_hash_once_registered_and_every_control_is_proven(monkeypatch):
    release = inapp.complete_release(all_controls_proven(authored()), fill())
    digest = release_sha256(release)
    with pytest.raises(ReleaseRefused, match="ACTUAL_EXECUTION_RELEASE_NOT_APPROVED"):
        check_release(release, expected_sha256=digest, now=NOW)
    register(monkeypatch, release)
    assert check_release(release, expected_sha256=digest, now=NOW) == digest
    assert inapp.unqualified_controls(release) == []
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_HASH_MISMATCH"):
        check_release(release, expected_sha256="0" * 64, now=NOW)
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_EXPIRED"):
        check_release(release, expected_sha256=digest, now=dt.datetime(2026, 10, 24, tzinfo=dt.timezone.utc))


@pytest.mark.parametrize("control", sorted(CONTROLS))
@pytest.mark.parametrize("change", [
    {"state": "UNKNOWN"}, {"evidence_class": "LOCAL_TESTED"}, {"proof_sha256": "e" * 64},
])
def test_any_changed_control_refuses(monkeypatch, control, change):
    source = all_controls_proven(authored())
    release = inapp.complete_release(source, fill())
    register(monkeypatch, release)
    changed_source = copy.deepcopy(source)
    changed_source["release"]["controls"][control].update(change)
    changed = inapp.complete_release(changed_source, fill())
    assert release_sha256(changed) != release_sha256(release)
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_HASH_MISMATCH"):
        check_release(changed, expected_sha256=release_sha256(release), now=NOW)
    with pytest.raises(ReleaseRefused, match="ACTUAL_EXECUTION_RELEASE_NOT_APPROVED"):
        check_release(changed, expected_sha256=release_sha256(changed), now=NOW)


@pytest.mark.parametrize("name", ["actions", "attempts", "quote_requests"])
def test_one_action_one_attempt_stays_one(name):
    release = inapp.complete_release(authored(), fill())
    assert release.content()["limits"][name] == 1
    source = authored()
    source["release"]["limits"][name] = 2
    with pytest.raises(ReleaseRefused):
        inapp.complete_release(source, fill())


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("name", ["signer_requests", "broadcasts"])
def test_each_step_stays_one_signer_request_and_one_broadcast(index, name):
    release = inapp.complete_release(authored(), fill())
    assert release.content()["limits"]["steps"][index][name] == 1
    source = authored()
    source["release"]["limits"]["steps"][index][name] = 2
    with pytest.raises(ReleaseRefused):
        inapp.complete_release(source, fill())


def test_the_release_names_approve_swap_revoke_each_with_one_signer_request_and_one_broadcast():
    source = authored()
    limits = source["release"]["limits"]
    assert limits == {"actions": 1, "attempts": 1, "quote_requests": 1, "observer_requests": 20,
                      "max_request_bytes": 4096, "max_response_bytes": 16384, "deadline_seconds": 60,
                      "steps": [{"step": "approve", "signer_requests": 1, "broadcasts": 1},
                                {"step": "swap", "signer_requests": 1, "broadcasts": 1},
                                {"step": "revoke", "signer_requests": 1, "broadcasts": 1}]}
    assert [step["step"] for step in limits["steps"]] == source["facts"]["active_steps"]
    release = inapp.complete_release(source, fill())
    assert release_steps(release) == ("approve", "swap", "revoke")


@pytest.mark.parametrize("change", [
    lambda a: a["facts"].update(active_steps=["approve", "swap"]),
    lambda a: a["release"]["limits"].update(steps=a["release"]["limits"]["steps"][:2]),
    lambda a: a["release"]["limits"].update(steps=a["release"]["limits"]["steps"][::-1]),
    lambda a: a["release"]["limits"].pop("steps"),
    # The old single-action limits are a valid release shape, but not for the in-app approve, swap and revoke.
    lambda a: (a["release"]["limits"].pop("steps"), a["release"]["limits"].update(signer_requests=1, broadcasts=1)),
])
def test_an_authored_file_whose_release_steps_differ_from_its_active_steps_refuses(change):
    source = authored()
    change(source)
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())


def test_the_gas_budget_covers_approve_swap_and_revoke_at_the_fixed_maximum_fee():
    source = authored()
    gas, limits = source["release"]["gas"], source["facts"]["gas_limits"]
    assert gas["budget_raw"] == "169680000000000000"
    assert int(gas["budget_raw"]) == (limits["approve"] + limits["swap"] + limits["revoke"]) * gas["max_fee_per_gas"]
    assert inapp.complete_release(source, fill()).content()["gas"]["budget_raw"] == "169680000000000000"
    # Still inside the USD 2 ceiling with gas: the input plus the budget, at the release's MON price.
    price = Decimal(source["facts"]["mon_usd_price"])
    assert (Decimal(int(source["release"]["route"]["approved_input_raw"]) + int(gas["budget_raw"])) * price
            / Decimal(10**18)) == Decimal("0.2033936")
    assert inapp.worst_case_usd(source) <= Decimal("2.00")
    source["release"]["gas"]["budget_raw"] = "169679999999999999"
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())
    source["release"]["gas"]["budget_raw"] = "141400000000000000"  # the swap alone (the CLOUD-A2 budget)
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())


def test_the_document_prints_the_sha256_of_the_authored_release_file():
    digest = hashlib.sha256(AUTHORED_PATH.read_bytes()).hexdigest()
    document = AUTHORED_PATH.with_name("INAPP_TRADE_RELEASE.md").read_text(encoding="utf-8")
    assert f"`{digest}`" in document


def test_gas_rule_is_ceil_of_estimate_times_one_point_two():
    assert inapp.required_gas_limit(544967) == 653961
    assert inapp.required_gas_limit(10) == 12 and inapp.required_gas_limit(11) == 14
    inapp.check_gas_limits({"swap": 653961}, {"swap": 544967}, ["swap"])
    with pytest.raises(ReleaseRefused, match="GAS_LIMIT_TOO_LOW"):
        inapp.check_gas_limits({"swap": 653960}, {"swap": 544967}, ["swap"])
    with pytest.raises(ReleaseRefused, match="GAS_LIMIT_TOO_LOW"):  # the 2026-10-22 failed limit
        inapp.check_gas_limits({"swap": 400000}, {"swap": 544967}, ["swap"])


@pytest.mark.parametrize("step,estimate", [("swap", 583334), ("approve", 58334), ("revoke", 58334)])
def test_a_limit_below_one_point_two_times_the_recorded_estimate_refuses_completion(step, estimate):
    estimates = dict(fill()["gas_estimates"], **{step: estimate})
    with pytest.raises(ReleaseRefused, match="GAS_LIMIT_TOO_LOW"):
        inapp.complete_release(authored(), fill(gas_estimates=estimates))
    estimates[step] = estimate - 1  # ceil((estimate - 1) * 1.2) equals the authored limit
    inapp.complete_release(authored(), fill(gas_estimates=estimates))


def test_a_lowered_authored_swap_limit_refuses_against_the_recorded_estimate():
    source = authored()
    source["facts"]["gas_limits"]["swap"] = source["release"]["gas"]["gas_limit"] = 400000
    source["release"]["gas"]["budget_raw"] = str((70000 + 400000 + 70000) * source["release"]["gas"]["max_fee_per_gas"])
    with pytest.raises(ReleaseRefused, match="GAS_LIMIT_TOO_LOW"):
        inapp.complete_release(source, fill(gas_estimates={"approve": 1, "swap": 1, "revoke": 1}))


def test_release_swap_gas_must_equal_the_authored_swap_limit():
    source = authored()
    source["facts"]["gas_limits"]["swap"] = 800000
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())


def test_usd_ceiling_arithmetic_includes_every_step_gas():
    source = authored()
    worst_wei = 10 * 10**18 + (60000 + 70000 + 700000 + 70000) * 202 * 10**9
    assert worst_wei == 10_181_800_000_000_000_000
    assert inapp.worst_case_usd(source) == Decimal("0.203636")
    source["facts"]["mon_usd_price"] = "0.197"  # 10.1818 MON * 0.197 = 2.0058 USD
    with pytest.raises(ReleaseRefused, match="USD_CEILING_EXCEEDED"):
        inapp.complete_release(source, fill())
    source["facts"]["mon_usd_price"] = "0.196"  # 1.9956 USD
    inapp.complete_release(source, fill())
    source["facts"]["usd_ceiling"] = "2.01"
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())


def test_minimum_output_matches_the_direct_quote_floor_and_a_worse_pool_refuses_the_quote():
    release = inapp.complete_release(authored(), fill())
    content = release.content()
    amount = 10 * 10**18
    output = amount * 984000 * RESERVE_MOE // (RESERVE_WMON * 10**6 + amount * 984000)
    assert content["route"]["approved_min_output_raw"] == str(output * 9900 // 10000)
    accepted = {"chain_id": 143, "sell_token": WMON, "buy_token": MOE, "amount": str(amount), "user": WALLET}

    def quote(reserve_moe: int):
        client = DirectRouteQuoteClient(DirectRoutePins.from_release(content), accepted_request=accepted,
            slippage_bps=100, http=Http(reserves_reply(RESERVE_WMON, reserve_moe)), deadline_monotonic=100.0,
            connect_timeout_seconds=5.0, max_request_bytes=4096, max_response_bytes=16384,
            evidence_class="PROVIDER_UNQUALIFIED", monotonic=lambda: 1.0, wall_clock=lambda: NOW)
        return client.quote(dict(accepted))

    assert quote(RESERVE_MOE)["minOut"] == content["route"]["approved_min_output_raw"]
    assert DirectRoutePins.from_release(content).pre_sign_tolerance_bps == 50
    # 40 bps worse than the recorded read is inside the release's 50 bps pre-sign tolerance.
    inside = quote(RESERVE_MOE - RESERVE_MOE * 40 // 10000)
    assert inside["minOut"] == content["route"]["approved_min_output_raw"]
    call = decode_flow_call(data_hex=inside["transaction"]["calldata"], method="EXECUTE_SWAP")
    assert call.intent.min_amount_user_buys == content["route"]["approved_min_output_raw"]
    # 60 bps worse is outside it and refuses before signing.
    with pytest.raises(Exception, match="QUOTE_SLIPPAGE_EXCEEDED"):
        quote(RESERVE_MOE - RESERVE_MOE * 60 // 10000)
    with pytest.raises(Exception, match="QUOTE_SLIPPAGE_EXCEEDED"):
        quote(RESERVE_MOE - RESERVE_MOE // 100)


@pytest.mark.parametrize("value", [51, -1, 50.0, "50", True, None])
def test_a_pre_sign_tolerance_outside_the_integer_range_refuses(value):
    source = authored()
    source["release"]["quote"]["pre_sign_tolerance_bps"] = value
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())


def test_the_in_app_shape_requires_the_pre_sign_tolerance_field():
    source = authored()
    source["release"]["quote"].pop("pre_sign_tolerance_bps")
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())


@pytest.mark.parametrize("value", [0, 49, 50])
def test_an_integer_pre_sign_tolerance_from_zero_to_fifty_completes(value):
    source = authored()
    source["release"]["quote"]["pre_sign_tolerance_bps"] = value
    assert inapp.complete_release(source, fill()).content()["quote"]["pre_sign_tolerance_bps"] == value


def test_the_completed_release_carries_exactly_fifty_bps():
    assert inapp.complete_release(authored(), fill()).content()["quote"]["pre_sign_tolerance_bps"] == 50


@pytest.mark.parametrize("change", [
    lambda f: f.pop("abi_sha256"), lambda f: f.update(extra="x"),
    lambda f: f.update(quote_endpoint="https://quote.invalid/rpc"),
    lambda f: f.update(broadcast_endpoint="https://broadcast-relay.example/rpc?key=1"),
    lambda f: f.update(observer_endpoint=f["broadcast_endpoint"]),
    lambda f: f.update(valid_until="2026-10-26T00:00:00Z"),
    lambda f: f.update(abi_sha256="A" * 64),
    lambda f: f["reserves"].update(reserve_moe="0"), lambda f: f["reserves"].update(reserve_wmon=4000),
    lambda f: f["reserves"].pop("block_number"), lambda f: f["gas_estimates"].pop("revoke"),
    lambda f: f["gas_estimates"].update(wrap=1), lambda f: f["gas_estimates"].update(swap=True),
    lambda f: f.update(approved_min_output_raw="1"),
])
def test_a_malformed_or_extra_fill_refuses(change):
    value = fill()
    change(value)
    with pytest.raises(ReleaseRefused):
        inapp.complete_release(authored(), value)


@pytest.mark.parametrize("change", [
    lambda a: a["facts"].update(gas_margin="1.1"), lambda a: a["release"].pop("route"),
    lambda a: a["release"].update(quote=None), lambda a: a.update(facts=[]),
])
def test_a_malformed_authored_file_refuses_with_a_stable_code(change):
    source = authored()
    change(source)
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())


def test_an_oversized_reserve_refuses_with_a_stable_code():
    value = fill()
    value["reserves"]["reserve_moe"] = "9" * 5000
    with pytest.raises(ReleaseRefused, match="INAPP_FILL_INVALID"):
        inapp.complete_release(authored(), value)


def test_an_unfilled_marker_or_changed_authoring_schema_refuses():
    source = authored()
    source["release"]["policy_id"] = {"$fill": "policy_id"}
    with pytest.raises(ReleaseRefused):
        inapp.complete_release(source, fill())
    source = authored()
    source["schema"] = "edge-os.inapp-trade-authoring/2"
    with pytest.raises(ReleaseRefused, match="INAPP_AUTHORED_INVALID"):
        inapp.complete_release(source, fill())


def test_binding_hash_covers_owner_agent_and_consent_and_one_wallet(monkeypatch):
    release = inapp.complete_release(all_controls_proven(authored()), fill())
    bound = inapp.bind_release(release, binding_fill())
    assert bound.identity() == identity()
    for name in ("owner_id", "agent_id", "consent_adoption_id"):
        other = inapp.bind_release(release, binding_fill(identity={**identity(), name: "foreign"}))
        assert other.sha256 != bound.sha256
    for name, value in (("wallet_id", "other-wallet"), ("wallet_address", "0x" + "9" * 40)):
        with pytest.raises(ReleaseRefused):
            inapp.bind_release(release, binding_fill(identity={**identity(), name: value}))
    with pytest.raises(ReleaseRefused, match="ACTUAL_EXECUTION_BINDING_NOT_APPROVED"):
        bound.admit(identity(), now=NOW)
    register(monkeypatch, release, bound)
    assert bound.admit(identity(), now=NOW) == bound.sha256
    with pytest.raises(ReleaseRefused, match="EXECUTION_BINDING_MISMATCH"):
        bound.admit({**identity(), "agent_id": "foreign"}, now=NOW)


def test_binding_of_the_honest_release_refuses_at_the_control_check(monkeypatch):
    release = inapp.complete_release(authored(), fill())
    bound = inapp.bind_release(release, binding_fill())
    register(monkeypatch, release, bound)
    with pytest.raises(ReleaseRefused, match="EXECUTION_CONTROL_UNQUALIFIED"):
        bound.admit(identity(), now=NOW)


@pytest.mark.parametrize("change", [
    lambda b: b.pop("market_profile"), lambda b: b.update(extra=None),
    lambda b: b.update(finality_proof_sha256=None), lambda b: b["identity"].pop("terms_hash"),
])
def test_a_malformed_binding_fill_refuses(change):
    release = inapp.complete_release(authored(), fill())
    value = binding_fill()
    change(value)
    with pytest.raises(ReleaseRefused):
        inapp.bind_release(release, value)


def test_registry_lines_are_the_exact_pending_one_line_changes():
    release = inapp.complete_release(authored(), fill())
    bound = inapp.bind_release(release, binding_fill())
    digest = release_sha256(release)
    assert inapp.registry_lines(release, bound) == [
        f'APPROVED_ACTUAL_RELEASES: Mapping[str, str] = MappingProxyType({{"actual-inapp-wmon-moe-20261022/1": "{digest}"}})',
        f'APPROVED_ACTUAL_BINDINGS: Mapping[str, str] = MappingProxyType({{"{bound.sha256}": "{digest}"}})',
    ]


def test_saved_identity_is_read_from_the_builder_records_and_must_name_the_release_wallet(monkeypatch):
    release = inapp.complete_release(authored(), fill())
    owner = uuid.UUID(identity()["owner_id"])
    agent = SimpleNamespace(wallet_id="bsb2feecuxl81dl5jz4u9xxo")
    saved = identity()
    calls = []
    monkeypatch.setattr(inapp, "resolve_agent", lambda session, owner_id, agent_id: calls.append(
        (owner_id, agent_id)) or agent)
    monkeypatch.setattr(inapp, "adopted_consent", lambda session, value: "consent" if value is agent else None)
    monkeypatch.setattr(inapp, "wallet_address", lambda session, owner_id, agent_id, wallet_id: WALLET)
    monkeypatch.setattr(inapp, "saved_release_identity", lambda value, consent, address: dict(saved))
    assert inapp.saved_identity_for_release(object(), owner, "agent-test", release) == saved
    assert calls == [(owner, "agent-test")]
    monkeypatch.setattr(inapp, "saved_release_identity",
                        lambda value, consent, address: {**saved, "wallet_address": "0x" + "9" * 40})
    with pytest.raises(ReleaseRefused, match="SAVED_IDENTITY_WALLET_MISMATCH"):
        inapp.saved_identity_for_release(object(), owner, "agent-test", release)
    monkeypatch.setattr(inapp, "adopted_consent", lambda session, value: None)
    with pytest.raises(ReleaseRefused, match="SAVED_IDENTITY_UNAVAILABLE"):
        inapp.saved_identity_for_release(object(), owner, "agent-test", release)
    monkeypatch.setattr(inapp, "resolve_agent", lambda session, owner_id, agent_id: None)
    with pytest.raises(ReleaseRefused, match="SAVED_IDENTITY_UNAVAILABLE"):
        inapp.saved_identity_for_release(object(), owner, "agent-test", release)


def test_command_prints_the_release_hash_and_registry_lines(tmp_path, capsys):
    fill_path, binding_path = tmp_path / "fill.json", tmp_path / "binding.json"
    fill_path.write_text(json.dumps(fill()), encoding="utf-8")
    binding_path.write_text(json.dumps(binding_fill()), encoding="utf-8")
    assert inapp.main(["--authored", str(AUTHORED_PATH), "--fill", str(fill_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    release = inapp.complete_release(authored(), fill())
    assert printed["release_sha256"] == release_sha256(release)
    assert printed["release"] == release.content()
    assert printed["unqualified_controls"] == sorted(CONTROLS)
    assert "binding_sha256" not in printed
    assert inapp.main(["--authored", str(AUTHORED_PATH), "--fill", str(fill_path),
                       "--binding-fill", str(binding_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["binding_sha256"] == inapp.bind_release(release, binding_fill()).sha256
    assert printed["registry_lines"] == inapp.registry_lines(release, inapp.bind_release(release, binding_fill()))
    fill_path.write_text("{}", encoding="utf-8")
    assert inapp.main(["--authored", str(AUTHORED_PATH), "--fill", str(fill_path)]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "code": "INAPP_FILL_INVALID"}
