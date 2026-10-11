"""The NEW local P30 agent-submission denial check (prepared, not mounted).

A pending, unknown or confirmed removal denies a new agent submission through
this check. The check is UNWIRED in this stage: no accepted P22 admission or P23
execution caller consults it yet, and this package must not claim otherwise. The
missing connection is recorded for future qualified wiring.

A local stop is not confirmed provider removal. This check reads only the
persisted `revocation_local` derived states; it never reuses a stop token and
never treats a stop or an exhausted allowance counter as provider removal.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.orm import Session

# The prepared check is not mounted on any accepted submission caller yet.
P30_CHECK_WIRED = False


class RemovalReader(Protocol):
    """Read-only derived removal-state lookup for the local P30 denial check."""

    def submission_denial(
        self,
        session: Session,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str,
        wallet_id: str,
        network_id: str,
    ) -> list[str]: ...


def removal_denial(
    reader: RemovalReader | None,
    session: Session,
    verified_owner_id: uuid.UUID,
    *,
    agent_id: str,
    wallet_id: str,
    network_id: str,
) -> str | None:
    """The joined local P30 removal reason that denies this submission, or None.

    When no reader is supplied the result is None, exactly as an unmounted check
    behaves. The lookup reads the persisted states inside the caller's
    transaction and never consults a caller-supplied value.
    """
    if reader is None:
        return None
    reasons = reader.submission_denial(
        session, verified_owner_id, agent_id=agent_id, wallet_id=wallet_id, network_id=network_id)
    return ";".join(reasons) if reasons else None
