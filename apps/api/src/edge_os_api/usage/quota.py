"""Shared owner and global usage quotas in PostgreSQL.

A reservation binds one original subject (for example an investigation job) to an owner and to fixed amounts of each
resource. It is taken under row locks on the GLOBAL allocation, then the OWNER allocation, so two processes cannot
both take the last capacity. Settlement is idempotent per resource: a known measurement consumes the full measured
use, releases only the unused part and records any excess as overrun; an unknown outcome keeps the whole open amount
as unknown liability. Nothing here resets, credits or renews capacity.

Caps are frozen when an allocation is first created. A different configured value later is never applied silently:
reservations are refused with `quota_cap_mismatch` and readiness reports it, until an operator records an explicit
cap change with `python -m edge_os_api.usage.quota set-cap`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    MetaData,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

RESOURCES = ("provider_requests", "compute_seconds")
GLOBAL_OWNER = uuid.UUID(int=0)  # the GLOBAL scope's owner key; never a real owner id

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "pk": "%(table_name)s_pkey",
}


class UsageBase(DeclarativeBase):
    """Migration 0010 creates these tables in the `usage_local` schema."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="usage_local")


class AllocationRow(UsageBase):
    __tablename__ = "usage_allocations"
    allocation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    owner_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    cap: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cap_source: Mapped[str] = mapped_column(Text, nullable=False)
    reserved: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    consumed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    unknown: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    overrun: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frozen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("scope", "owner_key", "resource", name="uq_usage_allocation_scope"),
        CheckConstraint("scope IN ('GLOBAL', 'OWNER')", name="scope"),
        CheckConstraint("cap >= 0 AND reserved >= 0 AND consumed >= 0 AND unknown >= 0 AND overrun >= 0",
                        name="amounts"),
    )


class ReservationRow(UsageBase):
    __tablename__ = "usage_reservations"
    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    subject_kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    amounts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    settled: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("subject_kind", "subject_id", name="uq_usage_reservation_subject"),)


class UsageEventRow(UsageBase):
    """Append-only history of grants, refusals, settlements and explicit cap changes."""

    __tablename__ = "usage_events"
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True)
class Caps:
    """Configured caps per resource for the owner scope and the global scope."""

    owner: Mapping[str, int]
    global_: Mapping[str, int]
    # The GLOBAL row's key. The application always uses GLOBAL_OWNER; tests isolate a global scope with their own key.
    global_key: uuid.UUID = GLOBAL_OWNER


class CapMismatch(RuntimeError):
    """A stored cap differs from the configured cap. Nothing is reserved until an operator decides."""

    def __init__(self, scope: str, resource: str, stored: int, configured: int) -> None:
        super().__init__(f"{scope} {resource} cap is {stored}; configuration says {configured}")
        self.scope, self.resource, self.stored, self.configured = scope, resource, stored, configured


@dataclass(frozen=True)
class Grant:
    reservation: ReservationRow
    replayed: bool


@dataclass(frozen=True)
class Refusal:
    scope: str
    resource: str
    requested: int
    available: int


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _available(row: AllocationRow) -> int:
    return row.cap - row.reserved - row.consumed - row.unknown


def _allocation(session: Session, scope: str, owner_key: uuid.UUID, resource: str, configured: int,
                *, lock: bool) -> AllocationRow:
    now = utcnow()
    session.execute(pg_insert(AllocationRow).values(
        allocation_id=uuid.uuid4(), scope=scope, owner_key=owner_key, resource=resource, cap=configured,
        cap_source="configuration-at-first-use", reserved=0, consumed=0, unknown=0, overrun=0, frozen_at=now,
        updated_at=now).on_conflict_do_nothing(constraint="uq_usage_allocation_scope"))
    statement = select(AllocationRow).where(AllocationRow.scope == scope, AllocationRow.owner_key == owner_key,
                                            AllocationRow.resource == resource)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = session.execute(statement).scalar_one()
    if row.cap != configured:
        raise CapMismatch(scope, resource, row.cap, configured)
    return row


def _locked_rows(session: Session, owner_id: uuid.UUID, caps: Caps) -> list[AllocationRow]:
    """GLOBAL rows first, then OWNER rows, each in resource order: one lock order for every process."""
    rows = [_allocation(session, "GLOBAL", caps.global_key, resource, caps.global_[resource], lock=True)
            for resource in RESOURCES]
    rows += [_allocation(session, "OWNER", owner_id, resource, caps.owner[resource], lock=True)
             for resource in RESOURCES]
    return rows


def _event(session: Session, kind: str, owner_id: uuid.UUID | None, reservation_id: uuid.UUID | None,
           content: dict[str, Any]) -> None:
    session.add(UsageEventRow(kind=kind, owner_id=owner_id, reservation_id=reservation_id, content=content,
                              created_at=utcnow()))


def existing(session: Session, subject_kind: str, subject_id: str) -> ReservationRow | None:
    return session.execute(select(ReservationRow).where(ReservationRow.subject_kind == subject_kind,
                                                        ReservationRow.subject_id == subject_id)).scalar_one_or_none()


def reserve(session: Session, owner_id: uuid.UUID, subject_kind: str, subject_id: str,
            amounts: Mapping[str, int], caps: Caps) -> Grant | Refusal:
    """Reserve fixed amounts for one original subject against both caps. The caller commits.

    A repeated subject returns its original reservation. A refusal changes no allocation.
    """
    prior = existing(session, subject_kind, subject_id)
    if prior is not None:
        return Grant(prior, replayed=True)
    rows = _locked_rows(session, owner_id, caps)
    prior = existing(session, subject_kind, subject_id)  # re-read under the locks
    if prior is not None:
        return Grant(prior, replayed=True)
    for row in rows:
        requested = int(amounts[row.resource])
        if _available(row) < requested:
            refusal = Refusal(row.scope, row.resource, requested, _available(row))
            _event(session, "REFUSED", owner_id, None, {"subject": [subject_kind, subject_id],
                                                        "scope": row.scope, "resource": row.resource,
                                                        "requested": requested, "available": _available(row)})
            return refusal
    now = utcnow()
    for row in rows:
        row.reserved += int(amounts[row.resource])
        row.updated_at = now
    reservation = ReservationRow(reservation_id=uuid.uuid4(), owner_id=owner_id, subject_kind=subject_kind,
                                 subject_id=subject_id, amounts={key: int(amounts[key]) for key in RESOURCES},
                                 settled={}, created_at=now)
    session.add(reservation)
    session.flush()
    _event(session, "RESERVED", owner_id, reservation.reservation_id, {"amounts": reservation.amounts})
    return Grant(reservation, replayed=False)


def settle(session: Session, reservation: ReservationRow, resource: str, kind: str, measured: int,
           caps: Caps) -> dict[str, int] | None:
    """Settle one resource of a reservation once. `kind` is KNOWN or UNKNOWN. Returns the booked amounts, or
    None when that resource was already settled (a duplicate settlement changes nothing)."""
    if kind not in {"KNOWN", "UNKNOWN"} or resource not in RESOURCES:
        raise ValueError("settle needs KNOWN or UNKNOWN and a known resource")
    rows = [row for row in _locked_rows(session, reservation.owner_id, caps) if row.resource == resource]
    current = session.execute(select(ReservationRow).where(
        ReservationRow.reservation_id == reservation.reservation_id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one()
    if resource in current.settled:
        return None
    reserved = int(current.amounts[resource])
    if kind == "UNKNOWN":
        booked = {"consumed": 0, "unknown": reserved, "released": 0, "overrun": 0}
    else:
        used = max(int(measured), 0)
        booked = {"consumed": used, "unknown": 0, "released": max(reserved - used, 0),
                  "overrun": max(used - reserved, 0)}
    now = utcnow()
    for row in rows:
        row.reserved -= reserved
        row.consumed += booked["consumed"]
        row.unknown += booked["unknown"]
        row.overrun += booked["overrun"]
        row.updated_at = now
    current.settled = {**current.settled, resource: {"kind": kind, **booked, "at": now.isoformat()}}
    _event(session, "SETTLED", current.owner_id, current.reservation_id,
           {"resource": resource, "kind": kind, **booked})
    return booked


def view(session: Session, owner_id: uuid.UUID, caps: Caps) -> dict[str, Any]:
    """Owner totals plus the global remaining capacity. Reads only; creates nothing."""
    rows = session.execute(select(AllocationRow).where(
        ((AllocationRow.scope == "OWNER") & (AllocationRow.owner_key == owner_id))
        | ((AllocationRow.scope == "GLOBAL") & (AllocationRow.owner_key == caps.global_key)))).scalars().all()
    by_key = {(row.scope, row.resource): row for row in rows}

    def totals(scope: str, configured: Mapping[str, int]) -> dict[str, Any]:
        result: dict[str, Any] = {name: {} for name in ("limits", "reserved", "consumed", "unknown_liability",
                                                        "overrun", "available")}
        for resource in RESOURCES:
            row = by_key.get((scope, resource))
            cap = configured[resource] if row is None else row.cap
            values = (0, 0, 0, 0) if row is None else (row.reserved, row.consumed, row.unknown, row.overrun)
            result["limits"][resource] = cap
            result["reserved"][resource], result["consumed"][resource] = values[0], values[1]
            result["unknown_liability"][resource], result["overrun"][resource] = values[2], values[3]
            result["available"][resource] = cap - values[0] - values[1] - values[2]
        return result

    owner = totals("OWNER", caps.owner)
    owner["global_available"] = totals("GLOBAL", caps.global_)["available"]
    return owner


def cap_mismatches(session: Session, caps: Caps) -> list[dict[str, Any]]:
    """Stored GLOBAL caps that differ from configuration (readiness evidence; no write)."""
    rows = session.execute(select(AllocationRow).where(AllocationRow.scope == "GLOBAL",
                                                       AllocationRow.owner_key == caps.global_key)).scalars().all()
    return [{"scope": "GLOBAL", "resource": row.resource, "stored": row.cap, "configured": caps.global_[row.resource]}
            for row in rows if row.resource in caps.global_ and row.cap != caps.global_[row.resource]]


def set_cap(session: Session, scope: str, owner_key: uuid.UUID, resource: str, cap: int, reason: str) -> None:
    """The only way to change a frozen cap: an explicit, recorded operator action."""
    if not reason.strip() or cap < 0 or scope not in {"GLOBAL", "OWNER"} or resource not in RESOURCES:
        raise ValueError("set-cap needs a scope, a resource, a non-negative cap and a reason")
    row = session.execute(select(AllocationRow).where(
        AllocationRow.scope == scope, AllocationRow.owner_key == owner_key, AllocationRow.resource == resource)
        .with_for_update()).scalar_one_or_none()
    if row is None:
        raise ValueError("no allocation exists for that scope and resource")
    _event(session, "CAP_CHANGED", None if scope == "GLOBAL" else owner_key, None,
           {"scope": scope, "resource": resource, "from": row.cap, "to": cap, "reason": reason})
    row.cap, row.cap_source, row.updated_at = cap, f"operator:{reason}", utcnow()


def main() -> None:
    """Operator command: `python -m edge_os_api.usage.quota set-cap --scope GLOBAL --resource … --cap N --reason …`."""
    from edge_os_api.core.database import make_engine, make_session_factory, require_head
    from edge_os_api.core.settings import load_settings

    parser = argparse.ArgumentParser(description="Record an explicit quota cap change.")
    sub = parser.add_subparsers(dest="command", required=True)
    change = sub.add_parser("set-cap")
    change.add_argument("--scope", choices=["GLOBAL", "OWNER"], required=True)
    change.add_argument("--owner", default=str(GLOBAL_OWNER))
    change.add_argument("--resource", choices=list(RESOURCES), required=True)
    change.add_argument("--cap", type=int, required=True)
    change.add_argument("--reason", required=True)
    args = parser.parse_args()
    settings = load_settings()
    engine = make_engine(settings.database_url, settings.database_statement_timeout_ms)
    require_head(engine)
    with make_session_factory(engine)() as session:
        set_cap(session, args.scope, uuid.UUID(args.owner), args.resource, args.cap, args.reason)
        session.commit()
    print(f"recorded {args.scope} {args.resource} cap {args.cap}")


if __name__ == "__main__":
    main()
