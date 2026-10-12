"""Evaluate the authored policy request locally.

This is a bounded, offline model of the declared policy. It mirrors the
documented provider semantics that matter here: default denial, a declared
``DENY`` rule before any ``ALLOW`` rule, exact comparison except for EVM
addresses and hex byte strings, and a condition that cannot resolve to a fact
evaluates false. A local ``AUTHORED_POLICY_ALLOW`` is authored behavior only; it
is never an independent provider result.
"""

from __future__ import annotations

import re

from ..types import AdapterError, DecodedFlowCall
from .binding_types import (
    RESULT_AUTHORED_POLICY_ALLOW,
    RESULT_BLOCKED,
    R_POLICY_DENY_RULE,
    R_POLICY_NO_ALLOW_RULE,
    PolicyAction,
    PolicyCondition,
    PolicyFieldSource,
    PolicyFacts,
    PolicyOperator,
    PolicyRequest,
    PolicyRule,
    PolicySimulationVerdict,
)
from .policy_request import function_name_for_method

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")

_TRANSACTION_FIELDS = {
    "chain_id": "chain_id",
    "to": "to",
    "value": "value_raw",
}


def facts_from_decoded_call(
    *,
    chain_id: int,
    entrypoint_address: str,
    rpc_method: str,
    call: DecodedFlowCall,
) -> PolicyFacts:
    """Derive the declared facts from one bounded decoded Flow call."""
    if not isinstance(call, DecodedFlowCall):
        raise AdapterError("call must be a DecodedFlowCall")
    function_name = function_name_for_method(call.method)
    arguments = {
        "intent.tokenUserBuys": call.intent.token_user_buys,
        "intent.minAmountUserBuys": call.intent.min_amount_user_buys,
        "intent.tokenUserSells": call.intent.token_user_sells,
        "intent.amountUserSells": call.intent.amount_user_sells,
        "fees.feeCollectorAddress": call.fees.fee_collector_address,
        "fees.feeBps": str(call.fees.fee_bps),
        "fees.referrerAddress": call.fees.referrer_address,
        "fees.referrerFeeBps": str(call.fees.referrer_fee_bps),
        "fees.isInTokenFee": "true" if call.fees.is_in_token_fee else "false",
        "program": call.program_hex,
    }
    if call.receiver is not None:
        arguments["receiver"] = call.receiver
    return PolicyFacts(
        rpc_method=rpc_method,
        chain_id=str(chain_id),
        to=entrypoint_address,
        function_name=function_name,
        arguments=arguments,
    )


def _field_key(value: str) -> str:
    """Addresses compare case-insensitively; every other value compares exactly."""
    return value.lower() if _ADDRESS.fullmatch(value) else value


def _transaction_fact(field: str, facts: PolicyFacts) -> str | None:
    attribute = _TRANSACTION_FIELDS.get(field)
    return getattr(facts, attribute) if attribute is not None else None


def _calldata_fact(field: str, facts: PolicyFacts) -> str | None:
    prefix, separator, suffix = field.partition(".")
    if not separator:
        return facts.function_name if field == "function_name" else None
    if prefix != facts.function_name:
        return None
    return facts.arguments.get(suffix)


def _compare(operator: PolicyOperator, declared: str, expected: str | list[str]) -> bool:
    values = expected if isinstance(expected, list) else [expected]
    if operator in (PolicyOperator.EQ, PolicyOperator.NEQ, PolicyOperator.IN, PolicyOperator.IN_CONDITION_SET):
        matched = any(_field_key(declared) == _field_key(value) for value in values)
        return not matched if operator is PolicyOperator.NEQ else matched
    if operator in (PolicyOperator.CONTAINS, PolicyOperator.STARTS_WITH, PolicyOperator.ENDS_WITH):
        return any(_string_op(operator, declared, value) for value in values)
    if len(values) != 1:
        return False
    return _number_op(operator, declared, values[0])


def _string_op(operator: PolicyOperator, declared: str, value: str) -> bool:
    if operator is PolicyOperator.CONTAINS:
        return value in declared
    if operator is PolicyOperator.STARTS_WITH:
        return declared.startswith(value)
    return declared.endswith(value)


def _number_op(operator: PolicyOperator, declared: str, value: str) -> bool:
    try:
        left, right = int(declared), int(value)
    except (TypeError, ValueError):
        return False
    if operator is PolicyOperator.LT:
        return left < right
    if operator is PolicyOperator.LTE:
        return left <= right
    if operator is PolicyOperator.GT:
        return left > right
    return left >= right


def _condition_matches(condition: PolicyCondition, facts: PolicyFacts) -> bool:
    if condition.field_source is PolicyFieldSource.ETHEREUM_TRANSACTION:
        declared = _transaction_fact(condition.field, facts)
    else:
        declared = _calldata_fact(condition.field, facts)
    if declared is None:
        return False
    return _compare(condition.operator, declared, condition.value)


def _rule_matches(rule: PolicyRule, facts: PolicyFacts) -> bool:
    if rule.method != facts.rpc_method:
        return False
    return all(_condition_matches(condition, facts) for condition in rule.conditions)


def evaluate_authored_policy(
    request: PolicyRequest, facts: PolicyFacts
) -> PolicySimulationVerdict:
    """Evaluate the authored request against declared facts. Default denial."""
    for rule in request.rules:
        if rule.action is PolicyAction.DENY and _rule_matches(rule, facts):
            return PolicySimulationVerdict(
                allowed=False,
                result_class=RESULT_BLOCKED,
                matched_rule=rule.name,
                reasons=[R_POLICY_DENY_RULE],
            )
    for rule in request.rules:
        if rule.action is PolicyAction.ALLOW and _rule_matches(rule, facts):
            return PolicySimulationVerdict(
                allowed=True,
                result_class=RESULT_AUTHORED_POLICY_ALLOW,
                matched_rule=rule.name,
            )
    return PolicySimulationVerdict(
        allowed=False,
        result_class=RESULT_BLOCKED,
        reasons=[R_POLICY_NO_ALLOW_RULE],
    )
