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
        origin = os.getcwd()
        try:
            os.chdir(output)
            for _ in range(700):  # about 1,400 characters of path: more than the host path limit
                os.mkdir("a")
                os.chdir("a")
            Path("deep.log").write_text(OLD)
        finally:
            os.chdir(origin)

    install_process(monkeypatch, behaviour)
    runner, _, _ = build(tmp_path, credential)
    try:
        runner.run_turn(Turn("attempt-1", "prompt", "task", "m", "route", 4096))
    except EvidenceNotSealed:
        pass

    assert not list((tmp_path / "evidence").glob("turn-*/output")), "evidence that cannot be sealed must not be kept"


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
