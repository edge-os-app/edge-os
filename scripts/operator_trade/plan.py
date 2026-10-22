"""Plan math for one operator trade: expected output, local minimum and the USD ceiling.

The output formula and pinned fee are the merged direct-route formula. The worst-case cost counts
the MON value plus gas for all four transactions at the same ``max_fee_per_gas`` that each signed
transaction will carry.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.trade_file import GasLimits, OperatorTrade

PROGRAM_FEE_SCALE = 10**6
MAX_SIGNER_SAFE_INTEGER = 2**53 - 1
FEE_BASE_MULTIPLIER = 2
WEI_PER_MON = 10**18


@dataclass(frozen=True)
class TradePlan:
    input_raw: int
    expected_raw: int
    minimum_raw: int
    slippage_bps: int
    base_fee: int
    priority_fee: int
    max_fee_per_gas: int
    max_priority_fee_per_gas: int
    total_gas: int
    gas_wei: int
    worst_case_wei: int
    worst_case_usd: Decimal
    usd_ceiling: Decimal
    input_above_signer_safe_integer: bool


def expected_output(amount: int, reserve_in: int, reserve_out: int, fee_ppm: int) -> int:
    if not all(type(value) is int for value in (amount, reserve_in, reserve_out, fee_ppm)):
        raise OperatorError("QUOTE_INPUT_INVALID")
    if amount <= 0 or reserve_in <= 0 or reserve_out <= 0:
        raise OperatorError("QUOTE_RESERVES_EMPTY")
    if not 0 < fee_ppm < PROGRAM_FEE_SCALE:
        raise OperatorError("QUOTE_FEE_INVALID")
    output = amount * (PROGRAM_FEE_SCALE - fee_ppm) * reserve_out // (
        reserve_in * PROGRAM_FEE_SCALE + amount * (PROGRAM_FEE_SCALE - fee_ppm)
    )
    if output <= 0:
        raise OperatorError("QUOTE_OUTPUT_ZERO")
    return output


def minimum_output(expected_raw: int, slippage_bps: int) -> int:
    if not 0 <= slippage_bps <= 10000:
        raise OperatorError("PLAN_SLIPPAGE_INVALID")
    return expected_raw * (10000 - slippage_bps) // 10000


def max_fee_per_gas(base_fee: int, priority_fee: int) -> int:
    if not all(type(value) is int and value >= 0 for value in (base_fee, priority_fee)):
        raise OperatorError("PLAN_FEE_INVALID")
    return FEE_BASE_MULTIPLIER * base_fee + priority_fee


def worst_case_wei_cost(value_wei: int, gas_limits: GasLimits, max_fee: int) -> int:
    return value_wei + gas_limits.total() * max_fee


def worst_case_usd_cost(value_wei: int, gas_limits: GasLimits, max_fee: int, price: Decimal) -> Decimal:
    return Decimal(worst_case_wei_cost(value_wei, gas_limits, max_fee)) * price / Decimal(WEI_PER_MON)


def plan_trade(trade: OperatorTrade, *, base_fee: int, priority_fee: int, reserve_wmon: int, reserve_moe: int) -> TradePlan:
    fee = max_fee_per_gas(base_fee, priority_fee)
    if fee > MAX_SIGNER_SAFE_INTEGER or priority_fee > MAX_SIGNER_SAFE_INTEGER:
        raise OperatorError("FEE_ABOVE_SIGNER_LIMIT")
    reserve_in, reserve_out = ((reserve_wmon, reserve_moe) if trade.direction == 0
                               else (reserve_moe, reserve_wmon))
    expected = expected_output(trade.input_raw, reserve_in, reserve_out, trade.program_fee_ppm)
    minimum = minimum_output(expected, trade.slippage_bps)
    gas_wei = trade.gas_limits.total() * fee
    worst_wei = trade.input_raw + gas_wei
    usd = Decimal(worst_wei) * trade.mon_usd_price / Decimal(WEI_PER_MON)
    if usd > trade.usd_ceiling:
        raise OperatorError("USD_CEILING_EXCEEDED", f"{usd:.6f} > {trade.usd_ceiling_text}")
    if trade.usd_ceiling > Decimal("2.00"):
        raise OperatorError("USD_CEILING_EXCEEDED", "the absolute limit is USD 2.00")
    return TradePlan(
        input_raw=trade.input_raw,
        expected_raw=expected,
        minimum_raw=minimum,
        slippage_bps=trade.slippage_bps,
        base_fee=base_fee,
        priority_fee=priority_fee,
        max_fee_per_gas=fee,
        max_priority_fee_per_gas=priority_fee,
        total_gas=trade.gas_limits.total(),
        gas_wei=gas_wei,
        worst_case_wei=worst_wei,
        worst_case_usd=usd,
        usd_ceiling=trade.usd_ceiling,
        input_above_signer_safe_integer=trade.input_raw > MAX_SIGNER_SAFE_INTEGER,
    )
