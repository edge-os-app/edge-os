"""Strict input validation and state vocabulary for the local removal domain."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from edge_os_api.revocation.types import OBSERVATION_STATES, REMOVAL_STATES, RemovalObservation, RemovalRequest

from revocation._support import observation, removal_request


def test_states_match_the_accepted_p15_vocabulary():
    assert REMOVAL_STATES == ("NOT_REQUESTED", "REQUESTED", "PENDING", "UNKNOWN", "CONFIRMED", "FAILED")
    assert OBSERVATION_STATES == ("PENDING", "UNKNOWN", "CONFIRMED", "FAILED")


def test_blank_agent_is_rejected():
    with pytest.raises(ValidationError):
        removal_request(agent_id="")


def test_non_url_safe_agent_is_rejected():
    with pytest.raises(ValidationError):
        removal_request(agent_id="bad agent!")


def test_unsupported_network_is_rejected():
    with pytest.raises(ValidationError):
        removal_request(network_id="ethereum:1")


def test_blank_signer_and_policy_are_rejected():
    with pytest.raises(ValidationError):
        removal_request(signer_identity="   ")
    with pytest.raises(ValidationError):
        removal_request(policy_identity="   ")


def test_requested_at_requires_an_explicit_utc_offset():
    with pytest.raises(ValidationError):
        removal_request(requested_at="2026-01-01T00:16:00")


def test_unknown_body_field_is_rejected():
    with pytest.raises(ValidationError):
        RemovalRequest(request_key="k", agent_id="agent-a", network_id="monad:143", reason="r",
                       provenance={"source": "SYNTHETIC_AUTHORED"}, requested_at="2026-01-01T00:16:00Z",
                       owner_id=str(uuid.uuid4()))


def test_not_requested_is_not_an_observation_outcome():
    with pytest.raises(ValidationError):
        observation(uuid.uuid4(), observed_state="NOT_REQUESTED")


def test_observation_blank_signer_is_rejected():
    with pytest.raises(ValidationError):
        observation(uuid.uuid4(), signer_identity="  ")


def test_observation_requires_a_request_uuid():
    with pytest.raises(ValidationError):
        RemovalObservation(observation_key="o", request_id="not-a-uuid", observed_state="CONFIRMED",
                           agent_id="agent-a", wallet_id="wallet-a", network_id="monad:143",
                           provenance={"source": "SYNTHETIC_AUTHORED"}, observed_at="2026-01-01T00:16:00Z")
