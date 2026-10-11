"""StopService: durable scoped-stop records and read-only enforcement lookup.

A stop is requested by an authenticated owner-equivalent local service and saved
durably. Enforcement is a read against the persisted rows, so a queued action
cannot bypass a newly recorded stop by replay, restart, stale input or another
process. The read participates in the caller's transaction and never writes.

`request_stop` takes the same per-wallet advisory lock the accepted P22 admission
path uses. That lock defines the atomic ordering between a committed stop and
submission ownership: the stop write and the admission/submission-ownership
transition are serialized for one owner, agent, wallet and network. If the stop
commits first, submission ownership is refused and no transport call happens. If
ownership commits first, the action is already submission-owned and the stop
never undoes it.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.service import acquire_wallet_lock
from edge_os_api.stops.models import StopRow
from edge_os_api.stops.types import (
    StopError,
    StopRequest,
    StopView,
    denial_reason,
    stop_denies,
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


def _view(row: StopRow) -> StopView:
    return StopView(
        stop_id=row.stop_id, owner_id=row.owner_id, agent_id=row.agent_id,
        wallet_id=row.wallet_id, network_id=row.network_id, scope=row.scope,
        mode=row.mode, trigger=row.trigger, position_id=row.position_id or None,
        created_at=_iso(row.created_at))


class StopService:
    def __init__(self, session_factory: sessionmaker[Session], *, clock=None) -> None:
        self._factory = session_factory
        self._clock = clock or _utc_now

    # ------------------------------------------------------------------ request

    def request_stop(self, verified_owner_id: uuid.UUID, request: StopRequest) -> StopView:
        """Save a durable scoped stop and return its owner-scoped view.

        An identical repeated request is idempotent: the same durable record is
        returned and no second row is written. No clear, resume or renewal action
        exists in this stage.
        """
        with self._factory() as session:
            try:
                acquire_wallet_lock(session, verified_owner_id, request.agent_id,
                                    request.wallet_id, request.network_id)
                now = self._clock()
                session.execute(pg_insert(StopRow).values(
                    stop_id=uuid.uuid4(), owner_id=verified_owner_id, agent_id=request.agent_id,
                    wallet_id=request.wallet_id, network_id=request.network_id, scope=request.scope,
                    mode=request.mode, trigger=request.trigger, position_id=request.position_id or "",
                    created_at=now,
                ).on_conflict_do_nothing(index_elements=[
                    "owner_id", "agent_id", "wallet_id", "network_id", "scope", "position_id", "mode",
                    "trigger",
                ]))
                session.flush()
                row = session.execute(select(StopRow).where(
                    StopRow.owner_id == verified_owner_id, StopRow.agent_id == request.agent_id,
                    StopRow.wallet_id == request.wallet_id, StopRow.network_id == request.network_id,
                    StopRow.scope == request.scope, StopRow.position_id == (request.position_id or ""),
                    StopRow.mode == request.mode, StopRow.trigger == request.trigger,
                )).scalar_one()
                session.commit()
                return _view(row)
            except SQLAlchemyError:
                session.rollback()
                raise

    # ---------------------------------------------------------------- retrieval

    def retrieve_stops(
        self,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str | None = None,
        wallet_id: str | None = None,
        network_id: str | None = None,
        position_id: str | None = None,
    ) -> list[StopView]:
        """Expose the owner-scoped durable stop records, oldest first.

        Another owner sees nothing. Broad history retrieval (no `position_id`)
        returns every owner stop, optionally filtered by agent, wallet or network.

        A `position_id` filter needs the exact agent, wallet and network scope,
        because this local module has no adopted position-to-wallet mapping. It
        returns only that wallet's position stop and that wallet's covering
        agent-wallet-network stops, so a stop on another wallet is never reported
        as covering this position. A position filter without the exact scope is
        refused rather than guessed.
        """
        if position_id is not None and (agent_id is None or wallet_id is None or network_id is None):
            raise StopError(
                "a position-filtered stop lookup requires the exact agent_id, wallet_id and network_id scope")
        with self._factory() as session:
            statement = select(StopRow).where(StopRow.owner_id == verified_owner_id)
            if agent_id is not None:
                statement = statement.where(StopRow.agent_id == agent_id)
            if wallet_id is not None:
                statement = statement.where(StopRow.wallet_id == wallet_id)
            if network_id is not None:
                statement = statement.where(StopRow.network_id == network_id)
            rows = session.execute(
                statement.order_by(StopRow.created_at, StopRow.stop_id)).scalars().all()
            views = [_view(row) for row in rows]
            if position_id is not None:
                views = [view for view in views
                         if view.scope == "AGENT_WALLET_NETWORK" or view.position_id == position_id]
            return views

    # ------------------------------------------------------------ enforcement

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
    ) -> list[str]:
        """The durable stop reasons that deny this operation for this action scope.

        The lookup reads the persisted rows inside the caller's transaction, so it
        observes every committed stop and never a caller-supplied omission. An
        agent-wallet-network stop covers every position in the wallet; a position
        stop covers only its exact position. A stop on another wallet or owner is
        never returned.
        """
        rows = session.execute(select(StopRow).where(
            StopRow.owner_id == verified_owner_id, StopRow.agent_id == agent_id,
            StopRow.wallet_id == wallet_id, StopRow.network_id == network_id,
        )).scalars().all()
        reasons: set[str] = set()
        for row in rows:
            if row.scope == "POSITION" and row.position_id != (position_id or ""):
                continue
            if stop_denies(row.mode, operation):
                reasons.add(denial_reason(row.mode))
        return sorted(reasons)
