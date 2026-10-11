"""Durable stops at the real ExecutionService and RecoveryService boundaries."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from sqlalchemy import select

from edge_os_api.execution.models import QueueRow, SubmissionAttemptRow
from edge_os_api.execution.transport import TransportOutcome

from admission._builders import AGENT_A, NETWORK, POSITION_A, WALLET_A, approval_a, context_a, intent_entry
from execution._builders import frozen_entry_exit
from execution._support import enqueue_entry, entry_inputs, quote, transport
from recovery._support import confirmed_actuals, evidence_for
from stops._support import stop_request


class CountingTransport:
    transport_id = "test-stop-count/1"

    def __init__(self) -> None:
        self.calls = 0

    def submit(self, prepared):
        self.calls += 1
        return TransportOutcome(outcome="CONFIRMED", detail="a stop must prevent this call")


def _load_queue(factory, owner, action_id) -> QueueRow:
    with factory() as session:
        return session.execute(select(QueueRow).where(
            QueueRow.owner_id == owner, QueueRow.action_id == action_id)).scalar_one()


def _tick(execution_service, owner, revision, approval, context, action_id, fixture):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(),
        quote=quote(action_id, revision, "110"), transport=fixture)


def test_queued_action_cannot_bypass_a_new_stop(execution_service, stops_factory, stop_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    assert result.admission_status == "ADMITTED"
    action_id = result.intent.action_id

    # The action is already queued and admitted; the stop is recorded afterwards.
    stop_service.request_stop(fresh_owner, stop_request(position_id="position-1"))

    fixture = CountingTransport()
    tick = _tick(execution_service, fresh_owner, revision, approval, context, action_id, fixture)

    assert tick.status == "REVALIDATION_DENIED"
    assert "STOPPED_NEW_ENTRIES" in (tick.reason or "")
    assert fixture.calls == 0
    assert _load_queue(stops_factory, fresh_owner, action_id).state == "REVALIDATION_DENIED"
    with stops_factory() as session:
        attempts = session.execute(select(SubmissionAttemptRow).where(
            SubmissionAttemptRow.owner_id == fresh_owner,
            SubmissionAttemptRow.action_id == action_id)).scalars().all()
    assert attempts == []


def test_submission_ownership_refuses_a_committed_stop(execution_service, admission_service,
                                                       stop_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, _context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id

    stop_service.request_stop(fresh_owner, stop_request(position_id="position-1"))

    assert admission_service.acquire_submission(fresh_owner, action_id) == "STOPPED_SCOPE"
    # Ownership was not taken and the action stays eligible-but-stopped, not unknown.
    assert admission_service.retrieve_decisions(
        fresh_owner, action_id=action_id)[0].status == "ADMITTED"


def test_stop_does_not_undo_a_submission_owned_action(recovery_service, execution_service,
                                                      admission_service, stops_factory, stop_service,
                                                      fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id

    unknown = _tick(execution_service, fresh_owner, revision, approval, context, action_id,
                    transport("UNKNOWN", action_id=action_id))
    assert unknown.status == "SUBMITTED_UNKNOWN"

    stop_service.request_stop(fresh_owner, stop_request(scope="AGENT_WALLET_NETWORK", position_id=None))

    # The already submission-owned action stays visible with its pending state.
    queue = execution_service.retrieve_queue(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert [item.state for item in queue] == ["SUBMITTED_UNKNOWN"]
    status = execution_service.status(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert status.blocking_reason == "SUBMISSION_UNKNOWN"

    # Recovery reconciles the original reference; the stop never relabels it unsent.
    actual_input, actual_output, actual_gas = confirmed_actuals()
    evidence = evidence_for(stops_factory, fresh_owner, action_id, outcome="CONFIRMED",
                            actual_input=actual_input, actual_output=actual_output, actual_gas=actual_gas)
    recovered = recovery_service.reconcile(fresh_owner, action_id, evidence)

    assert recovered.case.state == "CONFIRMED"
    assert admission_service.retrieve_decisions(fresh_owner, action_id=action_id)[0].status == "CONFIRMED"
    # The durable stop is preserved and not cleared by recovery or monitoring.
    assert len(stop_service.retrieve_stops(fresh_owner)) == 1


def test_successor_approval_does_not_clear_a_stop(admission_service, stop_service, fresh_owner) -> None:
    stop_service.request_stop(
        fresh_owner, stop_request(scope="AGENT_WALLET_NETWORK", position_id=None))
    successor = approval_a(approval_id="approval-a-v4", quote_approved_raw="9999",
                           base_approved_raw="9999")

    denied = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id=POSITION_A), successor, context_a())

    assert denied.status == "DENIED" and "STOPPED_NEW_ENTRIES" in (denied.reason or "")


def test_stop_and_submission_ordering_is_atomic(execution_service, stops_factory, stop_service,
                                                fresh_owner) -> None:
    revision = frozen_entry_exit()
    for _ in range(6):
        owner = uuid.uuid4()
        _decision, approval, context, result = enqueue_entry(execution_service, owner, revision)
        action_id = result.intent.action_id
        fixture = CountingTransport()
        barrier = threading.Barrier(2)
        outcome: dict[str, Any] = {}

        def record_stop() -> None:
            barrier.wait()
            outcome["stop"] = stop_service.request_stop(owner, stop_request(position_id="position-1"))

        def run_tick() -> None:
            barrier.wait()
            outcome["tick"] = _tick(execution_service, owner, revision, approval, context, action_id, fixture)

        threads = [threading.Thread(target=record_stop), threading.Thread(target=run_tick)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # The stop is always durable. Either it won before submission eligibility
        # (zero transport calls) or the action was already submission-owned and
        # completed its own call. Never both.
        assert stop_service.retrieve_stops(owner)
        if fixture.calls == 0:
            assert outcome["tick"].status in {"REVALIDATION_DENIED", "SUBMISSION_NOT_OWNED"}
        else:
            assert fixture.calls == 1 and outcome["tick"].status == "SUBMITTED_CONFIRMED"
