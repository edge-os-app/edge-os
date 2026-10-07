"""Authored D01 convention examples, not a collector or production adapter.

Run with python3 docs/qualification/nansen/check_d01_profile.py.
No provider records, credentials, files or network are read.
"""

from datetime import datetime
from decimal import Decimal
from fractions import Fraction
import unittest


def freshness(available_at: str | None, checked_at: str, max_age: int) -> str:
    """Classify availability relative to an aware assessment timestamp."""
    if type(max_age) is not int or max_age < 0:
        raise ValueError("age limit must be nonnegative integer seconds")
    checked = datetime.fromisoformat(checked_at)
    if checked.utcoffset() is None:
        raise ValueError("assessment timestamp requires an offset")
    if available_at is None:
        return "unknown"
    available = datetime.fromisoformat(available_at)
    if available.utcoffset() is None:
        raise ValueError("availability timestamp requires an offset")
    age = (checked - available).total_seconds()
    if age < 0:
        return "not_yet_available"
    return "stale" if age > max_age else "within_declared_age"


def may_reserve(attempts: list[tuple[str, str]], next_credits: str = "5") -> bool:
    """Check conservative reservations against fixed five-call/25-credit caps."""
    credits = [Decimal(value) for _, value in attempts]
    reserve = Decimal(next_credits)
    if any(not value.is_finite() or value < 0 for value in credits):
        raise ValueError("prior reservations require finite nonnegative credits")
    if not reserve.is_finite() or reserve <= 0:
        raise ValueError("next reservation requires finite positive credits")
    return (
        len(attempts) < 5
        and all(state == "settled" for state, _ in attempts)
        and sum((Fraction(value) for value in credits), Fraction())
        + Fraction(reserve) <= 25
    )


def supply_percentage(
    amounts: list[str | None], supply: str | None, units_qualified: bool
) -> Fraction | None:
    """Use an independently documented supply in the same qualified units."""
    if not units_qualified or supply is None or not amounts or None in amounts:
        return None
    denominator = Decimal(supply)
    values = [Decimal(value) for value in amounts if value is not None]
    if not denominator.is_finite() or denominator <= 0:
        raise ValueError("supply requires a finite positive value")
    if any(not value.is_finite() or value < 0 for value in values):
        raise ValueError("balances require finite nonnegative values")
    total = sum((Fraction(value) for value in values), Fraction())
    if total > Fraction(denominator):
        raise ValueError("selected balances exceed documented supply")
    return total * 100 / Fraction(denominator)


class Controls(unittest.TestCase):
    """Independent examples at the intake's agreed calculation/control seams."""

    def test_future_availability_is_not_fresh(self) -> None:
        self.assertEqual(
            freshness("2026-01-01T10:00:00Z", "2026-01-01T09:00:00Z", 300),
            "not_yet_available",
        )

    def test_credit_only_exhaustion(self) -> None:
        self.assertFalse(may_reserve([("settled", "21")]))

    def test_separate_request_cap_and_credit_boundary(self) -> None:
        self.assertFalse(may_reserve([("settled", "1")] * 5))
        self.assertTrue(may_reserve([("settled", "5")] * 4))
        self.assertTrue(may_reserve([("settled", "20")]))
        for state in ("reserved", "stopped", "unknown"):
            self.assertFalse(may_reserve([(state, "1")]))
        for credits in ("-1", "NaN", "Infinity"):
            with self.assertRaises(ValueError):
                may_reserve([("settled", credits)])
        for reserve in ("0", "-1", "NaN", "Infinity"):
            with self.assertRaises(ValueError):
                may_reserve([], reserve)

    def test_freshness_boundary_unknown_and_stale(self) -> None:
        checked = "2026-01-01T09:00:00Z"
        for available, expected in (
            (None, "unknown"),
            (checked, "within_declared_age"),
            ("2026-01-01T08:55:00Z", "within_declared_age"),
            ("2026-01-01T08:54:59Z", "stale"),
            ("2026-01-01T10:00:00+01:00", "within_declared_age"),
        ):
            self.assertEqual(freshness(available, checked, 300), expected)
        with self.assertRaises(ValueError):
            freshness(checked, "2026-01-01T09:00:00", 300)
        with self.assertRaises(ValueError):
            freshness("2026-01-01T09:00:00", checked, 300)
        for limit in (-1, True):
            with self.assertRaises(ValueError):
                freshness(checked, checked, limit)

    def test_partial_inventory_uses_supply_not_page_sum(self) -> None:
        self.assertEqual(supply_percentage(["2.5", "1"], "10", True), 35)
        self.assertIsNone(supply_percentage(["2.5"], "10", False))
        self.assertIsNone(supply_percentage(["2.5"], None, True))
        self.assertIsNone(supply_percentage([None], "10", True))
        self.assertIsNone(supply_percentage([], "10", True))
        self.assertEqual(supply_percentage(["0"], "10", True), 0)
        self.assertEqual(supply_percentage(["1"], "3", True), Fraction(100, 3))
        for denominator in ("0", "-1", "NaN", "Infinity"):
            with self.assertRaises(ValueError):
                supply_percentage(["1"], denominator, True)
        for value in ("-1", "NaN", "Infinity", "11"):
            with self.assertRaises(ValueError):
                supply_percentage([value], "10", True)


if __name__ == "__main__":
    unittest.main()
