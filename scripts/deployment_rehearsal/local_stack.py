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
# Run labels of the other verified owners on this host, each carrying its run identity as the value: the P03/P05
# harness and pytest runs (`edge-os.test.run`) and the lane-1 Hermes relay supervisor (`edge-os.hermes-relay`).
OTHER_RUN_LABELS = ("edge-os.test.run", "edge-os.hermes-relay")
RECOGNIZED_RUN_LABELS = (RUN_LABEL, *OTHER_RUN_LABELS)
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


def owner_labels(labels: dict[str, str] | None) -> dict[str, str]:
    """The recognized run labels a resource carries, with their run identities. Empty values do not count."""
    return {name: value for name, value in (labels or {}).items() if name in RECOGNIZED_RUN_LABELS and value}


def inventory() -> dict[str, dict[str, dict[str, Any]]]:
    """Every container, volume, network and image ID on this daemon with its name and recognized run labels."""
    found: dict[str, dict[str, dict[str, Any]]] = {}
    labels = "\t".join('{{.Label "%s"}}' % name for name in RECOGNIZED_RUN_LABELS)
    for kind, (args, key, name) in {"containers": (["docker", "ps", "-a", "--no-trunc"], "{{.ID}}", "{{.Names}}"),
                                    "volumes": (["docker", "volume", "ls"], "{{.Name}}", "{{.Name}}"),
                                    "networks": (["docker", "network", "ls", "--no-trunc"], "{{.ID}}", "{{.Name}}")}.items():
        found[kind] = {}
        for row in text(sh([*args, "--format", f"{key}\t{name}\t{labels}"])).splitlines():
            fields = (row.split("\t") + [""] * (2 + len(RECOGNIZED_RUN_LABELS)))[:2 + len(RECOGNIZED_RUN_LABELS)]
            if fields[0]:
                found[kind][fields[0]] = {"name": fields[1],
                                          "owners": owner_labels(dict(zip(RECOGNIZED_RUN_LABELS, fields[2:])))}
    # `docker image ls` cannot format labels; read them from one JSON inspect over every image ID.
    ids = sorted(set(text(sh(["docker", "image", "ls", "-a", "--no-trunc", "--format", "{{.ID}}"])).split()))
    images, disappeared = _inspect_images(ids)
    found["images"] = {image["Id"]: {"name": ",".join(image.get("RepoTags") or []),
                                     "owners": owner_labels((image.get("Config") or {}).get("Labels"))}
                       for image in images}
    found["images_disappeared"] = disappeared
    return found


def _inspect_images(ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Inspect every listed image. An image removed between `ls` and `inspect` (for example by a parallel run) is
    recorded as disappeared; any other inspect failure raises, so an unknown state is never reported as clean."""
    if not ids:
        return [], []
    bulk = sh(["docker", "image", "inspect", *ids], check=False)
    if bulk.returncode == 0:
        return json.loads(text(bulk)), []
    images, disappeared = [], []
    for image_id in ids:
        single = sh(["docker", "image", "inspect", image_id], check=False)
        error = (single.stderr or b"").decode("utf-8", "replace")
        if single.returncode == 0:
            images += json.loads(text(single))
        elif "No such image" in error:
            disappeared.append(image_id)
        else:
            raise RuntimeError(f"docker image inspect {image_id[:19]} failed: {error.strip()[:200]}")
    return images, disappeared


def owner_class(item: dict[str, Any], run_id: str) -> str:
    """`own`, `other` (exactly one recognized run label, not this run), `unlabelled` or `conflict` (several)."""
    owners = item.get("owners") or {}
    if not owners:
        return "unlabelled"
    if len(owners) > 1:
        return "conflict"
    return "own" if owners.get(RUN_LABEL) == run_id else "other"


def _described(item: dict[str, Any], run_id: str) -> str:
    text_ = f" ({item['name']})" if item.get("name") else ""
    owners = ", ".join(f"{name}={value}" for name, value in sorted((item.get("owners") or {}).items()))
    if owner_class(item, run_id) == "conflict":
        text_ += f" [conflicting run labels: {owners}]"
    elif owners:
        text_ += f" [{owners}]"
    return text_


def _changes(before: dict[str, Any], after: dict[str, Any], run_id: str, classes: set[str]) -> list[str]:
    found: list[str] = []
    for kind in ("containers", "volumes", "networks", "images"):
        old = {key for key, item in before.get(kind, {}).items() if owner_class(item, run_id) in classes}
        new = {key for key, item in after.get(kind, {}).items() if owner_class(item, run_id) in classes}
        found += [f"{kind}:{key} disappeared" + _described(before[kind][key], run_id) for key in sorted(old - new)]
        found += [f"{kind}:{key} appeared" + _described(after[kind][key], run_id) for key in sorted(new - old)]
    return found


def foreign_changes(before: dict[str, Any], after: dict[str, Any], *, run_id: str) -> list[str]:
    """Unlabelled or conflictingly labelled resources that appeared or disappeared. Any entry fails the run."""
    return _changes(before, after, run_id, {"unlabelled", "conflict"})


def other_run_changes(before: dict[str, Any], after: dict[str, Any], *, run_id: str) -> list[str]:
    """Changes accounted to another recognized run (kept as evidence; that run owns them)."""
    return _changes(before, after, run_id, {"other"})


def leftovers(after: dict[str, Any], *, run_id: str) -> list[str]:
    """Every resource that still carries this run's label, whatever else it carries."""
    return [f"{kind}:{key}" for kind in ("containers", "volumes", "networks", "images")
            for key, item in after.get(kind, {}).items() if (item.get("owners") or {}).get(RUN_LABEL) == run_id]


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
