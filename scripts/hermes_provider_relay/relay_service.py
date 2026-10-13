"""The relay process: the only holder of the provider key, and the only component that can reach the provider.

It runs in its own container on an internal network shared only with the AUTHORED provider (see `relay_supervisor.py`).
It reads its fixed configuration, the synthetic provider key and the admission key once, at start. Then, in a loop:

- it writes a heartbeat (release, start time, egress self-probe);
- for every grant the host issued (`grants/<attempt>.json`): a revocation or the grant's expiry closes the attempt;
  otherwise it looks for the attempt's channel request in the job's own output folder (`turn-*-<attempt>`);
- each channel request is handled once, on its own thread: grant signature and window, the channel message, then the
  accepted provider guard on the exact bytes under the grant's policy and logical request. Only then, under the one
  state lock, a start record is created exclusively and fsynced, and exactly one request is sent (`relay_transport`).
  Its outcome is recorded and a bounded reply goes back into the channel.

Records live in `state/<attempt>/`: `started.json`, `finished.json`, `closed.json`. After `closed.json` exists nothing
can start; nothing ever starts without `started.json`; nothing is ever sent twice for one attempt, whatever the job
writes and across restarts. On start the relay marks every started-but-unfinished attempt `unknown_restart` and never
sends for it again. No header value, body or key is ever written to a record or a log.

Usage: python relay_service.py <config.json>. See `docs/qualification/hermes-provider-relay/CONTRACT.md`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import stat
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path[:0] = [str(Path(__file__).resolve().parent)] + [p for p in os.environ.get("RELAY_SUPPORT_PATH", "").split(":") if p]

from provider_guard import GuardPolicy, LogicalRequest, ProviderRequestGuard  # noqa: E402
from provider_transport import TransportReply, TransportRoute, reply_refusal  # noqa: E402
from relay_admission import (  # noqa: E402
    IDENTIFIER, ProviderDestination, RelayRelease, channel_refusal, grant_refusal, parse_channel_message,
)
from relay_transport import ReplyLost, send_once  # noqa: E402

MAX_GRANTS = 1024
MAX_GRANT_BYTES = 256 * 1024
MAX_EVENTS = 10_000
MAX_RECOVERED = 10_000
MAX_HANDLERS = 16
CHANNEL = ("output", "relay-channel")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
GUARD_HEADERS = {"accept": "application/json", "content-type": "application/json"}


def _write_new(folder: int, name: str, value: dict[str, Any]) -> bool:
    """Create `name` in `folder` exactly once, fully written and fsynced, by a temporary file and a rename.

    Returns False when it already exists or the folder refuses (a link, a planted file). Never follows a link.
    """
    temporary = f".{name}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
    except OSError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, sort_keys=True))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.stat(name, dir_fd=folder, follow_symlinks=False)
            return False  # exists already: the first one stands
        except FileNotFoundError:
            pass
        os.rename(temporary, name, src_dir_fd=folder, dst_dir_fd=folder)
        os.fsync(folder)
        return True
    finally:
        try:
            os.unlink(temporary, dir_fd=folder)
        except OSError:
            pass


def _read_plain(folder: int, name: str, limit: int) -> bytes | None:
    """A plain file of at most `limit` bytes, read without following a link or blocking; otherwise None."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            return None
        data = os.read(fd, limit + 1)
        return data if len(data) <= limit else None
    except OSError:
        return None
    finally:
        os.close(fd)


def _open_path(root: int, parts: tuple[str, ...]) -> int | None:
    fd = os.dup(root)
    for part in parts:
        try:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
        except OSError:
            os.close(fd)
            return None
        os.close(fd)
        fd = child
    return fd


class Relay:
    def __init__(self, config: dict[str, Any]) -> None:
        self.release = RelayRelease.from_settings(config["release"])
        if self.release.kind != "AUTHORED":
            raise SystemExit("this relay serves AUTHORED releases only")
        self.destination = ProviderDestination(**config["destination"])
        self.route = TransportRoute(self.release.route_id, "AUTHORED", f"https://{self.destination.host}{self.destination.path}",
                                    self.release.max_reply_bytes)
        paths = config["paths"]
        self.key = Path(paths["provider_key"]).read_text(encoding="utf-8").strip()
        self.admission_key = Path(paths["admission_key"]).read_bytes()
        self.ca_file = paths["provider_ca"]
        self.grants, self.revocations, self.state = Path(paths["grants"]), Path(paths["revocations"]), Path(paths["state"])
        self.channel_roots: dict[str, str] = dict(config["channel_roots"])
        self.poll_seconds = float(config.get("poll_seconds", 0.02))
        self.probes = list(config.get("egress_probes", []))
        self.lock = threading.RLock()  # orders start and close for every attempt; a refusal under it closes too
        self.event_lock = threading.Lock()
        self.handling: set[str] = set()
        self.closed: set[str] = set()  # a closed attempt stays closed; it is never looked at again
        self.handlers = threading.BoundedSemaphore(MAX_HANDLERS)
        self.events = 0
        self.started_at = time.time()
        self.egress: list[dict[str, Any]] = []

    # --- records ----------------------------------------------------------------------------------------------------

    def _attempt_dir(self, attempt: str) -> int:
        try:
            os.mkdir(self.state / attempt, 0o700)
        except FileExistsError:
            pass
        return os.open(self.state / attempt, DIR_FLAGS)

    def _has(self, attempt: str, name: str) -> bool:
        return (self.state / attempt / name).is_file()

    def _record(self, attempt: str, name: str, value: dict[str, Any]) -> bool:
        folder = self._attempt_dir(attempt)
        try:
            return _write_new(folder, name, {"attempt_id": attempt, "at": time.time(), **value})
        finally:
            os.close(folder)

    def event(self, attempt: str | None, kind: str, **detail: Any) -> None:
        with self.event_lock, (self.state / "events.jsonl").open("a", encoding="utf-8") as stream:
            if self.events >= MAX_EVENTS:
                return
            self.events += 1
            stream.write(json.dumps({"attempt_id": attempt, "kind": kind, "at": time.time(), **detail}, sort_keys=True) + "\n")

    def close(self, attempt: str, why: str) -> None:
        with self.lock:
            if not self._has(attempt, "closed.json"):
                self._record(attempt, "closed.json", {"started": self._has(attempt, "started.json"), "why": why})
            self.closed.add(attempt)

    # --- start --------------------------------------------------------------------------------------------------------

    def recover(self) -> None:
        """Before serving: every attempt that started and never finished is unknown, and is never sent again."""
        for count, folder in enumerate(sorted(p for p in self.state.iterdir() if p.is_dir())):
            if count >= MAX_RECOVERED:
                break
            attempt = folder.name
            if not IDENTIFIER.fullmatch(attempt):
                continue
            if self._has(attempt, "started.json") and not self._has(attempt, "finished.json"):
                self._record(attempt, "finished.json", {"outcome": "unknown_restart"})
                self.event(attempt, "unknown_restart")
                grant = self._grant(attempt)
                if grant is not None:
                    self._reply(grant, {"attempt_id": attempt, "outcome": "lost"})

    def probe(self) -> None:
        for target in self.probes:
            try:
                socket.create_connection((target["host"], target["port"]), timeout=2).close()
                reached = True
            except OSError:
                reached = False
            self.egress.append({"host": target["host"], "port": target["port"], "reached": reached,
                                "expected": target["expect"] == "reachable"})

    def heartbeat(self) -> None:
        value = {"release": self.release.settings(), "started_at": self.started_at, "at": time.time(),
                 "egress_probe": self.egress, "pid": os.getpid()}
        temporary = self.state / ".heartbeat.tmp"
        temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.state / "heartbeat.json")

    # --- serving ------------------------------------------------------------------------------------------------------

    def _grant(self, attempt: str) -> dict[str, Any] | None:
        folder = os.open(self.grants, DIR_FLAGS)
        try:
            raw = _read_plain(folder, f"{attempt}.json", MAX_GRANT_BYTES)
        finally:
            os.close(folder)
        grant = parse_channel_message(raw) if raw is not None else None
        return grant if grant is not None and grant.get("attempt_id") == attempt else None

    def _channel(self, grant: dict[str, Any]) -> int | str:
        """The attempt's channel folder (an open fd), or the reason there is none."""
        root_path = self.channel_roots.get(grant["channel_root"])
        if root_path is None:
            return "channel_root_unknown"
        try:
            root = os.open(root_path, DIR_FLAGS)
        except OSError:
            return "channel_root_unavailable"
        try:
            folders = [entry.name for entry in os.scandir(root)
                       if entry.name.startswith("turn-") and entry.name.endswith(f"-{grant['attempt_id']}")]
            if not folders:
                return "no_channel"
            if len(folders) > 1:
                return "channel_ambiguous"
            fd = _open_path(root, (folders[0], *CHANNEL))
            return fd if fd is not None else "no_channel"
        finally:
            os.close(root)

    def _reply(self, grant: dict[str, Any], value: dict[str, Any]) -> None:
        channel = self._channel(grant)
        if isinstance(channel, str):
            return
        try:
            if not _write_new(channel, "reply.json", value):
                self.event(grant["attempt_id"], "reply_not_written")
        finally:
            os.close(channel)

    def serve_once(self) -> None:
        open_names = []
        for name in sorted(os.listdir(self.grants)):
            attempt = name[:-5]
            if not name.endswith(".json") or not IDENTIFIER.fullmatch(attempt) or attempt in self.closed:
                continue
            if self._has(attempt, "closed.json"):
                self.closed.add(attempt)
                continue
            open_names.append(name)
        for name in open_names[:MAX_GRANTS]:  # at most this many open grants are served per pass
            attempt = name[:-5]
            grant = self._grant(attempt)
            if grant is None:
                continue
            if (self.revocations / name).exists():
                self.close(attempt, "revoked")
                continue
            if grant_refusal(grant, self.admission_key, self.release, now=time.time()) == "grant_expired":
                self.close(attempt, "expired")
                continue
            if attempt in self.handling:  # one handling per attempt; a restarted relay finds its start record
                continue
            channel = self._channel(grant)
            if isinstance(channel, str):
                continue
            try:
                os.stat("request.json", dir_fd=channel, follow_symlinks=False)
                present = True
            except OSError:
                present = False
            finally:
                os.close(channel)
            if present and self.handlers.acquire(blocking=False):
                self.handling.add(attempt)
                threading.Thread(target=self._handle, args=(attempt, grant), daemon=True).start()

    def _handle(self, attempt: str, grant: dict[str, Any]) -> None:
        try:
            self._handle_request(attempt, grant)
        except Exception as error:  # noqa: BLE001 - recorded; the attempt stays as its records say
            self.event(attempt, "handler_failed", error_class=type(error).__name__)
        finally:
            self.handlers.release()

    def _refuse(self, attempt: str, grant: dict[str, Any], reason: str) -> None:
        self.event(attempt, "refused", reason=reason)
        self.close(attempt, f"refused:{reason}")  # a refusal is final: nothing can start for this attempt afterwards
        self._reply(grant, {"attempt_id": attempt, "outcome": "refused", "refusal": reason, "before_send": True})

    def _handle_request(self, attempt: str, grant: dict[str, Any]) -> None:
        channel = self._channel(grant)
        if isinstance(channel, str):
            return self._refuse(attempt, grant, channel)
        try:
            raw = _read_plain(channel, "request.json", 2 * self.release.max_request_bytes + 4096)
        finally:
            os.close(channel)
        refusal = grant_refusal(grant, self.admission_key, self.release, now=time.time())
        message = parse_channel_message(raw) if raw is not None else None
        if refusal is None and message is None:
            refusal = "channel_message_invalid"
        if refusal is None:
            refusal = channel_refusal(message, grant, self.release)
        body = base64.b64decode(message["body_b64"]) if refusal is None else b""
        if refusal is None:
            policy = GuardPolicy(**grant["policy"])
            logical = LogicalRequest(grant["logical"]["system_prompt"], grant["logical"]["user_message"])
            decision = ProviderRequestGuard(policy, logical, None).admit(body, GUARD_HEADERS)
            refusal = None if decision.admitted else f"guard:{decision.reason}"
        if refusal is not None:
            return self._refuse(attempt, grant, refusal)
        with self.lock:
            if self._has(attempt, "closed.json"):
                return self._refuse(attempt, grant, "grant_closed")
            if time.time() >= grant["expires_at"]:
                return self._refuse(attempt, grant, "grant_expired")
            if not self._record(attempt, "started.json", {"grant_id": grant["grant_id"], "body_sha256":
                                                         hashlib.sha256(body).hexdigest(), "body_bytes": len(body)}):
                self.event(attempt, "refused", reason="already_started")
                return None  # the first request stands; nothing is sent again
        self._send(attempt, grant, body)
        return None

    def _send(self, attempt: str, grant: dict[str, Any], body: bytes) -> None:
        began = time.time()
        try:
            sent = send_once(self.destination, ca_file=self.ca_file, key=self.key, body=body,
                             deadline=grant["expires_at"], max_reply_bytes=self.release.max_reply_bytes)
        except ReplyLost as lost:
            self._record(attempt, "finished.json", {"outcome": "lost", "error": str(lost), "seconds": time.time() - began})
            return self._reply(grant, {"attempt_id": attempt, "outcome": "lost"})
        refused = reply_refusal(TransportReply(sent.status, sent.body), self.route)
        if refused is None and 300 <= sent.status < 400:
            refused = "reply_redirect_refused"
        if refused is None and not sent.content_type.startswith("application/json"):
            refused = "reply_not_json"
        usage = None
        if refused is None:
            reported = json.loads(sent.body).get("usage")
            keys = ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(reported, dict) and all(type(reported.get(k)) is int for k in keys):  # noqa: E721
                usage = {k: reported[k] for k in keys}
        self._record(attempt, "finished.json", {
            "outcome": "reply" if refused is None else "refused_reply", "refusal": refused, "status": sent.status,
            "reply_bytes": len(sent.body), "reply_sha256": hashlib.sha256(sent.body).hexdigest(), "usage": usage,
            "seconds": time.time() - began})
        if refused is not None:
            return self._reply(grant, {"attempt_id": attempt, "outcome": "refused", "refusal": refused,
                                       "before_send": False})
        return self._reply(grant, {"attempt_id": attempt, "outcome": "reply", "status": sent.status,
                                   "body_b64": base64.b64encode(sent.body).decode()})

    def run(self) -> None:
        self.probe()
        self.recover()
        while True:
            self.heartbeat()
            self.serve_once()
            time.sleep(self.poll_seconds)


def main() -> int:
    Relay(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
