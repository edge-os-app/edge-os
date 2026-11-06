"""Plan math: the direct-route formula, the minimum and the USD 2.00 worst-case ceiling."""

from __future__ import annotations

from decimal import Decimal

import pytest

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.plan import expected_output, minimum_output, plan_trade, worst_case_usd_cost
from scripts.operator_trade.trade_file import GasLimits

from ._support import INPUT, trade_dict
from scripts.operator_trade.trade_file import OperatorTrade, load_trade_file
from pathlib import Path
import json


def _trade(tmp_path: Path, **overrides: object) -> OperatorTrade:
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict(**overrides)), encoding="utf-8")
    return load_trade_file(path)


def test_expected_output_matches_the_live_check_fixture() -> None:
    # LIVE_QUOTE_CHECK1.json: 50 WMON, reserves 862430562121790033386323 / 65519655595145240989629270.
    assert expected_output(INPUT, 862430562121790033386323, 65519655595145240989629270, 16000) == 3_737_556_748_405_128_021_448


def test_expected_output_refuses_empty_reserves() -> None:
    with pytest.raises(OperatorError):
        expected_output(INPUT, 0, 1, 16000)


def test_minimum_uses_floor_and_the_trade_slippage() -> None:
    expected = 3_737_556_748_405_128_021_448
    assert minimum_output(expected, 100) == expected * 9900 // 10000
    assert minimum_output(expected, 0) == expected
    assert minimum_output(expected, 10000) == 0


def test_worst_case_cost_includes_the_value_and_all_four_gas_limits() -> None:
    limits = GasLimits(wrap=60_000, approve=60_000, swap=400_000, revoke=60_000)
    max_fee = 5_000_000_000
    value = INPUT
    assert worst_case_usd_cost(value, limits, max_fee, Decimal("0.02")) == (
        Decimal(value + 580_000 * max_fee) * Decimal("0.02") / Decimal(10**18)
    )


def test_plan_sets_the_max_fee_and_the_local_minimum(tmp_path: Path) -> None:
    trade = _trade(tmp_path)
    plan = plan_trade(trade, base_fee=1_000_000_000, priority_fee=1_000_000_000, reserve_wmon=862430562121790033386323, reserve_moe=65519655595145240989629270)
    assert plan.max_fee_per_gas == 3_000_000_000
    assert plan.expected_raw == 3_737_556_748_405_128_021_448
    assert plan.minimum_raw == plan.expected_raw * 9900 // 10000
    assert plan.worst_case_wei == INPUT + 580_000 * 3_000_000_000
    assert plan.worst_case_usd < Decimal("2.00")


def test_plan_refuses_above_the_usd_ceiling(tmp_path: Path) -> None:
    trade = _trade(tmp_path, mon_usd_price="0.10")
    with pytest.raises(OperatorError) as caught:
        plan_trade(trade, base_fee=1_000_000_000, priority_fee=1_000_000_000, reserve_wmon=862430562121790033386323, reserve_moe=65519655595145240989629270)
    assert caught.value.code == "USD_CEILING_EXCEEDED"


def test_plan_refuses_a_trade_file_ceiling_above_two_dollars(tmp_path: Path) -> None:
    with pytest.raises(OperatorError):
        _trade(tmp_path, usd_ceiling="2.01")


def test_plan_refuses_a_fee_above_the_signer_safe_integer(tmp_path: Path) -> None:
    trade = _trade(tmp_path)
    with pytest.raises(OperatorError) as caught:
        plan_trade(trade, base_fee=2**52, priority_fee=2**52, reserve_wmon=862430562121790033386323, reserve_moe=65519655595145240989629270)
    assert caught.value.code == "FEE_ABOVE_SIGNER_LIMIT"


def test_plan_reports_the_signer_quantity_limit_for_a_large_input(tmp_path: Path) -> None:
    trade = _trade(tmp_path)
    plan = plan_trade(trade, base_fee=1_000_000_000, priority_fee=1_000_000_000, reserve_wmon=862430562121790033386323, reserve_moe=65519655595145240989629270)
    assert plan.input_above_signer_safe_integer is True
