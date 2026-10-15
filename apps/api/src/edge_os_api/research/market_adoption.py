"""Pre-publication adoption of a QUALIFIED recorded-history market for a compiled strategy request (#58 RG05).

The owner names one of their saved datasets and restates the trade amounts for that market's quote unit. The server
rebuilds the market from the dataset's stored P07 projection after checking its hashes and verdict, then appends a NEW
interpretation revision, its clarification and the routed outcome and draft through the existing record functions.
Nothing earlier changes: previous interpretations, drafts and published revisions stay as they were, and publication
still requires the exact draft bytes. No amount is converted and no execution route is qualified here.
"""

from __future__ import annotations

import copy
import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from edge_os_api.core.authentication import Principal
from edge_os_api.core.errors import AppError, finding, invalid
from edge_os_api.core.request_schemas import MarketAdoptionBody
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.records.models import IdempotencyRecord, InvestigationDeclaration, StrategyRevision
from edge_os_api.research import history_dataset, history_payload_binding, service
from edge_os_api.research.effect_comparison import expression_inputs
from edge_os_api.research.investigation_adoption import EXAMPLE_RULE_HASHES, HISTORY_SCHEMA_VERSION
from edge_os_api.research.outcome_router import route
from edge_os_api.strategies import compiler as strategy_compiler

QUESTION_ID = "adopt-recorded-market"


def declared_entry(rule: dict[str, Any]) -> dict[str, Any]:
    """The strategy entry for one declared rule: its price condition and its volume condition together."""
    return {"op": "and", "args": [rule["price_expression"], rule["volume_expression"]]}


def declared_rule(session: Session, principal: Principal, declaration_id: str,
                  evaluation_id: str) -> tuple[InvestigationDeclaration, dict[str, Any]]:
    """One USER_ADOPTED rule of the dataset's own v3 declaration, owner-scoped."""
    declaration = session.execute(select(InvestigationDeclaration).where(
        InvestigationDeclaration.owner_id == principal.user_id,
        InvestigationDeclaration.declaration_id == uuid.UUID(declaration_id))).scalar_one_or_none()
    rule = None
    wanted = str(uuid.UUID(evaluation_id))  # identities compare in canonical lowercase form
    if declaration is not None and declaration.content["schema_version"] == HISTORY_SCHEMA_VERSION:
        rule = next((item for item in declaration.content["rule_map"]["rules"]
                     if str(uuid.UUID(item["evaluation_id"])) == wanted and item["rule_source"] == "USER_ADOPTED"), None)
    if declaration is None or rule is None:
        raise invalid("/evaluation_id", "Choose one rule that you declared for this dataset's investigation.",
                      "declared_rule_not_found")
    return declaration, rule


def _conflict(code: str, path: str, detail: str) -> AppError:
    return AppError(409, "VALIDATION", "CONFLICTED", code, [finding(code, path, detail)])


def _unavailable(code: str, path: str, detail: str) -> AppError:
    return AppError(409, "VALIDATION", "UNAVAILABLE", code, [finding(code, path, detail)])


def _quote_units(node: Any) -> set[str]:
    if isinstance(node, dict):
        units = {node["unit"]} if isinstance(node.get("unit"), str) and node["unit"].startswith("QUOTE:") else set()
        return units.union(*(_quote_units(value) for value in node.values())) if node else units
    if isinstance(node, list):
        return set().union(*(_quote_units(item) for item in node)) if node else set()
    return set()


def _head_revision(session: Session, principal: Principal, strategy_id: str) -> uuid.UUID | None:
    rows = list(session.execute(select(StrategyRevision.revision_id, StrategyRevision.parent_revision_id).where(
        StrategyRevision.owner_id == principal.user_id, StrategyRevision.strategy_id == strategy_id)))
    parents = {parent for _, parent in rows if parent is not None}
    heads = [revision for revision, _ in rows if revision not in parents]
    return heads[0] if len(heads) == 1 else None


def _market_from_dataset(session: Session, principal: Principal,
                         dataset_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """The full P02 market, rebuilt only from a same-owner, hash-verified, QUALIFIED and complete dataset whose
    required payload binding passes now. Returns the row, the market and the binding state."""
    row = history_dataset.owned_dataset(session, principal, dataset_id)
    verified = history_dataset.verify_hashes(row)
    if not all(verified.values()):
        raise _conflict("dataset_hash_mismatch", "/dataset_id",
                        "The saved dataset no longer matches its recorded hashes. It cannot bind a market.")
    content = row.content
    if (content["verdict"]["overall"] != "QUALIFIED" or content["status"] != "COMPLETE"
            or content["binding_state"] != "QUALIFIED_BINDING" or content["market_binding"] is None):
        raise _unavailable("dataset_not_qualified", "/dataset_id",
                           "Only a complete, QUALIFIED dataset can supply a market. This one stays "
                           f"{content['verdict']['overall']} and keeps its limits.")
    market = history_dataset.strategy_market(content["market_binding"])
    if strategy_compiler.market_binding_id(market) != content["market_binding_id"]:
        raise _conflict("dataset_binding_mismatch", "/dataset_id",
                        "The dataset's market identity does not recompute. It cannot bind a market.")
    # The saved P07 verdict stays QUALIFIED either way; a failed or missing required binding only blocks this use.
    binding = history_payload_binding.require_bound(session, principal, row, stage="VALIDATION", path="/dataset_id")
    return row, market, binding


def adopt_dataset_market(session: Session, principal: Principal, intake_id: str,
                         body: MarketAdoptionBody) -> tuple[int, dict[str, Any]]:
    path = f"/v1/research/requests/{intake_id}/market-adoptions"
    fingerprint = record_contract.sha256_hex({"owner_id": str(principal.user_id), "path": path,
                                              "body": body.model_dump(mode="json")})
    intake = service.lock_intake(session, principal, intake_id)
    existing = session.execute(select(IdempotencyRecord).where(
        IdempotencyRecord.owner_id == principal.user_id, IdempotencyRecord.method == "POST",
        IdempotencyRecord.path == path, IdempotencyRecord.idempotency_key == body.idempotency_key)).scalar_one_or_none()
    if existing is not None:
        session.rollback()
        if existing.fingerprint != fingerprint:
            raise _conflict("idempotency_key_reused", "/idempotency_key",
                            "This key was used for a different market adoption.")
        return 200, {"adoption": existing.response, "replayed": True,
                     "bundle": service.load_bundle(session, principal, intake.record_id)}
    if intake.content["requested_job"] != "CREATE_STRATEGY":
        raise invalid("/requested_job", "Only a strategy request can adopt a market for its draft.",
                      "strategy_job_required")
    rows = service.intake_rows(session, principal, intake.record_id)
    head = service.head_interpretation(rows)
    if head is None or head.content["interpretation_revision_id"] != body.expected_interpretation_revision_id:
        raise _conflict("parent_revision_conflict", "/expected_interpretation_revision_id",
                        "The request changed. Reload it and review the market again.")
    head_draft = next((row for row in reversed(rows) if row.record_type == "StrategyDraft"
                       and row.interpretation_record_id == head.record_id), None)
    if head_draft is None:
        raise _unavailable("compiled_draft_required", "/expected_interpretation_revision_id",
                           "Adopt every strategy setting first. A market can replace only a compiled draft's market.")
    strategy_id = head_draft.content["strategy_id"]
    parent = _head_revision(session, principal, strategy_id)
    if (None if parent is None else str(parent)) != body.expected_parent_revision_id:
        raise _conflict("parent_revision_conflict", "/expected_parent_revision_id",
                        "The published revision changed. Reload the request before adopting a market.")
    dataset, market, binding = _market_from_dataset(session, principal, body.dataset_id)
    if body.quote_unit != market["quote_unit"]:
        raise invalid("/quote_unit", "Confirm the dataset market's exact quote unit.", "quote_unit_mismatch")
    declaration, rule = declared_rule(session, principal, dataset.content["declaration_id"], body.evaluation_id)
    entry = declared_entry(rule)
    for field_path, expression in (("/evaluation_id", entry), ("/exit_rule", body.exit_rule)):
        if record_contract.sha256_hex(expression) in EXAMPLE_RULE_HASHES:
            raise invalid(field_path, "This rule belongs to a worked example. Use your own rule.",
                          "example_rule_not_adoptable")
        if _quote_units(expression) - {market["quote_unit"]}:
            raise invalid(field_path, "A rule compares against an amount in another market's quote unit. "
                          "Restate it for this market.", "unit_mismatch")
        try:
            if strategy_compiler.expression_info(expression, market, field_path).kind != "BOOLEAN":
                raise invalid(field_path, "A rule must be a Boolean condition.", "rule_not_boolean")
        except strategy_compiler.CompilerError as error:
            raise invalid(error.path, error.detail, error.code) from None
    evidence = {item["field_name"]: copy.deepcopy(item) for item in head.content["field_evidence"]}
    revision_id = uuid.uuid4()
    source_ref = f"history-dataset:{dataset.dataset_id}"
    confirmed = f"market-adoption:{revision_id}"
    rule_ref = f"history-rule:{declaration.declaration_id}:{rule['evaluation_id']}"  # the stored canonical identity
    inputs = sorted(expression_inputs(entry) | expression_inputs(body.exit_rule))
    for name, value, ref in (("entry", entry, rule_ref), ("exit", copy.deepcopy(body.exit_rule), confirmed)):
        restated = {key: item for key, item in evidence[name].items() if key != "adoption"}
        evidence[name] = {**restated, "origin": "USER_CONFIRMED", "source_ref": ref, "value": value}
    evidence["data_inputs"] = {**evidence["data_inputs"], "origin": "APPLICATION_CONFIGURED", "source_ref": confirmed,
                               "adoption": "ADOPTED", "value": inputs}
    evidence["market"] = {**evidence["market"], "origin": "APPLICATION_CONFIGURED", "source_ref": source_ref,
                          "evidence_status": "HYPOTHESIS", "adoption": "ADOPTED", "value": market}
    # The owner restates both amounts for the new quote unit; nothing carries over from the old unit.
    for name, value in (("sizing", {**evidence["sizing"]["value"], "amount": body.sizing_amount,
                                    "unit": market["quote_unit"]}),
                        ("risk_limits", {**evidence["risk_limits"]["value"],
                                         "max_quote_notional": body.max_quote_notional})):
        restated = {key: item for key, item in evidence[name].items() if key != "adoption"}
        evidence[name] = {**restated, "origin": "USER_CONFIRMED", "source_ref": confirmed, "value": value}
    new_evidence = service.bind_revision([evidence[item["field_name"]] for item in head.content["field_evidence"]],
                                         str(revision_id))
    old = {item["field_name"]: {k: v for k, v in item.items() if k != "interpretation_revision"}
           for item in head.content["field_evidence"]}
    new = {item["field_name"]: {k: v for k, v in item.items() if k != "interpretation_revision"}
           for item in new_evidence}
    changed = sorted(name for name in new if old.get(name) != new.get(name))
    clarification = {"previous_revision_id": head.content["interpretation_revision_id"], "question_id": QUESTION_ID,
                     "question": (f"Adopt the market of recorded dataset {dataset.dataset_id} "
                                  f"({dataset.content['source_id']}, {dataset.content['evidence_class']}, "
                                  f"{dataset.content['content_label']}) with trade size {body.sizing_amount} and "
                                  f"limit {body.max_quote_notional} in {market['quote_unit']}, entering on declared rule "
                                  f"{rule['evaluation_id']} and exiting on the restated exit rule?"),
                     "answer_ref": f"choice:{QUESTION_ID}:adopt", "changed_fields": changed,
                     "preserved_restrictions": list(head.content["preserved_restrictions"]),
                     "resulting_revision_id": str(revision_id)}
    interp_content = copy.deepcopy(head.content)
    interp_content.update({"interpretation_revision_id": str(revision_id), "field_evidence": new_evidence,
                           "clarification_history": [clarification]})
    routed = route(intake.content, interp_content, service.INTERPRETER, None, strategy_id)
    if routed.outcome != "COMPILED" or routed.strategy is None:
        raise AppError(422, "VALIDATION", "INVALID_INPUT", "market_adoption_not_compiled", routed.findings or [
            finding("market_adoption_not_compiled", "/", "The adopted market does not form a valid strategy.")])
    operation_id = uuid.uuid4()
    moment = max(service.utcnow(), head.created_at + dt.timedelta(microseconds=1))
    interp = service.put_record(session, principal, "PromptInterpretation", interp_content, operation_id, moment,
                                record_id=revision_id, intake_id=intake.record_id, predecessor_id=head.record_id)
    service.put_record(session, principal, "Clarification", clarification, operation_id, moment,
                       intake_id=intake.record_id, predecessor_id=head.record_id, interpretation_id=interp.record_id)
    service.put_record(session, principal, "Outcome",
                       service.outcome_content(operation_id, intake.record_id, routed), operation_id, moment,
                       intake_id=intake.record_id, interpretation_id=interp.record_id)
    draft_id = uuid.uuid4()
    draft = {"draft_id": str(draft_id), "original_request": intake.content["original_request"],
             "interpretation_revision_id": str(revision_id), "source_syntax": routed.strategy,
             "validation_findings": [], "state": "DRAFT", "published_revision_id": None,
             "strategy_id": strategy_id, "base_revision_id": None if parent is None else str(parent)}
    service.put_record(session, principal, "StrategyDraft", draft, operation_id, moment, record_id=draft_id,
                       intake_id=intake.record_id, interpretation_id=interp.record_id)
    service.verify_lineage(session, principal, intake.record_id)
    adoption = {"interpretation_revision_id": str(revision_id), "draft_id": str(draft_id),
                "dataset_id": str(dataset.dataset_id), "dataset_content_sha256": dataset.content_sha256,
                "declaration_id": dataset.content["declaration_id"], "job_id": dataset.content["job_id"],
                "market_binding_id": dataset.content["market_binding_id"], "quote_unit": market["quote_unit"],
                "evaluation_id": rule["evaluation_id"], "rule_map_sha256": declaration.content["frozen"]["rule_map_sha256"],
                "base_revision_id": draft["base_revision_id"]}
    lineage = history_payload_binding.lineage(binding)
    if lineage is not None:  # additive: an adoption of an unbound dataset keeps its saved shape
        adoption["payload_binding"] = lineage
    inserted = session.execute(pg_insert(IdempotencyRecord).values(
        owner_id=principal.user_id, method="POST", path=path, idempotency_key=body.idempotency_key,
        fingerprint=fingerprint, revision_id=revision_id, response=adoption).on_conflict_do_nothing()
        .returning(IdempotencyRecord.revision_id)).first()
    if inserted is None:
        session.rollback()
        raise _conflict("idempotency_key_reused", "/idempotency_key", "This key was used concurrently. Reload.")
    session.commit()
    return 201, {"adoption": adoption, "replayed": False,
                 "bundle": service.load_bundle(session, principal, intake.record_id)}
