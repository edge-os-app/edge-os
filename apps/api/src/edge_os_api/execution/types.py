"""Strict typed models for the local P23 execution, evaluation and queue domain.

This module binds the accepted P06 compiler meaning and the accepted P22
admission types. It adds no scheduling service, provider call, signing path or
wallet authority. Amounts and identities reuse the P22 canonical types.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from edge_os_api.admission.types import (
    AssetAmount,
    IdentityBinding,
    ValueState,
    parse_utc,
)
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.strategies import compiler as strategy_compiler

OPERATIONS = ("ENTRY", "EXIT")
DECISION_STATUSES = ("SIGNAL", "NO_SIGNAL", "INELIGIBLE")
RULE_NAMES = ("entry", "exit", "invalidation")
_MAX_SCHEDULE = 288
_MAX_REASONS = 64


class ExecutionError(Exception):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _parse_required(value: str) -> str:
    parse_utc(value)
    return value


def sha256_ref(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical_hash(payload: Any) -> str:
    return sha256_ref(record_contract.canonical_bytes(payload))


@dataclass(frozen=True)
class FrozenRevision:
    """One immutable compiled revision identity.

    The compiled strategy is stored as canonical bytes. Every `strategy` access
    returns a fresh parse of those bytes, so mutating a returned mapping cannot
    change the revision meaning or its declared content hash.
    """

    strategy_id: str
    revision_id: str
    content_hash: str
    manifest_hash: str
    market_binding_id: str
    warmup_buckets: int
    _canonical_json: bytes

    @property
    def strategy(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def freeze_revision(strategy: dict[str, Any]) -> FrozenRevision:
    """Validate a compiled P06 strategy and freeze its canonical identity.

    Validation reuses the actual compiler. A malformed or unsupported revision
    raises `CompilerError` before any identity is accepted.
    """
    strategy_compiler.validate_strategy(strategy)
    canonical = record_contract.canonical_bytes(strategy)
    frozen = json.loads(canonical)
    content_hash = sha256_ref(canonical)
    return FrozenRevision(
        strategy_id=frozen["strategy_id"],
        revision_id=f"{frozen['strategy_id']}:{content_hash[7:23]}",
        content_hash=content_hash,
        manifest_hash=canonical_hash(frozen["semantic_manifest"]),
        market_binding_id=strategy_compiler.market_binding_id(frozen["market"]),
        warmup_buckets=frozen["warmup_buckets"],
        _canonical_json=canonical,
    )


class InputObservation(StrictModel):
    """One scheduled input observation with its availability and qualification evidence."""

    value: str | None = None
    bucket_end: str = Field(min_length=1, max_length=40)
    qualified: bool = True
    available_at: str | None = Field(default=None, min_length=1, max_length=40)
    reasons: list[str] = Field(default_factory=list, max_length=_MAX_REASONS)

    @field_validator("bucket_end")
    @classmethod
    def bucket_end_is_utc(cls, value: str) -> str:
        return _parse_required(value)

    @field_validator("available_at")
    @classmethod
    def available_at_is_utc(cls, value: str | None) -> str | None:
        return None if value is None else _parse_required(value)


class EvaluationInputs(StrictModel):
    """The controlled clock, schedule, declared data and portfolio state for one decision."""

    decision_time: str = Field(min_length=1, max_length=40)
    position: int = Field(ge=0, le=_MAX_SCHEDULE - 1)
    position_open: bool
    scheduled_bucket_ends: list[str] = Field(min_length=1, max_length=_MAX_SCHEDULE)
    prices: list[InputObservation | None]
    quote_volumes: list[InputObservation | None]

    @field_validator("decision_time")
    @classmethod
    def decision_time_is_utc(cls, value: str) -> str:
        return _parse_required(value)

    @field_validator("scheduled_bucket_ends")
    @classmethod
    def schedule_entries_are_utc(cls, values: list[str]) -> list[str]:
        for value in values:
            _parse_required(value)
        return values

    @model_validator(mode="after")
    def positions_match_schedule(self) -> "EvaluationInputs":
        count = len(self.scheduled_bucket_ends)
        if len(self.prices) != count or len(self.quote_volumes) != count:
            raise ValueError("price and quote-volume rows must match the schedule length")
        for index, end in enumerate(self.scheduled_bucket_ends):
            for rows in (self.prices, self.quote_volumes):
                row = rows[index]
                if row is not None and row.bucket_end != end:
                    raise ValueError("each observation must bind its exact scheduled bucket end")
        return self

    def identity(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))

    def observed_at(self) -> dt.datetime:
        return parse_utc(self.decision_time)


class ActionQuote(StrictModel):
    """Authored current action quote for one exact action.

    This is controlled local evidence, not a real provider quote. It binds the
    quote to the exact intended action, immutable revision and market, and carries
    the quote identity, amount and units, and an observation and expiry time. The
    submission revalidation requires the binding and the quote to be current and
    compatible with the saved intent before any transport call.
    """

    action_id: str = Field(min_length=1, max_length=200)
    revision_id: str = Field(min_length=1, max_length=200)
    revision_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    market_binding_id: str = Field(min_length=1, max_length=200)
    quote_asset_id: str = Field(min_length=1, max_length=200)
    amount: AssetAmount
    observed_at: str = Field(min_length=1, max_length=40)
    expires_at: str = Field(min_length=1, max_length=40)
    source_ref: str = Field(min_length=1, max_length=200)

    @field_validator("observed_at", "expires_at")
    @classmethod
    def times_are_utc(cls, value: str) -> str:
        return _parse_required(value)

    @model_validator(mode="after")
    def amount_matches_asset(self) -> "ActionQuote":
        if self.amount.asset_id != self.quote_asset_id:
            raise ValueError("the quote amount must use the declared quote asset")
        return self


class RuleEvaluation(StrictModel):
    rule: str = Field(min_length=1, max_length=20)
    state: str = Field(min_length=1, max_length=20)
    reasons: list[str] = Field(default_factory=list, max_length=_MAX_REASONS)


class EvaluationOutcome(StrictModel):
    status: str = Field(min_length=1, max_length=20)
    operation: str | None = None
    reasons: list[str] = Field(default_factory=list, max_length=_MAX_REASONS)
    rule_results: list[RuleEvaluation] = Field(default_factory=list, max_length=8)
    inputs_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class IntentTerms(StrictModel):
    """Authored intent amounts and bindings for one exact signal decision."""

    operation: Literal["ENTRY", "EXIT"]
    position_id: str = Field(min_length=1, max_length=200)
    policy_binding: str = Field(min_length=1, max_length=200)
    mandate_id: str = Field(min_length=1, max_length=200)
    quote_asset_id: str = Field(min_length=1, max_length=200)
    quantity: AssetAmount
    quote_input: AssetAmount | None = None
    expected_quote: AssetAmount | None = None
    mark: ValueState | None = None
    quote_status: Literal["FRESH", "STALE", "MISSING"]

    @model_validator(mode="after")
    def scope_and_assets(self) -> "IntentTerms":
        if self.operation == "ENTRY" and self.quote_input is None:
            raise ValueError("an entry requires a reviewed quote buy input")
        if self.operation == "EXIT" and self.quote_input is not None:
            raise ValueError("an exit does not consume quote buy input")
        for name, amount in (("quote_input", self.quote_input), ("expected_quote", self.expected_quote)):
            if amount is not None and amount.asset_id != self.quote_asset_id:
                raise ValueError(f"{name} must use the declared quote asset")
        if self.mark is not None and self.mark.amount is not None and self.mark.amount.asset_id != self.quote_asset_id:
            raise ValueError("mark must use the declared quote asset")
        return self


class IntentPlan(StrictModel):
    intent_id: str = Field(min_length=1, max_length=200)
    action_id: str = Field(min_length=1, max_length=200)
    decision_id: uuid.UUID
    review_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    operation: str = Field(min_length=1, max_length=20)
    position_id: str = Field(min_length=1, max_length=200)
    binding: IdentityBinding
    payload_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class EnqueueResult(StrictModel):
    intent: IntentPlan
    admission_status: str = Field(min_length=1, max_length=20)
    admission_reason: str | None = None
    queue_entry: "QueueEntryView | None" = None


class SavedDecisionView(StrictModel):
    decision_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: str
    strategy_id: str
    revision_id: str
    content_hash: str
    manifest_hash: str
    market_binding_id: str
    decision_at: str
    status: str
    operation: str | None
    reasons: list[str] = Field(default_factory=list)
    rule_results: list[RuleEvaluation] = Field(default_factory=list)
    inputs_hash: str
    created_at: str


class QueueEntryView(StrictModel):
    queue_id: uuid.UUID
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: str
    position_id: str
    operation: str
    action_id: str
    decision_id: uuid.UUID
    priority: int
    state: str
    blocking_reason: str | None
    enqueued_at: str
    updated_at: str
    waiting_seconds: int = Field(ge=0)
    delayed_exit: bool


class RevalidationOutcome(StrictModel):
    status: Literal["PASSED", "DENIED"]
    reason: str | None = None
    revision_hash: str
    approval_hash: str
    policy_binding: str
    market_binding_id: str
    validation_identity: str
    submission_at: str


class SubmissionEvidence(StrictModel):
    """Immutable local fixture evidence. It is not a real transport result."""

    attempt_id: uuid.UUID
    outcome: Literal["DEFINITELY_UNSENT", "SUBMISSION_POSSIBLE", "CONFIRMED", "REVERTED"]
    detail: str = Field(min_length=1, max_length=200)
    actual_input: AssetAmount | None = None
    actual_output: AssetAmount | None = None
    actual_gas: AssetAmount | None = None


class TickResult(StrictModel):
    status: str = Field(min_length=1, max_length=40)
    reason: str | None = None
    selected_action_id: str | None = None
    queue_entry: QueueEntryView | None = None
    evidence: SubmissionEvidence | None = None


class HealthView(StrictModel):
    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_id: str
    last_attempt_at: str | None
    last_completion_at: str | None
    last_input_at: str | None
    last_decision_id: uuid.UUID | None
    next_scheduled_at: str | None
    queue: list[QueueEntryView] = Field(default_factory=list)
    blocking_reason: str | None


def utc_iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_intent_id(decision_id: uuid.UUID, operation: str) -> str:
    """The intent id equals the action id: one decision plus one operation, one intent."""
    return f"p23:{decision_id}:{operation}"


def canonical_action_id(decision_id: uuid.UUID, operation: str) -> str:
    return f"p23:{decision_id}:{operation}"
