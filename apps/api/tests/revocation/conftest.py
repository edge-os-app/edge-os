"""P30 local revocation test harness.

Reuses the repository session fixtures (real run-labelled PostgreSQL). It creates
the owned `revocation_local` schema plus the accepted `admission_local` and
`stops_local` schemas, so the removal tests can compose the accepted admission
and stop modules and prove the removal package leaves their rows unchanged. The
migrated `public` schema and its wallet-setup tables stay in place. The owned
schemas are dropped at the end of the session. This is a scoped local harness,
not production wiring and not a full verify-edge-os pass.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.models import AdmissionBase
from edge_os_api.consent.records import ConsentBase
from edge_os_api.funding.persistence import FundingBase
from edge_os_api.revocation.records import RevocationBase
from edge_os_api.revocation.removal_service import RemovalService
from edge_os_api.stops.models import StopBase
from edge_os_api.wallet_setup.persistence import WALLET_SETUP_METADATA

# Controlled clock: one minute after the authored request time.
NOW = dt.datetime(2026, 1, 1, 0, 16, tzinfo=dt.timezone.utc)

OWNED_SCHEMAS = ("revocation_local", "admission_local", "stops_local", "funding_local", "consent_local")
OWNED_BASES = (RevocationBase, AdmissionBase, StopBase, FundingBase, ConsentBase)
REVOCATION_TABLES = ("removal_requests", "removal_observations", "removal_states")
WALLET_SETUP_TABLES = ("wallet_setups", "wallet_setup_events", "wallet_setup_denials")


def _tables(connection, schema: str) -> list[str]:
    return list(connection.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"), {"schema": schema}).scalars())


def _truncate(connection, schema: str, names) -> None:
    present = [name for name in names if name in _tables(connection, schema)]
    if present:
        connection.execute(text("TRUNCATE TABLE " + ", ".join(f'"{schema}"."{name}"' for name in present) + " CASCADE"))


@pytest.fixture(scope="session")
def revocation_engine(migrated):
    engine = create_engine(migrated.url, pool_pre_ping=True, pool_size=10, max_overflow=10)
    with engine.begin() as connection:
        for schema in OWNED_SCHEMAS:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    for base in OWNED_BASES:
        base.metadata.create_all(engine)
    WALLET_SETUP_METADATA.create_all(engine)  # idempotent over the migrated 0007 tables
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            for schema in OWNED_SCHEMAS:
                connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        engine.dispose()


@pytest.fixture(scope="session")
def revocation_factory(revocation_engine) -> sessionmaker:
    return sessionmaker(revocation_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _reset_state(revocation_engine):
    with revocation_engine.begin() as connection:
        _truncate(connection, "revocation_local", REVOCATION_TABLES)
        for schema in ("admission_local", "stops_local", "funding_local", "consent_local"):
            _truncate(connection, schema, _tables(connection, schema))
        _truncate(connection, "public", WALLET_SETUP_TABLES)
    yield


@pytest.fixture
def removal_service(revocation_factory) -> RemovalService:
    return RemovalService(revocation_factory, clock=lambda: NOW)


@pytest.fixture
def session(revocation_engine):
    with Session(revocation_engine) as active:
        yield active
