"""Process-level recovery and concurrency controls against the real run-labelled PostgreSQL.

Each control runs the real service in an independent OS process. Crash scenarios stop that
process with `os._exit`. No control makes a network or provider call.
"""

from __future__ import annotations

import json
import time

import helpers

NETWORK = 10143


def _prepare(wallet_client, headers, agent_id, strategy_id, revision_id):
    response = wallet_client.post(
        f"/v1/wallet-setup/agents/{agent_id}/prepare",
        json={"network_id": NETWORK, "strategy_id": strategy_id, "strategy_revision_id": revision_id,
              "request_key": f"key-{agent_id}"}, headers=headers)
    assert response.status_code == 200, response.text


def _run_driver(pg, owner_id, agent_id, strategy_id, revision_id, scenario, *extra):
    process = helpers.start_driver(pg.url, owner_id, agent_id, strategy_id, revision_id, scenario, *extra)
    out, err = process.communicate(timeout=90)
    assert process.returncode == 0, err
    return json.loads(out.strip().splitlines()[-1])


def test_fresh_process_restart_reloads_same_binding(wallet_client, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = helpers.owner_user_id(wallet_client, owner_a)
    _prepare(wallet_client, owner_a, "agent-r1", strategy_id, revision_id)

    confirmed = _run_driver(pg, owner_id, "agent-r1", strategy_id, revision_id, "dispatch")
    assert confirmed["state"] == "CONFIRMED" and confirmed["wallet_id"]
    reloaded = _run_driver(pg, owner_id, "agent-r1", strategy_id, revision_id, "read")
    assert reloaded["state"] == "CONFIRMED" and reloaded["wallet_id"] == confirmed["wallet_id"]
    api_view = wallet_client.get("/v1/wallet-setup/agents/agent-r1", headers=owner_a).json()
    assert api_view["wallet_id"] == confirmed["wallet_id"]
    assert pg.psql("select creation_dispatched from wallet_setups where agent_id = 'agent-r1'") == "t"


def test_crash_during_dispatch_does_not_authorize_second_creation(wallet_client, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = helpers.owner_user_id(wallet_client, owner_a)
    _prepare(wallet_client, owner_a, "agent-crash1", strategy_id, revision_id)

    process = helpers.start_driver(pg.url, owner_id, "agent-crash1", strategy_id, revision_id, "crash_at_dispatch")
    assert process.wait(timeout=90) == 7
    assert pg.psql("select creation_dispatched from wallet_setups where agent_id = 'agent-crash1'") == "t"
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'DISPATCH_INTENT'") == "1"
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'RESULT_RETURNED'") == "0"

    resumed = _run_driver(pg, owner_id, "agent-crash1", strategy_id, revision_id, "resume")
    assert resumed["state"] == "UNKNOWN" and resumed["reason"] == "RECONCILE_NO_EXACT_ID"
    assert resumed["invoked"] is False
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'DISPATCH_INTENT'") == "1"
    assert pg.psql("select count(*) from wallet_setups where wallet_id is not null") == "0"


def test_crash_after_result_before_binding_reconciles_exact_late_result(wallet_client, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = helpers.owner_user_id(wallet_client, owner_a)
    _prepare(wallet_client, owner_a, "agent-crash2", strategy_id, revision_id)

    process = helpers.start_driver(pg.url, owner_id, "agent-crash2", strategy_id, revision_id, "crash_at_verify")
    assert process.wait(timeout=90) == 8
    retained = pg.psql("select content->>'wallet_id' from wallet_setup_events where event_type = 'RESULT_RETURNED' "
                       "order by sequence desc limit 1")
    assert retained
    assert pg.psql("select count(*) from wallet_setups where wallet_id is not null") == "0"

    resumed = _run_driver(pg, owner_id, "agent-crash2", strategy_id, revision_id, "resume", "--seed-wallet", retained)
    assert resumed["state"] == "CONFIRMED" and resumed["wallet_id"] == retained
    assert resumed["invoked"] is False
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'DISPATCH_INTENT'") == "1"
    assert pg.psql("select count(distinct wallet_id) from wallet_setups where wallet_id is not null") == "1"


def test_two_independent_processes_create_one_wallet(wallet_client, owner_a, pg, tmp_path):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = helpers.owner_user_id(wallet_client, owner_a)
    _prepare(wallet_client, owner_a, "agent-race", strategy_id, revision_id)

    start_file = tmp_path / "go"
    first = helpers.start_driver(pg.url, owner_id, "agent-race", strategy_id, revision_id, "race",
                                 "--start-file", str(start_file))
    second = helpers.start_driver(pg.url, owner_id, "agent-race", strategy_id, revision_id, "race",
                                  "--start-file", str(start_file))
    time.sleep(0.5)
    start_file.write_text("go")
    out1, err1 = first.communicate(timeout=90)
    out2, err2 = second.communicate(timeout=90)
    assert first.returncode == 0, err1
    assert second.returncode == 0, err2
    results = [json.loads(out1.strip().splitlines()[-1]), json.loads(out2.strip().splitlines()[-1])]

    assert sum(1 for item in results if item["invoked"]) == 1
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'DISPATCH_INTENT'") == "1"
    assert pg.psql("select count(*) from wallet_setups") == "1"
    assert pg.psql("select count(distinct wallet_id) from wallet_setups where wallet_id is not null") == "1"
    assert pg.psql("select state from wallet_setups where agent_id = 'agent-race'") == "CONFIRMED"
    bound = {item["wallet_id"] for item in results if item["wallet_id"]}
    assert len(bound) == 1
    assert wallet_client.get("/v1/wallet-setup/agents/agent-race", headers=owner_a).json()["wallet_id"] in bound
