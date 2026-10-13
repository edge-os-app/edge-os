"""The relay's admission rules: signed grants for one owner/request/job/attempt/route/release, and the channel message."""

from __future__ import annotations

import base64
import json

import pytest

from relay_admission import (
    ProviderDestination, RelayRelease, channel_refusal, grant_refusal, issue_grant, parse_channel_message,
)

KEY = b"k" * 32
RELEASE = RelayRelease("local-relay-1", "authored-local-1", "AUTHORED", "fixture-model/1", 4096, 12_000, 65_536)
POLICY = {"model": "fixture-model/1", "max_output_tokens": 4096, "max_request_bytes": 12_000,
          "max_envelope_chars": 2_500, "required_extra": {}}


def grant(**changes):
    fields = dict(release=RELEASE, run_id="run-1", channel_root="root-1", owner_id="owner-a", request_id="intake-1",
                  attempt_id="att-1", scope="intake:intake-1", policy=POLICY, system_prompt="sys", user_message="task",
                  issued_at=1000.0, timeout_seconds=30.0, key=KEY)
    fields.update(changes)
    return issue_grant(**fields)


def message(**changes):
    value = {"attempt_id": "att-1", "route_id": "authored-local-1", "release_id": "local-relay-1",
             "body_b64": base64.b64encode(b'{"model": "fixture-model/1"}').decode()}
    value.update(changes)
    return value


def test_a_signed_open_grant_for_this_release_is_admitted_and_names_every_identity() -> None:
    issued = grant()
    assert grant_refusal(issued, KEY, RELEASE, now=1001.0) is None
    assert {k: issued[k] for k in ("owner_id", "request_id", "run_id", "attempt_id", "route_id", "release_id")} == {
        "owner_id": "owner-a", "request_id": "intake-1", "run_id": "run-1", "attempt_id": "att-1",
        "route_id": "authored-local-1", "release_id": "local-relay-1"}
    assert issued["expires_at"] == 1030.0


@pytest.mark.parametrize("change, reason", [
    ({"owner_id": "owner-b"}, "grant_signature_invalid"),  # altered after signing: another owner
    ({"attempt_id": "att-2"}, "grant_signature_invalid"),
    ({"expires_at": 9999.0}, "grant_signature_invalid"),
    ({"mac": "0" * 64}, "grant_signature_invalid"),
    ({"extra": 1}, "grant_fields_invalid"),
])
def test_a_grant_changed_after_signing_is_refused(change, reason) -> None:
    assert grant_refusal({**grant(), **change}, KEY, RELEASE, now=1001.0) == reason


def test_a_grant_signed_with_another_key_or_for_another_release_or_expired_is_refused() -> None:
    assert grant_refusal(grant(key=b"x" * 32), KEY, RELEASE, now=1001.0) == "grant_signature_invalid"
    other = RelayRelease("local-relay-2", "authored-local-1", "AUTHORED", "fixture-model/1", 4096, 12_000, 65_536)
    assert grant_refusal(grant(release=other), KEY, RELEASE, now=1001.0) == "grant_release_mismatch"
    assert grant_refusal(grant(), KEY, RELEASE, now=1030.0) == "grant_expired"
    assert grant_refusal(grant(), KEY, RELEASE, now=990.0) == "grant_not_yet_valid"
    assert grant_refusal("not a grant", KEY, RELEASE, now=1001.0) == "grant_fields_invalid"


def test_the_channel_message_must_name_exactly_the_grant_identities_and_carry_only_a_bounded_body() -> None:
    issued = grant()
    assert channel_refusal(message(), issued, RELEASE) is None
    assert channel_refusal(message(attempt_id="att-2"), issued, RELEASE) == "attempt_mismatch"
    assert channel_refusal(message(route_id="other-route"), issued, RELEASE) == "route_mismatch"
    assert channel_refusal(message(release_id="local-relay-2"), issued, RELEASE) == "release_mismatch"
    assert channel_refusal(message(authorization="Bearer stolen"), issued, RELEASE) == "channel_field_not_permitted"
    assert channel_refusal(message(url="https://elsewhere.invalid/"), issued, RELEASE) == "channel_field_not_permitted"
    assert channel_refusal(message(body_b64="%%%"), issued, RELEASE) == "body_not_base64"
    big = base64.b64encode(b"x" * 12_001).decode()
    assert channel_refusal(message(body_b64=big), issued, RELEASE) == "request_too_large"
    assert channel_refusal({k: v for k, v in message().items() if k != "release_id"}, issued, RELEASE) == "channel_field_missing"


def test_a_channel_file_must_be_one_json_object_without_repeated_keys() -> None:
    assert parse_channel_message(json.dumps(message()).encode()) == message()
    assert parse_channel_message(b'{"attempt_id": "a", "attempt_id": "b"}') is None
    assert parse_channel_message(b"[1]") is None
    assert parse_channel_message(b"\xff") is None


def test_release_and_destination_are_bounded_and_only_authored_in_this_milestone() -> None:
    with pytest.raises(ValueError):
        RelayRelease("local-relay-1", "authored-local-1", "ACTUAL", "m", 4096, 12_000, 65_536)
    with pytest.raises(ValueError):
        RelayRelease("local-relay-1", "authored-local-1", "AUTHORED", "m", 4096, 12_000, 2 * 1024 * 1024)
    assert ProviderDestination("authored-provider", 8443, "/v1/chat/completions").path == "/v1/chat/completions"
    for host, port, path in (("a b", 443, "/x"), ("h", 0, "/x"), ("h", 443, "x"), ("h", 443, "/x?y=1"),
                             ("user@h", 443, "/x")):
        with pytest.raises(ValueError):
            ProviderDestination(host, port, path)
