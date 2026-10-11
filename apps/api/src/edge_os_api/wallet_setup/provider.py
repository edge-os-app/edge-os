"""The wallet-creation boundary port.

The selected React creation route has no REST `external_id` and no provider idempotency
guarantee. A lost response therefore leaves setup `UNKNOWN` unless an exact retained server
wallet ID can be reconciled. This module defines the port only. Every concrete implementation
used in this local task is an authored fake (see `tests/wallet_setup/fake_provider.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CreationRequest:
    """Server-derived creation input. It carries no client-supplied owner assertion."""

    owner_id: uuid.UUID
    agent_id: str
    network_id: int
    strategy_id: str
    strategy_revision_id: uuid.UUID
    content_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class WalletEvidence:
    """Provider-side wallet identity returned by create or an independent lookup.

    `network_id` is the application binding. An Ethereum provider wallet is not inherently
    bound to one chain ID, so the provider evidence carries a chain type and address only.
    """

    wallet_id: str
    owner_id: uuid.UUID
    chain_type: str
    address: str


class WalletProviderUnavailable(RuntimeError):
    """The provider lookup or creation path cannot answer. The caller must stay `UNKNOWN`."""


@runtime_checkable
class WalletCreationPort(Protocol):
    def create_wallet(self, request: CreationRequest) -> WalletEvidence | None:
        """Create one owner-linked wallet. Return `None` when the response is lost or malformed."""

    def lookup_wallet(self, wallet_id: str) -> WalletEvidence | None:
        """Return the provider record for one exact wallet ID, or `None` when it is not an exact match."""
