from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from edge_os_api.replay.proposed_market_context import (
    ProposedFeeScheduleSnapshot,
    ProposedTickerSnapshot,
    ProposedTimeframe,
    ProposedVenueInstrument,
    completed_bar_end,
    quote_cost_assumptions,
    resolve_completed_context,
    select_fee_schedule,
)


UTC = timezone.utc
AT = datetime(2026, 10, 1, 12, 5, tzinfo=UTC)
FIVE_MINUTES = ProposedTimeframe("5m", 5)
ONE_HOUR = ProposedTimeframe("1h", 60)


def _spot() -> ProposedVenueInstrument:
    return ProposedVenueInstrument(
        "example-venue", "BTC-USDT", "SPOT", "USDT", None, None, FIVE_MINUTES,
        (FIVE_MINUTES, ONE_HOUR), "archive:ohlcv-v1", "official:settlement#spot",
    )


def _completed_snapshots() -> dict[str, ProposedTickerSnapshot]:
    return {
        "5m": ProposedTickerSnapshot(FIVE_MINUTES, AT, Decimal("101"), "TRADE", "official:klines?5m", AT, "sha256:five"),
        "1h": ProposedTickerSnapshot(ONE_HOUR, datetime(2026, 10, 1, 12, tzinfo=UTC), Decimal("100"), "MARK", "official:klines?1h", AT, "sha256:hour"),
    }


def _schedule(**changes: object) -> ProposedFeeScheduleSnapshot:
    values: dict[str, object] = {
        "venue": "example-venue", "instrument": "BTC-USDT", "contract_kind": "SPOT",
        "effective_from": datetime(2026, 10, 1, tzinfo=UTC), "effective_to": None,
        "retrieved_at": AT, "source_ref": "official:fees#snapshot-a", "account_tier_ref": "vip-0",
        "fee_asset": "USDT", "maker_rate": Decimal("0.0002"), "taker_rate": Decimal("0.0006"),
        "discount_or_promotion_ref": "NONE",
    }
    values.update(changes)
    return ProposedFeeScheduleSnapshot(**values)  # type: ignore[arg-type]


def test_multi_timeframe_context_uses_only_completed_bars_with_provenance() -> None:
    accepted, reasons = resolve_completed_context(AT, _spot(), _completed_snapshots())
    assert tuple(accepted) == ("5m", "1h")
    assert reasons == ()
    assert completed_bar_end(AT, ONE_HOUR) == datetime(2026, 10, 1, 12, tzinfo=UTC)


def test_context_rejects_unusable_instrument_even_when_its_bars_are_valid() -> None:
    snapshots = _completed_snapshots()
    for instrument in (
        replace(_spot(), venue=""),
        replace(_spot(), instrument=""),
        replace(_spot(), settlement_asset=None),
        replace(_spot(), historical_data_source_ref=""),
        replace(_spot(), settlement_procedure_ref=""),
        replace(_spot(), contract_kind="UNSUPPORTED"),
        replace(_spot(), leverage=Decimal("2")),
    ):
        accepted, reasons = resolve_completed_context(AT, instrument, snapshots)
        assert accepted == {}
        assert reasons == ("MARKET_CONTEXT_UNAVAILABLE",)


def test_future_stale_or_unknown_context_is_refused_not_forward_filled() -> None:
    unknown = ProposedTickerSnapshot(ONE_HOUR, datetime(2026, 10, 1, 13, tzinfo=UTC), None, "TRADE", "official:klines", AT, "sha256:unknown")
    accepted, reasons = resolve_completed_context(AT, _spot(), {"1h": unknown})
    assert accepted == {}
    assert reasons == ("CONTEXT_UNAVAILABLE:5m", "CONTEXT_UNAVAILABLE:1h")


def test_venue_product_context_requires_settlement_and_explicit_derivative_leverage() -> None:
    assert _spot().is_usable()
    assert not ProposedVenueInstrument("venue", "BTC-USDT", "LINEAR_PERPETUAL", "USDT", None, None, FIVE_MINUTES, (), "source", "settlement").is_usable()
    assert not ProposedVenueInstrument("venue", "BTC-USDT", "SPOT", "USDT", Decimal("2"), None, FIVE_MINUTES, (), "source", "settlement").is_usable()
    assert ProposedVenueInstrument("venue", "BTC-USDT", "LINEAR_PERPETUAL", "USDT", Decimal("3"), Decimal("0.001"), FIVE_MINUTES, (), "source", "settlement", "funding").is_usable()


def test_dated_fee_schedule_selection_names_gaps_and_overlaps() -> None:
    schedule = _schedule(effective_to=AT + timedelta(minutes=1))
    assert select_fee_schedule(AT, _spot(), (schedule,)) == (schedule, None)
    assert select_fee_schedule(AT + timedelta(minutes=1), _spot(), (schedule,)) == (None, "FEE_SCHEDULE_GAP")
    assert select_fee_schedule(AT, _spot(), (schedule, _schedule())) == (None, "FEE_SCHEDULE_OVERLAP")


def test_fee_benchmark_retains_role_asset_and_contract_boundaries() -> None:
    schedule = _schedule()
    costs, reason = quote_cost_assumptions(schedule, "TAKER", "USDT", Decimal("0.001"))
    assert reason is None
    assert costs is not None and costs.fee_rate == Decimal("0.0006")
    assert quote_cost_assumptions(schedule, "MAKER", "USDC", Decimal("0"))[1] == "FEE_ASSET_UNSUPPORTED"
    assert quote_cost_assumptions(_schedule(maker_rate=Decimal("-0.0001")), "MAKER", "USDT", Decimal("0"))[1] == "FEE_RATE_UNSUPPORTED"
    assert quote_cost_assumptions(_schedule(contract_kind="LINEAR_PERPETUAL"), "TAKER", "USDT", Decimal("0"))[1] == "CONTRACT_SETTLEMENT_UNSUPPORTED"
