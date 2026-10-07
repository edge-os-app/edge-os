#!/usr/bin/env python3
"""Offline conformance examples for the P15 contract. No provider access."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
RAW_AMOUNT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
OWNER_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


def load(name: str) -> dict[str, object]:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def matches_binding(left: dict[str, object], right: dict[str, object]) -> bool:
    fields = (
        "owner_id", "agent_id", "wallet_id", "network_id", "position_id",
        "strategy_revision", "mandate_id", "review_hash",
    )
    return all(left[field] == right[field] for field in fields)


def main() -> None:
    contract = load("contract.json")
    fixture = load("fixtures.json")

    assert contract["contract_id"] == "edge-os.wallet-mandate-account"
    assert fixture["contract_version"] == contract["version"]
    assert contract["network_ids"] == ["monad:143", "monad-testnet:10143"]
    assert not RAW_AMOUNT.fullmatch("01")
    assert not RAW_AMOUNT.fullmatch("-1")

    agents = fixture["agents"]
    positions = fixture["positions"]
    assert isinstance(agents, list) and len(agents) == 2
    assert isinstance(positions, list)
    assert len({agent["owner_id"] for agent in agents}) == 1
    assert OWNER_ID.fullmatch(agents[0]["owner_id"])
    assert contract["persisted_record_envelope"] == [
        "schema_version", "record_type", "record_id", "owner_id",
        "operation_id", "created_at", "content",
    ]
    wallets = {agent["wallet_id"] for agent in agents}
    assert len(wallets) == 2

    same_token = [
        position for position in positions
        if position["asset_id"] == "monad:143/asset:MOE"
    ]
    assert len(same_token) == 3
    assert len({position["position_id"] for position in same_token}) == 3
    assert len({
        (position["agent_id"], position["wallet_id"], position["strategy_revision"])
        for position in same_token
    }) == 3
    for position in same_token:
        owner = next(agent for agent in agents if agent["agent_id"] == position["agent_id"])
        assert position["wallet_id"] == owner["wallet_id"]
        assert RAW_AMOUNT.fullmatch(position["inventory_raw"])

    denied_cross_agent = fixture["cross_agent_control"]
    assert denied_cross_agent["agent_id"] != denied_cross_agent["position_agent_id"]
    assert denied_cross_agent["wallet_id"] != denied_cross_agent["position_wallet_id"]
    assert denied_cross_agent["expected"] == "DENY"
    owner_claim = fixture["owner_claim_control"]
    assert owner_claim["verified_owner_id"] != owner_claim["request_owner_id"]
    assert owner_claim["expected"] == "REJECT_422"

    preview = fixture["preview"]
    action = fixture["action"]
    assert matches_binding(preview, action)
    position = next(item for item in positions if item["position_id"] == action["position_id"])
    assert all(position[field] == action[field] for field in (
        "owner_id", "agent_id", "wallet_id", "network_id", "strategy_revision", "mandate_id",
    ))
    stale_action = dict(action, strategy_revision="strategy-a-v4")
    assert not matches_binding(preview, stale_action)
    changed_input = dict(action, review_hash="sha256:changed-input")
    assert not matches_binding(preview, changed_input)
    cross_wallet_action = dict(action, agent_id="agent-a", wallet_id="wallet-a")
    assert not matches_binding(preview, cross_wallet_action)

    snapshots = fixture["approval_snapshots"]
    assert len(snapshots) == 2
    assert snapshots[0]["approval_id"] != snapshots[1]["approval_id"]
    assert snapshots[0]["terms_hash"] != snapshots[1]["terms_hash"]
    assert snapshots[0]["superseded_by"] == snapshots[1]["approval_id"]

    queues = fixture["queues"]
    assert queues["agent-a"]["unresolved_action"] == "action-unknown"
    assert queues["agent-a"]["reservations_retained"] is True
    assert queues["agent-a"]["next_economic_action_allowed"] is False
    assert queues["agent-b"]["next_economic_action_allowed"] is True
    inventory = fixture["inventory_reservations"]
    reserved_inventory = sum(Decimal(item["raw"]) for item in inventory["position_reservations"])
    assert reserved_inventory == Decimal(inventory["available_raw"])
    assert reserved_inventory + Decimal(inventory["duplicate_attempt_raw"]) > Decimal(
        inventory["available_raw"]
    )
    assert inventory["duplicate_attempt_expected"] == "DENY"

    removal = fixture["signer_removal"]
    renewal = fixture["renewal"]
    assert removal["state"] == "PENDING"
    assert removal["new_submissions_allowed"] is False
    assert renewal["preserved_consumed_raw"] == "300"
    assert renewal["preserved_reserved_raw"] == "100"
    assert renewal["preserved_stop_ids"] == renewal["stop_ids_after_renewal"]
    assert renewal["signer_state_after_renewal"] == "PENDING"
    assert renewal["new_strategy_revision_restores_authority"] is False
    assert fixture["creation_recovery"]["state"] == "UNKNOWN"
    recovery = fixture["creation_recovery"]
    assert recovery["retry_wallet_id"] == recovery["original_wallet_id"]

    empty_agent = fixture["pretrade_stop"]
    assert empty_agent["positions"] == []
    assert empty_agent["scope"] == "AGENT_WALLET_NETWORK"
    assert empty_agent["mode"] == "STOP_NEW_ENTRIES"
    assert empty_agent["entries_allowed"] is False
    assert empty_agent["monitoring_allowed"] is True
    assert empty_agent["later_stop_clear_id"]
    entries_only = fixture["entries_only_stop"]
    assert entries_only["positions"] and entries_only["scope"] == "POSITION"
    assert entries_only["entries_allowed"] is False
    assert entries_only["exits_allowed"] is True
    assert entries_only["exit_authority"] == "ACTIVE_EXPLICIT_MANDATE"
    halt = fixture["posttrade_halt"]
    assert halt["positions"]
    assert halt["mode"] == "HALT_ALL_SWAPS"
    assert halt["entries_allowed"] is False and halt["exits_allowed"] is False
    assert halt["monitoring_allowed"] is True

    cancellation = fixture["cancellation"]
    assert cancellation["PROPOSED"] == "CANCELLED"
    assert cancellation["QUEUED"] == "CANCELLED"
    assert cancellation["SUBMITTED"] == "DENIED"
    attempts = fixture["attempt_semantics"]
    assert attempts["confirmed_success"]["attempt_count"] == 1
    assert attempts["confirmed_success"]["input_consumed_after_reconciliation"] is True
    assert attempts["confirmed_revert"]["attempt_count"] == 1
    assert attempts["confirmed_revert"]["gas_consumed"] is True
    assert attempts["proved_prebroadcast_denial"]["attempt_count"] == 0
    assert attempts["submission_unknown"]["reservations_retained"] is True
    resend = attempts["qualified_resend"]
    assert resend["provider_request_count"] == 2
    assert resend["economic_action_count"] == 1
    assert resend["action_id"] == queues["agent-a"]["unresolved_action"]
    assert attempts["changed_signed_transaction"]["expected"] == "NEW_AUTHORITY_REQUIRED"

    cost = fixture["cost_example"]
    basis = Decimal(cost["first_cost_quote"]) + Decimal(cost["addition_cost_quote"])
    units = Decimal(cost["first_units"]) + Decimal(cost["addition_units"])
    average = basis / units
    partial_basis = average * Decimal(cost["partial_exit_units"])
    realized = Decimal(cost["partial_exit_proceeds_quote"]) - partial_basis
    assert average == Decimal("110")
    assert partial_basis == Decimal("550")
    assert realized == Decimal("100")
    assert realized != Decimal("600")
    assert cost["gas_asset_id"] != cost["quote_asset_id"]
    assert cost["unrealized_mark"] is None
    assert cost["unrealized_status"] == "UNKNOWN"

    flows = fixture["capital_flows"]
    assert flows[0]["kind"] == "DEPOSIT"
    assert flows[0]["wallet_id"] == "wallet-a"
    assert flows[0]["status"] == "CONFIRMED"
    assert flows[0]["included_in_realized_result"] is False

    limits = fixture["allowance_example"]
    assert Decimal(limits["consumed_raw"]) + Decimal(limits["reserved_raw"]) <= Decimal(
        limits["approved_raw"]
    )
    assert Decimal(limits["remaining_raw"]) == (
        Decimal(limits["approved_raw"])
        - Decimal(limits["consumed_raw"])
        - Decimal(limits["reserved_raw"])
    )
    assert limits["asset_id"] == "monad:143/asset:USDC"
    assert limits["gas_asset_id"] == "monad:143/native"
    overdraw = fixture["allowance_overdraw_control"]
    assert Decimal(overdraw["consumed_raw"]) + Decimal(overdraw["reserved_raw"]) > Decimal(
        overdraw["approved_raw"]
    )
    assert overdraw["expected"] == "DENY"

    monitoring = fixture["monitoring"]
    assert monitoring["last_check_at"] and monitoring["last_result"]
    assert monitoring["next_check_at"] is None and monitoring["blocking_reason"]
    assert "private_reasoning" not in monitoring
    assert contract["return_metrics"] == "UNAVAILABLE_UNTIL_PROFILED"
    assert all(profile["consumers"] for profile in contract["qualification_profiles"])

    print("P15 contract fixtures: PASS")


if __name__ == "__main__":
    main()
