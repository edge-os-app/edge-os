"""The provider transport contract shared by the host and the container job. Standard library only; no I/O anywhere.

Pinned Hermes talks to a fixed placeholder client: `HERMES_CLIENT_URL` with `HERMES_CLIENT_KEY`. It never holds the
host's endpoint or credential. For each interpretation attempt the job:

1. admits the physical request (`physical_refusal`): POST to the placeholder URL, the SDK's own header names only, JSON
   in and out, no streaming, SDK retry count 0, and the body names this attempt (`session_id` is `p05-<attempt id>`);
2. passes it to the accepted provider guard (body, model, limits, prompt, task, one physical request per attempt);
3. builds the host request (`host_request`): the route's endpoint, three fixed headers, the host credential when there
   is one, and the admitted body byte for byte;
4. gives only a bounded reply back to Hermes (`reply_refusal`).

A refusal at step 1 or 2 means no transport saw the request. The transport itself is injected (`ProviderTransport`). In
this candidate only an AUTHORED transport exists; an ACTUAL route is refused before anything is built
(`ActualProviderUnavailable`). Enabling a network transport or a real credential needs a separate approval packet.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

__all__ = ["ActualProviderUnavailable", "HERMES_CLIENT_KEY", "HERMES_CLIENT_URL", "HostRequest", "PhysicalRequest",
           "ProviderTransport", "TransportLost", "TransportReply", "TransportRoute", "host_request", "physical_refusal",
           "reply_refusal"]

# The client the job gives Hermes (hermes_turn_job.run_hermes): a name that never resolves and a key that is no secret.
HERMES_CLIENT_URL = "https://fake-provider.invalid/v1/chat/completions"
HERMES_CLIENT_KEY = "fixture-only-not-a-secret"
# The header names the pinned OpenAI SDK sends for one non-streaming chat completion (seen in every accepted P05 run).
SDK_HEADERS = frozenset({
    "accept", "accept-encoding", "authorization", "connection", "content-length", "content-type", "host", "user-agent",
    "x-stainless-arch", "x-stainless-async", "x-stainless-lang", "x-stainless-os", "x-stainless-package-version",
    "x-stainless-read-timeout", "x-stainless-retry-count", "x-stainless-runtime", "x-stainless-runtime-version"})
ROUTE_KINDS = ("AUTHORED", "ACTUAL")
MAX_REPLY_LIMIT = 1024 * 1024  # a chat completion of 4,096 output tokens is far smaller
ROUTE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")


class ActualProviderUnavailable(RuntimeError):
    """No actual provider transport exists in this candidate. A separate approval packet is needed to add one."""


class TransportLost(RuntimeError):
    """The request was handed to the transport and no reply came back. Whether the provider worked is unknown."""


@dataclass(frozen=True)
class TransportRoute:
    """The host-owned route: where an admitted request goes and how large a reply may be."""

    route_id: str
    kind: str
    endpoint_url: str
    max_reply_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.route_id, str) or not ROUTE_ID.fullmatch(self.route_id):
            raise ValueError("route_id must be 1-64 letters, digits or ._:-")
        if self.kind not in ROUTE_KINDS:
            raise ValueError(f"kind must be one of {ROUTE_KINDS}")
        parts = urlsplit(self.endpoint_url) if isinstance(self.endpoint_url, str) else None
        if (parts is None or parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment):
            raise ValueError("endpoint_url must be an https URL with no user, query or fragment")
        limit = self.max_reply_bytes
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 < limit <= MAX_REPLY_LIMIT:
            raise ValueError(f"max_reply_bytes must be a whole number from 1 to {MAX_REPLY_LIMIT}")

    def settings(self) -> dict[str, Any]:
        return {"route_id": self.route_id, "kind": self.kind, "endpoint_url": self.endpoint_url,
                "max_reply_bytes": self.max_reply_bytes}

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> TransportRoute:
        return cls(settings["route_id"], settings["kind"], settings["endpoint_url"], settings["max_reply_bytes"])


@dataclass(frozen=True)
class PhysicalRequest:
    """The request exactly as Hermes' HTTP client built it. Header names are lower case."""

    method: str
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


@dataclass(frozen=True)
class HostRequest:
    """What the host transport sends: the route's endpoint, host-made headers and the admitted body."""

    attempt_id: str
    route_id: str
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


@dataclass(frozen=True)
class TransportReply:
    status: int
    body: bytes


class ProviderTransport(Protocol):
    def send(self, request: HostRequest) -> TransportReply:
        """Send once. Never retry, stream or follow a redirect. Read at most the route's max_reply_bytes + 1 bytes.

        Raise `TransportLost` when the request may have been sent and no complete reply came back.
        """
        ...


def physical_refusal(request: PhysicalRequest, attempt_id: str, client_url: str) -> str | None:
    """Why this is not the one intended physical request of this attempt, or None when it is."""
    if request.method != "POST":
        return "method_not_post"
    if request.url != client_url:
        return "url_not_as_configured"
    names = [name.lower() for name, _ in request.headers]
    if len(set(names)) != len(names):
        return "header_repeated"  # two readers could see two different values
    if set(names) - SDK_HEADERS:
        return "header_not_permitted"
    headers = {name.lower(): value for name, value in request.headers}
    if headers.get("accept") != "application/json":
        return "streaming_not_permitted"
    if headers.get("x-stainless-retry-count") != "0":
        return "sdk_retry_not_permitted"
    if headers.get("content-type") != "application/json":
        return "body_not_json"
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "body_not_a_json_object"
    if not isinstance(body, dict):
        return "body_not_a_json_object"
    if body.get("session_id") != f"p05-{attempt_id}":
        return "attempt_not_as_configured"
    return None  # the accepted provider guard checks the rest of the body next


def host_request(request: PhysicalRequest, route: TransportRoute, attempt_id: str, credential: str | None) -> HostRequest:
    """The request the host sends. None of Hermes' headers pass; the host's endpoint and credential replace its own."""
    headers = [("accept", "application/json"), ("content-type", "application/json")]
    if credential is not None:
        headers.append(("authorization", f"Bearer {credential}"))
    return HostRequest(attempt_id, route.route_id, route.endpoint_url, tuple(headers), request.body)


def reply_refusal(reply: TransportReply, route: TransportRoute) -> str | None:
    """Why this reply may not reach Hermes, or None. A reply larger than the route allows is never parsed."""
    if isinstance(reply.status, bool) or not isinstance(reply.status, int) or not 100 <= reply.status <= 599:
        return "reply_status_invalid"
    if not isinstance(reply.body, bytes) or len(reply.body) > route.max_reply_bytes:
        return "reply_too_large"
    try:
        parsed = json.loads(reply.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return "reply_not_a_json_object"
    return None if isinstance(parsed, dict) else "reply_not_a_json_object"
