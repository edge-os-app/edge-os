"""A recorded breach is never silently replaced by a later receipt (P24 focused 5/5)."""

from __future__ import annotations

from admission._builders import (
    approval_a,
    confirm_entry,
    context_a,
    intent_entry,
    prebroadcast,
    receipt,
    unknown,
)


def _breached_entry(admission_service, owner):
    approval = approval_a(base_approved_raw="10")
    entry = intent_entry(quantity_raw="1", quote_input_raw="20", position_id="position-a-1")
    assert admission_service.admit_and_reserve(owner, entry, approval, context_a()).status == "ADMITTED"
    outcome = admission_service.reconcile(owner, entry.action_id, confirm_entry(entry, "20", "11", "1"))
    assert outcome.decision_status == "BREACHED"
    assert outcome.reason == "SELL_COVERAGE_EXCEEDED"
    return entry


def test_later_receipt_cannot_replace_a_recorded_breach(admission_service, fresh_owner) -> None:
    entry = _breached_entry(admission_service, fresh_owner)

    follow_ups = [
        ("identical replay", confirm_entry(entry, "20", "11", "1")),
        ("conflicting confirmed", confirm_entry(entry, "20", "10", "1")),
        ("reverted", receipt(entry, "REVERTED")),
        ("unknown", unknown(entry)),
        ("denial", prebroadcast(entry)),
        ("cancellation", receipt(entry, "CANCELLED")),
    ]
    for label, follow_up in follow_ups:
        outcome = admission_service.reconcile(fresh_owner, entry.action_id, follow_up)
        assert outcome.decision_status == "BREACHED", (label, outcome)
        assert outcome.reason in {"CONTRADICTORY_RECOVERY", "NOT_CANCELLABLE_AFTER_SUBMISSION"}, (label, outcome)

    # The durable breach decision and its single breach receipt are preserved.
    assert admission_service.retrieve_decisions(
        fresh_owner, action_id=entry.action_id)[0].status == "BREACHED"
    receipts = admission_service.retrieve_receipts(fresh_owner, action_id=entry.action_id)
    assert len(receipts) == 1
    assert receipts[0].breach is True and receipts[0].outcome == "CONFIRMED"


def test_breach_still_blocks_new_work_after_a_later_receipt(admission_service, fresh_owner) -> None:
    entry = _breached_entry(admission_service, fresh_owner)
    admission_service.reconcile(fresh_owner, entry.action_id, unknown(entry))

    blocked = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-2"), approval_a(base_approved_raw="10"), context_a())
    assert blocked.status == "DENIED"
    assert blocked.reason == "UNRESOLVED_PRIOR_ACTION"
