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
credential is never reported as clean. Removal is itself bounded: what cannot be removed in time is moved in one step to
a private quarantine folder, which the error names, and `purge_quarantine` removes it later. Sealing works on bytes, removes links and special files without
opening them, deletes files too large to scan, and has to finish by the job timeout plus `seal_grace_seconds`.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
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
MAX_ENTRIES = 10_000  # more files and folders than this in one output are not scanned: the output is removed
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
    stop_deadline: float  # the stop step must be done by this time; the rest of the budget is kept for removing evidence


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
        self._check_deadline_settings(self.timeout_seconds, seal_grace_seconds)
        self.policy, self.credential_file, self.seal_grace_seconds = policy, credential_file, seal_grace_seconds
        self._turn_lock = threading.Lock()
        self._token = uuid.uuid4().hex[:6]  # two runner objects with one run_id must not share container names

    @staticmethod
    def _check_deadline_settings(timeout: Any, grace: Any) -> None:
        for label, value in (("timeout_seconds", timeout), ("seal_grace_seconds", grace)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{label} must be a finite number")  # a NaN would switch every deadline off

    def _plan(self) -> _TurnPlan:
        with self._turn_lock:
            policy, source, timeout = self.policy, self.credential_file, self.timeout_seconds
            image, run_id, budget, forbidden = self.image, self.run_id, self.run_budget_seconds, tuple(self.forbidden)
            grace = self.seal_grace_seconds
            self._check_deadline_settings(timeout, grace)  # before a turn number is used or anything starts
            self.turn_count += 1
            sequence = self.turn_count
        secret = None
        if source is not None:
            try:
                secret = source.read_text(encoding="utf-8").strip()  # an editor or secret store adds a newline
            except (OSError, UnicodeDecodeError):
                raise CredentialUnavailable("the credential file could not be read") from None
            if not secret:
                raise CredentialUnavailable("the credential file is empty")
        deadline = time.monotonic() + timeout + grace
        return _TurnPlan(sequence, f"p05-{run_id}-{self._token}-{sequence:02d}", run_id, image, policy, secret, timeout,
                         budget, forbidden, deadline, deadline - max(0.0, min(0.5, grace / 10)))

    # --- Sealing evidence -----------------------------------------------------------------------------------------

    @classmethod
    def _redact(cls, folder: Path, secret: str, deadline: float) -> bool:
        """Remove the credential from every file and name under `folder`. True when something held it.

        Iterative, so a very deep tree cannot exhaust the recursion limit. Any error propagates to `_seal`.
        """
        forms, found, pending, seen = encodings(secret), False, [folder], 0
        while pending:
            current = pending.pop()
            current.chmod(0o700)
            with os.scandir(current) as scan:  # read no more than the limit allows, so a folder that never ends cannot hang us
                entries = list(itertools.islice(scan, MAX_ENTRIES - seen + 1))
            if len(entries) > MAX_ENTRIES - seen:
                raise EvidenceNotSealed("the output holds more entries than can be scanned")
            for entry in entries:
                seen += 1
                if time.monotonic() > deadline:
                    raise EvidenceNotSealed("sealing passed its time limit")
                path, kind = Path(entry.path), stat.S_IFMT(entry.stat(follow_symlinks=False).st_mode)
                if kind not in (stat.S_IFDIR, stat.S_IFREG):  # a link, a named pipe, a socket or a device: removed, never opened
                    path.unlink()
                    continue
                name = os.fsencode(path.name)  # a name that is not valid text is still bytes
                if any(form in name for form in forms):  # rename BEFORE descending, so the folder's files are still sealed
                    found = True
                    path = path.rename(path.with_name(f"redacted-name-{hashlib.sha256(name).hexdigest()[:8]}"))
                if kind == stat.S_IFDIR:
                    pending.append(path)
                else:
                    found |= cls._seal_file(path, forms)
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
    def _remove_tree(root: Path, until: float) -> None:
        """Remove `root` and everything under it without ever following a link. Raises `TimeoutError` after `until`.

        Works on directory file descriptors, so a folder that a still-running container swaps for a link while this runs
        is unlinked as a link and never entered: nothing outside `root` can be touched. Every step ticks the clock.
        Folders are made ours (mode 700) as they are entered. A very deep tree needs more descriptors than the process
        may hold; that raises, and the caller moves the tree instead.
        """
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

        def open_folder(parent: int, name: str) -> int:
            """Open a folder by name relative to `parent`, never through a link; make a locked one ours first."""
            try:
                fd = os.open(name, flags, dir_fd=parent)
            except PermissionError:  # a locked folder: change its own mode (not a link's target), then open it
                os.chmod(name, 0o700, dir_fd=parent, follow_symlinks=False)
                fd = os.open(name, flags, dir_fd=parent)
            os.fchmod(fd, 0o700)
            return fd

        parent_fd = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY)
        frames: list[tuple[int, str, int, Any]] = []  # (descriptor, name, parent descriptor, names still to visit)
        try:
            fd = open_folder(parent_fd, root.name)
            frames.append((fd, root.name, parent_fd, iter(os.listdir(fd))))
            while frames:
                if time.monotonic() > until:  # every step ticks the clock, including the removal of an empty folder
                    raise TimeoutError("removal passed its time limit")
                fd, name, parent, names = frames[-1]
                child = next(names, None)
                if child is None:
                    frames.pop()
                    os.close(fd)
                    os.rmdir(name, dir_fd=parent)
                    continue
                if stat.S_ISDIR(os.stat(child, dir_fd=fd, follow_symlinks=False).st_mode):
                    below = open_folder(fd, child)  # a link swapped in since the check fails here (ELOOP)
                    frames.append((below, child, fd, iter(os.listdir(below))))
                else:
                    os.unlink(child, dir_fd=fd)
        finally:
            for fd, *_ in frames:
                os.close(fd)
            os.close(parent_fd)

    def _quarantine(self, output: Path, plan: _TurnPlan) -> None:
        """Take evidence that cannot be proved clean out of reach. It returns when the folder is gone, else raises `EvidenceNotSealed`.

        Removal has the rest of the turn's budget (a tenth of a second at least, so a small output is always removed).
        If it is not finished by then, the rest is MOVED, in one step, to a private `quarantine-*` folder beside the turn
        folders and the turn says so. `purge_quarantine` removes those folders when no clock runs.
        """
        interrupt = None
        try:
            self._remove_tree(output, max(plan.deadline, time.monotonic() + 0.1))
        except Exception:  # noqa: BLE001 - out of time, or the walk cannot go on: never an unbounded removal; move it
            pass
        except BaseException as stopped:  # an interrupt: still move the folder first, then let the interrupt through
            interrupt = stopped
        if not output.exists():
            if interrupt is not None:
                raise interrupt
            return
        held = output.parent.parent / f"quarantine-{output.parent.name}-{uuid.uuid4().hex[:6]}"
        try:
            output.rename(held)
            held.chmod(0o700)
        except OSError as error:
            raise EvidenceNotSealed("evidence that may hold the credential could not be removed or moved") from error
        if interrupt is not None:
            raise interrupt
        raise EvidenceNotSealed(f"evidence that may hold the credential was not removed in time; it is in the private folder {held.name}")

    def purge_quarantine(self) -> None:
        """Remove every quarantine folder. This has no clock: run it between turns. Raises if any folder is left."""
        left = []
        for held in self.evidence_dir.glob("quarantine-*"):
            try:
                self._remove_tree(held, float("inf"))
            except Exception:  # noqa: BLE001 - e.g. a chain longer than the path limit: the fd-based removal copes with that
                shutil.rmtree(held, ignore_errors=True)
            if held.exists():
                left.append(held.name)
        if left:
            raise EvidenceNotSealed(f"quarantine folders are still there: {', '.join(left)}")

    def _seal(self, output: Path, plan: _TurnPlan) -> bool:
        """Seal the output. Any failure at all removes it and raises `EvidenceNotSealed`."""
        if plan.secret is None:
            return False
        try:
            return self._redact(output, plan.secret, plan.deadline)
        except BaseException as error:
            self._quarantine(output, plan)
            if isinstance(error, EvidenceNotSealed):
                raise
            raise EvidenceNotSealed("the evidence could not be sealed") from error

    # --- Stopping the container ------------------------------------------------------------------------------------

    def _stop_owned(self, plan: _TurnPlan, proc: Any) -> dict[str, Any]:
        """Stop this turn's own container if it is still there, and verify it is gone.

        Every command, the wait for the client and every pause draw on ONE remaining budget (`plan.stop_deadline`).
        No command or wait starts once the budget is spent, and none is longer than what is left, so the step cannot
        pass the deadline. If it cannot show the container gone in time, it says so.
        """
        name, owned = plan.name, False

        def left() -> float:
            return plan.stop_deadline - time.monotonic()

        def cli(*args: str) -> subprocess.CompletedProcess[str]:
            if left() <= 0:
                raise TimeoutError("the stop budget is spent")
            return docker_turn_runner.docker(*args, timeout=min(60.0, left()), check=False)

        def failed() -> dict[str, Any]:
            return {"container": name, "ownership_verified": owned, "container_absent": False}

        try:
            proc.kill()  # the client first: a client that is still starting could create the container after our check
        except Exception:  # noqa: BLE001
            pass
        try:
            info = cli("inspect", name, "--format", f'{{{{.Name}}}} {{{{index .Config.Labels "{LABEL}"}}}}')
            owned = info.returncode == 0 and info.stdout.strip() == f"/{name} {plan.run_id}"
            if owned:
                cli("kill", name)
        except Exception:  # noqa: BLE001 - if the stop commands fail, the container is not shown to be gone
            return failed()
        if left() > 0:
            try:
                proc.communicate(timeout=min(5.0, left()))  # reap the client, within what is left
            except Exception:  # noqa: BLE001 - reaping the client must not hide the verification below
                pass
        clear = 0
        for _ in range(20):  # at most 20 listings, and none after the budget is spent
            if left() <= 0:
                break
            try:
                listing = cli("ps", "-a", "--filter", f"name=^{name}$", "-q")
            except Exception:  # noqa: BLE001
                return failed()
            if listing.returncode == 0 and not listing.stdout.strip():  # a failed listing proves nothing
                clear += 1
                if clear >= 2:  # absent twice in a row, so a slow start cannot hide behind one empty answer
                    return {"container": name, "ownership_verified": owned, "container_absent": True}
            else:
                clear = 0
            time.sleep(max(0.0, min(0.25, left())))
        return failed()

    def _confirm_stopped(self, plan: _TurnPlan, launch: _Launch) -> None:
        if launch.proc is None or launch.stopped:
            return
        if launch.stopping:  # the stop was tried in this turn and failed: no renewed commands, no fresh budget
            raise EvidenceNotSealed(f"container {plan.name} may still write and could not be stopped")
        launch.stopping = self._stop_owned(plan, launch.proc)
        if not launch.stopping["container_absent"]:
            raise EvidenceNotSealed(f"container {plan.name} may still write and could not be stopped")
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
        except BaseException as failure:
            try:  # the same two steps as on success
                self._confirm_stopped(plan, launch)
                self._seal(output, plan)
            except BaseException as cleanup_error:  # an interrupt here counts too: the evidence goes
                self._quarantine(output, plan)  # raises EvidenceNotSealed unless the folder was removed
                if isinstance(failure, Exception) and not isinstance(failure, EvidenceNotSealed):  # say it, with the cause
                    detail = str(cleanup_error) if isinstance(cleanup_error, EvidenceNotSealed) else type(cleanup_error).__name__
                    raise EvidenceNotSealed(f"the turn failed and its container or evidence could not be secured ({detail})") from failure
            raise  # an interrupt, a failure already reported as EvidenceNotSealed, or one after which all was secured
        try:
            self._confirm_stopped(plan, launch)
            self._seal(output, plan)
        except BaseException as error:
            self._quarantine(output, plan)
            if isinstance(error, EvidenceNotSealed):
                raise
            raise EvidenceNotSealed("the evidence could not be sealed") from error
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
