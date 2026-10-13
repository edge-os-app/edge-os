"""P31 LOCAL read-only agent health snapshot and conversation through mounted routes.

Seams: authenticated `GET /v1/agents/{agent_id}/health` and `GET …/health/explanation` over the accepted P27
producer (`RecurringOperation.projection`), account, stop and removal reads. Producer passes run with no HTTP caller.
Expected values come from the saved rows (direct SQL) and the authored fixture constants, never from the code under
test. Every read is checked for zero writes (a digest of every row in the financial schemas) and zero provider calls
(every provider port replaced by a recorder that refuses). Authored fixtures only; nothing is live evidence.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

import financial_flows as ff
import harness
from edge_os_api.core.provider_ports import ProviderUnavailable
from edge_os_api.core.settings import load_settings
from edge_os_api.execution.worker import decision_slot

SLOT = dt.timedelta(minutes=5)
SCHEMAS = ("execution_local", "admission_local", "stops_local", "revocation_local", "recovery_local",
           "funding_local", "public")
PORTS = ("market", "quotes", "holdings", "receipts", "deposits", "removals", "chain", "original")


@pytest.fixture(scope="module")
def env(pg, signer):
    name = f"{pg.database}_health_{uuid.uuid4().hex[:6]}"
    pg.psql(f"create database {name}", db="postgres")
    url = make_url(pg.url).set(database=name).render_as_string(hide_password=False)
    try:
        yield harness.api_env(database_url=url, public_pem=signer.public_pem, previous_pem=None,
                              cors=["http://127.0.0.1:3999"])
    finally:
        pg.psql(f"drop database if exists {name} with (force)", db="postgres")


@pytest.fixture(scope="module")
def settings(env):
    result = harness.migrate(env)
    assert result.returncode == 0, result.stderr
    return load_settings(env)


@pytest.fixture
def journey(settings, tmp_path):
    with ff.fixture_client(settings, tmp_path / "effects.jsonl") as client:
        client.producer_base = decision_slot(dt.datetime.now(dt.timezone.utc)) + dt.timedelta(seconds=150)
        yield client


# ------------------------------------------------------------------------------------------------ helpers

def deployed(client: TestClient, headers: dict[str, str], agent: str) -> dict[str, Any]:
    state = ff.ready_for_action(client, headers, agent)
    response = client.post(f"/v1/agents/{agent}/deployment", headers=headers,
                           json={"request_key": "activate", "expected_consent_hash": state["consent"]["consent_hash"]})
    assert response.status_code == 201, response.text
    return {**state, "deployment": response.json()}


@contextlib.contextmanager
def at(client: TestClient, minutes: float):
    financial = client.app.state.financial
    saved = financial.connected._clock, financial.recurring._clock
    shifted = lambda: client.producer_base + dt.timedelta(minutes=minutes)  # noqa: E731 - one fixed moment
    financial.connected._clock = financial.recurring._clock = shifted
    try:
        yield
    finally:
        financial.connected._clock, financial.recurring._clock = saved


def produce(client: TestClient, state: dict[str, Any], minutes: float) -> None:
    with at(client, minutes):
        client.app.state.financial.recurring.producer_pass(only=[uuid.UUID(state["deployment"]["deployment_id"])])


def rows(client: TestClient, sql: str, **params: Any) -> list[dict[str, Any]]:
    with client.app.state.session_factory() as session:
        return [dict(row) for row in session.execute(text(sql), params).mappings()]


def fingerprint(client: TestClient) -> dict[str, str]:
    """md5 of every row of every table in the financial and record schemas: any write changes it."""
    tables = rows(client, "select table_schema s, table_name t from information_schema.tables where table_schema = "
                          "any(:schemas) and table_type = 'BASE TABLE' order by 1, 2", schemas=list(SCHEMAS))
    result = {}
    for table in tables:
        name = f'"{table["s"]}"."{table["t"]}"'
        [row] = rows(client, f"select md5(coalesce(string_agg(x::text, '|' order by x::text), '')) h from {name} x")
        result[name] = row["h"]
    return result


@contextlib.contextmanager
def no_provider(client: TestClient):
    """Every provider port refuses and records the attempt; the read must make none."""
    ports, calls = client.app.state.financial.ports, []

    class Refusing:
        def __init__(self, port: str) -> None:
            self.port = port

        def __getattr__(self, name: str) -> Any:
            calls.append(f"{self.port}.{name}")
            raise ProviderUnavailable(self.port)

    saved = {name: getattr(ports, name) for name in PORTS}
    for name in PORTS:
        setattr(ports, name, Refusing(name))
    try:
        yield calls
    finally:
        for name, port in saved.items():
            setattr(ports, name, port)


def read(client: TestClient, headers: dict[str, str], agent: str, minutes: float = 0) -> dict[str, Any]:
    """The direct snapshot, read with providers refused and every row compared before and after."""
    before = fingerprint(client)
    with at(client, minutes), no_provider(client) as calls:
        response = client.get(f"/v1/agents/{agent}/health", headers=headers)
    assert response.status_code == 200, response.text
    assert calls == [] and fingerprint(client) == before
    return response.json()


def ask(client: TestClient, headers: dict[str, str], agent: str, question: str, minutes: float = 0) -> dict[str, Any]:
    before = fingerprint(client)
    with at(client, minutes), no_provider(client) as calls:
        response = client.get(f"/v1/agents/{agent}/health/explanation", headers=headers, params={"question": question})
    assert response.status_code == 200, response.text
    assert calls == [] and fingerprint(client) == before
    return response.json()


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def newest_write(client: TestClient, deployment_id: str) -> tuple[str, str, str]:
    """Independent SQL: the newest stored time among the deployment's named rows."""
    candidates = rows(client, """
        select 'execution_local.execution_recurring_deployments' t, deployment_id::text id, 'updated_at' f,
               updated_at at time zone 'utc' at_ from execution_local.execution_recurring_deployments
         where deployment_id = cast(:d as uuid)
        union all select 'execution_local.execution_evaluation_jobs', job_id::text, 'updated_at',
               updated_at at time zone 'utc' from execution_local.execution_evaluation_jobs
         where deployment_id = cast(:d as uuid)
        union all select 'execution_local.execution_evaluation_outcomes', job_id::text, 'evaluated_at',
               evaluated_at at time zone 'utc' from execution_local.execution_evaluation_outcomes
         where deployment_id = cast(:d as uuid)
        union all select 'execution_local.execution_submission_attempts', a.attempt_id::text, f.f,
               case f.f when 'started_at' then a.started_at else a.completed_at end at time zone 'utc'
          from execution_local.execution_submission_attempts a
          cross join (values ('started_at'), ('completed_at')) f(f)
         where a.action_id in (select action_id from execution_local.execution_evaluation_jobs
                                where deployment_id = cast(:d as uuid))
        union all select 'execution_local.execution_queue', queue_id::text, 'updated_at', updated_at at time zone 'utc'
          from execution_local.execution_queue where action_id in (
               select action_id from execution_local.execution_evaluation_jobs where deployment_id = cast(:d as uuid))
    """, d=deployment_id)
    best = max((row for row in candidates if row["at_"] is not None), key=lambda row: row["at_"])
    return best["t"], best["id"], best["f"]


# ------------------------------------------------------------------------------------------------ cases

def test_signal_slot_is_dated_sourced_and_the_conversation_quotes_the_same_snapshot(journey, owner_a):
    agent = "health-signal"
    state = deployed(journey, owner_a, agent)
    produce(journey, state, 0)
    [job] = rows(journey, "select * from execution_local.execution_evaluation_jobs where deployment_id = "
                          "cast(:d as uuid)", d=state["deployment"]["deployment_id"])
    [outcome] = rows(journey, "select * from execution_local.execution_evaluation_outcomes where job_id = :j",
                     j=job["job_id"])
    [attempt] = rows(journey, "select * from execution_local.execution_submission_attempts where action_id = :a",
                     a=job["action_id"])
    health = read(journey, owner_a, agent)

    assert health["schema_version"] == "edge-os.agent-health-projection/1"
    assert health["evidence_class"] == "SERVICE_PROJECTION" and health["provider_mode"] == "fixture"
    assert health["scope"] == {"owner_id": health["scope"]["owner_id"], "agent_id": agent,
                               "wallet_id": state["wallet_id"], "network_id": job["network_id"],
                               "deployment_id": state["deployment"]["deployment_id"]}
    evaluation = health["last_evaluation"]["value"]
    assert evaluation["decision_slot"] == iso(job["decision_slot"]) and evaluation["evaluation"]["outcome"] == "SIGNAL"
    assert evaluation["evaluation"]["inputs_observed_at"]["value"] == iso(outcome["inputs_observed_at"])
    assert evaluation["evaluation"]["inputs_collected_at"]["value"] == iso(outcome["inputs_collected_at"])
    assert evaluation["evaluation"]["evaluated_at"]["value"] == iso(outcome["evaluated_at"])
    attempt_view = health["last_trade_attempt"]["value"]
    assert attempt_view["action_id"] == job["action_id"] and attempt_view["job_outcome"] == "SUBMITTED_CONFIRMED"
    assert attempt_view["submission"]["completed_at"]["value"] == iso(attempt["completed_at"])
    # Next work is the producer's cursor + one slot, never the bounded pipeline's last decision + 5 minutes.
    assert health["producer"]["next_due_slot"] == {"state": "KNOWN", "value": iso(job["decision_slot"] + SLOT),
                                                   "source": "producer.next_due_slot"}
    assert health["bounded_pipeline"]["next_scheduled_at"]["state"] == "UNKNOWN"
    assert health["wait_reason"]["value"] is None and health["read_at"] == iso(journey.producer_base)
    table, row_id, field = newest_write(journey, state["deployment"]["deployment_id"])
    assert (health["as_of"]["table"], health["as_of"]["id"], health["as_of"]["field"]) == (table, row_id, field)
    assert health["pending_reconciliation"]["canonical"]["action_ids"] == []
    assert {item["field"] for item in health["unknown_inputs"]} == {
        "native_gas_aggregate", "dataset_qualification", "revision_edge_evidence", "control_state_basis",
        "selected_completion_outcome", "job_manifest_hash"}
    assert all(item["state"] == "UNKNOWN" for item in health["unknown_inputs"])
    assert [p["quantity"]["raw"] for p in health["residual_inventory"]] == [ff.ENTRY_BASE_OUTPUT]

    answer = ask(journey, owner_a, agent, "What did the agent last do?")
    assert answer["topic"] == "last" and answer["snapshot"] == health
    assert answer["snapshot_digest"] == health["snapshot_digest"] and answer["as_of"] == health["as_of"]
    text_ = " ".join(line["text"] for line in answer["answer"])
    assert job["action_id"] in text_ and "SIGNAL" in text_ and iso(outcome["evaluated_at"]) in text_
    assert "An evaluation is not a trade" in text_


@pytest.mark.parametrize("agent,outcome", [("health-fx-nosignal", "NO_SIGNAL"), ("health-fx-ineligible", "INELIGIBLE")])
def test_a_no_signal_evaluation_is_not_reported_as_a_trade(journey, owner_a, agent, outcome):
    state = deployed(journey, owner_a, agent)
    produce(journey, state, 0)
    health = read(journey, owner_a, agent)
    assert health["last_evaluation"]["value"]["evaluation"]["outcome"] == outcome
    assert health["last_trade_attempt"] == {"state": "UNKNOWN", "reason": "NO_SUBMISSION_IN_SHOWN_OCCURRENCES"}
    assert health["residual_inventory"] == []
    answer = ask(journey, owner_a, agent, "did it trade?")
    assert "Last trade attempt: UNKNOWN (NO_SUBMISSION_IN_SHOWN_OCCURRENCES)" in answer["answer"][1]["text"]


def test_a_missing_feed_keeps_its_unsaved_times_unknown_with_a_reason(journey, owner_a):
    agent = "health-missing-feed"
    state = deployed(journey, owner_a, agent)
    market = journey.app.state.financial.ports.market
    real = market.observe
    market.observe = lambda request: (_ for _ in ()).throw(ProviderUnavailable("observations"))
    try:
        produce(journey, state, 0)
    finally:
        market.observe = real
    health = read(journey, owner_a, agent)
    evaluation = health["last_evaluation"]["value"]["evaluation"]
    assert (evaluation["outcome"], evaluation["reason"]) == ("UNAVAILABLE", "OBSERVATIONS_UNAVAILABLE")
    [row] = rows(journey, "select inputs_observed_at, inputs_collected_at from execution_local."
                          "execution_evaluation_outcomes where deployment_id = cast(:d as uuid)",
                 d=state["deployment"]["deployment_id"])
    # The port never answered, so the producer saved no input time: each stays UNKNOWN with its own reason.
    assert (row["inputs_observed_at"], row["inputs_collected_at"]) == (None, None)
    assert evaluation["inputs_observed_at"] == {"state": "UNKNOWN", "reason": "INPUT_OBSERVED_TIME_NOT_SAVED"}
    assert evaluation["inputs_collected_at"] == {"state": "UNKNOWN", "reason": "INPUT_COLLECTION_TIME_NOT_SAVED"}
    assert evaluation["evaluated_at"]["state"] == "KNOWN"
    assert health["last_trade_attempt"]["state"] == "UNKNOWN"
    text_ = " ".join(line["text"] for line in ask(journey, owner_a, agent, "what was last evaluated")["answer"])
    assert "collected UNKNOWN (INPUT_COLLECTION_TIME_NOT_SAVED)" in text_


def test_next_work_is_the_producer_slot_not_the_last_decision_plus_five_minutes(journey, owner_a):
    agent = "health-next-work"
    state = deployed(journey, owner_a, agent)
    produce(journey, state, 0)  # slot 0 decides and trades
    market = journey.app.state.financial.ports.market
    real = market.observe
    market.observe = lambda request: (_ for _ in ()).throw(ProviderUnavailable("observations"))
    try:
        produce(journey, state, 5)  # slot 5 saves no decision: the feed is missing
    finally:
        market.observe = real
    [cursor] = rows(journey, "select cursor_slot from execution_local.execution_recurring_deployments where "
                             "deployment_id = cast(:d as uuid)", d=state["deployment"]["deployment_id"])
    [decision] = rows(journey, "select max(decision_at) d from execution_local.execution_decisions where agent_id = :a",
                      a=agent)
    health = read(journey, owner_a, agent, minutes=5)
    assert health["producer"]["next_due_slot"]["value"] == iso(cursor["cursor_slot"] + SLOT)
    assert iso(decision["d"] + SLOT) != health["producer"]["next_due_slot"]["value"]  # the two rules differ here
    assert health["bounded_pipeline"]["last_decision_input_at"]["value"] == iso(decision["d"])


def test_a_silent_producer_is_a_read_clock_wait_and_as_of_is_the_stored_write(journey, owner_a):
    agent = "health-silent"
    state = deployed(journey, owner_a, agent)
    health = read(journey, owner_a, agent, minutes=0)
    assert health["producer"]["producer_silent"]["value"] is True
    assert health["producer"]["next_due_slot"] == {"state": "UNKNOWN", "reason": "PRODUCER_NOT_SEEN"}
    assert health["wait_reason"] == {"state": "KNOWN", "value": "PRODUCER_NOT_SEEN",
                                     "source": "producer.wait_reason at read_at"}
    assert health["last_evaluation"] == {"state": "UNKNOWN", "reason": "NO_OCCURRENCE_SAVED"}
    [deployment] = rows(journey, "select updated_at from execution_local.execution_recurring_deployments where "
                                 "deployment_id = cast(:d as uuid)", d=state["deployment"]["deployment_id"])
    assert health["as_of"] == {"table": "execution_local.execution_recurring_deployments",
                               "id": state["deployment"]["deployment_id"], "field": "updated_at",
                               "time": iso(deployment["updated_at"])}
    # A later read clock changes only the read-clock values; the stored write stays the same.
    later = read(journey, owner_a, agent, minutes=20)
    assert later["as_of"] == health["as_of"] and later["read_at"] != health["read_at"]
    answer = ask(journey, owner_a, agent, "why is it waiting?")
    assert answer["topic"] == "waiting" and "PRODUCER_NOT_SEEN" in answer["answer"][0]["text"]


def test_an_unknown_original_is_the_canonical_pending_item_and_account_warnings_stay_separate(journey, owner_a):
    agent = "health-fx-lost-ack"
    state = deployed(journey, owner_a, agent)
    produce(journey, state, 0)
    [job] = rows(journey, "select action_id, outcome from execution_local.execution_evaluation_jobs where "
                          "deployment_id = cast(:d as uuid)", d=state["deployment"]["deployment_id"])
    assert job["outcome"] == "SUBMITTED_UNKNOWN"
    health = read(journey, owner_a, agent)
    pending = health["pending_reconciliation"]
    assert pending["canonical"]["rule"] == "PRODUCER_UNSETTLED_QUEUE"
    assert pending["canonical"]["action_ids"] == [job["action_id"]]
    recovery, monitoring = pending["warnings"]
    open_cases = [r["action_id"] for r in rows(journey, "select action_id from recovery_local.recovery_cases where "
                                                        "action_id = :a and state in ('OPEN','UNKNOWN')",
                                               a=job["action_id"])]
    assert recovery["kind"] == "ACCOUNT_RECOVERY_OPEN_OR_UNKNOWN" and recovery["action_ids"] == open_cases
    assert monitoring == {"kind": "MONITORING_SUBMITTED_UNKNOWN", "pending": True,
                          "source": monitoring["source"]}
    assert health["wait_reason"]["value"] == "WAITING_RECONCILIATION"
    answer = ask(journey, owner_a, agent, "is anything pending reconciliation?")
    assert answer["topic"] == "reconciliation" and job["action_id"] in answer["answer"][0]["text"]
    assert "not merged" in answer["answer"][1]["text"]


def test_stop_removal_and_end_are_dated_rows_and_residual_inventory_stays(journey, owner_a):
    agent = "health-controls"
    state = deployed(journey, owner_a, agent)
    produce(journey, state, 0)
    stop = journey.post(f"/v1/agents/{agent}/stops", headers=owner_a,
                        json={"mode": "STOP_NEW_ENTRIES", "scope": "AGENT_WALLET_NETWORK"})
    assert stop.status_code == 200, stop.text
    stopped = read(journey, owner_a, agent)
    assert [(s["mode"], s["scope"], s["created_at"]) for s in stopped["controls"]["stops"]] == [
        ("STOP_NEW_ENTRIES", "AGENT_WALLET_NETWORK", stop.json()["created_at"].replace("+00:00", "Z")[:19] + "Z")]
    assert stopped["wait_reason"]["value"] == "STOPPED:STOP_NEW_ENTRIES"
    assert stopped["controls"]["control_state_basis"]["state"] == "UNKNOWN"
    removal = journey.post(f"/v1/agents/{agent}/removal", headers=owner_a,
                           json={"request_key": "remove", "reason": "owner removes the agent"})
    assert removal.status_code == 200, removal.text
    produce(journey, state, 5)
    removed = read(journey, owner_a, agent, minutes=5)
    assert (removed["deployment"]["state"], removed["deployment"]["end_reason"]) == ("ENDED", "REMOVAL_REQUESTED")
    assert [r["state"] for r in removed["controls"]["removals"]] == [removal.json()["state"]]
    assert removed["producer"]["next_due_slot"] == {"state": "UNKNOWN", "reason": "REMOVAL_REQUESTED"}
    assert [p["quantity"]["raw"] for p in removed["residual_inventory"]] == [ff.ENTRY_BASE_OUTPUT]
    answer = ask(journey, owner_a, agent, "was it stopped or removed?", minutes=5)
    assert answer["topic"] == "controls"
    first = answer["answer"][0]["text"]
    assert "ENDED (REMOVAL_REQUESTED" in first and "STOP_NEW_ENTRIES" in first
    assert "changes nothing" in answer["answer"][1]["text"]


def test_an_owner_end_is_a_dated_end_with_no_next_work(journey, owner_a):
    agent = "health-ended"
    state = deployed(journey, owner_a, agent)
    produce(journey, state, 0)
    ended = journey.post(f"/v1/agents/{agent}/deployment/end", headers=owner_a)
    assert ended.status_code == 200, ended.text
    health = read(journey, owner_a, agent)
    assert health["deployment"]["ended_at"] == ended.json()["ended_at"]
    assert health["producer"]["next_due_slot"] == {"state": "UNKNOWN", "reason": "OWNER_ENDED"}
    assert health["wait_reason"]["value"] == "ENDED:OWNER_ENDED"
    # Historical evaluation and trade facts stay as dated facts after the end.
    assert health["last_evaluation"]["state"] == "KNOWN" and health["last_trade_attempt"]["state"] == "KNOWN"


def test_a_changed_saved_revision_keeps_current_and_historical_identity_distinct(journey, owner_a):
    agent = "health-revision"
    state = deployed(journey, owner_a, agent)
    produce(journey, state, 0)
    # Authored fault: the saved deployment names another execution revision than the agent now resolves to.
    with journey.app.state.session_factory() as session:
        session.execute(text("update execution_local.execution_recurring_deployments set execution_revision_id = "
                             "'authored-older-revision' where deployment_id = cast(:d as uuid)"),
                        {"d": state["deployment"]["deployment_id"]})
        session.commit()
    health = read(journey, owner_a, agent)
    identity = health["identity"]
    assert identity["saved_deployment"]["execution_revision_id"] == "authored-older-revision"
    assert identity["current_resolution"]["value"]["execution_revision_id"] != "authored-older-revision"
    assert identity["changed"] == {"state": "KNOWN", "value": True,
                                   "source": "saved deployment identity vs current resolution"}
    produce(journey, state, 5)
    after = read(journey, owner_a, agent, minutes=5)
    assert after["deployment"]["end_reason"] == "IDENTITY_CHANGED"
    assert after["occurrences"][0]["decision_slot"] == health["occurrences"][0]["decision_slot"]
    answer = ask(journey, owner_a, agent, "did the revision change?", minutes=5)
    assert answer["topic"] == "identity" and "Changed: True" in answer["answer"][0]["text"]


def test_sibling_agents_and_another_owner_cannot_leak_or_retarget(journey, owner_a, owner_b):
    first = deployed(journey, owner_a, "health-sibling-one")
    second = deployed(journey, owner_a, "health-sibling-two")
    produce(journey, first, 0)
    produce(journey, second, 0)
    one = read(journey, owner_a, "health-sibling-one")
    two = read(journey, owner_a, "health-sibling-two")
    # Both agents hold the same token; each snapshot names only its own deployment, wallet and position.
    assert one["scope"]["deployment_id"] != two["scope"]["deployment_id"]
    assert one["scope"]["wallet_id"] != two["scope"]["wallet_id"]
    assert {p["asset_id"] for p in one["residual_inventory"]} == {p["asset_id"] for p in two["residual_inventory"]}
    assert {p["position_id"] for p in one["residual_inventory"]}.isdisjoint(
        {p["position_id"] for p in two["residual_inventory"]})
    own_actions = {r["action_id"] for r in rows(journey, "select action_id from execution_local."
                                                         "execution_evaluation_jobs where agent_id = 'health-sibling-one'")}
    assert one["occurrences"] and all(item["action_id"] in own_actions for item in one["occurrences"])
    assert journey.get("/v1/me", headers=owner_b).status_code == 200  # first sign-in saves the user row
    before = fingerprint(journey)
    for path in ("/v1/agents/health-sibling-one/health", "/v1/agents/health-sibling-one/health/explanation"):
        response = journey.get(path, headers=owner_b, params={"question": "what did it do"})
        assert response.status_code == 404 and "health-sibling" not in response.text.replace(path, "")
    assert journey.get("/v1/agents/health-nobody/health", headers=owner_a).status_code == 404
    assert journey.get("/v1/agents/health-sibling-one/health").status_code == 401
    assert fingerprint(journey) == before


def test_an_agent_without_a_deployment_is_explicitly_unknown(journey, owner_a):
    agent = "health-undeployed"
    ff.ready_for_action(journey, owner_a, agent)
    health = read(journey, owner_a, agent)
    assert health["deployment"] is None and health["as_of"] is None and health["scope"]["deployment_id"] is None
    assert health["producer"]["next_due_slot"] == {"state": "UNKNOWN", "reason": "NO_DEPLOYMENT"}
    assert health["pending_reconciliation"]["canonical"] == {"state": "UNKNOWN", "reason": "NO_DEPLOYMENT"}
    assert health["record_id"].endswith(":none")
    answer = ask(journey, owner_a, agent, "hello")
    assert answer["topic"] == "summary" and "UNKNOWN (NO_DEPLOYMENT)" in " ".join(l["text"] for l in answer["answer"])


def test_a_question_is_bounded_and_a_new_reply_reads_the_current_snapshot(journey, owner_a):
    agent = "health-replies"
    state = deployed(journey, owner_a, agent)
    assert journey.get(f"/v1/agents/{agent}/health/explanation", headers=owner_a).status_code == 422
    too_long = journey.get(f"/v1/agents/{agent}/health/explanation", headers=owner_a, params={"question": "x" * 501})
    assert too_long.status_code == 422
    first = ask(journey, owner_a, agent, "what is next?")
    produce(journey, state, 0)
    second = ask(journey, owner_a, agent, "what is next?")
    assert first["snapshot_digest"] != second["snapshot_digest"] and first["as_of"] != second["as_of"]
    assert first["answer"][0]["text"].startswith("Next due slot from the producer: UNKNOWN (PRODUCER_NOT_SEEN)")
    assert second["snapshot"]["producer"]["next_due_slot"]["state"] == "KNOWN"
    # Unchanged rows give the same digest on a repeated read: the identity survives a re-read.
    assert ask(journey, owner_a, agent, "what is next?")["snapshot_digest"] == second["snapshot_digest"]


def test_a_restarted_application_returns_the_same_snapshot_identity(journey, owner_a, settings, tmp_path):
    agent = "health-restart"
    state = deployed(journey, owner_a, agent)
    produce(journey, state, 0)
    before = read(journey, owner_a, agent)
    with ff.fixture_client(settings, tmp_path / "restart-effects.jsonl") as restarted:
        restarted.producer_base = journey.producer_base
        after = read(restarted, owner_a, agent)
    assert after == before
