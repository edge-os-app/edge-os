"""Pure proposed STAT-Q01 calculation primitives with explicit failure states."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from hashlib import sha256
from random import Random
from time import monotonic
from typing import Mapping

from edge_os_api.strategies.compiler import NUMERIC


ELIGIBILITY_GROUPS = frozenset({"TRIGGERED", "CONTROL", "EXCLUDED"})


class EvaluationDeadlineExceeded(RuntimeError):
    """The caller's finite calibration deadline elapsed during numerical work."""


@dataclass(frozen=True)
class ScheduledObservation:
    """One retained scheduled opportunity; a missing response is never a zero."""

    slot_id: str
    group: str
    response: Decimal | None
    reason: str | None = None


@dataclass(frozen=True)
class FrozenComparison:
    """One named primary or incremental comparison on an ordered schedule."""

    comparison_id: str
    observations: tuple[ScheduledObservation, ...]


@dataclass(frozen=True)
class ComparisonSummary:
    """Observed-outcome descriptive statistics with retained missingness counts."""

    scheduled_count: int
    triggered_observed: int
    triggered_missing: int
    control_observed: int
    control_missing: int
    triggered_mean: Decimal | None
    control_mean: Decimal | None
    contrast: Decimal | None
    missing_reasons: Mapping[str, int]


@dataclass(frozen=True)
class BlockLengthSelection:
    """Auditable output from the corrected PPW stationary-bootstrap selector."""

    status: str
    selected_length: int | None
    raw_length: Decimal | None
    cutoff_lag: int | None
    bandwidth: int | None
    weighted_autocovariance: Decimal | None
    long_run_variance: Decimal | None
    variance_constant: Decimal | None


@dataclass(frozen=True)
class StatisticalPreparationProfile:
    """Every numerical setting required by the frozen preparation profile."""

    profile_id: str
    seed: int
    bootstrap_draws: int
    minimum_relevant_difference: Decimal
    family_alpha: Decimal
    pointwise_alpha: Decimal
    minimum_scheduled_slots: int
    maximum_scheduled_slots: int
    minimum_group_observations: int
    minimum_group_coverage: Decimal
    minimum_draw_group_observations: int
    maximum_comparisons: int

    def is_usable(self) -> bool:
        decimal_values = (self.minimum_relevant_difference, self.family_alpha, self.pointwise_alpha,
                          self.minimum_group_coverage)
        return (
            bool(self.profile_id)
            and isinstance(self.seed, int) and not isinstance(self.seed, bool) and self.seed >= 0
            and isinstance(self.bootstrap_draws, int) and not isinstance(self.bootstrap_draws, bool)
            and self.bootstrap_draws > 0
            and all(isinstance(value, Decimal) and value.is_finite() for value in decimal_values)
            and self.minimum_relevant_difference >= 0
            and 0 < self.family_alpha < 1
            and 0 < self.pointwise_alpha < 1
            and 0 < self.minimum_group_coverage <= 1
            and all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in (
                self.minimum_scheduled_slots, self.maximum_scheduled_slots,
                self.minimum_group_observations, self.minimum_draw_group_observations,
                self.maximum_comparisons,
            ))
            and self.minimum_scheduled_slots <= self.maximum_scheduled_slots
        )


@dataclass(frozen=True)
class FrozenComparisonFamily:
    """A validation-only frozen family with one shared ordered schedule."""

    family_id: str
    partition_id: str
    target_horizon_seconds: int
    reference_window_seconds: int
    decision_interval_seconds: int
    comparisons: tuple[FrozenComparison, ...]


@dataclass(frozen=True)
class ComparisonEvaluation:
    """One retained comparison's feasibility and eventual inference outputs."""

    comparison: FrozenComparison
    summary: ComparisonSummary
    selector: BlockLengthSelection | None
    status: str
    sensitivity_results: Mapping[str, "BootstrapEvaluation"]
    holm_rejections: Mapping[str, bool | None]
    candidate_eligible: bool | None


@dataclass(frozen=True)
class BootstrapEvaluation:
    """One fixed-block-length result for an individual comparison."""

    status: str
    block_length: int
    interval: tuple[Decimal, Decimal] | None
    directional_pvalue: Decimal | None


@dataclass(frozen=True)
class FamilyEvaluation:
    """Complete result of a validation-only family, including failures."""

    family: FrozenComparisonFamily
    status: str
    schedule_overlap_floor: int | None
    selected_block_length: int | None
    comparisons: Mapping[str, ComparisonEvaluation]
    family_holm_rejections: Mapping[str, Mapping[str, bool | None]]


@dataclass(frozen=True)
class ValidationFinalist:
    """One frozen validation finalist, without exposing any holdout records."""

    status: str
    finalist_id: str | None
    eligible_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProtectedHoldoutDecision:
    """A proposed one-shot confirmation record for the already-selected finalist."""

    status: str
    finalist_id: str | None
    submitted_comparison_id: str
    pvalue: Decimal | None


def schedule_overlap_floor(
    *,
    target_horizon_seconds: int,
    reference_window_seconds: int,
    decision_interval_seconds: int,
) -> int:
    """Return the smallest block preserving one full scheduled response span."""
    values = (target_horizon_seconds, reference_window_seconds, decision_interval_seconds)
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
        raise ValueError("response horizon, window, and decision interval must be positive whole seconds")
    span = target_horizon_seconds + reference_window_seconds
    return (span + decision_interval_seconds - 1) // decision_interval_seconds


def summarize_comparison(comparison: FrozenComparison) -> ComparisonSummary:
    """Summarize one observed-outcome contrast without changing its schedule."""
    if not comparison.comparison_id:
        raise ValueError("comparison identity is required")
    slot_ids: set[str] = set()
    values = {"TRIGGERED": [], "CONTROL": []}
    missing = {"TRIGGERED": 0, "CONTROL": 0}
    reasons: Counter[str] = Counter()
    for observation in comparison.observations:
        _validate_observation(observation, slot_ids)
        if observation.response is None:
            if observation.group in missing:
                missing[observation.group] += 1
            reasons[observation.reason or "MISSING_REASON_UNSPECIFIED"] += 1
        elif observation.group in values:
            values[observation.group].append(observation.response)
    triggered_mean = _mean(values["TRIGGERED"])
    control_mean = _mean(values["CONTROL"])
    contrast = None
    if triggered_mean is not None and control_mean is not None:
        with localcontext(NUMERIC):
            contrast = triggered_mean - control_mean
    return ComparisonSummary(
        scheduled_count=len(comparison.observations),
        triggered_observed=len(values["TRIGGERED"]),
        triggered_missing=missing["TRIGGERED"],
        control_observed=len(values["CONTROL"]),
        control_missing=missing["CONTROL"],
        triggered_mean=triggered_mean,
        control_mean=control_mean,
        contrast=contrast,
        missing_reasons=dict(sorted(reasons.items())),
    )


def select_ppw_stationary_block_length(
    influence: tuple[Decimal, ...],
    *,
    overlap_floor: int,
) -> BlockLengthSelection:
    """Apply the frozen corrected PPW selector to one contrast influence series."""
    if isinstance(overlap_floor, bool) or not isinstance(overlap_floor, int) or overlap_floor <= 0:
        raise ValueError("overlap floor must be a positive whole number of scheduled slots")
    if len(influence) < 128:
        return _unresolved_selection("UNRESOLVED_SHORT_HISTORY")
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in influence):
        return _unresolved_selection("UNRESOLVED_NONFINITE_INFLUENCE")
    size = len(influence)
    with localcontext(NUMERIC):
        mean = _mean(list(influence))
        assert mean is not None
        autocovariances = tuple(_autocovariance(influence, mean, lag) for lag in range(size))
        variance = autocovariances[0]
        if variance <= 0:
            return _unresolved_selection("UNRESOLVED_DEGENERATE_INFLUENCE")
        base_ten_log = Decimal(size).ln() / Decimal(10).ln()
        run_length = max(5, int(base_ten_log.sqrt()))
        maximum_lag = min(size // 4, 32)
        threshold = Decimal(2) * (base_ten_log / Decimal(size)).sqrt()
        cutoff_lag = _first_negligible_run(autocovariances, variance, maximum_lag, run_length, threshold)
        if cutoff_lag is None:
            return _unresolved_selection("UNRESOLVED_SELECTOR_BANDWIDTH")
        bandwidth = cutoff_lag * 2
        weighted_autocovariance = sum(
            (Decimal(2) * _flat_top_weight(lag, bandwidth) * Decimal(lag) * autocovariances[lag]
             for lag in range(1, bandwidth + 1)),
            Decimal(0),
        )
        long_run_variance = autocovariances[0] + sum(
            (Decimal(2) * _flat_top_weight(lag, bandwidth) * autocovariances[lag]
             for lag in range(1, bandwidth + 1)),
            Decimal(0),
        )
        if long_run_variance <= 0:
            return _unresolved_selection("UNRESOLVED_NONPOSITIVE_LONG_RUN_VARIANCE")
        variance_constant = Decimal(2) * long_run_variance ** 2
        if weighted_autocovariance == 0:
            raw_length = Decimal(0)
        else:
            raw_length = ((Decimal(2) * weighted_autocovariance ** 2 / variance_constant) * Decimal(size)).ln()
            raw_length = (raw_length / Decimal(3)).exp()
        rounded = int(raw_length.to_integral_value(rounding=ROUND_HALF_EVEN))
        selected_length = max(overlap_floor, 1, rounded)
        if selected_length > size:
            return _unresolved_selection("UNRESOLVED_SELECTOR_LENGTH_EXCEEDS_PARTITION")
        return BlockLengthSelection(
            "SELECTED", selected_length, raw_length, cutoff_lag, bandwidth, weighted_autocovariance,
            long_run_variance, variance_constant,
        )


def joint_stationary_bootstrap_indices(
    *,
    population_size: int,
    expected_block_length: int,
    draws: int,
    seed: int,
) -> tuple[tuple[int, ...], ...]:
    """Generate one common circular stationary-bootstrap index stream per draw."""
    integers = (population_size, expected_block_length, draws, seed)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
        raise ValueError("stationary-bootstrap dimensions and seed must be whole numbers")
    if population_size <= 0 or expected_block_length <= 0 or draws <= 0:
        raise ValueError("population size, expected block length, and draws must be positive")
    random = Random(seed)
    samples: list[tuple[int, ...]] = []
    for _ in range(draws):
        current = random.randrange(population_size)
        indices: list[int] = []
        for _ in range(population_size):
            if indices and random.randrange(expected_block_length) == 0:
                current = random.randrange(population_size)
            indices.append(current)
            current = (current + 1) % population_size
        samples.append(tuple(indices))
    return tuple(samples)


def holm_rejections(
    pvalues: Mapping[str, Decimal | None],
    *,
    alpha: Decimal,
) -> Mapping[str, bool | None]:
    """Apply step-down Holm to the entire named family or leave it unresolved."""
    if not pvalues:
        raise ValueError("Holm needs a non-empty frozen comparison family")
    if not isinstance(alpha, Decimal) or not alpha.is_finite() or not Decimal(0) < alpha < Decimal(1):
        raise ValueError("Holm alpha must be a finite Decimal strictly between zero and one")
    if any(value is None or not isinstance(value, Decimal) or not value.is_finite() or value < 0 or value > 1
           for value in pvalues.values()):
        return {comparison_id: None for comparison_id in pvalues}
    ordered = sorted(pvalues.items(), key=lambda item: (item[1], item[0]))
    rejections: dict[str, bool] = {comparison_id: False for comparison_id in pvalues}
    with localcontext(NUMERIC):
        for index, (comparison_id, pvalue) in enumerate(ordered):
            assert pvalue is not None
            if pvalue <= alpha / Decimal(len(ordered) - index):
                rejections[comparison_id] = True
            else:
                break
    return rejections


def evaluate_validation_family(
    profile: StatisticalPreparationProfile,
    family: FrozenComparisonFamily,
    *,
    deadline: float | None = None,
) -> FamilyEvaluation:
    """Validate and prepare one complete validation family without holdout inputs."""
    _check_deadline(deadline)
    if not profile.is_usable():
        raise ValueError("a complete finite statistical preparation profile is required")
    _validate_family_shape(profile, family)
    overlap_floor = schedule_overlap_floor(
        target_horizon_seconds=family.target_horizon_seconds,
        reference_window_seconds=family.reference_window_seconds,
        decision_interval_seconds=family.decision_interval_seconds,
    )
    evaluations: dict[str, ComparisonEvaluation] = {}
    incomplete = False
    for comparison in family.comparisons:
        _check_deadline(deadline)
        summary = summarize_comparison(comparison)
        feasible = _summary_is_feasible(summary, profile)
        status = "PENDING_SELECTOR" if feasible else "UNRESOLVED_FEASIBILITY"
        incomplete = incomplete or not feasible
        evaluations[comparison.comparison_id] = ComparisonEvaluation(
            comparison=comparison,
            summary=summary,
            selector=None,
            status=status,
            sensitivity_results={},
            holm_rejections={},
            candidate_eligible=None,
        )
    if incomplete:
        return FamilyEvaluation(family, "UNRESOLVED_FAMILY_INCOMPLETE", overlap_floor, None, evaluations, {})
    selected: dict[str, BlockLengthSelection] = {}
    for comparison in family.comparisons:
        _check_deadline(deadline)
        selection = select_ppw_stationary_block_length(_contrast_influence(comparison, evaluations[comparison.comparison_id].summary),
                                                        overlap_floor=1)
        selected[comparison.comparison_id] = selection
    if any(selection.status != "SELECTED" for selection in selected.values()):
        for comparison_id, evaluation in evaluations.items():
            selection = selected[comparison_id]
            evaluations[comparison_id] = ComparisonEvaluation(
                evaluation.comparison, evaluation.summary, selection,
                "UNRESOLVED_SELECTOR" if selection.status != "SELECTED" else "UNRESOLVED_FAMILY_SELECTOR",
                {}, {}, None,
            )
        return FamilyEvaluation(family, "UNRESOLVED_FAMILY_INCOMPLETE", overlap_floor, None, evaluations, {})
    selected_block_length = max(overlap_floor, *(selection.selected_length or 0 for selection in selected.values()))
    lengths = {
        "HALF": max(overlap_floor, (selected_block_length + 1) // 2),
        "NOMINAL": selected_block_length,
        "DOUBLE": selected_block_length * 2,
    }
    size = len(family.comparisons[0].observations)
    if any(length > size for length in lengths.values()):
        for comparison_id, evaluation in evaluations.items():
            evaluations[comparison_id] = ComparisonEvaluation(
                evaluation.comparison, evaluation.summary, selected[comparison_id],
                "UNRESOLVED_SENSITIVITY", {}, {}, None,
            )
        return FamilyEvaluation(family, "UNRESOLVED_FAMILY_INCOMPLETE", overlap_floor, selected_block_length,
                                evaluations, {})
    per_comparison: dict[str, dict[str, BootstrapEvaluation]] = {
        comparison.comparison_id: {} for comparison in family.comparisons
    }
    family_holm: dict[str, Mapping[str, bool | None]] = {}
    for sensitivity, length in lengths.items():
        indices = joint_stationary_bootstrap_indices(
            population_size=size,
            expected_block_length=length,
            draws=profile.bootstrap_draws,
            seed=_derived_bootstrap_seed(profile, family.partition_id, length),
        )
        pvalues: dict[str, Decimal | None] = {}
        for comparison in family.comparisons:
            _check_deadline(deadline)
            evaluation = _bootstrap_evaluation(profile, comparison, evaluations[comparison.comparison_id].summary,
                                               length, indices, deadline)
            per_comparison[comparison.comparison_id][sensitivity] = evaluation
            pvalues[comparison.comparison_id] = evaluation.directional_pvalue
        family_holm[sensitivity] = holm_rejections(pvalues, alpha=profile.family_alpha)
    family_complete = all(
        all(value is not None for value in rejections.values()) for rejections in family_holm.values()
    )
    for comparison_id, evaluation in evaluations.items():
        decisions = {sensitivity: rejections[comparison_id] for sensitivity, rejections in family_holm.items()}
        candidate_eligible: bool | None
        if not family_complete:
            candidate_eligible = None
            status = "UNRESOLVED_FAMILY_INCOMPLETE"
        else:
            candidate_eligible = all(decision is True for decision in decisions.values()) and (
                evaluation.summary.contrast is not None
                and evaluation.summary.contrast > profile.minimum_relevant_difference
            )
            status = "EVALUATED"
        evaluations[comparison_id] = ComparisonEvaluation(
            evaluation.comparison, evaluation.summary, selected[comparison_id], status,
            per_comparison[comparison_id], decisions, candidate_eligible,
        )
    status = "EVALUATED" if family_complete else "UNRESOLVED_FAMILY_INCOMPLETE"
    return FamilyEvaluation(family, status, overlap_floor, selected_block_length, evaluations, family_holm)


def select_validation_finalist(
    validation_candidates: Mapping[str, tuple[Decimal | None, bool | None]],
) -> ValidationFinalist:
    """Apply the frozen effect-size/ID rule without accepting any holdout data."""
    if not validation_candidates:
        raise ValueError("finalist selection needs the complete frozen validation family")
    if any(contrast is None or eligible is None for contrast, eligible in validation_candidates.values()):
        return ValidationFinalist("UNRESOLVED_FAMILY_INCOMPLETE", None, ())
    eligible = tuple(
        comparison_id for comparison_id, (contrast, allowed) in validation_candidates.items()
        if allowed is True and contrast is not None
    )
    if not eligible:
        return ValidationFinalist("UNRESOLVED_NO_FINALIST", None, ())
    finalist_id = min(eligible, key=lambda comparison_id: (-validation_candidates[comparison_id][0], comparison_id))
    return ValidationFinalist("SELECTED", finalist_id, tuple(sorted(eligible)))


def confirm_protected_holdout(
    selection: ValidationFinalist,
    *,
    comparison_id: str,
    pvalue: Decimal | None,
    alpha: Decimal,
) -> ProtectedHoldoutDecision:
    """Record only the selected finalist's synthetic confirmation outcome.

    Durable one-shot access enforcement belongs to a later adopted runtime; this
    pure primitive makes a wrong-finalist or missing confirmation explicit.
    """
    if not comparison_id:
        raise ValueError("a submitted comparison identity is required")
    if not isinstance(alpha, Decimal) or not alpha.is_finite() or not Decimal(0) < alpha < Decimal(1):
        raise ValueError("holdout alpha must be a finite Decimal strictly between zero and one")
    if selection.status != "SELECTED" or selection.finalist_id is None:
        return ProtectedHoldoutDecision("UNRESOLVED_NO_FINALIST", selection.finalist_id, comparison_id, pvalue)
    if comparison_id != selection.finalist_id:
        return ProtectedHoldoutDecision("UNRESOLVED_HOLDOUT_WRONG_FINALIST", selection.finalist_id, comparison_id, pvalue)
    if pvalue is None or not isinstance(pvalue, Decimal) or not pvalue.is_finite() or not Decimal(0) <= pvalue <= Decimal(1):
        return ProtectedHoldoutDecision("UNRESOLVED_HOLDOUT_INSUFFICIENT", selection.finalist_id, comparison_id, pvalue)
    status = "CANDIDATE_HOLDOUT_CONFIRMED" if pvalue <= alpha else "UNRESOLVED_HOLDOUT_FAILED"
    return ProtectedHoldoutDecision(status, selection.finalist_id, comparison_id, pvalue)


def _validate_family_shape(profile: StatisticalPreparationProfile, family: FrozenComparisonFamily) -> None:
    if not family.family_id or not family.partition_id:
        raise ValueError("family and non-holdout partition identities are required")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (
        family.target_horizon_seconds, family.reference_window_seconds, family.decision_interval_seconds,
    )):
        raise ValueError("family schedule values must be positive whole seconds")
    if not family.comparisons or len(family.comparisons) > profile.maximum_comparisons:
        raise ValueError("a frozen family exceeds its frozen profile comparison limit")
    if len({comparison.comparison_id for comparison in family.comparisons}) != len(family.comparisons):
        raise ValueError("frozen comparison identities must be unique")
    first_slots = tuple(observation.slot_id for observation in family.comparisons[0].observations)
    if not profile.minimum_scheduled_slots <= len(first_slots) <= profile.maximum_scheduled_slots:
        raise ValueError("family scheduled length is outside its frozen profile bounds")
    for comparison in family.comparisons:
        if tuple(observation.slot_id for observation in comparison.observations) != first_slots:
            raise ValueError("every frozen comparison must retain the same ordered scheduled slots")


def _summary_is_feasible(summary: ComparisonSummary, profile: StatisticalPreparationProfile) -> bool:
    with localcontext(NUMERIC):
        return (
            summary.triggered_mean is not None
            and summary.control_mean is not None
            and summary.triggered_observed >= profile.minimum_group_observations
            and summary.control_observed >= profile.minimum_group_observations
            and Decimal(summary.triggered_observed) / Decimal(summary.scheduled_count) >= profile.minimum_group_coverage
            and Decimal(summary.control_observed) / Decimal(summary.scheduled_count) >= profile.minimum_group_coverage
        )


def _contrast_influence(comparison: FrozenComparison, summary: ComparisonSummary) -> tuple[Decimal, ...]:
    assert summary.triggered_mean is not None and summary.control_mean is not None
    size = Decimal(summary.scheduled_count)
    with localcontext(NUMERIC):
        triggered_share = Decimal(summary.triggered_observed) / size
        control_share = Decimal(summary.control_observed) / size
        output: list[Decimal] = []
        for observation in comparison.observations:
            if observation.group == "TRIGGERED" and observation.response is not None:
                output.append((observation.response - summary.triggered_mean) / triggered_share)
            elif observation.group == "CONTROL" and observation.response is not None:
                output.append(-(observation.response - summary.control_mean) / control_share)
            else:
                output.append(Decimal(0))
        return tuple(output)


def _bootstrap_evaluation(
    profile: StatisticalPreparationProfile,
    comparison: FrozenComparison,
    summary: ComparisonSummary,
    block_length: int,
    indices: tuple[tuple[int, ...], ...],
    deadline: float | None,
) -> BootstrapEvaluation:
    assert summary.contrast is not None
    errors: list[Decimal] = []
    for draw_index, draw in enumerate(indices):
        if draw_index % 8 == 0:
            _check_deadline(deadline)
        sampled = _sampled_contrast(comparison.observations, draw, profile.minimum_draw_group_observations)
        if sampled is None:
            return BootstrapEvaluation("UNRESOLVED_SPARSE_RESAMPLE", block_length, None, None)
        with localcontext(NUMERIC):
            errors.append(sampled - summary.contrast)
    with localcontext(NUMERIC):
        lower_probability = profile.pointwise_alpha / Decimal(2)
        upper_probability = Decimal(1) - lower_probability
        interval = (
            summary.contrast - _empirical_quantile(errors, upper_probability),
            summary.contrast - _empirical_quantile(errors, lower_probability),
        )
        threshold = summary.contrast - profile.minimum_relevant_difference
        tail = sum(error >= threshold for error in errors)
        pvalue = Decimal(1 + tail) / Decimal(1 + len(errors))
    return BootstrapEvaluation("EVALUATED", block_length, interval, pvalue)


def _sampled_contrast(
    observations: tuple[ScheduledObservation, ...],
    indices: tuple[int, ...],
    minimum_group_observations: int,
) -> Decimal | None:
    triggered: list[Decimal] = []
    controls: list[Decimal] = []
    for index in indices:
        observation = observations[index]
        if observation.response is None:
            continue
        if observation.group == "TRIGGERED":
            triggered.append(observation.response)
        elif observation.group == "CONTROL":
            controls.append(observation.response)
    if len(triggered) < minimum_group_observations or len(controls) < minimum_group_observations:
        return None
    triggered_mean, control_mean = _mean(triggered), _mean(controls)
    assert triggered_mean is not None and control_mean is not None
    with localcontext(NUMERIC):
        return triggered_mean - control_mean


def _empirical_quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    if not values or not Decimal(0) < probability < Decimal(1):
        raise ValueError("quantiles need finite values and a probability strictly between zero and one")
    ordered = sorted(values)
    rank = max(1, int((probability * Decimal(len(ordered))).to_integral_value(rounding="ROUND_CEILING")))
    return ordered[rank - 1]


def _derived_bootstrap_seed(profile: StatisticalPreparationProfile, partition_id: str, block_length: int) -> int:
    source = f"{profile.profile_id}\x00{partition_id}\x00{block_length}\x00{profile.seed}".encode("utf-8")
    return int.from_bytes(sha256(source).digest()[:16], "big")


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and monotonic() >= deadline:
        raise EvaluationDeadlineExceeded("the finite calibration deadline elapsed")


def _autocovariance(influence: tuple[Decimal, ...], mean: Decimal, lag: int) -> Decimal:
    size = len(influence)
    return sum(
        ((influence[index] - mean) * (influence[index + lag] - mean) for index in range(size - lag)),
        Decimal(0),
    ) / Decimal(size)


def _first_negligible_run(
    autocovariances: tuple[Decimal, ...],
    variance: Decimal,
    maximum_lag: int,
    run_length: int,
    threshold: Decimal,
) -> int | None:
    for cutoff in range(1, maximum_lag - run_length + 1):
        if all(abs(autocovariances[lag] / variance) < threshold
               for lag in range(cutoff + 1, cutoff + run_length + 1)):
            return cutoff
    return None


def _flat_top_weight(lag: int, bandwidth: int) -> Decimal:
    ratio = Decimal(lag) / Decimal(bandwidth)
    if ratio <= Decimal("0.5"):
        return Decimal(1)
    if ratio <= Decimal(1):
        return Decimal(2) * (Decimal(1) - ratio)
    return Decimal(0)


def _unresolved_selection(status: str) -> BlockLengthSelection:
    return BlockLengthSelection(status, None, None, None, None, None, None, None)


def _validate_observation(observation: ScheduledObservation, slot_ids: set[str]) -> None:
    if not observation.slot_id or observation.slot_id in slot_ids:
        raise ValueError("each comparison needs a unique non-empty scheduled slot identity")
    if observation.group not in ELIGIBILITY_GROUPS:
        raise ValueError("observation group must be TRIGGERED, CONTROL, or EXCLUDED")
    if observation.response is None:
        if not observation.reason:
            raise ValueError("a missing response needs its retained reason")
    elif not isinstance(observation.response, Decimal) or not observation.response.is_finite():
        raise ValueError("an observed response must be a finite Decimal")
    slot_ids.add(observation.slot_id)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    with localcontext(NUMERIC):
        return sum(values, Decimal(0)) / Decimal(len(values))
