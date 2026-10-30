"""Provider selection at the wallet-creation boundary.

Only an authored local fixture and the local-only server-wallet adapter are available outside
production. Production refuses both and uses the fail-closed unavailable provider, so real mode
stays unavailable: no provider call, no key and no lookup. The fixture derives one deterministic
wallet per `(owner, agent)` so a restarted local process reconciles the same exact identity, and it
counts its own calls so a verifier can measure provider calls independently of the HTTP or UI
response. The server-wallet adapter asks the separate lookup process for one exact A2 release match.
"""

from __future__ import annotations

import hashlib
import os
import re
import socket
import threading
import time
import uuid
from typing import Any

from edge_os_api.wallet_setup.lookup_client import DEADLINE_SECONDS, OwnerBoundLookupProvider
from edge_os_api.wallet_setup.lookup_framing import FrameError, encode_frame, read_frame
from edge_os_api.wallet_setup.lookup_matching import valid_address, valid_wallet_id
from edge_os_api.wallet_setup.provider import CreationRequest, WalletEvidence, WalletProviderUnavailable

FIXTURE_MODE = "fixture"
UNAVAILABLE_MODE = "unavailable"
PRIVY_SERVER_MODE = "privy_server"
SERVER_WALLET_OPERATION = "bind_server_wallet"
SERVER_SOCKET_ENV = "EDGE_OS_PRIVY_SERVER_SOCKET"
_BINDING_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class UnavailableWalletProvider:
    """The fail-closed real-mode provider. It creates nothing and answers no lookup."""

    def create_wallet(self, request: CreationRequest) -> WalletEvidence | None:
        raise WalletProviderUnavailable()

    def lookup_wallet(self, wallet_id: str) -> WalletEvidence | None:
        raise WalletProviderUnavailable()


class PrivyServerWalletProvider:
    """Local-only binding of the builder's Privy server wallet to its exact A2 release.

    The API holds no app secret. It asks the separate trusted lookup process, over the same-user-only
    Unix socket, for the fixed `bind_server_wallet` operation. That process makes one read-only
    `GET /v1/wallets/{wallet_id}` and answers only when the id, chain, address, policy and signer
    fields exactly match the release it loaded. Any other reply is refused. The provider keeps the
    verified owner of a created wallet in memory so the service's second, independent lookup can
    compare the owner; a fresh process without that owner stays UNKNOWN (never WALLET_BOUND).
    """

    def __init__(self, socket_path: str, timeout: float = DEADLINE_SECONDS) -> None:
        if not _valid_socket_path(socket_path):
            raise ValueError("privy_server socket path must be a short absolute path without '..'")
        self.socket_path = socket_path
        self.timeout = timeout
        self._owners: dict[str, uuid.UUID] = {}
        self._owners_lock = threading.Lock()

    def create_wallet(self, request: CreationRequest) -> WalletEvidence | None:
        reply = self._ask({"op": SERVER_WALLET_OPERATION})
        evidence = self._evidence(reply, request.owner_id, expected_wallet_id=None)
        if evidence is None:
            raise WalletProviderUnavailable()
        with self._owners_lock:
            known = self._owners.get(evidence.wallet_id)
            if known is not None and known != request.owner_id:
                raise WalletProviderUnavailable()
            self._owners[evidence.wallet_id] = request.owner_id
        return evidence

    def lookup_wallet(self, wallet_id: str) -> WalletEvidence | None:
        with self._owners_lock:
            owner_id = self._owners.get(wallet_id) if valid_wallet_id(wallet_id) else None
        if owner_id is None:
            return None
        try:
            reply = self._ask({"op": SERVER_WALLET_OPERATION})
        except Exception:  # noqa: BLE001 - any lookup failure stays UNKNOWN
            return None
        return self._evidence(reply, owner_id, expected_wallet_id=wallet_id)

    def _evidence(self, reply: object, owner_id: uuid.UUID,
                  expected_wallet_id: str | None) -> WalletEvidence | None:
        if not isinstance(reply, dict) or set(reply) != {
                "status", "wallet_id", "address", "chain_type", "release_binding_sha256"}:
            return None
        wallet_id, address = reply.get("wallet_id"), reply.get("address")
        digest = reply.get("release_binding_sha256")
        if not (reply.get("status") == "matched" and valid_wallet_id(wallet_id) and valid_address(address)
                and reply.get("chain_type") == "ethereum"
                and isinstance(digest, str) and _BINDING_SHA256.fullmatch(digest) is not None
                and (expected_wallet_id is None or wallet_id == expected_wallet_id)):
            return None
        assert isinstance(wallet_id, str) and isinstance(address, str) and isinstance(digest, str)
        return WalletEvidence(wallet_id=wallet_id, owner_id=owner_id, chain_type="ethereum", address=address,
                              release_binding_sha256=digest)

    def _ask(self, request: dict[str, Any]) -> dict[str, Any]:
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
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    sock.settimeout(remaining)
    return True


def _valid_socket_path(value: object) -> bool:
    return (isinstance(value, str) and value.startswith("/") and ".." not in value.split("/")
            and len(value) <= 100 and "\x00" not in value)


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


def build_wallet_provider(mode: str, *, socket_path: str | None = None) -> (
        UnavailableWalletProvider | FixtureWalletProvider | PrivyServerWalletProvider):
    """Build the provider for one configuration mode. Any other mode stays fail-closed.

    The server mode is local-only. It needs the private lookup socket in `EDGE_OS_PRIVY_SERVER_SOCKET`;
    a missing or invalid path keeps the fail-closed unavailable provider. The API never holds the
    Privy app secret.
    """
    if mode == FIXTURE_MODE:
        return FixtureWalletProvider()
    if mode == PRIVY_SERVER_MODE:
        path = socket_path if socket_path is not None else os.environ.get(SERVER_SOCKET_ENV)
        if _valid_socket_path(path):
            assert isinstance(path, str)
            return PrivyServerWalletProvider(path)
    return UnavailableWalletProvider()


def provider_info(provider: object) -> dict[str, object]:
    """The active provider mode and, for the local fixture, its independent call counters."""
    if isinstance(provider, OwnerBoundLookupProvider):  # browser creation, owner-bound lookup; no counters to report
        return {"provider": "privy_lookup", "create_calls": None, "lookup_calls": None}
    if isinstance(provider, FixtureWalletProvider):
        return {"provider": FIXTURE_MODE, "create_calls": provider.create_calls,
                "lookup_calls": provider.lookup_calls}
    if isinstance(provider, PrivyServerWalletProvider):
        return {"provider": PRIVY_SERVER_MODE, "create_calls": None, "lookup_calls": None}
    return {"provider": UNAVAILABLE_MODE, "create_calls": None, "lookup_calls": None}
