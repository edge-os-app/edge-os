"""P03 isolated-instance harness: run-labelled PostgreSQL, API and web processes.

Rules (P01 profile, "Isolated instance"):
- every resource carries the labels `edge-os.test=1` and `edge-os.test.run=<run_id>`;
- the child environment is built from scratch, never from ambient `EDGE_OS_*` values;
- processes are stopped only through the handle this process holds (no PID files);
- cleanup removes exact resources found by this run's name and label, then verifies they are gone.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API_DIR = REPO / "apps" / "api"
WEB_DIR = REPO / "apps" / "web"
POSTGRES_IMAGE = "postgres:18.6-trixie"
TEST_APP_ID = "edge-os-test-app"
LABEL = "edge-os.test=1"


def sh(args: list[str], *, check: bool = True, timeout: int = 120, env: dict[str, str] | None = None
       ) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=check, timeout=timeout, env=env)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


RUN_ID = re.compile(r"^[a-z0-9]{4,24}$")


def new_run_id() -> str:
    return "p03" + secrets.token_hex(4)


def check_run_id(run_id: str) -> str:
    """Run IDs become container, volume, database and folder names. Accept plain lowercase words only."""
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"run ID {run_id!r} must be 4 to 24 lowercase letters or digits")
    return run_id


def exists(kind: str, name: str) -> bool:
    """Exact-name lookup. `docker <kind> inspect` never matches by substring."""
    return sh(["docker", kind, "inspect", name], check=False).returncode == 0


def label_of(kind: str, name: str, key: str) -> str:
    template = "{{index .Config.Labels \"%s\"}}" % key if kind == "container" else "{{index .Labels \"%s\"}}" % key
    return sh(["docker", kind, "inspect", "-f", template, name], check=False).stdout.strip()


@dataclass
class Postgres:
    """A run-labelled PostgreSQL container and volume.

    This object removes only what it created itself (`created_*`) and only after the labels still name this run.
    A name or label match alone never proves ownership, so a repeated run ID refuses and preserves what exists.
    """

    run_id: str
    password: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    host_port: int = 0
    created_container: bool = False
    created_volume: bool = False

    @property
    def container(self) -> str:
        return f"edge-os-test-pg-{self.run_id}"

    @property
    def volume(self) -> str:
        return f"edge-os-test-pg-{self.run_id}"

    @property
    def database(self) -> str:
        return f"edge_os_test_{self.run_id}"

    @property
    def url(self) -> str:
        return f"postgresql+psycopg://postgres:{self.password}@127.0.0.1:{self.host_port}/{self.database}"

    def labels(self) -> list[str]:
        return ["--label", LABEL, "--label", f"edge-os.test.run={self.run_id}"]

    def existing_resources(self) -> list[str]:
        found = []
        if exists("container", self.container):
            found.append(f"container {self.container}")
        if exists("volume", self.volume):
            found.append(f"volume {self.volume}")
        return found

    def start(self) -> "Postgres":
        present = self.existing_resources()
        if present:
            raise RuntimeError(f"refusing to start run {self.run_id}: {', '.join(present)} already exists. "
                               "Nothing was created or changed. Use a new run ID.")
        sh(["docker", "volume", "create", *self.labels(), self.volume])
        # `docker volume create` is idempotent. Claim the volume only if it carries this run's labels.
        if label_of("volume", self.volume, "edge-os.test.run") != self.run_id or label_of("volume", self.volume, "edge-os.test") != "1":
            raise RuntimeError(f"refusing run {self.run_id}: volume {self.volume} exists without this run's labels. "
                               "Nothing was removed.")
        self.created_volume = True
        try:
            sh(["docker", "run", "-d", "--name", self.container, *self.labels(),
                "-e", f"POSTGRES_PASSWORD={self.password}", "-e", f"POSTGRES_DB={self.database}",
                "-p", "127.0.0.1::5432", "-v", f"{self.volume}:/var/lib/postgresql", POSTGRES_IMAGE])
        finally:
            # `docker run` can create the container and still fail to start it. Own it only if it now exists.
            self.created_container = exists("container", self.container) and \
                label_of("container", self.container, "edge-os.test.run") == self.run_id
        port_line = sh(["docker", "port", self.container, "5432/tcp"]).stdout.strip().splitlines()[0]
        self.host_port = int(port_line.rsplit(":", 1)[1])
        self._wait_ready()
        self.assert_guard()
        return self

    def psql(self, sql: str, *, db: str | None = None) -> str:
        return sh(["docker", "exec", self.container, "psql", "-U", "postgres", "-d", db or self.database,
                   "-v", "ON_ERROR_STOP=1", "-tAc", sql]).stdout.strip()

    def _wait_ready(self, timeout: float = 90.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = sh(["docker", "exec", self.container, "psql", "-U", "postgres", "-d", self.database,
                         "-tAc", "select 1"], check=False)
            if result.returncode == 0 and result.stdout.strip() == "1":
                return
            time.sleep(0.5)
        raise RuntimeError(f"postgres {self.container} did not become ready")

    def assert_guard(self) -> None:
        """Refuse to continue unless this is the run's own labelled container and database."""
        if self.psql("select current_database()") != self.database:
            raise RuntimeError("guard: current_database() is not this run's database")
        inspected = json.loads(sh(["docker", "inspect", self.container]).stdout)[0]["Config"]["Labels"]
        if inspected.get("edge-os.test") != "1" or inspected.get("edge-os.test.run") != self.run_id:
            raise RuntimeError("guard: container labels do not match this run")

    def version(self) -> str:
        return self.psql("show server_version")

    def image_identity(self) -> dict[str, str]:
        info = json.loads(sh(["docker", "image", "inspect", POSTGRES_IMAGE]).stdout)[0]
        return {"image": POSTGRES_IMAGE, "id": info["Id"], "repo_digests": ",".join(info.get("RepoDigests", []))}

    def _owned(self, kind: str, name: str) -> bool:
        return exists(kind, name) and label_of(kind, name, "edge-os.test") == "1" \
            and label_of(kind, name, "edge-os.test.run") == self.run_id

    def stop_and_remove(self) -> None:
        """Remove what this instance created, if its labels still name this run. Otherwise change nothing."""
        if self.created_container and self._owned("container", self.container):
            sh(["docker", "rm", "-f", "-v", self.container], check=False)
        if self.created_volume and self._owned("volume", self.volume):
            sh(["docker", "volume", "rm", self.volume], check=False)

    def leftovers(self) -> list[str]:
        """Resources this instance created that still exist."""
        out: list[str] = []
        if self.created_container and exists("container", self.container):
            out.append(f"container:{self.container}")
        if self.created_volume and exists("volume", self.volume):
            out.append(f"volume:{self.volume}")
        return out


@dataclass
class Process:
    name: str
    popen: subprocess.Popen[bytes]
    log_path: Path
    log_handle: Any = None

    def stop(self, grace: float = 8.0) -> None:
        try:
            if self.popen.poll() is not None:
                return  # already exited: never signal a possibly reused process group
            os.killpg(self.popen.pid, signal.SIGTERM)
            try:
                self.popen.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                if self.popen.poll() is None:
                    os.killpg(self.popen.pid, signal.SIGKILL)
                    self.popen.wait(timeout=grace)
        finally:
            if self.log_handle is not None:
                self.log_handle.close()
                self.log_handle = None


def wait_http(url: str, *, timeout: float = 60.0, ok: tuple[int, ...] = (200,)) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 - loopback only
                if response.status in ok:
                    return
        except Exception as error:  # noqa: BLE001
            last = type(error).__name__
        time.sleep(0.3)
    raise RuntimeError(f"{url} not ready ({last})")


def api_python() -> str:
    return str(API_DIR / ".venv" / "bin" / "python")


def base_env() -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", os.defpath), "HOME": os.environ.get("HOME", "/tmp"), "LANG": "en_US.UTF-8"}


def api_env(*, database_url: str, public_pem: str, previous_pem: str | None, cors: list[str],
            env_name: str = "test") -> dict[str, str]:
    env = base_env()
    env.update({
        "EDGE_OS_ENV": env_name,
        "EDGE_OS_DATABASE_URL": database_url,
        "EDGE_OS_PRIVY_APP_ID": TEST_APP_ID,
        "EDGE_OS_PRIVY_VERIFICATION_KEY": public_pem.replace("\n", "\\n"),
        "EDGE_OS_CORS_ALLOWED_ORIGINS": ",".join(cors),
        "EDGE_OS_BUILD_SHA": git_sha(),
    })
    if previous_pem:
        env["EDGE_OS_PRIVY_VERIFICATION_KEY_PREVIOUS"] = previous_pem.replace("\n", "\\n")
    return env


def git_sha() -> str:
    return sh(["git", "-C", str(REPO), "rev-parse", "HEAD"]).stdout.strip()


def migrate(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([api_python(), "-m", "alembic", "upgrade", "head"], cwd=API_DIR, env=env,
                          capture_output=True, text=True, timeout=120)


def start_api(env: dict[str, str], port: int, log_dir: Path, name: str = "api") -> Process:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    handle = open(log_path, "ab")
    popen = subprocess.Popen(
        [api_python(), "-m", "uvicorn", "edge_os_api.main:create_app", "--factory", "--host", "127.0.0.1",
         "--port", str(port)], cwd=API_DIR, env=env, stdout=handle, stderr=handle, start_new_session=True)
    return Process(name, popen, log_path, handle)


def web_tsconfig(dist: str) -> str:
    return f"tsconfig.{dist.lstrip('.')}.json"


def web_env(api_url: str, dist: str) -> dict[str, str]:
    env = base_env()
    env["EDGE_OS_WEB_TSCONFIG"] = web_tsconfig(dist)
    env["NEXT_PUBLIC_API_BASE_URL"] = api_url
    env["NEXT_PUBLIC_PRIVY_APP_ID"] = TEST_APP_ID
    env["EDGE_OS_WEB_DIST"] = dist
    return env


def build_web(*, api_url: str, dist: str, log_dir: Path) -> subprocess.CompletedProcess[str]:
    """Production build into a run-scoped directory. NEXT_PUBLIC_* values are inlined here, at build time."""
    log_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(WEB_DIR / "tsconfig.json", WEB_DIR / web_tsconfig(dist))
    result = subprocess.run(["npm", "run", "build"], cwd=WEB_DIR, env=web_env(api_url, dist), capture_output=True,
                            text=True, timeout=600)
    (log_dir / "web-build.log").write_text(result.stdout + result.stderr)
    return result


def start_web(*, api_url: str, dist: str, port: int, log_dir: Path, name: str = "web") -> Process:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    handle = open(log_path, "ab")
    env = web_env(api_url, dist)
    popen = subprocess.Popen(["node", str(WEB_DIR / "node_modules" / "next" / "dist" / "bin" / "next"), "start",
                              "--hostname", "127.0.0.1", "--port", str(port)], cwd=WEB_DIR, env=env,
                             stdout=handle, stderr=handle, start_new_session=True)
    return Process(name, popen, log_path, handle)


def orphan_report() -> list[dict[str, str]]:
    """List labelled resources. Removal needs explicit confirmation naming the run ID."""
    rows = sh(["docker", "ps", "-a", "--filter", f"label={LABEL}", "--format",
               "{{.Names}}\t{{.Label \"edge-os.test.run\"}}\t{{.State}}\t{{.CreatedAt}}"], check=False).stdout
    return [dict(zip(("container", "run_id", "state", "created"), line.split("\t"))) for line in rows.splitlines() if line]


def remove_orphan(run_id: str) -> None:
    """Remove one stopped, labelled orphan after the operator named its run ID. Refuse anything else."""
    pg = Postgres(run_id)
    if not exists("container", pg.container):
        raise RuntimeError(f"{pg.container} does not exist")
    if sh(["docker", "inspect", "-f", "{{.State.Running}}", pg.container], check=False).stdout.strip() == "true":
        raise RuntimeError(f"{pg.container} is running and may belong to a live run; refusing removal")
    if label_of("container", pg.container, "edge-os.test") != "1" or label_of("container", pg.container, "edge-os.test.run") != run_id:
        raise RuntimeError("labels do not match this run ID; refusing removal")
    pg.created_container = True  # the operator named this run and its labels match: removal is authorized
    pg.created_volume = exists("volume", pg.volume)
    pg.stop_and_remove()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "orphans"
    if command == "orphans":
        print(json.dumps(orphan_report(), indent=2))
    elif command == "remove-orphan" and len(sys.argv) == 3:
        remove_orphan(sys.argv[2])
        print("removed", sys.argv[2])
    else:
        sys.exit("usage: harness.py orphans | remove-orphan <run_id>")
