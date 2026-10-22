"""The Orbio release draft is a record nothing selects; the adopted OpenRouter release is unchanged (CLOUD-ORBIO-RELEASE).

The draft in docs/qualification/orbio-release/ is read as bytes only. Nothing here opens a socket, reads a key or
contacts Orbio. See `docs/qualification/orbio-release/ORBIO_RELEASE_DRAFT.md`.
"""

from __future__ import annotations

import hashlib
import json
import ssl
from pathlib import Path

import pytest

import relay_admission
from edge_os_api.research import hermes_relay_composition as composition
from relay_admission import ActualReleaseUnapproved, ProviderDestination, load_actual_release

REPO = Path(__file__).resolve().parents[2]
DRAFT = REPO / "docs/qualification/orbio-release"
RECORD = DRAFT / "orbio_draft_record.json"
PACKET = DRAFT / "orbio_draft_packet.json"
PRICES = DRAFT / "orbio_draft_prices.json"
CA = DRAFT / "orbio_ca_isrg_root_x1.pem"
ADOPTED = REPO / "docs/qualification/hermes-actual-operation/release"
ADOPTED_SHA = "3fa94dd73e53a72ca8af6cda9c8633770de89c262fa5303756c1965bb92fed8f"
ISRG_ROOT_X1_DER_SHA256 = "96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6"
# A test-only stand-in. Whether Orbio forwards OpenRouter's routing object is UNKNOWN; the draft names none.
SYNTHETIC_ROUTING = {"only": ["synthetic"], "allow_fallbacks": False, "require_parameters": True,
                     "data_collection": "deny", "max_price": {"prompt": 2, "completion": 10}}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def raw_is_canonical(raw: bytes) -> bool:
    return canonical(json.loads(raw)) == raw


def draft() -> tuple[bytes, dict]:
    raw = RECORD.read_bytes()
    return raw, json.loads(raw)


def test_the_draft_record_is_refused_as_not_approved() -> None:
    raw, _ = draft()
    with pytest.raises(ActualReleaseUnapproved):
        load_actual_release(raw, sha(raw))
    assert sha(raw) not in relay_admission.APPROVED_ACTUAL_RELEASES


def test_even_an_approved_hash_would_not_load_the_draft_because_it_names_no_routing() -> None:
    raw, value = draft()
    assert value["provider"] is None and "provider" not in value["allowed_fields"]
    with pytest.raises(ValueError, match="routing must be an object") as refused:
        load_actual_release(raw, sha(raw), approved=frozenset({sha(raw)}))
    assert not isinstance(refused.value, ActualReleaseUnapproved)


def test_every_other_draft_field_parses_under_the_cloud_02_rules() -> None:
    _, value = draft()
    assert set(value) - {"prompt_cache_options"} == relay_admission.RECORD_FIELDS
    assert raw_is_canonical(RECORD.read_bytes())
    # Only the routing object is swapped for a synthetic one, so the rest meets the loader as written.
    probe = canonical({**value, "provider": SYNTHETIC_ROUTING,
                       "allowed_fields": [*value["allowed_fields"], "provider"]})
    actual = load_actual_release(probe, sha(probe), approved=frozenset({sha(probe)}))
    assert actual.destination == ProviderDestination("api.orbio.so", 443, "/api/v1/chat/completions")
    assert actual.endpoint_url == "https://api.orbio.so/api/v1/chat/completions"
    assert actual.ca_bundle_sha256 == sha(CA.read_bytes())
    assert actual.release.settings() == {
        "release_id": "orbio-draft-1", "route_id": "orbio-openrouter-managed", "kind": "ACTUAL",
        "model": "openai/gpt-6.1-sol", "max_output_tokens": 4096, "max_request_bytes": 65536,
        "max_reply_bytes": 262144}
    assert (actual.reasoning, actual.prompt_cache_options, actual.timeout_seconds) == (
        {"effort": "low"}, {"mode": "explicit"}, 90)


def test_the_draft_hash_chain_names_its_packet_prices_and_ca_bundle() -> None:
    _, value = draft()
    packet = json.loads(PACKET.read_bytes())
    assert value["approval"] == {"path": "docs/qualification/orbio-release/orbio_draft_packet.json",
                                 "sha256": sha(PACKET.read_bytes())}
    assert packet["status"] == "DRAFT_NOT_APPROVED"
    assert packet["record_values_except_approval"] == {k: v for k, v in value.items() if k != "approval"}
    assert value["price_snapshot_sha256"] == sha(PRICES.read_bytes())
    assert json.loads(PRICES.read_bytes()) == {"completion_usd_per_million": "10", "model": "openai/gpt-6.1-sol",
                                               "prompt_usd_per_million": "2", "provider": "orbio"}
    adopted_prices = json.loads((ADOPTED / "hermes_first_call_prices.json").read_bytes())
    assert {k: v for k, v in adopted_prices.items() if k != "provider"} == {
        k: v for k, v in json.loads(PRICES.read_bytes()).items() if k != "provider"}
    assert value["response_format_sha256"] == json.loads(
        (ADOPTED / "hermes_first_call_record.json").read_bytes())["response_format_sha256"]


def test_the_ca_bundle_is_only_isrg_root_x1() -> None:
    text = CA.read_text()
    assert text.count("-----BEGIN CERTIFICATE-----") == 1
    assert sha(ssl.PEM_cert_to_DER_cert(text)) == ISRG_ROOT_X1_DER_SHA256
    ssl.create_default_context(cafile=str(CA))  # the relay's own construction accepts the file as its trust store


def test_nothing_selects_orbio_and_one_openrouter_release_stays_approved() -> None:
    raw, _ = draft()
    assert relay_admission.APPROVED_ACTUAL_RELEASES == frozenset({ADOPTED_SHA})
    assert [d.record_sha256 for d in composition.RELEASE_DEFINITIONS] == [ADOPTED_SHA]
    assert all(b"orbio" not in d.record for d in composition.RELEASE_DEFINITIONS)
    assert composition._approved_definition().record_sha256 == ADOPTED_SHA
    assert sha(raw) not in {d.record_sha256 for d in composition.RELEASE_DEFINITIONS}


def test_the_adopted_openrouter_release_bytes_are_unchanged() -> None:
    record = (ADOPTED / "hermes_first_call_record.json").read_bytes()
    assert sha(record) == ADOPTED_SHA
    assert sha((ADOPTED / "hermes_first_call_approval.json").read_bytes()) == (
        "0bcc0c485021cea626b05ddf3c3fad7ad7b372afad158e4e25c02fb09df3e1ac")
    assert sha((ADOPTED / "hermes_first_call_prices.json").read_bytes()) == (
        "e53259b2605d7a54c7597e04b75dc5b57e8b6ff7484c90be6a788b3388d54fe9")
    assert composition.RELEASE_DEFINITIONS[0].record == record
    actual = load_actual_release(record, ADOPTED_SHA)
    assert actual.destination == ProviderDestination("openrouter.ai", 443, "/api/v1/chat/completions")
