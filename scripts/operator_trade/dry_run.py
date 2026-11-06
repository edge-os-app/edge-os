"""Read-only dry run: build the unsigned calls and simulate them in order.

Each step gets ``eth_estimateGas`` and an ``eth_call`` that carries the trade file's gas limit. The
call fails the plan when that limit is below ``ceil(estimate * 1.2)``, with ``GAS_LIMIT_TOO_LOW``.
The margin allows for a small state change between the simulation block and the receipt.

The simulation uses ``eth_call`` with storage overrides for the wrapped balance and the temporary
allowance. The slot layout below is the WMON token's observed layout, verified by the builder's
2026-10-22 live check (`.scratch/direct-route-l1-20261022/root/live-check1/LIVE_QUOTE_CHECK1.json`).
It is used only to simulate; the live path never overrides state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from eth_utils import keccak

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.plan import TradePlan
from scripts.operator_trade.preflight import Preflight
from scripts.operator_trade.rpc import OperatorRpc
from scripts.operator_trade.trade_file import OperatorTrade
from scripts.operator_trade.transactions import UnsignedTransaction, build_unsigned

BALANCE_SLOT = 3
ALLOWANCE_SLOT = 4
GAS_MARGIN_NUM = 6
GAS_MARGIN_DEN = 5


@dataclass(frozen=True)
class Simulation:
    step: str
    to: str
    value: int
    gas_limit: int
    gas_estimate: int | None
    data_sha256: str
    ok: bool
    output_raw: int | None
    error_code: str | None


def required_gas_limit(estimate: int) -> int:
    """``ceil(estimate * 6 / 5)``: the limit must hold the estimate plus a 20 percent margin."""
    return -(-estimate * GAS_MARGIN_NUM // GAS_MARGIN_DEN)


def _address_word(value: str) -> bytes:
    return bytes.fromhex(value[2:].lower().rjust(64, "0"))


def _word(value: int) -> str:
    return "0x" + value.to_bytes(32, "big").hex()


def _mapping_slot(wallet: str, base_slot: int) -> str:
    return "0x" + keccak(_address_word(wallet) + base_slot.to_bytes(32, "big")).hex()


def _balance_slot(wallet: str) -> str:
    return _mapping_slot(wallet, BALANCE_SLOT)


def _allowance_slot(wallet: str, spender: str) -> str:
    return "0x" + keccak(_address_word(spender) + bytes.fromhex(_mapping_slot(wallet, ALLOWANCE_SLOT)[2:])).hex()


def _overrides(trade: OperatorTrade, preflight: Preflight, balances: bool, allowance: bool) -> dict[str, object] | None:
    diff: dict[str, str] = {}
    if balances:
        credit = trade.input_raw if trade.start == "MON" else 0
        diff[_balance_slot(trade.wallet_address)] = _word(preflight.wmon_balance + credit)
    if allowance:
        diff[_allowance_slot(trade.wallet_address, trade.entrypoint)] = _word(trade.input_raw)
    return {trade.wmon: {"stateDiff": diff}} if diff else None


def _overrides_for(transaction: UnsignedTransaction, trade: OperatorTrade,
                   preflight: Preflight) -> dict[str, object] | None:
    if transaction.step == "wrap":
        return _overrides(trade, preflight, balances=False, allowance=False)
    if transaction.step == "approve":
        return _overrides(trade, preflight, balances=True, allowance=False)
    if transaction.step == "swap":
        return _overrides(trade, preflight, balances=True, allowance=True)
    return _overrides(trade, preflight, balances=False, allowance=True)


def _call(trade: OperatorTrade, transaction: UnsignedTransaction, *, gas: int | None) -> dict[str, Any]:
    call: dict[str, Any] = {"from": trade.wallet_address, "to": transaction.to,
                            "value": hex(transaction.value), "data": transaction.data}
    if gas is not None:
        call["gas"] = hex(gas)
    return call


def _params(call: dict[str, Any], preflight: Preflight, overrides: dict[str, object] | None) -> list[object]:
    params: list[object] = [call, hex(preflight.block_number)]
    if overrides is not None:
        params.append(overrides)
    return params


def simulate(rpc: OperatorRpc, trade: OperatorTrade, plan: TradePlan, preflight: Preflight) -> tuple[Simulation, ...]:
    unsigned = build_unsigned(trade, plan, preflight)
    results: list[Simulation] = []
    for transaction in unsigned:
        overrides = _overrides_for(transaction, trade, preflight)
        try:
            estimate = int(rpc.call("eth_estimateGas",
                                    _params(_call(trade, transaction, gas=None), preflight, overrides)), 16)
        except Exception as error:  # noqa: BLE001 - any refused estimate stops the dry run
            results.append(_failed(transaction, None, getattr(error, "code", "SIMULATION_ERROR")))
            raise OperatorError("SIMULATION_FAILED",
                                f"{transaction.step}:{getattr(error, 'code', 'SIMULATION_ERROR')}") from error
        required = required_gas_limit(estimate)
        if transaction.gas_limit < required:
            results.append(_failed(transaction, estimate, "GAS_LIMIT_TOO_LOW"))
            raise OperatorError("GAS_LIMIT_TOO_LOW",
                                f"{transaction.step} gas_limit={transaction.gas_limit} "
                                f"estimate={estimate} required={required}")
        try:
            output = rpc.call("eth_call",
                              _params(_call(trade, transaction, gas=transaction.gas_limit), preflight, overrides))
        except Exception as error:  # noqa: BLE001 - any refused simulation stops the dry run
            results.append(_failed(transaction, estimate, getattr(error, "code", "SIMULATION_ERROR")))
            raise OperatorError("SIMULATION_FAILED",
                                f"{transaction.step}:{getattr(error, 'code', 'SIMULATION_ERROR')}") from error
        raw = int(output[2:], 16) if len(output) >= 66 else None
        if transaction.step == "swap":
            if raw is None or raw < plan.minimum_raw:
                results.append(_failed(transaction, estimate, "SIMULATION_BELOW_MINIMUM", raw))
                raise OperatorError("SIMULATION_BELOW_MINIMUM", f"{raw} < {plan.minimum_raw}")
        results.append(Simulation(step=transaction.step, to=transaction.to, value=transaction.value,
                                  gas_limit=transaction.gas_limit, gas_estimate=estimate,
                                  data_sha256=_data_digest(transaction), ok=True, output_raw=raw,
                                  error_code=None))
    return tuple(results)


def _failed(transaction: UnsignedTransaction, estimate: int | None, code: str,
            raw: int | None = None) -> Simulation:
    return Simulation(step=transaction.step, to=transaction.to, value=transaction.value,
                      gas_limit=transaction.gas_limit, gas_estimate=estimate,
                      data_sha256=_data_digest(transaction), ok=False, output_raw=raw, error_code=code)


def _data_digest(transaction: UnsignedTransaction) -> str:
    return hashlib.sha256(bytes.fromhex(transaction.data[2:])).hexdigest()
