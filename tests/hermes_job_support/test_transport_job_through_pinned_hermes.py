"""ACTUAL pinned Hermes (commit 54bc5e5) sends its one request through the guard and an injected AUTHORED transport.

Each test runs the saved interpretation path (`HermesInterpreter`) over `build_transport_job` in a no-egress container.
The provider is authored, the credential a dummy sentinel, and no network is used. Each test needs Docker and takes
several seconds per Hermes process.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import threading
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from authored_cases import load_case, provider_script
from edge_os_api.research.hermes_interpreter import HermesInterpreter, HermesInterpreterConfig, Interpreted, Unavailable
from edge_os_api.research.interpretation_attempts import AttemptLedger
from leak_scan import find_leaks
from provider_guard import GuardPolicy
from provider_transport import TransportRoute
from spend_ledger import SpendLedger, TokenPrice
from transport_turn_runner import build_transport_job

SENTINEL = "sk-test-DUMMY-SENTINEL-9f3a71c2e8b54d06"
PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
CONFIG = HermesInterpreterConfig(model="fixture-model/1", route="local-authored-transport", max_output_tokens=4096)
POLICY = GuardPolicy(model="fixture-model/1", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500)
ROUTE = TransportRoute("authored-local-1", "AUTHORED", "https://authored-transport.invalid/v1/chat/completions", 65_536)
RESERVATION = Decimal("0.054848")  # (12,000 + 64) x 2.00 / 1e6 + 4,096 x 7.50 / 1e6
EXACT_CHARGE = Decimal("0.0074285")  # the concrete-thesis case reports 1,423 prompt and 611 completion tokens
OWNER, INTAKE = "owner-a-7f3c", "intake-5e21"


class Rig:
    """One interpreter over the transport job, a durable spend ledger and a private dummy credential."""

    def __init__(self, image: str, run_id: str, root: Path, name: str, script: dict[str, Any], *,
                 spend: SpendLedger | None = None, scope: str = "case-a", ids: str = "attempt", timeout_seconds: float = 90) -> None:
        self.root = root / name
        self.root.mkdir(parents=True)
        self.credential = self.root / "private-credential"
        self.credential.write_text(SENTINEL, encoding="utf-8")
        self.credential.chmod(0o400)
        self.evidence = self.root / "evidence"
        self.spend = spend or SpendLedger(self.root / "spend.sqlite", cap_usd=Decimal("0.20"), price=PRICE)
        self.job = build_transport_job(
            ROUTE, policy=POLICY, ledger=self.spend, scope_for=lambda turn: scope, image=image, run_id=run_id,
            evidence_dir=self.evidence, script_for=lambda turn: script, credential_file=self.credential,
            forbidden=[OWNER, INTAKE], timeout_seconds=timeout_seconds)
        from test_interpretation_attempts import MemoryAttemptStore
        self.store = MemoryAttemptStore()
        counter, ticks = itertools.count(1), itertools.count(0)
        self.ledger = AttemptLedger(self.store, new_id=lambda: f"{ids}-{next(counter)}", now=lambda: dt.datetime(
            2026, 10, 12, 12, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=next(ticks)))
        self.interpreter = HermesInterpreter(CONFIG, self.job.runner, self.ledger, monotonic=time.monotonic)

    def run_case(self, name: str = "concrete-thesis"):
        return self.interpreter.interpret(OWNER, INTAKE, load_case(name)["intake"])

    def output(self, turn: int = 1) -> Path:
        [path] = sorted(self.evidence.glob(f"turn-{turn:02d}-*/output"))
        return path

    def container_result(self, turn: int = 1) -> dict[str, Any]:
        return json.loads((self.output(turn) / "container-result.json").read_text())

    def saved(self) -> Any:
        [attempt] = self.ledger.history(OWNER, INTAKE)
        return attempt

    def no_leaks(self) -> bool:
        scripts = list(self.evidence.glob("turn-*/input.json"))  # an authored script may hold the echo by design
        return find_leaks(self.root, SENTINEL, exclude=[self.credential, *scripts]) == []


def case(name: str = "concrete-thesis", **fault: Any) -> dict[str, Any]:
    return {**provider_script(load_case(name)["provider"]), **fault}


def test_one_admitted_request_reaches_the_transport_with_the_host_credential_and_every_identity_is_the_attempt(
        pinned_hermes_image, run_id, evidence_root) -> None:
    rig = Rig(pinned_hermes_image, run_id, evidence_root, "valid", case())

    result = rig.run_case()

    assert isinstance(result, Interpreted) and result.attempt_id == "attempt-1"
    saved, container = rig.saved(), rig.container_result()
    observed = saved.settlement.runtime_observed
    assert (observed["transport_attempt_id"], observed["transport_request_attempt_ids"]) == ("attempt-1", ["attempt-1"])
    assert observed["transport_route_id"] == ROUTE.route_id and observed["spend_state"] == "SETTLED"
    request = json.loads((rig.output() / "requests" / "request-1.json").read_text())
    assert request["session_id"] == "p05-attempt-1"  # the wire body names the same attempt
    assert [event.kind for event in rig.spend.events("attempt-1")] == ["RESERVED", "SETTLED"]
    assert (container["guard"]["admitted_count"], container["guard"]["seen_count"]) == (1, 1)
    assert container["transport"]["credential_attached"] is True  # the host credential, attached by the host request
    assert container["transport"]["sent"] == [{"attempt_id": "attempt-1", "route_id": ROUTE.route_id,
                                               "body_bytes": container["guard"]["evidence"][0]["request_bytes"]}]
    assert saved.settlement.request_count == 1 and rig.spend.committed_usd() == EXACT_CHARGE
    assert container["sandbox"]["network"]["blocked"] is True and container["hermes_source_commit"].startswith("54bc5e5")
    assert rig.no_leaks()


def test_a_request_the_guard_refuses_never_reaches_the_transport_and_frees_its_reservation(
        pinned_hermes_image, run_id, evidence_root) -> None:
    rig = Rig(pinned_hermes_image, run_id, evidence_root, "guard-refused", case())
    rig.job.supervision.policy = replace(POLICY, max_output_tokens=2048)  # the job is told a different output limit

    result = rig.run_case()

    # Hermes raises after the 429, so the accepted mapping saves UNKNOWN; the guard's count of 0 still frees the spend
    assert isinstance(result, Unavailable) and result.reason_code == "outcome_unknown"
    container = rig.container_result()
    assert container["transport"]["sent"] == [] and container["hermes"]["request_count"] == 0
    assert [r["reason"] for r in container["guard"]["evidence"]] == ["output_limit_not_as_configured"]
    assert rig.spend.state("attempt-1") == "RELEASED" and rig.spend.committed_usd() == 0


def test_a_request_that_is_not_the_intended_physical_request_is_refused_before_the_guard_and_the_transport(
        pinned_hermes_image, run_id, evidence_root) -> None:
    rig = Rig(pinned_hermes_image, run_id, evidence_root, "physical-refused", case())
    entry = rig.job.supervision.job_entry
    transport = {**entry.settings["transport"], "client_url": "https://another-client.invalid/v1/chat/completions"}
    rig.job.supervision.job_entry = replace(entry, settings={"transport": transport})

    rig.run_case()

    container = rig.container_result()
    assert container["transport"]["sent"] == [] and container["guard"]["seen_count"] == 0
    assert {r["refusal"] for r in container["transport"]["evidence"]} == {"url_not_as_configured"}
    assert rig.spend.state("attempt-1") == "RELEASED" and rig.spend.committed_usd() == 0


def test_a_lost_reply_publishes_nothing_and_keeps_the_full_reservation(pinned_hermes_image, run_id, evidence_root) -> None:
    rig = Rig(pinned_hermes_image, run_id, evidence_root, "lost-reply", case(transport_fault="lost_reply"))

    result = rig.run_case()

    assert not isinstance(result, Interpreted)
    container = rig.container_result()
    assert container["hermes"]["text"] is None and container["hermes"]["request_count"] == 1
    assert len(container["transport"]["sent"]) == 1  # Hermes' own retry was refused before the transport
    assert (rig.spend.state("attempt-1"), rig.spend.committed_usd()) == ("UNKNOWN", RESERVATION)
    assert rig.saved().settlement.response_text is None and rig.no_leaks()


def test_a_reply_larger_than_the_route_allows_is_dropped_and_keeps_the_full_reservation(
        pinned_hermes_image, run_id, evidence_root) -> None:
    rig = Rig(pinned_hermes_image, run_id, evidence_root, "oversized", case(transport_fault="oversized_reply"))

    result = rig.run_case()

    assert not isinstance(result, Interpreted)
    container = rig.container_result()
    assert "reply_too_large" in container["hermes"]["observed"]["transport_refusals"]
    assert container["hermes"]["text"] is None and container["hermes"]["usage"]["reported"] is False
    assert (rig.spend.state("attempt-1"), rig.spend.committed_usd()) == ("UNKNOWN", RESERVATION)


def test_a_job_that_dies_after_the_provider_worked_is_unknown_and_keeps_the_full_reservation(
        pinned_hermes_image, run_id, evidence_root) -> None:
    rig = Rig(pinned_hermes_image, run_id, evidence_root, "crash", case(transport_fault="crash_after_send"))

    result = rig.run_case()

    assert isinstance(result, Unavailable) and result.reason_code == "outcome_unknown"
    assert rig.saved().settlement.error_class == "ContainerExit"
    assert (rig.spend.state("attempt-1"), rig.spend.committed_usd()) == ("UNKNOWN", RESERVATION)
    assert rig.job.supervision.pending_cleanup() == [] and rig.no_leaks()


def test_missing_usage_keeps_the_full_reservation(pinned_hermes_image, run_id, evidence_root) -> None:
    rig = Rig(pinned_hermes_image, run_id, evidence_root, "no-usage", case("usage-not-reported"))

    rig.run_case("usage-not-reported")

    assert (rig.spend.state("attempt-1"), rig.spend.committed_usd()) == ("UNKNOWN", RESERVATION)


def test_a_hung_provider_is_stopped_by_the_one_deadline_and_stays_liable(pinned_hermes_image, run_id, evidence_root) -> None:
    rig = Rig(pinned_hermes_image, run_id, evidence_root, "hang", case("provider-hang"), timeout_seconds=12)
    plans = []
    original = rig.job.supervision._plan
    rig.job.supervision._plan = lambda: plans.append(original()) or plans[-1]  # observe D; the plan itself is unchanged

    result = rig.run_case("provider-hang")
    returned = time.monotonic()

    assert isinstance(result, Unavailable) and result.reason_code == "timed_out"
    [lifecycle] = rig.evidence.glob("turn-01-*/container-lifecycle.json")
    assert json.loads(lifecycle.read_text())["container_absent"] is True
    assert (rig.spend.state("attempt-1"), rig.spend.committed_usd()) == ("UNKNOWN", RESERVATION)
    # D was made once (12 s + 5 s grace) and never renewed; the ledger commit after the runner is outside it
    (rig.root / "deadline.json").write_text(json.dumps({"late_seconds": returned - plans[0].deadline}))
    assert returned - plans[0].deadline < 1.0


def test_two_independent_tasks_at_the_same_time_keep_their_own_identities_and_charges(
        pinned_hermes_image, run_id, evidence_root) -> None:
    spend = SpendLedger(evidence_root / "shared-spend.sqlite", cap_usd=Decimal("0.20"), price=PRICE)
    rigs = [Rig(pinned_hermes_image, f"{run_id}-{name}", evidence_root, f"parallel-{name}", case(), spend=spend,
                scope=f"case-{name}", ids=f"attempt-{name}") for name in ("a", "b")]
    results: dict[int, Any] = {}
    threads = [threading.Thread(target=lambda i=i: results.__setitem__(i, rigs[i].run_case())) for i in range(2)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=180)

    assert [type(results[i]).__name__ for i in range(2)] == ["Interpreted", "Interpreted"]
    for rig, name in zip(rigs, ("a", "b")):
        observed = rig.saved().settlement.runtime_observed
        assert observed["transport_request_attempt_ids"] == [f"attempt-{name}-1"]
        assert json.loads((rig.output() / "requests" / "request-1.json").read_text())["session_id"] == f"p05-attempt-{name}-1"
        assert spend.state(f"attempt-{name}-1") == "SETTLED"
    assert spend.committed_usd() == 2 * EXACT_CHARGE


def test_after_the_host_dies_mid_turn_recovery_stops_its_own_container_and_the_unknown_spend_stays_and_blocks(
        pinned_hermes_image, run_id, evidence_root, request) -> None:
    import os
    import signal
    import subprocess
    import sys

    from docker_turn_runner import docker
    from edge_os_api.research.hermes_interpreter import HermesTurn
    from transport_turn_runner import build_transport_job as build

    root = evidence_root / "host-died"
    root.mkdir()
    credential, evidence, spend_path = root / "private-credential", root / "evidence", root / "spend.sqlite"
    credential.write_text(SENTINEL)
    dead_run = f"{run_id}-dead"

    def remove_own_leftover() -> None:  # only if the test fails early: the dead run's container, by name AND label
        names = docker("ps", "-aq", "--filter", f"name=^p05-{dead_run}-", "--filter",
                       f"label=edge-os.test.run={dead_run}", check=False).stdout.split()
        for name in names:
            docker("rm", "-f", name, check=False)

    request.addfinalizer(remove_own_leftover)
    here = Path(__file__).resolve().parent
    paths = [str(here.parents[1] / "apps" / "api" / "src"), str(here.parents[1] / "scripts" / "hermes_interpretation"),
             str(here.parents[1] / "scripts" / "hermes_job_support")]
    host = subprocess.Popen([sys.executable, str(here / "hung_turn_host.py"), pinned_hermes_image, dead_run, str(evidence),
                             str(spend_path), str(credential)], env={**os.environ, "PYTHONPATH": os.pathsep.join(paths)})
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not list(evidence.glob("turn-01-*/output/requests/request-1.json")):
            time.sleep(0.5)  # the hung provider has the one admitted request: the job is inside its model work
        assert list(evidence.glob("turn-01-*/output/requests/request-1.json")), "the job never reached the provider"
    finally:
        host.send_signal(signal.SIGKILL)  # no cleanup, no settlement: the host is simply gone
        host.wait()
    [container] = docker("ps", "--filter", f"name=^p05-{dead_run}-", "--format", "{{.Names}}").stdout.split()
    spend = SpendLedger(spend_path, cap_usd=Decimal("0.20"), price=PRICE)
    assert (spend.state("attempt-dead-1"), spend.committed_usd()) == ("RESERVED", RESERVATION)

    def restarted(run: str, scope: str) -> Any:
        return build(ROUTE, policy=POLICY, ledger=spend, scope_for=lambda turn: scope, image=pinned_hermes_image,
                     run_id=run, evidence_dir=evidence, credential_file=credential, script_for=lambda turn: case())

    other_owner = restarted(f"{run_id}-other", "case-other")
    other_owner.supervision.recover_pending(10.0)  # another run's recovery: never this run's record or container
    assert docker("ps", "-q", "--filter", f"name=^{container}$").stdout.strip()

    same = restarted(dead_run, "case-a")
    [pending] = same.supervision.pending_cleanup()
    assert (pending["container"], pending["state"]) == (container, "running")  # the dead turn's identity survived
    left = same.supervision.recover_pending(30.0)  # one supervised pass, one budget C

    assert left == [] and not docker("ps", "-aq", "--filter", f"name=^{container}$").stdout.strip()
    assert [u.attempt_id for u in spend.unresolved()] == ["attempt-dead-1"]  # a kill proves no zero charge
    turn = HermesTurn("attempt-next-1", "prompt", "task", "fixture-model/1", "local", 4096)
    blocked = same.runner.run_turn(turn)  # the same scope: refused before any job starts
    assert blocked.error_class == "SpendScopeBlocked" and len(list(evidence.glob("turn-*"))) == 1
    assert spend.committed_usd() == RESERVATION and find_leaks(root, SENTINEL, exclude=[credential]) == []
