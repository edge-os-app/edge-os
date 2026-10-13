"""The relay process's own rules, driven through its grant, revocation and channel folders. Host processes on loopback.

Every refusal must happen before any provider request: no start record and no provider receipt. Every possible request
must have a start record first, and no attempt may ever cause a second provider request: not on a duplicate channel
message, not on a restart. Egress enforcement is not shown here; the Docker tests show it.
"""

from __future__ import annotations

import base64
import json
import os
import time

import pytest

from host_relay import HostRelay, body
from leak_scan import find_leaks
from relay_admission import RelayRelease
from relay_harness import RELEASE

from conftest import SENTINEL

USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
CONTENT = {"kind": "content", "content": "{\"ok\": true}", "finish_reason": "stop", "usage": USAGE}


@pytest.fixture
def host(tmp_path):
    key = tmp_path / "provider-key"
    key.write_text(SENTINEL)
    relay = HostRelay(tmp_path / "relay", RELEASE, key).start()
    yield relay
    relay.stop()
    assert find_leaks(tmp_path / "relay", SENTINEL) == []  # no record, reply, receipt or event holds the key


def nothing_sent(host: HostRelay, attempt: str) -> bool:
    return host.record(attempt, "started") is None and host.receipts(attempt) == []


def test_an_admitted_request_is_sent_once_with_the_relay_key_and_its_reply_returns_through_the_channel(host) -> None:
    host.script("a1", CONTENT)
    host.grant("a1")
    host.request("a1")

    reply = host.reply("a1")

    assert reply["outcome"] == "reply" and reply["status"] == 200
    assert json.loads(base64.b64decode(reply["body_b64"]))["usage"] == USAGE
    [receipt] = host.receipts("a1")
    assert receipt["bearer_matches"] is True and receipt["body_sha256"] == host.record("a1", "started")["body_sha256"]
    assert host.record("a1", "finished", 5)["usage"] == USAGE
    host.revoke("a1")
    assert host.record("a1", "closed", 5)["started"] is True


@pytest.mark.parametrize("change, reason", [
    ({"owner_id": "owner-b"}, "grant_signature_invalid"),  # a cross-owner grant: changed after signing
    ({"request_id": "intake-2"}, "grant_signature_invalid"),
    ({"expires_at": time.time() + 3600}, "grant_signature_invalid"),
])
def test_a_grant_changed_after_signing_admits_nothing(host, change, reason) -> None:
    host.script("a2", CONTENT)
    host.grant("a2", **change)
    host.request("a2")
    assert host.reply("a2") == {"attempt_id": "a2", "outcome": "refused", "refusal": reason, "before_send": True}
    assert nothing_sent(host, "a2") and host.record("a2", "closed")["started"] is False


def test_a_grant_signed_with_another_key_or_for_another_release_admits_nothing(host) -> None:
    host.script("a3", CONTENT)
    host.grant("a3", key=b"w" * 32)
    host.request("a3")
    assert host.reply("a3")["refusal"] == "grant_signature_invalid"
    other = RelayRelease("local-relay-2", RELEASE.route_id, "AUTHORED", RELEASE.model, RELEASE.max_output_tokens,
                         RELEASE.max_request_bytes, RELEASE.max_reply_bytes)
    host.grant("a4", release=other)
    host.request("a4")
    assert host.reply("a4")["refusal"] == "grant_release_mismatch"
    assert nothing_sent(host, "a3") and nothing_sent(host, "a4")


def test_a_stale_grant_closes_at_its_expiry_and_a_later_request_is_never_sent(host) -> None:
    host.script("a5", CONTENT)
    host.grant("a5", timeout_seconds=0.3)
    closed = host.record("a5", "closed", 5)
    assert (closed["started"], closed["why"]) == (False, "expired")
    host.request("a5")
    time.sleep(0.5)
    assert nothing_sent(host, "a5") and not (host.channel("a5") / "reply.json").exists()


def test_cancellation_before_the_request_closes_the_attempt_and_nothing_is_sent_afterwards(host) -> None:
    host.script("a6", CONTENT)
    host.grant("a6")
    host.revoke("a6")
    assert host.record("a6", "closed", 5)["started"] is False
    host.request("a6")
    time.sleep(0.5)
    assert nothing_sent(host, "a6")


def test_cancellation_after_a_possible_request_records_it_as_started_and_its_lost_reply_holds(host) -> None:
    host.script("a7", {"kind": "hang"})
    host.grant("a7", timeout_seconds=2.0)
    host.request("a7")
    host.record("a7", "started", 5)
    host.revoke("a7")
    assert host.record("a7", "closed", 5)["started"] is True
    assert host.record("a7", "finished", 5)["outcome"] == "lost"  # the relay stopped waiting at the grant's expiry
    assert len(host.receipts("a7")) == 1  # one request; its job is over, so no late reply enters the sealed output


@pytest.mark.parametrize("message, reason", [
    ({"attempt_id": "other-attempt"}, "attempt_mismatch"),
    ({"route_id": "another-route"}, "route_mismatch"),
    ({"release_id": "local-relay-2"}, "release_mismatch"),
    ({"authorization": "Bearer sk-attacker"}, "channel_field_not_permitted"),
    ({"url": "https://elsewhere.invalid/v1"}, "channel_field_not_permitted"),
    ({"headers": {"x-provider": "other"}}, "channel_field_not_permitted"),
    ({"body_b64": "not base64!"}, "body_not_base64"),
    ({"body_b64": base64.b64encode(b"x" * 12_001).decode()}, "request_too_large"),
    ({"body_b64": base64.b64encode(body("a8", model="other-model/9")).decode()}, "guard:model_not_as_configured"),
    ({"body_b64": base64.b64encode(body("a8", session_id="p05-victim")).decode()}, "body_attempt_mismatch"),
    ({"body_b64": base64.b64encode(body("a8", session_id=None)).decode()}, "body_attempt_mismatch"),
    ({"body_b64": base64.b64encode(body("a8", stream=True)).decode()}, "guard:unpermitted_field"),
    ({"body_b64": base64.b64encode(body("a8", max_tokens=99_999)).decode()}, "guard:output_limit_not_as_configured"),
    ({"body_b64": base64.b64encode(body("a8", provider={"order": ["x"]})).decode()}, "guard:unpermitted_field"),
])
def test_an_altered_channel_message_is_refused_before_any_request(host, message, reason) -> None:
    host.script("a8", CONTENT)
    host.grant("a8")
    host.request("a8", **message)
    assert host.reply("a8")["refusal"] == reason
    assert nothing_sent(host, "a8") and host.record("a8", "closed")["started"] is False


@pytest.mark.parametrize("raw", [b"{not json", b"[1, 2]", b'{"attempt_id": "a9", "attempt_id": "a9"}', b"x" * 30_000])
def test_a_malformed_or_oversized_channel_file_is_refused(host, raw) -> None:
    host.grant("a9")
    host.request("a9", raw=raw)
    assert host.reply("a9")["refusal"] == "channel_message_invalid" and nothing_sent(host, "a9")


def test_a_linked_request_file_or_two_channels_for_one_attempt_are_refused(host, tmp_path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"attempt_id": "a10"}))
    host.grant("a10")
    os.symlink(outside, host.channel("a10") / "request.json")
    assert host.reply("a10")["refusal"] == "channel_message_invalid" and nothing_sent(host, "a10")
    host.channel("a11", sequence=1)
    host.channel("a11", sequence=2)
    host.grant("a11")
    host.request("a11")
    time.sleep(0.5)
    assert nothing_sent(host, "a11")  # neither folder is trusted as the channel


def test_a_planted_reply_link_is_never_written_through(host, tmp_path) -> None:
    target = tmp_path / "target"
    host.script("a12", CONTENT)
    os.symlink(target, host.channel("a12") / "reply.json")
    host.grant("a12")
    host.request("a12")
    host.record("a12", "finished", 5)
    time.sleep(0.2)
    assert not target.exists() and [e["kind"] for e in host.events("a12")] == ["reply_not_written"]


def test_a_duplicate_or_recovered_request_never_causes_a_second_provider_request(host) -> None:
    host.script("a13", CONTENT)
    host.grant("a13")
    host.request("a13")
    assert host.reply("a13")["outcome"] == "reply"
    os.unlink(host.channel("a13") / "reply.json")
    host.request("a13")  # the job asks again
    time.sleep(0.4)
    host.kill_relay()
    host.start_relay()  # a restarted relay finds the same request
    time.sleep(0.4)
    assert len(host.receipts("a13")) == 1 and [e["reason"] for e in host.events("a13")] == ["already_started"]


def test_a_relay_killed_after_a_possible_request_never_sends_it_again_and_reports_it_lost(host) -> None:
    host.script("a14", {"kind": "hang"})
    host.grant("a14")
    host.request("a14")
    host.record("a14", "started", 5)
    deadline = time.monotonic() + 5
    while not host.receipts("a14") and time.monotonic() < deadline:
        time.sleep(0.01)
    host.kill_relay()

    host.start_relay()

    assert host.record("a14", "finished", 5)["outcome"] == "unknown_restart"
    assert host.reply("a14")["outcome"] == "lost" and len(host.receipts("a14")) == 1
    host.revoke("a14")
    assert host.record("a14", "closed", 5)["started"] is True


@pytest.mark.parametrize("script, refusal", [
    ({**CONTENT, "kind": "oversized_reply", "bytes": 70_000}, "reply_too_large"),
    ({"kind": "redirect"}, "reply_redirect_refused"),
    ({"kind": "stream", **{k: v for k, v in CONTENT.items() if k != "kind"}}, "reply_not_json"),
])
def test_a_reply_the_route_does_not_allow_is_dropped_but_the_request_counts(host, script, refusal) -> None:
    host.script("a15", script)
    host.grant("a15")
    host.request("a15")
    assert host.reply("a15") == {"attempt_id": "a15", "outcome": "refused", "refusal": refusal, "before_send": False}
    assert host.record("a15", "finished", 5)["outcome"] == "refused_reply" and len(host.receipts("a15")) == 1


def test_a_lost_reply_is_recorded_lost_with_one_provider_request(host) -> None:
    host.script("a16", {"kind": "lost_reply"})
    host.grant("a16")
    host.request("a16")
    assert host.reply("a16")["outcome"] == "lost"
    assert host.record("a16", "finished", 5)["outcome"] == "lost" and len(host.receipts("a16")) == 1


def test_a_request_without_any_grant_is_never_looked_at(host) -> None:
    host.script("a17", CONTENT)
    host.request("a17")
    time.sleep(0.3)
    assert nothing_sent(host, "a17") and not (host.channel("a17") / "reply.json").exists()


def test_a_new_grant_is_served_however_many_earlier_attempts_are_closed(host) -> None:
    for index in range(1100):  # more closed attempts than the relay serves open grants in one pass
        attempt = f"a00-old-{index:04d}"
        (host.root / "grants" / f"{attempt}.json").write_text("{}")
        (host.root / "state" / attempt).mkdir()
        (host.root / "state" / attempt / "closed.json").write_text('{"started": false}')
    host.script("zz-new", CONTENT)
    host.grant("zz-new")
    host.request("zz-new")
    assert host.reply("zz-new", 15)["outcome"] == "reply" and len(host.receipts("zz-new")) == 1


def test_a_malformed_grant_does_not_stop_the_relay_for_other_attempts(host) -> None:
    (host.root / "grants" / "bad-1.json").write_text(json.dumps({"attempt_id": "bad-1"}))  # no other field
    host.request("bad-1")
    host.script("a18", CONTENT)
    host.grant("a18")
    host.request("a18")
    assert host.reply("a18")["outcome"] == "reply" and host.relay.poll() is None
    assert nothing_sent(host, "bad-1")


def test_no_reply_is_written_into_a_channel_after_its_grant_was_revoked(host) -> None:
    host.script("a19", {"kind": "hang"})
    host.grant("a19", timeout_seconds=1.5)
    host.request("a19")
    host.record("a19", "started", 5)
    host.revoke("a19")  # the job is over and its output sealed
    assert host.record("a19", "finished", 5)["outcome"] == "lost"
    time.sleep(0.3)
    assert not (host.channel("a19") / "reply.json").exists()
    assert "late_reply_not_written" in [e["kind"] for e in host.events("a19")]
