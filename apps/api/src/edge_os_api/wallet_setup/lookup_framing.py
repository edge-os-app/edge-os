"""Bounded frames for the private wallet-lookup socket.

One frame is a 4-byte big-endian length and a UTF-8 JSON object of at most `MAX_FRAME` bytes. An
oversized, short, non-JSON or non-object frame raises `FrameError`, whose message never repeats the
received bytes.

A caller may pass one absolute monotonic `deadline` to `read_frame`. Header and body then share that
single budget: before every receive the socket timeout is re-armed to the remaining time, and a
just-crossed deadline raises `FrameError` instead of accepting a paced reply. Without a deadline the
reader keeps its previous per-operation behaviour.
"""

from __future__ import annotations

import json
import socket
import struct
import time
from collections.abc import Callable
from typing import Any

MAX_FRAME = 4096
_HEADER = struct.Struct(">I")


class FrameError(ValueError):
    """A frame could not be read or written within the fixed bounds."""


def encode_frame(message: dict[str, Any]) -> bytes:
    body = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(body) > MAX_FRAME:
        raise FrameError("frame too large")
    return _HEADER.pack(len(body)) + body


def decode_body(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise FrameError("frame is not JSON") from None
    if not isinstance(value, dict):
        raise FrameError("frame is not an object")
    return value


def _read_exact(sock: socket.socket, size: int, deadline: float | None, clock: Callable[[], float]) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        if deadline is not None:
            budget = deadline - clock()
            if budget <= 0:
                raise FrameError("frame deadline exceeded")
            sock.settimeout(budget)
        chunk = sock.recv(remaining)
        if not chunk:
            raise FrameError("connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(sock: socket.socket, deadline: float | None = None,
               clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    (size,) = _HEADER.unpack(_read_exact(sock, _HEADER.size, deadline, clock))
    if size == 0 or size > MAX_FRAME:
        raise FrameError("frame size out of bounds")
    return decode_body(_read_exact(sock, size, deadline, clock))
