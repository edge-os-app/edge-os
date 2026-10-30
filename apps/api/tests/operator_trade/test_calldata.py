"""Operator calldata: deposit, exact approve and revoke, and the merged direct-route swap call."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from eth_abi import encode as abi_encode
from eth_utils import keccak

from edge_os_api.execution.direct_route_quote_client import (
    DirectRoutePins,
    build_calldata_hex,
    build_program_hex,
)
from edge_os_api.kuru_flow.flow_calldata import decode_flow_call
from edge_os_api.kuru_flow.types import METHOD_EXECUTE_SWAP

from scripts.operator_trade.calldata import approve_calldata, deposit_calldata, swap_calldata

from ._support import ENTRYPOINT, INPUT, MOE, POOL, WMON


def _selector(signature: str) -> str:
    return "0x" + keccak(signature.encode()).hex()[:8]


def test_deposit_is_the_payable_deposit_call() -> None:
    assert deposit_calldata() == _selector("deposit()")


def test_approve_matches_an_independent_eth_abi_encoding() -> None:
    amount = 70 * 10**18
    expected = "0x" + _selector("approve(address,uint256)")[2:] + abi_encode(
        ["address", "uint256"], [ENTRYPOINT, amount]
    ).hex()
    assert approve_calldata(ENTRYPOINT, amount) == expected


def test_revoke_is_approve_to_zero() -> None:
    expected = "0x" + _selector("approve(address,uint256)")[2:] + abi_encode(
        ["address", "uint256"], [ENTRYPOINT, 0]
    ).hex()
    assert approve_calldata(ENTRYPOINT, 0) == expected


def test_approve_refuses_a_non_address_spender() -> None:
    with pytest.raises(ValueError):
        approve_calldata("0x1234", 1)


def test_swap_equals_the_merged_builder_for_the_same_pins() -> None:
    pins = DirectRoutePins(
        endpoint="https://placeholder.invalid/rpc",
        pool_address=POOL,
        token0_address=WMON,
        token1_address=MOE,
        direction=0,
        program_fee_ppm=16000,
        approved_program_hex=build_program_hex(
            input_token=WMON, pool_address=POOL, direction=0, fee_ppm=16000
        ),
        approved_input_raw=str(INPUT),
        approved_min_output_raw=str(INPUT // 2),
        entrypoint_address=ENTRYPOINT,
        input_token=WMON,
        output_token=MOE,
    )
    trade = SimpleNamespace(pool=POOL, wmon=WMON, moe=MOE, entrypoint=ENTRYPOINT,
                            token0=WMON, token1=MOE, direction=0, program_fee_ppm=16000)
    assert swap_calldata(trade, INPUT, INPUT // 2) == build_calldata_hex(pins)


def test_swap_calldata_decodes_to_the_policy_fields() -> None:
    trade = SimpleNamespace(pool=POOL, wmon=WMON, moe=MOE, entrypoint=ENTRYPOINT,
                            token0=WMON, token1=MOE, direction=0, program_fee_ppm=16000)
    minimum = 3_700_181_180_921_076_741_233
    call = decode_flow_call(data_hex=swap_calldata(trade, INPUT, minimum), method=METHOD_EXECUTE_SWAP)
    assert call.intent.token_user_buys.lower() == MOE.lower()
    assert call.intent.min_amount_user_buys == str(minimum)
    assert call.intent.token_user_sells.lower() == WMON.lower()
    assert call.intent.amount_user_sells == str(INPUT)
    assert call.fees.fee_collector_address.lower() == "0x" + "0" * 40
    assert call.fees.fee_bps == 0
    assert call.fees.is_in_token_fee is False
    assert call.program_hex == build_program_hex(
        input_token=WMON, pool_address=POOL, direction=0, fee_ppm=16000
    )
