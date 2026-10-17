"""Separate trusted process: one fixed owner-bound Privy wallet lookup over a private Unix socket.

Run explicitly: `python -m lookup_server <socket_path>` with PRIVY_APP_ID and PRIVY_APP_SECRET in this process's
environment only. The API never imports this module and never sees the secret. The one operation fetches
`GET https://api.privy.io/v1/users/{did}` for the DID the API verified and matches the exact embedded Ethereum
wallet (`lookup_matching.match_claim`). Only when that linked wallet has no ID does it also make the fixed read-only
`POST https://api.privy.io/v1/wallets/address` with exactly `{"address": ...}` to resolve the ID. There is no
caller-chosen URL, method, header, payload, creation, signer, policy or signing operation. HTTPS uses default
certificate validation, no redirect, no retry, a per-operation timeout and a capped response. One failed lookup
answers a code and the process keeps serving. Errors and logs carry codes only, never provider bodies or secrets.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import socket
import ssl
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from edge_os_api.wallet_setup.lookup_framing import FrameError, encode_frame, read_frame
from edge_os_api.wallet_setup.lookup_matching import (linked_wallet, match_claim, valid_address, valid_did,
                                                      valid_wallet_id)

API_BASE = "https://api.privy.io/v1/users/"
WALLET_BY_ADDRESS = "https://api.privy.io/v1/wallets/address"
DEADLINE_SECONDS = 10.0
MAX_RESPONSE = 256 * 1024
CONNECTION_TIMEOUT = 20.0
OPERATION = "lookup_embedded_wallet"

FetchUser = Callable[[str], object]
FetchWallet = Callable[[str], object]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class PrivyUserReader:
    """Holds the app credential privately. Its repr never shows it."""

    def __init__(self, app_id: str, app_secret: str) -> None:
        if not app_id or not app_secret:
            raise SystemExit("lookup: credential not configured")
        self._app_id = app_id
        self._auth = "Basic " + base64.b64encode(f"{app_id}:{app_secret}".encode()).decode("ascii")
        self._opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def __repr__(self) -> str:
        return "PrivyUserReader(<redacted>)"

    def __call__(self, did: str) -> object:
        if not valid_did(did):
            return None
        return self._fetch(urllib.request.Request(API_BASE + urllib.parse.quote(did, safe=""), method="GET",
                                                  headers={"Authorization": self._auth,
                                                           "privy-app-id": self._app_id}))

    def wallet_by_address(self, address: str) -> object:
        """Read-only fixed lookup: POST {address} to the wallets-by-address endpoint. No create or policy call."""
        if not valid_address(address):
            return None
        body = json.dumps({"address": address}).encode("ascii")
        return self._fetch(urllib.request.Request(WALLET_BY_ADDRESS, data=body, method="POST", headers={
            "Authorization": self._auth, "privy-app-id": self._app_id, "Content-Type": "application/json"}))

    def _fetch(self, request: urllib.request.Request) -> object:
        try:
            with self._opener.open(request, timeout=DEADLINE_SECONDS) as response:
                if response.status != 200:
                    return None
                body = response.read(MAX_RESPONSE + 1)
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
            return None
        if len(body) > MAX_RESPONSE:
            return None
        try:
            return json.loads(body)
        except ValueError:
            return None


def answer(message: dict[str, Any], fetch_user: FetchUser, fetch_wallet: FetchWallet | None = None) -> dict[str, Any]:
    """The only supported operation. Any other shape is refused with a code."""
    if set(message) != {"op", "did", "address", "wallet_id"} or message.get("op") != OPERATION:
        return {"status": "unknown", "reason": "UNSUPPORTED_REQUEST"}
    did, address, wallet_id = message["did"], message["address"], message["wallet_id"]
    if not (valid_did(did) and valid_address(address) and (wallet_id is None or valid_wallet_id(wallet_id))):
        return {"status": "unknown", "reason": "INVALID_REQUEST"}
    user = fetch_user(did)
    if user is None:
        return {"status": "unknown", "reason": "LOOKUP_UNAVAILABLE"}
    account = linked_wallet(user, did, address)
    if account is None:
        return {"status": "unknown", "reason": "NO_EXACT_MATCH"}
    record = None
    if account.get("id") is None:  # the user's own link matched; only now resolve its ID by exact address
        record = fetch_wallet(address) if fetch_wallet is not None else None
        if record is None:
            return {"status": "unknown", "reason": "LOOKUP_UNAVAILABLE"}
    matched = match_claim(user, did, address, wallet_id, wallet_record=record)
    if matched is None:
        return {"status": "unknown", "reason": "NO_EXACT_MATCH"}
    return {"status": "matched", "wallet_id": matched.wallet_id, "address": matched.address,
            "chain_type": matched.chain_type}


def same_user_peer(conn: socket.socket) -> bool:
    """Accept only a peer running as this process's own user (macOS LOCAL_PEERCRED or Linux SO_PEERCRED)."""
    try:
        if hasattr(socket, "SO_PEERCRED"):
            import struct
            _pid, uid, _gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            return uid == os.getuid()
        if hasattr(socket, "LOCAL_PEERCRED"):
            import struct
            raw = conn.getsockopt(0, socket.LOCAL_PEERCRED, 76)
            _version, uid = struct.unpack("Ii", raw[:8])
            return uid == os.getuid()
    except OSError:
        return False
    return False


def handle(conn: socket.socket, fetch_user: FetchUser, fetch_wallet: FetchWallet | None = None) -> None:
    conn.settimeout(CONNECTION_TIMEOUT)
    try:
        if not same_user_peer(conn):
            return
        try:
            message = read_frame(conn)
        except (FrameError, OSError):
            conn.sendall(encode_frame({"status": "unknown", "reason": "MALFORMED_FRAME"}))
            return
        try:
            reply = answer(message, fetch_user, fetch_wallet)
        except Exception:  # noqa: BLE001 - one failed lookup must not stop the process; the caller stays UNKNOWN
            reply = {"status": "unknown", "reason": "LOOKUP_FAILED"}
        conn.sendall(encode_frame(reply))
    except OSError:
        return


def prepare_socket_path(path: str) -> Path:
    target = Path(path)
    if not target.is_absolute() or ".." in target.parts or len(path) > 100:
        raise SystemExit("lookup: socket path must be a short absolute path")
    parent = target.parent
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise SystemExit("lookup: socket directory must be owned by this user with mode 0700")
    if target.exists() or target.is_symlink():
        # No proved own claim on an existing target: it may be another live process. Refuse, never unlink.
        raise SystemExit("lookup: socket path already exists; remove it deliberately before startup")
    return target


def serve(path: str, fetch_user: FetchUser, fetch_wallet: FetchWallet | None = None) -> None:
    target = prepare_socket_path(path)
    previous = os.umask(0o177)
    try:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(target))
    finally:
        os.umask(previous)
    os.chmod(target, 0o600)
    server.listen(8)
    try:
        while True:
            conn, _ = server.accept()
            with conn:
                handle(conn, fetch_user, fetch_wallet)
    finally:
        server.close()
        target.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: lookup_server.py <socket_path>", file=sys.stderr)
        return 2
    reader = PrivyUserReader(os.environ.get("PRIVY_APP_ID", ""), os.environ.get("PRIVY_APP_SECRET", ""))
    serve(argv[1], reader, reader.wallet_by_address)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
