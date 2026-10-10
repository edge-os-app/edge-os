"""Durability: committed records survive a fresh session and a fresh engine
(process restart); a rolled-back transaction leaves no partial rows."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from edge_os_api.admission.models import (
    AdmissionBase,
    DecisionRow,
    ReservationRow,
)
from edge_os_api.admission.service import AdmissionService

from admission._builders import (
    BASE,
    NATIVE,
    QUOTE,
    approval_a,
    context_a,
    intent_entry,
)

OWNER_FIXED = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _fresh_service(pg: object) -> tuple[AdmissionService, object]:
    engine = create_engine(pg.url, pool_pre_ping=True)
    return AdmissionService(sessionmaker(engine, expire_on_commit=False)), engine


def test_committed_records_survive_fresh_engine(pg, admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110")
    admitted = admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    assert admitted.status == "ADMITTED"

    restarted, engine = _fresh_service(pg)
    try:
        decisions = restarted.retrieve_decisions(fresh_owner)
        reservations = restarted.retrieve_reservations(
            fresh_owner, wallet_id="wallet-a", network_id="monad:143")
        summaries = {s.asset_id: s for s in
                     restarted.balances(fresh_owner, agent_id="agent-a", wallet_id="wallet-a", network_id="monad:143")}
        assert len(decisions) == 1 and decisions[0].status == "ADMITTED"
        assert len(reservations) == 5
        assert summaries[QUOTE].remaining_raw == "390"
        assert summaries[BASE].remaining_raw == "990"
        assert summaries[NATIVE].remaining_raw == "48"
    finally:
        engine.dispose()


def test_rollback_leaves_no_partial_rows(admission_engine, admission_factory, fresh_owner) -> None:
    session = admission_factory()
    try:
        deleted = session.execute(text(
            "DELETE FROM admission_reservations WHERE owner_id = :owner"
        ), {"owner": str(fresh_owner)})
        session.execute(text(
            "DELETE FROM admission_decisions WHERE owner_id = :owner"
        ), {"owner": str(fresh_owner)})
        session.commit()
        assert deleted.rowcount == 0  # clean slate

        row = DecisionRow(
            decision_id=uuid.uuid4(), owner_id=fresh_owner, agent_id="agent-a",
            wallet_id="wallet-a", network_id="monad:143", action_id="action-rolled-back",
            review_hash="sha256:" + "c" * 64, operation="ENTRY", status="ADMITTED",
            reason=None, binding={"agent_id": "agent-a"},
        )
        session.add(row)
        reservation = ReservationRow(
            reservation_id=uuid.uuid4(), owner_id=fresh_owner, agent_id="agent-a",
            wallet_id="wallet-a", network_id="monad:143", action_id="action-rolled-back",
            review_hash="sha256:" + "c" * 64, scope="CAPITAL", position_id="",
            asset_id=QUOTE, decimals=0, raw=110, state="RESERVED",
        )
        session.add(reservation)
        session.flush()
        session.rollback()
    finally:
        session.close()

    with admission_engine.connect() as connection:
        decisions = connection.execute(text(
            "SELECT count(*) FROM admission_decisions WHERE owner_id = :owner AND action_id = 'action-rolled-back'"
        ), {"owner": str(fresh_owner)}).scalar_one()
        reservations = connection.execute(text(
            "SELECT count(*) FROM admission_reservations WHERE owner_id = :owner AND action_id = 'action-rolled-back'"
        ), {"owner": str(fresh_owner)}).scalar_one()
    assert decisions == 0
    assert reservations == 0


def test_owned_tables_are_isolated_from_shared_schema(pg, admission_engine, fresh_owner) -> None:
    """Owned tables live in their own schema and never collide with the migrated public schema."""
    with admission_engine.connect() as connection:
        owned = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'admission_local'"
        ))}
        public = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))}
    expected = {table.name for table in AdmissionBase.metadata.tables.values()}
    assert owned == expected
    assert not (public & expected)