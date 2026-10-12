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

    credential = run_with(tmp_path, monkeypatch, expect_raise=EvidenceNotSealed)  # the huge file is held aside unscanned

    assert outside.read_text() == f"not evidence {SENTINEL}", "a link must never lead the redaction outside the evidence folder"
    assert not any("huge.bin" in str(path) for path in tmp_path.glob("evidence/turn-*/**/*"))
    assert all(held.stat().st_mode & 0o077 == 0 for held in tmp_path.glob("evidence/quarantine-*"))
    GuardedDockerTurnRunner(image="unused", run_id="redact-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                            script_for=lambda turn: {}).purge_quarantine()
    assert [name for name in leaks(tmp_path, credential) if name != "outside-file.txt"] == []  # the outside file is the bait


# --- Repairs after gate verdict 3/3: one captured plan per turn, no blocking on odd entries, a time bound ----------------

import math
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


TURN_RECORDS: list[dict] = []  # every turn of the current test: its plan and the moment the runner itself returned


@pytest.fixture(autouse=True)
def record_each_turn_against_its_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Record each turn's plan and the runner's own return, so deadline checks compare with D and need no tolerance."""
    TURN_RECORDS.clear()
    original_plan, original_run_turn = GuardedDockerTurnRunner._plan, GuardedDockerTurnRunner.run_turn

    def plan(self):
        made = original_plan(self)
        TURN_RECORDS.append({"plan": made, "returned": None})
        return made

    def run_turn(self, turn):
        try:
            return original_run_turn(self, turn)
        finally:
            if TURN_RECORDS:
                TURN_RECORDS[-1]["returned"] = time.monotonic()

    monkeypatch.setattr(GuardedDockerTurnRunner, "_plan", plan)
    monkeypatch.setattr(GuardedDockerTurnRunner, "run_turn", run_turn)


def latest_late() -> float:
    """The last turn's runner return minus its one deadline D: a strict check asserts it is <= 0."""
    record = TURN_RECORDS[-1]
    return record["returned"] - record["plan"].deadline


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


def assert_outputs_clean_and_held_evidence_private(tmp_path: Path, runner) -> None:
    """No turn folder holds the credential; anything held aside is private (mode 700) and gone after the purge."""
    evidence = tmp_path / "evidence"
    for turn_folder in evidence.glob("turn-*"):
        assert plain_bytes_leak(turn_folder, OLD) == []
    assert all(held.stat().st_mode & 0o077 == 0 for held in evidence.glob("quarantine-*"))
    runner.purge_quarantine()
    assert not list(evidence.glob("quarantine-*")) and plain_bytes_leak(evidence, OLD) == []


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
    assert sorted(p.name.split("-", 2)[2] for p in (tmp_path / "evidence").glob("turn-*")) == ["attempt-a", "attempt-b"]
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


def test_evidence_that_cannot_be_sealed_in_time_stops_the_turn_and_is_not_left_as_output(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    install_process(monkeypatch, lambda output: (output / "provider-error.log").write_text(OLD))
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=0.3)
    from dataclasses import replace as replace_plan
    original_plan = runner._plan
    monkeypatch.setattr(runner, "_plan", lambda: replace_plan(original_plan(), seal_deadline=time.monotonic() - 1.0))
    # no time at all to seal: the seal share is already spent, while the job itself is still inside its budget

    with pytest.raises(EvidenceNotSealed):  # removed while removal has time, else moved to quarantine and named
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert list((tmp_path / "evidence").glob("turn-*/output")) == []
    assert all(held.stat().st_mode & 0o077 == 0 for held in (tmp_path / "evidence").glob("quarantine-*"))
    runner.purge_quarantine()  # between turns, with no clock
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
               secret: bool = True, ledger: bool = True, stop_budget_spent: bool = False, timeout: float = 0.1):
    """Runs one guarded turn with a slow docker CLI. Returns (late, outcome, spend, evidence, calls, plan).

    `late` is the runner's own return minus the plan's one deadline D (no tolerance: it must be <= 0); `calls` holds
    (monotonic start, args, timeout) of each docker CLI call. With `stop_budget_spent` the stop share ends when the job
    wait ends, so the stop step finds its budget already spent.
    """
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    calls: list[tuple[float, tuple, float | None]] = []
    started = time.monotonic()

    def cli(*args, timeout=None, **_kw):
        calls.append((time.monotonic(), args, timeout))
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
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=timeout, seal_grace_seconds=grace)
    if stop_budget_spent:
        from dataclasses import replace as replace_plan
        original_plan = runner._plan
        monkeypatch.setattr(runner, "_plan", lambda: (lambda plan: replace_plan(plan, stop_deadline=plan.job_deadline))(original_plan()))
    plans, _removals = _spy_plan_and_removal(monkeypatch, runner)
    runner_returned = _record_runner_return(monkeypatch, runner)
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
    late = runner_returned[0] - plans[0].deadline
    print(f"grace {grace}: runner return minus D {late:+.4f} s")  # kept as a measured value in the receipt
    return late, outcome[0], spend, tmp_path / "evidence", calls, plans[0]


def sleeps_exactly_its_timeout(*args, timeout=None, **_kw):
    time.sleep(timeout)
    raise subprocess.TimeoutExpired("controlled-owned-stop", timeout)


def test_a_stop_command_that_hangs_cannot_run_the_turn_past_the_job_timeout_plus_grace(tmp_path: Path, monkeypatch) -> None:
    late, outcome, spend, evidence, calls, _plan = timed_turn(tmp_path, monkeypatch, docker=sleeps_exactly_its_timeout, grace=1.0)

    assert outcome == "EvidenceNotSealed" and late <= 0.0, late
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("UNKNOWN", RESERVATION)
    assert not list(evidence.glob("turn-*/output")) and plain_bytes_leak(evidence, OLD) == []
    assert len(calls) == 1, "a second command was started after the first had used the budget"


def test_no_command_starts_once_the_budget_is_spent(tmp_path: Path, monkeypatch) -> None:
    late, outcome, _, evidence, calls, _plan = timed_turn(tmp_path, monkeypatch, docker=sleeps_exactly_its_timeout, grace=0.0,
                                                         stop_budget_spent=True, timeout=0.3)  # 0.1 s would leave only 0.02 s to launch

    assert outcome == "EvidenceNotSealed" and calls == [] and late <= 0.0, (calls, late)
    assert not list(evidence.glob("turn-*/output"))


def test_every_docker_command_fits_inside_the_remaining_budget(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module

    class RunnerClock:  # the runner's own clock: remembers the last reading, which is the one a timeout came from
        last = 0.0

        def monotonic(self) -> float:
            RunnerClock.last = time.monotonic()
            return RunnerClock.last

        def __getattr__(self, name):
            return getattr(time, name)

    monkeypatch.setattr(module, "time", RunnerClock())
    command_ends: list[float] = []

    def recorded(*args, timeout=None, **kwargs):
        command_ends.append(RunnerClock.last + timeout)  # when the runner read its clock, plus the time it allowed
        return sleeps_exactly_its_timeout(*args, timeout=timeout, **kwargs)

    late, _, _, _, calls, plan = timed_turn(tmp_path, monkeypatch, docker=recorded, grace=0.8)

    assert calls and all(end <= plan.stop_deadline for end in command_ends), [e - plan.stop_deadline for e in command_ends]
    assert late <= 0.0, late


def healthy_docker(*args, timeout=None, **_kw):
    if args[0] == "inspect":
        return subprocess.CompletedProcess(args, 1, "", "")
    return subprocess.CompletedProcess(args, 0, "", "")


def test_the_wait_for_the_stopped_client_is_part_of_the_same_budget(tmp_path: Path, monkeypatch) -> None:
    late, outcome, _, evidence, _, _plan = timed_turn(tmp_path, monkeypatch, docker=healthy_docker, communicate_after_timeout=5.0, grace=1.0)

    assert late <= 0.0, late  # a fresh five-second wait would have taken five seconds
    assert outcome in ("returned", "EvidenceNotSealed") and plain_bytes_leak(evidence, OLD) == []


@pytest.mark.parametrize("fail_wait", [True, False])  # False: the job times out and the stop runs inside the turn first
def test_a_failed_stop_is_not_repeated_by_the_cleanup_of_the_failure(tmp_path: Path, monkeypatch, fail_wait: bool) -> None:
    def failing(*args, timeout=None, **_kw):
        raise subprocess.TimeoutExpired("controlled-owned-stop", 0.01)

    _, outcome, spend, evidence, calls, _plan = timed_turn(tmp_path, monkeypatch, docker=failing, fail_wait=fail_wait, grace=1.0)

    assert outcome == "EvidenceNotSealed"  # the failed stop is reported, not hidden behind the original failure
    assert len([call for call in calls if call[1][0] == "inspect"]) == 1
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("UNKNOWN", RESERVATION)
    assert not list(evidence.glob("turn-*/output"))


def test_the_pauses_between_listings_are_part_of_the_same_budget(tmp_path: Path, monkeypatch) -> None:
    def present_forever(*args, timeout=None, **_kw):
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, "abc\n", "")
        return subprocess.CompletedProcess(args, 0, f"/{args[1]} repair-test\n" if args[0] == "inspect" else "", "")

    late, outcome, _, evidence, _, _plan = timed_turn(tmp_path, monkeypatch, docker=present_forever, grace=1.0)

    assert outcome == "EvidenceNotSealed" and late <= 0.0, late
    assert not list(evidence.glob("turn-*/output"))


# --- Repairs after round-8 review: removal of a huge output is bounded, and the settings are checked ---------------

def test_removing_a_huge_output_after_a_missed_bound_cannot_run_the_turn_past_the_deadline(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(module, "MAX_ENTRIES", 10_000_000)  # the count limit is not what stops this one
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # present and not ours: never stoppable
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    crowd = tmp_path / "crowd"  # made before the turn and moved in by the job in one step: only cleanup is on the clock
    crowd.mkdir()
    for index in range(40_000):
        (crowd / f"f{index}.log").write_text("x")
    (crowd / "secret.log").write_text(OLD)

    def behaviour(output: Path) -> None:
        os.rename(crowd, output / "crowd")

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
    assert latest_late() <= 0.0, (outcome, latest_late())  # deleting 40,000 files takes seconds; the turn must not wait for it
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
    # The job's files are made before the turn and moved into the output in one step while the job runs, so the time
    # checked against D is the runner's own work, not the stand-in's (a real wait would time the job out).
    staged = tmp_path / "staged"
    staged.mkdir()
    behaviour(staged)

    def move_in(output: Path) -> None:
        for entry in list(staged.iterdir()):
            os.rename(entry, output / entry.name)

    install_process(monkeypatch, move_in, returncode=-9)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=grace)
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

    assert latest_late() <= 0.0, (outcome, latest_late())
    assert not list((tmp_path / "evidence").glob("turn-*/output"))
    runner.purge_quarantine()
    assert not list((tmp_path / "evidence").glob("quarantine-*"))


def test_a_path_too_long_for_the_plain_walk_is_moved_not_removed_without_a_clock(tmp_path: Path, monkeypatch) -> None:
    def chain_and_files(output: Path) -> None:
        write_deep_chain(output, 700, files=1_500, secret=OLD)  # deep files are slow to create and to remove: about 1.5 ms each

    runner, outcome = run_removal_turn(tmp_path, monkeypatch, chain_and_files)

    assert latest_late() <= 0.0, (outcome, latest_late())
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

    assert latest_late() <= 0.0, (outcome, latest_late())  # an unbounded removal of 40,000 files would take seconds
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

    assert latest_late() <= 0.0, (status, latest_late())


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

    assert latest_late() <= 0.0, (status, latest_late())
    kept = sum(p.stat().st_size for p in (tmp_path / "evidence").glob("turn-*/**/*stdout*") if p.is_file())
    assert kept <= module.MAX_STDOUT_BYTES
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)


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

    with pytest.raises(EvidenceNotSealed, match="quarantine-"):  # an over-limit stdout is held aside unscanned
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    kept = b"".join(p.read_bytes() for p in (tmp_path / "evidence").glob("turn-*/**/*stdout*") if p.is_file())
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)
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

    assert status in ("UNKNOWN", "EvidenceNotSealed") and latest_late() <= 0.0, (status, latest_late())
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

    with pytest.raises(EvidenceNotSealed, match="quarantine-"):  # an over-limit stdout is held aside unscanned
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    kept = b"".join(p.read_bytes() for p in (tmp_path / "evidence").glob("turn-*/**/*stdout*") if p.is_file())
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)
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
    assert latest_late() <= 0.0, (status, latest_late())


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

    assert latest_late() <= 0.0, (status, latest_late())
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)


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


# --- Repair after round-20 review: a docker CLI that streams without end cannot stretch the stop step ---------------

def test_a_docker_cli_that_streams_without_end_cannot_run_the_turn_past_its_deadline(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text("#!/bin/sh\nexec yes xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n")
    (fake_bin / "docker").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setattr(docker_turn_runner, "docker", module.BASE_DOCKER_CLI)  # the real helpers, the fake docker on PATH
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    install_process(monkeypatch, lambda output: None, returncode=-9)  # a client killed by a signal: the stop step runs
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.1, seal_grace_seconds=5.0)

    status, elapsed = _timed_run(runner, limit=120)

    assert status == "EvidenceNotSealed" and latest_late() <= 0.0, (status, latest_late())


# --- Repair after gate 6/6: cleanup never renews the one deadline, and sealing stops in time to remove ---------------

from guarded_docker_runner import holds_credential  # noqa: E402
from leak_scan import encodings  # noqa: E402

def _record_runner_return(monkeypatch, runner) -> list[float]:
    """Record the moment the guarded Docker runner itself returns or raises, before the ledger commits."""
    returned: list[float] = []
    original = runner.run_turn

    def timed(turn):
        try:
            return original(turn)
        finally:
            returned.append(time.monotonic())

    monkeypatch.setattr(runner, "run_turn", timed)
    return returned


def _spy_plan_and_removal(monkeypatch, runner) -> tuple[list, list]:
    """Record the turn's plan and every removal deadline that the runner asks for."""
    plans: list = []
    removals: list[float] = []
    original_plan, original_remove = runner._plan, GuardedDockerTurnRunner._remove_tree

    def plan():
        plans.append(original_plan())
        return plans[-1]

    def remove(folder, until):
        removals.append(until)
        return original_remove(folder, until)

    monkeypatch.setattr(runner, "_plan", plan)
    monkeypatch.setattr(GuardedDockerTurnRunner, "_remove_tree", staticmethod(remove))
    return plans, removals


def test_an_exhausted_turn_gives_evidence_removal_no_time_past_the_original_deadline(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    prepared = tmp_path / "prepared"  # made before the turn: only the cleanup is on the clock
    prepared.mkdir()
    for index in range(4000):
        (prepared / f"f{index}.log").write_text("x")
    (prepared / "secret.log").write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # present and not ours: never stoppable
    install_process(monkeypatch, lambda output: prepared.rename(output / "many"), returncode=-9)
    # 0.3 s: a budget of 0.1 s with no grace would leave only 0.02 s to launch after the post-job reserve
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=0.3, seal_grace_seconds=0.0)
    plans, removals = _spy_plan_and_removal(monkeypatch, runner)

    status, elapsed = _timed_run(guarded)

    assert status == "EvidenceNotSealed"
    assert removals and all(until <= plans[0].deadline for until in removals), "cleanup was given renewed time"
    assert latest_late() <= 0.0, latest_late()  # the move into quarantine fits inside D as well
    assert list((tmp_path / "evidence").glob("turn-*/output")) == []
    held = list((tmp_path / "evidence").glob("quarantine-*"))
    assert all(folder.stat().st_mode & 0o077 == 0 for folder in held)  # unread by others, never published as output
    assert spend.state("attempt-1") == "UNKNOWN" and spend.committed_usd() == Decimal("0.054848")
    runner.purge_quarantine()  # between turns, with no clock: separate from the timed turn
    assert not list((tmp_path / "evidence").glob("quarantine-*")) and plain_bytes_leak(tmp_path / "evidence", OLD) == []


@pytest.mark.parametrize("shape", ["every-form", "dense-escapes"])
def test_sealing_a_supported_8_mib_file_ends_the_turn_inside_timeout_plus_grace(tmp_path: Path, monkeypatch, shape: str) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    pattern = b"|".join(encodings(OLD)) + b"|" if shape == "every-form" else b"\\u0061" * 100_000 + b"|"
    prepared = tmp_path / "large.log"
    prepared.write_bytes((pattern * (8 * 1024 * 1024 // len(pattern) + 1))[: 8 * 1024 * 1024])

    def behaviour(output: Path) -> None:
        prepared.rename(output / "large.log")
        time.sleep(0.98)  # the client runs almost the whole job timeout

    install_process(monkeypatch, behaviour, returncode=3)
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=0.3)
    plans, removals = _spy_plan_and_removal(monkeypatch, runner)

    status, elapsed = _timed_run(guarded)

    assert elapsed <= 1.0 + 0.3, (status, elapsed)  # strict: no tolerance on the accepted bound
    assert all(until <= plans[0].deadline for until in removals)
    assert spend.state("attempt-1") == "UNKNOWN" and spend.committed_usd() == Decimal("0.054848")
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []
    assert not list((tmp_path / "evidence").rglob("large.log")) or not holds_credential(
        next((tmp_path / "evidence").rglob("large.log")).read_bytes(), encodings(OLD))


def test_the_turn_plan_orders_its_deadlines_and_keeps_part_of_the_grace_for_removal() -> None:
    import guarded_docker_runner as module
    runner = GuardedDockerTurnRunner(image="unused", run_id="repair-test", evidence_dir=Path("/nonexistent"), policy=POLICY,
                                     script_for=lambda turn: {}, timeout_seconds=1.0, seal_grace_seconds=0.3)
    plan = runner._plan()
    assert plan.job_deadline <= plan.stop_deadline <= plan.seal_deadline < plan.deadline
    assert plan.deadline - plan.job_deadline == pytest.approx(0.3)
    assert isinstance(module.holds_credential(b"x", [b"y"], until=time.monotonic() + 1), bool)


def test_an_output_sealed_after_the_container_is_gone_is_not_sealed_a_second_time(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    install_process(monkeypatch, lambda output: (output / "provider-error.log").write_text("Bearer " + OLD), returncode=3)
    runner, spend, guarded = build(tmp_path, credential)
    walks: list[Path] = []
    original = GuardedDockerTurnRunner._redact.__func__

    def counted(cls, folder, secret, deadline, *rest):
        walks.append(folder)
        return original(cls, folder, secret, deadline, *rest)

    monkeypatch.setattr(GuardedDockerTurnRunner, "_redact", classmethod(counted))

    result = guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert result.status == "UNKNOWN" and len(walks) == 1, walks  # a second pass would spend the deadline for nothing
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == [] and spend.state("attempt-1") == "UNKNOWN"


# --- Repair after round-22 review: a large job-written file is never freed on the clock ------------------------------

def _spy_size_proportional_frees(monkeypatch) -> list[tuple[str, int]]:
    """Record every truncate or unlink of a plain file larger than the scan limit, while a turn runs."""
    import guarded_docker_runner as module
    large: list[tuple[str, int]] = []
    real_unlink, real_ftruncate = os.unlink, os.ftruncate

    def unlink(path, *, dir_fd=None):
        info = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
        if stat_module.S_ISREG(info.st_mode) and info.st_size > module.MAX_SCANNED_BYTES:
            large.append(("unlink", info.st_size))
        return real_unlink(path, dir_fd=dir_fd)

    def ftruncate(fd, length):
        size = os.fstat(fd).st_size
        if size > module.MAX_SCANNED_BYTES and length < size:
            large.append(("ftruncate", size))
        return real_ftruncate(fd, length)

    monkeypatch.setattr(module.os, "unlink", unlink)
    monkeypatch.setattr(module.os, "ftruncate", ftruncate)
    return large


import stat as stat_module  # noqa: E402


@pytest.mark.parametrize("where", ["stdout", "output-file"])
def test_a_huge_job_written_file_is_moved_aside_in_one_step_and_freed_only_by_the_purge(tmp_path: Path, monkeypatch, where: str) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    two_gib = 2 * 1024 * 1024 * 1024  # sparse: as large as a flood, without writing it

    def behaviour(output: Path) -> None:
        target = output / ("host-captured-stdout.log" if where == "stdout" else "huge.log")
        with open(target, "ab") as file:
            file.write(b"Bearer " + OLD.encode())
            file.truncate(two_gib)

    install_process(monkeypatch, behaviour, returncode=3)
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=5, seal_grace_seconds=0.3)
    large = _spy_size_proportional_frees(monkeypatch)

    status, _elapsed = _timed_run(guarded)

    assert large == [], f"the turn freed a job-sized file on the clock: {large}"
    assert status == "EvidenceNotSealed"  # held aside unscanned: never a success
    assert spend.state("attempt-1") == "UNKNOWN" and spend.committed_usd() == Decimal("0.054848")
    held = list((tmp_path / "evidence").glob("quarantine-*"))
    assert held and all(folder.stat().st_mode & 0o077 == 0 for folder in held)
    for folder in (tmp_path / "evidence").glob("turn-*/output"):  # what stays as output is small and sealed
        assert all(path.stat().st_size <= 1024 * 1024 for path in folder.rglob("*") if path.is_file())
    runner.purge_quarantine()  # between turns, with no clock: here the large file is freed
    assert not list((tmp_path / "evidence").glob("quarantine-*")) and plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_removal_on_the_clock_moves_an_output_holding_a_huge_file_instead_of_freeing_it(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # present and not ours: never stoppable

    def behaviour(output: Path) -> None:
        with open(output / "huge.log", "ab") as file:
            file.write(OLD.encode())
            file.truncate(2 * 1024 * 1024 * 1024)

    install_process(monkeypatch, behaviour, returncode=-9)
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=0.2, seal_grace_seconds=0.3)
    large = _spy_size_proportional_frees(monkeypatch)

    status, _elapsed = _timed_run(guarded)

    assert status == "EvidenceNotSealed" and large == [], large
    assert list((tmp_path / "evidence").glob("turn-*/output")) == []
    assert spend.state("attempt-1") == "UNKNOWN" and spend.committed_usd() == Decimal("0.054848")
    runner.purge_quarantine()
    assert not list((tmp_path / "evidence").glob("quarantine-*")) and plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_the_job_client_cannot_put_more_than_the_stdout_limit_on_host_disk(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  run) exec /usr/bin/python3 -I -c 'import os, time\nfor _ in range(64): os.write(1, b\"x\" * (1 << 20))\ntime.sleep(30)' ;;\n"
        "  inspect) exit 1 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n")
    (fake_bin / "docker").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setattr(docker_turn_runner, "docker", module.BASE_DOCKER_CLI)  # the real CLI helpers, the fake docker on PATH
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=0.3)

    status, elapsed = _timed_run(guarded, limit=60)

    written = sum(path.stat().st_size for path in (tmp_path / "evidence").rglob("*") if path.is_file())
    assert written <= module.MAX_STDOUT_BYTES + 64 * 1024, written  # the flood never reached host disk
    assert elapsed <= 1.0 + 0.3, (status, elapsed)
    assert spend.state("attempt-1") == "UNKNOWN" and spend.committed_usd() == Decimal("0.054848")
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)


# --- Repair after round-22 review A1: reading the result after sealing stays inside the one deadline -----------------

@pytest.mark.parametrize("exit_at", [0.955, 0.965, 0.975, 0.985])
def test_reading_a_hostile_4_mib_result_after_sealing_ends_inside_the_deadline(tmp_path: Path, monkeypatch, exit_at: float) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    lists = b"[]," * 600_000
    text = b"\\u0041" * 65_000 + OLD[:-3].encode() * 30_000  # never the whole credential
    result = b'{"x":[' + lists.rstrip(b",") + b'],"t":"' + text + b'"}'
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=0.3)
    plans, _removals = _spy_plan_and_removal(monkeypatch, runner)

    def behaviour(output: Path) -> None:  # the job writes its result, then exits by itself (code 0) late in the turn
        (output / "container-result.json").write_bytes(result)
        time.sleep(max(0.0, plans[0].job_deadline - 1.0 + exit_at - time.monotonic()))

    install_process(monkeypatch, behaviour, returncode=0)

    runner_returned = _record_runner_return(monkeypatch, runner)

    status, _elapsed = _timed_run(guarded)
    ended = time.monotonic()

    # The runner's own return is held to D with no tolerance; the ledger's commit after it is measured and kept apart.
    print("runner return minus D:", round(runner_returned[0] - plans[0].deadline, 4),
          "ledger commit after it:", round(ended - runner_returned[0], 4))
    assert runner_returned[0] <= plans[0].deadline, (status, runner_returned[0] - plans[0].deadline)
    # a late exit leaves sealing no time, and that fails closed too; either way the full reservation stays
    assert status in {"UNKNOWN", "EvidenceNotSealed"} and spend.state("attempt-1") == "UNKNOWN"
    assert spend.committed_usd() == Decimal("0.054848")
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)


# --- Repair after round-23 review A1: no job-chosen value is hashed unless its type is checked first ----------------

def _returned_result(evidence: list) -> bytes:
    import json as json_module
    return json_module.dumps({
        "hermes": {"outcome": "returned", "text": "ok", "error_class": None, "request_count": 1, "observed": {},
                   "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "reported": True}},
        "sandbox": {"network": {"blocked": True}},
        "guard": {"admitted_count": 1, "seen_count": len(evidence) + 1, "evidence": evidence}}).encode()


@pytest.mark.parametrize("reasons", ["colliding-integers", "plain-strings"])
def test_refusal_reasons_chosen_by_the_job_cannot_make_the_summary_quadratic(tmp_path: Path, monkeypatch, reasons: str) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    count = 4_000 if reasons == "colliding-integers" else 3  # fits under MAX_RESULT_BYTES, so the result is read
    evidence = [{"admitted": False, "reason": index * (2**61 - 1) if reasons == "colliding-integers" else "too-large"}
                for index in range(1, count + 1)]
    body = _returned_result(evidence)
    import guarded_docker_runner as module
    assert len(body) <= module.MAX_RESULT_BYTES
    install_process(monkeypatch, lambda output: (output / "container-result.json").write_bytes(body), returncode=0)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=0.3)
    outcome: list = []

    def go() -> None:
        started = time.monotonic()
        try:
            outcome.append(runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096)))
        except BaseException as error:  # noqa: BLE001
            outcome.append(error)
        outcome.append(time.monotonic() - started)

    worker = threading.Thread(target=go, daemon=True)
    worker.start()
    worker.join(timeout=120)

    assert not worker.is_alive() and outcome[1] <= 1.0 + 0.3, outcome[1:]
    result = outcome[0]
    if reasons == "colliding-integers":  # a reason that is not text is not a refusal the guard wrote
        assert result.status == "UNKNOWN" and result.error_class == "ContainerResultUnreadable", result
    else:
        assert result.status == "RETURNED" and result.observed["guard_refusal_reasons"] == ["too-large"], result


# --- Repair after round-23 review B1 and B2: held evidence is never a success, and a nested result fits its budget --

def test_a_returned_turn_whose_stdout_was_held_aside_unscanned_fails_closed_and_names_the_folder(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    body = _returned_result([])

    def behaviour(output: Path) -> None:  # an honest result, and a stdout one byte over the limit that holds the credential
        (output / "container-result.json").write_bytes(body)
        stdout = (b"Bearer " + OLD.encode() + b"\n").ljust(module.MAX_STDOUT_BYTES + 1, b"x")
        (output / "host-captured-stdout.log").write_bytes(stdout)

    install_process(monkeypatch, behaviour, returncode=0)
    runner, spend, guarded = build(tmp_path, credential)

    with pytest.raises(EvidenceNotSealed, match="quarantine-"):
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert spend.state("attempt-1") == "UNKNOWN" and spend.committed_usd() == Decimal("0.054848")
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)


@pytest.mark.parametrize("exit_at", [0.955, 0.965, 0.975, 0.985])
def test_a_deeply_nested_result_at_the_size_limit_is_read_inside_the_deadline_or_not_at_all(
        tmp_path: Path, monkeypatch, exit_at: float) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    unit = b"[" * 12 + b"]" * 12 + b","
    filler = (unit * (module.MAX_RESULT_BYTES // len(unit)))[: module.MAX_RESULT_BYTES - 200].rstrip(b",")
    result = b'{"x":[' + filler + b"]}"
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=0.3)
    plans, _removals = _spy_plan_and_removal(monkeypatch, runner)

    def behaviour(output: Path) -> None:
        (output / "container-result.json").write_bytes(result)
        time.sleep(max(0.0, plans[0].job_deadline - 1.0 + exit_at - time.monotonic()))

    install_process(monkeypatch, behaviour, returncode=0)

    runner_returned = _record_runner_return(monkeypatch, runner)

    status, _elapsed = _timed_run(guarded)
    ended = time.monotonic()

    # The runner's own return is held to D with no tolerance; the ledger's commit after it is measured and kept apart.
    print("runner return minus D:", round(runner_returned[0] - plans[0].deadline, 4),
          "ledger commit after it:", round(ended - runner_returned[0], 4))
    assert runner_returned[0] <= plans[0].deadline, (status, runner_returned[0] - plans[0].deadline)
    assert status in {"UNKNOWN", "EvidenceNotSealed"} and spend.committed_usd() == Decimal("0.054848")


def test_the_result_budget_covers_parsing_and_freeing_at_the_worst_measured_rate() -> None:
    """Round 23 measured up to 0.06 s per MiB to parse deeply nested lists under load, and freeing them costs about as
    much. Both happen in the turn, so the time that admits a result of the largest size must cover both."""
    import guarded_docker_runner as module
    worst_seconds = 2 * 0.06 * module.MAX_RESULT_BYTES / (1024 * 1024)
    admitted = module.RESULT_MIN_SECONDS + module.MAX_RESULT_BYTES * module.RESULT_SECONDS_PER_BYTE
    assert admitted >= 2 * worst_seconds, (admitted, worst_seconds)  # twice the worst, as the constant's comment says


def test_a_result_whose_freeing_runs_past_the_deadline_is_never_reported_as_returned(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    real_loads = module.json.loads

    class SlowToFree(dict):
        def __del__(self) -> None:
            time.sleep(0.6)  # freeing the parsed result outlasts the whole grace

    monkeypatch.setattr(module.json, "loads", lambda text, *a, **k: SlowToFree(real_loads(text, *a, **k)))
    body = _returned_result([])
    install_process(monkeypatch, lambda output: (output / "container-result.json").write_bytes(body), returncode=0)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.5, seal_grace_seconds=0.3)
    plans, _removals = _spy_plan_and_removal(monkeypatch, runner)

    result = runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert time.monotonic() > plans[0].deadline  # the free did run past the deadline
    assert result.status == "UNKNOWN", result  # so the turn may not claim a returned, exactly charged result


# --- Repair after round-24 review B1: no step that cannot be stopped is longer than what sealing keeps back ----------

@pytest.mark.parametrize("grace", [0.3, 0.0])
def test_undoing_the_most_escapes_allowed_in_an_8_mib_file_ends_inside_the_deadline(tmp_path: Path, monkeypatch, grace: float) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    size = 8 * 1024 * 1024
    tail = b"\\u0073" + OLD[1:].encode()  # the credential with its first character escaped
    body = b"\\ud800" * (module.MAX_ESCAPES - 1)  # exactly MAX_ESCAPES escapes: no shortcut, every one is undone
    data = body + b"z" * (size - len(body) - len(tail)) + tail
    runner, _, _ = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=grace)
    plans, _removals = _spy_plan_and_removal(monkeypatch, runner)
    late: list[float] = []
    for exit_at in (1.0 + grace * offset for offset in (-0.2, -0.1, -0.06, -0.04, -0.02, -0.01)):
        prepared = tmp_path / "large.log"
        prepared.write_bytes(data)

        def behaviour(output: Path, exit_at=exit_at, prepared=prepared) -> None:  # the job exits by itself at exit_at
            prepared.rename(output / "large.log")
            time.sleep(max(0.0, min(plans[-1].job_deadline - 0.001, plans[-1].job_deadline - 1.0 + exit_at) - time.monotonic()))

        install_process(monkeypatch, behaviour, returncode=3)
        try:
            runner.run_turn(Turn(f"attempt-{len(plans)}", "prompt", "task", "m", "route", 4096))
        except EvidenceNotSealed:
            pass
        late.append(time.monotonic() - plans[-1].deadline)

    # Strict with grace; with no grace at all a job that runs to its own deadline leaves no time after it, and only the
    # one-step move into quarantine (a rename) may end past the deadline.
    if grace:
        assert max(late) <= 0.0, late  # strict: the runner returns by its one deadline
    else:
        # With no grace, a job that runs to its own deadline leaves no time after it, and the failure handling and the
        # one-step move end a few ms past D. That is a measured overrun, NOT a deadline pass and not a tolerance
        # (controller deadline interpretation, 2026-10-12): it is printed and kept as evidence. Asserted here is only
        # the deterministic part: no removal is given time past D.
        print("grace-0 runner return minus D, per turn:", [round(value, 4) for value in late])
        assert all(until <= plan.deadline for plan, until in zip(plans, _removals)), "cleanup was given renewed time"
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)


def test_a_step_that_cannot_be_stopped_and_starts_just_before_sealing_stops_still_ends_inside_the_deadline(
        tmp_path: Path, monkeypatch) -> None:
    """Sealing keeps back STEP_RESERVE_SECONDS whatever the grace; a 20 ms step that starts at its last moment fits."""
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    real_holds = module.holds_credential

    def slow_holds(data, forms, until=math.inf):
        found = real_holds(data, forms, until)  # its own clock check comes first
        time.sleep(0.02)  # then 20 ms that nothing can stop, like replacing one form in 8 MiB under load
        return found

    monkeypatch.setattr(module, "holds_credential", slow_holds)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=0.3)
    plans, _removals = _spy_plan_and_removal(monkeypatch, runner)
    late: list[float] = []
    for offset in (0.27, 0.275, 0.28, 0.285, 0.29):  # the job exits this long before the deadline
        def behaviour(output: Path, offset=offset) -> None:
            for index in range(40):
                (output / f"f{index}.log").write_text("x" * 100)
            time.sleep(max(0.0, min(plans[-1].job_deadline - 0.001, plans[-1].deadline - offset) - time.monotonic()))

        install_process(monkeypatch, behaviour, returncode=3)
        try:
            runner.run_turn(Turn(f"attempt-{len(plans)}", "prompt", "task", "m", "route", 4096))
        except EvidenceNotSealed:
            pass
        late.append(time.monotonic() - plans[-1].deadline)

    assert max(late) <= 0.0, late
    assert_outputs_clean_and_held_evidence_private(tmp_path, runner)


def test_removal_that_cannot_finish_leaves_time_for_the_move_inside_the_deadline(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    for index in range(40_000):
        (prepared / f"f{index}.log").write_text("x")
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # present and not ours: never stoppable
    install_process(monkeypatch, lambda output: prepared.rename(output / "many"), returncode=-9)
    runner, spend, _guarded = build(tmp_path, credential, timeout_seconds=0.2, seal_grace_seconds=0.3)
    plans, removals = _spy_plan_and_removal(monkeypatch, runner)

    with pytest.raises(EvidenceNotSealed, match="quarantine-"):
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    ended = time.monotonic()

    assert removals and ended <= plans[0].deadline, (ended - plans[0].deadline, [u - plans[0].deadline for u in removals])
    runner.purge_quarantine()


def test_a_large_file_holding_the_credential_is_deleted_whole_and_a_small_one_is_redacted(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def behaviour(output: Path) -> None:
        (output / "small.log").write_text("Bearer " + OLD + "\n")
        (output / "large.log").write_bytes(b"Bearer " + OLD.encode() + b"\n" + b"y" * (module.REWRITE_LIMIT_BYTES + 1))

    install_process(monkeypatch, behaviour, returncode=3)
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    output = next((tmp_path / "evidence").glob("turn-*/output"))
    assert not (output / "large.log").exists()  # replacing in it would be a long step: it is deleted instead
    assert (output / "small.log").read_text() == "Bearer [REDACTED]\n"
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_undoing_escapes_stops_part_way_when_the_clock_runs_out() -> None:
    import guarded_docker_runner as module
    data = b"\\ud800" * (module.MAX_ESCAPES - 1) + b"z" * 1024  # every escape undone: about 0.02 s in one piece
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        module.holds_credential(data, encodings(OLD), until=started + 0.003)
    assert time.monotonic() - started < 0.012  # stopped within a batch, not after the whole undo


# --- Controller job-budget disposition (2026-10-12): the job wait leaves the post-job reserve inside D -------------

def _job_that_runs_to_its_timeout(monkeypatch) -> None:
    """A stand-in `docker run` client that never ends by itself: it honours the wait's timeout, like the real one."""
    real_popen = subprocess.Popen

    class Endless:
        returncode = None

        def __init__(self, argv, **_kw) -> None:
            self.argv = argv

        def communicate(self, timeout=None):
            if timeout is None:
                return b"", None
            time.sleep(timeout)
            raise subprocess.TimeoutExpired("docker run", timeout)

        def kill(self) -> None:
            self.returncode = -9

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: Endless(argv, **kw) if argv[:2] == ["docker", "run"] else real_popen(argv, **kw))


@pytest.mark.parametrize("timeout, grace", [(0.5, 0.0), (0.5, 0.02), (0.5, 0.3), (0.5, 5.0)])
def test_a_job_that_runs_to_its_timeout_still_ends_the_turn_by_the_deadline(tmp_path: Path, monkeypatch, timeout: float, grace: float) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    _job_that_runs_to_its_timeout(monkeypatch)
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=timeout, seal_grace_seconds=grace)
    plans, removals = _spy_plan_and_removal(monkeypatch, runner)
    runner_returned = _record_runner_return(monkeypatch, runner)

    status, _elapsed = _timed_run(guarded)
    settled = time.monotonic()

    plan = plans[0]
    print(f"timeout {timeout} grace {grace}: runner return minus D {runner_returned[0] - plan.deadline:+.4f} s,"
          f" spend settlement after it {settled - runner_returned[0]:.4f} s")
    assert plan.job_deadline <= plan.deadline - module.POST_JOB_RESERVE_SECONDS  # the wait leaves the reserve
    assert runner_returned[0] <= plan.deadline, (status, runner_returned[0] - plan.deadline)
    assert all(until <= plan.deadline for until in removals)
    assert spend.state("attempt-1") == "UNKNOWN" and spend.committed_usd() == Decimal("0.054848")


def test_a_budget_too_small_for_the_post_job_reserve_starts_no_job(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    launched = install_process(monkeypatch, lambda output: None)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=0.05, seal_grace_seconds=0.0)

    result = runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert launched == [] and result.status == "PROVIDER_FAILED" and result.request_count == 0
    assert result.error_class == "DeadlinePassedBeforeLaunch"


def test_a_negative_grace_is_refused_when_built_and_before_any_turn_effect(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(ValueError, match="negative"):
        GuardedDockerTurnRunner(image="unused", run_id="repair-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                                script_for=lambda turn: {}, timeout_seconds=1.0, seal_grace_seconds=-0.2)
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    launched = install_process(monkeypatch, lambda output: None)
    runner, _, _ = build(tmp_path, credential, timeout_seconds=1.0, seal_grace_seconds=0.3)
    runner.seal_grace_seconds = -0.2  # changed after construction

    with pytest.raises(ValueError, match="negative"):
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert launched == [] and runner.turn_count == 0 and not (tmp_path / "evidence").exists()


# --- Supervised recovery (accepted cleanup rule, 2026-10-12; .scratch/p05-provider/evidence/SUPERVISED_RECOVERY_CONTRACT*.md)

import json as _json  # noqa: E402


def _records(tmp_path: Path) -> list[dict]:
    folder = tmp_path / "evidence" / "pending-cleanup"
    return [_json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))] if folder.exists() else []


def _unstoppable_flood_turn(tmp_path: Path, monkeypatch, *, files: int = 40_000, **build_kwargs):
    """A turn whose container is present and not ours (never stoppable), with a big output made before the turn."""
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    staged = tmp_path / "staged"
    staged.mkdir()
    for index in range(files):
        (staged / f"f{index}.log").write_text("x")
    (staged / "secret.log").write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))
    install_process(monkeypatch, lambda output: os.rename(staged, output / "many"), returncode=-9)
    return build(tmp_path, credential, **build_kwargs)


def test_the_foreground_unlinks_no_more_than_a_small_bounded_number_of_job_files(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    runner, spend, guarded = _unstoppable_flood_turn(tmp_path, monkeypatch, timeout_seconds=0.3, seal_grace_seconds=5.0)
    unlinked: list[str] = []
    real_unlink = os.unlink

    def counting_unlink(path, *, dir_fd=None):
        unlinked.append(path)
        return real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(module.os, "unlink", counting_unlink)
    status, _elapsed = _timed_run(guarded, limit=60)

    assert status == "EvidenceNotSealed" and len(unlinked) <= module.FOREGROUND_REMOVAL_ENTRIES, len(unlinked)
    assert latest_late() <= 0.0, latest_late()
    assert list((tmp_path / "evidence").glob("turn-*/output")) == []
    assert spend.state("attempt-1") == "UNKNOWN" and spend.committed_usd() == Decimal("0.054848")
    pending = _records(tmp_path)
    assert len(pending) == 1 and pending[0]["state"] == "pending" and pending[0]["held"]


def test_a_pending_cleanup_record_is_written_before_the_job_starts_and_removed_after_a_clean_turn(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    seen: list[list[dict]] = []
    install_process(monkeypatch, lambda output: seen.append(_records(tmp_path)), returncode=3)
    runner, _, _ = build(tmp_path, credential)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert len(seen[0]) == 1 and seen[0][0]["state"] == "running" and seen[0][0]["container"].startswith("p05-repair-test-")
    assert OLD not in _json.dumps(seen[0][0])
    assert _records(tmp_path) == []  # a clean end leaves nothing pending


def test_recovery_at_the_next_turn_removes_held_evidence_and_unblocks_new_work(tmp_path: Path, monkeypatch) -> None:
    runner, spend, guarded = _unstoppable_flood_turn(tmp_path, monkeypatch, files=2_000, timeout_seconds=0.3, seal_grace_seconds=0.3)
    with pytest.raises(EvidenceNotSealed):
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    assert _records(tmp_path) and list((tmp_path / "evidence").glob("quarantine-*"))
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False))  # the container is gone now
    install_process(monkeypatch, lambda output: None, returncode=3)

    result = guarded.run_turn(Turn("attempt-2", "prompt", "task", "m", "route", 4096))

    assert result.error_class != "CleanupPending" and _records(tmp_path) == []
    assert not list((tmp_path / "evidence").glob("quarantine-*")) and plain_bytes_leak(tmp_path / "evidence", OLD) == []
    assert spend.state("attempt-1") == "UNKNOWN"  # recovery never releases the unknown charge


def test_new_work_is_refused_while_cleanup_cannot_be_confirmed(tmp_path: Path, monkeypatch) -> None:
    runner, spend, guarded = _unstoppable_flood_turn(tmp_path, monkeypatch, files=10, timeout_seconds=0.3, seal_grace_seconds=0.3)
    with pytest.raises(EvidenceNotSealed):
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    launched = install_process(monkeypatch, lambda output: None, returncode=3)

    result = guarded.run_turn(Turn("attempt-2", "prompt", "task", "m", "route", 4096))

    assert result.status == "PROVIDER_FAILED" and result.request_count == 0 and result.error_class == "CleanupPending"
    assert launched == []
    assert spend.state("attempt-2") == "RELEASED" and spend.state("attempt-1") == "UNKNOWN"
    assert spend.committed_usd() == Decimal("0.054848")


def test_recovery_attempts_are_finite_and_an_exhausted_record_keeps_blocking(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    monkeypatch.setattr(module, "RECOVERY_BACKOFF_SECONDS", 0.0)
    runner, _, guarded = _unstoppable_flood_turn(tmp_path, monkeypatch, files=10, timeout_seconds=0.3, seal_grace_seconds=0.3,
                                                 recovery_budget_seconds=0.3)
    with pytest.raises(EvidenceNotSealed):
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    calls: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False, record=calls))

    for _ in range(module.MAX_RECOVERY_ATTEMPTS + 3):
        runner.recover_pending(0.3)
    after_exhaustion = len(calls)
    runner.recover_pending(0.3)

    record = _records(tmp_path)[0]
    assert record["state"] == "exhausted" and record["attempts"] == module.MAX_RECOVERY_ATTEMPTS
    assert len(record["history"]) == module.MAX_RECOVERY_ATTEMPTS and len(calls) == after_exhaustion  # no more attempts
    assert all(entry["end"] - entry["start"] <= entry["budget"] for entry in record["history"]), record["history"]
    result = runner.run_turn(Turn("attempt-2", "prompt", "task", "m", "route", 4096))
    assert result.error_class == "CleanupPending"
    assert [r["container"] for r in runner.pending_cleanup()] == [record["container"]]


def test_a_new_runner_after_a_restart_recovers_what_an_interrupted_turn_left(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def crash(output: Path) -> None:
        (output / "secret.log").write_text(OLD)
        raise SystemExit("the host process died during the turn")  # after registration, before any confirmation

    install_process(monkeypatch, crash, returncode=3)
    runner, _, _ = build(tmp_path, credential)
    monkeypatch.setattr(GuardedDockerTurnRunner, "_quarantine", lambda self, output, plan: None)  # the process dies first
    with pytest.raises(SystemExit):
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    monkeypatch.undo()
    assert len(_records(tmp_path)) == 1  # the identity survived the interrupted turn
    path = next((tmp_path / "evidence" / "pending-cleanup").glob("*.json"))
    data = _json.loads(path.read_text())
    data["pid"] = 999_999  # a process that no longer runs
    path.write_text(_json.dumps(data))
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False))

    restarted = GuardedDockerTurnRunner(image="unused", run_id="repair-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                                        credential_file=credential, script_for=lambda turn: {}, timeout_seconds=60)
    restarted.recover_pending(5.0)

    assert _records(tmp_path) == [] and not list((tmp_path / "evidence").glob("turn-*/output"))
    assert plain_bytes_leak(tmp_path / "evidence", OLD) == []


def test_records_of_another_run_are_neither_recovered_nor_counted(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    foreign = {"version": 1, "run_id": "someone-else", "label": "someone-else", "container": "p05-someone-else-abc-01",
               "turn_folder": "turn-01-x", "held": [], "state": "pending", "attempts": 0, "pid": 999_999,
               "created": 0, "last_attempt": None, "next_attempt_after": 0, "history": []}
    (folder / "turn-01-x.json").write_text(_json.dumps(foreign))
    calls: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(record=calls))
    install_process(monkeypatch, lambda output: None, returncode=3)
    runner, _, _ = build(tmp_path, credential)

    result = runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert result.error_class != "CleanupPending"
    assert not any(args[0] == "kill" and "someone-else" in args[1] for args, _ in calls)
    assert _json.loads((folder / "turn-01-x.json").read_text()) == foreign  # untouched


@pytest.mark.parametrize("budget", [0, -1.0, float("nan"), float("inf")])
def test_an_invalid_recovery_budget_is_refused(tmp_path: Path, budget: float) -> None:
    with pytest.raises(ValueError):
        GuardedDockerTurnRunner(image="unused", run_id="repair-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                                script_for=lambda turn: {}, timeout_seconds=1.0, recovery_budget_seconds=budget)


def test_recovery_never_touches_a_turn_that_is_still_running_in_a_live_process(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    running = {"version": 1, "run_id": "repair-test", "label": "repair-test", "container": "p05-repair-test-live-01",
               "turn_folder": "turn-01-live", "held": [], "state": "running", "attempts": 0, "pid": os.getpid(),
               "created": 0, "last_attempt": None, "next_attempt_after": 0, "history": []}
    (folder / "turn-01-live.json").write_text(_json.dumps(running))
    import guarded_docker_runner as module
    monkeypatch.setattr(module, "_ACTIVE_RECORDS", {str(folder / "turn-01-live.json")})  # a turn this process runs now
    held = GuardedDockerTurnRunner._try_lock(folder / "turn-01-live.json")  # ... and holds its lock, as a live turn does
    calls: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(record=calls))
    runner, _, _ = build(tmp_path, credential)

    try:
        runner.recover_pending(1.0)
    finally:
        GuardedDockerTurnRunner._release(folder / "turn-01-live.json", held)

    assert calls == [] and _json.loads((folder / "turn-01-live.json").read_text()) == running  # a concurrent turn is left alone


# --- Repair after round-27 review: held large files are recoverable; a same-pid restart is not taken for a live turn --

def test_recovery_removes_a_held_file_larger_than_the_scan_limit(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)

    def behaviour(output: Path) -> None:
        with open(output / "huge.log", "ab") as file:
            file.write(OLD.encode())
            file.truncate(2 * 1024 * 1024 * 1024)  # sparse: held aside unscanned by sealing

    install_process(monkeypatch, behaviour, returncode=3)
    runner, spend, guarded = build(tmp_path, credential)
    with pytest.raises(EvidenceNotSealed):
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    assert _records(tmp_path) and list((tmp_path / "evidence").glob("quarantine-*-held"))

    runner.recover_pending(5.0)

    assert _records(tmp_path) == [] and not list((tmp_path / "evidence").glob("quarantine-*"))
    assert spend.state("attempt-1") == "UNKNOWN"


def test_an_exhausted_record_can_be_given_new_attempts_but_is_cleared_only_by_confirmed_recovery(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    monkeypatch.setattr(module, "RECOVERY_BACKOFF_SECONDS", 0.0)
    runner, _, guarded = _unstoppable_flood_turn(tmp_path, monkeypatch, files=10, timeout_seconds=0.3, seal_grace_seconds=0.3,
                                                 recovery_budget_seconds=0.3)
    with pytest.raises(EvidenceNotSealed):
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    for _ in range(module.MAX_RECOVERY_ATTEMPTS):
        runner.recover_pending(0.3)
    assert _records(tmp_path)[0]["state"] == "exhausted"

    assert runner.retry_exhausted() == 1
    record = _records(tmp_path)[0]
    assert record["state"] == "pending" and record["attempts"] == 0 and len(record["history"]) == module.MAX_RECOVERY_ATTEMPTS
    assert guarded.run_turn(Turn("attempt-2", "prompt", "task", "m", "route", 4096)).error_class == "CleanupPending"  # still blocked
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False))  # the person removed the container
    runner.recover_pending(5.0)
    assert _records(tmp_path) == []


def test_a_running_record_left_by_an_earlier_process_with_the_same_pid_is_recovered_and_blocks(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    turn = tmp_path / "evidence" / "turn-01-old"
    (turn / "output").mkdir(parents=True)
    (turn / "output" / "secret.log").write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    stale = {"version": 1, "run_id": "repair-test", "label": "repair-test", "container": "p05-repair-test-old-01",
             "turn_folder": "turn-01-old", "held": [], "state": "running", "attempts": 0, "pid": os.getpid(),
             "created": 0, "last_attempt": None,
             "next_attempt_after": 0, "history": []}
    (folder / "turn-01-old.json").write_text(_json.dumps(stale))
    calls: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=True, record=calls))  # the old container is there
    launched = install_process(monkeypatch, lambda output: None, returncode=3)
    runner, _, guarded = build(tmp_path, credential, recovery_budget_seconds=1.0)

    guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert any(args[0] == "kill" and args[1] == "p05-repair-test-old-01" for args, _ in calls)  # checked and stopped
    assert not (turn / "output").exists() and plain_bytes_leak(tmp_path / "evidence", OLD) == []
    assert _records(tmp_path) == [] and launched  # recovered first, then the new job


def test_a_running_turn_of_another_live_process_blocks_new_work_and_is_not_touched(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    other = {"version": 1, "run_id": "repair-test", "label": "repair-test", "container": "p05-repair-test-other-01",
             "turn_folder": "turn-01-other", "held": [], "state": "running", "attempts": 0, "pid": os.getppid(),
             "created": 0, "last_attempt": None, "next_attempt_after": 0, "history": []}
    (folder / "turn-01-other.json").write_text(_json.dumps(other))
    owner = _hold_lock_in_another_process(folder / ".turn-01-other.json.lock")
    calls: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(record=calls))
    launched = install_process(monkeypatch, lambda output: None, returncode=3)
    runner, _, guarded = build(tmp_path, credential)

    try:
        result = guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    finally:
        owner.kill()
        owner.wait()

    assert result.error_class == "CleanupPending" and launched == [] and calls == []
    assert _json.loads((folder / "turn-01-other.json").read_text()) == other


def test_a_turn_whose_pending_mark_could_not_be_written_still_blocks_and_is_recovered(tmp_path: Path, monkeypatch) -> None:
    """If writing the final 'pending' state fails (a full disk the job can cause), the record stays 'running' with this
    process's pid and token; once the turn has ended it must not pass for a live turn."""
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # present and not ours: never stoppable
    install_process(monkeypatch, lambda output: (output / "secret.log").write_text(OLD), returncode=-9)
    runner, spend, guarded = build(tmp_path, credential, timeout_seconds=0.3, seal_grace_seconds=0.3)
    monkeypatch.setattr(GuardedDockerTurnRunner, "_mark_pending", lambda self, path, task_dir: None)  # the write fails
    with pytest.raises(EvidenceNotSealed):
        guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    assert _records(tmp_path)[0]["state"] == "running"
    launched = install_process(monkeypatch, lambda output: None, returncode=3)

    result = guarded.run_turn(Turn("attempt-2", "prompt", "task", "m", "route", 4096))

    assert result.error_class == "CleanupPending" and launched == []
    assert spend.state("attempt-1") == "UNKNOWN"


def test_a_concurrent_recovery_right_after_registration_never_takes_the_new_turn_for_a_left_behind_one(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False))
    launched = install_process(monkeypatch, lambda output: None, returncode=3)
    runner, _, _ = build(tmp_path, credential)
    original_register = GuardedDockerTurnRunner._register
    seen: list = []

    def register_then_another_thread_recovers(self, plan, task_dir):
        path = original_register(self, plan, task_dir)
        self.recover_pending(1.0)  # what a concurrent turn's recovery could do at exactly this moment
        seen.append((_records(tmp_path), (task_dir / "output").exists()))
        return path

    monkeypatch.setattr(GuardedDockerTurnRunner, "_register", register_then_another_thread_recovers)

    runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    records, _output_not_made_yet = seen[0]  # the output folder is made only after registration
    assert len(records) == 1 and records[0]["state"] == "running" and launched  # not taken for one left behind
    assert next((tmp_path / "evidence").glob("turn-*/output")).exists()


# --- Repair after round-28 review A3: recovery decides on each record's current content, never on a stale listing ---

def test_recovery_never_acts_on_a_record_whose_turn_ended_cleanly_during_the_pass(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    evidence = tmp_path / "evidence"
    folder = evidence / "pending-cleanup"
    folder.mkdir(parents=True)
    base = {"version": 1, "run_id": "repair-test", "label": "repair-test", "held": [], "attempts": 0, "created": 0,
            "last_attempt": None, "next_attempt_after": 0, "history": []}
    left_behind = {**base, "container": "p05-repair-test-a-01", "turn_folder": "turn-01-a", "state": "pending", "pid": 999_999}
    live = {**base, "container": "p05-repair-test-b-02", "turn_folder": "turn-02-b", "state": "running", "pid": os.getpid()}
    (folder / "turn-01-a.json").write_text(_json.dumps(left_behind))
    (folder / "turn-02-b.json").write_text(_json.dumps(live))
    (evidence / "turn-02-b" / "output").mkdir(parents=True)
    (evidence / "turn-02-b" / "output" / "container-result.json").write_text("{}")  # the live turn's sealed result
    monkeypatch.setattr(module, "_ACTIVE_RECORDS", {str(folder / "turn-02-b.json")})
    live_lock = GuardedDockerTurnRunner._try_lock(folder / "turn-02-b.json")  # the live turn holds its lock
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False))
    runner, _, _ = build(tmp_path, credential)
    original = GuardedDockerTurnRunner._recover_one

    def recover_then_the_live_turn_ends(self, path, data, deadline, budget):
        original(self, path, data, deadline, budget)
        if path.name == "turn-01-a.json":  # meanwhile the live turn ends cleanly: record deleted, lock given back
            (folder / "turn-02-b.json").unlink()
            GuardedDockerTurnRunner._release(folder / "turn-02-b.json", live_lock)
            module._ACTIVE_RECORDS.discard(str(folder / "turn-02-b.json"))

    monkeypatch.setattr(GuardedDockerTurnRunner, "_recover_one", recover_then_the_live_turn_ends)

    runner.recover_pending(5.0)

    assert (evidence / "turn-02-b" / "output" / "container-result.json").exists()  # its sealed output is kept
    assert not (folder / "turn-02-b.json").exists() and not (folder / "turn-01-a.json").exists()  # nothing written back


def test_two_recovery_passes_never_work_on_one_record_at_once(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    record = {"version": 1, "run_id": "repair-test", "label": "repair-test", "held": [], "attempts": 0, "created": 0,
              "last_attempt": None, "next_attempt_after": 0, "history": [], "container": "p05-repair-test-a-01",
              "turn_folder": "turn-01-a", "state": "pending", "pid": 999_999}
    (folder / "turn-01-a.json").write_text(_json.dumps(record))
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))  # never confirmable
    runner, _, _ = build(tmp_path, credential)
    inner: list[int] = []
    original = GuardedDockerTurnRunner._recover_one

    def nested(self, path, data, deadline, budget):
        inner.append(len(self.recover_pending(0.3)))  # a second pass while the first one holds the record
        original(self, path, data, deadline, budget)

    monkeypatch.setattr(GuardedDockerTurnRunner, "_recover_one", nested)

    runner.recover_pending(0.5)

    assert len(inner) == 1  # the second pass did not take the claimed record (no nested attempt)
    assert _json.loads((folder / "turn-01-a.json").read_text())["attempts"] == 1



def _hold_lock_in_another_process(lock: Path) -> subprocess.Popen:
    """A separate process that takes the lock and keeps it until it is killed (a live owner elsewhere)."""
    import sys
    lock.parent.mkdir(parents=True, exist_ok=True)
    owner = subprocess.Popen([sys.executable, "-c", (
        "import fcntl, os, sys, time\n"
        "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "print('held', flush=True)\n"
        "time.sleep(60)\n"), str(lock)], stdout=subprocess.PIPE, text=True)
    assert owner.stdout.readline().strip() == "held"
    return owner


# --- Repair after round-28 review B1: ownership between processes is the record's lock, never a PID -----------------

def test_a_left_behind_record_whose_pid_now_belongs_to_another_live_process_is_recovered(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    turn = tmp_path / "evidence" / "turn-01-crash"
    (turn / "output").mkdir(parents=True)
    (turn / "output" / "secret.log").write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    crashed = {"version": 1, "run_id": "repair-test", "label": "repair-test", "container": "p05-repair-test-crash-01",
               "turn_folder": "turn-01-crash", "held": [], "state": "running", "attempts": 0, "pid": os.getppid(),
               "created": 0, "last_attempt": None, "next_attempt_after": 0, "history": []}  # that pid lives on, unrelated
    (folder / "turn-01-crash.json").write_text(_json.dumps(crashed))
    calls: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=True, record=calls))
    launched = install_process(monkeypatch, lambda output: None, returncode=3)
    runner, _, guarded = build(tmp_path, credential, recovery_budget_seconds=1.0)

    guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert any(args[0] == "kill" and args[1] == "p05-repair-test-crash-01" for args, _ in calls)
    assert _records(tmp_path) == [] and not (turn / "output").exists() and launched


def test_a_live_turn_of_another_process_with_the_same_pid_is_never_recovered(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    other = {"version": 1, "run_id": "repair-test", "label": "repair-test", "container": "p05-repair-test-other-01",
             "turn_folder": "turn-01-other", "held": [], "state": "running", "attempts": 0, "pid": os.getpid(),
             "created": 0, "last_attempt": None, "next_attempt_after": 0, "history": []}  # same pid, other namespace
    (folder / "turn-01-other.json").write_text(_json.dumps(other))
    owner = _hold_lock_in_another_process(folder / ".turn-01-other.json.lock")
    calls: list = []
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(record=calls))
    runner, _, guarded = build(tmp_path, credential)

    try:
        result = guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
        runner.retry_exhausted()
    finally:
        owner.kill()
        owner.wait()

    assert result.error_class == "CleanupPending" and calls == []  # no inspect, no kill of the live turn
    assert _json.loads((folder / "turn-01-other.json").read_text()) == other


def test_an_attempt_never_brings_back_a_record_that_vanished_during_it(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    record = {"version": 1, "run_id": "repair-test", "label": "repair-test", "container": "p05-repair-test-a-01",
              "turn_folder": "turn-01-a", "held": [], "state": "pending", "attempts": 0, "pid": 999_999,
              "created": 0, "last_attempt": None, "next_attempt_after": 0, "history": []}
    (folder / "turn-01-a.json").write_text(_json.dumps(record))
    runner, _, _ = build(tmp_path, credential)
    original = GuardedDockerTurnRunner._stop_owned

    def stop_while_someone_removes_the_record(self, plan, proc):
        (folder / "turn-01-a.json").unlink()  # e.g. a person removed it during the attempt
        return {**original(self, plan, proc), "container_absent": False}

    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(owned=False))
    monkeypatch.setattr(GuardedDockerTurnRunner, "_stop_owned", stop_while_someone_removes_the_record)

    runner.recover_pending(0.5)

    assert not (folder / "turn-01-a.json").exists()


# --- Repair after gate verdict 7/7 (disposition 8): a recovery attempt is recorded durably before any risky step -----

def _pending_record(folder: Path, **overrides) -> Path:
    data = {"version": 1, "run_id": "repair-test", "label": "repair-test", "container": "p05-repair-test-old-01",
            "turn_folder": "turn-01-old", "held": [], "state": "pending", "attempts": 0, "pid": 999_999, "created": 0,
            "last_attempt": None, "next_attempt_after": 0, "history": [], **overrides}
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "turn-01-old.json"
    path.write_text(_json.dumps(data))
    return path


def _orphans(folder: Path) -> list[str]:
    return [p.name for p in folder.glob(".turn-01-old.json.*") if not p.name.endswith(".lock")]


def test_a_recovery_attempt_that_cannot_be_recorded_takes_no_risky_step_and_leaves_no_orphan(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    path = _pending_record(folder)
    stops: list[str] = []
    runner, spend, guarded = build(tmp_path, credential, recovery_budget_seconds=0.1)
    monkeypatch.setattr(GuardedDockerTurnRunner, "_stop_owned",
                        lambda self, plan, proc: (stops.append(plan.name) or {"container_absent": False, "ownership_verified": False}))
    monkeypatch.setattr(module.os, "replace", lambda source, dest: (_ for _ in ()).throw(OSError("persistent record-write failure")))

    for _ in range(8):  # the gate's probe: on the old candidate, 8 unrecorded stops and 8 orphan files
        runner.recover_pending(0.1)
    launched = install_process(monkeypatch, lambda output: None, returncode=3)
    result = guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    assert stops == [] and _orphans(folder) == []
    record = _json.loads(path.read_text())
    assert record["attempts"] == 0 and record["state"] == "pending"  # the original identity is kept, unchanged
    assert result.error_class == "CleanupPending" and launched == []  # and it still blocks new work


def test_attempts_stay_finite_when_only_the_write_after_the_risky_step_fails(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    monkeypatch.setattr(module, "RECOVERY_BACKOFF_SECONDS", 0.0)
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    path = _pending_record(folder)
    stops: list[str] = []
    runner, _, _ = build(tmp_path, credential)
    monkeypatch.setattr(GuardedDockerTurnRunner, "_stop_owned",
                        lambda self, plan, proc: (stops.append(plan.name) or {"container_absent": False, "ownership_verified": False}))
    real_write = GuardedDockerTurnRunner._write_record

    def fail_after_the_step(path, data):
        if not data.get("attempt_in_progress"):  # the write that would close the attempt
            raise OSError("persistent failure after the risky step")
        return real_write(path, data)

    monkeypatch.setattr(GuardedDockerTurnRunner, "_write_record", staticmethod(fail_after_the_step))

    for _ in range(module.MAX_RECOVERY_ATTEMPTS + 4):
        runner.recover_pending(0.5)

    record = _json.loads(path.read_text())
    assert len(stops) == module.MAX_RECOVERY_ATTEMPTS and record["attempts"] == module.MAX_RECOVERY_ATTEMPTS
    assert _orphans(folder) == []


def test_a_crash_after_an_attempt_is_recorded_keeps_the_attempt_and_its_uncertainty(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    path = _pending_record(folder)
    runner, _, _ = build(tmp_path, credential)

    def crash(self, plan, proc):
        raise SystemExit("the host process died during the stop")

    monkeypatch.setattr(GuardedDockerTurnRunner, "_stop_owned", crash)
    with pytest.raises(SystemExit):
        runner.recover_pending(1.0)

    record = _json.loads(path.read_text())
    assert record["attempts"] == 1 and record["attempt_in_progress"]  # consumed, outcome unknown, visible
    assert record["next_attempt_after"] > 0
    monkeypatch.undo()
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False))
    import guarded_docker_runner as module
    monkeypatch.setattr(module, "RECOVERY_BACKOFF_SECONDS", 0.0)
    record["next_attempt_after"] = 0
    path.write_text(_json.dumps(record))

    GuardedDockerTurnRunner(image="unused", run_id="repair-test", evidence_dir=tmp_path / "evidence", policy=POLICY,
                            credential_file=credential, script_for=lambda turn: {}, timeout_seconds=60).recover_pending(1.0)

    assert not path.exists()  # a later pass confirms and clears it


def test_a_confirmed_recovery_whose_record_cannot_be_deleted_keeps_blocking_without_raising(tmp_path: Path, monkeypatch) -> None:
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    path = _pending_record(folder)
    monkeypatch.setattr(docker_turn_runner, "docker", docker_double(present=False))
    runner, _, _ = build(tmp_path, credential)
    real_unlink = Path.unlink

    def refuse(self, missing_ok=False):
        if self == path:
            raise OSError("cannot delete the record")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", refuse)
    runner.recover_pending(1.0)  # must not raise

    assert path.exists() and runner.pending_cleanup()  # still pending, still blocking
    monkeypatch.setattr(Path, "unlink", real_unlink)
    import guarded_docker_runner as module
    monkeypatch.setattr(module, "RECOVERY_BACKOFF_SECONDS", 0.0)
    data = _json.loads(path.read_text())
    data["next_attempt_after"] = 0
    path.write_text(_json.dumps(data))
    runner.recover_pending(1.0)
    assert not path.exists()


def test_a_failed_atomic_write_removes_only_its_own_temporary_file(tmp_path: Path, monkeypatch) -> None:
    import guarded_docker_runner as module
    folder = tmp_path / "pending-cleanup"
    folder.mkdir()
    (folder / ".turn-01-old.json.someone-elses").write_text("x")  # not this operation's file: must stay
    monkeypatch.setattr(module.os, "replace", lambda source, dest: (_ for _ in ()).throw(OSError("full disk")))

    with pytest.raises(OSError):
        GuardedDockerTurnRunner._write_record(folder / "turn-01-old.json", {"state": "pending"})

    assert sorted(p.name for p in folder.iterdir()) == [".turn-01-old.json.someone-elses"]



def test_repeated_failed_writes_in_a_folder_that_refuses_rename_and_removal_leave_at_most_one_temporary_file(
        tmp_path: Path, monkeypatch) -> None:
    """Like an append-only folder (macOS chflags uappnd): files can be created, but neither renamed nor removed."""
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    path = _pending_record(folder)
    stops: list[str] = []
    runner, _, guarded = build(tmp_path, credential, recovery_budget_seconds=0.1)
    monkeypatch.setattr(GuardedDockerTurnRunner, "_stop_owned",
                        lambda self, plan, proc: (stops.append(plan.name) or {"container_absent": False, "ownership_verified": False}))
    real_unlink = module.os.unlink

    def refuse_in_folder(target, *args, **kwargs):
        name = Path(target).name  # any temporary file of the record, whatever the writer names it
        if Path(target).parent == folder and name.startswith(f".{path.name}.") and not name.endswith(".lock"):
            raise PermissionError("removal refused")
        return real_unlink(target, *args, **kwargs)

    monkeypatch.setattr(module.os, "replace", lambda source, dest: (_ for _ in ()).throw(PermissionError("rename refused")))
    monkeypatch.setattr(module.os, "unlink", refuse_in_folder)

    for _ in range(50):
        runner.recover_pending(0.1)
    install_process(monkeypatch, lambda output: None, returncode=3)
    result = guarded.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))

    leftovers = [p.name for p in folder.iterdir() if not p.name.endswith(".lock") and p.name != path.name]
    assert len(leftovers) <= 1, leftovers  # one per record at most, never one per failure
    assert stops == [] and _json.loads(path.read_text())["attempts"] == 0
    assert result.error_class == "CleanupPending"



def test_repeated_new_requests_in_a_folder_that_refuses_rename_and_removal_leave_at_most_one_leftover(
        tmp_path: Path, monkeypatch) -> None:
    """Round-31 review A1: each NEW turn has a new record name; a failed registration must not leave one more file per
    request, and must not hold a never-sent reservation as UNKNOWN."""
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    real_unlink = module.os.unlink

    def refuse_temporaries(target, *args, **kwargs):
        name = Path(target).name
        if Path(target).parent == folder and name.startswith(".") and not name.endswith(".lock"):
            raise PermissionError("removal refused")
        return real_unlink(target, *args, **kwargs)

    monkeypatch.setattr(module.os, "replace", lambda source, dest: (_ for _ in ()).throw(PermissionError("rename refused")))
    monkeypatch.setattr(module.os, "unlink", refuse_temporaries)
    launched = install_process(monkeypatch, lambda output: None, returncode=3)
    runner, spend, guarded = build(tmp_path, credential)

    results = [guarded.run_turn(Turn(f"attempt-{index}", "prompt", "task", "m", "route", 4096)) for index in range(10)]

    leftovers = [p.name for p in folder.iterdir() if not p.name.endswith(".lock")]
    assert len(leftovers) <= 1, leftovers
    assert launched == [] and all(result.request_count == 0 for result in results)
    assert results[0].error_class == "CleanupStorageUnwritable"
    assert all(result.error_class == "CleanupPending" for result in results[1:])  # the leftover blocks the rest
    assert spend.committed_usd() == Decimal("0")  # nothing was sent, so nothing is held as unknown


def test_a_hard_link_at_the_temporary_name_is_never_written_through(tmp_path: Path) -> None:
    folder = tmp_path / "pending-cleanup"
    folder.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not a record")
    os.link(outside, folder / ".turn-01-old.json.tmp")

    with pytest.raises(PermissionError):
        GuardedDockerTurnRunner._write_record(folder / "turn-01-old.json", {"state": "pending"})

    assert outside.read_text() == "not a record" and not (folder / "turn-01-old.json").exists()


def test_repeated_new_requests_in_a_folder_that_refuses_every_new_file_leave_nothing_and_hold_nothing(
        tmp_path: Path, monkeypatch) -> None:
    """A pending folder that refuses to create any file: no lock, no record, no turn folder, per request."""
    import guarded_docker_runner as module
    credential = tmp_path / "credential"
    credential.write_text(OLD)
    folder = tmp_path / "evidence" / "pending-cleanup"
    folder.mkdir(parents=True)
    real_open = module.os.open

    def refuse_new_files(target, flags, *args, **kwargs):
        if Path(target).parent == folder and flags & os.O_CREAT:
            raise PermissionError("no new files here")
        return real_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", refuse_new_files)
    launched = install_process(monkeypatch, lambda output: None, returncode=3)
    runner, spend, guarded = build(tmp_path, credential)

    results = [guarded.run_turn(Turn(f"attempt-{index}", "prompt", "task", "m", "route", 4096)) for index in range(10)]

    assert launched == [] and all(result.request_count == 0 for result in results)
    assert results[0].error_class == "CleanupStorageUnwritable"
    assert all(result.error_class == "CleanupPending" for result in results[1:])
    assert list(folder.iterdir()) == [] and list((tmp_path / "evidence").glob("turn-*")) == []
    assert spend.committed_usd() == Decimal("0")
    monkeypatch.setattr(module.os, "open", real_open)  # the folder works again: a probe write clears the block
    assert guarded.run_turn(Turn("attempt-again", "prompt", "task", "m", "route", 4096)).error_class != "CleanupPending"
