"""The keyless egress gateway: the relay's only way out. Standard library only. See CONTRACT.md A6.

It holds no key and no CA. It listens only on a Unix socket in a private folder shared with the relay. For each
connection it reads ONE `CONNECT openrouter.ai:443` head that names the attempt and the grant expiry, resolves the name
itself, refuses the whole request if any answer is not globally routable, connects once to the first answer and then
copies bytes unchanged both ways: TLS stays end to end between the relay and the provider. The tunnel closes at the
expiry (at most `MAX_TUNNEL_SECONDS`), at `MAX_TUNNEL_BYTES` in either direction, or when either side closes.

Every connection leaves one fsynced line in `receipts/tunnels.jsonl` (refusals before the refusal is answered). An
attempt with any receipt is never tunnelled again. No header value is logged except the attempt id and the expiry.

Usage: python egress_gateway.py <config.json>. Config: `socket`, `receipts`; optional `test_resolution` (an address
used instead of DNS, for AUTHORED tests only; an ACTUAL supervisor refuses it).
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import socket
import stat
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["ConnectRequest", "Gateway", "Receipts", "address_refusal", "choose_address", "parse_connect", "serve"]

ALLOWED_HOST, ALLOWED_PORT = "openrouter.ai", 443
MAX_HEAD = 1024
HEAD_SECONDS = 5.0
CONNECT_SECONDS = 10.0
MAX_TUNNEL_SECONDS = 120.0
MAX_TUNNEL_BYTES = 4 * 1024 * 1024
MAX_TUNNELS = 16
CHUNK = 64 * 1024
ATTEMPT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
HEADERS = frozenset({"host", "x-relay-attempt", "x-relay-expires"})
DOCKER_RANGES = tuple(ipaddress.ip_network(net) for net in (  # also refused by the global check; named for the record
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fd00::/8"))
ESTABLISHED = b"HTTP/1.1 200 Connection Established\r\n\r\n"


@dataclass(frozen=True)
class ConnectRequest:
    attempt_id: str
    expires_at: float


def parse_connect(head: bytes, *, now: float) -> ConnectRequest | str:
    """The one admitted CONNECT in `head` (which ends at the blank line), or the refusal reason."""
    try:
        text = head.decode("ascii")
    except UnicodeDecodeError:
        return "head_not_ascii"
    if not text.endswith("\r\n\r\n"):
        return "head_incomplete"
    request, *lines = text[:-4].split("\r\n")
    parts = request.split(" ")
    if len(parts) != 3:
        return "request_line_invalid"
    method, target, version = parts
    if method != "CONNECT":
        return "method_not_connect"
    if version != "HTTP/1.1":
        return "version_invalid"
    host, separator, port = target.rpartition(":")
    if not separator or not host or not port.isdigit():
        return "target_invalid"
    try:
        ipaddress.ip_address(host.strip("[]"))
        return "target_ip_literal"
    except ValueError:
        pass
    if host != ALLOWED_HOST:
        return "target_name_not_allowed"
    if int(port) != ALLOWED_PORT or port != str(ALLOWED_PORT):
        return "target_port_not_allowed"
    headers: dict[str, str] = {}
    for line in lines:
        name, separator, value = line.partition(":")
        name = name.strip().lower()
        if not separator or name in headers or name not in HEADERS:
            return "header_invalid"
        headers[name] = value.strip()
    if set(headers) != HEADERS or headers["host"] != target:
        return "header_invalid"
    if not ATTEMPT.fullmatch(headers["x-relay-attempt"]):
        return "attempt_invalid"
    try:
        expires = float(headers["x-relay-expires"])
    except ValueError:
        return "expiry_invalid"
    if not math.isfinite(expires) or expires <= now or expires > now + MAX_TUNNEL_SECONDS:
        return "expiry_invalid"
    return ConnectRequest(headers["x-relay-attempt"], expires)


def address_refusal(address: str) -> str | None:
    """None only for a globally routable unicast address; a scope suffix (fe80::1%eth0) is refused as non-global."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "dns_answer_invalid"
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None or not ip.is_global or ip.is_multicast or any(ip in net for net in DOCKER_RANGES
                                                                          if net.version == ip.version):
        return "dns_answer_not_global"
    return None


def choose_address(answers: list[tuple[Any, ...]]) -> str:
    """The first answer's address, if every answer is global; otherwise a ValueError naming the refusal."""
    addresses = [str(answer[4][0]) for answer in answers]
    if not addresses:
        raise ValueError("dns_no_answer")
    for address in addresses:
        refusal = address_refusal(address)
        if refusal is not None:
            raise ValueError(refusal)
    return addresses[0]


class Receipts:
    """`tunnels.jsonl`: one fsynced line per connection; an attempt seen once is never admitted again."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / "tunnels.jsonl"
        self.lock = threading.Lock()
        self.seen: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    attempt = json.loads(line).get("attempt_id")
                except ValueError:
                    continue  # a torn last line; the attempts before it still count
                if isinstance(attempt, str):
                    self.seen.add(attempt)

    def admit(self, attempt_id: str) -> bool:
        with self.lock:
            if attempt_id in self.seen:
                return False
            self.seen.add(attempt_id)
            return True

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps({"at": time.time(), **record}, sort_keys=True) + "\n"
        with self.lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, line.encode())
                os.fsync(fd)
            finally:
                os.close(fd)


def _pump(client: Any, upstream: Any, until: float, clock: Callable[[], float]) -> tuple[int, int, str]:
    """Copy both ways until `until`, a byte limit or a close. Returns bytes up, bytes down and why it closed."""
    counts = {"up": 0, "down": 0}
    reason: list[str] = []
    done = threading.Event()

    def cut(why: str) -> None:
        if not reason:
            reason.append(why)
        for each in (client, upstream):
            try:
                each.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        done.set()

    def copy(source: Any, target: Any, direction: str) -> None:
        try:
            while True:
                data = source.recv(CHUNK)
                if not data:
                    cut(f"{'client' if direction == 'up' else 'provider'}_closed")
                    return
                counts[direction] += len(data)
                if counts[direction] > MAX_TUNNEL_BYTES:
                    cut("byte_limit")
                    return
                target.sendall(data)
        except OSError:
            cut("error")  # after a cut the first reason stands

    watchdog = threading.Timer(max(0.0, until - clock()), cut, args=("expiry",))
    watchdog.daemon = True
    watchdog.start()
    threads = [threading.Thread(target=copy, args=(client, upstream, "up"), daemon=True),
               threading.Thread(target=copy, args=(upstream, client, "down"), daemon=True)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    watchdog.cancel()
    return counts["up"], counts["down"], reason[0] if reason else "closed"


class Gateway:
    """Admits and serves one connection at a time per call to `handle`. Resolver, connector and clock are injectable."""

    def __init__(self, receipts: Receipts, *, test_resolution: str | None = None,
                 resolve: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
                 connect: Callable[..., Any] = socket.create_connection, clock: Callable[[], float] = time.time) -> None:
        if test_resolution is not None:
            ip = ipaddress.ip_address(test_resolution)  # a bridge address of an AUTHORED stand-in, never loopback
            if not ip.is_private or ip.is_loopback or ip.is_unspecified:
                raise ValueError("test_resolution must be a private, non-loopback address")
        self.receipts, self.test_resolution = receipts, test_resolution
        self.resolve, self.connect, self.clock = resolve, connect, clock

    def _refuse(self, client: Any, reason: str, attempt_id: str | None) -> dict[str, Any]:
        record = {"attempt_id": attempt_id, "outcome": "refused", "reason": reason}
        self.receipts.write(record)  # the receipt exists before the relay can see the refusal
        try:
            client.sendall(f"HTTP/1.1 403 Forbidden\r\nX-Refusal: {reason}\r\n\r\n".encode())
        except OSError:
            pass
        return record

    @staticmethod
    def _read_head(client: Any) -> bytes | str:
        data = b""
        while b"\r\n\r\n" not in data:
            if len(data) > MAX_HEAD:
                return "head_too_large"
            try:
                chunk = client.recv(MAX_HEAD + 1 - len(data))
            except OSError:
                return "head_incomplete"
            if not chunk:
                return "head_incomplete"
            data += chunk
        end = data.index(b"\r\n\r\n") + 4
        if end > MAX_HEAD:
            return "head_too_large"
        if len(data) > end:
            return "data_before_tunnel"  # e.g. a second CONNECT or TLS bytes sent before the answer
        return data

    def handle(self, client: Any) -> dict[str, Any]:
        try:
            client.settimeout(HEAD_SECONDS)
            head = self._read_head(client)
            if isinstance(head, str):
                return self._refuse(client, head, None)
            request = parse_connect(head, now=self.clock())
            if isinstance(request, str):
                return self._refuse(client, request, None)
            if not self.receipts.admit(request.attempt_id):
                return self._refuse(client, "attempt_repeated", request.attempt_id)
            if self.test_resolution is not None:
                address = self.test_resolution
            else:
                try:
                    address = choose_address(self.resolve(ALLOWED_HOST, ALLOWED_PORT, type=socket.SOCK_STREAM))
                except ValueError as refusal:
                    return self._refuse(client, str(refusal), request.attempt_id)
                except OSError:
                    return self._refuse(client, "dns_failure", request.attempt_id)
            until = min(request.expires_at, self.clock() + MAX_TUNNEL_SECONDS)
            try:
                upstream = self.connect((address, ALLOWED_PORT), timeout=max(0.001, min(CONNECT_SECONDS,
                                                                                          until - self.clock())))
            except OSError:
                return self._refuse(client, "connect_failed", request.attempt_id)
            opened = self.clock()
            try:
                client.settimeout(None)
                upstream.settimeout(None)
                client.sendall(ESTABLISHED)
                up, down, why = _pump(client, upstream, until, self.clock)
            finally:
                upstream.close()
            record = {"attempt_id": request.attempt_id, "outcome": "tunnel", "reason": None, "address": address,
                      "test_resolution": self.test_resolution is not None, "opened_at": opened,
                      "closed_at": self.clock(), "bytes_up": up, "bytes_down": down, "close_reason": why}
            self.receipts.write(record)
            return record
        finally:
            client.close()


def serve(socket_path: Path, gateway: Gateway) -> None:  # pragma: no cover - exercised by the Docker tests
    if socket_path.exists() or socket_path.is_symlink():
        if not stat.S_ISSOCK(os.lstat(socket_path).st_mode):
            raise SystemExit("the socket path holds something else")
        socket_path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    os.umask(0o177)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    listener.listen(MAX_TUNNELS)
    slots = threading.BoundedSemaphore(MAX_TUNNELS)
    while True:
        client, _ = listener.accept()
        if not slots.acquire(blocking=False):
            gateway._refuse(client, "gateway_busy", None)
            client.close()
            continue

        def run(each: Any = client) -> None:
            try:
                gateway.handle(each)
            finally:
                slots.release()
        threading.Thread(target=run, daemon=True).start()


def main() -> int:  # pragma: no cover - exercised by the Docker tests
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    receipts = Receipts(Path(config["receipts"]))
    gateway = Gateway(receipts, test_resolution=config.get("test_resolution"))
    Path(config["receipts"], "ready").write_text(json.dumps({"pid": os.getpid(), "at": time.time(),
                                                             "test_resolution": gateway.test_resolution is not None}))
    serve(Path(config["socket"]), gateway)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
