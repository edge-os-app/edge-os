"""Configuration, finite bounds and sanitized errors for the HTTP source clients.

These clients are the *actual* injected clients the accepted P07 seams expect:
``EnvioHypersyncSource`` needs an ``EnvioQueryClient`` and ``corroborate_records``
needs a ``QuickNodeRpcClient``. This module holds what both clients share: the
finite per-call bounds, the endpoint policy, endpoint redaction and the error
types. It performs no I/O, reads no credential and reaches no network at import or
construction.

The bounds are caller-supplied local limits. They are not provider allowances and
they grant no quota. A caller that wants a durable request budget keeps it in its
own owner/run quota counter; these clients only count and expose their own local
attempts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

from edge_os_api.research_history.provider_transport import SourceFailure

# Plaintext HTTP is refused except for an owned loopback host, so the shipped
# transport can be exercised by an owned-loopback test server without weakening
# the production rule.
_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


class ClientConfigError(ValueError):
    """A caller supplied an unsafe, missing or incomplete client configuration.

    This is a programmer or caller defect, not a provider failure. It is raised
    before any request is sent, so the accepted collectors do not mistake it for a
    ``SourceFailure`` and it propagates.
    """


class HttpProviderError(SourceFailure):
    """An HTTP provider reply the client refuses.

    A subclass of the accepted ``SourceFailure`` so the collector and the
    corroboration record their expected partial outcome. ``code`` lets a caller or
    test branch without reading message text. The message and ``detail`` never
    carry an endpoint credential.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ClientBounds:
    """Finite per-call limits owned by the caller.

    ``deadline_seconds`` bounds the whole call; ``connect_timeout_seconds`` bounds
    each socket wait; ``max_response_bytes`` bounds the retained reply body;
    ``max_request_bytes`` bounds the request body; ``max_blocks_per_page`` bounds
    the block span of one HyperSync page.
    """

    deadline_seconds: float
    connect_timeout_seconds: float
    max_response_bytes: int
    max_request_bytes: int
    max_blocks_per_page: int

    def validate(self) -> None:
        for name in ("deadline_seconds", "connect_timeout_seconds"):
            value = getattr(self, name)
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or value <= 0):
                raise ClientConfigError(f"{name} must be a finite positive number")
        for name in ("max_response_bytes", "max_request_bytes", "max_blocks_per_page"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ClientConfigError(f"{name} must be a positive integer")


def _split_endpoint(endpoint: str) -> SplitResult:
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ClientConfigError("endpoint must be a non-empty URL string")
    if any(character in endpoint for character in (" ", "\t", "\n", "\r", "\x00")):
        raise ClientConfigError("endpoint must not contain whitespace or control characters")
    try:
        parts = urlsplit(endpoint)
    except ValueError as error:
        raise ClientConfigError("endpoint is not a valid URL") from error
    if parts.scheme not in ("https", "http"):
        raise ClientConfigError("endpoint scheme must be https (http is allowed only for a loopback host)")
    if not parts.hostname:
        raise ClientConfigError("endpoint must name a host")
    if parts.username is not None or parts.password is not None:
        raise ClientConfigError("endpoint must not carry userinfo")
    if parts.fragment:
        raise ClientConfigError("endpoint must not carry a fragment")
    if parts.scheme == "http" and parts.hostname not in _LOOPBACK_HOSTS:
        raise ClientConfigError("plaintext http is allowed only for a loopback host")
    try:
        parts.port
    except ValueError as error:
        raise ClientConfigError("endpoint port is not a valid port number") from error
    return parts


def validate_endpoint(endpoint: str) -> str:
    """Return the endpoint when it is safe, else raise ``ClientConfigError``."""
    _split_endpoint(endpoint)
    return endpoint


def endpoint_has_path(endpoint: str) -> bool:
    """Whether the endpoint carries a non-root path (a QuickNode key lives there)."""
    path = _split_endpoint(endpoint).path
    return path not in ("", "/")


def endpoint_path(endpoint: str) -> str:
    return _split_endpoint(endpoint).path


def safe_endpoint(endpoint: str) -> str:
    """A redacted ``scheme://host[:port]`` form for a message.

    The path and query are dropped, so an endpoint that carries a key in its path
    (a QuickNode endpoint) never leaks it into an error, a log or a test failure.
    """
    try:
        parts = urlsplit(endpoint if isinstance(endpoint, str) else "")
        host = parts.hostname or "<host>"
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "<endpoint>"
    scheme = parts.scheme if parts.scheme in ("http", "https") else "https"
    return f"{scheme}://{host}{port}"
