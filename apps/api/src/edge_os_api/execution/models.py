"""Owned P23 execution tables.

These tables belong to the local execution stage. They are created by the owned
package metadata inside a run-labelled test database and are never published
through a shared migration in this stage. The migrated `public` schema and the
P22 `admission_local` schema stay separate.
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
    "QUEUED", "CLAIMED", "REVALIDATION_DENIED", "ADMISSION_DENIED", "BREACHED",
    "SUBMITTED_CONFIRMED", "SUBMITTED_REVERTED", "SUBMITTED_UNKNOWN", "DENIED_UNSENT",
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
            "state IN ('QUEUED','CLAIMED','REVALIDATION_DENIED','ADMISSION_DENIED','BREACHED',"
            "'SUBMITTED_CONFIRMED','SUBMITTED_REVERTED','SUBMITTED_UNKNOWN','DENIED_UNSENT')",
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
