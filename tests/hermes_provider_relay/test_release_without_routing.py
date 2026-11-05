"""A release may name no routing, and that weakens no release that names it (draft section 7 step 3, decision 3).

Synthetic records only, loaded under a test-only registry. No network, key or provider.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from relay_admission import ActualRelease, load_actual_release

ROUTING = {"only": ["synthetic-slug"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
           "max_price": {"prompt": 1, "completion": 2}}
UNROUTED_FIELDS = ["model", "messages", "stream", "reasoning", "max_tokens", "session_id"]
ATTEMPT = "attempt-1"


def record(**changes: Any) -> dict[str, Any]:
    return {"release_id": "rel-unrouted-1", "route_id": "route-unrouted", "kind": "ACTUAL",
            "approval": {"path": "/synthetic/approval.md", "sha256": "a" * 64},
            "destination": {"host": "seller.example", "port": 443, "path": "/api/v1/chat/completions"},
            "ca_bundle_sha256": "b" * 64, "model": "synthetic/model-1", "provider": None, "max_tokens": 4096,
            "reasoning": {"effort": "low"}, "response_format_sha256": "c" * 64, "stream": False,
            "allowed_fields": UNROUTED_FIELDS, "max_request_bytes": 65_536, "max_reply_bytes": 262_144,
            "timeout_seconds": 90, "price_snapshot_sha256": "d" * 64, **changes}


def load(value: dict[str, Any]) -> ActualRelease:
    raw = json.dumps(value).encode()
    sha = hashlib.sha256(raw).hexdigest()
    return load_actual_release(raw, sha, approved=frozenset({sha}))


def body(**changes: Any) -> bytes:
    return json.dumps({"model": "synthetic/model-1", "messages": [{"role": "user", "content": "x"}], "stream": False,
                       "reasoning": {"effort": "low"}, "max_tokens": 4096, "session_id": f"p05-{ATTEMPT}",
                       **changes}).encode()


def test_a_record_naming_no_routing_loads_with_no_routing() -> None:
    assert load(record()).provider is None


def test_a_release_with_no_routing_admits_a_body_with_no_routing_field() -> None:
    assert load(record()).body_refusal(body(), ATTEMPT) is None


@pytest.mark.parametrize("sent", [None, {}, ROUTING])
def test_a_release_with_no_routing_refuses_any_routing_field_in_the_body(sent: Any) -> None:
    assert load(record()).body_refusal(body(provider=sent), ATTEMPT) == "body_field_not_permitted"


def test_a_record_with_no_routing_may_not_allow_a_routing_field() -> None:
    with pytest.raises(ValueError, match="allowed_fields"):
        load(record(allowed_fields=[*UNROUTED_FIELDS, "provider"]))


def test_a_record_that_leaves_out_the_routing_key_is_refused() -> None:
    value = record()
    del value["provider"]
    with pytest.raises(ValueError, match="frozen fields"):
        load(value)


@pytest.mark.parametrize("given", [{}, [], False, 0, "", "openai"])
def test_only_null_means_no_routing_and_any_other_value_is_refused(given: Any) -> None:
    with pytest.raises(ValueError, match="routing"):
        load(record(provider=given, allowed_fields=[*UNROUTED_FIELDS, "provider"]))


@pytest.mark.parametrize("field", sorted(ROUTING))
def test_a_routed_record_still_needs_every_routing_field(field: str) -> None:
    routing = {name: value for name, value in ROUTING.items() if name != field}
    with pytest.raises(ValueError, match="routing field missing"):
        load(record(provider=routing, allowed_fields=[*UNROUTED_FIELDS, "provider"]))


def test_a_routed_record_must_still_allow_the_routing_field() -> None:
    with pytest.raises(ValueError, match="allowed_fields"):
        load(record(provider=ROUTING))


@pytest.mark.parametrize("sent, refusal", [
    ("absent", "body_field_missing"), (None, "body_routing_mismatch"), ({}, "body_routing_mismatch"),
    ({**ROUTING, "allow_fallbacks": True}, "body_routing_mismatch")])
def test_a_routed_release_still_refuses_a_body_without_its_exact_routing(sent: Any, refusal: str) -> None:
    actual = load(record(provider=ROUTING, allowed_fields=[*UNROUTED_FIELDS, "provider"]))
    assert actual.body_refusal(body() if sent == "absent" else body(provider=sent), ATTEMPT) == refusal
    assert actual.body_refusal(body(provider=ROUTING), ATTEMPT) is None
