"""The keyless egress gateway's rules, on in-memory sockets: no network, no real socket, no DNS (CONTRACT A6)."""

from __future__ import annotations

import json
import queue
import socket
import stat
import time
from pathlib import Path
from typing import Any

import pytest

import egress_gateway
from egress_gateway import (
    ESTABLISHED, ConnectRequest, Gateway, Receipts, _early_bytes, address_refusal, choose_address, parse_connect,
)

NOW = 1_000_000.0


def head(target: str = "openrouter.ai:443", *, method: str = "CONNECT", version: str = "HTTP/1.1",
         headers: list[str] | None = None) -> bytes:
    lines = headers if headers is not None else [f"Host: {target}", "X-Relay-Attempt: att-1", f"X-Relay-Expires: {NOW + 60}"]
    return ("\r\n".join([f"{method} {target} {version}", *lines]) + "\r\n\r\n").encode()


def test_the_one_admitted_connect() -> None:
    assert parse_connect(head(), now=NOW) == ConnectRequest("att-1", NOW + 60)


@pytest.mark.parametrize("raw, reason", [
    (head(method="GET"), "method_not_connect"),
    (head(method="POST"), "method_not_connect"),
    (head(version="HTTP/1.0"), "version_invalid"),
    (head("104.18.2.115:443"), "target_ip_literal"),
    (head("[2606:4700::6812:272]:443"), "target_ip_literal"),
    (head("openrouter.ai.example:443"), "target_name_not_allowed"),
    (head("api.openrouter.ai:443"), "target_name_not_allowed"),
    (head("OPENROUTER.AI:443"), "target_name_not_allowed"),
    (head("openrouter.ai:80"), "target_port_not_allowed"),
    (head("openrouter.ai:0443"), "target_port_not_allowed"),
    (head("openrouter.ai"), "target_invalid"),
    (head(headers=["Host: openrouter.ai:443", f"X-Relay-Expires: {NOW + 60}"]), "header_invalid"),
    (head(headers=["Host: openrouter.ai:443", "X-Relay-Attempt: a", "X-Relay-Attempt: b",
                   f"X-Relay-Expires: {NOW + 60}"]), "header_invalid"),
    (head(headers=["Host: openrouter.ai:443", "X-Relay-Attempt: a", f"X-Relay-Expires: {NOW + 60}",
                   "Proxy-Authorization: Basic eA=="]), "header_invalid"),
    (head(headers=["Host: other:443", "X-Relay-Attempt: a", f"X-Relay-Expires: {NOW + 60}"]), "header_invalid"),
    (head(headers=["Host: openrouter.ai:443", "X-Relay-Attempt: ../a", f"X-Relay-Expires: {NOW + 60}"]), "attempt_invalid"),
    (head(headers=["Host: openrouter.ai:443", "X-Relay-Attempt: a", f"X-Relay-Expires: {NOW}"]), "expiry_invalid"),
    (head(headers=["Host: openrouter.ai:443", "X-Relay-Attempt: a", f"X-Relay-Expires: {NOW + 121}"]), "expiry_invalid"),
    (head(headers=["Host: openrouter.ai:443", "X-Relay-Attempt: a", "X-Relay-Expires: nan"]), "expiry_invalid"),
    (head(headers=["Host: openrouter.ai:443", "X-Relay-Attempt: a", "X-Relay-Expires: soon"]), "expiry_invalid"),
    (b"CONNECT openrouter.ai:443 HTTP/1.1\r\n", "head_incomplete"),
    ("CONNECT openrouter.ai:443 HTTP/1.1\r\nHost: é\r\n\r\n".encode(), "head_not_ascii"),
])
def test_every_other_request_is_refused(raw: bytes, reason: str) -> None:
    assert parse_connect(raw, now=NOW) == reason


@pytest.mark.parametrize("address", ["104.18.2.115", "8.8.8.8", "2606:4700::6812:272"])
def test_a_global_answer_is_allowed(address: str) -> None:
    assert address_refusal(address) is None


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "172.17.0.1", "172.18.0.2", "192.168.65.254",
                                     "169.254.1.1", "100.64.0.1", "224.0.0.1", "0.0.0.0", "240.0.0.1", "::1", "::",
                                     "fe80::1", "fd00::1", "ff02::1", "::ffff:8.8.8.8", "not-an-address"])
def test_a_non_global_answer_is_refused(address: str) -> None:
    assert address_refusal(address) is not None


def answer(address: str) -> tuple[Any, ...]:
    return (2, 1, 6, "", (address, 443))


def test_one_private_answer_refuses_the_whole_name() -> None:
    with pytest.raises(ValueError, match="dns_answer_not_global"):
        choose_address([answer("104.18.2.115"), answer("10.0.0.5")])
    with pytest.raises(ValueError, match="dns_no_answer"):
        choose_address([])
    assert choose_address([answer("104.18.2.115"), answer("104.18.3.115")]) == "104.18.2.115"


class FakeSocket:
    """A blocking in-memory socket end: `recv` waits for queued bytes; a shutdown or close ends it."""

    def __init__(self, inbound: list[bytes] | None = None, *, end: bool = False, on_send: Any = None) -> None:
        self.inbound: queue.Queue[bytes] = queue.Queue()
        for chunk in inbound or []:
            self.inbound.put(chunk)
        if end:
            self.inbound.put(b"")
        self.sent = b""
        self.on_send = on_send
        self.closed = False

    def recv(self, size: int, flags: int = 0) -> bytes:
        if flags & socket.MSG_PEEK:  # a non-blocking look at what is already queued, as a real socket answers
            with self.inbound.mutex:
                if not self.inbound.queue:
                    raise BlockingIOError
                return self.inbound.queue[0][:size]
        return self.inbound.get()[:size]

    def sendall(self, data: bytes) -> None:
        if self.on_send is not None:
            self.on_send(data)
        self.sent += data

    def settimeout(self, _: float | None) -> None:
        pass

    def gettimeout(self) -> float | None:  # a real socket has both; this fake answers at once in every mode
        return None

    def setblocking(self, _: bool) -> None:
        pass

    def shutdown(self, _: int) -> None:
        self.inbound.put(b"")

    def close(self) -> None:
        self.closed = True
        self.inbound.put(b"")


class Network:
    """Counts every resolve and connect the gateway makes."""

    def __init__(self, answers: list[tuple[Any, ...]] | Exception, upstream: FakeSocket | Exception | None = None) -> None:
        self.answers, self.upstream = answers, upstream
        self.resolved: list[tuple[Any, ...]] = []
        self.connected: list[tuple[Any, ...]] = []

    def resolve(self, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        self.resolved.append(args)
        if isinstance(self.answers, Exception):
            raise self.answers
        return self.answers

    def connect(self, address: tuple[str, int], timeout: float) -> FakeSocket:
        self.connected.append(address)
        assert 0 < timeout <= egress_gateway.CONNECT_SECONDS
        if isinstance(self.upstream, Exception):
            raise self.upstream
        assert self.upstream is not None
        return self.upstream


def gateway(tmp_path: Path, network: Network, **kwargs: Any) -> Gateway:
    return Gateway(Receipts(tmp_path), resolve=network.resolve, connect=network.connect, **kwargs)


def live_head(attempt: str = "att-1", seconds: float = 30) -> bytes:
    return head(headers=["Host: openrouter.ai:443", f"X-Relay-Attempt: {attempt}", f"X-Relay-Expires: {time.time() + seconds}"])


def receipts(folder: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (folder / "tunnels.jsonl").read_text(encoding="utf-8").splitlines()]


def test_an_admitted_connect_is_tunnelled_once_unchanged_and_receipted(tmp_path: Path) -> None:
    upstream = FakeSocket([b"server-hello", b"reply"], end=True)
    network = Network([answer("104.18.2.115")], upstream)
    client = FakeSocket([live_head()])
    client.on_send = lambda data: client.inbound.put(b"client-hello") if data == ESTABLISHED else None  # after the answer
    record = gateway(tmp_path, network).handle(client)
    assert network.connected == [("104.18.2.115", 443)]
    assert client.sent == ESTABLISHED + b"server-hello" + b"reply"
    assert upstream.sent == b"client-hello"
    assert (record["outcome"], record["attempt_id"], record["address"], record["bytes_down"], record["bytes_up"],
            record["close_reason"], record["test_resolution"]) == ("tunnel", "att-1", "104.18.2.115", 17, 12,
                                                                   "provider_closed", False)
    opening, closing = receipts(tmp_path)
    assert (opening["outcome"], opening["attempt_id"], opening["address"]) == ("opening", "att-1", "104.18.2.115")
    assert closing == {**record, "at": closing["at"]}
    assert client.closed and upstream.closed
    assert stat.S_IMODE((tmp_path / "tunnels.jsonl").stat().st_mode) == 0o600


@pytest.mark.parametrize("inbound, reason", [
    ([live_head() + b"CONNECT openrouter.ai:443 HTTP/1.1\r\n\r\n"], "data_before_tunnel"),
    ([live_head() + b"\x16\x03\x01"], "data_before_tunnel"),
    ([b"C" * 2000], "head_too_large"),
    ([b"CONNECT openrouter.ai:443 HTTP/1.1\r\n"], "head_incomplete"),
    ([live_head().replace(b"openrouter.ai:443", b"10.0.0.1:443")], "target_ip_literal"),
])
def test_a_refusal_is_receipted_before_it_is_answered_and_nothing_is_resolved_or_connected(
        tmp_path: Path, inbound: list[bytes], reason: str) -> None:
    network = Network([answer("104.18.2.115")], FakeSocket(end=True))

    def receipt_first(data: bytes) -> None:
        assert receipts(tmp_path)[-1]["reason"] == reason  # written and fsynced before the relay can read the answer
        assert data == f"HTTP/1.1 403 Forbidden\r\nX-Refusal: {reason}\r\n\r\n".encode()

    record = gateway(tmp_path, network).handle(FakeSocket(inbound, end=True, on_send=receipt_first))
    assert (record["outcome"], record["reason"]) == ("refused", reason)
    assert network.resolved == [] and network.connected == []


@pytest.mark.parametrize("answers, upstream, reason", [
    ([answer("104.18.2.115"), answer("127.0.0.1")], None, "dns_answer_not_global"),
    ([answer("172.17.0.1")], None, "dns_answer_not_global"),
    ([], None, "dns_no_answer"),
    (OSError("no name"), None, "dns_failure"),
    ([answer("104.18.2.115")], ConnectionRefusedError(), "connect_failed"),
])
def test_dns_and_connect_failures_are_refused_with_a_receipt(tmp_path: Path, answers: Any, upstream: Any,
                                                             reason: str) -> None:
    network = Network(answers, upstream)
    client = FakeSocket([live_head()], end=True)
    record = gateway(tmp_path, network).handle(client)
    assert (record["outcome"], record["reason"], record["attempt_id"]) == ("refused", reason, "att-1")
    assert client.sent == f"HTTP/1.1 403 Forbidden\r\nX-Refusal: {reason}\r\n\r\n".encode()
    assert len(network.connected) == (1 if reason == "connect_failed" else 0)
    assert [r["outcome"] for r in receipts(tmp_path)] == (["opening", "refused"] if reason == "connect_failed"
                                                         else ["refused"])  # an attempted connect is always counted


def test_an_attempt_is_tunnelled_at_most_once_even_after_a_gateway_restart(tmp_path: Path) -> None:
    network = Network([answer("104.18.2.115")], FakeSocket([b"x"], end=True))
    gateway(tmp_path, network).handle(FakeSocket([live_head("att-7")], end=True))
    second = gateway(tmp_path, network).handle(FakeSocket([live_head("att-7")], end=True))  # restarted: reads receipts
    assert (second["outcome"], second["reason"]) == ("refused", "attempt_repeated")
    assert len(network.connected) == 1


def test_a_torn_receipt_line_does_not_hide_the_attempts_before_it(tmp_path: Path) -> None:
    (tmp_path / "tunnels.jsonl").write_text(json.dumps({"attempt_id": "att-1"}) + "\n{\"attempt_", encoding="utf-8")
    assert Receipts(tmp_path).seen == {"att-1"}


def test_the_tunnel_closes_at_the_relay_expiry(tmp_path: Path) -> None:
    network = Network([answer("104.18.2.115")], FakeSocket())  # a provider that never answers
    began = time.time()
    record = gateway(tmp_path, network).handle(FakeSocket([live_head(seconds=0.3)]))
    assert record["close_reason"] == "expiry"
    assert record["closed_at"] - began < 0.3 + 1.0  # a backstop only: the relay's own send ends earlier (A5)


def test_the_tunnel_closes_at_the_byte_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(egress_gateway, "MAX_TUNNEL_BYTES", 10)
    network = Network([answer("104.18.2.115")], FakeSocket([b"0123456789A"]))
    record = gateway(tmp_path, network).handle(FakeSocket([live_head()]))
    assert record["close_reason"] == "byte_limit"


def test_a_test_resolution_replaces_dns_only_with_a_private_bridge_address(tmp_path: Path) -> None:
    for address in ("127.0.0.1", "0.0.0.0", "104.18.2.115", "not-an-address"):
        with pytest.raises(ValueError):
            gateway(tmp_path, Network([]), test_resolution=address)
    network = Network(OSError("dns must not be used"), FakeSocket(end=True))
    record = gateway(tmp_path, network, test_resolution="172.18.0.5").handle(FakeSocket([live_head()], end=True))
    assert (record["outcome"], record["address"], record["test_resolution"]) == ("tunnel", "172.18.0.5", True)
    assert network.resolved == [] and network.connected == [("172.18.0.5", 443)]


def test_the_gateway_has_no_key_no_tcp_listener_and_no_proxy_from_the_environment() -> None:
    source = Path(egress_gateway.__file__).read_text(encoding="utf-8")
    for forbidden in ("environ", "AF_INET", "authorization", "ssl", "provider-key", "secrets"):
        assert forbidden not in source.replace("AF_UNIX", "")


def test_a_connect_is_counted_by_an_fsynced_opening_receipt_before_it_starts(tmp_path: Path) -> None:
    """A gateway killed during a tunnel still leaves its count: the opening line exists before any connect."""
    class Counted(Network):
        def connect(self, address: tuple[str, int], timeout: float) -> FakeSocket:
            assert receipts(tmp_path)[-1]["outcome"] == "opening"
            return super().connect(address, timeout)

    network = Counted([answer("104.18.2.115")], FakeSocket(end=True))
    gateway(tmp_path, network).handle(FakeSocket([live_head()], end=True))
    assert len(network.connected) == 1


def test_dns_shares_the_relays_expiry_and_a_slow_answer_connects_nothing(tmp_path: Path) -> None:
    class Slow(Network):
        def resolve(self, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            time.sleep(1.0)
            return super().resolve(*args, **kwargs)

    network = Slow([answer("104.18.2.115")], FakeSocket(end=True))
    began = time.monotonic()
    record = gateway(tmp_path, network).handle(FakeSocket([live_head(seconds=0.3)], end=True))
    assert (record["outcome"], record["reason"]) == ("refused", "dns_timeout")
    assert time.monotonic() - began < 1.0 and network.connected == []


def test_no_connect_starts_once_the_budget_is_spent(tmp_path: Path) -> None:
    clock = [time.time()]
    network = Network([answer("104.18.2.115")], FakeSocket(end=True))
    resolve = network.resolve

    def late(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        clock[0] += 31  # the answer comes after the relay's expiry (wall clock of the gateway's own host)
        return resolve(*args, **kwargs)

    network.resolve = late  # type: ignore[method-assign]
    record = gateway(tmp_path, network, clock=lambda: clock[0]).handle(FakeSocket([live_head(seconds=30)], end=True))
    assert (record["outcome"], record["reason"]) == ("refused", "expired")
    assert network.connected == []



# --- R9 (controller disposition l1-e1-r9prep.md): NAT64 targets, one head budget, early bytes ----------------------


@pytest.mark.parametrize("address, embedded", [
    ("64:ff9b::7f00:1", "127.0.0.1"), ("64:ff9b::a00:1", "10.0.0.1"), ("64:ff9b::ac11:1", "172.17.0.1"),
    ("64:ff9b::c0a8:41fe", "192.168.65.254"), ("64:ff9b::6440:1", "100.64.0.1"), ("64:ff9b::a9fe:101", "169.254.1.1"),
    ("64:ff9b::e000:1", "224.0.0.1"), ("64:ff9b::", "0.0.0.0"),
])
def test_a_nat64_answer_whose_embedded_ipv4_is_not_global_is_refused(address: str, embedded: str) -> None:
    assert address_refusal(embedded) is not None  # the same target, given directly, is refused already
    assert address_refusal(address) == "dns_answer_not_global"


def test_a_nat64_answer_with_a_public_embedded_ipv4_stays_allowed() -> None:
    assert address_refusal("64:ff9b::6812:273") is None  # 104.18.2.115


def test_one_nat64_private_answer_refuses_the_whole_name() -> None:
    with pytest.raises(ValueError, match="dns_answer_not_global"):
        choose_address([answer("104.18.2.115"), answer("64:ff9b::a00:1")])


class SlowClient(FakeSocket):
    """A client that sends its valid head in pieces; each piece takes `step` seconds of the gateway's monotonic clock."""

    def __init__(self, pieces: list[bytes], clock: list[float], step: float) -> None:
        super().__init__(pieces, end=True)
        self.clock, self.step, self.timeouts = clock, step, []

    def settimeout(self, value: float | None) -> None:
        self.timeouts.append(value)

    def recv(self, size: int, flags: int = 0) -> bytes:
        if not flags & socket.MSG_PEEK:
            self.clock[0] += self.step
        return super().recv(size, flags)


def split(raw: bytes, parts: int) -> list[bytes]:
    size = -(-len(raw) // parts)
    return [raw[i:i + size] for i in range(0, len(raw), size)]


def test_the_whole_head_shares_one_five_second_budget_and_a_slow_head_connects_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [500.0]
    monkeypatch.setattr(egress_gateway, "monotonic", lambda: clock[0], raising=False)
    network = Network([answer("104.18.2.115")], FakeSocket(end=True))
    client = SlowClient(split(live_head(), 4), clock, 4.9)  # 4 pieces x 4.9 s: each read is short, the head is not
    record = gateway(tmp_path, network).handle(client)
    assert (record["outcome"], record["reason"]) == ("refused", "head_timeout")
    assert network.resolved == [] and network.connected == []
    assert receipts(tmp_path)[-1]["reason"] == "head_timeout"


def test_a_head_within_the_budget_passes_and_each_read_gets_only_the_time_left(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [500.0]
    monkeypatch.setattr(egress_gateway, "monotonic", lambda: clock[0], raising=False)
    network = Network([answer("104.18.2.115")], FakeSocket(end=True))
    client = SlowClient(split(live_head(), 3), clock, 1.0)
    record = gateway(tmp_path, network).handle(client)
    assert record["outcome"] == "tunnel" and network.connected == [("104.18.2.115", 443)]
    head_timeouts = client.timeouts[:3]
    assert head_timeouts == [5.0, 4.0, 3.0]  # never renewed per read


def test_bytes_already_queued_after_the_head_are_refused_before_any_connect(tmp_path: Path) -> None:
    network = Network([answer("104.18.2.115")], FakeSocket(end=True))
    record = gateway(tmp_path, network).handle(FakeSocket([live_head(), b"\x16\x03\x01"]))  # a second read's bytes
    assert (record["outcome"], record["reason"]) == ("refused", "data_before_tunnel")
    assert network.resolved == [] and network.connected == []


def test_bytes_that_arrive_during_the_lookup_are_refused_before_the_answer(tmp_path: Path) -> None:
    client = FakeSocket([live_head()])

    class Arriving(Network):
        def connect(self, address: tuple[str, int], timeout: float) -> FakeSocket:
            client.inbound.put(b"\x16\x03\x01")  # early client bytes, queued while the gateway connects
            return super().connect(address, timeout)

    upstream = FakeSocket()
    record = gateway(tmp_path, Arriving([answer("104.18.2.115")], upstream)).handle(client)
    assert (record["outcome"], record["reason"]) == ("refused", "data_before_tunnel")
    assert ESTABLISHED not in client.sent and upstream.sent == b"" and upstream.closed



# --- peekfix (controller disposition l1-peekfix1.md): the queued-byte look must never wait -------------------------


class TimedSocket(FakeSocket):
    """Models CPython's socket modes: with a POSITIVE timeout an empty read first waits the whole timeout (whatever the
    flags) and raises TimeoutError; with timeout 0.0 (non-blocking) it raises BlockingIOError at once; None blocks."""

    def __init__(self, inbound: list[bytes] | None = None, **kwargs: Any) -> None:
        super().__init__(inbound, **kwargs)
        self.timeout: float | None = None
        self.waited = 0.0

    def settimeout(self, value: float | None) -> None:
        self.timeout = value

    def gettimeout(self) -> float | None:
        return self.timeout

    def setblocking(self, flag: bool) -> None:
        self.timeout = None if flag else 0.0

    def recv(self, size: int, flags: int = 0) -> bytes:
        with self.inbound.mutex:
            empty = not self.inbound.queue
        if empty and self.timeout == 0.0:
            raise BlockingIOError
        if empty and self.timeout:
            self.waited += self.timeout
            raise TimeoutError("timed out")
        return super().recv(size, flags)


def test_an_empty_look_returns_at_once_and_restores_the_timeout() -> None:
    client = TimedSocket()
    client.settimeout(3.0)  # what _read_head leaves on the socket
    assert _early_bytes(client) is False
    assert (client.waited, client.gettimeout()) == (0.0, 3.0)


def test_a_queued_byte_is_seen_left_unread_and_the_timeout_restored() -> None:
    client = TimedSocket([b"\x16"])
    client.settimeout(3.0)
    assert _early_bytes(client) is True
    assert list(client.inbound.queue) == [b"\x16"] and client.gettimeout() == 3.0


class BrokenRestore(TimedSocket):
    def settimeout(self, value: float | None) -> None:
        if self.timeout == 0.0:
            raise OSError("restore failed")
        super().settimeout(value)


class ResetSocket(TimedSocket):
    def recv(self, size: int, flags: int = 0) -> bytes:
        raise ConnectionResetError


@pytest.mark.parametrize("client", [BrokenRestore(), ResetSocket()], ids=["restore-fails", "reset"])
def test_an_unreadable_socket_state_is_refused_not_assumed_clean(client: TimedSocket) -> None:
    client.timeout = 3.0
    assert _early_bytes(client) is True


def test_a_healthy_connect_passes_both_looks_without_waiting_and_gets_its_tunnel(tmp_path: Path) -> None:
    client = TimedSocket([live_head()])
    client.on_send = lambda data: client.inbound.put(b"client-hello") if data == ESTABLISHED else None
    upstream = FakeSocket([b"server-hello"], end=True)
    record = gateway(tmp_path, Network([answer("104.18.2.115")], upstream)).handle(client)
    assert record["outcome"] == "tunnel" and client.waited == 0.0
    assert client.sent.startswith(ESTABLISHED) and upstream.sent == b"client-hello"


def test_queued_bytes_are_refused_unread_by_either_look(tmp_path: Path) -> None:
    after_head = TimedSocket([live_head(), b"\x16\x03\x01"])
    network = Network([answer("104.18.2.115")], FakeSocket(end=True))
    record = gateway(tmp_path, network).handle(after_head)
    assert (record["reason"], network.connected, list(after_head.inbound.queue)[:1]) == (
        "data_before_tunnel", [], [b"\x16\x03\x01"])

    before_answer = TimedSocket([live_head()])

    class Arriving(Network):
        def connect(self, address: tuple[str, int], timeout: float) -> FakeSocket:
            before_answer.inbound.put(b"\x16\x03\x01")
            return super().connect(address, timeout)

    upstream = FakeSocket()
    (tmp_path / "second").mkdir()
    record = gateway(tmp_path / "second", Arriving([answer("104.18.2.115")], upstream)).handle(before_answer)
    assert record["reason"] == "data_before_tunnel" and before_answer.waited == 0.0
    assert ESTABLISHED not in before_answer.sent and upstream.sent == b"" and upstream.closed
