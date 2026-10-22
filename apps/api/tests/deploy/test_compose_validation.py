"""Full Compose validation with explicit placeholder values. No secret and no network."""

from __future__ import annotations

import deploy_support as support

DUMMY = "0" * 64


def coolify_values() -> dict[str, str]:
    return {
        "EDGE_OS_API_IMAGE": f"ghcr.io/edge-os-app/edge-os-api@sha256:{DUMMY}",
        "EDGE_OS_WEB_IMAGE": f"ghcr.io/edge-os-app/edge-os-web@sha256:{DUMMY}",
        "EDGE_OS_POSTGRES_IMAGE": f"postgres:18.6-trixie@sha256:{DUMMY}",
        "EDGE_OS_DATABASE_URL": "postgresql+psycopg://edge_os:placeholder@postgres:5432/edge_os?sslmode=require",
        "POSTGRES_PASSWORD": "placeholder",
        "POSTGRES_DB": "edge_os",
        "EDGE_OS_PRIVY_APP_ID": "placeholder",
        "EDGE_OS_PRIVY_VERIFICATION_KEY": "placeholder",
        "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.edgeos.fun",
        "EDGE_OS_BUILD_SHA": "0" * 40,
        "EDGE_OS_POSTGRES_TLS_DIR": "/etc/edge-os/postgres-tls",
    }


def host_proxy_values() -> dict[str, str]:
    return {
        "EDGE_OS_SOCKET_PROXY_IMAGE": f"wollomatic/socket-proxy@sha256:{DUMMY}",
        "EDGE_OS_PROXY_RESEARCH_UID": "10001",
        "EDGE_OS_RESEARCH_GID": "10001",
        "EDGE_OS_PROXY_RELAY_UID": "10002",
        "EDGE_OS_RELAY_GID": "10002",
        "EDGE_OS_DOCKER_GID": "999",
    }


def test_the_coolify_compose_validates_with_placeholder_values():
    support.validate_compose(support.COMPOSE_COOLIFY, coolify_values())


def test_the_host_proxy_compose_validates_with_placeholder_values():
    support.validate_compose(support.HOST_PROXY_COMPOSE, host_proxy_values())
