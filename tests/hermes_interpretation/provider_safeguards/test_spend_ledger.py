"""The local spend ledger, tested through reserve, settle and reopen with real files and real processes.

The money values below are literals worked out by hand. The prices are test prices. They are not current provider
prices and they carry no meaning for any release. The ledger proves LOCAL accounting only. It cannot prove an upstream
billing ceiling.
"""

from __future__ import annotations

import multiprocessing
import os
import sqlite3
import subprocess
import sys
import textwrap
import threading
from decimal import Decimal
from pathlib import Path

import pytest

from spend_ledger import (
    CapExceeded, LedgerConfigMismatch, NotReserved, ReservationExists, ScopeBlocked, SpendLedger, TokenPrice,
)

PRICE = TokenPrice(prompt_usd_per_million=Decimal("2.00"), completion_usd_per_million=Decimal("7.50"))
CAP = Decimal("0.10")
HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / "scripts" / "hermes_interpretation"


def ledger(tmp_path: Path, cap: Decimal = CAP, price: TokenPrice = PRICE) -> SpendLedger:
    return SpendLedger(tmp_path / "spend.sqlite", cap_usd=cap, price=price)


@pytest.mark.parametrize("prompt, completion", [("-1", "7.50"), ("2.00", "-0.01"), ("NaN", "1"), ("Infinity", "1")])
def test_a_token_price_must_be_a_finite_non_negative_amount(prompt: str, completion: str) -> None:
    with pytest.raises(ValueError):
        TokenPrice(Decimal(prompt), Decimal(completion))


def test_a_reservation_is_the_worst_case_for_its_token_bounds(tmp_path: Path) -> None:
    spend = ledger(tmp_path)

    reservation = spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)

    # 7,300 x 2.00 / 1,000,000 = 0.0146 and 4,096 x 7.50 / 1,000,000 = 0.03072
    assert reservation.amount_usd == Decimal("0.04532")
    assert spend.committed_usd() == Decimal("0.04532")
    assert spend.state("attempt-1") == "RESERVED"


def test_known_usage_settles_to_the_exact_cost_and_frees_the_unused_reservation(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)

    settlement = spend.settle("attempt-1", input_tokens=1_423, output_tokens=611)

    # 1,423 x 2.00 / 1e6 = 0.002846 and 611 x 7.50 / 1e6 = 0.0045825
    assert (settlement.state, settlement.cost_usd) == ("SETTLED", Decimal("0.0074285"))
    assert spend.committed_usd() == Decimal("0.0074285")


def test_a_second_settlement_of_the_same_usage_does_not_charge_twice(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.settle("attempt-1", input_tokens=1_423, output_tokens=611)

    spend.settle("attempt-1", input_tokens=1_423, output_tokens=611)

    assert spend.committed_usd() == Decimal("0.0074285")


def test_reservations_beyond_the_cap_are_refused_and_nothing_is_written(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.reserve("attempt-2", scope="case-b", max_input_tokens=7_300, max_output_tokens=4_096)

    with pytest.raises(CapExceeded) as refused:
        spend.reserve("attempt-3", scope="case-c", max_input_tokens=7_300, max_output_tokens=4_096)

    assert refused.value.committed_usd == Decimal("0.09064")
    assert refused.value.requested_usd == Decimal("0.04532")
    assert spend.committed_usd() == Decimal("0.09064")
    assert spend.state("attempt-3") is None


def test_the_cap_is_exact_decimal_money_not_binary_floating_point(tmp_path: Path) -> None:
    # 0.1 + 0.2 is 0.30000000000000004 in binary floating point. A float ledger would refuse the exact total.
    price = TokenPrice(prompt_usd_per_million=Decimal("0.10"), completion_usd_per_million=Decimal("0.20"))
    spend = ledger(tmp_path, cap=Decimal("0.30"), price=price)

    spend.reserve("attempt-1", scope="case-a", max_input_tokens=1_000_000, max_output_tokens=1_000_000)

    assert spend.committed_usd() == Decimal("0.30")
    with pytest.raises(CapExceeded):
        spend.reserve("attempt-2", scope="case-b", max_input_tokens=1, max_output_tokens=0)


@pytest.mark.parametrize("usage", [
    (None, None), (100, None), (None, 100), (True, 5), (5, True), (-1, 5), (5, -1), ("12", 5), (1.5, 5), (5, float("nan")),
    (2 ** 70, 5), (0, 5), (0, 0)])
def test_missing_or_invalid_usage_keeps_the_whole_reservation_as_liability(tmp_path: Path, usage) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)

    settlement = spend.settle("attempt-1", input_tokens=usage[0], output_tokens=usage[1])

    assert (settlement.state, settlement.cost_usd) == ("UNKNOWN", Decimal("0.04532"))
    assert spend.committed_usd() == Decimal("0.04532")


def test_an_unknown_outcome_keeps_its_full_reservation_and_blocks_the_next_attempt_in_its_scope(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)

    spend.mark_unknown("attempt-1", reason="TimeoutExpired")

    assert spend.state("attempt-1") == "UNKNOWN"
    assert spend.committed_usd() == Decimal("0.04532")
    with pytest.raises(ScopeBlocked):
        spend.reserve("attempt-2", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.reserve("attempt-3", scope="case-b", max_input_tokens=7_300, max_output_tokens=4_096)  # other scopes go on


def test_a_reservation_is_released_only_while_no_request_could_have_started(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.release_unsent("attempt-1", reason="RequestNotAdmitted")
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("RELEASED", Decimal("0"))

    spend.reserve("attempt-2", scope="case-b", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.mark_unknown("attempt-2", reason="ContainerExit")
    with pytest.raises(NotReserved):
        spend.release_unsent("attempt-2", reason="RequestNotAdmitted")
    assert spend.committed_usd() == Decimal("0.04532")


def test_an_attempt_identifier_reserves_once_so_a_restart_cannot_spend_it_again(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.settle("attempt-1", input_tokens=1_423, output_tokens=611)

    with pytest.raises(ReservationExists):
        spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)

    assert spend.committed_usd() == Decimal("0.0074285")


def test_state_survives_reopening_the_same_file(tmp_path: Path) -> None:
    first = ledger(tmp_path)
    first.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    first.settle("attempt-1", input_tokens=1_423, output_tokens=611)
    first.reserve("attempt-2", scope="case-b", max_input_tokens=7_300, max_output_tokens=4_096)

    reopened = ledger(tmp_path)

    assert reopened.state("attempt-1") == "SETTLED" and reopened.state("attempt-2") == "RESERVED"
    assert reopened.committed_usd() == Decimal("0.0074285") + Decimal("0.04532")
    assert [row.attempt_id for row in reopened.unresolved()] == ["attempt-2"]


def test_reopening_with_a_different_cap_or_price_is_refused(tmp_path: Path) -> None:
    ledger(tmp_path)

    with pytest.raises(LedgerConfigMismatch):
        ledger(tmp_path, cap=Decimal("1.00"))
    with pytest.raises(LedgerConfigMismatch):
        ledger(tmp_path, price=TokenPrice(Decimal("1.00"), Decimal("7.50")))


def test_a_killed_process_leaves_its_reservation_as_liability(tmp_path: Path) -> None:
    code = textwrap.dedent(f"""
        import os, sys
        from decimal import Decimal
        sys.path.insert(0, {str(SCRIPTS)!r})
        from spend_ledger import SpendLedger, TokenPrice
        spend = SpendLedger({str(tmp_path / 'spend.sqlite')!r}, cap_usd=Decimal("0.10"),
                            price=TokenPrice(Decimal("2.00"), Decimal("7.50")))
        spend.reserve("attempt-1", scope="case-a", max_input_tokens=7300, max_output_tokens=4096)
        os._exit(9)  # killed between the reservation and any settlement
    """)

    killed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)

    assert killed.returncode == 9, killed.stderr
    reopened = ledger(tmp_path)
    assert reopened.state("attempt-1") == "RESERVED"
    assert reopened.committed_usd() == Decimal("0.04532")
    with pytest.raises(ScopeBlocked):
        reopened.reserve("attempt-2", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)


def test_concurrent_reservations_never_exceed_the_cap(tmp_path: Path) -> None:
    spend = ledger(tmp_path)  # room for exactly two reservations of 0.04532
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(index: int) -> None:
        try:
            ledger(tmp_path).reserve(f"attempt-{index}", scope=f"case-{index}", max_input_tokens=7_300,
                                     max_output_tokens=4_096)
            result = "reserved"
        except CapExceeded:
            result = "refused"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt, args=(index,)) for index in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert sorted(outcomes) == ["refused"] * 10 + ["reserved"] * 2
    assert spend.committed_usd() == Decimal("0.09064")


def _reserve_in_process(path: str, queue) -> None:
    try:
        SpendLedger(path, cap_usd=Decimal("0.10"), price=TokenPrice(Decimal("2.00"), Decimal("7.50"))).reserve(
            "attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
        queue.put("reserved")
    except ReservationExists:
        queue.put("exists")


def test_concurrent_processes_cannot_reserve_the_same_attempt_twice(tmp_path: Path) -> None:
    ledger(tmp_path)
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    workers = [context.Process(target=_reserve_in_process, args=(str(tmp_path / "spend.sqlite"), queue)) for _ in range(6)]
    for worker in workers:
        worker.start()
    results = sorted(queue.get(timeout=120) for _ in workers)
    for worker in workers:
        worker.join(timeout=60)

    assert results == ["exists"] * 5 + ["reserved"]
    assert ledger(tmp_path).committed_usd() == Decimal("0.04532")


def test_late_evidence_settles_an_unknown_outcome_once_and_is_recorded(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.mark_unknown("attempt-1", reason="TimeoutExpired")

    late = spend.reconcile("attempt-1", input_tokens=1_423, output_tokens=611, source="LATE_RESULT")

    assert (late.state, late.cost_usd) == ("SETTLED", Decimal("0.0074285"))
    assert spend.committed_usd() == Decimal("0.0074285")
    again = spend.reconcile("attempt-1", input_tokens=1_423, output_tokens=611, source="LATE_RESULT")
    assert again.cost_usd == Decimal("0.0074285") and spend.committed_usd() == Decimal("0.0074285")
    kinds = [event.kind for event in spend.events("attempt-1")]
    assert kinds == ["RESERVED", "UNKNOWN", "RECONCILED", "DUPLICATE_EVIDENCE"]


def test_late_evidence_that_disagrees_with_a_settlement_keeps_the_higher_charge_and_is_flagged(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.settle("attempt-1", input_tokens=1_423, output_tokens=611)

    spend.reconcile("attempt-1", input_tokens=2_000, output_tokens=611, source="LATE_RESULT")

    # 2,000 x 2.00 / 1e6 = 0.004 and 611 x 7.50 / 1e6 = 0.0045825
    assert spend.committed_usd() == Decimal("0.0085825")
    assert "CONFLICTING_EVIDENCE" in [event.kind for event in spend.events("attempt-1")]


def test_late_evidence_that_is_lower_than_the_recorded_charge_does_not_lower_it(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.settle("attempt-1", input_tokens=2_000, output_tokens=611)

    spend.reconcile("attempt-1", input_tokens=1_000, output_tokens=100, source="LATE_RESULT")

    assert spend.committed_usd() == Decimal("0.0085825")


def test_a_charge_above_its_reservation_still_counts_and_blocks_later_reservations(tmp_path: Path) -> None:
    spend = ledger(tmp_path, cap=Decimal("0.05"))
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=1_000, max_output_tokens=100)  # 0.002 + 0.00075

    settlement = spend.settle("attempt-1", input_tokens=20_000, output_tokens=4_000)  # provider ignored the bounds

    assert settlement.cost_usd == Decimal("0.07")  # 0.04 + 0.03
    assert spend.committed_usd() == Decimal("0.07")
    assert "OVERRUN" in [event.kind for event in spend.events("attempt-1")]
    with pytest.raises(CapExceeded):
        spend.reserve("attempt-2", scope="case-b", max_input_tokens=1, max_output_tokens=1)


def test_money_is_stored_as_integers(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    spend.settle("attempt-1", input_tokens=1_423, output_tokens=611)

    with sqlite3.connect(tmp_path / "spend.sqlite") as connection:
        kinds = {row[0] for row in connection.execute(
            "select typeof(reserved_nano_usd) from reservation union select typeof(charged_nano_usd) from reservation "
            "where charged_nano_usd is not null")}

    assert kinds == {"integer"}


def test_an_interrupted_settlement_keeps_the_liability(tmp_path: Path) -> None:
    spend = ledger(tmp_path)
    spend.reserve("attempt-1", scope="case-a", max_input_tokens=7_300, max_output_tokens=4_096)
    path = tmp_path / "spend.sqlite"
    path.chmod(0o444)  # the settlement write now fails like a full or failing disk would
    try:
        with pytest.raises(sqlite3.OperationalError):
            spend.settle("attempt-1", input_tokens=1_423, output_tokens=611)
    finally:
        path.chmod(0o644)

    reopened = ledger(tmp_path)
    assert reopened.state("attempt-1") == "RESERVED"
    assert reopened.committed_usd() == Decimal("0.04532")
    assert os.access(path, os.W_OK)
