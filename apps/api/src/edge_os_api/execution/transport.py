"""Labelled local fixture submission transport for the P23 local stage.

This module is a local fixture. It is not a Kuru, Privy or RPC transport, and it
never signs, broadcasts or calls a provider. Its only job is to give the queue
a submission-capable boundary that records immutable local evidence and clearly
separates a definitely-unsent denial from a submission-possible/unknown result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from edge_os_api.admission.types import ActionIntent, AllowanceCap, ApprovalSnapshot
from edge_os_api.execution.types import AssetAmount


class FixtureAcknowledgementLost(Exception):
    """The fixture applied a possible effect and then lost its acknowledgement."""


class TransportOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    outcome: Literal["DEFINITELY_UNSENT", "SUBMISSION_POSSIBLE", "CONFIRMED", "REVERTED"]
    detail: str
    actual_input: AssetAmount | None = None
    actual_output: AssetAmount | None = None
    actual_gas: AssetAmount | None = None


@dataclass(frozen=True)
class PreparedSubmission:
    """The exact frozen payload a transport would receive. It is never mutated."""

    action_id: str
    owner_id: str
    wallet_id: str
    network_id: str
    operation: str
    payload_hash: str
    attempt_id: str | None = None  # the saved IN_FLIGHT attempt; set by the submission step


class SubmissionTransport(Protocol):
    transport_id: str

    def submit(self, prepared: PreparedSubmission) -> TransportOutcome: ...


class FixturePlan(BaseModel):
    """One authored local outcome. `lose_acknowledgement` marks a lost reply, not a definite send."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["ACCEPT", "DENY", "UNKNOWN", "REVERT"]
    detail: str = "local-fixture"
    actual_input: AssetAmount | None = None
    actual_output: AssetAmount | None = None
    actual_gas: AssetAmount | None = None
    lose_acknowledgement: bool = False


class LocalFixtureTransport:
    """A labelled local fixture transport with authored, per-action outcomes."""

    transport_id = "local-fixture/1"

    @staticmethod
    def authored_actuals(outcome: TransportOutcome, intent: ActionIntent, approval: ApprovalSnapshot) -> TransportOutcome:
        """Authored fixture amounts for a plan that names none: the intent's planned input/output and the approved
        per-action gas. Fixture input only; the generic settlement never substitutes planned values itself."""
        def cap(value: AllowanceCap) -> AssetAmount:
            return AssetAmount(asset_id=value.asset_id, raw=value.approved_raw, decimals=value.decimals)

        if intent.operation == "ENTRY":
            planned = (intent.input.quote_input, intent.quantity, cap(approval.per_action_gas))
        else:
            planned = (intent.quantity, intent.input.expected_quote, cap(approval.per_exit_gas))
        actual_input, actual_output, actual_gas = planned
        if outcome.outcome == "REVERTED":
            return outcome.model_copy(update={"actual_gas": outcome.actual_gas or actual_gas})
        return outcome.model_copy(update={"actual_input": outcome.actual_input or actual_input,
                                          "actual_output": outcome.actual_output or actual_output,
                                          "actual_gas": outcome.actual_gas or actual_gas})

    def __init__(self, plans: dict[str, FixturePlan], default: FixturePlan) -> None:
        self._plans = dict(plans)
        self._default = default

    def plan_for(self, action_id: str) -> FixturePlan:
        return self._plans.get(action_id, self._default)

    def submit(self, prepared: PreparedSubmission) -> TransportOutcome:
        plan = self.plan_for(prepared.action_id)
        if plan.lose_acknowledgement:
            raise FixtureAcknowledgementLost(prepared.action_id)
        if plan.mode == "DENY":
            return TransportOutcome(outcome="DEFINITELY_UNSENT", detail=plan.detail)
        if plan.mode == "UNKNOWN":
            return TransportOutcome(outcome="SUBMISSION_POSSIBLE", detail=plan.detail)
        if plan.mode == "REVERT":
            return TransportOutcome(outcome="REVERTED", detail=plan.detail, actual_gas=plan.actual_gas)
        return TransportOutcome(
            outcome="CONFIRMED", detail=plan.detail,
            actual_input=plan.actual_input, actual_output=plan.actual_output, actual_gas=plan.actual_gas)
