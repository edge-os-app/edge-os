"""Owned P22 admission tables.

These tables belong to the local admission stage. They are created by the
owned package metadata inside a run-labelled test database and are never
published through a shared migration in this stage.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    MetaData,
    Numeric,
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


class AdmissionBase(DeclarativeBase):
    # Owned tables live in their own schema so the migrated `public` application
    # schema stays exactly as released. The schema is created by the owned test
    # fixture inside the run-labelled test database only.
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="admission_local")


def _raw_column() -> Numeric:
    return mapped_column(Numeric(78, 0), nullable=False)


class DecisionRow(AdmissionBase):
    """Saved admission or denial for one action identity."""

    __tablename__ = "admission_decisions"
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    review_hash: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    binding: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "action_id", name="uq_admission_decisions_owner_action"),
        CheckConstraint("status IN ('PROPOSED','ADMITTED','DENIED','CANCELLED','CONFIRMED','REVERTED','SUBMISSION_UNKNOWN')",
                        name="ck_admission_decisions_status"),
        Index("ix_admission_decisions_owner_wallet", "owner_id", "wallet_id", "network_id"),
        Index("ix_admission_decisions_owner_agent", "owner_id", "agent_id"),
    )


class AllowanceRow(AdmissionBase):
    """Per-wallet asset allowance ledger. approved comes from the reviewed approval snapshot."""

    __tablename__ = "admission_allowances"
    allowance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    decimals: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approved: Mapped[Decimal] = _raw_column()
    consumed: Mapped[Decimal] = _raw_column()

    __table_args__ = (
        UniqueConstraint("owner_id", "agent_id", "wallet_id", "network_id", "asset_id",
                         name="uq_admission_allowances_key"),
        CheckConstraint("approved >= 0 AND consumed >= 0", name="ck_admission_allowances_non_negative"),
    )


class ReservationRow(AdmissionBase):
    """One atomic reservation. Unique action-scope-asset-position preserves the original
    action identity and prevents a double reservation of the same atom."""

    __tablename__ = "admission_reservations"
    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_id: Mapped[str] = mapped_column(Text, nullable=False)
    review_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    position_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    decimals: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw: Mapped[Decimal] = _raw_column()
    state: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)
    reconciled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("owner_id", "action_id", "scope", "asset_id", "position_id",
                         name="uq_admission_reservations_atom"),
        CheckConstraint("state IN ('RESERVED','CONSUMED','RELEASED')", name="ck_admission_reservations_state"),
        CheckConstraint("raw >= 0", name="ck_admission_reservations_non_negative"),
        Index("ix_admission_reservations_owner_wallet_state", "owner_id", "wallet_id", "network_id", "asset_id", "state"),
        Index("ix_admission_reservations_owner_position", "owner_id", "position_id", "state"),
    )


class PositionRow(AdmissionBase):
    """Reconciled attributed inventory per position."""

    __tablename__ = "admission_positions"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position_id: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    decimals: Mapped[int] = mapped_column(BigInteger, nullable=False)
    inventory: Mapped[Decimal] = _raw_column()

    __table_args__ = (
        PrimaryKeyConstraint("owner_id", "position_id", name="pk_admission_positions"),
        CheckConstraint("inventory >= 0", name="ck_admission_positions_non_negative"),
    )