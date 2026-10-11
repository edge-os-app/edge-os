"""PostgreSQL storage for the interpretation attempt ledger and the proof of who is running an attempt.

`PostgresAttemptStore` implements the ledger's `AttemptStore` over append-only tables. Each call is one short
transaction on its own session. `bound_to(session)` returns a store that writes on the caller's session without
committing, so a link can commit in the same transaction as the revision it names.

`AdvisoryLockGuard` holds a session-level advisory lock on a dedicated idle connection while an attempt runs. The lock
is the claim: a crashed worker loses its connection and so its claim, and only then is its attempt provably abandoned.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from edge_os_api.records.models import (
    InterpretationAttempt, InterpretationAttemptLink, InterpretationLateResult, InterpretationSettlement,
)

from .interpretation_attempts import (
    AlreadyLinked, AlreadySettled, AttemptIdentity, AttemptInFlight, AttemptStart, AttemptSettlement, LateResult,
    RevisionMoved, Usage,
)

__all__ = ["AdvisoryLockGuard", "ClaimHeld", "PostgresAttemptStore"]


def _constraint(error: IntegrityError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _start_of(row: InterpretationAttempt) -> AttemptStart:
    identity = AttemptIdentity(
        purpose=row.purpose, prompt_version=row.prompt_version, system_prompt_sha256=row.system_prompt_sha256,
        task_sha256=row.task_sha256, task_text=row.task_text, response_shape_sha256=row.response_shape_sha256,
        manifest_sha256=row.manifest_sha256, config=dict(row.config), runtime_label=row.runtime_label,
        answer_ref=row.answer_ref, answer_text=row.answer_text,
        previous_revision_id=str(row.previous_revision_id) if row.previous_revision_id else None)
    return AttemptStart(
        attempt_id=str(row.attempt_id), owner_id=str(row.owner_id), intake_record_id=str(row.intake_record_id),
        sequence=row.sequence, retry_of=str(row.retry_of) if row.retry_of else None, identity=identity,
        config_sha256=row.config_sha256, started_at=row.started_at)


def _usage_of(row: InterpretationSettlement | InterpretationLateResult) -> Usage:
    if row.usage_source != "PROVIDER_REPORTED":
        return Usage()
    return Usage(row.input_tokens, row.output_tokens, row.total_tokens, "PROVIDER_REPORTED")


def _settlement_of(row: InterpretationSettlement) -> AttemptSettlement:
    return AttemptSettlement(
        attempt_id=str(row.attempt_id), owner_id=str(row.owner_id), status=row.status, finished_at=row.finished_at,
        latency_ms=row.latency_ms, usage=_usage_of(row), request_count=row.request_count,
        response_sha256=row.response_sha256, response_text=row.response_text, parse_result=row.parse_result,
        error_class=row.error_class, runtime_observed=dict(row.runtime_observed))


def _late_result_of(row: InterpretationLateResult) -> LateResult:
    return LateResult(
        observation_id=str(row.observation_id), attempt_id=str(row.attempt_id), owner_id=str(row.owner_id),
        observed_at=row.observed_at, status=row.status, response_sha256=row.response_sha256,
        response_text=row.response_text, usage=_usage_of(row), request_count=row.request_count,
        error_class=row.error_class)


class PostgresAttemptStore:
    def __init__(self, session_factory: Callable[[], Session] | None = None, *, session: Session | None = None) -> None:
        if (session_factory is None) == (session is None):
            raise ValueError("Give either a session factory or a session.")
        self._factory, self._session = session_factory, session

    def bound_to(self, session: Session) -> PostgresAttemptStore:
        """A store that uses the caller's session and leaves the commit to the caller."""
        return PostgresAttemptStore(session=session)

    @contextmanager
    def _unit(self) -> Iterator[Session]:
        if self._session is not None:
            yield self._session
            return
        assert self._factory is not None
        with self._factory() as session:
            yield session
            session.commit()

    def _insert(self, session: Session, row: Any, on_conflict: dict[str, Exception]) -> None:
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError as error:
            if (mapped := on_conflict.get(_constraint(error) or "")) is not None:
                raise mapped from None
            raise

    def add_start(self, start: AttemptStart) -> None:
        identity = start.identity
        row = InterpretationAttempt(
            attempt_id=uuid.UUID(start.attempt_id), owner_id=uuid.UUID(start.owner_id),
            intake_record_id=uuid.UUID(start.intake_record_id), sequence=start.sequence,
            retry_of=uuid.UUID(start.retry_of) if start.retry_of else None, purpose=identity.purpose,
            prompt_version=identity.prompt_version, system_prompt_sha256=identity.system_prompt_sha256,
            task_sha256=identity.task_sha256, task_text=identity.task_text,
            response_shape_sha256=identity.response_shape_sha256, manifest_sha256=identity.manifest_sha256,
            config=dict(identity.config), config_sha256=start.config_sha256, runtime_label=identity.runtime_label,
            answer_ref=identity.answer_ref, answer_text=identity.answer_text,
            answer_sha256=_sha256(identity.answer_text) if identity.answer_text is not None else None,
            previous_revision_id=uuid.UUID(identity.previous_revision_id) if identity.previous_revision_id else None,
            started_at=start.started_at)
        with self._unit() as session:  # the unique (owner, request, sequence) is what separates concurrent admissions
            self._require_current_basis(session, start)
            self._insert(session, row, {"uq_attempt_owner_intake_sequence": AttemptInFlight(
                "Another attempt for this request took this place first.")})

    @staticmethod
    def _require_current_basis(session: Session, start: AttemptStart) -> None:
        """Admit a reply only while the saved meaning it answers is still the current one.

        The request row is locked for the check and the insert, the same lock that every writer of a revision takes. A
        writer then either finished first, and this call sees the new head, or it starts later and sees this open
        attempt. A request that was checked earlier and waited cannot start a second provider call on an old basis.
        """
        if start.identity.previous_revision_id is None:
            return  # a first reading reads the request itself; the ledger admits it only as the first attempt or as a retry of the latest one
        found = session.execute(text(
            "select 1 from records where owner_id = :o and record_id = :i and record_type = 'IntakeRequest' for update"),
            {"o": uuid.UUID(start.owner_id), "i": uuid.UUID(start.intake_record_id)}).first()
        if found is None:
            return  # the ledger is used on its own in unit tests; a stored request always has its row
        head = session.execute(text(
            "select p.content ->> 'interpretation_revision_id' from records p "
            "where p.owner_id = :o and p.intake_record_id = :i and p.record_type = 'PromptInterpretation' "
            "and not exists (select 1 from records s where s.owner_id = p.owner_id and s.record_type = 'PromptInterpretation' "
            "and s.predecessor_record_id = p.record_id) order by p.created_at desc limit 1"),
            {"o": uuid.UUID(start.owner_id), "i": uuid.UUID(start.intake_record_id)}).scalar_one_or_none()
        if head != start.identity.previous_revision_id:
            raise RevisionMoved("The saved meaning changed after this attempt was requested.")

    def add_settlement(self, settlement: AttemptSettlement) -> None:
        with self._unit() as session:
            attempt = session.execute(select(InterpretationAttempt.intake_record_id).where(
                InterpretationAttempt.owner_id == uuid.UUID(settlement.owner_id),
                InterpretationAttempt.attempt_id == uuid.UUID(settlement.attempt_id))).scalar_one()
            usage = settlement.usage
            row = InterpretationSettlement(
                attempt_id=uuid.UUID(settlement.attempt_id), owner_id=uuid.UUID(settlement.owner_id),
                intake_record_id=attempt, status=settlement.status, finished_at=settlement.finished_at,
                latency_ms=settlement.latency_ms, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens, usage_source=usage.source, request_count=settlement.request_count,
                response_sha256=settlement.response_sha256, response_text=settlement.response_text,
                parse_result=settlement.parse_result, error_class=settlement.error_class,
                runtime_observed=dict(settlement.runtime_observed))
            self._insert(session, row, {"interpretation_settlements_pkey": AlreadySettled("This attempt already settled.")})

    def add_link(self, owner_id: str, attempt_id: str, revision_id: str,
                 offered_questions: Sequence[Mapping[str, Any]]) -> None:
        with self._unit() as session:
            intake = session.execute(select(InterpretationAttempt.intake_record_id).where(
                InterpretationAttempt.owner_id == uuid.UUID(owner_id),
                InterpretationAttempt.attempt_id == uuid.UUID(attempt_id))).scalar_one()
            row = InterpretationAttemptLink(
                attempt_id=uuid.UUID(attempt_id), owner_id=uuid.UUID(owner_id), intake_record_id=intake,
                revision_record_id=uuid.UUID(revision_id), settled_status="COMPLETED", settled_parse_result="ACCEPTED",
                offered_questions=[dict(question) for question in offered_questions],
                created_at=dt.datetime.now(dt.timezone.utc))
            self._insert(session, row, {"interpretation_attempt_links_pkey": AlreadyLinked("Already linked."),
                                        "uq_attempt_link_owner_revision": AlreadyLinked("Already linked.")})

    def add_observation(self, observation: LateResult) -> None:
        with self._unit() as session:
            settled = session.execute(select(InterpretationSettlement).where(
                InterpretationSettlement.owner_id == uuid.UUID(observation.owner_id),
                InterpretationSettlement.attempt_id == uuid.UUID(observation.attempt_id))).scalar_one()
            usage = observation.usage
            row = InterpretationLateResult(
                observation_id=uuid.UUID(observation.observation_id), attempt_id=settled.attempt_id,
                owner_id=settled.owner_id, intake_record_id=settled.intake_record_id, settled_status=settled.status,
                observed_at=observation.observed_at, status=observation.status, input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens, total_tokens=usage.total_tokens, usage_source=usage.source,
                request_count=observation.request_count, response_sha256=observation.response_sha256,
                response_text=observation.response_text, error_class=observation.error_class)
            self._insert(session, row, {})

    def find_start(self, owner_id: str, attempt_id: str) -> AttemptStart | None:
        with self._unit() as session:
            row = session.execute(select(InterpretationAttempt).where(
                InterpretationAttempt.owner_id == uuid.UUID(owner_id),
                InterpretationAttempt.attempt_id == uuid.UUID(attempt_id))).scalar_one_or_none()
            return _start_of(row) if row is not None else None

    def starts(self, owner_id: str, intake_record_id: str) -> Sequence[AttemptStart]:
        with self._unit() as session:
            rows = session.execute(select(InterpretationAttempt).where(
                InterpretationAttempt.owner_id == uuid.UUID(owner_id),
                InterpretationAttempt.intake_record_id == uuid.UUID(intake_record_id))
                .order_by(InterpretationAttempt.sequence)).scalars()
            return [_start_of(row) for row in rows]

    def settlements(self, owner_id: str, intake_record_id: str) -> Sequence[AttemptSettlement]:
        with self._unit() as session:
            rows = session.execute(select(InterpretationSettlement).where(
                InterpretationSettlement.owner_id == uuid.UUID(owner_id),
                InterpretationSettlement.intake_record_id == uuid.UUID(intake_record_id))
                .order_by(InterpretationSettlement.finished_at)).scalars()
            return [_settlement_of(row) for row in rows]

    def links(self, owner_id: str, intake_record_id: str) -> Mapping[str, str]:
        with self._unit() as session:
            rows = session.execute(select(InterpretationAttemptLink).where(
                InterpretationAttemptLink.owner_id == uuid.UUID(owner_id),
                InterpretationAttemptLink.intake_record_id == uuid.UUID(intake_record_id))).scalars()
            return {str(row.attempt_id): str(row.revision_record_id) for row in rows}

    def observations(self, owner_id: str, intake_record_id: str) -> Sequence[LateResult]:
        with self._unit() as session:
            rows = session.execute(select(InterpretationLateResult).where(
                InterpretationLateResult.owner_id == uuid.UUID(owner_id),
                InterpretationLateResult.intake_record_id == uuid.UUID(intake_record_id))
                .order_by(InterpretationLateResult.observed_at)).scalars()
            return [_late_result_of(row) for row in rows]

    def offered_questions(self, owner_id: str, intake_record_id: str, revision_id: str) -> Sequence[Mapping[str, Any]]:
        with self._unit() as session:
            row = session.execute(select(InterpretationAttemptLink.offered_questions).where(
                InterpretationAttemptLink.owner_id == uuid.UUID(owner_id),
                InterpretationAttemptLink.intake_record_id == uuid.UUID(intake_record_id),
                InterpretationAttemptLink.revision_record_id == uuid.UUID(revision_id))).scalar_one_or_none()
            return list(row) if row is not None else []


class ClaimHeld(RuntimeError):
    """Another connection already holds the claim for this attempt."""


def _lock_key(attempt_id: str) -> int:
    digest = hashlib.sha256(f"edge-os:p05:attempt:{uuid.UUID(attempt_id)}".encode()).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


class AdvisoryLockGuard:
    """The claim is a PostgreSQL session lock on an idle, dedicated connection. It never sits inside a transaction."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def claim(self, attempt_id: str) -> Iterator[None]:
        key = {"key": _lock_key(attempt_id)}
        connection = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            if not connection.execute(text("SELECT pg_try_advisory_lock(:key)"), key).scalar_one():
                raise ClaimHeld("Another worker holds the claim for this attempt.")
            try:
                yield
            finally:
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), key)
                except Exception:  # noqa: BLE001 - a connection that cannot unlock must not return to the pool
                    connection.invalidate()
        finally:
            connection.close()

    def is_abandoned(self, attempt_id: str) -> bool:
        """True only when nobody holds the claim. A failed probe proves nothing, so it is reported as not abandoned."""
        key = {"key": _lock_key(attempt_id)}
        try:
            with self._engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                if not connection.execute(text("SELECT pg_try_advisory_lock(:key)"), key).scalar_one():
                    return False
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), key)
                except Exception:  # noqa: BLE001 - a connection that cannot unlock must not return to the pool
                    connection.invalidate()
                return True
        except Exception:  # noqa: BLE001
            return False
