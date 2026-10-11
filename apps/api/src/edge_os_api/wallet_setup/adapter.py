"""Provider selection at the wallet-creation boundary.

Only an authored local fixture is available outside production. Production refuses the fixture and
uses the fail-closed unavailable provider, so real mode stays unavailable: no provider call, no
key and no lookup. The fixture derives one deterministic wallet per `(owner, agent)` so a restarted
local process reconciles the same exact identity.
"""

from __future__ import annotations

import hashlib
import uuid

from edge_os_api.wallet_setup.provider import CreationRequest, WalletEvidence, WalletProviderUnavailable

FIXTURE_MODE = "fixture"
UNAVAILABLE_MODE = "unavailable"


class UnavailableWalletProvider:
    """The fail-closed real-mode provider. It creates nothing and answers no lookup."""

    def create_wallet(self, request: CreationRequest) -> WalletEvidence | None:
        raise WalletProviderUnavailable()

    def lookup_wallet(self, wallet_id: str) -> WalletEvidence | None:
        raise WalletProviderUnavailable()


class FixtureWalletProvider:
    """AUTHORED LOCAL FIXTURE. Its wallets are not provider, wallet or financial evidence.

    Enabled only in local and test configuration. An agent id that ends with the reserved
    `fixture-lost-response` marker makes creation return no result, so the local verify path can
    exercise the uncertain/lost-response state without a real provider.
    """

    LOSE_RESPONSE_SUFFIX = "fixture-lost-response"

    def create_wallet(self, request: CreationRequest) -> WalletEvidence | None:
        if request.agent_id.endswith(self.LOSE_RESPONSE_SUFFIX):
            return None
        return self._evidence(self._wallet_id(request.owner_id, request.agent_id))

    def lookup_wallet(self, wallet_id: str) -> WalletEvidence | None:
        return None if self._owner_of(wallet_id) is None else self._evidence(wallet_id)

    def _wallet_id(self, owner_id: uuid.UUID, agent_id: str) -> str:
        return f"fixture:{owner_id}:{agent_id}"

    def _owner_of(self, wallet_id: str) -> uuid.UUID | None:
        parts = wallet_id.split(":")
        if len(parts) != 3 or parts[0] != "fixture":
            return None
        try:
            return uuid.UUID(parts[1])
        except (ValueError, TypeError):
            return None

    def _evidence(self, wallet_id: str) -> WalletEvidence:
        owner_id = self._owner_of(wallet_id)
        if owner_id is None:
            raise WalletProviderUnavailable()
        digest = hashlib.sha256(wallet_id.encode("utf-8")).hexdigest()
        return WalletEvidence(wallet_id=wallet_id, owner_id=owner_id, chain_type="ethereum",
                              address="0x" + digest[:40])


def build_wallet_provider(mode: str) -> UnavailableWalletProvider | FixtureWalletProvider:
    """Build the provider for one configuration mode. Any other mode stays fail-closed."""
    return FixtureWalletProvider() if mode == FIXTURE_MODE else UnavailableWalletProvider()
