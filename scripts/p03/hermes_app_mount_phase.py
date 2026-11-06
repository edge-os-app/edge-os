"""HERMES-MOUNT phase of the mapped verification path: the Research journey over the LOCAL Hermes transport mount.

It runs right after the P05 phase, on the same database, web build and port. It builds its own pinned Hermes image and
replaces the standard API with `scripts/hermes_app_mount/serve_transport_mount.py`: the accepted guarded runner,
transport identity check and no-network job over the shared PostgreSQL spend ledger, with the AUTHORED transport and a
dummy credential. Nothing here reaches a real provider. It ends by removing its image and starting the standard API again.

Steps: build the image, start the mount, drive the browser (a completed turn and a lost reply, desktop and 390px, reopen in a new context,
another owner refused), compare SQL with HTTP and with the job's own request files, deny another owner, restart the
same run id, reopen in a new browser context, prove nothing changed and nothing ran, and scan for the credential.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import harness
from p05_phase import attempt_snapshot, deny_other_owner, http, inspect_attempts, sql_rows  # adds the Hermes support path
from docker_turn_runner import PinnedHermesImage  # noqa: E402 - scripts/hermes_interpretation, on the path through p05_phase
from leak_scan import find_leaks  # noqa: E402 - same folder

MOUNT_HOST = harness.REPO / "scripts" / "hermes_app_mount" / "serve_transport_mount.py"
SENTINEL = "sk-test-DUMMY-SENTINEL-mount-4c1e9a7b20d3"
ROUTE_ID = "authored-local-1"
EXACT_CHARGE_NANO = 7_428_500  # concrete-thesis: 1,423 x 2.00 + 611 x 7.50 USD per million tokens
RESERVATION_NANO = 54_848_000  # (12,000 + 64) x 2.00 + 4,096 x 7.50 USD per million tokens
SPEND_ROWS = ("select attempt_id, owner_id, intake_record_id, scope, state, reserved_nano_usd, charged_nano_usd "
              "from usage_local.provider_spend_reservations order by attempt_id")


def start_mount(env: dict[str, str], port: int, tag: str, run_id: str, workdir: Path, log_dir: Path, name: str,
                report: Path) -> harness.Process:
    log_dir.mkdir(parents=True, exist_ok=True)
    handle = open(log_dir / f"{name}.log", "ab")
    popen = subprocess.Popen(
        [harness.api_python(), str(MOUNT_HOST), "--port", str(port), "--image", tag, "--run-id", run_id,
         "--evidence-dir", str(workdir / "turns"), "--script-file", str(workdir / "script-queue.json"),
         "--credential-file", str(workdir / "private-credential"), "--report-file", str(report),
         "--global-cap", "0.50", "--owner-cap", "0.25"],
        cwd=harness.API_DIR, env={**env, "EDGE_OS_INTERPRETER": "hermes_local"}, stdout=handle, stderr=handle,
        start_new_session=True)
    return harness.Process(name, popen, log_dir / f"{name}.log", handle)


def requests_sent(workdir: Path, attempt_id: str) -> int:
    """Requests the authored provider received for one attempt, counted from the job's own request files."""
    return sum(len(list(turn.glob("output/requests/request-*.json")))
               for turn in (workdir / "turns").glob(f"turn-*-{attempt_id}"))


def job_names_the_attempt(workdir: Path, attempt_id: str) -> bool:
    """The job's own result file and the wire request it received both name this attempt."""
    for turn in (workdir / "turns").glob(f"turn-*-{attempt_id}"):
        result = turn / "output" / "container-result.json"
        wire = turn / "output" / "requests" / "request-1.json"
        if result.exists() and wire.exists():
            return (json.loads(result.read_text()).get("attempt_id") == attempt_id
                    and json.loads(wire.read_text()).get("session_id") == f"p05-{attempt_id}")
    return False


def saved_revision(pg: harness.Postgres, item: dict[str, Any]) -> dict[str, Any]:
    """The saved strategy revision of a completed mounted request: owner, request, draft and the attempt's interpretation."""
    revision = item.get("revision", "")
    [row] = sql_rows(pg, f"""
        select (select count(*) from strategy_revisions where revision_id::text = '{revision}') revisions,
               (select count(*) from strategy_revisions s join records r on r.owner_id = s.owner_id
                  where s.revision_id::text = '{revision}' and r.record_id::text = '{item['id']}') owner_matches_request,
               (select count(*) from strategy_revisions s join records d on d.record_id = s.draft_record_id
                  where s.revision_id::text = '{revision}' and d.intake_record_id::text = '{item['id']}') draft_belongs_to_request,
               (select count(*) from strategy_revisions s
                  where s.revision_id::text = '{revision}'
                  and s.content_sha256 = encode(sha256(convert_to(s.strategy_canonical, 'UTF8')), 'hex')) hash_recomputes,
               (select count(*) from interpretation_attempt_links l join strategy_revisions s on s.owner_id = l.owner_id
                  where l.attempt_id::text = '{item['attempt']}' and l.intake_record_id::text = '{item['id']}'
                  and s.revision_id::text = '{revision}') attempt_interpretation_linked,
               (select count(*) from interpretation_attempts where intake_record_id::text = '{item['id']}') attempts""")
    return {**row, "all_checks_pass": bool(revision) and all(row[key] == 1 for key in row)}


def turn_count(workdir: Path) -> int:
    return len(list((workdir / "turns").glob("turn-*")))


def inspect_mount(pg: harness.Postgres, api_url: str, token: str, workdir: Path, results: dict[str, Any]) -> dict[str, Any]:
    spend = {row["attempt_id"]: row for row in sql_rows(pg, SPEND_ROWS)}
    checks: dict[str, Any] = {}
    for key, item in sorted(results.items()):
        completed = key.startswith("mount-completed-")
        [settled] = sql_rows(pg, f"select s.status, s.parse_result, s.runtime_observed, s.input_tokens, s.output_tokens, "
                                 f"a.owner_id, a.intake_record_id from interpretation_settlements s join interpretation_attempts a "
                                 f"using (attempt_id) where attempt_id = '{item['attempt']}'")
        observed = settled["runtime_observed"]
        status, bundle = http("GET", f"{api_url}/v1/research/requests/{item['id']}", token)
        public = next((a for a in bundle.get("attempts", []) if a["attempt_id"] == item["attempt"]), {}) if status == 200 else {}
        reservation = spend.get(item["attempt"], {})
        expected = ("SETTLED", EXACT_CHARGE_NANO) if completed else ("UNKNOWN", None)
        checks[key] = {
            "status": settled["status"], "parse_result": settled["parse_result"],
            "transport_identity_is_the_attempt": (
                observed.get("transport_attempt_id") == item["attempt"]
                and observed.get("transport_request_attempt_ids") == [item["attempt"]]
                and observed.get("transport_route_id") == ROUTE_ID),
            "requests_at_the_transport": requests_sent(workdir, item["attempt"]),
            "job_and_wire_name_the_attempt": job_names_the_attempt(workdir, item["attempt"]),
            "reservation_owner_and_request_are_the_attempts": (
                reservation.get("owner_id"), reservation.get("intake_record_id")) == (settled["owner_id"], settled["intake_record_id"])
            and settled["intake_record_id"] == item["id"],
            "usage": [settled["input_tokens"], settled["output_tokens"]],
            "usage_as_expected": [settled["input_tokens"], settled["output_tokens"]] == ([1423, 611] if completed else [None, None]),
            "reservation": {k: reservation.get(k) for k in ("state", "reserved_nano_usd", "charged_nano_usd", "scope")},
            "reservation_as_expected": (reservation.get("state"), reservation.get("charged_nano_usd")) == expected
            and reservation.get("reserved_nano_usd") == RESERVATION_NANO
            and reservation.get("scope") == f"intake:{item['id']}",
            "public_spend": public.get("spend"),
            "public_spend_matches": public.get("spend", {}).get("state") == expected[0],
            "result_as_expected": (settled["status"], settled["parse_result"]) == (
                ("COMPLETED", "ACCEPTED") if completed else ("UNKNOWN", "NOT_PARSED")),
            "saved_revision": saved_revision(pg, item) if completed else None,
        }
    sql_http = inspect_attempts(pg, api_url, token, [item["id"] for item in results.values()])
    total = pg.psql("select coalesce(sum(case when state = 'SETTLED' then charged_nano_usd when state in "
                    "('RESERVED', 'UNKNOWN') then reserved_nano_usd else 0 end), 0) from usage_local.provider_spend_reservations")
    completed_count = sum(1 for key in results if key.startswith("mount-completed-"))
    expected_total = completed_count * EXACT_CHARGE_NANO + (len(results) - completed_count) * RESERVATION_NANO
    return {"attempts": checks, "sql_matches_http": sql_http, "liability_nano_usd": int(total),
            "expected_liability_nano_usd": expected_total,
            "all_checks_pass": bool(results) and len(spend) == len(results) and int(total) == expected_total
            and sql_http["all_checks_pass"]
            and all(c["transport_identity_is_the_attempt"] and c["requests_at_the_transport"] == 1
                    and c["job_and_wire_name_the_attempt"] and c["reservation_owner_and_request_are_the_attempts"]
                    and c["usage_as_expected"]
                    and (c["saved_revision"] is None or c["saved_revision"]["all_checks_pass"])
                    and c["reservation_as_expected"] and c["public_spend_matches"] and c["result_as_expected"]
                    for c in checks.values())}


def drive_mount(rec: Any, pg: harness.Postgres, env: dict[str, str], api_port: int, api_url: str, evidence: Path,
                run_id: str, tag: str, ui_env: dict[str, str], token_a: str, token_b: str, run_playwright: Any,
                processes: list[Any]) -> bool:
    """Returns whether every step passed. The port must be free; this leaves it free again."""
    ok = True
    workdir = evidence / "hermes-app-mount" / "mount"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "script-queue.json").write_text("[]")
    credential = workdir / "private-credential"
    credential.write_text(SENTINEL)
    credential.chmod(0o400)
    process: harness.Process | None = None
    try:
        process = start_mount(env, api_port, tag, run_id, workdir, evidence / "logs", "api-hermes-mount",
                              workdir / "startup-1.json")
        processes.append(process)
        harness.wait_http(f"{api_url}/readyz", timeout=120)
        status, label = http("GET", f"{api_url}/v1/interpreter", token_a)
        startup = json.loads((workdir / "startup-1.json").read_text())
        ok &= rec.step("HERMES-MOUNT: the API runs with the transport mount (local Hermes label, clean startup recovery)",
                       status == 200 and label["interpreter"]["kind"] == "HERMES_LOCAL_FAKE_PROVIDER"
                       and startup["startup_recovery"] == [], {"label": label.get("interpreter"), "startup": startup})

        mount_env = {**ui_env, "HERMES_MOUNT_SCRIPT_FILE": str(workdir / "script-queue.json")}
        code = run_playwright(["hermes-transport-mount.spec.mjs"], mount_env, evidence / "ui-hermes-transport-mount.log")
        ok &= rec.step("HERMES-MOUNT: browser drive at desktop and 390px (submit, attempt and usage, adopt and save the "
                       "revision with no model call, reopen in a new context, other owner refused, lost reply unknown and "
                       "not retried)", code == 0, {"exit": code})
        results_path = evidence / "ui" / "hermes-mount-results.json"
        results = json.loads(results_path.read_text()) if results_path.exists() else {}
        inspection = inspect_mount(pg, api_url, token_a, workdir, results)
        rec.write("hermes-mount-inspection.json", inspection)
        ok &= rec.step("HERMES-MOUNT: SQL matches HTTP; transport identity is the attempt; one request per job at the "
                       "transport; exact charge or full unknown reservation per request; the saved revision belongs to the "
                       "owner, the request and the mounted attempt's interpretation", inspection["all_checks_pass"],
                       {"liability_nano_usd": inspection["liability_nano_usd"],
                        "expected": inspection["expected_liability_nano_usd"]})
        ids = sorted({item["id"] for item in results.values()})
        spend_before = pg.psql("select count(*) from usage_local.provider_spend_reservations")
        denial = deny_other_owner(pg, api_url, token_a, token_b, ids[0]) if ids else {"all_denied": False}
        denial["spend_rows_before_after"] = [spend_before, pg.psql("select count(*) from usage_local.provider_spend_reservations")]
        rec.write("hermes-mount-ownership-drive.json", denial)
        ok &= rec.step("HERMES-MOUNT: another owner is denied read, answer and retry; no attempt, record or spend row changes",
                       denial["all_denied"] and spend_before == denial["spend_rows_before_after"][1], denial)

        snapshots = {intake_id: attempt_snapshot(pg, intake_id) for intake_id in ids}
        spend_rows = sql_rows(pg, SPEND_ROWS)
        turns_before = turn_count(workdir)
        process.stop()
        process = start_mount(env, api_port, tag, run_id, workdir, evidence / "logs", "api-hermes-mount-restarted",
                              workdir / "startup-2.json")
        processes.append(process)
        harness.wait_http(f"{api_url}/readyz", timeout=120)
        restart = json.loads((workdir / "startup-2.json").read_text())
        code = run_playwright(["hermes-transport-mount-restart.spec.mjs"], mount_env, evidence / "ui-hermes-transport-mount-restart.log")
        ok &= rec.step("HERMES-MOUNT: after a restart with the same run id the saved revision and attempts reopen "
                       "unchanged (new browser context, no write)", code == 0 and restart["startup_recovery"] == [],
                       {"exit": code, "startup": restart})
        after = {intake_id: attempt_snapshot(pg, intake_id) for intake_id in ids}
        rec.write("hermes-mount-rows.json", {"before": snapshots, "after": after, "spend_before": spend_rows,
                                             "spend_after": sql_rows(pg, SPEND_ROWS)})
        ok &= rec.step("HERMES-MOUNT: attempt and spend rows are unchanged by the restart and no turn ran",
                       after == snapshots and sql_rows(pg, SPEND_ROWS) == spend_rows and turn_count(workdir) == turns_before,
                       {"turns_before": turns_before, "turns_after": turn_count(workdir)})

        inputs = list((workdir / "turns").glob("turn-*/input.json"))  # an authored script may hold the echo by design
        leaks = find_leaks(workdir, SENTINEL, exclude=[credential, *inputs])
        logs = [p.name for p in (evidence / "logs").glob("api-hermes-mount*.log") if SENTINEL in p.read_text(errors="ignore")]
        stored = SENTINEL in pg.psql("select concat_ws('|', (select string_agg(t::text, '') from interpretation_settlements t), "
                                     "(select string_agg(t::text, '') from usage_local.provider_spend_events t))")
        ok &= rec.step("HERMES-MOUNT: the dummy credential is in no evidence file, log or saved row",
                       leaks == [] and logs == [] and not stored, {"evidence": leaks, "logs": logs, "rows": stored})
    finally:
        if process is not None:
            try:
                process.stop()
            except Exception as error:  # noqa: BLE001
                ok &= rec.step("HERMES-MOUNT: stop the mount API", False, f"{type(error).__name__}: {error}")
    return bool(ok)


def run_hermes_app_mount_phase(rec: Any, pg: harness.Postgres, env: dict[str, str], api_port: int, api_url: str,
                               evidence: Path, run_id: str, ui_env: dict[str, str], token_a: str, token_b: str,
                               run_playwright: Any, current_api: harness.Process, processes: list[Any]) -> bool:
    """Returns whether every step passed. Stops `current_api` and ends by starting the standard API again; every process
    it starts goes into `processes` at once, so the caller's cleanup stops it even when a step raises."""
    ok = True
    image = PinnedHermesImage(run_id, evidence / "hermes-app-mount" / "image")
    image_started = False
    try:
        image_started = True  # before the build: a build that fails late can still leave a tagged image
        tag = image.build()
        current_api.stop()
        ok &= drive_mount(rec, pg, env, api_port, api_url, evidence, run_id, tag, ui_env, token_a, token_b,
                          run_playwright, processes)
    finally:
        if image_started:
            try:
                removal = image.remove()
                rec.write("hermes-mount-image-removal.json", removal)
                ok &= rec.step("HERMES-MOUNT: removed this run's image; no labelled container is left",
                               removal["image_removed"] and not removal["labeled_containers_left"], removal)
            except Exception as error:  # noqa: BLE001
                ok &= rec.step("HERMES-MOUNT: removed this run's image", False, f"{type(error).__name__}: {error}")
        try:
            current_api.stop()  # already stopped when the phase got that far; stopping again is harmless
        except Exception as error:  # noqa: BLE001
            ok &= rec.step("HERMES-MOUNT: stop the earlier API", False, f"{type(error).__name__}: {error}")
        standard = harness.start_api(env, api_port, evidence / "logs", name="api-after-hermes-app-mount",
                                     factory="harness:create_app_fixture", app_dir=harness.P03_DIR)
        processes.append(standard)  # registered before any wait, so a failed wait cannot lose the handle
        harness.wait_http(f"{api_url}/readyz")
    return bool(ok)
