"""The records that publishing an accepted answer writes, built in one place.

Publication stores a `PromptInterpretation`, a routed `Outcome` and, for a reply, a `Clarification`. The workflow builds
them here to store them. The adapter builds the very same records here, with placeholder identifiers, and validates them
BEFORE it accepts an answer. An answer that could not be published is then a saved rejection that the user may retry. It
is never an accepted attempt that fails later and leaves the request without an outcome.

There is one builder for each record set, so the check and the storage cannot drift apart.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research import service
from edge_os_api.research.interpretation_response import (
    ClarificationAnswer, OfferedQuestion, ParsedInterpretation, Rejection,
)
from edge_os_api.research.outcome_router import Routed, route

__all__ = ["OfferedBook", "RecordPublicationCheck", "UNPUBLISHABLE", "first_reading_records", "questions_to_json",
           "reply_records"]

UNPUBLISHABLE = "unpublishable_response"
DRAFT_OVERHEAD_BYTES = 4096  # the strategy draft's own fields and the strategy's fixed parts, with room to spare
MAX_RECORD_BYTES = record_contract.CONTRACT["limits"]["input_bytes"]
MAX_OFFERED_BYTES = 32 * 1024  # the questions that an accepted answer offers are saved with its link
DRY_RUN_REQUEST = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
DRY_RUN_REVISION = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
DRY_RUN_PREVIOUS = uuid.UUID("00000000-0000-4000-8000-0000000000a3")
DRY_RUN_OPERATION = uuid.UUID("00000000-0000-4000-8000-0000000000a4")


class OfferedBook:
    """The questions that the model offered, in the shape the router words its clarifications from."""

    kind = "HERMES"

    def __init__(self, offered: Sequence[OfferedQuestion]) -> None:
        self._offered = list(offered)

    def question_for(self, intake: dict[str, Any]) -> list[OfferedQuestion]:
        return list(self._offered)


def questions_to_json(questions: Sequence[OfferedQuestion]) -> list[dict[str, Any]]:
    return [{"question_id": q.question_id, "field_name": q.field_name, "text": q.text,
             "options": [{"id": o.id, "label": o.label, "value": copy.deepcopy(o.value)} for o in q.options]}
            for q in questions]


def first_reading_records(intake_content: Mapping[str, Any], request_id: uuid.UUID, parsed: ParsedInterpretation,
                          revision_id: uuid.UUID) -> tuple[dict[str, Any], Routed]:
    """The interpretation and routed outcome that the first accepted answer of a request publishes."""
    interp = {
        "intake_record_id": str(request_id), "interpretation_revision_id": str(revision_id),
        "input_class": intake_content["input_class"], "requested_job": intake_content["requested_job"],
        "field_evidence": service.bind_revision(list(parsed.field_evidence), str(revision_id)),
        "clarification_history": [], "preserved_restrictions": list(intake_content["restrictions"]),
        "meaning_status": parsed.meaning_status, "syntax_status": "VALID",
        "evidence_readiness": parsed.evidence_readiness}
    routed = route(dict(intake_content), interp, OfferedBook(parsed.questions), parsed.missing_capability,
                   service.strategy_id_for(request_id))
    return interp, routed


def reply_records(base: Mapping[str, Any], intake_content: Mapping[str, Any], request_id: uuid.UUID,
                  evidence: Sequence[dict[str, Any]], question: str, answer_ref: str, question_id: str,
                  meaning_status: str, readiness: str, missing_capability: str | None,
                  questions: Sequence[OfferedQuestion], revision_id: uuid.UUID,
                  ) -> tuple[dict[str, Any], dict[str, Any], Routed]:
    """The interpretation, clarification and routed outcome that an accepted reply publishes.

    `base` is the content of the revision that the reply answers (the head).
    """
    def strip(items: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        return {i["field_name"]: {k: v for k, v in i.items() if k != "interpretation_revision"} for i in items}

    old, new = strip(base["field_evidence"]), strip(evidence)
    changed = sorted(name for name in set(old) | set(new) if old.get(name) != new.get(name))
    clarification = {"previous_revision_id": base["interpretation_revision_id"], "question_id": question_id,
                     "question": question, "answer_ref": answer_ref, "changed_fields": changed,
                     "preserved_restrictions": list(base["preserved_restrictions"]),
                     "resulting_revision_id": str(revision_id)}
    interp = copy.deepcopy(dict(base))
    interp.update({"interpretation_revision_id": str(revision_id),
                   "field_evidence": service.bind_revision(list(evidence), str(revision_id)),
                   "clarification_history": [clarification], "meaning_status": meaning_status,
                   "evidence_readiness": readiness})
    routed = route(dict(intake_content), interp, OfferedBook(questions), missing_capability,
                   service.strategy_id_for(request_id))
    return interp, clarification, routed


def _rejection() -> Rejection:
    return Rejection(UNPUBLISHABLE, "", "The answer could not be saved as a record, so none of it was used.")


class RecordPublicationCheck:
    """Builds the exact records that publication would write, with placeholder identifiers, and validates them."""

    def first(self, intake: Mapping[str, Any], parsed: ParsedInterpretation) -> Rejection | None:
        try:
            interp, routed = first_reading_records(intake, DRY_RUN_REQUEST, parsed, DRY_RUN_REVISION)
            record_contract.validate_record("PromptInterpretation", interp)
            record_contract.validate_record("Outcome", service.outcome_content(DRY_RUN_OPERATION, DRY_RUN_REQUEST, routed))
            return self._offered(parsed) or self._room(intake, parsed)
        except Exception:  # noqa: BLE001 - whatever stops these records stops publication, so the answer is rejected
            return _rejection()

    def reply(self, intake: Mapping[str, Any], previous_evidence: Sequence[Mapping[str, Any]], question: str,
              answer: ClarificationAnswer, parsed: ParsedInterpretation) -> Rejection | None:
        try:
            base = {"intake_record_id": str(DRY_RUN_REQUEST), "interpretation_revision_id": str(DRY_RUN_PREVIOUS),
                    "input_class": intake["input_class"], "requested_job": intake["requested_job"],
                    "field_evidence": [dict(item) for item in previous_evidence], "clarification_history": [],
                    "preserved_restrictions": list(intake["restrictions"]), "meaning_status": parsed.meaning_status,
                    "syntax_status": "VALID", "evidence_readiness": parsed.evidence_readiness}
            interp, clarification, routed = reply_records(
                base, intake, DRY_RUN_REQUEST, list(parsed.field_evidence), question, answer.answer_ref,
                "dry-run-question", parsed.meaning_status, parsed.evidence_readiness, parsed.missing_capability,
                parsed.questions, DRY_RUN_REVISION)
            record_contract.validate_record("PromptInterpretation", interp)
            record_contract.validate_record("Clarification", clarification)
            record_contract.validate_record("Outcome", service.outcome_content(DRY_RUN_OPERATION, DRY_RUN_REQUEST, routed))
            return self._offered(parsed) or self._room(intake, parsed)
        except Exception:  # noqa: BLE001
            return _rejection()

    @staticmethod
    def _room(intake: Mapping[str, Any], parsed: ParsedInterpretation) -> Rejection | None:
        """Leave room for the strategy draft that adoption writes later.

        The draft holds the whole request next to a strategy built from the answer's values. The request counts at its
        canonical size: a control character costs six bytes there, so the character count says too little.
        """
        request = len(record_contract.canonical_bytes(intake["original_request"]))
        answer = len(record_contract.canonical_bytes([dict(item) for item in parsed.field_evidence]))
        # a chosen option moves its value into the evidence, and so into the strategy: count every offered value
        options = len(record_contract.canonical_bytes(questions_to_json(parsed.questions)))
        if request + answer + options + DRAFT_OVERHEAD_BYTES > MAX_RECORD_BYTES:
            return Rejection(UNPUBLISHABLE, "", "The request is long, so the answer could not be saved with room to use it. "
                                                "A shorter request leaves more room.")
        return None

    @staticmethod
    def _offered(parsed: ParsedInterpretation) -> Rejection | None:
        size = len(record_contract.canonical_bytes(questions_to_json(parsed.questions)))
        return _rejection() if size > MAX_OFFERED_BYTES else None
