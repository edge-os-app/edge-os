"""Frozen policy-layer packet for the real Privy policy c30racyru6duaipj815cvjce.

These tests bind the exact packet, table, profile and operator command. They make
no network call and read no credential. The packet is the only code-owned
approval; every other packet must still refuse.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from scripts.privy_unfunded_proof import actual_packet, actual_profile, actual_run, specimens
from scripts.privy_unfunded_proof.actual_packet import (
    CODE_OWNED_PACKET_APPROVALS,
    POLICY_LAYER_CONTROLS,
    UNFUNDED_POLICY_ORDER,
    UNFUNDED_POLICY_PACKET,
    UNFUNDED_POLICY_TABLE,
    resolve_approved_packet,
)
from scripts.privy_unfunded_proof.specimens import Category, Expected, SpecimenRefused

NOW = 1_790_000_000
MON = 10**18
CAP = 70 * MON

WMON = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"
ENTRYPOINT = "0xb3e6778480b2e488385e8205ea05e20060b813cb"
SINK = "0x000000000000000000000000000000000000dead"
WALLET_ID = "bsb2feecuxl81dl5jz4u9xxo"
WALLET_ADDRESS = "0x91BB52A63c91986813288965e4681FF111De1b63"
APP_ID = "cmuyj4smt00tw0dla2j19tlu7"
POLICY_ID = "c30racyru6duaipj815cvjce"
POLICY_OWNER = "a5gwmgrsn6903ac09lphyv9a"
EXECUTOR = "zu1qjdfqlbcq1ct7sdxendgg"
POLICY_BODY_SHA256 = "61860d201ecd9ce6d92bff5e7c2122b40164ecb69d1fa375738cb67b17b0892b"
V1_PACKET_SHA256 = "5835579cc1a0f1935d3e9b0c29bf7521d651e30d47e40c79f9cc32f34ebf0edf"
V2_PACKET_SHA256 = "a84440727360ba470055ec387fc45f110089da6dedecb93a242c5cdac1c2d496"
SIGNING_URL = f"https://api.privy.io/v1/wallets/{WALLET_ID}/rpc"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
NEW_RECEIVER_ROW = "raw.deny_execute_swap_with_receiver"
RECEIVER_SELECTOR = "0x31343b21"
RECEIVER_SIGNATURE = (
    "executeSwapWithReceiver((address,uint256,address,uint256),"
    "(address,uint256,address,uint256,bool),bytes,address)"
)

EXPECTED_ORDER = (
    "raw.allow_deposit_1_mon",
    "raw.allow_deposit_at_cap",
    "raw.allow_approve_at_cap",
    "raw.allow_swap_zero_value",
    "raw.deny_deposit_wrong_to",
    "raw.deny_deposit_wrong_chain",
    "raw.deny_approve_wrong_chain",
    "raw.deny_swap_wrong_chain",
    "raw.deny_approve_wrong_to",
    "raw.deny_swap_wrong_to",
    "raw.deny_wmon_wrong_function",
    "raw.deny_entrypoint_wrong_function",
    NEW_RECEIVER_ROW,
    "raw.deny_approve_other_spender",
    "raw.deny_approve_above_cap",
    "raw.deny_approve_with_value",
    "raw.deny_deposit_above_cap",
    "raw.deny_plain_mon_transfer",
    "raw.deny_swap_with_mon",
)
EXPECTED_ALLOW = frozenset({
    "raw.allow_deposit_1_mon",
    "raw.allow_deposit_at_cap",
    "raw.allow_approve_at_cap",
    "raw.allow_swap_zero_value",
})


def _transaction(specimen_id: str) -> dict:
    body = json.loads(UNFUNDED_POLICY_PACKET.requests[specimen_id].body)
    return body["params"]["transaction"]


def _logical_value(specimen_id: str) -> int:
    value = _transaction(specimen_id)["value"]
    return int(value, 16) if isinstance(value, str) else value


# ---------------------------------------------------------------- registry and admission


def test_registry_holds_the_frozen_packet_and_the_control_packet() -> None:
    # The control-proof packet (test_control_proof_packet.py) is the only other sealed entry.
    assert list(CODE_OWNED_PACKET_APPROVALS) == [actual_packet.SEALED_PACKET_SHA256,
                                                 actual_packet.SEALED_CONTROL_PROOF_PACKET_SHA256]
    assert CODE_OWNED_PACKET_APPROVALS[actual_packet.SEALED_PACKET_SHA256] is UNFUNDED_POLICY_PACKET
    assert list(actual_profile.QUALIFIED_ACTUAL_PROFILES) == [actual_packet.UNFUNDED_POLICY_PROFILE_ID]
    assert actual_profile.QUALIFIED_ACTUAL_PROFILES[actual_packet.UNFUNDED_POLICY_PROFILE_ID].profile == "raw"


def test_unknown_packet_still_refuses() -> None:
    with pytest.raises(SpecimenRefused) as caught:
        resolve_approved_packet("0" * 64, now_epoch=NOW)
    assert caught.value.code == "ACTUAL_PACKET_NOT_APPROVED"


def test_registered_packet_admits_with_its_table() -> None:
    packet = resolve_approved_packet(UNFUNDED_POLICY_PACKET.packet_id, now_epoch=NOW,
                                     table=UNFUNDED_POLICY_TABLE)
    assert packet is UNFUNDED_POLICY_PACKET


def test_packet_hash_is_stable_and_self_bound() -> None:
    assert UNFUNDED_POLICY_PACKET.packet_id == UNFUNDED_POLICY_PACKET.packet_sha256()
    assert UNFUNDED_POLICY_PACKET.packet_id == actual_packet.SEALED_PACKET_SHA256
    assert len(UNFUNDED_POLICY_PACKET.packet_id) == 64


def test_a_changed_packet_field_is_not_admitted() -> None:
    tampered = dataclasses.replace(UNFUNDED_POLICY_PACKET, packet_id="",
                                   attempt_identity="unfunded-policy-proof-4")
    tampered = dataclasses.replace(tampered, packet_id=tampered.packet_sha256())
    assert tampered.packet_id != actual_packet.SEALED_PACKET_SHA256
    assert actual_packet._sealed_packet_registry(tampered, actual_packet.SEALED_PACKET_SHA256) == {}
    with pytest.raises(SpecimenRefused) as caught:
        resolve_approved_packet(tampered.packet_id, now_epoch=NOW)
    assert caught.value.code == "ACTUAL_PACKET_NOT_APPROVED"


def test_v1_and_v2_packets_are_refused_and_their_attempt_identities_are_not_reused() -> None:
    for refused_packet in (V1_PACKET_SHA256, V2_PACKET_SHA256):
        assert UNFUNDED_POLICY_PACKET.packet_id != refused_packet
        with pytest.raises(SpecimenRefused) as caught:
            resolve_approved_packet(refused_packet, now_epoch=NOW, table=UNFUNDED_POLICY_TABLE)
        assert caught.value.code == "ACTUAL_PACKET_NOT_APPROVED"
    assert UNFUNDED_POLICY_PACKET.attempt_identity == "unfunded-policy-proof-3"
    for specimen_id in UNFUNDED_POLICY_ORDER:
        attempt = UNFUNDED_POLICY_PACKET.attempt_identity_for(specimen_id)
        assert attempt.startswith("unfunded-policy-proof-3:")
        assert not attempt.startswith(("unfunded-policy-proof-1:", "unfunded-policy-proof-2:"))


def test_fixture_matches_the_saved_live_result_when_present() -> None:
    workspace_root = Path(__file__).resolve().parents[2].parents[2]
    source = workspace_root / ".scratch/trade-prep-20261021/R3_TIGHTEN1_RESULT.json"
    if not source.exists():
        pytest.skip("the private saved live result is not in this checkout")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        "a9276df89ff59f12c5380f981218275f2c0333fedbd26c70eabcf87a4a045a2c"
    )
    saved = json.loads(source.read_text(encoding="utf-8"))
    fixture = json.loads((FIXTURE_DIR / "policy_v2_live_rules.json").read_text(encoding="utf-8"))
    assert fixture["live_policy"]["rules"] == saved["live_policy"]["rules"]


def test_policy_body_hash_derives_from_the_saved_live_v2_rules() -> None:
    saved = json.loads((FIXTURE_DIR / "policy_v2_live_rules.json").read_text(encoding="utf-8"))
    live_rules = saved["live_policy"]["rules"]
    assert saved["source_sha256"] == "a9276df89ff59f12c5380f981218275f2c0333fedbd26c70eabcf87a4a045a2c"
    assert [rule["id"] for rule in live_rules] == [
        "e2qc2t0a9c4vfiy7r8p1v7g4",
        "d0ylb7k5f5afi0itijxypjrl",
        "osinqlsjmm9q8lnej21q4mbe",
    ]
    assert any(character.isupper() for rule in live_rules for character in json.dumps(rule))
    assert actual_packet.policy_body_sha256(live_rules) == POLICY_BODY_SHA256
    assert UNFUNDED_POLICY_PACKET.profile_policy_sha256 == {"raw": POLICY_BODY_SHA256}


def test_live_policy_normalization_is_required() -> None:
    raw = json.loads((FIXTURE_DIR / "policy_v2_live_rules.json").read_text(encoding="utf-8"))["live_policy"]["rules"]
    unnormalized = actual_packet.canonical_json({"rules": raw})
    assert hashlib.sha256(unnormalized).hexdigest() != POLICY_BODY_SHA256
    normalized = actual_packet.normalize_live_policy_rules(raw)
    assert all("id" not in rule for rule in normalized)
    assert actual_packet.canonical_json({"rules": normalized}) != unnormalized


def test_r3_text_is_the_tightened_execute_swap_only_rule() -> None:
    saved = json.loads((FIXTURE_DIR / "policy_v2_live_rules.json").read_text(encoding="utf-8"))
    live_rules = saved["live_policy"]["rules"]
    fn = next(condition for condition in live_rules[2]["conditions"] if condition["field"] == "function_name")
    assert fn["operator"] == "eq"
    assert fn["value"] == "executeSwap"
    assert [abi["name"] for abi in fn["abi"]] == ["executeSwap"]


def test_a_changed_table_row_is_not_admitted() -> None:
    rows = list(UNFUNDED_POLICY_TABLE.all())
    rows[-1] = dataclasses.replace(rows[-1], expected=Expected.ALLOW)
    tampered = specimens.build_table(rows)
    assert tampered.manifest_sha256 != actual_packet.SEALED_ACTUAL_MANIFEST_SHA256
    assert not tampered.matches_actual_manifest()


def test_packet_binds_the_real_identities() -> None:
    packet = UNFUNDED_POLICY_PACKET
    assert packet.app_id == APP_ID
    assert packet.executor_id == EXECUTOR
    assert packet.owner_id == POLICY_OWNER
    assert packet.policy_resource_owner_id == POLICY_OWNER
    assert packet.wallet_id == WALLET_ID
    assert packet.wallet_address == WALLET_ADDRESS
    assert packet.network_id == "eip155:143"
    assert packet.chain_id == 143
    assert packet.signing_url == SIGNING_URL
    assert packet.signing_method == "eth_signTransaction"
    assert packet.profile_policies == {"raw": POLICY_ID}
    assert packet.profile_policy_sha256 == {"raw": POLICY_BODY_SHA256}


def test_policy_owner_is_outside_executor_control() -> None:
    assert UNFUNDED_POLICY_PACKET.policy_resource_owner_id != UNFUNDED_POLICY_PACKET.executor_id
    assert UNFUNDED_POLICY_PACKET.policy_resource_owner_id == UNFUNDED_POLICY_PACKET.owner_id


def test_packet_uses_only_the_raw_profile() -> None:
    assert set(UNFUNDED_POLICY_PACKET.profile_policies) == {"raw"}
    assert {row.profile for row in UNFUNDED_POLICY_TABLE.all()} == {"raw"}


def test_policy_layer_scope_keeps_out_of_scope_controls_honest() -> None:
    assert UNFUNDED_POLICY_PACKET.proof_scope == "POLICY_LAYER"
    for name in POLICY_LAYER_CONTROLS:
        assert UNFUNDED_POLICY_PACKET.controls[name] not in actual_packet.BLOCKING_CONTROL_STATES
    assert UNFUNDED_POLICY_PACKET.controls["opaque_program"] is actual_packet.ControlState.UNKNOWN
    assert UNFUNDED_POLICY_PACKET.controls["gas_action_capacity"] is actual_packet.ControlState.UNSET
    assert UNFUNDED_POLICY_PACKET.position_inventory is actual_packet.ControlState.UNSUPPORTED


def test_actual_manifest_registry_holds_the_policy_and_control_tables() -> None:
    assert specimens.CODE_OWNED_ACTUAL_MANIFESTS == frozenset({
        actual_packet.SEALED_ACTUAL_MANIFEST_SHA256, actual_packet.SEALED_CONTROL_PROOF_MANIFEST_SHA256})
    assert UNFUNDED_POLICY_TABLE.manifest_sha256 == actual_packet.SEALED_ACTUAL_MANIFEST_SHA256
    assert UNFUNDED_POLICY_TABLE.matches_actual_manifest()
    tampered = dataclasses.replace(UNFUNDED_POLICY_TABLE, manifest_sha256="deadbeef")
    assert not tampered.matches_actual_manifest()


# ---------------------------------------------------------------- order and expected table


def test_order_is_the_frozen_order_and_starts_with_the_positive_control() -> None:
    assert UNFUNDED_POLICY_ORDER == EXPECTED_ORDER
    assert UNFUNDED_POLICY_ORDER[-2:] == ("raw.deny_plain_mon_transfer", "raw.deny_swap_with_mon")
    first = UNFUNDED_POLICY_TABLE.get(UNFUNDED_POLICY_ORDER[0])
    assert first.category is Category.POSITIVE_CONTROL
    assert first.expected is Expected.ALLOW
    assert first.wallet_id == WALLET_ID


def test_expected_table_matches_every_policy_boundary() -> None:
    for specimen_id in UNFUNDED_POLICY_ORDER:
        row = UNFUNDED_POLICY_TABLE.get(specimen_id)
        expected = Expected.ALLOW if specimen_id in EXPECTED_ALLOW else Expected.POLICY_DENY
        assert row.expected is expected
        assert UNFUNDED_POLICY_PACKET.specimen_expected[specimen_id] == expected.value


def test_negative_set_covers_each_policy_owned_boundary() -> None:
    denied = {sid for sid in UNFUNDED_POLICY_ORDER if sid not in EXPECTED_ALLOW}
    assert "raw.deny_deposit_wrong_chain" in denied
    assert "raw.deny_approve_wrong_chain" in denied
    assert "raw.deny_swap_wrong_chain" in denied
    assert "raw.deny_deposit_wrong_to" in denied
    assert "raw.deny_approve_wrong_to" in denied
    assert "raw.deny_swap_wrong_to" in denied
    assert "raw.deny_wmon_wrong_function" in denied
    assert "raw.deny_entrypoint_wrong_function" in denied
    assert NEW_RECEIVER_ROW in denied
    assert "raw.deny_approve_other_spender" in denied
    assert "raw.deny_approve_above_cap" in denied
    assert "raw.deny_approve_with_value" in denied
    assert "raw.deny_deposit_above_cap" in denied
    assert "raw.deny_swap_with_mon" in denied
    assert "raw.deny_plain_mon_transfer" in denied


# ---------------------------------------------------------------- exact request bodies


def test_every_request_uses_the_single_wallet_route_and_a_type_2_body() -> None:
    for specimen_id in UNFUNDED_POLICY_ORDER:
        request = UNFUNDED_POLICY_PACKET.requests[specimen_id]
        assert request.url == SIGNING_URL
        assert request.http_method == "POST"
        body = json.loads(request.body)
        assert set(body) == {"method", "params"}
        assert body["method"] == "eth_signTransaction"
        assert set(body["params"]) == {"transaction"}
        transaction = body["params"]["transaction"]
        assert set(transaction) == {
            "type", "chain_id", "nonce", "to", "value", "data", "gas_limit",
            "max_fee_per_gas", "max_priority_fee_per_gas",
        }
        assert transaction["type"] == 2
        assert transaction["nonce"] == 0
        expected_gas = 500_000 if "swap" in specimen_id else 100_000
        assert transaction["gas_limit"] == expected_gas
        assert transaction["max_fee_per_gas"] == 100_000_000_000
        assert transaction["max_priority_fee_per_gas"] == 2_000_000_000


def test_exact_chain_values() -> None:
    for specimen_id in UNFUNDED_POLICY_ORDER:
        transaction = _transaction(specimen_id)
        if "wrong_chain" in specimen_id:
            assert transaction["chain_id"] == 10143
        else:
            assert transaction["chain_id"] == 143


def test_exact_deposit_values() -> None:
    assert _logical_value("raw.allow_deposit_1_mon") == MON
    assert _logical_value("raw.allow_deposit_at_cap") == CAP
    assert _logical_value("raw.deny_deposit_above_cap") == CAP + 1
    assert _transaction("raw.deny_deposit_wrong_to")["to"] == SINK
    assert _transaction("raw.deny_deposit_wrong_chain")["to"] == WMON


def test_large_deposit_values_are_canonical_hex_on_the_wire() -> None:
    for specimen_id, value in (
        ("raw.allow_deposit_1_mon", MON),
        ("raw.allow_deposit_at_cap", CAP),
        ("raw.deny_deposit_above_cap", CAP + 1),
    ):
        wire = _transaction(specimen_id)["value"]
        assert wire == hex(value)
        assert wire == wire.lower()
        assert int(wire, 16) == value


def test_exact_approve_values() -> None:
    approve = "0x095ea7b3"
    for specimen_id in ("raw.allow_approve_at_cap", "raw.deny_approve_other_spender",
                        "raw.deny_approve_above_cap", "raw.deny_approve_with_value"):
        data = _transaction(specimen_id)["data"]
        assert data.startswith(approve)
        assert len(data) == 2 + 8 + 64 + 64
    assert _transaction("raw.allow_approve_at_cap")["data"].endswith(f"{CAP:064x}")
    assert _transaction("raw.deny_approve_above_cap")["data"].endswith(f"{CAP + 1:064x}")
    assert _transaction("raw.deny_approve_other_spender")["data"][10:74] == "0" * 24 + SINK[2:]
    assert _transaction("raw.deny_approve_with_value")["value"] == 1


def test_execute_swap_selector_matches_the_policy_abi() -> None:
    from eth_utils import keccak

    signature = ("executeSwap((address,uint256,address,uint256),"
                 "(address,uint256,address,uint256,bool),bytes)")
    assert keccak(text=signature)[:4].hex() == actual_packet.EXECUTE_SWAP_SELECTOR[2:]
    assert actual_packet.EXECUTE_SWAP_SELECTOR == "0xce1e7030"


def test_execute_swap_with_receiver_selector_matches_the_full_signature() -> None:
    from eth_utils import keccak

    assert keccak(text=RECEIVER_SIGNATURE)[:4].hex() == RECEIVER_SELECTOR[2:]
    assert actual_packet.EXECUTE_SWAP_WITH_RECEIVER_SELECTOR == RECEIVER_SELECTOR
    assert actual_packet.EXECUTE_SWAP_WITH_RECEIVER_SIGNATURE == RECEIVER_SIGNATURE


def test_exact_swap_values() -> None:
    swap = "0xce1e7030"
    for specimen_id in ("raw.allow_swap_zero_value", "raw.deny_swap_with_mon",
                        "raw.deny_swap_wrong_chain", "raw.deny_swap_wrong_to"):
        transaction = _transaction(specimen_id)
        assert transaction["data"].startswith(swap)
        expected_to = SINK if "wrong_to" in specimen_id else ENTRYPOINT
        assert transaction["to"] == expected_to
    assert _transaction("raw.allow_swap_zero_value")["value"] == 0
    assert _transaction("raw.deny_swap_with_mon")["value"] == 1


def test_exact_execute_swap_with_receiver_negative() -> None:
    transaction = _transaction(NEW_RECEIVER_ROW)
    assert transaction["chain_id"] == 143
    assert transaction["to"] == ENTRYPOINT
    assert transaction["value"] == 0
    assert transaction["gas_limit"] == 500_000
    data = transaction["data"]
    assert data.startswith(RECEIVER_SELECTOR)
    assert data[10 + 9 * 64 : 10 + 10 * 64] == f"{352:064x}"
    assert data[10 + 10 * 64 : 10 + 11 * 64] == "0" * 24 + SINK[2:]
    assert data.endswith("01" + "0" * 62)
    row = UNFUNDED_POLICY_TABLE.get(NEW_RECEIVER_ROW)
    assert row.expected is Expected.POLICY_DENY
    assert UNFUNDED_POLICY_PACKET.specimen_expected[NEW_RECEIVER_ROW] == "POLICY_DENY"
    assert data[10 + 10 * 64 : 10 + 11 * 64] != "0" * 24 + WALLET_ADDRESS[2:].lower()


def test_exact_wrong_function_and_plain_transfer() -> None:
    assert _transaction("raw.deny_wmon_wrong_function")["to"] == WMON
    assert _transaction("raw.deny_wmon_wrong_function")["data"].startswith("0xa9059cbb")
    assert _transaction("raw.deny_entrypoint_wrong_function")["to"] == ENTRYPOINT
    assert _transaction("raw.deny_entrypoint_wrong_function")["data"] == "0xd0e30db0"
    assert _transaction("raw.deny_plain_mon_transfer")["to"] == SINK
    assert _transaction("raw.deny_plain_mon_transfer")["data"] == "0x"
    assert _transaction("raw.deny_plain_mon_transfer")["value"] == 1


def test_every_request_passes_the_accepted_transport_profile() -> None:
    from scripts.privy_unfunded_proof.actual_transport import accepted_request_profile

    for specimen_id in UNFUNDED_POLICY_ORDER:
        body = json.loads(UNFUNDED_POLICY_PACKET.requests[specimen_id].body)
        assert accepted_request_profile(body) is True


def test_every_request_is_within_the_packet_ceilings() -> None:
    assert len(UNFUNDED_POLICY_ORDER) <= UNFUNDED_POLICY_PACKET.request_count_ceiling
    for specimen_id in UNFUNDED_POLICY_ORDER:
        assert len(UNFUNDED_POLICY_PACKET.requests[specimen_id].body) <= UNFUNDED_POLICY_PACKET.request_byte_ceiling


def test_packet_has_no_broadcast_operation() -> None:
    for specimen_id in UNFUNDED_POLICY_ORDER:
        body = json.loads(UNFUNDED_POLICY_PACKET.requests[specimen_id].body)
        assert body["method"] == "eth_signTransaction"
        assert body["method"] != "eth_sendTransaction"


def test_positive_control_value_is_inside_the_policy_cap() -> None:
    assert 0 < _logical_value("raw.allow_deposit_1_mon") <= CAP


# ---------------------------------------------------------------- profile and classifier


def test_profile_classifies_the_documented_policy_violation() -> None:
    profile = actual_profile.QUALIFIED_ACTUAL_PROFILES[actual_packet.UNFUNDED_POLICY_PROFILE_ID]
    assert profile.codes["policy_violation"] == (400, "POLICY_DENY", "PRIVY_POLICY_VIOLATION")
    assert profile.codes["request_expired"] == (400, "UNKNOWN", "EXPIRY_REFUSAL")
    assert profile.codes["zero_correct_authorization_signatures"] == (
        401, "AUTHORIZATION_DENY", "PRIVY_AUTHORIZATION_DENIED",
    )


@pytest.mark.parametrize("body", [
    {"code": "policy_violation"},
    {"error": {"code": "policy_violation"}},
    {"error": "policy_violation"},
])
def test_reply_code_reads_the_flat_and_nested_privy_shapes(body: dict) -> None:
    assert actual_packet.reply_code(body) == "policy_violation"


def test_reply_code_ignores_unknown_shapes() -> None:
    assert actual_packet.reply_code({}) is None
    assert actual_packet.reply_code({"error": {"message": "denied"}}) is None
    assert actual_packet.reply_code(["policy_violation"]) is None


# ---------------------------------------------------------------- operator command


def test_dry_run_lists_every_row_in_order(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _FrozenTime:
        @staticmethod
        def time() -> int:
            return NOW

    monkeypatch.setattr(actual_run, "time", _FrozenTime)
    assert actual_run.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    for specimen_id in UNFUNDED_POLICY_ORDER:
        assert specimen_id in out
    assert len(UNFUNDED_POLICY_ORDER) == 19
    assert out.index(UNFUNDED_POLICY_ORDER[0]) < out.index(UNFUNDED_POLICY_ORDER[-1])
    assert out.index("raw.deny_plain_mon_transfer") < out.index("raw.deny_swap_with_mon")


def test_live_run_requires_unfunded_confirmation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "store"
    assert actual_run.main(["--store", str(store)]) == 2
    assert not store.exists()
    assert "UNFUNDED_CONFIRMATION_REQUIRED" in capsys.readouterr().out


def test_live_run_refuses_an_existing_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "store"
    store.mkdir()
    assert actual_run.main(["--store", str(store), "--confirm-unfunded"]) == 2
    assert "STORE_ALREADY_EXISTS" in capsys.readouterr().out
