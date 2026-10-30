"""OWNER-TRIGGER-L3: the owner-triggered basis keeps every other submission revalidation.

The owner basis removes only the market-rule check and `STALE_INPUTS`. Revision, policy, approval, intent,
context, quote, admission, stop and coverage denials still run with zero transport calls.
"""
from __future__ import annotations

import datetime as dt

from edge_os_api.execution.types import EvaluationInputs

from admission._builders import AGENT_A, NETWORK, WALLET_A
from execution._builders import (
    DECISION_TIME,
    frozen_entry_exit,
    gt_constant,
    scoped_approval,
    scoped_context,
)
from execution._support import decide_entry, entry_terms, quote, transport

RELEASE_ID = "actual-inapp-wmon-moe-20261022/1"
BINDING = "7" * 64


def _owner_entry(execution_service, owner, revision):
    decision = execution_service.authorize_owner_trigger(
        owner, revision, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        decision_at=DECISION_TIME, release_id=RELEASE_ID, binding_sha256=BINDING)
    approval, context = scoped_approval(revision_id=revision.revision_id), scoped_context()
    result = execution_service.enqueue(
        owner, decision.decision_id, entry_terms(), approval, context)
    assert result.admission_status == "ADMITTED", result.admission_reason
    return result.intent.action_id, approval, context


def _tick(execution_service, owner, revision, approval, context, action_id, *,
          inputs: EvaluationInputs | None = None, quote_amount: str = "110", quote_observed: str = "2026-01-01T00:16:00Z"):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=inputs,
        quote=quote(action_id, revision, quote_amount, observed_at=quote_observed),
        transport=transport("ACCEPT", action_id=action_id))


def _attempts(engine, owner) -> int:
    from sqlalchemy import text

    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT count(*) FROM execution_submission_attempts WHERE owner_id = :owner"),
            {"owner": str(owner)}).scalar_one()


def test_the_owner_basis_still_submits_with_no_rule_inputs(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, approval, context = _owner_entry(execution_service, fresh_owner, revision)
    tick = _tick(execution_service, fresh_owner, revision, approval, context, action_id)
    assert tick.status == "SUBMITTED_CONFIRMED", tick
    assert _attempts(execution_engine, fresh_owner) == 1


def test_a_changed_revision_denies_the_owner_basis(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, _approval, context = _owner_entry(execution_service, fresh_owner, revision)
    other = frozen_entry_exit(entry=gt_constant("101"))
    tick = _tick(execution_service, fresh_owner, other, scoped_approval(revision_id=other.revision_id),
                 context, action_id)
    assert (tick.status, tick.reason) == ("REVALIDATION_DENIED", "REVISION_CHANGED")


def test_an_inactive_approval_denies_the_owner_basis(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, _approval, context = _owner_entry(execution_service, fresh_owner, revision)
    tick = _tick(execution_service, fresh_owner, revision,
                 scoped_approval(revision_id=revision.revision_id, state="REVOKED"), context, action_id)
    assert (tick.status, tick.reason) == ("REVALIDATION_DENIED", "APPROVAL_INACTIVE_OR_EXPIRED")


def test_a_changed_policy_binding_denies_the_owner_basis(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, _approval, context = _owner_entry(execution_service, fresh_owner, revision)
    tick = _tick(execution_service, fresh_owner, revision,
                 scoped_approval(revision_id=revision.revision_id, policy_binding="p23-policy-other"),
                 context, action_id)
    assert (tick.status, tick.reason) == ("REVALIDATION_DENIED", "POLICY_BINDING_CHANGED")


def test_a_cancelled_admission_denies_the_owner_basis(execution_service, admission_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, approval, context = _owner_entry(execution_service, fresh_owner, revision)
    assert admission_service.cancel(fresh_owner, action_id).decision_status == "CANCELLED"
    tick = _tick(execution_service, fresh_owner, revision, approval, context, action_id)
    assert tick.status == "REVALIDATION_DENIED" and (tick.reason or "").startswith("ACTION_NOT_ADMITTED")


def test_a_stop_denies_the_owner_basis(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, _approval, context = _owner_entry(execution_service, fresh_owner, revision)
    tick = _tick(execution_service, fresh_owner, revision,
                 scoped_approval(revision_id=revision.revision_id, stops=("STOP_NEW_ENTRIES",)), context, action_id)
    assert tick.status == "REVALIDATION_DENIED" and "STOPPED_NEW_ENTRIES" in (tick.reason or "")


def test_a_stale_quote_denies_the_owner_basis(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, approval, context = _owner_entry(execution_service, fresh_owner, revision)
    tick = _tick(execution_service, fresh_owner, revision, approval, context, action_id,
                 quote_observed="2026-01-01T00:10:00Z")
    assert (tick.status, tick.reason) == ("REVALIDATION_DENIED", "QUOTE_STALE")


def test_a_changed_quote_denies_the_owner_basis(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, approval, context = _owner_entry(execution_service, fresh_owner, revision)
    tick = _tick(execution_service, fresh_owner, revision, approval, context, action_id, quote_amount="111")
    assert (tick.status, tick.reason) == ("REVALIDATION_DENIED", "QUOTE_CHANGED")


def test_an_expired_intent_denies_the_owner_basis(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, approval, context = _owner_entry(execution_service, fresh_owner, revision)
    late = DECISION_TIME + dt.timedelta(minutes=14)
    tick = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=None,
        quote=quote(action_id, revision, "110", observed_at="2026-01-01T00:16:00Z"),
        transport=transport("ACCEPT", action_id=action_id), now=late)
    assert (tick.status, tick.reason) == ("REVALIDATION_DENIED", "INTENT_EXPIRED")


def test_a_rule_decision_without_inputs_is_refused(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    decision = decide_entry(execution_service, fresh_owner, revision)
    approval, context = scoped_approval(revision_id=revision.revision_id), scoped_context()
    result = execution_service.enqueue(fresh_owner, decision.decision_id, entry_terms(), approval, context)
    assert result.admission_status == "ADMITTED"
    tick = _tick(execution_service, fresh_owner, revision, approval, context, result.intent.action_id)
    assert (tick.status, tick.reason) == ("REVALIDATION_DENIED", "INPUTS_MISSING")


def test_a_stale_context_denies_the_owner_basis(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    action_id, approval, _context = _owner_entry(execution_service, fresh_owner, revision)
    stale = scoped_context(checked_at="2026-01-01T00:00:00Z")
    tick = _tick(execution_service, fresh_owner, revision, approval, stale, action_id)
    assert (tick.status, tick.reason) == ("REVALIDATION_DENIED", "STALE_CONTEXT")
