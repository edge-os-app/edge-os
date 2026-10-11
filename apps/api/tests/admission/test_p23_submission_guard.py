"""P23 submission-ownership guard regressions on the accepted P22 service.

These pin the minimal admission behavior the P23 repair relies on: an action that
P23 has claimed for submission is non-cancellable and non-competing until a
proved definite-unsent or reconciled outcome.
"""

from __future__ import annotations

from admission._builders import (
    approval_a,
    confirm_entry,
    context_a,
    intent_entry,
    prebroadcast,
    receipt,
)


def _reserved(admission_service, owner) -> list:
    return admission_service.retrieve_reservations(owner, wallet_id="wallet-a", network_id="monad:143")


def test_submission_owned_action_blocks_cancel_and_competing_admission(admission_service, fresh_owner) -> None:
    approval = approval_a(quote_approved_raw="110")
    entry = intent_entry(quote_input_raw="110", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a()).status == "ADMITTED"

    owned = admission_service.reconcile(fresh_owner, entry.action_id, receipt(entry, "SUBMISSION_UNKNOWN"))
    assert owned.decision_status == "SUBMISSION_UNKNOWN"

    cancelled = admission_service.cancel(fresh_owner, entry.action_id)
    assert cancelled.decision_status == "SUBMISSION_UNKNOWN"
    assert cancelled.reason == "NOT_CANCELLABLE_AFTER_SUBMISSION"

    competing = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-2"), approval, context_a())
    assert competing.status == "DENIED" and competing.reason == "UNRESOLVED_PRIOR_ACTION"

    assert len(_reserved(admission_service, fresh_owner)) == 4


def test_proved_prebroadcast_denial_releases_a_submission_owned_action(admission_service, fresh_owner) -> None:
    approval = approval_a(base_approved_raw="10")
    entry = intent_entry(quantity_raw="1", quote_input_raw="20", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a())
    owned = admission_service.reconcile(fresh_owner, entry.action_id, receipt(entry, "SUBMISSION_UNKNOWN"))
    assert owned.decision_status == "SUBMISSION_UNKNOWN"

    released = admission_service.reconcile(fresh_owner, entry.action_id, prebroadcast(entry))
    assert released.decision_status == "DENIED" and released.reason == "PREBROADCAST_DENIED"
    assert _reserved(admission_service, fresh_owner) == []


def test_confirmed_settles_a_submission_owned_action(admission_service, fresh_owner) -> None:
    approval = approval_a()
    entry = intent_entry(quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, receipt(entry, "SUBMISSION_UNKNOWN"))

    settled = admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "110", "10", "1"))
    assert settled.decision_status == "CONFIRMED"


def test_acquire_submission_is_action_scoped_and_writes_no_receipt(admission_service, fresh_owner) -> None:
    approval = approval_a(quote_approved_raw="110")
    entry = intent_entry(quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a())

    assert admission_service.acquire_submission(fresh_owner, entry.action_id) == "ACQUIRED"
    # Ownership is a pre-call state, not a transport receipt.
    assert admission_service.retrieve_receipts(fresh_owner, action_id=entry.action_id) == []
    # A second acquire does not re-acquire an already owned action.
    assert admission_service.acquire_submission(fresh_owner, entry.action_id) == "SUBMISSION_UNKNOWN"
    # Ownership blocks cancellation and a competing admission, and retains capacity.
    assert admission_service.cancel(fresh_owner, entry.action_id).reason == "NOT_CANCELLABLE_AFTER_SUBMISSION"
    competing = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-2"), approval, context_a())
    assert competing.status == "DENIED" and competing.reason == "UNRESOLVED_PRIOR_ACTION"
    assert len(_reserved(admission_service, fresh_owner)) == 4
    # A proved definitely-unsent releases the acquired action.
    released = admission_service.reconcile(fresh_owner, entry.action_id, prebroadcast(entry))
    assert released.decision_status == "DENIED" and released.reason == "PREBROADCAST_DENIED"
    assert _reserved(admission_service, fresh_owner) == []


def test_acquire_submission_refuses_a_non_admitted_action(admission_service, fresh_owner) -> None:
    entry = intent_entry(quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.cancel(fresh_owner, entry.action_id)

    assert admission_service.acquire_submission(fresh_owner, entry.action_id) == "CANCELLED"
    assert admission_service.acquire_submission(fresh_owner, "p23:missing:ENTRY") == "NOT_FOUND"
