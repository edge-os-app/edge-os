"""Local P30 revocation preparation package.

Local, owner-authored removal records only. The package writes only its own
`revocation_local` tables. It performs no provider call, no signing, no wallet or
policy change and no broadcast. A local record is not confirmed provider removal,
and the local P30 denial check is prepared but not mounted on any accepted
submission caller.
"""

from __future__ import annotations

from edge_os_api.revocation.enforcement import P30_CHECK_WIRED, RemovalReader, removal_denial
from edge_os_api.revocation.records import RevocationBase
from edge_os_api.revocation.removal_service import (
    RemovalService,
    SavedWalletBindingReader,
    WalletBinding,
    WalletBindingReader,
)
from edge_os_api.revocation.types import (
    DENIAL_REASON,
    DENYING_STATES,
    OBSERVATION_STATES,
    REMOVAL_STATES,
    ReconcileOutcome,
    RemovalError,
    RemovalObservation,
    RemovalRequest,
    RemovalView,
)

__all__ = [
    "DENIAL_REASON",
    "DENYING_STATES",
    "OBSERVATION_STATES",
    "REMOVAL_STATES",
    "P30_CHECK_WIRED",
    "ReconcileOutcome",
    "RemovalError",
    "RemovalObservation",
    "RemovalReader",
    "RemovalRequest",
    "RemovalService",
    "RemovalView",
    "RevocationBase",
    "SavedWalletBindingReader",
    "WalletBinding",
    "WalletBindingReader",
    "removal_denial",
]
