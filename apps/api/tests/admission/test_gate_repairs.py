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
    approval = approval_a(gas_approved_raw="4", per_action_gas_raw="2")
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


# ---------------------------------------------------------------- B8

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