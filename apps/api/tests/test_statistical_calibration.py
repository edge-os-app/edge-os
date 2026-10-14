from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from edge_os_api.research.statistical_calibration import (
    CalibrationRepetition,
    CalibrationLimits,
    CalibrationScenario,
    ExperimentResult,
    _assess_experiment,
    generate_synthetic_family,
    frozen_calibration_profile,
    run_bounded_calibration,
    run_experiment,
    run_failure_fixtures,
    write_calibration_result,
)
from edge_os_api.research.statistical_partition import validate_validation_windows
from edge_os_api.research.statistical_preparation import ValidationFinalist


def test_seeded_generator_preserves_complete_scheduled_history_and_partition_boundary() -> None:
    generated = generate_synthetic_family("known-effect-v1", 2101)

    assert generated == generate_synthetic_family("known-effect-v1", 2101)
    assert generated.family.partition_id == "known-effect-v1:2101"
    assert len(generated.family.comparisons) == 3
    assert all(len(comparison.observations) == 160 for comparison in generated.family.comparisons)
    assert generated.truth == {"positive": Decimal("0.35"), "null": Decimal(0), "negative": Decimal("-0.35")}
    assert any(observation.response is None and observation.reason == "SYNTHETIC_MISSING"
               for observation in generated.family.comparisons[0].observations)
    assert validate_validation_windows(
        generated.family,
        generated.outcome_windows,
        validation_starts_at=generated.validation_starts_at,
        protected_starts_at=generated.protected_starts_at,
    ).status == "VALID"


def test_generator_is_independent_of_the_callers_ambient_decimal_precision() -> None:
    with localcontext() as context:
        context.prec = 28
        low_precision = generate_synthetic_family("known-effect-v1", 2101)
    with localcontext() as context:
        context.prec = 50
        high_precision = generate_synthetic_family("known-effect-v1", 2101)

    assert low_precision == high_precision
    assert low_precision.history_hash == high_precision.history_hash


def test_nonstationary_generator_keeps_a_nonconstant_truth_unknown_not_zero() -> None:
    generated = generate_synthetic_family("nonstationary-v1", 3101)

    assert generated.truth == {"positive": None, "null": Decimal(0), "negative": Decimal(0)}


def test_runner_preserves_static_and_wall_limit_failures_without_retrying() -> None:
    scenario = CalibrationScenario("known-effect-v1", (2101,))
    profile = replace(frozen_calibration_profile(), bootstrap_draws=3)
    static = run_experiment(
        scenario, profile=profile,
        limits=CalibrationLimits(maximum_slot_visits=1, per_experiment_seconds=10, total_seconds=10,
                                 maximum_traced_bytes=1_000_000),
    )
    wall = run_experiment(
        scenario, profile=profile,
        limits=CalibrationLimits(maximum_slot_visits=1_000_000, per_experiment_seconds=0, total_seconds=10,
                                 maximum_traced_bytes=1_000_000),
    )

    assert static.status == "LIMIT_STATIC_WORK"
    assert static.repetitions == ()
    assert wall.status == "LIMIT_WALL_TIME"
    assert wall.repetitions == ()


def test_small_bounded_experiment_is_reproducible_and_retains_result_detail() -> None:
    scenario = CalibrationScenario("known-effect-v1", (2101,))
    profile = replace(frozen_calibration_profile(), bootstrap_draws=7)
    limits = CalibrationLimits(maximum_slot_visits=1_000_000, per_experiment_seconds=10, total_seconds=10,
                               maximum_traced_bytes=10_000_000)

    first = run_experiment(scenario, profile=profile, limits=limits)
    second = run_experiment(scenario, profile=profile, limits=limits)

    assert first.status == "COMPLETED"
    assert (first.scenario, first.planned_slot_visits, first.repetitions) == (
        second.scenario, second.planned_slot_visits, second.repetitions,
    )
    assert len(first.repetitions) == 1
    assert first.repetitions[0].history_hash
    assert set(first.repetitions[0].comparisons) == {"positive", "null", "negative"}


def test_failure_fixtures_cover_required_unresolved_and_holdout_governance_paths() -> None:
    statuses = run_failure_fixtures(frozen_calibration_profile())

    assert statuses == {
        "short": "UNRESOLVED_SHORT_HISTORY",
        "sparse": "UNRESOLVED_FAMILY_INCOMPLETE",
        "all_missing": "UNRESOLVED_FAMILY_INCOMPLETE",
        "zero_missing": "RETAINED",
        "invalid_pvalue": "UNRESOLVED_FAMILY_INCOMPLETE",
        "tie": "SELECTED:alpha",
        "selector_bandwidth": "UNRESOLVED_SELECTOR_BANDWIDTH",
        "partition_lower_boundary": "UNRESOLVED_OUTCOME_BEFORE_VALIDATION",
        "partition_upper_boundary": "UNRESOLVED_OUTCOME_REACHES_HOLDOUT",
        "holdout_access_started": "ACCESS_STARTED",
        "holdout_failure": "UNRESOLVED_HOLDOUT_FAILED",
        "holdout_wrong_finalist": "UNRESOLVED_HOLDOUT_WRONG_FINALIST",
        "holdout_runner_up": "UNRESOLVED_HOLDOUT_ALREADY_ACCESSED",
        "holdout_revision_mismatch": "UNRESOLVED_HOLDOUT_REVISION_MISMATCH",
        "holdout_reaccess": "UNRESOLVED_HOLDOUT_ALREADY_ACCESSED",
    }


def test_bounded_calibration_uses_decimal_coverage_and_preserves_its_proposal_status(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    plan = docs / "qualification" / "p42" / "CALIBRATION_PLAN.md"
    profile = docs / "implementation" / "STAT_Q01_CANDIDATE_PREPARATION_PROFILE.md"
    plan.parent.mkdir(parents=True)
    profile.parent.mkdir(parents=True)
    plan.write_text("frozen plan\n")
    profile.write_text("frozen profile\n")
    result = run_bounded_calibration(
        plan,
        profile=replace(frozen_calibration_profile(), bootstrap_draws=7),
        scenarios=(CalibrationScenario("known-effect-v1", (2101,)),),
        limits=CalibrationLimits(1_000_000, 10, 10, 10_000_000),
    )

    assert result["status"] == "UNRESOLVED"
    assert result["experiments"][0].status == "COMPLETED"
    assert result["assessments"]["known-effect-v1"]["coverage"]


def test_calibration_limits_refuse_an_unfrozen_parallel_execution_shape() -> None:
    scenario = CalibrationScenario("known-effect-v1", (2101,))
    limits = CalibrationLimits(1_000_000, 10, 10, 10_000_000, processes=2)

    with pytest.raises(ValueError, match="single-process"):
        run_experiment(scenario, profile=replace(frozen_calibration_profile(), bootstrap_draws=3), limits=limits)


def test_bounded_calibration_records_total_static_work_limit_without_running_a_partial_experiment(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    plan = docs / "qualification" / "p42" / "CALIBRATION_PLAN.md"
    profile = docs / "implementation" / "STAT_Q01_CANDIDATE_PREPARATION_PROFILE.md"
    plan.parent.mkdir(parents=True)
    profile.parent.mkdir(parents=True)
    plan.write_text("frozen plan\n")
    profile.write_text("frozen profile\n")
    result = run_bounded_calibration(
        plan,
        profile=replace(frozen_calibration_profile(), bootstrap_draws=3),
        scenarios=(CalibrationScenario("known-effect-v1", (2101,)),),
        limits=CalibrationLimits(1_000_000, 10, 10, 10_000_000, maximum_total_slot_visits=1),
    )

    assert result["status"] == "UNRESOLVED"
    assert result["planned_total_slot_visits"] > 1
    assert result["experiments"][0].status == "LIMIT_STATIC_TOTAL_WORK"


def test_nonstationary_assessment_requires_a_frozen_rule_not_merely_no_finalist() -> None:
    scenario = CalibrationScenario("nonstationary-v1", tuple(range(32)))

    def repetition(reason: str) -> CalibrationRepetition:
        return CalibrationRepetition(
            1, "history", "VALID", "EVALUATED", ValidationFinalist("UNRESOLVED_NO_FINALIST", None, ()),
            reason, {}, {}, None, {"positive": None, "null": Decimal(0), "negative": Decimal(0)},
        )

    generic = ExperimentResult(scenario, "COMPLETED", 0, tuple(repetition("UNRESOLVED_NO_FINALIST") for _ in scenario.seeds), 0)
    selector_bound = ExperimentResult(
        scenario, "COMPLETED", 0, tuple(repetition("UNRESOLVED_SELECTOR_RULE") for _ in scenario.seeds), 0,
    )

    assert _assess_experiment(generic)["passed"] is False
    assert _assess_experiment(generic)["rule_unresolved"] == 0
    assert _assess_experiment(selector_bound)["passed"] is True


def test_result_writer_emits_json_without_decimal_or_provider_inputs(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    result = {"profile_id": "proposal", "value": Decimal("0.10"), "network": False}

    write_calibration_result(target, result)

    assert target.read_text() == '{\n  "network": false,\n  "profile_id": "proposal",\n  "value": "0.10"\n}\n'
