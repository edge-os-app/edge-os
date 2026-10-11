"""Concurrency and independent-process restart controls against the real run-labelled PostgreSQL.

Each process control runs the real funding service in an independent OS process. Crash scenarios stop
that process with `os._exit`. No control makes a network or provider call.
"""

from __future__ import annotations

import json
import threading
import uuid

from sqlalchemy import text as sql_text

from funding import fake_observer
from funding import funding_helpers as h
from edge_os_api.funding import service
from edge_os_api.funding.types import ObservationStatus


def _setup(funding_engine, funding_factory, owner, *, reference: str = "ref-1"):
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        h.prepare(session, owner, reference=reference, raw="500000000", decimals=6)


def _credit_count(engine) -> int:
    with engine.begin() as connection:
        return connection.execute(sql_text("select count(*) from funding_local.funding_credits")).scalar_one()


def _run_driver(pg, owner, reference: str, event_id: str, scenario: str) -> dict:
    process = h.start_driver(pg.url, str(owner), "agent-a", "wallet-a", h.NETWORK, reference, event_id,
                             "499000000", 6, h.TRADING_ASSET, scenario)
    out, err = process.communicate(timeout=90)
    assert process.returncode == 0, err
    return json.loads(out.strip().splitlines()[-1])


def test_concurrent_reconcile_credits_once(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner)
    observed = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1",
                                         status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET,
                                         raw="499000000", decimals=6, event_id="0xconcurrent")
    barrier, errors = threading.Barrier(2), []

    def run() -> None:
        try:
            barrier.wait()
            with funding_factory() as session:
                service.reconcile_funding(session, h.principal(owner), agent_id="agent-a",
                                          observer=fake_observer.AuthoredFakeDepositObserver([observed]))
        except Exception as error:  # noqa: BLE001 - the control asserts no error either way
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert _credit_count(funding_engine) == 1


def test_crash_during_observe_then_restart_credits_once(funding_engine, funding_factory, pg):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner, reference="ref-crash")
    process = h.start_driver(pg.url, str(owner), "agent-a", "wallet-a", h.NETWORK, "ref-crash", "0xcrash",
                             "499000000", 6, h.TRADING_ASSET, "crash_during_observe")
    assert process.wait(timeout=90) == 9
    assert _credit_count(funding_engine) == 0
    assert _run_driver(pg, owner, "ref-crash", "0xcrash", "reconcile")["credits"] == 1
    assert _run_driver(pg, owner, "ref-crash", "0xcrash", "reconcile")["credits"] == 0
    assert _credit_count(funding_engine) == 1


def test_crash_after_credit_then_restart_credits_once(funding_engine, funding_factory, pg):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner, reference="ref-loss")
    process = h.start_driver(pg.url, str(owner), "agent-a", "wallet-a", h.NETWORK, "ref-loss", "0xloss",
                             "499000000", 6, h.TRADING_ASSET, "crash_after_credit")
    assert process.wait(timeout=90) == 10
    assert _credit_count(funding_engine) == 1
    assert _run_driver(pg, owner, "ref-loss", "0xloss", "reconcile")["credits"] == 0
    assert _credit_count(funding_engine) == 1
