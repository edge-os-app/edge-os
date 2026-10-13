"""Authenticated, owner-scoped bounded-action routes.

`POST /v1/agents/{agent_id}/actions` saves one evaluation job for the agent's adopted consent and the
current decision slot. It does not evaluate, admit or submit; the bounded worker does that from saved state.
A body carries only an idempotency key. Reads return the saved jobs, decisions, queue, attempts, admission
reservations and receipts, and the recovery case of the exact original action.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from edge_os_api.admission.models import PositionRow, ReservationRow
from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.errors import AppError, finding, not_found
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.execution.connected_identity import resolve_agent
from edge_os_api.execution.original_transaction import owner_projection
from edge_os_api.execution.models import DecisionRow, IntentRow, QueueRow, SubmissionAttemptRow
from edge_os_api.execution.recurring_scheduler import DeploymentRefused
from edge_os_api.execution.worker import JobRefused
from edge_os_api.recovery.models import RecoveryCaseRow
from edge_os_api.records import contract_adapter as record_contract

router = APIRouter(prefix="/v1", tags=["actions"], dependencies=[Depends(require_principal)])


RESERVED_KEY_PREFIX = "recurring:"  # occurrence keys the recurring producer saves; never an owner's manual key


class ScheduleBody(StrictModel):
    request_key: str = Field(min_length=1, max_length=200)

    @field_validator("request_key")
    @classmethod
    def not_reserved(cls, value: str) -> str:
        if value.startswith(RESERVED_KEY_PREFIX):
            raise ValueError("this key prefix is reserved for recurring occurrences")
        return value


class DeploymentBody(StrictModel):
    """Recurring activation binds the exact adopted consent the owner reviewed. Nothing else is accepted."""

    request_key: str = Field(min_length=1, max_length=200)
    expected_consent_hash: str = Field(min_length=1, max_length=200)


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def refused(error: JobRefused) -> AppError:
    if error.code == "action_not_found":
        return not_found("action")
    status = 503 if error.code.endswith("_unavailable") else 409
    detail = {"agent_not_ready": "The agent needs a confirmed wallet bound to an exact saved revision.",
              "consent_not_adopted": "Adopt the exact reviewed terms for this agent first.",
              "receipt_unavailable": "No qualified receipt source is available. The original action stays as saved."
              }.get(error.code, "The request was refused. Nothing was submitted.")
    return AppError(status, "ACTION", "UNAVAILABLE" if status == 503 else "CONFLICTED", error.code,
                    [finding(error.code, "/", detail)], "SAFE_SAME_KEY" if status == 503 else "NOT_RETRYABLE")


def _iso(value: Any) -> str | None:
    return None if value is None else record_contract.utc_string(value)


def decision_view(row: DecisionRow) -> dict[str, Any]:
    return {"decision_id": str(row.decision_id), "decision_at": _iso(row.decision_at), "status": row.status,
            "operation": row.operation, "reasons": row.reasons, "rule_results": row.rule_results,
            "revision_id": row.revision_id, "content_hash": row.content_hash,
            "market_binding_id": row.market_binding_id, "inputs_hash": row.inputs_hash}


def queue_view(row: QueueRow) -> dict[str, Any]:
    return {"queue_id": str(row.queue_id), "action_id": row.action_id, "operation": row.operation,
            "position_id": row.position_id, "state": row.state, "blocking_reason": row.blocking_reason,
            "enqueued_at": _iso(row.enqueued_at), "updated_at": _iso(row.updated_at)}


@router.post("/agents/{agent_id}/actions")
def schedule(agent_id: str, data: ScheduleBody, request: Request,
             principal: Principal = Depends(require_principal)) -> JSONResponse:
    try:
        created, job = request.app.state.financial.connected.schedule(principal.user_id, agent_id, data.request_key)
    except JobRefused as error:
        raise refused(error) from None
    return JSONResponse(job, status_code=201 if created else 200,
                        headers=None if created else {"Idempotent-Replay": "true"})


@router.get("/agents/{agent_id}/actions")
def agent_actions(agent_id: str, request: Request, principal: Principal = Depends(require_principal),
                  session: Session = Depends(get_session)) -> dict[str, Any]:
    agent = resolve_agent(session, principal.user_id, agent_id)
    if agent is None:
        raise not_found("agent wallet")
    owner = principal.user_id
    decisions = session.execute(select(DecisionRow).where(
        DecisionRow.owner_id == owner, DecisionRow.agent_id == agent_id).order_by(DecisionRow.decision_at)).scalars()
    queue = session.execute(select(QueueRow).where(QueueRow.owner_id == owner, QueueRow.agent_id == agent_id)
                            .order_by(QueueRow.enqueued_at)).scalars()
    positions = session.execute(select(PositionRow).where(
        PositionRow.owner_id == owner, PositionRow.agent_id == agent_id)).scalars()
    financial = request.app.state.financial
    health = financial.execution.status(owner, agent_id=agent_id, wallet_id=agent.wallet_id,
                                        network_id=agent.network_id)
    return {"agent_id": agent_id, "identity": agent.identity(), "provider_mode": financial.ports.mode,
            "jobs": financial.connected.list_jobs(owner, agent_id),
            "decisions": [decision_view(row) for row in decisions], "queue": [queue_view(row) for row in queue],
            "positions": [{"position_id": row.position_id, "asset_id": row.asset_id, "decimals": int(row.decimals),
                           "inventory_raw": str(int(row.inventory)), "cost_basis_raw": str(int(row.cost_basis)),
                           "realized_quote_raw": str(int(row.realized_quote)), "quote_asset_id": row.quote_asset_id}
                          for row in positions],
            "blocking_reason": health.blocking_reason, "next_scheduled_at": health.next_scheduled_at}


DEPLOYMENT_DETAIL = {
    "agent_not_ready": "The agent needs a confirmed wallet bound to an exact saved revision.",
    "consent_not_adopted": "Adopt the exact reviewed terms for this agent first.",
    "deployment_consent_mismatch": "The adopted terms changed. Review the current terms before activating.",
    "deployment_ended": "Recurring operation for these terms has ended. Review and adopt new terms to start again.",
    "deployment_not_found": "No recurring operation is saved for this agent.",
    "end_conflict": "Recurring operation changed while it was being ended. Nothing was ended; check it and try again.",
    "activation_unavailable": "No qualified execution route exists in this build. Nothing was activated.",
    "consent_expired": "The adopted terms have expired. Nothing was activated.",
    "agent_removed": "Agent removal was requested. Recurring operation cannot start for this agent.",
}


def deployment_refused(error: DeploymentRefused) -> AppError:
    if error.code == "deployment_not_found":
        return not_found("deployment")
    status = 503 if error.code == "activation_unavailable" else 409
    detail = DEPLOYMENT_DETAIL.get(error.code, "Recurring operation cannot start with these terms. Nothing was activated.")
    return AppError(status, "DEPLOYMENT", "UNAVAILABLE" if status == 503 else "CONFLICTED", error.code,
                    [finding(error.code, "/", detail)], "SAFE_SAME_KEY" if status == 503 else "NOT_RETRYABLE")


@router.post("/agents/{agent_id}/deployment")
def activate_deployment(agent_id: str, data: DeploymentBody, request: Request,
                        principal: Principal = Depends(require_principal)) -> JSONResponse:
    try:
        created, deployment = request.app.state.financial.recurring.activate(
            principal.user_id, agent_id, data.request_key, data.expected_consent_hash)
    except DeploymentRefused as error:
        raise deployment_refused(error) from None
    return JSONResponse(deployment, status_code=201 if created else 200,
                        headers=None if created else {"Idempotent-Replay": "true"})


@router.post("/agents/{agent_id}/deployment/end")
def end_deployment(agent_id: str, request: Request, principal: Principal = Depends(require_principal)) -> Any:
    try:
        return request.app.state.financial.recurring.end(principal.user_id, agent_id)
    except DeploymentRefused as error:
        raise deployment_refused(error) from None


@router.get("/agents/{agent_id}/deployment")
def read_deployment(agent_id: str, request: Request, principal: Principal = Depends(require_principal),
                    session: Session = Depends(get_session)) -> dict[str, Any]:
    view = request.app.state.financial.recurring.projection(principal.user_id, agent_id)
    # A saved deployment stays readable after its agent identity changed; an unknown agent is not found.
    if view["deployment"] is None and resolve_agent(session, principal.user_id, agent_id) is None:
        raise not_found("agent wallet")
    return view


@router.get("/actions/{action_id}")
def read_action(action_id: str, request: Request, principal: Principal = Depends(require_principal),
                session: Session = Depends(get_session)) -> dict[str, Any]:
    owner = principal.user_id
    intent = session.execute(select(IntentRow).where(
        IntentRow.owner_id == owner, IntentRow.action_id == action_id)).scalar_one_or_none()
    if intent is None:
        raise not_found("action")
    decision = session.execute(select(DecisionRow).where(
        DecisionRow.owner_id == owner, DecisionRow.decision_id == intent.decision_id)).scalar_one()
    queue = session.execute(select(QueueRow).where(
        QueueRow.owner_id == owner, QueueRow.action_id == action_id)).scalar_one_or_none()
    attempts = session.execute(select(SubmissionAttemptRow).where(
        SubmissionAttemptRow.owner_id == owner, SubmissionAttemptRow.action_id == action_id)
        .order_by(SubmissionAttemptRow.started_at)).scalars().all()
    case = session.execute(select(RecoveryCaseRow).where(
        RecoveryCaseRow.owner_id == owner, RecoveryCaseRow.action_id == action_id)).scalar_one_or_none()
    reservations = session.execute(select(ReservationRow).where(
        ReservationRow.owner_id == owner, ReservationRow.action_id == action_id)
        .order_by(ReservationRow.scope, ReservationRow.asset_id)).scalars().all()
    admission = request.app.state.financial.admission
    saved = admission.retrieve_decisions(owner, action_id=action_id)
    recovery = None
    if case is not None:
        recovery = request.app.state.financial.recovery.status(owner, action_id).model_dump(mode="json")
    return {"action_id": action_id, "agent_id": intent.agent_id, "wallet_id": intent.wallet_id,
            "network_id": intent.network_id, "operation": intent.operation, "position_id": intent.position_id,
            "revision_id": intent.revision_id, "mandate_id": intent.mandate_id, "policy_binding": intent.policy_binding,
            "payload_hash": intent.payload_hash, "review_hash": intent.review_hash, "payload": intent.payload,
            "decision": decision_view(decision), "queue": queue_view(queue) if queue is not None else None,
            "admission": [item.model_dump(mode="json") for item in saved],
            "reservations": [{"scope": row.scope, "asset_id": row.asset_id, "decimals": int(row.decimals),
                              "raw": str(int(row.raw)), "state": row.state} for row in reservations],
            "receipts": [item.model_dump(mode="json") for item in admission.retrieve_receipts(
                owner, action_id=action_id)],
            "attempts": [{"attempt_id": str(row.attempt_id), "state": row.state, "outcome": row.outcome,
                          "detail": row.detail, "transport_id": row.transport_id,
                          # Signed bytes and the signing request body stay private; the owner sees identities.
                          "content": {**{k: v for k, v in row.content.items() if k != "original_transaction"},
                                      "original_transaction": owner_projection(row.content.get(
                                          "original_transaction"))},
                          "started_at": _iso(row.started_at), "completed_at": _iso(row.completed_at)}
                         for row in attempts],
            "recovery": recovery}
