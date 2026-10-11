"""Revalidation immediately before submission denies changed or expired inputs."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from edge_os_api.admission.types import AssetAmount
from edge_os_api.execution.types import ActionQuote

from admission._builders import AGENT_A, BASE, NETWORK, QUOTE, WALLET_A
from execution._builders import (
    DECISION_TIME,
    frozen_entry_exit,
    gt_constant,
    make_inputs,
    scoped_approval,
    scoped_context,
)
from execution._support import enqueue_entry, entry_inputs, quote, transport


def _payload_hash(engine, owner, action_id: str) -> str:
    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT payload_hash FROM execution_intents WHERE owner_id = :owner AND action_id = :action"),
            {"owner": str(owner), "action": action_id}).scalar_one()


def _run(execution_service, owner, revision, approval, context, action_id):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(), quote=quote(action_id, revision, "110"),
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
        inputs=entry_inputs(), quote=quote(result.intent.action_id, revision, "110"), transport=transport("ACCEPT"), now=late)
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
        inputs=entry_inputs(), quote=quote(result.intent.action_id, revision, "110"), transport=transport("ACCEPT"))
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
        inputs=changed, quote=quote(result.intent.action_id, revision, "110"), transport=transport("ACCEPT"))
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
        inputs=missing, quote=quote(result.intent.action_id, revision, "110"), transport=transport("ACCEPT"))
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
        inputs=entry_inputs(), quote=quote(result.intent.action_id, revision, "110"), transport=transport("ACCEPT"), now=next_bucket)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "INTENT_EXPIRED"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def _tick_with_quote(execution_service, owner, revision, approval, context, quote_evidence):
    return execution_service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(), quote=quote_evidence,
        transport=transport("ACCEPT"))


def test_changed_action_quote_denies_while_the_signal_stays_true(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    # The rule still yields SIGNAL (price 110); only the action quote changed.
    tick = _tick_with_quote(execution_service, fresh_owner, revision,
                            scoped_approval(revision_id=revision.revision_id), context, quote(result.intent.action_id, revision, "120"))
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "QUOTE_CHANGED"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_missing_action_quote_denies(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    tick = _tick_with_quote(execution_service, fresh_owner, revision,
                            scoped_approval(revision_id=revision.revision_id), context, None)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "QUOTE_MISSING"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_stale_or_expired_action_quote_denies(execution_service, execution_engine) -> None:
    revision = frozen_entry_exit()
    approval = scoped_approval(revision_id=revision.revision_id)

    owner_a = uuid.uuid4()
    _d1, _a1, context1, _r1 = enqueue_entry(execution_service, owner_a, revision)
    stale = _tick_with_quote(execution_service, owner_a, revision, approval, context1,
                             quote(_r1.intent.action_id, revision, "110", observed_at="2026-01-01T00:05:00Z"))
    assert stale.status == "REVALIDATION_DENIED" and stale.reason == "QUOTE_STALE"

    owner_b = uuid.uuid4()
    _d2, _a2, context2, _r2 = enqueue_entry(execution_service, owner_b, revision)
    expired = _tick_with_quote(execution_service, owner_b, revision, approval, context2,
                               quote(_r2.intent.action_id, revision, "110", expires_at="2026-01-01T00:15:00Z"))
    assert expired.status == "REVALIDATION_DENIED" and expired.reason == "QUOTE_EXPIRED"
    assert _attempt_count(execution_engine, owner_a) == 0
    assert _attempt_count(execution_engine, owner_b) == 0


def test_wrong_identity_or_units_action_quote_denies(execution_service, execution_engine) -> None:
    revision = frozen_entry_exit()
    approval = scoped_approval(revision_id=revision.revision_id)

    owner_a = uuid.uuid4()
    _d1, _a1, context1, _r1 = enqueue_entry(execution_service, owner_a, revision)
    wrong_asset = _tick_with_quote(execution_service, owner_a, revision, approval, context1,
                                   quote(_r1.intent.action_id, revision, "110", asset=BASE))
    assert wrong_asset.status == "REVALIDATION_DENIED"
    assert wrong_asset.reason == "QUOTE_IDENTITY_MISMATCH"

    owner_b = uuid.uuid4()
    _d2, _a2, context2, _r2 = enqueue_entry(execution_service, owner_b, revision)
    wrong_units = _tick_with_quote(execution_service, owner_b, revision, approval, context2,
                                   quote(_r2.intent.action_id, revision, "110", decimals=6))
    assert wrong_units.status == "REVALIDATION_DENIED"
    assert wrong_units.reason == "QUOTE_UNITS_MISMATCH"
    assert _attempt_count(execution_engine, owner_a) == 0
    assert _attempt_count(execution_engine, owner_b) == 0


def test_compatible_action_quote_submits(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    tick = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(),
        quote=quote(result.intent.action_id, revision, "110"), transport=transport("ACCEPT"))
    assert tick.status == "SUBMITTED_CONFIRMED"


def test_quote_bound_to_a_different_action_denies(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    approval = scoped_approval(revision_id=revision.revision_id)
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    foreign = quote("p23:00000000-0000-0000-0000-000000000000:ENTRY", revision, "110")

    tick = _tick_with_quote(execution_service, fresh_owner, revision, approval, context, foreign)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "QUOTE_ACTION_MISMATCH"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_quote_bound_to_a_different_market_denies(execution_service, execution_engine, fresh_owner) -> None:
    revision = frozen_entry_exit()
    approval = scoped_approval(revision_id=revision.revision_id)
    _decision, _approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    foreign = quote(result.intent.action_id, revision, "110", market_binding_id="other-market-binding")

    tick = _tick_with_quote(execution_service, fresh_owner, revision, approval, context, foreign)
    assert tick.status == "REVALIDATION_DENIED"
    assert tick.reason == "QUOTE_MARKET_MISMATCH"
    assert _attempt_count(execution_engine, fresh_owner) == 0


def test_quote_bound_to_a_different_revision_denies(execution_service, execution_engine) -> None:
    revision = frozen_entry_exit()
    approval = scoped_approval(revision_id=revision.revision_id)

    owner_a = uuid.uuid4()
    _d1, _a1, context1, result1 = enqueue_entry(execution_service, owner_a, revision)
    wrong_revision = quote(result1.intent.action_id, revision, "110", revision_id="other-revision")
    tick_a = _tick_with_quote(execution_service, owner_a, revision, approval, context1, wrong_revision)
    assert tick_a.status == "REVALIDATION_DENIED" and tick_a.reason == "QUOTE_REVISION_MISMATCH"

    owner_b = uuid.uuid4()
    _d2, _a2, context2, result2 = enqueue_entry(execution_service, owner_b, revision)
    wrong_hash = quote(result2.intent.action_id, revision, "110",
                       revision_content_hash="sha256:" + "c" * 64)
    tick_b = _tick_with_quote(execution_service, owner_b, revision, approval, context2, wrong_hash)
    assert tick_b.status == "REVALIDATION_DENIED" and tick_b.reason == "QUOTE_REVISION_MISMATCH"
    assert _attempt_count(execution_engine, owner_a) == 0
    assert _attempt_count(execution_engine, owner_b) == 0


def test_action_quote_requires_nonempty_identity_fields() -> None:
    revision = frozen_entry_exit()
    base = dict(
        action_id="p23:ok:ENTRY", revision_id=revision.revision_id,
        revision_content_hash=revision.content_hash, market_binding_id=revision.market_binding_id,
        quote_asset_id=QUOTE, amount=AssetAmount(asset_id=QUOTE, raw="110", decimals=0),
        observed_at="2026-01-01T00:16:00Z", expires_at="2026-01-01T00:21:00Z", source_ref="x")
    ActionQuote(**base)  # a complete binding constructs
    for field in ("action_id", "revision_id", "market_binding_id", "revision_content_hash"):
        with pytest.raises(ValidationError):
            ActionQuote(**{**base, field: ""})
