"""#58 RESEARCH-RUNTIME-LOCAL: the operating-release research composition, proved with stand-in providers only.

Seam: authenticated declaration or Nansen request → saved original job → worker → release admission → composed
credentials → accepted P07 HTTP clients (or the Nansen package) over a STAND-IN transport → saved dataset or report →
public read, adoption, replay, restart and other owner. Provider request counts come from the stand-in providers,
outside the application. Expected values are written by hand from the SOURCE-LOCAL native recordings (24 swaps on two
pages; one chain read and one receipt per sampled swap) and the authored Nansen fixture (5 + 1 credits).

No actual provider, credential or network outside loopback is used. One actual release is registered in the code-owned
default; it is admitted and refused locally, but no actual provider report runs in this module.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import threading
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

import harness
import operating_release_stand_in as stand_in
from edge_os_api.core.research import operating_release, released_runtime_bootstrap
from edge_os_api.core.research.operating_release import ReleaseRefused
from edge_os_api.core.research.released_source_runtime import (
    nansen_request as released_nansen_request,
    open_released_runtime,
)
from edge_os_api.core.settings import ConfigError, load_settings
from edge_os_api.main import create_app
from edge_os_api.research.investigation_jobs import InvestigationWorker
from edge_os_api.research_history.http_clients import HttpResponse, StdlibHttpTransport
from flows import compiled_thesis, publish, submit
from research_flows import adoption_body, declare, history_body, history_replay_body, investigation_request, jobs_path

from test_actual_binding_admission import authored_actual_history

SOURCE = stand_in.SOURCE_ID
QUESTION = "Which holder records does MOE return, and what do basic flow records show?"
REGISTERED_RELEASE_ID = "actual-moe-history2h-nansen-20261022/1"
REGISTERED_RELEASE_SHA256 = "45c8cfbf5d61eb519ee3140e02e50b2b7091669dc28cbef224bdc6a0e77ca877"
REGISTERED_NANSEN_REQUEST: dict[str, Any] = {
    "token_address": "0xd8e004acba279417c04c0633cb5a21ceca207777", "token_symbol": "MOE",
    "window": {"start_utc": "2026-10-21T23:40:00Z", "end_utc": "2026-10-22T23:40:00Z"},
    "operations": ["holders", "flows"],
    "holder_query": {"label_type": "all_holders", "aggregate_by_entity": False, "order_field": "token_amount",
                     "value_usd_min": None},
    "flow_query": {"label": "top_100_holders"},
    "limits": {"max_requests": 2, "max_pages": 1, "max_bytes": 2000000, "max_credits": "6", "per_page": 100},
    "deadline_seconds": 300, "compute_seconds": 300}


@pytest.fixture(scope="module")
def env(pg, signer):
    """This module's own database: Nansen jobs and credit rows never enter the shared database."""
    name = f"{pg.database}_release_{uuid.uuid4().hex[:6]}"
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


def app(settings, runtime=None) -> TestClient:
    return TestClient(create_app(settings, research_runtime=runtime))


@pytest.fixture
def composed(settings):
    """A fresh stand-in runtime over the in-process recording, and its app."""
    runtime, provider, nansen, creds = stand_in.recording_runtime(settings)
    with app(settings, runtime) as client:
        yield {"client": client, "runtime": runtime, "provider": provider, "nansen": nansen, "creds": creds}


def worker(client, runtime=None, **kwargs) -> InvestigationWorker:
    return InvestigationWorker(client.app.state.session_factory, client.app.state.settings,
                               research_runtime=runtime, **kwargs)


def view(client, headers, job_id: str) -> dict[str, Any]:
    response = client.get(f"/v1/research/investigation-jobs/{job_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def dataset(client, headers, job: dict[str, Any]) -> dict[str, Any]:
    response = client.get(f"/v1/research/history-datasets/{job['dataset']['dataset_id']}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


def release_limits(runtime) -> dict[str, int]:
    return dict(runtime.release.history.limits)


def declare_release(client, headers, runtime, **kwargs) -> tuple[str, str]:
    intake_id, declaration_id, _ = declare(client, headers, source_id=SOURCE, bounds=release_limits(runtime), **kwargs)
    return intake_id, declaration_id


def start(client, headers, intake_id: str, declaration_id: str, key: str | None = None):
    return client.post(jobs_path(intake_id, declaration_id), headers=headers,
                       json={"operation_id": str(uuid.uuid4()), "request_key": key or f"release-{uuid.uuid4()}"})


def started_job(client, headers, runtime) -> str:
    intake_id, declaration_id = declare_release(client, headers, runtime)
    response = start(client, headers, intake_id, declaration_id)
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


# --------------------------------------------------------------------------------------- composition default

def test_the_default_composes_only_the_registered_release_and_provider_keys_change_nothing(settings, env, owner_a):
    keyed = load_settings({**env, "HYPERSYNC_API_KEY": "x", "QUICKNODE_API_URL": "https://example.invalid/k/",
                           "NANSEN_API_KEY": "y", "EDGE_OS_RESEARCH_OPERATING_RELEASE": "stand-in-native/1"})
    with app(keyed) as client:
        sources = client.get("/v1/research/history-sources", headers=owner_a).json()
        assert SOURCE not in {item["source_id"] for item in sources["sources"]}  # no stand-in source is served
        runtime = client.app.state.research_runtime  # the server bootstrap composes the registered release
        assert runtime is not None and runtime.release.history is not None and runtime.release.nansen is not None
        assert (runtime.release.release_id, runtime.release_sha256) == (REGISTERED_RELEASE_ID,
                                                                       REGISTERED_RELEASE_SHA256)
        assert sources["operating_release"]["sha256"] == REGISTERED_RELEASE_SHA256
        # A provider key, an environment value or a request cannot add a release or change its class: the composed one
        # is the registered ACTUAL release, never `stand-in-native/1` and never a stand-in.
        assert sources["operating_release"]["kind"] == "ACTUAL"
        assert runtime.release.release_id != "stand-in-native/1"
        listed = client.get(f"/v1/research/requests/{investigation_request(client, owner_a)['intake']['record_id']}"
                            "/nansen-reports", headers=owner_a).json()
        assert listed["available"] is True and listed["operating_release"]["sha256"] == REGISTERED_RELEASE_SHA256


def test_an_explicitly_emptied_registry_composes_no_release_and_lists_nothing(settings, env, owner_a, monkeypatch):
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", {})
    with app(load_settings({**env})) as client:
        sources = client.get("/v1/research/history-sources", headers=owner_a).json()
        assert sources["operating_release"] is None
        listed = client.get(f"/v1/research/requests/{investigation_request(client, owner_a)['intake']['record_id']}"
                            "/nansen-reports", headers=owner_a).json()
        assert listed == {"available": False, "jobs": []}  # unchanged when no release is composed
        assert client.app.state.research_runtime is None  # an explicitly emptied registry composes nothing


def test_a_stand_in_release_is_listed_with_its_fixed_bounds_and_stand_in_class(composed, owner_a):
    client, runtime = composed["client"], composed["runtime"]
    catalog = client.get("/v1/research/history-sources", headers=owner_a).json()
    entry = next(item for item in catalog["sources"] if item["source_id"] == SOURCE)
    assert (entry["evidence_class"], entry["content_label"], entry["available"]) == (
        "RELEASE_STAND_IN_RESPONSE", "SYNTHETIC_FIXTURE", True)
    release = entry["release"]
    assert (release["release_id"], release["kind"], release["transport_kind"]) == (
        "stand-in-native/1", "STAND_IN", "IN_PROCESS_RECORDING")
    assert release["sha256"] == runtime.release_sha256 == catalog["operating_release"]["sha256"]
    assert release["history"]["limits"] == {"provider_requests": 27, "compute_seconds": 30, "max_pages": 2,
                                            "max_rows": 200, "max_bytes": 1_048_576, "deadline_seconds": 600}
    assert release["history"]["endpoint_hosts"] == {"ENVIO_HYPERSYNC": "hypersync.stand-in.invalid",
                                                    "QUICKNODE_JSON_RPC": "quicknode.stand-in.invalid"}
    assert entry["transport"]["provider_requests_needed"] == 27
    assert not any(value in json.dumps(catalog) for value in stand_in.SENTINELS)
    assert composed["creds"].reads == [] and composed["provider"].requests == []


# --------------------------------------------------------------------------------------- history happy path

def test_a_release_job_runs_the_p07_http_clients_over_the_stand_in_and_saves_labelled_evidence(composed, owner_a):
    client, runtime, provider, creds = (composed[k] for k in ("client", "runtime", "provider", "creds"))
    job_id = started_job(client, owner_a, runtime)
    assert creds.reads == [] and provider.requests == []  # nothing is read or sent before the worker
    worker(client, runtime).run_job(uuid.UUID(job_id))
    job = view(client, owner_a, job_id)
    assert job["state"] == "REPORTED", job["terminal_reason"]
    assert creds.reads == [stand_in.ENVIO_SLOT, stand_in.QUICKNODE_SLOT]
    assert [item["kind"] for item in provider.requests].count("envio") == 2
    assert [item["kind"] for item in provider.requests].count("rpc") == 25
    content = dataset(client, owner_a, job)
    assert (content["evidence_class"], content["content_label"], content["profile_evidence_class"]) == (
        "RELEASE_STAND_IN_RESPONSE", "SYNTHETIC_FIXTURE", "SYNTHETIC_FIXTURE")
    assert content["operating_release"] == {"release_id": "stand-in-native/1", "sha256": runtime.release_sha256,
                                            "kind": "STAND_IN"}
    assert content["transport_kind"] == "IN_PROCESS_RECORDING"
    transport = content["transport"]
    assert transport["clients"] == "P07_HTTP_CLIENTS_OPERATING_RELEASE"
    assert transport["client_classes"] == {"ENVIO_HYPERSYNC": "HttpEnvioQueryClient",
                                           "QUICKNODE_JSON_RPC": "HttpQuickNodeRpcClient"}
    assert transport["client_calls"] == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 25}
    assert len(transport["request_sha256"]) == len(transport["response_sha256"]) == 27
    assert transport["request_sha256"] == [item["body_sha256"] for item in provider.requests]
    assert set(transport["response_status"]) == {200}
    assert content["evidence_basis"]["chain_id"] == "CHECKED_AGAINST_STAND_IN_RPC"
    assert content["evidence_basis"]["decimals"] == "RELEASE_DECLARATION"
    assert content["verdict"]["overall"] == "QUALIFIED" and content["binding_state"] == "QUALIFIED_BINDING"
    assert content["query_sha256"] and content["coverage"]["covers_requested_scan"] is True
    assert content["release_coverage"] == {"required": "COMPLETE_SCAN", "met": True}
    times = content["application_collection_time"]
    assert times["basis"] == "APPLICATION_CLOCK" and times["started_at"] <= times["finished_at"]
    assert "Stand-in responses" in content["notice"]
    assert (content["provider_requests_state"], job["budget"]["consumed"]["provider_requests"]) == (
        "MEASURED_CLIENT_CALLS", 27)
    started = next(event for event in job["events"] if event["kind"] == "ATTEMPT_STARTED")
    assert started["content"]["operating_release"]["sha256"] == runtime.release_sha256
    assert started["content"]["evidence_class"] == "RELEASE_STAND_IN_RESPONSE"
    assert not any(value in json.dumps(job) + json.dumps(content) for value in stand_in.SENTINELS)
    summary = job["dataset"]["transport"]
    assert (summary["clients"], summary["transport_kind"], summary["operating_release"]["release_id"]) == (
        "P07_HTTP_CLIENTS_OPERATING_RELEASE", "IN_PROCESS_RECORDING", "stand-in-native/1")
    report = job["report"]["content"]
    assert report["evidence_class"] == "RELEASE_STAND_IN_RESPONSE"
    # An unbound release keeps its behavior: no binding event, no requirement, and nothing is required of consumers.
    assert job["dataset"]["payload_binding"]["status"] == "NOT_REQUIRED"
    assert "HISTORY_PAYLOAD_BOUND" not in [event["kind"] for event in job["events"]]
    assert "payload_binding_requirement" not in content and "payload_binding_requirement" not in started["content"]
    # Reopening reads the saved rows: no credential read and no provider request.
    reads, sent = len(creds.reads), len(provider.requests)
    assert view(client, owner_a, job_id) == job
    worker(client, runtime).run_job(uuid.UUID(job_id))
    assert (len(creds.reads), len(provider.requests)) == (reads, sent)


# --------------------------------------------------------------------------------------- admission

class Killed(BaseException):
    """A worker stopped mid-call, as a killed process stops."""


def budget(client, headers) -> dict[str, Any]:
    return client.get("/v1/research/budget", headers=headers).json()


def test_a_declaration_must_use_the_release_limits_and_its_served_class(composed, owner_a):
    client, runtime = composed["client"], composed["runtime"]
    bundle = investigation_request(client, owner_a)
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations"
    wider = {**release_limits(runtime), "provider_requests": 40}
    refused = client.post(path, headers=owner_a, json=history_body(client, owner_a, bundle, source_id=SOURCE,
                                                                    bounds=wider))
    assert (refused.status_code, refused.json()["code"]) == (422, "release_bounds_mismatch")
    for claimed, status, code in (("PROVIDER_ACTUAL", 409, "actual_data_not_authorized"),
                                  ("AUTHORED_HTTP_RESPONSE", 422, "history_source_class_mismatch")):
        body = history_body(client, owner_a, bundle, source_id=SOURCE, bounds=release_limits(runtime))
        body["configuration"]["source"]["evidence_class"] = claimed
        body["configuration"]["permitted_access"] = [claimed]
        response = client.post(path, headers=owner_a, json=body)
        assert (response.status_code, response.json()["code"]) == (status, code)
    saved = client.post(path, headers=owner_a, json=history_body(client, owner_a, bundle, source_id=SOURCE,
                                                                  bounds=release_limits(runtime)))
    assert saved.status_code == 201, saved.text
    frozen = saved.json()["declaration"]["content"]["frozen"]
    assert (frozen["operating_release_id"], frozen["operating_release_sha256"]) == (
        "stand-in-native/1", runtime.release_sha256)
    assert composed["creds"].reads == [] and composed["provider"].requests == []


def test_without_the_release_a_saved_declaration_cannot_start_and_a_saved_job_ends_before_effect(
        settings, composed, owner_a, monkeypatch):
    client, runtime = composed["client"], composed["runtime"]
    intake_id, declaration_id = declare_release(client, owner_a, runtime)
    queued = started_job(client, owner_a, runtime)
    before = budget(client, owner_a)
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", {})  # truly no composed release
    with app(settings) as plain:
        refused = start(plain, owner_a, intake_id, declaration_id)
        assert (refused.status_code, refused.json()["code"]) == (409, "operating_release_unavailable")
        assert budget(plain, owner_a) == before
        worker(plain).run_job(uuid.UUID(queued))
        job = view(plain, owner_a, queued)
    assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", "operating_release_unavailable")
    assert job["budget"]["released"]["provider_requests"] == 27 and job["budget"]["unknown_liability"] == {
        "provider_requests": 0, "compute_seconds": 0}
    assert "ATTEMPT_STARTED" not in [event["kind"] for event in job["events"]]
    assert composed["creds"].reads == [] and composed["provider"].requests == []


def test_a_changed_release_is_refused_at_start_and_at_the_worker_before_any_credential_read(settings, composed,
                                                                                            owner_a):
    client, runtime = composed["client"], composed["runtime"]
    intake_id, declaration_id = declare_release(client, owner_a, runtime)
    queued = started_job(client, owner_a, runtime)
    changed = stand_in.stand_in_release(release_id="stand-in-native/2")
    other, provider, _, creds = stand_in.recording_runtime(settings, release=changed)
    assert other.release_sha256 != runtime.release_sha256
    with app(settings, other) as client2:
        refused = start(client2, owner_a, intake_id, declaration_id)
        assert (refused.status_code, refused.json()["code"]) == (409, "operating_release_changed")
        worker(client2, other).run_job(uuid.UUID(queued))
        job = view(client2, owner_a, queued)
    assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", "operating_release_changed")
    assert job["budget"]["released"]["provider_requests"] == 27
    assert creds.reads == [] and provider.requests == [] and composed["provider"].requests == []


class _BrokenCredentials:
    """A credential source that fails with its own error; the detail must never be saved or shown."""

    def __init__(self) -> None:
        self.reads: list[str] = []

    def read(self, slot: str) -> str:
        self.reads.append(slot)
        raise PermissionError("secret-store-detail-SENTINEL")


@pytest.mark.parametrize("problem,reason", [
    ("missing", "operating_release_credential_unavailable"),
    ("foreign_host", "operating_release_endpoint_mismatch"),
    ("malformed_url", "operating_release_endpoint_mismatch"),  # review B4: refused before the attempt is saved
    ("broken_source", "operating_release_credential_unavailable")])  # review B6: one read, no retry loop
def test_a_missing_or_foreign_credential_ends_the_job_before_any_request(settings, owner_a, problem, reason):
    creds = {"missing": lambda: stand_in.credentials(missing=(stand_in.QUICKNODE_SLOT,)),
             "foreign_host": lambda: stand_in.credentials(
                 quicknode="https://quicknode.elsewhere.invalid" + stand_in.QUICKNODE_KEY_PATH),
             "malformed_url": lambda: stand_in.credentials(
                 quicknode="https://user:pw@quicknode.stand-in.invalid" + stand_in.QUICKNODE_KEY_PATH),
             "broken_source": _BrokenCredentials}[problem]()
    runtime, provider, _, creds = stand_in.recording_runtime(settings, creds=creds)
    with app(settings, runtime) as client:
        job_id = started_job(client, owner_a, runtime)
        worker(client, runtime).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
    assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", reason)
    assert job["budget"]["released"] == {"provider_requests": 27, "compute_seconds": 30}
    assert provider.requests == [] and "ATTEMPT_STARTED" not in [event["kind"] for event in job["events"]]
    assert not any(value in json.dumps(job) for value in (*stand_in.SENTINELS, "secret-store-detail-SENTINEL"))
    if problem == "broken_source":
        assert len(creds.reads) == 1  # the job ended at the first failed read; no later pass reads again


def test_a_budget_refusal_reads_no_credential_and_sends_nothing(env, owner_a):
    small = load_settings({**env, "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "26"})
    runtime, provider, _, creds = stand_in.recording_runtime(small)
    with app(small, runtime) as client:
        intake_id, declaration_id = declare_release(client, owner_a, runtime)
        refused = start(client, owner_a, intake_id, declaration_id)
        assert (refused.status_code, refused.json()["code"]) == (409, "research_budget_exhausted")
        jobs = client.get(jobs_path(intake_id, declaration_id), headers=owner_a).json()["jobs"]
    assert [job["state"] for job in jobs] == ["BUDGET_EXHAUSTED"]
    assert jobs[0]["budget"]["reserved"]["provider_requests"] == 0
    assert creds.reads == [] and provider.requests == []


def test_concurrent_starts_keep_one_original_job_per_key_and_one_reservation(composed, owner_a):
    client, runtime = composed["client"], composed["runtime"]
    intake_id, declaration_id = declare_release(client, owner_a, runtime)
    body = {"operation_id": str(uuid.uuid4()), "request_key": "release-concurrent"}
    results: list[Any] = []

    def go() -> None:
        results.append(client.post(jobs_path(intake_id, declaration_id), headers=owner_a, json=body))
    threads = [threading.Thread(target=go) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(response.status_code for response in results) == [200, 200, 200, 201]
    assert len({response.json()["job_id"] for response in results}) == 1
    jobs = client.get(jobs_path(intake_id, declaration_id), headers=owner_a).json()["jobs"]
    assert len(jobs) == 1 and jobs[0]["budget"]["reserved"]["provider_requests"] == 27


def test_concurrent_starts_cannot_overspend_the_owner_cap(env, owner_a):
    capped = load_settings({**env, "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "54"})
    runtime, provider, _, _ = stand_in.recording_runtime(capped)
    with app(capped, runtime) as client:
        intake_id, declaration_id = declare_release(client, owner_a, runtime)
        results: list[Any] = []
        threads = [threading.Thread(target=lambda: results.append(start(client, owner_a, intake_id, declaration_id)))
                   for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        states = sorted(job["state"] for job in client.get(jobs_path(intake_id, declaration_id),
                                                           headers=owner_a).json()["jobs"])
    assert sorted(response.status_code for response in results) == [201, 201, 409]
    assert states == ["BUDGET_EXHAUSTED", "RESERVED", "RESERVED"] and provider.requests == []


def test_another_owner_cannot_start_read_or_cancel_a_release_job(composed, owner_a, owner_b):
    client, runtime = composed["client"], composed["runtime"]
    intake_id, declaration_id = declare_release(client, owner_a, runtime)
    assert start(client, owner_b, intake_id, declaration_id).status_code == 404
    job_id = started_job(client, owner_a, runtime)
    worker(client, runtime).run_job(uuid.UUID(job_id))
    job = view(client, owner_a, job_id)
    for path in (f"/v1/research/investigation-jobs/{job_id}",
                 f"/v1/research/history-datasets/{job['dataset']['dataset_id']}",
                 f"/v1/research/investigation-reports/{job['report']['report_id']}",
                 jobs_path(intake_id, declaration_id)):
        assert client.get(path, headers=owner_b).status_code == 404
    assert client.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_b).status_code == 404


# --------------------------------------------------------------------------------------- interruption

def test_a_cancel_before_the_worker_reads_and_sends_nothing(composed, owner_a):
    client, runtime = composed["client"], composed["runtime"]
    job_id = started_job(client, owner_a, runtime)
    assert client.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_a).status_code == 200
    worker(client, runtime).run_job(uuid.UUID(job_id))
    job = view(client, owner_a, job_id)
    assert job["state"] == "CANCELLED" and job["budget"]["released"]["provider_requests"] == 27
    assert composed["creds"].reads == [] and composed["provider"].requests == []


def test_a_cancel_after_the_first_page_stops_before_the_next_request(composed, owner_a):
    client, runtime, provider = composed["client"], composed["runtime"], composed["provider"]
    job_id = started_job(client, owner_a, runtime)

    def cancel_during_first(index: int, kind: str) -> None:
        if index == 1:
            assert client.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_a).status_code == 200
        return None
    provider.fault = cancel_during_first
    worker(client, runtime).run_job(uuid.UUID(job_id))
    job = view(client, owner_a, job_id)
    assert job["state"] == "CANCELLED", job["terminal_reason"]
    assert len(provider.requests) == 1  # the next call was refused before it was made
    # The accepted client saw the cancel after the first reply arrived, so that reply is not a completed call: the
    # whole request reservation stays unknown liability (conservative, never zero).
    assert job["budget"]["unknown_liability"]["provider_requests"] == 27


def test_the_deadline_bounds_each_call_and_refuses_the_next_one(composed, owner_a):
    client, runtime, provider = composed["client"], composed["runtime"], composed["provider"]
    job_id = started_job(client, owner_a, runtime)
    deadline = dt.datetime.fromisoformat(view(client, owner_a, job_id)["deadline_at"].replace("Z", "+00:00"))
    now = {"at": deadline - dt.timedelta(seconds=5)}
    seen: list[float] = []

    def late(index: int, kind: str) -> None:
        now["at"] = deadline + dt.timedelta(seconds=1)  # the job deadline passes during the first call
        return None
    provider.fault = late
    original = stand_in.RecordingStandInTransport.request

    def measured(self, **kwargs):
        import time
        seen.append(kwargs["deadline"] - time.monotonic())
        return original(self, **kwargs)
    stand_in.RecordingStandInTransport.request = measured
    try:
        worker(client, runtime, clock=lambda: now["at"]).run_job(uuid.UUID(job_id))
    finally:
        stand_in.RecordingStandInTransport.request = original
    job = view(client, owner_a, job_id)
    assert job["state"] == "DEADLINE_EXCEEDED", job["terminal_reason"]
    assert len(provider.requests) == 1 and seen[0] <= 5.0  # one call, bounded by the 5 s the job had left
    assert job["budget"]["consumed"]["provider_requests"] == 1


def test_each_later_call_is_bounded_by_the_time_the_job_has_left(composed, owner_a):
    """Review A F1 / B B3: the bound applies to every physical request, not only the first one."""
    import time

    client, runtime, provider = composed["client"], composed["runtime"], composed["provider"]
    job_id = started_job(client, owner_a, runtime)
    deadline = dt.datetime.fromisoformat(view(client, owner_a, job_id)["deadline_at"].replace("Z", "+00:00"))
    frozen_now = deadline - dt.timedelta(seconds=5)  # the job clock never passes the deadline by itself
    seen: list[float] = []
    original = stand_in.RecordingStandInTransport.request

    def measured(self, **kwargs):
        seen.append(kwargs["deadline"] - time.monotonic())
        time.sleep(1.2)  # each stand-in reply takes 1.2 s of real time
        return original(self, **kwargs)
    stand_in.RecordingStandInTransport.request = measured
    try:
        worker(client, runtime, clock=lambda: frozen_now).run_job(uuid.UUID(job_id))
    finally:
        stand_in.RecordingStandInTransport.request = original
    job = view(client, owner_a, job_id)
    content = dataset(client, owner_a, job)
    assert len(seen) >= 2 and seen[0] <= 5.0 and seen[1] <= 3.9  # the second call had at most ~3.8 s left
    assert all(later < earlier for earlier, later in zip(seen, seen[1:]))
    assert 2 <= len(provider.requests) <= 5  # no request is sent once the 5 s have passed
    # The two pages finish early, so page collection itself may be complete; the deadline falls during the QuickNode
    # reads. Its effects are on the corroboration, the client accounting, the saved usage and the reservation.
    transport = content["transport"]
    assert transport["request_sha256"] == [item["body_sha256"] for item in provider.requests]  # refused = not sent
    assert transport["corroboration"]["missingness"]["rpc_failed"] >= 1  # receipts cut off by the deadline
    assert transport["http_accounting"]["QUICKNODE_JSON_RPC"]["unknown_liability"] >= 1  # late or unsent calls
    assert content["provider_requests_state"] == "UNKNOWN" and content["provider_requests"] is None
    assert job["budget"]["unknown_liability"]["provider_requests"] == 27
    assert job["budget"]["consumed"]["provider_requests"] == 0


def test_a_setup_delay_in_the_worker_does_not_extend_the_saved_deadline(composed, owner_a, monkeypatch):
    """Controller dw-l2-clock3.md (review B R2-N2): a delay between the attempt commit and the client build is not
    added back to the job's time. The worker clock follows real time from 5 s before the saved deadline."""
    import time

    from edge_os_api.research import investigation_tools

    client, runtime, provider = composed["client"], composed["runtime"], composed["provider"]
    job_id = started_job(client, owner_a, runtime)
    deadline = dt.datetime.fromisoformat(view(client, owner_a, job_id)["deadline_at"].replace("Z", "+00:00"))
    t0, start = time.monotonic(), deadline - dt.timedelta(seconds=5)
    seen: list[float] = []
    original_collect = investigation_tools.collect_recorded_history
    original_request = stand_in.RecordingStandInTransport.request

    def delayed_collect(*args, **kwargs):
        time.sleep(1.0)  # setup work after the attempt commit, before the clients are built
        return original_collect(*args, **kwargs)

    def measured(self, **kwargs):
        seen.append(kwargs["deadline"] - time.monotonic())
        return original_request(self, **kwargs)
    monkeypatch.setattr(investigation_tools, "collect_recorded_history", delayed_collect)
    monkeypatch.setattr(stand_in.RecordingStandInTransport, "request", measured)
    worker(client, runtime, clock=lambda: start + dt.timedelta(seconds=time.monotonic() - t0)).run_job(uuid.UUID(job_id))
    assert seen and seen[0] <= 4.05  # about 4 s were left when the first request was sent, not 5


def test_a_release_that_reuses_a_recorded_source_id_cannot_be_composed(settings):
    runtime = stand_in.recording_runtime(settings, release=stand_in.stand_in_release(
        source_id="native-syn-qualified/1"))[0]
    with pytest.raises(ConfigError, match="operating_release_invalid"):
        create_app(settings, research_runtime=runtime)
    with pytest.raises(ReleaseRefused):
        InvestigationWorker(None, settings, research_runtime=runtime)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_a_refused_page_stops_with_a_stable_code_no_retry_and_no_provider_text(composed, owner_a, status):
    client, runtime, provider = composed["client"], composed["runtime"], composed["provider"]
    provider.fault = lambda index, kind: HttpResponse(
        status=status, headers={"content-type": "application/json"},
        body=b'{"error":"provider-private-detail-7731"}') if index == 1 else None
    job_id = started_job(client, owner_a, runtime)
    worker(client, runtime).run_job(uuid.UUID(job_id))
    job = view(client, owner_a, job_id)
    content = dataset(client, owner_a, job)
    assert (content["status"], content["stop_reason"]) == ("PARTIAL", "PROVIDER_ERROR")
    assert len(provider.requests) == 1 and content["transport"]["response_status"] == [status]
    assert "provider-private-detail-7731" not in json.dumps(job) + json.dumps(content)
    assert content["binding_state"] == "UNAVAILABLE_LIMITED_DATA" and job["report"]["content"]["outcome"] == "SOURCE_LOSS"


def test_a_lost_reply_keeps_the_whole_request_reservation_unknown(composed, owner_a):
    client, runtime, provider = composed["client"], composed["runtime"], composed["provider"]

    def lose(index: int, kind: str) -> None:
        if index == 3:
            raise OSError("stand-in: the reply was lost")
        return None
    provider.fault = lose
    job_id = started_job(client, owner_a, runtime)
    worker(client, runtime).run_job(uuid.UUID(job_id))
    job = view(client, owner_a, job_id)
    content = dataset(client, owner_a, job)
    assert content["provider_requests_state"] == "UNKNOWN"
    assert job["budget"]["unknown_liability"]["provider_requests"] == 27
    assert None in content["transport"]["response_status"]


def test_a_worker_killed_after_the_attempt_never_collects_again(composed, owner_a):
    client, runtime, provider, creds = (composed[k] for k in ("client", "runtime", "provider", "creds"))

    def killed(index: int, kind: str) -> None:
        raise Killed()
    provider.fault = killed
    job_id = started_job(client, owner_a, runtime)
    with pytest.raises(Killed):
        worker(client, runtime).run_job(uuid.UUID(job_id))
    provider.fault = None
    sent = len(provider.requests)
    restarted = stand_in.recording_runtime(client.app.state.settings, provider=provider, creds=creds)[0]
    worker(client, restarted).run_job(uuid.UUID(job_id))
    job = view(client, owner_a, job_id)
    assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", "collection_outcome_unknown")
    assert job["budget"]["unknown_liability"]["provider_requests"] == 27
    assert len(provider.requests) == sent == 1
    assert [event["kind"] for event in job["events"]].count("ATTEMPT_STARTED") == 1


# --------------------------------------------------------------------------------------- histories

@pytest.mark.parametrize("recording_id,verdict,outcome,unavailable", [
    ("native-syn-sampled/1", "LIMITED", "LIMITED_DATA", ["VERDICT_LIMITED"]),
    ("native-syn-receipt-mismatch/1", None, None, None),
    ("native-syn-provider-failure/1", None, "SOURCE_LOSS", None),
    ("native-syn-wrong-chain/1", "UNRESOLVED", "LIMITED_DATA", ["VERDICT_UNRESOLVED"])])
def test_limited_contrary_and_lost_histories_stay_as_collected(settings, owner_a, recording_id, verdict, outcome,
                                                               unavailable):
    runtime, provider, _, _ = stand_in.recording_runtime(settings, recording_id=recording_id)
    with app(settings, runtime) as client:
        job_id = started_job(client, owner_a, runtime)
        worker(client, runtime).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
        content = dataset(client, owner_a, job)
    assert job["state"] == "REPORTED", job["terminal_reason"]
    assert content["evidence_class"] == "RELEASE_STAND_IN_RESPONSE"
    assert content["binding_state"] == "UNAVAILABLE_LIMITED_DATA" and content["market_binding_id"] is None
    assert content["verdict"]["overall"] != "QUALIFIED"
    if verdict:
        assert content["verdict"]["overall"] == verdict
    if outcome:
        assert job["report"]["content"]["outcome"] == outcome
    if unavailable:
        assert content["unavailable_states"] == unavailable
    if recording_id == "native-syn-receipt-mismatch/1":
        assert content["transport"]["corroboration"]["mismatches"] >= 1
    if recording_id == "native-syn-provider-failure/1":
        assert (content["status"], content["stop_reason"]) == ("PARTIAL", "PROVIDER_ERROR")
        assert content["release_coverage"] == {"required": "COMPLETE_SCAN", "met": False}


def test_a_qualified_release_history_with_late_delivery_reports_insufficient_data_without_a_claim(settings, owner_a):
    runtime, provider, _, _ = stand_in.recording_runtime(settings, recording_id="native-syn-late-delivery/1")
    with app(settings, runtime) as client:
        job_id = started_job(client, owner_a, runtime)
        worker(client, runtime).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
    report = job["report"]["content"]
    assert (job["state"], report["outcome"]) == ("REPORTED", "INSUFFICIENT_DATA")
    assert (report["claims"]["significance"], report["claims"]["capital_authority"]) == ("NOT_CLAIMED", "NONE")
    assert report["evidence_class"] == "RELEASE_STAND_IN_RESPONSE" and len(provider.requests) == 27


# --------------------------------------------------------------------------------------- rules, replay, restart

def test_a_release_dataset_feeds_adoption_and_a_labelled_replay_and_reopens_after_restart(settings, composed,
                                                                                          owner_a, owner_b):
    client, runtime, provider, creds = (composed[k] for k in ("client", "runtime", "provider", "creds"))
    job_id = started_job(client, owner_a, runtime)
    worker(client, runtime).run_job(uuid.UUID(job_id))
    dataset_id = view(client, owner_a, job_id)["dataset"]["dataset_id"]
    listed = next(item for item in client.get("/v1/research/history-datasets", headers=owner_a).json()["datasets"]
                  if item["dataset_id"] == dataset_id)
    bundle = compiled_thesis(client, owner_a)
    first, _ = publish(client, owner_a, bundle)
    parent = first.json()["revision_id"]
    adopted = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions", headers=owner_a,
                          json=adoption_body(bundle, dataset_id, parent=parent,
                                             evaluation_id=listed["declared_rules"][0]["evaluation_id"],
                                             quote_unit="QUOTE:0x" + "d2" * 20))
    assert adopted.status_code == 201, adopted.text
    second, _ = publish(client, owner_a, adopted.json()["bundle"], parent=parent)
    assert second.status_code == 201, second.text
    start_at = dt.datetime.fromisoformat(listed["window_start"].replace("Z", "+00:00")) + dt.timedelta(minutes=15)
    body = history_replay_body(bundle["head"]["strategy_id"], second.json()["revision_id"], dataset_id,
                               start=start_at.strftime("%Y-%m-%dT%H:%M:%SZ"), end=listed["readable_until"])
    replayed = client.post("/v1/spot-replays", headers=owner_a, json=body)
    assert replayed.status_code in (200, 201), replayed.text
    replay = replayed.json()
    lineage = replay["content"]["inputs"]["history_input"]
    assert replay["content"]["result"]["status"] == "COMPLETE", replay["content"]["result"].get("reason")
    assert (lineage["source_evidence_class"], lineage["fill_label"], lineage["rule_linkage"]["state"]) == (
        "RELEASE_STAND_IN_RESPONSE", "simulated fills", "ENTRY_IS_DECLARED_RULE")
    assert "payload_binding" not in lineage and "payload_binding" not in adopted.json()["adoption"]
    assert listed["payload_binding"]["status"] == "NOT_REQUIRED"
    assert client.get(f"/v1/spot-replays/{replay['replay_id']}", headers=owner_b).status_code == 404
    before = {"job": view(client, owner_a, job_id),
              "dataset": client.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json(),
              "replay": client.get(f"/v1/spot-replays/{replay['replay_id']}", headers=owner_a).json()}
    sent, reads = len(provider.requests), len(creds.reads)
    # A new API process and a new worker on the same database, with the same release composed again.
    again, provider2, _, creds2 = stand_in.recording_runtime(settings)
    assert again.release_sha256 == runtime.release_sha256
    with app(settings, again) as restarted:
        worker(restarted, again).run_job(uuid.UUID(job_id))
        after = {"job": view(restarted, owner_a, job_id),
                 "dataset": restarted.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json(),
                 "replay": restarted.get(f"/v1/spot-replays/{replay['replay_id']}", headers=owner_a).json()}
    assert after == before and after["dataset"]["hashes_verified"] == {"content_sha256": True,
                                                                       "raw_evidence_sha256": True}
    assert (len(provider.requests), len(creds.reads), provider2.requests, creds2.reads) == (sent, reads, [], [])


# --------------------------------------------------------------------------------------- loopback stand-in

def test_the_accepted_network_transport_reaches_only_the_loopback_stand_in(settings, owner_a, tmp_path):
    server = stand_in.LoopbackStandInProvider("native-syn-qualified/1", tmp_path / "requests.jsonl").start()
    try:
        runtime, creds = stand_in.loopback_runtime(settings, server)
        assert runtime.network_transport and runtime.transport_kind == "LOOPBACK_HTTP"
        with app(settings, runtime) as client:
            job_id = started_job(client, owner_a, runtime)
            assert server.entries() == []
            worker(client, runtime).run_job(uuid.UUID(job_id))
            job = view(client, owner_a, job_id)
            content = dataset(client, owner_a, job)
            entries = server.entries()
            worker(client, runtime).run_job(uuid.UUID(job_id))
            assert server.entries() == entries  # reopening and another pass send nothing
    finally:
        server.stop()
    assert job["state"] == "REPORTED", job["terminal_reason"]
    assert [entry["kind"] for entry in entries].count("envio") == 2 and len(entries) == 27
    assert all(entry["authorized"] and entry["status"] == 200 for entry in entries)
    assert content["transport"]["request_sha256"] == [entry["body_sha256"] for entry in entries]
    assert (content["transport_kind"], content["evidence_class"]) == ("LOOPBACK_HTTP", "RELEASE_STAND_IN_RESPONSE")
    assert content["transport"]["endpoint_hosts"] == {"ENVIO_HYPERSYNC": "127.0.0.1", "QUICKNODE_JSON_RPC": "127.0.0.1"}
    assert job["budget"]["consumed"]["provider_requests"] == 27
    assert not any(value in json.dumps(content) + json.dumps(job) for value in stand_in.SENTINELS)


# --------------------------------------------------------------------------------------- release validation

def test_release_validation_refuses_before_any_credential_read(settings, monkeypatch):
    creds = stand_in.credentials()
    refusals = {}
    cases = {
        "unapproved_actual": (stand_in.stand_in_release(), "ACTUAL", StdlibHttpTransport),
        "stand_in_real_host": (stand_in.stand_in_release(envio_endpoint="https://monad.hypersync.xyz", nansen=False),
                               None, stand_in.RecordingStandIn().transport),
        "unknown_kind": (dataclasses.replace(stand_in.stand_in_release(nansen=False), kind="actual"), None,
                         stand_in.RecordingStandIn().transport),
        "limits_too_small": (stand_in.stand_in_release(limits={"provider_requests": 3, "compute_seconds": 30,
                                                               "max_pages": 2, "max_rows": 200,
                                                               "max_bytes": 1_048_576, "deadline_seconds": 600},
                                                       nansen=False),
                             None, stand_in.RecordingStandIn().transport),
    }
    for name, (release, kind, transport) in cases.items():
        if kind == "ACTUAL":
            release = operating_release.OperatingRelease(
                release.release_id, "ACTUAL", history=authored_actual_history(stand_in.stand_in_release(
                    envio_endpoint="https://hypersync.actual-test.example", quicknode_host="quicknode.actual-test.example",
                    nansen=False).history))
        with pytest.raises(ReleaseRefused) as refused:
            open_released_runtime(settings, release, credentials=creds, http_transport=transport)
        refusals[name] = refused.value.code
    assert refusals == {"unapproved_actual": "operating_release_not_approved",
                        "stand_in_real_host": "stand_in_endpoint_not_local",
                        "unknown_kind": "operating_release_invalid",
                        "limits_too_small": "operating_release_invalid"}
    actual = operating_release.OperatingRelease("actual-test/1", "ACTUAL", history=authored_actual_history(stand_in.stand_in_release(
        envio_endpoint="https://hypersync.actual-test.example", quicknode_host="quicknode.actual-test.example",
        nansen=False).history))
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES",
                        {"actual-test/1": operating_release.release_sha256(actual)})
    with pytest.raises(ReleaseRefused) as refused:  # an approved actual release never runs over a recording
        open_released_runtime(settings, actual, credentials=creds, http_transport=stand_in.RecordingStandIn().transport)
    assert refused.value.code == "actual_release_needs_network_transport"
    composed = open_released_runtime(settings, actual, credentials=creds, http_transport=StdlibHttpTransport)
    assert (composed.evidence_class, composed.transport_kind) == ("PROVIDER_ACTUAL", "PROVIDER_HTTP")
    production = type("Production", (), {"env": "production"})()
    with pytest.raises(ReleaseRefused) as refused:
        open_released_runtime(production, stand_in.stand_in_release(), credentials=creds,
                              http_transport=stand_in.RecordingStandIn().transport,
                              nansen_transport=stand_in.StandInNansen().transport)
    assert refused.value.code == "stand_in_refused_in_production"
    assert creds.reads == []


def test_an_approved_actual_release_lists_actual_labels_and_no_stand_in_can_claim_them(settings, monkeypatch,
                                                                                         owner_a):
    actual = operating_release.OperatingRelease("actual-test/1", "ACTUAL", history=authored_actual_history(stand_in.stand_in_release(
        envio_endpoint="https://hypersync.actual-test.example", quicknode_host="quicknode.actual-test.example",
        nansen=False).history))
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES",
                        {"actual-test/1": operating_release.release_sha256(actual)})
    creds = stand_in.credentials()
    runtime = open_released_runtime(settings, actual, credentials=creds, http_transport=StdlibHttpTransport)
    with app(settings, runtime) as client:  # no job is started: no actual request runs in this milestone
        entry = next(item for item in client.get("/v1/research/history-sources", headers=owner_a).json()["sources"]
                     if item["source_id"] == SOURCE)
    assert (entry["evidence_class"], entry["content_label"], entry["release"]["kind"]) == (
        "PROVIDER_ACTUAL", "PROVIDER_HISTORY", "ACTUAL")
    assert creds.reads == []
    stand_in_entry = stand_in.recording_runtime(settings)[0]
    assert stand_in_entry.evidence_class == "RELEASE_STAND_IN_RESPONSE"


def test_create_app_refuses_two_nansen_paths(env):
    authored = load_settings({**env, "EDGE_OS_NANSEN_RESEARCH_MODE": "authored_fixture"})
    runtime = stand_in.recording_runtime(authored)[0]
    with pytest.raises(ConfigError, match="research_runtime"):
        create_app(authored, research_runtime=runtime)


# --------------------------------------------------------------------------------------- Nansen

def nansen_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "operation_id": str(uuid.uuid4()), "request_key": f"nansen-{uuid.uuid4()}", "token_address": stand_in.TOKEN,
        "token_symbol": "MOE", "window": {"start_utc": "2026-10-06T09:44:14Z", "end_utc": "2026-10-07T09:44:14Z"},
        "operations": ["holders", "flows"],
        "limits": {"max_requests": 4, "max_pages": 2, "max_bytes": 200000, "max_credits": "12", "per_page": 100},
        "deadline_seconds": 600, "compute_seconds": 30}
    body.update(overrides)
    return body


def nansen_intake(client, headers) -> str:
    response = submit(client, headers, QUESTION, job="INVESTIGATE_EFFECT", input_class="BOUNDED_NO_THESIS")
    assert response.status_code == 201, response.text
    return response.json()["intake"]["record_id"]


def test_a_release_nansen_report_uses_the_fixed_request_and_saves_stand_in_labels(settings, composed, owner_a,
                                                                                  owner_b):
    client, runtime, nansen, creds = (composed[k] for k in ("client", "runtime", "nansen", "creds"))
    intake_id = nansen_intake(client, owner_a)
    listed = client.get(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a).json()
    assert listed["available"] is True and listed["operating_release"]["sha256"] == runtime.release_sha256
    assert listed["operating_release"]["request"]["limits"]["max_credits"] == "12"
    wider = client.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a,
                        json=nansen_body(limits={"max_requests": 6, "max_pages": 2, "max_bytes": 200000,
                                                 "max_credits": "20", "per_page": 100}))
    assert (wider.status_code, wider.json()["code"]) == (422, "release_request_mismatch")
    assert [item["path"] for item in wider.json()["findings"]] == ["/limits"]
    started = client.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a, json=nansen_body())
    assert started.status_code == 201, started.text
    job_id = started.json()["job_id"]
    assert nansen.requests == [] and creds.reads == []
    worker(client, runtime).run_job(uuid.UUID(job_id))
    job = view(client, owner_a, job_id)
    assert job["state"] == "REPORTED", job["terminal_reason"]
    assert nansen.requests == ["holders", "flows"] and creds.reads == [stand_in.NANSEN_SLOT]
    report_id = job["nansen_report"]["report_id"]
    report = client.get(f"/v1/research/nansen-reports/{report_id}", headers=owner_a).json()
    content = report["content"]
    assert (content["evidence_class"], content["transport_label"]) == (
        "RELEASE_STAND_IN_RESPONSE", "RELEASE_STAND_IN_NANSEN_TRANSPORT")
    assert content["operating_release"]["sha256"] == runtime.release_sha256 and "Stand-in" in content["notice"]
    assert content["report"]["question"] == QUESTION and all(report["hashes_verified"].values())
    assert job["budget"]["consumed"]["nansen_credits"] == 6 and job["budget"]["unknown_liability"]["nansen_credits"] == 0
    assert client.get(f"/v1/research/nansen-reports/{report_id}", headers=owner_b).status_code == 404
    assert not any(value in json.dumps(report) + json.dumps(job) for value in stand_in.SENTINELS)


@pytest.mark.parametrize("problem,reason", [("missing", "operating_release_credential_unavailable"),
                                            ("changed", "operating_release_changed"),
                                            ("absent", "operating_release_unavailable")])
def test_a_release_nansen_job_ends_before_any_request_without_its_release_or_credential(settings, owner_a, problem,
                                                                                        reason):
    runtime, _, nansen, _ = stand_in.recording_runtime(settings)
    with app(settings, runtime) as client:
        started = client.post(f"/v1/research/requests/{nansen_intake(client, owner_a)}/nansen-reports",
                              headers=owner_a, json=nansen_body())
        assert started.status_code == 201, started.text
        job_id = started.json()["job_id"]
        if problem == "missing":
            other = stand_in.recording_runtime(settings, creds=stand_in.credentials(missing=(stand_in.NANSEN_SLOT,)),
                                               nansen=nansen)[0]
        elif problem == "changed":
            other = stand_in.recording_runtime(settings, release=stand_in.stand_in_release(release_id="stand-in-native/9"),
                                               nansen=nansen)[0]
        else:
            other = None
        worker(client, other).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
    assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", reason)
    assert job["budget"]["released"] == {"provider_requests": 4, "compute_seconds": 30, "nansen_credits": 12}
    assert nansen.requests == []


def test_the_registered_actual_default_admits_a_job_and_refuses_before_any_provider_io(settings, owner_a, owner_b,
                                                                                        monkeypatch):
    """The ordinary create_app composes the registered ACTUAL default. With the one selected slot missing, the worker
    refuses at preparation and reaches no provider. This is local admission and refusal proof, not an actual report."""
    reached: list[str] = []

    def sentinel(*args: Any, **kwargs: Any) -> Any:
        reached.append("provider-http-boundary")
        raise AssertionError("a real provider HTTP request was attempted")

    monkeypatch.setattr(StdlibHttpTransport, "request", sentinel)  # the real HTTP boundary must stay unreached
    monkeypatch.delenv("NANSEN_API_KEY", raising=False)  # the one selected slot is explicitly missing
    with app(settings) as client:  # no injected runtime: the default bootstrap composes the release
        runtime = client.app.state.research_runtime
        assert runtime is not None and runtime.release.history is not None and runtime.release.nansen is not None
        assert (runtime.release.release_id, runtime.release.kind, runtime.release_sha256) == (
            REGISTERED_RELEASE_ID, "ACTUAL", REGISTERED_RELEASE_SHA256)
        # The fixed request is frozen before the worker and equals the registered release exactly.
        assert released_nansen_request(runtime.release.nansen) == REGISTERED_NANSEN_REQUEST
        intake_id = nansen_intake(client, owner_a)
        listed = client.get(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a).json()
        assert listed["available"] is True
        assert listed["operating_release"]["sha256"] == REGISTERED_RELEASE_SHA256
        assert listed["operating_release"]["request"] == REGISTERED_NANSEN_REQUEST
        body = {"operation_id": str(uuid.uuid4()), "request_key": f"actual-{uuid.uuid4()}",
                **REGISTERED_NANSEN_REQUEST}
        started = client.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a, json=body)
        assert started.status_code == 201, started.text
        job_id = started.json()["job_id"]
        assert reached == []  # a start sends nothing
        worker(client, runtime).run_job(uuid.UUID(job_id))  # the worker uses the default composed runtime
        job = view(client, owner_a, job_id)
        assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", "operating_release_credential_unavailable")
        assert job["budget"]["reserved"] == {"provider_requests": 2, "compute_seconds": 300, "nansen_credits": 6}
        assert job["budget"]["released"] == {"provider_requests": 2, "compute_seconds": 300, "nansen_credits": 6}
        assert job["budget"]["consumed"] == {"provider_requests": 0, "compute_seconds": 0, "nansen_credits": 0}
        assert job["budget"]["unknown_liability"] == {"provider_requests": 0, "compute_seconds": 0, "nansen_credits": 0}
        kinds = [event["kind"] for event in job["events"]]
        assert "SOURCE_REFUSED" in kinds and "ATTEMPT_STARTED" not in kinds and "JOB_QUEUED" in kinds
        assert reached == []  # no provider call, and no attempt or debit
    # A restart reopens the same saved job for the owner only: nothing is reserved, called or charged again.
    with app(settings) as restarted:
        assert view(restarted, owner_a, job_id) == job
        assert restarted.get(f"/v1/research/investigation-jobs/{job_id}", headers=owner_b).status_code == 404
    assert reached == []


# --------------------------------------------------------------------------------------- R58-RESEARCH-MOUNT-L2
# The accepted Nansen HTTP adapter mounted in the original job lifecycle, over an owned 127.0.0.1 stand-in only.

@pytest.fixture
def nansen_loopback(tmp_path):
    provider = stand_in.LoopbackStandInNansen(tmp_path / "nansen.log").start()
    yield provider
    provider.stop()


def start_nansen(client, headers, **overrides) -> str:
    started = client.post(f"/v1/research/requests/{nansen_intake(client, headers)}/nansen-reports", headers=headers,
                          json=nansen_body(**overrides))
    assert started.status_code == 201, started.text
    return started.json()["job_id"]


def request_cancel(client, job_id: str) -> None:
    """The owner's cancel, saved while the worker is inside a provider call (the API route does the same update)."""
    from edge_os_api.research.investigation_jobs import InvestigationJobRow

    with client.app.state.session_factory() as session:
        session.get(InvestigationJobRow, uuid.UUID(job_id)).cancel_requested_at = dt.datetime.now(dt.timezone.utc)
        session.commit()


def test_a_loopback_release_nansen_report_crosses_the_accepted_adapter_and_reopens_without_a_call(
        settings, owner_a, owner_b, nansen_loopback):
    runtime, creds = stand_in.nansen_loopback_runtime(settings, nansen_loopback)
    with app(settings, runtime) as client:
        job_id = start_nansen(client, owner_a)
        assert nansen_loopback.entries() == [] and creds.reads == []
        worker(client, runtime).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
        report_id = job["nansen_report"]["report_id"]
        report = client.get(f"/v1/research/nansen-reports/{report_id}", headers=owner_a).json()
    assert job["state"] == "REPORTED", job["terminal_reason"]
    assert [(entry["operation"], entry["authorized"]) for entry in nansen_loopback.entries()] == [
        ("holders", True), ("flows", True)]
    assert nansen_loopback.targets == [("https", "api.nansen.ai", None)] * 2 and creds.reads == [stand_in.NANSEN_SLOT]
    content = report["content"]
    assert (content["evidence_class"], content["transport_label"], content["transport_kind"]) == (
        "RELEASE_STAND_IN_RESPONSE", "RELEASE_STAND_IN_NANSEN_TRANSPORT", "LOOPBACK_HTTP")
    assert len(content["transport_response_sha256"]) == 2 and all(report["hashes_verified"].values())
    assert job["budget"]["consumed"]["nansen_credits"] == 6 and job["budget"]["unknown_liability"]["nansen_credits"] == 0
    restarted, _ = stand_in.nansen_loopback_runtime(settings, nansen_loopback)
    with app(settings, restarted) as client:  # a new API process over the same rows: reopening calls nothing
        reopened = client.get(f"/v1/research/nansen-reports/{report_id}", headers=owner_a).json()
        foreign = client.get(f"/v1/research/nansen-reports/{report_id}", headers=owner_b).status_code
        worker(client, restarted).run_pending()
    assert reopened["content_sha256"] == report["content_sha256"] and foreign == 404
    assert len(nansen_loopback.entries()) == 2
    assert not any(value in json.dumps(report) + json.dumps(job) for value in stand_in.SENTINELS)


def test_a_release_nansen_call_past_the_saved_deadline_ends_deadline_exceeded_with_unknown_liability(
        settings, owner_a, nansen_loopback):
    runtime, _ = stand_in.nansen_loopback_runtime(settings, nansen_loopback)
    nansen_loopback.fault = lambda index, operation: {"delay": 3.0} if index == 1 else None
    with app(settings, runtime) as client:
        job_id = start_nansen(client, owner_a)
        # The worker starts 598 s after the job: about two seconds of the saved 600 s deadline are left.
        late = lambda: dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=598)  # noqa: E731
        worker(client, runtime, clock=late).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
    assert (job["state"], job["terminal_reason"]) == ("DEADLINE_EXCEEDED", "deadline_during_collection")
    assert len(nansen_loopback.entries()) == 1  # flows was never sent
    assert job["budget"]["unknown_liability"]["provider_requests"] == 4
    assert job["budget"]["unknown_liability"]["nansen_credits"] == 12 and job["budget"]["consumed"]["nansen_credits"] == 0


def test_a_cancel_during_a_release_nansen_call_ends_cancelled_with_unknown_liability(settings, owner_a,
                                                                                    nansen_loopback):
    runtime, _ = stand_in.nansen_loopback_runtime(settings, nansen_loopback)
    with app(settings, runtime) as client:
        job_id = start_nansen(client, owner_a)

        def cancel_mid_call(index: int, operation: str) -> dict[str, Any] | None:
            if index == 1:
                request_cancel(client, job_id)
                return {"delay": 0.3}
            return None

        nansen_loopback.fault = cancel_mid_call
        worker(client, runtime).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
    assert (job["state"], job["terminal_reason"]) == ("CANCELLED", "cancelled_during_collection")
    assert len(nansen_loopback.entries()) == 1
    assert job["budget"]["unknown_liability"]["provider_requests"] == 4
    assert job["budget"]["unknown_liability"]["nansen_credits"] == 12


def test_a_release_nansen_job_with_a_malformed_key_ends_before_any_request(settings, owner_a, nansen_loopback):
    creds = stand_in.StandInCredentials({stand_in.NANSEN_SLOT: "stand-in key with spaces"})
    runtime, _ = stand_in.nansen_loopback_runtime(settings, nansen_loopback, creds=creds)
    with app(settings, runtime) as client:
        job_id = start_nansen(client, owner_a)
        worker(client, runtime).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
    assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", "operating_release_credential_unavailable")
    assert [event["kind"] for event in job["events"]].count("ATTEMPT_STARTED") == 0
    assert job["budget"]["released"] == {"provider_requests": 4, "compute_seconds": 30, "nansen_credits": 12}
    assert nansen_loopback.entries() == []


def test_a_worker_killed_during_a_release_nansen_call_never_runs_it_again(settings, owner_a):
    class KilledNansen:
        def request(self, operation: str, path: str, body: Any) -> Any:
            raise Killed()

    stand_in_nansen = stand_in.StandInNansen()
    release = stand_in.stand_in_release(history=False)
    killing = open_released_runtime(settings, release, credentials=stand_in.credentials(),
                                    nansen_transport=lambda part, key, **bounds: KilledNansen())
    restarted = open_released_runtime(settings, release, credentials=stand_in.credentials(),
                                      nansen_transport=stand_in_nansen.transport)
    with app(settings, killing) as client:
        job_id = start_nansen(client, owner_a)
        with pytest.raises(Killed):
            worker(client, killing).run_job(uuid.UUID(job_id))
        worker(client, restarted).run_job(uuid.UUID(job_id))
        job = view(client, owner_a, job_id)
    assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", "nansen_outcome_unknown")
    assert [event["kind"] for event in job["events"]].count("ATTEMPT_STARTED") == 1
    assert job["budget"]["unknown_liability"]["nansen_credits"] == 12 and stand_in_nansen.requests == []
