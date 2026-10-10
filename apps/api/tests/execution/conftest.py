"""Owned P23 execution test fixtures.

The shared tests/conftest.py provides the session-scoped `pg` harness instance
(run-labelled PostgreSQL 18). This file creates the owned `execution_local`
schema plus the accepted P22 `admission_local` schema inside that run-labelled
database and removes exactly those schemas at the end. The migrated `public`
schema is untouched.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from edge_os_api.admission.models import AdmissionBase
from edge_os_api.admission.service import AdmissionService
from edge_os_api.execution.models import ExecutionBase
from edge_os_api.execution.service import ExecutionService


def build_engine(pg: object) -> Engine:
    engine = create_engine(pg.url, pool_pre_ping=True, pool_size=10, max_overflow=10,
                           connect_args={"options": "-csearch_path=execution_local,admission_local,public"})
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS admission_local"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS execution_local"))
    AdmissionBase.metadata.create_all(engine)
    ExecutionBase.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="session")
def execution_engine(pg: object) -> Engine:
    engine = build_engine(pg)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS execution_local CASCADE"))
            connection.execute(text("DROP SCHEMA IF EXISTS admission_local CASCADE"))
        engine.dispose()


@pytest.fixture(scope="session")
def execution_factory(execution_engine: Engine) -> sessionmaker:
    return sessionmaker(execution_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def admission_service(execution_factory: sessionmaker) -> AdmissionService:
    return AdmissionService(execution_factory)


@pytest.fixture(scope="session")
def execution_service(execution_factory: sessionmaker, admission_service: AdmissionService) -> ExecutionService:
    return ExecutionService(execution_factory, admission_service)


@pytest.fixture
def fresh_owner() -> uuid.UUID:
    return uuid.uuid4()
