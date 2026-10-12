"""Durable stops across a true process restart, schema isolation and monitoring."""

from __future__ import annotations

from sqlalchemy import text

from edge_os_api.admission.types import AssetAmount
from edge_os_api.stops.models import StopBase

from admission._builders import AGENT_A, BASE, NETWORK, POSITION_A, WALLET_A, approval_a, context_a, intent_entry
from execution._builders import frozen_entry_exit
from execution._support import enqueue_entry, entry_inputs, quote, transport
from recovery._support import evidence_for
from stops._support import restart_probe, stop_request

SCOPE = {"agent_id": AGENT_A, "wallet_id": WALLET_A, "network_id": NETWORK}


def _tick(execution_service, owner, revision, approval, context, action_id, fixture):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(),
        quote=quote(action_id, revision, "110"), transport=fixture)


def test_owned_tables_are_isolated_from_other_schemas(stops_engine) -> None:
    with stops_engine.connect() as connection:
        owned = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'stops_local'"))}
        public = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
        admission = {row[0] for row in connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'admission_local'"))}
    expected = {table.name for table in StopBase.metadata.tables.values()}
    assert owned == expected
    assert not (public & expected)
    assert not (admission & expected)


def test_stop_denies_a_scoped_entry_across_a_true_process_restart(stop_service, pg, fresh_owner) -> None:
    stop_service.request_stop(fresh_owner, stop_request(position_id=POSITION_A))

    probe = restart_probe(
        pg.url, str(fresh_owner), SCOPE,
        intent=intent_entry(position_id=POSITION_A), approval=approval_a(), context=context_a())

    assert len(probe["stop_ids"]) == 1 and probe["modes"] == ["STOP_NEW_ENTRIES"]
    assert probe["decision_status"] == "DENIED"
    assert "STOPPED_NEW_ENTRIES" in probe["decision_reason"]


def test_submission_ownership_guard_survives_a_true_process_restart(
        execution_service, stop_service, pg, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, _context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    stop_service.request_stop(fresh_owner, stop_request(position_id="position-1"))

    probe = restart_probe(pg.url, str(fresh_owner), SCOPE, acquire_action_id=action_id)

    assert probe["acquire"] == "STOPPED_SCOPE"


def test_monitoring_and_reservations_remain_after_a_stop(execution_service, admission_service,
                                                         recovery_service, stop_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    unknown = _tick(execution_service, fresh_owner, revision, approval, context, action_id,
                    transport("UNKNOWN", action_id=action_id))
    assert unknown.status == "SUBMITTED_UNKNOWN"

    stop_service.request_stop(fresh_owner, stop_request(scope="AGENT_WALLET_NETWORK", position_id=None))

    # Unknown reservations are retained, not released by the stop.
    reservations = admission_service.retrieve_reservations(
        fresh_owner, wallet_id=WALLET_A, network_id=NETWORK)
    assert len(reservations) == 4

    # Recovery monitoring is still available and shows the retained claim.
    case = recovery_service.status(fresh_owner, action_id)
    assert case.state == "UNKNOWN" and case.claim_held is True
    assert [item.action_id for item in recovery_service.list_cases(fresh_owner)] == [action_id]

    # The queue shows the delayed/blocking state after the stop.
    status = execution_service.status(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert status.blocking_reason == "SUBMISSION_UNKNOWN"


def test_a_stop_does_not_clear_a_retained_breach(execution_service, admission_service, stops_factory,
                                                 recovery_service, stop_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    overfill = _tick(execution_service, fresh_owner, revision, approval, context, action_id,
                     transport("ACCEPT", action_id=action_id,
                               actual_output=AssetAmount(asset_id=BASE, raw="1001", decimals=0)))
    assert overfill.status == "BREACHED"

    stop_service.request_stop(fresh_owner, stop_request(scope="AGENT_WALLET_NETWORK", position_id=None))

    assert admission_service.retrieve_decisions(fresh_owner, action_id=action_id)[0].status == "BREACHED"
    blocked = recovery_service.reconcile(
        fresh_owner, action_id, evidence_for(stops_factory, fresh_owner, action_id, outcome="CONFIRMED"))
    assert blocked.applied is False
    assert admission_service.retrieve_decisions(fresh_owner, action_id=action_id)[0].status == "BREACHED"
