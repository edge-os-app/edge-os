"""The connected fixture journey through mounted routes and the bounded worker.

Seam: authenticated route → saved state → worker → saved/readback result. Expected values come from the
authored fixture constants (revision sizing 100 quote units, authored price 2 quote per base), not from the
code under test.
"""

from __future__ import annotations

import uuid

import pytest

import financial_flows as ff


@pytest.fixture
def journey(settings, tmp_path):
    with ff.fixture_client(settings, tmp_path / "effects.jsonl") as client:
        yield client


def test_signal_saves_decision_then_one_confirmed_action_with_receipt(journey, owner_a):
    ff.ready_for_action(journey, owner_a, "journey-signal")
    scheduled = ff.schedule(journey, owner_a, "journey-signal", "first")
    assert scheduled.status_code == 201, scheduled.text
    job = ff.run_job(journey, scheduled.json())
    assert job["state"] == "COMPLETED", job
    assert job["outcome"] == "SUBMITTED_CONFIRMED", job

    action = journey.get(f"/v1/actions/{job['action_id']}", headers=owner_a)
    assert action.status_code == 200, action.text
    body = action.json()
    assert body["decision"]["status"] == "SIGNAL"
    assert body["decision"]["decision_id"] == job["decision_id"]
    assert body["payload"]["input"]["quote_input"]["raw"] == ff.ENTRY_QUOTE_INPUT
    assert body["payload"]["quantity"]["raw"] == ff.ENTRY_BASE_OUTPUT
    assert body["queue"]["state"] == "SUBMITTED_CONFIRMED"
    assert [receipt["outcome"] for receipt in body["receipts"]] == ["CONFIRMED"]
    assert body["attempts"][0]["content"]["original_references"]["transaction_hash"] is None
    assert body["mandate_id"] == job["consent_adoption_id"]
    assert len(ff.effects(journey)) == 1

    overview = journey.get("/v1/agents/journey-signal/actions", headers=owner_a).json()
    assert overview["positions"][0]["inventory_raw"] == ff.ENTRY_BASE_OUTPUT
    funding = journey.get("/v1/agents/journey-signal/funding", headers=owner_a).json()
    holdings = {item["asset_id"]: item["raw"] for item in funding["current_holdings"]["assets"]}
    quote_asset = funding["declaration"]["trading_asset"]["asset_id"]
    assert holdings[quote_asset] == str(int(ff.TRADING_DEPOSIT) - int(ff.ENTRY_QUOTE_INPUT))
    credited = {b["asset_id"]: b["credited_deposits"]["raw"] for b in funding["deposit_balances"]}
    assert credited[quote_asset] == ff.TRADING_DEPOSIT  # deposit history stays distinct from current holdings


def test_repeated_scheduling_and_rerun_never_create_a_second_action(journey, owner_a):
    ff.ready_for_action(journey, owner_a, "journey-repeat")
    first = ff.schedule(journey, owner_a, "journey-repeat", "same-key")
    again = ff.schedule(journey, owner_a, "journey-repeat", "same-key")
    other_key = ff.schedule(journey, owner_a, "journey-repeat", "other-key")
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["job_id"] == first.json()["job_id"]
    assert other_key.json()["job_id"] == first.json()["job_id"]  # same consent and decision slot: one job
    ff.run_job(journey, first.json())
    rerun = ff.run_job(journey, first.json())
    assert rerun["state"] == "COMPLETED" and rerun["runs"] >= 1
    assert len(ff.effects(journey)) == 1


@pytest.mark.parametrize("agent_id,outcome", [("journey-fx-nosignal", "NO_SIGNAL"),
                                              ("journey-fx-ineligible", "INELIGIBLE")])
def test_no_signal_and_ineligible_save_the_decision_and_create_no_intent(journey, owner_a, agent_id, outcome):
    ff.ready_for_action(journey, owner_a, agent_id)
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent_id).json())
    assert (job["state"], job["outcome"], job["action_id"]) == ("COMPLETED", outcome, None)
    overview = journey.get(f"/v1/agents/{agent_id}/actions", headers=owner_a).json()
    assert [d["status"] for d in overview["decisions"]] == [outcome]
    assert overview["queue"] == []
    assert ff.effects(journey) == []


def test_lost_acknowledgement_stays_unknown_then_reconciles_the_original_action(journey, owner_a):
    agent = "journey-fx-lost-ack"
    ff.ready_for_action(journey, owner_a, agent)
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert (job["state"], job["outcome"]) == ("SUBMITTED", "SUBMITTED_UNKNOWN")
    before = journey.get(f"/v1/actions/{job['action_id']}", headers=owner_a).json()
    assert before["admission"][0]["status"] == "SUBMISSION_UNKNOWN"
    assert {r["state"] for r in before["reservations"]} == {"RESERVED"}  # unknown keeps every reservation

    # The same job is not rerun as a new submission, and a later slot cannot submit past the unresolved action.
    rerun = ff.run_job(journey, job)
    assert rerun["state"] == "SUBMITTED" and len(ff.effects(journey)) == 1
    connected = journey.app.state.financial.connected
    original_clock = connected._clock
    connected._clock = lambda: original_clock() + __import__("datetime").timedelta(minutes=5)
    try:
        later = ff.run_job(journey, ff.schedule(journey, owner_a, agent, "later-slot").json())
    finally:
        connected._clock = original_clock
    assert later["job_id"] != job["job_id"]
    assert (later["outcome"], later["reason"]) == ("ADMISSION_DENIED", "UNRESOLVED_PRIOR_ACTION")
    assert len(ff.effects(journey)) == 1

    settled = journey.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a)
    assert settled.status_code == 200, settled.text
    assert (settled.json()["receipt_outcome"], settled.json()["case_state"]) == ("CONFIRMED", "CONFIRMED")
    repeat = journey.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a)
    assert repeat.json()["duplicate"] is True
    after = journey.get(f"/v1/actions/{job['action_id']}", headers=owner_a).json()
    assert after["queue"]["state"] == "SUBMITTED_CONFIRMED"
    assert [r["outcome"] for r in after["receipts"]] == ["SUBMISSION_UNKNOWN", "CONFIRMED"]  # history kept
    assert len(ff.effects(journey)) == 1  # reconciliation made no second economic action
    jobs = journey.get(f"/v1/agents/{agent}/actions", headers=owner_a).json()["jobs"]
    assert jobs[0]["state"] == "COMPLETED"


def test_unknown_outcome_reconciles_from_the_independent_receipt(journey, owner_a):
    agent = "journey-fx-unknown"
    ff.ready_for_action(journey, owner_a, agent)
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert job["outcome"] == "SUBMITTED_UNKNOWN"
    settled = journey.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert settled["case_state"] == "CONFIRMED"


def test_revert_consumes_gas_only_and_deny_releases_reservations(journey, owner_a):
    ff.ready_for_action(journey, owner_a, "journey-fx-revert")
    reverted = ff.run_job(journey, ff.schedule(journey, owner_a, "journey-fx-revert").json())
    assert reverted["outcome"] == "SUBMITTED_REVERTED"
    body = journey.get(f"/v1/actions/{reverted['action_id']}", headers=owner_a).json()
    assert body["receipts"][0]["outcome"] == "REVERTED"
    funding = journey.get("/v1/agents/journey-fx-revert/funding", headers=owner_a).json()
    holdings = {item["asset_id"]: item["raw"] for item in funding["current_holdings"]["assets"]}
    assert holdings[funding["declaration"]["trading_asset"]["asset_id"]] == ff.TRADING_DEPOSIT
    assert holdings[funding["declaration"]["gas_asset"]["asset_id"]] == str(int(ff.GAS_DEPOSIT) - int(ff.PER_ACTION_GAS))

    ff.ready_for_action(journey, owner_a, "journey-fx-deny")
    denied = ff.run_job(journey, ff.schedule(journey, owner_a, "journey-fx-deny").json())
    assert denied["outcome"] == "DENIED_UNSENT"
    body = journey.get(f"/v1/actions/{denied['action_id']}", headers=owner_a).json()
    assert {r["state"] for r in body["reservations"]} == {"RELEASED"}


def test_open_position_exit_closes_the_attributed_inventory(journey, owner_a):
    agent = "journey-exit"
    ff.ready_for_action(journey, owner_a, agent)
    entry = ff.run_job(journey, ff.schedule(journey, owner_a, agent, "entry").json())
    assert entry["outcome"] == "SUBMITTED_CONFIRMED"
    # The next slot evaluates the exit rule on the open position (fixture prices fall once a position is open).
    connected = journey.app.state.financial.connected
    original_clock = connected._clock
    connected._clock = lambda: original_clock() + __import__("datetime").timedelta(minutes=5)
    try:
        exit_job = ff.run_job(journey, ff.schedule(journey, owner_a, agent, "exit").json())
    finally:
        connected._clock = original_clock
    assert exit_job["outcome"] == "SUBMITTED_CONFIRMED", exit_job
    action = journey.get(f"/v1/actions/{exit_job['action_id']}", headers=owner_a).json()
    assert action["operation"] == "EXIT"
    positions = journey.get(f"/v1/agents/{agent}/actions", headers=owner_a).json()["positions"]
    assert [p["inventory_raw"] for p in positions] == ["0"]
    # A closed position never blocks the next entry: a later slot opens a new position.
    connected._clock = lambda: original_clock() + __import__("datetime").timedelta(minutes=10)
    try:
        again = ff.run_job(journey, ff.schedule(journey, owner_a, agent, "re-entry").json())
    finally:
        connected._clock = original_clock
    assert again["outcome"] == "SUBMITTED_CONFIRMED", again
    positions = journey.get(f"/v1/agents/{agent}/actions", headers=owner_a).json()["positions"]
    assert sorted(p["inventory_raw"] for p in positions) == ["0", ff.ENTRY_BASE_OUTPUT]


class ProcessDied(BaseException):
    """Stands in for a process killed between the provider effect and the saved outcome."""


def test_restart_after_death_inside_submission_reconciles_without_a_second_effect(settings, tmp_path, owner_a):
    effects_file = tmp_path / "effects.jsonl"
    agent = "journey-crash"
    with ff.fixture_client(settings, effects_file) as first:
        ff.ready_for_action(first, owner_a, agent)
        job = ff.schedule(first, owner_a, agent).json()
        ports = first.app.state.financial.ports
        real_transport = ports.transport

        def dying_transport(**kwargs):
            transport = real_transport(**kwargs)
            real_submit = transport.submit

            def submit(prepared):
                real_submit(prepared)  # the fixture applies and records the effect
                raise ProcessDied()
            transport.submit = submit
            return transport

        ports.transport = dying_transport
        with pytest.raises(ProcessDied):
            first.app.state.financial.connected.run_job(uuid.UUID(job["job_id"]))
        assert len(ff.effects(first)) == 1

    with ff.fixture_client(settings, effects_file) as restarted:  # a fresh process over the same database
        resumed = ff.run_job(restarted, job)
        assert (resumed["state"], resumed["outcome"]) == ("SUBMITTED", "CLAIMED"), resumed  # retained claim, no retry
        action = restarted.get(f"/v1/actions/{resumed['action_id']}", headers=owner_a).json()
        assert [a["state"] for a in action["attempts"]] == ["IN_FLIGHT"]
        assert action["admission"][0]["status"] == "SUBMISSION_UNKNOWN"
        settled = restarted.post(f"/v1/actions/{resumed['action_id']}/reconcile", headers=owner_a).json()
        assert settled["case_state"] == "CONFIRMED"
        assert len(ff.effects(restarted)) == 1
        final = restarted.get(f"/v1/actions/{resumed['action_id']}", headers=owner_a).json()
        assert final["queue"]["state"] == "SUBMITTED_CONFIRMED"
        assert [a["state"] for a in final["attempts"]] == ["TERMINAL"]


def test_observations_for_another_market_are_never_evaluated(journey, owner_a):
    agent = "journey-wrong-market"
    ff.ready_for_action(journey, owner_a, agent)
    market = journey.app.state.financial.ports.market
    real_observe = market.observe

    def other_market(request):
        observed = real_observe(request)
        return type(observed)(inputs=observed.inputs, provenance={**observed.provenance, "market_binding_id": "other"})
    market.observe = other_market
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert (job["state"], job["reason"], job["decision_id"]) == ("UNAVAILABLE", "OBSERVATIONS_WRONG_MARKET", None)
    assert journey.get(f"/v1/agents/{agent}/actions", headers=owner_a).json()["decisions"] == []


@pytest.mark.parametrize("receipt", ["missing_gas", "wrong_wallet"])
def test_incomplete_or_wrong_tuple_receipts_keep_the_action_unknown_and_liable(journey, owner_a, receipt):
    agent = f"journey-fx-unknown-{receipt.replace('_', '-')}"
    ff.ready_for_action(journey, owner_a, agent)
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert job["outcome"] == "SUBMITTED_UNKNOWN"
    receipts = journey.app.state.financial.ports.receipts
    real_observe = receipts.observe

    def altered(*, action_id, wallet_id, network_id):
        if receipt == "wrong_wallet":
            return real_observe(action_id=action_id, wallet_id="another-wallet", network_id=network_id)
        observed = real_observe(action_id=action_id, wallet_id=wallet_id, network_id=network_id)
        return type(observed)(observed.outcome, observed.actual_input, observed.actual_output, None,
                              observed.observed_at, observed.source_ref)
    receipts.observe = altered
    settled = journey.post(f"/v1/actions/{job['action_id']}/reconcile", headers=owner_a).json()
    assert settled["case_state"] != "CONFIRMED", settled
    action = journey.get(f"/v1/actions/{job['action_id']}", headers=owner_a).json()
    # Missing gas fails closed as a durable breach; a wrong-tuple receipt proves nothing. Neither invents an
    # amount, releases a reservation or lets the wallet start another action.
    expected = "BREACHED" if receipt == "missing_gas" else "SUBMISSION_UNKNOWN"
    assert action["admission"][0]["status"] == expected
    assert {r["state"] for r in action["reservations"]} == {"RESERVED"}
    assert all(r["outcome"] != "CONFIRMED" or r["breach"] for r in action["receipts"])
    assert len(ff.effects(journey)) == 1
