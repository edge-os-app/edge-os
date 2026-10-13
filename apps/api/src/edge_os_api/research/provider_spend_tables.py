"""Tables of the shared provider spend ledger (migration 0013), registered with Alembic so `alembic check` agrees.

`PostgresSpendLedger` writes them. Each reservation names a saved interpretation attempt: the ledger copies its owner and
saved request from that append-only row inside the reserving transaction.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, DateTime, Identity, Index, MetaData, PrimaryKeyConstraint, SmallInteger, Table,
    Text, Uuid,
)

__all__ = ["SPEND_METADATA"]

SPEND_METADATA = MetaData(schema="usage_local")

Table(
    "provider_spend_settings", SPEND_METADATA,
    Column("settings_id", SmallInteger, nullable=False),
    Column("global_cap_nano_usd", BigInteger, nullable=False),
    Column("owner_cap_nano_usd", BigInteger, nullable=False),
    Column("prompt_usd_per_million", Text, nullable=False),
    Column("completion_usd_per_million", Text, nullable=False),
    Column("cap_source", Text, nullable=False),
    Column("frozen_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("settings_id = 1", name="provider_spend_settings_single_check"),
    CheckConstraint("global_cap_nano_usd >= 0 AND owner_cap_nano_usd >= 0", name="provider_spend_settings_caps_check"),
    PrimaryKeyConstraint("settings_id", name="provider_spend_settings_pkey"),
)

Table(
    "provider_spend_reservations", SPEND_METADATA,
    Column("attempt_id", Uuid, nullable=False),
    Column("owner_id", Uuid, nullable=False),
    Column("intake_record_id", Uuid, nullable=False),
    Column("scope", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("reserved_nano_usd", BigInteger, nullable=False),
    Column("charged_nano_usd", BigInteger, nullable=True),
    Column("max_input_tokens", BigInteger, nullable=False),
    Column("max_output_tokens", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("state IN ('RESERVED', 'UNKNOWN', 'SETTLED', 'RELEASED')", name="provider_spend_reservations_state_check"),
    CheckConstraint("reserved_nano_usd >= 0 AND (charged_nano_usd IS NULL OR charged_nano_usd >= 0)",
                    name="provider_spend_reservations_amounts_check"),
    CheckConstraint("(state = 'SETTLED') = (charged_nano_usd IS NOT NULL)", name="provider_spend_reservations_charge_check"),
    PrimaryKeyConstraint("attempt_id", name="provider_spend_reservations_pkey"),
    Index("ix_provider_spend_owner_state", "owner_id", "state"),
    Index("ix_provider_spend_scope_state", "scope", "state"),
)

Table(
    "provider_spend_events", SPEND_METADATA,
    Column("seq", BigInteger, Identity(always=False), nullable=False),
    Column("attempt_id", Uuid, nullable=True),
    Column("kind", Text, nullable=False),
    Column("detail", Text, nullable=False),
    Column("nano_usd", BigInteger, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("seq", name="provider_spend_events_pkey"),
    Index("ix_provider_spend_events_attempt", "attempt_id", "seq"),
)
