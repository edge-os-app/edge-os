"""#58 SOURCE-LOCAL: the investigation worker collects through the accepted P07 transport and corroboration.

Every source is a SYNTHETIC native-shaped recording (`native_history_recordings.py`) replayed by offline recorded
clients. Expected values are written by hand from the recording: 24 swaps on two pages, one `eth_chainId` call and one
receipt call per corroborated swap. Nothing reaches a provider.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

import native_history_recordings
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.research.investigation_jobs import InvestigationWorker
from research_flows import declare, jobs_path, source_entry

QUALIFIED = "native-syn-qualified/1"
NATIVE_BOUNDS = {"provider_requests": 27, "compute_seconds": 30, "max_pages": 2, "max_rows": 200,
                 "max_bytes": 1_048_576, "deadline_seconds": 600}


@pytest.fixture(scope="module")
def native(env, migrated):
    values = {**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded", "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "400",
              "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS": "3600"}
    with TestClient(create_app(load_settings(values))) as client:
        yield client


def run(client, job_id: str) -> dict:
    worker = InvestigationWorker(client.app.state.session_factory, client.app.state.settings)
    return worker.run_job(uuid.UUID(job_id))


def start_native(client, headers, source_id: str = QUALIFIED, bounds: dict | None = None) -> tuple[str, str, dict]:
    intake_id, declaration_id, _ = declare(client, headers, source_id=source_id, bounds=bounds or NATIVE_BOUNDS)
    started = client.post(jobs_path(intake_id, declaration_id), headers=headers,
                          json={"operation_id": str(uuid.uuid4()), "request_key": f"native-{uuid.uuid4()}"})
    assert started.status_code == 201, started.text
    return intake_id, declaration_id, started.json()


def dataset(client, headers, view: dict) -> dict:
    response = client.get(f"/v1/research/history-datasets/{view['dataset']['dataset_id']}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


def test_saved_native_bundle_equals_its_writer():
    saved = json.loads(native_history_recordings.BUNDLE_PATH.read_text(encoding="utf-8"))
    assert saved == native_history_recordings.build_bundle()


def test_native_source_is_listed_with_its_own_market_and_class(native, owner_a):
    entry = source_entry(native, owner_a, QUALIFIED)
    assert entry["evidence_class"] == "RECORDED_NATIVE_RESPONSE" and entry["content_label"] == "SYNTHETIC_FIXTURE"
    assert entry["market"]["pool_address"] == "0x" + "d1" * 20
    assert entry["market"] != source_entry(native, owner_a, "recorded-syn-qualified/1")["market"]
    assert entry["transport"] == {"history_provider": "ENVIO_HYPERSYNC", "provider_version": "envio-hypersync/1",
                                  "corroboration_provider": "QUICKNODE_JSON_RPC", "corroboration_sample_size": 24,
                                  "provider_requests_needed": 27}


def test_worker_collects_through_the_p07_transport_and_saves_its_provenance(native, owner_a):
    _, _, started = start_native(native, owner_a)
    view = run(native, started["job_id"])
    assert view["state"] == "REPORTED", view
    content = dataset(native, owner_a, view)
    assert content["evidence_class"] == "RECORDED_NATIVE_RESPONSE" and content["status"] == "COMPLETE"
    assert content["verdict"]["overall"] == "QUALIFIED" and content["binding_state"] == "QUALIFIED_BINDING"
    transport = content["transport"]
    assert transport["envio"]["attempted_requests"] == 2 and transport["envio"]["pages_framed"] == 2
    assert transport["envio"]["records_framed"] == 24 and transport["envio"]["units"] == "RAW_INTEGER_WORD"
    assert transport["chain_read"]["chain_id"] == 143 and transport["chain_read"]["network"] == "MONAD"
    corroboration = transport["corroboration"]
    assert (corroboration["class"], corroboration["sample_size"], corroboration["mismatches"]) == ("COMPLETE", 24, 0)
    assert transport["client_calls"] == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 25}
    assert content["provider_requests_state"] == "MEASURED_CLIENT_CALLS"
    assert content["provider_requests"] == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 25}
    assert content["evidence_basis"]["corroboration"] == "COMPUTED_FROM_RECORDED_RPC"
    assert content["evidence_basis"]["decimals"] == "RECORDED_DECLARATION"
    assert view["budget"]["consumed"]["provider_requests"] == 27
    assert content["query"]["address"] == "0x" + "d1" * 20
    assert len(transport["envio"]["content_sha256"]) == 2 and content["coverage"]["covers_requested_scan"] is True


def native_run(client, headers, source_id: str, **kwargs) -> tuple[dict, dict]:
    _, _, started = start_native(client, headers, source_id)
    view = run(client, started["job_id"], **kwargs) if kwargs else run(client, started["job_id"])
    return view, dataset(client, headers, view)


def test_a_page_without_its_end_block_fact_is_refused_and_keeps_only_page_one(native, owner_a):
    view, content = native_run(native, owner_a, "native-syn-page-facts-missing/1")
    assert (content["status"], content["stop_reason"]) == ("PARTIAL", "PROVIDER_ERROR")
    assert {"code": "SOURCE_ERROR", "detail": "SourceContractError"} in content["gaps"]
    assert content["coverage"]["page_ranges"] == [[500, 513]] and len(content["trades"]) == 12
    assert content["binding_state"] == "UNAVAILABLE_LIMITED_DATA" and content["market_binding"] is None
    assert content["transport"]["client_calls"] == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 13}
    assert view["report"]["content"]["outcome"] == "SOURCE_LOSS"


def test_a_response_echoing_another_chain_keeps_nothing_and_skips_corroboration(native, owner_a):
    view, content = native_run(native, owner_a, "native-syn-wrong-network/1")
    assert (content["status"], content["stop_reason"]) == ("PARTIAL", "PROVIDER_ERROR")
    assert content["trades"] == [] and content["transport"]["chain_read"] is None
    assert content["transport"]["corroboration"]["reason"] == "NO_RECORDS"
    assert content["transport"]["client_calls"] == {"ENVIO_HYPERSYNC": 1, "QUICKNODE_JSON_RPC": 0}
    assert view["report"]["content"]["outcome"] == "SOURCE_LOSS"


def test_a_provider_failure_counts_the_failed_call_and_is_not_retried(native, owner_a):
    _, content = native_run(native, owner_a, "native-syn-provider-failure/1")
    assert content["stop_reason"] == "PROVIDER_ERROR" and len(content["trades"]) == 12
    assert content["transport"]["client_calls"]["ENVIO_HYPERSYNC"] == 2
    assert content["transport"]["envio"]["pages_framed"] == 1


@pytest.mark.parametrize(("source_id", "reason", "calls"), [
    ("native-syn-receipt-mismatch/1", "BLOCK_MISMATCH", 25),
    ("native-syn-rpc-failure/1", "RPC_FAILED", 25),
])
def test_a_corroboration_mismatch_is_counted_and_blocks_the_binding(native, owner_a, source_id, reason, calls):
    _, content = native_run(native, owner_a, source_id)
    corroboration = content["transport"]["corroboration"]
    assert corroboration["class"] == "COMPLETE" and corroboration["mismatches"] == 1
    assert [entry["reason"] for entry in corroboration["records"] if not entry["matched"]] == [reason]
    assert content["verdict"]["overall"] != "QUALIFIED" and content["market_binding"] is None
    assert content["transport"]["client_calls"]["QUICKNODE_JSON_RPC"] == calls


def test_another_chain_from_the_rpc_is_not_verified_and_fetches_no_receipt(native, owner_a):
    _, content = native_run(native, owner_a, "native-syn-wrong-chain/1")
    transport = content["transport"]
    assert transport["chain_read"]["chain_id"] == 1 and transport["chain_read"]["network"] is None
    assert transport["corroboration"]["class"] == "NONE" and transport["corroboration"]["reason"] == "CHAIN_NOT_MONAD"
    assert transport["client_calls"]["QUICKNODE_JSON_RPC"] == 1
    assert content["verdict"]["overall"] != "QUALIFIED" and content["market_binding"] is None


def test_sampled_corroboration_stays_limited_and_unbound(native, owner_a):
    _, content = native_run(native, owner_a, "native-syn-sampled/1")
    corroboration = content["transport"]["corroboration"]
    assert (corroboration["class"], corroboration["sample_size"]) == ("SAMPLED", 8)
    assert content["verdict"]["overall"] == "LIMITED" and content["binding_state"] == "UNAVAILABLE_LIMITED_DATA"
    assert content["transport"]["client_calls"] == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 9}


def test_late_delivery_is_kept_as_recorded(native, owner_a):
    _, content = native_run(native, owner_a, "native-syn-late-delivery/1")
    first = content["buckets"][0]
    assert (first["bucket_end"], first["available_at"]) == ("2026-09-25T10:05:00Z", "2026-09-25T10:05:30Z")


def test_a_declaration_without_requests_for_corroboration_is_refused(native, owner_a):
    from research_flows import history_body, investigation_request

    bundle = investigation_request(native, owner_a)
    body = history_body(native, owner_a, bundle, source_id=QUALIFIED, bounds={**NATIVE_BOUNDS, "provider_requests": 26})
    refused = native.post(f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations",
                          headers=owner_a, json=body)
    assert refused.status_code == 422 and refused.json()["code"] == "resource_bounds_too_small"
    assert refused.json()["findings"][0]["path"] == "/configuration/resource_bounds/provider_requests"


def test_cancellation_after_the_first_page_refuses_every_later_call(native, owner_a, monkeypatch):
    from edge_os_api.research import native_history_collection

    _, _, started = start_native(native, owner_a)
    original = native_history_collection.RecordedEnvioClient.query

    def cancel_after_first(self, request):
        page = original(self, request)
        native.post(f"/v1/research/investigation-jobs/{started['job_id']}/cancel", headers=owner_a)
        return page

    monkeypatch.setattr(native_history_collection.RecordedEnvioClient, "query", cancel_after_first)
    view = run(native, started["job_id"])
    content = dataset(native, owner_a, view)
    assert view["state"] == "CANCELLED" and content["stop_reason"] == "CANCELLED"
    assert content["transport"]["client_calls"] == {"ENVIO_HYPERSYNC": 1, "QUICKNODE_JSON_RPC": 0}
    assert content["transport"]["chain_read"]["failure"] == "SourceCancelled"
    assert view["budget"]["consumed"]["provider_requests"] == 1
    assert view["budget"]["released"]["provider_requests"] == 26


def test_a_passed_deadline_makes_no_client_call(native, owner_a):
    import datetime as dt

    _, _, started = start_native(native, owner_a)
    late = lambda: dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)  # noqa: E731
    worker = InvestigationWorker(native.app.state.session_factory, native.app.state.settings, clock=late)
    view = worker.run_job(uuid.UUID(started["job_id"]))
    assert view["state"] == "DEADLINE_EXCEEDED" and view["dataset"] is None
    assert view["budget"]["released"]["provider_requests"] == 27


class Killed(BaseException):
    """Ends the worker like a killed process: no `except Exception` handler sees it."""


def test_a_worker_killed_during_collection_keeps_unknown_liability_and_never_collects_again(native, owner_a,
                                                                                            monkeypatch):
    from edge_os_api.research import native_history_collection

    _, _, started = start_native(native, owner_a)
    calls = []

    def killed(self, request):
        calls.append(request)
        raise Killed()

    monkeypatch.setattr(native_history_collection.RecordedEnvioClient, "query", killed)
    with pytest.raises(Killed):
        run(native, started["job_id"])
    monkeypatch.undo()
    view = run(native, started["job_id"])
    assert view["state"] == "UNAVAILABLE" and view["terminal_reason"] == "collection_outcome_unknown"
    assert view["budget"]["unknown_liability"]["provider_requests"] == 27 and len(calls) == 1


def test_another_owner_cannot_start_or_read_and_no_client_is_called(native, owner_a, owner_b, monkeypatch):
    from edge_os_api.research import native_history_collection

    calls = []
    monkeypatch.setattr(native_history_collection.RecordedEnvioClient, "query",
                        lambda self, request: calls.append(request))
    intake_id, declaration_id, _ = declare(native, owner_a, source_id=QUALIFIED, bounds=NATIVE_BOUNDS)
    denied = native.post(jobs_path(intake_id, declaration_id), headers=owner_b,
                         json={"operation_id": str(uuid.uuid4()), "request_key": "native-foreign"})
    assert denied.status_code == 404 and calls == []
    assert native.get(jobs_path(intake_id, declaration_id), headers=owner_b).status_code == 404


def test_a_duplicate_start_returns_the_original_job(native, owner_a):
    intake_id, declaration_id, _ = declare(native, owner_a, source_id=QUALIFIED, bounds=NATIVE_BOUNDS)
    body = {"operation_id": str(uuid.uuid4()), "request_key": "native-same-key"}
    first = native.post(jobs_path(intake_id, declaration_id), headers=owner_a, json=body)
    again = native.post(jobs_path(intake_id, declaration_id), headers=owner_a, json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["job_id"] == first.json()["job_id"]


def test_a_deadline_passing_after_the_pages_refuses_the_chain_read(native, owner_a, monkeypatch):
    import datetime as dt

    from edge_os_api.research import native_history_collection

    _, _, started = start_native(native, owner_a)
    passed = []
    original = native_history_collection.RecordedEnvioClient.query

    def second_page_then_late(self, request):
        page = original(self, request)
        if request.cursor_after is not None:
            passed.append(True)
        return page

    monkeypatch.setattr(native_history_collection.RecordedEnvioClient, "query", second_page_then_late)
    clock = lambda: dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2 if passed else 0)  # noqa: E731
    worker = InvestigationWorker(native.app.state.session_factory, native.app.state.settings, clock=clock)
    view = worker.run_job(uuid.UUID(started["job_id"]))
    content = dataset(native, owner_a, view)
    assert content["status"] == "COMPLETE"
    assert content["transport"]["chain_read"]["failure"] == "SourceTimeout"
    assert content["transport"]["client_calls"] == {"ENVIO_HYPERSYNC": 2, "QUICKNODE_JSON_RPC": 0}
    assert content["market_binding"] is None


def test_the_job_view_separates_computed_transport_facts_from_recorded_declarations(native, owner_a):
    _, _, started = start_native(native, owner_a)
    view = run(native, started["job_id"])
    transport = view["dataset"]["transport"]
    assert transport["envio_pages_framed"] == 2 and (transport["chain_id"], transport["chain_network"]) == (143, "MONAD")
    assert transport["corroboration"] == {"class": "COMPLETE", "sample_size": 24, "population_size": 24, "mismatches": 0}
    assert transport["recorded_declarations"] == ["decimals", "delivery_records", "feasibility_claim",
                                                  "fee_transfer_semantics", "finality_at_collection", "pool_tokens",
                                                  "pool_venue"]


def test_a_bundle_source_job_has_no_transport_summary(native, owner_a):
    intake_id, declaration_id, _ = declare(native, owner_a)
    started = native.post(jobs_path(intake_id, declaration_id), headers=owner_a,
                          json={"operation_id": str(uuid.uuid4()), "request_key": f"bundle-{uuid.uuid4()}"}).json()
    view = run(native, started["job_id"])
    assert view["dataset"]["transport"] is None and "transport" not in dataset(native, owner_a, view)


NATIVE_UNIT = "QUOTE:0x" + "d2" * 20


def test_a_qualified_native_dataset_flows_to_adoption_publication_and_labelled_replay(native, owner_a, owner_b):
    from flows import compiled_thesis, publish
    from research_flows import adoption_body, history_replay_body, reported_dataset, rising, volume_above

    dataset_id = reported_dataset(native, owner_a, source_id=QUALIFIED,
                                  rules=[(rising(1), volume_above("10", NATIVE_UNIT))])
    bundle = compiled_thesis(native, owner_a)
    first, _ = publish(native, owner_a, bundle)
    parent = first.json()["revision_id"]
    adopted = native.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions", headers=owner_a,
                          json=adoption_body(bundle, dataset_id, parent=parent, quote_unit=NATIVE_UNIT))
    assert adopted.status_code == 201, adopted.text
    second, _ = publish(native, owner_a, adopted.json()["bundle"], parent=parent)
    assert second.status_code == 201, second.text
    body = history_replay_body(bundle["head"]["strategy_id"], second.json()["revision_id"], dataset_id)
    saved = native.post("/v1/spot-replays", headers=owner_a, json=body)
    assert saved.status_code in (200, 201), saved.text
    content = saved.json()["content"]
    assert content["result"]["status"] == "COMPLETE" and content["result"]["evidence_class"] == "SYNTHETIC_FIXTURE"
    lineage = content["inputs"]["history_input"]
    assert lineage["source_evidence_class"] == "RECORDED_NATIVE_RESPONSE" and lineage["fill_label"] == "simulated fills"
    assert lineage["dataset_id"] == dataset_id and lineage["rule_linkage"]["state"] == "ENTRY_IS_DECLARED_RULE"
    assert "Simulated fills" in content["notice"]
    assert native.get(f"/v1/spot-replays/{saved.json()['replay_id']}", headers=owner_a).json() == saved.json()
    assert native.get(f"/v1/spot-replays/{saved.json()['replay_id']}", headers=owner_b).status_code == 404
    assert native.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_b).status_code == 404


def test_a_limited_native_dataset_cannot_be_adopted_as_a_market(native, owner_a):
    from flows import compiled_thesis, publish
    from research_flows import adoption_body, reported_dataset

    dataset_id = reported_dataset(native, owner_a, source_id="native-syn-sampled/1")
    bundle = compiled_thesis(native, owner_a)
    first, _ = publish(native, owner_a, bundle)
    refused = native.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions", headers=owner_a,
                          json=adoption_body(bundle, dataset_id, parent=first.json()["revision_id"],
                                             quote_unit=NATIVE_UNIT))
    assert refused.status_code == 409 and refused.json()["code"] == "dataset_not_qualified"
