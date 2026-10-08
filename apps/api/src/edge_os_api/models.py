"""Schema. Migrations in `migrations/` must agree with these definitions (`alembic check`)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Index,
                        Text, UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NOW = text("now()")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    privy_did: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)


class Record(Base):
    """P02 persisted envelope. Rows are append-only (a trigger rejects UPDATE and DELETE)."""

    __tablename__ = "records"
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    record_type: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    intake_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    predecessor_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    interpretation_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)

    __table_args__ = (
        UniqueConstraint("owner_id", "record_id", name="uq_records_owner_record"),
        ForeignKeyConstraint(["owner_id", "intake_record_id"], ["records.owner_id", "records.record_id"],
                             name="fk_records_intake"),
        ForeignKeyConstraint(["owner_id", "predecessor_record_id"], ["records.owner_id", "records.record_id"],
                             name="fk_records_predecessor"),
        ForeignKeyConstraint(["owner_id", "interpretation_record_id"], ["records.owner_id", "records.record_id"],
                             name="fk_records_interpretation"),
        Index("ix_records_owner_type_seq", "owner_id", "record_type", "seq"),
        Index("ix_records_owner_intake", "owner_id", "intake_record_id"),
        Index("uq_records_interpretation_successor", "owner_id", "predecessor_record_id", unique=True,
              postgresql_where=text("record_type = 'PromptInterpretation' AND predecessor_record_id IS NOT NULL")),
    )


class StrategyRevision(Base):
    """Immutable published revision. `strategy_canonical` holds the exact hashed bytes as text."""

    __tablename__ = "strategy_revisions"
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    draft_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_canonical: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_id", "strategy_id", "revision_id", name="uq_revision_owner_strategy"),
        UniqueConstraint("owner_id", "operation_id", name="uq_revision_owner_operation"),
        ForeignKeyConstraint(["owner_id", "strategy_id", "parent_revision_id"],
                             ["strategy_revisions.owner_id", "strategy_revisions.strategy_id",
                              "strategy_revisions.revision_id"], name="fk_revision_parent"),
        ForeignKeyConstraint(["owner_id", "draft_record_id"], ["records.owner_id", "records.record_id"],
                             name="fk_revision_draft"),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$' AND manifest_sha256 ~ '^[0-9a-f]{64}$'",
                        name="ck_revision_hashes"),
        Index("uq_revision_root_slot", "owner_id", "strategy_id", unique=True,
              postgresql_where=text("parent_revision_id IS NULL")),
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    method: Mapped[str] = mapped_column(Text, primary_key=True)
    path: Mapped[str] = mapped_column(Text, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(Text, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        CheckConstraint("length(idempotency_key) BETWEEN 1 AND 200", name="ck_idempotency_key_length"),
    )
