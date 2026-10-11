"""Pure proposed P14 accounting for additions, partial exits, and shared cash.

This module is deliberately not wired into ``run_spot_replay``.  P12/1 remains
the adopted one-position, full-exit profile; these proposed semantics need their
own reviewed profile and saved-run record version before application use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Mapping

from edge_os_api.strategies import compiler as strategy_compiler


@dataclass(frozen=True)
class ProposedCostAssumptions:
    """Saved fractional costs required before a proposed action can proceed."""

    fee_rate: Decimal
    slippage_rate: Decimal
    source_ref: str

    def is_usable(self) -> bool:
        return (
            bool(self.source_ref)
            and self.fee_rate.is_finite()
            and self.slippage_rate.is_finite()
            and Decimal(0) <= self.fee_rate <= Decimal(1)
            and Decimal(0) <= self.slippage_rate < Decimal(1)
        )


@dataclass(frozen=True)
class ProposedEntryRequest:
    """One requested entry or addition competing for the shared cash balance."""

    request_id: str
    position_id: str
    quote_notional: Decimal


@dataclass(frozen=True)
class ProposedExitRequest:
    """One requested partial or full exit for a named proposed position."""

    request_id: str
    position_id: str
    base_amount: Decimal | None


@dataclass(frozen=True)
class ProposedReplayTick:
    """One scheduled decision point with fills for orders reserved at the prior tick."""

    at: datetime
    fill_prices: Mapping[str, Decimal | None] = field(default_factory=dict)
    marks: Mapping[str, Decimal | None] = field(default_factory=dict)
    exit_requests: tuple[ProposedExitRequest, ...] = ()
    entry_requests: tuple[ProposedEntryRequest, ...] = ()


@dataclass(frozen=True)
class ProposedReplayResult:
    """Pure proposed replay output, intentionally separate from P12 ``ReplayResult``."""

    samples: tuple[Mapping[str, Decimal | datetime | tuple[str, ...] | None], ...]
    events: tuple[ProposedAccountingEvent, ...]
    positions: Mapping[str, ProposedPosition]


@dataclass
class ProposedPosition:
    """Weighted-basis inventory for one explicit position identity."""

    position_id: str
    base_amount: Decimal = Decimal(0)
    basis_quote: Decimal = Decimal(0)
    realized_quote: Decimal = Decimal(0)
    fees_quote: Decimal = Decimal(0)


@dataclass(frozen=True)
class ProposedAccountingEvent:
    """A deterministic action outcome with the affected position after the action."""

    kind: str
    status: str
    position_id: str
    request_id: str | None
    cash_quote: Decimal
    base_amount: Decimal
    basis_quote: Decimal
    fees_quote: Decimal
    realized_quote: Decimal
    details: Mapping[str, Decimal | str | None]


@dataclass(frozen=True)
class _EntryReservation:
    request: ProposedEntryRequest
    required_cash: Decimal
    costs: ProposedCostAssumptions


@dataclass(frozen=True)
class _ExitReservation:
    request: ProposedExitRequest
    costs: ProposedCostAssumptions


@dataclass
class ProposedSharedCapitalLedger:
    """Proposed isolated accounting ledger; never a P12/1 replay replacement."""

    cash_quote: Decimal
    positions: dict[str, ProposedPosition] = field(default_factory=dict)
    events: list[ProposedAccountingEvent] = field(default_factory=list)
    _reservations: dict[str, _EntryReservation] = field(default_factory=dict)
    _exit_reservations: dict[str, _ExitReservation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.cash_quote.is_finite() or self.cash_quote < 0:
            raise ValueError("Initial proposed replay cash must be finite and non-negative.")

    def reserve_entries(
        self,
        requests: tuple[ProposedEntryRequest, ...],
        costs: ProposedCostAssumptions | None,
    ) -> tuple[ProposedAccountingEvent, ...]:
        """Reserve competing requests by stable ``(position_id, request_id)`` order.

        A rejected request is never resized.  The caller later settles each accepted
        request against an explicitly supplied next-bucket fill, or releases it.
        """
        if costs is None or not costs.is_usable():
            return tuple(self._record("ENTRY", "COST_UNAVAILABLE", request.position_id, request.request_id, {})
                         for request in sorted(requests, key=self._entry_order))
        outcomes: list[ProposedAccountingEvent] = []
        for request in sorted(requests, key=self._entry_order):
            if not self._valid_identifier(request.request_id) or not self._valid_identifier(request.position_id):
                outcomes.append(self._record("ENTRY", "INVALID_IDENTIFIER", request.position_id, request.request_id, {}))
                continue
            if request.request_id in self._reservations or request.request_id in self._exit_reservations:
                outcomes.append(self._record("ENTRY", "DUPLICATE_REQUEST", request.position_id, request.request_id, {}))
                continue
            if not request.quote_notional.is_finite() or request.quote_notional <= 0:
                outcomes.append(self._record("ENTRY", "INVALID_NOTIONAL", request.position_id, request.request_id, {}))
                continue
            with localcontext(strategy_compiler.NUMERIC):
                required_cash = request.quote_notional * (Decimal(1) + costs.fee_rate)
            if required_cash > self.free_cash_quote:
                outcomes.append(self._record(
                    "ENTRY", "INSUFFICIENT_CASH", request.position_id, request.request_id,
                    {"requested_quote": request.quote_notional, "required_cash_quote": required_cash},
                ))
                continue
            self._reservations[request.request_id] = _EntryReservation(request, required_cash, costs)
            outcomes.append(self._record(
                "ENTRY", "RESERVED", request.position_id, request.request_id,
                {"reserved_quote": required_cash, "free_cash_quote": self.free_cash_quote},
            ))
        return tuple(outcomes)

    def reserve_exits(
        self,
        requests: tuple[ProposedExitRequest, ...],
        costs: ProposedCostAssumptions | None,
    ) -> tuple[ProposedAccountingEvent, ...]:
        """Reserve exit inventory before an explicit later fill."""
        outcomes: list[ProposedAccountingEvent] = []
        for request in sorted(requests, key=self._exit_order):
            position = self.positions.get(request.position_id)
            if costs is None or not costs.is_usable():
                outcomes.append(self._record("EXIT", "COST_UNAVAILABLE", request.position_id, request.request_id, {}))
            elif not self._valid_identifier(request.request_id) or not self._valid_identifier(request.position_id):
                outcomes.append(self._record("EXIT", "INVALID_IDENTIFIER", request.position_id, request.request_id, {}))
            elif request.request_id in self._reservations or request.request_id in self._exit_reservations:
                outcomes.append(self._record("EXIT", "DUPLICATE_REQUEST", request.position_id, request.request_id, {}))
            elif position is None or position.base_amount <= 0:
                outcomes.append(self._record("EXIT", "POSITION_UNAVAILABLE", request.position_id, request.request_id, {}))
            elif (request.base_amount is not None
                  and (not request.base_amount.is_finite() or request.base_amount <= 0
                       or request.base_amount > self._free_base(request.position_id))):
                outcomes.append(self._record("EXIT", "INVALID_BASE_AMOUNT", request.position_id, request.request_id, {}))
            else:
                base_amount = request.base_amount or self._free_base(request.position_id)
                if base_amount <= 0:
                    outcomes.append(self._record("EXIT", "INVALID_BASE_AMOUNT", request.position_id, request.request_id, {}))
                    continue
                reserved = ProposedExitRequest(request.request_id, request.position_id, base_amount)
                self._exit_reservations[request.request_id] = _ExitReservation(reserved, costs)
                outcomes.append(self._record(
                    "EXIT", "RESERVED", request.position_id, request.request_id,
                    {"reserved_base": base_amount},
                ))
        return tuple(outcomes)

    def settle_entry(
        self,
        request_id: str,
        close_price: Decimal | None,
    ) -> ProposedAccountingEvent:
        """Fill one accepted reservation or release it without charging a fee."""
        reservation = self._reservations.pop(request_id, None)
        if reservation is None:
            return self._record("ENTRY", "UNKNOWN_RESERVATION", "", request_id, {})
        request, reserved_quote, costs = reservation.request, reservation.required_cash, reservation.costs
        if close_price is None:
            return self._record("ENTRY", "FILL_UNAVAILABLE", request.position_id, request_id,
                                {"reservation_released_quote": reserved_quote})
        with localcontext(strategy_compiler.NUMERIC):
            fill_price = close_price * (Decimal(1) + costs.slippage_rate)
            fee = request.quote_notional * costs.fee_rate
            if not fill_price.is_finite() or fill_price <= 0:
                return self._record("ENTRY", "NON_POSITIVE_FILL", request.position_id, request_id,
                                    {"reservation_released_quote": reserved_quote})
            acquired = request.quote_notional / fill_price
            position = self.positions.setdefault(request.position_id, ProposedPosition(request.position_id))
            self.cash_quote -= request.quote_notional + fee
            position.base_amount += acquired
            position.basis_quote += request.quote_notional + fee
            position.fees_quote += fee
        return self._record(
            "ENTRY", "FILLED", request.position_id, request_id,
            {"fill_price": fill_price, "acquired_base": acquired, "fee_quote": fee},
        )

    def settle_exit(
        self,
        request_id: str,
        close_price: Decimal | None,
    ) -> ProposedAccountingEvent:
        """Fill one accepted exit reservation or release it without a fee."""
        request = self._exit_reservations.pop(request_id, None)
        if request is None:
            return self._record("EXIT", "UNKNOWN_RESERVATION", "", request_id, {})
        reserved, costs = request.request, request.costs
        if close_price is None:
            return self._record("EXIT", "FILL_UNAVAILABLE", reserved.position_id, request_id,
                                {"reservation_released_base": reserved.base_amount})
        return self._apply_sale(reserved.position_id, reserved.base_amount, close_price, costs, request_id)

    def sell(
        self,
        position_id: str,
        base_amount: Decimal,
        close_price: Decimal | None,
        costs: ProposedCostAssumptions | None,
    ) -> ProposedAccountingEvent:
        """Propose a settled full or partial exit with proportional basis allocation."""
        if costs is None or not costs.is_usable():
            return self._record("EXIT", "COST_UNAVAILABLE", position_id, None, {})
        if close_price is None:
            return self._record("EXIT", "FILL_UNAVAILABLE", position_id, None, {})
        return self._apply_sale(position_id, base_amount, close_price, costs, None)

    def no_next_bucket(self, kind: str, position_id: str, request_id: str) -> ProposedAccountingEvent:
        """Record a terminal proposed decision without creating a reservation."""
        return self._record(kind, "NO_NEXT_BUCKET", position_id, request_id, {})

    def suppress_entry_for_exit(self, request: ProposedEntryRequest) -> ProposedAccountingEvent:
        """Keep a same-position add from competing with its exit at one decision."""
        return self._record("ENTRY", "EXIT_PRIORITY", request.position_id, request.request_id, {})

    def _apply_sale(
        self,
        position_id: str,
        base_amount: Decimal,
        close_price: Decimal,
        costs: ProposedCostAssumptions,
        request_id: str | None,
    ) -> ProposedAccountingEvent:
        position = self.positions.get(position_id)
        if position is None or position.base_amount <= 0:
            return self._record("EXIT", "POSITION_UNAVAILABLE", position_id, request_id, {})
        if not base_amount.is_finite() or base_amount <= 0 or base_amount > position.base_amount:
            return self._record("EXIT", "INVALID_BASE_AMOUNT", position_id, request_id, {})
        with localcontext(strategy_compiler.NUMERIC):
            fill_price = close_price * (Decimal(1) - costs.slippage_rate)
            if not fill_price.is_finite() or fill_price <= 0:
                return self._record("EXIT", "NON_POSITIVE_FILL", position_id, request_id, {})
            allocated_basis = position.basis_quote * base_amount / position.base_amount
            gross = base_amount * fill_price
            fee = gross * costs.fee_rate
            net = gross - fee
            realized = net - allocated_basis
            position.base_amount -= base_amount
            position.basis_quote -= allocated_basis
            position.realized_quote += realized
            position.fees_quote += fee
            self.cash_quote += net
            status = "FULL_EXIT" if position.base_amount == 0 else "PARTIAL_EXIT"
        return self._record(
            "EXIT", status, position_id, request_id,
            {"fill_price": fill_price, "gross_quote": gross, "fee_quote": fee,
             "allocated_basis_quote": allocated_basis, "realized_quote": realized},
        )

    def mark_account(self, marks: Mapping[str, Decimal | None]) -> tuple[Decimal | None, tuple[str, ...]]:
        """Return a known account value, or an explicit unknown mark reason."""
        reasons: list[str] = []
        value = self.cash_quote
        with localcontext(strategy_compiler.NUMERIC):
            for position_id, position in sorted(self.positions.items()):
                if position.base_amount == 0:
                    continue
                mark = marks.get(position_id)
                if mark is None or not mark.is_finite() or mark <= 0:
                    reasons.append(f"MISSING_MARK:{position_id}")
                    continue
                value += position.base_amount * mark
        return (None, tuple(reasons)) if reasons else (value, ())

    @property
    def free_cash_quote(self) -> Decimal:
        with localcontext(strategy_compiler.NUMERIC):
            return self.cash_quote - sum(
                (reservation.required_cash for reservation in self._reservations.values()), Decimal(0),
            )

    def _free_base(self, position_id: str) -> Decimal:
        position = self.positions[position_id]
        with localcontext(strategy_compiler.NUMERIC):
            return position.base_amount - sum(
                (reservation.request.base_amount for reservation in self._exit_reservations.values()
                 if reservation.request.position_id == position_id),
                Decimal(0),
            )

    @staticmethod
    def _entry_order(request: ProposedEntryRequest) -> tuple[str, str]:
        return request.position_id, request.request_id

    @staticmethod
    def _exit_order(request: ProposedExitRequest) -> tuple[str, str]:
        return request.position_id, request.request_id

    @staticmethod
    def _valid_identifier(value: str) -> bool:
        return bool(value) and value.isascii() and value.isprintable()

    def _record(
        self,
        kind: str,
        status: str,
        position_id: str,
        request_id: str | None,
        details: Mapping[str, Decimal | str | None],
    ) -> ProposedAccountingEvent:
        position = self.positions.get(position_id, ProposedPosition(position_id))
        event = ProposedAccountingEvent(
            kind, status, position_id, request_id, self.cash_quote, position.base_amount,
            position.basis_quote, position.fees_quote, position.realized_quote, dict(details),
        )
        self.events.append(event)
        return event


def run_proposed_accounting_replay(
    ticks: tuple[ProposedReplayTick, ...],
    initial_cash_quote: Decimal,
    costs: ProposedCostAssumptions | None,
) -> ProposedReplayResult:
    """Replay pre-qualified proposed actions with P12-shaped settle/value/decide order.

    The caller supplies action decisions and immutable per-tick closes. This helper
    deliberately does not evaluate P06 expressions or redefine saved P12 inputs.
    """
    if (not ticks
            or any(current.at >= following.at for current, following in zip(ticks, ticks[1:]))
            or any(tick.at.tzinfo is None or tick.at.utcoffset() != timedelta(0)
                   or tick.at.minute % 5 or tick.at.second or tick.at.microsecond for tick in ticks)):
        raise ValueError("Proposed replay ticks must be ordered UTC five-minute boundaries.")
    ledger = ProposedSharedCapitalLedger(initial_cash_quote)
    pending_entries: tuple[str, ...] = ()
    pending_exits: tuple[str, ...] = ()
    samples: list[Mapping[str, Decimal | datetime | tuple[str, ...] | None]] = []
    for index, tick in enumerate(ticks):
        for request_id in pending_exits:
            ledger.settle_exit(request_id, tick.fill_prices.get(request_id))
        for request_id in pending_entries:
            ledger.settle_entry(request_id, tick.fill_prices.get(request_id))
        account_value, mark_reasons = ledger.mark_account(tick.marks)
        samples.append({"at": tick.at, "cash_quote": ledger.cash_quote,
                        "account_value_quote": account_value, "mark_reasons": mark_reasons})
        if index == len(ticks) - 1:
            for request in sorted(tick.exit_requests, key=ledger._exit_order):
                ledger.no_next_bucket("EXIT", request.position_id, request.request_id)
            for request in sorted(tick.entry_requests, key=ledger._entry_order):
                ledger.no_next_bucket("ENTRY", request.position_id, request.request_id)
            continue
        exit_outcomes = ledger.reserve_exits(tick.exit_requests, costs)
        exiting_positions = {event.position_id for event in exit_outcomes if event.status == "RESERVED"}
        for request in tick.entry_requests:
            if request.position_id in exiting_positions:
                ledger.suppress_entry_for_exit(request)
        entry_outcomes = ledger.reserve_entries(
            tuple(request for request in tick.entry_requests if request.position_id not in exiting_positions), costs,
        )
        pending_exits = tuple(event.request_id for event in exit_outcomes if event.status == "RESERVED" and event.request_id)
        pending_entries = tuple(event.request_id for event in entry_outcomes if event.status == "RESERVED" and event.request_id)
    return ProposedReplayResult(tuple(samples), tuple(ledger.events), dict(ledger.positions))
