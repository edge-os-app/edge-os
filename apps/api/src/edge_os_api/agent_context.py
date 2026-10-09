"""Versioned owner controls for one agent's stored context."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Generator
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from edge_os_api.auth import Principal, require_principal
from edge_os_api.errors import AppError, finding, invalid, not_found, service_unavailable
from edge_os_api.models import Record, User
from edge_os_api.p02 import utc_string

router = APIRouter(prefix="/v1/agents/{agent_id}/context", tags=["agent context"])
RECORD_TYPE = "AgentContextRecord"
SCHEMA_VERSION = "agent-context/1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ContextEntry(StrictModel):
    context_id: str = Field(min_length=1, max_length=200)
    kind: Literal["PREFERENCE", "CORRECTION", "LESSON"]
    status: Literal["ADOPTED", "SUGGESTED"]
    text: str = Field(min_length=1, max_length=2000)
    source_refs: list[str] = Field(max_length=20)


class ContextContent(StrictModel):
    owner_id: str
    agent_id: str = Field(min_length=1, max_length=200)
    memory_version: int = Field(ge=0)
    state: Literal["ACTIVE", "DISABLED", "CLEARED"]
    entries: list[ContextEntry] = Field(max_length=100)


class CorrectionBody(StrictModel):
    expected_version: int = Field(ge=0)
    context_id: str = Field(min_length=1, max_length=200)
    replacement: str = Field(min_length=1, max_length=2000)


class VersionBody(StrictModel):
    expected_version: int = Field(ge=0)


class AdoptionBody(VersionBody):
    context_id: str = Field(min_length=1, max_length=200)


def _validate_agent_id(agent_id: str) -> None:
    if not agent_id or len(agent_id) > 200:
        raise invalid("/agent_id", "The agent ID must contain between 1 and 200 characters.")


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def _latest(session: Session, owner_id: uuid.UUID, agent_id: str) -> Record | None:
    return session.execute(select(Record).where(
        Record.owner_id == owner_id,
        Record.record_type == RECORD_TYPE,
        Record.content["agent_id"].astext == agent_id,
    ).order_by(Record.seq.desc()).limit(1)).scalar_one_or_none()


def _content(row: Record | None, owner_id: uuid.UUID, agent_id: str) -> ContextContent:
    if row is None:
        return ContextContent(owner_id=str(owner_id), agent_id=agent_id, memory_version=0,
                              state="ACTIVE", entries=[])
    try:
        result = ContextContent.model_validate(row.content)
    except ValueError as error:
        raise service_unavailable("RECONCILE") from error
    if (result.owner_id != str(owner_id) or result.agent_id != agent_id
            or result.memory_version < 1 or row.schema_version != SCHEMA_VERSION):
        raise service_unavailable("RECONCILE")
    return result


def _source_ids(content: ContextContent) -> list[uuid.UUID]:
    try:
        parsed = [uuid.UUID(source_ref) for entry in content.entries for source_ref in entry.source_refs]
    except (ValueError, TypeError, AttributeError):
        raise service_unavailable("RECONCILE") from None
    return list(dict.fromkeys(parsed))


def _verify_sources(session: Session, principal: Principal, content: ContextContent) -> None:
    source_ids = _source_ids(content)
    if not source_ids:
        return
    try:
        found = set(session.execute(select(Record.record_id).where(
            Record.owner_id == principal.user_id,
            Record.record_id.in_(source_ids),
        )).scalars())
    except SQLAlchemyError:
        session.rollback()
        raise service_unavailable("RECONCILE") from None
    if found != set(source_ids):
        raise not_found("context source")


def _response(session: Session, principal: Principal, content: ContextContent) -> dict[str, Any]:
    try:
        _verify_sources(session, principal, content)
        return content.model_dump(mode="json")
    except SQLAlchemyError:
        session.rollback()
        raise service_unavailable("RECONCILE") from None


def _current(session: Session, principal: Principal, agent_id: str) -> ContextContent:
    _validate_agent_id(agent_id)
    try:
        return _content(_latest(session, principal.user_id, agent_id), principal.user_id, agent_id)
    except SQLAlchemyError:
        session.rollback()
        raise service_unavailable("RECONCILE") from None


def _write(
    session: Session,
    principal: Principal,
    agent_id: str,
    expected_version: int,
    state: Literal["ACTIVE", "DISABLED", "CLEARED"] | None = None,
    entries: list[ContextEntry] | None = None,
) -> ContextContent:
    _validate_agent_id(agent_id)
    try:
        session.execute(select(User.id).where(User.id == principal.user_id).with_for_update()).scalar_one()
        current_row = _latest(session, principal.user_id, agent_id)
        current = _content(current_row, principal.user_id, agent_id)
        if current.memory_version != expected_version:
            raise AppError(409, "WRITE", "CONFLICTED", "context_version_conflict",
                           [finding("context_version_conflict", "/expected_version",
                                    "Context changed. Reload it and review the current version.")])
        if (state or current.state) != "CLEARED":
            _verify_sources(session, principal, current)
        next_content = ContextContent(
            owner_id=str(principal.user_id), agent_id=agent_id,
            memory_version=current.memory_version + 1,
            state=state or current.state,
            entries=current.entries if entries is None else entries,
        )
        now = dt.datetime.now(dt.timezone.utc)
        row = Record(
            record_id=uuid.uuid4(), owner_id=principal.user_id, record_type=RECORD_TYPE,
            schema_version=SCHEMA_VERSION, operation_id=uuid.uuid4(), created_at=now,
            content=next_content.model_dump(mode="json"),
        )
        session.add(row)
        session.commit()
        return next_content
    except AppError:
        session.rollback()
        raise
    except SQLAlchemyError:
        session.rollback()
        raise service_unavailable("RECONCILE") from None


def get_agent_context(
    agent_id: str,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Inspect the verified owner's latest version for the named agent."""
    if not agent_id:
        raise invalid("/agent_id", "The agent ID is required.")
    return _response(session, principal, _current(session, principal, agent_id))


def correct_context(
    agent_id: str,
    body: CorrectionBody,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Append a corrected version while preserving the agent's enabled state."""
    current = _current(session, principal, agent_id)
    updated: list[ContextEntry] = []
    changed = False
    for entry in current.entries:
        if entry.context_id == body.context_id and entry.status == "ADOPTED":
            updated.append(entry.model_copy(update={"text": body.replacement, "kind": "CORRECTION"}))
            changed = True
        else:
            updated.append(entry)
    if not changed:
        raise not_found("adopted context")
    next_content = _write(session, principal, agent_id, body.expected_version, entries=updated)
    return _response(session, principal, next_content)


def adopt_suggestion(
    agent_id: str,
    body: AdoptionBody,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Append a version that adopts one existing suggested lesson."""
    current = _current(session, principal, agent_id)
    updated: list[ContextEntry] = []
    changed = False
    for entry in current.entries:
        if entry.context_id == body.context_id and entry.status == "SUGGESTED":
            updated.append(entry.model_copy(update={"status": "ADOPTED"}))
            changed = True
        else:
            updated.append(entry)
    if not changed:
        raise not_found("suggested context")
    next_content = _write(session, principal, agent_id, body.expected_version, entries=updated)
    return _response(session, principal, next_content)


def disable_context(
    agent_id: str,
    body: VersionBody,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Append a disabled version; future task retrieval omits its entries."""
    next_content = _write(session, principal, agent_id, body.expected_version, state="DISABLED")
    return _response(session, principal, next_content)


def clear_context(
    agent_id: str,
    body: VersionBody,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Append a cleared version without changing account or permission records."""
    next_content = _write(session, principal, agent_id, body.expected_version,
                          state="CLEARED", entries=[])
    return _response(session, principal, next_content)


def retrieve_agent_context(
    session: Session,
    principal: Principal,
    authorized_agent_id: str,
    requested_agent_id: str,
) -> tuple[int, list[dict[str, str]]]:
    """Return adopted text only for the agent authorized by the caller's trusted task scope."""
    if not authorized_agent_id or requested_agent_id != authorized_agent_id:
        raise not_found("agent context")
    _validate_agent_id(authorized_agent_id)
    content = _current(session, principal, authorized_agent_id)
    _verify_sources(session, principal, content)
    if content.state != "ACTIVE":
        return content.memory_version, []
    return content.memory_version, [
        {"context_id": entry.context_id, "text": entry.text}
        for entry in content.entries if entry.status == "ADOPTED"
    ]


router.add_api_route("", get_agent_context, methods=["GET"])
router.add_api_route("/corrections", correct_context, methods=["POST"])
router.add_api_route("/suggestions/adopt", adopt_suggestion, methods=["POST"])
router.add_api_route("/disable", disable_context, methods=["POST"])
router.add_api_route("/clear", clear_context, methods=["POST"])
