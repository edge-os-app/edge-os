from decimal import Decimal

from edge_os_api.replay.proposed_lp_accounting import (
    ProposedLpEvidenceField,
    ProposedLpModelIdentity,
    ProposedLpReadiness,
    ProposedLpValuation,
    calculate_proposed_lp_result,
)


def _model() -> ProposedLpModelIdentity:
    return ProposedLpModelIdentity("chain-x", "venue-y", "pool-z", "model-v1", "USDC")


def _valuation(**changes: object) -> ProposedLpValuation:
    values: dict[str, object] = {
        "model": _model(), "inventory_quote": Decimal("400"), "separately_held_fees_quote": Decimal("5"),
        "fees_reinvested": False, "gas_quote": Decimal("3"), "rebalance_cost_quote": Decimal("0"),
        "comparator_quote": Decimal("500"), "external_cash_flows_quote": Decimal("0"),
    }
    values.update(changes)
    return ProposedLpValuation(**values)  # type: ignore[arg-type]


def test_lp_readiness_requires_named_model_and_every_evidence_category() -> None:
    fields = {name: ProposedLpEvidenceField("KNOWN", f"source:{name}") for name in (
        "position_history", "fee_history", "price_history", "cost_history", "comparator", "action_semantics",
    )}
    assert ProposedLpReadiness(_model(), fields).assess() == (True, ())
    fields["fee_history"] = ProposedLpEvidenceField("UNKNOWN")
    assert ProposedLpReadiness(_model(), fields).assess() == (False, ("UNKNOWN:fee_history",))


def test_lp_net_benefit_keeps_il_diagnostic_out_of_the_formula() -> None:
    result = calculate_proposed_lp_result(_valuation())
    assert result.impermanent_loss_diagnostic_quote == Decimal("-100")
    assert result.net_benefit_quote == Decimal("-98")
    assert result.reasons == ()


def test_unknown_cost_or_double_counted_reinvested_fee_withholds_net_result() -> None:
    unknown = calculate_proposed_lp_result(_valuation(gas_quote=None))
    double_count = calculate_proposed_lp_result(_valuation(fees_reinvested=True))
    assert unknown.net_benefit_quote is None and unknown.reasons == ("UNKNOWN:gas_quote",)
    assert double_count.net_benefit_quote is None and double_count.reasons == ("REINVESTED_FEE_DOUBLE_COUNT",)


def test_known_zero_is_not_an_unknown_value() -> None:
    result = calculate_proposed_lp_result(_valuation(separately_held_fees_quote=Decimal("0"), gas_quote=Decimal("0")))
    assert result.net_benefit_quote == Decimal("-100")


def test_negative_cost_is_refused_rather_than_improving_lp_result() -> None:
    result = calculate_proposed_lp_result(_valuation(gas_quote=Decimal("-1")))
    assert result.net_benefit_quote is None
    assert result.reasons == ("NEGATIVE_LP_COMPONENT",)
