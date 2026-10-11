"""Local funding test harness.

Reuses the repository session fixtures (real run-labelled PostgreSQL, real test signing key and the
real verifier). It creates the owned `funding_local` tables for the session and the accepted P17
`wallet_setup` tables only for the duration of each test, plus a test-only router. It does not modify
the shared conftest, the shared models, the production router or any migration.

The P17 tables are created in the default `public` schema (as the accepted P17 harness does), so they
are created and dropped around each test. That keeps the migrated `public` schema unchanged for other
tests, including the migration-head check.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text as sql_text

from funding import fake_observer, funding_routes

from edge_os_api.funding.persistence import FundingBase
from edge_os_api.main import create_app
from edge_os_api.wallet_setup.persistence import WALLET_SETUP_METADATA


@pytest.fixture(scope="session")
def funding_engine(pg):
    """Create the owned `funding_local` tables in this run's database for the whole session."""
    engine = create_engine(pg.url, pool_pre_ping=True, pool_size=10, max_overflow=10)
    with engine.begin() as connection:
        connection.execute(sql_text("CREATE SCHEMA IF NOT EXISTS funding_local"))
    FundingBase.metadata.create_all(engine)  # schema-qualified: funding_local
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(sql_text("DROP SCHEMA IF EXISTS funding_local CASCADE"))
        engine.dispose()


@pytest.fixture(scope="session")
def funding_factory(funding_engine):
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(funding_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _funding_state(funding_engine):
    """Add the accepted P17 binding table for this test, reset local rows, then remove the P17 table.

    The P17 table is created and dropped around each test so the migrated `public` schema stays clean
    for the rest of the session.
    """
    WALLET_SETUP_METADATA.create_all(funding_engine)
    with funding_engine.begin() as connection:
        connection.execute(sql_text(
            "truncate table funding_local.funding_denials, funding_local.funding_credits, "
            "funding_local.funding_observations, funding_local.funding_flows, funding_local.funding_profiles, "
            "public.wallet_setups, public.wallet_setup_events, public.wallet_setup_denials"))
    try:
        yield
    finally:
        WALLET_SETUP_METADATA.drop_all(funding_engine)


@pytest.fixture(scope="session")
def funding_app(settings, funding_engine):
    app = create_app(settings)
    app.include_router(funding_routes.build_funding_router())
    return app


@pytest.fixture
def observer():
    return fake_observer.AuthoredFakeDepositObserver()


@pytest.fixture
def funding_client(funding_app, observer):
    """A test-only client on the real app plus the funding router and the authored fake observer."""
    funding_app.state.funding_observer = observer
    with TestClient(funding_app) as client:
        yield client


@pytest.fixture
def fresh_owner() -> uuid.UUID:
    return uuid.uuid4()
