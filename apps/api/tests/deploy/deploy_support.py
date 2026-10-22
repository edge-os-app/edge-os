"""Shared helpers for the deployment-file tests. No network, no secrets, no host change."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
COMPOSE_COOLIFY = REPO / "compose.coolify.yml"
HOST_PROXY_COMPOSE = REPO / "deploy" / "host" / "docker-socket-proxy.yml"
GUARDED_RUNNER = REPO / "scripts" / "hermes_interpretation" / "guarded_docker_runner.py"
DOCKER_TURN_RUNNER = REPO / "scripts" / "hermes_interpretation" / "docker_turn_runner.py"
RELAY_SUPERVISOR = REPO / "scripts" / "hermes_provider_relay" / "relay_supervisor.py"
RELAY_OPERATOR = REPO / "scripts" / "hermes_provider_relay" / "relay_operator.py"


def _compose_json(path: Path) -> dict[str, Any]:
    """The Compose model without interpolation or an env file, so no secret and no ambient value enters."""
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as empty:
        empty_path = empty.name
    try:
        completed = subprocess.run(
            ["docker", "compose", "--project-directory", str(REPO), "--env-file", empty_path,
             "-f", str(path), "config", "--no-interpolate", "--format", "json"],
            capture_output=True, text=True, timeout=60, cwd=REPO,
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
        )
    finally:
        Path(empty_path).unlink(missing_ok=True)
    assert completed.returncode == 0, f"docker compose could not read {path.name}: {completed.stderr.strip()}"
    model = json.loads(completed.stdout)
    assert isinstance(model, dict)
    return model


@lru_cache(maxsize=None)
def compose_model(path: str) -> dict[str, Any]:
    return _compose_json(Path(path))


def environment_names(service: dict[str, Any]) -> set[str]:
    environment = service.get("environment") or {}
    if isinstance(environment, list):
        return {item.split("=", 1)[0] for item in environment}
    return set(environment)


def environment_values(service: dict[str, Any]) -> dict[str, Any]:
    environment = service.get("environment") or {}
    if isinstance(environment, list):
        return {item.split("=", 1)[0]: item.split("=", 1)[1] if "=" in item else None for item in environment}
    return dict(environment)


def command_text(service: dict[str, Any]) -> str:
    command = service.get("command") or []
    if isinstance(command, str):
        return command
    return " ".join(str(part) for part in command)


def mounts(service: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalized mounts: `source`, `target`, `type`, `read_only` for string or Compose-object form."""
    normalized: list[dict[str, Any]] = []
    for mount in service.get("volumes") or []:
        if isinstance(mount, str):
            parts = mount.split(":")
            source, target = parts[0], parts[1] if len(parts) > 1 else ""
            mode = parts[2] if len(parts) > 2 else ""
            normalized.append({"source": source, "target": target, "read_only": "ro" in mode.split(",")})
        else:
            normalized.append({"source": mount.get("source"), "target": mount.get("target"),
                               "type": mount.get("type"), "read_only": mount.get("read_only") is True})
    return normalized


def docker_verbs(text: str) -> set[str]:
    """Docker CLI verbs this source names in a literal call or argv."""
    verbs: set[str] = set()
    verbs |= set(re.findall(r'docker\(\s*"([a-z]+)"', text))
    verbs |= set(re.findall(r'\[\s*"docker"\s*,\s*"([a-z]+)"', text))
    verbs |= set(re.findall(r'\bcli\(\s*"([a-z]+)"', text))
    return verbs


def command_allow_rules(service: dict[str, Any]) -> dict[str, list[str]]:
    """The socket-proxy allow rules: HTTP method -> regular expressions."""
    rules: dict[str, list[str]] = {}
    command = service.get("command") or []
    for item in command:
        match = re.fullmatch(r"-allow(GET|HEAD|POST|PUT|PATCH|DELETE|CONNECT|TRACE|OPTIONS)=(.*)", str(item))
        if match:
            rules.setdefault(match.group(1), []).append(match.group(2))
    return rules


def command_option(service: dict[str, Any], name: str) -> str | None:
    prefix = f"-{name}="
    for item in service.get("command") or []:
        text = str(item)
        if text.startswith(prefix):
            return text[len(prefix):]
    return None


def allows(rules: dict[str, list[str]], method: str, path: str) -> bool:
    return any(re.fullmatch(pattern, path) for pattern in rules.get(method, []))


QUERY = re.compile(r"\?.*$")


def endpoint(method: str, path: str) -> tuple[str, str]:
    return method, QUERY.sub("", path)
