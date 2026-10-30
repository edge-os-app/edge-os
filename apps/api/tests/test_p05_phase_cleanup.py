"""The P05 verification phase must register every process it starts, even when a step fails.

A failed phase once started a replacement API and lost its handle, so the run's own cleanup never stopped it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import harness
import p05_phase


class Recorder:
    def __init__(self) -> None:
        self.steps: list[tuple[str, bool]] = []

    def step(self, name: str, ok: bool, detail: object = None) -> bool:
        self.steps.append((name, ok))
        return ok

    def write(self, name: str, value: object) -> None:
        pass


class FakeProcess:
    def __init__(self, name: str) -> None:
        self.name, self.stopped = name, False

    def stop(self) -> None:
        self.stopped = True


def test_a_failed_phase_still_hands_its_replacement_api_to_the_caller(tmp_path: Path, monkeypatch) -> None:
    started: list[FakeProcess] = []

    def build_fails(self: Any) -> str:
        raise RuntimeError("docker build failed")

    def start_api(env: Any, port: int, log_dir: Path, name: str = "api",
                  factory: str = "edge_os_api.main:create_app", app_dir: Path | None = None) -> FakeProcess:
        started.append(FakeProcess(name))
        return started[-1]

    monkeypatch.setattr(p05_phase.PinnedHermesImage, "build", build_fails)
    monkeypatch.setattr(harness, "start_api", start_api)
    monkeypatch.setattr(harness, "wait_http", lambda *_a, **_k: None)
    removals: list[bool] = []
    monkeypatch.setattr(p05_phase.PinnedHermesImage, "remove",
                        lambda self: removals.append(True) or {"image_removed": True, "labeled_containers_left": []})
    current, processes = FakeProcess("api"), []

    try:
        p05_phase.run_p05_phase(Recorder(), None, {}, 1, "http://127.0.0.1:1", tmp_path, "p05test", {}, "a", "b",
                                lambda *_a, **_k: 0, current, processes)
    except RuntimeError:
        pass

    assert [p.name for p in started] == ["api-after-p05"]
    assert started[0] in processes, "the caller's own cleanup must see the process that the phase started"
    assert current.stopped
    assert removals == [True], "a build that failed may still have left a tagged image, so removal must run"


def test_a_failed_wait_for_the_replacement_api_still_registers_it(tmp_path: Path, monkeypatch) -> None:
    started: list[FakeProcess] = []
    monkeypatch.setattr(p05_phase.PinnedHermesImage, "build", lambda self: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(harness, "start_api", lambda *a, **k: started.append(FakeProcess("api-after-p05")) or started[-1])
    monkeypatch.setattr(harness, "wait_http", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("not ready")))
    processes: list[Any] = []

    try:
        p05_phase.run_p05_phase(Recorder(), None, {}, 1, "http://127.0.0.1:1", tmp_path, "p05test", {}, "a", "b",
                                lambda *_a, **_k: 0, FakeProcess("api"), processes)
    except RuntimeError:
        pass

    assert started and started[0] in processes
