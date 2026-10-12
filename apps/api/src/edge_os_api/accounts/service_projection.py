"""Read-only account projections from the connected financial state (#58 F1).

The account views have shown authored P19 records only. This module projects the owner's own saved funding,
admission, execution, recovery and removal rows into the same `AccountViewContent` shapes, labelled
`evidence_class = SERVICE_PROJECTION`. It writes nothing and never changes domain accounting. Unknown values stay
UNKNOWN: no mark exists, so estimated unrealized results and marks are UNKNOWN; deposits are capital flows, never
holdings; a flow without a credit keeps its declared amount and its uncredited status. In fixture execution mode the
rows come from fixture provider ports, and the response says so.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from edge_os_api.accounts.views import AccountViewContent
from edge_os_api.admission.models import PositionRow, ReceiptRow
from edge_os_api.execution.models import EvaluationJobRow, IntentRow, QueueRow
from edge_os_api.funding.persistence import FundingCreditRow, FundingFlowRow, FundingProfileRow
from edge_os_api.records.contract_adapter import utc_string
from edge_os_api.recovery.models import RecoveryCaseRow
from edge_os_api.revocation.records import RemovalStateRow

PROJECTION_VERSION = "account-view-projection/1"
FLOW_KINDS = {"DEPOSIT": "DEPOSIT", "WITHDRAWAL": "WITHDRAWAL"}
UNSETTLED_JOB_OUTCOMES = {"SUBMITTED_UNKNOWN"}
# Domain states mapped onto the accepted account-view vocabulary (views.AccountViewContent). Anything not listed maps
# to the vocabulary's unknown or pending value, never to a success.
ACTION_STATUS = {"CONFIRMED": "CONFIRMED", "REVERTED": "REVERTED", "SUBMISSION_UNKNOWN": "SUBMISSION_UNKNOWN",
                 "SUBMITTED_CONFIRMED": "CONFIRMED", "SUBMITTED_REVERTED": "REVERTED",
                 "SUBMITTED_UNKNOWN": "SUBMISSION_UNKNOWN", "QUEUED": "QUEUED", "CLAIMED": "SUBMITTED",
                 "DENIED_UNSENT": "DENIED", "ADMISSION_DENIED": "DENIED", "REVALIDATION_DENIED": "DENIED",
                 "BREACHED": "DENIED", "SUBMISSION_NOT_OWNED": "DENIED", "RECONCILE_MISMATCH": "SUBMISSION_UNKNOWN"}
PROJECTION_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)  # a position without any saved action (none expected)
FLOW_STATUS = {"REQUESTED": "REQUESTED", "PENDING": "PENDING", "UNKNOWN": "UNKNOWN", "FAILED": "FAILED"}


def _raw(value: Decimal | int) -> str:
    return str(int(value))


def _amount(asset_id: str, raw: Decimal | int, decimals: int) -> dict[str, Any]:
    return {"asset_id": asset_id, "raw": _raw(raw), "decimals": int(decimals)}


def _signed(asset_id: str, raw: Decimal | int, decimals: int) -> dict[str, Any]:
    return {"asset_id": asset_id, "raw": str(int(raw)), "decimals": int(decimals)}


def _record(kind: str, key: str, source: dict[str, str], content: dict[str, Any]) -> dict[str, Any]:
    """Validate against the accepted account-view content model before returning anything."""
    checked = AccountViewContent.model_validate(content).model_dump(mode="json")
    return {"schema_version": PROJECTION_VERSION, "record_type": "AccountViewProjection",
            "record_id": f"projection:{kind.lower()}:{key}", "source": source, "content": checked}


def project(session: Session, owner_id: uuid.UUID, agent_id: str | None = None) -> list[dict[str, Any]]:
    """Every projection for the verified owner, optionally for one agent. Reads only."""
    owner = str(owner_id)

    def rows(model: Any) -> list[Any]:
        statement = select(model).where(model.owner_id == owner_id)
        if agent_id is not None:
            statement = statement.where(model.agent_id == agent_id)
        return list(session.execute(statement).scalars())

    records: list[dict[str, Any]] = []
    removals = {(row.agent_id, row.wallet_id): row for row in rows(RemovalStateRow)}
    for profile in rows(FundingProfileRow):
        removal = removals.get((profile.agent_id, profile.wallet_id))
        records.append(_record("AGENT", profile.agent_id, {"table": "funding_local.funding_profiles",
                                                           "id": str(profile.profile_id)}, {
            "owner_id": owner, "evidence_class": "SERVICE_PROJECTION", "record_kind": "AGENT",
            "agent_id": profile.agent_id, "wallet_id": profile.wallet_id, "network_id": str(profile.network_id),
            "status": "STOPPED" if removal is not None else "CONFIRMED", "updated_at": utc_string(profile.updated_at),
            "permission_state": "REMOVAL_" + removal.state if removal is not None else "NO_REMOVAL_REQUESTED"}))

    credits: dict[uuid.UUID, list[FundingCreditRow]] = defaultdict(list)
    for credit in rows(FundingCreditRow):
        credits[credit.flow_id].append(credit)
    for flow in rows(FundingFlowRow):
        credited = credits.get(flow.flow_id, [])
        quantity = (_amount(flow.asset_id, sum(item.actual_raw for item in credited), flow.decimals) if credited
                    else _amount(flow.asset_id, flow.declared_raw, flow.decimals))
        records.append(_record("CAPITAL_FLOW", str(flow.flow_id), {"table": "funding_local.funding_flows",
                                                                    "id": str(flow.flow_id)}, {
            "owner_id": owner, "evidence_class": "SERVICE_PROJECTION", "record_kind": "CAPITAL_FLOW",
            "agent_id": flow.agent_id, "wallet_id": flow.wallet_id, "network_id": str(flow.network_id),
            "asset_id": flow.asset_id, "flow_id": str(flow.flow_id),
            "flow_kind": FLOW_KINDS.get(flow.kind, "TRANSFER_IN"),
            "status": "CONFIRMED" if credited else FLOW_STATUS.get(flow.state, "PENDING"),
            "updated_at": utc_string(flow.updated_at),
            "quantity": quantity, "included_in_realized_result": False,
            "reason": None if credited else "Declared amount; no credit has been observed for this flow."}))

    receipts: dict[str, ReceiptRow] = {}
    for receipt in sorted(rows(ReceiptRow), key=lambda item: item.created_at):
        receipts[receipt.action_id] = receipt
    intents = rows(IntentRow)
    # Positions have no timestamp of their own: use the latest saved receipt or intent of the position, so a
    # re-read returns the same value (never the read time).
    position_times: dict[str, dt.datetime] = {}
    for intent in intents:
        receipt = receipts.get(intent.action_id)
        moment = receipt.created_at if receipt is not None else intent.created_at
        if intent.position_id and (intent.position_id not in position_times or moment > position_times[intent.position_id]):
            position_times[intent.position_id] = moment

    positions = rows(PositionRow)
    position_assets = {row.position_id: row.asset_id for row in positions}
    for position in positions:
        open_ = position.inventory > 0
        records.append(_record("POSITION", position.position_id, {"table": "admission_local.admission_positions",
                                                                  "id": position.position_id}, {
            "owner_id": owner, "evidence_class": "SERVICE_PROJECTION", "record_kind": "POSITION",
            "agent_id": position.agent_id, "wallet_id": position.wallet_id, "network_id": position.network_id,
            "asset_id": position.asset_id, "position_id": position.position_id,
            "strategy_revision": position.strategy_revision, "mandate_id": position.mandate_id,
            "status": "OPEN" if open_ else "CLOSED", "position_state": "OPEN" if open_ else "CLOSED",
            "updated_at": utc_string(position_times.get(position.position_id, PROJECTION_EPOCH)),
            "quantity": _amount(position.asset_id, position.inventory, position.decimals),
            "basis": {"state": "KNOWN", "amount": _amount(position.quote_asset_id, position.cost_basis,
                                                          position.quote_decimals)},
            "realized_result": {"state": "KNOWN", "amount": _signed(position.quote_asset_id, position.realized_quote,
                                                                    position.quote_decimals)},
            "estimated_unrealized_result": {"state": "UNKNOWN"}, "mark": {"state": "UNKNOWN"}}))

    queues = {row.action_id: row for row in rows(QueueRow)}
    open_cases = {row.action_id for row in rows(RecoveryCaseRow) if row.state in {"OPEN", "UNKNOWN"}}
    for intent in intents:
        receipt = receipts.get(intent.action_id)
        queue = queues.get(intent.action_id)
        raw_status = receipt.outcome if receipt is not None else (queue.state if queue is not None else "PROPOSED")
        status = ACTION_STATUS.get(raw_status, "PROPOSED")
        records.append(_record("ACTION", intent.action_id, {"table": "execution_local.execution_intents",
                                                            "id": intent.intent_id}, {
            "owner_id": owner, "evidence_class": "SERVICE_PROJECTION", "record_kind": "ACTION",
            "agent_id": intent.agent_id, "wallet_id": intent.wallet_id, "network_id": intent.network_id,
            "action_id": intent.action_id, "position_id": intent.position_id,
            "asset_id": position_assets.get(intent.position_id)
            or (intent.payload.get("quantity") or {}).get("asset_id"),
            "strategy_revision": intent.revision_id, "mandate_id": intent.mandate_id, "status": status,
            "updated_at": utc_string(receipt.created_at if receipt is not None else intent.created_at),
            "pending_reconciliation": intent.action_id in open_cases,
            "reason": intent.admission_reason}))

    jobs: dict[tuple[str, str, str], list[EvaluationJobRow]] = defaultdict(list)
    for job in rows(EvaluationJobRow):
        jobs[(job.agent_id, job.wallet_id, job.network_id)].append(job)
    for (agent, wallet, network), items in jobs.items():
        pending = any(item.outcome in UNSETTLED_JOB_OUTCOMES for item in items)
        records.append(_record("MONITORING", f"{agent}:{wallet}", {"table": "execution_local.execution_evaluation_jobs",
                                                                   "id": f"{agent}:{wallet}:{network}"}, {
            "owner_id": owner, "evidence_class": "SERVICE_PROJECTION", "record_kind": "MONITORING",
            "agent_id": agent, "wallet_id": wallet, "network_id": network,
            # No worker heartbeat is projected, so a settled agent is UNKNOWN rather than RUNNING.
            "status": "BLOCKED" if pending else "UNKNOWN", "health": "ATTENTION" if pending else "OK",
            "updated_at": utc_string(max(item.updated_at for item in items)),
            "evaluation_attempts": len(items),
            "evaluation_completions": sum(item.state == "COMPLETED" for item in items),
            "pending_reconciliation": pending,
            "next_work": "Reconcile the original action before another evaluation." if pending else None}))
    return records
