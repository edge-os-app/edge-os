"""Repair-slice tests: attempt budgets and effects, wallet-scoped capacity,
terminal-reconcile guard, consumption caps and reconciled-actual validation."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from edge_os_api.admission.types import ActionReceipt, AssetAmount

from admission._builders import (
    NATIVE,
    NETWORK,
    QUOTE,
    WALLET_A,
    WALLET_B,
    approval_a,
    approval_b,
    context_a,
    context_b,
    intent_entry,
    intent_entry_b,
)


def _one(summaries, asset_id: str):
    for summary in summaries:
        if summary.asset_id == asset_id:
            return summary
    raise AssertionError(f"no allowance for {asset_id}")


def _gas(raw: str) -> AssetAmount:
    return AssetAmount(asset_id=NATIVE, raw=raw, decimals=0)


def test_attempt_budget_exhausted(admission_service, fresh_owner) -> None:
    approval = approval_a(attempt_budget=1)
    first = intent_entry(position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, first, approval, context_a()).status == "ADMITTED"
    second = intent_entry(position_id="position-a-2")
    denied = admission_service.admit_and_reserve(fresh_owner, second, approval, context_a())
    assert denied.status == "DENIED"
    assert denied.reason == "ATTEMPT_BUDGET_EXHAUSTED"


def test_revert_consumes_attempt_but_prebroadcast_does_not(admission_service, admission_engine, fresh_owner) -> None:
    reverted = intent_entry(position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, reverted, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, reverted.action_id, ActionReceipt(
        action_id=reverted.action_id, binding=reverted.binding, outcome="REVERTED", actual_gas=_gas("1")))

    denied = intent_entry(position_id="position-a-2")
    admission_service.admit_and_reserve(fresh_owner, denied, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, denied.action_id, ActionReceipt(
        action_id=denied.action_id, binding=denied.binding, outcome="PREBROADCAST_DENIED"))

    with admission_engine.connect() as connection:
        states = dict(connection.execute(text(
            "SELECT action_id, state FROM admission_reservations "
            "WHERE owner_id = :owner AND scope = 'ATTEMPT'"
        ), {"owner": str(fresh_owner)}).all())
    assert states[reverted.action_id] == "CONSUMED"
    assert states[denied.action_id] == "RELEASED"


def test_reservations_and_balances_are_wallet_scoped(admission_service, fresh_owner) -> None:
    a_intent = intent_entry(quantity_raw="10", quote_input_raw="300", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, a_intent, approval_a(), context_a()).status == "ADMITTED"

    b_intent = intent_entry_b(quantity_raw="10", quote_input_raw="300")
    b_decision = admission_service.admit_and_reserve(fresh_owner, b_intent, approval_b(), context_b())
    assert b_decision.status == "ADMITTED"

    a_quote = _one(admission_service.balances(fresh_owner, wallet_id=WALLET_A, network_id=NETWORK), QUOTE)
    b_quote = _one(admission_service.balances(fresh_owner, wallet_id=WALLET_B, network_id=NETWORK), QUOTE)
    assert a_quote.reserved_raw == "300"
    assert b_quote.reserved_raw == "300"


def test_second_reconcile_of_terminal_action_is_ignored(admission_service, fresh_owner) -> None:
    intent = intent_entry(position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    first = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="CONFIRMED", actual_gas=_gas("1")))
    assert first.decision_status == "CONFIRMED"

    late = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="SUBMISSION_UNKNOWN"))
    assert late.decision_status == "CONFIRMED"
    assert late.reason == "RECONCILIATION_TERMINAL_STATE"
    quote = _one(admission_service.balances(fresh_owner), QUOTE)
    assert quote.consumed_raw == "110"  # unchanged by the late receipt


def test_actual_gas_over_cap_fails_closed(admission_service, fresh_owner) -> None:
    approval = approval_a(gas_approved_raw="1", per_action_gas_raw="1")
    intent = intent_entry(position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, intent, approval, context_a()).status == "ADMITTED"
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="CONFIRMED", actual_gas=_gas("5")))
    assert outcome.reason == "CONSUMED_EXCEEDS_APPROVED"
    assert outcome.decision_status == "ADMITTED"  # rollback; terminal state not reached
    gas = _one(admission_service.balances(fresh_owner), NATIVE)
    assert gas.consumed_raw == "0"


def test_reconciled_actual_quantity_mismatch_fails_closed(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="CONFIRMED", actual_gas=_gas("1"),
        actual_quantity=AssetAmount(asset_id=QUOTE, raw="999", decimals=0)))
    assert outcome.reason == "RECEIPT_QUANTITY_MISMATCH"
    assert outcome.decision_status == "ADMITTED"
    assert _one(admission_service.balances(fresh_owner), QUOTE).consumed_raw == "0"


def test_reconciled_actual_quantity_match_commits(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-1")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="CONFIRMED", actual_gas=_gas("1"),
        actual_quantity=AssetAmount(asset_id=QUOTE, raw="110", decimals=0)))
    assert outcome.decision_status == "CONFIRMED"
    assert _one(admission_service.balances(fresh_owner), QUOTE).consumed_raw == "110"