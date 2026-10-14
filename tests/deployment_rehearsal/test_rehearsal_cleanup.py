"""Rehearsal cleanup under failure: every owned teardown is attempted, the events child always ends, a failed or
unverifiable cleanup is recorded as failed (never clean), and the summary is still written. Faults are injected at the
Docker/subprocess seams (`LocalStack.down`, `local_stack.sh`, `local_stack.inventory`) with real child processes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

import local_stack
import rehearsal_run

RUN = "l4ab12"
REAL_INVENTORY = local_stack.inventory  # the cleanup tests stub it; the inventory tests call the real one
CLEAN = {"containers": {}, "volumes": {}, "networks": {}, "images": {}}


class FakeStack:
    def __init__(self, names: local_stack.StackNames, failure: BaseException | None = None) -> None:
        self.names, self.failure, self.claimed, self.down_calls = names, failure, True, 0

    def down(self) -> None:
        self.down_calls += 1
        if self.failure is not None:
            raise self.failure


def rehearsal(tmp_path: Path, restored_failure: BaseException | None = None,
              events_cmd: list[str] | None = None) -> rehearsal_run.Rehearsal:
    item = object.__new__(rehearsal_run.Rehearsal)
    item.run_id, item.evidence, item.build_sha = RUN, tmp_path, "0" * 40
    item.rec = rehearsal_run.Recorder(tmp_path)
    item.args = argparse.Namespace(keep=False)
    item.before = CLEAN
    item.primary = FakeStack(local_stack.StackNames.primary(RUN))
    item.restored = FakeStack(local_stack.StackNames.restored(RUN), restored_failure)
    item.events_log = open(tmp_path / "docker-events.jsonl", "wb")
    item.events = subprocess.Popen(events_cmd or [sys.executable, "-c", "import time; time.sleep(60)"])
    return item


@pytest.fixture(autouse=True)
def no_real_docker(monkeypatch) -> None:
    monkeypatch.setattr(local_stack, "remove_run_images", lambda names: [])
    monkeypatch.setattr(local_stack, "inventory", lambda: CLEAN)
    monkeypatch.setattr(rehearsal_run, "EVENTS_SETTLE_SECONDS", 0.0, raising=False)


def cleanup_step(item: rehearsal_run.Rehearsal) -> dict:
    return [step for step in json.loads((item.evidence / "steps.json").read_text()) if step["step"].startswith("cleanup")][-1]


def test_a_clean_teardown_passes_and_ends_the_events_child(tmp_path: Path) -> None:
    item = rehearsal(tmp_path)
    assert item.cleanup() is True
    assert item.events.poll() is not None and item.events_log.closed
    assert item.primary.down_calls == 1 and item.restored.down_calls == 1


def test_a_failed_restored_teardown_still_tears_down_the_primary_and_fails_cleanup(tmp_path: Path) -> None:
    item = rehearsal(tmp_path, restored_failure=subprocess.TimeoutExpired(["docker", "compose", "down"], 180))
    assert item.cleanup() is False
    assert item.primary.down_calls == 1 and item.restored.down_calls == 1
    assert item.events.poll() is not None and item.events_log.closed
    step = cleanup_step(item)
    assert step["ok"] is False
    assert any(RUN + "r" in error and "TimeoutExpired" in error for error in step["detail"]["teardown_errors"])


def test_an_unavailable_inventory_is_never_reported_clean(tmp_path: Path, monkeypatch) -> None:
    def broken() -> dict:
        raise RuntimeError("docker image inspect failed: Cannot connect to the Docker daemon")
    monkeypatch.setattr(local_stack, "inventory", broken)
    item = rehearsal(tmp_path)
    assert item.cleanup() is False
    step = cleanup_step(item)
    assert step["ok"] is False and "Cannot connect" in step["detail"]["inventory_error"]
    assert item.events.poll() is not None and item.events_log.closed
    assert not (tmp_path / "resources-after.json").exists()


def test_an_events_child_that_ignores_sigterm_is_stopped_within_its_bound(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(rehearsal_run, "EVENTS_STOP_SECONDS", 0.5, raising=False)
    stubborn = [sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"]
    item = rehearsal(tmp_path, events_cmd=stubborn)
    assert item.cleanup() is True
    assert item.events.poll() is not None and item.events_log.closed


def test_the_summary_is_written_and_failed_when_the_run_and_its_cleanup_fail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(rehearsal_run.signal, "signal", lambda *_: None)  # keep this test process's own handlers
    item = rehearsal(tmp_path, restored_failure=subprocess.TimeoutExpired(["docker"], 180))
    def fail() -> bool:
        raise RuntimeError("preflight broke")
    item.preflight = fail
    assert item.run() is False
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["ok"] is False and any(name.startswith("cleanup") for name in summary["failed"])


def _completed(args: list[str], code: int, out: bytes = b"", err: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args, code, stdout=out, stderr=err)


def fake_docker(inspect_bulk_error: bytes, single_errors: dict[str, bytes]):
    image_a = {"Id": "sha256:a", "RepoTags": ["x:1"], "Config": {"Labels": {}}}

    def sh(args: list[str], *, check: bool = True, **_: object) -> subprocess.CompletedProcess:
        if args[:3] == ["docker", "image", "ls"]:
            return _completed(args, 0, b"sha256:a\nsha256:b\n")
        if args[:3] == ["docker", "image", "inspect"]:
            ids = args[3:]
            if len(ids) > 1:
                result = _completed(args, 1, json.dumps([image_a]).encode(), inspect_bulk_error)
            elif ids[0] in single_errors:
                result = _completed(args, 1, b"[]", single_errors[ids[0]])
            else:
                result = _completed(args, 0, json.dumps([image_a]).encode())
            if check and result.returncode:
                raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
            return result
        return _completed(args, 0, b"")  # ps / volume ls / network ls: nothing
    return sh


def test_an_image_that_disappears_during_inventory_is_recorded_not_fatal(monkeypatch) -> None:
    gone = b"Error response from daemon: No such image: sha256:b"
    monkeypatch.setattr(local_stack, "sh", fake_docker(gone, {"sha256:b": gone}))
    found = REAL_INVENTORY()
    assert list(found["images"]) == ["sha256:a"]
    assert found["images_disappeared"] == ["sha256:b"]


def test_any_other_inspect_failure_still_stops_the_inventory(monkeypatch) -> None:
    broken = b"Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
    monkeypatch.setattr(local_stack, "sh", fake_docker(broken, {"sha256:b": broken}))
    with pytest.raises(RuntimeError, match="Cannot connect"):
        REAL_INVENTORY()
