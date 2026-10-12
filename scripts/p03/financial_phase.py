"""#58 connected financial phase of the mapped verifier.

Runs inside `verify_run.py` on the same isolated instance. The API already runs with
`EDGE_OS_EXECUTION_MODE=fixture` and a run-owned `EDGE_OS_FIXTURE_EFFECTS_PATH`. This module starts the bounded
worker, drives `financial-journey.spec.mjs`, compares saved rows with direct SQL and the independent fixture
effect record, and after the shared API restart restarts the worker and reopens the journey. Fixture only: it
proves no wallet, deposit, quote, transaction, receipt or removal at any provider.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

import harness

EFFECTS_NAME = "fixture-effects.jsonl"


def configure(env: dict[str, str], evidence: Path) -> Path:
    """Fixture execution for this isolated run only. Production refuses both settings."""
    effects = evidence / EFFECTS_NAME
    env["EDGE_OS_EXECUTION_MODE"] = "fixture"
    env["EDGE_OS_FIXTURE_EFFECTS_PATH"] = str(effects)
    return effects


def start_worker(env: dict[str, str], log_dir: Path, name: str = "worker") -> harness.Process:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    handle = open(log_path, "ab")
    popen = subprocess.Popen([harness.api_python(), "-m", "edge_os_api.execution.worker", "--interval", "1"],
                             cwd=harness.API_DIR, env=env, stdout=handle, stderr=handle, start_new_session=True)
    return harness.Process(name, popen, log_path, handle)


def _rows(pg: harness.Postgres, sql: str) -> list[dict[str, Any]]:
    return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))


def _effects(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []


def inspect(pg: harness.Postgres, effects_path: Path, results: dict[str, Any], owner_b_id: str | None) -> dict[str, Any]:
    """Direct SQL over the financial schemas plus the independent effect record."""
    checks: dict[str, Any] = {}
    effects = _effects(effects_path)
    agents = {key: value["agentId"] for key, value in results.items()}
    for key, agent in agents.items():
        jobs = _rows(pg, "select state, outcome, reason, action_id, runs from execution_local.execution_evaluation_jobs "
                         f"where agent_id = '{agent}' order by created_at")
        intents = _rows(pg, "select action_id, operation, admission_status from execution_local.execution_intents "
                            f"where agent_id = '{agent}' order by created_at")
        attempts = _rows(pg, "select action_id, state, outcome, content->'original_references'->>'transaction_hash' tx "
                             f"from execution_local.execution_submission_attempts where agent_id = '{agent}'")
        receipts = _rows(pg, "select r.action_id, r.outcome from admission_local.admission_receipts r "
                             f"where r.agent_id = '{agent}' order by r.created_at")
        removals = _rows(pg, "select state from revocation_local.removal_states "
                             f"where agent_id = '{agent}'")
        stops = _rows(pg, f"select mode from stops_local.scoped_stops where agent_id = '{agent}'")
        credits = _rows(pg, "select asset_id, actual_raw::text raw from funding_local.funding_credits "
                            f"where agent_id = '{agent}' order by asset_id")
        consents = _rows(pg, "select a.status from consent_local.consent_adoptions a join consent_local.consent_reviews r "
                             f"using (review_id) where r.agent_id = '{agent}'")
        actions = {intent["action_id"] for intent in intents}
        checks[key] = {
            "jobs": jobs, "intents": intents, "attempts": attempts, "receipts": receipts, "removals": removals,
            "stops": stops, "credits": credits, "consents": consents,
            "effects_per_action": {action: sum(1 for e in effects if e["action_id"] == action) for action in actions},
            "attempt_tx_hashes": sorted({a["tx"] for a in attempts if a["tx"]}),
        }
    expectations = {}
    for key, value in checks.items():
        effects_ok = all(count <= 1 for count in value["effects_per_action"].values())
        expectations[f"{key}: at most one provider effect per action"] = effects_ok
        expectations[f"{key}: consent rows stay INACTIVE"] = all(c["status"] == "INACTIVE" for c in value["consents"])
        expectations[f"{key}: no invented transaction hash"] = value["attempt_tx_hashes"] == []
        if key.startswith("main-"):
            expectations[f"{key}: one confirmed entry with one receipt"] = (
                [i["admission_status"] for i in value["intents"]] == ["ADMITTED"]
                and [r["outcome"] for r in value["receipts"]] == ["CONFIRMED"]
                and list(value["effects_per_action"].values()) == [1])
            expectations[f"{key}: removal confirmed"] = [r["state"] for r in value["removals"]] == ["CONFIRMED"]
        if key.startswith("lost-ack-"):
            expectations[f"{key}: unknown then reconciled original"] = (
                [r["outcome"] for r in value["receipts"]] == ["SUBMISSION_UNKNOWN", "CONFIRMED"]
                and list(value["effects_per_action"].values()) == [1])
        if key.startswith("removed-"):
            expectations[f"{key}: requested removal denied before any effect"] = (
                [j["outcome"] for j in value["jobs"]] == ["ADMISSION_DENIED"]
                and [j["reason"] for j in value["jobs"]] == ["REMOVAL_REQUESTED"]
                and sum(value["effects_per_action"].values()) == 0)
        if key.startswith("stop-"):
            expectations[f"{key}: stop denied before any effect"] = (
                [s["mode"] for s in value["stops"]] == ["HALT_ALL_SWAPS"]
                and [j["outcome"] for j in value["jobs"]] == ["ADMISSION_DENIED"]
                and sum(value["effects_per_action"].values()) == 0)
    if owner_b_id:
        foreign = _rows(pg, "select count(*) c from execution_local.execution_evaluation_jobs "
                            f"where owner_id = '{owner_b_id}'")[0]["c"]
        expectations["owner B created no financial jobs"] = foreign == 0
    expectations["every effect belongs to a saved action"] = all(
        any(e["action_id"] in value["effects_per_action"] for value in checks.values()) for e in effects)
    return {"checks": checks, "expectations": expectations, "effects_lines": len(effects),
            "all_checks_pass": all(expectations.values())}


def _http(method: str, url: str, token: str, body: object = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - loopback only
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def browser_completion(pg: harness.Postgres, ui_env: dict[str, str]) -> dict[str, Any]:
    """IC04 through the mounted API: a browser-reported wallet id binds only after the fixture lookup names the
    verified owner; a foreign id stays UNKNOWN. No browser creation runs (that needs a real provider)."""
    api, token_a, token_b = ui_env["P03_API_URL"], ui_env["P03_TOKEN_A"], ui_env["P03_TOKEN_B"]
    owner_a = _http("GET", f"{api}/v1/me", token_a)[1]["user_id"]
    owner_b = _http("GET", f"{api}/v1/me", token_b)[1]["user_id"]
    revision = _rows(pg, "select strategy_id, revision_id::text from strategy_revisions "
                         f"where owner_id = '{owner_a}' order by created_at desc limit 1")[0]
    suffix = uuid.uuid4().hex[:8]
    agents = {"bound": f"fin-ic04-{suffix}", "foreign": f"fin-ic04f-{suffix}"}
    for agent in agents.values():
        status, _ = _http("POST", f"{api}/v1/wallet-setup/agents/{agent}/prepare", token_a, {
            "network_id": 10143, "strategy_id": revision["strategy_id"],
            "strategy_revision_id": revision["revision_id"], "request_key": f"key-{agent}"})
        assert status == 200, status
    bound = _http("POST", f"{api}/v1/wallet-setup/agents/{agents['bound']}/complete", token_a,
                  {"wallet_id": f"fixture:{owner_a}:{agents['bound']}"})[1]
    foreign = _http("POST", f"{api}/v1/wallet-setup/agents/{agents['foreign']}/complete", token_a,
                    {"wallet_id": f"fixture:{owner_b}:{agents['foreign']}"})[1]
    other_owner = _http("POST", f"{api}/v1/wallet-setup/agents/{agents['bound']}/complete", token_b,
                        {"wallet_id": f"fixture:{owner_b}:{agents['bound']}"})[0]
    events = _rows(pg, "select e.event_type, e.content->>'trusted' trusted from wallet_setup_events e join wallet_setups s "
                       f"using (setup_id) where s.agent_id = '{agents['bound']}' order by e.sequence")
    return {"agents": agents, "bound": bound, "foreign": foreign, "owner_b_status": other_owner, "events": events,
            "checks": {
                "browser id binds after lookup": bound.get("state") == "CONFIRMED"
                and bound.get("wallet_id") == f"fixture:{owner_a}:{agents['bound']}",
                "foreign id stays unknown and unbound": foreign.get("state") == "UNKNOWN"
                and foreign.get("wallet_id") is None,
                "owner B cannot complete owner A's setup": other_owner == 404,
                "untrusted claim saved before binding": [e["event_type"] for e in events]
                == ["PREPARED", "DISPATCH_INTENT", "RESULT_RETURNED", "WALLET_BOUND"] and events[2]["trusted"] == "false",
            }}


def browser_completion_after_restart(ui_env: dict[str, str], before: dict[str, Any]) -> bool:
    api, token_a = ui_env["P03_API_URL"], ui_env["P03_TOKEN_A"]
    status, setup = _http("GET", f"{api}/v1/wallet-setup/agents/{before['agents']['bound']}", token_a)
    return status == 200 and setup.get("state") == "CONFIRMED" and setup.get("wallet_id") == before["bound"]["wallet_id"]


def drive(rec: Any, pg: harness.Postgres, env: dict[str, str], evidence: Path, ui_env: dict[str, str],
          run_playwright: Callable[..., int], processes: list[Any], owner_b_id: str | None) -> tuple[bool, dict[str, Any]]:
    effects = Path(env["EDGE_OS_FIXTURE_EFFECTS_PATH"])
    worker = start_worker(env, evidence / "logs")
    processes.append(worker)
    ok = rec.step("bounded worker started (fixture execution mode)", worker.popen.poll() is None)
    code = run_playwright(["financial-journey.spec.mjs"], ui_env, evidence / "ui-financial.log")
    ok &= rec.step("financial journey drive: wallet, funding, exact terms, action, receipt, recovery, stop, removal "
                   "(desktop and 390px)", code == 0, {"exit": code})
    results_path = evidence / "ui" / "financial-results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    inspection = inspect(pg, effects, results, owner_b_id)
    rec.write("financial-inspection.json", inspection)
    ok &= rec.step("financial rows and the independent effect record agree (direct SQL)",
                   bool(results) and inspection["all_checks_pass"], inspection["expectations"])
    completion = browser_completion(pg, ui_env)
    rec.write("ic04-browser-completion.json", completion)
    ok &= rec.step("IC04 browser completion binds only after lookup; foreign and other-owner results refused (API, SQL)",
                   all(completion["checks"].values()), completion["checks"])
    inspection["ic04"] = completion
    worker.stop()
    return ok, inspection


def after_restart(rec: Any, pg: harness.Postgres, env: dict[str, str], evidence: Path, ui_env: dict[str, str],
                  run_playwright: Callable[..., int], processes: list[Any], before: dict[str, Any],
                  owner_b_id: str | None) -> bool:
    worker = start_worker(env, evidence / "logs", name="worker-restarted")
    processes.append(worker)
    ok = rec.step("bounded worker restarted on the same database", worker.popen.poll() is None)
    code = run_playwright(["financial-reopen.spec.mjs"], ui_env, evidence / "ui-financial-reopen.log")
    ok &= rec.step("financial journey reopens unchanged after API and worker restart (new browser context)",
                   code == 0, {"exit": code})
    results = json.loads((evidence / "ui" / "financial-results.json").read_text())
    after = inspect(pg, Path(env["EDGE_OS_FIXTURE_EFFECTS_PATH"]), results, owner_b_id)
    rec.write("financial-inspection-after-restart.json", after)
    ok &= rec.step("financial rows and effects unchanged by the restart (no second economic action)",
                   after["checks"] == before["checks"] and after["effects_lines"] == before["effects_lines"],
                   {"effects_before": before["effects_lines"], "effects_after": after["effects_lines"]})
    ok &= rec.step("IC04 browser-completed wallet reopens bound after the restart",
                   "ic04" in before and browser_completion_after_restart(ui_env, before["ic04"]))
    worker.stop()
    return ok
