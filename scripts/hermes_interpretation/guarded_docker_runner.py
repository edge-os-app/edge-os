"""Runs one Hermes turn behind the request guard in a disposable no-network container. Controlled provider only.

It reuses the accepted container policy and result mapping of `DockerHermesTurnRunner` and changes what the guarded
job needs: the entrypoint, the guard policy, and a credential file. Everything a turn depends on is captured ONCE at its
start (turn number, policy, credential value), so a change to the source file, the policy or the counter during the turn
cannot split the turn's identity. The job reads a private copy of the credential, so the host holds the exact value the
job was given. The credential is a file mount, never a command-line value.

Evidence handling: before a turn ends, on every path, the output folder is sealed. Sealing works on bytes, removes links
and special files (a named pipe is deleted, never opened), makes locked paths writable, deletes files too large to scan,
and must finish within the job timeout plus `seal_grace_seconds`. A folder that cannot be sealed in time is removed and
the turn raises `EvidenceNotSealed`: it is never reported as clean. A container that may still run is stopped, or the
turn raises, before sealing.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from docker_turn_runner import HERE, LABEL, DockerHermesTurnRunner
from leak_scan import encodings
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage
from provider_guard import GuardPolicy

REDACTED = "[REDACTED]"
MAX_SCANNED_BYTES = 64 * 1024 * 1024
ENTRYPOINT = "/opt/hermes/.venv/bin/python"


class EvidenceNotSealed(RuntimeError):
    """Saved evidence could not be proved free of the credential, or a container may still write to it."""


class CredentialUnavailable(RuntimeError):
    """The credential file could not be read. The message names neither the path nor any value."""


@dataclass(frozen=True)
class _TurnPlan:
    """What one turn depends on, captured once under a lock before any other work."""

    sequence: int
    policy: GuardPolicy
    secret: str | None
    deadline: float  # monotonic time by which the process wait AND the sealing must be done


class GuardedDockerTurnRunner(DockerHermesTurnRunner):
    def __init__(self, *, policy: GuardPolicy, credential_file: Path | None = None, seal_grace_seconds: float = 5.0,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.policy, self.credential_file, self.seal_grace_seconds = policy, credential_file, seal_grace_seconds
        self._turn_lock = threading.Lock()

    def _plan(self) -> _TurnPlan:
        with self._turn_lock:
            self.turn_count += 1
            sequence, policy, source = self.turn_count, self.policy, self.credential_file
        secret = None
        if source is not None:
            try:
                secret = source.read_text(encoding="utf-8").strip() or None  # an editor or secret store adds a newline
            except (OSError, UnicodeDecodeError):
                raise CredentialUnavailable("the credential file could not be read") from None
        return _TurnPlan(sequence, policy, secret, time.monotonic() + self.timeout_seconds + self.seal_grace_seconds)

    # --- Sealing evidence -----------------------------------------------------------------------------------------

    @classmethod
    def _redact(cls, folder: Path, secret: str, deadline: float) -> bool:
        """Remove the credential from every file and name under `folder`. True when something held it."""
        forms, found = encodings(secret), [False]
        cls._seal_folder(folder, forms, found, deadline)
        return found[0]

    @classmethod
    def _seal_folder(cls, folder: Path, forms: list[bytes], found: list[bool], deadline: float) -> None:
        try:
            folder.chmod(0o700)
            entries = list(os.scandir(folder))
        except OSError as error:
            shutil.rmtree(folder, ignore_errors=True)
            if folder.exists():
                raise EvidenceNotSealed("a folder could not be read or removed") from error
            found[0] = True
            return
        for entry in entries:
            if time.monotonic() > deadline:
                raise EvidenceNotSealed("sealing passed its time limit")
            path = Path(entry.path)
            try:
                kind = stat.S_IFMT(entry.stat(follow_symlinks=False).st_mode)
                if kind == stat.S_IFDIR:
                    cls._seal_folder(path, forms, found, deadline)
                elif kind == stat.S_IFREG:
                    cls._seal_file(path, forms, found)
                else:  # a link, a named pipe, a socket or a device: removed, never opened or followed
                    path.unlink()
            except EvidenceNotSealed:
                raise
            except OSError as error:
                path.unlink(missing_ok=True)
                if path.exists():
                    raise EvidenceNotSealed("an entry could not be sealed or removed") from error
                found[0] = True
            name = path.name.encode()
            if path.exists() and any(form in name for form in forms):
                found[0] = True
                path.rename(path.with_name(f"redacted-name-{hashlib.sha256(name).hexdigest()[:8]}"))

    @staticmethod
    def _seal_file(path: Path, forms: list[bytes], found: list[bool]) -> None:
        path.chmod(0o600)
        if path.stat().st_size > MAX_SCANNED_BYTES:  # too large to scan whole: not kept
            path.unlink()
            found[0] = True
            return
        data = path.read_bytes()
        if any(form in data for form in forms):
            found[0] = True
            for form in forms:
                data = data.replace(form, REDACTED.encode())
            path.write_bytes(data)

    def _seal(self, output: Path, plan: _TurnPlan) -> bool:
        if plan.secret is None:
            return False
        try:
            return self._redact(output, plan.secret, plan.deadline)
        except EvidenceNotSealed:
            shutil.rmtree(output, ignore_errors=True)  # evidence that may hold the credential is not kept
            raise

    # --- One turn -------------------------------------------------------------------------------------------------

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        plan = self._plan()
        task_dir = self.evidence_dir / f"turn-{plan.sequence:02d}-{turn.attempt_id}"
        output = task_dir / "output"
        output.mkdir(parents=True)
        try:
            with tempfile.TemporaryDirectory(prefix="p05-credential-") as private:
                return self._run_container(turn, task_dir, plan, Path(private))
        finally:  # whatever happened above, nothing that may hold the credential stays in the evidence
            self._seal(output, plan)

    def _run_container(self, turn: HermesTurn, task_dir: Path, plan: _TurnPlan, private: Path) -> HermesTurnResult:
        output, policy = task_dir / "output", plan.policy
        job = {"attempt_id": turn.attempt_id, "system_prompt": turn.system_prompt, "user_message": turn.user_message,
               "model": turn.model, "route": turn.route, "max_output_tokens": turn.max_output_tokens,
               "run_budget_seconds": self.run_budget_seconds, "provider_script": dict(self.script_for(turn)),
               "forbidden": self.forbidden, "guard": {"policy": {**asdict(policy), "required_extra": dict(policy.required_extra)}}}
        input_path = task_dir / "input.json"
        input_path.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
        input_path.chmod(0o400)
        name = f"p05-{self.run_id}-{plan.sequence:02d}"
        mounts = [(input_path, "/job/input.json"), (HERE / "guarded_turn_job.py", "/opt/p05guard/guarded_turn_job.py"),
                  (HERE / "provider_guard.py", "/opt/p05guard/provider_guard.py")]
        if plan.secret is not None:  # the job reads this private copy, so the host holds exactly what the job was given
            given = private / "credential"
            given.write_text(plan.secret, encoding="utf-8")
            given.chmod(0o400)
            mounts.append((given, "/job/credential"))
        argv = ["docker", "run", "--rm", "--name", name, "--label", f"{LABEL}={self.run_id}", "--network=none",
                "--read-only", "--memory=512m", "--memory-swap=512m", "--cpus=1", "--pids-limit=64", "--cap-drop=ALL",
                "--user", f"{os.getuid()}:{os.getgid()}", "--security-opt=no-new-privileges",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--entrypoint", ENTRYPOINT]
        for source, target in mounts:
            argv += ["--mount", f"type=bind,src={source.resolve()},dst={target},readonly"]
        argv += ["--mount", f"type=bind,src={output.resolve()},dst=/job/output",
                 "--env", f"HOME=/tmp/p05-{name}/home", "--env", f"HERMES_HOME=/tmp/p05-{name}/hermes-home",
                 "--env", f"XDG_CONFIG_HOME=/tmp/p05-{name}/config", "--env", f"XDG_CACHE_HOME=/tmp/p05-{name}/cache",
                 "--env", "PYTHONDONTWRITEBYTECODE=1", self.image, "-B", "/opt/p05guard/guarded_turn_job.py"]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)  # bytes: the output need not be valid text
        try:
            stdout, _ = proc.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            lifecycle = self._kill_owned(name, proc)
            (task_dir / "container-lifecycle.json").write_text(json.dumps(lifecycle, indent=1) + "\n")
            if not lifecycle["container_absent"]:
                raise EvidenceNotSealed("the container was still present after the kill") from None
            return HermesTurnResult(status="TIMED_OUT", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="TimeoutExpired")
        if proc.returncode is None or proc.returncode < 0:  # the client died of a signal: the container may still run
            if not self._kill_owned(name, proc)["container_absent"]:
                raise EvidenceNotSealed("a container that may still write could not be stopped")
        scrubbed = stdout
        for form in (encodings(plan.secret) if plan.secret else []):
            scrubbed = scrubbed.replace(form, REDACTED.encode())
        (task_dir / "container-stdout.txt").write_bytes(scrubbed)  # stdout is evidence too
        echoed = self._seal(output, plan)  # sealed here for the result check, and again in `finally` for every path
        result_path = output / "container-result.json"
        if proc.returncode != 0 or not result_path.exists():
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerExit")
        raw = json.loads(result_path.read_text(encoding="utf-8"))
        mapped = self._map(raw)
        guard = raw["guard"]
        observed = {**mapped.observed, "guard_admitted": guard["admitted_count"], "guard_seen": guard["seen_count"],
                    "guard_refusal_reasons": sorted({r["reason"] for r in guard["evidence"] if not r["admitted"]})}
        mapped = replace(mapped, observed=observed)
        if echoed:
            return replace(mapped, status="UNKNOWN", text=None, error_class="CredentialEchoed")
        return mapped
