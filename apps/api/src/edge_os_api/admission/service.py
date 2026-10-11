"""AdmissionService: deterministic local admission, atomic reservation and durable reconciliation.

The owner is always the verified caller; the intent never carries an owner.
Every mutation for one wallet is serialized by a per-wallet PostgreSQL advisory
transaction lock, used by admission, cancellation and reconciliation in the same
order. Approved amounts come only from the caller-supplied authored approval
snapshot. All ledger arithmetic is exact Python integer arithmetic on the
canonical raw values.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import timezone
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.accounting import (
    ACQUISITIONS,
    ATTEMPT_ASSET,
    HOLD_ACTION_PREFIX,
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
    ReceiptRow,
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
    SavedReceipt,
    SavedReservation,
)

_CAPITAL_SCOPES = ("CAPITAL", "GAS")
_CANCELLABLE = {"PROPOSED", "ADMITTED"}
# A proved pre-broadcast denial releases a working or submission-owned action.
# SUBMISSION_UNKNOWN is included so a P23 submission-owned action can be released
# when the transport proves no send was possible; a breach is still not clearable.
_PREBROADCAST_CLEARABLE = {"PROPOSED", "ADMITTED", "SUBMISSION_UNKNOWN"}
_TERMINAL = {"CONFIRMED", "REVERTED", "DENIED", "CANCELLED"}


class AdmissionError(Exception):
    pass


class AccountingBreach(AdmissionError):
    """A reconciled actual would invalidate the ledger. Fails closed; nothing is committed."""

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


def _lock_keys(owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str) -> tuple[int, int]:
    raw = f"{owner}:{agent_id}:{wallet_id}:{network_id}".encode()
    digest = hashlib.sha256(raw).digest()

    def int4(offset: int) -> int:
        value = int.from_bytes(digest[offset:offset + 4], "big")
        return value - 2**32 if value >= 2**31 else value

    return int4(0), int4(4)


def _acquire_wallet_lock(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str) -> None:
    key_a, key_b = _lock_keys(owner, agent_id, wallet_id, network_id)
    session.execute(text("SELECT pg_advisory_xact_lock(:key_a, :key_b)"), {"key_a": key_a, "key_b": key_b})


def acquire_wallet_lock(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str) -> None:
    """Public entry to the shared per-wallet admission lock.

    The lock serializes admission, submission ownership and any durable scoped
    stop write for one owner, agent, wallet and network. It defines the atomic
    ordering between a committed stop and the submission-ownership transition.
    """
    _acquire_wallet_lock(session, owner, agent_id, wallet_id, network_id)


class StopReader(Protocol):
    """Read-only durable stop lookup used by admission and execution.

    The implementation reads the persisted stop records inside the caller's
    transaction. It never writes and it never consults a caller-supplied stop.
    """

    def denial_reasons(
        self,
        session: Session,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str,
        wallet_id: str,
        network_id: str,
        position_id: str,
        operation: str,
    ) -> list[str]: ...


def _binding_snapshot(intent: ActionIntent, approval: ApprovalSnapshot) -> dict[str, Any]:
    quote_decimals = approval.quote_allowance.decimals
    if intent.input.quote_input is not None:
        quote_decimals = intent.input.quote_input.decimals
    return {
        "agent_id": intent.binding.agent_id, "wallet_id": intent.binding.wallet_id,
        "network_id": intent.binding.network_id, "strategy_revision": intent.binding.strategy_revision,
        "mandate_id": intent.binding.mandate_id, "policy_binding": intent.policy_binding,
        "approval_id": approval.approval_id,
        "position_id": intent.position_id, "operation": intent.operation,
        "base_asset_id": intent.quantity.asset_id, "base_decimals": intent.quantity.decimals,
        "quote_asset_id": intent.input.quote_asset_id, "quote_decimals": quote_decimals,
        "allocation_asset_id": approval.allocation_quote.asset_id,
        "allocation_approved_raw": approval.allocation_quote.approved_raw,
        "gas_asset_id": approval.gas.asset_id, "gas_decimals": approval.gas.decimals,
        "entry_gas_raw": approval.per_action_gas.approved_raw,
        "exit_gas_raw": approval.per_exit_gas.approved_raw,
        "attempt_budget": approval.attempt_budget,
    }


def _approved_cap(approval: ApprovalSnapshot, asset_id: str) -> int | None:
    caps = (approval.quote_allowance, approval.base_allowance, approval.gas)
    for cap in caps:
        if cap.asset_id == asset_id:
            return cap.as_int()
    return None


def _position_row(session: Session, owner: uuid.UUID, position_id: str, *, for_update: bool = False) -> PositionRow | None:
    if not position_id:
        return None
    statement = select(PositionRow).where(
        PositionRow.owner_id == owner, PositionRow.position_id == position_id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.execute(statement).scalar_one_or_none()


def _find_decision(session: Session, owner: uuid.UUID, action_id: str, *, for_update: bool = False) -> DecisionRow | None:
    statement = select(DecisionRow).where(
        DecisionRow.owner_id == owner, DecisionRow.action_id == action_id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.execute(statement).scalar_one_or_none()


def _save_decision(session: Session, owner: uuid.UUID, intent: ActionIntent,
                   status: str, reason: str | None, approval: ApprovalSnapshot) -> DecisionRow:
    row = DecisionRow(
        decision_id=uuid.uuid4(), owner_id=owner, agent_id=intent.binding.agent_id,
        wallet_id=intent.binding.wallet_id, network_id=intent.binding.network_id,
        action_id=intent.action_id, review_hash=intent.review_hash,
        operation=intent.operation, status=status, reason=reason,
        binding=_binding_snapshot(intent, approval),
    )
    session.add(row)
    session.flush()
    return row


def _capital_reserved(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str,
                      network_id: str, asset_id: str, *, exclude: uuid.UUID | None = None) -> int:
    statement = select(func.coalesce(func.sum(ReservationRow.raw), 0)).where(
        ReservationRow.owner_id == owner,
        ReservationRow.agent_id == agent_id,
        ReservationRow.wallet_id == wallet_id,
        ReservationRow.network_id == network_id,
        ReservationRow.asset_id == asset_id,
        ReservationRow.state == "RESERVED",
        ReservationRow.scope.in_(_CAPITAL_SCOPES),
    )
    if exclude is not None:
        statement = statement.where(ReservationRow.reservation_id != exclude)
    return _int(session.execute(statement).scalar_one())


def _exit_hold(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
               position_id: str, asset_id: str, *, exclude: uuid.UUID | None = None) -> int:
    statement = select(func.coalesce(func.sum(ReservationRow.raw), 0)).where(
        ReservationRow.owner_id == owner,
        ReservationRow.agent_id == agent_id,
        ReservationRow.wallet_id == wallet_id,
        ReservationRow.network_id == network_id,
        ReservationRow.position_id == position_id,
        ReservationRow.asset_id == asset_id,
        ReservationRow.scope == "INVENTORY",
        ReservationRow.operation == "EXIT",
        ReservationRow.state == "RESERVED",
    )
    if exclude is not None:
        statement = statement.where(ReservationRow.reservation_id != exclude)
    return _int(session.execute(statement).scalar_one())


def _pending_acquisition(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str,
                         network_id: str, asset_id: str, *, exclude: uuid.UUID | None = None) -> int:
    statement = select(func.coalesce(func.sum(ReservationRow.raw), 0)).where(
        ReservationRow.owner_id == owner,
        ReservationRow.agent_id == agent_id,
        ReservationRow.wallet_id == wallet_id,
        ReservationRow.network_id == network_id,
        ReservationRow.asset_id == asset_id,
        ReservationRow.scope == "INVENTORY",
        ReservationRow.operation.in_(ACQUISITIONS),
        ReservationRow.state == "RESERVED",
    )
    if exclude is not None:
        statement = statement.where(ReservationRow.reservation_id != exclude)
    return _int(session.execute(statement).scalar_one())


def _attributed_inventory(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str,
                          network_id: str, asset_id: str) -> int:
    total = session.execute(select(func.coalesce(func.sum(PositionRow.inventory), 0)).where(
        PositionRow.owner_id == owner,
        PositionRow.agent_id == agent_id,
        PositionRow.wallet_id == wallet_id,
        PositionRow.network_id == network_id,
        PositionRow.asset_id == asset_id,
    )).scalar_one()
    return _int(total)


def _attributed_cost(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str,
                     network_id: str, quote_asset: str) -> int:
    """Deployed capital = cost basis of positions quoted in the adopted quote asset only."""
    total = session.execute(select(func.coalesce(func.sum(PositionRow.cost_basis), 0)).where(
        PositionRow.owner_id == owner,
        PositionRow.agent_id == agent_id,
        PositionRow.wallet_id == wallet_id,
        PositionRow.network_id == network_id,
        PositionRow.quote_asset_id == quote_asset,
    )).scalar_one()
    return _int(total)


def _attempt_count(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str) -> int:
    total = session.execute(select(func.coalesce(func.sum(ReservationRow.raw), 0)).where(
        ReservationRow.owner_id == owner,
        ReservationRow.agent_id == agent_id,
        ReservationRow.wallet_id == wallet_id,
        ReservationRow.network_id == network_id,
        ReservationRow.scope == "ATTEMPT",
        ReservationRow.state.in_(("RESERVED", "CONSUMED")),
    )).scalar_one()
    return _int(total)


def _ensure_allowance(session: Session, owner: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
                      asset_id: str, decimals: int, cap: int, approval_id: str, approval_hash: str,
                      reserved_current: int) -> tuple[AllowanceRow | None, str | None]:
    """Return the locked allowance for this wallet asset, or a denial reason.

    Rejects a changed-content reuse of the same approval identity (compared by the
    full approval content hash). A different approval identity is treated as an
    explicit successor: it may raise the cap, but a reduction must keep existing
    consumption and reservations covered.
    """
    statement = select(AllowanceRow).where(
        AllowanceRow.owner_id == owner, AllowanceRow.agent_id == agent_id,
        AllowanceRow.wallet_id == wallet_id, AllowanceRow.network_id == network_id,
        AllowanceRow.asset_id == asset_id,
    ).with_for_update().execution_options(populate_existing=True)
    row = session.execute(statement).scalar_one_or_none()
    if row is None:
        session.execute(pg_insert(AllowanceRow).values(
            allowance_id=uuid.uuid4(), owner_id=owner, agent_id=agent_id, wallet_id=wallet_id,
            network_id=network_id, asset_id=asset_id, decimals=decimals, approval_id=approval_id,
            approval_hash=approval_hash, approved=Decimal(cap), consumed=Decimal(0),
        ).on_conflict_do_nothing(
            index_elements=["owner_id", "agent_id", "wallet_id", "network_id", "asset_id"]))
        session.flush()
        row = session.execute(statement).scalar_one()
    if _int(row.decimals) != decimals:
        return None, "DECIMALS_MISMATCH"
    if row.approval_id == approval_id:
        if row.approval_hash != approval_hash or _int(row.approved) != cap:
            return None, "APPROVAL_MISMATCH"
        return row, None
    # A different approval identity: an explicit successor. It must not erase
    # consumption or outstanding reservations.
    if cap < _int(row.consumed) + reserved_current:
        return None, "RENEWAL_ERASES_COMMITMENTS"
    row.approved = Decimal(cap)
    row.approval_id = approval_id
    row.approval_hash = approval_hash
    return row, None


class AdmissionService:
    def __init__(self, session_factory: sessionmaker[Session], *, stops: StopReader | None = None) -> None:
        self._factory = session_factory
        self._stops = stops

    def _stop_denial(self, session: Session, owner: uuid.UUID, intent: ActionIntent) -> str | None:
        """The durable stop reason that denies this intent, or None.

        Reads the persisted stop records inside the caller's transaction. When no
        stop reader is wired, behavior is unchanged.
        """
        if self._stops is None:
            return None
        reasons = self._stops.denial_reasons(
            session, owner, agent_id=intent.binding.agent_id, wallet_id=intent.binding.wallet_id,
            network_id=intent.binding.network_id, position_id=intent.position_id,
            operation=intent.operation)
        return ";".join(reasons) if reasons else None

    def _stop_denial_for_row(self, session: Session, owner: uuid.UUID, row: DecisionRow) -> str | None:
        """The durable stop reason that denies a saved decision, or None."""
        if self._stops is None:
            return None
        reasons = self._stops.denial_reasons(
            session, owner, agent_id=row.agent_id, wallet_id=row.wallet_id, network_id=row.network_id,
            position_id=str(row.binding.get("position_id") or ""), operation=row.operation)
        return ";".join(reasons) if reasons else None

    # ----------------------------------------------------------------- propose

    def propose(
        self,
        verified_owner_id: uuid.UUID,
        intent: ActionIntent,
        approval: ApprovalSnapshot,
        context: AdmissionContext,
    ) -> AdmissionDecision:
        """Validate without persisting. Returns PROPOSED or DENIED with its reason."""
        position_exists = context.holdings.positions.get(intent.position_id) is not None
        reasons = denial_reasons(intent, approval, context, position_exists)
        if reasons:
            return AdmissionDecision(
                decision_id=uuid.uuid4(), owner_id=verified_owner_id, action_id=intent.action_id,
                review_hash=intent.review_hash, operation=intent.operation, status="DENIED",
                reason=";".join(sorted(set(reasons))), created_at=context.checked_at)
        return AdmissionDecision(
            decision_id=uuid.uuid4(), owner_id=verified_owner_id, action_id=intent.action_id,
            review_hash=intent.review_hash, operation=intent.operation, status="PROPOSED",
            reason=None, created_at=context.checked_at)

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

                _acquire_wallet_lock(session, verified_owner_id, intent.binding.agent_id,
                                     intent.binding.wallet_id, intent.binding.network_id)
                # Re-check the immutable action identity under the lock: a concurrent
                # identical admission must return the same saved decision, not fail.
                existing = _find_decision(session, verified_owner_id, intent.action_id)
                if existing is not None:
                    if existing.review_hash == intent.review_hash:
                        session.commit()
                        return _decision_view(session, existing)
                    session.rollback()
                    raise StaleInput(intent.action_id)
                denial = self._admit_locked(session, verified_owner_id, intent, approval, context)
                if denial is not None:
                    row = _save_decision(session, verified_owner_id, intent, "DENIED", denial, approval)
                    session.commit()
                    return _decision_view(session, row)
                persisted = _save_decision(session, verified_owner_id, intent, "ADMITTED", None, approval)
                session.commit()
                return _decision_view(session, persisted)
            except SQLAlchemyError:
                session.rollback()
                raise
            except AdmissionError:
                session.rollback()
                raise

    def _admit_locked(
        self,
        session: Session,
        owner: uuid.UUID,
        intent: ActionIntent,
        approval: ApprovalSnapshot,
        context: AdmissionContext,
    ) -> str | None:
        # One unresolved or breached economic state per agent wallet and network.
        unresolved = session.execute(select(DecisionRow.action_id).where(
            DecisionRow.owner_id == owner, DecisionRow.wallet_id == intent.binding.wallet_id,
            DecisionRow.network_id == intent.binding.network_id,
            DecisionRow.status.in_(("SUBMISSION_UNKNOWN", "BREACHED"))).limit(1)).scalar_one_or_none()
        if unresolved is not None:
            return "UNRESOLVED_PRIOR_ACTION"

        # Durable scoped stops. The persisted records are consulted inside this
        # transaction under the per-wallet lock, so a newly recorded stop denies
        # the exact scoped operation. This never rewrites the immutable approval
        # snapshot and it never widens a selected stop.
        stop_reason = self._stop_denial(session, owner, intent)
        if stop_reason is not None:
            return stop_reason

        durable = _position_row(session, owner, intent.position_id, for_update=True)
        snapshot = context.holdings.positions.get(intent.position_id)
        if intent.operation == "ENTRY":
            position_exists = durable is not None or snapshot is not None
        else:
            position_exists = durable is not None

        reasons = denial_reasons(intent, approval, context, position_exists)
        if reasons:
            return ";".join(sorted(set(reasons)))

        if intent.operation == "ENTRY":
            position = None
        else:
            # ADDITION and EXIT both use an existing durable position; validate its
            # complete binding before any capacity decision.
            assert durable is not None  # POSITION_MISSING already returned above
            expected = (intent.binding.agent_id, intent.binding.wallet_id, intent.binding.network_id,
                        intent.quantity.asset_id, intent.quantity.decimals,
                        intent.binding.strategy_revision, intent.binding.mandate_id)
            actual = (durable.agent_id, durable.wallet_id, durable.network_id, durable.asset_id,
                      _int(durable.decimals), durable.strategy_revision, durable.mandate_id)
            if actual != expected:
                return "POSITION_BINDING_MISMATCH"
            # Q4: bind the durable adopted quote identity before reserving.
            if (durable.quote_asset_id != intent.input.quote_asset_id
                    or _int(durable.quote_decimals) != approval.quote_allowance.decimals):
                return "POSITION_QUOTE_MISMATCH"
            if snapshot is not None:
                snapshot_identity = (snapshot.binding.agent_id, snapshot.binding.wallet_id,
                                     snapshot.binding.network_id, snapshot.asset_id, snapshot.decimals,
                                     snapshot.as_int())
                durable_identity = (durable.agent_id, durable.wallet_id, durable.network_id,
                                    durable.asset_id, _int(durable.decimals), _int(durable.inventory))
                if snapshot_identity != durable_identity:
                    return "STALE_POSITION_SNAPSHOT"
            position = durable

        current_inventory = _int(position.inventory) if position is not None else None
        plan = plan_reservations(intent, approval, current_inventory)
        if not plan.ok:
            return plan.reason

        b = intent.binding
        # Quote and gas capital coverage and holdings.
        for asset_id, sought in self._capital_needs(plan).items():
            cap = _approved_cap(approval, asset_id)
            if cap is None:
                return "ALLOWANCE_UNSPECIFIED"
            decimals = self._decimals_for(approval, context, asset_id)
            if decimals is None:
                return "DECIMALS_UNKNOWN"
            reserved = _capital_reserved(session, owner, b.agent_id, b.wallet_id, b.network_id, asset_id)
            row, reason = _ensure_allowance(session, owner, b.agent_id, b.wallet_id, b.network_id,
                                            asset_id, decimals, cap, approval.approval_id,
                                            approval.content_hash(), reserved)
            if reason is not None:
                return reason
            assert row is not None
            if not covered(_int(row.approved), _int(row.consumed), reserved, sought):
                return "CAPACITY_UNAVAILABLE"
            holdings = context.holdings.balances.get(asset_id)
            if holdings is None or holdings.as_int() < reserved + sought:
                return "HOLDINGS_SHORTFALL"

        # Sell coverage: cumulative sold plus attributed and pending inventory must
        # not exceed the finite sell ceiling. An acquisition adds its planned bound.
        quantity = intent.quantity.as_int()
        base_asset = intent.quantity.asset_id
        base_cap = _approved_cap(approval, base_asset)
        if base_cap is None:
            return "ALLOWANCE_UNSPECIFIED"
        base_decimals = approval.base_allowance.decimals
        base_row, reason = _ensure_allowance(session, owner, b.agent_id, b.wallet_id, b.network_id,
                                             base_asset, base_decimals, base_cap, approval.approval_id,
                                             approval.content_hash(),
                                             _attributed_inventory(session, owner, b.agent_id, b.wallet_id,
                                                                   b.network_id, base_asset)
                                             + _pending_acquisition(session, owner, b.agent_id, b.wallet_id,
                                                                    b.network_id, base_asset))
        if reason is not None:
            return reason
        assert base_row is not None
        coverage = (_attributed_inventory(session, owner, b.agent_id, b.wallet_id, b.network_id, base_asset)
                    + _pending_acquisition(session, owner, b.agent_id, b.wallet_id, b.network_id, base_asset))
        if intent.operation in ACQUISITIONS:
            if _int(base_row.consumed) + coverage + quantity > _int(base_row.approved):
                return "SELL_CAPACITY_UNAVAILABLE"

        # Adopted allocation bounds deployed capital (cost basis plus pending buys).
        allocation = approval.allocation_quote
        if intent.operation in ACQUISITIONS and intent.input.quote_input is not None:
            quote_asset = intent.input.quote_asset_id
            if allocation.asset_id != quote_asset:
                return "ALLOCATION_ASSET_MISMATCH"
            deployed = (_attributed_cost(session, owner, b.agent_id, b.wallet_id, b.network_id, quote_asset)
                        + _capital_reserved(session, owner, b.agent_id, b.wallet_id, b.network_id, quote_asset))
            if deployed + intent.input.quote_input.as_int() > allocation.as_int():
                return "ALLOCATION_EXCEEDED"

        attempt_needs = sum(need.raw for need in plan.needs if need.scope == "ATTEMPT")
        if attempt_needs and _attempt_count(session, owner, b.agent_id, b.wallet_id, b.network_id) + attempt_needs > approval.attempt_budget:
            return "ATTEMPT_BUDGET_EXHAUSTED"

        if intent.operation == "EXIT":
            assert position is not None
            # The exit draws its gas/attempt coverage from the position's retained
            # hold; any shortfall is funded from the wallet's approved budget, so a
            # partial exit never strands the remaining inventory (G2).
            hold_id = _hold_action_id(intent.position_id)
            holds = session.execute(select(ReservationRow).where(
                ReservationRow.owner_id == owner, ReservationRow.action_id == hold_id,
                ReservationRow.position_id == intent.position_id, ReservationRow.state == "RESERVED",
                ReservationRow.scope.in_(("GAS", "ATTEMPT")),
            ).with_for_update().execution_options(populate_existing=True)).scalars().all()
            gas_asset = approval.gas.asset_id
            gas_decimals = approval.gas.decimals
            # Draw gas only from holds of the exit's own gas asset/decimals; a hold from
            # a different approval gas asset cannot fund this exit (H2).
            hold_gas = sum(_int(r.raw) for r in holds
                           if r.scope == "GAS" and r.asset_id == gas_asset and _int(r.decimals) == gas_decimals)
            hold_att = sum(_int(r.raw) for r in holds if r.scope == "ATTEMPT")
            need_gas = approval.per_exit_gas.as_int()
            take_gas = min(hold_gas, need_gas)
            take_att = min(hold_att, 1)
            deficit_gas = need_gas - take_gas
            deficit_att = 1 - take_att
            other_reserved = _exit_hold(session, owner, b.agent_id, b.wallet_id, b.network_id,
                                        intent.position_id, base_asset)
            if _int(position.inventory) - other_reserved < quantity:
                return "INVENTORY_SHORTFALL"
            gas_cap = approval.gas.as_int()
            reserved_gas = _capital_reserved(session, owner, b.agent_id, b.wallet_id, b.network_id, gas_asset)
            gas_row, reason = _ensure_allowance(session, owner, b.agent_id, b.wallet_id, b.network_id,
                                                gas_asset, gas_decimals, gas_cap, approval.approval_id,
                                                approval.content_hash(), reserved_gas)
            if reason is not None:
                return reason
            assert gas_row is not None
            if not covered(_int(gas_row.approved), _int(gas_row.consumed), reserved_gas, deficit_gas):
                return "CAPACITY_UNAVAILABLE"
            if deficit_gas > 0:
                gas_holdings = context.holdings.balances.get(gas_asset)
                if gas_holdings is None or gas_holdings.as_int() < reserved_gas + deficit_gas:
                    return "HOLDINGS_SHORTFALL"
            if deficit_att > 0:
                if _attempt_count(session, owner, b.agent_id, b.wallet_id, b.network_id) + deficit_att > approval.attempt_budget:
                    return "ATTEMPT_BUDGET_EXHAUSTED"
            # A partial exit must leave a usable exit path for the remaining inventory
            # under the unchanged approval. Already-reserved hold units count as future
            # coverage; only a true deficit is denied before mutating (J1).
            remaining_inventory = _int(position.inventory) - other_reserved - quantity
            if remaining_inventory > 0:
                remaining_hold_att = hold_att - take_att
                attempt_free_after = approval.attempt_budget - (_attempt_count(session, owner, b.agent_id, b.wallet_id, b.network_id) + deficit_att)
                if remaining_hold_att + attempt_free_after < 1:
                    return "PARTIAL_EXIT_UNCOVERED"
                remaining_hold_gas = hold_gas - take_gas
                gas_free_after = (_int(gas_row.approved) - _int(gas_row.consumed) - (reserved_gas + deficit_gas))
                if remaining_hold_gas + gas_free_after < need_gas:
                    return "PARTIAL_EXIT_UNCOVERED"
            _take_from_holds(holds, take_gas, take_att, gas_asset, gas_decimals)
            if need_gas > 0:
                _add_exit_reservation(session, owner, intent, "GAS", gas_asset, gas_decimals, need_gas)
            _add_exit_reservation(session, owner, intent, "ATTEMPT", ATTEMPT_ASSET, 0, 1)

        self._publish_reservations(session, owner, intent, plan)
        return None

    @staticmethod
    def _capital_needs(plan: ReservationPlan) -> dict[str, int]:
        needs: dict[str, int] = {}
        for need in plan.needs:
            if need.scope in _CAPITAL_SCOPES:
                needs[need.asset_id] = needs.get(need.asset_id, 0) + need.raw
        return needs

    @staticmethod
    def _decimals_for(approval: ApprovalSnapshot, context: AdmissionContext, asset_id: str) -> int | None:
        for cap in (approval.quote_allowance, approval.base_allowance, approval.gas):
            if cap.asset_id == asset_id:
                return cap.decimals
        holding = context.holdings.balances.get(asset_id)
        return holding.decimals if holding is not None else None

    def _publish_reservations(
        self,
        session: Session,
        owner: uuid.UUID,
        intent: ActionIntent,
        plan: ReservationPlan,
    ) -> None:
        for need in plan.needs:
            session.add(ReservationRow(
                reservation_id=uuid.uuid4(), owner_id=owner,
                agent_id=intent.binding.agent_id, wallet_id=intent.binding.wallet_id,
                network_id=intent.binding.network_id, action_id=intent.action_id,
                operation=intent.operation, review_hash=intent.review_hash, scope=need.scope,
                position_id=need.position_id or "", asset_id=need.asset_id,
                decimals=need.decimals, raw=Decimal(need.raw), state="RESERVED",
            ))
        if plan.requires_new_position and intent.position_id:
            quote = intent.input.quote_input
            session.add(PositionRow(
                owner_id=owner, position_id=intent.position_id,
                agent_id=intent.binding.agent_id, wallet_id=intent.binding.wallet_id,
                network_id=intent.binding.network_id,
                strategy_revision=intent.binding.strategy_revision, mandate_id=intent.binding.mandate_id,
                asset_id=intent.quantity.asset_id, decimals=intent.quantity.decimals,
                quote_asset_id=intent.input.quote_asset_id,
                quote_decimals=quote.decimals if quote is not None else 0,
                inventory=Decimal(0), cost_basis=Decimal(0), realized_quote=Decimal(0),
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
                reserved = (_capital_reserved(session, verified_owner_id, row.agent_id, row.wallet_id,
                                              row.network_id, row.asset_id)
                            + _pending_acquisition(session, verified_owner_id, row.agent_id, row.wallet_id,
                                                   row.network_id, row.asset_id)
                            + _attributed_inventory(session, verified_owner_id, row.agent_id, row.wallet_id,
                                                    row.network_id, row.asset_id))
                summaries.append(AllowanceSummary.from_literals(
                    owner_id=verified_owner_id, agent_id=row.agent_id, wallet_id=row.wallet_id,
                    network_id=row.network_id, asset_id=row.asset_id, decimals=_int(row.decimals),
                    approved=_int(row.approved), consumed=_int(row.consumed), reserved=reserved))
            return summaries

    def retrieve_receipts(
        self,
        verified_owner_id: uuid.UUID,
        *,
        action_id: str | None = None,
        wallet_id: str | None = None,
        network_id: str | None = None,
        limit: int = 100,
    ) -> list[SavedReceipt]:
        with self._factory() as session:
            statement = select(ReceiptRow).where(ReceiptRow.owner_id == verified_owner_id)
            if action_id is not None:
                statement = statement.where(ReceiptRow.action_id == action_id)
            if wallet_id is not None:
                statement = statement.where(ReceiptRow.wallet_id == wallet_id)
            if network_id is not None:
                statement = statement.where(ReceiptRow.network_id == network_id)
            rows = session.execute(
                statement.order_by(ReceiptRow.created_at, ReceiptRow.receipt_id).limit(limit)
            ).scalars().all()
            return [_saved_receipt(row) for row in rows]

    # ----------------------------------------------------------------- cancel

    def cancel(self, verified_owner_id: uuid.UUID, action_id: str) -> CancellationOutcome:
        with self._factory() as session:
            try:
                row = _find_decision(session, verified_owner_id, action_id)
                if row is None:
                    return CancellationOutcome(action_id=action_id, decision_status="NOT_FOUND",
                                               reason=None, released=[])
                agent_id, wallet_id, network_id = row.agent_id, row.wallet_id, row.network_id
                session.rollback()
                _acquire_wallet_lock(session, verified_owner_id, agent_id, wallet_id, network_id)
                session.expire_all()
                row = _find_decision(session, verified_owner_id, action_id, for_update=True)
                assert row is not None
                if row.status not in _CANCELLABLE:
                    session.commit()
                    return CancellationOutcome(action_id=action_id, decision_status=row.status,
                                               reason="NOT_CANCELLABLE_AFTER_SUBMISSION", released=[])
                released = _release_all(session, row, "CANCELLED")
                session.commit()
                return CancellationOutcome(action_id=action_id, decision_status="CANCELLED",
                                           reason=None, released=released)
            except SQLAlchemyError:
                session.rollback()
                raise

    # -------------------------------------------------------- acquire submission

    def acquire_submission(self, verified_owner_id: uuid.UUID, action_id: str) -> str:
        """Atomically acquire submission ownership for one action.

        Under the per-wallet advisory lock, move an `ADMITTED` action to the
        submission-owned `SUBMISSION_UNKNOWN` state and return `ACQUIRED`. If the
        action is missing, already unknown, breached, cancelled or otherwise not
        `ADMITTED`, return its current status and change nothing. No receipt is
        written: ownership is a pre-call state, not a transport outcome, and the
        caller records its own pre-call attempt evidence.
        """
        with self._factory() as session:
            try:
                row = _find_decision(session, verified_owner_id, action_id)
                if row is None:
                    return "NOT_FOUND"
                agent_id, wallet_id, network_id = row.agent_id, row.wallet_id, row.network_id
                session.rollback()
                _acquire_wallet_lock(session, verified_owner_id, agent_id, wallet_id, network_id)
                session.expire_all()
                row = _find_decision(session, verified_owner_id, action_id, for_update=True)
                if row is None:
                    return "NOT_FOUND"
                if row.status != "ADMITTED":
                    session.commit()
                    return row.status
                # Atomic durable-stop guard. This runs under the same per-wallet
                # lock the stop write uses, so a stop that committed before this
                # transition refuses ownership and the caller makes no transport
                # call. An action already submission-owned is unaffected by a later
                # stop; it reconciles its original reference.
                if self._stop_denial_for_row(session, verified_owner_id, row) is not None:
                    session.commit()
                    return "STOPPED_SCOPE"
                row.status = "SUBMISSION_UNKNOWN"
                session.commit()
                return "ACQUIRED"
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
                agent_id, wallet_id, network_id = row.agent_id, row.wallet_id, row.network_id
                session.rollback()
                _acquire_wallet_lock(session, verified_owner_id, agent_id, wallet_id, network_id)
                session.expire_all()
                row = _find_decision(session, verified_owner_id, action_id, for_update=True)
                assert row is not None

                if not _receipt_matches(row, action_id, receipt):
                    return ReconciliationOutcome(action_id=action_id, decision_status=row.status,
                                                 reason="ACTION_IDENTITY_MISMATCH")
                if row.status in _TERMINAL:
                    return ReconciliationOutcome(action_id=action_id, decision_status=row.status,
                                                 reason="RECONCILIATION_TERMINAL_STATE")

                outcome = receipt.outcome
                if row.status == "BREACHED" and outcome in {"CONFIRMED", "REVERTED", "SUBMISSION_UNKNOWN"}:
                    # A recorded breach is never silently replaced. A later receipt
                    # that would settle or downgrade it is refused, so the durable
                    # breach, its receipts, its reservations and its exposure are
                    # preserved. A proved pre-broadcast denial and a cancellation keep
                    # their existing contradictory handling below.
                    session.commit()
                    return ReconciliationOutcome(action_id=action_id, decision_status="BREACHED",
                                                 reason="CONTRADICTORY_RECOVERY")

                if outcome == "SUBMISSION_UNKNOWN":
                    _save_receipt(session, row, receipt, outcome, breach=False)
                    row.status = "SUBMISSION_UNKNOWN"
                    session.commit()
                    return ReconciliationOutcome(
                        action_id=action_id, decision_status="SUBMISSION_UNKNOWN", reason=None,
                        retained=[_reservation_amount(r) for r in _action_reservations(session, row)
                                  if r.state == "RESERVED"])

                if outcome == "CANCELLED":
                    if row.status not in _CANCELLABLE:
                        session.commit()
                        return ReconciliationOutcome(action_id=action_id, decision_status=row.status,
                                                     reason="NOT_CANCELLABLE_AFTER_SUBMISSION")
                    _save_receipt(session, row, receipt, outcome, breach=False)
                    _release_all(session, row, "CANCELLED")
                    session.commit()
                    return ReconciliationOutcome(action_id=action_id, decision_status="CANCELLED", reason=None)

                if outcome == "PREBROADCAST_DENIED":
                    if row.status not in _PREBROADCAST_CLEARABLE:
                        session.commit()
                        return ReconciliationOutcome(action_id=action_id, decision_status=row.status,
                                                     reason="CONTRADICTORY_RECOVERY")
                    _save_receipt(session, row, receipt, outcome, breach=False)
                    _release_all(session, row, "DENIED", reason="PREBROADCAST_DENIED")
                    session.commit()
                    return ReconciliationOutcome(action_id=action_id, decision_status="DENIED",
                                                 reason="PREBROADCAST_DENIED")

                if outcome in {"CONFIRMED", "REVERTED"}:
                    try:
                        # Savepoint keeps the wallet advisory lock and outer transaction
                        # across a breach, so protection commits atomically (Q2).
                        with session.begin_nested():
                            consumed, released = _settle(session, row, receipt)
                    except AccountingBreach as breach:
                        row = _find_decision(session, verified_owner_id, action_id, for_update=True)
                        assert row is not None
                        _save_receipt(session, row, receipt, outcome, breach=True)
                        row.status = "BREACHED"
                        row.reason = breach.reason
                        session.commit()
                        return ReconciliationOutcome(action_id=action_id, decision_status="BREACHED",
                                                     reason=breach.reason)
                    _save_receipt(session, row, receipt, outcome, breach=False)
                    session.commit()
                    return ReconciliationOutcome(
                        action_id=action_id, decision_status=row.status, reason=None,
                        consumed=consumed, released=released)

                raise AdmissionError(f"unhandled receipt outcome {outcome!r}")
            except SQLAlchemyError:
                session.rollback()
                raise


# ------------------------------------------------------------------------- helpers

def _receipt_matches(row: DecisionRow, action_id: str, receipt: ActionReceipt) -> bool:
    binding = row.binding
    return (
        receipt.action_id == action_id == row.action_id
        and receipt.binding.agent_id == binding.get("agent_id")
        and receipt.binding.wallet_id == binding.get("wallet_id")
        and receipt.binding.network_id == binding.get("network_id")
        and receipt.binding.strategy_revision == binding.get("strategy_revision")
        and receipt.binding.mandate_id == binding.get("mandate_id")
    )


def _decision_view(session: Session, row: DecisionRow) -> AdmissionDecision:
    reservations: list[ReservationView] = []
    for res in session.execute(select(ReservationRow).where(
            ReservationRow.owner_id == row.owner_id, ReservationRow.action_id == row.action_id,
    )).scalars().all():
        view = _saved_reservation(res)
        reservations.append(ReservationView(
            reservation_id=view.reservation_id, scope=view.scope, position_id=view.position_id,
            amount=view.amount, state=view.state))
    return AdmissionDecision(
        decision_id=row.decision_id, owner_id=row.owner_id, action_id=row.action_id,
        review_hash=row.review_hash, operation=row.operation, status=row.status,
        reason=row.reason, created_at=_utc_iso(row.created_at), reservations=reservations)


def _saved_decision(row: DecisionRow) -> SavedDecision:
    return SavedDecision(
        decision_id=row.decision_id, owner_id=row.owner_id, action_id=row.action_id,
        review_hash=row.review_hash, operation=row.operation, status=row.status,
        reason=row.reason, created_at=_utc_iso(row.created_at))


def _saved_reservation(row: ReservationRow) -> SavedReservation:
    return SavedReservation(
        reservation_id=row.reservation_id, owner_id=row.owner_id, action_id=row.action_id,
        scope=row.scope, position_id=row.position_id or None,
        amount=_amount(row.asset_id, _int(row.raw), _int(row.decimals)), state=row.state)


def _reservation_amount(row: ReservationRow) -> AssetAmount:
    return _amount(row.asset_id, _int(row.raw), _int(row.decimals))


def _amount_dict(amount: AssetAmount | None) -> dict[str, Any] | None:
    if amount is None:
        return None
    return {"asset_id": amount.asset_id, "raw": amount.raw, "decimals": amount.decimals}


def _save_receipt(session: Session, row: DecisionRow, receipt: ActionReceipt,
                  outcome: str, *, breach: bool) -> None:
    content = {
        "outcome": outcome,
        "review_hash": row.review_hash,
        "operation": row.operation,
        "breach": breach,
        "actual_input": _amount_dict(receipt.actual_input),
        "actual_output": _amount_dict(receipt.actual_output),
        "actual_gas": _amount_dict(receipt.actual_gas),
    }
    session.add(ReceiptRow(
        receipt_id=uuid.uuid4(), owner_id=row.owner_id, agent_id=row.agent_id,
        wallet_id=row.wallet_id, network_id=row.network_id, action_id=row.action_id,
        position_id=str(row.binding.get("position_id") or ""), operation=row.operation,
        review_hash=row.review_hash, outcome=outcome, breach=breach, content=content,
    ))


def _saved_receipt(row: ReceiptRow) -> SavedReceipt:
    return SavedReceipt(
        receipt_id=row.receipt_id, owner_id=row.owner_id, action_id=row.action_id,
        position_id=row.position_id or None, operation=row.operation, outcome=row.outcome,
        breach=bool(row.breach), created_at=_utc_iso(row.created_at), content=row.content,
    )


def _action_reservations(session: Session, row: DecisionRow, *, for_update: bool = False) -> list[ReservationRow]:
    statement = select(ReservationRow).where(
        ReservationRow.owner_id == row.owner_id, ReservationRow.action_id == row.action_id,
        ReservationRow.operation != "EXIT_HOLD",
    ).order_by(ReservationRow.scope, ReservationRow.asset_id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.execute(statement).scalars().all()


def _release_all(session: Session, row: DecisionRow, status: str, reason: str | None = None) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for reservation in _action_reservations(session, row, for_update=True):
        if reservation.state != "RESERVED":
            continue
        if row.operation == "EXIT" and reservation.scope in ("GAS", "ATTEMPT"):
            # Return the retained exit coverage to the position hold.
            _create_hold(session, row, reservation.scope, reservation.asset_id,
                         _int(reservation.decimals), _int(reservation.raw))
        reservation.state = "RELEASED"
        reservation.reconciled_at = func.now()
        ids.append(reservation.reservation_id)
    row.status = status
    if reason is not None:
        row.reason = reason
    session.flush()
    return ids


def _release_position_holds(session: Session, row: DecisionRow, position_id: str) -> None:
    hold_id = _hold_action_id(position_id)
    hold_rows = session.execute(select(ReservationRow).where(
        ReservationRow.owner_id == row.owner_id, ReservationRow.action_id == hold_id,
        ReservationRow.position_id == position_id, ReservationRow.state == "RESERVED",
    ).with_for_update().execution_options(populate_existing=True)).scalars().all()
    for hold in hold_rows:
        hold.state = "RELEASED"
        hold.reconciled_at = func.now()


def _charge(session: Session, row: DecisionRow, reservation: ReservationRow, amount: int) -> None:
    """Add a reconciled actual to the wallet allowance, counting other live reservations.

    Fails closed when consumed + amount + other reservations would exceed approved.
    The reservation being settled is excluded because it is consumed or released now.
    """
    allowance = _lock_allowance_for(session, row, reservation.asset_id, reservation.decimals)
    if allowance is None:
        raise AccountingBreach("ALLOWANCE_MISSING")
    others = _capital_reserved(session, row.owner_id, row.agent_id, row.wallet_id, row.network_id,
                               reservation.asset_id, exclude=reservation.reservation_id)
    if _int(allowance.consumed) + amount + others > _int(allowance.approved):
        raise AccountingBreach("CONSUMED_EXCEEDS_APPROVED")
    allowance.consumed = Decimal(_int(allowance.consumed) + amount)


def _charge_amount(session: Session, row: DecisionRow, asset_id: str, decimals: int, amount: int) -> None:
    """Charge a reconciled actual with no matching reservation (e.g. a zero-hold exit)."""
    allowance = _lock_allowance_for(session, row, asset_id, decimals)
    if allowance is None:
        raise AccountingBreach("ALLOWANCE_MISSING")
    others = _capital_reserved(session, row.owner_id, row.agent_id, row.wallet_id, row.network_id, asset_id)
    if _int(allowance.consumed) + amount + others > _int(allowance.approved):
        raise AccountingBreach("CONSUMED_EXCEEDS_APPROVED")
    allowance.consumed = Decimal(_int(allowance.consumed) + amount)


def _require_actual(amount: AssetAmount | None, asset_id: str, decimals: int, reason: str) -> int:
    if amount is None:
        raise AccountingBreach(reason)
    if amount.asset_id != asset_id or amount.decimals != decimals:
        raise AccountingBreach(reason)
    return amount.as_int()


def _hold_action_id(position_id: str) -> str:
    return f"{HOLD_ACTION_PREFIX}{position_id}"


def _create_hold(session: Session, row: DecisionRow, scope: str, asset_id: str,
                 decimals: int, raw: int) -> None:
    position_id = str(row.binding.get("position_id") or "")
    hold_id = _hold_action_id(position_id)
    existing = session.execute(select(ReservationRow).where(
        ReservationRow.owner_id == row.owner_id, ReservationRow.action_id == hold_id,
        ReservationRow.scope == scope, ReservationRow.asset_id == asset_id,
        ReservationRow.position_id == position_id, ReservationRow.state == "RESERVED",
    ).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if existing is not None:
        existing.raw = Decimal(_int(existing.raw) + raw)
        return
    session.add(ReservationRow(
        reservation_id=uuid.uuid4(), owner_id=row.owner_id, agent_id=row.agent_id,
        wallet_id=row.wallet_id, network_id=row.network_id,
        action_id=hold_id, operation="EXIT_HOLD", review_hash=row.review_hash,
        scope=scope, position_id=position_id, asset_id=asset_id, decimals=decimals,
        raw=Decimal(raw), state="RESERVED",
    ))


def _take_from_holds(holds: list[ReservationRow], take_gas: int, take_att: int,
                     gas_asset: str, gas_decimals: int) -> None:
    """Reduce the position hold by the exit coverage it contributes.

    Gas is taken only from rows of the exit's own gas asset/decimals, and never
    more than a row holds (H2).
    """
    remaining_gas, remaining_att = take_gas, take_att
    for hold in holds:
        if remaining_gas <= 0 and remaining_att <= 0:
            break
        take = 0
        if (hold.scope == "GAS" and hold.asset_id == gas_asset
                and _int(hold.decimals) == gas_decimals):
            take = min(remaining_gas, _int(hold.raw))
            remaining_gas -= take
        elif hold.scope == "ATTEMPT":
            take = min(remaining_att, _int(hold.raw))
            remaining_att -= take
        if take > 0:
            hold.raw = Decimal(_int(hold.raw) - take)


def _add_exit_reservation(session: Session, owner: uuid.UUID, intent: ActionIntent,
                          scope: str, asset_id: str, decimals: int, raw: int) -> None:
    session.add(ReservationRow(
        reservation_id=uuid.uuid4(), owner_id=owner, agent_id=intent.binding.agent_id,
        wallet_id=intent.binding.wallet_id, network_id=intent.binding.network_id,
        action_id=intent.action_id, operation="EXIT", review_hash=intent.review_hash,
        scope=scope, position_id=intent.position_id, asset_id=asset_id,
        decimals=decimals, raw=Decimal(raw), state="RESERVED",
    ))


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
    base_decimals = _int(row.binding.get("base_decimals") or 0)
    quote_asset = str(row.binding.get("quote_asset_id") or "")
    quote_decimals = _int(row.binding.get("quote_decimals") or 0)
    gas_asset = str(row.binding.get("gas_asset_id") or "")
    gas_decimals = _int(row.binding.get("gas_decimals") or 0)
    position = _position_row(session, row.owner_id, str(row.binding.get("position_id") or ""), for_update=True)
    if position is not None:
        expected_position = (row.agent_id, row.wallet_id, row.network_id, base_asset, base_decimals,
                             str(row.binding.get("strategy_revision") or ""),
                             str(row.binding.get("mandate_id") or ""))
        actual_position = (position.agent_id, position.wallet_id, position.network_id, position.asset_id,
                           _int(position.decimals), position.strategy_revision, position.mandate_id)
        if actual_position != expected_position:
            raise AccountingBreach("POSITION_BINDING_MISMATCH")
        if position.quote_asset_id != quote_asset or _int(position.quote_decimals) != quote_decimals:
            raise AccountingBreach("QUOTE_BINDING_MISMATCH")

    reservations = _action_reservations(session, row, for_update=True)
    has_gas_reservation = any(r.scope == "GAS" for r in reservations)
    for reservation in reservations:
        if reservation.state != "RESERVED":
            continue

        if reservation.scope == "ATTEMPT":
            if operation in ACQUISITIONS:
                # Consume exactly one entry attempt; retain one for the intended exit.
                reservation.raw = Decimal(1)
                reservation.state = "CONSUMED"
                if committed:
                    _create_hold(session, row, "ATTEMPT", reservation.asset_id, _int(reservation.decimals), 1)
            else:
                reservation.state = "CONSUMED"
            reservation.reconciled_at = func.now()
            consumed_amounts.append(_amount(reservation.asset_id, 1, _int(reservation.decimals)))
            continue

        if reservation.scope == "GAS":
            amount = _require_actual(receipt.actual_gas, reservation.asset_id, _int(reservation.decimals),
                                     "MISSING_RECONCILED_GAS")
            # Retain the intended exit gas as a position hold BEFORE charging, so the
            # cap check counts the retained exit coverage (G1).
            if operation in ACQUISITIONS and committed:
                exit_gas = _int(row.binding.get("exit_gas_raw") or 0)
                if exit_gas > 0:
                    _create_hold(session, row, "GAS", reservation.asset_id, _int(reservation.decimals), exit_gas)
            _charge(session, row, reservation, amount)
            reservation.state = "CONSUMED" if operation == "EXIT" else "RELEASED"
            reservation.reconciled_at = func.now()
            consumed_amounts.append(_amount(reservation.asset_id, amount, _int(reservation.decimals)))
            continue

        if reservation.scope == "CAPITAL":
            if not committed:
                reservation.state = "RELEASED"
                released_amounts.append(_reservation_amount(reservation))
                reservation.reconciled_at = func.now()
                continue
            amount = _require_actual(receipt.actual_input, quote_asset, quote_decimals,
                                     "MISSING_RECONCILED_INPUT")
            _charge(session, row, reservation, amount)
            reservation.state = "CONSUMED"
            reservation.reconciled_at = func.now()
            consumed_amounts.append(_amount(quote_asset, amount, quote_decimals))
            continue

        if reservation.scope == "INVENTORY":
            if position is None:
                raise AccountingBreach("POSITION_MISSING")
            if not committed:
                reservation.state = "RELEASED"
                reservation.reconciled_at = func.now()
                continue
            if operation in ACQUISITIONS:
                acquired = _require_actual(receipt.actual_output, base_asset, base_decimals,
                                           "MISSING_RECONCILED_OUTPUT")
                if receipt.actual_input is None or receipt.actual_input.asset_id != quote_asset:
                    raise AccountingBreach("MISSING_RECONCILED_INPUT")
                invested = receipt.actual_input.as_int()
                # The reconciled actual is authoritative. It must stay within the
                # adopted sell coverage and allocation, or the settlement fails closed.
                base_allowance = _lock_allowance_for(session, row, base_asset, base_decimals)
                if base_allowance is None:
                    raise AccountingBreach("ALLOWANCE_MISSING")
                coverage_others = (
                    _attributed_inventory(session, row.owner_id, row.agent_id, row.wallet_id,
                                          row.network_id, base_asset)
                    + _pending_acquisition(session, row.owner_id, row.agent_id, row.wallet_id,
                                           row.network_id, base_asset, exclude=reservation.reservation_id))
                if _int(base_allowance.consumed) + coverage_others + acquired > _int(base_allowance.approved):
                    raise AccountingBreach("SELL_COVERAGE_EXCEEDED")
                allocation_raw = _int(row.binding.get("allocation_approved_raw") or 0)
                deployed = (_attributed_cost(session, row.owner_id, row.agent_id, row.wallet_id, row.network_id, quote_asset)
                            + _capital_reserved(session, row.owner_id, row.agent_id, row.wallet_id,
                                                row.network_id, quote_asset))
                if deployed + invested > allocation_raw:
                    raise AccountingBreach("ALLOCATION_EXCEEDED")
                position.inventory = Decimal(_int(position.inventory) + acquired)
                position.cost_basis = Decimal(_int(position.cost_basis) + invested)
            else:  # EXIT
                exited = _require_actual(receipt.actual_input, base_asset, base_decimals,
                                         "MISSING_RECONCILED_INPUT")
                if (receipt.actual_output is None or receipt.actual_output.asset_id != quote_asset
                        or receipt.actual_output.decimals != quote_decimals):
                    raise AccountingBreach("MISSING_RECONCILED_OUTPUT")
                proceeds = receipt.actual_output.as_int()
                inventory = _int(position.inventory)
                if inventory <= 0:
                    raise AccountingBreach("INVENTORY_UNDERFLOW")
                # The reconciled exit must fit the inventory not already promised to
                # another RESERVED exit for this position.
                others = _exit_hold(session, row.owner_id, row.agent_id, row.wallet_id, row.network_id,
                                    position.position_id, base_asset, exclude=reservation.reservation_id)
                if exited > inventory - others:
                    raise AccountingBreach("EXIT_EXCEEDS_RESERVED")
                _charge(session, row, reservation, exited)
                basis = _int(position.cost_basis)
                removed = basis * exited // inventory
                position.inventory = Decimal(inventory - exited)
                position.cost_basis = Decimal(basis - removed)
                position.realized_quote = Decimal(_int(position.realized_quote) + (proceeds - removed))
            reservation.state = "CONSUMED"
            reservation.reconciled_at = func.now()

    # A verified full close proves this position needs no further exit. Release only
    # this position's demonstrably unused exit holds, preserving other positions'
    # holds and every receipt/action record (J2).
    if operation == "EXIT" and committed and position is not None and _int(position.inventory) == 0:
        _release_position_holds(session, row, position.position_id)

    # An exit with no reserved GAS row (zero planned exit gas) still spends actual
    # gas; account it and fail closed on an over-cap effect (G1).
    if operation == "EXIT" and not has_gas_reservation:
        amount = _require_actual(receipt.actual_gas, gas_asset, gas_decimals, "MISSING_RECONCILED_GAS")
        _charge_amount(session, row, gas_asset, gas_decimals, amount)
        consumed_amounts.append(_amount(gas_asset, amount, gas_decimals))

    row.status = "CONFIRMED" if committed else "REVERTED"
    session.flush()
    return consumed_amounts, released_amounts


def _lock_allowance_for(session: Session, row: DecisionRow, asset_id: str, decimals: int) -> AllowanceRow | None:
    return session.execute(select(AllowanceRow).where(
        AllowanceRow.owner_id == row.owner_id, AllowanceRow.agent_id == row.agent_id,
        AllowanceRow.wallet_id == row.wallet_id, AllowanceRow.network_id == row.network_id,
        AllowanceRow.asset_id == asset_id,
    ).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()


def _utc_iso(moment: Any) -> str:
    return moment.astimezone(timezone.utc).isoformat() if getattr(moment, "tzinfo", None) is not None else str(moment)