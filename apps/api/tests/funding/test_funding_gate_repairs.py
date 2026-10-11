"""Gate-repair controls: asset-network binding, class distinctness, foreign-owner replay and fee identity.

These controls reproduce the three blockers from the first independent gate review on candidate
66e468e and prove each repair against real PostgreSQL with the authored fake observer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text as sql_text

import pytest

from edge_os_api.core.errors import AppError
from edge_os_api.funding import service
from edge_os_api.funding.types import FlowState, ObservationStatus

from funding import fake_observer
from funding import funding_helpers as h

TESTNET_TRADING = "monad-testnet:10143/asset:USDC"


def _setup(funding_engine, funding_factory, owner, *, agent_id="agent-a", wallet_id="wallet-a", reference="ref-1"):
    h.seed_confirmed_binding(funding_engine, owner, agent_id=agent_id, wallet_id=wallet_id)
    with funding_factory() as session:
        h.declare(session, owner, agent_id=agent_id)
        h.prepare(session, owner, agent_id=agent_id, reference=reference, raw="500000000", decimals=6,
                  recipient=wallet_id)


def _reconcile(funding_factory, owner, observer, agent_id="agent-a"):
    with funding_factory() as session:
        return service.reconcile_funding(session, h.principal(owner), agent_id=agent_id, observer=observer)


def _denials(funding_engine, code):
    with funding_engine.begin() as connection:
        return connection.execute(sql_text("select count(*) from funding_local.funding_denials where code = :code"),
                                  {"code": code}).scalar_one()


def test_declared_asset_must_belong_to_the_network(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        with pytest.raises(AppError) as error:
            h.declare(session, owner, trading_asset_id=TESTNET_TRADING)
    assert error.value.status == 422


def test_gas_and_trading_assets_must_be_distinct(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        with pytest.raises(AppError) as error:
            h.declare(session, owner, trading_asset_id=h.GAS_ASSET)
    assert error.value.status == 422


def test_wrong_network_observation_asset_never_credits(funding_engine, funding_factory):
    owner = uuid.uuid4()
    _setup(funding_engine, funding_factory, owner)
    observed = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1",
                                         status=ObservationStatus.CONFIRMED, asset_id=TESTNET_TRADING, raw="71000000",
                                         decimals=6, event_id="0xwrongnet")
    results = _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([observed]))
    assert all(result.credits == [] for result in results)
    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "0"
    assert _denials(funding_engine, "WRONG_NETWORK") == 1
    with funding_engine.begin() as connection:
        visible = connection.execute(sql_text(
            "select count(*) from funding_local.funding_observations where reason = 'WRONG_NETWORK'")).scalar_one()
    assert visible == 1


def test_one_declared_asset_cannot_appear_in_two_classes(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        with pytest.raises(AppError):
            h.declare(session, owner, trading_asset_id=h.GAS_ASSET, gas_asset_id=h.GAS_ASSET)
        with pytest.raises(AppError):
            h.declare(session, owner, compute_asset_id=h.TRADING_ASSET, compute_decimals=6)


def test_foreign_owner_replay_does_not_confirm_or_credit(funding_engine, funding_factory):
    owner_a, owner_c = uuid.uuid4(), uuid.uuid4()
    _setup(funding_engine, funding_factory, owner_a, agent_id="agent-a", wallet_id="wallet-a")
    _setup(funding_engine, funding_factory, owner_c, agent_id="agent-c", wallet_id="wallet-a")
    observed = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-1",
                                         status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET, raw="499000000",
                                         decimals=6, event_id="0xforeign")
    first = _reconcile(funding_factory, owner_a, fake_observer.AuthoredFakeDepositObserver([observed]), agent_id="agent-a")
    assert first[0].credits and first[0].flow.state is FlowState.CONFIRMED
    second = _reconcile(funding_factory, owner_c, fake_observer.AuthoredFakeDepositObserver([observed]), agent_id="agent-c")
    assert all(result.credits == [] for result in second)
    assert second[0].flow.state is not FlowState.CONFIRMED
    with funding_factory() as session:
        c_available = service.available_credit(session, h.principal(owner_c), agent_id="agent-c",
                                               asset_id=h.TRADING_ASSET)
    assert c_available.raw == "0"
    assert _denials(funding_engine, "WRONG_OWNER") == 1
    with funding_engine.begin() as connection:
        credits = connection.execute(sql_text("select count(*) from funding_local.funding_credits")).scalar_one()
    assert credits == 1


def test_declared_fee_keeps_its_own_asset_identity(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        flow = h.prepare(session, owner, reference="ref-fee", raw="500000000", decimals=6,
                         declared_fee_asset_id=h.GAS_ASSET, declared_fee_raw="2000000000000000",
                         declared_fee_decimals=18)
    assert flow.declared_fee is not None and flow.declared_fee.asset_id == h.GAS_ASSET
    observed = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-fee",
                                         status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET, raw="499000000",
                                         decimals=6, event_id="0xfee", fee_asset_id=h.GAS_ASSET,
                                         fee_raw="2000000000000000", fee_decimals=18)
    results = _reconcile(funding_factory, owner, fake_observer.AuthoredFakeDepositObserver([observed]))
    credit = results[0].credits[0]
    assert credit.fee is not None and credit.fee.asset_id == h.GAS_ASSET and credit.fee.decimals == 18


def test_fee_without_asset_identity_or_wrong_decimals_stays_unknown(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        h.prepare(session, owner, reference="ref-fee-none", raw="500000000", decimals=6)
        h.prepare(session, owner, reference="ref-fee-bad", raw="500000000", decimals=6)
    no_asset = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-fee-none",
                                         status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET, raw="499000000",
                                         decimals=6, event_id="0xfee-none", fee_raw="1000000", fee_decimals=6)
    wrong_decimals = fake_observer.observation(wallet_id="wallet-a", network_id=h.NETWORK, reference="ref-fee-bad",
                                               status=ObservationStatus.CONFIRMED, asset_id=h.TRADING_ASSET,
                                               raw="499000000", decimals=6, event_id="0xfee-bad",
                                               fee_asset_id=h.GAS_ASSET, fee_raw="1000000", fee_decimals=6)
    results = _reconcile(funding_factory, owner,
                         fake_observer.AuthoredFakeDepositObserver([no_asset, wrong_decimals]))
    assert all(credit.fee is None for result in results for credit in result.credits)
    with funding_factory() as session:
        available = service.available_credit(session, h.principal(owner), agent_id="agent-a",
                                             asset_id=h.TRADING_ASSET)
    assert available.raw == "998000000"


def test_declared_fee_requires_an_asset_identity(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        with pytest.raises(AppError) as error:
            h.prepare(session, owner, declared_fee_raw="1000000", declared_fee_decimals=6)
    assert error.value.status == 422
