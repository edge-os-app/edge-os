"""Behavior of the strict generated-response parser at its public seam: response text + saved intake in, result out.

Expected values are hand-written literals. They do not come from the code under test.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest

from edge_os_api.research.interpretation_response import ParsedInterpretation, Rejection, parse_interpretation_response

THESIS = "Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. Spot only."
THESIS_INTAKE = {"original_request": THESIS, "restrictions": ["no leverage"], "requested_job": "CREATE_STRATEGY",
                 "input_class": "CONCRETE_THESIS"}
ENTRY_PASSAGE = "Buy when the 15-minute price return is above 1%"  # characters 0-47
EXIT_PASSAGE = "exit when the 5-minute return turns negative"  # characters 53-97
ENTRY_VALUE = {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                    {"op": "constant", "value": "0.01", "unit": "DIMENSIONLESS"}]}
EXIT_VALUE = {"op": "lt", "args": [{"op": "price_return", "lookback_buckets": 1},
                                   {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}


def thesis_response() -> dict[str, Any]:
    return {
        "meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "READY",
        "field_evidence": [
            {"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": ENTRY_PASSAGE,
             "value": copy.deepcopy(ENTRY_VALUE)},
            {"field_name": "exit", "state": "KNOWN", "origin": "USER_STATED", "source_passage": EXIT_PASSAGE,
             "value": copy.deepcopy(EXIT_VALUE)},
        ],
        "questions": [],
    }


def parse(response: dict[str, Any] | str, intake: dict[str, Any] = THESIS_INTAKE) -> ParsedInterpretation | Rejection:
    text = response if isinstance(response, str) else json.dumps(response)
    return parse_interpretation_response(text, intake)


def assert_rejected(result: ParsedInterpretation | Rejection, reason_code: str, path: str | None = None) -> None:
    assert isinstance(result, Rejection), f"expected a whole-response rejection, got {result!r}"
    assert result.reason_code == reason_code
    if path is not None:
        assert result.path == path


def test_accepts_one_object_and_ties_user_stated_fields_to_exact_request_characters() -> None:
    text = json.dumps(thesis_response())
    result = parse_interpretation_response(text, THESIS_INTAKE)

    assert isinstance(result, ParsedInterpretation)
    assert result.meaning_status == "SUPPORTED"
    assert result.missing_capability is None
    assert result.evidence_readiness == "READY"
    assert result.response_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    by_name = {item["field_name"]: item for item in result.field_evidence}
    assert by_name["entry"] == {
        "field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
        "source_ref": "intake:original_request#c0-47", "interpretation_revision": "",
        "evidence_status": "HYPOTHESIS", "value": ENTRY_VALUE}
    assert by_name["exit"]["source_ref"] == "intake:original_request#c53-97"
    # The application, not the model, owns the restrictions item.
    assert by_name["restrictions"] == {
        "field_name": "restrictions", "state": "KNOWN", "origin": "USER_STATED",
        "source_ref": "intake:restrictions", "interpretation_revision": "", "evidence_status": "VERIFIED_FACT",
        "value": ["no leverage"]}


@pytest.mark.parametrize("text, reason_code", [
    pytest.param(json.dumps(thesis_response()) + json.dumps(thesis_response()), "multiple_objects",
                 id="two-objects-back-to-back"),
    pytest.param(json.dumps(thesis_response()) + "\n" + json.dumps(thesis_response()), "multiple_objects",
                 id="two-objects-on-separate-lines"),
    pytest.param(json.dumps(thesis_response()) + "\nHope this helps.", "trailing_content", id="prose-after-object"),
    pytest.param("Here is the result:\n" + json.dumps(thesis_response()), "invalid_json", id="prose-before-object"),
    pytest.param("```json\n" + json.dumps(thesis_response()) + "\n```", "invalid_json", id="code-fenced-object"),
    pytest.param(json.dumps(thesis_response())[:-40], "invalid_json", id="cut-off-mid-object"),
    pytest.param("", "invalid_json", id="empty-text"),
    pytest.param(json.dumps([thesis_response()]), "not_an_object", id="array-instead-of-object"),
])
def test_rejects_the_whole_response_when_it_is_not_exactly_one_json_object(text: str, reason_code: str) -> None:
    assert_rejected(parse(text), reason_code)


def test_rejects_duplicate_keys_instead_of_keeping_the_last_value() -> None:
    text = json.dumps(thesis_response())[:-1] + ', "meaning_status": "UNSUPPORTED"}'
    assert_rejected(parse(text), "duplicate_key")


def test_rejects_json_floating_point_numbers() -> None:
    response = thesis_response()
    response["field_evidence"][0]["value"]["args"][1]["value"] = 0.01
    assert_rejected(parse(response), "invalid_number")


def test_rejects_an_unaccepted_top_level_field() -> None:
    response = thesis_response()
    response["confidence"] = "high"
    assert_rejected(parse(response), "unaccepted_field", "/confidence")


def test_rejects_an_unaccepted_field_inside_an_evidence_item() -> None:
    response = thesis_response()
    response["field_evidence"][1]["evidence_status"] = "VERIFIED_FACT"
    assert_rejected(parse(response), "unaccepted_field", "/field_evidence/1/evidence_status")


def test_rejects_a_missing_required_top_level_field() -> None:
    response = thesis_response()
    del response["evidence_readiness"]
    assert_rejected(parse(response), "missing_field", "/evidence_readiness")


# --- Origin and grounding discipline: the model may not claim meaning the user did not state ---

SIZING_PROPOSAL = {"kind": "FIXED_QUOTE_AMOUNT", "amount": "100",
                   "unit": "QUOTE:0x2222222222222222222222222222222222222222"}
SPOT_SCOPE = ["SPOT_BUY", "SPOT_SELL_ALL_ATTRIBUTABLE"]


def with_item(item: dict[str, Any]) -> dict[str, Any]:
    response = thesis_response()
    response["field_evidence"].append(item)
    return response


def test_accepted_output_is_a_valid_p02_interpretation_record() -> None:
    from edge_os_api.records import contract_adapter as record_contract

    result = parse(thesis_response())
    assert isinstance(result, ParsedInterpretation)
    items = [{**item, "interpretation_revision": "11111111-1111-4111-8111-111111111111"} for item in result.field_evidence]
    content = {"intake_record_id": "22222222-2222-4222-8222-222222222222",
               "interpretation_revision_id": "11111111-1111-4111-8111-111111111111",
               "input_class": "CONCRETE_THESIS", "requested_job": "CREATE_STRATEGY", "field_evidence": items,
               "clarification_history": [], "preserved_restrictions": ["no leverage"],
               "meaning_status": result.meaning_status, "syntax_status": "VALID",
               "evidence_readiness": result.evidence_readiness}
    record_contract.validate_record("PromptInterpretation", content)  # raises Invalid when the record is not valid


def test_keeps_an_agent_proposal_pending_and_labels_it_as_the_agent_s() -> None:
    proposal = {"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
                "value": SIZING_PROPOSAL}
    result = parse(with_item(proposal))

    assert isinstance(result, ParsedInterpretation)
    sizing = next(item for item in result.field_evidence if item["field_name"] == "sizing")
    assert sizing == {"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED",
                      "source_ref": "agent:proposal", "interpretation_revision": "", "evidence_status": "HYPOTHESIS",
                      "adoption": "PENDING", "value": SIZING_PROPOSAL}


@pytest.mark.parametrize("item, reason_code, path", [
    pytest.param({"field_name": "action_scope", "state": "KNOWN", "origin": "USER_STATED",
                  "source_passage": "Only spot buys and sells", "value": SPOT_SCOPE},
                 "source_passage_not_in_request", "/field_evidence/2/source_passage", id="paraphrased-passage"),
    pytest.param({"field_name": "action_scope", "state": "KNOWN", "origin": "USER_STATED", "source_passage": "",
                  "value": SPOT_SCOPE}, "source_passage_not_in_request", "/field_evidence/2/source_passage",
                 id="empty-passage-is-not-grounding"),
    pytest.param({"field_name": "action_scope", "state": "KNOWN", "origin": "USER_STATED", "value": SPOT_SCOPE},
                 "missing_field", "/field_evidence/2/source_passage", id="user-stated-without-passage"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "USER_CONFIRMED",
                  "source_passage": "Spot only", "value": SIZING_PROPOSAL}, "origin_not_allowed",
                 "/field_evidence/2/origin", id="model-claims-user-confirmed"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "APPLICATION_CONFIGURED",
                  "value": SIZING_PROPOSAL}, "origin_not_allowed", "/field_evidence/2/origin",
                 id="model-claims-application-configured"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "ADOPTED",
                  "value": SIZING_PROPOSAL}, "proposal_must_stay_pending", "/field_evidence/2/adoption",
                 id="model-adopts-its-own-proposal"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED", "value": SIZING_PROPOSAL},
                 "proposal_must_stay_pending", "/field_evidence/2/adoption", id="proposal-without-adoption-state"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "USER_STATED", "adoption": "PENDING",
                  "source_passage": "Spot only", "value": SIZING_PROPOSAL}, "adoption_not_allowed",
                 "/field_evidence/2/adoption", id="adoption-on-user-stated"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
                  "source_passage": "Spot only", "value": SIZING_PROPOSAL}, "source_passage_not_allowed",
                 "/field_evidence/2/source_passage", id="passage-on-an-agent-proposal"),
    pytest.param({"field_name": "restrictions", "state": "KNOWN", "origin": "USER_STATED",
                  "source_passage": "Spot only", "value": ["spot only"]}, "reserved_field",
                 "/field_evidence/2/field_name", id="model-writes-restrictions"),
    pytest.param({"field_name": "momentum", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
                  "value": "high"}, "unknown_field_name", "/field_evidence/2/field_name", id="field-outside-the-job"),
    pytest.param({"field_name": "entry", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
                  "value": ENTRY_VALUE}, "duplicate_field", "/field_evidence/2/field_name", id="same-field-twice"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING"},
                 "missing_field", "/field_evidence/2/value", id="known-without-value"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
                  "value": None}, "missing_field", "/field_evidence/2/value", id="known-with-null-value"),
    pytest.param({"field_name": "sizing", "state": "MAYBE", "origin": "AGENT_PROPOSED", "value": SIZING_PROPOSAL},
                 "invalid_value", "/field_evidence/2/state", id="unknown-state"),
    pytest.param({"field_name": "sizing", "state": "KNOWN", "origin": "GUESS", "value": SIZING_PROPOSAL},
                 "invalid_value", "/field_evidence/2/origin", id="unknown-origin"),
])
def test_rejects_evidence_the_model_cannot_ground_or_may_not_claim(item: dict[str, Any], reason_code: str,
                                                                    path: str) -> None:
    assert_rejected(parse(with_item(item)), reason_code, path)


# --- Missing, conflicting, unsupported, questions, and jobs where the application owns the market ---

HUNCH = "Recent rises seem to keep running. Is that worth testing?"
HUNCH_INTAKE = {"original_request": HUNCH, "restrictions": [], "requested_job": "CREATE_STRATEGY",
                "input_class": "LOOSE_INTUITION"}
BASE_ASSET = "0x" + "11" * 20
QUOTE_ASSET = "0x" + "22" * 20
DECLARED_MARKET = {"network": "MONAD", "base_asset": BASE_ASSET, "quote_asset": QUOTE_ASSET}
NO_THESIS = "I have no view. Look at this market over the last two days and tell me whether anything is worth testing."
NO_THESIS_INTAKE = {"original_request": NO_THESIS, "restrictions": [], "requested_job": "INVESTIGATE_EFFECT",
                    "input_class": "BOUNDED_NO_THESIS", "declared_market": DECLARED_MARKET}
ENTRY_QUESTION = {
    "question_id": "choose-entry", "field_name": "entry", "text": "What should count as a rise for the entry rule?",
    "options": [
        {"id": "g3-1pct", "label": "Price up more than 1% over the last 15 minutes", "value": ENTRY_VALUE},
        {"id": "g3-2pct", "label": "Price up more than 2% over the last 15 minutes",
         "value": {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                        {"op": "constant", "value": "0.02", "unit": "DIMENSIONLESS"}]}}]}


def hunch_response() -> dict[str, Any]:
    return {"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "READY",
            "field_evidence": [{"field_name": "entry", "state": "MISSING"}], "questions": [copy.deepcopy(ENTRY_QUESTION)]}


def test_reports_a_rough_hunch_as_a_missing_rule_and_offers_the_models_question() -> None:
    result = parse(hunch_response(), HUNCH_INTAKE)

    assert isinstance(result, ParsedInterpretation)
    entry = next(item for item in result.field_evidence if item["field_name"] == "entry")
    assert entry == {"field_name": "entry", "state": "MISSING", "origin": "USER_STATED",
                     "source_ref": "intake:original_request", "interpretation_revision": "",
                     "evidence_status": "UNKNOWN"}
    assert [(q.question_id, q.field_name, q.text, [o.id for o in q.options]) for q in result.questions] == [
        ("choose-entry", "entry", "What should count as a rise for the entry rule?", ["g3-1pct", "g3-2pct"])]
    assert result.questions[0].options[0].value == ENTRY_VALUE
    assert result.questions[0].options[1].label == "Price up more than 2% over the last 15 minutes"


@pytest.mark.parametrize("extra", ["value", "origin", "source_passage", "adoption", "conflicts"])
def test_rejects_content_on_a_missing_field(extra: str) -> None:
    response = hunch_response()
    response["field_evidence"][0][extra] = ENTRY_VALUE if extra == "value" else "USER_STATED"
    assert_rejected(parse(response, HUNCH_INTAKE), "not_allowed_for_state", f"/field_evidence/0/{extra}")


def conflicting_response() -> dict[str, Any]:
    response = thesis_response()
    response["field_evidence"] = [{"field_name": "entry", "state": "CONFLICTING", "conflicts": [
        {"value": ENTRY_VALUE, "source_passage": ENTRY_PASSAGE},
        {"value": EXIT_VALUE, "source_passage": EXIT_PASSAGE}]}]
    return response


def test_keeps_both_conflicting_statements_with_their_own_locations() -> None:
    result = parse(conflicting_response())

    assert isinstance(result, ParsedInterpretation)
    entry = next(item for item in result.field_evidence if item["field_name"] == "entry")
    assert entry == {"field_name": "entry", "state": "CONFLICTING", "origin": "USER_STATED",
                     "source_ref": "intake:original_request", "interpretation_revision": "",
                     "evidence_status": "UNKNOWN",
                     "conflicts": [{"value": ENTRY_VALUE, "source_ref": "intake:original_request#c0-47"},
                                   {"value": EXIT_VALUE, "source_ref": "intake:original_request#c53-97"}]}


@pytest.mark.parametrize("mutate, reason_code, path", [
    pytest.param(lambda r: r["field_evidence"][0].update(value=ENTRY_VALUE), "not_allowed_for_state",
                 "/field_evidence/0/value", id="value-on-conflict"),
    pytest.param(lambda r: r["field_evidence"][0]["conflicts"].pop(), "conflict_needs_two_alternatives",
                 "/field_evidence/0/conflicts", id="one-alternative"),
    pytest.param(lambda r: r["field_evidence"][0]["conflicts"][1].update(source_passage=ENTRY_PASSAGE),
                 "conflict_alternatives_not_distinct", "/field_evidence/0/conflicts/1/source_passage",
                 id="same-words-twice"),
    pytest.param(lambda r: r["field_evidence"][0]["conflicts"][0].update(source_passage="Sell on any dip"),
                 "source_passage_not_in_request", "/field_evidence/0/conflicts/0/source_passage",
                 id="alternative-not-in-request"),
    pytest.param(lambda r: r["field_evidence"][0]["conflicts"][0].update(note="x"), "unaccepted_field",
                 "/field_evidence/0/conflicts/0/note", id="extra-key-in-alternative"),
    pytest.param(lambda r: r["field_evidence"][0].pop("conflicts"), "missing_field",
                 "/field_evidence/0/conflicts", id="no-alternatives"),
])
def test_rejects_a_conflict_that_is_not_two_distinct_grounded_alternatives(mutate: Any, reason_code: str,
                                                                          path: str) -> None:
    response = conflicting_response()
    mutate(response)
    assert_rejected(parse(response), reason_code, path)


def test_keeps_an_unsupported_meaning_with_its_named_missing_capability_and_no_substitute() -> None:
    intake = {"original_request": "Tokens launched in the last 24 hours seem to keep running after a rise. "
                                  "Is that worth testing?", "restrictions": ["no leverage"],
              "requested_job": "CREATE_STRATEGY", "input_class": "LOOSE_INTUITION"}
    response = {"meaning_status": "UNSUPPORTED", "missing_capability": "token_launch_age_filter",
                "evidence_readiness": "READY", "field_evidence": [], "questions": []}
    result = parse(response, intake)

    assert isinstance(result, ParsedInterpretation)
    assert (result.meaning_status, result.missing_capability) == ("UNSUPPORTED", "token_launch_age_filter")
    assert [item["field_name"] for item in result.field_evidence] == ["restrictions"]


@pytest.mark.parametrize("changes, reason_code, path", [
    pytest.param({"meaning_status": "UNSUPPORTED", "missing_capability": None}, "missing_capability_required",
                 "/missing_capability", id="unsupported-without-a-named-capability"),
    pytest.param({"meaning_status": "UNSUPPORTED", "missing_capability": ""}, "missing_capability_required",
                 "/missing_capability", id="unsupported-with-empty-capability"),
    pytest.param({"missing_capability": "rsi"}, "missing_capability_not_allowed", "/missing_capability",
                 id="supported-but-names-a-missing-capability"),
    pytest.param({"meaning_status": "MAYBE"}, "invalid_value", "/meaning_status", id="unknown-meaning-status"),
    pytest.param({"evidence_readiness": "SOON"}, "invalid_value", "/evidence_readiness", id="unknown-readiness"),
    pytest.param({"questions": {}}, "invalid_value", "/questions", id="questions-not-a-list"),
    pytest.param({"field_evidence": "none"}, "invalid_value", "/field_evidence", id="evidence-not-a-list"),
])
def test_rejects_inconsistent_meaning_status_fields(changes: dict[str, Any], reason_code: str, path: str) -> None:
    assert_rejected(parse({**thesis_response(), **changes}), reason_code, path)


def test_the_application_owns_the_market_when_the_job_is_an_investigation() -> None:
    declared = parse({"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "UNRESOLVED",
                      "field_evidence": [], "questions": []}, NO_THESIS_INTAKE)
    undeclared_intake = {k: v for k, v in NO_THESIS_INTAKE.items() if k != "declared_market"}
    undeclared = parse({"meaning_status": "SUPPORTED", "missing_capability": None,
                        "evidence_readiness": "UNRESOLVED", "field_evidence": [], "questions": []}, undeclared_intake)

    assert isinstance(declared, ParsedInterpretation) and isinstance(undeclared, ParsedInterpretation)
    assert {i["field_name"]: i for i in declared.field_evidence}["market"] == {
        "field_name": "market", "state": "KNOWN", "origin": "USER_STATED", "source_ref": "intake:declared_market",
        "interpretation_revision": "", "evidence_status": "HYPOTHESIS", "value": DECLARED_MARKET}
    # No declared market: the application proposes the labelled synthetic fixture market and waits for adoption (D1).
    assert {i["field_name"]: i for i in undeclared.field_evidence}["market"] == {
        "field_name": "market", "state": "KNOWN", "origin": "APPLICATION_CONFIGURED",
        "source_ref": "application:synthetic-fixture-market", "interpretation_revision": "",
        "evidence_status": "HYPOTHESIS", "adoption": "PENDING", "value": DECLARED_MARKET}


def test_rejects_model_evidence_for_a_job_where_the_application_owns_the_fields() -> None:
    response = {"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "UNRESOLVED",
                "field_evidence": [{"field_name": "market", "state": "KNOWN", "origin": "AGENT_PROPOSED",
                                    "adoption": "PENDING", "value": DECLARED_MARKET}], "questions": []}
    assert_rejected(parse(response, NO_THESIS_INTAKE), "reserved_field", "/field_evidence/0/field_name")


@pytest.mark.parametrize("mutate, reason_code, path", [
    pytest.param(lambda q: q.update(field_name="exit"), "question_for_unreported_field",
                 "/questions/0/field_name", id="field-not-reported"),
    pytest.param(lambda q: q.update(field_name="restrictions"), "question_for_unreported_field",
                 "/questions/0/field_name", id="field-is-application-owned"),
    pytest.param(lambda q: q.update(text="What should count as a rise for the entry rule"), "question_text_invalid",
                 "/questions/0/text", id="question-without-question-mark"),
    pytest.param(lambda q: q.update(text=""), "question_text_invalid", "/questions/0/text", id="empty-question"),
    pytest.param(lambda q: q.update(options=[]), "question_needs_options", "/questions/0/options", id="no-options"),
    pytest.param(lambda q: q["options"][1].update(id="g3-1pct"), "duplicate_option", "/questions/0/options/1/id",
                 id="option-id-repeated"),
    pytest.param(lambda q: q["options"][0].update(value=None), "missing_field", "/questions/0/options/0/value",
                 id="option-without-value"),
    pytest.param(lambda q: q.update(hint="x"), "unaccepted_field", "/questions/0/hint", id="extra-question-key"),
    pytest.param(lambda q: q["options"][0].update(score=1), "unaccepted_field", "/questions/0/options/0/score",
                 id="extra-option-key"),
])
def test_rejects_a_question_that_does_not_ask_about_a_reported_open_field(mutate: Any, reason_code: str,
                                                                          path: str) -> None:
    response = hunch_response()
    mutate(response["questions"][0])
    assert_rejected(parse(response, HUNCH_INTAKE), reason_code, path)


def test_rejects_two_questions_with_the_same_id() -> None:
    response = hunch_response()
    response["questions"].append(copy.deepcopy(response["questions"][0]))
    assert_rejected(parse(response, HUNCH_INTAKE), "duplicate_question", "/questions/1/question_id")


def test_rejects_a_question_about_a_field_the_user_already_stated() -> None:
    response = thesis_response()
    response["questions"] = [copy.deepcopy(ENTRY_QUESTION)]
    assert_rejected(parse(response), "question_for_settled_field", "/questions/0/field_name")


def test_rejects_a_question_that_borrows_the_applications_adoption_question_id() -> None:
    response = hunch_response()
    response["questions"][0]["question_id"] = "adopt-suggested-settings"
    assert_rejected(parse(response, HUNCH_INTAKE), "reserved_question_id", "/questions/0/question_id")


# --- Numeric grounding: a number the user "stated" must appear in the quoted words, in any common spelling ---

def volume_rule_intake(sentence: str) -> dict[str, Any]:
    return {"original_request": sentence, "restrictions": [], "requested_job": "CREATE_STRATEGY",
            "input_class": "CONCRETE_THESIS"}


def entry_with_constant(value: str, sentence: str) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 1},
                                  {"op": "constant", "value": value, "unit": "DIMENSIONLESS"}]}
    response = {"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "READY",
                "field_evidence": [{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                                    "source_passage": sentence, "value": entry}], "questions": []}
    return response, volume_rule_intake(sentence)


@pytest.mark.parametrize("sentence, value", [
    pytest.param("Buy when the 5-minute return is above 1%", "0.01", id="percent-sign"),
    pytest.param("Buy when the 5-minute return is above 1 percent", "0.01", id="percent-word"),
    pytest.param("Buy when the 5-minute return is above one percent", "0.01", id="number-word-percent"),
    pytest.param("Buy when the 5-minute return is above 0.5%", "0.005", id="decimal-percent"),
    pytest.param("Buy when the 5-minute return is above 50 bps", "0.005", id="basis-points"),
    pytest.param("Buy when the 5-minute return is above 0.010", "0.01", id="trailing-zero-decimal"),
    pytest.param("Buy when quote volume is above twice its mean", "2", id="twice"),
    pytest.param("Buy when the 5-minute return is above 1,500", "1500", id="thousands-separator"),
    pytest.param("Buy when the 5-minute return turns negative", "0", id="zero-needs-no-number-in-words"),
])
def test_accepts_a_user_stated_number_that_the_quoted_words_state(sentence: str, value: str) -> None:
    response, intake = entry_with_constant(value, sentence)
    assert isinstance(parse(response, intake), ParsedInterpretation)


@pytest.mark.parametrize("sentence, value", [
    pytest.param("Buy when the 5-minute return is above 1%", "1", id="percent-read-as-whole-number"),
    pytest.param("Buy when the 5-minute return is above 1%", "0.02", id="different-number"),
    pytest.param("Buy when the 5-minute return is above 1%", "0.1", id="decimal-slip"),
    pytest.param("Buy when the price rises", "0.05", id="number-from-nowhere"),
    pytest.param("Buy when the 5-minute return is above 50 bps", "0.05", id="basis-points-misread"),
])
def test_rejects_a_user_stated_number_that_the_quoted_words_do_not_state(sentence: str, value: str) -> None:
    response, intake = entry_with_constant(value, sentence)
    assert_rejected(parse(response, intake), "ungrounded_number", "/field_evidence/0/value")


def test_checks_fixed_sizing_amounts_against_the_users_words_too() -> None:
    sentence = "Use a fixed size of 25 quote units per trade."
    intake = volume_rule_intake(sentence)

    def response_with(amount: str) -> dict[str, Any]:
        return {"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "READY",
                "field_evidence": [{"field_name": "sizing", "state": "KNOWN", "origin": "USER_STATED",
                                    "source_passage": "fixed size of 25 quote units",
                                    "value": {**SIZING_PROPOSAL, "amount": amount}}], "questions": []}

    assert isinstance(parse(response_with("25"), intake), ParsedInterpretation)
    assert_rejected(parse(response_with("100"), intake), "ungrounded_number", "/field_evidence/0/value")


def test_an_agent_proposal_may_carry_numbers_the_user_never_stated() -> None:
    result = parse(with_item({"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED",
                              "adoption": "PENDING", "value": SIZING_PROPOSAL}))
    assert isinstance(result, ParsedInterpretation)  # pending adoption is where the user sees and decides it


def test_rejects_an_option_whose_label_hides_a_number_that_its_value_carries() -> None:
    response = hunch_response()
    response["questions"][0]["options"][1]["label"] = "Price up more than 1% over the last 15 minutes"  # value is 0.02
    assert_rejected(parse(response, HUNCH_INTAKE), "option_label_omits_value", "/questions/0/options/1/label")

    response = hunch_response()
    response["questions"][0]["options"][0]["label"] = "A strong rise"  # value carries 0.01 but the label states none
    assert_rejected(parse(response, HUNCH_INTAKE), "option_label_omits_value", "/questions/0/options/0/label")


def test_checks_each_conflicting_alternative_against_its_own_quoted_words() -> None:
    sentence = "Buy above 1% but also buy above 3%."
    intake = volume_rule_intake(sentence)

    def alternative(value: str, passage: str) -> dict[str, Any]:
        return {"value": {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 1},
                                               {"op": "constant", "value": value, "unit": "DIMENSIONLESS"}]},
                "source_passage": passage}

    def response_with(second_value: str) -> dict[str, Any]:
        return {"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "READY",
                "field_evidence": [{"field_name": "entry", "state": "CONFLICTING", "conflicts": [
                    alternative("0.01", "Buy above 1%"), alternative(second_value, "buy above 3%")]}],
                "questions": []}

    assert isinstance(parse(response_with("0.03"), intake), ParsedInterpretation)
    assert_rejected(parse(response_with("3"), intake), "ungrounded_number", "/field_evidence/0/conflicts/1/value")


# --- Follow-up reply: the model lists only what changes; stated meaning is never silently overwritten ---

from edge_os_api.research.interpretation_response import ClarificationAnswer, parse_follow_up_response  # noqa: E402

ANSWER_REF = "answer:choose-entry"


def stored(item: dict[str, Any]) -> dict[str, Any]:
    """An evidence item as saved on a previous revision (its revision id is bound)."""
    return {**item, "interpretation_revision": "33333333-3333-4333-8333-333333333333"}


RESTRICTIONS_ITEM = stored({"field_name": "restrictions", "state": "KNOWN", "origin": "USER_STATED",
                            "source_ref": "intake:restrictions", "evidence_status": "VERIFIED_FACT",
                            "value": ["no leverage"]})
MISSING_ENTRY = stored({"field_name": "entry", "state": "MISSING", "origin": "USER_STATED",
                        "source_ref": "intake:original_request", "evidence_status": "UNKNOWN"})
STATED_ENTRY = stored({"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                       "source_ref": "intake:original_request#c0-47", "evidence_status": "HYPOTHESIS",
                       "value": ENTRY_VALUE})
STATED_EXIT = stored({"field_name": "exit", "state": "KNOWN", "origin": "USER_STATED",
                      "source_ref": "intake:original_request#c53-97", "evidence_status": "HYPOTHESIS",
                      "value": EXIT_VALUE})
ADOPTED_SIZING = stored({"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED",
                         "source_ref": "agent:proposal", "evidence_status": "HYPOTHESIS", "adoption": "ADOPTED",
                         "value": SIZING_PROPOSAL})
PENDING_SIZING = {**ADOPTED_SIZING, "adoption": "PENDING"}
TWO_PERCENT = {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                    {"op": "constant", "value": "0.02", "unit": "DIMENSIONLESS"}]}


def follow_up(delta: list[dict[str, Any]], previous: list[dict[str, Any]], reply: str,
              intake: dict[str, Any] = THESIS_INTAKE) -> ParsedInterpretation | Rejection:
    response = {**thesis_response(), "field_evidence": delta}
    return parse_follow_up_response(json.dumps(response), intake, previous, ClarificationAnswer(ANSWER_REF, reply))


def by_name(result: ParsedInterpretation) -> dict[str, dict[str, Any]]:
    return {item["field_name"]: item for item in result.field_evidence}


def test_a_reply_fills_a_missing_field_with_words_taken_from_the_reply() -> None:
    reply = "Price up more than 2% over the last 15 minutes"
    result = follow_up([{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": reply, "value": TWO_PERCENT}], [MISSING_ENTRY, RESTRICTIONS_ITEM], reply,
                       HUNCH_INTAKE | {"restrictions": ["no leverage"]})

    assert isinstance(result, ParsedInterpretation)
    assert by_name(result)["entry"] == {
        "field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_ref": "answer:choose-entry#c0-46",
        "interpretation_revision": "", "evidence_status": "HYPOTHESIS", "value": TWO_PERCENT}


def test_fields_the_reply_does_not_change_are_carried_forward_word_for_word() -> None:
    reply = "Use a fixed 100 quote units per entry"
    result = follow_up([{"field_name": "sizing", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": "100 quote units", "value": SIZING_PROPOSAL}],
                       [STATED_ENTRY, STATED_EXIT, RESTRICTIONS_ITEM], reply)

    assert isinstance(result, ParsedInterpretation)
    assert [(i["field_name"], i["source_ref"], i.get("value")) for i in result.field_evidence] == [
        ("entry", "intake:original_request#c0-47", ENTRY_VALUE), ("exit", "intake:original_request#c53-97", EXIT_VALUE),
        ("restrictions", "intake:restrictions", ["no leverage"]), ("sizing", "answer:choose-entry#c12-27", SIZING_PROPOSAL)]
    assert all(item["interpretation_revision"] == "" for item in result.field_evidence)


def test_a_paraphrased_restatement_of_the_same_meaning_is_rejected_because_it_changes_nothing() -> None:
    reply = "I meant above one percent over fifteen minutes"
    result = follow_up([{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": "above one percent", "value": ENTRY_VALUE}],
                       [STATED_ENTRY, RESTRICTIONS_ITEM], reply)

    assert_rejected(result, "reply_changed_nothing", "/field_evidence")  # a saved clarification must change a field


def test_a_reply_that_reports_nothing_is_rejected_because_it_changes_nothing() -> None:
    assert_rejected(follow_up([], [STATED_ENTRY, RESTRICTIONS_ITEM], "ok"), "reply_changed_nothing", "/field_evidence")


def test_rejects_a_silent_overwrite_of_a_value_the_user_stated() -> None:
    reply = "Make it more than 2%"
    result = follow_up([{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": "more than 2%", "value": TWO_PERCENT}], [STATED_ENTRY, RESTRICTIONS_ITEM],
                       reply)
    assert_rejected(result, "silent_overwrite", "/field_evidence/0")


def test_rejects_a_silent_overwrite_of_a_proposal_the_user_adopted() -> None:
    reply = "Use 50 quote units"
    changed = {**SIZING_PROPOSAL, "amount": "50"}
    result = follow_up([{"field_name": "sizing", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": "50 quote units", "value": changed}], [ADOPTED_SIZING, RESTRICTIONS_ITEM],
                       reply)
    assert_rejected(result, "silent_overwrite", "/field_evidence/0")


def test_rejects_the_model_retracting_a_value_the_user_stated() -> None:
    result = follow_up([{"field_name": "entry", "state": "MISSING"}], [STATED_ENTRY, RESTRICTIONS_ITEM], "Hmm, not sure")
    assert_rejected(result, "silent_overwrite", "/field_evidence/0")


def test_a_contradicting_reply_keeps_both_values_as_a_conflict_for_the_user_to_settle() -> None:
    reply = "Make it more than 2%"
    result = follow_up([{"field_name": "entry", "state": "CONFLICTING", "conflicts": [
        {"value": TWO_PERCENT, "source_passage": "more than 2%"}]}], [STATED_ENTRY, RESTRICTIONS_ITEM], reply)

    assert isinstance(result, ParsedInterpretation)
    entry = by_name(result)["entry"]
    assert entry["state"] == "CONFLICTING" and "value" not in entry
    assert entry["conflicts"] == [{"value": ENTRY_VALUE, "source_ref": "intake:original_request#c0-47"},
                                  {"value": TWO_PERCENT, "source_ref": "answer:choose-entry#c8-20"}]


def test_a_conflict_that_repeats_the_earlier_value_is_not_a_conflict() -> None:
    result = follow_up([{"field_name": "entry", "state": "CONFLICTING", "conflicts": [
        {"value": ENTRY_VALUE, "source_passage": "above 1%"}]}], [STATED_ENTRY, RESTRICTIONS_ITEM],
                       "Yes, above 1% please")
    assert_rejected(result, "not_a_conflict", "/field_evidence/0/conflicts/0/value")


def test_a_reply_can_settle_a_conflict_by_stating_the_value() -> None:
    conflicted = stored({"field_name": "entry", "state": "CONFLICTING", "origin": "USER_STATED",
                         "source_ref": "intake:original_request", "evidence_status": "UNKNOWN",
                         "conflicts": [{"value": ENTRY_VALUE, "source_ref": "intake:original_request#c0-47"},
                                       {"value": TWO_PERCENT, "source_ref": "intake:original_request#c60-70"}]})
    reply = "Go with 1%"
    result = follow_up([{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": "1%", "value": ENTRY_VALUE}], [conflicted, RESTRICTIONS_ITEM], reply)

    assert isinstance(result, ParsedInterpretation)
    assert by_name(result)["entry"]["state"] == "KNOWN"
    assert by_name(result)["entry"]["source_ref"] == "answer:choose-entry#c8-10"


def test_a_reply_can_replace_a_pending_proposal_with_the_users_own_value() -> None:
    reply = "Use 50 quote units"
    changed = {**SIZING_PROPOSAL, "amount": "50"}
    result = follow_up([{"field_name": "sizing", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": "50 quote units", "value": changed}], [PENDING_SIZING, RESTRICTIONS_ITEM],
                       reply)

    assert isinstance(result, ParsedInterpretation)
    sizing = by_name(result)["sizing"]
    assert (sizing["origin"], sizing["source_ref"], sizing["value"]["amount"]) == ("USER_STATED",
                                                                                 "answer:choose-entry#c4-18", "50")
    assert "adoption" not in sizing


@pytest.mark.parametrize("passage, value, reason_code", [
    pytest.param("Sell on any dip", TWO_PERCENT, "source_passage_not_in_request", id="words-from-neither-text"),
    pytest.param("more than 2%", {**TWO_PERCENT, "args": [TWO_PERCENT["args"][0], {
        "op": "constant", "value": "2", "unit": "DIMENSIONLESS"}]}, "ungrounded_number", id="percent-read-as-whole"),
])
def test_a_reply_is_grounded_like_the_original_request(passage: str, value: dict[str, Any], reason_code: str) -> None:
    result = follow_up([{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": passage, "value": value}], [MISSING_ENTRY, RESTRICTIONS_ITEM],
                       "Make it more than 2%", HUNCH_INTAKE | {"restrictions": ["no leverage"]})
    assert_rejected(result, reason_code)


def test_a_reply_cannot_alter_a_field_the_application_owns() -> None:
    result = follow_up([{"field_name": "restrictions", "state": "KNOWN", "origin": "USER_STATED",
                         "source_passage": "no leverage", "value": []}], [STATED_ENTRY, RESTRICTIONS_ITEM],
                       "no leverage")
    assert_rejected(result, "reserved_field", "/field_evidence/0/field_name")


def test_a_model_proposal_cannot_settle_a_conflict_the_user_has_not_resolved() -> None:
    conflicted = stored({"field_name": "entry", "state": "CONFLICTING", "origin": "USER_STATED",
                         "source_ref": "intake:original_request", "evidence_status": "UNKNOWN",
                         "conflicts": [{"value": ENTRY_VALUE, "source_ref": "intake:original_request#c0-47"},
                                       {"value": TWO_PERCENT, "source_ref": "intake:original_request#c60-70"}]})
    proposal = {"field_name": "entry", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
                "value": ENTRY_VALUE}
    assert_rejected(follow_up([proposal], [conflicted, RESTRICTIONS_ITEM], "Not sure"), "silent_overwrite",
                    "/field_evidence/0")


# --- The application, not the model, proposes the market binding and the decision interval ---

SYNTHETIC_MARKET = {
    "network": "MONAD",
    "research_binding": {
        "chain_id": None, "underlying_venue": "fixture-underlying-venue/1",
        "pool_address": "0x3333333333333333333333333333333333333333",
        "token_order": ["0x1111111111111111111111111111111111111111", "0x2222222222222222222222222222222222222222"],
        "base_asset": "0x1111111111111111111111111111111111111111",
        "quote_asset": "0x2222222222222222222222222222222222222222", "orientation": "QUOTE_PER_BASE",
        "base_decimals": 18, "quote_decimals": 6, "event_schema_version": "fixture-events/1",
        "amount_conversion_version": "fixture-amounts/1", "data_route": "ENVIO_QUICKNODE_CORROBORATED",
        "evidence_class": "SYNTHETIC_FIXTURE", "qualification": "UNQUALIFIED"},
    "execution_route": {"adapter": "KURU_FLOW_FIXED_INPUT", "identity_state": "UNKNOWN", "identity": None,
                        "qualification": "UNQUALIFIED"},
    "quote_unit": "QUOTE:0x2222222222222222222222222222222222222222"}


def test_a_supported_strategy_request_gets_the_applications_pending_market_and_interval_proposals() -> None:
    result = parse(thesis_response())

    assert isinstance(result, ParsedInterpretation)
    assert by_name(result)["market"] == {
        "field_name": "market", "state": "KNOWN", "origin": "APPLICATION_CONFIGURED",
        "source_ref": "application:synthetic-fixture-market", "interpretation_revision": "",
        "evidence_status": "HYPOTHESIS", "adoption": "PENDING", "value": SYNTHETIC_MARKET}
    assert by_name(result)["decision_interval_seconds"] == {
        "field_name": "decision_interval_seconds", "state": "KNOWN", "origin": "APPLICATION_CONFIGURED",
        "source_ref": "application:five-minute-buckets", "interpretation_revision": "",
        "evidence_status": "HYPOTHESIS", "adoption": "PENDING", "value": 300}


def test_the_application_proposes_no_defaults_for_an_unsupported_meaning() -> None:
    intake = {"original_request": "Tokens launched in the last 24 hours keep running.", "restrictions": [],
              "requested_job": "CREATE_STRATEGY", "input_class": "LOOSE_INTUITION"}
    result = parse({"meaning_status": "UNSUPPORTED", "missing_capability": "token_launch_age_filter",
                    "evidence_readiness": "READY", "field_evidence": [], "questions": []}, intake)

    assert isinstance(result, ParsedInterpretation)
    assert [item["field_name"] for item in result.field_evidence] == ["restrictions"]


@pytest.mark.parametrize("field_name", ["market", "decision_interval_seconds", "restrictions"])
def test_rejects_model_evidence_for_a_field_the_application_owns(field_name: str) -> None:
    item = {"field_name": field_name, "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING", "value": 300}
    assert_rejected(parse(with_item(item)), "reserved_field", "/field_evidence/2/field_name")


@pytest.mark.parametrize("capability", ["x" * 65, "Has Spaces", "line\nbreak", "9starts_with_digit", "UPPER", "a-b"])
def test_rejects_a_missing_capability_that_is_not_a_short_snake_case_name(capability: str) -> None:
    response = {**thesis_response(), "meaning_status": "UNSUPPORTED", "missing_capability": capability,
                "field_evidence": [], "questions": []}
    assert_rejected(parse(response), "invalid_value", "/missing_capability")


# --- Negative numbers and hostile values --------------------------------------------------------------------------------

NEG_PASSAGE = "enter when the 15-minute price return is below -2%"
NEG_INTAKE = {"original_request": NEG_PASSAGE + ", exit when the 5-minute return turns negative", "restrictions": [],
              "requested_job": "CREATE_STRATEGY", "input_class": "CONCRETE_THESIS"}


def negative_entry(value: str = "-0.02", passage: str = NEG_PASSAGE) -> dict[str, Any]:
    entry = {"op": "lt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                  {"op": "constant", "value": value, "unit": "DIMENSIONLESS"}]}
    return {**thesis_response(), "field_evidence": [{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                                                    "source_passage": passage, "value": entry}]}


@pytest.mark.parametrize("passage, value", [
    ("enter when the 15-minute price return is below -2%", "-0.02"),
    ("enter when the 15-minute price return is below −2%", "-0.02"),
    ("enter when the 15-minute price return is below minus 2%", "-0.02"),
    ("enter when the 15-minute price return is below negative 2 percent", "-0.02"),
    ("enter when the 15-minute price return is below -50 bps", "-0.005"),
    ("enter when the 15-minute price return is below -0.5", "-0.5"),
])
def test_accepts_a_negative_value_when_the_words_show_its_sign(passage: str, value: str) -> None:
    intake = {**NEG_INTAKE, "original_request": passage + ", exit when the 5-minute return turns negative"}
    result = parse(negative_entry(value, passage), intake)
    assert isinstance(result, ParsedInterpretation)
    assert {i["field_name"]: i for i in result.field_evidence}["entry"]["value"]["args"][1]["value"] == value


@pytest.mark.parametrize("passage, value", [
    ("enter when the 15-minute price return is below 2%", "-0.02"),          # the words show no sign
    ("enter when the 15-minute price return is below -2%", "0.02"),          # the words show a sign the value drops
    ("enter when the 15-minute price return is below 15-2%", "-0.02"),       # a dash inside a word is not a sign
    ("enter when the 15-minute price return is below -2%", "-0.2"),          # wrong scale
])
def test_rejects_a_sign_that_the_words_do_not_support(passage: str, value: str) -> None:
    intake = {**NEG_INTAKE, "original_request": passage + ", exit when the 5-minute return turns negative"}
    assert_rejected(parse(negative_entry(value, passage), intake), "ungrounded_number")


def test_a_dash_between_a_number_and_a_unit_is_not_a_sign() -> None:
    from edge_os_api.research.interpretation_response import _numbers_in
    stated = _numbers_in("the 15-minute return and the 5-10 range")
    assert 15 in stated and 5 in stated and 10 in stated
    assert not any(n < 0 for n in stated)


def test_accepts_an_option_label_that_shows_the_negative_sign() -> None:
    response = hunch_response()
    response["questions"][0]["options"] = [{"id": "down2", "label": "Price below -2% over the last 15 minutes",
        "value": {"op": "lt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                       {"op": "constant", "value": "-0.02", "unit": "DIMENSIONLESS"}]}}]
    assert isinstance(parse(response, HUNCH_INTAKE), ParsedInterpretation)
    response["questions"][0]["options"][0]["label"] = "Price down more than 2% over the last 15 minutes"
    assert_rejected(parse(response, HUNCH_INTAKE), "option_label_omits_value")


@pytest.mark.parametrize("hostile", [
    {"field_name": ["entry"], "state": "MISSING"},
    {"field_name": {"a": 1}, "state": "MISSING"},
    {"field_name": 5, "state": "MISSING"},
    {"field_name": None, "state": "MISSING"},
])
def test_a_field_name_that_is_not_text_is_rejected_not_raised(hostile: dict[str, Any]) -> None:
    response = {**thesis_response(), "field_evidence": [hostile]}
    assert_rejected(parse(response), "invalid_value", "/field_evidence/0/field_name")


@pytest.mark.parametrize("name", [["entry"], {"a": 1}, 7, None])
def test_a_question_field_name_that_is_not_text_is_rejected_not_raised(name: Any) -> None:
    response = hunch_response()
    response["questions"][0]["field_name"] = name
    assert_rejected(parse(response, HUNCH_INTAKE), "invalid_value", "/questions/0/field_name")


@pytest.mark.parametrize("quantity", ["sNaN", "NaN", "Infinity", "-Infinity", "snan"])
def test_a_non_finite_decimal_is_rejected_not_raised(quantity: str) -> None:
    response = thesis_response()
    response["field_evidence"][0]["value"]["args"][1]["value"] = quantity
    assert isinstance(parse(response), Rejection)


def test_a_value_nested_far_too_deep_is_rejected_not_raised() -> None:
    deep: Any = "x"
    for _ in range(1500):
        deep = {"op": "not", "value": deep}
    response = thesis_response()
    response["field_evidence"][0]["value"] = deep
    result = parse(response)
    assert isinstance(result, Rejection)


def test_no_json_value_makes_a_parser_raise() -> None:
    hostile_values: list[Any] = [None, True, 0, "", [], {}, [[]], {"op": []}, {"op": {}}, {"args": 5}, "9" * 5000]
    for field in ("source_passage", "value", "state", "origin", "adoption", "conflicts", "field_name"):
        for value in hostile_values:
            item = {"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": ENTRY_PASSAGE,
                    "value": copy.deepcopy(ENTRY_VALUE)}
            item[field] = copy.deepcopy(value)
            result = parse({**thesis_response(), "field_evidence": [item]})
            assert isinstance(result, (ParsedInterpretation, Rejection)), (field, value)


# --- Decoded values that a saved record cannot hold -------------------------------------------------------------------------

def with_sizing(value: Any) -> dict[str, Any]:
    return {**thesis_response(), "field_evidence": thesis_response()["field_evidence"] + [
        {"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING", "value": value}]}


@pytest.mark.parametrize("value", [
    {"note": "a\x00b"}, {"note": "a\ud800b"}, {"a\x00": 1}, {"nested": [{"deeper": "x\x00"}]},
    {"note": "é"},  # a decomposed accent: not NFC
])
def test_rejects_a_decoded_value_that_a_saved_record_cannot_hold(value: Any) -> None:
    # json.dumps writes the NUL and the surrogate as JSON escapes, so the raw text itself is plain ASCII.
    assert_rejected(parse(with_sizing(value)), "unstorable_text")


@pytest.mark.parametrize("levels", [91, 250, 300, 950])
def test_rejects_a_value_nested_deeper_than_a_saved_record_may_be(levels: int) -> None:
    deep: Any = "x"
    for _ in range(levels):
        deep = [deep]
    assert_rejected(parse(with_sizing(deep)), "value_too_deep")


@pytest.mark.parametrize("levels", [10, 40, 80])
def test_accepts_a_value_nested_within_the_limit(levels: int) -> None:
    deep: Any = "x"
    for _ in range(levels):
        deep = [deep]
    assert isinstance(parse(with_sizing(deep)), ParsedInterpretation)


def test_the_same_check_covers_questions_conflicts_and_replies() -> None:
    bad_question = hunch_response()
    bad_question["questions"][0]["text"] = "What counts as a rise\x00?"
    assert_rejected(parse(bad_question, HUNCH_INTAKE), "unstorable_text")
    reply_response = {**thesis_response(), "field_evidence": [{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
        "source_passage": "price up more than 1%", "value": {**ENTRY_VALUE, "note": "a\x00b"}}]}
    result = parse_follow_up_response(json.dumps(reply_response), THESIS_INTAKE, [],
                                      ClarificationAnswer("reply:1", "price up more than 1%"))
    assert_rejected(result, "unstorable_text")


# --- Sweep: whatever the parser accepts must be publishable ------------------------------------------------------------------

HOSTILE_VALUES: list[Any] = [
    None, True, False, 0, -1, 2 ** 70, "", " ", "a\x00b", "a\ud800b", "é", "‮", "−", "9" * 400, "x" * 5000,
    "sNaN", "NaN", "Infinity", "-0", "1e999", [], {}, [[]], [None], {"": None}, {"op": []}, {"op": {}}, {"args": 5},
    ["x"] * 300,
]


def mutations(base: Any, path: tuple[Any, ...] = ()) -> list[tuple[tuple[Any, ...], Any]]:
    """Every position of a JSON value, each paired with each hostile value."""
    found: list[tuple[tuple[Any, ...], Any]] = [(path, hostile) for hostile in HOSTILE_VALUES]
    if isinstance(base, dict):
        for key, child in base.items():
            found.extend(mutations(child, path + (key,)))
    elif isinstance(base, list):
        for index, child in enumerate(base):
            found.extend(mutations(child, path + (index,)))
    return found


def plant(base: Any, path: tuple[Any, ...], value: Any) -> Any:
    if not path:
        return copy.deepcopy(value)
    changed = copy.deepcopy(base)
    node = changed
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = copy.deepcopy(value)
    return changed


def assert_publishable(result: ParsedInterpretation, intake: dict[str, Any]) -> None:
    """What the workflow stores for an accepted answer must pass the record contract and its size limit.

    This oracle is the contract alone. The HTTP sweep in test_hermes_research_flow.py is the independent proof: it
    publishes for real.
    """
    from edge_os_api.records import contract_adapter as record_contract
    content = {"intake_record_id": "22222222-2222-4222-8222-222222222222",
               "interpretation_revision_id": "11111111-1111-4111-8111-111111111111",
               "input_class": intake["input_class"], "requested_job": intake["requested_job"],
               "field_evidence": [{**item, "interpretation_revision": "11111111-1111-4111-8111-111111111111"}
                                  for item in result.field_evidence],
               "clarification_history": [], "preserved_restrictions": list(intake["restrictions"]),
               "meaning_status": result.meaning_status, "syntax_status": "VALID",
               "evidence_readiness": result.evidence_readiness}
    record_contract.validate_record("PromptInterpretation", content)
    assert len(record_contract.canonical_bytes(content)) <= 65536


@pytest.mark.parametrize("name, response, intake", [
    ("thesis", thesis_response(), THESIS_INTAKE),
    ("hunch", hunch_response(), HUNCH_INTAKE),
    ("conflict", conflicting_response(), THESIS_INTAKE),
])
def test_no_hostile_value_at_any_position_makes_the_parser_raise_or_accept_something_unpublishable(
        name: str, response: dict[str, Any], intake: dict[str, Any]) -> None:
    checked = accepted = 0
    for path, hostile in mutations(response):
        result = parse(plant(response, path, hostile), intake)
        assert isinstance(result, (ParsedInterpretation, Rejection)), (name, path, hostile)
        checked += 1
        if isinstance(result, ParsedInterpretation):
            accepted += 1
            try:
                assert_publishable(result, intake)
            except Exception as error:  # noqa: BLE001 - report the exact planting that slipped through
                raise AssertionError(f"accepted but not publishable: {name} at {path} with {hostile!r}: {error!r}") from error
    assert checked > 500 and accepted > 0, (name, checked, accepted)


@pytest.mark.parametrize("question_id", ["ask-exit", "ask-entry", "ask-", "adopt-suggested-settings"])
def test_rejects_a_question_id_that_the_application_names_its_own_questions_with(question_id: str) -> None:
    response = hunch_response()
    response["questions"][0]["question_id"] = question_id
    assert_rejected(parse(response, HUNCH_INTAKE), "reserved_question_id", "/questions/0/question_id")


@pytest.mark.parametrize("where, change", [
    ("question_id", lambda q: q.update(question_id="q" * 201)),
    ("option id", lambda q: q["options"][0].update(id="o" * 201)),
])
def test_rejects_an_identifier_longer_than_the_answer_route_accepts(where: str, change: Any) -> None:
    response = hunch_response()
    change(response["questions"][0])
    assert isinstance(parse(response, HUNCH_INTAKE), Rejection), where
    response = hunch_response()
    response["questions"][0]["question_id"] = "q" * 200
    response["questions"][0]["options"][0]["id"] = "o" * 200
    assert isinstance(parse(response, HUNCH_INTAKE), ParsedInterpretation)


def test_rejects_a_question_or_label_longer_than_a_page_can_show() -> None:
    response = hunch_response()
    response["questions"][0]["text"] = "w" * 600 + "?"
    assert_rejected(parse(response, HUNCH_INTAKE), "question_text_invalid", "/questions/0/text")
    response = hunch_response()
    response["questions"][0]["options"][0]["label"] = "Price up more than 1% " + "x" * 400
    assert isinstance(parse(response, HUNCH_INTAKE), Rejection)


def test_a_non_finite_float_in_a_value_is_unstorable() -> None:
    from edge_os_api.research.interpretation_response import unstorable
    assert unstorable({"a": float("nan")}) is not None and unstorable({"a": float("inf")}) is not None
    assert unstorable({"a": 1.5, "b": [True, None, "ok"]}) is None
