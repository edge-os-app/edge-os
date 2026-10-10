"""Pure admission decisions and reservation planning.

No database access here. `denial_reasons` returns the deterministic fail-closed
reasons; `reservation_plan` returns the reservation needs an admissible action
must acquire. Expected arithmetic is authored in tests, not recomputed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from edge_os_api.admission.types import (
    ActionIntent,
    ApprovalSnapshot,
    AdmissionContext,
    parse_utc,
)


def allowance_remaining(approved: int, consumed: int, reserved: int) -> int:
    return approved - consumed - reserved


def covered(approved: int, consumed: int, reserved: int, sought: int) -> bool:
    return consumed + reserved + sought <= approved


@dataclass(frozen=True)
class ReservationNeed:
    scope: str
    asset_id: str
    decimals: int
    raw: int
    position_id: str = ""


@dataclass
class ReservationPlan:
    ok: bool
    reason: str | None = None
    needs: list[ReservationNeed] = field(default_factory=list)
    requires_new_position: bool = False

    def need(self, scope: str, asset_id: str) -> ReservationNeed | None:
        for need in self.needs:
            if need.scope == scope and need.asset_id == asset_id:
                return need
        return None


def denial_reasons(
    intent: ActionIntent,
    approval: ApprovalSnapshot,
    context: AdmissionContext,
    position_exists: bool,
) -> list[str]:
    reasons: list[str] = []

    if intent.binding != approval.binding:
        reasons.append("BINDING_MISMATCH")
    if intent.policy_binding != approval.policy_binding:
        reasons.append("POLICY_MISMATCH")
    if approval.state != "ACTIVE":
        reasons.append(f"APPROVAL_STATE:{approval.state}")
    else:
        checked = parse_utc(context.checked_at)
        if not approval.is_active_at(checked):
            reasons.append("APPROVAL_EXPIRED")
    if intent.operation not in approval.actions:
        reasons.append("UNSUPPORTED_ACTION")
    if intent.input.quote_status != "FRESH":
        reasons.append("STALE_QUOTE")

    holdings = context.holdings
    if (holdings.agent_id, holdings.wallet_id, holdings.network_id) != (
            intent.binding.agent_id, intent.binding.wallet_id, intent.binding.network_id):
        reasons.append("CROSS_WALLET_BINDING")
    if holdings.unexplained_external:
        reasons.append("EXTERNAL_DISCREPANCY")

    if intent.operation == "EXIT":
        if intent.input.mark is None or intent.input.mark.state != "KNOWN":
            reasons.append("MISSING_VALUATION")

    if intent.operation == "ENTRY":
        if position_exists:
            reasons.append("POSITION_EXISTS")
    if intent.operation in {"ADDITION", "EXIT"} and not position_exists:
        reasons.append("POSITION_MISSING")

    return reasons


def plan_reservations(
    intent: ActionIntent,
    approval: ApprovalSnapshot,
    current_inventory: int | None,
) -> ReservationPlan:
    """Required reservations for an admissible action, in deterministic order."""
    quantity = intent.quantity.as_int()
    gas = approval.per_action_gas.as_int()
    plan: list[ReservationNeed] = []
    requires_new_position = intent.operation == "ENTRY"

    if intent.operation in {"ENTRY", "ADDITION"}:
        quote = intent.input.quote_input
        if quote is None:
            return ReservationPlan(ok=False, reason="MISSING_QUOTE_INPUT")
        plan.append(ReservationNeed("CAPITAL", quote.asset_id, quote.decimals, quote.as_int()))
        plan.append(ReservationNeed("CAPITAL", intent.quantity.asset_id, intent.quantity.decimals, quantity))
        if intent.position_id:
            plan.append(ReservationNeed("INVENTORY", intent.quantity.asset_id, intent.quantity.decimals,
                                        quantity, intent.position_id))
        plan.append(ReservationNeed("GAS", approval.gas.asset_id, approval.gas.decimals, gas))
        # Inventory that results after the addition must be sellable: an addition
        # may not create inventory beyond the sell coverage already reserved for the
        # acquired quantity. The plan is per-action, so nothing more is derived here.
    else:  # EXIT
        if current_inventory is None or current_inventory < quantity:
            return ReservationPlan(ok=False, reason="INVENTORY_SHORTFALL")
        plan.append(ReservationNeed("CAPITAL", intent.quantity.asset_id, intent.quantity.decimals, quantity))
        if intent.position_id:
            plan.append(ReservationNeed("INVENTORY", intent.quantity.asset_id, intent.quantity.decimals,
                                        quantity, intent.position_id))
        plan.append(ReservationNeed("GAS", approval.gas.asset_id, approval.gas.decimals, gas))

    return ReservationPlan(ok=True, needs=plan, requires_new_position=requires_new_position)