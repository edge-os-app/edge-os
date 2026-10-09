"""Owner-scoped reads for persisted P15 account and monitoring records."""

from __future__ import annotations

import re
import uuid
from collections.abc import Generator
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from edge_os_api.auth import Principal, require_principal
from edge_os_api.errors import not_found, service_unavailable
from edge_os_api.models import Record
from edge_os_api.p02 import utc_string

router = APIRouter(prefix="/v1/account-views", tags=["account views"])
RECORD_TYPE = "AccountViewRecord"
SCHEMA_VERSION = "account-view/1"
OWNER_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AssetAmount(StrictModel):
    asset_id: str = Field(min_length=1, max_length=200)
    raw: str = Field(pattern=r"^(?:0|[1-9][0-9]*)$")
    decimals: int = Field(ge=0, le=255)


class ValueState(StrictModel):
    state: Literal["KNOWN", "UNKNOWN"]
    amount: AssetAmount | None = None

    @model_validator(mode="after")
    def amount_matches_state(self) -> "ValueState":
        if (self.state == "KNOWN") != (self.amount is not None):
            raise ValueError("known values require an amount; unknown values do not")
        return self


class AccountViewContent(StrictModel):
    owner_id: str
    evidence_class: Literal["SYNTHETIC_AUTHORED"]
    record_kind: Literal["AGENT", "POSITION", "ACTION", "CAPITAL_FLOW", "MONITORING", "EDGE_EVIDENCE"]
    agent_id: str = Field(min_length=1, max_length=200)
    wallet_id: str | None = None
    network_id: str | None = None
    asset_id: str | None = None
    position_id: str | None = None
    strategy_revision: str | None = None
    mandate_id: str | None = None
    action_id: str | None = None
    flow_id: str | None = None
    status: str = Field(min_length=1, max_length=80)
    updated_at: str = Field(min_length=1, max_length=40)
    quantity: AssetAmount | None = None
    wallet_balance: AssetAmount | None = None
    available_balance: AssetAmount | None = None
    reserved_amount: AssetAmount | None = None
    remaining_authority: AssetAmount | None = None
    native_gas: AssetAmount | None = None
    gas: AssetAmount | None = None
    basis: ValueState | None = None
    realized: ValueState | None = None
    unrealized: ValueState | None = None
    mark: ValueState | None = None
    position_state: Literal["OPEN", "CLOSED"] | None = None
    health: str | None = None
    permission_state: str | None = None
    flow_kind: Literal["DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT"] | None = None
    included_in_realized_result: bool | None = None
    reason: str | None = None
    evaluation_attempts: int | None = Field(default=None, ge=0)
    evaluation_completions: int | None = Field(default=None, ge=0)
    input_updated_at: str | None = None
    next_work: str | None = None
    blocking_reason: str | None = None
    pending_reconciliation: bool | None = None
    edge_revision: str | None = None
    edge_evidence_status: str | None = None

    @field_validator("owner_id")
    @classmethod
    def require_canonical_owner_id(cls, value: str) -> str:
        if not OWNER_ID.fullmatch(value):
            raise ValueError("owner_id must be a canonical UUID")
        return value

    @model_validator(mode="after")
    def require_kind_identity(self) -> "AccountViewContent":
        required = {
            "AGENT": (self.wallet_id, self.network_id),
            "POSITION": (self.wallet_id, self.network_id, self.asset_id, self.position_id,
                         self.strategy_revision, self.mandate_id, self.quantity, self.position_state),
            "ACTION": (self.wallet_id, self.network_id, self.action_id),
            "CAPITAL_FLOW": (self.wallet_id, self.network_id, self.flow_id, self.flow_kind, self.quantity),
            "MONITORING": (self.wallet_id, self.network_id, self.health, self.evaluation_attempts,
                           self.evaluation_completions, self.pending_reconciliation),
            "EDGE_EVIDENCE": (self.strategy_revision, self.edge_revision, self.edge_evidence_status),
        }[self.record_kind]
        if any(value is None for value in required):
            raise ValueError(f"{self.record_kind} is missing a required identity or state")
        if self.record_kind == "ACTION":
            position_binding = (self.position_id, self.strategy_revision, self.mandate_id, self.asset_id)
            if self.position_id is not None and any(value is None for value in position_binding):
                raise ValueError("position actions require the exact strategy, mandate and asset binding")
            if self.position_id is None and self.flow_id is None:
                raise ValueError("wallet-level actions require an explicit capital-flow identity")
        if self.record_kind == "CAPITAL_FLOW" and self.included_in_realized_result is not False:
            raise ValueError("capital flows must remain separate from realized trading results")
        statuses = {
            "AGENT": {"REQUESTED", "PENDING", "UNKNOWN", "CONFIRMED", "FAILED", "RUNNING", "STOPPED"},
            "POSITION": {"OPEN", "CLOSED"},
            "ACTION": {"PROPOSED", "QUEUED", "SUBMITTED", "CONFIRMED", "REVERTED", "DENIED", "CANCELLED", "SUBMISSION_UNKNOWN"},
            "CAPITAL_FLOW": {"REQUESTED", "PENDING", "UNKNOWN", "CONFIRMED", "FAILED"},
            "MONITORING": {"RUNNING", "STALE", "STOPPED", "UNKNOWN", "BLOCKED"},
            "EDGE_EVIDENCE": {"HYPOTHESIS", "DESCRIPTIVE_ONLY", "UNRESOLVED", "SUPPORTED", "CONFLICTED"},
        }
        if self.status not in statuses[self.record_kind]:
            raise ValueError(f"{self.record_kind} has an unsupported status")
        if self.record_kind == "POSITION" and self.status != self.position_state:
            raise ValueError("position status must match its open or closed state")
        if self.quantity is not None and self.asset_id not in (None, self.quantity.asset_id):
            raise ValueError("record asset and quantity asset must match")
        return self


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def _record_dict(row: Record, owner_id: uuid.UUID) -> dict[str, Any]:
    try:
        content = AccountViewContent.model_validate(row.content)
    except ValidationError as error:
        raise service_unavailable("RECONCILE") from error
    if content.owner_id != str(owner_id) or row.schema_version != SCHEMA_VERSION:
        raise service_unavailable("RECONCILE")
    return {
        "schema_version": row.schema_version,
        "record_type": row.record_type,
        "record_id": str(row.record_id),
        "owner_id": str(row.owner_id),
        "operation_id": str(row.operation_id),
        "created_at": utc_string(row.created_at),
        "content": content.model_dump(mode="json"),
    }


def _owned_record(session: Session, principal: Principal, record_id: str) -> Record:
    try:
        parsed = uuid.UUID(record_id)
    except (ValueError, TypeError, AttributeError):
        raise not_found() from None
    row = session.execute(select(Record).where(
        Record.owner_id == principal.user_id,
        Record.record_id == parsed,
        Record.record_type == RECORD_TYPE,
    )).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


def _list_records(
    session: Session,
    principal: Principal,
    filters: dict[str, str | None],
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int | None]:
    try:
        statement = select(Record).where(
            Record.owner_id == principal.user_id,
            Record.record_type == RECORD_TYPE,
        )
        for key, value in filters.items():
            if value is not None:
                statement = statement.where(Record.content[key].astext == value)
        rows = session.execute(statement.order_by(Record.seq).offset(offset).limit(limit + 1)).scalars().all()
        page = rows[:limit]
        records = [_record_dict(row, principal.user_id) for row in page]
        next_offset = offset + limit if len(rows) > limit else None
        return records, next_offset
    except SQLAlchemyError:
        session.rollback()
        raise service_unavailable() from None


@router.get("")
def list_account_records(
    agent_id: str | None = Query(default=None, max_length=200),
    wallet_id: str | None = Query(default=None, max_length=200),
    asset_id: str | None = Query(default=None, max_length=200),
    position_id: str | None = Query(default=None, max_length=200),
    strategy_revision: str | None = Query(default=None, max_length=200),
    record_kind: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """List records for the verified owner and apply exact identity filters."""
    records, next_offset = _list_records(session, principal, {
        "agent_id": agent_id, "wallet_id": wallet_id, "asset_id": asset_id,
        "position_id": position_id, "strategy_revision": strategy_revision, "record_kind": record_kind,
    }, limit, offset)
    return {"records": records, "next_offset": next_offset}


@router.get("/{record_id}")
def get_account_record(
    record_id: str,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return one record only when its exact ID belongs to the verified owner."""
    try:
        return _record_dict(_owned_record(session, principal, record_id), principal.user_id)
    except SQLAlchemyError:
        session.rollback()
        raise service_unavailable() from None
