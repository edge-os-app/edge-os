"""The investigation job tables, apart from the worker module.

`python -m edge_os_api.research.investigation_jobs` runs that file as `__main__`, so a later import by its real name
runs it a second time. A table class there would define its table twice and raise `InvalidRequestError`. The tables live
here because no start line runs this module as `__main__`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from edge_os_api.research.history_dataset import ResearchBase


class InvestigationJobRow(ResearchBase):
    __tablename__ = "investigation_jobs"
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    intake_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    declaration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_key: Mapped[str] = mapped_column(Text, nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    deadline_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_requested_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    terminal_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Migration 0011: the tool chain. A NANSEN_REPORT job's declaration_id is its saved nansen_requests row.
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'HISTORY_INVESTIGATION'"))
    __table_args__ = (UniqueConstraint("owner_id", "declaration_id", "request_key", name="uq_investigation_job_key"),
                      UniqueConstraint("owner_id", "operation_id", name="uq_investigation_job_operation"),
                      CheckConstraint("kind IN ('HISTORY_INVESTIGATION', 'NANSEN_REPORT')", name="kind"))


class InvestigationEventRow(ResearchBase):
    """Append-only job history: lifecycle, budget and every tool attempt with its outcome and provenance."""

    __tablename__ = "investigation_events"
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("job_id", "attempt_id", "kind", name="uq_investigation_attempt_kind"),)


class InvestigationReportRow(ResearchBase):
    __tablename__ = "investigation_reports"
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    declaration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
