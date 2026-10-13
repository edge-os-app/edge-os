"""P27 LOCAL recurring operation on the existing evaluation job engine.

A deployment is the owner's explicit recurring authorization for one adopted consent of one agent wallet. The
producer (`RecurringOperation.producer_pass`) does three bounded things per pass:

1. `tick`: for each ACTIVE deployment, under its locked row, re-resolve identity and authority (ending the
   deployment when they changed, expired or were removed), record slots missed while no producer ran, and save
   one ordinary evaluation job for the current due five-minute slot. The existing unique slot constraint keeps one
   job per consent and slot across producers, repeats and manual runs.
2. `reconcile_pending`: settle each SUBMITTED occurrence's original action from its independent receipt through
   `ConnectedExecution.reconcile_action`. Nothing is re-signed, repriced, resent or replaced.
3. one bounded worker pass over runnable jobs (`ConnectedExecution.run_pending` or the given jobs).

`projection` is the one durable view the direct account page reads. See
`docs/qualification/recurring-operation/CONTRACT.md`.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.execution.connected_identity import adopted_consent, derive_approval, resolve_agent
from edge_os_api.execution.models import (MISSED_INTERVALS_KEPT, EvaluationJobRow, EvaluationOutcomeRow, QueueRow,
                                          RecurringDeploymentRow, SubmissionAttemptRow)
from edge_os_api.execution.types import utc_iso
from edge_os_api.execution.worker import RUNNABLE, SLOT, ConnectedExecution, JobRefused, decision_slot, job_view

log = logging.getLogger("edge_os.recurring")

PRODUCER_LABEL = "recurring-producer/1"
OCCURRENCES_SHOWN = 20
UNSETTLED_QUEUE = ("CLAIMED", "SUBMITTED_UNKNOWN", "BREACHED", "RECONCILE_MISMATCH")
# A producer not seen for two slots is reported, never assumed alive.
PRODUCER_SILENCE = 2 * SLOT


class DeploymentRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(value: dt.datetime | None) -> str | None:
    return None if value is None else utc_iso(value)


def deployment_view(row: RecurringDeploymentRow) -> dict[str, Any]:
    return {"deployment_id": str(row.deployment_id), "state": row.state, "end_reason": row.end_reason,
            "request_key": row.request_key, "activated_at": _iso(row.activated_at), "ended_at": _iso(row.ended_at),
            "identity": {"agent_id": row.agent_id, "wallet_id": row.wallet_id, "network_id": row.network_id,
                         "strategy_id": row.strategy_id, "publication_revision_id": str(row.publication_revision_id),
                         "execution_revision_id": row.execution_revision_id, "content_hash": row.content_hash,
                         "manifest_hash": row.manifest_hash, "consent_adoption_id": str(row.consent_adoption_id),
                         "consent_hash": row.consent_hash}}


class RecurringOperation:
    def __init__(self, factory: sessionmaker[Session], services: Any, connected: ConnectedExecution, *,
                 clock: Callable[[], dt.datetime] | None = None) -> None:
        self._factory = factory
        self._services = services
        self._connected = connected
        self._clock = clock or _utc_now

    # ------------------------------------------------------------------------------ activation

    def activate(self, owner_id: uuid.UUID, agent_id: str, request_key: str,
                 expected_consent_hash: str) -> tuple[bool, dict[str, Any]]:
        """Save the one deployment for the agent's current adopted consent. Returns (created, deployment)."""
        now = self._clock()
        with self._factory() as session:
            by_key = session.execute(select(RecurringDeploymentRow).where(
                RecurringDeploymentRow.owner_id == owner_id, RecurringDeploymentRow.agent_id == agent_id,
                RecurringDeploymentRow.request_key == request_key)).scalar_one_or_none()
            if by_key is not None:
                return False, deployment_view(by_key)
            agent = resolve_agent(session, owner_id, agent_id)
            if agent is None:
                raise DeploymentRefused("agent_not_ready")
            consent = adopted_consent(session, agent)
            if consent is None:
                raise DeploymentRefused("consent_not_adopted")
            if consent.consent_hash != expected_consent_hash:
                raise DeploymentRefused("deployment_consent_mismatch")
            existing = self._for_consent(session, owner_id, consent.adoption_id)
            if existing is not None:
                if existing.state == "ENDED":
                    raise DeploymentRefused("deployment_ended")
                return False, deployment_view(existing)
            if self._services.removals.submission_denial(session, owner_id, agent_id=agent_id,
                                                         wallet_id=agent.wallet_id, network_id=agent.network_id):
                raise DeploymentRefused("agent_removed")
            approval, reason = derive_approval(agent, consent, qualification=self._connected.qualification, now=now)
            if approval is None:
                raise DeploymentRefused("activation_unavailable" if reason == "ACTIVATION_UNAVAILABLE"
                                        else (reason or "activation_unavailable").lower())
            # A newer adopted consent supersedes an older deployment of the same agent wallet.
            for older in session.execute(select(RecurringDeploymentRow).where(
                    RecurringDeploymentRow.owner_id == owner_id, RecurringDeploymentRow.agent_id == agent_id,
                    RecurringDeploymentRow.wallet_id == agent.wallet_id,
                    RecurringDeploymentRow.network_id == agent.network_id,
                    RecurringDeploymentRow.state == "ACTIVE").with_for_update()).scalars():
                self._end(older, "CONSENT_CHANGED", now)
            session.flush()
            inserted = session.execute(pg_insert(RecurringDeploymentRow).values(
                deployment_id=uuid.uuid4(), owner_id=owner_id, agent_id=agent_id, wallet_id=agent.wallet_id,
                network_id=agent.network_id, request_key=request_key, strategy_id=agent.strategy_id,
                publication_revision_id=agent.publication_revision_id,
                execution_revision_id=agent.revision.revision_id, content_hash=agent.revision.content_hash,
                manifest_hash=agent.revision.manifest_hash, consent_adoption_id=consent.adoption_id,
                consent_hash=consent.consent_hash, state="ACTIVE", missed_intervals=[], activated_at=now,
                updated_at=now).on_conflict_do_nothing().returning(RecurringDeploymentRow.deployment_id)
            ).scalar_one_or_none()
            session.commit()
            row = (self._for_consent(session, owner_id, consent.adoption_id) if inserted is None else
                   session.get(RecurringDeploymentRow, inserted))
            if row is None:  # a concurrent activation with another key won on the active-wallet index
                row = self._active(session, owner_id, agent_id)
            if row is None:
                raise DeploymentRefused("deployment_conflict")
            return inserted is not None, deployment_view(row)

    def end(self, owner_id: uuid.UUID, agent_id: str) -> dict[str, Any]:
        """End the agent's ACTIVE deployment. Already sent actions and their liability stay as saved."""
        now = self._clock()
        with self._factory() as session:
            row = session.execute(select(RecurringDeploymentRow).where(
                RecurringDeploymentRow.owner_id == owner_id, RecurringDeploymentRow.agent_id == agent_id,
                RecurringDeploymentRow.state == "ACTIVE").with_for_update()).scalar_one_or_none()
            if row is not None:
                self._end(row, "OWNER_ENDED", now)
                session.commit()
                return deployment_view(row)
            latest = self._latest(session, owner_id, agent_id)
            if latest is None:
                raise DeploymentRefused("deployment_not_found")
            return deployment_view(latest)

    # --------------------------------------------------------------------------------- producer

    def tick(self, only: Iterable[uuid.UUID] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Save the current due occurrence for each ACTIVE deployment. A deployment another producer holds is
        skipped; the unique slot constraint keeps one job per consent and slot in any case."""
        with self._factory() as session:
            statement = select(RecurringDeploymentRow.deployment_id).where(RecurringDeploymentRow.state == "ACTIVE")
            if only is not None:
                statement = statement.where(RecurringDeploymentRow.deployment_id.in_(list(only)))
            # Least recently ticked first, so a bounded window rotates through every ACTIVE deployment.
            ids = list(session.execute(statement.order_by(
                RecurringDeploymentRow.last_tick_at.asc().nulls_first(), RecurringDeploymentRow.deployment_id)
                .limit(limit)).scalars().all())
        results = []
        for deployment_id in ids:
            try:
                result = self._tick_one(deployment_id)
            except Exception as error:  # noqa: BLE001 - one deployment's failure must not stop other owners' work
                # Nothing of the failed tick committed; the class only, never a message with private detail.
                log.error("recurring tick %s failed: %s", deployment_id, type(error).__name__)
                results.append({"deployment_id": str(deployment_id), "failed": type(error).__name__})
                continue
            if result is not None:
                results.append(result)
        return results

    def _tick_one(self, deployment_id: uuid.UUID) -> dict[str, Any] | None:
        now = self._clock()
        with self._factory() as session:
            row = session.execute(select(RecurringDeploymentRow).where(
                RecurringDeploymentRow.deployment_id == deployment_id, RecurringDeploymentRow.state == "ACTIVE")
                .with_for_update(skip_locked=True)).scalar_one_or_none()
            if row is None:
                return None
            problem = self._authority_problem(session, row, now)
            if problem is not None:
                self._end(row, problem, now)
                session.commit()
                return {"deployment_id": str(deployment_id), "ended": problem}
            due = decision_slot(now)
            row.last_tick_at, row.updated_at = now, now
            if row.cursor_slot is not None and due <= row.cursor_slot:
                session.commit()
                return {"deployment_id": str(deployment_id), "slot": _iso(due), "created": False}
            # The first slot this deployment owes work for is the slot after the saved cursor, or, before any tick,
            # the slot in which the owner activated it. Every owed slot before the current one was missed: it is
            # counted with its reason and never replayed.
            first_owed = row.cursor_slot + SLOT if row.cursor_slot is not None else decision_slot(row.activated_at)
            if due > first_owed:
                missed = int((due - first_owed) / SLOT)
                row.missed_slots = int(row.missed_slots) + missed
                interval = {"from": _iso(first_owed), "to": _iso(due - SLOT), "count": missed,
                            "reason": "PRODUCER_ABSENT", "recorded_at": _iso(now)}
                row.missed_intervals = [*row.missed_intervals, interval][-MISSED_INTERVALS_KEPT:]
            inserted = session.execute(pg_insert(EvaluationJobRow).values(
                job_id=uuid.uuid4(), owner_id=row.owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id,
                network_id=row.network_id, request_key=f"recurring:{row.deployment_id}:{_iso(due)}",
                decision_slot=due, strategy_id=row.strategy_id, publication_revision_id=row.publication_revision_id,
                execution_revision_id=row.execution_revision_id, content_hash=row.content_hash,
                manifest_hash=row.manifest_hash, consent_adoption_id=row.consent_adoption_id,
                consent_hash=row.consent_hash, state="QUEUED", deployment_id=row.deployment_id,
                provenance={"producer": PRODUCER_LABEL, "deployment_id": str(row.deployment_id),
                            "scheduled_at": now.isoformat()},
                created_at=now, updated_at=now).on_conflict_do_nothing().returning(EvaluationJobRow.job_id)
            ).scalar_one_or_none()
            row.cursor_slot = due
            if inserted is not None:
                row.occurrences = int(row.occurrences) + 1
            session.commit()
            return {"deployment_id": str(deployment_id), "slot": _iso(due), "created": inserted is not None,
                    "job_id": None if inserted is None else str(inserted)}

    def _authority_problem(self, session: Session, row: RecurringDeploymentRow, now: dt.datetime) -> str | None:
        """Why this deployment may no longer produce work, read from saved server state only."""
        agent = resolve_agent(session, row.owner_id, row.agent_id)
        if agent is None or (agent.wallet_id, agent.network_id, agent.publication_revision_id,
                             agent.revision.revision_id) != (row.wallet_id, row.network_id,
                                                             row.publication_revision_id, row.execution_revision_id):
            return "IDENTITY_CHANGED"
        consent = adopted_consent(session, agent)
        if consent is None or (consent.adoption_id, consent.consent_hash) != (row.consent_adoption_id,
                                                                             row.consent_hash):
            return "CONSENT_CHANGED"
        if self._services.removals.submission_denial(session, row.owner_id, agent_id=row.agent_id,
                                                     wallet_id=row.wallet_id, network_id=row.network_id):
            return "REMOVAL_REQUESTED"
        approval, reason = derive_approval(agent, consent, qualification=self._connected.qualification, now=now)
        return None if approval is not None else (reason or "ACTIVATION_UNAVAILABLE")

    def reconcile_pending(self, only: Iterable[uuid.UUID] | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Settle SUBMITTED occurrences from their receipts. A missing receipt leaves the original waiting."""
        with self._factory() as session:
            statement = select(EvaluationJobRow.job_id, EvaluationJobRow.owner_id, EvaluationJobRow.action_id).where(
                EvaluationJobRow.deployment_id.is_not(None), EvaluationJobRow.state == "SUBMITTED",
                EvaluationJobRow.action_id.is_not(None))
            if only is not None:
                statement = statement.where(EvaluationJobRow.deployment_id.in_(list(only)))
            # Least recently tried first: an original that never settles moves to the back after each try, so it
            # cannot hold the window for another action or another owner.
            pending = session.execute(statement.order_by(EvaluationJobRow.updated_at, EvaluationJobRow.job_id)
                                      .limit(limit)).all()
        results = []
        for job_id, owner_id, action_id in pending:
            try:
                view = self._connected.reconcile_action(owner_id, action_id)
                results.append({"action_id": action_id, "case_state": view.case_state, "applied": view.applied})
            except JobRefused as refused:
                results.append({"action_id": action_id, "waiting": refused.code})
            except Exception as error:  # noqa: BLE001 - one owner's receipt failure must not stop other owners
                log.error("recurring reconciliation of %s failed: %s", action_id, type(error).__name__)
                results.append({"action_id": action_id, "failed": type(error).__name__})
            self._connected.touch(job_id)  # the try is recorded on the job, which rotates the window
        return results

    def producer_pass(self, only: Iterable[uuid.UUID] | None = None, worker_limit: int = 20) -> list[dict[str, Any]]:
        """One bounded producer pass: tick, reconcile, then advance runnable jobs once."""
        scope = None if only is None else list(only)
        results: list[dict[str, Any]] = [*self.tick(scope), *self.reconcile_pending(scope)]
        # The producer advances its own occurrences only; manual evaluations stay with the bounded worker process.
        # Either may advance an occurrence: the per-job advisory lock lets only one hold it at a time.
        with self._factory() as session:
            statement = select(EvaluationJobRow.job_id).where(EvaluationJobRow.deployment_id.is_not(None),
                                                              EvaluationJobRow.state.in_(RUNNABLE))
            if scope is not None:
                statement = statement.where(EvaluationJobRow.deployment_id.in_(scope))
            job_ids = list(session.execute(statement.order_by(EvaluationJobRow.created_at).limit(worker_limit))
                           .scalars().all())
        for job_id in job_ids:
            try:
                advanced = self._connected.run_job(job_id)
            except Exception as error:  # noqa: BLE001 - one failing occurrence must not stop other owners' work
                # Saved stage state stays as it was; the class only, never a message that could carry private bytes.
                self._connected.record_failure(job_id, type(error).__name__)
                continue
            if advanced is not None:
                results.append(advanced)
        return results

    # ------------------------------------------------------------------------------ projection

    def projection(self, owner_id: uuid.UUID, agent_id: str) -> dict[str, Any]:
        """The durable recurring view: deployment, producer cursor, occurrences, pending reconciliation, wait."""
        now = self._clock()
        with self._factory() as session:
            row = self._latest(session, owner_id, agent_id)
            if row is None:
                return {"deployment": None}
            jobs = session.execute(select(EvaluationJobRow).where(
                EvaluationJobRow.owner_id == owner_id, EvaluationJobRow.deployment_id == row.deployment_id)
                .order_by(EvaluationJobRow.decision_slot.desc()).limit(OCCURRENCES_SHOWN)).scalars().all()
            outcomes = {item.job_id: item for item in session.execute(select(EvaluationOutcomeRow).where(
                EvaluationOutcomeRow.owner_id == owner_id,
                EvaluationOutcomeRow.job_id.in_([job.job_id for job in jobs]))).scalars()}
            actions = [job.action_id for job in jobs if job.action_id]
            attempts: dict[str, SubmissionAttemptRow] = {}
            for attempt in session.execute(select(SubmissionAttemptRow).where(
                    SubmissionAttemptRow.owner_id == owner_id, SubmissionAttemptRow.action_id.in_(actions))
                    .order_by(SubmissionAttemptRow.started_at)).scalars():
                attempts[attempt.action_id] = attempt  # the latest attempt per action
            pending = [entry.action_id for entry in session.execute(select(QueueRow).where(
                QueueRow.owner_id == owner_id, QueueRow.agent_id == agent_id, QueueRow.wallet_id == row.wallet_id,
                QueueRow.network_id == row.network_id, QueueRow.state.in_(UNSETTLED_QUEUE))
                .order_by(QueueRow.enqueued_at)).scalars()]
            removal = self._services.removals.submission_denial(session, owner_id, agent_id=agent_id,
                                                                wallet_id=row.wallet_id, network_id=row.network_id)
        stops = sorted({stop.mode for stop in self._services.stops.retrieve_stops(
            owner_id, agent_id=agent_id, wallet_id=row.wallet_id, network_id=row.network_id)
            if stop.scope == "AGENT_WALLET_NETWORK"})
        active = row.state == "ACTIVE"
        if not active:
            wait = f"ENDED:{row.end_reason}"
        elif removal:
            wait = f"REMOVAL:{','.join(removal)}"
        elif pending:
            wait = "WAITING_RECONCILIATION"
        elif stops:
            wait = f"STOPPED:{','.join(stops)}"
        else:
            wait = None
        silent = active and (row.last_tick_at is None or now - row.last_tick_at > PRODUCER_SILENCE)
        if wait is None and silent:
            wait = "PRODUCER_NOT_SEEN"

        def occurrence(job: EvaluationJobRow) -> dict[str, Any]:
            outcome = outcomes.get(job.job_id)
            attempt = attempts.get(job.action_id) if job.action_id else None
            return {**job_view(job),
                    "evaluation": None if outcome is None else {
                        "outcome": outcome.outcome, "reason": outcome.reason,
                        "decision_id": str(outcome.decision_id) if outcome.decision_id else None,
                        "inputs_observed_at": _iso(outcome.inputs_observed_at),
                        "inputs_collected_at": _iso(outcome.inputs_collected_at),
                        "evaluated_at": _iso(outcome.evaluated_at),
                        "evidence_class": outcome.provenance.get("evidence_class")},
                    "submission": None if attempt is None else {
                        "attempt_id": str(attempt.attempt_id), "state": attempt.state, "outcome": attempt.outcome,
                        "started_at": _iso(attempt.started_at), "completed_at": _iso(attempt.completed_at)}}

        return {"deployment": deployment_view(row),
                # The next due slot is shown only while a producer is seen; a silent producer has no next work.
                "producer": {"last_tick_at": _iso(row.last_tick_at), "cursor_slot": _iso(row.cursor_slot),
                             "producer_silent": silent,
                             "next_due_slot": _iso(row.cursor_slot + SLOT)
                             if active and row.cursor_slot and not silent else None,
                             "no_next_reason": row.end_reason if not active else (
                                 "PRODUCER_NOT_SEEN" if silent else None),
                             "occurrences": int(row.occurrences), "missed_slots": int(row.missed_slots),
                             "missed_intervals": list(row.missed_intervals)},
                "occurrences": [occurrence(job) for job in jobs],
                "pending_reconciliation": pending, "stops": stops, "removal": removal, "wait_reason": wait,
                "read_at": _iso(now)}

    # -------------------------------------------------------------------------------- helpers

    @staticmethod
    def _end(row: RecurringDeploymentRow, reason: str, now: dt.datetime) -> None:
        row.state, row.end_reason, row.ended_at, row.updated_at = "ENDED", reason, now, now

    @staticmethod
    def _for_consent(session: Session, owner_id: uuid.UUID, adoption_id: uuid.UUID) -> RecurringDeploymentRow | None:
        return session.execute(select(RecurringDeploymentRow).where(
            RecurringDeploymentRow.owner_id == owner_id,
            RecurringDeploymentRow.consent_adoption_id == adoption_id)).scalar_one_or_none()

    @staticmethod
    def _active(session: Session, owner_id: uuid.UUID, agent_id: str) -> RecurringDeploymentRow | None:
        return session.execute(select(RecurringDeploymentRow).where(
            RecurringDeploymentRow.owner_id == owner_id, RecurringDeploymentRow.agent_id == agent_id,
            RecurringDeploymentRow.state == "ACTIVE")).scalar_one_or_none()

    @staticmethod
    def _latest(session: Session, owner_id: uuid.UUID, agent_id: str) -> RecurringDeploymentRow | None:
        return session.execute(select(RecurringDeploymentRow).where(
            RecurringDeploymentRow.owner_id == owner_id, RecurringDeploymentRow.agent_id == agent_id)
            .order_by(RecurringDeploymentRow.activated_at.desc(), RecurringDeploymentRow.deployment_id.desc())
            .limit(1)).scalar_one_or_none()
