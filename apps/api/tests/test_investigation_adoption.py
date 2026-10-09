"""Authenticated declaration, append-only adoption and retrieval for P08."""

from __future__ import annotations

import uuid

import pytest

from edge_os_api import p02
from conftest import run_threads
from flows import NO_THESIS, answer, submit

ADOPTED_FIELDS = ["edge_spec", "question", "pool_binding", "variants", "direction", "horizons", "sources",
                  "candidate_limit", "parameter_limit", "compute_limit", "period", "partitions",
                  "permitted_access", "stopping_rule", "evaluation_plan", "budget_version", "optional_tools"]


def declaration_body(bundle, *, operation_id=None, key=None):
    body = {
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
            "horizons": [{"value": 15, "unit": "MINUTES"}],
            "sources": ["fixture-unqualified-pool/1"],
            "candidate_limit": 2,
            "parameter_limit": 4,
            "compute_limit": {"max_evaluations": 2, "max_runtime_seconds": 60, "max_cost_usd": "0"},
            "period": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"},
            "partitions": [
                {"partition_id": "training", "role": "TRAINING", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
                {"partition_id": "validation", "role": "VALIDATION", "start": "2026-01-02T00:00:00Z", "end": "2026-01-02T12:00:00Z"},
                {"partition_id": "holdout", "role": "HOLDOUT", "start": "2026-01-02T12:00:00Z", "end": "2026-01-03T00:00:00Z"},
            ],
            "evaluation_plan": [],
            "permitted_access": ["FIXTURE_ONLY"],
            "stopping_rule": "Stop after the two declared comparisons.",
            "budget_version": "p08-research-budget/2",
            "optional_tools": {"creator_history": "UNAVAILABLE", "wallet_pnl": "UNAVAILABLE",
                                "social_signals": "UNAVAILABLE"},
        },
        "adopted_fields": ADOPTED_FIELDS.copy(),
        "field_origins": {name: {"origin": "USER_STATED" if name == "question" else "USER_CONFIRMED",
                                 "source_ref": "original_request" if name == "question" else "investigation-review/2",
                                 "adoption": "ADOPTED"} for name in
                          ADOPTED_FIELDS},
        "trial_ids": [str(uuid.uuid4())],
        "evaluation_ids": [str(uuid.uuid4())],
    }
    body["configuration"]["evaluation_plan"] = [{
        "evaluation_id": body["evaluation_ids"][0], "trial_id": body["trial_ids"][0],
        "variant_id": "primary", "horizon": {"value": 15, "unit": "MINUTES"},
        "partition_ids": ["validation"],
    }]
    return body


def test_declaration_is_saved_and_reopened_with_access_order_before_evaluation(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    before = pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'")
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
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == "1"
    assert pg.psql(f"select count(*) from investigation_access_events e join investigation_declarations d using (declaration_id) where d.intake_record_id = '{intake_id}'") == "1"


def test_descriptive_declaration_saves_and_reopens_without_a_holdout(client, owner_a):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    body = declaration_body(bundle)
    body["edge_spec"]["claim"]["status"] = "DESCRIPTIVE_ONLY"
    body["edge_spec"]["falsification"]["status"] = "DESCRIPTIVE_ONLY"
    body["configuration"]["direction"] = "DESCRIPTIVE"
    body["configuration"]["partitions"] = [{"partition_id": "descriptive", "role": "DESCRIPTIVE",
                                               "start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"}]
    for row in body["configuration"]["evaluation_plan"]:
        row["partition_ids"] = ["descriptive"]
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/investigations"
    saved = client.post(path, headers=owner_a, json=body)
    assert saved.status_code == 201, saved.text
    reopened = client.get(f"{path}/{saved.json()['declaration']['record_id']}", headers=owner_a)
    assert reopened.status_code == 200
    assert reopened.json()["declaration"]["content"]["configuration"]["partitions"] == body["configuration"]["partitions"]


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
    intake_id = bundle["intake"]["record_id"]
    before = pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'")
    body = declaration_body(bundle)
    body["configuration"]["candidate_limit"] = 1
    response = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                           headers=owner_a, json=body)
    assert response.status_code == 422
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == before

    body = declaration_body(bundle)
    additional_evaluation_id = str(uuid.uuid4())
    body["evaluation_ids"].append(additional_evaluation_id)
    body["configuration"]["evaluation_plan"].append({
        **body["configuration"]["evaluation_plan"][0], "evaluation_id": additional_evaluation_id,
        "variant_id": "comparison",
    })
    body["configuration"]["compute_limit"]["max_evaluations"] = 1
    response = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                           headers=owner_a, json=body)
    assert response.status_code == 422
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == before


def test_contradictory_claim_status_direction_pairs_are_rejected_without_records(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    before = pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'")
    path = f"/v1/research/requests/{intake_id}/investigations"
    for claim, falsification, direction in [
        ("HYPOTHESIS", "DESCRIPTIVE_ONLY", "OUTPERFORM"),
        ("DESCRIPTIVE_ONLY", "DESCRIPTIVE_ONLY", "OUTPERFORM"),
    ]:
        body = declaration_body(bundle)
        body["edge_spec"]["claim"]["status"] = claim
        body["edge_spec"]["falsification"]["status"] = falsification
        body["configuration"]["direction"] = direction
        response = client.post(path, headers=owner_a, json=body)
        assert response.status_code == 422
        assert "declaration_semantics_conflict" in str(response.json())
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == before


def test_horizons_partitions_and_explicit_evaluation_plan_are_validated(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    before = pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'")
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/investigations"
    body = declaration_body(bundle)
    body["configuration"]["horizons"] = [{"value": -15, "unit": "MINUTES"}]
    response = client.post(path, headers=owner_a, json=body)
    assert response.status_code == 422
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == before

    body = declaration_body(bundle)
    body["configuration"]["period"] = {"start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"}
    body["configuration"]["partitions"] = [
        {"partition_id": "training", "role": "TRAINING", "start": "2025-12-31T00:00:00Z", "end": "2026-01-01T00:00:00Z"}
    ]
    response = client.post(path, headers=owner_a, json=body)
    assert response.status_code == 422
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == before


@pytest.mark.parametrize("field_path", [
    ("edge_spec", "hypothesis"), ("edge_spec", "claim", "text"),
    ("configuration", "stopping_rule"), ("configuration", "variants", 0, "hypothesis"),
    ("configuration", "pool_binding", "limitations", 0), ("field_origins", "edge_spec", "source_ref"),
])
def test_non_nfc_declaration_text_is_a_field_specific_validation_error(client, owner_a, field_path, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    before = pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'")
    body = declaration_body(bundle)
    target = body
    for part in field_path[:-1]:
        target = target[part]
    target[field_path[-1]] = "Cafe\u0301 cohort" if not isinstance(field_path[-1], int) else "Cafe\u0301 cohort"
    response = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                           headers=owner_a, json=body)
    assert response.status_code == 422
    assert "text_not_nfc" in str(response.json())
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == before


def test_non_nfc_idempotency_key_is_rejected_before_fingerprinting(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    body = declaration_body(bundle)
    body["idempotency_key"] = "Cafe\u0301-key"
    response = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=body)
    assert response.status_code == 422
    assert any(item["code"] == "text_not_nfc" and item["path"] == "/idempotency_key"
               for item in response.json()["findings"])
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == "0"


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


def test_retained_plan_ids_from_an_earlier_proposal_save_against_current_interpretation(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    path = f"/v1/research/requests/{intake_id}/investigations"
    first_proposal = client.get(f"/v1/research/requests/{intake_id}/investigation-proposal", headers=owner_a).json()
    clarification = answer(client, owner_a, bundle, "choose-market", "fixture-market")
    assert clarification.status_code == 201, clarification.text
    current_proposal = client.get(f"/v1/research/requests/{intake_id}/investigation-proposal", headers=owner_a).json()
    assert first_proposal["trial_ids"] != current_proposal["trial_ids"]
    assert first_proposal["evaluation_ids"] != current_proposal["evaluation_ids"]

    body = declaration_body(bundle)
    body["expected_interpretation_revision_id"] = clarification.json()["head"]["interpretation_revision_id"]
    body["edge_spec"] = first_proposal["edge_spec"]
    body["configuration"] = first_proposal["configuration"]
    body["trial_ids"] = first_proposal["trial_ids"]
    body["evaluation_ids"] = first_proposal["evaluation_ids"]
    body["configuration"]["evaluation_plan"] = first_proposal["configuration"]["evaluation_plan"]
    body["configuration"]["stopping_rule"] = "Retain the reviewed plan after clarification."
    response = client.post(path, headers=owner_a, json=body)
    assert response.status_code == 201, response.text
    content = response.json()["declaration"]["content"]
    assert content["interpretation_revision_id"] == clarification.json()["head"]["interpretation_revision_id"]
    assert content["trial_ids"] == first_proposal["trial_ids"]
    assert content["evaluation_ids"] == first_proposal["evaluation_ids"]
    assert content["configuration"]["evaluation_plan"] == first_proposal["configuration"]["evaluation_plan"]
    assert content["configuration"]["stopping_rule"] == "Retain the reviewed plan after clarification."
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == "1"
    assert pg.psql(f"select count(*) from investigation_access_events e join investigation_declarations d using (declaration_id) where d.intake_record_id = '{intake_id}'") == "1"


def test_evaluation_plan_requires_user_confirmation_with_review_source(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    body = declaration_body(bundle)
    body["field_origins"]["evaluation_plan"] = {
        "origin": "USER_STATED", "source_ref": "investigation-review/2", "adoption": "ADOPTED",
    }
    response = client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/investigations",
                           headers=owner_a, json=body)
    assert response.status_code == 422
    assert any(item["path"] == "/field_origins/evaluation_plan" for item in response.json()["findings"])
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{bundle['intake']['record_id']}'") == "0"


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


def test_clarification_committed_after_initial_head_observation_rejects_new_save(client, owner_a, pg, monkeypatch):
    import threading
    from edge_os_api import investigation_adoption

    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    body = declaration_body(bundle, key="p08-clarification-race")
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/investigations"
    observed = threading.Event()
    continue_save = threading.Event()
    original_rows = investigation_adoption.intake_rows
    first_call = True

    def pause_after_initial_read(session, principal, intake_id):
        nonlocal first_call
        rows = original_rows(session, principal, intake_id)
        if first_call:
            first_call = False
            observed.set()
            assert continue_save.wait(timeout=10)
        return rows

    monkeypatch.setattr(investigation_adoption, "intake_rows", pause_after_initial_read)
    result = []
    worker = threading.Thread(target=lambda: result.append(client.post(path, headers=owner_a, json=body)))
    worker.start()
    assert observed.wait(timeout=10)
    clarification = answer(client, owner_a, bundle, "choose-market", "fixture-market")
    assert clarification.status_code == 201, clarification.text
    continue_save.set()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert result[0].status_code == 409
    assert result[0].json()["code"] == "interpretation_revision_conflict"
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{bundle['intake']['record_id']}'") == "0"
    assert pg.psql(f"select count(*) from investigation_access_events e join investigation_declarations d using (declaration_id) where d.intake_record_id = '{bundle['intake']['record_id']}'") == "0"


def test_committed_same_key_replay_survives_later_clarification_but_changed_body_conflicts(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    body = declaration_body(bundle, key="p08-replay-after-clarification")
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/investigations"
    first = client.post(path, headers=owner_a, json=body)
    assert first.status_code == 201, first.text
    clarification = answer(client, owner_a, bundle, "choose-market", "fixture-market")
    assert clarification.status_code == 201
    replay = client.post(path, headers=owner_a, json=body)
    assert replay.status_code == 200
    assert replay.json()["declaration"] == first.json()["declaration"]
    assert replay.json()["access_history"] == first.json()["access_history"]
    changed = {**body, "configuration": {**body["configuration"], "stopping_rule": "Changed request."}}
    conflict = client.post(path, headers=owner_a, json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_key_reused"
    stale_new = client.post(path, headers=owner_a, json=declaration_body(bundle, key="p08-stale-new"))
    assert stale_new.status_code == 409
    intake_id = bundle["intake"]["record_id"]
    assert pg.psql(f"select count(*) from investigation_declarations where intake_record_id = '{intake_id}'") == "1"
    assert pg.psql(f"select count(*) from investigation_access_events e join investigation_declarations d using (declaration_id) where d.intake_record_id = '{intake_id}'") == "1"


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
