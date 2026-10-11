"""WAL-Q22 top-up invariance: a confirmed deposit leaves existing admission state unchanged.

The control seeds authored admission allowance and reservation rows directly, takes a full-row digest
of the admission schema and the accepted P17 binding, runs a confirmed funding credit, then proves the
admission digest and the binding digest are identical while the funding credit is the only change.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import text as sql_text

from funding import fake_observer
from funding import funding_helpers as h
from edge_os_api.admission.models import AdmissionBase, AllowanceRow, ReservationRow
from edge_os_api.funding import service
from edge_os_api.funding.types import ObservationStatus


def _ensure_admission_tables(engine) -> None:
    with engine.begin() as connection:
        connection.execute(sql_text("CREATE SCHEMA IF NOT EXISTS admission_local"))
    AdmissionBase.metadata.create_all(engine)


def _seed_admission(engine, owner: uuid.UUID) -> None:
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        session.execute(sql_text("truncate table admission_local.admission_allowances, "
                                 "admission_local.admission_reservations"))
        session.add(AllowanceRow(allowance_id=uuid.uuid4(), owner_id=owner, agent_id="agent-a", wallet_id="wallet-a",
                                 network_id="monad:143", asset_id=h.TRADING_ASSET, decimals=6,
                                 approval_id="approval-a", approval_hash="sha256:abc", approved=500000000,
                                 consumed=100000000))
        session.add(ReservationRow(reservation_id=uuid.uuid4(), owner_id=owner, agent_id="agent-a",
                                   wallet_id="wallet-a", network_id="monad:143", action_id="action-x",
                                   operation="ENTRY", review_hash="sha256:review", scope="CAPITAL",
                                   position_id="position-a-1", asset_id=h.TRADING_ASSET, decimals=6, raw=100000000,
                                   state="RESERVED"))
        session.commit()


def _table_digest(engine, schema: str) -> dict[str, tuple[int, str]]:
    with engine.begin() as connection:
        tables = [row[0] for row in connection.execute(sql_text(
            "select table_name from information_schema.tables where table_schema = :schema order by table_name"),
            {"schema": schema})]
        digest: dict[str, tuple[int, str]] = {}
        for table in tables:
            qualified = f"{schema}.{table}"
            count = connection.execute(sql_text(f"select count(*) from {qualified}")).scalar_one()
            rows = connection.execute(sql_text(f"select t::text from {qualified} t")).scalars().all()
            joined = "|".join(sorted(rows))
            digest[table] = (count, hashlib.sha256(joined.encode()).hexdigest())
        return digest


def test_confirmed_deposit_changes_no_admission_or_binding_state(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _ensure_admission_tables(funding_engine)
    h.seed_confirmed_binding(funding_engine, owner)
    _seed_admission(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        h.prepare(session, owner, reference="ref-topup", raw="500000000", decimals=6)

    admission_before = _table_digest(funding_engine, "admission_local")
    binding_before = _table_digest(funding_engine, "public")["wallet_setups"]

    observer = fake_observer.AuthoredFakeDepositObserver([fake_observer.observation(
        wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-topup", status=ObservationStatus.CONFIRMED,
        asset_id=h.TRADING_ASSET, raw="499000000", decimals=6, event_id="0xtopup")])
    with funding_factory() as session:
        results = service.reconcile_funding(session, h.principal(owner), agent_id="agent-a", observer=observer)
    assert results[0].credits and results[0].credits[0].amount.raw == "499000000"

    admission_after = _table_digest(funding_engine, "admission_local")
    binding_after = _table_digest(funding_engine, "public")["wallet_setups"]
    assert admission_after == admission_before
    assert binding_after == binding_before

    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "499000000"


def test_summary_reports_gas_and_trading_separately(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        h.prepare(session, owner, asset_id=h.GAS_ASSET, raw="1000000000000000000", decimals=18, reference="gas-1")
        h.prepare(session, owner, asset_id=h.TRADING_ASSET, raw="500000000", decimals=6, reference="trade-1")
    observer = fake_observer.AuthoredFakeDepositObserver([
        fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="gas-1",
                                  status=ObservationStatus.CONFIRMED, asset_id=h.GAS_ASSET,
                                  raw="900000000000000000", decimals=18, event_id="0xgas"),
        fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="trade-1",
                                  status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET, raw="499000000",
                                  decimals=6, event_id="0xtrade")])
    with funding_factory() as session:
        service.reconcile_funding(session, h.principal(owner), agent_id="agent-a", observer=observer)
        summary = service.wallet_funding_summary(session, h.principal(owner), agent_id="agent-a")
    by_class = {balance.asset_class.value: balance for balance in summary}
    assert by_class["NATIVE_GAS"].available.raw == "900000000000000000"
    assert by_class["TRADING"].available.raw == "499000000"
    assert by_class["NATIVE_GAS"].available.asset_id != by_class["TRADING"].available.asset_id
