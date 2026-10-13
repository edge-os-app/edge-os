"""compose.local.yml: private topology, explicit configuration mapping, the serialized migration and secret ownership.

The model is read with `docker compose config --format json` (the Compose CLI parses it; no daemon is needed) using
dummy, non-secret values for the required variables.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from edge_os_api.core.settings import FORBIDDEN_ENV_NAMES, ConfigError, load_settings

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "compose.local.yml"
PYTHON_ROLES = {"migrate", "api", "entry", "research-worker", "execution-worker", "recurring-producer"}
WORKERS = {
    "research-worker": ["python", "-m", "edge_os_api.research.investigation_jobs", "--interval", "2"],
    "execution-worker": ["python", "-m", "edge_os_api.execution.worker", "--interval", "2"],
    "recurring-producer": ["python", "-m", "edge_os_api.execution.recurring_producer", "--interval", "30"],
}
APPLICATION_SETTINGS = {
    "EDGE_OS_ENV", "EDGE_OS_DATABASE_URL", "EDGE_OS_PRIVY_APP_ID", "EDGE_OS_PRIVY_VERIFICATION_KEY",
    "EDGE_OS_CORS_ALLOWED_ORIGINS", "EDGE_OS_BUILD_SHA", "EDGE_OS_INTERPRETER", "EDGE_OS_WALLET_PROVIDER",
    "EDGE_OS_EXECUTION_MODE", "EDGE_OS_FIXTURE_EFFECTS_PATH", "EDGE_OS_RESEARCH_HISTORY_MODE",
    "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS", "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS",
}
DB_PASSWORD = "dummy-password-for-config-test"


def _public_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1()).public_key()
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


PUBLIC_PEM = _public_pem()
VARIABLES = {
    "EDGE_OS_LOCAL_RUN_ID": "cfgtest", "EDGE_OS_LOCAL_PUBLIC_PORT": "18999", "EDGE_OS_LOCAL_DB_NAME": "edge_os_local_cfgtest",
    "EDGE_OS_LOCAL_DB_PASSWORD": DB_PASSWORD, "EDGE_OS_LOCAL_VERIFICATION_KEY": PUBLIC_PEM.replace("\n", "\\n"),
    "EDGE_OS_LOCAL_BUILD_SHA": "0" * 40,
}

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="the Docker Compose CLI is required")


def _config(variables: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/tmp"), **variables}
    return subprocess.run(["docker", "compose", "-f", str(COMPOSE), "-p", "edge-os-local-cfgtest", "--profile", "migrate",
                           "--profile", "workers", "config", "--format", "json"],
                          capture_output=True, text=True, env=env, timeout=60, check=False)


@pytest.fixture(scope="module")
def model() -> dict[str, Any]:
    result = _config(VARIABLES)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_every_expected_role_and_nothing_else(model) -> None:
    assert set(model["services"]) == {"postgres", "migrate", "api", "web", "entry", *WORKERS}


def test_only_the_entry_publishes_one_loopback_port(model) -> None:
    published = {name: service["ports"] for name, service in model["services"].items() if service.get("ports")}
    assert list(published) == ["entry"]
    [port] = published["entry"]
    assert port["host_ip"] == "127.0.0.1" and port["published"] == "18999" and port["target"] == 8080
    for service in model["services"].values():
        assert not service.get("expose")


def test_application_database_and_workers_have_no_route_out(model) -> None:
    assert model["networks"]["private"].get("internal") is True
    for name, service in model["services"].items():
        expected = {"private", "entry"} if name == "entry" else {"private"}
        assert set(service["networks"]) == expected, name
        assert "network_mode" not in service and not service.get("privileged") and "pid" not in service


def test_no_docker_socket_host_path_or_env_file_anywhere(model) -> None:
    for name, service in model["services"].items():
        assert "env_file" not in service, name
        for volume in service.get("volumes", []):
            assert volume["type"] == "volume", f"{name} mounts a host path"
            assert "docker.sock" not in json.dumps(volume)
    assert "docker.sock" not in COMPOSE.read_text()


def test_forbidden_authentication_names_never_appear() -> None:
    text = COMPOSE.read_text()
    for name in FORBIDDEN_ENV_NAMES:
        assert name not in text
    assert "SECRET" not in text.upper().replace("NOTHING SECRET", "").replace("NEVER A PRIVY SECRET", "")


def test_database_password_reaches_only_postgres_and_the_composed_url(model) -> None:
    for name, service in model["services"].items():
        environment = service.get("environment") or {}
        holders = {key for key, value in environment.items() if DB_PASSWORD in str(value)}
        if name == "postgres":
            assert holders == {"POSTGRES_PASSWORD"}
        elif name in {"migrate", "api", *WORKERS}:
            assert holders == {"EDGE_OS_DATABASE_URL"}, name
            assert not any(key.startswith("POSTGRES_") for key in environment), name
        else:
            assert holders == set(), name
        assert DB_PASSWORD not in json.dumps(service.get("build", {})), name


def test_settings_are_named_one_by_one_and_load_under_the_accepted_rules(model) -> None:
    api = model["services"]["api"]["environment"]
    assert set(api) == APPLICATION_SETTINGS
    assert api["EDGE_OS_ENV"] == "local" and api["EDGE_OS_PRIVY_APP_ID"] == "edge-os-test-app"
    assert api["EDGE_OS_CORS_ALLOWED_ORIGINS"] == "http://127.0.0.1:18999"
    settings = load_settings(dict(api))
    assert settings.env == "local" and settings.interpreter == "fixture"
    for name in WORKERS:
        worker = model["services"][name]["environment"]
        differs = {key for key in APPLICATION_SETTINGS if worker.get(key) != api.get(key)}
        assert set(worker) == APPLICATION_SETTINGS
        assert differs == ({"EDGE_OS_FIXTURE_EFFECTS_PATH"} if name == "recurring-producer" else set()), name
    assert set(model["services"]["migrate"]["environment"]) == {"EDGE_OS_DATABASE_URL"}


@pytest.mark.parametrize("name", FORBIDDEN_ENV_NAMES)
def test_the_composed_settings_still_refuse_a_forbidden_name(model, name: str) -> None:
    with pytest.raises(ConfigError, match="unsupported configuration present"):
        load_settings({**model["services"]["api"]["environment"], name: "1"})


def test_the_local_fixture_profile_is_refused_as_production(model) -> None:
    production = {**model["services"]["api"]["environment"], "EDGE_OS_ENV": "production"}
    with pytest.raises(ConfigError) as refused:
        load_settings(production)
    message = str(refused.value)
    # The composed host `postgres` is not loopback, so the hosted-database rule passes; the TLS rule still refuses.
    for field in ("database_url: production needs sslmode=require", "fixture effects are refused",
                  "wallet_provider", "execution_mode", "research_history_mode", "the test app id is refused",
                  "production origins must use https"):
        assert field in message
    assert DB_PASSWORD not in message and "BEGIN PUBLIC KEY" not in message


def test_web_receives_public_build_values_only(model) -> None:
    web = model["services"]["web"]
    assert not web.get("environment")
    assert set(web["build"]["args"]) == {"EDGE_OS_SOURCE_COMMIT", "NEXT_PUBLIC_API_BASE_URL", "NEXT_PUBLIC_PRIVY_APP_ID"}
    assert web["build"]["args"]["NEXT_PUBLIC_API_BASE_URL"] == "http://127.0.0.1:18999"
    assert web["build"]["args"]["NEXT_PUBLIC_PRIVY_APP_ID"] == "edge-os-test-app"
    assert web["build"]["dockerfile"] == "apps/web/Dockerfile"


def test_migration_is_one_explicit_step_that_nothing_starts_implicitly(model) -> None:
    migrate = model["services"]["migrate"]
    assert migrate["profiles"] == ["migrate"] and migrate["restart"] == "no"
    assert migrate["command"] == ["sh", "-c", "python -m alembic upgrade head && python -m alembic check"]
    for name, service in model["services"].items():
        assert "migrate" not in (service.get("depends_on") or {}), name
        if name != "migrate":
            assert "alembic" not in json.dumps(service.get("command") or []), name


def test_readiness_gates_the_entry(model) -> None:
    api, web, entry = (model["services"][name] for name in ("api", "web", "entry"))
    assert api["healthcheck"]["test"][-1] == "http://127.0.0.1:8000/readyz"
    assert "http://127.0.0.1:3000/" in web["healthcheck"]["test"][-1]
    assert entry["depends_on"]["api"]["condition"] == "service_healthy"
    assert entry["depends_on"]["web"]["condition"] == "service_healthy"
    assert entry["environment"] == {"ENTRY_API_UPSTREAM": "api:8000", "ENTRY_WEB_UPSTREAM": "web:3000",
                                    "ENTRY_LISTEN": "0.0.0.0:8080"}


def test_workers_are_the_existing_bounded_commands_and_start_only_when_named(model) -> None:
    for name, command in WORKERS.items():
        service = model["services"][name]
        assert service["command"] == command and service["profiles"] == ["workers"], name
        assert service["image"] == "edge-os-local-api:cfgtest" and "build" not in service


def test_application_containers_are_hardened_and_non_root_images_are_used(model) -> None:
    for name in PYTHON_ROLES | {"web"}:
        service = model["services"][name]
        assert service["read_only"] is True and service["cap_drop"] == ["ALL"], name
        assert service["security_opt"] == ["no-new-privileges:true"] and service["init"] is True, name
        assert not service.get("user"), f"{name} must keep the image's non-root user"
    assert model["services"]["postgres"]["image"].startswith("postgres:18.6-trixie@sha256:")


def test_every_resource_carries_the_run_label(model) -> None:
    for kind in ("services", "networks", "volumes"):
        for name, item in model[kind].items():
            assert item["labels"]["edge-os.rehearsal.run"] == "cfgtest", f"{kind}.{name}"
            assert item["labels"]["edge-os.profile"] == "LOCAL", f"{kind}.{name}"


@pytest.mark.parametrize("missing", sorted(VARIABLES))
def test_a_missing_required_value_fails_closed(missing: str) -> None:
    result = _config({key: value for key, value in VARIABLES.items() if key != missing})
    assert result.returncode != 0 and missing in result.stderr
    assert DB_PASSWORD not in result.stderr
