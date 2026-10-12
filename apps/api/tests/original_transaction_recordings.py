"""The only writer of the authored original-transaction recordings (#58 ORIGINAL-LOCAL).

Run `uv run python tests/original_transaction_recordings.py` from `apps/api` to rewrite
`tests/fixtures/original_transaction/original_transaction_v1.json`.

Everything here is AUTHORED. Native shapes follow the public documentation only:
- route quote: the Monad Kuru Flow guide `transaction.calldata` response (K2), with the accepted P20 authored
  selector stand-in and program bytes;
- signer reply: Privy `POST /v1/wallets/{wallet_id}/rpc` `eth_signTransaction` → `data.signed_transaction`,
  `data.encoding = "rlp"`;
- chain reads: Ethereum JSON-RPC `eth_getTransactionCount`, `eth_sendRawTransaction`, `eth_getTransactionReceipt`,
  `eth_getBlockByNumber`, `eth_getBalance`, `eth_call`.

The signatures use the eth-account documentation's published example key (sender
0x2c7536E3605D9C16a7a3D7b1898e529396a65c23). It is a public test key, never a real wallet, and the
application never holds it: tests replay the frozen bytes. No response was captured from any provider.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eth_account import Account
from eth_utils import keccak

from edge_os_api.execution.original_transaction import (
    BALANCE_OF_SELECTOR,
    DECIMALS_SELECTOR,
    TRANSFER_TOPIC,
    signing_request_key,
)

OUTPUT = Path(__file__).parent / "fixtures" / "original_transaction" / "original_transaction_v1.json"
PUBLISHED_TEST_KEY = "0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"
WALLET = "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23"
CHAIN_ID = 143
QUOTE_TOKEN = "0x2222222222222222222222222222222222222222"  # the fixture revision's quote asset (6 decimals)
BASE_TOKEN = "0x1111111111111111111111111111111111111111"  # its base asset (18 decimals)
ENTRYPOINT = "0x00000000000000000000000000000000000f1007"  # authored; not a deployed address
SELECTOR = "0x12345678"  # the accepted P20 authored selector stand-in
PROGRAM_HEX = "0xdeadbeef"
ZERO = "0x0000000000000000000000000000000000000000"
ROUTE_PROFILE = {"chain_id": CHAIN_ID, "entrypoint": ENTRYPOINT, "method": "EXECUTE_SWAP", "selector": SELECTOR,
                 "program_hex": PROGRAM_HEX, "fee_bps": 0, "referrer_fee_bps": 0, "fee_collector": ZERO,
                 "referrer": ZERO, "is_in_token_fee": False, "min_output_bps": 9900,
                 "max_quote_age_seconds": 60, "max_input_age_seconds": 300, "gas_limit": 300000,
                 "max_fee_per_gas": 3000000000, "max_priority_fee_per_gas": 1000000000}
# (operation, sell token, sell raw, buy token, expected output raw): the fixture journey's two actions.
ACTIONS = (("ENTRY", QUOTE_TOKEN, 100000000, BASE_TOKEN, 50000000000000000000),
           ("EXIT", BASE_TOKEN, 50000000000000000000, QUOTE_TOKEN, 100000000))
NONCES = range(8)
GAS_USED, EFFECTIVE_GAS_PRICE = 150000, 2000000000
def word(value: int | str) -> bytes:
    if isinstance(value, str):
        return bytes(12) + bytes.fromhex(value[2:])
    return value.to_bytes(32, "big")


def data_word(value: int) -> str:
    """JSON-RPC unformatted `DATA`: one 32-byte ABI word, as `eth_call` results and log data carry it."""
    return "0x" + word(value).hex()


# `eth_getBalance` and block fields are `QUANTITY`; `eth_call` results (`balanceOf`, `decimals`) are `DATA` words.
HOLDINGS = {"block_number": "0x1e8480", "age_seconds": 12, "finality": "finalized", "native": hex(10**18),
            "tokens": {QUOTE_TOKEN: data_word(1000000000), BASE_TOKEN: data_word(50 * 10**18)},
            "decimals": {QUOTE_TOKEN: data_word(6), BASE_TOKEN: data_word(18)}}


def calldata(sell: str, amount: int, buy: str, minimum: int) -> str:
    """`executeSwap(SwapIntent, FeeCollection, bytes)` in the accepted P20 layout."""
    program = bytes.fromhex(PROGRAM_HEX[2:])
    head = b"".join([word(buy), word(minimum), word(sell), word(amount), word(ZERO), word(0), word(ZERO), word(0),
                     word(0), word(10 * 32)])
    region = word(len(program)) + program + bytes(-len(program) % 32)
    return SELECTOR[2:] + (head + region).hex()


def unsigned(nonce: int, data: str) -> dict[str, Any]:
    return {"type": 2, "chain_id": CHAIN_ID, "nonce": nonce, "to": ENTRYPOINT, "value": 0, "data": "0x" + data,
            "gas_limit": ROUTE_PROFILE["gas_limit"], "max_fee_per_gas": ROUTE_PROFILE["max_fee_per_gas"],
            "max_priority_fee_per_gas": ROUTE_PROFILE["max_priority_fee_per_gas"]}


def topic(address: str) -> str:
    return "0x" + word(address.lower()).hex()


def receipt(tx_hash: str, sell: str, amount: int, buy: str, output: int) -> dict[str, Any]:
    def transfer(token: str, source: str, target: str, raw: int) -> dict[str, Any]:
        return {"address": token, "topics": [TRANSFER_TOPIC, topic(source), topic(target)], "data": data_word(raw)}

    return {"transactionHash": tx_hash, "status": "0x1", "from": WALLET.lower(), "to": ENTRYPOINT,
            "blockNumber": "0x1e8481", "gasUsed": hex(GAS_USED), "effectiveGasPrice": hex(EFFECTIVE_GAS_PRICE),
            "logs": [transfer(sell, WALLET, ENTRYPOINT, amount), transfer(buy, ENTRYPOINT, WALLET, output)]}


def build() -> dict[str, Any]:
    assert Account.from_key(PUBLISHED_TEST_KEY).address == WALLET
    routes, signatures, receipts, hashes = [], [], {}, {}
    for operation, sell, amount, buy, output in ACTIONS:
        minimum = output * ROUTE_PROFILE["min_output_bps"] // 10000
        data = calldata(sell, amount, buy, minimum)
        routes.append({"request": {"sell_token": sell, "buy_token": buy, "amount": str(amount)},
                       "response": {"output": str(output), "minOut": str(minimum),
                                    "transaction": {"to": ENTRYPOINT, "value": 0, "calldata": data},
                                    "gasPrices": {"standard": str(EFFECTIVE_GAS_PRICE)}}})
        for nonce in NONCES:
            fields = unsigned(nonce, data)
            signed = Account.sign_transaction(
                {"type": 2, "chainId": CHAIN_ID, "nonce": nonce, "to": ENTRYPOINT, "value": 0, "data": fields["data"],
                 "gas": fields["gas_limit"], "maxFeePerGas": fields["max_fee_per_gas"],
                 "maxPriorityFeePerGas": fields["max_priority_fee_per_gas"], "accessList": []}, PUBLISHED_TEST_KEY)
            raw = "0x" + bytes(signed.raw_transaction).hex()
            tx_hash = "0x" + keccak(bytes(signed.raw_transaction)).hex()
            signatures.append({"request_key": signing_request_key(fields), "operation": operation, "nonce": nonce,
                               "response": {"method": "eth_signTransaction",
                                            "data": {"signed_transaction": raw, "encoding": "rlp"}}})
            hashes[raw] = tx_hash
            receipts[tx_hash] = receipt(tx_hash, sell, amount, buy, output)
    return {"schema": "edge-os.original-transaction-recordings/1", "label": "AUTHORED",
            "notice": ("Authored native-shaped responses. Signed with the eth-account documentation's published "
                       "example key; no provider response was captured and no real wallet exists."),
            "wallet_address": WALLET, "chain_id": CHAIN_ID, "route_profile": ROUTE_PROFILE,
            "selectors": {"balance_of": BALANCE_OF_SELECTOR, "decimals": DECIMALS_SELECTOR},
            "routes": routes, "signatures": signatures, "transaction_hashes": hashes, "receipts": receipts,
            "holdings": HOLDINGS}


def write() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    write()
