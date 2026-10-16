"""Separate trusted process: one fixed owner-bound Privy wallet lookup over a private Unix socket.

Run explicitly: `python -m lookup_server <socket_path>` with PRIVY_APP_ID and PRIVY_APP_SECRET in this process's
environment only. The API never imports this module and never sees the secret. The one operation fetches
`GET https://api.privy.io/v1/users/{did}` for the DID the API verified and matches the exact embedded Ethereum
wallet (`lookup_matching.match_claim`). There is no caller-chosen URL, method, header, payload, creation,
signer, policy or signing operation. HTTPS uses default certificate validation, no redirect, no retry, a
finite deadline and a capped response. Errors and logs carry codes only, never provider bodies or secrets.
"""

from __future__ import annotations

import base64
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
from edge_os_api.wallet_setup.lookup_matching import match_claim, valid_address, valid_did, valid_wallet_id

API_BASE = "https://api.privy.io/v1/users/"
DEADLINE_SECONDS = 10.0
MAX_RESPONSE = 256 * 1024
CONNECTION_TIMEOUT = 20.0
OPERATION = "lookup_embedded_wallet"

FetchUser = Callable[[str], object]


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
        request = urllib.request.Request(API_BASE + urllib.parse.quote(did, safe=""), method="GET",
                                         headers={"Authorization": self._auth, "privy-app-id": self._app_id})
        try:
            with self._opener.open(request, timeout=DEADLINE_SECONDS) as response:
                if response.status != 200:
                    return None
                body = response.read(MAX_RESPONSE + 1)
        except (urllib.error.URLError, OSError, ValueError):
            return None
        if len(body) > MAX_RESPONSE:
            return None
        try:
            return json.loads(body)
        except ValueError:
            return None


def answer(message: dict[str, Any], fetch_user: FetchUser) -> dict[str, Any]:
    """The only supported operation. Any other shape is refused with a code."""
    if set(message) != {"op", "did", "address", "wallet_id"} or message.get("op") != OPERATION:
        return {"status": "unknown", "reason": "UNSUPPORTED_REQUEST"}
    did, address, wallet_id = message["did"], message["address"], message["wallet_id"]
    if not (valid_did(did) and valid_address(address) and (wallet_id is None or valid_wallet_id(wallet_id))):
        return {"status": "unknown", "reason": "INVALID_REQUEST"}
    user = fetch_user(did)
    if user is None:
        return {"status": "unknown", "reason": "LOOKUP_UNAVAILABLE"}
    matched = match_claim(user, did, address, wallet_id)
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


def handle(conn: socket.socket, fetch_user: FetchUser) -> None:
    conn.settimeout(CONNECTION_TIMEOUT)
    try:
        if not same_user_peer(conn):
            return
        try:
            message = read_frame(conn)
        except (FrameError, OSError):
            conn.sendall(encode_frame({"status": "unknown", "reason": "MALFORMED_FRAME"}))
            return
        conn.sendall(encode_frame(answer(message, fetch_user)))
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
        if not stat.S_ISSOCK(target.lstat().st_mode):
            raise SystemExit("lookup: socket path exists and is not a socket")
        target.unlink()
    return target


def serve(path: str, fetch_user: FetchUser) -> None:
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
                handle(conn, fetch_user)
    finally:
        server.close()
        target.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: lookup_server.py <socket_path>", file=sys.stderr)
        return 2
    reader = PrivyUserReader(os.environ.get("PRIVY_APP_ID", ""), os.environ.get("PRIVY_APP_SECRET", ""))
    serve(argv[1], reader)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
