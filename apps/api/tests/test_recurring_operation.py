"""P27 LOCAL recurring operation through mounted routes, the producer and the existing job engine.

Seams: authenticated deployment routes → durable deployment → producer pass (tick, receipt reconciliation, worker)
→ saved jobs, outcomes, decisions, intents, attempts and fixture effects → the durable projection. Every pass runs
with no browser or HTTP caller. Expected values come from the authored fixture constants (revision sizing 100
quote units, authored price 2 quote per base, rising prices while flat and falling prices while a position is
open), never from the code under test. The module has its own database in the session container, so the
separate-process producers and the downgrade check touch nothing another module owns.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import os
import subprocess
import sys
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

import financial_flows as ff
import harness
from edge_os_api.core.provider_ports import MarketObservations, ProviderUnavailable
from edge_os_api.core.settings import load_settings
from edge_os_api.execution.models import (DecisionRow, EvaluationJobRow, EvaluationOutcomeRow, IntentRow,
                                          RecurringDeploymentRow)
from edge_os_api.execution.recurring_producer import ClockOffsetRefused, producer_clock
from edge_os_api.execution.recurring_scheduler import RecurringOperation
from edge_os_api.execution.worker import ConnectedExecution, decision_slot
from edge_os_api.main import create_app

SLOT = dt.timedelta(minutes=5)


@pytest.fixture(scope="module")
def env(pg, signer):
    name = f"{pg.database}_recurring_{uuid.uuid4().hex[:6]}"
    pg.psql(f"create database {name}", db="postgres")
    url = make_url(pg.url).set(database=name).render_as_string(hide_password=False)
    try:
        yield harness.api_env(database_url=url, public_pem=signer.public_pem, previous_pem=None,
                              cors=["http://127.0.0.1:3999"])
    finally:
        pg.psql(f"drop database if exists {name} with (force)", db="postgres")


@pytest.fixture(scope="module")
def migrated(env):
    result = harness.migrate(env)
    assert result.returncode == 0, result.stderr
    return env


@pytest.fixture(scope="module")
def settings(env, migrated):
    return load_settings(env)


@pytest.fixture
def journey(settings, tmp_path):
    with ff.fixture_client(settings, tmp_path / "effects.jsonl") as client:
        # One fixed anchor per test, mid-slot, so shifted producer moments never straddle a real slot boundary.
        client.producer_base = decision_slot(dt.datetime.now(dt.timezone.utc)) + dt.timedelta(seconds=150)
        yield client


# ------------------------------------------------------------------------------------------------ helpers

def ready(client: TestClient, headers: dict[str, str], agent: str, **terms: Any) -> dict[str, Any]:
    confirmed = ff.confirmed_agent(client, headers, agent)
    declaration = ff.funded(client, headers, agent)
    consent = ff.adopted(client, headers, agent, declaration, **terms)
    return {**confirmed, "declaration": declaration, "consent": consent}


def activate(client: TestClient, headers: dict[str, str], agent: str, consent_hash: str, key: str = "activate"):
    return client.post(f"/v1/agents/{agent}/deployment", headers=headers,
                       json={"request_key": key, "expected_consent_hash": consent_hash})


def deployed(client: TestClient, headers: dict[str, str], agent: str, **terms: Any) -> dict[str, Any]:
    state = ready(client, headers, agent, **terms)
    response = activate(client, headers, agent, state["consent"]["consent_hash"])
    assert response.status_code == 201, response.text
    return {**state, "deployment": response.json()}


@contextlib.contextmanager
def at(client: TestClient, minutes: float):
    """The producer and its worker pass run `minutes` after now. The browser and HTTP callers are absent."""
    financial = client.app.state.financial
    connected, recurring = financial.connected, financial.recurring
    saved = connected._clock, recurring._clock
    shifted = lambda: client.producer_base + dt.timedelta(minutes=minutes)  # noqa: E731 - one fixed moment
    connected._clock = recurring._clock = shifted
    try:
        yield shifted
    finally:
        connected._clock, recurring._clock = saved


def produce(client: TestClient, deployment: dict[str, Any], minutes: float) -> list[dict[str, Any]]:
    with at(client, minutes):
        return client.app.state.financial.recurring.producer_pass(only=[uuid.UUID(deployment["deployment_id"])])


def produce_restarted(client: TestClient, deployment: dict[str, Any], minutes: float) -> list[dict[str, Any]]:
    """A pass by a new producer: fresh objects over the same saved state and ports, nothing carried in memory."""
    financial = client.app.state.financial
    with at(client, minutes) as clock:
        connected = ConnectedExecution(client.app.state.session_factory, financial, financial.ports,
                                       qualification=financial.ports.mode, clock=clock)
        restarted = RecurringOperation(client.app.state.session_factory, financial, connected, clock=clock)
        return restarted.producer_pass(only=[uuid.UUID(deployment["deployment_id"])])


def projection(client: TestClient, headers: dict[str, str], agent: str) -> dict[str, Any]:
    response = client.get(f"/v1/agents/{agent}/deployment", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def occurrences(client: TestClient, deployment: dict[str, Any]) -> list[EvaluationJobRow]:
    with client.app.state.session_factory() as session:
        return list(session.execute(select(EvaluationJobRow).where(
            EvaluationJobRow.deployment_id == uuid.UUID(deployment["deployment_id"]))
            .order_by(EvaluationJobRow.decision_slot)).scalars().all())


def outcome_rows(client: TestClient, deployment: dict[str, Any]) -> list[EvaluationOutcomeRow]:
    with client.app.state.session_factory() as session:
        return list(session.execute(select(EvaluationOutcomeRow).where(
            EvaluationOutcomeRow.deployment_id == uuid.UUID(deployment["deployment_id"]))
            .order_by(EvaluationOutcomeRow.decision_slot)).scalars().all())


def operations(client: TestClient, headers: dict[str, str], jobs: list[EvaluationJobRow]) -> list[str | None]:
    result = []
    for job in jobs:
        if job.action_id is None:
            result.append(None)
        else:
            result.append(client.get(f"/v1/actions/{job.action_id}", headers=headers).json()["operation"])
    return result


# ------------------------------------------------------------------------------------------- activation

def test_activation_binds_the_exact_adopted_consent_once(journey, owner_a, owner_b):
    agent = "rec-activate"
    state = ready(journey, owner_a, agent)
    consent_hash = state["consent"]["consent_hash"]
    wrong = activate(journey, owner_a, agent, "sha256:" + "0" * 64)
    assert (wrong.status_code, wrong.json()["code"]) == (409, "deployment_consent_mismatch")
    first = activate(journey, owner_a, agent, consent_hash, key="one")
    assert first.status_code == 201, first.text
    again = activate(journey, owner_a, agent, consent_hash, key="one")
    other = activate(journey, owner_a, agent, consent_hash, key="two")
    assert again.status_code == 200 and other.status_code == 200
    assert first.json()["deployment_id"] == again.json()["deployment_id"] == other.json()["deployment_id"]
    identity = first.json()["identity"]
    assert identity["consent_adoption_id"] == state["consent"]["adoption_id"]
    assert identity["consent_hash"] == consent_hash and identity["wallet_id"] == state["wallet_id"]
    assert identity["publication_revision_id"] == state["revision_id"]
    with journey.app.state.session_factory() as session:
        assert session.execute(select(RecurringDeploymentRow).where(
            RecurringDeploymentRow.agent_id == agent)).scalars().all().__len__() == 1
    # Another owner can neither read nor activate this agent.
    assert journey.get(f"/v1/agents/{agent}/deployment", headers=owner_b).status_code == 404
    assert activate(journey, owner_b, agent, consent_hash).status_code == 409
    # Activation alone creates no work: only a producer pass saves an occurrence.
    assert occurrences(journey, first.json()) == []
    assert projection(journey, owner_a, agent)["wait_reason"] == "PRODUCER_NOT_SEEN"


def test_unavailable_execution_mode_refuses_activation(settings, owner_a):
    unavailable = settings.model_copy(update={"wallet_provider": "fixture", "execution_mode": "unavailable"})
    with TestClient(create_app(unavailable)) as client:
        agent = "rec-unavailable"
        ff.confirmed_agent(client, owner_a, agent)
        declaration = ff.funded(client, owner_a, agent)
        adopt = ff.adopted(client, owner_a, agent, declaration)
        refused = activate(client, owner_a, agent, adopt["consent_hash"])
        assert (refused.status_code, refused.json()["code"]) == (503, "activation_unavailable")
        assert projection(client, owner_a, agent) == {"deployment": None}


# --------------------------------------------------------------------------------------- recurrence

def test_repeated_slots_run_entry_full_exit_and_re_entry_without_any_caller(journey, owner_a):
    agent = "rec-cycle"
    state = deployed(journey, owner_a, agent)
    for minutes in (0, 5, 10):
        produce(journey, state["deployment"], minutes)
    jobs = occurrences(journey, state["deployment"])
    assert [job.outcome for job in jobs] == ["SUBMITTED_CONFIRMED"] * 3
    assert [job.decision_slot for job in jobs][1] - jobs[0].decision_slot == SLOT
    assert operations(journey, owner_a, jobs) == ["ENTRY", "EXIT", "ENTRY"]
    assert len(ff.effects(journey)) == 3
    positions = journey.get(f"/v1/agents/{agent}/actions", headers=owner_a).json()["positions"]
    assert sorted(position["inventory_raw"] for position in positions) == ["0", ff.ENTRY_BASE_OUTPUT]
    outcomes = outcome_rows(journey, state["deployment"])
    assert [row.outcome for row in outcomes] == ["SIGNAL"] * 3
    for row, job in zip(outcomes, jobs):
        assert row.inputs_observed_at == job.decision_slot and row.inputs_collected_at == job.decision_slot
        assert row.decision_id == job.decision_id and row.evaluated_at >= row.inputs_collected_at
        assert row.provenance["evidence_class"] == "SYNTHETIC_FIXTURE"


def test_duplicate_ticks_and_passes_in_one_slot_create_one_occurrence_and_one_effect(journey, owner_a):
    state = deployed(journey, owner_a, "rec-duplicate")
    recurring = journey.app.state.financial.recurring
    with at(journey, 0):
        only = [uuid.UUID(state["deployment"]["deployment_id"])]
        first, second = recurring.tick(only), recurring.tick(only)
        recurring.producer_pass(only)
        recurring.producer_pass(only)
    assert first[0]["created"] is True and second[0]["created"] is False
    assert len(occurrences(journey, state["deployment"])) == 1
    assert len(ff.effects(journey)) == 1
    assert projection(journey, owner_a, "rec-duplicate")["producer"]["occurrences"] == 1


def test_a_manual_run_and_the_producer_share_one_job_for_one_slot(journey, owner_a):
    agent = "rec-manual"
    state = deployed(journey, owner_a, agent)
    with at(journey, 0):
        manual = ff.schedule(journey, owner_a, agent, "manual").json()
        journey.app.state.financial.recurring.producer_pass(only=[uuid.UUID(state["deployment"]["deployment_id"])])
        ff.run_job(journey, manual)
    assert occurrences(journey, state["deployment"]) == []  # the slot's one job is the manual one
    assert len(ff.effects(journey)) == 1
    assert projection(journey, owner_a, agent)["producer"]["cursor_slot"] is not None


def test_the_producer_leaves_manual_evaluations_to_the_bounded_worker(journey, owner_a):
    ready(journey, owner_a, "rec-manual-only")
    with at(journey, 0):
        manual = ff.schedule(journey, owner_a, "rec-manual-only", "manual").json()
        journey.app.state.financial.recurring.producer_pass()  # an unscoped pass, as the producer process runs
    with journey.app.state.session_factory() as session:
        job = session.get(EvaluationJobRow, uuid.UUID(manual["job_id"]))
    assert (job.state, job.runs, job.deployment_id) == ("QUEUED", 0, None)


def test_missed_slots_are_counted_and_never_replayed(journey, owner_a):
    agent = "rec-missed"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    produce(journey, state["deployment"], 20)  # the producer was absent for three slots
    jobs = occurrences(journey, state["deployment"])
    assert len(jobs) == 2 and jobs[1].decision_slot - jobs[0].decision_slot == 4 * SLOT
    producer = projection(journey, owner_a, agent)["producer"]
    assert producer["missed_slots"] == 3
    [interval] = producer["missed_intervals"]
    assert interval["count"] == 3
    assert interval["from"] == (jobs[0].decision_slot + SLOT).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert interval["to"] == (jobs[1].decision_slot - SLOT).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert len(ff.effects(journey)) == 2  # one per produced occurrence (entry, then exit); none for missed slots


def test_a_restarted_producer_resumes_from_the_saved_cursor(journey, owner_a, settings):
    state = deployed(journey, owner_a, "rec-restart")
    produce(journey, state["deployment"], 0)
    financial = journey.app.state.financial
    with at(journey, 0) as clock:  # a new producer process: fresh objects over the same saved state
        connected = ConnectedExecution(journey.app.state.session_factory, financial, financial.ports,
                                       qualification=financial.ports.mode, clock=clock)
        restarted = RecurringOperation(journey.app.state.session_factory, financial, connected, clock=clock)
        assert restarted.producer_pass(only=[uuid.UUID(state["deployment"]["deployment_id"])])[0]["created"] is False
    produce(journey, state["deployment"], 5)
    assert len(occurrences(journey, state["deployment"])) == 2 and len(ff.effects(journey)) == 2


@pytest.mark.parametrize("change,reason", [
    ({"evidence_class": "RECORDED_RESPONSE"}, "OBSERVATIONS_NOT_FORWARD"),
    ({"finality": None}, "OBSERVATIONS_PROVENANCE_INCOMPLETE"),
    ({"collected_at": "2000-01-01T00:00:00+00:00"}, "OBSERVATIONS_STALE"),
    ({"market_binding_id": "other-market"}, "OBSERVATIONS_WRONG_MARKET"),
    ("wrong-time", "OBSERVATIONS_WRONG_TIME"),
    (None, "OBSERVATIONS_UNAVAILABLE")])
def test_unusable_observations_save_an_unavailable_outcome_and_no_intent(journey, owner_a, change, reason):
    agent = f"rec-obs-{uuid.uuid4().hex[:6]}"
    state = deployed(journey, owner_a, agent)
    market = journey.app.state.financial.ports.market
    real = market.observe

    def altered(request):
        if change is None:
            raise ProviderUnavailable("observations")
        if change == "wrong-time":  # observations for the previous slot, answered for this one
            return real(dataclasses.replace(request, decision_time=request.decision_time - SLOT))
        observed = real(request)
        return MarketObservations(inputs=observed.inputs, provenance={**observed.provenance, **change})

    market.observe = altered
    try:
        produce(journey, state["deployment"], 0)
    finally:
        market.observe = real
    [job] = occurrences(journey, state["deployment"])
    assert (job.state, job.outcome, job.reason, job.decision_id, job.action_id) == (
        "UNAVAILABLE", "UNAVAILABLE", reason, None, None)
    [row] = outcome_rows(journey, state["deployment"])
    assert (row.outcome, row.reason, row.decision_id) == ("UNAVAILABLE", reason, None)
    with journey.app.state.session_factory() as session:
        assert session.execute(select(DecisionRow).where(DecisionRow.agent_id == agent)).first() is None
    assert ff.effects(journey) == []


def test_a_late_evaluation_of_an_earlier_slot_is_stale_and_creates_no_intent(journey, owner_a):
    state = deployed(journey, owner_a, "rec-late")
    recurring = journey.app.state.financial.recurring
    with at(journey, 0):
        recurring.tick([uuid.UUID(state["deployment"]["deployment_id"])])  # saved, then no worker ran in its slot
    [job] = occurrences(journey, state["deployment"])
    with at(journey, 6):
        ff.run_job(journey, {"job_id": str(job.job_id)})
    [job] = occurrences(journey, state["deployment"])
    assert (job.outcome, job.reason) == ("UNAVAILABLE", "OBSERVATIONS_STALE")
    assert ff.effects(journey) == []


@pytest.mark.parametrize("terms,reason", [({"quote_cap": "200000000"}, "CAPACITY_UNAVAILABLE"),
                                          ({"attempts": 2}, "ATTEMPT_BUDGET_EXHAUSTED")])
def test_cumulative_limits_stop_later_entries_and_survive_a_restart(journey, owner_a, terms, reason):
    agent = f"rec-limit-{uuid.uuid4().hex[:6]}"
    state = deployed(journey, owner_a, agent, **terms)
    produced = {"quote_cap": 4, "attempts": 2}[next(iter(terms))]  # actions the cumulative limit allows
    for minutes in range(0, 5 * (produced + 1), 5):
        produce(journey, state["deployment"], minutes)
    jobs = occurrences(journey, state["deployment"])
    assert [job.outcome for job in jobs[:produced]] == ["SUBMITTED_CONFIRMED"] * produced
    denied = jobs[produced]
    assert denied.outcome == "ADMISSION_DENIED" and denied.action_id is not None
    assert denied.reason == reason
    assert len(ff.effects(journey)) == produced
    # A new producer (a restart) does not reset the counters: the next entry is denied again.
    produce_restarted(journey, state["deployment"], 5 * (produced + 2))
    assert occurrences(journey, state["deployment"])[-1].outcome == "ADMISSION_DENIED"
    assert len(ff.effects(journey)) == produced


def test_consent_expiry_ends_the_deployment_before_any_later_occurrence(journey, owner_a):
    expiry = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = deployed(journey, owner_a, "rec-expiry", expiry=expiry)
    produce(journey, state["deployment"], 0)
    produce(journey, state["deployment"], 2 * 24 * 60)
    view = projection(journey, owner_a, "rec-expiry")
    assert (view["deployment"]["state"], view["deployment"]["end_reason"]) == ("ENDED", "CONSENT_EXPIRED")
    assert view["producer"]["next_due_slot"] is None and view["wait_reason"] == "ENDED:CONSENT_EXPIRED"
    assert len(occurrences(journey, state["deployment"])) == 1 and len(ff.effects(journey)) == 1


def test_an_unknown_original_waits_for_its_receipt_then_later_occurrences_trade(journey, owner_a):
    agent = "rec-fx-lost-ack"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    [first] = occurrences(journey, state["deployment"])
    assert (first.state, first.outcome) == ("SUBMITTED", "SUBMITTED_UNKNOWN")
    view = projection(journey, owner_a, agent)
    assert view["pending_reconciliation"] == [first.action_id] and view["wait_reason"] == "WAITING_RECONCILIATION"
    receipts = journey.app.state.financial.ports.receipts
    real = receipts.observe
    receipts.observe = lambda **kwargs: (_ for _ in ()).throw(ProviderUnavailable("receipt"))
    try:
        results = produce(journey, state["deployment"], 5)
    finally:
        receipts.observe = real
    assert {"action_id": first.action_id, "waiting": "receipt_unavailable"} in results
    assert len(ff.effects(journey)) == 1  # the claim kept the later occurrence from any effect
    produce(journey, state["deployment"], 10)  # the receipt is back: the original settles from it first
    action = journey.get(f"/v1/actions/{first.action_id}", headers=owner_a).json()
    assert action["recovery"]["state"] == "CONFIRMED"
    assert [receipt["outcome"] for receipt in action["receipts"]].count("CONFIRMED") == 1
    effects = ff.effects(journey)
    assert len({effect.action_id for effect in effects}) == len(effects)  # one effect per action, none repeated
    assert first.action_id in {effect.action_id for effect in effects}


def test_another_owners_unknown_action_does_not_block_this_deployment(journey, owner_a, owner_b):
    other = deployed(journey, owner_b, "rec-other-fx-lost-ack")
    mine = deployed(journey, owner_a, "rec-mine")
    produce(journey, other["deployment"], 0)
    produce(journey, mine["deployment"], 0)
    assert occurrences(journey, other["deployment"])[0].outcome == "SUBMITTED_UNKNOWN"
    assert occurrences(journey, mine["deployment"])[0].outcome == "SUBMITTED_CONFIRMED"
    assert projection(journey, owner_a, "rec-mine")["pending_reconciliation"] == []


def test_stop_new_entries_allows_the_exit_denies_later_entries_and_survives_a_restart(journey, owner_a):
    agent = "rec-stop"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    stop = journey.post(f"/v1/agents/{agent}/stops", headers=owner_a,
                        json={"mode": "STOP_NEW_ENTRIES", "scope": "AGENT_WALLET_NETWORK"})
    assert stop.status_code == 200, stop.text
    produce(journey, state["deployment"], 5)
    produce(journey, state["deployment"], 10)
    jobs = occurrences(journey, state["deployment"])
    assert operations(journey, owner_a, jobs) == ["ENTRY", "EXIT", "ENTRY"]
    assert [job.outcome for job in jobs] == ["SUBMITTED_CONFIRMED", "SUBMITTED_CONFIRMED", "ADMISSION_DENIED"]
    assert jobs[2].reason == "STOPPED_NEW_ENTRIES"
    produce_restarted(journey, state["deployment"], 15)  # a new producer: the stop is still saved and still denies
    assert occurrences(journey, state["deployment"])[-1].outcome == "ADMISSION_DENIED"
    assert len(ff.effects(journey)) == 2
    assert projection(journey, owner_a, agent)["wait_reason"] == "STOPPED:STOP_NEW_ENTRIES"


def test_removal_ends_the_deployment_and_keeps_residual_holdings_and_reads(journey, owner_a):
    agent = "rec-removal"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    removal = journey.post(f"/v1/agents/{agent}/removal", headers=owner_a,
                           json={"request_key": "remove", "reason": "owner removes the agent"})
    assert removal.status_code == 200, removal.text
    produce(journey, state["deployment"], 5)
    view = projection(journey, owner_a, agent)
    assert (view["deployment"]["state"], view["deployment"]["end_reason"]) == ("ENDED", "REMOVAL_REQUESTED")
    assert len(occurrences(journey, state["deployment"])) == 1 and len(ff.effects(journey)) == 1
    positions = journey.get(f"/v1/agents/{agent}/actions", headers=owner_a).json()["positions"]
    assert [position["inventory_raw"] for position in positions] == [ff.ENTRY_BASE_OUTPUT]
    assert activate(journey, owner_a, agent, state["consent"]["consent_hash"], key="again").json()["code"] == \
        "deployment_ended"


def test_the_owner_ends_recurring_operation_and_it_does_not_restart_on_the_same_terms(journey, owner_a):
    agent = "rec-end"
    state = deployed(journey, owner_a, agent)
    ended = journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a)
    assert (ended.status_code, ended.json()["state"], ended.json()["end_reason"]) == (200, "ENDED", "OWNER_ENDED")
    produce(journey, state["deployment"], 0)
    assert occurrences(journey, state["deployment"]) == []
    again = activate(journey, owner_a, agent, state["consent"]["consent_hash"], key="again")
    assert (again.status_code, again.json()["code"]) == (409, "deployment_ended")
    # The accepted consent rules allow one review per agent and revision, so new terms need a new agent setup.
    changed = journey.post(f"/v1/agents/{agent}/consent/review", headers=owner_a,
                           json={"terms": ff.connected_terms(state["declaration"], attempts=6)})
    assert (changed.status_code, changed.json()["code"]) == (409, "changed_review")
    assert projection(journey, owner_a, agent)["wait_reason"] == "ENDED:OWNER_ENDED"


def test_the_projection_matches_the_saved_rows(journey, owner_a):
    agent = "rec-projection"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    produce(journey, state["deployment"], 5)
    jobs = occurrences(journey, state["deployment"])
    with at(journey, 5):
        view = projection(journey, owner_a, agent)
    producer = view["producer"]
    assert producer["cursor_slot"] == jobs[-1].decision_slot.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert producer["next_due_slot"] == (jobs[-1].decision_slot + SLOT).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert producer["occurrences"] == 2 and producer["missed_slots"] == 0 and view["wait_reason"] is None
    shown = view["occurrences"]
    assert [item["job_id"] for item in shown] == [str(job.job_id) for job in reversed(jobs)]
    for item in shown:
        assert item["evaluation"]["outcome"] == "SIGNAL"
        assert item["evaluation"]["inputs_observed_at"] == item["decision_slot"].replace("+00:00", "Z")
        assert item["submission"]["state"] == "TERMINAL" and item["submission"]["completed_at"] is not None
    assert view["deployment"]["identity"]["consent_hash"] == state["consent"]["consent_hash"]


# ------------------------------------------------------------------------------- processes and schema

def producer_env(env: dict[str, str], effects: str, offset: float = 0) -> dict[str, str]:
    return {**env, "EDGE_OS_WALLET_PROVIDER": "fixture", "EDGE_OS_EXECUTION_MODE": "fixture",
            "EDGE_OS_FIXTURE_EFFECTS_PATH": effects}


def test_two_producer_processes_in_one_slot_save_one_occurrence(journey, owner_a, env, tmp_path):
    state = deployed(journey, owner_a, "rec-contention")
    effects = str(tmp_path / "effects.jsonl")  # the same authored effect record as the journey app
    command = [sys.executable, "-m", "edge_os_api.execution.recurring_producer", "--once"]
    procs = [subprocess.Popen(command, cwd=harness.API_DIR, env=producer_env(env, effects),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT) for _ in range(2)]
    codes = [proc.wait(timeout=180) for proc in procs]
    assert codes == [0, 0], [proc.stdout.read().decode()[-800:] for proc in procs]
    jobs = occurrences(journey, state["deployment"])
    # One occurrence per slot. Both processes read the real clock, so a run that crosses a slot boundary may save
    # the next slot too, but never a second job for one slot or a second effect for one action.
    assert 1 <= len(jobs) <= 2 and len({job.decision_slot for job in jobs}) == len(jobs)
    assert jobs[0].outcome == "SUBMITTED_CONFIRMED"
    for job in jobs:
        assert [effect.action_id for effect in ff.effects(journey)].count(job.action_id) <= 1


def test_the_persistent_producer_runs_bounded_passes_then_exits(journey, owner_a, env, tmp_path):
    state = deployed(journey, owner_a, "rec-loop")
    command = [sys.executable, "-m", "edge_os_api.execution.recurring_producer", "--interval", "0.2",
               "--max-passes", "3"]
    result = subprocess.run(command, cwd=harness.API_DIR, env=producer_env(env, str(tmp_path / "effects.jsonl")),
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-800:]
    assert result.stderr.count("recurring producer pass") == 3
    jobs = occurrences(journey, state["deployment"])
    assert 1 <= len(jobs) <= 2 and len({job.decision_slot for job in jobs}) == len(jobs)  # see the contention test


def test_a_clock_offset_is_refused_outside_local_fixture_mode(settings, env):
    with pytest.raises(ClockOffsetRefused):
        producer_clock(settings.model_copy(update={"execution_mode": "unavailable"}), 5)
    assert producer_clock(settings.model_copy(update={"execution_mode": "fixture"}), 0)() is not None
    result = subprocess.run([sys.executable, "-m", "edge_os_api.execution.recurring_producer", "--once",
                             "--clock-offset-minutes", "5"], cwd=harness.API_DIR,
                            env={**env, "EDGE_OS_EXECUTION_MODE": "unavailable"}, capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 2 and "refused" in result.stderr


def test_a_downgrade_below_0012_is_refused_while_deployments_exist(journey, owner_a, migrated):
    deployed(journey, owner_a, "rec-downgrade")
    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "0011"], cwd=harness.API_DIR, env=migrated,
                          capture_output=True, text=True, timeout=180)
    assert down.returncode != 0 and "downgrade below 0012 refused" in down.stdout + down.stderr
    assert journey.get("/readyz").json()["status"] == "ready"


def test_the_due_slot_is_the_five_minute_grid_point():
    moment = dt.datetime(2026, 10, 13, 9, 44, 59, tzinfo=dt.timezone.utc)
    assert decision_slot(moment) == dt.datetime(2026, 10, 13, 9, 40, tzinfo=dt.timezone.utc)


# ------------------------------------------------------------------------------------ repair round 1

def test_slots_missed_between_activation_and_the_first_pass_are_counted(journey, owner_a):
    agent = "rec-first-gap"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 20)  # no producer ran in the activation slot or the three after it
    [job] = occurrences(journey, state["deployment"])
    activated = dt.datetime.fromisoformat(state["deployment"]["activated_at"].replace("Z", "+00:00"))
    expected = int((job.decision_slot - decision_slot(activated)) / SLOT)
    producer = projection(journey, owner_a, agent)["producer"]
    assert expected >= 1 and producer["missed_slots"] == expected
    [interval] = producer["missed_intervals"]
    assert (interval["count"], interval["reason"]) == (expected, "PRODUCER_ABSENT")
    assert interval["from"] == decision_slot(activated).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_bounded_ticks_rotate_through_every_deployment(journey, owner_a):
    ids = [uuid.UUID(deployed(journey, owner_a, f"rec-fair-{index}")["deployment"]["deployment_id"])
           for index in range(3)]
    recurring = journey.app.state.financial.recurring
    with at(journey, 0):
        first = recurring.tick(ids, limit=2)
        second = recurring.tick(ids, limit=2)
    ticked = {item["deployment_id"] for item in first + second}
    assert ticked == {str(item) for item in ids}  # the third was not starved by a fixed window


def test_one_failing_deployment_or_receipt_does_not_stop_other_owners(journey, owner_a, owner_b, monkeypatch):
    broken = deployed(journey, owner_a, "rec-broken-fx-lost-ack")
    healthy = deployed(journey, owner_b, "rec-healthy-fx-lost-ack")
    both = [uuid.UUID(broken["deployment"]["deployment_id"]), uuid.UUID(healthy["deployment"]["deployment_id"])]
    recurring = journey.app.state.financial.recurring
    with at(journey, 0):
        recurring.producer_pass(both)  # both originals are now unknown
    connected = journey.app.state.financial.connected
    real = connected.reconcile_action

    def failing(owner_id, action_id):
        if owner_id == occurrences(journey, broken["deployment"])[0].owner_id:
            raise ValueError("authored receipt parsing failure")
        return real(owner_id, action_id)

    monkeypatch.setattr(connected, "reconcile_action", failing)
    real_authority = recurring._authority_problem

    def tick_failure(session, row, now):
        if row.deployment_id == both[0]:
            raise RuntimeError("authored tick failure")
        return real_authority(session, row, now)

    monkeypatch.setattr(recurring, "_authority_problem", tick_failure)
    with at(journey, 5):
        results = recurring.producer_pass(both)
    assert {"deployment_id": str(both[0]), "failed": "RuntimeError"} in results
    healthy_jobs = occurrences(journey, healthy["deployment"])
    assert healthy_jobs[0].outcome == "SUBMITTED_CONFIRMED"  # owner B's original reconciled from its receipt
    assert len(healthy_jobs) == 2  # and owner B's next slot was produced and advanced
    assert occurrences(journey, broken["deployment"])[0].state == "SUBMITTED"  # owner A's stays unknown, held


def test_a_stuck_original_does_not_hold_the_reconciliation_window(journey, owner_a, owner_b):
    stuck = deployed(journey, owner_a, "rec-stuck-fx-lost-ack")
    other = deployed(journey, owner_b, "rec-later-fx-lost-ack")
    ids = [uuid.UUID(stuck["deployment"]["deployment_id"]), uuid.UUID(other["deployment"]["deployment_id"])]
    recurring = journey.app.state.financial.recurring
    with at(journey, 0):
        recurring.producer_pass(ids)
    receipts = journey.app.state.financial.ports.receipts
    real = receipts.observe
    stuck_action = occurrences(journey, stuck["deployment"])[0].action_id
    receipts.observe = lambda **kwargs: (
        (_ for _ in ()).throw(ProviderUnavailable("receipt")) if kwargs["action_id"] == stuck_action else real(**kwargs))
    try:
        with at(journey, 0):
            tried = [recurring.reconcile_pending(ids, limit=1) for _ in range(2)]
    finally:
        receipts.observe = real
    assert {item["action_id"] for batch in tried for item in batch} == {
        stuck_action, occurrences(journey, other["deployment"])[0].action_id}
    assert occurrences(journey, other["deployment"])[0].outcome == "SUBMITTED_CONFIRMED"


def test_ending_releases_an_admitted_unsent_occurrence_without_any_effect(journey, owner_a):
    agent = "rec-end-enqueued"
    state = deployed(journey, owner_a, agent)
    connected = journey.app.state.financial.connected
    real_submit = connected._submit
    connected._submit = lambda *args, **kwargs: None  # admitted, then the worker stops before submission
    try:
        produce(journey, state["deployment"], 0)
    finally:
        connected._submit = real_submit
    [job] = occurrences(journey, state["deployment"])
    assert job.state == "ENQUEUED"
    assert journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a).status_code == 200
    produce(journey, state["deployment"], 0)  # the same slot: the producer's worker pass reaches the occurrence
    [job] = occurrences(journey, state["deployment"])
    assert (job.state, job.outcome, job.reason) == ("COMPLETED", "DEPLOYMENT_ENDED", "DEPLOYMENT_ENDED:OWNER_ENDED")
    action = journey.get(f"/v1/actions/{job.action_id}", headers=owner_a).json()
    assert {reservation["state"] for reservation in action["reservations"]} == {"RELEASED"}
    assert ff.effects(journey) == []


def test_ending_denies_a_saved_occurrence_that_was_never_evaluated(journey, owner_a):
    agent = "rec-end-queued"
    state = deployed(journey, owner_a, agent)
    with at(journey, 0):
        journey.app.state.financial.recurring.tick([uuid.UUID(state["deployment"]["deployment_id"])])
    journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a)
    produce(journey, state["deployment"], 0)
    [job] = occurrences(journey, state["deployment"])
    assert (job.state, job.outcome, job.reason, job.decision_id) == (
        "COMPLETED", "DENIED", "DEPLOYMENT_ENDED:OWNER_ENDED", None)
    assert outcome_rows(journey, state["deployment"]) == [] and ff.effects(journey) == []


def test_an_unknown_original_is_still_reconciled_after_the_owner_ends(journey, owner_a):
    agent = "rec-end-unknown-fx-lost-ack"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    assert occurrences(journey, state["deployment"])[0].state == "SUBMITTED"
    journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a)
    produce(journey, state["deployment"], 5)
    jobs = occurrences(journey, state["deployment"])
    assert len(jobs) == 1 and jobs[0].outcome == "SUBMITTED_CONFIRMED"  # receipt read; no new occurrence
    assert projection(journey, owner_a, agent)["pending_reconciliation"] == []
    assert len(ff.effects(journey)) == 1


@pytest.mark.parametrize("agent,outcome", [("rec-out-fx-nosignal", "NO_SIGNAL"),
                                           ("rec-out-fx-ineligible", "INELIGIBLE")])
def test_no_signal_and_ineligible_occurrences_save_their_outcome_rows(journey, owner_a, agent, outcome):
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    [job] = occurrences(journey, state["deployment"])
    [row] = outcome_rows(journey, state["deployment"])
    assert (job.outcome, job.action_id) == (outcome, None)
    assert (row.outcome, row.reason, row.decision_id) == (outcome, None, job.decision_id)
    assert row.inputs_collected_at == job.decision_slot and ff.effects(journey) == []


def test_halt_all_swaps_denies_the_exit_and_keeps_the_residual_position(journey, owner_a):
    agent = "rec-halt"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    halt = journey.post(f"/v1/agents/{agent}/stops", headers=owner_a,
                        json={"mode": "HALT_ALL_SWAPS", "scope": "AGENT_WALLET_NETWORK"})
    assert halt.status_code == 200, halt.text
    produce_restarted(journey, state["deployment"], 5)
    jobs = occurrences(journey, state["deployment"])
    assert operations(journey, owner_a, jobs) == ["ENTRY", "EXIT"]
    assert (jobs[1].outcome, jobs[1].reason) == ("ADMISSION_DENIED", "STOPPED_HALT_ALL_SWAPS")
    positions = journey.get(f"/v1/agents/{agent}/actions", headers=owner_a).json()["positions"]
    assert [position["inventory_raw"] for position in positions] == [ff.ENTRY_BASE_OUTPUT]
    assert len(ff.effects(journey)) == 1
    assert projection(journey, owner_a, agent)["wait_reason"] == "STOPPED:HALT_ALL_SWAPS"


def test_a_stop_after_the_decision_and_before_the_outcome_row_recovers_with_the_saved_time(journey, owner_a):
    agent = "rec-crash-outcome"
    state = deployed(journey, owner_a, agent)
    connected = journey.app.state.financial.connected
    real_save = connected._save_outcome

    def crash(*args, **kwargs):
        raise RuntimeError("authored stop after the decision was saved")

    connected._save_outcome = crash
    try:
        produce(journey, state["deployment"], 0)  # the decision commits, then the worker stops
    finally:
        connected._save_outcome = real_save
    [job] = occurrences(journey, state["deployment"])
    assert job.state == "QUEUED" and job.reason == "WORKER_ERROR:RuntimeError" and outcome_rows(journey, state["deployment"]) == []
    produce(journey, state["deployment"], 0)  # the restarted worker in the same slot
    [job] = occurrences(journey, state["deployment"])
    [row] = outcome_rows(journey, state["deployment"])
    with journey.app.state.session_factory() as session:
        decision = session.get(DecisionRow, row.decision_id)
    assert row.outcome == "SIGNAL" and row.evaluated_at == decision.created_at
    assert row.provenance["recovered_after_restart"] is True
    assert job.outcome == "SUBMITTED_CONFIRMED" and len(ff.effects(journey)) == 1  # one decision, one action


def test_a_saved_unavailable_outcome_stays_final_on_retry(journey, owner_a):
    agent = "rec-unavailable-final"
    state = deployed(journey, owner_a, agent)
    recurring = journey.app.state.financial.recurring
    with at(journey, 0):
        recurring.tick([uuid.UUID(state["deployment"]["deployment_id"])])
    [job] = occurrences(journey, state["deployment"])
    connected = journey.app.state.financial.connected
    with journey.app.state.session_factory() as session:  # the outcome was saved; the stop came before the job ended
        session.execute(connected._outcome_insert(job, "UNAVAILABLE", "OBSERVATIONS_STALE", None, None, None,
                                                  job.decision_slot, {}))
        session.commit()
    calls = []
    market = journey.app.state.financial.ports.market
    real = market.observe
    market.observe = lambda request: calls.append(request) or real(request)
    try:
        produce(journey, state["deployment"], 0)
    finally:
        market.observe = real
    [job] = occurrences(journey, state["deployment"])
    assert (job.state, job.reason, calls) == ("UNAVAILABLE", "OBSERVATIONS_STALE", [])
    assert ff.effects(journey) == []


def test_a_failed_tick_commits_nothing(journey, owner_a, monkeypatch):
    from edge_os_api.execution import recurring_scheduler

    state = deployed(journey, owner_a, "rec-tick-crash")

    def failing_insert(*args, **kwargs):
        raise RuntimeError("authored failure inside the tick")

    monkeypatch.setattr(recurring_scheduler, "pg_insert", failing_insert)
    with at(journey, 0):
        result = journey.app.state.financial.recurring.tick([uuid.UUID(state["deployment"]["deployment_id"])])
    assert result == [{"deployment_id": state["deployment"]["deployment_id"], "failed": "RuntimeError"}]
    with journey.app.state.session_factory() as session:
        row = session.get(RecurringDeploymentRow, uuid.UUID(state["deployment"]["deployment_id"]))
    assert (row.cursor_slot, row.last_tick_at, int(row.occurrences)) == (None, None, 0)
    assert occurrences(journey, state["deployment"]) == []


def test_activation_is_refused_after_removal_was_requested(journey, owner_a):
    agent = "rec-removed-first"
    state = ready(journey, owner_a, agent)
    journey.post(f"/v1/agents/{agent}/removal", headers=owner_a,
                 json={"request_key": "remove", "reason": "owner removes the agent"})
    refused = activate(journey, owner_a, agent, state["consent"]["consent_hash"])
    assert (refused.status_code, refused.json()["code"]) == (409, "agent_removed")


def test_manual_evaluations_cannot_use_the_reserved_occurrence_key(journey, owner_a):
    ready(journey, owner_a, "rec-reserved-key")
    response = ff.schedule(journey, owner_a, "rec-reserved-key", "recurring:anything")
    assert response.status_code == 422


@pytest.mark.parametrize("flags", [["--interval", "0"], ["--max-passes", "0"]])
def test_the_producer_refuses_an_unbounded_or_empty_run(env, flags):
    result = subprocess.run([sys.executable, "-m", "edge_os_api.execution.recurring_producer", *flags],
                            cwd=harness.API_DIR, env=producer_env(env, "unused.jsonl"), capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 2 and "--interval must be positive" in result.stderr


# ------------------------------------------------------------------------------- gate REVISE 1/3 (R1–R3)

def admission_view(client: TestClient, headers: dict[str, str], action_id: str) -> dict[str, Any]:
    action = client.get(f"/v1/actions/{action_id}", headers=headers).json()
    return {"admission": [item["status"] for item in action["admission"]],
            "reservations": sorted({item["state"] for item in action["reservations"]}),
            "queue": (action["queue"] or {}).get("state"), "attempts": len(action["attempts"])}


def test_an_end_committed_before_submission_ownership_wins_and_nothing_is_sent(journey, owner_a):
    """R1, end first: the end commits after the worker's last outer check and before ownership is acquired."""
    agent = "rec-race-end-first"
    state = deployed(journey, owner_a, agent)
    execution = journey.app.state.financial.execution
    real_tick = execution.tick

    def end_then_tick(*args, **kwargs):
        ended = journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a)
        assert ended.json()["end_reason"] == "OWNER_ENDED"
        return real_tick(*args, **kwargs)

    execution.tick = end_then_tick
    try:
        produce(journey, state["deployment"], 0)
    finally:
        execution.tick = real_tick
    [job] = occurrences(journey, state["deployment"])
    view = admission_view(journey, owner_a, job.action_id)
    assert ff.effects(journey) == []
    # The shared control denies at revalidation (execution lock) or, at the latest, at ownership (admission lock).
    assert job.state == "COMPLETED" and job.outcome in ("REVALIDATION_DENIED", "SUBMISSION_NOT_OWNED")
    assert view["reservations"] == ["RELEASED"] and "CANCELLED" in view["admission"]


def test_an_end_committed_after_revalidation_is_still_refused_at_ownership(journey, owner_a):
    """R1, the last point: revalidation passed, then the end commits, then `acquire_submission` runs under the lock."""
    agent = "rec-race-end-at-ownership"
    state = deployed(journey, owner_a, agent)
    admission = journey.app.state.financial.admission
    real_acquire = admission.acquire_submission
    seen = []

    def end_then_acquire(owner, action_id):
        assert journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a).status_code == 200
        status = real_acquire(owner, action_id)
        seen.append(status)
        return status

    admission.acquire_submission = end_then_acquire
    try:
        produce(journey, state["deployment"], 0)
    finally:
        admission.acquire_submission = real_acquire
    [job] = occurrences(journey, state["deployment"])
    assert seen == ["STOPPED_SCOPE"] and ff.effects(journey) == []
    assert (job.state, job.outcome) == ("COMPLETED", "SUBMISSION_NOT_OWNED")
    view = admission_view(journey, owner_a, job.action_id)
    assert view["reservations"] == ["RELEASED"] and "CANCELLED" in view["admission"]


def test_ownership_acquired_before_the_end_keeps_the_original_and_its_recovery(journey, owner_a):
    """R1, ownership first: the end commits after the action became submission-owned; the original proceeds."""
    agent = "rec-race-owned-first"
    state = deployed(journey, owner_a, agent)
    admission = journey.app.state.financial.admission
    real_acquire = admission.acquire_submission

    def acquire_then_end(owner, action_id):
        status = real_acquire(owner, action_id)
        assert status == "ACQUIRED"
        assert journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a).status_code == 200
        return status

    admission.acquire_submission = acquire_then_end
    try:
        produce(journey, state["deployment"], 0)
    finally:
        admission.acquire_submission = real_acquire
    [job] = occurrences(journey, state["deployment"])
    assert job.outcome == "SUBMITTED_CONFIRMED" and len(ff.effects(journey)) == 1
    assert projection(journey, owner_a, agent)["deployment"]["end_reason"] == "OWNER_ENDED"


def test_the_end_waits_for_the_wallet_lock_that_submission_ownership_holds(journey, owner_a):
    """R1, serialization: while the per-wallet admission lock is held, the end cannot commit."""
    import threading

    from edge_os_api.admission.service import acquire_wallet_lock

    agent = "rec-race-lock"
    state = deployed(journey, owner_a, agent)
    identity = state["deployment"]["identity"]
    owner_id = occurrences_owner(journey, state)
    holder = journey.app.state.session_factory()
    acquire_wallet_lock(holder, owner_id, agent, identity["wallet_id"], identity["network_id"])
    finished = threading.Event()
    worker = threading.Thread(target=lambda: (journey.app.state.financial.recurring.end(owner_id, agent),
                                              finished.set()))
    worker.start()
    try:
        assert not finished.wait(1.0)  # blocked behind the lock
        assert projection(journey, owner_a, agent)["deployment"]["state"] == "ACTIVE"
    finally:
        holder.rollback()  # releases the lock, as acquire_submission's commit does
        holder.close()
    worker.join(timeout=30)
    assert finished.is_set() and projection(journey, owner_a, agent)["deployment"]["state"] == "ENDED"


def occurrences_owner(client: TestClient, state: dict[str, Any]) -> uuid.UUID:
    with client.app.state.session_factory() as session:
        return session.get(RecurringDeploymentRow, uuid.UUID(state["deployment"]["deployment_id"])).owner_id


def test_an_ended_deployment_never_blocks_a_manual_run_or_another_owner(journey, owner_a, owner_b):
    """R1 scope: the end control denies only that deployment's admitted action."""
    mine = deployed(journey, owner_a, "rec-scope-ended")
    other = deployed(journey, owner_b, "rec-scope-other")
    journey.post("/v1/agents/rec-scope-ended/deployment/end", headers=owner_a)
    with at(journey, 0):
        manual = ff.run_job(journey, ff.schedule(journey, owner_a, "rec-scope-ended", "manual").json())
    produce(journey, other["deployment"], 0)
    assert manual["outcome"] == "SUBMITTED_CONFIRMED"
    assert occurrences(journey, other["deployment"])[0].outcome == "SUBMITTED_CONFIRMED"
    assert occurrences(journey, mine["deployment"]) == []
    assert len(ff.effects(journey)) == 2


@pytest.mark.parametrize("change,reason", [
    ({"finality": None}, "OBSERVATIONS_PROVENANCE_INCOMPLETE"),
    ({"evidence_class": "RECORDED_RESPONSE"}, "OBSERVATIONS_NOT_FORWARD"),
    ({"collected_at": "2000-01-01T00:00:00+00:00"}, "OBSERVATIONS_STALE"),
    ({"market_binding_id": "other-market"}, "OBSERVATIONS_WRONG_MARKET"),
    ("wrong-time", "OBSERVATIONS_WRONG_TIME")])
def test_a_degraded_submission_observation_waits_and_sends_nothing(journey, owner_a, change, reason):
    """R2: the decision's valid reading never qualifies a degraded reading at submission."""
    agent = f"rec-sub-obs-{uuid.uuid4().hex[:6]}"
    state = deployed(journey, owner_a, agent)
    market = journey.app.state.financial.ports.market
    real = market.observe
    calls = []

    def second_degraded(request):
        calls.append(request)
        if len(calls) == 1:
            return real(request)
        if change == "wrong-time":
            return real(dataclasses.replace(request, decision_time=request.decision_time - SLOT))
        observed = real(request)
        return MarketObservations(inputs=observed.inputs, provenance={**observed.provenance, **change})

    market.observe = second_degraded
    try:
        produce(journey, state["deployment"], 0)
    finally:
        market.observe = real
    [job] = occurrences(journey, state["deployment"])
    assert len(calls) >= 2 and ff.effects(journey) == []  # the run loop may read again while waiting
    assert (job.state, job.reason) == ("ENQUEUED", f"WAITING:SUBMISSION_{reason}")
    assert job.provenance["submission_observations"]["problem"] == reason
    [outcome] = outcome_rows(journey, state["deployment"])
    assert outcome.outcome == "SIGNAL"  # the saved decision evidence is kept
    view = admission_view(journey, owner_a, job.action_id)
    assert view["admission"] == ["ADMITTED"] and view["attempts"] == 0
    # Past its slot the unsent action is released through the accepted cancellation; it was never sent. (The next
    # slot's own occurrence may trade on fresh observations; that is a different action.)
    produce(journey, state["deployment"], 6)
    view = admission_view(journey, owner_a, job.action_id)
    assert view["reservations"] == ["RELEASED"] and view["attempts"] == 0
    assert job.action_id not in {effect.action_id for effect in ff.effects(journey)}


def crash_after_enqueue(client: TestClient, deployment: dict[str, Any]) -> EvaluationJobRow:
    connected = client.app.state.financial.connected
    real = connected._after_enqueue

    def crash(*args, **kwargs):
        raise RuntimeError("authored stop after the intent was saved")

    connected._after_enqueue = crash
    try:
        produce(client, deployment, 0)
    finally:
        connected._after_enqueue = real
    [job] = occurrences(client, deployment)
    return job


def test_an_admitted_intent_saved_before_a_crash_is_released_when_the_owner_ends(journey, owner_a):
    """R3: the saved intent is reconnected by its decision and released; no replacement and no effect."""
    agent = "rec-orphan-end"
    state = deployed(journey, owner_a, agent)
    job = crash_after_enqueue(journey, state["deployment"])
    assert (job.state, job.action_id) == ("DECIDED", None)
    with journey.app.state.session_factory() as session:
        [intent] = session.execute(select(IntentRow).where(IntentRow.decision_id == job.decision_id)).scalars().all()
    journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a)
    produce(journey, state["deployment"], 0)
    [job] = occurrences(journey, state["deployment"])
    assert (job.state, job.outcome, job.action_id) == ("COMPLETED", "DEPLOYMENT_ENDED", intent.action_id)
    view = admission_view(journey, owner_a, intent.action_id)
    assert view == {"admission": view["admission"], "reservations": ["RELEASED"], "queue": "DENIED_UNSENT",
                    "attempts": 0} and "CANCELLED" in view["admission"]
    with journey.app.state.session_factory() as session:
        assert len(session.execute(select(IntentRow).where(IntentRow.agent_id == agent)).all()) == 1
    assert ff.effects(journey) == []


def test_an_admitted_intent_saved_before_a_crash_is_released_when_authority_changes(journey, owner_a, monkeypatch):
    """R3 adjacent: a changed identity or consent also reconnects and releases the saved intent."""
    agent = "rec-orphan-drift"
    state = deployed(journey, owner_a, agent)
    job = crash_after_enqueue(journey, state["deployment"])
    connected = journey.app.state.financial.connected
    monkeypatch.setattr(connected, "_context_for", lambda job: (None, None, "CONSENT_CHANGED"))
    produce(journey, state["deployment"], 0)
    [job] = occurrences(journey, state["deployment"])
    assert (job.outcome, job.reason) == ("DENIED", "CONSENT_CHANGED") and job.action_id is not None
    assert admission_view(journey, owner_a, job.action_id)["reservations"] == ["RELEASED"]
    assert ff.effects(journey) == []


def test_an_admitted_intent_saved_before_a_crash_resumes_once_when_nothing_changed(journey, owner_a):
    """R3 control: without an end or a change, the saved intent is reused and sent exactly once."""
    state = deployed(journey, owner_a, "rec-orphan-resume")
    crash_after_enqueue(journey, state["deployment"])
    produce(journey, state["deployment"], 0)
    [job] = occurrences(journey, state["deployment"])
    assert job.outcome == "SUBMITTED_CONFIRMED" and len(ff.effects(journey)) == 1
    with journey.app.state.session_factory() as session:
        assert len(session.execute(select(IntentRow).where(IntentRow.agent_id == "rec-orphan-resume")).all()) == 1


def test_a_submission_owned_original_is_never_released_by_an_end(journey, owner_a):
    """R1/R3 invariant: an unknown, owned original keeps its reservations after an end and settles from its receipt."""
    agent = "rec-owned-end-fx-lost-ack"
    state = deployed(journey, owner_a, agent)
    produce(journey, state["deployment"], 0)
    [job] = occurrences(journey, state["deployment"])
    assert job.state == "SUBMITTED"
    journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a)
    assert admission_view(journey, owner_a, job.action_id)["reservations"] != ["RELEASED"]
    produce(journey, state["deployment"], 5)
    assert occurrences(journey, state["deployment"])[0].outcome == "SUBMITTED_CONFIRMED"
    assert len(ff.effects(journey)) == 1


# ------------------------------------------------------------------------------------- gate REVISE 2/3 (R4)

def test_simultaneous_ends_both_reply_with_the_saved_ended_state(journey, owner_a):
    """R4: two ends wait on the same wallet lock; after the first commits, the second replies ENDED, not stale ACTIVE."""
    import threading

    from edge_os_api.admission.service import acquire_wallet_lock

    agent = "rec-double-end"
    state = deployed(journey, owner_a, agent)
    identity = state["deployment"]["identity"]
    owner_id = occurrences_owner(journey, state)
    recurring = journey.app.state.financial.recurring
    holder = journey.app.state.session_factory()
    acquire_wallet_lock(holder, owner_id, agent, identity["wallet_id"], identity["network_id"])
    replies: list[dict[str, Any]] = []
    workers = [threading.Thread(target=lambda: replies.append(recurring.end(owner_id, agent))) for _ in range(2)]
    for worker in workers:
        worker.start()
    try:
        # Both ends have read the ACTIVE row and now wait behind the held wallet lock (bounded wait, 10 s).
        import time

        deadline, waiting = time.monotonic() + 10, 0
        while time.monotonic() < deadline:
            with journey.app.state.session_factory() as session:
                waiting = session.execute(text(
                    "select count(*) from pg_stat_activity where wait_event_type = 'Lock' "
                    "and wait_event = 'advisory' and datname = current_database()")).scalar_one()
            if waiting >= 2:
                break
            time.sleep(0.05)
        assert waiting >= 2
    finally:
        holder.rollback()
        holder.close()
    for worker in workers:
        worker.join(timeout=30)
    assert [reply["state"] for reply in replies] == ["ENDED", "ENDED"]
    assert {reply["end_reason"] for reply in replies} == {"OWNER_ENDED"}
    again = journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a)  # idempotent: the saved end, unchanged
    assert (again.status_code, again.json()["state"], again.json()["ended_at"]) == (
        200, "ENDED", replies[0]["ended_at"])
    assert projection(journey, owner_a, agent)["deployment"]["state"] == "ENDED"


# ------------------------------------------------------------------------- gate REVISE 3/3 (R1-C, D4)

def end_after_initial_empty_read(client: TestClient, headers: dict[str, str], agent: str, state: dict[str, Any],
                                 monkeypatch, *, wait_for: Any = None) -> dict[str, Any]:
    """Run End in its own thread. Its first real SELECT finds no deployment; then, before End reads again, a real
    authenticated activation commits and the original occurrence is decided and admitted through the unchanged
    worker stages. `wait_for` (an Event) holds End there until the test lets it continue. No row is fabricated."""
    import threading

    recurring, connected = client.app.state.financial.recurring, client.app.state.financial.connected
    real_factory = recurring._factory
    record: dict[str, Any] = {"trace": [], "replies": [], "errors": [], "deployment": None}
    admitted, committed = threading.Event(), threading.Event()
    hooked: list[bool] = []

    def factory(*args, **kwargs):
        session = real_factory(*args, **kwargs)
        if threading.current_thread().name != "end-after-empty-read" or hooked:
            return session
        hooked.append(True)
        real_execute, real_commit = session.execute, session.commit
        calls: list[str] = []

        def execute(statement, *a, **k):
            if "pg_advisory_xact_lock" in str(statement):
                record["trace"].append("END_WAITS_FOR_WALLET_LOCK")
            result = real_execute(statement, *a, **k)
            calls.append(str(statement))
            if "pg_advisory_xact_lock" in str(statement):
                record["trace"].append("END_HOLDS_WALLET_LOCK")
            if len(calls) == 1:
                record["trace"].append("END_INITIAL_READ_EMPTY")
                response = activate(client, headers, agent, state["consent"]["consent_hash"])
                assert response.status_code == 201, response.text
                record["deployment"] = response.json()
                with at(client, 0):
                    recurring.tick(only=[uuid.UUID(record["deployment"]["deployment_id"])])
                    [job] = occurrences(client, record["deployment"])
                    connected._advance(job)
                    connected._advance(connected._load(job.job_id))
                [job] = occurrences(client, record["deployment"])
                assert job.state == "ENQUEUED" and job.action_id is not None
                record["trace"].append("ACTIVATED_AND_ORIGINAL_ADMITTED")
                admitted.set()
                if wait_for is not None:
                    assert wait_for.wait(30), "the test did not release End"
            return result

        def commit():
            real_commit()
            if record["deployment"] is not None and not committed.is_set():
                record["trace"].append("END_COMMITTED")
                committed.set()

        session.execute, session.commit = execute, commit
        return session

    monkeypatch.setattr(recurring, "_factory", factory)
    owner_id = uuid.UUID(client.get("/v1/me", headers=headers).json()["user_id"])

    def run_end():
        try:
            record["replies"].append(recurring.end(owner_id, agent))
        except BaseException as error:  # noqa: BLE001 - reported to the test thread
            record["errors"].append(repr(error))
            admitted.set()

    thread = threading.Thread(target=run_end, name="end-after-empty-read")
    record.update(thread=thread, admitted=admitted, committed=committed, owner_id=owner_id)
    thread.start()
    return record


def test_an_end_whose_first_read_was_empty_waits_for_ownership_held_on_the_wallet(journey, owner_a, monkeypatch):
    """R1-C, ownership first: a deployment activated after End's empty first read is ended only under its wallet lock,
    so End cannot commit while submission ownership holds that lock; the original then proceeds and stays owned."""
    import threading

    agent = "rec-r1c-ownership-first"
    state = ready(journey, owner_a, agent)
    release_end = threading.Event()
    observed: dict[str, Any] = {}
    record = end_after_initial_empty_read(journey, owner_a, agent, state, monkeypatch, wait_for=release_end)
    try:
        assert record["admitted"].wait(30) and not record["errors"], record["errors"]
        admission = journey.app.state.financial.admission
        real_guard = admission._stop_denial_for_row

        def guard(session, owner, row):
            result = real_guard(session, owner, row)  # the real control read, under the real admission wallet lock
            observed["control"] = result
            release_end.set()  # End now continues and needs this same wallet lock
            observed["end_committed_while_ownership_held"] = record["committed"].wait(2)
            return result

        monkeypatch.setattr(admission, "_stop_denial_for_row", guard)
        [job] = occurrences(journey, record["deployment"])
        with at(journey, 0):
            journey.app.state.financial.connected.run_job(job.job_id)
        record["thread"].join(timeout=30)
    finally:
        release_end.set()
        record["thread"].join(timeout=35)
    assert not record["thread"].is_alive() and not record["errors"], record["errors"]
    assert observed == {"control": None, "end_committed_while_ownership_held": False}, observed
    assert "END_HOLDS_WALLET_LOCK" in record["trace"]
    assert record["trace"].index("END_HOLDS_WALLET_LOCK") < record["trace"].index("END_COMMITTED")
    [job] = occurrences(journey, record["deployment"])
    assert job.outcome == "SUBMITTED_CONFIRMED" and len(ff.effects(journey)) == 1  # owned first: the original
    assert record["replies"][0]["state"] == "ENDED"
    assert projection(journey, owner_a, agent)["deployment"]["state"] == "ENDED"


def test_an_end_whose_first_read_was_empty_ends_under_the_lock_before_ownership(journey, owner_a, monkeypatch):
    """R1-C, end first: End retries after its empty read, locks the newly active deployment's wallet and ends it; the
    admitted original is then refused ownership with no effect and its reservations are released."""
    agent = "rec-r1c-end-first"
    state = ready(journey, owner_a, agent)
    record = end_after_initial_empty_read(journey, owner_a, agent, state, monkeypatch)
    record["thread"].join(timeout=35)
    assert not record["thread"].is_alive() and not record["errors"], record["errors"]
    assert record["trace"].index("END_HOLDS_WALLET_LOCK") < record["trace"].index("END_COMMITTED")
    assert record["replies"][0]["state"] == "ENDED"
    [job] = occurrences(journey, record["deployment"])
    with at(journey, 0):
        journey.app.state.financial.connected.run_job(job.job_id)
    [job] = occurrences(journey, record["deployment"])
    assert ff.effects(journey) == []
    assert job.state == "COMPLETED" and job.outcome in ("DEPLOYMENT_ENDED", "REVALIDATION_DENIED",
                                                         "SUBMISSION_NOT_OWNED")
    view = admission_view(journey, owner_a, job.action_id)
    assert view["reservations"] == ["RELEASED"] and "CANCELLED" in view["admission"]


def test_an_end_with_no_deployment_at_all_ends_nothing(journey, owner_a):
    ready(journey, owner_a, "rec-r1c-none")
    response = journey.post("/v1/agents/rec-r1c-none/deployment/end", headers=owner_a)
    assert response.status_code == 404
