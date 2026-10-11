"""Owned inactive-consent tables.

These tables belong to the local inactive-consent preparation stage. They are
created by the owned package metadata inside a run-labelled test database and are
never published through a shared migration in this stage. The shared `public`
application schema is unchanged. The consent tables are read-only relative to
every accepted module: they never write holdings, allowances, reservations,
claims, recovery cases, funding flows or stop history.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, MetaData, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONSENT_SCHEMA = "consent_local"
STATUS_INACTIVE = "'INACTIVE'"

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "pk": "%(table_name)s_pkey",
}

NOW = text("now()")


class ConsentBase(DeclarativeBase):
    # Owned tables live in their own schema so the migrated `public` application
    # schema stays exactly as released.
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=CONSENT_SCHEMA)


class ConsentReviewRow(ConsentBase):
    """One immutable grouped review of one exact revision, wallet and term set."""

    __tablename__ = "consent_reviews"
    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    terms_version: Mapped[str] = mapped_column(Text, nullable=False)
    terms_hash: Mapped[str] = mapped_column(Text, nullable=False)
    review_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "review_id", name="uq_consent_reviews_owner_review"),
        UniqueConstraint("owner_id", "agent_id", "strategy_revision_id", name="uq_consent_reviews_identity"),
        CheckConstraint(f"status = {STATUS_INACTIVE}", name="ck_consent_reviews_status"),
        Index("ix_consent_reviews_owner_agent", "owner_id", "agent_id"),
    )


class ConsentAdoptionRow(ConsentBase):
    """One durable owner adoption of one reviewed meaning, always INACTIVE."""

    __tablename__ = "consent_adoptions"
    adoption_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_hash: Mapped[str] = mapped_column(Text, nullable=False)
    consent_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        UniqueConstraint("owner_id", "review_id", name="uq_consent_adoptions_owner_review"),
        CheckConstraint(f"status = {STATUS_INACTIVE}", name="ck_consent_adoptions_status"),
        Index("ix_consent_adoptions_owner_review", "owner_id", "review_id"),
    )


class ConsentDenialRow(ConsentBase):
    """Append-only fail-closed denial. A denial never writes an affirmative consent."""

    __tablename__ = "consent_denials"
    denial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(Text)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=NOW)

    __table_args__ = (
        CheckConstraint("operation IN ('REVIEW','ADOPT','READ')", name="ck_consent_denials_operation"),
        Index("ix_consent_denials_owner_operation", "owner_id", "operation", "created_at"),
    )
