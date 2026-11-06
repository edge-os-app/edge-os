"""Local, offline test helpers for the injected HTTP clients.

Everything here is authored and offline. ``LoopbackServer`` is an owned
``127.0.0.1`` HTTP server used to exercise the shipped transport and the real
client boundary over a real socket. ``FakeTransport``, ``FakeConnection`` and
``FakeResponse`` are deterministic seams for cases that need a fake clock or a
cancellation flag flipped mid-body. The native HyperSync pages are built from the
accepted synthetic fixtures and are labelled SYNTHETIC_FIXTURE.
"""

from __future__ import annotations

import http.server
import json
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The accepted fixtures live in the parent folder. Add it so ``import _support``
# works from this subdirectory without a second ``conftest.py`` (which would shadow
# the real ``tests/conftest.py`` under pytest's prepend import mode). Test modules
# import this module before ``_support``.
_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import _support as support  # noqa: E402
from edge_os_api.research_history.http_clients.http_transport import HttpResponse  # noqa: E402

_LOG_FIELDS = ("address", "topic0", "topic1", "topic2", "data", "block_number", "block_hash",
               "transaction_hash", "transaction_index", "log_index", "removed")


def native_log(event: Mapping[str, Any]) -> dict[str, Any]:
    return {key: event[key] for key in _LOG_FIELDS if key in event}


def native_page(next_block: int, blocks: list[dict[str, Any]], logs: list[dict[str, Any]],
                guard: dict[str, Any]) -> dict[str, Any]:
    return {
        "archive_height": support.ARCHIVE_HEIGHT,
        "next_block": next_block,
        "total_execution_time": 7,
        "data": [{"blocks": blocks, "logs": logs}],
        "rollback_guard": guard,
    }


def page_one() -> dict[str, Any]:
    guard = {"block_number": 103, "timestamp": support.P1_LAST_TS, "hash": support.HASH_103,
             "first_block_number": 100, "first_parent_hash": "0x" + "44" * 32}
    blocks = [{"number": 100, "timestamp": support.P1_FIRST_TS},
              {"number": support.EVENT_QUOTE_IN["block_number"], "timestamp": support.E1_TS},
              {"number": 103, "timestamp": support.P1_LAST_TS}]
    return native_page(104, blocks, [native_log(support.EVENT_QUOTE_IN)], guard)


def page_two() -> dict[str, Any]:
    guard = {"block_number": 110, "timestamp": support.P2_LAST_TS, "hash": support.HASH_110,
             "first_block_number": 104, "first_parent_hash": support.HASH_103}
    blocks = [{"number": 104, "timestamp": support.P2_FIRST_TS},
              {"number": support.EVENT_BASE_IN["block_number"], "timestamp": support.E2_TS},
              {"number": 110, "timestamp": support.P2_LAST_TS}]
    return native_page(111, blocks, [native_log(support.EVENT_BASE_IN)], guard)


def envio_router(_method: str, _path: str, _headers: Mapping[str, str], body: bytes) -> "Reply":
    """A HyperSync-like responder that tiles blocks 100-110 and returns two pages."""
    request = json.loads(body.decode("utf-8"))
    from_block = request.get("from_block")
    if from_block == support.SCAN["from_block"]:
        return Reply(body=json.dumps(page_one()).encode("utf-8"))
    if from_block == 104:
        return Reply(body=json.dumps(page_two()).encode("utf-8"))
    return Reply(status=400, body=b"unexpected from_block")


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    delay_before_headers: float = 0.0
    chunks: list[bytes] | None = None
    pause_between_chunks: float = 0.0
    raw_http: bytes | None = None


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # keep the test output quiet
        return

    def _respond(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        reply = self.server.responder(self.command, self.path, dict(self.headers), body)
        if reply.delay_before_headers:
            time.sleep(reply.delay_before_headers)
        try:
            if reply.raw_http is not None:
                # A fully authored HTTP response written one byte at a time, to model a
                # paced provider that keeps every receive under the socket timeout.
                for byte in reply.raw_http:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    if reply.pause_between_chunks:
                        time.sleep(reply.pause_between_chunks)
                return
            self.send_response(reply.status)
            for name, value in reply.headers.items():
                self.send_header(name, value)
            if reply.chunks is not None:
                self.send_header("transfer-encoding", "chunked")
                self.end_headers()
                for chunk in reply.chunks:
                    self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
                    if reply.pause_between_chunks:
                        time.sleep(reply.pause_between_chunks)
                self.wfile.write(b"0\r\n\r\n")
            else:
                self.send_header("content-length", str(len(reply.body)))
                self.end_headers()
                self.wfile.write(reply.body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # The client timed out or cancelled and closed the socket first.
            return

    do_POST = _respond
    do_GET = _respond


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys

        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class LoopbackServer:
    """An owned 127.0.0.1 HTTP server. Bind to an ephemeral port."""

    def __init__(self, responder: Callable[[str, str, Mapping[str, str], bytes], Reply]) -> None:
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.responder = responder  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "LoopbackServer":
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"


class FakeTransport:
    """A transport seam that replays canned ``HttpResponse`` values or raises."""

    def __init__(self, replies: list[Any]) -> None:
        self._replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> HttpResponse:
        self.calls.append(kwargs)
        item = self._replies.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def response(status: int = 200, body: Any = b"", headers: Mapping[str, str] | None = None) -> HttpResponse:
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        body = body.encode("utf-8")
    return HttpResponse(status=status, headers={k.lower(): v for k, v in (headers or {}).items()}, body=body)


class FakeResponse:
    """A fake ``http.client`` response that can hook each read."""

    def __init__(self, status: int = 200, body: bytes = b"", headers: list[tuple[str, str]] | None = None,
                 read_hook: Callable[["FakeResponse"], None] | None = None) -> None:
        self.status = status
        self._body = body
        self._headers = list(headers or [])
        self._read_hook = read_hook
        self._position = 0

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self._headers)

    def read(self, amount: int) -> bytes:
        if self._read_hook is not None:
            self._read_hook(self)
        chunk = self._body[self._position:self._position + amount]
        self._position += len(chunk)
        return chunk


class FakeConnection:
    """A fake ``http.client`` connection that records requests and closes."""

    def __init__(self, response: FakeResponse, on_connect: Callable[[], None] | None = None) -> None:
        self.response = response
        self.closed = 0
        self.requests: list[tuple[str, str, bytes, dict[str, str]]] = []
        if on_connect is not None:
            on_connect()

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: Mapping[str, str] | None = None) -> None:
        self.requests.append((method, path, body or b"", dict(headers or {})))

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed += 1
