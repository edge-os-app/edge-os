"""The public Hermes forward on the Coolify API.

The real `create_app` is used with the shared database. Only the upstream is a local HTTP server. The tests prove the
split, the auth and write-limit order, the header and body allowlists, the no-retry rule, and the explicit error codes.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from edge_os_api.core import hermes_proxy
from edge_os_api.core.hermes_proxy import public_forward_enabled
from edge_os_api.main import create_app

INTAKE = "0b7f5f3a-0a8f-4f6a-9a6e-1a2b3c4d5e6f"


class Upstream:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.status = 200
        self.headers: list[tuple[str, str]] = [("Content-Type", "application/json")]
        self.body = b'{"ok": true}'
        self.delay = 0.0
        self.lock = threading.Lock()

    def record(self, method: str, path: str, headers: list[tuple[str, str]], body: bytes) -> None:
        with self.lock:
            self.requests.append({"method": method, "path": path,
                                  "headers": {name.lower(): value for name, value in headers}, "body": body})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - the base class name
        self._answer()

    def do_POST(self) -> None:  # noqa: N802
        self._answer()

    def _answer(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length) if length else b""
        self.server.upstream.record(self.command, self.path, list(self.headers.items()), body)
        if self.server.upstream.delay:
            time.sleep(self.server.upstream.delay)
        payload = self.server.upstream.body
        self.send_response(self.server.upstream.status)
        for name, value in self.server.upstream.headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args: Any) -> None:
        pass


@pytest.fixture
def upstream() -> Any:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.upstream = Upstream()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def app_client(settings: Any, upstream: ThreadingHTTPServer) -> TestClient:
    url = f"http://127.0.0.1:{upstream.server_address[1]}"
    return TestClient(create_app(settings.model_copy(update={"hermes_app_url": url})))


def test_an_unauthenticated_request_is_refused_before_the_upstream(settings, migrated, upstream) -> None:
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter")
    assert response.status_code == 401 and response.json()["code"] == "auth_required"
    assert upstream.upstream.requests == []


def test_the_six_paths_are_forwarded_with_method_path_and_body(settings, migrated, owner_a, upstream) -> None:
    with app_client(settings, upstream) as client:
        get_one = client.get("/v1/interpreter", headers=owner_a)
        create = client.post("/v1/research/requests", headers=owner_a, json={"text": "hello"})
        listing = client.get("/v1/research/requests", headers=owner_a)
        detail = client.get(f"/v1/research/requests/{INTAKE}", headers=owner_a)
        answer = client.post(f"/v1/research/requests/{INTAKE}/clarifications", headers=owner_a, json={"answer_text": "x"})
        retry = client.post(f"/v1/research/requests/{INTAKE}/interpretation-retries", headers=owner_a, json={})
    assert [response.status_code for response in (get_one, create, listing, detail, answer, retry)] == [200] * 6
    seen = upstream.upstream.requests
    assert [(item["method"], item["path"]) for item in seen] == [
        ("GET", "/v1/interpreter"),
        ("POST", "/v1/research/requests"),
        ("GET", "/v1/research/requests"),
        ("GET", f"/v1/research/requests/{INTAKE}"),
        ("POST", f"/v1/research/requests/{INTAKE}/clarifications"),
        ("POST", f"/v1/research/requests/{INTAKE}/interpretation-retries"),
    ]
    assert json.loads(seen[1]["body"]) == {"text": "hello"}
    assert seen[0]["headers"]["authorization"] == owner_a["Authorization"]


def test_a_path_outside_the_six_is_not_forwarded(settings, migrated, owner_a, upstream) -> None:
    with app_client(settings, upstream) as client:
        response = client.get("/v1/me", headers=owner_a)
    assert response.status_code == 200
    assert upstream.upstream.requests == []


@pytest.mark.parametrize("path", [
    "/v1/interpreter/", "/v1/research/requests/", "/v1/research/requests/%2e%2e",
    "/v1/research/requests/" + INTAKE + "/investigations",
])
def test_a_near_miss_or_outside_path_is_not_forwarded(settings, migrated, owner_a, upstream, path: str) -> None:
    with app_client(settings, upstream) as client:
        response = client.get(path, headers=owner_a)
    assert response.status_code == 404
    assert upstream.upstream.requests == []


def test_only_the_allowlisted_request_headers_are_forwarded(settings, migrated, owner_a, upstream) -> None:
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter", headers={
            **owner_a, "Accept": "application/json", "Cookie": "session=secret", "X-Forwarded-For": "1.2.3.4",
            "Forwarded": "for=1.2.3.4", "X-Real-IP": "1.2.3.4", "Host": "evil.example", "X-Secret": "no",
        })
    assert response.status_code == 200
    [seen] = upstream.upstream.requests
    assert "cookie" not in seen["headers"] and "x-forwarded-for" not in seen["headers"]
    assert "forwarded" not in seen["headers"] and "x-real-ip" not in seen["headers"]
    assert "x-secret" not in seen["headers"]
    assert seen["headers"]["host"] == f"127.0.0.1:{upstream.server_address[1]}"


def test_only_the_allowlisted_response_headers_are_returned(settings, migrated, owner_a, upstream) -> None:
    upstream.upstream.headers = [("Content-Type", "application/json"), ("Retry-After", "3"),
                                 ("X-Secret", "no"), ("Set-Cookie", "session=secret")]
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter", headers=owner_a)
    assert response.status_code == 200
    assert response.headers["retry-after"] == "3"
    assert "x-secret" not in response.headers and "set-cookie" not in response.headers


def test_the_upstream_json_error_envelope_returns_unchanged(settings, migrated, owner_a, upstream) -> None:
    upstream.upstream.status = 409
    upstream.upstream.body = json.dumps({"code": "parent_revision_conflict", "detail": "reload"}).encode()
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter", headers=owner_a)
    assert response.status_code == 409 and response.json() == {"code": "parent_revision_conflict",
                                                               "detail": "reload"}


def test_a_refused_connection_is_an_explicit_503(settings, migrated, owner_a) -> None:
    with TestClient(create_app(settings.model_copy(update={"hermes_app_url": "http://127.0.0.1:1"}))) as client:
        response = client.get("/v1/interpreter", headers=owner_a)
    assert response.status_code == 503
    assert response.json()["code"] == "interpreter_unavailable"


def test_a_read_timeout_is_an_explicit_504(settings, migrated, owner_a, upstream, monkeypatch) -> None:
    monkeypatch.setattr(hermes_proxy, "READ_TIMEOUT_SECONDS", 0.2)
    upstream.upstream.delay = 1.0
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter", headers=owner_a)
    assert response.status_code == 504
    assert response.json()["code"] == "interpreter_timeout"


def test_a_redirect_is_never_followed_and_becomes_an_explicit_502(settings, migrated, owner_a, upstream) -> None:
    upstream.upstream.status = 302
    upstream.upstream.headers = [("Content-Type", "application/json"), ("Location", "http://evil.example")]
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter", headers=owner_a)
    assert response.status_code == 502
    assert response.json()["code"] == "interpreter_route_failed"
    assert "location" not in response.headers


def test_an_environment_proxy_is_never_read(settings, migrated, owner_a, upstream, monkeypatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter", headers=owner_a)
    assert response.status_code == 200
    assert len(upstream.upstream.requests) == 1


def test_an_over_size_request_body_is_refused_before_the_upstream(settings, migrated, owner_a, upstream) -> None:
    with app_client(settings, upstream) as client:
        response = client.post("/v1/research/requests", headers={**owner_a, "Content-Type": "application/json"},
                               content=b"{" + b"a" * (256 * 1024) + b"}")
    assert response.status_code == 422
    assert response.json()["findings"][0]["code"] == "body_too_large"
    assert upstream.upstream.requests == []


def test_an_over_size_upstream_reply_is_an_explicit_502(settings, migrated, owner_a, upstream, monkeypatch) -> None:
    monkeypatch.setattr(hermes_proxy, "MAX_UPSTREAM_BYTES", 10)
    upstream.upstream.body = b'{"long": "0123456789"}'
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter", headers=owner_a)
    assert response.status_code == 502
    assert response.json()["code"] == "interpreter_route_failed"


def test_the_write_limit_runs_before_the_forward(settings, migrated, owner_a, upstream) -> None:
    tight = settings.model_copy(update={"write_rate_per_minute": 1})
    with app_client(tight, upstream) as client:
        first = client.post("/v1/research/requests", headers=owner_a, json={})
        second = client.post("/v1/research/requests", headers=owner_a, json={})
    assert first.status_code == 200 and second.status_code == 429
    assert len(upstream.upstream.requests) == 1


def test_options_is_answered_by_the_api_and_not_forwarded(settings, migrated, upstream) -> None:
    with app_client(settings, upstream) as client:
        response = client.options("/v1/research/requests", headers={
            "Origin": "http://127.0.0.1:3999", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3999"
    assert upstream.upstream.requests == []


def test_the_upstream_url_is_not_taken_from_a_client_header(settings, migrated, owner_a, upstream) -> None:
    with app_client(settings, upstream) as client:
        response = client.get("/v1/interpreter", headers={**owner_a, "X-Upstream": "http://evil.example:8011"})
    assert response.status_code == 200
    assert len(upstream.upstream.requests) == 1
    assert upstream.upstream.requests[0]["path"] == "/v1/interpreter"


def test_only_the_fixture_api_forwards() -> None:
    from types import SimpleNamespace

    def settings(interpreter: str, env: str, url: str | None) -> SimpleNamespace:
        return SimpleNamespace(interpreter=interpreter, env=env, hermes_app_url=url)

    assert public_forward_enabled(settings("fixture", "production", None)) is True
    assert public_forward_enabled(settings("fixture", "production", "http://10.0.1.1:8011")) is True
    assert public_forward_enabled(settings("fixture", "test", None)) is False
    assert public_forward_enabled(settings("hermes_local", "production", None)) is False
    assert public_forward_enabled(settings("hermes_local", "test", None)) is False
