"""Observation reconciliation: matched states, exact confirmation, refusals and contradictions."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from edge_os_api.revocation.types import RemovalError

from revocation._support import (
    NETWORK,
    NOW_ISO,
    OWNER_A,
    SIGNER_OTHER,
    STALE_ISO,
    WALLET_A,
    WALLET_B,
    observation,
    removal_request,
    seed_wallet_binding,
)


def _requested(engine, service, **kwargs):
    seed_wallet_binding(engine, OWNER_A)
    return service.request_removal(OWNER_A, removal_request(**kwargs))


def test_matched_pending_observation_derives_pending(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="PENDING"))
    assert outcome.accepted is True
    assert outcome.state == "PENDING"


def test_unknown_observation_does_not_confirm_removal(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="UNKNOWN"))
    assert outcome.state == "UNKNOWN"
    assert outcome.state != "CONFIRMED"


def test_exact_matched_confirmation_with_evidence(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="CONFIRMED"))
    assert outcome.state == "CONFIRMED"
    assert outcome.reason == "PROVIDER_REMOVAL_CONFIRMED"
    assert outcome.view.evidenced_signer == "signer-a"
    with revocation_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT state, evidenced_signer FROM revocation_local.removal_states")).fetchall() == [
            ("CONFIRMED", "signer-a")]


def test_confirmation_without_signer_evidence_stays_unknown(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service, signer_identity=None, policy_identity=None)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="CONFIRMED",
                             signer_identity=None, policy_identity=None))
    assert outcome.state == "UNKNOWN"
    assert outcome.reason == "SIGNER_EVIDENCE_UNKNOWN"


def test_observation_evidencing_the_signer_can_confirm(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service, signer_identity=None, policy_identity=None)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="CONFIRMED",
                             signer_identity="signer-evidenced", policy_identity=None))
    assert outcome.state == "CONFIRMED"
    assert outcome.view.evidenced_signer == "signer-evidenced"


def test_wrong_wallet_observation_is_refused(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="CONFIRMED",
                             wallet_id=WALLET_B))
    assert outcome.accepted is False
    assert outcome.denial_code == "OBSERVATION_IDENTITY_MISMATCH"
    assert outcome.state == "REQUESTED"
    assert removal_service.read_removal(OWNER_A)[0].denied_observations == 1


def test_wrong_signer_observation_is_refused(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="CONFIRMED",
                             signer_identity=SIGNER_OTHER))
    assert outcome.denial_code == "WRONG_SIGNER"
    assert outcome.state == "REQUESTED"


def test_stale_observation_is_refused(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="CONFIRMED",
                             observed_at=STALE_ISO))
    assert outcome.denial_code == "STALE_OBSERVATION"
    assert outcome.state == "REQUESTED"


def test_stale_wallet_binding_is_refused(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    with revocation_engine.begin() as connection:
        connection.execute(text(
            "UPDATE public.wallet_setups SET wallet_id = :wallet WHERE agent_id = :agent"),
            {"wallet": "wallet-a-moved", "agent": "agent-a"})
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="CONFIRMED"))
    assert outcome.denial_code == "STALE_WALLET_BINDING"
    assert outcome.state == "REQUESTED"


def test_late_observation_cannot_restore_a_confirmed_removal(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="CONFIRMED"))
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o2", observed_state="PENDING",
                             observed_at="2026-01-01T00:17:00Z"))
    assert outcome.state == "CONFIRMED"
    assert outcome.view.contradictory is True
    reasons = removal_service.read_removal(OWNER_A)
    assert reasons[0].last_observation_state == "PENDING"
    with revocation_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT observed_state, matched, contradictory FROM revocation_local.removal_observations "
            "ORDER BY sequence")).fetchall() == [("CONFIRMED", True, False), ("PENDING", True, True)]


def test_reconcile_a_foreign_request_id_is_refused(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="CONFIRMED"))
    with pytest.raises(RemovalError):
        removal_service.reconcile(OWNER_A, observation(uuid.uuid4(), observation_key="o2",
                                                       observed_state="UNKNOWN"))


def test_observation_identity_must_match_the_request_network(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="CONFIRMED",
                             network_id="monad-testnet:10143"))
    assert outcome.denial_code == "OBSERVATION_IDENTITY_MISMATCH"


def test_exact_observation_repeat_is_idempotent(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    first = removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                           observed_state="PENDING"))
    second = removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                            observed_state="PENDING"))
    assert first.state == second.state == "PENDING"
    with revocation_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM revocation_local.removal_observations")).scalar_one() == 1


def test_changed_reuse_of_an_observation_key_is_refused(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                   observed_state="PENDING"))
    with pytest.raises(RemovalError):
        removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                       observed_state="UNKNOWN"))
    assert removal_service.read_removal(OWNER_A)[0].state == "PENDING"


def test_later_confirmation_cannot_replace_the_confirmed_signer(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service, signer_identity=None, policy_identity=None)
    first = removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                           observed_state="CONFIRMED",
                                                           signer_identity="signer-a", policy_identity=None))
    assert first.state == "CONFIRMED"
    assert first.view.evidenced_signer == "signer-a"
    second = removal_service.reconcile(OWNER_A, observation(
        view.request_id, observation_key="o2", observed_state="CONFIRMED", signer_identity="signer-b",
        policy_identity=None, observed_at="2026-01-01T00:17:00Z"))
    assert second.state == "CONFIRMED"
    assert second.view.evidenced_signer == "signer-a"
    assert second.view.contradictory is True


def test_now_iso_observation_matches_the_clock(revocation_engine, removal_service):
    assert NOW_ISO == "2026-01-01T00:16:00Z"
    view = _requested(revocation_engine, removal_service)
    outcome = removal_service.reconcile(
        OWNER_A, observation(view.request_id, observation_key="o1", observed_state="PENDING"))
    assert outcome.state == "PENDING"
    assert removal_service.read_removal(OWNER_A, wallet_id=WALLET_A, network_id=NETWORK)[0].state == "PENDING"


def test_exact_observation_repeat_returns_the_recorded_outcome_after_progress(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service)
    first = removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="first",
                                                           observed_state="PENDING"))
    assert first.state == "PENDING"
    later = removal_service.reconcile(OWNER_A, observation(
        view.request_id, observation_key="later", observed_state="CONFIRMED",
        observed_at="2026-01-01T00:17:00Z"))
    assert later.state == "CONFIRMED"
    repeat = removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="first",
                                                            observed_state="PENDING"))
    assert repeat.accepted is True
    assert repeat.state == "PENDING"
    assert repeat.reason == "OBSERVED_PENDING"
    # The latest derived state stays available through the owner read.
    assert removal_service.read_removal(OWNER_A)[0].state == "CONFIRMED"


def test_later_confirmation_without_the_confirmed_evidence_is_contradictory(revocation_engine, removal_service):
    view = _requested(revocation_engine, removal_service, signer_identity=None, policy_identity=None)
    first = removal_service.reconcile(OWNER_A, observation(view.request_id, observation_key="o1",
                                                           observed_state="CONFIRMED",
                                                           signer_identity="signer-a", policy_identity=None))
    assert first.view.evidenced_signer == "signer-a"
    second = removal_service.reconcile(OWNER_A, observation(
        view.request_id, observation_key="o2", observed_state="CONFIRMED", signer_identity=None,
        policy_identity=None, observed_at="2026-01-01T00:17:00Z"))
    assert second.state == "CONFIRMED"
    assert second.view.evidenced_signer == "signer-a"
    assert second.view.contradictory is True
