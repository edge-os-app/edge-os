#!/usr/bin/env python3
"""Checked tmux-bridge delivery and per-session Stop guard."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STATUSES = {"PREPARED", "TYPED", "SUBMITTED", "UNCONFIRMED", "BLOCKED"}
ALLOW_STOP = {"AWAITING_EVENT", "BLOCKED", "BUDGET_EXHAUSTED", "APPROVAL_REQUIRED", "INTERRUPTED", "RUN_LIMIT", "COMPLETE"}
OPEN_DELIVERIES = ("PREPARED", "TYPED", "UNCONFIRMED", "BLOCKED")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _key_tuple(record: dict) -> tuple[str, str, str, str, str, str, str, str]:
    values = tuple(record.get(k, "") for k in ("host", "session_id", "agent_id", "task_id", "event_id", "candidate", "sender", "destination"))
    if any(not isinstance(v, str) or not v or "\n" in v or "\r" in v for v in values):
        raise ValueError("host, session_id, agent_id, task_id, event_id, candidate, sender, and destination must be non-empty single-line strings")
    if values[0] not in {"codex", "claude"} or values[2] != f"{values[0]}:{values[1]}":
        raise ValueError("delivery host/session identity is invalid")
    return values  # type: ignore[return-value]


class GuardStore:
    """Atomic delivery records and bounded Stop reason identities."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS delivery ("
                "host TEXT NOT NULL,session_id TEXT NOT NULL,agent_id TEXT NOT NULL,"
                "task_id TEXT NOT NULL,event_id TEXT NOT NULL,candidate TEXT NOT NULL,sender TEXT NOT NULL,destination TEXT NOT NULL,"
                "status TEXT NOT NULL,preflight_sha256 TEXT,typed_sha256 TEXT,text_sha256 TEXT,updated_at REAL NOT NULL,"
                "PRIMARY KEY(host,session_id,agent_id,task_id,event_id,candidate,sender,destination))"
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(delivery)")}
            if "host" not in columns:
                db.execute("ALTER TABLE delivery RENAME TO delivery_legacy")
                db.execute(
                    "CREATE TABLE delivery ("
                    "host TEXT NOT NULL,session_id TEXT NOT NULL,agent_id TEXT NOT NULL,"
                    "task_id TEXT NOT NULL,event_id TEXT NOT NULL,candidate TEXT NOT NULL,sender TEXT NOT NULL,destination TEXT NOT NULL,"
                    "status TEXT NOT NULL,preflight_sha256 TEXT,typed_sha256 TEXT,text_sha256 TEXT,updated_at REAL NOT NULL,"
                    "PRIMARY KEY(host,session_id,agent_id,task_id,event_id,candidate,sender,destination))"
                )
                db.execute(
                    "INSERT INTO delivery SELECT '', '', '', task_id,event_id,candidate,sender,destination,status,"
                    "preflight_sha256,typed_sha256,text_sha256,updated_at FROM delivery_legacy"
                )
                db.execute("DROP TABLE delivery_legacy")
            db.execute(
                "CREATE TABLE IF NOT EXISTS stop_seen ("
                "host TEXT NOT NULL,session_id TEXT NOT NULL,reason_id TEXT NOT NULL,updated_at REAL NOT NULL,"
                "PRIMARY KEY(host,session_id,reason_id))"
            )
            stop_columns = {row[1] for row in db.execute("PRAGMA table_info(stop_seen)")}
            if "host" not in stop_columns:
                db.execute("ALTER TABLE stop_seen RENAME TO stop_seen_legacy")
                db.execute(
                    "CREATE TABLE stop_seen (host TEXT NOT NULL,session_id TEXT NOT NULL,reason_id TEXT NOT NULL,"
                    "updated_at REAL NOT NULL,PRIMARY KEY(host,session_id,reason_id))"
                )
                db.execute("INSERT INTO stop_seen SELECT '',session_id,reason_id,updated_at FROM stop_seen_legacy")
                db.execute("DROP TABLE stop_seen_legacy")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @contextlib.contextmanager
    def target_lock(self, target: str):
        path = self.path.parent / ("target-" + digest(target)[:24] + ".lock")
        with path.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def get_record(self, key: tuple[str, str, str, str, str, str, str, str]) -> dict | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM delivery WHERE host=? AND session_id=? AND agent_id=? AND task_id=? AND event_id=? AND candidate=? AND sender=? AND destination=?", key
            ).fetchone()
            return dict(row) if row else None

    def put_record(self, record: dict) -> None:
        key = _key_tuple(record)
        status = record.get("status")
        if status not in STATUSES:
            raise ValueError("invalid delivery status")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO delivery VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(host,session_id,agent_id,task_id,event_id,candidate,sender,destination) DO UPDATE SET "
                "status=excluded.status,preflight_sha256=COALESCE(excluded.preflight_sha256,delivery.preflight_sha256),"
                "typed_sha256=COALESCE(excluded.typed_sha256,delivery.typed_sha256),"
                "text_sha256=COALESCE(excluded.text_sha256,delivery.text_sha256),updated_at=excluded.updated_at",
                (
                    *key, status, record.get("preflight_sha256"), record.get("typed_sha256"),
                    record.get("text_sha256") or (digest(record["text"]) if isinstance(record.get("text"), str) else None),
                    time.time(),
                ),
            )

    def open_for_binding(self, host: str, session_id: str, agent_id: str, task_ids: list[str]) -> list[dict]:
        if not task_ids:
            return []
        placeholders = ",".join("?" for _ in task_ids)
        with self._db() as db:
            rows = db.execute(
                "SELECT task_id,event_id,candidate,destination,status FROM delivery "
                f"WHERE host=? AND session_id=? AND agent_id=? AND task_id IN ({placeholders}) AND status IN (?,?,?,?) ORDER BY updated_at",
                (host, session_id, agent_id, *task_ids, *OPEN_DELIVERIES),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_stop_reason(self, host: str, session_id: str, reason_id: str) -> bool:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM stop_seen WHERE host=? AND session_id=? AND reason_id=?", (host, session_id, reason_id)).fetchone():
                return False
            db.execute("INSERT INTO stop_seen VALUES (?,?,?,?)", (host, session_id, reason_id, time.time()))
            db.execute(
                "DELETE FROM stop_seen WHERE host=? AND session_id=? AND reason_id IN ("
                "SELECT reason_id FROM stop_seen WHERE host=? AND session_id=? ORDER BY updated_at DESC LIMIT -1 OFFSET 64)",
                (host, session_id, host, session_id),
            )
            return True


class TmuxBridge:
    """The installed bridge is the only transport boundary."""

    def __init__(self, executable: str = "tmux-bridge"):
        self.executable = executable

    def _run(self, *args: str) -> str:
        result = subprocess.run([self.executable, *args], text=True, capture_output=True, check=False)
        if result.returncode:
            raise RuntimeError("tmux-bridge command failed: " + args[0])
        return result.stdout.rstrip("\n")

    def id(self) -> str:
        return self._run("id").strip()

    def resolve(self, destination: str) -> str:
        if destination.startswith("%") and destination[1:].isdigit():
            return destination
        return self._run("resolve", destination).strip()

    def read(self, target: str) -> str:
        return self._run("read", target, "80")

    def message(self, target: str, text: str) -> None:
        self._run("message", target, text)

    def enter(self, target: str) -> None:
        self._run("keys", target, "Enter")


def _message_line(line: str, sender: str, text: str) -> bool:
    suffix = "] " + text
    line = re.sub(r"^\s*(?:❯|›)\s*", "", line)
    match = re.match(r"^\[tmux-bridge from:[^\]]+ pane:([^\s\]]+) at:[^\]]+ — load the smux skill to reply\] ", line)
    return bool(match and match.group(1) == sender and line.endswith(suffix))


def _has_active_draft(capture: str, sender: str, text: str) -> bool:
    lines = capture.splitlines()
    return bool(lines and _message_line(lines[-1], sender, text))


def _has_partial_input(capture: str) -> bool:
    lines = capture.splitlines()
    if not lines or lines[-1].strip() in {"❯", "›"}:
        return False
    return any(re.match(r"^\s*(?:❯|›)(?:\s|$)", line) for line in lines)


def _submitted(capture: str, sender: str, text: str) -> bool:
    lines = capture.splitlines()
    return bool(lines and lines[-1].strip() in {"❯", "›"} and any(_message_line(line, sender, text) for line in lines[:-1]))


def _read_hash(capture: str) -> str:
    return hashlib.sha256(capture.encode("utf-8")).hexdigest()


def checked_send(request: dict, bridge, store: GuardStore, settle=lambda: time.sleep(0.18)) -> dict:
    """Send one confirmed message, or preserve a state that cannot be retried."""
    key = _key_tuple(request)
    sender, destination = key[6], key[7]
    target_id = request.get("destination_id")
    destination_name = request.get("destination_name", destination)
    text = request.get("text")
    preflight_hash = request.get("preflight_sha256")
    if not isinstance(target_id, str) or not target_id.startswith("%") or not target_id[1:].isdigit():
        raise ValueError("destination_id must be a tmux pane ID")
    if not isinstance(text, str) or not text or "\n" in text or "\r" in text or text.lstrip().startswith("/clear"):
        raise ValueError("text must be one normal Smux message line; native /clear is not a message")
    if not isinstance(preflight_hash, str) or not HASH_RE.fullmatch(preflight_hash):
        raise ValueError("preflight_sha256 must be a SHA-256 capture hash")

    with store.target_lock(destination):
        current = store.get_record(key)
        if current and current["status"] in {"SUBMITTED", "UNCONFIRMED", "BLOCKED"}:
            return {"status": current["status"], "duplicate": True}
        if current and current.get("text_sha256") != digest(text):
            store.put_record({**current, "status": "BLOCKED"})
            return {"status": "BLOCKED", "reason": "event identity is already bound to different message content"}
        if current and current["status"] == "PREPARED" and current.get("preflight_sha256") != preflight_hash:
            store.put_record({**current, "status": "BLOCKED"})
            return {"status": "BLOCKED", "reason": "event identity is already bound to a different preflight capture"}
        try:
            if bridge.id() != sender:
                raise ValueError("active sender pane does not match request")
            if bridge.resolve(destination_name) != target_id or target_id != destination:
                raise ValueError("destination pane identity changed or does not match its pane ID")
        except Exception as exc:
            store.put_record({**request, "status": "BLOCKED"})
            return {"status": "BLOCKED", "reason": str(exc)}

        if not current:
            current = {**request, "status": "PREPARED", "preflight_sha256": preflight_hash}
            store.put_record(current)
        try:
            before = bridge.read(target_id)
        except Exception:
            store.put_record({**current, "status": "BLOCKED"})
            return {"status": "BLOCKED", "reason": "destination preflight read failed"}

        if current["status"] == "PREPARED":
            if _has_active_draft(before, sender, text):
                store.put_record({**current, "status": "BLOCKED"})
                return {"status": "BLOCKED", "reason": "PREPARED events cannot adopt an existing draft; only durable TYPED events can recover"}
            if _read_hash(before) != preflight_hash:
                store.put_record({**current, "status": "BLOCKED"})
                return {"status": "BLOCKED", "reason": "pane capture changed after confirmation"}
            if not (request.get("confirm_idle") is True and request.get("confirm_no_draft") is True) or _has_partial_input(before):
                store.put_record({**current, "status": "BLOCKED"})
                return {"status": "BLOCKED", "reason": "explicit idle and no-draft confirmation is required"}

        if current["status"] == "TYPED" and (
            not _has_active_draft(before, sender, text)
            or _read_hash(before) != current.get("typed_sha256")
        ):
            store.put_record({**current, "status": "BLOCKED"})
            return {"status": "BLOCKED", "reason": "the exact own draft capture is no longer the durable same-event input"}

        if current["status"] != "TYPED":
            try:
                if bridge.resolve(destination_name) != target_id:
                    raise ValueError("destination pane identity changed before typing")
                bridge.message(target_id, text)
                settle()
                after_type = bridge.read(target_id)
            except Exception:
                try:
                    settle()
                    after_type = bridge.read(target_id)
                except Exception:
                    after_type = ""
                if _has_active_draft(after_type, sender, text):
                    store.put_record({**current, "status": "TYPED", "typed_sha256": _read_hash(after_type)})
                else:
                    store.put_record({**current, "status": "BLOCKED"})
                    return {"status": "BLOCKED", "reason": "typing failed or left an unverified pane state"}
                return {"status": "TYPED", "reason": "own draft is present; same-input recovery is available"}
            if not _has_active_draft(after_type, sender, text):
                store.put_record({**current, "status": "BLOCKED"})
                return {"status": "BLOCKED", "reason": "typed message did not match the exact requested input"}
            store.put_record({**current, "status": "TYPED", "typed_sha256": _read_hash(after_type)})

        # Persist uncertainty before the keypress so a crash can never cause a blind retry.
        store.put_record({**current, "status": "UNCONFIRMED"})
        # The prior read satisfies tmux-bridge's read guard. Never repeat an Enter attempt.
        try:
            bridge.enter(target_id)
        except Exception:
            try:
                bridge.read(target_id)
            except Exception:
                pass
            store.put_record({**current, "status": "UNCONFIRMED"})
            return {"status": "UNCONFIRMED", "reason": "Enter may have been sent; do not retry this event"}

        try:
            after_enter = bridge.read(target_id)
        except Exception:
            store.put_record({**current, "status": "UNCONFIRMED"})
            return {"status": "UNCONFIRMED", "reason": "post-Enter read failed; do not retry this event"}
        status = "SUBMITTED" if _submitted(after_enter, sender, text) else "UNCONFIRMED"
        store.put_record({**current, "status": status})
        return {"status": status, "reason": None if status == "SUBMITTED" else "post-Enter result is ambiguous; do not retry this event"}


def _state_read(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "bindings": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("bindings"), list):
        raise ValueError("state must contain version 1 and a bindings list")
    return state


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def save_binding(state_file: Path, binding: dict, replace: bool = False) -> None:
    required = ("host", "session_id", "agent_id", "pane_id", "cwd", "status")
    if any(not isinstance(binding.get(k), str) or not binding[k] for k in required):
        raise ValueError("binding requires host, session_id, agent_id, pane_id, cwd, and status")
    if (
        binding["host"] not in {"codex", "claude"}
        or binding["agent_id"] != f"{binding['host']}:{binding['session_id']}"
        or not re.fullmatch(r"%[0-9]+", binding["pane_id"])
    ):
        raise ValueError("agent_id must equal '<host>:<session_id>' and pane_id must be a tmux pane ID")
    if not isinstance(binding.get("required_reports"), list) or not isinstance(binding.get("approved_work"), list):
        raise ValueError("required_reports and approved_work must be lists")
    if any(not isinstance(p, str) or not p or Path(p).is_absolute() or ".." in Path(p).parts for p in binding["required_reports"]):
        raise ValueError("required report paths must stay inside the bound cwd")
    if any(not isinstance(w, dict) or not isinstance(w.get("id"), str) or not isinstance(w.get("status"), str) for w in binding["approved_work"]):
        raise ValueError("approved work entries require id and status")
    lock_path = state_file.with_name(state_file.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = _state_read(state_file)
            entries = state["bindings"]
            index = next((i for i, old in enumerate(entries) if old.get("host") == binding["host"] and old.get("session_id") == binding["session_id"]), None)
            if index is not None and not replace:
                raise ValueError("session binding already exists; use update")
            if index is None:
                entries.append(binding)
            else:
                old = entries[index]
                if old.get("agent_id") != binding["agent_id"] or old.get("pane_id") != binding["pane_id"] or old.get("cwd") != binding["cwd"]:
                    raise ValueError("update cannot change the bound agent, pane, or cwd identity")
                entries[index] = binding
            _atomic_json(state_file, state)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _valid_binding(binding: dict, host: str, session_id: str) -> bool:
    required_text = ("host", "session_id", "agent_id", "pane_id", "cwd", "status")
    if any(not isinstance(binding.get(key), str) or not binding[key] for key in required_text):
        return False
    if (
        binding["host"] != host
        or binding["session_id"] != session_id
        or binding["agent_id"] != f"{host}:{session_id}"
        or not re.fullmatch(r"%[0-9]+", binding["pane_id"])
        or binding["status"] not in ALLOW_STOP | {"ACTIVE"}
        or not isinstance(binding.get("required_reports"), list)
        or not isinstance(binding.get("approved_work"), list)
    ):
        return False
    if any(not isinstance(p, str) or not p or Path(p).is_absolute() or ".." in Path(p).parts for p in binding["required_reports"]):
        return False
    if any(
        not isinstance(work, dict)
        or not isinstance(work.get("id"), str)
        or not work.get("id")
        or not isinstance(work.get("status"), str)
        for work in binding["approved_work"]
    ):
        return False
    return True


def stop_decision(host: str, payload: dict, state_file: Path, store: GuardStore) -> dict:
    session_id, cwd = payload.get("session_id"), payload.get("cwd")
    if not isinstance(session_id, str) or not session_id or not isinstance(cwd, str) or not cwd:
        return {"decision": "allow"}
    if payload.get("stop_hook_active") is True:
        return {"decision": "allow"}
    try:
        state = _state_read(state_file)
    except Exception:
        reason = "Controller guard state is unreadable. Repair the registered state file before the next turn."
        first = store.mark_stop_reason(host, session_id, digest(host + ":" + session_id + ":bad-state"))
        return {"decision": "block", "reason": reason} if first else {"decision": "allow"}

    matches = [b for b in state["bindings"] if isinstance(b, dict) and b.get("host") == host and b.get("session_id") == session_id]
    if len(matches) > 1:
        reason = "Controller guard has duplicate bindings for this session. Repair the state file."
        first = store.mark_stop_reason(host, session_id, digest(host + ":" + session_id + ":duplicate-binding"))
        return {"decision": "block", "reason": reason} if first else {"decision": "allow"}
    binding = matches[0] if matches else None
    if binding is None:
        return {"decision": "allow"}
    if not _valid_binding(binding, host, session_id):
        reason = "Controller guard session binding is malformed. Repair it before the next turn."
        first = store.mark_stop_reason(host, session_id, digest(host + ":" + session_id + ":bad-binding"))
        return {"decision": "block", "reason": reason} if first else {"decision": "allow"}
    if os.path.realpath(cwd) != os.path.realpath(binding["cwd"]):
        reason = "Controller guard session identity does not match its registered agent and cwd. Repair the binding."
        first = store.mark_stop_reason(host, session_id, digest(host + ":" + session_id + ":identity"))
        return {"decision": "block", "reason": reason} if first else {"decision": "allow"}
    if binding.get("status") in ALLOW_STOP:
        return {"decision": "allow"}

    reasons = []
    for report in binding.get("required_reports", []):
        if not isinstance(report, str) or not report or Path(report).is_absolute() or ".." in Path(report).parts:
            reasons.append("invalid-report-binding")
        else:
            root = Path(binding["cwd"]).resolve()
            report_path = (root / report).resolve()
            if root not in report_path.parents:
                reasons.append("invalid-report-binding")
            elif not report_path.is_file():
                reasons.append("missing-report:" + report)
    active_tasks = [
        work["id"] for work in binding["approved_work"]
        if work["status"] in {"eligible", "pending", "in_progress"}
    ]
    unfinished = store.open_for_binding(host, session_id, binding["agent_id"], active_tasks)
    reasons.extend("unfinished-delivery:" + r["task_id"] + ":" + r["event_id"] for r in unfinished)
    for work in binding.get("approved_work", []):
        if isinstance(work, dict) and work.get("status") in {"eligible", "pending", "in_progress"}:
            reasons.append("approved-work:" + str(work.get("id", "unknown")))
    if not reasons:
        return {"decision": "allow"}
    reason_id = digest(host + ":" + session_id + ":" + "|".join(sorted(reasons)))
    if not store.mark_stop_reason(host, session_id, reason_id):
        return {"decision": "allow"}
    codes = ", ".join(part.split(":", 1)[0] for part in sorted(reasons))
    return {
        "decision": "block",
        "reason": "Controller work remains: " + codes + ". Record an allowed wait, blocker, approval, interruption, limit, or completion state.",
    }


def _default_state_root() -> Path:
    override = os.environ.get("CONTROLLER_GUARD_STATE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    project = Path(__file__).resolve().parents[1]
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")).expanduser()
    return base / "edge-os" / "controller-guard" / digest(str(project))


def _binding_path(root: Path) -> Path:
    return root / "bindings.json"


def _hook(host: str, root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be an object")
    except Exception:
        print('{}')
        return 0
    if not _binding_path(root).exists():
        print('{}')
        return 0
    result = stop_decision(host, payload, _binding_path(root), GuardStore(root / "delivery.sqlite3"))
    print(json.dumps({"decision": "block", "reason": result["reason"]}, separators=(",", ":")) if result["decision"] == "block" else '{}')
    return 0


def preflight(destination_name: str, bridge: TmuxBridge) -> dict:
    sender = bridge.id()
    destination_id = bridge.resolve(destination_name)
    if not destination_id.startswith("%") or not destination_id[1:].isdigit():
        raise ValueError("resolved destination is not a tmux pane ID")
    capture = bridge.read(destination_id)
    return {
        "sender": sender,
        "destination_name": destination_name,
        "destination_id": destination_id,
        "capture_sha256": _read_hash(capture),
        "capture": capture,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, default=_default_state_root())
    commands = parser.add_subparsers(dest="command", required=True)
    hook = commands.add_parser("hook")
    hook.add_argument("host", choices=("codex", "claude"))
    for name in ("bind", "update"):
        cmd = commands.add_parser(name)
        cmd.add_argument("host", choices=("codex", "claude"))
    inspect = commands.add_parser("preflight")
    inspect.add_argument("destination")
    commands.add_parser("send")
    args = parser.parse_args(argv)
    root = args.state_root.expanduser().resolve()
    if args.command == "hook":
        return _hook(args.host, root)
    if args.command == "preflight":
        try:
            print(json.dumps(preflight(args.destination, TmuxBridge()), separators=(",", ":")))
            return 0
        except Exception as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
    if args.command in {"bind", "update"}:
        try:
            binding = json.load(sys.stdin)
            if not isinstance(binding, dict) or binding.get("host") != args.host:
                raise ValueError("stdin binding host must match command host")
            if not binding.get("session_id") and args.host == "codex":
                binding["session_id"] = os.environ.get("CODEX_SESSION_ID", "")
            if not binding.get("session_id"):
                raise ValueError("session_id is required; Claude does not provide a verified shell binding ID")
            binding.setdefault("agent_id", f"{args.host}:{binding['session_id']}")
            if "pane_id" not in binding:
                binding["pane_id"] = TmuxBridge().id()
            binding.setdefault("cwd", os.getcwd())
            binding.setdefault("status", "ACTIVE")
            binding.setdefault("required_reports", [])
            binding.setdefault("approved_work", [])
            save_binding(_binding_path(root), binding, replace=args.command == "update")
            print(json.dumps({"registered": True, "host": args.host, "session_id": binding["session_id"]}))
            return 0
        except Exception as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
    if args.command == "send":
        try:
            request = json.load(sys.stdin)
            result = checked_send(request, TmuxBridge(), GuardStore(root / "delivery.sqlite3"))
            print(json.dumps(result, separators=(",", ":")))
            return 0
        except Exception as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
