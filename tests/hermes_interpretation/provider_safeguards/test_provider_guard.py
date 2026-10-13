"""The provider request guard: what may leave for the provider, decided before any transport sees it.

The guard sits in front of the transport. A refused request never reaches the transport. These tests use the wire
shape that the pinned Hermes really sends (model, messages, max_tokens, session_id), measured in the P05 container runs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from provider_guard import GuardPolicy, LogicalRequest, ProviderRequestGuard, guard_handler

SENTINEL = "sk-test-DUMMY-SENTINEL-9f3a71c2e8b54d06"
PROMPT = "You read one trading request and answer with one JSON object."
TASK = '{"task":"interpret","original_request":"Buy when the 15-minute return is above 1%."}'
WRAPPED = "You are Hermes Agent.\n\n" + PROMPT + "\n\nHost: Linux\n"
POLICY = GuardPolicy(model="vendor/model-1", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500)
LOGICAL = LogicalRequest(system_prompt=PROMPT, user_message=TASK)
AUTH = {"authorization": f"Bearer {SENTINEL}", "content-type": "application/json"}


def body(**changes: Any) -> bytes:
    wire: dict[str, Any] = {"model": "vendor/model-1", "max_tokens": 4096, "session_id": "attempt-1", "messages": [
        {"role": "system", "content": WRAPPED}, {"role": "user", "content": TASK}]}
    wire.update(changes)
    return json.dumps({key: value for key, value in wire.items() if value is not ...}).encode()


def guard(policy: GuardPolicy = POLICY) -> ProviderRequestGuard:
    return ProviderRequestGuard(policy, LOGICAL, credential=SENTINEL)


def test_the_exact_logical_request_in_the_hermes_envelope_is_admitted() -> None:
    decision = guard().admit(body(), AUTH)

    assert (decision.admitted, decision.reason) == (True, None)


@pytest.mark.parametrize("changes, reason", [
    ({"model": "vendor/other"}, "model_not_as_configured"),
    ({"max_tokens": 8192}, "output_limit_not_as_configured"),
    ({"max_tokens": ...}, "output_limit_not_as_configured"),
    ({"max_completion_tokens": 4096}, "unpermitted_field"),
    ({"tools": [{"type": "function"}]}, "unpermitted_field"),
    ({"tool_choice": "auto"}, "unpermitted_field"),
    ({"stream": True}, "unpermitted_field"),
    ({"models": ["vendor/fallback"]}, "unpermitted_field"),
    ({"route": "fallback"}, "unpermitted_field"),
    ({"transforms": ["middle-out"]}, "unpermitted_field"),
    ({"provider": {"allow_fallbacks": True}}, "unpermitted_field"),
    ({"messages": [{"role": "system", "content": WRAPPED}]}, "messages_not_as_configured"),
    ({"messages": [{"role": "system", "content": WRAPPED}, {"role": "user", "content": TASK},
                   {"role": "assistant", "content": "x"}]}, "messages_not_as_configured"),
    ({"messages": [{"role": "system", "content": WRAPPED}, {"role": "user", "content": TASK + " also sell"}]},
     "task_not_as_configured"),
    ({"messages": [{"role": "system", "content": "You are Hermes Agent."}, {"role": "user", "content": TASK}]},
     "prompt_not_as_configured"),
    ({"messages": [{"role": "system", "content": WRAPPED + "x" * 2_501}, {"role": "user", "content": TASK}]},
     "envelope_too_large"),
])
def test_a_request_that_differs_from_the_configuration_is_refused(changes: dict[str, Any], reason: str) -> None:
    decision = guard().admit(body(**changes), AUTH)

    assert (decision.admitted, decision.reason) == (False, reason)


def test_a_request_over_the_byte_limit_is_refused() -> None:
    small = GuardPolicy(model="vendor/model-1", max_output_tokens=4096, max_request_bytes=len(body()) - 1,
                        max_envelope_chars=2_500)

    assert guard(small).admit(body(), AUTH).reason == "request_too_large"
    assert guard(GuardPolicy("vendor/model-1", 4096, len(body()), 2_500)).admit(body(), AUTH).admitted


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'"text"', b"\xff\xfe"])
def test_a_body_that_is_not_one_json_object_is_refused(raw: bytes) -> None:
    assert guard().admit(raw, AUTH).reason == "body_not_a_json_object"


@pytest.mark.parametrize("headers", [{}, {"authorization": "Bearer other-key"}, {"authorization": SENTINEL}])
def test_a_request_without_the_injected_credential_is_refused(headers: dict[str, str]) -> None:
    assert guard().admit(body(), headers).reason == "credential_not_as_injected"


def test_the_required_provider_routing_must_match_exactly() -> None:
    routed = GuardPolicy(model="vendor/model-1", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500,
                         required_extra={"provider": {"allow_fallbacks": False, "data_collection": "deny"}})

    assert guard(routed).admit(body(provider={"allow_fallbacks": False, "data_collection": "deny"}), AUTH).admitted
    assert guard(routed).admit(body(), AUTH).reason == "routing_not_as_configured"
    assert guard(routed).admit(body(provider={"allow_fallbacks": True, "data_collection": "deny"}), AUTH).reason == (
        "routing_not_as_configured")


def test_exactly_one_physical_request_is_admitted_per_attempt() -> None:
    attempt = guard()

    assert attempt.admit(body(), AUTH).admitted
    second = attempt.admit(body(), AUTH)

    assert (second.admitted, second.reason, second.phase) == (False, "physical_request_count_exceeded", "retry")
    assert (attempt.admitted_count, attempt.seen_count) == (1, 2)


def test_a_truncation_continuation_is_refused_and_named() -> None:
    attempt = guard()
    attempt.admit(body(), AUTH)
    continuation = body(max_tokens=8192, messages=[
        {"role": "system", "content": WRAPPED}, {"role": "user", "content": TASK},
        {"role": "user", "content": "[System: Continue exactly where you left off.]"}])

    decision = attempt.admit(continuation, AUTH)

    assert (decision.admitted, decision.phase) == (False, "truncation_continuation")


def test_an_iteration_summary_request_is_refused_and_named() -> None:
    attempt = guard()
    attempt.admit(body(), AUTH)
    summary = body(messages=[{"role": "system", "content": WRAPPED}, {"role": "user", "content": TASK},
                             {"role": "user", "content": "Please write a summarizing what you've found and accomplished so far."}])

    assert attempt.admit(summary, AUTH).phase == "iteration_summary"


def test_a_refused_first_request_does_not_use_up_the_admission() -> None:
    attempt = guard()

    assert not attempt.admit(body(model="vendor/other"), AUTH).admitted
    assert attempt.admit(body(), AUTH).admitted
    assert (attempt.admitted_count, attempt.seen_count) == (1, 2)


def test_refusal_evidence_holds_hashes_and_names_but_never_bodies_or_credentials() -> None:
    attempt = guard()
    raw = body(model="vendor/other")
    attempt.admit(raw, AUTH)

    [record] = attempt.evidence()

    assert record["request_sha256"] == hashlib.sha256(raw).hexdigest()
    assert record["request_bytes"] == len(raw) and record["reason"] == "model_not_as_configured"
    assert record["header_names"] == ["authorization", "content-type"]
    dumped = json.dumps(attempt.evidence())
    assert SENTINEL not in dumped and TASK not in dumped and "Bearer" not in dumped


def test_a_refused_request_never_reaches_the_transport() -> None:
    reached: list[bytes] = []
    handler = guard_handler(guard(), lambda raw, headers: reached.append(raw) or (200, b"{}"))

    assert handler(body(model="vendor/other"), AUTH)[0] == 429
    assert reached == []
    assert handler(body(), AUTH)[0] == 200
    assert handler(body(), AUTH)[0] == 429
    assert len(reached) == 1


def test_simultaneous_requests_admit_exactly_one() -> None:
    import sys
    import threading

    attempt, results, start = guard(), [], threading.Barrier(16)
    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # switch threads often, so a missing lock shows

    def send() -> None:
        start.wait()
        results.append(attempt.admit(body(), AUTH).admitted)

    threads = [threading.Thread(target=send) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    sys.setswitchinterval(interval)

    assert sorted(results) == [False] * 15 + [True]
    assert (attempt.admitted_count, attempt.seen_count) == (1, 16)


def test_a_float_output_limit_or_a_repeated_key_is_not_the_configured_request() -> None:
    as_float = body().replace(b'"max_tokens": 4096', b'"max_tokens": 4096.0')
    repeated = body().replace(b'"max_tokens": 4096', b'"max_tokens": 1, "max_tokens": 4096')

    assert guard().admit(as_float, AUTH).reason == "output_limit_not_as_configured"
    assert guard().admit(repeated, AUTH).reason == "body_not_a_json_object"


@pytest.mark.parametrize("index", [0, 1])
def test_an_unexpected_field_inside_any_message_never_reaches_the_transport(index: int) -> None:
    reached: list[bytes] = []
    messages = [{"role": "system", "content": WRAPPED}, {"role": "user", "content": TASK}]
    messages[index]["tool_calls"] = [{"id": "x", "type": "function", "function": {"name": "unapproved", "arguments": "{}"}}]
    handler = guard_handler(guard(), lambda raw, headers: reached.append(raw) or (200, b"{}"))

    status, _ = handler(body(messages=messages), AUTH)

    assert (status, reached) == (429, [])


def test_a_message_without_its_role_or_content_is_not_the_configured_request() -> None:
    assert guard().admit(body(messages=[{"role": "system"}, {"role": "user", "content": TASK}]), AUTH).reason == "messages_not_as_configured"
