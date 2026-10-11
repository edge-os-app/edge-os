"""The host runner of the guarded container: the dummy credential must stay out of saved evidence on EVERY exit path.

The docker command line is the only stand-in: a stub process writes the credential into the output folder the way a
failing job could, then exits or times out. The runner and its redaction are the real ones.
"""

from __future__ import annotations

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
        self.returncode, self.argv = StubProcess.returncode, argv

    returncode = 3
    timeout = False

    def communicate(self, timeout=None):
        if StubProcess.timeout and timeout is not None and timeout > 25:
            raise subprocess.TimeoutExpired("docker", timeout)
        return f"stdout with {SENTINEL}", None

    def kill(self) -> None:
        pass


@pytest.mark.parametrize("timeout, returncode, status", [(False, 3, "UNKNOWN"), (True, 0, "TIMED_OUT")])
def test_the_credential_is_removed_from_evidence_when_the_job_fails_or_times_out(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: bool, returncode: int, status: str) -> None:
    StubProcess.timeout, StubProcess.returncode = timeout, returncode
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
