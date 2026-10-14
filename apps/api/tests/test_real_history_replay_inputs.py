"""#58 RG05: saved recorded-history datasets through the unchanged P13 replay runtime.

Fills are simulated. Sources are SYNTHETIC recorded responses; no result is observed market history.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from edge_os_api.core.errors import AppError
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.replay import history_inputs, saved_runs, simulator
from flows import compiled_thesis, publish
from research_flows import adoption_body, history_replay_body, reported_dataset


@pytest.fixture(scope="module")
def research(env, migrated):
    settings = load_settings({**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded",
                              "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "200",
                              "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS": "9000"})
    with TestClient(create_app(settings)) as client:
        yield client


def history_strategy(client, headers, source_id="recorded-syn-qualified/1", direction="OUTPERFORM"):
    """A fixture revision, then a NEW revision on the dataset market. Returns ids for both."""
    dataset_id = reported_dataset(client, headers, source_id=source_id, direction=direction)
    bundle = compiled_thesis(client, headers)
    first, _ = publish(client, headers, bundle)
    parent = first.json()["revision_id"]
    adopted = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions", headers=headers,
                          json=adoption_body(bundle, dataset_id, parent=parent))
    assert adopted.status_code == 201, adopted.text
    second, _ = publish(client, headers, adopted.json()["bundle"], parent=parent)
    assert second.status_code == 201, second.text
    return bundle["head"]["strategy_id"], parent, second.json()["revision_id"], dataset_id


def replay(client, headers, body):
    response = client.post("/v1/spot-replays", headers=headers, json=body)
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_adopted_revision_replays_on_its_dataset_with_exact_lineage(research, owner_a):
    strategy_id, _, revision_id, dataset_id = history_strategy(research, owner_a)
    saved = replay(research, owner_a, history_replay_body(strategy_id, revision_id, dataset_id))
    content = saved["content"]
    assert content["result"]["status"] == "COMPLETE", content["result"].get("reason")
    assert content["result"]["evidence_class"] == "SYNTHETIC_FIXTURE"
    lineage = content["inputs"]["history_input"]
    assert lineage["dataset_id"] == dataset_id and lineage["fill_label"] == "simulated fills"
    assert lineage["rule_linkage"]["state"] == "ENTRY_IS_DECLARED_RULE"
    assert content["result"]["trades"], "the declared rule should trade on the recorded prices"
    assert lineage["dataset_market_binding_id"] == lineage["strategy_market_binding_id"]
    assert lineage["source_evidence_class"] == "RECORDED_RESPONSE" and lineage["content_label"] == "SYNTHETIC_FIXTURE"
    assert content["strategy_revision_id"] == revision_id and content["dataset_fixture_id"] is None
    assert "Simulated fills" in content["notice"]
    dataset = research.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json()
    assert content["inputs"]["buckets"] == [bucket for bucket in dataset["content"]["buckets"]
                                            if bucket["bucket_end"] < "2026-09-25T11:00:00Z"]
    assert lineage["declaration_id"] == dataset["content"]["declaration_id"]
    again = research.get(f"/v1/spot-replays/{saved['replay_id']}", headers=owner_a).json()
    assert again == saved


def test_original_fixture_revision_still_fails_on_the_history_market(research, owner_a):
    strategy_id, fixture_revision, _, dataset_id = history_strategy(research, owner_a)
    saved = replay(research, owner_a, history_replay_body(strategy_id, fixture_revision, dataset_id))
    assert saved["content"]["result"]["status"] == "UNAVAILABLE"
    assert saved["content"]["result"]["reason"]["code"] == "MARKET_BINDING_MISMATCH"
    assert saved["content"]["inputs"]["history_input"]["rule_linkage"]["state"] == "ENTRY_NOT_FROM_THIS_DECLARATION"


@pytest.mark.parametrize("start,end,code", [
    ("2026-09-25T10:05:00Z", "2026-09-25T10:40:00Z", "DATASET_COVERAGE_UNPROVEN"),  # warm-up not available
    ("2026-09-25T11:30:00Z", "2026-09-25T12:30:00Z", "DATASET_COVERAGE_UNPROVEN"),  # window truncated by the data
])
def test_warmup_and_truncated_windows_are_refused_by_the_runtime(research, owner_a, start, end, code):
    strategy_id, _, revision_id, dataset_id = history_strategy(research, owner_a, direction="DESCRIPTIVE")
    saved = replay(research, owner_a, history_replay_body(strategy_id, revision_id, dataset_id, start=start, end=end))
    assert saved["content"]["result"]["status"] == "UNAVAILABLE"
    assert saved["content"]["result"]["reason"]["code"] == code


def test_late_delivered_inputs_are_never_read_early(research, owner_a):
    strategy_id, _, revision_id, dataset_id = history_strategy(research, owner_a, "recorded-syn-late-delivery/1")
    saved = replay(research, owner_a, history_replay_body(strategy_id, revision_id, dataset_id))
    result = saved["content"]["result"]
    assert result["status"] == "COMPLETE" and result["trades"] == []
    decisions = [event for event in result["events"] if event["kind"] == "DECISION"]
    assert decisions and all(event["entry"]["value"] == "UNKNOWN" for event in decisions)
    reasons = {reason for event in decisions for reason in event["entry"]["reasons"]}
    assert any(reason.startswith(("FUTURE_INFORMATION", "LATE_INPUT")) for reason in reasons), reasons


def test_limited_dataset_is_refused_by_the_runtime_not_relabelled(research, owner_a):
    dataset_id = reported_dataset(research, owner_a, source_id="recorded-syn-provider-failure/1")
    strategy_id, _, revision_id, _ = history_strategy(research, owner_a)
    saved = replay(research, owner_a, history_replay_body(strategy_id, revision_id, dataset_id))
    assert saved["content"]["result"]["reason"]["code"] == "DATASET_COVERAGE_UNPROVEN"
    assert saved["content"]["inputs"]["dataset_qualification"] in {"LIMITED", "UNRESOLVED"}


def test_foreign_dataset_and_body_shape_are_refused(research, owner_a, owner_b):
    strategy_id, _, revision_id, dataset_id = history_strategy(research, owner_a)
    foreign_dataset = reported_dataset(research, owner_b)
    body = history_replay_body(strategy_id, revision_id, foreign_dataset)
    assert research.post("/v1/spot-replays", headers=owner_a, json=body).status_code == 404
    both = {**history_replay_body(strategy_id, revision_id, dataset_id), "dataset_fixture_id": "p13.wc01/1"}
    assert research.post("/v1/spot-replays", headers=owner_a, json=both).status_code == 422
    neither = history_replay_body(strategy_id, revision_id, dataset_id)
    del neither["history_dataset_id"]
    assert research.post("/v1/spot-replays", headers=owner_a, json=neither).status_code == 422


def relabelled(row, **labels):
    """A detached copy of a saved dataset with the given top-level labels. Nothing is written."""
    row.content = {**row.content, **labels}
    return row


def detached_dataset(research, dataset_id):
    with research.app.state.session_factory() as session:
        row = session.get(history_inputs.history_dataset.HistoryDatasetRow, uuid.UUID(dataset_id))
        session.expunge(row)
    return row


def test_a_dataset_cannot_claim_provider_history_by_its_profile_label_alone(research, owner_a):
    _, _, _, dataset_id = history_strategy(research, owner_a)
    row = relabelled(detached_dataset(research, dataset_id), profile_evidence_class="PROVIDER_ACTUAL")
    with pytest.raises(AppError) as refused:  # a recorded or stand-in source never becomes provider history
        history_inputs.replay_dataset(row, dt.datetime(2026, 9, 25, 11, 0, tzinfo=dt.timezone.utc))
    assert (refused.value.status, refused.value.code) == (409, "evidence_class_inconsistent")


def test_actual_provider_history_passes_through_with_unchanged_numbers(research, owner_a):
    """Labels only: the buckets are the saved recorded ones, relabelled in memory as an approved actual release would
    have written them. No provider data exists; the check is that the class passes and nothing else changes."""
    strategy_id, _, revision_id, dataset_id = history_strategy(research, owner_a)
    saved = replay(research, owner_a, history_replay_body(strategy_id, revision_id, dataset_id))
    strategy = saved["content"]["inputs"]["strategy"]
    window_end = dt.datetime(2026, 9, 25, 11, 0, tzinfo=dt.timezone.utc)
    synthetic = history_inputs.replay_dataset(detached_dataset(research, dataset_id), window_end)
    row = relabelled(detached_dataset(research, dataset_id), evidence_class="PROVIDER_ACTUAL",
                     profile_evidence_class="PROVIDER_ACTUAL",
                     operating_release={"release_id": "actual-label-check/1", "sha256": "0" * 64, "kind": "ACTUAL"})
    dataset = history_inputs.replay_dataset(row, window_end)
    assert dataset.evidence_class == "PROVIDER_ACTUAL"
    assert (dataset.buckets, dataset.qualification, dataset.coverage_complete, dataset.market_binding_id) == (
        synthetic.buckets, synthetic.qualification, synthetic.coverage_complete, synthetic.market_binding_id)
    inputs = saved["content"]["inputs"]  # the saved run's own identities, so only the evidence class differs
    run = simulator.ReplayInput(strategy_revision_id=revision_id, run_configuration_id=inputs["run_configuration_id"],
                                dataset=dataset, essential_evidence=inputs["essential_evidence"],
                                window_start=dt.datetime.fromisoformat(inputs["window_start"].replace("Z", "+00:00")),
                                window_end=window_end, initial_cash_quote=inputs["initial_cash_quote"])
    result = simulator.run_spot_replay(strategy, run)
    baseline = simulator.run_spot_replay(strategy, dataclasses.replace(run, dataset=synthetic))
    assert result.evidence_class == "PROVIDER_ACTUAL" and result.repeatability_id != baseline.repeatability_id
    assert (result.trades, result.metrics, result.metric_statuses) == (
        baseline.trades, baseline.metrics, baseline.metric_statuses)
    snapshot = history_inputs.snapshot(row, strategy, {"state": "ENTRY_IS_DECLARED_RULE"})
    assert (snapshot["source_evidence_class"], snapshot["profile_evidence_class"], snapshot["fill_label"]) == (
        "PROVIDER_ACTUAL", "PROVIDER_ACTUAL", "simulated fills")
    assert saved_runs.notice_for(result.evidence_class) != saved_runs.notice_for("SYNTHETIC_FIXTURE")
    assert "No trading permission" in saved_runs.notice_for(result.evidence_class)


def test_replay_never_reads_validation_or_holdout_buckets(research, owner_a):
    strategy_id, _, revision_id, dataset_id = history_strategy(research, owner_a)  # train 10:00-11:00, then protected
    before = research.get("/v1/spot-replays/00000000-0000-4000-8000-000000000000", headers=owner_a).status_code
    refused = research.post("/v1/spot-replays", headers=owner_a, json=history_replay_body(
        strategy_id, revision_id, dataset_id, end="2026-09-25T11:05:00Z"))
    assert before == 404
    assert refused.status_code == 409 and refused.json()["code"] == "protected_partition_not_authorized"
    listed = research.get("/v1/research/history-datasets", headers=owner_a).json()["datasets"]
    assert next(item for item in listed if item["dataset_id"] == dataset_id)["readable_until"] == "2026-09-25T11:00:00Z"
    allowed = replay(research, owner_a, history_replay_body(strategy_id, revision_id, dataset_id))
    assert max(bucket["bucket_end"] for bucket in allowed["content"]["inputs"]["buckets"]) <= "2026-09-25T11:00:00Z"


def test_descriptive_dataset_reads_its_whole_window(research, owner_a):
    strategy_id, _, revision_id, dataset_id = history_strategy(research, owner_a, direction="DESCRIPTIVE")
    listed = research.get("/v1/research/history-datasets", headers=owner_a).json()["datasets"]
    assert next(item for item in listed if item["dataset_id"] == dataset_id)["readable_until"] == "2026-09-25T12:00:00Z"
    saved = replay(research, owner_a, history_replay_body(strategy_id, revision_id, dataset_id,
                                                          end="2026-09-25T11:20:00Z"))
    assert saved["content"]["result"]["status"] == "COMPLETE"
