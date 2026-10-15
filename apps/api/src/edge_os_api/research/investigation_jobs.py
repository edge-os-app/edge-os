"""Owner-scoped original investigation jobs (`edge-os.investigation-job/1`).

One job per owner, v3 declaration and request key. Starting a job reserves its declared provider and compute bounds
against the owner's research budget before any adapter effect. A bounded worker then runs the declared tools in order:
collect the recorded source, save the dataset, compare with the adopted rules, save the report. Every step appends an
immutable event. A worker that stops during collection never collects again: the original attempt becomes
OUTCOME_UNKNOWN and keeps its whole reservation as unknown liability. Missing or malformed provider usage is unknown,
never zero. This module holds no financial authority and imports no wallet, consent, admission or execution path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import math
import time
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding, not_found
from edge_os_api.core.request_schemas import InvestigationJobBody, NansenReportBody
from edge_os_api.core.settings import Settings
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.core.research import provider_composition, released_runtime_bootstrap, released_source_runtime
from edge_os_api.core.research.operating_release import ReleaseRefused
from edge_os_api.nansen_research import NansenLimitError, NansenRequestError, run_research
from edge_os_api.research import history_dataset, history_payload_binding, investigation_tools, nansen_reports
from edge_os_api.research.history_dataset import HistoryDatasetRow, ResearchBase
from edge_os_api.research.investigation_adoption import owned_history_declaration
from edge_os_api.research.service import get_owned, parse_uuid
from edge_os_api.usage import quota

log = logging.getLogger(__name__)

JOB_VERSION = "edge-os.investigation-job/1"
REPORT_VERSION = "edge-os.investigation-report/1"
RUNNABLE = ("RESERVED", "COLLECTING", "EVALUATING")
TERMINAL = ("REPORTED", "CANCELLED", "DEADLINE_EXCEEDED", "BUDGET_EXHAUSTED", "UNAVAILABLE", "FAILED")
STATES = ("QUEUED", *RUNNABLE, *TERMINAL)


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


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime | None) -> str | None:
    return None if moment is None else record_contract.utc_string(moment)


def _refusal(status: int, code: str, path: str, detail: str) -> AppError:
    kind = {409: "UNAVAILABLE", 422: "INVALID_INPUT"}.get(status, "CONFLICTED")
    return AppError(status, "INVESTIGATION_JOB", kind, code, [finding(code, path, detail)])


def _event(session: Session, job: InvestigationJobRow, kind: str, content: dict[str, Any],
           attempt_id: uuid.UUID | None = None) -> None:
    session.add(InvestigationEventRow(event_id=uuid.uuid4(), owner_id=job.owner_id, job_id=job.job_id, kind=kind,
                                      attempt_id=attempt_id, content=content, created_at=utcnow()))


def _events(session: Session, job_id: uuid.UUID) -> list[InvestigationEventRow]:
    return list(session.execute(select(InvestigationEventRow).where(InvestigationEventRow.job_id == job_id)
                                .order_by(InvestigationEventRow.seq)).scalars())


# ------------------------------------------------------------------------------------------------- budget

QUOTA_SUBJECT = "investigation_job"


def caps(settings: Settings, *, nansen: bool = True) -> quota.Caps:
    """Owner and global research caps from configuration. Stored caps are frozen; see `usage.quota`.

    A history job reserves and settles only requests and compute (`nansen=False`), so it never creates or locks
    Nansen credit rows. Reads (budget view, readiness) use every resource."""
    owner = {"provider_requests": settings.research_budget_provider_requests,
             "compute_seconds": settings.research_budget_compute_seconds}
    global_ = {"provider_requests": settings.usage_global_provider_requests,
               "compute_seconds": settings.usage_global_compute_seconds}
    if nansen:
        owner["nansen_credits"] = settings.research_budget_nansen_credits
        global_["nansen_credits"] = settings.usage_global_nansen_credits
    return quota.Caps(owner=owner, global_=global_)


def _job_caps(settings: Settings, job: InvestigationJobRow) -> quota.Caps:
    return caps(settings, nansen=job.kind == nansen_reports.NANSEN_KIND)


def _cap_mismatch(error: quota.CapMismatch) -> AppError:
    return AppError(503, "INVESTIGATION_JOB", "UNAVAILABLE", "quota_cap_mismatch", [finding(
        "quota_cap_mismatch", "/", "Research capacity is paused: a configured cap differs from the recorded cap. "
        "Nothing was reserved.")])


def get_budget(session: Session, principal: Principal, settings: Settings) -> dict[str, Any]:
    return quota.view(session, principal.user_id, caps(settings))


def _settle(session: Session, job: InvestigationJobRow, settings: Settings, *, provider: str, compute: str,
            provider_consumed: int = 0, compute_consumed: int = 0, credits: str = "SKIP",
            credits_consumed: int = 0) -> None:
    """Move a job's open reservation to consumed, unknown or released. Each kind: KNOWN, UNKNOWN or SKIP (stay open).
    `credits` applies only to a job that reserved Nansen credits."""
    budget = dict(job.budget)

    def open_amount(resource: str, kind: str) -> int:
        if kind == "SKIP" or resource not in budget["reserved"]:
            return 0
        return budget["reserved"][resource] - budget["settled"].get(resource, 0)

    plan = [("provider_requests", provider, provider_consumed), ("compute_seconds", compute, compute_consumed),
            ("nansen_credits", credits, credits_consumed)]
    plan = [(resource, kind, measured, open_amount(resource, kind)) for resource, kind, measured in plan]
    if all(amount <= 0 for *_, amount in plan):
        return
    reservation = quota.existing(session, QUOTA_SUBJECT, str(job.job_id))
    if reservation is None:  # an original reservation must exist for every reserved job
        raise RuntimeError(f"investigation job {job.job_id} has no usage reservation")
    totals = {key: dict(value) for key, value in budget.items() if isinstance(value, dict)}
    for resource, kind, measured, open_amount_ in plan:
        if open_amount_ <= 0:
            continue
        # The shared ledger books the job's whole reservation for this resource once; a repeat books nothing.
        booked = quota.settle(session, reservation, resource, kind, measured, _job_caps(settings, job))
        if booked is not None:
            totals["consumed"][resource] += booked["consumed"]
            totals["unknown_liability"][resource] += booked["unknown"]
            totals["released"][resource] += booked["released"]
            totals["overrun"][resource] += booked["overrun"]
        totals["settled"][resource] += open_amount_
    job.budget = {**budget, **totals}
    _event(session, job, "BUDGET_SETTLED", {"budget": job.budget, "provider": provider, "compute": compute,
                                            **({} if credits == "SKIP" else {"credits": credits})})


# ------------------------------------------------------------------------------------------------- HTTP

def _job_fingerprint(principal: Principal, declaration_id: uuid.UUID, body: InvestigationJobBody) -> str:
    return record_contract.sha256_hex({"owner_id": str(principal.user_id), "declaration_id": str(declaration_id),
                                       "body": body.model_dump(mode="json")})


def _existing_job(session: Session, owner_id: uuid.UUID, declaration_id: uuid.UUID,
                  key: str) -> InvestigationJobRow | None:
    return session.execute(select(InvestigationJobRow).where(
        InvestigationJobRow.owner_id == owner_id, InvestigationJobRow.declaration_id == declaration_id,
        InvestigationJobRow.request_key == key)).scalar_one_or_none()


def _replay(session: Session, row: InvestigationJobRow, fingerprint: str) -> tuple[int, dict[str, Any]]:
    if row.fingerprint != fingerprint:
        raise _refusal(409, "request_key_reused", "/request_key", "This request key belongs to another job start.")
    if row.state == "BUDGET_EXHAUSTED":
        raise _budget_refusal(row)
    return 200, job_view(session, row)


def _budget_refusal(row: InvestigationJobRow) -> AppError:
    return AppError(409, "INVESTIGATION_JOB", "UNAVAILABLE", "research_budget_exhausted", [finding(
        "research_budget_exhausted", "/resource_bounds",
        f"Your research budget cannot reserve this job's declared bounds. Job {row.job_id} is saved as refused; "
        "nothing was collected.")])


def release_refusal(runtime: Any, frozen_sha256: str, part: str = "history") -> tuple[str, str] | None:
    """Admission of a saved release job: this process must compose the exact release the job froze. Checked before
    any reservation (start) and before any credential read or request (worker)."""
    if runtime is None or getattr(runtime.release, part) is None:
        return ("operating_release_unavailable",
                "This server does not compose the operating release this job names. Nothing was started or sent.")
    if runtime.release_sha256 != frozen_sha256:
        return ("operating_release_changed",
                "The operating release changed after this was saved. Declare again on the current release. "
                "Nothing was started or sent.")
    return None


def release_http_clients(prepared: Any, deadline_at: dt.datetime, wall_clock: Callable[[], dt.datetime],
                         clock: Callable[[], float] = time.monotonic) -> Callable[..., Any]:
    """The worker's client factory for a release job. The time left is read from the job's SAVED deadline at the moment
    the clients are built, next to the monotonic anchor, so a delay before construction never extends the bound
    (review B R2-N2, controller dw-l2-clock3.md)."""
    def build(_source: Any, _bounds: Any, cancelled: Callable[[], bool]) -> Any:
        anchor = clock()  # read before the wall clock, so the anchored deadline can only be earlier, never later
        return prepared.clients((deadline_at - wall_clock()).total_seconds(), cancelled, clock=clock, anchor=anchor)
    return build


def release_nansen_transport(prepared: Any, deadline_at: dt.datetime, wall_clock: Callable[[], dt.datetime],
                             cancelled: Callable[[], bool], clock: Callable[[], float] = time.monotonic) -> Any:
    """The worker's Nansen transport for a release job, built before the original attempt is saved. Its one deadline is
    anchored to the job's SAVED deadline the same way as `release_http_clients`: the monotonic anchor is read first, so
    the mapped deadline can only be earlier, never later (contract section 12.3)."""
    anchor = clock()
    return prepared.transport((deadline_at - wall_clock()).total_seconds(), cancelled, clock=clock, anchor=anchor)


def _release_record(runtime: Any) -> dict[str, Any]:
    return {"release_id": runtime.release.release_id, "sha256": runtime.release_sha256, "kind": runtime.release.kind}


def start_job(session: Session, principal: Principal, settings: Settings, intake_id: str, declaration_id: str,
              body: InvestigationJobBody, runtime: Any = None) -> tuple[int, dict[str, Any]]:
    """Save one original job and reserve its bounds before any effect. The same key returns the original job.

    A declaration on an operating-release source needs that exact release composed here; recorded sources need the
    recorded history mode."""
    declaration = owned_history_declaration(session, principal, intake_id, declaration_id)
    frozen_release = declaration.content["frozen"].get("operating_release_sha256")
    if frozen_release is None and settings.research_history_mode != "recorded":
        raise _refusal(409, "history_source_unavailable", "/",
                       "History collection is unavailable in this configuration. Nothing was started.")
    fingerprint = _job_fingerprint(principal, declaration.declaration_id, body)
    existing = _existing_job(session, principal.user_id, declaration.declaration_id, body.request_key)
    if existing is not None:
        return _replay(session, existing, fingerprint)
    release_refused = None if frozen_release is None else release_refusal(runtime, frozen_release)
    if release_refused is not None:
        raise _refusal(409, release_refused[0], "/", release_refused[1])
    if (declaration.content["configuration"]["source"]["evidence_class"] == history_dataset.HTTP_CLASS
            and settings.research_source_clients != "authored_http"):
        raise _refusal(409, "history_source_unavailable", "/",
                       "This server does not compose the HTTP source clients. Nothing was started.")
    bounds = declaration.content["configuration"]["resource_bounds"]
    requested = {"provider_requests": bounds["provider_requests"], "compute_seconds": bounds["compute_seconds"]}
    now = utcnow()
    job_id = uuid.uuid4()
    try:
        outcome = quota.reserve(session, principal.user_id, QUOTA_SUBJECT, str(job_id), requested,
                                caps(settings, nansen=False))
    except quota.CapMismatch as error:
        session.rollback()
        raise _cap_mismatch(error) from None
    existing = _existing_job(session, principal.user_id, declaration.declaration_id, body.request_key)
    if existing is not None:  # a concurrent start with this key won; the locks above serialized us behind it
        session.rollback()
        return _replay(session, existing, fingerprint)
    # Counted under the owner's quota row locks, so concurrent starts of one owner cannot both pass the limit.
    active = session.execute(select(func.count()).select_from(InvestigationJobRow).where(
        InvestigationJobRow.owner_id == principal.user_id,
        InvestigationJobRow.state.in_(("QUEUED", *RUNNABLE)))).scalar_one()
    if active >= settings.research_max_active_jobs:
        session.rollback()
        raise _refusal(409, "too_many_active_jobs", "/",
                       f"You already have {active} research jobs waiting or running. Cancel one or wait for one to "
                       "finish. Nothing was started.")
    granted = isinstance(outcome, quota.Grant)
    zero = {"provider_requests": 0, "compute_seconds": 0}
    refused = None if granted else {"scope": outcome.scope, "resource": outcome.resource,
                                    "requested": outcome.requested, "available": outcome.available}
    job = InvestigationJobRow(
        job_id=job_id, owner_id=principal.user_id, intake_record_id=declaration.intake_record_id,
        declaration_id=declaration.declaration_id, request_key=body.request_key,
        operation_id=uuid.UUID(body.operation_id), fingerprint=fingerprint, state="QUEUED",
        budget={"requested": requested, "reserved": dict(requested) if granted else dict(zero),
                "settled": dict(zero), "consumed": dict(zero), "unknown_liability": dict(zero),
                "released": dict(zero), "overrun": dict(zero)},
        deadline_at=now + dt.timedelta(seconds=bounds["deadline_seconds"]), created_at=now, updated_at=now)
    session.add(job)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = _existing_job(session, principal.user_id, declaration.declaration_id, body.request_key)
        if existing is None:
            raise _refusal(409, "operation_id_reused", "/operation_id",
                           "This operation ID belongs to another job.") from None
        return _replay(session, existing, fingerprint)
    _event(session, job, "JOB_QUEUED", {"schema_version": JOB_VERSION, "requested": requested,
                                        "declaration_sha256": declaration.content["frozen"]["configuration_sha256"],
                                        **({} if frozen_release is None else
                                           {"operating_release": _release_record(runtime)})})
    if not granted:
        job.state, job.terminal_reason = "BUDGET_EXHAUSTED", "research_budget_exhausted"
        _event(session, job, "BUDGET_REFUSED", {"requested": requested, "refused": refused})
        session.commit()
        raise _budget_refusal(job)
    job.state = "RESERVED"
    _event(session, job, "BUDGET_RESERVED", {"reserved": requested,
                                             "reservation_id": str(outcome.reservation.reservation_id)})
    session.commit()
    return 201, job_view(session, job)


# ------------------------------------------------------------------------------------------------- Nansen

def _nansen_refusal(code: str, detail: str) -> AppError:
    return AppError(422, "NANSEN_REPORT", "INVALID_INPUT", code, [finding(code, "/", detail)])


def _nansen_released(runtime: Any) -> bool:
    return runtime is not None and runtime.release.nansen is not None


def start_nansen_job(session: Session, principal: Principal, settings: Settings, intake_id: str,
                     body: NansenReportBody, runtime: Any = None) -> tuple[int, dict[str, Any]]:
    """Save one original Nansen report job and reserve its caps before any effect. The same key returns it.

    With a composed release Nansen part, the request must equal the release's fixed request exactly."""
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    released = _nansen_released(runtime)
    if not released and settings.nansen_research_mode != "authored_fixture":
        raise _refusal(409, "nansen_research_unavailable", "/",
                       "Nansen research is unavailable in this configuration. Nothing was started.")
    fingerprint = record_contract.sha256_hex({"owner_id": str(principal.user_id),
                                              "intake_record_id": str(intake.record_id),
                                              "body": body.model_dump(mode="json")})
    saved = _nansen_request_for_key(session, principal.user_id, intake.record_id, body.request_key)
    if saved is not None:
        return _replay(session, _nansen_job(session, saved), fingerprint)
    if released:
        mismatched = released_source_runtime.nansen_mismatches(runtime, body.model_dump(mode="json"))
        if mismatched:
            raise AppError(422, "NANSEN_REPORT", "INVALID_INPUT", "release_request_mismatch", [finding(
                "release_request_mismatch", path, "This report runs under a fixed operating release. Use its listed "
                "value exactly. Nothing was reserved.") for path in mismatched])
    now = utcnow()
    deadline_at = now + dt.timedelta(seconds=body.deadline_seconds)
    try:
        request = nansen_reports.build_request(body, intake.content["original_request"], _whole_seconds(deadline_at))
    except (NansenRequestError, NansenLimitError) as error:
        raise _nansen_refusal(error.code, error.detail) from None
    requested = nansen_reports.reservation(body)
    job_id, request_id = uuid.uuid4(), uuid.uuid4()
    try:
        outcome = quota.reserve(session, principal.user_id, QUOTA_SUBJECT, str(job_id), requested, caps(settings))
    except quota.CapMismatch as error:
        session.rollback()
        raise _cap_mismatch(error) from None
    saved = _nansen_request_for_key(session, principal.user_id, intake.record_id, body.request_key)
    if saved is not None:  # a concurrent start with this key won; the quota locks serialized us behind it
        session.rollback()
        return _replay(session, _nansen_job(session, saved), fingerprint)
    active = session.execute(select(func.count()).select_from(InvestigationJobRow).where(
        InvestigationJobRow.owner_id == principal.user_id,
        InvestigationJobRow.state.in_(("QUEUED", *RUNNABLE)))).scalar_one()
    if active >= settings.research_max_active_jobs:
        session.rollback()
        raise _refusal(409, "too_many_active_jobs", "/",
                       f"You already have {active} research jobs waiting or running. Cancel one or wait for one to "
                       "finish. Nothing was started.")
    content = nansen_reports.request_content(principal.user_id, intake.record_id, body.request_key, request)
    if released:
        content["operating_release"] = _release_record(runtime)
    session.add(nansen_reports.NansenRequestRow(
        request_id=request_id, owner_id=principal.user_id, intake_record_id=intake.record_id,
        request_key=body.request_key, content_sha256=record_contract.sha256_hex(content), content=content,
        created_at=now))
    granted = isinstance(outcome, quota.Grant)
    zero = {key: 0 for key in requested}
    job = InvestigationJobRow(
        job_id=job_id, owner_id=principal.user_id, intake_record_id=intake.record_id, declaration_id=request_id,
        request_key=body.request_key, operation_id=uuid.UUID(body.operation_id), fingerprint=fingerprint,
        state="QUEUED", kind=nansen_reports.NANSEN_KIND,
        budget={"requested": requested, "reserved": dict(requested) if granted else dict(zero), "settled": dict(zero),
                "consumed": dict(zero), "unknown_liability": dict(zero), "released": dict(zero),
                "overrun": dict(zero)},
        deadline_at=deadline_at, created_at=now, updated_at=now)
    session.add(job)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        saved = _nansen_request_for_key(session, principal.user_id, intake.record_id, body.request_key)
        if saved is None:
            raise _refusal(409, "operation_id_reused", "/operation_id",
                           "This operation ID belongs to another job.") from None
        return _replay(session, _nansen_job(session, saved), fingerprint)
    _event(session, job, "JOB_QUEUED", {"schema_version": JOB_VERSION, "kind": job.kind, "requested": requested,
                                        "request_sha256": content["request_sha256"]})
    if not granted:
        job.state, job.terminal_reason = "BUDGET_EXHAUSTED", "research_budget_exhausted"
        _event(session, job, "BUDGET_REFUSED", {"requested": requested, "refused": {
            "scope": outcome.scope, "resource": outcome.resource, "requested": outcome.requested,
            "available": outcome.available}})
        session.commit()
        raise _budget_refusal(job)
    job.state = "RESERVED"
    _event(session, job, "BUDGET_RESERVED", {"reserved": requested,
                                             "reservation_id": str(outcome.reservation.reservation_id)})
    session.commit()
    return 201, job_view(session, job)


def _nansen_request_for_key(session: Session, owner_id: uuid.UUID, intake_id: uuid.UUID,
                            key: str) -> nansen_reports.NansenRequestRow | None:
    return session.execute(select(nansen_reports.NansenRequestRow).where(
        nansen_reports.NansenRequestRow.owner_id == owner_id,
        nansen_reports.NansenRequestRow.intake_record_id == intake_id,
        nansen_reports.NansenRequestRow.request_key == key)).scalar_one_or_none()


def _nansen_job(session: Session, request: nansen_reports.NansenRequestRow) -> InvestigationJobRow:
    return session.execute(select(InvestigationJobRow).where(
        InvestigationJobRow.owner_id == request.owner_id,
        InvestigationJobRow.declaration_id == request.request_id)).scalar_one()


def list_nansen_jobs(session: Session, principal: Principal, settings: Settings, intake_id: str,
                     runtime: Any = None) -> dict[str, Any]:
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    rows = session.execute(select(InvestigationJobRow).where(
        InvestigationJobRow.owner_id == principal.user_id, InvestigationJobRow.intake_record_id == intake.record_id,
        InvestigationJobRow.kind == nansen_reports.NANSEN_KIND)
        .order_by(InvestigationJobRow.created_at, InvestigationJobRow.job_id)).scalars().all()
    # `available` says whether this server composes the Nansen transport; saved reports reopen either way.
    released = _nansen_released(runtime)
    listing: dict[str, Any] = {"available": settings.nansen_research_mode == "authored_fixture" or released,
                               "jobs": [job_view(session, row) for row in rows]}
    if released:  # additive: the fixed request a composed release permits
        listing["operating_release"] = {**_release_record(runtime), "evidence_class": runtime.evidence_class,
                                        "request": released_source_runtime.nansen_request(runtime.release.nansen)}
    return listing


def get_nansen_report(session: Session, principal: Principal, report_id: str) -> dict[str, Any]:
    return nansen_reports.report_view(nansen_reports.owned_report(session, principal, report_id))


def _owned_job(session: Session, principal: Principal, job_id: str, *, lock: bool = False) -> InvestigationJobRow:
    parsed = parse_uuid(job_id)
    statement = select(InvestigationJobRow).where(InvestigationJobRow.owner_id == principal.user_id,
                                                  InvestigationJobRow.job_id == parsed)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = None if parsed is None else session.execute(statement).scalar_one_or_none()
    if row is None:
        raise not_found("investigation job")
    return row


def cancel_job(session: Session, principal: Principal, settings: Settings, job_id: str) -> dict[str, Any]:
    """Request cancellation. A job that has not started an effect stops now and releases its reservation."""
    job = _owned_job(session, principal, job_id, lock=True)
    if job.state in TERMINAL:
        session.rollback()
        return job_view(session, job)
    if job.cancel_requested_at is None:
        job.cancel_requested_at = utcnow()
        _event(session, job, "CANCEL_REQUESTED", {"state_at_request": job.state})
    if job.state == "RESERVED":
        _finish(session, job, settings, "CANCELLED", "cancelled_before_collection", provider="KNOWN", compute="KNOWN")
    session.commit()
    return job_view(session, job)


def get_job(session: Session, principal: Principal, job_id: str) -> dict[str, Any]:
    return job_view(session, _owned_job(session, principal, job_id))


def list_jobs(session: Session, principal: Principal, intake_id: str, declaration_id: str) -> dict[str, Any]:
    declaration = owned_history_declaration(session, principal, intake_id, declaration_id)
    rows = session.execute(select(InvestigationJobRow).where(
        InvestigationJobRow.owner_id == principal.user_id,
        InvestigationJobRow.declaration_id == declaration.declaration_id)
        .order_by(InvestigationJobRow.created_at, InvestigationJobRow.job_id)).scalars().all()
    return {"jobs": [job_view(session, row) for row in rows]}


def get_report(session: Session, principal: Principal, report_id: str) -> dict[str, Any]:
    parsed = parse_uuid(report_id)
    row = None if parsed is None else session.execute(select(InvestigationReportRow).where(
        InvestigationReportRow.owner_id == principal.user_id,
        InvestigationReportRow.report_id == parsed)).scalar_one_or_none()
    if row is None:
        raise not_found("investigation report")
    return _report_view(row)


def _report_view(row: InvestigationReportRow) -> dict[str, Any]:
    return {"report_id": str(row.report_id), "content_sha256": row.content_sha256,
            "stored_hash_matches_content": record_contract.sha256_hex(row.content) == row.content_sha256,
            "created_at": _iso(row.created_at), "content": row.content}


def _nansen_summary(row: nansen_reports.NansenReportRow | None) -> dict[str, Any] | None:
    """The saved Nansen report at a glance; the full packages come from `GET /v1/research/nansen-reports/{id}`."""
    if row is None:
        return None
    report = row.content["report"]
    return {"report_id": str(row.report_id), "content_sha256": row.content_sha256,
            "answer_state": report["answer_state"], "question": report["question"],
            "token_symbol": report["token_symbol"], "evidence_class": row.content["evidence_class"],
            "settlement": row.content["settlement"], "outcomes": row.content["outcomes"]}


def job_view(session: Session, job: InvestigationJobRow) -> dict[str, Any]:
    nansen = job.kind == nansen_reports.NANSEN_KIND
    dataset = None if job.dataset_id is None else session.get(HistoryDatasetRow, job.dataset_id)
    report = None if job.report_id is None or nansen else session.get(InvestigationReportRow, job.report_id)
    nansen_report = None if job.report_id is None or not nansen else session.get(
        nansen_reports.NansenReportRow, job.report_id)
    return {
        "schema_version": JOB_VERSION, "kind": job.kind, "job_id": str(job.job_id),
        "declaration_id": str(job.declaration_id),
        "nansen_report": _nansen_summary(nansen_report),
        "intake_record_id": str(job.intake_record_id), "request_key": job.request_key,
        "operation_id": str(job.operation_id), "state": job.state, "terminal_reason": job.terminal_reason,
        "budget": job.budget, "deadline_at": _iso(job.deadline_at),
        "cancel_requested_at": _iso(job.cancel_requested_at), "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "events": [{"kind": event.kind, "attempt_id": None if event.attempt_id is None else str(event.attempt_id),
                    "created_at": _iso(event.created_at),
                    "content": history_payload_binding.public_event(event.kind, event.content)}
                   for event in _events(session, job.job_id)],
        "dataset": None if dataset is None else {
            "dataset_id": str(dataset.dataset_id), "content_sha256": dataset.content_sha256,
            "hashes_verified": history_dataset.verify_hashes(dataset),
            "summary": {key: dataset.content[key] for key in (
                "source_id", "evidence_class", "content_label", "status", "stop_reason", "verdict", "binding_state",
                "unavailable_states", "provider_requests", "provider_requests_state", "invocations_measured",
                "window_start", "window_end", "gaps", "normalized_sha256", "collection_sha256", "market_binding_id")},
            "transport": _transport_summary(dataset.content),
            "payload_binding": history_payload_binding.binding_state(session, dataset, job.owner_id)},
        "report": None if report is None else _report_view(report),
    }


# ------------------------------------------------------------------------------------------------- worker

def _transport_summary(content: dict[str, Any]) -> dict[str, Any] | None:
    """What a native source's P07 transport computed, and what the recording only declared. None for a bundle."""
    transport = content.get("transport")
    if transport is None:
        return None
    corroboration = transport["corroboration"]
    chain = transport["chain_read"] or {}
    summary = {"envio_pages_framed": transport["envio"]["pages_framed"], "client_calls": transport["client_calls"],
               "chain_id": chain.get("chain_id"), "chain_network": chain.get("network"),
               "corroboration": {key: corroboration[key] for key in ("class", "sample_size", "population_size",
                                                                    "mismatches")},
               "corroboration_reason": corroboration.get("reason"),
               "recorded_declarations": sorted(key for key, value in content["evidence_basis"].items()
                                               if value in {"RECORDED_DECLARATION", "RELEASE_DECLARATION"})}
    if transport.get("clients") in {"P07_HTTP_CLIENTS_AUTHORED_TRANSPORT", released_source_runtime.CLIENTS_LABEL}:
        summary.update({"clients": transport["clients"], "client_classes": transport["client_classes"],
                        "transport_label": transport["transport_label"]})  # additive; recorded summaries unchanged
    if "operating_release" in content:
        summary.update({"operating_release": content["operating_release"], "transport_kind": content["transport_kind"],
                        "requests_hashed": len(transport.get("request_sha256", [])),
                        "endpoint_hosts": transport.get("endpoint_hosts")})
    return summary


def _lock_key(job_id: uuid.UUID) -> tuple[int, int]:
    digest = hashlib.sha256(f"investigation-job:{job_id}".encode()).digest()
    return (int.from_bytes(digest[:4], "big", signed=True), int.from_bytes(digest[4:8], "big", signed=True))


def _measured_compute(session: Session, job_id: uuid.UUID) -> int:
    """Compute seconds the job's finished tool attempts measured: the ceiling of their summed milliseconds.

    Events saved before milliseconds were recorded carry `compute_seconds`; those count as whole seconds.
    Pending changes are flushed first.
    """
    session.flush()
    total_ms = 0
    for event in _events(session, job_id):
        if event.kind != "ATTEMPT_FINISHED":
            continue
        usage = event.content.get("usage", {})
        total_ms += usage["compute_ms"] if "compute_ms" in usage else usage.get("compute_seconds", 0) * 1000
    return math.ceil(total_ms / 1000)


def _interrupted(session: Session, job_id: uuid.UUID) -> bool:
    """Some tool attempt spent compute that was never measured, so the job's compute cannot be known (G-N2):

    - an attempt reconciled as interrupted or with an unknown outcome;
    - an attempt that started and has neither a finish nor a reconciliation (for example a killed comparison
      followed by a cancel or the deadline);
    - an attempt that finished without a compute measurement (for example a failed comparison).
    """
    session.flush()
    events = _events(session, job_id)
    finished = {event.attempt_id for event in events if event.kind == "ATTEMPT_FINISHED"}
    reconciled = {uuid.UUID(event.content["attempt_id"]) for event in events
                  if event.kind == "ATTEMPT_RECONCILED" and event.content.get("attempt_id")}
    for event in events:
        if event.kind == "ATTEMPT_RECONCILED" and event.content.get("outcome") in {
                "INTERRUPTED_LOCAL_CALCULATION", "OUTCOME_UNKNOWN"}:
            return True
        if event.kind == "ATTEMPT_STARTED" and event.attempt_id not in finished | reconciled:
            return True
        if event.kind == "ATTEMPT_FINISHED":
            usage = event.content.get("usage") or {}
            if "compute_ms" not in usage and "compute_seconds" not in usage:
                return True
    return False


def _finish(session: Session, job: InvestigationJobRow, settings: Settings, state: str, reason: str, *,
            provider: str, compute: str, provider_consumed: int = 0, credits: str | None = None,
            credits_consumed: int = 0) -> None:
    """End a job. Known compute settles at what its finished attempts measured, the rest is released. A job with an
    interrupted attempt has unmeasured compute, so its open compute stays as unknown liability (G-N2). Nansen credits
    follow the provider settlement unless given."""
    if compute == "KNOWN" and _interrupted(session, job.job_id):
        compute = "UNKNOWN"
    _settle(session, job, settings, provider=provider, compute=compute, provider_consumed=provider_consumed,
            compute_consumed=_measured_compute(session, job.job_id) if compute == "KNOWN" else 0,
            credits=provider if credits is None else credits, credits_consumed=credits_consumed)
    job.state, job.terminal_reason, job.updated_at = state, reason, utcnow()
    _event(session, job, "JOB_" + state, {"reason": reason})


class InvestigationWorker:
    """Advances saved jobs. One process or many: a per-job advisory lock lets only one advance a job at a time."""

    def __init__(self, factory: sessionmaker[Session], settings: Settings,
                 clock: Callable[[], dt.datetime] = utcnow,
                 after_collection_saved: Callable[[uuid.UUID], None] | None = None,
                 nansen_transport: Callable[[str], Any] = provider_composition.nansen_transport,
                 http_clients: Callable[..., Any] = provider_composition.http_source_clients,
                 research_runtime: Any = None) -> None:
        self._factory, self._settings, self._clock = factory, settings, clock
        # The composed operating release, if any. Without it every saved release job ends UNAVAILABLE before effect.
        if research_runtime is not None:
            if research_runtime.release.kind == "STAND_IN" and settings.env == "production":
                raise ReleaseRefused("stand_in_refused_in_production", "a stand-in release is local and test only")
            history_dataset.check_release_source(research_runtime)
        self._runtime = research_runtime
        # Test seam: runs after the dataset and attempt result commit and before the job advances (a lost reply).
        self._after_collection_saved = after_collection_saved or (lambda job_id: None)
        # Per-job provider clients composed by the application; tests inject authored fault transports here.
        self._nansen_transport, self._http_clients = nansen_transport, http_clients

    def run_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._factory() as session:
            ids = list(session.execute(select(InvestigationJobRow.job_id).where(
                InvestigationJobRow.state.in_(RUNNABLE)).order_by(InvestigationJobRow.created_at)
                .limit(limit)).scalars())
        results = []
        for job_id in ids:
            try:
                result = self.run_job(job_id)
            except Exception as error:  # noqa: BLE001 - one job's defect must not stop other owners' jobs
                log.error("investigation job %s failed: %s", job_id, type(error).__name__)  # no message: it may hold provider text
                continue
            if result is not None:
                results.append(result)
        return results

    def run_job(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        with self._factory() as guard:
            key_a, key_b = _lock_key(job_id)
            if not guard.execute(text("SELECT pg_try_advisory_xact_lock(:a, :b)"), {"a": key_a, "b": key_b}).scalar():
                return None
            try:
                for _ in range(len(RUNNABLE) + 1):
                    with self._factory() as session:
                        job = session.get(InvestigationJobRow, job_id, with_for_update=True)
                        if job is None or job.state not in RUNNABLE:
                            break
                        self._advance(session, job)
                with self._factory() as session:
                    job = session.get(InvestigationJobRow, job_id)
                    return None if job is None else job_view(session, job)
            finally:
                guard.rollback()

    def _cancelled(self, job_id: uuid.UUID) -> bool:
        with self._factory() as session:
            return session.execute(select(InvestigationJobRow.cancel_requested_at).where(
                InvestigationJobRow.job_id == job_id)).scalar_one() is not None

    def _advance(self, session: Session, job: InvestigationJobRow) -> None:
        if job.kind == nansen_reports.NANSEN_KIND:
            self._advance_nansen(session, job)
            return
        now = self._clock()
        started_collect = _open_attempt(session, job.job_id, investigation_tools.COLLECT_TOOL)
        if job.state == "RESERVED" and (job.cancel_requested_at is not None or now >= job.deadline_at):
            state = "CANCELLED" if job.cancel_requested_at is not None else "DEADLINE_EXCEEDED"
            _finish(session, job, self._settings, state, f"{state.lower()}_before_collection",
                    provider="KNOWN", compute="KNOWN")
            session.commit()
            return
        if job.state == "RESERVED":
            self._collect(session, job)
            return
        if job.state == "COLLECTING":
            self._reconcile_collection(session, job, started_collect)
            return
        if job.state == "EVALUATING":
            if job.cancel_requested_at is not None or now >= job.deadline_at:
                state = "CANCELLED" if job.cancel_requested_at is not None else "DEADLINE_EXCEEDED"
                _finish(session, job, self._settings, state, f"{state.lower()}_after_collection",
                        provider="KNOWN", compute="KNOWN")
                session.commit()
                return
            self._evaluate(session, job)

    def _refuse_source(self, session: Session, job: InvestigationJobRow, source_id: str, reason: str) -> None:
        """Refused before any credential read or request: nothing was sent, so everything is released."""
        _event(session, job, "SOURCE_REFUSED", {"source_id": source_id, "reason": reason})
        _finish(session, job, self._settings, "UNAVAILABLE", reason, provider="KNOWN", compute="KNOWN")
        session.commit()

    def _collect(self, session: Session, job: InvestigationJobRow) -> None:
        declaration = _declaration(session, job)
        config = declaration.content["configuration"]
        frozen_release = declaration.content["frozen"].get("operating_release_sha256")
        prepared = None
        if frozen_release is not None:  # admission, then the only credential read; no request yet
            refused = release_refusal(self._runtime, frozen_release)
            if refused is None:
                try:
                    prepared = released_source_runtime.prepare_history(self._runtime)
                except ReleaseRefused as error:
                    refused = (error.code, error.detail)
            if refused is not None:
                self._refuse_source(session, job, config["source"]["source_id"], refused[0])
                return
        source = history_dataset.served_sources(self._runtime).get(config["source"]["source_id"])
        frozen = declaration.content["frozen"]["source_profile_sha256"]
        if (source is not None and source["evidence_class"] == history_dataset.HTTP_CLASS
                and self._settings.research_source_clients != "authored_http"):
            # The HTTP composition was removed after the job was saved: refused before any client exists.
            _event(session, job, "SOURCE_REFUSED", {"source_id": source["source_id"],
                                                    "reason": "history_source_unavailable"})
            _finish(session, job, self._settings, "UNAVAILABLE", "history_source_unavailable",
                    provider="KNOWN", compute="KNOWN")
            session.commit()
            return
        if source is None or history_dataset.profile_sha256(source) != frozen:
            # Checked before any attempt: nothing was collected, so the whole reservation is released.
            _event(session, job, "SOURCE_REFUSED", {"source_id": config["source"]["source_id"],
                                                    "frozen_profile_sha256": frozen,
                                                    "served": None if source is None else
                                                    history_dataset.profile_sha256(source)})
            _finish(session, job, self._settings, "UNAVAILABLE", "declared_source_changed",
                    provider="KNOWN", compute="KNOWN")
            session.commit()
            return
        attempt_id = uuid.uuid4()
        tool_input = {"source_id": source["source_id"], "profile_sha256": history_dataset.profile_sha256(source),
                      "scan": source["scan"], "bounds": config["resource_bounds"]}
        release = None if prepared is None else {
            "operating_release": _release_record(self._runtime), "evidence_class": source["evidence_class"],
            "transport_kind": self._runtime.transport_kind}
        binding = None if prepared is None else released_source_runtime.forward_history_binding(self._runtime)
        if binding is not None:  # frozen with the attempt, before any effect; the handoff text is not copied
            release[history_payload_binding.REQUIREMENT_KEY] = history_payload_binding.requirement(binding)
        _event(session, job, "ATTEMPT_STARTED", {"tool": investigation_tools.COLLECT_TOOL,
                                                 "tool_version": investigation_tools.TOOL_VERSION,
                                                 "input_sha256": investigation_tools.input_sha256(tool_input),
                                                 "input": tool_input, **(release or {})}, attempt_id)
        job.state, job.updated_at = "COLLECTING", utcnow()
        session.commit()  # the original attempt is durable before the adapter runs
        started_at = self._clock()
        try:
            if prepared is not None:
                composed = {"http_clients": release_http_clients(prepared, job.deadline_at, self._clock)}
            else:
                composed = ({"http_clients": self._http_clients}
                            if source["evidence_class"] == history_dataset.HTTP_CLASS else {})
            result, collection, normalized, transport = investigation_tools.collect_recorded_history(
                source, config["resource_bounds"], _whole_seconds(job.deadline_at), lambda: self._cancelled(job.job_id),
                lambda: _whole_seconds(self._clock()), **composed)
        except Exception as error:  # noqa: BLE001 - any adapter defect fails this job and keeps unknown liability
            session.rollback()
            job = session.get(InvestigationJobRow, job.job_id, with_for_update=True)
            _event(session, job, "ATTEMPT_FINISHED", {"tool": investigation_tools.COLLECT_TOOL, "outcome": "FAILED",
                                                      "error_type": type(error).__name__},
                   attempt_id)
            _finish(session, job, self._settings, "FAILED", "collection_failed", provider="UNKNOWN", compute="UNKNOWN")
            session.commit()
            return
        dataset_id = uuid.uuid4()
        if release is not None:
            release["application_collection_time"] = {"started_at": _iso(started_at), "finished_at": _iso(self._clock()),
                                                      "basis": "APPLICATION_CLOCK"}
        content = history_dataset.dataset_content(
            dataset_id=dataset_id, owner_id=job.owner_id, declaration_id=job.declaration_id, job_id=job.job_id,
            attempt_id=attempt_id, source=source, collection=collection, normalized=normalized, transport=transport,
            release=release)
        history_dataset.save_dataset(session, content, normalized["raw_records"])
        findings = []
        if result.usage["provider_requests_state"] == "UNKNOWN":
            findings.append({"finding": "PROVIDER_USAGE_MISSING", "liability": "UNKNOWN_KEEPS_RESERVATION"})
        if result.usage["provider_requests_state"] == "INVALID":
            findings.append({"finding": "PROVIDER_USAGE_INVALID", "liability": "UNKNOWN_KEEPS_RESERVATION"})
        _event(session, job, "ATTEMPT_FINISHED", {
            "tool": result.tool, "outcome": result.outcome, "output": result.output, "usage": result.usage,
            "provenance": result.provenance, "findings": findings, "dataset_id": str(dataset_id)}, attempt_id)
        if binding is not None:  # in the dataset transaction: one commit saves the dataset, its result and its binding
            history_payload_binding.record_binding(session, owner_id=job.owner_id, job_id=job.job_id,
                                                   attempt_id=attempt_id, dataset_id=dataset_id, definition=binding)
        session.commit()
        self._after_collection_saved(job.job_id)
        job = session.get(InvestigationJobRow, job.job_id, with_for_update=True)
        self._advance_from_saved(session, job)

    def _reconcile_collection(self, session: Session, job: InvestigationJobRow,
                              started: InvestigationEventRow | None) -> None:
        """Resume after a stop. A saved result advances; a missing one stays unknown. Never collect again."""
        finished = _finished(session, job.job_id, investigation_tools.COLLECT_TOOL)
        if finished is not None:
            _event(session, job, "ATTEMPT_RECONCILED", {"tool": investigation_tools.COLLECT_TOOL,
                                                        "outcome": "RESULT_FOUND_AFTER_RESTART"}, None)
            self._advance_from_saved(session, job)
            return
        _event(session, job, "ATTEMPT_RECONCILED", {
            "tool": investigation_tools.COLLECT_TOOL, "outcome": "OUTCOME_UNKNOWN",
            "attempt_id": None if started is None else str(started.attempt_id),
            "detail": "The worker stopped before the collection result was saved. It is not collected again."})
        _finish(session, job, self._settings, "UNAVAILABLE", "collection_outcome_unknown",
                provider="UNKNOWN", compute="UNKNOWN")
        session.commit()

    def _advance_from_saved(self, session: Session, job: InvestigationJobRow) -> None:
        finished = _finished(session, job.job_id, investigation_tools.COLLECT_TOOL)
        assert finished is not None
        usage = finished.content["usage"]
        known = usage["provider_requests_state"] in {"SUPPLIED_EVIDENCE", "MEASURED_CLIENT_CALLS"}
        consumed = sum(usage["provider_requests"].values()) if known else 0
        job.dataset_id = uuid.UUID(finished.content["dataset_id"])
        stop = finished.content["output"]["stop_reason"]
        _settle(session, job, self._settings, provider="KNOWN" if known else "UNKNOWN", compute="SKIP",
                provider_consumed=consumed)
        if stop == "CANCELLED":
            _finish(session, job, self._settings, "CANCELLED", "cancelled_during_collection",
                    provider="KNOWN", compute="KNOWN")
        elif stop == "DEADLINE":
            _finish(session, job, self._settings, "DEADLINE_EXCEEDED", "deadline_during_collection",
                    provider="KNOWN", compute="KNOWN")
        else:
            job.state, job.updated_at = "EVALUATING", utcnow()
            _event(session, job, "JOB_EVALUATING", {"dataset_id": str(job.dataset_id)})
        session.commit()

    def _evaluate(self, session: Session, job: InvestigationJobRow) -> None:
        declaration = _declaration(session, job)
        dataset = session.get(HistoryDatasetRow, job.dataset_id)
        assert dataset is not None
        interrupted = _open_attempt(session, job.job_id, investigation_tools.COMPARE_TOOL)
        if interrupted is not None:
            _event(session, job, "ATTEMPT_RECONCILED", {
                "tool": investigation_tools.COMPARE_TOOL, "outcome": "INTERRUPTED_LOCAL_CALCULATION",
                "attempt_id": str(interrupted.attempt_id),
                "detail": "A local deterministic comparison stopped; a new attempt recalculates it. No provider call."})
        verified = history_dataset.verify_hashes(dataset)
        attempt_id = uuid.uuid4()
        tool_input = {"declaration_sha256": declaration.content["frozen"]["configuration_sha256"],
                      "rule_map_sha256": declaration.content["frozen"]["rule_map_sha256"],
                      "dataset_content_sha256": dataset.content_sha256}
        _event(session, job, "ATTEMPT_STARTED", {"tool": investigation_tools.COMPARE_TOOL,
                                                 "tool_version": investigation_tools.TOOL_VERSION,
                                                 "input_sha256": investigation_tools.input_sha256(tool_input),
                                                 "input": tool_input}, attempt_id)
        session.commit()
        if not all(verified.values()):
            _event(session, job, "ATTEMPT_FINISHED", {"tool": investigation_tools.COMPARE_TOOL, "outcome": "FAILED",
                                                      "error_type": "DatasetHashMismatch", "hashes": verified},
                   attempt_id)
            _finish(session, job, self._settings, "FAILED", "dataset_hash_mismatch", provider="KNOWN", compute="KNOWN")
            session.commit()
            return
        try:
            result = investigation_tools.compare_declared_effects(declaration.content, dataset.content)
        except Exception as error:  # noqa: BLE001 - a calculation defect fails this job only
            session.rollback()
            job = session.get(InvestigationJobRow, job.job_id, with_for_update=True)
            _event(session, job, "ATTEMPT_FINISHED", {"tool": investigation_tools.COMPARE_TOOL, "outcome": "FAILED",
                                                      "error_type": type(error).__name__}, attempt_id)
            _finish(session, job, self._settings, "FAILED", "comparison_failed", provider="KNOWN", compute="KNOWN")
            session.commit()
            return
        report_id = uuid.uuid4()
        frozen = declaration.content["frozen"]
        content = {
            **result.output, "report_id": str(report_id), "owner_id": str(job.owner_id), "job_id": str(job.job_id),
            "declaration_id": str(job.declaration_id), "request_record_id": str(job.intake_record_id),
            "declaration_configuration_sha256": frozen["configuration_sha256"],
            "rule_map_sha256": frozen["rule_map_sha256"], "rule_map": declaration.content["rule_map"],
            "evaluation_plan": declaration.content["configuration"]["evaluation_plan"],
            "hypothesis": declaration.content["edge_spec"]["hypothesis"],
            "dataset_id": str(dataset.dataset_id), "dataset_content_sha256": dataset.content_sha256,
            "dataset_normalized_sha256": dataset.content["normalized_sha256"],
            "dataset_verdict": dataset.content["verdict"], "evidence_class": dataset.content["evidence_class"],
            "content_label": dataset.content["content_label"], "source_id": dataset.content["source_id"],
            "access_order": [event.kind for event in _events(session, job.job_id)] + ["REPORT_SAVED"],
            "notice": (("Descriptive comparison of provider history. " if dataset.content["evidence_class"]
                        == released_source_runtime.ACTUAL_CLASS else "Descriptive comparison of synthetic recorded "
                        "responses. ") + "No statistical support, profitability, execution or capital authority is "
                       "claimed."),
        }
        session.add(InvestigationReportRow(report_id=report_id, owner_id=job.owner_id, job_id=job.job_id,
                                           declaration_id=job.declaration_id, dataset_id=dataset.dataset_id,
                                           content_sha256=record_contract.sha256_hex(content), content=content,
                                           created_at=utcnow()))
        _event(session, job, "ATTEMPT_FINISHED", {
            "tool": result.tool, "outcome": result.outcome, "usage": result.usage, "provenance": result.provenance,
            "contrary_findings": result.contrary_findings, "report_id": str(report_id)}, attempt_id)
        job.report_id = report_id
        _finish(session, job, self._settings, "REPORTED", result.outcome.lower(), provider="KNOWN", compute="KNOWN")
        session.commit()


    # ------------------------------------------------------------------------------------------ Nansen

    def _advance_nansen(self, session: Session, job: InvestigationJobRow) -> None:
        if job.state == "RESERVED" and (job.cancel_requested_at is not None or self._clock() >= job.deadline_at):
            state = "CANCELLED" if job.cancel_requested_at is not None else "DEADLINE_EXCEEDED"
            _finish(session, job, self._settings, state, f"{state.lower()}_before_collection",
                    provider="KNOWN", compute="KNOWN")
            session.commit()
            return
        request_row = session.get(nansen_reports.NansenRequestRow, job.declaration_id)
        released = None if request_row is None else request_row.content.get("operating_release")
        if job.state == "RESERVED" and released is not None:
            refused = release_refusal(self._runtime, released["sha256"], "nansen")
            if refused is not None:
                _event(session, job, "SOURCE_REFUSED", {"tool": nansen_reports.TOOL, "reason": refused[0]})
                _finish(session, job, self._settings, "UNAVAILABLE", refused[0], provider="KNOWN", compute="KNOWN")
                session.commit()
                return
        if (job.state == "RESERVED" and released is None
                and self._settings.nansen_research_mode != "authored_fixture"):
            # The composition was removed after the job was saved: refused before any effect, everything released.
            _event(session, job, "SOURCE_REFUSED", {"tool": nansen_reports.TOOL, "reason": "nansen_research_unavailable"})
            _finish(session, job, self._settings, "UNAVAILABLE", "nansen_research_unavailable",
                    provider="KNOWN", compute="KNOWN")
            session.commit()
            return
        if job.state == "RESERVED":
            self._run_nansen(session, job)
            return
        # COLLECTING with no saved result: the worker stopped during the run. Never run it again.
        _event(session, job, "ATTEMPT_RECONCILED", {
            "tool": nansen_reports.TOOL, "outcome": "OUTCOME_UNKNOWN",
            "attempt_id": None if (started := _open_attempt(session, job.job_id, nansen_reports.TOOL)) is None
            else str(started.attempt_id),
            "detail": "The worker stopped before the Nansen report was saved. It is not run again."})
        _finish(session, job, self._settings, "UNAVAILABLE", "nansen_outcome_unknown",
                provider="UNKNOWN", compute="UNKNOWN", credits="UNKNOWN")
        session.commit()

    def _run_nansen(self, session: Session, job: InvestigationJobRow) -> None:
        request_row = session.get(nansen_reports.NansenRequestRow, job.declaration_id)
        assert request_row is not None and request_row.owner_id == job.owner_id
        request = nansen_reports.saved_request(request_row)
        released = request_row.content.get("operating_release")
        job_id, deadline_at = job.job_id, job.deadline_at
        cancelled = lambda: self._cancelled(job_id)  # noqa: E731
        try:
            inner = (self._nansen_transport(request.token_address) if released is None
                     else release_nansen_transport(released_source_runtime.prepare_nansen(self._runtime), deadline_at,
                                                   self._clock, cancelled))
        except ReleaseRefused as error:  # the credential read failed: nothing was sent, everything is released
            session.rollback()
            job = session.get(InvestigationJobRow, job.job_id, with_for_update=True)
            _event(session, job, "SOURCE_REFUSED", {"tool": nansen_reports.TOOL, "reason": error.code})
            _finish(session, job, self._settings, "UNAVAILABLE", error.code, provider="KNOWN", compute="KNOWN")
            session.commit()
            return
        except Exception as error:  # noqa: BLE001 - nothing was sent: the composition failed before any attempt
            session.rollback()
            job = session.get(InvestigationJobRow, job.job_id, with_for_update=True)
            _event(session, job, "SOURCE_REFUSED", {"tool": nansen_reports.TOOL, "reason": "nansen_composition_failed",
                                                    "error_type": type(error).__name__})
            _finish(session, job, self._settings, "FAILED", "nansen_composition_failed", provider="KNOWN",
                    compute="KNOWN")
            session.commit()
            return
        attempt_id = uuid.uuid4()
        _event(session, job, "ATTEMPT_STARTED", {"tool": nansen_reports.TOOL,
                                                 "tool_version": investigation_tools.TOOL_VERSION,
                                                 "input_sha256": request_row.content["request_sha256"],
                                                 **({} if released is None else {
                                                     "operating_release": released,
                                                     "evidence_class": self._runtime.evidence_class})}, attempt_id)
        job.state, job.updated_at = "COLLECTING", utcnow()
        session.commit()  # the original attempt is durable before any provider effect
        started = time.monotonic()
        transport = provider_composition.GuardedNansenTransport(
            inner, cancelled, lambda: self._clock() >= deadline_at or (released is not None and inner.deadline_passed()))
        try:
            run = run_research(request, transport, clock=lambda: _whole_seconds(self._clock()))
        except Exception as error:  # noqa: BLE001 - any package or transport defect fails this job, liability kept
            session.rollback()
            job = session.get(InvestigationJobRow, job.job_id, with_for_update=True)
            _event(session, job, "ATTEMPT_FINISHED", {"tool": nansen_reports.TOOL, "outcome": "FAILED",
                                                      "error_type": type(error).__name__}, attempt_id)
            _finish(session, job, self._settings, "FAILED", "nansen_run_failed", provider="UNKNOWN",
                    compute="UNKNOWN", credits="UNKNOWN")
            session.commit()
            return
        session.rollback()  # end the read transaction held across the transport calls, then lock the job row
        job = session.get(InvestigationJobRow, job.job_id, with_for_update=True)
        request_row = session.get(nansen_reports.NansenRequestRow, job.declaration_id)
        assert request_row is not None
        settled = nansen_reports.settlement(run.evidence, transport.sent)
        report_id = uuid.uuid4()
        stand_in = self._runtime is not None and self._runtime.release.kind == "STAND_IN"
        labels = None if released is None else {
            "evidence_class": self._runtime.evidence_class,
            "transport_label": released_source_runtime.NANSEN_STAND_IN_LABEL if stand_in
            else released_source_runtime.NANSEN_ACTUAL_LABEL, "transport_kind": self._runtime.nansen_transport_kind,
            "notice": released_source_runtime.NANSEN_STAND_IN_NOTICE if stand_in
            else released_source_runtime.NANSEN_ACTUAL_NOTICE, "operating_release": released}
        content = nansen_reports.report_content(
            report_id=report_id, owner_id=job.owner_id, job_id=job.job_id, request_row=request_row, run=run,
            response_sha256=list(getattr(inner, "response_sha256", [])), settled=settled, labels=labels)
        session.add(nansen_reports.NansenReportRow(
            report_id=report_id, owner_id=job.owner_id, job_id=job.job_id, request_id=request_row.request_id,
            content_sha256=record_contract.sha256_hex(content), content=content, created_at=utcnow()))
        usage = {"provider_requests_state": settled["provider_requests"]["state"],
                 "provider_requests": {"NANSEN_TGM": settled["provider_requests"]["measured"]},
                 "nansen_credits": settled["nansen_credits"], "compute_ms": max(1, math.ceil(
                     (time.monotonic() - started) * 1000))}
        _event(session, job, "ATTEMPT_FINISHED", {
            "tool": nansen_reports.TOOL, "outcome": run.report.answer_state, "usage": usage,
            "stop_reason": run.evidence.stop_reason, "report_id": str(report_id)}, attempt_id)
        job.report_id = report_id
        stop = run.evidence.stop_reason
        # A call the transport stopped at the saved deadline ends the job there, like a refusal at the deadline.
        expired = stop == "DEADLINE" or (stop == "TIMEOUT" and self._clock() >= deadline_at)
        state, reason = (("CANCELLED", "cancelled_during_collection") if stop == "CANCELLED"
                         else ("DEADLINE_EXCEEDED", "deadline_during_collection") if expired
                         else ("REPORTED", run.report.answer_state.lower()))
        _finish(session, job, self._settings, state, reason,
                provider=settled["provider_requests"]["state"],
                provider_consumed=settled["provider_requests"]["measured"], compute="KNOWN",
                credits=settled["nansen_credits"]["state"], credits_consumed=settled["nansen_credits"]["measured"])
        session.commit()


def _whole_seconds(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _declaration(session: Session, job: InvestigationJobRow) -> Any:
    from edge_os_api.records.models import InvestigationDeclaration

    return session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == job.owner_id,
        InvestigationDeclaration.declaration_id == job.declaration_id)).scalar_one()


def _open_attempt(session: Session, job_id: uuid.UUID, tool: str) -> InvestigationEventRow | None:
    events = _events(session, job_id)
    finished = {event.attempt_id for event in events if event.kind == "ATTEMPT_FINISHED"}
    reconciled = {uuid.UUID(event.content["attempt_id"]) for event in events
                  if event.kind == "ATTEMPT_RECONCILED" and event.content.get("attempt_id")}
    return next((event for event in reversed(events) if event.kind == "ATTEMPT_STARTED"
                 and event.content["tool"] == tool and event.attempt_id not in finished
                 and event.attempt_id not in reconciled), None)


def _finished(session: Session, job_id: uuid.UUID, tool: str) -> InvestigationEventRow | None:
    return next((event for event in reversed(_events(session, job_id)) if event.kind == "ATTEMPT_FINISHED"
                 and event.content["tool"] == tool and "dataset_id" in event.content), None)


def main() -> None:
    """Bounded worker loop over saved investigation jobs. Nothing here creates new work."""
    from edge_os_api.core.database import make_engine, make_session_factory
    from edge_os_api.core.settings import load_settings

    parser = argparse.ArgumentParser(description="Advance saved investigation jobs.")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between passes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    engine = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    # The same server-owned release the API composes (none by default); see `released_runtime_bootstrap`.
    worker = InvestigationWorker(make_session_factory(engine), settings,
                                 research_runtime=released_runtime_bootstrap.server_research_runtime(settings))
    from edge_os_api.core import worker_loop

    worker_loop.exit_with(worker_loop.run("investigation worker", engine, worker.run_pending, once=args.once,
                                          interval=args.interval, log=log))

if __name__ == "__main__":
    main()
