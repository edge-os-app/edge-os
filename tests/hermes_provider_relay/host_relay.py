"""The relay and the AUTHORED provider as host processes on loopback, for fast tests of the relay's own rules.

This harness does NOT enforce egress: the Docker tests do that. Here the same `relay_service.py` and
`authored_provider.py` run unchanged with host paths, so grant, channel, duplicate, cancellation and restart behavior can
be driven exactly. Test support only; synthetic key; the provider listens on 127.0.0.1.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from relay_admission import RelayRelease, issue_grant
from relay_supervisor import make_provider_tls

REPO = Path(__file__).resolve().parents[2]
RELAY = REPO / "scripts" / "hermes_provider_relay"
SUPPORT = f"{REPO / 'scripts' / 'hermes_job_support'}:{REPO / 'scripts' / 'hermes_interpretation'}"
POLICY = {"model": "fixture-model/1", "max_output_tokens": 4096, "max_request_bytes": 12_000,
          "max_envelope_chars": 2_500, "required_extra": {}}
SYSTEM, TASK = "You interpret research requests.", "Find wallets that bought X."


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def body(attempt: str, **changes: Any) -> bytes:
    """A wire body the accepted guard admits for SYSTEM and TASK."""
    value = {"model": "fixture-model/1", "max_tokens": 4096, "session_id": f"p05-{attempt}",
             "messages": [{"role": "system", "content": f"Hermes says: {SYSTEM}"}, {"role": "user", "content": TASK}]}
    value.update(changes)
    return json.dumps(value).encode()


class HostRelay:
    def __init__(self, root: Path, release: RelayRelease, key_file: Path) -> None:
        self.root, self.release, self.key_file = root, release, key_file
        for folder in ("grants", "revocations", "state", "tls", "scripts", "receipts", "jobs"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        self.admission_key = secrets.token_bytes(32)
        (root / "admission-key").write_bytes(self.admission_key)
        make_provider_tls(root / "tls", ("localhost",))
        self.port = free_port()
        (root / "provider.json").write_text(json.dumps({
            "bind": "127.0.0.1", "port": self.port, "path": "/v1/chat/completions", "cert": str(root / "tls/server.pem"),
            "key": str(root / "tls/server.key"), "scripts": str(root / "scripts"), "receipts": str(root / "receipts"),
            "expected_key_file": str(key_file)}))
        (root / "relay.json").write_text(json.dumps({
            "release": release.settings(), "destination": {"host": "localhost", "port": self.port,
                                                           "path": "/v1/chat/completions"},
            "channel_roots": {"jobs": str(root / "jobs")},
            "paths": {"provider_key": str(key_file), "admission_key": str(root / "admission-key"),
                      "provider_ca": str(root / "tls/ca.pem"), "grants": str(root / "grants"),
                      "revocations": str(root / "revocations"), "state": str(root / "state")},
            "poll_seconds": 0.01}))
        self.provider = self.relay = None

    def start(self) -> HostRelay:
        self.provider = subprocess.Popen([sys.executable, "-B", str(RELAY / "authored_provider.py"),
                                          str(self.root / "provider.json")])
        self._wait(lambda: (self.root / "receipts" / "ready").exists())
        self.start_relay()
        return self

    def start_relay(self) -> None:
        before = self.heartbeat().get("started_at", 0)
        self.relay = subprocess.Popen([sys.executable, "-B", str(RELAY / "relay_service.py"), str(self.root / "relay.json")],
                                      env={**os.environ, "RELAY_SUPPORT_PATH": SUPPORT})
        self._wait(lambda: self.heartbeat().get("started_at", 0) > before)

    def kill_relay(self) -> None:
        self.relay.send_signal(signal.SIGKILL)
        self.relay.wait(10)

    def stop(self) -> None:
        for process in (self.relay, self.provider):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(10)

    def heartbeat(self) -> dict[str, Any]:
        try:
            return json.loads((self.root / "state" / "heartbeat.json").read_text())
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _wait(ready: Any, seconds: float = 15.0) -> None:
        until = time.monotonic() + seconds
        while not ready():
            assert time.monotonic() < until, "not ready in time"
            time.sleep(0.01)

    # --- driving ------------------------------------------------------------------------------------------------------

    def grant(self, attempt: str, *, key: bytes | None = None, release: RelayRelease | None = None,
              timeout_seconds: float = 10.0, issued_at: float | None = None, **changes: Any) -> dict[str, Any]:
        grant = issue_grant(release=release or self.release, run_id="run-1", channel_root="jobs", owner_id="owner-a",
                            request_id="intake-1", attempt_id=attempt, scope="intake:intake-1", policy=POLICY,
                            system_prompt=SYSTEM, user_message=TASK, issued_at=issued_at or time.time(),
                            timeout_seconds=timeout_seconds, key=key or self.admission_key)
        grant.update(changes)
        (self.root / "grants" / f"{attempt}.json").write_text(json.dumps(grant))
        return grant

    def script(self, attempt: str, script: dict[str, Any]) -> None:
        (self.root / "scripts" / f"{attempt}.json").write_text(json.dumps(script))

    def channel(self, attempt: str, sequence: int = 1) -> Path:
        folder = self.root / "jobs" / f"turn-{sequence:02d}-{attempt}" / "output" / "relay-channel"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def request(self, attempt: str, raw: bytes | None = None, **message: Any) -> Path:
        value = {"attempt_id": attempt, "route_id": self.release.route_id, "release_id": self.release.release_id,
                 "body_b64": base64.b64encode(body(attempt)).decode()}
        value.update(message)
        folder = self.channel(attempt)
        (folder / ".tmp").write_bytes(raw if raw is not None else json.dumps(value).encode())
        os.replace(folder / ".tmp", folder / "request.json")
        return folder

    def reply(self, attempt: str, seconds: float = 10.0) -> dict[str, Any]:
        path = self.channel(attempt) / "reply.json"
        self._wait(path.exists, seconds)
        return json.loads(path.read_text())

    def revoke(self, attempt: str) -> None:
        (self.root / "revocations" / f"{attempt}.json").write_text("{}")

    def record(self, attempt: str, name: str, seconds: float = 0.0) -> dict[str, Any] | None:
        path = self.root / "state" / attempt / f"{name}.json"
        if seconds:
            self._wait(path.exists, seconds)
        return json.loads(path.read_text()) if path.exists() else None

    def receipts(self, attempt: str) -> list[dict[str, Any]]:
        path = self.root / "receipts" / "receipts.jsonl"
        lines = path.read_text().splitlines() if path.exists() else []
        return [r for r in map(json.loads, lines) if r["attempt_id"] == attempt]

    def events(self, attempt: str) -> list[dict[str, Any]]:
        path = self.root / "state" / "events.jsonl"
        lines = path.read_text().splitlines() if path.exists() else []
        return [r for r in map(json.loads, lines) if r["attempt_id"] == attempt]
