"""Owner-scoped P09 run adoption, immutable execution attempts, and report retrieval."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import p02, p06
from .auth import Principal
from .effect_comparison import compare_effects, evaluate_p06_bindings, parse_utc
from .errors import AppError, finding, not_found
from .models import EffectReport, EffectRunDeclaration, EffectRunEvent, InvestigationDeclaration
from .schemas import EffectAttemptBody, EffectRunBody
from .service import get_owned, parse_uuid

SCHEMA_VERSION = "p09.effect-run-declaration/1"
REPORT_VERSION = "p09.effect-report/1"
FIXTURE_ID = "synthetic-effect-comparison/1"
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "effect_comparison" / "synthetic_effect_comparison_v1.json"
PROFILE_PATH = Path(__file__).resolve().parents[4] / "docs" / "implementation" / "EFFECT_COMPARISON_PROFILE.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _owned_run(session: Session, principal: Principal, intake_id: str, run_id: str) -> EffectRunDeclaration:
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    parsed = parse_uuid(run_id)
    row = None if parsed is None else session.execute(select(EffectRunDeclaration).where(
        EffectRunDeclaration.owner_id == principal.user_id,
        EffectRunDeclaration.intake_record_id == intake.record_id,
        EffectRunDeclaration.run_id == parsed)).scalar_one_or_none()
    if row is None:
        raise not_found("effect comparison run")
    return row


def _response(row: EffectRunDeclaration, events: list[EffectRunEvent], report: EffectReport | None = None) -> dict[str, Any]:
    return {
        "run": {"schema_version": SCHEMA_VERSION, "record_type": "EffectRunDeclaration",
                "record_id": str(row.run_id), "owner_id": str(row.owner_id),
                "p08_declaration_id": str(row.p08_declaration_id),
                "created_at": p02.utc_string(row.created_at), "content": row.content},
        "events": [{"event_id": str(item.event_id), "sequence": item.sequence,
                    "created_at": p02.utc_string(item.created_at), "content": item.content} for item in events],
        "report": None if report is None else {"schema_version": REPORT_VERSION,
                                                "record_type": "EffectReport",
                                                "record_id": str(report.report_id),
                                                "owner_id": str(report.owner_id),
                                                "created_at": p02.utc_string(report.created_at),
                                                "content": report.content},
    }


def _events(session: Session, row: EffectRunDeclaration) -> list[EffectRunEvent]:
    return list(session.execute(select(EffectRunEvent).where(
        EffectRunEvent.owner_id == row.owner_id, EffectRunEvent.run_id == row.run_id)
        .order_by(EffectRunEvent.sequence)).scalars())


def adopt_effect_run(session: Session, principal: Principal, intake_id: str,
                     p08_declaration_id: str, body: EffectRunBody) -> tuple[int, dict[str, Any]]:
    """Persist an explicit P09 binding. This operation reads no outcome data."""
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    p08_id = parse_uuid(p08_declaration_id)
    declaration = None if p08_id is None else session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == principal.user_id,
        InvestigationDeclaration.intake_record_id == intake.record_id,
        InvestigationDeclaration.declaration_id == p08_id)).scalar_one_or_none()
    if declaration is None:
        raise not_found("investigation declaration")
    config = declaration.content["configuration"]
    if (config["permitted_access"] != ["FIXTURE_ONLY"]
            or config["pool_binding"]["profile_id"] != "fixture-unqualified-pool/1"):
        raise AppError(409, "EFFECT_COMPARISON", "UNAVAILABLE", "unsupported_p08_access",
                       [finding("unsupported_p08_access", "/p08_declaration_id",
                                "P09 currently accepts only the explicitly synthetic fixture declaration.")])
    if any(partition["role"] != "DESCRIPTIVE" for partition in config["partitions"]):
        raise AppError(409, "EFFECT_COMPARISON", "UNAVAILABLE", "protected_partition_not_authorized",
                       [finding("protected_partition_not_authorized", "/p08_declaration_id",
                                "This P09 profile does not access training, validation, or holdout partitions.")])
    start, end = body.schedule.start, body.schedule.end
    period_start, period_end = parse_utc(config["period"]["start"]), parse_utc(config["period"]["end"])
    partition = config["partitions"][0]
    partition_start, partition_end = parse_utc(partition["start"]), parse_utc(partition["end"])
    if start < period_start or end > period_end:
        raise AppError(422, "EFFECT_COMPARISON", "INVALID_INPUT", "schedule_outside_p08_period",
                       [finding("schedule_outside_p08_period", "/schedule",
                                "The decision schedule must remain inside the adopted P08 period.")])
    if start < partition_start or end > partition_end:
        raise AppError(422, "EFFECT_COMPARISON", "INVALID_INPUT", "schedule_outside_descriptive_partition",
                       [finding("schedule_outside_descriptive_partition", "/schedule",
                                "The decision schedule must remain inside the adopted descriptive partition.")])
    plan = config["evaluation_plan"]
    plan_by_id = {item["evaluation_id"]: item for item in plan}
    bindings = [item.model_dump(mode="json") for item in body.bindings]
    if set(plan_by_id) != {item["evaluation_id"] for item in bindings}:
        raise AppError(422, "EFFECT_COMPARISON", "INVALID_INPUT", "p08_plan_binding_mismatch",
                       [finding("p08_plan_binding_mismatch", "/bindings",
                                "Bind every declared P08 evaluation exactly once; do not add or omit trials or variants.")])
    for binding in bindings:
        adopted = plan_by_id[binding["evaluation_id"]]
        if any(binding[field] != adopted[field] for field in ("trial_id", "variant_id")):
            raise AppError(422, "EFFECT_COMPARISON", "INVALID_INPUT", "p08_identity_binding_mismatch",
                           [finding("p08_identity_binding_mismatch", "/bindings",
                                    "Each P06 rule binding must retain the exact adopted evaluation, trial, and variant identities.")])
        try:
            for expression in (binding["price_expression"], binding["volume_expression"]):
                if p06.expression_info(expression, p02.FIXTURE_STRATEGY["market"]).kind != "BOOLEAN":
                    raise ValueError("conditions must be typed Boolean P06 expressions")
        except p06.CompilerError as error:
            raise AppError(422, "EFFECT_COMPARISON", "INVALID_INPUT", "unsupported_p06_expression",
                           [finding(error.code, error.path, error.detail)]) from None

    try:
        fixture_hash, profile_hash = _sha256(FIXTURE_PATH), _sha256(PROFILE_PATH)
    except OSError:
        raise AppError(503, "EFFECT_COMPARISON", "UNAVAILABLE", "fixture_profile_unavailable", []) from None
    body_json = body.model_dump(mode="json")
    fingerprint = p02.sha256_hex({"owner_id": str(principal.user_id), "intake_record_id": str(intake.record_id),
                                  "p08_declaration_id": str(declaration.declaration_id), "body": body_json})
    existing = session.execute(select(EffectRunDeclaration).where(
        EffectRunDeclaration.owner_id == principal.user_id,
        EffectRunDeclaration.intake_record_id == intake.record_id,
        EffectRunDeclaration.idempotency_key == body.idempotency_key)).scalar_one_or_none()
    if existing is not None:
        if existing.fingerprint != fingerprint:
            raise AppError(409, "EFFECT_COMPARISON", "CONFLICTED", "idempotency_key_reused",
                           [finding("idempotency_key_reused", "/idempotency_key",
                                    "This key was used for a different adopted run configuration.")])
        return 200, _response(existing, _events(session, existing))

    now = dt.datetime.now(dt.timezone.utc)
    row = EffectRunDeclaration(
        run_id=uuid.uuid4(), owner_id=principal.user_id, intake_record_id=intake.record_id,
        p08_declaration_id=declaration.declaration_id, operation_id=uuid.UUID(body.operation_id),
        idempotency_key=body.idempotency_key, fingerprint=fingerprint,
        content={"schema_version": SCHEMA_VERSION, "fixture_id": body.fixture_id,
                 "fixture_sha256": fixture_hash, "profile_id": "p09.synthetic-descriptive/1",
                 "profile_sha256": profile_hash, "p08_declaration_id": str(declaration.declaration_id),
                 "p08_request_record_id": str(intake.record_id), "p08_configuration_sha256": p02.sha256_hex(config),
                 "p08_evaluation_plan": copy.deepcopy(plan), "configuration": body_json,
                 "configuration_sha256": p02.sha256_hex(body_json),
                 "notice": "Explicit synthetic P09 adoption; no outcomes are read until a separate evaluation attempt."},
        created_at=now)
    try:
        session.add(row)
        session.flush()
        event = EffectRunEvent(event_id=uuid.uuid4(), owner_id=principal.user_id, run_id=row.run_id,
                               content={"kind": "RUN_ADOPTED", "outcome_accessed": False,
                                        "p08_declaration_id": str(declaration.declaration_id),
                                        "configuration_sha256": p02.sha256_hex(body_json)}, created_at=now)
        session.add(event)
        session.commit()
    except IntegrityError:
        session.rollback()
        replay = session.execute(select(EffectRunDeclaration).where(
            EffectRunDeclaration.owner_id == principal.user_id,
            EffectRunDeclaration.intake_record_id == intake.record_id,
            EffectRunDeclaration.idempotency_key == body.idempotency_key)).scalar_one_or_none()
        if replay is None or replay.fingerprint != fingerprint:
            raise AppError(409, "EFFECT_COMPARISON", "CONFLICTED", "run_adoption_conflict", []) from None
        return 200, _response(replay, _events(session, replay))
    return 201, _response(row, _events(session, row))


def execute_effect_run(session: Session, principal: Principal, intake_id: str, run_id: str,
                       body: EffectAttemptBody) -> tuple[int, dict[str, Any]]:
    """Record a started attempt before fixture access, then save one exact immutable report."""
    row = _owned_run(session, principal, intake_id, run_id)
    existing_report = session.execute(select(EffectReport).where(
        EffectReport.owner_id == principal.user_id, EffectReport.run_id == row.run_id)).scalar_one_or_none()
    if existing_report is not None:
        replay_event = EffectRunEvent(event_id=uuid.uuid4(), owner_id=principal.user_id, run_id=row.run_id,
                                      content={"kind": "ATTEMPT_REPLAY", "operation_id": body.operation_id,
                                               "idempotency_key": body.idempotency_key,
                                               "report_id": str(existing_report.report_id),
                                               "outcome_accessed": False},
                                      created_at=dt.datetime.now(dt.timezone.utc))
        session.add(replay_event)
        session.commit()
        return 200, _response(row, _events(session, row), existing_report)

    events = _events(session, row)
    started = next((event for event in events if event.attempt_idempotency_key == body.idempotency_key), None)
    failed_before = any(event.content.get("kind") == "ATTEMPT_FAILED"
                        and event.content.get("idempotency_key") == body.idempotency_key for event in events)
    if started is not None:
        if started.content.get("operation_id") != body.operation_id:
            raise AppError(409, "EFFECT_COMPARISON", "CONFLICTED", "attempt_key_reused",
                           [finding("attempt_key_reused", "/idempotency_key",
                                    "This attempt key belongs to a different operation identity.")])
        if failed_before:
            raise AppError(409, "EFFECT_COMPARISON", "CONFLICTED", "attempt_already_failed",
                           [finding("attempt_already_failed", "/idempotency_key",
                                    "This attempt already failed. Start a new attempt with a new key.")])
        # A prior ATTEMPT_STARTED without a terminal event is an interrupted request; resume it in place.
    else:
        started = EffectRunEvent(event_id=uuid.uuid4(), owner_id=principal.user_id, run_id=row.run_id,
                                 attempt_idempotency_key=body.idempotency_key,
                                 content={"kind": "ATTEMPT_STARTED", "operation_id": body.operation_id,
                                          "idempotency_key": body.idempotency_key,
                                          "p08_declaration_id": str(row.p08_declaration_id),
                                          "configuration_sha256": row.content["configuration_sha256"]},
                                 created_at=dt.datetime.now(dt.timezone.utc))
        session.add(started)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raced = next((event for event in _events(session, row)
                          if event.attempt_idempotency_key == body.idempotency_key), None)
            if raced is None or raced.content.get("operation_id") != body.operation_id:
                raise AppError(409, "EFFECT_COMPARISON", "CONFLICTED", "attempt_key_reused", []) from None
            started = raced
    outcome_accessed = False
    try:
        if row.content["fixture_id"] != FIXTURE_ID or _sha256(FIXTURE_PATH) != row.content["fixture_sha256"]:
            raise ValueError("The adopted fixture identity or bytes have changed.")
        if _sha256(PROFILE_PATH) != row.content["profile_sha256"]:
            raise ValueError("The adopted P09 profile bytes have changed.")
        outcome_accessed = True
        dataset = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        adopted = row.content["configuration"]
        plan = row.content["p08_evaluation_plan"]
        decisions = evaluate_p06_bindings(schedule=adopted["schedule"], evaluation_plan=plan,
                                          bindings=adopted["bindings"], feature_rows=dataset["features"])
        result = compare_effects(schedule=adopted["schedule"], evaluation_plan=plan,
                                 decisions=decisions, trades=dataset["trades"],
                                 incremental_volume_declared=adopted["incremental_volume_declared"])
        report_content = {
            "schema_version": REPORT_VERSION, "run_id": str(row.run_id),
            "owner_id": str(principal.user_id), "request_record_id": row.content["p08_request_record_id"],
            "p08_declaration_id": str(row.p08_declaration_id),
            "p08_configuration_sha256": row.content["p08_configuration_sha256"],
            "p09_configuration_sha256": row.content["configuration_sha256"],
            "fixture_id": row.content["fixture_id"], "fixture_sha256": row.content["fixture_sha256"],
            "profile_id": row.content["profile_id"], "profile_sha256": row.content["profile_sha256"],
            "fixture_qualification": dataset["qualification"], "fixture_limitations": dataset["limitations"],
            "evaluation_plan": plan, "access_order": [event.content["kind"] for event in _events(session, row)]
                            + ["FIXTURE_READ", "REPORT_SAVED"],
            "result": result,
            "next_action": "Qualify the research-data history and inference profile before interpreting a real-data claim.",
        }
        report = EffectReport(report_id=uuid.uuid4(), owner_id=principal.user_id, run_id=row.run_id,
                              content=report_content, created_at=dt.datetime.now(dt.timezone.utc))
        session.add(report)
        session.add(EffectRunEvent(event_id=uuid.uuid4(), owner_id=principal.user_id, run_id=row.run_id,
                                   content={"kind": "REPORT_SAVED", "report_id": str(report.report_id),
                                            "outcome_accessed": True,
                                            "fixture_sha256": row.content["fixture_sha256"]},
                                   created_at=report.created_at))
        session.commit()
        return 201, _response(row, _events(session, row), report)
    except Exception as error:
        session.rollback()
        session.add(EffectRunEvent(event_id=uuid.uuid4(), owner_id=principal.user_id, run_id=row.run_id,
                                   content={"kind": "ATTEMPT_FAILED", "operation_id": body.operation_id,
                                            "idempotency_key": body.idempotency_key,
                                            "error_type": type(error).__name__,
                                            "outcome_accessed": outcome_accessed},
                                   created_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()
        raise AppError(422, "EFFECT_COMPARISON", "INVALID_INPUT", "effect_evaluation_failed",
                       [finding("effect_evaluation_failed", "/", str(error)[:300])]) from None


def get_effect_run(session: Session, principal: Principal, intake_id: str,
                   run_id: str) -> dict[str, Any]:
    row = _owned_run(session, principal, intake_id, run_id)
    report = session.execute(select(EffectReport).where(
        EffectReport.owner_id == principal.user_id, EffectReport.run_id == row.run_id)).scalar_one_or_none()
    return _response(row, _events(session, row), report)


def list_effect_runs(session: Session, principal: Principal, intake_id: str) -> dict[str, Any]:
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    rows = list(session.execute(select(EffectRunDeclaration).where(
        EffectRunDeclaration.owner_id == principal.user_id,
        EffectRunDeclaration.intake_record_id == intake.record_id)
        .order_by(EffectRunDeclaration.created_at, EffectRunDeclaration.run_id)).scalars())
    return {"runs": [get_effect_run(session, principal, intake_id, str(row.run_id)) for row in rows]}
