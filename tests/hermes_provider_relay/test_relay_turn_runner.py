"""The host turn runner: no grant without a reservation, a proved owner and a live relay; the relay's own record limits
what the job may claim. A fake job stands in for the container, and the relay's records are written as the relay would.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage
from provider_transport import ActualProviderUnavailable, TransportRoute
from relay_admission import RelayRelease, RelaySubject, grant_refusal
from relay_harness import POLICY, PRICE, RELEASE, ROUTE
from relay_turn_runner import RelayEndpoint, build_relay_job
from spend_ledger import SpendLedger

TURN = HermesTurn("att-1", "system prompt", "user task", POLICY.model, "relay", POLICY.max_output_tokens)
USAGE = Usage(1423, 611, 2034, "PROVIDER_REPORTED")


def counted(**changes: Any) -> HermesTurnResult:
    observed = {"guard_admitted": 1, "transport_attempt_id": "att-1", "transport_route_id": ROUTE.route_id,
                "transport_sent": 1, "transport_request_attempt_ids": ["att-1"]}
    fields = dict(status="RETURNED", text="{}", usage=USAGE, request_count=1, observed=observed, error_class=None)
    return HermesTurnResult(**{**fields, **changes})


def unsent(**changes: Any) -> HermesTurnResult:
    observed = {"guard_admitted": 0, "transport_attempt_id": "att-1", "transport_route_id": ROUTE.route_id,
                "transport_sent": 0, "transport_request_attempt_ids": []}
    fields = dict(status="UNKNOWN", text=None, usage=Usage(), request_count=0, observed=observed, error_class="BadRequest")
    return HermesTurnResult(**{**fields, **changes})


class Relay:
    """Folders and a heartbeat as the relay keeps them."""

    def __init__(self, root: Path) -> None:
        self.endpoint = RelayEndpoint(root / "grants", root / "revocations", root / "state", root / "admission-key", "jobs")
        for folder in ("grants", "revocations", "state"):
            (root / folder).mkdir(parents=True)
        (root / "admission-key").write_bytes(b"a" * 32)
        self.beat()

    def beat(self, release: RelayRelease = RELEASE, at: float | None = None) -> None:
        (self.endpoint.state / "heartbeat.json").write_text(json.dumps({"release": release.settings(),
                                                                       "at": at or time.time(), "started_at": 0}))

    def records(self, attempt: str, *, started: bool, finished: dict[str, Any] | None = None) -> None:
        folder = self.endpoint.state / attempt
        folder.mkdir(exist_ok=True)
        (folder / "closed.json").write_text(json.dumps({"started": started}))
        if finished is not None:
            (folder / "finished.json").write_text(json.dumps(finished))


class Rig:
    def __init__(self, tmp_path: Path, result: Any, *, records: dict[str, Any] | None = None,
                 subject: Any = RelaySubject("owner-a", "intake-1")) -> None:
        self.relay = Relay(tmp_path / "relay")
        self.spend = SpendLedger(tmp_path / "spend.sqlite", cap_usd=Decimal("0.20"), price=PRICE)
        self.calls = 0

        def subject_for(turn: HermesTurn) -> RelaySubject:
            if isinstance(subject, Exception):
                raise subject
            return subject

        self.job = build_relay_job(ROUTE, release=RELEASE, endpoint=self.relay.endpoint, subject_for=subject_for,
                                   policy=POLICY, ledger=self.spend, scope_for=lambda turn: "scope-1",
                                   image="unused", run_id="run-1", evidence_dir=tmp_path / "jobs",
                                   script_for=lambda turn: {}, close_budget_seconds=0.3)

        def run_turn(turn: HermesTurn) -> HermesTurnResult:  # the job: it ran, and the relay recorded what it did
            self.calls += 1
            if records is not None:
                self.relay.records(turn.attempt_id, **records)
            if isinstance(result, BaseException):
                raise result
            return result

        self.job.supervision.run_turn = run_turn  # type: ignore[method-assign]

    def grant(self) -> dict[str, Any]:
        return json.loads((self.relay.endpoint.grants / "att-1.json").read_text())


def test_construction_does_no_io_and_refuses_an_actual_route_or_a_mismatched_release(tmp_path: Path) -> None:
    common = dict(endpoint=RelayEndpoint(*(tmp_path / n for n in ("g", "r", "s", "k")), "jobs"),
                  subject_for=lambda t: None, policy=POLICY, ledger=None, scope_for=lambda t: "", image="i",
                  run_id="r", evidence_dir=tmp_path / "e", script_for=lambda t: {})
    build_relay_job(ROUTE, release=RELEASE, **common)
    assert list(tmp_path.iterdir()) == []  # nothing was created or read
    actual = TransportRoute(ROUTE.route_id, "ACTUAL", ROUTE.endpoint_url, ROUTE.max_reply_bytes)
    with pytest.raises(ActualProviderUnavailable):
        build_relay_job(actual, release=RELEASE, **common)  # with a release
    with pytest.raises(ValueError):
        RelayRelease("r", ROUTE.route_id, "ACTUAL", POLICY.model, 4096, 12_000, 65_536)  # no ACTUAL release can exist
    other = RelayRelease("local-relay-1", ROUTE.route_id, "AUTHORED", "other-model", 4096, 12_000, 65_536)
    with pytest.raises(ValueError):
        build_relay_job(ROUTE, release=other, **common)
    with pytest.raises(ValueError):
        build_relay_job(ROUTE, release=RELEASE, close_budget_seconds=float("nan"), **common)


def test_a_counted_request_the_relay_started_and_answered_with_the_same_usage_is_settled_exactly(tmp_path) -> None:
    rig = Rig(tmp_path, counted(), records={"started": True, "finished": {
        "outcome": "reply", "status": 200, "usage": {"prompt_tokens": 1423, "completion_tokens": 611,
                                                     "total_tokens": 2034}}})

    result = rig.job.runner.run_turn(TURN)

    assert result.status == "RETURNED" and result.observed["spend_state"] == "SETTLED"
    assert (result.observed["relay_started"], result.observed["relay_outcome"]) == (True, "reply")
    grant = rig.grant()
    assert (grant["owner_id"], grant["request_id"], grant["attempt_id"], grant["scope"]) == ("owner-a", "intake-1", "att-1", "scope-1")
    assert grant_refusal(grant, b"a" * 32, RELEASE, now=time.time()) is None
    assert (rig.relay.endpoint.revocations / "att-1.json").exists()  # closed after the job


def test_a_zero_request_result_is_released_only_when_the_relay_recorded_it_closed_and_never_started(tmp_path) -> None:
    rig = Rig(tmp_path, unsent(), records={"started": False})
    result = rig.job.runner.run_turn(TURN)
    assert result.request_count == 0 and result.observed["spend_state"] == "RELEASED"
    assert rig.spend.committed_usd() == 0


@pytest.mark.parametrize("records, result", [
    ({"started": True, "finished": {"outcome": "reply", "usage": None}}, unsent()),  # the job hid a request
    ({"started": False}, counted()),  # the job claims a request the relay never made
    ({"started": True, "finished": {"outcome": "reply", "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                                                   "total_tokens": 2}}}, counted()),  # other usage
    ({"started": True, "finished": {"outcome": "lost"}}, counted()),  # the relay lost what the job claims it got
    ({"started": True, "finished": {"outcome": "reply", "status": 500, "usage": {
        "prompt_tokens": 1423, "completion_tokens": 611, "total_tokens": 2034}}}, counted()),  # a provider error
    ({"started": True, "finished": {"outcome": "reply", "status": 429, "usage": {
        "prompt_tokens": 1423, "completion_tokens": 611, "total_tokens": 2034}}}, counted()),
    ({"started": True, "finished": {"outcome": "reply", "usage": {
        "prompt_tokens": 1423, "completion_tokens": 611, "total_tokens": 2034}}}, counted()),  # no status recorded
    (None, unsent()),  # the relay never confirmed a close
    (None, counted()),
])
def test_a_job_report_the_relay_record_does_not_support_is_withheld_and_holds_the_full_reservation(
        tmp_path, records, result) -> None:
    rig = Rig(tmp_path, result, records=records)
    saved = rig.job.runner.run_turn(TURN)
    assert saved.status == "UNKNOWN" and saved.request_count is None and saved.text is None
    assert saved.error_class in ("RelayCountMismatch", "RelayStateUnknown")
    assert saved.observed["spend_state"] == "UNKNOWN" and rig.spend.committed_usd() == Decimal("0.054848")


def test_a_lost_reply_the_relay_started_keeps_the_liability(tmp_path) -> None:
    rig = Rig(tmp_path, counted(status="UNKNOWN", text=None, usage=Usage(), error_class="ReadError"),
              records={"started": True, "finished": {"outcome": "lost"}})
    saved = rig.job.runner.run_turn(TURN)
    assert saved.observed["spend_state"] == "UNKNOWN" and rig.spend.state("att-1") == "UNKNOWN"


@pytest.mark.parametrize("prepare, error_class", [
    (lambda rig: rig.relay.beat(at=time.time() - 30), "RelayUnavailable"),  # a stale heartbeat
    (lambda rig: rig.relay.beat(release=RelayRelease("local-relay-9", ROUTE.route_id, "AUTHORED", POLICY.model, 4096,
                                                     12_000, 65_536)), "RelayUnavailable"),
    (lambda rig: (rig.relay.endpoint.state / "heartbeat.json").unlink(), "RelayUnavailable"),
    (lambda rig: rig.relay.endpoint.admission_key_file.unlink(), "RelayUnavailable"),
])
def test_without_a_live_relay_for_this_release_no_grant_is_issued_no_job_runs_and_the_reservation_is_released(
        tmp_path, prepare, error_class) -> None:
    rig = Rig(tmp_path, counted())
    prepare(rig)
    result = rig.job.runner.run_turn(TURN)
    assert (result.error_class, result.request_count, rig.calls) == (error_class, 0, 0)
    assert not (rig.relay.endpoint.grants / "att-1.json").exists() and rig.spend.state("att-1") == "RELEASED"


def test_an_owner_or_request_that_cannot_be_proved_gets_no_grant(tmp_path) -> None:
    rig = Rig(tmp_path, counted(), subject=LookupError("no saved attempt"))
    result = rig.job.runner.run_turn(TURN)
    assert (result.error_class, rig.calls) == ("RelaySubjectUnavailable", 0) and rig.spend.state("att-1") == "RELEASED"


def test_without_a_recorded_reservation_no_grant_is_issued(tmp_path) -> None:
    rig = Rig(tmp_path, counted())
    relay_runner = rig.job.runner._delegate  # the relay step alone, with nothing reserved
    result = relay_runner.run_turn(TURN)
    assert (result.error_class, result.request_count, rig.calls) == ("RelayReservationMissing", 0, 0)
    assert not (rig.relay.endpoint.grants / "att-1.json").exists()


def test_an_existing_grant_is_never_replaced_and_its_attempt_is_held_as_unknown(tmp_path) -> None:
    rig = Rig(tmp_path, counted())
    (rig.relay.endpoint.grants / "att-1.json").write_text('{"earlier": true}')
    result = rig.job.runner.run_turn(TURN)
    assert (result.status, result.error_class, rig.calls) == ("UNKNOWN", "RelayGrantExists", 0)
    assert json.loads((rig.relay.endpoint.grants / "att-1.json").read_text()) == {"earlier": True}
    assert rig.spend.state("att-1") == "UNKNOWN"


def test_a_job_that_raises_still_revokes_its_grant_and_keeps_the_liability(tmp_path) -> None:
    rig = Rig(tmp_path, KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        rig.job.runner.run_turn(TURN)
    assert (rig.relay.endpoint.revocations / "att-1.json").exists() and rig.spend.state("att-1") == "UNKNOWN"


def test_the_grant_expires_no_later_than_the_job_timeout(tmp_path) -> None:
    rig = Rig(tmp_path, unsent(), records={"started": False})
    before = time.time()
    rig.job.runner.run_turn(TURN)
    grant = rig.grant()
    assert before <= grant["issued_at"] and grant["expires_at"] - grant["issued_at"] == 90


def test_a_relay_clock_slightly_ahead_of_the_host_still_counts_as_live(tmp_path) -> None:
    rig = Rig(tmp_path, unsent(), records={"started": False})
    rig.relay.beat(at=time.time() + 1.0)  # within the grant clock allowance
    result = rig.job.runner.run_turn(TURN)
    assert result.error_class != "RelayUnavailable" and rig.calls == 1
