"""Interpretation through the pinned Hermes integration.

`HermesInterpreter` builds one request, records the attempt before the call, hands the request to an injected
`HermesTurnRunner` (the whole-process Hermes boundary), settles the attempt, and parses the generated text whole.
It makes exactly one attempt per call. It never retries, repairs or replays an uncertain attempt.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import Any, Protocol

from edge_os_api.records import contract_adapter as record_contract
from .interpretation_attempts import (
    AlreadySettled, AttemptIdentity, AttemptInFlight, AttemptLedger, AttemptSettlement, AttemptView, ExecutionGuard,
    LateResult, RetryTargetInvalid, Usage,
)
from .interpretation_response import (
    ADOPT_QUESTION_ID, APPLICATION_OWNED_FIELDS, ClarificationAnswer, OfferedQuestion, ParsedInterpretation, Rejection,
    parse_follow_up_response, parse_interpretation_response,
)

__all__ = ["HermesInterpreter", "HermesInterpreterConfig", "HermesTurn", "HermesTurnResult", "HermesTurnRunner",
           "Interpreted", "LiveRelease", "LiveReleaseRequired", "OutputRejected", "Unavailable",
           "apply_choice_answer", "open_questions"]

PINNED_HERMES_COMMIT = "54bc5e509c985f37265c3d416bd2c64b10fc77ba"
PINNED_HERMES_LOCK_SHA256 = "de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01"
PROMPT_VERSION = "p05-interpretation/1"
RUNTIME_LABELS = ("LOCAL_FAKE_PROVIDER", "LIVE")

RESPONSE_SHAPE = """\
{"meaning_status": "SUPPORTED" | "UNSUPPORTED",
 "missing_capability": null | "<snake_case name>",
 "evidence_readiness": "READY" | "UNRESOLVED",
 "field_evidence": [
   {"field_name": "<one of model_fields>", "state": "KNOWN", "origin": "USER_STATED", "source_passage": "<exact words>", "value": <value>},
   {"field_name": "<one of model_fields>", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING", "value": <value>},
   {"field_name": "<one of model_fields>", "state": "MISSING"},
   {"field_name": "<one of model_fields>", "state": "CONFLICTING", "conflicts": [{"value": <value>, "source_passage": "<exact words>"}, ...]}],
 "questions": [{"question_id": "<id>", "field_name": "<a MISSING or CONFLICTING field>", "text": "<question ending with ?>",
                "options": [{"id": "<id>", "label": "<label that states every number in value>", "value": <value>}]}]}"""

SYSTEM_PROMPT = f"""\
You turn one user's trading idea into structured meaning for a research application. The application checks every
word of your answer. It rejects the whole answer when one rule below is broken, and it never repairs an answer.

Return exactly one JSON object and nothing else: no text before or after it, no code fence, no second object.
Write every decimal number as a JSON string such as "0.01". Never write a JSON number with a fraction.

The object has these keys, all required:
{RESPONSE_SHAPE}

Rules:
1. Copy the user's words exactly in every source_passage, character for character. Do not paraphrase them.
2. A number in a USER_STATED value must be stated in its source_passage. Write 1% as "0.01", 50 bps as "0.005".
3. Use AGENT_PROPOSED with adoption "PENDING" only for something the user did not say. The user decides later.
   Prefer MISSING plus a question for the entry rule and the exit rule. Never invent them.
4. Never report restrictions, market or decision_interval_seconds. The application records them.
5. When the idea needs a capability that the supported rules cannot express, set meaning_status to "UNSUPPORTED",
   name the capability in missing_capability, and leave out anything you would substitute. Never swap in an easier idea.
6. When the user states two values for one field, use CONFLICTING and quote each statement. Do not pick one.
7. A question must ask about a field you report as MISSING or CONFLICTING. Its text ends with "?". Each option label
   states every number that its value carries.
8. Use the shapes in field_shapes and only the operators in operators. Those shapes show form, not advice.
9. When requested_job is not CREATE_STRATEGY, model_fields is empty: return an empty field_evidence and no questions,
   and set evidence_readiness to "UNRESOLVED" when the user asks you to look for ideas without a thesis.

When task is "follow_up", the user answered a question. List only the fields that the answer changes or adds. The
application keeps every other field as it was. Quote the answer's exact words. If the answer restates meaning that is
already stated, list nothing for it. If the answer contradicts stated meaning, report that field as CONFLICTING with the
new statement only; the application keeps the earlier statement as the other alternative.
"""


class LiveReleaseRequired(Exception):
    """A live runtime needs a recorded controller release for its provider, model and budget."""


@dataclass(frozen=True)
class LiveRelease:
    release_id: str
    provider: str
    model: str
    budget_usd: str
    recorded_in: str


@dataclass(frozen=True)
class HermesInterpreterConfig:
    model: str
    route: str
    max_output_tokens: int
    runtime_label: str = "LOCAL_FAKE_PROVIDER"
    live_release: LiveRelease | None = None

    def identity(self) -> dict[str, Any]:
        """The configuration that every attempt records and hashes."""
        identity: dict[str, Any] = {
            "model": self.model, "route": self.route, "max_output_tokens": self.max_output_tokens,
            "hermes_commit": PINNED_HERMES_COMMIT, "hermes_lock_sha256": PINNED_HERMES_LOCK_SHA256,
            "tools": [], "memory": "off", "context_files": "off", "fallback": "none", "streaming": "off"}
        if self.live_release is not None:
            identity["live_release_id"] = self.live_release.release_id
        return identity


@dataclass(frozen=True)
class HermesTurn:
    attempt_id: str
    system_prompt: str
    user_message: str
    model: str
    route: str
    max_output_tokens: int


@dataclass(frozen=True)
class HermesTurnResult:
    status: str
    text: str | None
    usage: Usage
    request_count: int | None
    observed: Mapping[str, Any] = field(default_factory=dict)
    error_class: str | None = None


class HermesTurnRunner(Protocol):
    def run_turn(self, turn: HermesTurn) -> HermesTurnResult: ...


@dataclass(frozen=True)
class Interpreted:
    attempt_id: str
    parsed: ParsedInterpretation


@dataclass(frozen=True)
class OutputRejected:
    attempt_id: str
    rejection: Rejection


@dataclass(frozen=True)
class Unavailable:
    attempt_id: str | None
    reason_code: str
    detail: str


InterpretResult = Interpreted | OutputRejected | Unavailable

UNAVAILABLE_DETAIL = {
    "provider_failed": "The model provider did not return a result. The request is saved. You can try again.",
    "timed_out": "The model provider took too long. The request is saved. You can try again.",
    "outcome_unknown": "It is not known whether the model provider finished. The request is saved.",
    "attempt_in_flight": "An earlier attempt for this request has not finished.",
    "retry_target_invalid": "The attempt to retry does not belong to this request.",
    "attempt_not_recorded": "The attempt could not be recorded, so no model call was made.",
    "result_not_recorded": "The result could not be recorded, so it was not used.",
    "result_arrived_late": "The result arrived after the attempt was closed. It is kept for review and was not used.",
}
STATUS_BY_RUNNER_STATUS = {"RETURNED": "COMPLETED", "TRUNCATED": "TRUNCATED", "PROVIDER_FAILED": "PROVIDER_FAILED",
                           "TIMED_OUT": "TIMED_OUT"}
UNAVAILABLE_BY_STATUS = {"PROVIDER_FAILED": "provider_failed", "TIMED_OUT": "timed_out", "UNKNOWN": "outcome_unknown"}
ERROR_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _error_class(name: str | None) -> str | None:
    """Keep a class name only. Provider text never reaches a stored or public field."""
    return name if name is not None and ERROR_CLASS.fullmatch(name) else ("ProviderError" if name else None)


def _model_fields(intake: Mapping[str, Any]) -> list[str]:
    if intake["requested_job"] != "CREATE_STRATEGY":
        return []
    return [name for name in record_contract.CREATE_STRATEGY_FIELDS if name not in APPLICATION_OWNED_FIELDS]


def _task_base(kind: str, intake: Mapping[str, Any]) -> dict[str, Any]:
    names = _model_fields(intake)
    task: dict[str, Any] = {
        "task": kind, "original_request": intake["original_request"], "restrictions": list(intake["restrictions"]),
        "requested_job": intake["requested_job"], "input_class": intake["input_class"], "model_fields": names,
        "field_shapes": {name: copy.deepcopy(record_contract.FIXTURE_STRATEGY[name]) for name in names},
        "operators": list(record_contract.CONTRACT["operators"]), "supported_restrictions": sorted(record_contract.SUPPORTED_RESTRICTIONS)}
    if intake.get("declared_market") is not None:
        task["declared_market"] = copy.deepcopy(intake["declared_market"])
    return task


def _model_view(evidence: Sequence[Mapping[str, Any]], names: Sequence[str]) -> list[dict[str, Any]]:
    """What the model may know about earlier evidence: model-owned fields only, without revision ids."""
    view: list[dict[str, Any]] = []
    for item in evidence:
        if item["field_name"] not in names:
            continue
        entry: dict[str, Any] = {"field_name": item["field_name"], "state": item["state"]}
        if item["state"] == "KNOWN":
            entry.update(origin=item["origin"], value=copy.deepcopy(item["value"]))
            if "adoption" in item:
                entry["adoption"] = item["adoption"]
        elif item["state"] == "CONFLICTING":
            entry["conflicts"] = copy.deepcopy(item["conflicts"])
        view.append(entry)
    return view


def _task_json(task: Mapping[str, Any]) -> str:
    return record_contract.canonical_bytes(task).decode("utf-8")


class HermesInterpreter:
    def __init__(self, config: HermesInterpreterConfig, runner: HermesTurnRunner, ledger: AttemptLedger,
                 monotonic: Callable[[], float], guard: ExecutionGuard | None = None) -> None:
        if config.runtime_label not in RUNTIME_LABELS:
            raise ValueError(f"unknown runtime label {config.runtime_label!r}")
        if config.runtime_label == "LIVE" and (config.live_release is None or config.live_release.model != config.model):
            raise LiveReleaseRequired("A live runtime needs a recorded release for this provider, model and budget.")
        self._config, self._runner, self._ledger, self._monotonic = config, runner, ledger, monotonic
        self._guard = guard

    def interpret(self, owner_id: str, intake_record_id: str, intake: Mapping[str, Any],
                  retry_of: str | None = None) -> InterpretResult:
        """One attempt to interpret the saved request. A retry is a new call that names the attempt it follows."""
        task = _task_json(_task_base("interpret", intake))
        return self._attempt(owner_id, intake_record_id, "INTERPRET", task, None, None, None, retry_of,
                             lambda text: parse_interpretation_response(text, intake))

    def follow_up(self, owner_id: str, intake_record_id: str, intake: Mapping[str, Any],
                  previous_evidence: Sequence[Mapping[str, Any]], question: str, answer: ClarificationAnswer,
                  retry_of: str | None = None, previous_revision_id: str | None = None) -> InterpretResult:
        """One attempt to read a free-text reply to a clarification question."""
        task = _task_base("follow_up", intake)
        task.update(previous_field_evidence=_model_view(previous_evidence, task["model_fields"]),
                    question=question, answer=answer.text)
        return self._attempt(owner_id, intake_record_id, "FOLLOW_UP", _task_json(task), answer.answer_ref, answer.text,
                             previous_revision_id, retry_of,
                             lambda text: parse_follow_up_response(text, intake, previous_evidence, answer))

    def reparse(self, view: AttemptView, intake: Mapping[str, Any],
                previous_evidence: Sequence[Mapping[str, Any]] | None = None,
                answer: ClarificationAnswer | None = None) -> ParsedInterpretation | Rejection:
        """Parse a saved response again. This is recovery: it makes no model call."""
        settlement = view.settlement
        if settlement is None or settlement.response_text is None:
            return Rejection("no_saved_response", "", "This attempt saved no response.")
        if view.start.identity.purpose == "INTERPRET":
            return parse_interpretation_response(settlement.response_text, intake)
        if previous_evidence is None or answer is None:
            return Rejection("missing_context", "", "A follow-up needs its earlier evidence and the user's reply.")
        return parse_follow_up_response(settlement.response_text, intake, previous_evidence, answer)

    def _attempt(self, owner_id: str, intake_record_id: str, purpose: str, task: str, answer_ref: str | None,
                 answer_text: str | None, previous_revision_id: str | None, retry_of: str | None,
                 parse: Callable[[str], ParsedInterpretation | Rejection]) -> InterpretResult:
        identity = AttemptIdentity(
            purpose=purpose, prompt_version=PROMPT_VERSION, system_prompt_sha256=_sha256(SYSTEM_PROMPT),
            task_sha256=_sha256(task), task_text=task, response_shape_sha256=_sha256(RESPONSE_SHAPE),
            manifest_sha256=record_contract.manifest_sha256(), config=self._config.identity(),
            runtime_label=self._config.runtime_label, answer_ref=answer_ref, answer_text=answer_text,
            previous_revision_id=previous_revision_id)
        attempt_id = self._ledger.new_attempt_id()
        with ExitStack() as held:
            if self._guard is not None:  # the claim comes first, so a recorded attempt is never seen without its claim
                try:
                    held.enter_context(self._guard.claim(attempt_id))
                except Exception:  # noqa: BLE001 - without a claim the attempt cannot be shown to be running
                    return Unavailable(None, "attempt_not_recorded", UNAVAILABLE_DETAIL["attempt_not_recorded"])
            return self._run_claimed(attempt_id, owner_id, intake_record_id, identity, retry_of, parse)

    def _run_claimed(self, attempt_id: str, owner_id: str, intake_record_id: str, identity: AttemptIdentity,
                     retry_of: str | None,
                     parse: Callable[[str], ParsedInterpretation | Rejection]) -> InterpretResult:
        try:
            start = self._ledger.begin(owner_id, intake_record_id, identity, retry_of, attempt_id=attempt_id)
        except AttemptInFlight:
            return Unavailable(None, "attempt_in_flight", UNAVAILABLE_DETAIL["attempt_in_flight"])
        except RetryTargetInvalid:
            return Unavailable(None, "retry_target_invalid", UNAVAILABLE_DETAIL["retry_target_invalid"])
        except Exception:  # noqa: BLE001 - storage can fail in many ways; with no record there must be no provider call
            return Unavailable(None, "attempt_not_recorded", UNAVAILABLE_DETAIL["attempt_not_recorded"])
        turn = HermesTurn(attempt_id=start.attempt_id, system_prompt=SYSTEM_PROMPT, user_message=identity.task_text,
                          model=self._config.model, route=self._config.route,
                          max_output_tokens=self._config.max_output_tokens)
        began = self._monotonic()
        try:
            result = self._runner.run_turn(turn)
        except Exception as error:  # noqa: BLE001 - after an unexpected failure it is unknown whether the provider worked
            latency_ms = round((self._monotonic() - began) * 1000)
            return self._settle(start.attempt_id, owner_id, "UNKNOWN", None, Usage(), None, {}, _error_class(
                type(error).__name__), latency_ms, "NOT_PARSED", None)
        latency_ms = round((self._monotonic() - began) * 1000)
        return self._finish(start.attempt_id, owner_id, result, latency_ms, parse)

    def _finish(self, attempt_id: str, owner_id: str, result: HermesTurnResult, latency_ms: int,
                parse: Callable[[str], ParsedInterpretation | Rejection]) -> InterpretResult:
        status = STATUS_BY_RUNNER_STATUS.get(result.status, "UNKNOWN")
        if status == "COMPLETED" and result.text is None:
            status = "UNKNOWN"
        text = result.text if status in {"COMPLETED", "TRUNCATED"} else None
        outcome: ParsedInterpretation | Rejection | None = None
        parse_result = "NOT_PARSED"
        if text is not None:
            if status == "TRUNCATED":
                outcome = Rejection("truncated", "", "The model's answer was cut short, so none of it was used.")
            elif not _within_approved_settings(result):
                outcome = Rejection("runtime_policy_violation", "",
                                    "The model ran outside its approved settings, so its answer was not used.")
            else:
                outcome = parse(text)
            parse_result = "ACCEPTED" if isinstance(outcome, ParsedInterpretation) else f"REJECTED:{outcome.reason_code}"
        return self._settle(attempt_id, owner_id, status, text, result.usage, result.request_count,
                            dict(result.observed), _error_class(result.error_class), latency_ms, parse_result, outcome)

    def _settle(self, attempt_id: str, owner_id: str, status: str, text: str | None, usage: Usage,
                request_count: int | None, observed: Mapping[str, Any], error_class: str | None, latency_ms: int,
                parse_result: str, outcome: ParsedInterpretation | Rejection | None) -> InterpretResult:
        settlement = AttemptSettlement(
            attempt_id=attempt_id, owner_id=owner_id, status=status, finished_at=self._ledger.now(),
            latency_ms=latency_ms, usage=usage, request_count=request_count,
            response_sha256=_sha256(text) if text is not None else None, response_text=text,
            parse_result=parse_result, error_class=error_class, runtime_observed=observed)
        try:
            self._ledger.settle(settlement)
        except AlreadySettled:  # the attempt was closed as unknown while it ran: keep this result as evidence only
            return self._keep_late(settlement)
        except Exception:  # noqa: BLE001 - an unrecorded result is not released; abandonment is proved later
            return Unavailable(attempt_id, "result_not_recorded", UNAVAILABLE_DETAIL["result_not_recorded"])
        if isinstance(outcome, ParsedInterpretation):
            return Interpreted(attempt_id, outcome)
        if isinstance(outcome, Rejection):
            return OutputRejected(attempt_id, outcome)
        reason = UNAVAILABLE_BY_STATUS[status]
        return Unavailable(attempt_id, reason, UNAVAILABLE_DETAIL[reason])


    def _keep_late(self, settlement: AttemptSettlement) -> Unavailable:
        try:
            self._ledger.observe_late_result(LateResult(
                observation_id=self._ledger.new_attempt_id(), attempt_id=settlement.attempt_id,
                owner_id=settlement.owner_id, observed_at=settlement.finished_at, status=settlement.status,
                response_sha256=settlement.response_sha256, response_text=settlement.response_text,
                usage=settlement.usage, request_count=settlement.request_count, error_class=settlement.error_class))
        except Exception:  # noqa: BLE001 - nothing more can be kept; the result stays unused either way
            return Unavailable(settlement.attempt_id, "result_not_recorded", UNAVAILABLE_DETAIL["result_not_recorded"])
        return Unavailable(settlement.attempt_id, "result_arrived_late", UNAVAILABLE_DETAIL["result_arrived_late"])


def _within_approved_settings(result: HermesTurnResult) -> bool:
    """True only when the runtime reported the approved settings, sent our prompt and task, and made one request."""
    observed = result.observed
    return (observed.get("tools_effective") == [] and observed.get("fallback_count") == 0
            and observed.get("skip_memory_effective") is True and observed.get("streaming_disabled") is True
            and observed.get("wire_system_contains_prompt") is True and observed.get("wire_user_message_verbatim") is True
            and result.request_count == 1)


def apply_choice_answer(evidence: Sequence[Mapping[str, Any]], offered: Sequence[OfferedQuestion], question_id: str,
                        choice_id: str) -> tuple[list[dict[str, Any]], str, str] | None:
    """Apply one offered choice or the adoption review. Return (evidence, question text, answer ref), or None."""
    updated = [copy.deepcopy(dict(item)) for item in evidence]
    answer_ref = f"choice:{question_id}:{choice_id}"
    if question_id == ADOPT_QUESTION_ID:
        pending = [item for item in updated if item["state"] == "KNOWN" and item.get("adoption") == "PENDING"]
        if choice_id != "adopt" or not pending:
            return None
        for item in pending:
            item["adoption"] = "ADOPTED"
        names = ", ".join(sorted(item["field_name"].replace("_", " ") for item in pending))
        return updated, f"Adopt the suggested settings: {names}?", answer_ref
    question = next((q for q in offered if q.question_id == question_id), None)
    option = next((o for o in question.options if o.id == choice_id), None) if question else None
    target = next((i for i in updated if question and i["field_name"] == question.field_name), None)
    if question is None or option is None or target is None or target["state"] not in {"MISSING", "CONFLICTING"}:
        return None
    updated[updated.index(target)] = {
        "field_name": question.field_name, "state": "KNOWN", "origin": "USER_CONFIRMED", "source_ref": answer_ref,
        "interpretation_revision": "", "evidence_status": "HYPOTHESIS", "value": copy.deepcopy(option.value)}
    return updated, question.text, answer_ref


def open_questions(offered: Sequence[OfferedQuestion], evidence: Sequence[Mapping[str, Any]],
                   targets: Sequence[str]) -> list[dict[str, Any]]:
    """The open questions for the interface: one entry per offered choice and one bundled adoption review."""
    by_name = {item["field_name"]: item for item in evidence}
    questions: list[dict[str, Any]] = []
    for question in offered:
        item = by_name.get(question.field_name)
        if question.field_name in targets and item is not None and item["state"] in {"MISSING", "CONFLICTING"}:
            questions.append({"question_id": question.question_id, "kind": "CHOICE", "field_name": question.field_name,
                              "text": question.text, "options": [{"id": o.id, "label": o.label} for o in question.options]})
    items = []
    for name in targets:
        item = by_name.get(name)
        if item is not None and item.get("adoption") == "PENDING":
            label = name.replace("_", " ").capitalize()
            items.append({"field_name": name, "label": label, "origin": item["origin"], "value": copy.deepcopy(item["value"]),
                          "summary": record_contract.canonical_bytes(item["value"]).decode("utf-8"),
                          "question": f"Adopt the suggested {label.lower()}?"})
    if items:
        questions.append({"question_id": ADOPT_QUESTION_ID, "kind": "ADOPT",
                          "text": "Review the suggested settings. Adopt them to continue.", "items": items,
                          "options": [{"id": "adopt", "label": "Adopt these settings"}]})
    return questions
