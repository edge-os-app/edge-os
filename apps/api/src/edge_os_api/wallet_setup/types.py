"""Wallet-setup identities and setup states.

Local preparation only. This package is not production wiring. It creates no wallet, signer,
funding, mandate activation, position or trading action.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from dataclasses import dataclass


class SetupState(enum.StrEnum):
    """The five accepted P15 wallet-setup states. No other state is added here."""

    REQUESTED = "REQUESTED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class CancellationIntent(enum.StrEnum):
    """Cancellation is separate from setup state. `CANCELLED` is not an accepted contract state."""

    NONE = "NONE"
    REQUESTED_BEFORE_DISPATCH = "REQUESTED_BEFORE_DISPATCH"
    REQUESTED_AFTER_DISPATCH = "REQUESTED_AFTER_DISPATCH"


class NetworkId(enum.IntEnum):
    """The two accepted Monad networks. Approval for one does not approve the other."""

    MONAD_MAINNET = 143
    MONAD_TESTNET = 10143


class SetupEventType(enum.StrEnum):
    """Append-only setup evidence. Denials are recorded in a separate table."""

    PREPARED = "PREPARED"
    DISPATCH_INTENT = "DISPATCH_INTENT"
    RESULT_RETURNED = "RESULT_RETURNED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"
    WALLET_BOUND = "WALLET_BOUND"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    RECONCILED = "RECONCILED"


class SetupReason(enum.StrEnum):
    """Stable reason codes shown for pending, unknown, failure and recovery states."""

    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    RESPONSE_LOST = "RESPONSE_LOST"
    MALFORMED_RESULT = "MALFORMED_RESULT"
    RECONCILE_NO_EXACT_ID = "RECONCILE_NO_EXACT_ID"
    RECONCILE_NO_MATCH = "RECONCILE_NO_MATCH"
    RECONCILE_WRONG_IDENTITY = "RECONCILE_WRONG_IDENTITY"
    CONFLICTING_WALLET = "CONFLICTING_WALLET"


EVM_CHAIN_TYPE = "ethereum"
ACCEPTED_NETWORK_IDS = frozenset(member.value for member in NetworkId)


@dataclass(frozen=True)
class SetupIdentity:
    """The immutable binding a setup persists before any creation-capable call."""

    owner_id: uuid.UUID
    agent_id: str
    network_id: int
    strategy_id: str
    strategy_revision_id: uuid.UUID
    content_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class SetupRecord:
    """The current owner-scoped setup row, including its recovery reason."""

    setup_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    network_id: int
    strategy_id: str
    strategy_revision_id: uuid.UUID
    content_sha256: str
    manifest_sha256: str
    state: SetupState
    cancellation_intent: CancellationIntent
    creation_dispatched: bool
    request_key: str
    wallet_id: str | None
    reason: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
