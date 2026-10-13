"""#58 P27 LOCAL recurring phase of the mapped verifier.

Runs inside `verify_run.py` on the same isolated instance, after the research phase. Two owners (one per browser
width) start recurring operation through the real screens; the browser then closes. With no browser or HTTP
caller, separate `edge_os_api.execution.recurring_producer` processes run passes at fixed five-minute slot
offsets from one anchor (`--clock-offset-minutes`, accepted in local fixture mode only):

- slot 0 twice at once (two processes: one occurrence), then slots 5, 10 and 25 (15 and 20 are missed);
- slot 30 after the desktop owner stopped new entries, slot 35 after removal and the other owner's end;
- after the shared API restart, slot 40 (nothing may change).

The producers record their authored fixture effects in their own `recurring-effects.jsonl`, apart from the
financial phase's record. Direct SQL compares deployments, occurrences, outcomes, decisions, intents and attempts
with that effect record. Authored fixtures only: no wallet, quote, signature, transaction or chain evidence.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import harness

EFFECTS_NAME = "recurring-effects.jsonl"
PROJECTS = ("desktop", "mobile-390")
SLOT_MINUTES = 5


def _rows(pg: harness.Postgres, sql: str) -> list[dict[str, Any]]:
    return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))


def _effects(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []


def anchor_now() -> dt.datetime:
    """Mid-slot on the UTC five-minute grid, so each pass lands well inside its intended slot."""
    now = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    return now - dt.timedelta(minutes=now.minute % SLOT_MINUTES) + dt.timedelta(seconds=150)


class Producer:
    """Launches producer processes whose clocks sit at `anchor + slot` minutes."""

    def __init__(self, env: dict[str, str], evidence: Path, anchor: dt.datetime) -> None:
        self.env = {**env, "EDGE_OS_FIXTURE_EFFECTS_PATH": str(evidence / EFFECTS_NAME)}
        self.log_dir = evidence / "logs"
        self.anchor = anchor
        self.runs: list[dict[str, Any]] = []

    def _command(self, slot: int) -> list[str]:
        target = self.anchor + dt.timedelta(minutes=slot)
        offset = (target - dt.datetime.now(dt.timezone.utc)).total_seconds() / 60
        return [harness.api_python(), "-m", "edge_os_api.execution.recurring_producer", "--once",
                "--clock-offset-minutes", f"{offset:.4f}"]

    def run(self, slot: int, copies: int = 1) -> list[int]:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        handles, procs = [], []
        for index in range(copies):
            handle = open(self.log_dir / f"recurring-producer-slot{slot}-{index}.log", "ab")
            handles.append(handle)
            procs.append(subprocess.Popen(self._command(slot), cwd=harness.API_DIR, env=self.env, stdout=handle,
                                          stderr=handle))
        codes = [proc.wait(timeout=300) for proc in procs]
        for handle in handles:
            handle.close()
        self.runs.append({"slot": slot, "copies": copies, "exit_codes": codes})
        return codes


def inspect(pg: harness.Postgres, evidence: Path, results: dict[str, Any]) -> dict[str, Any]:
    """Direct SQL over the recurring rows of this run's two owners, compared with the producers' effect record."""
    effects = _effects(evidence / EFFECTS_NAME)
    checks: dict[str, Any] = {}
    expectations: dict[str, bool] = {}
    for project in PROJECTS:
        agent = results.get(project, {}).get("agentId")
        deployment = _rows(pg, "select deployment_id::text, state, end_reason, missed_slots, occurrences, "
                               "missed_intervals, cursor_slot, consent_hash from execution_local.execution_recurring_deployments "
                               f"where agent_id = '{agent}'")
        jobs = _rows(pg, "select j.job_id::text, j.decision_slot, j.state, j.outcome, j.reason, j.action_id from "
                         "execution_local.execution_evaluation_jobs j join execution_local.execution_recurring_deployments d "
                         f"using (deployment_id) where d.agent_id = '{agent}' order by j.decision_slot")
        slots = _rows(pg, "select decision_slot, count(*) c from execution_local.execution_evaluation_jobs "
                          f"where agent_id = '{agent}' group by decision_slot having count(*) > 1")
        outcomes = _rows(pg, "select o.outcome, o.decision_id is not null decided, o.inputs_observed_at = o.decision_slot "
                             "observed_at_slot, o.inputs_collected_at is not null collected, "
                             "o.provenance->>'evidence_class' evidence from execution_local.execution_evaluation_outcomes o "
                             f"where o.agent_id = '{agent}' order by o.decision_slot")
        intents = _rows(pg, "select action_id, operation, admission_status, admission_reason from "
                            f"execution_local.execution_intents where agent_id = '{agent}' order by created_at")
        actions = {row["action_id"] for row in intents}
        mine = [effect for effect in effects if effect["action_id"] in actions]
        per_action = {action: sum(1 for effect in mine if effect["action_id"] == action) for action in actions}
        checks[project] = {"deployment": deployment, "jobs": jobs, "duplicate_slots": slots, "outcomes": outcomes,
                           "intents": intents, "effects_per_action": per_action}
        row = deployment[0] if len(deployment) == 1 else {}
        admitted = [i for i in intents if i["admission_status"] == "ADMITTED"]
        expectations.update({
            f"{project}: one deployment, ended as the owner directed": len(deployment) == 1 and row.get("state") == "ENDED"
            and row.get("end_reason") == ("REMOVAL_REQUESTED" if project == "desktop" else "OWNER_ENDED"),
            f"{project}: five occurrences on five distinct slots; two missed slots counted, none replayed":
            len(jobs) == 5 and not slots and row.get("missed_slots") == 2 and row.get("occurrences") == 5,
            f"{project}: one saved outcome per occurrence, forward fixture inputs, input time = slot":
            len(outcomes) == 5 and all(o["outcome"] == "SIGNAL" and o["decided"] and o["observed_at_slot"]
                                       and o["collected"] and o["evidence"] == "SYNTHETIC_FIXTURE" for o in outcomes),
            f"{project}: every admitted action reached the fixture exactly once": bool(admitted)
            and all(per_action.get(i["action_id"]) == 1 for i in admitted),
        })
        operations = [i["operation"] for i in intents]
        if project == "desktop":
            expectations.update({
                "desktop: entry, full exit, re-entry, exit, then the stopped entry was denied":
                operations == ["ENTRY", "EXIT", "ENTRY", "EXIT", "ENTRY"]
                and [j["outcome"] for j in jobs] == ["SUBMITTED_CONFIRMED"] * 4 + ["ADMISSION_DENIED"]
                and jobs[4]["reason"] == "STOPPED_NEW_ENTRIES" and len(mine) == 4,
            })
        else:
            expectations.update({
                "mobile-390: each unknown action reconciled from its receipt before the next traded; the attempt "
                "budget then denied the fifth entry before any effect":
                [j["outcome"] for j in jobs] == ["SUBMITTED_CONFIRMED"] * 4 + ["ADMISSION_DENIED"]
                and jobs[4]["reason"] == "ATTEMPT_BUDGET_EXHAUSTED" and len(mine) == 4
                and operations == ["ENTRY", "EXIT", "ENTRY", "EXIT", "ENTRY"],
            })
    return {"checks": checks, "expectations": expectations, "effects_lines": len(effects),
            "all_checks_pass": bool(checks) and all(expectations.values())}


def drive(rec: Any, pg: harness.Postgres, env: dict[str, str], evidence: Path, ui_env: dict[str, str],
          run_playwright: Callable[..., int]) -> tuple[bool, dict[str, Any]]:
    code = run_playwright(["recurring-journey.spec.mjs"], ui_env, evidence / "ui-recurring-journey.log")
    ok = rec.step("P27 recurring: two owners save a revision, fund the agent, adopt terms and start recurring "
                  "operation through the screens (desktop and 390px)", code == 0, {"exit": code})
    producer = Producer(env, evidence, anchor_now())
    codes = producer.run(0, copies=2)
    contention = _rows(pg, "select d.agent_id, count(*) c from execution_local.execution_evaluation_jobs j join "
                           "execution_local.execution_recurring_deployments d using (deployment_id) group by d.agent_id")
    ok &= rec.step("two producer processes in one slot saved one occurrence per deployment (browser closed)",
                   codes == [0, 0] and sorted(row["c"] for row in contention) == [1, 1],
                   {"exit_codes": codes, "occurrences": contention})
    passes = {slot: producer.run(slot) for slot in (5, 10, 25)}
    ok &= rec.step("producer passes at slots 5, 10 and 25 with the browser closed (15 and 20 missed)",
                   all(value == [0] for value in passes.values()), passes)
    code = run_playwright(["recurring-report.spec.mjs", "--grep", "stage A"], ui_env, evidence / "ui-recurring-a.log")
    ok &= rec.step("reopened: entry, full exit and re-entry traded; unknown actions reconciled from receipts; missed "
                   "slots shown; other owner denied; desktop stops new entries (desktop and 390px)", code == 0,
                   {"exit": code})
    ok &= rec.step("producer pass at slot 30 after the stop", producer.run(30) == [0])
    code = run_playwright(["recurring-report.spec.mjs", "--grep", "stage B"], ui_env, evidence / "ui-recurring-b.log")
    ok &= rec.step("stop denied the next entry; desktop requests removal; the other owner ends recurring operation",
                   code == 0, {"exit": code})
    ok &= rec.step("producer pass at slot 35 after removal and end", producer.run(35) == [0])
    code = run_playwright(["recurring-report.spec.mjs", "--grep", "stage C"], ui_env, evidence / "ui-recurring-c.log")
    ok &= rec.step("both deployments ended; the last unknown action reconciled; residual holdings readable",
                   code == 0, {"exit": code})
    results_path = evidence / "ui" / "recurring-results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    inspection = inspect(pg, evidence, results)
    inspection["producer_runs"] = producer.runs
    inspection["anchor"] = producer.anchor.isoformat()
    rec.write("recurring-inspection.json", inspection)
    ok &= rec.step("recurring deployments, occurrences, outcomes, intents and the producers' effect record agree "
                   "(direct SQL)", inspection["all_checks_pass"], inspection["expectations"])
    inspection["producer"] = producer
    return ok, inspection


def after_restart(rec: Any, pg: harness.Postgres, evidence: Path, ui_env: dict[str, str],
                  run_playwright: Callable[..., int], before: dict[str, Any]) -> bool:
    producer: Producer = before["producer"]
    ok = rec.step("producer pass at slot 40 after the restart", producer.run(40) == [0])
    code = run_playwright(["recurring-report.spec.mjs", "--grep", "after restart"], ui_env,
                          evidence / "ui-recurring-restart.log")
    ok &= rec.step("recurring record reopens unchanged after the restart (new browser context)", code == 0,
                   {"exit": code})
    results = json.loads((evidence / "ui" / "recurring-results.json").read_text())
    after = inspect(pg, evidence, results)
    rec.write("recurring-inspection-after-restart.json", {**after, "producer_runs": producer.runs})
    ok &= rec.step("recurring rows and effects unchanged by the restart and a later pass (ended stays ended)",
                   after["checks"] == before["checks"] and after["effects_lines"] == before["effects_lines"],
                   {"effects_before": before["effects_lines"], "effects_after": after["effects_lines"]})
    return ok
