"""The host contract of the transport job, without a container: construction, the ACTUAL route and identity checks.

The container boundary is the only stand-in (`ReportingJob` plays what a job reports). The guard runner, the spend ledger
and the identity check are the real ones.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage
from guarded_turn_runner import GuardedTurnRunner
from provider_guard import GuardPolicy
from provider_transport import ActualProviderUnavailable, TransportRoute
from spend_ledger import SpendLedger, TokenPrice
from transport_turn_runner import TransportTurnRunner, build_transport_job

POLICY = GuardPolicy(model="m", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500)
ROUTE = TransportRoute("authored-local-1", "AUTHORED", "https://authored-transport.invalid/v1/chat/completions", 65_536)
TURN = HermesTurn("attempt-1", "prompt", "task", "m", "route", 4096)
RESERVATION = Decimal("0.054848")
REPORTED = Usage(100, 10, 110, "PROVIDER_REPORTED")


class ReportingJob:
    """Stands in for the container: returns what a job reported for the turn."""

    def __init__(self, **observed: Any) -> None:
        self.observed = observed

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        return HermesTurnResult("RETURNED", "{}", REPORTED, 1, {"guard_admitted": 1, **self.observed})


def own_report(**changes: Any) -> dict[str, Any]:
    return {"transport_attempt_id": "attempt-1", "transport_route_id": ROUTE.route_id, "transport_sent": 1,
            "transport_request_attempt_ids": ["attempt-1"]} | changes


def guarded(tmp_path: Path, job: Any, ledger: Any = None) -> tuple[GuardedTurnRunner, SpendLedger]:
    spend = ledger or SpendLedger(tmp_path / "spend.sqlite", cap_usd=Decimal("0.20"), price=TokenPrice(Decimal("2.00"), Decimal("7.50")))
    return GuardedTurnRunner(TransportTurnRunner(job, ROUTE), spend, POLICY, scope_for=lambda turn: "case-a"), spend


def build(tmp_path: Path, route: TransportRoute = ROUTE, ledger: Any = None):
    return build_transport_job(route, policy=POLICY, ledger=ledger, scope_for=lambda turn: "case-a", image="unused",
                               run_id="contract", evidence_dir=tmp_path / "evidence", script_for=lambda turn: {},
                               credential_file=tmp_path / "no-such-credential")


def test_building_the_job_reads_and_writes_nothing(tmp_path: Path) -> None:
    job = build(tmp_path)

    assert list(tmp_path.iterdir()) == []  # no evidence folder, no credential read (the file does not even exist)
    assert job.supervision.job_entry.script == "/opt/p05job/transport_turn_job.py"


def test_an_actual_provider_route_is_refused_before_anything_is_built(tmp_path: Path) -> None:
    actual = TransportRoute("provider-x", "ACTUAL", "https://api.provider.example/v1/chat/completions", 65_536)

    with pytest.raises(ActualProviderUnavailable):
        build(tmp_path, actual)
    assert list(tmp_path.iterdir()) == []


def test_a_report_that_names_this_attempt_and_route_is_used_and_charged_exactly(tmp_path: Path) -> None:
    runner, spend = guarded(tmp_path, ReportingJob(**own_report()))

    result = runner.run_turn(TURN)

    assert (result.status, result.text, result.observed["spend_state"]) == ("RETURNED", "{}", "SETTLED")
    assert spend.committed_usd() == Decimal("0.000275")  # 100 x 2.00 / 1e6 + 10 x 7.50 / 1e6


@pytest.mark.parametrize("report", [
    own_report(transport_attempt_id="attempt-2"),  # another attempt's job
    own_report(transport_request_attempt_ids=["attempt-2"]),  # the request it sent named another attempt
    own_report(transport_request_attempt_ids=["attempt-1", "attempt-1"], transport_sent=2),  # more than one request
    own_report(transport_route_id="another-route"),
    own_report(transport_sent=0),  # the count disagrees with the requests it lists
    {},  # a job that reports a result and no transport at all
])
def test_a_report_that_does_not_match_this_attempt_is_withheld_and_keeps_the_full_reservation(tmp_path: Path, report) -> None:
    runner, spend = guarded(tmp_path, ReportingJob(**report))

    result = runner.run_turn(TURN)

    assert (result.status, result.text, result.error_class) == ("UNKNOWN", None, "TransportIdentityMismatch")
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("UNKNOWN", RESERVATION)


def test_a_turn_that_never_started_a_job_passes_through_and_frees_its_reservation(tmp_path: Path) -> None:
    class NeverStarted:
        def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
            return HermesTurnResult("PROVIDER_FAILED", None, Usage(), 0, {"guard_admitted": 0}, "CleanupPending")

    runner, spend = guarded(tmp_path, NeverStarted())

    result = runner.run_turn(TURN)

    assert result.error_class == "CleanupPending" and spend.state("attempt-1") == "RELEASED"


def test_a_settlement_that_cannot_be_recorded_keeps_the_result_and_the_liability(tmp_path: Path) -> None:
    class FailingSettle(SpendLedger):
        def settle(self, *args: Any, **kwargs: Any) -> Any:
            raise OSError("disk full")

    spend = FailingSettle(tmp_path / "spend.sqlite", cap_usd=Decimal("0.20"), price=TokenPrice(Decimal("2.00"), Decimal("7.50")))
    runner, _ = guarded(tmp_path, ReportingJob(**own_report()), spend)

    result = runner.run_turn(TURN)

    assert result.observed["spend_state"] == "SETTLEMENT_NOT_RECORDED"
    assert (spend.state("attempt-1"), spend.committed_usd()) == ("RESERVED", RESERVATION)
