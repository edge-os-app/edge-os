"""The study's model cost, summed from each saved attempt's spend as the guarded runner recorded it.

Only a SETTLED attempt has a known cost. Every other state, and an attempt with no spend record (a crash), is unknown:
it is counted, never added as zero, so the total is then only a lower bound. Amounts stay exact decimal strings.
"""

from __future__ import annotations

from typing import Any

from edge_os_api.research.interpretation_workflow import study_model_cost


def attempt(state: str | None, charge: str | None) -> dict[str, Any]:
    return {"spend": {"state": state, "charge_usd": charge}}


def test_settled_charges_add_up_exactly_and_the_total_is_complete() -> None:
    cost = study_model_cost([attempt("SETTLED", "0.0074285"), attempt("SETTLED", "0.0074285")])
    assert cost == {"settled_usd": "0.014857", "settled_calls": 2, "unknown_calls": 0}


def test_amounts_that_floats_would_round_stay_exact() -> None:
    cost = study_model_cost([attempt("SETTLED", "0.1"), attempt("SETTLED", "0.2"), attempt("SETTLED", "0.000000001")])
    assert cost["settled_usd"] == "0.300000001"  # 0.1 + 0.2 as floats is 0.30000000000000004


def test_unknown_states_and_missing_records_are_counted_and_never_added() -> None:
    cost = study_model_cost([
        attempt("SETTLED", "0.0074285"),
        attempt("UNKNOWN", "0.054848"),  # the held reservation is liability, not a cost
        attempt("RELEASED", "0"),
        attempt("SETTLEMENT_NOT_RECORDED", None),
        attempt(None, None),  # no spend record: the process stopped before the runner saved one
        attempt("SETTLED", None),  # a settled state without its charge is not a known cost either
    ])
    assert cost == {"settled_usd": "0.0074285", "settled_calls": 1, "unknown_calls": 5}


def test_no_settled_call_gives_no_amount_rather_than_zero() -> None:
    assert study_model_cost([attempt("UNKNOWN", "0.054848"), attempt(None, None)]) == {
        "settled_usd": None, "settled_calls": 0, "unknown_calls": 2}
    assert study_model_cost([]) == {"settled_usd": None, "settled_calls": 0, "unknown_calls": 0}
