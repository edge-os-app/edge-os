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
    # RESEARCH-PORTS-LOCAL: the accepted P07 HTTP clients and the Nansen package over the application's AUTHORED
    # transports (no network, no credential). Production refuses both values.
    env["EDGE_OS_RESEARCH_SOURCE_CLIENTS"] = "authored_http"
    env["EDGE_OS_NANSEN_RESEARCH_MODE"] = "authored_fixture"


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


def inspect_ports(pg: harness.Postgres, results: dict[str, Any]) -> dict[str, Any]:
    """Direct SQL over the RESEARCH-PORTS-LOCAL journeys: the HTTP-client dataset, the Nansen request, report, job
    kind and its separate credit settlement in the shared quota ledger."""
    checks: dict[str, Any] = {}
    expectations: dict[str, bool] = {}
    ports = {key: run for key, run in results.items() if key.startswith("ports-")}
    for key, run in ports.items():
        http = _rows(pg, "select j.kind, j.state, j.budget, d.content->>'evidence_class' evidence, "
                         "d.content->>'content_label' label, d.content->'verdict'->>'overall' verdict, "
                         "d.content->'transport'->>'clients' clients, d.content->'transport'->'client_classes' classes, "
                         "d.content->'transport'->>'transport_label' transport_label, "
                         "d.content->'transport'->'http_accounting' accounting, "
                         "jsonb_array_length(d.content->'transport'->'response_sha256') responses, "
                         "d.content->'transport'->'client_calls' calls, d.content_sha256, "
                         "position('authored-local-fixture' in d.content::text) bearer_in_record "
                         "from research_local.investigation_jobs j join research_local.history_datasets d using (dataset_id) "
                         f"where j.declaration_id = '{run['declarationId']}'")
        nansen = _rows(pg, "select j.kind, j.state, j.terminal_reason, j.budget, j.declaration_id::text request_id, "
                           "q.content->'request'->>'question' request_question, q.content_sha256 request_sha256, "
                           "r.report_id::text, r.content_sha256, r.content->>'evidence_class' evidence, "
                           "r.content->>'transport_label' transport_label, r.content->'report'->>'question' question, "
                           "r.content->'report'->>'answer_state' answer, r.content->'settlement' settlement, "
                           "r.request_id = q.request_id request_bound "
                           "from research_local.investigation_jobs j "
                           "join research_local.nansen_requests q on q.request_id = j.declaration_id "
                           "join research_local.nansen_reports r on r.job_id = j.job_id "
                           f"where j.job_id = '{run['nansenJobId']}'")
        events = [row["kind"] for row in _rows(pg, "select kind from research_local.investigation_events "
                                                   f"where job_id = '{run['nansenJobId']}' order by seq")]
        reservation = _rows(pg, "select amounts, settled from usage_local.usage_reservations "
                                f"where subject_id = '{run['nansenJobId']}'")
        checks[key] = {"http": http, "nansen": nansen, "events": events, "reservation": reservation}
        row, report = (http[0] if http else {}), (nansen[0] if nansen else {})
        expectations.update({
            f"{key}: HTTP-client job reported a labelled authored dataset": row.get("kind") == "HISTORY_INVESTIGATION"
            and row.get("state") == "REPORTED" and row.get("evidence") == "AUTHORED_HTTP_RESPONSE"
            and row.get("label") == "SYNTHETIC_FIXTURE" and row.get("verdict") == "QUALIFIED",
            f"{key}: the accepted P07 HTTP client classes served 27 authored responses":
            row.get("clients") == "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT" and row.get("classes") == {
                "ENVIO_HYPERSYNC": "HttpEnvioQueryClient", "QUICKNODE_JSON_RPC": "HttpQuickNodeRpcClient"}
            and row.get("transport_label") == "AUTHORED_HTTP_TRANSPORT" and row.get("responses") == 27
            and row.get("calls") == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 25}
            and all(item.get("unknown_liability") == 0 for item in (row.get("accounting") or {"x": {}}).values()),
            f"{key}: the authored bearer value is absent from the saved dataset": row.get("bearer_in_record") == 0,
            f"{key}: HTTP-client usage settled as measured calls": row.get("budget", {}).get("consumed", {})
            .get("provider_requests") == 27,
            f"{key}: Nansen job saved its request and one bound report": report.get("kind") == "NANSEN_REPORT"
            and report.get("state") == "REPORTED" and report.get("request_bound") is True
            and report.get("evidence") == "AUTHORED_FIXTURE" and report.get("transport_label") == "AUTHORED_NANSEN_TRANSPORT",
            f"{key}: the report question is the saved request text, unchanged": bool(report.get("question"))
            and report.get("question") == report.get("request_question") == run.get("question"),
            f"{key}: Nansen credits reserved separately and settled as known": bool(reservation)
            and reservation[0]["amounts"].get("nansen_credits") == 12
            and report.get("budget", {}).get("consumed", {}).get("nansen_credits") == 6
            and report.get("budget", {}).get("unknown_liability", {}).get("nansen_credits") == 0
            and (report.get("settlement") or {}).get("nansen_credits", {}).get("state") == "KNOWN",
            f"{key}: one Nansen attempt, reserved before it started": events.count("ATTEMPT_STARTED") == 1
            and "BUDGET_RESERVED" in events and events.index("BUDGET_RESERVED") < events.index("ATTEMPT_STARTED"),
        })
    allocations = _rows(pg, "select scope, cap, reserved, consumed, unknown from usage_local.usage_allocations "
                            "where resource = 'nansen_credits' order by scope, owner_key")
    checks["nansen_credit_allocations"] = allocations
    expectations["global Nansen credit ledger holds exactly the known charges"] = bool(ports) and any(
        row["scope"] == "GLOBAL" and row["consumed"] == 6 * len(ports) and row["reserved"] == 0 and row["unknown"] == 0
        for row in allocations)
    return {"checks": checks, "expectations": expectations,
            "all_checks_pass": bool(ports) and all(expectations.values())}


def drive(rec: Any, pg: harness.Postgres, env: dict[str, str], evidence: Path, ui_env: dict[str, str],
          run_playwright: Callable[..., int]) -> tuple[bool, dict[str, Any]]:
    log_dir = evidence / "logs"
    code = run_playwright(["research-history-journey.spec.mjs"], ui_env, evidence / "ui-research-journey.log")
    ok = rec.step("research journey: declare first, waiting, cancel, retry, budget denial (desktop and 390px)",
                  code == 0, {"exit": code})
    code = run_playwright(["research-native-journey.spec.mjs"], ui_env, evidence / "ui-research-native-journey.log")
    ok &= rec.step("SOURCE-LOCAL native journey: declaration on a native recording and its original job, no worker "
                   "running (desktop and 390px, one owner each)", code == 0, {"exit": code})
    code = run_playwright(["research-ports-journey.spec.mjs"], ui_env, evidence / "ui-research-ports-journey.log")
    ok &= rec.step("RESEARCH-PORTS-LOCAL: declaration on the P07 HTTP-client source and a Nansen report request on the "
                   "same saved request, no worker running (desktop and 390px, one owner each)", code == 0, {"exit": code})
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
    code = run_playwright(["research-ports-report.spec.mjs"], ui_env, evidence / "ui-research-ports-report.log")
    ok &= rec.step("RESEARCH-PORTS-LOCAL: HTTP-client dataset with labelled client facts and the reopened Nansen report "
                   "(exact question, findings, gaps, recomputed hashes); owner B denied (desktop and 390px)",
                   code == 0, {"exit": code})
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
    ports = inspect_ports(pg, results)
    rec.write("research-ports-inspection.json", ports)
    ok &= rec.step("RESEARCH-PORTS-LOCAL datasets, Nansen requests, reports and separate credit settlement match the "
                   "screens (direct SQL)", ports["all_checks_pass"], ports["expectations"])
    inspection["ports"] = ports
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
    ports_after = inspect_ports(pg, results)
    rec.write("research-ports-inspection-after-restart.json", ports_after)
    ok &= rec.step("RESEARCH-PORTS-LOCAL datasets, Nansen reports and credit settlement unchanged by the restart; "
                   "reopening ran nothing again (direct SQL)",
                   "ports" in before and ports_after["checks"] == before["ports"]["checks"])
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


# ------------------------------------------------------------------------------------------- RESEARCH-RUNTIME-LOCAL
# The operating-release composition, proved with an owned loopback STAND-IN provider only. The API and the worker run
# with a stand-in release composed by these verifier-only host scripts; no setting can compose one. The stand-in
# provider is its own process and logs every request it receives, so request counts come from outside the
# application. Nothing reaches a real provider.

RELEASE_ID, CHANGED_RELEASE_ID = "stand-in-loopback/1", "stand-in-loopback/2"
RELEASE_SENTINELS = ("stand-in-bearer-SENTINEL-7d41c0", "stand-in-key-SENTINEL-55e0a1", "stand-in-nansen-SENTINEL-2b9c44")
_RELEASE_PRELUDE = """
import os, sys
sys.path.insert(0, os.environ["P03_RELEASE_TESTS_DIR"])
import operating_release_stand_in as stand_in
"""
STAND_IN_PROVIDER = _RELEASE_PRELUDE + """
import time
from pathlib import Path
stand_in.LoopbackStandInProvider("native-syn-qualified/1", Path(sys.argv[2]), port=int(sys.argv[1])).start()
while True:
    time.sleep(3600)
"""
# R58-RESEARCH-MOUNT-L2: the Nansen stand-in, reached through the accepted NansenHttpTransport and a loopback connector
# only. Its own log counts the requests it received, outside the application.
STAND_IN_NANSEN = _RELEASE_PRELUDE + """
import time
from pathlib import Path
stand_in.LoopbackStandInNansen(Path(sys.argv[2]), port=int(sys.argv[1])).start()
while True:
    time.sleep(3600)
"""
RELEASE_HOST = _RELEASE_PRELUDE + """
import uvicorn
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
settings = load_settings()
runtime, _ = stand_in.loopback_runtime_at(settings, int(os.environ["P03_STAND_IN_PORT"]),
                                          release_id=os.environ["P03_RELEASE_ID"],
                                          nansen_port=int(os.environ["P03_STAND_IN_NANSEN_PORT"]))
uvicorn.run(create_app(settings, research_runtime=runtime), host="127.0.0.1", port=int(sys.argv[1]),
            log_level="warning")
"""
# Fault injection for the verifier only: `kill` / `kill-nansen` end the worker process right after the first stand-in
# history / Nansen reply, exactly like a killed worker; `missing` / `missing-nansen` compose the release without its
# QuickNode / Nansen credential; `late` runs the worker 601 s after now, past every saved 600 s deadline. The application
# has none of these.
RELEASE_WORKER = _RELEASE_PRELUDE + """
import datetime as dt
import uuid
from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.core.research import released_source_runtime
from edge_os_api.core.settings import load_settings
from edge_os_api.research.investigation_jobs import InvestigationWorker, utcnow
settings = load_settings()
mode = sys.argv[1]
missing = {"missing": (stand_in.QUICKNODE_SLOT,), "missing-nansen": (stand_in.NANSEN_SLOT,)}.get(mode, ())
runtime, _ = stand_in.loopback_runtime_at(settings, int(os.environ["P03_STAND_IN_PORT"]),
                                          release_id=os.environ["P03_RELEASE_ID"], missing=missing,
                                          nansen_port=int(os.environ["P03_STAND_IN_NANSEN_PORT"]))
if mode in ("kill", "kill-nansen"):
    name = "HashingTransport" if mode == "kill" else "ReleasedNansenTransport"
    original = getattr(released_source_runtime, name).request
    def killed(self, *args, **kwargs):
        original(self, *args, **kwargs)
        os._exit(9)
    setattr(getattr(released_source_runtime, name), "request", killed)
clock = (lambda: utcnow() + dt.timedelta(seconds=601)) if mode == "late" else utcnow
worker = InvestigationWorker(make_session_factory(make_engine(settings.database_url)), settings,
                             research_runtime=runtime, clock=clock)
for job_id in sys.argv[2:]:
    worker.run_job(uuid.UUID(job_id))
"""
# Saves fault-case declarations and jobs through the public API, with the same request shapes the API tests use.
RELEASE_DRIVER = _RELEASE_PRELUDE + """
import json, uuid
import httpx
from research_flows import declare, jobs_path
client = httpx.Client(base_url=os.environ["P03_API_URL"], timeout=60)
tokens = json.loads(os.environ["P03_RELEASE_FAULT_TOKENS"])  # one owner per case: each job fits its owner's budget
out = {}
for name in sys.argv[1].split(","):
    headers = {"Authorization": "Bearer " + tokens[name]}
    source = next(item for item in client.get("/v1/research/history-sources", headers=headers).json()["sources"]
                  if "release" in item)
    intake_id, declaration_id, _ = declare(client, headers, source_id=source["source_id"],
                                           bounds=source["release"]["history"]["limits"])
    started = client.post(jobs_path(intake_id, declaration_id), headers=headers,
                          json={"operation_id": str(uuid.uuid4()), "request_key": "verifier-" + name})
    out[name] = {"intake_id": intake_id, "declaration_id": declaration_id, "status": started.status_code,
                 "job_id": started.json().get("job_id")}
print(json.dumps(out))
"""
# Saves one release Nansen report job per fault owner through the public API, with the release's fixed request.
NANSEN_DRIVER = _RELEASE_PRELUDE + """
import json, uuid
import httpx
from research_flows import investigation_request
client = httpx.Client(base_url=os.environ["P03_API_URL"], timeout=60)
tokens = json.loads(os.environ["P03_RELEASE_FAULT_TOKENS"])
out = {}
for name in sys.argv[1].split(","):
    headers = {"Authorization": "Bearer " + tokens[name]}
    intake_id = investigation_request(client, headers)["intake"]["record_id"]
    listed = client.get(f"/v1/research/requests/{intake_id}/nansen-reports", headers=headers).json()
    started = client.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=headers,
                          json={"operation_id": str(uuid.uuid4()), "request_key": "verifier-nansen-" + name,
                                **listed["operating_release"]["request"]})
    out[name] = {"intake_id": intake_id, "status": started.status_code, "job_id": started.json().get("job_id"),
                 "release": listed["operating_release"]["release_id"]}
print(json.dumps(out))
"""
# Which Nansen fault each fault owner carries, and the worker mode that drives it.
NANSEN_FAULTS = {"kill": "kill-nansen", "stale": "late", "missing": "missing-nansen"}


def _release_env(env: dict[str, str], port: int, release_id: str = RELEASE_ID,
                 nansen_port: int | None = None) -> dict[str, str]:
    # A release Nansen part and the authored Nansen mode cannot both serve reports, so the release processes turn the
    # authored mode off; the standard API keeps it.
    return {**env, "P03_RELEASE_TESTS_DIR": str(harness.API_DIR / "tests"), "P03_STAND_IN_PORT": str(port),
            "P03_RELEASE_ID": release_id, "P03_STAND_IN_NANSEN_PORT": str(nansen_port or 0),
            "EDGE_OS_NANSEN_RESEARCH_MODE": "unavailable"}


def _spawn(env: dict[str, str], name: str, script: str, args: list[str], log_dir: Path) -> harness.Process:
    log_dir.mkdir(parents=True, exist_ok=True)
    handle = open(log_dir / f"{name}.log", "ab")
    popen = subprocess.Popen([harness.api_python(), "-c", script, *args], cwd=harness.API_DIR, env=env,
                             stdout=handle, stderr=handle, start_new_session=True)
    return harness.Process(name, popen, log_dir / f"{name}.log", handle)


def _release_worker(env: dict[str, str], log_dir: Path, name: str, mode: str, job_ids: list[str]) -> int:
    """One bounded worker process over this phase's own jobs only, so no other phase's saved job is advanced."""
    with open(log_dir / f"{name}.log", "ab") as handle:
        return subprocess.run([harness.api_python(), "-c", RELEASE_WORKER, mode, *job_ids], cwd=harness.API_DIR,
                              env=env, stdout=handle, stderr=handle, timeout=300).returncode


def stand_in_requests(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text().splitlines() if line] if log.exists() else []


def inspect_release(pg: harness.Postgres, results: dict[str, Any], faults: dict[str, Any],
                    requests: list[dict[str, Any]]) -> dict[str, Any]:
    """Direct SQL over the release jobs, datasets, reports and replays, compared with the stand-in provider's own
    request log."""
    from collections import Counter

    runs = {key: run for key, run in results.items() if key.startswith("release-")}
    job_ids = [run["jobId"] for run in runs.values()] + [case["job_id"] for case in faults.values()]
    jobs = {row["job_id"]: row for row in _rows(pg, (
        "select j.job_id::text, j.state, j.terminal_reason, j.budget, d.content->>'evidence_class' evidence, "
        "d.content->>'content_label' label, d.content->>'profile_evidence_class' profile_evidence, "
        "d.content->>'transport_kind' transport_kind, d.content->'operating_release' release, "
        "d.content->'transport'->'request_sha256' request_hashes, d.content->'transport'->'endpoint_hosts' hosts, "
        "d.content->'application_collection_time' collected, d.content->>'query_sha256' query_sha256, "
        "d.content->'release_coverage' coverage, d.content->'verdict'->>'overall' verdict, "
        "r.content->>'evidence_class' report_evidence, r.content->>'outcome' outcome "
        "from research_local.investigation_jobs j "
        "left join research_local.history_datasets d using (dataset_id) "
        "left join research_local.investigation_reports r using (report_id) "
        "where j.job_id::text in (" + ",".join(f"'{job_id}'" for job_id in job_ids) + ")"))} if job_ids else {}
    events = {job_id: [row["kind"] for row in _rows(pg, (
        f"select kind from research_local.investigation_events where job_id = '{job_id}' order by seq"))]
              for job_id in job_ids}
    replays = _rows(pg, "select content->'result'->>'status' status, "
                        "content->'inputs'->'history_input'->>'source_evidence_class' evidence, "
                        "content->'inputs'->'history_input'->>'fill_label' fills, "
                        "content->'inputs'->'history_input'->>'dataset_id' dataset from spot_replay_runs where "
                        "replay_id::text in (" + ",".join(f"'{run.get('replayId')}'" for run in runs.values()) + ")"
                    ) if runs else []
    dump = pg.psql("select concat_ws('|', (select string_agg(t::text, '') from research_local.history_datasets t), "
                   "(select string_agg(t::text, '') from research_local.investigation_events t), "
                   "(select string_agg(t::text, '') from research_local.investigation_reports t))")
    saved_hashes = Counter(hash_ for row in jobs.values() for hash_ in (row["request_hashes"] or []))
    logged = Counter(entry["body_sha256"] for entry in requests)
    expectations: dict[str, bool] = {}
    for key, run in runs.items():
        row = jobs.get(run["jobId"], {})
        kinds = events.get(run["jobId"], [])
        expectations.update({
            f"{key}: reported on the loopback stand-in with stand-in labels": row.get("state") == "REPORTED"
            and row.get("evidence") == "RELEASE_STAND_IN_RESPONSE" and row.get("label") == "SYNTHETIC_FIXTURE"
            and row.get("profile_evidence") == "SYNTHETIC_FIXTURE" and row.get("transport_kind") == "LOOPBACK_HTTP"
            and row.get("report_evidence") == "RELEASE_STAND_IN_RESPONSE" and row.get("verdict") == "QUALIFIED",
            f"{key}: release identity, query hash, hosts, coverage and collection times saved":
            (row.get("release") or {}).get("release_id") == RELEASE_ID and bool(row.get("query_sha256"))
            and row.get("hosts") == {"ENVIO_HYPERSYNC": "127.0.0.1", "QUICKNODE_JSON_RPC": "127.0.0.1"}
            and row.get("coverage") == {"required": "COMPLETE_SCAN", "met": True}
            and (row.get("collected") or {}).get("basis") == "APPLICATION_CLOCK",
            f"{key}: 27 measured calls settled; reservation before the one attempt":
            (row.get("budget") or {}).get("consumed", {}).get("provider_requests") == 27
            and len(row.get("request_hashes") or []) == 27 and kinds.count("ATTEMPT_STARTED") == 2
            and "BUDGET_RESERVED" in kinds and kinds.index("BUDGET_RESERVED") < kinds.index("ATTEMPT_STARTED"),
        })
    kill, stale, missing = (jobs.get(faults.get(name, {}).get("job_id"), {}) for name in ("kill", "stale", "missing"))
    kill_events = events.get(faults.get("kill", {}).get("job_id"), [])
    extra = logged - saved_hashes
    expectations.update({
        "killed worker: outcome unknown, whole reservation kept, one attempt only":
        (kill.get("state"), kill.get("terminal_reason")) == ("UNAVAILABLE", "collection_outcome_unknown")
        and (kill.get("budget") or {}).get("unknown_liability", {}).get("provider_requests") == 27
        and kill_events.count("ATTEMPT_STARTED") == 1 and "ATTEMPT_RECONCILED" in kill_events,
        "changed release: refused before any credential read or request; everything released":
        (stale.get("state"), stale.get("terminal_reason")) == ("UNAVAILABLE", "operating_release_changed")
        and (stale.get("budget") or {}).get("released", {}).get("provider_requests") == 27,
        "missing credential: refused before any request; everything released":
        (missing.get("state"), missing.get("terminal_reason")) == (
            "UNAVAILABLE", "operating_release_credential_unavailable")
        and (missing.get("budget") or {}).get("released", {}).get("provider_requests") == 27,
        "the stand-in provider received exactly the saved requests plus the killed worker's one":
        sum(extra.values()) == 1 and not (saved_hashes - logged)
        and len(requests) == 27 * len(runs) + 1 and all(entry["authorized"] for entry in requests),
        "replays on release datasets are labelled stand-in and simulated": bool(replays) and len(replays) == len(runs)
        and all(item["status"] == "COMPLETE" and item["evidence"] == "RELEASE_STAND_IN_RESPONSE"
                and item["fills"] == "simulated fills" for item in replays),
        "no stand-in credential is saved in any research row": not any(value in dump for value in RELEASE_SENTINELS),
    })
    return {"jobs": jobs, "events": events, "replays": replays, "stand_in_requests": len(requests),
            "expectations": expectations, "all_checks_pass": bool(runs) and all(expectations.values())}


def inspect_release_nansen(pg: harness.Postgres, results: dict[str, Any], faults: dict[str, Any],
                           requests: list[dict[str, Any]]) -> dict[str, Any]:
    """Direct SQL over the release Nansen report jobs (R58-RESEARCH-MOUNT-L2), compared with the Nansen stand-in's own
    request log: saved original deadline, state and stop reason, request and credit settlement, labels, the original
    attempt, and no stand-in key in any saved row."""
    runs = {key: run for key, run in results.items() if key.startswith("release-") and run.get("nansenJobId")}
    job_ids = [run["nansenJobId"] for run in runs.values()] + [case["job_id"] for case in faults.values()]
    jobs = {row["job_id"]: row for row in _rows(pg, (
        "select j.job_id::text, j.state, j.terminal_reason, j.budget, "
        "extract(epoch from j.deadline_at - j.created_at)::int deadline_seconds, "
        "q.content->'operating_release'->>'release_id' request_release, r.content->>'evidence_class' evidence, "
        "r.content->>'transport_kind' transport_kind, r.content->>'transport_label' label, "
        "r.content->'operating_release'->>'release_id' report_release, r.content->'settlement' settlement, "
        "jsonb_array_length(r.content->'transport_response_sha256') reply_hashes, r.content_sha256 "
        "from research_local.investigation_jobs j "
        "join research_local.nansen_requests q on q.request_id = j.declaration_id "
        "left join research_local.nansen_reports r on r.job_id = j.job_id "
        "where j.job_id::text in (" + ",".join(f"'{job_id}'" for job_id in job_ids) + ")"))} if job_ids else {}
    events = {job_id: [row["kind"] for row in _rows(pg, (
        f"select kind from research_local.investigation_events where job_id = '{job_id}' order by seq"))]
              for job_id in job_ids}
    dump = pg.psql("select concat_ws('|', (select string_agg(t::text, '') from research_local.nansen_requests t), "
                   "(select string_agg(t::text, '') from research_local.nansen_reports t), "
                   "(select string_agg(t::text, '') from research_local.investigation_events t))")
    whole = {"provider_requests": 4, "compute_seconds": 30, "nansen_credits": 12}
    expectations: dict[str, bool] = {}
    for key, run in runs.items():
        row, kinds = jobs.get(run["nansenJobId"], {}), events.get(run["nansenJobId"], [])
        settlement = row.get("settlement") or {}
        expectations.update({
            f"{key} Nansen: reported over the accepted adapter to the loopback stand-in with stand-in labels":
            row.get("state") == "REPORTED" and row.get("evidence") == "RELEASE_STAND_IN_RESPONSE"
            and row.get("transport_kind") == "LOOPBACK_HTTP" and row.get("label") == "RELEASE_STAND_IN_NANSEN_TRANSPORT"
            and row.get("request_release") == RELEASE_ID and row.get("report_release") == RELEASE_ID,
            f"{key} Nansen: saved 600 s original deadline; reservation before the one attempt":
            row.get("deadline_seconds") == 600 and kinds.count("ATTEMPT_STARTED") == 1 and "BUDGET_RESERVED" in kinds
            and kinds.index("BUDGET_RESERVED") < kinds.index("ATTEMPT_STARTED"),
            f"{key} Nansen: 2 requests and 6 credits settled KNOWN from 2 kept reply hashes":
            settlement.get("provider_requests", {}).get("state") == "KNOWN"
            and settlement.get("provider_requests", {}).get("measured") == 2
            and settlement.get("nansen_credits", {}).get("state") == "KNOWN" and row.get("reply_hashes") == 2
            and (row.get("budget") or {}).get("consumed", {}).get("nansen_credits") == 6
            and (row.get("budget") or {}).get("unknown_liability", {}).get("nansen_credits") == 0,
        })
    kill, late, missing = (jobs.get(faults.get(name, {}).get("job_id"), {}) for name in ("kill", "stale", "missing"))
    kill_events = events.get(faults.get("kill", {}).get("job_id"), [])
    expectations.update({
        "Nansen killed worker: outcome unknown, whole request and credit reservation kept, one attempt only":
        (kill.get("state"), kill.get("terminal_reason")) == ("UNAVAILABLE", "nansen_outcome_unknown")
        and (kill.get("budget") or {}).get("unknown_liability", {}).get("nansen_credits") == 12
        and (kill.get("budget") or {}).get("unknown_liability", {}).get("provider_requests") == 4
        and kill_events.count("ATTEMPT_STARTED") == 1 and "ATTEMPT_RECONCILED" in kill_events
        and kill.get("content_sha256") is None,
        "Nansen worker past the saved deadline: stopped before any key read or request; everything released":
        (late.get("state"), late.get("terminal_reason")) == ("DEADLINE_EXCEEDED", "deadline_exceeded_before_collection")
        and (late.get("budget") or {}).get("released") == whole and late.get("deadline_seconds") == 600
        and "ATTEMPT_STARTED" not in events.get(faults.get("stale", {}).get("job_id"), []),
        "Nansen missing key: refused before any request; everything released":
        (missing.get("state"), missing.get("terminal_reason")) == (
            "UNAVAILABLE", "operating_release_credential_unavailable")
        and (missing.get("budget") or {}).get("released") == whole
        and "ATTEMPT_STARTED" not in events.get(faults.get("missing", {}).get("job_id"), []),
        "the Nansen stand-in received exactly 2 requests per report plus the killed worker's one, all with the key":
        len(requests) == 2 * len(runs) + 1 and all(entry["authorized"] for entry in requests)
        and all(entry["operation"] in ("holders", "flows") for entry in requests),
        "no stand-in credential is saved in any Nansen row or event": not any(value in dump for value in RELEASE_SENTINELS),
    })
    return {"jobs": jobs, "events": events, "stand_in_requests": len(requests), "expectations": expectations,
            "all_checks_pass": bool(runs) and all(expectations.values())}


def _http_status(url: str, token: str, method: str = "GET", body: dict[str, Any] | None = None) -> tuple[int, Any]:
    import urllib.error
    import urllib.request

    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


# ------------------------------------------------------------------------------------------- SAVED-HISTORY-BINDING-L2
# The release journey once more with ONE bound synthetic source plus the existing Nansen stand-in: a four-bucket
# SYNTHETIC recording whose release names a frozen recorder handoff (`apps/api/tests/forward_history_stand_in.py`). The
# worker binds the saved dataset in its own transaction; adoption and replay rerun the checker on the saved records.
# Everything is SYNTHETIC and loopback; a PASS proves payload binding only.

_BOUND_PRELUDE = _RELEASE_PRELUDE + "import forward_history_stand_in as bound\n"
BOUND_PROVIDER = _BOUND_PRELUDE + """
import time
from pathlib import Path
bound.loopback_provider(Path(sys.argv[2]), port=int(sys.argv[1])).start()
while True:
    time.sleep(3600)
"""
BOUND_HOST = _BOUND_PRELUDE + """
import uvicorn
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
settings = load_settings()
runtime, _ = bound.loopback_runtime_at(settings, int(os.environ["P03_STAND_IN_PORT"]),
                                       nansen_port=int(os.environ["P03_STAND_IN_NANSEN_PORT"]))
uvicorn.run(create_app(settings, research_runtime=runtime), host="127.0.0.1", port=int(sys.argv[1]),
            log_level="warning")
"""
BOUND_WORKER = _BOUND_PRELUDE + """
import uuid
from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.core.settings import load_settings
from edge_os_api.research.investigation_jobs import InvestigationWorker
settings = load_settings()
runtime, _ = bound.loopback_runtime_at(settings, int(os.environ["P03_STAND_IN_PORT"]),
                                       nansen_port=int(os.environ["P03_STAND_IN_NANSEN_PORT"]))
worker = InvestigationWorker(make_session_factory(make_engine(settings.database_url)), settings,
                             research_runtime=runtime)
for job_id in sys.argv[1:]:
    worker.run_job(uuid.UUID(job_id))
"""
# Declares on the bound source (DESCRIPTIVE: its window is 20 minutes) and saves one history job and one Nansen report
# job under the bound release, through the public API, while no worker runs.
BOUND_DECLARE = _BOUND_PRELUDE + """
import json, uuid
import httpx
from research_flows import jobs_path
client = httpx.Client(base_url=os.environ["P03_API_URL"], timeout=60)
headers = {"Authorization": "Bearer " + os.environ["P03_BOUND_TOKEN"]}
catalog = client.get("/v1/research/history-sources", headers=headers).json()
source = next(item for item in catalog["sources"] if "release" in item)
intake_id, declaration_id, body = bound.declare(client, headers, source["release"]["history"]["limits"])
job = client.post(jobs_path(intake_id, declaration_id), headers=headers,
                  json={"operation_id": str(uuid.uuid4()), "request_key": "verifier-bound"})
listed = client.get(f"/v1/research/requests/{intake_id}/nansen-reports", headers=headers).json()
nansen = client.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=headers,
                     json={"operation_id": str(uuid.uuid4()), "request_key": "verifier-bound-nansen",
                           **listed["operating_release"]["request"]})
print(json.dumps({"url": f"/#/research/{intake_id}", "intakeId": intake_id, "declarationId": declaration_id,
                  "hypothesis": body["edge_spec"]["hypothesis"], "jobStatus": job.status_code,
                  "jobId": job.json().get("job_id"), "nansenStatus": nansen.status_code,
                  "nansenJobId": nansen.json().get("job_id"), "sourceId": source["source_id"],
                  "release": {key: catalog["operating_release"][key] for key in ("release_id", "sha256", "kind")},
                  "handoffSha256": (source["release"]["history"].get("payload_binding") or {}).get("handoff_sha256"),
                  "providerRequests": source["release"]["history"]["limits"]["provider_requests"]}))
"""
# After the worker: market adoption on a NEW revision, publication and a replay on the bound dataset; then another
# owner's reads. Prints the ids and the lineage each consumer saved.
BOUND_CONSUME = _BOUND_PRELUDE + """
import json
import httpx
from flows import compiled_thesis, publish
from research_flows import adoption_body, history_replay_body
client = httpx.Client(base_url=os.environ["P03_API_URL"], timeout=60)
headers = {"Authorization": "Bearer " + os.environ["P03_BOUND_TOKEN"]}
other = {"Authorization": "Bearer " + os.environ["P03_BOUND_OTHER_TOKEN"]}
run = json.loads(os.environ["P03_BOUND_RUN"])
job = client.get(f"/v1/research/investigation-jobs/{run['jobId']}", headers=headers).json()
dataset_id = job["dataset"]["dataset_id"]
listed = next(item for item in client.get("/v1/research/history-datasets", headers=headers).json()["datasets"]
              if item["dataset_id"] == dataset_id)
bundle = compiled_thesis(client, headers)
first, _ = publish(client, headers, bundle)
parent = first.json()["revision_id"]
adopted = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions", headers=headers,
                      json=adoption_body(bundle, dataset_id, parent=parent, quote_unit="QUOTE:0x" + "d2" * 20,
                                         evaluation_id=listed["declared_rules"][0]["evaluation_id"]))
second, _ = publish(client, headers, adopted.json()["bundle"], parent=parent)
revision = second.json().get("revision_id")
replay = client.post("/v1/spot-replays", headers=headers, json=history_replay_body(
    bundle["head"]["strategy_id"], revision, dataset_id, start=bound.WINDOW_START, end=bound.WINDOW_END))
replay_id = replay.json().get("replay_id")
routes = [f"/v1/research/history-datasets/{dataset_id}", f"/v1/research/investigation-jobs/{run['jobId']}",
          f"/v1/spot-replays/{replay_id}", f"/v1/research/investigation-jobs/{run['nansenJobId']}"]
print(json.dumps({"datasetId": dataset_id, "jobState": job["state"], "binding": listed["payload_binding"],
                  "adoptionStatus": adopted.status_code, "adoptionBinding": adopted.json().get("adoption", {}).get(
                      "payload_binding"), "publishStatus": second.status_code, "releaseRevision": revision,
                  "strategyUrl": f"/#/research/{bundle['intake']['record_id']}", "replayStatus": replay.status_code,
                  "replayId": replay_id, "otherOwner": {route: client.get(route, headers=other).status_code
                                                        for route in routes}}))
"""


def _bound_env(env: dict[str, str], port: int, nansen_port: int) -> dict[str, str]:
    return {**_release_env(env, port, nansen_port=nansen_port), "P03_RELEASE_ID": "stand-in-bound/1"}


def _driver(script: str, run_env: dict[str, str], logs: Path, name: str) -> dict[str, Any]:
    done = subprocess.run([harness.api_python(), "-c", script], cwd=harness.API_DIR, env=run_env, capture_output=True,
                          text=True, timeout=300)
    (logs / f"{name}.log").write_text(done.stdout + done.stderr)
    return json.loads(done.stdout.strip().splitlines()[-1]) if done.returncode == 0 and done.stdout.strip() else {}


def _bound_worker(run_env: dict[str, str], logs: Path, name: str, job_ids: list[str]) -> int:
    with open(logs / f"{name}.log", "ab") as handle:
        return subprocess.run([harness.api_python(), "-c", BOUND_WORKER, *job_ids], cwd=harness.API_DIR,
                              env=run_env, stdout=handle, stderr=handle, timeout=300).returncode


def inspect_bound(pg: harness.Postgres, run: dict[str, Any], requests: list[dict[str, Any]],
                  nansen_requests: int) -> dict[str, Any]:
    """Direct SQL over the bound job, dataset, binding event, Nansen report and replay, compared with the bound
    stand-in provider's own request log and the identities the API listed before any request."""
    job_id, nansen_job, replay_id = run.get("jobId"), run.get("nansenJobId"), run.get("replayId")
    dataset = (_rows(pg, (
        "select d.dataset_id::text, d.owner_id::text, d.attempt_id::text, d.content_sha256, "
        "d.content->'raw_evidence'->>'sha256' raw_sha256, d.content->'operating_release' release, "
        "d.content->'payload_binding_requirement' requirement, d.content->'verdict'->>'overall' verdict, "
        "d.content->'transport'->'request_sha256' request_hashes, j.state, j.budget "
        "from research_local.investigation_jobs j join research_local.history_datasets d using (dataset_id) "
        f"where j.job_id = '{job_id}'")) or [{}])[0] if job_id else {}
    events = _rows(pg, ("select owner_id::text, attempt_id::text, content from research_local.investigation_events "
                        f"where job_id = '{job_id}' and kind = 'HISTORY_PAYLOAD_BOUND'")) if job_id else []
    nansen = (_rows(pg, ("select r.content->>'evidence_class' evidence, r.content_sha256, "
                         "r.content->'operating_release'->>'release_id' release from research_local.nansen_reports r "
                         f"where r.job_id = '{nansen_job}'")) or [{}])[0] if nansen_job else {}
    replay = (_rows(pg, ("select owner_id::text, content_sha256, content->'inputs'->'history_input'->>'dataset_id' "
                         "dataset, content->'inputs'->'history_input'->'payload_binding' binding "
                         f"from spot_replay_runs where replay_id::text = '{replay_id}'")) or [{}])[0] if replay_id else {}
    dump = pg.psql("select concat_ws('|', (select string_agg(t::text, '') from research_local.history_datasets t), "
                   "(select string_agg(t::text, '') from research_local.investigation_events t), "
                   "(select string_agg(t::text, '') from spot_replay_runs t))")
    event = events[0] if len(events) == 1 else {}
    content = event.get("content") or {}
    report = content.get("report") or {}
    calls = run.get("providerRequests")
    expectations = {
        "bound: one HISTORY_PAYLOAD_BOUND event, PASS, for the owner, attempt and dataset of the saved row":
        len(events) == 1 and content.get("result") == "PASS" and content.get("dataset_id") == dataset.get("dataset_id")
        and event.get("owner_id") == dataset.get("owner_id") and event.get("attempt_id") == dataset.get("attempt_id"),
        "bound: report content and raw hashes are the saved row's; handoff and release hashes are the listed ones":
        report.get("content_sha256") == dataset.get("content_sha256") and report.get("raw_sha256")
        == dataset.get("raw_sha256") and report.get("handoff_sha256") == content.get("handoff_sha256")
        == (dataset.get("requirement") or {}).get("handoff_sha256") == run.get("handoffSha256") is not None
        and report.get("release") == dataset.get("release") == run.get("release"),
        "bound: the P07 verdict stays QUALIFIED and the job reported with the measured calls settled":
        dataset.get("verdict") == "QUALIFIED" and dataset.get("state") == "REPORTED"
        and (dataset.get("budget") or {}).get("consumed", {}).get("provider_requests") == calls,
        "bound: the stand-in received exactly the saved requests, all with the stand-in credential":
        len(requests) == calls and all(entry["authorized"] for entry in requests)
        and [entry["body_sha256"] for entry in requests] == (dataset.get("request_hashes") or []),
        "bound: the Nansen report under the bound release, 2 Nansen requests":
        nansen.get("evidence") == "RELEASE_STAND_IN_RESPONSE" and nansen.get("release") == run.get("release", {}).get(
            "release_id") and nansen_requests == 2,
        "bound: adoption and replay saved the binding report and handoff identity":
        (run.get("adoptionStatus"), run.get("publishStatus"), run.get("replayStatus")) == (201, 201, 201)
        and (run.get("adoptionBinding") or {}).get("report_sha256") == content.get("report_sha256")
        and (replay.get("binding") or {}).get("report_sha256") == content.get("report_sha256")
        and (replay.get("binding") or {}).get("handoff_sha256") == run.get("handoffSha256")
        and replay.get("dataset") == dataset.get("dataset_id") and replay.get("owner_id") == dataset.get("owner_id"),
        "bound: another owner receives 404 for the dataset, job, replay and Nansen job":
        bool(run.get("otherOwner")) and set((run.get("otherOwner") or {}).values()) == {404},
        "bound: no stand-in credential in any research or replay row": not any(value in dump for value in RELEASE_SENTINELS),
    }
    return {"dataset": dataset, "event": {key: value for key, value in content.items() if key != "handoff_json"},
            "nansen": nansen, "replay": replay, "expectations": expectations,
            "all_checks_pass": all(expectations.values())}


def run_bound_release_phase(rec: Any, pg: harness.Postgres, env: dict[str, str], api_port: int, api_url: str,
                            evidence: Path, ui_env: dict[str, str], run_playwright: Callable[..., int],
                            processes: list[Any], nansen_port: int, nansen_log: Path, logs: Path) -> bool:
    """The bound journey. The caller stopped the release API; every process started here goes into `processes` at
    once, and the bound API is stopped before return."""
    ok = True
    work = evidence / "research-release"
    log = work / "stand-in-bound-requests.jsonl"
    port = harness.free_port()
    bound_env = _bound_env(env, port, nansen_port)
    tokens = json.loads(ui_env["P03_RELEASE_FAULT_TOKENS"])
    driver_env = {**bound_env, "P03_API_URL": api_url, "P03_BOUND_TOKEN": tokens["missing"],
                  "P03_BOUND_OTHER_TOKEN": tokens["stale"]}
    host = None
    try:
        provider = _spawn(bound_env, "research-bound-stand-in", BOUND_PROVIDER, [str(port), str(log)], logs)
        processes.append(provider)
        harness.wait_http(f"http://127.0.0.1:{port}/ready")
        host = _spawn(bound_env, "api-research-bound", BOUND_HOST, [str(api_port)], logs)
        processes.append(host)
        harness.wait_http(f"{api_url}/readyz")
        nansen_before = len(stand_in_requests(nansen_log))
        run = _driver(BOUND_DECLARE, driver_env, logs, "research-bound-declare")
        ok &= rec.step("SAVED-HISTORY-BINDING: the bound release lists its SYNTHETIC handoff identity; one history job "
                       "and one Nansen report saved with no request sent yet",
                       (run.get("jobStatus"), run.get("nansenStatus")) == (201, 201) and bool(run.get("handoffSha256"))
                       and run.get("release", {}).get("release_id") == "stand-in-bound/1"
                       and stand_in_requests(log) == [] and len(stand_in_requests(nansen_log)) == nansen_before,
                       {key: run.get(key) for key in ("jobStatus", "nansenStatus", "release", "handoffSha256")})
        worker = _bound_worker(bound_env, logs, "research-bound-worker-1", [run["jobId"], run["nansenJobId"]])
        consumed = _driver(BOUND_CONSUME, {**driver_env, "P03_BOUND_RUN": json.dumps(run)}, logs,
                           "research-bound-consume")
        run.update(consumed)
        results_path = evidence / "ui" / "research-results.json"
        results = json.loads(results_path.read_text()) if results_path.exists() else {}
        results["bound"] = run
        results_path.write_text(json.dumps(results, indent=2))
        ok &= rec.step("SAVED-HISTORY-BINDING: one worker pass binds the saved dataset (PASS); adoption, publication "
                       "and replay carry the binding; another owner reads nothing",
                       worker == 0 and run.get("jobState") == "REPORTED"
                       and (run.get("binding") or {}).get("status") == "PASS"
                       and (run.get("adoptionStatus"), run.get("replayStatus")) == (201, 201),
                       {"worker": worker, **{key: run.get(key) for key in ("jobState", "binding", "adoptionStatus",
                                                                            "replayStatus", "otherOwner")}})
        requests = stand_in_requests(log)
        nansen_sent = len(stand_in_requests(nansen_log)) - nansen_before
        inspection = inspect_bound(pg, run, requests, nansen_sent)
        rec.write("research-bound-inspection.json", inspection)
        ok &= rec.step("SAVED-HISTORY-BINDING: SQL matches owner, dataset, raw/content/handoff/report/release hashes, "
                       "one event, and the stand-in's own request log", inspection["all_checks_pass"],
                       inspection["expectations"])
        host.stop()
        host = _spawn(bound_env, "api-research-bound-restarted", BOUND_HOST, [str(api_port)], logs)
        processes.append(host)
        harness.wait_http(f"{api_url}/readyz")
        again = _bound_worker(bound_env, logs, "research-bound-worker-restarted", [run["jobId"], run["nansenJobId"]])
        code = run_playwright(["research-release-restart.spec.mjs"], {**ui_env, "P03_BOUND_PHASE": "1"},
                              evidence / "ui-research-bound-restart.log")
        after = inspect_bound(pg, run, stand_in_requests(log), len(stand_in_requests(nansen_log)) - nansen_before)
        rec.write("research-bound-inspection-after-restart.json", after)
        ok &= rec.step("SAVED-HISTORY-BINDING: after an API and worker restart the bound job, dataset, binding and replay "
                       "reopen unchanged in a new context (desktop and 390px); no request repeated; owner B denied",
                       again == 0 and code == 0 and after == inspection
                       and len(stand_in_requests(log)) == len(requests),
                       {"worker_exit": again, "spec_exit": code, "stand_in_requests": len(stand_in_requests(log))})
    finally:
        if host is not None:
            try:
                host.stop()
            except Exception as error:  # noqa: BLE001
                ok &= rec.step("SAVED-HISTORY-BINDING: stop the bound API", False, f"{type(error).__name__}: {error}")
    return bool(ok)


def run_release_phase(rec: Any, pg: harness.Postgres, env: dict[str, str], api_port: int, api_url: str,
                      evidence: Path, ui_env: dict[str, str], run_playwright: Callable[..., int],
                      current_api: Any, processes: list[Any]) -> tuple[bool, Any]:
    """Returns whether every step passed and the standard API it started last. It stops `current_api`; every process
    it starts goes into `processes` at once, so the caller's cleanup stops it even when a step raises."""
    ok = True
    work, logs = evidence / "research-release", evidence / "logs"
    work.mkdir(parents=True, exist_ok=True)
    log = work / "stand-in-requests.jsonl"
    nansen_log = work / "stand-in-nansen-requests.jsonl"
    port, nansen_port = harness.free_port(), harness.free_port()
    release_env = _release_env(env, port, nansen_port=nansen_port)
    standard = current_api
    host = None
    try:
        provider = _spawn(release_env, "research-release-stand-in", STAND_IN_PROVIDER, [str(port), str(log)], logs)
        processes.append(provider)
        harness.wait_http(f"http://127.0.0.1:{port}/ready")
        nansen_provider = _spawn(release_env, "research-release-stand-in-nansen", STAND_IN_NANSEN,
                                 [str(nansen_port), str(nansen_log)], logs)
        processes.append(nansen_provider)
        harness.wait_http(f"http://127.0.0.1:{nansen_port}/ready")
        current_api.stop()
        host = _spawn(release_env, "api-research-release", RELEASE_HOST, [str(api_port)], logs)
        processes.append(host)
        harness.wait_http(f"{api_url}/readyz")
        fault_tokens = json.loads(ui_env["P03_RELEASE_FAULT_TOKENS"])
        token = fault_tokens["kill"]
        status, catalog = _http_status(f"{api_url}/v1/research/history-sources", token)
        ok &= rec.step("RESEARCH-RUNTIME: the API composes the stand-in release (listed with its fixed limits; no "
                       "request yet)", status == 200 and (catalog.get("operating_release") or {}).get("release_id")
                       == RELEASE_ID and stand_in_requests(log) == [], catalog.get("operating_release"))
        nansen_view = (catalog.get("operating_release") or {}).get("nansen") or {}
        ok &= rec.step("R58-MOUNT: the same release has a Nansen part on the loopback host with its fixed request and "
                       "client bounds; stand-in class and loopback transport; no Nansen request yet",
                       nansen_view.get("endpoint_host") == "127.0.0.1" and nansen_view.get("limits", {}).get(
                           "max_credits") == "12" and bool(nansen_view.get("client_bounds"))
                       and catalog["operating_release"].get("evidence_class") == "RELEASE_STAND_IN_RESPONSE"
                       and stand_in_requests(nansen_log) == [], nansen_view)
        code = run_playwright(["research-release-journey.spec.mjs"], ui_env, evidence / "ui-research-release-journey.log")
        ok &= rec.step("RESEARCH-RUNTIME: declare on the release source with its fixed bounds and start one job, no "
                       "worker running (desktop and 390px, one owner each)", code == 0, {"exit": code})
        driver = subprocess.run([harness.api_python(), "-c", RELEASE_DRIVER, "kill,stale,missing"],
                                cwd=harness.API_DIR, env={**release_env, "P03_API_URL": api_url,
                                                          "P03_RELEASE_FAULT_TOKENS": ui_env["P03_RELEASE_FAULT_TOKENS"]},
                                capture_output=True, text=True, timeout=300)
        faults = json.loads(driver.stdout.strip().splitlines()[-1]) if driver.returncode == 0 else {}
        rec.write("research-release-fault-jobs.json", faults)
        ok &= rec.step("RESEARCH-RUNTIME: fault-case declarations and jobs saved through the API",
                       sorted(faults) == ["kill", "missing", "stale"]
                       and all(case["status"] == 201 for case in faults.values()), {"exit": driver.returncode})
        before = len(stand_in_requests(log))
        killed = _release_worker(release_env, logs, "research-release-worker-killed", "kill", [faults["kill"]["job_id"]])
        ok &= rec.step("RESEARCH-RUNTIME: the worker is killed right after the first stand-in reply (exit 9)",
                       killed == 9 and len(stand_in_requests(log)) == before + 1,
                       {"exit": killed, "stand_in_requests": len(stand_in_requests(log)) - before})
        changed = _release_worker(_release_env(env, port, CHANGED_RELEASE_ID, nansen_port), logs, "research-release-worker-changed",
                                  "pass", [faults["stale"]["job_id"]])
        missing = _release_worker(release_env, logs, "research-release-worker-missing", "missing",
                                  [faults["missing"]["job_id"]])
        ok &= rec.step("RESEARCH-RUNTIME: a changed release and a missing credential end their jobs before any request",
                       (changed, missing) == (0, 0) and len(stand_in_requests(log)) == before + 1,
                       {"exits": [changed, missing]})
        nansen_driver = subprocess.run([harness.api_python(), "-c", NANSEN_DRIVER, ",".join(NANSEN_FAULTS)],
                                       cwd=harness.API_DIR, env={**release_env, "P03_API_URL": api_url,
                                                                 "P03_RELEASE_FAULT_TOKENS": ui_env["P03_RELEASE_FAULT_TOKENS"]},
                                       capture_output=True, text=True, timeout=300)
        nansen_faults = json.loads(nansen_driver.stdout.strip().splitlines()[-1]) if nansen_driver.returncode == 0 else {}
        rec.write("research-release-nansen-fault-jobs.json", nansen_faults)
        ok &= rec.step("R58-MOUNT: release Nansen fault reports saved through the API with the release's fixed request",
                       sorted(nansen_faults) == sorted(NANSEN_FAULTS)
                       and all(case["status"] == 201 and case["release"] == RELEASE_ID for case in nansen_faults.values()),
                       {"exit": nansen_driver.returncode})
        nansen_before = len(stand_in_requests(nansen_log))
        nansen_exits = {name: _release_worker(release_env, logs, f"research-release-worker-nansen-{name}", mode,
                                              [nansen_faults[name]["job_id"]]) for name, mode in NANSEN_FAULTS.items()}
        ok &= rec.step("R58-MOUNT: a Nansen worker killed after the first stand-in reply (exit 9); a worker past the "
                       "saved deadline and a missing Nansen key end their jobs before any request",
                       nansen_exits == {"kill": 9, "stale": 0, "missing": 0}
                       and len(stand_in_requests(nansen_log)) == nansen_before + 1,
                       {"exits": nansen_exits, "nansen_requests": len(stand_in_requests(nansen_log)) - nansen_before})
        results_path = evidence / "ui" / "research-results.json"
        journey = json.loads(results_path.read_text()) if results_path.exists() else {}
        phase_jobs = [run["jobId"] for key, run in journey.items() if key.startswith("release-")] + [
            faults["kill"]["job_id"]] + [run["nansenJobId"] for key, run in journey.items()
                                         if key.startswith("release-") and run.get("nansenJobId")] + [
            nansen_faults["kill"]["job_id"]]
        worker = _release_worker(release_env, logs, "research-release-worker-1", "pass", phase_jobs)
        ok &= rec.step("RESEARCH-RUNTIME: bounded release worker pass over this phase's jobs (stand-in only; the "
                       "killed history and Nansen jobs reconcile without a call)", worker == 0 and len(phase_jobs) == 6
                       and len(stand_in_requests(nansen_log)) == nansen_before + 1 + 4,
                       {"exit": worker, "jobs": len(phase_jobs), "nansen_requests": len(stand_in_requests(nansen_log))})
        code = run_playwright(["research-release-report.spec.mjs"], ui_env, evidence / "ui-research-release-report.log")
        ok &= rec.step("RESEARCH-RUNTIME: report and dataset with stand-in labels and hashes, market adoption, "
                       "publication and a labelled replay with simulated fills; owner B denied (desktop and 390px)",
                       code == 0, {"exit": code})
        results = json.loads(results_path.read_text()) if results_path.exists() else {}
        requests = stand_in_requests(log)
        inspection = inspect_release(pg, results, faults, requests)
        rec.write("research-release-inspection.json", inspection)
        ok &= rec.step("RESEARCH-RUNTIME: SQL matches the screens and the stand-in provider's own request log",
                       inspection["all_checks_pass"], inspection["expectations"])
        nansen_requests = stand_in_requests(nansen_log)
        nansen_inspection = inspect_release_nansen(pg, results, nansen_faults, nansen_requests)
        rec.write("research-release-nansen-inspection.json", nansen_inspection)
        ok &= rec.step("R58-MOUNT: Nansen SQL (saved deadline, state, stop reason, request and credit settlement, "
                       "labels, original attempt) matches the screens and the Nansen stand-in's own request log",
                       nansen_inspection["all_checks_pass"], nansen_inspection["expectations"])
        host.stop()
        host = _spawn(release_env, "api-research-release-restarted", RELEASE_HOST, [str(api_port)], logs)
        processes.append(host)
        harness.wait_http(f"{api_url}/readyz")
        again = _release_worker(release_env, logs, "research-release-worker-restarted", "pass",
                                [*phase_jobs, faults["stale"]["job_id"], faults["missing"]["job_id"],
                                 nansen_faults["stale"]["job_id"], nansen_faults["missing"]["job_id"]])
        code = run_playwright(["research-release-restart.spec.mjs"], ui_env, evidence / "ui-research-release-restart.log")
        after = inspect_release(pg, results, faults, stand_in_requests(log))
        rec.write("research-release-inspection-after-restart.json", after)
        nansen_after = inspect_release_nansen(pg, results, nansen_faults, stand_in_requests(nansen_log))
        rec.write("research-release-nansen-inspection-after-restart.json", nansen_after)
        ok &= rec.step("RESEARCH-RUNTIME: after an API and worker restart the report, dataset and replay reopen "
                       "unchanged in a new context; no request was repeated; owner B denied",
                       again == 0 and code == 0 and after["jobs"] == inspection["jobs"]
                       and after["replays"] == inspection["replays"] and len(stand_in_requests(log)) == len(requests),
                       {"worker_exit": again, "spec_exit": code, "stand_in_requests": len(stand_in_requests(log))})
        ok &= rec.step("R58-MOUNT: after the restart every release Nansen job, report and settlement is unchanged and "
                       "reopening sent no Nansen request",
                       again == 0 and code == 0 and nansen_after["jobs"] == nansen_inspection["jobs"]
                       and len(stand_in_requests(nansen_log)) == len(nansen_requests),
                       {"nansen_requests": len(stand_in_requests(nansen_log))})
        host.stop()
        ok &= run_bound_release_phase(rec, pg, env, api_port, api_url, evidence, ui_env, run_playwright, processes,
                                      nansen_port, nansen_log, logs)
        standard = harness.start_api(env, api_port, logs, name="api-after-research-release")
        processes.append(standard)
        harness.wait_http(f"{api_url}/readyz")
        run = next(iter(value for key, value in results.items() if key.startswith("release-")), {})
        status_list, plain = _http_status(f"{api_url}/v1/research/history-sources", token)
        refused, body = _http_status(
            f"{api_url}/v1/research/requests/{faults['stale']['intake_id']}/history-investigations/"
            f"{faults['stale']['declaration_id']}/jobs", fault_tokens["stale"], "POST",
            {"operation_id": "3f1c2a4e-0b7d-4c5e-9a8b-1d2e3f4a5b6c", "request_key": "verifier-no-release"})
        ok &= rec.step("RESEARCH-RUNTIME: the standard API composes no release: the source is not listed and a saved "
                       "release declaration cannot start (409 operating_release_unavailable)",
                       status_list == 200 and not any("release" in item for item in plain.get("sources", []))
                       and plain.get("operating_release") is None
                       and (refused, body.get("code")) == (409, "operating_release_unavailable")
                       and len(stand_in_requests(log)) == len(requests), {"status": refused, "code": body.get("code"),
                                                                          "run": bool(run)})
        texts = [*logs.glob("*.log"), *(evidence / "ui").glob("*.json"), *evidence.glob("ui-*.log"), log, nansen_log]
        leaked = [p.name for p in texts if p.exists() and any(value in p.read_text(errors="ignore")
                                                                for value in RELEASE_SENTINELS)]
        ok &= rec.step("RESEARCH-RUNTIME: no stand-in credential appears in logs, browser results or the request log",
                       not leaked, leaked)
    finally:
        if host is not None:
            try:
                host.stop()
            except Exception as error:  # noqa: BLE001
                ok &= rec.step("RESEARCH-RUNTIME: stop the release API", False, f"{type(error).__name__}: {error}")
        if standard is current_api:  # a step raised before the standard API was restarted
            standard = harness.start_api(env, api_port, logs, name="api-after-research-release")
            processes.append(standard)
            harness.wait_http(f"{api_url}/readyz")
    return bool(ok), standard
