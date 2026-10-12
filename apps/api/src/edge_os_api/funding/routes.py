"""Authenticated, owner-scoped funding routes over the accepted funding service.

The owner comes from the verified `Principal`. The wallet, network and asset identities come from the
confirmed agent binding and its exact saved revision: a body chooses only which declared asset class to
fund, the raw amount and its own reference. Observed deposits come only from the server's configured
deposit port. A body can never post a confirmed deposit, a balance or a credit.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal, require_principal
from edge_os_api.core.errors import not_found
from edge_os_api.core.provider_ports import ProviderUnavailable
from edge_os_api.core.request_schemas import StrictModel
from edge_os_api.execution.connected_identity import resolve_agent
from edge_os_api.execution.original_transaction import wallet_address
from edge_os_api.funding import service
from edge_os_api.funding.persistence import load_profile, to_profile
from edge_os_api.funding.types import AssetAmount, FundingBalance, FundingFlowRecord, ReconciliationResult

router = APIRouter(prefix="/v1/agents", tags=["funding"], dependencies=[Depends(require_principal)])
DEPOSIT_TRANSPORT = "deposit-to-agent-wallet"


class FlowBody(StrictModel):
    asset_class: Literal["TRADING", "NATIVE_GAS"]
    raw: str = Field(min_length=1, max_length=78, pattern=r"^(0|[1-9][0-9]*)$")
    reference: str = Field(min_length=1, max_length=200)


class EmptyBody(StrictModel):
    """No identity, balance, observation or credit can be supplied."""


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def amount(value: AssetAmount | None) -> dict[str, Any] | None:
    return None if value is None else {"asset_id": value.asset_id, "raw": value.raw, "decimals": value.decimals}


def serialize_flow(record: FundingFlowRecord) -> dict[str, Any]:
    return {"flow_id": str(record.flow_id), "agent_id": record.agent_id, "wallet_id": record.wallet_id,
            "network_id": record.network_id, "kind": record.kind.value, "asset": amount(record.asset),
            "transport": record.transport, "recipient": record.recipient, "state": record.state.value,
            "reference": record.reference, "transaction_reference": record.transaction_reference,
            "reason": record.reason, "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat()}


def serialize_balance(balance: FundingBalance) -> dict[str, Any]:
    return {"asset_class": balance.asset_class.value, "asset_id": balance.asset_id,
            "credited_deposits": amount(balance.available), "pending_deposits": amount(balance.pending)}


def serialize_result(result: ReconciliationResult) -> dict[str, Any]:
    return {"flow": serialize_flow(result.flow),
            "observations": [{"status": o.status.value, "actual": amount(o.actual), "event_id": o.event_id,
                              "reason": o.reason} for o in result.observations],
            "credits": [{"asset_id": c.asset_id, "amount": amount(c.amount), "event_id": c.event_id}
                        for c in result.credits],
            "denials": result.denials}


def _agent(session: Session, principal: Principal, agent_id: str) -> Any:
    agent = resolve_agent(session, principal.user_id, agent_id)
    if agent is None:
        raise not_found("agent wallet")
    return agent


@router.get("/{agent_id}/funding")
def read_funding(agent_id: str, request: Request, principal: Principal = Depends(require_principal),
                 session: Session = Depends(get_session)) -> dict[str, Any]:
    """Declaration, reviewed flows, credited deposits and the separately observed current holdings."""
    agent = _agent(session, principal, agent_id)
    profile_row = load_profile(session, principal.user_id, agent_id)
    declaration = None
    balances: list[dict[str, Any]] = []
    if profile_row is not None:
        profile = to_profile(profile_row)
        declaration = {"trading_asset": amount(profile.trading_asset), "gas_asset": amount(profile.gas_asset)}
        balances = [serialize_balance(b) for b in service.wallet_funding_summary(session, principal, agent_id=agent_id)]
    flows = [serialize_flow(record) for record in service.list_funding(session, principal, agent_id=agent_id)]
    ports = request.app.state.financial.ports
    holdings: dict[str, Any]
    try:
        observed = ports.holdings.observe(
            owner_id=principal.user_id, agent_id=agent_id, wallet_id=agent.wallet_id, network_id=agent.network_id,
            assets=[(agent.quote.asset_id, agent.quote.decimals), (agent.base.asset_id, agent.base.decimals),
                    (agent.gas.asset_id, agent.gas.decimals)])
        address = (wallet_address(session, principal.user_id, agent_id, agent.wallet_id)
                   if observed.wallet_address is not None else None)
        holdings = observed.view(observed.refusal(wallet_address=address, chain_id=agent.network_number,
                                                  now=ports.clock()))
    except ProviderUnavailable:
        holdings = {"state": "UNAVAILABLE", "reason": "HOLDINGS_UNAVAILABLE", "evidence_class": None, "assets": []}
    allowances = [summary.model_dump(mode="json") for summary in request.app.state.financial.admission.balances(
        principal.user_id, agent_id=agent_id, wallet_id=agent.wallet_id, network_id=agent.network_id)]
    return {"agent_id": agent_id, "wallet_id": agent.wallet_id, "network_id": agent.network_number,
            "provider_mode": ports.mode, "declaration": declaration, "flows": flows, "deposit_balances": balances,
            "current_holdings": holdings, "allowances": allowances}


@router.post("/{agent_id}/funding/declaration")
def declare(agent_id: str, data: EmptyBody | None = Body(default=None), principal: Principal = Depends(require_principal),
            session: Session = Depends(get_session)) -> dict[str, Any]:
    """Declare the revision's quote asset as trading capital and native MON as gas. Idempotent."""
    agent = _agent(session, principal, agent_id)
    record = service.declare_funding_assets(
        session, principal, agent_id=agent_id, network_id=agent.network_number,
        trading_asset_id=agent.quote.asset_id, trading_decimals=agent.quote.decimals,
        gas_asset_id=agent.gas.asset_id, gas_decimals=agent.gas.decimals)
    return {"trading_asset": amount(record.trading_asset), "gas_asset": amount(record.gas_asset)}


@router.post("/{agent_id}/funding/flows")
def prepare(agent_id: str, data: FlowBody, principal: Principal = Depends(require_principal),
            session: Session = Depends(get_session)) -> dict[str, Any]:
    """Save one reviewed deposit before any transfer. A reviewed flow is not a sent or credited transfer."""
    agent = _agent(session, principal, agent_id)
    asset = agent.quote if data.asset_class == "TRADING" else agent.gas
    record = service.prepare_funding(session, principal, agent_id=agent_id, kind="DEPOSIT", asset_id=asset.asset_id,
                                     raw=data.raw, decimals=asset.decimals, transport=DEPOSIT_TRANSPORT,
                                     reference=data.reference, recipient=agent.wallet_id)
    return serialize_flow(record)


@router.post("/{agent_id}/funding/reconcile")
def reconcile(agent_id: str, request: Request, data: EmptyBody | None = Body(default=None),
              principal: Principal = Depends(require_principal),
              session: Session = Depends(get_session)) -> dict[str, Any]:
    """Read the server's deposit port. Only a CONFIRMED observation credits, once per event identity."""
    _agent(session, principal, agent_id)
    observer = request.app.state.financial.ports.deposits
    results = service.reconcile_funding(session, principal, agent_id=agent_id, observer=observer)
    return {"results": [serialize_result(result) for result in results]}
