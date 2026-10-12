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
import re
import resource
import selectors
import shutil
import signal
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
MAX_SCANNED_BYTES = 8 * 1024 * 1024  # evidence files are small; a larger file is removed whole, unread
MAX_ESCAPES = 65_536  # more JSON escapes than this in one file: too costly to undo in time, so it is treated as holding
MAX_STDOUT_BYTES = 1024 * 1024  # the host keeps at most this much of the job's own output
MAX_CREDENTIAL_BYTES = 64 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024  # a result file larger than this is not read: the turn ends as UNKNOWN
MAX_ENTRIES = 10_000  # more files and folders than this in one output are not scanned: the output is removed
ENTRYPOINT = "/opt/hermes/.venv/bin/python"


_JSON_ESCAPE = re.compile(rb"\\u([0-9a-fA-F]{4})|\\([\"\\/])")


def _json_unescaped(data: bytes) -> bytes:
    """`data` with JSON string escapes undone (\\uXXXX, \\", \\\\, \\/), in one linear pass. Not a JSON parser."""
    def undo(match: re.Match[bytes]) -> bytes:
        if match.group(1) is not None:
            return chr(int(match.group(1), 16)).encode("utf-8", "surrogatepass")
        return match.group(2)
    return _JSON_ESCAPE.sub(undo, data)


def holds_credential(data: bytes, forms: list[bytes], until: float = math.inf) -> bool:
    """The one test for "these bytes hold the credential": any form, any case, raw or with JSON escapes undone.

    The clock is checked between steps (each one linear in `data`); past `until` it raises `TimeoutError`.
    """
    def tick() -> None:
        if time.monotonic() > until:
            raise TimeoutError("the credential check passed its time limit")

    def found_in(text: bytes) -> bool:
        for form in lowered:
            tick()
            if form in text:
                return True
        return False

    if not forms:
        return False
    lowered = [form.lower() for form in forms]
    tick()
    if found_in(data.lower()):
        return True
    if b"\\" not in data:  # nothing escaped: the raw check was the whole check
        return False
    if data.count(b"\\") > MAX_ESCAPES:  # bounded cost: rather than spend the deadline undoing them, assume the worst
        return True
    tick()
    return found_in(_json_unescaped(data).lower())



BASE_DOCKER_CLI = docker_turn_runner.docker  # the base helper as shipped; a test may install a stand-in in its place
MAX_CLI_ANSWER_BYTES = 64 * 1024  # an inspect or ps answer is a few lines; anything larger is not a real answer


def bounded_docker(*args: str, timeout: float) -> subprocess.CompletedProcess[str]:
    """Run one docker CLI command that cannot outlast `timeout` or fill host memory, whatever the CLI prints.

    The base helper keeps the whole answer in memory and does work after its timeout that grows with the answer, so a
    CLI that streams output can hold the call long past its budget. Here at most `MAX_CLI_ANSWER_BYTES` are read, only
    until the deadline; then the command's whole process group is killed and reaped. A larger answer is a failure.
    A stand-in installed on the base helper (tests) is used as it is.
    """
    if docker_turn_runner.docker is not BASE_DOCKER_CLI:
        return docker_turn_runner.docker(*args, timeout=timeout, check=False)
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen(
        ["docker", *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    chunks: list[bytes] = []
    size, ended = 0, False
    try:
        fd = proc.stdout.fileno()
        os.set_blocking(fd, False)
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            while size <= MAX_CLI_ANSWER_BYTES and (left := deadline - time.monotonic()) > 0:
                if not selector.select(left):
                    continue
                try:
                    chunk = os.read(fd, MAX_CLI_ANSWER_BYTES + 1 - size)
                except BlockingIOError:
                    continue
                if not chunk:
                    ended = True
                    break
                chunks.append(chunk)
                size += len(chunk)
    finally:
        proc.stdout.close()
        if ended:
            try:
                proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                ended = False
        if not ended or proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()  # SIGKILL cannot be ignored, so this returns at once
    if not ended or size > MAX_CLI_ANSWER_BYTES:
        raise TimeoutError("the docker CLI did not answer within its budget and size")
    return subprocess.CompletedProcess(["docker", *args], proc.returncode, b"".join(chunks).decode("utf-8", "replace"), "")



def _limit_client_file_size() -> None:
    """Runs in the job client before it starts: no file it writes, its stdout included, may pass MAX_STDOUT_BYTES + 1.

    Without it the job decides how much reaches host disk while it runs, and writing back gigabytes stalls every later
    disk step (closing the file, the ledger's commit) past the deadline. A client that writes more gets SIGXFSZ and
    exits; the stop step then verifies the container is gone, and the over-limit stdout is moved aside whole.
    It only calls setrlimit: no lock or import that another thread of the parent could hold at the fork.
    """
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_STDOUT_BYTES + 1, MAX_STDOUT_BYTES + 1))


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
    deadline: float  # monotonic time by which everything the turn does must be done, cleanup included; never renewed
    stop_deadline: float  # the stop step must be done by this time; the rest is kept for sealing and removal
    seal_deadline: float  # sealing stops by this time; the rest is kept for removing evidence that could not be sealed


@dataclass
class _Launch:
    """What the lifecycle needs to know about the job process."""

    proc: Any = None
    stopped: bool = False  # the client exited by itself, or the container was verified gone
    stopping: dict[str, Any] = field(default_factory=dict)
    sealed: bool = False  # sealed after the container was verified gone; nothing can change it, so it is not sealed again


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
                         budget, forbidden, job_deadline, deadline, deadline - max(0.0, min(0.5, grace / 10)),
                         deadline - max(0.0, min(0.25, grace / 20)))

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
    def _redact(cls, folder: Path, secret: str | None, deadline: float,
                hold: Callable[[int, str], None] | None = None) -> bool:
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
            if holds_credential(raw, forms):  # the same test as contents; rename BEFORE descending, so the folder's files are still sealed
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
                found[0] |= cls._seal_file(dir_fd, name, forms, deadline, hold)
            return None

        cls._walk(folder, deadline, visit, EvidenceNotSealed, remove_dirs=False)
        return found[0]

    @staticmethod
    def _seal_file(dir_fd: int, name: str, forms: list[bytes], deadline: float = float("inf"),
                   hold: Callable[[int, str], None] | None = None) -> bool:
        """Seal one file through a descriptor. A link or a pipe swapped in for it is removed, never followed or read.

        A plain file too large to scan is given to `hold` (moved aside in one step), because freeing it takes time that
        grows with its size; with no `hold` it is unlinked.
        """
        def open_nofollow(flags: int) -> int:
            return os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)

        def tick() -> None:  # between every step that is linear in the file's size
            if time.monotonic() > deadline:
                raise EvidenceNotSealed("sealing passed its time limit")

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
            if not stat.S_ISREG(info.st_mode):  # not a plain file: removed unread
                os.unlink(name, dir_fd=dir_fd)
                return True
            if info.st_size > MAX_SCANNED_BYTES:  # too large to scan: treated as holding the credential
                (hold or (lambda folder, entry: os.unlink(entry, dir_fd=folder)))(dir_fd, name)
                return True
            os.fchmod(fd, 0o600)
            chunks = []
            while True:
                tick()
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)
        if not holds_credential(data, forms, deadline):
            return False
        for form in forms:
            tick()
            data = data.replace(form, REDACTED.encode())
        if holds_credential(data, forms, deadline):  # a copy that replacing cannot reach (case, JSON escapes): the file goes whole
            os.unlink(name, dir_fd=dir_fd)
            return True
        tick()
        out = open_nofollow(os.O_WRONLY)
        try:
            after = os.fstat(out)
            if (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino):  # the name now points elsewhere: drop it
                os.unlink(name, dir_fd=dir_fd)
                return True
            os.ftruncate(out, 0)
            view = memoryview(data)
            while view:
                tick()
                view = view[os.write(out, view[: 1 << 20]):]
        finally:
            os.close(out)
        return True

    @classmethod
    def _remove_tree(cls, root: Path, until: float) -> None:
        """Remove `root` and everything under it without ever following a link. Raises `TimeoutError` after `until`.

        A folder that a still-running container swaps for a link is unlinked as a link and never entered. A very deep
        tree needs more descriptors than the process may hold; that raises, and the caller moves the tree instead.
        With a finite `until`, a plain file larger than the scan limit is not unlinked: freeing it takes time that grows
        with its size, which no clock check can cut short. That raises too, and the caller moves the tree.
        """
        def visit(dir_fd: int, name: str, mode: int) -> None:
            if stat.S_ISDIR(mode):
                return
            if (until != math.inf and stat.S_ISREG(mode)
                    and os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_size > MAX_SCANNED_BYTES):
                raise TimeoutError("a file too large to free on the clock")
            os.unlink(name, dir_fd=dir_fd)

        cls._walk(root, until, visit, TimeoutError, remove_dirs=True)

    @staticmethod
    def _hold(output: Path, dir_fd: int, name: str) -> None:
        """Move one entry out of `output` in one step, into the turn's private holding folder (mode 700).

        Freeing a large file takes time that grows with its size, and the job decides the size, so it is never done
        while the turn's clock runs. `purge_quarantine` frees the folder between turns.
        """
        held = output.parent.parent / f"quarantine-{output.parent.name}-held"
        held.mkdir(mode=0o700, exist_ok=True)
        held_fd = os.open(held, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fchmod(held_fd, 0o700)
            os.rename(name, uuid.uuid4().hex, src_dir_fd=dir_fd, dst_dir_fd=held_fd)
        finally:
            os.close(held_fd)

    def _quarantine(self, output: Path, plan: _TurnPlan) -> None:
        """Take evidence that cannot be proved clean out of reach. It returns when the folder is gone, else raises `EvidenceNotSealed`.

        Removal has what is left of the turn's one deadline and never more: once it has passed, removal does not start.
        Whatever is not removed by then is MOVED, in one step, to a private `quarantine-*` folder beside the turn folders,
        and the turn says so. `purge_quarantine` removes those folders between turns, when no clock runs.
        """
        interrupt = None
        try:
            self._remove_tree(output, plan.deadline)
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
            return self._redact(output, plan.secret, plan.seal_deadline,
                                lambda dir_fd, name: self._hold(output, dir_fd, name))
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
            return bounded_docker(*args, timeout=min(60.0, left()))

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

    @classmethod
    def _cap_stdout(cls, sink: Any, returned: bytes | None, output: Path) -> None:
        """Keep the job's output only if it fits in MAX_STDOUT_BYTES; otherwise move it whole aside and leave a note.

        Whole, not cut: a cut at any offset could split the credential, and a split part is not found by sealing. Moved,
        not emptied: emptying or deleting a file takes time that grows with its size, and the job decides the size, so
        the file goes to the private holding folder in one step and `purge_quarantine` frees it between turns.
        """
        if returned:  # a process that handed its output back instead of writing it to the file
            if len(returned) <= MAX_STDOUT_BYTES:
                sink.write(returned)
            else:
                sink.write(b"x" * (MAX_STDOUT_BYTES + 1))  # marks the file as over the limit, so it is dropped below
        sink.flush()
        info = os.fstat(sink.fileno())
        if info.st_size <= MAX_STDOUT_BYTES:
            return
        name = "host-captured-stdout.log"
        folder = os.open(output, cls._DIR_FLAGS)
        try:
            now = os.stat(name, dir_fd=folder, follow_symlinks=False)
            if (now.st_dev, now.st_ino) != (info.st_dev, info.st_ino):  # the job moved it: sealing deals with what is there
                return
            cls._hold(output, folder, name)
            try:
                note = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
            except OSError:  # a job that still runs took the name: the note is only a courtesy
                return
            try:
                os.write(note, b"[the job's output was larger than 1 MiB and was not kept]\n")
            finally:
                os.close(note)
        finally:
            os.close(folder)

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
                if launch.proc is not None and not launch.sealed:  # with no job launched, the output holds nothing the job could write
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
            if launch.proc is not None and not launch.sealed:  # with no job launched, the output holds nothing the job could write
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
                launch.proc = proc = subprocess.Popen(argv, stdout=sink, stderr=subprocess.STDOUT,
                                                      preexec_fn=_limit_client_file_size)
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
                self._cap_stdout(sink, returned, output)
        echoed = self._seal(output, plan)  # sealed here for the result check; the lifecycle seals on every other path
        launch.sealed = True
        if proc.returncode != 0:
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerExit")
        read = self._read_result(output, plan)
        if read is None:  # sealing removes a result that held the credential, so say why it is gone
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="CredentialEchoed" if echoed else "ContainerResultUnreadable")
        raw, data = read
        # The same test as sealing, on the same bytes: decoding can undo escapes that hid a form from a plain byte scan.
        if plan.secret and holds_credential(data, encodings(plan.secret)):
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="CredentialEchoed")
        if time.monotonic() > plan.deadline:  # the checks above are linear, but the deadline still decides
            return HermesTurnResult(status="UNKNOWN", text=None, usage=Usage(), request_count=None, observed={},
                                    error_class="ContainerResultUnreadable")
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

    @classmethod
    def _read_result(cls, output: Path, plan: _TurnPlan) -> tuple[dict[str, Any], bytes] | None:
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
        return (parsed, data) if isinstance(parsed, dict) else None
