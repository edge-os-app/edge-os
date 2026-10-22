"""The approved release record names its own destination, routing fields and CA pin (CLOUD-02). No I/O beyond tmp files.

A record naming another host, port or path loads only when it is the approved release; the gateway admits only the
approved release's host and port; an unknown routing field is refused; a CA bundle that does not match the record's pin
is refused; and the relay's TLS server name and CONNECT target are the record's host. Synthetic records only.
"""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path
from typing import Any

import pytest

import egress_gateway
import relay_admission
import relay_service
import relay_transport
from egress_gateway import AllowedTarget, ConnectRequest, Gateway, Receipts, allowed_target, parse_connect
from relay_admission import ActualReleaseUnapproved, load_actual_release
from relay_supervisor import RelaySupervisor
from test_egress_gateway import FakeSocket, Network, answer, head
from test_release_destination_golden import GOLDEN_CONNECT, RECORD
from test_relay_actual_release import ROUTING, record
from test_relay_supervisor_online import supervisor

from conftest import SENTINEL

NOW = 1_000_000.0
OTHER = {"host": "chat.provider-synthetic.example", "port": 8443, "path": "/v2/complete"}
OTHER_TARGET = AllowedTarget(OTHER["host"], OTHER["port"])


def raw_of(value: dict[str, Any]) -> tuple[bytes, str]:
    raw = json.dumps(value).encode()
    return raw, hashlib.sha256(raw).hexdigest()


# --- the record names the destination -----------------------------------------------------------------------------


def test_the_registry_approves_exactly_one_release_the_adopted_openrouter_record() -> None:
    raw = RECORD.read_bytes()
    assert relay_admission.APPROVED_ACTUAL_RELEASES == frozenset({hashlib.sha256(raw).hexdigest()})
    actual = load_actual_release(raw, hashlib.sha256(raw).hexdigest())
    assert (actual.destination.host, actual.destination.port, actual.destination.path) == (
        "openrouter.ai", 443, "/api/v1/chat/completions")


@pytest.mark.parametrize("destination", [
    OTHER,
    {"host": "localhost", "port": 443, "path": "/api/v1/chat/completions"},
    {"host": "openrouter.ai", "port": 8443, "path": "/api/v1/chat/completions"},
    {"host": "openrouter.ai", "port": 443, "path": "/v1/chat/completions"},
])
def test_a_record_naming_another_destination_is_refused_unless_it_is_the_approved_release(
        destination: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    raw, sha = raw_of(record(destination=destination))
    with pytest.raises(ActualReleaseUnapproved):  # the default registry: only the adopted OpenRouter record
        load_actual_release(raw, sha)
    with pytest.raises(ActualReleaseUnapproved):  # another record is approved instead
        load_actual_release(raw, sha, approved=frozenset({"0" * 64}))
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({sha}))  # this record IS the approved one
    actual = load_actual_release(raw, sha)
    assert (actual.destination.host, actual.destination.port, actual.destination.path) == (
        destination["host"], destination["port"], destination["path"])
    assert actual.endpoint_url == f"https://{destination['host']}{destination['path']}"


# --- routing fields -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("routing, message", [
    ({**ROUTING, "sort": "price"}, "unknown routing field refused: \\['sort'\\]"),
    ({**ROUTING, "allow_fallbacks": False, "order": ["a"]}, "unknown routing field refused: \\['order'\\]"),
    ({key: value for key, value in ROUTING.items() if key != "data_collection"}, "routing field missing"),
    ({key: value for key, value in ROUTING.items() if key != "max_price"}, "routing field missing"),
    (["only"], "routing must be an object"),
])
def test_an_unknown_or_missing_routing_field_is_refused_not_ignored(routing: Any, message: str) -> None:
    raw, sha = raw_of(record(provider=routing))
    with pytest.raises(ValueError, match=message):
        load_actual_release(raw, sha, approved=frozenset({sha}))


def test_the_approved_records_routing_is_the_only_routing_a_body_may_carry() -> None:
    raw, sha = raw_of(record(provider={**ROUTING, "only": ["provider-synthetic"]}))
    actual = load_actual_release(raw, sha, approved=frozenset({sha}))
    assert actual.provider == {**ROUTING, "only": ["provider-synthetic"]}
    body = {"model": "synthetic/model-1", "messages": [{"role": "user", "content": "x"}], "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "strict": True,
                                                                       "schema": {"type": "object"}}},
            "reasoning": {"effort": "low"}, "max_tokens": 4096, "session_id": "p05-att-1"}
    assert actual.body_refusal(json.dumps({**body, "provider": actual.provider}).encode(), "att-1") is None
    for other in (ROUTING, {**actual.provider, "sort": "price"}):
        assert actual.body_refusal(json.dumps({**body, "provider": other}).encode(), "att-1") == "body_routing_mismatch"


# --- the gateway admits the approved host and port only ------------------------------------------------------------


def connect(target: str) -> bytes:
    return head(target, headers=[f"Host: {target}", "X-Relay-Attempt: att-1", f"X-Relay-Expires: {NOW + 60}"])


def test_the_gateway_admits_only_the_approved_host_and_port() -> None:
    assert parse_connect(connect("chat.provider-synthetic.example:8443"), now=NOW,
                         allowed=OTHER_TARGET) == ConnectRequest("att-1", NOW + 60)
    for target, reason in (("openrouter.ai:443", "target_name_not_allowed"),
                           ("openrouter.ai:8443", "target_name_not_allowed"),
                           ("chat.provider-synthetic.example:443", "target_port_not_allowed"),
                           ("api.chat.provider-synthetic.example:8443", "target_name_not_allowed"),
                           ("CHAT.provider-synthetic.example:8443", "target_name_not_allowed"),
                           ("104.18.2.115:8443", "target_ip_literal")):
        assert parse_connect(connect(target), now=NOW, allowed=OTHER_TARGET) == reason, target


def test_the_gateway_resolves_and_connects_to_the_approved_host_and_port_only(tmp_path: Path) -> None:
    upstream = FakeSocket([b""])
    network = Network([answer("104.18.2.115")], upstream)
    gateway = Gateway(Receipts(tmp_path), allowed=OTHER_TARGET, resolve=network.resolve, connect=network.connect)
    target = "chat.provider-synthetic.example:8443"
    live = head(target, headers=[f"Host: {target}", "X-Relay-Attempt: att-1",
                                 f"X-Relay-Expires: {egress_gateway.time.time() + 30}"])
    record_ = gateway.handle(FakeSocket([live], end=True))
    assert record_["outcome"] == "tunnel"
    assert network.resolved == [("chat.provider-synthetic.example", 8443)]
    assert network.connected == [("104.18.2.115", 8443)]


def test_the_adopted_openrouter_connect_is_admitted_by_a_gateway_configured_from_the_record() -> None:
    raw = RECORD.read_bytes()
    actual = load_actual_release(raw, hashlib.sha256(raw).hexdigest())
    allowed = AllowedTarget(actual.destination.host, actual.destination.port)
    assert parse_connect(GOLDEN_CONNECT, now=NOW, allowed=allowed) == ConnectRequest("att-golden-1", NOW + 90)
    assert parse_connect(GOLDEN_CONNECT, now=NOW, allowed=OTHER_TARGET) == "target_name_not_allowed"


@pytest.mark.parametrize("config", [
    {}, {"destination": None}, {"destination": {"host": "openrouter.ai"}},
    {"destination": {"host": "openrouter.ai", "port": 443, "path": "/x"}},
    {"destination": {"host": "10.0.0.1", "port": 443}}, {"destination": {"host": "OpenRouter.ai", "port": 443}},
    {"destination": {"host": "openrouter.ai", "port": 0}}, {"destination": {"host": "openrouter.ai", "port": "443"}},
    {"destination": {"host": "openrouter.ai", "port": True}},
])
def test_a_gateway_config_without_one_valid_destination_admits_nothing(config: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        allowed_target({"socket": "/egress/gateway.sock", "receipts": "/gateway/receipts", **config})


def test_a_gateway_has_no_default_target(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        Gateway(Receipts(tmp_path))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Gateway(Receipts(tmp_path), allowed=("openrouter.ai", 443))  # type: ignore[arg-type]
    assert allowed_target({"destination": {"host": "openrouter.ai", "port": 443}}) == AllowedTarget("openrouter.ai", 443)


# --- the supervisor configures the gateway from the approved record -------------------------------------------------


def approved_other(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, ca: bytes = b"synthetic CA bundle"):
    bundle = tmp_path / "ca-bundle.pem"
    bundle.write_bytes(ca)
    raw, sha = raw_of(record(destination=OTHER, ca_bundle_sha256=hashlib.sha256(b"synthetic CA bundle").hexdigest()))
    path = tmp_path / "release.json"
    path.write_bytes(raw)
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({sha}))
    return load_actual_release(raw, sha), path, bundle


def test_an_actual_supervisor_gives_the_gateway_the_approved_records_host_and_port(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    actual, path, bundle = approved_other(tmp_path, monkeypatch)
    made, fake = supervisor(tmp_path, monkeypatch, release=actual.release, actual=actual, release_record=path,
                            ca_bundle_file=bundle)
    made.start()
    gateway = json.loads(made.path("gateway-config.json").read_text())
    assert gateway["destination"] == {"host": OTHER["host"], "port": OTHER["port"]} and "test_resolution" not in gateway
    assert allowed_target(gateway) == OTHER_TARGET
    relay = json.loads(made.path("relay-config.json").read_text())
    assert "destination" not in relay and relay["release_record"]["sha256"] == actual.record_sha256
    assert list(fake.runs()) == ["relay-gateway", "relay"]


def test_an_actual_supervisor_refuses_a_ca_bundle_that_does_not_match_the_records_pin(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    actual, path, bundle = approved_other(tmp_path, monkeypatch, ca=b"another bundle")
    key = tmp_path / "provider-key"
    key.write_text(SENTINEL)
    key.chmod(0o400)
    with pytest.raises(ValueError, match="CA bundle"):
        RelaySupervisor(tmp_path / "relay", actual.release, "pinned:test", "hpr-unit", key, {}, online=True,
                        actual=actual, release_record=path, ca_bundle_file=bundle)


# --- the relay sends to the approved record's destination, with its host as the TLS server name ----------------------


def relay_config(tmp_path: Path, path: Path, sha: str, ca: bytes) -> dict[str, Any]:
    for folder in ("grants", "revocations", "state", "jobs"):
        (tmp_path / folder).mkdir(exist_ok=True)
    (tmp_path / "admission-key").write_bytes(b"k" * 32)
    (tmp_path / "provider-key").write_text(SENTINEL)
    (tmp_path / "ca.pem").write_bytes(ca)
    return {"release_record": {"path": str(path), "sha256": sha}, "gateway_socket": "/relay/egress/gateway.sock",
            "channel_roots": {"jobs": str(tmp_path / "jobs")},
            "paths": {"provider_key": str(tmp_path / "provider-key"), "admission_key": str(tmp_path / "admission-key"),
                      "provider_ca": str(tmp_path / "ca.pem"), "grants": str(tmp_path / "grants"),
                      "revocations": str(tmp_path / "revocations"), "state": str(tmp_path / "state")}}


def test_the_relay_refuses_a_ca_bundle_that_does_not_match_the_approved_records_pin(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    actual, path, _ = approved_other(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="CA bundle"):
        relay_service.Relay(relay_config(tmp_path, path, actual.record_sha256, b"another bundle"))


def test_the_relay_connects_and_verifies_tls_for_the_approved_records_host(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    actual, path, _ = approved_other(tmp_path, monkeypatch)
    relay = relay_service.Relay(relay_config(tmp_path, path, actual.record_sha256, b"synthetic CA bundle"))
    assert relay.destination == actual.destination
    assert relay.route.endpoint_url == "https://chat.provider-synthetic.example/v2/complete"
    sent: list[bytes] = []
    names: list[str] = []

    class Unix(FakeSocket):
        def __init__(self) -> None:
            super().__init__([b"HTTP/1.1 200 Connection Established\r\n\r\n"])

        def connect(self, _: str) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            sent.append(bytes(data))

    class Context:
        def wrap_socket(self, sock: Any, *, server_hostname: str) -> Any:
            names.append(server_hostname)
            raise relay_transport.ssl.SSLCertVerificationError("synthetic: stop at the TLS handshake")

    monkeypatch.setattr(relay_transport.socket, "socket", lambda family, kind: Unix() if (
        family, kind) == (socket.AF_UNIX, socket.SOCK_STREAM) else None)
    monkeypatch.setattr(relay_transport.ssl, "create_default_context", lambda **_: Context())
    with pytest.raises(relay_transport.ReplyLost):
        relay_transport.send_once(relay.destination, ca_file=relay.ca_file, key=SENTINEL, body=b"{}",
                                  deadline=relay_transport.time.time() + 30, max_reply_bytes=1024,
                                  gateway_socket=relay.gateway_socket, attempt_id="att-1")
    assert b"".join(sent).startswith(b"CONNECT chat.provider-synthetic.example:8443 HTTP/1.1\r\n")
    assert names == ["chat.provider-synthetic.example"]
