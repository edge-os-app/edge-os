"""The PostgreSQL spend ledger: the accepted `SpendLedger` rules, shared by every API process, with owner and global caps.

Seam: `PostgresSpendLedger` over a real migrated database. Reservations name saved interpretation attempts, made through
the attempt ledger. Money values are hand-worked literals at TEST prices: 2.00 and 7.50 USD per million tokens, so a
reservation for 12,064 input and 4,096 output tokens is 0.024128 + 0.03072 = 0.054848 USD.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from flows import submit

from edge_os_api.research.attempt_store import PostgresAttemptStore
from edge_os_api.research.interpretation_attempts import AttemptIdentity, AttemptLedger
from edge_os_api.research.provider_spend_ledger import PostgresSpendLedger, SpendLimits

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "hermes_interpretation"))
from spend_ledger import (  # noqa: E402
    CapExceeded, LedgerConfigMismatch, NotReserved, ReservationExists, ScopeBlocked, TokenPrice,
)

PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
RESERVATION = Decimal("0.054848")
BOUNDS = {"max_input_tokens": 12_064, "max_output_tokens": 4_096}
TASK = '{"task":"interpret","original_request":"Buy when price is up 1%"}'


def limits(global_cap: str = "0.20", owner_cap: str = "0.20", price: TokenPrice = PRICE) -> SpendLimits:
    return SpendLimits(global_cap_usd=Decimal(global_cap), owner_cap_usd=Decimal(owner_cap), price=price)


@pytest.fixture
def factory(client):
    return client.app.state.session_factory


def empty_spend_ledger(factory) -> None:
    from sqlalchemy import text
    with factory() as session:
        session.execute(text("TRUNCATE usage_local.provider_spend_events, usage_local.provider_spend_reservations, "
                             "usage_local.provider_spend_settings"))
        session.commit()


@pytest.fixture
def clean_spend(factory):
    """Each test starts and ends with an empty spend ledger: the tables are shared by the whole test session, and a
    later migration test may downgrade, which reservations would refuse."""
    empty_spend_ledger(factory)
    yield factory
    empty_spend_ledger(factory)


@pytest.fixture
def attempts(client, factory):
    """`new(headers)` saves a request for that owner and records one interpretation attempt; returns its id."""
    ledger = AttemptLedger(PostgresAttemptStore(factory), new_id=lambda: str(uuid.uuid4()),
                           now=lambda: dt.datetime.now(dt.timezone.utc))
    identity = AttemptIdentity(purpose="INTERPRET", prompt_version="prompt/1", system_prompt_sha256="a" * 64,
                               task_sha256=hashlib.sha256(TASK.encode()).hexdigest(), task_text=TASK,
                               response_shape_sha256="c" * 64, manifest_sha256="d" * 64,
                               config={"model": "fixture-model/1"}, runtime_label="LOCAL_FAKE_PROVIDER")

    class Attempts:
        def new(self, headers: dict[str, str]) -> str:
            owner = client.get("/v1/me", headers=headers).json()["user_id"]
            created = submit(client, headers)
            assert created.status_code == 201, created.text
            return ledger.begin(owner, created.json()["intake"]["record_id"], identity).attempt_id

    return Attempts()


def test_a_reservation_records_the_worst_case_and_one_past_the_cap_writes_nothing(clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.10"))
    first, second, third = attempts.new(owner_a), attempts.new(owner_a), attempts.new(owner_a)

    assert spend.reserve(first, scope="s1", **BOUNDS).amount_usd == RESERVATION
    with pytest.raises(CapExceeded):
        spend.reserve(second, scope="s2", **BOUNDS)

    assert spend.state(first) == "RESERVED" and spend.state(second) is None
    assert spend.committed_usd() == RESERVATION and [e.kind for e in spend.events(first)] == ["RESERVED"]
    assert spend.events(second) == [] and spend.liability_usd(third) is None


def test_each_owner_has_a_cap_and_every_owner_together_shares_the_global_cap(clean_spend, attempts, owner_a, owner_b) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.15", owner_cap="0.11"))
    a1, a2, a3 = attempts.new(owner_a), attempts.new(owner_a), attempts.new(owner_a)
    b1, b2 = attempts.new(owner_b), attempts.new(owner_b)

    spend.reserve(a1, scope="a1", **BOUNDS)
    spend.reserve(a2, scope="a2", **BOUNDS)  # owner A: 0.109696 of 0.11
    with pytest.raises(CapExceeded) as owner_full:
        spend.reserve(a3, scope="a3", **BOUNDS)
    assert owner_full.value.cap_usd == Decimal("0.11")
    with pytest.raises(CapExceeded) as global_full:  # owner B has room of its own, but all owners together do not
        spend.reserve(b1, scope="b1", **BOUNDS)
    assert global_full.value.cap_usd == Decimal("0.15")

    spend.release_unsent(a2, reason="no request was admitted")
    spend.reserve(b1, scope="b1", **BOUNDS)
    with pytest.raises(CapExceeded):
        spend.reserve(b2, scope="b2", **BOUNDS)
    assert spend.committed_usd() == RESERVATION * 2
    assert {u.attempt_id for u in spend.unresolved()} == {a1, b1}


def test_one_reservation_per_attempt_one_open_attempt_per_scope_and_only_saved_attempts(clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits())
    first, second = attempts.new(owner_a), attempts.new(owner_a)
    spend.reserve(first, scope="intake:1", **BOUNDS)

    with pytest.raises(ReservationExists):
        spend.reserve(first, scope="intake:2", **BOUNDS)
    with pytest.raises(ScopeBlocked):
        spend.reserve(second, scope="intake:1", **BOUNDS)
    from edge_os_api.research.provider_spend_ledger import AttemptNotSaved
    for unsaved in (str(uuid.uuid4()), "not-an-attempt-id"):
        with pytest.raises(AttemptNotSaved):
            spend.reserve(unsaved, scope="intake:3", **BOUNDS)
        assert spend.state(unsaved) is None and spend.events(unsaved) == []
    assert spend.committed_usd() == RESERVATION and spend.state(second) is None


def test_usage_settles_exactly_and_everything_else_keeps_the_whole_reservation(clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.30", owner_cap="0.30"))
    exact, invalid, lost, unsent = (attempts.new(owner_a) for _ in range(4))
    for index, attempt in enumerate((exact, invalid, lost, unsent)):
        spend.reserve(attempt, scope=f"scope-{index}", **BOUNDS)

    assert spend.settle(exact, input_tokens=1_423, output_tokens=611).cost_usd == Decimal("0.0074285")
    assert spend.settle(invalid, input_tokens=0, output_tokens=611).state == "UNKNOWN"
    spend.mark_unknown(lost, reason="TransportLost")
    spend.release_unsent(unsent, reason="CleanupPending")

    assert [spend.state(a) for a in (exact, invalid, lost, unsent)] == ["SETTLED", "UNKNOWN", "UNKNOWN", "RELEASED"]
    assert spend.committed_usd() == Decimal("0.0074285") + RESERVATION * 2
    for attempt in (exact, invalid, lost, unsent):  # nothing frees liability that is not still plainly RESERVED
        with pytest.raises(NotReserved):
            spend.release_unsent(attempt, reason="again")
    with pytest.raises(NotReserved):
        spend.settle(lost, input_tokens=10, output_tokens=10)
    assert spend.settle(exact, input_tokens=1_423, output_tokens=611).cost_usd == Decimal("0.0074285")
    assert [e.kind for e in spend.events(exact)] == ["RESERVED", "SETTLED", "DUPLICATE_EVIDENCE"]


def test_late_evidence_settles_unknown_liability_once_and_a_disagreement_keeps_the_higher_charge(
        clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits())
    lost = attempts.new(owner_a)
    spend.reserve(lost, scope="s", **BOUNDS)
    spend.mark_unknown(lost, reason="Killed")

    assert spend.reconcile(lost, input_tokens=1_423, output_tokens=611, source="provider record").cost_usd == Decimal("0.0074285")
    assert spend.reconcile(lost, input_tokens=2_000, output_tokens=611, source="later record").cost_usd == Decimal("0.0085825")
    with pytest.raises(ValueError):
        spend.reconcile(lost, input_tokens=0, output_tokens=1, source="nothing")
    assert [e.kind for e in spend.events(lost)] == ["RESERVED", "UNKNOWN", "RECONCILED", "CONFLICTING_EVIDENCE"]
    assert spend.committed_usd() == Decimal("0.0085825") and spend.unresolved() == []


def test_a_changed_cap_refuses_new_reservations_until_a_recorded_change_and_old_ones_still_settle(
        clean_spend, attempts, owner_a) -> None:
    held, waiting, after = attempts.new(owner_a), attempts.new(owner_a), attempts.new(owner_a)
    PostgresSpendLedger(clean_spend, limits()).reserve(held, scope="held", **BOUNDS)

    raised = PostgresSpendLedger(clean_spend, limits(global_cap="5.00", owner_cap="5.00"))  # a restart with new caps
    with pytest.raises(LedgerConfigMismatch):
        raised.reserve(waiting, scope="waiting", **BOUNDS)
    assert raised.settle(held, input_tokens=1_423, output_tokens=611).cost_usd == Decimal("0.0074285")
    with pytest.raises(LedgerConfigMismatch):  # prices never change, even through a later process
        PostgresSpendLedger(clean_spend, limits(price=TokenPrice(Decimal("1.00"), Decimal("7.50")))).reserve(
            waiting, scope="waiting", **BOUNDS)

    raised.change_caps(global_cap_usd=Decimal("0.06"), owner_cap_usd=Decimal("0.06"), reason="ticket test lowers the cap")
    with pytest.raises(CapExceeded):  # 0.0074285 + 0.054848 > 0.06: the recorded cap applies, whatever is configured
        raised.reserve(waiting, scope="waiting", **BOUNDS)
    raised.change_caps(global_cap_usd=Decimal("0.07"), owner_cap_usd=Decimal("0.07"), reason="ticket test raises it")
    assert PostgresSpendLedger(clean_spend, limits()).reserve(waiting, scope="waiting", **BOUNDS).amount_usd == RESERVATION
    with pytest.raises(CapExceeded):
        raised.reserve(after, scope="after", **BOUNDS)
    with pytest.raises(ValueError):
        raised.change_caps(global_cap_usd=Decimal("1"), owner_cap_usd=Decimal("1"), reason=" ")


def test_a_new_process_view_of_the_database_sees_the_same_liability(clean_spend, attempts, owner_a, settings) -> None:
    from edge_os_api.core.database import make_engine, make_session_factory
    first = attempts.new(owner_a)
    PostgresSpendLedger(clean_spend, limits()).reserve(first, scope="s", **BOUNDS)

    engine = make_engine(settings.database_url)
    try:
        reopened = PostgresSpendLedger(make_session_factory(engine), limits())
        assert reopened.state(first) == "RESERVED" and reopened.committed_usd() == RESERVATION
        with pytest.raises(ScopeBlocked):
            reopened.reserve(attempts.new(owner_a), scope="s", **BOUNDS)
    finally:
        engine.dispose()


def test_two_api_processes_contending_for_the_last_capacity_never_pass_either_cap(
        clean_spend, attempts, owner_a, owner_b, settings) -> None:
    import json
    import subprocess
    import time
    owners = {"a": [attempts.new(owner_a) for _ in range(4)], "b": [attempts.new(owner_b) for _ in range(4)]}
    halves = [[*owners["a"][:2], *owners["b"][:2]], [*owners["a"][2:], *owners["b"][2:]]]
    start_at = str(time.time() + 4)
    worker = Path(__file__).with_name("spend_reservation_worker.py")
    processes = [subprocess.Popen([sys.executable, str(worker), settings.database_url, "0.20", "0.11", start_at,
                                   *(f"{attempt}:{attempt}" for attempt in half)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for half in halves]
    outputs = [process.communicate(timeout=120) for process in processes]

    assert [p.returncode for p in processes] == [0, 0], [err[-800:] for _out, err in outputs]
    results = [item for out, _err in outputs for item in json.loads(out)]
    granted = {r["attempt_id"] for r in results if r["outcome"] == "RESERVED"}
    # 0.20 holds three reservations of 0.054848 and each owner's 0.11 holds two: exactly three are granted in total
    assert len(results) == 8 and len(granted) == 3
    assert {r["outcome"] for r in results} == {"RESERVED", "CapExceeded"}
    assert all(len(granted & set(mine)) <= 2 for mine in owners.values())
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.20", owner_cap="0.11"))
    assert spend.committed_usd() == RESERVATION * 3 and {u.attempt_id for u in spend.unresolved()} == granted


def test_a_downgrade_below_0013_is_refused_while_any_reservation_exists_and_keeps_it(
        clean_spend, attempts, owner_a, migrated, env) -> None:
    import subprocess

    import harness
    held = attempts.new(owner_a)
    spend = PostgresSpendLedger(clean_spend, limits())
    spend.reserve(held, scope="s", **BOUNDS)
    spend.mark_unknown(held, reason="TransportLost")

    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "0012"], cwd=harness.API_DIR, env=env,
                          capture_output=True, text=True, timeout=180)

    assert down.returncode != 0 and "downgrade below 0013 refused" in down.stdout + down.stderr
    assert spend.state(held) == "UNKNOWN" and spend.committed_usd() == RESERVATION

    empty_spend_ledger(clean_spend)  # no reservation left, but a recorded cap decision is history too
    PostgresSpendLedger(clean_spend, limits()).change_caps(global_cap_usd=Decimal("0.30"), owner_cap_usd=Decimal("0.30"),
                                                           reason="recorded decision")
    again = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "0012"], cwd=harness.API_DIR, env=env,
                           capture_output=True, text=True, timeout=180)
    assert again.returncode != 0 and "downgrade below 0013 refused" in again.stdout + again.stderr


# --- The per-call output limit (ORBIO_CREDIT_DESIGN 2b) ----------------------------------------------------------------
# TEST prices: 12,064 input tokens cost 24,128,000 nano-USD and each output token 7,500 nano-USD. The tests set their own
# `min_output_tokens`; no release sets one.

def recorded(factory, attempt: str) -> tuple[list[tuple], list[str]]:
    from sqlalchemy import text
    with factory() as session:
        rows = [tuple(r) for r in session.execute(text(
            "SELECT max_output_tokens, reserved_nano_usd FROM usage_local.provider_spend_reservations "
            "WHERE attempt_id = :a"), {"a": uuid.UUID(attempt)}).all()]
        kinds = list(session.execute(text("SELECT kind FROM usage_local.provider_spend_events WHERE attempt_id = :a"),
                                     {"a": uuid.UUID(attempt)}).scalars())
    return rows, kinds


def test_the_owner_headroom_lowers_the_output_limit_inside_the_reservation(clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.20", owner_cap="0.05"))
    attempt = attempts.new(owner_a)

    reservation = spend.reserve(attempt, scope="s1", **BOUNDS, min_output_tokens=1)

    # (50,000,000 - 24,128,000) / 7,500 = 3,449.6, so 3,449 output tokens: 24,128,000 + 25,867,500 nano-USD
    assert (reservation.max_output_tokens, reservation.amount_usd) == (3_449, Decimal("0.0499955"))
    assert spend.reserved_output_tokens(attempt) == 3_449
    assert recorded(clean_spend, attempt) == ([(3_449, 49_995_500)], ["RESERVED"])


def test_the_global_headroom_lowers_the_output_limit_when_it_is_the_smaller(clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.04", owner_cap="0.20"))
    attempt = attempts.new(owner_a)
    reservation = spend.reserve(attempt, scope="s1", **BOUNDS, min_output_tokens=1)
    # (40,000,000 - 24,128,000) / 7,500 = 2,116.3, so 2,116 output tokens: 39,998,000 nano-USD
    assert (reservation.max_output_tokens, reservation.amount_usd) == (2_116, Decimal("0.039998"))
    assert recorded(clean_spend, attempt) == ([(2_116, 39_998_000)], ["RESERVED"])


def test_a_call_over_budget_is_refused_before_anything_is_written(clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.20", owner_cap="0.05"))
    attempt = attempts.new(owner_a)

    with pytest.raises(CapExceeded) as refused:  # 3,450 tokens would cost 50,003,000 nano-USD: past the owner's 0.05
        spend.reserve(attempt, scope="s1", **BOUNDS, min_output_tokens=3_450)

    assert (refused.value.requested_usd, refused.value.cap_usd) == (Decimal("0.050003"), Decimal("0.05"))
    assert recorded(clean_spend, attempt) == ([], [])
    assert spend.state(attempt) is None and spend.reserved_output_tokens(attempt) is None
    assert spend.committed_usd() == 0


def test_without_a_smallest_limit_the_postgres_reservation_is_exact_as_before(clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.20", owner_cap="0.05"))
    attempt = attempts.new(owner_a)
    with pytest.raises(CapExceeded) as refused:
        spend.reserve(attempt, scope="s1", **BOUNDS)
    assert refused.value.requested_usd == RESERVATION and recorded(clean_spend, attempt) == ([], [])
    roomy = PostgresSpendLedger(clean_spend, limits())
    roomy.change_caps(global_cap_usd=Decimal("0.20"), owner_cap_usd=Decimal("0.20"), reason="test restores room")
    reservation = roomy.reserve(attempt, scope="s1", **BOUNDS)
    assert (reservation.max_output_tokens, reservation.amount_usd) == (4_096, RESERVATION)


@pytest.mark.parametrize("smallest", [0, True, 4_097, "1"])
def test_a_postgres_smallest_limit_outside_one_to_the_full_limit_is_refused(clean_spend, attempts, owner_a,
                                                                            smallest) -> None:
    spend = PostgresSpendLedger(clean_spend, limits())
    attempt = attempts.new(owner_a)
    with pytest.raises(ValueError):
        spend.reserve(attempt, scope="s1", **BOUNDS, min_output_tokens=smallest)
    assert recorded(clean_spend, attempt) == ([], [])


def test_a_started_call_reserved_with_a_lowered_limit_is_never_reserved_again_after_more_headroom(
        clean_spend, attempts, owner_a) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.20", owner_cap="0.05"))
    attempt = attempts.new(owner_a)
    spend.reserve(attempt, scope="s1", **BOUNDS, min_output_tokens=1)
    spend.mark_unknown(attempt, reason="the host runner was killed after the start")

    spend.change_caps(global_cap_usd=Decimal("0.20"), owner_cap_usd=Decimal("0.20"), reason="test raises the cap")
    with pytest.raises(ReservationExists):
        spend.reserve(attempt, scope="s1", **BOUNDS, min_output_tokens=1)

    assert spend.reserved_output_tokens(attempt) == 3_449  # no new limit
    assert recorded(clean_spend, attempt) == ([(3_449, 49_995_500)], ["RESERVED", "UNKNOWN"])


def test_two_processes_racing_for_the_last_headroom_with_lowered_limits_never_pass_the_cap(
        clean_spend, attempts, owner_a, owner_b, settings) -> None:
    import json
    import subprocess
    import time
    mine = [attempts.new(owner_a) for _ in range(3)] + [attempts.new(owner_b) for _ in range(3)]
    halves = [mine[0::2], mine[1::2]]
    start_at = str(time.time() + 4)
    worker = Path(__file__).with_name("spend_reservation_worker.py")
    processes = [subprocess.Popen([sys.executable, str(worker), settings.database_url, "0.15", "0.20", start_at, "min=1",
                                   *(f"{attempt}:{attempt}" for attempt in half)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for half in halves]
    outputs = [process.communicate(timeout=120) for process in processes]

    assert [p.returncode for p in processes] == [0, 0], [err[-800:] for _out, err in outputs]
    results = [item for out, _err in outputs for item in json.loads(out)]
    # 0.15 holds two full calls (0.109696); the 0.040304 left gives a third call (40,304,000 - 24,128,000) / 7,500 =
    # 2,156 output tokens (40,298,000 nano-USD); the 6,000 nano-USD left fits no call
    assert sorted((r["outcome"], r["max_output_tokens"]) for r in results) == sorted(
        [("RESERVED", 4_096), ("RESERVED", 4_096), ("RESERVED", 2_156)] + [("CapExceeded", None)] * 3)
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.15", owner_cap="0.20"))
    assert spend.committed_usd() == Decimal("0.149994") <= Decimal("0.15")


# --- The owner's budget from the ledger: `spend_view` and its CREDIT form (ORBIO_CREDIT_DESIGN 2a) -----------------------------------
# TEST prices 2.00 / 7.50 USD per million: a reservation is 54,848,000 nano-USD and 1,423 + 611 tokens settle at 7,428,500.

def owner_of(client, headers) -> uuid.UUID:
    return uuid.UUID(client.get("/v1/me", headers=headers).json()["user_id"])


def test_a_ledger_that_was_never_used_has_no_budget_rather_than_a_zero_one(clean_spend, client, owner_a) -> None:
    from sqlalchemy import text

    from edge_os_api.research.provider_spend_ledger import spend_view
    with clean_spend() as session:
        assert spend_view(session, owner_of(client, owner_a)) is None
        assert session.execute(text("SELECT count(*) FROM usage_local.provider_spend_settings")).scalar_one() == 0
    from edge_os_api.research.interpretation_workflow import model_budget
    assert model_budget(None) is None


def test_held_liability_is_used_budget_and_the_smaller_headroom_is_what_is_available(
        clean_spend, attempts, client, owner_a, owner_b) -> None:
    from edge_os_api.research.provider_spend_ledger import PostgresSpendLedger, spend_view
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.20", owner_cap="0.12"))
    settled, lost, released, other = (attempts.new(owner_a), attempts.new(owner_a), attempts.new(owner_a),
                                      attempts.new(owner_b))
    spend.reserve(settled, scope="s1", **BOUNDS)
    spend.settle(settled, input_tokens=1_423, output_tokens=611)
    spend.reserve(lost, scope="s2", **BOUNDS)
    spend.mark_unknown(lost, reason="the outcome is not known")
    spend.reserve(released, scope="s3", **BOUNDS)
    spend.release_unsent(released, reason="no request was admitted")
    spend.reserve(other, scope="s4", **BOUNDS)  # owner B's call, still RESERVED

    with clean_spend() as session:
        mine, theirs = spend_view(session, owner_of(client, owner_a)), spend_view(session, owner_of(client, owner_b))
        nobody = spend_view(session, uuid.uuid4())

    # owner A: 120,000,000 - (7,428,500 + 54,848,000) = 57,723,500; everyone: 200,000,000 - 117,124,500 = 82,875,500
    assert mine == {"owner_cap": 120_000_000, "global_cap": 200_000_000, "settled": 7_428_500, "held": 54_848_000,
                    "held_calls": 1, "available": 57_723_500}
    assert theirs == {"owner_cap": 120_000_000, "global_cap": 200_000_000, "settled": 0, "held": 54_848_000,
                      "held_calls": 1, "available": 65_152_000}
    assert nobody["available"] == 82_875_500 and (nobody["settled"], nobody["held"], nobody["held_calls"]) == (0, 0, 0)
    from edge_os_api.research.interpretation_workflow import model_budget
    assert model_budget(mine) == {"unit": "CREDIT", "state": "SET", "owner_cap_credit": "0.12", "global_cap_credit": "0.2",
                                  "settled_credit": "0.0074285", "held_credit": "0.054848", "held_calls": 1,
                                  "available_credit": "0.0577235"}



def test_a_call_over_the_global_headroom_is_refused_against_the_global_cap(clean_spend, attempts, owner_a, owner_b) -> None:
    spend = PostgresSpendLedger(clean_spend, limits(global_cap="0.07", owner_cap="0.20"))
    spend.reserve(attempts.new(owner_b), scope="b1", **BOUNDS)  # 0.054848 of the 0.07 everyone shares
    attempt = attempts.new(owner_a)

    with pytest.raises(CapExceeded) as refused:  # 15,152,000 left, but the input alone costs 24,128,000
        spend.reserve(attempt, scope="a1", **BOUNDS, min_output_tokens=1)

    assert (refused.value.committed_usd, refused.value.requested_usd, refused.value.cap_usd) == (
        RESERVATION, Decimal("0.0241355"), Decimal("0.07"))
    assert recorded(clean_spend, attempt) == ([], [])
