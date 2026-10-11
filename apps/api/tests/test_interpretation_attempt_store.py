"""The attempt ledger on PostgreSQL: the same rules, plus what only the database can guarantee.

Seam: `AttemptLedger` over `PostgresAttemptStore`, a real migrated database, and `AdvisoryLockGuard`. Raw SQL appears only
to prove append-only storage and constraints that a caller cannot reach through the ledger.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from conftest import run_threads
from flows import submit

from edge_os_api.research.attempt_store import AdvisoryLockGuard, PostgresAttemptStore
from edge_os_api.research.interpretation_attempts import (
    AlreadyLinked, AttemptIdentity, AttemptInFlight, AttemptLedger, AttemptSettlement, LateResult, NotPublishable,
    NotUncertain, UnknownAttempt, Usage,
)

TASK = '{"task":"interpret","original_request":"Buy when price is up 1%"}'
REPLY = "make it two percent over the last quarter hour"
CONFIG = {"model": "fixture-model/1", "max_output_tokens": 4096, "route": "local-fake"}
TEXT = '{"meaning_status": "SUPPORTED"}'
REPORTED = Usage(1200, 300, 1500, "PROVIDER_REPORTED")


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def identity(task: str = TASK, **changes) -> AttemptIdentity:
    values = dict(purpose="INTERPRET", prompt_version="prompt/1", system_prompt_sha256="a" * 64, task_sha256=sha(task),
                  task_text=task, response_shape_sha256="c" * 64, manifest_sha256="d" * 64, config=CONFIG,
                  runtime_label="LOCAL_FAKE_PROVIDER")
    values.update(changes)
    return AttemptIdentity(**values)


def settled(attempt_id: str, owner: str, status: str = "COMPLETED", text_: str | None = TEXT, **changes):
    values = dict(
        attempt_id=attempt_id, owner_id=owner, status=status,
        finished_at=dt.datetime.now(dt.timezone.utc), latency_ms=1500, usage=REPORTED, request_count=1,
        response_sha256=sha(text_) if text_ is not None else None, response_text=text_,
        parse_result="ACCEPTED" if status == "COMPLETED" and text_ else ("NOT_PARSED" if text_ is None else
                                                                          "REJECTED:truncated"),
        error_class=None, runtime_observed={"tools_effective": [], "request_count": 1})
    values.update(changes)
    return AttemptSettlement(**values)


@pytest.fixture
def store(client) -> PostgresAttemptStore:
    return PostgresAttemptStore(client.app.state.session_factory)


@pytest.fixture
def ledger(store) -> AttemptLedger:
    return AttemptLedger(store, new_id=lambda: str(uuid.uuid4()), now=lambda: dt.datetime.now(dt.timezone.utc))


@pytest.fixture
def request_of(client, owner_a):
    """(owner id, saved request id) for a fresh owner."""
    owner = client.get("/v1/me", headers=owner_a).json()["user_id"]
    created = submit(client, owner_a)
    assert created.status_code == 201, created.text
    return owner, created.json()["intake"]["record_id"]


@pytest.fixture
def other_request(client, owner_b):
    owner = client.get("/v1/me", headers=owner_b).json()["user_id"]
    return owner, submit(client, owner_b).json()["intake"]["record_id"]


def sql(client, statement: str, **params):
    with client.app.state.engine.begin() as connection:
        return connection.execute(text(statement), params)


def test_an_attempt_survives_a_new_ledger_with_every_identity_and_the_measured_values(client, request_of) -> None:
    owner, intake = request_of
    first = AttemptLedger(PostgresAttemptStore(client.app.state.session_factory), new_id=lambda: str(uuid.uuid4()),
                          now=lambda: dt.datetime.now(dt.timezone.utc))
    start = first.begin(owner, intake, identity())
    first.settle(settled(start.attempt_id, owner))

    reopened = AttemptLedger(PostgresAttemptStore(client.app.state.session_factory), new_id=lambda: "unused",
                             now=lambda: dt.datetime.now(dt.timezone.utc))
    [view] = reopened.history(owner, intake)

    assert view.start == start
    assert view.start.identity == identity()
    assert view.start.config_sha256 == hashlib.sha256(
        b'{"max_output_tokens":4096,"model":"fixture-model/1","route":"local-fake"}').hexdigest()
    assert (view.status, view.completion) == ("COMPLETED", "COMPLETE")
    assert view.settlement is not None
    assert (view.settlement.latency_ms, view.settlement.usage, view.settlement.request_count) == (1500, REPORTED, 1)
    assert (view.settlement.response_text, view.settlement.response_sha256) == (TEXT, sha(TEXT))
    assert view.settlement.runtime_observed == {"tools_effective": [], "request_count": 1}


def test_unknown_usage_is_stored_as_unknown_and_never_as_zero(client, ledger, request_of) -> None:
    owner, intake = request_of
    start = ledger.begin(owner, intake, identity())
    ledger.settle(settled(start.attempt_id, owner, "TIMED_OUT", None, usage=Usage(), latency_ms=None, request_count=None))

    [view] = ledger.history(owner, intake)
    assert view.settlement is not None and view.settlement.usage == Usage()
    row = sql(client, "select input_tokens, output_tokens, total_tokens, usage_source, latency_ms, request_count "
                      "from interpretation_settlements where attempt_id = :a", a=start.attempt_id).one()
    assert tuple(row) == (None, None, None, "UNKNOWN", None, None)


def test_the_exact_task_and_reply_are_saved_with_hashes_and_the_revision_they_answer(client, ledger, request_of) -> None:
    owner, intake = request_of
    revision = ledger.history(owner, intake) or None  # no attempt yet
    assert revision is None or revision == []
    task = '{"task":"follow_up","answer":"' + REPLY + '"}'
    with client.app.state.session_factory() as session:
        head = session.execute(text("select record_id from records where intake_record_id = :i and "
                                    "record_type = 'PromptInterpretation'"), {"i": intake}).scalar_one()
    start = ledger.begin(owner, intake, identity(
        task, purpose="FOLLOW_UP", answer_ref="reply:" + str(uuid.uuid4()), answer_text=REPLY,
        previous_revision_id=str(head)))

    row = sql(client, "select task_text, task_sha256, answer_text, answer_sha256, previous_revision_id::text "
                      "from interpretation_attempts where attempt_id = :a", a=start.attempt_id).one()
    assert tuple(row) == (task, sha(task), REPLY, sha(REPLY), str(head))


def test_a_second_attempt_is_refused_while_one_is_open_and_allowed_after_it_settles(ledger, request_of) -> None:
    owner, intake = request_of
    first = ledger.begin(owner, intake, identity())
    with pytest.raises(AttemptInFlight):
        ledger.begin(owner, intake, identity())
    ledger.settle(settled(first.attempt_id, owner, "PROVIDER_FAILED", None, error_class="ProviderHTTPError"))

    second = ledger.begin(owner, intake, identity(), retry_of=first.attempt_id)

    assert (first.sequence, second.sequence, second.retry_of) == (1, 2, first.attempt_id)
    assert [v.start.attempt_id for v in ledger.history(owner, intake)] == [first.attempt_id, second.attempt_id]


def test_concurrent_attempts_for_one_request_admit_exactly_one(client, request_of) -> None:
    owner, intake = request_of

    def attempt(_index: int):
        local = AttemptLedger(PostgresAttemptStore(client.app.state.session_factory), new_id=lambda: str(uuid.uuid4()),
                              now=lambda: dt.datetime.now(dt.timezone.utc))
        try:
            return local.begin(owner, intake, identity()).sequence
        except AttemptInFlight:
            return "refused"

    results = run_threads(8, attempt)

    assert sorted(map(str, results)) == ["1"] + ["refused"] * 7
    rows = sql(client, "select count(*) from interpretation_attempts where intake_record_id = :i", i=intake).scalar_one()
    assert rows == 1


def test_another_owner_sees_nothing_and_cannot_settle_link_or_observe(client, ledger, request_of, other_request) -> None:
    owner, intake = request_of
    stranger, stranger_intake = other_request
    start = ledger.begin(owner, intake, identity())

    assert ledger.history(stranger, intake) == []
    with pytest.raises(UnknownAttempt):
        ledger.settle(settled(start.attempt_id, stranger))
    with pytest.raises(UnknownAttempt):
        ledger.link_revision(stranger, start.attempt_id, str(uuid.uuid4()))
    with pytest.raises(UnknownAttempt):
        ledger.observe_late_result(LateResult(
            str(uuid.uuid4()), start.attempt_id, stranger, dt.datetime.now(dt.timezone.utc), "COMPLETED", sha(TEXT), TEXT,
            REPORTED, 1, None))
    assert ledger.history(stranger, stranger_intake) == []
    assert ledger.history(owner, intake)[0].status == "STARTED"


def test_a_request_of_another_owner_cannot_hold_my_attempt(ledger, request_of, other_request) -> None:
    owner, _ = request_of
    _, stranger_intake = other_request
    with pytest.raises(IntegrityError):  # the database refuses: the request does not belong to this owner
        ledger.begin(owner, stranger_intake, identity())


@pytest.mark.parametrize("table", ["interpretation_attempts", "interpretation_settlements",
                                   "interpretation_attempt_links", "interpretation_late_results"])
def test_stored_rows_cannot_be_changed_or_removed(client, ledger, request_of, table: str) -> None:
    owner, intake = request_of
    start = ledger.begin(owner, intake, identity())
    ledger.settle(settled(start.attempt_id, owner, "TIMED_OUT", None, usage=Usage(), latency_ms=None, request_count=None))
    ledger.observe_late_result(LateResult(
        str(uuid.uuid4()), start.attempt_id, owner, dt.datetime.now(dt.timezone.utc), "COMPLETED", sha(TEXT), TEXT,
        REPORTED, 1, None))
    accepted = ledger.begin(owner, intake, identity(), retry_of=start.attempt_id)
    ledger.settle(settled(accepted.attempt_id, owner))
    ledger.link_revision(owner, accepted.attempt_id, accepted_revision(client, owner, intake))
    key = "observation_id" if table == "interpretation_late_results" else "attempt_id"
    for statement in (f"update {table} set owner_id = owner_id", f"delete from {table}"):
        with pytest.raises(DBAPIError, match="immutable"):
            sql(client, statement + f" where {key} is not null")


def test_the_database_refuses_a_hash_that_does_not_match_the_saved_text(client, request_of) -> None:
    owner, intake = request_of
    now = dt.datetime.now(dt.timezone.utc)
    with pytest.raises(IntegrityError, match="ck_attempt_task_hash"):
        sql(client, "insert into interpretation_attempts (attempt_id, owner_id, intake_record_id, sequence, purpose, "
                    "prompt_version, system_prompt_sha256, task_sha256, task_text, response_shape_sha256, manifest_sha256,"
                    " config, config_sha256, runtime_label, started_at) values (:a, :o, :i, 1, 'INTERPRET', 'p', :h, :h, "
                    "'text', :h, :h, '{}', :h, 'LOCAL_FAKE_PROVIDER', :t)",
            a=str(uuid.uuid4()), o=owner, i=intake, h="a" * 64, t=now)


def test_the_database_refuses_a_settlement_that_contradicts_its_status(client, ledger, request_of) -> None:
    owner, intake = request_of
    start = ledger.begin(owner, intake, identity())
    with pytest.raises(IntegrityError, match="ck_settlement_text"):
        sql(client, "insert into interpretation_settlements (attempt_id, owner_id, intake_record_id, status, finished_at,"
                    " usage_source, parse_result, runtime_observed) values (:a, :o, :i, 'COMPLETED', now(), 'UNKNOWN', "
                    "'NOT_PARSED', '{}')", a=start.attempt_id, o=owner, i=intake)


def test_an_attempt_settles_once_even_through_two_ledgers(client, ledger, request_of) -> None:
    owner, intake = request_of
    start = ledger.begin(owner, intake, identity())
    ledger.settle(settled(start.attempt_id, owner))
    other = AttemptLedger(PostgresAttemptStore(client.app.state.session_factory), new_id=lambda: "x",
                          now=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(Exception) as caught:
        other.settle(settled(start.attempt_id, owner, "PROVIDER_FAILED", None, usage=Usage(), parse_result="NOT_PARSED"))
    assert caught.type.__name__ in {"AlreadySettled", "IntegrityError"}
    assert ledger.history(owner, intake)[0].status == "COMPLETED"


def accepted_revision(client, owner: str, intake: str) -> str:
    """The saved root interpretation of this request (written by the application)."""
    return str(sql(client, "select record_id from records where intake_record_id = :i and "
                           "record_type = 'PromptInterpretation'", i=intake).scalar_one())


def test_only_an_accepted_attempt_links_to_a_revision_and_only_once(client, ledger, request_of) -> None:
    owner, intake = request_of
    revision = accepted_revision(client, owner, intake)
    rejected = ledger.begin(owner, intake, identity())
    ledger.settle(settled(rejected.attempt_id, owner, "COMPLETED", TEXT, parse_result="REJECTED:multiple_objects"))
    with pytest.raises(NotPublishable):
        ledger.link_revision(owner, rejected.attempt_id, revision)
    accepted = ledger.begin(owner, intake, identity(), retry_of=rejected.attempt_id)
    ledger.settle(settled(accepted.attempt_id, owner))
    questions = [{"question_id": "q", "field_name": "entry", "text": "Which?", "options": []}]

    ledger.link_revision(owner, accepted.attempt_id, revision, offered_questions=questions)

    assert ledger.history(owner, intake)[1].revision_id == revision
    assert ledger.offered_questions(owner, intake, revision) == questions
    with pytest.raises(AlreadyLinked):
        ledger.link_revision(owner, accepted.attempt_id, revision)
    assert ledger.unpublished_results(owner, intake) == []


def test_a_link_written_in_an_outer_transaction_disappears_with_its_rollback(client, store, ledger, request_of) -> None:
    owner, intake = request_of
    revision = accepted_revision(client, owner, intake)
    start = ledger.begin(owner, intake, identity())
    ledger.settle(settled(start.attempt_id, owner))

    with client.app.state.session_factory() as session:
        AttemptLedger(store.bound_to(session), new_id=lambda: "x", now=lambda: dt.datetime.now(dt.timezone.utc)
                      ).link_revision(owner, start.attempt_id, revision)
        session.rollback()

    assert ledger.history(owner, intake)[0].revision_id is None
    assert [v.start.attempt_id for v in ledger.unpublished_results(owner, intake)] == [start.attempt_id]


def test_a_late_result_is_stored_beside_an_unknown_attempt_and_changes_nothing(client, ledger, request_of) -> None:
    owner, intake = request_of
    start = ledger.begin(owner, intake, identity())
    ledger.settle(settled(start.attempt_id, owner, "TIMED_OUT", None, usage=Usage(), latency_ms=None, request_count=None))
    before = ledger.history(owner, intake)

    ledger.observe_late_result(LateResult(
        "11111111-1111-4111-8111-111111111111", start.attempt_id, owner, dt.datetime.now(dt.timezone.utc), "COMPLETED",
        sha(TEXT), TEXT, REPORTED, 1, None))

    assert ledger.history(owner, intake) == before
    [late] = ledger.late_results(owner, intake)
    assert (late.observation_id, late.response_text, late.usage, late.status) == (
        "11111111-1111-4111-8111-111111111111", TEXT, REPORTED, "COMPLETED")
    assert ledger.unpublished_results(owner, intake) == []


def test_the_database_refuses_a_late_result_beside_a_known_outcome(client, ledger, request_of) -> None:
    owner, intake = request_of
    start = ledger.begin(owner, intake, identity())
    ledger.settle(settled(start.attempt_id, owner))
    with pytest.raises(NotUncertain):
        ledger.observe_late_result(LateResult(
            str(uuid.uuid4()), start.attempt_id, owner, dt.datetime.now(dt.timezone.utc), "COMPLETED", sha(TEXT), TEXT,
            REPORTED, 1, None))
    with pytest.raises(IntegrityError, match="fk_late_result_uncertain_settlement|ck_late_result_uncertain"):
        sql(client, "insert into interpretation_late_results (observation_id, attempt_id, owner_id, intake_record_id, "
                    "settled_status, observed_at, status, usage_source) values (:x, :a, :o, :i, 'COMPLETED', now(), "
                    "'COMPLETED', 'UNKNOWN')", x=str(uuid.uuid4()), a=start.attempt_id, o=owner, i=intake)


class HeldClaim:
    """Holds a claim from a second database connection pool, as a second API process would."""

    def __init__(self, engine, attempt_id: str) -> None:
        self.guard, self.attempt_id = AdvisoryLockGuard(engine), attempt_id

    def __enter__(self):
        self.context = self.guard.claim(self.attempt_id)
        self.context.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self.context.__exit__(*exc)


def test_a_claim_held_by_another_connection_keeps_its_attempt_open_until_the_claim_is_released(
        client, ledger, request_of) -> None:
    owner, intake = request_of
    engine = client.app.state.engine
    guard = AdvisoryLockGuard(engine)
    attempt_id = str(uuid.uuid4())
    with HeldClaim(engine, attempt_id):  # the live worker holds the claim before it records the attempt
        ledger.begin(owner, intake, identity(), attempt_id=attempt_id)
        assert guard.is_abandoned(attempt_id) is False
        assert ledger.interrupt_abandoned(owner, intake, lambda start: guard.is_abandoned(start.attempt_id)) == []
        assert ledger.history(owner, intake)[0].status == "STARTED"
        with pytest.raises(AttemptInFlight):
            ledger.begin(owner, intake, identity())

    assert guard.is_abandoned(attempt_id) is True  # the worker is gone: the claim is released
    [closed] = ledger.interrupt_abandoned(owner, intake, lambda start: guard.is_abandoned(start.attempt_id))
    assert (closed.status, closed.completion) == ("INTERRUPTED", "UNKNOWN")
    assert closed.settlement is not None and closed.settlement.usage == Usage()


def test_a_claim_is_released_when_its_connection_dies(client) -> None:
    engine = client.app.state.engine
    guard = AdvisoryLockGuard(engine)
    attempt_id = str(uuid.uuid4())
    context = guard.claim(attempt_id)
    context.__enter__()
    assert guard.is_abandoned(attempt_id) is False
    context.__exit__(RuntimeError, RuntimeError("worker crashed"), None)
    assert guard.is_abandoned(attempt_id) is True
