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
from edge_os_api.core.settings import ConfigError, load_settings

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


@pytest.mark.parametrize("name", ["EDGE_OS_ENV", "EDGE_OS_DATABASE_URL", "EDGE_OS_PRIVY_APP_ID",
                                  "EDGE_OS_PRIVY_VERIFICATION_KEY", "EDGE_OS_CORS_ALLOWED_ORIGINS"])
def test_ambient_environment_does_not_fill_an_explicit_mapping(env, monkeypatch, name):
    monkeypatch.setenv(name, env[name])
    broken = {k: v for k, v in env.items() if k != name}
    with pytest.raises(ConfigError) as caught:
        load_settings(broken)
    assert name.removeprefix("EDGE_OS_").lower() in str(caught.value)


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
    hosted = {**prod, "EDGE_OS_PRIVY_APP_ID": "real-app", "EDGE_OS_BUILD_SHA": "0123456789abcdef",
              "EDGE_OS_DATABASE_URL": "postgresql+psycopg://app@db.internal.example:5432/edge_os?sslmode=require"}
    assert load_settings(hosted).docs_enabled is False


@pytest.mark.parametrize("change,message", [
    ({"EDGE_OS_BUILD_SHA": ""}, "build_sha: production needs the exact build identity"),
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://app@127.0.0.1:5432/edge_os?sslmode=require"},
     "database_url: production needs a hosted database"),
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://app@db.internal.example:5432/edge_os"},
     "database_url: production needs sslmode=require"),
    ({"EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"}, "research_history_mode"),
    ({"EDGE_OS_INTERPRETER": "hermes_local"}, "interpreter"),
    ({"EDGE_OS_EXECUTION_MODE": "fixture"}, "execution_mode"),
    ({"EDGE_OS_WALLET_PROVIDER": "fixture"}, "wallet_provider"),
])
def test_production_refuses_local_modes_and_missing_selected_settings(env, change, message):
    secret = "postgresql+psycopg://app:do-not-echo-this@db.internal.example:5432/edge_os?sslmode=require"
    hosted = {**env, "EDGE_OS_ENV": "production", "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.example.com",
              "EDGE_OS_PRIVY_APP_ID": "real-app", "EDGE_OS_BUILD_SHA": "0123456789abcdef",
              "EDGE_OS_DATABASE_URL": secret}
    with pytest.raises(ConfigError, match=message) as refused:
        load_settings({**hosted, **change})
    assert "do-not-echo-this" not in str(refused.value)


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
    worker_only = SRC / "execution" / "released_execution_bootstrap.py"  # worker process only (INAPP_TRADE_RELEASE.md)
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        for word in forbidden:
            if path.name == "settings.py" and word in {"AUTH_DISABLED", "BYPASS", "PRIVY_APP_SECRET"}:
                continue  # settings.py only lists them to refuse them
            if path == worker_only and word == "PRIVY_APP_SECRET":
                continue  # the worker-only value; the API role is refused before any read
            assert word not in text, f"{word} in {path.name}"
        tree = ast.parse(text)
        assert not any(isinstance(n, ast.Attribute) and n.attr == "dependency_overrides" for n in ast.walk(tree))


def test_the_api_process_never_loads_the_worker_secret_module(env, migrated):
    """The API process builds the app and enters startup without the worker-only bootstrap.

    A subprocess hides any import another test made. It also calls create_app and enters the ASGI lifespan, so a
    lazy import added to the factory or to startup is caught, not only one reached by importing main. The migrated
    fixture puts the schema at head, as create_app requires.
    """
    module = "edge_os_api.execution.released_execution_bootstrap"
    code = (
        "import asyncio, sys\n"
        "from edge_os_api.core.settings import load_settings\n"
        "from edge_os_api.main import create_app\n"
        f"assert {module!r} not in sys.modules\n"
        "app = create_app(load_settings())\n"
        f"assert {module!r} not in sys.modules, 'create_app loaded the worker-only bootstrap'\n"
        "async def startup():\n"
        "    async with app.router.lifespan_context(app):\n"
        "        pass\n"
        "asyncio.run(startup())\n"
        f"assert {module!r} not in sys.modules, 'startup loaded the worker-only bootstrap'\n"
    )
    child = {**env, "PYTHONPATH": str(SRC.parent)}
    run = subprocess.run([sys.executable, "-c", code], env=child, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_t9_cors_allow_list(client):
    allowed = client.options("/v1/me", headers={"Origin": "http://127.0.0.1:3999", "Access-Control-Request-Method": "GET",
                                                "Access-Control-Request-Headers": "authorization"})
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:3999"
    other = client.options("/v1/me", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in other.headers
    assert client.get("/healthz", headers={"Origin": "http://evil.example"}).headers.get("access-control-allow-origin") is None


def test_error_bodies_follow_the_contract_envelope(client, owner_a):
    from edge_os_api.records import contract_adapter as record_contract
    for response in (client.get("/nope"), client.get("/v1/me"), client.post("/v1/research/requests", json={}, headers=owner_a),
                     client.get("/v1/research/requests/not-a-uuid", headers=owner_a)):
        record_contract.validate_http_error(response.json())


def test_p02_inputs_are_frozen_and_checker_still_passes():
    from edge_os_api.records import contract_adapter as record_contract
    record_contract.verify_frozen_files()
    run = subprocess.run([sys.executable, "-I", str(record_contract.CHECKER_PATH)], capture_output=True, text=True)
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


# --- the public Hermes forward upstream (HERMES-ROUTE-L4) ---------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8011", "http://10.0.1.1:8011", "http://172.16.0.1:8011", "http://192.168.1.5:9000",
])
def test_hermes_app_url_accepts_a_loopback_or_rfc1918_http_literal(env, url):
    assert load_settings({**env, "EDGE_OS_HERMES_APP_URL": url}).hermes_app_url == url


def test_an_empty_hermes_app_url_means_none(env):
    assert load_settings({**env, "EDGE_OS_HERMES_APP_URL": ""}).hermes_app_url is None
    assert load_settings({**env, "EDGE_OS_HERMES_APP_URL": "   "}).hermes_app_url is None


@pytest.mark.parametrize("url", [
    "https://10.0.1.1:8011", "http://example.com:8011", "http://10.0.1.1", "http://10.0.1.1:8011/path",
    "http://10.0.1.1:8011?query=1", "http://10.0.1.1:8011#fragment", "http://user:pw@10.0.1.1:8011",
    "http://0.0.0.0:8011", "http://[::1]:8011", "http://[fd1a:b4ba:f96b::1]:8011", "http://8.8.8.8:8011",
    "http://169.254.1.1:8011", "http://10.0.1.1:0", "http://10.0.1.1:65536", "http://10.0.1.1:http",
])
def test_hermes_app_url_refuses_anything_else(env, url):
    with pytest.raises(ConfigError, match="hermes_app_url"):
        load_settings({**env, "EDGE_OS_HERMES_APP_URL": url})


def test_a_host_application_cannot_forward_to_another_host_application(env):
    with pytest.raises(ConfigError, match="hermes_app_url"):
        load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local",
                       "EDGE_OS_HERMES_APP_URL": "http://10.0.1.1:8011"})


def test_production_refuses_a_loopback_forward_upstream(env):
    prod = {**env, "EDGE_OS_ENV": "production", "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.example.com",
            "EDGE_OS_PRIVY_APP_ID": "real-app", "EDGE_OS_BUILD_SHA": "0123456789abcdef",
            "EDGE_OS_DATABASE_URL": "postgresql+psycopg://app@db.internal.example:5432/edge_os?sslmode=require"}
    with pytest.raises(ConfigError, match="hermes_app_url"):
        load_settings({**prod, "EDGE_OS_HERMES_APP_URL": "http://127.0.0.1:8011"})
    assert load_settings({**prod, "EDGE_OS_HERMES_APP_URL": "http://10.0.1.1:8011"}).hermes_app_url == \
        "http://10.0.1.1:8011"
