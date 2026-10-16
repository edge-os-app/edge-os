"""Authored regression cases for the fixed edge-os.delayed-history-replay/1 timing profile."""

from __future__ import annotations

import copy
import itertools
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.replay import simulator
from edge_os_api.replay.simulator import ReplayBucket, ReplayDataset, ReplayError, ReplayInput, run_spot_replay
from edge_os_api.strategies import compiler as strategy_compiler

DELAYED = "edge-os.delayed-history-replay/1"
LEGACY = "p12.spot-replay/1"
DELAY = timedelta(seconds=300)
MICROSECOND = timedelta(microseconds=1)
FILL_LABEL = "Hypothetical stale historical close"
QUOTE_ASSET = record_contract.FIXTURE_STRATEGY["market"]["research_binding"]["quote_asset"]
# Legacy fingerprint of `_run()` recorded at base 5ae6164d before the delayed profile existed.
LEGACY_BASE_FINGERPRINT = "193974c5d9a9e111c3a0c499b776f50b9988b8171c4b5b27f82645932242b2e9"


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 1, 5, hour, minute, tzinfo=timezone.utc)


def _strategy(*, entry: dict[str, Any] | None = None, warmup: int = 0,
              data_inputs: list[str] | None = None) -> dict[str, Any]:
    values = {name: copy.deepcopy(record_contract.FIXTURE_STRATEGY[name])
              for name in record_contract.CREATE_STRATEGY_FIELDS if name != "restrictions"}
    values["entry"] = entry or {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "7", "unit": "PRICE"}]}
    values["exit"] = {"op": "gte", "args": [{"op": "price"}, {"op": "constant", "value": "9", "unit": "PRICE"}]}
    values["invalidation"] = {"state": "NOT_REQUESTED", "source_ref": "synthetic-delayed"}
    values["data_inputs"] = data_inputs or ["price"]
    values["sizing"]["amount"] = "400"
    values["cost_assumptions"] = {"fee_rate": "0.001", "slippage_rate": "0.25", "source_ref": "synthetic-delayed"}
    values["risk_limits"]["max_quote_notional"] = "400"
    values["warmup_buckets"] = warmup
    strategy = strategy_compiler.build_strategy("synthetic-strategy-delayed-v1", values)
    strategy_compiler.validate_strategy(strategy)
    return strategy


def _run(
    strategy: dict[str, Any],
    prices: tuple[str | None, ...] = ("8", "8", "12", "12", "100"),
    *,
    first_end: datetime = _at(9, 55),
    window: tuple[datetime, datetime] = (_at(10, 0), _at(10, 20)),
    price_available: dict[int, datetime | None] | None = None,
    volume_available: dict[int, datetime | None] | None = None,
) -> ReplayInput:
    """Each close is available exactly at its delayed decision time unless overridden."""
    market_id = strategy_compiler.market_binding_id(strategy["market"])
    buckets = []
    for index, value in enumerate(prices):
        end = first_end + timedelta(minutes=5 * index)
        status = "COMPLETE_EMPTY" if value is None else "COMPLETE_OCCUPIED"
        reasons = ("EMPTY_BUCKET_NO_CLOSE",) if value is None else ()
        price_at = (price_available or {}).get(index, end + DELAY)
        volume_at = (volume_available or {}).get(index, end + DELAY)
        buckets.append(ReplayBucket(
            end, status,
            strategy_compiler.Observation(value, end, market_id, True, price_at, reasons),
            strategy_compiler.Observation("0" if value is None else "10", end, market_id, True, volume_at, reasons),
        ))
    dependencies = [{"series": "price", "offset_buckets": 0}]
    descriptor = {
        "schema_version": "p12.essential-evidence/1",
        "strategy_revision": "strategy-rev-delayed",
        "run_configuration_id": "run-config-delayed",
        "dataset_revision": "dataset-rev-delayed",
        "market_binding_id": market_id,
        "fields": {name: {"state": "BOUND", "essential_dependencies": copy.deepcopy(dependencies)}
                   for name in ("entry", "exit")},
    }
    return ReplayInput(
        strategy_revision_id="strategy-rev-delayed",
        run_configuration_id="run-config-delayed",
        dataset=ReplayDataset("dataset-rev-delayed", "QUALIFIED", True, market_id, tuple(buckets)),
        essential_evidence=descriptor,
        window_start=window[0],
        window_end=window[1],
        initial_cash_quote="1000",
    )


def _orders(result: simulator.ReplayResult) -> list[tuple[datetime, str]]:
    return [(event["at"], event["status"]) for event in result.events if event["kind"] == "ORDER"]


def test_delayed_buy_and_sell_settle_on_the_next_stale_close_with_hand_checked_arithmetic() -> None:
    strategy = _strategy()

    result = run_spot_replay(strategy, _run(strategy), timing_profile=DELAYED)

    # Source 09:55 decides at 10:00; 10:15 decides at the exclusive end and is coverage only.
    assert [sample["at"] for sample in result.samples] == [_at(10, 0), _at(10, 5), _at(10, 10), _at(10, 15)]
    assert [sample["source_bucket_end"] for sample in result.samples] == [_at(9, 55), _at(10, 0), _at(10, 5), _at(10, 10)]
    assert _orders(result) == [
        (_at(10, 0), "RESERVED"), (_at(10, 5), "BUY_FILLED"),
        (_at(10, 10), "RESERVED"), (_at(10, 15), "SELL_FILLED"),
        (_at(10, 15), "NO_NEXT_BUCKET"),
    ]
    buy = next(event for event in result.events if event.get("status") == "BUY_FILLED")
    # Close 8 * (1 + 0.25) = 10; 400 / 10 = 40 base; fee 400 * 0.001 = 0.4; cash 1000 - 400.4.
    assert (buy["fill_price"], buy["base_amount"], buy["fee_quote"], buy["cash_quote"]) == (
        Decimal("10"), Decimal("40"), Decimal("0.4"), Decimal("599.6"))
    assert (buy["signal_at"], buy["fill_at"], buy["source_bucket_end"], buy["available_at"]) == (
        _at(10, 0), _at(10, 5), _at(10, 0), _at(10, 5))
    assert (buy["timing_profile"], buy["fill_rule"], buy["fill_label"]) == (DELAYED, "NEXT_BUCKET_DELAYED_CLOSE", FILL_LABEL)
    sell = next(event for event in result.events if event.get("status") == "SELL_FILLED")
    # Close 12 * (1 - 0.25) = 9; 40 * 9 = 360 gross; fee 0.36; cash 599.6 + 359.64.
    assert (sell["fill_price"], sell["gross_quote"], sell["fee_quote"], sell["cash_quote"]) == (
        Decimal("9"), Decimal("360"), Decimal("0.36"), Decimal("959.24"))
    assert (sell["signal_at"], sell["fill_at"], sell["source_bucket_end"]) == (_at(10, 10), _at(10, 15), _at(10, 10))
    assert result.trades == ({
        "entry_at": _at(10, 0), "entry_origin": "REPLAY_SIGNAL", "exit_at": _at(10, 15),
        "base_amount": Decimal("40"), "entry_basis_quote": Decimal("400.4"),
        "gross_quote": Decimal("360"), "exit_fee_quote": Decimal("0.36"), "gain_loss_quote": Decimal("-40.76"),
        "timing_profile": DELAYED, "fill_label": FILL_LABEL,
    },)
    # Marks: 1000; 599.6 + 40 * 8; 599.6 + 40 * 12 = 1079.6; 959.24.
    assert [sample["account_value_quote"] for sample in result.samples] == [
        Decimal("1000"), Decimal("919.6"), Decimal("1079.6"), Decimal("959.24")]
    assert result.metrics == {"gain_loss_quote": Decimal("-40.76"), "completed_trade_pairs": 1,
                              "largest_drawdown_quote": Decimal("120.36")}
    assert result.evidence_class == "SYNTHETIC_FIXTURE"
    assert all("EXECUTABLE" not in str(event.get("fill_label", "")).upper() for event in result.events)


def test_decisions_retain_source_clock_and_policy_identity() -> None:
    strategy = _strategy()

    result = run_spot_replay(strategy, _run(strategy), timing_profile=DELAYED)

    decisions = [event for event in result.events if event["kind"] == "DECISION"]
    assert [(event["at"], event["signal_at"], event["source_bucket_end"]) for event in decisions] == [
        (_at(10, 0), _at(10, 0), _at(9, 55)), (_at(10, 5), _at(10, 5), _at(10, 0)),
        (_at(10, 10), _at(10, 10), _at(10, 5)), (_at(10, 15), _at(10, 15), _at(10, 10))]
    assert {event["timing_profile"] for event in decisions} == {DELAYED}
    reserved = [event for event in result.events if event.get("status") == "RESERVED"]
    assert [(event["signal_at"], event["fill_at"]) for event in reserved] == [
        (_at(10, 0), _at(10, 5)), (_at(10, 10), _at(10, 15))]
    assert all(event["at"] < _at(10, 20) for event in result.events)


def test_input_available_exactly_at_the_delayed_decision_passes_and_one_microsecond_late_blocks() -> None:
    strategy = _strategy()
    on_time = run_spot_replay(strategy, _run(strategy), timing_profile=DELAYED)
    assert on_time.events[0]["entry"]["eligible"] is True

    late = run_spot_replay(strategy, _run(strategy, price_available={0: _at(10, 0) + MICROSECOND}),
                           timing_profile=DELAYED)

    first = late.events[0]
    assert first["kind"] == "DECISION"
    assert first["entry"]["eligible"] is False
    assert first["entry"]["eligibility_status"] == "ESSENTIAL_EVIDENCE_UNAVAILABLE"
    assert "LATE_INPUT" in first["entry"]["eligibility_reasons"]
    assert late.samples[0]["account_value_quote"] is None
    assert late.samples[0]["mark_reasons"] == ("LATE_INPUT",)


def test_unknown_availability_blocks_the_delayed_decision() -> None:
    strategy = _strategy()

    result = run_spot_replay(strategy, _run(strategy, price_available={0: None}), timing_profile=DELAYED)

    entry = result.events[0]["entry"]
    assert entry["eligible"] is False
    assert "AVAILABILITY_UNKNOWN" in entry["eligibility_reasons"]


def test_hidden_boolean_branch_with_a_late_input_blocks_the_decision() -> None:
    entry = {"op": "or", "args": [
        {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "7", "unit": "PRICE"}]},
        {"op": "gt", "args": [{"op": "quote_volume"}, {"op": "constant", "value": "1", "unit": f"QUOTE:{QUOTE_ASSET}"}]},
    ]}
    strategy = _strategy(entry=entry, data_inputs=["price", "quote_volume"])

    result = run_spot_replay(strategy, _run(strategy, volume_available={0: _at(10, 0) + MICROSECOND}),
                             timing_profile=DELAYED)

    first = result.events[0]["entry"]
    assert first["value"] == strategy_compiler.Truth.TRUE
    assert first["eligible"] is False
    assert first["eligibility_status"] == "TIMING_UNAVAILABLE"
    assert first["eligibility_reasons"] == ("FUTURE_INFORMATION:0",)
    assert all(event["status"] != "RESERVED" for event in result.events
               if event["kind"] == "ORDER" and event["at"] == _at(10, 0))


def test_warmup_is_validated_before_the_shifted_first_index_not_the_legacy_one() -> None:
    lagged = {"op": "gt", "args": [{"op": "lag", "buckets": 1, "value": {"op": "price"}},
                                   {"op": "constant", "value": "7", "unit": "PRICE"}]}
    strategy = _strategy(entry=lagged, warmup=1)
    short = _run(strategy)

    assert run_spot_replay(strategy, short).samples[0]["at"] == _at(10, 0)
    with pytest.raises(ReplayError) as error:
        run_spot_replay(strategy, short, timing_profile=DELAYED)
    assert error.value.code == "DATASET_COVERAGE_UNPROVEN"

    longer = _run(strategy, ("8", "8", "8", "12", "12", "100"), first_end=_at(9, 50))
    result = run_spot_replay(strategy, longer, timing_profile=DELAYED)
    first = result.events[0]
    assert (first["at"], first["source_bucket_end"]) == (_at(10, 0), _at(9, 55))
    assert first["entry"]["value"] == strategy_compiler.Truth.TRUE
    assert first["entry"]["eligible"] is True


def test_missing_source_coverage_for_the_first_delayed_decision_fails() -> None:
    strategy = _strategy()
    no_prior_bucket = _run(strategy, ("8", "12", "12", "100"), first_end=_at(10, 0))

    run_spot_replay(strategy, no_prior_bucket)
    with pytest.raises(ReplayError) as error:
        run_spot_replay(strategy, no_prior_bucket, timing_profile=DELAYED)
    assert error.value.code == "DATASET_COVERAGE_UNPROVEN"


def test_legacy_coverage_rules_still_apply_to_the_delayed_profile() -> None:
    strategy = _strategy()
    truncated = _run(strategy, ("8", "8", "12", "12"))

    with pytest.raises(ReplayError) as error:
        run_spot_replay(strategy, truncated, timing_profile=DELAYED)
    assert error.value.code == "DATASET_COVERAGE_UNPROVEN"


@pytest.mark.parametrize(("override", "reason"), [
    ({"price_available": {1: _at(10, 5) + MICROSECOND}}, "LATE_INPUT"),
    ({"price_available": {1: None}}, "AVAILABILITY_UNKNOWN"),
    ({"prices": ("8", None, "12", "12", "100")}, "EMPTY_BUCKET_NO_CLOSE"),
])
def test_unavailable_next_close_releases_the_reservation_once_without_substitution(
    override: dict[str, Any], reason: str,
) -> None:
    strategy = _strategy()
    run = _run(strategy, **override)

    result = run_spot_replay(strategy, run, timing_profile=DELAYED)

    released = [event for event in result.events if event.get("status") == "FILL_UNAVAILABLE"]
    assert len(released) == 1
    assert released[0]["at"] == _at(10, 5)
    assert reason in released[0]["reasons"]
    assert (released[0]["reservation_released_quote"], released[0]["reservation_released_base"]) == (
        Decimal("400.4"), Decimal("0"))
    assert result.samples[1]["reserved_quote"] == Decimal("0")
    assert result.samples[1]["cash_quote"] == Decimal("1000")
    # No earlier/later close replaces it: the next fill comes only from a new 10:10 reservation at 10:15.
    assert [status for _, status in _orders(result)] == [
        "RESERVED", "FILL_UNAVAILABLE", "RESERVED", "BUY_FILLED", "NO_NEXT_BUCKET"]
    fills = [event for event in result.events if event.get("status") == "BUY_FILLED"]
    assert [(event["at"], event["source_bucket_end"], event["fill_price"]) for event in fills] == [
        (_at(10, 15), _at(10, 10), Decimal("15"))]


def test_exclusive_end_excludes_the_shifted_final_source_bucket() -> None:
    strategy = _strategy()

    result = run_spot_replay(strategy, _run(strategy, ("6", "6", "6", "6", "8")), timing_profile=DELAYED)

    assert all(sample["source_bucket_end"] != _at(10, 15) for sample in result.samples)
    assert all(event["at"] < _at(10, 20) for event in result.events)
    assert _orders(result) == []
    assert result.trades == ()


def test_unknown_timing_profiles_fail() -> None:
    strategy = _strategy()
    run = _run(strategy)
    for profile in ("p12.spot-replay/2", "", "EDGE-OS.DELAYED-HISTORY-REPLAY/1", None, ["p12.spot-replay/1"]):
        with pytest.raises(ReplayError) as error:
            run_spot_replay(strategy, run, timing_profile=profile)  # type: ignore[arg-type]
        assert error.value.code == "UNSUPPORTED_TIMING_PROFILE"


def test_default_profile_output_and_fingerprint_are_unchanged() -> None:
    strategy = _strategy()
    run = _run(strategy)

    default = run_spot_replay(strategy, run)
    explicit = run_spot_replay(strategy, run, timing_profile=LEGACY)

    assert default == explicit
    assert default.repeatability_id == LEGACY_BASE_FINGERPRINT
    assert all("timing_profile" not in event and "source_bucket_end" not in event for event in default.events)
    assert all("source_bucket_end" not in sample for sample in default.samples)
    assert [sample["at"] for sample in default.samples] == [_at(10, 0), _at(10, 5), _at(10, 10), _at(10, 15)]


def test_delayed_fingerprint_is_separate_and_binds_the_complete_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    from edge_os_api.replay import delayed_history_profile

    strategy = _strategy()
    run = _run(strategy)
    legacy = run_spot_replay(strategy, run).repeatability_id
    delayed = run_spot_replay(strategy, run, timing_profile=DELAYED).repeatability_id
    assert delayed != legacy
    assert delayed == run_spot_replay(strategy, run, timing_profile=DELAYED).repeatability_id
    assert dict(delayed_history_profile.POLICY) == {
        "schema_version": DELAYED, "decision_delay_seconds": 300,
        "fill_rule": "NEXT_BUCKET_DELAYED_CLOSE", "fill_label": FILL_LABEL,
    }

    for key, value in (("decision_delay_seconds", 301), ("fill_rule", "OTHER"), ("fill_label", "Other")):
        changed = {**delayed_history_profile.POLICY, key: value}
        monkeypatch.setattr(delayed_history_profile, "POLICY", changed)
        assert run_spot_replay(strategy, run, timing_profile=DELAYED).repeatability_id != delayed
        monkeypatch.undo()


def test_four_bucket_tuple_outcomes_include_zero_fills_and_at_most_one_round_trip() -> None:
    strategy = _strategy()
    outcomes: set[tuple[str, ...]] = set()
    for prices in itertools.product(("6", "8", "12"), repeat=4):
        result = run_spot_replay(strategy, _run(strategy, prices, window=(_at(10, 0), _at(10, 15))),
                                 timing_profile=DELAYED)
        assert len(result.samples) == 3
        assert result.metrics["completed_trade_pairs"] <= 1
        outcomes.add(tuple(status for _, status in _orders(result) if status != "RESERVED"))
    assert outcomes == {
        (),
        ("NO_NEXT_BUCKET",),
        ("BUY_FILLED",),
        ("BUY_FILLED", "NO_NEXT_BUCKET"),
        ("BUY_FILLED", "SELL_FILLED"),
        ("BUY_FILLED", "SELL_FILLED", "NO_NEXT_BUCKET"),
    }
