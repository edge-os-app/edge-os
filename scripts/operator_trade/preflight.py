"""Read-only preflight: chain, funds, pins, code hashes, nonce and fees.

Refusals happen before any journal, signature or send. Every observed code hash is public chain
data, so a mismatch reports the observed value; it never reports an RPC URL.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from eth_utils import keccak

from edge_os_api.execution.original_transaction import BALANCE_OF_SELECTOR

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.plan import FEE_BASE_MULTIPLIER
from scripts.operator_trade.rpc import OperatorRpc
from scripts.operator_trade.trade_file import OperatorTrade

TOKEN0_SELECTOR = "0x" + keccak(b"token0()")[:4].hex()
TOKEN1_SELECTOR = "0x" + keccak(b"token1()")[:4].hex()
RESERVES_SELECTOR = "0x" + keccak(b"getReserves()")[:4].hex()
ALLOWANCE_SELECTOR = "0x" + keccak(b"allowance(address,address)")[:4].hex()


@dataclass(frozen=True)
class Preflight:
    chain_id: int
    block_number: int
    native_balance: int
    wmon_balance: int
    moe_balance: int
    allowance: int
    token0: str
    token1: str
    reserve_wmon: int
    reserve_moe: int
    entrypoint_code_sha256: str
    wmon_code_sha256: str
    pool_code_sha256: str
    nonce: int
    base_fee: int
    priority_fee: int


def _address_word(value: str) -> str:
    return value[2:].lower().rjust(64, "0")


def _read_word(rpc: OperatorRpc, to: str, data: str) -> int:
    result = rpc.call("eth_call", [{"to": to, "data": data}, "latest"])
    if type(result) is not str or not result.startswith("0x") or len(result) != 66:
        raise OperatorError("PREFLIGHT_WORD_INVALID")
    return int(result[2:], 16)


def _read_address(rpc: OperatorRpc, to: str, data: str) -> str:
    return "0x" + _read_word(rpc, to, data).to_bytes(32, "big")[12:].hex()


def read_balance(rpc: OperatorRpc, token: str, wallet: str) -> int:
    return _read_word(rpc, token, BALANCE_OF_SELECTOR + _address_word(wallet))


def read_allowance(rpc: OperatorRpc, token: str, owner: str, spender: str) -> int:
    return _read_word(rpc, token, ALLOWANCE_SELECTOR + _address_word(owner) + _address_word(spender))


def read_code_sha256(rpc: OperatorRpc, address: str) -> str:
    code = rpc.call("eth_getCode", [address, "latest"])
    return hashlib.sha256(bytes.fromhex(code[2:])).hexdigest()


def read_preflight(rpc: OperatorRpc, trade: OperatorTrade) -> Preflight:
    chain_id = int(rpc.call("eth_chainId", []), 16)
    if chain_id != trade.chain_id:
        raise OperatorError("CHAIN_ID_MISMATCH", str(chain_id))
    block_number = int(rpc.call("eth_blockNumber", []), 16)
    native = int(rpc.call("eth_getBalance", [trade.wallet_address, "latest"]), 16)
    wmon_balance = read_balance(rpc, trade.wmon, trade.wallet_address)
    moe_balance = read_balance(rpc, trade.moe, trade.wallet_address)
    allowance = read_allowance(rpc, trade.wmon, trade.wallet_address, trade.entrypoint)
    token0 = _read_address(rpc, trade.pool, TOKEN0_SELECTOR)
    token1 = _read_address(rpc, trade.pool, TOKEN1_SELECTOR)
    if token0.lower() != trade.token0.lower() or token1.lower() != trade.token1.lower():
        raise OperatorError("TOKEN_ORDER_MISMATCH", f"token0={token0} token1={token1}")
    reserves = rpc.call("eth_call", [{"to": trade.pool, "data": RESERVES_SELECTOR}, "latest"])
    if type(reserves) is not str or len(reserves) < 2 + 2 * 64:
        raise OperatorError("PREFLIGHT_RESERVES_INVALID")
    words = [int(reserves[2 + index * 64:2 + (index + 1) * 64], 16) for index in range(2)]
    reserve_wmon, reserve_moe = ((words[0], words[1]) if trade.direction == 0 else (words[1], words[0]))
    code_hashes = {
        "entrypoint": read_code_sha256(rpc, trade.entrypoint),
        "wmon": read_code_sha256(rpc, trade.wmon),
        "pool": read_code_sha256(rpc, trade.pool),
    }
    for role, observed in code_hashes.items():
        if observed != trade.code_sha256[role]:
            raise OperatorError("CODE_HASH_MISMATCH", f"{role}={observed}")
    if allowance != 0:
        raise OperatorError("ALLOWANCE_NOT_ZERO", str(allowance))
    nonce = int(rpc.call("eth_getTransactionCount", [trade.wallet_address, "pending"]), 16)
    block = rpc.call("eth_getBlockByNumber", ["latest", False])
    base_fee = int(block["baseFeePerGas"], 16)
    priority_fee = int(rpc.call("eth_maxPriorityFeePerGas", []), 16)
    max_fee = FEE_BASE_MULTIPLIER * base_fee + priority_fee
    required = trade.input_raw + trade.gas_limits.total() * max_fee
    if native < required:
        raise OperatorError("INSUFFICIENT_NATIVE_BALANCE", f"{native} < {required}")
    return Preflight(
        chain_id=chain_id,
        block_number=block_number,
        native_balance=native,
        wmon_balance=wmon_balance,
        moe_balance=moe_balance,
        allowance=allowance,
        token0=token0,
        token1=token1,
        reserve_wmon=reserve_wmon,
        reserve_moe=reserve_moe,
        entrypoint_code_sha256=code_hashes["entrypoint"],
        wmon_code_sha256=code_hashes["wmon"],
        pool_code_sha256=code_hashes["pool"],
        nonce=nonce,
        base_fee=base_fee,
        priority_fee=priority_fee,
    )
