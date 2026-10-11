"""P24 original-action recovery: durable reopen, controlled reconciliation and races."""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from edge_os_api.admission.service import AdmissionService
from edge_os_api.admission.types import AssetAmount
from edge_os_api.execution.service import ExecutionService
from edge_os_api.recovery.service import RecoveryService
from edge_os_api.recovery.types import RecoveryError

from admission._builders import AGENT_A, AGENT_B, BASE, NATIVE, NETWORK, QUOTE, WALLET_A, WALLET_B
from execution._builders import exit_terms, frozen_entry_exit, make_inputs, scoped_context
from execution._support import enqueue_entry, entry_inputs, exit_inputs, open_position, quote
from execution._support import transport as exec_transport
from recovery._support import (
    active_claim,
    confirmed_actuals,
    evidence_for,
    load_intent,
    load_queue,
    open_unknown_entry,
)


def _balances(admission_service, owner):
    return {item.asset_id: item for item in admission_service.balances(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)}


def _confirmed_entry(service, owner, revision):
    """Admit an entry and complete it normally through a confirmed fixture call."""
    _decision, approval, context, result = enqueue_entry(service, owner, revision)
    assert result.admission_status == "ADMITTED", result.admission_reason
    tick = service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(),
        quote=quote(result.intent.action_id, revision, "110"),
        transport=exec_transport("ACCEPT", action_id=result.intent.action_id))
    assert tick.status == "SUBMITTED_CONFIRMED", tick
    return result.intent.action_id


def test_reopen_after_restart_preserves_original_identity(
        recovery_factory, recovery_service, execution_service, pg, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    intent = load_intent(recovery_factory, fresh_owner, action_id)

    engine = create_engine(pg.url, pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    restarted_admission = AdmissionService(factory)
    restarted = RecoveryService(
        factory, restarted_admission, ExecutionService(factory, restarted_admission))
    try:
        view = restarted.status(fresh_owner, action_id)
        assert view.action_id == action_id
        assert (view.agent_id, view.wallet_id, view.network_id) == (
            intent.agent_id, intent.wallet_id, intent.network_id)
        assert view.revision_id == intent.revision_id
        assert view.payload_hash == intent.payload_hash
        assert view.state == "UNKNOWN"
        assert view.claim_held is True
        assert view.decision_status == "SUBMISSION_UNKNOWN"
        assert [case.action_id for case in restarted.list_cases(fresh_owner)] == [action_id]
    finally:
        engine.dispose()

    # The original queue entry and exclusive claim are unchanged by a status read.
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_UNKNOWN"
    assert active_claim(recovery_factory, fresh_owner) is not None


def test_confirmed_reconciles_once_and_duplicate_is_a_noop(
        recovery_factory, recovery_service, admission_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    actual_input, actual_output, actual_gas = confirmed_actuals()

    evidence = evidence_for(recovery_factory, fresh_owner, action_id, outcome="CONFIRMED",
                            actual_input=actual_input, actual_output=actual_output, actual_gas=actual_gas)
    first = recovery_service.reconcile(fresh_owner, action_id, evidence)
    assert first.applied is True and first.duplicate is False
    assert first.case.state == "CONFIRMED"
    assert first.case.queue_state == "SUBMITTED_CONFIRMED"
    assert first.case.claim_held is False
    assert first.decision_status == "CONFIRMED"

    consumed = _balances(admission_service, fresh_owner)
    assert consumed[NATIVE].consumed_raw == "2"
    assert consumed[QUOTE].consumed_raw == "110"
    assert active_claim(recovery_factory, fresh_owner) is None

    second = recovery_service.reconcile(fresh_owner, action_id, evidence)
    assert second.duplicate is True and second.applied is False
    after = _balances(admission_service, fresh_owner)
    assert after[QUOTE].consumed_raw == consumed[QUOTE].consumed_raw
    assert after[NATIVE].consumed_raw == consumed[NATIVE].consumed_raw


def test_foreign_wallet_evidence_is_rejected(
        recovery_factory, recovery_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    intent = load_intent(recovery_factory, fresh_owner, action_id)

    foreign = evidence_for(
        recovery_factory, fresh_owner, action_id, outcome="CONFIRMED",
        actual_input=confirmed_actuals()[0], actual_output=confirmed_actuals()[1],
        actual_gas=confirmed_actuals()[2], binding=_foreign_binding(intent))

    outcome = recovery_service.reconcile(fresh_owner, action_id, foreign)
    assert outcome.applied is False
    assert outcome.case.state == "DISCREPANCY"
    assert "FOREIGN_IDENTITY" in (outcome.case.blocking_reason or "")
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_UNKNOWN"
    assert active_claim(recovery_factory, fresh_owner) is not None


def test_altered_payload_evidence_is_rejected(
        recovery_factory, recovery_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    evidence = evidence_for(
        recovery_factory, fresh_owner, action_id, outcome="CONFIRMED",
        actual_input=confirmed_actuals()[0], actual_output=confirmed_actuals()[1],
        actual_gas=confirmed_actuals()[2], payload_hash="sha256:" + "0" * 64)

    outcome = recovery_service.reconcile(fresh_owner, action_id, evidence)
    assert outcome.applied is False
    assert outcome.case.state == "DISCREPANCY"
    assert "PAYLOAD_MISMATCH" in (outcome.case.blocking_reason or "")
    assert active_claim(recovery_factory, fresh_owner) is not None


def test_unknown_evidence_retains_reservations_and_claim(
        recovery_factory, recovery_service, admission_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    before = _balances(admission_service, fresh_owner)

    evidence = evidence_for(recovery_factory, fresh_owner, action_id, outcome="SUBMISSION_UNKNOWN",
                            detail="fixture still holds no acknowledgement")
    outcome = recovery_service.reconcile(fresh_owner, action_id, evidence)
    assert outcome.case.state == "UNKNOWN"
    assert outcome.case.claim_held is True
    assert outcome.case.decision_status == "SUBMISSION_UNKNOWN"
    assert outcome.case.queue_state == "SUBMITTED_UNKNOWN"
    assert active_claim(recovery_factory, fresh_owner) is not None
    after = _balances(admission_service, fresh_owner)
    assert after[QUOTE].reserved_raw == before[QUOTE].reserved_raw
    assert after[QUOTE].consumed_raw == "0"


def test_proved_prebroadcast_denial_releases_without_consumption(
        recovery_factory, recovery_service, admission_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id

    evidence = evidence_for(recovery_factory, fresh_owner, action_id, outcome="PREBROADCAST_DENIED",
                            detail="fixture proved no send was possible")
    outcome = recovery_service.reconcile(fresh_owner, action_id, evidence)
    assert outcome.case.state == "DENIED_UNSENT"
    assert outcome.decision_status == "DENIED"
    assert outcome.case.queue_state == "DENIED_UNSENT"
    assert active_claim(recovery_factory, fresh_owner) is None
    after = _balances(admission_service, fresh_owner)
    assert after[QUOTE].consumed_raw == "0"
    assert after[QUOTE].reserved_raw == "0"


def test_contradictory_terminal_evidence_is_blocked(
        recovery_factory, recovery_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id = _confirmed_entry(execution_service, fresh_owner, revision)

    contradictory = evidence_for(
        recovery_factory, fresh_owner, action_id, outcome="REVERTED",
        actual_gas=confirmed_actuals()[2])
    outcome = recovery_service.reconcile(fresh_owner, action_id, contradictory)
    assert outcome.applied is False
    assert outcome.case.state == "DISCREPANCY"
    assert "P22_SETTLED_MISMATCH:CONFIRMED" in (outcome.case.blocking_reason or "")
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_CONFIRMED"


def test_replayed_rejection_does_not_escalate(
        recovery_factory, recovery_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id = _confirmed_entry(execution_service, fresh_owner, revision)
    contradictory = evidence_for(
        recovery_factory, fresh_owner, action_id, outcome="REVERTED",
        actual_gas=confirmed_actuals()[2])

    first = recovery_service.reconcile(fresh_owner, action_id, contradictory)
    assert first.case.state == "DISCREPANCY"
    assert first.case.evidence[-1].state == "REJECTED"

    second = recovery_service.reconcile(fresh_owner, action_id, contradictory)
    assert second.applied is False and second.duplicate is True
    assert second.case.state == "DISCREPANCY"
    assert second.case.evidence[-1].state == "REJECTED"
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_CONFIRMED"


def test_replayed_foreign_evidence_stays_rejected(
        recovery_factory, recovery_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    intent = load_intent(recovery_factory, fresh_owner, action_id)
    foreign = evidence_for(
        recovery_factory, fresh_owner, action_id, outcome="CONFIRMED",
        actual_input=confirmed_actuals()[0], actual_output=confirmed_actuals()[1],
        actual_gas=confirmed_actuals()[2], binding=_foreign_binding(intent))

    first = recovery_service.reconcile(fresh_owner, action_id, foreign)
    second = recovery_service.reconcile(fresh_owner, action_id, foreign)
    assert first.case.state == second.case.state == "DISCREPANCY"
    assert second.duplicate is True
    assert second.case.evidence[-1].state == "REJECTED"
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_UNKNOWN"
    assert active_claim(recovery_factory, fresh_owner) is not None


def test_never_submitted_action_is_blocked(
        recovery_factory, recovery_service, admission_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, _context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    assert result.admission_status == "ADMITTED"

    evidence = evidence_for(recovery_factory, fresh_owner, action_id, outcome="CONFIRMED",
                            actual_input=confirmed_actuals()[0], actual_output=confirmed_actuals()[1],
                            actual_gas=confirmed_actuals()[2])
    outcome = recovery_service.reconcile(fresh_owner, action_id, evidence)
    assert outcome.applied is False
    assert outcome.case.state == "NO_SUBMISSION_ATTEMPT"
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "QUEUED"
    assert active_claim(recovery_factory, fresh_owner) is None
    assert admission_service.retrieve_receipts(fresh_owner, action_id=action_id) == []
    assert _balances(admission_service, fresh_owner)[QUOTE].consumed_raw == "0"


@pytest.mark.parametrize("field,mismatch_raw", [
    ("actual_input", "109"), ("actual_output", "9"), ("actual_gas", "3"),
])
def test_crash_convergence_rejects_mismatched_actuals(
        recovery_factory, recovery_service, admission_service, execution_service, fresh_owner,
        field, mismatch_raw) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    actual_input, actual_output, actual_gas = confirmed_actuals()
    good = evidence_for(recovery_factory, fresh_owner, action_id, outcome="CONFIRMED",
                        actual_input=actual_input, actual_output=actual_output, actual_gas=actual_gas)

    # The P22 terminal receipt is committed with the good actuals; P23 stays stale.
    settlement = admission_service.reconcile(fresh_owner, action_id, good.receipt())
    assert settlement.decision_status == "CONFIRMED"
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_UNKNOWN"

    amounts = {"actual_input": actual_input, "actual_output": actual_output, "actual_gas": actual_gas}
    amounts[field] = AssetAmount(asset_id=amounts[field].asset_id, raw=mismatch_raw, decimals=0)
    divergent = evidence_for(recovery_factory, fresh_owner, action_id, outcome="CONFIRMED", **amounts)
    outcome = recovery_service.reconcile(fresh_owner, action_id, divergent)
    assert outcome.applied is False
    assert outcome.case.state == "DISCREPANCY"
    assert outcome.case.blocking_reason == f"P22_RECEIPT_MISMATCH:{field}"
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_UNKNOWN"


def test_delayed_exit_reports_blocking_reason(
        recovery_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id = _unknown_exit(execution_service, fresh_owner, revision)
    view = recovery_service.status(fresh_owner, action_id)
    assert view.operation == "EXIT"
    assert view.state == "UNKNOWN"
    assert view.delayed_exit is True
    assert view.claim_held is True
    assert view.blocking_reason == "SUBMISSION_UNKNOWN"


def test_restart_after_reconcile_converges_stale_queue_without_second_accounting(
        recovery_factory, recovery_service, admission_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    actual_input, actual_output, actual_gas = confirmed_actuals()
    evidence = evidence_for(recovery_factory, fresh_owner, action_id, outcome="CONFIRMED",
                            actual_input=actual_input, actual_output=actual_output, actual_gas=actual_gas)

    # Simulate a crash after P22 reconciliation committed but before the P23 queue converged.
    settlement = admission_service.reconcile(fresh_owner, action_id, evidence.receipt())
    assert settlement.decision_status == "CONFIRMED"
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_UNKNOWN"
    consumed_once = _balances(admission_service, fresh_owner)[QUOTE].consumed_raw

    outcome = recovery_service.reconcile(fresh_owner, action_id, evidence)
    assert outcome.applied is True
    assert outcome.case.state == "CONFIRMED"
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "SUBMITTED_CONFIRMED"
    assert _balances(admission_service, fresh_owner)[QUOTE].consumed_raw == consumed_once


def test_competing_recoverers_apply_accounting_once(
        recovery_factory, recovery_service, admission_service, execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    actual_input, actual_output, actual_gas = confirmed_actuals()
    evidence = evidence_for(recovery_factory, fresh_owner, action_id, outcome="CONFIRMED",
                            actual_input=actual_input, actual_output=actual_output, actual_gas=actual_gas)

    barrier = threading.Barrier(2)
    results: list = [None, None]

    def recover(index: int) -> None:
        barrier.wait()
        results[index] = recovery_service.reconcile(fresh_owner, action_id, evidence)

    threads = [threading.Thread(target=recover, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert {item.case.state for item in results} == {"CONFIRMED"}
    assert sum(1 for item in results if item.applied) == 1
    assert sum(1 for item in results if item.duplicate) == 1
    balances = _balances(admission_service, fresh_owner)
    assert balances[QUOTE].consumed_raw == "110"
    assert balances[NATIVE].consumed_raw == "2"


def test_wallet_uncertainty_is_isolated(
        recovery_factory, recovery_service, execution_service, fresh_owner) -> None:
    owner_b = uuid.uuid4()
    revision = frozen_entry_exit()
    _approval, _context, result_a = open_unknown_entry(execution_service, fresh_owner, revision)
    account_b = RecoveryService(
        recovery_factory, AdmissionService(recovery_factory),
        ExecutionService(recovery_factory, AdmissionService(recovery_factory)))
    # Owner B admits its own unknown action under a different wallet binding.
    _approval_b, _context_b, result_b = _open_unknown_entry_scoped(
        execution_service, owner_b, revision, agent_id=AGENT_B, wallet_id=WALLET_B)

    evidence = evidence_for(recovery_factory, fresh_owner, result_a.intent.action_id, outcome="CONFIRMED",
                            actual_input=confirmed_actuals()[0], actual_output=confirmed_actuals()[1],
                            actual_gas=confirmed_actuals()[2])
    recovery_service.reconcile(fresh_owner, result_a.intent.action_id, evidence)

    view_b = account_b.status(owner_b, result_b.intent.action_id)
    assert view_b.state == "UNKNOWN"
    assert view_b.claim_held is True
    assert view_b.wallet_id == WALLET_B


def test_recovery_exposes_no_submission_interface() -> None:
    for forbidden in ("submit", "tick", "enqueue", "admit", "admit_and_reserve", "propose", "cancel", "route"):
        assert not hasattr(RecoveryService, forbidden), forbidden


def test_foreign_owner_action_is_not_found(recovery_service) -> None:
    owner = uuid.uuid4()
    # No saved action exists for this owner/action pair; the lookup fails closed.
    with pytest.raises(RecoveryError):
        recovery_service.status(owner, "p23:does-not-exist:ENTRY")


def _unknown_exit(service, owner, revision):
    """Open a position, then leave an exit in the submission-unknown state."""
    approval, _context = open_position(service, owner, revision)
    position_context = scoped_context(position_inventory="10", position_id="position-1",
                                      revision_id=revision.revision_id)
    decision = service.evaluate_and_decide(
        owner, revision, make_inputs(["90"], ["5"], position_open=True),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    enqueued = service.enqueue(owner, decision.decision_id,
                               exit_terms(position_id="position-1", quantity="5"),
                               approval, position_context)
    assert enqueued.admission_status == "ADMITTED", enqueued.admission_reason
    tick = service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=position_context, revision=revision, inputs=exit_inputs(),
        quote=quote(enqueued.intent.action_id, revision, "250"),
        transport=exec_transport("UNKNOWN", action_id=enqueued.intent.action_id))
    assert tick.status == "SUBMITTED_UNKNOWN", tick
    return enqueued.intent.action_id


def _foreign_binding(intent) -> object:
    from edge_os_api.admission.types import IdentityBinding
    return IdentityBinding(agent_id=intent.agent_id, wallet_id="foreign-wallet",
                           network_id=intent.network_id, strategy_revision=intent.revision_id,
                           mandate_id=intent.mandate_id)


def _open_unknown_entry_scoped(service, owner, revision, *, agent_id: str, wallet_id: str):
    from execution._builders import make_inputs, scoped_approval, scoped_context
    from execution._support import entry_inputs as _entries
    decision = service.evaluate_and_decide(
        owner, revision, make_inputs(["110"], ["5"], position_open=False),
        agent_id=agent_id, wallet_id=wallet_id, network_id=NETWORK)
    approval = scoped_approval(revision_id=revision.revision_id, agent_id=agent_id, wallet_id=wallet_id)
    context = scoped_context(agent_id=agent_id, wallet_id=wallet_id)
    from execution._builders import entry_terms
    result = service.enqueue(owner, decision.decision_id,
                             entry_terms(quantity="10", quote_input="110"), approval, context)
    assert result.admission_status == "ADMITTED", result.admission_reason
    tick = service.tick(
        owner, agent_id=agent_id, wallet_id=wallet_id, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=_entries(),
        quote=quote(result.intent.action_id, revision, "110"),
        transport=exec_transport("UNKNOWN", action_id=result.intent.action_id))
    assert tick.status == "SUBMITTED_UNKNOWN", tick
    return approval, context, result
