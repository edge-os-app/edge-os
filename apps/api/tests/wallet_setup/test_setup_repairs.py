"""Gate repair regressions G1-G4 and G6.

G1: resume must validate the retained result against the current lookup with the same identity rules.
G2: a concurrent valid prepare must return the same setup, not an uncaught uniqueness failure.
G3: malformed creation or lookup results must become durable UNKNOWN, never a 500.
G4: the mutation seams must reject spoofed or changed identity assertions before any mutation or call.
G6: a malformed field inside a WalletEvidence result must be rejected before the event write and
never leave the setup PENDING without a reason or trigger a second creation.
"""

from __future__ import annotations

import json
import time
import uuid

from sqlalchemy import text as sql_text

import helpers

from edge_os_api.wallet_setup.provider import WalletEvidence, WalletProviderUnavailable

NETWORK = 10143


def _prepare(wallet_client, headers, agent_id, strategy_id, revision_id):
    return wallet_client.post(
        f"/v1/wallet-setup/agents/{agent_id}/prepare",
        json={"network_id": NETWORK, "strategy_id": strategy_id, "strategy_revision_id": revision_id,
              "request_key": f"key-{agent_id}"}, headers=headers)


def _dispatch(wallet_client, headers, agent_id):
    return wallet_client.post(f"/v1/wallet-setup/agents/{agent_id}/dispatch", headers=headers)


def _digest(pg) -> str:
    return pg.psql("select coalesce(md5(string_agg(setup_id::text || state || coalesce(wallet_id, ''), ',' "
                   "order by setup_id)), '') from wallet_setups")


def _retain_unknown_result(wallet_client, owner_a, provider, agent_id, strategy_id, revision_id, retained):
    """Dispatch once so a RESULT_RETURNED event is retained, but leave the setup UNKNOWN (lookup fails)."""
    assert _prepare(wallet_client, owner_a, agent_id, strategy_id, revision_id).status_code == 200
    provider.create_result = retained
    provider.on_lookup = lambda _wallet_id: (_ for _ in ()).throw(WalletProviderUnavailable())
    assert _dispatch(wallet_client, owner_a, agent_id).json()["state"] == "UNKNOWN"
    provider.on_lookup = None


def test_resume_rejects_changed_retained_address(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = uuid.UUID(helpers.owner_user_id(wallet_client, owner_a))
    assert _prepare(wallet_client, owner_a, "agent-addr", strategy_id, revision_id).status_code == 200
    provider.create_result = WalletEvidence(wallet_id="wallet-addr", owner_id=owner_id, chain_type="ethereum",
                                            address="0x" + "a" * 40)
    provider.on_lookup = lambda _wallet_id: (_ for _ in ()).throw(WalletProviderUnavailable())
    first = _dispatch(wallet_client, owner_a, "agent-addr").json()
    assert first["state"] == "UNKNOWN"
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'RESULT_RETURNED'") == "1"

    provider.on_lookup = None
    provider.wallets["wallet-addr"] = WalletEvidence(wallet_id="wallet-addr", owner_id=owner_id,
                                                     chain_type="ethereum", address="0x" + "b" * 40)
    resumed = wallet_client.post("/v1/wallet-setup/agents/agent-addr/resume", headers=owner_a).json()
    assert resumed["state"] == "UNKNOWN" and resumed["reason"] == "RECONCILE_WRONG_IDENTITY"
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-addr'") == "t"


def test_crash_after_result_resume_rejects_changed_address(wallet_client, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = helpers.owner_user_id(wallet_client, owner_a)
    assert _prepare(wallet_client, owner_a, "agent-addr2", strategy_id, revision_id).status_code == 200
    crashed = helpers.start_driver(pg.url, owner_id, "agent-addr2", strategy_id, revision_id, "crash_at_verify")
    assert crashed.wait(timeout=90) == 8
    retained = pg.psql("select content->>'wallet_id' from wallet_setup_events where event_type = 'RESULT_RETURNED' "
                       "order by sequence desc limit 1")
    assert retained
    resumed = helpers.start_driver(pg.url, owner_id, "agent-addr2", strategy_id, revision_id, "resume",
                                   "--seed-wallet", retained, "--seed-address", "0x" + "b" * 40)
    out, err = resumed.communicate(timeout=90)
    assert resumed.returncode == 0, err
    body = json.loads(out.strip().splitlines()[-1])
    assert body["state"] == "UNKNOWN" and body["reason"] == "RECONCILE_WRONG_IDENTITY"
    assert body["invoked"] is False
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-addr2'") == "t"


def test_malformed_creation_becomes_unknown(wallet_client, owner_a, provider, pg):
    provider.create_returns_malformed = True
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    assert _prepare(wallet_client, owner_a, "agent-malformed-create", strategy_id, revision_id).status_code == 200
    body = _dispatch(wallet_client, owner_a, "agent-malformed-create").json()
    assert body["state"] == "UNKNOWN" and body["reason"] == "MALFORMED_RESULT"
    assert len(provider.created) == 1
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'DISPATCH_INTENT'") == "1"
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-malformed-create'") == "t"


def test_malformed_evidence_field_becomes_unknown_and_never_recreates(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = uuid.UUID(helpers.owner_user_id(wallet_client, owner_a))
    provider.create_result = WalletEvidence(wallet_id="gate-malformed-fields", owner_id=owner_id,
                                            chain_type="ethereum", address=object())
    assert _prepare(wallet_client, owner_a, "agent-malformed-field", strategy_id, revision_id).status_code == 200
    body = _dispatch(wallet_client, owner_a, "agent-malformed-field").json()
    assert body["state"] == "UNKNOWN" and body["reason"] == "MALFORMED_RESULT"
    assert len(provider.created) == 1
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'DISPATCH_INTENT'") == "1"
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'RESULT_RETURNED'") == "0"
    for _ in range(2):
        resumed = wallet_client.post("/v1/wallet-setup/agents/agent-malformed-field/resume", headers=owner_a).json()
        assert resumed["state"] == "UNKNOWN"
    assert len(provider.created) == 1
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-malformed-field'") == "t"


def test_unstorable_evidence_field_becomes_unknown(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = uuid.UUID(helpers.owner_user_id(wallet_client, owner_a))
    provider.create_result = WalletEvidence(wallet_id="wallet-nul", owner_id=owner_id, chain_type="ethereum",
                                            address="0x\x00bad")
    assert _prepare(wallet_client, owner_a, "agent-nul", strategy_id, revision_id).status_code == 200
    body = _dispatch(wallet_client, owner_a, "agent-nul").json()
    assert body["state"] == "UNKNOWN" and body["reason"] == "MALFORMED_RESULT"
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'RESULT_RETURNED'") == "0"
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-nul'") == "t"


def test_malformed_lookup_evidence_field_becomes_unknown(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = uuid.UUID(helpers.owner_user_id(wallet_client, owner_a))
    retained = WalletEvidence("wallet-field", owner_id, "ethereum", "0x" + "a" * 40)
    _retain_unknown_result(wallet_client, owner_a, provider, "agent-mlf", strategy_id, revision_id, retained)
    provider.wallets["wallet-field"] = WalletEvidence("wallet-field", owner_id, "ethereum", address=object())
    provider.create_result = None
    resumed = wallet_client.post("/v1/wallet-setup/agents/agent-mlf/resume", headers=owner_a).json()
    assert resumed["state"] == "UNKNOWN" and resumed["reason"] == "RECONCILE_NO_MATCH"
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-mlf'") == "t"


def test_malformed_lookup_becomes_unknown(wallet_client, owner_a, provider, pg):
    provider.lookup_returns_malformed = True
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    assert _prepare(wallet_client, owner_a, "agent-malformed-lookup", strategy_id, revision_id).status_code == 200
    body = _dispatch(wallet_client, owner_a, "agent-malformed-lookup").json()
    assert body["state"] == "UNKNOWN" and body["reason"] == "RECONCILE_NO_MATCH"
    assert pg.psql("select count(*) from wallet_setup_events where event_type = 'RESULT_RETURNED'") == "1"
    assert pg.psql("select wallet_id is null from wallet_setups where agent_id = 'agent-malformed-lookup'") == "t"


def test_resume_rejects_wrong_owner_or_chain(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = uuid.UUID(helpers.owner_user_id(wallet_client, owner_a))
    other_owner = uuid.uuid4()
    retained = WalletEvidence("wallet-oc", owner_id, "ethereum", "0x" + "a" * 40)
    cases = {"owner": WalletEvidence("wallet-oc", other_owner, "ethereum", "0x" + "a" * 40),
             "chain": WalletEvidence("wallet-oc", owner_id, "solana", "0x" + "a" * 40)}
    for name, evidence in cases.items():
        agent = f"agent-oc-{name}"
        provider.create_result = None
        _retain_unknown_result(wallet_client, owner_a, provider, agent, strategy_id, revision_id, retained)
        provider.wallets[evidence.wallet_id] = evidence
        resumed = wallet_client.post(f"/v1/wallet-setup/agents/{agent}/resume", headers=owner_a).json()
        assert resumed["state"] == "UNKNOWN" and resumed["reason"] == "RECONCILE_WRONG_IDENTITY", name
        assert pg.psql(f"select wallet_id is null from wallet_setups where agent_id = '{agent}'") == "t"


def test_mutation_handlers_reject_each_identity_field(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    fields = {"owner_id": str(uuid.uuid4()), "wallet_id": "foreign-wallet", "setup_id": str(uuid.uuid4()),
              "network_id": 143, "strategy_revision_id": str(uuid.uuid4())}
    for operation in ("dispatch", "resume", "cancel"):
        agent = f"agent-g4-{operation}"
        assert _prepare(wallet_client, owner_a, agent, strategy_id, revision_id).status_code == 200
        before = _digest(pg)
        for name, value in fields.items():
            response = wallet_client.post(f"/v1/wallet-setup/agents/{agent}/{operation}", json={name: value},
                                          headers=owner_a)
            assert response.status_code == 422, (name, response.text)
            assert response.json()["code"] == "validation_error"
            assert _digest(pg) == before, name
    assert provider.created == []
    assert pg.psql("select count(*) from wallet_setups where wallet_id is not null") == "0"


def test_concurrent_prepare_returns_same_setup(wallet_client, owner_a, wallet_schema, pg, tmp_path):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = helpers.owner_user_id(wallet_client, owner_a)
    with wallet_schema.begin() as connection:
        connection.execute(sql_text(
            "create or replace function wallet_setup_slow() returns trigger as $$ "
            "begin perform pg_sleep(0.6); return new; end $$ language plpgsql"))
        connection.execute(sql_text(
            "create trigger wallet_setup_slow before insert on wallet_setups "
            "for each row execute function wallet_setup_slow()"))
    try:
        start_file = tmp_path / "go"
        first = helpers.start_driver(pg.url, owner_id, "agent-raceprep", strategy_id, revision_id, "prepare_race",
                                     "--start-file", str(start_file))
        second = helpers.start_driver(pg.url, owner_id, "agent-raceprep", strategy_id, revision_id, "prepare_race",
                                      "--start-file", str(start_file))
        time.sleep(0.5)
        start_file.write_text("go")
        out1, err1 = first.communicate(timeout=90)
        out2, err2 = second.communicate(timeout=90)
        assert first.returncode == 0, err1
        assert second.returncode == 0, err2
        setup_ids = {json.loads(out.strip().splitlines()[-1])["setup_id"] for out in (out1, out2)}
        assert len(setup_ids) == 1
    finally:
        with wallet_schema.begin() as connection:
            connection.execute(sql_text("drop trigger if exists wallet_setup_slow on wallet_setups"))
            connection.execute(sql_text("drop function if exists wallet_setup_slow()"))
    assert pg.psql("select count(*) from wallet_setups") == "1"
