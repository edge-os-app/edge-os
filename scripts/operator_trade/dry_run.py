"""Read-only dry run: build the four unsigned calls and simulate them in order.

The simulation uses ``eth_call`` with storage overrides for the wrapped balance and the temporary
allowance. The slot layout below is the WMON token's observed layout, verified by the builder's
2026-10-22 live check (`.scratch/direct-route-l1-20261022/root/live-check1/LIVE_QUOTE_CHECK1.json`).
It is used only to simulate; the live path never overrides state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from eth_utils import keccak

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.plan import TradePlan
from scripts.operator_trade.preflight import Preflight
from scripts.operator_trade.rpc import OperatorRpc
from scripts.operator_trade.trade_file import OperatorTrade
from scripts.operator_trade.transactions import UnsignedTransaction, build_unsigned

BALANCE_SLOT = 3
ALLOWANCE_SLOT = 4


@dataclass(frozen=True)
class Simulation:
    step: str
    to: str
    value: int
    data_sha256: str
    ok: bool
    output_raw: int | None
    error_code: str | None


def _address_word(value: str) -> bytes:
    return bytes.fromhex(value[2:].lower().rjust(64, "0"))


def _word(value: int) -> str:
    return "0x" + value.to_bytes(32, "big").hex()


def _mapping_slot(wallet: str) -> str:
    return "0x" + keccak(_address_word(wallet) + BALANCE_SLOT.to_bytes(32, "big")).hex()


def _allowance_slot(wallet: str, spender: str) -> str:
    return "0x" + keccak(_address_word(spender) + bytes.fromhex(_mapping_slot(wallet)[2:])).hex()


def _overrides(trade: OperatorTrade, preflight: Preflight, balances: bool, allowance: bool) -> dict[str, object] | None:
    diff: dict[str, str] = {}
    if balances:
        diff[_mapping_slot(trade.wallet_address)] = _word(preflight.wmon_balance + trade.input_raw)
    if allowance:
        diff[_allowance_slot(trade.wallet_address, trade.entrypoint)] = _word(trade.input_raw)
    return {trade.wmon: {"stateDiff": diff}} if diff else None


def simulate(rpc: OperatorRpc, trade: OperatorTrade, plan: TradePlan, preflight: Preflight) -> tuple[Simulation, ...]:
    unsigned = build_unsigned(trade, plan, preflight)
    results: list[Simulation] = []
    for transaction in unsigned:
        if transaction.step == "wrap":
            overrides = _overrides(trade, preflight, balances=False, allowance=False)
        elif transaction.step == "approve":
            overrides = _overrides(trade, preflight, balances=True, allowance=False)
        elif transaction.step == "swap":
            overrides = _overrides(trade, preflight, balances=True, allowance=True)
        else:
            overrides = _overrides(trade, preflight, balances=False, allowance=True)
        call = {"from": trade.wallet_address, "to": transaction.to, "value": hex(transaction.value),
                "data": transaction.data}
        params: list[object] = [call, hex(preflight.block_number)]
        if overrides is not None:
            params.append(overrides)
        try:
            output = rpc.call("eth_call", params)
        except Exception as error:  # noqa: BLE001 - any refused simulation stops the dry run
            results.append(Simulation(step=transaction.step, to=transaction.to, value=transaction.value,
                                      data_sha256=_data_digest(transaction), ok=False, output_raw=None,
                                      error_code=getattr(error, "code", "SIMULATION_ERROR")))
            raise OperatorError("SIMULATION_FAILED",
                                f"{transaction.step}:{getattr(error, 'code', 'SIMULATION_ERROR')}") from error
        raw = int(output[2:], 16) if len(output) >= 66 else None
        if transaction.step == "swap":
            if raw is None or raw < plan.minimum_raw:
                results.append(Simulation(step=transaction.step, to=transaction.to, value=transaction.value,
                                          data_sha256=_data_digest(transaction), ok=False, output_raw=raw,
                                          error_code="SIMULATION_BELOW_MINIMUM"))
                raise OperatorError("SIMULATION_BELOW_MINIMUM",
                                    f"{raw} < {plan.minimum_raw}")
        results.append(Simulation(step=transaction.step, to=transaction.to, value=transaction.value,
                                  data_sha256=_data_digest(transaction), ok=True, output_raw=raw,
                                  error_code=None))
    return tuple(results)


def _data_digest(transaction: UnsignedTransaction) -> str:
    return hashlib.sha256(bytes.fromhex(transaction.data[2:])).hexdigest()
