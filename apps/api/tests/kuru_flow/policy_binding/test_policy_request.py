from __future__ import annotations

import pytest

from edge_os_api.kuru_flow.policy_binding import (
    DOCUMENTED_CONTROLS,
    PROVIDER_EXECUTED,
    R_POLICY_ADMIN_NOT_SEPARATED,
    R_POLICY_ADMIN_OWNER_MISSING,
    R_POLICY_PROVIDER_EXECUTED,
    R_POLICY_REQUEST_INCOMPLETE,
    UNEXPRESSIBLE_CONTROLS,
    UNPROVEN_CONTROLS,
    PolicyFieldSource,
    PolicyRequest,
    PreparedPolicyRequest,
    build_policy_request,
    validate_binding,
)
from edge_os_api.kuru_flow.types import AdapterError

from kuru_flow._support import MAINNET_ENTRYPOINT, USDC_MAINNET, base_config

WALLET_ID = "wal_000000000000000000000000"


def _conditions(request: PolicyRequest) -> list[dict]:
    return [
        {"field_source": condition.field_source.value, "field": condition.field, "operator": condition.operator.value}
        for rule in request.rules
        for condition in rule.conditions
    ]


def test_build_pins_chain_entrypoint_and_function():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    conditions = _conditions(prepared.request)
    fields = {condition["field"] for condition in conditions}
    sources = {condition["field_source"] for condition in conditions}
    assert {"chain_id", "to", "function_name"} <= fields
    assert "ethereum_transaction" in sources
    assert "ethereum_calldata" in sources
    assert any(field.startswith("executeSwap.") for field in fields)


def test_build_attempts_intent_fee_and_program_arguments():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    fields = {condition["field"] for condition in _conditions(prepared.request)}
    assert {
        "executeSwap.intent.tokenUserBuys",
        "executeSwap.intent.minAmountUserBuys",
        "executeSwap.intent.tokenUserSells",
        "executeSwap.intent.amountUserSells",
        "executeSwap.fees.feeBps",
        "executeSwap.fees.referrerFeeBps",
        "executeSwap.fees.isInTokenFee",
        "executeSwap.program",
    } <= fields


def test_build_uses_eth_sign_transaction_and_exactly_one_allow_rule():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    assert prepared.request.version == "1.0"
    assert prepared.request.chain_type == "ethereum"
    assert len(prepared.request.rules) == 1
    assert prepared.request.rules[0].method == "eth_signTransaction"
    assert prepared.request.rules[0].action.value == "ALLOW"


def test_coverage_split_matches_reviewed_sources():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    assert prepared.documented_controls == DOCUMENTED_CONTROLS
    assert prepared.unproven_controls == UNPROVEN_CONTROLS
    assert prepared.unexpressible_controls == UNEXPRESSIBLE_CONTROLS


def test_validate_reports_every_unproven_and_unexpressible_control():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    reasons = validate_binding(prepared)
    for control in UNPROVEN_CONTROLS + UNEXPRESSIBLE_CONTROLS:
        assert f"{R_POLICY_REQUEST_INCOMPLETE}:{control}" in reasons


def test_validate_reports_a_missing_documented_condition():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    rule = prepared.request.rules[0]
    kept = [
        condition
        for condition in rule.conditions
        if not (
            condition.field_source is PolicyFieldSource.ETHEREUM_TRANSACTION
            and condition.field == "chain_id"
        )
    ]
    stripped = prepared.request.model_copy(
        update={"rules": [rule.model_copy(update={"conditions": kept})]}
    )
    reasons = validate_binding(prepared.model_copy(update={"request": stripped}))
    assert "POLICY_REQUEST_INCOMPLETE:chain" in reasons


def test_receiver_method_adds_a_receiver_condition():
    prepared = build_policy_request(
        base_config(method="EXECUTE_SWAP_WITH_RECEIVER"), wallet_id=WALLET_ID
    )
    fields = {condition["field"] for condition in _conditions(prepared.request)}
    assert "executeSwapWithReceiver.receiver" in fields


def test_prepared_request_records_provider_not_run():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    assert prepared.provider_executed == PROVIDER_EXECUTED == "NOT_RUN"


def test_validate_rejects_a_claimed_provider_run():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    doctor = prepared.model_copy(update={"provider_executed": "PROVIDER_ACTUAL"})
    assert R_POLICY_PROVIDER_EXECUTED in validate_binding(doctor)


def test_build_rejects_an_empty_wallet_identity():
    with pytest.raises(AdapterError):
        build_policy_request(base_config(), wallet_id="   ")


def test_entrypoint_condition_value_is_the_approved_entrypoint():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    to_values = [
        condition.value
        for condition in prepared.request.rules[0].conditions
        if condition.field == "to"
    ]
    assert to_values == [MAINNET_ENTRYPOINT]
    assert USDC_MAINNET not in to_values


def test_condition_values_are_bounded():
    from edge_os_api.kuru_flow.policy_binding import (
        MAX_CONDITION_VALUE_ITEMS,
        PolicyCondition,
        PolicyOperator,
    )

    too_many = ["0x00"] * (MAX_CONDITION_VALUE_ITEMS + 1)
    with pytest.raises(ValueError):
        PolicyCondition(
            field_source=PolicyFieldSource.ETHEREUM_CALLDATA,
            field="executeSwap.program",
            operator=PolicyOperator.IN,
            value=too_many,
        )


def test_declared_bounds_are_positive():
    from edge_os_api.kuru_flow.policy_binding import (
        MAX_CONDITIONS_PER_RULE,
        MAX_RULES,
    )

    assert MAX_RULES > 0
    assert MAX_CONDITIONS_PER_RULE > 0


def _value_conditions(prepared):
    return [
        condition.value
        for condition in prepared.request.rules[0].conditions
        if condition.field_source is PolicyFieldSource.ETHEREUM_TRANSACTION
        and condition.field == "value"
    ]


def test_build_binds_the_transaction_value():
    native = build_policy_request(base_config(), wallet_id=WALLET_ID)
    assert _value_conditions(native) == [base_config().approved_input_raw]

    erc20 = build_policy_request(
        base_config(
            input_token=USDC_MAINNET,
            input_asset_id="monad:143/usdc",
            input_decimals=6,
            allowance_raw="1000000000000000000",
        ),
        wallet_id=WALLET_ID,
    )
    assert _value_conditions(erc20) == ["0"]


def test_validate_reports_a_missing_native_value_condition():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    rule = prepared.request.rules[0]
    kept = [
        condition
        for condition in rule.conditions
        if not (
            condition.field_source is PolicyFieldSource.ETHEREUM_TRANSACTION
            and condition.field == "value"
        )
    ]
    stripped = prepared.request.model_copy(
        update={"rules": [rule.model_copy(update={"conditions": kept})]}
    )
    reasons = validate_binding(prepared.model_copy(update={"request": stripped}))
    assert "POLICY_REQUEST_INCOMPLETE:native_value" in reasons


def test_validate_requires_a_policy_resource_owner_by_default():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID)
    reasons = validate_binding(prepared)
    assert R_POLICY_ADMIN_OWNER_MISSING in reasons
    assert R_POLICY_ADMIN_NOT_SEPARATED in reasons


def test_validate_clears_the_admin_reasons_when_bound():
    prepared = build_policy_request(
        base_config(),
        wallet_id=WALLET_ID,
        policy_owner_id="ou_policy_owner",
        administration_separated=True,
    )
    reasons = validate_binding(prepared)
    assert R_POLICY_ADMIN_OWNER_MISSING not in reasons
    assert R_POLICY_ADMIN_NOT_SEPARATED not in reasons
    assert prepared.request.owner_id == "ou_policy_owner"


def _serialized(prepared: PreparedPolicyRequest) -> dict:
    return prepared.model_dump(mode="python")


def _bound_proposal() -> PreparedPolicyRequest:
    return build_policy_request(
        base_config(),
        wallet_id=WALLET_ID,
        policy_owner_id="ou_policy_owner",
        administration_separated=True,
    )


def test_serialized_consistent_owner_revalidates_and_clears_admin_reasons():
    revalidated = PreparedPolicyRequest.model_validate(_serialized(_bound_proposal()))
    reasons = validate_binding(revalidated)
    assert R_POLICY_ADMIN_OWNER_MISSING not in reasons
    assert R_POLICY_ADMIN_NOT_SEPARATED not in reasons


def test_payload_and_wrapper_owner_disagreements_are_rejected():
    mutations = {
        "payload_none": lambda payload: payload["request"].update({"owner_id": None}),
        "payload_blank": lambda payload: payload["request"].update({"owner_id": ""}),
        "payload_whitespace": lambda payload: payload["request"].update({"owner_id": "   "}),
        "payload_different": lambda payload: payload["request"].update({"owner_id": "ou_other"}),
        "wrapper_different": lambda payload: payload.update({"policy_owner_id": "ou_other"}),
        "wrapper_none": lambda payload: payload.update({"policy_owner_id": None}),
    }
    for label, mutate in mutations.items():
        payload = _serialized(_bound_proposal())
        mutate(payload)
        with pytest.raises(ValueError):
            PreparedPolicyRequest.model_validate(payload)


def test_default_ownerless_proposal_is_preserved_and_flagged():
    revalidated = PreparedPolicyRequest.model_validate(_serialized(build_policy_request(base_config(), wallet_id=WALLET_ID)))
    assert revalidated.request.owner_id is None
    assert R_POLICY_ADMIN_OWNER_MISSING in validate_binding(revalidated)


def test_blank_owner_is_flagged_even_when_payload_and_wrapper_agree():
    prepared = build_policy_request(base_config(), wallet_id=WALLET_ID, policy_owner_id="   ")
    assert R_POLICY_ADMIN_OWNER_MISSING in validate_binding(prepared)
