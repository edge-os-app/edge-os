"""Exact intent admission, replay safety, exclusive claim and exit priority."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from edge_os_api.execution.types import ExecutionError

from admission._builders import AGENT_A, AGENT_B, NETWORK, WALLET_A, WALLET_B
from execution._builders import (
    entry_terms,
    exit_terms,
    frozen_entry_exit,
    make_inputs,
    scoped_approval,
    scoped_context,
)
from execution._support import (
    entry_inputs,
    enqueue_entry,
    exit_inputs,
    open_position,
    run_concurrently,
    transport,
)


def test_enqueue_admits_and_links_intent_to_decision(execution_service, admission_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    decision, _approval, _context, result = enqueue_entry(execution_service, fresh_owner, revision)

    assert result.admission_status == "ADMITTED", result.admission_reason
    assert result.intent.decision_id == decision.decision_id
    assert result.intent.binding.strategy_revision == revision.revision_id
    assert result.queue_entry is not None and result.queue_entry.state == "QUEUED"

    saved = admission_service.retrieve_decisions(fresh_owner, action_id=result.intent.action_id)
    assert len(saved) == 1 and saved[0].status == "ADMITTED"


def test_replay_same_decision_never_creates_second_action(execution_service, admission_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    decision, approval, context, first = enqueue_entry(execution_service, fresh_owner, revision)

    second = execution_service.enqueue(
        fresh_owner, decision.decision_id, entry_terms(), approval, context)

    assert second.intent.action_id == first.intent.action_id
    assert second.intent.review_hash == first.intent.review_hash
    queue = execution_service.retrieve_queue(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert [item.action_id for item in queue] == [first.intent.action_id]
    # Only one economic action was ever admitted.
    assert len(admission_service.retrieve_decisions(fresh_owner)) == 1


def test_replay_under_changed_meaning_is_refused(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    decision, approval, context, _first = enqueue_entry(execution_service, fresh_owner, revision)

    changed = entry_terms(quantity="10", quote_input="220")
    with pytest.raises(ExecutionError):
        execution_service.enqueue(fresh_owner, decision.decision_id, changed, approval, context)


def test_exit_is_selected_before_an_unsubmitted_entry(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    approval, _context = open_position(execution_service, fresh_owner, revision)
    position_context = scoped_context(position_inventory="10", position_id="position-1",
                                      revision_id=revision.revision_id)

    exit_decision = execution_service.evaluate_and_decide(
        fresh_owner, revision, make_inputs(["90"], ["5"], position_open=True),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    exit_enqueue = execution_service.enqueue(
        fresh_owner, exit_decision.decision_id, exit_terms(position_id="position-1", quantity="10"),
        approval, position_context)
    assert exit_enqueue.admission_status == "ADMITTED", exit_enqueue.admission_reason

    entry_decision = execution_service.evaluate_and_decide(
        fresh_owner, revision, make_inputs(["110"], ["5"], position_open=False),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    entry_enqueue = execution_service.enqueue(
        fresh_owner, entry_decision.decision_id,
        entry_terms(position_id="position-2", quantity="10", quote_input="110"),
        approval, position_context)
    assert entry_enqueue.admission_status == "ADMITTED", entry_enqueue.admission_reason

    queue = execution_service.retrieve_queue(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert [item.operation for item in queue if item.state == "QUEUED"] == ["EXIT", "ENTRY"]

    tick = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=position_context, revision=revision, inputs=exit_inputs(),
        transport=transport("ACCEPT", action_id=exit_enqueue.intent.action_id))
    assert tick.selected_action_id == exit_enqueue.intent.action_id
    assert tick.status == "SUBMITTED_CONFIRMED"


def test_unknown_outcome_blocks_only_its_wallet(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval_a, context_a, result_a = enqueue_entry(execution_service, fresh_owner, revision)

    first = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval_a,
        context=context_a, revision=revision, inputs=entry_inputs(),
        transport=transport("UNKNOWN", action_id=result_a.intent.action_id))
    assert first.status == "SUBMITTED_UNKNOWN"

    blocked = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval_a,
        context=context_a, revision=revision, inputs=entry_inputs(), transport=transport("ACCEPT"))
    assert blocked.status == "BLOCKED_UNKNOWN"

    # Wallet B is independent and can still proceed.
    approval_b = scoped_approval(revision_id=revision.revision_id, agent_id=AGENT_B, wallet_id=WALLET_B)
    context_b = scoped_context(agent_id=AGENT_B, wallet_id=WALLET_B)
    decision_b = execution_service.evaluate_and_decide(
        fresh_owner, revision, make_inputs(["110"], ["5"], position_open=False),
        agent_id=AGENT_B, wallet_id=WALLET_B, network_id=NETWORK)
    enqueue_b = execution_service.enqueue(
        fresh_owner, decision_b.decision_id, entry_terms(position_id="position-b-1"),
        approval_b, context_b)
    assert enqueue_b.admission_status == "ADMITTED", enqueue_b.admission_reason
    tick_b = execution_service.tick(
        fresh_owner, agent_id=AGENT_B, wallet_id=WALLET_B, network_id=NETWORK, approval=approval_b,
        context=context_b, revision=revision, inputs=entry_inputs(),
        transport=transport("ACCEPT", action_id=enqueue_b.intent.action_id))
    assert tick_b.status == "SUBMITTED_CONFIRMED"


def test_two_concurrent_ticks_submit_once(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id

    def tick(_index: int) -> str:
        return execution_service.tick(
            fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
            context=context, revision=revision, inputs=entry_inputs(),
            transport=transport("ACCEPT", action_id=action_id)).status

    statuses = run_concurrently(2, tick)
    assert statuses.count("SUBMITTED_CONFIRMED") == 1
    with execution_engine.connect() as connection:
        attempts = connection.execute(text(
            "SELECT count(*) FROM execution_submission_attempts WHERE owner_id = :owner"),
            {"owner": str(fresh_owner)}).scalar_one()
    assert attempts == 1
