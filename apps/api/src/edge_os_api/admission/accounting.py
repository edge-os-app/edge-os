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

ATTEMPT_ASSET = "attempt"
ACQUISITIONS = ("ENTRY", "ADDITION")
# Internal per-position exit holds use a reserved action-id namespace. A caller
# action id must never collide with it (G3).
HOLD_ACTION_PREFIX = "exit-hold:"


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


def _stop_applies(stop, intent: ActionIntent) -> bool:
    if stop.scope == "POSITION":
        return stop.position_id == intent.position_id
    return True


def denial_reasons(
    intent: ActionIntent,
    approval: ApprovalSnapshot,
    context: AdmissionContext,
    position_exists: bool,
) -> list[str]:
    reasons: list[str] = []

    if intent.action_id.startswith(HOLD_ACTION_PREFIX):
        reasons.append("RESERVED_ACTION_ID")
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

    # Scoped stops. HALT_ALL_SWAPS denies every operation; STOP_NEW_ENTRIES denies
    # only entries and additions. A local stop is not signer removal.
    for stop in approval.stops:
        if not _stop_applies(stop, intent):
            continue
        if stop.mode == "HALT_ALL_SWAPS":
            reasons.append("STOPPED_HALT_ALL_SWAPS")
        elif intent.operation in ACQUISITIONS:
            reasons.append("STOPPED_NEW_ENTRIES")

    # Required controls fail closed when not qualified for the adopted model.
    if intent.operation in ACQUISITIONS and not approval.exit_capacity_qualified:
        reasons.append("EXIT_CAPACITY_UNQUALIFIED")
    if not approval.cost_model_qualified:
        reasons.append("COST_MODEL_UNQUALIFIED")
    if intent.operation == "EXIT":
        if not approval.valuation_qualified:
            reasons.append("VALUATION_UNQUALIFIED")
        if intent.input.mark is None or intent.input.mark.state != "KNOWN":
            reasons.append("MISSING_VALUATION")

    # Cross-record asset and decimal identity must agree before reserving. The
    # adopted quote asset governs the exit mark, expected quote and actual output.
    base_asset = intent.quantity.asset_id
    quote_cap = approval.quote_allowance
    if base_asset != approval.base_allowance.asset_id:
        reasons.append("BASE_ASSET_MISMATCH")
    elif intent.quantity.decimals != approval.base_allowance.decimals:
        reasons.append("BASE_DECIMALS_MISMATCH")
    if intent.input.quote_asset_id != quote_cap.asset_id:
        reasons.append("QUOTE_ASSET_MISMATCH")
    quote_amounts: list[tuple[str, object]] = []
    if intent.operation in ACQUISITIONS:
        quote_amounts.append(("quote_input", intent.input.quote_input))
    else:
        quote_amounts.append(("mark", intent.input.mark.amount if intent.input.mark else None))
    quote_amounts.append(("expected_quote", intent.input.expected_quote))
    for name, amount in quote_amounts:
        if amount is None:
            continue
        if amount.asset_id != quote_cap.asset_id:
            reasons.append(f"{name.upper()}_ASSET_MISMATCH")
        elif amount.decimals != quote_cap.decimals:
            reasons.append(f"{name.upper()}_DECIMALS_MISMATCH")
    for amount in (intent.quantity, intent.input.quote_input):
        if amount is None:
            continue
        holding = holdings.balances.get(amount.asset_id)
        if holding is not None and holding.decimals != amount.decimals:
            reasons.append("HOLDINGS_DECIMALS_MISMATCH")

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
    """Required reservations for an admissible action, in deterministic order.

    Attempts, trading input and gas stay separate. Sell coverage is derived from
    attributed inventory plus pending acquisition reservations (see the service),
    so an acquisition does not carry a base capital reservation of its own.
    """
    quantity = intent.quantity.as_int()
    gas = approval.per_action_gas.as_int()
    exit_gas = approval.per_exit_gas.as_int()
    plan: list[ReservationNeed] = []
    requires_new_position = intent.operation == "ENTRY"

    if intent.operation in ACQUISITIONS:
        quote = intent.input.quote_input
        if quote is None:
            return ReservationPlan(ok=False, reason="MISSING_QUOTE_INPUT")
        plan.append(ReservationNeed("CAPITAL", quote.asset_id, quote.decimals, quote.as_int()))
        plan.append(ReservationNeed("INVENTORY", intent.quantity.asset_id, intent.quantity.decimals,
                                    quantity, intent.position_id))
        # An acquisition must also cover its intended exit: gas for the entry and
        # its exit, and one attempt each. Attempts are counted as two atoms here.
        plan.append(ReservationNeed("GAS", approval.gas.asset_id, approval.gas.decimals, gas + exit_gas))
        plan.append(ReservationNeed("ATTEMPT", ATTEMPT_ASSET, 0, 2))
        return ReservationPlan(ok=True, needs=plan, requires_new_position=requires_new_position)

    # EXIT uses the position's retained exit coverage; it reserves only its inventory
    # hold here. The exit gas and attempt are consumed from the position exit hold.
    if current_inventory is None or current_inventory < quantity:
        return ReservationPlan(ok=False, reason="INVENTORY_SHORTFALL")
    plan.append(ReservationNeed("INVENTORY", intent.quantity.asset_id, intent.quantity.decimals,
                                quantity, intent.position_id))
    return ReservationPlan(ok=True, needs=plan, requires_new_position=requires_new_position)