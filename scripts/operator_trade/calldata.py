"""Calldata for the three operator calls.

The swap call is not rebuilt here: it uses the merged direct-route builder from
``edge_os_api.execution.direct_route_quote_client``. ``deposit()`` and ``approve(address,uint256)``
are encoded locally; tests compare them with an independent ``eth_abi`` encoding.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from eth_utils import keccak

from edge_os_api.execution.direct_route_quote_client import (
    DirectRoutePins,
    build_calldata_hex,
    build_program_hex,
)
from edge_os_api.kuru_flow.types import is_address

PROGRAM_ENDPOINT_PLACEHOLDER = "https://operator-trade.invalid/rpc"
_UINT256 = 2**256


def _selector(signature: str) -> str:
    return "0x" + keccak(signature.encode("ascii")).hex()[:8]


DEPOSIT_SELECTOR = _selector("deposit()")
APPROVE_SELECTOR = _selector("approve(address,uint256)")


def _address_word(value: str) -> str:
    if not is_address(value):
        raise ValueError("address is not canonical")
    return "0" * 24 + value[2:].lower()


def _uint_word(value: int) -> str:
    if type(value) is not int or not 0 <= value < _UINT256:
        raise ValueError("amount is outside uint256")
    return value.to_bytes(32, "big").hex()


def deposit_calldata() -> str:
    return DEPOSIT_SELECTOR


def approve_calldata(spender: str, amount: int) -> str:
    return APPROVE_SELECTOR + _address_word(spender) + _uint_word(amount)


def _pin(trade: Mapping[str, Any] | Any, name: str) -> Any:
    return trade[name] if isinstance(trade, Mapping) else getattr(trade, name)


def swap_calldata(trade: Mapping[str, Any] | Any, input_raw: int, minimum_raw: int) -> str:
    """The exact merged ``executeSwap(SwapIntent,FeeCollection,bytes)`` call for these pins.

    ``DirectRoutePins`` validates its read endpoint, but ``build_calldata_hex`` never reads it. A
    fixed placeholder keeps the live RPC URL out of this object.
    """
    pins = DirectRoutePins(
        endpoint=PROGRAM_ENDPOINT_PLACEHOLDER,
        pool_address=_pin(trade, "pool"),
        token0_address=_pin(trade, "token0"),
        token1_address=_pin(trade, "token1"),
        direction=_pin(trade, "direction"),
        program_fee_ppm=_pin(trade, "program_fee_ppm"),
        approved_program_hex=build_program_hex(
            input_token=_pin(trade, "wmon"),
            pool_address=_pin(trade, "pool"),
            direction=_pin(trade, "direction"),
            fee_ppm=_pin(trade, "program_fee_ppm"),
        ),
        approved_input_raw=str(input_raw),
        approved_min_output_raw=str(minimum_raw),
        entrypoint_address=_pin(trade, "entrypoint"),
        input_token=_pin(trade, "wmon"),
        output_token=_pin(trade, "moe"),
    )
    return build_calldata_hex(pins)
