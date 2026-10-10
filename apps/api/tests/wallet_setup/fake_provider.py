"""AUTHORED FAKE wallet provider. Its results are not Privy or any provider evidence.

It exists only to exercise the local setup service and its recovery controls. It stores wallets
in memory, so a fresh process holds no wallets it did not create. Crash hooks let a test stop a
process at a named boundary without changing the production service interface.
"""

from __future__ import annotations

from typing import Any, Callable

from edge_os_api.wallet_setup.provider import CreationRequest, WalletEvidence, WalletProviderUnavailable


class AuthoredFakeWalletProvider:
    """An authored fake. Never treat a result here as provider, wallet or financial evidence."""

    def __init__(self, *, wallets: dict[str, WalletEvidence] | None = None, lose_response: bool = False,
                 unavailable: bool = False, create_result: WalletEvidence | None = None,
                 on_create: Callable[[CreationRequest], None] | None = None,
                 on_lookup: Callable[[str], None] | None = None) -> None:
        self.wallets: dict[str, WalletEvidence] = dict(wallets or {})
        self.created: list[CreationRequest] = []
        self.lookups: list[str] = []
        self.lose_response = lose_response
        self.unavailable = unavailable
        self.create_result = create_result
        self.on_create = on_create
        self.on_lookup = on_lookup
        self._counter = len(self.wallets)

    def create_wallet(self, request: CreationRequest) -> WalletEvidence | None:
        if self.on_create is not None:
            self.on_create(request)
        if self.unavailable:
            raise WalletProviderUnavailable()
        self.created.append(request)
        if self.lose_response:
            return None
        if self.create_result is not None:
            self.wallets[self.create_result.wallet_id] = self.create_result
            return self.create_result
        self._counter += 1
        wallet_id = f"wallet-{self._counter:04d}"
        evidence = WalletEvidence(wallet_id=wallet_id, owner_id=request.owner_id, chain_type="ethereum",
                                  address=f"0x{self._counter:040x}")
        self.wallets[wallet_id] = evidence
        return evidence

    def lookup_wallet(self, wallet_id: str) -> WalletEvidence | None:
        if self.on_lookup is not None:
            self.on_lookup(wallet_id)
        if self.unavailable:
            raise WalletProviderUnavailable()
        self.lookups.append(wallet_id)
        return self.wallets.get(wallet_id)


def crash_evidence(owner_id: Any, wallet_id: str = "wallet-retained") -> WalletEvidence:
    """A deterministic retained wallet used to seed a restarted process."""
    return WalletEvidence(wallet_id=wallet_id, owner_id=owner_id, chain_type="ethereum", address=f"0x{1:040x}")
