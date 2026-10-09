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

        status_none, _ = http("GET", f"{api_url}/v1/me")
        status_bad, _ = http("GET", f"{api_url}/v1/me", token_bad)
        ok &= rec.step("API rejects missing and wrong-key credentials", (status_none, status_bad) == (401, 401), [status_none, status_bad])

        if not args.skip_ui:
            ui_env = {"P03_WEB_URL": web_url, "P03_API_URL": api_url, "P03_TOKEN_A": token_a, "P03_TOKEN_B": token_b, "P03_TOKEN_C": token_c, "P03_TOKEN_BAD": token_bad,
                      "P03_EVIDENCE_DIR": str(evidence / "ui")}
            code = run_playwright(["e2e.spec.mjs", "quality.spec.mjs", "provenance.spec.mjs"], ui_env, evidence / "ui-e2e.log")
            ok &= rec.step("browser drive (desktop and 390px)", code == 0, {"exit": code})

            results_path = evidence / "ui" / "ui-results.json"
            results = json.loads(results_path.read_text()) if results_path.exists() else {}
            inspection = sql_inspection(pg, results)
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
            after_restart = sql_inspection(pg, results)
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
        events = rows(f"select content from effect_run_events where run_id='{run_id}' order by sequence")
        item = {"key": key, "run_id": run_id, "report_id": report_id, "rows": len(found),
                "events": [event["content"] for event in events]}
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
                    == ["RUN_ADOPTED", "ATTEMPT_STARTED", "REPORT_SAVED"],
                "exact_saved_report_matches_ui": report_content == saved["p09"]["report"]["content"],
                "configuration_and_fixture_hashes_match_ui": run_content.get("configuration_sha256") == saved["p09ConfigurationSha256"]
                    and report_content.get("fixture_sha256") == saved["fixtureSha256"]
                    and report_content.get("profile_sha256") == saved["profileSha256"],
                "report_remains_unresolved": report_content.get("result", {}).get("status") == "UNRESOLVED"
                    and report_content.get("result", {}).get("statistical_status") == "UNRESOLVED",
                "exact_run_and_report_counts": rows(f"select count(*) c from effect_run_declarations where run_id='{run_id}'")[0]["c"] == 1
                    and rows(f"select count(*) c from effect_reports where run_id='{run_id}'")[0]["c"] == 1
                    and len(events) == 3,
            })
        effect_runs.append(item)
    checks["effect_comparisons"] = effect_runs
    effect_runs_pass = bool(effect_runs) and all(v.get("rows") == 1 and v.get("owner_matches_intake")
        and v.get("run_links_exact_p08_declaration") and v.get("run_plan_matches_p08")
        and v.get("adoption_precedes_reads") and v.get("attempt_and_report_order")
        and v.get("exact_saved_report_matches_ui") and v.get("configuration_and_fixture_hashes_match_ui")
        and v.get("report_remains_unresolved") and v.get("exact_run_and_report_counts") for v in effect_runs)
    return {"checks": checks, "all_checks_pass": passed and investigations_pass and effect_runs_pass}


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
