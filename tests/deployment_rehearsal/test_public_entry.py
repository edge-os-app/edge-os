"""The loopback public entry: routing, header handling, body cap and upstream loss, over real loopback sockets."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import public_entry


@pytest.mark.parametrize(("path", "expected"), [
    ("/healthz", "api"), ("/readyz", "api"), ("/v1/me", "api"), ("/v1", "api"), ("/v1/research/requests?x=1", "api"),
    ("/", "web"), ("/_next/static/chunk.js", "web"), ("/v10", "web"), ("/healthzz", "web"), ("/docs", "web"),
    ("/openapi.json", "web"), ("/readyz/extra", "web"),
])
def test_routes_only_the_public_api_paths_to_the_api(path: str, expected: str) -> None:
    assert public_entry.upstream_for(path) == expected


def test_drops_hop_by_hop_headers_and_those_named_by_connection() -> None:
    kept = public_entry.forwardable_headers([
        ("Authorization", "Bearer t"), ("Connection", "keep-alive, X-Private"), ("Keep-Alive", "5"),
        ("Transfer-Encoding", "chunked"), ("X-Private", "1"), ("Upgrade", "h2c"), ("Content-Type", "application/json"),
        ("Proxy-Authorization", "x"), ("TE", "trailers"), ("Trailer", "x"),
    ])
    assert kept == [("Authorization", "Bearer t"), ("Content-Type", "application/json")]


class _Recorder(BaseHTTPRequestHandler):
    seen: list[dict[str, object]] = []
    name = "upstream"

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        type(self).seen.append({"method": self.command, "path": self.path, "body": body,
                                "headers": {k.lower(): v for k, v in self.headers.items()}})
        payload = json.dumps({"from": type(self).name, "path": self.path}).encode()
        self.send_response(201 if self.command == "POST" else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Upstream", type(self).name)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    do_GET = do_POST = do_HEAD = do_OPTIONS = _answer

    def log_message(self, *_: object) -> None:
        return


def _serve(handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def entry() -> Iterator[tuple[int, type[_Recorder], type[_Recorder]]]:
    api = type("ApiRecorder", (_Recorder,), {"seen": [], "name": "api"})
    web = type("WebRecorder", (_Recorder,), {"seen": [], "name": "web"})
    api_server, web_server = _serve(api), _serve(web)
    upstreams = {"api": ("127.0.0.1", api_server.server_address[1]), "web": ("127.0.0.1", web_server.server_address[1])}
    server = public_entry.build_server("127.0.0.1", 0, upstreams)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1], api, web
    finally:
        for item in (server, api_server, web_server):
            item.shutdown()
            item.server_close()


def _request(port: int, method: str, path: str, body: bytes | None = None,
             headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        connection.close()


def test_forwards_method_path_body_and_authorization_to_the_api(entry) -> None:
    port, api, web = entry
    status, headers, body = _request(port, "POST", "/v1/research/requests?x=1", b'{"a":1}',
                                     {"Authorization": "Bearer tok", "Content-Type": "application/json"})
    assert status == 201 and headers["x-upstream"] == "api"
    assert json.loads(body) == {"from": "api", "path": "/v1/research/requests?x=1"}
    assert api.seen[0]["method"] == "POST" and api.seen[0]["body"] == b'{"a":1}'
    assert api.seen[0]["headers"]["authorization"] == "Bearer tok"
    assert web.seen == []


def test_forwards_pages_to_the_web_and_keeps_the_host_header(entry) -> None:
    port, api, web = entry
    status, headers, _ = _request(port, "GET", "/research/abc", headers={"Host": "127.0.0.1:9999"})
    assert status == 200 and headers["x-upstream"] == "web"
    assert web.seen[0]["headers"]["host"] == "127.0.0.1:9999"
    assert api.seen == []


@pytest.mark.parametrize("size", [public_entry.MAX_BODY_BYTES + 1, 4 * 1024 * 1024, 8 * 1024 * 1024],
                         ids=["cap-plus-one", "4MiB", "drain-ceiling"])
def test_a_complete_oversized_body_is_refused_with_413_and_no_upstream_contact(entry, size: int) -> None:
    """The client sends its whole body before reading; it must receive the 413, not a connection reset."""
    port, api, web = entry
    status, headers, body = _request(port, "POST", "/v1/x", b"x" * size)
    assert status == 413 and json.loads(body)["reason"] == "body_too_large"
    assert headers["connection"] == "close"
    assert api.seen == [] and web.seen == []


def _raw(port: int, head: bytes) -> socket.socket:
    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    client.sendall(head)
    return client


def _read_until_closed(client: socket.socket, limit: float) -> tuple[bytes, float]:
    """Everything the entry sends until it closes the connection, and how long that took."""
    started, data = time.monotonic(), b""
    client.settimeout(limit)
    try:
        while chunk := client.recv(65536):
            data += chunk
    except ConnectionResetError:
        pass
    return data, time.monotonic() - started


def test_a_huge_declared_length_is_refused_at_once_without_draining_it(entry) -> None:
    port, api, web = entry
    client = _raw(port, b"POST /v1/x HTTP/1.1\r\nHost: t\r\nContent-Length: 10737418240\r\n\r\n")
    try:
        data, elapsed = _read_until_closed(client, limit=5)
    finally:
        client.close()
    assert data.startswith(b"HTTP/1.1 413 ") and b"body_too_large" in data
    assert elapsed < 1.0
    assert api.seen == [] and web.seen == []


def test_a_sender_that_stops_early_is_closed_without_contacting_an_upstream(entry) -> None:
    port, api, web = entry
    declared = public_entry.MAX_BODY_BYTES + 10_000
    client = _raw(port, b"POST /v1/x HTTP/1.1\r\nHost: t\r\nContent-Length: %d\r\n\r\n" % declared + b"x" * 1024)
    client.shutdown(socket.SHUT_WR)  # the body ends early: the entry sees end of stream mid-drain
    try:
        data, elapsed = _read_until_closed(client, limit=5)
    finally:
        client.close()
    assert (data == b"" or data.startswith(b"HTTP/1.1 413 ")) and elapsed < 1.0  # either is a safe end
    assert api.seen == [] and web.seen == []
    status, _, _ = _request(port, "GET", "/healthz")  # the entry still serves the next caller
    assert status == 200


def test_a_slow_drip_is_cut_off_at_the_total_drain_deadline(entry, monkeypatch) -> None:
    """Each byte arrives well inside any per-read timeout; only a total deadline can stop the drain."""
    monkeypatch.setattr(public_entry, "DRAIN_SECONDS", 1.0, raising=False)
    port, api, web = entry
    threads_before = threading.active_count()
    client = _raw(port, b"POST /v1/x HTTP/1.1\r\nHost: t\r\nContent-Length: %d\r\n\r\n" % (public_entry.MAX_BODY_BYTES + 1))
    started, closed_after = time.monotonic(), None
    try:
        client.settimeout(0.05)
        while time.monotonic() - started < 4.0:
            try:
                client.send(b"x")
                if client.recv(1) == b"":
                    closed_after = time.monotonic() - started
                    break
            except TimeoutError:
                continue
            except (BrokenPipeError, ConnectionResetError):
                closed_after = time.monotonic() - started
                break
    finally:
        client.close()
    assert closed_after is not None, "the entry kept draining past its deadline"
    assert 0.9 <= closed_after <= 1.8
    assert api.seen == [] and web.seen == []
    deadline = time.monotonic() + 2.0
    while threading.active_count() > threads_before and time.monotonic() < deadline:
        time.sleep(0.05)
    assert threading.active_count() <= threads_before, "the handler thread did not finish"


def test_refuses_a_chunked_request_body(entry) -> None:
    port, api, _ = entry
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.putrequest("POST", "/v1/x")
        connection.putheader("Transfer-Encoding", "chunked")
        connection.endheaders()
        connection.send(b"1\r\nx\r\n0\r\n\r\n")
        response = connection.getresponse()
        assert response.status == 411
    finally:
        connection.close()
    assert api.seen == []


def test_reports_a_lost_upstream_with_a_reason_code_only() -> None:
    server = public_entry.build_server("127.0.0.1", 0, {"api": ("127.0.0.1", 9), "web": ("127.0.0.1", 9)})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, _, body = _request(server.server_address[1], "GET", "/readyz")
    finally:
        server.shutdown()
        server.server_close()
    assert status == 502
    assert json.loads(body) == {"status": "unavailable", "reason": "upstream_unavailable", "upstream": "api"}


@pytest.mark.parametrize(("line", "code"), [
    (b"GARBAGE\r\n\r\n", b"400"),                       # wrong word count: rejected before a path exists
    (b"GET /v1/me HTTP/9.x\r\n\r\n", b"400"),           # bad version
    (b"GET /" + b"a" * 70_000 + b" HTTP/1.1\r\n\r\n", b"414"),  # request line over the stdlib limit
], ids=["word-count", "bad-version", "too-long"])
def test_a_malformed_request_line_gets_its_error_reply_without_a_crash(entry, capsys, line: bytes, code: bytes) -> None:
    port, api, web = entry
    client = _raw(port, line)
    try:
        data, _ = _read_until_closed(client, limit=5)
    finally:
        client.close()
    assert code in data, data[:200]
    assert "Traceback" not in capsys.readouterr().err
    assert api.seen == [] and web.seen == []
    status, _, _ = _request(port, "GET", "/healthz")
    assert status == 200


@pytest.mark.parametrize("value", ["\xb2", "1" * 5000, "+5", "-1"], ids=["non-ascii-digit", "5000-digits", "plus", "minus"])
def test_an_invalid_content_length_is_refused_with_400_before_any_upstream(entry, capsys, value: str) -> None:
    port, api, web = entry
    client = _raw(port, b"POST /v1/x HTTP/1.1\r\nHost: t\r\nContent-Length: " + value.encode("latin-1") + b"\r\n\r\n")
    try:
        data, _ = _read_until_closed(client, limit=5)
    finally:
        client.close()
    assert data.startswith(b"HTTP/1.1 400 ") and b"invalid_length" in data, data[:200]
    assert "Traceback" not in capsys.readouterr().err
    assert api.seen == [] and web.seen == []
