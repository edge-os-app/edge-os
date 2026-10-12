"""IC04 owner-linked browser completion: a browser-reported wallet id binds only after independent lookup.

Seam: authenticated completion route → saved setup row and events. The authored fake provider is the only
lookup source; nothing is created on the server for this path.
"""

from __future__ import annotations

import uuid

import helpers

from edge_os_api.wallet_setup.provider import WalletEvidence

NETWORK = 10143


def _prepared(wallet_client, headers, agent_id):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, headers)
    response = wallet_client.post(f"/v1/wallet-setup/agents/{agent_id}/prepare", headers=headers, json={
        "network_id": NETWORK, "strategy_id": strategy_id, "strategy_revision_id": revision_id,
        "request_key": f"key-{agent_id}"})
    assert response.status_code == 200, response.text
    return strategy_id, revision_id


def _complete(wallet_client, headers, agent_id, wallet_id):
    return wallet_client.post(f"/v1/wallet-setup/agents/{agent_id}/complete", headers=headers,
                              json={"wallet_id": wallet_id})


def _browser_wallet(provider, owner_id, wallet_id="browser-wallet-1", address="0x" + "ab" * 20):
    evidence = WalletEvidence(wallet_id=wallet_id, owner_id=uuid.UUID(owner_id), chain_type="ethereum",
                              address=address)
    provider.wallets[wallet_id] = evidence
    return evidence


def test_browser_wallet_binds_after_independent_lookup_without_server_creation(wallet_client, owner_a, provider, pg):
    _prepared(wallet_client, owner_a, "browser-a")
    wallet = _browser_wallet(provider, helpers.owner_user_id(wallet_client, owner_a))
    response = _complete(wallet_client, owner_a, "browser-a", wallet.wallet_id)
    assert response.status_code == 200, response.text
    assert (response.json()["state"], response.json()["wallet_id"]) == ("CONFIRMED", wallet.wallet_id)
    assert provider.created == [] and provider.lookups == [wallet.wallet_id]
    events = pg.psql("select string_agg(event_type, ',' order by sequence) from wallet_setup_events")
    assert events == "PREPARED,DISPATCH_INTENT,RESULT_RETURNED,WALLET_BOUND"
    # A repeated completion is idempotent; a different late wallet never replaces the bound one.
    assert _complete(wallet_client, owner_a, "browser-a", wallet.wallet_id).json()["wallet_id"] == wallet.wallet_id
    late = _complete(wallet_client, owner_a, "browser-a", "browser-wallet-other")
    assert late.json()["wallet_id"] == wallet.wallet_id
    assert "CONFLICTING_RESULT" in pg.psql("select string_agg(code, ',') from wallet_setup_denials")


def test_unknown_or_foreign_wallet_stays_unknown_and_grants_nothing(wallet_client, owner_a, owner_b, provider, pg):
    _prepared(wallet_client, owner_a, "browser-unknown")
    missing = _complete(wallet_client, owner_a, "browser-unknown", "never-created")
    assert (missing.json()["state"], missing.json()["reason"]) == ("UNKNOWN", "RECONCILE_NO_MATCH")
    assert missing.json()["wallet_id"] is None

    _prepared(wallet_client, owner_b, "browser-b")
    owner_a_wallet = _browser_wallet(provider, helpers.owner_user_id(wallet_client, owner_a), "owner-a-wallet")
    foreign = _complete(wallet_client, owner_b, "browser-b", owner_a_wallet.wallet_id)
    assert (foreign.json()["state"], foreign.json()["reason"]) == ("UNKNOWN", "RECONCILE_WRONG_IDENTITY")
    assert foreign.json()["wallet_id"] is None
    # Owner B cannot complete owner A's setup at all.
    assert _complete(wallet_client, owner_b, "browser-unknown", owner_a_wallet.wallet_id).status_code == 404


def test_late_completion_reconciles_an_unknown_setup_and_cancel_before_dispatch_refuses(
        wallet_client, owner_a, provider, pg):
    _prepared(wallet_client, owner_a, "browser-late")
    assert _complete(wallet_client, owner_a, "browser-late", "late-wallet").json()["state"] == "UNKNOWN"
    late = _browser_wallet(provider, helpers.owner_user_id(wallet_client, owner_a), "late-wallet")
    resolved = _complete(wallet_client, owner_a, "browser-late", late.wallet_id)
    assert (resolved.json()["state"], resolved.json()["wallet_id"]) == ("CONFIRMED", late.wallet_id)

    _prepared(wallet_client, owner_a, "browser-cancel")
    wallet_client.post("/v1/wallet-setup/agents/browser-cancel/cancel", headers=owner_a)
    cancelled_wallet = _browser_wallet(provider, helpers.owner_user_id(wallet_client, owner_a), "cancel-wallet")
    refused = _complete(wallet_client, owner_a, "browser-cancel", cancelled_wallet.wallet_id)
    assert (refused.json()["state"], refused.json()["wallet_id"]) == ("FAILED", None)
    assert "LATE_RESULT_AFTER_CANCEL" in pg.psql("select string_agg(code, ',') from wallet_setup_denials")


def test_one_wallet_cannot_bind_two_agents_and_bodies_cannot_assert_identity(wallet_client, owner_a, provider):
    _prepared(wallet_client, owner_a, "browser-first")
    wallet = _browser_wallet(provider, helpers.owner_user_id(wallet_client, owner_a), "shared-wallet")
    assert _complete(wallet_client, owner_a, "browser-first", wallet.wallet_id).json()["state"] == "CONFIRMED"
    _prepared(wallet_client, owner_a, "browser-second")
    second = _complete(wallet_client, owner_a, "browser-second", wallet.wallet_id)
    assert (second.json()["state"], second.json()["reason"]) == ("UNKNOWN", "CONFLICTING_WALLET")
    for body in ({"wallet_id": "w", "owner_id": str(uuid.uuid4())}, {"wallet_id": ""}, {"wallet_id": 5},
                 {"wallet_id": "w", "state": "CONFIRMED"}):
        assert wallet_client.post("/v1/wallet-setup/agents/browser-second/complete", headers=owner_a,
                                  json=body).status_code == 422


def test_concurrent_completions_bind_exactly_one_wallet(wallet_client, owner_a, provider, pg):
    import threading
    _prepared(wallet_client, owner_a, "browser-race")
    owner = helpers.owner_user_id(wallet_client, owner_a)
    wallets = [_browser_wallet(provider, owner, f"race-wallet-{index}", "0x" + f"{index:02x}" * 20)
               for index in range(4)]
    barrier, results = threading.Barrier(4), [None] * 4

    def complete(index):
        barrier.wait()
        results[index] = _complete(wallet_client, owner_a, "browser-race", wallets[index].wallet_id).json()
    threads = [threading.Thread(target=complete, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    saved = pg.psql("select wallet_id from wallet_setups where agent_id = 'browser-race'")
    assert saved in {wallet.wallet_id for wallet in wallets}
    assert {result["wallet_id"] for result in results if result["state"] == "CONFIRMED"} == {saved}
    assert pg.psql("select count(*) from wallet_setup_events e join wallet_setups s using (setup_id) "
                   "where s.agent_id = 'browser-race' and e.event_type = 'WALLET_BOUND'") == "1"
