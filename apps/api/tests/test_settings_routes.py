"""T4, T7-T10: configuration failures, route default-deny, CORS, production refusals."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute

import harness
from edge_os_api.main import create_app
from edge_os_api.settings import ConfigError, load_settings

SRC = Path(__file__).resolve().parents[1] / "src" / "edge_os_api"
PUBLIC_PATHS = {"/healthz", "/readyz"}


@pytest.mark.parametrize("name", ["EDGE_OS_ENV", "EDGE_OS_DATABASE_URL", "EDGE_OS_PRIVY_APP_ID",
                                  "EDGE_OS_PRIVY_VERIFICATION_KEY", "EDGE_OS_CORS_ALLOWED_ORIGINS"])
def test_t7_missing_required_value_names_field_only(env, name):
    broken = {k: v for k, v in env.items() if k != name}
    with pytest.raises(ConfigError) as caught:
        load_settings(broken)
    message = str(caught.value)
    assert name.removeprefix("EDGE_OS_").lower() in message
    for secret in (env["EDGE_OS_DATABASE_URL"], env["EDGE_OS_PRIVY_VERIFICATION_KEY"], "BEGIN"):
        assert secret not in message


@pytest.mark.parametrize("name,value", [
    ("EDGE_OS_ENV", "staging"), ("EDGE_OS_DATABASE_URL", "sqlite:///x.db"),
    ("EDGE_OS_DATABASE_URL", "postgresql://u:pw@127.0.0.1/edge_os_test_x"), ("EDGE_OS_PRIVY_APP_ID", " "),
    ("EDGE_OS_CORS_ALLOWED_ORIGINS", "*"), ("EDGE_OS_CORS_ALLOWED_ORIGINS", "http://a.example,*"),
    ("EDGE_OS_CORS_ALLOWED_ORIGINS", ""), ("EDGE_OS_PRIVY_VERIFICATION_KEY", "garbage")])
def test_t7_invalid_values_fail(env, name, value):
    with pytest.raises(ConfigError) as caught:
        load_settings({**env, name: value})
    assert "pw" not in str(caught.value)


def test_t7_test_env_rules(env, pg):
    remote = env["EDGE_OS_DATABASE_URL"].replace("127.0.0.1", "db.example.com")
    with pytest.raises(ConfigError, match="loopback"):
        load_settings({**env, "EDGE_OS_DATABASE_URL": remote})
    with pytest.raises(ConfigError, match="edge_os_test_"):
        load_settings({**env, "EDGE_OS_DATABASE_URL": env["EDGE_OS_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"})


def test_t10_production_refuses_test_app_and_http_origins(env):
    prod = {**env, "EDGE_OS_ENV": "production", "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.example.com",
            "EDGE_OS_DATABASE_URL": env["EDGE_OS_DATABASE_URL"]}
    with pytest.raises(ConfigError, match="test app id"):
        load_settings(prod)
    with pytest.raises(ConfigError, match="https"):
        load_settings({**prod, "EDGE_OS_PRIVY_APP_ID": "real-app", "EDGE_OS_CORS_ALLOWED_ORIGINS": "http://app.example.com"})
    assert load_settings({**prod, "EDGE_OS_PRIVY_APP_ID": "real-app"}).docs_enabled is False


def test_ambient_environment_is_ignored_by_the_harness(env, monkeypatch):
    monkeypatch.setenv("EDGE_OS_DATABASE_URL", "postgresql+psycopg://wrong@127.0.0.1/edge_os_test_wrong")
    child = harness.api_env(database_url=env["EDGE_OS_DATABASE_URL"], public_pem="x", previous_pem=None, cors=["http://a"])
    assert child["EDGE_OS_DATABASE_URL"] == env["EDGE_OS_DATABASE_URL"]
    assert "VIRTUAL_ENV" not in child


def leaf_routes(routes, prefix=""):
    """Flatten FastAPI's included-router wrappers into (full path, route) pairs."""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from leaf_routes(inner.routes, prefix + getattr(getattr(route, "include_context", None), "prefix", ""))
        else:
            yield prefix + getattr(route, "path", ""), route


def concrete(path):
    for name in ("intake_id", "strategy_id", "revision_id", "operation_id"):
        path = path.replace("{" + name + "}", "x")
    return path


def test_t4_route_walk_finds_only_api_routes(client):
    paths = {path for path, _ in leaf_routes(client.app.routes)}
    assert "/docs" not in paths and "/openapi.json" not in paths  # test env disables docs
    for path, route in leaf_routes(client.app.routes):
        assert isinstance(route, APIRoute), f"mount, websocket or other route found at {path}: {type(route)}"
    assert PUBLIC_PATHS <= paths and any(p.startswith("/v1/") for p in paths)


def test_t4_unauthenticated_requests_reach_no_route(client):
    seen = 0
    for path, route in leaf_routes(client.app.routes):
        if path in PUBLIC_PATHS:
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            response = client.request(method, concrete(path), content=b"")
            assert response.status_code == 401, (method, path, response.status_code)
            assert response.json()["code"] == "auth_required"
            seen += 1
    assert seen >= 9


def test_t4_docs_are_enabled_only_locally(env, migrated):
    local = TestClient(create_app(load_settings({**env, "EDGE_OS_ENV": "local"})))
    assert local.get("/docs").status_code == 200
    test = TestClient(create_app(load_settings(env)))
    assert test.get("/docs").status_code == 404 and test.get("/openapi.json").status_code == 404


def test_t4_source_has_no_override_or_bypass():
    forbidden = ("dependency_overrides", "AUTH_DISABLED", "BYPASS", "PRIVY_APP_SECRET")
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        for word in forbidden:
            if path.name == "settings.py" and word in {"AUTH_DISABLED", "BYPASS", "PRIVY_APP_SECRET"}:
                continue  # settings.py only lists them to refuse them
            assert word not in text, f"{word} in {path.name}"
        tree = ast.parse(text)
        assert not any(isinstance(n, ast.Attribute) and n.attr == "dependency_overrides" for n in ast.walk(tree))


def test_t9_cors_allow_list(client):
    allowed = client.options("/v1/me", headers={"Origin": "http://127.0.0.1:3999", "Access-Control-Request-Method": "GET",
                                                "Access-Control-Request-Headers": "authorization"})
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:3999"
    other = client.options("/v1/me", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in other.headers
    assert client.get("/healthz", headers={"Origin": "http://evil.example"}).headers.get("access-control-allow-origin") is None


def test_error_bodies_follow_the_contract_envelope(client, owner_a):
    from edge_os_api import p02
    for response in (client.get("/nope"), client.get("/v1/me"), client.post("/v1/research/requests", json={}, headers=owner_a),
                     client.get("/v1/research/requests/not-a-uuid", headers=owner_a)):
        p02.validate_http_error(response.json())


def test_p02_inputs_are_frozen_and_checker_still_passes():
    from edge_os_api import p02
    p02.verify_frozen_files()
    run = subprocess.run([sys.executable, "-I", str(p02.CHECKER_PATH)], capture_output=True, text=True)
    assert run.returncode == 0 and "PASS: 39 fixtures" in run.stdout


def test_m1_m2_migration_head_matches_models(env, migrated):
    child = harness.base_env()
    child["EDGE_OS_DATABASE_URL"] = env["EDGE_OS_DATABASE_URL"]
    check = subprocess.run([harness.api_python(), "-m", "alembic", "check"], cwd=harness.API_DIR, env=child,
                           capture_output=True, text=True)
    assert check.returncode == 0 and "No new upgrade operations detected" in (check.stdout + check.stderr)
    again = harness.migrate(env)  # upgrade is idempotent at head
    assert again.returncode == 0


@pytest.mark.parametrize("name", ["EDGE_OS_PRIVY_VERIFICATION_KEY", "EDGE_OS_PRIVY_APP_ID"])
def test_an_empty_required_value_stops_startup_with_the_field_name(env, name):
    with pytest.raises(ConfigError) as caught:
        load_settings({**env, name: ""})
    assert name.removeprefix("EDGE_OS_").lower() in str(caught.value)
