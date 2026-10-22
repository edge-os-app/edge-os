"""With the adopted OpenRouter release, the bytes the relay sends stay exactly those of the base behavior (CLOUD-02).

The destination, SNI host and routing come from the approved release record; this golden test pins what that record
makes the relay send: the gateway CONNECT head, the TLS server name and the plaintext HTTP request inside TLS. In-memory
sockets and a fake TLS context: no network, no real socket, no key (the key is a synthetic sentinel).
"""

from __future__ import annotations

import hashlib
import io
import socket
from pathlib import Path
from typing import Any

import pytest

import relay_transport
from relay_admission import load_actual_release
from relay_transport import send_once

REPO = Path(__file__).resolve().parents[2]
RECORD = REPO / "docs/qualification/hermes-actual-operation/release/hermes_first_call_record.json"
KEY = "sk-test-GOLDEN-SENTINEL-0000"  # synthetic: no provider knows it
BODY = b'{"model":"openai/gpt-6.1-sol","messages":[{"role":"user","content":"x"}]}'
NOW = 1_000_000.0
REPLY = (b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 2\r\nconnection: close\r\n\r\n{}")

# Captured from the base commit 00f058279487d6383adf96de54f8d3aa6253c421 with the same inputs.
GOLDEN_CONNECT = (b"CONNECT openrouter.ai:443 HTTP/1.1\r\nHost: openrouter.ai:443\r\nX-Relay-Attempt: att-golden-1\r\n"
                  b"X-Relay-Expires: 1000090.0\r\n\r\n")
GOLDEN_SNI = "openrouter.ai"
GOLDEN_REQUEST = (b"POST /api/v1/chat/completions HTTP/1.1\r\nhost: openrouter.ai:443\r\naccept: application/json\r\n"
                  b"content-type: application/json\r\ncontent-length: 73\r\n"
                  b"authorization: Bearer sk-test-GOLDEN-SENTINEL-0000\r\nconnection: close\r\n\r\n" + BODY)


class Recorder:
    """One in-memory socket end: records what is sent and plays back `answer`."""

    def __init__(self, answer: bytes) -> None:
        self.answer, self.sent = answer, b""

    def settimeout(self, _: Any) -> None:
        pass

    def connect(self, _: Any) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent += bytes(data)

    def recv(self, size: int) -> bytes:
        data, self.answer = self.answer[:size], self.answer[size:]
        return data

    def makefile(self, *_: Any, **__: Any) -> io.BytesIO:
        return io.BytesIO(self.answer)

    def shutdown(self, _: int) -> None:
        pass

    def close(self) -> None:
        pass


def test_the_adopted_openrouter_release_sends_the_base_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = RECORD.read_bytes()
    actual = load_actual_release(raw, hashlib.sha256(raw).hexdigest())  # the default registry: no test approval
    unix = Recorder(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    tls = Recorder(REPLY)
    names: list[str] = []

    class Context:
        def wrap_socket(self, sock: Any, *, server_hostname: str) -> Recorder:
            assert sock is unix
            names.append(server_hostname)
            return tls

    monkeypatch.setattr(relay_transport.socket, "socket", lambda family, kind: unix if (
        family, kind) == (socket.AF_UNIX, socket.SOCK_STREAM) else None)
    monkeypatch.setattr(relay_transport.ssl, "create_default_context", lambda **_: Context())
    monkeypatch.setattr(relay_transport.time, "time", lambda: NOW)
    reply = send_once(actual.destination, ca_file="unused", key=KEY, body=BODY, deadline=NOW + 90,
                      max_reply_bytes=actual.release.max_reply_bytes, gateway_socket="/relay/egress/gateway.sock",
                      attempt_id="att-golden-1")
    assert (reply.status, reply.body) == (200, b"{}")
    assert unix.sent == GOLDEN_CONNECT
    assert names == [GOLDEN_SNI]
    assert tls.sent == GOLDEN_REQUEST
