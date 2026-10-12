from __future__ import annotations

import pytest

from edge_os_api.kuru_flow.flow_calldata import CalldataDecodeError, decode_flow_call
from edge_os_api.kuru_flow.types import (
    NATIVE_TOKEN_ADDRESS,
    R_CALLDATA_NOT_HEX,
    R_INCONSISTENT_ABI,
    R_METHOD_LAYOUT_UNKNOWN,
    R_NON_CANONICAL_PADDING,
    R_NON_CANONICAL_WORD,
    R_PROGRAM_MISSING,
    R_TRUNCATED_ABI,
)

from kuru_flow._support import (
    AUTHORED_RECEIVER_SELECTOR,
    AUTHORED_SELECTOR,
    FIXTURE_MIN_OUT,
    FIXTURE_ORDER,
    PROGRAM_HEX,
    USDC_MAINNET,
    WALLET,
    encode_execute_swap,
    encode_execute_swap_with_receiver,
)


def _patch_word(data_hex: str, word_index: int, raw_word: bytes) -> str:
    raw = bytearray(bytes.fromhex(data_hex[2:]))
    start = 4 + word_index * 32
    raw[start : start + 32] = raw_word
    return "0x" + raw.hex()


def test_decode_execute_swap_literal_fields():
    call = decode_flow_call(data_hex=encode_execute_swap(), method="EXECUTE_SWAP")
    assert call.selector == AUTHORED_SELECTOR
    assert call.method == "EXECUTE_SWAP"
    assert call.intent.token_user_buys == USDC_MAINNET.lower()
    assert call.intent.min_amount_user_buys == FIXTURE_MIN_OUT
    assert call.intent.token_user_sells == NATIVE_TOKEN_ADDRESS.lower()
    assert call.intent.amount_user_sells == FIXTURE_ORDER
    assert call.fees.fee_bps == 0
    assert call.fees.referrer_fee_bps == 0
    assert call.fees.is_in_token_fee is False
    assert call.program_hex == PROGRAM_HEX
    assert call.receiver is None


def test_decode_execute_swap_with_receiver_literal_fields():
    data = encode_execute_swap_with_receiver(receiver=WALLET)
    call = decode_flow_call(data_hex=data, method="EXECUTE_SWAP_WITH_RECEIVER")
    assert call.selector == AUTHORED_RECEIVER_SELECTOR
    assert call.receiver == WALLET.lower()
    assert call.program_hex == PROGRAM_HEX


def test_non_hex_calldata_rejected():
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex="0xzz", method="EXECUTE_SWAP")
    assert error.value.reason == R_CALLDATA_NOT_HEX


def test_unknown_method_layout_rejected():
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex=encode_execute_swap(), method="NOPE")
    assert error.value.reason == R_METHOD_LAYOUT_UNKNOWN


def test_truncated_head_rejected():
    data = encode_execute_swap()
    body_hex = data[2:][8 : 8 + 9 * 64]
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex="0x" + data[2:][:8] + body_hex, method="EXECUTE_SWAP")
    assert error.value.reason == R_TRUNCATED_ABI


def test_inconsistent_program_offset_rejected():
    data = _patch_word(encode_execute_swap(), 9, (352).to_bytes(32, "big"))
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex=data, method="EXECUTE_SWAP")
    assert error.value.reason == R_INCONSISTENT_ABI


def test_trailing_bytes_rejected():
    data = encode_execute_swap() + "00" * 32
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex=data, method="EXECUTE_SWAP")
    assert error.value.reason == R_INCONSISTENT_ABI


def test_non_canonical_address_word_rejected():
    bad = (1).to_bytes(1, "big") + b"\x00" * 31
    data = _patch_word(encode_execute_swap(), 0, bad)
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex=data, method="EXECUTE_SWAP")
    assert error.value.reason == R_NON_CANONICAL_WORD


def test_non_canonical_boolean_word_rejected():
    data = _patch_word(encode_execute_swap(), 8, (2).to_bytes(32, "big"))
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex=data, method="EXECUTE_SWAP")
    assert error.value.reason == R_NON_CANONICAL_WORD


def test_empty_program_rejected():
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex=encode_execute_swap(program_hex="0x"), method="EXECUTE_SWAP")
    assert error.value.reason == R_PROGRAM_MISSING


def test_nonzero_program_padding_rejected():
    data = encode_execute_swap()
    altered = data[:-2] + "01"
    with pytest.raises(CalldataDecodeError) as error:
        decode_flow_call(data_hex=altered, method="EXECUTE_SWAP")
    assert error.value.reason == R_NON_CANONICAL_PADDING
