"""Owned P22 admission test fixtures.

The shared tests/conftest.py provides the session-scoped `pg` harness
instance (run-labelled PostgreSQL 18). This file creates the owned admission
tables inside that run-labelled database and removes exactly those tables at
the end. No production schema is published by this stage.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from edge_os_api.admission.models import AdmissionBase
from edge_os_api.admission.service import AdmissionService


@pytest.fixture(scope="session")
def admission_engine(pg: object) -> Engine:
    engine = create_engine(pg.url, pool_pre_ping=True, pool_size=10, max_overflow=10,
                           connect_args={"options": "-csearch_path=admission_local,public"})
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS admission_local"))
    AdmissionBase.metadata.create_all(engine)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS admission_local CASCADE"))
        engine.dispose()


@pytest.fixture(scope="session")
def admission_factory(admission_engine: Engine) -> sessionmaker:
    return sessionmaker(admission_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def admission_service(admission_factory: sessionmaker) -> AdmissionService:
    return AdmissionService(admission_factory)


@pytest.fixture
def fresh_owner() -> uuid.UUID:
    return uuid.uuid4()