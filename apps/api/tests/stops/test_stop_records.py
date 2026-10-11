"""Durable scoped-stop record requests, owner scope and direct row inspection."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from edge_os_api.stops.types import StopRequest

from admission._builders import AGENT_A, AGENT_B, NETWORK, WALLET_A, WALLET_B
from stops._support import stop_request


def test_request_and_retrieve_stop_is_owner_scoped(stop_service, stops_engine, fresh_owner) -> None:
    view = stop_service.request_stop(fresh_owner, stop_request(position_id="position-a-1"))

    assert view.owner_id == fresh_owner
    assert view.agent_id == AGENT_A and view.wallet_id == WALLET_A and view.network_id == NETWORK
    assert view.scope == "POSITION" and view.mode == "STOP_NEW_ENTRIES"
    assert view.trigger == "USER" and view.position_id == "position-a-1"

    another_owner = uuid.uuid4()
    assert stop_service.retrieve_stops(another_owner) == []
    mine = stop_service.retrieve_stops(fresh_owner)
    assert [item.stop_id for item in mine] == [view.stop_id]

    with stops_engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT agent_id, wallet_id, network_id, scope, mode, trigger, position_id "
            "FROM stops_local.scoped_stops WHERE owner_id = :owner"), {"owner": str(fresh_owner)}).all()
    assert rows == [(AGENT_A, WALLET_A, NETWORK, "POSITION", "STOP_NEW_ENTRIES", "USER", "position-a-1")]


def test_identical_stop_request_is_idempotent_and_history_accumulates(stop_service, fresh_owner) -> None:
    first = stop_service.request_stop(fresh_owner, stop_request(position_id="position-a-1"))
    repeated = stop_service.request_stop(fresh_owner, stop_request(position_id="position-a-1"))

    assert repeated.stop_id == first.stop_id
    assert len(stop_service.retrieve_stops(fresh_owner)) == 1

    other_mode = stop_service.request_stop(
        fresh_owner, stop_request(mode="HALT_ALL_SWAPS", position_id="position-a-1"))
    assert other_mode.stop_id != first.stop_id
    assert {item.mode for item in stop_service.retrieve_stops(fresh_owner)} == {
        "STOP_NEW_ENTRIES", "HALT_ALL_SWAPS"}


def test_agent_wallet_stop_leaves_other_wallet_unchanged(stop_service, fresh_owner) -> None:
    stop_service.request_stop(
        fresh_owner, stop_request(scope="AGENT_WALLET_NETWORK", agent_id=AGENT_A, wallet_id=WALLET_A))

    wallet_a = stop_service.retrieve_stops(fresh_owner, wallet_id=WALLET_A, network_id=NETWORK)
    wallet_b = stop_service.retrieve_stops(fresh_owner, wallet_id=WALLET_B, network_id=NETWORK)
    assert len(wallet_a) == 1 and wallet_a[0].position_id is None
    assert wallet_b == []


def test_retrieval_position_filter_includes_covering_wallet_stop(stop_service, fresh_owner) -> None:
    stop_service.request_stop(fresh_owner, stop_request(position_id="position-a-1"))
    stop_service.request_stop(fresh_owner, stop_request(scope="AGENT_WALLET_NETWORK", position_id=None))
    stop_service.request_stop(fresh_owner, stop_request(position_id="position-a-2"))

    covering = stop_service.retrieve_stops(fresh_owner, position_id="position-a-1")
    assert {item.position_id for item in covering} == {"position-a-1", None}


def test_scope_and_trigger_validation_refuses_unmapped_scopes() -> None:
    with pytest.raises(ValidationError):
        StopRequest(trigger="USER", mode="STOP_NEW_ENTRIES", scope="POSITION",
                    agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    with pytest.raises(ValidationError):
        StopRequest(trigger="USER", mode="STOP_NEW_ENTRIES", scope="AGENT_WALLET_NETWORK",
                    agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, position_id="position-a-1")
    # A wider deployment or all-agent scope is refused explicitly, not widened silently.
    with pytest.raises(ValidationError):
        StopRequest(trigger="USER", mode="HALT_ALL_SWAPS", scope="DEPLOYMENT",
                    agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    with pytest.raises(ValidationError):
        StopRequest(trigger="UNKNOWN", mode="STOP_NEW_ENTRIES", scope="AGENT_WALLET_NETWORK",
                    agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
