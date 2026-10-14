"""Proposal-only LP readiness and reporting arithmetic for P36–P39.

It accepts a caller-selected model and evidence facts but does not choose a
venue, reconstruct an AMM position, or grant an LP action/execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Mapping

from edge_os_api.strategies import compiler as strategy_compiler


@dataclass(frozen=True)
class ProposedLpModelIdentity:
    chain: str
    venue: str
    pool_id: str
    model_version: str
    quote_asset: str

    def is_usable(self) -> bool:
        return all((self.chain, self.venue, self.pool_id, self.model_version, self.quote_asset))


@dataclass(frozen=True)
class ProposedLpEvidenceField:
    """`UNKNOWN` is distinct from the known numeric value zero."""

    state: str  # KNOWN, NOT_APPLICABLE, or UNKNOWN
    source_ref: str | None = None

    def is_usable(self) -> bool:
        return (
            self.state == "KNOWN" and bool(self.source_ref)
        ) or (self.state == "NOT_APPLICABLE" and self.source_ref is None) or (
            self.state == "UNKNOWN" and self.source_ref is None
        )


@dataclass(frozen=True)
class ProposedLpReadiness:
    model: ProposedLpModelIdentity
    fields: Mapping[str, ProposedLpEvidenceField]

    def assess(self) -> tuple[bool, tuple[str, ...]]:
        required = (
            "position_history", "fee_history", "price_history", "cost_history",
            "comparator", "action_semantics",
        )
        if not self.model.is_usable():
            return False, ("MODEL_IDENTITY_UNAVAILABLE",)
        missing = tuple(
            f"UNKNOWN:{field}" for field in required
            if field not in self.fields or not self.fields[field].is_usable() or self.fields[field].state == "UNKNOWN"
        )
        return not missing, missing


@dataclass(frozen=True)
class ProposedLpValuation:
    model: ProposedLpModelIdentity
    inventory_quote: Decimal | None
    separately_held_fees_quote: Decimal | None
    fees_reinvested: bool
    gas_quote: Decimal | None
    rebalance_cost_quote: Decimal | None
    comparator_quote: Decimal | None
    external_cash_flows_quote: Decimal | None


@dataclass(frozen=True)
class ProposedLpResult:
    inventory_quote: Decimal | None
    separately_held_fees_quote: Decimal | None
    impermanent_loss_diagnostic_quote: Decimal | None
    net_benefit_quote: Decimal | None
    reasons: tuple[str, ...]


def _is_nonnegative_finite(value: Decimal | None) -> bool:
    return value is not None and value.is_finite() and value >= 0


def calculate_proposed_lp_result(valuation: ProposedLpValuation) -> ProposedLpResult:
    """Report components once; unknown inputs withhold only affected conclusions."""
    values = {
        "inventory_quote": valuation.inventory_quote,
        "separately_held_fees_quote": valuation.separately_held_fees_quote,
        "gas_quote": valuation.gas_quote,
        "rebalance_cost_quote": valuation.rebalance_cost_quote,
        "comparator_quote": valuation.comparator_quote,
        "external_cash_flows_quote": valuation.external_cash_flows_quote,
    }
    reasons = tuple(
        f"UNKNOWN:{name}" for name, value in values.items()
        if value is None or not value.is_finite()
    )
    if not valuation.model.is_usable():
        reasons += ("MODEL_IDENTITY_UNAVAILABLE",)
    if valuation.fees_reinvested and valuation.separately_held_fees_quote not in {None, Decimal(0)}:
        reasons += ("REINVESTED_FEE_DOUBLE_COUNT",)
    if any(values[name] is not None and values[name].is_finite() and values[name] < 0 for name in (
        "inventory_quote", "separately_held_fees_quote", "gas_quote", "rebalance_cost_quote", "comparator_quote",
    )):
        reasons += ("NEGATIVE_LP_COMPONENT",)
    impermanent_loss = None
    if (
        valuation.model.is_usable()
        and _is_nonnegative_finite(valuation.inventory_quote)
        and _is_nonnegative_finite(valuation.comparator_quote)
    ):
        with localcontext(strategy_compiler.NUMERIC):
            impermanent_loss = valuation.inventory_quote - valuation.comparator_quote
    if reasons:
        return ProposedLpResult(valuation.inventory_quote, valuation.separately_held_fees_quote, impermanent_loss, None, reasons)
    assert all(value is not None for value in values.values())
    with localcontext(strategy_compiler.NUMERIC):
        net_benefit = (
            valuation.inventory_quote + valuation.separately_held_fees_quote
            - valuation.gas_quote - valuation.rebalance_cost_quote
            - valuation.comparator_quote + valuation.external_cash_flows_quote
        )
    return ProposedLpResult(
        valuation.inventory_quote, valuation.separately_held_fees_quote, impermanent_loss, net_benefit, (),
    )
