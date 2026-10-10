"""Bounded evaluation of one immutable compiled revision on controlled clock and data.

The evaluator reuses the accepted P06 compiler (`evaluate_expression`) without
reimplementing it. It never fills, aligns or gaps data and never executes
generated Python. A missing or UNKNOWN required observation is INELIGIBLE, not a
no-signal or a zero.
"""

from __future__ import annotations

from edge_os_api.admission.types import parse_utc
from edge_os_api.strategies import compiler as strategy_compiler

from edge_os_api.execution.types import (
    EvaluationInputs,
    EvaluationOutcome,
    FrozenRevision,
    InputObservation,
    RuleEvaluation,
)

_RULES = ("entry", "exit", "invalidation")
_OR_TRUE = strategy_compiler.Truth.TRUE
_OR_FALSE = strategy_compiler.Truth.FALSE


def _to_observation(row: InputObservation | None, binding_id: str) -> strategy_compiler.Observation | None:
    if row is None:
        return None
    return strategy_compiler.Observation(
        value=row.value,
        bucket_end=parse_utc(row.bucket_end),
        market_binding_id=binding_id,
        qualified=row.qualified,
        available_at=parse_utc(row.available_at) if row.available_at is not None else None,
        reasons=tuple(row.reasons),
    )


def _context(revision: FrozenRevision, inputs: EvaluationInputs) -> strategy_compiler.EvaluationContext:
    binding_id = revision.market_binding_id
    prices = [_to_observation(row, binding_id) for row in inputs.prices]
    volumes = [_to_observation(row, binding_id) for row in inputs.quote_volumes]
    schedule = [parse_utc(value) for value in inputs.scheduled_bucket_ends]
    return strategy_compiler.EvaluationContext(
        prices, volumes, schedule, binding_id, inputs.observed_at(), inputs.position)


def _rule_state(revision: FrozenRevision, name: str, context: strategy_compiler.EvaluationContext) -> RuleEvaluation:
    node = revision.strategy[name]
    if name == "invalidation" and isinstance(node, dict) and node.get("state") == "NOT_REQUESTED":
        return RuleEvaluation(rule=name, state="NOT_REQUESTED", reasons=[])
    result = strategy_compiler.evaluate_expression(node, revision.strategy["market"], context)
    return RuleEvaluation(rule=name, state=result.state, reasons=list(result.reasons))


def _merge(*groups: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for group in groups:
        for reason in group:
            seen.setdefault(reason, None)
    return list(seen)


def evaluate(revision: FrozenRevision, inputs: EvaluationInputs) -> EvaluationOutcome:
    """Return SIGNAL, NO_SIGNAL or INELIGIBLE for the revision and controlled inputs."""
    inputs_hash = inputs.identity()
    try:
        context = _context(revision, inputs)
        rule_results = [_rule_state(revision, name, context) for name in _RULES]
    except strategy_compiler.CompilerError as error:
        return EvaluationOutcome(
            status="INELIGIBLE", operation=None, reasons=[f"EVALUATION_ERROR:{error.code}"],
            rule_results=[], inputs_hash=inputs_hash)

    states = {item.rule: item for item in rule_results}
    if not inputs.position_open:
        entry = states["entry"]
        if entry.state == _OR_TRUE:
            return EvaluationOutcome(status="SIGNAL", operation="ENTRY", reasons=entry.reasons,
                                     rule_results=rule_results, inputs_hash=inputs_hash)
        if entry.state == _OR_FALSE:
            return EvaluationOutcome(status="NO_SIGNAL", operation=None, reasons=entry.reasons,
                                     rule_results=rule_results, inputs_hash=inputs_hash)
        return EvaluationOutcome(
            status="INELIGIBLE", operation=None,
            reasons=_merge(entry.reasons, ["ENTRY_NOT_EVALUABLE"]) or ["ENTRY_NOT_EVALUABLE"],
            rule_results=rule_results, inputs_hash=inputs_hash)

    exit_state = states["exit"]
    invalidation_state = states["invalidation"]
    invalidation_value = invalidation_state.state if invalidation_state.state in (_OR_TRUE, _OR_FALSE) else (
        None if invalidation_state.state == "NOT_REQUESTED" else strategy_compiler.Truth.UNKNOWN)
    values = (exit_state.state, invalidation_value)
    if _OR_TRUE in values:
        return EvaluationOutcome(status="SIGNAL", operation="EXIT",
                                 reasons=_merge(exit_state.reasons, invalidation_state.reasons),
                                 rule_results=rule_results, inputs_hash=inputs_hash)
    if all(value == _OR_FALSE for value in values):
        return EvaluationOutcome(status="NO_SIGNAL", operation=None,
                                 reasons=_merge(exit_state.reasons, invalidation_state.reasons),
                                 rule_results=rule_results, inputs_hash=inputs_hash)
    return EvaluationOutcome(
        status="INELIGIBLE", operation=None,
        reasons=_merge(exit_state.reasons, invalidation_state.reasons, ["EXIT_NOT_EVALUABLE"])
        or ["EXIT_NOT_EVALUABLE"],
        rule_results=rule_results, inputs_hash=inputs_hash)
