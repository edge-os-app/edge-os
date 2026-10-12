"""Saved Nansen report requests and reports for the original investigation jobs (#58 RESEARCH-PORTS-LOCAL).

A Nansen report job is an `investigation_jobs` row with `kind = NANSEN_REPORT`. Its `declaration_id` is the saved
`nansen_requests` row: the exact question (the owner's request text), token, window, operations, queries and local
caps. The worker runs the accepted `nansen_research.run_research` once over the application-composed transport and
saves one immutable `nansen_reports` row with the frozen request, evidence and report packages and their hashes.
Reopening reads that row; it never calls a transport or charges again.

This module computes facts from the saved packages only. It holds no provider, credential or financial path.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Text, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import not_found
from edge_os_api.core.request_schemas import NansenReportBody
from edge_os_api.core.research.provider_composition import NANSEN_EVIDENCE_CLASS, NANSEN_TRANSPORT_LABEL
from edge_os_api.nansen_research import (
    FlowQuery,
    HolderQuery,
    NansenEvidence,
    NansenLimits,
    NansenReport,
    NansenRequest,
    NansenRun,
    ObservationWindow,
)
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research.history_dataset import ResearchBase
from edge_os_api.research.service import parse_uuid

HISTORY_KIND = "HISTORY_INVESTIGATION"
NANSEN_KIND = "NANSEN_REPORT"
TOOL = "run_nansen_research"
REQUEST_RECORD_VERSION = "edge-os.nansen-request/1"
REPORT_RECORD_VERSION = "edge-os.nansen-report-record/1"
# A refusal raised by the application's guard before the request left: never a made provider call.
REFUSED_BEFORE_SEND = frozenset({"CANCELLED", "DEADLINE"})
NOTICE = ("Authored Nansen-shaped responses replayed locally. Not provider data, not a market fact and not "
          "bounty evidence. Address counts are returned records; amounts keep their raw text and unresolved units.")


class NansenRequestRow(ResearchBase):
    __tablename__ = "nansen_requests"
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    intake_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("owner_id", "intake_record_id", "request_key", name="uq_nansen_request_key"),
                      CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="hash"))


class NansenReportRow(ResearchBase):
    __tablename__ = "nansen_reports"
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="hash"),)


def build_request(body: NansenReportBody, question: str, deadline_utc: str) -> NansenRequest:
    """The exact `nansen-research-request/1` for one job. Raises the package's `NansenRequestError`/`NansenLimitError`
    for a request it refuses; nothing is reserved or sent before that check."""
    try:
        credits = Decimal(body.limits.max_credits)
    except InvalidOperation:  # the schema pattern already refuses this; kept for a direct caller
        credits = Decimal("NaN")
    request = NansenRequest(
        question=question, token_address=body.token_address, token_symbol=body.token_symbol,
        window=ObservationWindow(start_utc=body.window.start_utc, end_utc=body.window.end_utc),
        operations=tuple(body.operations),
        limits=NansenLimits(max_requests=body.limits.max_requests, max_pages=body.limits.max_pages,
                            max_bytes=body.limits.max_bytes, max_credits=credits, per_page=body.limits.per_page,
                            deadline_utc=deadline_utc),
        holder_query=HolderQuery(label_type=body.holder_query.label_type,
                                 aggregate_by_entity=body.holder_query.aggregate_by_entity,
                                 order_field=body.holder_query.order_field,
                                 value_usd_min=body.holder_query.value_usd_min),
        flow_query=FlowQuery(label=body.flow_query.label))
    request.validate()
    return request


def reservation(body: NansenReportBody) -> dict[str, int]:
    """Reserved before any effect: the request cap, the declared compute and the credit cap rounded up."""
    return {"provider_requests": body.limits.max_requests, "compute_seconds": body.compute_seconds,
            "nansen_credits": math.ceil(Decimal(body.limits.max_credits))}


def request_content(owner_id: uuid.UUID, intake_record_id: uuid.UUID, request_key: str,
                    request: NansenRequest) -> dict[str, Any]:
    return {"schema_version": REQUEST_RECORD_VERSION, "owner_id": str(owner_id),
            "intake_record_id": str(intake_record_id), "request_key": request_key,
            "request": request.to_dict(), "request_sha256": request.sha256()}


def saved_request(row: NansenRequestRow) -> NansenRequest:
    return NansenRequest.from_dict(row.content["request"])


def _credit(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def settlement(evidence: NansenEvidence) -> dict[str, Any]:
    """Provider-request and credit settlement from the saved evidence only.

    A record with a received status is a made call. A record refused by the application's own guard before sending
    is not. Any other record without a status is a lost reply: the request count becomes UNKNOWN. Credits are KNOWN
    only when every made call reported a valid deducted charge and nothing was lost; otherwise the whole credit
    reservation stays unknown liability. Neither is ever zero by default.
    """
    made = [record for record in evidence.sources if record.status is not None]
    lost = [record for record in evidence.sources
            if record.status is None and record.failure not in REFUSED_BEFORE_SEND]
    deducted = [_credit(record.deducted_credits) for record in made]
    requests_known = not lost
    credits_known = requests_known and all(amount is not None for amount in deducted)
    total = sum((amount for amount in deducted if amount is not None), Decimal(0))
    return {"provider_requests": {"state": "KNOWN" if requests_known else "UNKNOWN", "measured": len(made),
                                  "lost": len(lost)},
            "nansen_credits": {"state": "KNOWN" if credits_known else "UNKNOWN",
                               "measured": math.ceil(total) if credits_known else 0,
                               "deducted": str(total) if credits_known else None,
                               "reserved_by_package": evidence.reserved_credits}}


def report_content(*, report_id: uuid.UUID, owner_id: uuid.UUID, job_id: uuid.UUID, request_row: NansenRequestRow,
                   run: NansenRun, response_sha256: list[str], settled: dict[str, Any]) -> dict[str, Any]:
    request = saved_request(request_row)
    return {"schema_version": REPORT_RECORD_VERSION, "report_id": str(report_id), "owner_id": str(owner_id),
            "job_id": str(job_id), "request_id": str(request_row.request_id),
            "intake_record_id": request_row.content["intake_record_id"], "evidence_class": NANSEN_EVIDENCE_CLASS,
            "transport_label": NANSEN_TRANSPORT_LABEL, "notice": NOTICE,
            "request": request.to_dict(), "evidence": run.evidence.to_dict(), "report": run.report.to_dict(),
            "request_sha256": request.sha256(), "evidence_sha256": run.evidence.sha256(),
            "report_sha256": run.report.sha256(), "transport_response_sha256": list(response_sha256),
            "outcomes": [{"operation": outcome.operation, "status": outcome.status,
                          "stop_reason": outcome.stop_reason} for outcome in run.outcomes],
            "settlement": settled}


def report_view(row: NansenReportRow) -> dict[str, Any]:
    """The saved report as an owner reads it. The hashes are recomputed from the saved packages."""
    content = row.content
    evidence = NansenEvidence.from_dict(content["evidence"])
    report = NansenReport.from_dict(content["report"])
    request = NansenRequest.from_dict(content["request"])
    return {"report_id": str(row.report_id), "job_id": str(row.job_id), "content_sha256": row.content_sha256,
            "hashes_verified": {"content_sha256": record_contract.sha256_hex(content) == row.content_sha256,
                                "request_sha256": request.sha256() == content["request_sha256"],
                                "evidence_sha256": evidence.sha256() == content["evidence_sha256"],
                                "report_sha256": report.sha256() == content["report_sha256"],
                                "report_binds_request": report.request_sha256 == content["request_sha256"]},
            "created_at": record_contract.utc_string(row.created_at), "content": content}


def owned_report(session: Session, principal: Principal, report_id: str) -> NansenReportRow:
    parsed = parse_uuid(report_id)
    row = None if parsed is None else session.execute(select(NansenReportRow).where(
        NansenReportRow.owner_id == principal.user_id, NansenReportRow.report_id == parsed)).scalar_one_or_none()
    if row is None:
        raise not_found("nansen report")
    return row
