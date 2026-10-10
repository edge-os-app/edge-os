"""Authored synthetic builders for admission tests.

Every approval here is clearly labelled SYNTHETIC_AUTHORED and is injectable
only in test/local stage. Amounts are invented for local determinism; they do
not describe a live account, token, provider response or production limit.
"""

from __future__ import annotations

import uuid

from edge_os_api.admission.types import (
    ActionInput,
    ActionIntent,
    AdmissionContext,
    AllowanceCap,
    ApprovalSnapshot,
    AssetAmount,
    HoldingsSnapshot,
    Holding,
    IdentityBinding,
    PositionState,
    ValueState,
)

OWNER_A = uuid.UUID("b212b4e8-88d0-4233-bc92-084bace61d08")
OWNER_B = uuid.UUID("22ad0953-197e-4f96-b003-3459cb7b02cf")
AGENT_A = "agent-a"
AGENT_B = "agent-b"
WALLET_A = "wallet-a"
WALLET_B = "wallet-b"
NETWORK = "monad:143"
NETWORK_TESTNET = "monad-testnet:10143"
STRATEGY_A = "strategy-a-v3"
MANDATE_A = "mandate-a-v1"
POLICY_A = "policy-a-v1"
APPROVAL_A = "approval-a-v3"
QUOTE = "monad:143/asset:USDC"
BASE = "monad:143/asset:MOE"
NATIVE = "monad:143/native"
POSITION_A = "position-a-1"
POSITION_B = "position-b-1"


def new_action_id() -> str:
    return f"action-{uuid.uuid4().hex[:8]}"


def binding_a() -> IdentityBinding:
    return IdentityBinding(
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        strategy_revision=STRATEGY_A, mandate_id=MANDATE_A,
    )


def approval_a(*, state: str = "ACTIVE", expires_at: str = "2030-01-01T00:00:00Z",
               actions: tuple[str, ...] = ("ENTRY", "ADDITION", "EXIT"),
               quote_approved_raw: str = "500", base_approved_raw: str = "1000",
               gas_approved_raw: str = "50", per_action_gas_raw: str = "2") -> ApprovalSnapshot:
    return ApprovalSnapshot(
        approval_id=APPROVAL_A,
        binding=binding_a(),
        state=state,
        policy_binding=POLICY_A,
        expires_at=expires_at,
        actions=list(actions),
        quote_allowance=AllowanceCap(asset_id=QUOTE, decimals=0, approved_raw=quote_approved_raw),
        base_allowance=AllowanceCap(asset_id=BASE, decimals=0, approved_raw=base_approved_raw),
        gas=AllowanceCap(asset_id=NATIVE, decimals=0, approved_raw=gas_approved_raw),
        per_action_gas=AllowanceCap(asset_id=NATIVE, decimals=0, approved_raw=per_action_gas_raw),
        fixture_label="SYNTHETIC_AUTHORED",
    )


def holdings_a(*, quote_raw: str = "5000", base_raw: str = "40", native_raw: str = "20",
               position_inventory: str | None = None, position_id: str = POSITION_A,
               unexplained: bool = False) -> HoldingsSnapshot:
    positions: dict[str, PositionState] = {}
    if position_inventory is not None:
        positions[position_id] = PositionState(
            position_id=position_id, binding=binding_a(), asset_id=BASE,
            decimals=0, inventory_raw=position_inventory,
        )
    return HoldingsSnapshot(
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        balances={QUOTE: Holding(asset_id=QUOTE, decimals=0, raw=quote_raw),
                  BASE: Holding(asset_id=BASE, decimals=0, raw=base_raw),
                  NATIVE: Holding(asset_id=NATIVE, decimals=0, raw=native_raw)},
        positions=positions,
        unexplained_external=unexplained,
    )


def context_a(checked_at: str = "2026-10-10T00:00:00Z", **holdings: object) -> AdmissionContext:
    position_inventory = holdings.get("position_inventory")
    return AdmissionContext(
        checked_at=checked_at,
        holdings=holdings_a(
            position_inventory=str(position_inventory) if position_inventory is not None else None,
            unexplained=bool(holdings.get("unexplained", False)),
        ),
    )


def intent_a(
    operation: str,
    quantity_raw: str,
    *,
    action_id: str | None = None,
    position_id: str | None = POSITION_A,
    review_hash: str | None = None,
    quote_input_raw: str | None = None,
    quote_status: str = "FRESH",
    mark: str = "KNOWN",
    policy_binding: str = POLICY_A,
    binding: IdentityBinding | None = None,
) -> ActionIntent:
    expected_quote = AssetAmount(asset_id=QUOTE, raw=(quote_input_raw or "0") if operation != "EXIT" else "250", decimals=0)
    if operation == "EXIT":
        if mark == "KNOWN":
            mark_state = ValueState(state="KNOWN", amount=AssetAmount(asset_id=QUOTE, raw="22", decimals=0))
        elif mark == "UNKNOWN":
            mark_state = ValueState(state="UNKNOWN", amount=None)
        else:
            mark_state = None
    else:
        mark_state = None
    return ActionIntent(
        action_id=action_id or new_action_id(),
        binding=binding if binding is not None else binding_a(),
        policy_binding=policy_binding,
        position_id=position_id,
        operation=operation,
        review_hash=review_hash or "sha256:" + "a" * 64,
        quantity=AssetAmount(asset_id=BASE, raw=quantity_raw, decimals=0),
        input=ActionInput(
            quote_asset_id=QUOTE,
            quote_input=AssetAmount(asset_id=QUOTE, raw=quote_input_raw, decimals=0)
            if quote_input_raw is not None else None,
            mark=mark_state,
            quote_status=quote_status,
            expected_quote=expected_quote,
        ),
    )


def intent_entry(quantity_raw: str = "10", quote_input_raw: str = "110", **kwargs) -> ActionIntent:
    return intent_a("ENTRY", quantity_raw, quote_input_raw=quote_input_raw, **kwargs)


def intent_addition(quantity_raw: str = "10", quote_input_raw: str = "120", **kwargs) -> ActionIntent:
    return intent_a("ADDITION", quantity_raw, quote_input_raw=quote_input_raw, **kwargs)


def intent_exit(quantity_raw: str = "5", **kwargs) -> ActionIntent:
    return intent_a("EXIT", quantity_raw, quote_input_raw=None, **kwargs)