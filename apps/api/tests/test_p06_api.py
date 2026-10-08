from __future__ import annotations

import copy
import json
import uuid

from edge_os_api import p02, p06
from flows import answer, publication_body, submit

VOLUME_RULE = ("Enter when current quote volume is above twice its prior 10-minute mean; exit when the 5-minute "
               "price return is below zero.")
UNSUPPORTED_RULE = ("Enter when the 14-period RSI is above 70; exit when the 5-minute price return is below zero.")


def test_user_can_review_save_and_reopen_a_price_volume_rule(client, owner_a, pg):
    first = submit(client, owner_a, VOLUME_RULE, restrictions=["no leverage"]).json()
    assert first["head"]["outcome"] == "NEEDS_CLARIFICATION"
    compiled = answer(client, owner_a, first, "adopt-suggested-settings", "adopt").json()
    assert compiled["head"]["outcome"] == "COMPILED"
    draft = compiled["drafts"][0]
    strategy = draft["content"]["source_syntax"]
    p06.validate_strategy(strategy)
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
    assert row["strategy_canonical"].encode() == p02.canonical_bytes(strategy)
    assert row["content_sha256"] == result["content_sha256"] == p02.sha256_hex(strategy)
    assert row["manifest_sha256"] == result["manifest_sha256"] == p06.manifest_sha256()


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
