from __future__ import annotations

import copy
import json
import uuid

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.strategies import compiler as strategy_compiler
from flows import answer, compiled_thesis, publication_body, submit

VOLUME_RULE = ("Enter when current quote volume is above twice its prior 10-minute mean; exit when the 5-minute "
               "price return is below zero.")
UNSUPPORTED_RULE = ("Enter when the 14-period RSI is above 70; exit when the 5-minute price return is below zero.")


def legacy_p02_bundle(client, owner, pg):
    bundle = compiled_thesis(client, owner)
    source = copy.deepcopy(bundle["drafts"][0]["content"])
    strategy = source["source_syntax"]
    strategy["schema_version"] = record_contract.CONTRACT["identity"]["strategy_schema"]
    strategy["semantic_manifest"] = dict(record_contract.MANIFEST)
    record_contract.validate_strategy(strategy)
    draft_id = str(uuid.uuid4())
    source["draft_id"] = draft_id
    owner_id = pg.psql("select owner_id from records where record_id = "
                       f"'{bundle['intake']['record_id']}'")
    source_json = json.dumps(source, separators=(",", ":")).replace("'", "''")
    pg.psql("insert into records (record_id, owner_id, record_type, schema_version, operation_id, created_at, "
            "content, intake_record_id, predecessor_record_id, interpretation_record_id) values "
            f"('{draft_id}', '{owner_id}', 'StrategyDraft', 'p02.strategy_draft/1', "
            f"'{bundle['intake']['operation_id']}', now(), '{source_json}'::jsonb, "
            f"'{bundle['intake']['record_id']}', null, '{bundle['head']['interpretation_revision_id']}')")
    return bundle, strategy, draft_id, owner_id


def seed_legacy_revision(pg, strategy, draft_id, owner_id, *, operation_id=None):
    revision_id, publication_id = str(uuid.uuid4()), str(uuid.uuid4())
    operation_id = operation_id or str(uuid.uuid4())
    canonical = record_contract.canonical_bytes(strategy).decode().replace("'", "''")
    pg.psql("insert into strategy_revisions (revision_id, owner_id, strategy_id, parent_revision_id, "
            "draft_record_id, publication_id, operation_id, content_sha256, manifest_sha256, strategy_canonical, "
            "created_at) values "
            f"('{revision_id}', '{owner_id}', '{strategy['strategy_id']}', null, '{draft_id}', "
            f"'{publication_id}', '{operation_id}', '{record_contract.sha256_hex(strategy)}', '{record_contract.manifest_sha256()}', "
            f"'{canonical}', now())")
    return revision_id, publication_id, operation_id


def test_user_can_review_save_and_reopen_a_price_volume_rule(client, owner_a, pg):
    first = submit(client, owner_a, VOLUME_RULE, restrictions=["no leverage"]).json()
    assert first["head"]["outcome"] == "NEEDS_CLARIFICATION"
    compiled = answer(client, owner_a, first, "adopt-suggested-settings", "adopt").json()
    assert compiled["head"]["outcome"] == "COMPILED"
    draft = compiled["drafts"][0]
    strategy = draft["content"]["source_syntax"]
    strategy_compiler.validate_strategy(strategy)
    assert strategy["entry"]["args"][0] == {"op": "relative_volume", "lookback_buckets": 2}
    assert strategy["data_inputs"] == ["price", "quote_volume"]
    assert strategy["warmup_buckets"] == 2
    assert strategy["execution_permission"] == {"state": "NOT_GRANTED", "mandate_ref": None}

    body = publication_body(compiled)
    response = client.post(f"/v1/strategies/{strategy['strategy_id']}/revisions", json=body, headers=owner_a)
    assert response.status_code == 201, response.text
    result = response.json()
    reopened = client.get(f"/v1/strategies/{strategy['strategy_id']}/revisions/{result['revision_id']}",
                          headers=owner_a)
    assert reopened.status_code == 200
    assert reopened.json()["strategy"] == strategy
    assert reopened.json()["stored_hash_matches_content"] is True
    row = json.loads(pg.psql("select coalesce(json_agg(r), '[]'::json) from strategy_revisions r where revision_id = "
                             f"'{result['revision_id']}'"))[0]
    assert row["strategy_canonical"].encode() == record_contract.canonical_bytes(strategy)
    assert row["content_sha256"] == result["content_sha256"] == record_contract.sha256_hex(strategy)
    assert row["manifest_sha256"] == result["manifest_sha256"] == strategy_compiler.manifest_sha256()


def test_mapped_only_rule_fixtures_do_not_appear_as_home_examples(client, owner_a):
    response = client.get("/v1/interpreter", headers=owner_a)
    assert response.status_code == 200
    visible = {sample["scenario_id"] for sample in response.json()["samples"]}
    assert not {"grouped-rule", "grouped-rule-right", "tiny-threshold", "tiny-threshold-positive"} & visible


def test_grouped_rules_keep_distinct_meaning_when_saved_and_reopened(client, owner_a, pg):
    grouped_left = ("Enter when (current quote volume is above twice its prior 10-minute mean or price is above 20) "
                    "and price is above 30. Exit when the 5-minute price return is below zero.")
    grouped_right = ("Enter when current quote volume is above twice its prior 10-minute mean or (price is above 20 "
                     "and price is above 30). Exit when the 5-minute price return is below zero.")
    a = {"op": "gt", "args": [{"op": "relative_volume", "lookback_buckets": 2},
                                  {"op": "constant", "value": "2", "unit": "DIMENSIONLESS"}]}
    b = {"op": "gt", "args": [{"op": "price"},
                                  {"op": "constant", "value": "20", "unit": "PRICE"}]}
    c = {"op": "gt", "args": [{"op": "price"},
                                  {"op": "constant", "value": "30", "unit": "PRICE"}]}

    bundle = compiled_thesis(client, owner_a, text=grouped_left, restrictions=["no leverage"])
    first_strategy = bundle["drafts"][0]["content"]["source_syntax"]
    assert first_strategy["entry"] == {"op": "and", "args": [{"op": "or", "args": [a, b]}, c]}
    first_body = publication_body(bundle)
    first = client.post(f"/v1/strategies/{first_strategy['strategy_id']}/revisions", json=first_body,
                        headers=owner_a)
    assert first.status_code == 201, first.text

    second_bundle = compiled_thesis(client, owner_a, text=grouped_right, restrictions=["no leverage"])
    second_strategy = second_bundle["drafts"][0]["content"]["source_syntax"]
    assert second_strategy["entry"] == {"op": "or", "args": [a, {"op": "and", "args": [b, c]}]}
    second_body = publication_body(second_bundle)
    second = client.post(f"/v1/strategies/{second_strategy['strategy_id']}/revisions", json=second_body,
                         headers=owner_a)
    assert second.status_code == 201, second.text

    reopened = []
    rows = []
    for strategy, publication, expected_tree in ((first_strategy, first.json(), first_strategy["entry"]),
                                                  (second_strategy, second.json(), second_strategy["entry"])):
        response = client.get(f"/v1/strategies/{strategy['strategy_id']}/revisions/"
                              f"{publication['revision_id']}", headers=owner_a)
        assert response.status_code == 200
        assert response.json()["strategy"]["entry"] == expected_tree
        assert response.json()["stored_hash_matches_content"] is True
        reopened.append(response.json()["strategy"]["entry"])
        rows.append(json.loads(pg.psql("select coalesce(json_agg(r), '[]'::json) from strategy_revisions r "
                                       f"where revision_id = '{publication['revision_id']}'"))[0])

    assert reopened[0] != reopened[1]
    assert rows[0]["content_sha256"] != rows[1]["content_sha256"]
    for row, publication in zip(rows, (first.json(), second.json()), strict=True):
        assert row["content_sha256"] == publication["content_sha256"]
        assert row["manifest_sha256"] == strategy_compiler.manifest_sha256()


def test_exact_tiny_return_threshold_survives_review_save_and_reopen(client, owner_a, pg):
    threshold = "-0." + ("0" * 399) + "1"
    original = (f"Enter when the 5-minute price return is above {threshold}. "
                "Exit when the 5-minute price return is below zero.")
    bundle = compiled_thesis(client, owner_a, text=original, restrictions=["no leverage"])
    strategy = bundle["drafts"][0]["content"]["source_syntax"]
    assert strategy["entry"]["args"][1]["value"] == threshold
    body = publication_body(bundle)
    result = client.post(f"/v1/strategies/{strategy['strategy_id']}/revisions", json=body, headers=owner_a)
    assert result.status_code == 201, result.text

    reopened = client.get(f"/v1/strategies/{strategy['strategy_id']}/revisions/{result.json()['revision_id']}",
                          headers=owner_a)
    assert reopened.status_code == 200
    assert reopened.json()["strategy"]["entry"] == strategy["entry"]
    assert reopened.json()["strategy"]["entry"]["args"][1]["value"] == threshold
    row = json.loads(pg.psql("select coalesce(json_agg(r), '[]'::json) from strategy_revisions r where revision_id = "
                             f"'{result.json()['revision_id']}'"))[0]
    assert row["strategy_canonical"].encode() == record_contract.canonical_bytes(strategy)
    assert row["content_sha256"] == result.json()["content_sha256"] == record_contract.sha256_hex(strategy)


def test_unsupported_indicator_names_the_entry_field(client, owner_a):
    first = submit(client, owner_a, UNSUPPORTED_RULE, restrictions=["no leverage"]).json()
    result = answer(client, owner_a, first, "adopt-suggested-settings", "adopt").json()

    assert result["head"]["outcome"] == "UNSUPPORTED"
    assert result["drafts"] == []
    finding = result["outcomes"][-1]["record"]["content"]["findings"][0]
    assert finding["code"] == "missing_capability"
    assert finding["path"] == "/field_evidence/entry"
    assert "rsi" in finding["detail"]


def test_fresh_and_saved_invalid_rule_have_the_same_compile_rejection(client, owner_a, pg):
    first = submit(client, owner_a, VOLUME_RULE, restrictions=["no leverage"]).json()
    compiled = answer(client, owner_a, first, "adopt-suggested-settings", "adopt").json()
    original = publication_body(compiled)
    invalid_strategy = copy.deepcopy(original["strategy"])
    invalid_strategy["entry"]["args"][0] = {"op": "future_price"}

    fresh = client.post(f"/v1/strategies/{invalid_strategy['strategy_id']}/revisions", headers=owner_a,
                        json={**original, "strategy": invalid_strategy})
    assert fresh.status_code == 422
    before = pg.psql("select count(*) from strategy_revisions")

    source = copy.deepcopy(compiled["drafts"][0]["content"])
    source["source_syntax"]["entry"]["args"][0] = {"op": "future_price"}
    draft_id = str(uuid.uuid4())
    source["draft_id"] = draft_id
    owner_id = pg.psql("select owner_id from records where record_id = "
                       f"'{compiled['intake']['record_id']}'")
    source_json = json.dumps(source, separators=(",", ":")).replace("'", "''")
    pg.psql("insert into records (record_id, owner_id, record_type, schema_version, operation_id, created_at, "
            "content, intake_record_id, predecessor_record_id, interpretation_record_id) values "
            f"('{draft_id}', '{owner_id}', 'StrategyDraft', 'p02.strategy_draft/1', "
            f"'{compiled['intake']['operation_id']}', now(), '{source_json}'::jsonb, "
            f"'{compiled['intake']['record_id']}', null, '{compiled['head']['interpretation_revision_id']}')")
    saved = client.post(f"/v1/strategies/{original['strategy']['strategy_id']}/revisions", headers=owner_a,
                        json={**original, "draft_id": draft_id})

    assert saved.status_code == fresh.status_code == 422
    assert saved.json()["findings"] == fresh.json()["findings"]
    assert saved.json()["findings"][0]["path"] == "/strategy/entry/args/0"
    assert pg.psql("select count(*) from strategy_revisions") == before


def test_valid_existing_p02_revision_remains_readable_without_rewriting_its_bytes(client, owner_a, pg):
    _, strategy, draft_id, owner_id = legacy_p02_bundle(client, owner_a, pg)
    revision_id, _, _ = seed_legacy_revision(pg, strategy, draft_id, owner_id)

    response = client.get(f"/v1/strategies/{strategy['strategy_id']}/revisions/{revision_id}", headers=owner_a)

    assert response.status_code == 200, response.text
    assert response.json()["strategy"] == strategy
    assert response.json()["stored_hash_matches_content"] is True
    assert response.json()["stored_manifest_hash_matches_content"] is True


def test_corrupt_stored_manifest_is_reported_without_claiming_verification(client, owner_a, pg):
    bundle = compiled_thesis(client, owner_a)
    strategy = bundle["drafts"][0]["content"]["source_syntax"]
    result = client.post(f"/v1/strategies/{strategy['strategy_id']}/revisions", headers=owner_a,
                         json=publication_body(bundle)).json()
    corrupt_revision_id, publication_id, operation_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    pg.psql("insert into strategy_revisions (revision_id, owner_id, strategy_id, parent_revision_id, "
            "draft_record_id, publication_id, operation_id, content_sha256, manifest_sha256, strategy_canonical, "
            "created_at) select "
            f"'{corrupt_revision_id}', owner_id, strategy_id, '{result['revision_id']}', draft_record_id, "
            f"'{publication_id}', '{operation_id}', content_sha256, '{'0' * 64}', strategy_canonical, now() "
            f"from strategy_revisions where revision_id = '{result['revision_id']}'")

    response = client.get(f"/v1/strategies/{strategy['strategy_id']}/revisions/{corrupt_revision_id}",
                          headers=owner_a)

    assert response.status_code == 200, response.text
    assert response.json()["stored_hash_matches_content"] is True
    assert response.json()["stored_manifest_hash_matches_content"] is False


def test_successful_existing_p02_publication_replay_remains_idempotent(client, owner_a, pg):
    bundle, strategy, draft_id, owner_id = legacy_p02_bundle(client, owner_a, pg)
    operation_id = str(uuid.uuid4())
    revision_id, publication_id, _ = seed_legacy_revision(
        pg, strategy, draft_id, owner_id, operation_id=operation_id)
    path = f"/v1/strategies/{strategy['strategy_id']}/revisions"
    idempotency_key = "legacy-replay-round-one"
    body = {"operation_id": operation_id, "idempotency_key": idempotency_key,
            "expected_parent_revision_id": None, "draft_id": draft_id, "strategy": strategy}
    fingerprint = record_contract.sha256_hex({"owner_id": owner_id, "method": "POST", "path": path,
        "expected_parent_revision_id": None, "draft_id": draft_id,
        "canonical_strategy_bytes": record_contract.canonical_bytes(strategy).decode()})
    result = {"operation_id": operation_id, "stage": "PUBLICATION", "outcome": "PUBLISHED",
              "code": "published", "findings": [], "retry": "SAFE_SAME_KEY",
              "publication_id": publication_id, "revision_id": revision_id,
              "content_sha256": record_contract.sha256_hex(strategy), "manifest_sha256": record_contract.manifest_sha256(),
              "created_at": "2026-01-01T00:00:00.000000Z"}
    record_contract.validate_record("PublicationResult", result)
    result_json = json.dumps(result, separators=(",", ":")).replace("'", "''")
    pg.psql("insert into idempotency_records (owner_id, method, path, idempotency_key, fingerprint, revision_id, "
            "response) values "
            f"('{owner_id}', 'POST', '{path}', '{idempotency_key}', '{fingerprint}', '{revision_id}', "
            f"'{result_json}'::jsonb)")
    before = pg.psql("select count(*) from strategy_revisions")

    replay = client.post(path, json=body, headers=owner_a)

    assert replay.status_code == 200, replay.text
    assert replay.headers["idempotent-replay"] == "true"
    assert replay.json() == result
    assert pg.psql("select count(*) from strategy_revisions") == before


def test_over_limit_derived_history_rejects_before_unresolved_evidence(client, owner_a, monkeypatch):
    from edge_os_api.research import service as service

    original_interpret = service.INTERPRETER.interpret

    def unresolved_with_deep_entry(intake):
        result = original_interpret(intake)
        result["evidence_readiness"] = "UNRESOLVED"
        rule: dict = {"op": "price"}
        for _ in range(2):
            rule = {"op": "lag", "value": rule, "buckets": 288}
        for item in result["field_evidence"]:
            if item["field_name"] == "entry":
                item["value"] = {"op": "gt", "args": [
                    rule, {"op": "constant", "value": "1", "unit": "PRICE"}]}
        return result

    monkeypatch.setattr(service.INTERPRETER, "interpret", unresolved_with_deep_entry)
    first = submit(client, owner_a).json()

    response = answer(client, owner_a, first, "adopt-suggested-settings", "adopt")

    assert response.status_code == 201, response.text
    assert response.json()["head"]["outcome"] == "INVALID_INPUT"
    finding = response.json()["outcomes"][-1]["record"]["content"]["findings"][0]
    assert finding["code"] == "history_limit"
    assert finding["path"] == "/field_evidence/entry"
