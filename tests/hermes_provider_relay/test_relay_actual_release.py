"""The ACTUAL release record and its exact request and reply rules (CONTRACT A6). Synthetic records only; no I/O."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

import relay_admission
from relay_admission import ActualReleaseUnapproved, RelayRelease, load_actual_release

SCHEMA = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {"type": "object"}}}
ROUTING = {"only": ["synthetic-slug"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
           "max_price": {"prompt": 1, "completion": 2}}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def record(**changes: Any) -> dict[str, Any]:
    value = {"release_id": "rel-synthetic-1", "route_id": "route-synthetic", "kind": "ACTUAL",
             "approval": {"path": "/synthetic/approval.md", "sha256": "a" * 64},
             "destination": {"host": "openrouter.ai", "port": 443, "path": "/api/v1/chat/completions"},
             "ca_bundle_sha256": "b" * 64, "model": "synthetic/model-1", "provider": ROUTING, "max_tokens": 4096,
             "reasoning": {"effort": "low"}, "response_format_sha256": hashlib.sha256(canonical(SCHEMA)).hexdigest(),
             "stream": False, "allowed_fields": ["model", "messages", "stream", "response_format", "provider",
                                                 "reasoning", "max_tokens", "session_id"],
             "max_request_bytes": 65_536, "max_reply_bytes": 262_144, "timeout_seconds": 90,
             "price_snapshot_sha256": "c" * 64}
    value.update(changes)
    return value


def load(value: dict[str, Any], approved: bool = True):
    raw = json.dumps(value).encode()
    sha = hashlib.sha256(raw).hexdigest()
    return load_actual_release(raw, sha, approved=frozenset({sha}) if approved else None)


def test_no_actual_release_is_approved_in_this_candidate_so_every_record_fails_closed() -> None:
    assert relay_admission.APPROVED_ACTUAL_RELEASES == frozenset()
    with pytest.raises(ActualReleaseUnapproved):
        load(record(), approved=False)


def test_a_record_whose_bytes_differ_from_the_named_hash_is_refused() -> None:
    raw = json.dumps(record()).encode()
    with pytest.raises(ValueError, match="hash"):
        load_actual_release(raw + b" ", hashlib.sha256(raw).hexdigest(), approved=frozenset({hashlib.sha256(raw).hexdigest()}))


def test_an_approved_record_gives_the_actual_release_and_fixed_destination() -> None:
    actual = load(record())
    assert actual.release.settings() == {"release_id": "rel-synthetic-1", "route_id": "route-synthetic", "kind": "ACTUAL",
                                         "model": "synthetic/model-1", "max_output_tokens": 4096,
                                         "max_request_bytes": 65_536, "max_reply_bytes": 262_144}
    with pytest.raises(ValueError, match="approved release record"):  # nothing else can build an ACTUAL release
        RelayRelease.from_settings(actual.release.settings())
    assert (actual.destination.host, actual.destination.port, actual.destination.path) == (
        "openrouter.ai", 443, "/api/v1/chat/completions")
    assert actual.endpoint_url == "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.parametrize("change", [
    {"kind": "AUTHORED"},
    {"destination": {"host": "localhost", "port": 443, "path": "/api/v1/chat/completions"}},
    {"destination": {"host": "openrouter.ai", "port": 8443, "path": "/api/v1/chat/completions"}},
    {"destination": {"host": "openrouter.ai", "port": 443, "path": "/v1/chat/completions"}},
    {"stream": True},
    {"provider": {**ROUTING, "allow_fallbacks": True}},
    {"provider": {**ROUTING, "only": ["a", "b"]}},
    {"provider": {**ROUTING, "require_parameters": False}},
    {"allowed_fields": ["model", "messages", "temperature"]},
    {"ca_bundle_sha256": "not-a-hash"},
    {"test_resolution": "172.18.0.5"},  # a test resolver can never be part of an ACTUAL release
    {"max_reply_bytes": 0},
])
def test_a_record_outside_the_frozen_shape_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises((ValueError, TypeError)):
        load(record(**change))


def test_a_record_with_a_repeated_key_is_refused() -> None:
    raw = json.dumps(record())[:-1].encode() + b', "kind": "ACTUAL"}'
    sha = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        load_actual_release(raw, sha, approved=frozenset({sha}))


def body(**changes: Any) -> bytes:
    value = {"model": "synthetic/model-1", "messages": [{"role": "user", "content": "x"}], "stream": False,
             "response_format": SCHEMA, "provider": ROUTING, "reasoning": {"effort": "low"}, "max_tokens": 4096,
             "session_id": "p05-att-1"}
    value.update(changes)
    return json.dumps({k: v for k, v in value.items() if v is not ...}).encode()


def test_the_exact_admitted_body_passes() -> None:
    assert load(record()).body_refusal(body(), "att-1") is None


@pytest.mark.parametrize("raw, reason", [
    (b"not json", "body_not_json"),
    (body(temperature=0.2), "body_field_not_permitted"),
    (body(session_id=...), "body_field_missing"),
    (body(model="synthetic/other"), "body_model_mismatch"),
    (body(stream=True), "body_stream_not_false"),
    (body(max_tokens=4095), "body_max_tokens_mismatch"),
    (body(max_tokens=True), "body_max_tokens_mismatch"),
    (body(provider={**ROUTING, "allow_fallbacks": True}), "body_routing_mismatch"),
    (body(reasoning={"effort": "high"}), "body_reasoning_mismatch"),
    (body(response_format={**SCHEMA, "type": "json_object"}), "body_schema_mismatch"),
    (body(session_id="p05-att-2"), "body_session_mismatch"),
    (body(messages="x"), "body_messages_invalid"),
])
def test_any_other_body_is_refused_before_a_start_record(raw: bytes, reason: str) -> None:
    assert load(record()).body_refusal(raw, "att-1") == reason


def reply(**changes: Any) -> bytes:
    value = {"id": "gen-synthetic-1", "model": "synthetic/model-1",
             "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}],
             "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.000123}}
    value.update(changes)
    return json.dumps(value).encode()


def test_a_complete_reply_gives_usage_cost_and_generation_id() -> None:
    refusal, details = load(record()).reply_check(200, "application/json", "", reply())
    assert refusal is None
    assert details == {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, "cost": 0.000123,
                       "generation_id": "gen-synthetic-1"}


@pytest.mark.parametrize("status, content_type, encoding, raw, reason", [
    (200, "application/json", "gzip", reply(), "reply_encoded_refused"),
    (302, "application/json", "", reply(), "reply_status_not_2xx"),
    (500, "application/json", "", reply(), "reply_status_not_2xx"),
    (200, "text/html", "", reply(), "reply_not_json"),
    (200, "application/json", "", b"[]", "reply_not_a_json_object"),
    (200, "application/json", "", reply(choices=[]), "reply_choices_invalid"),
    (200, "application/json", "", reply(choices=[{"finish_reason": "stop"}, {"finish_reason": "stop"}]),
     "reply_choices_invalid"),
    (200, "application/json", "", reply(choices=[{"finish_reason": "length"}]), "reply_truncated"),
    (200, "application/json", "", reply(choices=[{"finish_reason": None}]), "reply_not_final"),
    (200, "application/json", "", reply(model="synthetic/other"), "reply_model_mismatch"),
    (200, "application/json", "", reply(usage={"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.1}),
     "reply_usage_invalid"),
    (200, "application/json", "", reply(usage={"prompt_tokens": 1.5, "completion_tokens": 5, "total_tokens": 6,
                                               "cost": 0.1}), "reply_usage_invalid"),
    (200, "application/json", "", reply(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}),
     "reply_cost_invalid"),
    (200, "application/json", "", reply(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                                               "cost": -1}), "reply_cost_invalid"),
    (200, "application/json", "", reply(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                                               "cost": True}), "reply_cost_invalid"),
    (200, "application/json", "", b'{"usage": {"cost": NaN}}', "reply_not_a_json_object"),
])
def test_any_other_reply_is_refused_and_stays_unknown(status: int, content_type: str, encoding: str, raw: bytes,
                                                      reason: str) -> None:
    refusal, details = load(record()).reply_check(status, content_type, encoding, raw)
    assert (refusal, details) == (reason, {})
