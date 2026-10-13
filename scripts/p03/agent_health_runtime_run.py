"""P31 LOCAL agent health: one isolated mounted browser/API/SQL/restart run (lane 3 recipe).

Run with the API environment's Python from the repository root:

    apps/api/.venv/bin/python scripts/p03/agent_health_runtime_run.py --evidence <new empty directory>

It owns every resource it starts: a run-labelled PostgreSQL container, one API process (restarted once on the same
port), one production web build in a run-scoped directory and one web server. Two owners (desktop and 390px) each
get one confirmed, funded agent with adopted terms and a recurring deployment, seeded through the public API. With
no browser open, separate `recurring_producer --once` processes run slots 0 and 5 (the desktop owner stops new
entries between them; the 390px agent's acknowledgements are lost, so an original stays unknown). The browser then
checks that the direct health panel and the read-only conversation quote the API's dated snapshot, that a third
owner is refused, and that after an API restart a new browser context reads the same snapshot identity. Direct SQL
compares the snapshot with the saved rows and proves the browser stages wrote no financial row and caused no fixture
effect. Authored fixture ports only: nothing is a wallet, quote, transaction or chain evidence.

It is not part of the shared mapped verifier; the controller may mount it serially (see the lane-3 map proposal).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
import recurring_phase  # noqa: E402
from tokens import TestSigner  # noqa: E402

sys.path.insert(0, str(harness.API_DIR / "tests"))
import httpx  # noqa: E402
import financial_flows as ff  # noqa: E402

PROJECTS = {"desktop": "health-desktop", "mobile-390": "health-mobile-390-fx-lost-ack"}
FINANCIAL_SCHEMAS = ("execution_local", "admission_local", "stops_local", "revocation_local", "recovery_local",
                     "funding_local")


class Recorder:
    def __init__(self, evidence: Path) -> None:
        self.evidence, self.steps = evidence, []

    def step(self, name: str, ok: bool, detail: Any = None) -> bool:
        self.steps.append({"step": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        return bool(ok)

    def write(self, name: str, value: Any) -> None:
        (self.evidence / name).write_text(value if isinstance(value, str) else json.dumps(value, indent=2, default=str))


def rows(pg: harness.Postgres, sql: str) -> list[dict[str, Any]]:
    return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))


def fingerprint(pg: harness.Postgres) -> dict[str, str]:
    """md5 of every row of every financial table: any write between two calls changes it."""
    tables = rows(pg, "select table_schema sch, table_name tab from information_schema.tables where table_type = "
                      f"'BASE TABLE' and table_schema in ({','.join(repr(s) for s in FINANCIAL_SCHEMAS)}) order by 1, 2")
    result = {}
    for table in tables:
        name = f'"{table["sch"]}"."{table["tab"]}"'
        result[name] = rows(pg, f"select md5(coalesce(string_agg(x::text, '|' order by x::text), '')) h "
                                f"from {name} x")[0]["h"]
    return result


def lines(path: Path) -> int:
    return len([line for line in path.read_text().splitlines() if line]) if path.exists() else 0


def run_playwright(args: list[str], env_extra: dict[str, str], log: Path) -> int:
    env = harness.base_env()
    env.update(env_extra)
    result = subprocess.run(["npx", "playwright", "test", "--config", "playwright.config.mjs",
                             "agent-health-runtime.spec.mjs", *args], cwd=harness.REPO / "tests" / "p03", env=env,
                            capture_output=True, text=True, timeout=900)
    log.write_text(result.stdout + result.stderr)
    return result.returncode


def seed(api_url: str, token: str, agent: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=api_url, timeout=60) as client:
        state = ff.ready_for_action(client, headers, agent)  # type: ignore[arg-type]
        response = client.post(f"/v1/agents/{agent}/deployment", headers=headers, json={
            "request_key": "health-activate", "expected_consent_hash": state["consent"]["consent_hash"]})
        assert response.status_code == 201, response.text
        return {"agent": agent, "wallet_id": state["wallet_id"], "deployment_id": response.json()["deployment_id"]}


def api_get(api_url: str, token: str, path: str) -> tuple[int, Any]:
    response = httpx.get(f"{api_url}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=60)
    return response.status_code, response.json()


def sql_inspection(pg: harness.Postgres, snapshots: dict[str, dict[str, Any]],
                   seeded: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Independent SQL for each owner's snapshot: as_of, next work, pending items, stops, inventory, outcomes."""
    expectations: dict[str, bool] = {}
    checks: dict[str, Any] = {}
    for project, health in snapshots.items():
        deployment = seeded[project]["deployment_id"]
        times = rows(pg, f"""
            select 'execution_local.execution_recurring_deployments' tab, deployment_id::text id, 'updated_at' f, updated_at a
              from execution_local.execution_recurring_deployments where deployment_id = '{deployment}'
            union all select 'execution_local.execution_evaluation_jobs', job_id::text, 'updated_at', updated_at
              from execution_local.execution_evaluation_jobs where deployment_id = '{deployment}'
            union all select 'execution_local.execution_evaluation_outcomes', job_id::text, 'evaluated_at', evaluated_at
              from execution_local.execution_evaluation_outcomes where deployment_id = '{deployment}'
            union all select 'execution_local.execution_submission_attempts', attempt_id::text, 'started_at', started_at
              from execution_local.execution_submission_attempts where action_id in (select action_id from
              execution_local.execution_evaluation_jobs where deployment_id = '{deployment}')
            union all select 'execution_local.execution_submission_attempts', attempt_id::text, 'completed_at', completed_at
              from execution_local.execution_submission_attempts where completed_at is not null and action_id in (
              select action_id from execution_local.execution_evaluation_jobs where deployment_id = '{deployment}')
            union all select 'execution_local.execution_queue', queue_id::text, 'updated_at', updated_at
              from execution_local.execution_queue where action_id in (select action_id from
              execution_local.execution_evaluation_jobs where deployment_id = '{deployment}')
            order by 4 desc""")
        cursor = rows(pg, "select to_char((cursor_slot + interval '5 minutes') at time zone 'utc', "
                          "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') n, state from execution_local.execution_recurring_deployments "
                          f"where deployment_id = '{deployment}'")[0]
        unsettled = [r["action_id"] for r in rows(pg, "select action_id from execution_local.execution_queue where "
                     f"agent_id = '{seeded[project]['agent']}' and state in ('CLAIMED','SUBMITTED_UNKNOWN','BREACHED',"
                     "'RECONCILE_MISMATCH') order by enqueued_at")]
        stops = rows(pg, f"select mode, scope from stops_local.scoped_stops where agent_id = '{seeded[project]['agent']}'")
        positions = rows(pg, "select position_id, inventory::text inventory from admission_local.admission_positions "
                             f"where agent_id = '{seeded[project]['agent']}' order by position_id")
        outcomes = rows(pg, "select o.outcome, j.outcome job_outcome from execution_local.execution_evaluation_outcomes o "
                            "join execution_local.execution_evaluation_jobs j using (job_id) where "
                            f"o.deployment_id = '{deployment}' order by o.decision_slot desc")
        newest = times[0]
        checks[project] = {"times": times, "cursor_next": cursor, "unsettled": unsettled, "stops": stops,
                           "positions": positions, "outcomes": outcomes}
        as_of = health["as_of"] or {}
        expectations.update({
            f"{project}: as_of names the newest stored write (table, id, field)":
            (as_of.get("table"), as_of.get("id"), as_of.get("field")) == (newest["tab"], newest["id"], newest["f"]),
            f"{project}: next due slot equals the producer cursor + 5 minutes":
            health["producer"]["next_due_slot"].get("value") == cursor["n"],
            f"{project}: canonical pending reconciliation equals the unsettled queue rows":
            health["pending_reconciliation"]["canonical"]["action_ids"] == unsettled,
            f"{project}: stop rows match":
            sorted((s["mode"], s["scope"]) for s in health["controls"]["stops"]) == sorted((s["mode"], s["scope"]) for s in stops),
            f"{project}: residual inventory matches the saved positions":
            sorted((p["position_id"], p["quantity"]["raw"]) for p in health["residual_inventory"])
            == sorted((p["position_id"], p["inventory"]) for p in positions),
            f"{project}: the last evaluation is the newest saved outcome":
            bool(outcomes) and health["last_evaluation"]["value"]["evaluation"]["outcome"] == outcomes[0]["outcome"],
        })
    return {"checks": checks, "expectations": expectations, "all_checks_pass": bool(checks) and all(expectations.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    evidence: Path = args.evidence.resolve()
    if evidence.exists() and any(evidence.iterdir()):
        print(f"evidence directory {evidence} is not empty", file=sys.stderr)
        return 2
    (evidence / "ui").mkdir(parents=True, exist_ok=True)
    rec = Recorder(evidence)
    run_id = harness.new_run_id()
    pg = harness.Postgres(run_id)
    dist = f".next-health-{run_id}"
    processes: list[harness.Process] = []
    signer = TestSigner()
    started = time.monotonic()
    ok = True
    try:
        pg.start()
        ok &= rec.step("postgres started (isolated, labelled)", True, {"container": pg.container, "run_id": run_id})
        api_port, web_port = harness.free_port(), harness.free_port()
        api_url, web_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
        env = harness.api_env(database_url=pg.url, public_pem=signer.public_pem, previous_pem=None, cors=[web_url])
        env.update({"EDGE_OS_WALLET_PROVIDER": "fixture", "EDGE_OS_EXECUTION_MODE": "fixture",
                    "EDGE_OS_FIXTURE_EFFECTS_PATH": str(evidence / "api-effects.jsonl")})
        migration = harness.migrate(env)
        rec.write("migrate.log", migration.stdout + migration.stderr)
        ok &= rec.step("migrations applied", migration.returncode == 0)
        processes.append(harness.start_api(env, api_port, evidence / "logs"))
        harness.wait_http(f"{api_url}/readyz")
        build = harness.build_web(api_url=api_url, dist=dist, log_dir=evidence / "logs")
        ok &= rec.step("web production build (run-scoped directory)", build.returncode == 0, {"dist": dist})
        if build.returncode != 0:
            raise RuntimeError("web build failed; see logs/")
        processes.append(harness.start_web(api_url=api_url, dist=dist, port=web_port, log_dir=evidence / "logs"))
        harness.wait_http(web_url + "/")

        tokens = {project: signer.token(f"did:privy:test-health-{project}") for project in PROJECTS}
        intruder = signer.token("did:privy:test-health-intruder")
        seeded = {project: seed(api_url, tokens[project], agent) for project, agent in PROJECTS.items()}
        assert api_get(api_url, intruder, "/v1/me")[0] == 200  # the intruder's first sign-in saves its user row
        rec.write("seeded.json", seeded)
        ok &= rec.step("two owners: confirmed, funded agents with adopted terms and one recurring deployment each "
                       "(public API, authored fixtures)", True, seeded)

        producer = recurring_phase.Producer(env, evidence, recurring_phase.anchor_now())
        ok &= rec.step("producer pass at slot 0 with no browser open", producer.run(0) == [0])
        stop = httpx.post(f"{api_url}/v1/agents/{PROJECTS['desktop']}/stops", timeout=60,
                          headers={"Authorization": f"Bearer {tokens['desktop']}"},
                          json={"mode": "STOP_NEW_ENTRIES", "scope": "AGENT_WALLET_NETWORK"})
        ok &= rec.step("desktop owner stops new entries", stop.status_code == 200, stop.json())
        ok &= rec.step("producer pass at slot 5 with no browser open", producer.run(5) == [0])

        ui_env = {"P03_WEB_URL": web_url, "P03_API_URL": api_url, "P03_EVIDENCE_DIR": str(evidence / "ui"),
                  "P31_TOKEN_DESKTOP": tokens["desktop"], "P31_TOKEN_MOBILE_390": tokens["mobile-390"],
                  "P31_TOKEN_INTRUDER": intruder, "P31_AGENT_DESKTOP": PROJECTS["desktop"],
                  "P31_AGENT_MOBILE_390": PROJECTS["mobile-390"]}
        effects = evidence / recurring_phase.EFFECTS_NAME
        before = {"rows": fingerprint(pg), "effects": lines(effects), "api_effects": lines(evidence / "api-effects.jsonl")}
        code = run_playwright(["--grep", "health stage A|health intruder"], ui_env, evidence / "ui-health-a.log")
        ok &= rec.step("browser: direct health panel and read-only conversation quote the API snapshot; unknowns "
                       "explicit; no financial control; another owner refused (desktop and 390px)", code == 0,
                       {"exit": code})
        after = {"rows": fingerprint(pg), "effects": lines(effects), "api_effects": lines(evidence / "api-effects.jsonl")}
        changed = sorted(name for name in before["rows"] if before["rows"][name] != after["rows"].get(name))
        ok &= rec.step("the browser reads wrote no financial row and caused no fixture effect (direct SQL, effect "
                       "records)", not changed and before["effects"] == after["effects"]
                       and before["api_effects"] == after["api_effects"],
                       {"changed_tables": changed, "effects": [before["effects"], after["effects"]],
                        "api_effects": [before["api_effects"], after["api_effects"]]})

        snapshots = {project: api_get(api_url, tokens[project], f"/v1/agents/{agent}/health")[1]
                     for project, agent in PROJECTS.items()}
        rec.write("health-snapshots.json", snapshots)
        inspection = sql_inspection(pg, snapshots, seeded)
        rec.write("health-sql-inspection.json", inspection)
        ok &= rec.step("health snapshots agree with the saved rows (direct SQL)", inspection["all_checks_pass"],
                       inspection["expectations"])

        api = processes.pop(0)
        api.stop()
        processes.insert(0, harness.start_api(env, api_port, evidence / "logs", name="api-restarted"))
        harness.wait_http(f"{api_url}/readyz")
        ok &= rec.step("API restarted on the same port over the same database", True)
        code = run_playwright(["--grep", "health after restart"], ui_env, evidence / "ui-health-restart.log")
        ok &= rec.step("after restart a new browser context reads the same record, snapshot digest, as_of and "
                       "unknowns (desktop and 390px)", code == 0, {"exit": code})
        final = {"rows": fingerprint(pg), "effects": lines(effects), "api_effects": lines(evidence / "api-effects.jsonl")}
        changed = sorted(name for name in after["rows"] if after["rows"][name] != final["rows"].get(name))
        ok &= rec.step("restart and new-context reads wrote no financial row and caused no fixture effect",
                       not changed and final["effects"] == after["effects"]
                       and final["api_effects"] == after["api_effects"], {"changed_tables": changed})
        rec.write("producer-runs.json", {"anchor": producer.anchor.isoformat(), "runs": producer.runs})
    except Exception as error:  # noqa: BLE001 - recorded, then cleanup still runs
        ok = rec.step(f"run stopped: {type(error).__name__}: {error}", False)
        rec.write("error-traceback.txt", traceback.format_exc())
    finally:
        for process in reversed(processes):
            process.stop()
        pg.stop_and_remove()
        shutil.rmtree(harness.WEB_DIR / dist, ignore_errors=True)
        (harness.WEB_DIR / harness.web_tsconfig(dist)).unlink(missing_ok=True)
        leftovers = pg.leftovers()
        ok &= rec.step("cleanup: container, volume, web build and tsconfig removed", not leftovers
                       and not (harness.WEB_DIR / dist).exists(), {"leftovers": leftovers})
        rec.write("run.json", {"run_id": run_id, "ok": ok, "git_sha": harness.git_sha(),
                               "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                               "seconds": round(time.monotonic() - started, 1), "steps": rec.steps})
    print(json.dumps({"ok": ok, "evidence": str(evidence)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
