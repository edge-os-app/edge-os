"""Authenticated declaration, append-only adoption and retrieval for P08."""

from __future__ import annotations

import uuid

import pytest

from edge_os_api import p02
from conftest import run_threads
from flows import NO_THESIS, answer, submit

ADOPTED_FIELDS = ["edge_spec", "question", "pool_binding", "variants", "direction", "horizons", "sources",
                  "candidate_limit", "parameter_limit", "compute_limit", "period", "partitions",
                  "permitted_access", "stopping_rule", "budget_version", "optional_tools"]


def declaration_body(bundle, *, operation_id=None, key=None):
    return {
        "operation_id": operation_id or str(uuid.uuid4()),
        "idempotency_key": key or f"p08-{uuid.uuid4()}",
        "expected_interpretation_revision_id": bundle["head"]["interpretation_revision_id"],
        "edge_spec": {
            "edge_id": str(uuid.uuid4()),
            "version": 1,
            "parent_declaration_id": None,
            "hypothesis": "Creator-linked launch behavior may precede a repeatable price move.",
            "claim": {"status": "HYPOTHESIS", "text": "The declared cohort outperforms the comparison."},
            "falsification": {"status": "DECLARED", "criteria": "The effect is absent in the declared comparison."},
            "alternatives": ["Price momentum explains the association."],
            "unknowns": ["Participant incentives are unverified.", "Persistence and capacity are unknown."],
        },
        "configuration": {
            "question": bundle["intake"]["content"]["original_request"],
            "pool_binding": {
                "profile_id": "fixture-unqualified-pool/1",
                "qualification": "UNQUALIFIED_FIXTURE",
                "limitations": ["Synthetic interface fixture; no production pool is qualified."],
            },
            "variants": [{"variant_id": "primary", "hypothesis": "Primary cohort"},
                         {"variant_id": "comparison", "hypothesis": "Comparison cohort"}],
            "direction": "OUTPERFORM",
            "horizons": ["15 minutes"],
            "sources": ["fixture-unqualified-pool/1"],
            "candidate_limit": 2,
            "parameter_limit": 4,
            "compute_limit": {"max_evaluations": 2, "max_runtime_seconds": 60, "max_cost_usd": "0"},
            "period": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"},
            "partitions": [{"partition_id": "descriptive", "role": "DESCRIPTIVE"}],
            "permitted_access": ["FIXTURE_ONLY"],
            "stopping_rule": "Stop after the two declared comparisons.",
            "budget_version": "p08-research-budget/1",
            "optional_tools": {"creator_history": "UNAVAILABLE", "wallet_pnl": "UNAVAILABLE",
                                "social_signals": "UNAVAILABLE"},
        },
        "adopted_fields": ADOPTED_FIELDS.copy(),
        "field_origins": {name: {"origin": "USER_STATED" if name == "question" else "USER_CONFIRMED",
                                 "source_ref": "original_request" if name == "question" else "investigation-review/1",
                                 "adoption": "ADOPTED"} for name in
                          ADOPTED_FIELDS},
        "trial_ids": [str(uuid.uuid4())],
        "evaluation_ids": [str(uuid.uuid4())],
    }


def test_declaration_is_saved_and_reopened_with_access_order_before_evaluation(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    body = declaration_body(bundle)
    response = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                           headers=owner_a, json=body)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["declaration"]["content"]["configuration"] == body["configuration"]
    assert saved["declaration"]["content"]["edge_spec"] == body["edge_spec"]
    assert saved["access_history"][0]["event"] == "DECLARATION_SAVED"
    assert saved["access_history"][0]["outcome_labels_read"] is False
    assert saved["study_started"] is False
    assert saved["declaration"]["content"]["original_request"] == bundle["intake"]["content"]["original_request"]
    assert saved["declaration"]["content"]["declaration_state"] == "PRE_OUTCOME_DECLARED"
    assert saved["declaration"]["content"]["edge_spec"]["unknowns"]

    reopened = client.get(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations/"
                          f"{saved['declaration']['record_id']}", headers=owner_a)
    assert reopened.status_code == 200
    assert reopened.json()["declaration"] == saved["declaration"]
    assert reopened.json()["access_history"] == saved["access_history"]
    assert pg.psql("select count(*) from investigation_declarations") == "1"
    assert pg.psql("select count(*) from investigation_access_events") == "1"


def test_unbounded_question_gets_a_bounded_unadopted_proposal(client, owner_a):
    bundle = submit(client, owner_a, "Something nobody scripted.", job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    path = f"/v1/research/requests/{bundle['intake']['record_id']}"
    proposal = client.get(f"{path}/investigation-proposal", headers=owner_a)
    assert proposal.status_code == 200, proposal.text
    assert proposal.json()["interpretation_revision_id"] is None
    assert proposal.json()["configuration"]["question"] == "Something nobody scripted."
    assert proposal.json()["adopted_fields"] == []
    assert all(item["adoption"] == "PENDING" for item in proposal.json()["field_origins"].values())
    body = declaration_body(bundle)
    body["expected_interpretation_revision_id"] = None
    saved = client.post(f"{path}/investigations", headers=owner_a, json=body)
    assert saved.status_code == 201, saved.text
    assert saved.json()["declaration"]["content"]["interpretation_revision_id"] is None


def test_candidate_and_evaluation_limits_cover_variants(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    body = declaration_body(bundle)
    body["configuration"]["candidate_limit"] = 1
    before = pg.psql("select count(*) from investigation_declarations")
    response = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                           headers=owner_a, json=body)
    assert response.status_code == 422
    assert pg.psql("select count(*) from investigation_declarations") == before

    body = declaration_body(bundle)
    body["configuration"]["compute_limit"]["max_evaluations"] = 1
    response = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                           headers=owner_a, json=body)
    assert response.status_code == 422
    assert pg.psql("select count(*) from investigation_declarations") == before


def test_missing_adoption_and_cross_owner_adoption_are_rejected_without_records(client, owner_a, owner_b, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    body = declaration_body(bundle)
    body["adopted_fields"].remove("stopping_rule")
    before = pg.psql("select count(*) from investigation_declarations")
    missing = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                          headers=owner_a, json=body)
    assert missing.status_code == 422
    assert missing.json()["findings"][0]["code"] == "required_setting_not_adopted"
    assert pg.psql("select count(*) from investigation_declarations") == before

    valid = declaration_body(bundle)
    denied = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                         headers=owner_b, json=valid)
    assert denied.status_code == 404
    assert pg.psql("select count(*) from investigation_declarations") == before


def test_same_key_replays_saved_identity_and_hypotheses_keep_distinct_lineage(client, owner_a, owner_b):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    first_body = declaration_body(bundle, key="p08-same-key")
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/investigations"
    first = client.post(path, headers=owner_a, json=first_body)
    assert first.status_code == 201, first.text
    replay = client.post(path, headers=owner_a, json=first_body)
    assert replay.status_code == 200
    assert replay.json()["declaration"] == first.json()["declaration"]
    assert replay.json()["access_history"] == first.json()["access_history"]
    assert replay.json()["idempotent_replay"] is True

    second_body = declaration_body(bundle)
    second_body["edge_spec"]["hypothesis"] = "A distinct hypothesis about unsuccessful launches."
    second = client.post(path, headers=owner_a, json=second_body)
    assert second.status_code == 201
    assert second.json()["declaration"]["content"]["edge_spec"]["edge_id"] != first.json()["declaration"]["content"]["edge_spec"]["edge_id"]
    foreign_id = first.json()["declaration"]["record_id"]
    foreign_read = client.get(f"{path}/{foreign_id}", headers=owner_b)
    assert foreign_read.status_code == 404
    p02.validate_http_error(foreign_read.json())

    child = declaration_body(bundle)
    child["edge_spec"].update({"edge_id": first.json()["declaration"]["content"]["edge_spec"]["edge_id"],
                               "version": 2, "parent_declaration_id": foreign_id})
    child["edge_spec"]["hypothesis"] = "Revise the original hypothesis after new evidence."
    revised = client.post(path, headers=owner_a, json=child)
    assert revised.status_code == 201, revised.text
    assert revised.json()["declaration"]["content"]["edge_spec"]["version"] == 2
    assert revised.json()["declaration"]["content"]["edge_spec"]["parent_declaration_id"] == foreign_id


def test_stale_interpretation_and_unknown_parent_are_rejected(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    stale_body = declaration_body(bundle)
    updated = answer(client, owner_a, bundle, "choose-market", "fixture-market")
    assert updated.status_code == 201
    stale = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                        headers=owner_a, json=stale_body)
    assert stale.status_code == 409
    assert stale.json()["code"] == "interpretation_revision_conflict"

    current_body = declaration_body(updated.json())
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/investigations"
    first = client.post(path, headers=owner_a, json=current_body)
    assert first.status_code == 201, first.text
    child = declaration_body(updated.json())
    child["edge_spec"].update({"edge_id": first.json()["declaration"]["content"]["edge_spec"]["edge_id"],
                               "version": 2, "parent_declaration_id": str(uuid.uuid4())})
    before = pg.psql("select count(*) from investigation_declarations")
    invalid_parent = client.post(path, headers=owner_a, json=child)
    assert invalid_parent.status_code == 409
    assert invalid_parent.json()["code"] == "parent_declaration_conflict"
    assert pg.psql("select count(*) from investigation_declarations") == before


def test_concurrent_same_key_save_commits_one_declaration_and_access_event(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    body = declaration_body(bundle, key="p08-concurrent-key")
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/investigations"
    responses = run_threads(2, lambda _index: client.post(path, headers=owner_a, json=body))
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json()["declaration"] == responses[1].json()["declaration"]
    assert pg.psql("select count(*) from investigation_declarations where idempotency_key = 'p08-concurrent-key'") == "1"
    assert pg.psql("select count(*) from investigation_access_events") == pg.psql("select count(*) from investigation_declarations")


def test_declaration_rows_reject_update_and_delete(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    response = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                           headers=owner_a, json=declaration_body(bundle))
    assert response.status_code == 201
    declaration_id = response.json()["declaration"]["record_id"]
    for statement in (
        f"update investigation_declarations set content = '{{}}' where declaration_id = '{declaration_id}'",
        f"delete from investigation_declarations where declaration_id = '{declaration_id}'",
        "delete from investigation_access_events",
    ):
        with pytest.raises(Exception) as caught:
            pg.psql(statement)
        assert "immutable" in str(getattr(caught.value, "stderr", caught.value))
