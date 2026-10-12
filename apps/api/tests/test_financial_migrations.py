"""Forward migrations ship every accepted financial table (funding, admission, execution, recovery,
stops, consent, removal) through the normal Alembic path, on a fresh database and on an upgraded
pre-financial database, without changing saved rows, keys, precision or uniqueness."""

from __future__ import annotations

import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import harness
from edge_os_api.admission.models import AdmissionBase
from edge_os_api.consent.records import ConsentBase
from edge_os_api.execution.models import ExecutionBase
from edge_os_api.funding.persistence import FundingBase
from edge_os_api.recovery.models import RecoveryBase
from edge_os_api.revocation.records import RevocationBase
from edge_os_api.stops.models import StopBase

FINANCIAL_BASES = (FundingBase, AdmissionBase, ExecutionBase, RecoveryBase, StopBase, ConsentBase, RevocationBase)
PRE_FINANCIAL_HEAD = "0007"


def alembic(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([harness.api_python(), "-m", "alembic", *args], cwd=harness.API_DIR, env=env,
                          capture_output=True, text=True, timeout=120)


def test_financial_tables_are_migrated(client, settings):
    engine = create_engine(settings.database_url)
    try:
        inspector = inspect(engine)
        for base in FINANCIAL_BASES:
            for table in base.metadata.tables.values():
                assert inspector.has_table(table.name, schema=table.schema), f"{table.schema}.{table.name}"
    finally:
        engine.dispose()


def test_migrated_schema_matches_every_registered_model(env, migrated):
    """`alembic check` compares the migrated database with every registered metadata."""
    result = alembic(env, "check")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="module")
def upgrade_database(pg, env):
    """A separate run-owned database inside the run-labelled container, first migrated only to 0007."""
    name = f"edge_os_test_{pg.run_id}_upg"
    pg.psql(f"CREATE DATABASE {name}")
    url = pg.url.rsplit("/", 1)[0] + "/" + name
    upgrade_env = {**env, "EDGE_OS_DATABASE_URL": url}
    try:
        yield url, upgrade_env
    finally:
        pg.psql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def test_upgrade_from_pre_financial_head_preserves_saved_rows(upgrade_database):
    url, upgrade_env = upgrade_database
    first = alembic(upgrade_env, "upgrade", PRE_FINANCIAL_HEAD)
    assert first.returncode == 0, first.stderr
    owner, record = uuid.uuid4(), uuid.uuid4()
    setup = uuid.uuid4()
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, privy_did) VALUES (:id, 'did:privy:upgrade-owner')"),
                               {"id": owner})
            connection.execute(text(
                "INSERT INTO records (record_id, owner_id, record_type, schema_version, operation_id, created_at, content)"
                " VALUES (:rid, :owner, 'ResearchIntake', 'p02.intake/1', :op, now(), CAST(:content AS jsonb))"),
                {"rid": record, "owner": owner, "op": uuid.uuid4(), "content": '{"text": "keep me exactly"}'})
            connection.execute(text(
                "INSERT INTO wallet_setups (setup_id, owner_id, agent_id, network_id, strategy_id, strategy_revision_id,"
                " content_sha256, manifest_sha256, state, request_key, wallet_id, created_at, updated_at)"
                " VALUES (:sid, :owner, 'agent-upg', 10143, 'strategy-upg', :rev, 'c', 'm', 'CONFIRMED', 'k',"
                " 'fixture:wallet', now(), now())"), {"sid": setup, "owner": owner, "rev": uuid.uuid4()})
            before = connection.execute(text(
                "SELECT record_id, owner_id, content::text, seq FROM records ORDER BY seq")).all()
            setups_before = connection.execute(text("SELECT * FROM wallet_setups ORDER BY setup_id")).all()

        upgraded = alembic(upgrade_env, "upgrade", "head")
        assert upgraded.returncode == 0, upgraded.stderr
        repeated = alembic(upgrade_env, "upgrade", "head")  # a second upgrade is a no-op, never a failure
        assert repeated.returncode == 0, repeated.stderr

        inspector = inspect(engine)
        for base in FINANCIAL_BASES:
            for table in base.metadata.tables.values():
                assert inspector.has_table(table.name, schema=table.schema), f"{table.schema}.{table.name}"
        with engine.connect() as connection:
            after = connection.execute(text(
                "SELECT record_id, owner_id, content::text, seq FROM records ORDER BY seq")).all()
            setups_after = connection.execute(text("SELECT * FROM wallet_setups ORDER BY setup_id")).all()
        assert after == before
        assert setups_after == setups_before
        assert after[0][2] == '{"text": "keep me exactly"}'
    finally:
        engine.dispose()


def test_migrated_amounts_keep_exact_78_digit_precision_and_once_only_credit(settings):
    engine = create_engine(settings.database_url)
    raw = "9" * 78
    owner = uuid.uuid4()
    values = {"credit": uuid.uuid4(), "owner": owner, "raw": raw, "flow": uuid.uuid4(), "obs": uuid.uuid4()}
    insert = text(
        "INSERT INTO funding_local.funding_credits (credit_id, owner_id, agent_id, wallet_id, network_id, asset_id,"
        " actual_raw, decimals, event_id, flow_id, observation_id, created_at)"
        " VALUES (:credit, :owner, 'agent-m', 'wallet-m', 10143, 'monad-testnet:10143/native', CAST(:raw AS numeric),"
        " 18, 'event-m', :flow, :obs, now())")
    try:
        with engine.begin() as connection:
            connection.execute(insert, values)
            stored = connection.execute(text(
                "SELECT actual_raw::text FROM funding_local.funding_credits WHERE credit_id = :credit"),
                {"credit": values["credit"]}).scalar_one()
        assert stored == raw
        with pytest.raises(IntegrityError):  # the once-only credit identity is enforced by the migrated schema
            with engine.begin() as connection:
                connection.execute(insert, {**values, "credit": uuid.uuid4()})
        with pytest.raises(IntegrityError):  # a network outside Monad 143/10143 is refused
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO funding_local.funding_profiles (profile_id, owner_id, agent_id, wallet_id, network_id,"
                    " trading_asset_id, trading_decimals, gas_asset_id, gas_decimals, created_at, updated_at)"
                    " VALUES (:id, :owner, 'agent-n', 'wallet-n', 1, 't', 6, 'g', 18, now(), now())"),
                    {"id": uuid.uuid4(), "owner": owner})
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM funding_local.funding_credits WHERE owner_id = :owner"),
                               {"owner": owner})
        engine.dispose()


def test_downgrade_to_pre_financial_head_removes_only_financial_tables_then_upgrades_again(upgrade_database):
    url, upgrade_env = upgrade_database
    assert alembic(upgrade_env, "upgrade", "head").returncode == 0
    down = alembic(upgrade_env, "downgrade", PRE_FINANCIAL_HEAD)
    assert down.returncode == 0, down.stderr
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        for base in FINANCIAL_BASES:
            for table in base.metadata.tables.values():
                assert not inspector.has_table(table.name, schema=table.schema), f"{table.schema}.{table.name}"
        assert inspector.has_table("wallet_setups") and inspector.has_table("records")
        assert alembic(upgrade_env, "upgrade", "head").returncode == 0
        inspector = inspect(engine)
        assert all(inspector.has_table(t.name, schema=t.schema) for b in FINANCIAL_BASES for t in b.metadata.tables.values())
    finally:
        engine.dispose()
