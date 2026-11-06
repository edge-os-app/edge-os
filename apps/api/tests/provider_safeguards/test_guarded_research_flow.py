"""The guarded runner behind the saved Research path: HTTP, PostgreSQL, the attempt ledger and a durable spend ledger.

Only the Hermes process boundary is a controlled stand-in (`CaseRunner`). The spend ledger and the guard policy around
it are the real ones from `scripts/hermes_interpretation`. No provider, key, account or network is used; the checks
count requests at the boundary and watch for any non-loopback socket. Money values are hand-worked literals at TEST prices.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "scripts" / "hermes_interpretation"))

from guarded_turn_runner import GuardedTurnRunner  # noqa: E402
from provider_guard import GuardPolicy  # noqa: E402
from spend_ledger import SpendLedger, TokenPrice  # noqa: E402

from edge_os_api.core.settings import load_settings  # noqa: E402
from edge_os_api.main import create_app  # noqa: E402
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult  # noqa: E402
from edge_os_api.research.interpretation_attempts import Usage  # noqa: E402
from hermes_cases import CaseRunner, case, intake_body, turn_result  # noqa: E402
from test_hermes_research_flow import create, retry, rows  # noqa: E402

SENTINEL = "sk-test-DUMMY-SENTINEL-9f3a71c2e8b54d06"
PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
POLICY = GuardPolicy(model="local-fake/p05-interpretation", max_output_tokens=4096, max_request_bytes=7_236, max_envelope_chars=2_500)
RESERVATION = Decimal("0.04532")


@pytest.fixture
def spend(tmp_path: Path) -> SpendLedger:
    return SpendLedger(tmp_path / "spend.sqlite", cap_usd=Decimal("0.10"), price=PRICE)


@pytest.fixture
def make_guarded(env, migrated, spend):
    """Applications whose interpreter runner is the guarded one over a controlled boundary."""
    opened: list[TestClient] = []

    def build(delegate: Any, ledger: SpendLedger | None = None, scope_for=lambda turn: "research") -> TestClient:
        guarded = GuardedTurnRunner(delegate, ledger or spend, POLICY, scope_for=scope_for)
        client = TestClient(create_app(load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"}), hermes_runner=guarded))
        client.__enter__()
        opened.append(client)
        return client

    yield build
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def no_egress(monkeypatch: pytest.MonkeyPatch):
    """Records every socket connection to a non-loopback address. A guarded local run must make none."""
    real, outside = socket.socket.connect, []

    def watch(self, address, *args):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            outside.append(host)
        return real(self, address, *args)

    monkeypatch.setattr(socket.socket, "connect", watch)
    return outside


def settlement_rows(client: TestClient, since: Any = None) -> list[Any]:
    """Settlements in the shared test database, optionally only those finished after `since`."""
    return rows(client, "select status, request_count, error_class, runtime_observed from interpretation_settlements "
                        "where finished_at > coalesce(:since, '-infinity'::timestamptz) order by finished_at", since=since)


def database_now(client: TestClient) -> Any:
    return rows(client, "select clock_timestamp()")[0][0]


def test_a_returned_answer_is_saved_charged_exactly_and_made_no_outside_connection(make_guarded, owner_a, spend, no_egress) -> None:
    delegate = CaseRunner(turn_result(case("concrete-thesis")["provider"]))
    client = make_guarded(delegate)

    created = create(client, owner_a, "concrete-thesis")

    assert created.status_code == 201, created.text
    [attempt] = created.json()["attempts"]
    assert (attempt["status"], attempt["request_count"], attempt["parse_result"]) == ("COMPLETED", 1, "ACCEPTED")
    assert len(delegate.turns) == 1 and no_egress == []
    [(status, count, error, observed)] = [r for r in settlement_rows(client) if r[0] == "COMPLETED"][-1:]
    assert observed["spend_state"] == "SETTLED" and observed["spend_charge_usd"] == "0.0074285"
    assert spend.committed_usd() == Decimal("0.0074285")


def test_a_rejected_answer_is_saved_and_its_reported_usage_is_still_charged(make_guarded, owner_a, spend) -> None:
    client = make_guarded(CaseRunner(turn_result(case("multiple-objects")["provider"])))

    created = create(client, owner_a, "multiple-objects")

    assert created.status_code == 201
    assert created.json()["attempts"][0]["parse_result"].startswith("REJECTED")
    [(status, count, _, observed)] = settlement_rows(client)[-1:]
    assert (status, count, observed["spend_state"]) == ("COMPLETED", 1, "SETTLED")
    assert spend.committed_usd() > 0 and spend.committed_usd() < RESERVATION


def test_a_cut_off_answer_is_saved_as_truncated_and_charged_from_its_usage(make_guarded, owner_a, spend) -> None:
    client = make_guarded(CaseRunner(turn_result(case("truncated-cut-off")["provider"])))

    create(client, owner_a, "truncated-cut-off")

    assert settlement_rows(client)[-1][0] == "TRUNCATED" and spend.committed_usd() == Decimal("0.0074285")


def test_a_provider_error_keeps_the_reservation_and_a_retry_starts_no_second_request(make_guarded, owner_a, spend) -> None:
    delegate = CaseRunner(turn_result(case("provider-503")["provider"]), turn_result(case("concrete-thesis")["provider"]))
    client = make_guarded(delegate)
    create(client, owner_a, "concrete-thesis")
    intake_id = client.get("/v1/research/requests", headers=owner_a).json()["requests"][0]["intake_record_id"]
    shown = client.get(f"/v1/research/requests/{intake_id}", headers=owner_a).json()
    attempt_id = shown["attempts"][0]["attempt_id"]
    retried = client.post(f"/v1/research/requests/{intake_id}/interpretation-retries", headers=owner_a, json={"retry_of": attempt_id})

    assert spend.state(attempt_id) == "UNKNOWN" and len(delegate.turns) == 1
    last = settlement_rows(client)[-1]
    assert (last[1], last[2]) == (0, "SpendScopeBlocked") and retried.status_code == 201
    assert spend.committed_usd() == RESERVATION


def test_malformed_usage_keeps_the_full_reservation(make_guarded, owner_a, spend) -> None:
    result = turn_result(case("concrete-thesis")["provider"])
    client = make_guarded(CaseRunner(HermesTurnResult(result.status, result.text, Usage(True, 5, None, "PROVIDER_REPORTED"),
                                                      1, result.observed, None)))

    create(client, owner_a, "concrete-thesis")

    assert [(s.state, s.amount_usd) for s in spend.unresolved()] == [("UNKNOWN", RESERVATION)]


def test_a_hung_boundary_leaves_liability_that_survives_restart_and_late_evidence_settles_it_once(
        make_guarded, owner_a, spend, tmp_path: Path) -> None:
    client = make_guarded(CaseRunner(turn_result(case("provider-hang")["provider"])))
    create(client, owner_a, "concrete-thesis")
    [(attempt_id, _, _)] = [(r.attempt_id, r.state, r.amount_usd) for r in spend.unresolved()]

    reopened = SpendLedger(tmp_path / "spend.sqlite", cap_usd=Decimal("0.10"), price=PRICE)
    assert (reopened.state(attempt_id), reopened.committed_usd()) == ("UNKNOWN", RESERVATION)

    late = reopened.reconcile(attempt_id, input_tokens=1_423, output_tokens=611, source="LATE_RESULT")
    again = reopened.reconcile(attempt_id, input_tokens=1_423, output_tokens=611, source="LATE_RESULT")
    assert (late.cost_usd, again.cost_usd, reopened.committed_usd()) == (Decimal("0.0074285"),) * 3


def test_an_exhausted_cap_saves_a_refused_attempt_and_the_boundary_is_never_called(make_guarded, owner_a, tmp_path: Path) -> None:
    tight = SpendLedger(tmp_path / "tight.sqlite", cap_usd=Decimal("0.04"), price=PRICE)  # below one worst-case reservation
    delegate = CaseRunner(turn_result(case("concrete-thesis")["provider"]))
    client = make_guarded(delegate, tight)

    created = create(client, owner_a, "concrete-thesis")

    assert created.status_code == 201, created.text
    assert created.json()["outcomes"][-1]["record"]["content"]["findings"][0]["code"] == "budget_exhausted"
    assert delegate.turns == [] and tight.committed_usd() == 0
    [(status, count, error, _)] = settlement_rows(client)[-1:]
    assert (status, count, error) == ("PROVIDER_FAILED", 0, "SpendCapReached")


def test_simultaneous_requests_start_only_as_many_boundary_calls_as_the_cap_allows(
        make_guarded, owner_a, owner_b, signer, spend) -> None:
    release, entered, lock = threading.Event(), [], threading.Lock()

    class Holding:
        def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
            with lock:
                entered.append(turn.attempt_id)
            release.wait(timeout=30)  # both admitted calls stay in flight while the others are refused
            return turn_result(case("concrete-thesis")["provider"])

    client = make_guarded(Holding(), scope_for=lambda turn: turn.attempt_id)
    since = database_now(client)
    results: list[int] = []
    owners = [owner_a, owner_b]
    owners.extend({"Authorization": f"Bearer {signer.token(f'did:privy:test-owner-{index}-{uuid.uuid4().hex[:8]}')}"}
                  for index in range(4))

    def go(headers: dict[str, str]) -> None:
        outcome = client.post("/v1/research/requests", json=intake_body("concrete-thesis"), headers=headers)
        with lock:
            results.append(outcome.status_code)

    threads = [threading.Thread(target=go, args=(headers,)) for headers in owners]
    for thread in threads:
        thread.start()
    for _ in range(300):
        with lock:
            if len(results) >= 4:
                break
        threading.Event().wait(0.1)
    release.set()
    for thread in threads:
        thread.join(timeout=60)

    assert len(entered) == 2
    assert spend.committed_usd() == Decimal("0.0074285") * 2
    assert sorted(results) == [201, 201, 429, 429, 429, 429]
    assert [r for r in settlement_rows(client, since) if r[2] == "SpendCapReached"] == []


def test_spend_already_recorded_counts_toward_the_cap(make_guarded, owner_a, tmp_path: Path) -> None:
    tight = SpendLedger(tmp_path / "recorded.sqlite", cap_usd=Decimal("0.050"), price=PRICE)
    delegate = CaseRunner(turn_result(case("concrete-thesis")["provider"]),
                          turn_result(case("concrete-thesis")["provider"]))
    client = make_guarded(delegate, tight)

    first = create(client, owner_a, "concrete-thesis")
    second = create(client, owner_a, "concrete-thesis")

    assert first.status_code == 201 and second.status_code == 201, second.text
    assert len(delegate.turns) == 1
    assert tight.committed_usd() == Decimal("0.0074285")
    assert second.json()["outcomes"][-1]["record"]["content"]["findings"][0]["code"] == "budget_exhausted"


def test_a_failure_message_with_a_credential_in_it_reaches_no_saved_record_response_or_log(
        make_guarded, owner_a, spend, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")
    client = make_guarded(CaseRunner(OSError(f"connection failed with Authorization: Bearer {SENTINEL}")))

    response = create(client, owner_a, "concrete-thesis")

    assert SENTINEL not in response.text and SENTINEL not in caplog.text
    dump = json.dumps(rows(client, "select error_class, runtime_observed::text from interpretation_settlements"), default=str)
    assert SENTINEL not in dump and "OSError" in dump
    assert (spend.state(spend.unresolved()[0].attempt_id), spend.committed_usd()) == ("UNKNOWN", RESERVATION)
