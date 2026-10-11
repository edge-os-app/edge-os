from __future__ import annotations

from edge_os_api.kuru_flow.transaction_preparation import prepare_unsigned_transaction
from edge_os_api.kuru_flow.types import (
    R_ALLOWANCE_UNKNOWN,
    R_CALLDATA_MISSING,
    R_CONFLICTING_SUMMARY,
    R_ENTRYPOINT_NOT_ALLOWED,
    R_ERC20_VALUE_NOT_ZERO,
    R_EXPIRY_UNKNOWN,
    R_FEE_BOUND_EXCEEDED,
    R_FRESHNESS_UNKNOWN,
    R_INPUT_FRESHNESS_UNKNOWN,
    R_INPUT_NOT_APPROVED,
    R_INTENT_EXPIRED,
    R_MIN_OUTPUT_INVALID,
    R_NATIVE_VALUE_INSUFFICIENT,
    R_PROGRAM_NOT_APPROVED,
    R_RECIPIENT_NOT_ALLOWED,
    R_SCHEMA_UNSUPPORTED,
    R_SELECTOR_NOT_ALLOWED,
    R_STALE_QUOTE,
    ResponseProvenance,
)

from kuru_flow._support import (
    AUTHORED_RECEIVER_SELECTOR,
    FIXTURE_MIN_OUT,
    FIXTURE_ORDER,
    PROGRAM_HEX,
    WALLET,
    base_config,
    build_response,
    encode_execute_swap,
    encode_execute_swap_with_receiver,
    erc20_config,
    transaction_response,
)

NOW = "2026-10-10T00:00:00Z"


def _prepare(response, config, *, value=None, **kwargs):
    if value is not None:
        response = dict(response)
        response["transaction"] = dict(response["transaction"])
        response["transaction"]["value"] = value
    kwargs.setdefault("provenance", ResponseProvenance.AUTHORED)
    kwargs.setdefault("now", NOW)
    kwargs.setdefault("quote_age_seconds", 10)
    kwargs.setdefault("input_age_seconds", 20)
    return prepare_unsigned_transaction(quote_response=response, config=config, **kwargs)


def test_accepted_candidate_is_immutable_with_literal_identity():
    result = _prepare(transaction_response(encode_execute_swap()), base_config())
    assert result.outcome.value == "ACCEPTED"
    candidate = result.candidate
    assert candidate is not None
    assert candidate.chain_id == 143
    assert candidate.to == "0xb3e6778480b2E488385E8205eA05E20060B813cb"
    assert candidate.value_raw == FIXTURE_ORDER
    assert candidate.intent.amount_user_sells == FIXTURE_ORDER
    assert candidate.intent.min_amount_user_buys == FIXTURE_MIN_OUT
    assert candidate.program_hex == PROGRAM_HEX
    assert candidate.candidate_hash.startswith("sha256:")
    assert len(candidate.candidate_hash) == 71


def test_selector_mismatch_blocked():
    result = _prepare(transaction_response(encode_execute_swap()), base_config(selector="0x99999999"))
    assert R_SELECTOR_NOT_ALLOWED in result.reasons


def test_entrypoint_mismatch_blocked():
    response = transaction_response(encode_execute_swap(), to="0x0000000000000000000000000000000000000099")
    result = _prepare(response, base_config())
    assert R_ENTRYPOINT_NOT_ALLOWED in result.reasons


def test_input_amount_mismatch_blocked():
    data = encode_execute_swap(amount_user_sells="2")
    response = transaction_response(data, value="2")
    result = _prepare(response, base_config())
    assert R_INPUT_NOT_APPROVED in result.reasons


def test_min_output_above_quote_blocked():
    data = encode_execute_swap(min_amount_user_buys="2000000")
    result = _prepare(transaction_response(data), base_config(min_out_raw="2000000"))
    assert R_MIN_OUTPUT_INVALID in result.reasons


def test_program_mismatch_blocked():
    data = encode_execute_swap(program_hex="0xcafebabe")
    result = _prepare(transaction_response(data), base_config())
    assert R_PROGRAM_NOT_APPROVED in result.reasons


def test_fee_bound_exceeded_blocked():
    data = encode_execute_swap(fee_bps=6000, referrer_fee_bps=6000)
    result = _prepare(transaction_response(data), base_config())
    assert R_FEE_BOUND_EXCEEDED in result.reasons


def test_native_value_insufficient_blocked():
    result = _prepare(transaction_response(encode_execute_swap()), base_config(), value="1")
    assert R_NATIVE_VALUE_INSUFFICIENT in result.reasons


def test_erc20_nonzero_value_blocked():
    data = encode_execute_swap(token_user_sells="0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A")
    result = _prepare(transaction_response(data), erc20_config())
    assert R_ERC20_VALUE_NOT_ZERO in result.reasons


def test_erc20_missing_allowance_blocked():
    data = encode_execute_swap(token_user_sells="0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A")
    result = _prepare(transaction_response(data, value=0), erc20_config(allowance_raw=None))
    assert R_ALLOWANCE_UNKNOWN in result.reasons


def test_conflicting_declared_summary_blocked():
    response = transaction_response(encode_execute_swap())
    response["intent"] = {"amountUserSells": "999"}
    result = _prepare(response, base_config())
    assert R_CONFLICTING_SUMMARY in result.reasons


def test_missing_freshness_values_yield_unknown():
    result = _prepare(
        transaction_response(encode_execute_swap()),
        base_config(),
        now=None,
        quote_age_seconds=None,
        input_age_seconds=None,
    )
    assert result.outcome.value == "UNKNOWN"
    assert set(result.reasons) == {R_FRESHNESS_UNKNOWN, R_INPUT_FRESHNESS_UNKNOWN, R_EXPIRY_UNKNOWN}


def test_stale_quote_blocked():
    result = _prepare(transaction_response(encode_execute_swap()), base_config(), quote_age_seconds=100)
    assert result.outcome.value == "BLOCKED"
    assert R_STALE_QUOTE in result.reasons


def test_expired_intent_blocked():
    result = _prepare(transaction_response(encode_execute_swap()), base_config(), now="2026-10-13T00:00:00Z")
    assert R_INTENT_EXPIRED in result.reasons


def test_build_response_blocked():
    result = _prepare(build_response(), base_config())
    assert result.outcome.value == "BLOCKED"
    assert R_SCHEMA_UNSUPPORTED in result.reasons


def test_missing_calldata_blocked():
    result = _prepare(transaction_response(None), base_config())
    assert result.outcome.value == "BLOCKED"
    assert R_CALLDATA_MISSING in result.reasons


def test_receiver_variant_accepts_matching_receiver():
    config = base_config(method="EXECUTE_SWAP_WITH_RECEIVER", selector=AUTHORED_RECEIVER_SELECTOR)
    data = encode_execute_swap_with_receiver(receiver=WALLET)
    result = _prepare(transaction_response(data), config)
    assert result.outcome.value == "ACCEPTED"
    assert result.candidate is not None
    assert result.candidate.receiver == WALLET.lower()


def test_receiver_variant_rejects_other_receiver():
    config = base_config(method="EXECUTE_SWAP_WITH_RECEIVER", selector=AUTHORED_RECEIVER_SELECTOR)
    data = encode_execute_swap_with_receiver(receiver="0x00000000000000000000000000000000000000B2")
    result = _prepare(transaction_response(data), config)
    assert R_RECIPIENT_NOT_ALLOWED in result.reasons
