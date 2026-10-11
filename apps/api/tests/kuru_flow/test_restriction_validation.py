from __future__ import annotations

import pytest

from edge_os_api.kuru_flow.flow_calldata import decode_flow_call
from edge_os_api.kuru_flow.quote_schema import parse_quote_response
from edge_os_api.kuru_flow.restriction_validation import validate_candidate
from edge_os_api.kuru_flow.types import (
    NATIVE_TOKEN_ADDRESS,
    R_ASSET_NOT_ALLOWED,
    ApprovedAdapterConfiguration,
    ApprovedFeeCollection,
    ResponseProvenance,
)

from kuru_flow._support import (
    AUTHORED_SELECTOR,
    FIXTURE_MIN_OUT,
    FIXTURE_ORDER,
    MAINNET_ENTRYPOINT,
    PROGRAM_HEX,
    USDC_MAINNET,
    WALLET,
    base_config,
    encode_execute_swap,
    transaction_response,
)


def _parsed_and_call(data_hex: str):
    parsed = parse_quote_response(
        transaction_response(data_hex), ResponseProvenance.AUTHORED
    )
    call = decode_flow_call(data_hex=data_hex, method="EXECUTE_SWAP")
    return parsed, call


def test_matching_candidate_has_no_reasons():
    parsed, call = _parsed_and_call(encode_execute_swap())
    reasons = validate_candidate(
        parsed=parsed, call=call, config=base_config(), quote_age_seconds=5, input_age_seconds=5,
        now="2026-10-10T00:00:00Z",
    )
    assert reasons == ()


def test_asset_mismatch_reports_asset_not_allowed():
    parsed, call = _parsed_and_call(encode_execute_swap())
    reasons = validate_candidate(
        parsed=parsed,
        call=call,
        config=base_config(output_token="0x0000000000000000000000000000000000000001"),
        quote_age_seconds=5,
        input_age_seconds=5,
        now="2026-10-10T00:00:00Z",
    )
    assert R_ASSET_NOT_ALLOWED in reasons


def _raw_config(**overrides):
    fields = {
        "network_id": "monad:143",
        "entrypoint_address": MAINNET_ENTRYPOINT,
        "method": "EXECUTE_SWAP",
        "selector": AUTHORED_SELECTOR,
        "input_asset": {"asset_id": "a", "token_address": NATIVE_TOKEN_ADDRESS, "decimals": 18},
        "output_asset": {"asset_id": "b", "token_address": USDC_MAINNET, "decimals": 6},
        "recipient": WALLET,
        "approved_input_raw": FIXTURE_ORDER,
        "approved_min_output_raw": FIXTURE_MIN_OUT,
        "approved_program_hex": PROGRAM_HEX,
        "fees": {
            "fee_bps": 0,
            "referrer_fee_bps": 0,
            "fee_collector_address": NATIVE_TOKEN_ADDRESS,
            "referrer_address": NATIVE_TOKEN_ADDRESS,
            "is_in_token_fee": False,
        },
        "approved_allowance_raw": None,
        "freshness": {},
        "supported_schema_variants": ["TRANSACTION_CALLDATA"],
    }
    fields.update(overrides)
    return fields


def test_boolean_rejected_for_integer_fee():
    fields = _raw_config()
    fields["fees"] = dict(fields["fees"])
    fields["fees"]["fee_bps"] = True
    with pytest.raises(Exception):
        ApprovedAdapterConfiguration(**fields)


def test_float_rejected_for_integer_decimal():
    fields = _raw_config()
    fields["input_asset"] = dict(fields["input_asset"])
    fields["input_asset"]["decimals"] = 18.0
    with pytest.raises(Exception):
        ApprovedAdapterConfiguration(**fields)


def test_noncanonical_raw_rejected():
    with pytest.raises(Exception):
        ApprovedAdapterConfiguration(**_raw_config(approved_input_raw="01"))


def test_empty_program_rejected():
    with pytest.raises(Exception):
        ApprovedAdapterConfiguration(**_raw_config(approved_program_hex="0x"))


def test_unknown_network_rejected():
    with pytest.raises(Exception):
        ApprovedAdapterConfiguration(**_raw_config(network_id="ethereum:1"))


def test_unknown_schema_variant_rejected():
    with pytest.raises(Exception):
        ApprovedAdapterConfiguration(**_raw_config(supported_schema_variants=["MYSTERY"]))


def test_fee_helper_bound_is_enforced_at_construction():
    with pytest.raises(Exception):
        ApprovedFeeCollection(
            fee_bps=6000,
            referrer_fee_bps=6000,
            fee_collector_address=NATIVE_TOKEN_ADDRESS,
            referrer_address=NATIVE_TOKEN_ADDRESS,
            is_in_token_fee=False,
        )
