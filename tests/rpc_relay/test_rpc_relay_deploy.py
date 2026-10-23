"""The relay's image, Compose service, Traefik routing, egress firewall rule and document. No daemon, no network."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from relay_support import RELAY, REPO

COMPOSE = RELAY / "compose.rpc-relay.yml"
DOCKERFILE = RELAY / "Dockerfile"
DOCKERIGNORE = RELAY / ".dockerignore"
FIREWALL = REPO / "deploy" / "host" / "edge-os-egress-firewall.sh"
DOC = REPO / "docs" / "qualification" / "inapp-trade" / "RPC_RELAY.md"
RUNBOOK = REPO / "docs" / "qualification" / "hosted-gates" / "HOSTED_RECORD_V2_RUNBOOK.md"
API_DOCKERFILE = REPO / "deploy" / "docker" / "api.Dockerfile"
OBSERVER_HOST, BROADCAST_HOST = "rpc-a.edgeos.fun", "rpc-b.edgeos.fun"

needs_compose = pytest.mark.skipif(shutil.which("docker") is None, reason="the Docker Compose CLI is required")


def compose_model() -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as empty:
        empty_path = empty.name
    try:
        completed = subprocess.run(
            ["docker", "compose", "--project-directory", str(RELAY), "--env-file", empty_path, "-f", str(COMPOSE),
             "config", "--no-interpolate", "--format", "json"],
            capture_output=True, text=True, timeout=60, cwd=RELAY,
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")})
    finally:
        Path(empty_path).unlink(missing_ok=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def validate(values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as empty:
        empty_path = empty.name
    try:
        return subprocess.run(
            ["docker", "compose", "--project-directory", str(RELAY), "--env-file", empty_path, "-f", str(COMPOSE),
             "config", "--quiet"],
            capture_output=True, text=True, timeout=60, cwd=RELAY,
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), **values})
    finally:
        Path(empty_path).unlink(missing_ok=True)


VALUES = {
    "EDGE_OS_RPC_RELAY_UPSTREAM_URL": "https://placeholder.invalid/placeholder-key/",
    "EDGE_OS_RPC_RELAY_SOURCE_COMMIT": "0" * 40,
    "EDGE_OS_RPC_RELAY_ALLOWED_SOURCES": "10.0.1.1/32",
}


@pytest.fixture(scope="module")
def service() -> dict[str, Any]:
    model = compose_model()
    assert set(model["services"]) == {"rpc-relay"}
    return model["services"]["rpc-relay"] | {"__networks": model["networks"]}


def labels(service: dict[str, Any]) -> dict[str, str]:
    value = service.get("labels") or {}
    if isinstance(value, list):
        return dict(item.split("=", 1) for item in value)
    return dict(value)


@needs_compose
def test_the_compose_file_validates_and_refuses_each_missing_value():
    assert validate(VALUES).returncode == 0
    for name in VALUES:
        missing = {k: v for k, v in VALUES.items() if k != name}
        completed = validate(missing)
        assert completed.returncode != 0, name
        assert name in completed.stderr


@needs_compose
def test_the_relay_keeps_the_stack_hardening(service):
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["init"] is True
    assert service["user"] == "10001:10001"
    assert service.get("tmpfs")
    assert service["mem_limit"]
    # Threads count against pids: 2 x MAX_CONNECTIONS handlers, 3 server threads, init, and headroom.
    assert int(service["pids_limit"]) >= 2 * 32 + 3 + 1 + 32
    assert service["restart"] == "unless-stopped"
    assert "ports" not in service
    assert sorted(service["expose"]) == ["8545", "8546"]


@needs_compose
def test_the_relay_receives_only_its_own_settings(service):
    environment = service["environment"]
    assert set(environment) == {"EDGE_OS_RPC_RELAY_UPSTREAM_URL", "EDGE_OS_RPC_RELAY_TRUSTED_PROXY"}
    assert re.fullmatch(r"\$\{EDGE_OS_RPC_RELAY_UPSTREAM_URL:\?[^}]+\}", environment["EDGE_OS_RPC_RELAY_UPSTREAM_URL"])
    assert environment["EDGE_OS_RPC_RELAY_TRUSTED_PROXY"] == "coolify-proxy"


@needs_compose
def test_the_relay_is_built_from_its_own_folder_and_tagged_by_commit(service):
    assert service["build"]["context"] in (".", str(RELAY))
    assert service["build"]["dockerfile"] == "Dockerfile"
    assert service["image"] == "edge-os-rpc-relay:${EDGE_OS_RPC_RELAY_SOURCE_COMMIT:?set EDGE_OS_RPC_RELAY_SOURCE_COMMIT to the deployed source commit}"
    assert service["build"]["args"]["EDGE_OS_SOURCE_COMMIT"].startswith("${EDGE_OS_RPC_RELAY_SOURCE_COMMIT")


@needs_compose
def test_the_relay_joins_only_the_proxy_network(service):
    assert set(service["networks"]) == {"coolify"}
    networks = service["__networks"]
    assert set(networks) == {"coolify"}
    assert networks["coolify"]["external"] is True


@needs_compose
def test_the_health_check_reads_both_local_health_endpoints(service):
    text = " ".join(service["healthcheck"]["test"])
    assert "127.0.0.1:8545/healthz" in text and "127.0.0.1:8546/healthz" in text


@needs_compose
def test_traefik_routes_one_host_to_each_role_over_https_only(service):
    found = labels(service)
    assert found["traefik.enable"] == "true"
    assert found["traefik.docker.network"] == "${COOLIFY_NETWORK:-coolify}"
    routers = {key.split(".")[3] for key in found if key.startswith("traefik.http.routers.")}
    assert routers == {"edgeos-rpc-observer", "edgeos-rpc-broadcast"}
    for router, host, port in (("edgeos-rpc-observer", OBSERVER_HOST, "8545"),
                               ("edgeos-rpc-broadcast", BROADCAST_HOST, "8546")):
        prefix = f"traefik.http.routers.{router}"
        assert found[f"{prefix}.rule"] == f"Host(`{host}`) && Path(`/rpc`) && Method(`POST`)"
        assert found[f"{prefix}.entrypoints"] == "https"
        assert found[f"{prefix}.tls"] == "true"
        assert found[f"{prefix}.tls.certresolver"] == "letsencrypt"
        assert found[f"{prefix}.service"] == router
        assert found[f"{prefix}.middlewares"] == "edgeos-rpc-allow,edgeos-rpc-body"
        assert found[f"traefik.http.services.{router}.loadbalancer.server.port"] == port
    assert found["traefik.http.middlewares.edgeos-rpc-allow.ipallowlist.sourcerange"] == (
        "${EDGE_OS_RPC_RELAY_ALLOWED_SOURCES:?set EDGE_OS_RPC_RELAY_ALLOWED_SOURCES to the worker's source range}")
    assert found["traefik.http.middlewares.edgeos-rpc-body.buffering.maxRequestBodyBytes"] == "32768"
    assert not any(".entrypoints" in key and value == "http" for key, value in found.items())


def test_the_compose_file_holds_no_secret_value():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "quiknode" not in text.lower() and "quicknode.pro" not in text.lower()
    assert not re.search(r"(?m)^\s*EDGE_OS_RPC_RELAY_UPSTREAM_URL:\s*(?!\$\{)\S", text)
    assert "docker.sock" not in text


def test_the_image_is_pinned_non_root_and_holds_only_the_relay():
    text = DOCKERFILE.read_text(encoding="utf-8")
    pinned = re.search(r"(?m)^ARG PYTHON_IMAGE=(\S+)$", API_DOCKERFILE.read_text(encoding="utf-8")).group(1)
    assert f"ARG PYTHON_IMAGE={pinned}" in text and "@sha256:" in pinned
    assert re.findall(r"(?m)^COPY .*$", text) == ["COPY rpc_relay.py /app/rpc_relay.py"]
    assert "USER 10001:10001" in text
    assert re.search(r'(?m)^CMD \["python", "-I", "/app/rpc_relay.py"\]$', text)
    assert "pip install" not in text and "ENV EDGE_OS_RPC_RELAY_UPSTREAM_URL" not in text
    assert "ARG EDGE_OS_PROFILE=LOCAL" in text and 'edge-os.profile="${EDGE_OS_PROFILE}"' in text
    ignore = [line for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    assert ignore == ["*", "!Dockerfile", "!rpc_relay.py"]


def test_the_relay_uses_the_standard_library_only():
    text = (RELAY / "rpc_relay.py").read_text(encoding="utf-8")
    imports = set(re.findall(r"(?m)^(?:from|import) ([a-zA-Z_][\w]*)", text))
    assert imports <= {"__future__", "dataclasses", "hmac", "http", "ipaddress", "json", "math", "os", "re",
                       "signal", "socket", "socketserver", "ssl", "sys", "threading", "time", "typing", "collections",
                       "urllib"}, imports


# --- egress firewall -------------------------------------------------------------------------------------------


def test_the_firewall_admits_the_worker_to_the_relay_through_traefik_only():
    text = FIREWALL.read_text(encoding="utf-8")
    for rule in (
            'EDGE_OS_EGRESS_RELAY_HOSTS=${EDGE_OS_EGRESS_RELAY_HOSTS:-}',
            "RELAY_SET=edgeos-egress-relay",
            "RELAY_MARK=0x2031",
            'fill "$RELAY_SET" "$EDGE_OS_EGRESS_RELAY_HOSTS"',
            'fill "$SET" "$EDGE_OS_EGRESS_HOSTS"',
            'mark=$(build PREROUTING EDGE_OS_RELAY_MARK mangle)',
            '-i edgeos-egress -s "$EGRESS_SUBNET" -p tcp --dport 443 -m set --match-set "$RELAY_SET" dst '
            '-m conntrack --ctstate NEW -j CONNMARK --set-mark "$RELAY_MARK"',
            'hook PREROUTING EDGE_OS_RELAY_MARK "$mark" mangle',
            '-o edgeos-egress -d "$EGRESS_SUBNET" -m connmark --mark "$RELAY_MARK" '
            '-m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT',
            '-i edgeos-egress -s "$EGRESS_SUBNET" -p tcp -m connmark --mark "$RELAY_MARK" '
            '-m conntrack --ctstate DNAT --ctorigdstport 443 -j ACCEPT'):
        assert rule in text, rule
    # The relay accept comes before the final drop of the forward chain.
    assert text.index("--ctorigdstport 443 -j ACCEPT") < text.index('iptables -A "$fwd" -j DROP')


def test_the_firewall_keeps_the_relay_hosts_out_of_the_general_allow_set():
    text = FIREWALL.read_text(encoding="utf-8")
    assert 'fill "$SET" "$EDGE_OS_EGRESS_RELAY_HOSTS"' not in text


@pytest.mark.skipif(shutil.which("sh") is None, reason="a POSIX shell is required")
def test_the_firewall_script_parses():
    assert subprocess.run(["sh", "-n", str(FIREWALL)], capture_output=True, timeout=30).returncode == 0


def test_the_runbook_names_the_relay_hosts_instead_of_the_provider():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert 'EDGE_OS_EGRESS_HOSTS="api.privy.io"' in text
    assert f'EDGE_OS_EGRESS_RELAY_HOSTS="{OBSERVER_HOST} {BROADCAST_HOST}"' in text
    assert "RPC_RELAY.md" in text
    assert "<the Monad RPC host name in the approved execution release>" not in text


# --- document --------------------------------------------------------------------------------------------------


def test_the_document_gives_the_fill_values_methods_dns_and_checks():
    text = DOC.read_text(encoding="utf-8")
    for needle in (
            f"https://{OBSERVER_HOST}/rpc", f"https://{BROADCAST_HOST}/rpc",
            '"quote_endpoint": "https://rpc-a.edgeos.fun/rpc"',
            '"observer_endpoint": "https://rpc-a.edgeos.fun/rpc"',
            '"broadcast_endpoint": "https://rpc-b.edgeos.fun/rpc"',
            "EDGE_OS_EXECUTION_MONAD_RPC_URL", "EDGE_OS_EGRESS_RELAY_HOSTS", "EDGE_OS_RPC_RELAY_ALLOWED_SOURCES",
            "EDGE_OS_RPC_RELAY_UPSTREAM_URL", "coolify-proxy", "ipallowlist", "letsencrypt", "AAAA",
            "eth_sendRawTransaction", "eth_feeHistory", "batch", "-32601", "-32005", "429", "413",
            "## Checks", "## DNS records", "## Deploy", "## Method table", "## Limits"):
        assert needle in text, needle
    for method in ("eth_chainId", "eth_blockNumber", "eth_call", "eth_estimateGas", "eth_getBalance", "eth_getCode",
                   "eth_getTransactionCount", "eth_getBlockByNumber", "eth_getTransactionReceipt",
                   "eth_getTransactionByHash", "eth_gasPrice", "eth_maxPriorityFeePerGas"):
        assert f"`{method}`" in text, method
    assert "quiknode.pro/" not in text
