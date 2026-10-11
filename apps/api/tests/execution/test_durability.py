"""Durability and schema isolation for the owned execution tables."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from edge_os_api.admission.service import AdmissionService
from edge_os_api.execution.models import ExecutionBase
from edge_os_api.execution.service import ExecutionService

from admission._builders import AGENT_A, NETWORK, WALLET_A
from execution._builders import frozen_entry_exit
from execution._support import enqueue_entry


def test_records_survive_a_fresh_engine(execution_service, pg, fresh_owner) -> None:
    revision = frozen_entry_exit()
    decision, _approval, _context, result = enqueue_entry(execution_service, fresh_owner, revision)

    engine = create_engine(pg.url, pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    restarted = ExecutionService(factory, AdmissionService(factory))
    try:
        decisions = restarted.retrieve_decisions(fresh_owner)
        queue = restarted.retrieve_queue(
            fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
        assert [item.decision_id for item in decisions] == [decision.decision_id]
        assert [item.action_id for item in queue] == [result.intent.action_id]
    finally:
        engine.dispose()


def test_owned_tables_are_isolated_from_other_schemas(execution_engine) -> None:
    with execution_engine.connect() as connection:
        owned = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'execution_local'"))}
        public = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
        admission = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'admission_local'"))}
    expected = {table.name for table in ExecutionBase.metadata.tables.values()}
    assert owned == expected
    assert not (public & expected)
    assert not (admission & expected)
