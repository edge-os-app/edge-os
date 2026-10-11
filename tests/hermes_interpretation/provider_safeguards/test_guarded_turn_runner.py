"""The guarded turn runner: identity check, reservation before the request, settlement after it.

The wrapped runner is a controlled stand-in for the process boundary. It returns authored results. No provider, key or
network is used. These tests show the money and refusal rules around the boundary, not model behaviour.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from pathlib import Path

import pytest

from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage
from guarded_turn_runner import GuardedTurnRunner
from provider_guard import GuardPolicy
from spend_ledger import SpendLedger, TokenPrice

PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
POLICY = GuardPolicy(model="vendor/model-1", max_output_tokens=4096, max_request_bytes=7_236, max_envelope_chars=2_500)
RESERVATION = Decimal("0.04532")  # (7,236 + 64) x 2.00 / 1e6 + 4,096 x 7.50 / 1e6
CAP = Decimal("0.10")


def turn(attempt_id: str = "attempt-1", **changes) -> HermesTurn:
    fields = dict(attempt_id=attempt_id, system_prompt="prompt", user_message="task", model="vendor/model-1",
                  route="route-1", max_output_tokens=4096)
    fields.update(changes)
    return HermesTurn(**fields)


def reported(input_tokens=1_423, output_tokens=611) -> Usage:
    return Usage(input_tokens, output_tokens, None, "PROVIDER_REPORTED")


def returned(**changes) -> HermesTurnResult:
    fields = dict(status="RETURNED", text="{}", usage=reported(), request_count=1, observed={}, error_class=None)
    fields.update(changes)
    return HermesTurnResult(**fields)


class Delegate:
    """Plays the process boundary. It records how often it ran and what the ledger said while it ran."""

    def __init__(self, ledger: SpendLedger, *results: HermesTurnResult | Exception) -> None:
        self.ledger, self.results, self.calls, self.seen_during = ledger, list(results), 0, []

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        self.calls += 1
        self.seen_during.append((self.ledger.state(turn.attempt_id), self.ledger.committed_usd()))
        outcome = self.results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def ledger(tmp_path: Path) -> SpendLedger:
    return SpendLedger(tmp_path / "spend.sqlite", cap_usd=CAP, price=PRICE)


def runner(ledger: SpendLedger, *results: HermesTurnResult | Exception) -> tuple[GuardedTurnRunner, Delegate]:
    delegate = Delegate(ledger, *results)
    return GuardedTurnRunner(delegate, ledger, POLICY, scope_for=lambda t: "case-a"), delegate


def test_a_returned_answer_with_usage_is_charged_exactly_and_reported_in_the_result(ledger: SpendLedger) -> None:
    guarded, delegate = runner(ledger, returned())

    result = guarded.run_turn(turn())

    assert (result.status, result.text, delegate.calls) == ("RETURNED", "{}", 1)
    assert ledger.state("attempt-1") == "SETTLED" and ledger.committed_usd() == Decimal("0.0074285")
    assert result.observed["spend_state"] == "SETTLED" and result.observed["spend_charge_usd"] == "0.0074285"


def test_the_reservation_exists_before_the_request_can_start(ledger: SpendLedger) -> None:
    guarded, delegate = runner(ledger, returned())

    guarded.run_turn(turn())

    assert delegate.seen_during == [("RESERVED", RESERVATION)]


@pytest.mark.parametrize("changes", [
    {"model": "vendor/other"}, {"max_output_tokens": 8192}, {"user_message": "x" * 7_300}])
def test_a_turn_that_differs_from_the_policy_is_refused_before_anything_is_reserved(ledger: SpendLedger, changes) -> None:
    guarded, delegate = runner(ledger, returned())

    result = guarded.run_turn(turn(**changes))

    assert (result.status, result.request_count, result.error_class) == ("PROVIDER_FAILED", 0, "RequestNotAdmitted")
    assert delegate.calls == 0 and ledger.state("attempt-1") is None and ledger.committed_usd() == 0


def test_an_exhausted_cap_refuses_the_next_turn_without_calling_the_boundary(ledger: SpendLedger) -> None:
    ledger.reserve("older-1", scope="case-x", max_input_tokens=7_300, max_output_tokens=4_096)
    ledger.reserve("older-2", scope="case-y", max_input_tokens=7_300, max_output_tokens=4_096)
    guarded, delegate = runner(ledger, returned())

    result = guarded.run_turn(turn())

    assert (result.status, result.request_count, result.error_class) == ("PROVIDER_FAILED", 0, "SpendCapReached")
    assert delegate.calls == 0 and ledger.state("attempt-1") is None


def test_a_truncated_answer_is_charged_from_its_reported_usage(ledger: SpendLedger) -> None:
    guarded, _ = runner(ledger, returned(status="TRUNCATED", usage=reported(1_000, 4_096)))

    guarded.run_turn(turn())

    assert ledger.committed_usd() == Decimal("0.032720")  # 1,000 x 2.00 / 1e6 + 4,096 x 7.50 / 1e6


@pytest.mark.parametrize("usage", [Usage(), Usage(True, 5, None, "PROVIDER_REPORTED"), Usage(-1, 5, None, "PROVIDER_REPORTED"),
                                   Usage(1_423, 611, None, "UNKNOWN")])
def test_missing_or_malformed_usage_keeps_the_full_reservation(ledger: SpendLedger, usage: Usage) -> None:
    guarded, _ = runner(ledger, returned(usage=usage))

    result = guarded.run_turn(turn())

    assert (ledger.state("attempt-1"), ledger.committed_usd()) == ("UNKNOWN", RESERVATION)
    assert result.observed["spend_state"] == "UNKNOWN"


@pytest.mark.parametrize("outcome", [
    returned(status="PROVIDER_FAILED", text=None, usage=Usage(), error_class="ProviderHTTPError"),
    returned(status="TIMED_OUT", text=None, usage=Usage(), request_count=None, error_class="TimeoutExpired"),
    returned(status="UNKNOWN", text=None, usage=Usage(), request_count=None, error_class="ContainerExit"),
    returned(request_count=2)])
def test_an_unclear_outcome_keeps_liability_and_blocks_an_automatic_retry(ledger: SpendLedger, outcome) -> None:
    guarded, delegate = runner(ledger, outcome, returned())

    guarded.run_turn(turn())
    retry = guarded.run_turn(turn("attempt-2"))

    assert (ledger.state("attempt-1"), ledger.committed_usd()) == ("UNKNOWN", RESERVATION)
    assert (retry.request_count, retry.error_class, delegate.calls) == (0, "SpendScopeBlocked", 1)


def test_the_reported_liability_is_this_attempts_reservation_not_the_ledger_total(ledger: SpendLedger) -> None:
    guarded, _ = runner(ledger, returned(), returned(status="UNKNOWN", text=None, usage=Usage(), request_count=None))
    guarded.run_turn(turn("attempt-1"))
    other = GuardedTurnRunner(Delegate(ledger, returned(status="UNKNOWN", text=None, usage=Usage(), request_count=None)),
                              ledger, POLICY, scope_for=lambda t: "case-b")

    result = other.run_turn(turn("attempt-2"))

    assert result.observed["spend_charge_usd"] == "0.04532" and ledger.committed_usd() == Decimal("0.0074285") + RESERVATION


def test_when_no_request_was_admitted_the_reservation_is_released(ledger: SpendLedger) -> None:
    refused = returned(status="UNKNOWN", text=None, usage=Usage(), request_count=0, error_class="RuntimeError")
    guarded, _ = runner(ledger, refused)

    guarded.run_turn(turn())

    assert (ledger.state("attempt-1"), ledger.committed_usd()) == ("RELEASED", Decimal("0"))


def test_a_zero_request_count_that_the_guard_contradicts_keeps_liability(ledger: SpendLedger) -> None:
    contradicted = returned(status="UNKNOWN", text=None, usage=Usage(), request_count=0, error_class="RuntimeError",
                            observed={"guard_admitted": 1})
    guarded, _ = runner(ledger, contradicted)

    guarded.run_turn(turn())

    assert (ledger.state("attempt-1"), ledger.committed_usd()) == ("UNKNOWN", RESERVATION)


def test_a_failure_of_the_boundary_keeps_liability_and_still_raises(ledger: SpendLedger) -> None:
    guarded, _ = runner(ledger, OSError("pipe broke"))

    with pytest.raises(OSError):
        guarded.run_turn(turn())

    assert (ledger.state("attempt-1"), ledger.committed_usd()) == ("UNKNOWN", RESERVATION)


def test_a_restart_with_the_same_attempt_identifier_cannot_spend_it_again(tmp_path: Path, ledger: SpendLedger) -> None:
    first, _ = runner(ledger, returned())
    first.run_turn(turn())
    reopened = SpendLedger(tmp_path / "spend.sqlite", cap_usd=CAP, price=PRICE)
    second, delegate = runner(reopened, returned())

    result = second.run_turn(turn())

    assert (result.request_count, result.error_class, delegate.calls) == (0, "ReservationExists", 0)
    assert reopened.committed_usd() == Decimal("0.0074285")


def test_a_ledger_that_cannot_record_stops_the_request_before_it_starts(tmp_path: Path, ledger: SpendLedger) -> None:
    (tmp_path / "spend.sqlite").chmod(0o444)
    try:
        guarded, delegate = runner(ledger, returned())
        result = guarded.run_turn(turn())
    finally:
        (tmp_path / "spend.sqlite").chmod(0o644)

    assert (result.request_count, result.error_class, delegate.calls) == (0, "SpendLedgerUnavailable", 0)


def test_an_interrupted_settlement_still_returns_the_result_and_keeps_the_liability(tmp_path: Path, ledger: SpendLedger) -> None:
    path = tmp_path / "spend.sqlite"

    class ReadOnlyAfterRun(Delegate):
        def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
            result = super().run_turn(turn)
            path.chmod(0o444)  # the disk fails after the provider answered and before the settlement is written
            return result

    delegate = ReadOnlyAfterRun(ledger, returned())
    guarded = GuardedTurnRunner(delegate, ledger, POLICY, scope_for=lambda t: "case-a")
    try:
        result = guarded.run_turn(turn())
    finally:
        path.chmod(0o644)

    assert result.status == "RETURNED" and result.observed["spend_state"] == "SETTLEMENT_NOT_RECORDED"
    assert (ledger.state("attempt-1"), ledger.committed_usd()) == ("RESERVED", RESERVATION)


def test_concurrent_turns_start_only_as_many_requests_as_the_cap_allows(ledger: SpendLedger) -> None:
    lock, started = threading.Lock(), []

    class Counting:
        def run_turn(self, t: HermesTurn) -> HermesTurnResult:
            with lock:
                started.append(t.attempt_id)
            return returned()

    guarded = GuardedTurnRunner(Counting(), ledger, POLICY, scope_for=lambda t: t.attempt_id)
    results: list[HermesTurnResult] = []

    def go(index: int) -> None:
        outcome = guarded.run_turn(turn(f"attempt-{index}"))
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=go, args=(index,)) for index in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    # settled turns free their unused reservation, so more than two may run one after another, but never beyond the cap
    assert len(started) == sum(1 for r in results if r.request_count == 1)
    assert ledger.committed_usd() <= CAP
    assert all(r.error_class in (None, "SpendCapReached") for r in results)
