"""The gateway's CONNECT handling on a REAL Unix socket pair (controller dispositions l1-e1-r9prep.md, l1-peekfix1.md,
l1-peekproof1.md): the client side is a real kernel socket with CPython's real timeout modes; the provider side stays an
in-memory stand-in that answers only after it receives the client's bytes. No network, DNS or Docker. Runs only in a
granted runtime window (NOT part of the non-network set). Each test owns its sockets and the handler thread and tears
them down in `finally`, also on failure. Timings are host monotonic durations, recorded apart from the senders' sleeps;
the bounds only tell one shared head budget from a renewed per-read one."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

import egress_gateway
from egress_gateway import ESTABLISHED, Gateway, Receipts
from test_egress_gateway import OPENROUTER, FakeSocket, Network, answer, live_head

JOIN_SECONDS = 10.0


class StandIn(FakeSocket):
    """The provider's end: silent until the client's first bytes arrive through the tunnel, then one reply and EOF."""

    def __init__(self, reply: bytes = b"server-hello") -> None:
        super().__init__()
        self.reply = reply

    def sendall(self, data: bytes) -> None:
        first = self.sent == b""
        super().sendall(data)
        if first:
            self.inbound.put(self.reply)
            self.inbound.put(b"")


@contextmanager
def owned_pair(tmp_path: Path, network: Network, upstream: FakeSocket) -> Iterator[tuple[socket.socket, dict[str, Any],
                                                                                          threading.Thread]]:
    """A real socket pair; the gateway handles its far end on a thread, as `serve` does. Torn down in `finally`."""
    before = set(threading.enumerate())
    client, far = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    result: dict[str, Any] = {}
    gateway = Gateway(Receipts(tmp_path), allowed=OPENROUTER, resolve=network.resolve, connect=network.connect)
    worker = threading.Thread(target=lambda: result.update(gateway.handle(far)), name="gateway-handler", daemon=True)
    try:
        yield client, result, worker
    finally:
        for sock in (client, far):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        upstream.shutdown(socket.SHUT_RDWR)  # unblocks the stand-in's side of the copy
        if worker.ident is not None:
            worker.join(JOIN_SECONDS)
        until = time.monotonic() + JOIN_SECONDS  # the copy threads and the cancelled watchdog end with the handler
        while (left := [t for t in threading.enumerate() if t not in before and t.is_alive()]) and time.monotonic() < until:
            time.sleep(0.05)
        assert not left, f"owned threads left: {[t.name for t in left]}"


def read_answer(client: socket.socket, seconds: float) -> bytes:
    client.settimeout(seconds)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = client.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def record(tmp_path: Path, name: str, value: dict[str, Any]) -> None:
    (tmp_path / f"{name}.json").write_text(json.dumps(value, indent=1, default=str))


def test_a_healthy_connect_on_a_real_socket_gets_its_answer_without_waiting(tmp_path: Path) -> None:
    upstream = StandIn()
    network = Network([answer("104.18.2.115")], upstream)
    with owned_pair(tmp_path, network, upstream) as (client, result, worker):
        client.sendall(live_head())
        began = time.monotonic()
        worker.start()
        answer_bytes = read_answer(client, egress_gateway.HEAD_SECONDS + 2)
        waited = time.monotonic() - began
        client.sendall(b"client-hello")  # the relay's first byte, only after the answer
        reply = client.recv(4096)
        worker.join(JOIN_SECONDS)
        record(tmp_path, "healthy", {"waited_s": waited, "result": result})
    assert answer_bytes == ESTABLISHED
    assert waited < 1.0  # neither queued-byte look may wait for the (absent) next byte
    assert (reply, upstream.sent, result["outcome"]) == (b"server-hello", b"client-hello", "tunnel")


def test_bytes_queued_during_the_connect_on_a_real_socket_are_refused_by_the_second_look(tmp_path: Path) -> None:
    upstream = FakeSocket()
    client_side: list[socket.socket] = []

    class QueuesDuringConnect(Network):
        def connect(self, address: tuple[str, int], timeout: float) -> FakeSocket:
            client_side[0].sendall(b"\x16\x03\x01")  # in the far end's kernel buffer before sendall returns (AF_UNIX)
            return super().connect(address, timeout)

    network = QueuesDuringConnect([answer("104.18.2.115")], upstream)
    with owned_pair(tmp_path, network, upstream) as (client, result, worker):
        client_side.append(client)
        client.sendall(live_head())  # the head alone: the first look (after the head) sees nothing
        worker.start()
        answer_bytes = read_answer(client, egress_gateway.HEAD_SECONDS + 2)
        worker.join(JOIN_SECONDS)
    lines = [json.loads(x) for x in (tmp_path / "tunnels.jsonl").read_text().splitlines()]
    assert answer_bytes == b"HTTP/1.1 403 Forbidden\r\nX-Refusal: data_before_tunnel\r\n\r\n"
    assert [(r["outcome"], r["reason"]) for r in lines] == [("opening", None), ("refused", "data_before_tunnel")]
    assert network.connected == [("104.18.2.115", 443)] and upstream.sent == b"" and upstream.closed


def test_a_slow_head_on_a_real_socket_is_refused_at_one_shared_budget(tmp_path: Path) -> None:
    upstream = FakeSocket()
    network = Network([answer("104.18.2.115")], upstream)
    body = live_head(seconds=60)[:-4]  # the head without its final blank line: it never completes
    size = -(-len(body) // 4)
    pieces = [body[i:i + size] for i in range(0, len(body), size)]
    with owned_pair(tmp_path, network, upstream) as (client, result, worker):
        worker.start()
        began = time.monotonic()
        slept = 0.0
        for piece in pieces:  # 4 x 1.8 s = 7.2 s: a renewed 5 s per read would never refuse
            client.sendall(piece)
            time.sleep(1.8)
            slept += 1.8
            if not worker.is_alive():
                break
        worker.join(JOIN_SECONDS)
        refused_after = time.monotonic() - began
        record(tmp_path, "slow-head", {"refused_after_s": refused_after, "sender_slept_s": slept, "result": result})
    assert result["reason"] == "head_timeout" and network.resolved == [] and network.connected == []
    assert refused_after < 7.0  # one shared 5 s budget plus at most one sender sleep; not a real-time claim


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: Any, **__: Any) -> None:
        raise AssertionError("no name lookup in these tests")
    monkeypatch.setattr(egress_gateway.socket, "getaddrinfo", refuse)
