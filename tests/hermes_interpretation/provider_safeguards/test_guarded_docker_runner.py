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
