"""Owner-scoped P08 proposal, adoption, persistence and retrieval."""

from __future__ import annotations

import copy
import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding, invalid, not_found
from edge_os_api.records.models import InvestigationAccessEvent, InvestigationDeclaration
from edge_os_api.core.request_schemas import HistoryInvestigationBody, InvestigationBody, InvestigationConfiguration
from edge_os_api.research import fixture_interpreter, history_dataset
from edge_os_api.research.effect_comparison import expression_inputs
from edge_os_api.research.service import get_owned, head_interpretation, intake_rows, lock_intake, parse_uuid
from edge_os_api.strategies import compiler as strategy_compiler

SCHEMA_VERSION = "p08.investigation-declaration/2"
HISTORY_SCHEMA_VERSION = "p08.investigation-declaration/3"
RULE_MAP_VERSION = "edge-os.hypothesis-rule-map/1"
PROPOSAL_VERSION = "p08-bounded-review/2"
BUDGET_VERSION = "p08-research-budget/2"
FIXTURE_PROFILE = "fixture-unqualified-pool/1"
CONFIGURATION_FIELDS = (
    "question", "pool_binding", "variants", "direction", "horizons", "sources", "candidate_limit",
    "parameter_limit", "compute_limit", "period", "partitions", "permitted_access", "stopping_rule", "evaluation_plan",
    "budget_version", "optional_tools",
)


def _proposal_configuration(question: str) -> dict[str, Any]:
    return {
        "question": question,
        "pool_binding": {
            "profile_id": FIXTURE_PROFILE,
            "qualification": "UNQUALIFIED_FIXTURE",
            "limitations": ["Synthetic interface fixture only; no production pool or source is qualified."],
        },
        "variants": [
            {"variant_id": "primary", "hypothesis": "Primary descriptive group."},
            {"variant_id": "comparison", "hypothesis": "Declared comparison group."},
        ],
        "direction": "DESCRIPTIVE",
        "horizons": [{"value": 15, "unit": "MINUTES"}],
        "sources": [FIXTURE_PROFILE],
        "candidate_limit": 2,
        "parameter_limit": 4,
        "compute_limit": {"max_evaluations": 2, "max_runtime_seconds": 60, "max_cost_usd": "0"},
        "period": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"},
        "partitions": [{"partition_id": "descriptive", "role": "DESCRIPTIVE",
                        "start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"}],
        "evaluation_plan": [
            {"evaluation_id": "00000000-0000-4000-8000-000000000001",
             "trial_id": "00000000-0000-4000-8000-000000000000", "variant_id": "primary",
             "horizon": {"value": 15, "unit": "MINUTES"}, "partition_ids": ["descriptive"]},
            {"evaluation_id": "00000000-0000-4000-8000-000000000002",
             "trial_id": "00000000-0000-4000-8000-000000000000", "variant_id": "comparison",
             "horizon": {"value": 15, "unit": "MINUTES"}, "partition_ids": ["descriptive"]},
        ],
        "permitted_access": ["FIXTURE_ONLY"],
        "stopping_rule": "Stop after the two declared comparisons; no outcome is evaluated by this save.",
        "budget_version": BUDGET_VERSION,
        "optional_tools": {"creator_history": "UNAVAILABLE", "wallet_pnl": "UNAVAILABLE",
                           "social_signals": "UNAVAILABLE"},
    }


def proposal_for(intake: Any, interpretation: Any | None) -> dict[str, Any]:
    """Return a bounded, explicitly unadopted fixture proposal for one saved request."""
    question = intake.content["original_request"]
    trial_ids = [str(uuid.uuid4())]
    evaluation_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    configuration = _proposal_configuration(question)
    configuration["evaluation_plan"] = [
        {"evaluation_id": evaluation_ids[0], "trial_id": trial_ids[0], "variant_id": "primary",
         "horizon": {"value": 15, "unit": "MINUTES"}, "partition_ids": ["descriptive"]},
        {"evaluation_id": evaluation_ids[1], "trial_id": trial_ids[0], "variant_id": "comparison",
         "horizon": {"value": 15, "unit": "MINUTES"}, "partition_ids": ["descriptive"]},
    ]
    fields = {
        name: {"origin": "USER_STATED" if name == "question" else "APPLICATION_CONFIGURED",
               "source_ref": "original_request" if name == "question" else f"proposal:{PROPOSAL_VERSION}",
               "adoption": "PENDING"}
        for name in CONFIGURATION_FIELDS
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "proposal_version": PROPOSAL_VERSION,
        "interpretation_revision_id": (interpretation.content["interpretation_revision_id"]
                                       if interpretation is not None else None),
        "request_record_id": str(intake.record_id),
        "edge_spec": {
            "edge_id": str(uuid.uuid4()), "version": 1, "parent_declaration_id": None,
            "hypothesis": "A descriptive comparison; no predictive hypothesis has been adopted.",
            "claim": {"status": "DESCRIPTIVE_ONLY", "text": "Describe only. No predictive claim is declared."},
            "falsification": {"status": "DESCRIPTIVE_ONLY", "criteria": "No outcome claim is evaluated."},
            "alternatives": ["The observed association may reflect selection or an unmeasured alternative."],
            "unknowns": ["Participant identity and incentives are unverified.",
                         "Persistence, capacity, and evidence capture are unknown.",
                         "Costs and data-source coverage are not measured."],
        },
        "configuration": configuration,
        "adopted_fields": [],
        "field_origins": fields,
        "trial_ids": trial_ids,
        "evaluation_ids": evaluation_ids,
        "notice": "This is a fixture-only proposal. Adoption saves a pre-outcome declaration; it does not run a study.",
    }


def get_proposal(session: Session, principal: Principal, intake_id: str) -> dict[str, Any]:
    """Load the current owner-scoped request state and propose a bounded review configuration."""
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    if intake.content["requested_job"] != "INVESTIGATE_EFFECT":
        raise invalid("/requested_job", "Only an investigation request can use this proposal.",
                      "investigation_job_required")
    interpretation = head_interpretation(intake_rows(session, principal, intake.record_id))
    return proposal_for(intake, interpretation)


def _declaration_envelope(row: InvestigationDeclaration) -> dict[str, Any]:
    return {"schema_version": row.content["schema_version"], "record_type": "InvestigationDeclaration",
            "record_id": str(row.declaration_id), "owner_id": str(row.owner_id),
            "operation_id": str(row.operation_id), "created_at": record_contract.utc_string(row.created_at),
            "content": row.content}


def _access_event(session: Session, row: InvestigationDeclaration) -> dict[str, Any]:
    event = session.execute(select(InvestigationAccessEvent).where(
        InvestigationAccessEvent.owner_id == row.owner_id,
        InvestigationAccessEvent.declaration_id == row.declaration_id)).scalar_one()
    return {"event_id": str(event.event_id), "declaration_id": str(event.declaration_id),
            "created_at": record_contract.utc_string(event.created_at), **event.content}


def _response(session: Session, row: InvestigationDeclaration, *, replay: bool = False) -> dict[str, Any]:
    return {"declaration": _declaration_envelope(row), "access_history": [_access_event(session, row)],
            "study_started": False, "idempotent_replay": replay}


def _request_fingerprint(principal: Principal, intake_id: uuid.UUID,
                         body: InvestigationBody | HistoryInvestigationBody) -> str:
    canonical_body = record_contract.canonical_bytes(body.model_dump(mode="json")).decode("utf-8")
    return record_contract.sha256_hex({"owner_id": str(principal.user_id), "intake_record_id": str(intake_id),
                          "body": canonical_body})


def _existing_for_key(session: Session, principal: Principal, intake_id: uuid.UUID,
                      key: str) -> InvestigationDeclaration | None:
    return session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == principal.user_id,
        InvestigationDeclaration.intake_record_id == intake_id,
        InvestigationDeclaration.idempotency_key == key)).scalar_one_or_none()


def _replay_or_conflict(session: Session, row: InvestigationDeclaration | None, fingerprint: str) -> tuple[int, dict[str, Any]] | None:
    if row is None:
        return None
    session.rollback()
    if row.fingerprint != fingerprint:
        raise AppError(409, "INVESTIGATION", "CONFLICTED", "idempotency_key_reused", [finding(
            "idempotency_key_reused", "/idempotency_key", "This key was used for a different declaration.")])
    return 200, _response(session, row, replay=True)


def create_declaration(session: Session, principal: Principal, intake_id: str,
                       body: InvestigationBody) -> tuple[int, dict[str, Any]]:
    """Validate and atomically append one adopted declaration and its first access event."""
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    if intake.content["requested_job"] != "INVESTIGATE_EFFECT":
        raise invalid("/requested_job", "Only an investigation request can save this declaration.",
                      "investigation_job_required")
    fingerprint = _request_fingerprint(principal, intake.record_id, body)
    existing = _existing_for_key(session, principal, intake.record_id, body.idempotency_key)
    replay = _replay_or_conflict(session, existing, fingerprint)
    if replay is not None:
        return replay

    # Observe before acquiring the shared lock, then serialize and re-read the head below.
    intake_rows(session, principal, intake.record_id)
    intake = lock_intake(session, principal, intake_id)
    rows = intake_rows(session, principal, intake.record_id)
    interpretation = head_interpretation(rows)
    current_revision_id = interpretation.content["interpretation_revision_id"] if interpretation is not None else None
    existing = _existing_for_key(session, principal, intake.record_id, body.idempotency_key)
    replay = _replay_or_conflict(session, existing, fingerprint)
    if replay is not None:
        return replay
    if body.expected_interpretation_revision_id != current_revision_id:
        session.rollback()
        raise AppError(409, "INVESTIGATION", "CONFLICTED", "interpretation_revision_conflict", [finding(
            "interpretation_revision_conflict", "/expected_interpretation_revision_id",
            "The request changed. Reload it and review the current settings before saving.")])
    if body.configuration.question != intake.content["original_request"]:
        raise invalid("/configuration/question", "Keep the original question unchanged in the declaration.",
                      "original_request_changed")
    if body.configuration.compute_limit.max_cost_usd != "0":
        raise invalid("/configuration/compute_limit/max_cost_usd", "P08 permits no paid or provider operation.",
                      "paid_access_not_permitted")
    if body.configuration.permitted_access != ["FIXTURE_ONLY"]:
        raise invalid("/configuration/permitted_access", "P08 can declare fixture-only access.",
                      "unsupported_access_route")
    if any(value.origin == "AGENT_PROPOSED" for value in body.field_origins.values()):
        raise invalid("/field_origins", "No agent proposed these settings; identify the user's or application source.",
                      "unsupported_origin")

    proposal = InvestigationConfiguration.model_validate(
        _proposal_configuration(intake.content["original_request"])
    ).model_dump(mode="json")
    provided = body.configuration.model_dump(mode="json")
    for field_name, origin in body.field_origins.items():
        if field_name == "edge_spec":
            if origin.origin not in {"USER_STATED", "USER_CONFIRMED"} or origin.source_ref != "investigation-review/2":
                raise invalid("/field_origins/edge_spec", "Review and adopt the hypothesis or descriptive status.",
                              "edge_spec_not_adopted")
            continue
        if field_name == "question":
            if origin.origin != "USER_STATED" or origin.source_ref != "original_request":
                raise invalid("/field_origins/question", "Keep the original question bound to its saved source.",
                              "configuration_origin_mismatch")
            continue
        if field_name == "evaluation_plan":
            if origin.origin != "USER_CONFIRMED" or origin.source_ref != "investigation-review/2":
                raise invalid("/field_origins/evaluation_plan", "Confirm the exact evaluation plan in this review.",
                              "configuration_origin_mismatch")
            continue
        if origin.origin == "APPLICATION_CONFIGURED":
            if provided[field_name] != proposal[field_name] or origin.source_ref != f"proposal:{PROPOSAL_VERSION}":
                raise invalid(f"/field_origins/{field_name}",
                              "An edited setting must be recorded as user-confirmed with its review source.",
                              "configuration_origin_mismatch")
        elif origin.origin not in {"USER_STATED", "USER_CONFIRMED"} or origin.source_ref != "investigation-review/2":
            raise invalid(f"/field_origins/{field_name}", "The setting source does not match the saved review.",
                          "configuration_origin_mismatch")

    edge = body.edge_spec
    parent_id = parse_uuid(edge.parent_declaration_id) if edge.parent_declaration_id else None
    if parent_id is None and (edge.parent_declaration_id is not None or edge.version != 1):
        raise invalid("/edge_spec/parent_declaration_id", "A first hypothesis version has no parent and starts at version 1.",
                      "invalid_hypothesis_lineage")
    if parent_id is not None:
        parent = session.execute(select(InvestigationDeclaration).where(
            InvestigationDeclaration.owner_id == principal.user_id,
            InvestigationDeclaration.intake_record_id == intake.record_id,
            InvestigationDeclaration.declaration_id == parent_id)).scalar_one_or_none()
        if parent is None:
            raise AppError(409, "INVESTIGATION", "CONFLICTED", "parent_declaration_conflict", [finding(
                "parent_declaration_conflict", "/edge_spec/parent_declaration_id",
                "The parent declaration does not exist for this owner and request.")])
        if str(parent.edge_id) != edge.edge_id or edge.version != parent.edge_version + 1:
            raise invalid("/edge_spec", "A revised hypothesis must keep its edge identity and increment its version.",
                          "invalid_hypothesis_lineage")
    elif edge.version != 1:
        raise invalid("/edge_spec/version", "A new hypothesis starts at version 1.", "invalid_hypothesis_lineage")

    now = dt.datetime.now(dt.timezone.utc)
    declaration_id = uuid.uuid4()
    content = {
        "schema_version": SCHEMA_VERSION,
        "original_request": intake.content["original_request"],
        "restrictions": list(intake.content["restrictions"]),
        "input_class": intake.content["input_class"],
        "requested_job": intake.content["requested_job"],
        "interpretation_revision_id": current_revision_id,
        "edge_spec": body.edge_spec.model_dump(mode="json"),
        "configuration": provided,
        "adopted_fields": list(body.adopted_fields),
        "field_origins": {name: value.model_dump(mode="json") for name, value in body.field_origins.items()},
        "trial_ids": list(body.trial_ids),
        "evaluation_ids": list(body.evaluation_ids),
        "declaration_state": "PRE_OUTCOME_DECLARED",
        "outcome_labels_read": False,
    }
    row = InvestigationDeclaration(
        declaration_id=declaration_id, owner_id=principal.user_id, intake_record_id=intake.record_id,
        edge_id=uuid.UUID(edge.edge_id), edge_version=edge.version, parent_declaration_id=parent_id,
        operation_id=uuid.UUID(body.operation_id), idempotency_key=body.idempotency_key,
        fingerprint=fingerprint, content=content, created_at=now)
    event = InvestigationAccessEvent(
        event_id=uuid.uuid4(), owner_id=principal.user_id, declaration_id=declaration_id,
        content={"schema_version": "p08.investigation-access/1", "event": "DECLARATION_SAVED",
                 "outcome_labels_read": False, "provider_queries": 0,
                 "study_started": False}, created_at=now)
    session.add(row)
    try:
        session.flush()
        session.add(event)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        existing = session.execute(select(InvestigationDeclaration).where(
            InvestigationDeclaration.owner_id == principal.user_id,
            InvestigationDeclaration.intake_record_id == intake.record_id,
            InvestigationDeclaration.idempotency_key == body.idempotency_key)).scalar_one_or_none()
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise AppError(409, "INVESTIGATION", "CONFLICTED", "idempotency_key_reused", [finding(
                    "idempotency_key_reused", "/idempotency_key", "This key was used for a different declaration.")]) from None
            return 200, _response(session, existing, replay=True)
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_investigation_owner_operation":
            raise AppError(409, "INVESTIGATION", "CONFLICTED", "operation_id_reused", [finding(
                "operation_id_reused", "/operation_id", "This operation ID belongs to another declaration.")]) from None
        if constraint == "uq_investigation_edge_version":
            raise AppError(409, "INVESTIGATION", "CONFLICTED", "edge_version_conflict", [finding(
                "edge_version_conflict", "/edge_spec/version", "This hypothesis version already exists.")]) from None
        if constraint == "fk_investigation_parent":
            raise AppError(409, "INVESTIGATION", "CONFLICTED", "parent_declaration_conflict", [finding(
                "parent_declaration_conflict", "/edge_spec/parent_declaration_id",
                "The parent declaration does not exist for this owner and request.")]) from None
        raise
    return 201, _response(session, row)


def list_declarations(session: Session, principal: Principal, intake_id: str) -> dict[str, Any]:
    """Return an owner's exact declarations and their saved access events."""
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    rows = [row for row in _declaration_rows(session, principal, intake.record_id)
            if row.content["schema_version"] == SCHEMA_VERSION]
    declarations = [_declaration_envelope(row) for row in rows]
    access_history = [_access_event(session, row) for row in rows]
    return {"declarations": declarations, "access_history": access_history}


def get_declaration(session: Session, principal: Principal, intake_id: str, declaration_id: str) -> dict[str, Any]:
    """Read one declaration and its access record without exposing another owner's identity."""
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    parsed_id = parse_uuid(declaration_id)
    row = None if parsed_id is None else session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == principal.user_id,
        InvestigationDeclaration.intake_record_id == intake.record_id,
        InvestigationDeclaration.declaration_id == parsed_id)).scalar_one_or_none()
    if row is None or row.content["schema_version"] != SCHEMA_VERSION:
        raise not_found("investigation declaration")
    return _response(session, row)


def _declaration_rows(session: Session, principal: Principal, intake_id: uuid.UUID) -> list[InvestigationDeclaration]:
    return list(session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == principal.user_id,
        InvestigationDeclaration.intake_record_id == intake_id)
        .order_by(InvestigationDeclaration.created_at, InvestigationDeclaration.declaration_id)).scalars())


def _example_rule_hashes() -> frozenset[str]:
    """Rules an example already tested: the fixture strategy, the fixture interpreter's choices and the P09 example."""
    strategy = record_contract.FIXTURE_STRATEGY
    quote_unit = strategy["market"]["quote_unit"]
    examples: list[Any] = [strategy["entry"], strategy["exit"],
                           {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "99", "unit": "PRICE"}]}]
    examples += [option.value for option in fixture_interpreter.ENTRY_QUESTION.options]
    examples += [{"op": "gt", "args": [{"op": "quote_volume"}, {"op": "constant", "value": value, "unit": quote_unit}]}
                 for value in ("4", "6")]
    return frozenset(record_contract.sha256_hex(item) for item in examples)


EXAMPLE_RULE_HASHES = _example_rule_hashes()


def _history_refusal(status: int, code: str, path: str, detail: str) -> AppError:
    kind = "UNAVAILABLE" if status == 409 else "INVALID_INPUT"
    return AppError(status, "INVESTIGATION", kind, code, [finding(code, path, detail)])


def _check_history_configuration(body: HistoryInvestigationBody, runtime: Any = None) -> dict[str, Any]:
    """Bind the declaration to one served source and the user's own rules. Returns that source.

    `runtime` is the composed operating release, if any; its one history source is served only while it is composed."""
    config = body.configuration
    source = history_dataset.served_sources(runtime).get(config.source.source_id)
    if config.source.evidence_class == "PROVIDER_ACTUAL" and (
            source is None or source["evidence_class"] != "PROVIDER_ACTUAL"):
        # Only an approved actual release, composed by this server, serves actual history; none is approved.
        raise _history_refusal(409, "actual_data_not_authorized", "/configuration/source/evidence_class",
                               "Actual provider history needs a separately approved data packet. "
                               "Only recorded responses are available.")
    if source is None:
        raise _history_refusal(422, "unsupported_history_source", "/configuration/source/source_id",
                               "Choose one of the listed recorded sources.")
    if config.source.evidence_class != source["evidence_class"]:
        raise _history_refusal(422, "history_source_class_mismatch", "/configuration/source/evidence_class",
                               "The evidence class must be the listed source's own class.")
    if config.source.profile_sha256 != history_dataset.profile_sha256(source):
        raise _history_refusal(422, "history_source_changed", "/configuration/source/profile_sha256",
                               "The recorded source differs from the one you reviewed. Reload the source list.")
    if config.market.model_dump() != history_dataset.source_market(source):
        raise _history_refusal(422, "history_market_mismatch", "/configuration/market",
                               "The market must be the declared source's exact network, pool and assets.")
    window = history_dataset.source_window(source)
    if (config.window.start, config.window.end) != (parse_utc_text(window["start"]), parse_utc_text(window["end"])):
        raise _history_refusal(422, "history_window_unsupported", "/configuration/window",
                               "Only the declared source's recorded window is supported.")
    bounds = config.resource_bounds
    if "release" in source and bounds.model_dump() != source["release"]["history"]["limits"]:
        raise _history_refusal(422, "release_bounds_mismatch", "/configuration/resource_bounds",
                               "This source runs under a fixed operating release. Use its listed limits exactly.")
    if bounds.max_pages < history_dataset.page_requests(source):
        raise _history_refusal(422, "resource_bounds_too_small", "/configuration/resource_bounds/max_pages",
                               f"This source needs {history_dataset.page_requests(source)} page requests.")
    if bounds.provider_requests < history_dataset.requests_needed(source):
        raise _history_refusal(422, "resource_bounds_too_small", "/configuration/resource_bounds/provider_requests",
                               f"This source needs {history_dataset.requests_needed(source)} provider requests: "
                               "its pages, one chain read and one receipt per corroborated swap.")
    market = {"network": config.market.network, "quote_unit": f"QUOTE:{config.market.quote_asset}",
              "research_binding": {"base_asset": config.market.base_asset, "quote_asset": config.market.quote_asset}}
    for index, rule in enumerate(config.rule_map.rules):
        for name in ("price_expression", "volume_expression"):
            path = f"/configuration/rule_map/rules/{index}/{name}"
            expression = getattr(rule, name)
            if record_contract.sha256_hex(expression) in EXAMPLE_RULE_HASHES:
                raise _history_refusal(422, "example_rule_not_adoptable", path,
                                       "This rule belongs to a worked example. Write and adopt your own rule.")
            try:
                if strategy_compiler.expression_info(expression, market, path).kind != "BOOLEAN":
                    raise _history_refusal(422, "p06_condition_not_boolean", path, "Each adopted condition must be Boolean.")
            except strategy_compiler.CompilerError as error:
                raise _history_refusal(422, "unsupported_p06_expression", error.path, error.detail) from None
        if config.rule_map.incremental_volume_declared and (
                expression_inputs(rule.price_expression) != {"price"}
                or expression_inputs(rule.volume_expression) != {"quote_volume"}):
            raise _history_refusal(422, "incremental_volume_mapping_unsupported", f"/configuration/rule_map/rules/{index}",
                                   "Incremental volume comparison needs a price-only rule and a quote-volume-only rule.")
    return source


def parse_utc_text(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def create_history_declaration(session: Session, principal: Principal, intake_id: str,
                               body: HistoryInvestigationBody, runtime: Any = None) -> tuple[int, dict[str, Any]]:
    """Save one v3 declaration and its first access event before any collection, outcome or provider request."""
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    if intake.content["requested_job"] != "INVESTIGATE_EFFECT":
        raise invalid("/requested_job", "Only an investigation request can save this declaration.",
                      "investigation_job_required")
    fingerprint = _request_fingerprint(principal, intake.record_id, body)
    replay = _replay_or_conflict(session, _existing_for_key(session, principal, intake.record_id, body.idempotency_key),
                                 fingerprint)
    if replay is not None:
        return replay
    source = _check_history_configuration(body, runtime)
    intake = lock_intake(session, principal, intake_id)
    interpretation = head_interpretation(intake_rows(session, principal, intake.record_id))
    current_revision_id = interpretation.content["interpretation_revision_id"] if interpretation is not None else None
    replay = _replay_or_conflict(session, _existing_for_key(session, principal, intake.record_id, body.idempotency_key),
                                 fingerprint)
    if replay is not None:
        return replay
    if body.expected_interpretation_revision_id != current_revision_id:
        session.rollback()
        raise AppError(409, "INVESTIGATION", "CONFLICTED", "interpretation_revision_conflict", [finding(
            "interpretation_revision_conflict", "/expected_interpretation_revision_id",
            "The request changed. Reload it and review the current settings before saving.")])
    if body.configuration.question != intake.content["original_request"]:
        raise invalid("/configuration/question", "Keep the original question unchanged in the declaration.",
                      "original_request_changed")
    edge = body.edge_spec
    if edge.parent_declaration_id is not None or edge.version != 1:
        raise invalid("/edge_spec", "A recorded-history declaration starts a new hypothesis at version 1.",
                      "invalid_hypothesis_lineage")
    configuration = body.configuration.model_dump(mode="json")
    rule_map = {**configuration["rule_map"], "declaration_hypothesis": edge.hypothesis, "edge_id": edge.edge_id,
                "binding_state": "PENDING_DATASET_QUALIFICATION"}
    now = dt.datetime.now(dt.timezone.utc)
    declaration_id = uuid.uuid4()
    content = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "original_request": intake.content["original_request"],
        "restrictions": list(intake.content["restrictions"]),
        "input_class": intake.content["input_class"],
        "requested_job": intake.content["requested_job"],
        "interpretation_revision_id": current_revision_id,
        "edge_spec": edge.model_dump(mode="json"),
        "configuration": configuration,
        "rule_map": rule_map,
        "field_origins": {name: value.model_dump(mode="json") for name, value in body.field_origins.items()},
        "trial_ids": list(body.trial_ids),
        "evaluation_ids": list(body.evaluation_ids),
        "frozen": {"configuration_sha256": record_contract.sha256_hex(configuration),
                   "rule_map_sha256": record_contract.sha256_hex(rule_map),
                   "source_profile_sha256": history_dataset.profile_sha256(source),
                   "scan": dict(source["scan"]), "frozen_at": record_contract.utc_string(now),
                   **({"operating_release_id": source["release"]["release_id"],
                       "operating_release_sha256": source["release"]["sha256"]} if "release" in source else {})},
        "declaration_state": "PRE_OUTCOME_DECLARED",
        "outcome_labels_read": False,
    }
    row = InvestigationDeclaration(
        declaration_id=declaration_id, owner_id=principal.user_id, intake_record_id=intake.record_id,
        edge_id=uuid.UUID(edge.edge_id), edge_version=edge.version, parent_declaration_id=None,
        operation_id=uuid.UUID(body.operation_id), idempotency_key=body.idempotency_key,
        fingerprint=fingerprint, content=content, created_at=now)
    event = InvestigationAccessEvent(
        event_id=uuid.uuid4(), owner_id=principal.user_id, declaration_id=declaration_id,
        content={"schema_version": "p08.investigation-access/1", "event": "DECLARATION_SAVED",
                 "outcome_labels_read": False, "provider_queries": 0, "study_started": False}, created_at=now)
    session.add(row)
    try:
        session.flush()
        session.add(event)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        existing = _existing_for_key(session, principal, intake.record_id, body.idempotency_key)
        if existing is not None:
            return _replay_or_conflict(session, existing, fingerprint)  # type: ignore[return-value]
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_investigation_owner_operation":
            raise AppError(409, "INVESTIGATION", "CONFLICTED", "operation_id_reused", [finding(
                "operation_id_reused", "/operation_id", "This operation ID belongs to another declaration.")]) from None
        if constraint == "uq_investigation_edge_version":
            raise AppError(409, "INVESTIGATION", "CONFLICTED", "edge_version_conflict", [finding(
                "edge_version_conflict", "/edge_spec/version", "This hypothesis version already exists.")]) from None
        raise
    return 201, _response(session, row)


def owned_history_declaration(session: Session, principal: Principal, intake_id: str,
                              declaration_id: str) -> InvestigationDeclaration:
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    parsed_id = parse_uuid(declaration_id)
    row = None if parsed_id is None else session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == principal.user_id,
        InvestigationDeclaration.intake_record_id == intake.record_id,
        InvestigationDeclaration.declaration_id == parsed_id)).scalar_one_or_none()
    if row is None or row.content["schema_version"] != HISTORY_SCHEMA_VERSION:
        raise not_found("investigation declaration")
    return row


def list_history_declarations(session: Session, principal: Principal, intake_id: str) -> dict[str, Any]:
    intake = get_owned(session, principal, intake_id, "IntakeRequest")
    rows = [row for row in _declaration_rows(session, principal, intake.record_id)
            if row.content["schema_version"] == HISTORY_SCHEMA_VERSION]
    return {"declarations": [_response(session, row) for row in rows]}


def get_history_declaration(session: Session, principal: Principal, intake_id: str,
                            declaration_id: str) -> dict[str, Any]:
    return _response(session, owned_history_declaration(session, principal, intake_id, declaration_id))
