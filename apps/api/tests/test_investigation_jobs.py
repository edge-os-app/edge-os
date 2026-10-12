"""#58 RG03: original investigation jobs, budget reservation before effects, and every stop and restart path.

Sources are SYNTHETIC recorded responses. A fake stop is an exception that is not an `Exception`, so it escapes the
worker exactly like a killed process: nothing after it commits.
"""

from __future__ import annotations

import ast
import datetime as dt
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import run_threads
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.research import investigation_tools
from edge_os_api.research.investigation_jobs import InvestigationWorker
from research_flows import declare, jobs_path, start


class Killed(BaseException):
    """Stands in for a killed worker process."""


def _app(env, **overrides):
    values = {**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded", "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "64",
              "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS": "3600", **overrides}
    return TestClient(create_app(load_settings(values)))


@pytest.fixture(scope="module")
def research(env, migrated):
    with _app(env) as client:
        yield client


def worker(client, **kwargs) -> InvestigationWorker:
    return InvestigationWorker(client.app.state.session_factory, client.app.state.settings, **kwargs)


def job(client, headers, job_id):
    return client.get(f"/v1/research/investigation-jobs/{job_id}", headers=headers).json()


def kinds(view):
    return [event["kind"] for event in view["events"]]


def count_collections(monkeypatch) -> list[int]:
    calls = [0]
    original = investigation_tools.collect_recorded_history

    def counted(*args, **kwargs):
        calls[0] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(investigation_tools, "collect_recorded_history", counted)
    return calls


def test_duplicate_start_returns_the_original_job_and_reserves_once(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a)
    before = research.get("/v1/research/budget", headers=owner_a).json()
    body = {"operation_id": str(uuid.uuid4()), "request_key": f"dup-{uuid.uuid4()}"}
    first = research.post(jobs_path(intake_id, declaration_id), headers=owner_a, json=body)
    again = research.post(jobs_path(intake_id, declaration_id), headers=owner_a, json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["job_id"] == first.json()["job_id"] and first.json()["state"] == "RESERVED"
    assert kinds(first.json()) == ["JOB_QUEUED", "BUDGET_RESERVED"]
    after = research.get("/v1/research/budget", headers=owner_a).json()
    assert after["reserved"]["provider_requests"] == before["reserved"]["provider_requests"] + 2
    changed = {**body, "operation_id": str(uuid.uuid4())}
    conflict = research.post(jobs_path(intake_id, declaration_id), headers=owner_a, json=changed)
    assert conflict.status_code == 409 and conflict.json()["code"] == "request_key_reused"


def test_concurrent_duplicate_start_creates_one_job(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a)
    body = {"operation_id": str(uuid.uuid4()), "request_key": f"race-{uuid.uuid4()}"}
    results = run_threads(4, lambda _: research.post(jobs_path(intake_id, declaration_id), headers=owner_a, json=body))
    assert sorted(result.status_code for result in results) == [200, 200, 200, 201]
    assert len({result.json()["job_id"] for result in results}) == 1


def test_last_budget_slot_goes_to_exactly_one_job_and_exhaustion_refuses(env, migrated, owner_a):
    with _app(env, EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS="4") as client:
        intake_id, declaration_id, _ = declare(client, owner_a)
        assert start(client, owner_a, intake_id, declaration_id).status_code == 201
        results = run_threads(3, lambda index: start(client, owner_a, intake_id, declaration_id, key=f"slot-{index}"))
        codes = sorted(result.status_code for result in results)
        assert codes == [201, 409, 409], [result.text for result in results]
        refused = [result for result in results if result.status_code == 409]
        assert {result.json()["code"] for result in refused} == {"research_budget_exhausted"}
        listed = client.get(jobs_path(intake_id, declaration_id), headers=owner_a).json()["jobs"]
        assert sorted(item["state"] for item in listed) == ["BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED", "RESERVED",
                                                            "RESERVED"]
        exhausted = next(item for item in listed if item["state"] == "BUDGET_EXHAUSTED")
        assert exhausted["budget"]["reserved"] == {"provider_requests": 0, "compute_seconds": 0}
        assert kinds(exhausted) == ["JOB_QUEUED", "BUDGET_REFUSED"]
        # Replaying a refused start repeats the refusal; it never reserves later capacity silently.
        replay = client.post(jobs_path(intake_id, declaration_id), headers=owner_a,
                             json={"operation_id": exhausted["operation_id"], "request_key": exhausted["request_key"]})
        assert replay.status_code == 409
        budget = client.get("/v1/research/budget", headers=owner_a).json()
        assert budget["available"]["provider_requests"] == 0 and budget["limits"]["provider_requests"] == 4


def test_owner_budgets_are_separate(env, migrated, owner_a, owner_b):
    with _app(env, EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS="2") as client:
        intake_a, declaration_a, _ = declare(client, owner_a)
        intake_b, declaration_b, _ = declare(client, owner_b)
        assert start(client, owner_a, intake_a, declaration_a).status_code == 201
        assert start(client, owner_b, intake_b, declaration_b).status_code == 201
        assert start(client, owner_a, intake_a, declaration_a).status_code == 409


def test_foreign_owner_cannot_read_or_cancel_a_job(research, owner_a, owner_b):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
    assert research.get(f"/v1/research/investigation-jobs/{job_id}", headers=owner_b).status_code == 404
    assert research.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_b).status_code == 404
    assert research.get(jobs_path(intake_id, declaration_id), headers=owner_b).status_code == 404
    assert job(research, owner_a, job_id)["state"] == "RESERVED"


def test_cancel_before_collection_releases_reservation_and_collects_nothing(research, owner_a, monkeypatch):
    calls = count_collections(monkeypatch)
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
    cancelled = research.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_a).json()
    assert cancelled["state"] == "CANCELLED"
    assert cancelled["budget"]["released"] == {"provider_requests": 2, "compute_seconds": 30}
    assert worker(research).run_job(uuid.UUID(job_id))["state"] == "CANCELLED"
    assert calls[0] == 0 and job(research, owner_a, job_id)["dataset"] is None


def test_cancel_during_collection_keeps_the_partial_attempt(research, owner_a, monkeypatch):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
    original = investigation_tools.collect_recorded_history

    def cancel_then_collect(source, bounds, deadline, cancelled, clock):
        research.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_a)
        return original(source, bounds, deadline, cancelled, clock)

    monkeypatch.setattr(investigation_tools, "collect_recorded_history", cancel_then_collect)
    worker(research).run_job(uuid.UUID(job_id))
    view = job(research, owner_a, job_id)
    assert view["state"] == "CANCELLED" and view["terminal_reason"] == "cancelled_during_collection"
    assert view["dataset"]["summary"]["stop_reason"] == "CANCELLED"
    assert view["dataset"]["summary"]["binding_state"] == "UNAVAILABLE_LIMITED_DATA"
    assert "ATTEMPT_FINISHED" in kinds(view) and view["report"] is None


def test_deadline_before_collection_and_during_collection(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
    late = lambda: dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)  # noqa: E731
    worker(research, clock=late).run_job(uuid.UUID(job_id))
    view = job(research, owner_a, job_id)
    assert view["state"] == "DEADLINE_EXCEEDED" and view["dataset"] is None
    assert view["budget"]["released"]["provider_requests"] == 2


def test_killed_worker_during_collection_is_not_collected_again(research, owner_a, monkeypatch):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]

    def killed(*args, **kwargs):
        raise Killed()

    monkeypatch.setattr(investigation_tools, "collect_recorded_history", killed)
    with pytest.raises(Killed):
        worker(research).run_job(uuid.UUID(job_id))
    assert job(research, owner_a, job_id)["state"] == "COLLECTING"
    monkeypatch.undo()
    calls = count_collections(monkeypatch)
    with _restarted(research) as restarted:
        worker(restarted).run_job(uuid.UUID(job_id))
        view = job(restarted, owner_a, job_id)
    assert calls[0] == 0
    assert view["state"] == "UNAVAILABLE" and view["terminal_reason"] == "collection_outcome_unknown"
    assert view["budget"]["unknown_liability"] == {"provider_requests": 2, "compute_seconds": 30}
    reconciled = next(event for event in view["events"] if event["kind"] == "ATTEMPT_RECONCILED")
    assert reconciled["content"]["outcome"] == "OUTCOME_UNKNOWN"
    started = next(event for event in view["events"] if event["kind"] == "ATTEMPT_STARTED")
    assert reconciled["content"]["attempt_id"] == started["attempt_id"]
    budget = research.get("/v1/research/budget", headers=owner_a).json()
    assert budget["unknown_liability"]["provider_requests"] >= 2


def test_lost_reply_after_saved_collection_resumes_without_a_second_collection(research, owner_a, monkeypatch):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]

    def lost(_job_id):
        raise Killed()

    with pytest.raises(Killed):
        worker(research, after_collection_saved=lost).run_job(uuid.UUID(job_id))
    assert job(research, owner_a, job_id)["state"] == "COLLECTING"
    calls = count_collections(monkeypatch)
    with _restarted(research) as restarted:
        worker(restarted).run_job(uuid.UUID(job_id))
        view = job(restarted, owner_a, job_id)
    assert calls[0] == 0 and view["state"] == "REPORTED"
    assert kinds(view).count("ATTEMPT_STARTED") == 2  # one collection, one comparison
    assert view["budget"]["consumed"]["provider_requests"] == 2


def test_missing_and_invalid_provider_usage_keep_unknown_liability(research, owner_a):
    for source_id, finding in (("recorded-syn-usage-unknown/1", "PROVIDER_USAGE_MISSING"),
                               ("recorded-syn-usage-invalid/1", "PROVIDER_USAGE_INVALID")):
        intake_id, declaration_id, _ = declare(research, owner_a, source_id=source_id)
        job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
        worker(research).run_job(uuid.UUID(job_id))
        view = job(research, owner_a, job_id)
        assert view["state"] == "REPORTED"
        assert view["budget"]["unknown_liability"]["provider_requests"] == 2
        assert view["budget"]["consumed"]["provider_requests"] == 0
        finished = next(event for event in view["events"] if event["kind"] == "ATTEMPT_FINISHED")
        assert finished["content"]["findings"][0]["finding"] == finding
        assert view["dataset"]["summary"]["provider_requests"] is None


def test_unexpected_adapter_failure_fails_the_job_and_keeps_unknown_liability(research, owner_a, monkeypatch):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]

    def broken(*args, **kwargs):
        raise RuntimeError("adapter defect")

    monkeypatch.setattr(investigation_tools, "collect_recorded_history", broken)
    worker(research).run_job(uuid.UUID(job_id))
    view = job(research, owner_a, job_id)
    assert view["state"] == "FAILED" and view["terminal_reason"] == "collection_failed"
    assert view["budget"]["unknown_liability"]["provider_requests"] == 2
    assert "adapter defect" not in str(view)


def test_retry_is_a_new_job_and_the_original_attempts_stay(research, owner_a, monkeypatch):
    intake_id, declaration_id, _ = declare(research, owner_a, source_id="recorded-syn-provider-failure/1")
    first = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
    worker(research).run_job(uuid.UUID(first))
    second = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
    assert second != first
    worker(research).run_job(uuid.UUID(second))
    listed = research.get(jobs_path(intake_id, declaration_id), headers=owner_a).json()["jobs"]
    assert [item["job_id"] for item in listed] == [first, second]
    assert all(item["report"]["content"]["outcome"] == "SOURCE_LOSS" for item in listed)


def test_second_worker_skips_a_held_job(research, owner_a, monkeypatch):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = uuid.UUID(start(research, owner_a, intake_id, declaration_id).json()["job_id"])
    inner = []
    original = investigation_tools.collect_recorded_history

    def nested(*args, **kwargs):
        inner.append(worker(research).run_job(job_id))
        return original(*args, **kwargs)

    monkeypatch.setattr(investigation_tools, "collect_recorded_history", nested)
    worker(research).run_job(job_id)
    assert inner == [None]
    assert job(research, owner_a, str(job_id))["state"] == "REPORTED"


def test_recorded_mode_is_required_and_production_refuses_it(env, migrated, owner_a):
    with _app(env, EDGE_OS_RESEARCH_HISTORY_MODE="unavailable") as client:
        intake_id, declaration_id, _ = declare(client, owner_a)
        refused = start(client, owner_a, intake_id, declaration_id)
        assert refused.status_code == 409 and refused.json()["code"] == "history_source_unavailable"
    from edge_os_api.core.settings import ConfigError
    with pytest.raises(ConfigError, match="research_history_mode"):
        load_settings({**env, "EDGE_OS_ENV": "production", "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"})


def test_research_tools_hold_no_financial_or_network_authority():
    forbidden = ("edge_os_api.execution", "edge_os_api.admission", "edge_os_api.consent", "edge_os_api.funding",
                 "edge_os_api.wallet_setup", "edge_os_api.revocation", "edge_os_api.kuru_flow", "httpx", "socket",
                 "requests", "urllib", "edge_os_api.research.hermes_interpreter")
    root = Path(__file__).resolve().parents[1] / "src" / "edge_os_api" / "research"
    for name in ("investigation_jobs.py", "investigation_tools.py", "history_dataset.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        assert not {module for module in imported if module.startswith(forbidden)}, (name, imported)


class _restarted:
    """A new application instance over the same database: nothing survives but saved rows."""

    def __init__(self, client):
        self._settings = client.app.state.settings

    def __enter__(self):
        self._client = TestClient(create_app(self._settings))
        return self._client.__enter__()

    def __exit__(self, *exc):
        return self._client.__exit__(*exc)


def test_cancel_after_collection_keeps_the_dataset_and_reports_nothing(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]

    def lost(_job_id):
        raise Killed()

    with pytest.raises(Killed):
        worker(research, after_collection_saved=lost).run_job(uuid.UUID(job_id))
    research.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_a)
    worker(research).run_job(uuid.UUID(job_id))
    view = job(research, owner_a, job_id)
    assert view["state"] == "CANCELLED" and view["terminal_reason"] == "cancelled_after_collection"
    assert view["dataset"] is not None and view["report"] is None
    assert view["budget"]["consumed"]["provider_requests"] == 2
    measured = next(event for event in view["events"] if event["kind"] == "ATTEMPT_FINISHED")["content"]["usage"]
    assert view["budget"]["consumed"]["compute_seconds"] == measured["compute_seconds"] >= 1
    assert view["budget"]["released"]["compute_seconds"] == 30 - measured["compute_seconds"]


def test_reported_job_consumes_its_measured_compute(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
    view = worker(research).run_job(uuid.UUID(job_id))
    measured = sum(event["content"]["usage"]["compute_seconds"] for event in view["events"]
                   if event["kind"] == "ATTEMPT_FINISHED")
    assert view["state"] == "REPORTED" and measured >= 2
    assert view["budget"]["consumed"]["compute_seconds"] == measured
    assert view["budget"]["released"]["compute_seconds"] == 30 - measured


def test_changed_source_is_refused_before_any_attempt(research, owner_a, monkeypatch):
    from edge_os_api.research import history_dataset

    intake_id, declaration_id, _ = declare(research, owner_a)
    job_id = start(research, owner_a, intake_id, declaration_id).json()["job_id"]
    served = history_dataset.recorded_sources()
    changed = {key: {**value, "profile": {**value["profile"], "profile_id": "changed/1"}} for key, value in served.items()}
    monkeypatch.setattr(history_dataset, "recorded_sources", lambda: changed)
    view = worker(research).run_job(uuid.UUID(job_id))
    assert view["state"] == "UNAVAILABLE" and view["terminal_reason"] == "declared_source_changed"
    assert "ATTEMPT_STARTED" not in kinds(view) and "SOURCE_REFUSED" in kinds(view)
    assert view["budget"]["released"] == {"provider_requests": 2, "compute_seconds": 30}


def test_measured_compute_beyond_a_small_bound_is_consumed_and_recorded_as_overrun(env, migrated, owner_a):
    bounds = {"provider_requests": 2, "compute_seconds": 1, "max_pages": 2, "max_rows": 200,
              "max_bytes": 1_048_576, "deadline_seconds": 600}
    with _app(env, EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS="10", EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS="10") as client:
        intake_id, declaration_id, _ = declare(client, owner_a, bounds=bounds)
        job_id = start(client, owner_a, intake_id, declaration_id).json()["job_id"]
        view = worker(client).run_job(uuid.UUID(job_id))
        measured = sum(event["content"]["usage"]["compute_seconds"] for event in view["events"]
                       if event["kind"] == "ATTEMPT_FINISHED")
        assert view["state"] == "REPORTED" and measured >= 2
        assert view["budget"]["consumed"]["compute_seconds"] == measured
        assert view["budget"]["overrun"]["compute_seconds"] == measured - 1
        assert view["budget"]["released"]["compute_seconds"] == 0
        budget = client.get("/v1/research/budget", headers=owner_a).json()
    with _app(env, EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS="10", EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS="10") as restarted:
        after = restarted.get("/v1/research/budget", headers=owner_a).json()
    assert budget == after
    assert after["consumed"]["compute_seconds"] == measured and after["reserved"]["compute_seconds"] == 0
    assert after["available"]["compute_seconds"] == 10 - measured
