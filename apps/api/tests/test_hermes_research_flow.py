"""The saved Research path through the Hermes interpreter, tested over authenticated HTTP and the real database.

Only the Hermes process boundary is scripted (`CaseRunner`, with authored provider behaviour). Everything else is the
application: routes, authentication, owner scoping, the ledger, PostgreSQL storage and the P02 record lineage. The
actual pinned Hermes runs the same cases in `tests/hermes_interpretation`. No model is called.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from flows import RESTRICTIONS, publish
from hermes_cases import CaseRunner, case, intake_body, provider_text, reply, turn_result
from test_interpretation_response import ENTRY_VALUE, EXIT_VALUE

from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app

REPLY_TWO_PERCENT = "Price up more than 2% over the last 15 minutes"
TWO_PERCENT = {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                    {"op": "constant", "value": "0.02", "unit": "DIMENSIONLESS"}]}


@pytest.fixture
def make_client(env, migrated):
    """Build applications over the shared database whose interpreter is Hermes with a scripted process boundary."""
    opened: list[TestClient] = []

    def build(runner: CaseRunner) -> TestClient:
        settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})
        client = TestClient(create_app(settings, hermes_runner=runner))
        client.__enter__()
        opened.append(client)
        return client

    yield build
    for client in opened:
        client.__exit__(None, None, None)


def create(client: TestClient, headers: dict[str, str], name: str):
    return client.post("/v1/research/requests", json=intake_body(name), headers=headers)


def answer(client: TestClient, headers: dict[str, str], bundle: dict[str, Any], question_id: str, **choice: str):
    return client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/clarifications", headers=headers, json={
        "previous_revision_id": bundle["head"]["interpretation_revision_id"], "question_id": question_id, **choice})


def retry(client: TestClient, headers: dict[str, str], bundle: dict[str, Any], retry_of: str | None):
    return client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/interpretation-retries", headers=headers,
                       json={"retry_of": retry_of})


def rows(client: TestClient, statement: str, **params: Any) -> list[Any]:
    with client.app.state.engine.begin() as connection:
        return list(connection.execute(text(statement), params))


def no_model_text(bundle: dict[str, Any], *fragments: str) -> None:
    """Public views carry structured values and hashes, never the generated text itself (decision D5)."""
    dumped = json.dumps(bundle)
    for fragment in fragments:
        assert fragment not in dumped


# --- Concrete thesis -----------------------------------------------------------------------------------------------

def test_a_concrete_thesis_is_read_from_the_users_words_and_compiles_only_after_adoption(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)

    created = create(client, owner_a, "concrete-thesis")

    assert created.status_code == 201, created.text
    bundle = created.json()
    assert bundle["interpreter"]["kind"] == "HERMES_LOCAL_FAKE_PROVIDER"
    assert "No real model" in bundle["interpreter"]["notice"]
    assert bundle["head"]["outcome"] == "NEEDS_CLARIFICATION" and bundle["head"]["draft_id"] is None
    evidence = {i["field_name"]: i for i in bundle["interpretations"][0]["content"]["field_evidence"]}
    assert (evidence["entry"]["origin"], evidence["entry"]["value"]) == ("USER_STATED", ENTRY_VALUE)
    assert evidence["entry"]["source_ref"] == "intake:original_request#c0-47"
    assert (evidence["exit"]["origin"], evidence["exit"]["value"]) == ("USER_STATED", EXIT_VALUE)
    assert evidence["sizing"]["origin"] == "AGENT_PROPOSED" and evidence["sizing"]["adoption"] == "PENDING"
    assert evidence["market"]["origin"] == "APPLICATION_CONFIGURED" and evidence["market"]["adoption"] == "PENDING"
    [question] = bundle["head"]["questions"]
    assert question["kind"] == "ADOPT"
    [attempt] = bundle["attempts"]
    assert (attempt["sequence"], attempt["purpose"], attempt["status"], attempt["completion"]) == (
        1, "INTERPRET", "COMPLETED", "COMPLETE")
    assert attempt["usage"] == {"source": "PROVIDER_REPORTED", "input_tokens": 1423, "output_tokens": 611,
                                "total_tokens": 2034}
    assert isinstance(attempt["latency_ms"], int) and attempt["latency_ms"] >= 0
    assert attempt["parse_result"] == "ACCEPTED" and attempt["request_count"] == 1
    assert attempt["revision_id"] == bundle["head"]["interpretation_revision_id"]
    assert attempt["identity"]["runtime_label"] == "LOCAL_FAKE_PROVIDER"
    assert attempt["identity"]["prompt_version"] == "p05-interpretation/3"
    assert len(attempt["identity"]["task_sha256"]) == 64
    no_model_text(bundle, '"source_passage"', "Buy when the 15-minute price return is above 1%\", \"value\"")
    assert runner.turns[0].user_message.startswith("{")

    adopted = answer(client, owner_a, bundle, "adopt-suggested-settings", choice_id="adopt")

    assert adopted.status_code == 201, adopted.text
    final = adopted.json()
    assert final["head"]["outcome"] == "COMPILED" and final["head"]["draft_id"] is not None
    assert len(runner.turns) == 1, "adopting settings is deterministic and calls no model"
    assert len(final["attempts"]) == 1
    assert client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a).json() == final
    published, _ = publish(client, owner_a, final)
    assert published.status_code == 201, published.text


def test_the_saved_attempt_rows_match_what_the_api_returns(make_client, owner_a) -> None:
    client = make_client(CaseRunner(turn_result(case("concrete-thesis")["provider"])))
    bundle = create(client, owner_a, "concrete-thesis").json()
    [attempt] = bundle["attempts"]

    [stored] = rows(client, "select a.sequence, a.purpose, a.prompt_version, a.task_sha256, a.config_sha256, "
                            "a.runtime_label, s.status, s.input_tokens, s.output_tokens, s.total_tokens, s.usage_source,"
                            " s.latency_ms, s.request_count, s.response_sha256, s.parse_result, l.revision_record_id::text "
                            "from interpretation_attempts a join interpretation_settlements s using (attempt_id) "
                            "join interpretation_attempt_links l using (attempt_id) where a.attempt_id = :a",
                    a=attempt["attempt_id"])

    identity = attempt["identity"]
    assert tuple(stored) == (1, "INTERPRET", identity["prompt_version"], identity["task_sha256"],
                             identity["config_sha256"], identity["runtime_label"], "COMPLETED", 1423, 611, 2034,
                             "PROVIDER_REPORTED", attempt["latency_ms"], 1, attempt["response_sha256"], "ACCEPTED",
                             attempt["revision_id"])
    [operation] = rows(client, "select count(distinct operation_id) from records where intake_record_id = :i "
                               "and record_type in ('PromptInterpretation', 'Outcome')", i=bundle["intake"]["record_id"])
    assert operation[0] == 1  # the records written from one attempt share that attempt's id as their operation id


# --- Rough hunch, choices and free-text replies --------------------------------------------------------------------

def test_a_rough_hunch_gets_the_models_questions_and_a_chosen_option_calls_no_model(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("rough-hunch")["provider"]))
    client = make_client(runner)

    bundle = create(client, owner_a, "rough-hunch").json()

    assert bundle["head"]["outcome"] == "NEEDS_CLARIFICATION"
    questions = {q["question_id"]: q for q in bundle["head"]["questions"]}
    assert {"choose-entry", "choose-exit", "adopt-suggested-settings"} <= set(questions)
    assert [o["id"] for o in questions["choose-entry"]["options"]] == ["g3-1pct", "g3-2pct"]
    entry = next(i for i in bundle["interpretations"][0]["content"]["field_evidence"] if i["field_name"] == "entry")
    assert entry["state"] == "MISSING"

    chosen = answer(client, owner_a, bundle, "choose-entry", choice_id="g3-2pct")
    assert chosen.status_code == 201, chosen.text
    after = chosen.json()
    entry = next(i for i in after["interpretations"][-1]["content"]["field_evidence"] if i["field_name"] == "entry")
    assert (entry["origin"], entry["value"]) == ("USER_CONFIRMED", TWO_PERCENT)
    assert {q["question_id"] for q in after["head"]["questions"]} >= {"choose-exit", "adopt-suggested-settings"}
    assert "choose-entry" not in {q["question_id"] for q in after["head"]["questions"]}
    assert len(runner.turns) == 1 and len(after["attempts"]) == 1


def hunch_follow_up(name: str, delta: list[dict[str, Any]]) -> dict[str, Any]:
    first = case(name)["provider"]["model_response"]
    return {**first, "field_evidence": delta, "questions": []}


def test_a_free_text_reply_is_read_by_the_model_and_kept_exactly(make_client, owner_a) -> None:
    follow_up = hunch_follow_up("rough-hunch", [{
        "field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": REPLY_TWO_PERCENT,
        "value": TWO_PERCENT}])
    runner = CaseRunner(turn_result(case("rough-hunch")["provider"]), reply(follow_up))
    client = make_client(runner)
    bundle = create(client, owner_a, "rough-hunch").json()

    response = answer(client, owner_a, bundle, "choose-entry", answer_text=REPLY_TWO_PERCENT)

    assert response.status_code == 201, response.text
    after = response.json()
    entry = next(i for i in after["interpretations"][-1]["content"]["field_evidence"] if i["field_name"] == "entry")
    assert (entry["origin"], entry["value"]) == ("USER_STATED", TWO_PERCENT)
    assert entry["source_ref"].endswith("#c0-46") and entry["source_ref"].startswith("reply:")
    [clarification] = after["clarifications"]
    assert clarification["content"]["answer_ref"] == entry["source_ref"].split("#")[0]
    assert clarification["content"]["changed_fields"] == ["entry"]
    assert [a["purpose"] for a in after["attempts"]] == ["INTERPRET", "FOLLOW_UP"]
    follow = after["attempts"][1]
    assert follow["identity"]["answer_ref"] == clarification["content"]["answer_ref"]
    assert follow["identity"]["previous_revision_id"] == bundle["head"]["interpretation_revision_id"]
    assert follow["revision_id"] == after["head"]["interpretation_revision_id"]
    [stored] = rows(client, "select answer_text, answer_sha256 from interpretation_attempts where attempt_id = :a",
                    a=follow["attempt_id"])
    assert stored[0] == REPLY_TWO_PERCENT and len(stored[1]) == 64
    assert json.loads(runner.turns[1].user_message)["answer"] == REPLY_TWO_PERCENT
    no_model_text(after, REPLY_TWO_PERCENT + "\"")  # the reply is kept as a hash in the public attempt view


def test_a_reply_that_states_two_values_becomes_a_conflict_with_both_quotes(make_client, owner_a) -> None:
    both = "Price up more than 1% over the last 15 minutes. Actually, Price up more than 2% over the last 15 minutes"
    follow_up = hunch_follow_up("rough-hunch", [{
        "field_name": "entry", "state": "CONFLICTING",
        "conflicts": [{"value": ENTRY_VALUE, "source_passage": "Price up more than 1% over the last 15 minutes"},
                      {"value": TWO_PERCENT, "source_passage": "Price up more than 2% over the last 15 minutes"}]}])
    client = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"]), reply(follow_up)))
    bundle = create(client, owner_a, "rough-hunch").json()

    response = answer(client, owner_a, bundle, "choose-entry", answer_text=both)

    assert response.status_code == 201, response.text
    after = response.json()
    entry = next(i for i in after["interpretations"][-1]["content"]["field_evidence"] if i["field_name"] == "entry")
    assert entry["state"] == "CONFLICTING"
    assert [alt["value"] for alt in entry["conflicts"]] == [ENTRY_VALUE, TWO_PERCENT]
    assert after["head"]["outcome"] == "NEEDS_CLARIFICATION"
    codes = {f["path"]: f["code"] for f in after["outcomes"][-1]["record"]["content"]["findings"]}
    assert codes["/field_evidence/entry"] == "conflicting_field"
    assert "ask-entry" in {q["question_id"] for q in after["head"]["questions"]}  # the user can settle it in words
    first_entry = next(i for i in after["interpretations"][0]["content"]["field_evidence"] if i["field_name"] == "entry")
    assert first_entry["state"] == "MISSING"  # the first revision is unchanged and still stored


def test_a_reply_whose_quote_does_not_state_the_number_it_claims_is_rejected_and_the_saved_meaning_stays(
        make_client, owner_a) -> None:
    overwrite = hunch_follow_up("rough-hunch", [{
        "field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": "below zero",
        "value": TWO_PERCENT}])
    client = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"]), reply(overwrite)))
    chosen = answer(client, owner_a, create(client, owner_a, "rough-hunch").json(), "choose-entry", choice_id="g3-1pct")
    bundle = chosen.json()

    response = answer(client, owner_a, bundle, "choose-exit", answer_text="exit when the return is below zero")

    assert response.status_code == 200, response.text
    after = response.json()
    assert len(after["interpretations"]) == 2
    assert after["head"]["interpretation_revision_id"] == bundle["head"]["interpretation_revision_id"]
    assert after["head"]["outcome"] == bundle["head"]["outcome"] and after["head"]["questions"] == bundle["head"]["questions"]
    reply_state = after["head"]["reply"]
    assert (reply_state["state"], reply_state["reason_code"]) == ("REJECTED", "ungrounded_number")
    assert [a["status"] for a in after["attempts"]] == ["COMPLETED", "COMPLETED"]
    assert after["attempts"][1]["revision_id"] is None
    saved_entry = next(i for i in after["interpretations"][-1]["content"]["field_evidence"] if i["field_name"] == "entry")
    assert (saved_entry["origin"], saved_entry["value"]) == ("USER_CONFIRMED", ENTRY_VALUE)


def test_a_reply_that_replaces_stated_meaning_with_a_quoted_value_is_rejected_whole(make_client, owner_a) -> None:
    reply_text = "exit when the return is below zero, and make the entry more than 2%"
    overwrite = hunch_follow_up("rough-hunch", [{
        "field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": "more than 2%",
        "value": TWO_PERCENT}])
    client = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"]), reply(overwrite)))
    bundle = answer(client, owner_a, create(client, owner_a, "rough-hunch").json(), "choose-entry",
                    choice_id="g3-1pct").json()

    response = answer(client, owner_a, bundle, "choose-exit", answer_text=reply_text)

    after = response.json()
    assert response.status_code == 200 and after["head"]["reply"]["reason_code"] == "silent_overwrite"
    assert after["attempts"][1]["parse_result"] == "REJECTED:silent_overwrite"
    assert len(after["interpretations"]) == 2 and after["head"]["retry"]["allowed"] is True


# --- Bounded no-thesis and unsupported capability --------------------------------------------------------------------

def test_a_bounded_no_thesis_request_stays_unresolved_and_creates_no_strategy(make_client, owner_a) -> None:
    client = make_client(CaseRunner(turn_result(case("bounded-no-thesis")["provider"])))

    bundle = create(client, owner_a, "bounded-no-thesis").json()

    assert bundle["head"]["outcome"] == "UNRESOLVED" and bundle["head"]["draft_id"] is None
    assert bundle["drafts"] == [] and bundle["head"]["questions"] == []
    names = [i["field_name"] for i in bundle["interpretations"][0]["content"]["field_evidence"]]
    assert names == ["market", "restrictions"]


def test_an_unsupported_extension_is_reported_as_missing_capability_not_as_a_failure(make_client, owner_a) -> None:
    client = make_client(CaseRunner(turn_result(case("unsupported-extension")["provider"])))

    bundle = create(client, owner_a, "unsupported-extension").json()

    assert bundle["head"]["outcome"] == "UNSUPPORTED"
    finding = bundle["outcomes"][-1]["record"]["content"]["findings"][0]
    assert finding["code"] == "missing_capability" and "token_launch_age_filter" in finding["detail"]
    assert bundle["interpretations"][0]["content"]["meaning_status"] == "UNSUPPORTED"
    assert bundle["drafts"] == [] and bundle["attempts"][0]["status"] == "COMPLETED"


# --- Malformed output, truncation, unavailability, retry -------------------------------------------------------------

@pytest.mark.parametrize("name, reason", [("multiple-objects", "multiple_objects"), ("code-fenced", "invalid_json"),
                                          ("ungrounded-number", "ungrounded_number"),
                                          ("self-adopted-proposal", "proposal_must_stay_pending")])
def test_malformed_model_output_is_saved_as_a_rejected_attempt_and_is_not_a_verdict_on_the_idea(
        make_client, owner_a, name: str, reason: str) -> None:
    client = make_client(CaseRunner(turn_result(case(name)["provider"])))

    bundle = create(client, owner_a, name).json()

    outcome = bundle["outcomes"][-1]["record"]["content"]
    assert (outcome["outcome"], outcome["stage"]) == ("INVALID_INPUT", "INTERPRETATION")
    assert outcome["findings"][0]["code"] == "malformed_model_output" and reason in outcome["findings"][0]["detail"]
    assert outcome["retry"] == "SAFE_SAME_KEY"
    assert bundle["interpretations"] == [] and bundle["drafts"] == []
    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["parse_result"], attempt["revision_id"]) == (
        "COMPLETED", f"REJECTED:{reason}", None)
    assert bundle["head"]["retry"] == {"allowed": True, "retry_of": attempt["attempt_id"], "reason": None}
    no_model_text(bundle, provider_text(case(name)["provider"])[:80], '"source_passage"')


@pytest.mark.parametrize("name", ["truncated-cut-off", "truncated-but-parseable"])
def test_a_truncated_answer_is_never_used_and_keeps_its_known_usage(make_client, owner_a, name: str) -> None:
    client = make_client(CaseRunner(turn_result(case(name)["provider"])))

    bundle = create(client, owner_a, name).json()

    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["completion"], attempt["parse_result"]) == (
        "TRUNCATED", "TRUNCATED", "REJECTED:truncated")
    assert attempt["usage"]["output_tokens"] == 611
    assert bundle["interpretations"] == [] and bundle["head"]["retry"]["allowed"] is True


def test_a_provider_failure_is_a_system_failure_with_unknown_usage_and_a_separate_explicit_retry(
        make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("provider-503")["provider"]), turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)

    failed = create(client, owner_a, "concrete-thesis").json()

    outcome = failed["outcomes"][-1]["record"]["content"]
    assert outcome["findings"][0]["code"] == "interpreter_unavailable" and outcome["retry"] == "SAFE_SAME_KEY"
    assert "sk-LEAK" not in json.dumps(failed) and failed["interpretations"] == []
    [first] = failed["attempts"]
    assert (first["status"], first["completion"], first["usage"]) == (
        "PROVIDER_FAILED", "NONE", {"source": "UNKNOWN", "input_tokens": None, "output_tokens": None,
                                    "total_tokens": None})
    assert first["error_class"] == "ProviderHTTPError"

    retried = retry(client, owner_a, failed, first["attempt_id"])

    assert retried.status_code == 201, retried.text
    after = retried.json()
    assert [(a["sequence"], a["status"], a["retry_of"]) for a in after["attempts"]] == [
        (1, "PROVIDER_FAILED", None), (2, "COMPLETED", first["attempt_id"])]
    assert after["attempts"][0] == failed["attempts"][0]  # the failed attempt is preserved unchanged
    assert after["head"]["outcome"] == "NEEDS_CLARIFICATION" and len(after["outcomes"]) == 2


def test_an_unknown_outcome_is_kept_unknown_and_is_not_retried(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("provider-hang")["provider"]), turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)

    hung = create(client, owner_a, "concrete-thesis").json()

    outcome = hung["outcomes"][-1]["record"]["content"]
    assert outcome["findings"][0]["code"] == "interpreter_outcome_unknown" and outcome["retry"] == "RECONCILE"
    [attempt] = hung["attempts"]
    assert (attempt["status"], attempt["completion"]) == ("TIMED_OUT", "UNKNOWN")
    assert attempt["usage"]["source"] == "UNKNOWN"
    assert hung["head"]["retry"] == {"allowed": False, "retry_of": None, "reason": "outcome_uncertain"}

    refused = retry(client, owner_a, hung, attempt["attempt_id"])

    assert refused.status_code == 409
    assert refused.json()["findings"][0]["code"] == "outcome_uncertain"
    assert len(runner.turns) == 1  # nothing was replayed
    after = client.get(f"/v1/research/requests/{hung['intake']['record_id']}", headers=owner_a).json()
    assert after["attempts"] == hung["attempts"]


def test_a_runner_that_raises_leaves_an_unknown_attempt_and_no_traceback(make_client, owner_a) -> None:
    client = make_client(CaseRunner(RuntimeError("boom: sk-LEAK-0002 owner-ZZ")))

    bundle = create(client, owner_a, "concrete-thesis").json()

    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["error_class"]) == ("UNKNOWN", "RuntimeError")
    assert "sk-LEAK" not in json.dumps(bundle) and "boom" not in json.dumps(bundle)


def test_a_retry_that_names_no_failed_attempt_or_a_stale_one_is_refused(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("multiple-objects")["provider"]), turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)
    failed = create(client, owner_a, "multiple-objects").json()

    wrong = retry(client, owner_a, failed, str(uuid.uuid4()))
    assert wrong.status_code == 409 and wrong.json()["findings"][0]["code"] == "retry_target_invalid"
    assert len(runner.turns) == 1

    good = retry(client, owner_a, failed, failed["attempts"][0]["attempt_id"])
    assert good.status_code == 201
    again = retry(client, owner_a, good.json(), good.json()["attempts"][1]["attempt_id"])
    assert again.status_code == 409 and again.json()["findings"][0]["code"] == "nothing_to_retry"
    assert len(runner.turns) == 2


def test_blank_words_are_refused_before_any_model_call(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("rough-hunch")["provider"]))
    client = make_client(runner)
    bundle = create(client, owner_a, "rough-hunch").json()

    refused = answer(client, owner_a, bundle, "choose-entry", answer_text="   \n\t ")

    assert refused.status_code == 422
    assert len(runner.turns) == 1 and len(bundle_after(client, owner_a, bundle)["attempts"]) == 1


def bundle_after(client, headers, bundle):
    return client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=headers).json()


def test_a_bounded_no_thesis_request_with_no_declared_market_offers_the_synthetic_market_for_adoption(
        make_client, owner_a) -> None:
    undeclared = {k: v for k, v in intake_body("bounded-no-thesis").items() if k != "declared_market"}
    runner = CaseRunner(turn_result(case("bounded-no-thesis")["provider"]))
    client = make_client(runner)

    created = client.post("/v1/research/requests", json=undeclared, headers=owner_a)

    assert created.status_code == 201, created.text
    bundle = created.json()
    assert bundle["head"]["outcome"] == "NEEDS_CLARIFICATION"
    [question] = bundle["head"]["questions"]
    assert (question["question_id"], question["kind"]) == ("adopt-suggested-settings", "ADOPT")
    assert [item["field_name"] for item in question["items"]] == ["market"]
    market = evidence(bundle, "market", 0)
    assert (market["origin"], market["adoption"], market["source_ref"]) == (
        "APPLICATION_CONFIGURED", "PENDING", "application:synthetic-fixture-market")
    assert not any(q["kind"] == "TEXT" for q in bundle["head"]["questions"]), "no question the user cannot answer"

    adopted = answer(client, owner_a, bundle, "adopt-suggested-settings", choice_id="adopt")

    assert adopted.status_code == 201, adopted.text
    final = adopted.json()
    assert final["head"]["outcome"] == "UNRESOLVED" and final["drafts"] == []
    assert evidence(final, "market")["adoption"] == "ADOPTED"
    assert len(runner.turns) == 1  # adopting calls no model


@pytest.mark.parametrize("job, outcome", [
    ("COMPARE", "NEEDS_CLARIFICATION"), ("SIMULATE", "UNSUPPORTED"), ("OBSERVE_FORWARD", "UNSUPPORTED"),
    ("REQUEST_LIVE", "UNSUPPORTED")])
def test_no_job_without_a_declared_market_leaves_no_question_that_cannot_be_answered(
        make_client, owner_a, job: str, outcome: str) -> None:
    body = {**{k: v for k, v in intake_body("bounded-no-thesis").items() if k != "declared_market"}, "requested_job": job}
    client = make_client(CaseRunner(turn_result(case("bounded-no-thesis")["provider"])))

    created = client.post("/v1/research/requests", json=body, headers=owner_a)

    assert created.status_code == 201, created.text
    bundle = created.json()
    assert bundle["head"]["outcome"] == outcome
    assert not any(q["kind"] == "TEXT" for q in bundle["head"]["questions"])
    for question in bundle["head"]["questions"]:
        assert question["kind"] == "ADOPT" or question["options"], "every open question can be answered"


def evidence(bundle, name, index=-1):
    return next(i for i in bundle["interpretations"][index]["content"]["field_evidence"] if i["field_name"] == name)


# --- Ownership -----------------------------------------------------------------------------------------------------------

def test_another_owner_cannot_read_answer_or_retry_a_request_and_sees_no_attempts(make_client, owner_a, owner_b) -> None:
    runner = CaseRunner(turn_result(case("provider-503")["provider"]), turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)
    failed = create(client, owner_a, "concrete-thesis").json()
    intake = failed["intake"]["record_id"]

    assert client.get(f"/v1/research/requests/{intake}", headers=owner_b).status_code == 404
    assert retry(client, owner_b, failed, failed["attempts"][0]["attempt_id"]).status_code == 404
    assert client.post(f"/v1/research/requests/{intake}/clarifications", headers=owner_b, json={
        "previous_revision_id": str(uuid.uuid4()), "question_id": "ask-entry", "answer_text": "hello"}).status_code == 404
    assert len(runner.turns) == 1
    assert client.get(f"/v1/research/requests/{intake}", headers=owner_a).json()["attempts"] == failed["attempts"]


# --- Fixture mode keeps its meaning ----------------------------------------------------------------------------------------

def test_the_default_fixture_interpreter_has_no_attempts_free_text_or_retry(client, owner_a) -> None:
    bundle = client.post("/v1/research/requests", headers=owner_a, json={
        "original_request": case("concrete-thesis")["intake"]["original_request"], "restrictions": RESTRICTIONS,
        "requested_job": "CREATE_STRATEGY", "input_class": "CONCRETE_THESIS"}).json()
    assert bundle["interpreter"]["kind"] == "FIXTURE" and bundle["attempts"] == []
    free = answer(client, owner_a, bundle, "adopt-suggested-settings", answer_text="adopt")
    assert free.status_code == 422 and free.json()["findings"][0]["code"] == "free_text_not_supported"
    assert retry(client, owner_a, bundle, None).status_code == 409


def test_a_reply_with_no_saved_result_is_reported_as_unfinished_not_as_a_failure(make_client, owner_a) -> None:
    first = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"])))
    bundle = create(first, owner_a, "rough-hunch").json()
    owner = first.get("/v1/me", headers=owner_a).json()["user_id"]
    from test_interpretation_attempt_store import identity as attempt_identity
    first.app.state.hermes.ledger.begin(owner, bundle["intake"]["record_id"], attempt_identity(
        '{"task":"follow_up","answer":"x"}', purpose="FOLLOW_UP", answer_ref="reply:1", answer_text="x",
        previous_revision_id=bundle["head"]["interpretation_revision_id"]))

    after = first.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a).json()

    assert after["head"]["reply"]["state"] == "UNFINISHED"
    assert after["attempts"][-1]["status"] == "STARTED"
    assert after["head"]["retry"]["reason"] == "attempt_in_flight"


# --- Hostile model output settles as a rejected attempt and stays retryable ------------------------------------------------

def hostile_text(kind: str) -> str:
    good = case("concrete-thesis")["provider"]["model_response"]
    if kind == "list_field_name":
        return json.dumps({**good, "field_evidence": [{"field_name": ["entry"], "state": "MISSING"}]})
    if kind == "snan":
        bad = json.loads(json.dumps(good))
        bad["field_evidence"][0]["value"]["args"][1]["value"] = "sNaN"
        return json.dumps(bad)
    if kind == "nul":
        return json.dumps(good) + "\x00"
    if kind == "surrogate":
        return json.dumps(good) + "\ud800"
    raise AssertionError(kind)


@pytest.mark.parametrize("kind, reason", [("list_field_name", "invalid_value"), ("snan", "ungrounded_number"),
                                          ("nul", "unstorable_text"), ("surrogate", "unstorable_text")])
def test_hostile_model_output_settles_as_a_rejected_attempt_with_its_usage_and_allows_a_retry(
        make_client, owner_a, kind: str, reason: str) -> None:
    from edge_os_api.research.interpretation_attempts import Usage
    hostile = reply(json.loads(json.dumps(case("concrete-thesis")["provider"]["model_response"])),
                    usage=Usage(1500, 400, 1900, "PROVIDER_REPORTED"), text=hostile_text(kind))
    runner = CaseRunner(hostile, turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)

    created = create(client, owner_a, "concrete-thesis")

    assert created.status_code == 201, created.text
    bundle = created.json()
    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["completion"], attempt["parse_result"]) == ("COMPLETED", "COMPLETE", f"REJECTED:{reason}")
    assert attempt["usage"] == {"source": "PROVIDER_REPORTED", "input_tokens": 1500, "output_tokens": 400, "total_tokens": 1900}
    assert bundle["outcomes"][-1]["record"]["content"]["findings"][0]["code"] == "malformed_model_output"
    assert bundle["head"]["retry"]["allowed"] is True
    assert attempt["response_sha256"] is not None

    retried = retry(client, owner_a, bundle, attempt["attempt_id"])

    assert retried.status_code == 201, retried.text
    assert retried.json()["head"]["outcome"] == "NEEDS_CLARIFICATION"
    assert [a["status"] for a in retried.json()["attempts"]] == ["COMPLETED", "COMPLETED"]


def test_a_hostile_reply_leaves_the_saved_meaning_and_settles_the_reply_attempt(make_client, owner_a) -> None:
    from edge_os_api.research.interpretation_attempts import Usage
    hostile = reply(case("rough-hunch")["provider"]["model_response"], usage=Usage(900, 120, 1020, "PROVIDER_REPORTED"),
                    text=hostile_text("list_field_name"))
    client = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"]), hostile))
    bundle = create(client, owner_a, "rough-hunch").json()

    response = answer(client, owner_a, bundle, "choose-entry", answer_text="up more than 2% over the last 15 minutes")

    assert response.status_code == 200, response.text
    after = response.json()
    assert after["attempts"][-1]["parse_result"] == "REJECTED:invalid_value"
    assert after["head"]["reply"]["state"] == "REJECTED"
    assert len(after["interpretations"]) == 1


def test_a_negative_threshold_is_read_from_the_users_words_and_compiles_after_adoption(make_client, owner_a) -> None:
    words = ("Buy the dip: enter when the 15-minute price return is below -2%, and exit when the 5-minute return turns "
             "negative. Spot only.")
    good = json.loads(json.dumps(case("concrete-thesis")["provider"]["model_response"]))
    good["field_evidence"][0]["source_passage"] = "enter when the 15-minute price return is below -2%"
    good["field_evidence"][0]["value"] = {"op": "lt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                                              {"op": "constant", "value": "-0.02", "unit": "DIMENSIONLESS"}]}
    good["field_evidence"][1]["source_passage"] = "exit when the 5-minute return turns negative"
    client = make_client(CaseRunner(reply(good)))
    body = {**intake_body("concrete-thesis"), "original_request": words}

    created = client.post("/v1/research/requests", json=body, headers=owner_a)

    assert created.status_code == 201, created.text
    bundle = created.json()
    assert bundle["attempts"][0]["parse_result"] == "ACCEPTED"
    assert evidence(bundle, "entry", 0)["value"]["args"][1]["value"] == "-0.02"
    adopted = answer(client, owner_a, bundle, "adopt-suggested-settings", choice_id="adopt")
    assert adopted.json()["head"]["outcome"] == "COMPILED"


# --- Values that parse but could not be saved, and provider values that could not be settled --------------------------------

def thesis_with_sizing(value: Any) -> str:
    good = json.loads(json.dumps(case("concrete-thesis")["provider"]["model_response"]))
    sizing = next(i for i in good["field_evidence"] if i["field_name"] == "sizing")
    sizing["value"] = value
    return json.dumps(good)


def nested(levels: int) -> Any:
    deep: Any = "x"
    for _ in range(levels):
        deep = [deep]
    return deep


@pytest.mark.parametrize("name, value, reason", [
    ("escaped NUL", {"note": "a\x00b"}, "unstorable_text"),
    ("escaped lone surrogate", {"note": "a\ud800b"}, "unstorable_text"),
    ("not NFC", {"note": "é"}, "unstorable_text"),
    ("250 levels deep", nested(250), "value_too_deep"),
    ("300 levels deep", nested(300), "value_too_deep")])
def test_an_unstorable_decoded_value_settles_as_a_rejected_attempt_and_the_request_stays_openable_and_retryable(
        make_client, owner_a, name: str, value: Any, reason: str) -> None:
    from edge_os_api.research.interpretation_attempts import Usage
    hostile = reply(case("concrete-thesis")["provider"]["model_response"], usage=Usage(1500, 400, 1900, "PROVIDER_REPORTED"),
                    text=thesis_with_sizing(value))
    client = make_client(CaseRunner(hostile, turn_result(case("concrete-thesis")["provider"])))

    created = create(client, owner_a, "concrete-thesis")

    assert created.status_code == 201, (name, created.text)
    bundle = created.json()
    [attempt] = bundle["attempts"]
    assert attempt["parse_result"] == f"REJECTED:{reason}", name
    assert attempt["usage"]["input_tokens"] == 1500
    assert bundle["head"]["retry"]["allowed"] is True
    opened = client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a)
    assert opened.status_code == 200, name
    retried = retry(client, owner_a, bundle, attempt["attempt_id"])
    assert retried.status_code == 201 and retried.json()["head"]["outcome"] == "NEEDS_CLARIFICATION"


def test_a_hostile_decoded_value_in_a_reply_settles_as_rejected_and_keeps_the_saved_meaning(make_client, owner_a) -> None:
    first = case("rough-hunch")["provider"]["model_response"]
    hostile = {**first, "questions": [], "field_evidence": [{
        "field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": "up more than 1%",
        "value": {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                       {"op": "constant", "value": "0.01", "unit": "DIMENSIONLESS"}], "note": "a\x00b"}}]}
    client = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"]), reply(hostile)))
    bundle = create(client, owner_a, "rough-hunch").json()

    response = answer(client, owner_a, bundle, "choose-entry", answer_text="up more than 1%")

    assert response.status_code == 200, response.text
    after = response.json()
    assert after["attempts"][-1]["parse_result"] == "REJECTED:unstorable_text"
    assert after["head"]["reply"]["state"] == "REJECTED" and len(after["interpretations"]) == 1


def test_a_truncated_answer_with_no_text_is_saved_as_a_rejected_truncation_with_a_retry(make_client, owner_a) -> None:
    from edge_os_api.research.hermes_interpreter import HermesTurnResult
    from edge_os_api.research.interpretation_attempts import Usage
    from hermes_cases import OBSERVED_OK
    empty = HermesTurnResult("TRUNCATED", None, Usage(1423, 4096, 5519, "PROVIDER_REPORTED"), 1, OBSERVED_OK, None)
    client = make_client(CaseRunner(empty, turn_result(case("concrete-thesis")["provider"])))

    bundle = create(client, owner_a, "concrete-thesis").json()

    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["completion"], attempt["parse_result"]) == ("TRUNCATED", "TRUNCATED", "REJECTED:truncated")
    assert attempt["usage"]["output_tokens"] == 4096
    assert bundle["head"]["retry"]["allowed"] is True


@pytest.mark.parametrize("usage", ["negative", "huge"])
def test_usage_the_database_cannot_hold_is_saved_as_unknown_and_the_answer_is_still_used(make_client, owner_a, usage: str) -> None:
    from edge_os_api.research.interpretation_attempts import Usage
    bad = Usage(-1, 5, 4, "PROVIDER_REPORTED") if usage == "negative" else Usage(2 ** 70, 5, 2 ** 70, "PROVIDER_REPORTED")
    client = make_client(CaseRunner(reply(case("concrete-thesis")["provider"]["model_response"], usage=bad)))

    created = create(client, owner_a, "concrete-thesis")

    assert created.status_code == 201, created.text
    [attempt] = created.json()["attempts"]
    assert attempt["parse_result"] == "ACCEPTED"
    assert attempt["usage"] == {"source": "UNKNOWN", "input_tokens": None, "output_tokens": None, "total_tokens": None}


# --- Answers too large to save, the application's own question ids, and a settle step that always settles ------------------

@pytest.mark.parametrize("size", [66_000, 80_000, 300_000])
def test_an_accepted_looking_answer_too_large_to_save_settles_as_rejected_and_stays_openable_and_retryable(
        make_client, owner_a, size: int) -> None:
    from edge_os_api.research.interpretation_attempts import Usage
    hostile = reply(case("concrete-thesis")["provider"]["model_response"], usage=Usage(1500, 400, 1900, "PROVIDER_REPORTED"),
                    text=thesis_with_sizing({"note": "a" * size}))
    client = make_client(CaseRunner(hostile, turn_result(case("concrete-thesis")["provider"])))

    created = create(client, owner_a, "concrete-thesis")

    assert created.status_code == 201, created.text
    bundle = created.json()
    [attempt] = bundle["attempts"]
    assert attempt["parse_result"] == "REJECTED:response_too_large"
    assert attempt["usage"]["input_tokens"] == 1500 and bundle["head"]["retry"]["allowed"] is True
    assert client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a).status_code == 200
    assert retry(client, owner_a, bundle, attempt["attempt_id"]).status_code == 201


def test_a_model_question_id_that_collides_with_the_applications_text_question_is_rejected(make_client, owner_a) -> None:
    first = json.loads(json.dumps(case("rough-hunch")["provider"]["model_response"]))
    first["questions"] = [dict(first["questions"][0], question_id="ask-exit")]
    first["field_evidence"] = [i for i in first["field_evidence"] if i["field_name"] != "exit"] + [
        {"field_name": "exit", "state": "MISSING"}]
    client = make_client(CaseRunner(reply(first)))

    bundle = create(client, owner_a, "rough-hunch").json()

    assert bundle["attempts"][0]["parse_result"] == "REJECTED:reserved_question_id"
    assert bundle["interpretations"] == [] and bundle["head"]["retry"]["allowed"] is True


def test_a_too_large_reply_result_settles_as_rejected_and_keeps_the_saved_meaning(make_client, owner_a) -> None:
    first = case("rough-hunch")["provider"]["model_response"]
    hostile = {**first, "questions": [], "field_evidence": [{
        "field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": "up more than 1%",
        "value": {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                       {"op": "constant", "value": "0.01", "unit": "DIMENSIONLESS"}],
                  "note": "a" * 70_000}}]}
    client = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"]), reply(hostile)))
    bundle = create(client, owner_a, "rough-hunch").json()

    response = answer(client, owner_a, bundle, "choose-entry", answer_text="up more than 1%")

    assert response.status_code == 200, response.text
    after = response.json()
    assert after["attempts"][-1]["parse_result"] == "REJECTED:response_too_large"
    assert after["head"]["reply"]["state"] == "REJECTED" and len(after["interpretations"]) == 1


@pytest.mark.parametrize("label, changes", [
    ("request count beyond a 32-bit integer", {"request_count": 2 ** 31}),
    ("runtime report with a NUL", {"observed": {"note": "a\x00b"}}),
    ("runtime report with a lone surrogate", {"observed": {"note": "a\ud800b"}}),
    ("runtime report with NaN", {"observed": {"value": float("nan")}}),
    ("error class that is not text", {"error_class": 5}),
])
def test_a_defective_runner_result_still_settles_the_attempt_and_keeps_the_answer(make_client, owner_a, label: str,
                                                                                  changes: dict) -> None:
    from edge_os_api.research.hermes_interpreter import HermesTurnResult
    base = turn_result(case("concrete-thesis")["provider"])
    defective = HermesTurnResult(**{**base.__dict__, **changes})
    if "observed" in changes:  # keep the policy fields so only the saved value is defective
        defective = HermesTurnResult(**{**base.__dict__, "observed": {**base.observed, **changes["observed"]}})
    client = make_client(CaseRunner(defective))

    created = create(client, owner_a, "concrete-thesis")

    assert created.status_code == 201, (label, created.text)
    [attempt] = created.json()["attempts"]
    assert attempt["status"] == "COMPLETED", label
    if "request count" in label:  # more than one provider request breaks the runtime policy: rejected, but it settles
        assert attempt["parse_result"] == "REJECTED:runtime_policy_violation" and attempt["request_count"] is None
    else:
        assert attempt["parse_result"] == "ACCEPTED" and attempt["revision_id"] is not None, label


def test_a_status_that_is_not_text_and_a_usage_that_is_not_usage_settle_as_unknown(make_client, owner_a) -> None:
    from edge_os_api.research.hermes_interpreter import HermesTurnResult
    base = turn_result(case("concrete-thesis")["provider"])
    for field, value in (("status", None), ("usage", None), ("text", 5), ("text", b"{}")):
        client = make_client(CaseRunner(HermesTurnResult(**{**base.__dict__, field: value})))
        created = create(client, owner_a, "concrete-thesis")
        assert created.status_code == 201, (field, value, created.text)
        [attempt] = created.json()["attempts"]
        assert attempt["status"] in {"COMPLETED", "UNKNOWN"}, (field, value)


def thesis_variants() -> list[tuple[str, str]]:
    """About 120 plantings of a hostile value at a position of the authored thesis answer, chosen the same way each run."""
    good = case("concrete-thesis")["provider"]["model_response"]
    from test_interpretation_response import HOSTILE_VALUES, mutations, plant
    chosen = []
    positions = mutations(good)
    for index, (path, hostile) in enumerate(positions):
        if index % 9 == 0:
            chosen.append((f"{'/'.join(map(str, path))} <- {hostile!r:.40}", json.dumps(plant(good, path, hostile))))
    return chosen[:140]


def test_every_hostile_planting_ends_published_or_rejected_and_never_stuck(make_client, owner_a) -> None:
    """The independent oracle: an answer that settles ACCEPTED must be published for real, and a rejected one retryable."""
    from edge_os_api.research.interpretation_attempts import Usage
    stuck, accepted, rejected = [], 0, 0
    variants = thesis_variants()
    assert len(variants) > 100
    base = case("concrete-thesis")["provider"]["model_response"]
    client = make_client(CaseRunner(*[reply(base, usage=Usage(900, 120, 1020, "PROVIDER_REPORTED"), text=text)
                                      for _, text in variants]))  # one application, so connections are not exhausted
    for label, _ in variants:
        created = create(client, owner_a, "concrete-thesis")
        if created.status_code != 201:
            stuck.append((label, created.status_code))
            continue
        bundle = created.json()
        [attempt] = bundle["attempts"]
        opened = client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a)
        if opened.status_code != 200 or attempt["status"] != "COMPLETED":
            stuck.append((label, opened.status_code, attempt["status"]))
        elif attempt["parse_result"] == "ACCEPTED":
            accepted += 1
            if attempt["revision_id"] is None or bundle["head"]["outcome"] is None:
                stuck.append((label, "accepted but not published"))
        else:
            rejected += 1
            if not bundle["head"]["retry"]["allowed"]:
                stuck.append((label, "rejected but not retryable"))
    assert stuck == [], stuck[:5]
    assert accepted > 0 and rejected > 0


# --- Round 11: the next user step must also fit the record limit -----------------------------------------------------------

@pytest.mark.parametrize("size", [21_000, 45_000, 60_500])
def test_a_response_above_the_size_bound_is_rejected_before_any_follow_on_record_can_overflow(
        make_client, owner_a, size: int) -> None:
    from edge_os_api.research.interpretation_attempts import Usage
    hostile = reply(case("concrete-thesis")["provider"]["model_response"], usage=Usage(1500, 400, 1900, "PROVIDER_REPORTED"),
                    text=thesis_with_sizing({"note": "a" * size}))
    client = make_client(CaseRunner(hostile, turn_result(case("concrete-thesis")["provider"])))

    bundle = create(client, owner_a, "concrete-thesis").json()

    [attempt] = bundle["attempts"]
    assert attempt["parse_result"] == "REJECTED:response_too_large"
    assert bundle["head"]["retry"]["allowed"] is True


def test_the_largest_accepted_response_with_the_longest_request_still_adopts_without_a_server_error(
        make_client, owner_a) -> None:
    from edge_os_api.research.hermes_interpreter import MAX_RESPONSE_BYTES
    from edge_os_api.research.interpretation_attempts import Usage
    base = thesis_with_sizing({"note": ""})
    room = MAX_RESPONSE_BYTES - len(base.encode("utf-8")) - 64
    big = reply(case("concrete-thesis")["provider"]["model_response"], usage=Usage(1500, 400, 1900, "PROVIDER_REPORTED"),
                text=thesis_with_sizing({"note": "a" * room}))
    client = make_client(CaseRunner(big))
    body = intake_body("concrete-thesis")
    body["original_request"] += " " + "価" * (10_000 - len(body["original_request"]) - 1)  # the longest legal request

    created = client.post("/v1/research/requests", json=body, headers=owner_a)

    assert created.status_code == 201, created.text
    bundle = created.json()
    assert bundle["attempts"][0]["parse_result"] == "ACCEPTED"
    adopted = answer(client, owner_a, bundle, "adopt-suggested-settings", choice_id="adopt")
    assert adopted.status_code < 500, adopted.text


def test_a_record_the_store_refuses_as_too_large_is_a_plain_refusal_and_leaves_the_saved_reading_unchanged(
        make_client, owner_a, monkeypatch) -> None:
    from edge_os_api.records import contract_adapter as record_contract
    from edge_os_api.research import service
    client = make_client(CaseRunner(turn_result(case("concrete-thesis")["provider"])))
    bundle = create(client, owner_a, "concrete-thesis").json()

    def refuse(*args: Any, **kwargs: Any):
        raise record_contract.Invalid("record exceeds the byte limit")
    monkeypatch.setattr(service, "put_record", refuse)

    response = answer(client, owner_a, bundle, "adopt-suggested-settings", choice_id="adopt")

    assert response.status_code == 422, response.text
    assert "record_too_large" in response.text
    monkeypatch.undo()
    after = client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a).json()
    assert len(after["interpretations"]) == 1


def and_tree(rule: Any, copies: int) -> Any:
    if copies <= 1:
        return rule
    half = copies // 2
    return {"op": "and", "args": [and_tree(rule, half), and_tree(rule, copies - half)]}


@pytest.mark.parametrize("pad,length,copies,expected", [
    ("\u0001", 10_000, 12, "REJECTED:unpublishable_response"),  # a 60 KB request leaves no room for the draft that adoption writes
    ("\u0001", 6_000, 12, "ACCEPTED"),
    ("a", 10_000, 12, "ACCEPTED"),
    ("\U0001F600", 10_000, 12, "ACCEPTED")])
def test_the_room_for_an_answer_depends_on_what_the_request_costs_in_the_record_and_an_accepted_answer_adopts(
        make_client, owner_a, pad: str, length: int, copies: int, expected: str) -> None:
    """A control character costs six bytes in the canonical record, so the character count says too little."""
    from edge_os_api.research.interpretation_attempts import Usage
    good = json.loads(thesis_with_sizing({"note": ""}))
    entry = next(i for i in good["field_evidence"] if i["field_name"] == "entry")
    entry["value"] = and_tree(entry["value"], copies)
    client = make_client(CaseRunner(reply(case("concrete-thesis")["provider"]["model_response"],
                                          usage=Usage(1500, 400, 1900, "PROVIDER_REPORTED"), text=json.dumps(good)),
                                    turn_result(case("concrete-thesis")["provider"])))
    body = intake_body("concrete-thesis")
    body["original_request"] += " " + pad * (length - len(body["original_request"]) - 1)

    created = client.post("/v1/research/requests", json=body, headers=owner_a)

    assert created.status_code == 201, created.text
    bundle = created.json()
    assert bundle["attempts"][0]["parse_result"] == expected
    if expected == "ACCEPTED":
        adopted = answer(client, owner_a, bundle, "adopt-suggested-settings", choice_id="adopt")
        assert adopted.status_code == 201, adopted.text  # the compiler may still judge the odd rule; the save must not fail


def test_a_contract_refusal_that_is_not_about_size_is_not_called_a_size_problem(make_client, owner_a, monkeypatch) -> None:
    from edge_os_api.records import contract_adapter as record_contract
    from edge_os_api.research import service
    client = make_client(CaseRunner(turn_result(case("concrete-thesis")["provider"])))
    bundle = create(client, owner_a, "concrete-thesis").json()

    def refuse(*args: Any, **kwargs: Any):
        raise record_contract.Invalid("strings must be Unicode NFC")
    monkeypatch.setattr(service, "put_record", refuse)

    response = answer(client, owner_a, bundle, "adopt-suggested-settings", choice_id="adopt")

    assert "record_too_large" not in response.text
