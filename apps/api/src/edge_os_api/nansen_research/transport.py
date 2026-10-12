"""Transport seam for the read-only Nansen research client.

The client takes a caller-supplied ``NansenTransport``. The transport owns the
endpoint and any credential; this package never reads a credential, opens a
socket or reaches a network. The package ships exactly one transport,
``RecordedNansenTransport``, which serves authored responses to a test.

A transport returns one ``NansenResponse`` per call and must not retry. It raises
``NansenTransportError`` (or a subclass) for an expected failure, and its own
error type for a programmer defect.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from edge_os_api.nansen_research.errors import NansenTransportError


@dataclass(frozen=True)
class NansenResponse:
    """One provider response. ``headers`` holds the raw provider header mapping."""

    status: int
    headers: Mapping[str, str]
    body: bytes

    def __post_init__(self) -> None:
        if isinstance(self.status, bool) or not isinstance(self.status, int) or not 100 <= self.status <= 599:
            raise ValueError("status must be an integer in 100..599")
        if not isinstance(self.headers, Mapping):
            raise ValueError("headers must be a mapping")
        if not isinstance(self.body, bytes):
            raise ValueError("body must be bytes")


@runtime_checkable
class NansenTransport(Protocol):
    """The injected native Nansen transport. One call per ``request``, no retry."""

    def request(self, operation: str, path: str, body: Mapping[str, Any]) -> NansenResponse: ...


class RecordedNansenTransport:
    """A deterministic offline transport for tests and authored examples.

    It serves the scripted items in order. An item may be a ``NansenResponse`` or
    an exception instance; an exception is raised to model a transport fault. An
    exhausted script raises ``NansenTransportError``, so a test cannot silently
    read a provider that no longer answers.
    """

    def __init__(self, script: Sequence[NansenResponse | BaseException]) -> None:
        self._script = list(script)
        self._index = 0

    @property
    def remaining(self) -> int:
        return len(self._script) - self._index

    def request(self, operation: str, path: str, body: Mapping[str, Any]) -> NansenResponse:
        if self._index >= len(self._script):
            raise NansenTransportError("NO_RECORDED_RESPONSE", "the recorded transport is exhausted")
        item = self._script[self._index]
        self._index += 1
        if isinstance(item, BaseException):
            raise item
        return item
