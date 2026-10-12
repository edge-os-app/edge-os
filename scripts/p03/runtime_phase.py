"""#58 Stage 2 runtime phase of the mapped verifier.

Runs inside `verify_run.py` on the same isolated instance, after the financial and research restart checks, so its
writes cannot change their before/after comparisons. It checks:

- the read-only service projection through the mounted API (owner scoping, unknown values stay unknown);
- shared quota totals in SQL (GLOBAL totals equal the sum of the OWNER totals for every resource);
- a second API process on the same database with a different cap and a small write rate: readiness reports
  `quota_cap_mismatch` and the third write in one minute gets 429 with `Retry-After`;
- workers stop with exit code 3 before any effect on a database that is one migration behind;
- the browser: the projection panel, a saved change whose read-back fails (controls stay paused) and a keyboard pass
  (desktop and 390px), through `runtime.spec.mjs`.

Everything stays on loopback. No credential, provider or network call is made.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import harness

RUNTIME_OWNER = "did:privy:test-runtime-d"
DRIFT_REVISION = "0009"


def _request(method: str, url: str, token: str | None = None, body: object = None
             ) -> tuple[int, dict[str, Any], dict[str, str]]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - loopback only
            return response.status, json.loads(response.read() or b"{}"), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}"), dict(error.headers)


def _rows(pg: harness.Postgres, sql: str) -> list[dict[str, Any]]:
    return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))


def projection_checks(api_url: str, token_a: str, token_b: str, agent_id: str) -> dict[str, Any]:
    status, page, _ = _request("GET", f"{api_url}/v1/account-views/service?agent_id={agent_id}", token_a)
    records = page.get("records", []) if status == 200 else []
    contents = [item["content"] for item in records]
    kinds = sorted({item["record_kind"] for item in contents})
    positions = [item for item in contents if item["record_kind"] == "POSITION"]
    flows = [item for item in contents if item["record_kind"] == "CAPITAL_FLOW"]
    foreign_status, foreign, _ = _request("GET", f"{api_url}/v1/account-views/service?agent_id={agent_id}", token_b)
    checks = {
        "owner_reads_projection": status == 200 and page.get("ports") == "FIXTURE",
        "every_record_is_a_service_projection": bool(contents)
        and all(item["evidence_class"] == "SERVICE_PROJECTION" for item in contents),
        "agent_flow_position_action_monitoring_present": {"AGENT", "CAPITAL_FLOW", "POSITION", "ACTION",
                                                          "MONITORING"} <= set(kinds),
        "unrealized_result_and_mark_stay_unknown": bool(positions) and all(
            item["estimated_unrealized_result"]["state"] == "UNKNOWN" and item["mark"]["state"] == "UNKNOWN"
            for item in positions),
        "deposits_are_not_results": bool(flows) and all(item["included_in_realized_result"] is False for item in flows),
        "another_owner_sees_nothing": foreign_status == 200 and foreign.get("records") == [],
    }
    return {"checks": checks, "kinds": kinds, "records": len(records)}


def quota_checks(pg: harness.Postgres) -> dict[str, Any]:
    totals = _rows(pg, """
        select resource,
               sum(reserved) filter (where scope = 'GLOBAL') as global_reserved,
               sum(reserved) filter (where scope = 'OWNER') as owner_reserved,
               sum(consumed) filter (where scope = 'GLOBAL') as global_consumed,
               sum(consumed) filter (where scope = 'OWNER') as owner_consumed,
               sum(unknown) filter (where scope = 'GLOBAL') as global_unknown,
               sum(unknown) filter (where scope = 'OWNER') as owner_unknown,
               sum(overrun) filter (where scope = 'GLOBAL') as global_overrun,
               sum(overrun) filter (where scope = 'OWNER') as owner_overrun
        from usage_local.usage_allocations group by resource order by resource""")
    reservations = _rows(pg, "select subject_kind, count(*) as count from usage_local.usage_reservations "
                             "group by subject_kind")
    jobs = int(pg.psql("select count(*) from research_local.investigation_jobs "
                       "where (budget->'reserved'->>'provider_requests')::bigint > 0"))
    consistent = bool(totals) and all(
        row[f"global_{part}"] == row[f"owner_{part}"] for row in totals
        for part in ("reserved", "consumed", "unknown", "overrun"))
    reserved_jobs = sum(row["count"] for row in reservations if row["subject_kind"] == "investigation_job")
    return {"totals": totals, "reservations": reservations, "jobs_with_reservations": jobs,
            "checks": {"global_equals_sum_of_owners": consistent, "one_reservation_per_reserving_job":
                       reserved_jobs == jobs and jobs > 0}}


def second_process_checks(env: dict[str, str], evidence: Path, signer: Any, processes: list[Any]) -> dict[str, Any]:
    """A second API process with a changed global cap and a write rate of 2 on the same database."""
    port = harness.free_port()
    url = f"http://127.0.0.1:{port}"
    changed = {**env, "EDGE_OS_WRITE_RATE_PER_MINUTE": "2",
               "EDGE_OS_USAGE_GLOBAL_COMPUTE_SECONDS": str(int(env.get("EDGE_OS_USAGE_GLOBAL_COMPUTE_SECONDS",
                                                                       "10000000")) + 1)}
    api = harness.start_api(changed, port, evidence / "logs", name="api-runtime-limits")
    processes.append(api)
    try:
        harness.wait_http(f"{url}/healthz")
        ready_status, ready, _ = _request("GET", f"{url}/readyz")
        token = signer.token(RUNTIME_OWNER)
        writes = [_request("POST", f"{url}/v1/research/requests", token, {}) for _ in range(3)]
        budget_status, _, _ = _request("GET", f"{url}/v1/research/budget", token)
    finally:
        api.stop()
    statuses = [status for status, _, _ in writes]
    retry_after = writes[-1][2].get("Retry-After") or writes[-1][2].get("retry-after")
    checks = {
        "readiness_reports_cap_mismatch": ready_status == 503 and ready.get("reason") == "quota_cap_mismatch"
        and "compute_seconds" in json.dumps(ready),
        # Two writes inside the limit reach validation (422 for the empty body); the third is refused first.
        "third_write_in_a_minute_is_rate_limited": statuses == [422, 422, 429]
        and bool(retry_after) and 1 <= int(retry_after) <= 61,
        "reads_are_not_rate_limited": budget_status in {200, 503},
    }
    return {"checks": checks, "readyz": ready, "write_statuses": statuses, "retry_after": retry_after,
            "budget_read_status": budget_status}


def drift_checks(pg: harness.Postgres, env: dict[str, str], evidence: Path) -> dict[str, Any]:
    """Both workers stop with exit code 3 on a database one migration behind, before any effect."""
    database = f"{pg.database}_drift"
    pg.psql(f"create database {database}", db="postgres")
    try:
        url = pg.url.rsplit("/", 1)[0] + f"/{database}"
        drift_env = {**env, "EDGE_OS_DATABASE_URL": url}
        upgrade = subprocess.run([harness.api_python(), "-m", "alembic", "upgrade", DRIFT_REVISION],
                                 cwd=harness.API_DIR, env=drift_env, capture_output=True, text=True, timeout=180)
        before = pg.psql("select (select count(*) from execution_local.execution_evaluation_jobs) || ':' || "
                         "(select count(*) from research_local.investigation_jobs)", db=database)
        log_dir = evidence / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        codes = {}
        for name, module in (("execution", "edge_os_api.execution.worker"),
                             ("research", "edge_os_api.research.investigation_jobs")):
            with open(log_dir / f"worker-drift-{name}.log", "ab") as handle:
                codes[name] = subprocess.run([harness.api_python(), "-m", module, "--once"], cwd=harness.API_DIR,
                                             env=drift_env, stdout=handle, stderr=handle, timeout=120).returncode
        after = pg.psql("select (select count(*) from execution_local.execution_evaluation_jobs) || ':' || "
                        "(select count(*) from research_local.investigation_jobs)", db=database)
        revision = pg.psql("select version_num from alembic_version", db=database)
    finally:
        pg.psql(f"drop database if exists {database} with (force)", db="postgres")
    checks = {"database_one_migration_behind": upgrade.returncode == 0 and revision == DRIFT_REVISION,
              "both_workers_exit_3": codes == {"execution": 3, "research": 3},
              "no_rows_written": before == after}
    return {"checks": checks, "exit_codes": codes, "rows_before": before, "rows_after": after}


def drive(rec: Any, pg: harness.Postgres, env: dict[str, str], evidence: Path, ui_env: dict[str, str],
          run_playwright: Callable[..., int], processes: list[Any], signer: Any) -> bool:
    api_url, token_a, token_b = ui_env["P03_API_URL"], ui_env["P03_TOKEN_A"], ui_env["P03_TOKEN_B"]
    financial = json.loads((evidence / "ui" / "financial-results.json").read_text())
    agent_id = financial["main-desktop"]["agentId"]

    projection = projection_checks(api_url, token_a, token_b, agent_id)
    rec.write("runtime-projection.json", projection)
    ok = rec.step("F1 service projection: owner-scoped, unknown marks stay unknown, deposits are not results (API)",
                  all(projection["checks"].values()), projection["checks"])

    quotas = quota_checks(pg)
    rec.write("runtime-quotas.json", quotas)
    ok &= rec.step("shared quotas: GLOBAL totals equal the OWNER totals; one reservation per reserving job (SQL)",
                   all(quotas["checks"].values()), quotas["checks"])

    limits = second_process_checks(env, evidence, signer, processes)
    rec.write("runtime-limits.json", limits)
    ok &= rec.step("second API process: changed cap reported by readiness; third write in a minute gets 429",
                   all(limits["checks"].values()), limits["checks"])

    drift = drift_checks(pg, env, evidence)
    rec.write("runtime-drift.json", drift)
    ok &= rec.step("workers stop with exit 3 before any effect on a database one migration behind",
                   all(drift["checks"].values()), drift["checks"])

    code = run_playwright(["runtime.spec.mjs"], ui_env, evidence / "ui-runtime.log")
    ok &= rec.step("projection panel, failed read-back pause and keyboard pass (desktop and 390px)", code == 0,
                   {"exit": code})
    return ok
