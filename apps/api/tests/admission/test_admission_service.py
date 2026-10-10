"""Behavioral tests for proposed/admitted decisions, denials, retrieval, balances,
cancellation and reconciliation. Persistence is cross-checked with direct SQL.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from edge_os_api.admission.models import (
    AllowanceRow,
    DecisionRow,
    PositionRow,
    ReservationRow,
)
from edge_os_api.admission.service import StaleInput
from edge_os_api.admission.types import ActionReceipt, IdentityBinding

from admission._builders import (
    AGENT_A,
    BASE,
    NETWORK,
    NATIVE,
    OWNER_A,
    OWNER_B,
    POSITION_A,
    QUOTE,
    WALLET_A,
    approval_a,
    context_a,
    holdings_a,
    intent_addition,
    intent_entry,
    intent_exit,
)


def _amount(asset_id: str, raw: str) -> int:
    return int(raw)


def _one(summary_list, asset_id: str):
    for summary in summary_list:
        if summary.asset_id == asset_id:
            return summary
    raise AssertionError(f"no allowance for {asset_id}")


# --------------------------------------------------------------- propose

def test_propose_valid_entry_is_proposed(admission_service, fresh_owner) -> None:
    decision = admission_service.propose(fresh_owner, intent_entry(), approval_a(), context_a())
    assert decision.status == "PROPOSED"
    assert not decision.reservations


@pytest.mark.parametrize("state,expires,expected", [
    ("EXPIRED", "2030-01-01T00:00:00Z", "APPROVAL_STATE:EXPIRED"),
    ("REVOKED", "2030-01-01T00:00:00Z", "APPROVAL_STATE:REVOKED"),
    ("ACTIVE", "2020-01-01T00:00:00Z", "APPROVAL_EXPIRED"),
])
def test_propose_denies_inactive_authority(admission_service, fresh_owner, state, expires, expected) -> None:
    approval = approval_a(state=state, expires_at=expires)
    decision = admission_service.propose(fresh_owner, intent_entry(), approval, context_a())
    assert decision.status == "DENIED"
    assert expected in decision.reason


def test_propose_denies_policy_mismatch(admission_service, fresh_owner) -> None:
    intent = intent_entry(policy_binding="policy-other")
    decision = admission_service.propose(fresh_owner, intent, approval_a(), context_a())
    assert decision.status == "DENIED"
    assert "POLICY_MISMATCH" in decision.reason


# ------------------------------------------------------- admit and denials

def test_entry_is_admitted_and_persisted(admission_service, admission_engine, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110")
    decision = admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    assert decision.status == "ADMITTED"
    assert decision.reason is None
    assert len(decision.reservations) == 4  # capital quote, capital base, inventory, gas

    with admission_engine.connect() as connection:
        decisions = connection.execute(text(
            "SELECT action_id, status FROM admission_decisions WHERE owner_id = :owner"
        ), {"owner": str(fresh_owner)}).all()
        reservations = connection.execute(text(
            "SELECT scope, asset_id, raw, state FROM admission_reservations WHERE owner_id = :owner AND action_id = :action"
        ), {"owner": str(fresh_owner), "action": intent.action_id}).all()
        allowance_quote = connection.execute(text(
            "SELECT approved, consumed FROM admission_allowances WHERE owner_id = :owner AND asset_id = :asset"
        ), {"owner": str(fresh_owner), "asset": QUOTE}).one()

    assert (intent.action_id, "ADMITTED") in decisions
    assert {("CAPITAL", QUOTE, 110, "RESERVED"), ("CAPITAL", BASE, 10, "RESERVED"),
            ("INVENTORY", BASE, 10, "RESERVED"), ("GAS", NATIVE, 2, "RESERVED")} == {
        (r.scope, r.asset_id, int(r.raw), r.state) for r in reservations
    }
    assert int(allowance_quote.approved) == 500
    assert int(allowance_quote.consumed) == 0


def test_second_entry_denied_when_allowance_exhausted(admission_service, fresh_owner) -> None:
    first = intent_entry(quantity_raw="10", quote_input_raw="300", position_id="position-a-1")
    assert admission_service.admit_and_reserve(fresh_owner, first, approval_a(), context_a()).status == "ADMITTED"
    second = intent_entry(quantity_raw="10", quote_input_raw="300", position_id="position-a-2")
    denied = admission_service.admit_and_reserve(fresh_owner, second, approval_a(), context_a())
    assert denied.status == "DENIED"
    assert denied.reason == "CAPACITY_UNAVAILABLE"


def test_deposit_does_not_enlarge_authority(admission_service, fresh_owner) -> None:
    approval = approval_a(quote_approved_raw="100")
    big_holdings = context_a(quote_raw="999999")
    first = intent_entry(quantity_raw="1", quote_input_raw="60", position_id="position-a-1")
    second = intent_entry(quantity_raw="1", quote_input_raw="60", position_id="position-a-2")
    assert admission_service.admit_and_reserve(fresh_owner, first, approval, big_holdings).status == "ADMITTED"
    denied = admission_service.admit_and_reserve(fresh_owner, second, approval, big_holdings)
    assert denied.status == "DENIED" and denied.reason == "CAPACITY_UNAVAILABLE"


def test_denial_is_saved_with_reason(admission_service, admission_engine, fresh_owner) -> None:
    approval = approval_a(expires_at="2020-01-01T00:00:00Z")
    intent = intent_entry()
    decision = admission_service.admit_and_reserve(fresh_owner, intent, approval, context_a())
    assert decision.status == "DENIED" and "APPROVAL_EXPIRED" in decision.reason
    with admission_engine.connect() as connection:
        row = connection.execute(text(
            "SELECT status, reason FROM admission_decisions WHERE owner_id = :owner AND action_id = :action"
        ), {"owner": str(fresh_owner), "action": intent.action_id}).one()
        reservations = connection.execute(text(
            "SELECT count(*) FROM admission_reservations WHERE owner_id = :owner AND action_id = :action"
        ), {"owner": str(fresh_owner), "action": intent.action_id}).scalar_one()
    assert row.status == "DENIED"
    assert "APPROVAL_EXPIRED" in row.reason
    assert reservations == 0


def test_exit_denied_without_known_valuation(admission_service, fresh_owner) -> None:
    intent = intent_exit(quantity_raw="5", mark="UNKNOWN")
    decision = admission_service.admit_and_reserve(
        fresh_owner, intent, approval_a(),
        context_a(position_inventory="10"),
    )
    assert decision.status == "DENIED"
    assert "MISSING_VALUATION" in decision.reason


def test_external_discrepancy_denies(admission_service, fresh_owner) -> None:
    decision = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(), approval_a(), context_a(unexplained=True)
    )
    assert decision.status == "DENIED"
    assert "EXTERNAL_DISCREPANCY" in decision.reason


def test_cross_wallet_binding_denies(admission_service, fresh_owner) -> None:
    other_binding = IdentityBinding(agent_id="agent-b", wallet_id="wallet-b", network_id=NETWORK,
                                    strategy_revision="strategy-b-v5", mandate_id="mandate-b-v1")
    intent = intent_entry(binding=other_binding)
    decision = admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    assert decision.status == "DENIED"
    assert "BINDING_MISMATCH" in decision.reason
    assert "CROSS_WALLET_BINDING" in decision.reason


def test_entry_into_existing_position_denied(admission_service, fresh_owner) -> None:
    decision = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id=POSITION_A), approval_a(),
        context_a(position_inventory="10"),
    )
    assert decision.status == "DENIED"
    assert "POSITION_EXISTS" in decision.reason


def test_unsupported_action_denied(admission_service, fresh_owner) -> None:
    approval = approval_a(actions=("EXIT",))
    decision = admission_service.admit_and_reserve(fresh_owner, intent_entry(), approval, context_a())
    assert decision.status == "DENIED"
    assert "UNSUPPORTED_ACTION" in decision.reason


def test_same_action_id_preserves_idempotent_identity(admission_service, fresh_owner) -> None:
    intent = intent_entry(action_id="action-idempotent")
    first = admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    second = admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    assert first.decision_id == second.decision_id
    assert second.status == "ADMITTED"
    assert len(second.reservations) == 4


def test_changed_review_hash_for_same_action_is_stale(admission_service, fresh_owner) -> None:
    intent = intent_entry(action_id="action-stale")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    changed = intent.model_copy(update={"review_hash": "sha256:" + "b" * 64})
    with pytest.raises(StaleInput):
        admission_service.admit_and_reserve(fresh_owner, changed, approval_a(), context_a())


# --------------------------------------------------------------- retrieval

def test_retrieval_is_owner_scoped(admission_service, fresh_owner) -> None:
    intent = intent_entry(action_id="action-owner-scoped")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    owned = admission_service.retrieve_decisions(fresh_owner)
    other = admission_service.retrieve_decisions(uuid.uuid4())
    assert len(owned) == 1 and owned[0].action_id == intent.action_id
    assert other == []


def test_retrieve_reservations_and_balances(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    reservations = admission_service.retrieve_reservations(
        fresh_owner, wallet_id=WALLET_A, network_id=NETWORK, asset_id=BASE)
    assert {r.amount.raw for r in reservations} == {"10"}

    summaries = admission_service.balances(fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    quote = _one(summaries, QUOTE)
    base = _one(summaries, BASE)
    gas = _one(summaries, NATIVE)
    assert (quote.approved_raw, quote.consumed_raw, quote.reserved_raw, quote.remaining_raw) == ("500", "0", "110", "390")
    assert (base.approved_raw, base.consumed_raw, base.reserved_raw, base.remaining_raw) == ("1000", "0", "10", "990")
    assert (gas.approved_raw, gas.consumed_raw, gas.reserved_raw, gas.remaining_raw) == ("50", "0", "2", "48")


# ----------------------------------------------------------------- cancel

def test_cancel_releases_reservations(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110")
    admitted = admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    assert admitted.status == "ADMITTED"
    outcome = admission_service.cancel(fresh_owner, intent.action_id)
    assert outcome.decision_status == "CANCELLED"
    assert len(outcome.released) == 4
    remaining = [s for s in admission_service.balances(fresh_owner, wallet_id=WALLET_A, network_id=NETWORK)
                 if s.asset_id in (QUOTE, BASE, NATIVE)]
    assert all(s.reserved_raw == "0" for s in remaining)


# -------------------------------------------------------------- reconcile

def test_confirm_entry_consumes_quote_and_attributes_inventory(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="CONFIRMED",
        actual_gas=_gas(1),
    ))
    assert outcome.decision_status == "CONFIRMED"
    quote = _one(admission_service.balances(fresh_owner), QUOTE)
    base = _one(admission_service.balances(fresh_owner), BASE)
    gas = _one(admission_service.balances(fresh_owner), NATIVE)
    assert quote.consumed_raw == "110" and quote.reserved_raw == "0"
    assert base.consumed_raw == "0" and base.reserved_raw == "0"
    assert gas.consumed_raw == "1" and gas.reserved_raw == "0"


def test_revert_entry_releases_input_and_consumes_gas(admission_service, admission_engine, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="REVERTED",
        actual_gas=_gas(2),
    ))
    assert outcome.decision_status == "REVERTED"
    quote = _one(admission_service.balances(fresh_owner), QUOTE)
    assert quote.consumed_raw == "0" and quote.reserved_raw == "0"
    with admission_engine.connect() as connection:
        state = connection.execute(text(
            "SELECT state FROM admission_reservations WHERE owner_id = :owner AND scope = 'CAPITAL' AND asset_id = :asset"
        ), {"owner": str(fresh_owner), "asset": QUOTE}).scalars().all()
    assert set(state) == {"RELEASED"}


def test_prebroadcast_denial_consumes_neither(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="PREBROADCAST_DENIED"))
    assert outcome.decision_status == "DENIED"
    assert outcome.reason == "PREBROADCAST_DENIED"
    for summary in admission_service.balances(fresh_owner):
        assert summary.consumed_raw == "0"
        assert summary.reserved_raw == "0"


def test_submission_unknown_retains_reservations(admission_service, fresh_owner) -> None:
    intent = intent_entry(quantity_raw="10", quote_input_raw="110")
    admission_service.admit_and_reserve(fresh_owner, intent, approval_a(), context_a())
    outcome = admission_service.reconcile(fresh_owner, intent.action_id, ActionReceipt(
        action_id=intent.action_id, binding=intent.binding, outcome="SUBMISSION_UNKNOWN"))
    assert outcome.decision_status == "SUBMISSION_UNKNOWN"
    retained = [amount.raw for amount in outcome.retained]
    assert sorted(retained) == ["10", "10", "110", "2"]
    quote = _one(admission_service.balances(fresh_owner), QUOTE)
    assert quote.reserved_raw == "110"

    # A second economic action for the same wallet/network stays blocked while
    # the outcome is unknown.
    blocked = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(quantity_raw="10", quote_input_raw="110", position_id="position-a-2"),
        approval_a(), context_a())
    assert blocked.status == "DENIED"
    assert blocked.reason == "UNRESOLVED_PRIOR_ACTION"


def test_confirm_exit_consumes_base_and_reduces_inventory(admission_service, admission_engine, fresh_owner) -> None:
    entry = intent_entry(quantity_raw="10", quote_input_raw="110")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, ActionReceipt(
        action_id=entry.action_id, binding=entry.binding, outcome="CONFIRMED", actual_gas=_gas(1)))

    exit_intent = intent_exit(quantity_raw="5")
    admitted = admission_service.admit_and_reserve(
        fresh_owner, exit_intent, approval_a(), context_a(position_inventory="10"))
    assert admitted.status == "ADMITTED"
    outcome = admission_service.reconcile(fresh_owner, exit_intent.action_id, ActionReceipt(
        action_id=exit_intent.action_id, binding=exit_intent.binding, outcome="CONFIRMED",
        actual_gas=_gas(1),
    ))
    assert outcome.decision_status == "CONFIRMED"
    base = _one(admission_service.balances(fresh_owner), BASE)
    assert base.consumed_raw == "5" and base.reserved_raw == "0"
    with admission_engine.connect() as connection:
        inventory = connection.execute(text(
            "SELECT inventory FROM admission_positions WHERE owner_id = :owner AND position_id = :position"
        ), {"owner": str(fresh_owner), "position": POSITION_A}).scalar_one()
    assert int(inventory) == 5


def test_addition_confirm_grows_position(admission_service, admission_engine, fresh_owner) -> None:
    entry = intent_entry(quantity_raw="10", quote_input_raw="110")
    admission_service.admit_and_reserve(fresh_owner, entry, approval_a(), context_a())
    admission_service.reconcile(fresh_owner, entry.action_id, ActionReceipt(
        action_id=entry.action_id, binding=entry.binding, outcome="CONFIRMED", actual_gas=_gas(1)))

    addition = intent_addition(quantity_raw="5", quote_input_raw="60")
    admission_service.admit_and_reserve(fresh_owner, addition, approval_a(),
                                        context_a(position_inventory="10"))
    admission_service.reconcile(fresh_owner, addition.action_id, ActionReceipt(
        action_id=addition.action_id, binding=addition.binding, outcome="CONFIRMED", actual_gas=_gas(1)))
    with admission_engine.connect() as connection:
        inventory = connection.execute(text(
            "SELECT inventory FROM admission_positions WHERE owner_id = :owner AND position_id = :position"
        ), {"owner": str(fresh_owner), "position": POSITION_A}).scalar_one()
    assert int(inventory) == 15


def _gas(raw: str | int) -> object:
    from admission._builders import NATIVE
    from edge_os_api.admission.types import AssetAmount
    return AssetAmount(asset_id=NATIVE, raw=str(raw), decimals=0)