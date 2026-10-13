from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from edge_os_api.replay.proposed_accounting import (
    ProposedCostAssumptions,
    ProposedEntryRequest,
    ProposedExitRequest,
    ProposedReplayTick,
    ProposedSharedCapitalLedger,
    run_proposed_accounting_replay,
)


def _costs(fee: str = "0.001", slippage: str = "0") -> ProposedCostAssumptions:
    return ProposedCostAssumptions(Decimal(fee), Decimal(slippage), "synthetic-p14-edge")


def _funded_position(ledger: ProposedSharedCapitalLedger, position_id: str = "position-a") -> None:
    reserved, = ledger.reserve_entries(
        (ProposedEntryRequest("entry-1", position_id, Decimal("400")),), _costs(),
    )
    assert reserved.status == "RESERVED"
    assert ledger.settle_entry("entry-1", Decimal("8")).status == "FILLED"


@pytest.mark.parametrize(
    "costs",
    (
        None,
        ProposedCostAssumptions(Decimal("-0.001"), Decimal("0"), "cost"),
        ProposedCostAssumptions(Decimal("1.001"), Decimal("0"), "cost"),
        ProposedCostAssumptions(Decimal("0"), Decimal("-0.001"), "cost"),
        ProposedCostAssumptions(Decimal("0"), Decimal("1"), "cost"),
        ProposedCostAssumptions(Decimal("0"), Decimal("0"), ""),
    ),
)
def test_invalid_or_unknown_costs_never_become_zero_costs(costs: ProposedCostAssumptions | None) -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))

    outcome, = ledger.reserve_entries(
        (ProposedEntryRequest("entry-1", "position-a", Decimal("400")),), costs,
    )

    assert outcome.status == "COST_UNAVAILABLE"
    assert ledger.cash_quote == ledger.free_cash_quote == Decimal("1000")
    assert ledger.positions == {}


@pytest.mark.parametrize("price", (Decimal("0"), Decimal("-1"), Decimal("NaN")))
def test_bad_buy_fills_release_the_reservation_without_cash_or_inventory_mutation(price: Decimal) -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))
    ledger.reserve_entries((ProposedEntryRequest("entry-1", "position-a", Decimal("400")),), _costs())

    outcome = ledger.settle_entry("entry-1", price)

    assert outcome.status == "NON_POSITIVE_FILL"
    assert outcome.details["reservation_released_quote"] == Decimal("400.400")
    assert ledger.cash_quote == ledger.free_cash_quote == Decimal("1000")
    assert ledger.positions == {}


def test_exit_reservations_prevent_double_sale_and_an_unavailable_fill_releases_inventory() -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))
    _funded_position(ledger)

    first, = ledger.reserve_exits((ProposedExitRequest("exit-1", "position-a", None),), _costs())
    blocked, = ledger.reserve_exits((ProposedExitRequest("exit-2", "position-a", Decimal("1")),), _costs())
    released = ledger.settle_exit("exit-1", None)
    retry, = ledger.reserve_exits((ProposedExitRequest("exit-2", "position-a", Decimal("1")),), _costs())

    assert first.status == "RESERVED"
    assert blocked.status == "INVALID_BASE_AMOUNT"
    assert released.status == "FILL_UNAVAILABLE"
    assert released.details["reservation_released_base"] == Decimal("50")
    assert retry.status == "RESERVED"
    position = ledger.positions["position-a"]
    assert (ledger.cash_quote, position.base_amount, position.basis_quote, position.realized_quote) == (
        Decimal("599.600"), Decimal("50"), Decimal("400.400"), Decimal("0"),
    )


@pytest.mark.parametrize("price", (Decimal("0"), Decimal("-1"), Decimal("NaN")))
def test_bad_exit_fills_do_not_sell_inventory_or_charge_a_fee(price: Decimal) -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))
    _funded_position(ledger)
    ledger.reserve_exits((ProposedExitRequest("exit-1", "position-a", Decimal("10")),), _costs())

    outcome = ledger.settle_exit("exit-1", price)

    assert outcome.status == "NON_POSITIVE_FILL"
    position = ledger.positions["position-a"]
    assert (ledger.cash_quote, position.base_amount, position.basis_quote, position.fees_quote) == (
        Decimal("599.600"), Decimal("50"), Decimal("400.400"), Decimal("0.400"),
    )


def test_request_ids_are_global_across_entry_and_exit_reservations() -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))
    _funded_position(ledger)
    exit_reserved, = ledger.reserve_exits((ProposedExitRequest("shared-id", "position-a", Decimal("1")),), _costs())
    duplicate, = ledger.reserve_entries(
        (ProposedEntryRequest("shared-id", "position-b", Decimal("1")),), _costs(),
    )

    assert exit_reserved.status == "RESERVED"
    assert duplicate.status == "DUPLICATE_REQUEST"
    assert ledger.free_cash_quote == Decimal("599.600")


def test_marking_one_of_two_positions_unknown_preserves_known_balances_instead_of_zeroing_them() -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))
    _funded_position(ledger, "position-a")
    reserved, = ledger.reserve_entries(
        (ProposedEntryRequest("entry-2", "position-b", Decimal("100")),), _costs(),
    )
    assert reserved.status == "RESERVED"
    ledger.settle_entry("entry-2", Decimal("10"))

    value, reasons = ledger.mark_account({"position-a": Decimal("9"), "position-b": None})

    assert value is None
    assert reasons == ("MISSING_MARK:position-b",)
    assert ledger.cash_quote == Decimal("499.500")
    assert ledger.positions["position-a"].base_amount == Decimal("50")
    assert ledger.positions["position-b"].basis_quote == Decimal("100.100")


def test_reservation_captures_the_saved_costs_that_determine_the_event() -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))
    locked_costs = _costs("0.01")
    ledger.reserve_entries((ProposedEntryRequest("entry-1", "position-a", Decimal("400")),), locked_costs)

    filled = ledger.settle_entry("entry-1", Decimal("8"))

    assert filled.details["fee_quote"] == Decimal("4.00")
    assert ledger.cash_quote == Decimal("596.00")
    assert ledger.positions["position-a"].basis_quote == Decimal("404.00")


def test_addition_and_full_exit_apply_adverse_saved_slippage_on_each_side() -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))
    costs = _costs("0.01", "0.1")
    ledger.reserve_entries((ProposedEntryRequest("entry-1", "position-a", Decimal("100")),), costs)
    entry = ledger.settle_entry("entry-1", Decimal("10"))
    position = ledger.positions["position-a"]
    ledger.reserve_exits((ProposedExitRequest("exit-1", "position-a", None),), costs)
    exit_event = ledger.settle_exit("exit-1", Decimal("20"))

    assert entry.details["fill_price"] == Decimal("11.0")
    assert position.base_amount == Decimal("0")
    assert exit_event.details["fill_price"] == Decimal("18.0")
    assert exit_event.details["allocated_basis_quote"] == Decimal("101.00")
    assert exit_event.details["realized_quote"] == Decimal("61.00000000000000000000000000000000000000000000000")
    assert ledger.cash_quote == Decimal("1061.0000000000000000000000000000000000000000000000")


@pytest.mark.parametrize(
    "ticks",
    (
        (),
        (ProposedReplayTick(datetime(2026, 10, 1, 12),),),
        (ProposedReplayTick(datetime(2026, 10, 1, 12, tzinfo=timezone(timedelta(hours=1))),),),
        (ProposedReplayTick(datetime(2026, 10, 1, 12, 1, tzinfo=timezone.utc),),),
        (
            ProposedReplayTick(datetime(2026, 10, 1, 12, 5, tzinfo=timezone.utc),),
            ProposedReplayTick(datetime(2026, 10, 1, 12, tzinfo=timezone.utc),),
        ),
    ),
)
def test_proposed_replay_rejects_non_schedule_timestamps(ticks: tuple[ProposedReplayTick, ...]) -> None:
    with pytest.raises(ValueError, match="UTC five-minute"):
        run_proposed_accounting_replay(ticks, Decimal("1000"), _costs())


def test_proposed_replay_rejects_a_missing_bucket_before_a_later_fill() -> None:
    start = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    ticks = (
        ProposedReplayTick(start, entry_requests=(ProposedEntryRequest("entry-1", "position-a", Decimal("400")),)),
        ProposedReplayTick(start + timedelta(minutes=10), {"entry-1": Decimal("8")}),
    )

    with pytest.raises(ValueError, match="contiguous"):
        run_proposed_accounting_replay(ticks, Decimal("1000"), _costs())


def test_replay_with_no_saved_costs_has_no_reservation_or_later_fill() -> None:
    start = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    ticks = (
        ProposedReplayTick(start, entry_requests=(ProposedEntryRequest("entry-1", "position-a", Decimal("400")),)),
        ProposedReplayTick(start + timedelta(minutes=5), {"entry-1": Decimal("8")}),
    )

    result = run_proposed_accounting_replay(ticks, Decimal("1000"), None)

    assert [(event.status, event.request_id) for event in result.events] == [("COST_UNAVAILABLE", "entry-1")]
    assert [sample["cash_quote"] for sample in result.samples] == [Decimal("1000"), Decimal("1000")]
    assert result.positions == {}


def test_same_proposed_inputs_replay_identically() -> None:
    start = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    ticks = (
        ProposedReplayTick(start, entry_requests=(ProposedEntryRequest("entry-1", "position-a", Decimal("400")),)),
        ProposedReplayTick(start + timedelta(minutes=5), {"entry-1": Decimal("8")}, {"position-a": Decimal("8")}),
    )

    first = run_proposed_accounting_replay(ticks, Decimal("1000"), _costs())
    second = run_proposed_accounting_replay(ticks, Decimal("1000"), _costs())

    assert first == second


def test_negative_initial_cash_is_rejected() -> None:
    with pytest.raises(ValueError, match="Initial proposed replay cash"):
        ProposedSharedCapitalLedger(Decimal("-0.01"))
