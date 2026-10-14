"""The relay's one provider request: one HTTPS POST, built by the relay, bounded in time and size. Standard library only.

`send_once` opens a fresh TLS connection (certificate and host name verified against the configured CA), sends the
admitted body byte for byte with headers the relay chose, reads at most `max_reply_bytes + 1` bytes and closes. It never
retries, follows a redirect, streams or reuses a connection. Once the connection is open the request may have reached
the provider, so every failure after that point raises `ReplyLost`: the caller keeps the full liability.
"""

from __future__ import annotations

import http.client
import socket
import ssl
import threading
import time
from dataclasses import dataclass

from relay_admission import ProviderDestination

__all__ = ["ReplyLost", "SentReply", "send_once"]

READ_CHUNK = 64 * 1024


class ReplyLost(RuntimeError):
    """The request may have been sent and no complete, bounded reply came back."""


@dataclass(frozen=True)
class SentReply:
    status: int
    content_type: str
    body: bytes  # at most max_reply_bytes + 1 bytes: one more than allowed shows that the reply was too large


def send_once(destination: ProviderDestination, *, ca_file: str, key: str, body: bytes, deadline: float,
              max_reply_bytes: int) -> SentReply:
    """One request with ONE total deadline (a `time.time()` value) for connecting, sending and reading.

    A watchdog shuts the socket down when the deadline comes, so a provider that drips its headers or body byte by
    byte cannot hold the request longer: a per-call socket timeout alone would restart for every byte.
    """
    if deadline - time.time() <= 0:
        raise ReplyLost("no time was left for the request")
    context = ssl.create_default_context(cafile=ca_file)  # verified certificate and host name; no system CA store
    left = deadline - time.time()  # after the setup above, so the watchdog and the socket end at the fixed deadline
    if left <= 0:
        raise ReplyLost("no time was left for the request")
    connection = http.client.HTTPSConnection(destination.host, destination.port, timeout=left, context=context)
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

    watchdog = threading.Timer(max(0.0, deadline - time.time()), cut)
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
        if expired.is_set() or time.time() >= deadline:
            raise ReplyLost("the deadline passed before the reply was complete")
        return SentReply(response.status, response.getheader("content-type") or "", bytes(data))
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise ReplyLost(type(error).__name__) from None
    finally:
        watchdog.cancel()
        connection.close()
