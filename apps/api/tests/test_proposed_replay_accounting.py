from datetime import datetime, timedelta, timezone
from decimal import Decimal

from edge_os_api.replay.proposed_accounting import (
    ProposedCostAssumptions,
    ProposedEntryRequest,
    ProposedExitRequest,
    ProposedReplayTick,
    ProposedSharedCapitalLedger,
    run_proposed_accounting_replay,
)


def _costs() -> ProposedCostAssumptions:
    return ProposedCostAssumptions(Decimal("0.001"), Decimal("0"), "synthetic-p14")


def _reserve_and_fill(
    ledger: ProposedSharedCapitalLedger,
    request_id: str,
    position_id: str,
    quote_notional: str,
    price: str,
) -> None:
    reservation, = ledger.reserve_entries(
        (ProposedEntryRequest(request_id, position_id, Decimal(quote_notional)),), _costs(),
    )
    assert reservation.status == "RESERVED"
    assert ledger.settle_entry(request_id, Decimal(price)).status == "FILLED"


def test_proposed_add_partial_exit_add_again_and_full_exit_is_independently_reconciled() -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))

    _reserve_and_fill(ledger, "entry-1", "position-a", "400", "8")
    first = ledger.events[-1]
    assert (first.cash_quote, first.base_amount, first.basis_quote, first.fees_quote, first.realized_quote) == (
        Decimal("599.600"), Decimal("50"), Decimal("400.400"), Decimal("0.400"), Decimal("0"),
    )

    _reserve_and_fill(ledger, "add-1", "position-a", "200", "10")
    added = ledger.events[-1]
    assert (added.cash_quote, added.base_amount, added.basis_quote, added.fees_quote, added.realized_quote) == (
        Decimal("399.400"), Decimal("70"), Decimal("600.600"), Decimal("0.600"), Decimal("0"),
    )

    partial = ledger.sell("position-a", Decimal("28"), Decimal("12"), _costs())
    assert partial.status == "PARTIAL_EXIT"
    assert partial.details["allocated_basis_quote"] == Decimal("240.240")
    assert (partial.cash_quote, partial.base_amount, partial.basis_quote, partial.fees_quote, partial.realized_quote) == (
        Decimal("735.064"), Decimal("42"), Decimal("360.360"), Decimal("0.936"), Decimal("95.424"),
    )

    _reserve_and_fill(ledger, "add-2", "position-a", "100", "9")
    second_add = ledger.events[-1]
    assert second_add.cash_quote == Decimal("634.964")
    assert second_add.base_amount == Decimal("53.111111111111111111111111111111111111111111111111")
    assert second_add.basis_quote == Decimal("460.460")
    assert second_add.fees_quote == Decimal("1.036")

    full = ledger.sell("position-a", second_add.base_amount, Decimal("11"), _costs())
    assert full.status == "FULL_EXIT"
    assert full.base_amount == Decimal("0")
    assert full.basis_quote == Decimal("0")
    assert full.cash_quote == Decimal("1218.6020000000000000000000000000000000000000000000")
    assert full.realized_quote == Decimal("218.60200000000000000000000000000000000000000000000")
    assert full.fees_quote == Decimal("1.6202222222222222222222222222222222222222222222222")


def test_proposed_competing_entries_sort_by_position_then_request_and_deny_without_resizing() -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("500"))
    outcomes = ledger.reserve_entries(
        (
            ProposedEntryRequest("request-b", "position-b", Decimal("300")),
            ProposedEntryRequest("request-a", "position-a", Decimal("300")),
        ),
        _costs(),
    )

    assert [(event.position_id, event.request_id, event.status) for event in outcomes] == [
        ("position-a", "request-a", "RESERVED"),
        ("position-b", "request-b", "INSUFFICIENT_CASH"),
    ]
    denied = outcomes[1]
    assert denied.details == {"requested_quote": Decimal("300"), "required_cash_quote": Decimal("300.300")}
    filled = ledger.settle_entry("request-a", Decimal("5"))
    assert filled.status == "FILLED"
    assert ledger.cash_quote == Decimal("199.700")
    assert "position-b" not in ledger.positions
    assert ledger.free_cash_quote == Decimal("199.700")


def test_proposed_unknown_cost_unavailable_fill_missing_mark_and_unsold_inventory_stay_distinct_from_zero() -> None:
    ledger = ProposedSharedCapitalLedger(Decimal("1000"))
    missing_cost = ledger.reserve_entries(
        (ProposedEntryRequest("entry-1", "position-a", Decimal("400")),), None,
    )
    assert missing_cost[0].status == "COST_UNAVAILABLE"
    assert ledger.cash_quote == Decimal("1000")

    reservation, = ledger.reserve_entries(
        (ProposedEntryRequest("entry-1", "position-a", Decimal("400")),), _costs(),
    )
    assert reservation.status == "RESERVED"
    unavailable = ledger.settle_entry("entry-1", None)
    assert unavailable.status == "FILL_UNAVAILABLE"
    assert unavailable.details["reservation_released_quote"] == Decimal("400.400")
    assert ledger.cash_quote == Decimal("1000")
    assert ledger.free_cash_quote == Decimal("1000")

    _reserve_and_fill(ledger, "entry-2", "position-a", "400", "8")
    value, reasons = ledger.mark_account({"position-a": None})
    assert value is None
    assert reasons == ("MISSING_MARK:position-a",)
    position = ledger.positions["position-a"]
    assert position.base_amount == Decimal("50")
    assert position.basis_quote == Decimal("400.400")
    assert position.realized_quote == Decimal("0")


def test_proposed_replay_settles_then_marks_then_reserves_and_rejects_terminal_orders() -> None:
    start = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    at = lambda index: start + timedelta(minutes=5 * index)
    ticks = (
        ProposedReplayTick(at(0), entry_requests=(ProposedEntryRequest("entry-1", "position-a", Decimal("400")),)),
        ProposedReplayTick(at(1), {"entry-1": Decimal("8")}, {"position-a": Decimal("8")},
                           entry_requests=(ProposedEntryRequest("add-1", "position-a", Decimal("200")),)),
        ProposedReplayTick(at(2), {"add-1": Decimal("10")}, {"position-a": Decimal("10")},
                           exit_requests=(ProposedExitRequest("exit-1", "position-a", Decimal("28")),),
                           entry_requests=(ProposedEntryRequest("suppressed-add", "position-a", Decimal("1")),)),
        ProposedReplayTick(at(3), {"exit-1": Decimal("12")}, {"position-a": Decimal("12")},
                           entry_requests=(ProposedEntryRequest("add-2", "position-a", Decimal("100")),)),
        ProposedReplayTick(at(4), {"add-2": Decimal("9")}, {"position-a": Decimal("9")},
                           exit_requests=(ProposedExitRequest("exit-2", "position-a", None),)),
        ProposedReplayTick(at(5), {"exit-2": Decimal("11")}, {},
                           entry_requests=(ProposedEntryRequest("terminal-add", "position-a", Decimal("1")),)),
    )

    result = run_proposed_accounting_replay(ticks, Decimal("1000"), _costs())

    assert [sample["cash_quote"] for sample in result.samples] == [
        Decimal("1000"), Decimal("599.600"), Decimal("399.400"),
        Decimal("735.064"), Decimal("634.964"), Decimal("1218.6020000000000000000000000000000000000000000000"),
    ]
    assert result.samples[3]["account_value_quote"] == Decimal("1239.064")
    assert result.samples[-1]["account_value_quote"] == Decimal("1218.6020000000000000000000000000000000000000000000")
    assert [(event.kind, event.status, event.request_id) for event in result.events] == [
        ("ENTRY", "RESERVED", "entry-1"), ("ENTRY", "FILLED", "entry-1"),
        ("ENTRY", "RESERVED", "add-1"), ("ENTRY", "FILLED", "add-1"),
        ("EXIT", "RESERVED", "exit-1"), ("ENTRY", "EXIT_PRIORITY", "suppressed-add"),
        ("EXIT", "PARTIAL_EXIT", "exit-1"),
        ("ENTRY", "RESERVED", "add-2"), ("ENTRY", "FILLED", "add-2"),
        ("EXIT", "RESERVED", "exit-2"), ("EXIT", "FULL_EXIT", "exit-2"),
        ("ENTRY", "NO_NEXT_BUCKET", "terminal-add"),
    ]
