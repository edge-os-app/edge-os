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
from collections.abc import Callable
from typing import Any

import docker_turn_runner
from docker_turn_runner import HERE, LABEL, DockerHermesTurnRunner
from leak_scan import encodings
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage
from provider_guard import GuardPolicy

REDACTED = "[REDACTED]"
MAX_SCANNED_BYTES = 64 * 1024 * 1024
MAX_STDOUT_BYTES = 1024 * 1024  # the host keeps at most this much of the job's own output
MAX_CREDENTIAL_BYTES = 64 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024  # a result file larger than this is not read: the turn ends as UNKNOWN
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
    job_deadline: float  # the job must be done by this time; all setup before the launch comes out of it
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
        started = time.monotonic()  # the one deadline counts from here: everything the turn does is inside it
        secret = self._read_credential(source) if source is not None else None
        job_deadline = started + timeout
        deadline = job_deadline + grace
        return _TurnPlan(sequence, f"p05-{run_id}-{self._token}-{sequence:02d}", run_id, image, policy, secret, timeout,
                         budget, forbidden, job_deadline, deadline, deadline - max(0.0, min(0.5, grace / 10)))

    @staticmethod
    def _read_credential(source: Path) -> str:
        """Read the credential without blocking. A pipe, a device or a folder is refused; a link to a file is followed."""
        try:
            fd = os.open(source, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            raise CredentialUnavailable("the credential file could not be read") from None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise CredentialUnavailable("the credential path is not a plain file")
            raw = os.read(fd, MAX_CREDENTIAL_BYTES + 1)
        except OSError:
            raise CredentialUnavailable("the credential file could not be read") from None
        finally:
            os.close(fd)
        if len(raw) > MAX_CREDENTIAL_BYTES:
            raise CredentialUnavailable("the credential file is too large")
        try:
            secret = raw.decode("utf-8").strip()  # an editor or secret store adds a newline
        except UnicodeDecodeError:
            raise CredentialUnavailable("the credential file could not be read") from None
        if not secret:
            raise CredentialUnavailable("the credential file is empty")
        return secret

    # --- Sealing evidence -----------------------------------------------------------------------------------------

    _DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    @classmethod
    def _open_dir(cls, parent: int, name: str) -> int:
        """Open a folder by name relative to the folder `parent`, never through a link, and make it ours (mode 700).

        A locked folder gets a no-follow mode change first. A link that was swapped in fails here (ELOOP or ENOTDIR).
        """
        try:
            fd = os.open(name, cls._DIR_FLAGS, dir_fd=parent)
        except PermissionError:
            os.chmod(name, 0o700, dir_fd=parent, follow_symlinks=False)
            fd = os.open(name, cls._DIR_FLAGS, dir_fd=parent)
        try:
            os.fchmod(fd, 0o700)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @classmethod
    def _walk(cls, root: Path, until: float, visit: Callable[[int, str, int], bool | None], timeout: type[BaseException],
              remove_dirs: bool) -> None:
        """Walk `root` depth first on directory descriptors. Never follows a link. Ticks the clock at every step.

        `visit(dir_fd, name, mode)` is called for every entry that is not a folder; it returns nothing or a value the
        caller collects itself. Folders are entered through `_open_dir`; with `remove_dirs` each emptied folder is removed.
        Entries are read one at a time, so a huge folder cannot be read whole before the next clock check.
        """
        parent_fd = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY)
        frames: list[tuple[int, str, int, Any, Any]] = []  # (descriptor, name, parent descriptor, scan, iterator)
        try:
            fd = cls._open_dir(parent_fd, root.name)
            scan = os.scandir(fd)
            frames.append((fd, root.name, parent_fd, scan, iter(scan)))
            while frames:
                if time.monotonic() > until:  # every step ticks the clock, including leaving an empty folder
                    raise timeout("the walk passed its time limit")
                fd, name, parent, scan, entries = frames[-1]
                entry = next(entries, None)
                if entry is None:
                    frames.pop()
                    scan.close()
                    os.close(fd)
                    if remove_dirs:
                        os.rmdir(name, dir_fd=parent)
                    continue
                child = entry.name
                mode = os.stat(child, dir_fd=fd, follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    child = visit(fd, child, mode) or child  # a visit may rename a folder before it is entered
                    below = cls._open_dir(fd, child)
                    try:
                        scan = os.scandir(below)
                    except BaseException:
                        os.close(below)
                        raise
                    frames.append((below, child, fd, scan, iter(scan)))
                else:
                    visit(fd, child, mode)
        finally:
            for fd, _name, _parent, scan, _entries in frames:
                scan.close()
                os.close(fd)
            os.close(parent_fd)

    @classmethod
    def _redact(cls, folder: Path, secret: str | None, deadline: float) -> bool:
        """Remove the credential from every file and name under `folder`. True when something held it.

        With no credential, the walk still runs: links, pipes, sockets and devices are removed, so nothing the host reads
        later can block it or lead it outside `folder`.

        Works on directory descriptors and never follows a link, so a container that is still writing cannot lead it
        outside `folder`. Links, pipes, sockets and devices are removed without being opened. Any error propagates.
        """
        forms, found, seen = (encodings(secret) if secret else []), [False], [0]

        def visit(dir_fd: int, name: str, mode: int) -> str | None:
            seen[0] += 1
            if seen[0] > MAX_ENTRIES:
                raise EvidenceNotSealed("the output holds more entries than can be scanned")
            raw = os.fsencode(name)  # a name that is not valid text is still bytes
            if any(form in raw for form in forms):  # rename BEFORE descending, so the folder's files are still sealed
                found[0] = True
                renamed = f"redacted-name-{hashlib.sha256(raw).hexdigest()[:8]}-{uuid.uuid4().hex[:8]}"  # unique: no collision
                os.rename(name, renamed, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                name = renamed
            if stat.S_ISDIR(mode):
                return name
            if not stat.S_ISREG(mode):
                os.unlink(name, dir_fd=dir_fd)
                return None
            if forms:
                found[0] |= cls._seal_file(dir_fd, name, forms)
            return None

        cls._walk(folder, deadline, visit, EvidenceNotSealed, remove_dirs=False)
        return found[0]

    @staticmethod
    def _seal_file(dir_fd: int, name: str, forms: list[bytes]) -> bool:
        """Seal one file through a descriptor. A link or a pipe swapped in for it is removed, never followed or read."""
        def open_nofollow(flags: int) -> int:
            return os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)

        try:
            fd = open_nofollow(os.O_RDONLY)
        except PermissionError:  # a locked file: change its own mode, never a link's target
            os.chmod(name, 0o600, dir_fd=dir_fd, follow_symlinks=False)
            fd = open_nofollow(os.O_RDONLY)
        except OSError:  # a link swapped in (ELOOP) or a pipe with no writer: remove the name
            os.unlink(name, dir_fd=dir_fd)
            return True
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SCANNED_BYTES:  # not a plain file, or too large to scan
                os.unlink(name, dir_fd=dir_fd)
                return True
            os.fchmod(fd, 0o600)
            chunks = []
            while chunk := os.read(fd, 1 << 20):
                chunks.append(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)
        if not any(form in data for form in forms):
            return False
        for form in forms:
            data = data.replace(form, REDACTED.encode())
        out = open_nofollow(os.O_WRONLY)
        try:
            after = os.fstat(out)
            if (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino):  # the name now points elsewhere: drop it
                os.unlink(name, dir_fd=dir_fd)
                return True
            os.ftruncate(out, 0)
            view = memoryview(data)
            while view:
                view = view[os.write(out, view):]
        finally:
            os.close(out)
        return True

    @classmethod
    def _remove_tree(cls, root: Path, until: float) -> None:
        """Remove `root` and everything under it without ever following a link. Raises `TimeoutError` after `until`.

        A folder that a still-running container swaps for a link is unlinked as a link and never entered. A very deep
        tree needs more descriptors than the process may hold; that raises, and the caller moves the tree instead.
        """
        cls._walk(root, until, lambda dir_fd, name, mode: None if stat.S_ISDIR(mode) else os.unlink(name, dir_fd=dir_fd),
                  TimeoutError, remove_dirs=True)

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
            raise EvidenceNotSealed(f"evidence that may hold the credential could not be removed or moved ({type(error).__name__})") from None
        if interrupt is not None:
            raise interrupt
        raise EvidenceNotSealed(f"evidence that may hold the credential was not removed in time; it is in the private folder {held.name}") from None

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
        try:
            return self._redact(output, plan.secret, plan.deadline)
        except BaseException as error:
            self._quarantine(output, plan)
            if isinstance(error, EvidenceNotSealed):
                raise EvidenceNotSealed(str(error)) from None  # its cause may name a file that holds the credential
            raise EvidenceNotSealed(f"the evidence could not be sealed ({type(error).__name__})") from None

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

    @staticmethod
    def _cap_stdout(sink: Any, returned: bytes | None, secret: str | None) -> None:
        """Keep the job's output only if it fits in MAX_STDOUT_BYTES; otherwise drop it whole and leave a note.

        Dropping, not cutting: a cut at any offset could split the credential, and a split part is not found by sealing.
        Emptying a file is one step, whatever its size. `secret` is unused and kept for the callers' symmetry.
        """
        if returned:  # a process that handed its output back instead of writing it to the file
            if len(returned) <= MAX_STDOUT_BYTES:
                sink.write(returned)
            else:
                sink.write(b"x" * (MAX_STDOUT_BYTES + 1))  # marks the file as over the limit, so it is dropped below
        sink.flush()
        if os.fstat(sink.fileno()).st_size > MAX_STDOUT_BYTES:
            os.ftruncate(sink.fileno(), 0)
            os.pwrite(sink.fileno(), b"[the job's output was larger than 1 MiB and was not kept]\n", 0)

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
                if launch.proc is not None:  # with no job launched, the output holds nothing the job could write
                    self._seal(output, plan)
            except BaseException as cleanup_error:  # an interrupt here counts too: the evidence goes
                self._quarantine(output, plan)  # raises EvidenceNotSealed unless the folder was removed
                if isinstance(failure, Exception) and not isinstance(failure, EvidenceNotSealed):  # say it, with the cause
                    detail = str(cleanup_error) if isinstance(cleanup_error, EvidenceNotSealed) else type(cleanup_error).__name__
                    secured = EvidenceNotSealed(f"the turn failed and its container or evidence could not be secured ({detail})")
                    if isinstance(failure, OSError):  # an OS error may name a file that holds the credential
                        raise secured from None
                    raise secured from failure
            raise  # an interrupt, a failure already reported as EvidenceNotSealed, or one after which all was secured
        try:
            self._confirm_stopped(plan, launch)
            if launch.proc is not None:  # with no job launched, the output holds nothing the job could write
                self._seal(output, plan)
        except BaseException as error:
            self._quarantine(output, plan)
            if isinstance(error, EvidenceNotSealed):
                raise EvidenceNotSealed(str(error)) from None
            raise EvidenceNotSealed(f"the evidence could not be sealed ({type(error).__name__})") from None
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
        # The job's own output goes to a file inside the output folder, never into host memory. After the container is
        # gone the file is cut to MAX_STDOUT_BYTES, and the lifecycle seals it with the rest of the output.
        if time.monotonic() >= plan.job_deadline:  # setup used the whole job budget: start nothing, so nothing was sent
            return HermesTurnResult(status="PROVIDER_FAILED", text=None, usage=Usage(), request_count=0,
                                    observed={"guard_admitted": 0}, error_class="DeadlinePassedBeforeLaunch")
        sink_fd = os.open(output / "host-captured-stdout.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(sink_fd, "wb") as sink:
            returned = None
            try:
                launch.proc = proc = subprocess.Popen(argv, stdout=sink, stderr=subprocess.STDOUT)
                try:  # setup time since the plan was made comes out of the wait, never on top of it
                    returned, _ = proc.communicate(timeout=max(0.0, plan.job_deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    self._confirm_stopped(plan, launch)  # raises if the container is still there after the kill
                    (task_dir / "container-lifecycle.json").write_text(json.dumps(launch.stopping, indent=1) + "\n")
                    return HermesTurnResult(status="TIMED_OUT", text=None, usage=Usage(), request_count=None, observed={},
                                            error_class="TimeoutExpired")
                # Whatever the client's exit code, the container may still run (a client that lost its daemon exits with
                # an error while the container goes on). Verify it is gone before any evidence is touched.
                self._confirm_stopped(plan, launch)
            finally:  # on every path, the host keeps at most MAX_STDOUT_BYTES of the job's output
                self._cap_stdout(sink, returned, plan.secret)
        echoed = self._seal(output, plan)  # sealed here for the result check; the lifecycle seals again on every path
        if proc.returncode != 0:
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerExit")
        raw = self._read_result(output, plan)
        if raw is None:
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerResultUnreadable")
        if plan.secret and self._holds_secret(raw, plan.secret):  # JSON escapes can hide it from the byte-level scan
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="CredentialEchoed")
        try:
            mapped = self._map(raw)
            guard = raw["guard"]
            observed = {**mapped.observed, "guard_admitted": guard["admitted_count"], "guard_seen": guard["seen_count"],
                        "guard_refusal_reasons": sorted({r["reason"] for r in guard["evidence"] if not r["admitted"]})}
        except (ValueError, RecursionError, KeyError, TypeError, AttributeError):  # a result the host cannot use
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerResultUnreadable")
        mapped = replace(mapped, observed=observed)
        if echoed:
            return replace(mapped, status="UNKNOWN", text=None, error_class="CredentialEchoed")
        return mapped

    @staticmethod
    def _holds_secret(value: Any, secret: str) -> bool:
        """True when any decoded string of the result, key or value, at any depth, holds the credential in any form.

        It uses the same forms as sealing (`leak_scan.encodings`), compared without regard to case, so the two checks
        agree on what "holds the credential" means. Decoding can undo escapes that hid a form from the byte scan.
        """
        forms = [form.lower() for form in encodings(secret)]
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                data = item.encode("utf-8", "surrogatepass").lower()
                if any(form in data for form in forms):
                    return True
            elif isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        return False

    @classmethod
    def _read_result(cls, output: Path, plan: _TurnPlan) -> dict[str, Any] | None:
        """Read the job's result file within the deadline: no link followed, no blocking, a plain file of bounded size.

        Returns None when the file is missing, is not a plain file, is too large, cannot be parsed, or the deadline passed.
        """
        if time.monotonic() > plan.deadline:
            return None
        try:
            folder = os.open(output, cls._DIR_FLAGS)
        except OSError:
            return None
        try:
            fd = os.open("container-result.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        except OSError:
            os.close(folder)
            return None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RESULT_BYTES:
                return None
            data = os.read(fd, MAX_RESULT_BYTES + 1)
        except OSError:
            return None
        finally:
            os.close(fd)
            os.close(folder)
        if len(data) > MAX_RESULT_BYTES or time.monotonic() > plan.deadline:
            return None
        try:
            parsed = json.loads(data.decode("utf-8"))
        except (ValueError, RecursionError, UnicodeDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None
