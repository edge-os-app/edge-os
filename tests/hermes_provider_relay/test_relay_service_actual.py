"""The relay process's ACTUAL path (CONTRACT A6), driven in process with a fake send: no network, no socket, no key.

A synthetic release record is approved only inside each test. The relay must refuse to start for an unapproved record,
a CA file of another hash or a missing gateway socket; refuse a body outside the record before any start record; send
once through the gateway; and count only a complete reply, keeping everything else UNKNOWN.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

import relay_admission
import relay_service
from host_relay import SYSTEM, TASK, body
from provider_guard import GuardPolicy
from relay_admission import RelayRelease, issue_grant
from relay_transport import ReplyLost, SentReply

from conftest import SENTINEL

SCHEMA = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {"type": "object"}}}
ROUTING = {"only": ["synthetic-slug"], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
           "max_price": {"prompt": 1, "completion": 2}}
REASONING = {"effort": "low"}
EXTRA = {"stream": False, "provider": ROUTING, "reasoning": REASONING, "response_format": SCHEMA}
SOCKET = "/relay/egress/gateway.sock"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def record(ca: bytes) -> dict[str, Any]:
    return {"release_id": "rel-synthetic-1", "route_id": "route-synthetic", "kind": "ACTUAL",
            "approval": {"path": "/synthetic/approval.md", "sha256": "a" * 64},
            "destination": {"host": "openrouter.ai", "port": 443, "path": "/api/v1/chat/completions"},
            "ca_bundle_sha256": hashlib.sha256(ca).hexdigest(), "model": "fixture-model/1", "provider": ROUTING,
            "max_tokens": 4096, "reasoning": REASONING, "response_format_sha256": hashlib.sha256(canonical(SCHEMA)).hexdigest(),
            "stream": False, "allowed_fields": ["model", "messages", "stream", "response_format", "provider", "reasoning",
                                                "max_tokens", "session_id"],
            "max_request_bytes": 12_000, "max_reply_bytes": 65_536, "timeout_seconds": 90,
            "price_snapshot_sha256": "c" * 64}


class Rig:
    """The relay's folders and config, as the supervisor would write them, and a fake send that counts calls."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch, *, approve: bool = True, ca_matches: bool = True,
                 gateway: bool = True) -> None:
        for folder in ("grants", "revocations", "state", "jobs"):
            (root / folder).mkdir(parents=True)
        self.root, self.admission_key = root, secrets.token_bytes(32)
        (root / "admission-key").write_bytes(self.admission_key)
        (root / "provider-key").write_text(SENTINEL)
        (root / "ca.pem").write_bytes(b"synthetic CA bundle")
        raw = json.dumps(record(b"synthetic CA bundle" if ca_matches else b"another bundle")).encode()
        (root / "release.json").write_bytes(raw)
        self.record_sha = hashlib.sha256(raw).hexdigest()
        if approve:
            monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({self.record_sha}))
        self.config = {"release_record": {"path": str(root / "release.json"), "sha256": self.record_sha},
                       "channel_roots": {"jobs": str(root / "jobs")},
                       "paths": {"provider_key": str(root / "provider-key"), "admission_key": str(root / "admission-key"),
                                 "provider_ca": str(root / "ca.pem"), "grants": str(root / "grants"),
                                 "revocations": str(root / "revocations"), "state": str(root / "state")}}
        if gateway:
            self.config["gateway_socket"] = SOCKET
        self.sends: list[dict[str, Any]] = []
        self.answer: SentReply | Exception = SentReply(200, "application/json", reply())

        def fake_send(destination: Any, **kwargs: Any) -> SentReply:
            self.sends.append({"destination": destination, **kwargs})
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer
        monkeypatch.setattr(relay_service, "send_once", fake_send)

    def relay(self) -> relay_service.Relay:
        return relay_service.Relay(json.loads(json.dumps(self.config)))

    def run(self, attempt: str, wire: bytes, *, extra: dict[str, Any] = EXTRA) -> relay_service.Relay:
        relay = self.relay()
        policy = asdict(GuardPolicy(model="fixture-model/1", max_output_tokens=4096, max_request_bytes=12_000,
                                    max_envelope_chars=2_500, required_extra=extra))
        grant = issue_grant(release=relay.release, run_id="run-1", channel_root="jobs", owner_id="owner-a",
                            request_id="intake-1", attempt_id=attempt, scope="intake:intake-1", policy=policy,
                            system_prompt=SYSTEM, user_message=TASK, issued_at=relay_service.time.time(),
                            timeout_seconds=10.0, key=self.admission_key)
        (self.root / "grants" / f"{attempt}.json").write_text(json.dumps(grant))
        channel = self.root / "jobs" / f"turn-01-{attempt}" / "output" / "relay-channel"
        channel.mkdir(parents=True)
        (channel / "request.json").write_text(json.dumps({
            "attempt_id": attempt, "route_id": relay.release.route_id, "release_id": relay.release.release_id,
            "body_b64": base64.b64encode(wire).decode()}))
        self.grant = grant
        relay._handle_request(attempt, grant)
        return relay

    def record_of(self, attempt: str, name: str) -> dict[str, Any] | None:
        path = self.root / "state" / attempt / f"{name}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def channel_reply(self, attempt: str) -> dict[str, Any]:
        return json.loads((self.root / "jobs" / f"turn-01-{attempt}" / "output" / "relay-channel" / "reply.json").read_text())


def reply(**changes: Any) -> bytes:
    value = {"id": "gen-synthetic-1", "model": "fixture-model/1",
             "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}],
             "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "cost": 0.0012}}
    value.update(changes)
    return json.dumps(value).encode()


def actual_body(attempt: str, **changes: Any) -> bytes:
    return body(attempt, **{**EXTRA, **changes})


def test_an_unapproved_record_never_starts_a_relay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch, approve=False)
    with pytest.raises(SystemExit, match="not an approved ACTUAL release"):
        rig.relay()


@pytest.mark.parametrize("change, reason", [({"ca_matches": False}, "CA bundle"), ({"gateway": False}, "gateway")])
def test_an_actual_relay_needs_the_record_ca_and_the_gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                             change: dict[str, bool], reason: str) -> None:
    rig = Rig(tmp_path, monkeypatch, **change)
    with pytest.raises(SystemExit, match=reason):
        rig.relay()


def test_an_admitted_actual_request_goes_once_through_the_gateway_and_a_complete_reply_counts(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch)
    rig.run("a1", actual_body("a1"))
    [send] = rig.sends
    assert (send["destination"].host, send["destination"].port, send["destination"].path) == (
        "openrouter.ai", 443, "/api/v1/chat/completions")
    assert (send["gateway_socket"], send["attempt_id"], send["deadline"]) == (SOCKET, "a1", rig.grant["expires_at"])
    assert send["key"] == SENTINEL and send["body"] == actual_body("a1")
    finished = rig.record_of("a1", "finished")
    assert (finished["outcome"], finished["usage"], finished["cost"], finished["generation_id"]) == (
        "reply", {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}, 0.0012, "gen-synthetic-1")
    assert rig.channel_reply("a1")["outcome"] == "reply"


def test_a_body_the_policy_admits_but_the_record_does_not_is_refused_before_any_start(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch)
    loose = {**ROUTING, "allow_fallbacks": True}  # a host policy that drifted from the frozen record
    rig.run("a2", actual_body("a2", provider=loose), extra={**EXTRA, "provider": loose})
    assert rig.sends == [] and rig.record_of("a2", "started") is None
    closed = rig.record_of("a2", "closed")
    assert (closed["started"], closed["why"]) == (False, "refused:body_routing_mismatch")


@pytest.mark.parametrize("answer, outcome, detail", [
    (SentReply(200, "application/json", reply(), "gzip"), "refused_reply", "reply_encoded_refused"),
    (SentReply(200, "application/json", reply(choices=[{"finish_reason": "length"}])), "refused_reply", "reply_truncated"),
    (SentReply(200, "application/json", reply(usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})),
     "refused_reply", "reply_cost_invalid"),
    (SentReply(302, "application/json", reply()), "refused_reply", "reply_redirect_refused"),
    (ReplyLost("gateway_refused:dns_answer_not_global"), "lost", "gateway_refused:dns_answer_not_global"),
    (ReplyLost("FileNotFoundError"), "lost", "FileNotFoundError"),
])
def test_anything_but_a_complete_reply_is_recorded_once_and_stays_unknown(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: Any, outcome: str, detail: str) -> None:
    rig = Rig(tmp_path, monkeypatch)
    rig.answer = answer
    relay = rig.run("a3", actual_body("a3"))
    finished = rig.record_of("a3", "finished")
    assert finished["outcome"] == outcome
    assert finished.get("refusal" if outcome == "refused_reply" else "error") == detail
    assert finished.get("usage") is None and finished.get("cost") is None
    assert len(rig.sends) == 1 and rig.record_of("a3", "started") is not None
    relay._handle_request("a3", rig.grant)  # the same request again: already started, never sent twice
    assert len(rig.sends) == 1


def test_an_authored_relay_also_refuses_an_encoded_reply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch, approve=False, gateway=False)
    release = RelayRelease("local-relay-1", "route-local", "AUTHORED", "fixture-model/1", 4096, 12_000, 65_536)
    rig.config = {**{k: v for k, v in rig.config.items() if k != "release_record"}, "release": release.settings(),
                  "destination": {"host": "localhost", "port": 8443, "path": "/v1/chat/completions"}}
    rig.answer = SentReply(200, "application/json", reply(), "br")
    rig.run("a4", body("a4"), extra={})
    finished = rig.record_of("a4", "finished")
    assert (finished["outcome"], finished["refusal"]) == ("refused_reply", "reply_encoded_refused")
    assert rig.sends[0]["gateway_socket"] is None
