"""Request -> clarification -> review -> publication -> reopen, with direct database observation."""

from __future__ import annotations

import json

import pytest

from edge_os_api import p02
from flows import (HUNCH, LAUNCH_AGE, MARKET, NO_THESIS, RESTRICTIONS, THESIS, answer, compiled_thesis, publish,
                   submit)

EXACT = "  Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. Spot only.\n"


def rows(pg, sql):
    return pg.psql(f"select coalesce(json_agg(t), '[]'::json) from ({sql}) t")


def test_thesis_end_to_end_with_database_observation(client, owner_a, pg):
    first = submit(client, owner_a, THESIS)
    assert first.status_code == 201
    bundle = first.json()
    assert bundle["interpreter"]["kind"] == "FIXTURE"
    assert bundle["head"]["outcome"] == "NEEDS_CLARIFICATION"
    questions = bundle["head"]["questions"]
    assert [q["kind"] for q in questions] == ["ADOPT"]
    items = {i["field_name"] for i in questions[0]["items"]}
    assert items >= {"market", "sizing", "cost_assumptions"}
    assert not items & {"entry", "exit", "restrictions"}  # the user's own rules are never re-asked
    # stated meaning is kept as stated; nothing guessed
    interp = bundle["interpretations"][0]["content"]
    entry = next(i for i in interp["field_evidence"] if i["field_name"] == "entry")
    assert entry["origin"] == "USER_STATED" and entry["state"] == "KNOWN"
    market = next(i for i in interp["field_evidence"] if i["field_name"] == "market")
    assert market["origin"] == "AGENT_PROPOSED" and market["adoption"] == "PENDING"

    adopted = answer(client, owner_a, bundle, "adopt-suggested-settings", "adopt")
    assert adopted.status_code == 201
    done = adopted.json()
    assert done["head"]["outcome"] == "COMPILED"
    assert len(done["clarifications"]) == 1
    assert done["clarifications"][0]["content"]["preserved_restrictions"] == RESTRICTIONS

    response, body = publish(client, owner_a, done)
    assert response.status_code == 201, response.text
    result = response.json()
    p02.validate_record("PublicationResult", result)
    assert result["outcome"] == "PUBLISHED"

    # direct database observations
    intake_id = done["intake"]["record_id"]
    intake_row = json.loads(rows(pg, f"select content from records where record_id = '{intake_id}'"))[0]["content"]
    assert intake_row["original_request"] == THESIS
    assert intake_row["restrictions"] == RESTRICTIONS
    revision = json.loads(rows(pg, f"select * from strategy_revisions where revision_id = '{result['revision_id']}'"))[0]
    assert revision["content_sha256"] == result["content_sha256"]
    assert revision["parent_revision_id"] is None
    assert p02.sha256_hex(json.loads(revision["strategy_canonical"])) == revision["content_sha256"]
    assert revision["strategy_canonical"].encode() == p02.canonical_bytes(body["strategy"])
    types = json.loads(rows(pg, f"select record_type from records where record_id = '{intake_id}' or "
                                f"intake_record_id = '{intake_id}' order by seq"))
    assert [t["record_type"] for t in types] == ["IntakeRequest", "PromptInterpretation", "Outcome",
                                                "PromptInterpretation", "Clarification", "Outcome", "StrategyDraft",
                                                "PublicationResult"]

    # reopen through the API
    reopened = client.get(f"/v1/research/requests/{intake_id}", headers=owner_a).json()
    assert reopened["revisions"][0]["revision_id"] == result["revision_id"]
    fetched = client.get(f"/v1/strategies/{body['strategy']['strategy_id']}/revisions/{result['revision_id']}",
                         headers=owner_a).json()
    assert fetched["strategy"] == body["strategy"] and fetched["stored_hash_matches_content"] is True
    assert fetched["strategy"]["execution_permission"] == {"state": "NOT_GRANTED", "mandate_ref": None}


def test_exact_original_words_are_preserved(client, owner_a, pg):
    # an unscripted text is still saved byte for byte, and the outcome is a system outcome
    response = submit(client, owner_a, EXACT, restrictions=["no leverage", "no  leverage ", "ünïcode 🙂"])
    assert response.status_code == 201
    bundle = response.json()
    intake_id = bundle["intake"]["record_id"]
    stored = json.loads(rows(pg, f"select content from records where record_id = '{intake_id}'"))[0]["content"]
    assert stored["original_request"] == EXACT
    assert stored["restrictions"] == ["no leverage", "no  leverage ", "ünïcode 🙂"]


def test_hunch_needs_one_choice_and_one_adoption_in_any_order(client, owner_a):
    first = submit(client, owner_a, HUNCH, job="CREATE_STRATEGY", input_class="LOOSE_INTUITION").json()
    kinds = {q["kind"]: q for q in first["head"]["questions"]}
    assert set(kinds) == {"CHOICE", "ADOPT"}
    entry_field = next(i for i in first["interpretations"][0]["content"]["field_evidence"] if i["field_name"] == "entry")
    assert entry_field["state"] == "MISSING" and "value" not in entry_field
    assert "entry" not in {i["field_name"] for i in kinds["ADOPT"]["items"]}
    # the proposed settings are adopted first; the user's own meaning is still required
    second = answer(client, owner_a, first, "adopt-suggested-settings", "adopt").json()
    assert second["head"]["outcome"] == "NEEDS_CLARIFICATION"
    assert [q["kind"] for q in second["head"]["questions"]] == ["CHOICE"]
    third = answer(client, owner_a, second, "choose-entry", "g3-2pct")
    assert third.status_code == 201
    done = third.json()
    assert done["head"]["outcome"] == "COMPILED"
    strategy = done["drafts"][0]["content"]["source_syntax"]
    assert strategy["entry"]["args"][1]["value"] == "0.02"
    assert [c["content"]["question_id"] for c in done["clarifications"]] == ["adopt-suggested-settings", "choose-entry"]
    entry = next(i for i in done["interpretations"][-1]["content"]["field_evidence"] if i["field_name"] == "entry")
    assert entry["origin"] == "USER_CONFIRMED"
    p02.validate_record_bundle([done["intake"], *done["interpretations"], *done["clarifications"],
                                *[o["record"] for o in done["outcomes"]], *done["drafts"]])


def test_no_thesis_stays_investigation_and_unresolved(client, owner_a, pg):
    response = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT", input_class="BOUNDED_NO_THESIS",
                      restrictions=[], declared_market=MARKET)
    assert response.status_code == 201
    bundle = response.json()
    assert bundle["head"]["outcome"] == "UNRESOLVED"
    assert bundle["intake"]["content"]["requested_job"] == "INVESTIGATE_EFFECT"
    assert bundle["drafts"] == [] and bundle["head"]["draft_id"] is None
    outcome = bundle["outcomes"][0]["record"]["content"]
    assert outcome["findings"][0]["code"] == "missing_dependency"
    assert outcome["intake_record_id"] == bundle["intake"]["record_id"]
    count = pg.psql("select count(*) from records where record_type = 'StrategyDraft' and "
                    f"intake_record_id = '{bundle['intake']['record_id']}'")
    assert count == "0"


def test_no_thesis_without_market_asks_which_market(client, owner_a):
    bundle = submit(client, owner_a, NO_THESIS, job="INVESTIGATE_EFFECT", input_class="BOUNDED_NO_THESIS",
                    restrictions=[]).json()
    assert bundle["head"]["outcome"] == "NEEDS_CLARIFICATION"
    assert bundle["head"]["questions"][0]["field_name"] == "market"
    done = answer(client, owner_a, bundle, "choose-market", "fixture-market").json()
    assert done["head"]["outcome"] == "UNRESOLVED"


def test_unsupported_meaning_is_preserved_and_blocks_compilation(client, owner_a):
    bundle = submit(client, owner_a, LAUNCH_AGE, input_class="LOOSE_INTUITION", restrictions=["no leverage"]).json()
    assert bundle["head"]["outcome"] == "UNSUPPORTED"
    assert bundle["drafts"] == []
    outcome = bundle["outcomes"][0]["record"]["content"]
    assert outcome["findings"][0]["code"] == "missing_capability"
    assert bundle["intake"]["content"]["original_request"] == LAUNCH_AGE


def test_unsupported_restriction_blocks_before_any_question(client, owner_a):
    bundle = submit(client, owner_a, HUNCH, input_class="LOOSE_INTUITION",
                    restrictions=["no leverage", "only tokens younger than 24 hours"]).json()
    assert bundle["head"]["outcome"] == "UNSUPPORTED"
    assert bundle["head"]["questions"] == []
    assert bundle["interpretations"][0]["content"]["preserved_restrictions"] == [
        "no leverage", "only tokens younger than 24 hours"]


@pytest.mark.parametrize("job", ["SIMULATE", "OBSERVE_FORWARD", "REQUEST_LIVE"])
def test_other_jobs_are_kept_and_unsupported(client, owner_a, job):
    bundle = submit(client, owner_a, THESIS, job=job).json()
    assert bundle["head"]["outcome"] in {"UNSUPPORTED", "INVALID_INPUT"}
    assert bundle["intake"]["content"]["requested_job"] == job


def test_unscripted_text_is_a_system_outcome_not_unsupported(client, owner_a):
    bundle = submit(client, owner_a, "Something nobody scripted.").json()
    assert bundle["head"]["outcome"] == "INVALID_INPUT"
    assert bundle["outcomes"][0]["record"]["content"]["findings"][0]["code"] == "interpreter_no_scripted_response"
    assert bundle["intake"]["content"]["original_request"] == "Something nobody scripted."


def test_no_guessed_field_and_no_dropped_restriction(client, owner_a):
    first = submit(client, owner_a, HUNCH, input_class="LOOSE_INTUITION").json()
    second = answer(client, owner_a, first, "adopt-suggested-settings", "adopt").json()
    third = answer(client, owner_a, second, "choose-entry", "g6-3pct").json()
    for interp in third["interpretations"]:
        assert interp["content"]["preserved_restrictions"] == RESTRICTIONS
        bound = next(i for i in interp["content"]["field_evidence"] if i["field_name"] == "restrictions")
        assert bound["value"] == RESTRICTIONS
    # the compiled strategy honours the saved restrictions
    strategy = third["drafts"][0]["content"]["source_syntax"]
    assert strategy["domain"] == "SPOT" and strategy["risk_limits"]["max_open_positions"] == 1


def test_clarification_rejects_stale_wrong_and_replayed_answers(client, owner_a):
    first = submit(client, owner_a, HUNCH, input_class="LOOSE_INTUITION").json()
    intake_id = first["intake"]["record_id"]
    path = f"/v1/research/requests/{intake_id}/clarifications"
    stale = {"previous_revision_id": "00000000-0000-4000-8000-000000000000", "question_id": "choose-entry",
             "choice_id": "g3-1pct"}
    assert client.post(path, json=stale, headers=owner_a).status_code == 409
    current = first["head"]["interpretation_revision_id"]
    for question, choice in [("choose-entry", "not-a-choice"), ("no-such", "x"), ("adopt-suggested-settings", "other")]:
        bad = client.post(path, headers=owner_a, json={"previous_revision_id": current, "question_id": question,
                                                       "choice_id": choice})
        assert bad.status_code == 422 and bad.json()["code"] == "validation_error"
    ok = client.post(path, headers=owner_a, json={"previous_revision_id": current, "question_id": "choose-entry",
                                                  "choice_id": "g3-1pct"})
    assert ok.status_code == 201
    replay = client.post(path, headers=owner_a, json={"previous_revision_id": current, "question_id": "choose-entry",
                                                      "choice_id": "g3-1pct"})
    assert replay.status_code == 409 and replay.json()["code"] == "parent_revision_conflict"


def test_list_and_reopen_summaries(client, owner_a):
    compiled_thesis(client, owner_a)
    listed = client.get("/v1/research/requests", headers=owner_a).json()["requests"]
    assert len(listed) == 1 and listed[0]["outcome"] == "COMPILED" and listed[0]["original_request"] == THESIS
