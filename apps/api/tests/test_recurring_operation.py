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
import datetime as dt
import os
import subprocess
import sys
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import make_url

import financial_flows as ff
import harness
from edge_os_api.core.provider_ports import MarketObservations, ProviderUnavailable
from edge_os_api.core.settings import load_settings
from edge_os_api.execution.models import (DecisionRow, EvaluationJobRow, EvaluationOutcomeRow,
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
    (None, "OBSERVATIONS_UNAVAILABLE")])
def test_unusable_observations_save_an_unavailable_outcome_and_no_intent(journey, owner_a, change, reason):
    agent = f"rec-obs-{uuid.uuid4().hex[:6]}"
    state = deployed(journey, owner_a, agent)
    market = journey.app.state.financial.ports.market
    real = market.observe

    def altered(request):
        if change is None:
            raise ProviderUnavailable("observations")
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


@pytest.mark.parametrize("terms,reason", [({"quote_cap": "200000000"}, None), ({"attempts": 2}, "ATTEMPT_BUDGET_EXHAUSTED")])
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
    if reason is not None:
        assert denied.reason == reason
    assert len(ff.effects(journey)) == produced
    # A new producer process (a restart) does not reset the counters: the next entry is denied again.
    produce(journey, state["deployment"], 5 * (produced + 2))
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
    produce(journey, state["deployment"], 15)  # still denied on a later slot
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
    assert len(jobs) == 1 and jobs[0].outcome == "SUBMITTED_CONFIRMED"
    assert [effect.action_id for effect in ff.effects(journey)].count(jobs[0].action_id) == 1


def test_the_persistent_producer_runs_bounded_passes_then_exits(journey, owner_a, env, tmp_path):
    state = deployed(journey, owner_a, "rec-loop")
    command = [sys.executable, "-m", "edge_os_api.execution.recurring_producer", "--interval", "0.2",
               "--max-passes", "3"]
    result = subprocess.run(command, cwd=harness.API_DIR, env=producer_env(env, str(tmp_path / "effects.jsonl")),
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-800:]
    assert result.stderr.count("recurring producer pass") == 3
    assert len(occurrences(journey, state["deployment"])) == 1


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
