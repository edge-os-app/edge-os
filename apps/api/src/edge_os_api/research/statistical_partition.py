"""Pure chronological-boundary and one-shot-holdout guards for STAT-Q01."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from edge_os_api.research.statistical_preparation import (
    FrozenComparisonFamily,
    ProtectedHoldoutDecision,
    ScheduledObservation,
    ValidationFinalist,
    confirm_protected_holdout,
    frozen_family_sha256,
)


FROZEN_HOLDOUT_ALPHA = Decimal("0.05")


@dataclass(frozen=True)
class OutcomeWindow:
    """A retained outcome window and the revision that produced its response."""

    slot_id: str
    started_at: datetime
    ended_at: datetime
    outcome_revision_id: str


@dataclass(frozen=True)
class PartitionValidation:
    """Schedule-derived validation status and immutable family lineage."""

    status: str
    retained_slot_count: int
    reasons: tuple[str, ...]
    slot_statuses: Mapping[str, str]
    family_id: str
    partition_id: str
    family_hash: str
    comparison_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProtectedHoldoutAccess:
    """One immutable access state; access begins before an outcome label is read."""

    comparison_id: str
    revision_id: str
    status: str
    decision_status: str | None = None


@dataclass(frozen=True)
class ProtectedHoldoutLedger:
    """Pure state a future adopted runtime must persist transactionally."""

    profile_hash: str
    plan_hash: str
    family_hash: str
    comparison_ids: tuple[str, ...]
    protected_partition_id: str
    finalist_id: str
    finalist_revision_id: str
    outcome_control_test_hash: str
    alpha: Decimal
    accesses: tuple[ProtectedHoldoutAccess, ...]


@dataclass(frozen=True)
class HoldoutAccessRequest:
    """The full frozen lineage checked before a protected label is accessed."""

    comparison_id: str
    revision_id: str
    profile_hash: str
    plan_hash: str
    family_hash: str
    protected_partition_id: str
    outcome_control_test_hash: str


@dataclass(frozen=True)
class HoldoutAccessStart:
    """A pre-label access transition and the ledger it consumes."""

    status: str
    ledger: ProtectedHoldoutLedger


@dataclass(frozen=True)
class HoldoutConfirmation:
    """A resolved protected-label outcome and its consumed immutable state."""

    decision: ProtectedHoldoutDecision
    ledger: ProtectedHoldoutLedger


def validate_validation_windows(
    family: FrozenComparisonFamily,
    windows: Mapping[str, OutcomeWindow],
    *,
    validation_starts_at: datetime,
    protected_starts_at: datetime,
) -> PartitionValidation:
    """Derive the complete schedule from a frozen family, never caller slot filtering."""
    if not _is_utc(validation_starts_at) or not _is_utc(protected_starts_at) or validation_starts_at >= protected_starts_at:
        raise ValueError("validation and protected bounds must be ordered aware UTC instants")
    if not isinstance(windows, Mapping):
        raise ValueError("outcome windows must be a mapping keyed by canonical slot identity")
    slot_ids = _canonical_schedule(family)
    family_hash = frozen_family_sha256(family)
    statuses: dict[str, str] = {}
    reasons: list[str] = []
    expected = set(slot_ids)
    for slot_id in slot_ids:
        window = windows.get(slot_id)
        if window is None:
            statuses[slot_id] = "MISSING_WINDOW"
            reasons.append(slot_id)
        elif not isinstance(window, OutcomeWindow):
            statuses[slot_id] = "INVALID_WINDOW"
            reasons.append(slot_id)
        elif window.slot_id != slot_id or not _is_identity(window.outcome_revision_id):
            statuses[slot_id] = "INVALID_IDENTITY"
            reasons.append(slot_id)
        elif not _is_utc(window.started_at) or not _is_utc(window.ended_at) or window.ended_at <= window.started_at:
            statuses[slot_id] = "INVALID_WINDOW"
            reasons.append(slot_id)
        elif window.started_at < validation_starts_at:
            statuses[slot_id] = "BEFORE_VALIDATION"
            reasons.append(slot_id)
        elif window.ended_at > protected_starts_at:
            statuses[slot_id] = "REACHES_HOLDOUT"
            reasons.append(slot_id)
        else:
            statuses[slot_id] = "VALID"
    extras = tuple(sorted(str(slot_id) for slot_id in windows if slot_id not in expected))
    if extras:
        reasons.extend(extras)
    if all(status == "VALID" for status in statuses.values()) and not extras:
        status = "VALID"
    elif any(status == "MISSING_WINDOW" for status in statuses.values()):
        status = "UNRESOLVED_PARTITION_SLOT_MISSING"
    elif extras:
        status = "UNRESOLVED_PARTITION_SLOT_EXTRA"
    elif any(status == "INVALID_IDENTITY" for status in statuses.values()):
        status = "UNRESOLVED_PARTITION_IDENTITY"
    elif any(status == "INVALID_WINDOW" for status in statuses.values()):
        status = "UNRESOLVED_PARTITION_WINDOW_INVALID"
    elif any(status == "BEFORE_VALIDATION" for status in statuses.values()):
        status = "UNRESOLVED_OUTCOME_BEFORE_VALIDATION"
    else:
        status = "UNRESOLVED_OUTCOME_REACHES_HOLDOUT"
    return PartitionValidation(
        status, len(slot_ids), tuple(sorted(set(reasons))), statuses,
        family.family_id, family.partition_id, family_hash,
        tuple(comparison.comparison_id for comparison in family.comparisons),
    )


def prepare_protected_holdout_ledger(
    selection: ValidationFinalist,
    *,
    profile_hash: str,
    plan_hash: str,
    partition: PartitionValidation,
    protected_partition_id: str,
    finalist_revision_id: str,
    outcome_control_test_hash: str,
) -> ProtectedHoldoutLedger:
    """Bind one future confirmation to a successfully checked frozen lineage."""
    if not _selection_is_usable(selection):
        raise ValueError("a selected finalist contained exactly once in its eligible family is required")
    if not isinstance(partition, PartitionValidation) or partition.status != "VALID" or not _is_sha256(partition.family_hash):
        raise ValueError("a valid schedule-derived partition lineage is required")
    if not _selection_matches_family(selection, partition.family_hash, partition.comparison_ids):
        raise ValueError("the selected finalist must be bound to the exact checked family")
    hashes = (profile_hash, plan_hash, partition.family_hash, outcome_control_test_hash)
    if not all(_is_sha256(value) for value in hashes):
        raise ValueError("holdout profile, plan, family, and outcome-test identities must be SHA-256 values")
    if not _is_identity(protected_partition_id) or not _is_identity(finalist_revision_id):
        raise ValueError("protected partition and finalist revision identities are required")
    assert selection.finalist_id is not None
    return ProtectedHoldoutLedger(
        profile_hash, plan_hash, partition.family_hash, partition.comparison_ids, protected_partition_id, selection.finalist_id,
        finalist_revision_id, outcome_control_test_hash, FROZEN_HOLDOUT_ALPHA, (),
    )


def begin_protected_holdout(
    ledger: ProtectedHoldoutLedger,
    selection: ValidationFinalist,
    request: HoldoutAccessRequest,
) -> HoldoutAccessStart:
    """Append the sole valid pre-label transition after checking every lineage field."""
    if not _ledger_is_usable(ledger):
        return HoldoutAccessStart("UNRESOLVED_HOLDOUT_LINEAGE_INVALID", ledger)
    if ledger.accesses:
        return HoldoutAccessStart("UNRESOLVED_HOLDOUT_ALREADY_ACCESSED", ledger)
    if not _selection_is_usable(selection):
        return HoldoutAccessStart("UNRESOLVED_NO_FINALIST", ledger)
    if not _selection_matches_family(selection, ledger.family_hash, ledger.comparison_ids):
        return HoldoutAccessStart("UNRESOLVED_HOLDOUT_SELECTION_FAMILY_MISMATCH", ledger)
    if selection.finalist_id != ledger.finalist_id:
        return HoldoutAccessStart("UNRESOLVED_NO_FINALIST", ledger)
    if not isinstance(request, HoldoutAccessRequest):
        return HoldoutAccessStart("UNRESOLVED_HOLDOUT_LINEAGE_MISMATCH", ledger)
    if request.comparison_id != ledger.finalist_id:
        return HoldoutAccessStart("UNRESOLVED_HOLDOUT_WRONG_FINALIST", ledger)
    if request.revision_id != ledger.finalist_revision_id:
        return HoldoutAccessStart("UNRESOLVED_HOLDOUT_REVISION_MISMATCH", ledger)
    if not _request_matches_ledger(request, ledger):
        return HoldoutAccessStart("UNRESOLVED_HOLDOUT_LINEAGE_MISMATCH", ledger)
    access = ProtectedHoldoutAccess(request.comparison_id, request.revision_id, "ACCESS_STARTED")
    return HoldoutAccessStart("ACCESS_STARTED", _append_access(ledger, access))


def resolve_protected_holdout(
    ledger: ProtectedHoldoutLedger,
    *,
    pvalue: Decimal | None,
    outcome_control_test_hash: str,
) -> HoldoutConfirmation:
    """Resolve only an intact started lineage; every label-read result remains consumed."""
    if not _ledger_is_usable(ledger):
        return _unresolved_confirmation("UNRESOLVED_HOLDOUT_LINEAGE_INVALID", ledger, pvalue)
    if len(ledger.accesses) != 1 or not _started_access_matches_ledger(ledger.accesses[0], ledger):
        return _unresolved_confirmation("UNRESOLVED_HOLDOUT_NOT_STARTED", ledger, pvalue)
    if outcome_control_test_hash != ledger.outcome_control_test_hash:
        decision = ProtectedHoldoutDecision(
            "UNRESOLVED_HOLDOUT_LINEAGE_MISMATCH", ledger.finalist_id, ledger.finalist_id, pvalue,
        )
    else:
        selection = ValidationFinalist("SELECTED", ledger.finalist_id, (ledger.finalist_id,), ledger.family_hash)
        decision = confirm_protected_holdout(
            selection, comparison_id=ledger.finalist_id, pvalue=pvalue, alpha=ledger.alpha,
        )
    access = ProtectedHoldoutAccess(ledger.finalist_id, ledger.finalist_revision_id, "RESOLVED", decision.status)
    return HoldoutConfirmation(decision, _append_access(ledger, access))


def _append_access(ledger: ProtectedHoldoutLedger, access: ProtectedHoldoutAccess) -> ProtectedHoldoutLedger:
    return ProtectedHoldoutLedger(
        ledger.profile_hash, ledger.plan_hash, ledger.family_hash, ledger.comparison_ids, ledger.protected_partition_id,
        ledger.finalist_id, ledger.finalist_revision_id, ledger.outcome_control_test_hash,
        ledger.alpha, ledger.accesses + (access,),
    )


def _canonical_schedule(family: FrozenComparisonFamily) -> tuple[str, ...]:
    if not isinstance(family, FrozenComparisonFamily) or not _is_identity(family.family_id) or not _is_identity(family.partition_id):
        raise ValueError("a frozen family with non-empty canonical identities is required")
    if not family.comparisons or len({item.comparison_id for item in family.comparisons}) != len(family.comparisons):
        raise ValueError("the frozen family needs uniquely named comparisons")
    if any(not _is_identity(item.comparison_id) for item in family.comparisons):
        raise ValueError("the frozen family needs non-empty comparison identities")
    first = tuple(_observation_slot_id(item) for item in family.comparisons[0].observations)
    if not first or len(set(first)) != len(first):
        raise ValueError("the frozen family needs unique non-empty canonical scheduled slots")
    if any(tuple(_observation_slot_id(item) for item in comparison.observations) != first
           for comparison in family.comparisons[1:]):
        raise ValueError("every frozen comparison must retain the same canonical ordered schedule")
    return first


def _selection_is_usable(selection: object) -> bool:
    return (
        isinstance(selection, ValidationFinalist)
        and selection.status == "SELECTED"
        and _is_identity(selection.finalist_id)
        and isinstance(selection.eligible_ids, tuple)
        and selection.eligible_ids.count(selection.finalist_id) == 1
        and len(set(selection.eligible_ids)) == len(selection.eligible_ids)
        and all(_is_identity(candidate_id) for candidate_id in selection.eligible_ids)
        and _is_sha256(selection.family_hash)
    )


def _selection_matches_family(
    selection: ValidationFinalist,
    family_hash: str,
    comparison_ids: tuple[str, ...],
) -> bool:
    return (
        selection.family_hash == family_hash
        and _comparison_ids_are_usable(comparison_ids)
        and selection.finalist_id in comparison_ids
        and set(selection.eligible_ids).issubset(comparison_ids)
    )


def _ledger_is_usable(ledger: object) -> bool:
    return (
        isinstance(ledger, ProtectedHoldoutLedger)
        and all(_is_sha256(value) for value in (
            ledger.profile_hash, ledger.plan_hash, ledger.family_hash, ledger.outcome_control_test_hash,
        ))
        and _comparison_ids_are_usable(ledger.comparison_ids)
        and _is_identity(ledger.protected_partition_id)
        and _is_identity(ledger.finalist_id)
        and _is_identity(ledger.finalist_revision_id)
        and ledger.alpha == FROZEN_HOLDOUT_ALPHA
        and isinstance(ledger.accesses, tuple)
    )


def _request_matches_ledger(request: HoldoutAccessRequest, ledger: ProtectedHoldoutLedger) -> bool:
    return (
        request.profile_hash == ledger.profile_hash
        and request.plan_hash == ledger.plan_hash
        and request.family_hash == ledger.family_hash
        and request.protected_partition_id == ledger.protected_partition_id
        and request.outcome_control_test_hash == ledger.outcome_control_test_hash
    )


def _started_access_matches_ledger(access: object, ledger: ProtectedHoldoutLedger) -> bool:
    return (
        isinstance(access, ProtectedHoldoutAccess)
        and access.status == "ACCESS_STARTED"
        and access.decision_status is None
        and access.comparison_id == ledger.finalist_id
        and access.revision_id == ledger.finalist_revision_id
    )


def _unresolved_confirmation(
    status: str,
    ledger: ProtectedHoldoutLedger,
    pvalue: Decimal | None,
) -> HoldoutConfirmation:
    return HoldoutConfirmation(
        ProtectedHoldoutDecision(status, ledger.finalist_id, ledger.finalist_id, pvalue), ledger,
    )


def _observation_slot_id(observation: object) -> str:
    if not isinstance(observation, ScheduledObservation) or not _is_identity(observation.slot_id):
        raise ValueError("the frozen family needs unique non-empty canonical scheduled slots")
    return observation.slot_id


def _is_identity(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _comparison_ids_are_usable(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and bool(value)
        and len(set(value)) == len(value)
        and all(_is_identity(comparison_id) for comparison_id in value)
    )


def _is_utc(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() == timedelta(0)
