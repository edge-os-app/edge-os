"""Local `funding_local` schema and row helpers.

The tables live in their own metadata and their own schema. They are created only by the
test/qualification harness in a run-labelled database. This package ships no migration and
registers no shared model. `owner_id` follows the verified principal `users.id` by application
convention; it carries no foreign key so the local schema stays self-contained.

`funding_credits` carries the once-only guard: a unique constraint on the exact
`(wallet_id, network_id, asset_id, event_id)` identity. A replayed, concurrent, response-lost or
restart credit attempt cannot insert a second row for the same identity.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, Identity, Index, Integer, MetaData, Numeric, Text,
                        UniqueConstraint, select, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from edge_os_api.funding.types import (AssetAmount, CreditRecord, FlowKind, FlowState, FundingFlowRecord,
                                       FundingProfileRecord, ObservationRecord, ObservationStatus)

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "pk": "%(table_name)s_pkey",
}

NOW = text("now()")
FUNDING_SCHEMA = "funding_local"


class FundingBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=FUNDING_SCHEMA)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _raw_column() -> Numeric:
    return mapped_column(Numeric(78, 0), nullable=False)


def _raw_nullable_column() -> Numeric:
    return mapped_column(Numeric(78, 0))


class FundingProfileRow(FundingBase):
    """The declared supported assets for one `(owner_id, agent_id)` confirmed wallet binding."""

    __tablename__ = "funding_profiles"
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[int] = mapped_column(Integer, nullable=False)
    trading_asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    trading_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    gas_asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    gas_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    compute_asset_id: Mapped[str | None] = mapped_column(Text)
    compute_decimals: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_id", "agent_id", name="uq_funding_profiles_owner_agent"),
        CheckConstraint("network_id IN (143, 10143)", name="network"),
    )


class FundingFlowRow(FundingBase):
    """One reviewed funding flow. The reviewed reference is unique per agent."""

    __tablename__ = "funding_flows"
    flow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    declared_raw: Mapped[Decimal] = _raw_column()
    decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    declared_fee_raw: Mapped[Decimal | None] = _raw_nullable_column()
    declared_fee_decimals: Mapped[int | None] = mapped_column(Integer)
    declared_fee_asset_id: Mapped[str | None] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str | None] = mapped_column(Text)
    recipient: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_reference: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_id", "agent_id", "reference", name="uq_funding_flows_owner_agent_reference"),
        CheckConstraint("kind IN ('DEPOSIT', 'WITHDRAWAL')", name="kind"),
        CheckConstraint("state IN ('PENDING', 'CONFIRMED', 'FAILED', 'UNKNOWN')", name="state"),
        CheckConstraint("network_id IN (143, 10143)", name="network"),
        Index("ix_funding_flows_owner_wallet_state", "owner_id", "wallet_id", "state"),
    )


class FundingObservationRow(FundingBase):
    """Append-only deposit observations. Request and actual amounts stay distinguishable."""

    __tablename__ = "funding_observations"
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)
    flow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_id: Mapped[str | None] = mapped_column(Text)
    actual_raw: Mapped[Decimal | None] = _raw_nullable_column()
    decimals: Mapped[int | None] = mapped_column(Integer)
    fee_raw: Mapped[Decimal | None] = _raw_nullable_column()
    fee_decimals: Mapped[int | None] = mapped_column(Integer)
    fee_asset_id: Mapped[str | None] = mapped_column(Text)
    event_id: Mapped[str | None] = mapped_column(Text)
    transaction_reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str | None] = mapped_column(Text)
    recipient: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'CONFIRMED', 'FAILED', 'UNKNOWN', 'DUPLICATE')", name="status"),
        Index("ix_funding_observations_owner_wallet_sequence", "owner_id", "wallet_id", "sequence"),
        Index("ix_funding_observations_flow", "flow_id", "sequence"),
    )


class FundingCreditRow(FundingBase):
    """Once-only credits. The unique constraint is the durable guard against a second credit."""

    __tablename__ = "funding_credits"
    credit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_id: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    actual_raw: Mapped[Decimal] = _raw_column()
    decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_raw: Mapped[Decimal | None] = _raw_nullable_column()
    fee_decimals: Mapped[int | None] = mapped_column(Integer)
    fee_asset_id: Mapped[str | None] = mapped_column(Text)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    flow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("wallet_id", "network_id", "asset_id", "event_id", name="uq_funding_credit_event_identity"),
        CheckConstraint("network_id IN (143, 10143)", name="network"),
        Index("ix_funding_credits_owner_wallet_asset", "owner_id", "wallet_id", "asset_id"),
    )


class FundingDenialRow(FundingBase):
    """Denials and unsupported observations recorded separately from protected flow state."""

    __tablename__ = "funding_denials"
    denial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_funding_denials_owner_created", "owner_id", "created_at"),
    )


def _int_or_none(value: Decimal | None) -> str | None:
    return None if value is None else str(int(value))


def _amount(asset_id: str, raw: Decimal, decimals: int) -> AssetAmount:
    return AssetAmount(asset_id=asset_id, raw=str(int(raw)), decimals=decimals)


def to_profile(row: FundingProfileRow) -> FundingProfileRecord:
    compute = (AssetAmount(asset_id=row.compute_asset_id, raw="0", decimals=int(row.compute_decimals))
               if row.compute_asset_id is not None and row.compute_decimals is not None else None)
    return FundingProfileRecord(
        owner_id=row.owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id, network_id=row.network_id,
        trading_asset=AssetAmount(asset_id=row.trading_asset_id, raw="0", decimals=int(row.trading_decimals)),
        gas_asset=AssetAmount(asset_id=row.gas_asset_id, raw="0", decimals=int(row.gas_decimals)),
        compute_asset=compute, updated_at=row.updated_at)


def to_flow(row: FundingFlowRow) -> FundingFlowRecord:
    fee = (AssetAmount(asset_id=row.declared_fee_asset_id, raw=str(int(row.declared_fee_raw)),
                       decimals=int(row.declared_fee_decimals))
           if row.declared_fee_asset_id is not None and row.declared_fee_raw is not None
           and row.declared_fee_decimals is not None else None)
    return FundingFlowRecord(
        flow_id=row.flow_id, owner_id=row.owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id,
        network_id=row.network_id, kind=FlowKind(row.kind), asset=_amount(row.asset_id, row.declared_raw, row.decimals),
        declared_fee=fee, transport=row.transport, sender=row.sender, recipient=row.recipient,
        state=FlowState(row.state), reference=row.reference, transaction_reference=row.transaction_reference,
        reason=row.reason, created_at=row.created_at, updated_at=row.updated_at)


def to_observation(row: FundingObservationRow) -> ObservationRecord:
    actual = (_amount(row.asset_id, row.actual_raw, int(row.decimals))
              if row.asset_id is not None and row.actual_raw is not None and row.decimals is not None else None)
    fee = (_amount(row.fee_asset_id, row.fee_raw, int(row.fee_decimals))
           if row.fee_asset_id is not None and row.fee_raw is not None and row.fee_decimals is not None else None)
    return ObservationRecord(
        observation_id=row.observation_id, owner_id=row.owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id,
        network_id=row.network_id, asset_id=row.asset_id, actual=actual, fee=fee, event_id=row.event_id,
        transaction_reference=row.transaction_reference, status=ObservationStatus(row.status), flow_id=row.flow_id,
        reason=row.reason, observed_at=row.observed_at)


def to_credit(row: FundingCreditRow) -> CreditRecord:
    fee = (_amount(row.fee_asset_id, row.fee_raw, int(row.fee_decimals))
           if row.fee_asset_id is not None and row.fee_raw is not None and row.fee_decimals is not None else None)
    return CreditRecord(
        credit_id=row.credit_id, owner_id=row.owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id,
        network_id=row.network_id, asset_id=row.asset_id, amount=_amount(row.asset_id, row.actual_raw, row.decimals),
        fee=fee, event_id=row.event_id, flow_id=row.flow_id, observation_id=row.observation_id, created_at=row.created_at)


def load_profile(session: Any, owner_id: uuid.UUID, agent_id: str, *, lock: bool = False) -> FundingProfileRow | None:
    stmt = select(FundingProfileRow).where(FundingProfileRow.owner_id == owner_id, FundingProfileRow.agent_id == agent_id)
    if lock:
        stmt = stmt.execution_options(populate_existing=True).with_for_update()
    return session.execute(stmt).scalar_one_or_none()


def load_flow(session: Any, owner_id: uuid.UUID, agent_id: str, flow_id: uuid.UUID, *, lock: bool = False
              ) -> FundingFlowRow | None:
    stmt = select(FundingFlowRow).where(FundingFlowRow.owner_id == owner_id, FundingFlowRow.agent_id == agent_id,
                                        FundingFlowRow.flow_id == flow_id)
    if lock:
        stmt = stmt.execution_options(populate_existing=True).with_for_update()
    return session.execute(stmt).scalar_one_or_none()


def load_flow_by_reference(session: Any, owner_id: uuid.UUID, wallet_id: str, network_id: int, reference: str
                           ) -> FundingFlowRow | None:
    return session.execute(select(FundingFlowRow).where(
        FundingFlowRow.owner_id == owner_id, FundingFlowRow.wallet_id == wallet_id,
        FundingFlowRow.network_id == network_id, FundingFlowRow.reference == reference)).scalar_one_or_none()


def list_flows(session: Any, owner_id: uuid.UUID, agent_id: str) -> list[FundingFlowRow]:
    return list(session.execute(select(FundingFlowRow).where(
        FundingFlowRow.owner_id == owner_id, FundingFlowRow.agent_id == agent_id
    ).order_by(FundingFlowRow.created_at, FundingFlowRow.flow_id)).scalars())


def flows_for_wallet(session: Any, owner_id: uuid.UUID, wallet_id: str, network_id: int) -> list[FundingFlowRow]:
    return list(session.execute(select(FundingFlowRow).where(
        FundingFlowRow.owner_id == owner_id, FundingFlowRow.wallet_id == wallet_id,
        FundingFlowRow.network_id == network_id).order_by(FundingFlowRow.created_at)).scalars())


def insert_observation(session: Any, **values: Any) -> FundingObservationRow:
    row = FundingObservationRow(observation_id=uuid.uuid4(), created_at=utcnow(), **values)
    session.add(row)
    session.flush()
    return row


def observations_for_flow(session: Any, flow_id: uuid.UUID) -> list[FundingObservationRow]:
    return list(session.execute(select(FundingObservationRow).where(
        FundingObservationRow.flow_id == flow_id).order_by(FundingObservationRow.sequence)).scalars())


def credit_for_identity(session: Any, wallet_id: str, network_id: int, asset_id: str, event_id: str
                        ) -> FundingCreditRow | None:
    return session.execute(select(FundingCreditRow).where(
        FundingCreditRow.wallet_id == wallet_id, FundingCreditRow.network_id == network_id,
        FundingCreditRow.asset_id == asset_id, FundingCreditRow.event_id == event_id)).scalar_one_or_none()


def credits_for_wallet(session: Any, owner_id: uuid.UUID, wallet_id: str, network_id: int, asset_id: str
                       ) -> list[FundingCreditRow]:
    return list(session.execute(select(FundingCreditRow).where(
        FundingCreditRow.owner_id == owner_id, FundingCreditRow.wallet_id == wallet_id,
        FundingCreditRow.network_id == network_id, FundingCreditRow.asset_id == asset_id
    ).order_by(FundingCreditRow.created_at)).scalars())


def record_denial(session: Any, owner_id: uuid.UUID, agent_id: str | None, code: str,
                  content: dict[str, Any]) -> None:
    """Record a denial for the requesting (verified) owner. It never references another owner's row."""
    session.add(FundingDenialRow(denial_id=uuid.uuid4(), owner_id=owner_id, agent_id=agent_id, code=code,
                                 content=content, created_at=utcnow()))
    session.flush()
