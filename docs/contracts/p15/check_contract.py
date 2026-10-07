#!/usr/bin/env python3
"""Offline conformance examples for the P15 contract. No provider access."""

from __future__ import annotations

import json
from datetime import datetime
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
        "strategy_revision", "mandate_id", "review_hash", "asset_id",
        "quantity_raw", "decimals", "operation", "policy_binding", "approval_id",
        "deployment_id",
    )
    return all(left[field] == right[field] for field in fields)


def eligible_at_send(
    action: dict[str, object],
    preview: dict[str, object],
    current: dict[str, object],
    now: datetime,
    stop: dict[str, object] | None = None,
) -> bool:
    if action["status"] != "QUEUED" or not matches_binding(preview, action):
        return False
    current_fields = (
        "owner_id", "agent_id", "wallet_id", "network_id", "strategy_revision",
        "mandate_id", "approval_id", "deployment_id",
    )
    if any(action[field] != current[field] for field in current_fields):
        return False
    if current["mandate_status"] != "ACTIVE":
        return False
    mandate_expiry = datetime.fromisoformat(
        str(current["mandate_expires_at"]).replace("Z", "+00:00")
    )
    if mandate_expiry <= now:
        return False
    if (
        current["policy_status"] != "ACTIVE"
        or action["policy_binding"] != current["policy_binding"]
    ):
        return False
    preview_expiry = datetime.fromisoformat(
        str(preview["expires_at"]).replace("Z", "+00:00")
    )
    if preview_expiry <= now:
        return False
    if stop:
        scope = stop["scope"]
        if scope not in {"POSITION", "DEPLOYMENT", "AGENT_WALLET_NETWORK"}:
            return False
        if stop["mode"] not in {"STOP_NEW_ENTRIES", "HALT_ALL_SWAPS"}:
            return False
        applies = all(
            stop[field] == action[field]
            for field in ("owner_id", "agent_id", "wallet_id", "network_id")
        )
        if scope == "POSITION":
            applies = applies and stop["position_id"] == action["position_id"]
        elif scope == "DEPLOYMENT":
            applies = applies and stop["deployment_id"] == action["deployment_id"]
        if applies and stop["mode"] == "HALT_ALL_SWAPS":
            return False
        if applies and stop["mode"] == "STOP_NEW_ENTRIES":
            return action["operation"] == "EXIT" and stop["exit_authority"] == "ACTIVE_EXPLICIT_MANDATE"
    return True


def main() -> None:
    contract = load("contract.json")
    fixture = load("fixtures.json")

    assert contract["contract_id"] == "edge-os.wallet-mandate-account"
    assert fixture["contract_version"] == contract["version"]
    assert contract["network_ids"] == ["monad:143", "monad-testnet:10143"]
    for stop in (
        fixture["pretrade_stop"], fixture["entries_only_stop"], fixture["posttrade_halt"],
        fixture["send_time_examples"]["entries_only_stop"],
        fixture["send_time_examples"]["halt_all_stop"],
        fixture["send_time_examples"]["deployment_stop"],
    ):
        assert all(field in stop for field in contract["stop_scope_targets"][stop["scope"]])
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
        assert position["owner_id"] == owner["owner_id"]
        assert position["wallet_id"] == owner["wallet_id"]
        assert position["network_id"] == owner["network_id"]
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
    assert RAW_AMOUNT.fullmatch(str(preview["quantity_raw"]))
    assert RAW_AMOUNT.fullmatch(str(action["quantity_raw"]))
    position = next(item for item in positions if item["position_id"] == action["position_id"])
    assert all(position[field] == action[field] for field in (
        "owner_id", "agent_id", "wallet_id", "network_id", "strategy_revision", "mandate_id",
    ))
    stale_action = dict(action, strategy_revision="strategy-a-v4")
    assert not matches_binding(preview, stale_action)
    changed_input = dict(action, review_hash="sha256:changed-input")
    assert not matches_binding(preview, changed_input)
    changed_quantity = dict(action, quantity_raw="6")
    assert not matches_binding(preview, changed_quantity)
    changed_asset = dict(action, asset_id="monad:143/asset:OTHER")
    assert not matches_binding(preview, changed_asset)
    cross_wallet_action = dict(action, agent_id="agent-a", wallet_id="wallet-a")
    assert not matches_binding(preview, cross_wallet_action)

    snapshots = fixture["approval_snapshots"]
    assert len(snapshots) == 4
    approvals = {snapshot["approval_id"]: snapshot for snapshot in snapshots}
    assert approvals["approval-a-v2"]["superseded_by"] == "approval-a-v3"
    assert approvals["approval-a-v3"]["superseded_by"] == "approval-a-v4"
    assert approvals["approval-a-v4"]["supersedes"] == "approval-a-v3"
    mandate_bindings: dict[str, set[tuple[str, str, str, str, str]]] = {}
    for snapshot in snapshots:
        mandate_bindings.setdefault(snapshot["mandate_id"], set()).add((
            snapshot["owner_id"], snapshot["agent_id"], snapshot["wallet_id"],
            snapshot["network_id"], snapshot["strategy_revision"],
        ))
    assert all(len(bindings) == 1 for bindings in mandate_bindings.values())
    for position in positions:
        assert any(
            snapshot["owner_id"] == position["owner_id"]
            and snapshot["agent_id"] == position["agent_id"]
            and snapshot["wallet_id"] == position["wallet_id"]
            and snapshot["network_id"] == position["network_id"]
            and snapshot["strategy_revision"] == position["strategy_revision"]
            and snapshot["mandate_id"] == position["mandate_id"]
            for snapshot in snapshots
        )

    queues = fixture["queues"]
    assert queues["agent-a"]["unresolved_action"] == "action-unknown"
    assert queues["agent-a"]["reservations_retained"] is True
    assert queues["agent-a"]["next_economic_action_allowed"] is False
    assert queues["agent-b"]["next_economic_action_allowed"] is True
    authority = fixture["current_authority"]["agent-b"]
    send = fixture["send_time_examples"]
    send_now = datetime.fromisoformat(send["checked_at"].replace("Z", "+00:00"))
    assert eligible_at_send(action, preview, authority, send_now)
    assert eligible_at_send(
        action, preview, authority, send_now, send["entries_only_stop"]
    )
    revoked = dict(authority, mandate_status="REVOKED")
    assert not eligible_at_send(action, preview, revoked, send_now)
    expired_mandate = dict(authority, mandate_expires_at=send["checked_at"])
    assert not eligible_at_send(action, preview, expired_mandate, send_now)
    stale_policy = dict(authority, policy_binding="policy-b-old")
    assert not eligible_at_send(action, preview, stale_policy, send_now)
    expired_preview = dict(preview, expires_at=send["expiry_boundary"])
    assert not eligible_at_send(action, expired_preview, authority, send_now)
    entry_preview = dict(preview, action_id="action-b-entry-1", operation="ENTRY")
    entry_action = dict(action, action_id="action-b-entry-1", operation="ENTRY")
    assert not eligible_at_send(
        entry_action, entry_preview, authority, send_now, send["entries_only_stop"]
    )
    assert not eligible_at_send(
        action, preview, authority, send_now, send["halt_all_stop"]
    )
    assert not eligible_at_send(action, preview, authority, send_now, send["deployment_stop"])
    other_deployment_stop = dict(send["deployment_stop"], deployment_id="deployment-other")
    assert eligible_at_send(action, preview, authority, send_now, other_deployment_stop)
    other_position_stop = dict(send["entries_only_stop"], position_id="position-other")
    assert eligible_at_send(action, preview, authority, send_now, other_position_stop)
    queue_candidates = send["priority_candidates"]
    priority = {"EXIT": 0, "ENTRY": 1, "ADDITION": 1}
    ordered = sorted(
        queue_candidates,
        key=lambda item: (priority[item["operation"]], item["action_id"]),
    )
    assert [item["action_id"] for item in ordered] == send["expected_priority_order"]
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
    assert removal["owner_access_preserved"] is True
    assert renewal["preserved_consumed_raw"] == "300"
    assert renewal["preserved_reserved_raw"] == "100"
    assert renewal["preserved_stop_ids"] == renewal["stop_ids_after_renewal"]
    assert renewal["signer_state_after_renewal"] == "PENDING"
    assert renewal["new_strategy_revision_restores_authority"] is False
    assert fixture["creation_recovery"]["state"] == "UNKNOWN"
    recovery = fixture["creation_recovery"]
    assert recovery["reconcile_before_retry"] is True
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
    assert attempts["confirmed_revert"]["input_consumed"] is False
    assert attempts["proved_prebroadcast_denial"]["attempt_count"] == 0
    assert attempts["submission_unknown"]["reservations_retained"] is True
    resend = attempts["qualified_resend"]
    unresolved = queues["agent-a"]
    assert unresolved["transaction_hash"]
    assert unresolved["signed_transaction_reference"]
    assert unresolved["provider_request_references"]
    assert resend["signed_transaction_hash"] == unresolved["transaction_hash"]
    assert resend["signed_transaction_reference"] == unresolved["signed_transaction_reference"]
    assert unresolved["provider_request_id"] in unresolved["provider_request_references"]
    assert resend["provider_request_id"] in unresolved["provider_request_references"]
    assert resend["provider_request_count"] == len(unresolved["provider_request_references"])
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
