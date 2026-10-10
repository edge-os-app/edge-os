"""Multi-step flows through actual pinned Hermes against a LOCAL FAKE provider.

These are scenario tests over behavior that the unit tests already cover. They show the pieces working together around
the real Hermes runtime. The fake provider returns authored text, so none of this shows how a real model behaves.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from edge_os_api.research.hermes_interpreter import Interpreted, OutputRejected, Unavailable, apply_choice_answer
from edge_os_api.research.interpretation_attempts import AttemptLedger
from edge_os_api.research.interpretation_response import ClarificationAnswer
from test_pinned_hermes import (
    CASES, INTAKE, OWNER, Session, adopt_all, provider_script, routed,
)

ENTRY = CASES["concrete-thesis"]["expect"]["entry_value"]
EXIT = CASES["concrete-thesis"]["expect"]["exit_value"]
ENTRY2 = {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3},
                               {"op": "constant", "value": "0.02", "unit": "DIMENSIONLESS"}]}
USAGE = {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}


def reply_script(delta: list[dict[str, Any]], usage: dict[str, int] | None = USAGE) -> dict[str, Any]:
    response = {"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "READY",
                "field_evidence": delta, "questions": []}
    return {"kind": "content", "content": json.dumps(response), "finish_reason": "stop", "usage": usage}


def first_turn(session: Session, case: str) -> Interpreted:
    result = session.interpreter.interpret(OWNER, INTAKE, CASES[case]["intake"])
    assert isinstance(result, Interpreted), result
    return result


def test_a_free_text_reply_to_a_hunch_is_read_by_a_second_attempt_and_compiles_after_adoption(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    reply = "Enter when the price is up more than 2% over the last 15 minutes, and exit when the 5-minute return is below zero."
    delta = [{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
              "source_passage": "price is up more than 2% over the last 15 minutes", "value": ENTRY2},
             {"field_name": "exit", "state": "KNOWN", "origin": "USER_STATED",
              "source_passage": "exit when the 5-minute return is below zero", "value": EXIT}]
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-hunch-reply",
                      [provider_script(CASES["rough-hunch"]["provider"]), reply_script(delta)])
    intake = CASES["rough-hunch"]["intake"]
    first = first_turn(session, "rough-hunch")

    second = session.interpreter.follow_up(OWNER, INTAKE, intake, first.parsed.field_evidence,
                                           "What should count as a rise for the entry rule?",
                                           ClarificationAnswer("answer:choose-entry", reply))

    assert isinstance(second, Interpreted)
    by_name = {i["field_name"]: i for i in second.parsed.field_evidence}
    assert (by_name["entry"]["origin"], by_name["entry"]["value"]) == ("USER_STATED", ENTRY2)
    assert by_name["entry"]["source_ref"] == "answer:choose-entry#c15-64"
    assert by_name["exit"]["source_ref"] == "answer:choose-entry#c70-113"
    assert [i for i in first.parsed.field_evidence if i["field_name"] not in {"entry", "exit"}] == [
        i for i in second.parsed.field_evidence if i["field_name"] not in {"entry", "exit"}]  # carried forward
    assert routed(intake, second.parsed).outcome == "NEEDS_CLARIFICATION"  # proposals still await adoption
    assert routed(intake, second.parsed, adopt_all(second.parsed)).outcome == "COMPILED"
    history = session.ledger.history(OWNER, INTAKE)
    assert [(v.start.sequence, v.start.identity.purpose, v.status) for v in history] == [
        (1, "INTERPRET", "COMPLETED"), (2, "FOLLOW_UP", "COMPLETED")]
    assert history[1].start.retry_of is None  # a follow-up is a new step, not a retry


def test_choosing_offered_options_then_adopting_compiles_the_hunch_without_a_second_model_call(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-hunch-choices",
                      [provider_script(CASES["rough-hunch"]["provider"])])
    intake = CASES["rough-hunch"]["intake"]
    first = first_turn(session, "rough-hunch")
    questions = list(first.parsed.questions)

    entry = apply_choice_answer(list(first.parsed.field_evidence), questions, "choose-entry", "g3-1pct")
    assert entry is not None
    exit_ = apply_choice_answer(entry[0], questions, "choose-exit", "ret-below-zero")
    assert exit_ is not None
    adopted = apply_choice_answer(exit_[0], questions, "adopt-suggested-settings", "adopt")
    assert adopted is not None

    by_name = {i["field_name"]: i for i in adopted[0]}
    assert (by_name["entry"]["origin"], by_name["entry"]["value"]) == ("USER_CONFIRMED", ENTRY)
    assert routed(intake, first.parsed, adopted[0]).outcome == "COMPILED"
    assert session.runner.turn_count == 1  # choices and adoption are deterministic; no provider call


def test_a_reply_that_silently_changes_stated_meaning_is_rejected_and_both_attempts_are_kept(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    overwrite = [{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                  "source_passage": "more than 2%", "value": ENTRY2}]
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-silent-overwrite",
                      [provider_script(CASES["concrete-thesis"]["provider"]), reply_script(overwrite)])
    intake = CASES["concrete-thesis"]["intake"]
    first = first_turn(session, "concrete-thesis")

    second = session.interpreter.follow_up(OWNER, INTAKE, intake, first.parsed.field_evidence, "Confirm?",
                                           ClarificationAnswer("answer:q", "Make it more than 2%"))

    assert isinstance(second, OutputRejected) and second.rejection.reason_code == "silent_overwrite"
    history = session.ledger.history(OWNER, INTAKE)
    assert [(v.status, v.settlement.parse_result) for v in history] == [  # type: ignore[union-attr]
        ("COMPLETED", "ACCEPTED"), ("COMPLETED", "REJECTED:silent_overwrite")]
    assert history[1].settlement.response_text == json.loads(json.dumps(reply_script(overwrite)))["content"]  # type: ignore[union-attr]


def test_a_contradicting_reply_becomes_a_conflict_that_the_router_sends_back_to_the_user(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    conflict = [{"field_name": "entry", "state": "CONFLICTING",
                 "conflicts": [{"value": ENTRY2, "source_passage": "more than 2%"}]}]
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-conflict",
                      [provider_script(CASES["concrete-thesis"]["provider"]), reply_script(conflict)])
    intake = CASES["concrete-thesis"]["intake"]
    first = first_turn(session, "concrete-thesis")

    second = session.interpreter.follow_up(OWNER, INTAKE, intake, first.parsed.field_evidence, "Confirm?",
                                           ClarificationAnswer("answer:q", "Make it more than 2%"))

    assert isinstance(second, Interpreted)
    entry = next(i for i in second.parsed.field_evidence if i["field_name"] == "entry")
    assert entry["conflicts"] == [{"value": ENTRY, "source_ref": "intake:original_request#c0-47"},
                                  {"value": ENTRY2, "source_ref": "answer:q#c8-20"}]
    outcome = routed(intake, second.parsed, adopt_all(second.parsed))
    assert outcome.outcome == "NEEDS_CLARIFICATION"
    assert [(f["code"], f["path"]) for f in outcome.findings] == [("conflicting_field", "/field_evidence/entry")]


def test_a_paraphrased_restatement_is_rejected_because_it_changes_nothing(pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    restate = [{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                "source_passage": "above one percent", "value": ENTRY}]
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-restatement",
                      [provider_script(CASES["concrete-thesis"]["provider"]), reply_script(restate)])
    first = first_turn(session, "concrete-thesis")

    second = session.interpreter.follow_up(OWNER, INTAKE, CASES["concrete-thesis"]["intake"], first.parsed.field_evidence,
                                           "Confirm?", ClarificationAnswer("answer:q", "I meant above one percent"))

    assert isinstance(second, OutputRejected) and second.rejection.reason_code == "reply_changed_nothing"
    assert session.ledger.history(OWNER, INTAKE)[1].settlement.parse_result == "REJECTED:reply_changed_nothing"  # type: ignore[union-attr]


def test_a_retry_after_a_provider_failure_is_a_separate_attempt_and_the_failure_stays(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-retry",
                      [provider_script(CASES["provider-503"]["provider"]),
                       provider_script(CASES["concrete-thesis"]["provider"])])
    intake = CASES["concrete-thesis"]["intake"]

    failed = session.interpreter.interpret(OWNER, INTAKE, intake)
    assert isinstance(failed, Unavailable) and failed.attempt_id is not None
    retried = session.interpreter.interpret(OWNER, INTAKE, intake, retry_of=failed.attempt_id)

    assert isinstance(retried, Interpreted)
    history = session.ledger.history(OWNER, INTAKE)
    assert [(v.start.sequence, v.start.retry_of, v.status) for v in history] == [
        (1, None, "PROVIDER_FAILED"), (2, failed.attempt_id, "COMPLETED")]
    assert history[0].settlement.usage.source == "UNKNOWN"  # type: ignore[union-attr]
    assert history[1].settlement.usage.total_tokens == 2034  # type: ignore[union-attr]
    stored = repr(session.store._settlements)
    assert "sk-LEAK-0001" not in stored and "owner-ZZ" not in stored and "overloaded" not in stored
    assert "sk-LEAK-0001" not in repr(failed)


def test_a_timed_out_attempt_stays_uncertain_and_a_retry_does_not_erase_it(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-timeout-retry",
                      [provider_script(CASES["provider-hang"]["provider"]),
                       provider_script(CASES["concrete-thesis"]["provider"])], timeout_seconds=12)
    intake = CASES["concrete-thesis"]["intake"]

    timed_out = session.interpreter.interpret(OWNER, INTAKE, intake)
    assert isinstance(timed_out, Unavailable) and timed_out.reason_code == "timed_out"
    session.runner.timeout_seconds = 90
    retried = session.interpreter.interpret(OWNER, INTAKE, intake, retry_of=timed_out.attempt_id)

    assert isinstance(retried, Interpreted)
    assert [(v.status, v.completion) for v in session.ledger.history(OWNER, INTAKE)] == [
        ("TIMED_OUT", "UNKNOWN"), ("COMPLETED", "COMPLETE")]
    lifecycle = json.loads(next((evidence_root / "flow-timeout-retry").glob("turn-01-*/container-lifecycle.json")).read_text())
    assert lifecycle["ownership_verified"] and lifecycle["container_absent"]


def test_a_restart_closes_the_unsettled_attempt_and_never_replays_it(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    from edge_os_api.research.hermes_interpreter import PROMPT_VERSION
    from edge_os_api.research.interpretation_attempts import AttemptIdentity
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-restart", [])
    task = "restart-task"
    session.ledger.begin(OWNER, INTAKE, AttemptIdentity(
        "INTERPRET", PROMPT_VERSION, "a" * 64, hashlib.sha256(task.encode()).hexdigest(), task, "c" * 64, "d" * 64,
        {"model": "x"}, "LOCAL_FAKE_PROVIDER"))
    reopened = AttemptLedger(session.store, new_id=lambda: "attempt-after-restart", now=session.ledger.now)

    closed = reopened.interrupt_abandoned(OWNER, INTAKE, lambda start: True)

    assert [(v.status, v.completion) for v in closed] == [("INTERRUPTED", "UNKNOWN")]
    assert closed[0].settlement.usage.source == "UNKNOWN"  # type: ignore[union-attr]
    assert session.runner.turn_count == 0  # no container started: nothing was replayed


def test_recovery_reparses_the_saved_text_without_starting_another_container(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-recovery",
                      [provider_script(CASES["concrete-thesis"]["provider"])])
    first = first_turn(session, "concrete-thesis")

    waiting = session.ledger.unpublished_results(OWNER, INTAKE)
    recovered = session.interpreter.reparse(waiting[0], CASES["concrete-thesis"]["intake"])

    assert recovered == first.parsed
    assert session.runner.turn_count == 1


def test_another_owner_cannot_see_or_retry_these_attempts_and_no_container_starts(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-foreign-owner",
                      [provider_script(CASES["concrete-thesis"]["provider"])])
    first = first_turn(session, "concrete-thesis")

    denied = session.interpreter.interpret("owner-b-0000", INTAKE, CASES["concrete-thesis"]["intake"],
                                           retry_of=first.attempt_id)

    assert isinstance(denied, Unavailable) and denied.reason_code == "retry_target_invalid"
    assert session.ledger.history("owner-b-0000", INTAKE) == []
    assert session.runner.turn_count == 1


def test_the_wire_request_carries_only_the_task_and_no_owner_or_request_identifier(
        pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    session = Session(pinned_hermes_image, run_id, evidence_root, "flow-wire", [
        provider_script(CASES["concrete-thesis"]["provider"])])
    first_turn(session, "concrete-thesis")

    observed = session.ledger.history(OWNER, INTAKE)[0].settlement.runtime_observed  # type: ignore[union-attr]
    assert observed["wire_forbidden_present"] == []  # neither the owner id nor the request id reached the provider
    assert (observed["wire_tool_count"], observed["wire_system_contains_prompt"], observed["wire_user_message_verbatim"]) == (
        0, True, True)
    assert len(observed["wire_request_sha256"]) == 64 and len(observed["wire_system_message_sha256"]) == 64
    request = json.loads(next((evidence_root / "flow-wire").glob("turn-01-*/output/requests/request-1.json")).read_text())
    assert (request["max_tokens"], request.get("stream", False), request.get("tools")) == (4096, False, None)
    assert [m["role"] for m in request["messages"]] == ["system", "user"]
