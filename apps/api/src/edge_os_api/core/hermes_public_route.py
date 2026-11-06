"""The one public route table for the host Hermes application.

The Coolify `api` forwards exactly these paths. The host application admits exactly these paths and the two operator
health paths. Everything else is `404`. Path matching is exact and case-sensitive; a percent-encoded byte, a dot
segment, a double slash or a trailing slash never matches, so a rewritten path cannot reach the host application.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse

from edge_os_api.core.errors import not_found

_INTAKE = "{intake_id}"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+")


@dataclass(frozen=True)
class Route:
    method: str
    template: str
    parts: tuple[str, ...]


ROUTES: tuple[Route, ...] = (
    Route("GET", "/v1/interpreter", ("v1", "interpreter")),
    Route("POST", "/v1/research/requests", ("v1", "research", "requests")),
    Route("GET", "/v1/research/requests", ("v1", "research", "requests")),
    Route("GET", "/v1/research/requests/{intake_id}", ("v1", "research", "requests", _INTAKE)),
    Route("POST", "/v1/research/requests/{intake_id}/clarifications",
          ("v1", "research", "requests", _INTAKE, "clarifications")),
    Route("POST", "/v1/research/requests/{intake_id}/interpretation-retries",
          ("v1", "research", "requests", _INTAKE, "interpretation-retries")),
)

HEALTH_ROUTES: tuple[tuple[str, str], ...] = (("GET", "/healthz"), ("GET", "/readyz"))


@dataclass(frozen=True)
class Matched:
    method: str
    path: str
    intake_id: str | None


def _strict_parts(path: str) -> list[str] | None:
    if not path.startswith("/"):
        return None
    parts = path[1:].split("/")
    if not parts or any(not part for part in parts):
        return None
    return parts


def _loose_parts(path: str) -> list[str] | None:
    if not path.startswith("/"):
        return None
    return [part for part in path[1:].split("/") if part]


def _normalize(parts: list[str]) -> list[str]:
    kept: list[str] = []
    for part in parts:
        if part in {".", ""}:
            continue
        if part == "..":
            if kept:
                kept.pop()
            continue
        kept.append(part)
    return kept


def _shape(method: str, parts: list[str]) -> Route | None:
    for route in ROUTES:
        if route.method != method or len(route.parts) != len(parts):
            continue
        if all(literal == part or literal == _INTAKE for literal, part in zip(route.parts, parts)):
            return route
    return None


def match(method: str, path: str, raw_path: bytes | None = None) -> Matched | None:
    """The exact public route, or None. `raw_path` must equal the ASCII path: no percent-encoding is accepted."""
    try:
        raw = path.encode("ascii") if raw_path is None else raw_path
        decoded_raw = raw.decode("ascii")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return None
    if decoded_raw != path:
        return None
    parts = _strict_parts(path)
    if parts is None or any(_SEGMENT.fullmatch(part) is None for part in parts):
        return None
    route = _shape(method, parts)
    if route is None:
        return None
    intake: str | None = None
    for literal, part in zip(route.parts, parts):
        if literal == _INTAKE:
            if _UUID.fullmatch(part) is None:
                return None
            try:
                if str(uuid.UUID(part)) != part:
                    return None
            except ValueError:
                return None
            intake = part
        elif literal != part:
            return None
    return Matched(route.method, path, intake)


def is_public_shape(path: str) -> bool:
    """True when the path has the literal shape of a public route, whatever the method."""
    parts = _strict_parts(path)
    return parts is not None and any(
        len(route.parts) == len(parts)
        and all(literal == part or (literal == _INTAKE and _SEGMENT.fullmatch(part) is not None)
                for literal, part in zip(route.parts, parts))
        for route in ROUTES
    )


def is_near_miss(method: str, path: str) -> bool:
    """True when the path could become a public route after normalising `//`, `.` and `..`."""
    parts = _loose_parts(path)
    if parts is None:
        return False
    return _shape(method, _normalize(parts)) is not None


class PublicRouteGuard:
    """ASGI guard for the host application. It admits the six public routes and two operator health reads."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope["method"]
        path = scope["path"]
        raw_path = scope.get("raw_path")
        found = match(method, path, raw_path)
        if found is not None:
            await self.app(scope, receive, send)
            return
        if method == "OPTIONS" and is_public_shape(path):
            await self.app(scope, receive, send)
            return
        if (method, path) in HEALTH_ROUTES:
            await self.app(scope, receive, send)
            return
        response = JSONResponse(not_found("route").body(), status_code=404)
        await response(scope, receive, send)
