"""The Coolify API forward for the six public Hermes paths.

The forward runs in a worker thread (`anyio.to_thread.run_sync`, the anyio default limiter) because
`http.client` blocks. It reads a bounded request body, sends only allowlisted headers, never follows a redirect and
never reads an environment proxy. A transport failure becomes an explicit JSON error, never a fixture answer.
"""

from __future__ import annotations

import http.client
import logging
import socket
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

import anyio
from fastapi import Request
from fastapi.responses import JSONResponse

from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.errors import (
    AppError, internal_error, interpreter_route_failed, interpreter_timeout, interpreter_unavailable, invalid,
    not_found,
)
from edge_os_api.core.hermes_public_route import Matched, is_near_miss, match
from edge_os_api.core.limits import MAX_BODY_BYTES

log = logging.getLogger("edge_os.hermes_proxy")

CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 150.0
MAX_UPSTREAM_BYTES = 4 * 1024 * 1024
FORWARD_REQUEST_HEADERS = ("authorization", "content-type", "accept")
FORWARD_RESPONSE_HEADERS = frozenset({"content-type", "retry-after"})


def public_forward_enabled(settings: Any) -> bool:
    """Only the fixture API forwards. The host application (`hermes_local`) serves its own routes."""
    return settings.interpreter == "fixture" and (
        settings.hermes_app_url is not None or settings.env == "production")


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class _ConnectFailed(Exception):
    """The connection was not established. No request byte was sent."""


class _ReadTimedOut(Exception):
    """The request was sent, but the reply did not arrive inside the read timeout."""


class _TransportFailed(Exception):
    """Any other transport failure, including a reply that is too large."""


class _ClientGone(Exception):
    """The client disconnected while the request body was read."""


def forward(method: str, path: str, body: bytes, headers: dict[str, str], upstream_url: str) -> UpstreamResponse:
    """One blocking HTTP request to the host application. It never follows a redirect and never reads a proxy."""
    parts = urlsplit(upstream_url)
    host, port = parts.hostname, parts.port
    if host is None or port is None:
        raise _TransportFailed("the upstream URL is incomplete")
    connection = http.client.HTTPConnection(host, port, timeout=CONNECT_TIMEOUT_SECONDS)
    try:
        try:
            connection.connect()
        except socket.timeout as error:
            raise _ConnectFailed("connect timed out") from error
        except OSError as error:
            raise _ConnectFailed("connect failed") from error
        if connection.sock is not None:
            connection.sock.settimeout(READ_TIMEOUT_SECONDS)  # connect and read timeouts stay separate
        try:
            connection.putrequest(method, path, skip_accept_encoding=True)
            for name, value in headers.items():
                connection.putheader(name, value)
            connection.putheader("Content-Length", str(len(body)))
            connection.putheader("Accept-Encoding", "identity")
            connection.endheaders(body)
        except socket.timeout as error:
            raise _TransportFailed("write timed out") from error
        except (http.client.HTTPException, OSError) as error:
            raise _TransportFailed("write failed") from error
        try:
            response = connection.getresponse()
            payload = response.read(MAX_UPSTREAM_BYTES + 1)
        except socket.timeout as error:
            raise _ReadTimedOut("read timed out") from error
        except (http.client.HTTPException, OSError) as error:
            raise _TransportFailed("read failed") from error
        if len(payload) > MAX_UPSTREAM_BYTES:
            raise _TransportFailed("response too large")
        returned = {name: value for name, value in response.getheaders()
                    if name.lower() in FORWARD_RESPONSE_HEADERS}
        return UpstreamResponse(response.status, returned, payload)
    finally:
        connection.close()


async def _read_body(request: Request, receive: Any) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise invalid("/", "The request body is too large.", "body_too_large")
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise _ClientGone()
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise invalid("/", "The request body is too large.", "body_too_large")
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


def _forward_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name in FORWARD_REQUEST_HEADERS:
        value = request.headers.get(name)
        if value is not None:
            headers[name.title()] = value
    return headers


def _response_headers(response: UpstreamResponse) -> list[tuple[bytes, bytes]]:
    headers = [(name.encode("latin-1"), value.encode("latin-1")) for name, value in response.headers.items()]
    headers.append((b"content-length", str(len(response.body)).encode("ascii")))
    return headers


class HermesProxyMiddleware:
    """Pure ASGI middleware: auth, write limit, body bound, forward and the explicit error envelope."""

    def __init__(self, app: Any, *, settings: Any, write_limit: Callable[[Request, Principal], None]) -> None:
        self.app, self.settings, self.write_limit = app, settings, write_limit

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method, path = scope["method"], scope["path"]
        found: Matched | None = match(method, path, scope.get("raw_path"))
        if found is None:
            if is_near_miss(method, path):
                await self._error(scope, receive, send, not_found("route"))
                return
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        try:
            principal = require_principal(request)
            self.write_limit(request, principal)
        except AppError as error:
            await self._error(scope, receive, send, error)
            return
        except Exception:  # noqa: BLE001 - the forward must never expose an unexpected exception
            log.error("hermes forward admission failed on %s %s", method, path)
            await self._error(scope, receive, send, internal_error())
            return
        if self.settings.hermes_app_url is None:
            if self.settings.env == "production":
                await self._error(scope, receive, send, interpreter_unavailable(
                    "The live interpretation route is not configured. The saved request is unchanged."))
                return
            await self.app(scope, receive, send)
            return
        try:
            body = await _read_body(request, receive)
        except _ClientGone:
            return
        except AppError as error:
            await self._error(scope, receive, send, error)
            return
        try:
            response = await anyio.to_thread.run_sync(
                lambda: forward(found.method, found.path, body, _forward_headers(request),
                                self.settings.hermes_app_url))
        except _ConnectFailed:
            await self._error(scope, receive, send, interpreter_unavailable())
            return
        except _ReadTimedOut:
            await self._error(scope, receive, send, interpreter_timeout())
            return
        except _TransportFailed:
            await self._error(scope, receive, send, interpreter_route_failed())
            return
        if 300 <= response.status < 400:
            await self._error(scope, receive, send, interpreter_route_failed("A redirect is not accepted."))
            return
        content_type = next((value for name, value in response.headers.items()
                             if name.lower() == "content-type"), "")
        if not content_type.lower().startswith("application/json"):
            await self._error(scope, receive, send, interpreter_route_failed("The reply is not JSON."))
            return
        await send({"type": "http.response.start", "status": response.status, "headers": _response_headers(response)})
        await send({"type": "http.response.body", "body": response.body})

    @staticmethod
    async def _error(scope: dict[str, Any], receive: Any, send: Any, error: AppError) -> None:
        response = JSONResponse(error.body(), status_code=error.status, headers=error.headers)
        await response(scope, receive, send)
