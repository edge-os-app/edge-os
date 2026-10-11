"""Authored synthetic builders for execution tests.

Every approval is labelled SYNTHETIC_AUTHORED and is injectable only in the
local test stage. Amounts are invented for local determinism; they do not
describe a live account, token, provider response or production limit.
"""

from __future__ import annotations

import copy
import datetime as dt

from edge_os_api.admission.types import (
    AdmissionContext,
    AllowanceCap,
    ApprovalSnapshot,
    AssetAmount,
    Holding,
    HoldingsSnapshot,
    IdentityBinding,
    PositionState,
    StopSpec,
    ValueState,
)
from edge_os_api.execution.types import EvaluationInputs, FrozenRevision, InputObservation, IntentTerms, freeze_revision
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.strategies import compiler as strategy_compiler

from admission._builders import AGENT_A, BASE, NATIVE, NETWORK, QUOTE, WALLET_A, WALLET_B, AGENT_B

DECISION_TIME = dt.datetime(2026, 1, 1, 0, 15, tzinfo=dt.timezone.utc)
STRATEGY_ID = "p23-authored-spot-v1"
MANDATE = "p23-mandate-v1"
POLICY = "p23-policy-v1"


def iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


def gt_constant(value: str = "100", unit: str = "PRICE") -> dict:
    return {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": value, "unit": unit}]}


def lt_constant(value: str = "100", unit: str = "PRICE") -> dict:
    return {"op": "lt", "args": [{"op": "price"}, {"op": "constant", "value": value, "unit": unit}]}


def relative_volume_gt(value: str = "2") -> dict:
    return {"op": "gt", "args": [
        {"op": "relative_volume", "lookback_buckets": 2},
        {"op": "constant", "value": value, "unit": "DIMENSIONLESS"},
    ]}


def make_strategy(*, entry: dict, exit_: dict, invalidation: dict | None = None,
                  data_inputs: tuple[str, ...] = ("price",), strategy_id: str = STRATEGY_ID) -> dict:
    base = copy.deepcopy(record_contract.FIXTURE_STRATEGY)
    base["strategy_id"] = strategy_id
    base["schema_version"] = strategy_compiler.CONTRACT["identity"]["strategy_schema"]
    base["semantic_manifest"] = dict(strategy_compiler.MANIFEST)
    base["data_inputs"] = list(data_inputs)
    base["entry"] = entry
    base["exit"] = exit_
    base["invalidation"] = invalidation or {
        "state": "NOT_REQUESTED", "source_ref": "synthetic:adopted-no-invalidation"}
    history = max(strategy_compiler.required_history(entry, base["market"]),
                  strategy_compiler.required_history(exit_, base["market"]))
    if base["invalidation"].get("state") != "NOT_REQUESTED":
        history = max(history, strategy_compiler.required_history(base["invalidation"], base["market"]))
    base["warmup_buckets"] = history
    return base


def frozen_entry_exit(*, entry: dict | None = None, exit_: dict | None = None,
                      invalidation: dict | None = None, data_inputs: tuple[str, ...] = ("price",),
                      strategy_id: str = STRATEGY_ID) -> FrozenRevision:
    strategy = make_strategy(
        entry=entry or gt_constant(), exit_=exit_ or lt_constant(),
        invalidation=invalidation, data_inputs=data_inputs, strategy_id=strategy_id)
    return freeze_revision(strategy)


def _rows(values: list[str | None], ends: list[dt.datetime], *, reasons=None, future=None,
          unqualified=None) -> list[InputObservation | None]:
    reasons, future, unqualified = reasons or {}, future or set(), unqualified or set()
    rows: list[InputObservation | None] = []
    for index, value in enumerate(values):
        if value is None:
            rows.append(None)
            continue
        rows.append(InputObservation(
            value=value, bucket_end=iso(ends[index]), qualified=index not in unqualified,
            available_at=iso(DECISION_TIME + dt.timedelta(seconds=1)) if index in future else None,
            reasons=list(reasons.get(index, ()))))
    return rows


def make_inputs(prices: list[str | None], volumes: list[str | None], *, position_open: bool,
                position: int = 0, decision_time: dt.datetime = DECISION_TIME,
                price_reasons=None, volume_reasons=None, price_future=None, volume_future=None,
                price_unqualified=None) -> EvaluationInputs:
    assert len(prices) == len(volumes)
    first_end = decision_time - dt.timedelta(minutes=5 * position)
    ends = [first_end + dt.timedelta(minutes=5 * index) for index in range(len(prices))]
    return EvaluationInputs(
        decision_time=iso(decision_time), position=position, position_open=position_open,
        scheduled_bucket_ends=[iso(end) for end in ends],
        prices=_rows(prices, ends, reasons=price_reasons, future=price_future, unqualified=price_unqualified),
        quote_volumes=_rows(volumes, ends, reasons=volume_reasons, future=volume_future))


def binding_for(revision_id: str, *, agent_id: str = AGENT_A, wallet_id: str = WALLET_A,
                network_id: str = NETWORK, mandate_id: str = MANDATE) -> IdentityBinding:
    return IdentityBinding(agent_id=agent_id, wallet_id=wallet_id, network_id=network_id,
                           strategy_revision=revision_id, mandate_id=mandate_id)


def scoped_approval(*, revision_id: str, mandate_id: str = MANDATE, policy_binding: str = POLICY,
                    agent_id: str = AGENT_A, wallet_id: str = WALLET_A, network_id: str = NETWORK,
                    state: str = "ACTIVE", expires_at: str = "2030-01-01T00:00:00Z",
                    actions: tuple[str, ...] = ("ENTRY", "EXIT"),
                    quote_approved_raw: str = "500", base_approved_raw: str = "1000",
                    gas_approved_raw: str = "50", per_action_gas_raw: str = "2",
                    per_exit_gas_raw: str = "2", attempt_budget: int = 5,
                    allocation_quote_raw: str = "5000", stops: tuple[str, ...] = (),
                    stop_scope_position: str | None = None,
                    exit_capacity_qualified: bool = True, valuation_qualified: bool = True,
                    cost_model_qualified: bool = True, approval_id: str = "p23-approval-v1") -> ApprovalSnapshot:
    stop_specs = []
    for value in stops:
        if value == "STOP_NEW_ENTRIES" and stop_scope_position:
            stop_specs.append(StopSpec(scope="POSITION", position_id=stop_scope_position, mode=value))
        else:
            stop_specs.append(StopSpec(scope="AGENT_WALLET_NETWORK", mode=value))
    return ApprovalSnapshot(
        approval_id=approval_id,
        binding=binding_for(revision_id, agent_id=agent_id, wallet_id=wallet_id,
                            network_id=network_id, mandate_id=mandate_id),
        state=state, policy_binding=policy_binding, expires_at=expires_at, actions=list(actions),
        allocation_quote=AllowanceCap(asset_id=QUOTE, decimals=0, approved_raw=allocation_quote_raw),
        quote_allowance=AllowanceCap(asset_id=QUOTE, decimals=0, approved_raw=quote_approved_raw),
        base_allowance=AllowanceCap(asset_id=BASE, decimals=0, approved_raw=base_approved_raw),
        gas=AllowanceCap(asset_id=NATIVE, decimals=0, approved_raw=gas_approved_raw),
        per_action_gas=AllowanceCap(asset_id=NATIVE, decimals=0, approved_raw=per_action_gas_raw),
        per_exit_gas=AllowanceCap(asset_id=NATIVE, decimals=0, approved_raw=per_exit_gas_raw),
        attempt_budget=attempt_budget, stops=stop_specs, exit_capacity_qualified=exit_capacity_qualified,
        valuation_qualified=valuation_qualified, cost_model_qualified=cost_model_qualified,
        fixture_label="SYNTHETIC_AUTHORED")


def scoped_context(*, agent_id: str = AGENT_A, wallet_id: str = WALLET_A, network_id: str = NETWORK,
                   quote_raw: str = "5000", base_raw: str = "0", native_raw: str = "20",
                   position_inventory: str | None = None, position_id: str = "position-1",
                   revision_id: str | None = None, mandate_id: str = MANDATE,
                   checked_at: str = "2026-01-01T00:16:00Z", unexplained: bool = False) -> AdmissionContext:
    positions = {}
    if position_inventory is not None:
        assert revision_id is not None
        positions[position_id] = PositionState(
            position_id=position_id,
            binding=binding_for(revision_id, agent_id=agent_id, wallet_id=wallet_id,
                                network_id=network_id, mandate_id=mandate_id),
            asset_id=BASE, decimals=0, inventory_raw=position_inventory)
    return AdmissionContext(
        checked_at=checked_at,
        holdings=HoldingsSnapshot(
            agent_id=agent_id, wallet_id=wallet_id, network_id=network_id,
            balances={QUOTE: Holding(asset_id=QUOTE, decimals=0, raw=quote_raw),
                      BASE: Holding(asset_id=BASE, decimals=0, raw=base_raw),
                      NATIVE: Holding(asset_id=NATIVE, decimals=0, raw=native_raw)},
            positions=positions, unexplained_external=unexplained))


def entry_terms(*, position_id: str = "position-1", quantity: str = "10", quote_input: str = "110",
                mandate_id: str = MANDATE, policy_binding: str = POLICY, quote_status: str = "FRESH") -> IntentTerms:
    return IntentTerms(
        operation="ENTRY", position_id=position_id, policy_binding=policy_binding, mandate_id=mandate_id,
        quote_asset_id=QUOTE, quantity=AssetAmount(asset_id=BASE, raw=quantity, decimals=0),
        quote_input=AssetAmount(asset_id=QUOTE, raw=quote_input, decimals=0),
        expected_quote=AssetAmount(asset_id=QUOTE, raw=quote_input, decimals=0), mark=None,
        quote_status=quote_status)


def exit_terms(*, position_id: str = "position-1", quantity: str = "10", mark: str = "250",
               expected_quote: str = "250", mandate_id: str = MANDATE, policy_binding: str = POLICY,
               quote_status: str = "FRESH") -> IntentTerms:
    return IntentTerms(
        operation="EXIT", position_id=position_id, policy_binding=policy_binding, mandate_id=mandate_id,
        quote_asset_id=QUOTE, quantity=AssetAmount(asset_id=BASE, raw=quantity, decimals=0),
        quote_input=None,
        expected_quote=AssetAmount(asset_id=QUOTE, raw=expected_quote, decimals=0),
        mark=ValueState(state="KNOWN", amount=AssetAmount(asset_id=QUOTE, raw=mark, decimals=0)),
        quote_status=quote_status)
