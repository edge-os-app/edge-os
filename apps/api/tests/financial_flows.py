"""Drive the connected financial journey through the public API, the way the web app does.

Every step is an HTTP call by a verified owner. Nothing here inserts a success row. The fixture app uses
the authored wallet fixture and the authored execution-mode fixture ports; both are refused in production.
"""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import flows
from edge_os_api.main import create_app

TRADING_DEPOSIT = "1000000000"  # 1,000 quote units at 6 decimals
GAS_DEPOSIT = "1000000000000000000"  # 1 MON at 18 decimals
ENTRY_QUOTE_INPUT = "100000000"  # the fixture revision's FIXED_QUOTE_AMOUNT of 100 at 6 decimals
ENTRY_BASE_OUTPUT = "50000000000000000000"  # 100 quote at the authored fixture price of 2 quote per base
PER_ACTION_GAS = "1000000000000000"


def fixture_settings(settings: Any, effects: Path | None = None) -> Any:
    return settings.model_copy(update={"wallet_provider": "fixture", "execution_mode": "fixture",
                                       "fixture_effects_path": str(effects) if effects else None})


class _SlotAnchoredClient(TestClient):
    """A fixture client whose connected worker clock runs from the middle of the current five-minute slot.

    Evaluations must use observations collected in their own slot, so a test that schedules and evaluates must not
    straddle a real slot boundary. The clock still advances with real time; tests that shift it build on it.
    """

    def __enter__(self) -> "_SlotAnchoredClient":
        client = super().__enter__()
        start = dt.datetime.now(dt.timezone.utc)
        anchor = start.replace(second=0, microsecond=0)
        anchor = anchor - dt.timedelta(minutes=anchor.minute % 5) + dt.timedelta(seconds=150)
        self.app.state.financial.connected._clock = (
            lambda: anchor + (dt.datetime.now(dt.timezone.utc) - start))
        return client


def fixture_client(settings: Any, effects: Path | None = None) -> TestClient:
    return _SlotAnchoredClient(create_app(fixture_settings(settings, effects)))


def published_revision(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    bundle = flows.compiled_thesis(client, headers)
    response, body = flows.publish(client, headers, bundle)
    assert response.status_code == 201, response.text
    return {"strategy_id": body["strategy"]["strategy_id"], "revision_id": response.json()["revision_id"]}


def confirmed_agent(client: TestClient, headers: dict[str, str], agent_id: str,
                    revision: dict[str, Any] | None = None, network_id: int = 10143) -> dict[str, Any]:
    revision = revision or published_revision(client, headers)
    prepared = client.post(f"/v1/wallet-setup/agents/{agent_id}/prepare", headers=headers, json={
        "network_id": network_id, "strategy_id": revision["strategy_id"],
        "strategy_revision_id": revision["revision_id"], "request_key": f"key-{agent_id}"})
    assert prepared.status_code == 200, prepared.text
    dispatched = client.post(f"/v1/wallet-setup/agents/{agent_id}/dispatch", headers=headers)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["state"] == "CONFIRMED", dispatched.json()
    return {"agent_id": agent_id, **revision, "wallet_id": dispatched.json()["wallet_id"]}


def funded(client: TestClient, headers: dict[str, str], agent_id: str) -> dict[str, Any]:
    declared = client.post(f"/v1/agents/{agent_id}/funding/declaration", headers=headers)
    assert declared.status_code == 200, declared.text
    for asset_class, raw in (("TRADING", TRADING_DEPOSIT), ("NATIVE_GAS", GAS_DEPOSIT)):
        flow = client.post(f"/v1/agents/{agent_id}/funding/flows", headers=headers, json={
            "asset_class": asset_class, "raw": raw, "reference": f"{agent_id}-{asset_class.lower()}"})
        assert flow.status_code == 200, flow.text
    reconciled = client.post(f"/v1/agents/{agent_id}/funding/reconcile", headers=headers)
    assert reconciled.status_code == 200, reconciled.text
    return declared.json()


def connected_terms(declaration: dict[str, Any], *, expiry: str = "2030-01-01T00:00:00Z",
                    quote_cap: str = "500000000", attempts: int = 5) -> dict[str, Any]:
    quote = declaration["trading_asset"]
    gas = declaration["gas_asset"]
    base_asset = quote["asset_id"].rsplit("/", 1)[0] + "/0x1111111111111111111111111111111111111111"

    def amount(asset: dict[str, Any], raw: str) -> dict[str, Any]:
        return {"asset_id": asset["asset_id"], "raw": raw, "decimals": asset["decimals"]}

    base = {"asset_id": base_asset, "decimals": 18}
    return {
        "terms_version": "connected-spot/1", "operating_purpose": "TRIAL",
        "trial_objective": "Observe one bounded fixture action end to end.",
        "allocation": [amount(quote, quote_cap)],
        "allowances": [{"name": "quote_input", "amount": amount(quote, quote_cap)},
                       {"name": "base_inventory", "amount": amount(base, "1000000000000000000000")},
                       {"name": "per_action_gas", "amount": amount(gas, PER_ACTION_GAS)},
                       {"name": "per_exit_gas", "amount": amount(gas, PER_ACTION_GAS)}],
        "attempt_budget": attempts, "gas_budget": amount(gas, "100000000000000000"), "expiry": expiry,
        "supported_actions": ["ENTRY", "EXIT"], "supported_assets": [quote["asset_id"], base_asset],
        "supported_routes": ["KURU_FLOW_FIXED_INPUT"], "route": {"adapter": "KURU_FLOW_FIXED_INPUT"},
        "evidence": {"status": "HYPOTHESIS", "source": "fixture-research"},
        "stop_effects": ["STOP_NEW_ENTRIES denies new entries", "HALT_ALL_SWAPS denies every swap"]}


def adopted(client: TestClient, headers: dict[str, str], agent_id: str, declaration: dict[str, Any],
            **term_overrides: Any) -> dict[str, Any]:
    review = client.post(f"/v1/agents/{agent_id}/consent/review", headers=headers,
                         json={"terms": connected_terms(declaration, **term_overrides)})
    assert review.status_code == 200, review.text
    adopt = client.post(f"/v1/agents/{agent_id}/consent/adopt", headers=headers, json={
        "review_id": review.json()["review_id"], "expected_review_hash": review.json()["review_hash"]})
    assert adopt.status_code == 200, adopt.text
    return adopt.json()


def ready_for_action(client: TestClient, headers: dict[str, str], agent_id: str) -> dict[str, Any]:
    agent = confirmed_agent(client, headers, agent_id)
    declaration = funded(client, headers, agent_id)
    consent = adopted(client, headers, agent_id, declaration)
    return {**agent, "declaration": declaration, "consent": consent}


def schedule(client: TestClient, headers: dict[str, str], agent_id: str, key: str | None = None):
    return client.post(f"/v1/agents/{agent_id}/actions", headers=headers,
                       json={"request_key": key or f"run-{uuid.uuid4().hex[:10]}"})


def run_job(client: TestClient, job: dict[str, Any]) -> dict[str, Any]:
    """Advance one exact job. Tests share one database, so they never sweep other tests' jobs."""
    result = client.app.state.financial.connected.run_job(uuid.UUID(job["job_id"]))
    assert result is not None, "another worker holds this job"
    return result


def effects(client: TestClient) -> list[Any]:
    return client.app.state.financial.ports.chain.effects()
