"""The Coolify production topology: private services, digest images, TLS and scoped settings."""

from __future__ import annotations

import json
import re

import pytest

import deploy_support as support

SERVICES = {"postgres", "migrate", "api", "web", "execution-worker", "recurring-producer"}
LONG_RUNNING = SERVICES - {"migrate"}
UNSET = "__EDGE_OS_UNSET__"

API_SETTINGS = {
    "EDGE_OS_ENV", "EDGE_OS_DATABASE_URL", "EDGE_OS_PRIVY_APP_ID", "EDGE_OS_PRIVY_VERIFICATION_KEY",
    "EDGE_OS_CORS_ALLOWED_ORIGINS", "EDGE_OS_BUILD_SHA", "EDGE_OS_INTERPRETER", "EDGE_OS_WALLET_PROVIDER",
    "EDGE_OS_EXECUTION_MODE", "EDGE_OS_RESEARCH_HISTORY_MODE", "EDGE_OS_RESEARCH_SOURCE_CLIENTS",
    "EDGE_OS_NANSEN_RESEARCH_MODE", "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS",
    "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS", "EDGE_OS_RESEARCH_BUDGET_NANSEN_CREDITS",
    "EDGE_OS_USAGE_GLOBAL_PROVIDER_REQUESTS", "EDGE_OS_USAGE_GLOBAL_COMPUTE_SECONDS",
    "EDGE_OS_USAGE_GLOBAL_NANSEN_CREDITS", "EDGE_OS_WRITE_RATE_PER_MINUTE", "EDGE_OS_RESEARCH_MAX_ACTIVE_JOBS",
    "EDGE_OS_DATABASE_STATEMENT_TIMEOUT_MS",
}
POSTGRES_MASKS = {"EDGE_OS_DATABASE_URL", "EDGE_OS_PRIVY_APP_ID", "EDGE_OS_PRIVY_VERIFICATION_KEY",
                  "EDGE_OS_CORS_ALLOWED_ORIGINS", "EDGE_OS_BUILD_SHA"}
MIGRATE_MASKS = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "EDGE_OS_ENV", "EDGE_OS_PRIVY_APP_ID",
                 "EDGE_OS_PRIVY_VERIFICATION_KEY", "EDGE_OS_CORS_ALLOWED_ORIGINS", "EDGE_OS_BUILD_SHA"}
API_MASKS = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}
WEB_MASKS = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "EDGE_OS_ENV", "EDGE_OS_DATABASE_URL",
             "EDGE_OS_PRIVY_APP_ID", "EDGE_OS_PRIVY_VERIFICATION_KEY", "EDGE_OS_CORS_ALLOWED_ORIGINS",
             "EDGE_OS_BUILD_SHA"}
# The execution worker has its own block: only the settings `load_settings()` requires and the worker reads. It never
# shares the API block, so no research, budget or interpreter value and no future API-only name reaches it.
WORKER_SETTINGS = {
    "EDGE_OS_ENV", "EDGE_OS_DATABASE_URL", "EDGE_OS_PRIVY_APP_ID", "EDGE_OS_PRIVY_VERIFICATION_KEY",
    "EDGE_OS_CORS_ALLOWED_ORIGINS", "EDGE_OS_BUILD_SHA", "EDGE_OS_EXECUTION_MODE",
    "EDGE_OS_DATABASE_STATEMENT_TIMEOUT_MS",
}
POSTGRES_ALIAS = "edge-os-postgres"
EGRESS_BRIDGE = "edgeos-egress"
ENV_ALLOW = {
    "postgres": {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"} | POSTGRES_MASKS,
    "migrate": {"EDGE_OS_DATABASE_URL"} | MIGRATE_MASKS,
    "api": API_SETTINGS | API_MASKS,
    "web": WEB_MASKS,
    "execution-worker": WORKER_SETTINGS | API_MASKS,
    "recurring-producer": API_SETTINGS | API_MASKS,
}
SECRET_OWNERS = {
    "POSTGRES_PASSWORD": {"postgres"},
    "POSTGRES_USER": {"postgres"},
    "POSTGRES_DB": {"postgres"},
    "EDGE_OS_DATABASE_URL": {"migrate", "api", "execution-worker", "recurring-producer"},
    "EDGE_OS_PRIVY_VERIFICATION_KEY": {"api", "execution-worker", "recurring-producer"},
}


@pytest.fixture(scope="module")
def compose():
    return support.compose_model(str(support.COMPOSE_COOLIFY))


def test_services_are_the_reviewed_set(compose):
    assert set(compose["services"]) == SERVICES


@pytest.mark.parametrize("name", sorted(SERVICES - {"postgres"}))
def test_no_other_service_publishes_a_host_port(compose, name):
    assert "ports" not in compose["services"][name]


def test_postgres_is_published_on_loopback_only_for_the_host_research_worker(compose):
    ports = compose["services"]["postgres"]["ports"]
    assert len(ports) == 1
    port = ports[0]
    assert port["host_ip"] == "127.0.0.1"
    assert str(port["published"]) == "5432"
    assert port["target"] == 5432
    assert port.get("protocol", "tcp") == "tcp"
    text = support.COMPOSE_COOLIFY.read_text(encoding="utf-8")
    assert "0.0.0.0" not in text
    assert not re.search(r'(?m)^\s*-\s*"?5432(:5432)?"?\s*$', text)


def test_postgres_has_a_unique_alias_that_cannot_collide_with_coolify(compose):
    postgres = compose["services"]["postgres"]
    assert set(postgres["networks"]) == {"private", "hostdb"}
    assert postgres["networks"]["private"]["aliases"] == [POSTGRES_ALIAS]
    assert "aliases" not in (postgres["networks"]["hostdb"] or {})
    text = support.COMPOSE_COOLIFY.read_text(encoding="utf-8")
    assert f"@{POSTGRES_ALIAS}:5432/" in text
    assert "@postgres:" not in text


def test_only_the_execution_worker_joins_the_egress_network(compose):
    egress = compose["networks"]["egress"]
    assert egress.get("internal") is not True
    assert egress["driver"] == "bridge"
    assert egress["driver_opts"]["com.docker.network.bridge.name"] == EGRESS_BRIDGE
    assert egress["ipam"]["config"] == [{"subnet": "10.203.0.0/28"}]
    assert egress["enable_ipv6"] is False
    members = {name for name, service in compose["services"].items() if "egress" in service["networks"]}
    assert members == {"execution-worker"}


def test_the_loopback_publish_network_has_no_route_out_and_only_postgres(compose):
    hostdb = compose["networks"]["hostdb"]
    assert hostdb["driver"] == "bridge"
    assert hostdb["driver_opts"]["com.docker.network.bridge.name"] == "edgeos-hostdb"
    assert hostdb["driver_opts"]["com.docker.network.bridge.enable_ip_masquerade"] == "false"
    assert hostdb["ipam"]["config"] == [{"subnet": "10.203.0.16/28"}]
    assert hostdb["enable_ipv6"] is False
    members = {name for name, service in compose["services"].items() if "hostdb" in service["networks"]}
    assert members == {"postgres"}


def test_the_execution_worker_does_not_merge_the_api_environment():
    text = support.COMPOSE_COOLIFY.read_text(encoding="utf-8")
    worker = text.split("  execution-worker:", 1)[1].split("\n  recurring-producer:", 1)[0]
    assert "*api-environment" not in worker
    assert "x-worker-environment: &worker-environment" in text
    assert "environment: *worker-environment" in worker


def test_only_the_web_and_api_ports_are_exposed(compose):
    assert compose["services"]["api"]["expose"] == ["8000"]
    assert compose["services"]["web"]["expose"] == ["3000"]
    for name in SERVICES - {"api", "web"}:
        assert "expose" not in compose["services"][name]


def test_no_service_mounts_the_docker_socket(compose):
    rendered = json.dumps(compose)
    assert "docker.sock" not in rendered
    assert "docker.sock" not in support.COMPOSE_COOLIFY.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_every_image_is_a_required_digest_variable(compose, name):
    service = compose["services"][name]
    assert "build" not in service
    assert re.fullmatch(r"\$\{EDGE_OS_[A-Z_]+_IMAGE:\?[^}]+\}", service["image"]), service["image"]


def test_the_web_public_values_are_not_runtime_settings(compose):
    web = compose["services"]["web"]
    assert "build" not in web
    assert support.environment_names(web) == WEB_MASKS


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_every_service_keeps_the_hardening(compose, name):
    service = compose["services"][name]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service.get("init") is True
    assert service.get("tmpfs")
    assert service.get("mem_limit")


def test_postgres_starts_as_the_image_user_under_cap_drop_all(compose):
    """The entrypoint cannot chown the data and socket folders without root capabilities."""
    postgres = compose["services"]["postgres"]
    assert postgres["cap_drop"] == ["ALL"]
    assert postgres["user"] == "999:999"
    assert "uid=999,gid=999" in " ".join(postgres["tmpfs"])


@pytest.mark.parametrize("name", sorted(LONG_RUNNING))
def test_long_running_services_have_a_healthcheck(compose, name):
    assert "healthcheck" in compose["services"][name]


def test_postgres_health_check_proves_tls_is_on(compose):
    health = compose["services"]["postgres"]["healthcheck"]
    text = " ".join(health["test"])
    assert "pg_isready" in text
    assert "show ssl" in text


def test_postgres_runs_with_tls_from_a_read_only_mount(compose):
    postgres = compose["services"]["postgres"]
    command = support.command_text(postgres)
    assert "ssl=on" in command
    assert "ssl_cert_file=/etc/edge-os/postgres-tls/server.crt" in command
    assert "ssl_key_file=/etc/edge-os/postgres-tls/server.key" in command
    mounts = support.mounts(postgres)
    tls = [mount for mount in mounts if "postgres-tls" in mount["target"]]
    assert len(tls) == 1
    assert tls[0]["source"] == "/etc/edge-os/postgres-tls"
    assert tls[0]["read_only"] is True
    assert "EDGE_OS_POSTGRES_TLS_DIR" not in support.COMPOSE_COOLIFY.read_text(encoding="utf-8")
    database = [mount for mount in mounts if mount["target"] == "/var/lib/postgresql"]
    assert len(database) == 1


def test_the_migration_is_one_explicit_service(compose):
    migrate = compose["services"]["migrate"]
    assert migrate["restart"] == "no"
    command = support.command_text(migrate)
    assert "alembic upgrade head" in command
    assert "alembic check" in command
    assert "profiles" not in migrate
    for name in ("api", "execution-worker", "recurring-producer"):
        assert compose["services"][name]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"


def test_the_api_and_workers_wait_for_postgres_and_migration(compose):
    for name in ("api", "execution-worker", "recurring-producer"):
        depends = compose["services"][name]["depends_on"]
        assert depends["postgres"]["condition"] == "service_healthy"
    assert compose["services"]["web"]["depends_on"]["api"]["condition"] == "service_healthy"


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_each_service_gets_only_its_own_environment_names(compose, name):
    assert support.environment_names(compose["services"][name]) == ENV_ALLOW[name]


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_foreign_secrets_are_masked(compose, name):
    values = support.environment_values(compose["services"][name])
    for secret, owners in SECRET_OWNERS.items():
        if name in owners or secret not in values:
            continue
        assert values[secret] == UNSET, f"{secret} is not masked on {name}"


def test_production_modes_are_pinned(compose):
    values = support.environment_values(compose["services"]["api"])
    assert values["EDGE_OS_ENV"] == "production"
    assert values["EDGE_OS_INTERPRETER"] == "fixture"
    assert values["EDGE_OS_WALLET_PROVIDER"] == "unavailable"
    assert values["EDGE_OS_EXECUTION_MODE"] == "unavailable"
    assert values["EDGE_OS_RESEARCH_HISTORY_MODE"] == "unavailable"
    assert values["EDGE_OS_RESEARCH_SOURCE_CLIENTS"] == "recorded"
    assert values["EDGE_OS_NANSEN_RESEARCH_MODE"] == "unavailable"
    worker = support.environment_values(compose["services"]["execution-worker"])
    assert worker["EDGE_OS_ENV"] == "production"
    assert worker["EDGE_OS_EXECUTION_MODE"] == "unavailable"


def test_the_workers_use_a_heartbeat_command(compose):
    heartbeat = {
        "execution-worker": "/tmp/edge-os-worker-heartbeat",
        "recurring-producer": "/tmp/edge-os-recurring-heartbeat",
    }
    for name, path in heartbeat.items():
        text = support.command_text(compose["services"][name])
        assert "--once" in text
        assert path in text
        health = " ".join(compose["services"][name]["healthcheck"]["test"])
        assert path in health


def test_api_and_web_join_the_proxy_network(compose):
    for name in ("api", "web"):
        assert set(compose["services"][name]["networks"]) == {"private", "coolify"}
    for name in ("migrate", "recurring-producer"):
        assert set(compose["services"][name]["networks"]) == {"private"}
    assert set(compose["services"]["postgres"]["networks"]) == {"private", "hostdb"}
    assert set(compose["services"]["execution-worker"]["networks"]) == {"private", "egress"}
    assert compose["networks"]["private"]["internal"] is True
    assert compose["networks"]["private"]["driver_opts"]["com.docker.network.bridge.name"] == "edgeos-private"
    assert compose["networks"]["private"]["ipam"]["config"] == [{"subnet": "10.203.0.64/26"}]
    assert compose["networks"]["coolify"]["external"] is True


def test_the_compose_file_holds_no_secret_value(compose):
    text = support.COMPOSE_COOLIFY.read_text(encoding="utf-8")
    assert "BEGIN PRIVATE KEY" not in text
    assert "BEGIN RSA" not in text
    assert not re.search(r"postgresql\+psycopg://[^:\s]+:(?!\$\{)[^@\s]+@", text)
    assert not re.search(
        r"(?im)^\s*(POSTGRES_PASSWORD|EDGE_OS_DATABASE_URL):\s*(?!\$\{|__EDGE_OS_UNSET__)\S", text)
