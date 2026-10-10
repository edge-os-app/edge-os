"""Revalidation immediately before submission denies changed or expired inputs."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text

from admission._builders import AGENT_A, NETWORK, WALLET_A
from execution._builders import (
    DECISION_TIME,
    frozen_entry_exit,
    gt_constant,
    make_inputs,
    scoped_approval,
    scoped_context,
)
from execution._support import enqueue_entry, entry_inputs, transport


def _payload_hash(engine, owner, action_id: str) -> str:
    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT payload_hash FROM execution_intents WHERE owner_id = :owner AND action_id = :action"),
            {"owner": str(owner), "action": action_id}).scalar_one()


def _run(execution_service, owner, revision, approval, context, action_id):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(),
        transport=transport("ACCEPT", action_id=action_id))


def test_expired_or_revoked_approval_denies_and_preserves_payload(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    before = _payload_hash(execution_engine, fresh_owner, result.intent.action_id)

    revoked = scoped_approval(revision_id=revision.revision_id, state="REVOKED")
    tick = _run(execution_service, fresh_owner, revision, revoked, context, result.intent.action_id)

    assert tick.status == "REVALIDATION_DENIED"
    assert "APPROVAL_INACTIVE_OR_EXPIRED" in (tick.reason or "")
    assert _payload_hash(execution_engine, fresh_owner, result.intent.action_id) == before
    with execution_engine.connect() as connection:
        attempts = connection.execute(text(
            "SELECT count(*) FROM execution_submission_attempts WHERE owner_id = :owner"),
            {"owner": str(fresh_owner)}).scalar_one()
    assert attempts == 0


def test_changed_policy_binding_denies(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    changed = scoped_approval(revision_id=revision.revision_id, policy_binding="p23-policy-other")

    tick = _run(execution_service, fresh_owner, revision, changed, context, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "POLICY_BINDING_CHANGED"


def test_changed_revision_denies(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    other = frozen_entry_exit(entry=gt_constant("101"))

    tick = _run(execution_service, fresh_owner, other, scoped_approval(revision_id=other.revision_id),
                context, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "REVISION_CHANGED"


def test_scoped_stop_denies_a_queued_entry(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    stopped = scoped_approval(revision_id=revision.revision_id, stops=("STOP_NEW_ENTRIES",))

    tick = _run(execution_service, fresh_owner, revision, stopped, context, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert "STOPPED_NEW_ENTRIES" in (tick.reason or "")
    assert tick.queue_entry is not None and tick.queue_entry.state == "REVALIDATION_DENIED"


def _attempt_count(engine, owner) -> int:
    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT count(*) FROM execution_submission_attempts WHERE owner_id = :owner"),
            {"owner": str(owner)}).scalar_one()


def test_empty_holdings_deny_before_submission(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, _context, result = enqueue_entry(execution_service, fresh_owner, revision)
    empty = scoped_context(quote_raw="0", native_raw="0")

    tick = _run(execution_service, fresh_owner, revision,
                scoped_approval(revision_id=revision.revision_id), empty, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "HOLDINGS_SHORTFALL"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_lowered_successor_limits_deny_before_submission(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    lower = scoped_approval(revision_id=revision.revision_id, quote_approved_raw="1",
                            gas_approved_raw="0", approval_id="gate-successor")

    tick = _run(execution_service, fresh_owner, revision, lower, context, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "CAPACITY_UNAVAILABLE"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_cancelled_action_denies_before_submission(execution_service, admission_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    assert admission_service.cancel(fresh_owner, result.intent.action_id).decision_status == "CANCELLED"

    tick = _run(execution_service, fresh_owner, revision, approval, context, result.intent.action_id)
    assert tick.status == "REVALIDATION_DENIED"
    assert (tick.reason or "").startswith("ACTION_NOT_ADMITTED")
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_expired_intent_denies_before_submission(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    late = DECISION_TIME + dt.timedelta(minutes=14)

    tick = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        approval=scoped_approval(revision_id=revision.revision_id), context=context, revision=revision,
        inputs=entry_inputs(), transport=transport("ACCEPT"), now=late)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "INTENT_EXPIRED"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_stale_submission_context_denies_before_submission(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, _context, result = enqueue_entry(execution_service, fresh_owner, revision)
    stale = scoped_context(checked_at="2026-01-01T00:05:00Z")

    tick = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        approval=scoped_approval(revision_id=revision.revision_id), context=stale, revision=revision,
        inputs=entry_inputs(), transport=transport("ACCEPT"))
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "STALE_CONTEXT"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_changed_current_inputs_deny_before_submission(execution_service, execution_engine, fresh_owner) -> None:
    """A newer no-signal input at a fresh context time must not submit the old signal."""
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    changed = make_inputs(["90"], ["5"], position_open=False)  # entry now FALSE -> NO_SIGNAL

    tick = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        approval=scoped_approval(revision_id=revision.revision_id), context=context, revision=revision,
        inputs=changed, transport=transport("ACCEPT"))
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "INPUTS_CHANGED"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_missing_current_input_denies_before_submission(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    missing = make_inputs([None], ["5"], position_open=False)  # required price missing -> INELIGIBLE

    tick = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        approval=scoped_approval(revision_id=revision.revision_id), context=context, revision=revision,
        inputs=missing, transport=transport("ACCEPT"))
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "INPUTS_CHANGED"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_next_bucket_boundary_denies_the_old_intent(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    next_bucket = DECISION_TIME + dt.timedelta(minutes=5)

    tick = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        approval=scoped_approval(revision_id=revision.revision_id), context=context, revision=revision,
        inputs=entry_inputs(), transport=transport("ACCEPT"), now=next_bucket)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "INTENT_EXPIRED"
    assert _attempt_count(execution_engine, fresh_owner) == 0
