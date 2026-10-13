"""The saved Research path over the Hermes transport mount, with ACTUAL pinned Hermes (commit 54bc5e5) in a no-egress job.

Each model turn runs in a no-network container whose one request goes through the accepted guard and the AUTHORED
transport. Spend goes to the shared PostgreSQL ledger. Requests are counted at the transport's own record and request
files, not from the guard's claim. The credential is a dummy sentinel. Needs Docker; each Hermes process takes seconds.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import harness
from authored_cases import load_case, provider_script
from docker_turn_runner import LABEL, docker
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.research.hermes_transport_mount import AUTHORED_ROUTE, open_transport_mount
from edge_os_api.research.provider_spend_ledger import SpendLimits, TokenPrice
from leak_scan import find_leaks

SENTINEL = "sk-test-DUMMY-SENTINEL-9f3a71c2e8b54d06"
PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
LIMITS = SpendLimits(Decimal("0.20"), Decimal("0.12"), PRICE)
RESERVATION = Decimal("0.054848")  # (12,000 + 64) x 2.00 / 1e6 + 4,096 x 7.50 / 1e6
EXACT_CHARGE = Decimal("0.0074285")  # concrete-thesis reports 1,423 prompt and 611 completion tokens
HOST = Path(__file__).with_name("transport_mount_host.py")
SPEND_TABLES = "usage_local.provider_spend_events, usage_local.provider_spend_reservations, usage_local.provider_spend_settings"


def intake(name: str = "concrete-thesis") -> dict[str, Any]:
    return dict(load_case(name)["intake"])


def requests_sent(evidence: Path, attempt_id: str) -> int:
    """Requests the authored provider received for one attempt, from the job's own request files."""
    return sum(len(list(folder.glob("output/requests/request-*.json"))) for folder in evidence.glob(f"turn-*-{attempt_id}"))


def stored_text(pg: harness.Postgres) -> str:
    """Every saved attempt, settlement, late result, record and spend row, as text."""
    return pg.psql("select concat_ws('|', (select string_agg(t::text, '') from interpretation_attempts t), "
                   "(select string_agg(t::text, '') from interpretation_settlements t), "
                   "(select string_agg(t::text, '') from interpretation_late_results t), "
                   "(select string_agg(t::text, '') from records t), "
                   "(select string_agg(t::text, '') from usage_local.provider_spend_reservations t), "
                   "(select string_agg(t::text, '') from usage_local.provider_spend_events t))")


@pytest.fixture
def spend_reset(pg, migrated):
    pg.psql(f"truncate {SPEND_TABLES}")
    yield
    pg.psql(f"truncate {SPEND_TABLES}")


@pytest.fixture
def credential(tmp_path: Path) -> Path:
    path = tmp_path / "private-credential"
    path.write_text(SENTINEL, encoding="utf-8")
    path.chmod(0o400)
    return path


class InProcess:
    """One application over one mount, in this process. `script(...)` queues what the next jobs' provider does."""

    def __init__(self, env: dict[str, str], image: str, run_id: str, root: Path, credential: Path, **limits: Any) -> None:
        self.queue: list[dict[str, Any]] = []
        self.evidence = root / run_id
        self.settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})
        self.mount = open_transport_mount(self.settings, limits=LIMITS, image=image, run_id=run_id, evidence_dir=self.evidence,
                                          script_for=lambda turn: self.queue.pop(0), credential_file=credential, **limits)
        self.client = TestClient(create_app(self.settings, hermes_runner=self.mount.runner))
        self.client.__enter__()

    def script(self, name: str = "concrete-thesis", **fault: str) -> None:
        self.queue.append({**provider_script(load_case(name)["provider"]), **fault})

    def close(self) -> None:
        self.client.__exit__(None, None, None)
        self.mount.close()


@pytest.fixture
def in_process(env, pinned_hermes_image, run_id, evidence_root, credential, spend_reset, request):
    opened: list[InProcess] = []

    def build(name: str, **limits: Any) -> InProcess:
        app = InProcess(env, pinned_hermes_image, f"{run_id}-{request.node.name[5:30]}-{name}", evidence_root, credential,
                        **limits)
        opened.append(app)
        return app

    yield build
    for app in opened:
        app.close()


def test_a_saved_request_runs_pinned_hermes_once_is_charged_exactly_and_reopens_from_another_application(
        in_process, owner_a, owner_b, pg, evidence_root, credential, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")
    app = in_process("first")
    app.script()

    created = app.client.post("/v1/research/requests", json=intake(), headers=owner_a)

    assert created.status_code == 201, created.text
    [attempt] = created.json()["attempts"]
    attempt_id = attempt["attempt_id"]
    assert (attempt["status"], attempt["parse_result"], attempt["request_count"]) == ("COMPLETED", "ACCEPTED", 1)
    assert attempt["spend"] == {"state": "SETTLED", "charge_usd": str(EXACT_CHARGE)}
    assert created.json()["head"]["interpretation_revision_id"] == attempt["revision_id"] is not None
    observed = json.loads(pg.psql(f"select runtime_observed from interpretation_settlements where attempt_id = '{attempt_id}'"))
    assert (observed["transport_attempt_id"], observed["transport_request_attempt_ids"], observed["transport_route_id"]) == (
        attempt_id, [attempt_id], AUTHORED_ROUTE.route_id)
    [turn] = list(app.evidence.glob(f"turn-*-{attempt_id}"))
    container = json.loads((turn / "output" / "container-result.json").read_text())
    assert [s["attempt_id"] for s in container["transport"]["sent"]] == [attempt_id] and requests_sent(app.evidence, attempt_id) == 1
    assert json.loads((turn / "output" / "requests" / "request-1.json").read_text())["session_id"] == f"p05-{attempt_id}"
    assert container["sandbox"]["network"]["blocked"] is True and container["transport"]["credential_attached"] is True
    assert app.mount.spend.state(attempt_id) == "SETTLED" and app.mount.spend.committed_usd() == EXACT_CHARGE

    reopened = in_process("reopen")  # the browser was closed; another application process serves the reopen
    path = f"/v1/research/requests/{created.json()['intake']['record_id']}"
    again = reopened.client.get(path, headers=owner_a).json()
    assert again["attempts"] == created.json()["attempts"] and again["head"] == created.json()["head"]
    assert reopened.client.get(path, headers=owner_b).status_code == 404
    assert list(reopened.evidence.glob("turn-*")) == []  # reopening made no model call

    scripts = list(evidence_root.glob("**/turn-*/input.json"))  # an authored script may hold the echo by design
    assert find_leaks(evidence_root, SENTINEL, exclude=[credential, *scripts]) == []
    assert SENTINEL not in stored_text(pg) and SENTINEL not in caplog.text


def test_a_lost_reply_is_saved_as_unknown_keeps_the_whole_reservation_and_publishes_nothing(in_process, owner_a) -> None:
    app = in_process("lost")
    app.script(transport_fault="lost_reply")

    bundle = app.client.post("/v1/research/requests", json=intake(), headers=owner_a).json()

    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["parse_result"], attempt["revision_id"]) == ("UNKNOWN", "NOT_PARSED", None)
    assert bundle["head"]["interpretation_revision_id"] is None and attempt["response_sha256"] is None
    assert attempt["spend"] == {"state": "UNKNOWN", "charge_usd": str(RESERVATION)}
    assert requests_sent(app.evidence, attempt["attempt_id"]) == 1  # the provider did the work; the reply was lost
    retried = app.client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/interpretation-retries",
                              headers=owner_a, json={"retry_of": attempt["attempt_id"]})
    assert retried.status_code == 409 and len(list(app.evidence.glob("turn-*"))) == 1  # uncertain work is never replayed


def test_a_hung_provider_is_stopped_at_the_deadline_and_its_reservation_stays(in_process, owner_a) -> None:
    app = in_process("hung", timeout_seconds=12)
    app.script("provider-hang")
    began = time.monotonic()

    bundle = app.client.post("/v1/research/requests", json=intake(), headers=owner_a).json()

    elapsed = time.monotonic() - began
    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["spend"]["state"]) == ("TIMED_OUT", "UNKNOWN")
    [lifecycle] = app.evidence.glob("turn-*/container-lifecycle.json")
    assert json.loads(lifecycle.read_text())["container_absent"] is True
    assert elapsed < 12 + 5 + 10  # D = timeout + seal grace; the rest is HTTP, the database and the settlement
    assert app.mount.spend.committed_usd() == RESERVATION


class Host:
    """One separate API process over its own mount (its own run id), sharing the database and the spend ledger."""

    def __init__(self, env: dict[str, str], image: str, run_id: str, root: Path, credential: Path, limits: SpendLimits,
                 timeout_seconds: float = 90) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root, self.run_id, self.evidence = root, run_id, root / "turns"
        self.script_file, self.report = root / "script.json", root / "report.json"
        if not self.script_file.exists():
            self.script_file.write_text("[]")
        self.args = [harness.api_python(), str(HOST), "--image", image, "--run-id", run_id, "--evidence-dir",
                     str(self.evidence), "--script-file", str(self.script_file), "--credential-file", str(credential),
                     "--report-file", str(self.report), "--global-cap", str(limits.global_cap_usd), "--owner-cap",
                     str(limits.owner_cap_usd), "--timeout-seconds", str(timeout_seconds)]
        self.env = {**env, "EDGE_OS_INTERPRETER": "hermes_local"}
        self.process: harness.Process | None = None
        self.port = 0

    def start(self) -> "Host":
        self.port = harness.free_port()
        handle = open(self.root / "host.log", "ab")
        popen = subprocess.Popen([*self.args, "--port", str(self.port)], cwd=harness.API_DIR, env=self.env, stdout=handle,
                                 stderr=handle, start_new_session=True)
        self.process = harness.Process(self.run_id, popen, self.root / "host.log", handle)
        harness.wait_http(f"{self.url}/readyz", timeout=120)
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def script(self, *items: dict[str, Any]) -> None:
        self.script_file.write_text(json.dumps([*json.loads(self.script_file.read_text()), *items]))

    def post(self, headers: dict[str, str], body: dict[str, Any]) -> httpx.Response:
        return httpx.post(f"{self.url}/v1/research/requests", json=body, headers=headers, timeout=240)

    def get(self, headers: dict[str, str], intake_id: str) -> httpx.Response:
        return httpx.get(f"{self.url}/v1/research/requests/{intake_id}", headers=headers, timeout=60)

    def kill(self) -> None:
        assert self.process is not None
        os.killpg(self.process.popen.pid, signal.SIGKILL)  # no cleanup, no settlement: the process is simply gone
        self.process.popen.wait(timeout=30)
        self.process.stop()

    def stop(self) -> None:
        if self.process is not None:
            self.process.stop()


@pytest.fixture
def hosts(env, pinned_hermes_image, run_id, evidence_root, credential, spend_reset, request):
    started: list[Host] = []

    def build(name: str, limits: SpendLimits = LIMITS, **options: Any) -> Host:
        host = Host(env, pinned_hermes_image, f"{run_id}-{name}", evidence_root / request.node.name[5:40] / name,
                    credential, limits, **options)
        started.append(host)
        return host

    yield build
    for host in started:
        host.stop()
        for name in docker("ps", "-aq", "--filter", f"label={LABEL}={host.run_id}", check=False).stdout.split():
            docker("rm", "-f", name, check=False)  # only this test's own run label


def test_two_api_processes_and_two_owners_never_pass_the_shared_caps_and_send_one_request_per_reservation(
        hosts, owner_a, owner_b, pg, migrated) -> None:
    first, second = hosts("p1").start(), hosts("p2").start()
    lost = {"case": "concrete-thesis", "transport_fault": "lost_reply"}  # each admitted job keeps its full reservation
    for host in (first, second):
        host.script(lost, lost, lost)
    plan = [(first, owner_a), (first, owner_a), (first, owner_b), (second, owner_b), (second, owner_b), (second, owner_a)]
    results: list[httpx.Response | None] = [None] * len(plan)
    barrier = threading.Barrier(len(plan))

    def go(index: int) -> None:
        host, headers = plan[index]
        barrier.wait()
        results[index] = host.post(headers, intake())

    threads = [threading.Thread(target=go, args=(i,)) for i in range(len(plan))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=300)

    attempts = [r.json()["attempts"][0] for r in results if r is not None]
    assert len(attempts) == 6
    granted = [a for a in attempts if a["spend"]["state"] == "UNKNOWN"]
    refused = [a for a in attempts if a["error_class"] == "SpendCapReached"]
    # 0.20 holds three reservations of 0.054848, each owner's 0.12 holds two: three run, three are refused unsent
    assert (len(granted), len(refused)) == (3, 3) and all(a["request_count"] == 0 for a in refused)
    owners = [plan[i][1] for i, r in enumerate(results) if r is not None and r.json()["attempts"][0] in granted]
    assert owners.count(owner_a) <= 2 and owners.count(owner_b) <= 2
    sent = {a["attempt_id"]: requests_sent(host.evidence, a["attempt_id"]) for a in attempts for host in (first, second)
            if list(host.evidence.glob(f"turn-*-{a['attempt_id']}"))}
    assert sorted(sent) == sorted(a["attempt_id"] for a in granted) and set(sent.values()) == {1}
    count, total = pg.psql("select count(*) || '|' || coalesce(sum(reserved_nano_usd), 0) "
                           "from usage_local.provider_spend_reservations").split("|")
    assert (int(count), Decimal(total) / 10**9) == (3, RESERVATION * 3)  # only the granted three hold anything
    scripts = list(first.root.parent.glob("**/turn-*/input.json"))
    assert find_leaks(first.root.parent, SENTINEL, exclude=scripts) == []  # host logs, evidence and reports

def test_a_killed_api_process_restarts_recovers_its_container_within_c_and_keeps_the_unknown_spend(
        hosts, owner_a, pg, migrated) -> None:
    host = hosts("crash", timeout_seconds=240).start()
    host.script({"case": "provider-hang"})
    response: dict[str, Any] = {}
    poster = threading.Thread(target=lambda: response.setdefault("r", _post_quietly(host, owner_a)))
    poster.start()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and not list(host.evidence.glob("turn-*/output/requests/request-1.json")):
        time.sleep(0.5)  # the hung provider has the one admitted request: the job is inside its model work
    assert list(host.evidence.glob("turn-*/output/requests/request-1.json")), "the job never reached the provider"
    [turn] = list(host.evidence.glob("turn-*"))
    attempt_id = turn.name.split("-", 2)[2]
    [container] = docker("ps", "--filter", f"label={LABEL}={host.run_id}", "--format", "{{.Names}}").stdout.split()
    host.kill()
    poster.join(timeout=60)
    assert pg.psql(f"select state from usage_local.provider_spend_reservations where attempt_id = '{attempt_id}'") == "RESERVED"
    assert docker("ps", "-q", "--filter", f"name=^{container}$").stdout.strip()  # the dead process left it running

    restarted = host.start()  # the same run id and evidence folder: its own dead turn is recovered at startup
    report = json.loads(host.report.read_text())
    assert report["startup_recovery"] == [] and not docker("ps", "-aq", "--filter", f"name=^{container}$").stdout.strip()
    intake_id = pg.psql(f"select intake_record_id from interpretation_attempts where attempt_id = '{attempt_id}'")
    [attempt] = restarted.get(owner_a, intake_id).json()["attempts"]
    assert (attempt["attempt_id"], attempt["status"], attempt["spend"]) == (
        attempt_id, "INTERRUPTED", {"state": None, "charge_usd": None})
    assert pg.psql(f"select state from usage_local.provider_spend_reservations where attempt_id = '{attempt_id}'") == "RESERVED"
    retried = httpx.post(f"{restarted.url}/v1/research/requests/{intake_id}/interpretation-retries", headers=owner_a,
                         json={"retry_of": attempt_id}, timeout=60)
    assert retried.status_code == 409  # an interrupted attempt is never replayed
    assert len(list(host.evidence.glob("turn-*"))) == 1 and requests_sent(host.evidence, attempt_id) == 0  # output removed
    host.script({"case": "concrete-thesis"})
    other = restarted.post(owner_a, intake()).json()["attempts"][0]  # another saved request is its own scope
    assert (other["status"], other["spend"]["state"]) == ("COMPLETED", "SETTLED")
    assert len(list(host.evidence.glob("turn-*"))) == 2


def _post_quietly(host: Host, headers: dict[str, str]) -> Any:
    try:
        return host.post(headers, intake())
    except httpx.HTTPError as error:  # the process is killed while this request waits
        return type(error).__name__
