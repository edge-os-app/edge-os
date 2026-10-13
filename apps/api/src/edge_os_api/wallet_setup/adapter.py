"""Provider selection at the wallet-creation boundary.

Only an authored local fixture is available outside production. Production refuses the fixture and
uses the fail-closed unavailable provider, so real mode stays unavailable: no provider call, no
key and no lookup. The fixture derives one deterministic wallet per `(owner, agent)` so a restarted
local process reconciles the same exact identity, and it counts its own calls so a verifier can
measure provider calls independently of the HTTP or UI response.
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
    `fixture-lost-response` marker creates its wallet and then loses the response, so the local
    verify path exercises a committed response loss. `create_calls` and `lookup_calls` count the
    provider calls the service actually made.
    """

    LOSE_RESPONSE_SUFFIX = "fixture-lost-response"
    # Reserved marker (#58 ORIGINAL-LOCAL amendment A1): an agent id containing it gets the AUTHORED public
    # test-signer address that the frozen original-transaction fixtures were signed for. The address is the
    # eth-account documentation example key's sender; this process never holds that key.
    ORIGINAL_SIGNER_MARKER = "fx-original"
    AUTHORED_TEST_SIGNER_ADDRESS = "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23"

    def __init__(self) -> None:
        self.create_calls = 0
        self.lookup_calls = 0

    def create_wallet(self, request: CreationRequest) -> WalletEvidence | None:
        self.create_calls += 1
        evidence = self._evidence(self._wallet_id(request.owner_id, request.agent_id))
        if request.agent_id.endswith(self.LOSE_RESPONSE_SUFFIX):
            return None  # the wallet exists provider-side; only the response is lost
        return evidence

    def lookup_wallet(self, wallet_id: str) -> WalletEvidence | None:
        self.lookup_calls += 1
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
        if self.ORIGINAL_SIGNER_MARKER in wallet_id.split(":", 2)[2]:
            return WalletEvidence(wallet_id=wallet_id, owner_id=owner_id, chain_type="ethereum",
                                  address=self.AUTHORED_TEST_SIGNER_ADDRESS)
        digest = hashlib.sha256(wallet_id.encode("utf-8")).hexdigest()
        return WalletEvidence(wallet_id=wallet_id, owner_id=owner_id, chain_type="ethereum",
                              address="0x" + digest[:40])


def build_wallet_provider(mode: str) -> UnavailableWalletProvider | FixtureWalletProvider:
    """Build the provider for one configuration mode. Any other mode stays fail-closed."""
    return FixtureWalletProvider() if mode == FIXTURE_MODE else UnavailableWalletProvider()


def provider_info(provider: object) -> dict[str, object]:
    """The active provider mode and, for the local fixture, its independent call counters."""
    if isinstance(provider, FixtureWalletProvider):
        return {"provider": FIXTURE_MODE, "create_calls": provider.create_calls,
                "lookup_calls": provider.lookup_calls}
    return {"provider": UNAVAILABLE_MODE, "create_calls": None, "lookup_calls": None}
