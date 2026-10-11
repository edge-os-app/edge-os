"""The controlled observation boundary and exact once-only credit against real PostgreSQL."""

from __future__ import annotations

import uuid

from sqlalchemy import text as sql_text

from edge_os_api.funding import service
from edge_os_api.funding.types import FlowState, ObservationStatus

from funding import fake_observer
from funding import funding_helpers as h


def _setup(funding_engine, funding_factory, owner, *, agent_id="agent-a", wallet_id="wallet-a", reference="ref-1",
           raw="500000000", decimals=6):
    h.seed_confirmed_binding(funding_engine, owner, agent_id=agent_id, wallet_id=wallet_id)
    with funding_factory() as session:
        h.declare(session, owner, agent_id=agent_id)
        flow = h.prepare(session, owner, agent_id=agent_id, raw=raw, decimals=decimals, reference=reference,
                         recipient=wallet_id)
    return flow


def _reconcile(funding_factory, owner, observer, agent_id="agent-a"):
    with funding_factory() as session:
        return service.reconcile_funding(session, h.principal(owner), agent_id=agent_id, observer=observer)


def test_confirmed_observation_credits_actual_once(funding_engine, funding_factory):
    owner = uuid.uuid4()
    flow = _setup(funding_engine, funding_factory, owner)
    observer = fake_observer.AuthoredFakeDepositObserver([fake_observer.observation(
        wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1", status=ObservationStatus.CONFIRMED,
        asset_id=h.TRADING_ASSET, raw="499000000", decimals=6, event_id="0xevent-1", fee_raw="1000000",
        fee_decimals=6)])
    results = _reconcile(funding_factory, owner, observer)
    assert len(results) == 1
    assert results[0].flow.state is FlowState.CONFIRMED
    assert len(results[0].credits) == 1
    assert results[0].credits[0].amount.raw == "499000000"
    assert results[0].credits[0].event_id == "0xevent-1"
    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "499000000"
    assert available.decimals == 6


def test_pending_failed_and_unknown_are_unavailable(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner)
    for status in (ObservationStatus.PENDING, ObservationStatus.FAILED, ObservationStatus.UNKNOWN):
        observer = fake_observer.AuthoredFakeDepositObserver([fake_observer.observation(
            wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1", status=status,
            asset_id=h.TRADING_ASSET, raw="499000000", decimals=6, event_id="0xevent-1")])
        results = _reconcile(funding_factory, owner, observer)
        assert results[0].flow.state.value == status.value
        assert results[0].credits == []
    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "0"


def test_replayed_event_cannot_credit_twice(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner)
    observed = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1",
                                         status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET,
                                         raw="499000000", decimals=6, event_id="0xevent-1")
    for _ in range(3):
        _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([observed]))
    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "499000000"
    with funding_engine.begin() as connection:
        credits = connection.execute(sql_text("select count(*) from funding_local.funding_credits")).scalar_one()
        duplicates = connection.execute(sql_text(
            "select count(*) from funding_local.funding_observations where status = 'DUPLICATE'")).scalar_one()
    assert credits == 1
    assert duplicates == 2


def test_conflicting_terminal_evidence_fails_closed(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner)
    first = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1",
                                      status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET, raw="499000000",
                                      decimals=6, event_id="0xevent-1")
    _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([first]))
    conflict = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1",
                                         status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET, raw="999999999",
                                         decimals=6, event_id="0xevent-1")
    results = _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([conflict]))
    assert results[0].credits == []
    assert any(reason == "CONFLICTING_TERMINAL_EVIDENCE" for reason in results[0].denials)
    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "499000000"
    with funding_engine.begin() as connection:
        denials = connection.execute(sql_text(
            "select count(*) from funding_local.funding_denials where code = 'CONFLICTING_TERMINAL_EVIDENCE'"
        )).scalar_one()
    assert denials == 1


def test_wrong_wallet_and_wrong_network_never_credit(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner)
    wrong_wallet = fake_observer.observation(wallet_id="wallet-other", network_id=h.NETWORK, reference="ref-1",
                                             status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET,
                                             raw="499000000", decimals=6, event_id="0xe1")
    wrong_network = fake_observer.observation(wallet_id="wallet-a", network_id=10143, reference="ref-1",
                                              status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET,
                                              raw="499000000", decimals=6, event_id="0xe2")
    _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([wrong_wallet, wrong_network]))
    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "0"


def test_unsupported_and_orphan_observations_stay_unavailable(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner)
    unsupported = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1",
                                            status=ObservationStatus.CONFIRMED, asset_id="monad:143/asset:OTHER",
                                            raw="5", decimals=6, event_id="0xu")
    orphan = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="no-such-ref",
                                       status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET, raw="5",
                                       decimals=6, event_id="0xo")
    results = _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([unsupported, orphan]))
    assert all(result.credits == [] for result in results)
    with funding_engine.begin() as connection:
        unsupported_denials = connection.execute(sql_text(
            "select count(*) from funding_local.funding_denials where code = 'UNSUPPORTED_ASSET'")).scalar_one()
        orphan_denials = connection.execute(sql_text(
            "select count(*) from funding_local.funding_denials where code = 'NO_MATCHING_FLOW'")).scalar_one()
    assert unsupported_denials == 1
    assert orphan_denials == 1


def test_no_cross_wallet_or_cross_asset_pooling(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner, agent_id="agent-a", wallet_id="wallet-a")
    _setup(funding_engine, funding_factory, owner, agent_id="agent-b", wallet_id="wallet-b")
    observer = fake_observer.AuthoredFakeDepositObserver([fake_observer.observation(
        wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1", status=ObservationStatus.CONFIRMED,
        asset_id=h.TRADING_ASSET, raw="499000000", decimals=6, event_id="0xa")])
    _reconcile(funding_factory, owner, observer, agent_id="agent-a")
    with funding_factory() as session:
        a = service.available_credit(session, h.principal(owner), agent_id="agent-a", asset_id=h.TRADING_ASSET)
        b = service.available_credit(session, h.principal(owner), agent_id="agent-b", asset_id=h.TRADING_ASSET)
        gas = service.available_credit(session, h.principal(owner), agent_id="agent-a", asset_id=h.GAS_ASSET)
    assert a.raw == "499000000"
    assert b.raw == "0"
    assert gas.raw == "0"


def test_observation_history_is_preserved(funding_engine, funding_factory):
    owner = uuid.uuid4()
    flow = _setup(funding_engine, funding_factory, owner)
    _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([fake_observer.observation(
        wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1", status=ObservationStatus.PENDING,
        asset_id=h.TRADING_ASSET, raw="499000000", decimals=6, event_id="0xe1")]))
    _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([fake_observer.observation(
        wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1", status=ObservationStatus.CONFIRMED,
        asset_id=h.TRADING_ASSET, raw="499000000", decimals=6, event_id="0xe1")]))
    with funding_engine.begin() as connection:
        count = connection.execute(sql_text(
            "select count(*) from funding_local.funding_observations where flow_id = :flow_id"),
            {"flow_id": flow.flow_id}).scalar_one()
    assert count == 2


def test_unavailable_observer_credits_nothing(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner)
    results = _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver(unavailable=True))
    assert results == []
    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "0"
    with funding_engine.begin() as connection:
        denials = connection.execute(sql_text(
            "select count(*) from funding_local.funding_denials where code = 'OBSERVATION_UNAVAILABLE'"
        )).scalar_one()
    assert denials == 1
