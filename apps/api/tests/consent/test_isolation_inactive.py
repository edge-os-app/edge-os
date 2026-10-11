"""Red/green slice: review and adoption never change the accepted modules' state.

Inactive preparation writes only the owned `consent_local` tables. It does not
change holdings, allowances, reservations, claims, pending recovery, stop history,
breach state or another agent, and it cannot reset or raise an existing budget.
"""

from __future__ import annotations

from sqlalchemy import text

from consent import _support as support

from edge_os_api.admission.service import AdmissionService
from edge_os_api.consent.types import AdoptionRequest
from edge_os_api.stops.service import StopService


def _table_stat(connection, schema: str, name: str):
    statement = text(
        f'SELECT count(*) AS n, coalesce(md5(string_agg(q::text, chr(10) ORDER BY q::text)), \'EMPTY\') AS h '
        f'FROM "{schema}"."{name}" q')
    row = connection.execute(statement).one()
    return (row.n, row.h)


def _accepted_fingerprint(engine) -> dict:
    fingerprint = {}
    with engine.connect() as connection:
        for schema in ("admission_local", "stops_local", "funding_local", "execution_local", "recovery_local"):
            names = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"),
                                       {"schema": schema}).scalars()
            for name in names:
                fingerprint[f"{schema}.{name}"] = _table_stat(connection, schema, name)
        for name in ("users", "records", "strategy_revisions", "wallet_setups", "wallet_setup_events",
                     "wallet_setup_denials"):
            fingerprint[f"public.{name}"] = _table_stat(connection, "public", name)
    return fingerprint


def _seed_accepted_state(engine):
    revision_a = support.seed_revision(engine, support.OWNER_A)
    support.seed_wallet_setup(engine, support.OWNER_A, revision_a)
    support.seed_funding_credit(engine, support.OWNER_A, raw="4000")
    action_id = support.seed_allowance_and_unknown_decision(engine, support.OWNER_A)
    support.seed_stop(engine, support.OWNER_A, mode="HALT_ALL_SWAPS")
    # A second agent's independent wallet state, to prove consent never touches another agent.
    revision_b = support.seed_revision(engine, support.OWNER_B, strategy_id="strategy-consent-b")
    support.seed_wallet_setup(engine, support.OWNER_B, revision_b, agent_id="agent-b", wallet_id="wallet-b")
    return revision_a, action_id


def test_review_and_adoption_leave_every_accepted_module_unchanged(consent_engine, consent_service, consent_factory) -> None:
    revision, action_id = _seed_accepted_state(consent_engine)
    before = _accepted_fingerprint(consent_engine)

    view = consent_service.review(support.OWNER_A, support.review_request(revision))
    consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                           expected_review_hash=view.review_hash))
    after = _accepted_fingerprint(consent_engine)

    assert before == after


def test_consent_does_not_reset_a_budget_and_keeps_the_stop_and_unknown_action(consent_engine, consent_service, consent_factory) -> None:
    revision, action_id = _seed_accepted_state(consent_engine)
    admission = AdmissionService(consent_factory)

    balances_before = {item.asset_id: item for item in admission.balances(support.OWNER_A)}
    decisions_before = {item.action_id: item.status for item in admission.retrieve_decisions(support.OWNER_A)}

    view = consent_service.review(support.OWNER_A, support.review_request(revision))
    consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                           expected_review_hash=view.review_hash))

    balances_after = {item.asset_id: item for item in admission.balances(support.OWNER_A)}
    decisions_after = {item.action_id: item.status for item in admission.retrieve_decisions(support.OWNER_A)}

    assert balances_after.keys() == balances_before.keys()
    for asset_id, before in balances_before.items():
        assert balances_after[asset_id].approved_raw == before.approved_raw
        assert balances_after[asset_id].consumed_raw == before.consumed_raw
        assert balances_after[asset_id].remaining_raw == before.remaining_raw
    assert decisions_after == decisions_before
    assert decisions_after[action_id] == "SUBMISSION_UNKNOWN"

    stops = StopService(consent_factory).retrieve_stops(support.OWNER_A)
    assert len(stops) == 1 and stops[0].mode == "HALT_ALL_SWAPS"
