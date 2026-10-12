"""Mounted financial routes: registration, verified-owner scoping and body boundaries.

Denials must leave protected rows unchanged and make zero provider effects.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

import financial_flows as ff


@pytest.fixture
def journey(settings, tmp_path):
    with ff.fixture_client(settings, tmp_path / "effects.jsonl") as client:
        yield client


def test_financial_routes_are_mounted(client):
    # FastAPI keeps included routers as nested objects; the generated schema lists every mounted path.
    paths = set(client.app.openapi()["paths"])
    assert {
        "/v1/agents/{agent_id}/funding",
        "/v1/agents/{agent_id}/consent/review",
        "/v1/agents/{agent_id}/consent/adopt",
        "/v1/agents/{agent_id}/actions",
        "/v1/actions/{action_id}",
        "/v1/actions/{action_id}/reconcile",
        "/v1/agents/{agent_id}/stops",
        "/v1/agents/{agent_id}/removal",
    } <= paths


@pytest.mark.parametrize("method,path", [
    ("GET", "/v1/agents/a/funding"), ("POST", "/v1/agents/a/funding/declaration"),
    ("POST", "/v1/agents/a/funding/flows"), ("POST", "/v1/agents/a/funding/reconcile"),
    ("POST", "/v1/agents/a/consent/review"), ("POST", "/v1/agents/a/consent/adopt"), ("GET", "/v1/agents/a/consent"),
    ("POST", "/v1/agents/a/actions"), ("GET", "/v1/agents/a/actions"), ("GET", "/v1/actions/x"),
    ("POST", "/v1/actions/x/reconcile"), ("POST", "/v1/agents/a/stops"), ("GET", "/v1/agents/a/stops"),
    ("POST", "/v1/agents/a/removal"), ("GET", "/v1/agents/a/removal"), ("POST", "/v1/agents/a/removal/reconcile"),
    ("GET", "/v1/financial/provider"),
])
def test_every_financial_route_requires_a_verified_principal(client, method, path):
    assert client.request(method, path).status_code == 401


def _counts(settings) -> dict[str, int]:
    engine = create_engine(settings.database_url)
    tables = ["funding_local.funding_flows", "funding_local.funding_credits", "consent_local.consent_reviews",
              "consent_local.consent_adoptions", "execution_local.execution_evaluation_jobs",
              "execution_local.execution_intents", "execution_local.execution_submission_attempts",
              "admission_local.admission_reservations", "stops_local.scoped_stops",
              "revocation_local.removal_requests", "recovery_local.recovery_evidence"]
    try:
        with engine.connect() as connection:
            return {table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in tables}
    finally:
        engine.dispose()


def test_another_owner_cannot_read_or_change_any_financial_resource(journey, settings, owner_a, owner_b):
    agent = "routes-owner-a"
    ff.ready_for_action(journey, owner_a, agent)
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    action_id = job["action_id"]
    review_id = journey.get(f"/v1/agents/{agent}/consent", headers=owner_a).json()["reviews"][0]["review_id"]
    before, effects_before = _counts(settings), len(ff.effects(journey))
    attempts = [
        ("GET", f"/v1/agents/{agent}/funding", None), ("POST", f"/v1/agents/{agent}/funding/declaration", None),
        ("POST", f"/v1/agents/{agent}/funding/flows", {"asset_class": "TRADING", "raw": "1", "reference": "b"}),
        ("POST", f"/v1/agents/{agent}/funding/reconcile", None),
        ("POST", f"/v1/agents/{agent}/consent/review", {"terms": ff.connected_terms(
            {"trading_asset": {"asset_id": "monad-testnet:10143/0x2222222222222222222222222222222222222222",
                               "decimals": 6}, "gas_asset": {"asset_id": "monad-testnet:10143/native", "decimals": 18}})}),
        ("POST", f"/v1/agents/{agent}/consent/adopt", {"review_id": review_id, "expected_review_hash": "sha256:" + "0" * 64}),
        ("POST", f"/v1/agents/{agent}/actions", {"request_key": "b-key"}), ("GET", f"/v1/agents/{agent}/actions", None),
        ("GET", f"/v1/actions/{action_id}", None), ("POST", f"/v1/actions/{action_id}/reconcile", None),
        ("POST", f"/v1/agents/{agent}/stops", {"mode": "HALT_ALL_SWAPS", "scope": "AGENT_WALLET_NETWORK"}),
        ("GET", f"/v1/agents/{agent}/stops", None),
        ("POST", f"/v1/agents/{agent}/removal", {"request_key": "b", "reason": "b"}),
        ("POST", f"/v1/agents/{agent}/removal/reconcile", None),
    ]
    for method, path, body in attempts:
        response = journey.request(method, path, headers=owner_b, json=body)
        assert response.status_code in (404, 409), (method, path, response.status_code, response.text)
    assert journey.get(f"/v1/agents/{agent}/removal", headers=owner_b).json()["removals"] == []
    assert journey.get(f"/v1/agents/{agent}/consent", headers=owner_b).json()["adoptions"] == []
    assert _counts(settings) == before
    assert len(ff.effects(journey)) == effects_before


@pytest.mark.parametrize("path,body", [
    ("/v1/agents/{agent}/funding/flows", {"asset_class": "TRADING", "raw": "1", "reference": "r",
                                          "owner_id": "00000000-0000-4000-8000-000000000000"}),
    ("/v1/agents/{agent}/funding/flows", {"asset_class": "TRADING", "raw": "01", "reference": "r"}),
    ("/v1/agents/{agent}/funding/flows", {"asset_class": "TRADING", "raw": "-5", "reference": "r"}),
    ("/v1/agents/{agent}/funding/flows", {"asset_class": "TRADING", "raw": 5, "reference": "r"}),
    ("/v1/agents/{agent}/funding/flows", {"asset_class": "COMPUTE", "raw": "5", "reference": "r"}),
    ("/v1/agents/{agent}/funding/reconcile", {"status": "CONFIRMED", "raw": "999"}),
    ("/v1/actions/{action}/reconcile", {"outcome": "CONFIRMED"}),
    ("/v1/agents/{agent}/actions", {"request_key": "k", "qualified": True}),
    ("/v1/agents/{agent}/removal/reconcile", {"observed_state": "CONFIRMED"}),
    ("/v1/agents/{agent}/consent/adopt", {"review_id": "x", "expected_review_hash": "sha256:" + "0" * 64,
                                          "status": "ACTIVE"}),
])
def test_bodies_cannot_assert_owner_balance_outcome_or_authority(journey, owner_a, path, body):
    agent = "routes-body"
    if not journey.get(f"/v1/agents/{agent}/funding", headers=owner_a).status_code == 200:
        ff.confirmed_agent(journey, owner_a, agent)
    response = journey.post(path.format(agent=agent, action="p23:missing:ENTRY"), headers=owner_a, json=body)
    assert response.status_code == 422, response.text
    assert ff.effects(journey) == []


def test_duplicate_requests_return_the_saved_identity(journey, owner_a):
    agent = "routes-duplicate"
    ff.confirmed_agent(journey, owner_a, agent)
    declaration = ff.funded(journey, owner_a, agent)
    again = journey.post(f"/v1/agents/{agent}/funding/declaration", headers=owner_a)
    assert again.json() == declaration
    body = {"asset_class": "TRADING", "raw": "7", "reference": "dup-flow"}
    first = journey.post(f"/v1/agents/{agent}/funding/flows", headers=owner_a, json=body).json()
    second = journey.post(f"/v1/agents/{agent}/funding/flows", headers=owner_a, json=body).json()
    assert first["flow_id"] == second["flow_id"]
    changed = journey.post(f"/v1/agents/{agent}/funding/flows", headers=owner_a, json={**body, "raw": "8"})
    assert changed.status_code == 409
    for _ in range(2):
        journey.post(f"/v1/agents/{agent}/funding/reconcile", headers=owner_a)
    credited = journey.get(f"/v1/agents/{agent}/funding", headers=owner_a).json()["deposit_balances"]
    trading = next(item for item in credited if item["asset_class"] == "TRADING")
    assert trading["credited_deposits"]["raw"] == str(int(ff.TRADING_DEPOSIT) + 7)  # once per event identity
    stop = {"mode": "STOP_NEW_ENTRIES", "scope": "AGENT_WALLET_NETWORK"}
    first_stop = journey.post(f"/v1/agents/{agent}/stops", headers=owner_a, json=stop).json()
    second_stop = journey.post(f"/v1/agents/{agent}/stops", headers=owner_a, json=stop).json()
    assert first_stop["stop_id"] == second_stop["stop_id"]


def test_unknown_agent_and_action_are_not_found(journey, owner_a):
    assert journey.get("/v1/agents/never-set-up/funding", headers=owner_a).status_code == 404
    assert journey.post("/v1/agents/never-set-up/actions", headers=owner_a,
                        json={"request_key": "k"}).status_code == 409
    assert journey.get(f"/v1/actions/p23:{uuid.uuid4()}:ENTRY", headers=owner_a).status_code == 404


def test_production_refuses_fixture_execution_and_fixture_effects(env):
    from edge_os_api.core.settings import ConfigError, load_settings
    production = {**env, "EDGE_OS_ENV": "production", "EDGE_OS_PRIVY_APP_ID": "real-app",
                  "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.example"}
    load_settings({key: value for key, value in production.items() if not key.startswith("EDGE_OS_DATABASE")}
                  | {"EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@db.internal/edge"})
    for extra in ({"EDGE_OS_EXECUTION_MODE": "fixture"}, {"EDGE_OS_FIXTURE_EFFECTS_PATH": "/tmp/x"}):
        with pytest.raises(ConfigError) as refused:
            load_settings({**production, "EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@db.internal/edge", **extra})
        assert "execution_mode" in str(refused.value) or "fixture_effects_path" in str(refused.value)
