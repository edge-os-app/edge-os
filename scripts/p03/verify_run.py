#!/usr/bin/env python3
"""Run the mapped P03 verification path against a fresh isolated instance and keep the evidence.

Run it with the API toolchain's interpreter so `cryptography` and `jwt` are available:

    cd apps/api && uv run --frozen python ../../scripts/p03/verify_run.py

Steps: environment record, PostgreSQL 18, migrations, API start and health, production web build and start,
API drive (auth and ownership), UI drive in a real browser, SQL record inspection, API restart and reopen in a new
browser context, log scan, production-bundle scan, then cleanup of exactly the resources this run created.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
from tokens import OWNER_A, OWNER_B, OWNER_C, TestSigner  # noqa: E402

THESIS = ("Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. "
          "Spot only.")


class Recorder:
    def __init__(self, directory: Path):
        self.directory, self.steps = directory, []
        directory.mkdir(parents=True, exist_ok=True)

    def step(self, name: str, ok: bool, detail: object = None) -> bool:
        self.steps.append({"step": name, "ok": ok, "detail": detail, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        (self.directory / "steps.json").write_text(json.dumps(self.steps, indent=2, default=str))
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        return ok

    def write(self, name: str, value: object) -> None:
        (self.directory / name).write_text(value if isinstance(value, str) else json.dumps(value, indent=2, default=str))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_version(args: list[str]) -> str:
    try:
        return harness.sh(args, check=False).stdout.strip().splitlines()[0]
    except Exception as error:  # noqa: BLE001
        return f"unavailable: {type(error).__name__}"


def docker_resources(run_id: str) -> dict[str, list[str]]:
    """Containers and volumes that are not another run's. Unlabelled resources (the user's) and this run's are
    compared, so a parallel labelled run cannot cause a false failure while an unrelated change still shows."""
    def keep(listing: str) -> list[str]:
        names = []
        for line in listing.splitlines():
            name, _, owner = line.partition("\t")
            if name and owner in ("", run_id):
                names.append(name)
        return sorted(names)
    containers = harness.sh(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Label \"edge-os.test.run\"}}"], check=False).stdout
    volumes = harness.sh(["docker", "volume", "ls", "--format", "{{.Name}}\t{{.Label \"edge-os.test.run\"}}"], check=False).stdout
    return {"containers": keep(containers), "volumes": keep(volumes)}


def http(method: str, url: str, token: str | None = None, body: object = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - loopback only
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def environment_record(pg: harness.Postgres) -> dict:
    lock = json.loads((harness.WEB_DIR / "package-lock.json").read_text())
    packages = lock["packages"]
    return {
        "git_head": harness.git_sha(),
        "python": sys.version.split()[0], "uv": tool_version(["uv", "--version"]),
        "node": tool_version(["node", "--version"]), "npm": tool_version(["npm", "--version"]),
        "docker_server": tool_version(["docker", "version", "--format", "{{.Server.Version}}"]),
        "postgres_server_version": pg.version(), "postgres_image": pg.image_identity(),
        "uv_lock_sha256": sha256_file(harness.API_DIR / "uv.lock"),
        "package_lock_sha256": sha256_file(harness.WEB_DIR / "package-lock.json"),
        "web_versions": {name: packages[f"node_modules/{name}"]["version"] for name in
                         ("next", "react", "react-dom", "@privy-io/react-auth", "typescript")},
        "playwright": tool_version(["npx", "--prefix", str(harness.REPO / "tests" / "p03"), "playwright", "--version"]),
    }


def scan_bundle(dist: Path) -> dict:
    """T12: the production output must not contain the fixture provider or key material."""
    texts = {p: p.read_bytes() for p in dist.rglob("*") if p.is_file() and p.suffix in {".js", ".html", ".json", ".css", ".map"}}
    def found(needle: bytes) -> list[str]:
        return sorted(str(p.relative_to(dist)) for p, data in texts.items() if needle in data)
    pem_body = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----[\\nA-Za-z0-9+/=\s]{40,}")
    return {
        "fixture_label_in_bundle": found(b"TEST AUTH FIXTURE"),
        "private_key_blocks_in_bundle": sorted(str(p.relative_to(dist)) for p, data in texts.items() if pem_body.search(data)),
        "privy_create_on_login_off_literals": sum(len(re.findall(rb'createOnLogin:\s*"off"', data)) for data in texts.values()),
        "files_scanned": len(texts),
    }


def seed_account_fixtures(pg: harness.Postgres, api_url: str, token_a: str) -> dict:
    """Seed authored P19 rows after verified fixture owners exist; never expose a production write route."""
    owner = http("GET", f"{api_url}/v1/me", token_a)
    if owner[0] != 200:
        raise RuntimeError("could not resolve the verified P19 fixture owner")
    owner_id = owner[1]["user_id"]
    fixture_path = harness.API_DIR / "tests" / "fixtures" / "account_views" / "account-records-v1.json"
    fixture = json.loads(fixture_path.read_text())
    second_agent = json.loads(json.dumps(fixture[0]))
    second_agent["record_id"] = "00000000-0000-4000-8000-000000000021"
    second_agent["operation_id"] = "10000000-0000-4000-8000-000000000021"
    second_agent["content"].update(agent_id="agent-b", wallet_id="wallet-b", status="STOPPED",
                                   permission_state="REMOVED", updated_at="2026-10-09T12:01:00Z")
    fixture.append(second_agent)
    orphan_source_ids = {
        "monitoring_first_page": "00000000-0000-4000-8000-000000000301",
        "permission_first_page": "00000000-0000-4000-8000-000000000302",
        "monitoring_later_page": "00000000-0000-4000-8000-000000000303",
        "permission_later_page": "00000000-0000-4000-8000-000000000304",
    }
    def orphan_source(kind: str, agent_id: str, wallet_id: str, record_id: str, updated_at: str) -> dict:
        template = next(item for item in fixture if item["content"].get("record_kind") == kind)
        source = json.loads(json.dumps(template))
        source["record_id"] = record_id
        source["operation_id"] = record_id.replace("00000000", "10000000")
        source["content"].update(agent_id=agent_id, wallet_id=wallet_id, updated_at=updated_at,
                                 strategy_revision=f"strategy-{agent_id}-v4", mandate_id=f"mandate-{agent_id}-v2")
        if kind == "MONITORING":
            source["content"].update(next_work=f"inspect saved {agent_id}", blocking_reason="synthetic source has no agent summary")
        else:
            source["content"].update(approval_id=f"approval-{agent_id}-v1", predecessor_approval_id=None,
                                      successor_approval_id=None, signer_binding=f"signer-{agent_id}-v1",
                                      policy_binding=f"policy-{agent_id}-v1")
            canonical_terms = json.dumps(source["content"]["terms"], sort_keys=True, separators=(",", ":"))
            source["content"]["terms_hash"] = "sha256:" + hashlib.sha256(canonical_terms.encode("utf-8")).hexdigest()
        return source
    fixture.extend([
        orphan_source("MONITORING", "orphan-monitoring-first", "wallet-orphan-monitoring-first",
                      orphan_source_ids["monitoring_first_page"], "2026-10-09T12:02:00Z"),
        orphan_source("PERMISSION_SNAPSHOT", "orphan-permission-first", "wallet-orphan-permission-first",
                      orphan_source_ids["permission_first_page"], "2026-10-09T12:03:00Z"),
    ])
    target_position = next(item for item in fixture if item["content"].get("record_kind") == "POSITION"
                           and item["content"].get("position_id") == "position-a-2")
    target_action = next(item for item in fixture if item["content"].get("record_kind") == "ACTION"
                         and item["content"].get("action_id") == "action-a-failed-2")
    fixture.remove(target_position)
    fixture.remove(target_action)
    filler_template = next(item for item in fixture if item["content"].get("record_kind") == "MONITORING")
    for index in range(100):
        filler = json.loads(json.dumps(filler_template))
        filler["record_id"] = f"00000000-0000-4000-8000-{index + 100:012d}"
        filler["operation_id"] = f"10000000-0000-4000-8000-{index + 100:012d}"
        filler["content"].update(agent_id=f"fixture-monitor-{index:03d}", wallet_id=f"fixture-wallet-{index:03d}",
                                  updated_at=f"2026-10-09T13:{index // 60:02d}:{index % 60:02d}Z")
        fixture.append(filler)
    target_position_b = json.loads(json.dumps(target_position))
    target_position_b["record_id"] = "00000000-0000-4000-8000-000000000200"
    target_position_b["operation_id"] = "10000000-0000-4000-8000-000000000200"
    target_position_b["content"].update(agent_id="agent-b", wallet_id="wallet-b", position_id="position-b-paged",
                                         strategy_revision="strategy-b-v1", mandate_id="mandate-b-v1")
    target_action_b = json.loads(json.dumps(target_action))
    target_action_b["record_id"] = "00000000-0000-4000-8000-000000000201"
    target_action_b["operation_id"] = "10000000-0000-4000-8000-000000000201"
    target_action_b["content"].update(agent_id="agent-b", wallet_id="wallet-b", position_id="position-b-paged",
                                       strategy_revision="strategy-b-v1", mandate_id="mandate-b-v1",
                                       action_id="action-b-failed-paged")
    fixture.extend([target_position, target_action, target_position_b, target_action_b,
        orphan_source("MONITORING", "orphan-monitoring-later", "wallet-orphan-monitoring-later",
                      orphan_source_ids["monitoring_later_page"], "2026-10-09T13:30:00Z"),
        orphan_source("PERMISSION_SNAPSHOT", "orphan-permission-later", "wallet-orphan-permission-later",
                      orphan_source_ids["permission_later_page"], "2026-10-09T13:31:00Z")])
    for item in fixture:
        content = {**item["content"], "owner_id": owner_id}
        statement = (
            "insert into records(record_id, owner_id, record_type, schema_version, operation_id, created_at, content) values ("
            f"'{item['record_id']}', '{owner_id}', 'AccountViewRecord', '{item.get('schema_version', 'account-view/1')}', '{item['operation_id']}', "
            f"'{item['content']['updated_at']}'::timestamptz, {sql_literal(json.dumps(content, separators=(',', ':')))}::jsonb)"
        )
        pg.psql(statement)
    research_status, research_bundle = http("POST", f"{api_url}/v1/research/requests", token_a, {
        "original_request": "Synthetic source for the P19 owner-context navigation test.",
        "restrictions": ["synthetic fixture only"], "requested_job": "CREATE_STRATEGY", "input_class": "CONCRETE_THESIS",
    })
    if research_status != 201:
        raise RuntimeError("could not create the authenticated synthetic Research source")
    research_source_id = research_bundle["intake"]["record_id"]
    if http("GET", f"{api_url}/v1/research/requests/{research_source_id}", token_a)[0] != 200:
        raise RuntimeError("authenticated synthetic Research source did not reopen")
    context = json.loads((fixture_path.parent / "agent-context-v1.json").read_text())
    context.update(owner_id=owner_id, agent_id="agent-a")
    context["entries"][-1]["source_refs"] = [target_action["record_id"], research_source_id]
    def seed_context(agent_id: str, record_id: str, operation_id: str, source_id: str, created_at: str) -> None:
        saved_context = json.loads(json.dumps(context))
        saved_context.update(agent_id=agent_id)
        saved_context["entries"][-1]["source_refs"] = [source_id, research_source_id]
        saved_context["entries"][-1]["source_refs"].extend(orphan_source_ids.values())
        pg.psql(
            "insert into records(record_id, owner_id, record_type, schema_version, operation_id, created_at, content) values ("
            f"'{record_id}', '{owner_id}', 'AgentContextRecord', 'agent-context/1', '{operation_id}', "
            f"'{created_at}'::timestamptz, {sql_literal(json.dumps(saved_context, separators=(',', ':')))}::jsonb)"
        )
    seed_context("agent-a", "20000000-0000-4000-8000-000000000001", "20000000-0000-4000-8000-000000000101",
                 target_action["record_id"], "2026-10-09T12:00:00Z")
    seed_context("agent-b", "20000000-0000-4000-8000-000000000002", "20000000-0000-4000-8000-000000000102",
                 target_action_b["record_id"], "2026-10-09T12:01:00Z")
    return {"owner_id": owner_id, "record_ids": [item["record_id"] for item in fixture],
            "agent_record_ids": {"agent-a": fixture[0]["record_id"], "agent-b": second_agent["record_id"]},
            "research_source_id": research_source_id,
            "orphan_source_ids": orphan_source_ids,
            "source_action_ids": {"agent-a": target_action["record_id"], "agent-b": target_action_b["record_id"]},
            "source_position_ids": {"agent-a": target_position["record_id"], "agent-b": target_position_b["record_id"]},
            "position_record_ids": {"position-a-1": next(item["record_id"] for item in fixture if item["content"].get("position_id") == "position-a-1"),
                                     "position-a-2": target_position["record_id"]},
            "financial_fixture": fixture,
            "account_snapshot": account_history_snapshot(pg, owner_id)}


def run_playwright(specs: list[str], env_extra: dict[str, str], log: Path) -> int:
    env = harness.base_env()
    env.update(env_extra)
    result = subprocess.run(["npx", "playwright", "test", "--config", "playwright.config.mjs", *specs],
                            cwd=harness.REPO / "tests" / "p03", env=env, capture_output=True, text=True, timeout=900)
    log.write_text(result.stdout + result.stderr)
    return result.returncode


def preflight_present(pg: harness.Postgres, evidence: Path, paths: tuple[Path, ...]) -> list[str]:
    present = pg.existing_resources()
    present += [f"path {p}" for p in paths if p.exists()]
    present += [f"evidence {evidence}"] if evidence.exists() and any(evidence.iterdir()) else []
    return present


def release_owned(owned: list[Path]) -> None:
    for path in owned:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=harness.new_run_id())
    parser.add_argument("--evidence-root", default=str(harness.REPO / ".scratch" / "p03" / "evidence"))
    parser.add_argument("--skip-ui", action="store_true", help="skip the browser steps (not a full pass)")
    parser.add_argument("--hold-seconds", type=int, default=0,
                        help="keep the instance up this long after the drive so an inspector can run SQL, then clean up")
    args = parser.parse_args()
    try:
        run_id = harness.check_run_id(args.run_id)
    except ValueError as error:
        print(f"REFUSED: {error}")
        return 2
    evidence = Path(args.evidence_root) / run_id
    pg = harness.Postgres(run_id)
    dist = f".next-{run_id}"
    dist_path = harness.WEB_DIR / dist
    tsconfig_copy = harness.WEB_DIR / harness.web_tsconfig(dist)
    # A repeated run ID must never touch what an earlier run owns: refuse before creating or deleting anything.
    present = preflight_present(pg, evidence, (dist_path, tsconfig_copy))
    if present:
        print(f"REFUSED run {run_id}: {', '.join(present)} already exists. Nothing was created or changed. Use a new run ID.")
        return 2
    # The check above is not a claim: another caller with this run ID can pass it too. Claim the build folder and the
    # tsconfig copy by exclusive creation, and remove later only what this call created.
    owned: list[Path] = []
    try:
        dist_path.mkdir()
        owned.append(dist_path)
        tsconfig_copy.open("x").close()
        owned.append(tsconfig_copy)
    except FileExistsError as error:
        release_owned(owned)
        print(f"REFUSED run {run_id}: {error.filename} already exists. Nothing was created or changed. Use a new run ID.")
        return 2
    rec = Recorder(evidence)
    processes: list[harness.Process] = []
    before = docker_resources(run_id)
    rec.write("resources-before.json", before)
    signer = TestSigner()
    ok = True
    try:
        pg.start()
        rec.write("environment.json", environment_record(pg))
        ok &= rec.step("postgres started (isolated, labelled)", True, {"container": pg.container, "version": pg.version()})

        locks = {}
        for name, command, cwd in (("api uv.lock", ["uv", "lock", "--check"], harness.API_DIR),
                                   ("web package-lock.json", ["npm", "ci", "--dry-run", "--no-audit", "--no-fund"], harness.WEB_DIR),
                                   ("browser-check package-lock.json", ["npm", "ci", "--dry-run", "--no-audit", "--no-fund"],
                                    harness.REPO / "tests" / "p03")):
            result = subprocess.run(command, cwd=cwd, env={**harness.base_env()}, capture_output=True, text=True)
            locks[name] = result.returncode == 0
        rec.write("lockfiles.json", locks)
        ok &= rec.step("lockfiles install cleanly (uv lock --check, npm ci --dry-run)", all(locks.values()), locks)

        api_port, web_port = harness.free_port(), harness.free_port()
        api_url, web_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
        env = harness.api_env(database_url=pg.url, public_pem=signer.public_pem, previous_pem=None, cors=[web_url])

        migration = harness.migrate(env)
        rec.write("migrate.log", migration.stdout + migration.stderr)
        check_env = harness.base_env(); check_env["EDGE_OS_DATABASE_URL"] = pg.url
        check = subprocess.run([harness.api_python(), "-m", "alembic", "check"], cwd=harness.API_DIR, env=check_env,
                               capture_output=True, text=True)
        rec.write("alembic-check.log", check.stdout + check.stderr)
        ok &= rec.step("migrations applied; models and migrations agree", migration.returncode == 0 and check.returncode == 0)

        api = harness.start_api(env, api_port, evidence / "logs")
        processes.append(api)
        harness.wait_http(f"{api_url}/readyz")
        status, health = http("GET", f"{api_url}/healthz")
        _, ready = http("GET", f"{api_url}/readyz")
        rec.write("health.json", {"healthz": health, "readyz": ready})
        ok &= rec.step("API health and readiness", status == 200 and ready.get("status") == "ready", ready)

        build = harness.build_web(api_url=api_url, dist=dist, log_dir=evidence / "logs")
        ok &= rec.step("web production build", build.returncode == 0, {"dist": dist})
        if build.returncode != 0:
            # Fall through to the cleanup and the final JSON line, so a waiting reader is never left without an end.
            raise RuntimeError("web build failed; see logs/")
        bundle = scan_bundle(dist_path)
        rec.write("bundle-scan.json", bundle)
        ok &= rec.step("production bundle has no fixture provider or key", not bundle["fixture_label_in_bundle"]
                       and not bundle["private_key_blocks_in_bundle"] and bundle["privy_create_on_login_off_literals"] >= 2, bundle)
        web = harness.start_web(api_url=api_url, dist=dist, port=web_port, log_dir=evidence / "logs")
        processes.append(web)
        harness.wait_http(web_url + "/")
        ok &= rec.step("web health", True, {"url": web_url})

        token_a, token_b, token_c = signer.token(OWNER_A), signer.token(OWNER_B), signer.token(OWNER_C)
        token_bad = TestSigner().token(OWNER_A)
        p19_fixtures = seed_account_fixtures(pg, api_url, token_a)
        rec.write("p19-fixtures.json", {k: v for k, v in p19_fixtures.items() if k != "financial_fixture"})
        ok &= rec.step("P19 authored account and context fixtures seeded for the verified owner",
                       len(p19_fixtures["record_ids"]) == len(json.loads((harness.API_DIR / "tests" / "fixtures" / "account_views" / "account-records-v1.json").read_text())) + 107,
                       {"records": len(p19_fixtures["record_ids"])})

        status_none, _ = http("GET", f"{api_url}/v1/me")
        status_bad, _ = http("GET", f"{api_url}/v1/me", token_bad)
        ok &= rec.step("API rejects missing and wrong-key credentials", (status_none, status_bad) == (401, 401), [status_none, status_bad])

        if not args.skip_ui:
            ui_env = {"P03_WEB_URL": web_url, "P03_API_URL": api_url, "P03_TOKEN_A": token_a, "P03_TOKEN_B": token_b, "P03_TOKEN_C": token_c, "P03_TOKEN_BAD": token_bad,
                      "P19_AGENT_RECORD_ID": p19_fixtures["record_ids"][0],
                      "P19_AGENT_B_RECORD_ID": p19_fixtures["agent_record_ids"]["agent-b"],
                      "P19_FIRST_POSITION_ID": p19_fixtures["position_record_ids"]["position-a-1"],
                      "P19_SECOND_POSITION_ID": p19_fixtures["position_record_ids"]["position-a-2"],
                      "P19_SOURCE_ACTION_ID": p19_fixtures["source_action_ids"]["agent-a"],
                      "P19_SOURCE_ACTION_B_ID": p19_fixtures["source_action_ids"]["agent-b"],
                      "P19_SOURCE_POSITION_ID": p19_fixtures["source_position_ids"]["agent-a"],
                      "P19_SOURCE_POSITION_B_ID": p19_fixtures["source_position_ids"]["agent-b"],
                      "P19_ORPHAN_SOURCE_IDS": json.dumps(p19_fixtures["orphan_source_ids"]),
                      "P19_RESEARCH_SOURCE_ID": p19_fixtures["research_source_id"],
                      "P19_ACCOUNT_RECORD_COUNT": str(len(p19_fixtures["record_ids"])),
                      "P03_EVIDENCE_DIR": str(evidence / "ui")}
            code = run_playwright(["e2e.spec.mjs", "quality.spec.mjs", "provenance.spec.mjs"], ui_env, evidence / "ui-e2e.log")
            ok &= rec.step("browser drive (desktop and 390px)", code == 0, {"exit": code})

            results_path = evidence / "ui" / "ui-results.json"
            results = json.loads(results_path.read_text()) if results_path.exists() else {}
            inspection = sql_inspection(pg, results, p19_fixtures["owner_id"], p19_fixtures["account_snapshot"])
            rec.write("sql-inspection.json", inspection)
            ok &= rec.step("saved records match what the UI submitted (direct SQL)", inspection["all_checks_pass"], inspection["checks"])

            # cross-owner denial against the real saved rows
            denial = ownership_drive(pg, api_url, token_a, token_b)
            rec.write("ownership-drive.json", denial)
            ok &= rec.step("another owner is denied read and mutation of saved rows (a foreign parent reference is covered by the database test)", denial["all_denied"], denial)

            api.stop()
            api = harness.start_api(env, api_port, evidence / "logs", name="api-restarted")
            processes.append(api)
            harness.wait_http(f"{api_url}/readyz")
            ok &= rec.step("API restarted on the same database", True)
            code = run_playwright(["reopen.spec.mjs"], ui_env, evidence / "ui-reopen.log")
            ok &= rec.step("saved revision reopens unchanged after restart (new browser context)", code == 0, {"exit": code})
            after_restart = sql_inspection(pg, results, p19_fixtures["owner_id"], p19_fixtures["account_snapshot"])
            ok &= rec.step("records unchanged by the restart", after_restart["checks"] == inspection["checks"])

        if args.hold_seconds:
            hold = {"web": web_url, "api": api_url, "token_owner_a": token_a,
                    "psql": f"docker exec {pg.container} psql -U postgres -d {pg.database}", "seconds": args.hold_seconds}
            print("HOLD " + json.dumps({k: v for k, v in hold.items() if not k.startswith("token")}), flush=True)
            rec.write("hold.json", {k: v for k, v in hold.items() if not k.startswith("token")})
            time.sleep(args.hold_seconds)

        logs = [p for p in (evidence / "logs").glob("*.log")]
        secrets_seen = [str(p.name) for p in logs if any(t in p.read_text(errors="ignore") for t in (token_a, token_b, token_c, token_bad, signer.private_pem))]
        ok &= rec.step("logs contain no token or private key", not secrets_seen, secrets_seen)
    except Exception as error:  # noqa: BLE001
        rec.step("run aborted", False, f"{type(error).__name__}: {error}")
        ok = False
    finally:
        # Each step runs even if an earlier one raises, so one failure cannot leave the container or build folder behind.
        for process in reversed(processes):
            try:
                process.stop()
            except Exception as error:  # noqa: BLE001
                rec.step(f"stop {process.name}", False, f"{type(error).__name__}: {error}")
                ok = False
        for label, action in (("remove database container and volume", pg.stop_and_remove),
                              ("remove the web build folder and tsconfig copy this run created", lambda: release_owned(owned))):
            try:
                action()
            except Exception as error:  # noqa: BLE001
                rec.step(label, False, f"{type(error).__name__}: {error}")
                ok = False
        after = docker_resources(run_id)
        rec.write("resources-after.json", after)
        clean = pg.leftovers() == [] and after == before and not any(p.exists() for p in owned)
        rec.step("cleanup removed only this run's resources", clean, {"leftovers": pg.leftovers(), "unchanged": after == before})
        ok &= clean
        manifest = {str(p.relative_to(evidence)): sha256_file(p) for p in sorted(evidence.rglob("*")) if p.is_file()}
        rec.write("MANIFEST.json", {"run_id": run_id, "files": manifest})
    print(json.dumps({"run_id": run_id, "evidence": str(evidence), "ok": bool(ok)}))
    return 0 if ok else 1


def account_history_snapshot(pg: harness.Postgres, owner_id: str) -> list[dict]:
    return json.loads(pg.psql(
        "select coalesce(json_agg(to_jsonb(r) order by r.seq), '[]'::json) from records r "
        f"where r.owner_id='{owner_id}' and r.record_type='AccountViewRecord'"
    ))


def sql_inspection(pg: harness.Postgres, results: dict, p19_owner_id: str, p19_account_snapshot: list[dict]) -> dict:
    checks: dict[str, object] = {}
    def rows(sql: str):
        return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))
    checks["users"] = rows("select count(*) c from users")[0]["c"]
    checks["records_by_type"] = {r["record_type"]: r["c"] for r in rows(
        "select record_type, count(*) c from records group by record_type order by 1")}
    checks["revisions"] = rows("select count(*) c from strategy_revisions")[0]["c"]
    current_p19_accounts = account_history_snapshot(pg, p19_owner_id)
    def context_history(agent_id: str) -> dict:
        versions = rows(
            "select record_id::text, content from records where owner_id='" + p19_owner_id + "' "
            "and record_type='AgentContextRecord' and content->>'agent_id'='" + agent_id + "' order by seq"
        )
        return {
            "versions": [row["content"]["memory_version"] for row in versions],
            "states": [row["content"]["state"] for row in versions],
            "suggestion_adopted": any(any(entry["context_id"] == "lesson-1" and entry["status"] == "ADOPTED"
                for entry in row["content"]["entries"]) for row in versions),
            "final_cleared": bool(versions) and versions[-1]["content"]["state"] == "CLEARED"
                and not versions[-1]["content"]["entries"],
        }
    checks["p19_account_history"] = {
        "exact_immutable_snapshot": current_p19_accounts == p19_account_snapshot,
        "row_count": len(current_p19_accounts),
        "rows": current_p19_accounts,
    }
    account_content = [row["content"] for row in current_p19_accounts]
    positions = {row.get("position_id"): row for row in account_content if row.get("record_kind") == "POSITION"}
    flows = [row for row in account_content if row.get("record_kind") == "CAPITAL_FLOW"]
    wallet_actions = [row for row in account_content if row.get("record_kind") == "ACTION" and not row.get("position_id")]
    permission_rows = [row for row in account_content if row.get("record_kind") == "PERMISSION_SNAPSHOT"]
    checks["p19_account_content"] = {
        "all_authored_rows_match_verified_owner": all(row.get("owner_id") == p19_owner_id for row in account_content)
            and all(row.get("owner_id") == p19_owner_id for row in current_p19_accounts),
        "signed_result_literals_and_precision": positions.get("position-a-1", {}).get("realized_result", {}).get("amount")
            == {"asset_id": "monad:143/asset:USDC", "raw": "-2", "decimals": 0}
            and positions.get("position-a-1", {}).get("basis", {}).get("amount")
            == {"asset_id": "monad:143/asset:USDC", "raw": "10", "decimals": 0}
            and "proceeds 8 minus removed basis 10" in positions.get("position-a-1", {}).get("reason", "")
            and positions.get("position-a-2", {}).get("realized_result", {}).get("amount")
            == {"asset_id": "monad:143/asset:USDC", "raw": "2000000000000000001", "decimals": 18}
            and positions.get("position-a-2", {}).get("estimated_unrealized_result", {}).get("amount")
            == {"asset_id": "monad:143/asset:USDC", "raw": "0", "decimals": 8}
            and positions.get("position-b-1", {}).get("realized_result", {}).get("state") == "UNKNOWN",
        "deposit_and_withdrawal_flows": {row.get("flow_kind") for row in flows} >= {"DEPOSIT", "WITHDRAWAL"},
        "wallet_action_states_and_exact_flow_ids": {row.get("status") for row in wallet_actions}
            >= {"QUEUED", "SUBMISSION_UNKNOWN", "CONFIRMED", "REVERTED"}
            and all(row.get("flow_id") in {flow.get("flow_id") for flow in flows} for row in wallet_actions),
        "permission_history_and_bindings": {row.get("status") for row in permission_rows}
            >= {"CURRENT", "EARLIER", "CHANGE_APPLIED", "FAILED", "CANCELLED"}
            and all(row.get("approval_id") and row.get("terms_hash") and row.get("policy_binding")
                    and row.get("signer_binding") and row.get("strategy_revision") and row.get("mandate_id")
                    for row in permission_rows),
        "permission_terms_hashes_match_exact_sql_terms": all(
            row.get("terms_hash") == "sha256:" + hashlib.sha256(
                json.dumps(row.get("terms"), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            for row in permission_rows),
    }
    checks["p19_context_history"] = {agent_id: context_history(agent_id) for agent_id in ("agent-a", "agent-b")}
    verdicts = []
    for key, saved in results.items():
        if not key.startswith(("thesis-", "volume-rule-", "grouped-rule-", "grouped-right-", "tiny-threshold-")):
            continue
        request_id = saved["url"].split("/research/")[1]
        intake = rows(f"select record_id, content from records where record_type='IntakeRequest' and record_id = '{request_id}' "
                      f"and content->>'original_request' = {sql_literal(saved['original'])}")
        revision = rows(f"select * from strategy_revisions where revision_id = '{saved['revisionId']}'")
        item = {"key": key, "request_id": request_id, "intake_rows_with_exact_text": len(intake), "revision_rows": len(revision)}
        if revision:
            canonical = revision[0]["strategy_canonical"]
            strategy = json.loads(canonical)
            item["hash_recomputed_matches"] = hashlib.sha256(canonical.encode()).hexdigest() == revision[0]["content_sha256"]
            item["parent_is_null"] = revision[0]["parent_revision_id"] is None
            item["strategy_schema_version"] = strategy.get("schema_version")
            item["relative_volume_baseline"] = strategy.get("entry", {}).get("args", [{}])[0] if key.startswith("volume-rule-") else None
            if "expectedEntryTree" in saved:
                item["entry_tree_matches_ui_fixture"] = strategy.get("entry") == saved["expectedEntryTree"]
            if key.startswith("volume-rule-"):
                item["quote_volume_input_declared"] = "quote_volume" in strategy.get("data_inputs", [])
            item["owner_matches_intake"] = bool(rows(
                "select 1 from records r join strategy_revisions s on s.owner_id = r.owner_id "
                f"where s.revision_id = '{saved['revisionId']}' and r.record_id = '{request_id}'"))
            item["revision_draft_belongs_to_request"] = bool(rows(
                "select 1 from records d join strategy_revisions s on s.draft_record_id = d.record_id "
                f"where s.revision_id = '{saved['revisionId']}' and d.intake_record_id = '{request_id}'"))
            item["restrictions_saved"] = intake[0]["content"]["restrictions"] if intake else None
        verdicts.append(item)
    checks["thesis_verdicts"] = verdicts
    passed = bool(verdicts) and all(v["intake_rows_with_exact_text"] == 1 and v["revision_rows"] == 1 and v.get("revision_draft_belongs_to_request")
                                    and v.get("hash_recomputed_matches") and v.get("parent_is_null")
                                    and v.get("owner_matches_intake") and v.get("strategy_schema_version") == "p06.strategy/1"
                                    and (not v["key"].startswith("volume-rule-") or
                                         v.get("quote_volume_input_declared") and
                                         v.get("relative_volume_baseline") == {"op": "relative_volume", "lookback_buckets": 2})
                                    and ("entry_tree_matches_ui_fixture" not in v or v["entry_tree_matches_ui_fixture"])
                                    for v in verdicts)
    spot_replays = []
    for key, saved in results.items():
        if not key.startswith("spot-replay-"):
            continue
        replay_id = saved["replayId"]
        replay_rows = rows(
            "select r.replay_id::text, r.owner_id::text, r.strategy_id, r.strategy_revision_id::text, "
            "r.method, r.path, r.idempotency_key, r.fingerprint, r.content_sha256, r.content, "
            "(r.content->'inputs'->'essential_evidence'->'fields') fields, "
            "(r.content->'result'->'metrics') metrics, r.content->'result'->>'status' result_status, "
            "r.content->'result'->>'evidence_class' evidence_class "
            "from spot_replay_runs r join strategy_revisions s "
            "on s.owner_id=r.owner_id and s.strategy_id=r.strategy_id and s.revision_id=r.strategy_revision_id "
            f"where r.replay_id='{replay_id}' and r.strategy_revision_id='{saved['revisionId']}'")
        item = {"key": key, "replay_id": replay_id, "rows": len(replay_rows)}
        if replay_rows:
            row = replay_rows[0]
            content = row["content"]
            item.update({
                "owner_matches_saved_revision": bool(row["owner_id"]),
                "method_and_path_match": row["method"] == "POST" and row["path"] == "/v1/spot-replays",
                "idempotency_key_present": bool(row["idempotency_key"]),
                "idempotency_key_matches_browser": not saved.get("expectedIdempotencyKey")
                    or row["idempotency_key"] == saved["expectedIdempotencyKey"],
                "request_fingerprint_is_sha256": bool(re.fullmatch(r"[0-9a-f]{64}", row["fingerprint"])),
                "stored_hash_matches_browser": row["content_sha256"] == saved["replayHash"],
                "stored_hash_recomputed": hashlib.sha256(json.dumps(
                    content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")).hexdigest() == row["content_sha256"],
                "entry_dependencies_match_browser": row["fields"]["entry"].get("essential_dependencies") == saved["expectedEntryDependencies"],
                "exit_dependencies_match_browser": row["fields"]["exit"].get("essential_dependencies") == saved["expectedExitDependencies"],
                "expected_result_status": row["result_status"] == saved.get("expectedStatus", "COMPLETE"),
                "expected_unavailable_reason": saved.get("expectedStatus", "COMPLETE") != "UNAVAILABLE"
                    or content["result"].get("reason", {}).get("code") == saved.get("expectedReason"),
                "synthetic_evidence_class": row["evidence_class"] == "SYNTHETIC_FIXTURE",
                "complete_synthetic_result": row["result_status"] == "COMPLETE" and row["evidence_class"] == "SYNTHETIC_FIXTURE",
                "expected_accounting": saved.get("expectedStatus", "COMPLETE") != "COMPLETE" or
                    (row["metrics"].get("gain_loss_quote") == saved["expectedGainLossQuote"]
                    and content["result"]["samples"][-1]["cash_quote"] == saved["expectedEndingCashQuote"]
                    and row["metrics"].get("completed_trade_pairs") == 1),
                "no_trade_permission_notice": "No trading permission is granted." in content["notice"],
            })
        spot_replays.append(item)
    checks["spot_replays"] = spot_replays
    spot_replays_pass = bool(spot_replays) and all(
        item.get("rows") == 1 and item.get("owner_matches_saved_revision") and item.get("method_and_path_match")
        and item.get("idempotency_key_present") and item.get("idempotency_key_matches_browser")
        and item.get("request_fingerprint_is_sha256")
        and item.get("stored_hash_matches_browser") and item.get("stored_hash_recomputed")
        and item.get("entry_dependencies_match_browser") and item.get("exit_dependencies_match_browser")
        and item.get("expected_result_status") and item.get("expected_unavailable_reason")
        and item.get("synthetic_evidence_class") and item.get("expected_accounting")
        and item.get("no_trade_permission_notice") for item in spot_replays)
    investigations = []
    for key, saved in results.items():
        if not key.startswith("investigation-"):
            continue
        intake_id = saved["url"].split("/research/")[-1].split("?")[0].split("#")[0]
        declaration_id = saved["declarationId"]
        rows_for_declaration = rows(
            "select d.declaration_id, d.owner_id, d.intake_record_id, d.content, e.content access_content "
            "from investigation_declarations d join investigation_access_events e "
            "on e.owner_id=d.owner_id and e.declaration_id=d.declaration_id "
            f"where d.declaration_id='{declaration_id}' and d.intake_record_id='{intake_id}'")
        item = {"key": key, "intake_id": intake_id, "declaration_id": declaration_id,
                "rows": len(rows_for_declaration)}
        if rows_for_declaration:
            content = rows_for_declaration[0]["content"]
            access = rows_for_declaration[0]["access_content"]
            configuration = content.get("configuration", {})
            partitions = configuration.get("partitions", [])
            partition_by_id = {part.get("partition_id"): part for part in partitions}
            plan = configuration.get("evaluation_plan", [])
            start = datetime.fromisoformat(configuration.get("period", {}).get("start", "").replace("Z", "+00:00"))
            end = datetime.fromisoformat(configuration.get("period", {}).get("end", "").replace("Z", "+00:00"))
            intervals = [(datetime.fromisoformat(part["start"].replace("Z", "+00:00")),
                          datetime.fromisoformat(part["end"].replace("Z", "+00:00"))) for part in partitions]
            plan_bound = (len({row.get("evaluation_id") for row in plan}) == len(plan)
                and {row.get("evaluation_id") for row in plan} == set(content.get("evaluation_ids", []))
                and {row.get("trial_id") for row in plan} == set(content.get("trial_ids", []))
                and configuration.get("compute_limit", {}).get("max_evaluations", 0) >= len(plan)
                and all(row.get("variant_id") in {item.get("variant_id") for item in configuration.get("variants", [])}
                    and row.get("partition_ids") and set(row["partition_ids"]).issubset(partition_by_id)
                    and (row.get("horizon", {}).get("value"), row.get("horizon", {}).get("unit"))
                        in {(item.get("value"), item.get("unit")) for item in configuration.get("horizons", [])}
                    for row in plan))
            semantics_bound = ((content.get("edge_spec", {}).get("claim", {}).get("status") == "DESCRIPTIVE_ONLY"
                and content.get("edge_spec", {}).get("falsification", {}).get("status") == "DESCRIPTIVE_ONLY"
                and configuration.get("direction") == "DESCRIPTIVE") or
                (content.get("edge_spec", {}).get("claim", {}).get("status") == "HYPOTHESIS"
                and content.get("edge_spec", {}).get("falsification", {}).get("status") == "DECLARED"
                and configuration.get("direction") in {"OUTPERFORM", "UNDERPERFORM"}))
            temporal_bound = (bool(intervals) and all(start <= left < right <= end for left, right in intervals)
                and all(previous[1] <= current[0] for previous, current in zip(intervals, intervals[1:]))
                and (configuration.get("direction") != "DESCRIPTIVE" or
                     len(intervals) == 1 and intervals[0] == (start, end) and partitions[0].get("role") == "DESCRIPTIVE")
                and (configuration.get("direction") == "DESCRIPTIVE" or
                     {part.get("role") for part in partitions}.issuperset({"TRAINING", "VALIDATION", "HOLDOUT"})))
            item.update({
                "original_request_matches_ui": content.get("original_request") == saved["original"],
                "saved_content_matches_ui_and_api": content == saved.get("content"),
                "access_event_matches_ui_and_api": access == saved.get("access"),
                "state_is_pre_outcome": content.get("declaration_state") == "PRE_OUTCOME_DECLARED",
                "labels_unread": content.get("outcome_labels_read") is False and access.get("outcome_labels_read") is False,
                "no_provider_or_study": access.get("provider_queries") == 0 and access.get("study_started") is False,
                "fixture_only_zero_cost": content.get("configuration", {}).get("permitted_access") == ["FIXTURE_ONLY"]
                    and content.get("configuration", {}).get("compute_limit", {}).get("max_cost_usd") == "0",
                "version_two_contract": rows_for_declaration[0]["content"].get("schema_version") == "p08.investigation-declaration/2",
                "declaration_semantics_consistent": semantics_bound,
                "evaluation_plan_explicit_and_budgeted": plan_bound,
                "partition_boundaries_contained_and_ordered": temporal_bound,
                "owner_matches_intake": bool(rows(f"select 1 from records r join investigation_declarations d "
                    f"on d.owner_id=r.owner_id where r.record_id='{intake_id}' and d.declaration_id='{declaration_id}'")),
                "access_event_count": rows(f"select count(*) c from investigation_access_events where declaration_id='{declaration_id}'")[0]["c"],
            })
        investigations.append(item)
    checks["investigations"] = investigations
    investigations_pass = bool(investigations) and all(v.get("rows") == 1 and v.get("original_request_matches_ui")
        and v.get("saved_content_matches_ui_and_api") and v.get("access_event_matches_ui_and_api")
        and v.get("state_is_pre_outcome") and v.get("labels_unread") and v.get("no_provider_or_study")
        and v.get("fixture_only_zero_cost") and v.get("owner_matches_intake") and v.get("access_event_count") == 1
        and v.get("version_two_contract") and v.get("declaration_semantics_consistent")
        and v.get("evaluation_plan_explicit_and_budgeted") and v.get("partition_boundaries_contained_and_ordered")
        for v in investigations)
    effect_runs = []
    for key, saved in results.items():
        if not key.startswith("investigation-") or not saved.get("runId"):
            continue
        run_id, report_id = saved["runId"], saved["reportId"]
        found = rows(
            "select r.owner_id, r.intake_record_id, r.p08_declaration_id, r.content run_content, "
            "p.owner_id report_owner_id, p.content report_content "
            "from effect_run_declarations r join effect_reports p on p.owner_id=r.owner_id and p.run_id=r.run_id "
            f"where r.run_id='{run_id}' and p.report_id='{report_id}'")
        events = rows(f"select event_id, attempt_idempotency_key, content from effect_run_events where run_id='{run_id}' order by sequence")
        event_content = [event["content"] for event in events]
        item = {"key": key, "run_id": run_id, "report_id": report_id, "rows": len(found),
                "events": event_content}
        if found:
            run_content, report_content = found[0]["run_content"], found[0]["report_content"]
            p08 = rows(f"select content from investigation_declarations where declaration_id='{found[0]['p08_declaration_id']}'")
            item.update({
                "owner_matches_intake": bool(rows(
                    f"select 1 from records where owner_id='{found[0]['owner_id']}' and record_id='{found[0]['intake_record_id']}'")),
                "run_links_exact_p08_declaration": found[0]["p08_declaration_id"] == saved["declarationId"],
                "run_plan_matches_p08": bool(p08) and run_content.get("p08_evaluation_plan") == p08[0]["content"].get("configuration", {}).get("evaluation_plan"),
                "adoption_precedes_reads": bool(events) and events[0]["content"].get("kind") == "RUN_ADOPTED"
                    and events[0]["content"].get("outcome_accessed") is False,
                "attempt_and_report_order": [event["content"].get("kind") for event in events]
                    == ["RUN_ADOPTED", "RUN_ADOPTION_REPLAY", "ATTEMPT_STARTED", "OUTCOME_ACCESS_STARTED",
                        "REPORT_SAVED", "ATTEMPT_REPLAY"],
                "durable_access_marker_matches_report": len(events) == 6
                    and event_content[3].get("outcome_accessed") is True
                    and event_content[3].get("p09_configuration_sha256") == run_content.get("configuration_sha256")
                    and event_content[4].get("access_marker_event_id") == str(events[3]["event_id"]),
                "exact_saved_report_matches_ui": report_content == saved["p09"]["report"]["content"],
                "configuration_and_fixture_hashes_match_ui": run_content.get("configuration_sha256") == saved["p09ConfigurationSha256"]
                    and report_content.get("fixture_sha256") == saved["fixtureSha256"]
                    and report_content.get("profile_sha256") == saved["profileSha256"],
                "report_remains_unresolved": report_content.get("result", {}).get("status") == "UNRESOLVED"
                    and report_content.get("result", {}).get("statistical_status") == "UNRESOLVED",
                "mapping_identity_proof_matches_ui": saved.get("p09", {}).get("identityProof", {}).get("exactRepeatStatus") == 200
                    and saved.get("p09", {}).get("identityProof", {}).get("exactRepeatRunId") == run_id
                    and saved.get("p09", {}).get("identityProof", {}).get("adoptionReplayRepeatStatus") == 200
                    and saved.get("p09", {}).get("identityProof", {}).get("adoptionChangedOperationStatus") == 409
                    and saved.get("p09", {}).get("identityProof", {}).get("adoptionReceiptCount") == 1
                    and saved.get("p09", {}).get("identityProof", {}).get("adoptionReceiptOperationId")
                        == event_content[1].get("operation_id")
                    and saved.get("p09", {}).get("identityProof", {}).get("adoptionReceiptKey")
                        == event_content[1].get("idempotency_key")
                    and event_content[1].get("kind") == "RUN_ADOPTION_REPLAY"
                    and event_content[1].get("outcome_accessed") is False
                    and saved.get("p09", {}).get("identityProof", {}).get("changedOperationStatus") == 409
                    and saved.get("p09", {}).get("identityProof", {}).get("changedOperationLeftEventsUnchanged") is True
                    and saved.get("p09", {}).get("identityProof", {}).get("reportReplayStatus") == 200
                    and saved.get("p09", {}).get("identityProof", {}).get("reportReplayRepeatStatus") == 200
                    and saved.get("p09", {}).get("identityProof", {}).get("reportReplayChangedOperationStatus") == 409
                    and saved.get("p09", {}).get("identityProof", {}).get("reportReplayChangedOperationLeftEventsUnchanged") is True
                    and saved.get("p09", {}).get("identityProof", {}).get("reportReplayReportId") == report_id
                    and saved.get("p09", {}).get("identityProof", {}).get("reportReplayEventCount") == len(events)
                    and saved.get("p09", {}).get("identityProof", {}).get("reportReplayReceiptOperationId")
                        == event_content[5].get("operation_id")
                    and saved.get("p09", {}).get("identityProof", {}).get("reportReplayReceiptKey")
                        == event_content[5].get("idempotency_key")
                    and events[5].get("attempt_idempotency_key") == event_content[5].get("idempotency_key")
                    and event_content[5].get("kind") == "ATTEMPT_REPLAY"
                    and saved.get("p09", {}).get("identityProof", {}).get("alternateMappingStatus") == 409
                    and saved.get("p09", {}).get("identityProof", {}).get("runCountAfterRejectedMapping") == 1,
                "p08_mapping_identity_is_unique": rows(
                    "select count(*) c from (select binding->>'evaluation_id' evaluation_id "
                    "from effect_run_declarations r cross join lateral "
                    "jsonb_array_elements(r.content->'configuration'->'bindings') binding "
                    f"where r.p08_declaration_id='{found[0]['p08_declaration_id']}' "
                    "group by binding->>'evaluation_id' having count(distinct md5(binding::text)) <> 1) conflicts"
                )[0]["c"] == 0 and rows(
                    "select count(*) c from effect_run_declarations "
                    f"where p08_declaration_id='{found[0]['p08_declaration_id']}'"
                )[0]["c"] == 1,
                "synthetic_comparison_and_unavailable_buckets_match": bool(report_content.get("result", {}).get("variants"))
                    and all(variant.get("general_comparison", {}).get("triggered", {}).get("mean") == "0.1"
                            and variant.get("general_comparison", {}).get("control", {}).get("mean") == "-0.1"
                            and variant.get("general_comparison", {}).get("triggered_minus_control_mean") == "0.2"
                            and variant.get("incremental_volume_comparison", {}).get("triggered_minus_control_mean") == "0.2"
                            for variant in report_content["result"]["variants"])
                    and report_content.get("result", {}).get("excluded_count") == 4
                    and report_content.get("result", {}).get("missing_outcome_count") == 4,
                "exact_run_and_report_counts": rows(f"select count(*) c from effect_run_declarations where run_id='{run_id}'")[0]["c"] == 1
                    and rows(f"select count(*) c from effect_reports where run_id='{run_id}'")[0]["c"] == 1
                    and len(events) == 6,
            })
        effect_runs.append(item)
    checks["effect_comparisons"] = effect_runs
    effect_runs_pass = bool(effect_runs) and all(v.get("rows") == 1 and v.get("owner_matches_intake")
        and v.get("run_links_exact_p08_declaration") and v.get("run_plan_matches_p08")
        and v.get("adoption_precedes_reads") and v.get("attempt_and_report_order")
        and v.get("durable_access_marker_matches_report")
        and v.get("exact_saved_report_matches_ui") and v.get("configuration_and_fixture_hashes_match_ui")
        and v.get("report_remains_unresolved") and v.get("mapping_identity_proof_matches_ui")
        and v.get("p08_mapping_identity_is_unique")
        and v.get("synthetic_comparison_and_unavailable_buckets_match")
        and v.get("exact_run_and_report_counts") for v in effect_runs)
    p19_ok = checks["p19_account_history"]["exact_immutable_snapshot"] and checks["p19_account_history"]["row_count"] == len(p19_account_snapshot) \
        and all(checks["p19_account_content"].values()) \
        and all(checks["p19_context_history"][agent_id]["versions"] == [1, 2, 3, 4, 5]
                and checks["p19_context_history"][agent_id]["suggestion_adopted"]
                and checks["p19_context_history"][agent_id]["final_cleared"] for agent_id in ("agent-a", "agent-b"))
    return {"checks": checks, "all_checks_pass": passed and investigations_pass and effect_runs_pass and spot_replays_pass and p19_ok}


def sql_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def ownership_drive(pg: harness.Postgres, api_url: str, token_a: str, token_b: str) -> dict:
    def rows(sql: str):
        return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))

    row = json.loads(pg.psql("select coalesce(json_agg(t), '[]'::json) from (select r.record_id, d.record_id draft_id, "
                             "d.content->>'strategy_id' strategy_id from records r join records d on d.intake_record_id = r.record_id "
                             "where r.record_type='IntakeRequest' and d.record_type='StrategyDraft' limit 1) t"))
    if not row:
        return {"all_denied": False, "error": "no saved draft found to attack"}
    row = row[0] if isinstance(row, list) else row
    sid, intake, draft = row["strategy_id"], row["record_id"], row["draft_id"]
    results = {}
    results["read_other_request"] = http("GET", f"{api_url}/v1/research/requests/{intake}", token_b)[0]
    results["answer_other_request"] = http("POST", f"{api_url}/v1/research/requests/{intake}/clarifications", token_b,
                                           {"previous_revision_id": "x", "question_id": "choose-entry", "choice_id": "g3-1pct"})[0]
    results["random_id_read"] = http("GET", f"{api_url}/v1/research/requests/22222222-2222-4222-8222-222222222222", token_b)[0]
    results["owner_a_still_reads"] = http("GET", f"{api_url}/v1/research/requests/{intake}", token_a)[0]
    denied = [results[k] for k in ("read_other_request", "answer_other_request", "random_id_read")]
    # the publish attempt carries an empty strategy, so it is rejected before ownership; repeat with the real body
    real = json.loads(pg.psql(f"select content->'source_syntax' from records where record_id = '{draft}'"))
    results["publish_other_draft_real_body"] = http("POST", f"{api_url}/v1/strategies/{sid}/revisions", token_b, {
        "operation_id": "33333333-3333-4333-8333-333333333333", "idempotency_key": "attack-2",
        "expected_parent_revision_id": None, "draft_id": draft, "strategy": real})[0]
    rows_unchanged = pg.psql(f"select count(*) from strategy_revisions where strategy_id = '{sid}'")
    results["revisions_for_strategy_after_attacks"] = rows_unchanged
    investigation = json.loads(pg.psql("select coalesce(json_agg(t), '[]'::json) from (select intake_record_id, declaration_id from investigation_declarations order by created_at limit 1) t"))
    investigation_ok = not investigation
    effect_ok = True
    if investigation:
        investigation = investigation[0]
        iid, did = investigation["intake_record_id"], investigation["declaration_id"]
        results["read_other_investigation"] = http("GET", f"{api_url}/v1/research/requests/{iid}/investigations/{did}", token_b)[0]
        results["list_other_investigations"] = http("GET", f"{api_url}/v1/research/requests/{iid}/investigations", token_b)[0]
        stored = rows(f"select content from investigation_declarations where declaration_id='{did}'")[0]["content"]
        attack = {"operation_id": "66666666-6666-4666-8666-666666666666", "idempotency_key": "foreign-investigation-attack",
                  "expected_interpretation_revision_id": stored["interpretation_revision_id"],
                  "edge_spec": stored["edge_spec"], "configuration": stored["configuration"],
                  "adopted_fields": stored["adopted_fields"], "field_origins": stored["field_origins"],
                  "trial_ids": stored["trial_ids"], "evaluation_ids": stored["evaluation_ids"]}
        results["adopt_other_investigation"] = http("POST", f"{api_url}/v1/research/requests/{iid}/investigations", token_b, attack)[0]
        results["owner_a_reads_investigation"] = http("GET", f"{api_url}/v1/research/requests/{iid}/investigations/{did}", token_a)[0]
        before = pg.psql(f"select count(*) from investigation_declarations where declaration_id='{did}'")
        access_before = pg.psql(f"select count(*) from investigation_access_events where declaration_id='{did}'")
        results["investigation_count_before_after"] = [before, pg.psql(
            f"select count(*) from investigation_declarations where declaration_id='{did}'")]
        results["investigation_access_count_before_after"] = [access_before, pg.psql(
            f"select count(*) from investigation_access_events where declaration_id='{did}'")]
        investigation_ok = results["read_other_investigation"] == 404 and results["list_other_investigations"] == 404 \
            and results["adopt_other_investigation"] == 404 \
            and results["owner_a_reads_investigation"] == 200 and before == results["investigation_count_before_after"][1] \
            and access_before == results["investigation_access_count_before_after"][1]
    effect_rows = rows("select intake_record_id, run_id from effect_run_declarations order by created_at limit 1")
    if effect_rows:
        iid, run_id = effect_rows[0]["intake_record_id"], effect_rows[0]["run_id"]
        results["read_other_effect_run"] = http("GET", f"{api_url}/v1/research/requests/{iid}/effect-runs/{run_id}", token_b)[0]
        results["list_other_effect_runs"] = http("GET", f"{api_url}/v1/research/requests/{iid}/effect-runs", token_b)[0]
        results["owner_a_reads_effect_run"] = http("GET", f"{api_url}/v1/research/requests/{iid}/effect-runs/{run_id}", token_a)[0]
        before_events = pg.psql(f"select count(*) from effect_run_events where run_id='{run_id}'")
        before_reports = pg.psql(f"select count(*) from effect_reports where run_id='{run_id}'")
        results["attempt_other_effect_run"] = http("POST", f"{api_url}/v1/research/requests/{iid}/effect-runs/{run_id}/attempts", token_b, {
            "operation_id": "77777777-7777-4777-8777-777777777777", "idempotency_key": "foreign-effect-run-attack"})[0]
        after_events = pg.psql(f"select count(*) from effect_run_events where run_id='{run_id}'")
        after_reports = pg.psql(f"select count(*) from effect_reports where run_id='{run_id}'")
        results["effect_history_count_before_after"] = {"events": [before_events, after_events],
                                                        "reports": [before_reports, after_reports]}
        effect_ok = (results["read_other_effect_run"] == 404 and results["list_other_effect_runs"] == 404
            and results["attempt_other_effect_run"] == 404 and results["owner_a_reads_effect_run"] == 200
            and before_events == after_events and before_reports == after_reports)
    return {**results, "all_denied": all(c == 404 for c in denied) and results["publish_other_draft_real_body"] == 404
            and results["owner_a_still_reads"] == 200 and rows_unchanged == "1" and investigation_ok and effect_ok}


if __name__ == "__main__":
    sys.exit(main())
