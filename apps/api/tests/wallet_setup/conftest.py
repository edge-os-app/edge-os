"""Local wallet-setup test harness.

Reuses the repository session fixtures (real run-labelled PostgreSQL, real test signing key and
the real verifier) and the application's own authenticated wallet-setup router. It only points
`app.state.wallet_provider` at a controlled authored fake; it adds no route of its own. The
`wallet_setup_local` tables come from migration 0007, so `create_all` is a safety net for the
local metadata only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

import fake_provider

from edge_os_api.core.database import make_engine
from edge_os_api.main import create_app
from edge_os_api.wallet_setup.persistence import WALLET_SETUP_METADATA


@pytest.fixture(scope="session")
def wallet_schema(settings, migrated):
    """Ensure the local `wallet_setup_local` tables exist in this run's labelled database."""
    engine = make_engine(settings.database_url)
    WALLET_SETUP_METADATA.create_all(engine)
    try:
        yield engine
    finally:
        WALLET_SETUP_METADATA.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def _clean_wallet_state(wallet_schema):
    """Reset only the local wallet-setup tables so each control starts from known rows."""
    with wallet_schema.begin() as connection:
        connection.execute(sql_text("truncate table wallet_setup_denials, wallet_setup_events, wallet_setups"))
    yield


@pytest.fixture(scope="session")
def wallet_app(settings, wallet_schema):
    """The real application, whose own composition mounts the authenticated wallet-setup router."""
    return create_app(settings)


@pytest.fixture
def provider():
    return fake_provider.AuthoredFakeWalletProvider()


@pytest.fixture
def wallet_client(wallet_app, provider):
    """A test-only client on the real app plus the wallet-setup router and the authored fake provider."""
    wallet_app.state.wallet_provider = provider
    with TestClient(wallet_app) as client:
        yield client
