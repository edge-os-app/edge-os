"""Immutable history of interpretation attempts.

Every provider attempt is recorded before the call (`AttemptStart`) and once afterwards (`AttemptSettlement`).
Nothing is updated or deleted. A retry or repair is a new attempt that names the attempt it follows. An attempt
that never settles is closed as INTERRUPTED with unknown usage and is never replayed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

from edge_os_api.records import contract_adapter as record_contract

__all__ = ["AlreadyLinked", "AlreadySettled", "AttemptError", "AttemptIdentity", "AttemptInFlight", "AttemptLedger",
           "AttemptSettlement", "AttemptStart", "AttemptStore", "AttemptView", "ExecutionGuard", "InvalidIdentity",
           "InvalidSettlement", "LateResult", "NotPublishable", "NotUncertain", "RetryTargetInvalid", "UnknownAttempt",
           "Usage"]


class AttemptError(Exception):
    """Base class for attempt ledger rule violations."""


class AttemptInFlight(AttemptError):
    """Another attempt for this request has not settled."""


class RetryTargetInvalid(AttemptError):
    """A retry must name an earlier attempt of the same owner and request."""


class UnknownAttempt(AttemptError):
    """No such attempt exists for this owner."""


class AlreadySettled(AttemptError):
    """An attempt settles once."""


class InvalidSettlement(AttemptError):
    """The settlement contradicts itself."""


class InvalidIdentity(AttemptError):
    """The attempt identity contradicts itself."""


class AlreadyLinked(AttemptError):
    """An attempt links to one interpretation revision."""


class NotPublishable(AttemptError):
    """Only a completed attempt whose response was accepted can link to a revision."""


class NotUncertain(AttemptError):
    """A late result belongs only beside an attempt whose outcome stayed unknown."""


COMPLETION_BY_STATUS = {"COMPLETED": "COMPLETE", "TRUNCATED": "TRUNCATED", "PROVIDER_FAILED": "NONE",
                        "TIMED_OUT": "UNKNOWN", "INTERRUPTED": "UNKNOWN", "UNKNOWN": "UNKNOWN"}
STATUSES_WITH_RESPONSE = frozenset({"COMPLETED", "TRUNCATED"})
UNCERTAIN_STATUSES = frozenset({"TIMED_OUT", "INTERRUPTED", "UNKNOWN"})
USAGE_SOURCES = ("UNKNOWN", "PROVIDER_REPORTED")


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    source: str = "UNKNOWN"


@dataclass(frozen=True)
class AttemptIdentity:
    purpose: str
    prompt_version: str
    system_prompt_sha256: str
    task_sha256: str
    task_text: str
    response_shape_sha256: str
    manifest_sha256: str
    config: Mapping[str, Any]
    runtime_label: str
    answer_ref: str | None = None
    answer_text: str | None = None
    previous_revision_id: str | None = None


@dataclass(frozen=True)
class AttemptStart:
    attempt_id: str
    owner_id: str
    intake_record_id: str
    sequence: int
    retry_of: str | None
    identity: AttemptIdentity
    config_sha256: str
    started_at: dt.datetime


@dataclass(frozen=True)
class AttemptSettlement:
    attempt_id: str
    owner_id: str
    status: str
    finished_at: dt.datetime
    latency_ms: int | None
    usage: Usage
    request_count: int | None
    response_sha256: str | None
    response_text: str | None
    parse_result: str
    error_class: str | None
    runtime_observed: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AttemptView:
    start: AttemptStart
    settlement: AttemptSettlement | None
    revision_id: str | None

    @property
    def status(self) -> str:
        return self.settlement.status if self.settlement else "STARTED"

    @property
    def completion(self) -> str:
        return COMPLETION_BY_STATUS.get(self.status, "UNKNOWN")


class AttemptStore(Protocol):
    """Append-only storage. Every method is scoped to one owner; another owner's rows do not exist for the caller."""

    def add_start(self, start: AttemptStart) -> None: ...
    def add_settlement(self, settlement: AttemptSettlement) -> None: ...
    def add_link(self, owner_id: str, attempt_id: str, revision_id: str,
                 offered_questions: Sequence[Mapping[str, Any]]) -> None: ...
    def add_observation(self, observation: LateResult) -> None: ...
    def find_start(self, owner_id: str, attempt_id: str) -> AttemptStart | None: ...
    def starts(self, owner_id: str, intake_record_id: str) -> Sequence[AttemptStart]: ...
    def settlements(self, owner_id: str, intake_record_id: str) -> Sequence[AttemptSettlement]: ...
    def links(self, owner_id: str, intake_record_id: str) -> Mapping[str, str]: ...
    def observations(self, owner_id: str, intake_record_id: str) -> Sequence[LateResult]: ...
    def offered_questions(self, owner_id: str, intake_record_id: str, revision_id: str) -> Sequence[Mapping[str, Any]]: ...


def _check_settlement(settlement: AttemptSettlement) -> None:
    status, text = settlement.status, settlement.response_text
    if status not in COMPLETION_BY_STATUS:
        raise InvalidSettlement("The status is not one the ledger defines.")
    if (status == "COMPLETED" and text is None) or (status not in STATUSES_WITH_RESPONSE and text is not None):
        raise InvalidSettlement("The response text does not fit the status.")
    expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None
    if settlement.response_sha256 != expected_hash:
        raise InvalidSettlement("The response hash does not match the response text.")
    if settlement.latency_ms is not None and settlement.latency_ms < 0:
        raise InvalidSettlement("Latency cannot be negative.")
    usage = settlement.usage
    counts = (usage.input_tokens, usage.output_tokens, usage.total_tokens)
    if usage.source not in USAGE_SOURCES or any(count is not None and count < 0 for count in counts):
        raise InvalidSettlement("The usage is not valid.")
    if (usage.source == "PROVIDER_REPORTED") != (usage.input_tokens is not None and usage.output_tokens is not None):
        raise InvalidSettlement("Usage is either reported with input and output counts or unknown.")
    parse_result = settlement.parse_result
    if text is None:
        valid_parse = parse_result == "NOT_PARSED"
    elif status == "TRUNCATED":
        valid_parse = parse_result.startswith("REJECTED:")
    else:
        valid_parse = parse_result == "ACCEPTED" or (parse_result.startswith("REJECTED:") and len(parse_result) > 9)
    if not valid_parse:
        raise InvalidSettlement("The parse result does not fit the response.")


class AttemptLedger:
    """Rules for attempt history. Concurrent callers are separated by the store's unique (owner, request, sequence)."""

    def __init__(self, store: AttemptStore, new_id: Callable[[], str], now: Callable[[], dt.datetime]) -> None:
        self._store, self._new_id, self._now = store, new_id, now

    def now(self) -> dt.datetime:
        return self._now()

    def new_attempt_id(self) -> str:
        return self._new_id()

    def begin(self, owner_id: str, intake_record_id: str, identity: AttemptIdentity,
              retry_of: str | None = None, attempt_id: str | None = None) -> AttemptStart:
        if identity.task_sha256 != hashlib.sha256(identity.task_text.encode("utf-8")).hexdigest():
            raise InvalidIdentity("The request hash does not match the saved request text.")
        if (identity.answer_ref is None) != (identity.answer_text is None):
            raise InvalidIdentity("A reply and its reference are saved together.")
        starts = self._store.starts(owner_id, intake_record_id)
        settled = {settlement.attempt_id for settlement in self._store.settlements(owner_id, intake_record_id)}
        if any(start.attempt_id not in settled for start in starts):
            raise AttemptInFlight("Another attempt for this request has not settled.")
        if retry_of is not None and retry_of not in {start.attempt_id for start in starts}:
            raise RetryTargetInvalid("A retry must name an earlier attempt of this request.")
        start = AttemptStart(attempt_id=attempt_id or self._new_id(), owner_id=owner_id, intake_record_id=intake_record_id,
                             sequence=len(starts) + 1, retry_of=retry_of, identity=identity,
                             config_sha256=record_contract.sha256_hex(dict(identity.config)), started_at=self._now())
        self._store.add_start(start)
        return start

    def settle(self, settlement: AttemptSettlement) -> None:
        start = self._store.find_start(settlement.owner_id, settlement.attempt_id)
        if start is None:
            raise UnknownAttempt("No such attempt.")
        if any(known.attempt_id == settlement.attempt_id
               for known in self._store.settlements(start.owner_id, start.intake_record_id)):
            raise AlreadySettled("This attempt already settled.")
        _check_settlement(settlement)
        self._store.add_settlement(settlement)

    def history(self, owner_id: str, intake_record_id: str) -> list[AttemptView]:
        settlements = {s.attempt_id: s for s in self._store.settlements(owner_id, intake_record_id)}
        links = self._store.links(owner_id, intake_record_id)
        return [AttemptView(start, settlements.get(start.attempt_id), links.get(start.attempt_id))
                for start in sorted(self._store.starts(owner_id, intake_record_id), key=lambda s: s.sequence)]

    def interrupt_abandoned(self, owner_id: str, intake_record_id: str,
                            is_abandoned: Callable[[AttemptStart], bool]) -> list[AttemptView]:
        """Close each unsettled attempt that is proved abandoned. Its usage and completion stay unknown.

        An attempt whose abandonment is not proved is left open, so a duplicate attempt is refused. Nothing is replayed.
        """
        closed: list[str] = []
        for view in self.history(owner_id, intake_record_id):
            if view.settlement is None and is_abandoned(view.start):
                try:
                    self._store.add_settlement(AttemptSettlement(
                        attempt_id=view.start.attempt_id, owner_id=owner_id, status="INTERRUPTED",
                        finished_at=self._now(), latency_ms=None, usage=Usage(), request_count=None,
                        response_sha256=None, response_text=None, parse_result="NOT_PARSED", error_class=None))
                except AlreadySettled:
                    continue  # the attempt settled while we looked: its real result stands
                closed.append(view.start.attempt_id)
        return [view for view in self.history(owner_id, intake_record_id) if view.start.attempt_id in closed]

    def observe_late_result(self, result: LateResult) -> None:
        """Keep a result that arrived after its attempt settled as unknown. The settlement is never replaced."""
        start = self._store.find_start(result.owner_id, result.attempt_id)
        if start is None:
            raise UnknownAttempt("No such attempt.")
        settlement = next((s for s in self._store.settlements(start.owner_id, start.intake_record_id)
                           if s.attempt_id == start.attempt_id), None)
        if settlement is None or settlement.status not in UNCERTAIN_STATUSES:
            raise NotUncertain("A late result belongs only beside an attempt that settled as unknown.")
        text = result.response_text
        if result.response_sha256 != (hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None):
            raise InvalidSettlement("The response hash does not match the response text.")
        self._store.add_observation(result)

    def late_results(self, owner_id: str, intake_record_id: str) -> list[LateResult]:
        return list(self._store.observations(owner_id, intake_record_id))

    def offered_questions(self, owner_id: str, intake_record_id: str, revision_id: str) -> list[dict[str, Any]]:
        return [dict(question) for question in self._store.offered_questions(owner_id, intake_record_id, revision_id)]

    def link_revision(self, owner_id: str, attempt_id: str, revision_id: str,
                      offered_questions: Sequence[Mapping[str, Any]] = ()) -> None:
        start = self._store.find_start(owner_id, attempt_id)
        if start is None:
            raise UnknownAttempt("No such attempt.")
        view = next(v for v in self.history(owner_id, start.intake_record_id) if v.start.attempt_id == attempt_id)
        if view.status != "COMPLETED" or view.settlement is None or view.settlement.parse_result != "ACCEPTED":
            raise NotPublishable("Only a completed attempt with an accepted response can link to a revision.")
        if view.revision_id is not None:
            raise AlreadyLinked("This attempt already links to a revision.")
        self._store.add_link(owner_id, attempt_id, revision_id, list(offered_questions))

    def unpublished_results(self, owner_id: str, intake_record_id: str) -> list[AttemptView]:
        """Accepted results that no revision uses yet. Recovery publishes them from the saved text, with no new call."""
        return [view for view in self.history(owner_id, intake_record_id)
                if view.status == "COMPLETED" and view.revision_id is None
                and view.settlement is not None and view.settlement.parse_result == "ACCEPTED"]


@dataclass(frozen=True)
class LateResult:
    """A result that arrived after its attempt settled with an unknown outcome. It is evidence, never authority."""

    observation_id: str
    attempt_id: str
    owner_id: str
    observed_at: dt.datetime
    status: str
    response_sha256: str | None
    response_text: str | None
    usage: Usage
    request_count: int | None
    error_class: str | None


class ExecutionGuard(Protocol):
    """Proof of who is running an attempt. An attempt is abandoned only when nobody holds its claim."""

    def claim(self, attempt_id: str) -> AbstractContextManager[None]: ...
    def is_abandoned(self, attempt_id: str) -> bool: ...
