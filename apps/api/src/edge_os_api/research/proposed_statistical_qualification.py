"""Proposal-only P42 primitives for joint stationary-bootstrap qualification.

The accepted contracts select a candidate method but leave its exact profile and
calibration unresolved.  This module deliberately requires every such choice
from the caller and is not wired into P09 reports or operational admission.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from random import Random
from typing import Mapping

from edge_os_api.strategies import compiler as strategy_compiler


@dataclass(frozen=True)
class ProposedStatisticalProfile:
    """All numerical choices a P42 adoption would need to freeze explicitly."""

    profile_ref: str
    selector_ref: str
    expected_block_length: int
    overlap_floor: int
    resamples: int
    seed: int
    lower_quantile: Decimal
    upper_quantile: Decimal
    family_alpha: Decimal
    minimum_coverage: Decimal
    minimum_usable_observations: int
    sparse_resample_policy: str

    def is_usable(self) -> bool:
        return (
            bool(self.profile_ref)
            and bool(self.selector_ref)
            and self.expected_block_length > 0
            and self.overlap_floor > 0
            and self.resamples > 0
            and self.lower_quantile.is_finite()
            and self.upper_quantile.is_finite()
            and self.family_alpha.is_finite()
            and self.minimum_coverage.is_finite()
            and 0 < self.lower_quantile < self.upper_quantile < 1
            and 0 < self.family_alpha < 1
            and 0 < self.minimum_coverage <= 1
            and self.minimum_usable_observations > 0
            and self.sparse_resample_policy == "UNRESOLVED"
        )


@dataclass(frozen=True)
class ProposedContrastSeries:
    """One frozen signed contrast at every scheduled opportunity; ``None`` is missing."""

    contrast_id: str
    values: tuple[Decimal | None, ...]


@dataclass(frozen=True)
class ProposedContrastResult:
    contrast_id: str
    observed_mean: Decimal | None
    usable_observations: int
    coverage: Decimal
    basic_interval: tuple[Decimal, Decimal] | None
    directional_pvalue: Decimal | None
    candidate_support: bool | None
    status: str


def joint_stationary_indices(
    population_size: int,
    block_length: int,
    draws: int,
    seed: int,
) -> tuple[tuple[int, ...], ...]:
    """Draw circular stationary-bootstrap indices shared by every comparison.

    A restart has probability ``1 / block_length``.  The returned index streams
    intentionally have no comparison dimension: callers must apply each stream
    to every frozen series, preserving shared schedule dependence.
    """
    if population_size <= 0 or block_length <= 0 or draws <= 0:
        raise ValueError("Population size, block length, and draws must be positive.")
    random = Random(seed)
    restart_probability = 1 / block_length
    samples: list[tuple[int, ...]] = []
    for _ in range(draws):
        current = random.randrange(population_size)
        sample: list[int] = []
        for _ in range(population_size):
            if sample and random.random() < restart_probability:
                current = random.randrange(population_size)
            sample.append(current)
            current = (current + 1) % population_size
        samples.append(tuple(sample))
    return tuple(samples)


def holm_rejections(
    pvalues: Mapping[str, Decimal | None],
    alpha: Decimal,
) -> Mapping[str, bool | None]:
    """Apply Holm to the complete family; invalid members are not silently dropped."""
    if not alpha.is_finite() or not Decimal(0) < alpha < Decimal(1):
        raise ValueError("Holm alpha must be finite and strictly between zero and one.")
    if not pvalues or any(value is None or not value.is_finite() or value < 0 or value > 1
                           for value in pvalues.values()):
        return {contrast_id: None for contrast_id in pvalues}
    ordered = sorted(pvalues.items(), key=lambda item: (item[1], item[0]))
    rejected: dict[str, bool] = {contrast_id: False for contrast_id in pvalues}
    with localcontext(strategy_compiler.NUMERIC):
        for index, (contrast_id, pvalue) in enumerate(ordered):
            threshold = alpha / (len(ordered) - index)
            if pvalue <= threshold:
                rejected[contrast_id] = True
            else:
                break
    return rejected


def evaluate_joint_family(
    profile: ProposedStatisticalProfile,
    contrasts: tuple[ProposedContrastSeries, ...],
    minimum_difference: Decimal,
) -> Mapping[str, ProposedContrastResult]:
    """Evaluate the selected candidate under nominal and predeclared sensitivities.

    Results are qualification inputs only. ``candidate_support`` can never mean
    formally qualified: that requires the complete ST-01–ST-10 evidence suite.
    """
    if (not profile.is_usable() or not minimum_difference.is_finite()
            or minimum_difference < 0 or not contrasts):
        raise ValueError("A complete usable proposal profile, finite minimum difference, and contrasts are required.")
    if len({contrast.contrast_id for contrast in contrasts}) != len(contrasts) or any(
        not contrast.contrast_id or len(contrast.values) != len(contrasts[0].values) for contrast in contrasts
    ):
        raise ValueError("Every named contrast must have the same non-empty scheduled length.")
    if not contrasts[0].values:
        raise ValueError("A contrast family needs scheduled observations.")

    lengths = tuple(sorted({
        max(profile.overlap_floor, profile.expected_block_length // 2),
        max(profile.overlap_floor, profile.expected_block_length),
        max(profile.overlap_floor, profile.expected_block_length * 2),
    }))
    by_length = {length: _evaluate_at_length(profile, contrasts, minimum_difference, length) for length in lengths}
    nominal = by_length[max(profile.overlap_floor, profile.expected_block_length)]
    nominal_pvalues = {contrast_id: result.directional_pvalue for contrast_id, result in nominal.items()}
    nominal_holm = holm_rejections(nominal_pvalues, profile.family_alpha)
    outputs: dict[str, ProposedContrastResult] = {}
    for contrast_id, result in nominal.items():
        sensitivity_support = []
        for length_results in by_length.values():
            candidate = length_results[contrast_id]
            if candidate.status != "EVALUATED" or candidate.directional_pvalue is None:
                sensitivity_support.append(None)
            else:
                sensitivity_support.append(holm_rejections(
                    {item_id: item.directional_pvalue for item_id, item in length_results.items()},
                    profile.family_alpha,
                )[contrast_id])
        if result.status != "EVALUATED" or nominal_holm[contrast_id] is None:
            status, support = result.status, None
        elif any(value is None for value in sensitivity_support):
            status, support = "UNRESOLVED_SENSITIVITY", None
        elif len(set(sensitivity_support)) != 1:
            status, support = "UNRESOLVED_SENSITIVITY", None
        else:
            status = "CANDIDATE_SUPPORT" if nominal_holm[contrast_id] else "CANDIDATE_NO_SUPPORT"
            support = nominal_holm[contrast_id]
        outputs[contrast_id] = ProposedContrastResult(
            result.contrast_id, result.observed_mean, result.usable_observations, result.coverage,
            result.basic_interval, result.directional_pvalue, support, status,
        )
    return outputs


def _evaluate_at_length(
    profile: ProposedStatisticalProfile,
    contrasts: tuple[ProposedContrastSeries, ...],
    minimum_difference: Decimal,
    block_length: int,
) -> Mapping[str, ProposedContrastResult]:
    # Qualification results must not depend on a caller's ambient Decimal
    # context.  Pin the whole calculation, not merely its helpers: coverage,
    # centred draws, interval endpoints, thresholds, and p-values each round.
    with localcontext(strategy_compiler.NUMERIC):
        size = len(contrasts[0].values)
        indices = joint_stationary_indices(size, block_length, profile.resamples, profile.seed)
        outputs: dict[str, ProposedContrastResult] = {}
        for contrast in contrasts:
            known = tuple(value for value in contrast.values if value is not None)
            coverage = Decimal(len(known)) / Decimal(size)
            if (len(known) < profile.minimum_usable_observations or coverage < profile.minimum_coverage
                    or any(not value.is_finite() for value in known)):
                outputs[contrast.contrast_id] = ProposedContrastResult(
                    contrast.contrast_id, None, len(known), coverage, None, None, None, "UNRESOLVED_MISSING",
                )
                continue
            observed = _mean(known)
            draws: list[Decimal] = []
            for sample in indices:
                sampled = tuple(contrast.values[index] for index in sample if contrast.values[index] is not None)
                if not sampled:
                    outputs[contrast.contrast_id] = ProposedContrastResult(
                        contrast.contrast_id, observed, len(known), coverage, None, None, None, "UNRESOLVED_SPARSE_RESAMPLE",
                    )
                    break
                draws.append(_mean(sampled) - observed)
            else:
                lower = observed - _quantile(draws, profile.upper_quantile)
                upper = observed - _quantile(draws, profile.lower_quantile)
                threshold = observed - minimum_difference
                pvalue = Decimal(sum(error >= threshold for error in draws)) / Decimal(len(draws))
                outputs[contrast.contrast_id] = ProposedContrastResult(
                    contrast.contrast_id, observed, len(known), coverage, (lower, upper), pvalue, None, "EVALUATED",
                )
        return outputs


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext(strategy_compiler.NUMERIC):
        return sum(values, Decimal(0)) / Decimal(len(values))


def _quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    ordered = sorted(values)
    with localcontext(strategy_compiler.NUMERIC):
        position = Decimal(len(ordered) - 1) * probability
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
