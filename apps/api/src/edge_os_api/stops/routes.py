"""Authenticated, owner-scoped scoped-stop routes.

The wallet and network come from the confirmed agent binding. A stop is an owner control: it denies the
scoped unsent work and never cancels, liquidates or withdraws. Pending actions and residual inventory stay
visible and recoverable.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field, ValidationError
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.errors import invalid, not_found
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.execution.connected_identity import resolve_agent
from edge_os_api.stops.types import StopRequest

router = APIRouter(prefix="/v1/agents", tags=["stops"], dependencies=[Depends(require_principal)])


class StopBody(StrictModel):
    mode: Literal["STOP_NEW_ENTRIES", "HALT_ALL_SWAPS"]
    scope: Literal["POSITION", "AGENT_WALLET_NETWORK"]
    position_id: str | None = Field(default=None, min_length=1, max_length=200)


def get_session(request: Request) -> Any:
    with request.app.state.session_factory() as session:
        yield session


@router.post("/{agent_id}/stops")
def request_stop(agent_id: str, data: StopBody, request: Request, principal: Principal = Depends(require_principal),
                 session: Session = Depends(get_session)) -> dict[str, Any]:
    agent = resolve_agent(session, principal.user_id, agent_id)
    if agent is None:
        raise not_found("agent wallet")
    session.rollback()
    try:
        stop = StopRequest(trigger="USER", mode=data.mode, scope=data.scope, agent_id=agent_id,
                           wallet_id=agent.wallet_id, network_id=agent.network_id, position_id=data.position_id)
    except ValidationError:
        raise invalid("/position_id", "A position stop names its position; a wallet stop names none.",
                      "invalid_stop_scope") from None
    view = request.app.state.financial.stops.request_stop(principal.user_id, stop)
    return view.model_dump(mode="json")


@router.get("/{agent_id}/stops")
def list_stops(agent_id: str, request: Request, principal: Principal = Depends(require_principal),
               session: Session = Depends(get_session)) -> dict[str, Any]:
    agent = resolve_agent(session, principal.user_id, agent_id)
    if agent is None:
        raise not_found("agent wallet")
    views = request.app.state.financial.stops.retrieve_stops(
        principal.user_id, agent_id=agent_id, wallet_id=agent.wallet_id, network_id=agent.network_id)
    return {"agent_id": agent_id, "stops": [view.model_dump(mode="json") for view in views]}
