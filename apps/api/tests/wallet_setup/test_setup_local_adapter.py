"""The authored local fixture adapter and the production refusal, over the real mounted routes.

The session `wallet_client` injects a controlled fake. These controls instead let the application
compose its own provider so the router, the service and the adapter are exercised together. They
make no network or provider call; every wallet here is authored local fixture data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import helpers

from edge_os_api.core.settings import ConfigError, load_settings
from edge_os_api.main import create_app
from edge_os_api.wallet_setup.adapter import FixtureWalletProvider, UnavailableWalletProvider, build_wallet_provider

NETWORK = 10143


def _prepare_body(strategy_id: str, revision_id: str, key: str) -> dict:
    return {"network_id": NETWORK, "strategy_id": strategy_id, "strategy_revision_id": revision_id,
            "request_key": key}


def _app_client(settings, provider) -> TestClient:
    app = create_app(settings)
    app.state.wallet_provider = provider
    return TestClient(app)


def test_local_fixture_confirms_and_survives_process_restart(wallet_client, settings, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    with _app_client(settings, FixtureWalletProvider()) as client:
        prepared = client.post("/v1/wallet-setup/agents/agent-fixture/prepare",
                               json=_prepare_body(strategy_id, revision_id, "fixture-key"), headers=owner_a)
        assert prepared.status_code == 200, prepared.text
        confirmed = client.post("/v1/wallet-setup/agents/agent-fixture/dispatch", headers=owner_a)
        assert confirmed.status_code == 200, confirmed.text
        body = confirmed.json()
        assert body["state"] == "CONFIRMED" and body["wallet_id"].startswith("fixture:")

    # A fresh application and a fresh fixture instance model a restarted local process.
    with _app_client(settings, FixtureWalletProvider()) as restarted:
        reread = restarted.get("/v1/wallet-setup/agents/agent-fixture", headers=owner_a)
        assert reread.status_code == 200 and reread.json()["wallet_id"] == body["wallet_id"]
    assert pg.psql("select count(*) from wallet_setups where agent_id = 'agent-fixture'") == "1"
    assert pg.psql("select count(*) from wallet_setups where wallet_id is not null") == "1"


def test_local_fixture_lost_response_marker_stays_unknown(wallet_client, settings, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    with _app_client(settings, FixtureWalletProvider()) as client:
        client.post("/v1/wallet-setup/agents/agent-lost-fixture-lost-response/prepare",
                    json=_prepare_body(strategy_id, revision_id, "lost-key"), headers=owner_a)
        body = client.post("/v1/wallet-setup/agents/agent-lost-fixture-lost-response/dispatch",
                           headers=owner_a).json()
        assert body["state"] == "UNKNOWN" and body["reason"] == "RESPONSE_LOST"
        resumed = client.post("/v1/wallet-setup/agents/agent-lost-fixture-lost-response/resume",
                              headers=owner_a).json()
        assert resumed["state"] == "UNKNOWN" and resumed["reason"] == "RECONCILE_NO_EXACT_ID"
    assert pg.psql("select count(*) from wallet_setups where wallet_id is not null") == "0"


def test_unavailable_provider_is_fail_closed(wallet_client, settings, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    with _app_client(settings, UnavailableWalletProvider()) as client:
        client.post("/v1/wallet-setup/agents/agent-unavailable/prepare",
                    json=_prepare_body(strategy_id, revision_id, "unavailable-key"), headers=owner_a)
        body = client.post("/v1/wallet-setup/agents/agent-unavailable/dispatch", headers=owner_a).json()
        assert body["state"] == "UNKNOWN" and body["reason"] == "PROVIDER_UNAVAILABLE"
    assert pg.psql("select count(*) from wallet_setups where wallet_id is not null") == "0"


def test_build_wallet_provider_selects_by_mode():
    assert isinstance(build_wallet_provider("fixture"), FixtureWalletProvider)
    assert isinstance(build_wallet_provider("unavailable"), UnavailableWalletProvider)
    assert isinstance(build_wallet_provider("anything-else"), UnavailableWalletProvider)


def test_production_refuses_the_local_fixture(env):
    production = {**env, "EDGE_OS_ENV": "production", "EDGE_OS_PRIVY_APP_ID": "real-app",
                  "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.example.com",
                  "EDGE_OS_WALLET_PROVIDER": "fixture"}
    with pytest.raises(ConfigError, match="wallet_provider"):
        load_settings(production)
    assert load_settings({**production, "EDGE_OS_WALLET_PROVIDER": "unavailable"}).wallet_provider == "unavailable"
