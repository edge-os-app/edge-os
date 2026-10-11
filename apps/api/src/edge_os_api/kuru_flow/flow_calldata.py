"""Bounded decoder for the exact Kuru Flow entrypoint calldata.

This decodes only the two documented entrypoint methods
``executeSwap(SwapIntent, FeeCollection, bytes)`` and
``executeSwapWithReceiver(SwapIntent, FeeCollection, bytes, address)`` from the
pinned public source. It is not a general ABI codec. Any shape outside these two
layouts, any non-canonical word, any truncation and any inconsistent dynamic
region is rejected. The function selector is reported, never recomputed: this
environment has no Ethereum Keccak-256 and the adapter never substitutes
SHA3-256 for it.
"""

from __future__ import annotations

from edge_os_api.kuru_flow.types import (
    METHOD_EXECUTE_SWAP,
    METHOD_EXECUTE_SWAP_WITH_RECEIVER,
    R_CALLDATA_NOT_HEX,
    R_INCONSISTENT_ABI,
    R_METHOD_LAYOUT_UNKNOWN,
    R_NON_CANONICAL_PADDING,
    R_NON_CANONICAL_WORD,
    R_PROGRAM_MISSING,
    R_TRUNCATED_ABI,
    AdapterError,
    DecodedFeeCollection,
    DecodedFlowCall,
    DecodedFlowIntent,
    is_nonempty_hex,
)

_WORD_BYTES = 32

_INTENT_WORDS = 4
_FEE_WORDS = 5
_HEAD_BYTES = {
    METHOD_EXECUTE_SWAP: (_INTENT_WORDS + _FEE_WORDS + 1) * _WORD_BYTES,
    METHOD_EXECUTE_SWAP_WITH_RECEIVER: (_INTENT_WORDS + _FEE_WORDS + 2) * _WORD_BYTES,
}
_OFFSET_WORD_INDEX = _INTENT_WORDS + _FEE_WORDS
_RECEIVER_WORD_INDEX = _OFFSET_WORD_INDEX + 1


class CalldataDecodeError(AdapterError):
    """A bounded-decode rejection that names its exact reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _word(body: bytes, index: int) -> bytes:
    start = index * _WORD_BYTES
    return body[start : start + _WORD_BYTES]


def _address_from_word(word: bytes) -> str:
    if word[:12] != b"\x00" * 12:
        raise CalldataDecodeError(R_NON_CANONICAL_WORD)
    return "0x" + word[12:].hex()


def _uint_from_word(word: bytes) -> int:
    return int.from_bytes(word, "big")


def _canonical_raw(value: int) -> str:
    return str(value)


def _bool_from_word(word: bytes) -> bool:
    value = _uint_from_word(word)
    if value not in (0, 1):
        raise CalldataDecodeError(R_NON_CANONICAL_WORD)
    return value == 1


def decode_flow_call(*, data_hex: str, method: str) -> DecodedFlowCall:
    """Decode the exact entrypoint call for the approved method layout."""
    if method not in _HEAD_BYTES:
        raise CalldataDecodeError(R_METHOD_LAYOUT_UNKNOWN)
    if not isinstance(data_hex, str) or not is_nonempty_hex(data_hex):
        raise CalldataDecodeError(R_CALLDATA_NOT_HEX)

    raw = bytes.fromhex(data_hex[2:])
    if len(raw) < 4:
        raise CalldataDecodeError(R_TRUNCATED_ABI)
    selector = "0x" + raw[:4].hex()
    body = raw[4:]

    head_bytes = _HEAD_BYTES[method]
    if len(body) < head_bytes:
        raise CalldataDecodeError(R_TRUNCATED_ABI)
    if len(body) % _WORD_BYTES != 0:
        raise CalldataDecodeError(R_INCONSISTENT_ABI)

    offset_word = _uint_from_word(_word(body, _OFFSET_WORD_INDEX))
    if offset_word != head_bytes:
        raise CalldataDecodeError(R_INCONSISTENT_ABI)

    region_start = head_bytes
    if len(body) < region_start + _WORD_BYTES:
        raise CalldataDecodeError(R_TRUNCATED_ABI)
    program_length = _uint_from_word(body[region_start : region_start + _WORD_BYTES])
    padded = ((program_length + _WORD_BYTES - 1) // _WORD_BYTES) * _WORD_BYTES
    program_end = region_start + _WORD_BYTES + padded
    if len(body) != program_end:
        raise CalldataDecodeError(R_INCONSISTENT_ABI)
    if program_length == 0:
        raise CalldataDecodeError(R_PROGRAM_MISSING)

    program_start = region_start + _WORD_BYTES
    padding = body[program_start + program_length : program_end]
    if any(byte != 0 for byte in padding):
        raise CalldataDecodeError(R_NON_CANONICAL_PADDING)

    program_hex = "0x" + body[program_start : program_start + program_length].hex()

    receiver: str | None = None
    if method == METHOD_EXECUTE_SWAP_WITH_RECEIVER:
        receiver = _address_from_word(_word(body, _RECEIVER_WORD_INDEX))

    intent = DecodedFlowIntent(
        token_user_buys=_address_from_word(_word(body, 0)),
        min_amount_user_buys=_canonical_raw(_uint_from_word(_word(body, 1))),
        token_user_sells=_address_from_word(_word(body, 2)),
        amount_user_sells=_canonical_raw(_uint_from_word(_word(body, 3))),
    )
    fees = DecodedFeeCollection(
        fee_collector_address=_address_from_word(_word(body, 4)),
        fee_bps=_uint_from_word(_word(body, 5)),
        referrer_address=_address_from_word(_word(body, 6)),
        referrer_fee_bps=_uint_from_word(_word(body, 7)),
        is_in_token_fee=_bool_from_word(_word(body, 8)),
    )
    return DecodedFlowCall(
        selector=selector,
        method=method,
        intent=intent,
        fees=fees,
        program_hex=program_hex,
        receiver=receiver,
    )
