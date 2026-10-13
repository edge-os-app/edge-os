from decimal import Decimal, localcontext

import pytest

from edge_os_api.research.proposed_statistical_qualification import (
    ProposedContrastSeries,
    ProposedStatisticalProfile,
    evaluate_joint_family,
    holm_rejections,
    joint_stationary_indices,
)


def _profile(**changes: object) -> ProposedStatisticalProfile:
    values: dict[str, object] = {
        "profile_ref": "proposal:p42/bootstrap-v1", "selector_ref": "proposal:caller-supplied-block",
        "expected_block_length": 3, "overlap_floor": 1, "resamples": 101, "seed": 7,
        "lower_quantile": Decimal("0.025"), "upper_quantile": Decimal("0.975"),
        "family_alpha": Decimal("0.05"), "minimum_coverage": Decimal("0.5"),
        "minimum_usable_observations": 2, "sparse_resample_policy": "UNRESOLVED",
    }
    values.update(changes)
    return ProposedStatisticalProfile(**values)  # type: ignore[arg-type]


def test_joint_stationary_indices_are_seeded_circular_and_shared() -> None:
    first = joint_stationary_indices(5, 2, 3, 19)
    assert first == joint_stationary_indices(5, 2, 3, 19)
    assert all(len(sample) == 5 and all(0 <= index < 5 for index in sample) for sample in first)
    with pytest.raises(ValueError):
        joint_stationary_indices(0, 2, 3, 19)


def test_holm_preserves_complete_family_and_does_not_drop_unknowns() -> None:
    assert holm_rejections({"a": Decimal("0.01"), "b": Decimal("0.03"), "c": Decimal("0.04")}, Decimal("0.05")) == {
        "a": True, "b": False, "c": False,
    }
    assert holm_rejections({"a": Decimal("0.01"), "missing": None}, Decimal("0.05")) == {
        "a": None, "missing": None,
    }
    assert holm_rejections({"a": Decimal("NaN")}, Decimal("0.05")) == {"a": None}
    with pytest.raises(ValueError):
        holm_rejections({"a": Decimal("0.01")}, Decimal("1"))


def test_profile_rejects_unfrozen_or_unsafe_default_like_choices() -> None:
    assert _profile().is_usable()
    assert not _profile(selector_ref="").is_usable()
    assert not _profile(sparse_resample_policy="DROP").is_usable()
    assert not _profile(minimum_coverage=Decimal("0")).is_usable()
    assert not _profile(family_alpha=Decimal("NaN")).is_usable()


def test_joint_evaluation_keeps_missing_distinct_from_zero_and_reports_coverage() -> None:
    result = evaluate_joint_family(
        _profile(),
        (
            ProposedContrastSeries("known", (Decimal("1"), Decimal("2"), None, Decimal("3"))),
            ProposedContrastSeries("missing", (None, None, None, Decimal("1"))),
        ),
        Decimal("0"),
    )
    assert result["known"].observed_mean == Decimal("2")
    assert result["known"].usable_observations == 3
    assert result["known"].coverage == Decimal("0.75")
    assert result["missing"].observed_mean is None
    assert result["missing"].status == "UNRESOLVED_MISSING"
    assert result["missing"].candidate_support is None


def test_joint_evaluation_is_seed_repeatable_and_minimum_difference_is_not_implicit() -> None:
    contrasts = (
        ProposedContrastSeries("first", (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"))),
        ProposedContrastSeries("second", (Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1"))),
    )
    first = evaluate_joint_family(_profile(resamples=31), contrasts, Decimal("1"))
    second = evaluate_joint_family(_profile(resamples=31), contrasts, Decimal("1"))
    assert first == second
    with pytest.raises(ValueError):
        evaluate_joint_family(_profile(), contrasts, Decimal("NaN"))
    with pytest.raises(ValueError):
        evaluate_joint_family(_profile(), contrasts, Decimal("-0.01"))


def test_joint_evaluation_pins_every_decimal_operation_to_the_profile_context() -> None:
    contrasts = (ProposedContrastSeries("precision", (Decimal("1"), Decimal("2"), Decimal("4"))),)
    profile = _profile(resamples=31)
    with localcontext() as context:
        context.prec = 28
        low_precision = evaluate_joint_family(profile, contrasts, Decimal("0"))
    with localcontext() as context:
        context.prec = 50
        high_precision = evaluate_joint_family(profile, contrasts, Decimal("0"))
    assert low_precision == high_precision


def test_sparse_bootstrap_sample_is_unresolved_not_a_zero_mean() -> None:
    result = evaluate_joint_family(
        _profile(expected_block_length=1, resamples=101, minimum_coverage=Decimal("0.25"), minimum_usable_observations=1),
        (ProposedContrastSeries("sparse", (None, None, None, Decimal("7"))),),
        Decimal("0"),
    )
    assert result["sparse"].observed_mean == Decimal("7")
    assert result["sparse"].status in {"UNRESOLVED_SPARSE_RESAMPLE", "UNRESOLVED_SENSITIVITY"}
    assert result["sparse"].candidate_support is None


def test_family_requires_same_schedule_and_never_emits_formal_qualification() -> None:
    with pytest.raises(ValueError):
        evaluate_joint_family(
            _profile(),
            (ProposedContrastSeries("a", (Decimal("1"),)), ProposedContrastSeries("b", (Decimal("1"), Decimal("2")))),
            Decimal("0"),
        )
    result = evaluate_joint_family(
        _profile(resamples=31),
        (ProposedContrastSeries("a", (Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"))),),
        Decimal("0"),
    )
    assert result["a"].status in {"CANDIDATE_SUPPORT", "CANDIDATE_NO_SUPPORT", "UNRESOLVED_SENSITIVITY"}
    assert "QUALIFIED" not in result["a"].status
