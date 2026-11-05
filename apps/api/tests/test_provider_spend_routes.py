"""One spend ledger for every route: shared caps, a frozen price per route, settlement at the reservation's own route.

Seam: `PostgresSpendLedger` over a real migrated database, and the Alembic revisions on that database. TEST prices:
route A costs 2.00 and 7.50 USD per million tokens and route B exactly twice that, so a reservation for 12,064 input and
4,096 output tokens holds 0.054848 on A and 0.109696 on B. 1,423 input and 611 output tokens charge 0.0074285 on A
and 0.014857 on B.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_provider_spend_ledger import (  # noqa: F401 - fixtures
    BOUNDS, PRICE, RESERVATION, attempts, clean_spend, empty_spend_ledger, factory, limits,
)

from edge_os_api.research.provider_spend_ledger import PostgresSpendLedger, spend_view

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "hermes_interpretation"))
from spend_ledger import CapExceeded, LedgerConfigMismatch, ScopeBlocked, TokenPrice  # noqa: E402

ROUTE_A, ROUTE_B = "route-a", "route-b"
PRICE_B = TokenPrice(Decimal("4.00"), Decimal("15.00"))
RESERVATION_B = Decimal("0.109696")
USAGE = {"input_tokens": 1_423, "output_tokens": 611}
CHARGE_A, CHARGE_B = Decimal("0.0074285"), Decimal("0.014857")
OPENROUTER = "openrouter-openai-standard"
EVENT_ROWS = "SELECT seq, attempt_id, kind, nano_usd FROM usage_local.provider_spend_events ORDER BY seq"
EVENT_CHANGES = ("UPDATE usage_local.provider_spend_events SET nano_usd = 0",
                 "DELETE FROM usage_local.provider_spend_events")


def on_a(session_factory, **caps: str) -> PostgresSpendLedger:
    return PostgresSpendLedger(session_factory, limits(**caps), route_id=ROUTE_A)


def on_b(session_factory, **caps: str) -> PostgresSpendLedger:
    return PostgresSpendLedger(session_factory, limits(price=PRICE_B, **caps), route_id=ROUTE_B)


def values(session_factory, statement: str) -> list[tuple]:
    with session_factory() as session:
        return [tuple(row) for row in session.execute(text(statement)).all()]


def test_a_mixed_route_run_reaches_the_one_shared_global_cap(clean_spend, attempts, owner_a, owner_b) -> None:
    a, b = on_a(clean_spend, global_cap="0.17", owner_cap="0.17"), on_b(clean_spend, global_cap="0.17", owner_cap="0.17")
    first, second, third = attempts.new(owner_a), attempts.new(owner_b), attempts.new(owner_b)

    assert a.reserve(first, scope="s1", **BOUNDS).amount_usd == RESERVATION
    assert b.reserve(second, scope="s2", **BOUNDS).amount_usd == RESERVATION_B
    with pytest.raises(CapExceeded):  # 0.164544 is held across both routes, and 0.054848 more is above 0.17
        a.reserve(third, scope="s3", **BOUNDS)

    assert a.committed_usd() == b.committed_usd() == Decimal("0.164544")
    assert a.state(third) is None and a.events(third) == []


def test_one_owner_cap_sees_that_owners_spend_on_every_route(clean_spend, attempts, owner_a, owner_b) -> None:
    a, b = on_a(clean_spend, global_cap="1.00", owner_cap="0.16"), on_b(clean_spend, global_cap="1.00", owner_cap="0.16")
    a.reserve(attempts.new(owner_a), scope="s1", **BOUNDS)
    with pytest.raises(CapExceeded):  # 0.054848 + 0.109696 = 0.164544 is above this owner's 0.16
        b.reserve(attempts.new(owner_a), scope="s2", **BOUNDS)
    assert b.reserve(attempts.new(owner_b), scope="s3", **BOUNDS).amount_usd == RESERVATION_B


def test_the_budget_view_counts_every_route(clean_spend, attempts, owner_a, client) -> None:
    a, b = on_a(clean_spend, global_cap="1.00", owner_cap="1.00"), on_b(clean_spend, global_cap="1.00", owner_cap="1.00")
    settled, held = attempts.new(owner_a), attempts.new(owner_a)
    a.reserve(settled, scope="s1", **BOUNDS)
    a.settle(settled, **USAGE)
    b.reserve(held, scope="s2", **BOUNDS)
    owner = client.get("/v1/me", headers=owner_a).json()["user_id"]
    with clean_spend() as session:
        view = spend_view(session, owner)
    assert (view["settled"], view["held"], view["held_calls"]) == (7_428_500, 109_696_000, 1)
    assert view["available"] == 1_000_000_000 - 7_428_500 - 109_696_000


def test_each_reservation_saves_its_route_as_text(clean_spend, attempts, owner_a) -> None:
    first, second = attempts.new(owner_a), attempts.new(owner_a)
    on_a(clean_spend).reserve(first, scope="s1", **BOUNDS)
    on_b(clean_spend).reserve(second, scope="s2", **BOUNDS)
    assert values(clean_spend, "SELECT attempt_id::text, route_id FROM usage_local.provider_spend_reservations "
                               "ORDER BY route_id") == [(first, ROUTE_A), (second, ROUTE_B)]
    assert values(clean_spend, "SELECT data_type FROM information_schema.columns WHERE table_schema = 'usage_local' "
                               "AND table_name = 'provider_spend_reservations' AND column_name = 'route_id'") == [("text",)]


def test_a_route_price_is_frozen_at_that_routes_first_use_and_a_later_price_is_refused(
        clean_spend, attempts, owner_a) -> None:
    first, refused, other = attempts.new(owner_a), attempts.new(owner_a), attempts.new(owner_a)
    on_a(clean_spend).reserve(first, scope="s1", **BOUNDS)

    changed = PostgresSpendLedger(clean_spend, limits(price=TokenPrice(Decimal("1.00"), Decimal("7.50"))), route_id=ROUTE_A)
    with pytest.raises(LedgerConfigMismatch):
        changed.reserve(refused, scope="s2", **BOUNDS)
    assert changed.state(refused) is None

    assert on_b(clean_spend).reserve(other, scope="s3", **BOUNDS).amount_usd == RESERVATION_B  # its own first use
    assert values(clean_spend, "SELECT route_id, prompt_usd_per_million, completion_usd_per_million "
                               "FROM usage_local.provider_spend_route_prices ORDER BY route_id") == [
        (ROUTE_A, "2.00", "7.50"), (ROUTE_B, "4.00", "15.00")]


def test_a_refused_first_use_freezes_no_price(clean_spend, attempts, owner_a) -> None:
    with pytest.raises(CapExceeded):
        on_b(clean_spend, global_cap="0.01", owner_cap="0.01").reserve(attempts.new(owner_a), scope="s", **BOUNDS)
    assert values(clean_spend, "SELECT route_id FROM usage_local.provider_spend_route_prices") == []


def test_settlement_uses_the_price_of_the_reservations_own_route(clean_spend, attempts, owner_a) -> None:
    on_routes = attempts.new(owner_a), attempts.new(owner_a)
    a, b = on_a(clean_spend), on_b(clean_spend)
    a.reserve(on_routes[0], scope="s1", **BOUNDS)
    b.reserve(on_routes[1], scope="s2", **BOUNDS)

    assert b.settle(on_routes[0], **USAGE).cost_usd == CHARGE_A  # a process now serving the other route
    assert a.settle(on_routes[1], **USAGE).cost_usd == CHARGE_B
    assert a.committed_usd() == CHARGE_A + CHARGE_B


def test_late_evidence_uses_the_price_of_the_reservations_own_route(clean_spend, attempts, owner_a) -> None:
    unknown, settled = attempts.new(owner_a), attempts.new(owner_a)
    a, b = on_a(clean_spend), on_b(clean_spend)
    b.reserve(unknown, scope="s1", **BOUNDS)
    b.mark_unknown(unknown, reason="TransportLost")
    assert a.reconcile(unknown, source="late", **USAGE).cost_usd == CHARGE_B

    b.reserve(settled, scope="s2", **BOUNDS)
    b.settle(settled, **USAGE)
    assert a.reconcile(settled, source="again", **USAGE).cost_usd == CHARGE_B  # the same evidence, not a conflict
    assert [event.kind for event in a.events(settled)] == ["RESERVED", "SETTLED", "DUPLICATE_EVIDENCE"]


def test_an_unknown_call_holds_its_full_reservation_against_every_route(clean_spend, attempts, owner_a) -> None:
    a, b = on_a(clean_spend, global_cap="0.15", owner_cap="0.15"), on_b(clean_spend, global_cap="0.15", owner_cap="0.15")
    held, next_call = attempts.new(owner_a), attempts.new(owner_a)
    a.reserve(held, scope="same-study", **BOUNDS)
    a.mark_unknown(held, reason="TransportLost")

    with pytest.raises(ScopeBlocked):  # one open liability per study, whichever route asks
        b.reserve(next_call, scope="same-study", **BOUNDS)
    with pytest.raises(CapExceeded):  # 0.054848 is still held: 0.109696 more is above 0.15
        b.reserve(next_call, scope="another-study", **BOUNDS)
    assert b.committed_usd() == RESERVATION


def test_a_lowered_output_limit_uses_the_routes_own_price_and_the_shared_headroom(clean_spend, attempts, owner_a) -> None:
    a, b = on_a(clean_spend, global_cap="0.15", owner_cap="0.15"), on_b(clean_spend, global_cap="0.15", owner_cap="0.15")
    a.reserve(attempts.new(owner_a), scope="s1", **BOUNDS)
    # 95,152,000 nano-USD left. Input on B: 48,256,000. Each output token on B: 15,000. (95,152,000 - 48,256,000) // 15,000.
    fitted = b.reserve(attempts.new(owner_a), scope="s2", min_output_tokens=1, **BOUNDS)
    assert fitted.max_output_tokens == 3_126 and fitted.amount_usd == Decimal("0.095146")


def test_two_processes_on_two_routes_never_pass_the_shared_cap_together(clean_spend, attempts, owner_a, owner_b,
                                                                        settings) -> None:
    import json
    import time
    mine = [attempts.new(owner_a) for _ in range(3)] + [attempts.new(owner_b) for _ in range(3)]
    start_at = str(time.time() + 4)
    worker = Path(__file__).with_name("spend_reservation_worker.py")
    processes = [subprocess.Popen([sys.executable, str(worker), settings.database_url, "0.20", "0.20", start_at, route,
                                   *(f"{attempt}:{attempt}" for attempt in half)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for route, half in (("route=route-a", mine[0::2]), ("route=route-b", mine[1::2]))]
    outputs = [process.communicate(timeout=120) for process in processes]

    assert [p.returncode for p in processes] == [0, 0], [err[-800:] for _out, err in outputs]
    results = [item for out, _err in outputs for item in json.loads(out)]
    assert {r["outcome"] for r in results} == {"RESERVED", "CapExceeded"}
    spend = on_a(clean_spend, global_cap="0.20", owner_cap="0.20")
    granted = [row for row in values(clean_spend, "SELECT route_id, reserved_nano_usd FROM "
                                                  "usage_local.provider_spend_reservations")]
    assert len(granted) == sum(r["outcome"] == "RESERVED" for r in results)
    assert {route for route, amount in granted} <= {ROUTE_A, ROUTE_B}
    assert all(amount == (54_848_000 if route == ROUTE_A else 109_696_000) for route, amount in granted)
    assert spend.committed_usd() <= Decimal("0.20")


@pytest.mark.parametrize("given", ["", None, 7])
def test_a_ledger_needs_a_route(factory, given: object) -> None:  # noqa: F811
    with pytest.raises(ValueError, match="route"):
        PostgresSpendLedger(factory, limits(), route_id=given)  # type: ignore[arg-type]


# --- The migration -------------------------------------------------------------------------------------------------


def alembic(env: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    import harness
    return subprocess.run([sys.executable, "-m", "alembic", *arguments], cwd=harness.API_DIR, env=env,
                          capture_output=True, text=True, timeout=180)


ROWS = ("attempt_id::text", "owner_id::text", "intake_record_id::text", "scope", "state", "reserved_nano_usd",
        "charged_nano_usd", "max_input_tokens", "max_output_tokens", "created_at::text", "updated_at::text")


def old_ledger(session_factory) -> list[tuple]:
    """Revision 0014 rows, written as the old ledger wrote them: settings with one price, each state, some events."""
    states = (("RESERVED", None), ("UNKNOWN", None), ("SETTLED", 7_428_500), ("RELEASED", None))
    with session_factory() as session:
        session.execute(text("INSERT INTO usage_local.provider_spend_settings VALUES "
                             "(1, 2000000000, 2000000000, '2', '10', 'configuration-at-first-use', "
                             "'2026-10-16T00:00:00Z', '2026-10-17T00:00:00Z')"))
        for index, (state, charge) in enumerate(states):
            attempt = uuid.uuid4()
            session.execute(text("INSERT INTO usage_local.provider_spend_reservations VALUES (:a, :o, :i, :s, :st, 172160000, "
                                 ":c, 65600, 4096, '2026-10-16T00:00:00Z', '2026-10-16T01:00:00Z')"),
                            {"a": attempt, "o": uuid.uuid4(), "i": uuid.uuid4(), "s": f"intake:{index}", "st": state,
                             "c": charge})
            session.execute(text("INSERT INTO usage_local.provider_spend_events (attempt_id, kind, detail, nano_usd, "
                                 "created_at) VALUES (:a, 'RESERVED', 'intake', 172160000, '2026-10-16T00:00:00Z')"),
                            {"a": attempt})
        session.commit()
    return sorted(values(session_factory, f"SELECT {', '.join(ROWS)} FROM usage_local.provider_spend_reservations"))


EVENTS = "SELECT seq, attempt_id::text, kind, detail, nano_usd, created_at::text FROM usage_local.provider_spend_events ORDER BY seq"
SETTINGS = ("SELECT settings_id, global_cap_nano_usd, owner_cap_nano_usd, cap_source, frozen_at::text, updated_at::text "
            "FROM usage_local.provider_spend_settings")


@pytest.fixture
def at_0014(clean_spend, migrated, env):
    """The database one revision back; it always ends at head with an empty ledger."""
    down = alembic(env, "downgrade", "0014")
    assert down.returncode == 0, down.stdout + down.stderr
    yield clean_spend
    alembic(env, "upgrade", "head")
    empty_spend_ledger(clean_spend)


def test_the_migration_moves_the_frozen_price_to_the_openrouter_route_and_changes_no_amount(at_0014, env) -> None:
    rows = old_ledger(at_0014)
    events, settings = values(at_0014, EVENTS), values(at_0014, SETTINGS)

    up = alembic(env, "upgrade", "head")

    assert up.returncode == 0, up.stdout + up.stderr
    assert sorted(values(at_0014, f"SELECT {', '.join(ROWS)} FROM usage_local.provider_spend_reservations")) == rows
    assert values(at_0014, "SELECT DISTINCT route_id FROM usage_local.provider_spend_reservations") == [(OPENROUTER,)]
    assert values(at_0014, EVENTS) == events and values(at_0014, SETTINGS) == settings
    assert values(at_0014, "SELECT route_id, prompt_usd_per_million, completion_usd_per_million, frozen_at::text FROM "
                           "usage_local.provider_spend_route_prices") == [
        (OPENROUTER, "2", "10", settings[0][4])]
    openrouter = PostgresSpendLedger(at_0014, limits(global_cap="2.00", owner_cap="2.00",
                                                     price=TokenPrice(Decimal("2"), Decimal("10"))), route_id=OPENROUTER)
    assert openrouter.settle(rows[[row[4] for row in rows].index("RESERVED")][0], **USAGE).cost_usd == Decimal("0.008956")


def test_after_the_migration_the_old_frozen_price_still_refuses_a_different_openrouter_price(at_0014, env) -> None:
    old_ledger(at_0014)
    assert alembic(env, "upgrade", "head").returncode == 0
    changed = PostgresSpendLedger(at_0014, limits(global_cap="2.00", owner_cap="2.00"), route_id=OPENROUTER)
    with pytest.raises(LedgerConfigMismatch):
        changed.reserve(str(uuid.uuid4()), scope="s", **BOUNDS)


def test_a_downgrade_with_one_route_restores_the_settings_price_and_keeps_every_row(at_0014, env) -> None:
    rows = old_ledger(at_0014)
    assert alembic(env, "upgrade", "head").returncode == 0
    down = alembic(env, "downgrade", "0014")
    assert down.returncode == 0, down.stdout + down.stderr
    assert values(at_0014, "SELECT prompt_usd_per_million, completion_usd_per_million FROM "
                           "usage_local.provider_spend_settings") == [("2", "10")]
    assert sorted(values(at_0014, f"SELECT {', '.join(ROWS)} FROM usage_local.provider_spend_reservations")) == rows
    assert values(at_0014, "SELECT column_name FROM information_schema.columns WHERE table_schema = 'usage_local' AND "
                           "table_name = 'provider_spend_settings' ORDER BY ordinal_position") == [  # 0014 inserts by position
        (name,) for name in ("settings_id", "global_cap_nano_usd", "owner_cap_nano_usd", "prompt_usd_per_million",
                             "completion_usd_per_million", "cap_source", "frozen_at", "updated_at")]


def assert_events_refuse(session_factory, statement: str) -> None:
    before = values(session_factory, EVENT_ROWS)
    assert before
    with session_factory() as session:
        with pytest.raises(DBAPIError, match="provider_spend_events rows are immutable"):
            session.execute(text(statement))
        session.rollback()
    assert values(session_factory, EVENT_ROWS) == before


@pytest.mark.parametrize("statement", EVENT_CHANGES)
def test_events_from_two_routes_refuse_every_change(clean_spend, attempts, owner_a, owner_b, statement: str) -> None:
    on_a(clean_spend).reserve(attempts.new(owner_a), scope="s1", **BOUNDS)
    on_b(clean_spend).reserve(attempts.new(owner_b), scope="s2", **BOUNDS)
    assert len(values(clean_spend, EVENT_ROWS)) == 2
    assert_events_refuse(clean_spend, statement)


@pytest.mark.parametrize("statement", EVENT_CHANGES)
def test_events_still_refuse_every_change_through_the_0015_downgrade_and_upgrade(
        at_0014, env, attempts, owner_a, statement: str) -> None:
    old_ledger(at_0014)
    assert alembic(env, "upgrade", "head").returncode == 0
    assert alembic(env, "downgrade", "0014").returncode == 0
    assert_events_refuse(at_0014, statement)  # the downgrade rebuilds the neighbouring settings table

    assert alembic(env, "upgrade", "head").returncode == 0
    on_b(at_0014, global_cap="2.00", owner_cap="2.00").reserve(attempts.new(owner_a), scope="s2", **BOUNDS)
    assert {row[0] for row in values(at_0014, "SELECT route_id FROM usage_local.provider_spend_reservations")} == {
        OPENROUTER, ROUTE_B}
    assert_events_refuse(at_0014, statement)


def test_a_downgrade_is_refused_while_a_second_route_exists_and_keeps_it(clean_spend, attempts, owner_a, migrated, env) -> None:
    first, second = attempts.new(owner_a), attempts.new(owner_a)
    on_a(clean_spend).reserve(first, scope="s1", **BOUNDS)
    on_b(clean_spend).reserve(second, scope="s2", **BOUNDS)

    down = alembic(env, "downgrade", "0014")

    assert down.returncode != 0 and "downgrade below 0015 refused" in down.stdout + down.stderr
    assert on_a(clean_spend).state(first) == on_a(clean_spend).state(second) == "RESERVED"
