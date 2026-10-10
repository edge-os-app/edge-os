"""Public deterministic effect-comparison behavior against independent fixtures."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research.effect_comparison import compare_effects, evaluate_p06_bindings, reference_trade

FIXTURES = Path(__file__).parent / "fixtures" / "effect_comparison"


def test_reference_trade_uses_half_open_window_and_chain_order() -> None:
    dataset = json.loads((FIXTURES / "window_boundaries.json").read_text())
    decision = datetime(2026, 1, 1, tzinfo=timezone.utc)

    start = reference_trade(dataset["trades"], decision, 0)
    end = reference_trade(dataset["trades"], decision, 30 * 60)

    assert start["event_id"] == "start-first"
    assert end["event_id"] == "end-first"
    assert start["price"] == "100"
    assert end["price"] == "120"
    assert (datetime.fromisoformat(end["event_time"].replace("Z", "+00:00")) -
            datetime.fromisoformat(start["event_time"].replace("Z", "+00:00"))).total_seconds() == 29 * 60 + 45


def test_synthetic_fixture_chain_order_is_monotonic_and_references_keep_authored_arithmetic() -> None:
    fixture = json.loads((FIXTURES / "synthetic_effect_comparison_v1.json").read_text())
    trades = fixture["trades"]
    ordered = sorted(trades, key=lambda row: (row["block_number"], row["transaction_index"], row["log_index"]))
    instants = [datetime.fromisoformat(row["event_time"].replace("Z", "+00:00")) for row in ordered]
    assert all(left < right for left, right in zip(instants, instants[1:]))
    assert [row["event_id"] for row in ordered] == [
        "fixture-start-0", "fixture-start-1", "fixture-end-0", "fixture-end-1"]
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = reference_trade(trades, base, 0)
    end = reference_trade(trades, base, 15 * 60)
    second_first = reference_trade(trades, base + timedelta(minutes=5), 0)
    second_end = reference_trade(trades, base + timedelta(minutes=5), 15 * 60)
    assert (first["event_id"], end["event_id"], second_first["event_id"], second_end["event_id"]) == (
        "fixture-start-0", "fixture-end-0", "fixture-start-1", "fixture-end-1")
    assert [format(Decimal(end["price"]) / Decimal(first["price"]) - Decimal(1), "f"),
            format(Decimal(second_end["price"]) / Decimal(second_first["price"]) - Decimal(1), "f")] == [
        "-0.1", "0.1"]


def test_comparison_keeps_unknown_future_and_missing_opportunities_out_of_controls() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:10:00Z", "interval_seconds": 120}
    evaluations = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
                    "horizon": {"value": 1, "unit": "MINUTES"}}]
    decisions = [
        {"decision_id": "d0", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:00:00Z",
         "available_at": "2026-01-01T00:00:00Z", "qualified": True,
         "essential_evidence_qualified": True, "price_state": "TRUE", "volume_state": "TRUE"},
        {"decision_id": "d2", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:02:00Z",
         "available_at": "2026-01-01T00:02:00Z", "qualified": True,
         "essential_evidence_qualified": True, "price_state": "FALSE", "volume_state": "TRUE"},
        {"decision_id": "d4", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:04:00Z",
         "available_at": "2026-01-01T00:05:00Z", "qualified": True,
         "essential_evidence_qualified": True, "price_state": "TRUE", "volume_state": "FALSE"},
        {"decision_id": "d6", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:06:00Z",
         "available_at": "2026-01-01T00:06:00Z", "qualified": True,
         "essential_evidence_qualified": False, "price_state": "FALSE", "volume_state": "FALSE"},
        {"decision_id": "d8", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:08:00Z",
         "available_at": "2026-01-01T00:08:00Z", "qualified": True,
         "essential_evidence_qualified": True, "price_state": "TRUE", "volume_state": "FALSE"},
    ]
    trades = []
    responses = {0: ("100", "110"), 2: ("100", "90"), 4: ("100", "120"),
                 6: ("100", "50"), 8: ("100", "105")}
    for minute, (first_price, last_price) in responses.items():
        for seconds, suffix, price in ((10, "start", first_price), (70, "end", last_price)):
            event_time = start.replace(minute=minute, second=0).timestamp() + seconds
            instant = datetime.fromtimestamp(event_time, timezone.utc)
            trades.append({"event_id": f"d{minute}-{suffix}", "event_time": instant.isoformat().replace("+00:00", "Z"),
                           "available_at": (instant.replace(second=instant.second + 1)).isoformat().replace("+00:00", "Z"),
                           "qualified": True, "block_number": minute * 10 + seconds,
                           "transaction_index": 0, "log_index": 0, "price": price})

    result = compare_effects(schedule=schedule, evaluation_plan=evaluations, decisions=decisions,
                             trades=trades, incremental_volume_declared=True)

    rows = result["variants"][0]["opportunities"]
    assert len(rows) == 5
    assert [row["eligibility_group"] for row in rows] == ["TRIGGERED", "CONTROL", "EXCLUDED", "EXCLUDED", "CONTROL"]
    assert "SIGNAL_NOT_AVAILABLE_AT_DECISION" in rows[2]["reasons"]
    assert "MISSING_ESSENTIAL_EVIDENCE" in rows[3]["reasons"]
    assert rows[4]["response"] == "0.05"
    stats = result["variants"][0]["general_comparison"]
    assert stats["triggered"]["opportunity_count"] == 1
    assert stats["control"]["opportunity_count"] == 2
    assert stats["triggered_minus_control_mean"] == "0.125"
    incremental = result["variants"][0]["incremental_volume_comparison"]
    assert incremental["triggered"]["opportunity_count"] == 1
    assert incremental["control"]["opportunity_count"] == 1
    assert incremental["triggered_minus_control_mean"] == "0.05"
    assert result["status"] == result["statistical_status"] == "UNRESOLVED"


def test_comparison_rejects_misaligned_decisions_and_does_not_infer_volume_contrast() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:02:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    decision = {"decision_id": "d0", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:00:00Z",
                "available_at": "2026-01-01T00:00:00Z", "qualified": True,
                "essential_evidence_qualified": True, "price_state": "TRUE", "volume_state": "FALSE"}
    import pytest
    with pytest.raises(ValueError, match="undeclared evaluation"):
        compare_effects(schedule=schedule, evaluation_plan=plan,
                        decisions=[{**decision, "evaluation_id": "undeclared"}], trades=[],
                        incremental_volume_declared=False)
    result = compare_effects(schedule=schedule, evaluation_plan=plan, decisions=[decision], trades=[],
                             incremental_volume_declared=False)
    assert result["variants"][0]["incremental_volume_comparison"] == {"status": "NOT_DECLARED"}


def test_explicit_p06_bindings_run_on_five_minute_features_under_independent_clock() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:03:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 15, "unit": "MINUTES"}}]
    price = {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "99", "unit": "PRICE"}]}
    quote_unit = f"QUOTE:{record_contract.FIXTURE_STRATEGY['market']['research_binding']['quote_asset']}"
    volume = {"op": "gt", "args": [{"op": "quote_volume"}, {
        "op": "constant", "value": "4", "unit": quote_unit}]}
    features = [{"bucket_end": "2026-01-01T00:00:00Z",
                 "price": {"value": "100", "qualified": True, "available_at": "2026-01-01T00:00:00Z"},
                 "quote_volume": {"value": "5", "qualified": True, "available_at": "2026-01-01T00:02:00Z"}}]
    binding = {"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
               "price_expression": price, "volume_expression": volume,
               "essential_inputs": ["price", "quote_volume"]}

    rows = evaluate_p06_bindings(schedule=schedule, evaluation_plan=plan, bindings=[binding], feature_rows=features)

    assert len(rows) == 3
    assert [row["price_state"] for row in rows] == ["TRUE", "TRUE", "TRUE"]
    assert [row["volume_state"] for row in rows] == ["UNKNOWN", "UNKNOWN", "TRUE"]
    assert [row["essential_evidence_qualified"] for row in rows] == [False, False, True]
    assert all("FUTURE_INFORMATION:0" in row["reasons"] for row in rows[:2])
    assert rows[2]["available_at"] == "2026-01-01T00:02:00Z"


def test_empty_or_unqualified_reference_keeps_opportunity_and_exact_reason() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:01:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    decision = {"decision_id": "d0", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:00:00Z",
                "available_at": "2026-01-01T00:00:00Z", "qualified": True,
                "essential_evidence_qualified": True, "price_state": "TRUE", "volume_state": "TRUE"}
    # A trade exists in the end window, but the start window is empty. No widening or carry is allowed.
    trade = {"event_id": "end-only", "event_time": "2026-01-01T00:01:10Z",
             "qualified": True, "block_number": 1, "transaction_index": 0, "log_index": 0, "price": "110"}
    result = compare_effects(schedule=schedule, evaluation_plan=plan, decisions=[decision], trades=[trade],
                             incremental_volume_declared=False)
    row = result["variants"][0]["opportunities"][0]
    assert result["opportunity_count"] == 1
    assert result["missing_outcome_count"] == 1
    assert row["group"] == "MISSING_OUTCOME"
    assert row["response"] is None
    assert row["start_trade"] is None
    assert row["end_trade"]["event_id"] == "end-only"
    assert "MISSING_START_REFERENCE" in row["reasons"]
    unqualified = {**trade, "event_id": "unqualified-only", "event_time": "2026-01-01T00:00:20Z",
                   "qualified": False, "block_number": 0}
    assert reference_trade([unqualified], datetime(2026, 1, 1, tzinfo=timezone.utc), 0) is None


def test_positive_raw_responses_during_a_rise_can_have_unfavorable_trigger_control_contrast() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:08:00Z", "interval_seconds": 120}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    decisions = []
    trades = []
    rows = ((0, "TRUE", "100", "110"), (2, "TRUE", "100", "105"),
            (4, "FALSE", "100", "120"), (6, "FALSE", "100", "110"))
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for minute, price_state, start_price, end_price in rows:
        decision_time = base.replace(minute=minute)
        decisions.append({"decision_id": f"d{minute}", "evaluation_id": "eval-a",
                          "decision_time": decision_time.isoformat().replace("+00:00", "Z"),
                          "available_at": decision_time.isoformat().replace("+00:00", "Z"),
                          "qualified": True, "essential_evidence_qualified": True,
                          "price_state": price_state, "volume_state": "TRUE"})
        for offset, suffix, price in ((5, "start", start_price), (65, "end", end_price)):
            event_time = decision_time + timedelta(seconds=offset)
            trades.append({"event_id": f"d{minute}-{suffix}",
                           "event_time": event_time.isoformat().replace("+00:00", "Z"),
                           "qualified": True, "block_number": minute * 100 + offset,
                           "transaction_index": 0, "log_index": 0, "price": price})
    result = compare_effects(schedule=schedule, evaluation_plan=plan, decisions=decisions, trades=trades,
                             incremental_volume_declared=False)
    stats = result["variants"][0]["general_comparison"]
    assert [row["response"] for row in result["variants"][0]["opportunities"]] == ["0.1", "0.05", "0.2", "0.1"]
    assert stats["triggered"]["mean"] == "0.075"
    assert stats["control"]["mean"] == "0.15"
    assert stats["triggered_minus_control_mean"] == "-0.075"
    assert result["status"] == "UNRESOLVED"


def test_overlapping_windows_and_reused_trade_ids_are_retained_not_counted_as_independent() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:01:00Z", "interval_seconds": 30}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decisions = [{"decision_id": f"d{offset}", "evaluation_id": "eval-a",
                  "decision_time": (base + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z"),
                  "available_at": base.isoformat().replace("+00:00", "Z"), "qualified": True,
                  "essential_evidence_qualified": True, "price_state": "TRUE", "volume_state": "TRUE"}
                 for offset in (0, 30)]
    trades = [
        {"event_id": "shared-start", "event_time": "2026-01-01T00:00:40Z", "qualified": True,
         "block_number": 1, "transaction_index": 0, "log_index": 0, "price": "100"},
        {"event_id": "shared-end", "event_time": "2026-01-01T00:01:40Z", "qualified": True,
         "block_number": 2, "transaction_index": 0, "log_index": 0, "price": "110"},
    ]
    result = compare_effects(schedule=schedule, evaluation_plan=plan, decisions=decisions, trades=trades,
                             incremental_volume_declared=False)
    first, second = result["variants"][0]["opportunities"]
    assert result["shared_event_ids"] == ["shared-end", "shared-start"]
    assert first["shared_event_ids"] == second["shared_event_ids"] == ["shared-end", "shared-start"]
    assert first["overlapping_decision_ids"] == [second["decision_id"]]
    assert second["overlapping_decision_ids"] == [first["decision_id"]]
    assert result["opportunity_count"] == 2
    assert result["statistical_status"] == "UNRESOLVED"


def test_missing_signal_opportunities_keep_distinct_overlap_identities() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:01:00Z", "interval_seconds": 30}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    trades = [
        {"event_id": "shared-start", "event_time": "2026-01-01T00:00:40Z", "qualified": True,
         "block_number": 1, "transaction_index": 0, "log_index": 0, "price": "100"},
        {"event_id": "shared-end", "event_time": "2026-01-01T00:01:40Z", "qualified": True,
         "block_number": 2, "transaction_index": 0, "log_index": 0, "price": "110"},
    ]

    result = compare_effects(schedule=schedule, evaluation_plan=plan, decisions=[], trades=trades,
                             incremental_volume_declared=False)

    rows = result["variants"][0]["opportunities"]
    assert [row["decision_id"] for row in rows] == [None, None]
    assert [row["opportunity_id"] for row in rows] == [
        "eval-a:2026-01-01T00:00:00Z", "eval-a:2026-01-01T00:00:30Z"]
    assert rows[0]["overlapping_opportunity_ids"] == [rows[1]["opportunity_id"]]
    assert rows[1]["overlapping_opportunity_ids"] == [rows[0]["opportunity_id"]]


def test_multi_horizon_rows_keep_one_variant_identity_and_each_horizon() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:01:00Z", "interval_seconds": 60}
    plans = [
        {"evaluation_id": "eval-short", "trial_id": "trial-a", "variant_id": "same-rule",
         "horizon": {"value": 1, "unit": "MINUTES"}},
        {"evaluation_id": "eval-long", "trial_id": "trial-a", "variant_id": "same-rule",
         "horizon": {"value": 2, "unit": "MINUTES"}},
    ]
    decisions = [{"decision_id": f"d-{plan['evaluation_id']}", "evaluation_id": plan["evaluation_id"],
                  "decision_time": "2026-01-01T00:00:00Z", "available_at": "2026-01-01T00:00:00Z",
                  "qualified": True, "essential_evidence_qualified": True,
                  "price_state": "TRUE", "volume_state": "TRUE"} for plan in plans]

    result = compare_effects(schedule=schedule, evaluation_plan=plans, decisions=decisions,
                             trades=[], incremental_volume_declared=False)

    assert [(row["evaluation_id"], row["trial_id"], row["variant_id"], row["horizon"])
            for row in result["variants"]] == [
                ("eval-short", "trial-a", "same-rule", {"value": 1, "unit": "MINUTES"}),
                ("eval-long", "trial-a", "same-rule", {"value": 2, "unit": "MINUTES"}),
            ]


def test_missing_current_five_minute_bucket_is_not_carried_from_previous_bucket() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:05:00Z",
                "end": "2026-01-01T00:06:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    quote_unit = f"QUOTE:{record_contract.FIXTURE_STRATEGY['market']['research_binding']['quote_asset']}"
    binding = {"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
               "price_expression": {"op": "gt", "args": [{"op": "price"},
                   {"op": "constant", "value": "99", "unit": "PRICE"}]},
               "volume_expression": {"op": "gt", "args": [{"op": "quote_volume"},
                   {"op": "constant", "value": "4", "unit": quote_unit}]},
               "essential_inputs": ["price", "quote_volume"]}
    features = [{"bucket_end": "2026-01-01T00:00:00Z",
                 "price": {"value": "100", "qualified": True, "available_at": "2026-01-01T00:00:00Z"},
                 "quote_volume": {"value": "5", "qualified": True, "available_at": "2026-01-01T00:00:00Z"}}]

    result = evaluate_p06_bindings(schedule=schedule, evaluation_plan=plan, bindings=[binding], feature_rows=features)

    assert result[0]["decision_time"] == "2026-01-01T00:05:00Z"
    assert result[0]["price_state"] == result[0]["volume_state"] == "UNKNOWN"
    assert result[0]["qualified"] is False
    assert "MISSING_POSITION:1" in result[0]["reasons"]


def test_missing_historical_dependency_under_true_or_is_not_a_qualified_signal() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:05:00Z",
                "end": "2026-01-01T00:06:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    quote_unit = f"QUOTE:{record_contract.FIXTURE_STRATEGY['market']['research_binding']['quote_asset']}"
    price_expr = {"op": "or", "args": [
        {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "99", "unit": "PRICE"}]},
        {"op": "gt", "args": [{"op": "lag", "value": {"op": "price"}, "buckets": 1},
                {"op": "constant", "value": "99", "unit": "PRICE"}]},
    ]}
    binding = {"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
               "price_expression": price_expr,
               "volume_expression": {"op": "gt", "args": [{"op": "quote_volume"},
                   {"op": "constant", "value": "4", "unit": quote_unit}]},
               "essential_inputs": ["price", "quote_volume"]}
    features = [{"bucket_end": "2026-01-01T00:05:00Z",
                 "price": {"value": "100", "qualified": True, "available_at": "2026-01-01T00:05:00Z"},
                 "quote_volume": {"value": "5", "qualified": True, "available_at": "2026-01-01T00:05:00Z"}}]

    result = evaluate_p06_bindings(schedule=schedule, evaluation_plan=plan, bindings=[binding], feature_rows=features)

    assert result[0]["price_state"] == "TRUE"
    assert result[0]["qualified"] is False
    assert any(item.get("dependency_position") == 0 and item.get("qualified") is False
               for item in result[0]["input_evidence"])


def test_price_return_middle_gap_is_diagnostic_not_a_required_dependency() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:10:00Z",
                "end": "2026-01-01T00:11:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    quote_unit = f"QUOTE:{record_contract.FIXTURE_STRATEGY['market']['research_binding']['quote_asset']}"
    comparison = {"op": "gt", "args": [
        {"op": "price_return", "lookback_buckets": 2},
        {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"},
    ]}
    binding = {"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
               "price_expression": comparison,
               "volume_expression": {"op": "gt", "args": [{"op": "quote_volume"},
                   {"op": "constant", "value": "4", "unit": quote_unit}]},
               "essential_inputs": ["price", "quote_volume"]}
    features = [
        {"bucket_end": "2026-01-01T00:00:00Z", "price": {"value": "100", "qualified": True}},
        {"bucket_end": "2026-01-01T00:10:00Z", "price": {"value": "110", "qualified": True},
         "quote_volume": {"value": "5", "qualified": True}},
    ]

    result = evaluate_p06_bindings(schedule=schedule, evaluation_plan=plan, bindings=[binding], feature_rows=features)

    row = result[0]
    assert row["price_state"] == "TRUE"
    assert row["qualified"] is True
    assert "MISSING_POSITION:1" in row["reasons"]
    gap = next(item for item in row["input_evidence"] if item["dependency_position"] == 1)
    assert gap["required_for_qualification"] is False
    assert gap["qualified"] is False

    future_gap_features = [*features, {"bucket_end": "2026-01-01T00:05:00Z",
                                      "price": {"value": "105", "qualified": True,
                                                "available_at": "2026-01-01T00:11:00Z"}}]
    future_gap = evaluate_p06_bindings(schedule=schedule, evaluation_plan=plan, bindings=[binding],
                                       feature_rows=future_gap_features)[0]
    assert future_gap["qualified"] is True
    assert future_gap["available_at"] == "2026-01-01T00:10:00Z"
    assert "FUTURE_INFORMATION:1" in future_gap["reasons"]


def test_nested_price_return_uses_only_nested_endpoints_but_mean_keeps_each_bucket_required() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:15:00Z",
                "end": "2026-01-01T00:16:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    quote_unit = f"QUOTE:{record_contract.FIXTURE_STRATEGY['market']['research_binding']['quote_asset']}"
    def binding(price_expression):
        return {"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
                "price_expression": price_expression,
                "volume_expression": {"op": "gt", "args": [{"op": "quote_volume"},
                    {"op": "constant", "value": "4", "unit": quote_unit}]},
                "essential_inputs": ["price", "quote_volume"]}
    features = [
        {"bucket_end": "2026-01-01T00:00:00Z", "price": {"value": "100", "qualified": True}},
        {"bucket_end": "2026-01-01T00:10:00Z", "price": {"value": "110", "qualified": True}},
        {"bucket_end": "2026-01-01T00:15:00Z", "price": {"value": "120", "qualified": True},
         "quote_volume": {"value": "5", "qualified": True}},
    ]
    nested = {"op": "gt", "args": [
        {"op": "lag", "buckets": 1, "value": {"op": "price_return", "lookback_buckets": 2}},
        {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"},
    ]}
    nested_result = evaluate_p06_bindings(schedule=schedule, evaluation_plan=plan, bindings=[binding(nested)],
                                          feature_rows=features)[0]
    assert nested_result["price_state"] == "TRUE"
    assert nested_result["qualified"] is True
    nested_gap = next(item for item in nested_result["input_evidence"]
                      if item["dependency_position"] == 1)
    assert nested_gap["required_for_qualification"] is False

    rolling = {"op": "gt", "args": [
        {"op": "mean", "buckets": 3, "value": {"op": "price"}},
        {"op": "constant", "value": "0", "unit": "PRICE"},
    ]}
    rolling_result = evaluate_p06_bindings(schedule=schedule, evaluation_plan=plan, bindings=[binding(rolling)],
                                           feature_rows=features)[0]
    assert rolling_result["price_state"] == "UNKNOWN"
    assert rolling_result["qualified"] is False
    missing_middle = next(item for item in rolling_result["input_evidence"]
                          if item["dependency_position"] == 1)
    assert missing_middle["required_for_qualification"] is True


def test_future_historical_dependency_under_true_or_is_not_available_at_decision() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:05:00Z",
                "end": "2026-01-01T00:06:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    quote_unit = f"QUOTE:{record_contract.FIXTURE_STRATEGY['market']['research_binding']['quote_asset']}"
    price_expr = {"op": "or", "args": [
        {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "99", "unit": "PRICE"}]},
        {"op": "gt", "args": [{"op": "lag", "value": {"op": "price"}, "buckets": 1},
                {"op": "constant", "value": "99", "unit": "PRICE"}]},
    ]}
    binding = {"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
               "price_expression": price_expr,
               "volume_expression": {"op": "gt", "args": [{"op": "quote_volume"},
                   {"op": "constant", "value": "4", "unit": quote_unit}]},
               "essential_inputs": ["price", "quote_volume"]}
    features = [
        {"bucket_end": "2026-01-01T00:00:00Z",
         "price": {"value": "100", "qualified": True, "available_at": "2026-01-01T00:06:00Z"},
         "quote_volume": {"value": "5", "qualified": True, "available_at": "2026-01-01T00:06:00Z"}},
        {"bucket_end": "2026-01-01T00:05:00Z",
         "price": {"value": "100", "qualified": True, "available_at": "2026-01-01T00:05:00Z"},
         "quote_volume": {"value": "5", "qualified": True, "available_at": "2026-01-01T00:05:00Z"}},
    ]

    result = evaluate_p06_bindings(schedule=schedule, evaluation_plan=plan, bindings=[binding], feature_rows=features)

    assert result[0]["price_state"] == "TRUE"
    assert result[0]["qualified"] is False
    assert "FUTURE_INFORMATION:0" in result[0]["reasons"]
    future = next(item for item in result[0]["input_evidence"] if item["dependency_position"] == 0)
    assert future["available_at"] == "2026-01-01T00:06:00Z"
    assert future["qualified"] is False


def test_opportunity_preserves_exact_input_evidence_for_reopening() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:01:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    evidence = [{"input": "price", "bucket_end": "2026-01-01T00:00:00Z", "value": "100",
                 "qualified": True, "available_at": "2026-01-01T00:00:00Z", "reasons": []}]
    decision = {"decision_id": "d0", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:00:00Z",
                "available_at": "2026-01-01T00:00:00Z", "qualified": True,
                "essential_evidence_qualified": True, "price_state": "TRUE", "volume_state": "TRUE",
                "input_evidence": evidence}

    result = compare_effects(schedule=schedule, evaluation_plan=plan, decisions=[decision], trades=[],
                             incremental_volume_declared=False)

    saved = result["variants"][0]["opportunities"][0]["input_evidence"][0]
    assert {key: saved[key] for key in evidence[0]} == evidence[0]
    assert saved["input_dependency_id"]
    assert saved["dependency_identity_basis"] == "synthetic_input_observation_key"


def test_response_windows_outside_partition_are_not_read_or_widened() -> None:
    schedule = {"version": "decision-clock/1", "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:01:00Z", "interval_seconds": 60}
    plan = [{"evaluation_id": "eval-a", "trial_id": "trial-a", "variant_id": "rule-a",
             "horizon": {"value": 1, "unit": "MINUTES"}}]
    decision = {"decision_id": "d0", "evaluation_id": "eval-a", "decision_time": "2026-01-01T00:00:00Z",
                "available_at": "2026-01-01T00:00:00Z", "qualified": True,
                "essential_evidence_qualified": True, "price_state": "TRUE", "volume_state": "TRUE"}
    trades = [{"event_id": "out-of-scope", "event_time": "2026-01-01T00:00:20Z", "qualified": True,
               "block_number": 1, "transaction_index": 0, "log_index": 0, "price": "100"}]

    result = compare_effects(schedule=schedule, evaluation_plan=plan, decisions=[decision], trades=trades,
                             incremental_volume_declared=False,
                             partition_bounds_by_evaluation={"eval-a": {"start": "2026-01-01T00:01:00Z",
                                                                           "end": "2026-01-01T00:10:00Z"}})

    row = result["variants"][0]["opportunities"][0]
    assert row["start_trade"] is None
    assert row["group"] == "MISSING_OUTCOME"
    assert "OUTCOME_WINDOW_OUTSIDE_PARTITION" in row["reasons"]
    assert "out-of-scope" not in result["shared_event_ids"]
