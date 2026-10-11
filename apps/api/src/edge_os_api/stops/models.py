"""Owned P25 durable scoped-stop tables.

These tables belong to the local scoped-stop stage. They are created by the owned
package metadata inside a run-labelled test database and are never published
through a shared migration in this stage. The `stops_local` schema stays separate
from the P22 `admission_local`, P23 `execution_local` and P24 `recovery_local`
schemas and from the migrated `public` schema.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    MetaData,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "pk": "%(table_name)s_pkey",
}

NOW = text("now()")

STOP_SCOPES = ("POSITION", "AGENT_WALLET_NETWORK")
STOP_MODES = ("STOP_NEW_ENTRIES", "HALT_ALL_SWAPS")
STOP_TRIGGERS = ("USER", "TRIAL", "POSITION_LOSS", "WALLET_LOSS")


class StopBase(DeclarativeBase):
    # Owned tables live in their own schema, created by the owned test fixture
    # inside the run-labelled test database only.
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="stops_local")


class StopRow(StopBase):
    """One durable scoped stop per owner, wallet, scope, target and mode.

    The uniqueness key makes an identical repeated request idempotent: the same
    durable stop is returned once and a second row is not created. Different
    modes, scopes or targets accumulate, so the table is the durable stop history.
    Records are never cleared; this stage assigns no stop-clear or resume action.
    """

    __tablename__ = "scoped_stops"
    stop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    position_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "agent_id", "wallet_id", "network_id", "scope", "position_id", "mode",
                         name="uq_scoped_stops_identity"),
        CheckConstraint("scope IN ('POSITION','AGENT_WALLET_NETWORK')", name="ck_scoped_stops_scope"),
        CheckConstraint("mode IN ('STOP_NEW_ENTRIES','HALT_ALL_SWAPS')", name="ck_scoped_stops_mode"),
        CheckConstraint("trigger IN ('USER','TRIAL','POSITION_LOSS','WALLET_LOSS')", name="ck_scoped_stops_trigger"),
        Index("ix_scoped_stops_owner_wallet", "owner_id", "agent_id", "wallet_id", "network_id"),
    )
