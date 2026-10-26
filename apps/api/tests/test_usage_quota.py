"""#58 Stage 2 shared owner/global quotas: distinct processes, exhaustion, owners, settlement, crash and cap changes.

The GLOBAL scope of each test uses its own key, so caps here never touch the application's global allocation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.core.research import released_runtime_bootstrap
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.usage import quota

DRIVER = Path(__file__).resolve().parent / "usage_driver.py"


def recorded_app(values):
    """A recorded-source app: a composed ACTUAL release would replace the recorded test sources."""
    with mock.patch.dict(released_runtime_bootstrap.RELEASE_DEFINITIONS, {}, clear=True):
        return create_app(load_settings(values))


@pytest.fixture(scope="module")
def factory(settings):
    engine = make_engine(settings.database_url, 30_000)
    yield make_session_factory(engine)
    engine.dispose()


def caps(owner_cap=4, global_cap=1000, key=None, compute=1000):
    return quota.Caps(owner={"provider_requests": owner_cap, "compute_seconds": compute},
                      global_={"provider_requests": global_cap, "compute_seconds": 100000},
                      global_key=key or uuid.uuid4())


def processes(settings, mode, owners, key, amount, owner_cap, global_cap):
    """Start one process per owner at once and return their parsed outputs (or exit codes)."""
    started = [subprocess.Popen([sys.executable, str(DRIVER), mode, settings.database_url, str(owner), str(key),
                                 f"subject-{uuid.uuid4()}", str(amount), "1", str(owner_cap), str(global_cap)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for owner in owners]
    results = []
    for process in started:
        out, err = process.communicate(timeout=120)
        results.append(json.loads(out) if process.returncode == 0 else {"exit": process.returncode, "err": err[-300:]})
    return results


def allocation(factory, scope, owner_key, resource="provider_requests"):
    with factory() as session:
        return session.execute(select(quota.AllocationRow).where(
            quota.AllocationRow.scope == scope, quota.AllocationRow.owner_key == owner_key,
            quota.AllocationRow.resource == resource)).scalar_one_or_none()


def test_last_owner_slot_goes_to_exactly_one_of_many_processes(settings, factory):
    owner, key = uuid.uuid4(), uuid.uuid4()
    with factory() as session:
        assert isinstance(quota.reserve(session, owner, "test_subject", str(uuid.uuid4()),
                                        {"provider_requests": 2, "compute_seconds": 1}, caps(4, 1000, key)), quota.Grant)
        session.commit()
    results = processes(settings, "reserve", [owner] * 6, key, 2, 4, 1000)
    assert sorted(item.get("granted") for item in results) == [False] * 5 + [True], results
    assert {item.get("scope") for item in results if not item.get("granted")} == {"OWNER"}
    row = allocation(factory, "OWNER", owner)
    assert row.reserved == 4 and row.cap == 4


def test_global_exhaustion_refuses_other_owners_without_touching_their_allocation(settings, factory):
    key = uuid.uuid4()
    owners = [uuid.uuid4() for _ in range(4)]
    results = processes(settings, "reserve", owners, key, 2, 10, 3)
    assert sorted(item.get("granted") for item in results) == [False, False, False, True], results
    assert {item.get("scope") for item in results if not item.get("granted")} == {"GLOBAL"}
    reserved = sorted((allocation(factory, "OWNER", owner).reserved
                       if allocation(factory, "OWNER", owner) else 0) for owner in owners)
    assert reserved == [0, 0, 0, 2]
    assert allocation(factory, "GLOBAL", key).reserved == 2


def test_one_owners_exhaustion_does_not_consume_another_owner(factory):
    key, owner_a, owner_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    limits = caps(2, 100, key)
    with factory() as session:
        assert isinstance(quota.reserve(session, owner_a, "test_subject", "a1",
                                        {"provider_requests": 2, "compute_seconds": 1}, limits), quota.Grant)
        assert isinstance(quota.reserve(session, owner_a, "test_subject", "a2",
                                        {"provider_requests": 1, "compute_seconds": 1}, limits), quota.Refusal)
        assert isinstance(quota.reserve(session, owner_b, "test_subject", "b1",
                                        {"provider_requests": 2, "compute_seconds": 1}, limits), quota.Grant)
        session.commit()
        view_b = quota.view(session, owner_b, limits)
    assert view_b["reserved"]["provider_requests"] == 2 and view_b["available"]["provider_requests"] == 0
    assert view_b["global_available"]["provider_requests"] == 96


def test_duplicate_subject_and_duplicate_settlement_change_nothing(factory):
    key, owner = uuid.uuid4(), uuid.uuid4()
    limits = caps(10, 100, key)
    with factory() as session:
        grant = quota.reserve(session, owner, "test_subject", "dup", {"provider_requests": 3, "compute_seconds": 5},
                              limits)
        again = quota.reserve(session, owner, "test_subject", "dup", {"provider_requests": 3, "compute_seconds": 5},
                              limits)
        assert again.replayed and again.reservation.reservation_id == grant.reservation.reservation_id
        first = quota.settle(session, grant.reservation, "provider_requests", "KNOWN", 5, limits)
        second = quota.settle(session, grant.reservation, "provider_requests", "KNOWN", 5, limits)
        session.commit()
    assert first == {"consumed": 5, "unknown": 0, "released": 0, "overrun": 2} and second is None
    row = allocation(factory, "OWNER", owner)
    assert (row.reserved, row.consumed, row.overrun) == (0, 5, 2)


def test_failed_settlement_commit_keeps_the_reservation_open_and_settles_once_later(factory):
    key, owner = uuid.uuid4(), uuid.uuid4()
    limits = caps(10, 100, key)
    with factory() as session:
        grant = quota.reserve(session, owner, "test_subject", "rollback",
                              {"provider_requests": 3, "compute_seconds": 5}, limits)
        session.commit()
        quota.settle(session, grant.reservation, "provider_requests", "KNOWN", 1, limits)
        session.rollback()  # the settlement transaction failed to commit
    row = allocation(factory, "OWNER", owner)
    assert (row.reserved, row.consumed) == (3, 0)
    with factory() as session:
        reservation = quota.existing(session, "test_subject", "rollback")
        assert reservation.settled == {}
        assert quota.settle(session, reservation, "provider_requests", "UNKNOWN", 0, limits) is not None
        session.commit()
    row = allocation(factory, "OWNER", owner)
    assert (row.reserved, row.consumed, row.unknown) == (0, 0, 3)


def test_a_process_killed_before_commit_reserves_nothing(settings, factory):
    key, owner = uuid.uuid4(), uuid.uuid4()
    results = processes(settings, "reserve-die", [owner], key, 2, 4, 100)
    assert results == [{"exit": 9, "err": ""}] or results[0].get("exit") == 9
    row = allocation(factory, "OWNER", owner)
    assert row is None or row.reserved == 0
    assert processes(settings, "reserve", [owner], key, 4, 4, 100)[0]["granted"] is True


def test_caps_are_frozen_and_change_only_by_an_explicit_recorded_operator_action(factory):
    key, owner = uuid.uuid4(), uuid.uuid4()
    with factory() as session:
        quota.reserve(session, owner, "test_subject", "freeze", {"provider_requests": 1, "compute_seconds": 1},
                      caps(2, 100, key))
        session.commit()
    with factory() as session, pytest.raises(quota.CapMismatch):
        quota.reserve(session, owner, "test_subject", "raise", {"provider_requests": 1, "compute_seconds": 1},
                      caps(50, 100, key))
    with factory() as session:
        row = allocation(factory, "OWNER", owner)
        assert not quota._mismatched(row, 2) and quota._mismatched(row, 50)
        assert any(item["scope"] == "OWNER" and item["resource"] == "provider_requests"
                   for item in quota.cap_mismatches(session, caps(50, 100, key)))
        quota.set_cap(session, "OWNER", owner, "provider_requests", 50, "support ticket 1")
        session.commit()
        assert isinstance(quota.reserve(session, owner, "test_subject", "raised",
                                        {"provider_requests": 10, "compute_seconds": 1}, caps(50, 100, key)), quota.Grant)
        session.commit()
        changes = session.execute(select(quota.UsageEventRow).where(quota.UsageEventRow.kind == "CAP_CHANGED",
                                                                    quota.UsageEventRow.owner_id == owner)).scalars().all()
    assert [item.content["to"] for item in changes] == [50] and changes[0].content["reason"] == "support ticket 1"
    with factory() as session, pytest.raises(ValueError):
        quota.set_cap(session, "OWNER", owner, "provider_requests", 60, " ")


def test_a_changed_configured_global_cap_pauses_research_and_shows_in_readiness(env, migrated, owner_a):
    from research_flows import declare, start

    with TestClient(recorded_app({**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"})) as client:
        intake_id, declaration_id, _ = declare(client, owner_a)
        assert start(client, owner_a, intake_id, declaration_id).status_code == 201  # freezes the global caps
        assert client.get("/readyz").json()["status"] == "ready"
    changed = {**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded", "EDGE_OS_USAGE_GLOBAL_PROVIDER_REQUESTS": "999999"}
    with TestClient(recorded_app(changed)) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 503 and ready.json() == {"status": "unavailable", "reason": "quota_cap_mismatch",
                                                             "resources": ["provider_requests"]}
        refused = start(client, owner_a, intake_id, declaration_id)
        assert refused.status_code == 503 and refused.json()["code"] == "quota_cap_mismatch"


def test_a_reservation_taken_before_a_cap_change_still_settles_and_operator_caps_are_authoritative(factory):
    """Review A B1: settlement never compares caps; an operator-recorded OWNER cap is not a mismatch."""
    key, owner = uuid.uuid4(), uuid.uuid4()
    amounts = {"provider_requests": 2, "compute_seconds": 5}
    with factory() as session:
        grant = quota.reserve(session, owner, "test_subject", "before-change", amounts, caps(4, 100, key))
        session.commit()
        reservation_id = grant.reservation.reservation_id
    changed = caps(9, 100, key)  # configuration changed after the reservation
    with factory() as session:
        reservation = session.get(quota.ReservationRow, reservation_id)
        assert quota.settle(session, reservation, "provider_requests", "KNOWN", 1, changed)["released"] == 1
        assert quota.settle(session, reservation, "compute_seconds", "UNKNOWN", 0, changed)["unknown"] == 5
        session.commit()
    row = allocation(factory, "OWNER", owner)
    assert (row.reserved, row.consumed, row.cap) == (0, 1, 4)  # settled; the frozen cap did not move
    with factory() as session:
        assert any(item["scope"] == "OWNER" for item in quota.cap_mismatches(session, changed))
        with pytest.raises(quota.CapMismatch):
            quota.reserve(session, owner, "test_subject", "after-change", amounts, changed)
        session.rollback()
        quota.set_cap(session, "OWNER", owner, "provider_requests", 6, "operator override differs from config")
        session.commit()
        # The operator value (6) differs from configuration (9) and is authoritative: no mismatch, reservations work.
        assert not quota._mismatched(allocation(factory, "OWNER", owner), changed.owner["provider_requests"])
        granted = quota.reserve(session, owner, "test_subject", "after-override",
                                {"provider_requests": 2, "compute_seconds": 0}, caps(9, 100, key, compute=1000))
        assert isinstance(granted, quota.Grant)
        session.rollback()


def test_an_owner_cap_mismatch_keeps_readiness_and_other_owners_but_pauses_that_owners_starts(env, migrated,
                                                                                               owner_a, owner_b):
    from research_flows import declare, start

    base = {**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"}
    with TestClient(recorded_app(base)) as client:
        intake_id, declaration_id, _ = declare(client, owner_a)
        assert start(client, owner_a, intake_id, declaration_id).status_code == 201  # freezes owner A's caps
    changed = {**base, "EDGE_OS_RESEARCH_BUDGET_PROVIDER_REQUESTS": "15"}
    with TestClient(recorded_app(changed)) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 200 and ready.json()["attention"]["owner_quota_cap_mismatch"]["provider_requests"] >= 1
        assert "owner" not in json.dumps(ready.json()["attention"]).replace("owner_quota_cap_mismatch", "")
        refused = start(client, owner_a, intake_id, declaration_id)
        assert refused.status_code == 503 and refused.json()["code"] == "quota_cap_mismatch"
        other_intake, other_declaration, _ = declare(client, owner_b)
        assert start(client, owner_b, other_intake, other_declaration).status_code == 201  # new owner: no mismatch
