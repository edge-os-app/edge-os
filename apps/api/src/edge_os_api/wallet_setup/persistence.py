"""`wallet_setup_local` schema and row helpers.

The tables live in their own metadata, separate from `records.Base`, and migration 0007 creates
them through the normal additive path. This package registers no shared model. `owner_id` follows
the verified principal `users.id` by application convention; it carries no foreign key so the
schema stays self-contained.

Appendix A (P15) says the envelope is `{schema_version, record_type, record_id, owner_id,
operation_id, created_at, content}`. This local table is metadata for one setup identity, not a
P02 `records` row, so it stores the same provisional fields as typed columns.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, Identity, Index, Integer, MetaData, Text,
                        UniqueConstraint, select, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from edge_os_api.wallet_setup.types import CancellationIntent, SetupEventType, SetupRecord, SetupState

WALLET_SETUP_METADATA = MetaData()


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class WalletSetupBase(DeclarativeBase):
    metadata = WALLET_SETUP_METADATA


class WalletSetupRow(WalletSetupBase):
    """The single current row per `(owner_id, agent_id)`. One wallet binding per agent."""

    __tablename__ = "wallet_setups"
    setup_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    cancellation_intent: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NONE'"))
    creation_dispatched: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    request_key: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_id", "agent_id", name="uq_wallet_setup_owner_agent"),
        UniqueConstraint("owner_id", "wallet_id", name="uq_wallet_setup_owner_wallet"),
        CheckConstraint("network_id IN (143, 10143)", name="ck_wallet_setup_network"),
        CheckConstraint("state IN ('REQUESTED', 'PENDING', 'UNKNOWN', 'CONFIRMED', 'FAILED')",
                        name="ck_wallet_setup_state"),
        CheckConstraint("cancellation_intent IN ('NONE', 'REQUESTED_BEFORE_DISPATCH', 'REQUESTED_AFTER_DISPATCH')",
                        name="ck_wallet_setup_cancellation_intent"),
        CheckConstraint("length(agent_id) BETWEEN 1 AND 64", name="ck_wallet_setup_agent_id"),
        CheckConstraint("length(request_key) BETWEEN 1 AND 200", name="ck_wallet_setup_request_key"),
        Index("ix_wallet_setup_owner_state", "owner_id", "state"),
    )


class WalletSetupEventRow(WalletSetupBase):
    """Append-only setup evidence, written before the fixture boundary where it matters."""

    __tablename__ = "wallet_setup_events"
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    setup_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_wallet_setup_event_setup", "setup_id", "sequence"),
    )


class WalletSetupDenialRow(WalletSetupBase):
    """Denials recorded separately from protected setup state."""

    __tablename__ = "wallet_setup_denials"
    denial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_wallet_setup_denial_owner", "owner_id", "created_at"),
    )


def load_setup(session: Any, owner_id: uuid.UUID, agent_id: str, *, lock: bool) -> WalletSetupRow | None:
    stmt = select(WalletSetupRow).where(WalletSetupRow.owner_id == owner_id, WalletSetupRow.agent_id == agent_id)
    if lock:
        stmt = stmt.execution_options(populate_existing=True).with_for_update(of=WalletSetupRow)
    return session.execute(stmt).scalar_one_or_none()


def conflicting_binding(session: Any, owner_id: uuid.UUID, agent_id: str, wallet_id: str) -> WalletSetupRow | None:
    """Another agent of the same owner that already holds this wallet ID, if any."""
    return session.execute(select(WalletSetupRow).where(
        WalletSetupRow.owner_id == owner_id, WalletSetupRow.wallet_id == wallet_id,
        WalletSetupRow.agent_id != agent_id)).scalar_one_or_none()


def insert_event(session: Any, row: WalletSetupRow, event_type: SetupEventType,
                 content: dict[str, Any]) -> WalletSetupEventRow:
    event = WalletSetupEventRow(event_id=uuid.uuid4(), setup_id=row.setup_id, owner_id=row.owner_id,
                                event_type=event_type.value, content=content, created_at=utcnow())
    session.add(event)
    session.flush()
    return event


def latest_event(session: Any, row: WalletSetupRow, event_type: SetupEventType) -> dict[str, Any] | None:
    stmt = (select(WalletSetupEventRow.content)
            .where(WalletSetupEventRow.setup_id == row.setup_id, WalletSetupEventRow.event_type == event_type.value)
            .order_by(WalletSetupEventRow.sequence.desc()).limit(1))
    return session.execute(stmt).scalar_one_or_none()


def record_denial(session: Any, owner_id: uuid.UUID, agent_id: str | None, code: str,
                  content: dict[str, Any]) -> None:
    """Record a denial for the requesting (verified) owner. It never references another owner's row."""
    session.add(WalletSetupDenialRow(denial_id=uuid.uuid4(), owner_id=owner_id, agent_id=agent_id, code=code,
                                     content=content, created_at=utcnow()))
    session.flush()


def mark_unknown(session: Any, row: WalletSetupRow, reason: str) -> SetupRecord:
    row.state = SetupState.UNKNOWN.value
    row.reason = reason
    row.updated_at = utcnow()
    insert_event(session, row, SetupEventType.RESULT_UNKNOWN, {"reason": reason})
    session.commit()
    return to_record(row)


def bind_wallet(session: Any, row: WalletSetupRow, wallet_id: str, evidence: dict[str, Any],
                event_type: SetupEventType) -> SetupRecord:
    row.wallet_id = wallet_id
    row.state = SetupState.CONFIRMED.value
    row.reason = None
    row.updated_at = utcnow()
    insert_event(session, row, event_type, {"wallet_id": wallet_id, "evidence": evidence})
    session.commit()
    return to_record(row)


def to_record(row: WalletSetupRow) -> SetupRecord:
    return SetupRecord(setup_id=row.setup_id, owner_id=row.owner_id, agent_id=row.agent_id,
                       network_id=row.network_id, strategy_id=row.strategy_id,
                       strategy_revision_id=row.strategy_revision_id, content_sha256=row.content_sha256,
                       manifest_sha256=row.manifest_sha256, state=SetupState(row.state),
                       cancellation_intent=CancellationIntent(row.cancellation_intent),
                       creation_dispatched=row.creation_dispatched, request_key=row.request_key,
                       wallet_id=row.wallet_id, reason=row.reason, created_at=row.created_at,
                       updated_at=row.updated_at)
