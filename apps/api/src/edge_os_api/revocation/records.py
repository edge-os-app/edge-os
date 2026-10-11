"""Owned P30 revocation tables.

These tables belong to the local revocation preparation stage. They are created
by the owned package metadata inside a run-labelled test database and are never
published through a shared migration in this stage. The `revocation_local`
schema stays separate from the migrated `public` schema and from every other
owned local schema. This package writes only its own tables: it never writes
holdings, allowances, reservations, claims, recovery cases, funding flows,
stops, inactive consent or a wallet binding.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    MetaData,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

REVOCATION_SCHEMA = "revocation_local"
STATES = ("NOT_REQUESTED", "REQUESTED", "PENDING", "UNKNOWN", "CONFIRMED", "FAILED")
OBSERVATION_STATES = ("PENDING", "UNKNOWN", "CONFIRMED", "FAILED")

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "pk": "%(table_name)s_pkey",
}

NOW = text("now()")


class RevocationBase(DeclarativeBase):
    # Owned tables live in their own schema so the migrated `public` application
    # schema stays exactly as released.
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=REVOCATION_SCHEMA)


class RemovalRequestRow(RevocationBase):
    """One durable owner removal request, persisted before any controlled effect.

    The uniqueness key is the exact removal identity (owner, agent, wallet,
    network). An exact repeated request is idempotent; a changed request key for
    the same identity is refused, so no new identity appears on restart.
    """

    __tablename__ = "removal_requests"
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    request_key: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    signer_identity: Mapped[str | None] = mapped_column(Text)
    policy_identity: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "agent_id", "wallet_id", "network_id", name="uq_removal_requests_identity"),
        UniqueConstraint("owner_id", "request_key", name="uq_removal_requests_owner_key"),
        Index("ix_removal_requests_owner_wallet", "owner_id", "agent_id", "wallet_id", "network_id"),
    )


class RemovalObservationRow(RevocationBase):
    """One append-only provider-style observation, matched or refused.

    A refused observation keeps its stable denial code and never changes the
    derived state. A matched observation that contradicts a confirmed removal is
    retained with `contradictory` set and never restores removed permission.
    """

    __tablename__ = "removal_observations"
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    observation_key: Mapped[str] = mapped_column(Text, nullable=False)
    observed_state: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    signer_identity: Mapped[str | None] = mapped_column(Text)
    policy_identity: Mapped[str | None] = mapped_column(Text)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    contradictory: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    denial_code: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "observation_key", name="uq_removal_observations_owner_key"),
        CheckConstraint("observed_state IN ('PENDING', 'UNKNOWN', 'CONFIRMED', 'FAILED')",
                        name="ck_removal_observations_state"),
        CheckConstraint("(matched AND denial_code IS NULL) OR (NOT matched AND denial_code IS NOT NULL)",
                        name="ck_removal_observations_denial"),
        Index("ix_removal_observations_request", "request_id", "sequence"),
    )


class RemovalStateRow(RevocationBase):
    """The derived current state for one request, separate from request and observation.

    The row is updated in the same transaction and under the same per-wallet
    lock as the observation it derives from, so a stale binding or a concurrent
    observation cannot silently confirm or restore removal.
    """

    __tablename__ = "removal_states"
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidenced_signer: Mapped[str | None] = mapped_column(Text)
    evidenced_policy: Mapped[str | None] = mapped_column(Text)
    contradictory: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_observation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("state IN ('NOT_REQUESTED', 'REQUESTED', 'PENDING', 'UNKNOWN', 'CONFIRMED', 'FAILED')",
                        name="ck_removal_states_state"),
        Index("ix_removal_states_owner_wallet", "owner_id", "agent_id", "wallet_id", "network_id"),
    )
