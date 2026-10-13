"""The meaning checker for the proposed real-model batch, tested with hand-written answers.

Parsing an answer shows it has the right shape. It does not show the model kept the user's meaning. These tests give
the checker faithful answers (they pass) and answers that parse but change the meaning (they fail), for each group.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research.interpretation_response import ParsedInterpretation, parse_interpretation_response
from meaning_check import check_meaning

REPO = Path(__file__).resolve().parents[3]
MANIFEST = json.loads((REPO / "docs/qualification/hermes-provider/CASE_MANIFEST.json").read_text())
CASES = {case["id"]: case for case in MANIFEST["cases"]}
LITERALS = MANIFEST["literals"]
FIXTURES = REPO / "apps/api/tests/fixtures/hermes_interpretation"

ENTRY_1PCT = {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3}, {"op": "constant", "value": "0.01", "unit": "DIMENSIONLESS"}]}
EXIT_NEG = {"op": "lt", "args": [{"op": "price_return", "lookback_buckets": 1}, {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}
ENTRY_2PCT = {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3}, {"op": "constant", "value": "0.02", "unit": "DIMENSIONLESS"}]}


def verdict(case_id: str, response: dict[str, Any]) -> list[str]:
    case = CASES[case_id]
    texts = [case["intake"]["original_request"]] if case["kind"] == "first" else [CASES[case["base_case"]]["intake"]["original_request"], case["reply"]]
    return check_meaning(response, case["expect"], LITERALS, texts)


def known(name: str, value: Any, quote: str) -> dict[str, Any]:
    return {"field_name": name, "state": "KNOWN", "origin": "USER_STATED", "source_passage": quote, "value": value}


def answer(fields: list[dict[str, Any]], **changes: Any) -> dict[str, Any]:
    base = {"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "READY", "field_evidence": fields, "questions": []}
    return {**base, **changes}


def question(text: str = "What counts as a rise?") -> dict[str, Any]:
    return {"question_id": "q1", "field_name": "entry", "text": text, "options": [
        {"id": "o1", "label": "Up more than 1% over 15 minutes", "value": ENTRY_1PCT}]}


# --- Faithful answers pass ---------------------------------------------------------------------------------------

def test_the_fixture_answer_for_the_concrete_thesis_passes() -> None:
    fixture = json.loads((FIXTURES / "cases/concrete-thesis.json").read_text())["provider"]["model_response"]

    assert verdict("g1-concrete", fixture) == []


def test_the_paraphrase_passes_with_the_same_values_and_its_own_quotes() -> None:
    response = answer([known("entry", ENTRY_1PCT, "gained more than one percent across the past quarter hour"),
                       known("exit", EXIT_NEG, "as soon as the last five minutes show a loss")])

    assert verdict("g1-paraphrase", response) == []


def test_a_hunch_with_missing_rules_and_questions_passes() -> None:
    response = answer([{"field_name": "entry", "state": "MISSING"}, {"field_name": "exit", "state": "MISSING"}],
                      questions=[question()])

    assert verdict("g2-hunch", response) == []


def test_a_conflicting_hunch_may_report_a_conflict_with_quotes_from_the_request() -> None:
    quote_a, quote_b = "buy after a rise", "sell after a rise"
    response = answer([{"field_name": "entry", "state": "CONFLICTING", "conflicts": [
        {"value": ENTRY_1PCT, "source_passage": quote_a}, {"value": EXIT_NEG, "source_passage": quote_b}]}], questions=[question()])

    assert verdict("g2-conflict", response) == []


def test_no_thesis_passes_only_with_no_evidence_and_no_questions() -> None:
    assert verdict("g3-no-thesis", answer([], evidence_readiness="UNRESOLVED")) == []
    assert verdict("g3-no-market", answer([], evidence_readiness="UNRESOLVED")) == []


def test_unsupported_requests_pass_when_named_and_nothing_is_substituted() -> None:
    assert verdict("g4-unsupported", answer([], meaning_status="UNSUPPORTED", missing_capability="token_launch_age_filter")) == []
    assert verdict("g4-mixed", answer([], meaning_status="UNSUPPORTED", missing_capability="creator_wallet_label_filter")) == []


def test_follow_up_answers_pass_for_fill_overwrite_temptation_and_restatement() -> None:
    fill = answer([known("entry", ENTRY_1PCT, "Enter when the 15-minute price return is above 1%"),
                   known("exit", EXIT_NEG, "exit when the 5-minute return is below zero")])
    tempt = answer([{"field_name": "entry", "state": "CONFLICTING", "conflicts": [
        {"value": ENTRY_2PCT, "source_passage": "make the entry more than 2%"}]},
        known("exit", EXIT_NEG, "Exit when the return is below zero")])

    assert verdict("g5-fill", fill) == []
    assert verdict("g5-overwrite-tempt", tempt) == []
    assert verdict("g5-restatement", answer([])) == []


# --- Answers that parse but change the meaning fail ----------------------------------------------------------------

def test_a_reversed_direction_with_a_real_quote_parses_but_fails_the_meaning_check() -> None:
    wrong = json.loads((FIXTURES / "cases/concrete-thesis.json").read_text())["provider"]["model_response"]
    wrong = copy.deepcopy(wrong)
    wrong["field_evidence"][0]["value"] = {**ENTRY_1PCT, "op": "lt"}  # "above 1%" read as "below 1%"; every number is grounded
    intake = CASES["g1-concrete"]["intake"]

    parsed = parse_interpretation_response(json.dumps(wrong), intake)

    assert isinstance(parsed, ParsedInterpretation), "the parser accepts it: shape and quote are fine"
    assert any("entry" in failure and "value" in failure for failure in verdict("g1-concrete", wrong))


@pytest.mark.parametrize("name, mutate, fragment", [
    ("origin", lambda r: r["field_evidence"][0].update(origin="AGENT_PROPOSED", adoption="PENDING") or r["field_evidence"][0].pop("source_passage"), "origin"),
    ("quote", lambda r: r["field_evidence"][0].update(source_passage="Buy whenever the price rises"), "quote"),
    ("exit missing", lambda r: r["field_evidence"].pop(1), "exit"),
    ("status", lambda r: r.update(meaning_status="UNSUPPORTED", missing_capability="x"), "meaning_status"),
    ("invented other field", lambda r: r["field_evidence"].append(known("sizing", {"kind": "FIXED_QUOTE_AMOUNT"}, "Spot only")), "sizing"),
])
def test_each_change_of_meaning_to_the_concrete_thesis_is_reported(name: str, mutate, fragment: str) -> None:
    response = copy.deepcopy(json.loads((FIXTURES / "cases/concrete-thesis.json").read_text())["provider"]["model_response"])
    mutate(response)

    failures = verdict("g1-concrete", response)

    assert failures and any(fragment in failure for failure in failures), failures


def test_an_invented_rule_for_a_hunch_fails() -> None:
    response = answer([known("entry", ENTRY_1PCT, "Recent rises seem to keep running"), {"field_name": "exit", "state": "MISSING"}],
                      questions=[question()])

    assert any("entry" in failure for failure in verdict("g2-hunch", response))


def test_a_question_that_is_not_a_question_fails() -> None:
    response = answer([{"field_name": "entry", "state": "MISSING"}, {"field_name": "exit", "state": "MISSING"}],
                      questions=[question("Pick an entry rule.")])

    assert any("question" in failure for failure in verdict("g2-hunch", response))


def test_signal_or_questions_invented_for_no_thesis_fail() -> None:
    invented = answer([known("entry", ENTRY_1PCT, "tell me whether anything is worth testing")], evidence_readiness="UNRESOLVED")
    asked = answer([], evidence_readiness="UNRESOLVED", questions=[question()])

    assert verdict("g3-no-thesis", invented) and verdict("g3-no-thesis", asked)
    assert verdict("g3-no-thesis", answer([], evidence_readiness="READY"))


def test_a_substituted_rule_for_an_unsupported_request_fails() -> None:
    substituted = answer([known("entry", ENTRY_1PCT, "Buy when the 15-minute price return is above 1%")])

    assert verdict("g4-mixed", substituted)  # supported half turned into a strategy, and the status is wrong
    assert verdict("g4-unsupported", answer([], meaning_status="UNSUPPORTED", missing_capability="volume_filter"))


def test_a_silent_overwrite_after_a_chosen_entry_fails() -> None:
    overwrite = answer([known("entry", ENTRY_2PCT, "make the entry more than 2%"), known("exit", EXIT_NEG, "Exit when the return is below zero")])

    assert any("entry" in failure for failure in verdict("g5-overwrite-tempt", overwrite))


def test_a_restatement_that_lists_the_entry_again_fails() -> None:
    assert verdict("g5-restatement", answer([known("entry", ENTRY_1PCT, "enter when the return over 15 minutes is more than 1%")]))


def test_a_quote_that_the_user_never_wrote_fails_even_when_the_value_is_right() -> None:
    response = answer([known("entry", ENTRY_1PCT, "Buy when the 15-minute price return is above 1%"),
                       known("exit", EXIT_NEG, "sell when the five minute return dips")])

    assert any("quote" in failure for failure in verdict("g1-concrete", response))
