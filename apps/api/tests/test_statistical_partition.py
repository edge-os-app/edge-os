from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

import pytest

from edge_os_api.research.statistical_partition import (
    FROZEN_HOLDOUT_ALPHA,
    HoldoutAccessRequest,
    OutcomeWindow,
    ProtectedHoldoutAccess,
    begin_protected_holdout,
    prepare_protected_holdout_ledger,
    resolve_protected_holdout,
    validate_validation_windows,
)
from edge_os_api.research.statistical_preparation import (
    FrozenComparison,
    FrozenComparisonFamily,
    ScheduledObservation,
    ValidationFinalist,
)


UTC = timezone.utc
SPLIT = datetime(2026, 1, 2, tzinfo=UTC)
VALIDATION_START = SPLIT - timedelta(days=1)


def _window(
    slot_id: str,
    *,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    revision_id: str = "outcomes-v1",
) -> OutcomeWindow:
    return OutcomeWindow(slot_id, starts_at or SPLIT - timedelta(minutes=35), ends_at or SPLIT, revision_id)


def _family(slot_ids: tuple[str, ...] = ("s0", "s1")) -> FrozenComparisonFamily:
    comparison = FrozenComparison(
        "primary",
        tuple(ScheduledObservation(slot_id, "CONTROL", Decimal(0)) for slot_id in slot_ids),
    )
    return FrozenComparisonFamily(
        "validation-family", "validation-partition", 1_800, 60, 300, (comparison,),
    )


def _hash(name: str) -> str:
    return sha256(name.encode()).hexdigest()


def _request(ledger, *, comparison_id: str = "positive", revision_id: str = "positive-v1", **changes):
    values = {
        "comparison_id": comparison_id,
        "revision_id": revision_id,
        "profile_hash": ledger.profile_hash,
        "plan_hash": ledger.plan_hash,
        "family_hash": ledger.family_hash,
        "protected_partition_id": ledger.protected_partition_id,
        "outcome_control_test_hash": ledger.outcome_control_test_hash,
    }
    values.update(changes)
    return HoldoutAccessRequest(**values)


def test_partition_guard_requires_every_retained_slot_and_excludes_windows_reaching_holdout() -> None:
    family = _family()
    missing = validate_validation_windows(
        family, {"s0": _window("s0")}, validation_starts_at=VALIDATION_START,
        protected_starts_at=SPLIT,
    )
    leaks = validate_validation_windows(
        family, {"s0": _window("s0"), "s1": _window("s1", ends_at=SPLIT + timedelta(seconds=1))},
        validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )
    prehistory = validate_validation_windows(
        _family(("s0",)), {"s0": _window("s0", starts_at=VALIDATION_START - timedelta(seconds=1))},
        validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )
    control = validate_validation_windows(
        family, {"s0": _window("s0"), "s1": _window("s1")},
        validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )

    assert missing.status == "UNRESOLVED_PARTITION_SLOT_MISSING"
    assert leaks.status == "UNRESOLVED_OUTCOME_REACHES_HOLDOUT"
    assert prehistory.status == "UNRESOLVED_OUTCOME_BEFORE_VALIDATION"
    assert control.status == "VALID"
    assert control.slot_statuses == {"s0": "VALID", "s1": "VALID"}
    assert len(control.family_hash) == 64


def test_partition_guard_derives_the_complete_schedule_and_rejects_filtered_or_inconsistent_family_rows() -> None:
    family = _family()
    filtered = validate_validation_windows(
        family, {"s0": _window("s0")}, validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )
    inconsistent = replace(
        family,
        comparisons=(
            family.comparisons[0],
            FrozenComparison("other", (ScheduledObservation("s0", "CONTROL", Decimal(0)),)),
        ),
    )

    assert filtered.status == "UNRESOLVED_PARTITION_SLOT_MISSING"
    assert filtered.slot_statuses["s1"] == "MISSING_WINDOW"
    with pytest.raises(ValueError, match="canonical ordered schedule"):
        validate_validation_windows(
            inconsistent, {"s0": _window("s0")}, validation_starts_at=VALIDATION_START,
            protected_starts_at=SPLIT,
        )


def test_partition_guard_retains_extra_and_malformed_window_evidence_as_unresolved() -> None:
    family = _family()
    malformed = validate_validation_windows(
        family, {"s0": object(), "s1": _window("s1")}, validation_starts_at=VALIDATION_START,
        protected_starts_at=SPLIT,
    )
    extra = validate_validation_windows(
        family, {"s0": _window("s0"), "s1": _window("s1"), "outside": _window("outside")},
        validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )

    assert malformed.status == "UNRESOLVED_PARTITION_WINDOW_INVALID"
    assert malformed.slot_statuses["s0"] == "INVALID_WINDOW"
    assert extra.status == "UNRESOLVED_PARTITION_SLOT_EXTRA"
    assert extra.reasons == ("outside",)


def test_holdout_ledger_allows_one_exact_finalist_revision_and_never_promotes_a_runner_up() -> None:
    selection = ValidationFinalist("SELECTED", "positive", ("positive", "runner-up"))
    partition = validate_validation_windows(
        _family(), {"s0": _window("s0"), "s1": _window("s1")},
        validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )
    ledger = prepare_protected_holdout_ledger(
        selection, profile_hash=_hash("profile"), plan_hash=_hash("plan"), partition=partition,
        protected_partition_id="holdout-v1", finalist_revision_id="positive-v1",
        outcome_control_test_hash=_hash("outcome-control-test"),
    )
    started = begin_protected_holdout(ledger, selection, _request(ledger))
    first = resolve_protected_holdout(
        started.ledger, pvalue=Decimal("0.20"), outcome_control_test_hash=ledger.outcome_control_test_hash,
    )
    wrong_finalist = begin_protected_holdout(
        ledger, selection, _request(ledger, comparison_id="runner-up", revision_id="runner-up-v1"),
    )
    runner_up = begin_protected_holdout(
        first.ledger, selection, _request(ledger, comparison_id="runner-up", revision_id="runner-up-v1"),
    )
    relabeled = begin_protected_holdout(ledger, selection, _request(ledger, revision_id="positive-v2"))

    assert started.status == "ACCESS_STARTED"
    assert first.decision.status == "UNRESOLVED_HOLDOUT_FAILED"
    assert tuple(event.status for event in first.ledger.accesses) == ("ACCESS_STARTED", "RESOLVED")
    assert wrong_finalist.status == "UNRESOLVED_HOLDOUT_WRONG_FINALIST"
    assert runner_up.status == "UNRESOLVED_HOLDOUT_ALREADY_ACCESSED"
    assert relabeled.status == "UNRESOLVED_HOLDOUT_REVISION_MISMATCH"
    assert first.ledger.alpha == FROZEN_HOLDOUT_ALPHA


def test_holdout_lineage_rejects_unchecked_partitions_mismatch_and_forged_starts() -> None:
    selection = ValidationFinalist("SELECTED", "positive", ("positive",))
    valid = validate_validation_windows(
        _family(), {"s0": _window("s0"), "s1": _window("s1")},
        validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )
    invalid = validate_validation_windows(
        _family(), {"s0": _window("s0")}, validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )
    with pytest.raises(ValueError, match="valid schedule-derived partition"):
        prepare_protected_holdout_ledger(
            selection, profile_hash=_hash("profile"), plan_hash=_hash("plan"), partition=invalid,
            protected_partition_id="holdout-v1", finalist_revision_id="positive-v1",
            outcome_control_test_hash=_hash("outcome"),
        )
    ledger = prepare_protected_holdout_ledger(
        selection, profile_hash=_hash("profile"), plan_hash=_hash("plan"), partition=valid,
        protected_partition_id="holdout-v1", finalist_revision_id="positive-v1",
        outcome_control_test_hash=_hash("outcome"),
    )
    mismatch = begin_protected_holdout(ledger, selection, _request(ledger, plan_hash=_hash("other-plan")))
    started = begin_protected_holdout(ledger, selection, _request(ledger))
    changed_outcome = resolve_protected_holdout(
        started.ledger, pvalue=Decimal("0.01"), outcome_control_test_hash=_hash("other-outcome"),
    )
    forged = replace(
        ledger,
        accesses=(ProtectedHoldoutAccess("runner-up", "runner-up-v1", "ACCESS_STARTED"),),
    )
    forged_result = resolve_protected_holdout(
        forged, pvalue=Decimal("0.01"), outcome_control_test_hash=ledger.outcome_control_test_hash,
    )

    assert mismatch.status == "UNRESOLVED_HOLDOUT_LINEAGE_MISMATCH"
    assert changed_outcome.decision.status == "UNRESOLVED_HOLDOUT_LINEAGE_MISMATCH"
    assert tuple(event.status for event in changed_outcome.ledger.accesses) == ("ACCESS_STARTED", "RESOLVED")
    assert forged_result.decision.status == "UNRESOLVED_HOLDOUT_NOT_STARTED"


def test_holdout_resolves_success_and_insufficiency_as_append_only_consumed_attempts() -> None:
    selection = ValidationFinalist("SELECTED", "positive", ("positive",))
    partition = validate_validation_windows(
        _family(), {"s0": _window("s0"), "s1": _window("s1")},
        validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )
    ledger = prepare_protected_holdout_ledger(
        selection, profile_hash=_hash("profile"), plan_hash=_hash("plan"), partition=partition,
        protected_partition_id="holdout-v1", finalist_revision_id="positive-v1",
        outcome_control_test_hash=_hash("outcome"),
    )
    success_start = begin_protected_holdout(ledger, selection, _request(ledger))
    success = resolve_protected_holdout(
        success_start.ledger, pvalue=Decimal("0.01"), outcome_control_test_hash=ledger.outcome_control_test_hash,
    )
    insufficient_start = begin_protected_holdout(ledger, selection, _request(ledger))
    insufficient = resolve_protected_holdout(
        insufficient_start.ledger, pvalue=None, outcome_control_test_hash=ledger.outcome_control_test_hash,
    )

    assert success.decision.status == "CANDIDATE_HOLDOUT_CONFIRMED"
    assert insufficient.decision.status == "UNRESOLVED_HOLDOUT_INSUFFICIENT"
    assert all(tuple(event.status for event in result.ledger.accesses) == ("ACCESS_STARTED", "RESOLVED")
               for result in (success, insufficient))


def test_holdout_rejects_a_selected_identifier_absent_from_its_eligible_family() -> None:
    partition = validate_validation_windows(
        _family(), {"s0": _window("s0"), "s1": _window("s1")},
        validation_starts_at=VALIDATION_START, protected_starts_at=SPLIT,
    )
    invalid_selection = ValidationFinalist("SELECTED", "positive", ("runner-up",))

    with pytest.raises(ValueError, match="contained exactly once"):
        prepare_protected_holdout_ledger(
            invalid_selection, profile_hash=_hash("profile"), plan_hash=_hash("plan"), partition=partition,
            protected_partition_id="holdout-v1", finalist_revision_id="positive-v1",
            outcome_control_test_hash=_hash("outcome"),
        )
