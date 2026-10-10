"""Independent capacity arithmetic for the P21 worked examples.

Standard library only. These pure functions back the numeric examples in
WORKED_CAPACITY.md. They are not production admission logic and they do not
read a wallet, ledger or provider. The accepted meanings come from the P15
contract; the reference literals come from the accepted P15 fixture.

Public interface:
    average_basis(total_units, total_cost_quote) -> Fraction
    removed_basis(average, exited_units) -> Fraction
    realized_result(proceeds_quote, removed) -> Fraction
    allowance_remaining(approved, consumed, reserved) -> int
    gas_reserved(entry_gas, exit_gas) -> int
    sell_reserved_remaining(sell_allowance, consumed, reserved) -> int
"""

from __future__ import annotations

import sys
from fractions import Fraction
from typing import Iterable


class CapacityError(ValueError):
    """Raised when a capacity input violates the P15 relationships."""


def _nonneg(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CapacityError(f"{field} must be an integer")
    if value < 0:
        raise CapacityError(f"{field} must not be negative")
    return value


def average_basis(total_units: int, total_cost_quote: int) -> Fraction:
    """Weighted-average acquisition cost per unit."""
    _nonneg(total_units, "total_units")
    _nonneg(total_cost_quote, "total_cost_quote")
    if total_units == 0:
        raise CapacityError("total_units must be positive")
    return Fraction(total_cost_quote, total_units)


def removed_basis(average: Fraction, exited_units: int) -> Fraction:
    """Cost basis removed by a partial exit: exited units * average basis."""
    _nonneg(exited_units, "exited_units")
    return Fraction(average) * exited_units


def realized_result(proceeds_quote: int, removed: Fraction) -> Fraction:
    """Realized result before fees in the quote asset."""
    _nonneg(proceeds_quote, "proceeds_quote")
    return Fraction(proceeds_quote) - Fraction(removed)


def allowance_remaining(approved: int, consumed: int, reserved: int) -> int:
    """remaining = approved - consumed - reserved, with the P15 bound."""
    _nonneg(approved, "approved")
    _nonneg(consumed, "consumed")
    _nonneg(reserved, "reserved")
    if consumed + reserved > approved:
        raise CapacityError("consumed + reserved exceeds approved")
    return approved - consumed - reserved


def gas_reserved(entry_gas: int, exit_gas: int) -> int:
    """Native gas reserved for an entry plus its retained exit."""
    return _nonneg(entry_gas, "entry_gas") + _nonneg(exit_gas, "exit_gas")


def sell_reserved_remaining(sell_allowance: int, consumed: int, reserved: int) -> int:
    """Remaining sell capacity in base-asset units."""
    return allowance_remaining(sell_allowance, consumed, reserved)


def _demo() -> int:
    average = average_basis(20, 2200)
    removed = removed_basis(average, 5)
    result = realized_result(650, removed)
    print(f"average_basis: {average}")
    print(f"removed_basis: {removed}")
    print(f"realized_result: {result}")
    print(f"allowance_remaining: {allowance_remaining(500, 300, 100)}")
    print(f"gas_reserved: {gas_reserved(4000000000000000, 4000000000000000)}")
    return 0


def main(argv: Iterable[str]) -> int:
    return _demo()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
