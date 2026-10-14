"""The gateway's CONNECT handling on a REAL Unix socket pair (controller dispositions l1-e1-r9prep.md, l1-peekfix1.md):
the client side is a real kernel socket with CPython's real timeout modes; the provider side stays an in-memory fake.
No network, DNS or Docker. Runs only in a granted runtime window (it is NOT part of the non-network set); timings are
host monotonic durations, recorded and bounded only to tell one shared head budget from a renewed per-read one."""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import egress_gateway
from egress_gateway import ESTABLISHED, Gateway, Receipts
from test_egress_gateway import FakeSocket, Network, answer, live_head


def serve_one(tmp_path: Path, network: Network) -> tuple[socket.socket, dict[str, Any], threading.Thread]:
    """A real socket pair; the gateway handles its far end on a thread, as `serve` does."""
    client, far = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    result: dict[str, Any] = {}
    gateway = Gateway(Receipts(tmp_path), resolve=network.resolve, connect=network.connect)
    worker = threading.Thread(target=lambda: result.update(gateway.handle(far)), daemon=True)
    return client, result, worker


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
    (tmp_path / f"{name}.json").write_text(json.dumps(value, indent=1))


def test_a_healthy_connect_on_a_real_socket_gets_its_answer_without_waiting(tmp_path: Path) -> None:
    upstream = FakeSocket([b"server-hello"], end=True)
    client, result, worker = serve_one(tmp_path, Network([answer("104.18.2.115")], upstream))
    began = time.monotonic()
    client.sendall(live_head())
    worker.start()
    answer_bytes = read_answer(client, egress_gateway.HEAD_SECONDS + 2)
    waited = time.monotonic() - began
    client.sendall(b"client-hello")  # the relay's first byte, only after the answer
    client.shutdown(socket.SHUT_WR)
    worker.join(10)
    record(tmp_path, "healthy", {"waited_s": waited, "result": result})
    assert answer_bytes.startswith(ESTABLISHED)
    assert waited < 1.0  # neither queued-byte look may wait for the (absent) next byte
    assert result["outcome"] == "tunnel" and upstream.sent == b"client-hello"


def test_bytes_queued_before_the_answer_on_a_real_socket_are_refused_and_nothing_connects(tmp_path: Path) -> None:
    network = Network([answer("104.18.2.115")], FakeSocket(end=True))
    client, result, worker = serve_one(tmp_path, network)
    client.sendall(live_head())
    client.sendall(b"\x16\x03\x01")  # queued in the kernel before the gateway reads anything
    worker.start()
    answer_bytes = read_answer(client, egress_gateway.HEAD_SECONDS + 2)
    worker.join(10)
    assert answer_bytes == b"HTTP/1.1 403 Forbidden\r\nX-Refusal: data_before_tunnel\r\n\r\n"
    assert result["reason"] == "data_before_tunnel" and network.resolved == [] and network.connected == []


def test_a_slow_head_on_a_real_socket_is_refused_at_one_shared_budget(tmp_path: Path) -> None:
    network = Network([answer("104.18.2.115")], FakeSocket(end=True))
    client, result, worker = serve_one(tmp_path, network)
    body = live_head(seconds=60)[:-4]  # the head without its final blank line: it never completes
    size = -(-len(body) // 4)
    pieces = [body[i:i + size] for i in range(0, len(body), size)]
    worker.start()
    began = time.monotonic()
    for piece in pieces:  # 4 x 1.8 s = 7.2 s: a renewed 5 s per read would never refuse
        client.sendall(piece)
        time.sleep(1.8)
        if not worker.is_alive():
            break
    worker.join(10)
    refused_after = time.monotonic() - began
    record(tmp_path, "slow-head", {"refused_after_s": refused_after, "result": result})
    assert result["reason"] == "head_timeout" and network.resolved == [] and network.connected == []
    assert refused_after < 7.0  # one shared budget (5 s) plus the last piece's sleep; not a real-time claim


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: Any, **__: Any) -> None:
        raise AssertionError("no name lookup in these tests")
    monkeypatch.setattr(egress_gateway.socket, "getaddrinfo", refuse)
