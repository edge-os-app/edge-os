"""The saved Research path when the interpreter is Hermes.

Order of work for one request: save the request, interpret it in a recorded attempt, then publish the accepted
result (revision, outcome and attempt link) in one transaction. The provider call never sits inside a transaction.

Three failures stay apart. Malformed model output is `malformed_model_output`. A provider that could not answer is
`interpreter_unavailable`. An answer that may or may not exist is `interpreter_outcome_unknown`. None of them is a
verdict on the user's idea, and an unsupported capability is a different outcome (`UNSUPPORTED`).

Recovery never calls a model. It closes only attempts whose claim nobody holds, and it publishes a saved accepted
result by parsing its stored text again.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding, invalid, service_unavailable
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.records.models import Record
from edge_os_api.research import service
from edge_os_api.research.attempt_store import AdvisoryLockGuard, PostgresAttemptStore
from edge_os_api.research.hermes_interpreter import (
    HermesInterpreter, HermesInterpreterConfig, HermesTurnRunner, Interpreted, InterpretResult, OutputRejected,
    Unavailable, apply_choice_answer, open_questions,
)
from edge_os_api.research.interpretation_attempts import AttemptLedger, AttemptView
from edge_os_api.research.interpretation_response import (
    ClarificationAnswer, OfferedOption, OfferedQuestion, ParsedInterpretation,
)
from edge_os_api.research.interpretation_publication import (
    OfferedBook, RecordPublicationCheck, first_reading_records, questions_to_json, reply_records,
)
from edge_os_api.research.outcome_router import Routed

log = logging.getLogger("edge_os")

LOCAL_FAKE_CONFIG = HermesInterpreterConfig(model="local-fake/p05-interpretation", route="local-fake-provider",
                                            max_output_tokens=4096, runtime_label="LOCAL_FAKE_PROVIDER")
LABEL = {"kind": "HERMES_LOCAL_FAKE_PROVIDER", "id": "p05-interpretation/4",
         "notice": "Actual pinned Hermes ran in a sandbox against a local fake provider. No real model was called "
                   "and no research ran."}
TEXT_QUESTION_PREFIX = "ask-"
UNCERTAIN = frozenset({"TIMED_OUT", "UNKNOWN", "INTERRUPTED"})

MALFORMED = "malformed_model_output"
UNAVAILABLE = "interpreter_unavailable"
OUTCOME_UNKNOWN = "interpreter_outcome_unknown"
REJECTION_DETAIL = "The model's answer could not be used (reason: {reason}). Nothing was changed. You can try again."
UNAVAILABLE_TEXT = {
    "provider_failed": "The model provider did not return a result. This is a system failure, not a verdict on the idea. "
                       "The request is saved. You can try again.",
    "timed_out": "It is not known whether the model provider finished. The request is saved. This attempt was not repeated.",
    "outcome_unknown": "It is not known whether the model provider finished. The request is saved. This attempt was not repeated.",
    "result_arrived_late": "The result arrived after the attempt was closed. It is kept for review and was not used.",
}


def questions_from_json(items: Sequence[dict[str, Any]]) -> list[OfferedQuestion]:
    return [OfferedQuestion(q["question_id"], q["field_name"], q["text"],
                            tuple(OfferedOption(o["id"], o["label"], o["value"]) for o in q["options"]))
            for q in items]


def _conflict(code: str, detail: str) -> AppError:
    return AppError(409, "VALIDATION", "CONFLICTED", "parent_revision_conflict", [finding(code, "/", detail)])


@dataclass(frozen=True)
class RetryState:
    allowed: bool
    retry_of: str | None
    reason: str | None


def retry_state(history: Sequence[AttemptView], has_interpretation: bool, head_revision_id: str | None) -> RetryState:
    """Whether an explicit retry may start now, and which attempt it follows. Uncertain work is never replayed."""
    if not history:
        return RetryState(not has_interpretation, None, "nothing_to_retry" if has_interpretation else None)
    last = history[-1]
    if last.settlement is None:
        return RetryState(False, None, "attempt_in_flight")
    if last.revision_id is not None or last.status == "COMPLETED" and last.settlement.parse_result == "ACCEPTED":
        return RetryState(False, None, "nothing_to_retry")
    if last.status in UNCERTAIN:
        return RetryState(False, None, "outcome_uncertain")
    if last.start.identity.purpose == "FOLLOW_UP" and last.start.identity.previous_revision_id != head_revision_id:
        return RetryState(False, None, "stale_reply")
    return RetryState(True, last.start.attempt_id, None)


def failure_for(status: str, parse_result: str) -> tuple[str, str, str]:
    """The finding code, plain words and retry hint that a settled, unusable attempt maps to."""
    if status == "PROVIDER_FAILED":
        return UNAVAILABLE, UNAVAILABLE_TEXT["provider_failed"], "SAFE_SAME_KEY"
    if parse_result.startswith("REJECTED:"):
        return MALFORMED, REJECTION_DETAIL.format(reason=parse_result.removeprefix("REJECTED:")), "SAFE_SAME_KEY"
    return OUTCOME_UNKNOWN, UNAVAILABLE_TEXT["outcome_unknown"], "RECONCILE"


def public_attempt(view: AttemptView) -> dict[str, Any]:
    """Structured values, hashes and sanitized codes. The generated text and the user's reply are not included."""
    start, settled, identity = view.start, view.settlement, view.start.identity
    usage = settled.usage if settled else None
    observed = settled.runtime_observed if settled else {}  # spend, as the guarded runner saved it; none after a crash
    return {
        "attempt_id": start.attempt_id, "sequence": start.sequence, "retry_of": start.retry_of,
        "purpose": identity.purpose, "status": view.status, "completion": view.completion,
        "started_at": record_contract.utc_string(start.started_at),
        "finished_at": record_contract.utc_string(settled.finished_at) if settled else None,
        "latency_ms": settled.latency_ms if settled else None,
        "usage": {"source": usage.source if usage else "UNKNOWN", "input_tokens": usage.input_tokens if usage else None,
                  "output_tokens": usage.output_tokens if usage else None,
                  "total_tokens": usage.total_tokens if usage else None},
        "request_count": settled.request_count if settled else None,
        "response_sha256": settled.response_sha256 if settled else None,
        "parse_result": settled.parse_result if settled else None,
        "error_class": settled.error_class if settled else None, "revision_id": view.revision_id,
        "spend": {"state": observed.get("spend_state"), "charge_usd": observed.get("spend_charge_usd")},
        "identity": {
            "prompt_version": identity.prompt_version, "system_prompt_sha256": identity.system_prompt_sha256,
            "task_sha256": identity.task_sha256, "response_shape_sha256": identity.response_shape_sha256,
            "manifest_sha256": identity.manifest_sha256, "config_sha256": start.config_sha256,
            "runtime_label": identity.runtime_label, "model": identity.config.get("model"),
            "route": identity.config.get("route"), "hermes_commit": identity.config.get("hermes_commit"),
            "answer_ref": identity.answer_ref, "previous_revision_id": identity.previous_revision_id}}


class HermesResearch:
    """Saved Research workflow with Hermes as the interpreter. One instance serves one application."""

    def __init__(self, runner: HermesTurnRunner, session_factory: Callable[[], Session], guard: AdvisoryLockGuard,
                 monotonic: Callable[[], float], config: HermesInterpreterConfig = LOCAL_FAKE_CONFIG) -> None:
        self._session_factory = session_factory
        self.guard = guard
        self.store = PostgresAttemptStore(session_factory)
        self.ledger = AttemptLedger(self.store, new_id=lambda: str(uuid.uuid4()), now=service.utcnow)
        self.interpreter = HermesInterpreter(config, runner, self.ledger, monotonic, guard=guard,
                                             publication=RecordPublicationCheck())

    def label(self) -> dict[str, str]:
        return dict(LABEL)

    # --- creating a request -------------------------------------------------------------------------------------

    def create_request(self, session: Session, principal: Principal, body: dict[str, Any]) -> dict[str, Any]:
        intake = service.save_intake(session, principal, body)
        session.commit()
        self._interpret(session, principal, intake.record_id, intake.content, retry_of=None)
        return service.load_bundle(session, principal, intake.record_id, self)

    def _interpret(self, session: Session, principal: Principal, intake_id: uuid.UUID, intake: dict[str, Any],
                   retry_of: str | None) -> None:
        owner = str(principal.user_id)
        session.rollback()  # no transaction is open while the provider is called
        result = self.interpreter.interpret(owner, str(intake_id), intake, retry_of)
        self._publish_initial(session, principal, intake_id, result)

    def _publish_initial(self, session: Session, principal: Principal, intake_id: uuid.UUID,
                         result: InterpretResult) -> None:
        if isinstance(result, Interpreted):
            self._publish_interpretation(session, principal, intake_id, result.attempt_id, result.parsed)
            return
        if isinstance(result, OutputRejected):
            detail = REJECTION_DETAIL.format(reason=result.rejection.reason_code)
            self._record_failure(session, principal, intake_id, result.attempt_id, MALFORMED, detail, "SAFE_SAME_KEY")
            return
        self._raise_or_record_unavailable(session, principal, intake_id, result)

    def _raise_or_record_unavailable(self, session: Session, principal: Principal, intake_id: uuid.UUID,
                                     result: Unavailable) -> None:
        reason = result.reason_code
        if reason == "attempt_in_flight":
            raise _conflict("attempt_in_flight", "An earlier attempt for this request has not finished.")
        if reason == "retry_target_invalid":
            raise _conflict("retry_target_invalid", "The attempt to retry does not belong to this request.")
        if reason == "revision_moved":
            raise _conflict("parent_revision_conflict", "The saved meaning changed first. Reload the request.")
        if reason in {"attempt_not_recorded", "result_not_recorded"} or result.attempt_id is None:
            raise service_unavailable("RECONCILE")
        known = reason == "provider_failed"
        self._record_failure(session, principal, intake_id, result.attempt_id, UNAVAILABLE if known else OUTCOME_UNKNOWN,
                             UNAVAILABLE_TEXT[reason], "SAFE_SAME_KEY" if known else "RECONCILE")

    # --- publishing ---------------------------------------------------------------------------------------------

    def _record_failure(self, session: Session, principal: Principal, intake_id: uuid.UUID, attempt_id: str, code: str,
                        detail: str, retry: str) -> None:
        """Save the system outcome for a first interpretation that failed. A failed reply leaves the saved meaning alone."""
        intake = service.lock_intake(session, principal, str(intake_id))
        view = self._view(principal, intake_id, attempt_id)
        if view.start.identity.purpose != "INTERPRET" or self._has_outcome_for(session, principal, attempt_id):
            session.rollback()
            return
        operation_id, moment = uuid.UUID(attempt_id), service.utcnow()
        routed = Routed("INVALID_INPUT", "INTERPRETATION", [finding(code, "/", detail)], retry=retry)
        service.persist_routed(session, principal, intake, None, routed, operation_id, moment)
        service.verify_lineage(session, principal, intake_id)
        session.commit()

    @staticmethod
    def _has_outcome_for(session: Session, principal: Principal, attempt_id: str) -> bool:
        return session.execute(text("select 1 from records where owner_id = :o and operation_id = :a "
                                    "and record_type = 'Outcome'"),
                               {"o": principal.user_id, "a": uuid.UUID(attempt_id)}).first() is not None

    def _view(self, principal: Principal, intake_id: uuid.UUID, attempt_id: str) -> AttemptView:
        return next(v for v in self.ledger.history(str(principal.user_id), str(intake_id))
                    if v.start.attempt_id == attempt_id)

    def _publish_interpretation(self, session: Session, principal: Principal, intake_id: uuid.UUID, attempt_id: str,
                                parsed: ParsedInterpretation) -> None:
        """Publish a first interpretation from an accepted attempt: revision, outcome, draft and link, or nothing."""
        intake = service.lock_intake(session, principal, str(intake_id))
        owner = str(principal.user_id)
        history = self.ledger.history(owner, str(intake_id))
        if any(v.start.attempt_id == attempt_id and v.revision_id for v in history) or any(
                r.record_type == "PromptInterpretation" for r in service.intake_rows(session, principal, intake_id)):
            session.rollback()  # already published, for example by recovery that ran first
            return
        revision_id, moment = uuid.uuid4(), service.utcnow()
        interp, routed = first_reading_records(intake.content, intake.record_id, parsed, revision_id)
        operation_id = uuid.UUID(attempt_id)
        row = service.put_record(session, principal, "PromptInterpretation", interp, operation_id, moment,
                                 record_id=revision_id, intake_id=intake.record_id)
        service.persist_routed(session, principal, intake, row, routed, operation_id, moment)
        self._link(session, owner, attempt_id, str(revision_id), parsed.questions)
        service.verify_lineage(session, principal, intake.record_id)
        session.commit()

    def _link(self, session: Session, owner: str, attempt_id: str, revision_id: str,
              questions: Sequence[OfferedQuestion]) -> None:
        bound = AttemptLedger(self.store.bound_to(session), new_id=self.ledger.new_attempt_id, now=self.ledger.now)
        bound.link_revision(owner, attempt_id, revision_id, questions_to_json(questions))

    # --- answering ----------------------------------------------------------------------------------------------

    def answer_question(self, session: Session, principal: Principal, intake_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        intake = service.get_owned(session, principal, intake_id, "IntakeRequest")
        self.reconcile(session, principal, intake.record_id)
        if body.get("answer_text") is not None:
            return self._answer_in_words(session, principal, intake.record_id, body)
        return 201, self._answer_with_choice(session, principal, intake.record_id, body)

    def _head(self, session: Session, principal: Principal, intake_id: uuid.UUID, body: dict[str, Any]):
        rows = service.intake_rows(session, principal, intake_id)
        head = service.head_interpretation(rows)
        if head is None:
            raise invalid("/", "This request has no interpretation to clarify.", "nothing_to_clarify")
        if body["previous_revision_id"] != head.content["interpretation_revision_id"]:
            raise _conflict("parent_revision_conflict",
                            "The answer refers to an older interpretation revision. Reload the request and answer again.")
        return rows, head

    def _answer_with_choice(self, session: Session, principal: Principal, intake_id: uuid.UUID,
                            body: dict[str, Any]) -> dict[str, Any]:
        intake = service.lock_intake(session, principal, str(intake_id))
        if self._open_attempt(principal, intake_id):
            session.rollback()
            raise _conflict("attempt_in_flight", "An earlier attempt for this request has not finished.")
        rows, head = self._head(session, principal, intake_id, body)
        offered = self._offered(principal, intake_id, rows, head)
        applied = apply_choice_answer(head.content["field_evidence"], offered, body["question_id"], body["choice_id"])
        if applied is None:
            raise invalid("/question_id", "This question or choice is not open for the current revision.",
                          "question_not_open")
        evidence, question_text, answer_ref = applied
        operation_id, moment = uuid.uuid4(), max(service.utcnow(), head.created_at + dt.timedelta(microseconds=1))
        self._save_revision(session, principal, intake, rows, head, evidence, question_text, answer_ref, body["question_id"],
                            head.content["meaning_status"], head.content["evidence_readiness"], None, offered, operation_id,
                            moment, None, ())
        return service.load_bundle(session, principal, intake_id, self)

    def _save_revision(self, session: Session, principal: Principal, intake: Record, rows: list[Record], head: Record,
                       evidence: Sequence[dict[str, Any]], question_text: str, answer_ref: str, question_id: str,
                       meaning_status: str, readiness: str, missing_capability: str | None,
                       offered: Sequence[OfferedQuestion], operation_id: uuid.UUID, moment: dt.datetime,
                       attempt_id: str | None, new_questions: Sequence[OfferedQuestion]) -> None:
        revision_id = uuid.uuid4()
        book_questions = list(new_questions) if attempt_id else list(offered)
        interp, clarification, routed = reply_records(
            head.content, intake.content, intake.record_id, list(evidence), question_text, answer_ref, question_id,
            meaning_status, readiness, missing_capability, book_questions, revision_id)
        try:
            row = service.put_record(session, principal, "PromptInterpretation", interp, operation_id, moment,
                                     record_id=revision_id, intake_id=intake.record_id, predecessor_id=head.record_id)
            service.put_record(session, principal, "Clarification", clarification, operation_id, moment,
                               intake_id=intake.record_id, predecessor_id=head.record_id, interpretation_id=row.record_id)
            service.persist_routed(session, principal, intake, row, routed, operation_id, moment)
            if attempt_id:
                self._link(session, str(principal.user_id), attempt_id, str(revision_id), new_questions)
            service.verify_lineage(session, principal, intake.record_id)
            session.commit()
        except record_contract.Invalid as error:
            session.rollback()  # keep the saved reading as it was
            log.error("record refused by the contract: %s", type(error).__name__)
            if "byte" not in str(error):
                raise  # not a size problem: let it show as the failure it is
            raise invalid("/", "This answer produces a record that is too large to save.", "record_too_large") from None
        except IntegrityError as error:
            session.rollback()
            if service.constraint_name(error) == "uq_records_interpretation_successor":
                raise _conflict("parent_revision_conflict", "Another answer was saved first for this revision. "
                                                            "Reload the request.") from None
            raise

    def _answer_in_words(self, session: Session, principal: Principal, intake_id: uuid.UUID,
                         body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        intake = service.lock_intake(session, principal, str(intake_id))
        if self._open_attempt(principal, intake_id):
            session.rollback()
            raise _conflict("attempt_in_flight", "An earlier attempt for this request has not finished.")
        rows, head = self._head(session, principal, intake_id, body)
        question = self._text_question(session, principal, intake_id, rows, head, body["question_id"])
        session.commit()
        answer = ClarificationAnswer(f"reply:{uuid.uuid4()}", body["answer_text"])
        result = self.interpreter.follow_up(
            str(principal.user_id), str(intake_id), intake.content, head.content["field_evidence"], question, answer,
            previous_revision_id=head.content["interpretation_revision_id"], question_id=body["question_id"])
        return self._publish_follow_up(session, principal, intake_id, result, answer, body["question_id"], question)

    def _publish_follow_up(self, session: Session, principal: Principal, intake_id: uuid.UUID, result: InterpretResult,
                           answer: ClarificationAnswer, question_id: str, question: str) -> tuple[int, dict[str, Any]]:
        if isinstance(result, Unavailable):
            if result.reason_code in {"attempt_in_flight", "retry_target_invalid", "revision_moved", "attempt_not_recorded",
                                      "result_not_recorded"}:
                self._raise_or_record_unavailable(session, principal, intake_id, result)
            return 200, service.load_bundle(session, principal, intake_id, self)
        if isinstance(result, OutputRejected):
            return 200, service.load_bundle(session, principal, intake_id, self)
        self._publish_reply(session, principal, intake_id, result.attempt_id, result.parsed, answer, question_id, question)
        return 201, service.load_bundle(session, principal, intake_id, self)

    def _publish_reply(self, session: Session, principal: Principal, intake_id: uuid.UUID, attempt_id: str,
                       parsed: ParsedInterpretation, answer: ClarificationAnswer, question_id: str, question: str) -> bool:
        intake = service.lock_intake(session, principal, str(intake_id))
        view = self._view(principal, intake_id, attempt_id)
        rows = service.intake_rows(session, principal, intake_id)
        head = service.head_interpretation(rows)
        if view.revision_id is not None:
            session.rollback()
            return False
        if head is None or head.content["interpretation_revision_id"] != view.start.identity.previous_revision_id:
            session.rollback()
            raise _conflict("parent_revision_conflict", "The saved meaning changed while your reply was being read. "
                                                        "Reload the request and answer again.")
        moment = max(service.utcnow(), head.created_at + dt.timedelta(microseconds=1))
        self._save_revision(session, principal, intake, rows, head, list(parsed.field_evidence), question, answer.answer_ref,
                            question_id, parsed.meaning_status, parsed.evidence_readiness, parsed.missing_capability,
                            self._offered(principal, intake_id, rows, head), uuid.UUID(attempt_id), moment, attempt_id,
                            parsed.questions)
        return True

    # --- retry --------------------------------------------------------------------------------------------------

    def retry(self, session: Session, principal: Principal, intake_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        intake = service.get_owned(session, principal, intake_id, "IntakeRequest")
        self.reconcile(session, principal, intake.record_id)
        owner = str(principal.user_id)
        history = self.ledger.history(owner, str(intake.record_id))
        rows = service.intake_rows(session, principal, intake.record_id)
        head = service.head_interpretation(rows)
        head_id = head.content["interpretation_revision_id"] if head else None
        state = retry_state(history, head is not None, head_id)
        if not state.allowed:
            raise _conflict(state.reason or "retry_not_allowed", "This request cannot be retried now.")
        if body["retry_of"] != state.retry_of:
            raise _conflict("retry_target_invalid", "The attempt to retry is not the latest failed attempt of this request.")
        last = history[-1] if history else None
        if last is not None and last.start.identity.purpose == "FOLLOW_UP":
            return self._retry_reply(session, principal, intake, head, last)
        self._interpret(session, principal, intake.record_id, intake.content, retry_of=state.retry_of)
        return 201, service.load_bundle(session, principal, intake.record_id, self)

    def _retry_reply(self, session: Session, principal: Principal, intake: Record, head: Record,
                     last: AttemptView) -> tuple[int, dict[str, Any]]:
        identity = last.start.identity
        task = json.loads(identity.task_text)
        answer = ClarificationAnswer(identity.answer_ref or "", identity.answer_text or "")
        question_id = self._question_id_of(session, principal, intake.record_id, head, task)
        session.rollback()  # no transaction is open while the provider is called
        result = self.interpreter.follow_up(
            str(principal.user_id), str(intake.record_id), intake.content, head.content["field_evidence"],
            task["question"], answer, retry_of=last.start.attempt_id,
            previous_revision_id=head.content["interpretation_revision_id"], question_id=question_id)
        return self._publish_follow_up(session, principal, intake.record_id, result, answer, question_id, task["question"])

    def _question_id_of(self, session: Session, principal: Principal, intake_id: uuid.UUID, head: Record,
                        task: dict[str, Any]) -> str:
        """The identifier of the question that the saved reply answered.

        The task saved with the attempt names it. An attempt saved before that field existed names only the question
        text; then the text must match exactly one open question, and any other case stays unguessed.
        """
        saved = task.get("question_id")
        if isinstance(saved, str) and saved:
            return saved
        rows = service.intake_rows(session, principal, intake_id)
        matches = [q["question_id"] for q in self._open_for(session, principal, intake_id, rows, head)
                   if q["text"] == task["question"]]
        return matches[0] if len(matches) == 1 else f"{TEXT_QUESTION_PREFIX}{task['question']}"

    # --- questions and views ------------------------------------------------------------------------------------

    def _open_attempt(self, principal: Principal, intake_id: uuid.UUID) -> bool:
        return any(v.settlement is None for v in self.ledger.history(str(principal.user_id), str(intake_id)))

    def _offered(self, principal: Principal, intake_id: uuid.UUID, rows: list[Record], head: Record) -> list[OfferedQuestion]:
        """The questions of the nearest revision that an attempt produced, found by walking the lineage back."""
        owner = str(principal.user_id)
        linked = {v.revision_id for v in self.ledger.history(owner, str(intake_id)) if v.revision_id}
        by_id = {r.record_id: r for r in rows if r.record_type == "PromptInterpretation"}
        node: Record | None = head
        while node is not None:
            if str(node.record_id) in linked:
                return questions_from_json(self.ledger.offered_questions(owner, str(intake_id), str(node.record_id)))
            node = by_id.get(node.predecessor_record_id) if node.predecessor_record_id else None
        return []

    def _targets(self, rows: list[Record], head: Record) -> tuple[list[str], dict[str, str]]:
        outcomes = [r for r in rows if r.record_type == "Outcome" and r.interpretation_record_id == head.record_id]
        if not outcomes or outcomes[-1].content["outcome"] != "NEEDS_CLARIFICATION":
            return [], {}
        findings = outcomes[-1].content["findings"]
        return [f["path"].rsplit("/", 1)[1] for f in findings], {f["path"].rsplit("/", 1)[1]: f["detail"] for f in findings}

    def _open_for(self, session: Session, principal: Principal, intake_id: uuid.UUID, rows: list[Record],
                  head: Record) -> list[dict[str, Any]]:
        targets, prompts = self._targets(rows, head)
        evidence = head.content["field_evidence"]
        offered = self._offered(principal, intake_id, rows, head)
        questions = open_questions(offered, evidence, targets)
        asked = {q["field_name"] for q in questions if q["kind"] == "CHOICE"}
        by_name = {i["field_name"]: i for i in evidence}
        for name in targets:
            item = by_name.get(name)
            pending = item is not None and item.get("adoption") == "PENDING"
            if name not in asked and not pending:
                questions.insert(len([q for q in questions if q["kind"] != "ADOPT"]), {
                    "question_id": f"{TEXT_QUESTION_PREFIX}{name}", "kind": "TEXT", "field_name": name,
                    "text": prompts[name], "options": []})
        return questions

    def _text_question(self, session: Session, principal: Principal, intake_id: uuid.UUID, rows: list[Record], head: Record,
                       question_id: str) -> str:
        for question in self._open_for(session, principal, intake_id, rows, head):
            if question["question_id"] == question_id and question["kind"] in {"CHOICE", "TEXT"}:
                return question["text"]
        raise invalid("/question_id", "This question is not open for the current revision, or it needs a listed choice.",
                      "question_not_open")

    def questions(self, session: Session, principal: Principal, intake_id: uuid.UUID, rows: list[Record], head: Record,
                  head_outcome: Record | None) -> list[dict[str, Any]]:
        if head_outcome is None or head_outcome.content["outcome"] != "NEEDS_CLARIFICATION":
            return []
        return self._open_for(session, principal, intake_id, rows, head)

    def attempt_state(self, principal: Principal, intake_id: uuid.UUID, head: Record | None) -> dict[str, Any]:
        owner, iid = str(principal.user_id), str(intake_id)
        history = self.ledger.history(owner, iid)
        head_id = head.content["interpretation_revision_id"] if head else None
        state = retry_state(history, head is not None, head_id)
        reply = None
        if history and history[-1].start.identity.purpose == "FOLLOW_UP" and history[-1].revision_id is None \
                and history[-1].settlement is None and history[-1].start.identity.previous_revision_id == head_id:
            reply = {"state": "UNFINISHED", "reason_code": None, "attempt_id": history[-1].start.attempt_id}
        elif history and history[-1].start.identity.purpose == "FOLLOW_UP" and history[-1].revision_id is None \
                and history[-1].settlement is not None and history[-1].start.identity.previous_revision_id == head_id:
            last = history[-1]
            parse = last.settlement.parse_result  # type: ignore[union-attr]
            reply = {"state": "REJECTED" if parse.startswith("REJECTED:") else
                     ("UNCERTAIN" if last.status in UNCERTAIN else
                      ("PENDING_SAVE" if parse == "ACCEPTED" else "FAILED")),
                     "reason_code": parse.removeprefix("REJECTED:") if parse.startswith("REJECTED:") else None,
                     "attempt_id": last.start.attempt_id}
        return {"attempts": [public_attempt(v) for v in history],
                "late_results": [self._public_late(o) for o in self.ledger.late_results(owner, iid)],
                "retry": {"allowed": state.allowed, "retry_of": state.retry_of, "reason": state.reason},
                "reply": reply}

    @staticmethod
    def _public_late(late: Any) -> dict[str, Any]:
        return {"observation_id": late.observation_id, "attempt_id": late.attempt_id,
                "observed_at": record_contract.utc_string(late.observed_at), "status": late.status,
                "response_sha256": late.response_sha256, "authoritative": False,
                "usage": {"source": late.usage.source, "input_tokens": late.usage.input_tokens,
                          "output_tokens": late.usage.output_tokens, "total_tokens": late.usage.total_tokens}}

    # --- the saved-requests list ------------------------------------------------------------------------------------

    def list_requests(self, session: Session, principal: Principal, limit: int = 50) -> tuple[list[dict[str, Any]], bool]:
        """The saved-requests list with the stored facts about each request's latest attempt.

        The list tag is chosen from these facts by the same function as the request page, so a request that was never
        read, is unfinished, was read but not saved, or failed never shows the outcome of an older attempt.
        """
        rows, has_more = service.list_requests(session, principal, limit)
        if not rows:
            return rows, has_more
        ids = [uuid.UUID(r["intake_record_id"]) for r in rows]
        interpreted = set(session.execute(select(Record.intake_record_id).where(
            Record.owner_id == principal.user_id, Record.record_type == "PromptInterpretation",
            Record.intake_record_id.in_(ids))).scalars())
        outcomes: dict[uuid.UUID, list[tuple[uuid.UUID, str | None]]] = {}
        for outcome in session.execute(select(Record).where(
                Record.owner_id == principal.user_id, Record.record_type == "Outcome",
                Record.intake_record_id.in_(ids)).order_by(Record.seq)).scalars():
            findings = outcome.content.get("findings") or []
            outcomes.setdefault(outcome.intake_record_id, []).append(  # type: ignore[arg-type]
                (outcome.operation_id, findings[0]["code"] if findings else None))
        owner = str(principal.user_id)
        for row, intake_id in zip(rows, ids):
            history = self.ledger.history(owner, str(intake_id))
            last = history[-1] if history else None
            mine = outcomes.get(intake_id, [])
            row["reading"] = {
                "has_interpretation": intake_id in interpreted,
                "outcome_present": row["outcome"] is not None,
                "last_attempt": None if last is None else {
                    "attempt_id": last.start.attempt_id, "status": last.status,
                    "parse_result": last.settlement.parse_result if last.settlement else None},
                "last_covered": last is not None and any(op == uuid.UUID(last.start.attempt_id) for op, _ in mine),
                "retry_allowed": retry_state(history, intake_id in interpreted, None).allowed}
            row["outcome_code"] = mine[-1][1] if mine else None
        return rows, has_more

    # --- recovery -----------------------------------------------------------------------------------------------

    def reconcile(self, session: Session, principal: Principal, intake_id: uuid.UUID) -> None:
        """Close attempts that are proved abandoned, then publish saved accepted results. No model is called."""
        owner, iid = str(principal.user_id), str(intake_id)
        self.ledger.interrupt_abandoned(owner, iid, lambda start: self.guard.is_abandoned(start.attempt_id))
        for view in self.ledger.unpublished_results(owner, iid):
            try:
                self._recover(session, principal, intake_id, view)
            except Exception as error:  # noqa: BLE001 - one bad saved result must not block the request or other requests
                session.rollback()
                log.error("recovery of an accepted attempt failed: %s", type(error).__name__)
        try:
            self._repair_failure_outcome(session, principal, intake_id)
        except Exception as error:  # noqa: BLE001 - a persistent error here must not block an answer or a retry
            session.rollback()
            log.error("saving a missing failure outcome failed: %s", type(error).__name__)

    def _repair_failure_outcome(self, session: Session, principal: Principal, intake_id: uuid.UUID) -> None:
        """Save the system outcome of a first interpretation that settled as a failure but never got its outcome.

        The settlement and the outcome are two commits. A crash between them leaves a settled failure with no outcome,
        and nothing else would ever write it. Only the latest attempt counts, and only while no revision exists.
        """
        rows = service.intake_rows(session, principal, intake_id)
        history = self.ledger.history(str(principal.user_id), str(intake_id))
        if not history or any(r.record_type == "PromptInterpretation" for r in rows):
            return
        last = history[-1]
        settled = last.settlement
        if last.start.identity.purpose != "INTERPRET" or settled is None or (
                settled.status == "COMPLETED" and settled.parse_result == "ACCEPTED"):
            return
        code, detail, retry = failure_for(settled.status, settled.parse_result)
        self._record_failure(session, principal, intake_id, last.start.attempt_id, code, detail, retry)

    def _recover(self, session: Session, principal: Principal, intake_id: uuid.UUID, view: AttemptView) -> None:
        rows = service.intake_rows(session, principal, intake_id)
        intake = rows[0].content
        head = service.head_interpretation(rows)
        if view.start.identity.purpose == "INTERPRET":
            if head is not None:
                return
            parsed = self.interpreter.reparse(view, intake)
            if isinstance(parsed, ParsedInterpretation):
                self._publish_interpretation(session, principal, intake_id, view.start.attempt_id, parsed)
            else:
                log.error("saved accepted answer rejected by the current rules: %s", parsed.reason_code)
            return
        identity = view.start.identity
        if head is None or head.content["interpretation_revision_id"] != identity.previous_revision_id:
            return  # the meaning moved on; this saved result stays as evidence and is not published
        task = json.loads(identity.task_text)
        answer = ClarificationAnswer(identity.answer_ref or "", identity.answer_text or "")
        parsed = self.interpreter.reparse(view, intake, head.content["field_evidence"], answer)
        if isinstance(parsed, ParsedInterpretation):
            question_id = self._question_id_of(session, principal, intake_id, head, task)
            self._publish_reply(session, principal, intake_id, view.start.attempt_id, parsed, answer, question_id,
                                task["question"])
        else:
            log.error("saved accepted reply rejected by the current rules: %s", parsed.reason_code)

    def recover_all(self) -> int:
        """Startup recovery for every request with unfinished or unpublished attempts. Returns requests visited."""
        with self._session_factory() as session:
            pairs = session.execute(text(
                "select distinct a.owner_id, a.intake_record_id from interpretation_attempts a "
                "left join interpretation_settlements s on s.attempt_id = a.attempt_id "
                "left join interpretation_attempt_links l on l.attempt_id = a.attempt_id "
                "where s.attempt_id is null or (s.status = 'COMPLETED' and s.parse_result = 'ACCEPTED' "
                "and l.attempt_id is null) "
                "union select a.owner_id, a.intake_record_id from interpretation_attempts a "
                "join interpretation_settlements s on s.attempt_id = a.attempt_id "
                "where a.purpose = 'INTERPRET' and not (s.status = 'COMPLETED' and s.parse_result = 'ACCEPTED') "
                "and not exists (select 1 from records r where r.owner_id = a.owner_id and r.operation_id = a.attempt_id "
                "and r.record_type = 'Outcome') "
                "and not exists (select 1 from records r where r.owner_id = a.owner_id "
                "and r.intake_record_id = a.intake_record_id and r.record_type = 'PromptInterpretation')")).all()
        for owner_id, intake_id in pairs:
            try:
                with self._session_factory() as session:
                    self.reconcile(session, Principal(owner_id, "recovery"), intake_id)
            except Exception as error:  # noqa: BLE001 - recovery of one request must not stop the others
                log.error("recovery of one request failed: %s", type(error).__name__)
        return len(pairs)
