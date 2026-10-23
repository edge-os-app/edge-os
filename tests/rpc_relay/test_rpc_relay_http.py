"""The relay's HTTP layer on 127.0.0.1 with a fake upstream, the peer gate and the upstream HTTPS client (faked)."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

import rpc_relay as relay
from relay_support import SENTINEL_HOST, SENTINEL_KEY, SENTINEL_URL
from test_rpc_relay_core import FakeUpstream, assert_no_secret, call


class Peers:
    def __init__(self, admit: bool = True) -> None:
        self.admit = admit
        self.seen: list[str] = []

    def __call__(self, address: str) -> bool:
        self.seen.append(address)
        return self.admit


@pytest.fixture
def served(capsys) -> Iterator[Any]:
    started: list[Any] = []

    def start(role: str = "observer", upstream: FakeUpstream | None = None, peers: Peers | None = None):
        upstream = upstream or FakeUpstream()
        logs: list[dict[str, Any]] = []
        config = relay.load_config({"EDGE_OS_RPC_RELAY_UPSTREAM_URL": SENTINEL_URL})
        core = relay.RelayCore(role=role, upstream=upstream, secrets=config.upstream.secrets(), log=logs.append)
        server = relay.build_server(core, admit_peer=peers or Peers(), host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append(server)
        return server.server_address[1], upstream, logs

    yield start
    for server in started:
        server.shutdown()
        server.server_close()
    captured = capsys.readouterr()
    assert_no_secret(captured.out, captured.err)


def request(port: int, method: str = "POST", path: str = "/rpc", body: bytes | None = None,
            headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body,
                           headers={"Content-Type": "application/json", **(headers or {})})
        response = connection.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        connection.close()


def raw_request(port: int, data: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(data)
        chunks = []
        while True:
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)


def test_a_call_is_answered_with_exact_framing(served):
    port, upstream, logs = served()
    status, headers, body = request(port, body=call("eth_chainId", []))
    assert status == 200
    assert json.loads(body) == {"jsonrpc": "2.0", "id": 7, "result": "0x8f"}
    assert headers["content-type"] == "application/json"
    assert int(headers["content-length"]) == len(body)
    assert "content-encoding" not in headers
    assert headers["cache-control"] == "no-store"
    assert "python" not in headers.get("server", "").lower()
    assert len(upstream.bodies) == 1 and logs[-1]["outcome"] == "forwarded"


def test_a_charset_parameter_on_the_content_type_is_accepted(served):
    port, upstream, _ = served()
    status, _, _ = request(port, body=call("eth_chainId", []),
                           headers={"Content-Type": "application/json; charset=utf-8"})
    assert status == 200 and len(upstream.bodies) == 1


@pytest.mark.parametrize("method, path, status", [
    ("GET", "/rpc", 405), ("PUT", "/rpc", 405), ("DELETE", "/rpc", 405),
    ("POST", "/rpc?x=1", 404), ("POST", "/rpc#f", 404), ("POST", "/rpc/", 404), ("POST", "/", 404),
    ("POST", "/RPC", 404), ("POST", "//rpc", 404), ("POST", "/healthz", 405),
])
def test_only_post_to_exactly_rpc_reaches_the_relay(served, method, path, status):
    port, upstream, _ = served()
    got, _, body = request(port, method=method, path=path, body=call("eth_chainId", []))
    assert got == status
    assert upstream.bodies == []
    assert json.loads(body)["error"]["code"] in (-32600, -32601)


def test_a_wrong_content_type_is_refused(served):
    port, upstream, _ = served()
    status, _, _ = request(port, body=call("eth_chainId", []), headers={"Content-Type": "text/plain"})
    assert status == 415 and upstream.bodies == []


def test_a_missing_content_length_is_refused(served):
    port, upstream, _ = served()
    reply = raw_request(port, b"POST /rpc HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                              b"Connection: close\r\n\r\n")
    assert reply.startswith(b"HTTP/1.1 411") or reply.startswith(b"HTTP/1.0 411")
    assert upstream.bodies == []


def test_chunked_bodies_are_refused(served):
    port, upstream, _ = served()
    reply = raw_request(port, b"POST /rpc HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                              b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n2\r\n{}\r\n0\r\n\r\n")
    assert b" 411 " in reply.split(b"\r\n", 1)[0] or b" 400 " in reply.split(b"\r\n", 1)[0]
    assert upstream.bodies == []


@pytest.mark.parametrize("length", ["-1", "abc", "1e3", "+5", "0x10", "5 5", "99999999999999999999"])
def test_a_bad_content_length_is_refused(served, length):
    port, upstream, _ = served()
    reply = raw_request(port, (f"POST /rpc HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                               f"Content-Length: {length}\r\nConnection: close\r\n\r\n").encode())
    first = reply.split(b"\r\n", 1)[0]
    assert b" 400 " in first or b" 413 " in first or b" 411 " in first, first
    assert upstream.bodies == []


def test_an_oversized_content_length_is_refused_before_the_body_is_read(served):
    port, upstream, _ = served()
    reply = raw_request(port, (f"POST /rpc HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                               f"Content-Length: {relay.MAX_REQUEST_BYTES + 1}\r\nConnection: close\r\n\r\n").encode())
    assert b" 413 " in reply.split(b"\r\n", 1)[0]
    assert upstream.bodies == []


def test_a_batch_over_http_is_refused(served):
    port, upstream, _ = served("broadcast")
    status, _, body = request(port, body=json.dumps([json.loads(call("eth_chainId", []))]).encode())
    assert status == 400 and json.loads(body)["error"]["code"] == -32600 and upstream.bodies == []


def test_a_peer_that_is_not_the_proxy_is_refused_before_the_body(served):
    peers = Peers(admit=False)
    port, upstream, logs = served(peers=peers)
    status, _, body = request(port, body=call("eth_chainId", []))
    assert status == 403
    assert json.loads(body)["error"]["code"] == -32600
    assert upstream.bodies == [] and peers.seen == ["127.0.0.1"]
    assert logs[-1]["outcome"] == "peer_refused"


def test_the_health_check_needs_no_upstream_and_no_proxy(served):
    peers = Peers(admit=False)
    port, upstream, _ = served("broadcast", peers=peers)
    status, _, body = request(port, method="GET", path="/healthz")
    assert status == 200 and json.loads(body) == {"status": "ok", "role": "broadcast"}
    assert upstream.bodies == [] and peers.seen == []


def test_the_upstream_url_never_reaches_a_client_or_the_output(served):
    def leaky(request: dict[str, Any]) -> relay.UpstreamReply:
        raise RuntimeError(f"failed {SENTINEL_URL}")

    port, _, logs = served(upstream=FakeUpstream(leaky))
    status, headers, body = request(port, body=call("eth_chainId", []))
    assert status == 502
    assert_no_secret(body, headers, logs)


def test_an_unexpected_handler_error_is_logged_by_type_only(served, monkeypatch):
    port, _, _ = served()

    def explode(self: Any, body: bytes) -> Any:
        raise ValueError(f"exploded near {SENTINEL_URL}")

    monkeypatch.setattr(relay.RelayCore, "handle", explode)
    status, _, body = request(port, body=call("eth_chainId", []))
    assert status == 500
    assert_no_secret(body)


# --- peer gate -------------------------------------------------------------------------------------------------


def test_the_proxy_gate_admits_only_the_resolved_proxy_address():
    answers = {"coolify-proxy": ["10.0.1.5"]}
    lookups: list[str] = []

    def resolve(name: str) -> list[str]:
        lookups.append(name)
        return answers[name]

    clock = [0.0]
    gate = relay.ProxyGate("coolify-proxy", resolve=resolve, clock=lambda: clock[0])
    assert gate("10.0.1.5") is True
    assert gate("10.0.1.6") is False
    assert gate("127.0.0.1") is False
    assert lookups == ["coolify-proxy"]  # cached
    clock[0] += relay.PROXY_CACHE_SECONDS + 1
    answers["coolify-proxy"] = ["10.0.1.9"]
    assert gate("10.0.1.5") is False
    assert gate("10.0.1.9") is True


@pytest.mark.parametrize("answer", [OSError("no such host"), [], ["not-an-ip"]])
def test_the_proxy_gate_refuses_when_the_proxy_cannot_be_resolved(answer):
    def resolve(name: str) -> list[str]:
        if isinstance(answer, Exception):
            raise answer
        return answer

    gate = relay.ProxyGate("coolify-proxy", resolve=resolve, clock=lambda: 0.0)
    assert gate("10.0.1.5") is False


def test_the_proxy_gate_compares_normalized_addresses():
    gate = relay.ProxyGate("p", resolve=lambda name: ["10.0.1.5"], clock=lambda: 0.0)
    assert gate("::ffff:10.0.1.5") is True
    assert gate("010.000.001.005") is False


# --- upstream HTTPS client (faked connection) ------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int, headers: list[tuple[str, str]], body: bytes) -> None:
        self.status, self._headers, self._body = status, headers, body
        self.read_sizes: list[int] = []

    def getheaders(self) -> list[tuple[str, str]]:
        return self._headers

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        out, self._body = (self._body, b"") if size < 0 else (self._body[:size], self._body[size:])
        return out


class FakeConnection:
    instances: list["FakeConnection"] = []

    def __init__(self, host: str, port: int, *, timeout: float, context: Any) -> None:
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.requests: list[tuple[str, str, bytes, dict[str, str]]] = []
        self.closed = False
        self.response = FakeResponse(200, [("Content-Type", "application/json")], b'{"jsonrpc":"2.0","id":1,"result":"0x8f"}')
        self.fail: Exception | None = None
        FakeConnection.instances.append(self)

    def request(self, method: str, path: str, body: bytes, headers: dict[str, str]) -> None:
        if self.fail:
            raise self.fail
        self.requests.append((method, path, body, headers))

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def upstream_client(**overrides: Any) -> relay.UpstreamClient:
    FakeConnection.instances = []
    config = relay.load_config({"EDGE_OS_RPC_RELAY_UPSTREAM_URL": SENTINEL_URL})
    return relay.UpstreamClient(config.upstream, connect=FakeConnection, **overrides)


def test_the_upstream_client_posts_to_the_keyed_path_with_fixed_headers_only():
    client = upstream_client()
    reply = client(b'{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}')
    connection = FakeConnection.instances[-1]
    assert (connection.host, connection.port) == (SENTINEL_HOST, 443)
    assert connection.context.verify_mode.name == "CERT_REQUIRED" and connection.context.check_hostname
    method, path, body, headers = connection.requests[0]
    assert method == "POST" and path == f"/{SENTINEL_KEY}/"
    assert {k.lower() for k in headers} == {"content-type", "accept", "accept-encoding", "user-agent"}
    assert headers["Accept-Encoding"] == "identity"
    assert connection.closed
    assert reply.status == 200 and reply.body.endswith(b'"0x8f"}')
    assert reply.headers == {"content-type": "application/json"}


def test_the_upstream_client_caps_the_reply_it_reads():
    client = upstream_client()
    FakeConnection.instances = []

    original = FakeConnection.__init__

    def big(self: FakeConnection, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        self.response = FakeResponse(200, [], b"x" * (relay.MAX_RESPONSE_BYTES * 2))

    FakeConnection.__init__ = big  # type: ignore[method-assign]
    try:
        reply = client(b"{}")
    finally:
        FakeConnection.__init__ = original  # type: ignore[method-assign]
    assert len(reply.body) == relay.MAX_RESPONSE_BYTES + 1


def test_an_upstream_transport_error_is_replaced_by_a_bare_failure():
    client = upstream_client()
    original = FakeConnection.__init__

    def failing(self: FakeConnection, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        self.fail = OSError(f"cannot reach {SENTINEL_URL}")

    FakeConnection.__init__ = failing  # type: ignore[method-assign]
    try:
        with pytest.raises(relay.UpstreamFailure) as caught:
            client(b"{}")
    finally:
        FakeConnection.__init__ = original  # type: ignore[method-assign]
    assert caught.value.__cause__ is None and caught.value.__context__ is None or caught.value.__suppress_context__
    assert_no_secret(str(caught.value), repr(caught.value), caught.value.args)


def test_the_upstream_client_never_follows_a_redirect():
    client = upstream_client()
    original = FakeConnection.__init__

    def redirect(self: FakeConnection, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        self.response = FakeResponse(301, [("Location", "https://elsewhere.invalid/")], b"")

    FakeConnection.__init__ = redirect  # type: ignore[method-assign]
    try:
        reply = client(b"{}")
    finally:
        FakeConnection.__init__ = original  # type: ignore[method-assign]
    assert reply.status == 301 and len(FakeConnection.instances) == 1


def test_open_connections_are_capped(served, monkeypatch):
    monkeypatch.setattr(relay, "MAX_CONNECTIONS", 1)
    port, upstream, logs = served()
    idle = socket.create_connection(("127.0.0.1", port), timeout=5)  # holds the one slot: it never sends a request
    try:
        second = raw_request(port, b"GET /healthz HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        assert second == b""
        assert logs[-1]["outcome"] == "connection_refused"
    finally:
        idle.close()
    for _ in range(100):
        if request(port, method="GET", path="/healthz")[0] == 200:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("the slot was not released")
