"""Owned P23 execution tables and the #58 durable evaluation jobs.

Migration 0008 creates these tables in the `execution_local` schema. The migrated
`public` schema and the P22 `admission_local` schema stay separate.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    MetaData,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "pk": "%(table_name)s_pkey",
}

NOW = text("now()")

DECISION_STATES = ("SIGNAL", "NO_SIGNAL", "INELIGIBLE")
QUEUE_STATES = (
    "QUEUED", "CLAIMED", "REVALIDATION_DENIED", "ADMISSION_DENIED", "BREACHED", "RECONCILE_MISMATCH",
    "SUBMISSION_NOT_OWNED", "SUBMITTED_CONFIRMED", "SUBMITTED_REVERTED", "SUBMITTED_UNKNOWN", "DENIED_UNSENT",
)
ATTEMPT_STATES = ("IN_FLIGHT", "TERMINAL")


class ExecutionBase(DeclarativeBase):
    # Owned tables live in their own schema. The schema is created by the owned
    # test fixture inside the run-labelled test database only.
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="execution_local")


class DecisionRow(ExecutionBase):
    """Saved evaluation of one immutable revision at one controlled decision time."""

    __tablename__ = "execution_decisions"
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    market_binding_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str | None] = mapped_column(Text)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    rule_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    inputs_hash: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "decision_id", name="uq_execution_decisions_owner_decision"),
        CheckConstraint("status IN ('SIGNAL','NO_SIGNAL','INELIGIBLE')", name="ck_execution_decisions_status"),
        Index("ix_execution_decisions_owner_wallet", "owner_id", "wallet_id", "network_id"),
        Index("ix_execution_decisions_owner_revision", "owner_id", "revision_id"),
    )


class IntentRow(ExecutionBase):
    """One exact immutable intent linked to its saved decision. Owner-scoped, replay-safe."""

    __tablename__ = "execution_intents"
    intent_id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    review_hash: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    position_id: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    mandate_id: Mapped[str] = mapped_column(Text, nullable=False)
    policy_binding: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    admission_status: Mapped[str] = mapped_column(Text, nullable=False)
    admission_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "intent_id", name="uq_execution_intents_owner_intent"),
        UniqueConstraint("owner_id", "action_id", name="uq_execution_intents_owner_action"),
        CheckConstraint("operation IN ('ENTRY','EXIT')", name="ck_execution_intents_operation"),
        Index("ix_execution_intents_owner_decision", "owner_id", "decision_id"),
    )


class QueueRow(ExecutionBase):
    """One durable queue entry for an admitted action, with its selection priority and state."""

    __tablename__ = "execution_queue"
    queue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    intent_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    position_id: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    blocking_reason: Mapped[str | None] = mapped_column(Text)
    revalidation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enqueued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "action_id", name="uq_execution_queue_owner_action"),
        CheckConstraint(
            "state IN ('QUEUED','CLAIMED','REVALIDATION_DENIED','ADMISSION_DENIED','BREACHED','RECONCILE_MISMATCH',"
            "'SUBMISSION_NOT_OWNED','SUBMITTED_CONFIRMED','SUBMITTED_REVERTED','SUBMITTED_UNKNOWN','DENIED_UNSENT')",
            name="ck_execution_queue_state",
        ),
        Index("ix_execution_queue_owner_wallet_state", "owner_id", "wallet_id", "network_id", "state"),
        Index("ix_execution_queue_owner_order", "owner_id", "priority", "enqueued_at", "queue_id"),
    )


class ClaimRow(ExecutionBase):
    """Exclusive submission claim per owner/agent/wallet/network. A released claim frees the key."""

    __tablename__ = "execution_claims"
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    queue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    acquired_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)
    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("state IN ('ACTIVE','RELEASED')", name="ck_execution_claims_state"),
        # One active claim per wallet and network across positions.
        Index("uq_execution_claims_active_wallet", "owner_id", "agent_id", "wallet_id", "network_id",
              unique=True, postgresql_where=text("released_at IS NULL")),
    )


class SubmissionAttemptRow(ExecutionBase):
    """Append-then-transition immutable evidence for one submission-capable fixture call."""

    __tablename__ = "execution_submission_attempts"
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    queue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    transport_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("state IN ('IN_FLIGHT','TERMINAL')", name="ck_execution_attempts_state"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('DEFINITELY_UNSENT','SUBMISSION_POSSIBLE','CONFIRMED','REVERTED')",
            name="ck_execution_attempts_outcome",
        ),
        Index("ix_execution_attempts_owner_wallet", "owner_id", "wallet_id", "network_id", "started_at"),
        Index("ix_execution_attempts_owner_action", "owner_id", "action_id"),
    )


JOB_STATES = ("QUEUED", "DECIDED", "ENQUEUED", "SUBMITTED", "COMPLETED", "UNAVAILABLE")


class EvaluationJobRow(ExecutionBase):
    """One durable bounded evaluation job for one approved agent and one five-minute decision slot.

    The job identity is stable: the same owner, agent, adopted consent and decision slot resolve to one row,
    however often the job is scheduled, so a repeat or a restart cannot create a replacement decision or
    intent. The row also binds the saved publication revision UUID to the hash-derived execution revision
    identity (IC01), and keeps the progress of the original decision, intent and action.
    """

    __tablename__ = "execution_evaluation_jobs"
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    request_key: Mapped[str] = mapped_column(Text, nullable=False)
    decision_slot: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    publication_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    execution_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    consent_adoption_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consent_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action_id: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    runs: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # P27: the recurring deployment that produced this occurrence; None for a manual evaluation (migration 0012).
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("owner_id", "agent_id", "request_key", name="uq_execution_jobs_owner_agent_request"),
        UniqueConstraint("owner_id", "agent_id", "consent_adoption_id", "decision_slot",
                         name="uq_execution_jobs_owner_agent_consent_slot"),
        CheckConstraint("state IN ('QUEUED','DECIDED','ENQUEUED','SUBMITTED','COMPLETED','UNAVAILABLE')",
                        name="ck_execution_jobs_state"),
        CheckConstraint("length(request_key) BETWEEN 1 AND 200", name="ck_execution_jobs_request_key"),
        Index("ix_execution_jobs_state", "state", "created_at"),
        Index("ix_execution_jobs_owner_agent", "owner_id", "agent_id", "created_at"),
        Index("ix_execution_jobs_deployment", "deployment_id", "decision_slot"),
    )


EVALUATION_OUTCOMES = ("SIGNAL", "NO_SIGNAL", "INELIGIBLE", "UNAVAILABLE")


class EvaluationOutcomeRow(ExecutionBase):
    """The one saved evaluation outcome of one job, written before any intent (P27, migration 0012).

    `execution_decisions` keeps its three statuses; an UNAVAILABLE evaluation has no decision row, so this row is
    what records it. Input observed time, input collection time and evaluation time stay separate.
    """

    __tablename__ = "execution_evaluation_outcomes"
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_slot: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    inputs_observed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    inputs_collected_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    evaluated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        CheckConstraint("outcome IN ('SIGNAL','NO_SIGNAL','INELIGIBLE','UNAVAILABLE')", name="outcome"),
        CheckConstraint("(outcome = 'UNAVAILABLE') = (decision_id IS NULL)", name="decision_presence"),
        Index("ix_execution_outcomes_owner_agent", "owner_id", "agent_id", "decision_slot"),
    )


DEPLOYMENT_STATES = ("ACTIVE", "ENDED")
MISSED_INTERVALS_KEPT = 20


class RecurringDeploymentRow(ExecutionBase):
    """One explicit recurring authorization for one adopted consent of one agent wallet (P27, migration 0012).

    The producer saves one occurrence job per due five-minute slot while ACTIVE. `cursor_slot` is the last slot it
    saved; slots skipped while no producer ran are counted in `missed_slots` and never replayed. ENDED is terminal.
    """

    __tablename__ = "execution_recurring_deployments"
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    request_key: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    publication_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    execution_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    consent_adoption_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consent_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    end_reason: Mapped[str | None] = mapped_column(Text)
    cursor_slot: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    occurrences: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    missed_slots: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    missed_intervals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    last_tick_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_id", "agent_id", "request_key", name="uq_recurring_deployments_owner_agent_request"),
        UniqueConstraint("owner_id", "consent_adoption_id", name="uq_recurring_deployments_owner_consent"),
        CheckConstraint("state IN ('ACTIVE','ENDED')", name="state"),
        CheckConstraint("(state = 'ENDED') = (end_reason IS NOT NULL AND ended_at IS NOT NULL)", name="ended"),
        CheckConstraint("length(request_key) BETWEEN 1 AND 200", name="request_key"),
        CheckConstraint("missed_slots >= 0 AND occurrences >= 0", name="counts"),
        Index("uq_recurring_deployments_active_wallet", "owner_id", "agent_id", "wallet_id", "network_id",
              unique=True, postgresql_where=text("state = 'ACTIVE'")),
        Index("ix_recurring_deployments_state", "state", "deployment_id"),
    )
