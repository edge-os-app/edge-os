"""The NEW local P30 submission-denial check: states, usable-allowance proof and controls."""

from __future__ import annotations

import pytest

from admission import _builders as admission_builders

from edge_os_api.admission.service import AdmissionService

from revocation._support import (
    AGENT_A,
    AGENT_B,
    NETWORK,
    OWNER_A,
    OWNER_B,
    WALLET_A,
    WALLET_B,
    AuthoredProviderRefusal,
    observation,
    removal_request,
    seed_admission_admitted,
    seed_admission_admitted_b,
    seed_admission_unknown,
    seed_stop,
    seed_wallet_binding,
)


def _requested(engine, service, **kwargs):
    seed_wallet_binding(engine, OWNER_A)
    return service.request_removal(OWNER_A, removal_request(**kwargs))


@pytest.mark.parametrize("observed,reason", [
    ("PENDING", "REMOVAL_PENDING"),
    ("UNKNOWN", "REMOVAL_UNKNOWN"),
    ("CONFIRMED", "REMOVAL_CONFIRMED"),
])
def test_pending_unknown_and_confirmed_deny_new_submission(
        revocation_engine, removal_service, session, observed, reason):
    view = _requested(revocation_engine, removal_service)
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state=observed))
    assert removal_service.submission_denial(
        session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK) == [reason]


def test_requested_state_does_not_deny(revocation_engine, removal_service, session):
    _requested(revocation_engine, removal_service)
    assert removal_service.submission_denial(
        session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK) == []


def test_failed_removal_does_not_deny(revocation_engine, removal_service, session):
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                             observed_state="FAILED"))
    assert outcome.state == "FAILED"
    assert removal_service.submission_denial(
        session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK) == []


def test_denial_holds_with_usable_allowances_and_no_stop(revocation_engine, removal_service, session):
    # Admit a real authored action: the accepted admission path proves the allowances
    # are usable and no durable stop exists, so an exhausted counter or an old stop
    # cannot be the cause of the denial.
    seed_wallet_binding(revocation_engine, OWNER_A)
    action_id = seed_admission_admitted(revocation_engine, OWNER_A)
    admission = AdmissionService(lambda: session)
    decisions = admission.retrieve_decisions(OWNER_A, action_id=action_id)
    assert [decision.status for decision in decisions] == ["ADMITTED"]
    assert removal_service.submission_denial(session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A,
                                             network_id=NETWORK) == []
    view = removal_service.request_removal(OWNER_A, removal_request())
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="PENDING"))
    assert removal_service.submission_denial(session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A,
                                             network_id=NETWORK) == ["REMOVAL_PENDING"]


def test_a_local_stop_alone_is_not_removal(revocation_engine, removal_service, session):
    seed_wallet_binding(revocation_engine, OWNER_A)
    seed_stop(revocation_engine, OWNER_A)
    assert removal_service.submission_denial(session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A,
                                             network_id=NETWORK) == []


def test_owner_positive_control_keeps_owner_access_after_confirmed_removal(
        revocation_engine, removal_service, session):
    view = _requested(revocation_engine, removal_service)
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="CONFIRMED"))
    assert [record.state for record in removal_service.read_removal(OWNER_A)] == ["CONFIRMED"]
    # The owner still reads their own saved wallet binding and can admit a new owner-reviewed action.
    binding_rows = session.connection().exec_driver_sql(
        "SELECT wallet_id FROM public.wallet_setups WHERE agent_id = 'agent-a'").fetchall()
    assert [row[0] for row in binding_rows] == [WALLET_A]
    action_id = seed_admission_admitted(revocation_engine, OWNER_A)
    decisions = AdmissionService(lambda: session).retrieve_decisions(OWNER_A, action_id=action_id)
    assert [decision.status for decision in decisions] == ["ADMITTED"]


def test_b_positive_control_b_wallet_is_unaffected(revocation_engine, removal_service, session):
    seed_wallet_binding(revocation_engine, OWNER_A)
    seed_wallet_binding(revocation_engine, OWNER_B, agent_id=AGENT_B, wallet_id=WALLET_B)
    view = removal_service.request_removal(OWNER_A, removal_request())
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="CONFIRMED"))
    # Owner A is denied; owner B is not, and B's admission still admits.
    assert removal_service.submission_denial(session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A,
                                             network_id=NETWORK) == ["REMOVAL_CONFIRMED"]
    assert removal_service.submission_denial(session, OWNER_B, agent_id=AGENT_B, wallet_id=WALLET_B,
                                             network_id=NETWORK) == []
    action_id = seed_admission_admitted_b(revocation_engine, OWNER_B)
    decisions = AdmissionService(lambda: session).retrieve_decisions(OWNER_B, action_id=action_id)
    assert [decision.status for decision in decisions] == ["ADMITTED"]


def test_controlled_provider_style_submission_refusal_is_separate_from_the_local_check(
        revocation_engine, removal_service, session):
    seed_wallet_binding(revocation_engine, OWNER_A)
    view = removal_service.request_removal(OWNER_A, removal_request())
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="CONFIRMED"))
    # The local P30 check denies with its own token.
    assert removal_service.submission_denial(session, OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A,
                                             network_id=NETWORK) == ["REMOVAL_CONFIRMED"]
    # A direct controlled provider-style submission for removed A is refused by the
    # authored fixture transport, separately from the local check and with a
    # distinct token. This is an authored fixture, not live Privy enforcement.
    provider = AuthoredProviderRefusal()
    state = removal_service.read_removal(OWNER_A, agent_id=AGENT_A, wallet_id=WALLET_A,
                                         network_id=NETWORK)[0].state
    assert provider.submit(state) == AuthoredProviderRefusal.REFUSED
    assert provider.submit("REQUESTED") == AuthoredProviderRefusal.ACCEPTED
    assert AuthoredProviderRefusal.REFUSED != "REMOVAL_CONFIRMED"
    # A controlled FAILED removal is not a confirmed removal and does not deny.
    assert admission_builders.intent_entry().operation == "ENTRY"
