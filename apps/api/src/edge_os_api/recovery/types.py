"""Strict typed models for the local P24 original-action recovery stage.

Recovery reopens the original saved P23 action after an engine or process
restart and reconciles controlled, labelled local outcome evidence for that
exact action. It is not a submission route: these types carry no fresh quote, no
transport and no wallet authority. Amount and identity reuse the P22 canonical
types. Unknown or unqualified evidence is represented explicitly, never as zero.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from edge_os_api.admission.types import (
    ActionReceipt,
    AssetAmount,
    IdentityBinding,
    parse_utc,
)
from edge_os_api.records import contract_adapter as record_contract

# The controlled, labelled outcomes recovery may reconcile for an original
# action. This is the P22 receipt vocabulary, not a transport result.
RECOVERY_OUTCOMES = ("CONFIRMED", "REVERTED", "PREBROADCAST_DENIED", "SUBMISSION_UNKNOWN")

# Durable recovery case states. OPEN means the original action is still unknown
# and its reservations and exclusive claim stay in force. SETTLED states mirror
# the reconciled P22 decision. BLOCKED states retain evidence that must not be
# reported as a confirmation.
RECOVERY_CASE_STATES = (
    "OPEN", "CONFIRMED", "REVERTED", "DENIED_UNSENT", "UNKNOWN",
    "BREACHED", "RECONCILE_MISMATCH", "DISCREPANCY", "NO_ADMISSION_DECISION",
    "NO_SUBMISSION_ATTEMPT",
)
_EVIDENCE_STATES = ("PENDING", "ACCEPTED", "REJECTED")


class RecoveryError(Exception):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _parse_required(value: str) -> str:
    parse_utc(value)
    return value


class OutcomeEvidence(StrictModel):
    """Controlled local outcome evidence for one original action.

    It is authored fixture evidence, not a real provider or chain receipt. It
    binds the outcome to the exact original action, immutable revision, policy
    and frozen payload reference, so foreign or altered evidence is rejected
    before it can reach the P22 ledger.
    """

    action_id: str = Field(min_length=1, max_length=200)
    binding: IdentityBinding
    operation: Literal["ENTRY", "ADDITION", "EXIT"]
    revision_id: str = Field(min_length=1, max_length=200)
    policy_binding: str = Field(min_length=1, max_length=200)
    payload_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    outcome: Literal["CONFIRMED", "REVERTED", "PREBROADCAST_DENIED", "SUBMISSION_UNKNOWN"]
    detail: str = Field(min_length=1, max_length=200)
    actual_input: AssetAmount | None = None
    actual_output: AssetAmount | None = None
    actual_gas: AssetAmount | None = None
    observed_at: str = Field(min_length=1, max_length=40)
    source_ref: str = Field(min_length=1, max_length=200)

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_utc(cls, value: str) -> str:
        return _parse_required(value)

    @model_validator(mode="after")
    def unproved_outcomes_carry_no_actuals(self) -> "OutcomeEvidence":
        # A proved pre-broadcast denial and a submission-possible result have no
        # known effect. Carrying an actual would be an invented value, so it is
        # rejected rather than silently ignored.
        if self.outcome in {"PREBROADCAST_DENIED", "SUBMISSION_UNKNOWN"}:
            if any(amount is not None for amount in (self.actual_input, self.actual_output, self.actual_gas)):
                raise ValueError(f"{self.outcome} evidence must not carry actual amounts")
        return self

    def receipt(self) -> ActionReceipt:
        return ActionReceipt(
            action_id=self.action_id, binding=self.binding, outcome=self.outcome,
            actual_input=self.actual_input, actual_output=self.actual_output, actual_gas=self.actual_gas)

    def fingerprint(self) -> str:
        """A stable identity for the economic outcome, independent of arrival time.

        Re-delivering the same outcome applies accounting once. A different
        outcome or actual value produces a different fingerprint and is handled
        as new evidence, not merged.
        """
        payload = {
            "action_id": self.action_id,
            "binding": self.binding.model_dump(mode="json"),
            "operation": self.operation,
            "revision_id": self.revision_id,
            "policy_binding": self.policy_binding,
            "payload_hash": self.payload_hash,
            "outcome": self.outcome,
            "actual_input": self.actual_input.model_dump(mode="json") if self.actual_input else None,
            "actual_output": self.actual_output.model_dump(mode="json") if self.actual_output else None,
            "actual_gas": self.actual_gas.model_dump(mode="json") if self.actual_gas else None,
        }
        return "sha256:" + hashlib.sha256(record_contract.canonical_bytes(payload)).hexdigest()


class RecoveryEvidenceView(StrictModel):
    evidence_id: uuid.UUID
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    outcome: str
    state: str
    rejection_reason: str | None
    source_ref: str
    observed_at: str
    created_at: str


class RecoveryCaseView(StrictModel):
    """Owner-scoped view of one original action's recovery record."""

    case_id: uuid.UUID
    owner_id: uuid.UUID
    action_id: str
    agent_id: str
    wallet_id: str
    network_id: str
    operation: str
    revision_id: str
    policy_binding: str
    payload_hash: str
    state: str
    blocking_reason: str | None
    decision_status: str
    queue_state: str | None
    claim_held: bool
    delayed_exit: bool
    opened_at: str
    updated_at: str
    reconciled_at: str | None
    evidence: list[RecoveryEvidenceView] = Field(default_factory=list)
    # The allowance an approve -> swap -> revoke action may have left open; None for a single-swap action.
    allowance: dict[str, Any] | None = None

    def known_outcome(self) -> str | None:
        return self.state if self.state in {"CONFIRMED", "REVERTED", "DENIED_UNSENT"} else None


class RecoveryResult(StrictModel):
    """The result of one recovery attempt, with duplicate and blocking flags."""

    case: RecoveryCaseView
    applied: bool
    duplicate: bool
    decision_status: str
    detail: str | None = None
