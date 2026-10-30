"""DEMO-POLISH-L1: with an approved ACTUAL release composed, the server offers only that release's real source.

The default server composes the registered MOE release. These checks prove three things at the authenticated API:
the source catalog lists exactly the release's real history source, a recorded source is refused by the declaration
validator even when a client sends it directly, and the recorded source list returns unchanged when no release is
composed. No provider, credential or network is used.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from edge_os_api.core.research import released_runtime_bootstrap
from edge_os_api.main import create_app
from edge_os_api.research import history_dataset
from flows import NO_THESIS, submit
from research_flows import FIELDS, QUALIFIED, REVIEW, rising, volume_above

ACTUAL_SOURCE = "actual-moe-wmon-fwd2h/1"


@pytest.fixture(scope="module")
def actual_client(settings):
    """The default composition: the registered ACTUAL release."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def no_release_client(env, settings, monkeypatch):
    """The same application with the code-owned release registry explicitly emptied."""
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", {})
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def investigation_bundle(client, headers) -> dict[str, Any]:
    response = submit(client, headers, NO_THESIS, job="INVESTIGATE_EFFECT", input_class="BOUNDED_NO_THESIS")
    assert response.status_code == 201, response.text
    return response.json()


def recorded_body(bundle: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """A valid recorded-source declaration body, built without asking the server's catalog for the source."""
    trial = str(uuid.uuid4())
    unit = f"QUOTE:{entry['market']['quote_asset']}"
    rules = [(rising(1), volume_above("101", unit)), (rising(2), volume_above("102", unit))]
    evaluations = [str(uuid.uuid4()) for _ in rules]
    return {
        "operation_id": str(uuid.uuid4()), "idempotency_key": f"polish-{uuid.uuid4()}",
        "expected_interpretation_revision_id": bundle["head"]["interpretation_revision_id"],
        "edge_spec": {
            "edge_id": str(uuid.uuid4()), "version": 1, "parent_declaration_id": None,
            "hypothesis": "Describe the recorded pool only.",
            "claim": {"status": "DESCRIPTIVE_ONLY", "text": "Describe only."},
            "falsification": {"status": "DESCRIPTIVE_ONLY", "criteria": "No outcome claim."},
            "alternatives": ["Short-term noise explains any difference."],
            "unknowns": ["The source is a local recording."],
        },
        "configuration": {
            "question": bundle["intake"]["content"]["original_request"],
            "source": {"source_id": entry["source_id"], "profile_sha256": entry["profile_sha256"],
                       "evidence_class": entry["evidence_class"]},
            "market": copy.deepcopy(entry["market"]),
            "window": dict(entry["window"]),
            "variants": [{"variant_id": f"v{index + 1}", "hypothesis": f"Adopted rule v{index + 1}"}
                         for index in range(len(rules))],
            "direction": "DESCRIPTIVE",
            "horizons": [{"value": 5, "unit": "MINUTES"}],
            "partitions": [{"partition_id": "described", "role": "DESCRIPTIVE",
                            "start": entry["window"]["start"], "end": entry["window"]["end"]}],
            "evaluation_plan": [{"evaluation_id": evaluation, "trial_id": trial, "variant_id": f"v{index + 1}",
                                 "horizon": {"value": 5, "unit": "MINUTES"}, "partition_ids": ["described"]}
                                for index, evaluation in enumerate(evaluations)],
            "schedule": {"version": "p09.decision-clock/1", "start": entry["window"]["start"],
                         "end": entry["window"]["end"], "interval_seconds": 300},
            "rule_map": {"schema_version": "edge-os.hypothesis-rule-map/1", "control": "UNTRIGGERED_DECISIONS",
                         "incremental_volume_declared": True,
                         "rules": [{"evaluation_id": evaluation, "trial_id": trial, "variant_id": f"v{index + 1}",
                                    "price_expression": price, "volume_expression": volume,
                                    "essential_inputs": ["price", "quote_volume"], "rule_source": "USER_ADOPTED"}
                                   for index, (evaluation, (price, volume)) in enumerate(zip(evaluations, rules))]},
            "resource_bounds": {"provider_requests": 2, "compute_seconds": 30, "max_pages": 2,
                                "max_rows": 200, "max_bytes": 1_048_576, "deadline_seconds": 600},
            "permitted_access": [entry["evidence_class"]],
            "stopping_rule": "Stop after the declared evaluations on the declared window.",
            "budget_version": "edge-os.research-budget/1",
        },
        "field_origins": {name: {"origin": "USER_STATED" if name == "question" else "USER_CONFIRMED",
                                 "source_ref": "original_request" if name == "question" else REVIEW,
                                 "adoption": "ADOPTED"} for name in FIELDS},
        "trial_ids": [trial],
        "evaluation_ids": evaluations,
    }


def test_an_actual_release_serves_only_its_real_source(actual_client, owner_a):
    catalog = actual_client.get("/v1/research/history-sources", headers=owner_a).json()
    runtime = actual_client.app.state.research_runtime
    assert runtime is not None and runtime.release.kind == "ACTUAL"
    assert [item["source_id"] for item in catalog["sources"]] == [ACTUAL_SOURCE]
    assert catalog["sources"][0]["evidence_class"] == "PROVIDER_ACTUAL"
    assert catalog["operating_release"]["kind"] == "ACTUAL"
    # No recorded, native or authored test scenario is offered by this composition.
    assert set(history_dataset.served_sources(runtime)) == {ACTUAL_SOURCE}


def test_the_server_refuses_a_recorded_source_it_no_longer_offers(actual_client, owner_a):
    recorded = next(item for item in history_dataset.catalog()["sources"] if item["source_id"] == QUALIFIED)
    bundle = investigation_bundle(actual_client, owner_a)
    body = recorded_body(bundle, recorded)
    saved = actual_client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations",
                               headers=owner_a, json=body)
    assert saved.status_code == 422, saved.text
    assert saved.json()["code"] == "unsupported_history_source"


def test_without_an_actual_release_the_recorded_sources_still_appear(no_release_client, owner_a):
    assert no_release_client.app.state.research_runtime is None
    catalog = no_release_client.get("/v1/research/history-sources", headers=owner_a).json()
    ids = {item["source_id"] for item in catalog["sources"]}
    assert QUALIFIED in ids
    assert ACTUAL_SOURCE not in ids
    assert {item["content_label"] for item in catalog["sources"]} == {"SYNTHETIC_FIXTURE"}
    # The unchanged recorded-source path still declares and saves without a release.
    recorded = next(item for item in catalog["sources"] if item["source_id"] == QUALIFIED)
    bundle = investigation_bundle(no_release_client, owner_a)
    saved = no_release_client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations",
                                   headers=owner_a, json=recorded_body(bundle, recorded))
    assert saved.status_code == 201, saved.text
