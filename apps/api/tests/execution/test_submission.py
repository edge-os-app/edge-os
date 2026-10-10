"""Fixture submission outcomes, unknown-outcome blocking and status reporting."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from edge_os_api.execution.models import ClaimRow, SubmissionAttemptRow

from admission._builders import AGENT_A, NETWORK, WALLET_A
from execution._builders import frozen_entry_exit
from execution._support import enqueue_entry, transport


def _tick(execution_service, owner, revision, approval, context, fixture):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, transport=fixture)


def _active_claims(engine, owner) -> int:
    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT count(*) FROM execution_claims WHERE owner_id = :owner AND released_at IS NULL"),
            {"owner": str(owner)}).scalar_one()


def test_confirmed_submission_reconciles_and_releases_claim(
        execution_service, admission_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)

    tick = _tick(execution_service, fresh_owner, revision, approval, context,
                 transport("ACCEPT", action_id=result.intent.action_id))

    assert tick.status == "SUBMITTED_CONFIRMED"
    assert tick.evidence is not None and tick.evidence.outcome == "CONFIRMED"
    assert admission_service.retrieve_decisions(fresh_owner, action_id=result.intent.action_id)[0].status == "CONFIRMED"
    assert _active_claims(execution_engine, fresh_owner) == 0


def test_definitely_unsent_denial_consumes_no_attempt(execution_service, admission_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)

    tick = _tick(execution_service, fresh_owner, revision, approval, context,
                 transport("DENY", action_id=result.intent.action_id))

    assert tick.status == "DENIED_UNSENT"
    assert admission_service.retrieve_decisions(fresh_owner, action_id=result.intent.action_id)[0].status == "DENIED"
    assert admission_service.retrieve_reservations(
        fresh_owner, wallet_id=WALLET_A, network_id=NETWORK) == []
    assert _active_claims(execution_engine, fresh_owner) == 0


def test_unknown_outcome_retains_claim_and_blocks_status(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)

    tick = _tick(execution_service, fresh_owner, revision, approval, context,
                 transport("UNKNOWN", action_id=result.intent.action_id))
    assert tick.status == "SUBMITTED_UNKNOWN"
    assert _active_claims(execution_engine, fresh_owner) == 1

    blocked = _tick(execution_service, fresh_owner, revision, approval, context, transport("ACCEPT"))
    assert blocked.status == "BLOCKED_UNKNOWN"

    status = execution_service.status(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert status.blocking_reason == "SUBMISSION_UNKNOWN"
    assert status.last_attempt_at is not None
    assert status.last_input_at is not None
    assert status.next_scheduled_at is not None
    blocked_entry = next(item for item in status.queue if item.action_id == result.intent.action_id)
    assert blocked_entry.state == "SUBMITTED_UNKNOWN"
    assert blocked_entry.delayed_exit is False
    assert blocked_entry.waiting_seconds >= 0


def test_lost_acknowledgement_is_submission_possible(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)

    tick = _tick(execution_service, fresh_owner, revision, approval, context,
                 transport("UNKNOWN", action_id=result.intent.action_id, lose_acknowledgement=True))

    assert tick.status == "SUBMITTED_UNKNOWN"
    with execution_engine.connect() as connection:
        outcome = connection.execute(text(
            "SELECT outcome FROM execution_submission_attempts WHERE owner_id = :owner AND action_id = :action"),
            {"owner": str(fresh_owner), "action": result.intent.action_id}).scalar_one()
    assert outcome == "SUBMISSION_POSSIBLE"
    assert _active_claims(execution_engine, fresh_owner) == 1


def test_in_flight_attempt_after_restart_blocks_a_duplicate(
        execution_service, execution_factory, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)

    # Simulate a crash between persisting the in-flight attempt and completing it.
    with execution_factory() as session:
        session.add(ClaimRow(
            claim_id=uuid.uuid4(), owner_id=fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A,
            network_id=NETWORK, queue_id=result.queue_entry.queue_id, action_id=result.intent.action_id,
            state="ACTIVE"))
        session.add(SubmissionAttemptRow(
            attempt_id=uuid.uuid4(), owner_id=fresh_owner, queue_id=result.queue_entry.queue_id,
            action_id=result.intent.action_id, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
            transport_id="local-fixture/1", payload_hash=result.intent.payload_hash, state="IN_FLIGHT",
            content={}, completed_at=None))
        session.commit()

    tick = _tick(execution_service, fresh_owner, revision, approval, context,
                 transport("ACCEPT", action_id=result.intent.action_id))
    assert tick.status == "BLOCKED_UNKNOWN"
    with execution_engine.connect() as connection:
        attempts = connection.execute(text(
            "SELECT count(*) FROM execution_submission_attempts WHERE owner_id = :owner"),
            {"owner": str(fresh_owner)}).scalar_one()
    assert attempts == 1
