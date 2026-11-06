"""Separate trusted process: one fixed owner-bound Privy wallet lookup over a private Unix socket.

Run explicitly: `python -m lookup_server <socket_path>` with PRIVY_APP_ID and PRIVY_APP_SECRET in this process's
environment only. The API never imports this module and never sees the secret. The one operation fetches
`GET https://api.privy.io/v1/users/{did}` for the DID the API verified and matches the exact embedded Ethereum
wallet (`lookup_matching.match_claim`). Only when that linked wallet has no ID does it also make the fixed read-only
`POST https://api.privy.io/v1/wallets/address` with exactly `{"address": ...}` to resolve the ID. There is no
caller-chosen URL, method, header, payload, creation, signer, policy or signing operation. HTTPS uses default
certificate validation, no redirect, no retry, one absolute deadline for each fixed read and a capped
response. Each read's connect, request, header and body phases share that single deadline: a per-call
watchdog shuts the socket down at the deadline and the body is streamed in capped chunks with a remaining
check between them, so a paced provider reply cannot exceed the budget. The DNS lookup and the initial
connect are waited on under that same budget, so a stalled resolver cannot extend the read either. One
failed lookup answers a code and the process keeps serving. Errors and logs carry codes only, never
provider bodies or secrets.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import stat
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edge_os_api.wallet_setup.lookup_framing import FrameError, encode_frame, read_frame
from edge_os_api.wallet_setup.lookup_matching import (linked_wallet, match_claim, valid_address, valid_did,
                                                      valid_wallet_id)

API_BASE = "https://api.privy.io/v1/users/"
WALLET_BY_ADDRESS = "https://api.privy.io/v1/wallets/address"
WALLET_BY_ID = "https://api.privy.io/v1/wallets/"
_PRIVY_HOST = urllib.parse.urlsplit(API_BASE).hostname or "api.privy.io"
_USERS_PATH = urllib.parse.urlsplit(API_BASE).path
_WALLETS_BY_ADDRESS_PATH = urllib.parse.urlsplit(WALLET_BY_ADDRESS).path
_WALLETS_BY_ID_PATH = urllib.parse.urlsplit(WALLET_BY_ID).path
DEADLINE_SECONDS = 10.0
MAX_RESPONSE = 256 * 1024
_CHUNK_BYTES = 65_536
CONNECTION_TIMEOUT = 20.0
OPERATION = "lookup_embedded_wallet"
SERVER_WALLET_OPERATION = "bind_server_wallet"
AUTHORED_SCHEMA = "edge-os.inapp-trade-authoring/1"
_MONAD_MAINNET = 143
_BOUND_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_RECORD_REQUIRED = frozenset({"id", "address", "chain_type", "policy_ids", "owner_id", "additional_signers"})
_RECORD_OPTIONAL = frozenset({"created_at", "entity", "external_id", "display_name", "exported_at",
                              "imported_at"})

FetchUser = Callable[[str], object]
FetchWallet = Callable[[str], object]

# The lookup process is serial: one outstanding connector is enough. Further reads answer UNKNOWN rather
# than start another thread while an unresolved connect holds the budget.
_CONNECTOR_LOCK = threading.Lock()
_CONNECTOR_BUSY = False


def _default_connect(timeout: float) -> http.client.HTTPSConnection:
    """One HTTPS connection to the fixed provider host with default certificate validation, no redirect.

    DNS and the TCP/TLS connect run under a bounded wait, so a stalled resolver cannot push this fixed read
    past its total deadline. At most ONE connector may be outstanding: `socket.create_connection` resolves
    the host before it can honour a socket timeout, so an abandoned wait is the only way to stop reading,
    and a second blocked read must not add another thread. A connector that finishes after its caller has
    given up is closed here, never handed to a caller that is gone.
    """
    global _CONNECTOR_BUSY
    connection = http.client.HTTPSConnection(_PRIVY_HOST, timeout=timeout, context=ssl.create_default_context())
    with _CONNECTOR_LOCK:
        if _CONNECTOR_BUSY:
            raise TimeoutError("provider connect already outstanding")
        _CONNECTOR_BUSY = True
    done = threading.Event()
    failure: list[BaseException] = []
    state = "connecting"  # connecting -> ready | failed | abandoned | closed, decided under the lock
    stale = False

    def _connect() -> None:
        nonlocal state
        global _CONNECTOR_BUSY
        try:
            connection.connect()
        except BaseException as exc:  # noqa: BLE001 - reported to the reading thread
            failure.append(exc)
        with _CONNECTOR_LOCK:
            close_now = state == "abandoned" or bool(failure)
            if state == "abandoned":
                state = "closed"
            else:
                state = "failed" if failure else "ready"
        # A failed connect may already own a socket, and the caller never receives the connection, so close it
        # here while this thread still owns it - before the slot is released. Exactly one close, and the
        # assigned socket is closed even if connection.close() itself raises.
        if close_now:
            sock = getattr(connection, "sock", None)
            try:
                connection.close()
            except OSError:
                pass
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        with _CONNECTOR_LOCK:
            _CONNECTOR_BUSY = False
        done.set()

    try:
        worker = threading.Thread(target=_connect, daemon=True)
        worker.start()
    except BaseException:  # nothing exists yet: never leave the single-connector slot held
        with _CONNECTOR_LOCK:
            _CONNECTOR_BUSY = False
        raise
    if not done.wait(timeout):
        with _CONNECTOR_LOCK:
            if state == "connecting":
                state = "abandoned"  # the connector closes itself when it finally finishes
            elif state == "ready":
                state = "closed"  # it finished inside the deadline; the caller that is leaving owns the close
                stale = True
        if stale:
            try:
                connection.close()
            except OSError:
                pass
        # shortcut: a stalled resolver thread outlives the deadline until getaddrinfo returns; upgrade to a
        # resolver with a native timeout if the platform offers one.
        raise TimeoutError("provider connect deadline exceeded")
    if failure:
        raise failure[0]
    return connection


class PrivyUserReader:
    """Holds the app credential privately. Its repr never shows it."""

    def __init__(self, app_id: str, app_secret: str) -> None:
        if not app_id or not app_secret:
            raise SystemExit("lookup: credential not configured")
        self._app_id = app_id
        self._auth = "Basic " + base64.b64encode(f"{app_id}:{app_secret}".encode()).decode("ascii")
        self._connect = _default_connect
        self._clock = time.monotonic

    def __repr__(self) -> str:
        return "PrivyUserReader(<redacted>)"

    def __call__(self, did: str) -> object:
        if not valid_did(did):
            return None
        return self._fetch("GET", _USERS_PATH + urllib.parse.quote(did, safe=""), None)

    def wallet_by_address(self, address: str) -> object:
        """Read-only fixed lookup: POST {address} to the wallets-by-address endpoint. No create or policy call."""
        if not valid_address(address):
            return None
        return self._fetch("POST", _WALLETS_BY_ADDRESS_PATH, json.dumps({"address": address}).encode("ascii"),
                           {"Content-Type": "application/json"})

    def wallet_by_id(self, wallet_id: str) -> object:
        """Read-only fixed lookup: GET /v1/wallets/{id}. No create, update, signer or policy call."""
        if not valid_wallet_id(wallet_id):
            return None
        return self._fetch("GET", _WALLETS_BY_ID_PATH + urllib.parse.quote(wallet_id, safe=""), None)

    def _fetch(self, method: str, path: str, body: bytes | None,
               extra_headers: dict[str, str] | None = None) -> object:
        """One fixed read under one absolute deadline. Connect, request, header and body share it."""
        headers = {"Authorization": self._auth, "privy-app-id": self._app_id}
        if extra_headers:
            headers.update(extra_headers)
        deadline = self._clock() + DEADLINE_SECONDS
        connection: http.client.HTTPSConnection | None = None
        response: Any = None
        watchdog: threading.Timer | None = None
        expired = False
        holder: dict[str, Any] = {"sock": None}

        def _expire() -> None:
            nonlocal expired
            expired = True
            sock = holder["sock"] or getattr(connection, "sock", None)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        try:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return None
            # A socket timeout bounds one wait, not the whole read: a paced reply resets it on every
            # receive. Arm the deadline watchdog before the connection so it covers the connect, request,
            # header and body phases; a fired deadline shuts the live socket.
            watchdog = threading.Timer(remaining, _expire)
            watchdog.daemon = True
            watchdog.start()
            connection = self._connect(remaining)
            if expired or self._clock() >= deadline:
                return None  # the connect phase spent the budget: send nothing
            connection.request(method, path, body=body, headers=headers)
            raw = getattr(connection, "sock", None)
            if raw is not None:
                holder["sock"] = raw
            if expired:
                return None
            response = connection.getresponse()
            if response.status != 200:
                return None
            chunks: list[bytes] = []
            total = 0
            while True:
                if expired or self._clock() >= deadline:
                    return None
                chunk = response.read(_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE:
                    return None
                chunks.append(chunk)
            try:
                return json.loads(b"".join(chunks))
            except ValueError:
                return None
        except (http.client.HTTPException, OSError, ValueError):
            return None
        finally:
            if watchdog is not None:
                watchdog.cancel()
            if response is not None:
                try:
                    response.close()
                except OSError:
                    pass
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            raw = holder["sock"]
            if raw is not None:
                try:
                    raw.close()
                except OSError:
                    pass


@dataclass(frozen=True)
class ServerWalletRelease:
    """The exact bound wallet identity from one authored A2 release."""

    release_id: str
    chain_id: int
    wallet_id: str
    address: str
    signer_id: str
    policy_id: str
    policy_owner_id: str
    binding_sha256: str


def server_wallet_binding_sha256(release: ServerWalletRelease) -> str:
    """Stable SHA-256 over the release identity and the wallet, signer and policy that bind it."""
    canonical = json.dumps({"release_id": release.release_id, "chain_id": release.chain_id,
                            "wallet_id": release.wallet_id, "wallet_address": release.address.lower(),
                            "chain_type": "ethereum", "signer_id": release.signer_id,
                            "policy_id": release.policy_id, "policy_owner_id": release.policy_owner_id},
                           sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def load_server_wallet_release(document: object) -> ServerWalletRelease:
    """Read the A2 bound wallet fields. A missing, extra-typed or non-mainnet release is refused."""
    if not isinstance(document, dict) or document.get("schema") != AUTHORED_SCHEMA:
        raise ValueError("server wallet release document")
    release = document.get("release")
    if not isinstance(release, dict) or release.get("kind") != "ACTUAL" or release.get("chain_id") != _MONAD_MAINNET:
        raise ValueError("server wallet release identity")
    release_id = release.get("release_id")
    if not (isinstance(release_id, str) and 0 < len(release_id) <= 128 and "\x00" not in release_id):
        raise ValueError("server wallet release id")
    wallet_id, address = release.get("wallet_id"), release.get("wallet_address")
    signer_id, policy_id = release.get("signer_id"), release.get("policy_id")
    policy_owner_id = release.get("policy_owner_id")
    if not (isinstance(wallet_id, str) and _BOUND_ID.fullmatch(wallet_id) is not None
            and isinstance(address, str) and valid_address(address)
            and isinstance(signer_id, str) and _BOUND_ID.fullmatch(signer_id) is not None
            and isinstance(policy_id, str) and _BOUND_ID.fullmatch(policy_id) is not None
            and isinstance(policy_owner_id, str) and _BOUND_ID.fullmatch(policy_owner_id) is not None):
        raise ValueError("server wallet release fields")
    release_fields = ServerWalletRelease(release_id=release_id, chain_id=_MONAD_MAINNET, wallet_id=wallet_id,
                                         address=address, signer_id=signer_id, policy_id=policy_id,
                                         policy_owner_id=policy_owner_id, binding_sha256="")
    return ServerWalletRelease(release_id=release_id, chain_id=_MONAD_MAINNET, wallet_id=wallet_id,
                               address=address, signer_id=signer_id, policy_id=policy_id,
                               policy_owner_id=policy_owner_id,
                               binding_sha256=server_wallet_binding_sha256(release_fields))


def _valid_optional_record_fields(record: dict[str, Any]) -> bool:
    created_at = record.get("created_at")
    if "created_at" in record and (type(created_at) is not int or created_at <= 0):
        return False
    if "entity" in record:
        entity = record["entity"]
        if entity is not None and not (isinstance(entity, dict) and set(entity) == {"id", "type"}
                                       and isinstance(entity.get("id"), str) and entity["id"]
                                       and entity.get("type") in {"user", "organization"}):
            return False
    for key in ("external_id", "display_name"):
        if key in record and record[key] is not None and not isinstance(record[key], str):
            return False
    for key in ("exported_at", "imported_at"):
        if key in record and record[key] is not None:
            return False
    return True


def match_server_wallet(record: object, release: ServerWalletRelease) -> dict[str, str] | None:
    """Return the matched identity only for one exact wallet object; any other shape is `None`."""
    if not isinstance(record, dict) or not (_RECORD_REQUIRED <= set(record)
                                            <= _RECORD_REQUIRED | _RECORD_OPTIONAL):
        return None
    address = record.get("address")
    if not (record.get("id") == release.wallet_id and isinstance(address, str)
            and address.lower() == release.address.lower() and record.get("chain_type") == "ethereum"
            and record.get("policy_ids") == [release.policy_id]
            and record.get("owner_id") == release.policy_owner_id
            and record.get("additional_signers") == [{"signer_id": release.signer_id,
                                                       "override_policy_ids": [release.policy_id]}]
            and _valid_optional_record_fields(record)):
        return None
    return {"wallet_id": release.wallet_id, "address": release.address, "chain_type": "ethereum",
            "release_binding_sha256": release.binding_sha256}


def answer_server_wallet(message: dict[str, Any], fetch_wallet: FetchWallet,
                         release: ServerWalletRelease | None) -> dict[str, Any]:
    """The only server-wallet operation. The caller names no wallet, field, URL or release."""
    if release is None or message != {"op": SERVER_WALLET_OPERATION}:
        return {"status": "unknown", "reason": "UNSUPPORTED_REQUEST"}
    try:
        record = fetch_wallet(release.wallet_id)
    except Exception:  # noqa: BLE001 - one failed read stays UNKNOWN; no provider text escapes
        return {"status": "unknown", "reason": "LOOKUP_FAILED"}
    if record is None:
        return {"status": "unknown", "reason": "LOOKUP_UNAVAILABLE"}
    matched = match_server_wallet(record, release)
    if matched is None:
        return {"status": "unknown", "reason": "NO_EXACT_MATCH"}
    return {"status": "matched", **matched}


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


def handle(conn: socket.socket, fetch_user: FetchUser, fetch_wallet: FetchWallet | None = None,
           server_wallet: ServerWalletRelease | None = None,
           fetch_wallet_by_id: FetchWallet | None = None) -> None:
    conn.settimeout(CONNECTION_TIMEOUT)
    try:
        if not same_user_peer(conn):
            return
        try:
            message = read_frame(conn, time.monotonic() + CONNECTION_TIMEOUT)
        except (FrameError, OSError):
            conn.sendall(encode_frame({"status": "unknown", "reason": "MALFORMED_FRAME"}))
            return
        try:
            if message.get("op") == SERVER_WALLET_OPERATION:
                reply = (answer_server_wallet(message, fetch_wallet_by_id, server_wallet)
                         if fetch_wallet_by_id is not None
                         else {"status": "unknown", "reason": "UNSUPPORTED_REQUEST"})
            else:
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


def serve(path: str, fetch_user: FetchUser, fetch_wallet: FetchWallet | None = None,
          server_wallet: ServerWalletRelease | None = None, fetch_wallet_by_id: FetchWallet | None = None,
          ready: threading.Event | None = None) -> None:
    target = prepare_socket_path(path)
    previous = os.umask(0o177)
    try:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(target))
    finally:
        os.umask(previous)
    os.chmod(target, 0o600)
    server.listen(8)
    if ready is not None:
        ready.set()
    try:
        while True:
            conn, _ = server.accept()
            with conn:
                handle(conn, fetch_user, fetch_wallet, server_wallet, fetch_wallet_by_id)
    finally:
        server.close()
        target.unlink(missing_ok=True)


def _release_from_file(path: str) -> ServerWalletRelease:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit("lookup: server wallet release unreadable") from None
    try:
        return load_server_wallet_release(document)
    except ValueError:
        raise SystemExit("lookup: server wallet release invalid") from None


def main(argv: list[str]) -> int:
    if len(argv) == 2:
        release = None
    elif len(argv) == 4 and argv[2] == "--server-wallet-release":
        release = _release_from_file(argv[3])
    else:
        print("usage: lookup_server.py <socket_path> [--server-wallet-release <release.json>]", file=sys.stderr)
        return 2
    reader = PrivyUserReader(os.environ.get("PRIVY_APP_ID", ""), os.environ.get("PRIVY_APP_SECRET", ""))
    serve(argv[1], reader, reader.wallet_by_address, release, reader.wallet_by_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
