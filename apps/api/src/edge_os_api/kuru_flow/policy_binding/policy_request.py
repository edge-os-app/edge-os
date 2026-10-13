"""Prepare and validate the offline independent wallet-policy request.

The request is a declared, Privy-shaped policy that a future real provider
check would submit. This module builds it from the approved adapter
configuration and validates its coverage. It selects no live value, contacts no
provider and changes no policy. A local pass never proves an independent
provider restriction.
"""

from __future__ import annotations

from typing import Any

from ..types import (
    METHOD_EXECUTE_SWAP,
    METHOD_EXECUTE_SWAP_WITH_RECEIVER,
    AdapterError,
    ApprovedAdapterConfiguration,
)
from .binding_types import (
    DOCUMENTED_CONTROLS,
    POLICY_SCHEMA_VERSION,
    PROVIDER_EXECUTED,
    R_POLICY_ADMIN_NOT_SEPARATED,
    R_POLICY_ADMIN_OWNER_MISSING,
    R_POLICY_PROVIDER_EXECUTED,
    R_POLICY_REQUEST_INCOMPLETE,
    UNEXPRESSIBLE_CONTROLS,
    UNPROVEN_CONTROLS,
    PolicyAction,
    PolicyCondition,
    PolicyFieldSource,
    PolicyOperator,
    PolicyRequest,
    PolicyRule,
    PreparedPolicyRequest,
)

RPC_METHOD_ETH_SIGN_TRANSACTION = "eth_signTransaction"
DEFAULT_POLICY_NAME = "Edge OS Kuru Flow fixed-input"

_FUNCTION_NAME_BY_METHOD = {
    METHOD_EXECUTE_SWAP: "executeSwap",
    METHOD_EXECUTE_SWAP_WITH_RECEIVER: "executeSwapWithReceiver",
}

_INTENT_COMPONENTS: list[dict[str, Any]] = [
    {"name": "tokenUserBuys", "type": "address"},
    {"name": "minAmountUserBuys", "type": "uint256"},
    {"name": "tokenUserSells", "type": "address"},
    {"name": "amountUserSells", "type": "uint256"},
]
_FEE_COMPONENTS: list[dict[str, Any]] = [
    {"name": "feeCollectorAddress", "type": "address"},
    {"name": "feeBps", "type": "uint256"},
    {"name": "referrerAddress", "type": "address"},
    {"name": "referrerFeeBps", "type": "uint256"},
    {"name": "isInTokenFee", "type": "bool"},
]


def function_name_for_method(method: str) -> str:
    """Return the pinned ABI function name for an approved adapter method."""
    try:
        return _FUNCTION_NAME_BY_METHOD[method]
    except KeyError as error:
        raise AdapterError(f"no pinned ABI function name for method {method!r}") from error


def _flow_abi(function_name: str, method: str) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = [
        {"name": "intent", "type": "tuple", "components": _INTENT_COMPONENTS},
        {"name": "fees", "type": "tuple", "components": _FEE_COMPONENTS},
        {"name": "program", "type": "bytes"},
    ]
    if method == METHOD_EXECUTE_SWAP_WITH_RECEIVER:
        inputs.append({"name": "receiver", "type": "address"})
    return [
        {
            "type": "function",
            "name": function_name,
            "stateMutability": "payable",
            "inputs": inputs,
            "outputs": [{"name": "", "type": "uint256"}],
        }
    ]


def _transaction_condition(field: str, value: str) -> PolicyCondition:
    return PolicyCondition(
        field_source=PolicyFieldSource.ETHEREUM_TRANSACTION,
        field=field,
        operator=PolicyOperator.EQ,
        value=value,
    )


def _calldata_condition(
    function_name: str, suffix: str, value: str, abi: list[dict[str, Any]]
) -> PolicyCondition:
    return PolicyCondition(
        field_source=PolicyFieldSource.ETHEREUM_CALLDATA,
        field=f"{function_name}.{suffix}",
        operator=PolicyOperator.EQ,
        value=value,
        abi=abi,
    )


def _function_name_condition(
    function_name: str, abi: list[dict[str, Any]]
) -> PolicyCondition:
    return PolicyCondition(
        field_source=PolicyFieldSource.ETHEREUM_CALLDATA,
        field="function_name",
        operator=PolicyOperator.EQ,
        value=function_name,
        abi=abi,
    )


def _build_conditions(
    config: ApprovedAdapterConfiguration, function_name: str
) -> list[PolicyCondition]:
    abi = _flow_abi(function_name, config.method)
    native_value = config.approved_input_raw if config.input_is_native() else "0"
    conditions = [
        _transaction_condition("chain_id", str(config.chain_id)),
        _transaction_condition("to", config.entrypoint_address),
        _transaction_condition("value", native_value),
        _function_name_condition(function_name, abi),
        _calldata_condition(
            function_name, "intent.tokenUserBuys", config.output_asset.token_address, abi
        ),
        _calldata_condition(
            function_name, "intent.tokenUserSells", config.input_asset.token_address, abi
        ),
        _calldata_condition(
            function_name, "intent.amountUserSells", config.approved_input_raw, abi
        ),
        _calldata_condition(
            function_name, "intent.minAmountUserBuys", config.approved_min_output_raw, abi
        ),
        _calldata_condition(function_name, "fees.feeBps", str(config.fees.fee_bps), abi),
        _calldata_condition(
            function_name, "fees.referrerFeeBps", str(config.fees.referrer_fee_bps), abi
        ),
        _calldata_condition(
            function_name, "fees.feeCollectorAddress", config.fees.fee_collector_address, abi
        ),
        _calldata_condition(
            function_name, "fees.referrerAddress", config.fees.referrer_address, abi
        ),
        _calldata_condition(
            function_name,
            "fees.isInTokenFee",
            "true" if config.fees.is_in_token_fee else "false",
            abi,
        ),
        _calldata_condition(function_name, "program", config.approved_program_hex, abi),
    ]
    if config.method == METHOD_EXECUTE_SWAP_WITH_RECEIVER:
        conditions.append(
            _calldata_condition(function_name, "receiver", config.recipient, abi)
        )
    return conditions


def build_policy_request(
    config: ApprovedAdapterConfiguration,
    *,
    wallet_id: str,
    policy_owner_id: str | None = None,
    administration_separated: bool = False,
    policy_name: str = DEFAULT_POLICY_NAME,
    rpc_method: str = RPC_METHOD_ETH_SIGN_TRANSACTION,
) -> PreparedPolicyRequest:
    """Build the declared policy request and its coverage split.

    ``policy_owner_id`` is the policy-resource owner. When it is absent the
    policy is ownerless and the application secret can update it, so the
    administration configuration stays unresolved. Raises ``AdapterError`` for a
    non-configuration input or a blank wallet identity. It never contacts a
    provider.
    """
    if not isinstance(config, ApprovedAdapterConfiguration):
        raise AdapterError("config must be an ApprovedAdapterConfiguration")
    if not isinstance(wallet_id, str) or not wallet_id.strip():
        raise AdapterError("wallet_id must be a non-empty identity")
    function_name = function_name_for_method(config.method)
    rule = PolicyRule(
        name="allow the approved Flow call",
        method=rpc_method,
        action=PolicyAction.ALLOW,
        conditions=_build_conditions(config, function_name),
    )
    request = PolicyRequest(
        version=POLICY_SCHEMA_VERSION,
        name=policy_name,
        rules=[rule],
        owner_id=policy_owner_id,
    )
    return PreparedPolicyRequest(
        wallet_id=wallet_id,
        request=request,
        documented_controls=DOCUMENTED_CONTROLS,
        unproven_controls=UNPROVEN_CONTROLS,
        unexpressible_controls=UNEXPRESSIBLE_CONTROLS,
        policy_owner_id=policy_owner_id,
        administration_separated=administration_separated,
        provider_executed=PROVIDER_EXECUTED,
    )


def _has_transaction_field(request: PolicyRequest, field: str) -> bool:
    return any(
        condition.field_source is PolicyFieldSource.ETHEREUM_TRANSACTION
        and condition.field == field
        for rule in request.rules
        for condition in rule.conditions
    )


def _has_function_name_condition(request: PolicyRequest) -> bool:
    return any(
        condition.field_source is PolicyFieldSource.ETHEREUM_CALLDATA
        and "." not in condition.field
        for rule in request.rules
        for condition in rule.conditions
    )


def validate_binding(prepared: PreparedPolicyRequest) -> tuple[str, ...]:
    """Return the ordered reasons a prepared request is not a complete binding.

    The request is incomplete while any unproven or unexpressible mandatory
    control remains, while a documented condition is missing, or while the
    policy-resource owner is absent or administration is not separated. A
    claimed provider run is rejected: a local artifact cannot be
    ``PROVIDER_ACTUAL``.
    """
    reasons: list[str] = []
    if prepared.provider_executed != PROVIDER_EXECUTED:
        reasons.append(R_POLICY_PROVIDER_EXECUTED)
    request = prepared.request
    if not _has_transaction_field(request, "chain_id"):
        reasons.append(f"{R_POLICY_REQUEST_INCOMPLETE}:chain")
    if not _has_transaction_field(request, "value"):
        reasons.append(f"{R_POLICY_REQUEST_INCOMPLETE}:native_value")
    if not _has_transaction_field(request, "to") or not _has_function_name_condition(
        request
    ):
        reasons.append(f"{R_POLICY_REQUEST_INCOMPLETE}:entrypoint_method")
    if not isinstance(request.owner_id, str) or not request.owner_id.strip():
        reasons.append(R_POLICY_ADMIN_OWNER_MISSING)
    if not prepared.administration_separated:
        reasons.append(R_POLICY_ADMIN_NOT_SEPARATED)
    for control in UNPROVEN_CONTROLS + UNEXPRESSIBLE_CONTROLS:
        reasons.append(f"{R_POLICY_REQUEST_INCOMPLETE}:{control}")
    return tuple(reasons)
