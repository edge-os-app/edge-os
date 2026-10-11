"""Independent tests for the capacity arithmetic used by WORKED_CAPACITY.md."""

from __future__ import annotations

import unittest
from fractions import Fraction

import capacity_examples as capacity


class AverageBasisTest(unittest.TestCase):
    def test_p15_cost_example(self) -> None:
        # 10 units at 1000, then 10 units at 1200 -> 20 units, 2200 cost.
        average = capacity.average_basis(20, 2200)
        self.assertEqual(average, Fraction(110))

    def test_zero_units_rejected(self) -> None:
        with self.assertRaises(capacity.CapacityError):
            capacity.average_basis(0, 0)


class PartialExitTest(unittest.TestCase):
    def test_removed_basis(self) -> None:
        self.assertEqual(capacity.removed_basis(Fraction(110), 5), Fraction(550))

    def test_realized_result(self) -> None:
        removed = capacity.removed_basis(Fraction(110), 5)
        self.assertEqual(capacity.realized_result(650, removed), Fraction(100))


class AllowanceTest(unittest.TestCase):
    def test_p15_allowance_example(self) -> None:
        # 500 approved, 300 consumed, 100 reserved -> 100 remaining.
        self.assertEqual(capacity.allowance_remaining(500, 300, 100), 100)

    def test_overdraw_rejected(self) -> None:
        with self.assertRaises(capacity.CapacityError):
            capacity.allowance_remaining(500, 300, 201)

    def test_two_positions_share_one_asset(self) -> None:
        # 1000 approved, 0 consumed, 500 reserved by two positions -> 500 left.
        self.assertEqual(capacity.allowance_remaining(1000, 0, 500), 500)
        # A competing 600 request exceeds the 500 remaining.
        self.assertGreater(600, capacity.allowance_remaining(1000, 0, 500))

    def test_partial_exit_reduces_remaining_sell(self) -> None:
        # 3000 sell allowance, 500 consumed by a partial exit, 200 reserved.
        self.assertEqual(capacity.sell_reserved_remaining(3000, 500, 200), 2300)


class GasTest(unittest.TestCase):
    def test_gas_reserved_two_entries(self) -> None:
        self.assertEqual(capacity.gas_reserved(4000000000000000, 4000000000000000), 8000000000000000)

    def test_gas_per_acquisition(self) -> None:
        # 0.002 entry + 0.002 retained exit = 0.004 per acquisition.
        self.assertEqual(capacity.gas_reserved(2000000000000000, 2000000000000000), 4000000000000000)

    def test_gas_total_two_acquisitions(self) -> None:
        self.assertEqual(capacity.gas_total(4000000000000000, 2), 8000000000000000)

    def test_gas_total_three_acquisitions(self) -> None:
        # Two entries plus one addition, all reserved at the checkpoint.
        self.assertEqual(capacity.gas_total(4000000000000000, 3), 12000000000000000)

    def test_gas_remaining_after_three_acquisitions(self) -> None:
        self.assertEqual(300000000000000000 - capacity.gas_total(4000000000000000, 3), 288000000000000000)

    def test_gas_negative_rejected(self) -> None:
        with self.assertRaises(capacity.CapacityError):
            capacity.gas_reserved(-1, 0)


if __name__ == "__main__":
    unittest.main()
