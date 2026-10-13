"""The relay's one send keeps one total deadline: a provider that drips its headers or its body cannot hold it longer."""

from __future__ import annotations

import socket
import ssl
import threading
import time
from pathlib import Path

import pytest

from relay_admission import ProviderDestination
from relay_supervisor import make_provider_tls
from relay_transport import ReplyLost, send_once


def dripping_server(tls: Path, head: bytes, body: bytes, pause: float, *, head_at_once: bool = False) -> int:
    """A loopback TLS server that answers one connection one byte at a time, `pause` seconds apart.

    With `head_at_once`, the status line and headers go out together and only the body drips.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls / "server.pem", tls / "server.key")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve() -> None:
        connection, _ = listener.accept()
        wrapped = context.wrap_socket(connection, server_side=True)
        try:
            received = b""
            while b"\r\n\r\n" not in received:  # the whole request: headers, then the declared body
                received += wrapped.recv(65536)
            headers, _, rest = received.partition(b"\r\n\r\n")
            length = int(next(line.split(b":")[1] for line in headers.split(b"\r\n")
                              if line.lower().startswith(b"content-length")))
            while len(rest) < length:
                rest += wrapped.recv(65536)
            if head_at_once:
                wrapped.sendall(head)
            for byte in (body if head_at_once else head + body):
                wrapped.sendall(bytes([byte]))
                time.sleep(pause)
            wrapped.unwrap()  # a clean TLS close after the last byte, so the client reads to the end
        except (OSError, ValueError):
            pass
        finally:
            wrapped.close()
            listener.close()

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1]


@pytest.fixture(scope="module")
def tls(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("tls")
    make_provider_tls(folder, ("localhost",))
    return folder


CLOSING = b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\nconnection: close\r\ncontent-length: 40\r\n\r\n"
SLOW_BODY = b"{" + b" " * 38 + b"}"


@pytest.mark.parametrize("head, body, head_at_once", [
    (b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 40\r\n\r\n", SLOW_BODY, False),
    (b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\nx-padding: " + b"p" * 60 + b"\r\n\r\n", b"{}", False),
    (b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 40\r\n\r\n", SLOW_BODY, True),
    (CLOSING, SLOW_BODY, True),  # the reply detaches the socket from the connection; the body still drips
    (b"HTTP/1.0 200 OK\r\ncontent-type: application/json\r\ncontent-length: 40\r\n\r\n", SLOW_BODY, True),
    (b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n\r\n", SLOW_BODY, True),  # no length: read to close
])
def test_a_dripping_reply_is_cut_at_the_deadline(tls: Path, head: bytes, body: bytes, head_at_once: bool) -> None:
    port = dripping_server(tls, head, body, pause=0.2, head_at_once=head_at_once)
    began = time.monotonic()
    with pytest.raises(ReplyLost):
        send_once(ProviderDestination("localhost", port, "/v1/chat/completions"), ca_file=str(tls / "ca.pem"),
                  key="sk-test-synthetic", body=b"{}", deadline=time.time() + 1.5, max_reply_bytes=65_536)
    assert time.monotonic() - began < 1.5 + 0.5


def test_a_prompt_reply_is_read_whole(tls: Path) -> None:
    port = dripping_server(tls, b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 2\r\n\r\n", b"{}",
                           pause=0)
    sent = send_once(ProviderDestination("localhost", port, "/v1/chat/completions"), ca_file=str(tls / "ca.pem"),
                     key="sk-test-synthetic", body=b"{}", deadline=time.time() + 5, max_reply_bytes=65_536)
    assert (sent.status, sent.body) == (200, b"{}")
