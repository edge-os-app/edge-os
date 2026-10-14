from datetime import datetime, timezone
from decimal import Decimal

from edge_os_api.research.proposed_evidence_package import (
    ProposedEvidencePackage,
    ProposedNumericalFinding,
    ProposedSourceObservation,
    ProposedToolAttempt,
)


NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def _package(**changes: object) -> ProposedEvidencePackage:
    values: dict[str, object] = {
        "declaration_ref": "p08:revision-1",
        "attempt": ProposedToolAttempt("tool-contract:v1", "attempt-1", NOW, "SUCCEEDED", "sha256:response", "usage:1"),
        "sources": (ProposedSourceObservation("https://primary.example/report", NOW, "sha256:source", "coverage:v1"),),
        "interpretation_ref": "interpretation:v1", "contrary_evidence_refs": ("source:contrary",),
        "numerical_finding": ProposedNumericalFinding("calc:v1", "USD", Decimal("2"), Decimal("10"), Decimal("0.8"), "reconcile:v1"),
        "report_ref": "report:v1",
    }
    values.update(changes)
    return ProposedEvidencePackage(**values)  # type: ignore[arg-type]


def test_reference_presence_requires_every_identity_without_claiming_runtime_completion() -> None:
    assert _package().assess().status == "REFERENCES_PRESENT"
    assessment = _package(declaration_ref="", interpretation_ref=None, report_ref="").assess()
    assert assessment.status == "UNAVAILABLE"
    assert assessment.reasons == ("DECLARATION_UNAVAILABLE", "INTERPRETATION_UNSUPPORTED", "PERSISTENCE_UNAVAILABLE")


def test_source_or_tool_failure_never_becomes_a_finding() -> None:
    failed = _package(attempt=ProposedToolAttempt("tool", "request", NOW, "FAILED", None, None), sources=()).assess()
    assert failed.status == "UNAVAILABLE"
    assert failed.reasons == ("TOOL_CALL_UNAVAILABLE", "SOURCE_UNAVAILABLE")


def test_success_without_usage_lineage_is_unavailable() -> None:
    assessment = _package(
        attempt=ProposedToolAttempt("tool", "request", NOW, "SUCCEEDED", "sha256:response", None),
    ).assess()
    assert assessment.status == "UNAVAILABLE"
    assert assessment.reasons == ("TOOL_CALL_UNAVAILABLE",)


def test_invalid_numeric_finding_is_distinct_from_zero() -> None:
    unavailable = _package(numerical_finding=ProposedNumericalFinding("calc", "USD", None, Decimal("1"), Decimal("1"), "reconcile")).assess()
    zero = _package(numerical_finding=ProposedNumericalFinding("calc", "USD", Decimal("0"), Decimal("1"), Decimal("1"), "reconcile")).assess()
    assert unavailable.reasons == ("EVALUATION_UNAVAILABLE",)
    assert zero.status == "REFERENCES_PRESENT"
    assert _package(contrary_evidence_refs=()).assess().reasons == ("CONTRARY_EVIDENCE_UNAVAILABLE",)


def test_zero_candidate_is_reference_unresolved_not_a_forced_strategy() -> None:
    result = _package(zero_candidate=True, numerical_finding=None).assess()
    assert result == result.__class__("ZERO_CANDIDATE_REFERENCE_UNRESOLVED", ())
