"""One job channel folder must let the relay's group write the reply, so the runner creates it group-writable.

Pure check: the folder helper only. No Docker, no job and no relay.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

import guarded_docker_runner
from edge_os_api.research.hermes_interpreter import HermesTurn
from guarded_docker_runner import GuardedDockerTurnRunner, TURN_FOLDER_MODE, _make_shared_folder
from provider_guard import GuardPolicy

POLICY = GuardPolicy(model="m", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500)
TURN = HermesTurn("attempt-1", "prompt", "task", "m", "route", 4096)


def test_a_turn_folder_is_group_writable(tmp_path: Path) -> None:
    path = tmp_path / "turn-01-attempt"
    _make_shared_folder(path)
    assert stat.S_IMODE(path.stat().st_mode) == TURN_FOLDER_MODE == 0o770


def test_a_turn_folder_is_never_reused(tmp_path: Path) -> None:
    path = tmp_path / "turn-01-attempt"
    path.mkdir()
    with pytest.raises(FileExistsError):
        _make_shared_folder(path)


def test_a_turn_folder_that_cannot_be_made_shared_ends_as_storage_unwritable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = tmp_path / "evidence"
    runner = GuardedDockerTurnRunner(image="unused", run_id="modes", evidence_dir=evidence, policy=POLICY,
                                     script_for=lambda turn: {}, timeout_seconds=60)

    def refuse(path: Path) -> None:
        path.mkdir()
        raise OSError("synthetic chmod failure")

    monkeypatch.setattr(guarded_docker_runner, "_make_shared_folder", refuse)
    result = runner.run_turn(TURN)
    assert (result.status, result.error_class) == ("PROVIDER_FAILED", "CleanupStorageUnwritable")
    assert not (evidence / "turn-01-attempt-1").exists()
