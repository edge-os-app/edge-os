"""Authorization and identity controls for local wallet setup.

Positive controls use real signed test tokens through the production verifier. Negative controls
cover missing credentials, cross-owner access, body-supplied owners and changed setup identity.
"""

from __future__ import annotations

import uuid

import helpers

NETWORK = 10143


def _prepare_body(strategy_id: str, revision_id: str, *, network: int = NETWORK, key: str = "key-1") -> dict:
    return {"network_id": network, "strategy_id": strategy_id, "strategy_revision_id": revision_id,
            "request_key": key}


def test_authenticated_positive_and_missing_token_negative(wallet_client, owner_a):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    response = wallet_client.post("/v1/wallet-setup/agents/agent-a1/prepare",
                                  json=_prepare_body(strategy_id, revision_id), headers=owner_a)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "REQUESTED"

    unauth = wallet_client.post("/v1/wallet-setup/agents/agent-a1/prepare",
                                json=_prepare_body(strategy_id, revision_id))
    assert unauth.status_code == 401 and unauth.json()["code"] == "auth_required"


def test_cross_owner_setup_is_not_found(wallet_client, owner_a, owner_b):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    wallet_client.post("/v1/wallet-setup/agents/agent-a1/prepare",
                       json=_prepare_body(strategy_id, revision_id), headers=owner_a)

    foreign = wallet_client.get("/v1/wallet-setup/agents/agent-a1", headers=owner_b)
    absent = wallet_client.get(f"/v1/wallet-setup/agents/agent-{uuid.uuid4().hex[:8]}", headers=owner_b)
    assert foreign.status_code == 404 and absent.status_code == 404
    f, a = foreign.json(), absent.json()
    f.pop("operation_id"), a.pop("operation_id")
    assert f == a

    attack = wallet_client.post("/v1/wallet-setup/agents/agent-a1/dispatch", headers=owner_b)
    assert attack.status_code == 404


def test_body_supplied_owner_is_rejected_at_any_depth(wallet_client, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    before = pg.psql("select count(*) from wallet_setups")
    body = {**_prepare_body(strategy_id, revision_id), "owner_id": str(uuid.uuid4())}
    response = wallet_client.post("/v1/wallet-setup/agents/agent-a1/prepare", json=body, headers=owner_a)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert pg.psql("select count(*) from wallet_setups") == before


def test_foreign_or_absent_revision_is_not_found(wallet_client, owner_a, owner_b, pg):
    other_strategy_id, other_revision_id = helpers.publish_revision(wallet_client, owner_b)
    random_revision = str(uuid.uuid4())
    for revision in (other_revision_id, random_revision):
        response = wallet_client.post("/v1/wallet-setup/agents/agent-a1/prepare",
                                      json=_prepare_body(other_strategy_id, revision), headers=owner_a)
        assert response.status_code == 404, response.text
    assert pg.psql("select count(*) from wallet_setups") == "0"


def test_changed_setup_identity_is_conflict_and_changes_nothing(wallet_client, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    first = wallet_client.post("/v1/wallet-setup/agents/agent-a1/prepare",
                               json=_prepare_body(strategy_id, revision_id, key="key-1"), headers=owner_a)
    assert first.status_code == 200
    saved_revision = first.json()["strategy_revision_id"]

    changed_network = wallet_client.post("/v1/wallet-setup/agents/agent-a1/prepare",
                                         json=_prepare_body(strategy_id, revision_id, network=143, key="key-2"),
                                         headers=owner_a)
    assert changed_network.status_code == 409 and changed_network.json()["code"] == "changed_setup_identity"

    other_strategy_id, other_revision_id = helpers.publish_revision(wallet_client, owner_a)
    changed_revision = wallet_client.post(
        "/v1/wallet-setup/agents/agent-a1/prepare",
        json=_prepare_body(other_strategy_id, other_revision_id, key="key-3"), headers=owner_a)
    assert changed_revision.status_code == 409 and changed_revision.json()["code"] == "changed_setup_identity"

    saved = pg.psql("select strategy_revision_id, state from wallet_setups where agent_id = 'agent-a1'")
    assert saved_revision in saved and "REQUESTED" in saved
    assert pg.psql("select count(*) from wallet_setups") == "1"
    assert pg.psql("select count(*) from wallet_setup_denials where code = 'CHANGED_SETUP_IDENTITY'") == "2"


def test_research_revision_is_usable_without_any_wallet(wallet_client, owner_a, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    fetched = wallet_client.get(f"/v1/strategies/{strategy_id}/revisions/{revision_id}", headers=owner_a)
    assert fetched.status_code == 200
    assert pg.psql("select count(*) from wallet_setups") == "0"
