"""Authenticated, owner-scoped agent removal routes.

The owner requests removal of the selected agent wallet's signer. The request is saved before any
provider effect and denies new submissions at once (REQUESTED denies). Reconciliation reads only the
server's removal port; a body can never post a confirmed removal. Owner access, pending recovery and
residual holdings stay.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.errors import AppError, finding, not_found
from edge_os_api.core.provider_ports import ProviderUnavailable
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.execution.connected_identity import resolve_agent
from edge_os_api.revocation.types import Provenance, RemovalError, RemovalObservation, RemovalRequest

router = APIRouter(prefix="/v1/agents", tags=["removal"], dependencies=[Depends(require_principal)])


class RemovalBody(StrictModel):
    request_key: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=200)


class EmptyBody(StrictModel):
    """No observation, identity or state can be supplied."""


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def _conflict(code: str, detail: str) -> AppError:
    return AppError(409, "REMOVAL", "CONFLICTED", code, [finding(code, "/", detail)])


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@router.post("/{agent_id}/removal")
def request_removal(agent_id: str, data: RemovalBody, request: Request,
                    principal: Principal = Depends(require_principal),
                    session: Session = Depends(get_session)) -> dict[str, Any]:
    agent = resolve_agent(session, principal.user_id, agent_id)
    if agent is None:
        raise not_found("agent wallet")
    session.rollback()
    try:
        view = request.app.state.financial.removals.request_removal(principal.user_id, RemovalRequest(
            request_key=data.request_key, agent_id=agent_id, network_id=agent.network_id,
            expected_wallet_id=agent.wallet_id, reason=data.reason,
            provenance=Provenance(source="edge-os-api", label="OWNER_REQUEST"), requested_at=_now()))
    except RemovalError as error:
        raise _conflict("removal_refused", str(error)) from None
    return view.model_dump(mode="json")


@router.get("/{agent_id}/removal")
def read_removal(agent_id: str, request: Request, principal: Principal = Depends(require_principal)) -> dict[str, Any]:
    views = request.app.state.financial.removals.read_removal(principal.user_id, agent_id=agent_id)
    return {"agent_id": agent_id, "removals": [view.model_dump(mode="json") for view in views]}


@router.post("/{agent_id}/removal/reconcile")
def reconcile_removal(agent_id: str, request: Request, data: EmptyBody | None = Body(default=None),
                      principal: Principal = Depends(require_principal)) -> dict[str, Any]:
    removals = request.app.state.financial.removals
    views = removals.read_removal(principal.user_id, agent_id=agent_id)
    if not views:
        raise not_found("removal request")
    view = views[-1]
    try:
        status = request.app.state.financial.ports.removals.observe(
            agent_id=agent_id, wallet_id=view.wallet_id, network_id=view.network_id)
    except ProviderUnavailable:
        raise AppError(503, "REMOVAL", "UNAVAILABLE", "removal_observation_unavailable", [finding(
            "removal_observation_unavailable", "/", "No qualified removal observation is available. "
            "The request stays saved and keeps denying new submissions.")], "SAFE_SAME_KEY") from None
    try:
        outcome = removals.reconcile(principal.user_id, RemovalObservation(
            observation_key=f"server-{uuid.uuid4()}", request_id=view.request_id, observed_state=status.observed_state,
            agent_id=agent_id, wallet_id=view.wallet_id, network_id=view.network_id,
            signer_identity=status.signer_identity, policy_identity=None,
            provenance=Provenance(source=status.source_ref[:120], label=None), observed_at=_now()))
    except RemovalError as error:
        raise _conflict("removal_reconcile_refused", str(error)) from None
    return outcome.model_dump(mode="json")
