"""Offline helpers for the Nansen HTTP transport tests.

Every key, token and number here is synthetic. ``AuthoredHttp`` is an injected
``HttpTransport`` that records each call and replays authored replies; the loopback
tests use the real ``StdlibHttpTransport`` with the shared owned ``LoopbackServer``.
"""

from __future__ import annotations

import http.client
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# The Nansen fixtures and the owned loopback server live in sibling test folders.
_TESTS = Path(__file__).resolve().parent.parent
for _folder in (_TESTS / "nansen_research", _TESTS / "research_history" / "http_clients"):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import _http_support as http_support  # noqa: E402
import nansen_fixtures as nansen  # noqa: E402
from edge_os_api.nansen_research.http_transport import NansenHttpTransport  # noqa: E402
from edge_os_api.research_history.http_clients.http_transport import HttpResponse  # noqa: E402

SYNTHETIC_KEY = "synthetic-nansen-key-7f3a9c"


class AuthoredHttp:
    """An injected HttpTransport: records every call, serves scripted items in order."""

    def __init__(self, *items: Any) -> None:
        self._items = list(items)
        self.calls: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> HttpResponse:
        self.calls.append(kwargs)
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def reply(status: int = 200, body: bytes = b"{}", headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status=status, headers=dict(headers or {}), body=body)


def adapter(http: Any, **overrides: Any) -> NansenHttpTransport:
    fields: dict[str, Any] = {
        "api_key": SYNTHETIC_KEY,
        "http": http,
        "connect_timeout_seconds": 2.0,
        "deadline_monotonic": time.monotonic() + 30.0,
        "max_request_bytes": 4_096,
        "max_response_bytes": 65_536,
    }
    fields.update(overrides)
    return NansenHttpTransport(**fields)


class LoopbackConnector:
    """Sends the fixed production origin to the owned loopback port, recording each
    requested target and every socket it opened so a test can prove cleanup."""

    def __init__(self, server: Any, on_connect: Callable[[], None] | None = None) -> None:
        self._address = server._server.server_address[:2]
        self._on_connect = on_connect
        self.targets: list[tuple[str, str, int | None]] = []
        self.sockets: list[Any] = []

    def __call__(self, scheme: str, host: str, port: int | None, timeout: float) -> http.client.HTTPConnection:
        self.targets.append((scheme, host, port))
        opened = self.sockets
        on_connect = self._on_connect

        class _Recording(http.client.HTTPConnection):
            def connect(self) -> None:
                super().connect()
                opened.append(self.sock)
                if on_connect is not None:
                    on_connect()

        return _Recording(*self._address, timeout=timeout)
