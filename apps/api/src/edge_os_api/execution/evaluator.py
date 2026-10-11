"""Bounded evaluation of one immutable compiled revision on controlled clock and data.

The evaluator reuses the accepted P06 compiler (`evaluate_expression`) without
reimplementing it. It never fills, aligns or gaps data and never executes
generated Python. A missing or UNKNOWN required observation is INELIGIBLE, not a
no-signal or a zero.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from edge_os_api.admission.types import parse_utc
from edge_os_api.strategies import compiler as strategy_compiler

from edge_os_api.execution.types import (
    EvaluationInputs,
    EvaluationOutcome,
    FrozenRevision,
    InputObservation,
    RuleEvaluation,
    canonical_hash,
)

_RULES = ("entry", "exit", "invalidation")
_TRUE = strategy_compiler.Truth.TRUE
_FALSE = strategy_compiler.Truth.FALSE
_UNKNOWN = strategy_compiler.Truth.UNKNOWN


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


def _context(strategy: dict[str, Any], revision: FrozenRevision,
             inputs: EvaluationInputs) -> strategy_compiler.EvaluationContext:
    binding_id = revision.market_binding_id
    prices = [_to_observation(row, binding_id) for row in inputs.prices]
    volumes = [_to_observation(row, binding_id) for row in inputs.quote_volumes]
    schedule = [parse_utc(value) for value in inputs.scheduled_bucket_ends]
    return strategy_compiler.EvaluationContext(
        prices, volumes, schedule, binding_id, inputs.observed_at(), inputs.position)


def _rule_state(strategy: dict[str, Any], name: str,
                context: strategy_compiler.EvaluationContext) -> RuleEvaluation:
    node = strategy[name]
    if name == "invalidation" and isinstance(node, dict) and node.get("state") == "NOT_REQUESTED":
        return RuleEvaluation(rule=name, state="NOT_REQUESTED", reasons=[])
    result = strategy_compiler.evaluate_expression(node, strategy["market"], context)
    return RuleEvaluation(rule=name, state=result.state, reasons=list(result.reasons))


def _merge(*groups: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for group in groups:
        for reason in group:
            seen.setdefault(reason, None)
    return list(seen)


def _flat_outcome(entry: RuleEvaluation, rule_results: list[RuleEvaluation],
                  inputs_hash: str) -> EvaluationOutcome:
    if entry.state == _TRUE:
        return EvaluationOutcome(status="SIGNAL", operation="ENTRY", reasons=entry.reasons,
                                 rule_results=rule_results, inputs_hash=inputs_hash)
    if entry.state == _FALSE:
        return EvaluationOutcome(status="NO_SIGNAL", operation=None, reasons=entry.reasons,
                                 rule_results=rule_results, inputs_hash=inputs_hash)
    return EvaluationOutcome(
        status="INELIGIBLE", operation=None,
        reasons=_merge(entry.reasons, ["ENTRY_NOT_EVALUABLE"]) or ["ENTRY_NOT_EVALUABLE"],
        rule_results=rule_results, inputs_hash=inputs_hash)


def _open_outcome(exit_state: RuleEvaluation, invalidation: RuleEvaluation,
                  rule_results: list[RuleEvaluation], inputs_hash: str) -> EvaluationOutcome:
    reasons = _merge(exit_state.reasons, invalidation.reasons)
    requested = invalidation.state != "NOT_REQUESTED"
    values = [exit_state.state, invalidation.state] if requested else [exit_state.state]
    if _TRUE in values:
        return EvaluationOutcome(status="SIGNAL", operation="EXIT", reasons=reasons,
                                 rule_results=rule_results, inputs_hash=inputs_hash)
    if all(value == _FALSE for value in values):
        return EvaluationOutcome(status="NO_SIGNAL", operation=None, reasons=reasons,
                                 rule_results=rule_results, inputs_hash=inputs_hash)
    return EvaluationOutcome(
        status="INELIGIBLE", operation=None,
        reasons=_merge(reasons, ["EXIT_NOT_EVALUABLE"]) or ["EXIT_NOT_EVALUABLE"],
        rule_results=rule_results, inputs_hash=inputs_hash)


def evaluate(revision: FrozenRevision, inputs: EvaluationInputs) -> EvaluationOutcome:
    """Return SIGNAL, NO_SIGNAL or INELIGIBLE for the revision and controlled inputs."""
    inputs_hash = inputs.identity()
    strategy = revision.strategy
    # The declared identity must match the exact bytes actually evaluated. The
    # frozen revision stores canonical bytes, so this defends against any future
    # refactor that would let the meaning drift from its identity.
    if canonical_hash(strategy) != revision.content_hash:
        return EvaluationOutcome(
            status="INELIGIBLE", operation=None, reasons=["REVISION_INTEGRITY_MISMATCH"],
            rule_results=[], inputs_hash=inputs_hash)
    try:
        context = _context(strategy, revision, inputs)
        rule_results = [_rule_state(strategy, name, context) for name in _RULES]
    except strategy_compiler.CompilerError as error:
        return EvaluationOutcome(
            status="INELIGIBLE", operation=None, reasons=[f"EVALUATION_ERROR:{error.code}"],
            rule_results=[], inputs_hash=inputs_hash)

    states = {item.rule: item for item in rule_results}
    if not inputs.position_open:
        return _flat_outcome(states["entry"], rule_results, inputs_hash)
    return _open_outcome(states["exit"], states["invalidation"], rule_results, inputs_hash)
