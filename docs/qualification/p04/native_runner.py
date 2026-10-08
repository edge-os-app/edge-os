"""Durable local fixtures and an exact-resource Docker policy for P04 qualification.

This module is a qualification harness. It is not application authentication, storage, or a
production Hermes integration.
"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path


class AttemptState(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class FixtureStore:
    """SQLite-backed owner/agent fixture used to prepare task-local read snapshots."""

    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    owner_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL UNIQUE,
                    PRIMARY KEY (owner_id, agent_id)
                );
                CREATE TABLE IF NOT EXISTS memories (
                    owner_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    entries_json TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    PRIMARY KEY (owner_id, agent_id),
                    FOREIGN KEY (owner_id, agent_id) REFERENCES agents(owner_id, agent_id)
                );
                CREATE TABLE IF NOT EXISTS sources (
                    owner_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    ref TEXT NOT NULL,
                    content TEXT NOT NULL,
                    PRIMARY KEY (owner_id, agent_id, source_id),
                    FOREIGN KEY (owner_id, agent_id) REFERENCES agents(owner_id, agent_id)
                );
                CREATE TABLE IF NOT EXISTS streams (
                    owner_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    chunk TEXT NOT NULL,
                    PRIMARY KEY (owner_id, agent_id, job_id, sequence),
                    FOREIGN KEY (owner_id, agent_id) REFERENCES agents(owner_id, agent_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=5, isolation_level="IMMEDIATE")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def create_agent(self, owner_id: str, agent_id: str) -> None:
        if not owner_id.strip() or not agent_id.strip():
            raise ValueError("owner and agent IDs are required")
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO agents(owner_id, agent_id) VALUES (?, ?)", (owner_id, agent_id)
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("agent already exists or belongs to another owner") from exc

    def _require_agent(self, connection: sqlite3.Connection, owner_id: str, agent_id: str) -> None:
        row = connection.execute(
            "SELECT 1 FROM agents WHERE owner_id=? AND agent_id=?", (owner_id, agent_id)
        ).fetchone()
        if row is None:
            raise PermissionError("agent is not owned by this principal")

    def add_source(
        self, owner_id: str, agent_id: str, source_id: str, ref: str, content: str
    ) -> None:
        if not all(value.strip() for value in (owner_id, agent_id, source_id, ref, content)):
            raise ValueError("source identity, reference and content are required")
        if not ref.startswith("fixture://"):
            raise ValueError("qualification source refs must use the fixture scheme")
        if len(ref.encode("utf-8")) > 2048 or len(content.encode("utf-8")) > 131_072:
            raise ValueError("qualification source exceeds its local fixture size limit")
        with self._connect() as connection:
            self._require_agent(connection, owner_id, agent_id)
            connection.execute(
                "INSERT INTO sources(owner_id, agent_id, source_id, ref, content) VALUES (?, ?, ?, ?, ?)",
                (owner_id, agent_id, source_id, ref, content),
            )

    def set_memory(
        self, owner_id: str, agent_id: str, entries: list[str], source_refs: list[str]
    ) -> int:
        if not isinstance(entries, list) or not all(isinstance(item, str) and item.strip() for item in entries):
            raise ValueError("memory entries must be nonempty strings")
        if not isinstance(source_refs, list) or not all(isinstance(item, str) and item.strip() for item in source_refs):
            raise ValueError("source refs must be nonempty strings")
        if len(entries) > 32 or any(len(item.encode("utf-8")) > 2048 for item in entries):
            raise ValueError("memory exceeds its entry count or per-entry byte limit")
        if len(source_refs) > 8:
            raise ValueError("memory exceeds its source-reference limit")
        encoded_memory = json.dumps(
            {"owner_id": owner_id, "agent_id": agent_id, "entries": entries, "source_refs": source_refs},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        if len(encoded_memory) > 16_384:
            raise ValueError("memory exceeds the 16 KiB local fixture limit")
        with self._connect() as connection:
            self._require_agent(connection, owner_id, agent_id)
            for source_id in source_refs:
                source = connection.execute(
                    "SELECT 1 FROM sources WHERE owner_id=? AND agent_id=? AND source_id=?",
                    (owner_id, agent_id, source_id),
                ).fetchone()
                if source is None:
                    raise PermissionError("source reference is not owned by this agent")
            existing = connection.execute(
                "SELECT version FROM memories WHERE owner_id=? AND agent_id=?", (owner_id, agent_id)
            ).fetchone()
            version = (int(existing["version"]) if existing else 0) + 1
            memory_record = {
                "schema": "edge-agent-context/1",
                "owner_id": owner_id,
                "agent_id": agent_id,
                "version": version,
                "enabled": True,
                "entries": [
                    {"text": item, "source_refs": source_refs} for item in entries
                ],
            }
            if len(json.dumps(
                memory_record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")) > 16_384:
                raise ValueError("canonical memory record exceeds the 16 KiB local fixture limit")
            connection.execute(
                """INSERT INTO memories(owner_id, agent_id, version, enabled, entries_json, source_refs_json)
                   VALUES (?, ?, ?, 1, ?, ?)
                   ON CONFLICT(owner_id, agent_id) DO UPDATE SET version=excluded.version, enabled=1,
                     entries_json=excluded.entries_json, source_refs_json=excluded.source_refs_json""",
                (owner_id, agent_id, version, json.dumps(entries), json.dumps(source_refs)),
            )
            return version

    def clear_memory(self, owner_id: str, agent_id: str) -> int:
        with self._connect() as connection:
            self._require_agent(connection, owner_id, agent_id)
            existing = connection.execute(
                "SELECT version FROM memories WHERE owner_id=? AND agent_id=?", (owner_id, agent_id)
            ).fetchone()
            version = (int(existing["version"]) if existing else 0) + 1
            connection.execute(
                """INSERT INTO memories(owner_id, agent_id, version, enabled, entries_json, source_refs_json)
                   VALUES (?, ?, ?, 0, '[]', '[]')
                   ON CONFLICT(owner_id, agent_id) DO UPDATE SET version=excluded.version, enabled=0,
                     entries_json='[]', source_refs_json='[]'""",
                (owner_id, agent_id, version),
            )
            return version

    def task_context(self, owner_id: str, agent_id: str) -> dict:
        with self._connect() as connection:
            self._require_agent(connection, owner_id, agent_id)
            memory = connection.execute(
                "SELECT version, enabled, entries_json, source_refs_json FROM memories WHERE owner_id=? AND agent_id=?",
                (owner_id, agent_id),
            ).fetchone()
            if memory is None:
                memory_data = {"version": 0, "enabled": False, "entries": []}
                source_refs: list[str] = []
            elif not memory["enabled"]:
                memory_data = {"version": int(memory["version"]), "enabled": False, "entries": []}
                source_refs = []
            else:
                memory_data = {
                    "version": int(memory["version"]), "enabled": True,
                    "entries": json.loads(memory["entries_json"]),
                }
                source_refs = json.loads(memory["source_refs_json"])
            sources = []
            for source_id in source_refs:
                row = connection.execute(
                    """SELECT source_id, ref, content FROM sources
                       WHERE owner_id=? AND agent_id=? AND source_id=?""",
                    (owner_id, agent_id, source_id),
                ).fetchone()
                if row is None:
                    raise PermissionError("memory points to a source outside this agent scope")
                sources.append(dict(row))
            return {
                "owner_id": owner_id,
                "agent_id": agent_id,
                "memory": memory_data,
                "sources": sources,
            }

    def append_stream_chunk(
        self, owner_id: str, agent_id: str, job_id: str, sequence: int, chunk: str
    ) -> None:
        if not job_id.strip() or sequence < 0 or not chunk:
            raise ValueError("stream identity, sequence and chunk are required")
        with self._connect() as connection:
            self._require_agent(connection, owner_id, agent_id)
            connection.execute(
                "INSERT INTO streams(owner_id, agent_id, job_id, sequence, chunk) VALUES (?, ?, ?, ?, ?)",
                (owner_id, agent_id, job_id, sequence, chunk),
            )

    def read_stream(self, owner_id: str, agent_id: str, job_id: str) -> list[str]:
        with self._connect() as connection:
            self._require_agent(connection, owner_id, agent_id)
            rows = connection.execute(
                """SELECT chunk FROM streams WHERE owner_id=? AND agent_id=? AND job_id=?
                   ORDER BY sequence""",
                (owner_id, agent_id, job_id),
            ).fetchall()
            if not rows:
                raise PermissionError("stream is not available to this agent")
            return [row["chunk"] for row in rows]


class QualificationLedger:
    """Durable local attempt/reservation fixture; not a production billing system."""

    def __init__(self, database: Path, *, total_budget_usd: str) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.total_budget = self._money(total_budget_usd)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    job_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    request_key TEXT NOT NULL,
                    prompt_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    dispatch_count INTEGER NOT NULL,
                    UNIQUE(owner_id, agent_id, request_key)
                );
                CREATE TABLE IF NOT EXISTS usage (
                    job_id TEXT PRIMARY KEY REFERENCES attempts(job_id),
                    reserved_usd TEXT NOT NULL,
                    state TEXT NOT NULL,
                    actual_usd TEXT,
                    actual_tokens INTEGER
                );
                """
            )

    @staticmethod
    def _money(value: str | Decimal) -> Decimal:
        try:
            amount = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("money amount is invalid") from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError("money amount must be finite and nonnegative")
        rounded = amount.quantize(Decimal("0.01"))
        if rounded != amount:
            raise ValueError("money amount must be expressed in whole cents")
        return rounded

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=5, isolation_level="IMMEDIATE")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def reserve_and_start(
        self, *, owner_id: str, agent_id: str, request_key: str,
        prompt_sha256: str, reserve_usd: str,
    ) -> tuple[str, bool]:
        if not all(item.strip() for item in (owner_id, agent_id, request_key, prompt_sha256)):
            raise ValueError("attempt identity and prompt hash are required")
        reserve = self._money(reserve_usd)
        if reserve <= 0:
            raise ValueError("positive usage reservation required")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(
                "SELECT job_id, prompt_sha256 FROM attempts WHERE owner_id=? AND agent_id=? AND request_key=?",
                (owner_id, agent_id, request_key),
            ).fetchone()
            if old:
                if old["prompt_sha256"] != prompt_sha256:
                    raise ValueError("idempotency key reused for a different prompt")
                return old["job_id"], False
            active = connection.execute(
                "SELECT reserved_usd FROM usage WHERE state IN ('RESERVED', 'UNKNOWN')"
            ).fetchall()
            reserved = sum((Decimal(row["reserved_usd"]) for row in active), Decimal("0"))
            if reserved + reserve > self.total_budget:
                raise ValueError("usage reservation exceeds the P04 task ceiling")
            job_id = uuid.uuid4().hex
            connection.execute(
                "INSERT INTO attempts VALUES (?, ?, ?, ?, ?, 'RUNNING', 1)",
                (job_id, owner_id, agent_id, request_key, prompt_sha256),
            )
            connection.execute(
                "INSERT INTO usage(job_id, reserved_usd, state) VALUES (?, ?, 'RESERVED')",
                (job_id, str(reserve)),
            )
            return job_id, True

    def recover_running(self) -> list[tuple[str, AttemptState]]:
        recovered: list[tuple[str, AttemptState]] = []
        with self._connect() as connection:
            rows = connection.execute("SELECT job_id FROM attempts WHERE state='RUNNING'").fetchall()
            for row in rows:
                job_id = row["job_id"]
                connection.execute("UPDATE attempts SET state='INTERRUPTED' WHERE job_id=?", (job_id,))
                connection.execute("UPDATE usage SET state='UNKNOWN' WHERE job_id=? AND state='RESERVED'", (job_id,))
                recovered.append((job_id, AttemptState.INTERRUPTED))
        return recovered

    @property
    def reserved_usd(self) -> str:
        with self._connect() as connection:
            rows = connection.execute("SELECT reserved_usd FROM usage WHERE state IN ('RESERVED', 'UNKNOWN')").fetchall()
        return str(sum((Decimal(row["reserved_usd"]) for row in rows), Decimal("0.00")))

    def state(self, job_id: str) -> AttemptState:
        with self._connect() as connection:
            row = connection.execute("SELECT state FROM attempts WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return AttemptState(row["state"])

    def usage_state(self, job_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute("SELECT state FROM usage WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return row["state"]

    def dispatch_count(self, job_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT dispatch_count FROM attempts WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return int(row["dispatch_count"])

    def dispatch_count_by_owner(self, owner_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COALESCE(SUM(dispatch_count), 0) AS total FROM attempts WHERE owner_id=?", (owner_id,)).fetchone()
        return int(row["total"])


@dataclass(frozen=True)
class DockerPolicy:
    run_id: str

    def __post_init__(self) -> None:
        if not self.run_id.strip() or any(char.isspace() for char in self.run_id):
            raise ValueError("run ID must be a nonempty Docker-label value")

    def run_argv(
        self, *, image: str, name: str, input_path: str, output_path: str
    ) -> list[str]:
        """Build a disposable, full-process container with only scoped task mounts."""
        return [
            "docker", "run", "--rm", "--name", name,
            "--label", f"edge-os.test.run={self.run_id}",
            "--network=none", "--read-only", "--memory=512m", "--memory-swap=512m",
            "--cpus=1", "--pids-limit=64", "--cap-drop=ALL",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--security-opt=no-new-privileges",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--mount", f"type=bind,src={input_path},dst=/qualification/input.json,readonly",
            "--mount", f"type=bind,src={output_path},dst=/qualification/output",
            "--env", f"HOME=/tmp/{name}/home", "--env", f"HERMES_HOME=/tmp/{name}/hermes-home",
            "--env", f"XDG_CONFIG_HOME=/tmp/{name}/config",
            "--env", f"XDG_CACHE_HOME=/tmp/{name}/cache",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            image,
        ]


PINNED_HERMES = "54bc5e509c985f37265c3d416bd2c64b10fc77ba"
WORKSPACE = Path(__file__).resolve().parents[3]
HERMES_SOURCE = Path("/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent")


def _docker(*args: str, timeout: int = 30) -> str:
    result = subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip()


def _source_identity(source: Path) -> dict:
    commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if commit != PINNED_HERMES or status:
        raise RuntimeError("pinned Hermes checkout identity or cleanliness check failed")
    pyproject = hashlib.sha256((source / "pyproject.toml").read_bytes()).hexdigest()
    lockfile = hashlib.sha256((source / "uv.lock").read_bytes()).hexdigest()
    return {
        "commit": commit,
        "clean": True,
        "pyproject_sha256": pyproject,
        "uv_lock_sha256": lockfile,
        "container_base": "python:3.14-slim-trixie@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2",
    }


def _build_context(source: Path, context: Path) -> None:
    checkout = context / "hermes-agent"
    checkout.mkdir()
    with subprocess.Popen(
        ["git", "-C", str(source), "archive", "--format=tar", PINNED_HERMES],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as process:
        assert process.stdout is not None
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            archive.extractall(checkout, filter="data")
        stderr = process.stderr.read() if process.stderr else b""
        status = process.wait(timeout=30)
        if status:
            raise RuntimeError(f"git archive failed ({status}): {stderr.decode(errors='replace')[:500]}")
    shutil.copy2(Path(__file__).with_name("Dockerfile"), context / "Dockerfile")
    shutil.copy2(Path(__file__).with_name("container_probe.py"), context / "container_probe.py")


def _docker_resources(run_id: str) -> list[str]:
    raw = _docker("ps", "-aq", "--filter", f"label=edge-os.test.run={run_id}")
    return [line for line in raw.splitlines() if line]


def _validate_container_result(result: dict, *, allow_failed: bool = False) -> None:
    sandbox = result["sandbox"]
    if not sandbox["filesystem"]["input_mount_read_only"] or not sandbox["filesystem"]["root_filesystem_read_only"]:
        raise AssertionError("container root or input filesystem was writable")
    if not sandbox["filesystem"]["other_job_input_unmounted"] or not sandbox["filesystem"]["other_job_output_unmounted"]:
        raise AssertionError("another task's mount path is visible")
    if not sandbox["filesystem"]["task_cache_private_marker"]:
        raise AssertionError("task-local cache marker did not persist")
    if not sandbox["filesystem"]["forbidden_owner_memory_not_in_task_context"] or not sandbox["filesystem"]["forbidden_owner_source_not_in_task_context"]:
        raise AssertionError("another owner's fixture data appears in this task context")
    if sandbox["filesystem"]["host_or_docker_mounts_present"]:
        raise AssertionError("host or Docker socket mount is visible")
    if sandbox["filesystem"]["provider_secret_env_names_present"]:
        raise AssertionError("provider credential environment is present in local fake run")
    if not sandbox["network"]["blocked"]:
        raise AssertionError("whole-process container egress check unexpectedly connected")
    if sandbox["cgroup"]["memory_max"] != str(512 * 1024 * 1024):
        raise AssertionError(f"unexpected cgroup memory limit: {sandbox['cgroup']['memory_max']}")
    if sandbox["cgroup"]["cpu_max"] != "100000 100000":
        raise AssertionError(f"unexpected cgroup CPU limit: {sandbox['cgroup']['cpu_max']}")
    if sandbox["cgroup"]["pids_max"] != "64":
        raise AssertionError(f"unexpected cgroup PID limit: {sandbox['cgroup']['pids_max']}")
    hermes = result["hermes"]
    required = (
        hermes["tools_effective"] == [],
        hermes["agent_max_iterations"] == 2,
        hermes["agent_max_tokens"] == 128,
        hermes["api_max_retries"] == 1,
        hermes["auto_recovery_cycles"] == 0,
        hermes["streaming_disabled"],
        hermes["skip_memory_effective"],
        hermes["skip_context_files"],
        hermes["skip_background_review"],
        hermes["fallback_count"] == 0,
        hermes["fake_request_count"] == 1,
        not hermes["interrupted"],
        allow_failed or not hermes["failed"],
    )
    if not all(required):
        raise AssertionError(f"Hermes invocation violated a local bound: {hermes}")


def _run_normal(
    *, policy: DockerPolicy, image: str, owner_id: str, agent_id: str, context: dict,
    evidence: Path, run_id: str, ordinal: str, forbidden_memory: str = "", forbidden_source: str = "",
    mode: str = "normal",
) -> dict:
    task_dir = evidence / f"task-{ordinal}"
    output = task_dir / "output"
    output.mkdir(parents=True)
    job_id = f"p04-{run_id}-{ordinal}"
    task = {
        **context,
        "job_id": job_id,
        "owner_id": owner_id,
        "agent_id": agent_id,
        "mode": mode,
        "probe_forbidden": {"memory": forbidden_memory, "source_id": forbidden_source},
    }
    input_path = task_dir / "input.json"
    encoded_task = json.dumps(task, sort_keys=True).encode("utf-8")
    if len(encoded_task) > 256_000:
        raise ValueError("task input exceeds the 256 KiB local limit")
    input_path.write_bytes(encoded_task)
    input_path.chmod(0o400)
    name = f"p04-{run_id}-{ordinal}"
    argv = policy.run_argv(
        image=image, name=name, input_path=str(input_path.resolve()), output_path=str(output.resolve())
    )
    started = time.monotonic()
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        stdout, _ = proc.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=10, check=False)
        stdout, _ = proc.communicate(timeout=15)
        raise TimeoutError(f"container {name} exceeded 90 seconds; output: {stdout[-1000:]}")
    if proc.returncode != 0:
        raise RuntimeError(f"container {name} exited {proc.returncode}: {stdout[-2000:]}")
    result_path = output / "container-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    _validate_container_result(result, allow_failed=mode == "error")
    receipt_lines = (output / "fake-provider-requests.jsonl").read_text(encoding="utf-8").splitlines()
    if len(receipt_lines) != 1:
        raise AssertionError(f"expected one fake request, observed {len(receipt_lines)}")
    receipt = json.loads(receipt_lines[0])
    if receipt["tool_count"] != 0 or receipt["stream"] is not False or receipt["max_tokens"] > 128:
        raise AssertionError(f"fake provider saw a request outside the local profile: {receipt}")
    if not receipt["other_owner_memory_absent"] or not receipt["other_owner_source_absent"]:
        raise AssertionError("provider request contains another owner's context")
    if mode == "normal":
        from qualification import validate_outcome
        outcome = validate_outcome(result["hermes"]["final_response"])
        result["hermes"]["validated_outcome"] = outcome
    elif result["hermes"].get("status") not in ("raised", "returned") or not result["hermes"].get("failed"):
        raise AssertionError("injected provider error did not produce a failed Hermes result")
    return {
        "container": name,
        "argv": argv,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "stdout_tail": stdout[-2000:],
        "result": result,
        "provider_receipt": receipt,
    }


def _run_cancellation(
    *, policy: DockerPolicy, image: str, context: dict, evidence: Path, run_id: str
) -> dict:
    task_dir = evidence / "task-cancel"
    output = task_dir / "output"
    output.mkdir(parents=True)
    owner_id, agent_id = "owner-a", "agent-a"
    task_id = f"p04-{run_id}-cancel"
    task = {**context, "job_id": task_id, "owner_id": owner_id, "agent_id": agent_id, "mode": "cancel"}
    input_path = task_dir / "input.json"
    encoded_task = json.dumps(task, sort_keys=True).encode("utf-8")
    if len(encoded_task) > 256_000:
        raise ValueError("task input exceeds the 256 KiB local limit")
    input_path.write_bytes(encoded_task)
    input_path.chmod(0o400)
    name = f"p04-{run_id}-cancel"
    argv = policy.run_argv(
        image=image, name=name, input_path=str(input_path.resolve()), output_path=str(output.resolve())
    )
    ledger_path = task_dir / "restart.sqlite3"
    ledger = QualificationLedger(ledger_path, total_budget_usd="2.00")
    prompt_hash = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()
    job_id, created = ledger.reserve_and_start(
        owner_id=owner_id, agent_id=agent_id, request_key="request-cancel",
        prompt_sha256=prompt_hash, reserve_usd="2.00",
    )
    if not created:
        raise AssertionError("cancel attempt was not newly reserved")
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    marker = output / "provider-started.marker"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and proc.poll() is None and not marker.exists():
        time.sleep(0.1)
    if not marker.exists():
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=10, check=False)
        stdout, _ = proc.communicate(timeout=15)
        raise RuntimeError(f"fake-provider cancellation marker did not appear: {stdout[-1500:]}")
    before = json.loads(_docker("inspect", "--format", "{{json .Config.Labels}}", name))
    if before.get("edge-os.test.run") != run_id:
        raise AssertionError("cancellation container lacks this task's resource label")
    subprocess.run(["docker", "kill", "--signal=KILL", name], capture_output=True, timeout=10, check=True)
    stdout, _ = proc.communicate(timeout=15)
    if proc.returncode == 0:
        raise AssertionError("killed fake-provider request unexpectedly completed")
    ledger = QualificationLedger(ledger_path, total_budget_usd="2.00")
    interrupted = ledger.recover_running()
    same_job, created_again = ledger.reserve_and_start(
        owner_id=owner_id, agent_id=agent_id, request_key="request-cancel",
        prompt_sha256=prompt_hash, reserve_usd="2.00",
    )
    receipts = (output / "fake-provider-requests.jsonl").read_text(encoding="utf-8").splitlines()
    if same_job != job_id or created_again or ledger.dispatch_count(job_id) != 1 or len(receipts) != 1:
        raise AssertionError("canceled attempt was replayed or duplicated")
    if ledger.state(job_id) != AttemptState.INTERRUPTED or ledger.usage_state(job_id) != "UNKNOWN":
        raise AssertionError("restart did not preserve interrupted/unknown attempt state")
    if ledger.reserved_usd != "2.00":
        raise AssertionError("unknown charge reservation was released")
    return {
        "container": name,
        "argv": argv,
        "label_before_kill": before,
        "docker_run_exit_code": proc.returncode,
        "docker_stdout_tail": stdout[-1200:],
        "request_count_before_cancel": len(receipts),
        "recovery_state": ledger.state(job_id).value,
        "ledger_reopened_after_container_kill": True,
        "usage_state": ledger.usage_state(job_id),
        "reserved_usd_local_fixture": ledger.reserved_usd,
        "repeat_same_request_created": created_again,
        "dispatch_count": ledger.dispatch_count(job_id),
        "resource_absent_after_kill": not _docker_resources(run_id),
    }


def run_qualification(
    *, source: Path = HERMES_SOURCE, evidence_root: Path | None = None
) -> Path:
    """Build the exact pinned runtime, run two scoped fake jobs and a killed/recovery case."""
    source = Path(source).resolve()
    source_info = _source_identity(source)
    run_id = f"p04-{uuid.uuid4().hex[:12]}"
    run_started_at_utc = datetime.now(timezone.utc).isoformat()
    evidence_root = evidence_root or WORKSPACE / "docs/qualification/p04/evidence"
    evidence = Path(evidence_root) / run_id
    evidence.mkdir(parents=True, exist_ok=False)
    policy = DockerPolicy(run_id=run_id)
    image = f"p04-hermes:{run_id}"
    image_id = None
    before_resources = _docker_resources(run_id)
    source_info["uv_version_host"] = subprocess.run(
        ["uv", "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    (evidence / "source_identity.json").write_text(json.dumps(source_info, sort_keys=True, indent=2) + "\n")
    (evidence / "host_docker_info.txt").write_text(
        _docker("info", "--format", "{{.CgroupDriver}} {{.CgroupVersion}} {{.Architecture}}") + "\n",
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory(prefix=f"{run_id}-build-") as temp:
        context_dir = Path(temp)
        _build_context(source, context_dir)
        build_argv = ["docker", "build", "--pull", "--tag", image, str(context_dir)]
        build = subprocess.run(
            build_argv,
            check=True, capture_output=True, text=True, timeout=900,
        )
        image_id = _docker("image", "inspect", "--format", "{{.Id}}", image)
        (evidence / "docker_build.json").write_text(json.dumps({
            "argv": build_argv, "exit_code": build.returncode,
            "stdout": build.stdout, "stderr": build.stderr,
        }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    stage = "fixture_setup"
    try:
        db = evidence / "fixture-state.sqlite3"
        fixtures = FixtureStore(db)
        fixtures.create_agent("owner-a", "agent-a")
        fixtures.create_agent("owner-b", "agent-b")
        fixtures.add_source("owner-a", "agent-a", "source-a", "fixture://source/a", "Source A fixture text.")
        fixtures.add_source("owner-b", "agent-b", "source-b", "fixture://source/b", "Source B fixture text.")
        fixtures.set_memory("owner-a", "agent-a", ["owner A short-memory sentinel"], ["source-a"])
        fixtures.set_memory("owner-b", "agent-b", ["owner B long-memory sentinel"], ["source-b"])
        fixtures.append_stream_chunk("owner-a", "agent-a", "stream-a", 0, "owner-a:fixture-chunk")
        fixtures.append_stream_chunk("owner-b", "agent-b", "stream-b", 0, "owner-b:fixture-chunk")
        stream_checks = {
            "owner_a_reads_own": fixtures.read_stream("owner-a", "agent-a", "stream-a") == ["owner-a:fixture-chunk"],
            "owner_b_reads_own": fixtures.read_stream("owner-b", "agent-b", "stream-b") == ["owner-b:fixture-chunk"],
        }
        try:
            fixtures.read_stream("owner-b", "agent-b", "stream-a")
            stream_checks["cross_owner_denied"] = False
        except PermissionError:
            stream_checks["cross_owner_denied"] = True
        if not all(stream_checks.values()):
            raise AssertionError("durable fixture stream ownership check failed")
        results = []
        for ordinal, (owner, agent) in enumerate((("owner-a", "agent-a"), ("owner-b", "agent-b")), start=1):
            stage = f"normal_job_{ordinal}_{owner}"
            context = fixtures.task_context(owner, agent)
            other = ("owner-b", "agent-b") if owner == "owner-a" else ("owner-a", "agent-a")
            forbidden_context = fixtures.task_context(*other)
            result = _run_normal(
                policy=policy, image=image, owner_id=owner, agent_id=agent,
                context=context, evidence=evidence, run_id=run_id, ordinal=f"{ordinal}-{owner}",
                forbidden_memory=forbidden_context["memory"]["entries"][0],
                forbidden_source=forbidden_context["sources"][0]["source_id"],
            )
            results.append(result)
        error_context = fixtures.task_context("owner-a", "agent-a")
        stage = "provider_error_case"
        provider_error = _run_normal(
            policy=policy, image=image, owner_id="owner-a", agent_id="agent-a",
            context=error_context, evidence=evidence, run_id=run_id,
            ordinal="3-owner-a-error", forbidden_memory="owner B long-memory sentinel",
            forbidden_source="source-b", mode="error",
        )
        cancel_context = fixtures.task_context("owner-a", "agent-a")
        stage = "cancellation_and_recovery"
        cancellation = _run_cancellation(
            policy=policy, image=image, context=cancel_context, evidence=evidence, run_id=run_id
        )
        after_resources = _docker_resources(run_id)
        if after_resources:
            raise AssertionError(f"task-labelled Docker containers remain: {after_resources}")
        summary = {
            "run_id": run_id,
            "run_started_at_utc": run_started_at_utc,
            "fixture_label": "LOCAL_FAKE_PROVIDER_NO_NETWORK",
            "source": source_info,
            "image_id": image_id,
            "before_labeled_containers": before_resources,
            "after_labeled_containers": after_resources,
            "normal_jobs": results,
            "provider_error_case": provider_error,
            "fixture_stream_checks": stream_checks,
            "cancellation": cancellation,
            "provider_calls": {"real_inference": 0, "local_fake_provider_requests": 4},
            "hosted_production_isolation": "NOT_TESTED",
        }
        (evidence / "qualification-result.json").write_text(
            json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        return evidence
    except Exception as exc:
        (evidence / "run-failure.json").write_text(
            json.dumps({
                "run_id": run_id,
                "stage": stage,
                "error_class": type(exc).__name__,
                "error_message_retained": False,
                "real_inference_requests": 0,
                "fixture_requests_may_have_occurred": True,
            }, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        if image_id:
            removed = subprocess.run(
                ["docker", "image", "rm", image],
                capture_output=True, text=True, timeout=60, check=False,
            )
            remaining = subprocess.run(
                ["docker", "image", "inspect", image],
                capture_output=True, text=True, timeout=30, check=False,
            )
            remaining_error = remaining.stdout + remaining.stderr
            tag_absent = remaining.returncode != 0 and (
                "No such image" in remaining_error or "No such object" in remaining_error
            )
            cleanup_ok = removed.returncode == 0 and tag_absent
            (evidence / "image_cleanup.txt").write_text(
                json.dumps({"image_tag": image, "image_id": image_id,
                            "exit_code": removed.returncode,
                            "tag_absent_after_cleanup": tag_absent,
                            "cleanup_pass": cleanup_ok,
                            "output": (removed.stdout + removed.stderr)[-2000:]}, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            if not cleanup_ok:
                raise RuntimeError(f"task-owned Docker image tag cleanup failed: {image}")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", type=Path, default=HERMES_SOURCE)
    parser.add_argument("--evidence-root", type=Path, default=WORKSPACE / "docs/qualification/p04/evidence")
    args = parser.parse_args()
    evidence = run_qualification(source=args.hermes_source, evidence_root=args.evidence_root)
    print(f"P04 local qualification evidence: {evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
