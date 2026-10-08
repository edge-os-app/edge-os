"""P06's versioned compiler and numerical seam. The accepted P02 contract remains unchanged."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from decimal import Context, Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any, Sequence

from . import p02

CONTRACT_PATH = Path(__file__).resolve().parents[4] / "docs" / "contracts" / "p06" / "contract.json"
CONTRACT: dict[str, Any] = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
LIMITS = CONTRACT["limits"]
MANIFEST: dict[str, str] = CONTRACT["identity"]["manifest_components"]
NUMERIC = Context(prec=50, rounding=ROUND_HALF_EVEN)


class CompilerError(ValueError):
    def __init__(self, code: str, path: str, detail: str):
        super().__init__(detail)
        self.code, self.path, self.detail = code, path, detail


@dataclass(frozen=True)
class ExpressionInfo:
    kind: str
    unit: str
    history: int


class Truth:
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Observation:
    value: str | Decimal | None
    bucket_end: dt.datetime
    market_binding_id: str
    qualified: bool = True
    available_at: dt.datetime | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationContext:
    prices: Sequence[Observation | None]
    quote_volumes: Sequence[Observation | None]
    scheduled_bucket_ends: Sequence[dt.datetime]
    market_binding_id: str
    decision_time: dt.datetime
    position: int


@dataclass(frozen=True)
class EvaluationResult:
    value: Decimal | str | None
    reasons: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if self.value in {Truth.TRUE, Truth.FALSE, Truth.UNKNOWN}:
            return self.value
        if self.value is None:
            return Truth.UNKNOWN
        return "VALUE"


def manifest_sha256() -> str:
    return hashlib.sha256(p02.canonical_bytes(MANIFEST)).hexdigest()


def market_binding_id(market: dict[str, Any]) -> str:
    binding = {"network": market["network"], "quote_unit": market["quote_unit"],
               "research_binding": market["research_binding"]}
    return hashlib.sha256(p02.canonical_bytes(binding)).hexdigest()


def _merge_reasons(*groups: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(reason for group in groups for reason in group))


def _positive_window(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CompilerError("invalid_parameter", path, "Use a whole number of five-minute buckets.")
    if not 1 <= value <= LIMITS["lookback_buckets"]:
        raise CompilerError("invalid_parameter", path,
                            f"Choose between 1 and {LIMITS['lookback_buckets']} scheduled buckets.")
    return value


def expression_info(node: object, market: dict[str, Any], path: str = "", depth: int = 1,
                    budget: list[int] | None = None) -> ExpressionInfo:
    if budget is None:
        budget = [0]
    if depth > LIMITS["expression_depth"]:
        raise CompilerError("expression_depth_limit", path or "/", "The rule is nested too deeply.")
    budget[0] += 1
    if budget[0] > LIMITS["expression_nodes"]:
        raise CompilerError("expression_node_limit", path or "/", "The rule contains too many operations.")
    if not isinstance(node, dict) or not isinstance(node.get("op"), str):
        raise CompilerError("invalid_expression", path or "/", "Each rule step must be an operation object.")
    op = node["op"]
    if op not in CONTRACT["operators"]:
        raise CompilerError("unsupported_operator", path or "/",
                            f"The {op!r} operation is not supported by this price and quote-volume compiler.")

    quote_unit = f"QUOTE:{market['research_binding']['quote_asset']}"
    specs = {
        "constant": {"op", "value", "unit"}, "price": {"op"}, "quote_volume": {"op"},
        "price_return": {"op", "lookback_buckets"}, "relative_volume": {"op", "lookback_buckets"},
        "lag": {"op", "value", "buckets"}, "sum": {"op", "value", "buckets"},
        "mean": {"op", "value", "buckets"}, "gt": {"op", "args"}, "gte": {"op", "args"},
        "lt": {"op", "args"}, "lte": {"op", "args"}, "and": {"op", "args"},
        "or": {"op", "args"}, "not": {"op", "value"},
    }
    if set(node) != specs[op]:
        raise CompilerError("invalid_arity", path or "/", f"The {op} operation has the wrong fields or arguments.")
    if op == "constant":
        try:
            p02._checker.canonical_decimal(node["value"])
        except (p02.Invalid, TypeError) as error:
            raise CompilerError("invalid_constant", f"{path}/value", str(error)) from None
        unit = node["unit"]
        if not isinstance(unit, str) or unit not in {"DIMENSIONLESS", "PRICE", quote_unit}:
            raise CompilerError("incompatible_unit", f"{path}/unit", "The constant must use the declared market unit.")
        return ExpressionInfo("NUMERIC", unit, 0)
    if op == "price":
        return ExpressionInfo("NUMERIC", "PRICE", 0)
    if op == "quote_volume":
        return ExpressionInfo("NUMERIC", quote_unit, 0)
    if op in {"price_return", "relative_volume"}:
        lookback = _positive_window(node["lookback_buckets"], f"{path}/lookback_buckets")
        return ExpressionInfo("NUMERIC", "DIMENSIONLESS", lookback)
    if op in {"lag", "sum", "mean"}:
        child = expression_info(node["value"], market, f"{path}/value", depth + 1, budget)
        if child.kind != "NUMERIC":
            raise CompilerError("incompatible_type", f"{path}/value", f"{op} requires a numeric series.")
        buckets = _positive_window(node["buckets"], f"{path}/buckets")
        history = child.history + buckets if op == "lag" else child.history + buckets - 1
        return ExpressionInfo("NUMERIC", child.unit, history)
    if op == "not":
        child = expression_info(node["value"], market, f"{path}/value", depth + 1, budget)
        if child.kind != "BOOLEAN":
            raise CompilerError("incompatible_type", f"{path}/value", "not requires a Boolean rule.")
        return ExpressionInfo("BOOLEAN", "BOOLEAN", child.history)
    if not isinstance(node["args"], list) or len(node["args"]) != 2:
        raise CompilerError("invalid_arity", f"{path}/args", f"{op} requires exactly two arguments.")
    left = expression_info(node["args"][0], market, f"{path}/args/0", depth + 1, budget)
    right = expression_info(node["args"][1], market, f"{path}/args/1", depth + 1, budget)
    if op in {"and", "or"}:
        if left.kind != "BOOLEAN" or right.kind != "BOOLEAN":
            raise CompilerError("incompatible_type", f"{path}/args", f"{op} requires two Boolean rules.")
    elif left.kind != "NUMERIC" or right.kind != "NUMERIC" or left.unit != right.unit:
        raise CompilerError("incompatible_unit", f"{path}/args", f"{op} requires numeric values with matching units.")
    return ExpressionInfo("BOOLEAN", "BOOLEAN", max(left.history, right.history))


def _input_names(node: object) -> set[str]:
    if not isinstance(node, dict):
        return set()
    op = node.get("op")
    used = {"price"} if op in {"price", "price_return"} else set()
    if op in {"quote_volume", "relative_volume"}:
        used.add("quote_volume")
    for child in node.values():
        if isinstance(child, dict):
            used.update(_input_names(child))
        elif isinstance(child, list):
            for item in child:
                used.update(_input_names(item))
    return used


def required_history(node: object, market: dict[str, Any]) -> int:
    return expression_info(node, market).history


def validate_compile_fields(strategy: dict[str, Any]) -> int:
    fields = p02.CREATE_STRATEGY_FIELDS
    for name in fields:
        if name != "restrictions":
            try:
                p02._checker.validate_typed_value(
                    strategy[name], p02.CONTRACT["record_schemas"]["StrategySpec"]["required"][name],
                    f"StrategySpec.{name}")
            except (p02.Invalid, KeyError, TypeError) as error:
                raise CompilerError("invalid_field", f"/{name}", str(error)) from None
    if strategy["decision_interval_seconds"] != 300:
        raise CompilerError("unsupported_resolution", "/decision_interval_seconds",
                            "Rules use scheduled five-minute UTC buckets.")
    market = strategy["market"]
    try:
        p02._checker._validate_research_binding(market["research_binding"])
    except (p02.Invalid, KeyError, TypeError) as error:
        raise CompilerError("invalid_market_binding", "/market/research_binding", str(error)) from None
    quote_unit = f"QUOTE:{market['research_binding']['quote_asset']}"
    if market["network"] != "MONAD" or market["quote_unit"] != quote_unit:
        raise CompilerError("incompatible_market", "/market", "The rule must bind to its declared Monad quote asset.")
    route = market["execution_route"]
    if route != {"adapter": "KURU_FLOW_FIXED_INPUT", "identity_state": "UNKNOWN", "identity": None,
                 "qualification": "UNQUALIFIED"}:
        raise CompilerError("unsupported_route", "/market/execution_route",
                            "This compiler does not qualify or select an execution route.")
    if not isinstance(strategy["data_inputs"], list) or len(set(strategy["data_inputs"])) != len(strategy["data_inputs"]):
        raise CompilerError("invalid_data_inputs", "/data_inputs", "List each declared input once.")
    if not set(strategy["data_inputs"]) <= {"price", "quote_volume"}:
        raise CompilerError("unsupported_data_input", "/data_inputs", "Only price and quote volume inputs are supported.")
    infos: list[ExpressionInfo] = []
    for field_name in ("entry", "exit", "invalidation"):
        node = strategy[field_name]
        if field_name == "invalidation" and isinstance(node, dict) and node.get("state") == "NOT_REQUESTED":
            p02._checker.validate_shape("NotRequestedInvalidation", node)
            continue
        info = expression_info(node, market, f"/{field_name}")
        if info.kind != "BOOLEAN":
            raise CompilerError("incompatible_type", f"/{field_name}", f"{field_name} must be a Boolean rule.")
        if info.history > LIMITS["lookback_buckets"]:
            raise CompilerError("history_limit", f"/{field_name}",
                                "Nested rules need more than 288 scheduled buckets.")
        if not _input_names(node) <= set(strategy["data_inputs"]):
            raise CompilerError("undeclared_input", f"/{field_name}", f"{field_name} uses an undeclared data input.")
        infos.append(info)

    quote_unit = f"QUOTE:{market['research_binding']['quote_asset']}"
    sizing = strategy["sizing"]
    amount = p02._checker.canonical_decimal(sizing["amount"])
    if amount <= 0 or sizing["unit"] != quote_unit:
        raise CompilerError("invalid_sizing", "/sizing", "Position size must be positive and use the declared quote asset.")
    if strategy["additions"] is not False or strategy["partial_exits"] is not False:
        raise CompilerError("unsupported_action", "/action_scope", "This compiler does not support additions or partial exits.")
    costs = strategy["cost_assumptions"]
    if (not 0 <= p02._checker.canonical_decimal(costs["fee_rate"]) <= 1
            or not 0 <= p02._checker.canonical_decimal(costs["slippage_rate"]) <= 1 or not costs["source_ref"]):
        raise CompilerError("invalid_costs", "/cost_assumptions", "Fee and slippage assumptions need valid rates and a source.")
    risk = strategy["risk_limits"]
    if (p02._checker.canonical_decimal(risk["max_quote_notional"]) < amount
            or isinstance(risk["max_open_positions"], bool) or risk["max_open_positions"] != 1):
        raise CompilerError("invalid_risk_limits", "/risk_limits", "Risk limits must cover size and allow one position.")
    if strategy["action_scope"] != ["SPOT_BUY", "SPOT_SELL_ALL_ATTRIBUTABLE"]:
        raise CompilerError("unsupported_action", "/action_scope", "This compiler supports spot buy and full attributable exit only.")
    return max((info.history for info in infos), default=0)


def validate_strategy(strategy: object) -> None:
    if not isinstance(strategy, dict):
        raise CompilerError("invalid_strategy", "/", "A strategy must be an object.")
    descriptors = p02.CONTRACT["record_schemas"]["StrategySpec"]["required"]
    if set(strategy) != set(descriptors):
        raise CompilerError("invalid_strategy_fields", "/", "The strategy has missing or additional fields.")
    for name, descriptor in descriptors.items():
        p02._checker.validate_typed_value(strategy[name], descriptor, f"StrategySpec.{name}")
    if strategy["schema_version"] != CONTRACT["identity"]["strategy_schema"] or strategy["domain"] != "SPOT":
        raise CompilerError("unsupported_strategy_version", "/schema_version", "Use the versioned P06 spot strategy format.")
    if strategy["execution_permission"] != {"state": "NOT_GRANTED", "mandate_ref": None}:
        raise CompilerError("permission_forbidden", "/execution_permission", "Compilation cannot grant trading permission.")
    if strategy["semantic_manifest"] != MANIFEST or len(MANIFEST) > LIMITS["manifest_entries"]:
        raise CompilerError("manifest_mismatch", "/semantic_manifest", "The strategy manifest does not match P06 compiler meaning.")
    required = validate_compile_fields(strategy)
    if isinstance(strategy["warmup_buckets"], bool) or strategy["warmup_buckets"] != required:
        raise CompilerError("warmup_mismatch", "/warmup_buckets",
                            f"History must match the nested rule dependencies: {required} buckets.")
    if required > LIMITS["lookback_buckets"]:
        raise CompilerError("history_limit", "/warmup_buckets", "Nested rules need more than 288 scheduled buckets.")
    if len(p02.canonical_bytes(strategy)) > LIMITS["input_bytes"]:
        raise CompilerError("input_size_limit", "/", "The strategy exceeds the 64 KiB input limit.")


def build_strategy(strategy_id: str, values: dict[str, Any]) -> dict[str, Any]:
    import copy

    strategy = {"schema_version": CONTRACT["identity"]["strategy_schema"], "strategy_id": strategy_id,
                "domain": "SPOT"}
    for name in p02.CREATE_STRATEGY_FIELDS:
        if name != "restrictions":
            strategy[name] = copy.deepcopy(values[name])
    strategy["execution_permission"] = {"state": "NOT_GRANTED", "mandate_ref": None}
    strategy["warmup_buckets"] = max((required_history(strategy[name], strategy["market"])
                                      for name in ("entry", "exit", "invalidation")
                                      if not (name == "invalidation" and isinstance(strategy[name], dict)
                                              and strategy[name].get("state") == "NOT_REQUESTED")), default=0)
    strategy["semantic_manifest"] = dict(MANIFEST)
    return strategy


def _observation(context: EvaluationContext, name: str, position: int, spend: list[int]) -> EvaluationResult:
    spend[0] += 1
    if spend[0] > LIMITS["evaluation_steps"]:
        raise CompilerError("evaluation_limit", "/", "Rule evaluation exceeded its declared work limit.")
    values = context.prices if name == "price" else context.quote_volumes
    if position < 0 or position >= len(values) or values[position] is None:
        return EvaluationResult(None, (f"MISSING_POSITION:{position}",))
    item = values[position]
    assert item is not None
    reasons = item.reasons
    if item.market_binding_id != context.market_binding_id:
        return EvaluationResult(None, _merge_reasons(reasons, (f"MARKET_BINDING_MISMATCH:{position}",)))
    if item.bucket_end != context.scheduled_bucket_ends[position]:
        return EvaluationResult(None, _merge_reasons(reasons, (f"SCHEDULE_MISMATCH:{position}",)))
    if item.bucket_end > context.decision_time:
        return EvaluationResult(None, _merge_reasons(reasons, (f"FUTURE_INFORMATION:{position}",)))
    if item.value is None:
        return EvaluationResult(None, _merge_reasons(reasons, (f"MISSING_{name.upper()}:{position}",)))
    if not item.qualified:
        return EvaluationResult(None, _merge_reasons(reasons, (f"UNQUALIFIED_{name.upper()}:{position}",)))
    if item.available_at is not None and item.available_at > context.decision_time:
        return EvaluationResult(None, _merge_reasons(reasons, (f"FUTURE_INFORMATION:{position}",)))
    try:
        value = Decimal(item.value)
    except (DecimalException, TypeError, ValueError):
        return EvaluationResult(None, _merge_reasons(reasons, (f"INVALID_NUMERIC_INPUT:{position}",)))
    if not value.is_finite() or name == "price" and value <= 0 or name == "quote_volume" and value < 0:
        return EvaluationResult(None, _merge_reasons(reasons, (f"INVALID_NUMERIC_INPUT:{position}",)))
    return EvaluationResult(value, reasons)


def evaluate_expression(node: object, market: dict[str, Any], context: EvaluationContext) -> EvaluationResult:
    expression_info(node, market)
    if context.market_binding_id != market_binding_id(market):
        raise CompilerError("market_binding_mismatch", "/market", "Evaluation data is bound to a different research market.")
    if context.decision_time.tzinfo is None or context.decision_time.utcoffset() != dt.timedelta(0):
        raise CompilerError("invalid_timing", "/data/decision_time", "Decision time must be an explicit UTC instant.")
    if len(context.prices) != len(context.quote_volumes) or len(context.prices) != len(context.scheduled_bucket_ends):
        raise CompilerError("schedule_mismatch", "/data", "Price, quote-volume and schedule positions must match.")
    spend = [0]
    if len(context.scheduled_bucket_ends) > LIMITS["evaluation_steps"]:
        raise CompilerError("evaluation_limit", "/", "Rule evaluation exceeded its declared work limit.")
    previous: dt.datetime | None = None
    for index, current in enumerate(context.scheduled_bucket_ends):
        spend[0] += 1
        if spend[0] > LIMITS["evaluation_steps"]:
            raise CompilerError("evaluation_limit", "/", "Rule evaluation exceeded its declared work limit.")
        if (current.tzinfo is None or current.utcoffset() != dt.timedelta(0)
                or current.minute % 5 or current.second or current.microsecond
                or index and current - previous != dt.timedelta(minutes=5)):
            raise CompilerError("schedule_mismatch", "/data/scheduled_bucket_ends",
                                "Evaluation positions must be unique scheduled five-minute UTC buckets.")
        previous = current
    def numeric_failure(reasons: tuple[str, ...]) -> EvaluationResult:
        return EvaluationResult(None, _merge_reasons(reasons, ("NUMERIC_FAILURE",)))

    def evaluate(current: dict[str, Any], position: int) -> EvaluationResult:
        spend[0] += 1
        if spend[0] > LIMITS["evaluation_steps"]:
            raise CompilerError("evaluation_limit", "/", "Rule evaluation exceeded its declared work limit.")
        op = current["op"]
        if op == "constant":
            return EvaluationResult(Decimal(current["value"]))
        if op == "price":
            return _observation(context, "price", position, spend)
        if op == "quote_volume":
            return _observation(context, "quote_volume", position, spend)
        if op == "price_return":
            n = current["lookback_buckets"]
            now = _observation(context, "price", position, spend)
            then = _observation(context, "price", position - n, spend)
            # A missing middle close remains visible without invalidating qualified endpoints.
            gaps = [_observation(context, "price", index, spend).reasons
                    for index in range(position - n + 1, position)]
            reasons = _merge_reasons(now.reasons, then.reasons, *gaps)
            if not isinstance(now.value, Decimal) or not isinstance(then.value, Decimal):
                return EvaluationResult(None, reasons)
            try:
                with localcontext(NUMERIC):
                    value = now.value / then.value - Decimal(1)
            except DecimalException:
                return numeric_failure(reasons)
            return EvaluationResult(value, reasons)
        if op in {"lag", "sum", "mean"}:
            n = current["buckets"]
            if op == "lag":
                return evaluate(current["value"], position - n)
            values = [evaluate(current["value"], index) for index in range(position - n + 1, position + 1)]
            reasons = _merge_reasons(*(value.reasons for value in values))
            if any(not isinstance(value.value, Decimal) for value in values):
                return EvaluationResult(None, reasons)
            try:
                with localcontext(NUMERIC):
                    total = sum((value.value for value in values if isinstance(value.value, Decimal)), Decimal(0))
                    result = total if op == "sum" else total / Decimal(n)
            except DecimalException:
                return numeric_failure(reasons)
            return EvaluationResult(result, reasons)
        if op == "relative_volume":
            n = current["lookback_buckets"]
            now = evaluate({"op": "quote_volume"}, position)
            base = [evaluate({"op": "quote_volume"}, index) for index in range(position - n, position)]
            reasons = _merge_reasons(now.reasons, *(value.reasons for value in base))
            if not isinstance(now.value, Decimal) or any(not isinstance(value.value, Decimal) for value in base):
                return EvaluationResult(None, reasons)
            try:
                with localcontext(NUMERIC):
                    mean = sum((value.value for value in base if isinstance(value.value, Decimal)), Decimal(0)) / Decimal(n)
                    if mean == 0:
                        return EvaluationResult(None, _merge_reasons(reasons, ("ZERO_BASELINE",)))
                    result = now.value / mean
            except DecimalException:
                return numeric_failure(reasons)
            return EvaluationResult(result, reasons)
        if op == "not":
            value = evaluate(current["value"], position)
            if value.value == Truth.TRUE:
                result = Truth.FALSE
            elif value.value == Truth.FALSE:
                result = Truth.TRUE
            else:
                result = Truth.UNKNOWN
            return EvaluationResult(result, value.reasons)
        if op in {"and", "or"}:
            left, right = (evaluate(child, position) for child in current["args"])
            a, b = left.value, right.value
            if op == "and":
                result = Truth.FALSE if Truth.FALSE in (a, b) else Truth.TRUE if a == b == Truth.TRUE else Truth.UNKNOWN
            else:
                result = Truth.TRUE if Truth.TRUE in (a, b) else Truth.FALSE if a == b == Truth.FALSE else Truth.UNKNOWN
            return EvaluationResult(result, _merge_reasons(left.reasons, right.reasons))
        left, right = (evaluate(child, position) for child in current["args"])
        reasons = _merge_reasons(left.reasons, right.reasons)
        if not isinstance(left.value, Decimal) or not isinstance(right.value, Decimal):
            return EvaluationResult(Truth.UNKNOWN, reasons)
        result = {"gt": left.value > right.value, "gte": left.value >= right.value,
                  "lt": left.value < right.value, "lte": left.value <= right.value}[op]
        return EvaluationResult(Truth.TRUE if result else Truth.FALSE, reasons)

    return evaluate(node, context.position)
