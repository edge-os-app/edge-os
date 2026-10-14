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
    deadline = time.time() + 1.5
    with pytest.raises(ReplyLost):
        send_once(ProviderDestination("localhost", port, "/v1/chat/completions"), ca_file=str(tls / "ca.pem"),
                  key="sk-test-synthetic", body=b"{}", deadline=deadline, max_reply_bytes=65_536)
    assert time.time() <= deadline  # the fixed grant expiry itself, with no allowance


def test_a_prompt_reply_is_read_whole(tls: Path) -> None:
    port = dripping_server(tls, b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 2\r\n\r\n", b"{}",
                           pause=0)
    sent = send_once(ProviderDestination("localhost", port, "/v1/chat/completions"), ca_file=str(tls / "ca.pem"),
                     key="sk-test-synthetic", body=b"{}", deadline=time.time() + 5, max_reply_bytes=65_536)
    assert (sent.status, sent.body) == (200, b"{}")



LEAD = 0.1  # CONTRACT A5: the relay's own send ends this long before the grant expiry


class FakeWatchdog:
    daemon = False

    def __init__(self, interval: float, _cut: object, *, fires: list[float], clock: list[float]) -> None:
        fires.append(clock[0] + interval)

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        pass


def fake_send(monkeypatch: pytest.MonkeyPatch, clock: list[float], deadline: float, *, setup: float = 0.0,
              connection: object = None, fires: list[float] | None = None):
    """send_once with a fake clock: `setup` seconds pass while the TLS context is built; nothing touches a network."""
    import relay_transport

    def context(**_: object) -> ssl.SSLContext:
        clock[0] += setup
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    def no_connection(*_: object, **__: object) -> None:
        raise AssertionError("a connection was built")

    monkeypatch.setattr(relay_transport.time, "time", lambda: clock[0])
    monkeypatch.setattr(relay_transport.ssl, "create_default_context", context)
    monkeypatch.setattr(relay_transport.http.client, "HTTPSConnection", connection or no_connection)
    monkeypatch.setattr(relay_transport.threading, "Timer",
                        lambda interval, cut: FakeWatchdog(interval, cut, fires=[] if fires is None else fires,
                                                           clock=clock))
    return send_once(ProviderDestination("localhost", 8443, "/v1/chat/completions"), ca_file="unused",
                     key="sk-test-synthetic", body=b"{}", deadline=deadline, max_reply_bytes=65_536)


def test_the_watchdog_and_the_socket_end_the_lead_before_the_deadline_after_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setup time is used up first; the watchdog and the socket then end `LEAD` before the fixed expiry."""
    clock = [1_000.0]
    deadline = clock[0] + 1.5
    fires: list[float] = []
    seen: dict[str, float] = {}

    class Connection:
        sock = None

        def __init__(self, *_: object, timeout: float, **__: object) -> None:
            seen["socket_timeout_ends"] = clock[0] + timeout

        def putrequest(self, *_: object, **__: object) -> None:
            raise OSError("stop before any byte is sent")

        def close(self) -> None:
            pass

    with pytest.raises(ReplyLost):
        fake_send(monkeypatch, clock, deadline, setup=0.4, connection=Connection, fires=fires)
    assert fires == [deadline - LEAD]
    assert seen["socket_timeout_ends"] == deadline - LEAD


@pytest.mark.parametrize("left, setup", [(0.05, 0.0), (LEAD, 0.0), (0.45, 0.4)])
def test_no_connection_is_built_when_less_than_the_lead_is_left(monkeypatch: pytest.MonkeyPatch, left: float,
                                                                 setup: float) -> None:
    """Less than the lead left at the call, or after setup used it up: refused before any connection or byte."""
    clock = [1_000.0]
    with pytest.raises(ReplyLost, match="no time was left"):
        fake_send(monkeypatch, clock, clock[0] + left, setup=setup)


def test_a_reply_completed_inside_the_lead_is_lost_after_one_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """A whole reply that ends within the lead is not used: ReplyLost (UNKNOWN, full liability), and it was sent once."""
    clock = [1_000.0]
    deadline = clock[0] + 1.5
    sends: list[bytes] = []

    class Response:
        status = 200
        chunks = [b"{}", b""]

        def read(self, _: int) -> bytes:
            clock[0] = deadline - LEAD / 2  # the last byte arrives inside the lead
            return self.chunks.pop(0)

        def getheader(self, _: str) -> str:
            return "application/json"

    class Connection:
        sock = None

        def __init__(self, *_: object, **__: object) -> None:
            pass

        def putrequest(self, *_: object, **__: object) -> None:
            pass

        def putheader(self, *_: object) -> None:
            pass

        def endheaders(self, body: bytes) -> None:
            sends.append(body)

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    with pytest.raises(ReplyLost, match="deadline passed before the reply was complete"):
        fake_send(monkeypatch, clock, deadline, connection=Connection)
    assert sends == [b"{}"]
