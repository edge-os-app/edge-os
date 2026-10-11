"""Owner request seam: persistence, idempotency, changed-reuse conflict and owner isolation."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from edge_os_api.revocation.types import RemovalError

from revocation._support import (
    AGENT_A,
    AGENT_B,
    NETWORK,
    OWNER_A,
    OWNER_B,
    SIGNER_OTHER,
    WALLET_A,
    WALLET_B,
    removal_request,
    seed_wallet_binding,
)


def test_request_requires_a_saved_wallet_binding(revocation_engine, removal_service):
    with pytest.raises(RemovalError):
        removal_service.request_removal(OWNER_A, removal_request())


def test_expected_wallet_mismatch_is_refused(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    with pytest.raises(RemovalError):
        removal_service.request_removal(OWNER_A, removal_request(expected_wallet_id=WALLET_B))


def test_request_persists_the_resolved_binding_before_any_effect(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    view = removal_service.request_removal(OWNER_A, removal_request())
    assert view.state == "REQUESTED"
    assert (view.agent_id, view.wallet_id, view.network_id) == (AGENT_A, WALLET_A, NETWORK)
    assert view.signer_identity == "signer-a"
    assert view.request_provenance["source"] == "SYNTHETIC_AUTHORED"
    with revocation_engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT request_key, wallet_id, network_id FROM revocation_local.removal_requests")).fetchall()
        states = connection.execute(text(
            "SELECT state, reason FROM revocation_local.removal_states")).fetchall()
    assert rows == [("req-1", WALLET_A, NETWORK)]
    assert states == [("REQUESTED", "OWNER_REQUESTED")]


def test_exact_repeated_request_is_idempotent(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    first = removal_service.request_removal(OWNER_A, removal_request())
    second = removal_service.request_removal(OWNER_A, removal_request())
    assert first.request_id == second.request_id
    assert len(removal_service.read_removal(OWNER_A)) == 1


def test_changed_observation_key_for_the_same_identity_conflicts(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    removal_service.request_removal(OWNER_A, removal_request(request_key="req-1"))
    with pytest.raises(RemovalError):
        removal_service.request_removal(OWNER_A, removal_request(request_key="req-2"))
    assert len(removal_service.read_removal(OWNER_A)) == 1


def test_changed_request_signer_is_refused(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    removal_service.request_removal(OWNER_A, removal_request(request_key="req-1"))
    with pytest.raises(RemovalError):
        removal_service.request_removal(OWNER_A, removal_request(request_key="req-1",
                                                                 signer_identity=SIGNER_OTHER))
    assert removal_service.read_removal(OWNER_A)[0].signer_identity == "signer-a"


def test_changed_request_reason_is_refused(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    removal_service.request_removal(OWNER_A, removal_request(request_key="req-1", reason="owner revoked"))
    with pytest.raises(RemovalError):
        removal_service.request_removal(OWNER_A, removal_request(request_key="req-1", reason="different reason"))


def test_a_foreign_owner_sees_only_their_own_records(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    seed_wallet_binding(revocation_engine, OWNER_B, agent_id=AGENT_B, wallet_id=WALLET_B)
    a_view = removal_service.request_removal(OWNER_A, removal_request())
    b_view = removal_service.request_removal(
        OWNER_B, removal_request(request_key="req-b", agent_id=AGENT_B))
    assert b_view.request_id != a_view.request_id
    assert [view.request_id for view in removal_service.read_removal(OWNER_B)] == [b_view.request_id]
    assert [view.request_id for view in removal_service.read_removal(OWNER_A)] == [a_view.request_id]


def test_read_exact_repeated_read_is_stable(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    removal_service.request_removal(OWNER_A, removal_request())
    first = removal_service.read_removal(OWNER_A)
    second = removal_service.read_removal(OWNER_A)
    assert first == second
