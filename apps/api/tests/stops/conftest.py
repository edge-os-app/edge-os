"""Owned P25 scoped-stop test fixtures.

The shared tests/conftest.py provides the session-scoped `pg` harness instance
(run-labelled PostgreSQL 18). This file creates the owned `stops_local` schema
plus the accepted P22 `admission_local`, P23 `execution_local` and P24
`recovery_local` schemas inside that run-labelled database and removes exactly
those schemas at the end. The migrated `public` schema is untouched.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from edge_os_api.admission.models import AdmissionBase
from edge_os_api.admission.service import AdmissionService
from edge_os_api.execution.models import ExecutionBase
from edge_os_api.execution.service import ExecutionService
from edge_os_api.recovery.models import RecoveryBase
from edge_os_api.recovery.service import RecoveryService
from edge_os_api.stops.models import StopBase
from edge_os_api.stops.service import StopService

# Controlled clock: one minute after the authored decision time.
NOW = dt.datetime(2026, 1, 1, 0, 16, tzinfo=dt.timezone.utc)

SEARCH_PATH = "stops_local,recovery_local,execution_local,admission_local,public"
OWNED_SCHEMAS = ("stops_local", "recovery_local", "execution_local", "admission_local")


def build_stops_engine(pg: object) -> Engine:
    engine = create_engine(pg.url, pool_pre_ping=True, pool_size=10, max_overflow=10,
                           connect_args={"options": f"-csearch_path={SEARCH_PATH}"})
    with engine.begin() as connection:
        for schema in OWNED_SCHEMAS:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    AdmissionBase.metadata.create_all(engine)
    ExecutionBase.metadata.create_all(engine)
    RecoveryBase.metadata.create_all(engine)
    StopBase.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="session")
def stops_engine(migrated: object) -> Engine:
    pg = migrated  # migration 0008 creates these tables first; create_all is a no-op safety net
    engine = build_stops_engine(pg)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            for schema in OWNED_SCHEMAS:
                connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        engine.dispose()


@pytest.fixture(scope="session")
def stops_factory(stops_engine: Engine) -> sessionmaker:
    return sessionmaker(stops_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def stop_service(stops_factory: sessionmaker) -> StopService:
    return StopService(stops_factory, clock=lambda: NOW)


@pytest.fixture(scope="session")
def admission_service(stops_factory: sessionmaker, stop_service: StopService) -> AdmissionService:
    return AdmissionService(stops_factory, stops=stop_service)


@pytest.fixture(scope="session")
def execution_service(stops_factory: sessionmaker, admission_service: AdmissionService,
                      stop_service: StopService) -> ExecutionService:
    return ExecutionService(stops_factory, admission_service, stops=stop_service, clock=lambda: NOW)


@pytest.fixture(scope="session")
def recovery_service(stops_factory: sessionmaker, admission_service: AdmissionService,
                     execution_service: ExecutionService) -> RecoveryService:
    return RecoveryService(stops_factory, admission_service, execution_service, clock=lambda: NOW)


@pytest.fixture
def fresh_owner() -> uuid.UUID:
    return uuid.uuid4()
