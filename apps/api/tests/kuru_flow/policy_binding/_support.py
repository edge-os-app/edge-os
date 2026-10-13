"""Independent test support for the offline policy binding.

The encoder and approved configuration come from the adapter's own test
support. This module adds only the authored facts a local policy simulation
needs. Nothing here contacts a provider.
"""

from __future__ import annotations

from typing import Any

from edge_os_api.kuru_flow.flow_calldata import decode_flow_call
from edge_os_api.kuru_flow.policy_binding import (
    PolicyFacts,
    facts_from_decoded_call,
)
from edge_os_api.kuru_flow.types import NATIVE_TOKEN_ADDRESS

from kuru_flow._support import (
    MAINNET_ENTRYPOINT,
    USDC_MAINNET,
    WALLET,
    encode_execute_swap,
    encode_execute_swap_with_receiver,
)

MAINNET = "monad:143"
RPC_METHOD = "eth_signTransaction"


def approved_call() -> Any:
    return decode_flow_call(data_hex=encode_execute_swap(), method="EXECUTE_SWAP")


def receiver_call() -> Any:
    return decode_flow_call(
        data_hex=encode_execute_swap_with_receiver(receiver=WALLET),
        method="EXECUTE_SWAP_WITH_RECEIVER",
    )


def valid_value_raw(call: Any) -> str:
    """The native value a correct caller sends: the input for native, else zero."""
    if call.intent.token_user_sells.lower() == NATIVE_TOKEN_ADDRESS:
        return call.intent.amount_user_sells
    return "0"


def facts_for(call: Any, **overrides: Any) -> PolicyFacts:
    base = facts_from_decoded_call(
        chain_id=143,
        entrypoint_address=MAINNET_ENTRYPOINT,
        rpc_method=RPC_METHOD,
        value_raw=valid_value_raw(call),
        call=call,
    )
    if not overrides:
        return base
    return base.model_copy(update=overrides)


def facts_with_argument(name: str, value: str, **overrides: Any) -> PolicyFacts:
    facts = facts_for(approved_call(), **overrides)
    arguments = dict(facts.arguments)
    arguments[name] = value
    return facts.model_copy(update={"arguments": arguments})


OTHER_ADDRESS = "0x00000000000000000000000000000000000000C3"
