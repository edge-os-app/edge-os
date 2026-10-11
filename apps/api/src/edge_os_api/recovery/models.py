"""Owned P24 recovery tables.

These tables belong to the local original-action recovery stage. They are created
by the owned package metadata inside a run-labelled test database and are never
published through a shared migration in this stage. The recovery schema stays
separate from the P22 `admission_local` and P23 `execution_local` schemas.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    MetaData,
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

CASE_STATES = (
    "OPEN", "CONFIRMED", "REVERTED", "DENIED_UNSENT", "UNKNOWN",
    "BREACHED", "RECONCILE_MISMATCH", "DISCREPANCY", "NO_ADMISSION_DECISION",
)
EVIDENCE_STATES = ("PENDING", "ACCEPTED", "REJECTED")


class RecoveryBase(DeclarativeBase):
    # Owned tables live in their own schema, created by the owned test fixture
    # inside the run-labelled test database only.
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="recovery_local")


class RecoveryCaseRow(RecoveryBase):
    """One durable recovery record per owner and original action.

    It preserves the original action identity and frozen references across a
    restart, so recovery never infers a new identity or opens a second economic
    action for the same decision.
    """

    __tablename__ = "recovery_cases"
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    policy_binding: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    blocking_reason: Mapped[str | None] = mapped_column(Text)
    decision_status: Mapped[str] = mapped_column(Text, nullable=False)
    queue_state: Mapped[str | None] = mapped_column(Text)
    claim_held: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    delayed_exit: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)
    reconciled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("owner_id", "action_id", name="uq_recovery_cases_owner_action"),
        CheckConstraint(
            "state IN ('OPEN','CONFIRMED','REVERTED','DENIED_UNSENT','UNKNOWN','BREACHED',"
            "'RECONCILE_MISMATCH','DISCREPANCY','NO_ADMISSION_DECISION')",
            name="ck_recovery_cases_state",
        ),
        Index("ix_recovery_cases_owner_wallet", "owner_id", "wallet_id", "network_id"),
    )


class RecoveryEvidenceRow(RecoveryBase):
    """Append-only outcome evidence for one recovery case.

    The (owner, action, fingerprint) uniqueness makes a re-delivered outcome a
    no-op: it is recorded once and applied to the P22 ledger once.
    """

    __tablename__ = "recovery_evidence"
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "action_id", "fingerprint", name="uq_recovery_evidence_fingerprint"),
        CheckConstraint("state IN ('PENDING','ACCEPTED','REJECTED')", name="ck_recovery_evidence_state"),
        Index("ix_recovery_evidence_owner_action", "owner_id", "action_id", "created_at"),
    )
