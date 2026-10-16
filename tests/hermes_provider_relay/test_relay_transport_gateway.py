"""The relay's send through the keyless gateway (CONTRACT A6): one CONNECT on the private Unix socket, then TLS end to
end for the provider's name. In-memory sockets and a fake TLS context: no network, no real socket."""

from __future__ import annotations

import socket
import ssl
from typing import Any

import pytest

import relay_transport
from relay_admission import ProviderDestination
from relay_transport import ReplyLost, connect_head, gateway_refusal, send_once

DESTINATION = ProviderDestination("openrouter.ai", 443, "/api/v1/chat/completions")


def test_the_connect_head_names_only_the_fixed_destination_the_attempt_and_the_grant_expiry() -> None:
    assert connect_head(DESTINATION, "att-1", 1_000_090.25) == (
        b"CONNECT openrouter.ai:443 HTTP/1.1\r\nHost: openrouter.ai:443\r\nX-Relay-Attempt: att-1\r\n"
        b"X-Relay-Expires: 1000090.25\r\n\r\n")


@pytest.mark.parametrize("head, refusal", [
    (b"HTTP/1.1 200 Connection Established\r\n\r\n", None),
    (b"HTTP/1.1 403 Forbidden\r\nX-Refusal: target_name_not_allowed\r\n\r\n", "gateway_refused:target_name_not_allowed"),
    (b"HTTP/1.1 403 Forbidden\r\nX-Refusal: <script>\r\n\r\n", "gateway_reply_invalid"),
    (b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n", "gateway_reply_invalid"),
    (b"HTTP/1.0 200 OK\r\n\r\n", "gateway_reply_invalid"),
    (b"garbage\r\n\r\n", "gateway_reply_invalid"),
])
def test_only_an_established_answer_opens_the_tunnel(head: bytes, refusal: str | None) -> None:
    assert gateway_refusal(head) == refusal


class FakeUnix:
    """The relay's end of the gateway socket: records what is sent and plays back the gateway's answer."""

    instances: list[FakeUnix] = []

    def __init__(self, family: int, kind: int, *, answer: bytes, connect_error: OSError | None) -> None:
        assert (family, kind) == (socket.AF_UNIX, socket.SOCK_STREAM)
        self.answer, self.connect_error = answer, connect_error
        self.path: str | None = None
        self.sent = b""
        self.timeout: float | None = None
        FakeUnix.instances.append(self)

    def settimeout(self, value: float | None) -> None:
        self.timeout = value

    def connect(self, path: str) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.path = path

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        data, self.answer = self.answer[:size], self.answer[size:]
        return data

    def shutdown(self, _: int) -> None:
        pass

    def close(self) -> None:
        pass


class FakeContext:
    wrapped: list[tuple[Any, str]] = []

    def wrap_socket(self, sock: Any, *, server_hostname: str) -> Any:
        FakeContext.wrapped.append((sock, server_hostname))
        raise ssl.SSLCertVerificationError("synthetic: stop at the TLS handshake")


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch):
    FakeUnix.instances, FakeContext.wrapped = [], []

    def install(answer: bytes = b"HTTP/1.1 200 Connection Established\r\n\r\n", connect_error: OSError | None = None):
        monkeypatch.setattr(relay_transport.socket, "socket",
                            lambda family, kind: FakeUnix(family, kind, answer=answer, connect_error=connect_error))
        monkeypatch.setattr(relay_transport.ssl, "create_default_context", lambda **_: FakeContext())
    return install


def send(deadline_in: float = 30.0) -> float:
    deadline = relay_transport.time.time() + deadline_in
    send_once(DESTINATION, ca_file="unused", key="sk-test-synthetic", body=b"{}", deadline=deadline,
              max_reply_bytes=65_536, gateway_socket="/relay/egress/gateway.sock", attempt_id="att-1")
    return deadline


def test_an_established_tunnel_is_wrapped_in_tls_for_the_provider_name(gateway: Any) -> None:
    gateway()
    with pytest.raises(ReplyLost, match="SSLCertVerificationError"):
        send()
    unix = FakeUnix.instances[0]
    assert unix.path == "/relay/egress/gateway.sock"
    assert unix.sent.startswith(b"CONNECT openrouter.ai:443 HTTP/1.1\r\n") and b"X-Relay-Attempt: att-1\r\n" in unix.sent
    assert b"Bearer" not in unix.sent and b"sk-test" not in unix.sent  # the gateway never sees the key or the body
    assert [(sock, name) for sock, name in FakeContext.wrapped] == [(unix, "openrouter.ai")]
    assert 0 < unix.timeout <= 30.0 - relay_transport.CUT_LEAD


def test_the_connect_carries_the_fixed_grant_expiry_not_the_relays_earlier_cut(gateway: Any,
                                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relay_transport.time, "time", lambda: 1_000_000.0)
    gateway()
    with pytest.raises(ReplyLost):
        send(90.0)
    assert b"X-Relay-Expires: 1000090.0\r\n" in FakeUnix.instances[0].sent


def test_a_gateway_refusal_is_lost_before_any_tls_or_body(gateway: Any) -> None:
    gateway(answer=b"HTTP/1.1 403 Forbidden\r\nX-Refusal: dns_answer_not_global\r\n\r\n")
    with pytest.raises(ReplyLost, match="^gateway_refused:dns_answer_not_global$"):
        send()
    assert FakeContext.wrapped == []
    assert FakeUnix.instances[0].sent.count(b"CONNECT") == 1


@pytest.mark.parametrize("answer", [
    b"HTTP/1.1 200 Connection Established\r\n\r\n\x16\x03",  # bytes after the answer: not a clean tunnel
    b"HTTP/1.1 200 Connection Established\r\n",  # closed before the answer ended
    b"H" * 2000,
])
def test_an_unclean_gateway_answer_is_lost_before_tls(gateway: Any, answer: bytes) -> None:
    gateway(answer=answer)
    with pytest.raises(ReplyLost, match="gateway_reply_invalid"):
        send()
    assert FakeContext.wrapped == []


@pytest.mark.parametrize("error", [FileNotFoundError(), ConnectionRefusedError()])
def test_a_missing_or_refusing_gateway_socket_is_lost(gateway: Any, error: OSError) -> None:
    gateway(connect_error=error)
    with pytest.raises(ReplyLost, match=type(error).__name__):
        send()
    assert FakeContext.wrapped == []


def test_the_gateway_route_needs_an_attempt_id(gateway: Any) -> None:
    gateway()
    with pytest.raises(ValueError):
        send_once(DESTINATION, ca_file="unused", key="k", body=b"{}", deadline=relay_transport.time.time() + 5,
                  max_reply_bytes=1, gateway_socket="/relay/egress/gateway.sock")


def test_no_accept_encoding_is_ever_sent() -> None:
    source = relay_transport.__file__
    text = open(source, encoding="utf-8").read()
    assert "skip_accept_encoding=True" in text and '"accept-encoding"' not in text.lower()
