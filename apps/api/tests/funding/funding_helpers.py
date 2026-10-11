"""Shared authored fixtures for the local funding tests.

Everything here is authored synthetic data. It is not provider, chain or financial evidence.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import harness

from edge_os_api.core.authentication import Principal
from edge_os_api.funding import service
from edge_os_api.funding.persistence import utcnow
from edge_os_api.funding.types import FlowKind
from edge_os_api.wallet_setup.persistence import WalletSetupRow

HERE = Path(__file__).resolve().parent
API_DIR = HERE.parents[1]
SRC = API_DIR / "src"

NETWORK = 143
TRADING_ASSET = "monad:143/asset:USDC"
GAS_ASSET = "monad:143/native"
COMPUTE_ASSET = "monad:143/compute:credits"


def seed_confirmed_binding(engine, owner_id: uuid.UUID, agent_id: str = "agent-a", wallet_id: str = "wallet-a",
                           network_id: int = NETWORK) -> str:
    """Insert one accepted P17 CONFIRMED binding row. This is the funding module's wallet prerequisite."""
    now = utcnow()
    row = WalletSetupRow(setup_id=uuid.uuid4(), owner_id=owner_id, agent_id=agent_id, network_id=network_id,
                         strategy_id="strategy-x", strategy_revision_id=uuid.uuid4(), content_sha256="0" * 64,
                         manifest_sha256="0" * 64, state="CONFIRMED", cancellation_intent="NONE",
                         creation_dispatched=True, request_key="seed-binding", wallet_id=wallet_id,
                         created_at=now, updated_at=now)
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        session.add(row)
        session.commit()
    return wallet_id


def principal(owner_id: uuid.UUID) -> Principal:
    return Principal(user_id=owner_id, privy_did="did:privy:funding-test")


def auth_header(signer, sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {signer.token(sub)}"}


def owner_id_for_sub(funding_client, funding_engine, signer, sub: str) -> uuid.UUID:
    """Resolve the verified-principal user id for a signed subject through the real `/v1/me` route."""
    response = funding_client.get("/v1/me", headers=auth_header(signer, sub))
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["user_id"])


def declare(session, owner_id: uuid.UUID, *, agent_id: str = "agent-a", network_id: int = NETWORK,
            trading_asset_id: str = TRADING_ASSET, trading_decimals: int = 6, gas_asset_id: str = GAS_ASSET,
            gas_decimals: int = 18, compute_asset_id: str | None = None, compute_decimals: int | None = None):
    return service.declare_funding_assets(session, principal(owner_id), agent_id=agent_id, network_id=network_id,
                                          trading_asset_id=trading_asset_id, trading_decimals=trading_decimals,
                                          gas_asset_id=gas_asset_id, gas_decimals=gas_decimals,
                                          compute_asset_id=compute_asset_id, compute_decimals=compute_decimals)


def prepare(session, owner_id: uuid.UUID, *, agent_id: str = "agent-a", kind: FlowKind = FlowKind.DEPOSIT,
            asset_id: str = TRADING_ASSET, raw: str = "500000000", decimals: int = 6, transport: str = "deposit-address",
            reference: str = "ref-1", sender: str | None = None, recipient: str | None = None,
            declared_fee_asset_id: str | None = None, declared_fee_raw: str | None = None,
            declared_fee_decimals: int | None = None):
    return service.prepare_funding(session, principal(owner_id), agent_id=agent_id, kind=kind, asset_id=asset_id,
                                   raw=raw, decimals=decimals, transport=transport, reference=reference,
                                   sender=sender, recipient=recipient, declared_fee_asset_id=declared_fee_asset_id,
                                   declared_fee_raw=declared_fee_raw, declared_fee_decimals=declared_fee_decimals)


def driver_env() -> dict[str, str]:
    env = dict(os.environ)
    parts = [str(SRC), str(HERE)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def start_driver(db_url: str, owner_id: str, agent_id: str, wallet_id: str, network_id: int, reference: str,
                 event_id: str, raw: str, decimals: int, asset_id: str, scenario: str) -> subprocess.Popen[str]:
    """Start one independent process that drives the funding service against the same database."""
    return subprocess.Popen(
        [harness.api_python(), str(HERE / "funding_driver.py"), db_url, owner_id, agent_id, wallet_id,
         str(network_id), reference, event_id, raw, str(decimals), asset_id, scenario],
        env=driver_env(), cwd=str(API_DIR), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
