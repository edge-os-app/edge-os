"""The unsigned operator transactions and the exact Privy sign request body.

A MON start builds four steps: wrap, approve, swap, revoke. A WMON start builds the last three and
uses the same nonces in sequence, so the wallet needs no MON value for the swap.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from scripts.operator_trade.calldata import approve_calldata, deposit_calldata, swap_calldata
from scripts.operator_trade.plan import TradePlan
from scripts.operator_trade.trade_file import OperatorTrade

SIGNER_METHOD = "eth_signTransaction"
SIGNER_FIELDS = frozenset({"type", "chain_id", "nonce", "to", "value", "data", "gas_limit",
                           "max_fee_per_gas", "max_priority_fee_per_gas"})


@dataclass(frozen=True)
class UnsignedTransaction:
    step: str
    nonce: int
    to: str
    value: int
    data: str
    gas_limit: int
    max_fee_per_gas: int
    max_priority_fee_per_gas: int

    def signer_body(self) -> dict[str, Any]:
        transaction = {
            "type": 2,
            "chain_id": 143,
            "nonce": self.nonce,
            "to": self.to,
            "value": self.value,
            "data": self.data,
            "gas_limit": self.gas_limit,
            "max_fee_per_gas": self.max_fee_per_gas,
            "max_priority_fee_per_gas": self.max_priority_fee_per_gas,
        }
        if set(transaction) != SIGNER_FIELDS:
            raise AssertionError("signer body fields changed")
        return {"method": SIGNER_METHOD, "params": {"transaction": transaction}}

    def request_hash(self) -> str:
        return hashlib.sha256(_canonical(self.signer_body())).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _step_call(trade: OperatorTrade, plan: TradePlan, step: str) -> tuple[str, int, str]:
    if step == "wrap":
        return trade.wmon, plan.input_raw, deposit_calldata()
    if step == "approve":
        return trade.wmon, 0, approve_calldata(trade.entrypoint, plan.input_raw)
    if step == "swap":
        return trade.entrypoint, 0, swap_calldata(trade, plan.input_raw, plan.minimum_raw)
    if step == "revoke":
        return trade.wmon, 0, approve_calldata(trade.entrypoint, 0)
    raise AssertionError("unknown step")


def build_unsigned(trade: OperatorTrade, plan: TradePlan, preflight: Any) -> tuple[UnsignedTransaction, ...]:
    limits = trade.gas_limits
    unsigned: list[UnsignedTransaction] = []
    for index, step in enumerate(trade.steps):
        to, value, data = _step_call(trade, plan, step)
        unsigned.append(UnsignedTransaction(
            step=step, nonce=preflight.nonce + index, to=to, value=value, data=data,
            gas_limit=getattr(limits, step), max_fee_per_gas=plan.max_fee_per_gas,
            max_priority_fee_per_gas=plan.max_priority_fee_per_gas))
    return tuple(unsigned)
