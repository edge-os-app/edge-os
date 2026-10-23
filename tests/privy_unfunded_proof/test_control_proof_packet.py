"""The sealed control-proof Privy packet: new rows only, the 19 v3 rows unchanged. No network."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from eth_utils import keccak

from scripts.privy_unfunded_proof import actual_packet, actual_run, chain_proof, specimens
from scripts.privy_unfunded_proof.actual_packet import (
    CODE_OWNED_PACKET_APPROVALS,
    CONTROL_PROOF_ORDER,
    CONTROL_PROOF_PACKET,
    CONTROL_PROOF_TABLE,
    UNFUNDED_POLICY_PACKET,
    UNFUNDED_POLICY_TABLE,
    resolve_approved_packet,
)
from scripts.privy_unfunded_proof.actual_profile import PRIVY_POLICY_CODES
from scripts.privy_unfunded_proof.actual_transport import accepted_request_profile
from scripts.privy_unfunded_proof.specimens import AttemptStore, Category, Expected, SpecimenRefused

from tests.privy_unfunded_proof._actual_support import code_reply, injected, make_profile, matched_factory, success_reply

NOW = 1_792_800_000  # 2026-10-23T08:00:00Z
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "policy_v2_live_rules.json"
V3_REQUESTS = {
    "raw.allow_deposit_1_mon": "f3a177f244b7df7cb97a19b0b448f0c28207e4d799981dc586f94c685b45fbc5",
    "raw.allow_swap_zero_value": "f31cde63df34f78379574114e4705415df911a72d78779ba679c294cb98e3946",
    "raw.deny_execute_swap_with_receiver": "cbc7282e3dbbf1737dfc979e55ed9b959d132974f7bf335c384e79469eb716d7",
    "raw.deny_swap_with_mon": "ac3277ebd460be8fedf0f1745d163eda5e3d8becea9b0027bf727d18d689b652",
}
EXPECTED_ORDER = (
    "raw.ctl_allow_revoke_zero",
    "raw.ctl_deny_approve_moe_entrypoint",
    "raw.ctl_deny_swap_receiver_wallet",
    "raw.ctl_deny_moe_transfer_sink",
    "raw.ctl_deny_expired_request",
)


def _transaction(specimen_id: str) -> dict:
    return json.loads(CONTROL_PROOF_PACKET.requests[specimen_id].body)["params"]["transaction"]


# ---------------------------------------------------------------- the v3 packet is unchanged


def test_v3_packet_and_its_nineteen_rows_are_unchanged() -> None:
    assert UNFUNDED_POLICY_PACKET.packet_id == actual_packet.SEALED_PACKET_SHA256 == (
        "8255d003097fd1a0216a6b64c48637f2ef745c7ebbe73035d0b8929403500528")
    assert UNFUNDED_POLICY_TABLE.manifest_sha256 == actual_packet.SEALED_ACTUAL_MANIFEST_SHA256
    assert len(UNFUNDED_POLICY_PACKET.requests) == 19
    for specimen_id, digest in V3_REQUESTS.items():
        assert UNFUNDED_POLICY_PACKET.requests[specimen_id].request_sha256 == digest
    assert not set(CONTROL_PROOF_PACKET.requests) & set(UNFUNDED_POLICY_PACKET.requests)


def test_registry_holds_the_v3_packet_and_the_sealed_control_packet() -> None:
    assert list(CODE_OWNED_PACKET_APPROVALS) == [actual_packet.SEALED_PACKET_SHA256,
                                                 actual_packet.SEALED_CONTROL_PROOF_PACKET_SHA256]
    assert CONTROL_PROOF_PACKET.packet_id == CONTROL_PROOF_PACKET.packet_sha256()
    assert CONTROL_PROOF_PACKET.packet_id == actual_packet.SEALED_CONTROL_PROOF_PACKET_SHA256
    assert specimens.CODE_OWNED_ACTUAL_MANIFESTS == frozenset({
        actual_packet.SEALED_ACTUAL_MANIFEST_SHA256, actual_packet.SEALED_CONTROL_PROOF_MANIFEST_SHA256})
    assert CONTROL_PROOF_TABLE.manifest_sha256 == actual_packet.SEALED_CONTROL_PROOF_MANIFEST_SHA256
    assert resolve_approved_packet(CONTROL_PROOF_PACKET.packet_id, now_epoch=NOW,
                                   table=CONTROL_PROOF_TABLE) is CONTROL_PROOF_PACKET


def test_a_changed_control_packet_is_not_admitted() -> None:
    tampered = dataclasses.replace(CONTROL_PROOF_PACKET, packet_id="", attempt_identity="control-proofs-2")
    tampered = dataclasses.replace(tampered, packet_id=tampered.packet_sha256())
    assert actual_packet._sealed_packet_registry(tampered, actual_packet.SEALED_CONTROL_PROOF_PACKET_SHA256) == {}
    with pytest.raises(SpecimenRefused) as caught:
        resolve_approved_packet(tampered.packet_id, now_epoch=NOW, table=CONTROL_PROOF_TABLE)
    assert caught.value.code == "ACTUAL_PACKET_NOT_APPROVED"


def test_control_packet_binds_the_same_identities_and_a_new_attempt_identity() -> None:
    for name in ("app_id", "executor_id", "owner_id", "policy_resource_owner_id", "wallet_id", "wallet_address",
                 "network_id", "chain_id", "signing_url", "signing_method", "profile_policies",
                 "profile_policy_sha256", "controls", "position_inventory", "proof_scope"):
        assert getattr(CONTROL_PROOF_PACKET, name) == getattr(UNFUNDED_POLICY_PACKET, name)
    assert CONTROL_PROOF_PACKET.attempt_identity == "control-proofs-1"
    assert CONTROL_PROOF_PACKET.expires_at_epoch == 1_796_083_200  # 2026-11-30T00:00:00Z
    assert CONTROL_PROOF_PACKET.auth_header_expiry == "1796083200000"


# ---------------------------------------------------------------- rows


def test_order_starts_with_the_one_allow_and_ends_with_the_expiry_row() -> None:
    assert CONTROL_PROOF_ORDER == EXPECTED_ORDER
    assert [row.specimen_id for row in CONTROL_PROOF_TABLE.all()] == list(EXPECTED_ORDER)
    assert CONTROL_PROOF_TABLE.positive_control("raw").specimen_id == EXPECTED_ORDER[0]
    assert CONTROL_PROOF_TABLE.get(EXPECTED_ORDER[0]).category is Category.POSITIVE_CONTROL
    assert dict(CONTROL_PROOF_PACKET.specimen_expected) == {
        "raw.ctl_allow_revoke_zero": "ALLOW",
        "raw.ctl_deny_approve_moe_entrypoint": "POLICY_DENY",
        "raw.ctl_deny_swap_receiver_wallet": "POLICY_DENY",
        "raw.ctl_deny_moe_transfer_sink": "POLICY_DENY",
        "raw.ctl_deny_expired_request": "EXPIRY_REFUSAL",
    }


def test_every_row_is_a_type_2_sign_request_on_the_wallet_route_with_an_unusable_nonce() -> None:
    for specimen_id in EXPECTED_ORDER:
        request = CONTROL_PROOF_PACKET.requests[specimen_id]
        body = json.loads(request.body)
        assert accepted_request_profile(body)
        assert request.url == actual_packet.SIGNING_URL and request.http_method == "POST"
        transaction = body["params"]["transaction"]
        assert transaction["chain_id"] == 143 and transaction["type"] == 2 and transaction["value"] == 0
        assert transaction["nonce"] == actual_packet.CONTROL_PROOF_NONCE == 1_000_000
        assert transaction["max_fee_per_gas"] == actual_packet.MAX_FEE_PER_GAS


def test_the_only_allow_is_a_revoke_to_zero() -> None:
    transaction = _transaction("raw.ctl_allow_revoke_zero")
    assert transaction["to"] == actual_packet.WMON
    assert transaction["data"] == "0x095ea7b3" + "0" * 24 + actual_packet.ENTRYPOINT[2:] + "0" * 64


def test_exact_negative_bodies() -> None:
    moe, wallet = chain_proof.MOE, actual_packet.WALLET_ADDRESS.lower()
    approve = _transaction("raw.ctl_deny_approve_moe_entrypoint")
    assert approve["to"] == moe
    assert approve["data"] == ("0x095ea7b3" + "0" * 24 + actual_packet.ENTRYPOINT[2:]
                               + f"{chain_proof.INPUT_RAW:064x}")
    transfer = _transaction("raw.ctl_deny_moe_transfer_sink")
    assert transfer["to"] == moe
    assert transfer["data"] == "0xa9059cbb" + "0" * 24 + actual_packet.SINK[2:] + f"{1:064x}"
    receiver = _transaction("raw.ctl_deny_swap_receiver_wallet")
    assert receiver["to"] == actual_packet.ENTRYPOINT
    selector = "0x" + keccak(text=actual_packet.EXECUTE_SWAP_WITH_RECEIVER_SIGNATURE)[:4].hex()
    assert receiver["data"].startswith(selector)
    swap = chain_proof.swap_calldata(min_output_raw=1)
    # The receiver variant is the release swap with bytes offset 352 and the wallet as the receiver word.
    assert receiver["data"][10:10 + 64 * 9] == swap[10:10 + 64 * 9]
    assert int(receiver["data"][10 + 64 * 9: 10 + 64 * 10], 16) == 352
    assert receiver["data"][10 + 64 * 10: 10 + 64 * 11] == "0" * 24 + wallet[2:]
    assert receiver["data"][10 + 64 * 11:] == swap[10 + 64 * 10:]


def test_the_expiry_row_is_the_in_policy_release_swap_with_a_past_request_expiry() -> None:
    request = CONTROL_PROOF_PACKET.requests["raw.ctl_deny_expired_request"]
    assert request.headers == (("privy-request-expiry", actual_packet.CONTROL_PROOF_EXPIRED_HEADER),)
    assert int(actual_packet.CONTROL_PROOF_EXPIRED_HEADER) < NOW * 1000
    transaction = _transaction("raw.ctl_deny_expired_request")
    assert transaction["to"] == actual_packet.ENTRYPOINT
    assert transaction["data"] == chain_proof.swap_calldata(min_output_raw=1)
    assert transaction["gas_limit"] == chain_proof.SWAP_GAS_LIMIT


# ---------------------------------------------------------------- the live rules decide each expectation


def _condition_holds(condition: dict, transaction: dict) -> bool:
    if condition["field_source"] == "ethereum_transaction":
        actual = transaction[condition["field"]]
        actual = int(actual, 16) if isinstance(actual, str) and actual.startswith("0x") and condition["field"] != "to" else actual
        if condition["field"] == "to":
            return actual.lower() == condition["value"].lower()
        expected = int(condition["value"], 16) if condition["value"].startswith("0x") else int(condition["value"])
        return actual == expected if condition["operator"] == "eq" else actual <= expected
    function = condition["abi"][0]
    signature = f"{function['name']}({','.join(_abi_type(item) for item in function['inputs'])})"
    if transaction["data"][:10] != "0x" + keccak(text=signature)[:4].hex():
        return False
    if condition["field"] == "function_name":
        return condition["value"] == function["name"]
    argument = [item["name"] for item in function["inputs"]].index(condition["field"].split(".")[1])
    word = transaction["data"][10 + 64 * argument: 10 + 64 * (argument + 1)]
    if function["inputs"][argument]["type"] == "address":
        return ("0x" + word[-40:]).lower() == condition["value"].lower()
    return int(word, 16) <= int(condition["value"], 16)


def _abi_type(item: dict) -> str:
    if item["type"] == "tuple":
        return "(" + ",".join(_abi_type(part) for part in item["components"]) + ")"
    return item["type"]


def _allowed_by_live_rules(transaction: dict) -> bool:
    rules = json.loads(FIXTURE.read_text(encoding="utf-8"))["live_policy"]["rules"]
    return any(all(_condition_holds(condition, transaction) for condition in rule["conditions"]) for rule in rules)


def test_each_expectation_follows_from_the_live_rules() -> None:
    assert _allowed_by_live_rules(_transaction("raw.ctl_allow_revoke_zero"))
    for specimen_id in ("raw.ctl_deny_approve_moe_entrypoint", "raw.ctl_deny_swap_receiver_wallet",
                        "raw.ctl_deny_moe_transfer_sink"):
        assert not _allowed_by_live_rules(_transaction(specimen_id))
    # The expiry row is allowed by every rule; only the past request expiry can refuse it.
    assert _allowed_by_live_rules(_transaction("raw.ctl_deny_expired_request"))


# ---------------------------------------------------------------- the accepted runner runs the packet


def test_the_accepted_runner_runs_every_row_once_in_order(tmp_path: Path) -> None:
    replies = {
        "raw.ctl_allow_revoke_zero": success_reply(),
        "raw.ctl_deny_approve_moe_entrypoint": code_reply(400, "policy_violation"),
        "raw.ctl_deny_swap_receiver_wallet": code_reply(400, "policy_violation"),
        "raw.ctl_deny_moe_transfer_sink": code_reply(400, "policy_violation"),
        "raw.ctl_deny_expired_request": code_reply(400, "request_expired"),
    }
    from scripts.privy_unfunded_proof.actual_runner import run_actual_specimen

    profile = make_profile("raw", decoder_factory=matched_factory, codes=dict(PRIVY_POLICY_CODES))
    store = AttemptStore(tmp_path / "store")
    (tmp_path / "store").mkdir()
    sent: list = []
    with injected(CONTROL_PROOF_PACKET, {actual_packet.UNFUNDED_POLICY_PROFILE_ID: profile}):
        for specimen_id in CONTROL_PROOF_ORDER:
            class _Transport:
                def binding(self, specimen_id: str = specimen_id) -> dict:
                    return {"method": "POST", "destination": CONTROL_PROOF_PACKET.signing_url,
                            "wallet_id": CONTROL_PROOF_PACKET.wallet_id, "app_id": CONTROL_PROOF_PACKET.app_id,
                            "request_id": CONTROL_PROOF_PACKET.attempt_identity_for(specimen_id),
                            "request_expiry_ms": int(CONTROL_PROOF_PACKET.auth_header_expiry)}

                def send(self, request, specimen_id: str = specimen_id):  # noqa: ANN001
                    sent.append(request)
                    return replies[specimen_id]

            result = run_actual_specimen(specimen_id, store=store, transport=_Transport(),
                                         packet_id=CONTROL_PROOF_PACKET.packet_id,
                                         profile_id=actual_packet.UNFUNDED_POLICY_PROFILE_ID,
                                         clock=lambda: "2026-10-24T00:00:00Z", now_epoch=NOW,
                                         started_at_epoch=NOW, table=CONTROL_PROOF_TABLE)
            assert result.matches_expectation, specimen_id
    assert [request.request_sha256 for request in sent] == [
        CONTROL_PROOF_PACKET.requests[specimen_id].request_sha256 for specimen_id in CONTROL_PROOF_ORDER]
    expired = store.read_outcome("raw.ctl_deny_expired_request")
    assert expired["outcome"] == "UNKNOWN" and expired["reason"] == "EXPIRY_REFUSAL"
    assert not store.is_stopped()


def test_a_signed_expiry_row_is_a_breach(tmp_path: Path) -> None:
    from scripts.privy_unfunded_proof.actual_runner import run_actual_specimen

    profile = make_profile("raw", decoder_factory=matched_factory, codes=dict(PRIVY_POLICY_CODES))
    (tmp_path / "store").mkdir()
    store = AttemptStore(tmp_path / "store")
    with injected(CONTROL_PROOF_PACKET, {actual_packet.UNFUNDED_POLICY_PROFILE_ID: profile}):
        for specimen_id, reply in (("raw.ctl_allow_revoke_zero", success_reply()),
                                   ("raw.ctl_deny_expired_request", success_reply())):
            class _Transport:
                def binding(self, specimen_id: str = specimen_id) -> dict:
                    return {"method": "POST", "destination": CONTROL_PROOF_PACKET.signing_url,
                            "wallet_id": CONTROL_PROOF_PACKET.wallet_id, "app_id": CONTROL_PROOF_PACKET.app_id,
                            "request_id": CONTROL_PROOF_PACKET.attempt_identity_for(specimen_id),
                            "request_expiry_ms": int(CONTROL_PROOF_PACKET.auth_header_expiry)}

                def send(self, request, reply=reply):  # noqa: ANN001
                    return reply

            result = run_actual_specimen(specimen_id, store=store, transport=_Transport(),
                                         packet_id=CONTROL_PROOF_PACKET.packet_id,
                                         profile_id=actual_packet.UNFUNDED_POLICY_PROFILE_ID,
                                         clock=lambda: "2026-10-24T00:00:00Z", now_epoch=NOW,
                                         started_at_epoch=NOW, table=CONTROL_PROOF_TABLE)
    assert result.outcome.value == "BREACH" and store.is_stopped()


# ---------------------------------------------------------------- operator command


def test_dry_run_lists_the_control_packet(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class _FrozenTime:
        @staticmethod
        def time() -> int:
            return NOW

    monkeypatch.setattr(actual_run, "time", _FrozenTime)
    assert actual_run.main(["--dry-run", "--packet", "control-proofs"]) == 0
    out = capsys.readouterr().out
    assert f"packet={CONTROL_PROOF_PACKET.packet_id}" in out
    for specimen_id in CONTROL_PROOF_ORDER:
        assert specimen_id in out
    assert actual_run.main(["--dry-run"]) == 0
    assert f"packet={UNFUNDED_POLICY_PACKET.packet_id}" in capsys.readouterr().out


def test_live_control_run_keeps_the_unfunded_confirmation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "store"
    assert actual_run.main(["--packet", "control-proofs", "--store", str(store)]) == 2
    assert not store.exists()
    assert "UNFUNDED_CONFIRMATION_REQUIRED" in capsys.readouterr().out


def test_an_expected_expiry_refusal_does_not_stop_the_command() -> None:
    from scripts.privy_unfunded_proof.evidence import Outcome, RunResult

    matched = RunResult("raw.ctl_deny_expired_request", "raw", "EXPIRY_REFUSAL", Outcome.UNKNOWN,
                        "EXPIRY_REFUSAL", True, "LOCAL_TESTED", "UNQUALIFIED")
    lost = RunResult("raw.ctl_deny_expired_request", "raw", "EXPIRY_REFUSAL", Outcome.UNKNOWN,
                     "SEND_LOST", False, "LOCAL_TESTED", "UNQUALIFIED")
    assert actual_run.should_stop(matched) is False
    assert actual_run.should_stop(lost) is True
    assert actual_run.should_stop(dataclasses.replace(matched, outcome=Outcome.BREACH)) is True
