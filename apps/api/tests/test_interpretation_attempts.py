"""Rules of the interpretation attempt ledger, tested through its public interface.

The store behind it is a dumb append-only list, so every rule under test lives in the ledger. The same tests can run
against the PostgreSQL store later by swapping `MemoryAttemptStore`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
from collections.abc import Mapping, Sequence

import pytest

from edge_os_api.interpretation_attempts import (
    AlreadyLinked, AlreadySettled, AttemptIdentity, AttemptInFlight, AttemptLedger, AttemptSettlement, AttemptStart,
    InvalidIdentity, InvalidSettlement, NotPublishable, RetryTargetInvalid, UnknownAttempt, Usage,
)

OWNER, OTHER_OWNER = "owner-a", "owner-b"
INTAKE, OTHER_INTAKE = "intake-1", "intake-2"
CONFIG = {"model": "fixture-model/1", "max_output_tokens": 4096, "route": "local-fake"}
CONFIG_SHA256 = "8a097034b61dbb688a2f7017bbd08ff3daa1c12c4f2286265c44874b00030ab3"  # sha256 of the sorted compact JSON
TASK_TEXT = '{"task":"interpret","original_request":"Buy when price is up 1%"}'
TASK_SHA256 = hashlib.sha256(TASK_TEXT.encode()).hexdigest()
IDENTITY = AttemptIdentity(
    purpose="INTERPRET", prompt_version="prompt/1", system_prompt_sha256="a" * 64, task_sha256=TASK_SHA256,
    task_text=TASK_TEXT, response_shape_sha256="c" * 64, manifest_sha256="d" * 64, config=CONFIG,
    runtime_label="LOCAL_FAKE_PROVIDER")
START_TIME = dt.datetime(2026, 10, 9, 12, 0, 0, tzinfo=dt.timezone.utc)
RESPONSE_TEXT = '{"meaning_status": "SUPPORTED"}'


class MemoryAttemptStore:
    """Append-only lists keyed by owner. It enforces nothing, so a passing rule test proves the ledger's rule."""

    def __init__(self) -> None:
        self._starts: list[AttemptStart] = []
        self._settlements: list[AttemptSettlement] = []
        self._links: list[tuple[str, str, str]] = []

    def add_start(self, start: AttemptStart) -> None:
        self._starts.append(start)

    def add_settlement(self, settlement: AttemptSettlement) -> None:
        self._settlements.append(settlement)

    def add_link(self, owner_id: str, attempt_id: str, revision_id: str) -> None:
        self._links.append((owner_id, attempt_id, revision_id))

    def find_start(self, owner_id: str, attempt_id: str) -> AttemptStart | None:
        return next((s for s in self._starts if s.owner_id == owner_id and s.attempt_id == attempt_id), None)

    def starts(self, owner_id: str, intake_record_id: str) -> Sequence[AttemptStart]:
        return [s for s in self._starts if s.owner_id == owner_id and s.intake_record_id == intake_record_id]

    def settlements(self, owner_id: str, intake_record_id: str) -> Sequence[AttemptSettlement]:
        ids = {s.attempt_id for s in self.starts(owner_id, intake_record_id)}
        return [s for s in self._settlements if s.owner_id == owner_id and s.attempt_id in ids]

    def links(self, owner_id: str, intake_record_id: str) -> Mapping[str, str]:
        ids = {s.attempt_id for s in self.starts(owner_id, intake_record_id)}
        return {a: r for o, a, r in self._links if o == owner_id and a in ids}


@pytest.fixture
def clock() -> dt.datetime:
    return START_TIME


@pytest.fixture
def ledger() -> AttemptLedger:
    counter = itertools.count(1)
    ticks = itertools.count(0)
    return AttemptLedger(MemoryAttemptStore(), new_id=lambda: f"attempt-{next(counter)}",
                         now=lambda: START_TIME + dt.timedelta(seconds=next(ticks)))


def settlement(attempt_id: str, status: str = "COMPLETED", *, owner: str = OWNER, usage: Usage | None = None,
               text: str | None = RESPONSE_TEXT, parse_result: str = "ACCEPTED", latency_ms: int | None = 1500,
               error_class: str | None = None, response_sha256: str | None = "default") -> AttemptSettlement:
    if response_sha256 == "default":
        response_sha256 = hashlib.sha256(text.encode()).hexdigest() if text is not None else None
    return AttemptSettlement(
        attempt_id=attempt_id, owner_id=owner, status=status, finished_at=START_TIME + dt.timedelta(minutes=1),
        latency_ms=latency_ms, usage=usage or Usage(), request_count=1, response_sha256=response_sha256,
        response_text=text, parse_result=parse_result, error_class=error_class)


def test_the_first_attempt_records_its_identity_sequence_and_configuration_hash(ledger: AttemptLedger) -> None:
    start = ledger.begin(OWNER, INTAKE, IDENTITY)

    assert (start.attempt_id, start.sequence, start.retry_of) == ("attempt-1", 1, None)
    assert start.started_at == START_TIME
    assert start.config_sha256 == CONFIG_SHA256
    assert start.identity == IDENTITY
    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.status, view.completion, view.settlement) == ("STARTED", "UNKNOWN", None)


def test_the_exact_request_text_and_the_users_reply_reference_are_kept_with_the_attempt(ledger: AttemptLedger) -> None:
    follow_up = AttemptIdentity(
        purpose="FOLLOW_UP", prompt_version="prompt/1", system_prompt_sha256="a" * 64, task_sha256=TASK_SHA256,
        task_text=TASK_TEXT, response_shape_sha256="c" * 64, manifest_sha256="d" * 64, config=CONFIG,
        runtime_label="LOCAL_FAKE_PROVIDER", answer_ref="answer:11111111-1111-4111-8111-111111111111")
    start = ledger.begin(OWNER, INTAKE, follow_up)

    saved = ledger.history(OWNER, INTAKE)[0].start
    assert saved == start
    assert (saved.identity.task_text, saved.identity.answer_ref) == (TASK_TEXT, "answer:11111111-1111-4111-8111-111111111111")
    assert ledger.history(OWNER, INTAKE)[0].start.identity.task_sha256 == TASK_SHA256


def test_a_request_hash_that_does_not_match_the_saved_text_is_refused_and_nothing_is_recorded(
        ledger: AttemptLedger) -> None:
    forged = AttemptIdentity(
        purpose="INTERPRET", prompt_version="prompt/1", system_prompt_sha256="a" * 64, task_sha256="b" * 64,
        task_text=TASK_TEXT, response_shape_sha256="c" * 64, manifest_sha256="d" * 64, config=CONFIG,
        runtime_label="LOCAL_FAKE_PROVIDER")
    with pytest.raises(InvalidIdentity):
        ledger.begin(OWNER, INTAKE, forged)
    assert ledger.history(OWNER, INTAKE) == []


def test_a_second_attempt_cannot_begin_while_the_first_has_not_settled(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    with pytest.raises(AttemptInFlight):
        ledger.begin(OWNER, INTAKE, IDENTITY)
    assert len(ledger.history(OWNER, INTAKE)) == 1


def test_a_settled_attempt_keeps_status_completion_latency_and_unknown_usage(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1"))

    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.status, view.completion) == ("COMPLETED", "COMPLETE")
    assert view.settlement is not None
    assert view.settlement.latency_ms == 1500
    assert (view.settlement.usage.input_tokens, view.settlement.usage.output_tokens) == (None, None)  # unknown, not 0
    assert view.settlement.usage.source == "UNKNOWN"


@pytest.mark.parametrize("status, completion", [
    ("COMPLETED", "COMPLETE"), ("TRUNCATED", "TRUNCATED"), ("PROVIDER_FAILED", "NONE"), ("TIMED_OUT", "UNKNOWN"),
    ("INTERRUPTED", "UNKNOWN"), ("UNKNOWN", "UNKNOWN"),
])
def test_each_settled_status_reports_what_is_known_about_completion(ledger: AttemptLedger, status: str,
                                                                    completion: str) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    text = RESPONSE_TEXT if status in {"COMPLETED", "TRUNCATED"} else None
    parse_result = {"COMPLETED": "ACCEPTED", "TRUNCATED": "REJECTED:truncated"}.get(status, "NOT_PARSED")
    ledger.settle(settlement("attempt-1", status, text=text, parse_result=parse_result))
    assert ledger.history(OWNER, INTAKE)[0].completion == completion


def test_a_retry_is_a_new_attempt_that_names_the_failed_one_and_the_failure_stays(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1", "PROVIDER_FAILED", text=None, parse_result="NOT_PARSED",
                             error_class="ProviderHTTPError"))
    retry = ledger.begin(OWNER, INTAKE, IDENTITY, retry_of="attempt-1")
    ledger.settle(settlement("attempt-2"))

    history = ledger.history(OWNER, INTAKE)
    assert [(v.start.attempt_id, v.start.sequence, v.start.retry_of, v.status) for v in history] == [
        ("attempt-1", 1, None, "PROVIDER_FAILED"), ("attempt-2", 2, "attempt-1", "COMPLETED")]
    assert retry.sequence == 2
    assert history[0].settlement is not None and history[0].settlement.error_class == "ProviderHTTPError"


def test_an_uncertain_attempt_is_not_erased_by_a_retry(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1", "UNKNOWN", text=None, parse_result="NOT_PARSED"))
    ledger.begin(OWNER, INTAKE, IDENTITY, retry_of="attempt-1")

    assert [v.status for v in ledger.history(OWNER, INTAKE)] == ["UNKNOWN", "STARTED"]


@pytest.mark.parametrize("owner, intake, target", [
    pytest.param(OWNER, INTAKE, "attempt-99", id="no-such-attempt"),
    pytest.param(OWNER, OTHER_INTAKE, "attempt-1", id="attempt-of-another-request"),
    pytest.param(OTHER_OWNER, INTAKE, "attempt-1", id="attempt-of-another-owner"),
])
def test_a_retry_must_name_an_attempt_of_the_same_owner_and_request(ledger: AttemptLedger, owner: str, intake: str,
                                                                    target: str) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1"))
    with pytest.raises(RetryTargetInvalid):
        ledger.begin(owner, intake, IDENTITY, retry_of=target)


def test_an_attempt_settles_once_and_the_first_result_stays(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1", "PROVIDER_FAILED", text=None, parse_result="NOT_PARSED"))
    with pytest.raises(AlreadySettled):
        ledger.settle(settlement("attempt-1", "COMPLETED"))
    assert ledger.history(OWNER, INTAKE)[0].status == "PROVIDER_FAILED"


@pytest.mark.parametrize("owner, attempt_id", [(OWNER, "attempt-99"), (OTHER_OWNER, "attempt-1")])
def test_settling_an_unknown_or_foreign_attempt_is_refused(ledger: AttemptLedger, owner: str, attempt_id: str) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    with pytest.raises(UnknownAttempt):
        ledger.settle(settlement(attempt_id, owner=owner))
    assert ledger.history(OWNER, INTAKE)[0].status == "STARTED"


@pytest.mark.parametrize("changes", [
    pytest.param({"status": "DONE"}, id="status-not-defined"),
    pytest.param({"status": "COMPLETED", "text": None}, id="completed-without-text"),
    pytest.param({"status": "COMPLETED", "response_sha256": "0" * 64}, id="hash-does-not-match-text"),
    pytest.param({"status": "PROVIDER_FAILED"}, id="failed-attempt-claims-a-response"),
    pytest.param({"status": "COMPLETED", "latency_ms": -1}, id="negative-latency"),
    pytest.param({"status": "TRUNCATED", "parse_result": "ACCEPTED"}, id="truncated-response-marked-accepted"),
    pytest.param({"status": "PROVIDER_FAILED", "text": None, "parse_result": "ACCEPTED"}, id="failure-marked-accepted"),
    pytest.param({"status": "COMPLETED", "parse_result": "NOT_PARSED"}, id="completed-response-never-examined"),
    pytest.param({"status": "COMPLETED", "usage": Usage(input_tokens=-5, output_tokens=2, source="PROVIDER_REPORTED")},
                 id="negative-usage"),
    pytest.param({"status": "COMPLETED", "usage": Usage(input_tokens=None, output_tokens=None, source="PROVIDER_REPORTED")},
                 id="usage-claims-a-report-but-has-no-numbers"),
])
def test_a_settlement_that_contradicts_itself_is_refused_and_the_attempt_stays_open(ledger: AttemptLedger,
                                                                                    changes: dict) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    status = changes.pop("status")
    with pytest.raises(InvalidSettlement):
        ledger.settle(settlement("attempt-1", status, **changes))
    assert ledger.history(OWNER, INTAKE)[0].status == "STARTED"


def test_a_restart_closes_the_unsettled_attempt_as_interrupted_with_unknown_usage_and_never_replays_it(
        ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)

    closed = ledger.interrupt_unsettled(OWNER, INTAKE)
    again = ledger.interrupt_unsettled(OWNER, INTAKE)

    assert [v.start.attempt_id for v in closed] == ["attempt-1"]
    assert again == []
    view = ledger.history(OWNER, INTAKE)[0]
    assert (view.status, view.completion) == ("INTERRUPTED", "UNKNOWN")
    assert view.settlement is not None
    assert view.settlement.usage == Usage()
    assert view.settlement.parse_result == "NOT_PARSED"
    assert len(ledger.history(OWNER, INTAKE)) == 1  # closing created no second attempt
    ledger.begin(OWNER, INTAKE, IDENTITY, retry_of="attempt-1")  # a deliberate retry is now allowed


def test_closing_interrupted_attempts_leaves_settled_ones_alone(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1"))
    ledger.begin(OWNER, INTAKE, IDENTITY, retry_of="attempt-1")

    ledger.interrupt_unsettled(OWNER, INTAKE)
    assert [v.status for v in ledger.history(OWNER, INTAKE)] == ["COMPLETED", "INTERRUPTED"]


def test_history_is_private_to_the_owner(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    assert ledger.history(OTHER_OWNER, INTAKE) == []
    assert ledger.interrupt_unsettled(OTHER_OWNER, INTAKE) == []
    assert ledger.history(OWNER, INTAKE)[0].status == "STARTED"


def test_an_accepted_result_can_be_recovered_without_a_new_attempt_until_it_is_linked(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1"))

    waiting = ledger.unpublished_results(OWNER, INTAKE)
    assert [v.start.attempt_id for v in waiting] == ["attempt-1"]
    assert waiting[0].settlement is not None and waiting[0].settlement.response_text == RESPONSE_TEXT

    ledger.link_revision(OWNER, "attempt-1", "revision-1")
    assert ledger.unpublished_results(OWNER, INTAKE) == []
    assert ledger.history(OWNER, INTAKE)[0].revision_id == "revision-1"
    assert len(ledger.history(OWNER, INTAKE)) == 1


def test_an_attempt_links_to_one_revision_only(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1"))
    ledger.link_revision(OWNER, "attempt-1", "revision-1")
    with pytest.raises(AlreadyLinked):
        ledger.link_revision(OWNER, "attempt-1", "revision-2")
    assert ledger.history(OWNER, INTAKE)[0].revision_id == "revision-1"


@pytest.mark.parametrize("status, parse_result, text", [
    ("COMPLETED", "REJECTED:multiple_objects", RESPONSE_TEXT),
    ("TRUNCATED", "REJECTED:truncated", RESPONSE_TEXT),
    ("PROVIDER_FAILED", "NOT_PARSED", None),
    ("INTERRUPTED", "NOT_PARSED", None),
])
def test_only_a_completed_and_accepted_attempt_can_link_to_a_revision(ledger: AttemptLedger, status: str,
                                                                      parse_result: str, text: str | None) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    ledger.settle(settlement("attempt-1", status, text=text, parse_result=parse_result))
    with pytest.raises(NotPublishable):
        ledger.link_revision(OWNER, "attempt-1", "revision-1")
    assert ledger.unpublished_results(OWNER, INTAKE) == []


def test_linking_an_unsettled_unknown_or_foreign_attempt_is_refused(ledger: AttemptLedger) -> None:
    ledger.begin(OWNER, INTAKE, IDENTITY)
    with pytest.raises(NotPublishable):
        ledger.link_revision(OWNER, "attempt-1", "revision-1")  # still in flight
    with pytest.raises(UnknownAttempt):
        ledger.link_revision(OWNER, "attempt-99", "revision-1")
    with pytest.raises(UnknownAttempt):
        ledger.link_revision(OTHER_OWNER, "attempt-1", "revision-1")
