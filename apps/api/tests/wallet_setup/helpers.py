"""Shared helpers for the local wallet-setup tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import flows
import harness

HERE = Path(__file__).resolve().parent
API_DIR = HERE.parents[1]
SRC = API_DIR / "src"


def publish_revision(client, headers) -> tuple[str, str]:
    """Publish one real immutable P02/P06 revision through the API and return `(strategy_id, revision_id)`."""
    bundle = flows.compiled_thesis(client, headers)
    response, body = flows.publish(client, headers, bundle)
    assert response.status_code == 201, response.text
    return body["strategy"]["strategy_id"], response.json()["revision_id"]


def owner_user_id(client, headers) -> str:
    response = client.get("/v1/me", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def driver_env() -> dict[str, str]:
    env = dict(os.environ)
    parts = [str(SRC), str(HERE)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def start_driver(db_url: str, owner_id: str, agent_id: str, strategy_id: str, revision_id: str,
                 scenario: str, *extra: str) -> subprocess.Popen[str]:
    """Start one independent process that drives the wallet-setup service against the same database."""
    return subprocess.Popen(
        [harness.api_python(), str(HERE / "driver.py"), db_url, owner_id, agent_id, strategy_id, revision_id,
         scenario, *extra],
        env=driver_env(), cwd=str(API_DIR), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
