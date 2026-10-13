"""Proposal-only P10 evidence-package validation, isolated from Hermes wiring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class ProposedToolAttempt:
    contract_ref: str
    request_id: str
    occurred_at: datetime
    outcome: str  # SUCCEEDED, FAILED, or DENIED
    response_hash: str | None
    usage_ref: str | None

    def is_usable(self) -> bool:
        return (
            bool(self.contract_ref)
            and bool(self.request_id)
            and _is_utc(self.occurred_at)
            and self.outcome in {"SUCCEEDED", "FAILED", "DENIED"}
            and (self.outcome != "SUCCEEDED" or (bool(self.response_hash) and bool(self.usage_ref)))
        )


@dataclass(frozen=True)
class ProposedSourceObservation:
    source_uri: str
    retrieved_at: datetime
    content_hash: str
    coverage_ref: str
    published_at: datetime | None = None

    def is_usable(self) -> bool:
        return (
            bool(self.source_uri)
            and bool(self.content_hash)
            and bool(self.coverage_ref)
            and _is_utc(self.retrieved_at)
            and (self.published_at is None or _is_utc(self.published_at))
        )


@dataclass(frozen=True)
class ProposedNumericalFinding:
    calculation_ref: str
    units: str
    value: Decimal | None
    denominator: Decimal | None
    coverage: Decimal | None
    reconciliation_ref: str | None

    def is_usable(self) -> bool:
        return (
            bool(self.calculation_ref)
            and bool(self.units)
            and self.value is not None
            and self.value.is_finite()
            and self.denominator is not None
            and self.denominator.is_finite()
            and self.denominator > 0
            and self.coverage is not None
            and self.coverage.is_finite()
            and Decimal(0) < self.coverage <= Decimal(1)
            and bool(self.reconciliation_ref)
        )


@dataclass(frozen=True)
class ProposedEvidenceAssessment:
    status: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProposedEvidencePackage:
    """All references required for a future source-backed P10 finding.

    Free-form source text is intentionally just data here: this pure module has
    no tool, wallet, provider, or persistence capability.
    """

    declaration_ref: str
    attempt: ProposedToolAttempt
    sources: tuple[ProposedSourceObservation, ...]
    interpretation_ref: str | None
    contrary_evidence_refs: tuple[str, ...]
    numerical_finding: ProposedNumericalFinding | None
    report_ref: str
    zero_candidate: bool = False

    def assess(self) -> ProposedEvidenceAssessment:
        reasons: list[str] = []
        if not self.declaration_ref:
            reasons.append("DECLARATION_UNAVAILABLE")
        if not self.attempt.is_usable() or self.attempt.outcome != "SUCCEEDED":
            reasons.append("TOOL_CALL_UNAVAILABLE")
        if not self.sources or any(not source.is_usable() for source in self.sources):
            reasons.append("SOURCE_UNAVAILABLE")
        if not self.interpretation_ref:
            reasons.append("INTERPRETATION_UNSUPPORTED")
        if self.zero_candidate:
            if self.numerical_finding is not None:
                reasons.append("ZERO_CANDIDATE_WITH_NUMERIC_FINDING")
            if not self.report_ref:
                reasons.append("PERSISTENCE_UNAVAILABLE")
            return ProposedEvidenceAssessment("ZERO_CANDIDATE_UNRESOLVED" if not reasons else "UNAVAILABLE", tuple(reasons))
        if self.numerical_finding is None or not self.numerical_finding.is_usable():
            reasons.append("EVALUATION_UNAVAILABLE")
        if not self.contrary_evidence_refs:
            reasons.append("CONTRARY_EVIDENCE_UNAVAILABLE")
        if not self.report_ref:
            reasons.append("PERSISTENCE_UNAVAILABLE")
        return ProposedEvidenceAssessment("PROPOSED_COMPLETE" if not reasons else "UNAVAILABLE", tuple(reasons))


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)
