"""Atomic immutable publication, idempotency, parent rules and database invariants."""

from __future__ import annotations

import copy
import uuid

import pytest

from edge_os_api import p02
from flows import compiled_thesis, publication_body, publish


def test_replay_returns_the_same_identity_without_new_rows(client, owner_a, pg):
    bundle = compiled_thesis(client, owner_a)
    response, body = publish(client, owner_a, bundle, key="retry-1")
    assert response.status_code == 201
    first = response.json()
    strategy_id = body["strategy"]["strategy_id"]
    for _ in range(3):
        again = client.post(f"/v1/strategies/{strategy_id}/revisions", json=body, headers=owner_a)
        assert again.status_code == 200
        assert again.headers["idempotent-replay"] == "true"
        assert again.json() == first
    assert pg.psql(f"select count(*) from strategy_revisions where strategy_id = '{strategy_id}'") == "1"
    # a lost acknowledgement can also be recovered by operation
    recovered = client.get(f"/v1/operations/{first['operation_id']}", headers=owner_a)
    assert recovered.status_code == 200 and recovered.json()["revision_id"] == first["revision_id"]


def test_changed_payload_with_same_key_conflicts(client, owner_a, pg):
    bundle = compiled_thesis(client, owner_a)
    response, body = publish(client, owner_a, bundle, key="reuse-1")
    assert response.status_code == 201
    changed = copy.deepcopy(body)
    changed["strategy"]["entry"]["args"][1]["value"] = "0.02"  # valid, but not the adopted meaning
    conflict = client.post(f"/v1/strategies/{body['strategy']['strategy_id']}/revisions", json=changed, headers=owner_a)
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_key_reused"
    p02.validate_http_error(conflict.json())
    assert conflict.json()["retry"] == "NOT_RETRYABLE"


def test_strategy_that_differs_from_adopted_meaning_is_rejected_without_writing(client, owner_a, pg):
    bundle = compiled_thesis(client, owner_a)
    body = publication_body(bundle)
    body["strategy"]["entry"]["args"][1]["value"] = "0.02"
    before = pg.psql("select count(*) from strategy_revisions")
    response = client.post(f"/v1/strategies/{body['strategy']['strategy_id']}/revisions", json=body, headers=owner_a)
    assert response.status_code == 422 and response.json()["findings"][0]["code"] == "strategy_differs_from_draft"
    assert pg.psql("select count(*) from strategy_revisions") == before


@pytest.mark.parametrize("mutate", [
    lambda s: s.__setitem__("domain", "PERP"),
    lambda s: s.__setitem__("execution_permission", {"state": "GRANTED", "mandate_ref": "x"}),
    lambda s: s.__setitem__("owner_id", "x"),
    lambda s: s["sizing"].__setitem__("amount", "100.0"),
    lambda s: s.__setitem__("warmup_buckets", 999),
])
def test_invalid_strategy_is_a_validation_error(client, owner_a, mutate):
    bundle = compiled_thesis(client, owner_a)
    body = publication_body(bundle)
    mutate(body["strategy"])
    response = client.post(f"/v1/strategies/{body['strategy']['strategy_id']}/revisions", json=body, headers=owner_a)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"


def test_path_and_body_strategy_ids_must_match(client, owner_a):
    bundle = compiled_thesis(client, owner_a)
    body = publication_body(bundle)
    response = client.post("/v1/strategies/another-strategy/revisions", json=body, headers=owner_a)
    assert response.status_code == 422


def test_float_and_duplicate_keys_are_rejected(client, owner_a):
    bundle = compiled_thesis(client, owner_a)
    body = publication_body(bundle)
    sid = body["strategy"]["strategy_id"]
    raw = client.post(f"/v1/strategies/{sid}/revisions", headers={**owner_a, "content-type": "application/json"},
                      content='{"operation_id": "' + body["operation_id"] + '", "operation_id": "x"}')
    assert raw.status_code == 422
    floaty = client.post(f"/v1/strategies/{sid}/revisions", headers={**owner_a, "content-type": "application/json"},
                         content='{"x": 1.5}')
    assert floaty.status_code == 422


def test_second_null_parent_loses_the_root_slot(client, owner_a, pg):
    bundle = compiled_thesis(client, owner_a)
    first, body = publish(client, owner_a, bundle)
    assert first.status_code == 201
    second = client.post(f"/v1/strategies/{body['strategy']['strategy_id']}/revisions", headers=owner_a,
                         json={**body, "idempotency_key": "other-key", "operation_id": str(uuid.uuid4())})
    assert second.status_code == 409 and second.json()["code"] == "parent_revision_conflict"
    sid = body["strategy"]["strategy_id"]
    assert pg.psql(f"select count(*) from strategy_revisions where strategy_id = '{sid}'") == "1"
    assert pg.psql("select count(*) from idempotency_records where idempotency_key = 'other-key'") == "0"


def test_reused_operation_id_with_new_key_conflicts(client, owner_a):
    bundle = compiled_thesis(client, owner_a)
    first, body = publish(client, owner_a, bundle)
    other_bundle = compiled_thesis(client, owner_a)
    reused = publication_body(other_bundle, operation_id=body["operation_id"])
    response = client.post(f"/v1/strategies/{reused['strategy']['strategy_id']}/revisions", json=reused, headers=owner_a)
    assert response.status_code == 409 and response.json()["code"] == "idempotency_key_reused"


def test_records_are_append_only_at_the_database(pg, client, owner_a):
    bundle = compiled_thesis(client, owner_a)
    response, body = publish(client, owner_a, bundle)
    rid = response.json()["revision_id"]
    for sql in (f"update strategy_revisions set strategy_id = 'x' where revision_id = '{rid}'",
                f"delete from strategy_revisions where revision_id = '{rid}'",
                f"update records set content = '{{}}' where record_id = '{bundle['intake']['record_id']}'",
                f"delete from records where record_id = '{bundle['intake']['record_id']}'",
                "delete from idempotency_records", "update idempotency_records set fingerprint = 'x'"):
        with pytest.raises(Exception) as caught:
            pg.psql(sql)
        assert "immutable" in str(getattr(caught.value, "stderr", caught.value))


def test_database_rejects_cross_owner_parent_reference(pg, client, owner_a, owner_b):
    a = compiled_thesis(client, owner_a)
    b = compiled_thesis(client, owner_b)
    a_rev = publish(client, owner_a, a)[0].json()["revision_id"]
    b_body = publication_body(b)
    # a direct insert that names A's revision as the parent of B's strategy must fail at the database
    b_draft = b["head"]["draft_id"]
    owner_b_id = pg.psql(f"select owner_id from records where record_id = '{b_draft}'")
    sql = ("insert into strategy_revisions (revision_id, owner_id, strategy_id, parent_revision_id, draft_record_id, "
           "publication_id, operation_id, content_sha256, manifest_sha256, strategy_canonical, created_at) values "
           f"(gen_random_uuid(), '{owner_b_id}', '{b_body['strategy']['strategy_id']}', '{a_rev}', '{b_draft}', "
           f"gen_random_uuid(), gen_random_uuid(), repeat('a',64), repeat('b',64), '{{}}', now())")
    with pytest.raises(Exception) as caught:
        pg.psql(sql)
    assert "fk_revision_parent" in str(getattr(caught.value, "stderr", caught.value))


def test_second_revision_with_valid_parent_succeeds_and_siblings_are_allowed(client, owner_a, pg):
    # second revisions need a draft whose base revision is the parent; the first slice only creates root drafts,
    # so exercise the database rule directly: two children of one parent are both accepted.
    bundle = compiled_thesis(client, owner_a)
    response, body = publish(client, owner_a, bundle)
    parent = response.json()["revision_id"]
    sid = body["strategy"]["strategy_id"]
    owner = pg.psql(f"select owner_id from strategy_revisions where revision_id = '{parent}'")
    draft = bundle["head"]["draft_id"]
    for _ in range(2):
        pg.psql("insert into strategy_revisions (revision_id, owner_id, strategy_id, parent_revision_id, "
                "draft_record_id, publication_id, operation_id, content_sha256, manifest_sha256, strategy_canonical, "
                f"created_at) values (gen_random_uuid(), '{owner}', '{sid}', '{parent}', '{draft}', gen_random_uuid(), "
                "gen_random_uuid(), repeat('a',64), repeat('b',64), '{}', now())")
    assert pg.psql(f"select count(*) from strategy_revisions where parent_revision_id = '{parent}'") == "2"
