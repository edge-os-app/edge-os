"""The production settings contract the Compose file must satisfy. Pure; no database, Docker or network."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from edge_os_api.core.settings import ConfigError, load_settings


def _public_key() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("utf-8")


def production_env() -> dict[str, str]:
    return {
        "EDGE_OS_ENV": "production",
        "EDGE_OS_DATABASE_URL": "postgresql+psycopg://edge_os:not-a-real-password@edge-os-postgres:5432/edge_os?sslmode=require",
        "EDGE_OS_PRIVY_APP_ID": "clz-production-example",
        "EDGE_OS_PRIVY_VERIFICATION_KEY": _public_key(),
        "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.edgeos.fun",
        "EDGE_OS_BUILD_SHA": "0" * 40,
        "EDGE_OS_INTERPRETER": "fixture",
        "EDGE_OS_WALLET_PROVIDER": "unavailable",
        "EDGE_OS_EXECUTION_MODE": "unavailable",
        "EDGE_OS_RESEARCH_HISTORY_MODE": "unavailable",
        "EDGE_OS_RESEARCH_SOURCE_CLIENTS": "recorded",
        "EDGE_OS_NANSEN_RESEARCH_MODE": "unavailable",
    }


def test_the_production_contract_loads():
    settings = load_settings(production_env())
    assert settings.env == "production"
    assert settings.cors_origins == ["https://app.edgeos.fun"]


@pytest.mark.parametrize("change,reason", [
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@edge-os-postgres:5432/edge_os"}, "sslmode"),
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@edge-os-postgres:5432/edge_os?sslmode=disable"}, "sslmode"),
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:5432/edge_os?sslmode=require"}, "loopback"),
    ({"EDGE_OS_CORS_ALLOWED_ORIGINS": "http://app.edgeos.fun"}, "https"),
    ({"EDGE_OS_CORS_ALLOWED_ORIGINS": "*"}, "wildcard"),
    ({"EDGE_OS_PRIVY_APP_ID": "edge-os-test-app"}, "test app id"),
    ({"EDGE_OS_WALLET_PROVIDER": "fixture"}, "wallet_provider"),
    ({"EDGE_OS_EXECUTION_MODE": "fixture"}, "execution_mode"),
    ({"EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"}, "research_history_mode"),
    ({"EDGE_OS_RESEARCH_SOURCE_CLIENTS": "authored_http"}, "research_source_clients"),
    ({"EDGE_OS_NANSEN_RESEARCH_MODE": "authored_fixture"}, "nansen_research_mode"),
    ({"EDGE_OS_BUILD_SHA": ""}, "build_sha"),
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@postgres:5432/edge_os?sslmode=require"},
     "Coolify's own database alias"),
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@POSTGRES:5432/edge_os?sslmode=require"},
     "Coolify's own database alias"),
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@postgres.:5432/edge_os?sslmode=require"},
     "Coolify's own database alias"),
    ({"EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@coolify-db:5432/edge_os?sslmode=require"},
     "Coolify's own database alias"),
    ({"EDGE_OS_DATABASE_URL":
      "postgresql+psycopg://u:p@edge-os-postgres:5432/edge_os?sslmode=require&host=postgres"},
     "host or hostaddr query parameters"),
    ({"EDGE_OS_DATABASE_URL":
      "postgresql+psycopg://u:p@edge-os-postgres:5432/edge_os?sslmode=require&hostaddr=127.0.0.1"},
     "host or hostaddr query parameters"),
    ({"EDGE_OS_EXECUTION_MODE": "controlled"}, "controlled execution needs an approved hosted deployment"),
])
def test_production_refusals_stay_in_force(change, reason):
    with pytest.raises(ConfigError) as caught:
        load_settings({**production_env(), **change})
    assert reason in str(caught.value)
    assert "not-a-real-password" not in str(caught.value)


def test_a_forbidden_name_is_refused_without_its_value():
    with pytest.raises(ConfigError) as caught:
        load_settings({**production_env(), "EDGE_OS_PRIVY_APP_SECRET": "do-not-print"})
    assert "unsupported configuration present" in str(caught.value)
    assert "EDGE_OS_PRIVY_APP_SECRET" in str(caught.value)
    assert "do-not-print" not in str(caught.value)


def test_the_approval_registry_pins_the_approved_record():
    from edge_os_api.core import hosted_deployment

    assert dict(hosted_deployment.APPROVED_HOSTED_DEPLOYMENTS) == {
        "edgeos-fun-vps1": "1b169e7b794150a161b2e59fd8184e7d2af6cb3eb90396da6ea8909807e7d0d9"}
