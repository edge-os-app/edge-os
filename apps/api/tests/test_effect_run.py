"""Authenticated P09 adoption, execution, immutable report retrieval, and owner scope."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from httpx import Client

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
                     "end": "2026-01-01T00:20:00Z", "interval_seconds": 300},
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
    assert result["opportunity_count"] == 8
    assert result["excluded_count"] == 4
    assert result["missing_outcome_count"] == 4
    assert len(result["shared_event_ids"]) == 4
    for variant in result["variants"]:
        assert variant["general_comparison"]["triggered"]["mean"] == "0.1"
        assert variant["general_comparison"]["control"]["mean"] == "-0.1"
        assert variant["general_comparison"]["triggered_minus_control_mean"] == "0.2"
        assert variant["incremental_volume_comparison"]["triggered_minus_control_mean"] == "0.2"
    assert saved["report"]["content"]["fixture_sha256"] == run["run"]["content"]["fixture_sha256"]
    first_variant_rows = result["variants"][0]["opportunities"]
    assert [(row["decision_time"], row["eligibility_group"], row["response"])
            for row in first_variant_rows] == [
                ("2026-01-01T00:00:00Z", "CONTROL", "-0.1"),
                ("2026-01-01T00:05:00Z", "TRIGGERED", "0.1"),
                ("2026-01-01T00:10:00Z", "EXCLUDED", None),
                ("2026-01-01T00:15:00Z", "EXCLUDED", None),
            ]
    assert saved["report"]["content"]["result"]["shared_input_dependency_ids"]
    assert saved["report"]["content"]["result"]["variants"][0]["opportunities"][0]["horizon"] == {
        "value": 15, "unit": "MINUTES"}
    assert saved["report"]["content"]["access_order"] == [
        "RUN_ADOPTED", "ATTEMPT_STARTED", "ATTEMPT_FAILED", "ATTEMPT_STARTED",
        "OUTCOME_ACCESS_STARTED", "FIXTURE_READ", "REPORT_SAVED"]

    reopened = client.get(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_a)
    assert reopened.status_code == 200
    assert reopened.json()["report"] == saved["report"]
    replay = client.post(attempt_path, headers=owner_a,
                         json={"operation_id": str(uuid.uuid4()), "idempotency_key": f"replay-{uuid.uuid4()}"})
    assert replay.status_code == 200
    assert replay.json()["report"] == saved["report"]
    assert client.get(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_b).status_code == 404
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "1"
    assert pg.psql(f"select count(*) from effect_run_events where run_id = '{run_id}'") == "7"


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
        "RUN_ADOPTED", "ATTEMPT_STARTED", "OUTCOME_ACCESS_STARTED", "ATTEMPT_FAILED"]
    assert events[-2]["content"]["outcome_accessed"] is True
    assert events[-1]["content"]["outcome_accessed"] is True
    assert events[-1]["content"]["error_type"] == "RuntimeError"
    assert saved.json()["report"] is None
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "0"
    assert pg.psql(f"select count(*) from effect_run_events where run_id = '{run_id}' and content->>'kind' = 'OUTCOME_ACCESS_STARTED' and content->>'outcome_accessed' = 'true'") == "1"

    same_attempt = client.post(attempt_path, headers=owner_a, json=attempt)
    assert same_attempt.status_code == 409
    recovered = client.post(attempt_path, headers=owner_a,
                            json={"operation_id": str(uuid.uuid4()), "idempotency_key": f"recovered-{uuid.uuid4()}"})
    assert recovered.status_code == 201, recovered.text
    recovered_events = recovered.json()["events"]
    assert [event["content"]["kind"] for event in recovered_events] == [
        "RUN_ADOPTED", "ATTEMPT_STARTED", "OUTCOME_ACCESS_STARTED", "ATTEMPT_FAILED",
        "ATTEMPT_STARTED", "OUTCOME_ACCESS_STARTED", "REPORT_SAVED"]
    assert recovered_events[2]["content"]["outcome_accessed"] is True
    assert recovered_events[5]["content"]["outcome_accessed"] is True
    assert recovered.json()["report"] is not None
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "1"


def test_numeric_root_is_a_structured_422_and_not_a_saved_run(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
    assert p08.status_code == 201, p08.text
    body = _run_body(p08_body)
    body["bindings"][0]["price_expression"] = {"op": "price"}
    path = f"/v1/research/requests/{intake_id}/investigations/{p08.json()['declaration']['record_id']}/effect-runs"

    response = client.post(path, headers=owner_a, json=body)

    assert response.status_code == 422
    assert "p06_condition_not_boolean" in response.text
    assert pg.psql(f"select count(*) from effect_run_declarations where intake_record_id = '{intake_id}'") == "0"


def test_incremental_volume_requires_distinct_supported_source_mapping(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
    body = _run_body(p08_body)
    body["bindings"][0]["volume_expression"] = body["bindings"][0]["price_expression"]
    path = f"/v1/research/requests/{intake_id}/investigations/{p08.json()['declaration']['record_id']}/effect-runs"

    response = client.post(path, headers=owner_a, json=body)

    assert response.status_code == 422
    assert "incremental_volume_mapping_unsupported" in response.text
    assert pg.psql(f"select count(*) from effect_run_declarations where intake_record_id = '{intake_id}'") == "0"


def test_p08_evaluation_identity_cannot_be_pre_adopted_with_a_second_rule_mapping(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
    assert p08.status_code == 201, p08.text
    declaration_id = p08.json()["declaration"]["record_id"]
    path = f"/v1/research/requests/{intake_id}/investigations/{declaration_id}/effect-runs"
    original = _run_body(p08_body)
    adopted = client.post(path, headers=owner_a, json=original)
    assert adopted.status_code == 201, adopted.text

    changed = _run_body(p08_body)
    changed["bindings"][0]["volume_expression"]["args"][1]["value"] = "7"
    response = client.post(path, headers=owner_a, json=changed)

    assert response.status_code == 409
    assert "p08_evaluation_mapping_conflict" in response.text
    assert pg.psql(f"select count(*) from effect_run_declarations where p08_declaration_id = '{declaration_id}'") == "1"


def test_saved_report_attempt_key_rejects_a_changed_operation_without_new_event(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
    assert p08.status_code == 201, p08.text
    declaration_id = p08.json()["declaration"]["record_id"]
    path = f"/v1/research/requests/{intake_id}/investigations/{declaration_id}/effect-runs"
    adopted = client.post(path, headers=owner_a, json=_run_body(p08_body))
    assert adopted.status_code == 201, adopted.text
    run_id = adopted.json()["run"]["record_id"]
    attempt_path = f"/v1/research/requests/{intake_id}/effect-runs/{run_id}/attempts"
    attempt = {"operation_id": str(uuid.uuid4()), "idempotency_key": f"saved-key-{uuid.uuid4()}"}
    saved = client.post(attempt_path, headers=owner_a, json=attempt)
    assert saved.status_code == 201, saved.text
    before = pg.psql(f"select count(*) from effect_run_events where run_id = '{run_id}'")

    changed_operation = client.post(attempt_path, headers=owner_a,
                                    json={**attempt, "operation_id": str(uuid.uuid4())})

    assert changed_operation.status_code == 409
    assert "attempt_key_reused" in changed_operation.text
    assert pg.psql(f"select count(*) from effect_run_events where run_id = '{run_id}'") == before


def test_concurrent_p08_mapping_adoption_and_outcome_access_keep_one_registered_meaning(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
    assert p08.status_code == 201, p08.text
    declaration_id = p08.json()["declaration"]["record_id"]
    path = f"/v1/research/requests/{intake_id}/investigations/{declaration_id}/effect-runs"
    first_mapping = _run_body(p08_body)
    second_mapping = _run_body(p08_body)
    second_mapping["bindings"][0]["volume_expression"]["args"][1]["value"] = "7"

    with ThreadPoolExecutor(max_workers=2) as pool:
        adoptions = list(pool.map(lambda body: client.post(path, headers=owner_a, json=body),
                                  (first_mapping, second_mapping)))
    assert sorted(response.status_code for response in adoptions) == [201, 409]
    winner = next(response.json() for response in adoptions if response.status_code == 201)
    winning_mapping = first_mapping if winner["run"]["content"]["configuration"]["bindings"] == first_mapping["bindings"] else second_mapping
    run_id = winner["run"]["record_id"]
    attempt_path = f"/v1/research/requests/{intake_id}/effect-runs/{run_id}/attempts"
    attempt = {"operation_id": str(uuid.uuid4()), "idempotency_key": f"race-{uuid.uuid4()}"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        evaluation = pool.submit(client.post, attempt_path, headers=owner_a, json=attempt)
        alternate = pool.submit(client.post, path, headers=owner_a, json={
            **(second_mapping if winning_mapping is first_mapping else first_mapping),
            "operation_id": str(uuid.uuid4()), "idempotency_key": f"alternate-{uuid.uuid4()}"})
        evaluation_response, alternate_response = evaluation.result(), alternate.result()

    assert evaluation_response.status_code == 201, evaluation_response.text
    assert alternate_response.status_code == 409, alternate_response.text
    assert "p08_evaluation_mapping_conflict" in alternate_response.text
    assert pg.psql(f"select count(*) from effect_run_declarations where p08_declaration_id = '{declaration_id}'") == "1"
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "1"


def test_same_p08_cannot_rebind_after_outcome_access(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
    declaration_id = p08.json()["declaration"]["record_id"]
    path = f"/v1/research/requests/{intake_id}/investigations/{declaration_id}/effect-runs"
    first = client.post(path, headers=owner_a, json=_run_body(p08_body))
    assert first.status_code == 201, first.text
    run_id = first.json()["run"]["record_id"]
    attempt_path = f"/v1/research/requests/{intake_id}/effect-runs/{run_id}/attempts"
    evaluated = client.post(attempt_path, headers=owner_a,
                            json={"operation_id": str(uuid.uuid4()), "idempotency_key": f"bind-{uuid.uuid4()}"})
    assert evaluated.status_code == 201, evaluated.text
    changed = _run_body(p08_body)
    changed["bindings"][0]["volume_expression"]["args"][1]["value"] = "7"

    response = client.post(path, headers=owner_a, json=changed)

    assert response.status_code == 409
    assert "p08_evaluation_mapping_conflict" in response.text
    assert pg.psql(f"select count(*) from effect_run_declarations where p08_declaration_id = '{declaration_id}'") == "1"


def test_simultaneous_run_attempts_commit_one_report_and_one_access_boundary(client, owner_a, pg):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
    path = f"/v1/research/requests/{intake_id}/investigations/{p08.json()['declaration']['record_id']}/effect-runs"
    adopted = client.post(path, headers=owner_a, json=_run_body(p08_body))
    run_id = adopted.json()["run"]["record_id"]
    attempt_path = f"/v1/research/requests/{intake_id}/effect-runs/{run_id}/attempts"
    requests = [{"operation_id": str(uuid.uuid4()), "idempotency_key": f"concurrent-{uuid.uuid4()}"}
                for _ in range(2)]

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda body: client.post(attempt_path, headers=owner_a, json=body), requests))

    assert sorted(response.status_code for response in responses) == [200, 201]
    persisted = client.get(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_a).json()
    kinds = [event["content"]["kind"] for event in persisted["events"]]
    assert kinds.count("OUTCOME_ACCESS_STARTED") == 1
    assert kinds.count("REPORT_SAVED") == 1
    assert kinds.count("ATTEMPT_STARTED") == 1
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "1"


def test_baseexception_after_access_boundary_keeps_durable_access_marker(client, owner_a, pg, monkeypatch):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                    input_class="BOUNDED_NO_THESIS").json()
    intake_id = bundle["intake"]["record_id"]
    p08_body = _p08_descriptive_body(bundle)
    p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
    path = f"/v1/research/requests/{intake_id}/investigations/{p08.json()['declaration']['record_id']}/effect-runs"
    adopted = client.post(path, headers=owner_a, json=_run_body(p08_body))
    run_id = adopted.json()["run"]["record_id"]
    attempt = {"operation_id": str(uuid.uuid4()), "idempotency_key": f"crash-{uuid.uuid4()}"}
    class SimulatedProcessInterruption(BaseException):
        pass

    class InterruptFixture:
        def read_text(self, encoding: str) -> str:
            raise SimulatedProcessInterruption()

    hashes = iter((adopted.json()["run"]["content"]["fixture_sha256"],
                   adopted.json()["run"]["content"]["profile_sha256"]))
    monkeypatch.setattr("edge_os_api.effect_run._sha256", lambda _path: next(hashes))
    monkeypatch.setattr("edge_os_api.effect_run.FIXTURE_PATH", InterruptFixture())
    response = client.post(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}/attempts",
                           headers=owner_a, json=attempt)
    assert response.status_code == 422
    monkeypatch.undo()
    events = client.get(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_a).json()["events"]
    marker = next(event for event in events if event["content"]["kind"] == "OUTCOME_ACCESS_STARTED")
    failure = next(event for event in events if event["content"]["kind"] == "ATTEMPT_FAILED")
    assert marker["content"]["outcome_accessed"] is True
    assert failure["content"]["outcome_accessed"] is True
    assert failure["content"]["access_marker_event_id"] == marker["event_id"]
    assert pg.psql(f"select count(*) from effect_reports where run_id = '{run_id}'") == "0"


def test_saved_report_reopens_after_api_process_restart(live_api, owner_a):
    with Client(base_url=live_api.url) as client:
        bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT",
                        input_class="BOUNDED_NO_THESIS").json()
        intake_id = bundle["intake"]["record_id"]
        p08_body = _p08_descriptive_body(bundle)
        p08 = client.post(f"/v1/research/requests/{intake_id}/investigations", headers=owner_a, json=p08_body)
        assert p08.status_code == 201, p08.text
        path = f"/v1/research/requests/{intake_id}/investigations/{p08.json()['declaration']['record_id']}/effect-runs"
        adopted = client.post(path, headers=owner_a, json=_run_body(p08_body))
        assert adopted.status_code == 201, adopted.text
        run_id = adopted.json()["run"]["record_id"]
        attempt = client.post(f"/v1/research/requests/{intake_id}/effect-runs/{run_id}/attempts",
                              headers=owner_a, json={"operation_id": str(uuid.uuid4()),
                                                     "idempotency_key": f"restart-{uuid.uuid4()}"})
        assert attempt.status_code == 201, attempt.text
        original_report = attempt.json()["report"]
    live_api.stop()
    live_api.start()
    with Client(base_url=live_api.url) as restarted_client:
        reopened = restarted_client.get(
            f"/v1/research/requests/{intake_id}/effect-runs/{run_id}", headers=owner_a)
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["report"] == original_report
        assert reopened.json()["events"][-1]["content"]["kind"] == "REPORT_SAVED"
