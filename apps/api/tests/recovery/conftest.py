"""Owned P24 recovery test fixtures.

The shared tests/conftest.py provides the session-scoped `pg` harness instance
(run-labelled PostgreSQL 18). This file creates the owned `recovery_local`
schema plus the accepted P22 `admission_local` and P23 `execution_local` schemas
inside that run-labelled database and removes exactly those schemas at the end.
The migrated `public` schema is untouched.
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

# Controlled clock: one minute after the authored decision time.
NOW = dt.datetime(2026, 1, 1, 0, 16, tzinfo=dt.timezone.utc)

SEARCH_PATH = "recovery_local,execution_local,admission_local,public"


def build_recovery_engine(pg: object) -> Engine:
    engine = create_engine(pg.url, pool_pre_ping=True, pool_size=10, max_overflow=10,
                           connect_args={"options": f"-csearch_path={SEARCH_PATH}"})
    with engine.begin() as connection:
        for schema in ("admission_local", "execution_local", "recovery_local"):
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    AdmissionBase.metadata.create_all(engine)
    ExecutionBase.metadata.create_all(engine)
    RecoveryBase.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="session")
def recovery_engine(pg: object) -> Engine:
    engine = build_recovery_engine(pg)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            for schema in ("recovery_local", "execution_local", "admission_local"):
                connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        engine.dispose()


@pytest.fixture(scope="session")
def recovery_factory(recovery_engine: Engine) -> sessionmaker:
    return sessionmaker(recovery_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def admission_service(recovery_factory: sessionmaker) -> AdmissionService:
    return AdmissionService(recovery_factory)


@pytest.fixture(scope="session")
def execution_service(recovery_factory: sessionmaker, admission_service: AdmissionService) -> ExecutionService:
    return ExecutionService(recovery_factory, admission_service, clock=lambda: NOW)


@pytest.fixture(scope="session")
def recovery_service(recovery_factory: sessionmaker, admission_service: AdmissionService,
                     execution_service: ExecutionService) -> RecoveryService:
    return RecoveryService(recovery_factory, admission_service, execution_service, clock=lambda: NOW)


@pytest.fixture
def fresh_owner() -> uuid.UUID:
    return uuid.uuid4()
