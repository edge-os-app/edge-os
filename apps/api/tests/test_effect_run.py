"""Authenticated P09 adoption, execution, immutable report retrieval, and owner scope."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from edge_os_api import p02
from flows import NO_THESIS, submit
from test_investigation_adoption import declaration_body


def _p08_descriptive_body(bundle):
    body = declaration_body(bundle)
    body["edge_spec"]["claim"]["status"] = "DESCRIPTIVE_ONLY"
    body["edge_spec"]["falsification"]["status"] = "DESCRIPTIVE_ONLY"
    body["configuration"]["direction"] = "DESCRIPTIVE"
    body["configuration"]["partitions"] = [{"partition_id": "descriptive", "role": "DESCRIPTIVE",
                                               "start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"}]
    first = body["configuration"]["evaluation_plan"][0]
    first["partition_ids"] = ["descriptive"]
    second_id = str(uuid.uuid4())
    body["evaluation_ids"].append(second_id)
    body["configuration"]["evaluation_plan"].append({**first, "evaluation_id": second_id,
                                                        "variant_id": "comparison"})
    return body


def _run_body(p08_body):
    quote = f"QUOTE:{p02.FIXTURE_STRATEGY['market']['research_binding']['quote_asset']}"
    price = {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "99", "unit": "PRICE"}]}
    volume_true = {"op": "gt", "args": [{"op": "quote_volume"}, {"op": "constant", "value": "4", "unit": quote}]}
    volume_false = {"op": "gt", "args": [{"op": "quote_volume"}, {"op": "constant", "value": "6", "unit": quote}]}
    plans = p08_body["configuration"]["evaluation_plan"]
    return {
        "operation_id": str(uuid.uuid4()), "idempotency_key": f"p09-{uuid.uuid4()}",
        "fixture_id": "synthetic-effect-comparison/1", "adoption": "ADOPT",
        "schedule": {"version": "p09.decision-clock/1", "start": "2026-01-01T00:00:00Z",
                     "end": "2026-01-01T00:02:00Z", "interval_seconds": 60},
        "bindings": [
            {"evaluation_id": plans[0]["evaluation_id"], "trial_id": plans[0]["trial_id"],
             "variant_id": plans[0]["variant_id"], "price_expression": price,
             "volume_expression": volume_true, "essential_inputs": ["price", "quote_volume"]},
            {"evaluation_id": plans[1]["evaluation_id"], "trial_id": plans[1]["trial_id"],
             "variant_id": plans[1]["variant_id"], "price_expression": price,
             "volume_expression": volume_false, "essential_inputs": ["price", "quote_volume"]},
        ],
        "incremental_volume_declared": True,
    }


def test_explicit_run_adoption_precedes_fixture_access_and_report_reopens_exactly(
        client, owner_a, owner_b, pg, monkeypatch):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a,
                      json=p08_body)
    assert p08.status_code == 201, p08.text
    declaration_id = p08.json()["declaration"]["record_id"]
    path = f"/v1/research/requests/{intake_id}/investigations/{declaration_id}/effect-runs"
    adopted = client.post(path, headers=owner_a, json=_run_body(p08_body))
    # The run body must bind the exact identities from the persisted P08 declaration.
    assert adopted.status_code == 201, adopted.text
    run = adopted.json()
    run_id = run["run"]["record_id"]
    assert run["events"][0]["content"]["kind"] == "RUN_ADOPTED"
    assert run["events"][0]["content"]["outcome_accessed"] is False
    assert run["report"] is None
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "0"

    attempt_path = f"/v1/research/requests/{intake_id}/effect-runs/{run_id}/attempts"
    attempt = {"operation_id": str(uuid.uuid4()), "idempotency_key": f"attempt-{uuid.uuid4()}"}
    monkeypatch.setattr("edge_os_api.effect_run._sha256", lambda _path: "0" * 64)
    failed_attempt = {"operation_id": str(uuid.uuid4()), "idempotency_key": f"failed-{uuid.uuid4()}"}
    failed = client.post(attempt_path, headers=owner_a, json=failed_attempt)
    assert failed.status_code == 422
    failed_events = client.get(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_a).json()["events"]
    assert [item["content"]["kind"] for item in failed_events] == ["RUN_ADOPTED", "ATTEMPT_STARTED", "ATTEMPT_FAILED"]
    assert failed_events[-1]["content"]["outcome_accessed"] is False
    monkeypatch.undo()
    same_failed_attempt = client.post(attempt_path, headers=owner_a, json=failed_attempt)
    assert same_failed_attempt.status_code == 409
    evaluated = client.post(attempt_path, headers=owner_a, json=attempt)
    assert evaluated.status_code == 201, evaluated.text
    saved = evaluated.json()
    result = saved["report"]["content"]["result"]
    assert result["status"] == "UNRESOLVED"
    assert result["opportunity_count"] == 4
    assert len(result["shared_event_ids"]) == 4
    assert result["variants"][0]["general_comparison"]["triggered"]["observed_count"] == 2
    assert result["variants"][1]["general_comparison"]["control"]["observed_count"] == 2
    assert result["variants"][1]["incremental_volume_comparison"]["control"]["observed_count"] == 2
    assert saved["report"]["content"]["fixture_sha256"] == run["run"]["content"]["fixture_sha256"]
    assert saved["report"]["content"]["access_order"] == [
        "RUN_ADOPTED", "ATTEMPT_STARTED", "ATTEMPT_FAILED", "ATTEMPT_STARTED", "FIXTURE_READ", "REPORT_SAVED"]

    reopened = client.get(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_a)
    assert reopened.status_code == 200
    assert reopened.json()["report"] == saved["report"]
    replay = client.post(attempt_path, headers=owner_a,
                         json={"operation_id": str(uuid.uuid4()), "idempotency_key": f"replay-{uuid.uuid4()}"})
    assert replay.status_code == 200
    assert replay.json()["report"] == saved["report"]
    assert client.get(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_b).status_code == 404
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "1"
    assert pg.psql(f"select count(*) from effect_run_events where run_id = '{run_id}'") == "6"


def test_held_out_p08_plan_is_refused_before_a_p09_run_is_saved(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    body = declaration_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=body)
    assert p08.status_code == 201, p08.text
    path = f"/v1/research/requests/{intake_id}/investigations/{p08.json()['declaration']['record_id']}/effect-runs"
    run_body = _run_body({"configuration": {"evaluation_plan": [
        {"evaluation_id": body["evaluation_ids"][0], "trial_id": body["trial_ids"][0],
         "variant_id": "primary"}, {"evaluation_id": str(uuid.uuid4()),
                                        "trial_id": body["trial_ids"][0], "variant_id": "comparison"}]}})
    response = client.post(path, headers=owner_a, json=run_body)
    assert response.status_code == 409
    assert "protected_partition_not_authorized" in response.text
    assert pg.psql(f"select count(*) from effect_run_declarations where intake_record_id = '{intake_id}'") == "0"


def test_inspected_outcomes_are_recorded_when_report_persistence_rolls_back(
        client, owner_a, pg, monkeypatch):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a,
                      json=p08_body)
    assert p08.status_code == 201, p08.text
    declaration_id = p08.json()["declaration"]["record_id"]
    path = f"/v1/research/requests/{intake_id}/investigations/{declaration_id}/effect-runs"
    adopted = client.post(path, headers=owner_a, json=_run_body(p08_body))
    assert adopted.status_code == 201, adopted.text
    run_id = adopted.json()["run"]["record_id"]

    original_commit = Session.commit
    injected = {"done": False}

    def fail_report_commit(session):
        if not injected["done"] and any(type(item).__name__ == "EffectReport" for item in session.new):
            injected["done"] = True
            raise RuntimeError("injected report persistence failure after outcome inspection")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_report_commit)
    attempt = {"operation_id": str(uuid.uuid4()), "idempotency_key": f"fault-{uuid.uuid4()}"}
    attempt_path = f"/v1/research/requests/{intake_id}/effect-runs/{run_id}/attempts"
    failed = client.post(attempt_path, headers=owner_a, json=attempt)
    assert injected["done"] is True
    assert failed.status_code == 422

    saved = client.get(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_a)
    assert saved.status_code == 200
    events = saved.json()["events"]
    assert [event["content"]["kind"] for event in events] == [
        "RUN_ADOPTED", "ATTEMPT_STARTED", "ATTEMPT_FAILED"]
    assert events[-1]["content"]["outcome_accessed"] is True
    assert events[-1]["content"]["error_type"] == "RuntimeError"
    assert saved.json()["report"] is None
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "0"
    assert pg.psql(f"select content->>'outcome_accessed' from effect_run_events where run_id = '{run_id}' and content->>'kind' = 'ATTEMPT_FAILED'") == "true"

    same_attempt = client.post(attempt_path, headers=owner_a, json=attempt)
    assert same_attempt.status_code == 409
    recovered = client.post(attempt_path, headers=owner_a,
                            json={"operation_id": str(uuid.uuid4()), "idempotency_key": f"recovered-{uuid.uuid4()}"})
    assert recovered.status_code == 201, recovered.text
    recovered_events = recovered.json()["events"]
    assert [event["content"]["kind"] for event in recovered_events] == [
        "RUN_ADOPTED", "ATTEMPT_STARTED", "ATTEMPT_FAILED", "ATTEMPT_STARTED", "REPORT_SAVED"]
    assert recovered_events[2]["content"]["outcome_accessed"] is True
    assert recovered.json()["report"] is not None
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "1"
