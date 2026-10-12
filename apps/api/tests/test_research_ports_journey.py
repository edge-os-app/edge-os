"""#58 RESEARCH-PORTS-LOCAL: the accepted P07 HTTP clients and Nansen reports through mounted owner-scoped jobs.

Seam: authenticated declaration or request → saved job → worker → application-composed client over an AUTHORED
transport → saved dataset or report → public read, restart and other owner. Expected values are written by hand from
the authored inputs: the SOURCE-LOCAL qualified recording (24 swaps on two pages; one chain read and one receipt per
swap) and the authored Nansen fixture (one holders page charged 5 credits, one flows page charged 1). Nothing reaches
a network or reads a credential.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from edge_os_api.core.research import provider_composition
from edge_os_api.core.settings import ConfigError, load_settings
from edge_os_api.main import create_app
from edge_os_api.nansen_research import NansenResponse
from edge_os_api.nansen_research.errors import NansenTransportError
from edge_os_api.research.forward_observation import forward_observation_from
from edge_os_api.research.investigation_jobs import InvestigationWorker
from edge_os_api.research_history.http_clients import HttpResponse
from flows import compiled_thesis, publish, submit
from research_flows import adoption_body, declare, history_replay_body, jobs_path, source_entry

HTTP_SOURCE = "native-http-qualified/1"
BOUNDS = {"provider_requests": 27, "compute_seconds": 30, "max_pages": 2, "max_rows": 200,
          "max_bytes": 1_048_576, "deadline_seconds": 600}
TOKEN = "0xd8e004acba279417c04c0633cb5a21ceca207777"
QUESTION = "Which holder records does MOE return, and what do basic flow records show?"
PROVIDER_TEXT = "provider-private-detail-7731"


def app(env: dict[str, str], **extra: str) -> TestClient:
    values = {**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded", "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "400",
              "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS": "3600", **extra}
    return TestClient(create_app(load_settings(values)))


@pytest.fixture(scope="module")
def ports(env, migrated):
    with app(env, EDGE_OS_RESEARCH_SOURCE_CLIENTS="authored_http", EDGE_OS_NANSEN_RESEARCH_MODE="authored_fixture") as c:
        yield c


@pytest.fixture(scope="module")
def plain(env, migrated):
    with app(env) as c:
        yield c


def worker(client, **kwargs) -> InvestigationWorker:
    return InvestigationWorker(client.app.state.session_factory, client.app.state.settings, **kwargs)


def view(client, headers, job_id: str) -> dict[str, Any]:
    response = client.get(f"/v1/research/investigation-jobs/{job_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def dataset(client, headers, job: dict[str, Any]) -> dict[str, Any]:
    response = client.get(f"/v1/research/history-datasets/{job['dataset']['dataset_id']}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


def start_http(client, headers, bounds: dict | None = None) -> str:
    intake_id, declaration_id, _ = declare(client, headers, source_id=HTTP_SOURCE, bounds=bounds or BOUNDS)
    started = client.post(jobs_path(intake_id, declaration_id), headers=headers,
                          json={"operation_id": str(uuid.uuid4()), "request_key": f"http-{uuid.uuid4()}"})
    assert started.status_code == 201, started.text
    return started.json()["job_id"]


# --------------------------------------------------------------------------------------- P07 HTTP clients

class FaultTransport:
    """Wraps the authored HTTP transport: answers the Nth request with an authored fault reply or a lost reply."""

    def __init__(self, inner, *, at: int, status: int | None = None, body: bytes = b"", lose: bool = False):
        self._inner, self._at, self._status, self._body, self._lose = inner, at, status, body, lose
        self.requests = 0
        self.response_sha256 = inner.response_sha256

    def request(self, **kwargs) -> HttpResponse:
        self.requests += 1
        if self.requests == self._at:
            if self._lose:
                self._inner.request(**kwargs)  # the provider served it
                raise OSError("authored: the reply was lost")
            return HttpResponse(status=self._status, headers={"content-type": "application/json"}, body=self._body)
        return self._inner.request(**kwargs)


def faulting_clients(**fault):
    seen: dict[str, Any] = {}

    def build(source, bounds, cancelled):
        envio, quicknode, transport = provider_composition.http_source_clients(source, bounds, cancelled)
        wrapped = FaultTransport(transport, **fault)
        envio._transport = wrapped  # the same accepted client class, over the faulting authored transport
        quicknode._transport = wrapped
        seen["transport"] = wrapped
        return envio, quicknode, wrapped
    return build, seen


def test_saved_nansen_fixture_equals_its_writer():
    import nansen_authored_fixture

    assert json.loads(nansen_authored_fixture.OUTPUT.read_text(encoding="utf-8")) == nansen_authored_fixture.build()
    assert provider_composition.NANSEN_FIXTURE_PATH.resolve() == nansen_authored_fixture.OUTPUT.resolve()


def test_http_source_job_runs_through_the_accepted_p07_http_clients(ports, owner_a):
    catalog = ports.get("/v1/research/history-sources", headers=owner_a).json()
    entry = next(item for item in catalog["sources"] if item["source_id"] == HTTP_SOURCE)
    assert (entry["evidence_class"], entry["content_label"], entry["available"]) == (
        "AUTHORED_HTTP_RESPONSE", "SYNTHETIC_FIXTURE", True)
    assert entry["transport"]["clients"] == "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT"
    job_id = start_http(ports, owner_a)
    worker(ports).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert job["state"] == "REPORTED", job["terminal_reason"]
    content = dataset(ports, owner_a, job)
    transport = content["transport"]
    assert (content["evidence_class"], content["content_label"]) == ("AUTHORED_HTTP_RESPONSE", "SYNTHETIC_FIXTURE")
    assert transport["client_classes"] == {"ENVIO_HYPERSYNC": "HttpEnvioQueryClient",
                                           "QUICKNODE_JSON_RPC": "HttpQuickNodeRpcClient"}
    assert transport["client_calls"] == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 25}
    assert transport["http_accounting"]["QUICKNODE_JSON_RPC"] == {
        "attempted_requests": 25, "completed_requests": 25, "unknown_liability": 0}
    assert len(transport["response_sha256"]) == 27 and transport["transport_label"] == "AUTHORED_HTTP_TRANSPORT"
    assert transport["corroboration"]["class"] == "COMPLETE" and transport["chain_read"]["chain_id"] == 143
    assert (content["provider_requests_state"], job["budget"]["consumed"]["provider_requests"]) == (
        "MEASURED_CLIENT_CALLS", 27)
    assert "authored-local-fixture" not in json.dumps(content)  # the authored bearer value never reaches the record
    summary = job["dataset"]["transport"]
    assert (summary["clients"], summary["transport_label"]) == ("P07_HTTP_CLIENTS_AUTHORED_TRANSPORT",
                                                               "AUTHORED_HTTP_TRANSPORT")
    assert summary["client_classes"] == transport["client_classes"]


def test_the_http_dataset_feeds_adoption_and_a_replay_with_simulated_fills(ports, owner_a):
    """Declared source -> saved dataset -> new revision on its market -> replay on it, labelled authored and simulated."""
    job_id = start_http(ports, owner_a)
    worker(ports).run_job(uuid.UUID(job_id))
    dataset_id = view(ports, owner_a, job_id)["dataset"]["dataset_id"]
    listed = next(item for item in ports.get("/v1/research/history-datasets", headers=owner_a).json()["datasets"]
                  if item["dataset_id"] == dataset_id)
    bundle = compiled_thesis(ports, owner_a)
    first, _ = publish(ports, owner_a, bundle)
    parent = first.json()["revision_id"]
    adopted = ports.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions", headers=owner_a,
                         json=adoption_body(bundle, dataset_id, parent=parent,
                                            evaluation_id=listed["declared_rules"][0]["evaluation_id"],
                                            quote_unit="QUOTE:0x" + "d2" * 20))
    assert adopted.status_code == 201, adopted.text
    second, _ = publish(ports, owner_a, adopted.json()["bundle"], parent=parent)
    assert second.status_code == 201, second.text
    start = dt.datetime.fromisoformat(listed["window_start"].replace("Z", "+00:00")) + dt.timedelta(minutes=15)
    body = history_replay_body(bundle["head"]["strategy_id"], second.json()["revision_id"], dataset_id,
                               start=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                               end=listed["readable_until"])  # validation and holdout data stay unread
    response = ports.post("/v1/spot-replays", headers=owner_a, json=body)
    assert response.status_code in (200, 201), response.text
    content = response.json()["content"]
    assert content["result"]["status"] == "COMPLETE", content["result"].get("reason")
    lineage = content["inputs"]["history_input"]
    assert (lineage["dataset_id"], lineage["source_evidence_class"], lineage["fill_label"]) == (
        dataset_id, "AUTHORED_HTTP_RESPONSE", "simulated fills")
    assert lineage["content_label"] == "SYNTHETIC_FIXTURE" and "Simulated fills" in content["notice"]


@pytest.mark.parametrize("status,code", [(401, "PROVIDER_ERROR"), (402, "PROVIDER_ERROR"), (429, "PROVIDER_ERROR")])
def test_a_refused_http_page_stops_with_a_stable_code_and_no_provider_text(ports, owner_a, status, code):
    build, seen = faulting_clients(at=2, status=status, body=json.dumps({"error": PROVIDER_TEXT}).encode())
    job_id = start_http(ports, owner_a)
    worker(ports, http_clients=build).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    content = dataset(ports, owner_a, job)
    assert content["stop_reason"] == code and content["status"] == "PARTIAL"
    assert content["transport"]["client_calls"]["ENVIO_HYPERSYNC"] == 2 and seen["transport"].requests >= 2
    assert PROVIDER_TEXT not in json.dumps(job) + json.dumps(content)


def test_a_lost_http_reply_keeps_the_whole_reservation_unknown(ports, owner_a):
    build, _ = faulting_clients(at=1, lose=True)
    job_id = start_http(ports, owner_a)
    worker(ports, http_clients=build).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    content = dataset(ports, owner_a, job)
    assert content["transport"]["http_accounting"]["ENVIO_HYPERSYNC"]["unknown_liability"] == 1
    assert content["provider_requests_state"] == "UNKNOWN"
    assert (job["budget"]["unknown_liability"]["provider_requests"], job["budget"]["consumed"]["provider_requests"]) \
        == (27, 0)


def test_an_oversized_http_page_is_refused_within_the_declared_byte_bound(ports, owner_a):
    job_id = start_http(ports, owner_a, bounds={**BOUNDS, "max_bytes": 1024})
    worker(ports).run_job(uuid.UUID(job_id))
    content = dataset(ports, owner_a, view(ports, owner_a, job_id))
    assert content["status"] == "PARTIAL" and content["transport"]["client_calls"]["ENVIO_HYPERSYNC"] == 1


def test_a_malformed_http_page_stops_without_a_retry(ports, owner_a):
    build, seen = faulting_clients(at=1, status=200, body=b"{authored malformed page")
    job_id = start_http(ports, owner_a)
    worker(ports, http_clients=build).run_job(uuid.UUID(job_id))
    content = dataset(ports, owner_a, view(ports, owner_a, job_id))
    assert content["status"] == "PARTIAL" and content["stop_reason"] == "PROVIDER_ERROR"
    assert seen["transport"].requests == 1 and content["transport"]["client_calls"]["ENVIO_HYPERSYNC"] == 1


def test_an_http_job_past_its_deadline_makes_no_client_call(ports, owner_a):
    build, seen = faulting_clients(at=99)
    job_id = start_http(ports, owner_a)
    late = worker(ports, http_clients=build, clock=lambda: dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1))
    late.run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert job["state"] == "DEADLINE_EXCEEDED" and "transport" not in seen
    assert job["budget"]["consumed"]["provider_requests"] == 0


def test_a_cancelled_http_job_makes_no_client_call(ports, owner_a):
    build, seen = faulting_clients(at=99)
    job_id = start_http(ports, owner_a)
    ports.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_a)
    worker(ports, http_clients=build).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert job["state"] == "CANCELLED" and "transport" not in seen


def test_without_the_http_composition_the_source_is_listed_unavailable_and_refused(plain, owner_a):
    entry = source_entry(plain, owner_a, HTTP_SOURCE)
    assert entry["available"] is False
    intake_id, declaration_id, _ = declare(plain, owner_a, source_id=HTTP_SOURCE, bounds=BOUNDS)
    started = plain.post(jobs_path(intake_id, declaration_id), headers=owner_a,
                         json={"operation_id": str(uuid.uuid4()), "request_key": "http-off"})
    assert (started.status_code, started.json()["code"]) == (409, "history_source_unavailable")
    budget = plain.get("/v1/research/budget", headers=owner_a)
    assert budget.status_code != 200 or budget.json()["reserved"]["provider_requests"] == 0


@pytest.mark.parametrize("name,value", [("EDGE_OS_RESEARCH_SOURCE_CLIENTS", "authored_http"),
                                        ("EDGE_OS_NANSEN_RESEARCH_MODE", "authored_fixture")])
def test_production_refuses_the_authored_transports(env, name, value):
    production = {**env, "EDGE_OS_ENV": "production", "EDGE_OS_PRIVY_APP_ID": "real-app",
                  "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.example.com",
                  "EDGE_OS_DATABASE_URL": "postgresql+psycopg://u:p@db.internal/edge?sslmode=require",
                  "EDGE_OS_BUILD_SHA": "0" * 40, name: value}
    with pytest.raises(ConfigError, match=name[len("EDGE_OS_"):].lower()):
        load_settings(production)


# --------------------------------------------------------------------------------------------- Nansen

def nansen_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "operation_id": str(uuid.uuid4()), "request_key": f"nansen-{uuid.uuid4()}", "token_address": TOKEN,
        "token_symbol": "MOE", "window": {"start_utc": "2026-10-06T09:44:14Z", "end_utc": "2026-10-07T09:44:14Z"},
        "operations": ["holders", "flows"],
        "limits": {"max_requests": 4, "max_pages": 2, "max_bytes": 200000, "max_credits": "12", "per_page": 100},
        "deadline_seconds": 600, "compute_seconds": 30}
    body.update(overrides)
    return body


def request_id(client, headers, text: str = QUESTION) -> str:
    response = submit(client, headers, text, job="INVESTIGATE_EFFECT", input_class="BOUNDED_NO_THESIS")
    assert response.status_code == 201, response.text
    return response.json()["intake"]["record_id"]


def start_nansen(client, headers, intake_id: str, **overrides: Any):
    return client.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=headers,
                       json=nansen_body(**overrides))


class CountingNansen:
    """The authored Nansen transport, or authored replies per call, counting every call."""

    def __init__(self, replies: list | None = None):
        self.calls = 0
        self._inner = provider_composition.AuthoredNansenTransport(TOKEN)
        self._replies = replies
        self.response_sha256 = self._inner.response_sha256

    def request(self, operation, path, body):
        self.calls += 1
        if self._replies is None or self.calls > len(self._replies) or self._replies[self.calls - 1] is None:
            return self._inner.request(operation, path, body)
        reply = self._replies[self.calls - 1]
        if isinstance(reply, BaseException):
            raise reply
        if callable(reply):
            return reply(operation, path, body)
        return reply


def nansen_worker(client, transport) -> InvestigationWorker:
    return worker(client, nansen_transport=lambda token: transport)


def test_a_nansen_report_job_saves_and_reopens_the_same_report(env, ports, owner_a, owner_b):
    intake_id = request_id(ports, owner_a)
    started = start_nansen(ports, owner_a, intake_id)
    assert started.status_code == 201, started.text
    job_id = started.json()["job_id"]
    assert started.json()["kind"] == "NANSEN_REPORT" and started.json()["state"] == "RESERVED"
    transport = CountingNansen()
    nansen_worker(ports, transport).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert job["state"] == "REPORTED", job["terminal_reason"]
    summary = job["nansen_report"]
    assert (summary["question"], summary["evidence_class"], transport.calls) == (QUESTION, "AUTHORED_FIXTURE", 2)
    assert summary["settlement"]["nansen_credits"] == {"state": "KNOWN", "measured": 6, "deducted": "6",
                                                       "reserved_by_package": "6"}
    assert (job["budget"]["consumed"]["nansen_credits"], job["budget"]["released"]["nansen_credits"]) == (6, 6)
    assert (job["budget"]["consumed"]["provider_requests"], job["budget"]["released"]["provider_requests"]) == (2, 2)
    report = ports.get(f"/v1/research/nansen-reports/{summary['report_id']}", headers=owner_a).json()
    assert all(report["hashes_verified"].values()), report["hashes_verified"]
    findings = {item["code"]: item["verdict"] for item in report["content"]["report"]["findings"]}
    assert findings["HOLDER_INVENTORY"] == "SUPPORTED" and findings["HOLDER_TOKEN_AMOUNT_UNITS"] == "UNRESOLVED"
    assert report["content"]["report"]["question"] == QUESTION
    assert "Not provider data" in report["content"]["notice"]
    # A restarted application reopens the same saved snapshot and never calls a transport again.
    with app(env, EDGE_OS_NANSEN_RESEARCH_MODE="authored_fixture") as restarted:
        again = restarted.get(f"/v1/research/nansen-reports/{summary['report_id']}", headers=owner_a).json()
    assert again["content"] == report["content"] and transport.calls == 2
    for path in (f"/v1/research/nansen-reports/{summary['report_id']}", f"/v1/research/investigation-jobs/{job_id}",
                 f"/v1/research/requests/{intake_id}/nansen-reports"):
        assert ports.get(path, headers=owner_b).status_code == 404, path


def failure(status: int, *, code: str | None = None, headers: dict | None = None) -> NansenResponse:
    payload = {"code": code, "message": PROVIDER_TEXT} if code else {"message": PROVIDER_TEXT}
    return NansenResponse(status=status, headers=headers or {}, body=json.dumps(payload).encode())


@pytest.mark.parametrize("reply,stop", [
    (failure(401), "UNAUTHENTICATED"), (failure(402), "PAYMENT_REQUIRED"),
    (failure(403, code="insufficient_credits"), "insufficient_credits"), (failure(429), "RATE_LIMITED")])
def test_a_refused_nansen_call_keeps_a_partial_report_with_a_stable_code(ports, owner_a, reply, stop):
    intake_id = request_id(ports, owner_a)
    job_id = start_nansen(ports, owner_a, intake_id).json()["job_id"]
    transport = CountingNansen([reply])
    nansen_worker(ports, transport).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert transport.calls == 1  # no retry and no next operation after a terminal failure
    assert job["nansen_report"]["outcomes"][0] == {"operation": "holders", "status": "FAILED", "stop_reason": stop}
    assert job["nansen_report"]["answer_state"] in ("PARTIAL", "UNAVAILABLE")
    assert PROVIDER_TEXT not in json.dumps(job) + json.dumps(ports.get(
        f"/v1/research/nansen-reports/{job['nansen_report']['report_id']}", headers=owner_a).json())


def test_a_missing_credit_charge_keeps_the_whole_credit_reservation_unknown(ports, owner_a):
    intake_id = request_id(ports, owner_a)
    job_id = start_nansen(ports, owner_a, intake_id, operations=["holders"]).json()["job_id"]
    no_charge = lambda operation, path, body: NansenResponse(  # noqa: E731
        status=200, headers={}, body=provider_composition.AuthoredNansenTransport(TOKEN).request(
            operation, path, body).body)
    nansen_worker(ports, CountingNansen([no_charge])).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert job["nansen_report"]["settlement"]["nansen_credits"]["state"] == "UNKNOWN"
    assert (job["budget"]["unknown_liability"]["nansen_credits"], job["budget"]["consumed"]["nansen_credits"]) == (
        12, 0)


def test_a_lost_nansen_reply_keeps_requests_and_credits_unknown(ports, owner_a):
    intake_id = request_id(ports, owner_a)
    job_id = start_nansen(ports, owner_a, intake_id).json()["job_id"]
    nansen_worker(ports, CountingNansen([NansenTransportError("LOST", "authored lost reply")])).run_job(
        uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert job["nansen_report"]["settlement"]["provider_requests"] == {"state": "UNKNOWN", "measured": 0, "lost": 1}
    assert job["budget"]["unknown_liability"]["provider_requests"] == 4
    assert job["budget"]["unknown_liability"]["nansen_credits"] == 12


def test_a_cancel_between_operations_stops_before_the_next_request(ports, owner_a):
    intake_id = request_id(ports, owner_a)
    job_id = start_nansen(ports, owner_a, intake_id).json()["job_id"]

    def holders_then_cancel(operation, path, body):
        reply = provider_composition.AuthoredNansenTransport(TOKEN).request(operation, path, body)
        ports.post(f"/v1/research/investigation-jobs/{job_id}/cancel", headers=owner_a)
        return reply

    transport = CountingNansen([holders_then_cancel])
    nansen_worker(ports, transport).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert (job["state"], transport.calls) == ("CANCELLED", 1)
    assert job["nansen_report"]["outcomes"][-1]["stop_reason"] == "CANCELLED"
    assert job["nansen_report"]["settlement"]["provider_requests"] == {"state": "KNOWN", "measured": 1, "lost": 0}


def test_a_malformed_nansen_reply_keeps_a_partial_report_and_stops(ports, owner_a):
    intake_id = request_id(ports, owner_a)
    job_id = start_nansen(ports, owner_a, intake_id).json()["job_id"]
    malformed = NansenResponse(status=200, headers={"x-nansen-credits-cost": "5"}, body=b"{authored malformed")
    transport = CountingNansen([malformed])
    nansen_worker(ports, transport).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert transport.calls == 1 and job["nansen_report"]["outcomes"][0]["status"] == "FAILED"
    assert job["nansen_report"]["answer_state"] in ("PARTIAL", "UNAVAILABLE")


def test_a_nansen_deadline_between_operations_stops_before_the_next_request(ports, owner_a):
    intake_id = request_id(ports, owner_a)
    job_id = start_nansen(ports, owner_a, intake_id).json()["job_id"]
    late = {"after_first": False}

    def clock() -> dt.datetime:
        now = dt.datetime.now(dt.timezone.utc)
        return now + dt.timedelta(days=1) if late["after_first"] else now

    def holders_then_late(operation, path, body):
        late["after_first"] = True
        return provider_composition.AuthoredNansenTransport(TOKEN).request(operation, path, body)

    transport = CountingNansen([holders_then_late])
    worker(ports, nansen_transport=lambda token: transport, clock=clock).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert (job["state"], transport.calls) == ("DEADLINE_EXCEEDED", 1)
    assert job["nansen_report"]["outcomes"][-1]["stop_reason"] == "DEADLINE"
    assert job["nansen_report"]["settlement"]["provider_requests"] == {"state": "KNOWN", "measured": 1, "lost": 0}


class Crash(BaseException):
    """An authored worker death inside the run (not an application exception)."""


def test_a_worker_killed_during_the_run_is_never_run_again(ports, owner_a):
    intake_id = request_id(ports, owner_a)
    job_id = start_nansen(ports, owner_a, intake_id).json()["job_id"]
    with pytest.raises(Crash):
        nansen_worker(ports, CountingNansen([Crash()])).run_job(uuid.UUID(job_id))
    again = CountingNansen()
    nansen_worker(ports, again).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    assert (job["state"], job["terminal_reason"], again.calls) == ("UNAVAILABLE", "nansen_outcome_unknown", 0)
    assert job["budget"]["unknown_liability"]["nansen_credits"] == 12 and job["nansen_report"] is None


@pytest.mark.parametrize("overrides,code", [
    ({"window": {"start_utc": "2026-10-07T09:44:14Z", "end_utc": "2026-10-06T09:44:14Z"}}, "WINDOW_INVALID"),
    ({"operations": ["holders", "holders"]}, "OPERATIONS_DUPLICATE"),
    ({"token_address": "0x123"}, None), ({"owner_id": str(uuid.uuid4())}, None),
    ({"limits": {"max_requests": 0, "max_pages": 1, "max_bytes": 1, "max_credits": "1"}}, None)])
def test_an_invalid_nansen_request_is_refused_before_any_reservation(ports, owner_a, overrides, code):
    intake_id = request_id(ports, owner_a)
    response = start_nansen(ports, owner_a, intake_id, **overrides)
    assert response.status_code == 422, response.text
    if code is not None:
        assert response.json()["code"] == code
    assert ports.get(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a).json()["jobs"] == []


def test_a_nansen_job_over_the_credit_budget_is_refused_and_calls_nothing(env, owner_a):
    with app(env, EDGE_OS_NANSEN_RESEARCH_MODE="authored_fixture", EDGE_OS_RESEARCH_BUDGET_NANSEN_CREDITS="5") as c:
        intake_id = request_id(c, owner_a)
        refused = start_nansen(c, owner_a, intake_id)
        assert (refused.status_code, refused.json()["code"]) == (409, "research_budget_exhausted")
        jobs = c.get(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a).json()["jobs"]
    assert [job["state"] for job in jobs] == ["BUDGET_EXHAUSTED"]


def test_a_repeated_key_returns_the_original_job_and_a_changed_body_is_refused(ports, owner_a):
    intake_id = request_id(ports, owner_a)
    body = nansen_body()
    first = ports.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a, json=body)
    again = ports.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a, json=body)
    changed = ports.post(f"/v1/research/requests/{intake_id}/nansen-reports", headers=owner_a,
                         json={**body, "token_symbol": "OTHER"})
    assert (first.status_code, again.status_code) == (201, 200) and again.json()["job_id"] == first.json()["job_id"]
    assert (changed.status_code, changed.json()["code"]) == (409, "request_key_reused")


def test_another_owner_cannot_start_a_report_on_this_request(ports, owner_a, owner_b):
    intake_id = request_id(ports, owner_a)
    assert start_nansen(ports, owner_b, intake_id).status_code == 404


def test_an_unsupported_question_clause_stays_unresolved(ports, owner_a):
    question = "Which holder records does MOE return, and who is buying MOE?"
    intake_id = request_id(ports, owner_a, question)
    job_id = start_nansen(ports, owner_a, intake_id).json()["job_id"]
    nansen_worker(ports, CountingNansen()).run_job(uuid.UUID(job_id))
    job = view(ports, owner_a, job_id)
    report = ports.get(f"/v1/research/nansen-reports/{job['nansen_report']['report_id']}", headers=owner_a).json()
    findings = {item["code"]: item["verdict"] for item in report["content"]["report"]["findings"]}
    assert findings["BUYING"] == "UNRESOLVED" and report["content"]["report"]["answer_state"] == "PARTIAL"


def test_without_the_nansen_composition_nothing_starts(plain, owner_a):
    intake_id = request_id(plain, owner_a)
    response = start_nansen(plain, owner_a, intake_id)
    assert (response.status_code, response.json()["code"]) == (409, "nansen_research_unavailable")


def test_a_saved_job_is_refused_before_effect_when_the_composition_is_removed(ports, plain, owner_a):
    """A worker whose settings no longer compose the authored transports refuses saved jobs and makes no call."""
    http_job = start_http(ports, owner_a)
    intake_id = request_id(ports, owner_a)
    started = start_nansen(ports, owner_a, intake_id, request_key="removed-composition")
    assert started.status_code == 201, started.text
    nansen_job = started.json()["job_id"]
    counting = CountingNansen()
    refusing = InvestigationWorker(plain.app.state.session_factory, plain.app.state.settings,
                                   nansen_transport=lambda token: counting,
                                   http_clients=lambda *a, **k: pytest.fail("no HTTP client may be composed"))
    for job_id, reason in ((http_job, "history_source_unavailable"), (nansen_job, "nansen_research_unavailable")):
        refusing.run_job(uuid.UUID(job_id))
        job = view(ports, owner_a, job_id)
        assert (job["state"], job["terminal_reason"]) == ("UNAVAILABLE", reason)
        assert "ATTEMPT_STARTED" not in [event["kind"] for event in job["events"]]
        assert sum(job["budget"]["unknown_liability"].values()) == 0 and job["budget"]["consumed"]["provider_requests"] == 0
    assert counting.calls == 0


@pytest.mark.parametrize("evidence_class,reason", [
    ("RECORDED_NATIVE_RESPONSE", "HISTORICAL_RECORDING"), ("AUTHORED_HTTP_RESPONSE", "HISTORICAL_RECORDING"),
    ("AUTHORED_FIXTURE", "NANSEN_CONTEXT_NOT_MARKET_OBSERVATION"), ("ANYTHING_ELSE", "NO_TRUSTED_FORWARD_SOURCE")])
def test_no_current_source_is_a_forward_observation(evidence_class, reason):
    observation = forward_observation_from({"evidence_class": evidence_class})
    assert (observation.availability, observation.reason, observation.observed_at) == ("UNAVAILABLE", reason, None)
