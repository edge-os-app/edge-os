"""P26 inactive-consent test harness.

Reuses the repository session fixtures (real run-labelled PostgreSQL). It creates
the owned `consent_local` tables and, so the review/adopt reads match the accepted
modules, the `admission_local`, `stops_local`, `funding_local`, `execution_local`
and `recovery_local` tables plus the migrated `public` wallet-setup tables. The
owned schemas are dropped at the end of the session; the migrated public schema is
left in place. Nothing here is production wiring.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import pytest

from edge_os_api.admission.models import AdmissionBase
from edge_os_api.admission.service import AdmissionService
from edge_os_api.consent.records import ConsentBase
from edge_os_api.consent.service import ConsentService
from edge_os_api.execution.models import ExecutionBase
from edge_os_api.funding.persistence import FundingBase
from edge_os_api.recovery.models import RecoveryBase
from edge_os_api.stops.models import StopBase
from edge_os_api.stops.service import StopService
from edge_os_api.wallet_setup.persistence import WALLET_SETUP_METADATA

OWNED_SCHEMAS = ("consent_local", "admission_local", "stops_local", "funding_local", "execution_local", "recovery_local")
OWNED_BASES = (ConsentBase, AdmissionBase, StopBase, FundingBase, ExecutionBase, RecoveryBase)
WALLET_SETUP_TABLES = ("wallet_setups", "wallet_setup_events", "wallet_setup_denials")
PUBLIC_SEEDED_TABLES = ("strategy_revisions", "records", "users") + WALLET_SETUP_TABLES
CONSENT_TABLES = ("consent_reviews", "consent_adoptions", "consent_denials")


def _tables(connection, schema: str) -> list[str]:
    return list(connection.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"), {"schema": schema}).scalars())


def _truncate(connection, schema: str, names) -> None:
    present = [name for name in names if name in _tables(connection, schema)]
    if present:
        connection.execute(text("TRUNCATE TABLE " + ", ".join(f'"{schema}"."{name}"' for name in present) + " CASCADE"))


@pytest.fixture(scope="session")
def consent_engine(migrated):
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
def consent_factory(consent_engine) -> sessionmaker:
    return sessionmaker(consent_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _reset_state(consent_engine):
    with consent_engine.begin() as connection:
        _truncate(connection, "consent_local", CONSENT_TABLES)
        for schema in ("admission_local", "stops_local", "funding_local", "execution_local", "recovery_local"):
            _truncate(connection, schema, _tables(connection, schema))
        _truncate(connection, "public", PUBLIC_SEEDED_TABLES)
    yield


@pytest.fixture
def consent_service(consent_factory) -> ConsentService:
    admission = AdmissionService(consent_factory)
    stops = StopService(consent_factory)
    return ConsentService(consent_factory, admission=admission, stops=stops)


@pytest.fixture
def session(consent_engine):
    with Session(consent_engine) as active:
        yield active
