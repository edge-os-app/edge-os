"""Crashes, restarts, two processes and uncertain work for the Hermes Research path, on a real database.

A second application over the same database stands in for a second API process: it has its own engine and its own
connections, so it sees only what PostgreSQL shows it. The Hermes process boundary is scripted.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import run_threads
from hermes_cases import CaseRunner, case, intake_body, turn_result
from test_hermes_research_flow import answer, create, make_client, retry, rows  # noqa: F401 - fixtures and helpers

from edge_os_api.research.interpretation_attempts import LateResult, Usage
from edge_os_api.research import interpretation_workflow, service


def bundle_of(client: TestClient, headers: dict[str, str], intake_id: str) -> dict[str, Any]:
    response = client.get(f"/v1/research/requests/{intake_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def counts(client: TestClient, intake_id: str) -> dict[str, int]:
    found = rows(client, "select record_type, count(*) from records where intake_record_id = :i or record_id = :i group by 1", i=intake_id)
    return {kind: total for kind, total in found}


def first_request_id(client: TestClient, headers: dict[str, str]) -> str:
    return client.get("/v1/research/requests", headers=headers).json()["requests"][0]["intake_record_id"]


# --- A crash after the result was saved ---------------------------------------------------------------------------

def test_a_result_saved_before_a_crash_is_published_after_restart_without_a_new_call(
        make_client, owner_a, monkeypatch: pytest.MonkeyPatch) -> None:
    first = make_client(CaseRunner(turn_result(case("concrete-thesis")["provider"])))

    def crash(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("process died after the result was saved")
    with monkeypatch.context() as crashing:
        crashing.setattr(interpretation_workflow.HermesResearch, "_publish_interpretation", crash)
        assert create(first, owner_a, "concrete-thesis").status_code == 500
    intake = first_request_id(first, owner_a)
    saved = bundle_of(first, owner_a, intake)
    assert saved["interpretations"] == [] and saved["attempts"][0]["revision_id"] is None
    assert (saved["attempts"][0]["status"], saved["attempts"][0]["parse_result"]) == ("COMPLETED", "ACCEPTED")

    reopened_runner = CaseRunner()
    reopened = make_client(reopened_runner)  # startup recovery runs here

    after = bundle_of(reopened, owner_a, intake)
    assert reopened_runner.turns == []
    assert after["head"]["outcome"] == "NEEDS_CLARIFICATION" and len(after["interpretations"]) == 1
    assert after["attempts"][0]["revision_id"] == after["head"]["interpretation_revision_id"]
    assert after["attempts"][0]["attempt_id"] == saved["attempts"][0]["attempt_id"]
    assert counts(reopened, intake)["PromptInterpretation"] == 1


def test_repeated_recovery_adds_no_second_revision(make_client, owner_a, monkeypatch: pytest.MonkeyPatch) -> None:
    first = make_client(CaseRunner(turn_result(case("concrete-thesis")["provider"])))
    with monkeypatch.context() as crashing:
        crashing.setattr(interpretation_workflow.HermesResearch, "_publish_interpretation",
                         lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("crash")))
        create(first, owner_a, "concrete-thesis")
    intake = first_request_id(first, owner_a)

    third = make_client(CaseRunner())
    for _ in range(3):  # startup recovery already published it; further passes must change nothing
        third.app.state.hermes.recover_all()

    assert counts(third, intake)["PromptInterpretation"] == 1 and counts(third, intake)["Outcome"] == 1
    assert len(bundle_of(third, owner_a, intake)["attempts"]) == 1


def test_a_failure_between_settlement_and_linking_leaves_nothing_half_published(
        make_client, owner_a, monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(CaseRunner(turn_result(case("concrete-thesis")["provider"])))
    with monkeypatch.context() as failing:
        failing.setattr(service, "verify_lineage", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("late failure")))
        assert create(client, owner_a, "concrete-thesis").status_code == 500
    intake = first_request_id(client, owner_a)

    assert counts(client, intake) == {"IntakeRequest": 1}  # no revision, outcome or link was committed
    assert rows(client, "select count(*) from interpretation_attempt_links where intake_record_id = :i", i=intake)[0][0] == 0

    with client.app.state.session_factory() as session:
        client.app.state.hermes.reconcile(session, _principal(client, owner_a), uuid.UUID(intake))
    assert counts(client, intake)["PromptInterpretation"] == 1


def _principal(client: TestClient, headers: dict[str, str]):
    from edge_os_api.core.authentication import Principal
    return Principal(uuid.UUID(client.get("/v1/me", headers=headers).json()["user_id"]), "test")


# --- A worker that is still running, and one that died ----------------------------------------------------------------

class HoldingRunner:
    """Blocks inside the provider call until released, so a request stays active while another process looks at it."""

    def __init__(self, result) -> None:
        self.entered, self.release, self.result, self.turns = threading.Event(), threading.Event(), result, []

    def run_turn(self, turn):
        self.turns.append(turn)
        self.entered.set()
        assert self.release.wait(30)
        return self.result


def test_a_second_process_does_not_interrupt_or_duplicate_an_attempt_that_a_live_worker_holds(make_client, owner_a) -> None:
    holder = HoldingRunner(turn_result(case("concrete-thesis")["provider"]))
    first = make_client(holder)
    outcome: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: outcome.update(response=create(first, owner_a, "concrete-thesis")))
    worker.start()
    try:
        assert holder.entered.wait(30)
        second_runner = CaseRunner(turn_result(case("concrete-thesis")["provider"]))
        second = make_client(second_runner)  # its startup recovery looks at the held attempt
        intake = first_request_id(second, owner_a)

        seen = bundle_of(second, owner_a, intake)
        assert [(a["status"], a["completion"]) for a in seen["attempts"]] == [("STARTED", "UNKNOWN")]
        assert seen["head"]["retry"] == {"allowed": False, "retry_of": None, "reason": "attempt_in_flight"}
        refused = retry(second, owner_a, seen, None)
        assert refused.status_code == 409 and refused.json()["findings"][0]["code"] == "attempt_in_flight"
        duplicate = second.post(f"/v1/research/requests/{intake}/clarifications", headers=owner_a, json={
            "previous_revision_id": "00000000-0000-4000-8000-000000000000", "question_id": "ask-entry", "answer_text": "x"})
        assert duplicate.status_code in {409, 422}
        assert second_runner.turns == []
        assert bundle_of(second, owner_a, intake)["attempts"][0]["status"] == "STARTED"  # nobody closed it
    finally:
        holder.release.set()
        worker.join(30)

    assert outcome["response"].status_code == 201
    done = bundle_of(first, owner_a, intake)
    assert [a["status"] for a in done["attempts"]] == ["COMPLETED"] and done["head"]["outcome"] == "NEEDS_CLARIFICATION"


def test_an_attempt_whose_worker_died_is_closed_as_unknown_and_is_never_replayed(make_client, owner_a) -> None:
    client = make_client(CaseRunner())
    owner = _principal(client, owner_a)
    from edge_os_api.research import service as research_service
    with client.app.state.session_factory() as session:
        intake = research_service.save_intake(session, owner, intake_body("concrete-thesis"))
        session.commit()
        intake_id, content = intake.record_id, intake.content
    hermes = client.app.state.hermes
    from edge_os_api.research.hermes_interpreter import SYSTEM_PROMPT
    died = hermes.ledger.begin(str(owner.user_id), str(intake_id), _identity(hermes, content))  # recorded; no claim exists

    restarted_runner = CaseRunner(turn_result(case("concrete-thesis")["provider"]))
    restarted = make_client(restarted_runner)  # startup recovery proves nobody holds the claim and closes the attempt

    after = bundle_of(restarted, owner_a, str(intake_id))
    [attempt] = after["attempts"]
    assert (attempt["attempt_id"], attempt["status"], attempt["completion"]) == (died.attempt_id, "INTERRUPTED", "UNKNOWN")
    assert attempt["usage"]["source"] == "UNKNOWN" and attempt["latency_ms"] is None
    assert after["outcomes"][-1]["record"]["content"]["findings"][0]["code"] == "interpreter_outcome_unknown"
    assert restarted_runner.turns == []
    refused = retry(restarted, owner_a, after, None)
    assert refused.status_code == 409 and refused.json()["findings"][0]["code"] == "outcome_uncertain"
    assert restarted_runner.turns == []


def _identity(hermes, intake_content):
    from edge_os_api.research.hermes_interpreter import (PROMPT_VERSION, RESPONSE_SHAPE, SYSTEM_PROMPT, _task_base,
                                                        _task_json)
    from edge_os_api.records import contract_adapter as record_contract
    from edge_os_api.research.interpretation_attempts import AttemptIdentity
    sha = lambda value: hashlib.sha256(value.encode()).hexdigest()  # noqa: E731
    task = _task_json(_task_base("interpret", intake_content))
    return AttemptIdentity("INTERPRET", PROMPT_VERSION, sha(SYSTEM_PROMPT), sha(task), task, sha(RESPONSE_SHAPE),
                           record_contract.manifest_sha256(), {"model": "m"}, "LOCAL_FAKE_PROVIDER")


# --- Late results -------------------------------------------------------------------------------------------------------

def test_a_late_result_is_shown_as_non_authoritative_and_creates_no_revision_or_retry(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("provider-hang")["provider"]), turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)
    hung = create(client, owner_a, "concrete-thesis").json()
    attempt = hung["attempts"][0]
    text = json.dumps(case("concrete-thesis")["provider"]["model_response"])

    client.app.state.hermes.ledger.observe_late_result(LateResult(
        "33333333-3333-4333-8333-333333333333", attempt["attempt_id"], hung["outcomes"][0]["record"]["owner_id"],
        dt.datetime.now(dt.timezone.utc), "COMPLETED", hashlib.sha256(text.encode()).hexdigest(), text,
        Usage(1423, 611, 2034, "PROVIDER_REPORTED"), 1, None))

    after = bundle_of(client, owner_a, hung["intake"]["record_id"])
    assert after["late_results"] == [{
        "observation_id": "33333333-3333-4333-8333-333333333333", "attempt_id": attempt["attempt_id"],
        "observed_at": after["late_results"][0]["observed_at"], "status": "COMPLETED",
        "response_sha256": hashlib.sha256(text.encode()).hexdigest(), "authoritative": False,
        "usage": {"source": "PROVIDER_REPORTED", "input_tokens": 1423, "output_tokens": 611, "total_tokens": 2034}}]
    assert after["attempts"] == hung["attempts"] and after["interpretations"] == []
    assert after["head"]["retry"]["allowed"] is False and len(runner.turns) == 1
    assert text not in json.dumps(after)


# --- Restart, reopen and concurrency ------------------------------------------------------------------------------------

def test_a_restarted_application_shows_exactly_the_saved_state(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("provider-503")["provider"]), turn_result(case("rough-hunch")["provider"]))
    first = make_client(runner)
    failed = create(first, owner_a, "rough-hunch").json()
    retried = retry(first, owner_a, failed, failed["attempts"][0]["attempt_id"]).json()
    chosen = answer(first, owner_a, retried, "choose-entry", choice_id="g3-1pct").json()

    reopened_runner = CaseRunner()
    reopened = make_client(reopened_runner)

    assert bundle_of(reopened, owner_a, chosen["intake"]["record_id"]) == chosen
    assert reopened_runner.turns == []


def test_two_simultaneous_retries_start_one_attempt(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("provider-503")["provider"]), turn_result(case("concrete-thesis")["provider"]),
                        turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)
    failed = create(client, owner_a, "concrete-thesis").json()
    attempt_id = failed["attempts"][0]["attempt_id"]

    results = run_threads(2, lambda _i: retry(client, owner_a, failed, attempt_id))

    assert sorted(r.status_code for r in results) == [201, 409]
    assert len(runner.turns) == 2
    final = bundle_of(client, owner_a, failed["intake"]["record_id"])
    assert [a["sequence"] for a in final["attempts"]] == [1, 2]


def test_two_simultaneous_choices_for_one_revision_save_one_revision(make_client, owner_a) -> None:
    client = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"])))
    bundle = create(client, owner_a, "rough-hunch").json()

    results = run_threads(2, lambda i: answer(client, owner_a, bundle, "choose-entry",
                                              choice_id=["g3-1pct", "g3-2pct"][i]))

    assert sorted(r.status_code for r in results) == [201, 409]
    assert len(bundle_of(client, owner_a, bundle["intake"]["record_id"])["interpretations"]) == 2


# --- Guards that hold when two callers race ---------------------------------------------------------------------------

def test_a_probe_that_cannot_reach_the_database_does_not_prove_abandonment() -> None:
    from sqlalchemy import create_engine
    from edge_os_api.research.attempt_store import AdvisoryLockGuard
    unreachable = create_engine("postgresql+psycopg://nobody:none@127.0.0.1:1/none", connect_args={"connect_timeout": 1})
    assert AdvisoryLockGuard(unreachable).is_abandoned(str(uuid.uuid4())) is False


def test_publishing_the_same_accepted_attempt_twice_saves_one_revision(make_client, owner_a) -> None:
    client = make_client(CaseRunner(turn_result(case("concrete-thesis")["provider"])))
    bundle = create(client, owner_a, "concrete-thesis").json()
    hermes, principal = client.app.state.hermes, _principal(client, owner_a)
    intake = uuid.UUID(bundle["intake"]["record_id"])
    view = hermes.ledger.history(str(principal.user_id), str(intake))[0]
    parsed = hermes.interpreter.reparse(view, bundle["intake"]["content"])

    with client.app.state.session_factory() as session:
        hermes._publish_interpretation(session, principal, intake, view.start.attempt_id, parsed)

    assert counts(client, str(intake))["PromptInterpretation"] == 1 and counts(client, str(intake))["Outcome"] == 1


def test_a_choice_is_refused_while_a_reply_is_being_read(make_client, owner_a) -> None:
    first = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"])))
    bundle = create(first, owner_a, "rough-hunch").json()
    holder = HoldingRunner(reply_for(case("rough-hunch")["provider"]["model_response"]))
    second = make_client(holder)
    worker = threading.Thread(target=lambda: answer(second, owner_a, bundle, "choose-entry", answer_text="up a lot"))
    worker.start()
    try:
        assert holder.entered.wait(30)
        refused = answer(first, owner_a, bundle, "choose-entry", choice_id="g3-1pct")
        assert refused.status_code == 409 and refused.json()["findings"][0]["code"] == "attempt_in_flight"
        assert len(bundle_of(first, owner_a, bundle["intake"]["record_id"])["interpretations"]) == 1
    finally:
        holder.release.set()
        worker.join(30)


def reply_for(model_response: dict[str, Any]):
    """A follow-up that fills the entry rule from the words 'up more than 2% over the last 15 minutes'."""
    from hermes_cases import reply
    from test_hermes_research_flow import TWO_PERCENT
    return reply({**model_response, "questions": [], "field_evidence": [{
        "field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": WORDS, "value": TWO_PERCENT}]})


WORDS = "up more than 2% over the last 15 minutes"


def _accepted_follow_up(client: TestClient, owner_headers: dict[str, str], bundle: dict[str, Any], previous: str):
    """Record an accepted follow-up attempt that answers `previous`, without publishing it."""
    hermes, principal = client.app.state.hermes, _principal(client, owner_headers)
    hermes.interpreter._runner.script.append(reply_for(case("rough-hunch")["provider"]["model_response"]))  # type: ignore[attr-defined]
    from edge_os_api.research.interpretation_response import ClarificationAnswer
    intake = bundle["intake"]["content"]
    evidence = bundle["interpretations"][0]["content"]["field_evidence"]
    answer_ref = f"reply:{uuid.uuid4()}"
    result = hermes.interpreter.follow_up(str(principal.user_id), bundle["intake"]["record_id"], intake, evidence,
                                          "What counts as a rise?", ClarificationAnswer(answer_ref, WORDS),
                                          previous_revision_id=previous)
    return hermes, principal, result, ClarificationAnswer(answer_ref, WORDS)


def test_a_reply_is_not_published_when_the_saved_meaning_moved_on(make_client, owner_a) -> None:
    runner = CaseRunner(turn_result(case("rough-hunch")["provider"]))
    client = make_client(runner)
    bundle = create(client, owner_a, "rough-hunch").json()
    first_revision = bundle["head"]["interpretation_revision_id"]
    moved = answer(client, owner_a, bundle, "choose-entry", choice_id="g3-1pct").json()
    hermes, principal, result, words = _accepted_follow_up(client, owner_a, bundle, first_revision)

    with client.app.state.session_factory() as session:
        from edge_os_api.core.errors import AppError
        with pytest.raises(AppError) as caught:
            hermes._publish_reply(session, principal, uuid.UUID(bundle["intake"]["record_id"]), result.attempt_id,
                                  result.parsed, words, "choose-entry", "What counts as a rise?")

    assert caught.value.status == 409
    assert len(bundle_of(client, owner_a, bundle["intake"]["record_id"])["interpretations"]) == len(moved["interpretations"])


def test_publishing_a_reply_twice_saves_one_revision_and_the_second_call_changes_nothing(make_client, owner_a) -> None:
    client = make_client(CaseRunner(turn_result(case("rough-hunch")["provider"])))
    bundle = create(client, owner_a, "rough-hunch").json()
    hermes, principal, result, words = _accepted_follow_up(client, owner_a, bundle, bundle["head"]["interpretation_revision_id"])
    intake = uuid.UUID(bundle["intake"]["record_id"])
    args = (principal, intake, result.attempt_id, result.parsed, words, "choose-entry", "What counts as a rise?")

    with client.app.state.session_factory() as session:
        assert hermes._publish_reply(session, *args) is True
    with client.app.state.session_factory() as session:
        assert hermes._publish_reply(session, *args) is False

    assert counts(client, str(intake))["PromptInterpretation"] == 2


# --- A failure outcome that was not saved in the same step is repaired ---------------------------------------------------

@pytest.mark.parametrize("name, code, retry", [
    ("provider-hang", "interpreter_outcome_unknown", "RECONCILE"),
    ("provider-503", "interpreter_unavailable", "SAFE_SAME_KEY"),
    ("multiple-objects", "malformed_model_output", "SAFE_SAME_KEY"),
    ("truncated-cut-off", "malformed_model_output", "SAFE_SAME_KEY")])
def test_a_settled_failure_whose_outcome_was_not_saved_gets_its_outcome_after_restart(
        make_client, owner_a, monkeypatch: pytest.MonkeyPatch, name: str, code: str, retry: str) -> None:
    first = make_client(CaseRunner(turn_result(case(name)["provider"])))
    with monkeypatch.context() as crashing:
        crashing.setattr(interpretation_workflow.HermesResearch, "_record_failure",
                         lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("process died before the outcome")))
        assert create(first, owner_a, "concrete-thesis").status_code == 500
    intake = first_request_id(first, owner_a)
    assert bundle_of(first, owner_a, intake)["outcomes"] == []

    runner = CaseRunner()
    second = make_client(runner)  # startup recovery runs here

    after = bundle_of(second, owner_a, intake)
    outcome = after["outcomes"][-1]["record"]["content"]
    assert (outcome["outcome"], outcome["findings"][0]["code"], outcome["retry"]) == ("INVALID_INPUT", code, retry)
    assert runner.turns == [] and len(after["attempts"]) == 1
    for _ in range(2):  # repeating the repair adds nothing
        second.app.state.hermes.recover_all()
    assert len(bundle_of(second, owner_a, intake)["outcomes"]) == 1


def test_an_attempt_closed_as_interrupted_whose_outcome_was_not_saved_gets_its_outcome(
        make_client, owner_a, monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(CaseRunner())
    owner = _principal(client, owner_a)
    from edge_os_api.research import service as research_service
    with client.app.state.session_factory() as session:
        intake = research_service.save_intake(session, owner, intake_body("concrete-thesis"))
        session.commit()
        intake_id, content = intake.record_id, intake.content
    hermes = client.app.state.hermes
    hermes.ledger.begin(str(owner.user_id), str(intake_id), _identity(hermes, content))
    with monkeypatch.context() as crashing:
        crashing.setattr(interpretation_workflow.HermesResearch, "_record_failure",
                         lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("died after closing")))
        with client.app.state.session_factory() as session:
            with pytest.raises(RuntimeError):
                hermes.reconcile(session, owner, intake_id)
    assert bundle_of(client, owner_a, str(intake_id))["attempts"][0]["status"] == "INTERRUPTED"
    assert bundle_of(client, owner_a, str(intake_id))["outcomes"] == []

    restarted = make_client(CaseRunner())

    after = bundle_of(restarted, owner_a, str(intake_id))
    assert after["outcomes"][-1]["record"]["content"]["findings"][0]["code"] == "interpreter_outcome_unknown"
