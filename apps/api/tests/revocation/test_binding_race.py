"""Real cross-session race: the accepted binding row lock is held through the removal commit."""

from __future__ import annotations

import datetime as dt
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from edge_os_api.revocation.removal_service import RemovalService, SavedWalletBindingReader

from revocation._support import (
    AGENT_A,
    NETWORK,
    OWNER_A,
    WALLET_A,
    observation,
    removal_request,
    seed_wallet_binding,
)


class _BlockingClock:
    """A controlled clock that pauses the service after its binding read, holding the transaction."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self) -> dt.datetime:
        self.entered.set()
        assert self.release.wait(5), "the test did not release the clock"
        return dt.datetime(2026, 1, 1, 0, 16, tzinfo=dt.timezone.utc)


def _attempt_binding_update(engine) -> None:
    with engine.connect() as other:
        other.execute(text("SET lock_timeout = '250ms'"))
        with pytest.raises(OperationalError):
            other.execute(text(
                "UPDATE public.wallet_setups SET wallet_id = 'moved' WHERE agent_id = 'agent-a'"))


def test_reader_row_lock_blocks_a_concurrent_binding_update(revocation_engine):
    seed_wallet_binding(revocation_engine, OWNER_A)
    holder = Session(revocation_engine)
    try:
        binding = SavedWalletBindingReader().current_binding(
            holder, OWNER_A, agent_id=AGENT_A, network_id=NETWORK, lock=True)
        assert binding is not None and binding.wallet_id == WALLET_A
        _attempt_binding_update(revocation_engine)
    finally:
        holder.rollback()
        holder.close()


def test_reconcile_holds_the_binding_row_lock_through_commit(revocation_engine, removal_service):
    seed_wallet_binding(revocation_engine, OWNER_A)
    view = removal_service.request_removal(OWNER_A, removal_request())
    clock = _BlockingClock()
    service = RemovalService(lambda: Session(revocation_engine), clock=clock)
    outcome: dict = {}

    def run() -> None:
        outcome["result"] = service.reconcile(
            OWNER_A, observation(view.request_id, observation_key="o1", observed_state="PENDING"))

    thread = threading.Thread(target=run)
    thread.start()
    assert clock.entered.wait(5), "the service did not reach its save point"
    # While the removal transaction holds the binding row lock, a concurrent
    # binding change cannot commit.
    _attempt_binding_update(revocation_engine)
    clock.release.set()
    thread.join(5)
    assert thread.is_alive() is False
    assert outcome["result"].state == "PENDING"
