"""The four unsigned operator transactions and the exact Privy sign request body."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from scripts.operator_trade.calldata import approve_calldata, deposit_calldata, swap_calldata
from scripts.operator_trade.plan import TradePlan
from scripts.operator_trade.trade_file import OperatorTrade

STEPS = ("wrap", "approve", "swap", "revoke")
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


def build_unsigned(trade: OperatorTrade, plan: TradePlan, preflight: Any) -> tuple[UnsignedTransaction, ...]:
    limits = trade.gas_limits
    nonce = preflight.nonce
    return (
        UnsignedTransaction(step="wrap", nonce=nonce, to=trade.wmon, value=plan.input_raw,
                            data=deposit_calldata(), gas_limit=limits.wrap,
                            max_fee_per_gas=plan.max_fee_per_gas,
                            max_priority_fee_per_gas=plan.max_priority_fee_per_gas),
        UnsignedTransaction(step="approve", nonce=nonce + 1, to=trade.wmon, value=0,
                            data=approve_calldata(trade.entrypoint, plan.input_raw), gas_limit=limits.approve,
                            max_fee_per_gas=plan.max_fee_per_gas,
                            max_priority_fee_per_gas=plan.max_priority_fee_per_gas),
        UnsignedTransaction(step="swap", nonce=nonce + 2, to=trade.entrypoint, value=0,
                            data=swap_calldata(trade, plan.input_raw, plan.minimum_raw), gas_limit=limits.swap,
                            max_fee_per_gas=plan.max_fee_per_gas,
                            max_priority_fee_per_gas=plan.max_priority_fee_per_gas),
        UnsignedTransaction(step="revoke", nonce=nonce + 3, to=trade.wmon, value=0,
                            data=approve_calldata(trade.entrypoint, 0), gas_limit=limits.revoke,
                            max_fee_per_gas=plan.max_fee_per_gas,
                            max_priority_fee_per_gas=plan.max_priority_fee_per_gas),
    )
