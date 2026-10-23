"""WALLET_BOUND evidence: the server wallet adds only its release binding hash.

The fixture and unavailable provider evidence keeps its exact previous shape. These controls read the
saved event for a dispatch through the real wallet-setup service; they use no provider network call.
"""

from __future__ import annotations

import json
import uuid

import pytest

import helpers

from edge_os_api.wallet_setup.provider import WalletEvidence
from edge_os_api.wallet_setup.service import _evidence_dict

NETWORK = 10143
HASH = "ab" * 32
ADDRESS = "0x" + "a" * 40


def test_evidence_projection_is_additive_and_byte_identical_for_existing_modes():
    owner = uuid.uuid4()
    plain = WalletEvidence(wallet_id="wallet-plain", owner_id=owner, chain_type="ethereum", address=ADDRESS)
    assert _evidence_dict(plain) == {"owner_id": str(owner), "chain_type": "ethereum", "address": ADDRESS}
    server = WalletEvidence(wallet_id="wallet-server", owner_id=owner, chain_type="ethereum", address=ADDRESS,
                            release_binding_sha256=HASH)
    assert _evidence_dict(server) == {"owner_id": str(owner), "chain_type": "ethereum", "address": ADDRESS,
                                      "release_binding_sha256": HASH}


@pytest.mark.parametrize("bad", ["", "ab", "AB" * 32, "0x" + "ab" * 32, "g" * 64, 7, object()])
def test_wallet_evidence_refuses_a_malformed_binding_hash(bad):
    with pytest.raises((TypeError, ValueError)):
        WalletEvidence(wallet_id="wallet-server", owner_id=uuid.uuid4(), chain_type="ethereum", address=ADDRESS,
                       release_binding_sha256=bad)


def test_server_wallet_dispatch_saves_the_release_binding_hash(wallet_client, owner_a, provider, pg):
    strategy_id, revision_id = helpers.publish_revision(wallet_client, owner_a)
    owner_id = uuid.UUID(helpers.owner_user_id(wallet_client, owner_a))
    evidence = WalletEvidence(wallet_id="wallet-server", owner_id=owner_id, chain_type="ethereum",
                              address=ADDRESS, release_binding_sha256=HASH)
    provider.create_result = evidence
    provider.wallets[evidence.wallet_id] = evidence
    prepared = wallet_client.post(
        "/v1/wallet-setup/agents/agent-server/prepare",
        json={"network_id": NETWORK, "strategy_id": strategy_id, "strategy_revision_id": revision_id,
              "request_key": "server-key"}, headers=owner_a)
    assert prepared.status_code == 200, prepared.text
    dispatched = wallet_client.post("/v1/wallet-setup/agents/agent-server/dispatch", headers=owner_a)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["state"] == "CONFIRMED"
    assert dispatched.json()["wallet_id"] == evidence.wallet_id
    content = json.loads(pg.psql(
        "select content::text from wallet_setup_events where event_type = 'WALLET_BOUND'"))
    assert content["wallet_id"] == evidence.wallet_id
    assert content["evidence"] == {"owner_id": str(owner_id), "chain_type": "ethereum", "address": ADDRESS,
                                   "release_binding_sha256": HASH}
