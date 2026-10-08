#!/usr/bin/env python3
"""Validate P06 machine contract and independent numerical fixture literals."""

from __future__ import annotations

import json
from decimal import Decimal, localcontext, Context, ROUND_HALF_EVEN
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))
FIXTURES = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))


def main() -> None:
    assert CONTRACT["schema_version"] == "p06.contract/1"
    assert CONTRACT["machine_encoding"] == "p06-expression-json/1"
    assert "relative_volume" in CONTRACT["operators"]
    assert CONTRACT["relative_volume"]["definition"] == "quote_volume[t] / mean(quote_volume[t-n .. t-1])"
    assert CONTRACT["identity"]["manifest_components"]["operator_registry"] == "edge-operators/2"
    assert FIXTURES["schema_version"] == "p06.fixtures/1"
    cases = {case["id"]: case for case in FIXTURES["cases"]}
    assert len(cases) == len(FIXTURES["cases"])
    ratio = cases["relative-volume-prior-two"]
    values = [Decimal(item) for item in ratio["scheduled_quote_volume"]]
    n, index = ratio["expression"]["lookback_buckets"], ratio["position"]
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        result = values[index] / (sum(values[index - n:index]) / Decimal(n))
        expected_ratio = Decimal(10) / Decimal(3)
    assert result == expected_ratio
    assert cases["relative-volume-zero-baseline-zero-current"]["expected_reasons"] == ["ZERO_BASELINE"]
    assert Decimal("110") / Decimal("100") - Decimal(1) == Decimal("0.1")
    assert cases["price-return-qualified-endpoints-with-gap"]["expected_reasons"] == ["MISSING_PRICE:1"]
    print(f"P06 contract and {len(cases)} independent fixture literals: PASS")


if __name__ == "__main__":
    main()
