from __future__ import annotations

import datetime as dt
from copy import deepcopy
from decimal import Decimal

import pytest

from edge_os_api import p02, p06


DECISION = dt.datetime(2026, 1, 1, 0, 15, tzinfo=dt.timezone.utc)
MARKET = p02.FIXTURE_STRATEGY["market"]


def observed(*values: str | None, reasons: dict[int, tuple[str, ...]] | None = None,
             future: set[int] | None = None, position: int = 0) -> list[p06.Observation | None]:
    reasons, future = reasons or {}, future or set()
    first_end = DECISION - dt.timedelta(minutes=5 * position)
    binding_id = p06.market_binding_id(MARKET)
    return [p06.Observation(value, first_end + dt.timedelta(minutes=5 * i), binding_id,
                            available_at=DECISION + dt.timedelta(seconds=1) if i in future else None,
                            reasons=reasons.get(i, ())) for i, value in enumerate(values)]


def relative_volume(buckets: int = 2) -> dict:
    return {"op": "relative_volume", "lookback_buckets": buckets}


def compare(op: str, left: dict, right: dict) -> dict:
    return {"op": op, "args": [left, right]}


def strategy_with_volume() -> dict:
    strategy = {**p02.FIXTURE_STRATEGY, "schema_version": p06.CONTRACT["identity"]["strategy_schema"],
                "semantic_manifest": dict(p06.MANIFEST), "entry": compare(
                    "gt", relative_volume(), {"op": "constant", "value": "2", "unit": "DIMENSIONLESS"}),
                "data_inputs": ["price", "quote_volume"], "warmup_buckets": 2}
    return strategy


def context(*, prices: tuple[str | None, ...] = (), quote_volumes: tuple[str | None, ...] = (),
            position: int = 0, price_reasons: dict[int, tuple[str, ...]] | None = None,
            volume_reasons: dict[int, tuple[str, ...]] | None = None,
            future_prices: set[int] | None = None) -> p06.EvaluationContext:
    length = max(len(prices), len(quote_volumes))
    price_rows = observed(*prices, reasons=price_reasons, future=future_prices, position=position)
    volume_rows = observed(*quote_volumes, reasons=volume_reasons, position=position)
    if not prices:
        price_rows = observed(*((None,) * length), position=position)
    if not quote_volumes:
        volume_rows = observed(*((None,) * length), position=position)
    schedule = tuple(row.bucket_end for row in price_rows if row is not None)
    return p06.EvaluationContext(price_rows, volume_rows, schedule, p06.market_binding_id(MARKET), DECISION, position)


def test_relative_volume_is_a_versioned_typed_strategy_and_binds_quote_asset():
    strategy = strategy_with_volume()

    p06.validate_strategy(strategy)

    assert strategy["schema_version"] == "p06.strategy/1"
    assert strategy["semantic_manifest"]["operator_registry"] == "edge-operators/2"
    assert strategy["warmup_buckets"] == 2
    assert p06.manifest_sha256() == p02.sha256_hex(p06.MANIFEST)


def test_relative_volume_uses_only_prior_scheduled_buckets():
    result = p06.evaluate_expression(relative_volume(2), MARKET,
                                     context(quote_volumes=("4", "8", "20"), position=2))

    assert result.value == Decimal("3.3333333333333333333333333333333333333333333333333")
    assert result.state == "VALUE"
    assert result.reasons == ()


@pytest.mark.parametrize("current,expected", [("0", "ZERO_BASELINE"), ("7", "ZERO_BASELINE")])
def test_relative_volume_zero_baseline_is_unknown(current: str, expected: str):
    result = p06.evaluate_expression(relative_volume(2), MARKET,
                                     context(quote_volumes=("0", "0", current), position=2))

    assert result.value is None
    assert result.state == "UNKNOWN"
    assert result.reasons == (expected,)


def test_price_return_keeps_intermediate_gap_while_using_qualified_endpoints():
    result = p06.evaluate_expression({"op": "price_return", "lookback_buckets": 2}, MARKET,
                                     context(prices=("100", None, "110"), position=2))

    assert result.value == Decimal("0.1")
    assert result.reasons == ("MISSING_PRICE:1",)


def test_numeric_failure_keeps_other_missing_reasons():
    result = p06.evaluate_expression({"op": "price_return", "lookback_buckets": 2}, MARKET,
                                     context(prices=("1e-999999", None, "1e999999"), position=2))

    assert result.state == "UNKNOWN"
    assert result.reasons == ("MISSING_PRICE:1", "NUMERIC_FAILURE")


def test_numeric_failure_is_an_unknown_operand_under_kleene_or():
    failed = compare("gt", {"op": "price_return", "lookback_buckets": 2},
                     {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"})
    rule = {"op": "or", "args": [
        compare("gt", {"op": "price"}, {"op": "constant", "value": "0", "unit": "PRICE"}), failed,
    ]}

    result = p06.evaluate_expression(rule, MARKET,
                                     context(prices=("1e-999999", None, "1e999999"), position=2))

    assert result.value == p06.Truth.TRUE
    assert result.reasons == ("MISSING_PRICE:1", "NUMERIC_FAILURE")


def test_rolling_mean_does_not_shrink_around_missing_scheduled_position():
    result = p06.evaluate_expression({"op": "mean", "value": {"op": "price"}, "buckets": 3}, MARKET,
                                     context(prices=("100", None, "110"), position=2))

    assert result.state == "UNKNOWN"
    assert result.reasons == ("MISSING_PRICE:1",)


def test_future_input_is_unknown_at_the_requested_decision_time():
    result = p06.evaluate_expression({"op": "price"}, MARKET,
                                     context(prices=("100",), future_prices={0}))

    assert result.state == "UNKNOWN"
    assert result.reasons == ("FUTURE_INFORMATION:0",)


def test_market_binding_mismatch_rejects_before_evaluation():
    data = context(prices=("100",))
    wrong = p06.EvaluationContext(data.prices, data.quote_volumes, data.scheduled_bucket_ends,
                                  "f" * 64, data.decision_time, data.position)

    with pytest.raises(p06.CompilerError) as error:
        p06.evaluate_expression({"op": "price"}, MARKET, wrong)

    assert error.value.code == "market_binding_mismatch"


def test_timestamp_mismatch_is_unknown_and_does_not_align_by_array_position():
    data = context(prices=("100",))
    mismatched = p06.Observation("100", DECISION - dt.timedelta(minutes=5), data.market_binding_id)
    wrong = p06.EvaluationContext((mismatched,), data.quote_volumes, data.scheduled_bucket_ends,
                                  data.market_binding_id, data.decision_time, 0)

    result = p06.evaluate_expression({"op": "price"}, MARKET, wrong)

    assert result.state == "UNKNOWN"
    assert result.reasons == ("SCHEDULE_MISMATCH:0",)


def test_even_a_single_schedule_position_must_be_utc_and_on_the_five_minute_grid():
    for scheduled in (dt.datetime(2026, 1, 1, 0, 14, tzinfo=dt.timezone.utc),
                      dt.datetime(2026, 1, 1, 0, 15)):
        binding = p06.market_binding_id(MARKET)
        observation = p06.Observation("100", scheduled, binding)
        data = p06.EvaluationContext((observation,), (None,), (scheduled,), binding, DECISION, 0)

        with pytest.raises(p06.CompilerError) as error:
            p06.evaluate_expression({"op": "price"}, MARKET, data)

        assert error.value.code == "schedule_mismatch"


def test_unqualified_input_is_unknown_with_its_reason():
    data = context(prices=("100",))
    stale = p06.Observation("100", DECISION, data.market_binding_id, qualified=False,
                            reasons=("STALE_SOURCE",))
    unqualified = p06.EvaluationContext((stale,), data.quote_volumes, data.scheduled_bucket_ends,
                                        data.market_binding_id, data.decision_time, 0)

    result = p06.evaluate_expression({"op": "price"}, MARKET, unqualified)

    assert result.state == "UNKNOWN"
    assert result.reasons == ("STALE_SOURCE", "UNQUALIFIED_PRICE:0")


@pytest.mark.parametrize(("left", "right", "and_value", "or_value"), [
    (p06.Truth.TRUE, p06.Truth.TRUE, p06.Truth.TRUE, p06.Truth.TRUE),
    (p06.Truth.TRUE, p06.Truth.FALSE, p06.Truth.FALSE, p06.Truth.TRUE),
    (p06.Truth.TRUE, p06.Truth.UNKNOWN, p06.Truth.UNKNOWN, p06.Truth.TRUE),
    (p06.Truth.FALSE, p06.Truth.TRUE, p06.Truth.FALSE, p06.Truth.TRUE),
    (p06.Truth.FALSE, p06.Truth.FALSE, p06.Truth.FALSE, p06.Truth.FALSE),
    (p06.Truth.FALSE, p06.Truth.UNKNOWN, p06.Truth.FALSE, p06.Truth.UNKNOWN),
    (p06.Truth.UNKNOWN, p06.Truth.TRUE, p06.Truth.UNKNOWN, p06.Truth.TRUE),
    (p06.Truth.UNKNOWN, p06.Truth.FALSE, p06.Truth.FALSE, p06.Truth.UNKNOWN),
    (p06.Truth.UNKNOWN, p06.Truth.UNKNOWN, p06.Truth.UNKNOWN, p06.Truth.UNKNOWN),
])
def test_kleene_boolean_table_and_reason_preservation(left, right, and_value, or_value):
    quote_unit = f"QUOTE:{MARKET['research_binding']['quote_asset']}"
    left_values = {p06.Truth.TRUE: "2", p06.Truth.FALSE: "1", p06.Truth.UNKNOWN: None}
    right_values = {p06.Truth.TRUE: "2", p06.Truth.FALSE: "0", p06.Truth.UNKNOWN: None}
    left_node = compare("gt", {"op": "price"}, {"op": "constant", "value": "1", "unit": "PRICE"})
    right_node = compare("gt", {"op": "quote_volume"},
                         {"op": "constant", "value": "1", "unit": quote_unit})
    left_value, right_value = left_values[left], right_values[right]
    data = p06.EvaluationContext(
        observed(left_value, reasons={0: ("PRICE_GAP",)} if left_value is None else None),
        observed(right_value, reasons={0: ("VOLUME_GAP",)} if right_value is None else None),
        (DECISION,), p06.market_binding_id(MARKET), DECISION, 0)

    and_result = p06.evaluate_expression({"op": "and", "args": [left_node, right_node]}, MARKET, data)
    or_result = p06.evaluate_expression({"op": "or", "args": [left_node, right_node]}, MARKET, data)

    assert and_result.value == and_value
    assert or_result.value == or_value
    assert and_result.state == and_value
    assert or_result.state == or_value
    if left == p06.Truth.UNKNOWN or right == p06.Truth.UNKNOWN:
        expected_reason = "PRICE_GAP" if left == p06.Truth.UNKNOWN else "VOLUME_GAP"
        assert expected_reason in and_result.reasons and expected_reason in or_result.reasons


def test_decisive_boolean_sibling_cannot_hide_unknown_operator():
    invalid = {"op": "and", "args": [
        compare("gt", {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"},
                {"op": "constant", "value": "1", "unit": "DIMENSIONLESS"}),
        {"op": "future_price"},
    ]}

    with pytest.raises(p06.CompilerError) as error:
        p06.expression_info(invalid, MARKET, "/entry")

    assert error.value.code == "unsupported_operator"
    assert error.value.path == "/entry/args/1"


@pytest.mark.parametrize(("expression", "code"), [
    ({"op": "gt", "args": [{"op": "price"}]}, "invalid_arity"),
    ({"op": "mac", "window": 4}, "unsupported_operator"),
    ({"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "1", "unit": "QUOTE:wrong"}]},
     "incompatible_unit"),
    ({"op": "lag", "value": {"op": "not", "value": {"op": "gt", "args": [
        {"op": "price"}, {"op": "constant", "value": "1", "unit": "PRICE"}]}}, "buckets": 1},
     "incompatible_type"),
])
def test_bad_arity_alias_unit_and_boolean_coercion_reject_at_compile(expression, code):
    with pytest.raises(p06.CompilerError) as error:
        p06.expression_info(expression, MARKET, "/entry")

    assert error.value.code == code


def test_unhashable_unit_is_a_compiler_error_not_an_internal_type_error():
    expression = {"op": "constant", "value": "1", "unit": []}

    with pytest.raises(p06.CompilerError) as error:
        p06.expression_info(expression, MARKET, "/entry")

    assert error.value.code == "incompatible_unit"
    assert error.value.path == "/entry/unit"


def test_relative_volume_and_nested_windows_have_exact_history_offsets():
    assert p06.required_history(relative_volume(2), MARKET) == 2
    assert p06.required_history({"op": "lag", "value": relative_volume(2), "buckets": 1}, MARKET) == 3
    assert p06.required_history({"op": "sum", "value": {"op": "price"}, "buckets": 2}, MARKET) == 1


def test_strict_and_inclusive_thresholds_keep_distinct_meaning():
    rule = {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "2", "unit": "PRICE"}]}
    at_threshold = context(prices=("2",))

    strict = p06.evaluate_expression(rule, MARKET, at_threshold)
    inclusive = p06.evaluate_expression({**rule, "op": "gte"}, MARKET, at_threshold)

    assert strict.value == p06.Truth.FALSE
    assert inclusive.value == p06.Truth.TRUE


def test_not_preserves_unknown_and_missing_reason():
    rule = {"op": "not", "value": compare("gt", {"op": "price"},
                                           {"op": "constant", "value": "1", "unit": "PRICE"})}
    result = p06.evaluate_expression(rule, MARKET,
                                     context(prices=(None,), price_reasons={0: ("PRICE_UNAVAILABLE",)}))

    assert result.state == "UNKNOWN"
    assert result.reasons == ("PRICE_UNAVAILABLE", "MISSING_PRICE:0")


def test_complete_empty_volume_is_zero_and_missing_volume_stays_unknown():
    empty = p06.evaluate_expression({"op": "quote_volume"}, MARKET,
                                    context(quote_volumes=("0",)))
    incomplete = p06.evaluate_expression({"op": "quote_volume"}, MARKET,
                                         context(quote_volumes=(None,)))

    assert empty.value == Decimal("0")
    assert incomplete.state == "UNKNOWN"
    assert incomplete.reasons == ("MISSING_QUOTE_VOLUME:0",)


def test_lookback_limit_accepts_288_and_rejects_289_independently():
    assert p06.expression_info({"op": "relative_volume", "lookback_buckets": 288}, MARKET).history == 288
    with pytest.raises(p06.CompilerError, match="Choose between 1 and 288"):
        p06.expression_info({"op": "relative_volume", "lookback_buckets": 289}, MARKET)


def test_expression_node_and_depth_limits_have_independent_edges():
    leaf = compare("gt", {"op": "constant", "value": "1", "unit": "DIMENSIONLESS"},
                   {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"})
    level = [deepcopy(leaf) for _ in range(512)]
    for _ in range(9):
        level = [{"op": "and", "args": [level[i], level[i + 1]]} for i in range(0, len(level), 2)]
    balanced = level[0]  # 512 comparison leaves and 511 AND nodes = 2,047 nodes.
    exact = {"op": "not", "value": balanced}  # exactly 2,048 nodes, depth 12.
    assert p06.expression_info(exact, MARKET).kind == "BOOLEAN"
    with pytest.raises(p06.CompilerError, match="too many operations"):
        p06.expression_info({"op": "not", "value": exact}, MARKET)

    depth_64 = leaf
    for _ in range(62):
        depth_64 = {"op": "not", "value": depth_64}
    assert p06.expression_info(depth_64, MARKET).kind == "BOOLEAN"
    with pytest.raises(p06.CompilerError, match="nested too deeply"):
        p06.expression_info({"op": "not", "value": depth_64}, MARKET)


def test_canonical_rule_and_manifest_changes_produce_new_identities():
    strategy = strategy_with_volume()
    changed = strategy_with_volume()
    changed["entry"]["args"][1]["value"] = "3"

    assert p02.sha256_hex(strategy) != p02.sha256_hex(changed)
    assert p06.manifest_sha256() != p02.sha256_hex(p02.MANIFEST)


def test_strategy_byte_limit_accepts_exact_boundary_and_rejects_one_over():
    strategy = strategy_with_volume()
    original = strategy["strategy_id"]
    needed = p06.LIMITS["input_bytes"] - len(p02.canonical_bytes(strategy))
    strategy["strategy_id"] = "x" * (len(original) + needed)
    assert len(p02.canonical_bytes(strategy)) == p06.LIMITS["input_bytes"]
    p06.validate_strategy(strategy)

    strategy["strategy_id"] += "x"
    with pytest.raises(p06.CompilerError, match="64 KiB"):
        p06.validate_strategy(strategy)


def test_evaluation_work_limit_stops_nested_rolling_expansion():
    expr: dict = {"op": "price"}
    for _ in range(4):
        expr = {"op": "mean", "value": expr, "buckets": 288}
    observations = tuple(p06.Observation("1", DECISION - dt.timedelta(minutes=5 * (1299 - i)),
                                         p06.market_binding_id(MARKET)) for i in range(1300))
    volumes = tuple(p06.Observation(None, row.bucket_end, row.market_binding_id) for row in observations)
    schedule = tuple(row.bucket_end for row in observations)
    data = p06.EvaluationContext(observations, volumes, schedule, p06.market_binding_id(MARKET), DECISION, 1150)

    with pytest.raises(p06.CompilerError) as error:
        p06.evaluate_expression(expr, MARKET, data)

    assert error.value.code == "evaluation_limit"


def test_evaluation_work_limit_accepts_boundary_then_rejects_one_step_over(monkeypatch):
    rule = {"op": "price_return", "lookback_buckets": 1}
    data = context(prices=("100", "110"), position=1)
    monkeypatch.setitem(p06.LIMITS, "evaluation_steps", 5)

    assert p06.evaluate_expression(rule, MARKET, data).value == Decimal("0.1")

    monkeypatch.setitem(p06.LIMITS, "evaluation_steps", 4)
    with pytest.raises(p06.CompilerError) as error:
        p06.evaluate_expression(rule, MARKET, data)
    assert error.value.code == "evaluation_limit"


def test_schedule_admission_and_expression_share_exact_work_boundary(monkeypatch):
    schedule = tuple(DECISION - dt.timedelta(minutes=5 * index) for index in range(4, -1, -1))
    data = p06.EvaluationContext((None,) * 5, (None,) * 5, schedule,
                                 p06.market_binding_id(MARKET), DECISION, 4)
    monkeypatch.setitem(p06.LIMITS, "evaluation_steps", 6)

    result = p06.evaluate_expression({"op": "constant", "value": "1", "unit": "DIMENSIONLESS"}, MARKET, data)

    assert result.value == Decimal("1")
    monkeypatch.setitem(p06.LIMITS, "evaluation_steps", 5)
    with pytest.raises(p06.CompilerError) as error:
        p06.evaluate_expression({"op": "constant", "value": "1", "unit": "DIMENSIONLESS"}, MARKET, data)
    assert error.value.code == "evaluation_limit"


def test_schedule_admission_rejects_oversized_length_before_scanning():
    class SizedSequence:
        def __init__(self, size):
            self.size, self.reads = size, 0

        def __len__(self):
            return self.size

        def __getitem__(self, index):
            self.reads += 1
            if index < 0 or index >= self.size:
                raise IndexError(index)
            return DECISION

    size = p06.LIMITS["evaluation_steps"] + 1
    schedule = SizedSequence(size)
    data = p06.EvaluationContext(SizedSequence(size), SizedSequence(size), schedule,
                                 p06.market_binding_id(MARKET), DECISION, size - 1)

    with pytest.raises(p06.CompilerError) as error:
        p06.evaluate_expression({"op": "constant", "value": "1", "unit": "DIMENSIONLESS"}, MARKET, data)

    assert error.value.code == "evaluation_limit"
    assert schedule.reads == 0


def test_six_level_eight_bucket_rolling_fixture_consumes_exactly_561780_steps(monkeypatch):
    expression: dict = {"op": "price"}
    for _ in range(6):
        expression = {"op": "mean", "value": expression, "buckets": 8}
    values = tuple("1" for _ in range(43))

    data = context(prices=values, position=42)
    monkeypatch.setitem(p06.LIMITS, "evaluation_steps", 561_780)
    result = p06.evaluate_expression(expression, MARKET, data)

    assert result.value == Decimal("1")
    assert p06.required_history(expression, MARKET) == 42

    monkeypatch.setitem(p06.LIMITS, "evaluation_steps", 561_779)
    with pytest.raises(p06.CompilerError) as error:
        p06.evaluate_expression(expression, MARKET, data)
    assert error.value.code == "evaluation_limit"
