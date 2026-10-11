"""Independent test support for the offline Kuru Flow adapter.

The encoder here is written independently of the adapter's bounded decoder. It
encodes the two documented entrypoint layouts from the pinned public source. The
authored selector constants are stand-ins: a real Ethereum selector requires
Keccak-256, which this environment does not have, so the adapter checks the
selector by equality against the approved constant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from edge_os_api.kuru_flow.types import (
    NATIVE_TOKEN_ADDRESS,
    ApprovedAdapterConfiguration,
    ApprovedFeeCollection,
    ApprovedFreshness,
)

MAINNET = "monad:143"
TESTNET = "monad-testnet:10143"
MAINNET_ENTRYPOINT = "0xb3e6778480b2E488385E8205eA05E20060B813cb"
MAINNET_ROUTER = "0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2"
USDC_MAINNET = "0x754704Bc059F8C67012fEd69BC8A327a5aafb603"
WALLET = "0x00000000000000000000000000000000000000A1"
OTHER_WALLET = "0x00000000000000000000000000000000000000B2"
AUTHORED_SELECTOR = "0x12345678"
AUTHORED_RECEIVER_SELECTOR = "0x87654321"
PROGRAM_HEX = "0xdeadbeef"

FIXTURE_ORDER = "1000000000000000000"
FIXTURE_MIN_OUT = "1000000"
FIXTURE_QUOTE_OUT = "1500000"


def _word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _address_word(address: str) -> bytes:
    return b"\x00" * 12 + bytes.fromhex(address[2:])


def _bytes_region(data_hex: str) -> bytes:
    payload = bytes.fromhex(data_hex[2:])
    pad = (32 - (len(payload) % 32)) % 32
    return _word(len(payload)) + payload + b"\x00" * pad


def encode_execute_swap(
    *,
    selector: str = AUTHORED_SELECTOR,
    token_user_sells: str = NATIVE_TOKEN_ADDRESS,
    amount_user_sells: str = FIXTURE_ORDER,
    token_user_buys: str = USDC_MAINNET,
    min_amount_user_buys: str = FIXTURE_MIN_OUT,
    fee_collector_address: str = NATIVE_TOKEN_ADDRESS,
    fee_bps: int = 0,
    referrer_address: str = NATIVE_TOKEN_ADDRESS,
    referrer_fee_bps: int = 0,
    is_in_token_fee: bool = False,
    program_hex: str = PROGRAM_HEX,
) -> str:
    head = b"".join(
        [
            _address_word(token_user_buys),
            _word(int(min_amount_user_buys)),
            _address_word(token_user_sells),
            _word(int(amount_user_sells)),
            _address_word(fee_collector_address),
            _word(fee_bps),
            _address_word(referrer_address),
            _word(referrer_fee_bps),
            _word(1 if is_in_token_fee else 0),
            _word(320),
        ]
    )
    return "0x" + (bytes.fromhex(selector[2:]) + head + _bytes_region(program_hex)).hex()


def encode_execute_swap_with_receiver(
    *,
    selector: str = AUTHORED_RECEIVER_SELECTOR,
    receiver: str = WALLET,
    **kwargs: Any,
) -> str:
    head = b"".join(
        [
            _address_word(kwargs.get("token_user_buys", USDC_MAINNET)),
            _word(int(kwargs.get("min_amount_user_buys", FIXTURE_MIN_OUT))),
            _address_word(kwargs.get("token_user_sells", NATIVE_TOKEN_ADDRESS)),
            _word(int(kwargs.get("amount_user_sells", FIXTURE_ORDER))),
            _address_word(kwargs.get("fee_collector_address", NATIVE_TOKEN_ADDRESS)),
            _word(kwargs.get("fee_bps", 0)),
            _address_word(kwargs.get("referrer_address", NATIVE_TOKEN_ADDRESS)),
            _word(kwargs.get("referrer_fee_bps", 0)),
            _word(1 if kwargs.get("is_in_token_fee", False) else 0),
            _word(352),
            _address_word(receiver),
        ]
    )
    program_hex = kwargs.get("program_hex", PROGRAM_HEX)
    return "0x" + (bytes.fromhex(selector[2:]) + head + _bytes_region(program_hex)).hex()


def transaction_response(calldata_hex: str | None, *, to: str = MAINNET_ENTRYPOINT, value: Any = FIXTURE_ORDER) -> dict:
    transaction: dict[str, Any] = {"to": to, "value": value}
    if calldata_hex is not None:
        transaction["calldata"] = calldata_hex[2:]
    return {
        "output": FIXTURE_QUOTE_OUT,
        "minOut": FIXTURE_MIN_OUT,
        "transaction": transaction,
        "gasPrices": {"standard": "1000000000"},
    }


def build_response() -> dict:
    return {
        "output": FIXTURE_QUOTE_OUT,
        "path": {"hops": []},
        "buildResponse": {"kind": "opaque"},
        "gasPrices": {"standard": "1000000000"},
    }


def base_config(**overrides: Any) -> ApprovedAdapterConfiguration:
    fields: dict[str, Any] = {
        "network_id": MAINNET,
        "entrypoint_address": MAINNET_ENTRYPOINT,
        "method": "EXECUTE_SWAP",
        "selector": AUTHORED_SELECTOR,
        "input_asset_id": "monad:143/native",
        "input_token": NATIVE_TOKEN_ADDRESS,
        "input_decimals": 18,
        "output_asset_id": "monad:143/usdc",
        "output_token": USDC_MAINNET,
        "output_decimals": 6,
        "recipient": WALLET,
        "input_raw": FIXTURE_ORDER,
        "min_out_raw": FIXTURE_MIN_OUT,
        "program_hex": PROGRAM_HEX,
        "fee_bps": 0,
        "referrer_fee_bps": 0,
        "fee_collector": NATIVE_TOKEN_ADDRESS,
        "referrer": NATIVE_TOKEN_ADDRESS,
        "is_in_token_fee": False,
        "allowance_raw": None,
        "supported": ["TRANSACTION_CALLDATA"],
    }
    fields.update(overrides)
    return ApprovedAdapterConfiguration(
        network_id=fields["network_id"],
        entrypoint_address=fields["entrypoint_address"],
        method=fields["method"],
        selector=fields["selector"],
        input_asset={
            "asset_id": fields["input_asset_id"],
            "token_address": fields["input_token"],
            "decimals": fields["input_decimals"],
        },
        output_asset={
            "asset_id": fields["output_asset_id"],
            "token_address": fields["output_token"],
            "decimals": fields["output_decimals"],
        },
        recipient=fields["recipient"],
        approved_input_raw=fields["input_raw"],
        approved_min_output_raw=fields["min_out_raw"],
        approved_program_hex=fields["program_hex"],
        fees=ApprovedFeeCollection(
            fee_bps=fields["fee_bps"],
            referrer_fee_bps=fields["referrer_fee_bps"],
            fee_collector_address=fields["fee_collector"],
            referrer_address=fields["referrer"],
            is_in_token_fee=fields["is_in_token_fee"],
        ),
        approved_allowance_raw=fields["allowance_raw"],
        freshness=ApprovedFreshness(
            max_quote_age_seconds=fields.get("max_quote_age", 30),
            max_input_age_seconds=fields.get("max_input_age", 60),
            intent_expires_at=fields.get("intent_expires", "2026-10-11T00:00:00Z"),
            mandate_expires_at=fields.get("mandate_expires", "2026-10-12T00:00:00Z"),
        ),
        supported_schema_variants=fields["supported"],
    )


def erc20_config(**overrides: Any) -> ApprovedAdapterConfiguration:
    allowance = overrides.pop("allowance_raw", "1000000000000000000")
    return base_config(
        input_asset_id="monad:143/wmon",
        input_token="0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A",
        input_decimals=18,
        allowance_raw=allowance,
        **overrides,
    )


FIXTURES_PATH = Path(__file__).with_name("fixtures.json")


def load_fixtures() -> dict:
    with FIXTURES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)
