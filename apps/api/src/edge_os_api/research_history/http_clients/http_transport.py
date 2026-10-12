"""Bounded synchronous HTTP transport seam for the source clients.

``StdlibHttpTransport`` is the one shipped live transport. It opens a real socket
through ``http.client`` and is used only when a caller injects it into a client
with an explicit endpoint. It performs no I/O at import or construction, reads no
credential and holds no default endpoint.

Every request is bounded three ways: an absolute deadline applied to the socket
for the connect and response-header phase and checked between body reads (so a
stalled header or a slow dribbling body still stops within the deadline), a
per-socket cap that never exceeds the remaining deadline, and a maximum retained
body size checked while streaming (so an unbounded reply is refused before it is
fully buffered). Redirects are never followed. The connection is always closed. A
caller cancellation flag is checked before the socket opens and between body reads.
A malformed HTTP framing reply is refused as a provider error rather than escaping
as an undocumented exception. Provider-controlled text (a content-encoding value)
is never copied into an error message.
"""

from __future__ import annotations

import http.client
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

from edge_os_api.research_history.http_clients.client_config import (
    ClientConfigError,
    HttpProviderError,
    safe_endpoint,
)
from edge_os_api.research_history.provider_transport import SourceCancelled, SourceTimeout

_CHUNK_BYTES = 65_536


@dataclass(frozen=True)
class HttpResponse:
    """A bounded HTTP reply. Header names are lower-cased."""

    status: int
    headers: Mapping[str, str]
    body: bytes


@runtime_checkable
class HttpTransport(Protocol):
    """The injected transport seam. One bounded request, no retry, no redirect."""

    def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes,
                timeout: float, deadline: float, max_response_bytes: int,
                cancel: Callable[[], bool] | None = None) -> HttpResponse: ...


def _default_connect(scheme: str, host: str, port: int | None, timeout: float):
    if scheme == "https":
        return http.client.HTTPSConnection(host, port, timeout=timeout)
    if scheme == "http":
        return http.client.HTTPConnection(host, port, timeout=timeout)
    raise ClientConfigError("transport scheme must be http or https")


class StdlibHttpTransport:
    """A bounded ``http.client`` transport. No redirect, no retry, no default host."""

    def __init__(self, connect: Callable[..., object] = _default_connect,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._connect = connect
        self._clock = clock

    def _check(self, cancel: Callable[[], bool] | None, deadline: float) -> None:
        if cancel is not None and cancel():
            raise SourceCancelled("the caller cancelled the request")
        if self._clock() >= deadline:
            raise SourceTimeout("the HTTP request exceeded its time bound")

    def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes,
                timeout: float, deadline: float, max_response_bytes: int,
                cancel: Callable[[], bool] | None = None) -> HttpResponse:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ClientConfigError("transport url must be an http or https URL with a host")
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        connection = None
        try:
            self._check(cancel, deadline)
            # The socket wait never exceeds the remaining whole-call deadline, so a
            # stalled connect or response-header phase cannot hold the call past it.
            socket_timeout = min(timeout, deadline - self._clock())
            connection = self._connect(parts.scheme, parts.hostname, parts.port, socket_timeout)
            connection.request(method, path, body=body, headers=dict(headers))
            response = connection.getresponse()
            chunks: list[bytes] = []
            total = 0
            while True:
                self._check(cancel, deadline)
                chunk = response.read(_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_response_bytes:
                    raise HttpProviderError(
                        "OVERSIZED_RESPONSE", f"reply exceeds max_response_bytes ({max_response_bytes})")
                chunks.append(chunk)
            header_map = {name.lower(): value for name, value in response.getheaders()}
            return HttpResponse(status=response.status, headers=header_map, body=b"".join(chunks))
        except TimeoutError as error:
            raise SourceTimeout("the HTTP request exceeded its socket time bound") from error
        except http.client.HTTPException as error:
            # Malformed HTTP framing (a bad status line, oversized headers, a short
            # body against Content-Length) is a refused provider reply, not an
            # undocumented escape that would crash the accepted consumers.
            raise HttpProviderError(
                "MALFORMED_PROVIDER_RESPONSE",
                f"the HTTP reply from {safe_endpoint(url)} is malformed: {type(error).__name__}") from error
        finally:
            if connection is not None:
                connection.close()


def refuse_provider_status(status: int, where: str) -> None:
    """Raise ``HttpProviderError`` for a non-2xx status. Shared by both clients."""
    if 200 <= status < 300:
        return
    if 300 <= status < 400:
        raise HttpProviderError("REDIRECT_REFUSED", f"{where} returned redirect status {status}")
    if status in (401, 403):
        raise HttpProviderError("AUTH_DENIED", f"{where} was denied (status {status})")
    if status == 402:
        raise HttpProviderError("PAYMENT_REQUIRED", f"{where} requires payment (status 402)")
    if status == 429:
        raise HttpProviderError("RATE_LIMITED", f"{where} was rate limited (status 429)")
    raise HttpProviderError("HTTP_STATUS", f"{where} returned status {status}")


def decode_json_reply(response: HttpResponse) -> Mapping[str, Any]:
    """Decode a bounded JSON-object reply. Shared by both clients."""
    encoding = response.headers.get("content-encoding")
    if encoding is not None and encoding.lower() != "identity":
        # The header value is provider-controlled and may echo a key; never copy it.
        raise HttpProviderError("UNSUPPORTED_CONTENT_ENCODING",
                                "reply used a non-identity content-encoding")
    try:
        text = response.body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply is not valid UTF-8") from error
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply is not valid JSON") from error
    if not isinstance(parsed, Mapping):
        raise HttpProviderError("MALFORMED_PROVIDER_RESPONSE", "reply is not a JSON object")
    return parsed
