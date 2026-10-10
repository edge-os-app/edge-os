"""Test-only FastAPI routes for local wallet setup.

These routes are not production wiring. The application exposes no wallet setup route. They call
the real `require_principal` with signed test tokens and the same verified-principal boundary as
the rest of the API. They are added to a fresh app only inside the wallet-setup test harness.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Request
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.wallet_setup import service
from edge_os_api.wallet_setup.provider import WalletCreationPort
from edge_os_api.wallet_setup.types import SetupRecord

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class PrepareBody(StrictModel):
    network_id: Literal[143, 10143]
    strategy_id: Identifier
    strategy_revision_id: Identifier
    request_key: Identifier


class NoIdentityBody(StrictModel):
    """A mutation handler accepts no body. Any identity assertion is rejected at the request seam."""


def serialize(record: SetupRecord) -> dict[str, Any]:
    return {
        "setup_id": str(record.setup_id), "owner_id": str(record.owner_id), "agent_id": record.agent_id,
        "network_id": record.network_id, "strategy_id": record.strategy_id,
        "strategy_revision_id": str(record.strategy_revision_id), "state": record.state.value,
        "cancellation_intent": record.cancellation_intent.value, "creation_dispatched": record.creation_dispatched,
        "wallet_id": record.wallet_id, "reason": record.reason, "updated_at": record.updated_at.isoformat(),
    }


def build_wallet_setup_router() -> APIRouter:
    router = APIRouter(prefix="/v1/wallet-setup", dependencies=[Depends(require_principal)])

    def get_session(request: Request) -> Any:
        with request.app.state.session_factory() as session:
            yield session

    def get_provider(request: Request) -> WalletCreationPort:
        return request.app.state.wallet_provider

    @router.post("/agents/{agent_id}/prepare")
    def prepare(agent_id: str, data: PrepareBody, principal: Principal = Depends(require_principal),
                session: Session = Depends(get_session)) -> dict[str, Any]:
        record = service.prepare_setup(session, principal, agent_id=agent_id, network_id=data.network_id,
                                       strategy_id=data.strategy_id,
                                       strategy_revision_id=data.strategy_revision_id,
                                       request_key=data.request_key)
        return serialize(record)

    @router.post("/agents/{agent_id}/dispatch")
    def dispatch(agent_id: str, data: NoIdentityBody | None = Body(default=None),
                 principal: Principal = Depends(require_principal),
                 session: Session = Depends(get_session),
                 provider: WalletCreationPort = Depends(get_provider)) -> dict[str, Any]:
        return serialize(service.dispatch_setup(session, principal, agent_id=agent_id, provider=provider))

    @router.post("/agents/{agent_id}/resume")
    def resume(agent_id: str, data: NoIdentityBody | None = Body(default=None),
               principal: Principal = Depends(require_principal),
               session: Session = Depends(get_session),
               provider: WalletCreationPort = Depends(get_provider)) -> dict[str, Any]:
        return serialize(service.resume_setup(session, principal, agent_id=agent_id, provider=provider))

    @router.post("/agents/{agent_id}/cancel")
    def cancel(agent_id: str, data: NoIdentityBody | None = Body(default=None),
               principal: Principal = Depends(require_principal),
               session: Session = Depends(get_session)) -> dict[str, Any]:
        return serialize(service.cancel_setup(session, principal, agent_id=agent_id))

    @router.get("/agents/{agent_id}")
    def read(agent_id: str, principal: Principal = Depends(require_principal),
             session: Session = Depends(get_session)) -> dict[str, Any]:
        return serialize(service.get_setup(session, principal, agent_id=agent_id))

    return router
