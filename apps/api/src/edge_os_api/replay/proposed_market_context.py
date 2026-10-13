"""Pure, proposal-only P14 market-context and fee-provenance rules.

This is deliberately separate from the P12 replay and the proposed spot cash
ledger.  It records what a future multi-timeframe replay would need to know;
it does not fetch live venue data or silently turn unknown context into zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Mapping

from edge_os_api.replay.proposed_accounting import ProposedCostAssumptions


@dataclass(frozen=True)
class ProposedTimeframe:
    """A UTC-aligned candle duration, named for display and saved provenance."""

    label: str
    minutes: int

    def is_usable(self) -> bool:
        return bool(self.label) and 0 < self.minutes <= 1_440 and 1_440 % self.minutes == 0


@dataclass(frozen=True)
class ProposedTickerSnapshot:
    """One retrieved historical bar; ``None`` price deliberately means unknown."""

    timeframe: ProposedTimeframe
    ended_at: datetime
    close: Decimal | None
    price_kind: str  # TRADE, MARK, or INDEX
    source_ref: str
    retrieved_at: datetime
    content_hash: str

    def is_usable(self) -> bool:
        return (
            self.timeframe.is_usable()
            and _is_utc(self.ended_at)
            and _is_utc(self.retrieved_at)
            and self.close is not None
            and self.close.is_finite()
            and self.close > 0
            and self.price_kind in {"TRADE", "MARK", "INDEX"}
            and bool(self.source_ref)
            and bool(self.content_hash)
        )


@dataclass(frozen=True)
class ProposedVenueInstrument:
    """The product facts that must be named before a venue result is comparable."""

    venue: str
    instrument: str
    contract_kind: str  # SPOT, LINEAR_PERPETUAL, or INVERSE_PERPETUAL
    settlement_asset: str | None
    leverage: Decimal | None
    contract_multiplier: Decimal | None
    execution_timeframe: ProposedTimeframe
    context_timeframes: tuple[ProposedTimeframe, ...]
    historical_data_source_ref: str
    settlement_procedure_ref: str
    funding_data_source_ref: str | None = None

    def is_usable(self) -> bool:
        frames = self.context_timeframes
        if (
            not all((self.venue, self.instrument, self.settlement_asset, self.historical_data_source_ref,
                     self.settlement_procedure_ref))
            or self.contract_kind not in {"SPOT", "LINEAR_PERPETUAL", "INVERSE_PERPETUAL"}
            or not self.execution_timeframe.is_usable()
            or not all(frame.is_usable() for frame in frames)
            or len({frame.label for frame in frames}) != len(frames)
        ):
            return False
        if self.contract_kind == "SPOT":
            return self.leverage is None and self.contract_multiplier is None and self.funding_data_source_ref is None
        return (
            self.leverage is not None and self.leverage.is_finite() and self.leverage > 0
            and self.contract_multiplier is not None and self.contract_multiplier.is_finite()
            and self.contract_multiplier > 0 and bool(self.funding_data_source_ref)
        )


@dataclass(frozen=True)
class ProposedFeeScheduleSnapshot:
    """An immutable observed fee schedule, not a claim about all historical fills."""

    venue: str
    instrument: str
    contract_kind: str
    effective_from: datetime
    effective_to: datetime | None
    retrieved_at: datetime
    source_ref: str
    account_tier_ref: str
    fee_asset: str | None
    maker_rate: Decimal | None
    taker_rate: Decimal | None
    discount_or_promotion_ref: str

    def is_usable(self) -> bool:
        rates = (self.maker_rate, self.taker_rate)
        return (
            all((self.venue, self.instrument, self.account_tier_ref, self.fee_asset, self.source_ref,
                 self.discount_or_promotion_ref))
            and self.contract_kind in {"SPOT", "LINEAR_PERPETUAL", "INVERSE_PERPETUAL"}
            and _is_utc(self.effective_from)
            and (self.effective_to is None or (_is_utc(self.effective_to) and self.effective_to > self.effective_from))
            and _is_utc(self.retrieved_at)
            and all(rate is not None and rate.is_finite() and Decimal(-1) < rate <= Decimal(1) for rate in rates)
        )


def completed_bar_end(at: datetime, timeframe: ProposedTimeframe) -> datetime | None:
    """Latest fully closed UTC bar end at a decision time, never a future bar."""
    if not _is_utc(at) or at.second or at.microsecond or not timeframe.is_usable():
        return None
    span_seconds = timeframe.minutes * 60
    elapsed_seconds = at.hour * 3_600 + at.minute * 60
    return at - timedelta(seconds=elapsed_seconds % span_seconds)


def resolve_completed_context(
    at: datetime,
    instrument: ProposedVenueInstrument,
    snapshots: Mapping[str, ProposedTickerSnapshot | None],
) -> tuple[Mapping[str, ProposedTickerSnapshot], tuple[str, ...]]:
    """Accept only the latest completed, self-identifying context bar per timeframe."""
    if not instrument.is_usable():
        return {}, ("MARKET_CONTEXT_UNAVAILABLE",)
    accepted: dict[str, ProposedTickerSnapshot] = {}
    reasons: list[str] = []
    for timeframe in instrument.context_timeframes:
        expected_end = completed_bar_end(at, timeframe)
        snapshot = snapshots.get(timeframe.label)
        if expected_end is None or snapshot is None or not snapshot.is_usable():
            reasons.append(f"CONTEXT_UNAVAILABLE:{timeframe.label}")
        elif snapshot.timeframe != timeframe or snapshot.ended_at != expected_end:
            reasons.append(f"CONTEXT_BAR_MISMATCH:{timeframe.label}")
        else:
            accepted[timeframe.label] = snapshot
    return accepted, tuple(reasons)


def select_fee_schedule(
    at: datetime,
    instrument: ProposedVenueInstrument,
    schedules: tuple[ProposedFeeScheduleSnapshot, ...],
) -> tuple[ProposedFeeScheduleSnapshot | None, str | None]:
    """Choose exactly one dated schedule or name the gap/overlap explicitly."""
    if not _is_utc(at) or not instrument.is_usable():
        return None, "MARKET_CONTEXT_UNAVAILABLE"
    applicable = tuple(
        schedule for schedule in schedules
        if schedule.is_usable()
        and (schedule.venue, schedule.instrument, schedule.contract_kind)
        == (instrument.venue, instrument.instrument, instrument.contract_kind)
        and schedule.effective_from <= at
        and (schedule.effective_to is None or at < schedule.effective_to)
    )
    if len(applicable) == 1:
        return applicable[0], None
    return (None, "FEE_SCHEDULE_GAP" if not applicable else "FEE_SCHEDULE_OVERLAP")


def quote_cost_assumptions(
    schedule: ProposedFeeScheduleSnapshot | None,
    liquidity_role: str,
    quote_asset: str,
    slippage_rate: Decimal,
) -> tuple[ProposedCostAssumptions | None, str | None]:
    """Adapt a dated quote-denominated *spot* schedule to the proposed cash ledger.

    Rebates, non-quote fee assets, and derivative contracts are intentionally
    refused here.  They need a later contract/funding/settlement accounting model.
    """
    if schedule is None or not schedule.is_usable():
        return None, "FEE_SCHEDULE_UNAVAILABLE"
    if schedule.contract_kind != "SPOT":
        return None, "CONTRACT_SETTLEMENT_UNSUPPORTED"
    if schedule.fee_asset != quote_asset:
        return None, "FEE_ASSET_UNSUPPORTED"
    rate = {"MAKER": schedule.maker_rate, "TAKER": schedule.taker_rate}.get(liquidity_role)
    if rate is None or rate < 0:
        return None, "FEE_RATE_UNSUPPORTED"
    costs = ProposedCostAssumptions(rate, slippage_rate, schedule.source_ref)
    return (costs, None) if costs.is_usable() else (None, "COST_UNAVAILABLE")


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)
