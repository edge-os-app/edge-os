"""Fixture submission outcomes, unknown-outcome blocking and status reporting."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from edge_os_api.admission.service import AdmissionService
from edge_os_api.admission.types import ActionReceipt, AssetAmount
from edge_os_api.execution.models import ClaimRow, SubmissionAttemptRow
from edge_os_api.execution.service import ExecutionService
from edge_os_api.execution.transport import TransportOutcome

from admission._builders import AGENT_A, BASE, NETWORK, WALLET_A, approval_a, context_a, intent_entry
from execution._builders import frozen_entry_exit
from execution._support import entry_inputs, enqueue_entry, quote, transport
from execution.conftest import NOW


def _tick(execution_service, owner, revision, approval, context, fixture):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(), quote=quote("110"), transport=fixture)


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


def test_rejected_settlement_breach_is_retained_not_reported(
        execution_service, admission_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)

    # The fixture reports a confirmed swap that overfills the adopted sell ceiling.
    overfill = transport("ACCEPT", action_id=result.intent.action_id,
                         actual_output=AssetAmount(asset_id=BASE, raw="1001", decimals=0))
    tick = _tick(execution_service, fresh_owner, revision, approval, context, overfill)

    assert tick.status == "BREACHED"
    saved = admission_service.retrieve_decisions(fresh_owner, action_id=result.intent.action_id)[0]
    assert saved.status == "BREACHED"
    assert _active_claims(execution_engine, fresh_owner) == 1

    status = execution_service.status(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert (status.blocking_reason or "").startswith("BREACHED")

    # A breached wallet cannot submit a next economic action.
    blocked = _tick(execution_service, fresh_owner, revision, approval, context, transport("ACCEPT"))
    assert blocked.status == "BLOCKED_UNKNOWN"


def test_claim_wins_cancellation_is_refused_and_capital_is_not_reused(
        execution_service, admission_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    observed = {}

    class CancellingTransport:
        """A concurrent P22 cancellation lands after the durable P23 ownership transition."""

        transport_id = "test-cancel-before-effect/1"

        def submit(self, prepared):
            refused = admission_service.cancel(fresh_owner, prepared.action_id)
            observed["cancel_status"] = refused.decision_status
            observed["cancel_reason"] = refused.reason
            competing = admission_service.admit_and_reserve(
                fresh_owner, intent_entry(position_id="compete-1"), approval_a(), context_a())
            observed["competing"] = competing.status
            observed["competing_reason"] = competing.reason
            return TransportOutcome(outcome="CONFIRMED", detail="effect after refused cancellation")

    tick = _tick(execution_service, fresh_owner, revision, approval, context, CancellingTransport())

    # The ownership transition won: cancellation is refused and no capital is reused.
    assert tick.status == "SUBMITTED_CONFIRMED"
    assert observed["cancel_status"] == "SUBMISSION_UNKNOWN"
    assert observed["cancel_reason"] == "NOT_CANCELLABLE_AFTER_SUBMISSION"
    assert observed["competing"] == "DENIED"
    assert observed["competing_reason"] == "UNRESOLVED_PRIOR_ACTION"
    saved = admission_service.retrieve_decisions(fresh_owner, action_id=action_id)[0]
    assert saved.status == "CONFIRMED"
    assert _active_claims(execution_engine, fresh_owner) == 0


def test_cancellation_before_the_ownership_transition_makes_no_call(
        execution_factory, admission_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    service = ExecutionService(execution_factory, admission_service, clock=lambda: NOW)
    _decision, approval, context, result = enqueue_entry(service, fresh_owner, revision)
    action_id = result.intent.action_id

    class CancellingAdmission(AdmissionService):
        """A cancellation wins the ownership transition race by committing first."""

        def __init__(self) -> None:
            super().__init__(execution_factory)
            self._done = False

        def acquire_submission(self, owner, called_action_id):
            if not self._done:
                self._done = True
                self.cancel(owner, called_action_id)
            return super().acquire_submission(owner, called_action_id)

    class CountingTransport:
        transport_id = "test-count/1"

        def __init__(self) -> None:
            self.calls = 0

        def submit(self, prepared):
            self.calls += 1
            return TransportOutcome(outcome="CONFIRMED", detail="must not be called")

    fixture = CountingTransport()
    racing = ExecutionService(execution_factory, CancellingAdmission(), clock=lambda: NOW)
    tick = racing.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(), quote=quote("110"), transport=fixture)

    assert tick.status == "SUBMISSION_NOT_OWNED"
    assert fixture.calls == 0
    assert admission_service.retrieve_decisions(fresh_owner, action_id=action_id)[0].status == "CANCELLED"


def test_preexisting_unknown_blocks_ownership_and_writes_no_extra_receipt(
        execution_factory, admission_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    service = ExecutionService(execution_factory, admission_service, clock=lambda: NOW)
    _decision, approval, context, result = enqueue_entry(service, fresh_owner, revision)
    action_id = result.intent.action_id

    class UnknownFirstAdmission(AdmissionService):
        """An independent actor reconciles the action to unknown before our acquire."""

        def __init__(self) -> None:
            super().__init__(execution_factory)
            self._done = False

        def acquire_submission(self, owner, called_action_id):
            if not self._done:
                self._done = True
                super().reconcile(owner, called_action_id, ActionReceipt(
                    action_id=called_action_id, binding=result.intent.binding, outcome="SUBMISSION_UNKNOWN"))
            return super().acquire_submission(owner, called_action_id)

    class CountingTransport:
        transport_id = "test-count-unknown/1"

        def __init__(self) -> None:
            self.calls = 0

        def submit(self, prepared):
            self.calls += 1
            return TransportOutcome(outcome="CONFIRMED", detail="must not be called")

    fixture = CountingTransport()
    racing = ExecutionService(execution_factory, UnknownFirstAdmission(), clock=lambda: NOW)
    tick = racing.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(), quote=quote("110"), transport=fixture)

    assert tick.status == "SUBMISSION_NOT_OWNED"
    assert fixture.calls == 0
    receipts = admission_service.retrieve_receipts(fresh_owner, action_id=action_id)
    assert [item.outcome for item in receipts] == ["SUBMISSION_UNKNOWN"]
