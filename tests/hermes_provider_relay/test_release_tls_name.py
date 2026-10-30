"""The relay's TLS verifies the release's host name and CA pin in a real handshake (CLOUD-ORBIO-01, relay contract A8).

A loopback TLS server presents a certificate from a throwaway test CA. The relay's own `send_once` reaches it directly
(no gateway). A certificate for another name (an SNI swap) or from another CA (a CA swap) ends the attempt at the
handshake, before any request byte or the key is sent; the matching name and CA complete one request. No provider,
key or network beyond loopback is used.
"""

from __future__ import annotations

import socket
import ssl
import threading
import time
from pathlib import Path

import pytest

import relay_transport
from relay_admission import ProviderDestination
from relay_supervisor import make_provider_tls

from conftest import SENTINEL

REPLY = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"


class Server:
    """One TLS connection on loopback: it records the bytes it receives after a completed handshake."""

    def __init__(self, tls: Path) -> None:
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(tls / "server.pem"), str(tls / "server.key"))
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.received = bytearray()
        self.handshakes = 0
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        self.listener.settimeout(10)
        try:
            raw, _ = self.listener.accept()
        except OSError:
            return
        raw.settimeout(10)
        try:
            with self.context.wrap_socket(raw, server_side=True) as tls:
                self.handshakes += 1
                while not self.received.endswith(b"\r\n\r\n{}"):  # the head and the client's two-byte body
                    chunk = tls.recv(4096)
                    if not chunk:
                        return
                    self.received += chunk
                tls.sendall(REPLY)
        except (OSError, ssl.SSLError):
            pass
        finally:
            self.listener.close()

    def join(self) -> None:
        self.thread.join(timeout=15)


def send(port: int, ca: Path) -> relay_transport.SentReply:
    return relay_transport.send_once(ProviderDestination("localhost", port, "/v1/chat/completions"),
                                     ca_file=str(ca), key=SENTINEL, body=b"{}", deadline=time.time() + 20,
                                     max_reply_bytes=1024)


def test_the_release_host_and_its_ca_complete_one_request(tmp_path: Path) -> None:
    make_provider_tls(tmp_path / "tls", ("localhost",))
    server = Server(tmp_path / "tls")
    reply = send(server.port, tmp_path / "tls" / "ca.pem")
    server.join()
    assert (reply.status, reply.body) == (200, b"{}")
    assert server.received.startswith(b"POST /v1/chat/completions HTTP/1.1\r\n")


def test_a_certificate_for_another_name_is_refused_before_any_byte_is_sent(tmp_path: Path) -> None:
    make_provider_tls(tmp_path / "tls", ("api.orbio.so",))  # a real CA, but not the release's host name
    server = Server(tmp_path / "tls")
    with pytest.raises(relay_transport.ReplyLost, match="SSLCertVerificationError"):
        send(server.port, tmp_path / "tls" / "ca.pem")
    server.join()
    assert server.handshakes == 0 and bytes(server.received) == b""


def test_a_certificate_from_another_ca_is_refused_before_any_byte_is_sent(tmp_path: Path) -> None:
    make_provider_tls(tmp_path / "tls", ("localhost",))
    make_provider_tls(tmp_path / "pinned", ("localhost",))  # the pinned bundle is a different CA
    server = Server(tmp_path / "tls")
    with pytest.raises(relay_transport.ReplyLost, match="SSLCertVerificationError"):
        send(server.port, tmp_path / "pinned" / "ca.pem")
    server.join()
    assert server.handshakes == 0 and bytes(server.received) == b""
