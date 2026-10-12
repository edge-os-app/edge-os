"""#58 Task 6 recorded-history research phase of the mapped verifier.

Runs inside `verify_run.py` on the same isolated instance. The API runs with `EDGE_OS_RESEARCH_HISTORY_MODE=recorded`,
so every history source is the authored SYNTHETIC recorded-response bundle. The phase drives the declaration and job
screens while no worker runs, stops one job like a killed worker after its collection attempt starts, runs the bounded
research worker once, drives reports, market adoption, publication and history replay, then inspects SQL directly.
After the shared API restart it runs the worker again and reopens everything in a new browser context.

The default run loads no provider credential and makes no provider, model or network call. `--actual-data` is an
explicit opt-in that refuses here: no approved actual-data packet exists and no actual adapter is implemented.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import harness

BUDGET_PROVIDER_REQUESTS = "40"
APPROVED_PACKETS: dict[str, str] = {}  # actual-data packet SHA-256 -> approval record. Empty: nothing is approved.
# Fault injection for the verifier only: the collection tool ends the process after the attempt is saved, exactly
# like a killed worker. The application has no such switch.
KILL_SCRIPT = """
import os, sys, uuid
from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.core.settings import load_settings
from edge_os_api.research import investigation_tools
from edge_os_api.research.investigation_jobs import InvestigationWorker

def killed(*args, **kwargs):
    os._exit(9)

investigation_tools.collect_recorded_history = killed
settings = load_settings()
worker = InvestigationWorker(make_session_factory(make_engine(settings.database_url)), settings)
worker.run_job(uuid.UUID(sys.argv[1]))
"""


def configure(env: dict[str, str]) -> None:
    """Recorded SYNTHETIC history for this isolated run only. Production refuses the recorded mode."""
    env["EDGE_OS_RESEARCH_HISTORY_MODE"] = "recorded"
    env["EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS"] = BUDGET_PROVIDER_REQUESTS
    env["EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS"] = "3600"


def actual_data_refusal(packet: str | None) -> str | None:
    """The opt-in actual-data entry point. Returns the refusal, or None when the default recorded run applies."""
    if packet is None:
        return None
    path = Path(packet)
    if not path.is_file():
        return f"--actual-data needs an approved packet file; {packet} does not exist. Nothing was started."
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest not in APPROVED_PACKETS:
        return (f"--actual-data packet {path.name} (SHA-256 {digest}) has no recorded approval. Actual collection and "
                "inference stay unauthorized. Nothing was started.")
    return "--actual-data is approved but no actual-data adapter exists in this milestone. Nothing was started."


def _rows(pg: harness.Postgres, sql: str) -> list[dict[str, Any]]:
    return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))


def _worker_once(env: dict[str, str], log_dir: Path, name: str) -> int:
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / f"{name}.log", "ab") as handle:
        return subprocess.run([harness.api_python(), "-m", "edge_os_api.research.investigation_jobs", "--once"],
                              cwd=harness.API_DIR, env=env, stdout=handle, stderr=handle, timeout=300).returncode


def _kill_during_collection(env: dict[str, str], job_id: str, log_dir: Path) -> int:
    with open(log_dir / f"research-killed-{job_id}.log", "ab") as handle:
        return subprocess.run([harness.api_python(), "-c", KILL_SCRIPT, job_id], cwd=harness.API_DIR, env=env,
                              stdout=handle, stderr=handle, timeout=120).returncode


def inspect(pg: harness.Postgres, results: dict[str, Any]) -> dict[str, Any]:
    """Direct SQL over `research_local`, the declarations, revisions and replays the browser created."""
    checks: dict[str, Any] = {}
    expectations: dict[str, bool] = {}
    for key, run in results.items():
        jobs = _rows(pg, "select job_id::text, state, terminal_reason, budget, dataset_id::text, report_id::text "
                         f"from research_local.investigation_jobs where declaration_id = '{run['main']}' order by created_at")
        events = {job["job_id"]: [row["kind"] for row in _rows(pg, (
            "select kind from research_local.investigation_events "
            f"where job_id = '{job['job_id']}' order by seq"))] for job in jobs}
        declaration = _rows(pg, "select content->>'schema_version' version, content->>'declaration_state' state, "
                                "content->'frozen' frozen from investigation_declarations "
                                f"where declaration_id = '{run['main']}'")
        greedy = _rows(pg, "select state, budget from research_local.investigation_jobs "
                           f"where declaration_id = '{run['greedy']}'")
        failing = _rows(pg, "select j.state, d.content->>'status' status, d.content->>'stop_reason' stop, "
                            "d.content->'verdict'->>'overall' verdict, d.content->>'binding_state' binding, "
                            "r.content->>'outcome' outcome from research_local.investigation_jobs j "
                            "join research_local.history_datasets d using (dataset_id) "
                            "join research_local.investigation_reports r using (report_id) "
                            f"where j.declaration_id = '{run['failing']}'")
        dataset = _rows(pg, "select content->'verdict'->>'overall' verdict, content->>'evidence_class' evidence, "
                            "content->>'content_label' label, content->'provider_requests' provider_requests, "
                            "content->>'market_binding_id' market from research_local.history_datasets "
                            f"where dataset_id = '{run.get('datasetId')}'") if run.get("datasetId") else []
        revisions = _rows(pg, "select revision_id::text, parent_revision_id::text parent, "
                              "strategy_canonical::jsonb->'market'->'research_binding'->>'pool_address' pool, "
                              "strategy_canonical::jsonb->'sizing'->>'unit' unit, "
                              "strategy_canonical::jsonb->'sizing'->>'amount' amount, "
                              "strategy_canonical::jsonb->'entry'->>'op' entry_op "
                              f"from strategy_revisions where strategy_id = '{run.get('strategyId')}' order by created_at")
        replays = _rows(pg, "select replay_id::text, content->'result'->>'status' status, "
                            "content->'result'->'reason'->>'code' reason, "
                            "content->'inputs'->'history_input'->>'dataset_id' dataset, "
                            "content->'inputs'->'history_input'->>'declaration_id' declaration, "
                            "content->'inputs'->'history_input'->>'fill_label' fills, "
                            "content->'inputs'->'history_input'->'rule_linkage'->>'state' linkage "
                            "from spot_replay_runs where replay_id in "
                            f"('{run.get('replayId')}', '{run.get('mismatchReplayId')}')")
        by_id = {row["replay_id"]: row for row in replays}
        checks[key] = {"jobs": jobs, "events": events, "declaration": declaration, "greedy": greedy,
                       "failing": failing, "dataset": dataset, "revisions": revisions, "replays": replays}
        states = [job["state"] for job in jobs]
        expectations.update({
            f"{key}: declaration saved pre-outcome with frozen hashes": bool(declaration)
            and declaration[0]["version"] == "p08.investigation-declaration/3"
            and declaration[0]["state"] == "PRE_OUTCOME_DECLARED" and bool(declaration[0]["frozen"]),
            f"{key}: job states (reported, cancelled, reported, unavailable, retried)": states[:4]
            == ["REPORTED", "CANCELLED", "REPORTED", "UNAVAILABLE"] and len(states) == 5,
            f"{key}: reservation precedes every collection attempt": all(
                kinds.index("BUDGET_RESERVED") < kinds.index("ATTEMPT_STARTED")
                for kinds in events.values() if "ATTEMPT_STARTED" in kinds),
            f"{key}: killed job reconciled without a second collection": len(jobs) > 3
            and events[jobs[3]["job_id"]].count("ATTEMPT_STARTED") == 1
            and "ATTEMPT_RECONCILED" in events[jobs[3]["job_id"]]
            and jobs[3]["budget"]["unknown_liability"]["provider_requests"] == 2,
            f"{key}: cancelled job released its reservation": len(jobs) > 1
            and jobs[1]["budget"]["released"]["provider_requests"] == 2 and jobs[1]["dataset_id"] is None,
            f"{key}: budget denial saved with nothing reserved": bool(greedy) and greedy[0]["state"] == "BUDGET_EXHAUSTED"
            and greedy[0]["budget"]["reserved"]["provider_requests"] == 0,
            f"{key}: provider failure saved as partial source loss, never bound": bool(failing)
            and failing[0]["status"] == "PARTIAL" and failing[0]["stop"] == "PROVIDER_ERROR"
            and failing[0]["binding"] == "UNAVAILABLE_LIMITED_DATA" and failing[0]["outcome"] == "SOURCE_LOSS",
            f"{key}: dataset is labelled synthetic recorded responses": bool(dataset) and dataset[0]["verdict"] == "QUALIFIED"
            and dataset[0]["evidence"] == "RECORDED_RESPONSE" and dataset[0]["label"] == "SYNTHETIC_FIXTURE",
            f"{key}: adopted revision is new and the fixture revision unchanged": len(revisions) == 2
            and revisions[1]["parent"] == revisions[0]["revision_id"]
            and revisions[0]["pool"] == "0x3333333333333333333333333333333333333333"
            and revisions[1]["pool"] == "0x" + "aa" * 20 and revisions[1]["unit"] == "QUOTE:0x" + "bb" * 20
            and revisions[1]["amount"] == "50" and revisions[1]["entry_op"] == "and",
            f"{key}: history replay saved with exact lineage and simulated fills": run.get("replayId") in by_id
            and by_id[run["replayId"]]["status"] == "COMPLETE" and by_id[run["replayId"]]["dataset"] == run["datasetId"]
            and by_id[run["replayId"]]["declaration"] == run["main"] and by_id[run["replayId"]]["fills"] == "simulated fills"
            and by_id[run["replayId"]]["linkage"] == "ENTRY_IS_DECLARED_RULE",
            f"{key}: fixture revision refused on the history market": run.get("mismatchReplayId") in by_id
            and by_id[run["mismatchReplayId"]]["reason"] == "MARKET_BINDING_MISMATCH",
        })
    counts = _rows(pg, "select (select count(*) from research_local.history_datasets) datasets, "
                       "(select count(*) from research_local.investigation_reports) reports, "
                       "(select count(*) from research_local.investigation_events) events")[0]
    return {"checks": checks, "expectations": expectations, "counts": counts,
            "all_checks_pass": bool(results) and all(expectations.values())}


def inspect_native(pg: harness.Postgres, results: dict[str, Any]) -> dict[str, Any]:
    """Direct SQL over the SOURCE-LOCAL native journeys: the saved transport provenance, settlement and replay."""
    checks: dict[str, Any] = {}
    expectations: dict[str, bool] = {}
    for key, run in results.items():
        if not key.startswith("native-"):
            continue
        rows = _rows(pg, "select j.state, j.budget, d.content->>'evidence_class' evidence, "
                         "d.content->>'content_label' label, d.content->'verdict'->>'overall' verdict, "
                         "d.content->>'provider_requests_state' usage_state, d.content->'provider_requests' usage, "
                         "d.content->'transport'->'client_calls' calls, "
                         "d.content->'transport'->'corroboration'->>'class' corroboration, "
                         "(d.content->'transport'->'corroboration'->>'mismatches')::int mismatches, "
                         "(d.content->'transport'->'chain_read'->>'chain_id')::int chain, "
                         "d.content->'transport'->'envio'->'content_sha256' page_hashes, "
                         "d.content->'evidence_basis'->>'decimals' decimals_basis, d.content_sha256, "
                         "d.content->'query'->>'address' pool from research_local.investigation_jobs j "
                         "join research_local.history_datasets d using (dataset_id) "
                         f"where j.declaration_id = '{run['declarationId']}'")
        replay = _rows(pg, "select content->'result'->>'status' status, "
                           "content->'inputs'->'history_input'->>'source_evidence_class' evidence, "
                           "content->'inputs'->'history_input'->>'fill_label' fills, "
                           "content->'inputs'->'history_input'->>'dataset_id' dataset from spot_replay_runs "
                           f"where replay_id = '{run.get('replayId')}'") if run.get("replayId") else []
        checks[key] = {"dataset": rows, "replay": replay}
        row = rows[0] if rows else {}
        expectations.update({
            f"{key}: native job reported with a labelled synthetic native dataset": row.get("state") == "REPORTED"
            and row.get("evidence") == "RECORDED_NATIVE_RESPONSE" and row.get("label") == "SYNTHETIC_FIXTURE"
            and row.get("verdict") == "QUALIFIED" and row.get("pool") == "0x" + "d1" * 20,
            f"{key}: transport provenance saved (2 Envio calls, 25 RPC calls, chain 143, 24 receipts matched)":
            row.get("calls") == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 25} and row.get("chain") == 143
            and row.get("corroboration") == "COMPLETE" and row.get("mismatches") == 0
            and len(row.get("page_hashes") or []) == 2 and row.get("decimals_basis") == "RECORDED_DECLARATION",
            f"{key}: measured client calls settled inside the reservation": row.get("usage_state") == "MEASURED_CLIENT_CALLS"
            and row.get("budget", {}).get("consumed", {}).get("provider_requests") == 27
            and row.get("budget", {}).get("unknown_liability", {}).get("provider_requests") == 0,
            f"{key}: replay on the native dataset is labelled simulated": bool(replay)
            and replay[0]["status"] == "COMPLETE" and replay[0]["evidence"] == "RECORDED_NATIVE_RESPONSE"
            and replay[0]["fills"] == "simulated fills" and replay[0]["dataset"] == run.get("datasetId"),
        })
    return {"checks": checks, "expectations": expectations,
            "all_checks_pass": bool(checks) and all(expectations.values())}


def drive(rec: Any, pg: harness.Postgres, env: dict[str, str], evidence: Path, ui_env: dict[str, str],
          run_playwright: Callable[..., int]) -> tuple[bool, dict[str, Any]]:
    log_dir = evidence / "logs"
    code = run_playwright(["research-history-journey.spec.mjs"], ui_env, evidence / "ui-research-journey.log")
    ok = rec.step("research journey: declare first, waiting, cancel, retry, budget denial (desktop and 390px)",
                  code == 0, {"exit": code})
    code = run_playwright(["research-native-journey.spec.mjs"], ui_env, evidence / "ui-research-native-journey.log")
    ok &= rec.step("SOURCE-LOCAL native journey: declaration on a native recording and its original job, no worker "
                   "running (desktop and 390px, one owner each)", code == 0, {"exit": code})
    results_path = evidence / "ui" / "research-results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    killed = {key: _kill_during_collection(env, run["jobs"]["killed"], log_dir) for key, run in results.items()
              if key.startswith("research-")}
    ok &= rec.step("killed worker: the collection attempt was saved, then the process ended (exit 9)",
                   bool(killed) and all(value == 9 for value in killed.values()), killed)
    worker = _worker_once(env, log_dir, "research-worker-1")
    ok &= rec.step("bounded research worker pass (recorded responses only)", worker == 0, {"exit": worker})
    code = run_playwright(["research-history-report.spec.mjs"], ui_env, evidence / "ui-research-report.log")
    ok &= rec.step("research reports, source loss, killed-job retry, market adoption, publication and labelled "
                   "history replay (desktop and 390px)", code == 0, {"exit": code})
    code = run_playwright(["research-native-report.spec.mjs"], ui_env, evidence / "ui-research-native-report.log")
    ok &= rec.step("SOURCE-LOCAL native report, transport facts, market adoption, publication and labelled replay; "
                   "owner B denied (desktop and 390px)", code == 0, {"exit": code})
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    inspection = inspect(pg, {key: run for key, run in results.items() if key.startswith("research-")})
    rec.write("research-inspection.json", inspection)
    ok &= rec.step("research rows, revisions and replays match the screens (direct SQL)",
                   inspection["all_checks_pass"], inspection["expectations"])
    native = inspect_native(pg, results)
    rec.write("research-native-inspection.json", native)
    ok &= rec.step("SOURCE-LOCAL native datasets keep transport provenance, measured settlement and replay lineage "
                   "(direct SQL)", native["all_checks_pass"], native["expectations"])
    inspection["native"] = native
    return ok, inspection


def after_restart(rec: Any, pg: harness.Postgres, env: dict[str, str], evidence: Path, ui_env: dict[str, str],
                  run_playwright: Callable[..., int], before: dict[str, Any]) -> bool:
    worker = _worker_once(env, evidence / "logs", "research-worker-restarted")
    ok = rec.step("research worker pass after the API restart finishes the retried job", worker == 0, {"exit": worker})
    code = run_playwright(["research-history-restart.spec.mjs"], ui_env, evidence / "ui-research-restart.log")
    ok &= rec.step("research report, dataset, adopted revision and history replay reopen unchanged; owner B denied "
                   "(new browser context)", code == 0, {"exit": code})
    results = json.loads((evidence / "ui" / "research-results.json").read_text())
    after = inspect(pg, {key: run for key, run in results.items() if key.startswith("research-")})
    native_after = inspect_native(pg, results)
    rec.write("research-native-inspection-after-restart.json", native_after)
    ok &= rec.step("SOURCE-LOCAL native datasets, settlement and replays unchanged by the restart (direct SQL)",
                   "native" in before and native_after["checks"] == before["native"]["checks"])
    rec.write("research-inspection-after-restart.json", after)
    unchanged = {key: {name: value for name, value in check.items() if name not in {"jobs", "events"}}
                 for key, check in before["checks"].items()}
    now = {key: {name: value for name, value in check.items() if name not in {"jobs", "events"}}
           for key, check in after["checks"].items()}
    ok &= rec.step("saved datasets, reports, revisions and replays unchanged by the restart", unchanged == now)
    retried = {key: check["jobs"][4]["state"] if len(check["jobs"]) > 4 else None for key, check in after["checks"].items()}
    ok &= rec.step("retried jobs reported after the restart; earlier jobs and attempts kept",
                   all(state == "REPORTED" for state in retried.values()) and all(
                       [job["state"] for job in after["checks"][key]["jobs"][:4]]
                       == [job["state"] for job in before["checks"][key]["jobs"][:4]] for key in after["checks"]), retried)
    return ok
