"""Funding preparation, persistence and owner-scoped read against real PostgreSQL."""

from __future__ import annotations

import uuid

import pytest

from edge_os_api.core.errors import AppError
from edge_os_api.funding import service
from edge_os_api.funding.types import FlowKind, FlowState

from funding import funding_helpers as h


def test_prepare_persists_exact_review(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        flow = h.prepare(session, owner, raw="500000000", decimals=6, recipient="wallet-a",
                         declared_fee_asset_id=h.TRADING_ASSET, declared_fee_raw="1000", declared_fee_decimals=6)
    assert flow.state is FlowState.PENDING
    assert flow.asset.asset_id == h.TRADING_ASSET
    assert flow.asset.raw == "500000000" and flow.asset.decimals == 6
    assert flow.kind is FlowKind.DEPOSIT
    assert flow.sender is None
    assert flow.recipient == "wallet-a"
    assert flow.declared_fee is not None and flow.declared_fee.raw == "1000"
    assert flow.declared_fee.asset_id == h.TRADING_ASSET
    assert flow.transaction_reference is None
    assert flow.reason is None


def test_read_back_survives_a_fresh_session(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        flow = h.prepare(session, owner)
    with funding_factory() as session:
        read = service.get_funding(session, h.principal(owner), agent_id="agent-a", flow_id=str(flow.flow_id))
        listed = service.list_funding(session, h.principal(owner), agent_id="agent-a")
    assert read.flow_id == flow.flow_id
    assert read.asset.raw == flow.asset.raw
    assert [item.flow_id for item in listed] == [flow.flow_id]


def test_prepare_is_idempotent_for_the_same_identity(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        first = h.prepare(session, owner, reference="ref-1")
        second = h.prepare(session, owner, reference="ref-1")
    assert first.flow_id == second.flow_id


def test_changed_flow_identity_is_denied(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        h.prepare(session, owner, reference="ref-1", raw="500000000")
        with pytest.raises(AppError) as error:
            h.prepare(session, owner, reference="ref-1", raw="600000000")
    assert error.value.status == 409


def test_missing_binding_is_a_404(funding_engine, funding_factory):
    owner = uuid.uuid4()
    with funding_factory() as session:
        with pytest.raises(AppError) as error:
            h.declare(session, owner)
    assert error.value.status == 404


def test_unconfirmed_binding_is_a_404(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    from sqlalchemy import text as sql_text
    with funding_engine.begin() as connection:
        connection.execute(sql_text("update public.wallet_setups set state = 'PENDING' where owner_id = :owner"),
                           {"owner": owner})
    with funding_factory() as session:
        with pytest.raises(AppError) as error:
            h.declare(session, owner)
    assert error.value.status == 404


def test_prepare_requires_a_declaration(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        with pytest.raises(AppError) as error:
            h.prepare(session, owner)
    assert error.value.status == 404


def test_unsupported_asset_is_denied(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        with pytest.raises(AppError) as error:
            h.prepare(session, owner, asset_id="monad:143/asset:OTHER", raw="1", decimals=6)
    assert error.value.status == 409


def test_withdrawal_is_unsupported_here(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        with pytest.raises(AppError) as error:
            h.prepare(session, owner, kind=FlowKind.WITHDRAWAL)
    assert error.value.status == 409


def test_declared_decimals_must_match(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        with pytest.raises(AppError) as error:
            h.prepare(session, owner, decimals=18)
    assert error.value.status == 409


def test_native_gas_asset_is_accepted_and_separate(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        flow = h.prepare(session, owner, asset_id=h.GAS_ASSET, raw="1000000000000000000", decimals=18,
                         reference="gas-ref")
    assert flow.asset.asset_id == h.GAS_ASSET
    assert flow.asset.asset_id != h.TRADING_ASSET


def test_cross_owner_prepare_is_a_404(funding_engine, funding_factory):
    owner, other = uuid.uuid4(), uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        with pytest.raises(AppError) as error:
            h.prepare(session, other)
    assert error.value.status == 404


def test_malformed_raw_and_decimals_are_rejected(funding_engine, funding_factory):
    owner = uuid.uuid4()
    h.seed_confirmed_binding(funding_engine, owner)
    with funding_factory() as session:
        h.declare(session, owner)
        for raw, decimals in (("00", 6), ("-1", 6), ("1.0", 6), ("5", -1), ("5", 256), ("5", "6")):
            with pytest.raises(AppError) as error:
                h.prepare(session, owner, raw=raw, decimals=decimals, reference=f"bad-{raw}-{decimals}")
            assert error.value.status == 422
