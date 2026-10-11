"""Small flow helpers for the recovery tests. They compose public interfaces only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from edge_os_api.admission.types import AssetAmount, IdentityBinding
from edge_os_api.execution.models import IntentRow, QueueRow, ClaimRow
from edge_os_api.recovery.types import OutcomeEvidence

from admission._builders import AGENT_A, BASE, NATIVE, NETWORK, QUOTE, WALLET_A
from execution._support import enqueue_entry, entry_inputs, quote
from execution._support import transport as exec_transport


def load_intent(factory: sessionmaker, owner: uuid.UUID, action_id: str) -> IntentRow:
    with factory() as session:
        return session.execute(select(IntentRow).where(
            IntentRow.owner_id == owner, IntentRow.action_id == action_id)).scalar_one()


def load_queue(factory: sessionmaker, owner: uuid.UUID, action_id: str) -> QueueRow:
    with factory() as session:
        return session.execute(select(QueueRow).where(
            QueueRow.owner_id == owner, QueueRow.action_id == action_id)).scalar_one()


def active_claim(factory: sessionmaker, owner: uuid.UUID) -> ClaimRow | None:
    with factory() as session:
        return session.execute(select(ClaimRow).where(
            ClaimRow.owner_id == owner, ClaimRow.agent_id == AGENT_A, ClaimRow.wallet_id == WALLET_A,
            ClaimRow.network_id == NETWORK, ClaimRow.released_at.is_(None))).scalar_one_or_none()


def open_unknown_entry(service, owner, revision, *, quantity: str = "10", quote_input: str = "110",
                       position_id: str = "position-1", mode: str = "UNKNOWN", approval=None):
    """Admit an entry and leave it in the submission-unknown (lost or unknown ack) state."""
    _decision, approval, context, result = enqueue_entry(
        service, owner, revision, quantity=quantity, quote_input=quote_input, position_id=position_id,
        approval=approval)
    assert result.admission_status == "ADMITTED", result.admission_reason
    tick = service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(),
        quote=quote(result.intent.action_id, revision, "110"),
        transport=exec_transport(mode, action_id=result.intent.action_id))
    assert tick.status == "SUBMITTED_UNKNOWN", tick
    return approval, context, result


def confirmed_actuals(*, quote_raw: str = "110", base_raw: str = "10", gas_raw: str = "2"):
    return (AssetAmount(asset_id=QUOTE, raw=quote_raw, decimals=0),
            AssetAmount(asset_id=BASE, raw=base_raw, decimals=0),
            AssetAmount(asset_id=NATIVE, raw=gas_raw, decimals=0))


def evidence_for(factory: sessionmaker, owner: uuid.UUID, action_id: str, *, outcome: str = "CONFIRMED",
                 actual_input: AssetAmount | None = None, actual_output: AssetAmount | None = None,
                 actual_gas: AssetAmount | None = None, detail: str = "local-fixture",
                 observed_at: str = "2026-01-01T00:20:00Z",
                 source_ref: str = "synthetic:p24-authored-outcome",
                 binding: IdentityBinding | None = None, evidence_action_id: str | None = None,
                 operation: str | None = None, revision_id: str | None = None,
                 policy_binding: str | None = None, payload_hash: str | None = None) -> OutcomeEvidence:
    row = load_intent(factory, owner, action_id)
    return OutcomeEvidence(
        action_id=evidence_action_id or row.action_id,
        binding=binding or IdentityBinding(
            agent_id=row.agent_id, wallet_id=row.wallet_id, network_id=row.network_id,
            strategy_revision=row.revision_id, mandate_id=row.mandate_id),
        operation=operation or row.operation,
        revision_id=revision_id or row.revision_id,
        policy_binding=policy_binding or row.policy_binding,
        payload_hash=payload_hash or row.payload_hash,
        outcome=outcome, detail=detail, actual_input=actual_input, actual_output=actual_output,
        actual_gas=actual_gas, observed_at=observed_at, source_ref=source_ref)
