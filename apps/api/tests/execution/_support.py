"""Small flow helpers for the execution tests. They compose public interfaces only."""

from __future__ import annotations

import threading

from edge_os_api.admission.types import AssetAmount
from edge_os_api.execution.transport import FixturePlan, LocalFixtureTransport
from edge_os_api.execution.types import ActionQuote

from admission._builders import AGENT_A, NETWORK, QUOTE, WALLET_A
from execution._builders import (
    entry_terms,
    make_inputs,
    scoped_approval,
    scoped_context,
)


def quote(amount_raw: str = "110", *, asset: str = QUOTE, decimals: int = 0,
          observed_at: str = "2026-01-01T00:16:00Z",
          expires_at: str = "2026-01-01T00:21:00Z",
          source_ref: str = "synthetic:authored-current-action-quote") -> ActionQuote:
    """An authored current action quote. Not a real provider quote."""
    return ActionQuote(
        quote_asset_id=asset, amount=AssetAmount(asset_id=asset, raw=amount_raw, decimals=decimals),
        observed_at=observed_at, expires_at=expires_at, source_ref=source_ref)


def transport(mode: str, *, action_id: str | None = None, **plan) -> LocalFixtureTransport:
    plan_obj = FixturePlan(mode=mode, **plan)
    return LocalFixtureTransport({action_id: plan_obj} if action_id else {}, plan_obj)


def entry_inputs(prices=("110",)):
    """Current submission-time observations that keep the entry rule TRUE."""
    return make_inputs(list(prices), ["5"], position_open=False)


def exit_inputs(prices=("90",)):
    """Current submission-time observations that keep the exit rule TRUE."""
    return make_inputs(list(prices), ["5"], position_open=True)


def decide_entry(service, owner, revision, *, prices=("110",), position_open=False):
    return service.evaluate_and_decide(
        owner, revision, make_inputs(list(prices), ["5"], position_open=position_open),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)


def enqueue_entry(service, owner, revision, *, quantity: str = "10", quote_input: str = "110",
                  position_id: str = "position-1", approval=None, context=None, prices=("110",)):
    decision = decide_entry(service, owner, revision, prices=prices)
    approval = approval or scoped_approval(revision_id=revision.revision_id)
    context = context or scoped_context()
    result = service.enqueue(
        owner, decision.decision_id,
        entry_terms(position_id=position_id, quantity=quantity, quote_input=quote_input),
        approval, context)
    return decision, approval, context, result


def open_position(service, owner, revision, *, quantity: str = "10", quote_input: str = "110",
                  position_id: str = "position-1"):
    _decision, approval, context, result = enqueue_entry(
        service, owner, revision, quantity=quantity, quote_input=quote_input, position_id=position_id)
    assert result.admission_status == "ADMITTED", result.admission_reason
    tick = service.tick(
        owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
        context=context, revision=revision, inputs=entry_inputs(), quote=quote("110"),
        transport=transport("ACCEPT", action_id=result.intent.action_id))
    assert tick.status == "SUBMITTED_CONFIRMED", tick
    return approval, context


def run_concurrently(count: int, target) -> list:
    barrier = threading.Barrier(count)
    results: list = [None] * count

    def worker(index: int) -> None:
        barrier.wait()
        results[index] = target(index)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results
