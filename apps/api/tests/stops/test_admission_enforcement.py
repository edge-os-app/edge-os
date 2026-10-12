"""Behavioral durable-stop enforcement at the real AdmissionService interface."""

from __future__ import annotations

import uuid

from edge_os_api.admission.types import (
    ActionInput,
    ActionIntent,
    AssetAmount,
    ValueState,
)

from admission._builders import (
    AGENT_A,
    BASE,
    NETWORK,
    POSITION_A,
    QUOTE,
    WALLET_A,
    approval_a,
    context_a,
    intent_addition,
    intent_entry,
    intent_exit,
)
from execution._builders import (
    POLICY,
    binding_for,
    frozen_entry_exit,
    scoped_approval,
    scoped_context,
)
from execution._support import enqueue_entry, entry_inputs, quote, transport
from stops._support import stop_request


def _denied_reason(decision) -> str:
    return decision.reason or ""


def test_durable_stop_denies_scoped_entry_and_addition(admission_service, stop_service, fresh_owner) -> None:
    approval = approval_a()
    stop_service.request_stop(fresh_owner, stop_request(position_id=POSITION_A))

    entry = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id=POSITION_A), approval, context_a())
    addition = admission_service.admit_and_reserve(
        fresh_owner, intent_addition(position_id=POSITION_A), approval, context_a())

    assert entry.status == "DENIED" and "STOPPED_NEW_ENTRIES" in _denied_reason(entry)
    assert addition.status == "DENIED" and "STOPPED_NEW_ENTRIES" in _denied_reason(addition)
    saved = admission_service.retrieve_decisions(fresh_owner, action_id=entry.action_id)
    assert saved[0].status == "DENIED" and "STOPPED_NEW_ENTRIES" in (saved[0].reason or "")


def test_agent_wallet_stop_denies_entry_before_a_position_exists(admission_service, stop_service, fresh_owner) -> None:
    stop_service.request_stop(
        fresh_owner, stop_request(scope="AGENT_WALLET_NETWORK", position_id=None))

    entry = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id="not-yet-created"), approval_a(), context_a())

    assert entry.status == "DENIED" and "STOPPED_NEW_ENTRIES" in _denied_reason(entry)


def test_halt_all_swaps_denies_scoped_exit(admission_service, stop_service, fresh_owner) -> None:
    stop_service.request_stop(
        fresh_owner, stop_request(mode="HALT_ALL_SWAPS", position_id=POSITION_A))

    exit_decision = admission_service.admit_and_reserve(
        fresh_owner, intent_exit(position_id=POSITION_A), approval_a(), context_a())

    assert exit_decision.status == "DENIED"
    assert "STOPPED_HALT_ALL_SWAPS" in _denied_reason(exit_decision)


def test_stop_did_not_mutate_the_approval_snapshot(admission_service, stop_service, fresh_owner) -> None:
    approval = approval_a()
    before = approval.content_hash()

    stop_service.request_stop(fresh_owner, stop_request(mode="HALT_ALL_SWAPS", position_id=POSITION_A))
    admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id=POSITION_A), approval, context_a())

    assert approval.stops == []
    assert approval.content_hash() == before


def test_owner_isolation_stop_does_not_deny_another_owner(admission_service, stop_service, fresh_owner) -> None:
    other_owner = uuid.uuid4()
    stop_service.request_stop(other_owner, stop_request(position_id=POSITION_A))

    decision = admission_service.admit_and_reserve(
        fresh_owner, intent_entry(position_id=POSITION_A), approval_a(), context_a())

    assert decision.status == "ADMITTED"


def test_stop_new_entries_keeps_an_approved_exit_available(
        admission_service, execution_service, stop_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    _decision, approval, context, entry = enqueue_entry(execution_service, fresh_owner, revision)
    opened = execution_service.tick(
        fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
        approval=approval, context=context, revision=revision, inputs=entry_inputs(),
        quote=quote(entry.intent.action_id, revision, "110"),
        transport=transport("ACCEPT", action_id=entry.intent.action_id))
    assert opened.status == "SUBMITTED_CONFIRMED"

    stop_service.request_stop(fresh_owner, stop_request(position_id="position-1"))

    exit_intent = ActionIntent(
        action_id="stop-test-exit-1", binding=binding_for(revision.revision_id), policy_binding=POLICY,
        position_id="position-1", operation="EXIT", review_hash="sha256:" + "b" * 64,
        quantity=AssetAmount(asset_id=BASE, raw="5", decimals=0),
        input=ActionInput(quote_asset_id=QUOTE, quote_input=None,
                          mark=ValueState(state="KNOWN", amount=AssetAmount(asset_id=QUOTE, raw="250", decimals=0)),
                          quote_status="FRESH", expected_quote=AssetAmount(asset_id=QUOTE, raw="250", decimals=0)))
    exit_approval = scoped_approval(revision_id=revision.revision_id)
    exit_context = scoped_context(position_inventory="10", position_id="position-1",
                                  revision_id=revision.revision_id)

    exit_decision = admission_service.admit_and_reserve(
        fresh_owner, exit_intent, exit_approval, exit_context)

    assert exit_decision.status == "ADMITTED", _denied_reason(exit_decision)


def test_expired_or_revoked_authority_still_denies_exits(admission_service, stop_service, fresh_owner) -> None:
    # STOP_NEW_ENTRIES does not stop the exit; the inactive authority still does.
    stop_service.request_stop(fresh_owner, stop_request(position_id=POSITION_A))
    revoked = admission_service.admit_and_reserve(
        fresh_owner, intent_exit(position_id=POSITION_A),
        approval_a(state="REVOKED"), context_a())
    assert revoked.status == "DENIED" and "APPROVAL_STATE:REVOKED" in _denied_reason(revoked)

    # HALT_ALL_SWAPS stops the exit; an expired authority denies it as well.
    stop_service.request_stop(
        fresh_owner, stop_request(mode="HALT_ALL_SWAPS", position_id=POSITION_A))
    expired = admission_service.admit_and_reserve(
        fresh_owner, intent_exit(position_id=POSITION_A),
        approval_a(expires_at="2020-01-01T00:00:00Z"), context_a())
    assert expired.status == "DENIED"
