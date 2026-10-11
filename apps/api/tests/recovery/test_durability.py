"""Durability and schema isolation for the owned recovery tables."""

from __future__ import annotations

from sqlalchemy import text

from edge_os_api.recovery.models import RecoveryBase


def test_owned_tables_are_isolated_from_other_schemas(recovery_engine) -> None:
    with recovery_engine.connect() as connection:
        owned = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'recovery_local'"))}
        public = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
        admission = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'admission_local'"))}
        execution = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'execution_local'"))}
    expected = {table.name for table in RecoveryBase.metadata.tables.values()}
    assert owned == expected
    assert not (public & expected)
    assert not (admission & expected)
    assert not (execution & expected)
