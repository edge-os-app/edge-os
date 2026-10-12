"""Verified-token, ownership and malformed-input controls at the funding request boundary."""

from __future__ import annotations

import uuid

from funding import fake_observer
from funding import funding_helpers as h
from edge_os_api.funding.types import ObservationStatus


def _seed(funding_client, funding_engine, signer, sub: str, agent_id: str = "agent-a", wallet_id: str = "wallet-a"):
    owner_id = h.owner_id_for_sub(funding_client, funding_engine, signer, sub)
    h.seed_confirmed_binding(funding_engine, owner_id, agent_id=agent_id, wallet_id=wallet_id)
    return owner_id


def test_verified_owner_declares_prepares_and_reads(funding_client, funding_engine, signer):
    headers = h.auth_header(signer, "did:privy:route-owner-a")
    _seed(funding_client, funding_engine, signer, "did:privy:route-owner-a")
    declared = funding_client.post("/v1/funding/agents/agent-a/declare", headers=headers, json={
        "network_id": h.NETWORK, "trading_asset_id": h.TRADING_ASSET, "trading_decimals": 6,
        "gas_asset_id": h.GAS_ASSET, "gas_decimals": 18})
    assert declared.status_code == 200, declared.text
    prepared = funding_client.post("/v1/funding/agents/agent-a/flows", headers=headers, json={
        "kind": "DEPOSIT", "asset_id": h.TRADING_ASSET, "raw": "500000000", "decimals": 6,
        "transport": "deposit-address", "reference": "ref-route-1", "recipient": "wallet-a"})
    assert prepared.status_code == 200, prepared.text
    flow_id = prepared.json()["flow_id"]
    assert prepared.json()["state"] == "PENDING"
    read = funding_client.get(f"/v1/funding/agents/agent-a/flows/{flow_id}", headers=headers)
    assert read.status_code == 200 and read.json()["reference"] == "ref-route-1"


def test_missing_token_is_unauthorized(funding_client):
    assert funding_client.get("/v1/funding/agents/agent-a/flows").status_code == 401


def test_body_supplied_owner_is_rejected(funding_client, funding_engine, signer):
    headers = h.auth_header(signer, "did:privy:route-owner-b")
    _seed(funding_client, funding_engine, signer, "did:privy:route-owner-b")
    response = funding_client.post("/v1/funding/agents/agent-a/declare", headers=headers, json={
        "owner_id": str(uuid.uuid4()), "network_id": h.NETWORK, "trading_asset_id": h.TRADING_ASSET,
        "trading_decimals": 6, "gas_asset_id": h.GAS_ASSET, "gas_decimals": 18})
    assert response.status_code == 422


def test_cross_owner_read_is_a_404(funding_client, funding_engine, signer):
    headers_a = h.auth_header(signer, "did:privy:route-owner-c")
    _seed(funding_client, funding_engine, signer, "did:privy:route-owner-c")
    funding_client.post("/v1/funding/agents/agent-a/declare", headers=headers_a, json={
        "network_id": h.NETWORK, "trading_asset_id": h.TRADING_ASSET, "trading_decimals": 6,
        "gas_asset_id": h.GAS_ASSET, "gas_decimals": 18})
    prepared = funding_client.post("/v1/funding/agents/agent-a/flows", headers=headers_a, json={
        "kind": "DEPOSIT", "asset_id": h.TRADING_ASSET, "raw": "5", "decimals": 6, "transport": "deposit-address",
        "reference": "ref-c"})
    flow_id = prepared.json()["flow_id"]
    headers_b = h.auth_header(signer, "did:privy:route-owner-d")
    _seed(funding_client, funding_engine, signer, "did:privy:route-owner-d", agent_id="agent-b", wallet_id="wallet-b")
    assert funding_client.get(f"/v1/funding/agents/agent-b/flows/{flow_id}", headers=headers_b).status_code == 404


def test_malformed_flow_body_is_rejected(funding_client, funding_engine, signer):
    headers = h.auth_header(signer, "did:privy:route-owner-e")
    _seed(funding_client, funding_engine, signer, "did:privy:route-owner-e")
    funding_client.post("/v1/funding/agents/agent-a/declare", headers=headers, json={
        "network_id": h.NETWORK, "trading_asset_id": h.TRADING_ASSET, "trading_decimals": 6,
        "gas_asset_id": h.GAS_ASSET, "gas_decimals": 18})
    for body in ({"kind": "DEPOSIT", "asset_id": h.TRADING_ASSET, "raw": "00", "decimals": 6,
                  "transport": "t", "reference": "r"},
                 {"kind": "DEPOSIT", "asset_id": h.TRADING_ASSET, "raw": "5", "decimals": -1,
                  "transport": "t", "reference": "r"}):
        response = funding_client.post("/v1/funding/agents/agent-a/flows", headers=headers, json=body)
        assert response.status_code == 422


def test_reconcile_route_credits_once(funding_client, funding_engine, signer):
    sub = "did:privy:route-owner-f"
    headers = h.auth_header(signer, sub)
    _seed(funding_client, funding_engine, signer, sub)
    funding_client.post("/v1/funding/agents/agent-a/declare", headers=headers, json={
        "network_id": h.NETWORK, "trading_asset_id": h.TRADING_ASSET, "trading_decimals": 6,
        "gas_asset_id": h.GAS_ASSET, "gas_decimals": 18})
    funding_client.post("/v1/funding/agents/agent-a/flows", headers=headers, json={
        "kind": "DEPOSIT", "asset_id": h.TRADING_ASSET, "raw": "500000000", "decimals": 6,
        "transport": "deposit-address", "reference": "ref-f"})
    funding_client.app.state.funding_observer = fake_observer.AuthoredFakeDepositObserver([
        fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-f",
                                  status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET, raw="499000000",
                                  decimals=6, event_id="0xroute")])
    for _ in range(2):
        reconciled = funding_client.post("/v1/funding/agents/agent-a/reconcile", headers=headers, json={})
        assert reconciled.status_code == 200, reconciled.text
    available = funding_client.get("/v1/funding/agents/agent-a/available", headers=headers,
                                   params={"asset_id": h.TRADING_ASSET})
    assert available.json()["raw"] == "499000000"
