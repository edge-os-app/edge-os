"""Durable persistence across a real process boundary and a cross-process request race."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from revocation._support import (
    AGENT_A,
    NETWORK,
    OWNER_A,
    WALLET_A,
    observation,
    removal_request,
    request_probe,
    restart_probe,
    seed_wallet_binding,
)


def test_confirmed_removal_persists_to_a_new_process(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    view = removal_service.request_removal(OWNER_A, removal_request())
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="CONFIRMED"))
    result = restart_probe(revocation_engine.url, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A,
                           network_id=NETWORK)
    assert result["denial"] == ["REMOVAL_CONFIRMED"]
    assert result["states"] == ["CONFIRMED"]
    # A restart re-request is idempotent and creates no new identity.
    again = removal_service.request_removal(OWNER_A, removal_request())
    assert again.request_id == view.request_id
    assert again.state == "CONFIRMED"
    with revocation_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM revocation_local.removal_requests")).scalar_one() == 1


def test_cross_process_requests_are_serialized_and_idempotent(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    request = removal_request(request_key="race-1")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: request_probe(revocation_engine.url, OWNER_A, request), range(2)))
    assert all(result["ok"] for result in results), results
    assert len({result["request_id"] for result in results}) == 1
    with revocation_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM revocation_local.removal_requests")).scalar_one() == 1
        assert connection.execute(text(
            "SELECT count(*) FROM revocation_local.removal_states")).scalar_one() == 1


def test_pending_state_is_readable_from_a_fresh_factory(revocation_engine, revocation_factory, removal_service):
    from edge_os_api.revocation.removal_service import RemovalService

    seed_wallet_binding(revocation_engine, OWNER_A)
    view = removal_service.request_removal(OWNER_A, removal_request())
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="UNKNOWN"))
    fresh = RemovalService(revocation_factory)
    assert [record.state for record in fresh.read_removal(OWNER_A)] == ["UNKNOWN"]
