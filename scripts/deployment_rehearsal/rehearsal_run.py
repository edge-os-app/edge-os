"""LOCAL Docker rehearsal of compose.local.yml: fresh images, guarded startup, seeded journeys, process replacement,
private backup, fresh-database restore into a separately owned stack, GET-only browser reopen and exact cleanup.

Run from the repository root with the qualified API environment:
    apps/api/.venv/bin/python scripts/deployment_rehearsal/rehearsal_run.py --evidence-root <private folder>

LOCAL fixture profile only. Synthetic owners and key, authored fixture providers and SYNTHETIC recorded history.
No provider, model, wallet, Privy or network call outside the run's own containers and loopback entry. A pass
proves the packaged LOCAL architecture on this host; it qualifies no production host, TLS, egress or judge access.
The pinned Hermes job path is not packaged here (it needs the trusted host supervisor/relay interface).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(REPO / "scripts" / "p03")]

import identity_snapshot  # noqa: E402
import image_inspection  # noqa: E402
import local_stack  # noqa: E402
import restore_drill  # noqa: E402
from local_stack import LocalStack, StackNames, sh, text  # noqa: E402

P03_DIR = REPO / "tests" / "p03"
BROWSER_DIR = REPO / "tests" / "deployment_rehearsal" / "browser"
APP_ROLES = ("api", "web", "entry")
WORKER_COMMANDS = {
    "research-worker": ["python", "-m", "edge_os_api.research.investigation_jobs", "--once"],
    "execution-worker": ["python", "-m", "edge_os_api.execution.worker", "--once"],
    "recurring-producer": ["python", "-m", "edge_os_api.execution.recurring_producer", "--once"],
}


class Recorder:
    def __init__(self, evidence: Path) -> None:
        self.evidence, self.steps = evidence, []

    def step(self, name: str, ok: bool, detail: Any = None) -> bool:
        self.steps.append({"step": name, "ok": bool(ok), "detail": detail, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        print(f"{'PASS' if ok else 'FAIL'} {name}", flush=True)
        self.write("steps.json", self.steps)
        return bool(ok)

    def write(self, name: str, data: Any) -> None:
        path = self.evidence / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http_json(url: str, token: str | None = None) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - run-owned loopback entry
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def wait_until(check: Callable[[], bool], timeout: float, interval: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return True
        except Exception:  # noqa: BLE001 - a probe that cannot answer yet is not ready
            pass
        time.sleep(interval)
    return False


def git(*args: str) -> str:
    return text(sh(["git", "-C", str(REPO), *args]))


def tool_versions() -> dict[str, str]:
    def version(args: list[str]) -> str:
        try:
            return text(sh(args, check=False, timeout=60)).splitlines()[0]
        except Exception as error:  # noqa: BLE001
            return f"unavailable: {type(error).__name__}"
    return {"docker": version(["docker", "version", "--format", "{{.Server.Version}}"]),
            "compose": version(["docker", "compose", "version", "--short"]),
            "python": platform.python_version(), "node": version(["node", "--version"]),
            "playwright": version(["npx", "--prefix", str(P03_DIR), "playwright", "--version"])}


def playwright(specs: list[str], *, cwd: Path, env: dict[str, str], log: Path, config: str = "playwright.config.mjs") -> int:
    base = {"PATH": os.environ.get("PATH", os.defpath), "HOME": os.environ.get("HOME", "/tmp"), "LANG": "en_US.UTF-8"}
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as handle:
        return subprocess.run(["npx", "playwright", "test", *specs, "--config", config], cwd=cwd, env={**base, **env},
                              stdout=handle, stderr=handle, timeout=1800).returncode


class Rehearsal:
    def __init__(self, args: argparse.Namespace) -> None:
        self.run_id = local_stack.check_run_id(args.run_id or "l4" + secrets.token_hex(4))
        self.evidence = Path(args.evidence_root).resolve() / self.run_id
        if self.evidence.exists():
            raise SystemExit(f"REFUSED evidence folder {self.evidence} already exists; use a new run ID")
        self.private = self.evidence / "private"
        self.private.mkdir(parents=True, mode=0o700)
        self.rec = Recorder(self.evidence)
        self.args = args
        self.port = free_port()
        from tokens import TestSigner  # scripts/p03 test signer: per-run in-memory P-256 key, trusted only by this run
        self.signer = TestSigner()
        self.tokens = {"a": self.signer.token("did:privy:rehearsal-owner-a"),
                       "b": self.signer.token("did:privy:rehearsal-owner-b")}
        self.build_sha = git("rev-parse", "HEAD")
        key = self.signer.public_pem.replace("\n", "\\n")
        self.passwords = {"primary": secrets.token_urlsafe(24), "restored": secrets.token_urlsafe(24)}
        self.primary = LocalStack(StackNames.primary(self.run_id), local_stack.compose_environment(
            StackNames.primary(self.run_id), port=self.port, db_password=self.passwords["primary"], verification_key=key,
            build_sha=self.build_sha), self.evidence / "logs")
        self.restored = LocalStack(StackNames.restored(self.run_id), local_stack.compose_environment(
            StackNames.restored(self.run_id), port=self.port, db_password=self.passwords["restored"], verification_key=key,
            build_sha=self.build_sha), self.evidence / "logs")
        self.entry = f"http://127.0.0.1:{self.port}"
        self.ui_env = {"P03_WEB_URL": self.entry, "P03_API_URL": self.entry, "P03_TOKEN_A": self.tokens["a"],
                       "P03_TOKEN_B": self.tokens["b"], "P03_TOKEN_REC_DESKTOP": self.tokens["a"],
                       "P03_TOKEN_REC_MOBILE_390": self.tokens["b"], "P03_EVIDENCE_DIR": str(self.evidence / "ui")}
        self.snapshots: dict[str, Any] = {}

    # ---- identity and preflight -------------------------------------------------------------------------------
    def preflight(self) -> bool:
        raw_status = git("status", "--porcelain")
        # `.omc/` is the agent host's own HUD state for the session, untracked and outside the build context.
        status = "\n".join(line for line in raw_status.splitlines() if line != "?? .omc/")
        identity = {"run_id": self.run_id, "commit": self.build_sha, "tree": git("rev-parse", "HEAD^{tree}"),
                    "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "clean": status == "", "raw_status": raw_status,
                    "public_entry": self.entry, "tools": tool_versions(), "platform": platform.platform(),
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "projects": [self.primary.names.project, self.restored.names.project],
                    "databases": [self.primary.names.database, self.restored.names.database],
                    "images": list(self.primary.names.images)}
        identity["build_context"] = image_inspection.build_context_fingerprint(REPO)
        self.rec.write("run-identity.json", identity)
        self.before = local_stack.inventory()
        self.rec.write("resources-before.json", self.before)
        # Daemon create/remove events during the run, so any change to another resource can be attributed by name.
        self.events_log = open(self.evidence / "docker-events.jsonl", "wb")
        self.events = subprocess.Popen(["docker", "events", "--format", "{{json .}}", *[arg for action in (
            "create", "destroy", "delete", "untag", "tag") for arg in ("--filter", f"event={action}")]],
            stdout=self.events_log, stderr=subprocess.DEVNULL)
        ok = self.rec.step("docker daemon answers", sh(["docker", "info"], check=False).returncode == 0)
        ok &= self.rec.step("candidate source is committed and clean", status == "" or self.args.allow_dirty,
                            {"clean": status == "", "allow_dirty": self.args.allow_dirty})
        self.primary.claim(images_must_be_new=True)
        self.restored.claim(images_must_be_new=False)
        return self.rec.step("run-owned projects, databases and image tags are new", True, identity["projects"]) and ok

    # ---- images -------------------------------------------------------------------------------------------------
    def build(self) -> bool:
        started = time.monotonic()
        build = ["build", "--progress", "plain"] + ([] if self.args.cached_build else ["--no-cache"]) + ["api", "web"]
        result = self.primary.run("build", *build, timeout=1800)
        ok = self.rec.step("fresh API and web images build from the committed source with frozen locks",
                           result.returncode == 0, {"exit": result.returncode, "seconds": round(time.monotonic() - started),
                                                    "no_cache": not self.args.cached_build})
        if not ok:
            return False
        api_tag, web_tag = self.primary.names.images
        identities = {tag: image_inspection.image_identity(tag) for tag in (api_tag, web_tag)}
        users = {tag: image_inspection.runtime_user(tag) for tag in (api_tag, web_tag)}
        identities["runtime_users"] = users
        assets = image_inspection.api_assets(api_tag)
        identities["api_runtime_assets"] = assets
        self.rec.write("image-identities.json", identities)
        ok &= self.rec.step("images carry the source commit, the run label and a non-root runtime user",
                            all(identities[tag]["labels"].get("org.opencontainers.image.revision") == self.build_sha
                                and identities[tag]["labels"].get(local_stack.RUN_LABEL) == self.run_id for tag in (api_tag, web_tag))
                            and users[api_tag] == "10001" and users[web_tag] == "1000", users)
        ok &= self.rec.step("API image opens every runtime contract, fixture and support asset (no host source mount)",
                            assets["ok"], assets)
        needles = {"primary_db_password": self.passwords["primary"], "restored_db_password": self.passwords["restored"],
                   "synthetic_public_key_body": self.signer.public_pem.splitlines()[1],
                   "synthetic_private_key_body": self.signer.private_pem.splitlines()[1],
                   "owner_a_token": self.tokens["a"], "owner_b_token": self.tokens["b"]}
        scans = {tag: image_inspection.scan_filesystem(tag, needles) for tag in (api_tag, web_tag)}
        self.rec.write("image-secret-scan.json", scans)
        return self.rec.step("no run secret, key, token or private-key block in either image; no fixture label in the "
                             "web bundle", all(scan["clean"] for scan in scans.values()),
                             {tag: {"files": scan["files_scanned"], "clean": scan["clean"]} for tag, scan in scans.items()}) and ok

    # ---- startup guards ------------------------------------------------------------------------------------------
    def guarded_startup(self) -> bool:
        stack = self.primary
        ok = self.rec.step("private PostgreSQL 18 starts healthy on its named volume",
                           stack.run("up-postgres", "up", "-d", "--no-build", "--wait", "postgres").returncode == 0)
        api_early = stack.run("api-before-migration", "run", "--rm", "--no-deps", "-T", "api")
        message = (api_early.stderr or b"").decode("utf-8", "replace")
        ok &= self.rec.step("API refuses to serve before the explicit migration (schema not at head)",
                            api_early.returncode != 0 and "does not match migration head" in message,
                            {"exit": api_early.returncode})
        drift = {name: stack.run(f"{name}-before-migration", "run", "--rm", "--no-deps", "-T", name, *command).returncode
                 for name, command in WORKER_COMMANDS.items()}
        ok &= self.rec.step("each worker role stops with exit 3 before any effect on an unmigrated schema",
                            all(code == 3 for code in drift.values()), drift)
        production = stack.run("api-production-refusal", "run", "--rm", "--no-deps", "-T", "-e", "EDGE_OS_ENV=production", "api")
        forbidden = stack.run("api-forbidden-name", "run", "--rm", "--no-deps", "-T", "-e", "EDGE_OS_PRIVY_APP_SECRET=refuse-me", "api")
        texts = [(item.stderr or b"").decode("utf-8", "replace") for item in (production, forbidden)]
        ok &= self.rec.step("the LOCAL fixture profile is refused as production (TLS, fixtures, test app id) and a "
                            "Privy app secret name is refused", production.returncode != 0 and "sslmode=require" in texts[0]
                            and "fixture" in texts[0] and forbidden.returncode != 0
                            and "unsupported configuration present: EDGE_OS_PRIVY_APP_SECRET" in texts[1]
                            and not any(self.passwords["primary"] in item for item in texts),
                            {"production_exit": production.returncode, "forbidden_exit": forbidden.returncode})
        migrate = stack.run("migrate", "run", "--rm", "-T", "migrate", timeout=300)
        head = stack.rows("select version_num from alembic_version")
        self.schema_head = [row["version_num"] for row in head]
        ok &= self.rec.step("one explicit migration step reaches head and `alembic check` finds no difference",
                            migrate.returncode == 0 and len(self.schema_head) == 1, {"exit": migrate.returncode, "head": self.schema_head})
        return ok

    def start_applications(self, stack: LocalStack, label: str) -> bool:
        up = stack.run(f"up-apps-{label}", "up", "-d", "--no-build", "--wait", "--wait-timeout", "180", *APP_ROLES, timeout=300)
        health = http_json(f"{self.entry}/healthz")
        ready = http_json(f"{self.entry}/readyz")
        return self.rec.step(f"{label}: API, web and entry are healthy; /readyz is ready at the schema head through the "
                             "loopback entry", up.returncode == 0 and health[0] == 200 and health[1]["build_sha"] == self.build_sha
                             and ready == (200, {"status": "ready", "schema_revision": self.schema_head[0]}),
                             {"healthz": health, "readyz": ready})

    def topology(self, stack: LocalStack, label: str) -> bool:
        details: dict[str, Any] = {}
        ok = True
        for service, container in stack.container_ids().items():
            info = json.loads(text(sh(["docker", "inspect", container])))[0]
            bindings = {port: [(item["HostIp"], item["HostPort"]) for item in values or []]
                        for port, values in (info["HostConfig"].get("PortBindings") or {}).items()}
            mounts = [(mount["Type"], mount.get("Name") or mount.get("Source")) for mount in info["Mounts"]]
            user = text(sh(["docker", "exec", container, "id", "-u"], check=False)) if info["State"]["Running"] else None
            details[service] = {"bindings": bindings, "mounts": mounts, "user": user,
                                "networks": sorted(info["NetworkSettings"]["Networks"]), "read_only": info["HostConfig"]["ReadonlyRootfs"],
                                "cap_drop": info["HostConfig"]["CapDrop"], "privileged": info["HostConfig"]["Privileged"]}
            ok &= not info["HostConfig"]["Privileged"] and not any("docker.sock" in str(m) for m in mounts)
            ok &= all(kind == "volume" for kind, _ in mounts)
            if service == "entry":
                ok &= bindings == {"8080/tcp": [("127.0.0.1", str(self.port))]}
            else:
                ok &= bindings == {}
            if service in {"api", "entry", "web"}:
                ok &= user in {"10001", "1000"}
        private = json.loads(text(sh(["docker", "network", "inspect", f"{stack.names.project}_private"])))[0]
        details["private_network_internal"] = private["Internal"]
        ok &= private["Internal"] is True
        self.rec.write(f"topology-{label}.json", details)
        return self.rec.step(f"{label}: only the entry publishes a port (127.0.0.1), application containers run as "
                             "non-root on an internal network, no host path or Docker socket is mounted", ok,
                             {name: value for name, value in details.items() if name != "private_network_internal"})

    # ---- seeded journeys -----------------------------------------------------------------------------------------
    def jobs_settled(self, stack: LocalStack) -> bool:
        return stack.rows("select count(*) n from research_local.investigation_jobs "
                          "where state in ('QUEUED', 'RESERVED', 'COLLECTING', 'EVALUATING')")[0]["n"] == 0

    def run_worker_until_settled(self, stack: LocalStack, label: str) -> bool:
        stack.run(f"research-worker-up-{label}", "up", "-d", "--no-build", "research-worker")
        settled = wait_until(lambda: self.jobs_settled(stack), timeout=240, interval=2)
        stack.run(f"research-worker-stop-{label}", "stop", "research-worker")
        return settled

    def seed(self) -> bool:
        stack = self.primary
        ui = self.evidence / "ui"
        code = playwright(["research-history-journey.spec.mjs"], cwd=P03_DIR, env=self.ui_env, log=ui / "seed-research-journey.log")
        ok = self.rec.step("seed: accepted recorded-history journey through the packaged web/API (desktop and 390px; "
                           "no worker running)", code == 0, {"exit": code})
        if not ok:
            return False
        from research_phase import KILL_SCRIPT  # verifier-only fault: the collection tool ends the process
        results = json.loads((ui / "research-results.json").read_text())
        killed = {key: stack.run(f"killed-{key}", "run", "--rm", "--no-deps", "-T", "research-worker", "python", "-c",
                                 KILL_SCRIPT, run["jobs"]["killed"]).returncode for key, run in results.items()}
        ok &= self.rec.step("fault: a research worker container is killed after its collection attempt is saved (exit 9)",
                            bool(killed) and all(value == 9 for value in killed.values()), killed)
        ok &= self.rec.step("packaged research-worker role advances the saved jobs to terminal states",
                            self.run_worker_until_settled(stack, "1"))
        code = playwright(["research-history-report.spec.mjs"], cwd=P03_DIR, env=self.ui_env, log=ui / "seed-research-report.log")
        ok &= self.rec.step("seed: reports, killed-job reconciliation, retry, market adoption, revision and labelled "
                            "replay through the packaged stack", code == 0, {"exit": code})
        ok &= self.rec.step("packaged research-worker role finishes the retried job",
                            self.run_worker_until_settled(stack, "2"))
        code = playwright(["recurring-journey.spec.mjs"], cwd=P03_DIR, env=self.ui_env, log=ui / "seed-recurring-journey.log")
        ok &= self.rec.step("seed: two owners start recurring operation through the packaged screens", code == 0, {"exit": code})
        stack.run("recurring-up", "up", "-d", "--no-build", "execution-worker", "recurring-producer")
        occurred = wait_until(lambda: stack.rows(
            "select count(*) n from execution_local.execution_recurring_deployments where occurrences < 1")[0]["n"] == 0
            and stack.rows("select count(*) n from execution_local.execution_recurring_deployments")[0]["n"] == 2,
            timeout=180, interval=3)
        stack.run("recurring-stop", "stop", "execution-worker", "recurring-producer")
        ok &= self.rec.step("packaged recurring-producer and execution-worker roles record an occurrence for each "
                            "deployment with no browser open", occurred)
        running = text(stack.compose("ps", "--status", "running", "--format", "{{.Service}}")).splitlines()
        return self.rec.step("worker roles are stopped before the identity snapshot",
                             not any(name in WORKER_COMMANDS for name in running), running) and ok

    # ---- snapshots, replacement, backup and restore ----------------------------------------------------------------
    def snapshot(self, stack: LocalStack, name: str) -> dict[str, Any]:
        taken = identity_snapshot.take(stack.rows)
        self.snapshots[name] = taken
        self.rec.write(f"identities/{name}.json", taken)
        return taken

    def reopen(self, stage: str) -> int:
        work = self.evidence / f"browser-{stage}"
        work.mkdir(parents=True)
        for item in BROWSER_DIR.glob("*.mjs"):
            shutil.copy(item, work / item.name)
        (work / "node_modules").symlink_to(P03_DIR / "node_modules", target_is_directory=True)
        env = {**self.ui_env, "REHEARSAL_STAGE": stage, "REHEARSAL_EVIDENCE_DIR": str(work / "evidence"),
               "REHEARSAL_EXPECTED": str(self.evidence / "identities" / "seeded.json")}
        return playwright([], cwd=work, env=env, log=work / "playwright.log")

    def replacement(self) -> bool:
        stack = self.primary
        before_ids = stack.container_ids()
        before_health = http_json(f"{self.entry}/healthz")[1]
        stack.run("restart-postgres", "restart", "postgres", timeout=180)
        recreate = stack.run("recreate-apps", "up", "-d", "--no-build", "--force-recreate", "--wait", "--wait-timeout", "180",
                             *APP_ROLES, timeout=300)
        after_ids = stack.container_ids()
        after_health = http_json(f"{self.entry}/healthz")[1]
        replaced = all(before_ids.get(role) != after_ids.get(role) for role in APP_ROLES)
        ok = self.rec.step("process replacement: API, web and entry containers are recreated and PostgreSQL restarts on "
                           "the same named volume", recreate.returncode == 0 and replaced
                           and before_health["started_at"] != after_health["started_at"],
                           {"before": {r: before_ids.get(r, "")[:12] for r in APP_ROLES},
                            "after": {r: after_ids.get(r, "")[:12] for r in APP_ROLES},
                            "api_started_at": [before_health["started_at"], after_health["started_at"]]})
        after = self.snapshot(stack, "after-replacement")
        diff = identity_snapshot.differences(self.snapshots["seeded"], after)
        ok &= self.rec.step("durability: every saved identity and table hash is unchanged after replacement", diff == [], diff)
        code = self.reopen("after-replacement")
        ok &= self.rec.step("browser reopen after replacement (GET only; desktop 1280 and 390px; keyboard, labels, "
                            "overflow, other-owner error)", code == 0, {"exit": code})
        diff = identity_snapshot.differences(self.snapshots["seeded"], self.snapshot(stack, "after-replacement-reopen"))
        return self.rec.step("the reopen created, changed and reset nothing (direct SQL)", diff == [], diff) and ok

    def backup_and_restore(self) -> bool:
        dump = self.private / f"{self.primary.names.database}.dump"
        backup = restore_drill.backup(self.primary, dump)
        ok = self.rec.step("private custom-format backup of the primary database (source only read)",
                           backup["bytes"] > 0 and backup["toc_entries"] > 0, backup)
        stopped = self.primary.run("stop-primary", "stop", timeout=180)
        ok &= self.rec.step("primary stack stopped (volumes kept until cleanup) before the restored stack takes the "
                            "loopback entry", stopped.returncode == 0)
        restored = self.restored
        ok &= self.rec.step("restored stack: fresh PostgreSQL with a new run-named database and password",
                            restored.run("up-postgres", "up", "-d", "--no-build", "--wait", "postgres").returncode == 0,
                            {"database": restored.names.database})
        try:
            restore = restore_drill.restore(restored, dump, source_database=self.primary.names.database)
            ok &= self.rec.step("guarded restore into the empty, uniquely named database", True, restore)
        except (restore_drill.RestoreRefused, RuntimeError) as error:
            return self.rec.step("guarded restore into the empty, uniquely named database", False, str(error))
        check = restored.run("restored-alembic-check", "run", "--rm", "-T", "migrate", "python", "-m", "alembic", "check")
        head = [row["version_num"] for row in restored.rows("select version_num from alembic_version")]
        ok &= self.rec.step("restored schema is at the same head and `alembic check` passes (no upgrade ran)",
                            check.returncode == 0 and head == self.schema_head, {"exit": check.returncode, "head": head})
        ok &= self.start_applications(restored, "restored")
        ok &= self.topology(restored, "restored")
        diff = identity_snapshot.differences(self.snapshots["seeded"], self.snapshot(restored, "restored"))
        ok &= self.rec.step("restored identities equal the pre-backup identities (schema head, requests, revisions, "
                            "reports, replays, deployments, jobs, caps, reservations, held unknown, every table hash)",
                            diff == [], diff)
        workers = [service for service in restored.container_ids() if service in WORKER_COMMANDS]
        ok &= self.rec.step("no worker role runs on the restored stack (no new effects)", workers == [], workers)
        code = self.reopen("restored")
        ok &= self.rec.step("browser reopen on the restored stack (GET only; desktop 1280 and 390px; keyboard, labels, "
                            "overflow, other-owner error)", code == 0, {"exit": code})
        diff = identity_snapshot.differences(self.snapshots["seeded"], self.snapshot(restored, "restored-after-reopen"))
        return self.rec.step("the restored reopen created, changed and reset nothing (direct SQL)", diff == [], diff) and ok

    # ---- cleanup ---------------------------------------------------------------------------------------------------
    def cleanup(self) -> bool:
        for stack in (self.restored, self.primary):
            stack.down()
        # Image tags are removed only when this run claimed them as new; a refused claim removes nothing.
        remaining = local_stack.remove_run_images(self.primary.names) if self.primary.claimed else []
        after = local_stack.inventory()
        if getattr(self, "events", None) is not None:
            time.sleep(1)  # let the daemon deliver the cleanup's own remove events
            self.events.terminate()
            self.events.wait(timeout=10)
            self.events_log.close()
        self.rec.write("resources-after.json", after)
        leftovers = local_stack.leftovers(after, run_id=self.run_id) + [f"image:{tag}" for tag in remaining]
        foreign = local_stack.foreign_changes(self.before, after, run_id=self.run_id)
        return self.rec.step("cleanup removed exactly this run's containers, volumes, networks and images; no other "
                             "resource changed", leftovers == [] and foreign == [], {"leftovers": leftovers, "foreign": foreign})

    def run(self) -> bool:
        ok = False
        try:
            ok = self.preflight() and self.build() and self.guarded_startup()
            ok = ok and self.start_applications(self.primary, "primary") and self.topology(self.primary, "primary")
            ok = ok and self.seed()
            if ok:
                self.snapshot(self.primary, "seeded")
                ok = self.replacement() and ok
                ok = self.backup_and_restore() and ok
        except Exception as error:  # noqa: BLE001 - every failure still reaches cleanup and the final line
            self.rec.step("unexpected error", False, f"{type(error).__name__}: {error}"[:400])
            ok = False
        except KeyboardInterrupt:
            self.rec.step("interrupted; owned resources are cleaned up next", False)
            ok = False
        finally:
            # A second interrupt must not cut the cleanup of this run's own resources short.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            if self.args.keep:
                self.rec.step("resources kept for inspection (--keep); this run is not a pass", False)
                ok = False
            else:
                ok = self.cleanup() and ok
        summary = {"ok": ok, "run_id": self.run_id, "commit": self.build_sha, "evidence": str(self.evidence),
                   "steps": len(self.rec.steps), "failed": [s["step"] for s in self.rec.steps if not s["ok"]]}
        self.rec.write("summary.json", summary)
        print(json.dumps(summary), flush=True)
        return ok


def _interrupt(*_: Any) -> None:
    raise KeyboardInterrupt


def main() -> None:
    signal.signal(signal.SIGTERM, _interrupt)  # a polite stop takes the same cleanup path as Ctrl-C
    parser = argparse.ArgumentParser(description="LOCAL Docker packaging, restore and restart rehearsal.")
    parser.add_argument("--run-id", help="4 to 20 lowercase letters or digits (default: generated)")
    parser.add_argument("--evidence-root", default=str(REPO / ".scratch" / "deployment-rehearsal"),
                        help="private folder for evidence, logs and the backup (never committed)")
    parser.add_argument("--cached-build", action="store_true", help="development only: allow the Docker layer cache")
    parser.add_argument("--allow-dirty", action="store_true", help="development only: run on uncommitted source")
    parser.add_argument("--keep", action="store_true", help="development only: keep resources; never a pass")
    sys.exit(0 if Rehearsal(parser.parse_args()).run() else 1)


if __name__ == "__main__":
    main()
