"""Runs one Hermes turn behind the request guard in a disposable no-network container. Controlled provider only.

It reuses the accepted container policy and result mapping of `DockerHermesTurnRunner` and changes what the guarded
job needs: the entrypoint, the guard policy, and a credential file.

One turn, one lifecycle. Everything a turn depends on is captured ONCE, under a lock, before any other work: its number
and container name, the policy, the image, the timeouts and the credential value. A change to the runner's attributes or
to the credential file during the turn cannot split the turn's identity. The job reads a private copy of the credential,
so the host holds the exact value the job was given. A credential file that is missing, unreadable or empty stops the
turn before any job starts: a configured credential is never silently dropped.

On EVERY path out of a turn (a result, a timeout, any exception including KeyboardInterrupt) the same two steps run,
in this order: a container that may still run is stopped and verified gone, then the output folder is sealed. If either
step fails, for any reason, the output folder is removed and `EvidenceNotSealed` is raised: evidence that may hold the
credential is never kept and never reported as clean. Sealing works on bytes, removes links and special files without
opening them, deletes files too large to scan, and has to finish by the job timeout plus `seal_grace_seconds`.
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
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import docker_turn_runner
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
    """The credential file is missing, unreadable or empty. The message names neither the path nor any value."""


@dataclass(frozen=True)
class _TurnPlan:
    """What one turn depends on, captured once under a lock before any other work."""

    sequence: int
    name: str
    run_id: str
    image: str
    policy: GuardPolicy
    secret: str | None
    timeout: float
    run_budget: int
    forbidden: tuple[str, ...]
    deadline: float  # monotonic time by which the process wait, the stop step and the sealing must be done


@dataclass
class _Launch:
    """What the lifecycle needs to know about the job process."""

    proc: Any = None
    stopped: bool = False  # the client exited by itself, or the container was verified gone
    stopping: dict[str, Any] = field(default_factory=dict)


class GuardedDockerTurnRunner(DockerHermesTurnRunner):
    def __init__(self, *, policy: GuardPolicy, credential_file: Path | None = None, seal_grace_seconds: float = 5.0,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.policy, self.credential_file, self.seal_grace_seconds = policy, credential_file, seal_grace_seconds
        self._turn_lock = threading.Lock()
        self._token = uuid.uuid4().hex[:6]  # two runner objects with one run_id must not share container names

    def _plan(self) -> _TurnPlan:
        with self._turn_lock:
            self.turn_count += 1
            sequence = self.turn_count
            policy, source, timeout = self.policy, self.credential_file, self.timeout_seconds
            image, run_id, budget, forbidden = self.image, self.run_id, self.run_budget_seconds, tuple(self.forbidden)
            grace = self.seal_grace_seconds
        secret = None
        if source is not None:
            try:
                secret = source.read_text(encoding="utf-8").strip()  # an editor or secret store adds a newline
            except (OSError, UnicodeDecodeError):
                raise CredentialUnavailable("the credential file could not be read") from None
            if not secret:
                raise CredentialUnavailable("the credential file is empty")
        return _TurnPlan(sequence, f"p05-{run_id}-{self._token}-{sequence:02d}", run_id, image, policy, secret, timeout,
                         budget, forbidden, time.monotonic() + timeout + grace)

    # --- Sealing evidence -----------------------------------------------------------------------------------------

    @classmethod
    def _redact(cls, folder: Path, secret: str, deadline: float) -> bool:
        """Remove the credential from every file and name under `folder`. True when something held it.

        Iterative, so a very deep tree cannot exhaust the recursion limit. Any error propagates to `_seal`.
        """
        forms, found, pending = encodings(secret), False, [folder]
        while pending:
            current = pending.pop()
            current.chmod(0o700)
            with os.scandir(current) as scan:
                entries = list(scan)
            for entry in entries:
                if time.monotonic() > deadline:
                    raise EvidenceNotSealed("sealing passed its time limit")
                path = Path(entry.path)
                kind = stat.S_IFMT(entry.stat(follow_symlinks=False).st_mode)
                if kind == stat.S_IFDIR:
                    pending.append(path)
                elif kind == stat.S_IFREG:
                    found |= cls._seal_file(path, forms)
                else:  # a link, a named pipe, a socket or a device: removed, never opened or followed
                    path.unlink()
                name = os.fsencode(path.name)  # a name that is not valid text is still bytes
                if path.exists() and any(form in name for form in forms):
                    found = True
                    path.rename(path.with_name(f"redacted-name-{hashlib.sha256(name).hexdigest()[:8]}"))
        return found

    @staticmethod
    def _seal_file(path: Path, forms: list[bytes]) -> bool:
        path.chmod(0o600)
        if path.stat().st_size > MAX_SCANNED_BYTES:  # too large to scan whole: not kept
            path.unlink()
            return True
        data = path.read_bytes()
        if not any(form in data for form in forms):
            return False
        for form in forms:
            data = data.replace(form, REDACTED.encode())
        path.write_bytes(data)
        return True

    @staticmethod
    def _quarantine(output: Path) -> None:
        """Remove evidence that cannot be proved clean. If it cannot be removed, say so."""
        def unlock(function, path, _error):  # a locked folder or file: make it ours, then retry
            try:
                os.chmod(path, 0o700)
                function(path)
            except OSError:
                pass

        shutil.rmtree(output, onexc=unlock)
        if output.exists():
            raise EvidenceNotSealed("evidence that may hold the credential could not be removed")

    def _seal(self, output: Path, plan: _TurnPlan) -> bool:
        """Seal the output. Any failure at all removes it and raises `EvidenceNotSealed`."""
        if plan.secret is None:
            return False
        try:
            return self._redact(output, plan.secret, plan.deadline)
        except BaseException as error:
            self._quarantine(output)
            if isinstance(error, EvidenceNotSealed):
                raise
            raise EvidenceNotSealed("the evidence could not be sealed") from error

    # --- Stopping the container ------------------------------------------------------------------------------------

    def _stop_owned(self, plan: _TurnPlan, proc: Any) -> dict[str, Any]:
        """Stop this turn's own container if it is still there, and verify it is gone. Each command has a time limit."""
        def cli(*args: str) -> subprocess.CompletedProcess[str]:
            return docker_turn_runner.docker(*args, timeout=int(max(1.0, min(60.0, plan.deadline - time.monotonic()))), check=False)

        name, owned = plan.name, False
        try:
            info = cli("inspect", name, "--format", f'{{{{.Name}}}} {{{{index .Config.Labels "{LABEL}"}}}}')
            owned = info.returncode == 0 and info.stdout.strip() == f"/{name} {plan.run_id}"
            if owned:
                cli("kill", name)
        except Exception:  # noqa: BLE001 - if the stop commands fail, the container is not shown to be gone
            return {"container": name, "ownership_verified": owned, "container_absent": False}
        try:
            proc.communicate(timeout=5)
        except Exception:  # noqa: BLE001 - reaping the client must not hide the verification below
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        for attempt in range(20):
            try:
                if not cli("ps", "-a", "--filter", f"name=^{name}$", "-q").stdout.strip():
                    return {"container": name, "ownership_verified": owned, "container_absent": True}
            except Exception:  # noqa: BLE001
                break
            if attempt and time.monotonic() > plan.deadline:
                break
            time.sleep(0.25)
        return {"container": name, "ownership_verified": owned, "container_absent": False}

    def _confirm_stopped(self, plan: _TurnPlan, launch: _Launch) -> None:
        if launch.proc is None or launch.stopped:
            return
        launch.stopping = self._stop_owned(plan, launch.proc)
        if not launch.stopping["container_absent"]:
            raise EvidenceNotSealed("a container that may still write could not be stopped")
        launch.stopped = True

    # --- One turn -------------------------------------------------------------------------------------------------

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        plan = self._plan()
        task_dir = self.evidence_dir / f"turn-{plan.sequence:02d}-{turn.attempt_id}"
        output = task_dir / "output"
        output.mkdir(parents=True)
        launch = _Launch()
        try:
            with tempfile.TemporaryDirectory(prefix="p05-credential-") as private:
                result = self._run_container(turn, task_dir, plan, Path(private), launch)
        except BaseException:
            try:  # the same two steps as on success; the original failure is the one that propagates
                self._confirm_stopped(plan, launch)
                self._seal(output, plan)
            except EvidenceNotSealed:
                self._quarantine(output)
            raise
        try:
            self._confirm_stopped(plan, launch)
            self._seal(output, plan)
        except EvidenceNotSealed:
            self._quarantine(output)
            raise
        return result

    def _run_container(self, turn: HermesTurn, task_dir: Path, plan: _TurnPlan, private: Path, launch: _Launch) -> HermesTurnResult:
        output, policy = task_dir / "output", plan.policy
        job = {"attempt_id": turn.attempt_id, "system_prompt": turn.system_prompt, "user_message": turn.user_message,
               "model": turn.model, "route": turn.route, "max_output_tokens": turn.max_output_tokens,
               "run_budget_seconds": plan.run_budget, "provider_script": dict(self.script_for(turn)),
               "forbidden": list(plan.forbidden), "guard": {"policy": {**asdict(policy), "required_extra": dict(policy.required_extra)}}}
        input_path = task_dir / "input.json"
        input_path.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
        input_path.chmod(0o400)
        name = plan.name
        mounts = [(input_path, "/job/input.json"), (HERE / "guarded_turn_job.py", "/opt/p05guard/guarded_turn_job.py"),
                  (HERE / "provider_guard.py", "/opt/p05guard/provider_guard.py")]
        if plan.secret is not None:  # the job reads this private copy, so the host holds exactly what the job was given
            given = private / "credential"
            given.write_text(plan.secret, encoding="utf-8")
            given.chmod(0o400)
            mounts.append((given, "/job/credential"))
        argv = ["docker", "run", "--rm", "--name", name, "--label", f"{LABEL}={plan.run_id}", "--network=none",
                "--read-only", "--memory=512m", "--memory-swap=512m", "--cpus=1", "--pids-limit=64", "--cap-drop=ALL",
                "--user", f"{os.getuid()}:{os.getgid()}", "--security-opt=no-new-privileges",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--entrypoint", ENTRYPOINT]
        for source, target in mounts:
            argv += ["--mount", f"type=bind,src={source.resolve()},dst={target},readonly"]
        argv += ["--mount", f"type=bind,src={output.resolve()},dst=/job/output",
                 "--env", f"HOME=/tmp/p05-{name}/home", "--env", f"HERMES_HOME=/tmp/p05-{name}/hermes-home",
                 "--env", f"XDG_CONFIG_HOME=/tmp/p05-{name}/config", "--env", f"XDG_CACHE_HOME=/tmp/p05-{name}/cache",
                 "--env", "PYTHONDONTWRITEBYTECODE=1", plan.image, "-B", "/opt/p05guard/guarded_turn_job.py"]
        launch.proc = proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)  # bytes: not always text
        try:
            stdout, _ = proc.communicate(timeout=plan.timeout)
        except subprocess.TimeoutExpired:
            self._confirm_stopped(plan, launch)  # raises if the container is still there after the kill
            (task_dir / "container-lifecycle.json").write_text(json.dumps(launch.stopping, indent=1) + "\n")
            return HermesTurnResult(status="TIMED_OUT", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="TimeoutExpired")
        if proc.returncode is not None and proc.returncode >= 0:
            launch.stopped = True  # the client returned, so the container it waited for has exited
        else:
            self._confirm_stopped(plan, launch)  # the client died of a signal: the container may still run
        scrubbed = stdout
        for form in (encodings(plan.secret) if plan.secret else []):
            scrubbed = scrubbed.replace(form, REDACTED.encode())
        (task_dir / "container-stdout.txt").write_bytes(scrubbed)  # stdout is evidence too
        echoed = self._seal(output, plan)  # sealed here for the result check; the lifecycle seals again on every path
        result_path = output / "container-result.json"
        if proc.returncode != 0 or not result_path.exists():
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerExit")
        try:
            raw = json.loads(result_path.read_text(encoding="utf-8"))
            mapped = self._map(raw)
            guard = raw["guard"]
            observed = {**mapped.observed, "guard_admitted": guard["admitted_count"], "guard_seen": guard["seen_count"],
                        "guard_refusal_reasons": sorted({r["reason"] for r in guard["evidence"] if not r["admitted"]})}
        except (ValueError, RecursionError, KeyError, TypeError, OSError):  # a result the job wrote but the host cannot read
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerResultUnreadable")
        mapped = replace(mapped, observed=observed)
        if echoed:
            return replace(mapped, status="UNKNOWN", text=None, error_class="CredentialEchoed")
        return mapped
