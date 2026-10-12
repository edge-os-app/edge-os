"""Bounded collection loop and the local run entry point.

One operation is collected page by page until the provider reports the last page
or a finite limit stops it. An expected provider or transport failure is recorded
with the attempted call and never retried. A caller-input problem propagates.

``run_research`` is the single local entry point. It builds no default transport,
opens no socket and reads no credential or environment value.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from edge_os_api.nansen_research.errors import (
    NansenBudgetExhausted,
    NansenTimeout,
    NansenTransportError,
)
from edge_os_api.nansen_research.evidence_extraction import (
    build_evidence,
    extract_flow_evidence,
    extract_holder_evidence,
)
from edge_os_api.nansen_research.models import NansenContext, NansenRequest, SourceRecord
from edge_os_api.nansen_research.nansen_client import OPERATIONS, NansenClient, NansenFetch
from edge_os_api.nansen_research.report_builder import build_report
from edge_os_api.nansen_research.serialization import canonical_sha256, utc_now
from edge_os_api.nansen_research.transport import NansenTransport


def _holder_body(request: NansenRequest, page: int) -> dict:
    body: dict[str, Any] = {
        "chain": request.network,
        "token_address": request.token_address,
        "aggregate_by_entity": request.holder_query.aggregate_by_entity,
        "label_type": request.holder_query.label_type,
        "pagination": {"page": page, "per_page": request.limits.per_page},
        "order_by": [{"field": request.holder_query.order_field, "direction": "DESC"}],
    }
    if request.holder_query.value_usd_min is not None:
        body["filters"] = {"value_usd": {"min": request.holder_query.value_usd_min}}
    return body


def _flow_body(request: NansenRequest, page: int) -> dict:
    return {
        "chain": request.network,
        "token_address": request.token_address,
        "date": {"from": request.window.start_utc, "to": request.window.end_utc},
        "label": request.flow_query.label,
        "pagination": {"page": page, "per_page": request.limits.per_page},
        "order_by": [{"field": "date", "direction": "ASC"}],
    }


def _body_builder(operation: str) -> Callable[[NansenRequest, int], dict]:
    return _holder_body if operation == "holders" else _flow_body


def _is_last_page(fetch: NansenFetch) -> bool | None:
    pagination = fetch.payload.get("pagination")
    if isinstance(pagination, Mapping):
        value = pagination.get("is_last_page")
        return value if isinstance(value, bool) else None
    return None


def _source_from_fetch(fetch: NansenFetch) -> SourceRecord:
    return SourceRecord(
        operation=fetch.operation,
        method=fetch.method,
        path=fetch.path,
        request_body=fetch.request_body,
        request_sha256=fetch.request_sha256,
        status=fetch.status,
        request_id=fetch.request_id,
        quoted_credits=fetch.quoted_credits,
        deducted_credits=fetch.deducted_credits,
        remaining_credits=fetch.remaining_credits,
        response_sha256=fetch.response_sha256,
        collected_at=fetch.collected_at,
        failure=None,
    )


def _failure_source(operation: str, body: Mapping[str, Any], code: str, collected_at: str) -> SourceRecord:
    method, path, _reservation = OPERATIONS[operation]
    return SourceRecord(
        operation=operation,
        method=method,
        path=path,
        request_body=dict(body),
        request_sha256=canonical_sha256(body),
        status=None,
        request_id=None,
        quoted_credits=None,
        deducted_credits=None,
        remaining_credits=None,
        response_sha256=None,
        collected_at=collected_at,
        failure=code,
    )


@dataclass(frozen=True)
class OperationOutcome:
    operation: str
    status: str
    stop_reason: str | None
    sources: tuple[SourceRecord, ...]
    fetches: tuple[NansenFetch, ...]


def _collect_operation(client: NansenClient, request: NansenRequest, operation: str) -> tuple[OperationOutcome, Any]:
    build = _body_builder(operation)
    fetches: list[NansenFetch] = []
    sources: list[SourceRecord] = []
    status = "COMPLETE"
    stop_reason: str | None = None
    page = 1
    while True:
        if page > request.limits.max_pages:
            status = "PARTIAL"
            stop_reason = "LIMIT_PAGES"
            break
        body = build(request, page)
        try:
            fetch = client.call(operation, body)
        except (NansenBudgetExhausted, NansenTimeout) as error:
            sources.append(_failure_source(operation, body, error.code, client.now()))
            status = "STOPPED"
            stop_reason = error.code
            break
        except NansenTransportError as error:
            sources.append(_failure_source(operation, body, error.code, client.now()))
            status = "FAILED"
            stop_reason = error.code
            break
        fetches.append(fetch)
        sources.append(_source_from_fetch(fetch))
        last = _is_last_page(fetch)
        if last is True:
            break
        if last is None:
            status = "PARTIAL"
            stop_reason = "PAGINATION_UNKNOWN"
            break
        page += 1

    extracted: Any = None
    if fetches and status in ("COMPLETE", "PARTIAL"):
        try:
            extracted = (extract_holder_evidence(fetches) if operation == "holders"
                         else extract_flow_evidence(fetches, request.window))
        except NansenTransportError as error:
            status = "FAILED"
            stop_reason = error.code
            extracted = None
    return OperationOutcome(operation, status, stop_reason, tuple(sources), tuple(fetches)), extracted


@dataclass(frozen=True)
class NansenRun:
    """The evidence package and the report from one local run."""

    evidence: Any = field()
    report: Any = field()
    outcomes: tuple[OperationOutcome, ...] = field(default=())


def run_research(request: NansenRequest, transport: NansenTransport, *,
                 context: NansenContext | None = None,
                 clock: Callable[[], str] = utc_now) -> NansenRun:
    """Collect the requested operations and build the deterministic report.

    ``transport`` is the only provider path. ``clock`` is injected so a run stays
    deterministic in a test.
    """
    request.validate()
    client = NansenClient(transport, request.limits, context=context or NansenContext(), clock=clock)
    outcomes: list[OperationOutcome] = []
    holder = None
    flows = None
    for operation in request.operations:
        outcome, extracted = _collect_operation(client, request, operation)
        outcomes.append(outcome)
        if operation == "holders":
            holder = extracted
        elif operation == "flows":
            flows = extracted

    sources = tuple(source for outcome in outcomes for source in outcome.sources)
    stop_reason = next((outcome.stop_reason for outcome in outcomes
                        if outcome.status in ("PARTIAL", "FAILED", "STOPPED")), None)
    evidence = build_evidence(
        request,
        client.context,
        sources=sources,
        attempts=client.attempts,
        pages=client.pages,
        reserved_credits=client.reserved_credits,
        holder=holder,
        flows=flows,
        stop_reason=stop_reason,
    )
    report = build_report(request, evidence)
    return NansenRun(evidence=evidence, report=report, outcomes=tuple(outcomes))
