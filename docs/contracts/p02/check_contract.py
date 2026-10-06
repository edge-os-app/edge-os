#!/usr/bin/env python3
"""Small standard-library checks for the P02 contract and authored fixtures."""

from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
import re
import sys
import tempfile
import unicodedata
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parent
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


def load_json(path: Path) -> object:
    return strict_loads(path.read_text(encoding="utf-8"))


CONTRACT = load_json(ROOT / "contract.json")
FIXTURES = load_json(ROOT / "fixtures.json")
STRATEGY = load_json(ROOT / "fixtures/complete-strategy.json")
STRATEGY_FIXTURES = {"complete-strategy": STRATEGY}


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
            if value_type == "BOOLEAN":
                raise Invalid(f"{op} requires a numeric operand")
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


def required_history(node: object) -> int:
    """Maximum scheduled offset from the decision bucket to an input bucket."""
    op = node["op"]
    if op in {"price", "quote_volume", "constant"}:
        return 0
    if op == "price_return":
        return node["lookback_buckets"]
    if op == "lag":
        return required_history(node["value"]) + node["buckets"]
    if op in {"sum", "mean"}:
        return required_history(node["value"]) + node["buckets"] - 1
    children = node.get("args", []) if op in {"and", "or", "gt", "gte", "lt", "lte"} else [node["value"]]
    return max((required_history(child) for child in children), default=0)


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
    validate_record("StrategySpec", strategy)


def _validate_strategy_semantics(strategy: object) -> None:
    if not isinstance(strategy, dict):
        raise Invalid("strategy must be an object")
    required = set(CONTRACT["record_schemas"]["StrategySpec"]["required"])
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
    if market["network"] != "MONAD":
        raise Invalid("market network is outside the P02 subset")
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
    expressions = [strategy["entry"], strategy["exit"]]
    if not (isinstance(invalidation, dict) and invalidation.get("state") == "NOT_REQUESTED"):
        expressions.append(invalidation)
    required = max(required_history(expression) for expression in expressions)
    warmup = strategy["warmup_buckets"]
    if isinstance(warmup, bool) or not isinstance(warmup, int) or not 0 <= warmup <= CONTRACT["limits"]["lookback_buckets"]:
        raise Invalid("warmup_buckets is outside the supported range")
    if warmup != required:
        raise Invalid(f"warmup_buckets must equal derived history requirement {required}")
    manifest = strategy["semantic_manifest"]
    if manifest != CONTRACT["identity"]["manifest_components"]:
        raise Invalid("semantic manifest is incomplete or changed")
    if len(manifest) > CONTRACT["limits"]["manifest_entries"]:
        raise Invalid("manifest entry limit exceeded")
    if len(canonical_bytes(strategy)) > CONTRACT["limits"]["input_bytes"]:
        raise Invalid("strategy input byte limit exceeded")


def validate_record(name: str, value: object) -> None:
    schema = CONTRACT["record_schemas"][name]
    if not isinstance(value, dict):
        raise Invalid(f"{name} must be an object")
    required, optional = schema["required"], schema["optional"]
    keys = set(value)
    if not set(required) <= keys or keys - set(required) - set(optional):
        raise Invalid(f"{name} has missing or additional properties")
    for key, descriptor in {**required, **optional}.items():
        if key in value:
            validate_typed_value(value[key], descriptor, f"{name}.{key}")
    if name in {"Outcome", "PublicationResult"}:
        allowed_codes = CONTRACT["result_codes"].get(value["outcome"])
        if allowed_codes is not None:
            if isinstance(allowed_codes, str):
                allowed_codes = [allowed_codes]
            if value["code"] not in allowed_codes:
                raise Invalid(f"{name} code does not match outcome")
    if name == "StrategySpec":
        _validate_strategy_semantics(value)
    if name == "ResearchBinding":
        _validate_research_binding(value)
    if name == "FieldEvidence":
        state, origin = value["state"], value["origin"]
        if state == "KNOWN" and "value" not in value:
            raise Invalid("KNOWN evidence requires value")
        if state != "KNOWN" and "value" in value:
            raise Invalid(f"{state} evidence cannot contain value")
        if state == "CONFLICTING":
            conflicts = value.get("conflicts", [])
            if len(conflicts) < 2 or len({item["source_ref"] for item in conflicts}) < 2:
                raise Invalid("CONFLICTING evidence requires two source-linked alternatives")
            if value.get("adoption") == "ADOPTED":
                raise Invalid("CONFLICTING evidence cannot be adopted")
        consequential = value["field_name"] in CONTRACT["field_evidence_rules"]["consequential_fields"]
        if origin in {"AGENT_PROPOSED", "APPLICATION_CONFIGURED"} and consequential and value.get("adoption") not in {"ADOPTED", "PENDING"}:
            raise Invalid("consequential proposed evidence requires adoption state")
    if name == "Clarification":
        if not value["changed_fields"] or len(set(value["changed_fields"])) != len(value["changed_fields"]):
            raise Invalid("Clarification requires a unique changed-field list")
        if len(set(value["preserved_restrictions"])) != len(value["preserved_restrictions"]):
            raise Invalid("Clarification restrictions cannot contain duplicates")
    if name == "IntakeRequest" and len(set(value["restrictions"])) != len(value["restrictions"]):
        raise Invalid("intake restrictions cannot contain duplicates")
    if name in {"Outcome", "PublicationResult"}:
        if CONTRACT["outcome_requirements"]["finding_path_format"] == "JSON_POINTER" and any(
            not _is_json_pointer(finding["path"]) for finding in value["findings"]
        ):
            raise Invalid("failure findings require a JSON Pointer path")
        expected_findings = CONTRACT["outcome_findings"].get(value["outcome"], [])
        codes = {finding["code"] for finding in value["findings"]}
        if value["outcome"] in CONTRACT["outcome_requirements"]["finding_required"] and not value["findings"]:
            raise Invalid(f"{value['outcome']} outcome requires actionable findings")
        if expected_findings and (not value["findings"] or not set(expected_findings) & codes):
            raise Invalid(f"{value['outcome']} outcome is missing its required finding")
        if name == "Outcome" and value["outcome"] == "NEEDS_CLARIFICATION":
            for finding in value["findings"]:
                prefix = "/field_evidence/"
                field_name = finding["path"][len(prefix):] if finding["path"].startswith(prefix) else ""
                field_label = field_name.replace("_", " ").casefold()
                if (not field_name or "/" in field_name or not finding["detail"].strip().endswith("?")
                        or field_label not in finding["detail"].casefold()):
                    raise Invalid("clarification finding must name its field and ask a specific question")
        if name == "Outcome" and value["outcome"] in CONTRACT["outcome_requirements"]["intake_record_required"]:
            if not value.get("intake_record_id"):
                raise Invalid(f"{value['outcome']} outcome must link to its intake record")
        if value["outcome"] == "INVALID_INPUT":
            if not value["findings"] or any(not finding["path"].startswith("/") for finding in value["findings"]):
                raise Invalid("INVALID_INPUT needs a stable finding code and JSON Pointer path")
    if name == "PublicationResult" and value["outcome"] == "CONFLICTED":
        rules = CONTRACT["publication_failure_rules"]
        if value["code"] in rules:
            rule = rules[value["code"]]
            if value["retry"] != rule["retry"] or len(value["findings"]) != 1 or value["findings"][0]["code"] != rule["finding_code"]:
                raise Invalid("conflicted publication code, finding, and retry policy must match")
    if name == "PromptInterpretation":
        names = [item["field_name"] for item in value["field_evidence"]]
        if len(set(names)) != len(names):
            raise Invalid("interpretation field names must be unique")
        if len(set(value["preserved_restrictions"])) != len(value["preserved_restrictions"]):
            raise Invalid("interpretation restrictions cannot contain duplicates")
        for item in value["field_evidence"]:
            validate_record("FieldEvidence", item)
            if item["interpretation_revision"] != value["interpretation_revision_id"]:
                raise Invalid("field evidence must bind to its interpretation revision")
    if name == "PublicationResult" and value["outcome"] == "PUBLISHED":
        if any(not isinstance(value[field], str) or not value[field] for field in ("publication_id", "revision_id")):
            raise Invalid("PUBLISHED result requires nonempty publication and revision IDs")
        if any(value[field] is None for field in ("content_sha256", "manifest_sha256")):
            raise Invalid("PUBLISHED result requires exact publication identity")
        for field in ("content_sha256", "manifest_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", value[field]):
                raise Invalid(f"{field} must be a lowercase SHA-256 digest")
    elif name == "PublicationResult" and any(value[field] is not None for field in ("publication_id", "revision_id", "content_sha256", "manifest_sha256")):
        raise Invalid("non-success publication result cannot carry publication identity")
    if len(canonical_bytes(value)) > CONTRACT["limits"]["input_bytes"]:
        raise Invalid(f"{name} input byte limit exceeded")


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


def _is_json_pointer(value: object) -> bool:
    return isinstance(value, str) and value.startswith("/") and re.search(r"~(?![01])", value) is None


def _validate_research_binding(binding: object) -> None:
    rules = CONTRACT["research_binding_rules"]
    if not isinstance(binding, dict):
        raise Invalid("ResearchBinding must be an object")
    if binding["token_order"] != [binding[key] for key in rules["token_order"]]:
        raise Invalid("token order must preserve the declared base/quote orientation")
    if binding["orientation"] != rules["orientation"]:
        raise Invalid("price orientation must be quote per base")
    low, high = rules["decimal_range"]
    for key in ("base_decimals", "quote_decimals"):
        if isinstance(binding[key], bool) or not low <= binding[key] <= high:
            raise Invalid("asset decimals must be explicit integers in the supported range")
    if binding["chain_id"] is None and not (
        binding["evidence_class"] == rules["null_chain_evidence_class"]
        and binding["qualification"] == rules["null_chain_qualification"]
    ):
        raise Invalid("unknown chain ID is allowed only for an unqualified synthetic fixture")


def parse_utc_timestamp(value: object) -> tuple[datetime, Decimal]:
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z", value) if isinstance(value, str) else None
    if match is None:
        raise Invalid("timestamp must be RFC 3339 UTC")
    if int(match.group(1)[11:13]) > 23:
        raise Invalid("timestamp must be a valid RFC 3339 UTC instant")
    try:
        seconds = datetime.fromisoformat(match.group(1) + "+00:00")
        fraction = Decimal("0." + match.group(2)) if match.group(2) else Decimal(0)
        return seconds, fraction
    except ValueError as error:
        raise Invalid("timestamp must be a valid RFC 3339 UTC instant") from error


def _is_utc_timestamp(value: object) -> bool:
    try:
        parse_utc_timestamp(value)
    except Invalid:
        return False
    return True


def validate_typed_value(value: object, descriptor: dict[str, object], path: str) -> None:
    kind = descriptor["type"]
    types = {
        "string": lambda v: isinstance(v, str),
        "nonempty_string": lambda v: isinstance(v, str) and bool(v),
        "nullable_string": lambda v: v is None or isinstance(v, str),
        "null": lambda v: v is None,
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "nullable_integer": lambda v: v is None or isinstance(v, int) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "object": lambda v: isinstance(v, dict),
        "json_value": lambda v: _is_json_value(v),
        "expression_object": lambda v: isinstance(v, dict),
        "expression_or_not_requested": lambda v: isinstance(v, dict),
        "string_map": lambda v: isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, str) for k, x in v.items()),
        "string_array": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
        "object_array": lambda v: isinstance(v, list) and all(isinstance(x, dict) for x in v),
        "finding_array": lambda v: isinstance(v, list) and all(isinstance(x, dict) and set(x) == {"code", "path", "detail"} and all(isinstance(x[k], str) for k in x) for x in v),
        "field_evidence_array": lambda v: isinstance(v, list) and all(isinstance(x, dict) for x in v),
        "clarification_array": lambda v: isinstance(v, list) and all(isinstance(x, dict) for x in v),
        "address": lambda v: isinstance(v, str) and re.fullmatch(r"0x[0-9a-fA-F]{40}", v) is not None,
        "address_array": lambda v: isinstance(v, list) and all(isinstance(x, str) and re.fullmatch(r"0x[0-9a-fA-F]{40}", x) for x in v),
        "decimal_string": lambda v: isinstance(v, str) and DECIMAL.fullmatch(v) is not None,
        "rfc3339_utc": lambda v: _is_utc_timestamp(v),
    }
    if kind.startswith("shape:"):
        validate_shape(kind.split(":", 1)[1], value)
        return
    if kind.startswith("shape_array:"):
        shape_name = kind.split(":", 1)[1]
        if not isinstance(value, list):
            raise Invalid(f"{path} must be an array")
        for item in value:
            validate_shape(shape_name, item)
        return
    if kind.startswith("record:"):
        validate_record(kind.split(":", 1)[1], value)
        return
    if kind == "expression_or_not_requested" and isinstance(value, dict) and value.get("state") == "NOT_REQUESTED":
        validate_shape("NotRequestedInvalidation", value)
        return
    if kind not in types or not types[kind](value):
        raise Invalid(f"{path} must have type {kind}")
    if "enum" in descriptor and value not in descriptor["enum"]:
        raise Invalid(f"{path} has an unknown enum value")
    if kind == "field_evidence_array":
        for item in value:
            validate_record("FieldEvidence", item)
    elif kind == "clarification_array":
        for item in value:
            validate_record("Clarification", item)


def validate_shape(name: str, value: object) -> None:
    schema = CONTRACT["nested_shapes"][name]
    if not isinstance(value, dict):
        raise Invalid(f"{name} must be an object")
    required, optional = schema["required"], schema["optional"]
    keys = set(value)
    if not set(required) <= keys or keys - set(required) - set(optional):
        raise Invalid(f"{name} has missing or additional properties")
    for key, descriptor in {**required, **optional}.items():
        if key in value:
            validate_typed_value(value[key], descriptor, f"{name}.{key}")


def validate_http_error(value: object) -> None:
    schema = CONTRACT["http_error_body"]
    if not isinstance(value, dict) or set(value) != set(schema["required"]):
        raise Invalid("HTTP error body has missing or additional properties")
    for key, descriptor in schema["required"].items():
        validate_typed_value(value[key], descriptor, f"HttpError.{key}")


def route(case: dict[str, object]) -> str:
    data = case["input"]
    interpretation = data.get("interpretation")
    try:
        validate_record("PromptInterpretation", interpretation)
    except (Invalid, KeyError, TypeError):
        actual = "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    if interpretation["syntax_status"] == "INVALID":
        actual = "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    if interpretation["meaning_status"] == "UNSUPPORTED":
        actual = "UNSUPPORTED" if data.get("original_request") and data.get("missing_capability") else "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    if interpretation["requested_job"] not in CONTRACT["required_strategy_fields"]:
        return "HANDOFF"
    if interpretation["evidence_readiness"] == "UNRESOLVED":
        actual = "UNRESOLVED"
        _validate_route_result(case, actual)
        return actual
    required = set(CONTRACT["required_strategy_fields"][interpretation["requested_job"]])
    evidence = interpretation["field_evidence"]
    if any(item["field_name"] not in required for item in evidence):
        actual = "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    by_name = {item["field_name"]: item for item in evidence}
    if len(by_name) != len(evidence):
        actual = "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    if required - set(by_name) or any(item["state"] in {"MISSING", "CONFLICTING"} for item in evidence):
        actual = "NEEDS_CLARIFICATION"
        _validate_route_result(case, actual)
        return actual
    if any(item.get("origin") in {"AGENT_PROPOSED", "APPLICATION_CONFIGURED"}
           and item.get("field_name") in required and item.get("adoption") != "ADOPTED" for item in evidence):
        actual = "NEEDS_CLARIFICATION"
        _validate_route_result(case, actual)
        return actual
    restrictions = by_name["restrictions"]["value"]
    if restrictions != interpretation["preserved_restrictions"]:
        actual = "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    supported_restrictions = CONTRACT["supported_restrictions"]
    if any(item not in supported_restrictions for item in restrictions):
        actual = "UNSUPPORTED"
        _validate_route_result(case, actual)
        return actual
    strategy = data.get("candidate_strategy")
    if not isinstance(strategy, dict):
        actual = "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    try:
        validate_strategy(strategy)
    except (Invalid, KeyError, TypeError):
        actual = "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    if any(canonical_bytes(by_name[name]["value"]) != canonical_bytes(strategy[name])
           for name in required if name != "restrictions"):
        actual = "INVALID_INPUT"
        _validate_route_result(case, actual)
        return actual
    for restriction in restrictions:
        rule = supported_restrictions[restriction]
        path = rule["field"].split(".")
        actual = strategy
        for part in path:
            actual = actual[part]
        if actual != rule["equals"]:
            outcome = "INVALID_INPUT"
            _validate_route_result(case, outcome)
            return outcome
    return "COMPILED"


def _validate_route_result(case: dict[str, object], expected: str) -> None:
    result = case.get("result")
    if not isinstance(result, dict):
        raise Invalid(f"{expected} route fixture requires a detailed Outcome")
    validate_record("Outcome", result)
    if result["outcome"] != expected:
        raise Invalid("route result details must match the routed outcome")
    interpretation = case["input"].get("interpretation")
    if isinstance(interpretation, dict) and result.get("intake_record_id") != interpretation.get("intake_record_id"):
        raise Invalid("route outcome must link to its intake record")
    if expected == "NEEDS_CLARIFICATION":
        required = set(CONTRACT["required_strategy_fields"][interpretation["requested_job"]])
        evidence = {item["field_name"]: item for item in interpretation["field_evidence"]}
        targets = {name for name, item in evidence.items()
                   if item["state"] in {"MISSING", "CONFLICTING"}
                   or item.get("origin") in {"AGENT_PROPOSED", "APPLICATION_CONFIGURED"}
                   and item.get("adoption") != "ADOPTED"}
        absent = required - set(evidence)
        if absent and not targets:
            history = interpretation.get("clarification_history", [])
            prior_targets = {name for item in history for name in item["changed_fields"] if name in absent}
            targets.update(prior_targets or absent)
        for field_name in targets:
            path = f"/field_evidence/{field_name}"
            findings = [finding for finding in result["findings"] if finding["path"] == path]
            field_label = field_name.replace("_", " ")
            if not findings or any(not finding["detail"].strip().endswith("?")
                                   or field_label not in finding["detail"].casefold() for finding in findings):
                raise Invalid("clarification finding must name its field and ask a specific question")
    if expected == "UNRESOLVED" and case["input"].get("candidate_strategy") is not None:
        raise Invalid("UNRESOLVED route cannot carry a strategy")


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
        clarification = data["clarification"]
        validate_record("Clarification", clarification)
        if clarification["previous_revision_id"] not in data["known_revision_ids"]:
            actual = "INVALID_INPUT"
            if actual != expected:
                raise AssertionError(f"{case['id']}: expected {expected!r}, got {actual!r}")
            return
        valid = (clarification["previous_revision_id"] and clarification["question"]
                 and set(data["original_restrictions"]) <= set(data["next_restrictions"])
                 and set(data["original_restrictions"]) <= set(clarification["preserved_restrictions"])
                 and set(data["next_restrictions"]) == set(clarification["preserved_restrictions"]))
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
        def hidden_not_found(operation_id: str) -> dict[str, object]:
            return {"http": 404, "body": {"operation_id": operation_id, "stage": "READ", "outcome": "NOT_FOUND",
                    "code": "not_found", "findings": [], "retry": "NOT_RETRYABLE"}}
        def owner_scoped_lookup(principal: str, stored_owner: str | None) -> dict[str, object]:
            if stored_owner is None or stored_owner != principal:
                return hidden_not_found(data["operation_id"])
            return {"http": 200, "body": {"record_id": data["requested_id"]}}
        denied = owner_scoped_lookup(data["owner_id"], data["record_owner_id"])
        absent = owner_scoped_lookup(data["owner_id"], None)
        validate_http_error(denied["body"])
        actual = denied if denied == absent else None
    elif kind == "idempotency":
        first_strategy = _strategy_fixture(data["strategy_fixture"])
        retry_strategy = _strategy_fixture(data["retry_strategy_fixture"])
        _validate_strategy_path(data["path"], first_strategy)
        _validate_strategy_path(data["retry_path"], retry_strategy)
        first = {"owner_id": data["owner_id"], "method": data["method"], "path": data["path"],
                 "expected_parent_revision_id": data["expected_parent_revision_id"], "draft_id": data["draft_id"],
                 "strategy": first_strategy}
        retry = {"owner_id": data["retry_owner_id"], "method": data["retry_method"], "path": data["retry_path"],
                 "expected_parent_revision_id": data["retry_expected_parent_revision_id"], "draft_id": data["retry_draft_id"],
                 "strategy": retry_strategy}
        valid_retry = (data["idempotency_key"] == data["retry_idempotency_key"]
                       and sha256(first) == sha256(retry) and data["acknowledgement"] == "UNKNOWN")
        # Stored idempotency results replay before draft/parent revalidation.
        actual = data["first_revision"] if valid_retry and not data["retry_parent_still_valid"] and data["first_revision"] == data["retry_revision"] else None
    elif kind == "idempotency_collision":
        first_strategy = _strategy_fixture(data["strategy_fixture"])
        retry_strategy = _strategy_fixture(data["retry_strategy_fixture"])
        _validate_strategy_path(data["path"], first_strategy)
        _validate_strategy_path(data["retry_path"], retry_strategy)
        first = {"owner_id": data["owner_id"], "method": data["method"], "path": data["path"],
                 "expected_parent_revision_id": data["parent"], "draft_id": data["draft_id"], "strategy": first_strategy}
        retry = {"owner_id": data["retry_owner_id"], "method": data["retry_method"], "path": data["retry_path"],
                 "expected_parent_revision_id": data["retry_parent"], "draft_id": data["retry_draft_id"], "strategy": retry_strategy}
        if data["mutate_strategy_threshold"]:
            retry["strategy"] = copy.deepcopy(retry_strategy)
            retry["strategy"]["entry"]["args"][1]["value"] = "0.02"
        actual = (409 if data["idempotency_key"] == data["retry_idempotency_key"]
                  and (data["owner_id"], data["method"], data["path"]) == (data["retry_owner_id"], data["retry_method"], data["retry_path"])
                  and sha256(first) != sha256(retry) else 200)
    elif kind == "idempotency_scope":
        first_key = (data["first_owner_id"], data["first_method"], data["first_path"], data["first_key"])
        second_key = (data["second_owner_id"], data["second_method"], data["second_path"], data["second_key"])
        actual = "INDEPENDENT" if first_key != second_key else "COLLISION"
    elif kind == "concurrent_publications":
        actual = (data["first_revision"] != data["second_revision"]
                  and data["first_key"] != data["second_key"]
                  and data["parent"] == "rev-parent"
                  and data["owner"] and data["strategy"] == data["first_draft_strategy"] == data["second_draft_strategy"]
                  and data["latest_at_first"] == data["parent"]
                  and data["latest_at_second"] != data["parent"])
    elif kind == "publication_parent":
        valid = (data["owner_id"] == data["draft_owner_id"]
                 and data["strategy_id"] == data["draft_strategy_id"]
                 and data["expected_parent_revision_id"] == data["draft_base_revision_id"])
        if data["expected_parent_revision_id"] is None:
            valid = valid and data["is_first_revision"] and data["root_slot_available"] and not data["parent_exists"]
        else:
            valid = valid and data["parent_exists"] and data["parent_owner_id"] == data["owner_id"] and data["parent_strategy_id"] == data["strategy_id"]
        actual = "ACCEPT" if valid else "parent_revision_conflict"
    elif kind == "typed_expression":
        try:
            actual = expression_type(data["expression"], data["quote_unit"])
        except Invalid:
            actual = "INVALID_INPUT"
    elif kind == "canonical_roundtrip":
        actual = strict_loads(canonical_bytes(data).decode("utf-8")) == data
    else:
        raise Invalid(f"unknown fixture kind: {kind}")
    if actual != expected:
        raise AssertionError(f"{case['id']}: expected {expected!r}, got {actual!r}")


def _strategy_fixture(name: object) -> dict[str, object]:
    if not isinstance(name, str) or name not in STRATEGY_FIXTURES:
        raise Invalid("publication fixture names an unknown StrategySpec")
    return STRATEGY_FIXTURES[name]


def _validate_strategy_path(path: object, strategy: dict[str, object]) -> None:
    match = re.fullmatch(r"/v1/strategies/([^/]+)/revisions", path) if isinstance(path, str) else None
    if match is None or match.group(1) != strategy["strategy_id"]:
        raise Invalid("publication strategy ID must match the strategy path")


def check_record_examples() -> None:
    examples = FIXTURES["record_examples"]
    if set(examples) != set(CONTRACT["record_schemas"]):
        raise AssertionError("each record schema needs one concrete content example")
    for name, example in examples.items():
        validate_record(name, example)
    for variant in FIXTURES.get("record_variants", []):
        validate_record(variant["type"], variant["value"])
    validate_record_bundle(FIXTURES.get("persisted_examples", []))
    check_lifecycle_links()


def _validate_clarification_transition(previous: dict[str, object], resulting: dict[str, object],
                                      clarification: dict[str, object]) -> None:
    prior_content, result_content, content = previous["content"], resulting["content"], clarification["content"]
    if previous["owner_id"] != resulting["owner_id"] or previous["owner_id"] != clarification["owner_id"]:
        raise Invalid("clarification revision links must resolve under the same owner")
    if prior_content["intake_record_id"] != result_content["intake_record_id"]:
        raise Invalid("clarification revisions must remain in one intake lineage")
    if prior_content["requested_job"] != result_content["requested_job"]:
        raise Invalid("clarification cannot change the requested job")
    if content["resulting_revision_id"] != result_content["interpretation_revision_id"]:
        raise Invalid("clarification resulting revision must match its interpretation")
    if not set(prior_content["preserved_restrictions"]) <= set(result_content["preserved_restrictions"]):
        raise Invalid("clarification cannot remove prior interpretation restrictions")
    if set(content["preserved_restrictions"]) != set(result_content["preserved_restrictions"]):
        raise Invalid("clarification restriction snapshot must match its resulting interpretation")
    prior_fields = {field["field_name"]: field for field in prior_content["field_evidence"]}
    result_fields = {field["field_name"]: field for field in result_content["field_evidence"]}
    actual_changes = set()
    for field_name in set(prior_fields) | set(result_fields):
        old, new = prior_fields.get(field_name), result_fields.get(field_name)
        old_meaning = {k: v for k, v in old.items() if k != "interpretation_revision"} if old else None
        new_meaning = {k: v for k, v in new.items() if k != "interpretation_revision"} if new else None
        if old_meaning != new_meaning:
            actual_changes.add(field_name)
    if actual_changes != set(content["changed_fields"]):
        raise Invalid("clarification changed_fields must exactly match changed evidence fields")


def validate_record_bundle(envelopes: list[dict[str, object]]) -> None:
    for envelope in envelopes:
        validate_envelope(envelope)
    by_type = {}
    for envelope in envelopes:
        kind = envelope["record_type"]
        by_type.setdefault(kind, []).append(envelope)
    record_ids = [e["record_id"] for e in envelopes]
    if len(record_ids) != len(set(record_ids)):
        raise Invalid("persisted record IDs must be unique")
    intake_records = {e["record_id"]: e for e in by_type.get("IntakeRequest", [])}
    interpretation_list = by_type.get("PromptInterpretation", [])
    revision_ids = [e["content"]["interpretation_revision_id"] for e in interpretation_list]
    if len(revision_ids) != len(set(revision_ids)):
        raise Invalid("interpretation revision IDs must be unique")
    interpretations = {e["content"]["interpretation_revision_id"]: e for e in interpretation_list}
    clarifications = by_type.get("Clarification", [])
    linked_clarification_ids = set()
    for envelope in envelopes:
        if envelope["record_type"] == "PromptInterpretation":
            content = envelope["content"]
            intake = intake_records.get(content["intake_record_id"])
            if intake is None or intake["owner_id"] != envelope["owner_id"]:
                raise Invalid("interpretation must link to an intake owned by the same principal")
            if content["requested_job"] != intake["content"]["requested_job"]:
                raise Invalid("interpretation job must match its intake request")
            intake_restrictions = set(intake["content"]["restrictions"])
            if not intake_restrictions <= set(content["preserved_restrictions"]):
                raise Invalid("interpretation cannot remove intake restrictions")
            if content["requested_job"] == "CREATE_STRATEGY":
                restriction_items = [item for item in content["field_evidence"] if item["field_name"] == "restrictions"]
                if len(restriction_items) != 1 or restriction_items[0].get("state") != "KNOWN" or restriction_items[0].get("value") != content["preserved_restrictions"]:
                    raise Invalid("strategy interpretation must bind its preserved restrictions as known evidence")
            for item in content["clarification_history"]:
                if sum(item == c["content"] for c in clarifications) != 1:
                    raise Invalid("clarification history must reference one persisted clarification")
                previous = interpretations.get(item["previous_revision_id"])
                if previous is None or previous["owner_id"] != envelope["owner_id"]:
                    raise Invalid("clarification must link to a prior interpretation owned by the same principal")
                previous_content = previous["content"]
                linked = [c for c in clarifications if c["content"] == item]
                if len(linked) != 1:
                    raise Invalid("clarification history must link to a persisted clarification record")
                _validate_clarification_transition(previous, envelope, linked[0])
                linked_clarification_ids.add(linked[0]["record_id"])
                previous_time = parse_utc_timestamp(previous["created_at"])
                clarification_time = parse_utc_timestamp(linked[0]["created_at"])
                result_time = parse_utc_timestamp(envelope["created_at"])
                if not previous_time < clarification_time <= result_time:
                    raise Invalid("clarification revisions must follow their predecessor in record time")
    if linked_clarification_ids != {c["record_id"] for c in clarifications}:
        raise Invalid("every persisted clarification must appear in its resulting interpretation history")
    for envelope in clarifications:
        content = envelope["content"]
        previous = interpretations.get(content["previous_revision_id"])
        resulting = interpretations.get(content["resulting_revision_id"])
        if previous is None or resulting is None or previous["owner_id"] != envelope["owner_id"] or resulting["owner_id"] != envelope["owner_id"]:
            raise Invalid("clarification revision links must resolve under the same owner")
        _validate_clarification_transition(previous, resulting, envelope)
        intake = intake_records.get(previous["content"]["intake_record_id"])
        if intake is None or intake["owner_id"] != envelope["owner_id"]:
            raise Invalid("clarification must resolve to its owner's intake")
        if previous["content"]["requested_job"] != intake["content"]["requested_job"]:
            raise Invalid("clarification job must match its intake request")
        history_count = sum(item == content for item in resulting["content"]["clarification_history"])
        if history_count != 1:
            raise Invalid("persisted clarification must appear exactly once in its resulting history")


def check_lifecycle_links() -> None:
    links = FIXTURES["lifecycle_links"]
    examples = FIXTURES["record_examples"]
    intake = next(e for e in FIXTURES["persisted_examples"]
                  if e["record_type"] == "IntakeRequest" and e["record_id"] == links["intake_record_id"])
    revisions = {e["content"]["interpretation_revision_id"]: e for e in FIXTURES["persisted_examples"]
                 if e["record_type"] == "PromptInterpretation"}
    if set(links["interpretation_revision_ids"]) != set(revisions):
        raise Invalid("lifecycle must link every interpretation revision")
    final_interpretation = revisions[links["interpretation_revision_ids"][-1]]["content"]
    if not any(e["record_type"] == "Clarification" and e["record_id"] == links["clarification_record_id"]
               for e in FIXTURES["persisted_examples"]):
        raise Invalid("lifecycle must link its persisted clarification record")
    draft, request, result, strategy = (examples["StrategyDraft"], examples["PublicationRequest"],
                                       examples["PublicationResult"], examples["StrategySpec"])
    if draft["original_request"] != intake["content"]["original_request"] or draft["interpretation_revision_id"] != final_interpretation["interpretation_revision_id"]:
        raise Invalid("draft must link to the intake request and final interpretation")
    if draft["draft_id"] != request["draft_id"] or draft["strategy_id"] != strategy["strategy_id"] or request["strategy"]["strategy_id"] != strategy["strategy_id"]:
        raise Invalid("draft, publication request, and strategy IDs must agree")
    if links["path_strategy_id"] != strategy["strategy_id"]:
        raise Invalid("publication strategy ID must match the route path")
    if request["expected_parent_revision_id"] != draft["base_revision_id"] or request["expected_parent_revision_id"] != links["parent_revision_id"]:
        raise Invalid("publication parent must match its draft base")
    if links["first_revision"] != (request["expected_parent_revision_id"] is None):
        raise Invalid("null publication parent is only valid for the first revision")
    if request["operation_id"] != result["operation_id"] or result["outcome"] != "PUBLISHED":
        raise Invalid("publication result must acknowledge the exact request")
    if result["content_sha256"] != sha256(request["strategy"]):
        raise Invalid("publication content hash must match the requested StrategySpec")
    if result["manifest_sha256"] != sha256(request["strategy"]["semantic_manifest"]):
        raise Invalid("publication manifest hash must match the requested manifest")
    if request["strategy"] != strategy:
        raise Invalid("publication request must carry the linked strategy example")
    if route({"input": {"interpretation": final_interpretation, "candidate_strategy": strategy}}) != "COMPILED":
        raise Invalid("linked lifecycle interpretation does not validate as the published strategy")


def validate_envelope(envelope: object) -> None:
    required = set(CONTRACT["record_envelope"]["required"])
    if not isinstance(envelope, dict) or set(envelope) != required:
        raise Invalid("persisted record envelope has missing or additional properties")
    record_type = envelope["record_type"]
    if record_type not in CONTRACT["record_schemas"]:
        raise Invalid("unknown record type")
    if envelope["schema_version"] != CONTRACT["schema_versions"][record_type]:
        raise Invalid("record schema version does not match type")
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    for field in ("record_id", "owner_id", "operation_id"):
        if not isinstance(envelope[field], str) or not re.fullmatch(uuid_pattern, envelope[field]):
            raise Invalid(f"{field} must be a UUID")
    parse_utc_timestamp(envelope["created_at"])
    validate_record(record_type, envelope["content"])


def must_reject(label: str, strategy: dict[str, object]) -> None:
    try:
        validate_strategy(strategy)
    except (Invalid, TypeError, KeyError):
        return
    raise AssertionError(f"invalid mutation was accepted: {label}")


def must_reject_record(label: str, name: str, record: object) -> None:
    try:
        validate_record(name, record)
    except (Invalid, TypeError, KeyError):
        return
    raise AssertionError(f"invalid record mutation was accepted: {label}")


def must_reject_action(label: str, action: object) -> None:
    try:
        action()
    except (Invalid, TypeError, KeyError, IndexError):
        return
    raise AssertionError(f"invalid mutation was accepted: {label}")


def main() -> int:
    if set(CONTRACT["operator_signatures"]) != set(CONTRACT["operators"]):
        raise AssertionError("operator names and machine signatures differ")
    check_record_examples()
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
    hidden_history_type = copy.deepcopy(STRATEGY)
    hidden_history_type["entry"] = {"op": "and", "args": [
        STRATEGY["entry"],
        {"op": "lag", "value": STRATEGY["entry"], "buckets": 1}]}
    hidden_history_type["warmup_buckets"] = 4
    must_reject("Boolean history operator hidden inside Boolean tree", hidden_history_type)
    unsupported_branch = copy.deepcopy(STRATEGY)
    unsupported_branch["entry"]["args"][0] = {"op": "future_price", "lookback_buckets": 1}
    must_reject("unsupported hidden operation", unsupported_branch)
    bad_history = copy.deepcopy(STRATEGY)
    bad_history["entry"]["args"][0]["lookback_buckets"] = 289
    must_reject("lookback over contract bound", bad_history)
    bad_identity = copy.deepcopy(STRATEGY)
    bad_identity["strategy_id"] = ""
    must_reject("empty strategy identity", bad_identity)
    bad_identity["strategy_id"] = None
    must_reject("non-string strategy identity", bad_identity)
    bad_binding = copy.deepcopy(STRATEGY)
    bad_binding["market"]["research_binding"]["evidence_class"] = "MADE_UP"
    must_reject("nested research binding enum", bad_binding)
    bad_binding_record = copy.deepcopy(FIXTURES["record_examples"]["ResearchBinding"])
    bad_binding_record["evidence_class"] = "MADE_UP"
    must_reject_record("standalone research binding enum", "ResearchBinding", bad_binding_record)
    for field, invalid_value in (("base_decimals", -1), ("quote_decimals", 256),
                                 ("token_order", []), ("qualification", "QUALIFIED")):
        bad_binding_record = copy.deepcopy(FIXTURES["record_examples"]["ResearchBinding"])
        bad_binding_record[field] = invalid_value
        must_reject_record(f"standalone research binding {field}", "ResearchBinding", bad_binding_record)
        bad_binding_strategy = copy.deepcopy(STRATEGY)
        bad_binding_strategy["market"]["research_binding"] = bad_binding_record
        must_reject(f"nested research binding {field}", bad_binding_strategy)
    bad_binding_record = copy.deepcopy(FIXTURES["record_examples"]["ResearchBinding"])
    bad_binding_record.update(chain_id=None, evidence_class="QUALIFIED_SOURCE", qualification="QUALIFIED")
    must_reject_record("standalone null-chain research binding cannot be qualified",
                       "ResearchBinding", bad_binding_record)
    bad_binding_strategy = copy.deepcopy(STRATEGY)
    bad_binding_strategy["market"]["research_binding"] = bad_binding_record
    must_reject("nested null-chain research binding cannot be qualified", bad_binding_strategy)
    bad_invalidation = copy.deepcopy(STRATEGY)
    bad_invalidation["invalidation"]["source_ref"] = {"untrusted": "source"}
    must_reject("not-requested invalidation requires source reference string", bad_invalidation)
    authority = copy.deepcopy(STRATEGY)
    authority["execution_permission"] = {"state": "GRANTED", "mandate_ref": "fixture-mandate"}
    must_reject("draft compiler cannot grant permission", authority)
    decimal_variant = copy.deepcopy(STRATEGY)
    decimal_variant["sizing"]["amount"] = 100.0
    must_reject("JSON float in decimal field", decimal_variant)
    strategy_path = ROOT / "fixtures/complete-strategy.json"
    assert load_json(strategy_path) == STRATEGY
    duplicate_strategy = strategy_path.read_text(encoding="utf-8").replace(
        "{", '{"strategy_id":"HIDDEN-INVALID-ID",', 1)
    with tempfile.TemporaryDirectory() as directory:
        duplicate_path = Path(directory) / "complete-strategy.json"
        duplicate_path.write_text(duplicate_strategy, encoding="utf-8")
        must_reject_action("duplicate strategy_id through fixture file loader",
                           lambda: load_json(duplicate_path))

    for case_id in ("route-clarification", "route-empty-meaning", "route-pending-exit-proposal"):
        bad_case = copy.deepcopy(next(case for case in FIXTURES["cases"] if case["id"] == case_id))
        bad_case["result"]["findings"][0]["detail"] = "Continue."
        must_reject_action(f"{case_id} generic clarification is not a question", lambda case=bad_case: route(case))
        bad_case = copy.deepcopy(next(case for case in FIXTURES["cases"] if case["id"] == case_id))
        bad_case["result"]["findings"][0]["path"] = "/field_evidence"
        must_reject_action(f"{case_id} clarification field is unbound", lambda case=bad_case: route(case))

    observation_as_exit = copy.deepcopy(STRATEGY)
    observation_as_exit["exit"] = {"op": "observation_period", "buckets": 12}
    must_reject("observation period is not an exit rule", observation_as_exit)

    nested_history = copy.deepcopy(STRATEGY)
    nested_history["entry"] = {"op": "gt", "args": [
        {"op": "lag", "value": {"op": "price_return", "lookback_buckets": 3}, "buckets": 2},
        {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}
    nested_history["warmup_buckets"] = 4
    must_reject("nested dependency underdeclares warmup", nested_history)
    nested_history["warmup_buckets"] = 5
    validate_strategy(nested_history)
    nested_history["exit"] = {"op": "gt", "args": [
        {"op": "mean", "value": {"op": "price_return", "lookback_buckets": 2}, "buckets": 4},
        {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}
    nested_history["invalidation"] = {"op": "gt", "args": [
        {"op": "sum", "value": {"op": "price_return", "lookback_buckets": 1}, "buckets": 3},
        {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}
    validate_strategy(nested_history)
    nested_history["warmup_buckets"] = 4
    must_reject("warmup omits history required by exit", nested_history)
    oversized_history = copy.deepcopy(STRATEGY)
    oversized_history["entry"] = {"op": "gt", "args": [
        {"op": "lag", "value": {"op": "price_return", "lookback_buckets": 288}, "buckets": 1},
        {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}
    oversized_history["warmup_buckets"] = 288
    must_reject("nested dependency exceeds maximum warmup", oversized_history)

    bad_evidence = copy.deepcopy(FIXTURES["record_examples"]["PromptInterpretation"])
    bad_evidence["field_evidence"][0]["state"] = "MISSING"
    must_reject_record("MISSING evidence carries a guessed value", "PromptInterpretation", bad_evidence)
    bad_evidence = copy.deepcopy(FIXTURES["record_examples"]["PromptInterpretation"])
    bad_evidence["field_evidence"][0]["state"] = "CONFLICTING"
    bad_evidence["field_evidence"][0]["conflicts"] = [
        {"value": "0.01", "source_ref": "source-a"}, {"value": "0.02", "source_ref": "source-b"}]
    must_reject_record("CONFLICTING evidence carries a selected value", "PromptInterpretation", bad_evidence)
    bad_evidence = copy.deepcopy(FIXTURES["record_examples"]["PromptInterpretation"])
    bad_evidence["field_evidence"][0]["state"] = "CONFLICTING"
    bad_evidence["field_evidence"][0].pop("value")
    bad_evidence["field_evidence"][0]["conflicts"] = [{"value": "0.01", "source_ref": "source-a"}]
    must_reject_record("CONFLICTING evidence lacks competing sources", "PromptInterpretation", bad_evidence)
    standalone = copy.deepcopy(FIXTURES["record_examples"]["FieldEvidence"])
    standalone["state"] = "MISSING"
    must_reject_record("standalone MISSING evidence cannot retain value", "FieldEvidence", standalone)
    standalone = copy.deepcopy(FIXTURES["record_examples"]["FieldEvidence"])
    standalone.pop("value")
    must_reject_record("standalone KNOWN evidence requires value", "FieldEvidence", standalone)
    standalone = copy.deepcopy(FIXTURES["record_examples"]["FieldEvidence"])
    standalone["state"] = "CONFLICTING"
    standalone.pop("value")
    must_reject_record("standalone CONFLICTING evidence requires alternatives", "FieldEvidence", standalone)
    bad_evidence = copy.deepcopy(FIXTURES["record_examples"]["PromptInterpretation"])
    bad_evidence["field_evidence"][0]["origin"] = "AGENT_PROPOSED"
    bad_evidence["field_evidence"][0].pop("adoption", None)
    must_reject_record("proposed consequential field lacks adoption", "PromptInterpretation", bad_evidence)
    bad_evidence = copy.deepcopy(FIXTURES["record_examples"]["PromptInterpretation"])
    bad_evidence["owner_id"] = "caller-owner"
    must_reject_record("client interpretation cannot set owner", "PromptInterpretation", bad_evidence)
    bad_request = copy.deepcopy(FIXTURES["record_examples"]["IntakeRequest"])
    bad_request["owner_id"] = "caller-owner"
    must_reject_record("client intake cannot set owner authority", "IntakeRequest", bad_request)
    bad_result = copy.deepcopy(FIXTURES["record_examples"]["Outcome"])
    del bad_result["code"]
    must_reject_record("result requires stable code", "Outcome", bad_result)
    bad_publication = copy.deepcopy(FIXTURES["record_examples"]["PublicationResult"])
    bad_publication["revision_id"] = ""
    must_reject_record("published result requires nonempty revision ID", "PublicationResult", bad_publication)
    parent_conflict = copy.deepcopy(next(v["value"] for v in FIXTURES["record_variants"]
                                         if v["type"] == "PublicationResult"
                                         and v["value"]["code"] == "parent_revision_conflict"))
    validate_record("PublicationResult", parent_conflict)
    validate_record("PublicationResult", FIXTURES["record_examples"]["PublicationResult"])
    bad_publication = copy.deepcopy(parent_conflict)
    bad_publication["retry"] = "SAFE_SAME_KEY"
    must_reject_record("parent conflict cannot be safe to retry", "PublicationResult", bad_publication)
    bad_publication = copy.deepcopy(parent_conflict)
    bad_publication["findings"][0]["code"] = "idempotency_key_reused"
    must_reject_record("parent conflict finding must match its result code", "PublicationResult", bad_publication)
    for outcome_name in ("NEEDS_CLARIFICATION", "UNSUPPORTED", "UNRESOLVED"):
        bad_outcome = copy.deepcopy(next(v["value"] for v in FIXTURES["record_variants"]
                                         if v["type"] == "Outcome" and v["value"]["outcome"] == outcome_name))
        bad_outcome["findings"][0]["path"] = ""
        must_reject_record(f"{outcome_name} outcome needs a finding path", "Outcome", bad_outcome)
        bad_outcome["findings"][0]["path"] = "/field_evidence/entry"
        bad_outcome["findings"][0]["detail"] = ""
        must_reject_record(f"{outcome_name} outcome needs a finding detail", "Outcome", bad_outcome)
        bad_outcome["findings"][0]["detail"] = "Actionable detail."
        bad_outcome["intake_record_id"] = None
        must_reject_record(f"{outcome_name} outcome links to intake", "Outcome", bad_outcome)
        if outcome_name == "NEEDS_CLARIFICATION":
            bad_outcome = copy.deepcopy(next(v["value"] for v in FIXTURES["record_variants"]
                                             if v["type"] == "Outcome" and v["value"]["outcome"] == outcome_name))
            bad_outcome["findings"][0]["detail"] = "Continue."
            must_reject_record("clarification Outcome rejects generic Continue", "Outcome", bad_outcome)
            bad_outcome["findings"][0]["detail"] = "Which entry threshold should apply?"
            bad_outcome["findings"][0]["path"] = "/field_evidence"
            must_reject_record("clarification Outcome requires a bound field path", "Outcome", bad_outcome)
    bad_publication = copy.deepcopy(next(v["value"] for v in FIXTURES["record_variants"]
                                         if v["type"] == "PublicationResult" and v["value"]["outcome"] == "INVALID_INPUT"))
    bad_publication["findings"] = []
    must_reject_record("publication error requires a finding", "PublicationResult", bad_publication)
    bad_publication["findings"] = [{"code": "unit_mismatch", "path": "", "detail": "Invalid unit."}]
    must_reject_record("publication error finding needs JSON Pointer", "PublicationResult", bad_publication)
    bad_publication["findings"][0]["path"] = "/strategy/~2"
    must_reject_record("publication error finding needs a valid JSON Pointer", "PublicationResult", bad_publication)
    bad_publication = copy.deepcopy(next(v["value"] for v in FIXTURES["record_variants"]
                                         if v["type"] == "PublicationResult" and v["value"]["outcome"] == "UNRESOLVED"))
    bad_publication["findings"] = []
    must_reject_record("unresolved publication requires a dependency finding", "PublicationResult", bad_publication)
    bad_envelope = copy.deepcopy(FIXTURES["persisted_examples"][0])
    bad_envelope["schema_version"] = "p02.unknown/99"
    try:
        validate_envelope(bad_envelope)
    except Invalid:
        pass
    else:
        raise AssertionError("unknown record schema version was accepted")
    bad_envelope = copy.deepcopy(FIXTURES["persisted_examples"][0])
    bad_envelope["created_at"] = "2026-99-99T99:99:99Z"
    must_reject_action("impossible persisted timestamp", lambda: validate_envelope(bad_envelope))
    must_reject_action("24-hour persisted timestamp", lambda: parse_utc_timestamp("2026-10-06T24:00:00Z"))
    assert parse_utc_timestamp("2026-10-06T10:00:01Z") < parse_utc_timestamp("2026-10-06T10:00:01.1Z")
    assert parse_utc_timestamp("2026-10-06T10:00:01.0000001Z") < parse_utc_timestamp("2026-10-06T10:00:01.0000002Z")
    bad_links = copy.deepcopy(FIXTURES["persisted_examples"])
    bad_links[-1]["content"]["intake_record_id"] = "40000000-0000-4000-8000-000000000004"
    try:
        validate_record_bundle(bad_links)
    except Invalid:
        pass
    else:
        raise AssertionError("interpretation with an unknown intake revision link was accepted")
    bad_links = copy.deepcopy(FIXTURES["persisted_examples"])
    bad_links[-1]["content"]["preserved_restrictions"] = []
    try:
        validate_record_bundle(bad_links)
    except Invalid:
        pass
    else:
        raise AssertionError("persisted interpretation removed intake restrictions")
    bad_links = copy.deepcopy(FIXTURES["persisted_examples"])
    bad_links[0]["content"]["requested_job"] = "OBSERVE_FORWARD"
    must_reject_action("interpretation cannot change the intake's requested job",
                       lambda: validate_record_bundle(bad_links))
    bad_links = copy.deepcopy(FIXTURES["persisted_examples"])
    clarification = next(e for e in bad_links if e["record_type"] == "Clarification")
    clarification["content"]["changed_fields"] = ["entry"]
    resulting = next(e for e in bad_links if e["record_type"] == "PromptInterpretation"
                     and e["content"]["interpretation_revision_id"] == clarification["content"]["resulting_revision_id"])
    resulting["content"]["clarification_history"][0]["changed_fields"] = ["entry"]
    must_reject_action("clarification changed_fields must match persisted evidence changes",
                       lambda: validate_record_bundle(bad_links))
    bad_links = copy.deepcopy(FIXTURES["persisted_examples"])
    resulting = next(e for e in bad_links if e["record_type"] == "PromptInterpretation"
                     and e["content"]["interpretation_revision_id"] == "interp-fixture-2")
    item = resulting["content"]["clarification_history"][0]
    resulting["content"]["clarification_history"].append(copy.deepcopy(item))
    must_reject_action("persisted clarification must appear exactly once", lambda: validate_record_bundle(bad_links))
    bad_links = copy.deepcopy(FIXTURES["persisted_examples"])
    for envelope in bad_links:
        if envelope["record_type"] == "Clarification":
            envelope["content"]["previous_revision_id"] = "does-not-exist"
        elif envelope["record_type"] == "PromptInterpretation" and envelope["content"]["interpretation_revision_id"] == "interp-fixture-2":
            envelope["content"]["clarification_history"][0]["previous_revision_id"] = "does-not-exist"
    try:
        validate_record_bundle(bad_links)
    except Invalid:
        pass
    else:
        raise AssertionError("persisted clarification accepted an unknown prior revision")
    bad_links = copy.deepcopy(FIXTURES["persisted_examples"])
    prior = next(e for e in bad_links if e["record_type"] == "PromptInterpretation"
                 and e["content"]["interpretation_revision_id"] == "interp-fixture-1")["content"]
    prior["preserved_restrictions"].append("no market orders")
    next(f for f in prior["field_evidence"] if f["field_name"] == "restrictions")["value"].append("no market orders")
    final = next(e for e in bad_links if e["record_type"] == "PromptInterpretation"
                 and e["content"]["interpretation_revision_id"] == "interp-fixture-2")["content"]
    final["clarification_history"] = []
    must_reject_action("clarification history cannot be omitted to drop a restriction",
                       lambda: validate_record_bundle(bad_links))
    bad_links = copy.deepcopy(FIXTURES["persisted_examples"])
    other_intake = copy.deepcopy(bad_links[0])
    other_intake["record_id"] = "90000000-0000-4000-8000-000000000001"
    other_intake["content"]["requested_job"] = "OBSERVE_FORWARD"
    other_intake["content"]["original_request"] = "Observe forward only. Do not create a strategy."
    bad_links.append(other_intake)
    final = next(e for e in bad_links if e["record_type"] == "PromptInterpretation"
                 and e["content"]["interpretation_revision_id"] == "interp-fixture-2")["content"]
    final["intake_record_id"] = other_intake["record_id"]
    must_reject_action("clarification cannot switch intake lineage or requested job",
                       lambda: validate_record_bundle(bad_links))
    unresolved_route = copy.deepcopy(next(c for c in FIXTURES["cases"] if c["id"] == "route-unresolved"))
    unresolved_route.pop("result")
    must_reject_action("unresolved route requires a detailed outcome", lambda: route(unresolved_route))
    unresolved_route = copy.deepcopy(next(c for c in FIXTURES["cases"] if c["id"] == "route-unresolved"))
    unresolved_route["result"]["findings"][0]["detail"] = ""
    must_reject_action("unresolved route requires a dependency detail", lambda: route(unresolved_route))
    unresolved_route = copy.deepcopy(next(c for c in FIXTURES["cases"] if c["id"] == "route-unresolved"))
    unresolved_route["result"]["intake_record_id"] = "40000000-0000-4000-8000-000000000004"
    must_reject_action("unresolved route preserves request linkage", lambda: route(unresolved_route))
    unresolved_route = copy.deepcopy(next(c for c in FIXTURES["cases"] if c["id"] == "route-unresolved"))
    unresolved_route["input"]["candidate_strategy"] = copy.deepcopy(STRATEGY)
    must_reject_action("unresolved route omits an unavailable strategy", lambda: route(unresolved_route))
    unknown_strategy = copy.deepcopy(next(c for c in FIXTURES["cases"] if c["kind"] == "idempotency"))
    unknown_strategy["input"]["retry_strategy_fixture"] = "does-not-exist"
    must_reject_action("idempotency retry resolves declared strategy fixture",
                       lambda: check_fixture(unknown_strategy))
    unknown_strategy = copy.deepcopy(next(c for c in FIXTURES["cases"] if c["kind"] == "idempotency"))
    unknown_strategy["input"]["strategy_fixture"] = "does-not-exist"
    must_reject_action("idempotency first request resolves declared strategy fixture",
                       lambda: check_fixture(unknown_strategy))
    wrong_path = copy.deepcopy(next(c for c in FIXTURES["cases"] if c["kind"] == "idempotency"))
    wrong_path["input"]["path"] = "/v1/strategies/other/revisions"
    must_reject_action("idempotency strategy matches first request path", lambda: check_fixture(wrong_path))
    wrong_path = copy.deepcopy(next(c for c in FIXTURES["cases"] if c["kind"] == "idempotency"))
    wrong_path["input"]["retry_path"] = "/v1/strategies/other/revisions"
    must_reject_action("idempotency strategy matches retry path", lambda: check_fixture(wrong_path))

    print(f"PASS: {len(FIXTURES['cases'])} fixtures, {len(FIXTURES['record_examples'])} record examples, valid strategy, canonical identity, and record/strategy rejection mutations")
    print("LIMIT: in-memory contract checks only; no server, storage, concurrency, provider, or production-cost claim")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, Invalid, KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
