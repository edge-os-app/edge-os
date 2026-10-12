"""#58 RG05 market adoption: a QUALIFIED recorded-history market becomes a NEW draft before publication.

Sources are SYNTHETIC recorded responses. Earlier drafts and published revisions never change.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from conftest import run_threads
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.records import contract_adapter as record_contract
from flows import compiled_thesis, publish
from research_flows import QUOTE_UNIT, adoption_body, reported_dataset


@pytest.fixture(scope="module")
def research(env, migrated):
    settings = load_settings({**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded",
                              "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "200",
                              "EDGE_OS_RESEARCH_BUDGET_COMPUTE_SECONDS": "9000"})
    with TestClient(create_app(settings)) as client:
        yield client


def finding(response) -> str:
    return response.json()["findings"][0]["code"]


def path(bundle) -> str:
    return f"/v1/research/requests/{bundle['intake']['record_id']}/market-adoptions"


def head_draft(bundle):
    return next(d for d in bundle["drafts"] if d["record_id"] == bundle["head"]["draft_id"])


def test_adoption_creates_a_new_interpretation_and_draft_and_keeps_the_old_ones(research, owner_a):
    dataset_id = reported_dataset(research, owner_a)
    bundle = compiled_thesis(research, owner_a)
    before = copy.deepcopy(bundle)
    response = research.post(path(bundle), headers=owner_a, json=adoption_body(bundle, dataset_id))
    assert response.status_code == 201, response.text
    adopted = response.json()
    after = adopted["bundle"]
    assert len(after["interpretations"]) == len(before["interpretations"]) + 1
    assert after["interpretations"][:-1] == before["interpretations"] and after["drafts"][:-1] == before["drafts"]
    draft = head_draft(after)["content"]
    assert draft["draft_id"] == adopted["adoption"]["draft_id"] and draft["base_revision_id"] is None
    strategy = draft["source_syntax"]
    dataset = research.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json()["content"]
    assert strategy["market"] == dataset["strategy_market"]
    assert strategy["market"]["execution_route"]["qualification"] == "UNQUALIFIED"
    assert strategy["sizing"] == {"kind": "FIXED_QUOTE_AMOUNT", "amount": "50", "unit": QUOTE_UNIT}
    assert strategy["risk_limits"]["max_quote_notional"] == "50"
    old = head_draft(before)["content"]["source_syntax"]
    assert {key: value for key, value in strategy.items() if key not in {"market", "sizing", "risk_limits"}} == {
        key: value for key, value in old.items() if key not in {"market", "sizing", "risk_limits"}}
    evidence = {item["field_name"]: item for item in after["interpretations"][-1]["content"]["field_evidence"]}
    assert evidence["market"]["source_ref"] == f"history-dataset:{dataset_id}"
    assert evidence["sizing"]["origin"] == "USER_CONFIRMED" and "adoption" not in evidence["sizing"]
    clarification = after["clarifications"][-1]["content"]
    assert clarification["question_id"] == "adopt-recorded-market"
    assert set(clarification["changed_fields"]) == {"market", "risk_limits", "sizing"}
    assert adopted["adoption"]["declaration_id"] == dataset["declaration_id"]
    record_contract.validate_record_bundle(
        [after["intake"], *after["interpretations"], *after["clarifications"],
         *[item["record"] for item in after["outcomes"]], *after["drafts"]])


def test_same_key_replays_after_a_lost_reply_and_other_body_conflicts(research, owner_a):
    dataset_id = reported_dataset(research, owner_a)
    bundle = compiled_thesis(research, owner_a)
    body = adoption_body(bundle, dataset_id)
    first = research.post(path(bundle), headers=owner_a, json=body)
    with TestClient(create_app(research.app.state.settings)) as restarted:
        again = restarted.post(path(bundle), headers=owner_a, json=body)
    assert first.status_code == 201 and again.status_code == 200 and again.json()["replayed"] is True
    assert again.json()["adoption"] == first.json()["adoption"]
    assert len(again.json()["bundle"]["drafts"]) == len(first.json()["bundle"]["drafts"])
    changed = {**body, "sizing_amount": "51"}
    assert research.post(path(bundle), headers=owner_a, json=changed).json()["code"] == "idempotency_key_reused"


def test_concurrent_same_key_adopts_once(research, owner_a):
    dataset_id = reported_dataset(research, owner_a)
    bundle = compiled_thesis(research, owner_a)
    body = adoption_body(bundle, dataset_id)
    results = run_threads(3, lambda _: research.post(path(bundle), headers=owner_a, json=body))
    assert sorted(result.status_code for result in results) == [200, 200, 201]
    assert len({result.json()["adoption"]["draft_id"] for result in results}) == 1


def test_publication_requires_the_exact_new_draft_and_parent(research, owner_a):
    dataset_id = reported_dataset(research, owner_a)
    bundle = compiled_thesis(research, owner_a)
    published, _ = publish(research, owner_a, bundle)
    assert published.status_code == 201
    parent = published.json()["revision_id"]
    stale = research.post(path(bundle), headers=owner_a, json=adoption_body(bundle, dataset_id, parent=None))
    assert stale.status_code == 409 and stale.json()["code"] == "parent_revision_conflict"
    adopted = research.post(path(bundle), headers=owner_a, json=adoption_body(bundle, dataset_id, parent=parent))
    assert adopted.status_code == 201, adopted.text
    after = adopted.json()["bundle"]
    tampered = copy.deepcopy(head_draft(after)["content"]["source_syntax"])
    tampered["sizing"]["amount"] = "40"
    wrong, _ = publish(research, owner_a, after, parent=parent, strategy=tampered)
    assert wrong.status_code == 422 and finding(wrong) == "strategy_differs_from_draft"
    second, _ = publish(research, owner_a, after, parent=parent)
    assert second.status_code == 201, second.text
    first_revision = research.get(f"/v1/strategies/{bundle['head']['strategy_id']}/revisions/{parent}",
                                  headers=owner_a).json()
    assert first_revision["stored_hash_matches_content"] is True


@pytest.mark.parametrize("source_id,code", [("recorded-syn-provider-failure/1", "dataset_not_qualified"),
                                            ("recorded-syn-uncorroborated/1", "dataset_not_qualified")])
def test_limited_or_unresolved_dataset_cannot_supply_a_market(research, owner_a, source_id, code):
    dataset_id = reported_dataset(research, owner_a, source_id=source_id)
    bundle = compiled_thesis(research, owner_a)
    response = research.post(path(bundle), headers=owner_a, json=adoption_body(bundle, dataset_id))
    assert response.status_code == 409 and response.json()["code"] == code


def test_foreign_missing_tampered_and_stale_inputs_are_refused(research, owner_a, owner_b):
    dataset_id = reported_dataset(research, owner_a)
    foreign = compiled_thesis(research, owner_b)
    assert research.post(path(foreign), headers=owner_b, json=adoption_body(foreign, dataset_id)).status_code == 404
    bundle = compiled_thesis(research, owner_a)
    assert research.post(path(bundle), headers=owner_b, json=adoption_body(bundle, dataset_id)).status_code == 404
    missing = adoption_body(bundle, "00000000-0000-4000-8000-000000000000")
    assert research.post(path(bundle), headers=owner_a, json=missing).status_code == 404
    stale = adoption_body(bundle, dataset_id)
    stale["expected_interpretation_revision_id"] = "00000000-0000-4000-8000-000000000000"
    assert research.post(path(bundle), headers=owner_a, json=stale).json()["code"] == "parent_revision_conflict"
    wrong_unit = adoption_body(bundle, dataset_id, quote_unit="QUOTE:0x" + "22" * 20)
    assert finding(research.post(path(bundle), headers=owner_a, json=wrong_unit)) == "quote_unit_mismatch"
    no_adoption = {**adoption_body(bundle, dataset_id), "adoption": "LATER"}
    assert research.post(path(bundle), headers=owner_a, json=no_adoption).status_code == 422
    client_binding = {**adoption_body(bundle, dataset_id), "market": {"qualification": "QUALIFIED"}}
    assert research.post(path(bundle), headers=owner_a, json=client_binding).status_code == 422
    tampered_id = reported_dataset(research, owner_a)
    with research.app.state.session_factory() as session:
        session.execute(text("ALTER TABLE research_local.history_datasets DISABLE TRIGGER history_datasets_immutable"))
        session.execute(text("UPDATE research_local.history_datasets SET content = jsonb_set(content, "
                             "'{market_binding,pool_address}', '\"0x0000000000000000000000000000000000000001\"') "
                             "WHERE dataset_id = :id"), {"id": tampered_id})
        session.execute(text("ALTER TABLE research_local.history_datasets ENABLE TRIGGER history_datasets_immutable"))
        session.commit()
    tampered = research.post(path(bundle), headers=owner_a, json=adoption_body(bundle, tampered_id))
    assert tampered.status_code == 409 and tampered.json()["code"] == "dataset_hash_mismatch"
    unchanged = research.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=owner_a).json()
    assert unchanged["drafts"] == bundle["drafts"]


def test_rule_in_another_quote_unit_must_be_restated(research, owner_a, monkeypatch):
    from edge_os_api.research import market_adoption

    assert market_adoption._quote_units({"op": "gt", "args": [{"op": "quote_volume"}, {
        "op": "constant", "value": "4", "unit": "QUOTE:0x" + "22" * 20}]}) == {"QUOTE:0x" + "22" * 20}
    dataset_id = reported_dataset(research, owner_a)
    bundle = compiled_thesis(research, owner_a)
    original = market_adoption._quote_units
    monkeypatch.setattr(market_adoption, "_quote_units", lambda node: original(node) | {"QUOTE:0x" + "22" * 20})
    response = research.post(path(bundle), headers=owner_a, json=adoption_body(bundle, dataset_id))
    assert response.status_code == 422 and finding(response) == "unit_mismatch"


def test_investigation_request_cannot_adopt_a_strategy_market(research, owner_a):
    from research_flows import investigation_request

    dataset_id = reported_dataset(research, owner_a)
    bundle = investigation_request(research, owner_a)
    body = adoption_body(bundle, dataset_id)
    response = research.post(path(bundle), headers=owner_a, json=body)
    assert response.status_code == 422 and finding(response) == "strategy_job_required"
