"""One read-only, dated agent health snapshot (`edge-os.agent-health-projection/1`, P31 LOCAL).

The canonical producer is `RecurringOperation.projection(owner_id, agent_id)`: the newest deployment and its newest
20 occurrences on the UTC five-minute grid. This module composes it with other accepted read sources and computes no
schedule, result or action of its own:

- `next_due_slot`, `no_next_reason`, `producer_silent` and `wait_reason` come from the producer only. Silence and the
  wait reason are values at the producer's read clock (`read_at`). The bounded pipeline's `next_scheduled_at` (last
  decision + 5 minutes) is never used as next work.
- `as_of` is the newest stored write of the saved deployment (`source_times`), named by table, id and field.
- Canonical pending reconciliation is the producer's unsettled queue. Account recovery cases and SUBMITTED_UNKNOWN
  monitoring are separately sourced warnings, never merged into one status.
- Stop and removal rows come from the accepted stop and removal reads; residual inventory from the account POSITION
  projection. Inputs no producer saves stay explicit UNKNOWN with a source-specific reason, never a default.

Every read is scoped by the verified owner and the saved agent/wallet/network/deployment. Nothing here writes or calls
a provider port.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.accounts.service_projection import project as account_projection
from edge_os_api.agent_health.source_times import deployment_source_times
from edge_os_api.execution.connected_identity import resolve_agent
from edge_os_api.execution.recurring_scheduler import OCCURRENCES_SHOWN, UNSETTLED_QUEUE
from edge_os_api.execution.types import utc_iso

SCHEMA_VERSION = "edge-os.agent-health-projection/1"
RECORD_TYPE = "AgentHealthProjection"
EVIDENCE_CLASS = "SERVICE_PROJECTION"
PRODUCER = {"name": "RecurringOperation.projection", "route": "GET /v1/agents/{agent_id}/deployment"}
NOTICE = ("Read-only service projection of this agent's saved records. In this build every observation, quote, "
          "transport and receipt is an authored fixture. It is not live trading evidence and grants no permission.")
# Producer inputs that no accepted source saves today. They stay UNKNOWN; full AUT06/P31 remains open.
PRODUCER_GAPS = (
    ("native_gas_aggregate", "PRODUCER_INPUT_MISSING: only per-receipt gas exists (GET /v1/actions/{action_id})"),
    ("dataset_qualification", "PRODUCER_INPUT_MISSING: no qualification verdict is linked to the deployment"),
    ("revision_edge_evidence", "PRODUCER_INPUT_MISSING: no revision-linked edge evidence is projected"),
    ("control_state_basis", "PRODUCER_INPUT_MISSING: the producer names stop modes and removal denials only"),
    ("selected_completion_outcome", "PRODUCER_INPUT_MISSING: no selected completion/outcome rule is agreed"),
    ("job_manifest_hash", "PRODUCER_INPUT_MISSING: job_view omits the saved job manifest_hash column"),
)
DIGEST_EXCLUDED = ("read_at", "snapshot_digest")


class HealthNotFound(Exception):
    """The verified owner has neither a saved deployment nor a confirmed wallet for this agent."""


def known(value: Any, source: str) -> dict[str, Any]:
    return {"state": "KNOWN", "value": value, "source": source}


def unknown(reason: str) -> dict[str, Any]:
    return {"state": "UNKNOWN", "reason": reason}


def _second(value: str) -> str:
    """One precision for every time: whole UTC seconds (the producer route already rounds; job_view does not)."""
    return utc_iso(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))


def _time(value: str | None, source: str, missing: str) -> dict[str, Any]:
    return unknown(missing) if value is None else known(_second(value), source)


def digest(snapshot: dict[str, Any]) -> str:
    """A stable identity of the snapshot's saved content; the read clock is excluded."""
    body = {key: value for key, value in snapshot.items() if key not in DIGEST_EXCLUDED}
    return "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _occurrence(item: dict[str, Any]) -> dict[str, Any]:
    evaluation, submission = item.get("evaluation"), item.get("submission")
    return {"job_id": item["job_id"], "decision_slot": _second(item["decision_slot"]), "job_state": item["state"],
            "job_outcome": item["outcome"], "job_reason": item["reason"], "action_id": item["action_id"],
            "job_updated_at": _second(item["updated_at"]),
            "evaluation": None if evaluation is None else {
                "outcome": evaluation["outcome"], "reason": evaluation["reason"],
                "inputs_observed_at": _time(evaluation["inputs_observed_at"], "evaluation.inputs_observed_at",
                                            "INPUT_OBSERVED_TIME_NOT_SAVED"),
                "inputs_collected_at": _time(evaluation["inputs_collected_at"], "evaluation.inputs_collected_at",
                                             "INPUT_COLLECTION_TIME_NOT_SAVED"),
                "evaluated_at": _time(evaluation["evaluated_at"], "evaluation.evaluated_at",
                                      "EVALUATION_TIME_NOT_SAVED"),
                "evidence_class": evaluation["evidence_class"]},
            "submission": None if submission is None else {
                "attempt_id": submission["attempt_id"], "state": submission["state"], "outcome": submission["outcome"],
                "started_at": _time(submission["started_at"], "submission.started_at", "ATTEMPT_START_NOT_SAVED"),
                "completed_at": _time(submission["completed_at"], "submission.completed_at",
                                      "ATTEMPT_NOT_COMPLETED")}}


def _last_evaluation(occurrences: list[dict[str, Any]]) -> dict[str, Any]:
    if not occurrences:
        return unknown("NO_OCCURRENCE_SAVED")
    for item in occurrences:
        if item["evaluation"] is not None:
            return known({key: item[key] for key in ("job_id", "decision_slot", "job_state", "evaluation")},
                         "producer.occurrences[].evaluation")
    return unknown("NO_EVALUATION_SAVED_IN_SHOWN_OCCURRENCES")


def _last_trade_attempt(occurrences: list[dict[str, Any]]) -> dict[str, Any]:
    for item in occurrences:
        if item["submission"] is not None:
            return known({key: item[key] for key in ("job_id", "decision_slot", "action_id", "job_outcome",
                                                     "submission")}, "producer.occurrences[].submission")
    return unknown("NO_SUBMISSION_IN_SHOWN_OCCURRENCES")


def _identity(saved: dict[str, Any] | None, current: Any) -> dict[str, Any]:
    current_view = unknown("AGENT_NOT_RESOLVED: no confirmed wallet bound to an exact saved revision") \
        if current is None else known(current.identity(), "resolve_agent (current resolution)")
    if saved is None:
        changed = unknown("NO_DEPLOYMENT")
    elif current is None:
        changed = unknown("AGENT_NOT_RESOLVED")
    else:
        # The producer's own identity comparison (RecurringOperation._authority_problem), read only.
        now = (current.wallet_id, current.network_id, str(current.publication_revision_id),
               current.revision.revision_id)
        then = (saved["wallet_id"], saved["network_id"], saved["publication_revision_id"],
                saved["execution_revision_id"])
        changed = known(now != then, "saved deployment identity vs current resolution")
    return {"saved_deployment": saved, "current_resolution": current_view, "changed": changed}


def read_health(factory: sessionmaker[Session], financial: Any, owner_id: uuid.UUID, agent_id: str) -> dict[str, Any]:
    view = financial.recurring.projection(owner_id, agent_id)
    deployment = view["deployment"]
    with factory() as session:
        current = resolve_agent(session, owner_id, agent_id)
        if deployment is None and current is None:
            raise HealthNotFound(agent_id)
        times = deployment_source_times(session, owner_id, uuid.UUID(deployment["deployment_id"])) \
            if deployment is not None else []
        records = account_projection(session, owner_id, agent_id)
        session.rollback()
    saved = deployment["identity"] if deployment is not None else None
    wallet_id = saved["wallet_id"] if saved else current.wallet_id
    network_id = saved["network_id"] if saved else current.network_id
    scope = {"owner_id": str(owner_id), "agent_id": agent_id, "wallet_id": wallet_id, "network_id": network_id,
             "deployment_id": deployment["deployment_id"] if deployment else None}

    def scoped(kind: str) -> list[dict[str, Any]]:
        return [item for item in records if item["content"]["record_kind"] == kind
                and item["content"]["wallet_id"] == wallet_id and item["content"]["network_id"] == network_id]

    stops = financial.stops.retrieve_stops(owner_id, agent_id=agent_id, wallet_id=wallet_id, network_id=network_id)
    removals = financial.removals.read_removal(owner_id, agent_id=agent_id, wallet_id=wallet_id, network_id=network_id)
    pipeline = financial.execution.status(owner_id, agent_id=agent_id, wallet_id=wallet_id, network_id=network_id)
    occurrences = [_occurrence(item) for item in view.get("occurrences", [])]
    producer = view.get("producer")
    read_at = view.get("read_at")

    if deployment is None:
        producer_view: dict[str, Any] = {"next_due_slot": unknown("NO_DEPLOYMENT"),
                                         "producer_silent": unknown("NO_DEPLOYMENT"),
                                         "last_tick_at": unknown("NO_DEPLOYMENT"),
                                         "cursor_slot": unknown("NO_DEPLOYMENT"),
                                         "missed_slots": unknown("NO_DEPLOYMENT"), "missed_intervals": [],
                                         "occurrences": unknown("NO_DEPLOYMENT")}
        wait = unknown("NO_DEPLOYMENT")
    else:
        producer_view = {
            "next_due_slot": known(producer["next_due_slot"], "producer.next_due_slot")
            if producer["next_due_slot"] else unknown(producer["no_next_reason"] or "NO_NEXT_SLOT"),
            "producer_silent": known(producer["producer_silent"], "producer.producer_silent at read_at"),
            "last_tick_at": _time(producer["last_tick_at"], "producer.last_tick_at", "PRODUCER_NEVER_TICKED"),
            "cursor_slot": _time(producer["cursor_slot"], "producer.cursor_slot", "NO_SLOT_SAVED"),
            "missed_slots": known(producer["missed_slots"], "producer.missed_slots"),
            "missed_intervals": producer["missed_intervals"],
            "occurrences": known(producer["occurrences"], "producer.occurrences")}
        wait = known(view["wait_reason"], "producer.wait_reason at read_at")

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "record_type": RECORD_TYPE, "evidence_class": EVIDENCE_CLASS,
        "record_id": "health:{owner_id}:{agent_id}:{wallet_id}:{network_id}:{deployment}".format(
            **scope, deployment=scope["deployment_id"] or "none"),
        "producer_source": PRODUCER, "notice": NOTICE, "provider_mode": financial.ports.mode,
        "read_at": read_at or utc_iso(dt.datetime.now(dt.timezone.utc)),
        "as_of": times[0].ref() if times else None,
        "as_of_meaning": "newest stored write among the named rows; not evidence that the producer advanced",
        "scope": scope,
        "deployment": None if deployment is None else {
            key: deployment[key] for key in ("deployment_id", "state", "end_reason", "activated_at", "ended_at")},
        "identity": _identity(saved, current),
        "producer": producer_view,
        "wait_reason": wait,
        "window": {"occurrences_shown": len(occurrences), "limit": OCCURRENCES_SHOWN},
        "occurrences": occurrences,
        "last_evaluation": _last_evaluation(occurrences),
        "last_trade_attempt": _last_trade_attempt(occurrences),
        "pending_reconciliation": {
            "canonical": {"rule": "PRODUCER_UNSETTLED_QUEUE", "queue_states": list(UNSETTLED_QUEUE),
                          "source": "producer.pending_reconciliation (execution_local.execution_queue)",
                          "action_ids": list(view.get("pending_reconciliation", []))}
            if deployment is not None else unknown("NO_DEPLOYMENT"),
            "warnings": [
                {"kind": "ACCOUNT_RECOVERY_OPEN_OR_UNKNOWN", "source": "recovery_local.recovery_cases (ACTION record)",
                 "action_ids": [item["content"]["action_id"] for item in scoped("ACTION")
                                if item["content"]["pending_reconciliation"]]},
                {"kind": "MONITORING_SUBMITTED_UNKNOWN",
                 "source": "execution_local.execution_evaluation_jobs (MONITORING record, agent wallet scope)",
                 "pending": any(item["content"]["pending_reconciliation"] for item in scoped("MONITORING"))}]},
        "controls": {
            "stops": [{"stop_id": str(stop.stop_id), "mode": stop.mode, "scope": stop.scope,
                       "position_id": stop.position_id, "trigger": stop.trigger, "created_at": _second(stop.created_at),
                       "source": "stops_local.scoped_stops"} for stop in stops],
            "removals": [{"request_id": str(item.request_id), "state": item.state, "reason": item.reason,
                          "requested_at": _second(item.requested_at), "updated_at": _second(item.updated_at),
                          "source": "revocation_local.removal_states"} for item in removals],
            "producer_stop_modes": list(view.get("stops", [])),
            "producer_removal_denials": list(view.get("removal", [])),
            "control_state_basis": unknown(PRODUCER_GAPS[3][1])},
        "residual_inventory": [{
            "position_id": item["content"]["position_id"], "asset_id": item["content"]["asset_id"],
            "quantity": item["content"]["quantity"], "position_state": item["content"]["position_state"],
            "updated_at": item["content"]["updated_at"], "time_field": "derived",
            "source": "admission_local.admission_positions (POSITION record)"} for item in scoped("POSITION")],
        "bounded_pipeline": {
            "scope": "agent wallet: manual and recurring evaluations",
            "last_decision_input_at": _time(pipeline.last_input_at, "ExecutionService.status.last_input_at",
                                            "NO_DECISION_SAVED"),
            "last_submission_attempt_at": _time(pipeline.last_attempt_at, "ExecutionService.status.last_attempt_at",
                                                "NO_SUBMISSION_ATTEMPT_SAVED"),
            "last_submission_completion_at": _time(pipeline.last_completion_at,
                                                   "ExecutionService.status.last_completion_at",
                                                   "NO_SUBMISSION_COMPLETED"),
            "blocking_reason": pipeline.blocking_reason,
            "next_scheduled_at": unknown("NOT_RECURRING_SCHEDULE: last decision + 5 minutes is not next work")},
        "unknown_inputs": [{"field": field, **unknown(reason)} for field, reason in PRODUCER_GAPS],
        "record_refs": [item.ref() for item in times],
    }
    snapshot["snapshot_digest"] = digest(snapshot)
    return snapshot
