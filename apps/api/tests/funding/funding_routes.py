"""Test-only FastAPI routes for local funding.

These routes are not production wiring. The application exposes no funding route. They call the real
`require_principal` with signed test tokens and the same verified-principal boundary as the rest of
the API. They are added to a fresh app only inside the funding test harness.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.funding import service
from edge_os_api.funding.observation import DepositObservationPort
from edge_os_api.funding.types import (AssetAmount, FundingBalance, FundingFlowRecord, FundingProfileRecord,
                                       ReconciliationResult)

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class DeclareBody(StrictModel):
    network_id: Literal[143, 10143]
    trading_asset_id: Identifier
    trading_decimals: int
    gas_asset_id: Identifier
    gas_decimals: int
    compute_asset_id: Identifier | None = None
    compute_decimals: int | None = None


class FlowBody(StrictModel):
    kind: Literal["DEPOSIT", "WITHDRAWAL"]
    asset_id: Identifier
    raw: Identifier
    decimals: int
    transport: Identifier
    reference: Identifier
    sender: Identifier | None = None
    recipient: Identifier | None = None
    declared_fee_asset_id: Identifier | None = None
    declared_fee_raw: Identifier | None = None
    declared_fee_decimals: int | None = None


class NoIdentityBody(StrictModel):
    """A mutation handler accepts no body. Any identity assertion is rejected at the request seam."""


def _amount(amount: AssetAmount | None) -> dict[str, Any] | None:
    return None if amount is None else {"asset_id": amount.asset_id, "raw": amount.raw, "decimals": amount.decimals}


def serialize_profile(record: FundingProfileRecord) -> dict[str, Any]:
    return {"owner_id": str(record.owner_id), "agent_id": record.agent_id, "wallet_id": record.wallet_id,
            "network_id": record.network_id, "trading_asset": _amount(record.trading_asset),
            "gas_asset": _amount(record.gas_asset), "compute_asset": _amount(record.compute_asset),
            "updated_at": record.updated_at.isoformat()}


def serialize_flow(record: FundingFlowRecord) -> dict[str, Any]:
    return {"flow_id": str(record.flow_id), "owner_id": str(record.owner_id), "agent_id": record.agent_id,
            "wallet_id": record.wallet_id, "network_id": record.network_id, "kind": record.kind.value,
            "asset": _amount(record.asset), "declared_fee": _amount(record.declared_fee), "transport": record.transport,
            "sender": record.sender, "recipient": record.recipient, "state": record.state.value,
            "reference": record.reference, "transaction_reference": record.transaction_reference,
            "reason": record.reason, "updated_at": record.updated_at.isoformat()}


def serialize_result(result: ReconciliationResult) -> dict[str, Any]:
    return {"flow": serialize_flow(result.flow),
            "observations": [{"observation_id": str(o.observation_id), "status": o.status.value,
                              "asset_id": o.asset_id, "actual": _amount(o.actual), "fee": _amount(o.fee),
                              "event_id": o.event_id, "flow_id": str(o.flow_id) if o.flow_id else None,
                              "reason": o.reason} for o in result.observations],
            "credits": [{"credit_id": str(c.credit_id), "asset_id": c.asset_id, "amount": _amount(c.amount),
                         "fee": _amount(c.fee), "event_id": c.event_id, "flow_id": str(c.flow_id)}
                        for c in result.credits],
            "denials": result.denials}


def serialize_balance(balance: FundingBalance) -> dict[str, Any]:
    return {"asset_class": balance.asset_class.value, "asset_id": balance.asset_id,
            "available": _amount(balance.available), "pending": _amount(balance.pending)}


def build_funding_router() -> APIRouter:
    router = APIRouter(prefix="/v1/funding", dependencies=[Depends(require_principal)])

    def get_session(request: Request) -> Any:
        with request.app.state.session_factory() as session:
            yield session

    def get_observer(request: Request) -> DepositObservationPort:
        return request.app.state.funding_observer

    @router.post("/agents/{agent_id}/declare")
    def declare(agent_id: str, data: DeclareBody, principal: Principal = Depends(require_principal),
                session: Session = Depends(get_session)) -> dict[str, Any]:
        record = service.declare_funding_assets(session, principal, agent_id=agent_id, network_id=data.network_id,
                                                trading_asset_id=data.trading_asset_id,
                                                trading_decimals=data.trading_decimals,
                                                gas_asset_id=data.gas_asset_id, gas_decimals=data.gas_decimals,
                                                compute_asset_id=data.compute_asset_id,
                                                compute_decimals=data.compute_decimals)
        return serialize_profile(record)

    @router.post("/agents/{agent_id}/flows")
    def prepare(agent_id: str, data: FlowBody, principal: Principal = Depends(require_principal),
                session: Session = Depends(get_session)) -> dict[str, Any]:
        record = service.prepare_funding(session, principal, agent_id=agent_id, kind=data.kind, asset_id=data.asset_id,
                                         raw=data.raw, decimals=data.decimals, transport=data.transport,
                                         reference=data.reference, sender=data.sender, recipient=data.recipient,
                                         declared_fee_asset_id=data.declared_fee_asset_id,
                                         declared_fee_raw=data.declared_fee_raw,
                                         declared_fee_decimals=data.declared_fee_decimals)
        return serialize_flow(record)

    @router.post("/agents/{agent_id}/reconcile")
    def reconcile(agent_id: str, data: NoIdentityBody | None = Body(default=None),
                  principal: Principal = Depends(require_principal), session: Session = Depends(get_session),
                  observer: DepositObservationPort = Depends(get_observer)) -> dict[str, Any]:
        results = service.reconcile_funding(session, principal, agent_id=agent_id, observer=observer)
        return {"results": [serialize_result(result) for result in results]}

    @router.get("/agents/{agent_id}/flows")
    def list_flows(agent_id: str, principal: Principal = Depends(require_principal),
                   session: Session = Depends(get_session)) -> dict[str, Any]:
        return {"flows": [serialize_flow(record)
                          for record in service.list_funding(session, principal, agent_id=agent_id)]}

    @router.get("/agents/{agent_id}/flows/{flow_id}")
    def read_flow(agent_id: str, flow_id: str, principal: Principal = Depends(require_principal),
                  session: Session = Depends(get_session)) -> dict[str, Any]:
        return serialize_flow(service.get_funding(session, principal, agent_id=agent_id, flow_id=flow_id))

    @router.get("/agents/{agent_id}/balances")
    def balances(agent_id: str, principal: Principal = Depends(require_principal),
                 session: Session = Depends(get_session)) -> dict[str, Any]:
        return {"balances": [serialize_balance(balance)
                             for balance in service.wallet_funding_summary(session, principal, agent_id=agent_id)]}

    @router.get("/agents/{agent_id}/available")
    def available(agent_id: str, asset_id: str = Query(...), principal: Principal = Depends(require_principal),
                  session: Session = Depends(get_session)) -> dict[str, Any]:
        return _amount(service.available_credit(session, principal, agent_id=agent_id, asset_id=asset_id)) or {}

    return router
