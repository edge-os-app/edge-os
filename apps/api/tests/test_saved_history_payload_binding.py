"""Saved-history payload binding through the API, the worker and PostgreSQL (SAVED-HISTORY-BINDING-L2).

A bound stand-in release (`forward_history_stand_in`) is collected by the real worker into this module's own database.
The tests prove the failure matrix: one immutable `HISTORY_PAYLOAD_BOUND` event in the dataset transaction, same-owner
reads only, consumers blocked on MISMATCH or INCOMPLETE while the P07 verdict stays QUALIFIED, a forged saved PASS
granting nothing, interruption before and after the dataset commit, and the binding inside the replay
configuration identity. Everything is SYNTHETIC; no provider is reached.
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

import forward_history_stand_in as bound
import harness
import operating_release_stand_in as stand_in
from edge_os_api.core.errors import AppError
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.replay import saved_runs
from edge_os_api.research import history_payload_binding
from edge_os_api.research.investigation_jobs import InvestigationWorker
from flows import compiled_thesis, publish
from research_flows import adoption_body, history_replay_body, jobs_path

QUOTE_UNIT = "QUOTE:0x" + "d2" * 20


class Killed(BaseException):
    """Ends the worker like a killed process: not an `Exception`, so no handler turns it into an outcome."""


@pytest.fixture(scope="module")
def env(pg, signer):
    """This module's own database, like the release research tests."""
    name = f"{pg.database}_binding_{uuid.uuid4().hex[:6]}"
    pg.psql(f"create database {name}", db="postgres")
    url = make_url(pg.url).set(database=name).render_as_string(hide_password=False)
    try:
        values = harness.api_env(database_url=url, public_pem=signer.public_pem, previous_pem=None,
                                 cors=["http://127.0.0.1:3999"])
        yield {**values, "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "400",
               "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS": "3600"}
    finally:
        pg.psql(f"drop database if exists {name} with (force)", db="postgres")


@pytest.fixture(scope="module")
def settings(env):
    result = harness.migrate(env)
    assert result.returncode == 0, result.stderr
    return load_settings(env)


def composed(settings, release=None):
    runtime, provider, nansen, creds = bound.recording_runtime(settings, release=release)
    return TestClient(create_app(settings, research_runtime=runtime)), runtime, provider, creds


def worker(client, runtime, **kwargs) -> InvestigationWorker:
    return InvestigationWorker(client.app.state.session_factory, client.app.state.settings,
                               research_runtime=runtime, **kwargs)


def job_view(client, headers, job_id: str) -> dict[str, Any]:
    response = client.get(f"/v1/research/investigation-jobs/{job_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def started(client, headers, runtime) -> str:
    intake_id, declaration_id, _ = bound.declare(client, headers, runtime.release.history.limits)
    response = client.post(jobs_path(intake_id, declaration_id), headers=headers,
                           json={"operation_id": str(uuid.uuid4()), "request_key": f"bound-{uuid.uuid4()}"})
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def collected(client, headers, runtime) -> tuple[str, dict[str, Any]]:
    job_id = started(client, headers, runtime)
    worker(client, runtime).run_job(uuid.UUID(job_id))
    job = job_view(client, headers, job_id)
    assert job["state"] == "REPORTED", job["terminal_reason"]
    return job_id, job


def rows(client, sql: str, **params: Any) -> list[dict[str, Any]]:
    with client.app.state.session_factory() as session:
        return [dict(row._mapping) for row in session.execute(text(sql), params)]


def execute(client, sql: str, **params: Any) -> None:
    with client.app.state.session_factory() as session:
        session.execute(text(sql), params)
        session.commit()


def bound_events(client, job_id: str) -> list[dict[str, Any]]:
    return rows(client, "select event_id, owner_id, attempt_id, content from research_local.investigation_events "
                        "where job_id = :job and kind = 'HISTORY_PAYLOAD_BOUND'", job=job_id)


def adopted_revision(client, headers, dataset_id: str) -> tuple[Any, Any]:
    """A fixture revision, then the adoption request of the dataset market. Returns the bundle and the response."""
    listed = next(item for item in client.get("/v1/research/history-datasets", headers=headers).json()["datasets"]
                  if item["dataset_id"] == dataset_id)
    bundle = compiled_thesis(client, headers)
    first, _ = publish(client, headers, bundle)
    parent = first.json()["revision_id"]
    adopted = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions", headers=headers,
                          json=adoption_body(bundle, dataset_id, parent=parent, quote_unit=QUOTE_UNIT,
                                             evaluation_id=listed["declared_rules"][0]["evaluation_id"]))
    return (bundle, parent), adopted


def replay_body(bundle, revision_id: str, dataset_id: str, **kwargs: Any) -> dict[str, Any]:
    return history_replay_body(bundle["head"]["strategy_id"], revision_id, dataset_id, start=bound.WINDOW_START,
                               end=bound.WINDOW_END, **kwargs)


def counts(client) -> dict[str, int]:
    tables = ("research_local.history_datasets", "research_local.investigation_events", "spot_replay_runs",
              "spot_replay_configurations", "idempotency_records")
    return {table: rows(client, f"select count(*) n from {table}")[0]["n"] for table in tables}


# --------------------------------------------------------------------------------------- PASS and lineage

def test_a_bound_job_saves_one_immutable_pass_event_and_consumers_carry_its_lineage(settings, owner_a, owner_b):
    client, runtime, provider, creds = composed(settings)
    with client:
        job_id, job = collected(client, owner_a, runtime)
        definition = history_payload_binding.requirement(bound.definition())
        assert len(provider.requests) == bound.provider_requests() == 7
        events = bound_events(client, job_id)
        assert len(events) == 1
        event = events[0]["content"]
        dataset_id = job["dataset"]["dataset_id"]
        assert (event["result"], event["reason"], event["dataset_id"]) == ("PASS", None, dataset_id)
        assert event["handoff_json"] == bound.definition()["handoff_json"]
        assert event["checker"]["sha256"] == history_payload_binding.CHECKER_SHA256
        stored = rows(client, "select owner_id, content, content_sha256, raw_records from "
                              "research_local.history_datasets where dataset_id = :id", id=dataset_id)[0]
        assert events[0]["owner_id"] == stored["owner_id"] and str(events[0]["attempt_id"]) == stored["content"][
            "attempt_id"]
        assert event["report"]["content_sha256"] == stored["content_sha256"]
        assert event["expected"]["release"]["sha256"] == runtime.release_sha256
        assert stored["content"]["payload_binding_requirement"] == definition
        assert "handoff_json" not in json.dumps(stored["content"])
        assert stored["content"]["verdict"]["overall"] == "QUALIFIED"
        # The owner's job view hides the handoff text; the dataset views expose the current binding.
        shown = next(item for item in job["events"] if item["kind"] == "HISTORY_PAYLOAD_BOUND")
        assert "handoff_json" not in shown["content"] and shown["content"]["handoff_bytes"] > 0
        kinds = [item["kind"] for item in job["events"]]
        assert kinds.index("ATTEMPT_FINISHED") < kinds.index("HISTORY_PAYLOAD_BOUND") < kinds.index("JOB_EVALUATING")
        assert job["dataset"]["payload_binding"]["status"] == "PASS"
        single = client.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json()
        listed = next(item for item in client.get("/v1/research/history-datasets", headers=owner_a).json()["datasets"]
                      if item["dataset_id"] == dataset_id)
        assert single["payload_binding"] == listed["payload_binding"] == job["dataset"]["payload_binding"]
        assert single["payload_binding"]["report_sha256"] == event["report_sha256"]
        before_rows = (stored, bound_events(client, job_id))
        # Market adoption and replay carry the report and handoff identity.
        (bundle, parent), adopted = adopted_revision(client, owner_a, dataset_id)
        assert adopted.status_code == 201, adopted.text
        lineage = adopted.json()["adoption"]["payload_binding"]
        assert lineage == history_payload_binding.lineage(single["payload_binding"])
        second, _ = publish(client, owner_a, adopted.json()["bundle"], parent=parent)
        assert second.status_code == 201, second.text
        replayed = client.post("/v1/spot-replays", headers=owner_a,
                               json=replay_body(bundle, second.json()["revision_id"], dataset_id))
        assert replayed.status_code == 201, replayed.text
        replay = replayed.json()
        assert replay["content"]["inputs"]["history_input"]["payload_binding"] == lineage
        assert replay["content"]["inputs"]["history_input"]["source_evidence_class"] == "RELEASE_STAND_IN_RESPONSE"
        # Consumers wrote nothing to the dataset or its event; nothing was collected again.
        after_rows = (rows(client, "select owner_id, content, content_sha256, raw_records from "
                                   "research_local.history_datasets where dataset_id = :id", id=dataset_id)[0],
                      bound_events(client, job_id))
        assert after_rows == before_rows
        assert len(provider.requests) == 7 and creds.reads == [stand_in.ENVIO_SLOT, stand_in.QUICKNODE_SLOT]
        # Same-owner reads only: another owner sees 404 and leaves no row.
        before = counts(client)
        for route in (f"/v1/research/history-datasets/{dataset_id}", f"/v1/research/investigation-jobs/{job_id}",
                      f"/v1/spot-replays/{replay['replay_id']}"):
            assert client.get(route, headers=owner_b).status_code == 404
        (bundle_b, parent_b), foreign = adopted_revision_foreign(client, owner_b, dataset_id)
        assert foreign.status_code == 404
        foreign_replay = client.post("/v1/spot-replays", headers=owner_b,
                                     json=replay_body(bundle_b, parent_b, dataset_id))
        assert foreign_replay.status_code == 404
        after = counts(client)
        assert after["research_local.history_datasets"] == before["research_local.history_datasets"]
        assert after["spot_replay_runs"] == before["spot_replay_runs"]
        assert not any(value in json.dumps(job) + json.dumps(single) for value in stand_in.SENTINELS)


def adopted_revision_foreign(client, headers, dataset_id: str) -> tuple[Any, Any]:
    """Owner B names owner A's dataset in its own adoption request."""
    bundle = compiled_thesis(client, headers)
    first, _ = publish(client, headers, bundle)
    parent = first.json()["revision_id"]
    adopted = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions", headers=headers,
                          json=adoption_body(bundle, dataset_id, parent=parent, quote_unit=QUOTE_UNIT))
    return (bundle, parent), adopted


# --------------------------------------------------------------------------------------- blocked consumers

def _contradicted() -> dict[str, str]:
    handoff = bound.handoff()
    buckets = copy.deepcopy(handoff["buckets"])
    buckets[2]["payload_sha256"] = "0" * 64
    return bound.definition({**handoff, "buckets": buckets})


def _blocked(client, headers, dataset_id: str, code: str) -> None:
    before = counts(client)
    (bundle, parent), adopted = adopted_revision(client, headers, dataset_id)
    assert (adopted.status_code, adopted.json()["code"]) == (409, code), adopted.text
    replayed = client.post("/v1/spot-replays", headers=headers, json=replay_body(bundle, parent, dataset_id))
    assert (replayed.status_code, replayed.json()["code"]) == (409, code), replayed.text
    after = counts(client)
    assert after["spot_replay_runs"] == before["spot_replay_runs"]
    assert after["spot_replay_configurations"] == before["spot_replay_configurations"]


def test_a_contradicted_handoff_is_a_mismatch_that_blocks_consumers_and_keeps_qualified(settings, owner_a):
    client, runtime, provider, _ = composed(settings, bound.bound_release(binding=_contradicted()))
    with client:
        job_id, job = collected(client, owner_a, runtime)
        event = bound_events(client, job_id)[0]["content"]
        assert (event["result"], event["reason"]) == ("MISMATCH", "BUCKET_2:PAYLOAD_DIFFERS")
        dataset_id = job["dataset"]["dataset_id"]
        dataset = client.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json()
        assert dataset["content"]["verdict"]["overall"] == "QUALIFIED"
        assert dataset["content"]["binding_state"] == "QUALIFIED_BINDING"
        assert (dataset["payload_binding"]["status"], dataset["payload_binding"]["reason"]) == (
            "MISMATCH", "BUCKET_2:PAYLOAD_DIFFERS")
        _blocked(client, owner_a, dataset_id, "payload_binding_mismatch")
        assert len(provider.requests) == 7


def test_a_missing_event_is_incomplete_and_a_forged_pass_grants_nothing(settings, owner_a):
    client, runtime, _, _ = composed(settings, bound.bound_release(binding=_contradicted()))
    with client:
        job_id, job = collected(client, owner_a, runtime)
        dataset_id = job["dataset"]["dataset_id"]
        # Forge the saved verdict only: the rerun on the saved raw records still disagrees.
        execute(client, "update research_local.investigation_events set content = jsonb_set(content, '{result}', "
                        "'\"PASS\"') where job_id = :job and kind = 'HISTORY_PAYLOAD_BOUND'", job=job_id)
        _blocked(client, owner_a, dataset_id, "payload_binding_mismatch")
        execute(client, "delete from research_local.investigation_events where job_id = :job and "
                        "kind = 'HISTORY_PAYLOAD_BOUND'", job=job_id)
        state = client.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json()["payload_binding"]
        assert (state["status"], state["reason"]) == ("INCOMPLETE", "BINDING_EVENT_MISSING")
        _blocked(client, owner_a, dataset_id, "payload_binding_incomplete")


def test_a_checker_unavailable_at_collection_saves_incomplete_and_blocks(settings, owner_a, monkeypatch):
    client, runtime, _, _ = composed(settings)
    with client:
        job_id = started(client, owner_a, runtime)
        history_payload_binding.checker.cache_clear()
        monkeypatch.setattr(history_payload_binding, "CHECKER_SHA256", "0" * 64)
        try:
            worker(client, runtime).run_job(uuid.UUID(job_id))
        finally:
            monkeypatch.undo()
            history_payload_binding.checker.cache_clear()
        job = job_view(client, owner_a, job_id)
        assert job["state"] == "REPORTED"
        event = bound_events(client, job_id)[0]["content"]
        assert (event["result"], event["reason"], event["report"], event["checker"]) == (
            "INCOMPLETE", "CHECKER_CHANGED", None, None)
        state = job["dataset"]["payload_binding"]  # the checker is back, but the saved refusal is not upgraded
        assert (state["status"], state["reason"]) == ("INCOMPLETE", "SAVED_CHECKER_CHANGED")
        _blocked(client, owner_a, job["dataset"]["dataset_id"], "payload_binding_incomplete")


# --------------------------------------------------------------------------------------- interruption

def test_a_crash_before_the_dataset_commit_keeps_unknown_liability_and_never_collects_again(settings, owner_a,
                                                                                         monkeypatch):
    client, runtime, provider, creds = composed(settings)
    with client:
        job_id = started(client, owner_a, runtime)

        def crashed(*args: Any, **kwargs: Any) -> None:
            raise Killed()
        monkeypatch.setattr(history_payload_binding, "record_binding", crashed)
        with pytest.raises(Killed):
            worker(client, runtime).run_job(uuid.UUID(job_id))
        monkeypatch.undo()
        sent = len(provider.requests)
        assert rows(client, "select count(*) n from research_local.history_datasets where job_id = :job",
                    job=job_id)[0]["n"] == 0
        assert bound_events(client, job_id) == []
        worker(client, runtime).run_job(uuid.UUID(job_id))
        job = job_view(client, owner_a, job_id)
        assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", "collection_outcome_unknown")
        assert job["budget"]["unknown_liability"]["provider_requests"] == bound.provider_requests()
        assert len(provider.requests) == sent == bound.provider_requests()
        assert [item["kind"] for item in job["events"]].count("ATTEMPT_STARTED") == 1
        assert bound_events(client, job_id) == []


def test_a_crash_after_the_commit_reuses_one_dataset_and_one_event(settings, owner_a):
    client, runtime, provider, _ = composed(settings)
    with client:
        job_id = started(client, owner_a, runtime)

        def lost(_job_id: uuid.UUID) -> None:
            raise Killed()
        with pytest.raises(Killed):
            worker(client, runtime, after_collection_saved=lost).run_job(uuid.UUID(job_id))
        sent = len(provider.requests)
        worker(client, runtime).run_job(uuid.UUID(job_id))
        job = job_view(client, owner_a, job_id)
        assert job["state"] == "REPORTED", job["terminal_reason"]
        assert len(provider.requests) == sent == bound.provider_requests()
        assert rows(client, "select count(*) n from research_local.history_datasets where job_id = :job",
                    job=job_id)[0]["n"] == 1
        events = bound_events(client, job_id)
        assert len(events) == 1 and events[0]["content"]["result"] == "PASS"
        assert job["dataset"]["payload_binding"]["status"] == "PASS"


# --------------------------------------------------------------------------------------- configuration identity

def test_a_changed_binding_under_a_reused_configuration_id_is_the_existing_conflict(settings, owner_a):
    client, runtime, _, _ = composed(settings)
    with client:
        _job_id, job = collected(client, owner_a, runtime)
        dataset_id = job["dataset"]["dataset_id"]
        (bundle, parent), adopted = adopted_revision(client, owner_a, dataset_id)
        second, _ = publish(client, owner_a, adopted.json()["bundle"], parent=parent)
        body = replay_body(bundle, second.json()["revision_id"], dataset_id)
        first = client.post("/v1/spot-replays", headers=owner_a, json=body)
        assert first.status_code == 201, first.text
        inputs = first.json()["content"]["inputs"]
        changed = copy.deepcopy(inputs)
        changed["history_input"]["payload_binding"]["report_sha256"] = "f" * 64
        owner = uuid.UUID(first.json()["content"]["owner_id"])
        with client.app.state.session_factory() as session:
            saved_runs._bind_configuration(session, owner, body["run_configuration_id"], inputs)  # same: accepted
            with pytest.raises(AppError) as conflict:
                saved_runs._bind_configuration(session, owner, body["run_configuration_id"], changed)
        assert conflict.value.code == "run_configuration_id_reused"
        unbound = copy.deepcopy(inputs)
        del unbound["history_input"]["payload_binding"]
        with client.app.state.session_factory() as session, pytest.raises(AppError) as dropped:
            saved_runs._bind_configuration(session, owner, body["run_configuration_id"], unbound)
        assert dropped.value.code == "run_configuration_id_reused"
