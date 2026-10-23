"""Local-only Privy server-wallet binding: one read-only wallet read, exact release match, fail closed.

These controls make no network, provider or credential call. They use the authored A2 release file and
fake HTTP or socket replies only.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from edge_os_api.core.settings import ConfigError, load_settings
from edge_os_api.wallet_setup.adapter import (PRIVY_SERVER_MODE, PrivyServerWalletProvider,
                                             UnavailableWalletProvider, build_wallet_provider, provider_info)
from edge_os_api.wallet_setup.provider import WalletEvidence, WalletProviderUnavailable

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "privy_wallet_lookup"))
import lookup_server  # noqa: E402

RELEASE_PATH = REPO / "docs" / "qualification" / "inapp-trade" / "release.authored.json"
WID = "bsb2feecuxl81dl5jz4u9xxo"
ADDR = "0x91BB52A63c91986813288965e4681FF111De1b63"
SIGNER = "zu1qjdfqlbcq1ct7sdxendgg"
POLICY = "c30racyru6duaipj815cvjce"
POLICY_OWNER = "a5gwmgrsn6903ac09lphyv9a"
HASH = "ab" * 32
OWNER = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _release_document() -> dict:
    return json.loads(RELEASE_PATH.read_text(encoding="utf-8"))


def _release() -> object:
    return lookup_server.load_server_wallet_release(_release_document())


def _record(**overrides: object) -> dict:
    record = {"id": WID, "address": ADDR, "chain_type": "ethereum", "policy_ids": [POLICY],
              "owner_id": POLICY_OWNER,
              "additional_signers": [{"signer_id": SIGNER, "override_policy_ids": [POLICY]}],
              "created_at": 1741834854578, "entity": {"id": "user-1", "type": "user"},
              "external_id": None, "display_name": None, "exported_at": None, "imported_at": None}
    record.update(overrides)
    return record


# Privy wallet read: GET-only, fixed path -------------------------------------------------------------------------


def test_wallet_by_id_uses_one_fixed_get_and_refuses_an_invalid_id():
    reader = lookup_server.PrivyUserReader("app-id-fake", "fake-secret-value")
    seen: list[tuple[str, str, bytes | None, dict[str, str] | None]] = []

    def fetch(method: str, path: str, body: bytes | None, extra: dict[str, str] | None = None) -> object:
        seen.append((method, path, body, extra))
        return {"id": WID}

    reader._fetch = fetch  # type: ignore[method-assign]
    assert reader.wallet_by_id(WID) == {"id": WID}
    assert seen == [("GET", "/v1/wallets/" + WID, None, None)]
    for bad in ("", "bad id", "../wallets", "x" * 129):
        assert reader.wallet_by_id(bad) is None
    assert len(seen) == 1


def test_wallet_read_has_no_create_or_sign_operation():
    assert not hasattr(lookup_server.PrivyUserReader, "create_wallet")
    assert not hasattr(lookup_server.PrivyUserReader, "sign")
    assert lookup_server.WALLET_BY_ID == "https://api.privy.io/v1/wallets/"


# Release binding ------------------------------------------------------------------------------------------------


def test_authored_a2_release_loads_exact_wallet_signer_and_policy():
    release = _release()
    assert (release.wallet_id, release.address, release.signer_id, release.policy_id, release.policy_owner_id) == (
        WID, ADDR, SIGNER, POLICY, POLICY_OWNER)
    canonical = json.dumps({"release_id": "actual-inapp-wmon-moe-20261022/1", "chain_id": 143,
                            "wallet_id": WID, "wallet_address": ADDR.lower(), "chain_type": "ethereum",
                            "signer_id": SIGNER, "policy_id": POLICY, "policy_owner_id": POLICY_OWNER},
                           sort_keys=True, separators=(",", ":")).encode("ascii")
    import hashlib
    assert release.binding_sha256 == hashlib.sha256(canonical).hexdigest()


@pytest.mark.parametrize("key", ["wallet_id", "wallet_address", "signer_id", "policy_id", "policy_owner_id"])
def test_release_refuses_a_missing_bound_field(key):
    document = _release_document()
    del document["release"][key]
    with pytest.raises(ValueError):
        lookup_server.load_server_wallet_release(document)


@pytest.mark.parametrize("key,value", [
    ("release_id", ""), ("release_id", None), ("wallet_id", ""), ("wallet_id", "bad id"),
    ("wallet_address", "0x12"), ("signer_id", ""), ("policy_id", ""), ("policy_owner_id", ""),
    ("chain_id", 10143), ("kind", "SYNTHETIC"),
])
def test_release_refuses_wrong_identity_or_network(key, value):
    document = _release_document()
    document["release"][key] = value
    with pytest.raises(ValueError):
        lookup_server.load_server_wallet_release(document)


def test_release_refuses_missing_release_or_wrong_schema():
    for document in ({}, {"schema": "other", "release": _release_document()["release"]},
                     {"schema": "edge-os.inapp-trade-authoring/1"}, None, []):
        with pytest.raises(ValueError):
            lookup_server.load_server_wallet_release(document)


def test_binding_hash_changes_with_every_bound_field():
    base = _release().binding_sha256
    for key, value in (("release_id", "other-release/1"), ("wallet_id", "other-wallet"),
                       ("wallet_address", "0x" + "cd" * 20), ("signer_id", "other-signer"),
                       ("policy_id", "other-policy"), ("policy_owner_id", "other-owner")):
        document = _release_document()
        document["release"][key] = value
        assert lookup_server.load_server_wallet_release(document).binding_sha256 != base


# Exact record match -----------------------------------------------------------------------------------------------


def test_exact_wallet_record_matches_the_release():
    release = _release()
    matched = lookup_server.match_server_wallet(_record(), release)
    assert matched == {"wallet_id": WID, "address": ADDR, "chain_type": "ethereum",
                       "release_binding_sha256": release.binding_sha256}


def test_recorded_live_signer_shape_matches():
    """The recorded creation state in PRIVY_SETUP1.json carries the signer override policy."""
    record = _record()
    record["additional_signers"] = [{"signer_id": SIGNER, "override_policy_ids": [POLICY]}]
    assert lookup_server.match_server_wallet(record, _release()) is not None


def test_optional_export_and_import_timestamps_must_be_null():
    assert lookup_server.match_server_wallet(_record(exported_at=None, imported_at=None), _release()) is not None
    for key in ("exported_at", "imported_at"):
        assert lookup_server.match_server_wallet(_record(**{key: 1}), _release()) is None


@pytest.mark.parametrize("record", [
    None, [], "wallet", {},
    {**_record(), "id": "other-wallet"},
    {**_record(), "address": "0x" + "cd" * 20},
    {**_record(), "chain_type": "solana"},
    {**_record(), "policy_ids": []},
    {**_record(), "policy_ids": [POLICY, "extra-policy"]},
    {**_record(), "policy_ids": POLICY},
    {**_record(), "owner_id": None},
    {**_record(), "owner_id": "other-owner"},
    {**_record(), "additional_signers": []},
    {**_record(), "additional_signers": [{"signer_id": "other-signer"}]},
    {**_record(), "additional_signers": [{"signer_id": SIGNER}]},
    {**_record(), "additional_signers": [{"signer_id": SIGNER, "override_policy_ids": []}]},
    {**_record(), "additional_signers": [{"signer_id": SIGNER, "override_policy_ids": ["other-policy"]}]},
    {**_record(), "additional_signers": [{"signer_id": SIGNER,
                                          "override_policy_ids": [POLICY, "other-policy"]}]},
    {**_record(), "additional_signers": [{"signer_id": SIGNER, "override_policy_ids": POLICY}]},
    {**_record(), "additional_signers": [{"signer_id": SIGNER, "override_policy_ids": [POLICY],
                                          "extra": "x"}]},
    {**_record(), "additional_signers": [{"signer_id": SIGNER, "override_policy_ids": [POLICY]},
                                         {"signer_id": "other-signer", "override_policy_ids": [POLICY]}]},
    {**_record(), "additional_signers": ["signer"]},
    {**_record(), "created_at": "yesterday"},
    {**_record(), "entity": "user"},
    {**_record(), "entity": {"id": "user-1"}},
    {**_record(), "external_id": 7},
    {**_record(), "display_name": 7},
    {**_record(), "exported_at": 1},
    {**_record(), "imported_at": 1},
    {key: value for key, value in _record().items() if key != "owner_id"},
    {key: value for key, value in _record().items() if key != "additional_signers"},
    {**_record(), "unknown_field": True},
])
def test_partial_or_mismatched_record_never_matches(record):
    assert lookup_server.match_server_wallet(record, _release()) is None


# Lookup operation ------------------------------------------------------------------------------------------------


def test_bind_operation_answers_only_an_exact_match():
    release = _release()
    calls: list[str] = []

    def fetch(wallet_id: str) -> object:
        calls.append(wallet_id)
        return _record()

    reply = lookup_server.answer_server_wallet({"op": "bind_server_wallet"}, fetch, release)
    assert reply == {"status": "matched", "wallet_id": WID, "address": ADDR, "chain_type": "ethereum",
                     "release_binding_sha256": release.binding_sha256}
    assert calls == [WID]
    for message in ({"op": "lookup_embedded_wallet"}, {"op": "bind_server_wallet", "wallet_id": WID}, {}):
        assert lookup_server.answer_server_wallet(message, fetch, release)["status"] == "unknown"
    assert calls == [WID]
    assert lookup_server.answer_server_wallet({"op": "bind_server_wallet"}, fetch, None)["status"] == "unknown"
    assert calls == [WID]
    assert lookup_server.answer({"op": "bind_server_wallet"},
                                lambda did: None)["status"] == "unknown"


def test_bind_operation_refuses_missing_or_mismatched_provider_record():
    release = _release()
    assert lookup_server.answer_server_wallet({"op": "bind_server_wallet"}, lambda wallet_id: None, release) == {
        "status": "unknown", "reason": "LOOKUP_UNAVAILABLE"}
    assert lookup_server.answer_server_wallet(
        {"op": "bind_server_wallet"}, lambda wallet_id: _record(id="other-wallet"), release) == {
        "status": "unknown", "reason": "NO_EXACT_MATCH"}


def test_bind_operation_maps_a_provider_failure_to_unknown():
    def boom(wallet_id: str) -> object:
        raise OSError("provider body must not escape")

    reply = lookup_server.answer_server_wallet({"op": "bind_server_wallet"}, boom, _release())
    assert reply == {"status": "unknown", "reason": "LOOKUP_FAILED"}
    assert "provider body" not in json.dumps(reply)


# API provider ---------------------------------------------------------------------------------------------------


def _matched_reply() -> dict:
    return {"status": "matched", "wallet_id": WID, "address": ADDR, "chain_type": "ethereum",
            "release_binding_sha256": HASH}


def _provider(reply: dict | Exception, *, owned: bool = False) -> PrivyServerWalletProvider:
    provider = PrivyServerWalletProvider("/tmp/unused.sock")
    if owned:
        provider._owners[WID] = OWNER

    def ask(request: dict) -> dict:
        assert request == {"op": "bind_server_wallet"}
        if isinstance(reply, Exception):
            raise reply
        return reply

    provider._ask = ask  # type: ignore[method-assign]
    return provider


def _create(provider: PrivyServerWalletProvider) -> WalletEvidence | None:
    from types import SimpleNamespace
    return provider.create_wallet(SimpleNamespace(owner_id=OWNER))  # type: ignore[arg-type]


def test_provider_binds_only_the_exact_matched_reply():
    evidence = _create(_provider(_matched_reply()))
    assert evidence is not None
    assert (evidence.wallet_id, evidence.owner_id, evidence.chain_type, evidence.address,
            evidence.release_binding_sha256) == (WID, OWNER, "ethereum", ADDR, HASH)
    looked_up = _provider(_matched_reply(), owned=True).lookup_wallet(WID)
    assert looked_up is not None and looked_up.wallet_id == WID


@pytest.mark.parametrize("reply", [
    {"status": "unknown", "reason": "NO_EXACT_MATCH"}, {},
    {**_matched_reply(), "chain_type": "solana"},
    {**_matched_reply(), "release_binding_sha256": "bad"},
    {**_matched_reply(), "release_binding_sha256": "AB" * 32},
    {**_matched_reply(), "release_binding_sha256": None},
    {key: value for key, value in _matched_reply().items() if key != "release_binding_sha256"},
    {**_matched_reply(), "extra": "x"},
])
def test_provider_refuses_a_partial_or_mismatched_reply(reply):
    with pytest.raises(WalletProviderUnavailable):
        _create(_provider(reply))
    assert _provider(reply, owned=True).lookup_wallet(WID) is None


def test_provider_refuses_a_second_owner_for_the_same_server_wallet():
    from types import SimpleNamespace
    provider = _provider(_matched_reply())
    assert _create(provider) is not None
    with pytest.raises(WalletProviderUnavailable):
        provider.create_wallet(SimpleNamespace(owner_id=uuid.uuid4()))  # type: ignore[arg-type]
    looked_up = provider.lookup_wallet(WID)
    assert looked_up is not None and looked_up.owner_id == OWNER


def test_provider_lookup_requires_the_exact_requested_wallet_id():
    assert _provider(_matched_reply(), owned=True).lookup_wallet("other-wallet") is None
    assert _provider(_matched_reply(), owned=True).lookup_wallet("bad id") is None


def test_provider_transport_failure_is_unavailable_or_no_match():
    with pytest.raises(WalletProviderUnavailable):
        _create(_provider(WalletProviderUnavailable()))
    assert _provider(WalletProviderUnavailable(), owned=True).lookup_wallet(WID) is None
    assert _provider(OSError("socket failed"), owned=True).lookup_wallet(WID) is None


def test_build_selects_the_server_provider_only_with_a_private_socket(monkeypatch):
    monkeypatch.setenv("EDGE_OS_PRIVY_SERVER_SOCKET", "/tmp/edge/l.sock")
    provider = build_wallet_provider(PRIVY_SERVER_MODE)
    assert isinstance(provider, PrivyServerWalletProvider)
    assert provider_info(provider) == {"provider": "privy_server", "create_calls": None, "lookup_calls": None}
    monkeypatch.delenv("EDGE_OS_PRIVY_SERVER_SOCKET")
    assert isinstance(build_wallet_provider(PRIVY_SERVER_MODE), UnavailableWalletProvider)
    for bad in ("relative.sock", "/tmp/../x.sock", "/" + "x" * 120):
        assert isinstance(build_wallet_provider(PRIVY_SERVER_MODE, socket_path=bad), UnavailableWalletProvider)
    assert isinstance(build_wallet_provider("anything-else"), UnavailableWalletProvider)


# Settings -------------------------------------------------------------------------------------------------------


def _env(**extra: str) -> dict[str, str]:
    pem = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return {"EDGE_OS_ENV": "local", "EDGE_OS_DATABASE_URL": "postgresql+psycopg://u@127.0.0.1/edge_os_test_x",
            "EDGE_OS_PRIVY_APP_ID": "fake-app", "EDGE_OS_PRIVY_VERIFICATION_KEY": pem,
            "EDGE_OS_CORS_ALLOWED_ORIGINS": "http://localhost:3000", **extra}


def test_privy_server_provider_is_local_only_and_needs_no_lookup_socket():
    assert load_settings(_env(EDGE_OS_WALLET_PROVIDER="privy_server")).wallet_provider == "privy_server"
    production = {**_env(), "EDGE_OS_ENV": "production", "EDGE_OS_PRIVY_APP_ID": "real-app",
                  "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.example.com",
                  "EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@db.internal/edge?sslmode=require",
                  "EDGE_OS_BUILD_SHA": "0" * 40, "EDGE_OS_WALLET_PROVIDER": "privy_server"}
    with pytest.raises(ConfigError, match="wallet_provider"):
        load_settings(production)
    with pytest.raises(ConfigError, match="wallet_lookup_socket"):
        load_settings(_env(EDGE_OS_WALLET_PROVIDER="privy_server", EDGE_OS_WALLET_LOOKUP_SOCKET="/tmp/l.sock"))
