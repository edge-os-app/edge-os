"""Strict typed models for the local P30 revocation preparation domain.

A removal record is a local, owner-authored control. It is not a live provider
operation and not an independent Privy proof. The owner request, the
provider-style observation and the derived current state are kept separate. A
pending, unknown or confirmed removal denies a new agent submission through the
local P30 check, while owner access, pending actions and residual holdings stay
untouched.

Every identifier is validated here. A request never carries an owner: the
service derives the owner from the verified identity.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from edge_os_api.admission.types import NETWORKS

# The accepted P15 signer-removal states. No other state is added here.
REMOVAL_STATES = ("NOT_REQUESTED", "REQUESTED", "PENDING", "UNKNOWN", "CONFIRMED", "FAILED")
# These derived states deny a new agent submission through the P30 check. A REQUESTED removal denies too:
# the request is persisted before any provider effect, so no fresh work is admitted while it is in flight
# (#58 G14). Only FAILED and absent records leave submission to the other controls.
DENYING_STATES = ("REQUESTED", "PENDING", "UNKNOWN", "CONFIRMED")
# Provider-style observation outcomes. `NOT_REQUESTED` is not an observation.
OBSERVATION_STATES = ("PENDING", "UNKNOWN", "CONFIRMED", "FAILED")

# Stable denial tokens for the local P30 check. A local stop has its own tokens;
# a stop never proves provider removal and never reuses these.
DENIAL_REASON = {
    "REQUESTED": "REMOVAL_REQUESTED",
    "PENDING": "REMOVAL_PENDING",
    "UNKNOWN": "REMOVAL_UNKNOWN",
    "CONFIRMED": "REMOVAL_CONFIRMED",
}

AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")

State = Literal["NOT_REQUESTED", "REQUESTED", "PENDING", "UNKNOWN", "CONFIRMED", "FAILED"]
ObservationState = Literal["PENDING", "UNKNOWN", "CONFIRMED", "FAILED"]


class RemovalError(Exception):
    """A refused local removal operation. Fails closed and writes no affirmative state."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def parse_utc(value: str) -> dt.datetime:
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as error:
        raise ValueError("timestamps must be RFC 3339 UTC") from error
    if moment.tzinfo is None or moment.utcoffset() != dt.timedelta(0):
        raise ValueError("timestamps must carry an explicit UTC offset")
    return moment.astimezone(dt.timezone.utc)


def _not_blank(value: str | None) -> str | None:
    if value is not None and not value.strip():
        raise ValueError("an identifier must not be blank")
    return value


class Provenance(StrictModel):
    """The origin of a request or an observation. Authored fixtures are labelled."""

    source: str = Field(min_length=1, max_length=120)
    label: str | None = Field(default=None, max_length=200)

    @field_validator("source")
    @classmethod
    def source_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("provenance source must not be blank")
        return value

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value: str | None) -> str | None:
        return _not_blank(value)


class RemovalRequest(StrictModel):
    """One owner request to remove the selected agent wallet's signer.

    The request names the agent and network. The service resolves the actual
    saved wallet binding through an accepted owner-scoped read and rejects a
    supplied `expected_wallet_id` that disagrees. No owner field is accepted.
    """

    request_key: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=64)
    network_id: str = Field(min_length=1, max_length=40)
    expected_wallet_id: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=200)
    signer_identity: str | None = Field(default=None, max_length=200)
    policy_identity: str | None = Field(default=None, max_length=200)
    provenance: Provenance
    requested_at: str = Field(min_length=1, max_length=40)

    @field_validator("agent_id")
    @classmethod
    def agent_id_is_url_safe(cls, value: str) -> str:
        if AGENT_ID.fullmatch(value) is None:
            raise ValueError("the agent ID must use 1 to 64 URL-safe characters")
        return value

    @field_validator("network_id")
    @classmethod
    def network_must_be_supported(cls, value: str) -> str:
        if value not in NETWORKS:
            raise ValueError("the network must name Monad 143 or testnet 10143")
        return value

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("the removal reason must not be blank")
        return value

    @field_validator("expected_wallet_id", "signer_identity", "policy_identity")
    @classmethod
    def optional_ids_not_blank(cls, value: str | None) -> str | None:
        return _not_blank(value)

    @field_validator("requested_at")
    @classmethod
    def requested_at_must_parse(cls, value: str) -> str:
        parse_utc(value)
        return value


class RemovalObservation(StrictModel):
    """One provider-style observation of the original removal request.

    The observation names the request it reconciles and the exact observed
    identity. A mismatched, stale, wrong-wallet, wrong-signer or wrong-network
    observation is refused and never changes the derived state.
    """

    observation_key: str = Field(min_length=1, max_length=200)
    request_id: uuid.UUID
    observed_state: ObservationState
    agent_id: str = Field(min_length=1, max_length=64)
    wallet_id: str = Field(min_length=1, max_length=200)
    network_id: str = Field(min_length=1, max_length=40)
    signer_identity: str | None = Field(default=None, max_length=200)
    policy_identity: str | None = Field(default=None, max_length=200)
    provenance: Provenance
    observed_at: str = Field(min_length=1, max_length=40)

    @field_validator("network_id")
    @classmethod
    def network_must_be_supported(cls, value: str) -> str:
        if value not in NETWORKS:
            raise ValueError("the network must name Monad 143 or testnet 10143")
        return value

    @field_validator("signer_identity", "policy_identity")
    @classmethod
    def optional_ids_not_blank(cls, value: str | None) -> str | None:
        return _not_blank(value)

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_parse(cls, value: str) -> str:
        parse_utc(value)
        return value


class RemovalView(StrictModel):
    """Owner-scoped view of one local removal record and its derived state."""

    request_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: str
    state: State
    reason: str
    request_key: str
    signer_identity: str | None
    policy_identity: str | None
    evidenced_signer: str | None
    evidenced_policy: str | None
    contradictory: bool
    denied_observations: int
    request_provenance: dict[str, Any]
    last_observation_state: str | None
    last_observation_provenance: dict[str, Any] | None
    requested_at: str
    updated_at: str


class ReconcileOutcome(StrictModel):
    """The result of reconciling one observation against its original request."""

    request_id: uuid.UUID
    accepted: bool
    denial_code: str | None
    state: State
    reason: str
    view: RemovalView
