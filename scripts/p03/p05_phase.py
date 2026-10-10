"""P05 phase of the mapped verification path: Research through the ACTUAL pinned Hermes and a LOCAL FAKE provider.

It runs after the fixture-interpreter phase, on the same database and the same web build. The API process is replaced by
`scripts/hermes_interpretation/serve_local.py`; each model turn runs in a no-network container whose provider answers from
an authored script queue that the browser spec fills. Nothing here proves how a real model reads a request.

Steps: build the pinned Hermes image, start the API on the same port, drive the browser, inspect the attempt rows with SQL
and compare them with HTTP, deny another owner, restart the API, reopen in a new browser context, and remove the image.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import harness

sys.path.insert(0, str(harness.REPO / "scripts" / "hermes_interpretation"))
from docker_turn_runner import PinnedHermesImage  # noqa: E402

SERVE_LOCAL = harness.REPO / "scripts" / "hermes_interpretation" / "serve_local.py"
RUN_BUDGET_SECONDS, TURN_TIMEOUT_SECONDS = 8, 40  # short enough to exercise the unknown-outcome path at both widths


def http(method: str, url: str, token: str | None = None, body: object = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - loopback only
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def request_ids(results: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for value in results.values():
        for key in ("id", "malformed", "unknown", "conflictId", "rejectedId"):
            if isinstance(value, dict) and key in value:
                ids.append(value[key])
    return list(dict.fromkeys(ids))


def start_hermes_api(env: dict[str, str], port: int, image_tag: str, run_id: str, workdir: Path, script_file: Path,
                     log_dir: Path, name: str) -> harness.Process:
    log_dir.mkdir(parents=True, exist_ok=True)
    handle = open(log_dir / f"{name}.log", "ab")
    popen = subprocess.Popen(
        [harness.api_python(), str(SERVE_LOCAL), "--port", str(port), "--image", image_tag, "--run-id", run_id,
         "--evidence-dir", str(workdir / "turns"), "--script-file", str(script_file),
         "--run-budget-seconds", str(RUN_BUDGET_SECONDS), "--timeout-seconds", str(TURN_TIMEOUT_SECONDS)],
        cwd=harness.API_DIR, env={**env, "EDGE_OS_INTERPRETER": "hermes_local"}, stdout=handle, stderr=handle,
        start_new_session=True)
    return harness.Process(name, popen, log_dir / f"{name}.log", handle)


def sql_rows(pg: harness.Postgres, sql: str) -> list[dict[str, Any]]:
    return json.loads(pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t"))


def attempt_snapshot(pg: harness.Postgres, intake_id: str) -> list[dict[str, Any]]:
    """Every stored column of one request's attempts, settlements, links and late results, in order."""
    return sql_rows(pg, f"""
        select a.sequence, a.attempt_id, a.retry_of, a.purpose, a.prompt_version, a.system_prompt_sha256, a.task_sha256,
               a.response_shape_sha256, a.manifest_sha256, a.config_sha256, a.config, a.runtime_label, a.answer_ref,
               a.answer_text, a.answer_sha256, a.previous_revision_id, a.started_at,
               s.status, s.finished_at, s.latency_ms, s.input_tokens, s.output_tokens, s.total_tokens, s.usage_source,
               s.request_count, s.response_sha256, s.response_text, s.parse_result, s.error_class, s.runtime_observed,
               l.revision_record_id, l.offered_questions,
               (select count(*) from interpretation_late_results x where x.attempt_id = a.attempt_id) late_results
        from interpretation_attempts a
        left join interpretation_settlements s on s.attempt_id = a.attempt_id
        left join interpretation_attempt_links l on l.attempt_id = a.attempt_id
        where a.intake_record_id = '{intake_id}' order by a.sequence""")


def inspect_attempts(pg: harness.Postgres, api_url: str, token: str, ids: list[str]) -> dict[str, Any]:
    checks: dict[str, Any] = {"requests": {}}
    bad_hash = sql_rows(pg, """
        select (select count(*) from interpretation_attempts where task_sha256 <> encode(sha256(convert_to(task_text, 'UTF8')), 'hex')) tasks,
               (select count(*) from interpretation_settlements where response_text is not null
                  and response_sha256 <> encode(sha256(convert_to(response_text, 'UTF8')), 'hex')) responses,
               (select count(*) from interpretation_attempts a left join interpretation_settlements s using (attempt_id)
                  where s.attempt_id is null) open_attempts,
               (select count(*) from interpretation_settlements where usage_source = 'UNKNOWN'
                  and (input_tokens is not null or output_tokens is not null or total_tokens is not null)) invented_usage,
               (select count(*) from interpretation_attempt_links l join records r on r.record_id = l.revision_record_id
                  where r.owner_id <> l.owner_id or r.intake_record_id <> l.intake_record_id) foreign_links""")[0]
    checks["global"] = bad_hash
    for intake_id in ids:
        rows = attempt_snapshot(pg, intake_id)
        status, bundle = http("GET", f"{api_url}/v1/research/requests/{intake_id}", token)
        public = bundle.get("attempts", []) if status == 200 else []
        matches = len(rows) == len(public) and all(
            row["attempt_id"] == item["attempt_id"] and row["status"] == item["status"]
            and row["parse_result"] == item["parse_result"] and row["latency_ms"] == item["latency_ms"]
            and (row["input_tokens"], row["output_tokens"]) == (item["usage"]["input_tokens"], item["usage"]["output_tokens"])
            and row["usage_source"] == item["usage"]["source"] and row["request_count"] == item["request_count"]
            and row["task_sha256"] == item["identity"]["task_sha256"] and row["config_sha256"] == item["identity"]["config_sha256"]
            and (row["revision_record_id"] or None) == item["revision_id"]
            for row, item in zip(rows, public))
        dumped = json.dumps(bundle)
        leaked = [row["attempt_id"] for row in rows if row["response_text"] and row["response_text"] in dumped]
        checks["requests"][intake_id] = {
            "attempts": len(rows), "http_matches_sql": matches, "generated_text_in_public_response": leaked,
            "statuses": [row["status"] for row in rows], "retry_chain": [(row["sequence"], row["retry_of"]) for row in rows],
            "sequences_are_consecutive": [row["sequence"] for row in rows] == list(range(1, len(rows) + 1)),
            "usage_unknown_kept_null": all(row["usage_source"] != "UNKNOWN" or row["input_tokens"] is None for row in rows if row["status"]),
            "hermes_commit": sorted({row["config"].get("hermes_commit") for row in rows}),
            "runtime_labels": sorted({row["runtime_label"] for row in rows}),
            "observed_one_request": all(row["request_count"] == 1 for row in rows if row["status"] in ("COMPLETED", "TRUNCATED")),
        }
    request_checks = checks["requests"].values()
    checks["all_checks_pass"] = (
        all(value == 0 for key, value in bad_hash.items())
        and all(c["http_matches_sql"] and not c["generated_text_in_public_response"] and c["sequences_are_consecutive"]
                and c["usage_unknown_kept_null"] and c["observed_one_request"] for c in request_checks)
        and all(c["attempts"] >= 1 for c in request_checks))
    return checks


def deny_other_owner(pg: harness.Postgres, api_url: str, token_a: str, token_b: str, intake_id: str) -> dict[str, Any]:
    before = pg.psql("select (select count(*) from interpretation_attempts) || '/' || (select count(*) from records)")
    revision = http("GET", f"{api_url}/v1/research/requests/{intake_id}", token_a)[1]["head"]["interpretation_revision_id"]
    outcomes = {
        "read": http("GET", f"{api_url}/v1/research/requests/{intake_id}", token_b)[0],
        "answer_choice": http("POST", f"{api_url}/v1/research/requests/{intake_id}/clarifications", token_b,
                              {"previous_revision_id": revision or "x", "question_id": "choose-entry", "choice_id": "g3-1pct"})[0],
        "answer_words": http("POST", f"{api_url}/v1/research/requests/{intake_id}/clarifications", token_b,
                             {"previous_revision_id": revision or "x", "question_id": "choose-entry", "answer_text": "words"})[0],
        "retry": http("POST", f"{api_url}/v1/research/requests/{intake_id}/interpretation-retries", token_b, {"retry_of": None})[0],
        "owner_a_still_reads": http("GET", f"{api_url}/v1/research/requests/{intake_id}", token_a)[0],
    }
    after = pg.psql("select (select count(*) from interpretation_attempts) || '/' || (select count(*) from records)")
    denied = all(outcomes[key] == 404 for key in ("read", "answer_choice", "answer_words", "retry"))
    return {"statuses": outcomes, "rows_before": before, "rows_after": after,
            "all_denied": denied and outcomes["owner_a_still_reads"] == 200 and before == after}


def turn_count(workdir: Path) -> int:
    return len(list((workdir / "turns").glob("turn-*")))


def run_p05_phase(rec: Any, pg: harness.Postgres, env: dict[str, str], api_port: int, api_url: str, evidence: Path,
                  run_id: str, ui_env: dict[str, str], token_a: str, token_b: str, run_playwright: Any,
                  current_api: harness.Process, processes: list[Any]) -> bool:
    """Returns whether every step passed.

    It stops `current_api`, runs the Hermes API for the P05 steps, and ends by starting the standard API again so the
    rest of the run (and a hold for SQL inspection) finds the service it expects. Every process that it starts goes into
    `processes` at once, so the caller's own cleanup stops it even when a step here raises.
    """
    ok = True
    workdir = evidence / "p05"
    workdir.mkdir(parents=True, exist_ok=True)
    image = PinnedHermesImage(run_id, workdir / "image")
    process: harness.Process | None = None
    image_built = False
    try:
        tag = image.build()
        image_built = True
        identity = json.loads((workdir / "image" / "source_identity.json").read_text())
        rec.write("p05-hermes-source-identity.json", identity)
        ok &= rec.step("P05: pinned Hermes image built from the locked source (no egress at run time)",
                       identity["commit"] == "54bc5e509c985f37265c3d416bd2c64b10fc77ba",
                       {"commit": identity["commit"], "uv_lock_sha256": identity["uv_lock_sha256"], "image_tag": tag})
        script_file = workdir / "script-queue.json"
        script_file.write_text("[]")
        current_api.stop()
        process = start_hermes_api(env, api_port, tag, run_id, workdir, script_file, evidence / "logs", "api-hermes-local")
        processes.append(process)
        harness.wait_http(f"{api_url}/readyz")
        status, label = http("GET", f"{api_url}/v1/interpreter", token_a)
        ok &= rec.step("P05: API runs with the local Hermes interpreter, labelled as a fake provider",
                       status == 200 and label["interpreter"]["kind"] == "HERMES_LOCAL_FAKE_PROVIDER", label.get("interpreter"))

        p05_env = {**ui_env, "P05_SCRIPT_FILE": str(script_file)}
        code = run_playwright(["interpreter.spec.mjs"], p05_env, evidence / "ui-p05.log")
        ok &= rec.step("P05: browser drive at desktop and 390px (failure, retry, words, conflict, rejection, unsupported)",
                       code == 0, {"exit": code})
        results_path = evidence / "ui" / "p05-results.json"
        results = json.loads(results_path.read_text()) if results_path.exists() else {}
        ids = request_ids(results)
        inspection = inspect_attempts(pg, api_url, token_a, ids)
        rec.write("p05-sql-inspection.json", inspection)
        ok &= rec.step("P05: saved attempts match what the API returns, hashes recompute, usage stays unknown, no generated text is public",
                       bool(ids) and inspection["all_checks_pass"], inspection["global"])
        snapshots = {intake_id: attempt_snapshot(pg, intake_id) for intake_id in ids}
        rec.write("p05-attempt-rows-before-restart.json", snapshots)

        denial = deny_other_owner(pg, api_url, token_a, token_b, ids[0]) if ids else {"all_denied": False}
        rec.write("p05-ownership-drive.json", denial)
        ok &= rec.step("P05: another owner is denied read, answer and retry, and no row changes", denial["all_denied"], denial)

        turns_before = turn_count(workdir)
        process.stop()
        process = start_hermes_api(env, api_port, tag, run_id, workdir, script_file, evidence / "logs", "api-hermes-local-restarted")
        processes.append(process)
        harness.wait_http(f"{api_url}/readyz")
        code = run_playwright(["interpreter-after-restart.spec.mjs"], p05_env, evidence / "ui-p05-reopen.log")
        ok &= rec.step("P05: saved attempts and states reopen unchanged after restart (new browser context, no write)",
                       code == 0, {"exit": code})
        after = {intake_id: attempt_snapshot(pg, intake_id) for intake_id in ids}
        rec.write("p05-attempt-rows-after-restart.json", after)
        ok &= rec.step("P05: attempt rows are byte-for-byte unchanged by the restart and the restart started no model turn",
                       after == snapshots and turn_count(workdir) == turns_before,
                       {"turns_before": turns_before, "turns_after": turn_count(workdir)})
    finally:
        if process is not None:
            process.stop()
        if image_built:
            removal = image.remove()
            rec.write("p05-image-removal.json", removal)
            ok &= rec.step("P05: removed this run's image; no labelled container is left",
                           removal["image_removed"] and not removal["labeled_containers_left"], removal)
        current_api.stop()  # already stopped when the phase got that far; stopping again is harmless
        standard = harness.start_api(env, api_port, evidence / "logs", name="api-after-p05")
        processes.append(standard)  # registered before any wait, so a failed wait cannot lose the handle
        harness.wait_http(f"{api_url}/readyz")
    return bool(ok)
