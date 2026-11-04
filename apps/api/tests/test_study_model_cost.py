"""The study's model cost, summed from each saved attempt's spend as the guarded runner recorded it.

Only a SETTLED attempt has a known cost. Every other state, and an attempt with no spend record (a crash), is unknown:
it is counted, never added as zero, so the total is then only a lower bound. Amounts stay exact decimal strings.
"""

from __future__ import annotations

import uuid
from typing import Any

from edge_os_api.research.interpretation_workflow import model_budget, study_model_cost


def attempt(state: str | None, charge: str | None) -> dict[str, Any]:
    return {"spend": {"state": state, "charge_usd": charge}}


def credit(settled: str | None, held: str | None = None) -> dict[str, Any]:
    """The CREDIT fields (ORBIO_CREDIT_DESIGN 2a): 1 CREDIT is exactly USD 1, so the amounts are the same strings."""
    return {"unit": "CREDIT", "settled_credit": settled, "held_credit": held}


def test_settled_charges_add_up_exactly_and_the_total_is_complete() -> None:
    cost = study_model_cost([attempt("SETTLED", "0.0074285"), attempt("SETTLED", "0.0074285")])
    assert cost == {"settled_usd": "0.014857", "settled_calls": 2, "unknown_calls": 0, **credit("0.014857")}


def test_amounts_that_floats_would_round_stay_exact() -> None:
    cost = study_model_cost([attempt("SETTLED", "0.1"), attempt("SETTLED", "0.2"), attempt("SETTLED", "0.000000001")])
    assert cost["settled_usd"] == "0.300000001"  # 0.1 + 0.2 as floats is 0.30000000000000004


def test_charges_the_runner_stored_in_exponent_form_add_up_to_a_plain_decimal() -> None:
    # The runner stores `str(Decimal.normalize())`, which writes very small and round amounts with an exponent.
    cost = study_model_cost([attempt("SETTLED", "5E-7"), attempt("SETTLED", "1E+1")])
    assert cost == {"settled_usd": "10.0000005", "settled_calls": 2, "unknown_calls": 0, **credit("10.0000005")}


def test_a_settled_charge_that_is_not_a_finite_amount_is_unknown() -> None:
    cost = study_model_cost([attempt("SETTLED", "0.5"), attempt("SETTLED", "NaN"), attempt("SETTLED", "not-usd"),
                             attempt("SETTLED", "-1")])
    assert cost == {"settled_usd": "0.5", "settled_calls": 1, "unknown_calls": 3, **credit("0.5")}


def test_unknown_states_and_missing_records_are_counted_and_never_added() -> None:
    cost = study_model_cost([
        attempt("SETTLED", "0.0074285"),
        attempt("UNKNOWN", "0.054848"),  # the held reservation is liability, not a cost
        attempt("RELEASED", "0"),
        attempt("SETTLEMENT_NOT_RECORDED", None),
        attempt(None, None),  # no spend record: the process stopped before the runner saved one
        attempt("SETTLED", None),  # a settled state without its charge is not a known cost either
    ])
    assert cost == {"settled_usd": "0.0074285", "settled_calls": 1, "unknown_calls": 5, **credit("0.0074285", "0.054848")}


def test_no_settled_call_gives_no_amount_rather_than_zero() -> None:
    assert study_model_cost([attempt("UNKNOWN", "0.054848"), attempt(None, None)]) == {
        "settled_usd": None, "settled_calls": 0, "unknown_calls": 2, **credit(None, "0.054848")}
    assert study_model_cost([]) == {"settled_usd": None, "settled_calls": 0, "unknown_calls": 0, **credit(None)}


def test_a_settled_zero_is_a_known_cost_and_stays_apart_from_unknown() -> None:
    cost = study_model_cost([attempt("SETTLED", "0"), attempt("UNKNOWN", "0.054848")])
    assert cost == {"settled_usd": "0", "settled_calls": 1, "unknown_calls": 1, **credit("0", "0.054848")}


def test_a_charge_outside_the_stored_decimal_form_is_unknown() -> None:
    # Only the plain or exponent form the runner writes (and the web reads) is an amount; the web shows the rest as
    # Unknown, so the total counts them as unknown too instead of adding them.
    charges = ["-0", "+5", ".5", "5.", " 0.5 ", "1_000", "1E-100", "1E+999", "1E+999999999", "٥"]
    cost = study_model_cost([attempt("SETTLED", "0.5")] + [attempt("SETTLED", c) for c in charges])
    assert cost == {"settled_usd": "0.5", "settled_calls": 1, "unknown_calls": len(charges), **credit("0.5")}


def test_the_total_keeps_every_digit_beyond_the_default_decimal_precision() -> None:
    cost = study_model_cost([attempt("SETTLED", "12345678901234567890123456789012345.1"), attempt("SETTLED", "1E+30"),
                             attempt("SETTLED", "1E-10")])
    assert cost == {"settled_usd": "12346678901234567890123456789012345.1000000001", "settled_calls": 3,
                    "unknown_calls": 0, **credit("12346678901234567890123456789012345.1000000001")}


# --- CREDIT (ORBIO_CREDIT_DESIGN 2a) -------------------------------------------------------------------------------------

def test_unknown_and_reserved_calls_are_held_never_settled_and_never_zero() -> None:
    cost = study_model_cost([attempt("UNKNOWN", "0.17216"), attempt("RESERVED", "0.15"), attempt(None, None)])
    assert cost["settled_credit"] is None and cost["settled_usd"] is None  # nothing settled: no amount, not "0"
    assert cost["held_credit"] == "0.32216" and cost["unknown_calls"] == 3 and cost["unit"] == "CREDIT"


def test_settled_credit_is_the_same_exact_amount_as_settled_usd() -> None:
    cost = study_model_cost([attempt("SETTLED", "0.0074285"), attempt("SETTLED", "5E-7"), attempt("UNKNOWN", "0.054848")])
    assert cost["settled_credit"] == cost["settled_usd"] == "0.007429"
    assert cost["held_credit"] == "0.054848" and cost["unknown_calls"] == 1


def test_an_attempt_without_a_recorded_charge_is_unknown_and_not_in_the_held_lower_bound() -> None:
    # SETTLEMENT_NOT_RECORDED saved no charge although its ledger row still holds the full reservation: held_credit is
    # a lower bound, and the true held amount comes from the ledger (`spend_view`).
    cost = study_model_cost([attempt("SETTLEMENT_NOT_RECORDED", None), attempt("UNKNOWN", "0.054848"),
                             attempt("UNKNOWN", "not-an-amount"), attempt("RELEASED", "0")])
    assert (cost["held_credit"], cost["unknown_calls"], cost["settled_credit"]) == ("0.054848", 4, None)
    assert study_model_cost([attempt("SETTLEMENT_NOT_RECORDED", None)])["held_credit"] is None


# --- The owner's budget from the ledger: `spend_view` (PostgreSQL) and its CREDIT form -----------------------------------
# TEST prices 2.00 / 7.50 USD per million: a reservation is 54,848,000 nano-USD and 1,423 + 611 tokens settle at 7,428,500.

from test_provider_spend_ledger import BOUNDS, attempts, clean_spend, factory, limits  # noqa: E402,F401 - fixtures


def owner_of(client, headers) -> uuid.UUID:
    return uuid.UUID(client.get("/v1/me", headers=headers).json()["user_id"])


def test_a_ledger_that_was_never_used_has_no_budget_rather_than_a_zero_one(clean_spend, client, owner_a) -> None:
    from sqlalchemy import text

    from edge_os_api.research.provider_spend_ledger import spend_view
    with clean_spend() as session:
        assert spend_view(session, owner_of(client, owner_a)) is None
        assert session.execute(text("SELECT count(*) FROM usage_local.provider_spend_settings")).scalar_one() == 0
    assert model_budget(None) is None


def test_held_liability_is_used_budget_and_the_smaller_headroom_is_what_is_available(
        clean_spend, attempts, client, owner_a, owner_b) -> None:
    from edge_os_api.research.provider_spend_ledger import PostgresSpendLedger, spend_view
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.20", owner_cap="0.12"))
    settled, lost, released, other = (attempts.new(owner_a), attempts.new(owner_a), attempts.new(owner_a),
                                      attempts.new(owner_b))
    spend.reserve(settled, scope="s1", **BOUNDS)
    spend.settle(settled, input_tokens=1_423, output_tokens=611)
    spend.reserve(lost, scope="s2", **BOUNDS)
    spend.mark_unknown(lost, reason="the outcome is not known")
    spend.reserve(released, scope="s3", **BOUNDS)
    spend.release_unsent(released, reason="no request was admitted")
    spend.reserve(other, scope="s4", **BOUNDS)  # owner B's call, still RESERVED

    with clean_spend() as session:
        mine, theirs = spend_view(session, owner_of(client, owner_a)), spend_view(session, owner_of(client, owner_b))
        nobody = spend_view(session, uuid.uuid4())

    # owner A: 120,000,000 - (7,428,500 + 54,848,000) = 57,723,500; everyone: 200,000,000 - 117,124,500 = 82,875,500
    assert mine == {"owner_cap": 120_000_000, "global_cap": 200_000_000, "settled": 7_428_500, "held": 54_848_000,
                    "held_calls": 1, "available": 57_723_500}
    assert theirs == {"owner_cap": 120_000_000, "global_cap": 200_000_000, "settled": 0, "held": 54_848_000,
                      "held_calls": 1, "available": 65_152_000}
    assert nobody["available"] == 82_875_500 and (nobody["settled"], nobody["held"], nobody["held_calls"]) == (0, 0, 0)
    assert model_budget(mine) == {"unit": "CREDIT", "owner_cap_credit": "0.12", "global_cap_credit": "0.2",
                                  "settled_credit": "0.0074285", "held_credit": "0.054848", "held_calls": 1,
                                  "available_credit": "0.0577235"}


def test_a_budget_past_its_cap_shows_nothing_available_and_exact_amounts() -> None:
    view = {"owner_cap": 2_000_000_000, "global_cap": 2_000_000_000, "settled": 2_000_000_001, "held": 0,
            "held_calls": 0, "available": -1}  # an OVERRUN charge passed the cap
    assert model_budget(view) == {"unit": "CREDIT", "owner_cap_credit": "2", "global_cap_credit": "2",
                                  "settled_credit": "2.000000001", "held_credit": "0", "held_calls": 0,
                                  "available_credit": "0"}
