"""The workflow, Dockerfile edits, runbook, smoke script and secret hygiene of the deployment files."""

from __future__ import annotations

import os
import re
from pathlib import Path

import deploy_support as support

WORKFLOW = support.REPO / ".github" / "workflows" / "images.yml"
RUNBOOK = support.REPO / "deploy" / "coolify" / "RUNBOOK.md"
SMOKE = support.REPO / "deploy" / "coolify" / "smoke_public.sh"
API_DOCKERFILE = support.REPO / "deploy" / "docker" / "api.Dockerfile"
WEB_DOCKERFILE = support.REPO / "apps" / "web" / "Dockerfile"


def test_the_workflow_is_manual_only():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert not re.search(r"(?m)^  (push|pull_request|schedule):", text)
    assert re.findall(r"secrets\.([A-Za-z0-9_]+)", text) == ["GITHUB_TOKEN"]


def test_the_workflow_builds_both_images_for_amd64_and_pushes_to_ghcr():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "deploy/docker/api.Dockerfile" in text
    assert "apps/web/Dockerfile" in text
    assert text.count("platforms: linux/amd64") == 2
    assert "ghcr.io/edge-os-app/edge-os-api" in text
    assert "ghcr.io/edge-os-app/edge-os-web" in text
    assert "push: true" in text
    assert "upload-artifact" in text


def test_the_workflow_passes_the_public_build_values_and_the_production_profile():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "EDGE_OS_PROFILE=PRODUCTION" in text
    assert "NEXT_PUBLIC_API_BASE_URL" in text
    assert "NEXT_PUBLIC_PRIVY_APP_ID" in text
    assert "github.sha" in text


def test_both_dockerfiles_take_the_profile_as_a_build_argument():
    for path in (API_DOCKERFILE, WEB_DOCKERFILE):
        text = path.read_text(encoding="utf-8")
        assert "ARG EDGE_OS_PROFILE=LOCAL" in text
        assert 'edge-os.profile="${EDGE_OS_PROFILE}"' in text
        assert 'edge-os.profile="LOCAL"' not in text


def test_the_web_dockerfile_refuses_an_empty_privy_app_id():
    text = WEB_DOCKERFILE.read_text(encoding="utf-8")
    assert 'test -n "${NEXT_PUBLIC_PRIVY_APP_ID}"' in text
    assert 'test -n "${NEXT_PUBLIC_API_BASE_URL}"' in text


def test_the_runbook_covers_every_approved_step():
    text = RUNBOOK.read_text(encoding="utf-8")
    for topic in ("DNS", "Build Variable", "runtime", "TLS", "migrate", "systemd", "socket",
                  "Smoke", "backup", "restore", "Rollback", "hosted-deployment",
                  "APPROVED_HOSTED_DEPLOYMENTS", "api.edgeos.fun", "app.edgeos.fun",
                  "Coolify 4.4.7 does not substitute", "compose.deployed.yml", "Never deploy by a floating tag"):
        assert topic in text, topic
    assert "This candidate does not approve a hosted deployment" in text


def test_the_smoke_script_is_runnable_and_checks_the_public_contract():
    assert os.access(SMOKE, os.X_OK)
    text = SMOKE.read_text(encoding="utf-8")
    assert "/healthz" in text
    assert "/readyz" in text
    assert "Access-Control-Allow-Origin" in text
    assert "Origin" in text


def test_the_deployment_files_hold_no_secret_value():
    files = [support.COMPOSE_COOLIFY, RUNBOOK, SMOKE, WORKFLOW, API_DOCKERFILE, WEB_DOCKERFILE]
    files += sorted((support.REPO / "deploy" / "coolify").glob("*"))
    files += sorted((support.REPO / "deploy" / "host").glob("*"))
    patterns = [
        r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
        r"ghp_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"sk-[A-Za-z0-9]{20,}",
        r"xox[baprs]-[A-Za-z0-9-]{10,}",
        r"AKIA[0-9A-Z]{16}",
    ]
    for path in files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert not re.search(pattern, text), f"{path.name} matches {pattern}"


def test_the_hosted_deployment_registry_is_unchanged():
    text = (support.REPO / "apps" / "api" / "src" / "edge_os_api" / "core" / "hosted_deployment.py").read_text(
        encoding="utf-8")
    assert "APPROVED_HOSTED_DEPLOYMENTS: Mapping[str, str] = {}" in text


HOSTED_RECORD_V2 = support.REPO / "docs" / "qualification" / "hosted-gates" / "HOSTED_RECORD_V2_RUNBOOK.md"


def test_the_hosted_record_v2_runbook_covers_every_host_step():
    text = HOSTED_RECORD_V2.read_text(encoding="utf-8")
    for topic in ("edge-os-postgres", "alias", "127.0.0.1:5432", "IP:127.0.0.1", "DNS:edge-os-postgres",
                  "0.0.0.0", "edgeos-egress", "DOCKER-USER", "api.privy.io", "cannot restrict by host name",
                  "Contabo", "snapshot", "pg_dump", "pg_restore", "scratch", "sponsored", "execution_release",
                  "edge-os.hosted-deployment/2", "APPROVED_HOSTED_DEPLOYMENTS", "APPROVED_ACTUAL_RELEASES",
                  "EDGE_OS_PRIVY_APP_SECRET"):
        assert topic in text, topic
    assert "This candidate registers no hosted deployment" in text
    # Containers are chosen within this stack's Compose project, never by the service label alone: Coolify's own
    # database is also a Compose service named `postgres`.
    assert "docker ps --filter label=com.docker.compose.service" not in text
    assert "head -1" not in text
    assert "label=com.docker.compose.project=$PROJECT" in text
    # A negative check passes only on the probe's own "blocked" exit code from a selected, running container.
    assert 'if [ "$rc" -eq 42 ]; then echo "pass: blocked"' in text
    assert "running \"$c\" ||" in text
    assert "-ge 125" not in text


def test_the_coolify_runbook_uses_the_unique_database_alias():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "@edge-os-postgres:5432/edge_os?sslmode=require" in text
    assert "@postgres:5432" not in text
    assert "DNS:edge-os-postgres" in text
    assert "edge-os.hosted-deployment/2" in text
    assert "HOSTED_RECORD_V2_RUNBOOK.md" in text


def test_the_egress_firewall_is_fail_closed_and_starts_before_docker():
    host = support.REPO / "deploy" / "host"
    script = host / "edge-os-egress-firewall.sh"
    assert os.access(script, os.X_OK)
    text = script.read_text(encoding="utf-8")
    for rule in ("-i edgeos-hostdb -j DROP", "-o edgeos-hostdb -j DROP", '-s "$HOSTDB_SUBNET" -j DROP',
                 '! -i edgeos-egress ! -s "$EGRESS_SUBNET" -j RETURN', '-m set --match-set "$SET" dst -j RETURN',
                 '-A "$fwd" -j DROP', '-A "$chain" -j DROP', "hook DOCKER-USER",
                 "hook INPUT", "conntrack -D -s", "flock 9", "conntrack is required",
                 'replies_only EDGE_OS_IN edgeos-egress "$EGRESS_SUBNET"',
                 'replies_only EDGE_OS_IN_DB edgeos-hostdb "$HOSTDB_SUBNET"',
                 'replies_only EDGE_OS_IN_PRIVATE edgeos-private "$PRIVATE_SUBNET"'):
        assert rule in text, rule
    assert "ipset flush" not in text and "ipset swap" not in text
    # The refresh unit (Docker up) finds the two containers by Compose labels and drops exactly the addresses they
    # hold on networks they do not declare. `apply` runs before Docker and must never call the daemon.
    for rule in ("EDGE_OS_COMPOSE_PROJECT", "com.docker.compose.service", "EDGE_OS_BYPASS",
                 "EDGE_OS_BYPASS_IN", "GlobalIPv6Address", 'hook DOCKER-USER EDGE_OS_BYPASS',
                 'hook INPUT EDGE_OS_BYPASS_IN', "refresh_allowlist", "enforce_injected_addresses",
                 "cannot inspect"):
        assert rule in text, rule
    apply_body = text.split("apply() {", 1)[1].split("\n}", 1)[0]
    assert "docker " not in apply_body
    unit = (host / "edge-os-egress-firewall.service").read_text(encoding="utf-8")
    assert "Before=docker.service" in unit and "RequiredBy=docker.service" in unit
    # A failed Condition* skips the unit as a success, so Docker would start without rules.
    assert not re.search(r"(?m)^Condition", unit)
    # The unit runs a root-owned installed copy, never the git checkout.
    assert "ExecStart=/usr/local/sbin/edge-os-egress-firewall apply" in unit
    assert "ExecReload=/usr/local/sbin/edge-os-egress-firewall apply" in unit
    assert "/opt/edge-os" not in "".join(line for line in unit.splitlines() if line.startswith("Exec"))
    timer = (host / "edge-os-egress-refresh.timer").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=5min" in timer
    # The refresh inspects containers, so it must wait for Docker. Never move that call into the apply path.
    refresh_unit = (host / "edge-os-egress-refresh.service").read_text(encoding="utf-8")
    assert "After=edge-os-egress-firewall.service docker.service" in refresh_unit
    assert "ExecStart=/usr/local/sbin/edge-os-egress-firewall refresh" in refresh_unit


def test_the_runbook_documents_the_coolify_network_control_without_a_manual_disconnect():
    text = HOSTED_RECORD_V2.read_text(encoding="utf-8")
    for topic in ("Coolify resource network", "EDGE_OS_COMPOSE_PROJECT", "/proc/net/route",
                  "EXECUTION_BOOTSTRAP_ROUTE_UNEXPECTED", "residual window", "gw_priority", "GwPriority"):
        assert topic in text, topic
    assert "docker network disconnect" not in text
