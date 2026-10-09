from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from edge_os_api import p02, p06
from edge_os_api.spot_replay import ReplayBucket, ReplayDataset, ReplayInput, run_spot_replay

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "spot_replay" / "wc01.json"


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _wc01_input() -> tuple[dict[str, Any], ReplayInput, dict[str, Any]]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    strategy = copy.deepcopy(p02.FIXTURE_STRATEGY)
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
    strategy = p06.build_strategy(
        "synthetic-strategy-wc01-v1",
        {name: strategy[name] for name in p02.CREATE_STRATEGY_FIELDS if name != "restrictions"},
    )
    p06.validate_strategy(strategy)

    market_id = p06.market_binding_id(strategy["market"])
    fixture["essential_evidence"]["market_binding_id"] = market_id
    buckets = tuple(
        ReplayBucket(
            bucket_end=_moment(bucket["bucket_end"]),
            status=bucket["status"],
            price=p06.Observation(
                value=bucket["price"],
                bucket_end=_moment(bucket["bucket_end"]),
                market_binding_id=market_id,
                qualified=bucket["status"] == "COMPLETE_OCCUPIED",
                available_at=_moment(bucket["available_at"]) if bucket["available_at"] else None,
                reasons=tuple(bucket.get("reasons", ())),
            ),
            quote_volume=p06.Observation(
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


def test_spot_replay_releases_a_late_fill_reservation_once() -> None:
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
    assert result.metrics["gain_loss_quote"] is None
    assert result.metric_statuses["gain_loss_quote"] == "UNAVAILABLE"
    assert result.metric_reasons["gain_loss_quote"] == ("LATE_INPUT",)


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
    assert decision["entry"]["value"] == p06.Truth.TRUE
    assert decision["entry"]["reasons"] == ("MISSING_QUOTE_VOLUME", "MISSING_QUOTE_VOLUME:0")
    assert decision["entry"]["eligible"] is False
    assert decision["entry"]["eligibility_status"] == "ESSENTIAL_EVIDENCE_UNAVAILABLE"
    assert not any(event.get("at") == _moment("2026-10-01T12:05:00Z")
                    and event.get("status") == "RESERVED" and event.get("side") == "BUY"
                    for event in result.events)


def test_spot_replay_preserves_p06_market_mismatch_and_fails_essential_binding() -> None:
    strategy, replay_input, _ = _wc01_input()
    buckets = list(replay_input.dataset.buckets)
    buckets[0] = replace(buckets[0], price=replace(buckets[0].price, market_binding_id="other-market"))
    replay_input = replace(replay_input, dataset=replace(replay_input.dataset, buckets=tuple(buckets)))

    result = run_spot_replay(strategy, replay_input)

    decision = next(event for event in result.events if event.get("kind") == "DECISION")
    assert decision["entry"]["value"] == p06.Truth.UNKNOWN
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
    assert decision["entry"]["value"] == p06.Truth.UNKNOWN
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
    strategy = p06.build_strategy(strategy["strategy_id"], {
        name: strategy[name] for name in p02.CREATE_STRATEGY_FIELDS if name != "restrictions"
    })

    try:
        run_spot_replay(strategy, replay_input)
    except ValueError as error:
        assert getattr(error, "code") == "DATASET_COVERAGE_UNPROVEN"
    else:
        raise AssertionError("the replay window cannot start before its saved strategy warm-up")
