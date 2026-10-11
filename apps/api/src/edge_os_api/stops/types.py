"""Strict typed models for the local P25 durable scoped-stop domain.

A durable scoped stop is a local, owner-authored control record. It is not
signer removal, not an immediate close, not liquidation and not evidence that
any holding is closed. It records the trigger, the affected scope and the mode,
and it denies only the operations the accepted mode covers. The approved,
immutable permission snapshot is never rewritten to manufacture a stop.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from edge_os_api.admission.types import NETWORKS

# Scopes supported by the accepted inputs. A wider deployment or all-agent scope
# must identify its real adopted mapping and every affected wallet; it is not an
# implicit wallet-global action and it is refused here rather than widened.
STOP_SCOPES = ("POSITION", "AGENT_WALLET_NETWORK")
STOP_MODES = ("STOP_NEW_ENTRIES", "HALT_ALL_SWAPS")
# Adopted trigger records only. The record is preserved verbatim; no loss, trial
# or threshold economy is computed from it.
STOP_TRIGGERS = ("USER", "TRIAL", "POSITION_LOSS", "WALLET_LOSS")

# The operations each accepted mode denies. STOP_NEW_ENTRIES keeps existing
# approved exits available; HALT_ALL_SWAPS denies exits too.
_DENIED_OPERATIONS: dict[str, tuple[str, ...]] = {
    "STOP_NEW_ENTRIES": ("ENTRY", "ADDITION"),
    "HALT_ALL_SWAPS": ("ENTRY", "ADDITION", "EXIT"),
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def stop_denies(mode: str, operation: str) -> bool:
    """True when a stop of this mode denies this operation."""
    return operation in _DENIED_OPERATIONS.get(mode, ())


def denial_reason(mode: str) -> str:
    """The stable reason token for a denying stop, reusing the accepted vocabulary."""
    return "STOPPED_HALT_ALL_SWAPS" if mode == "HALT_ALL_SWAPS" else "STOPPED_NEW_ENTRIES"


class StopRequest(_Strict):
    """One owner request for a durable scoped stop.

    The affected wallet identity is explicit. A `POSITION` stop names its exact
    position; a `AGENT_WALLET_NETWORK` stop applies to that agent's wallet and
    leave other agents and other wallets unchanged.
    """

    trigger: Literal["USER", "TRIAL", "POSITION_LOSS", "WALLET_LOSS"]
    mode: Literal["STOP_NEW_ENTRIES", "HALT_ALL_SWAPS"]
    scope: Literal["POSITION", "AGENT_WALLET_NETWORK"]
    agent_id: str = Field(min_length=1, max_length=200)
    wallet_id: str = Field(min_length=1, max_length=200)
    network_id: str = Field(min_length=1, max_length=200)
    position_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("network_id")
    @classmethod
    def network_must_be_supported(cls, value: str) -> str:
        if value not in NETWORKS:
            raise ValueError(f"network must name Monad 143 or testnet 10143, got {value!r}")
        return value

    @model_validator(mode="after")
    def target_matches_scope(self) -> "StopRequest":
        if self.scope == "POSITION" and self.position_id is None:
            raise ValueError("a POSITION stop requires its exact position_id")
        if self.scope == "AGENT_WALLET_NETWORK" and self.position_id is not None:
            raise ValueError("an AGENT_WALLET_NETWORK stop must not name a position")
        return self


class StopView(_Strict):
    """Owner-scoped view of one durable stop record."""

    stop_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: str
    scope: str
    mode: str
    trigger: str
    position_id: str | None
    created_at: str
