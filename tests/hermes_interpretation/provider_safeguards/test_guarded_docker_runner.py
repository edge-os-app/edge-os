"""The host runner of the guarded container: the dummy credential must stay out of saved evidence on EVERY exit path.

The docker command line is the only stand-in: a stub process writes the credential into the output folder the way a
failing job could, then exits or times out. The runner and its redaction are the real ones.
"""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import pytest

import guarded_docker_runner
from edge_os_api.research.hermes_interpreter import HermesTurn
from guarded_docker_runner import GuardedDockerTurnRunner
from leak_scan import find_leaks
from provider_guard import GuardPolicy

SENTINEL = "sk-test-DUMMY-SENTINEL-9f3a71c2e8b54d06"
POLICY = GuardPolicy(model="m", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500)
TURN = HermesTurn("attempt-1", "prompt", "task", "m", "route", 4096)


class StubProcess:
    """Writes the secret where a job would write evidence, then ends as told."""

    def __init__(self, argv, **_kwargs) -> None:
        output = next(part.split("src=")[1].split(",")[0] for part in argv if part.endswith("dst=/job/output"))
        (Path(output) / "partial.log").write_text(f"trace with {SENTINEL}")
        (Path(output) / "binary.bin").write_bytes(b"\xff\xfe" + SENTINEL.encode() + b"\x80")  # not UTF-8 text
        (Path(output) / "encoded.txt").write_text(base64.b64encode(f"Bearer {SENTINEL}".encode()).decode())
        self.returncode, self.argv = StubProcess.returncode, argv

    returncode = 3
    timeout = False

    explode = False
    stdout = f"stdout with {SENTINEL}".encode()

    def communicate(self, timeout=None):
        if StubProcess.timeout and timeout is not None and timeout > 25:
            raise subprocess.TimeoutExpired("docker", timeout)
        if StubProcess.explode:
            raise RuntimeError("the pipe broke")
        return StubProcess.stdout, None

    def kill(self) -> None:
        pass


@pytest.mark.parametrize("timeout, returncode, status", [(False, 3, "UNKNOWN"), (True, 0, "TIMED_OUT")])
def test_the_credential_is_removed_from_evidence_when_the_job_fails_or_times_out(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: bool, returncode: int, status: str) -> None:
    StubProcess.timeout, StubProcess.returncode, StubProcess.explode = timeout, returncode, False
    StubProcess.stdout = f"stdout with {SENTINEL}".encode()
    real_popen = subprocess.Popen

    def popen(argv, **kwargs):  # only the job's own `docker run` is stood in for; the cleanup commands run for real
        return StubProcess(argv, **kwargs) if argv[:2] == ["docker", "run"] else real_popen(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", popen)
    credential = tmp_path / "private-credential"
    credential.write_text(SENTINEL)
    runner = GuardedDockerTurnRunner(image="unused", run_id="redact-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                                     credential_file=credential, script_for=lambda turn: {}, timeout_seconds=60)

    result = runner.run_turn(TURN)

    assert result.status == status
    assert find_leaks(tmp_path, SENTINEL, exclude=[credential, *tmp_path.glob("evidence/turn-*/input.json")]) == []


def test_a_credential_file_that_ends_in_a_newline_is_still_removed_from_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    StubProcess.timeout, StubProcess.returncode, StubProcess.explode = False, 3, False
    StubProcess.stdout = f"stdout with {SENTINEL}".encode()
    real_popen = subprocess.Popen
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: StubProcess(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    credential = tmp_path / "private-credential"
    credential.write_text(SENTINEL + "\n")  # an editor or a secret store often adds the newline
    runner = GuardedDockerTurnRunner(image="unused", run_id="redact-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                                     credential_file=credential, script_for=lambda turn: {}, timeout_seconds=60)

    runner.run_turn(TURN)

    assert find_leaks(tmp_path, SENTINEL, exclude=[credential, *tmp_path.glob("evidence/turn-*/input.json")]) == []


def run_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, prepare=None, explode=False, stdout: bytes | None = None, expect_raise=None):
    StubProcess.timeout, StubProcess.returncode, StubProcess.explode = False, 3, explode
    StubProcess.stdout = stdout if stdout is not None else f"stdout with {SENTINEL}".encode()
    real_popen = subprocess.Popen
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: StubProcess(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    credential = tmp_path / "private-credential"
    credential.write_text(SENTINEL)
    runner = GuardedDockerTurnRunner(image="unused", run_id="redact-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                                     credential_file=credential, script_for=lambda turn: {}, timeout_seconds=60)
    if prepare:
        monkeypatch.setattr(StubProcess, "extra", prepare, raising=False)
    if expect_raise:
        with pytest.raises(expect_raise):
            runner.run_turn(TURN)
    else:
        runner.run_turn(TURN)
    return credential


def leaks(tmp_path: Path, credential: Path) -> list[str]:
    return find_leaks(tmp_path, SENTINEL, exclude=[credential, *tmp_path.glob("evidence/turn-*/input.json")])


def test_output_that_is_not_utf8_text_on_the_process_pipe_is_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    credential = run_with(tmp_path, monkeypatch, stdout=b"\xff\xfe" + SENTINEL.encode() + b"\x80")

    assert leaks(tmp_path, credential) == []


def test_evidence_is_sealed_even_when_the_run_fails_in_an_unexpected_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    credential = run_with(tmp_path, monkeypatch, explode=True, expect_raise=RuntimeError)

    assert leaks(tmp_path, credential) == []


def hostile_evidence(self_output: Path) -> None:
    pass


def test_links_hidden_folders_read_only_files_odd_names_and_huge_files_are_all_sealed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path / "outside-file.txt"
    outside.write_text(f"not evidence {SENTINEL}")
    original_init = StubProcess.__init__

    def init(self, argv, **kwargs):
        original_init(self, argv, **kwargs)
        output = Path(next(part.split("src=")[1].split(",")[0] for part in argv if part.endswith("dst=/job/output")))
        (output / "link").symlink_to(outside)                                   # a link out of the evidence folder
        hidden = output / "hidden"; hidden.mkdir(); (hidden / "x.log").write_text(SENTINEL); hidden.chmod(0o000)
        locked = output / "locked"; locked.mkdir(); (locked / "y.log").write_text(SENTINEL); (locked / "y.log").chmod(0o444); locked.chmod(0o555)
        (output / f"name-{SENTINEL}.txt").write_text("clean content")           # the secret in a file NAME
        (output / "hex.txt").write_text(SENTINEL.encode().hex())
        with (output / "huge.bin").open("wb") as stream:                          # too large to scan: not kept
            stream.truncate(80 * 1024 * 1024)
    monkeypatch.setattr(StubProcess, "__init__", init)

    credential = run_with(tmp_path, monkeypatch)

    assert [name for name in leaks(tmp_path, credential) if name != "outside-file.txt"] == []  # the outside file is the bait
    assert outside.read_text() == f"not evidence {SENTINEL}", "a link must never lead the redaction outside the evidence folder"
    assert not any("huge.bin" in str(path) for path in tmp_path.glob("evidence/**/*"))


# --- Repairs after gate verdict 3/3: one captured plan per turn, no blocking on odd entries, a time bound ----------------

import os
import threading
import time
from decimal import Decimal

import docker_turn_runner
from edge_os_api.research.hermes_interpreter import HermesTurn as Turn
from guarded_docker_runner import EvidenceNotSealed
from guarded_turn_runner import GuardedTurnRunner
from spend_ledger import SpendLedger, TokenPrice

OLD = "sk-test-DUMMY-OLD-0a1b2c3d4e5f60718293a4b5c6d7e8f9"
NEW = "sk-test-DUMMY-NEW-9f8e7d6c5b4a39281706f5e4d3c2b1a0"
RESERVATION = Decimal("0.054848")  # (12,000 + 64) x 2.00 / 1e6 + 4,096 x 7.50 / 1e6


def plain_bytes_leak(root: Path, secret: str) -> list[str]:
    """Independent oracle: plain bytes only, no shared scanner. Evidence input scripts and the source file are skipped."""
    found = []
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.name not in {"input.json", "credential"} \
                and secret.encode() in path.read_bytes():
            found.append(str(path.relative_to(root)))
    return found


def output_folder(argv: list[str]) -> Path:
    return Path(next(part.split("src=")[1].split(",")[0] for part in argv if part.endswith("dst=/job/output")))


@pytest.fixture(autouse=True)
def no_real_docker_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every docker CLI call in these tests answers "no such container" unless a test installs its own answer."""
    def absent(*args, **_kwargs):
        return subprocess.CompletedProcess(args, 1 if args[0] == "inspect" else 0, "", "")
    monkeypatch.setattr(docker_turn_runner, "docker", absent)


def install_process(monkeypatch: pytest.MonkeyPatch, behaviour, returncode: int = 3) -> list[list[str]]:
    """Stands in for the `docker run` process only. `behaviour(output_folder)` runs while the process is alive."""
    launched: list[list[str]] = []
    real_popen = subprocess.Popen

    class Process:
        def __init__(self, argv, **_kwargs) -> None:
            launched.append(list(argv))
            self.returncode, self.output, self.ran = returncode, output_folder(argv), False

        def communicate(self, timeout=None):
            if not self.ran:  # the job's behaviour happens once, however often the runner waits on the process
                self.ran = True
                behaviour(self.output)
            return b"controlled failure", None

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Process(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    return launched


def build(tmp_path: Path, credential: Path | None, **kwargs):
    runner = GuardedDockerTurnRunner(image="unused", run_id="repair-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                                     credential_file=credential, script_for=kwargs.pop("script_for", lambda turn: {}),
                                     timeout_seconds=kwargs.pop("timeout_seconds", 60), **kwargs)
    spend = SpendLedger(tmp_path / "spend.sqlite", cap_usd=Decimal("0.30"), price=TokenPrice(Decimal("2.00"), Decimal("7.50")))
    return runner, spend, GuardedTurnRunner(runner, spend, POLICY, scope_for=lambda turn: turn.attempt_id)


@pytest.mark.parametrize("change", ["replace", "remove"])
def test_the_credential_a_job_was_given_is_sealed_out_of_evidence_even_if_the_source_file_changes_later(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD + "\n")

    def behaviour(output: Path) -> None:
        (output / "provider-error.log").write_text("Authorization: Bearer " + OLD)
        credential.write_text(NEW) if change == "replace" else credential.unlink()

    install_process(monkeypatch, behaviour)
    _, spend, guarded = build(tmp_path, credential)

    result = guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert result.status == "UNKNOWN" and result.error_class == "ContainerExit"
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("UNKNOWN", RESERVATION)


def test_a_credential_file_that_is_gone_before_the_turn_fails_with_a_message_that_names_no_path_or_value(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential-that-is-missing"
    install_process(monkeypatch, lambda output: None)
    _, spend, guarded = build(tmp_path, credential)

    with pytest.raises(RuntimeError) as failure:
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert "credential-that-is-missing" not in str(failure.value) and str(tmp_path) not in str(failure.value)
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("UNKNOWN", RESERVATION)


def test_concurrent_turns_get_distinct_evidence_folders_and_container_names(tmp_path: Path, monkeypatch) -> None:
    arrived = threading.Barrier(2)

    def script(turn):  # both turns are inside the runner before either continues
        arrived.wait(timeout=10)
        return {}

    launched = install_process(monkeypatch, lambda output: None)
    _, spend, guarded = build(tmp_path, None, script_for=script)
    turns = [Turn("attempt-a", "prompt", "task", "m", "route", 4096), Turn("attempt-b", "prompt", "task", "m", "route", 4096)]

    threads = [threading.Thread(target=guarded.run_turn, args=(turn,)) for turn in turns]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    names = [argv[argv.index("--name") + 1] for argv in launched]
    folders = {output_folder(argv) for argv in launched}
    assert len(names) == 2 and len(set(names)) == 2 and len(folders) == 2
    assert sorted(p.name.split("-", 2)[2] for p in (tmp_path / "evidence").iterdir()) == ["attempt-a", "attempt-b"]
    assert spend.committed_usd() == RESERVATION * 2 and {spend.state("attempt-a"), spend.state("attempt-b")} == {"UNKNOWN"}


def test_a_named_pipe_in_the_output_cannot_block_the_runner_and_the_log_beside_it_is_still_sealed(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    pipes: list[Path] = []

    def behaviour(output: Path) -> None:
        os.mkfifo(output / "pipe")
        pipes.append(output / "pipe")
        (output / "provider-error.log").write_text(OLD)

    install_process(monkeypatch, behaviour)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, run_budget_seconds=0.1)
    outcome: list = []
    worker = threading.Thread(target=lambda: outcome.append(runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))), daemon=True)
    started = time.monotonic()
    worker.start()
    worker.join(timeout=5)
    hung = worker.is_alive()
    for pipe in pipes:  # owned cleanup: release a blocked reader if there is one, then remove the test's own pipe
        try:
            os.close(os.open(pipe, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        pipe.unlink(missing_ok=True)
    worker.join(timeout=5)

    assert not hung, "the runner blocked on a named pipe in the evidence"
    assert time.monotonic() - started < 5 and outcome and outcome[0].error_class == "ContainerExit"
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_evidence_that_cannot_be_sealed_in_time_stops_the_turn_and_is_not_left_behind(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    install_process(monkeypatch, lambda output: (output / "provider-error.log").write_text(OLD))
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=-1.0)  # no time at all to seal

    with pytest.raises(EvidenceNotSealed):
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_a_container_that_may_still_run_is_stopped_or_the_turn_fails_before_sealing(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    calls: list[tuple[str, ...]] = []
    state = {"present": True}

    def fake_docker(*args, **_kwargs):
        calls.append(args)
        done = subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0 if state["present"] else 1, f"/{args[1]} repair-test\n", "")
        if args[0] == "kill":
            state["present"] = False
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, "abc\n" if state["present"] else "", "")
        return done

    monkeypatch.setattr(docker_turn_runner, "docker", fake_docker)
    launched = install_process(monkeypatch, lambda output: (output / "late.log").write_text(OLD), returncode=-9)  # the client was killed
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert ("kill", launched[0][launched[0].index("--name") + 1]) in calls
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_a_container_that_is_not_ours_or_will_not_stop_fails_the_turn_without_a_clean_claim(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def stubborn(*args, **_kwargs):
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0, f"/{args[1]} someone-elses-run\n", "")
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, "abc\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(docker_turn_runner, "docker", stubborn)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    install_process(monkeypatch, lambda output: None, returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    with pytest.raises(EvidenceNotSealed):
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))


# --- Repairs after round-5 reviews: one exception-safe lifecycle ----------------------------------------------------

def write_deep_chain(output: Path, depth: int, files: int = 0, secret: str | None = None) -> None:
    """Builds a folder chain longer than the host path limit with directory file descriptors, never with chdir.

    The working directory belongs to the whole process, so a test that changes it can write into another test's folder.
    """
    fd = os.open(output, os.O_RDONLY)
    try:
        for _ in range(depth):
            os.mkdir("a", dir_fd=fd)
            below = os.open("a", os.O_RDONLY, dir_fd=fd)
            os.close(fd)
            fd = below
        names = [f"f{index}.log" for index in range(files)] + ([] if secret is None else ["deep.log"])
        for name in names:
            handle = os.open(name, os.O_WRONLY | os.O_CREAT, 0o644, dir_fd=fd)
            os.write(handle, (secret if name == "deep.log" else "x").encode())
            os.close(handle)
    finally:
        os.close(fd)


def run_expecting(runner, exception) -> None:
    with pytest.raises(exception):
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))


@pytest.mark.parametrize("failure", [RuntimeError("the pipe broke"), KeyboardInterrupt(), subprocess.SubprocessError("x")])
def test_any_failure_while_waiting_for_the_job_stops_the_container_before_the_evidence_is_sealed(tmp_path: Path, monkeypatch, failure) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    calls: list[tuple[str, ...]] = []
    state = {"present": True}

    def fake_docker(*args, **_kwargs):
        calls.append(args)
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0 if state["present"] else 1, f"/{args[1]} repair-test\n", "")
        if args[0] == "kill":
            state["present"] = False
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, "abc\n" if state["present"] else "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(docker_turn_runner, "docker", fake_docker)
    real_popen = subprocess.Popen

    class Process:
        returncode = None

        def __init__(self, argv, **_kw) -> None:
            self.output = output_folder(argv)

        def communicate(self, timeout=None):
            if not state.get("raised"):
                state["raised"] = True
                (self.output / "late.log").write_text(OLD)
                raise failure
            return b"", None

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Process(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, type(failure))

    assert any(call[0] == "kill" for call in calls), "the container was not stopped"
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_a_container_that_cannot_be_stopped_after_a_failure_leaves_no_evidence_behind(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def stubborn(*args, **_kwargs):
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, "abc\n", "")
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0, f"/{args[1]} repair-test\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(docker_turn_runner, "docker", stubborn)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    install_process(monkeypatch, lambda output: (output / "late.log").write_text(OLD), returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, EvidenceNotSealed)

    assert not list((tmp_path / "evidence").glob("turn-*/output"))


def test_a_container_still_present_after_a_timeout_kill_fails_the_turn(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def stubborn(*args, **_kwargs):
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, "abc\n", "")
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0, f"/{args[1]} repair-test\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(docker_turn_runner, "docker", stubborn)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    real_popen = subprocess.Popen

    class Hung:
        returncode = None

        def __init__(self, argv, **_kw) -> None:
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("docker", timeout)
            return b"", None

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Hung(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, EvidenceNotSealed)


@pytest.mark.parametrize("failure", [RuntimeError("boom"), RecursionError("deep"), UnicodeEncodeError("utf-8", "x", 0, 1, "bad"),
                                     PermissionError("locked"), KeyboardInterrupt()])
def test_any_unexpected_error_while_sealing_removes_the_evidence_and_stops_the_turn(tmp_path: Path, monkeypatch, failure) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    install_process(monkeypatch, lambda output: (output / "provider-error.log").write_text(OLD))

    def explode(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(GuardedDockerTurnRunner, "_seal_file", staticmethod(explode))
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, EvidenceNotSealed)

    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_a_directory_chain_longer_than_the_path_limit_cannot_keep_the_credential(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def behaviour(output: Path) -> None:
        write_deep_chain(output, 700, secret=OLD)  # about 1,400 characters of path: more than the host path limit

    install_process(monkeypatch, behaviour)
    runner, _, _ = build(tmp_path, credential)
    try:
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    except EvidenceNotSealed:
        pass

    for output in (tmp_path / "evidence").glob("turn-*/output"):  # sealed in place: read the deep file through descriptors
        fd = os.open(output, os.O_RDONLY)
        try:
            for _ in range(700):
                below = os.open("a", os.O_RDONLY, dir_fd=fd)
                os.close(fd)
                fd = below
            handle = os.open("deep.log", os.O_RDONLY, dir_fd=fd)
            assert OLD.encode() not in os.read(handle, 1 << 16), "the deep file kept the credential"
            os.close(handle)
        finally:
            os.close(fd)


@pytest.mark.parametrize("content", ["", "   \n\t"])
def test_an_empty_credential_file_stops_the_turn_before_any_job_starts(tmp_path: Path, monkeypatch, content: str) -> None:
    credential = tmp_path / "credential"
    credential.write_text(content)
    launched = install_process(monkeypatch, lambda output: None)
    runner, spend, guarded = build(tmp_path, credential)

    with pytest.raises(RuntimeError) as failure:
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert launched == [] and "empty" in str(failure.value)
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("UNKNOWN", RESERVATION)


def test_the_job_is_given_exactly_the_value_the_host_captured_even_if_the_file_changes_in_between(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    given: list[str] = []
    real_popen = subprocess.Popen

    class Process:
        returncode = 3

        def __init__(self, argv, **_kw) -> None:
            mount = next(part for part in argv if part.endswith("dst=/job/credential,readonly"))
            given.append(Path(mount.split("src=")[1].split(",")[0]).read_text())
            self.output = output_folder(argv)

        def communicate(self, timeout=None):
            return b"", None

    def change_the_file_after_capture(turn):  # runs after the host captured the credential and before the job starts
        credential.write_text(NEW)
        return {}

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Process(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential, script_for=change_the_file_after_capture)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert given == [OLD]


def test_two_runner_objects_with_the_same_run_id_do_not_share_container_names(tmp_path: Path, monkeypatch) -> None:
    launched = install_process(monkeypatch, lambda output: None)
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    first = build(tmp_path / "one", None)[0]
    second = build(tmp_path / "two", None)[0]

    first.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    second.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    names = [argv[argv.index("--name") + 1] for argv in launched]
    assert len(set(names)) == 2


def test_a_result_file_that_cannot_be_read_ends_the_turn_as_unknown_not_with_an_exception(tmp_path: Path, monkeypatch) -> None:
    def behaviour(output: Path) -> None:
        (output / "container-result.json").write_text("[" * 100_000)  # deep enough to exhaust the parser's recursion

    install_process(monkeypatch, behaviour, returncode=0)
    runner = build(tmp_path, None)[0]

    result = runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert (result.status, result.error_class) == ("UNKNOWN", "ContainerResultUnreadable")


# --- Repairs after round-6 reviews: removal that cannot fail on locked folders, a stop that must be verified ----------

def docker_double(*, present: bool = True, ps_code: int = 0, owned: bool = True, on_kill=None, record=None):
    """A stand-in for the docker CLI. `present` stays true until a kill (if the container is ours)."""
    state = {"present": present}

    def fake(*args, **kwargs):
        if record is not None:
            record.append((args, kwargs))
        if args[0] == "inspect":
            label = "repair-test" if owned else "someone-elses-run"
            return subprocess.CompletedProcess(args, 0 if state["present"] else 1, f"/{args[1]} {label}\n", "")
        if args[0] == "kill":
            state["present"] = False
            if on_kill:
                on_kill()
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, ps_code, "abc\n" if state["present"] else "", "")
        return subprocess.CompletedProcess(args, 0, "", "")
    return fake


@pytest.mark.parametrize("mode", [0o000, 0o500])
def test_evidence_in_a_locked_folder_is_removed_when_the_container_cannot_be_stopped(tmp_path: Path, monkeypatch, mode: int) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # present, not ours, so never stoppable
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    def behaviour(output: Path) -> None:
        locked = output / "locked"
        locked.mkdir()
        (locked / "x.log").write_text(OLD)
        locked.chmod(mode)

    install_process(monkeypatch, behaviour, returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, EvidenceNotSealed)

    assert not list((tmp_path / "evidence").glob("turn-*/output")), "evidence that may hold the credential was kept"


def test_a_docker_listing_that_fails_does_not_count_as_the_container_being_gone(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False, ps_code=1))  # daemon unreachable
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    install_process(monkeypatch, lambda output: (output / "late.log").write_text(OLD), returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, EvidenceNotSealed)

    assert not list((tmp_path / "evidence").glob("turn-*/output"))


def test_absence_is_seen_twice_before_the_container_counts_as_gone(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    seen: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False, record=seen))
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    install_process(monkeypatch, lambda output: None, returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert [call[0][0] for call in seen if call[0][0] == "ps"] == ["ps", "ps"]


def test_the_container_is_stopped_before_the_evidence_is_sealed(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folders: list[Path] = []

    def dying_container_writes_last() -> None:  # the kill is what makes the container write once more
        (folders[0] / "last-breath.log").write_text(OLD)

    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(on_kill=dying_container_writes_last))
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    install_process(monkeypatch, lambda output: folders.append(output), returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert plain_bytes_leak(tmp_path / "evidence", OLD) == [], "the evidence was sealed before the container stopped"


def test_a_container_that_is_not_ours_is_never_killed_and_every_docker_command_has_a_time_limit(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    seen: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False, record=seen))
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    install_process(monkeypatch, lambda output: None, returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, EvidenceNotSealed)

    assert not [call for call in seen if call[0][0] == "kill"]
    assert seen and all(0 < call[1].get("timeout", 0) <= 60 for call in seen)


def test_an_interrupt_during_the_stop_step_still_removes_the_evidence_and_the_failure_stays_explicit(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def interrupted(*args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(docker_turn_runner, "docker", interrupted)
    real_popen = subprocess.Popen

    class Process:
        returncode = None

        def __init__(self, argv, **_kw) -> None:
            self.output = output_folder(argv)

        def communicate(self, timeout=None):
            (self.output / "late.log").write_text(OLD)
            raise RuntimeError("the pipe broke")

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Process(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential)

    with pytest.raises(EvidenceNotSealed) as failure:  # the failure is explicit and keeps the original as its cause
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert isinstance(failure.value.__cause__, RuntimeError)
    assert not list((tmp_path / "evidence").glob("turn-*/output"))


def test_a_folder_whose_name_holds_the_credential_is_renamed_and_its_files_are_still_sealed(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def behaviour(output: Path) -> None:
        named = output / f"dir-{OLD}"
        named.mkdir()
        (named / "inner.log").write_text(OLD)

    install_process(monkeypatch, behaviour)
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []
    assert not [p for p in (tmp_path / "evidence").rglob("*") if OLD in p.name]
    assert list((tmp_path / "evidence").glob("turn-*/output/redacted-name-*/inner.log"))


def test_an_output_with_too_many_entries_is_not_scanned_and_is_removed(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(module, "MAX_ENTRIES", 5)
    install_process(monkeypatch, lambda output: [(output / f"f{i}.log").write_text("x") for i in range(6)])
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, EvidenceNotSealed)

    assert not list((tmp_path / "evidence").glob("turn-*/output"))


def test_when_the_wait_fails_the_container_is_stopped_before_the_evidence_is_sealed(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folders: list[Path] = []
    monkeypatch.setattr(docker_turn_runner, "docker",
                        docker_double(on_kill=lambda: (folders[0] / "last-breath.log").write_text(OLD)))  # the kill makes it write once more
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    real_popen = subprocess.Popen

    class Process:
        returncode = None

        def __init__(self, argv, **_kw) -> None:
            folders.append(output_folder(argv))

        def communicate(self, timeout=None):
            if len(folders) == 1 and not getattr(self, "failed", False):
                self.failed = True
                raise RuntimeError("the pipe broke")
            return b"", None

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Process(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential)

    run_expecting(runner, RuntimeError)

    assert plain_bytes_leak(tmp_path / "evidence", OLD) == [], "the evidence was sealed before the container stopped"


# --- Repairs after gate verdict 4/4: ONE remaining budget for stop, reap, pauses and sealing -----------------------

def timed_turn(tmp_path: Path, monkeypatch, *, docker, communicate_after_timeout=None, fail_wait=False, grace=1.0,
               secret: bool = True, ledger: bool = True):
    """Runs one guarded turn with a slow docker CLI. Returns (elapsed, outcome, spend, evidence, calls)."""
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    calls: list[tuple[float, tuple, float | None]] = []
    started = time.monotonic()

    def cli(*args, timeout=None, **_kw):
        calls.append((time.monotonic() - started, args, timeout))
        return docker(*args, timeout=timeout)

    monkeypatch.setattr(docker_turn_runner, "docker", cli)
    real_popen = subprocess.Popen

    class Process:
        returncode = -9

        def __init__(self, argv, **_kw) -> None:
            self.output, self.waits = output_folder(argv), 0

        def communicate(self, timeout=None):
            self.waits += 1
            if self.waits == 1:
                (self.output / "late.log").write_text(OLD)
                if fail_wait:
                    raise RuntimeError("the pipe broke")
                time.sleep(timeout)  # a real wait takes the time it was given before it times out
                raise subprocess.TimeoutExpired("docker", timeout)
            if communicate_after_timeout is not None:  # the reaping wait takes exactly the time it was given
                time.sleep(timeout if timeout is not None else communicate_after_timeout)
                raise subprocess.TimeoutExpired("docker", timeout)
            return b"", None

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Process(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=grace)
    outcome: list = []

    def go() -> None:
        started_at = time.monotonic()
        try:
            guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
            outcome.append("returned")
        except BaseException as error:  # noqa: BLE001
            outcome.append(type(error).__name__)
        outcome.append(time.monotonic() - started_at)

    worker = threading.Thread(target=go, daemon=True)
    worker.start()
    worker.join(timeout=grace + 12)  # a watchdog: the old behaviour needed up to six seconds more than its grace
    assert not worker.is_alive(), "the turn did not finish"
    return outcome[1], outcome[0], spend, tmp_path / "evidence", calls


def sleeps_exactly_its_timeout(*args, timeout=None, **_kw):
    time.sleep(timeout)
    raise subprocess.TimeoutExpired("controlled-owned-stop", timeout)


def test_a_stop_command_that_hangs_cannot_run_the_turn_past_the_job_timeout_plus_grace(tmp_path: Path, monkeypatch) -> None:
    elapsed, outcome, spend, evidence, calls = timed_turn(tmp_path, monkeypatch, docker=sleeps_exactly_its_timeout, grace=1.0)

    assert outcome == "EvidenceNotSealed" and elapsed <= 0.1 + 1.0 + 0.25, elapsed
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("UNKNOWN", RESERVATION)
    assert not list(evidence.glob("turn-*/output")) and plain_bytes_leak(evidence, OLD) == []
    assert len(calls) == 1, "a second command was started after the first had used the budget"


def test_no_command_starts_once_the_budget_is_spent(tmp_path: Path, monkeypatch) -> None:
    elapsed, outcome, _, evidence, calls = timed_turn(tmp_path, monkeypatch, docker=sleeps_exactly_its_timeout, grace=0.0)

    assert outcome == "EvidenceNotSealed" and calls == [] and elapsed <= 0.1 + 0.25
    assert not list(evidence.glob("turn-*/output"))


def test_every_docker_command_fits_inside_the_remaining_budget(tmp_path: Path, monkeypatch) -> None:
    elapsed, _, _, _, calls = timed_turn(tmp_path, monkeypatch, docker=sleeps_exactly_its_timeout, grace=0.8)

    assert calls and all(started + timeout <= 0.1 + 0.8 + 0.05 for started, _, timeout in calls)
    assert elapsed <= 0.1 + 0.8 + 0.25


def healthy_docker(*args, timeout=None, **_kw):
    if args[0] == "inspect":
        return subprocess.CompletedProcess(args, 1, "", "")
    return subprocess.CompletedProcess(args, 0, "", "")


def test_the_wait_for_the_stopped_client_is_part_of_the_same_budget(tmp_path: Path, monkeypatch) -> None:
    elapsed, outcome, _, evidence, _ = timed_turn(tmp_path, monkeypatch, docker=healthy_docker, communicate_after_timeout=5.0, grace=1.0)

    assert elapsed <= 0.1 + 1.0 + 0.25, elapsed  # a fresh five-second wait would have taken five seconds
    assert outcome in ("returned", "EvidenceNotSealed") and plain_bytes_leak(evidence, OLD) == []


@pytest.mark.parametrize("fail_wait", [True, False])  # False: the job times out and the stop runs inside the turn first
def test_a_failed_stop_is_not_repeated_by_the_cleanup_of_the_failure(tmp_path: Path, monkeypatch, fail_wait: bool) -> None:
    def failing(*args, timeout=None, **_kw):
        raise subprocess.TimeoutExpired("controlled-owned-stop", 0.01)

    _, outcome, spend, evidence, calls = timed_turn(tmp_path, monkeypatch, docker=failing, fail_wait=fail_wait, grace=1.0)

    assert outcome == "EvidenceNotSealed"  # the failed stop is reported, not hidden behind the original failure
    assert len([call for call in calls if call[1][0] == "inspect"]) == 1
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("UNKNOWN", RESERVATION)
    assert not list(evidence.glob("turn-*/output"))


def test_the_pauses_between_listings_are_part_of_the_same_budget(tmp_path: Path, monkeypatch) -> None:
    def present_forever(*args, timeout=None, **_kw):
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, "abc\n", "")
        return subprocess.CompletedProcess(args, 0, f"/{args[1]} repair-test\n" if args[0] == "inspect" else "", "")

    elapsed, outcome, _, evidence, _ = timed_turn(tmp_path, monkeypatch, docker=present_forever, grace=1.0)

    assert outcome == "EvidenceNotSealed" and elapsed <= 0.1 + 1.0 + 0.25, elapsed
    assert not list(evidence.glob("turn-*/output"))


# --- Repairs after round-8 review: removal of a huge output is bounded, and the settings are checked ---------------

def test_removing_a_huge_output_after_a_missed_bound_cannot_run_the_turn_past_the_deadline(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(module, "MAX_ENTRIES", 10_000_000)  # the count limit is not what stops this one
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # present and not ours: never stoppable
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    job_seconds: list[float] = []

    def behaviour(output: Path) -> None:  # the job itself takes a while to write this much; that time is not the runner's
        began = time.monotonic()
        crowd = output / "crowd"
        crowd.mkdir()
        for index in range(40_000):
            (crowd / f"f{index}.log").write_text("x")
        (crowd / "secret.log").write_text(OLD)
        job_seconds.append(time.monotonic() - began)

    install_process(monkeypatch, behaviour, returncode=-9)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=0.1)
    outcome: list = []

    def go() -> None:
        started = time.monotonic()
        try:
            runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
            outcome.append("returned")
        except EvidenceNotSealed as error:
            outcome.append(str(error))
        outcome.append(time.monotonic() - started)

    worker = threading.Thread(target=go, daemon=True)
    worker.start()
    worker.join(timeout=60)

    assert not worker.is_alive(), "the turn did not finish"
    assert outcome[1] - job_seconds[0] <= 0.1 + 0.1 + 0.4, outcome  # deleting 40,000 files takes seconds; the turn must not wait for it
    folders = list((tmp_path / "evidence").glob("turn-*/output"))
    assert folders == [], "evidence was left where a reader would find it as the turn's output"
    held = list((tmp_path / "evidence").glob("quarantine-*"))
    if held:  # removal did not finish: it is explicit, private and removable afterwards
        assert "quarantine" in outcome[0] and held[0].stat().st_mode & 0o077 == 0
        runner.purge_quarantine()
    assert not list((tmp_path / "evidence").glob("quarantine-*")) and plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_a_directory_listing_is_cut_off_at_the_entry_limit_instead_of_being_read_whole(tmp_path: Path, monkeypatch) -> None:
    import itertools
    import sys
    import guarded_docker_runner as module
    monkeypatch.setattr(module, "MAX_ENTRIES", 5)
    for index in range(3):
        (tmp_path / f"f{index}.log").write_text("x")

    class Endless:  # a folder that never ends; reading it whole would never return
        def __iter__(self):
            return (type("Entry", (), {"name": f"f{index % 3}.log"})() for index in itertools.count())

        def close(self) -> None:
            pass

    real_scandir = os.scandir
    served = {"done": False}

    def scandir(path):
        if not served["done"] and sys._getframe(1).f_code.co_name == "_walk":
            served["done"] = True
            return Endless()
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    outcome: list = []

    def go() -> None:
        try:
            GuardedDockerTurnRunner._redact(tmp_path, OLD, time.monotonic() + 30)
            outcome.append("returned")
        except EvidenceNotSealed:
            outcome.append("EvidenceNotSealed")

    worker = threading.Thread(target=go, daemon=True)
    worker.start()
    worker.join(timeout=10)

    assert outcome == ["EvidenceNotSealed"]


@pytest.mark.parametrize("field", ["timeout_seconds", "seal_grace_seconds"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), "5", None])
def test_a_timeout_or_grace_that_is_not_a_finite_number_is_refused_at_construction(tmp_path: Path, field: str, value) -> None:
    kwargs = {"timeout_seconds": 60, "seal_grace_seconds": 5.0, field: value}

    with pytest.raises(ValueError):
        GuardedDockerTurnRunner(image="unused", run_id="x", evidence_dir=tmp_path, policy=POLICY, script_for=lambda t: {}, **kwargs)


# --- Repairs after round-9 reviews: every step of removal ticks the clock, and no removal is left without one ---------

def run_removal_turn(tmp_path: Path, monkeypatch, behaviour, *, grace: float = 0.2):
    """A turn whose container cannot be stopped, so the whole output must be removed or moved. Returns the result."""
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(module, "MAX_ENTRIES", 10_000_000)  # the count limit is not what is being tested
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # present and not ours: never stoppable
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    job_seconds: list[float] = []

    def timed(output: Path) -> None:
        began = time.monotonic()
        behaviour(output)
        job_seconds.append(time.monotonic() - began)

    install_process(monkeypatch, timed, returncode=-9)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=grace)
    outcome: list = []

    def go() -> None:
        started = time.monotonic()
        try:
            runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
            outcome.append("returned")
        except EvidenceNotSealed as error:
            outcome.append(str(error))
        outcome.append(time.monotonic() - started - job_seconds[0])

    worker = threading.Thread(target=go, daemon=True)
    worker.start()
    worker.join(timeout=90)
    assert not worker.is_alive(), "the turn did not finish"
    return runner, outcome


def test_a_flood_of_empty_directories_cannot_run_the_turn_past_its_bound(tmp_path: Path, monkeypatch) -> None:
    def flood(output: Path) -> None:
        crowd = output / "crowd"
        crowd.mkdir()
        for index in range(40_000):
            os.mkdir(crowd / f"d{index}")

    runner, outcome = run_removal_turn(tmp_path, monkeypatch, flood)

    assert outcome[1] <= 0.1 + 0.2 + 0.4, outcome
    assert not list((tmp_path / "evidence").glob("turn-*/output"))
    runner.purge_quarantine()
    assert not list((tmp_path / "evidence").glob("quarantine-*"))


def test_a_path_too_long_for_the_plain_walk_is_moved_not_removed_without_a_clock(tmp_path: Path, monkeypatch) -> None:
    def chain_and_files(output: Path) -> None:
        write_deep_chain(output, 700, files=1_500, secret=OLD)  # deep files are slow to create and to remove: about 1.5 ms each

    runner, outcome = run_removal_turn(tmp_path, monkeypatch, chain_and_files)

    assert outcome[1] <= 0.1 + 0.2 + 0.4, outcome
    assert not list((tmp_path / "evidence").glob("turn-*/output"))
    assert "quarantine-" in outcome[0], "the error must name the folder that holds the evidence"
    runner.purge_quarantine()  # has no clock, and must cope with a chain longer than the path limit
    assert not list((tmp_path / "evidence").glob("quarantine-*"))


def test_purge_goes_on_past_a_folder_it_cannot_remove_and_says_what_is_left(tmp_path: Path) -> None:
    runner = GuardedDockerTurnRunner(image="unused", run_id="x", evidence_dir=tmp_path, policy=POLICY, script_for=lambda t: {})
    (tmp_path / "quarantine-a").mkdir()
    (tmp_path / "quarantine-b").mkdir()
    (tmp_path / "quarantine-b" / "kept.log").write_text("x")
    (tmp_path / "quarantine-b").chmod(0o000)  # unreadable, so the plain walk cannot enter it before it is made ours

    runner.purge_quarantine()

    assert not list(tmp_path.glob("quarantine-*"))


@pytest.mark.parametrize("field", ["timeout_seconds", "seal_grace_seconds"])
def test_a_deadline_setting_changed_to_a_non_finite_number_after_construction_stops_the_turn_before_any_job(tmp_path: Path, monkeypatch, field: str) -> None:
    launched = install_process(monkeypatch, lambda output: None)
    runner = GuardedDockerTurnRunner(image="unused", run_id="x", evidence_dir=tmp_path, policy=POLICY, script_for=lambda t: {})
    setattr(runner, field, float("nan"))

    with pytest.raises(ValueError):
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert launched == []


def test_the_error_for_a_container_that_cannot_be_stopped_names_the_container(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    launched = install_process(monkeypatch, lambda output: None, returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    with pytest.raises(EvidenceNotSealed) as failure:
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert launched[0][launched[0].index("--name") + 1] in str(failure.value), "an operator needs the name of the orphan"


def test_when_the_plain_walk_fails_for_any_reason_the_output_is_moved_and_never_removed_without_a_clock(tmp_path: Path, monkeypatch) -> None:
    def many_files(output: Path) -> None:
        crowd = output / "crowd"
        crowd.mkdir()
        for index in range(40_000):
            (crowd / f"f{index}.log").write_text("x")
        (crowd / "secret.log").write_text(OLD)

    def fails_at_once(*_args, **_kwargs):
        raise OSError(63, "File name too long")  # what the plain walk raises on a path the host cannot take

    monkeypatch.setattr(GuardedDockerTurnRunner, "_remove_tree", staticmethod(fails_at_once))
    runner, outcome = run_removal_turn(tmp_path, monkeypatch, many_files)

    assert outcome[1] <= 0.1 + 0.2 + 0.4, outcome  # an unbounded removal of 40,000 files would take seconds
    assert "quarantine-" in outcome[0] and not list((tmp_path / "evidence").glob("turn-*/output"))
    monkeypatch.undo()
    GuardedDockerTurnRunner(image="unused", run_id="x", evidence_dir=tmp_path / "evidence", policy=POLICY,
                            script_for=lambda t: {}).purge_quarantine()
    assert not list((tmp_path / "evidence").glob("quarantine-*"))


# --- Repairs after round-10 review: removal must not follow a link that a surviving container swaps in -----------------

def _swap_a_queued_folder_for_a_link_after_the_first_listing(monkeypatch, output_holder: list, victim: Path,
                                                             caller: str = "_walk") -> dict:
    """After the removal has listed the output once, a folder it has queued becomes a link to a host folder.

    That is what a container that is still alive could do between the listing and the visit. The hook fires once, only for
    a listing made from `_remove_tree`, and works for both ways of listing a folder.
    """
    import sys
    state = {"done": False}
    real_scandir, real_listdir = os.scandir, os.listdir

    def swap() -> None:
        if state["done"]:
            return
        state["done"] = True
        queued = output_holder[0] / "queued"
        shutil_rmtree(queued)
        queued.symlink_to(victim, target_is_directory=True)

    def from_remove_tree() -> bool:
        return sys._getframe(2).f_code.co_name == caller

    def scandir(path):
        result = real_scandir(path)
        if from_remove_tree():
            entries = list(result)
            result.close()
            swap()
            return _ListedEntries(entries)
        return result

    def listdir(path="."):
        result = real_listdir(path)
        if from_remove_tree():
            swap()
        return result

    monkeypatch.setattr(os, "scandir", scandir)
    monkeypatch.setattr(os, "listdir", listdir)
    return state


class _ListedEntries:
    def __init__(self, entries) -> None:
        self.entries = entries

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def __iter__(self):
        return iter(self.entries)

    def close(self) -> None:
        pass


def shutil_rmtree(path: Path) -> None:
    import shutil
    shutil.rmtree(path)


def test_removal_does_not_follow_a_link_that_a_surviving_container_swaps_in(tmp_path: Path, monkeypatch) -> None:
    victim = tmp_path / "host-folder"
    victim.mkdir()
    (victim / "keep.txt").write_text("a file of the host, not evidence")
    victim.chmod(0o755)
    holder: list[Path] = []

    def behaviour(output: Path) -> None:
        holder.append(output)
        (output / "queued").mkdir()
        (output / "queued" / "inner.log").write_text(OLD)
        (output / "other.log").write_text("x")

    swap = _swap_a_queued_folder_for_a_link_after_the_first_listing(monkeypatch, holder, victim)
    run_removal_turn(tmp_path, monkeypatch, behaviour, grace=2.0)
    assert swap["done"], "the swap did not happen, so this test proved nothing"

    assert (victim / "keep.txt").read_text() == "a file of the host, not evidence", "removal followed the link out of the evidence"
    assert victim.stat().st_mode & 0o777 == 0o755, "removal changed the mode of a host folder"


def test_a_second_interrupt_during_removal_still_moves_the_evidence_and_then_lets_the_interrupt_through(tmp_path: Path, monkeypatch) -> None:
    holder: list[Path] = []

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(GuardedDockerTurnRunner, "_remove_tree", staticmethod(interrupted))
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    install_process(monkeypatch, lambda output: (holder.append(output), (output / "late.log").write_text(OLD)), returncode=-9)
    runner, _, _ = build(tmp_path, credential)

    with pytest.raises(KeyboardInterrupt):
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert not list((tmp_path / "evidence").glob("turn-*/output")), "the output was left where a reader would find it"
    assert list((tmp_path / "evidence").glob("quarantine-*"))


def test_purge_says_which_folders_are_left_when_it_cannot_remove_them(tmp_path: Path, monkeypatch) -> None:
    import shutil
    runner = GuardedDockerTurnRunner(image="unused", run_id="x", evidence_dir=tmp_path, policy=POLICY, script_for=lambda t: {})
    (tmp_path / "quarantine-stuck").mkdir()

    def fails(*_args, **_kwargs):
        raise OSError("busy")

    monkeypatch.setattr(GuardedDockerTurnRunner, "_remove_tree", staticmethod(fails))
    monkeypatch.setattr(shutil, "rmtree", lambda *a, **k: None)

    with pytest.raises(EvidenceNotSealed, match="quarantine-stuck"):
        runner.purge_quarantine()


def test_removal_does_not_follow_a_link_swapped_in_between_the_check_and_the_open(tmp_path: Path, monkeypatch) -> None:
    import sys
    victim = tmp_path / "host-folder"
    victim.mkdir()
    (victim / "keep.txt").write_text("a file of the host, not evidence")
    victim.chmod(0o755)
    holder: list[Path] = []
    state = {"done": False}
    real_stat = os.stat

    def stat_then_swap(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if not state["done"] and path == "queued" and sys._getframe(1).f_code.co_name in ("_remove_tree", "_walk"):
            state["done"] = True  # the check has just seen a real folder; now it becomes a link
            shutil_rmtree(holder[0] / "queued")
            (holder[0] / "queued").symlink_to(victim, target_is_directory=True)
        return result

    def behaviour(output: Path) -> None:
        holder.append(output)
        (output / "queued").mkdir()
        (output / "queued" / "inner.log").write_text(OLD)

    monkeypatch.setattr(os, "stat", stat_then_swap)
    run_removal_turn(tmp_path, monkeypatch, behaviour, grace=2.0)

    assert state["done"], "the swap did not happen, so this test proved nothing"
    assert (victim / "keep.txt").read_text() == "a file of the host, not evidence"
    assert victim.stat().st_mode & 0o777 == 0o755


# --- Repairs after round-11 reviews: verify the container after ANY client exit, and seal on descriptors ------------

@pytest.mark.parametrize("returncode", [0, 1, 125])
def test_a_client_that_exits_while_its_container_still_runs_does_not_skip_the_stop(tmp_path: Path, monkeypatch, returncode: int) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folders: list[Path] = []
    calls: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(
        record=calls, on_kill=lambda: (folders[0] / "last-breath.log").write_text(OLD)))  # the container still writes once
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    install_process(monkeypatch, lambda output: folders.append(output), returncode=returncode)
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert any(call[0][0] == "kill" for call in calls), "the client exit code was trusted as proof that the container is gone"
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_sealing_does_not_follow_a_link_swapped_in_after_the_listing(tmp_path: Path, monkeypatch) -> None:
    victim = tmp_path / "host-folder"
    victim.mkdir()
    (victim / "keep.txt").write_text(f"a host file that happens to hold {OLD}")
    (victim / "keep.txt").chmod(0o644)
    (victim / "host-link").symlink_to(tmp_path)
    victim.chmod(0o755)
    holder: list[Path] = []

    def behaviour(output: Path) -> None:
        holder.append(output)
        (output / "queued").mkdir()
        (output / "queued" / "inner.log").write_text(OLD)

    credential = tmp_path / "credential"
    credential.write_text(OLD)
    install_process(monkeypatch, behaviour)
    import sys
    state = {"listings": 0, "swapped": False}
    real_scandir = os.scandir

    def scandir(path):
        if sys._getframe(1).f_code.co_name in ("_redact", "_walk"):
            state["listings"] += 1
            if state["listings"] == 2 and not state["swapped"]:  # the folder was classified and is about to be listed
                state["swapped"] = True
                shutil_rmtree(holder[0] / "queued")
                (holder[0] / "queued").symlink_to(victim, target_is_directory=True)
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    runner, _, _ = build(tmp_path, credential)

    try:
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    except EvidenceNotSealed:
        pass

    assert (victim / "keep.txt").read_text() == f"a host file that happens to hold {OLD}", "sealing rewrote a host file"
    assert (victim / "keep.txt").stat().st_mode & 0o777 == 0o644 and victim.stat().st_mode & 0o777 == 0o755
    assert (victim / "host-link").is_symlink(), "sealing deleted a host link"
    assert state["swapped"], "the swap did not happen, so this test proved nothing"


def test_a_file_that_becomes_a_named_pipe_before_sealing_opens_it_cannot_block_the_turn(tmp_path: Path, monkeypatch) -> None:
    import sys
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    holder: list[Path] = []
    state = {"done": False}
    real_stat = os.stat

    def stat_then_swap(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if not state["done"] and str(path).endswith("f.log") and sys._getframe(1).f_code.co_name in ("_redact", "_seal_file", "_walk"):
            state["done"] = True  # classified as a regular file; now it becomes a pipe that nobody writes to
            os.unlink(holder[0] / "f.log")
            os.mkfifo(holder[0] / "f.log")
        return result

    def behaviour(output: Path) -> None:
        holder.append(output)
        (output / "f.log").write_text(OLD)

    install_process(monkeypatch, behaviour)
    monkeypatch.setattr(os, "stat", stat_then_swap)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=1.0)
    done: list = []
    worker = threading.Thread(target=lambda: done.append(runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))),
                              daemon=True)
    worker.start()
    worker.join(timeout=5)
    hung = worker.is_alive()
    if hung:  # release the blocked reader so the test can clean up
        os.close(os.open(holder[0] / "f.log", os.O_WRONLY | os.O_NONBLOCK))
        worker.join(timeout=5)

    assert state["done"], "the swap did not happen, so this test proved nothing"
    assert not hung, "sealing blocked on a named pipe"


# --- Repairs after the round-12 tracing addenda: the job wait and the stdout are inside the one deadline ------------

def _timed_run(runner, turn_id: str = "attempt-1", limit: float = 30.0):
    outcome: list = []

    def go() -> None:
        started = time.monotonic()
        try:
            outcome.append(runner.run_turn(Turn(turn_id, "prompt", "task", "m", "route", 4096)).status)
        except BaseException as error:  # noqa: BLE001
            outcome.append(type(error).__name__)
        outcome.append(time.monotonic() - started)

    worker = threading.Thread(target=go, daemon=True)
    worker.start()
    worker.join(timeout=limit)
    assert not worker.is_alive(), "the turn did not finish"
    return outcome


def test_time_spent_before_the_job_starts_comes_out_of_the_job_wait_not_on_top_of_it(tmp_path: Path, monkeypatch) -> None:
    real_popen = subprocess.Popen

    class Hanging:  # a job that never finishes by itself; each wait lasts exactly the time it is given
        returncode = None

        def __init__(self, argv, **_kw) -> None:
            pass

        def communicate(self, timeout=None):
            time.sleep(max(0.0, timeout or 0.0))
            raise subprocess.TimeoutExpired("docker", timeout)

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Hanging(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))

    def slow_setup(turn):  # the caller's script, the file writes and the launch all happen after the deadline is set
        time.sleep(1.5)
        return {}

    runner, _, _ = build(tmp_path, None, script_for=slow_setup, timeout_seconds=1.0, seal_grace_seconds=1.0)

    status, elapsed = _timed_run(runner)

    assert elapsed <= 1.0 + 1.0 + 0.25, (status, elapsed)


@pytest.mark.parametrize("size", [10 * 1024 * 1024, 300 * 1024 * 1024])  # below and above the size that sealing will scan
def test_a_flood_of_stdout_is_capped_and_cannot_run_the_turn_past_its_deadline(tmp_path: Path, monkeypatch, size: int) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    flood = (OLD.encode() + b"x" * 1000) * 300_000  # about 300 MiB, with the credential all through it
    real_popen = subprocess.Popen

    class Loud:
        returncode = 0

        size = 0

        def __init__(self, argv, **kw) -> None:
            self.sink = kw.get("stdout")

        def communicate(self, timeout=None):
            if hasattr(self.sink, "write"):  # the host gave the job a file: the job wrote this much there while it ran
                self.sink.write(OLD.encode())
                self.sink.seek(int(self.size))
                self.sink.write(OLD.encode())
                self.sink.flush()
                return None, None
            return flood, None

        def kill(self) -> None:
            pass

    Loud.size = size
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Loud(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=0.5)

    status, elapsed = _timed_run(runner)

    assert elapsed <= 0.1 + 0.5 + 0.25, (status, elapsed)
    kept = sum(p.stat().st_size for p in (tmp_path / "evidence").rglob("*stdout*") if p.is_file())
    assert kept <= module.MAX_STDOUT_BYTES
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_a_credential_file_that_is_a_named_pipe_is_refused_without_blocking(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    os.mkfifo(credential)
    launched = install_process(monkeypatch, lambda output: None)
    runner, _, _ = build(tmp_path, credential)

    status, elapsed = _timed_run(runner, limit=5)

    assert status == "CredentialUnavailable" and elapsed < 1.0 and launched == []


# --- Repairs after round-13 reviews: every host read of a file the job controls is bounded, and the cut is safe --------

def test_cutting_the_stdout_never_keeps_a_part_of_the_credential(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    real_popen = subprocess.Popen

    class Loud:
        returncode = 0

        def __init__(self, argv, **kw) -> None:
            self.sink = kw.get("stdout")

        def communicate(self, timeout=None):  # the credential sits right across the 1 MiB cut
            self.sink.write(b"x" * (module.MAX_STDOUT_BYTES - 25) + OLD.encode() + b"y" * 4096)
            self.sink.flush()
            return None, None

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Loud(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    kept = b"".join(p.read_bytes() for p in (tmp_path / "evidence").rglob("*stdout*") if p.is_file())
    assert OLD.encode()[:12] not in kept, "the cut kept the first part of the credential"


@pytest.mark.parametrize("shape", ["fifo", "link-to-zero"])
def test_a_hostile_result_file_cannot_block_or_flood_the_host_even_without_a_credential(tmp_path: Path, monkeypatch, shape: str) -> None:
    def behaviour(output: Path) -> None:
        if shape == "fifo":
            os.mkfifo(output / "container-result.json")
        else:
            (output / "container-result.json").symlink_to("/dev/zero")

    install_process(monkeypatch, behaviour, returncode=0)
    runner, _, _ = build(tmp_path, None, timeout_seconds=1.0, seal_grace_seconds=1.0)

    status, elapsed = _timed_run(runner, limit=8)

    assert status in ("UNKNOWN", "EvidenceNotSealed") and elapsed <= 1.0 + 1.0 + 0.25, (status, elapsed)
    assert not [p for p in (tmp_path / "evidence").rglob("*") if p.is_symlink() or stat_is_fifo(p)], "a special file was kept"


def stat_is_fifo(path: Path) -> bool:
    import stat as stat_module
    return stat_module.S_ISFIFO(path.lstat().st_mode)


def test_no_job_is_launched_once_the_budget_is_spent_during_setup(tmp_path: Path, monkeypatch) -> None:
    launched = install_process(monkeypatch, lambda output: None, returncode=0)

    def slow_setup(turn):
        time.sleep(1.3)
        return {}

    runner, spend, guarded = build(tmp_path, None, script_for=slow_setup, timeout_seconds=1.0, seal_grace_seconds=0.2)

    result = guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert launched == [], "a job was started after its budget was spent"
    assert result.request_count == 0


def test_a_result_file_larger_than_the_limit_is_not_read(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    monkeypatch.setattr(module, "MAX_RESULT_BYTES", 1024)
    reads: list[int] = []
    real_read = os.read

    def counting_read(fd, n):
        reads.append(n)
        return real_read(fd, n)

    install_process(monkeypatch, lambda output: (output / "container-result.json").write_text(
        '{"guard": {}, "hermes": {}, "pad": "' + "x" * 4096 + '"}'), returncode=0)
    runner = build(tmp_path, None)[0]
    monkeypatch.setattr(os, "read", counting_read)

    result = runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert (result.status, result.error_class) == ("UNKNOWN", "ContainerResultUnreadable")
    assert all(n <= 1024 + 1 for n in reads), "the host read more of the result than the limit allows"


# --- Repairs after round-14 reviews: an over-limit stdout is dropped whole; errors carry no names -------------------

@pytest.mark.parametrize("back", [1, 25, 49])
def test_an_over_limit_stdout_keeps_no_part_of_the_credential_wherever_it_sits(tmp_path: Path, monkeypatch, back: int) -> None:
    import guarded_docker_runner as module
    from leak_scan import encodings
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    longest = max(len(form) for form in encodings(OLD))
    real_popen = subprocess.Popen

    class Loud:
        returncode = 0

        def __init__(self, argv, **kw) -> None:
            self.sink = kw.get("stdout")

        def communicate(self, timeout=None):  # the credential starts just before any cut point the host might choose
            for cut in (module.MAX_STDOUT_BYTES, module.MAX_STDOUT_BYTES - (longest - 1)):
                self.sink.seek(cut - back)
                self.sink.write(OLD.encode())
            self.sink.seek(module.MAX_STDOUT_BYTES + 4096)
            self.sink.write(b"end")
            self.sink.flush()
            return None, None

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Loud(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    kept = b"".join(p.read_bytes() for p in (tmp_path / "evidence").rglob("*stdout*") if p.is_file())
    assert OLD.encode()[:back] not in kept or back < 8, "a part of the credential stayed"
    assert OLD.encode()[:8] not in kept


def test_a_job_that_makes_a_rename_fail_cannot_put_the_credential_into_a_raised_error(tmp_path: Path, monkeypatch) -> None:
    import hashlib
    import traceback
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def behaviour(output: Path) -> None:
        named = output / f"dir-{OLD}"
        named.mkdir()
        (named / "inner.log").write_text("x")
        blocker = output / f"redacted-name-{hashlib.sha256(named.name.encode()).hexdigest()[:8]}"
        blocker.mkdir()  # a non-empty folder where the old code would rename to: the rename fails
        (blocker / "keep").write_text("x")

    install_process(monkeypatch, behaviour)
    runner, _, _ = build(tmp_path, credential)

    try:
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
        printed = ""
    except BaseException as error:  # noqa: BLE001
        printed = "".join(traceback.format_exception(error))

    assert OLD not in printed, "the credential reached a raised error"
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []
    assert not [p for p in (tmp_path / "evidence").rglob("*") if OLD in p.name]


def test_an_os_error_that_names_the_credential_never_reaches_a_raised_error(tmp_path: Path, monkeypatch) -> None:
    import traceback
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    install_process(monkeypatch, lambda output: (output / f"dir-{OLD}").mkdir())
    real_rename = os.rename

    def failing_rename(src, dst, *args, **kwargs):
        if OLD in str(src):
            raise OSError(66, "Directory not empty", str(src))  # an OS error carries the file name in its message
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "rename", failing_rename)
    runner, _, _ = build(tmp_path, credential)

    with pytest.raises(EvidenceNotSealed) as failure:
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert OLD not in "".join(traceback.format_exception(failure.value)), "the credential reached a raised error"


# --- Repair after round-15 review: the decoded result is checked, not only its raw bytes -------------------------

@pytest.mark.parametrize("escape", ["one-char", "every-char"])
def test_a_credential_hidden_by_json_escapes_in_the_result_is_caught_after_decoding(tmp_path: Path, monkeypatch, escape: str) -> None:
    import json as json_module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    if escape == "one-char":
        hidden = OLD[:5] + "\\u%04x" % ord(OLD[5]) + OLD[6:]  # one character as a JSON escape: not in the scanned forms
    else:
        hidden = "".join("\\u%04x" % ord(c) for c in OLD[:-1]) + OLD[-1]

    def behaviour(output: Path) -> None:
        (output / "container-result.json").write_text('{"hermes": {"text": "' + hidden + '"}, "guard": {}}')

    install_process(monkeypatch, behaviour, returncode=0)
    runner, _, _ = build(tmp_path, credential)

    result = runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert (result.status, result.error_class, result.text) == ("UNKNOWN", "CredentialEchoed", None)
    assert OLD not in json_module.dumps(dict(result.observed))


@pytest.mark.parametrize("form", ["hex", "base64", "reversed", "upper"])
def test_an_encoded_credential_hidden_by_one_json_escape_is_caught_after_decoding(tmp_path: Path, monkeypatch, form: str) -> None:
    import base64 as b64
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    encoded = {"hex": OLD.encode().hex(), "base64": b64.b64encode(OLD.encode()).decode(), "reversed": OLD[::-1],
               "upper": OLD.upper()}[form]
    hidden = encoded[:4] + "\\u%04x" % ord(encoded[4]) + encoded[5:]  # one escaped character hides it from the byte scan

    install_process(monkeypatch, lambda output: (output / "container-result.json").write_text(
        '{"hermes": {"text": "' + hidden + '"}, "guard": {}}'), returncode=0)
    runner, _, _ = build(tmp_path, credential)

    result = runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert (result.status, result.error_class, result.text) == ("UNKNOWN", "CredentialEchoed", None)


# --- Repairs after round-17 reviews: escaped copies leave the saved evidence too; the decoded check is fast ----------

def decoded_json_holds(root: Path, secret: str) -> list[str]:
    """Independent oracle: every saved file that parses as JSON, decoded, must not contain the credential."""
    import json as json_module
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.name in {"input.json", "credential"}:
            continue
        try:
            pending = [json_module.loads(path.read_text())]
        except (ValueError, UnicodeDecodeError):
            continue
        while pending:  # walk the decoded strings themselves: re-encoding would escape quotes again
            item = pending.pop()
            if isinstance(item, str) and secret in item:
                found.append(str(path.relative_to(root)))
                break
            if isinstance(item, dict):
                pending.extend(list(item.keys()) + list(item.values()))
            elif isinstance(item, list):
                pending.extend(item)
    return found


QUOTED = 'sk-test-DUMMY"QUOTE\\0a1b2c3d4e5f60718293a4b5'  # a credential with a quote and a backslash


@pytest.mark.parametrize("case", ["one-escape", "json-dumps-of-a-quoted-credential"])
def test_a_credential_that_only_decoding_reveals_does_not_stay_in_the_saved_result(tmp_path: Path, monkeypatch, case: str) -> None:
    import json as json_module
    secret = OLD if case == "one-escape" else QUOTED
    credential = tmp_path / "credential"
    credential.write_text(secret)
    if case == "one-escape":
        body = '{"hermes": {"text": "' + OLD[:5] + "\\u%04x" % ord(OLD[5]) + OLD[6:] + '"}, "guard": {}}'
    else:
        body = json_module.dumps({"hermes": {"text": secret}, "guard": {}})  # the job's own trusted encoder

    install_process(monkeypatch, lambda output: (output / "container-result.json").write_text(body), returncode=0)
    runner, _, _ = build(tmp_path, credential)

    result = runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert result.error_class == "CredentialEchoed"
    assert decoded_json_holds(tmp_path / "evidence", secret) == [], "a saved file still decodes to the credential"


def test_checking_a_result_of_a_million_tiny_strings_cannot_run_the_turn_past_its_deadline(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    count = (module.MAX_RESULT_BYTES - 64) // 3
    body = '{"hermes": {}, "guard": {}, "x": [' + ",".join(['""'] * count) + "]}"
    real_popen = subprocess.Popen

    class Late:  # the job writes its result and finishes right at the end of its timeout
        returncode = 0

        def __init__(self, argv, **_kw) -> None:
            self.output = output_folder(argv)

        def communicate(self, timeout=None):
            if not getattr(self, "done", False):  # only the job wait; later reaping returns at once
                self.done = True
                (self.output / "container-result.json").write_text(body)
                time.sleep(max(0.0, (timeout or 0) - 0.3))
            return None, None

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Late(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=1.0)

    status, elapsed = _timed_run(runner)
    assert elapsed <= 1.0 + 1.0 + 0.25, (status, elapsed)


# --- Repair after round-18 reviews: sealing one file has a bounded cost and sees the clock -------------------------

@pytest.mark.parametrize("filler", [b'\\"', b"\\\\", b"\\u0041", b"A"])
def test_sealing_a_file_dense_with_escapes_cannot_run_the_turn_past_its_deadline(tmp_path: Path, monkeypatch, filler: bytes) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    real_popen = subprocess.Popen
    size = 60 * 1024 * 1024

    class Late:
        returncode = 0

        def __init__(self, argv, **_kw) -> None:
            self.output = output_folder(argv)

        def communicate(self, timeout=None):
            if not getattr(self, "done", False):
                self.done = True
                (self.output / "dense.log").write_bytes(OLD.encode() + filler * (size // len(filler)))
            return None, None

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Late(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))
    runner, _, _ = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=1.0)

    status, elapsed = _timed_run(runner, limit=120)

    assert elapsed <= 1.0 + 1.0 + 0.4, (status, elapsed)
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


# --- Repair after round-19 review: names use the same credential test as contents --------------------------------

@pytest.mark.parametrize("shape", ["hex-one-upper", "reversed-upper", "one-escape"])
def test_a_name_that_encodes_the_credential_is_renamed_and_the_turn_says_so(tmp_path: Path, monkeypatch, shape: str) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    hexed = OLD.encode().hex()
    name = {"hex-one-upper": hexed[:3] + hexed[3].upper() + hexed[4:],
            "reversed-upper": OLD[::-1].upper(),
            "one-escape": OLD[:5] + "\\u%04x" % ord(OLD[5]) + OLD[6:]}[shape]
    install_process(monkeypatch, lambda output: (output / name).write_text("x"), returncode=3)
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert not [p for p in (tmp_path / "evidence").rglob("*") if p.name == name], "the name was kept"
