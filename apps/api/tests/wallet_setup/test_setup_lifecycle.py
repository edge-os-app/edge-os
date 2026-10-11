"""Setup lifecycle: prepare, dispatch, replay, cancel, lost response and conflicting results."""

from __future__ import annotations

import helpers

from edge_os_api.wallet_setup.provider import WalletEvidence

NETWORK = 10143


def _prepare(wallet_client, headers, agent_id, strategy_id, revision_id, *, key="key-1"):
    return wallet_client.post(f"/v1/wallet-setup/agents/{agent_id}/prepare",
                              json={"network_id": NETWORK, "strategy_id": strategy_id,
                                    "strategy_revision_id": revision_id, "request_key": key}, headers=headers)


def _dispatch(wallet_client, headers, agent_id):
    return wallet_client.post(f"/v1/wallet-setup/agents/{agent_id}/dispatch", headers=headers)


def test_prepare_dispatch_confirms_and_binds(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    assert _prepare(wallet_client, owner_a, "agent-a1", strategy_id, revision_id).status_code == 200
    response = _dispatch(wallet_client, owner_a, "agent-a1")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "CONFIRMED" and body["wallet_id"]
    assert len(provider.created) == 1
    assert provider.lookups == [body["wallet_id"]]
    assert "CONFIRMED" in pg.psql("select state from wallet_setups where agent_id = 'agent-a1'")
    events = pg.psql("select string_agg(event_type, ',' order by sequence) from wallet_setup_events")
    assert events == "PREPARED,DISPATCH_INTENT,RESULT_RETURNED,WALLET_BOUND"


def test_replay_and_new_request_key_do_not_create_again(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    first = _prepare(wallet_client, owner_a, "agent-a1", strategy_id, revision_id, key="key-1").json()
    confirmed = _dispatch(wallet_client, owner_a, "agent-a1").json()
    assert confirmed["state"] == "CONFIRMED"

    replay = _dispatch(wallet_client, owner_a, "agent-a1").json()
    assert replay["state"] == "CONFIRMED" and replay["wallet_id"] == confirmed["wallet_id"]

    again = _prepare(wallet_client, owner_a, "agent-a1", strategy_id, revision_id, key="different-key").json()
    assert again["setup_id"] == first["setup_id"]
    after = _dispatch(wallet_client, owner_a, "agent-a1").json()
    assert after["wallet_id"] == confirmed["wallet_id"]
    assert len(provider.created) == 1
    assert pg.psql("select count(*) from wallet_setups") == "1"


def test_second_agent_gets_a_distinct_wallet(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    wallets = []
    for agent in ("agent-a1", "agent-a2"):
        assert _prepare(wallet_client, owner_a, agent, strategy_id, revision_id, key=f"key-{agent}").status_code == 200
        body = _dispatch(wallet_client, owner_a, agent).json()
        assert body["state"] == "CONFIRMED"
        wallets.append(body["wallet_id"])
    assert wallets[0] != wallets[1]
    assert len(provider.created) == 2
    assert pg.psql("select count(*) from wallet_setups where state = 'CONFIRMED'") == "2"


def test_pre_dispatch_cancel_causes_zero_creation_calls(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    _prepare(wallet_client, owner_a, "agent-c", strategy_id, revision_id)
    cancelled = wallet_client.post("/v1/wallet-setup/agents/agent-c/cancel", headers=owner_a)
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["state"] == "FAILED" and body["reason"] == "CANCELLED_BEFORE_DISPATCH"
    assert body["cancellation_intent"] == "REQUESTED_BEFORE_DISPATCH"

    dispatched = _dispatch(wallet_client, owner_a, "agent-c").json()
    assert dispatched["state"] == "FAILED"
    assert provider.created == []
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'DISPATCH_INTENT'") == "0"


def test_lost_response_stays_unknown_and_never_retries_creation(wallet_client, owner_a, provider, pg):
    provider.lose_response = True
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    _prepare(wallet_client, owner_a, "agent-lost", strategy_id, revision_id)
    first = _dispatch(wallet_client, owner_a, "agent-lost").json()
    assert first["state"] == "UNKNOWN" and first["reason"] == "RESPONSE_LOST"
    assert len(provider.created) == 1

    resumed = wallet_client.post("/v1/wallet-setup/agents/agent-lost/resume", headers=owner_a).json()
    assert resumed["state"] == "UNKNOWN" and resumed["reason"] == "RECONCILE_NO_EXACT_ID"
    again = wallet_client.post("/v1/wallet-setup/agents/agent-lost/resume", headers=owner_a).json()
    assert again["reason"] == "RECONCILE_NO_EXACT_ID"
    assert len(provider.created) == 1
    assert pg.psql("select count(*) from wallet_setups where wallet_id is not null") == "0"


def test_wrong_owner_evidence_stays_unknown(wallet_client, owner_a, provider, pg):
    import uuid
    provider.create_result = WalletEvidence(wallet_id="wallet-bad", owner_id=uuid.uuid4(), chain_type="ethereum",
                                            address="0x" + "a" * 40)
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    _prepare(wallet_client, owner_a, "agent-bad", strategy_id, revision_id)
    body = _dispatch(wallet_client, owner_a, "agent-bad").json()
    assert body["state"] == "UNKNOWN" and body["reason"] == "RECONCILE_WRONG_IDENTITY"
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-bad'") == "t"


def test_conflicting_wallet_does_not_overwrite_confirmed_binding(wallet_client, owner_a, provider, pg):
    import uuid
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = uuid.UUID(helpers.owner_user_id(wallet_client, owner_a))
    _prepare(wallet_client, owner_a, "agent-a1", strategy_id, revision_id, key="key-a1")
    first = _dispatch(wallet_client, owner_a, "agent-a1").json()
    wallet_id = first["wallet_id"]

    provider.create_result = WalletEvidence(wallet_id=wallet_id, owner_id=owner_id, chain_type="ethereum",
                                            address="0x" + format(1, "040x"))
    _prepare(wallet_client, owner_a, "agent-a2", strategy_id, revision_id, key="key-a2")
    conflict = _dispatch(wallet_client, owner_a, "agent-a2").json()
    assert conflict["state"] == "UNKNOWN" and conflict["reason"] == "CONFLICTING_WALLET"

    assert pg.psql("select wallet_id from wallet_setups where agent_id = 'agent-a1'") == wallet_id
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-a2'") == "t"
    assert pg.psql("select count(*) from wallet_setup_denials where code = 'SAME_OWNER_CROSS_AGENT'") == "1"


def test_creation_creates_no_funding_signer_or_position_rows(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    before = pg.psql("select count(*) from records")
    _prepare(wallet_client, owner_a, "agent-plain", strategy_id, revision_id)
    body = _dispatch(wallet_client, owner_a, "agent-plain").json()
    assert body["state"] == "CONFIRMED"
    assert pg.psql("select count(*) from records") == before
    assert pg.psql("select count(*) from wallet_setups") == "1"
    assert pg.psql("select count(*) from wallet_setups where wallet_id is not null") == "1"
