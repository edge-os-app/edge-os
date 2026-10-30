"""Owner-bound wallet lookup over the private Unix socket.

The API holds no Privy app secret. It asks the separate trusted lookup process one fixed question: does
the verified owner's DID user record hold this exact embedded Ethereum wallet? The provider is built per
request from the verified `Principal`, never from a request body. It never creates a wallet: the browser
creates, and `create_wallet` raises `WalletProviderUnavailable`. Any socket, frame or reply failure is
`WalletProviderUnavailable`, which the service keeps as `UNKNOWN`. One absolute deadline bounds the
connect, the send and the reply read together, so a paced peer cannot keep the call open past the budget.
"""

from __future__ import annotations

import socket
import time
import uuid
from dataclasses import dataclass, field

from edge_os_api.wallet_setup.lookup_framing import FrameError, encode_frame, read_frame
from edge_os_api.wallet_setup.lookup_matching import valid_address, valid_did, valid_wallet_id
from edge_os_api.wallet_setup.provider import CreationRequest, WalletEvidence, WalletProviderUnavailable

LOOKUP_OPERATION = "lookup_embedded_wallet"
# Total budget for one lookup exchange. Connect, send and the frame read share this single deadline
# (re-armed before each socket operation and each receive), so a paced peer cannot hold the call past
# it. Longer than the lookup process's two fixed provider reads (2 x 10 s), so a slow but valid lookup
# is not cut off; a slower one still ends as UNKNOWN.
DEADLINE_SECONDS = 25.0


@dataclass
class OwnerBoundLookupProvider:
    """Answers `lookup_wallet` for one verified owner and one retained browser address claim."""

    socket_path: str
    owner_id: uuid.UUID
    privy_did: str
    timeout: float = DEADLINE_SECONDS
    claimed_address: str | None = field(default=None, repr=False)

    def create_wallet(self, request: CreationRequest) -> WalletEvidence | None:
        raise WalletProviderUnavailable()

    def with_claim(self, address: str | None) -> "OwnerBoundLookupProvider":
        return OwnerBoundLookupProvider(self.socket_path, self.owner_id, self.privy_did, self.timeout, address)

    def lookup_wallet(self, wallet_id: str) -> WalletEvidence | None:
        return self.lookup_claim(self.claimed_address, wallet_id)

    def lookup_claim(self, address: str | None, wallet_id: str | None) -> WalletEvidence | None:
        """One owner-bound lookup for an exact address claim, with or without a returned wallet ID."""
        if not (valid_did(self.privy_did) and valid_address(address)
                and (wallet_id is None or valid_wallet_id(wallet_id))):
            return None
        reply = self._ask({"op": LOOKUP_OPERATION, "did": self.privy_did, "address": address,
                           "wallet_id": wallet_id})
        if reply.get("status") != "matched":
            return None
        found_id, found_address = reply.get("wallet_id"), reply.get("address")
        if not (valid_wallet_id(found_id) and (wallet_id is None or found_id == wallet_id)
                and isinstance(found_address, str) and address is not None
                and found_address.lower() == address.lower() and reply.get("chain_type") == "ethereum"):
            return None
        return WalletEvidence(wallet_id=found_id, owner_id=self.owner_id, chain_type="ethereum",
                              address=found_address)

    def _ask(self, request: dict[str, object]) -> dict[str, object]:
        deadline = time.monotonic() + self.timeout
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                if not _arm(sock, deadline):
                    raise WalletProviderUnavailable()
                sock.connect(self.socket_path)
                if not _arm(sock, deadline):
                    raise WalletProviderUnavailable()
                sock.sendall(encode_frame(request))
                return read_frame(sock, deadline)
        except (OSError, FrameError):
            raise WalletProviderUnavailable() from None


def _arm(sock: socket.socket, deadline: float) -> bool:
    """Re-arm the socket timeout to the remaining budget. False once the deadline has passed."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    sock.settimeout(remaining)
    return True
