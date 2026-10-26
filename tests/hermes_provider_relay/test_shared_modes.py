"""The host-shared relay files: the application and the relay use one group, so each writer's files must be
group-readable and the state folder must not be group-writable.

Pure checks: no Docker, no real user, no host change.
"""

from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path

from provider_transport import HostRequest, TransportRoute
from relay_job_channel import CHANNEL_FOLDER_MODE, ChannelTransport
from relay_service import _write_new
from relay_turn_runner import RelayTurnRunner

STATE_FILE_MODE = 0o640


def test_a_state_or_reply_file_is_group_readable(tmp_path: Path) -> None:
    folder = tmp_path / "state"
    folder.mkdir(mode=0o2750)
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert _write_new(fd, "heartbeat.json", {"at": 1}) is True
    finally:
        os.close(fd)
    assert stat.S_IMODE((folder / "heartbeat.json").stat().st_mode) == STATE_FILE_MODE


def test_a_grant_or_revocation_file_is_group_readable(tmp_path: Path) -> None:
    path = tmp_path / "attempt-1.json"
    assert RelayTurnRunner._write_once(path, {"attempt_id": "attempt-1"}) is True
    assert stat.S_IMODE(path.stat().st_mode) == STATE_FILE_MODE


def test_the_job_reply_folder_is_group_writable_for_the_relay(tmp_path: Path) -> None:
    folder = tmp_path / "relay-channel"
    folder.mkdir()  # the job's default umask would leave it 0755
    route = TransportRoute("authored-local-1", "AUTHORED", "https://authored-transport.invalid/v1/chat/completions",
                           65_536)
    (folder / "reply.json").write_text(json.dumps({"outcome": "reply", "attempt_id": "attempt-1", "status": 200,
                                                   "body_b64": base64.b64encode(b"{}").decode()}))
    ChannelTransport(route=route, release_id="local-relay-1", folder=folder).send(
        HostRequest("attempt-1", route.route_id, "https://authored-transport.invalid/v1/chat/completions", (), b"{}"))
    assert CHANNEL_FOLDER_MODE == 0o770
    assert stat.S_IMODE(folder.stat().st_mode) == CHANNEL_FOLDER_MODE
