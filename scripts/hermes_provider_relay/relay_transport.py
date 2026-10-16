"""The relay's one provider request: one HTTPS POST, built by the relay, bounded in time and size. Standard library only.

`send_once` opens a fresh TLS connection (certificate and host name verified against the configured CA), sends the
admitted body byte for byte with headers the relay chose, reads at most `max_reply_bytes + 1` bytes and closes. It never
retries, follows a redirect, streams or reuses a connection. Once the connection is open the request may have reached
the provider, so every failure after that point raises `ReplyLost`: the caller keeps the full liability.

With `gateway_socket` (CONTRACT A6) the connection is a Unix socket to the keyless egress gateway: one CONNECT naming
the fixed destination, the attempt and the grant expiry, an exact established answer, then TLS end to end for the
provider's name over that socket. The gateway never sees the key or a body byte in clear.
"""

from __future__ import annotations

import http.client
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass

from relay_admission import ProviderDestination

__all__ = ["ReplyLost", "SentReply", "connect_head", "gateway_refusal", "send_once"]

READ_CHUNK = 64 * 1024
CUT_LEAD = 0.1  # seconds: the send ends this long before the grant expiry, so its return is not late (CONTRACT A5)
GATEWAY_ANSWER_LIMIT = 1024
ESTABLISHED = b"HTTP/1.1 200 Connection Established\r\n\r\n"
REFUSED = re.compile(rb"HTTP/1\.1 403 Forbidden\r\nX-Refusal: ([a-z_]{1,64})\r\n\r\n")


class ReplyLost(RuntimeError):
    """The request may have been sent and no complete, bounded reply came back."""


@dataclass(frozen=True)
class SentReply:
    status: int
    content_type: str
    body: bytes  # at most max_reply_bytes + 1 bytes: one more than allowed shows that the reply was too large
    content_encoding: str = ""  # none is asked for; any value means the reply is refused, never decoded


def connect_head(destination: ProviderDestination, attempt_id: str, expires_at: float) -> bytes:
    target = f"{destination.host}:{destination.port}"
    return (f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\nX-Relay-Attempt: {attempt_id}\r\n"
            f"X-Relay-Expires: {float(expires_at)!r}\r\n\r\n").encode()


def gateway_refusal(answer: bytes) -> str | None:
    """None only for the exact established answer; a gateway refusal keeps its reason; anything else is invalid."""
    if answer == ESTABLISHED:
        return None
    refused = REFUSED.fullmatch(answer)
    return f"gateway_refused:{refused.group(1).decode()}" if refused else "gateway_reply_invalid"


class _GatewayRefused(OSError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _read_answer(sock: socket.socket) -> bytes:
    """The gateway's whole answer head and nothing more: no byte may follow it before the relay's TLS starts."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(GATEWAY_ANSWER_LIMIT + 1 - len(data))
        if not chunk or len(data) + len(chunk) > GATEWAY_ANSWER_LIMIT:
            raise _GatewayRefused("gateway_reply_invalid")
        data += chunk
    if not data.endswith(b"\r\n\r\n"):
        raise _GatewayRefused("gateway_reply_invalid")
    return data


class _GatewayConnection(http.client.HTTPSConnection):
    """An HTTPS connection whose socket is a CONNECT tunnel through the gateway's Unix socket."""

    def __init__(self, destination: ProviderDestination, *, socket_path: str, head: bytes, timeout: float,
                 context: ssl.SSLContext) -> None:
        super().__init__(destination.host, destination.port, timeout=timeout, context=context)
        self._socket_path, self._head = socket_path, head

    def connect(self) -> None:
        raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock = raw  # from here on the watchdog can cut it
        raw.settimeout(self.timeout)
        raw.connect(self._socket_path)
        raw.sendall(self._head)
        refusal = gateway_refusal(_read_answer(raw))
        if refusal is not None:
            raise _GatewayRefused(refusal)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def send_once(destination: ProviderDestination, *, ca_file: str, key: str, body: bytes, deadline: float,
              max_reply_bytes: int, gateway_socket: str | None = None, attempt_id: str | None = None) -> SentReply:
    """One request with ONE total deadline (a `time.time()` value) for connecting, sending and reading.

    A watchdog shuts the socket down `CUT_LEAD` seconds before the deadline, so a provider that drips its headers or
    body byte by byte cannot hold the request longer: a per-call socket timeout alone would restart for every byte. The
    lead leaves time for the thread wake-up and the return; it only shortens the request, never extends it.
    """
    if gateway_socket is not None and not attempt_id:
        raise ValueError("a send through the gateway names its attempt")
    end = deadline - CUT_LEAD
    if end - time.time() <= 0:
        raise ReplyLost("no time was left for the request")
    context = ssl.create_default_context(cafile=ca_file)  # verified certificate and host name; no system CA store
    left = end - time.time()  # after the setup above, so the watchdog and the socket end at the same fixed time
    if left <= 0:
        raise ReplyLost("no time was left for the request")
    if gateway_socket is None:
        connection = http.client.HTTPSConnection(destination.host, destination.port, timeout=left, context=context)
    else:
        connection = _GatewayConnection(destination, socket_path=gateway_socket, timeout=left, context=context,
                                        head=connect_head(destination, str(attempt_id), deadline))
    expired = threading.Event()
    held: list[socket.socket] = []  # a reply that closes the connection detaches its socket; the watchdog keeps it

    def cut() -> None:
        expired.set()
        for sock in (*held, connection.sock):
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    watchdog = threading.Timer(max(0.0, end - time.time()), cut)
    watchdog.daemon = True
    watchdog.start()
    try:
        connection.putrequest("POST", destination.path, skip_host=True, skip_accept_encoding=True)
        for name, value in (("host", f"{destination.host}:{destination.port}"), ("accept", "application/json"),
                            ("content-type", "application/json"), ("content-length", str(len(body))),
                            ("authorization", f"Bearer {key}"), ("connection", "close")):
            connection.putheader(name, value)
        connection.endheaders(body)
        held.append(connection.sock)
        if expired.is_set():  # the watchdog may have fired between the send and the line above
            raise ReplyLost("the deadline passed while sending")
        response = connection.getresponse()
        data = bytearray()
        while len(data) <= max_reply_bytes:
            chunk = response.read(min(READ_CHUNK, max_reply_bytes + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        if expired.is_set() or time.time() >= end:
            raise ReplyLost("the deadline passed before the reply was complete")
        return SentReply(response.status, response.getheader("content-type") or "", bytes(data),
                         response.getheader("content-encoding") or "")
    except _GatewayRefused as refused:
        raise ReplyLost(refused.reason) from None
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise ReplyLost(type(error).__name__) from None
    finally:
        watchdog.cancel()
        connection.close()
