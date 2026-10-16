from __future__ import annotations

import pytest
from dataclasses import replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from random import Random

from edge_os_api.research.statistical_preparation import (
    FrozenComparison,
    FrozenComparisonFamily,
    EvaluationDeadlineExceeded,
    StatisticalPreparationProfile,
    ScheduledObservation,
    joint_stationary_bootstrap_indices,
    holm_rejections,
    select_validation_finalist,
    confirm_protected_holdout,
    evaluate_validation_family,
    schedule_overlap_floor,
    select_ppw_stationary_block_length,
    summarize_comparison,
)
from edge_os_api.strategies.compiler import NUMERIC


def test_schedule_overlap_floor_uses_full_response_span_not_only_horizon() -> None:
    assert schedule_overlap_floor(target_horizon_seconds=1_800, reference_window_seconds=60,
                                  decision_interval_seconds=300) == 7
    assert schedule_overlap_floor(target_horizon_seconds=600, reference_window_seconds=60,
                                  decision_interval_seconds=300) == 3
    with pytest.raises(ValueError):
        schedule_overlap_floor(target_horizon_seconds=0, reference_window_seconds=60,
                               decision_interval_seconds=300)


def test_summary_keeps_an_observed_zero_distinct_from_a_missing_outcome() -> None:
    comparison = FrozenComparison(
        "general",
        (
            ScheduledObservation("s0", "TRIGGERED", Decimal("0")),
            ScheduledObservation("s1", "TRIGGERED", None, "MISSING_END_REFERENCE"),
            ScheduledObservation("s2", "CONTROL", Decimal("0.20")),
            ScheduledObservation("s3", "EXCLUDED", Decimal("9"), "UNKNOWN_SIGNAL"),
        ),
    )

    summary = summarize_comparison(comparison)

    assert summary.scheduled_count == 4
    assert summary.triggered_observed == 1
    assert summary.triggered_missing == 1
    assert summary.control_observed == 1
    assert summary.triggered_mean == Decimal("0")
    assert summary.control_mean == Decimal("0.20")
    assert summary.contrast == Decimal("-0.20")
    assert summary.missing_reasons == {"MISSING_END_REFERENCE": 1}


def test_corrected_ppw_selector_reports_the_stationary_bootstrap_constant() -> None:
    random = Random(91)
    influence = tuple(Decimal(str(random.random() - 0.5)) for _ in range(128))

    selection = select_ppw_stationary_block_length(influence, overlap_floor=1)

    assert selection.status == "SELECTED"
    assert selection.selected_length is not None
    with localcontext(NUMERIC):
        assert selection.variance_constant == Decimal("2") * selection.long_run_variance ** 2
    assert selection.bandwidth is not None and selection.bandwidth % 2 == 0


def test_ppw_selector_matches_an_independent_symmetric_flat_top_reference() -> None:
    random = Random(91)
    influence = tuple(Decimal(str(random.random() - 0.5)) for _ in range(128))

    selection = select_ppw_stationary_block_length(influence, overlap_floor=7)
    expected = _reference_ppw(influence, overlap_floor=7)

    assert selection.status == "SELECTED"
    assert (selection.cutoff_lag, selection.bandwidth, selection.weighted_autocovariance,
            selection.long_run_variance, selection.variance_constant, selection.raw_length,
            selection.selected_length) == expected


def test_selector_returns_an_explicit_short_history_failure() -> None:
    selection = select_ppw_stationary_block_length((Decimal("1"),) * 12, overlap_floor=1)

    assert selection.status == "UNRESOLVED_SHORT_HISTORY"
    assert selection.selected_length is None


def test_joint_stationary_indices_are_seeded_circular_and_have_no_comparison_axis() -> None:
    first = joint_stationary_bootstrap_indices(population_size=7, expected_block_length=3, draws=5, seed=42)

    assert first == joint_stationary_bootstrap_indices(
        population_size=7, expected_block_length=3, draws=5, seed=42,
    )
    assert len(first) == 5
    assert all(len(draw) == 7 and all(0 <= index < 7 for index in draw) for draw in first)
    with pytest.raises(ValueError):
        joint_stationary_bootstrap_indices(population_size=0, expected_block_length=3, draws=5, seed=42)


def test_holm_keeps_the_complete_family_when_one_member_is_unavailable() -> None:
    assert holm_rejections(
        {"positive": Decimal("0.01"), "null": Decimal("0.03"), "negative": Decimal("0.04")},
        alpha=Decimal("0.05"),
    ) == {"positive": True, "null": False, "negative": False}
    assert holm_rejections(
        {"positive": Decimal("0.01"), "missing": None}, alpha=Decimal("0.05"),
    ) == {"positive": None, "missing": None}


def test_validation_family_preserves_an_incomplete_member_and_stays_unresolved() -> None:
    slots = tuple(f"s{index}" for index in range(128))
    complete = FrozenComparison(
        "complete",
        tuple(ScheduledObservation(slot, "TRIGGERED" if index % 2 else "CONTROL", Decimal(index) / Decimal("100"))
              for index, slot in enumerate(slots)),
    )
    incomplete = FrozenComparison(
        "incomplete",
        tuple(ScheduledObservation(slot, "TRIGGERED", None, "MISSING_OUTCOME") for slot in slots),
    )
    profile = StatisticalPreparationProfile(
        profile_id="test-profile", seed=7, bootstrap_draws=199, minimum_relevant_difference=Decimal("0.10"),
        family_alpha=Decimal("0.05"), pointwise_alpha=Decimal("0.05"), minimum_scheduled_slots=128,
        maximum_scheduled_slots=512, minimum_group_observations=16,
        minimum_group_coverage=Decimal("0.10"), minimum_draw_group_observations=2, maximum_comparisons=3,
    )
    family = FrozenComparisonFamily(
        family_id="family", partition_id="validation-a", target_horizon_seconds=1_800,
        reference_window_seconds=60, decision_interval_seconds=300, comparisons=(complete, incomplete),
    )

    result = evaluate_validation_family(profile, family)

    assert result.status == "UNRESOLVED_FAMILY_INCOMPLETE"
    assert result.comparisons["incomplete"].status == "UNRESOLVED_FEASIBILITY"
    assert result.comparisons["incomplete"].comparison.observations[0].response is None
    assert result.comparisons["complete"].summary.contrast is not None


def test_profile_rejects_a_family_larger_than_its_frozen_comparison_limit() -> None:
    slots = tuple(f"s{index}" for index in range(128))
    comparison = FrozenComparison(
        "one",
        tuple(ScheduledObservation(slot, "TRIGGERED" if index % 2 else "CONTROL", Decimal(index))
              for index, slot in enumerate(slots)),
    )
    profile = StatisticalPreparationProfile(
        profile_id="three-comparison-profile", seed=7, bootstrap_draws=1,
        minimum_relevant_difference=Decimal("0.10"), family_alpha=Decimal("0.05"),
        pointwise_alpha=Decimal("0.05"), minimum_scheduled_slots=128, maximum_scheduled_slots=512,
        minimum_group_observations=16, minimum_group_coverage=Decimal("0.10"),
        minimum_draw_group_observations=2, maximum_comparisons=3,
    )
    family = FrozenComparisonFamily(
        family_id="family", partition_id="validation-a", target_horizon_seconds=1_800,
        reference_window_seconds=60, decision_interval_seconds=300,
        comparisons=(
            comparison,
            replace(comparison, comparison_id="two"),
            replace(comparison, comparison_id="three"),
            replace(comparison, comparison_id="four"),
        ),
    )

    with pytest.raises(ValueError, match="frozen profile comparison limit"):
        evaluate_validation_family(profile, family)


def test_validation_family_bootstraps_the_complete_family_and_retains_each_sensitivity() -> None:
    random = Random(72)
    slots = tuple(f"s{index}" for index in range(128))
    groups = tuple("TRIGGERED" if random.random() < 0.5 else "CONTROL" for _ in slots)
    noise = tuple(Decimal(str((random.random() - 0.5) / 10)) for _ in slots)

    def comparison(comparison_id: str, effect: Decimal) -> FrozenComparison:
        return FrozenComparison(
            comparison_id,
            tuple(ScheduledObservation(slot, group, value + (effect if group == "TRIGGERED" else Decimal(0)))
                  for slot, group, value in zip(slots, groups, noise, strict=True)),
        )

    profile = StatisticalPreparationProfile(
        profile_id="test-profile", seed=73, bootstrap_draws=199, minimum_relevant_difference=Decimal("0.10"),
        family_alpha=Decimal("0.05"), pointwise_alpha=Decimal("0.05"), minimum_scheduled_slots=128,
        maximum_scheduled_slots=512, minimum_group_observations=16,
        minimum_group_coverage=Decimal("0.10"), minimum_draw_group_observations=2, maximum_comparisons=3,
    )
    family = FrozenComparisonFamily(
        family_id="family", partition_id="validation-a", target_horizon_seconds=1_800,
        reference_window_seconds=60, decision_interval_seconds=300,
        comparisons=(comparison("positive", Decimal("0.80")), comparison("null", Decimal("0")),
                     comparison("negative", Decimal("-0.80"))),
    )

    result = evaluate_validation_family(profile, family)

    assert result.status == "EVALUATED"
    assert result.selected_block_length is not None and result.selected_block_length >= 7
    assert set(result.family_holm_rejections) == {"HALF", "NOMINAL", "DOUBLE"}
    assert result.comparisons["positive"].candidate_eligible is True
    assert result.comparisons["negative"].candidate_eligible is False
    assert all(item.directional_pvalue is not None
               for item in result.comparisons["positive"].sensitivity_results.values())
    with pytest.raises(EvaluationDeadlineExceeded):
        evaluate_validation_family(profile, family, deadline=0.0)


def test_protected_holdout_cannot_promote_a_runner_up_after_finalist_failure() -> None:
    family = _selection_family("positive", "runner-up", "negative")
    selection = select_validation_finalist(
        {
            "positive": (Decimal("0.80"), True),
            "runner-up": (Decimal("0.60"), True),
            "negative": (Decimal("-0.80"), False),
        },
        family=family,
    )

    failed = confirm_protected_holdout(selection, comparison_id="positive", pvalue=Decimal("0.20"),
                                       alpha=Decimal("0.05"))
    substituted = confirm_protected_holdout(selection, comparison_id="runner-up", pvalue=Decimal("0.001"),
                                            alpha=Decimal("0.05"))

    assert selection.finalist_id == "positive"
    assert failed.status == "UNRESOLVED_HOLDOUT_FAILED"
    assert substituted.status == "UNRESOLVED_HOLDOUT_WRONG_FINALIST"


def test_finalist_selection_does_not_round_the_ordering_under_caller_precision() -> None:
    family = _selection_family("a-lower", "z-higher")
    candidates = {
        "a-lower": (Decimal("1.00000000000000000000000000001"), True),
        "z-higher": (Decimal("1.00000000000000000000000000002"), True),
    }

    with localcontext() as context:
        context.prec = 28
        low_precision = select_validation_finalist(candidates, family=family)
    with localcontext() as context:
        context.prec = 50
        high_precision = select_validation_finalist(candidates, family=family)

    assert low_precision == high_precision
    assert low_precision.finalist_id == "z-higher"


def test_validation_evaluation_ignores_the_callers_ambient_decimal_precision() -> None:
    slots = tuple(f"s{index}" for index in range(128))
    random = Random(83)
    noise = tuple(Decimal(str((random.random() - 0.5) / 100)) for _ in slots)
    comparison = FrozenComparison(
        "precision",
        tuple(ScheduledObservation(
            slot,
            "TRIGGERED" if index % 2 else "CONTROL",
            (Decimal("0.123456789123456789") if index % 2 else Decimal("0.023456789123456789")) + noise[index],
        ) for index, slot in enumerate(slots)),
    )
    profile = StatisticalPreparationProfile(
        profile_id="precision-profile", seed=19, bootstrap_draws=199,
        minimum_relevant_difference=Decimal("0.01"), family_alpha=Decimal("0.05"),
        pointwise_alpha=Decimal("0.05"), minimum_scheduled_slots=128, maximum_scheduled_slots=512,
        minimum_group_observations=16, minimum_group_coverage=Decimal("0.10"),
        minimum_draw_group_observations=2, maximum_comparisons=3,
    )
    family = FrozenComparisonFamily(
        family_id="precision-family", partition_id="validation-a", target_horizon_seconds=1_800,
        reference_window_seconds=60, decision_interval_seconds=300, comparisons=(comparison,),
    )

    with localcontext() as context:
        context.prec = 28
        low_precision = evaluate_validation_family(profile, family)
    with localcontext() as context:
        context.prec = 50
        high_precision = evaluate_validation_family(profile, family)

    assert low_precision == high_precision
    assert low_precision.status == "EVALUATED"


def _selection_family(*comparison_ids: str) -> FrozenComparisonFamily:
    return FrozenComparisonFamily(
        "selection-family", "validation-partition", 1_800, 60, 300,
        tuple(
            FrozenComparison(
                comparison_id, (ScheduledObservation("s0", "CONTROL", Decimal(0)),),
            )
            for comparison_id in comparison_ids
        ),
    )


def _reference_ppw(
    influence: tuple[Decimal, ...],
    *,
    overlap_floor: int,
) -> tuple[int, int, Decimal, Decimal, Decimal, Decimal, int]:
    """Independent literal transcription of the frozen PPW equations."""
    with localcontext(NUMERIC):
        size = len(influence)
        mean = sum(influence, Decimal(0)) / Decimal(size)
        covariance = tuple(
            sum((influence[index] - mean) * (influence[index + lag] - mean)
                for index in range(size - lag)) / Decimal(size)
            for lag in range(size)
        )
        limit = min(size // 4, 32)
        run = max(5, int((Decimal(size).ln() / Decimal(10).ln()).sqrt()))
        threshold = Decimal(2) * ((Decimal(size).ln() / Decimal(10).ln() / Decimal(size)).sqrt())
        cutoff = next(
            cutoff for cutoff in range(1, limit - run + 1)
            if all(abs(covariance[lag] / covariance[0]) < threshold
                   for lag in range(cutoff + 1, cutoff + run + 1))
        )
        bandwidth = 2 * cutoff

        def weight(lag: int) -> Decimal:
            ratio = Decimal(abs(lag)) / Decimal(bandwidth)
            return Decimal(1) if ratio <= Decimal("0.5") else Decimal(2) * (Decimal(1) - ratio)

        g_hat = sum((weight(lag) * Decimal(abs(lag)) * covariance[abs(lag)]
                     for lag in range(-bandwidth, bandwidth + 1)), Decimal(0))
        g_zero = sum((weight(lag) * covariance[abs(lag)] for lag in range(-bandwidth, bandwidth + 1)), Decimal(0))
        d_stationary = Decimal(2) * g_zero ** 2
        raw = ((Decimal(2) * g_hat ** 2 / d_stationary) * Decimal(size)).ln() / Decimal(3)
        raw = raw.exp()
        selected = max(overlap_floor, 1, int(raw.to_integral_value(rounding=ROUND_HALF_EVEN)))
        return cutoff, bandwidth, g_hat, g_zero, d_stationary, raw, selected
