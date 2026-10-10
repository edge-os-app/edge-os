from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.strategies import compiler as strategy_compiler
from edge_os_api.replay.simulator import ReplayBucket, ReplayDataset, ReplayError, ReplayInput, run_spot_replay

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "spot_replay" / "wc01.json"
REFERENCE_CASES_PATH = Path(__file__).parent / "fixtures" / "spot_replay" / "p12_reference_cases.json"


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _wc01_input() -> tuple[dict[str, Any], ReplayInput, dict[str, Any]]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    strategy = copy.deepcopy(record_contract.FIXTURE_STRATEGY)
    strategy["entry"] = {
        "op": "gt",
        "args": [{"op": "price"}, {"op": "constant", "value": "7", "unit": "PRICE"}],
    }
    strategy["exit"] = {
        "op": "gte",
        "args": [{"op": "price"}, {"op": "constant", "value": "9", "unit": "PRICE"}],
    }
    strategy["invalidation"] = {"state": "NOT_REQUESTED", "source_ref": "synthetic-wc01"}
    strategy["data_inputs"] = ["price"]
    strategy["sizing"]["amount"] = "400"
    strategy["cost_assumptions"] = {"fee_rate": "0.001", "slippage_rate": "0", "source_ref": "synthetic-wc01"}
    strategy["risk_limits"]["max_quote_notional"] = "400"
    strategy["warmup_buckets"] = 0
    strategy = strategy_compiler.build_strategy(
        "synthetic-strategy-wc01-v1",
        {name: strategy[name] for name in record_contract.CREATE_STRATEGY_FIELDS if name != "restrictions"},
    )
    strategy_compiler.validate_strategy(strategy)

    market_id = strategy_compiler.market_binding_id(strategy["market"])
    fixture["essential_evidence"]["market_binding_id"] = market_id
    buckets = tuple(
        ReplayBucket(
            bucket_end=_moment(bucket["bucket_end"]),
            status=bucket["status"],
            price=strategy_compiler.Observation(
                value=bucket["price"],
                bucket_end=_moment(bucket["bucket_end"]),
                market_binding_id=market_id,
                qualified=bucket["status"] == "COMPLETE_OCCUPIED",
                available_at=_moment(bucket["available_at"]) if bucket["available_at"] else None,
                reasons=tuple(bucket.get("reasons", ())),
            ),
            quote_volume=strategy_compiler.Observation(
                value=bucket["quote_volume"],
                bucket_end=_moment(bucket["bucket_end"]),
                market_binding_id=market_id,
                qualified=bucket["status"] in {"COMPLETE_OCCUPIED", "COMPLETE_EMPTY"},
                available_at=_moment(bucket["available_at"]) if bucket["available_at"] else None,
                reasons=tuple(bucket.get("reasons", ())),
            ),
        )
        for bucket in fixture["buckets"]
    )
    dataset = ReplayDataset(
        revision_id=fixture["dataset_revision_id"],
        qualification="QUALIFIED",
        coverage_complete=True,
        market_binding_id=market_id,
        buckets=buckets,
        evidence_class="SYNTHETIC_FIXTURE",
    )
    replay_input = ReplayInput(
        strategy_revision_id=fixture["strategy_revision_id"],
        run_configuration_id=fixture["run_configuration_id"],
        dataset=dataset,
        essential_evidence=fixture["essential_evidence"],
        window_start=_moment(fixture["window_start"]),
        window_end=_moment(fixture["window_end"]),
        initial_cash_quote=fixture["initial_cash_quote"],
    )
    return strategy, replay_input, fixture["expected"]


def _reference_case(name: str) -> dict[str, Any]:
    fixture = json.loads(REFERENCE_CASES_PATH.read_text(encoding="utf-8"))
    assert fixture["evidence_class"] == "SYNTHETIC_FIXTURE"
    return fixture["cases"][name]


def _rebuild_strategy(strategy: dict[str, Any], **changes: Any) -> dict[str, Any]:
    strategy_id = changes.pop("strategy_id", strategy["strategy_id"])
    values = {name: copy.deepcopy(strategy[name]) for name in record_contract.CREATE_STRATEGY_FIELDS
              if name != "restrictions"}
    for name, value in changes.items():
        if name != "invalidation" and isinstance(values.get(name), dict) and isinstance(value, dict):
            values[name].update(value)
        else:
            values[name] = value
    rebuilt = strategy_compiler.build_strategy(strategy_id, values)
    strategy_compiler.validate_strategy(rebuilt)
    return rebuilt


def _scheduled_run(
    strategy: dict[str, Any],
    replay_input: ReplayInput,
    prices: tuple[str | None, ...],
    *,
    schedule_start: datetime,
    window_start: datetime,
    window_end: datetime,
    availability: tuple[datetime | None, ...] | None = None,
    statuses: tuple[str, ...] | None = None,
) -> ReplayInput:
    market_id = strategy_compiler.market_binding_id(strategy["market"])
    buckets: list[ReplayBucket] = []
    for index, value in enumerate(prices):
        moment = schedule_start + timedelta(minutes=5 * index)
        status = statuses[index] if statuses else "COMPLETE_EMPTY" if value is None else "COMPLETE_OCCUPIED"
        available_at = availability[index] if availability else moment
        source_reasons = (("EMPTY_BUCKET_NO_CLOSE",) if status == "COMPLETE_EMPTY" else
                          ("COVERAGE_NOT_PROVEN",) if status == "INCOMPLETE" else
                          ("UNQUALIFIED_RECORDS",) if status == "UNQUALIFIED" else ())
        price = strategy_compiler.Observation(
            value, moment, market_id, status == "COMPLETE_OCCUPIED" or status == "COMPLETE_EMPTY",
            available_at, source_reasons,
        )
        volume_value = "0" if status == "COMPLETE_EMPTY" else "10"
        volume = strategy_compiler.Observation(
            volume_value, moment, market_id, status in {"COMPLETE_OCCUPIED", "COMPLETE_EMPTY"},
            available_at, source_reasons,
        )
        buckets.append(ReplayBucket(moment, status, price, volume))
    dataset = replace(
        replay_input.dataset,
        market_binding_id=market_id,
        buckets=tuple(buckets),
    )
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor.update({
        "strategy_revision": replay_input.strategy_revision_id,
        "run_configuration_id": replay_input.run_configuration_id,
        "dataset_revision": dataset.revision_id,
        "market_binding_id": market_id,
    })
    return replace(
        replay_input,
        dataset=dataset,
        essential_evidence=descriptor,
        window_start=window_start,
        window_end=window_end,
    )


def test_spot_replay_reconciles_the_adopted_full_entry_and_exit_case() -> None:
    strategy, replay_input, expected = _wc01_input()

    result = run_spot_replay(strategy, replay_input)

    assert result.evidence_class == "SYNTHETIC_FIXTURE"
    assert [sample["cash_quote"] for sample in result.samples] == [
        Decimal(value) for value in expected["cash_by_sample"]
    ]
    assert [sample["base_amount"] for sample in result.samples] == [
        Decimal(value) for value in expected["base_by_sample"]
    ]
    assert [sample["account_value_quote"] for sample in result.samples] == [
        Decimal(value) for value in expected["account_value_by_sample"]
    ]
    terminal_order_statuses = {"BUY_FILLED", "SELL_FILLED", "NO_NEXT_BUCKET"}
    assert [event["status"] for event in result.events
            if event["kind"] == "ORDER" and event["status"] in terminal_order_statuses] == expected["orders"]
    assert result.metrics == {
        "gain_loss_quote": Decimal(expected["gain_loss_quote"]),
        "completed_trade_pairs": expected["completed_trade_pairs"],
        "largest_drawdown_quote": Decimal(expected["largest_drawdown_quote"]),
    }
    assert result.metric_statuses == {
        "gain_loss_quote": "AVAILABLE",
        "completed_trade_pairs": "AVAILABLE",
        "largest_drawdown_quote": "AVAILABLE",
    }
    assert result.metric_reasons == {
        "gain_loss_quote": (),
        "completed_trade_pairs": (),
        "largest_drawdown_quote": (),
    }


def test_spot_replay_is_repeatable_for_the_same_saved_identity_tuple() -> None:
    strategy, replay_input, _ = _wc01_input()

    first = run_spot_replay(strategy, replay_input)
    second = run_spot_replay(strategy, replay_input)

    assert first.repeatability_id == second.repeatability_id
    assert first.samples == second.samples
    assert first.events == second.events
    assert first.trades == second.trades


def test_spot_replay_rejects_insufficient_cash_without_resizing_the_entry() -> None:
    strategy, replay_input, _ = _wc01_input()
    replay_input = replace(replay_input, initial_cash_quote="100")

    result = run_spot_replay(strategy, replay_input)

    orders = [event for event in result.events if event["kind"] == "ORDER"]
    assert any(event["status"] == "INSUFFICIENT_CASH" for event in orders)
    assert all(event["status"] != "BUY_FILLED" for event in orders)
    assert all(sample["cash_quote"] == Decimal("100") for sample in result.samples)
    assert result.trades == ()


def test_spot_replay_releases_a_late_fill_reservation_once_when_later_mark_recovers() -> None:
    strategy, replay_input, _ = _wc01_input()
    buckets = list(replay_input.dataset.buckets)
    late_price = replace(buckets[1].price, available_at=_moment("2026-10-01T12:12:00Z"))
    buckets[1] = replace(buckets[1], price=late_price)
    dataset = replace(replay_input.dataset, buckets=tuple(buckets))
    replay_input = replace(replay_input, dataset=dataset)

    result = run_spot_replay(strategy, replay_input)

    failures = [event for event in result.events
                if event.get("kind") == "ORDER" and event.get("status") == "FILL_UNAVAILABLE"]
    assert len(failures) == 1
    assert failures[0]["reservation_released_quote"] == Decimal("400.4")
    assert failures[0]["reasons"] == ("LATE_INPUT",)
    assert result.samples[1]["cash_quote"] == Decimal("1000")
    assert result.samples[1]["account_value_quote"] is None
    assert result.samples[1]["mark_reasons"] == ("LATE_INPUT",)
    assert result.metrics["gain_loss_quote"] == Decimal("-0.400")
    assert result.metric_statuses["gain_loss_quote"] == "AVAILABLE"
    assert result.metric_reasons["gain_loss_quote"] == ()


def test_spot_replay_rejects_a_descriptor_for_another_dataset_before_running() -> None:
    strategy, replay_input, _ = _wc01_input()
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor["dataset_revision"] = "synthetic-dataset-other"
    replay_input = replace(replay_input, essential_evidence=descriptor)

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "ESSENTIAL_BINDING_IDENTITY_MISMATCH"
    else:
        raise AssertionError("a mismatched essential-evidence descriptor must fail preflight")


def test_spot_replay_preserves_true_or_unknown_and_blocks_only_essential_missing_input() -> None:
    strategy, replay_input, _ = _wc01_input()
    strategy["data_inputs"] = ["price", "quote_volume"]
    strategy["entry"] = {
        "op": "or",
        "args": [
            {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "100", "unit": "PRICE"}]},
            {"op": "gt", "args": [{"op": "quote_volume"}, {"op": "constant", "value": "0", "unit": strategy["market"]["quote_unit"]}]},
        ],
    }
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor["fields"]["entry"]["essential_dependencies"] = [{"series": "quote_volume", "offset_buckets": 0}]
    replay_input = replace(replay_input, essential_evidence=descriptor)
    buckets = list(replay_input.dataset.buckets)
    buckets[0] = replace(buckets[0], price=replace(buckets[0].price, value="110"))
    missing_volume = replace(buckets[0].quote_volume, value=None, reasons=("MISSING_QUOTE_VOLUME",))
    buckets[0] = replace(buckets[0], quote_volume=missing_volume)
    replay_input = replace(replay_input, dataset=replace(replay_input.dataset, buckets=tuple(buckets)))

    result = run_spot_replay(strategy, replay_input)

    decision = next(event for event in result.events if event["kind"] == "DECISION")
    assert decision["entry"]["value"] == strategy_compiler.Truth.TRUE
    assert decision["entry"]["reasons"] == ("MISSING_QUOTE_VOLUME", "MISSING_QUOTE_VOLUME:0")
    assert decision["entry"]["eligible"] is False
    assert decision["entry"]["eligibility_status"] == "ESSENTIAL_EVIDENCE_UNAVAILABLE"
    assert not any(event.get("at") == _moment("2026-10-01T12:05:00Z")
                   and event.get("status") == "RESERVED" and event.get("side") == "BUY"
                   for event in result.events)


def test_spot_replay_blocks_future_or_unknown_timing_from_a_decisive_boolean_sibling() -> None:
    strategy, replay_input, _ = _wc01_input()
    expression = {
        "op": "or",
        "args": [
            {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "7", "unit": "PRICE"}]},
            {"op": "gt", "args": [{"op": "quote_volume"}, {"op": "constant", "value": "1", "unit": f"QUOTE:{strategy['market']['research_binding']['quote_asset']}"}]},
        ],
    }
    strategy = _rebuild_strategy(strategy, entry=expression, exit=expression, data_inputs=["price", "quote_volume"])
    first = replay_input.dataset.buckets[0]
    assert first.quote_volume is not None
    late = replace(first.quote_volume, available_at=first.bucket_end + timedelta(minutes=2))
    late_input = replace(
        replay_input,
        dataset=replace(replay_input.dataset, buckets=(replace(first, quote_volume=late),) + replay_input.dataset.buckets[1:]),
    )

    late_result = run_spot_replay(strategy, late_input)
    late_decision = next(event for event in late_result.events if event["kind"] == "DECISION")
    for field_name in ("entry", "exit"):
        assert late_decision[field_name]["value"] == "TRUE"
        assert "FUTURE_INFORMATION:0" in late_decision[field_name]["reasons"]
        assert late_decision[field_name]["eligible"] is False
        assert late_decision[field_name]["eligibility_status"] == "TIMING_UNAVAILABLE"
        assert "FUTURE_INFORMATION:0" in late_decision[field_name]["eligibility_reasons"]
    assert not any(event.get("at") == first.bucket_end and event.get("status") == "RESERVED"
                   for event in late_result.events)

    unknown = replace(first.quote_volume, available_at=None)
    unknown_input = replace(
        replay_input,
        dataset=replace(replay_input.dataset, buckets=(replace(first, quote_volume=unknown),) + replay_input.dataset.buckets[1:]),
    )
    unknown_result = run_spot_replay(strategy, unknown_input)
    unknown_decision = next(event for event in unknown_result.events if event["kind"] == "DECISION")
    for field_name in ("entry", "exit"):
        assert unknown_decision[field_name]["value"] == "TRUE"
        assert unknown_decision[field_name]["eligible"] is False
        assert unknown_decision[field_name]["eligibility_status"] == "TIMING_UNAVAILABLE"
        assert "AVAILABILITY_UNKNOWN:0" in unknown_decision[field_name]["eligibility_reasons"]
    assert not any(event.get("at") == first.bucket_end and event.get("status") == "RESERVED"
                   for event in unknown_result.events)


def test_present_null_consumed_observations_still_require_timing_before_reservation() -> None:
    original, original_run, _ = _wc01_input()
    quote_unit = f"QUOTE:{original['market']['research_binding']['quote_asset']}"
    operands = (
        ("price", {"op": "price"}, "price", 2, "PRICE"),
        ("volume", {"op": "quote_volume"}, "quote_volume", 2, quote_unit),
        ("lag-price", {"op": "lag", "value": {"op": "price"}, "buckets": 1}, "price", 1, "PRICE"),
        ("lag-volume", {"op": "lag", "value": {"op": "quote_volume"}, "buckets": 1}, "quote_volume", 1, quote_unit),
        ("sum-price", {"op": "sum", "value": {"op": "price"}, "buckets": 2}, "price", 1, "PRICE"),
        ("mean-price", {"op": "mean", "value": {"op": "price"}, "buckets": 2}, "price", 1, "PRICE"),
        ("sum-volume", {"op": "sum", "value": {"op": "quote_volume"}, "buckets": 2}, "quote_volume", 1, quote_unit),
        ("mean-volume", {"op": "mean", "value": {"op": "quote_volume"}, "buckets": 2}, "quote_volume", 1, quote_unit),
        ("price-return-endpoint", {"op": "price_return", "lookback_buckets": 2}, "price", 0, "DIMENSIONLESS"),
        ("relative-volume-history", {"op": "relative_volume", "lookback_buckets": 2}, "quote_volume", 0, "DIMENSIONLESS"),
    )
    start = _moment("2026-10-01T12:00:00Z")
    decision_time = start + timedelta(minutes=10)
    for name, operand, series, position, unit in operands:
        sibling_series = "quote_volume" if series == "price" else "price"
        sibling_unit = quote_unit if sibling_series == "quote_volume" else "PRICE"
        expression = {"op": "or", "args": [
            {"op": "gt", "args": [operand, {"op": "constant", "value": "0", "unit": unit}]},
            {"op": "gt", "args": [{"op": sibling_series}, {"op": "constant", "value": "0", "unit": sibling_unit}]},
        ]}
        strategy = _rebuild_strategy(
            original, entry=expression, exit=expression, data_inputs=["price", "quote_volume"],
        )
        run = _scheduled_run(
            strategy, original_run, ("8",) * 6, schedule_start=start,
            window_start=decision_time, window_end=start + timedelta(minutes=30),
        )
        descriptor = copy.deepcopy(run.essential_evidence)
        descriptor["fields"] = {
            field: {"state": "BOUND", "essential_dependencies": []} for field in ("entry", "exit")
        }
        run = replace(run, essential_evidence=descriptor)
        for action in ("BUY", "SELL"):
            for delivery in ("timely", "late", "unknown"):
                buckets = list(run.dataset.buckets)
                bucket = buckets[position]
                observation = getattr(bucket, series)
                assert observation is not None, (name, position)
                available_at = (
                    bucket.bucket_end if delivery == "timely"
                    else decision_time + timedelta(minutes=2) if delivery == "late"
                    else None
                )
                buckets[position] = replace(bucket, **{
                    series: replace(observation, value=None, available_at=available_at,
                                    reasons=("AUTHORED_MISSING",)),
                })
                candidate = replace(
                    run,
                    dataset=replace(run.dataset, buckets=tuple(buckets)),
                    initial_base_amount="0" if action == "BUY" else "25",
                    initial_basis_quote="0" if action == "BUY" else "100",
                )
                result = run_spot_replay(strategy, candidate)
                decision = next(event for event in result.events
                                if event["kind"] == "DECISION" and event["at"] == decision_time)
                field = "entry" if action == "BUY" else "exit"
                assert decision[field]["value"] == "TRUE", (name, action, delivery)
                assert "AUTHORED_MISSING" in decision[field]["reasons"], (name, action, delivery)
                expected_reason = f"MISSING_PRICE:{position}" if series == "price" else f"MISSING_QUOTE_VOLUME:{position}"
                assert expected_reason in decision[field]["reasons"], (name, action, delivery)
                orders = [event for event in result.events
                          if event["kind"] == "ORDER" and event["at"] == decision_time
                          and event.get("side") == action]
                reserved = any(event["status"] == "RESERVED" for event in orders)
                if delivery == "timely":
                    assert reserved, (name, action, delivery)
                else:
                    assert not reserved, (name, action, delivery, orders)
                    assert decision[field]["eligible"] is False, (name, action, delivery)
                    assert decision[field]["eligibility_status"] == "TIMING_UNAVAILABLE", (name, action, delivery)
                    expected_timing_reason = (
                        f"FUTURE_INFORMATION:{position}" if delivery == "late"
                        else f"AVAILABILITY_UNKNOWN:{position}"
                    )
                    assert decision[field]["eligibility_reasons"] == (expected_timing_reason,), (name, action, delivery)


def test_price_return_keeps_timing_of_its_two_endpoints_not_an_unused_gap() -> None:
    strategy, replay_input, _ = _wc01_input()
    strategy = _rebuild_strategy(
        strategy,
        data_inputs=["price"],
        entry={"op": "gt", "args": [
            {"op": "price_return", "lookback_buckets": 2},
            {"op": "constant", "value": "0.05", "unit": "DIMENSIONLESS"},
        ]},
    )
    start = _moment("2026-10-01T12:00:00Z")
    replay_input = _scheduled_run(
        strategy, replay_input, ("100", None, "110", "115"), schedule_start=start,
        window_start=start + timedelta(minutes=10), window_end=start + timedelta(minutes=20),
    )
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor["fields"]["entry"]["essential_dependencies"] = []
    replay_input = replace(replay_input, essential_evidence=descriptor)

    result = run_spot_replay(strategy, replay_input)

    decision = next(event for event in result.events if event["kind"] == "DECISION")
    assert decision["entry"]["value"] == strategy_compiler.Truth.TRUE
    assert decision["entry"]["reasons"] == ("EMPTY_BUCKET_NO_CLOSE", "MISSING_PRICE:1")
    assert decision["entry"]["eligible"] is True
    assert not any(event["kind"] == "ORDER" and event["at"] == start + timedelta(minutes=10)
                   and event.get("status") == "RESERVED" and event.get("side") == "SELL"
                   for event in result.events)
    assert any(event["kind"] == "ORDER" and event["at"] == start + timedelta(minutes=10)
               and event.get("status") == "RESERVED" and event.get("side") == "BUY"
               for event in result.events)


def test_spot_replay_rejects_unknown_descriptor_fields_as_invalid_not_unresolved() -> None:
    strategy, replay_input, _ = _wc01_input()
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    assert descriptor is not None
    descriptor["fields"]["invalidation"] = {"state": "BOUND", "essential_dependencies": []}
    with pytest.raises(ReplayError) as captured:
        run_spot_replay(strategy, replace(replay_input, essential_evidence=descriptor))
    assert captured.value.code == "INVALID_ESSENTIAL_BINDING"


def test_spot_replay_preserves_p06_market_mismatch_and_fails_essential_binding() -> None:
    strategy, replay_input, _ = _wc01_input()
    buckets = list(replay_input.dataset.buckets)
    buckets[0] = replace(buckets[0], price=replace(buckets[0].price, market_binding_id="other-market"))
    replay_input = replace(replay_input, dataset=replace(replay_input.dataset, buckets=tuple(buckets)))

    result = run_spot_replay(strategy, replay_input)

    decision = next(event for event in result.events if event.get("kind") == "DECISION")
    assert decision["entry"]["value"] == strategy_compiler.Truth.UNKNOWN
    assert decision["entry"]["reasons"] == ("MARKET_BINDING_MISMATCH:0",)
    assert decision["entry"]["eligible"] is False
    assert decision["entry"]["eligibility_reasons"] == ("MARKET_BINDING_MISMATCH:0",)


def test_spot_replay_preserves_p06_schedule_mismatch_and_fails_essential_binding() -> None:
    strategy, replay_input, _ = _wc01_input()
    buckets = list(replay_input.dataset.buckets)
    buckets[0] = replace(buckets[0], price=replace(buckets[0].price, bucket_end=_moment("2026-10-01T12:00:00Z")))
    replay_input = replace(replay_input, dataset=replace(replay_input.dataset, buckets=tuple(buckets)))

    result = run_spot_replay(strategy, replay_input)

    decision = next(event for event in result.events if event.get("kind") == "DECISION")
    assert decision["entry"]["value"] == strategy_compiler.Truth.UNKNOWN
    assert decision["entry"]["reasons"] == ("SCHEDULE_MISMATCH:0",)
    assert decision["entry"]["eligible"] is False
    assert decision["entry"]["eligibility_reasons"] == ("SCHEDULE_MISMATCH:0",)


def test_spot_replay_keeps_open_inventory_and_its_fee_inclusive_basis() -> None:
    strategy, replay_input, _ = _wc01_input()
    strategy["exit"] = {
        "op": "gte",
        "args": [{"op": "price"}, {"op": "constant", "value": "1000", "unit": "PRICE"}],
    }
    buckets = replay_input.dataset.buckets[:-1]
    dataset = replace(replay_input.dataset, buckets=buckets)
    replay_input = replace(replay_input, dataset=dataset, window_end=_moment("2026-10-01T12:20:00Z"))

    result = run_spot_replay(strategy, replay_input)

    assert result.open_position == {
        "base_amount": Decimal("50"),
        "weighted_basis_quote": Decimal("400.4"),
        "last_qualified_mark": Decimal("9"),
        "last_mark_at": _moment("2026-10-01T12:15:00Z"),
        "last_available_at": _moment("2026-10-01T12:15:00Z"),
    }
    assert result.metrics["completed_trade_pairs"] == 0


def test_spot_replay_rejects_positive_essential_offsets_before_replay() -> None:
    strategy, replay_input, _ = _wc01_input()
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor["fields"]["entry"]["essential_dependencies"][0]["offset_buckets"] = 1
    replay_input = replace(replay_input, essential_evidence=descriptor)

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "INVALID_ESSENTIAL_BINDING"
    else:
        raise AssertionError("a positive essential offset must fail preflight")


def test_spot_replay_reports_missing_exit_binding_without_inventing_an_empty_set() -> None:
    strategy, replay_input, _ = _wc01_input()
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    del descriptor["fields"]["exit"]
    replay_input = replace(replay_input, essential_evidence=descriptor)

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "UNRESOLVED_ESSENTIAL_EVIDENCE"
    else:
        raise AssertionError("a missing exit binding must not become an explicit empty set")


def test_spot_replay_rejects_unbound_exit_without_treating_it_as_empty() -> None:
    strategy, replay_input, _ = _wc01_input()
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor["fields"]["exit"] = {"state": "UNBOUND"}
    replay_input = replace(replay_input, essential_evidence=descriptor)

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "UNRESOLVED_ESSENTIAL_EVIDENCE"
    else:
        raise AssertionError("an explicit UNBOUND exit is not an empty dependency set")


def test_spot_replay_rejects_malformed_essential_dependencies() -> None:
    invalid_dependencies = (
        [{"series": "bid_ask", "offset_buckets": 0}],
        [{"series": "price", "offset_buckets": 0}, {"series": "price", "offset_buckets": 0}],
        [{"series": "price", "offset_buckets": True}],
        [{"series": "price", "offset_buckets": "0"}],
    )
    for dependencies in invalid_dependencies:
        strategy, replay_input, _ = _wc01_input()
        descriptor = copy.deepcopy(replay_input.essential_evidence)
        descriptor["fields"]["entry"]["essential_dependencies"] = dependencies
        replay_input = replace(replay_input, essential_evidence=descriptor)

        try:
            run_spot_replay(strategy, replay_input)
        except ValueError as error:
            assert getattr(error, "code") == "INVALID_ESSENTIAL_BINDING"
        else:
            raise AssertionError(f"malformed dependencies must be rejected: {dependencies!r}")


def test_spot_replay_keeps_valid_boolean_invalidation_unsupported() -> None:
    strategy, replay_input, _ = _wc01_input()
    strategy["invalidation"] = {"op": "lt", "args": [
        {"op": "price"}, {"op": "constant", "value": "5", "unit": "PRICE"}
    ]}
    strategy["warmup_buckets"] = 0

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "UNSUPPORTED_INVALIDATION"
    else:
        raise AssertionError("P12/1 must reject Boolean invalidation before replay")


def test_spot_replay_rejects_a_non_positive_derived_sell_fill_before_action() -> None:
    strategy, replay_input, _ = _wc01_input()
    strategy["cost_assumptions"]["slippage_rate"] = "1"

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "UNSUPPORTED_COST_ASSUMPTIONS"
    else:
        raise AssertionError("a saved slippage rate that makes sell fills zero must fail preflight")


def test_spot_replay_rejects_a_complete_empty_bucket_with_nonzero_volume() -> None:
    strategy, replay_input, _ = _wc01_input()
    buckets = list(replay_input.dataset.buckets)
    buckets[0] = replace(buckets[0], status="COMPLETE_EMPTY", price=None)
    replay_input = replace(replay_input, dataset=replace(replay_input.dataset, buckets=tuple(buckets)))

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "INVALID_REPLAY_BUCKET"
    else:
        raise AssertionError("a complete empty bucket must prove zero quote volume")


def test_spot_replay_rejects_a_binary_float_observation_before_evaluation() -> None:
    strategy, replay_input, _ = _wc01_input()
    buckets = list(replay_input.dataset.buckets)
    buckets[0] = replace(buckets[0], price=replace(buckets[0].price, value=7.5))
    replay_input = replace(replay_input, dataset=replace(replay_input.dataset, buckets=tuple(buckets)))

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "INVALID_REPLAY_NUMBER"
    else:
        raise AssertionError("binary floating-point observations are not canonical replay inputs")


def test_spot_replay_does_not_promote_non_fixture_data_to_qualified_evidence() -> None:
    strategy, replay_input, _ = _wc01_input()
    replay_input = replace(replay_input, dataset=replace(replay_input.dataset, evidence_class="REAL_MARKET"))

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "EVIDENCE_CLASS_UNSUPPORTED"
    else:
        raise AssertionError("the synthetic-only slice must not accept or qualify real market evidence")


def test_spot_replay_open_position_exit_takes_priority_over_entry_on_that_decision() -> None:
    strategy, replay_input, _ = _wc01_input()

    result = run_spot_replay(strategy, replay_input)

    assert any(event.get("kind") == "ORDER" and event.get("status") == "RESERVED"
               and event.get("side") == "SELL" and event.get("at") == _moment("2026-10-01T12:15:00Z")
               for event in result.events)
    assert not any(event.get("kind") == "ORDER" and event.get("side") == "BUY"
                   and event.get("at") == _moment("2026-10-01T12:15:00Z") for event in result.events)


def test_spot_replay_requires_the_saved_strategy_warmup_before_window_start() -> None:
    strategy, replay_input, _ = _wc01_input()
    strategy["entry"] = {"op": "gt", "args": [
        {"op": "lag", "buckets": 1, "value": {"op": "price"}},
        {"op": "constant", "value": "7", "unit": "PRICE"},
    ]}
    strategy["warmup_buckets"] = 1
    strategy = strategy_compiler.build_strategy(strategy["strategy_id"], {
        name: strategy[name] for name in record_contract.CREATE_STRATEGY_FIELDS if name != "restrictions"
    })

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "DATASET_COVERAGE_UNPROVEN"
    else:
        raise AssertionError("the replay window cannot start before its saved strategy warm-up")


def test_spot_replay_rejects_missing_trailing_scheduled_coverage() -> None:
    strategy, source, _ = _wc01_input()
    truncated_one = replace(source, dataset=replace(source.dataset, buckets=source.dataset.buckets[:-1]))
    truncated_two = replace(source, dataset=replace(source.dataset, buckets=source.dataset.buckets[:-2]))
    extended_window = replace(source, window_end=source.window_end + timedelta(minutes=5))
    valid_half_open = replace(source, window_end=source.window_end - timedelta(minutes=3))

    for incomplete in (truncated_one, truncated_two, extended_window):
        try:
            run_spot_replay(strategy, incomplete)
        except ValueError as error:
            assert getattr(error, "code") == "DATASET_COVERAGE_UNPROVEN"
        else:
            raise AssertionError("the declared half-open window needs every scheduled point before its end")

    valid_result = run_spot_replay(strategy, valid_half_open)
    assert valid_result.samples[-1]["at"] == source.dataset.buckets[-1].bucket_end


def test_wc05_reports_absolute_quote_drawdown_from_independent_samples() -> None:
    from edge_os_api.replay.simulator import calculate_quote_metrics

    values = tuple({"account_value_quote": value, "mark_reasons": ()} for value in (
        Decimal("1000"), Decimal("999.6"), Decimal("1049.6"), Decimal("1020")
    ))

    metrics = calculate_quote_metrics(values, Decimal("1000"), 0)

    assert metrics.values == {
        "gain_loss_quote": Decimal("20"),
        "completed_trade_pairs": 0,
        "largest_drawdown_quote": Decimal("29.6"),
    }
    assert metrics.statuses["gain_loss_quote"] == "AVAILABLE"
    assert metrics.statuses["largest_drawdown_quote"] == "AVAILABLE"


def test_wc13_replays_a_preexisting_single_position_with_current_bucket_settlement() -> None:
    case = _reference_case("WC-13")
    strategy, replay_input, _ = _wc01_input()
    strategy["entry"] = {"op": "gt", "args": [
        {"op": "price"}, {"op": "constant", "value": "5", "unit": "PRICE"}
    ]}
    strategy["exit"] = copy.deepcopy(strategy["entry"])
    strategy["sizing"]["amount"] = "50"
    strategy["risk_limits"]["max_quote_notional"] = "50"
    strategy["cost_assumptions"] = {"fee_rate": "0.001", "slippage_rate": "0", "source_ref": "synthetic-wc13"}
    strategy = strategy_compiler.build_strategy(strategy["strategy_id"], {
        name: strategy[name] for name in record_contract.CREATE_STRATEGY_FIELDS if name != "restrictions"
    })
    market_id = strategy_compiler.market_binding_id(strategy["market"])
    values = ("8", "11", "4")
    buckets = []
    for index, value in enumerate(values):
        moment = _moment("2026-10-01T12:00:00Z") + timedelta(minutes=5 * index)
        prior = replay_input.dataset.buckets[index]
        buckets.append(replace(
            prior,
            bucket_end=moment,
            price=strategy_compiler.Observation(value, moment, market_id, True, moment),
            quote_volume=replace(prior.quote_volume, bucket_end=moment, market_binding_id=market_id, available_at=moment),
        ))
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor.update({
        "strategy_revision": replay_input.strategy_revision_id,
        "run_configuration_id": replay_input.run_configuration_id,
        "market_binding_id": market_id,
    })
    replay_input = replace(
        replay_input,
        dataset=replace(replay_input.dataset, market_binding_id=market_id, buckets=tuple(buckets)),
        essential_evidence=descriptor,
        window_start=_moment("2026-10-01T12:00:00Z"),
        window_end=_moment("2026-10-01T12:15:00Z"),
        initial_cash_quote=case["initial_cash_quote"],
        initial_base_amount=case["initial_base"],
        initial_basis_quote=case["initial_basis_quote"],
    )

    result = run_spot_replay(strategy, replay_input)

    assert [sample["account_value_quote"] for sample in result.samples] == [
        Decimal("80"), Decimal(case["post_sell_cash_quote"]), Decimal(case["ending_account_value_quote"])
    ]
    assert [sample["cash_quote"] for sample in result.samples] == [
        Decimal(case["initial_cash_quote"]), Decimal(case["post_sell_cash_quote"]), Decimal(case["ending_cash_quote"])
    ]
    assert [sample["base_amount"] for sample in result.samples] == [
        Decimal(case["initial_base"]), Decimal("0"), Decimal(case["ending_base"])
    ]
    assert result.trades[0]["gain_loss_quote"] == Decimal(case["realized_quote"])
    assert result.trades[0]["entry_origin"] == "PREEXISTING_AT_RUN_START"
    assert result.trades[0]["entry_at"] is None
    assert result.metrics["gain_loss_quote"] == Decimal(case["gain_loss_quote"])
    assert result.metrics["completed_trade_pairs"] == case["completed_trade_pairs"]
    assert result.metrics["largest_drawdown_quote"] == Decimal(case["largest_drawdown_quote"])


def test_wc10_replays_the_named_full_window_tuple_repeatably() -> None:
    case = _reference_case("WC-10")
    strategy, replay_input, _ = _wc01_input()
    strategy = _rebuild_strategy(strategy, strategy_id=case["strategy_revision_id"])
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor.update({
        "strategy_revision": case["strategy_revision_id"],
        "run_configuration_id": case["run_configuration_id"],
        "dataset_revision": case["dataset_revision_id"],
    })
    replay_input = replace(
        replay_input,
        strategy_revision_id=case["strategy_revision_id"],
        run_configuration_id=case["run_configuration_id"],
        dataset=replace(replay_input.dataset, revision_id=case["dataset_revision_id"]),
        essential_evidence=descriptor,
    )

    first = run_spot_replay(strategy, replay_input)
    second = run_spot_replay(strategy, replay_input)

    assert case["profile_version"] == "p12.spot-replay/1"
    assert first.repeatability_id == second.repeatability_id
    assert first.samples == second.samples
    assert first.events == second.events
    assert [sample["cash_quote"] for sample in first.samples] == [Decimal(value) for value in case["sample_cash_quote"]]
    assert [sample["base_amount"] for sample in first.samples] == [Decimal(value) for value in case["sample_base"]]
    assert [sample["account_value_quote"] for sample in first.samples] == [
        Decimal(value) for value in case["sample_account_value_quote"]
    ]
    order_statuses = [event["status"] for event in first.events if event["kind"] == "ORDER"
                      and event["status"] in {"BUY_FILLED", "SELL_FILLED", "NO_NEXT_BUCKET"}]
    assert order_statuses == case["orders"]
    assert first.metrics["gain_loss_quote"] == Decimal(case["gain_loss_quote"])
    assert first.metrics["completed_trade_pairs"] == case["completed_trade_pairs"]
    assert first.metrics["largest_drawdown_quote"] == Decimal(case["largest_drawdown_quote"])


def test_wc11_preserves_valid_boolean_invalidation_then_rejects_p12_subset() -> None:
    case = _reference_case("WC-11")
    strategy, replay_input, _ = _wc01_input()
    strategy = _rebuild_strategy(
        strategy,
        invalidation={"op": "gt", "args": [
            {"op": "price"}, {"op": "constant", "value": "3", "unit": "PRICE"}
        ]},
        entry={"op": "gt", "args": [
            {"op": "price"}, {"op": "constant", "value": "100", "unit": "PRICE"}
        ]},
        exit={"op": "lt", "args": [
            {"op": "price"}, {"op": "constant", "value": "0", "unit": "PRICE"}
        ]},
        sizing={"amount": "100"},
        risk_limits={"max_quote_notional": "100"},
    )
    start = _moment("2026-10-01T12:00:00Z")
    replay_input = _scheduled_run(
        strategy, replay_input, ("4",), schedule_start=start, window_start=start,
        window_end=start + timedelta(minutes=5),
    )
    bucket = replay_input.dataset.buckets[0]
    context = strategy_compiler.EvaluationContext((bucket.price,), (bucket.quote_volume,), (start,),
                                   replay_input.dataset.market_binding_id, start, 0)
    invalidation = strategy_compiler.evaluate_expression(strategy["invalidation"], strategy["market"], context)

    assert invalidation.value == case["invalidation_value"]
    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == case["preflight_status"]
    else:
        raise AssertionError("valid P06 Boolean invalidation remains unsupported by P12/1")


def test_wc12_matches_ordered_decimal50_fees_slippage_and_rounding_residual() -> None:
    case = _reference_case("WC-12")
    strategy, replay_input, _ = _wc01_input()
    strategy = _rebuild_strategy(
        strategy,
        cost_assumptions={"fee_rate": case["fee_rate"], "slippage_rate": case["slippage_rate"],
                          "source_ref": "synthetic-cost-source"},
    )
    start = _moment("2026-10-01T12:00:00Z")
    replay_input = _scheduled_run(
        strategy, replay_input, ("8", "8", "9", "10"), schedule_start=start,
        window_start=start, window_end=start + timedelta(minutes=20),
    )

    result = run_spot_replay(strategy, replay_input)
    buy = next(event for event in result.events if event.get("status") == "BUY_FILLED")
    sell = next(event for event in result.events if event.get("status") == "SELL_FILLED")
    trade = result.trades[0]

    assert strategy["cost_assumptions"]["fee_rate"] == case["fee_rate"]
    assert strategy["cost_assumptions"]["slippage_rate"] == case["slippage_rate"]
    assert str(buy["fill_price"]) == case["buy_fill"]
    assert str(buy["base_amount"]) == case["base_amount"]
    assert str(buy["fee_quote"]) == case["buy_fee_quote"]
    assert str(buy["cash_quote"]) == case["cash_after_buy_quote"]
    assert str(trade["entry_basis_quote"]) == case["buy_basis_quote"]
    assert str(sell["fill_price"]) == case["sell_fill"]
    assert str(sell["gross_quote"]) == case["gross_quote"]
    assert str(sell["fee_quote"]) == case["sell_fee_quote"]
    with localcontext(strategy_compiler.NUMERIC):
        net = sell["gross_quote"] - sell["fee_quote"]
        residual = trade["gain_loss_quote"] - result.metrics["gain_loss_quote"]
    assert str(net) == case["net_quote"]
    assert str(result.samples[-1]["cash_quote"]) == case["final_cash_quote"]
    assert str(trade["gain_loss_quote"]) == case["realized_quote"]
    assert str(result.metrics["gain_loss_quote"]) == case["final_minus_initial_quote"]
    assert str(residual) == case["rounding_residual_quote"]
    assert Decimal(case["fee_basis_points_display_only"]) == Decimal(case["fee_rate"]) * Decimal("10000")
    assert Decimal(case["slippage_basis_points_display_only"]) == Decimal(case["slippage_rate"]) * Decimal("10000")


def test_wc14_resolves_moving_offsets_and_keeps_p06_result_separate_from_eligibility() -> None:
    case = _reference_case("WC-14")
    strategy, replay_input, _ = _wc01_input()
    strategy = _rebuild_strategy(
        strategy,
        data_inputs=["price"],
        entry={"op": "gt", "args": [
            {"op": "price_return", "lookback_buckets": 2},
            {"op": "constant", "value": "0.05", "unit": "DIMENSIONLESS"},
        ]},
        exit={"op": "lt", "args": [
            {"op": "price"}, {"op": "constant", "value": "90", "unit": "PRICE"}
        ]},
        invalidation={"state": "NOT_REQUESTED", "source_ref": "synthetic-wc14"},
    )
    start = _moment("2026-10-01T12:00:00Z")
    replay_input = _scheduled_run(
        strategy, replay_input, tuple(case["prices"]), schedule_start=start,
        window_start=start + timedelta(minutes=10), window_end=start + timedelta(minutes=20),
    )
    descriptor = copy.deepcopy(replay_input.essential_evidence)
    descriptor["fields"]["entry"]["essential_dependencies"] = [
        {"series": "price", "offset_buckets": offset} for offset in case["entry_offsets"]
    ]
    descriptor["fields"]["exit"]["essential_dependencies"] = []
    replay_input = replace(replay_input, essential_evidence=descriptor)

    result = run_spot_replay(strategy, replay_input)
    decisions = [event for event in result.events if event["kind"] == "DECISION"]

    assert len(decisions) == 2
    assert decisions[0]["entry"]["value"] == strategy_compiler.Truth.TRUE
    assert list(decisions[0]["entry"]["reasons"]) == case["position_2_reasons"]
    assert decisions[0]["entry"]["eligible"] is True
    assert decisions[1]["entry"]["value"] == strategy_compiler.Truth.UNKNOWN
    assert list(decisions[1]["entry"]["reasons"]) == case["position_3_reasons"]
    assert decisions[1]["entry"]["eligible"] is False
    assert decisions[1]["entry"]["eligibility_status"] == case["position_3_eligibility"]
    assert decisions[1]["exit"]["eligible"] is True
    assert decisions[1]["exit"]["value"] == strategy_compiler.Truth.FALSE


def test_wc02_reconciles_shared_reservation_literals_without_runtime_portfolio_support() -> None:
    case = _reference_case("WC-02")
    cash = Decimal(case["initial_cash_quote"])
    quote_size = Decimal(case["quote_notional"])
    fee_rate = Decimal(case["fee_rate"])
    reserved = quote_size + quote_size * fee_rate
    free_cash = cash - reserved
    base = quote_size / Decimal(case["fill_price"])
    account_value = free_cash + base * Decimal(case["fill_price"])

    assert reserved == Decimal(case["reserved_quote"])
    assert free_cash == Decimal(case["free_cash_after_first_reservation"])
    assert base == Decimal(case["base_amount"])
    assert quote_size * fee_rate == Decimal(case["fee_quote"])
    assert account_value == Decimal(case["terminal_account_value_quote"])
    assert case["second_request"] == "INSUFFICIENT_CASH"
    assert case["status"] == "ACCOUNTING_CONFORMANCE_ONLY"
    assert case["runtime_support"] == "UNSUPPORTED_SHARED_POSITION"


def test_wc03_reconciles_partial_exit_literals_but_rejects_runtime_partial_exit() -> None:
    case = _reference_case("WC-03")
    bought_base = Decimal("400") / Decimal("8")
    buy_basis = Decimal(case["buy_basis_quote"])
    unit_basis = buy_basis / bought_base
    sold_base = Decimal(case["partial_base_sold"])
    sale_gross = sold_base * Decimal("10")
    sale_fee = sale_gross * Decimal("0.001")
    realized = sale_gross - sale_fee - sold_base * unit_basis
    remaining = bought_base - sold_base
    remaining_basis = remaining * unit_basis
    ending_cash = Decimal("599.6") + sale_gross - sale_fee
    ending_value = ending_cash + remaining * Decimal("9")

    assert unit_basis == Decimal(case["weighted_basis_quote_per_base"])
    assert sale_gross == Decimal(case["partial_sale_gross_quote"])
    assert sale_fee == Decimal(case["partial_exit_fee_quote"])
    assert realized == Decimal(case["partial_sale_realized_quote"])
    assert remaining == Decimal(case["remaining_base"])
    assert remaining_basis == Decimal(case["remaining_basis_quote"])
    assert ending_cash == Decimal(case["ending_cash_quote"])
    assert ending_value == Decimal(case["ending_account_value_quote"])
    assert case["status"] == "ACCOUNTING_CONFORMANCE_ONLY"

    strategy, replay_input, _ = _wc01_input()
    strategy["partial_exits"] = True
    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == case["runtime_support"]
    else:
        raise AssertionError("WC-03 arithmetic must not enable production partial exits")


def test_wc04_midrun_missing_mark_preserves_terminal_gain_but_not_full_drawdown() -> None:
    case = _reference_case("WC-04")
    strategy, replay_input, _ = _wc01_input()
    replay_input = _scheduled_run(
        strategy, replay_input, ("8", "8", None, "10"),
        schedule_start=_moment("2026-10-01T12:05:00Z"),
        window_start=_moment("2026-10-01T12:05:00Z"),
        window_end=_moment("2026-10-01T12:25:00Z"),
    )

    result = run_spot_replay(strategy, replay_input)

    assert result.samples[2]["cash_quote"] == Decimal(case["mid_mark_expected_cash_quote"])
    assert result.samples[2]["base_amount"] == Decimal(case["mid_mark_expected_base"])
    assert result.samples[2]["account_value_quote"] is None
    assert result.samples[2]["mark_reasons"] == ("EMPTY_BUCKET_NO_CLOSE",)
    assert result.samples[-1]["account_value_quote"] == Decimal(case["mid_mark_terminal_value_quote"])
    assert result.metrics["gain_loss_quote"] == Decimal(case["mid_mark_gain_loss_quote"])
    assert result.metric_statuses["gain_loss_quote"] == case["mid_mark_gain_loss_status"]
    assert result.metric_statuses["largest_drawdown_quote"] == case["mid_mark_drawdown_status"]


def test_wc04_missing_terminal_mark_keeps_cash_and_inventory_and_invalidates_metrics() -> None:
    case = _reference_case("WC-04")
    strategy, replay_input, _ = _wc01_input()
    replay_input = _scheduled_run(
        strategy, replay_input, ("8", "8", "9", None),
        schedule_start=_moment("2026-10-01T12:05:00Z"),
        window_start=_moment("2026-10-01T12:05:00Z"),
        window_end=_moment("2026-10-01T12:25:00Z"),
    )

    result = run_spot_replay(strategy, replay_input)

    assert result.samples[-1]["cash_quote"] == Decimal("599.6")
    assert result.samples[-1]["base_amount"] == Decimal("50")
    assert result.samples[-1]["account_value_quote"] is None
    assert result.metric_statuses["gain_loss_quote"] == case["terminal_mark_gain_loss_status"]
    assert result.metric_statuses["largest_drawdown_quote"] == "UNAVAILABLE"
    assert result.metric_reasons["gain_loss_quote"] == ("EMPTY_BUCKET_NO_CLOSE",)


def test_wc04_missing_saved_cost_source_rejects_before_any_action() -> None:
    case = _reference_case("WC-04")
    strategy, replay_input, _ = _wc01_input()
    strategy["cost_assumptions"]["source_ref"] = ""

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == case["missing_cost_status"]
    else:
        raise AssertionError("missing saved cost provenance must not default to zero costs")


def test_wc07_preserves_late_future_empty_and_incomplete_input_reasons() -> None:
    case = _reference_case("WC-07")
    strategy, replay_input, _ = _wc01_input()
    start = _moment("2026-10-01T12:00:00Z")
    late_run = _scheduled_run(
        strategy, replay_input, ("110",), schedule_start=start, window_start=start,
        window_end=start + timedelta(minutes=5), availability=(start + timedelta(minutes=2),),
    )
    late_context = strategy_compiler.EvaluationContext(
        (late_run.dataset.buckets[0].price,), (late_run.dataset.buckets[0].quote_volume,),
        (start,), late_run.dataset.market_binding_id, start, 0,
    )
    late = strategy_compiler.evaluate_expression({"op": "price"}, strategy["market"], late_context)
    assert late.state == case["late_value"]
    assert list(late.reasons) == case["late_reasons"]

    misaligned = replace(late_run.dataset.buckets[0].price, bucket_end=start + timedelta(minutes=5))
    future_context = replace(late_context, prices=(misaligned,))
    future = strategy_compiler.evaluate_expression({"op": "price"}, strategy["market"], future_context)
    assert future.state == case["future_schedule_value"]
    assert list(future.reasons) == case["future_schedule_reasons"]

    empty_run = _scheduled_run(
        strategy, replay_input, (None,), schedule_start=start, window_start=start,
        window_end=start + timedelta(minutes=5),
    )
    empty_bucket = empty_run.dataset.buckets[0]
    empty_context = strategy_compiler.EvaluationContext((empty_bucket.price,), (empty_bucket.quote_volume,),
                                         (start,), empty_run.dataset.market_binding_id, start, 0)
    empty_price = strategy_compiler.evaluate_expression({"op": "price"}, strategy["market"], empty_context)
    empty_volume = strategy_compiler.evaluate_expression({"op": "quote_volume"}, strategy["market"], empty_context)
    assert empty_price.state == case["empty_price_value"]
    assert list(empty_price.reasons) == case["empty_price_reasons"]
    assert str(empty_volume.value) == case["empty_quote_volume_value"]

    for status, expected_reason in (
        ("INCOMPLETE", case["incomplete_reason"]),
        ("UNQUALIFIED", "UNQUALIFIED_RECORDS"),
    ):
        scheduled_gap = _scheduled_run(
            strategy, replay_input, ("110",), schedule_start=start, window_start=start,
            window_end=start + timedelta(minutes=5), statuses=(status,),
        )
        result = run_spot_replay(strategy, scheduled_gap)
        decision = next(event for event in result.events if event["kind"] == "DECISION")
        assert decision["entry"]["eligibility_reasons"] == (expected_reason,)
        assert not any(event.get("side") == "BUY" and event.get("status") == "RESERVED"
                       for event in result.events)


def test_wc08_late_fill_releases_once_and_does_not_retry_or_mark() -> None:
    case = _reference_case("WC-08")
    strategy, replay_input, _ = _wc01_input()
    strategy = _rebuild_strategy(
        strategy,
        entry={"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "4", "unit": "PRICE"}]},
        sizing={"unit": strategy["sizing"]["unit"], "amount": case["quote_notional"]},
        risk_limits={"max_quote_notional": case["quote_notional"], "max_open_positions": 1},
    )
    start = _moment("2026-10-01T12:00:00Z")
    replay_input = _scheduled_run(
        strategy, replay_input, ("5", "5"), schedule_start=start, window_start=start,
        window_end=start + timedelta(minutes=10),
        availability=(start, _moment(case["available_at"])),
    )

    result = run_spot_replay(strategy, replay_input)

    fills = [event for event in result.events if event.get("status") == case["fill_status"]]
    assert len(fills) == 1
    assert fills[0]["reasons"] == (case["fill_reason"],)
    assert fills[0]["reservation_released_quote"] == Decimal(case["released_quote"])
    assert result.samples[-1]["cash_quote"] == Decimal(case["ending_cash_quote"])
    assert result.samples[-1]["base_amount"] == Decimal(case["ending_base"])
    assert result.samples[-1]["account_value_quote"] is None
    assert result.metric_statuses["gain_loss_quote"] == case["gain_loss_status"]
    assert result.metric_statuses["largest_drawdown_quote"] == case["drawdown_status"]


def test_wc09_exclusive_end_rejects_order_before_reservation() -> None:
    case = _reference_case("WC-09")
    strategy, replay_input, _ = _wc01_input()
    strategy = _rebuild_strategy(
        strategy,
        entry={"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "4", "unit": "PRICE"}]},
        exit={"op": "lt", "args": [{"op": "price"}, {"op": "constant", "value": "0", "unit": "PRICE"}]},
        sizing={"unit": strategy["sizing"]["unit"], "amount": "100"},
        risk_limits={"max_quote_notional": "100", "max_open_positions": 1},
    )
    start = _moment(case["window_start"])
    replay_input = _scheduled_run(
        strategy, replay_input, ("4", "5"), schedule_start=start, window_start=start,
        window_end=_moment(case["window_end"]),
    )

    result = run_spot_replay(strategy, replay_input)

    terminal = result.samples[-1]
    assert terminal["at"] == _moment(case["terminal_at"])
    assert terminal["cash_quote"] == Decimal(case["terminal_cash_quote"])
    assert terminal["base_amount"] == Decimal(case["terminal_base"])
    assert terminal["account_value_quote"] == Decimal(case["terminal_account_value_quote"])
    terminal_orders = [event for event in result.events if event.get("at") == terminal["at"] and event["kind"] == "ORDER"]
    assert [(event["status"], event.get("reserved_quote", Decimal("0"))) for event in terminal_orders] == [
        (case["order_status"], Decimal(case["reservation_quote"]))
    ]
    assert not case["exclusive_end_is_sample"]
