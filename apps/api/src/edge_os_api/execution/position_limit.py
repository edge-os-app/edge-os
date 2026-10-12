"""One open or pending position per agent wallet and network for the connected journey.

The accepted P06/P02 strategy fixes `risk_limits.max_open_positions` at 1, and the connected worker gives each
entry its own position id. This read-only control enforces the limit where it holds atomically: the accepted
P22 admission (`admit_and_reserve`, `acquire_submission`) and P23 revalidation consult it through the same
`StopReader` seam, inside their transaction, and P22 runs it under the shared per-wallet advisory lock that
also serializes every settlement. An ENTRY or ADDITION is denied `POSITION_ALREADY_OPEN` while another
position of the same agent wallet holds inventory or carries an unresolved entry/addition. Exits are never
denied by this control.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from edge_os_api.admission.models import DecisionRow, PositionRow

_ACQUISITIONS = ("ENTRY", "ADDITION")
_UNRESOLVED = ("ADMITTED", "SUBMISSION_UNKNOWN", "BREACHED")


class OnePositionPerWallet:
    def denial_reasons(self, session: Session, verified_owner_id: uuid.UUID, *, agent_id: str, wallet_id: str,
                       network_id: str, position_id: str, operation: str) -> list[str]:
        if operation not in _ACQUISITIONS:
            return []
        held = session.execute(select(PositionRow.position_id).where(
            PositionRow.owner_id == verified_owner_id, PositionRow.agent_id == agent_id,
            PositionRow.wallet_id == wallet_id, PositionRow.network_id == network_id,
            PositionRow.position_id != position_id, PositionRow.inventory > 0).limit(1)).scalar_one_or_none()
        pending = session.execute(select(DecisionRow.action_id).where(
            DecisionRow.owner_id == verified_owner_id, DecisionRow.agent_id == agent_id,
            DecisionRow.wallet_id == wallet_id, DecisionRow.network_id == network_id,
            DecisionRow.operation.in_(_ACQUISITIONS), DecisionRow.status.in_(_UNRESOLVED),
            DecisionRow.binding["position_id"].astext != position_id).limit(1)).scalar_one_or_none()
        return ["POSITION_ALREADY_OPEN"] if held is not None or pending is not None else []


class CombinedControls:
    """Every connected submission control behind the one `StopReader` seam. Reasons are merged and sorted."""

    def __init__(self, *readers: object) -> None:
        self._readers = readers

    def denial_reasons(self, session: Session, verified_owner_id: uuid.UUID, *, agent_id: str, wallet_id: str,
                       network_id: str, position_id: str, operation: str) -> list[str]:
        reasons: set[str] = set()
        for reader in self._readers:
            reasons.update(reader.denial_reasons(  # type: ignore[attr-defined]
                session, verified_owner_id, agent_id=agent_id, wallet_id=wallet_id, network_id=network_id,
                position_id=position_id, operation=operation))
        return sorted(reasons)
