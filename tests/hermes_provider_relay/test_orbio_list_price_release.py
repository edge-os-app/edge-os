"""The list-price Orbio release is approved beside the OpenRouter release, and nothing selects it by default.

The files in docs/qualification/orbio-release/ are read as bytes. Nothing here opens a network socket, reads a provider key
or contacts Orbio. See `docs/qualification/orbio-release/ORBIO_RELEASE_DRAFT.md`.
"""

from __future__ import annotations

import hashlib
import json
import ssl
from decimal import Decimal
from pathlib import Path

import relay_admission
from edge_os_api.research import hermes_relay_composition as composition
from guarded_turn_runner import INPUT_TOKEN_MARGIN
from relay_admission import ProviderDestination, load_actual_release
from relay_operator import load_config
from spend_ledger import TokenPrice

REPO = Path(__file__).resolve().parents[2]
FOLDER = REPO / "docs/qualification/orbio-release"
RECORD = FOLDER / "orbio_list_price_record.json"
PACKET = FOLDER / "orbio_list_price_approval.json"
PRICES = FOLDER / "orbio_list_price_prices.json"
CA = FOLDER / "orbio_ca_isrg_root_x1.pem"
DRAFT = FOLDER / "ORBIO_RELEASE_DRAFT.md"
ADOPTED = REPO / "docs/qualification/hermes-actual-operation/release"
ADOPTED_SHA = "3fa94dd73e53a72ca8af6cda9c8633770de89c262fa5303756c1965bb92fed8f"
RETIRED_RECORD_SHA = "041f588d3b9564fd605d00d2204083cbfc4e4cd3307906656345a73118ac563f"
RETIRED_FILES = {"orbio_first_call_record.json": RETIRED_RECORD_SHA,
                 "orbio_first_call_approval.json": "22e9ccdc52de423f8c612bc59376bec38357a47134f2c130b50a75e7c9e23e48",
                 "orbio_first_call_prices.json": "4f83b00bd51b0614f1da551c762ce8969f27c5bb26bf5edf8a3f6e3412f982dc"}
ISRG_ROOT_X1_DER_SHA256 = "96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6"
STILL_UNKNOWN = ("U1", "U2", "U3", "U7", "U9", "U10", "U11")
CLOSED = ("U4", "U5", "U6", "U8")
RELEASE_MARKS = (b"orbio-list-price-1", b'"orbio-list-price"', b"orbio-first-call-1", b"orbio-openrouter-managed",
                 b"api.orbio.so")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def raw_is_canonical(raw: bytes) -> bool:
    return canonical(json.loads(raw)) == raw


def orbio_definition() -> composition.RelayApplicationDefinition:
    [given] = [item for item in composition.RELEASE_DEFINITIONS if item.record_sha256 == sha(RECORD.read_bytes())]
    return given


def test_the_orbio_record_loads_from_the_default_registry_with_its_own_destination_and_no_routing() -> None:
    raw = RECORD.read_bytes()
    assert raw_is_canonical(raw)
    actual = load_actual_release(raw, sha(raw))
    assert actual.destination == ProviderDestination("api.orbio.so", 443, "/api/v1/chat/completions")
    assert actual.provider is None and "provider" not in actual.allowed_fields
    assert actual.ca_bundle_sha256 == sha(CA.read_bytes())
    assert actual.recorded_reply_headers == ("X-Orbio-Balance", "X-Orbio-Ignored-Parameters")
    assert actual.release.settings() == {
        "release_id": "orbio-list-price-1", "route_id": "orbio-list-price", "kind": "ACTUAL",
        "model": "openai/gpt-6.1-sol", "max_output_tokens": 4096, "max_request_bytes": 65536,
        "max_reply_bytes": 262144}
    assert (actual.reasoning, actual.prompt_cache_options, actual.timeout_seconds) == (
        {"effort": "low"}, {"mode": "explicit"}, 90)


def test_the_hash_chain_names_its_packet_prices_and_ca_bundle() -> None:
    value = json.loads(RECORD.read_bytes())
    packet = json.loads(PACKET.read_bytes())
    assert value["approval"] == {"path": "docs/qualification/orbio-release/orbio_list_price_approval.json",
                                 "sha256": sha(PACKET.read_bytes())}
    assert packet["status"] == "APPROVED_RELEASE_VALUES"
    assert packet["record_values_except_approval"] == {k: v for k, v in value.items() if k != "approval"}
    assert value["price_snapshot_sha256"] == sha(PRICES.read_bytes())
    assert json.loads(PRICES.read_bytes()) == {"completion_usd_per_million": "10", "model": "openai/gpt-6.1-sol",
                                               "prompt_usd_per_million": "2", "provider": "orbio"}
    assert raw_is_canonical(PRICES.read_bytes())
    assert value["response_format_sha256"] == json.loads(
        (ADOPTED / "hermes_first_call_record.json").read_bytes())["response_format_sha256"]


def test_the_approval_packet_keeps_the_catalogue_and_tls_readings_and_approves_no_call() -> None:
    packet = json.loads(PACKET.read_bytes())
    assert packet["facts"]["catalogue"]["read_utc"] == "2026-11-05"
    assert packet["facts"]["catalogue"]["override"] == {"min_prompt_tokens": 272000, "prompt_usd_per_token": "0.000004",
                                                        "completion_usd_per_token": "0.000015"}
    assert packet["facts"]["tls"]["verify_return_code"] == 0
    assert "does not authorize" in packet["meaning"]
    assert sorted(packet["open"]) == sorted(STILL_UNKNOWN)


def test_the_definition_holds_the_frozen_file_bytes_and_binds_the_seller_at_the_list_price() -> None:
    given = orbio_definition()
    assert given.record == RECORD.read_bytes() and given.price_snapshot == PRICES.read_bytes()
    assert given.min_output_tokens is None
    assert (given.global_cap_usd, given.owner_cap_usd) == (Decimal("2.00"), Decimal("2.00"))
    assert composition.RELEASE_DEFINITIONS[0].images == given.images
    bound = composition.bind_release(given)
    assert bound.price == TokenPrice(Decimal("2"), Decimal("10"))
    assert bound.config.route == "orbio-list-price" and bound.config.live_release.provider == "orbio"
    assert "provider" not in bound.policy.required_extra
    assert bound.route.endpoint_url == "https://api.orbio.so/api/v1/chat/completions"


def bound_price() -> TokenPrice:
    return composition.bind_release(orbio_definition()).price


def test_the_price_is_the_list_rate_with_the_openrouter_maximum_hold() -> None:
    value = json.loads(RECORD.read_bytes())
    assert bound_price().nano_usd(value["max_request_bytes"] + INPUT_TOKEN_MARGIN, value["max_tokens"]) == 172_160_000


def test_the_first_paid_call_settles_at_exactly_its_reported_cost() -> None:
    # Request f82a30d4: 3,442 prompt and 228 completion tokens, usage.cost 0.009164, balance drop 0.009164.
    assert bound_price().nano_usd(3_442, 228) == 9_164_000


def test_the_retired_release_keeps_its_bytes_and_is_no_longer_approved() -> None:
    for name, digest in RETIRED_FILES.items():
        assert sha((FOLDER / name).read_bytes()) == digest
    assert RETIRED_RECORD_SHA not in relay_admission.APPROVED_ACTUAL_RELEASES
    assert RETIRED_RECORD_SHA not in [d.record_sha256 for d in composition.RELEASE_DEFINITIONS]
    assert json.loads(PACKET.read_bytes())["replaces"]["record_sha256"] == RETIRED_RECORD_SHA


def test_the_catalogue_override_cannot_be_reached_by_the_records_request_limit() -> None:
    value = json.loads(RECORD.read_bytes())
    packet = json.loads(PACKET.read_bytes())
    assert value["max_request_bytes"] + INPUT_TOKEN_MARGIN < packet["facts"]["catalogue"]["override"]["min_prompt_tokens"]


def test_the_draft_cites_orbios_public_pages_and_no_look_alike() -> None:
    text = DRAFT.read_text()
    for source in ("https://www.orbio.so", "https://www.orbio.so/developers", "https://www.orbio.so/llms.txt",
                   "https://www.orbio.so/api/v1/models"):
        assert f"<{source}>" in text
    assert "2026-10-30" in text and "CLOUD-ORBIO-01" in text
    for look_alike in ("orbioagent.world", "orbio-proposals.xyz"):
        assert f"https://{look_alike}" not in text and f"<{look_alike}" not in text


def test_the_draft_shows_the_new_status_of_every_unknown_and_step() -> None:
    text = DRAFT.read_text()
    for label in CLOSED:
        assert f"- {label}. CLOSED" in text
    for label in STILL_UNKNOWN:
        assert f"- {label}. UNKNOWN after one paid call" in text
    for step in range(1, 9):
        assert f"Step {step}: " in text
    assert sha(RECORD.read_bytes()) in text and sha(PACKET.read_bytes()) in text and "never added beside" not in text


def test_the_ca_bundle_is_only_isrg_root_x1() -> None:
    text = CA.read_text()
    assert text.count("-----BEGIN CERTIFICATE-----") == 1
    assert sha(ssl.PEM_cert_to_DER_cert(text)) == ISRG_ROOT_X1_DER_SHA256
    ssl.create_default_context(cafile=str(CA))  # the relay's own construction accepts the file as its trust store


def test_both_releases_are_approved_and_each_has_one_definition() -> None:
    orbio = sha(RECORD.read_bytes())
    assert relay_admission.APPROVED_ACTUAL_RELEASES == frozenset({ADOPTED_SHA, orbio})
    assert [d.record_sha256 for d in composition.RELEASE_DEFINITIONS] == [ADOPTED_SHA, orbio]


def test_nothing_outside_the_two_registries_names_the_orbio_release_as_a_default() -> None:
    allowed = {"apps/api/src/edge_os_api/research/hermes_relay_composition.py",
               "scripts/hermes_provider_relay/relay_admission.py"}
    roots = [*(REPO / "apps/api/src").rglob("*.py"), *(REPO / "scripts").rglob("*.py"), *(REPO / "deploy").rglob("*"),
             REPO / "compose.local.yml", REPO / "compose.coolify.yml"]
    named = {str(path.relative_to(REPO)) for path in roots if path.is_file()
             and any(mark in path.read_bytes() for mark in RELEASE_MARKS)}
    assert named <= allowed


def test_an_existing_openrouter_handoff_selects_the_same_openrouter_release(tmp_path: Path) -> None:
    raw = canonical({"release_record": {"path": "/any/path", "sha256": ADOPTED_SHA}})
    path = tmp_path / "handoff.json"
    path.write_bytes(raw)
    assert composition._selected_definition(path, sha(raw)) is composition.RELEASE_DEFINITIONS[0]


def test_an_operator_configuration_that_names_the_orbio_record_and_its_bundle_loads(tmp_path: Path) -> None:
    key = tmp_path / "provider-key"
    key.write_text("synthetic")
    key.chmod(0o600)
    loaded = load_config(canonical({
        "format": "edge-os.relay-operator-config/1", "operation_id": "paid-call-1", "kind": "ACTUAL", "release": None,
        "release_record": {"path": str(RECORD), "sha256": sha(RECORD.read_bytes())},
        "ca_bundle": {"path": str(CA), "sha256": sha(CA.read_bytes())},
        "image": {"reference": "edge-os-p05-hermes:local",
                  "id": composition.image_for_platform(orbio_definition(), composition._host_platform())},
        "run_root": str(tmp_path / "run"), "channel": {"name": "edge-os-research", "path": str(tmp_path / "channel")},
        "provider_key_file": str(key), "shutdown_owner": "relay_operator"}))
    assert loaded.release.release_id == "orbio-list-price-1"


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
    assert actual.recorded_reply_headers == ()
    assert composition.bind_release(composition.RELEASE_DEFINITIONS[0]).config.live_release.provider == "openai"
