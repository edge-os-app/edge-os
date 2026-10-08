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
from tokens import OWNER_A, OWNER_B, TestSigner  # noqa: E402

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


def docker_resources() -> dict[str, list[str]]:
    containers = harness.sh(["docker", "ps", "-a", "--format", "{{.Names}}"], check=False).stdout.split()
    volumes = harness.sh(["docker", "volume", "ls", "--format", "{{.Name}}"], check=False).stdout.split()
    return {"containers": sorted(containers), "volumes": sorted(volumes)}


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


def run_playwright(specs: list[str], env_extra: dict[str, str], log: Path) -> int:
    env = harness.base_env()
    env.update(env_extra)
    result = subprocess.run(["npx", "playwright", "test", "--config", "playwright.config.mjs", *specs],
                            cwd=harness.REPO / "tests" / "p03", env=env, capture_output=True, text=True, timeout=900)
    log.write_text(result.stdout + result.stderr)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=harness.new_run_id())
    parser.add_argument("--evidence-root", default=str(harness.REPO / ".scratch" / "p03" / "evidence"))
    parser.add_argument("--skip-ui", action="store_true", help="skip the browser steps (not a full pass)")
    parser.add_argument("--hold-seconds", type=int, default=0,
                        help="keep the instance up this long after the drive so an inspector can run SQL, then clean up")
    args = parser.parse_args()
    run_id = args.run_id
    evidence = Path(args.evidence_root) / run_id
    pg = harness.Postgres(run_id)
    dist = f".next-{run_id}"
    dist_path = harness.WEB_DIR / dist
    tsconfig_copy = harness.WEB_DIR / harness.web_tsconfig(dist)
    # A repeated run ID must never touch what an earlier run owns: refuse before creating or deleting anything.
    present = pg.existing_resources()
    present += [f"path {p}" for p in (dist_path, tsconfig_copy) if p.exists()]
    present += [f"evidence {evidence}"] if evidence.exists() and any(evidence.iterdir()) else []
    if present:
        print(f"REFUSED run {run_id}: {', '.join(present)} already exists. Nothing was created or changed. Use a new run ID.")
        return 2
    rec = Recorder(evidence)
    processes: list[harness.Process] = []
    before = docker_resources()
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
            return 1
        bundle = scan_bundle(dist_path)
        rec.write("bundle-scan.json", bundle)
        ok &= rec.step("production bundle has no fixture provider or key", not bundle["fixture_label_in_bundle"]
                       and not bundle["private_key_blocks_in_bundle"] and bundle["privy_create_on_login_off_literals"] >= 2, bundle)
        web = harness.start_web(api_url=api_url, dist=dist, port=web_port, log_dir=evidence / "logs")
        processes.append(web)
        harness.wait_http(web_url + "/")
        ok &= rec.step("web health", True, {"url": web_url})

        token_a, token_b = signer.token(OWNER_A), signer.token(OWNER_B)
        token_bad = TestSigner().token(OWNER_A)

        status_none, _ = http("GET", f"{api_url}/v1/me")
        status_bad, _ = http("GET", f"{api_url}/v1/me", token_bad)
        ok &= rec.step("API rejects missing and wrong-key credentials", (status_none, status_bad) == (401, 401), [status_none, status_bad])

        if not args.skip_ui:
            ui_env = {"P03_WEB_URL": web_url, "P03_TOKEN_A": token_a, "P03_TOKEN_B": token_b, "P03_TOKEN_BAD": token_bad,
                      "P03_EVIDENCE_DIR": str(evidence / "ui")}
            code = run_playwright(["e2e.spec.mjs", "quality.spec.mjs"], ui_env, evidence / "ui-e2e.log")
            ok &= rec.step("browser drive (desktop and 390px)", code == 0, {"exit": code})

            results_path = evidence / "ui" / "ui-results.json"
            results = json.loads(results_path.read_text()) if results_path.exists() else {}
            inspection = sql_inspection(pg, results)
            rec.write("sql-inspection.json", inspection)
            ok &= rec.step("saved records match what the UI submitted (direct SQL)", inspection["all_checks_pass"], inspection["checks"])

            # cross-owner denial against the real saved rows
            denial = ownership_drive(pg, api_url, token_a, token_b)
            rec.write("ownership-drive.json", denial)
            ok &= rec.step("another owner is denied read, mutation and parent reference", denial["all_denied"], denial)

            api.stop()
            api = harness.start_api(env, api_port, evidence / "logs", name="api-restarted")
            processes.append(api)
            harness.wait_http(f"{api_url}/readyz")
            ok &= rec.step("API restarted on the same database", True)
            code = run_playwright(["reopen.spec.mjs"], ui_env, evidence / "ui-reopen.log")
            ok &= rec.step("saved revision reopens unchanged after restart (new browser context)", code == 0, {"exit": code})
            after_restart = sql_inspection(pg, results)
            ok &= rec.step("records unchanged by the restart", after_restart["checks"] == inspection["checks"])

        if args.hold_seconds:
            hold = {"web": web_url, "api": api_url, "token_owner_a": token_a,
                    "psql": f"docker exec {pg.container} psql -U postgres -d {pg.database}", "seconds": args.hold_seconds}
            print("HOLD " + json.dumps({k: v for k, v in hold.items() if not k.startswith("token")}), flush=True)
            rec.write("hold.json", {k: v for k, v in hold.items() if not k.startswith("token")})
            time.sleep(args.hold_seconds)

        logs = [p for p in (evidence / "logs").glob("*.log")]
        secrets_seen = [str(p.name) for p in logs if any(t in p.read_text(errors="ignore") for t in (token_a, token_b, token_bad, signer.private_pem))]
        ok &= rec.step("logs contain no token or private key", not secrets_seen, secrets_seen)
    except Exception as error:  # noqa: BLE001
        rec.step("run aborted", False, f"{type(error).__name__}: {error}")
        ok = False
    finally:
        for process in reversed(processes):
            process.stop()
        pg.stop_and_remove()
        shutil.rmtree(dist_path, ignore_errors=True)
        tsconfig_copy.unlink(missing_ok=True)
        after = docker_resources()
        rec.write("resources-after.json", after)
        clean = pg.leftovers() == [] and after == before and not dist_path.exists() and not tsconfig_copy.exists()
        rec.step("cleanup removed only this run's resources", clean, {"leftovers": pg.leftovers(), "unchanged": after == before})
        ok &= clean
        manifest = {str(p.relative_to(evidence)): sha256_file(p) for p in sorted(evidence.rglob("*")) if p.is_file()}
        rec.write("MANIFEST.json", {"run_id": run_id, "files": manifest})
    print(json.dumps({"run_id": run_id, "evidence": str(evidence), "ok": bool(ok)}))
    return 0 if ok else 1


def sql_inspection(pg: harness.Postgres, results: dict) -> dict:
    checks: dict[str, object] = {}
    def rows(sql: str):
        return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))
    checks["users"] = rows("select count(*) c from users")[0]["c"]
    checks["records_by_type"] = {r["record_type"]: r["c"] for r in rows(
        "select record_type, count(*) c from records group by record_type order by 1")}
    checks["revisions"] = rows("select count(*) c from strategy_revisions")[0]["c"]
    verdicts = []
    for key, saved in results.items():
        if not key.startswith("thesis-"):
            continue
        request_id = saved["url"].split("/research/")[1]
        intake = rows(f"select record_id, content from records where record_type='IntakeRequest' and record_id = '{request_id}' "
                      f"and content->>'original_request' = {sql_literal(saved['original'])}")
        revision = rows(f"select * from strategy_revisions where revision_id = '{saved['revisionId']}'")
        item = {"key": key, "request_id": request_id, "intake_rows_with_exact_text": len(intake), "revision_rows": len(revision)}
        if revision:
            canonical = revision[0]["strategy_canonical"]
            item["hash_recomputed_matches"] = hashlib.sha256(canonical.encode()).hexdigest() == revision[0]["content_sha256"]
            item["parent_is_null"] = revision[0]["parent_revision_id"] is None
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
                                    and v.get("owner_matches_intake") for v in verdicts)
    return {"checks": checks, "all_checks_pass": passed}


def sql_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def ownership_drive(pg: harness.Postgres, api_url: str, token_a: str, token_b: str) -> dict:
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
    return {**results, "all_denied": all(c == 404 for c in denied) and results["publish_other_draft_real_body"] == 404
            and results["owner_a_still_reads"] == 200 and rows_unchanged == "1"}


if __name__ == "__main__":
    sys.exit(main())
