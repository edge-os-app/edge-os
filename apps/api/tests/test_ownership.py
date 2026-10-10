"""A15-A19, A22, A23: owner comes from the token only; another owner's IDs behave like missing ones."""

from __future__ import annotations

import uuid


from edge_os_api.records import contract_adapter as record_contract
from flows import HUNCH, answer, compiled_thesis, publication_body, publish, submit


def assert_not_found(response):
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found" and body["outcome"] == "NOT_FOUND"
    record_contract.validate_http_error(body)
    return body


def test_absent_and_foreign_records_give_identical_bodies(client, owner_a, owner_b):
    bundle = compiled_thesis(client, owner_a)
    intake_id = bundle["intake"]["record_id"]
    foreign = client.get(f"/v1/research/requests/{intake_id}", headers=owner_b)
    absent = client.get(f"/v1/research/requests/{uuid.uuid4()}", headers=owner_b)
    f, a = assert_not_found(foreign), assert_not_found(absent)
    for body in (f, a):
        body.pop("operation_id")
    assert f == a


def test_body_owner_id_is_rejected_at_any_depth_and_changes_nothing(client, owner_a, pg):
    before = pg.psql("select count(*) from records")
    other = str(uuid.uuid4())
    top = {"original_request": HUNCH, "restrictions": [], "requested_job": "CREATE_STRATEGY",
           "input_class": "LOOSE_INTUITION", "owner_id": other}
    nested = {**top, "declared_market": {"network": "MONAD", "base_asset": "0x" + "1" * 40,
                                        "quote_asset": "0x" + "2" * 40, "owner_id": other}}
    nested.pop("owner_id")
    for body in (top, nested):
        response = client.post("/v1/research/requests", json=body, headers=owner_a)
        assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert pg.psql("select count(*) from records") == before


def test_cross_owner_clarification_and_listing(client, owner_a, owner_b):
    bundle = submit(client, owner_a, HUNCH, input_class="LOOSE_INTUITION").json()
    attack = answer(client, owner_b, bundle, "choose-entry", "g3-1pct")
    assert_not_found(attack)
    assert len(client.get("/v1/research/requests", headers=owner_a).json()["requests"]) == 1
    assert client.get("/v1/research/requests", headers=owner_b).json()["requests"] == []
    # A's request is unchanged by B's attempt
    reread = client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a).json()
    assert len(reread["interpretations"]) == 1 and reread["clarifications"] == []


def test_cross_owner_publication_revision_and_operation(client, owner_a, owner_b, pg):
    bundle = compiled_thesis(client, owner_a)
    response, body = publish(client, owner_a, bundle)
    assert response.status_code == 201
    result = response.json()
    strategy_id = body["strategy"]["strategy_id"]
    assert_not_found(client.get(f"/v1/strategies/{strategy_id}/revisions/{result['revision_id']}", headers=owner_b))
    assert_not_found(client.get(f"/v1/operations/{result['operation_id']}", headers=owner_b))
    # B cannot publish A's draft: same 404 as a random draft id
    attack = client.post(f"/v1/strategies/{strategy_id}/revisions", headers=owner_b, json=body)
    assert_not_found(attack)
    random_draft = client.post(f"/v1/strategies/{strategy_id}/revisions", headers=owner_b,
                               json={**body, "draft_id": str(uuid.uuid4())})
    assert_not_found(random_draft)
    assert pg.psql(f"select count(*) from strategy_revisions where strategy_id = '{strategy_id}'") == "1"


def test_foreign_and_random_parent_give_the_same_conflict(client, owner_a, owner_b):
    a_bundle = compiled_thesis(client, owner_a)
    a_result = publish(client, owner_a, a_bundle)[0].json()
    b_bundle = compiled_thesis(client, owner_b)
    outcomes = []
    for parent in (a_result["revision_id"], str(uuid.uuid4())):
        body = publication_body(b_bundle, parent=parent)
        response = client.post(f"/v1/strategies/{body['strategy']['strategy_id']}/revisions", json=body,
                               headers=owner_b)
        assert response.status_code == 409 and response.json()["code"] == "parent_revision_conflict"
        payload = response.json()
        payload.pop("operation_id")
        outcomes.append(payload)
    assert outcomes[0] == outcomes[1]


def test_same_idempotency_key_and_operation_are_independent_per_owner(client, owner_a, owner_b):
    shared_key, shared_op = "shared-key-1", str(uuid.uuid4())
    results = []
    for headers in (owner_a, owner_b):
        bundle = compiled_thesis(client, headers)
        response, _ = publish(client, headers, bundle, key=shared_key, operation_id=shared_op)
        assert response.status_code == 201, response.text
        results.append(response.json())
    assert results[0]["revision_id"] != results[1]["revision_id"]
