"""Deterministic routing and minimal compilation (P02 outcome rules).

The router returns one explicit outcome. It never guesses a missing value, drops a restriction or builds a
strategy from unadopted meaning. Strategy validation uses the frozen P02 validators.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from . import p02
from .interpreter import FixtureInterpreter, Scenario, clarification_text

UNSUPPORTED_JOBS = {"SIMULATE", "OBSERVE_FORWARD", "REQUEST_LIVE"}
INVESTIGATION_FIELDS = ["market", "restrictions"]
CODES = p02.CONTRACT["result_codes"]


@dataclass
class Routed:
    outcome: str
    stage: str
    findings: list[dict[str, str]] = field(default_factory=list)
    retry: str = "NOT_RETRYABLE"
    strategy: dict[str, Any] | None = None
    targets: list[str] = field(default_factory=list)

    @property
    def code(self) -> str:
        return CODES[self.outcome]


def _finding(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def _invalid(path: str, detail: str, code: str = "invalid_value") -> Routed:
    return Routed("INVALID_INPUT", "VALIDATION", [_finding(code, path, detail)])


def required_fields(job: str) -> list[str]:
    return list(p02.CREATE_STRATEGY_FIELDS) if job == "CREATE_STRATEGY" else list(INVESTIGATION_FIELDS)


def build_strategy(strategy_id: str, values: dict[str, Any]) -> dict[str, Any]:
    expressions = [values["entry"], values["exit"]]
    if not (isinstance(values["invalidation"], dict) and values["invalidation"].get("state") == "NOT_REQUESTED"):
        expressions.append(values["invalidation"])
    strategy: dict[str, Any] = {"schema_version": p02.CONTRACT["identity"]["strategy_schema"],
                                "strategy_id": strategy_id, "domain": "SPOT"}
    for name in p02.CREATE_STRATEGY_FIELDS:
        if name != "restrictions":
            strategy[name] = copy.deepcopy(values[name])
    strategy["execution_permission"] = {"state": "NOT_GRANTED", "mandate_ref": None}
    strategy["warmup_buckets"] = max(p02.required_history(expression) for expression in expressions)
    strategy["semantic_manifest"] = dict(p02.MANIFEST)
    return strategy


def route(intake: dict[str, Any], interp: dict[str, Any], interpreter: FixtureInterpreter,
          scenario: Scenario | None, strategy_id: str) -> Routed:
    try:
        p02.validate_record("PromptInterpretation", interp)
    except (p02.Invalid, KeyError, TypeError) as error:
        return _invalid("/", f"The interpretation is not a valid record: {error}", "invalid_interpretation")
    if interp["syntax_status"] == "INVALID":
        return _invalid("/", "The interpreter returned a malformed representation. This is a system failure, "
                        "not a verdict on the request.", "malformed_interpretation")
    job = interp["requested_job"]
    restrictions = interp["preserved_restrictions"]
    for index, restriction in enumerate(restrictions):
        if restriction not in p02.SUPPORTED_RESTRICTIONS:
            return Routed("UNSUPPORTED", "INTERPRETATION", [_finding(
                "missing_capability", f"/preserved_restrictions/{index}",
                f"The restriction {restriction!r} cannot be represented. It is kept exactly as written and "
                "blocks compilation.")])
    if interp["meaning_status"] == "UNSUPPORTED":
        capability = (scenario.missing_capability if scenario else None) or "unsupported_meaning"
        return Routed("UNSUPPORTED", "INTERPRETATION", [_finding(
            "missing_capability", "/meaning_status",
            f"The meaning is clear but needs the capability {capability!r}, which is not available. "
            "The original request is kept and nothing was substituted.")])
    if job in UNSUPPORTED_JOBS:
        return Routed("UNSUPPORTED", "INTERPRETATION", [_finding(
            "missing_capability", "/requested_job",
            f"The requested job {job} has no workflow in this build. The request is kept as written.")])

    required = required_fields(job)
    evidence = interp["field_evidence"]
    by_name = {item["field_name"]: item for item in evidence}
    if job == "CREATE_STRATEGY" and any(name not in required for name in by_name):
        return _invalid("/field_evidence", "A field is not part of the strategy compile route.", "unknown_field")
    bound = by_name.get("restrictions")
    if bound is not None and bound["state"] == "KNOWN" and bound["value"] != restrictions:
        return _invalid("/field_evidence/restrictions", "Saved restrictions differ from the bound evidence.",
                        "restriction_mismatch")

    targets = [name for name in required if name not in by_name]
    targets += [name for name in required if name in by_name and (
        by_name[name]["state"] in {"MISSING", "CONFLICTING"}
        or (by_name[name].get("origin") in {"AGENT_PROPOSED", "APPLICATION_CONFIGURED"}
            and by_name[name].get("adoption") != "ADOPTED"))]
    if targets:
        findings = [_finding("conflicting_field" if by_name.get(name, {}).get("state") == "CONFLICTING"
                             else "missing_field", f"/field_evidence/{name}",
                             clarification_text(intake, interpreter, by_name.get(name), name)) for name in targets]
        return Routed("NEEDS_CLARIFICATION", "INTERPRETATION", findings, targets=targets)

    if job == "CREATE_STRATEGY":
        values = {name: item["value"] for name, item in by_name.items()}
        try:
            p02.validate_compile_fields(values)
        except (p02.Invalid, KeyError, TypeError) as error:
            return _invalid("/field_evidence", f"A supplied field is not valid: {error}", "invalid_field")
    if job != "CREATE_STRATEGY" or interp["evidence_readiness"] == "UNRESOLVED":
        return Routed("UNRESOLVED", "INTERPRETATION", [_finding(
            "missing_dependency", "/evidence_readiness",
            "No research run exists in this build, so the claim is untested. The adopted configuration is kept. "
            "No signal and no strategy were created.")])

    strategy = build_strategy(strategy_id, values)
    try:
        p02.validate_strategy(strategy)
    except (p02.Invalid, KeyError, TypeError) as error:
        return _invalid("/field_evidence", f"The adopted meaning does not form a valid strategy: {error}",
                        "invalid_strategy")
    for restriction in restrictions:
        rule = p02.SUPPORTED_RESTRICTIONS[restriction]
        actual: Any = strategy
        for part in rule["field"].split("."):
            actual = actual[part]
        if actual != rule["equals"]:
            return _invalid(f"/preserved_restrictions/{restrictions.index(restriction)}",
                            f"The strategy does not honour the restriction {restriction!r}.", "restriction_violated")
    return Routed("COMPILED", "COMPILATION", strategy=strategy)
