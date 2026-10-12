"""#58 Stage 2 F1: account views projected read-only from the connected financial rows.

Expected values come from the authored fixture constants used by the connected journey (sizing 100 quote units at an
authored price of 2 quote per base), checked against direct SQL, not from the projection code itself.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

import financial_flows as ff


@pytest.fixture
def journey(settings, tmp_path):
    with ff.fixture_client(settings, tmp_path / "effects.jsonl") as client:
        yield client


def projection(client, headers, agent_id=None):
    response = client.get("/v1/account-views/service", headers=headers,
                          params={} if agent_id is None else {"agent_id": agent_id})
    assert response.status_code == 200, response.text
    return response.json()


def test_projection_matches_saved_financial_rows_and_writes_nothing(journey, owner_a, pg):
    ff.ready_for_action(journey, owner_a, "proj-a")
    job = ff.run_job(journey, ff.schedule(journey, owner_a, "proj-a", "first").json())
    assert job["outcome"] == "SUBMITTED_CONFIRMED"
    counts_before = pg.psql("select count(*) from records")
    body = projection(journey, owner_a, "proj-a")
    assert pg.psql("select count(*) from records") == counts_before
    assert body["source"] == "SERVICE_PROJECTION" and body["ports"] == "FIXTURE"
    kinds = {record["content"]["record_kind"] for record in body["records"]}
    assert kinds == {"AGENT", "CAPITAL_FLOW", "POSITION", "ACTION", "MONITORING"}
    assert {record["content"]["evidence_class"] for record in body["records"]} == {"SERVICE_PROJECTION"}
    position = next(record["content"] for record in body["records"] if record["content"]["record_kind"] == "POSITION")
    sql = pg.psql("select inventory::text || '|' || cost_basis::text from admission_local.admission_positions "
                  f"where agent_id = 'proj-a'").strip()
    assert f"{position['quantity']['raw']}|{position['basis']['amount']['raw']}" == sql
    assert position["quantity"]["raw"] == ff.ENTRY_BASE_OUTPUT and position["position_state"] == "OPEN"
    assert position["estimated_unrealized_result"] == {"state": "UNKNOWN", "amount": None}
    assert position["mark"] == {"state": "UNKNOWN", "amount": None}
    # The position time is the saved action's receipt time, stable across reads (Review A N1), not the read time.
    again = next(record["content"] for record in projection(journey, owner_a, "proj-a")["records"]
                 if record["content"]["record_kind"] == "POSITION")
    assert again["updated_at"] == position["updated_at"]
    action_time = next(record["content"]["updated_at"] for record in body["records"]
                       if record["content"]["record_kind"] == "ACTION")
    assert position["updated_at"] == action_time
    action = next(record["content"] for record in body["records"] if record["content"]["record_kind"] == "ACTION")
    assert action["action_id"] == job["action_id"] and action["status"] == "CONFIRMED"
    flows = [record["content"] for record in body["records"] if record["content"]["record_kind"] == "CAPITAL_FLOW"]
    assert flows and all(flow["included_in_realized_result"] is False for flow in flows)
    assert all(flow["status"] == "CONFIRMED" and flow["reason"] is None for flow in flows)
    monitoring = next(record["content"] for record in body["records"]
                      if record["content"]["record_kind"] == "MONITORING")
    assert monitoring["evaluation_attempts"] == 1 and monitoring["evaluation_completions"] == 1


def test_unconfirmed_action_is_pending_reconciliation_not_success(journey, owner_a):
    ff.ready_for_action(journey, owner_a, "proj-fx-lost-ack")
    job = ff.run_job(journey, ff.schedule(journey, owner_a, "proj-fx-lost-ack", "first").json())
    assert job["outcome"] == "SUBMITTED_UNKNOWN", job
    body = projection(journey, owner_a, "proj-fx-lost-ack")
    monitoring = next(record["content"] for record in body["records"]
                      if record["content"]["record_kind"] == "MONITORING")
    assert monitoring["pending_reconciliation"] is True and monitoring["health"] == "ATTENTION"
    action = next(record["content"] for record in body["records"] if record["content"]["record_kind"] == "ACTION")
    assert action["status"] != "CONFIRMED"


def test_another_owner_sees_no_projection_and_unknown_agent_is_empty(journey, owner_a, owner_b):
    ff.ready_for_action(journey, owner_a, "proj-owner")
    assert projection(journey, owner_b, "proj-owner")["records"] == []
    assert projection(journey, owner_b)["records"] == []
    assert projection(journey, owner_a, "no-such-agent")["records"] == []


def test_declared_but_uncredited_deposit_is_not_shown_as_credited(journey, owner_a):
    ff.confirmed_agent(journey, owner_a, "proj-declared")
    assert journey.post("/v1/agents/proj-declared/funding/declaration", headers=owner_a).status_code == 200
    flow = journey.post("/v1/agents/proj-declared/funding/flows", headers=owner_a, json={
        "asset_class": "TRADING", "raw": ff.TRADING_DEPOSIT, "reference": "proj-declared-trading"})
    assert flow.status_code == 200, flow.text  # saved, but no reconciliation ran, so nothing is credited
    body = projection(journey, owner_a, "proj-declared")
    flows = [record["content"] for record in body["records"] if record["content"]["record_kind"] == "CAPITAL_FLOW"]
    assert len(flows) == 1 and flows[0]["status"] != "CONFIRMED"
    assert flows[0]["reason"] == "Declared amount; no credit has been observed for this flow."
    assert flows[0]["quantity"]["raw"] == ff.TRADING_DEPOSIT and flows[0]["included_in_realized_result"] is False
    assert not [record for record in body["records"] if record["content"]["record_kind"] == "POSITION"]


def test_unavailable_ports_label(settings, owner_a):
    from fastapi.testclient import TestClient

    from edge_os_api.main import create_app

    with TestClient(create_app(settings)) as client:
        body = projection(client, owner_a)
    assert body["ports"] == "UNAVAILABLE" and body["records"] == []


def test_agent_is_stopped_only_while_a_removal_denies_submission(journey, owner_a, pg):
    """Review B B3: a FAILED removal does not stop the agent (enforcement denies only DENYING_STATES)."""
    ff.confirmed_agent(journey, owner_a, "proj-removal")
    assert journey.post("/v1/agents/proj-removal/funding/declaration", headers=owner_a).status_code == 200
    requested = journey.post("/v1/agents/proj-removal/removal", headers=owner_a,
                             json={"request_key": "proj-removal-1", "reason": "owner removed the agent"})
    assert requested.status_code == 200, requested.text

    def agent():
        return next(record["content"] for record in projection(journey, owner_a, "proj-removal")["records"]
                    if record["content"]["record_kind"] == "AGENT")

    assert agent()["status"] == "STOPPED" and agent()["permission_state"] == "REMOVAL_REQUESTED"
    pg.psql("update revocation_local.removal_states set state = 'FAILED' where agent_id = 'proj-removal'")
    assert agent()["status"] == "CONFIRMED" and agent()["permission_state"] == "REMOVAL_FAILED"
