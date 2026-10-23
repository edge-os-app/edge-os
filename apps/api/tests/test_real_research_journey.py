"""#58 RG01, RG02 and RG04: declaration before collection, recorded-history datasets and saved reports.

Every source is a SYNTHETIC recorded-response bundle. No provider, model, credential or network is used.
"""

from __future__ import annotations

import copy
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

import history_recordings
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.records.models import InvestigationDeclaration
from edge_os_api.research import history_dataset
from edge_os_api.research.history_dataset import HistoryDatasetRow
from edge_os_api.research.investigation_jobs import InvestigationWorker
from flows import NO_THESIS, submit
from research_flows import QUALIFIED, declare, history_body, investigation_request, rising, start, volume_above
from test_investigation_adoption import declaration_body


@pytest.fixture(scope="module")
def research_settings(env, migrated):
    return load_settings({**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded",
                          "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "64",
                          "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS": "3600"})


@pytest.fixture(scope="module")
def research(research_settings):
    with TestClient(create_app(research_settings)) as test_client:
        yield test_client


def worker(client) -> InvestigationWorker:
    return InvestigationWorker(client.app.state.session_factory, client.app.state.settings)


def run_to_end(client, headers, intake_id, declaration_id, **kwargs):
    started = start(client, headers, intake_id, declaration_id, **kwargs)
    assert started.status_code == 201, started.text
    job_id = started.json()["job_id"]
    worker(client).run_pending()
    return client.get(f"/v1/research/investigation-jobs/{job_id}", headers=headers).json()


def test_recorded_bundle_file_matches_its_authored_builder():
    saved = json.loads(history_recordings.BUNDLE_PATH.read_text(encoding="utf-8"))
    assert saved == json.loads(json.dumps(history_recordings.build_bundle()))
    assert history_dataset.BUNDLE_PATH == history_recordings.BUNDLE_PATH
    assert all(source["content_label"] == "SYNTHETIC_FIXTURE" and source["profile"]["evidence_class"] == "SYNTHETIC_FIXTURE"
               for source in saved["sources"])


def test_source_catalog_lists_only_labelled_recordings(research, owner_a):
    catalog = research.get("/v1/research/history-sources", headers=owner_a).json()
    assert catalog["mode"] == "recorded"
    assert "SYNTHETIC" in catalog["label"]
    # SOURCE-LOCAL adds native-shaped recordings; RESEARCH-PORTS-LOCAL adds the same recording through the HTTP
    # clients (authored transport). All are local recordings and carry the synthetic label. The composed default adds
    # exactly one other entry: the one approved actual release source, with its release record.
    released = [item for item in catalog["sources"] if "release" in item]
    assert len(released) == 1
    assert released[0]["source_id"] == "actual-moe-wmon-fwd2h/1"
    assert released[0]["evidence_class"] == "PROVIDER_ACTUAL"
    assert released[0]["content_label"] == "PROVIDER_HISTORY"
    assert released[0]["available"] is True
    assert released[0]["release"]["release_id"] == "actual-moe-history2h-nansen-20261022/1"
    recorded = [item for item in catalog["sources"] if "release" not in item]
    assert {item["evidence_class"] for item in recorded} == {
        "RECORDED_RESPONSE", "RECORDED_NATIVE_RESPONSE", "AUTHORED_HTTP_RESPONSE"}
    assert {item["content_label"] for item in recorded} == {"SYNTHETIC_FIXTURE"}
    assert "SYNTHETIC" in catalog["native_label"]


def test_declaration_is_saved_before_any_collection_and_freezes_hashes(research, owner_a):
    intake_id, declaration_id, body = declare(research, owner_a)
    saved = research.get(f"/v1/research/requests/{intake_id}/history-investigations/{declaration_id}",
                         headers=owner_a).json()
    content = saved["declaration"]["content"]
    assert saved["declaration"]["schema_version"] == "p08.investigation-declaration/3"
    assert content["declaration_state"] == "PRE_OUTCOME_DECLARED" and content["outcome_labels_read"] is False
    assert content["frozen"]["configuration_sha256"] == record_contract.sha256_hex(content["configuration"])
    assert content["frozen"]["rule_map_sha256"] == record_contract.sha256_hex(content["rule_map"])
    assert content["rule_map"]["declaration_hypothesis"] == body["edge_spec"]["hypothesis"]
    assert content["rule_map"]["binding_state"] == "PENDING_DATASET_QUALIFICATION"
    assert saved["access_history"][0]["provider_queries"] == 0
    with research.app.state.session_factory() as session:
        assert session.execute(select(HistoryDatasetRow).where(
            HistoryDatasetRow.declaration_id == uuid.UUID(declaration_id))).first() is None
    # A v3 declaration is invisible to the v2 fixture reads and cannot start a fixture effect run.
    assert research.get(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a).json()["declarations"] == []
    assert research.get(f"/v1/research/requests/{intake_id}/investigations/{declaration_id}",
                        headers=owner_a).status_code == 404


def test_same_key_replays_and_changed_body_conflicts(research, owner_a):
    bundle = investigation_request(research, owner_a)
    intake_id = bundle["intake"]["record_id"]
    body = history_body(research, owner_a, bundle)
    path = f"/v1/research/requests/{intake_id}/history-investigations"
    first = research.post(path, headers=owner_a, json=body)
    again = research.post(path, headers=owner_a, json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["declaration"]["record_id"] == first.json()["declaration"]["record_id"]
    changed = copy.deepcopy(body)
    changed["configuration"]["stopping_rule"] = "Different."
    assert research.post(path, headers=owner_a, json=changed).json()["code"] == "idempotency_key_reused"


@pytest.mark.parametrize("expression", [
    record_contract.FIXTURE_STRATEGY["entry"],
    {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "99", "unit": "PRICE"}]},
])
def test_new_hypothesis_cannot_inherit_an_example_rule(research, owner_a, expression):
    bundle = investigation_request(research, owner_a)
    body = history_body(research, owner_a, bundle, rules=[(expression, volume_above("101"))])
    body["configuration"]["rule_map"]["incremental_volume_declared"] = False
    response = research.post(f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations",
                             headers=owner_a, json=body)
    assert response.status_code == 422 and response.json()["code"] == "example_rule_not_adoptable"


@pytest.mark.parametrize("mutate,code", [
    (lambda c: c["source"].update(evidence_class="PROVIDER_ACTUAL") or c.update(permitted_access=["PROVIDER_ACTUAL"]),
     "actual_data_not_authorized"),
    (lambda c: c["source"].update(profile_sha256="0" * 64), "history_source_changed"),
    (lambda c: c["source"].update(source_id="recorded-syn-missing/1"), "unsupported_history_source"),
    (lambda c: c["market"].update(pool_address="0x" + "dd" * 20), "history_market_mismatch"),
    (lambda c: c["resource_bounds"].update(max_pages=1, provider_requests=1), "resource_bounds_too_small"),
])
def test_unsupported_source_market_window_and_actual_access_are_refused(research, owner_a, mutate, code):
    bundle = investigation_request(research, owner_a)
    body = history_body(research, owner_a, bundle)
    mutate(body["configuration"])
    response = research.post(f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations",
                             headers=owner_a, json=body)
    assert response.json()["code"] == code, response.text


def test_rule_map_must_cover_the_exact_plan_and_only_user_adopted_rules(research, owner_a):
    bundle = investigation_request(research, owner_a)
    body = history_body(research, owner_a, bundle)
    body["configuration"]["rule_map"]["rules"][0]["rule_source"] = "EXAMPLE"
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations"
    assert research.post(path, headers=owner_a, json=body).status_code == 422
    body = history_body(research, owner_a, bundle)
    body["configuration"]["rule_map"]["rules"].pop()
    assert research.post(path, headers=owner_a, json=body).status_code == 422


def test_foreign_owner_cannot_read_or_extend_a_declaration(research, owner_a, owner_b):
    intake_id, declaration_id, _ = declare(research, owner_a)
    assert research.get(f"/v1/research/requests/{intake_id}/history-investigations/{declaration_id}",
                        headers=owner_b).status_code == 404
    assert start(research, owner_b, intake_id, declaration_id).status_code == 404
    foreign = investigation_request(research, owner_b)
    body = history_body(research, owner_b, foreign)
    assert research.post(f"/v1/research/requests/{intake_id}/history-investigations", headers=owner_b,
                         json=body).status_code == 404


def test_fixture_v2_declaration_and_effect_run_are_unchanged(research, owner_a):
    bundle = submit(research, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT", input_class="BOUNDED_NO_THESIS").json()
    response = research.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                             headers=owner_a, json=declaration_body(bundle))
    assert response.status_code == 201
    assert response.json()["declaration"]["schema_version"] == "p08.investigation-declaration/2"


def test_qualified_dataset_is_saved_verbatim_with_recomputable_hashes(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    assert job["state"] == "REPORTED", job
    dataset = research.get(f"/v1/research/history-datasets/{job['dataset']['dataset_id']}", headers=owner_a).json()
    content = dataset["content"]
    assert dataset["hashes_verified"] == {"content_sha256": True, "raw_evidence_sha256": True}
    assert content["schema_version"] == "edge-os.history-dataset/1"
    assert content["verdict"]["overall"] == "QUALIFIED" and content["binding_state"] == "QUALIFIED_BINDING"
    assert content["evidence_class"] == "RECORDED_RESPONSE" and content["content_label"] == "SYNTHETIC_FIXTURE"
    assert content["market_binding"]["evidence_class"] == "SYNTHETIC_FIXTURE"
    assert len(content["buckets"]) == 24 and {bucket["status"] for bucket in content["buckets"]} == {"COMPLETE_OCCUPIED"}
    assert content["buckets"][0]["available_at"] == "2026-09-25T10:05:00Z"
    assert content["provider_requests"] == {"ENVIO_HYPERSYNC": 2}
    assert content["invocations_measured"] == {"count": 2, "label": "EXACT_LOCAL_COUNT"}
    assert content["query_sha256"] and content["collection_sha256"] and content["normalized_sha256"]
    feature = history_dataset.feature_rows(content)[0]
    assert feature["price"] == {"value": "100", "qualified": True, "available_at": "2026-09-25T10:05:00Z",
                                "reasons": []}


def test_tampered_dataset_hash_is_reported_not_repaired(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    dataset_id = job["dataset"]["dataset_id"]
    with research.app.state.session_factory() as session:
        session.execute(text("ALTER TABLE research_local.history_datasets DISABLE TRIGGER history_datasets_immutable"))
        session.execute(text("UPDATE research_local.history_datasets SET content = jsonb_set(content, "
                             "'{buckets,0,close}', '\"999\"') WHERE dataset_id = :id"), {"id": dataset_id})
        session.execute(text("ALTER TABLE research_local.history_datasets ENABLE TRIGGER history_datasets_immutable"))
        session.commit()
    view = research.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json()
    assert view["hashes_verified"]["content_sha256"] is False
    assert view["content"]["buckets"][0]["close"] == "999"


def test_saved_dataset_and_report_reject_update(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    with research.app.state.session_factory() as session:
        for table, key, value in (("history_datasets", "dataset_id", job["dataset"]["dataset_id"]),
                                  ("investigation_reports", "report_id", job["report"]["report_id"])):
            with pytest.raises(Exception):
                session.execute(text(f"UPDATE research_local.{table} SET content = '{{}}' WHERE {key} = :id"),
                                {"id": value})
            session.rollback()


def test_partial_source_is_limited_never_bound_and_reported_as_source_loss(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a, source_id="recorded-syn-provider-failure/1")
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    assert job["state"] == "REPORTED"
    summary = job["dataset"]["summary"]
    assert summary["status"] == "PARTIAL" and summary["stop_reason"] == "PROVIDER_ERROR"
    assert summary["verdict"]["overall"] in {"LIMITED", "UNRESOLVED"}
    assert summary["binding_state"] == "UNAVAILABLE_LIMITED_DATA" and summary["market_binding_id"] is None
    assert {"SOURCE_UNAVAILABLE", "PARTIAL_COVERAGE"} <= set(summary["unavailable_states"])
    dataset = research.get(f"/v1/research/history-datasets/{summary and job['dataset']['dataset_id']}",
                           headers=owner_a).json()["content"]
    missing = [bucket for bucket in dataset["buckets"] if bucket["status"] not in {"COMPLETE_OCCUPIED", "COMPLETE_EMPTY"}]
    assert missing and all(bucket["close"] is None and bucket["quote_volume"] is None for bucket in missing)
    report = job["report"]["content"]
    assert report["outcome"] == "SOURCE_LOSS" and report["outcome_accessed"] is False and report["result"] is None


def test_uncorroborated_source_stays_unresolved_and_is_not_compared(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a, source_id="recorded-syn-uncorroborated/1")
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    assert job["dataset"]["summary"]["verdict"]["overall"] == "UNRESOLVED"
    assert job["report"]["content"]["outcome"] == "LIMITED_DATA"
    assert job["report"]["content"]["outcome_reasons"] == ["VERDICT_UNRESOLVED"]


def test_report_reopens_exactly_and_protected_partitions_stay_unread(research, owner_a):
    intake_id, declaration_id, body = declare(research, owner_a)
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    report = research.get(f"/v1/research/investigation-reports/{job['report']['report_id']}", headers=owner_a).json()
    assert report == job["report"] and report["stored_hash_matches_content"] is True
    content = report["content"]
    assert content["schema_version"] == "edge-os.investigation-report/1"
    assert content["claims"] == {"significance": "NOT_CLAIMED", "capital_authority": "NONE",
                                 "execution_authority": "NONE"}
    assert content["statistical_status"] == "UNRESOLVED"
    assert {item["role"] for item in content["protected_evaluations"]} <= {"VALIDATION", "HOLDOUT"}
    assert [item["role"] for item in content["protected_partitions"]] == ["VALIDATION", "HOLDOUT"]
    assert all(item["state"] == "NOT_READ" for item in content["protected_partitions"])
    rows = [row for variant in content["result"]["variants"] for row in variant["opportunities"]]
    used = [trade["event_time"] for row in rows for trade in (row["start_trade"], row["end_trade"]) if trade]
    assert used and max(used) < "2026-09-25T11:00:00Z"  # nothing from validation or holdout was read
    assert content["rule_map"]["rules"] == body["configuration"]["rule_map"]["rules"]
    assert content["access_order"].index("ATTEMPT_STARTED") < content["access_order"].index("REPORT_SAVED")
    assert content["outcome"] in {"DESCRIBED", "CONTRADICTORY", "INSUFFICIENT_DATA"}
    assert research.get(f"/v1/research/investigation-reports/{job['report']['report_id']}",
                        headers={"Authorization": "Bearer nope"}).status_code == 401


def test_insufficient_and_contradictory_outcomes_are_saved_honestly(research, owner_a):
    never = {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 1},
                                  {"op": "constant", "value": "5", "unit": "DIMENSIONLESS"}]}
    intake_id, declaration_id, _ = declare(research, owner_a, direction="DESCRIPTIVE",
                                           rules=[(never, volume_above("101"))])
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    assert job["report"]["content"]["outcome"] == "INSUFFICIENT_DATA"
    falling = {"op": "lt", "args": [{"op": "price_return", "lookback_buckets": 2},
                                    {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}
    intake_id, declaration_id, _ = declare(research, owner_a, direction="DESCRIPTIVE",
                                           rules=[(rising(1), volume_above("0")), (falling, volume_above("0"))])
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    content = job["report"]["content"]
    signs = {item["triggered_minus_control_mean"].startswith("-") for item in content["variants"]
             if item["outcome"] == "DESCRIBED"}
    assert signs == {True, False}, content["variants"]
    assert content["outcome"] == "CONTRADICTORY"


def test_late_delivered_inputs_are_excluded_not_read_early(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a, source_id="recorded-syn-late-delivery/1",
                                           direction="DESCRIPTIVE")
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    content = job["report"]["content"]
    assert content["outcome"] == "INSUFFICIENT_DATA"
    rows = [row for variant in content["result"]["variants"] for row in variant["opportunities"]]
    assert rows and all(row["eligibility_group"] == "EXCLUDED" for row in rows)
    assert all("SIGNAL_NOT_AVAILABLE_AT_DECISION" in row["reasons"] for row in rows)


def test_dataset_list_is_owner_scoped(research, owner_a, owner_b):
    intake_id, declaration_id, _ = declare(research, owner_a)
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    mine = research.get("/v1/research/history-datasets", headers=owner_a).json()["datasets"]
    assert job["dataset"]["dataset_id"] in {item["dataset_id"] for item in mine}
    entry = next(item for item in mine if item["dataset_id"] == job["dataset"]["dataset_id"])
    assert entry["quote_unit"] == "QUOTE:0x" + "bb" * 20 and entry["hashes_verified"]["content_sha256"] is True
    theirs = research.get("/v1/research/history-datasets", headers=owner_b).json()["datasets"]
    assert job["dataset"]["dataset_id"] not in {item["dataset_id"] for item in theirs}


def test_protected_only_plan_is_saved_as_unsupported_and_reopens(research, owner_a):
    intake_id, declaration_id, _ = declare(research, owner_a, partition="holdout")
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    content = job["report"]["content"]
    assert content["outcome"] == "UNSUPPORTED" and content["outcome_accessed"] is False and content["result"] is None
    assert {item["role"] for item in content["protected_evaluations"]} == {"HOLDOUT"}
    reopened = research.get(f"/v1/research/investigation-reports/{job['report']['report_id']}", headers=owner_a).json()
    assert reopened == job["report"]


def test_contrary_findings_are_kept_for_the_declared_direction(research, owner_a):
    seen = 0
    for direction in ("OUTPERFORM", "UNDERPERFORM"):
        intake_id, declaration_id, _ = declare(research, owner_a, direction=direction)
        job = run_to_end(research, owner_a, intake_id, declaration_id)
        content = job["report"]["content"]
        contrary = {item["variant_id"] for item in content["contrary_findings"]}
        expected = {item["variant_id"] for item in content["variants"] if item["outcome"] == "DESCRIBED"
                    and ((item["triggered_minus_control_mean"].startswith("-") or item["triggered_minus_control_mean"]
                          .strip("0.") == "") if direction == "OUTPERFORM"
                         else not item["triggered_minus_control_mean"].startswith("-"))}
        assert contrary == expected, (direction, content["variants"])
        seen += len(contrary)
        reopened = research.get(f"/v1/research/investigation-reports/{job['report']['report_id']}",
                                headers=owner_a).json()
        assert reopened["content"]["contrary_findings"] == content["contrary_findings"]
    assert seen > 0  # one of the two directions contradicts the recorded prices


class _ProtectedBucket(dict):
    """A bucket whose outcome values must never be read."""

    def __getitem__(self, key):
        if key in {"close", "quote_volume", "available_at", "status", "reasons"}:
            raise AssertionError(f"protected outcome value read: {key}")
        return super().__getitem__(key)

    def get(self, key, default=None):
        return self[key] if key in self else default


def test_protected_partition_values_are_never_read(research, owner_a):
    from edge_os_api.research.comparison_runs import compare_history

    intake_id, declaration_id, _ = declare(research, owner_a)  # TRAINING evaluations; validation and holdout protected
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    declaration = research.get(f"/v1/research/requests/{intake_id}/history-investigations/{declaration_id}",
                               headers=owner_a).json()["declaration"]["content"]
    dataset = research.get(f"/v1/research/history-datasets/{job['dataset']['dataset_id']}",
                           headers=owner_a).json()["content"]
    guarded = copy.deepcopy(dataset)
    guarded["buckets"] = [_ProtectedBucket(bucket) if bucket["bucket_end"] > "2026-09-25T11:00:00Z" else bucket
                          for bucket in dataset["buckets"]]
    assert compare_history(declaration, guarded) == compare_history(declaration, dataset)



def test_protected_partition_before_the_readable_one_is_never_read(research, owner_a):
    from edge_os_api.research.comparison_runs import compare_history

    bundle = investigation_request(research, owner_a)
    body = history_body(research, owner_a, bundle)
    config = body["configuration"]
    config["partitions"] = [
        {"partition_id": "holdout", "role": "HOLDOUT", "start": "2026-09-25T10:00:00Z", "end": "2026-09-25T10:30:00Z"},
        {"partition_id": "validate", "role": "VALIDATION", "start": "2026-09-25T10:30:00Z", "end": "2026-09-25T11:00:00Z"},
        {"partition_id": "train", "role": "TRAINING", "start": "2026-09-25T11:00:00Z", "end": "2026-09-25T12:00:00Z"}]
    for item in config["evaluation_plan"]:
        item["partition_ids"] = ["train"]
    saved = research.post(f"/v1/research/requests/{bundle['intake']['record_id']}/history-investigations",
                          headers=owner_a, json=body)
    assert saved.status_code == 201, saved.text
    intake_id, declaration_id = bundle["intake"]["record_id"], saved.json()["declaration"]["record_id"]
    job = run_to_end(research, owner_a, intake_id, declaration_id)
    declaration = saved.json()["declaration"]["content"]
    dataset = research.get(f"/v1/research/history-datasets/{job['dataset']['dataset_id']}",
                           headers=owner_a).json()["content"]
    guarded = copy.deepcopy(dataset)
    guarded["buckets"] = [_ProtectedBucket(bucket) if bucket["bucket_end"] <= "2026-09-25T11:00:00Z" else bucket
                          for bucket in dataset["buckets"]]
    assert compare_history(declaration, guarded) == compare_history(declaration, dataset)
    # The bucket ending at 11:00 lies in VALIDATION: changing it must not change the report.
    changed = copy.deepcopy(dataset)
    for bucket in changed["buckets"]:
        if bucket["bucket_end"] == "2026-09-25T11:00:00Z":
            bucket["close"] = "1"
    assert compare_history(declaration, changed) == compare_history(declaration, dataset)
    replay_limit = research.get("/v1/research/history-datasets", headers=owner_a).json()["datasets"]
    assert next(item for item in replay_limit
                if item["dataset_id"] == job["dataset"]["dataset_id"])["readable_until"] == "2026-09-25T10:00:00Z"
