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
