"""Regression tests for the gate findings B1-B9 on the P22 local stage."""

from __future__ import annotations

import threading

from sqlalchemy import text

from edge_os_api.admission.types import ActionReceipt, AssetAmount

from admission._builders import (
    BASE,
    NATIVE,
    QUOTE,
    approval_a,
    approval_b,
    binding_b,
    confirm_entry,
    confirm_exit,
    context_a,
    context_b,
    intent_a,
    intent_entry,
    intent_entry_b,
    intent_exit,
)


def _one(summaries, asset_id: str):
    for summary in summaries:
        if summary.asset_id == asset_id:
            return summary
    raise AssertionError(f"no allowance for {asset_id}")


def _run_concurrently(count, target):
    barrier = threading.Barrier(count)
    results = [None] * count

    def worker(index):
        barrier.wait()
        results[index] = target(index)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


# ---------------------------------------------------------------- B1

def test_concurrent_reconcile_settles_once(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())

    def settle(index):
        return admission_service.reconcile(fresh_owner, intent.action_id,
                                           confirm_entry(intent, "110", "10", "1"))

    outcomes = _run_concurrently(2, settle)
    quote = _one(admission_service.balances(fresh_owner), QUOTE)
    gas = _one(admission_service.balances(fresh_owner), NATIVE)
    # Exactly one receipt settles; the other is refused as a terminal repeat. No double charge.
    settled = [o for o in outcomes if o.reason is None]
    refused = [o for o in outcomes if o.reason == "RECONCILIATION_TERMINAL_STATE"]
    assert len(settled) == 1 and len(refused) == 1, [(o.decision_status, o.reason) for o in outcomes]
    assert settled[0].decision_status == "CONFIRMED"
    assert quote.consumed_raw == "110" and gas.consumed_raw == "1"


# ---------------------------------------------------------------- B2

def test_receipt_identity_mismatch_is_denied_without_mutation(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    wrong = ActionReceipt(
        action_id="other-action", binding=intent.binding, outcome="CONFIRMED",
        actual_input=AssetAmount(asset_id=QUOTE, raw="110", decimals=0),
        actual_output=AssetAmount(asset_id=BASE, raw="10", decimals=0),
        actual_gas=AssetAmount(asset_id=NATIVE, raw="1", decimals=0))
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, wrong)
    assert outcome.reason == "ACTION_IDENTITY_MISMATCH"
    assert _one(admission_service.balances(fresh_owner), QUOTE).consumed_raw == "0"


# ---------------------------------------------------------------- B3

def test_exit_with_other_wallet_binding_is_denied(admission_service, fresh_owner) -> None:
    entry = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "110", "10", "1"))

    cross = intent_a("EXIT", "5", binding=binding_b(), policy_binding="policy-b-v1", position_id="position-a-1")
    outcome = admission_service.admit_and_reserve(fresh_owner, cross, approval_b(), context_b())
    assert outcome.status == "DENIED"
    assert "POSITION_BINDING_MISMATCH" in outcome.reason or "BINDING_MISMATCH" in outcome.reason


def test_stale_position_snapshot_is_denied(admission_service, fresh_owner) -> None:
    entry = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "110", "10", "1"))

    first_exit = intent_exit(quantity_raw="6")
    admission_service.admit_and_reserve(fresh_owner, first_exit, approval_a(), context_a(position_inventory="10"))
    admission_service.reconcile(fresh_owner, first_exit.action_id, confirm_exit(first_exit, "6", "300", "1"))

    stale = intent_exit(quantity_raw="6")
    outcome = admission_service.admit_and_reserve(
        fresh_owner, stale, approval_a(), context_a(position_inventory="10"))
    assert outcome.status == "DENIED"
    assert "STALE_POSITION_SNAPSHOT" in outcome.reason


# ---------------------------------------------------------------- B4

def test_changed_approval_content_reuse_is_denied(admission_service, fresh_owner) -> None:
    first = intent_entry(quantity_raw="10", quote_input_raw="300", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, first, approval_a(quote_approved_raw="500"),
                                               context_a()).status == "ADMITTED"
    admission_service.cancel(fresh_owner, first.action_id)
    second = intent_entry(quantity_raw="10", quote_input_raw="200", position_id="position-a-2")
    denied = admission_service.admit_and_reserve(fresh_owner, second, approval_a(quote_approved_raw="100"),
                                                 context_a())
    assert denied.status == "DENIED"
    assert denied.reason == "APPROVAL_MISMATCH"


def test_adopted_successor_cap_is_applied(admission_service, fresh_owner) -> None:
    first = intent_entry(quantity_raw="10", quote_input_raw="300", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, first, approval_a(quote_approved_raw="500"),
                                               context_a()).status == "ADMITTED"
    admission_service.cancel(fresh_owner, first.action_id)
    second = intent_entry(quantity_raw="10", quote_input_raw="200", position_id="position-a-2")
    denied = admission_service.admit_and_reserve(
        fresh_owner, second, approval_a(quote_approved_raw="100", approval_id="approval-successor"), context_a())
    assert denied.status == "DENIED" and denied.reason == "CAPACITY_UNAVAILABLE"
    assert _one(admission_service.balances(fresh_owner), QUOTE).approved_raw == "100"


# ---------------------------------------------------------------- B5

def test_actual_gas_respects_other_outstanding_reservations(admission_service, fresh_owner) -> None:
    approval = approval_a(gas_approved_raw="4", per_action_gas_raw="2", per_exit_gas_raw="0")
    first = intent_entry(quantity_raw="1", quote_input_raw="50", position_id="position-a-1")
    second = intent_entry(quantity_raw="1", quote_input_raw="50", position_id="position-a-2")
    assert admission_service.admit_and_reserve(fresh_owner, first, approval, context_a()).status == "ADMITTED"
    assert admission_service.admit_and_reserve(fresh_owner, second, approval, context_a()).status == "ADMITTED"
    # First reconciles at actual gas 3. Consumed 3 + the other action's reserved 2 exceeds approved 4.
    outcome = admission_service.reconcile(fresh_owner, first.action_id, confirm_entry(first, "50", "1", "3"))
    assert outcome.reason == "CONSUMED_EXCEEDS_APPROVED"
    assert _one(admission_service.balances(fresh_owner), NATIVE).consumed_raw == "0"


# ---------------------------------------------------------------- B6

def test_large_integer_accounting_is_exact(admission_service, fresh_owner) -> None:
    big = "1100000000000000000000000000001"
    approval = approval_a(quote_approved_raw=big, allocation_quote_raw=big)
    intent = intent_entry(quantity_raw="10", quote_input_raw=big, position_id="position-a-1")
    context = context_a(quote_raw=big)
    decision = admission_service.admit_and_reserve(fresh_owner, intent, approval, context)
    assert decision.status == "ADMITTED", decision.reason
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, confirm_entry(intent, big, "10", "1"))
    assert outcome.decision_status == "CONFIRMED"
    assert _one(admission_service.balances(fresh_owner), QUOTE).consumed_raw == big


def test_decimal_drift_is_denied(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1", quote_decimals=18)
    denied = admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    assert denied.status == "DENIED"
    assert "QUOTE_DECIMALS_MISMATCH" in denied.reason


def test_oversized_raw_is_rejected_by_validation() -> None:
    import pytest
    from edge_os_api.admission.types import MAX_RAW_DIGITS

    with pytest.raises(Exception):
        AssetAmount(asset_id=QUOTE, raw="1" * (MAX_RAW_DIGITS + 1), decimals=0)


# ---------------------------------------------------------------- B7

def test_acquisition_cannot_exceed_remaining_sell_ceiling(admission_service, fresh_owner) -> None:
    approval = approval_a(base_approved_raw="10")
    first = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, first, approval, context_a()).status == "ADMITTED"
    admission_service.reconcile(fresh_owner, first.action_id, confirm_entry(first, "110", "10", "1"))
    second = intent_entry(quantity_raw="1", quote_input_raw="20", position_id="position-a-2")
    denied = admission_service.admit_and_reserve(fresh_owner, second, approval, context_a())
    assert denied.status == "DENIED" and denied.reason == "SELL_CAPACITY_UNAVAILABLE"


def test_favorable_overfill_beyond_sell_ceiling_fails_closed(admission_service, fresh_owner) -> None:
    approval = approval_a(base_approved_raw="10")
    entry = intent_entry(quantity_raw="1", quote_input_raw="20", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a()).status == "ADMITTED"
    outcome = admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "20", "11", "1"))
    assert outcome.reason == "SELL_COVERAGE_EXCEEDED"
    base = _one(admission_service.balances(fresh_owner), BASE)
    assert base.consumed_raw == "0" and base.reserved_raw == "1"


def test_reconciled_input_beyond_allocation_fails_closed(admission_service, fresh_owner) -> None:
    approval = approval_a(allocation_quote_raw="100", quote_approved_raw="1000")
    entry = intent_entry(quantity_raw="1", quote_input_raw="50", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a()).status == "ADMITTED"
    outcome = admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "150", "1", "1"))
    assert outcome.reason == "ALLOCATION_EXCEEDED"
    assert _one(admission_service.balances(fresh_owner), QUOTE).consumed_raw == "0"


def test_reconcile_and_admission_serialize_on_wallet_lock(admission_service, fresh_owner) -> None:
    approval = approval_a()
    first = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, first, approval, context_a())
    second = intent_entry(quantity_raw="5", quote_input_raw="60", position_id="position-a-2")

    def reconcile_first(index):
        return admission_service.reconcile(fresh_owner, first.action_id, confirm_entry(first, "110", "10", "1"))

    def admit_second(index):
        return admission_service.admit_and_reserve(fresh_owner, second, approval, context_a())

    outcomes = _run_concurrently(2, lambda i: reconcile_first(i) if i == 0 else admit_second(i))
    assert any(getattr(o, "decision_status", None) == "CONFIRMED" for o in outcomes)
    # Invariant holds after concurrent reconcile and admission: consumed + reserved <= approved.
    for summary in admission_service.balances(fresh_owner):
        assert int(summary.consumed_raw) + int(summary.reserved_raw) <= int(summary.approved_raw)

def test_scoped_stop_denies_acquisitions(admission_service, fresh_owner) -> None:
    denied = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-1"),
        approval_a(stops=("STOP_NEW_ENTRIES",)), context_a())
    assert denied.status == "DENIED" and "STOPPED_NEW_ENTRIES" in denied.reason
    halted = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-1"),
        approval_a(stops=("HALT_ALL_SWAPS",)), context_a())
    assert "STOPPED_HALT_ALL_SWAPS" in halted.reason


def test_position_stop_applies_only_to_its_target(admission_service, fresh_owner) -> None:
    approval = approval_a(stops=("POSITION:position-a-1:STOP_NEW_ENTRIES",))
    blocked = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-1"), approval, context_a())
    assert blocked.status == "DENIED" and "STOPPED_NEW_ENTRIES" in blocked.reason
    allowed = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-2"), approval, context_a())
    assert allowed.status == "ADMITTED"


def test_unqualified_controls_fail_closed(admission_service, fresh_owner) -> None:
    entry_denied = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-1"),
        approval_a(exit_capacity_qualified=False), context_a())
    assert "EXIT_CAPACITY_UNQUALIFIED" in entry_denied.reason

    approval = approval_a(valuation_qualified=False)
    entry = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a()).status == "ADMITTED"
    admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "110", "10", "1"))
    exit_denied = admission_service.admit_and_reserve(
        fresh_owner, intent_exit(quantity_raw="5"), approval, context_a(position_inventory="10"))
    assert "VALUATION_UNQUALIFIED" in exit_denied.reason


# ---------------------------------------------------------------- B9

def test_confirm_without_reconciled_actuals_is_denied(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    bare = ActionReceipt(action_id=intent.action_id, binding=intent.binding, outcome="CONFIRMED")
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, bare)
    assert outcome.reason == "MISSING_RECONCILED_INPUT"
    assert _one(admission_service.balances(fresh_owner), QUOTE).consumed_raw == "0"


def test_weighted_basis_realized_on_partial_exit(admission_service, admission_engine, fresh_owner) -> None:
    approval = approval_a(quote_approved_raw="5000")
    entry = intent_entry(quantity_raw="10", quote_input_raw="1000", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "1000", "10", "1"))
    addition = intent_a("ADDITION", "10", quote_input_raw="1200", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, addition, approval, context_a(position_inventory="10"))
    admission_service.reconcile(fresh_owner, addition.action_id, confirm_entry(addition, "1200", "10", "1"))
    with admission_engine.connect() as connection:
        inventory, basis = connection.execute(text(
            "SELECT inventory, cost_basis FROM admission_positions WHERE owner_id = :owner"
        ), {"owner": str(fresh_owner)}).one()
    # Weighted average basis 2200/20 = 110; exit 5 removes 550 and realizes 650 - 550 = 100.
    assert (int(inventory), int(basis)) == (20, 2200)
    exit_intent = intent_exit(quantity_raw="5")
    admission_service.admit_and_reserve(fresh_owner, exit_intent, approval, context_a(position_inventory="20"))
    admission_service.reconcile(fresh_owner, exit_intent.action_id, confirm_exit(exit_intent, "5", "650", "1"))
    with admission_engine.connect() as connection:
        inventory, basis, realized = connection.execute(text(
            "SELECT inventory, cost_basis, realized_quote FROM admission_positions WHERE owner_id = :owner"
        ), {"owner": str(fresh_owner)}).one()
    assert (int(inventory), int(basis), int(realized)) == (15, 1650, 100)

# ---------------------------------------------------------------- R1

def test_addition_to_other_wallet_position_is_denied(admission_service, fresh_owner) -> None:
    entry = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "110", "10", "1"))
    cross = intent_a("ADDITION", "5", quote_input_raw="50", position_id="position-a-1",
                     binding=binding_b(), policy_binding="policy-b-v1")
    denied = admission_service.admit_and_reserve(
        fresh_owner, cross, approval_b(), context_b())
    assert denied.status == "DENIED"
    assert "POSITION_BINDING_MISMATCH" in denied.reason or "POSITION_MISSING" in denied.reason


# ---------------------------------------------------------------- R2

def test_exit_output_wrong_quote_decimals_fails_closed(admission_service, fresh_owner) -> None:
    entry = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "110", "10", "1"))
    exit_intent = intent_exit(quantity_raw="5")
    admission_service.admit_and_reserve(fresh_owner, exit_intent, approval_a(), context_a(position_inventory="10"))
    bad = ActionReceipt(
        action_id=exit_intent.action_id, binding=exit_intent.binding, outcome="CONFIRMED",
        actual_input=AssetAmount(asset_id=BASE, raw="5", decimals=0),
        actual_output=AssetAmount(asset_id=QUOTE, raw="250", decimals=18),
        actual_gas=AssetAmount(asset_id=NATIVE, raw="1", decimals=0))
    outcome = admission_service.reconcile(fresh_owner, exit_intent.action_id, bad)
    assert outcome.reason == "MISSING_RECONCILED_OUTPUT"
    assert outcome.decision_status == "BREACHED"


# ---------------------------------------------------------------- R3

def test_changed_attempt_budget_under_same_approval_is_denied(admission_service, fresh_owner) -> None:
    first = intent_entry(quantity_raw="1", quote_input_raw="20", position_id="position-a-1")
    assert admission_service.admit_and_reserve(
        fresh_owner, first, approval_a(attempt_budget=2), context_a()).status == "ADMITTED"
    admission_service.cancel(fresh_owner, first.action_id)
    second = intent_entry(quantity_raw="1", quote_input_raw="20", position_id="position-a-2")
    denied = admission_service.admit_and_reserve(
        fresh_owner, second, approval_a(attempt_budget=5), context_a())
    assert denied.status == "DENIED" and denied.reason == "APPROVAL_MISMATCH"


# ---------------------------------------------------------------- R4

def test_exit_actual_cannot_consume_another_reserved_exit(admission_service, fresh_owner) -> None:
    entry = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "110", "10", "1"))
    first_exit = intent_exit(quantity_raw="5")
    second_exit = intent_exit(quantity_raw="5")
    assert admission_service.admit_and_reserve(
        fresh_owner, first_exit, approval_a(), context_a(position_inventory="10")).status == "ADMITTED"
    assert admission_service.admit_and_reserve(
        fresh_owner, second_exit, approval_a(), context_a(position_inventory="10")).status == "ADMITTED"
    outcome = admission_service.reconcile(fresh_owner, first_exit.action_id, confirm_exit(first_exit, "6", "300", "1"))
    assert outcome.reason == "EXIT_EXCEEDS_RESERVED"
    assert outcome.decision_status == "BREACHED"


# ---------------------------------------------------------------- R5

def test_entry_denied_when_intended_exit_not_coverable(admission_service, fresh_owner) -> None:
    # Attempt budget 1 cannot cover the entry plus its intended exit (two atoms).
    denied = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-1"),
        approval_a(attempt_budget=1), context_a())
    assert denied.status == "DENIED" and denied.reason == "ATTEMPT_BUDGET_EXHAUSTED"


def test_breach_blocks_new_work_and_keeps_receipt(admission_service, fresh_owner) -> None:
    approval = approval_a(base_approved_raw="10")
    entry = intent_entry(quantity_raw="1", quote_input_raw="20", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval, context_a())
    outcome = admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "20", "11", "1"))
    assert outcome.reason == "SELL_COVERAGE_EXCEEDED"
    assert outcome.decision_status == "BREACHED"
    blocked = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-2"), approval, context_a())
    assert blocked.status == "DENIED" and blocked.reason == "UNRESOLVED_PRIOR_ACTION"
    receipts = admission_service.retrieve_receipts(fresh_owner, action_id=entry.action_id)
    assert receipts and receipts[0].breach is True


# ---------------------------------------------------------------- R6

def test_entry_denied_without_cost_qualification(admission_service, fresh_owner) -> None:
    denied = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="position-a-1"),
        approval_a(cost_model_qualified=False), context_a())
    assert denied.status == "DENIED" and "COST_MODEL_UNQUALIFIED" in denied.reason


# ---------------------------------------------------------------- R7

def test_concurrent_identical_admission_returns_same_decision(admission_service, fresh_owner) -> None:
    intent = intent_entry(action_id="action-identical", quantity_raw="10", quote_input_raw="110")

    def admit(index):
        return admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())

    results = _run_concurrently(2, admit)
    assert all(r.status == "ADMITTED" for r in results), [r.status for r in results]
    assert len({r.decision_id for r in results}) == 1


# ---------------------------------------------------------------- R8

def test_receipt_lineage_is_persisted(admission_service, fresh_owner) -> None:
    entry = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, confirm_entry(entry, "110", "10", "1"))
    receipts = admission_service.retrieve_receipts(fresh_owner)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.action_id == entry.action_id and receipt.outcome == "CONFIRMED" and receipt.breach is False
    assert receipt.content["actual_input"] == {"asset_id": QUOTE, "raw": "110", "decimals": 0}
    assert receipt.content["actual_output"] == {"asset_id": BASE, "raw": "10", "decimals": 0}
