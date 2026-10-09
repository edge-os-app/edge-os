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


class InvestigationDeclaration(Base):
    """Append-only P08 EdgeSpec and adopted research configuration."""

    __tablename__ = "investigation_declarations"
    declaration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    intake_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    edge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    edge_version: Mapped[int] = mapped_column(nullable=False)
    parent_declaration_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_id", "declaration_id", name="uq_investigation_owner_declaration"),
        UniqueConstraint("owner_id", "intake_record_id", "declaration_id", name="uq_investigation_owner_intake_declaration"),
        UniqueConstraint("owner_id", "intake_record_id", "idempotency_key", name="uq_investigation_owner_request_key"),
        UniqueConstraint("owner_id", "operation_id", name="uq_investigation_owner_operation"),
        UniqueConstraint("owner_id", "edge_id", "edge_version", name="uq_investigation_edge_version"),
        ForeignKeyConstraint(["owner_id", "intake_record_id"], ["records.owner_id", "records.record_id"],
                             name="fk_investigation_intake"),
        ForeignKeyConstraint(["owner_id", "intake_record_id", "parent_declaration_id"],
                             ["investigation_declarations.owner_id", "investigation_declarations.intake_record_id",
                              "investigation_declarations.declaration_id"], name="fk_investigation_parent"),
        ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_investigation_owner"),
        CheckConstraint("edge_version >= 1", name="ck_investigation_edge_version"),
        CheckConstraint("length(idempotency_key) BETWEEN 1 AND 200", name="ck_investigation_idempotency_key"),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="ck_investigation_fingerprint"),
        Index("ix_investigation_owner_intake", "owner_id", "intake_record_id", "created_at"),
    )


class InvestigationAccessEvent(Base):
    """Append-only declaration-time access evidence; P08 never records outcome reads on save."""

    __tablename__ = "investigation_access_events"
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    declaration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "declaration_id"],
                             ["investigation_declarations.owner_id", "investigation_declarations.declaration_id"],
                             name="fk_investigation_access_declaration"),
        UniqueConstraint("owner_id", "event_id", name="uq_investigation_access_owner_event"),
        Index("ix_investigation_access_owner_declaration", "owner_id", "declaration_id", "sequence"),
    )


class EffectRunDeclaration(Base):
    """Immutable, explicitly adopted P09 mapping from a P08 plan to P06 rules and a fixture."""

    __tablename__ = "effect_run_declarations"
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    intake_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    p08_declaration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_id", "run_id", name="uq_effect_run_owner_run"),
        UniqueConstraint("owner_id", "intake_record_id", "run_id", name="uq_effect_run_owner_intake_run"),
        UniqueConstraint("owner_id", "intake_record_id", "idempotency_key", name="uq_effect_run_owner_request_key"),
        UniqueConstraint("owner_id", "operation_id", name="uq_effect_run_owner_operation"),
        ForeignKeyConstraint(["owner_id", "intake_record_id"], ["records.owner_id", "records.record_id"],
                             name="fk_effect_run_intake"),
        ForeignKeyConstraint(["owner_id", "intake_record_id", "p08_declaration_id"],
                             ["investigation_declarations.owner_id", "investigation_declarations.intake_record_id",
                              "investigation_declarations.declaration_id"], name="fk_effect_run_p08_declaration"),
        ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_effect_run_owner"),
        CheckConstraint("length(idempotency_key) BETWEEN 1 AND 200", name="ck_effect_run_idempotency_key"),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="ck_effect_run_fingerprint"),
        Index("ix_effect_run_owner_intake", "owner_id", "intake_record_id", "created_at"),
    )


class EffectRunEvent(Base):
    """Append-only adoption, attempt, failure, and replay evidence for P09."""

    __tablename__ = "effect_run_events"
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)
    attempt_idempotency_key: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "run_id"], ["effect_run_declarations.owner_id",
                                                         "effect_run_declarations.run_id"],
                             name="fk_effect_run_event_run"),
        ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_effect_run_event_owner"),
        UniqueConstraint("owner_id", "event_id", name="uq_effect_run_event_owner_event"),
        UniqueConstraint("owner_id", "run_id", "attempt_idempotency_key", name="uq_effect_run_event_attempt_key"),
        Index("ix_effect_run_event_owner_run", "owner_id", "run_id", "sequence"),
    )


class EffectReport(Base):
    """One immutable descriptive result, saved only after a separately adopted run."""

    __tablename__ = "effect_reports"
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "run_id"], ["effect_run_declarations.owner_id",
                                                         "effect_run_declarations.run_id"],
                             name="fk_effect_report_run"),
        ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_effect_report_owner"),
        UniqueConstraint("owner_id", "report_id", name="uq_effect_report_owner_report"),
        UniqueConstraint("owner_id", "run_id", name="uq_effect_report_owner_run"),
        Index("ix_effect_report_owner_created", "owner_id", "created_at"),
    )


class SpotReplayRun(Base):
    """One immutable owner-scoped P13 replay, including its exact inputs and result."""

    __tablename__ = "spot_replay_runs"
    replay_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "strategy_id", "strategy_revision_id"],
                             ["strategy_revisions.owner_id", "strategy_revisions.strategy_id",
                              "strategy_revisions.revision_id"], name="fk_spot_replay_strategy_revision"),
        ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_spot_replay_owner"),
        UniqueConstraint("owner_id", "replay_id", name="uq_spot_replay_owner_id"),
        UniqueConstraint("owner_id", "method", "path", "idempotency_key", name="uq_spot_replay_idempotency"),
        CheckConstraint("length(idempotency_key) BETWEEN 1 AND 200", name="ck_spot_replay_idempotency_key"),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$' AND content_sha256 ~ '^[0-9a-f]{64}$'",
                        name="ck_spot_replay_hashes"),
        Index("ix_spot_replay_owner_created", "owner_id", "created_at"),
    )
