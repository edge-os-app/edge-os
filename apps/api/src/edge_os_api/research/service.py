"""Owner-scoped persistence and the first Research path workflow.

Every query takes the owner from the verified `Principal`. Another owner's record is indistinguishable from a
missing one (404). Records are append-only; a later state is a new record.
"""

from __future__ import annotations

import copy
import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.strategies import compiler as strategy_compiler
from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding, invalid, not_found, service_unavailable
from edge_os_api.research.fixture_interpreter import FixtureInterpreter, find_scenario, open_questions
from edge_os_api.records.models import IdempotencyRecord, Record, StrategyRevision
from edge_os_api.research.outcome_router import Routed, route

INTERPRETER = FixtureInterpreter()
SCHEMA_VERSIONS: dict[str, str] = record_contract.CONTRACT["schema_versions"]


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_uuid(value: str) -> uuid.UUID | None:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
    return parsed if str(parsed) == value.lower() else None


def envelope_of(row: Record) -> dict[str, Any]:
    return {"schema_version": row.schema_version, "record_type": row.record_type, "record_id": str(row.record_id),
            "owner_id": str(row.owner_id), "operation_id": str(row.operation_id),
            "created_at": record_contract.utc_string(row.created_at), "content": row.content}


def put_record(session: Session, principal: Principal, record_type: str, content: dict[str, Any],
               operation_id: uuid.UUID, created_at: dt.datetime, *, record_id: uuid.UUID | None = None,
               intake_id: uuid.UUID | None = None, predecessor_id: uuid.UUID | None = None,
               interpretation_id: uuid.UUID | None = None) -> Record:
    record_id = record_id or uuid.uuid4()
    envelope = {"schema_version": SCHEMA_VERSIONS[record_type], "record_type": record_type,
                "record_id": str(record_id), "owner_id": str(principal.user_id), "operation_id": str(operation_id),
                "created_at": record_contract.utc_string(created_at), "content": content}
    record_contract.validate_envelope(envelope)
    row = Record(record_id=record_id, owner_id=principal.user_id, record_type=record_type,
                 schema_version=SCHEMA_VERSIONS[record_type], operation_id=operation_id, created_at=created_at,
                 content=content, intake_record_id=intake_id, predecessor_record_id=predecessor_id,
                 interpretation_record_id=interpretation_id)
    session.add(row)
    session.flush()
    return row


def get_owned(session: Session, principal: Principal, record_id: str, record_type: str | None = None) -> Record:
    parsed = parse_uuid(record_id)
    if parsed is None:
        raise not_found()
    stmt = select(Record).where(Record.owner_id == principal.user_id, Record.record_id == parsed)
    if record_type:
        stmt = stmt.where(Record.record_type == record_type)
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


def lock_intake(session: Session, principal: Principal, intake_id: str) -> Record:
    """Lock one owner-scoped intake row for the complete head-read/write transaction."""
    parsed = parse_uuid(intake_id)
    if parsed is None:
        raise not_found()
    row = session.execute(select(Record).where(
        Record.owner_id == principal.user_id,
        Record.record_id == parsed,
        Record.record_type == "IntakeRequest",
    ).execution_options(populate_existing=True).with_for_update(of=Record)).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


def intake_rows(session: Session, principal: Principal, intake_id: uuid.UUID) -> list[Record]:
    return list(session.execute(select(Record).where(
        Record.owner_id == principal.user_id,
        (Record.record_id == intake_id) | (Record.intake_record_id == intake_id)).order_by(Record.seq)).scalars())


def verify_lineage(session: Session, principal: Principal, intake_id: uuid.UUID) -> None:
    """Re-validate the whole saved lineage with the frozen P02 bundle checker before committing."""
    try:
        record_contract.validate_record_bundle([envelope_of(row) for row in intake_rows(session, principal, intake_id)])
    except (record_contract.Invalid, KeyError, TypeError) as error:
        raise AppError(500, "VALIDATION", "INVALID_INPUT", "validation_error",
                       [finding("lineage_invalid", "/", f"Saved lineage failed validation: {error}")]) from None


def bind_revision(evidence: list[dict[str, Any]], revision_id: str) -> list[dict[str, Any]]:
    bound = copy.deepcopy(evidence)
    for item in bound:
        item["interpretation_revision"] = revision_id
    return bound


def outcome_content(operation_id: uuid.UUID, intake_id: uuid.UUID, routed: Routed) -> dict[str, Any]:
    return {"operation_id": str(operation_id), "stage": routed.stage, "outcome": routed.outcome,
            "code": routed.code, "findings": routed.findings, "retry": routed.retry,
            "intake_record_id": str(intake_id)}


def persist_routed(session: Session, principal: Principal, intake_row: Record, interp_row: Record | None,
                   routed: Routed, operation_id: uuid.UUID, moment: dt.datetime) -> None:
    content = outcome_content(operation_id, intake_row.record_id, routed)
    put_record(session, principal, "Outcome", content, operation_id, moment, intake_id=intake_row.record_id,
               interpretation_id=interp_row.record_id if interp_row else None)
    if routed.outcome == "COMPILED" and interp_row is not None and routed.strategy is not None:
        draft_id = uuid.uuid4()
        draft = {"draft_id": str(draft_id), "original_request": intake_row.content["original_request"],
                 "interpretation_revision_id": interp_row.content["interpretation_revision_id"],
                 "source_syntax": routed.strategy, "validation_findings": [], "state": "DRAFT",
                 "published_revision_id": None, "strategy_id": routed.strategy["strategy_id"],
                 "base_revision_id": None}
        put_record(session, principal, "StrategyDraft", draft, operation_id, moment, record_id=draft_id,
                   intake_id=intake_row.record_id, interpretation_id=interp_row.record_id)


def strategy_id_for(intake_id: uuid.UUID) -> str:
    return f"strategy-{intake_id}"


def save_intake(session: Session, principal: Principal, body: dict[str, Any], operation_id: uuid.UUID | None = None,
                moment: dt.datetime | None = None) -> Record:
    """Validate and add the request as written. The caller commits."""
    content: dict[str, Any] = {"original_request": body["original_request"], "restrictions": list(body["restrictions"]),
                               "requested_job": body["requested_job"], "input_class": body["input_class"]}
    if body.get("declared_market") is not None:
        content["declared_market"] = body["declared_market"]
    try:
        record_contract.validate_record("IntakeRequest", content)
    except record_contract.Invalid as error:
        detail = ("Text must use composed Unicode characters (NFC). Re-type or paste it as plain text, for example "
                  "so that an accented letter is one character.") if "NFC" in str(error) else str(error)
        raise invalid("/", detail) from None
    return put_record(session, principal, "IntakeRequest", content, operation_id or uuid.uuid4(), moment or utcnow())


def create_request(session: Session, principal: Principal, body: dict[str, Any]) -> dict[str, Any]:
    operation_id, moment = uuid.uuid4(), utcnow()
    intake = save_intake(session, principal, body, operation_id, moment)
    content = intake.content
    proposal = INTERPRETER.interpret(content)
    if proposal is None:
        routed = Routed("INVALID_INPUT", "INTERPRETATION", [finding(
            "interpreter_no_scripted_response", "/original_request",
            "The fixture interpreter has no scripted response for this request, input class and job. "
            "The request is saved as written. This is not a verdict on the idea.")])
        persist_routed(session, principal, intake, None, routed, operation_id, moment)
    else:
        revision_id = uuid.uuid4()
        interp_content = {
            "intake_record_id": str(intake.record_id), "interpretation_revision_id": str(revision_id),
            "input_class": content["input_class"], "requested_job": content["requested_job"],
            "field_evidence": bind_revision(proposal["field_evidence"], str(revision_id)),
            "clarification_history": [], "preserved_restrictions": list(content["restrictions"]),
            "meaning_status": proposal["meaning_status"], "syntax_status": proposal["syntax_status"],
            "evidence_readiness": proposal["evidence_readiness"]}
        routed = route(content, interp_content, INTERPRETER, proposal["scenario"].missing_capability,
                       strategy_id_for(intake.record_id))
        interp = put_record(session, principal, "PromptInterpretation", interp_content, operation_id, moment,
                            record_id=revision_id, intake_id=intake.record_id)
        persist_routed(session, principal, intake, interp, routed, operation_id, moment)
    verify_lineage(session, principal, intake.record_id)
    session.commit()
    return load_bundle(session, principal, intake.record_id)


def head_interpretation(rows: list[Record]) -> Record | None:
    interps = [r for r in rows if r.record_type == "PromptInterpretation"]
    predecessors = {r.predecessor_record_id for r in interps if r.predecessor_record_id}
    heads = [r for r in interps if r.record_id not in predecessors]
    return heads[-1] if heads else None


def answer_question(session: Session, principal: Principal, intake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    intake = lock_intake(session, principal, intake_id)
    rows = intake_rows(session, principal, intake.record_id)
    head = head_interpretation(rows)
    if head is None:
        raise invalid("/", "This request has no interpretation to clarify.", "nothing_to_clarify")
    if body["previous_revision_id"] != head.content["interpretation_revision_id"]:
        raise AppError(409, "VALIDATION", "CONFLICTED", "parent_revision_conflict", [finding(
            "parent_revision_conflict", "/previous_revision_id",
            "The answer refers to an older interpretation revision. Reload the request and answer again.")])
    applied = INTERPRETER.apply_answer(intake.content, head.content["field_evidence"], body["question_id"],
                                       body["choice_id"])
    if applied is None:
        raise invalid("/question_id", "This question or choice is not open for the current revision.", "question_not_open")
    evidence, question_text, answer_ref = applied
    operation_id = uuid.uuid4()
    moment = max(utcnow(), head.created_at + dt.timedelta(microseconds=1))
    revision_id = uuid.uuid4()
    old = {i["field_name"]: {k: v for k, v in i.items() if k != "interpretation_revision"}
           for i in head.content["field_evidence"]}
    new = {i["field_name"]: {k: v for k, v in i.items() if k != "interpretation_revision"} for i in evidence}
    changed = sorted(name for name in set(old) | set(new) if old.get(name) != new.get(name))
    clarification = {"previous_revision_id": head.content["interpretation_revision_id"],
                     "question_id": body["question_id"], "question": question_text, "answer_ref": answer_ref,
                     "changed_fields": changed, "preserved_restrictions": list(head.content["preserved_restrictions"]),
                     "resulting_revision_id": str(revision_id)}
    interp_content = copy.deepcopy(head.content)
    interp_content.update({"interpretation_revision_id": str(revision_id),
                           "field_evidence": bind_revision(evidence, str(revision_id)),
                           "clarification_history": [clarification]})
    scenario = find_scenario(intake.content)
    routed = route(intake.content, interp_content, INTERPRETER, scenario.missing_capability if scenario else None,
                   strategy_id_for(intake.record_id))
    try:
        interp = put_record(session, principal, "PromptInterpretation", interp_content, operation_id, moment,
                            record_id=revision_id, intake_id=intake.record_id, predecessor_id=head.record_id)
        put_record(session, principal, "Clarification", clarification, operation_id, moment,
                   intake_id=intake.record_id, predecessor_id=head.record_id, interpretation_id=interp.record_id)
        persist_routed(session, principal, intake, interp, routed, operation_id, moment)
        verify_lineage(session, principal, intake.record_id)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if constraint_name(error) == "uq_records_interpretation_successor":
            raise AppError(409, "VALIDATION", "CONFLICTED", "parent_revision_conflict", [finding(
                "parent_revision_conflict", "/previous_revision_id",
                "Another answer was saved first for this revision. Reload the request.")]) from None
        raise
    return load_bundle(session, principal, intake.record_id)


def constraint_name(error: DBAPIError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def revision_summary(row: StrategyRevision) -> dict[str, Any]:
    return {"revision_id": str(row.revision_id), "strategy_id": row.strategy_id,
            "parent_revision_id": str(row.parent_revision_id) if row.parent_revision_id else None,
            "publication_id": str(row.publication_id), "operation_id": str(row.operation_id),
            "content_sha256": row.content_sha256, "manifest_sha256": row.manifest_sha256,
            "created_at": record_contract.utc_string(row.created_at)}


def validate_strategy_version(strategy: object) -> None:
    """Validate immutable revisions with the contract that owns their bytes."""
    if not isinstance(strategy, dict):
        raise strategy_compiler.CompilerError("invalid_strategy", "/", "A strategy must be an object.")
    version = strategy.get("schema_version")
    if version == record_contract.CONTRACT["identity"]["strategy_schema"]:
        record_contract.validate_strategy(strategy)
    elif version == strategy_compiler.CONTRACT["identity"]["strategy_schema"]:
        strategy_compiler.validate_strategy(strategy)
    else:
        raise strategy_compiler.CompilerError("unsupported_strategy_version", "/schema_version",
                                "The strategy revision uses an unsupported schema version.")


def load_bundle(session: Session, principal: Principal, intake_id: uuid.UUID, hermes: Any = None) -> dict[str, Any]:
    rows = intake_rows(session, principal, intake_id)
    if not rows or rows[0].record_id != intake_id or rows[0].record_type != "IntakeRequest":
        raise not_found()
    by_type: dict[str, list[Record]] = {}
    for row in rows:
        by_type.setdefault(row.record_type, []).append(row)
    interps = by_type.get("PromptInterpretation", [])
    outcomes = by_type.get("Outcome", [])
    head = head_interpretation(rows)
    head_outcome = None
    if outcomes:
        head_outcome = next((o for o in reversed(outcomes) if head is not None
                             and o.interpretation_record_id == head.record_id), outcomes[-1])
    drafts = by_type.get("StrategyDraft", [])
    revisions = list(session.execute(select(StrategyRevision).where(
        StrategyRevision.owner_id == principal.user_id,
        StrategyRevision.draft_record_id.in_([d.record_id for d in drafts] or [uuid.UUID(int=0)]))
        .order_by(StrategyRevision.created_at)).scalars())
    questions: list[dict[str, Any]] = []
    if hermes is not None:
        if head is not None:
            questions = hermes.questions(session, principal, intake_id, rows, head, head_outcome)
    elif head is not None and head_outcome is not None and head_outcome.content["outcome"] == "NEEDS_CLARIFICATION":
        targets = [f["path"].rsplit("/", 1)[1] for f in head_outcome.content["findings"]]
        questions = open_questions(rows[0].content, INTERPRETER, head.content["field_evidence"], targets)
    head_draft = None
    if head is not None:
        head_draft = next((d for d in reversed(drafts) if d.interpretation_record_id == head.record_id), None)
    attempts = hermes.attempt_state(principal, intake_id, head) if hermes is not None else None
    return {
        "interpreter": hermes.label() if hermes is not None else INTERPRETER.label(),
        "attempts": attempts["attempts"] if attempts else [],
        "late_results": attempts["late_results"] if attempts else [],
        "intake": envelope_of(rows[0]),
        "interpretations": [envelope_of(r) for r in interps],
        "clarifications": [envelope_of(r) for r in by_type.get("Clarification", [])],
        "outcomes": [{"interpretation_revision_id": next(
            (i.content["interpretation_revision_id"] for i in interps if i.record_id == o.interpretation_record_id),
            None), "record": envelope_of(o)} for o in outcomes],
        "drafts": [envelope_of(r) for r in drafts],
        "publications": [envelope_of(r) for r in by_type.get("PublicationResult", [])],
        "revisions": [revision_summary(r) for r in revisions],
        "head": {
            "interpretation_revision_id": head.content["interpretation_revision_id"] if head else None,
            "outcome": head_outcome.content["outcome"] if head_outcome else None,
            "questions": questions,
            "draft_id": str(head_draft.record_id) if head_draft else None,
            "strategy_id": head_draft.content["strategy_id"] if head_draft else None,
            "retry": attempts["retry"] if attempts else {"allowed": False, "retry_of": None, "reason": "no_interpreter_attempts"},
            "reply": attempts["reply"] if attempts else None,
        },
    }


def list_requests(session: Session, principal: Principal, limit: int = 50) -> tuple[list[dict[str, Any]], bool]:
    fetched = list(session.execute(select(Record).where(
        Record.owner_id == principal.user_id, Record.record_type == "IntakeRequest")
        .order_by(Record.seq.desc()).limit(limit + 1)).scalars())
    has_more, intakes = len(fetched) > limit, fetched[:limit]
    ids = [i.record_id for i in intakes]
    if not ids:
        return [], False
    outcomes = session.execute(select(Record).where(
        Record.owner_id == principal.user_id, Record.record_type == "Outcome", Record.intake_record_id.in_(ids))
        .order_by(Record.seq)).scalars()
    latest: dict[uuid.UUID, Record] = {}
    for row in outcomes:
        latest[row.intake_record_id] = row  # type: ignore[index]
    published = {r.intake_record_id for r in session.execute(select(Record).where(
        Record.owner_id == principal.user_id, Record.record_type == "PublicationResult",
        Record.intake_record_id.in_(ids))).scalars()}
    return [{"intake_record_id": str(i.record_id), "created_at": record_contract.utc_string(i.created_at),
             "original_request": i.content["original_request"], "requested_job": i.content["requested_job"],
             "input_class": i.content["input_class"],
             "outcome": latest[i.record_id].content["outcome"] if i.record_id in latest else None,
             "published": i.record_id in published} for i in intakes], has_more


def publish(session: Session, principal: Principal, strategy_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    path = f"/v1/strategies/{strategy_id}/revisions"
    strategy = body["strategy"]
    try:
        validate_strategy_version(strategy)
    except strategy_compiler.CompilerError as error:
        path = "/strategy" + (error.path if error.path != "/" else "")
        raise invalid(path, error.detail, error.code) from None
    except (record_contract.Invalid, KeyError, TypeError) as error:
        raise invalid("/strategy", f"The strategy is not valid: {error}") from None
    if strategy["strategy_id"] != strategy_id:
        raise invalid("/strategy/strategy_id", "The body strategy ID must equal the path strategy ID.")
    canonical = record_contract.canonical_bytes(strategy).decode("utf-8")
    fingerprint = record_contract.sha256_hex({
        "owner_id": str(principal.user_id), "method": "POST", "path": path,
        "expected_parent_revision_id": body["expected_parent_revision_id"], "draft_id": body["draft_id"],
        "canonical_strategy_bytes": canonical})
    for _ in range(3):
        outcome = _publish_once(session, principal, strategy_id, path, body, strategy, canonical, fingerprint)
        if outcome is not None:
            return outcome
    raise service_unavailable()


def _lookup_idempotency(session: Session, principal: Principal, path: str, key: str) -> IdempotencyRecord | None:
    return session.execute(select(IdempotencyRecord).where(
        IdempotencyRecord.owner_id == principal.user_id, IdempotencyRecord.method == "POST",
        IdempotencyRecord.path == path, IdempotencyRecord.idempotency_key == key)).scalar_one_or_none()


def _conflict(code: str, detail: str) -> AppError:
    return AppError(409, "PUBLICATION", "CONFLICTED", code, [finding(code, "/", detail)], "NOT_RETRYABLE")


def _publish_once(session: Session, principal: Principal, strategy_id: str, path: str, body: dict[str, Any],
                  strategy: dict[str, Any], canonical: str, fingerprint: str) -> tuple[int, dict[str, Any]] | None:
    existing = _lookup_idempotency(session, principal, path, body["idempotency_key"])
    if existing is not None:
        session.rollback()
        if existing.fingerprint != fingerprint:
            raise _conflict("idempotency_key_reused", "This idempotency key was used for a different request.")
        return 200, existing.response

    draft_uuid = parse_uuid(body["draft_id"])
    draft = None
    if draft_uuid is not None:
        draft = session.execute(select(Record).where(
            Record.owner_id == principal.user_id, Record.record_id == draft_uuid,
            Record.record_type == "StrategyDraft")).scalar_one_or_none()
    if draft is None:
        raise not_found("draft")
    content = draft.content
    if content["strategy_id"] != strategy_id or content["base_revision_id"] != body["expected_parent_revision_id"]:
        raise _conflict("parent_revision_conflict", "The draft does not bind to this strategy and parent revision.")
    try:
        validate_strategy_version(content["source_syntax"])
    except strategy_compiler.CompilerError as error:
        path = "/strategy" + (error.path if error.path != "/" else "")
        raise invalid(path, error.detail, error.code) from None
    except (record_contract.Invalid, KeyError, TypeError) as error:
        raise invalid("/strategy", f"The saved strategy is not valid: {error}") from None
    if record_contract.canonical_bytes(content["source_syntax"]).decode("utf-8") != canonical:
        raise invalid("/strategy", "The strategy differs from the adopted meaning saved in the draft.",
                      "strategy_differs_from_draft")
    parent_id = parse_uuid(body["expected_parent_revision_id"]) if body["expected_parent_revision_id"] else None
    if body["expected_parent_revision_id"] is not None:
        parent = None if parent_id is None else session.execute(select(StrategyRevision).where(
            StrategyRevision.owner_id == principal.user_id, StrategyRevision.revision_id == parent_id,
            StrategyRevision.strategy_id == strategy_id)).scalar_one_or_none()
        if parent is None:
            raise _conflict("parent_revision_conflict", "The expected parent revision does not exist for this strategy.")

    revision_id, publication_id = uuid.uuid4(), uuid.uuid4()
    moment = utcnow()
    result = {"operation_id": body["operation_id"], "stage": "PUBLICATION", "outcome": "PUBLISHED",
              "code": "published", "findings": [], "retry": "SAFE_SAME_KEY", "publication_id": str(publication_id),
              "revision_id": str(revision_id), "content_sha256": record_contract.sha256_hex(strategy),
              "manifest_sha256": record_contract.sha256_hex(strategy["semantic_manifest"]), "created_at": record_contract.utc_string(moment)}
    record_contract.validate_record("PublicationResult", result)
    try:
        inserted = session.execute(pg_insert(IdempotencyRecord).values(
            owner_id=principal.user_id, method="POST", path=path, idempotency_key=body["idempotency_key"],
            fingerprint=fingerprint, revision_id=revision_id, response=result)
            .on_conflict_do_nothing().returning(IdempotencyRecord.revision_id)).first()
        if inserted is None:
            session.rollback()
            return None  # a concurrent request with this key committed first: replay or conflict on retry
        session.add(StrategyRevision(
            revision_id=revision_id, owner_id=principal.user_id, strategy_id=strategy_id, parent_revision_id=parent_id,
            draft_record_id=draft.record_id, publication_id=publication_id, operation_id=uuid.UUID(body["operation_id"]),
            content_sha256=result["content_sha256"], manifest_sha256=result["manifest_sha256"],
            strategy_canonical=canonical, created_at=moment))
        session.flush()
        put_record(session, principal, "PublicationResult", result, uuid.UUID(body["operation_id"]), moment,
                   intake_id=draft.intake_record_id)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        name = constraint_name(error)
        if name in {"uq_revision_root_slot", "fk_revision_parent"}:
            raise _conflict("parent_revision_conflict", "Another revision already holds this parent slot.") from None
        if name == "uq_revision_owner_operation":
            raise _conflict("idempotency_key_reused", "This operation ID was already used by another request.") from None
        raise
    return 201, result


def get_revision(session: Session, principal: Principal, strategy_id: str, revision_id: str) -> dict[str, Any]:
    parsed = parse_uuid(revision_id)
    row = None
    if parsed is not None:
        row = session.execute(select(StrategyRevision).where(
            StrategyRevision.owner_id == principal.user_id, StrategyRevision.revision_id == parsed,
            StrategyRevision.strategy_id == strategy_id)).scalar_one_or_none()
    if row is None:
        raise not_found("revision")
    strategy = record_contract.strict_loads(row.strategy_canonical)
    try:
        validate_strategy_version(strategy)
    except (strategy_compiler.CompilerError, record_contract.Invalid, KeyError, TypeError):
        raise AppError(500, "READ", "UNAVAILABLE", "service_unavailable",
                       [finding("stored_strategy_invalid", "/strategy", "The saved revision failed P06 validation.")]) from None
    recomputed = record_contract.sha256_hex(strategy)
    manifest_hash = record_contract.sha256_hex(strategy["semantic_manifest"])
    return {**revision_summary(row), "strategy": strategy, "stored_hash_matches_content": recomputed == row.content_sha256,
            "stored_manifest_hash_matches_content": manifest_hash == row.manifest_sha256}


def get_operation(session: Session, principal: Principal, operation_id: str) -> dict[str, Any]:
    parsed = parse_uuid(operation_id)
    row = None
    if parsed is not None:
        row = session.execute(select(Record).where(
            Record.owner_id == principal.user_id, Record.operation_id == parsed,
            Record.record_type == "PublicationResult")).scalar_one_or_none()
    if row is None:
        raise not_found("operation")
    return row.content
