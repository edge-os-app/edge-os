"""One run-owned Compose project of compose.local.yml: names, scoped environment, commands and exact cleanup.

Ownership rules (same intent as the P01 isolated-instance profile):
- a run ID is a plain lowercase word; it names the Compose projects, databases and image tags;
- the Compose environment is built from scratch, never from ambient EDGE_OS_* or POSTGRES_* values;
- a project is claimed only when Docker holds no container, volume or network of that project and no image tag of
  the run exists yet; otherwise nothing is created or removed;
- cleanup removes that project's own containers, volumes and networks and the run's exact image tags, then verifies.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO / "compose.local.yml"
RUN_LABEL = "edge-os.rehearsal.run"
OTHER_RUN_LABEL = "edge-os.test.run"
RUN_ID = re.compile(r"^[a-z0-9]{4,20}$")
PROFILES = ("--profile", "migrate", "--profile", "workers")
# Docker CLI settings the compose child may need to find the daemon; nothing else is inherited.
DOCKER_CLIENT_VARIABLES = ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY")


def check_run_id(run_id: str) -> str:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"run ID {run_id!r} must be 4 to 20 lowercase letters or digits")
    return run_id


@dataclass(frozen=True)
class StackNames:
    run_id: str
    project: str
    database: str

    @classmethod
    def primary(cls, run_id: str) -> "StackNames":
        check_run_id(run_id)
        return cls(run_id, f"edge-os-local-{run_id}", f"edge_os_local_{run_id}")

    @classmethod
    def restored(cls, run_id: str) -> "StackNames":
        check_run_id(run_id)
        return cls(run_id, f"edge-os-local-{run_id}r", f"edge_os_restore_{run_id}")

    @property
    def images(self) -> tuple[str, str]:
        return f"edge-os-local-api:{self.run_id}", f"edge-os-local-web:{self.run_id}"


def compose_environment(names: StackNames, *, port: int, db_password: str, verification_key: str,
                        build_sha: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": os.environ.get("HOME", "/tmp")}
    env.update({name: os.environ[name] for name in DOCKER_CLIENT_VARIABLES if name in os.environ})
    env.update({
        "EDGE_OS_LOCAL_RUN_ID": names.run_id,
        "EDGE_OS_LOCAL_PUBLIC_PORT": str(port),
        "EDGE_OS_LOCAL_DB_NAME": names.database,
        "EDGE_OS_LOCAL_DB_PASSWORD": db_password,
        "EDGE_OS_LOCAL_VERIFICATION_KEY": verification_key,
        "EDGE_OS_LOCAL_BUILD_SHA": build_sha,
    })
    return env


def sh(args: list[str], *, check: bool = True, timeout: int = 120, env: dict[str, str] | None = None,
       stdin: Any = None, stdout: Any = subprocess.PIPE, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=stdout, stderr=subprocess.PIPE, stdin=stdin, input=input_bytes, check=check,
                          timeout=timeout, env=env)


def text(result: subprocess.CompletedProcess) -> str:
    return (result.stdout or b"").decode("utf-8", "replace").strip()


def inventory() -> dict[str, dict[str, dict[str, str]]]:
    """Every container, volume, network and image ID on this daemon with its rehearsal run label (or "")."""
    found: dict[str, dict[str, dict[str, str]]] = {}
    # A resource of another rehearsal run or of a P03 harness run (`edge-os.test.run`, e.g. a parallel lane) counts as
    # owned by that run; only resources with neither label are compared for foreign changes.
    template = '{{.ID}}\t{{.Label "%s"}}{{.Label "%s"}}\t{{.Names}}' % (RUN_LABEL, OTHER_RUN_LABEL)
    for kind, args in {"containers": ["docker", "ps", "-a", "--no-trunc"], "volumes": ["docker", "volume", "ls"],
                       "networks": ["docker", "network", "ls", "--no-trunc"]}.items():
        fmt = template.replace("{{.Names}}", "{{.Name}}") if kind != "containers" else template
        if kind == "volumes":
            fmt = fmt.replace("{{.ID}}", "{{.Name}}", 1)
        rows = [(row.split("\t") + ["", ""])[:3] for row in text(sh([*args, "--format", fmt])).splitlines() if row]
        found[kind] = {key: {"run": run, "name": name} for key, run, name in rows}
    # `docker image ls` cannot format labels; read them from one JSON inspect over every image ID.
    ids = sorted(set(text(sh(["docker", "image", "ls", "-a", "--no-trunc", "--format", "{{.ID}}"])).split()))
    images = json.loads(text(sh(["docker", "image", "inspect", *ids]))) if ids else []
    found["images"] = {}
    for image in images:
        labels = (image.get("Config") or {}).get("Labels") or {}
        found["images"][image["Id"]] = {"run": labels.get(RUN_LABEL, "") + labels.get(OTHER_RUN_LABEL, ""),
                                        "name": ",".join(image.get("RepoTags") or [])}
    return found


def _named(item: dict[str, str]) -> str:
    return f" ({item['name']})" if item.get("name") else ""


def foreign_changes(before: dict[str, Any], after: dict[str, Any], *, run_id: str) -> list[str]:
    """Resources not labelled for any rehearsal run that appeared or disappeared. Other runs are ignored."""
    changes: list[str] = []
    for kind in ("containers", "volumes", "networks", "images"):
        old = {key for key, value in before.get(kind, {}).items() if not value["run"]}
        new = {key for key, value in after.get(kind, {}).items() if not value["run"]}
        changes += [f"{kind}:{key} disappeared" + _named(before[kind][key]) for key in sorted(old - new)]
        changes += [f"{kind}:{key} appeared" + _named(after[kind][key]) for key in sorted(new - old)]
    return changes


def leftovers(after: dict[str, Any], *, run_id: str) -> list[str]:
    return [f"{kind}:{key}" for kind in ("containers", "volumes", "networks", "images")
            for key, value in after.get(kind, {}).items() if value["run"] == run_id]


class LocalStack:
    """A Compose project this run claimed. Commands never touch another project."""

    def __init__(self, names: StackNames, env: dict[str, str], log_dir: Path) -> None:
        self.names, self.env, self.log_dir = names, env, log_dir
        self.claimed = False

    def compose(self, *args: str, check: bool = True, timeout: int = 300, input_bytes: bytes | None = None,
                stdout: Any = subprocess.PIPE) -> subprocess.CompletedProcess:
        return sh(["docker", "compose", "-f", str(COMPOSE_FILE), "-p", self.names.project, *PROFILES, *args],
                  check=check, timeout=timeout, env=self.env, input_bytes=input_bytes, stdout=stdout)

    def existing_resources(self) -> list[str]:
        label = f"label=com.docker.compose.project={self.names.project}"
        found = []
        for kind, args in {"container": ["docker", "ps", "-a", "-q"], "volume": ["docker", "volume", "ls", "-q"],
                           "network": ["docker", "network", "ls", "-q"]}.items():
            found += [f"{kind} {item}" for item in text(sh([*args, "--filter", label])).splitlines() if item]
        return found

    def claim(self, *, images_must_be_new: bool) -> None:
        present = self.existing_resources()
        if images_must_be_new:
            present += [f"image {tag}" for tag in self.names.images
                        if sh(["docker", "image", "inspect", tag], check=False).returncode == 0]
        if present:
            raise RuntimeError(f"refusing project {self.names.project}: {', '.join(present)} already exist. "
                               "Nothing was created or changed. Use a new run ID.")
        self.claimed = True

    def log(self, name: str, result: subprocess.CompletedProcess) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_dir / f"{self.names.project}-{name}.log", "ab") as handle:
            handle.write(result.stdout or b"")
            handle.write(result.stderr or b"")

    def run(self, name: str, *args: str, check: bool = False, timeout: int = 300) -> subprocess.CompletedProcess:
        result = self.compose(*args, check=False, timeout=timeout)
        self.log(name, result)
        if check and result.returncode != 0:
            raise RuntimeError(f"{self.names.project}: `{' '.join(args[:3])}` failed with exit {result.returncode}")
        return result

    def psql(self, sql: str) -> str:
        result = self.compose("exec", "-T", "postgres", "psql", "-U", "edge_os", "-d", self.names.database,
                              "-v", "ON_ERROR_STOP=1", "-tAc", sql)
        return text(result)

    def rows(self, sql: str) -> list[dict[str, Any]]:
        return json.loads(self.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))

    def container_ids(self) -> dict[str, str]:
        rows = text(self.compose("ps", "-a", "--format", "{{.Service}}\t{{.ID}}")).splitlines()
        return dict(row.split("\t", 1) for row in rows if row)

    def inspect(self, service: str) -> dict[str, Any]:
        container = self.container_ids()[service]
        return json.loads(text(sh(["docker", "inspect", container])))[0]

    def down(self) -> subprocess.CompletedProcess | None:
        """Remove this project's containers, networks and volumes. Only a claimed project is touched."""
        if not self.claimed:
            return None
        result = self.compose("down", "--volumes", "--remove-orphans", "--timeout", "10", check=False, timeout=180)
        self.log("down", result)
        return result


def remove_run_images(names: StackNames) -> list[str]:
    """Remove the run's exact image tags if they carry the run label. Returns tags that still exist."""
    remaining = []
    for tag in names.images:
        inspected = sh(["docker", "image", "inspect", "--format", '{{index .Config.Labels "%s"}}' % RUN_LABEL, tag],
                       check=False)
        if inspected.returncode != 0:
            continue
        if text(inspected) == names.run_id:
            sh(["docker", "image", "rm", tag], check=False)
        if sh(["docker", "image", "inspect", tag], check=False).returncode == 0:
            remaining.append(tag)
    return remaining
