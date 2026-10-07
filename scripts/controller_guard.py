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
# ponytail: fixed 15-minute approval window; refresh the explicit assignment if dispatch takes longer.
ASSIGNMENT_TTL_SECONDS = 900
SESSION_START_SOURCES = {"startup", "resume", "clear", "compact", "fork"}


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

    def get_inherited_record(self, key: tuple[str, str, str, str, str, str, str, str],
                             inherited_session_ids: list[str]) -> dict | None:
        for session_id in reversed(inherited_session_ids):
            with self._db() as db:
                rows = db.execute(
                    "SELECT * FROM delivery WHERE host=? AND session_id=? AND agent_id=? "
                    "AND task_id=? AND event_id=? AND candidate=? AND destination=? "
                    "ORDER BY updated_at DESC",
                    (key[0], session_id, f"{key[0]}:{session_id}", key[3], key[4], key[5], key[7]),
                ).fetchall()
            records = [dict(row) for row in rows]
            terminal = next((record for record in records
                             if record["status"] in {"SUBMITTED", "UNCONFIRMED", "BLOCKED"}), None)
            if terminal:
                return terminal
            if records:
                return records[0]
        return None

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

    def open_for_binding(self, host: str, session_id: str, agent_id: str, task_ids: list[str],
                         inherited_session_ids: list[str] | None = None) -> list[dict]:
        if not task_ids:
            return []
        session_ids = list(dict.fromkeys([session_id, *(inherited_session_ids or [])]))
        session_agents = [(value, agent_id if value == session_id else f"{host}:{value}")
                          for value in session_ids]
        identity_filter = " OR ".join("(session_id=? AND agent_id=?)" for _ in session_agents)
        task_placeholders = ",".join("?" for _ in task_ids)
        with self._db() as db:
            rows = db.execute(
                "SELECT task_id,event_id,candidate,destination,status FROM delivery "
                f"WHERE host=? AND ({identity_filter}) AND task_id IN ({task_placeholders}) "
                "AND status IN (?,?,?,?) ORDER BY updated_at",
                (host, *(value for pair in session_agents for value in pair), *task_ids, *OPEN_DELIVERIES),
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


def _message_header(line: str, sender: str):
    line = re.sub(r"^\s*(?:❯|›)\s*", "", line)
    match = re.match(r"^\[tmux-bridge from:[^\]]+ pane:([^\s\]]+) at:[^\]]+ — load the smux skill to reply\] ", line)
    return match if match and match.group(1) == sender else None


def _message_line(line: str, sender: str, text: str) -> bool:
    header = _message_header(line, sender)
    line = re.sub(r"^\s*(?:❯|›)\s*", "", line)
    return bool(header and line[header.end():] == text)


def _is_native_footer(line: str) -> bool:
    line = line.strip()
    return bool(
        line and set(line) == {"─"}
        or re.match(r"^(?:GPT-[^·]+|Claude [^·]+) · ", line)
        or re.match(r"^🤖 [^|]+ \| 💰 ", line)
        or re.match(r"^\[OMC#[^]]+\] -> .+ \| session:\S+$", line)
        or re.match(r"^\[OMC#[^]]+\] -> \d+\.\d+\.\d+ omc update$", line)
        or re.match(
            r"^\d+h:\d+%\* wk:\d+%\*\([^()]+\) extra:\d+%\*"
            r"\(\$[\d,.]+/\$[\d,.]+\) \| session:\d+m$",
            line,
        )
        or re.match(r"^← for agents · \? for shortcuts(?:\s+⚠ .+ · f\d+ to view)?$", line)
        or line in {
            "? for shortcuts", "+ Show details", "⏸ manual mode on",
            "⏸ manual mode on · ← for agents",
        }
        or re.match(r"^⚠ .+ · f\d+ to view$", line)
    )


def _footer_start(lines: list[str]) -> int:
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    start = end
    while start and _is_native_footer(lines[start - 1]):
        start -= 1
    return start if start < end else len(lines)


def _input_region(capture: str) -> tuple[list[str], int, list[str]] | None:
    lines = capture.splitlines()
    limit = _footer_start(lines)
    for index in range(limit - 1, -1, -1):
        if re.match(r"^\s*(?:❯|›)(?:\s|$)", lines[index]):
            return lines, index, lines[index + 1:limit]
    return None


def _prompt_bodies(line: str, continuation: list[str]) -> set[str]:
    first = re.sub(r"^\s*(?:❯|›)\s*", "", line).rstrip()
    parts = [first, *(part.strip() for part in continuation)]
    return {" ".join(parts).strip(), "".join(parts).strip()}


def _message_at(lines: list[str], index: int, sender: str, text: str, limit: int,
                *, allow_following_output: bool = False) -> bool:
    if index >= limit:
        return False
    header = _message_header(lines[index], sender)
    if not header:
        return False
    first = re.sub(r"^\s*(?:❯|›)\s*", "", lines[index])[header.end():].rstrip()
    positions = {0}
    for i, chunk in enumerate([first, *(line.strip() for line in lines[index + 1:limit])]):
        next_positions = set()
        separators = ("",) if i == 0 else ("", " ")
        for position in positions:
            for separator in separators:
                candidate = separator + chunk
                if text.startswith(candidate, position):
                    next_positions.add(position + len(candidate))
        positions = next_positions
        if not positions:
            return False
        if allow_following_output and len(text) in positions:
            return True
    return len(text) in positions


def _empty_prompt(line: str, continuation: list[str]) -> bool:
    return bool(_prompt_bodies(line, continuation) & {
        "", "Ask Codex to do anything", "Try …", 'Try "edit <filepath> to..."',
        'Try "fix lint errors"',
    })


def _has_active_draft(capture: str, sender: str, text: str) -> bool:
    lines = capture.splitlines()
    region = _input_region(capture)
    if region:
        lines, index, continuation = region
        return _message_at([lines[index], *continuation], 0, sender, text, len(continuation) + 1)
    return bool(lines and _message_line(lines[-1], sender, text))


def _has_partial_input(capture: str) -> bool:
    region = _input_region(capture)
    if not region:
        return False
    lines, index, continuation = region
    return not _empty_prompt(lines[index], continuation)


def _submitted(capture: str, before_enter: str, sender: str, text: str) -> bool:
    before_lines = [line.rstrip() for line in before_enter.splitlines()]
    after_lines = [line.rstrip() for line in capture.splitlines()]
    before_region = _input_region(before_enter)
    after_region = _input_region(capture)
    if not before_lines or not after_lines or not after_region:
        return False
    after_lines, after_prompt, after_continuation = after_region
    if not _empty_prompt(after_lines[after_prompt], after_continuation):
        return False
    if before_region:
        before_lines, before_prompt, before_continuation = before_region
        if not _message_at([before_lines[before_prompt], *before_continuation], 0,
                           sender, text, len(before_continuation) + 1):
            return False
    else:
        before_prompt = len(before_lines) - 1
        if not _message_at(before_lines, before_prompt, sender, text, len(before_lines)):
            return False
    history = before_lines[:before_prompt]
    if (
        re.match(r"^\s*❯(?:\s|$)", before_lines[before_prompt])
        and len(history) >= 2
        and len(history[-1].strip()) >= 20
        and set(history[-1].strip()) == {"─"}
        and re.fullmatch(r" +✔ Update installed · Restart to update", history[-2])
    ):
        history = history[:-2]
    while history and not history[-1].strip():
        history.pop()
    submitted = after_lines[:after_prompt]
    if submitted[:len(history)] != history:
        return False
    message_index = len(history)
    while message_index < len(submitted) and not submitted[message_index].strip():
        message_index += 1
    return message_index < len(submitted) and _message_at(
        submitted, message_index, sender, text, len(submitted), allow_following_output=True,
    )


def _read_hash(capture: str) -> str:
    return hashlib.sha256(capture.encode("utf-8")).hexdigest()


def checked_send(request: dict, bridge, store: GuardStore, settle=lambda: time.sleep(0.35),
                 inherited_session_ids: list[str] | None = None) -> dict:
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
        if current is None and inherited_session_ids:
            current = store.get_inherited_record(key, inherited_session_ids)
            if current:
                return {"status": current["status"], "duplicate": True}
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
                settle()
                try:
                    after_type = bridge.read(target_id)
                except Exception:
                    after_type = ""
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
                settle()
                bridge.read(target_id)
            except Exception:
                pass
            store.put_record({**current, "status": "UNCONFIRMED"})
            return {"status": "UNCONFIRMED", "reason": "Enter may have been sent; do not retry this event"}

        try:
            settle()
            after_enter = bridge.read(target_id)
        except Exception:
            store.put_record({**current, "status": "UNCONFIRMED"})
            return {"status": "UNCONFIRMED", "reason": "post-Enter read failed; do not retry this event"}
        before_enter = before if current["status"] == "TYPED" else after_type
        status = "SUBMITTED" if _submitted(after_enter, before_enter, sender, text) else "UNCONFIRMED"
        store.put_record({**current, "status": status})
        return {"status": status, "reason": None if status == "SUBMITTED" else "post-Enter result is ambiguous; do not retry this event"}


def _state_read(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "bindings": [], "assignment": None, "receipts": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("bindings"), list):
        raise ValueError("state must contain version 1 and a bindings list")
    state.setdefault("assignment", None)
    state.setdefault("receipts", [])
    if not isinstance(state["receipts"], list):
        raise ValueError("state receipts must be a list")
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


@contextlib.contextmanager
def _state_lock(state_file: Path):
    lock_path = state_file.with_name(state_file.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _assignment_digest(assignment: dict) -> str:
    fields = ("approved", "assignment_id", "host", "role", "task_id", "pane_id", "cwd",
              "required_reports", "approved_work", "issued_at", "fork_parent_session_id")
    identity = {key: assignment[key] for key in fields if key in assignment}
    return digest(json.dumps(identity, sort_keys=True, separators=(",", ":")))


def _valid_assignment(assignment: dict) -> bool:
    required = ("assignment_id", "host", "role", "task_id", "pane_id", "cwd")
    if assignment.get("approved") is not True or any(
        not isinstance(assignment.get(key), str) or not assignment[key]
        or any(char in assignment[key] for char in "\0\r\n")
        for key in required
    ):
        return False
    if (
        assignment["host"] not in {"codex", "claude"}
        or assignment["role"] not in {"worker", "gate"}
        or not re.fullmatch(r"%[0-9]+", assignment["pane_id"])
        or not Path(assignment["cwd"]).is_absolute()
        or not isinstance(assignment.get("issued_at"), (int, float))
        or isinstance(assignment["issued_at"], bool)
    ):
        return False
    if not isinstance(assignment.get("required_reports"), list) or not isinstance(assignment.get("approved_work"), list):
        return False
    parent_session_id = assignment.get("fork_parent_session_id")
    if parent_session_id is not None and (
        not isinstance(parent_session_id, str) or not parent_session_id
        or any(char in parent_session_id for char in "\0\r\n")
    ):
        return False
    if any(not isinstance(path, str) or not path or any(char in path for char in "\0\r\n")
           or Path(path).is_absolute() or ".." in Path(path).parts
           for path in assignment["required_reports"]):
        return False
    work = assignment["approved_work"]
    if not work or any(not isinstance(entry, dict) or set(entry) != {"id", "status"}
                       or not isinstance(entry.get("id"), str)
                       or not entry["id"] or any(char in entry["id"] for char in "\0\r\n")
                       or not isinstance(entry.get("status"), str) or entry["status"] not in
                       {"eligible", "pending", "in_progress", "complete"} for entry in work):
        return False
    return all(entry["id"] == assignment["task_id"] for entry in work)


def approve_assignment(state_file: Path, assignment: dict) -> dict:
    allowed = {"approved", "assignment_id", "host", "role", "task_id", "pane_id", "cwd",
               "required_reports", "approved_work", "fork_parent_session_id"}
    if not isinstance(assignment, dict) or set(assignment) - allowed:
        raise ValueError("assignment contains unsupported fields")
    issued_at = time.time()
    if not _valid_assignment({**assignment, "issued_at": issued_at}):
        raise ValueError("assignment must explicitly approve a valid host, role, task, pane, cwd, reports, and approved work")
    prepared = {**assignment, "cwd": str(Path(assignment["cwd"]).resolve()), "issued_at": issued_at}
    if not _valid_assignment(prepared):
        raise ValueError("assignment cwd must resolve to a valid local directory")
    try:
        if not Path(prepared["cwd"]).is_dir():
            raise ValueError("assignment cwd must be an existing directory")
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError("assignment cwd must resolve to a valid local directory") from exc
    with _state_lock(state_file):
        state = _state_read(state_file)
        current = state.get("assignment")
        current_age = time.time() - current["issued_at"] if isinstance(current, dict) and _valid_assignment(current) else None
        if (isinstance(current, dict) and not current.get("consumed_by") and current_age is not None
                and 0 <= current_age < ASSIGNMENT_TTL_SECONDS):
            raise ValueError("an unconsumed approved assignment already exists")
        state["assignment"] = prepared
        _atomic_json(state_file, state)
    return {"approved": True, "assignment_id": prepared["assignment_id"],
            "assignment_sha256": _assignment_digest(prepared)}


def _receipt_matches(state: dict, host: str, session_id: str, cwd: str, pane_id: str) -> dict | None:
    receipts = [r for r in state["receipts"] if isinstance(r, dict)
                and r.get("host") == host and r.get("session_id") == session_id]
    bindings = [b for b in state["bindings"] if isinstance(b, dict)
                and b.get("host") == host and b.get("session_id") == session_id]
    if len(receipts) != 1 or len(bindings) != 1:
        return None
    receipt, binding = receipts[0], bindings[0]
    if (
        receipt.get("registered") is not True
        or receipt.get("host") != host
        or receipt.get("session_id") != session_id
        or receipt.get("agent_id") != f"{host}:{session_id}"
        or receipt.get("pane_id") != pane_id
        or binding.get("pane_id") != pane_id
        or receipt.get("cwd") != cwd
        or binding.get("cwd") != cwd
        or not _valid_binding(binding, host, session_id)
        or binding.get("role") not in {"worker", "gate"}
        or not isinstance(binding.get("task_id"), str)
        or not binding.get("task_id")
        or not isinstance(binding.get("assignment_id"), str)
        or not binding.get("assignment_id")
        or not isinstance(binding.get("assignment_sha256"), str)
        or not HASH_RE.fullmatch(binding["assignment_sha256"])
        or receipt.get("role") != binding.get("role")
        or receipt.get("task_id") != binding.get("task_id")
        or receipt.get("assignment_sha256") != binding.get("assignment_sha256")
        or not isinstance(receipt.get("assignment_sha256"), str)
        or not HASH_RE.fullmatch(receipt["assignment_sha256"])
        or receipt.get("assignment_id") != binding.get("assignment_id")
        or receipt.get("source") not in {"startup", "clear", "fork"}
        or not isinstance(receipt.get("registered_at"), (int, float))
    ):
        return None
    return receipt


def register_session_start(host: str, payload: dict, state_file: Path, bridge: TmuxBridge) -> dict | None:
    session_id, cwd, source = payload.get("session_id"), payload.get("cwd"), payload.get("source")
    if (host not in {"codex", "claude"} or payload.get("hook_event_name") != "SessionStart"
            or not isinstance(session_id, str) or not session_id or any(char in session_id for char in "\0\r\n")
            or not isinstance(cwd, str) or not cwd or any(char in cwd for char in "\0\r\n") or not Path(cwd).is_absolute()
            or source not in SESSION_START_SOURCES):
        return None
    try:
        cwd = str(Path(cwd).resolve())
        if not Path(cwd).is_dir():
            return None
        pane_id = bridge.id()
    except (OSError, ValueError, RuntimeError):
        return None
    if not re.fullmatch(r"%[0-9]+", pane_id):
        return None

    with _state_lock(state_file):
        state = _state_read(state_file)
        existing = _receipt_matches(state, host, session_id, cwd, pane_id)
        if existing:
            return existing
        if any(isinstance(b, dict) and b.get("host") == host and b.get("session_id") == session_id
               for b in state["bindings"]):
            return None
        if source not in {"startup", "clear", "fork"}:
            return None
        assignment = state.get("assignment")
        if not isinstance(assignment, dict) or not _valid_assignment(assignment):
            return None
        assignment_age = time.time() - assignment["issued_at"]
        if (assignment.get("consumed_by") or assignment["host"] != host
                or assignment["cwd"] != cwd or assignment["pane_id"] != pane_id
                or not 0 <= assignment_age < ASSIGNMENT_TTL_SECONDS):
            return None

        if source == "fork":
            parent_id = assignment.get("fork_parent_session_id")
            parents = [b for b in state["bindings"] if isinstance(b, dict)
                       and b.get("host") == host and b.get("session_id") == parent_id]
            if len(parents) != 1:
                return None
            parent = parents[0]
            if (not _receipt_matches(state, host, parent_id, parent.get("cwd"), parent.get("pane_id"))
                    or assignment["assignment_id"] == parent.get("assignment_id")
                    or assignment["cwd"] != parent.get("cwd")
                    or any(assignment[key] != parent.get(key) for key in
                           ("role", "task_id", "required_reports", "approved_work"))):
                return None
            inherited_sessions = parent.get("inherited_session_ids", [])
            if (not isinstance(inherited_sessions, list)
                    or any(not isinstance(value, str) or not value for value in inherited_sessions)):
                return None
            binding = {
                **parent,
                "session_id": session_id,
                "agent_id": f"{host}:{session_id}",
                "pane_id": pane_id,
                "assignment_id": assignment["assignment_id"],
                "assignment_sha256": _assignment_digest(assignment),
                "fork_parent_session_id": parent_id,
                "inherited_session_ids": list(dict.fromkeys([*inherited_sessions, parent_id])),
            }
        else:
            if assignment.get("fork_parent_session_id") is not None:
                return None
            binding = {
                "host": host,
                "session_id": session_id,
                "agent_id": f"{host}:{session_id}",
                "pane_id": pane_id,
                "cwd": cwd,
                "role": assignment["role"],
                "task_id": assignment["task_id"],
                "assignment_id": assignment["assignment_id"],
                "assignment_sha256": _assignment_digest(assignment),
                "status": "ACTIVE" if assignment["role"] == "worker" else "AWAITING_EVENT",
                "required_reports": assignment["required_reports"],
                "approved_work": assignment["approved_work"],
            }
        assignment_sha256 = _assignment_digest(assignment)
        receipt = {
            "registered": True,
            "host": host,
            "session_id": session_id,
            "agent_id": binding["agent_id"],
            "role": binding["role"],
            "task_id": binding["task_id"],
            "assignment_id": binding["assignment_id"],
            "assignment_sha256": assignment_sha256,
            "pane_id": pane_id,
            "cwd": cwd,
            "source": source,
            "registered_at": time.time(),
        }
        state["bindings"].append(binding)
        state["receipts"].append(receipt)
        assignment["consumed_by"] = session_id
        _atomic_json(state_file, state)
        return receipt


def verify_receipt(state_file: Path, host: str, session_id: str, assignment_id: str) -> dict | None:
    state = _state_read(state_file)
    matches = [r for r in state["receipts"] if isinstance(r, dict)
               and r.get("host") == host and r.get("session_id") == session_id
               and r.get("assignment_id") == assignment_id]
    if len(matches) != 1:
        return None
    receipt = matches[0]
    return receipt if _receipt_matches(state, host, session_id, receipt.get("cwd"), receipt.get("pane_id")) == receipt else None


def save_binding(state_file: Path, binding: dict, replace: bool = False) -> None:
    incoming = dict(binding)
    with _state_lock(state_file):
        state = _state_read(state_file)
        entries = state["bindings"]
        index = next((i for i, old in enumerate(entries) if old.get("host") == incoming.get("host")
                      and old.get("session_id") == incoming.get("session_id")), None)
        if index is not None and not replace:
            raise ValueError("session binding already exists; use update")
        old = entries[index] if index is not None else None
        binding = {**old, **incoming} if old is not None else incoming

        required = ("host", "session_id", "agent_id", "pane_id", "cwd", "status")
        if any(not isinstance(binding.get(k), str) or not binding[k] or "\0" in binding[k] for k in required):
            raise ValueError("binding requires host, session_id, agent_id, pane_id, cwd, and status")
        if (
            binding["host"] not in {"codex", "claude"}
            or binding["agent_id"] != f"{binding['host']}:{binding['session_id']}"
            or not re.fullmatch(r"%[0-9]+", binding["pane_id"])
        ):
            raise ValueError("agent_id must equal '<host>:<session_id>' and pane_id must be a tmux pane ID")
        if not isinstance(binding.get("required_reports"), list) or not isinstance(binding.get("approved_work"), list):
            raise ValueError("required_reports and approved_work must be lists")
        if any(not isinstance(p, str) or not p or "\0" in p or Path(p).is_absolute() or ".." in Path(p).parts for p in binding["required_reports"]):
            raise ValueError("required report paths must stay inside the bound cwd")
        if any(not isinstance(w, dict) or not isinstance(w.get("id"), str) or not isinstance(w.get("status"), str) for w in binding["approved_work"]):
            raise ValueError("approved work entries require id and status")
        if old is None:
            entries.append(binding)
        else:
            if old.get("agent_id") != binding["agent_id"] or old.get("pane_id") != binding["pane_id"] or old.get("cwd") != binding["cwd"]:
                raise ValueError("update cannot change the bound agent, pane, or cwd identity")
            for key in ("role", "task_id", "assignment_id", "assignment_sha256", "fork_parent_session_id",
                        "inherited_session_ids"):
                if key in incoming and incoming[key] != old.get(key):
                    raise ValueError("update cannot change the bound task assignment")
            if old.get("task_id") and any(work["id"] != old["task_id"] for work in binding["approved_work"]):
                raise ValueError("update cannot add another task to an assigned session")
            if old.get("task_id") and not binding["approved_work"] and binding["status"] != "COMPLETE":
                raise ValueError("update cannot remove assigned work before completion")
            if "review_history" in incoming:
                previous, updated = old.get("review_history", []), incoming["review_history"]
                if (not isinstance(previous, list) or not isinstance(updated, list)
                        or any(not isinstance(item, str) for item in previous + updated)
                        or updated[:len(previous)] != previous):
                    raise ValueError("update cannot remove or rewrite review history")
            if "gate_verdicts" in binding:
                updated = binding["gate_verdicts"]
                if (not isinstance(updated, int) or isinstance(updated, bool) or updated < 0
                        or (binding.get("role") == "gate" and updated > 3)):
                    raise ValueError("update cannot reset or exceed the gate verdict limit")
                if "gate_verdicts" in old:
                    previous = old["gate_verdicts"]
                    if (not isinstance(previous, int) or isinstance(previous, bool)
                            or updated < previous):
                        raise ValueError("update cannot reset or exceed the gate verdict limit")
            entries[index] = binding
        _atomic_json(state_file, state)


def _valid_binding(binding: dict, host: str, session_id: str) -> bool:
    required_text = ("host", "session_id", "agent_id", "pane_id", "cwd", "status")
    if any(not isinstance(binding.get(key), str) or not binding[key] or "\0" in binding[key] for key in required_text):
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
    if any(not isinstance(p, str) or not p or "\0" in p or Path(p).is_absolute() or ".." in Path(p).parts for p in binding["required_reports"]):
        return False
    if any(
        not isinstance(work, dict)
        or not isinstance(work.get("id"), str)
        or not work.get("id")
        or not isinstance(work.get("status"), str)
        for work in binding["approved_work"]
    ):
        return False
    inherited = binding.get("inherited_session_ids", [])
    if (not isinstance(inherited, list)
            or any(not isinstance(value, str) or not value or value == session_id
                   or any(char in value for char in "\0\r\n") for value in inherited)
            or len(set(inherited)) != len(inherited)):
        return False
    parent_id = binding.get("fork_parent_session_id")
    if parent_id is not None and (
        not isinstance(parent_id, str) or not parent_id or parent_id == session_id
        or any(char in parent_id for char in "\0\r\n")
    ):
        return False
    history = binding.get("review_history", [])
    if not isinstance(history, list) or any(not isinstance(item, str) for item in history):
        return False
    gate_verdicts = binding.get("gate_verdicts", 0)
    if (not isinstance(gate_verdicts, int) or isinstance(gate_verdicts, bool) or gate_verdicts < 0
            or (binding.get("role") == "gate" and gate_verdicts > 3)):
        return False
    return True


def _binding_repair(host: str, session_id: str, store: GuardStore) -> dict:
    reason = "Controller guard session binding or path is malformed or unreadable. Repair it before the next turn."
    first = store.mark_stop_reason(host, session_id, digest(host + ":" + session_id + ":bad-binding"))
    return {"decision": "block", "reason": reason} if first else {"decision": "allow"}


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
        return _binding_repair(host, session_id, store)
    try:
        identity_matches = os.path.realpath(cwd) == os.path.realpath(binding["cwd"])
    except (OSError, ValueError, RuntimeError):
        return _binding_repair(host, session_id, store)
    if not identity_matches:
        reason = "Controller guard session identity does not match its registered agent and cwd. Repair the binding."
        first = store.mark_stop_reason(host, session_id, digest(host + ":" + session_id + ":identity"))
        return {"decision": "block", "reason": reason} if first else {"decision": "allow"}
    if binding.get("status") in ALLOW_STOP:
        return {"decision": "allow"}

    reasons = []
    try:
        root = Path(binding["cwd"]).resolve()
        for report in binding["required_reports"]:
            report_path = (root / report).resolve()
            if root not in report_path.parents:
                reasons.append("invalid-report-binding")
            elif not report_path.is_file():
                reasons.append("missing-report:" + report)
    except (OSError, ValueError, RuntimeError):
        return _binding_repair(host, session_id, store)
    bound_tasks = [work["id"] for work in binding["approved_work"]]
    unfinished = store.open_for_binding(
        host, session_id, binding["agent_id"], bound_tasks, binding.get("inherited_session_ids", []),
    )
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


def _session_start(host: str, root: Path) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be an object")
        receipt = register_session_start(host, payload, _binding_path(root), TmuxBridge())
    except Exception:
        receipt = None
    if receipt:
        context = ("Controller guard binding registered: "
                   f"host={host} session={receipt['session_id']} task={receipt['task_id']} "
                   f"assignment_sha256={receipt['assignment_sha256']}")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": context,
        }}, separators=(",", ":")))
    else:
        print('{}')
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
    session_start = commands.add_parser("session-start")
    session_start.add_argument("host", choices=("codex", "claude"))
    assign = commands.add_parser("assign")
    assign.add_argument("host", choices=("codex", "claude"))
    receipt = commands.add_parser("receipt")
    receipt.add_argument("host", choices=("codex", "claude"))
    receipt.add_argument("session_id")
    receipt.add_argument("assignment_id")
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
    if args.command == "session-start":
        return _session_start(args.host, root)
    if args.command == "assign":
        try:
            assignment = json.load(sys.stdin)
            if not isinstance(assignment, dict) or assignment.get("host") != args.host:
                raise ValueError("stdin assignment host must match command host")
            print(json.dumps(approve_assignment(_binding_path(root), assignment), separators=(",", ":")))
            return 0
        except Exception as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
    if args.command == "receipt":
        try:
            found = verify_receipt(_binding_path(root), args.host, args.session_id, args.assignment_id)
            if not found:
                print(json.dumps({"registered": False}, separators=(",", ":")))
                return 1
            print(json.dumps(found, separators=(",", ":")))
            return 0
        except Exception as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
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
            if args.command == "bind":
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
            state = _state_read(_binding_path(root))
            matches = [binding for binding in state["bindings"] if isinstance(binding, dict)
                       and binding.get("host") == request.get("host")
                       and binding.get("session_id") == request.get("session_id")]
            inherited = []
            if len(matches) == 1:
                binding = matches[0]
                if (_valid_binding(binding, request.get("host"), request.get("session_id"))
                        and request.get("agent_id") == binding["agent_id"]
                        and request.get("task_id") in [work["id"] for work in binding["approved_work"]]):
                    inherited = binding.get("inherited_session_ids", [])
            result = checked_send(request, TmuxBridge(), GuardStore(root / "delivery.sqlite3"),
                                  inherited_session_ids=inherited)
            print(json.dumps(result, separators=(",", ":")))
            return 0
        except Exception as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
