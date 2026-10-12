from __future__ import annotations

from edge_os_api.kuru_flow.flow_calldata import decode_flow_call
from edge_os_api.kuru_flow.policy_binding import (
    POLICY_ACTION_ALLOW,
    POLICY_ACTION_DENY,
    PROVIDER_EXECUTED,
    R_POLICY_DENY_RULE,
    R_POLICY_NO_ALLOW_RULE,
    RESULT_AUTHORED_POLICY_ALLOW,
    RESULT_BLOCKED,
    PolicyAction,
    PolicyCondition,
    PolicyFieldSource,
    PolicyOperator,
    PolicyRequest,
    PolicyRule,
    build_policy_request,
    evaluate_authored_policy,
)

from kuru_flow._support import PROGRAM_HEX, USDC_MAINNET, base_config, encode_execute_swap

from ._support import (
    OTHER_ADDRESS,
    approved_call,
    facts_for,
    facts_with_argument,
    receiver_call,
)

WALLET_ID = "wal_000000000000000000000000"


def _approved_request(**overrides):
    return build_policy_request(base_config(**overrides), wallet_id=WALLET_ID)


def test_approved_payload_is_allowed_locally():
    verdict = evaluate_authored_policy(_approved_request().request, facts_for(approved_call()))
    assert verdict.allowed is True
    assert verdict.result_class == RESULT_AUTHORED_POLICY_ALLOW
    assert verdict.reasons == []
    assert verdict.provider_executed == PROVIDER_EXECUTED


def test_default_denies_when_no_rule_matches():
    request = PolicyRequest(version="1.0", name="empty", chain_type="ethereum", rules=[])
    verdict = evaluate_authored_policy(request, facts_for(approved_call()))
    assert verdict.allowed is False
    assert verdict.result_class == RESULT_BLOCKED
    assert verdict.reasons == [R_POLICY_NO_ALLOW_RULE]


def test_missing_fact_blocks_instead_of_raising():
    facts = facts_for(approved_call()).model_copy(update={"arguments": {}})
    verdict = evaluate_authored_policy(_approved_request().request, facts)
    assert verdict.allowed is False
    assert R_POLICY_NO_ALLOW_RULE in verdict.reasons


def test_one_field_route_and_identity_mutations_are_blocked():
    request = _approved_request().request
    mutations = {
        "program": facts_with_argument("program", "0xdeadbe00"),
        "amount": facts_with_argument("intent.amountUserSells", "2"),
        "min_output": facts_with_argument("intent.minAmountUserBuys", "1"),
        "input_asset": facts_with_argument("intent.tokenUserSells", OTHER_ADDRESS),
        "output_asset": facts_with_argument("intent.tokenUserBuys", OTHER_ADDRESS),
        "fee_bps": facts_with_argument("fees.feeBps", "5"),
        "chain": facts_for(approved_call(), chain_id="10143"),
        "entrypoint": facts_for(approved_call(), to=OTHER_ADDRESS),
        "function": facts_for(approved_call(), function_name="executeSwapWithReceiver"),
        "rpc_method": facts_for(approved_call(), rpc_method="eth_sendTransaction"),
        "native_value": facts_for(approved_call(), value_raw="0"),
    }
    for label, facts in mutations.items():
        verdict = evaluate_authored_policy(request, facts)
        assert verdict.allowed is False, label
        assert verdict.result_class == RESULT_BLOCKED, label


def test_receiver_route_binds_the_explicit_receiver():
    request = _approved_request(method="EXECUTE_SWAP_WITH_RECEIVER").request
    allowed = evaluate_authored_policy(request, facts_for(receiver_call()))
    assert allowed.allowed is True

    changed = facts_for(receiver_call(), to=OTHER_ADDRESS)
    changed = changed.model_copy(update={"arguments": dict(changed.arguments, receiver=OTHER_ADDRESS)})
    assert evaluate_authored_policy(request, changed).allowed is False


def test_a_matching_deny_rule_takes_precedence():
    prepared = _approved_request()
    deny = PolicyRule(
        name="deny the approved chain",
        method="eth_signTransaction",
        action=PolicyAction.DENY,
        conditions=[
            PolicyCondition(
                field_source=PolicyFieldSource.ETHEREUM_TRANSACTION,
                field="chain_id",
                operator=PolicyOperator.EQ,
                value="143",
            )
        ],
    )
    request = PolicyRequest(
        version="1.0",
        name="deny precedence",
        chain_type="ethereum",
        rules=[deny, *prepared.request.rules],
    )
    verdict = evaluate_authored_policy(request, facts_for(approved_call()))
    assert verdict.allowed is False
    assert verdict.reasons == [R_POLICY_DENY_RULE]
    assert verdict.matched_rule == "deny the approved chain"


def test_local_verdict_never_claims_an_independent_provider_pass():
    verdict = evaluate_authored_policy(_approved_request().request, facts_for(approved_call()))
    assert verdict.independent_provider_pass is False
    assert verdict.provider_executed == "NOT_RUN"


def _request_with(condition: PolicyCondition) -> PolicyRequest:
    return PolicyRequest(
        version="1.0",
        name="probe",
        chain_type="ethereum",
        rules=[
            PolicyRule(
                name="probe",
                method="eth_signTransaction",
                action=PolicyAction.ALLOW,
                conditions=[condition],
            )
        ],
    )


def test_string_operators_on_route_bytes():
    facts = facts_for(approved_call())
    contains = PolicyCondition(
        field_source=PolicyFieldSource.ETHEREUM_CALLDATA,
        field="executeSwap.program",
        operator=PolicyOperator.CONTAINS,
        value="dead",
    )
    assert evaluate_authored_policy(_request_with(contains), facts).allowed is True
    miss = contains.model_copy(update={"value": "ffff"})
    assert evaluate_authored_policy(_request_with(miss), facts).allowed is False


def test_membership_and_numeric_operators():
    facts = facts_with_argument("fees.feeBps", "5")
    membership = PolicyCondition(
        field_source=PolicyFieldSource.ETHEREUM_CALLDATA,
        field="executeSwap.fees.feeBps",
        operator=PolicyOperator.IN,
        value=["5", "6"],
    )
    assert evaluate_authored_policy(_request_with(membership), facts).allowed is True
    bounded = membership.model_copy(update={"operator": PolicyOperator.LTE, "value": "10"})
    assert evaluate_authored_policy(_request_with(bounded), facts).allowed is True
    too_low = membership.model_copy(update={"operator": PolicyOperator.LTE, "value": "4"})
    assert evaluate_authored_policy(_request_with(too_low), facts).allowed is False


def test_an_unknown_field_resolves_false():
    bogus = PolicyCondition(
        field_source=PolicyFieldSource.ETHEREUM_TRANSACTION,
        field="nonce",
        operator=PolicyOperator.EQ,
        value="1",
    )
    verdict = evaluate_authored_policy(_request_with(bogus), facts_for(approved_call()))
    assert verdict.allowed is False


def test_native_value_must_equal_the_input_exactly():
    request = _approved_request().request
    call = approved_call()
    amount = call.intent.amount_user_sells
    assert evaluate_authored_policy(request, facts_for(call)).allowed is True
    assert evaluate_authored_policy(request, facts_for(call, value_raw="0")).allowed is False
    assert evaluate_authored_policy(request, facts_for(call, value_raw=str(int(amount) - 1))).allowed is False
    assert evaluate_authored_policy(request, facts_for(call, value_raw=str(int(amount) + 1))).allowed is False
    assert evaluate_authored_policy(request, facts_for(call, value_raw=None)).allowed is False


def test_erc20_value_must_be_zero():
    config = base_config(
        input_token=USDC_MAINNET,
        input_asset_id="monad:143/usdc",
        input_decimals=6,
        allowance_raw="1000000000000000000",
    )
    request = build_policy_request(config, wallet_id=WALLET_ID).request
    call = decode_flow_call(
        data_hex=encode_execute_swap(token_user_sells=USDC_MAINNET), method="EXECUTE_SWAP"
    )
    assert evaluate_authored_policy(request, facts_for(call, value_raw="0")).allowed is True
    assert evaluate_authored_policy(request, facts_for(call, value_raw="1")).allowed is False


def test_receiver_route_binds_the_native_value_too():
    request = _approved_request(method="EXECUTE_SWAP_WITH_RECEIVER").request
    assert evaluate_authored_policy(request, facts_for(receiver_call(), value_raw="0")).allowed is False


def test_hex_byte_arguments_compare_case_insensitively():
    mixed_case = "0x" + PROGRAM_HEX[2:].upper()
    facts = facts_with_argument("program", mixed_case)
    assert evaluate_authored_policy(_approved_request().request, facts).allowed is True
