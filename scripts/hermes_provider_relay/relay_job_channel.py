"""The job side of the relay channel: a `ProviderTransport` that hands one request to the relay through files.

The job has no network and no key. `ChannelTransport.send` writes one request file into the job's own output folder
(`relay-channel/request.json`, by a temporary file and a rename) naming the attempt, route and release, with the
admitted body; then it waits for the relay's `reply.json`. The relay decides everything else. It sends no URL, header or
credential: the relay would refuse them. Standard library only; the job reads at most a bounded reply.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from provider_transport import HostRequest, TransportLost, TransportReply, TransportRoute

__all__ = ["ChannelTransport", "RelayRefused", "RelayReplyRefused"]

POLL_SECONDS = 0.02
# The relay runs with the shared group and writes `reply.json` into this folder. The job's default umask would make it
# `0755`, which denies that write, so the folder is created group-writable.
CHANNEL_FOLDER_MODE = 0o770


class RelayRefused(RuntimeError):
    """The relay refused the request before any provider request started. Nothing was sent."""


class RelayReplyRefused(RuntimeError):
    """The relay sent the request and refused the reply (too large, a redirect, not JSON). The provider may have worked."""


@dataclass
class ChannelTransport:
    route: TransportRoute
    release_id: str
    folder: Path = Path("/job/output/relay-channel")

    def __post_init__(self) -> None:
        self._sent = False

    def send(self, request: HostRequest) -> TransportReply:
        if self._sent or request.route_id != self.route.route_id:
            raise RuntimeError("one send per attempt, on this route only")
        self._sent = True
        self.folder.mkdir(exist_ok=True)
        os.chmod(self.folder, CHANNEL_FOLDER_MODE)  # the relay's shared group writes reply.json here
        message = {"attempt_id": request.attempt_id, "route_id": request.route_id, "release_id": self.release_id,
                   "body_b64": base64.b64encode(request.body).decode()}
        temporary = self.folder / ".request.json.tmp"
        temporary.write_text(json.dumps(message), encoding="utf-8")
        os.replace(temporary, self.folder / "request.json")
        reply = self._await_reply()
        outcome = reply.get("outcome")
        if outcome == "refused" and reply.get("before_send") is True:
            raise RelayRefused(str(reply.get("refusal")))
        if outcome == "refused":
            raise RelayReplyRefused(str(reply.get("refusal")))
        if outcome != "reply" or reply.get("attempt_id") != request.attempt_id:
            raise TransportLost("the relay reported no usable reply")
        try:
            body = base64.b64decode(reply["body_b64"], validate=True)
            status = reply["status"]
        except (KeyError, TypeError, ValueError):
            raise TransportLost("the relay reply could not be read") from None
        return TransportReply(status, body)

    def _await_reply(self) -> dict:
        limit = 4 * (self.route.max_reply_bytes // 3 + 2) + 4096
        path = self.folder / "reply.json"
        while True:  # the job deadline (the host stops this container) bounds the wait; the relay's grant ends sooner
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                time.sleep(POLL_SECONDS)
                continue
            with os.fdopen(fd, "rb") as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise TransportLost("the relay reply was too large")
            try:
                value = json.loads(data)
            except ValueError:
                raise TransportLost("the relay reply could not be read") from None
            if not isinstance(value, dict):
                raise TransportLost("the relay reply could not be read")
            return value
