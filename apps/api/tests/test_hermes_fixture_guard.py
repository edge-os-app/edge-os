"""The fixture API fails closed on a request that the host Hermes interpreter wrote.

The two applications share the database. The Hermes application creates a request and an attempt. The fixture
application must refuse to read the request, list it, or append a clarification to it. A fixture-only request keeps its
normal behaviour.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from hermes_cases import CaseRunner, case, intake_body, turn_result

from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app


def hermes_client(env, runner: CaseRunner) -> TestClient:
    settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})
    return TestClient(create_app(settings, hermes_runner=runner))


def fixture_client(env) -> TestClient:
    return TestClient(create_app(load_settings(env)))


def test_the_fixture_api_refuses_to_read_list_or_clarify_a_hermes_request(env, migrated, owner_a) -> None:
    runner = CaseRunner(turn_result(case("concrete-thesis")["provider"]))
    with hermes_client(env, runner) as hermes:
        created = hermes.post("/v1/research/requests", json=intake_body("concrete-thesis"), headers=owner_a)
    assert created.status_code == 201, created.text
    bundle = created.json()
    intake_id = bundle["intake"]["record_id"]

    with fixture_client(env) as fixture:
        detail = fixture.get(f"/v1/research/requests/{intake_id}", headers=owner_a)
        listed = fixture.get("/v1/research/requests", headers=owner_a)
        clarified = fixture.post(f"/v1/research/requests/{intake_id}/clarifications", headers=owner_a, json={
            "previous_revision_id": bundle["head"]["interpretation_revision_id"],
            "question_id": "adopt-suggested-settings", "answer_text": "a new answer"})
        with fixture.app.state.engine.connect() as connection:
            count = connection.execute(text(
                "select count(*) from records where intake_record_id = :i and record_type = 'Clarification'"),
                {"i": intake_id}).scalar_one()
    for response in (detail, listed, clarified):
        assert response.status_code == 503
        assert response.json()["code"] == "interpreter_unavailable"
    assert count == 0


def test_a_fixture_request_keeps_its_normal_read_and_answer(env, migrated, owner_a) -> None:
    body = {"original_request": case("concrete-thesis")["intake"]["original_request"], "restrictions": [],
            "requested_job": "CREATE_STRATEGY", "input_class": "CONCRETE_THESIS"}
    with fixture_client(env) as fixture:
        created = fixture.post("/v1/research/requests", json=body, headers=owner_a)
    assert created.status_code == 201, created.text
    bundle = created.json()
    intake_id = bundle["intake"]["record_id"]
    with fixture_client(env) as fixture:
        detail = fixture.get(f"/v1/research/requests/{intake_id}", headers=owner_a)
        listed = fixture.get("/v1/research/requests", headers=owner_a)
    assert detail.status_code == 200 and detail.json()["intake"]["record_id"] == intake_id
    assert listed.status_code == 200
