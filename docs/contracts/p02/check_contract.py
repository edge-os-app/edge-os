#!/usr/bin/env python3
"""Small standard-library checks for the P02 contract and authored fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import unicodedata
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))
FIXTURES = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))
STRATEGY = json.loads((ROOT / "fixtures/complete-strategy.json").read_text(encoding="utf-8"))
DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


class Invalid(ValueError):
    pass


def reject_float(token: str) -> None:
    raise Invalid(f"JSON floating-point value is forbidden: {token}")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise Invalid(f"duplicate object key: {key}")
        result[key] = value
    return result


def strict_loads(data: str) -> object:
    return json.loads(data, object_pairs_hook=unique_object, parse_float=reject_float,
                      parse_constant=reject_float)


def canonical_bytes(value: object) -> bytes:
    def visit(node: object) -> None:
        if isinstance(node, float):
            raise Invalid("JSON floating-point value is forbidden")
        if isinstance(node, str):
            if unicodedata.normalize("NFC", node) != node:
                raise Invalid("strings must be Unicode NFC")
            if any(0xD800 <= ord(char) <= 0xDFFF for char in node):
                raise Invalid("surrogate code point")
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str):
                    raise Invalid("object keys must be strings")
                visit(key)
                visit(item)
        elif node is not None and not isinstance(node, (bool, int)):
            raise Invalid(f"unsupported JSON value: {type(node).__name__}")

    visit(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_decimal(value: object) -> Decimal:
    if not isinstance(value, str) or not DECIMAL.fullmatch(value):
        raise Invalid("decimal must be a finite canonical decimal string")
    if value == "-0" or value.startswith("-") and Decimal(value).is_zero():
        raise Invalid("negative zero is forbidden")
    if "." in value and value.endswith("0"):
        raise Invalid("trailing fractional zero is forbidden")
    return Decimal(value)


def expression_type(node: object, quote_unit: str, depth: int = 1,
                    budget: list[int] | None = None) -> str:
    if budget is None:
        budget = [0]
    if depth > CONTRACT["limits"]["expression_depth"]:
        raise Invalid("expression depth limit exceeded")
    budget[0] += 1
    if budget[0] > CONTRACT["limits"]["expression_nodes"]:
        raise Invalid("expression node limit exceeded")
    if not isinstance(node, dict) or not isinstance(node.get("op"), str):
        raise Invalid("expression node must be an operator object")

    op = node["op"]
    if op not in CONTRACT["operators"]:
        raise Invalid(f"unsupported operator: {op}")
    if op == "price":
        if set(node) != {"op"}:
            raise Invalid("price takes no arguments")
        return "PRICE"
    if op == "quote_volume":
        if set(node) != {"op"}:
            raise Invalid("quote_volume takes no arguments")
        return quote_unit
    if op == "constant":
        if set(node) != {"op", "value", "unit"}:
            raise Invalid("constant requires value and unit")
        canonical_decimal(node["value"])
        unit = node["unit"]
        if unit not in {"DIMENSIONLESS", quote_unit, "PRICE"}:
            raise Invalid(f"unsupported constant unit: {unit}")
        return unit

    if op in {"price_return", "lag", "sum", "mean"}:
        if op == "price_return":
            if set(node) != {"op", "lookback_buckets"}:
                raise Invalid("price_return requires lookback_buckets")
            lookback = node["lookback_buckets"]
        else:
            if set(node) != {"op", "value", "buckets"}:
                raise Invalid(f"{op} requires value and buckets")
            value_type = expression_type(node["value"], quote_unit, depth + 1, budget)
            lookback = node["buckets"]
        if isinstance(lookback, bool) or not isinstance(lookback, int):
            raise Invalid("lookback must be an integer bucket count")
        if not 1 <= lookback <= CONTRACT["limits"]["lookback_buckets"]:
            raise Invalid("lookback outside supported range")
        if op == "price_return":
            return "DIMENSIONLESS"
        return value_type

    if op in {"gt", "gte", "lt", "lte", "and", "or"}:
        if set(node) != {"op", "args"} or not isinstance(node["args"], list) or len(node["args"]) != 2:
            raise Invalid(f"{op} requires exactly two arguments")
        # Visit both operands before checking the parent so decisive siblings
        # cannot hide an invalid type, unsupported node, or future dependency.
        left = expression_type(node["args"][0], quote_unit, depth + 1, budget)
        right = expression_type(node["args"][1], quote_unit, depth + 1, budget)
        if op in {"and", "or"}:
            if left != "BOOLEAN" or right != "BOOLEAN":
                raise Invalid(f"{op} requires Boolean operands")
        elif left != right or left == "BOOLEAN":
            raise Invalid(f"{op} requires matching numeric units")
        return "BOOLEAN"
    if op == "not":
        if set(node) != {"op", "value"}:
            raise Invalid("not requires one value")
        if expression_type(node["value"], quote_unit, depth + 1, budget) != "BOOLEAN":
            raise Invalid("not requires a Boolean operand")
        return "BOOLEAN"
    raise Invalid(f"operator has no contract: {op}")


def used_operators(node: object) -> set[str]:
    if not isinstance(node, dict):
        return set()
    result = {node["op"]} if isinstance(node.get("op"), str) else set()
    for value in node.values():
        if isinstance(value, dict):
            result |= used_operators(value)
        elif isinstance(value, list):
            for item in value:
                result |= used_operators(item)
    return result


def validate_strategy(strategy: object) -> None:
    if not isinstance(strategy, dict):
        raise Invalid("strategy must be an object")
    required = set(CONTRACT["record_fields"]["StrategySpec"])
    if set(strategy) != required:
        missing, extra = required - set(strategy), set(strategy) - required
        raise Invalid(f"strategy keys differ; missing={sorted(missing)}, extra={sorted(extra)}")
    if strategy["schema_version"] != CONTRACT["identity"]["strategy_schema"]:
        raise Invalid("unsupported strategy schema")
    if strategy["domain"] != "SPOT" or strategy["decision_interval_seconds"] != 300:
        raise Invalid("P02 supports spot strategies on five-minute buckets")
    market = strategy["market"]
    if not isinstance(market, dict) or set(market) != {"network", "research_binding", "execution_route", "quote_unit"}:
        raise Invalid("market requires separate research and execution identities")
    research = market["research_binding"]
    research_keys = set(CONTRACT["record_fields"]["ResearchBinding"])
    if not isinstance(research, dict) or set(research) != research_keys or market["network"] != "MONAD":
        raise Invalid("research binding is incomplete")
    for asset in (research["pool_address"], research["base_asset"], research["quote_asset"]):
        if not isinstance(asset, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", asset):
            raise Invalid("pool and asset identities must be 20-byte hexadecimal addresses")
    if research["token_order"] != [research["base_asset"], research["quote_asset"]]:
        raise Invalid("token order must preserve the declared base/quote orientation")
    if research["orientation"] != "QUOTE_PER_BASE":
        raise Invalid("price orientation must be quote per base")
    for decimals in (research["base_decimals"], research["quote_decimals"]):
        if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 255:
            raise Invalid("asset decimals must be explicit integers")
    for name in ("underlying_venue", "event_schema_version", "amount_conversion_version", "data_route"):
        if not isinstance(research[name], str) or not research[name]:
            raise Invalid(f"research binding requires {name}")
    if research["qualification"] not in {"QUALIFIED", "UNQUALIFIED"}:
        raise Invalid("research qualification must be explicit")
    if research["chain_id"] is None and not (research["evidence_class"] == "SYNTHETIC_FIXTURE" and research["qualification"] == "UNQUALIFIED"):
        raise Invalid("unknown chain ID is allowed only for an unqualified synthetic fixture")
    if research["chain_id"] is not None and (isinstance(research["chain_id"], bool) or not isinstance(research["chain_id"], int)):
        raise Invalid("chain ID must be an integer or explicit null")
    route = market["execution_route"]
    if route != {"adapter": "KURU_FLOW_FIXED_INPUT", "identity_state": "UNKNOWN", "identity": None, "qualification": "UNQUALIFIED"}:
        raise Invalid("unknown or unqualified execution route must remain explicit")
    quote_unit = f"QUOTE:{research['quote_asset']}"
    if market["quote_unit"] != quote_unit:
        raise Invalid("quote unit must bind to the declared quote asset")

    if not isinstance(strategy["data_inputs"], list) or not set(strategy["data_inputs"]) <= {"price", "quote_volume"}:
        raise Invalid("unsupported data input")
    for name in ("entry", "exit"):
        if expression_type(strategy[name], quote_unit) != "BOOLEAN":
            raise Invalid(f"{name} must be Boolean")
    invalidation = strategy["invalidation"]
    if isinstance(invalidation, dict) and invalidation.get("state") == "NOT_REQUESTED":
        if set(invalidation) != {"state", "source_ref"} or not invalidation["source_ref"]:
            raise Invalid("an unrequested invalidation needs its source")
    elif expression_type(invalidation, quote_unit) != "BOOLEAN":
        raise Invalid("invalidation must be a Boolean rule or explicitly not requested")
    for name in ("entry", "exit", "invalidation"):
        if name != "invalidation" or not (isinstance(strategy[name], dict) and strategy[name].get("state") == "NOT_REQUESTED"):
            required_inputs = {op for op in used_operators(strategy[name]) if op in {"price", "price_return", "quote_volume"}}
            input_names = {"price" if op in {"price", "price_return"} else "quote_volume" for op in required_inputs}
            if not input_names <= set(strategy["data_inputs"]):
                raise Invalid(f"{name} uses an undeclared data input")

    sizing = strategy["sizing"]
    if not isinstance(sizing, dict) or set(sizing) != {"kind", "amount", "unit"} or sizing["kind"] != "FIXED_QUOTE_AMOUNT":
        raise Invalid("sizing must be a fixed quote amount")
    amount = canonical_decimal(sizing["amount"])
    if amount <= 0 or sizing["unit"] != quote_unit:
        raise Invalid("sizing amount must be positive and use the market quote asset")
    if strategy["additions"] is not False or strategy["partial_exits"] is not False:
        raise Invalid("P02 minimum subset rejects additions and partial exits")
    costs = strategy["cost_assumptions"]
    if not isinstance(costs, dict) or set(costs) != {"fee_rate", "slippage_rate", "source_ref"}:
        raise Invalid("fee and slippage assumptions need a source")
    if not 0 <= canonical_decimal(costs["fee_rate"]) <= 1 or not 0 <= canonical_decimal(costs["slippage_rate"]) <= 1:
        raise Invalid("fee and slippage rates must be between zero and one")
    if not isinstance(costs["source_ref"], str) or not costs["source_ref"]:
        raise Invalid("cost source is required")
    risk = strategy["risk_limits"]
    if not isinstance(risk, dict) or set(risk) != {"max_quote_notional", "max_open_positions"}:
        raise Invalid("risk limits are incomplete")
    if (canonical_decimal(risk["max_quote_notional"]) < amount
            or isinstance(risk["max_open_positions"], bool) or risk["max_open_positions"] != 1):
        raise Invalid("risk limits must cover size and cap the instance at one position")
    if strategy["action_scope"] != ["SPOT_BUY", "SPOT_SELL_ALL_ATTRIBUTABLE"]:
        raise Invalid("action scope is outside the minimum P02 subset")
    if strategy["execution_permission"] != {"state": "NOT_GRANTED", "mandate_ref": None}:
        raise Invalid("a strategy record cannot grant execution permission")
    warmup = strategy["warmup_buckets"]
    if isinstance(warmup, bool) or not isinstance(warmup, int) or not 1 <= warmup <= CONTRACT["limits"]["lookback_buckets"]:
        raise Invalid("warmup_buckets is outside the supported range")
    manifest = strategy["semantic_manifest"]
    if manifest != CONTRACT["identity"]["manifest_components"]:
        raise Invalid("semantic manifest is incomplete or changed")
    if len(manifest) > CONTRACT["limits"]["manifest_entries"]:
        raise Invalid("manifest entry limit exceeded")
    if len(canonical_bytes(strategy)) > CONTRACT["limits"]["input_bytes"]:
        raise Invalid("strategy input byte limit exceeded")


def route(case: dict[str, object]) -> str:
    data = case["input"]
    if data.get("meaning") == "unsupported":
        return "UNSUPPORTED"
    if data.get("syntax_valid") is False:
        return "INVALID_INPUT"
    if data.get("complete") is False:
        return "NEEDS_CLARIFICATION"
    if data.get("evidence_ready") is False:
        return "UNRESOLVED"
    return "COMPILED"


def boolean(op: str, values: list[str], reasons: list[str]) -> dict[str, object]:
    if op == "not":
        value = {"TRUE": "FALSE", "FALSE": "TRUE", "UNKNOWN": "UNKNOWN"}[values[0]]
    elif op == "and":
        value = "FALSE" if "FALSE" in values else "TRUE" if values == ["TRUE", "TRUE"] else "UNKNOWN"
    elif op == "or":
        value = "TRUE" if "TRUE" in values else "FALSE" if values == ["FALSE", "FALSE"] else "UNKNOWN"
    else:
        raise Invalid(f"unsupported Boolean operator: {op}")
    return {"value": value, "reasons": sorted(set(reasons))}


def check_fixture(case: dict[str, object]) -> None:
    kind, data, expected = case["kind"], case["input"], case.get("expected")
    if kind == "route":
        actual = route(case)
    elif kind == "return":
        prices = data["scheduled_prices"]
        intervals = data["intervals"]
        if len(prices) <= intervals or prices[-1] is None or prices[-1 - intervals] is None:
            actual = {"value": None, "unknown_reasons": ["missing_endpoint"]}
        else:
            with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
                actual_value = Decimal(prices[-1]) / Decimal(prices[-1 - intervals]) - Decimal(1)
            actual = {"value": format(actual_value, "f"), "unknown_reasons": [f"missing_bucket:{i}" for i, item in enumerate(prices) if item is None]}
    elif kind == "rolling_mean":
        prices = data["scheduled_prices"]
        buckets = data["buckets"]
        window = prices[-buckets:]
        missing = [f"missing_bucket:{i + len(prices) - len(window)}" for i, value in enumerate(window) if value is None]
        if len(window) != buckets or missing:
            actual = {"value": None, "unknown_reasons": missing or ["insufficient_scheduled_history"]}
        else:
            with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
                actual_value = sum((Decimal(value) for value in window), Decimal(0)) / Decimal(buckets)
            actual = {"value": format(actual_value, "f"), "unknown_reasons": []}
    elif kind == "decimal":
        if data["operation"] != "divide":
            raise Invalid("unknown decimal fixture operation")
        with localcontext(Context(prec=expected["precision"], rounding=ROUND_HALF_EVEN)):
            actual_value = Decimal(data["left"]) / Decimal(data["right"])
        actual = {"precision": expected["precision"], "rounding": "ROUND_HALF_EVEN", "prefix": format(actual_value, "f")}
    elif kind == "boolean":
        actual = boolean(data["operator"], data["values"], data["reasons"])
    elif kind == "boolean_truth_table":
        for left, right, and_value, or_value in data["rows"]:
            if boolean("and", [left, right], [])["value"] != and_value:
                raise AssertionError(f"bad AND truth row: {left}, {right}")
            if boolean("or", [left, right], [])["value"] != or_value:
                raise AssertionError(f"bad OR truth row: {left}, {right}")
        for value, not_value in data["not"]:
            if boolean("not", [value], [])["value"] != not_value:
                raise AssertionError(f"bad NOT truth row: {value}")
        actual = True
    elif kind == "clarification":
        valid = (data["previous_revision"] and data["missing_field"] and data["questions"]
                 and set(data["original_restrictions"]) <= set(data["next_restrictions"]))
        actual = "NEEDS_CLARIFICATION" if valid else "INVALID_INPUT"
    elif kind == "unsupported":
        actual = "UNSUPPORTED" if data["original_request"] and data["missing_capability"] else "INVALID_INPUT"
    elif kind == "unresolved":
        valid = data["missing_dependency"] and data["strategy"] is None
        actual = "UNRESOLVED" if valid else "INVALID_INPUT"
    elif kind == "draft":
        actual = (data["state"] == "DRAFT" and data["published_revision_id"] is None
                 and data["execution_permission"] == {"state": "NOT_GRANTED", "mandate_ref": None})
    elif kind == "owner_error":
        actual = data["http"] == 404 and data["code"] == "not_found" if not data["owner_matches"] else False
    elif kind == "idempotency":
        valid_retry = (data["first_key"] == data["retry_key"]
                       and data["first_fingerprint"] == data["retry_fingerprint"]
                       and data["acknowledgement"] == "UNKNOWN")
        actual = data["first_revision"] if valid_retry and data["first_revision"] == data["retry_revision"] else None
    elif kind == "idempotency_collision":
        actual = (409 if data["first_key"] == data["retry_key"]
                  and data["first_fingerprint"] != data["retry_fingerprint"] else 200)
    elif kind == "concurrent_publications":
        actual = (data["first_revision"] != data["second_revision"]
                  and data["first_key"] != data["second_key"]
                  and data["parent"] == "rev-parent")
    elif kind == "typed_expression":
        try:
            expression_type(data["expression"], data["quote_unit"])
        except Invalid:
            actual = "INVALID_INPUT"
        else:
            actual = "COMPILED"
    elif kind == "canonical_roundtrip":
        actual = strict_loads(canonical_bytes(data).decode("utf-8")) == data
    else:
        raise Invalid(f"unknown fixture kind: {kind}")
    if actual != expected:
        raise AssertionError(f"{case['id']}: expected {expected!r}, got {actual!r}")


def must_reject(label: str, strategy: dict[str, object]) -> None:
    try:
        validate_strategy(strategy)
    except (Invalid, TypeError, KeyError):
        return
    raise AssertionError(f"invalid mutation was accepted: {label}")


def main() -> int:
    if set(CONTRACT["operator_signatures"]) != set(CONTRACT["operators"]):
        raise AssertionError("operator names and machine signatures differ")
    if set(CONTRACT["record_fields"]["PublicationResult"]) != {
        "operation_id", "publication_id", "revision_id", "content_sha256", "manifest_sha256", "created_at", "outcome"
    }:
        raise AssertionError("publication result fields changed without checker review")
    for case in FIXTURES["cases"]:
        check_fixture(case)
    validate_strategy(STRATEGY)

    changed_rule = copy.deepcopy(STRATEGY)
    changed_rule["entry"]["args"][1]["value"] = "0.02"
    assert sha256(changed_rule) != sha256(STRATEGY), "meaning change must change content hash"
    changed_manifest = copy.deepcopy(STRATEGY["semantic_manifest"])
    changed_manifest["numeric"] = "decimal-51-half-even/1"
    assert sha256(changed_manifest) != sha256(STRATEGY["semantic_manifest"]), "semantic change must change manifest hash"
    canonical = canonical_bytes(STRATEGY)
    assert canonical_bytes(strict_loads(canonical.decode("utf-8"))) == canonical, "canonical reload must be stable"

    missing_field = copy.deepcopy(STRATEGY)
    del missing_field["invalidation"]
    must_reject("missing trading field", missing_field)
    wrong_unit = copy.deepcopy(STRATEGY)
    wrong_unit["entry"]["args"][1]["unit"] = "QUOTE:wrong-asset"
    must_reject("incompatible unit", wrong_unit)
    hidden_invalid = copy.deepcopy(STRATEGY)
    hidden_invalid["entry"] = {"op": "and", "args": [
        {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"},
        STRATEGY["entry"],
    ]}
    must_reject("invalid whole-tree Boolean type", hidden_invalid)
    unsupported_branch = copy.deepcopy(STRATEGY)
    unsupported_branch["entry"]["args"][0] = {"op": "future_price", "lookback_buckets": 1}
    must_reject("unsupported hidden operation", unsupported_branch)
    bad_history = copy.deepcopy(STRATEGY)
    bad_history["entry"]["args"][0]["lookback_buckets"] = 289
    must_reject("lookback over contract bound", bad_history)
    authority = copy.deepcopy(STRATEGY)
    authority["execution_permission"] = {"state": "GRANTED", "mandate_ref": "fixture-mandate"}
    must_reject("draft compiler cannot grant permission", authority)
    decimal_variant = copy.deepcopy(STRATEGY)
    decimal_variant["sizing"]["amount"] = 100.0
    must_reject("JSON float in decimal field", decimal_variant)
    duplicate_key = '{"revision_id":"a","revision_id":"b"}'
    try:
        strict_loads(duplicate_key)
    except Invalid:
        pass
    else:
        raise AssertionError("duplicate JSON keys were accepted")

    observation_as_exit = copy.deepcopy(STRATEGY)
    observation_as_exit["exit"] = {"op": "observation_period", "buckets": 12}
    must_reject("observation period is not an exit rule", observation_as_exit)

    print(f"PASS: {len(FIXTURES['cases'])} independent fixtures, valid strategy, canonical identity, and 9 rejection mutations")
    print("LIMIT: in-memory contract checks only; no server, storage, concurrency, provider, or production-cost claim")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, Invalid, KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
