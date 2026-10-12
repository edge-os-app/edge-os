"""Transport seam for recorded provider history responses.

The adapter takes a caller-supplied ``ResponseSource``. It ships exactly one
source, ``RecordedResponseSource``, which serves an in-memory list of recorded
provider responses. This module defines no live transport, opens no socket and
reads no environment variable or credential file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


class SourceCancelled(Exception):
    """The caller cancelled the collection. Part of the result is retained."""


class SourceTimeout(Exception):
    """The supplied source hit its own time bound. Part of the result is retained."""


class SourceFailure(Exception):
    """An expected provider or transport failure.

    A source raises this for a known provider failure. The collector records a
    partial result with the attempted invocation and no retry. A programmer defect
    must raise its own error type instead, so it is not mistaken for a provider
    failure.
    """


@dataclass(frozen=True)
class HistoryRequest:
    """One bounded page request sent to the response source."""

    provider: str
    address: str
    topic0: str
    from_block: int
    to_block_exclusive: int
    cursor_after: int | None
    max_rows: int

    def as_view(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "address": self.address,
            "topic0": self.topic0,
            "from_block": self.from_block,
            "to_block_exclusive": self.to_block_exclusive,
            "cursor_after": self.cursor_after,
            "max_rows": self.max_rows,
        }


@runtime_checkable
class ResponseSource(Protocol):
    """A recorded response source. It returns the next provider response or None."""

    def next_response(self, request: HistoryRequest) -> Mapping[str, Any] | None: ...


class RecordedResponseSource:
    """Serves caller-supplied recorded responses in order.

    The source is deterministic and offline. It never invents a response and it
    never reaches a network, a provider or an environment value.
    """

    def __init__(self, responses: Sequence[Mapping[str, Any]]) -> None:
        self._responses = list(responses)
        self._index = 0

    @property
    def remaining(self) -> int:
        return len(self._responses) - self._index

    def next_response(self, request: HistoryRequest) -> Mapping[str, Any] | None:
        if self._index >= len(self._responses):
            return None
        response = self._responses[self._index]
        self._index += 1
        return response
