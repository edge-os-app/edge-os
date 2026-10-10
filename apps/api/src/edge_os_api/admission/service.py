"""AdmissionService: deterministic local admission, atomic reservation and durable reconciliation.

The owner is always the verified caller; the intent never carries an owner.
Serialization uses a per-wallet PostgreSQL advisory transaction lock plus
constraints as a backstop, so separate sessions cannot double-reserve the same
funds or inventory. Approved amounts come only from the caller-supplied
authored approval snapshot; this service invents no thresholds or limits.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.accounting import (
    ReservationNeed,
    ReservationPlan,
    covered,
    denial_reasons,
    plan_reservations,
)
from edge_os_api.admission.models import (
    AllowanceRow,
    DecisionRow,
    PositionRow,
    ReservationRow,
)
from edge_os_api.admission.types import (
    ActionIntent,
    ActionReceipt,
    AdmissionContext,
    AdmissionDecision,
    AllowanceSummary,
    ApprovalSnapshot,
    AssetAmount,
    CancellationOutcome,
    ReconciliationOutcome,
    ReservationView,
    SavedDecision,
    SavedReservation,
)

_CAPITAL_SCOPES = ("CAPITAL", "GAS")
_CANCELLABLE = {"PROPOSED", "ADMITTED"}
_TERMINAL = {"CONFIRMED", "REVERTED", "DENIED", "CANCELLED"}


class AdmissionError(Exception):
    pass


class AccountingBreach(AdmissionError):
    """A reconciled actual would exceed an approved cap. Fails closed; nothing is committed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class StaleInput(AdmissionError):
    def __init__(self, action_id: str) -> None:
        super().__init__(f"action {action_id} already admitted under a different reviewed input")
        self.action_id = action_id


def _int(value: Decimal | int | float) -> int:
    return int(value)


def _amount(asset_id: str, raw: int, decimals: int) -> AssetAmount:
    return AssetAmount(asset_id=asset_id, raw=str(raw), decimals=decimals)


def _advisory_keys(owner: uuid.UUID, intent: ActionIntent) -> tuple[int, int]:
    raw = f"{owner}:{intent.binding.agent_id}:{intent.binding.wallet_id}:{intent.binding.network_id}".encode()
    digest = hashlib.sha256(raw).digest()

    def int4(offset: int) -> int:
        value = int.from_bytes(digest[offset:offset + 4], "big")
        return value - 2**32 if value >= 2**31 else value

    return int4(0), int4(4)


def _binding_snapshot(intent: ActionIntent) -> dict[str, Any]:
    return {
        "agent_id": intent.binding.agent_id, "wallet_id": intent.binding.wallet_id,
        "network_id": intent.binding.network_id, "strategy_revision": intent.binding.strategy_revision,
        "mandate_id": intent.binding.mandate_id, "policy_binding": intent.policy_binding,
        "position_id": intent.position_id, "operation": intent.operation,
        "base_asset_id": intent.quantity.asset_id,
        "quote_asset_id": intent.input.quote_asset_id,
    }


def _approved_lookup(approval: ApprovalSnapshot) -> dict[str, int]:
    caps = (approval.quote_allowance, approval.base_allowance, approval.gas)
    return {cap.asset_id: cap.as_int() for cap in caps}


def _position_in_snapshot(context: AdmissionContext, intent: ActionIntent):
    if not intent.position_id:
        return None
    position = context.holdings.positions.get(intent.position_id)
    if position is None:
        return None
    if (position.binding.agent_id, position.binding.wallet_id, position.binding.network_id) != (
            intent.binding.agent_id, intent.binding.wallet_id, intent.binding.network_id):
        return None
    return position


def _position_row(session: Session, owner: uuid.UUID, position_id: str) -> PositionRow | None:
    if not position_id:
        return None
    return session.execute(select(PositionRow).where(
        PositionRow.owner_id == owner, PositionRow.position_id == position_id,
    )).scalar_one_or_none()


def _find_decision(session: Session, owner: uuid.UUID, action_id: str) -> DecisionRow | None:
    return session.execute(select(DecisionRow).where(
        DecisionRow.owner_id == owner, DecisionRow.action_id == action_id,
    )).scalar_one_or_none()


def _save_decision(session: Session, owner: uuid.UUID, intent: ActionIntent,
                   status: str, reason: str | None) -> DecisionRow:
    row = DecisionRow(
        decision_id=uuid.uuid4(), owner_id=owner, agent_id=intent.binding.agent_id,
        wallet_id=intent.binding.wallet_id, network_id=intent.binding.network_id,
        action_id=intent.action_id, review_hash=intent.review_hash,
        operation=intent.operation, status=status, reason=reason,
        binding=_binding_snapshot(intent),
    )
    session.add(row)
    session.flush()
    return row


def _reserved_capital(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str,
                      network_id: str, asset_id: str) -> int:
    total = session.execute(select(func.coalesce(func.sum(ReservationRow.raw), 0)).where(
        ReservationRow.owner_id == owner,
        ReservationRow.agent_id == agent_id,
        ReservationRow.wallet_id == wallet_id,
        ReservationRow.network_id == network_id,
        ReservationRow.asset_id == asset_id,
        ReservationRow.state == "RESERVED",
        ReservationRow.scope.in_(_CAPITAL_SCOPES),
    )).scalar_one()
    return _int(total)


def _reserved_inventory(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str,
                        network_id: str, position_id: str, asset_id: str) -> int:
    total = session.execute(select(func.coalesce(func.sum(ReservationRow.raw), 0)).where(
        ReservationRow.owner_id == owner,
        ReservationRow.agent_id == agent_id,
        ReservationRow.wallet_id == wallet_id,
        ReservationRow.network_id == network_id,
        ReservationRow.position_id == position_id,
        ReservationRow.asset_id == asset_id,
        ReservationRow.scope == "INVENTORY",
        ReservationRow.state == "RESERVED",
    )).scalar_one()
    return _int(total)


def _attempt_count(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str) -> int:
    """Consumed plus reserved attempt atoms for one owner wallet and network."""
    total = session.execute(select(func.coalesce(func.count(), 0)).where(
        ReservationRow.owner_id == owner,
        ReservationRow.agent_id == agent_id,
        ReservationRow.wallet_id == wallet_id,
        ReservationRow.network_id == network_id,
        ReservationRow.scope == "ATTEMPT",
        ReservationRow.state.in_(("RESERVED", "CONSUMED")),
    )).scalar_one()
    return _int(total)


def _lock_allowance(session: Session, owner: uuid.UUID, intent: ActionIntent,
                    asset_id: str, decimals: int, approved: int) -> AllowanceRow:
    statement = select(AllowanceRow).where(
        AllowanceRow.owner_id == owner,
        AllowanceRow.agent_id == intent.binding.agent_id,
        AllowanceRow.wallet_id == intent.binding.wallet_id,
        AllowanceRow.network_id == intent.binding.network_id,
        AllowanceRow.asset_id == asset_id,
    ).with_for_update()
    row = session.execute(statement).scalar_one_or_none()
    if row is None:
        session.execute(
            pg_insert(AllowanceRow).values(
                allowance_id=uuid.uuid4(), owner_id=owner,
                agent_id=intent.binding.agent_id, wallet_id=intent.binding.wallet_id,
                network_id=intent.binding.network_id, asset_id=asset_id,
                decimals=decimals, approved=Decimal(approved), consumed=Decimal(0),
            ).on_conflict_do_nothing(
                index_elements=["owner_id", "agent_id", "wallet_id", "network_id", "asset_id"],
            )
        )
        session.flush()
        row = session.execute(statement).scalar_one()
    return row


class AdmissionService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    # ----------------------------------------------------------------- propose

    def propose(
        self,
        verified_owner_id: uuid.UUID,
        intent: ActionIntent,
        approval: ApprovalSnapshot,
        context: AdmissionContext,
    ) -> AdmissionDecision:
        """Validate without persisting. Returns PROPOSED or DENIED with its reason."""
        position_exists = _position_in_snapshot(context, intent) is not None
        reasons = denial_reasons(intent, approval, context, position_exists)
        if reasons:
            return AdmissionDecision(
                decision_id=uuid.uuid4(), owner_id=verified_owner_id, action_id=intent.action_id,
                review_hash=intent.review_hash, operation=intent.operation, status="DENIED",
                reason=";".join(sorted(set(reasons))), created_at=context.checked_at,
            )
        return AdmissionDecision(
            decision_id=uuid.uuid4(), owner_id=verified_owner_id, action_id=intent.action_id,
            review_hash=intent.review_hash, operation=intent.operation, status="PROPOSED",
            reason=None, created_at=context.checked_at,
        )

    # ------------------------------------------------------- admit_and_reserve

    def admit_and_reserve(
        self,
        verified_owner_id: uuid.UUID,
        intent: ActionIntent,
        approval: ApprovalSnapshot,
        context: AdmissionContext,
    ) -> AdmissionDecision:
        with self._factory() as session:
            try:
                existing = _find_decision(session, verified_owner_id, intent.action_id)
                if existing is not None:
                    if existing.review_hash == intent.review_hash:
                        session.commit()
                        return _decision_view(session, existing)
                    session.rollback()
                    raise StaleInput(intent.action_id)

                plan, denial = self._adjudicated_plan(session, verified_owner_id, intent, approval, context)
                if denial is not None:
                    row = _save_decision(session, verified_owner_id, intent, "DENIED", denial)
                    session.commit()
                    return _decision_view(session, row)

                key_a, key_b = _advisory_keys(verified_owner_id, intent)
                session.execute(text("SELECT pg_advisory_xact_lock(:key_a, :key_b)"),
                                {"key_a": key_a, "key_b": key_b})

                denial = self._can_reserve_locked(session, verified_owner_id, intent, approval, context, plan)
                if denial is not None:
                    row = _save_decision(session, verified_owner_id, intent, "DENIED", denial)
                    session.commit()
                    return _decision_view(session, row)

                self._publish_reservations(session, verified_owner_id, intent, plan)
                persisted = _save_decision(session, verified_owner_id, intent, "ADMITTED", None)
                session.commit()
                return _decision_view(session, persisted)
            except SQLAlchemyError:
                session.rollback()
                raise
            except AdmissionError:
                session.rollback()
                raise

    def _adjudicated_plan(
        self,
        session: Session,
        owner: uuid.UUID,
        intent: ActionIntent,
        approval: ApprovalSnapshot,
        context: AdmissionContext,
    ) -> tuple[ReservationPlan, str | None]:
        if intent.operation == "ENTRY":
            position = _position_in_snapshot(context, intent)
            position_exists = position is not None or _position_row(session, owner, intent.position_id or "") is not None
        else:
            position = _position_in_snapshot(context, intent)
            position_exists = position is not None

        reasons = denial_reasons(intent, approval, context, position_exists)
        if reasons:
            return ReservationPlan(ok=False), ";".join(sorted(set(reasons)))

        current_inventory = position.as_int() if position is not None else None
        plan = plan_reservations(intent, approval, current_inventory)
        if not plan.ok:
            return plan, plan.reason
        return plan, None

    def _can_reserve_locked(
        self,
        session: Session,
        owner: uuid.UUID,
        intent: ActionIntent,
        approval: ApprovalSnapshot,
        context: AdmissionContext,
        plan: ReservationPlan,
    ) -> str | None:
        # One unresolved economic transaction per agent wallet and network.
        unresolved = session.execute(select(DecisionRow.action_id).where(
            DecisionRow.owner_id == owner,
            DecisionRow.wallet_id == intent.binding.wallet_id,
            DecisionRow.network_id == intent.binding.network_id,
            DecisionRow.status == "SUBMISSION_UNKNOWN",
        ).limit(1)).scalar_one_or_none()
        if unresolved is not None:
            return "UNRESOLVED_PRIOR_ACTION"

        b = intent.binding
        per_asset: dict[str, dict[str, int]] = {}
        for need in plan.needs:
            if need.scope in _CAPITAL_SCOPES:
                entry = per_asset.setdefault(need.asset_id, {"sought": 0, "decimals": need.decimals})
                entry["sought"] += need.raw

        approved_caps = _approved_lookup(approval)
        input_asset = (intent.input.quote_asset_id if intent.operation in {"ENTRY", "ADDITION"}
                       else intent.quantity.asset_id)
        for asset_id, entry in per_asset.items():
            approved = approved_caps.get(asset_id)
            if approved is None:
                return "ALLOWANCE_UNSPECIFIED"
            row = _lock_allowance(session, owner, intent, asset_id, entry["decimals"], approved)
            reserved = _reserved_capital(session, owner, b.agent_id, b.wallet_id, b.network_id, asset_id)
            if not covered(_int(row.approved), _int(row.consumed), reserved, entry["sought"]):
                return "CAPACITY_UNAVAILABLE"
            # Reconciled holdings must cover the asset the action actually spends
            # (buy input or sell input) and gas. The base sell-capacity reservation
            # is a permission against the allowance, not a spend of held base.
            if asset_id in (input_asset, approval.gas.asset_id):
                holdings = context.holdings.balances.get(asset_id)
                if holdings is None or holdings.as_int() < reserved + entry["sought"]:
                    return "HOLDINGS_SHORTFALL"

        attempt_needs = sum(need.raw for need in plan.needs if need.scope == "ATTEMPT")
        if attempt_needs and _attempt_count(session, owner, b.agent_id, b.wallet_id, b.network_id) + attempt_needs > approval.attempt_budget:
            return "ATTEMPT_BUDGET_EXHAUSTED"

        for need in plan.needs:
            if need.scope == "INVENTORY" and need.raw > 0:
                if intent.operation == "EXIT":
                    position = _position_in_snapshot(context, intent)
                    if position is None:
                        return "POSITION_MISSING"
                    reserved = _reserved_inventory(session, owner, b.agent_id, b.wallet_id, b.network_id,
                                                   need.position_id, need.asset_id)
                    if position.as_int() - reserved < need.raw:
                        return "INVENTORY_SHORTFALL"
        return None

    def _publish_reservations(
        self,
        session: Session,
        owner: uuid.UUID,
        intent: ActionIntent,
        plan: ReservationPlan,
    ) -> None:
        for need in plan.needs:
            self._insert_reservation(session, owner, intent, need)
        if plan.requires_new_position and intent.position_id:
            session.add(PositionRow(
                owner_id=owner, position_id=intent.position_id,
                agent_id=intent.binding.agent_id, wallet_id=intent.binding.wallet_id,
                network_id=intent.binding.network_id, asset_id=intent.quantity.asset_id,
                decimals=intent.quantity.decimals, inventory=Decimal(0),
            ))

    @staticmethod
    def _insert_reservation(session: Session, owner: uuid.UUID, intent: ActionIntent, need: ReservationNeed) -> None:
        session.add(ReservationRow(
            reservation_id=uuid.uuid4(), owner_id=owner,
            agent_id=intent.binding.agent_id, wallet_id=intent.binding.wallet_id,
            network_id=intent.binding.network_id, action_id=intent.action_id,
            review_hash=intent.review_hash, scope=need.scope,
            position_id=need.position_id or "", asset_id=need.asset_id,
            decimals=need.decimals, raw=Decimal(need.raw), state="RESERVED",
        ))

    # --------------------------------------------------------------- retrieval

    def retrieve_decisions(
        self,
        verified_owner_id: uuid.UUID,
        *,
        action_id: str | None = None,
        agent_id: str | None = None,
        wallet_id: str | None = None,
        network_id: str | None = None,
        limit: int = 100,
    ) -> list[SavedDecision]:
        with self._factory() as session:
            statement = select(DecisionRow).where(DecisionRow.owner_id == verified_owner_id)
            if action_id is not None:
                statement = statement.where(DecisionRow.action_id == action_id)
            if agent_id is not None:
                statement = statement.where(DecisionRow.agent_id == agent_id)
            if wallet_id is not None:
                statement = statement.where(DecisionRow.wallet_id == wallet_id)
            if network_id is not None:
                statement = statement.where(DecisionRow.network_id == network_id)
            rows = session.execute(
                statement.order_by(DecisionRow.created_at, DecisionRow.decision_id).limit(limit)
            ).scalars().all()
            return [_saved_decision(row) for row in rows]

    def retrieve_reservations(
        self,
        verified_owner_id: uuid.UUID,
        *,
        wallet_id: str,
        network_id: str,
        asset_id: str | None = None,
        state: str = "RESERVED",
    ) -> list[SavedReservation]:
        with self._factory() as session:
            statement = select(ReservationRow).where(
                ReservationRow.owner_id == verified_owner_id,
                ReservationRow.wallet_id == wallet_id,
                ReservationRow.network_id == network_id,
                ReservationRow.state == state,
            )
            if asset_id is not None:
                statement = statement.where(ReservationRow.asset_id == asset_id)
            rows = session.execute(statement.order_by(ReservationRow.created_at)).scalars().all()
            return [_saved_reservation(row) for row in rows]

    def balances(
        self,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str | None = None,
        wallet_id: str | None = None,
        network_id: str | None = None,
    ) -> list[AllowanceSummary]:
        with self._factory() as session:
            statement = select(AllowanceRow).where(AllowanceRow.owner_id == verified_owner_id)
            if agent_id is not None:
                statement = statement.where(AllowanceRow.agent_id == agent_id)
            if wallet_id is not None:
                statement = statement.where(AllowanceRow.wallet_id == wallet_id)
            if network_id is not None:
                statement = statement.where(AllowanceRow.network_id == network_id)
            rows = session.execute(statement.order_by(AllowanceRow.asset_id)).scalars().all()
            summaries: list[AllowanceSummary] = []
            for row in rows:
                reserved = _reserved_capital(session, verified_owner_id, row.agent_id, row.wallet_id,
                                             row.network_id, row.asset_id)
                summaries.append(AllowanceSummary.from_literals(
                    owner_id=verified_owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id,
                    network_id=row.network_id, asset_id=row.asset_id, decimals=_int(row.decimals),
                    approved=_int(row.approved), consumed=_int(row.consumed), reserved=reserved,
                ))
            return summaries

    # ----------------------------------------------------------------- cancel

    def cancel(self, verified_owner_id: uuid.UUID, action_id: str) -> CancellationOutcome:
        with self._factory() as session:
            try:
                row = _find_decision(session, verified_owner_id, action_id)
                if row is None:
                    return CancellationOutcome(action_id=action_id, decision_status="NOT_FOUND",
                                               reason=None, released=[])
                if row.status not in _CANCELLABLE:
                    return CancellationOutcome(action_id=action_id, decision_status=row.status,
                                               reason="NOT_CANCELLABLE_AFTER_SUBMISSION", released=[])
                released = _release_all(session, row, "CANCELLED")
                session.commit()
                return CancellationOutcome(action_id=action_id, decision_status="CANCELLED",
                                           reason=None, released=released)
            except SQLAlchemyError:
                session.rollback()
                raise

    # -------------------------------------------------------------- reconcile

    def reconcile(
        self,
        verified_owner_id: uuid.UUID,
        action_id: str,
        receipt: ActionReceipt,
    ) -> ReconciliationOutcome:
        with self._factory() as session:
            try:
                row = _find_decision(session, verified_owner_id, action_id)
                if row is None:
                    return ReconciliationOutcome(action_id=action_id, decision_status="NOT_FOUND", reason=None)
                if _snapshot_binding(row) != (receipt.binding.agent_id, receipt.binding.wallet_id,
                                              receipt.binding.network_id):
                    return ReconciliationOutcome(action_id=action_id, decision_status="DENIED",
                                                 reason="RECONCILIATION_BINDING_MISMATCH")

                if row.status in _TERMINAL:
                    # A terminal economic outcome cannot be replaced by a later receipt.
                    return ReconciliationOutcome(action_id=action_id, decision_status=row.status,
                                                 reason="RECONCILIATION_TERMINAL_STATE")

                outcome = receipt.outcome
                if outcome == "SUBMISSION_UNKNOWN":
                    row.status = "SUBMISSION_UNKNOWN"
                    session.commit()
                    return ReconciliationOutcome(
                        action_id=action_id, decision_status="SUBMISSION_UNKNOWN", reason=None,
                        retained=[_reservation_amount(r) for r in _action_reservations(session, row)
                                  if r.state == "RESERVED"],
                    )

                if outcome == "CANCELLED":
                    if row.status not in _CANCELLABLE:
                        session.commit()
                        return ReconciliationOutcome(action_id=action_id, decision_status=row.status,
                                                     reason="NOT_CANCELLABLE_AFTER_SUBMISSION")
                    _release_all(session, row, "CANCELLED")
                    session.commit()
                    return ReconciliationOutcome(action_id=action_id, decision_status="CANCELLED", reason=None)

                if outcome == "PREBROADCAST_DENIED":
                    _release_all(session, row, "DENIED", reason="PREBROADCAST_DENIED")
                    session.commit()
                    return ReconciliationOutcome(action_id=action_id, decision_status="DENIED",
                                                 reason="PREBROADCAST_DENIED")

                if outcome in {"CONFIRMED", "REVERTED"}:
                    try:
                        consumed, released = _settle(session, row, receipt)
                    except AccountingBreach as breach:
                        session.rollback()
                        return ReconciliationOutcome(action_id=action_id, decision_status=row.status,
                                                     reason=breach.reason)
                    session.commit()
                    return ReconciliationOutcome(
                        action_id=action_id, decision_status=row.status, reason=None,
                        consumed=consumed, released=released,
                    )

                raise AdmissionError(f"unhandled receipt outcome {outcome!r}")
            except SQLAlchemyError:
                session.rollback()
                raise


# ------------------------------------------------------------------------- helpers

def _snapshot_binding(row: DecisionRow) -> tuple[Any, ...]:
    binding = row.binding
    return (binding.get("agent_id"), binding.get("wallet_id"), binding.get("network_id"))


def _decision_view(session: Session, row: DecisionRow) -> AdmissionDecision:
    reservations: list[ReservationView] = []
    for res in session.execute(select(ReservationRow).where(
            ReservationRow.owner_id == row.owner_id, ReservationRow.action_id == row.action_id,
    )).scalars().all():
        view = _saved_reservation(res)
        reservations.append(ReservationView(
            reservation_id=view.reservation_id, scope=view.scope, position_id=view.position_id,
            amount=view.amount, state=view.state,
        ))
    return AdmissionDecision(
        decision_id=row.decision_id, owner_id=row.owner_id, action_id=row.action_id,
        review_hash=row.review_hash, operation=row.operation, status=row.status,
        reason=row.reason, created_at=_utc_iso(row.created_at), reservations=reservations,
    )


def _saved_decision(row: DecisionRow) -> SavedDecision:
    return SavedDecision(
        decision_id=row.decision_id, owner_id=row.owner_id, action_id=row.action_id,
        review_hash=row.review_hash, operation=row.operation, status=row.status,
        reason=row.reason, created_at=_utc_iso(row.created_at),
    )


def _saved_reservation(row: ReservationRow) -> SavedReservation:
    return SavedReservation(
        reservation_id=row.reservation_id, owner_id=row.owner_id, action_id=row.action_id,
        scope=row.scope, position_id=row.position_id or None,
        amount=_amount(row.asset_id, _int(row.raw), _int(row.decimals)), state=row.state,
    )


def _reservation_amount(row: ReservationRow) -> AssetAmount:
    return _amount(row.asset_id, _int(row.raw), _int(row.decimals))


def _action_reservations(session: Session, row: DecisionRow) -> list[ReservationRow]:
    return session.execute(select(ReservationRow).where(
        ReservationRow.owner_id == row.owner_id, ReservationRow.action_id == row.action_id,
    ).order_by(ReservationRow.scope, ReservationRow.asset_id)).scalars().all()


def _release_all(session: Session, row: DecisionRow, status: str, reason: str | None = None) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for reservation in _action_reservations(session, row):
        if reservation.state == "RESERVED":
            reservation.state = "RELEASED"
            reservation.reconciled_at = func.now()
            ids.append(reservation.reservation_id)
    row.status = status
    if reason is not None:
        row.reason = reason
    session.flush()
    return ids


def _charge(session: Session, row: DecisionRow, asset_id: str, decimals: int, amount: int) -> None:
    """Add a reconciled actual to a wallet allowance, failing closed on a cap breach."""
    allowance = _lock_allowance_for(session, row, asset_id, decimals)
    if _int(allowance.consumed) + amount > _int(allowance.approved):
        raise AccountingBreach("CONSUMED_EXCEEDS_APPROVED")
    allowance.consumed += Decimal(amount)


def _settle(
    session: Session,
    row: DecisionRow,
    receipt: ActionReceipt,
) -> tuple[list[AssetAmount], list[AssetAmount]]:
    committed = receipt.outcome == "CONFIRMED"
    consumed_amounts: list[AssetAmount] = []
    released_amounts: list[AssetAmount] = []
    operation = row.operation
    base_asset = str(row.binding.get("base_asset_id") or "")
    quote_asset = str(row.binding.get("quote_asset_id") or "")
    input_asset = quote_asset if operation in {"ENTRY", "ADDITION"} else base_asset

    # A supplied reconciled actual quantity must match the reserved input; a
    # mismatch fails closed instead of being silently ignored.
    if receipt.actual_quantity is not None:
        if receipt.actual_quantity.asset_id != input_asset:
            raise AccountingBreach("RECEIPT_QUANTITY_ASSET_MISMATCH")
        reserved_input = sum(
            _int(res.raw) for res in _action_reservations(session, row)
            if res.scope == "CAPITAL" and res.asset_id == input_asset and res.state == "RESERVED"
        )
        if receipt.actual_quantity.as_int() != reserved_input:
            raise AccountingBreach("RECEIPT_QUANTITY_MISMATCH")

    for reservation in _action_reservations(session, row):
        if reservation.state != "RESERVED":
            continue

        if reservation.scope == "ATTEMPT":
            # A broadcast-capable swap consumes one attempt, including a revert.
            reservation.state = "CONSUMED"
            reservation.reconciled_at = func.now()
            consumed_amounts.append(_reservation_amount(reservation))
            continue

        if reservation.scope == "GAS":
            actual = receipt.actual_gas
            amount = actual if actual is not None else _reservation_amount(reservation)
            _charge(session, row, reservation.asset_id, reservation.decimals, amount.as_int())
            reservation.state = "CONSUMED"
            reservation.reconciled_at = func.now()
            consumed_amounts.append(amount)
            continue

        if reservation.scope == "CAPITAL":
            if operation in {"ENTRY", "ADDITION"} and reservation.asset_id == quote_asset:
                if committed:
                    _charge(session, row, reservation.asset_id, reservation.decimals, _int(reservation.raw))
                    reservation.state = "CONSUMED"
                    consumed_amounts.append(_reservation_amount(reservation))
                else:
                    reservation.state = "RELEASED"
                    released_amounts.append(_reservation_amount(reservation))
            elif operation in {"ENTRY", "ADDITION"} and reservation.asset_id == base_asset:
                # Sell-capacity reservation: once inventory is attributed the capacity
                # is backed by the position, so the reservation is released. A revert
                # also releases it because no inventory exists.
                reservation.state = "RELEASED"
                released_amounts.append(_reservation_amount(reservation))
            elif operation == "EXIT":
                if committed:
                    _charge(session, row, reservation.asset_id, reservation.decimals, _int(reservation.raw))
                    reservation.state = "CONSUMED"
                    consumed_amounts.append(_reservation_amount(reservation))
                else:
                    reservation.state = "RELEASED"
                    released_amounts.append(_reservation_amount(reservation))
            reservation.reconciled_at = func.now()
            continue

        if reservation.scope == "INVENTORY":
            position = _position_row(session, row.owner_id, reservation.position_id or "")
            quantity = _int(reservation.raw)
            if position is not None:
                if operation == "EXIT":
                    if committed:
                        remaining = _int(position.inventory) - quantity
                        if remaining < 0:
                            raise AccountingBreach("INVENTORY_UNDERFLOW")
                        position.inventory = Decimal(remaining)
                else:
                    if committed:
                        position.inventory = Decimal(_int(position.inventory) + quantity)
            reservation.state = "CONSUMED" if committed else "RELEASED"
            reservation.reconciled_at = func.now()

    row.status = "CONFIRMED" if committed else "REVERTED"
    session.flush()
    return consumed_amounts, released_amounts


def _lock_allowance_for(session: Session, row: DecisionRow, asset_id: str, decimals: int) -> AllowanceRow:
    statement = select(AllowanceRow).where(
        AllowanceRow.owner_id == row.owner_id, AllowanceRow.agent_id == row.agent_id,
        AllowanceRow.wallet_id == row.wallet_id, AllowanceRow.network_id == row.network_id,
        AllowanceRow.asset_id == asset_id,
    ).with_for_update()
    allowance = session.execute(statement).scalar_one_or_none()
    if allowance is None:
        session.execute(
            pg_insert(AllowanceRow).values(
                allowance_id=uuid.uuid4(), owner_id=row.owner_id, agent_id=row.agent_id,
                wallet_id=row.wallet_id, network_id=row.network_id, asset_id=asset_id,
                decimals=decimals, approved=Decimal(0), consumed=Decimal(0),
            ).on_conflict_do_nothing(
                index_elements=["owner_id", "agent_id", "wallet_id", "network_id", "asset_id"],
            )
        )
        session.flush()
        allowance = session.execute(statement).scalar_one()
    return allowance


def _utc_iso(moment: Any) -> str:
    return moment.astimezone(timezone.utc).isoformat() if getattr(moment, "tzinfo", None) is not None else str(moment)