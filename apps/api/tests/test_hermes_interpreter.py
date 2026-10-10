"""Public behavior of the Hermes interpretation adapter.

Only the Hermes process boundary is replaced (`ScriptedRunner`). The ledger, the parser and the request builder are
real. These tests prove adapter mechanics. They do not show what a real model would write.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
from collections.abc import Callable
from typing import Any

import pytest

from edge_os_api.research.hermes_interpreter import (
    PROMPT_VERSION, HermesInterpreter, HermesInterpreterConfig, HermesTurn, HermesTurnResult, Interpreted, LiveRelease,
    LiveReleaseRequired, OutputRejected, Unavailable, apply_choice_answer, open_questions,
)
from edge_os_api.research.interpretation_attempts import AttemptLedger, Usage
from edge_os_api.research.interpretation_response import ClarificationAnswer, ParsedInterpretation
from test_interpretation_attempts import MemoryAttemptStore
from test_interpretation_response import (
    HUNCH, HUNCH_INTAKE, RESTRICTIONS_ITEM, STATED_ENTRY, THESIS, THESIS_INTAKE, TWO_PERCENT,
    hunch_response, thesis_response,
)

OWNER, OTHER_OWNER, INTAKE = "owner-a", "owner-b", "intake-1"
CONFIG = HermesInterpreterConfig(model="fixture-model/1", route="local-fake-provider", max_output_tokens=4096)
OBSERVED_OK = {"tools_effective": [], "fallback_count": 0, "streaming_disabled": True, "skip_memory_effective": True,
               "api_max_retries": 1, "wire_system_contains_prompt": True, "wire_user_message_verbatim": True,
               "wire_request_sha256": "e" * 64}
REPORTED = Usage(input_tokens=1200, output_tokens=300, total_tokens=1500, source="PROVIDER_REPORTED")


def failing(error: BaseException) -> Callable[..., Any]:
    def raise_error(*_args: Any, **_kwargs: Any) -> Any:
        raise error
    return raise_error


def failed(status: str, error_class: str) -> HermesTurnResult:
    return HermesTurnResult(status=status, text=None, usage=Usage(), request_count=1, observed=OBSERVED_OK,
                            error_class=error_class)


def returned(text: str, usage: Usage = REPORTED, **changes: Any) -> HermesTurnResult:
    base = dict(status="RETURNED", text=text, usage=usage, request_count=1, observed=OBSERVED_OK, error_class=None)
    return HermesTurnResult(**{**base, **changes})


class ScriptedRunner:
    """The Hermes process boundary: returns the next scripted result, or raises the next scripted exception."""

    def __init__(self, *script: HermesTurnResult | BaseException) -> None:
        self.script = list(script)
        self.turns: list[HermesTurn] = []
        self.probe: Callable[[], None] | None = None  # runs at call time, to observe what exists during the call

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        self.turns.append(turn)
        if self.probe is not None:
            self.probe()
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class RecordingGuard:
    """Stands in for the claim that proves who runs an attempt. It records when the claim is held."""

    def __init__(self, fail_to_claim: bool = False) -> None:
        self.held: list[str] = []
        self.history: list[str] = []
        self.fail_to_claim = fail_to_claim

    def claim(self, attempt_id: str):
        guard = self

        class Claim:
            def __enter__(self) -> None:
                if guard.fail_to_claim:
                    raise RuntimeError("claim connection lost")
                guard.held.append(attempt_id)
                guard.history.append(f"claim:{attempt_id}")

            def __exit__(self, *_exc: Any) -> None:
                guard.held.remove(attempt_id)
                guard.history.append(f"release:{attempt_id}")
        return Claim()

    def is_abandoned(self, attempt_id: str) -> bool:
        return attempt_id not in self.held


def build(*script: HermesTurnResult | BaseException, store: MemoryAttemptStore | None = None,
          config: HermesInterpreterConfig = CONFIG, guard: RecordingGuard | None = None) -> tuple[HermesInterpreter, ScriptedRunner, AttemptLedger,
                                                              MemoryAttemptStore]:
    store = store or MemoryAttemptStore()
    ids, ticks = itertools.count(1), itertools.count(0)
    ledger = AttemptLedger(store, new_id=lambda: f"attempt-{next(ids)}",
                           now=lambda: dt.datetime(2026, 10, 9, 12, 0, tzinfo=dt.timezone.utc)
                           + dt.timedelta(seconds=next(ticks)))
    runner = ScriptedRunner(*script)
    clock = itertools.chain.from_iterable((100.0 + 10 * n, 102.5 + 10 * n) for n in itertools.count())
    return HermesInterpreter(config, runner, ledger, monotonic=lambda: next(clock), guard=guard), runner, ledger, store


def thesis_text() -> str:
    return json.dumps(thesis_response())


def test_a_concrete_thesis_goes_through_the_runner_and_is_recorded_as_one_completed_attempt() -> None:
    interpreter, runner, ledger, _ = build(returned(thesis_text()))
    seen_during_call: list[str] = []
    runner.probe = lambda: seen_during_call.append(ledger.history(OWNER, INTAKE)[0].status)

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Interpreted) and isinstance(result.parsed, ParsedInterpretation)
    assert seen_during_call == ["STARTED"]  # the attempt was recorded before the provider call
    assert len(runner.turns) == 1
    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.start.attempt_id, view.start.sequence, view.status, view.completion) == (
        result.attempt_id, 1, "COMPLETED", "COMPLETE")
    settlement = view.settlement
    assert settlement is not None
    assert settlement.parse_result == "ACCEPTED"
    assert settlement.latency_ms == 2500
    assert settlement.usage == REPORTED
    assert settlement.request_count == 1
    assert settlement.response_text == thesis_text()
    assert settlement.response_sha256 == hashlib.sha256(thesis_text().encode()).hexdigest()
    assert settlement.runtime_observed == OBSERVED_OK
    assert result.parsed.response_sha256 == settlement.response_sha256


def test_the_attempt_keeps_exact_request_configuration_and_source_identities() -> None:
    interpreter, runner, ledger, _ = build(returned(thesis_text()))
    interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    start = ledger.history(OWNER, INTAKE)[0].start
    turn = runner.turns[0]
    assert start.identity.purpose == "INTERPRET"
    assert start.identity.prompt_version == PROMPT_VERSION == "p05-interpretation/1"
    assert start.identity.system_prompt_sha256 == hashlib.sha256(turn.system_prompt.encode()).hexdigest()
    assert start.identity.task_sha256 == hashlib.sha256(turn.user_message.encode()).hexdigest()
    assert start.identity.task_text == turn.user_message  # the exact request, not only its hash
    assert start.identity.answer_ref is None
    assert start.identity.runtime_label == "LOCAL_FAKE_PROVIDER"
    assert start.identity.config == {
        "model": "fixture-model/1", "route": "local-fake-provider", "max_output_tokens": 4096,
        "hermes_commit": "54bc5e509c985f37265c3d416bd2c64b10fc77ba",
        "hermes_lock_sha256": "de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01",
        "tools": [], "memory": "off", "context_files": "off", "fallback": "none", "streaming": "off"}
    assert len(start.identity.manifest_sha256) == 64 and len(start.identity.response_shape_sha256) == 64
    assert (turn.model, turn.route, turn.max_output_tokens, turn.attempt_id) == (
        "fixture-model/1", "local-fake-provider", 4096, start.attempt_id)


def test_the_request_carries_the_users_words_and_nothing_that_identifies_the_owner() -> None:
    interpreter, runner, _, _ = build(returned(thesis_text()))
    interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    task = json.loads(runner.turns[0].user_message)
    assert task["task"] == "interpret"
    assert task["original_request"] == THESIS
    assert task["restrictions"] == ["no leverage"]
    assert (task["requested_job"], task["input_class"]) == ("CREATE_STRATEGY", "CONCRETE_THESIS")
    assert task["model_fields"] == ["data_inputs", "entry", "exit", "invalidation", "sizing", "additions",
                                    "partial_exits", "cost_assumptions", "risk_limits", "action_scope"]
    for text in (runner.turns[0].user_message, runner.turns[0].system_prompt):
        assert OWNER not in text and INTAKE not in text and "attempt-1" not in text


def test_usage_that_the_provider_did_not_report_stays_unknown() -> None:
    interpreter, _, ledger, _ = build(returned(thesis_text(), usage=Usage()))
    interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    usage = ledger.history(OWNER, INTAKE)[0].settlement.usage  # type: ignore[union-attr]
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens, usage.source) == (None, None, None, "UNKNOWN")


@pytest.mark.parametrize("text, reason_code", [
    pytest.param(thesis_text() + thesis_text(), "multiple_objects", id="two-objects"),
    pytest.param("```json\n" + thesis_text() + "\n```", "invalid_json", id="code-fence"),
    pytest.param(thesis_text()[:-30], "invalid_json", id="cut-off-text"),
])
def test_malformed_output_is_rejected_whole_kept_exactly_and_not_retried(text: str, reason_code: str) -> None:
    interpreter, runner, ledger, _ = build(returned(text))

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, OutputRejected) and result.rejection.reason_code == reason_code
    assert len(runner.turns) == 1  # no automatic retry or repair
    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.status, view.settlement.parse_result, view.settlement.response_text) == (  # type: ignore[union-attr]
        "COMPLETED", f"REJECTED:{reason_code}", text)
    assert len(ledger.history(OWNER, INTAKE)) == 1


def test_a_response_that_the_provider_marked_as_cut_short_is_rejected_even_when_it_parses() -> None:
    interpreter, _, ledger, _ = build(returned(thesis_text(), status="TRUNCATED"))

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, OutputRejected) and result.rejection.reason_code == "truncated"
    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.status, view.completion, view.settlement.parse_result) == (  # type: ignore[union-attr]
        "TRUNCATED", "TRUNCATED", "REJECTED:truncated")
    assert view.settlement.response_text == thesis_text()  # type: ignore[union-attr]


@pytest.mark.parametrize("observed_change, why", [
    pytest.param({"tools_effective": ["web_search"]}, "tool", id="a-tool-was-enabled"),
    pytest.param({"fallback_count": 1}, "fallback", id="a-fallback-provider-was-configured"),
    pytest.param({"skip_memory_effective": False}, "memory", id="memory-was-on"),
    pytest.param({"streaming_disabled": False}, "streaming", id="streaming-was-on"),
    pytest.param({"tools_effective": None}, "missing", id="runtime-did-not-report-its-tools"),
    pytest.param({"wire_system_contains_prompt": False}, "prompt", id="the-request-did-not-carry-our-system-prompt"),
    pytest.param({"wire_user_message_verbatim": False}, "task", id="the-request-did-not-carry-our-task-verbatim"),
    pytest.param({"wire_user_message_verbatim": None}, "unreported", id="runtime-did-not-report-what-it-sent"),
])
def test_output_from_a_runtime_that_broke_the_approved_settings_is_not_accepted(observed_change: dict[str, Any],
                                                                               why: str) -> None:
    interpreter, _, ledger, _ = build(returned(thesis_text(), observed={**OBSERVED_OK, **observed_change}))

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, OutputRejected) and result.rejection.reason_code == "runtime_policy_violation"
    settlement = ledger.history(OWNER, INTAKE)[0].settlement
    assert settlement is not None and settlement.parse_result == "REJECTED:runtime_policy_violation"
    assert settlement.usage == REPORTED  # the cost that happened is still recorded


def test_more_than_one_provider_request_is_a_policy_violation_even_when_the_text_is_valid() -> None:
    interpreter, _, ledger, _ = build(returned(thesis_text(), request_count=2))
    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)
    assert isinstance(result, OutputRejected) and result.rejection.reason_code == "runtime_policy_violation"
    assert ledger.history(OWNER, INTAKE)[0].settlement.request_count == 2  # type: ignore[union-attr]


@pytest.mark.parametrize("status, expected_reason", [("PROVIDER_FAILED", "provider_failed"),
                                                     ("TIMED_OUT", "timed_out")])
def test_a_failed_or_timed_out_attempt_is_unavailable_not_a_verdict_and_not_retried(status: str,
                                                                                    expected_reason: str) -> None:
    interpreter, runner, ledger, _ = build(failed(status, "ProviderHTTPError"))

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == expected_reason
    assert result.attempt_id == "attempt-1" and len(runner.turns) == 1
    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.status, view.settlement.error_class, view.settlement.parse_result) == (  # type: ignore[union-attr]
        status, "ProviderHTTPError", "NOT_PARSED")


def test_an_unexpected_runner_exception_leaves_the_outcome_unknown_and_leaks_none_of_its_text() -> None:
    interpreter, runner, ledger, store = build(RuntimeError("401 from api.example.invalid key=sk-secret-123"))

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == "outcome_unknown"
    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.status, view.completion, view.settlement.error_class) == (  # type: ignore[union-attr]
        "UNKNOWN", "UNKNOWN", "RuntimeError")
    stored = repr(store._settlements) + repr(store._starts) + repr(result)
    assert "sk-secret-123" not in stored and "api.example.invalid" not in stored
    assert len(runner.turns) == 1


def test_no_provider_work_starts_when_the_attempt_cannot_be_recorded() -> None:
    interpreter, runner, _, store = build(returned(thesis_text()))
    store.add_start = failing(OSError("database unavailable"))  # type: ignore[method-assign]

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == "attempt_not_recorded"
    assert runner.turns == []


def test_a_response_that_cannot_be_recorded_is_not_released_and_the_attempt_stays_open_for_recovery() -> None:
    interpreter, _, ledger, store = build(returned(thesis_text()))
    store.add_settlement = failing(OSError("database unavailable"))  # type: ignore[method-assign]

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == "result_not_recorded"
    assert ledger.history(OWNER, INTAKE)[0].status == "STARTED"  # a restart closes it as INTERRUPTED, never replays


def test_a_second_request_while_one_is_in_flight_is_refused_before_any_provider_work() -> None:
    interpreter, runner, ledger, _ = build(returned(thesis_text()))
    ledger.begin(OWNER, INTAKE, interpreter_identity(interpreter))  # an earlier attempt that never settled

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == "attempt_in_flight"
    assert runner.turns == []


def interpreter_identity(interpreter: HermesInterpreter) -> Any:
    from edge_os_api.research.interpretation_attempts import AttemptIdentity
    return AttemptIdentity("INTERPRET", PROMPT_VERSION, "a" * 64, hashlib.sha256(b"task").hexdigest(), "task", "c" * 64,
                           "d" * 64, {"model": "x"}, "LOCAL_FAKE_PROVIDER")


def test_a_retry_is_a_separate_attempt_and_the_failed_one_is_kept() -> None:
    interpreter, runner, ledger, _ = build(failed("PROVIDER_FAILED", "ProviderHTTPError"), returned(thesis_text()))

    first = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)
    assert isinstance(first, Unavailable) and first.attempt_id is not None
    second = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE, retry_of=first.attempt_id)

    assert isinstance(second, Interpreted)
    assert [(v.start.attempt_id, v.start.retry_of, v.status) for v in ledger.history(OWNER, INTAKE)] == [
        ("attempt-1", None, "PROVIDER_FAILED"), ("attempt-2", "attempt-1", "COMPLETED")]
    assert len(runner.turns) == 2


def test_another_owner_cannot_retry_or_see_the_attempts_of_a_request() -> None:
    interpreter, _, ledger, _ = build(returned(thesis_text()), returned(thesis_text()))
    first = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)
    assert isinstance(first, Interpreted)

    result = interpreter.interpret(OTHER_OWNER, INTAKE, THESIS_INTAKE, retry_of=first.attempt_id)

    assert isinstance(result, Unavailable) and result.reason_code == "retry_target_invalid"
    assert ledger.history(OTHER_OWNER, INTAKE) == []


def test_a_live_runtime_needs_a_recorded_release_before_it_can_be_built() -> None:
    live = HermesInterpreterConfig(model="provider/model", route="provider-route", max_output_tokens=4096,
                                   runtime_label="LIVE")
    with pytest.raises(LiveReleaseRequired):
        build(config=live)
    released = HermesInterpreterConfig(
        model="provider/model", route="provider-route", max_output_tokens=4096, runtime_label="LIVE",
        live_release=LiveRelease("release-1", "provider", "provider/model", "0.10", "controller-record-1"))
    interpreter, runner, ledger, _ = build(returned(thesis_text()), config=released)
    interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)
    assert ledger.history(OWNER, INTAKE)[0].start.identity.runtime_label == "LIVE"


def test_a_live_release_for_another_model_does_not_release_this_one() -> None:
    mismatched = HermesInterpreterConfig(
        model="provider/other-model", route="provider-route", max_output_tokens=4096, runtime_label="LIVE",
        live_release=LiveRelease("release-1", "provider", "provider/model", "0.10", "controller-record-1"))
    with pytest.raises(LiveReleaseRequired):
        build(config=mismatched)


# --- Follow-up, recovery and answering ---

def follow_up_text(delta: list[dict[str, Any]]) -> str:
    return json.dumps({**hunch_response(), "field_evidence": delta, "questions": []})


def test_a_free_text_reply_runs_a_follow_up_attempt_with_the_previous_meaning_and_the_question() -> None:
    reply = "Price up more than 2% over the last 15 minutes"
    text = follow_up_text([{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": reply,
                            "value": TWO_PERCENT}])
    interpreter, runner, ledger, _ = build(returned(text))
    missing_entry = {"field_name": "entry", "state": "MISSING", "origin": "USER_STATED",
                     "source_ref": "intake:original_request", "interpretation_revision": "r1",
                     "evidence_status": "UNKNOWN"}

    result = interpreter.follow_up(OWNER, INTAKE, HUNCH_INTAKE, [missing_entry], "What counts as a rise?",
                                   ClarificationAnswer("answer:choose-entry", reply))

    assert isinstance(result, Interpreted)
    entry = next(i for i in result.parsed.field_evidence if i["field_name"] == "entry")
    assert (entry["origin"], entry["source_ref"], entry["value"]) == ("USER_STATED", "answer:choose-entry#c0-46",
                                                                    TWO_PERCENT)
    task = json.loads(runner.turns[0].user_message)
    assert (task["task"], task["question"], task["answer"]) == ("follow_up", "What counts as a rise?", reply)
    assert task["original_request"] == HUNCH
    assert task["previous_field_evidence"] == [{"field_name": "entry", "state": "MISSING"}]
    identity = ledger.history(OWNER, INTAKE)[0].start.identity
    assert (identity.purpose, identity.answer_ref) == ("FOLLOW_UP", "answer:choose-entry")
    assert json.loads(identity.task_text)["answer"] == reply  # the user's reply survives in the attempt record


def test_a_follow_up_that_overwrites_stated_meaning_is_rejected_whole() -> None:
    reply = "Make it more than 2%"
    text = follow_up_text([{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED",
                            "source_passage": "more than 2%", "value": TWO_PERCENT}])
    interpreter, _, ledger, _ = build(returned(text))

    result = interpreter.follow_up(OWNER, INTAKE, THESIS_INTAKE, [STATED_ENTRY, RESTRICTIONS_ITEM], "Sure?",
                                   ClarificationAnswer("answer:q", reply))

    assert isinstance(result, OutputRejected) and result.rejection.reason_code == "silent_overwrite"
    assert ledger.history(OWNER, INTAKE)[0].settlement.parse_result == "REJECTED:silent_overwrite"  # type: ignore[union-attr]


def test_an_accepted_result_that_was_never_published_is_recovered_from_saved_text_without_a_new_call() -> None:
    interpreter, runner, ledger, _ = build(returned(thesis_text()))
    first = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)
    assert isinstance(first, Interpreted)

    waiting = ledger.unpublished_results(OWNER, INTAKE)
    recovered = interpreter.reparse(waiting[0], THESIS_INTAKE)

    assert recovered == first.parsed
    assert len(runner.turns) == 1  # recovery made no second call


def test_recovering_a_follow_up_needs_the_same_context_and_makes_no_new_call() -> None:
    reply = "Price up more than 2% over the last 15 minutes"
    text = follow_up_text([{"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": reply,
                            "value": TWO_PERCENT}])
    interpreter, runner, ledger, _ = build(returned(text))
    missing_entry = {"field_name": "entry", "state": "MISSING", "origin": "USER_STATED",
                     "source_ref": "intake:original_request", "interpretation_revision": "r1",
                     "evidence_status": "UNKNOWN"}
    answer = ClarificationAnswer("answer:choose-entry", reply)
    first = interpreter.follow_up(OWNER, INTAKE, HUNCH_INTAKE, [missing_entry], "What counts as a rise?", answer)
    assert isinstance(first, Interpreted)

    recovered = interpreter.reparse(ledger.unpublished_results(OWNER, INTAKE)[0], HUNCH_INTAKE, [missing_entry], answer)

    assert recovered == first.parsed and len(runner.turns) == 1


def hunch_parsed() -> ParsedInterpretation:
    interpreter, _, _, _ = build(returned(json.dumps(hunch_response())))
    result = interpreter.interpret(OWNER, INTAKE, HUNCH_INTAKE)
    assert isinstance(result, Interpreted)
    return result.parsed


def test_choosing_an_offered_option_records_the_users_confirmation_with_the_options_exact_value() -> None:
    parsed = hunch_parsed()
    applied = apply_choice_answer(list(parsed.field_evidence), list(parsed.questions), "choose-entry", "g3-2pct")

    assert applied is not None
    evidence, question_text, answer_ref = applied
    assert (question_text, answer_ref) == ("What should count as a rise for the entry rule?",
                                           "choice:choose-entry:g3-2pct")
    entry = next(i for i in evidence if i["field_name"] == "entry")
    assert entry == {"field_name": "entry", "state": "KNOWN", "origin": "USER_CONFIRMED",
                     "source_ref": "choice:choose-entry:g3-2pct", "interpretation_revision": "",
                     "evidence_status": "HYPOTHESIS", "value": TWO_PERCENT}
    assert [i for i in evidence if i["field_name"] != "entry"] == [
        i for i in parsed.field_evidence if i["field_name"] != "entry"]  # nothing else changed


@pytest.mark.parametrize("question_id, choice_id", [("choose-entry", "no-such-option"), ("no-such-question", "g3-1pct")])
def test_an_answer_that_was_not_offered_is_not_applied(question_id: str, choice_id: str) -> None:
    parsed = hunch_parsed()
    assert apply_choice_answer(list(parsed.field_evidence), list(parsed.questions), question_id, choice_id) is None


def test_a_choice_cannot_overwrite_a_field_that_is_already_known() -> None:
    parsed = hunch_parsed()
    answered = apply_choice_answer(list(parsed.field_evidence), list(parsed.questions), "choose-entry", "g3-1pct")
    assert answered is not None
    assert apply_choice_answer(answered[0], list(parsed.questions), "choose-entry", "g3-2pct") is None


def test_adopting_the_pending_proposals_marks_each_adopted_and_nothing_else() -> None:
    parsed = hunch_parsed()
    pending = [i["field_name"] for i in parsed.field_evidence if i.get("adoption") == "PENDING"]
    assert pending == ["market", "decision_interval_seconds"]

    applied = apply_choice_answer(list(parsed.field_evidence), list(parsed.questions), "adopt-suggested-settings",
                                  "adopt")

    assert applied is not None
    evidence, question_text, answer_ref = applied
    assert [i["adoption"] for i in evidence if i["field_name"] in pending] == ["ADOPTED", "ADOPTED"]
    assert question_text == "Adopt the suggested settings: decision interval seconds, market?"
    assert answer_ref == "choice:adopt-suggested-settings:adopt"
    assert apply_choice_answer(evidence, list(parsed.questions), "adopt-suggested-settings", "adopt") is None


def test_the_open_questions_view_lists_choices_for_open_fields_and_one_adoption_review() -> None:
    parsed = hunch_parsed()
    view = open_questions(list(parsed.questions), list(parsed.field_evidence),
                          ["entry", "market", "decision_interval_seconds"])

    assert view[0] == {"question_id": "choose-entry", "kind": "CHOICE", "field_name": "entry",
                       "text": "What should count as a rise for the entry rule?",
                       "options": [{"id": "g3-1pct", "label": "Price up more than 1% over the last 15 minutes"},
                                   {"id": "g3-2pct", "label": "Price up more than 2% over the last 15 minutes"}]}
    adopt = view[1]
    assert (adopt["question_id"], adopt["kind"], adopt["options"]) == (
        "adopt-suggested-settings", "ADOPT", [{"id": "adopt", "label": "Adopt these settings"}])
    assert [(i["field_name"], i["origin"]) for i in adopt["items"]] == [
        ("market", "APPLICATION_CONFIGURED"), ("decision_interval_seconds", "APPLICATION_CONFIGURED")]
    assert all(set(i) == {"field_name", "label", "origin", "value", "summary", "question"} for i in adopt["items"])


def test_a_runner_that_passes_provider_text_as_its_error_class_has_that_text_replaced_before_storage() -> None:
    leaky = "401 from api.example.invalid key=sk-secret-123"
    interpreter, _, ledger, store = build(failed("PROVIDER_FAILED", leaky))

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == "provider_failed"
    assert ledger.history(OWNER, INTAKE)[0].settlement.error_class == "ProviderError"  # type: ignore[union-attr]
    assert "sk-secret-123" not in repr(store._settlements) + repr(result)


def test_the_claim_is_held_before_the_attempt_is_recorded_and_through_the_call_and_then_released() -> None:
    guard = RecordingGuard()
    interpreter, runner, ledger, _ = build(returned(thesis_text()), guard=guard)
    seen: list[tuple[list[str], str]] = []
    runner.probe = lambda: seen.append((list(guard.held), ledger.history(OWNER, INTAKE)[0].status))

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Interpreted)
    assert seen == [([result.attempt_id], "STARTED")]
    assert guard.held == []
    assert guard.history == [f"claim:{result.attempt_id}", f"release:{result.attempt_id}"]


def test_the_claim_is_released_when_the_runner_raises() -> None:
    guard = RecordingGuard()
    interpreter, _, ledger, _ = build(RuntimeError("boom"), guard=guard)

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == "outcome_unknown"
    assert guard.held == []
    assert ledger.history(OWNER, INTAKE)[0].status == "UNKNOWN"


def test_when_the_claim_cannot_be_taken_nothing_is_recorded_and_no_call_is_made() -> None:
    guard = RecordingGuard(fail_to_claim=True)
    interpreter, runner, ledger, _ = build(returned(thesis_text()), guard=guard)

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == "attempt_not_recorded"
    assert runner.turns == []
    assert ledger.history(OWNER, INTAKE) == []


def test_a_follow_up_records_the_exact_reply_and_the_revision_it_answers() -> None:
    interpreter, _, ledger, _ = build(returned(json.dumps(hunch_response())), returned(thesis_text()))
    first = interpreter.interpret(OWNER, INTAKE, HUNCH_INTAKE)
    assert isinstance(first, Interpreted)
    answer = ClarificationAnswer("reply:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", THESIS)

    interpreter.follow_up(OWNER, INTAKE, HUNCH_INTAKE, first.parsed.field_evidence, "Which entry?", answer,
                          previous_revision_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

    identity = ledger.history(OWNER, INTAKE)[1].start.identity
    assert (identity.answer_ref, identity.answer_text) == ("reply:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", THESIS)
    assert identity.previous_revision_id == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def test_a_result_that_arrives_after_its_attempt_was_closed_is_kept_as_a_late_result_and_not_used() -> None:
    interpreter, runner, ledger, _ = build(returned(thesis_text()))
    runner.probe = lambda: ledger.interrupt_abandoned(OWNER, INTAKE, lambda start: True)

    result = interpreter.interpret(OWNER, INTAKE, THESIS_INTAKE)

    assert isinstance(result, Unavailable) and result.reason_code == "result_arrived_late"
    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.status, view.completion) == ("INTERRUPTED", "UNKNOWN")  # the settlement is unchanged
    late = ledger.late_results(OWNER, INTAKE)
    assert len(late) == 1
    assert (late[0].attempt_id, late[0].response_text, late[0].usage) == (result.attempt_id, thesis_text(), REPORTED)
    assert ledger.unpublished_results(OWNER, INTAKE) == []
