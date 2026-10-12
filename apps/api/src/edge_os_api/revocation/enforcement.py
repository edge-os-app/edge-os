"""The P30 agent-submission denial check and its connection to admission and submission.

A requested, pending, unknown or confirmed removal denies a new agent submission. The connected
application wires this check through `SubmissionControls`: the accepted P22 admission
(`admit_and_reserve`, `acquire_submission`) and P23 revalidation already consult one `StopReader`
inside the caller's transaction under the shared per-wallet advisory lock, and `SubmissionControls`
answers that read with the durable stop reasons plus the removal reasons. `request_removal` takes the
same per-wallet lock, so a committed removal and the admission/submission-ownership transition are
serialized: either the removal commits first and the transition is denied, or ownership commits
first and the removal never undoes an in-flight original action (it stays recoverable).

A local stop is not confirmed provider removal. The removal check reads only the persisted
`revocation_local` derived states; it never reuses a stop token and never treats a stop or an exhausted
allowance counter as provider removal.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.orm import Session

# The check is mounted on the admission and submission callers by the connected composition.
P30_CHECK_WIRED = True


class RemovalReader(Protocol):
    """Read-only derived removal-state lookup for the P30 denial check."""

    def submission_denial(
        self,
        session: Session,
        verified_owner_id: uuid.UUID,
        *,
        agent_id: str,
        wallet_id: str,
        network_id: str,
    ) -> list[str]: ...


class DurableStopReader(Protocol):
    def denial_reasons(self, session: Session, verified_owner_id: uuid.UUID, *, agent_id: str, wallet_id: str,
                       network_id: str, position_id: str, operation: str) -> list[str]: ...


def removal_denial(
    reader: RemovalReader | None,
    session: Session,
    verified_owner_id: uuid.UUID,
    *,
    agent_id: str,
    wallet_id: str,
    network_id: str,
) -> str | None:
    """The joined P30 removal reason that denies this submission, or None.

    When no reader is supplied the result is None. The lookup reads the persisted states inside the
    caller's transaction and never consults a caller-supplied value.
    """
    if reader is None:
        return None
    reasons = reader.submission_denial(
        session, verified_owner_id, agent_id=agent_id, wallet_id=wallet_id, network_id=network_id)
    return ";".join(reasons) if reasons else None


class SubmissionControls:
    """The one `StopReader` the connected admission and submission paths consult.

    It returns the durable scoped-stop reasons for the operation plus every removal reason for the
    wallet. Removal denies every operation, including an exit: removing the agent's signer withdraws the
    agent's authority to submit, while owner access, pending recovery and residual holdings stay.
    """

    def __init__(self, stops: DurableStopReader, removals: RemovalReader) -> None:
        self._stops = stops
        self._removals = removals

    def denial_reasons(self, session: Session, verified_owner_id: uuid.UUID, *, agent_id: str, wallet_id: str,
                       network_id: str, position_id: str, operation: str) -> list[str]:
        reasons = self._stops.denial_reasons(session, verified_owner_id, agent_id=agent_id, wallet_id=wallet_id,
                                             network_id=network_id, position_id=position_id, operation=operation)
        removal = self._removals.submission_denial(session, verified_owner_id, agent_id=agent_id,
                                                   wallet_id=wallet_id, network_id=network_id)
        return sorted(set(reasons) | set(removal))
