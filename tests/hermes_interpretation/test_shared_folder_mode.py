"""One job channel folder must let the relay's group write the reply, so the runner creates it group-writable.

Pure check: the folder helper only. No Docker, no job and no relay.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from guarded_docker_runner import TURN_FOLDER_MODE, _make_shared_folder


def test_a_turn_folder_is_group_writable(tmp_path: Path) -> None:
    path = tmp_path / "turn-01-attempt"
    _make_shared_folder(path)
    assert stat.S_IMODE(path.stat().st_mode) == TURN_FOLDER_MODE == 0o770


def test_a_turn_folder_is_never_reused(tmp_path: Path) -> None:
    path = tmp_path / "turn-01-attempt"
    path.mkdir()
    with pytest.raises(FileExistsError):
        _make_shared_folder(path)
