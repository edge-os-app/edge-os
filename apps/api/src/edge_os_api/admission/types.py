"""Strict typed domain models for the local admission and reservation domain.

The service derives `owner_id` from the verified caller. Intent payloads never
carry an owner field. Amounts use the P15 canonical unsigned raw integer string
with decimals, and unlike assets are never summed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OPERATIONS = ("ENTRY", "ADDITION", "EXIT")
NETWORKS = ("monad:143", "monad-testnet:10143")
# Storage bound: the owned ledgers use NUMERIC(78, 0). A raw integer longer than
# this cannot be stored exactly, so it is rejected at validation.
MAX_RAW_DIGITS = 78

_ASSET_ID = Field(min_length=1, max_length=200)
_ID = Field(min_length=1, max_length=200)
LABEL = re.compile(r"SYNTHETIC_[A-Z0-9_]+")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def parse_utc(value: str) -> dt.datetime:
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamps must be RFC 3339 UTC") from error
    if moment.tzinfo is None or moment.utcoffset() != dt.timedelta(0):
        raise ValueError("timestamps must carry an explicit UTC offset")
    return moment.astimezone(dt.timezone.utc)


class AssetAmount(StrictModel):
    asset_id: str = _ASSET_ID
    raw: str = Field(pattern=r"^(?:0|[1-9][0-9]*)$")
    decimals: int = Field(ge=0, le=255)

    @field_validator("raw")
    @classmethod
    def raw_within_storage_bound(cls, value: str) -> str:
        if len(value) > MAX_RAW_DIGITS:
            raise ValueError(f"raw amount exceeds the {MAX_RAW_DIGITS}-digit storage bound")
        return value

    def as_int(self) -> int:
        return int(self.raw)

    @classmethod
    def from_int(cls, asset_id: str, value: int, decimals: int) -> "AssetAmount":
        return cls(asset_id=asset_id, raw=str(value), decimals=decimals)


class IdentityBinding(StrictModel):
    agent_id: str = _ID
    wallet_id: str = _ID
    network_id: str = _ID
    strategy_revision: str = _ID
    mandate_id: str = _ID

    @field_validator("network_id")
    @classmethod
    def network_must_be_supported(cls, value: str) -> str:
        if value not in NETWORKS:
            raise ValueError(f"network must name Monad 143 or testnet 10143, got {value!r}")
        return value


class ValueState(StrictModel):
    state: Literal["KNOWN", "UNKNOWN"]
    amount: AssetAmount | None = None

    @model_validator(mode="after")
    def amount_matches_state(self) -> "ValueState":
        if (self.state == "KNOWN") != (self.amount is not None):
            raise ValueError("known valuation requires an amount; unknown valuation forbids one")
        return self


class ActionInput(StrictModel):
    quote_asset_id: str = _ASSET_ID
    quote_input: AssetAmount | None = None
    mark: ValueState | None = None
    quote_status: Literal["FRESH", "STALE", "MISSING"]
    expected_quote: AssetAmount | None = None

    @model_validator(mode="after")
    def quote_amounts_use_declared_asset(self) -> "ActionInput":
        for amount, name in ((self.quote_input, "quote_input"), (self.expected_quote, "expected_quote")):
            if amount is not None and amount.asset_id != self.quote_asset_id:
                raise ValueError(f"{name} must use the declared quote asset {self.quote_asset_id!r}")
        if self.mark is not None and self.mark.amount is not None and self.mark.amount.asset_id != self.quote_asset_id:
            raise ValueError("mark must use the declared quote asset")
        return self


class ActionIntent(StrictModel):
    action_id: str = Field(min_length=1, max_length=200)
    binding: IdentityBinding
    policy_binding: str = Field(min_length=1, max_length=200)
    position_id: str = Field(min_length=1, max_length=200)
    operation: Literal["ENTRY", "ADDITION", "EXIT"]
    review_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    quantity: AssetAmount
    input: ActionInput

    @model_validator(mode="after")
    def scope_requires(self) -> "ActionIntent":
        if self.operation in {"ENTRY", "ADDITION"} and self.input.quote_input is None:
            raise ValueError("entry and addition require a reviewed quote buy input")
        if self.operation == "EXIT" and self.input.quote_input is not None:
            raise ValueError("exit does not consume quote buy input")
        return self


class AllowanceCap(StrictModel):
    asset_id: str = _ASSET_ID
    decimals: int = Field(ge=0, le=255)
    approved_raw: str = Field(pattern=r"^(?:0|[1-9][0-9]*)$")

    def as_int(self) -> int:
        return int(self.approved_raw)


class StopSpec(StrictModel):
    """A scoped, local stop on the authored approval. A local stop is not signer removal."""

    scope: Literal["POSITION", "AGENT_WALLET_NETWORK"]
    mode: Literal["STOP_NEW_ENTRIES", "HALT_ALL_SWAPS"]
    position_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def target_matches_scope(self) -> "StopSpec":
        if self.scope == "POSITION" and self.position_id is None:
            raise ValueError("a POSITION stop requires its exact position_id")
        if self.scope == "AGENT_WALLET_NETWORK" and self.position_id is not None:
            raise ValueError("an AGENT_WALLET_NETWORK stop must not name a position")
        return self


class ApprovalSnapshot(StrictModel):
    approval_id: str = _ID
    binding: IdentityBinding
    state: Literal["ACTIVE", "REVOKED", "EXPIRED", "DENIED"]
    policy_binding: str = Field(min_length=1, max_length=200)
    expires_at: str = Field(min_length=1, max_length=40)
    actions: list[str] = Field(min_length=1, max_length=20)
    allocation_quote: AllowanceCap
    quote_allowance: AllowanceCap
    base_allowance: AllowanceCap
    gas: AllowanceCap
    per_action_gas: AllowanceCap
    per_exit_gas: AllowanceCap
    attempt_budget: int = Field(ge=0, le=1_000_000)
    stops: list[StopSpec] = Field(default_factory=list, max_length=20)
    exit_capacity_qualified: bool
    valuation_qualified: bool
    cost_model_qualified: bool
    fixture_label: str = Field(min_length=1, max_length=80)

    def content_hash(self) -> str:
        """Canonical hash of the full immutable approval meaning (all terms, not just caps)."""
        payload = self.model_dump(mode="json")
        payload.pop("fixture_label", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @field_validator("actions")
    @classmethod
    def actions_must_be_supported(cls, values: list[str]) -> list[str]:
        unknown = [value for value in values if value not in OPERATIONS]
        if unknown:
            raise ValueError(f"unsupported approved actions: {unknown}")
        if len(set(values)) != len(values):
            raise ValueError("approved actions must be unique")
        return values

    @field_validator("fixture_label")
    @classmethod
    def label_must_be_synthetic(cls, value: str) -> str:
        if LABEL.fullmatch(value) is None:
            raise ValueError("authored fixture policies must carry a SYNTHETIC_ label")
        return value

    @field_validator("expires_at")
    @classmethod
    def expiry_must_parse(cls, value: str) -> str:
        parse_utc(value)
        return value

    def is_active_at(self, checked_at: dt.datetime) -> bool:
        return self.state == "ACTIVE" and parse_utc(self.expires_at) > checked_at


class Holding(StrictModel):
    asset_id: str = _ASSET_ID
    decimals: int = Field(ge=0, le=255)
    raw: str = Field(pattern=r"^(?:0|[1-9][0-9]*)$")

    def as_int(self) -> int:
        return int(self.raw)


class PositionState(StrictModel):
    position_id: str = _ID
    binding: IdentityBinding
    asset_id: str = _ASSET_ID
    decimals: int = Field(ge=0, le=255)
    inventory_raw: str = Field(pattern=r"^(?:0|[1-9][0-9]*)$")

    def as_int(self) -> int:
        return int(self.inventory_raw)


class HoldingsSnapshot(StrictModel):
    agent_id: str = _ID
    wallet_id: str = _ID
    network_id: str = _ID
    balances: dict[str, Holding]
    positions: dict[str, PositionState]
    unexplained_external: bool = False

    @field_validator("network_id")
    @classmethod
    def network_must_be_supported(cls, value: str) -> str:
        if value not in NETWORKS:
            raise ValueError(f"network must name Monad 143 or testnet 10143, got {value!r}")
        return value

    @model_validator(mode="after")
    def snapshots_are_consistent(self) -> "HoldingsSnapshot":
        for key, holding in self.balances.items():
            if key != holding.asset_id:
                raise ValueError("balance key must equal the holding asset_id")
        for key, position in self.positions.items():
            if key != position.position_id:
                raise ValueError("positions key must equal the position_id")
            if (position.binding.agent_id, position.binding.wallet_id, position.binding.network_id) != (
                    self.agent_id, self.wallet_id, self.network_id):
                raise ValueError("position binding must match the wallet snapshot")
        return self


class AdmissionContext(StrictModel):
    checked_at: str = Field(min_length=1, max_length=40)
    holdings: HoldingsSnapshot

    @field_validator("checked_at")
    @classmethod
    def time_must_parse(cls, value: str) -> str:
        parse_utc(value)
        return value


class ReservationView(StrictModel):
    reservation_id: uuid.UUID
    scope: str
    position_id: str | None
    amount: AssetAmount
    state: str


class AdmissionDecision(StrictModel):
    decision_id: uuid.UUID
    owner_id: uuid.UUID
    action_id: str
    review_hash: str
    operation: str
    status: str
    reason: str | None
    created_at: str
    reservations: list[ReservationView] = Field(default_factory=list)


class SavedDecision(StrictModel):
    decision_id: uuid.UUID
    owner_id: uuid.UUID
    action_id: str
    review_hash: str
    operation: str
    status: str
    reason: str | None
    created_at: str


class SavedReservation(StrictModel):
    reservation_id: uuid.UUID
    owner_id: uuid.UUID
    action_id: str
    scope: str
    position_id: str | None
    amount: AssetAmount
    state: str


class SavedReceipt(StrictModel):
    receipt_id: uuid.UUID
    owner_id: uuid.UUID
    action_id: str
    position_id: str | None
    operation: str
    outcome: str
    breach: bool
    created_at: str
    content: dict[str, Any]


class AllowanceSummary(StrictModel):
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: str
    asset_id: str
    decimals: int
    approved_raw: str
    consumed_raw: str
    reserved_raw: str
    remaining_raw: str

    @classmethod
    def from_literals(cls, *, owner_id: uuid.UUID, agent_id: str, wallet_id: str, network_id: str,
                      asset_id: str, decimals: int, approved: int, consumed: int, reserved: int) -> "AllowanceSummary":
        return cls(
            owner_id=owner_id, agent_id=agent_id, wallet_id=wallet_id, network_id=network_id,
            asset_id=asset_id, decimals=decimals, approved_raw=str(approved), consumed_raw=str(consumed),
            reserved_raw=str(reserved), remaining_raw=str(approved - consumed - reserved),
        )


class ActionReceipt(StrictModel):
    action_id: str = _ID
    binding: IdentityBinding
    outcome: Literal["CONFIRMED", "REVERTED", "SUBMISSION_UNKNOWN", "PREBROADCAST_DENIED", "CANCELLED"]
    actual_input: AssetAmount | None = None
    actual_output: AssetAmount | None = None
    actual_gas: AssetAmount | None = None


class CancellationOutcome(StrictModel):
    action_id: str
    decision_status: str
    reason: str | None
    released: list[uuid.UUID]


class ReconciliationOutcome(StrictModel):
    action_id: str
    decision_status: str
    reason: str | None
    consumed: list[AssetAmount] = Field(default_factory=list)
    released: list[AssetAmount] = Field(default_factory=list)
    retained: list[AssetAmount] = Field(default_factory=list)