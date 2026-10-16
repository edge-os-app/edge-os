"""The one approved ACTUAL Hermes release (`hermes-first-call-1`) in the ordinary registries, bound by `bind_release`.

Pure: no database, Docker, network, key or provider. The expected values are the adopted release values written as
literals here, not read back from the code under test. The frozen files under
`docs/qualification/hermes-actual-operation/release/` must equal the code-owned bytes exactly. Every other record,
including a one-byte change of the approved one, is still refused before any engine, key, socket or Docker command.
Binding proves the registry shape only; it is not evidence that any provider call ran.
"""

from __future__ import annotations

import builtins
import dataclasses
import hashlib
import json
import os
import socket
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research import hermes_relay_composition as composition
from edge_os_api.research.hermes_relay_composition import bind_release, compose_application
from edge_os_api.research.hermes_transport_mount import MountRefused
from edge_os_api.research.interpreter_output_schema import interpretation_response_format
from edge_os_api.research.provider_spend_ledger import TokenPrice
from test_hermes_relay_composition import endpoint, lazy_engine, open_with, unreachable  # noqa: F401 - a fixture

import relay_admission  # noqa: E402 - on the path once the composition module is imported
from guarded_turn_runner import INPUT_TOKEN_MARGIN  # noqa: E402

RELEASE = Path(__file__).resolve().parents[3] / "docs" / "qualification" / "hermes-actual-operation" / "release"
RECORD_SHA256 = "3fa94dd73e53a72ca8af6cda9c8633770de89c262fa5303756c1965bb92fed8f"
APPROVAL_PATH = "docs/qualification/hermes-actual-operation/release/hermes_first_call_approval.json"
APPROVAL_SHA256 = "0bcc0c485021cea626b05ddf3c3fad7ad7b372afad158e4e25c02fb09df3e1ac"
PRICES_SHA256 = "e53259b2605d7a54c7597e04b75dc5b57e8b6ff7484c90be6a788b3388d54fe9"
FORMAT_SHA256 = "cdffe6fd07f14b796cae3f97268148f6ad8893100b8080e1bc652c7d3e9cbc60"
CA_SHA256 = "7cef540c6af3bf0a3c7d0070bd3fd7aae34f8aa805b408d1c27a01c8aeb305df"
IMAGE = "sha256:2d28b6d634bb32e45409575433fb2404ba6a6144c5cc072ee5044b27d4d181f0"
MODEL = "openai/gpt-6.1-sol"
ROUTING = {"only": ["openai"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
           "max_price": {"prompt": 2, "completion": 10}}
FIELDS = {"model", "messages", "stream", "response_format", "provider", "reasoning", "max_tokens", "session_id",
          "prompt_cache_options"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def adopted() -> composition.RelayApplicationDefinition:
    [given] = composition.RELEASE_DEFINITIONS
    return given


def changed_record(**changes: Any) -> composition.RelayApplicationDefinition:
    """The approved definition with a record that differs in these fields, under the changed record's own hash."""
    raw = canonical({**json.loads(adopted().record), **changes})
    return dataclasses.replace(adopted(), record=raw, record_sha256=hashlib.sha256(raw).hexdigest())


@pytest.fixture
def no_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opening a file, a socket or an engine fails the test."""
    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("an effect was attempted")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(os, "open", refuse)
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(composition, "make_engine", refuse)


# --- the ordinary registries hold exactly the adopted release --------------------------------------------------------


def test_the_ordinary_registries_hold_exactly_the_one_adopted_record() -> None:
    assert relay_admission.APPROVED_ACTUAL_RELEASES == frozenset({RECORD_SHA256})
    assert [item.record_sha256 for item in composition.RELEASE_DEFINITIONS] == [RECORD_SHA256]
    assert composition._approved_definition() is adopted()


def test_the_frozen_release_files_are_the_code_owned_bytes() -> None:
    record = (RELEASE / "hermes_first_call_record.json").read_bytes()
    prices = (RELEASE / "hermes_first_call_prices.json").read_bytes()
    approval = (RELEASE / "hermes_first_call_approval.json").read_bytes()
    assert record == adopted().record and hashlib.sha256(record).hexdigest() == RECORD_SHA256
    assert prices == adopted().price_snapshot and hashlib.sha256(prices).hexdigest() == PRICES_SHA256
    assert hashlib.sha256(approval).hexdigest() == APPROVAL_SHA256
    assert json.loads(record)["approval"] == {"path": APPROVAL_PATH, "sha256": APPROVAL_SHA256}
    assert (Path(__file__).resolve().parents[3] / APPROVAL_PATH).read_bytes() == approval


def test_the_approval_names_every_record_value_and_no_record_hash() -> None:
    approval = json.loads((RELEASE / "hermes_first_call_approval.json").read_bytes())
    record = json.loads(adopted().record)
    assert approval["record_values_except_approval"] == {key: value for key, value in record.items()
                                                         if key != "approval"}
    assert approval["application_definition_values"] == {"image": IMAGE, "channel_root": "edge-os-research",
                                                         "global_cap_usd": "2.00", "owner_cap_usd": "2.00"}
    assert RECORD_SHA256 not in json.dumps(approval)  # the record names the approval, never the reverse


def test_the_definition_names_the_accepted_output_format_by_its_exact_bytes() -> None:
    schema = canonical(adopted().response_format)
    assert len(schema) == 7182 and hashlib.sha256(schema).hexdigest() == FORMAT_SHA256
    assert adopted().response_format == interpretation_response_format()


# --- the adopted release binds with exactly the adopted values -------------------------------------------------------


def test_the_adopted_release_binds_its_exact_request_shape_price_caps_and_image_without_any_effect(no_effects) -> None:
    release = bind_release(adopted())

    actual = release.actual
    assert actual.record_sha256 == RECORD_SHA256 and release.approval_sha256 == APPROVAL_SHA256
    assert release.price_snapshot_sha256 == PRICES_SHA256 and actual.ca_bundle_sha256 == CA_SHA256
    assert actual.release.settings() == {"release_id": "hermes-first-call-1", "route_id": "openrouter-openai-standard",
                                         "kind": "ACTUAL", "model": MODEL, "max_output_tokens": 4096,
                                         "max_request_bytes": 65536, "max_reply_bytes": 262144}
    assert actual.endpoint_url == "https://openrouter.ai/api/v1/chat/completions" and actual.timeout_seconds == 90
    assert actual.allowed_fields == frozenset(FIELDS) and actual.response_format_sha256 == FORMAT_SHA256
    assert release.policy.required_extra == {"stream": False, "provider": ROUTING, "reasoning": {"effort": "low"},
                                             "prompt_cache_options": {"mode": "explicit"},
                                             "response_format": interpretation_response_format()}
    assert (release.policy.model, release.policy.max_output_tokens, release.policy.max_request_bytes) == (
        MODEL, 4096, 65536)
    assert (release.route.kind, release.route.endpoint_url, release.route.max_reply_bytes) == (
        "ACTUAL", "https://openrouter.ai/api/v1/chat/completions", 262144)
    assert release.price == TokenPrice(Decimal("2"), Decimal("10")) and release.limits.price is release.price
    assert (release.limits.global_cap_usd, release.limits.owner_cap_usd) == (Decimal("2.00"), Decimal("2.00"))
    assert (release.image, release.channel_root) == (IMAGE, "edge-os-research")
    assert release.config.live_release is not None and release.config.live_release.recorded_in == APPROVAL_PATH


def test_one_request_reserves_at_most_the_adopted_worst_case_of_usd_0_17216() -> None:
    release = bind_release(adopted())
    worst = release.price.nano_usd(release.policy.max_request_bytes + INPUT_TOKEN_MARGIN,
                                   release.policy.max_output_tokens)
    assert worst == 172_160_000  # nano-USD: an accounting reservation inside the shared USD 2.00, not an allocation


def test_composing_the_adopted_release_opens_nothing(tmp_path: Path) -> None:
    app = compose_application(bind_release(adopted()), lazy_engine(), endpoint=endpoint(tmp_path / "relay",
                                                                                         "edge-os-research"),
                              run_id="rc-binding", evidence_dir=tmp_path / "jobs")
    assert app.spend._configured.price is app.release.price and app.supervision.image == IMAGE
    assert list(tmp_path.iterdir()) == []


# --- everything else is still refused before any effect --------------------------------------------------------------


@pytest.mark.parametrize("changes", [
    {"release_id": "hermes-first-call-2"},
    {"model": "openai/gpt-6.1"},
    {"provider": {**ROUTING, "only": ["azure"]}},
    {"provider": {**ROUTING, "allow_fallbacks": True}},
    {"provider": {**ROUTING, "data_collection": "allow"}},
    {"provider": {**ROUTING, "max_price": {"prompt": 3, "completion": 10}}},
    {"max_tokens": 8192},
    {"max_request_bytes": 131072},
    {"max_reply_bytes": 524288},
    {"timeout_seconds": 120},
    {"reasoning": {"effort": "high"}},
    {"reasoning": None},
    {"ca_bundle_sha256": "0" * 64},
    {"price_snapshot_sha256": "0" * 64},
    {"response_format_sha256": "0" * 64},
    {"approval": {"path": APPROVAL_PATH, "sha256": "0" * 64}},
    {"approval": {"path": "elsewhere/approval.json", "sha256": APPROVAL_SHA256}},
])
def test_a_record_that_differs_from_the_adopted_one_is_unapproved(no_effects, changes: dict[str, Any]) -> None:
    with pytest.raises(MountRefused, match="ActualReleaseUnapproved"):
        bind_release(changed_record(**changes))


def test_a_record_without_the_cache_option_is_unapproved(no_effects) -> None:
    record = {key: value for key, value in json.loads(adopted().record).items() if key != "prompt_cache_options"}
    raw = canonical({**record, "allowed_fields": sorted(FIELDS - {"prompt_cache_options"})})
    with pytest.raises(MountRefused, match="ActualReleaseUnapproved"):
        bind_release(dataclasses.replace(adopted(), record=raw, record_sha256=hashlib.sha256(raw).hexdigest()))


def test_record_bytes_one_byte_away_from_the_approved_hash_are_refused(no_effects) -> None:
    for raw in (adopted().record + b" ", adopted().record[:-1], adopted().record.replace(b"4096", b"4097")):
        with pytest.raises(MountRefused):
            bind_release(dataclasses.replace(adopted(), record=raw))


@pytest.mark.parametrize("changes", [
    {"price_snapshot": b'{"completion_usd_per_million":"10","model":"openai/gpt-6.1-sol","prompt_usd_per_million":"2",'
                       b'"provider":"openai"} '},
    {"price_snapshot": b'{"completion_usd_per_million":"9","model":"openai/gpt-6.1-sol","prompt_usd_per_million":"2",'
                       b'"provider":"openai"}'},
    {"response_format": {"type": "json_object"}},
    {"response_format": None},
    {"image": "edge-os-p05-hermes:latest"},
    {"image": "edge-os/pinned-hermes@" + IMAGE},
])
def test_an_approved_record_with_other_price_schema_or_image_bytes_is_refused(no_effects,
                                                                              changes: dict[str, Any]) -> None:
    with pytest.raises(MountRefused):
        bind_release(dataclasses.replace(adopted(), **changes))


def test_an_explicitly_empty_registry_refuses_the_adopted_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset())
    with pytest.raises(MountRefused, match="ActualReleaseUnapproved"):
        bind_release(adopted())
    assert composition._approved_definition() is None


def test_no_environment_value_adds_a_release(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = changed_record(release_id="hermes-env-1").record
    for name in ("EDGE_OS_HERMES_RELEASE", "APPROVED_ACTUAL_RELEASES", "RELEASE_DEFINITIONS"):
        monkeypatch.setenv(name, hashlib.sha256(raw).hexdigest())
    with pytest.raises(relay_admission.ActualReleaseUnapproved):
        relay_admission.load_actual_release(raw, hashlib.sha256(raw).hexdigest())
    assert relay_admission.APPROVED_ACTUAL_RELEASES == frozenset({RECORD_SHA256})


def test_the_default_application_still_needs_the_operator_handoff_before_any_engine(unreachable,  # noqa: F811
                                                                                    tmp_path: Path) -> None:
    with pytest.raises(MountRefused, match="handoff"):
        open_with(unreachable, tmp_path)  # the adopted release binds; the named handoff does not exist
    assert list(tmp_path.iterdir()) == []
