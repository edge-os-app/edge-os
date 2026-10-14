"""Bounded, authored-only calibration for the proposed STAT-Q01 profile."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tracemalloc
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, localcontext
from hashlib import sha256
from math import isfinite
from pathlib import Path
from random import Random
from time import monotonic
from typing import Any, Mapping, Sequence

from edge_os_api.research.statistical_partition import (
    HoldoutAccessRequest,
    OutcomeWindow,
    begin_protected_holdout,
    prepare_protected_holdout_ledger,
    resolve_protected_holdout,
    validate_validation_windows,
)
from edge_os_api.research.statistical_preparation import (
    BootstrapEvaluation,
    ComparisonSummary,
    EvaluationDeadlineExceeded,
    FamilyEvaluation,
    FrozenComparison,
    FrozenComparisonFamily,
    ScheduledObservation,
    StatisticalPreparationProfile,
    ValidationFinalist,
    evaluate_validation_family,
    holm_rejections,
    select_ppw_stationary_block_length,
    select_validation_finalist,
    summarize_comparison,
)
from edge_os_api.strategies.compiler import NUMERIC


SLOT_COUNT = 160
COMPARISON_IDS = ("positive", "null", "negative")
UTC = timezone.utc
PROFILE_ID = "edge-os.stat-q01-qprep/2026-10-14.2"
_CALCULATION_DIGEST_EXCLUDED_FIELDS = (
    "python",
    "platform",
    "elapsed_seconds",
    "experiments.*.peak_traced_bytes",
)


@dataclass(frozen=True)
class CalibrationScenario:
    """A frozen generator name and its complete, non-retried seed list."""

    scenario_id: str
    seeds: tuple[int, ...]


@dataclass(frozen=True)
class CalibrationLimits:
    """Finite local work, time, and traced-memory bounds for one run."""

    maximum_slot_visits: int
    per_experiment_seconds: float
    total_seconds: float
    maximum_traced_bytes: int
    maximum_total_slot_visits: int = 51_962_880
    processes: int = 1
    workers: int = 1


@dataclass(frozen=True)
class GeneratedFamily:
    """A reproducible synthetic validation family and its no-label timing metadata."""

    family: FrozenComparisonFamily
    truth: Mapping[str, Decimal | None]
    outcome_windows: Mapping[str, OutcomeWindow]
    validation_starts_at: datetime
    protected_starts_at: datetime
    history_hash: str


@dataclass(frozen=True)
class IidEvaluation:
    """The deliberately independence-assuming diagnostic result, never a support method."""

    status: str
    finalist: ValidationFinalist
    comparisons: Mapping[str, BootstrapEvaluation]
    holm_rejections: Mapping[str, bool | None]


@dataclass(frozen=True)
class CalibrationRepetition:
    """Complete retained outcome for one declared synthetic seed."""

    seed: int
    history_hash: str
    partition_status: str
    family_status: str
    selection: ValidationFinalist
    selection_reason: str
    sensitivity_finalists: Mapping[str, ValidationFinalist]
    comparisons: Mapping[str, Mapping[str, object]]
    iid: IidEvaluation | None
    truth: Mapping[str, Decimal | None]


@dataclass(frozen=True)
class ExperimentResult:
    """One bounded experiment, including completed repetitions on partial exit."""

    scenario: CalibrationScenario
    status: str
    planned_slot_visits: int
    repetitions: tuple[CalibrationRepetition, ...]
    peak_traced_bytes: int


CALIBRATION_SCENARIOS = (
    CalibrationScenario("dependent-null-v1", tuple(range(1101, 1165))),
    CalibrationScenario("known-effect-v1", tuple(range(2101, 2165))),
    CalibrationScenario("nonstationary-v1", tuple(range(3101, 3133))),
)
DEFAULT_LIMITS = CalibrationLimits(
    maximum_slot_visits=24_453_120,
    per_experiment_seconds=180,
    total_seconds=540,
    maximum_traced_bytes=256 * 1024 * 1024,
    maximum_total_slot_visits=51_962_880,
)

_FAILURE_FIXTURE_MANIFEST = (
    ("short", "twelve_equal_decimal_ones;overlap_floor=1", "UNRESOLVED_SHORT_HISTORY"),
    ("sparse", "128_slots;five_observed_per_eligible_group", "UNRESOLVED_FAMILY_INCOMPLETE"),
    ("all_missing", "128_slots;zero_observed_per_eligible_group", "UNRESOLVED_FAMILY_INCOMPLETE"),
    ("zero_missing", "observed_zero_and_retained_missing_reason", "RETAINED"),
    ("invalid_pvalue", "whole_family_one_none_pvalue", "UNRESOLVED_FAMILY_INCOMPLETE"),
    ("tie", "equal_eligible_contrasts;ascending_id_tiebreak", "SELECTED:alpha"),
    ("selector_bandwidth", "linear_decimal_influence;overlap_floor=1", "UNRESOLVED_SELECTOR_BANDWIDTH"),
    ("partition_lower_boundary", "window_starts_before_validation", "UNRESOLVED_OUTCOME_BEFORE_VALIDATION"),
    ("partition_upper_boundary", "window_ends_after_protected_start", "UNRESOLVED_OUTCOME_REACHES_HOLDOUT"),
    ("holdout_access_started", "exact_finalist_and_revision_before_label", "ACCESS_STARTED"),
    ("holdout_failure", "started_exact_finalist;pvalue=0.20", "UNRESOLVED_HOLDOUT_FAILED"),
    ("holdout_wrong_finalist", "unconsumed_ledger;runner_up_submission", "UNRESOLVED_HOLDOUT_WRONG_FINALIST"),
    ("holdout_runner_up", "consumed_failed_ledger;runner_up_submission", "UNRESOLVED_HOLDOUT_ALREADY_ACCESSED"),
    ("holdout_revision_mismatch", "unconsumed_ledger;finalist_revision_v2", "UNRESOLVED_HOLDOUT_REVISION_MISMATCH"),
    ("holdout_reaccess", "consumed_failed_ledger;repeat_finalist", "UNRESOLVED_HOLDOUT_ALREADY_ACCESSED"),
)


def frozen_calibration_profile() -> StatisticalPreparationProfile:
    """Return the complete proposal profile used by every authored experiment."""
    return StatisticalPreparationProfile(
        profile_id=PROFILE_ID,
        seed=0,
        bootstrap_draws=199,
        minimum_relevant_difference=Decimal("0.10"),
        family_alpha=Decimal("0.05"),
        pointwise_alpha=Decimal("0.05"),
        minimum_scheduled_slots=128,
        maximum_scheduled_slots=512,
        minimum_group_observations=16,
        minimum_group_coverage=Decimal("0.10"),
        minimum_draw_group_observations=2,
        maximum_comparisons=3,
    )


def generate_synthetic_family(scenario_id: str, seed: int) -> GeneratedFamily:
    """Generate one declared dependent, overlapping authored history without I/O."""
    if scenario_id not in {scenario.scenario_id for scenario in CALIBRATION_SCENARIOS}:
        raise ValueError("unknown frozen calibration scenario")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("a non-negative whole synthetic seed is required")
    random = Random(seed)
    with localcontext(NUMERIC):
        innovations = tuple(Decimal(str(random.normalvariate(0, 0.10))) for _ in range(SLOT_COUNT + 6))
        latent: list[Decimal] = []
        prior = Decimal(0)
        for innovation in innovations:
            prior = Decimal("0.60") * prior + innovation
            latent.append(prior)
        bases = tuple(sum(latent[index:index + 7], Decimal(0)) / Decimal(7) for index in range(SLOT_COUNT))
    groups = tuple("TRIGGERED" if random.random() < 0.5 else "CONTROL" for _ in range(SLOT_COUNT))
    missing = tuple(random.random() < 0.10 for _ in range(SLOT_COUNT))
    effects = _effects_for(scenario_id)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    windows: dict[str, OutcomeWindow] = {}
    comparisons: list[FrozenComparison] = []
    for comparison_id in COMPARISON_IDS:
        observations: list[ScheduledObservation] = []
        for index, (base, group, absent) in enumerate(zip(bases, groups, missing, strict=True)):
            slot_id = f"s{index:03d}"
            decision_at = start + timedelta(minutes=5 * index)
            windows[slot_id] = OutcomeWindow(
                slot_id, decision_at, decision_at + timedelta(minutes=31),
                f"synthetic-outcome/{scenario_id}/{seed}/v1",
            )
            if absent:
                observations.append(ScheduledObservation(slot_id, group, None, "SYNTHETIC_MISSING"))
                continue
            effect = effects[comparison_id][index] if group == "TRIGGERED" else Decimal(0)
            with localcontext(NUMERIC):
                response = base + effect
            observations.append(ScheduledObservation(slot_id, group, response))
        comparisons.append(FrozenComparison(comparison_id, tuple(observations)))
    family = FrozenComparisonFamily(
        family_id=f"synthetic/{scenario_id}",
        partition_id=f"{scenario_id}:{seed}",
        target_horizon_seconds=1_800,
        reference_window_seconds=60,
        decision_interval_seconds=300,
        comparisons=tuple(comparisons),
    )
    protected_start = windows[f"s{SLOT_COUNT - 1:03d}"].ended_at
    truth = {comparison_id: _constant_effect(effects[comparison_id]) for comparison_id in COMPARISON_IDS}
    return GeneratedFamily(family, truth, windows, start, protected_start, _history_hash(family, windows))


def run_experiment(
    scenario: CalibrationScenario,
    *,
    profile: StatisticalPreparationProfile,
    limits: CalibrationLimits,
    absolute_deadline: float | None = None,
) -> ExperimentResult:
    """Run one complete frozen experiment once, retaining any bounded partial output."""
    _validate_limits(limits)
    if not profile.is_usable() or scenario.scenario_id not in {item.scenario_id for item in CALIBRATION_SCENARIOS}:
        raise ValueError("a frozen usable profile and declared scenario are required")
    planned = _planned_slot_visits(scenario, profile)
    if planned > limits.maximum_slot_visits:
        return ExperimentResult(scenario, "LIMIT_STATIC_WORK", planned, (), 0)
    start = monotonic()
    deadline = min(
        start + limits.per_experiment_seconds,
        absolute_deadline if absolute_deadline is not None else float("inf"),
    )
    own_trace = not tracemalloc.is_tracing()
    if own_trace:
        tracemalloc.start()
    peak = 0
    repetitions: list[CalibrationRepetition] = []
    try:
        for seed in scenario.seeds:
            if monotonic() >= deadline:
                return ExperimentResult(scenario, "LIMIT_WALL_TIME", planned, tuple(repetitions), peak)
            generated = generate_synthetic_family(scenario.scenario_id, seed)
            partition = validate_validation_windows(
                generated.family, generated.outcome_windows, validation_starts_at=generated.validation_starts_at,
                protected_starts_at=generated.protected_starts_at,
            )
            if partition.status != "VALID":
                repetitions.append(_unresolved_repetition(seed, generated, partition.status))
                continue
            seeded_profile = replace(profile, seed=seed)
            try:
                evaluation = evaluate_validation_family(seeded_profile, generated.family, deadline=deadline)
                iid = _iid_evaluation(seeded_profile, generated.family, deadline) if scenario.scenario_id == "dependent-null-v1" else None
            except EvaluationDeadlineExceeded:
                return ExperimentResult(scenario, "LIMIT_WALL_TIME", planned, tuple(repetitions), peak)
            repetitions.append(_record_repetition(seed, generated, partition.status, evaluation, iid, seeded_profile))
            _, traced_peak = tracemalloc.get_traced_memory()
            peak = max(peak, traced_peak)
            if peak > limits.maximum_traced_bytes:
                return ExperimentResult(scenario, "LIMIT_MEMORY", planned, tuple(repetitions), peak)
        return ExperimentResult(scenario, "COMPLETED", planned, tuple(repetitions), peak)
    finally:
        if own_trace:
            tracemalloc.stop()


def run_failure_fixtures(
    profile: StatisticalPreparationProfile,
    *,
    deadline: float | None = None,
) -> Mapping[str, str]:
    """Run fixed adversarial/no-result fixtures without consulting any market data."""
    if _deadline_elapsed(deadline):
        return {"CALIBRATION_RUNNER": "LIMIT_TOTAL_WALL_TIME"}
    slots = tuple(f"s{index:03d}" for index in range(128))
    short = select_ppw_stationary_block_length((Decimal(1),) * 12, overlap_floor=1).status
    sparse = _fixture_family(slots, observed_per_group=5, reason="SYNTHETIC_SPARSE")
    all_missing = _fixture_family(slots, observed_per_group=0, reason="SYNTHETIC_MISSING")
    try:
        sparse_status = evaluate_validation_family(profile, sparse, deadline=deadline).status
        missing_status = evaluate_validation_family(profile, all_missing, deadline=deadline).status
    except EvaluationDeadlineExceeded:
        return {"CALIBRATION_RUNNER": "LIMIT_TOTAL_WALL_TIME"}
    invalid = holm_rejections({"positive": Decimal("0.01"), "failed": None}, alpha=profile.family_alpha)
    tie = select_validation_finalist({"beta": (Decimal("0.30"), True), "alpha": (Decimal("0.30"), True)})
    bandwidth = select_ppw_stationary_block_length(tuple(Decimal(index) for index in range(128)), overlap_floor=1).status
    boundary_start = datetime(2026, 1, 1, tzinfo=UTC)
    protected_start = boundary_start + timedelta(minutes=60)
    boundary_family = _partition_fixture_family(("boundary",))
    lower_partition = validate_validation_windows(
        boundary_family,
        {"boundary": OutcomeWindow("boundary", boundary_start - timedelta(seconds=1), boundary_start, "v1")},
        validation_starts_at=boundary_start,
        protected_starts_at=protected_start,
    )
    upper_partition = validate_validation_windows(
        boundary_family,
        {"boundary": OutcomeWindow("boundary", boundary_start, protected_start + timedelta(seconds=1), "v1")},
        validation_starts_at=boundary_start,
        protected_starts_at=protected_start,
    )
    if _deadline_elapsed(deadline):
        return {"CALIBRATION_RUNNER": "LIMIT_TOTAL_WALL_TIME"}
    selection = ValidationFinalist("SELECTED", "positive", ("positive", "runner-up"))
    holdout_family = _partition_fixture_family(("holdout",))
    partition = validate_validation_windows(
        holdout_family,
        {"holdout": OutcomeWindow("holdout", boundary_start, protected_start, "v1")},
        validation_starts_at=boundary_start,
        protected_starts_at=protected_start,
    )
    ledger = prepare_protected_holdout_ledger(
        selection, profile_hash=_fixture_sha256("synthetic-profile"), plan_hash=_fixture_sha256("synthetic-plan"),
        partition=partition,
        protected_partition_id="synthetic-holdout", finalist_revision_id="positive-v1",
        outcome_control_test_hash=_fixture_sha256("synthetic-test"),
    )
    request = HoldoutAccessRequest(
        "positive", "positive-v1", ledger.profile_hash, ledger.plan_hash, ledger.family_hash,
        ledger.protected_partition_id, ledger.outcome_control_test_hash,
    )
    started = begin_protected_holdout(ledger, selection, request)
    failed = resolve_protected_holdout(
        started.ledger, pvalue=Decimal("0.20"), outcome_control_test_hash=ledger.outcome_control_test_hash,
    )
    wrong_finalist = begin_protected_holdout(
        ledger, selection, replace(request, comparison_id="runner-up", revision_id="runner-up-v1"),
    )
    revision = begin_protected_holdout(ledger, selection, replace(request, revision_id="positive-v2"))
    runner_up = begin_protected_holdout(
        failed.ledger, selection, replace(request, comparison_id="runner-up", revision_id="runner-up-v1"),
    )
    reaccess = begin_protected_holdout(
        failed.ledger, selection, request,
    )
    zero_missing = summarize_comparison(FrozenComparison("zero-missing", (
        ScheduledObservation("z0", "TRIGGERED", Decimal(0)),
        ScheduledObservation("z1", "TRIGGERED", None, "SYNTHETIC_MISSING"),
        ScheduledObservation("z2", "CONTROL", Decimal(0)),
    )))
    return {
        "short": short,
        "sparse": sparse_status,
        "all_missing": missing_status,
        "zero_missing": "RETAINED" if zero_missing.triggered_mean == 0 and zero_missing.triggered_missing == 1 else "FAILED",
        "invalid_pvalue": "UNRESOLVED_FAMILY_INCOMPLETE" if all(value is None for value in invalid.values()) else "FAILED",
        "tie": f"SELECTED:{tie.finalist_id}",
        "selector_bandwidth": bandwidth,
        "partition_lower_boundary": lower_partition.status,
        "partition_upper_boundary": upper_partition.status,
        "holdout_access_started": started.status,
        "holdout_failure": failed.decision.status,
        "holdout_wrong_finalist": wrong_finalist.status,
        "holdout_runner_up": runner_up.status,
        "holdout_revision_mismatch": revision.status,
        "holdout_reaccess": reaccess.status,
    }


def run_bounded_calibration(
    plan_path: Path,
    *,
    profile: StatisticalPreparationProfile | None = None,
    scenarios: Sequence[CalibrationScenario] = CALIBRATION_SCENARIOS,
    limits: CalibrationLimits = DEFAULT_LIMITS,
) -> Mapping[str, object]:
    """Run the frozen authored plan and return a JSON-safe proposal evidence packet."""
    profile = profile or frozen_calibration_profile()
    scenarios = tuple(scenarios)
    _validate_limits(limits)
    if not profile.is_usable():
        raise ValueError("the calibration profile must be complete and finite")
    if not plan_path.is_file():
        raise ValueError("the calibration plan must be a readable committed file")
    started = monotonic()
    deadline = started + limits.total_seconds
    planned_total_slot_visits = sum(_planned_slot_visits(item, profile) for item in scenarios)
    static_total_limited = planned_total_slot_visits > limits.maximum_total_slot_visits
    if static_total_limited:
        results = tuple(
            ExperimentResult(item, "LIMIT_STATIC_TOTAL_WORK", _planned_slot_visits(item, profile), (), 0)
            for item in scenarios
        )
    else:
        results = tuple(run_experiment(item, profile=profile, limits=limits, absolute_deadline=deadline) for item in scenarios)
    assessments = {result.scenario.scenario_id: _assess_experiment(result) for result in results}
    fixtures = run_failure_fixtures(profile, deadline=deadline)
    deadline_elapsed = _deadline_elapsed(deadline)
    complete = all(result.status == "COMPLETED" for result in results) and not deadline_elapsed
    fixture_pass = fixtures == _failure_fixture_expectations()
    criteria_pass = all(assessment["passed"] is True for assessment in assessments.values())
    frozen_configuration = (
        profile == frozen_calibration_profile()
        and scenarios == CALIBRATION_SCENARIOS
        and limits == DEFAULT_LIMITS
        and _file_hash(_profile_path(plan_path)) is not None
    )
    status = (
        "PROPOSED_SUITABILITY_PASS_NOT_FORMAL_SUPPORT"
        if frozen_configuration and complete and fixture_pass and criteria_pass
        else "UNRESOLVED"
    )
    result = {
        "schema": "edge-os.stat-q01-calibration-result/2",
        "status": status,
        "profile": asdict(profile),
        "profile_sha256": _file_hash(_profile_path(plan_path)),
        "plan_sha256": _file_hash(plan_path),
        "failure_fixture_sha256": _failure_fixture_hash(),
        "python": sys.version,
        "platform": platform.platform(),
        "limits": asdict(limits),
        "planned_total_slot_visits": planned_total_slot_visits,
        "frozen_configuration": frozen_configuration,
        "calculation_digest_excludes": _CALCULATION_DIGEST_EXCLUDED_FIELDS,
        "elapsed_seconds": format(Decimal(str(monotonic() - started)), "f"),
        "termination_reason": (
            "LIMIT_STATIC_TOTAL_WORK" if static_total_limited
            else "LIMIT_TOTAL_WALL_TIME" if deadline_elapsed else None
        ),
        "experiments": results,
        "assessments": assessments,
        "failure_fixtures": fixtures,
        "limitations": [
            "AUTHORED_SYNTHETIC_ONLY",
            "PROPOSED_PROFILE_NOT_ADOPTED",
            "NO_PROTECTED_MARKET_HOLDOUT_READ",
            "ST10_OPERATIONAL_ADMISSION_NOT_RUN",
            "PURE_HOLDOUT_LEDGER_REQUIRES_LATER_DURABLE_RUNTIME",
        ] + ([] if frozen_configuration else ["NON_FROZEN_TEST_CONFIGURATION"]),
    }
    return {**result, "calculation_sha256": calculation_result_sha256(result)}


def calculation_result_sha256(result: Mapping[str, object]) -> str:
    """Fingerprint deterministic calculation content, excluding local run telemetry.

    The raw artifact retains interpreter/platform, elapsed time, and traced peak
    allocation so reviewers can assess an individual bounded run. Those fields
    are inherently environment-dependent and must not make equal numerical
    histories, selections, intervals, and verdicts appear irreproducible.
    """
    payload = _calculation_payload(result)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return sha256(encoded).hexdigest()


def _calculation_payload(result: Mapping[str, object]) -> Mapping[str, object]:
    """Return JSON-safe result content excluding declared volatile telemetry."""
    safe = _json_safe(result)
    if not isinstance(safe, dict):
        raise ValueError("calculation result must be a mapping")
    payload = {
        key: value
        for key, value in safe.items()
        if key not in {"calculation_sha256", "python", "platform", "elapsed_seconds"}
    }
    experiments = payload.get("experiments")
    if experiments is not None:
        if not isinstance(experiments, list):
            raise ValueError("calibration experiments must be a sequence")
        payload["experiments"] = [
            {key: value for key, value in experiment.items() if key != "peak_traced_bytes"}
            if isinstance(experiment, dict) else experiment
            for experiment in experiments
        ]
    return payload


def write_calibration_result(path: Path, result: object) -> None:
    """Atomically write sorted JSON run evidence without leaking Decimal objects."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(_json_safe(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    """Run only the frozen local authored calibration; no network options exist."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if not arguments.plan.is_file():
        parser.error("--plan must name the committed calibration plan")
    result = run_bounded_calibration(arguments.plan)
    write_calibration_result(arguments.output, result)
    print(json.dumps({"status": result["status"], "output": str(arguments.output)}, sort_keys=True))
    return 0


def _effects_for(scenario_id: str) -> Mapping[str, tuple[Decimal, ...]]:
    zero = (Decimal(0),) * SLOT_COUNT
    if scenario_id == "dependent-null-v1":
        return {comparison_id: zero for comparison_id in COMPARISON_IDS}
    if scenario_id == "known-effect-v1":
        return {"positive": (Decimal("0.35"),) * SLOT_COUNT, "null": zero, "negative": (Decimal("-0.35"),) * SLOT_COUNT}
    if scenario_id == "nonstationary-v1":
        return {"positive": (Decimal("0.35"),) * (SLOT_COUNT // 2) + (Decimal("-0.35"),) * (SLOT_COUNT // 2),
                "null": zero, "negative": zero}
    raise ValueError("unknown frozen calibration scenario")


def _planned_slot_visits(scenario: CalibrationScenario, profile: StatisticalPreparationProfile) -> int:
    components = 4 if scenario.scenario_id == "dependent-null-v1" else 3
    return len(scenario.seeds) * len(COMPARISON_IDS) * profile.bootstrap_draws * components * SLOT_COUNT


def _constant_effect(values: tuple[Decimal, ...]) -> Decimal | None:
    return values[0] if len(set(values)) == 1 else None


def _history_hash(
    family: FrozenComparisonFamily,
    windows: Mapping[str, OutcomeWindow],
) -> str:
    payload = {
        "family_id": family.family_id,
        "partition_id": family.partition_id,
        "target_horizon_seconds": family.target_horizon_seconds,
        "reference_window_seconds": family.reference_window_seconds,
        "decision_interval_seconds": family.decision_interval_seconds,
        "comparisons": [
            [comparison.comparison_id, [[item.slot_id, item.group, _decimal_text(item.response), item.reason]
                                        for item in comparison.observations]]
            for comparison in family.comparisons
        ],
        "outcome_windows": [
            [slot_id, window.started_at.isoformat(), window.ended_at.isoformat(), window.outcome_revision_id]
            for slot_id, window in sorted(windows.items())
        ],
    }
    return sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _record_repetition(
    seed: int,
    generated: GeneratedFamily,
    partition_status: str,
    evaluation: FamilyEvaluation,
    iid: IidEvaluation | None,
    profile: StatisticalPreparationProfile,
) -> CalibrationRepetition:
    comparisons: dict[str, Mapping[str, object]] = {}
    sensitivity_finalists: dict[str, ValidationFinalist] = {}
    for sensitivity in ("HALF", "NOMINAL", "DOUBLE"):
        candidates = {
            item.comparison_id: (evaluation.comparisons[item.comparison_id].summary.contrast,
                                 evaluation.comparisons[item.comparison_id].holm_rejections.get(sensitivity))
            for item in generated.family.comparisons
        }
        sensitivity_finalists[sensitivity] = select_validation_finalist({
            key: (contrast, bool(rejected) and contrast is not None and contrast > profile.minimum_relevant_difference)
            if rejected is not None else (contrast, None)
            for key, (contrast, rejected) in candidates.items()
        })
    for comparison_id, item in evaluation.comparisons.items():
        comparisons[comparison_id] = {
            "status": item.status,
            "contrast": item.summary.contrast,
            "scheduled_count": item.summary.scheduled_count,
            "triggered_observed": item.summary.triggered_observed,
            "triggered_missing": item.summary.triggered_missing,
            "control_observed": item.summary.control_observed,
            "control_missing": item.summary.control_missing,
            "missing_reasons": item.summary.missing_reasons,
            "selector_status": item.selector.status if item.selector else None,
            "sensitivities": {
                name: {
                    "status": value.status,
                    "pvalue": value.directional_pvalue,
                    "interval": value.interval,
                    "holm_rejected": item.holm_rejections.get(name),
                } for name, value in item.sensitivity_results.items()
            },
        }
    candidates = {comparison_id: (item.summary.contrast, item.candidate_eligible)
                  for comparison_id, item in evaluation.comparisons.items()}
    selection = select_validation_finalist(candidates)
    return CalibrationRepetition(
        seed, generated.history_hash, partition_status, evaluation.status, selection,
        _selection_reason(evaluation, selection, sensitivity_finalists), sensitivity_finalists,
        comparisons, iid, generated.truth,
    )


def _unresolved_repetition(seed: int, generated: GeneratedFamily, partition_status: str) -> CalibrationRepetition:
    return CalibrationRepetition(
        seed, generated.history_hash, partition_status, "UNRESOLVED_PARTITION",
        ValidationFinalist("UNRESOLVED_FAMILY_INCOMPLETE", None, ()), partition_status,
        {}, {}, None, generated.truth,
    )


def _selection_reason(
    evaluation: FamilyEvaluation,
    selection: ValidationFinalist,
    sensitivity_finalists: Mapping[str, ValidationFinalist],
) -> str:
    if evaluation.status != "EVALUATED":
        statuses = {item.status for item in evaluation.comparisons.values()}
        if "UNRESOLVED_SELECTOR" in statuses:
            return "UNRESOLVED_SELECTOR_RULE"
        if "UNRESOLVED_SENSITIVITY" in statuses:
            return "UNRESOLVED_SENSITIVITY_RULE"
        return "UNRESOLVED_FAMILY_RULE"
    if selection.status == "SELECTED":
        return "SELECTED"
    sensitivity_outcomes = {(item.status, item.finalist_id) for item in sensitivity_finalists.values()}
    if len(sensitivity_outcomes) > 1:
        return "UNRESOLVED_SENSITIVITY_RULE"
    return selection.status


def _iid_evaluation(
    profile: StatisticalPreparationProfile,
    family: FrozenComparisonFamily,
    deadline: float,
) -> IidEvaluation:
    """Run the frozen diagnostic that intentionally discards serial block structure."""
    size = len(family.comparisons[0].observations)
    random = Random(_iid_seed(profile, family.partition_id))
    indices = tuple(tuple(random.randrange(size) for _ in range(size)) for _ in range(profile.bootstrap_draws))
    summaries = {comparison.comparison_id: summarize_comparison(comparison) for comparison in family.comparisons}
    values: dict[str, BootstrapEvaluation] = {}
    for comparison in family.comparisons:
        if monotonic() >= deadline:
            raise EvaluationDeadlineExceeded("the finite calibration deadline elapsed")
        values[comparison.comparison_id] = _iid_bootstrap(
            profile, comparison, summaries[comparison.comparison_id], indices, deadline,
        )
    rejections = holm_rejections({key: value.directional_pvalue for key, value in values.items()}, alpha=profile.family_alpha)
    candidates = {
        comparison.comparison_id: (
            summaries[comparison.comparison_id].contrast,
            bool(rejections[comparison.comparison_id]) and summaries[comparison.comparison_id].contrast is not None
            and summaries[comparison.comparison_id].contrast > profile.minimum_relevant_difference,
        ) if rejections[comparison.comparison_id] is not None else (summaries[comparison.comparison_id].contrast, None)
        for comparison in family.comparisons
    }
    finalist = select_validation_finalist(candidates)
    status = "EVALUATED" if all(value is not None for value in rejections.values()) else "UNRESOLVED_FAMILY_INCOMPLETE"
    return IidEvaluation(status, finalist, values, rejections)


def _iid_bootstrap(
    profile: StatisticalPreparationProfile,
    comparison: FrozenComparison,
    summary: ComparisonSummary,
    indices: tuple[tuple[int, ...], ...],
    deadline: float,
) -> BootstrapEvaluation:
    if summary.contrast is None:
        return BootstrapEvaluation("UNRESOLVED_FEASIBILITY", 1, None, None)
    errors: list[Decimal] = []
    for number, draw in enumerate(indices):
        if number % 8 == 0 and monotonic() >= deadline:
            raise EvaluationDeadlineExceeded("the finite calibration deadline elapsed")
        sampled = _sampled_contrast(comparison.observations, draw, profile.minimum_draw_group_observations)
        if sampled is None:
            return BootstrapEvaluation("UNRESOLVED_SPARSE_RESAMPLE", 1, None, None)
        with localcontext(NUMERIC):
            errors.append(sampled - summary.contrast)
    with localcontext(NUMERIC):
        low, high = profile.pointwise_alpha / Decimal(2), Decimal(1) - profile.pointwise_alpha / Decimal(2)
        interval = (summary.contrast - _quantile(errors, high), summary.contrast - _quantile(errors, low))
        tail = sum(error >= summary.contrast - profile.minimum_relevant_difference for error in errors)
        pvalue = Decimal(1 + tail) / Decimal(1 + len(errors))
    return BootstrapEvaluation("EVALUATED", 1, interval, pvalue)


def _sampled_contrast(
    observations: tuple[ScheduledObservation, ...],
    indices: tuple[int, ...],
    minimum: int,
) -> Decimal | None:
    triggered = [observations[index].response for index in indices
                 if observations[index].group == "TRIGGERED" and observations[index].response is not None]
    controls = [observations[index].response for index in indices
                if observations[index].group == "CONTROL" and observations[index].response is not None]
    if len(triggered) < minimum or len(controls) < minimum:
        return None
    with localcontext(NUMERIC):
        return sum(triggered, Decimal(0)) / Decimal(len(triggered)) - sum(controls, Decimal(0)) / Decimal(len(controls))


def _quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    ordered = sorted(values)
    rank = max(1, int((probability * Decimal(len(ordered))).to_integral_value(rounding=ROUND_CEILING)))
    return ordered[rank - 1]


def _iid_seed(profile: StatisticalPreparationProfile, partition_id: str) -> int:
    source = f"{profile.profile_id}\x00{partition_id}\x00iid-slot-bootstrap/1\x00{profile.seed}".encode()
    return int.from_bytes(sha256(source).digest()[:16], "big")


def _fixture_family(slots: tuple[str, ...], *, observed_per_group: int, reason: str) -> FrozenComparisonFamily:
    comparisons = []
    for comparison_id in COMPARISON_IDS:
        observations = tuple(
            ScheduledObservation(
                slot, "TRIGGERED" if index % 2 else "CONTROL", _fixture_response(index),
            )
            if index < observed_per_group * 2 else ScheduledObservation(
                slot, "TRIGGERED" if index % 2 else "CONTROL", None, reason,
            ) for index, slot in enumerate(slots)
        )
        comparisons.append(FrozenComparison(comparison_id, observations))
    return FrozenComparisonFamily("failure-fixture", "failure-fixture", 1_800, 60, 300, tuple(comparisons))


def _partition_fixture_family(slots: tuple[str, ...]) -> FrozenComparisonFamily:
    comparison = FrozenComparison(
        "primary", tuple(ScheduledObservation(slot, "CONTROL", Decimal(0)) for slot in slots),
    )
    return FrozenComparisonFamily("partition-fixture", "partition-fixture", 1_800, 60, 300, (comparison,))


def _fixture_sha256(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _fixture_response(index: int) -> Decimal:
    with localcontext(NUMERIC):
        return Decimal(index) / Decimal(100)


def _assess_experiment(result: ExperimentResult) -> Mapping[str, object]:
    if result.status != "COMPLETED":
        return {"passed": False, "reason": result.status, "completed_repetitions": len(result.repetitions)}
    repetitions = result.repetitions
    if result.scenario.scenario_id == "nonstationary-v1":
        if len(repetitions) != len(result.scenario.seeds):
            return {"passed": False, "reason": "INSUFFICIENT_REPETITIONS", "total": len(repetitions)}
        finalists = sum(item.selection.status == "SELECTED" for item in repetitions)
        rule_reasons = {
            "UNRESOLVED_SELECTOR_RULE",
            "UNRESOLVED_SENSITIVITY_RULE",
            "UNRESOLVED_FAMILY_RULE",
        }
        rule_unresolved = sum(item.selection_reason in rule_reasons for item in repetitions)
        reason_counts = {
            reason: sum(item.selection_reason == reason for item in repetitions)
            for reason in sorted({item.selection_reason for item in repetitions})
        }
        passed = (
            finalists == 0
            and Decimal(rule_unresolved) / Decimal(len(repetitions)) >= Decimal("0.80")
        )
        return {
            "passed": passed,
            "finalists": finalists,
            "rule_unresolved": rule_unresolved,
            "selection_reasons": reason_counts,
        }
    valid = [item for item in repetitions if item.family_status == "EVALUATED"]
    if len(valid) != len(repetitions):
        return {"passed": False, "reason": "INSUFFICIENT_VALID_REPETITIONS", "valid": len(valid), "total": len(repetitions)}
    if result.scenario.scenario_id == "dependent-null-v1":
        false = sum(item.selection.status == "SELECTED" for item in valid)
        coverage = _coverage(valid)
        iid_false = sum(item.iid is not None and item.iid.finalist.status == "SELECTED" for item in valid)
        iid_coverage = _iid_coverage(valid)
        upper = _wilson(false, len(valid), Decimal("1.6448536269514722"))[1]
        interval = _wilson(coverage[0], coverage[1], Decimal("1.959963984540054"))
        observed_coverage = _rate(coverage)
        iid_observed_coverage = _rate(iid_coverage)
        discriminated = (
            iid_false >= false + 2
            or (
                iid_observed_coverage is not None
                and observed_coverage is not None
                and iid_observed_coverage <= observed_coverage - Decimal("0.05")
            )
        )
        passed = upper is not None and upper <= Decimal("0.15") and observed_coverage is not None and observed_coverage >= Decimal("0.85") \
            and interval[0] <= Decimal("1.00") and interval[1] >= Decimal("0.90") and discriminated
        return {"passed": passed, "false_finalists": false, "fwer_upper": upper, "coverage": coverage,
                "coverage_wilson": interval, "iid_false_finalists": iid_false, "iid_coverage": iid_coverage,
                "dependence_discriminated": discriminated}
    if result.scenario.scenario_id == "known-effect-v1":
        positive = sum(item.selection.finalist_id == "positive" for item in valid)
        negative = sum(item.selection.finalist_id == "negative" for item in valid)
        coverage = _coverage(valid)
        stable = sum(len({finalist.finalist_id for finalist in item.sensitivity_finalists.values()}) == 1 for item in valid)
        lower = _wilson(positive, len(valid), Decimal("1.6448536269514722"))[0]
        observed_coverage = _rate(coverage)
        passed = lower is not None and lower >= Decimal("0.50") and negative == 0 and observed_coverage is not None and observed_coverage >= Decimal("0.85") \
            and Decimal(stable) / Decimal(len(valid)) >= Decimal("0.80")
        return {"passed": passed, "positive_finalists": positive, "positive_lower": lower,
                "negative_finalists": negative, "coverage": coverage, "stable": stable}
    raise ValueError("unknown frozen calibration scenario")


def _coverage(repetitions: Sequence[CalibrationRepetition]) -> tuple[int, int]:
    hits = total = 0
    for item in repetitions:
        for comparison_id, comparison in item.comparisons.items():
            for sensitivity in comparison["sensitivities"].values():
                interval = sensitivity["interval"]
                truth = item.truth[comparison_id]
                if interval is not None and truth is not None:
                    total += 1
                    hits += interval[0] <= truth <= interval[1]
    return hits, total


def _iid_coverage(repetitions: Sequence[CalibrationRepetition]) -> tuple[int, int]:
    hits = total = 0
    for item in repetitions:
        if item.iid is None:
            continue
        for comparison_id, result in item.iid.comparisons.items():
            truth = item.truth[comparison_id]
            if result.interval is not None and truth is not None:
                total += 1
                hits += result.interval[0] <= truth <= result.interval[1]
    return hits, total


def _wilson(successes: int, total: int, z: Decimal) -> tuple[Decimal | None, Decimal | None]:
    if total <= 0:
        return None, None
    with localcontext(NUMERIC):
        rate, squared = Decimal(successes) / Decimal(total), z * z
        denominator = Decimal(1) + squared / Decimal(total)
        center = (rate + squared / (Decimal(2) * Decimal(total))) / denominator
        radius = z * ((rate * (Decimal(1) - rate) / Decimal(total) + squared / (Decimal(4) * Decimal(total) ** 2)).sqrt()) / denominator
        return center - radius, center + radius


def _validate_limits(limits: CalibrationLimits) -> None:
    if not isinstance(limits, CalibrationLimits):
        raise ValueError("calibration limits must be an explicit finite limits object")
    if (isinstance(limits.maximum_slot_visits, bool) or not isinstance(limits.maximum_slot_visits, int)
            or limits.maximum_slot_visits <= 0
            or isinstance(limits.per_experiment_seconds, bool)
            or not isinstance(limits.per_experiment_seconds, (int, float))
            or not isfinite(limits.per_experiment_seconds) or limits.per_experiment_seconds < 0
            or isinstance(limits.total_seconds, bool) or not isinstance(limits.total_seconds, (int, float))
            or not isfinite(limits.total_seconds) or limits.total_seconds < 0
            or isinstance(limits.maximum_traced_bytes, bool) or not isinstance(limits.maximum_traced_bytes, int)
            or limits.maximum_traced_bytes <= 0):
        raise ValueError("calibration limits must be finite non-negative work/time and positive memory bounds")
    if (isinstance(limits.maximum_total_slot_visits, bool)
            or not isinstance(limits.maximum_total_slot_visits, int)
            or limits.maximum_total_slot_visits <= 0):
        raise ValueError("the total calibration work limit must be a positive whole number")
    if limits.processes != 1 or limits.workers != 1:
        raise ValueError("the frozen calibration permits only a single-process, single-worker execution")


def _profile_path(plan_path: Path) -> Path:
    return plan_path.parents[2] / "implementation" / "STAT_Q01_CANDIDATE_PREPARATION_PROFILE.md"


def _file_hash(path: Path) -> str | None:
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _failure_fixture_hash() -> str:
    return sha256(json.dumps(_FAILURE_FIXTURE_MANIFEST, separators=(",", ":")).encode()).hexdigest()


def _failure_fixture_expectations() -> Mapping[str, str]:
    return {fixture_id: status for fixture_id, _, status in _FAILURE_FIXTURE_MANIFEST}


def _deadline_elapsed(deadline: float | None) -> bool:
    return deadline is not None and monotonic() >= deadline


def _rate(counts: tuple[int, int]) -> Decimal | None:
    numerator, denominator = counts
    if denominator <= 0:
        return None
    with localcontext(NUMERIC):
        return Decimal(numerator) / Decimal(denominator)


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
