"""A removal request and confirmed removal leave every accepted-module row unchanged."""

from __future__ import annotations

from sqlalchemy import text

from edge_os_api.admission.service import AdmissionService

from revocation._support import (
    AGENT_A,
    AGENT_B,
    NETWORK,
    OWNER_A,
    OWNER_B,
    WALLET_A,
    WALLET_B,
    observation,
    removal_request,
    seed_admission_unknown,
    seed_funding_and_consent,
    seed_stop,
    seed_wallet_binding,
    snapshot,
)


def test_removal_operations_leave_accepted_rows_unchanged(revocation_engine, removal_service, session):
    seed_funding_and_consent(revocation_engine, OWNER_A)
    seed_wallet_binding(revocation_engine, OWNER_B, agent_id=AGENT_B, wallet_id=WALLET_B)
    seed_admission_unknown(revocation_engine, OWNER_A)
    seed_stop(revocation_engine, OWNER_A)
    before = snapshot(revocation_engine)
    assert before["revocation_local.removal_requests"] == []
    assert before["revocation_local.removal_observations"] == []
    assert before["revocation_local.removal_states"] == []

    view = removal_service.request_removal(OWNER_A, removal_request())
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="PENDING"))
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o2",
                                                   observed_state="CONFIRMED",
                                                   observed_at="2026-01-01T00:17:00Z"))
    assert removal_service.submission_denial(session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A,
                                             network_id=NETWORK) == ["REMOVAL_CONFIRMED"]

    after = snapshot(revocation_engine)
    original = {key: value for key, value in before.items() if not key.startswith("revocation_local.")}
    preserved = {key: value for key, value in after.items() if not key.startswith("revocation_local.")}
    assert preserved == original
    # The accepted schemas are present and non-empty, so the equality is meaningful.
    assert any(key.startswith("admission_local.") and value for key, value in preserved.items())
    assert any(key.startswith("stops_local.") and value for key, value in preserved.items())
    assert any(key.startswith("funding_local.") and value for key, value in preserved.items())
    assert any(key.startswith("consent_local.") and value for key, value in preserved.items())
    assert preserved["public.wallet_setups"]


def test_pending_action_and_reservations_survive_a_confirmed_removal(revocation_engine, removal_service, session):
    seed_wallet_binding(revocation_engine, OWNER_A)
    action_id = seed_admission_unknown(revocation_engine, OWNER_A)
    view = removal_service.request_removal(OWNER_A, removal_request())
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="CONFIRMED"))
    admission = AdmissionService(lambda: session)
    assert [decision.status for decision in admission.retrieve_decisions(OWNER_A, action_id=action_id)] == \
           ["SUBMISSION_UNKNOWN"]
    reservations = admission.retrieve_reservations(OWNER_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert reservations, "a confirmed removal must not release reservations"
    with revocation_engine.connect() as connection:
        action_states = connection.execute(text(
            "SELECT DISTINCT status FROM admission_local.admission_decisions")).scalars().all()
    assert action_states == ["SUBMISSION_UNKNOWN"]
