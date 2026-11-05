"""OWNER-TRIGGER-L3 repair 2: a failed attempt that sent nothing does not use up the one action.

Seam: owner route -> saved job -> worker -> controlled runtime. Each failure is injected at the worker's holdings
read; the saved rows and the signing counter are the observed results.
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select

import financial_flows as ff
from admission._builders import AGENT_A, NETWORK, WALLET_A
from execution._builders import DECISION_TIME, frozen_entry_exit
from execution.test_mounted_controlled_execution import detail, reconcile, run_job, submit
from execution.test_owner_triggered_action import composed_case
from test_original_transaction_journey import original, recordings  # noqa: F401 - fixtures
from edge_os_api.execution.current_holdings import HoldingsUnavailable
from edge_os_api.execution.models import DecisionRow, EvaluationJobRow, IntentRow, QueueRow
from edge_os_api.execution.service import ExecutionService
from edge_os_api.execution.worker import ConnectedExecution

NEXT_SLOT = dt.timedelta(minutes=5)
USED = ("COMPLETED", "DENIED", "OWNER_TRIGGER_ALREADY_USED")


@pytest.fixture
def case(original, owner_a, tmp_path, settings, monkeypatch):  # noqa: F811
    return composed_case(original, owner_a, tmp_path, settings, monkeypatch, lifetime=dt.timedelta(hours=1))


def fail_holdings(monkeypatch, times=1):
    real, left = ConnectedExecution._holdings, [times]

    def holdings(self, agent, now):
        if left[0] > 0:
            left[0] -= 1
            raise HoldingsUnavailable("HOLDINGS_READ_FAILED")
        return real(self, agent, now)

    monkeypatch.setattr(ConnectedExecution, "_holdings", holdings)


def empty_wallet_once(monkeypatch):
    real, left = ConnectedExecution._holdings, [1]

    def holdings(self, agent, now):
        context = real(self, agent, now)
        if left[0] == 0:
            return context
        left[0] -= 1
        balances = {asset: held.model_copy(update={"raw": "0"}) for asset, held in context.holdings.balances.items()}
        return context.model_copy(update={"holdings": context.holdings.model_copy(update={"balances": balances})})

    monkeypatch.setattr(ConnectedExecution, "_holdings", holdings)


def stop_before_submit_once(monkeypatch):
    real, left = ConnectedExecution._submit, [1]

    def stopped(self, job, agent, consent):
        if left[0] > 0:
            left[0] -= 1
            raise RuntimeError("fake stop after enqueue")
        return real(self, job, agent, consent)

    monkeypatch.setattr(ConnectedExecution, "_submit", stopped)


def rows(case, model):
    with case.factory() as session:
        found = session.execute(select(model).where(model.agent_id == case.agent)).scalars().all()
        return [{column.name: getattr(row, column.name) for column in model.__table__.columns} for row in found]


def attempts(case):
    return sorted(row["owner_trigger_attempt"] for row in rows(case, DecisionRow))


def test_a_failed_holdings_read_does_not_use_up_the_action(case, monkeypatch):
    fail_holdings(monkeypatch)
    failed = submit(case)
    assert (failed["state"], failed["reason"]) == ("UNAVAILABLE", "HOLDINGS_READ_FAILED"), failed
    assert failed["decision_id"] is not None and failed["action_id"] is None
    case.offset[0] += NEXT_SLOT
    retried = submit(case)
    assert retried["state"] == "SUBMITTED", retried
    assert retried["decision_id"] != failed["decision_id"]
    assert len(case.acquired) == 1
    assert attempts(case) == [1, 2]


def test_a_denied_admission_does_not_use_up_the_action(case, monkeypatch):
    empty_wallet_once(monkeypatch)
    denied = submit(case)
    assert (denied["state"], denied["outcome"]) == ("COMPLETED", "ADMISSION_DENIED"), denied
    case.offset[0] += NEXT_SLOT
    retried = submit(case)
    assert retried["state"] == "SUBMITTED", retried
    assert retried["action_id"] != denied["action_id"]
    assert len(case.acquired) == 1


def test_an_expired_unsent_action_does_not_use_up_the_action(case, monkeypatch):
    stop_before_submit_once(monkeypatch)
    scheduled = ff.schedule(case.client, case.headers, case.agent, "expired-unsent")
    with pytest.raises(RuntimeError):
        run_job(case.client, scheduled.json())
    case.offset[0] += NEXT_SLOT
    expired = run_job(case.client, scheduled.json())
    assert expired["state"] == "COMPLETED", expired
    assert rows(case, QueueRow)[0]["state"] == "DENIED_UNSENT"
    retried = submit(case)
    assert retried["state"] == "SUBMITTED", retried
    assert len(case.acquired) == 1


def test_a_running_attempt_keeps_the_action_used(case, monkeypatch):
    stop_before_submit_once(monkeypatch)
    scheduled = ff.schedule(case.client, case.headers, case.agent, "still-running")
    with pytest.raises(RuntimeError):
        run_job(case.client, scheduled.json())
    case.offset[0] += NEXT_SLOT
    second = submit(case)
    assert (second["state"], second["outcome"], second["reason"]) == USED, second
    assert case.acquired == []


def test_an_unknown_send_stays_used_after_a_restart(case):
    first = submit(case)
    assert first["outcome"] == "SUBMITTED_UNKNOWN", first
    case.offset[0] += NEXT_SLOT
    case.client.app.state.financial = case.compose("api")
    case.client.app.state.execution_worker = case.compose("worker")
    second = submit(case)
    assert (second["state"], second["outcome"], second["reason"]) == USED, second
    assert len(case.acquired) == 1


def test_a_real_send_stays_used(case):
    first = submit(case)
    assert reconcile(case, first)["receipt_outcome"] == "CONFIRMED"
    assert detail(case, first)["queue"]["state"] == "SUBMITTED_CONFIRMED"
    case.offset[0] += NEXT_SLOT
    second = submit(case)
    assert (second["state"], second["outcome"], second["reason"]) == USED, second
    assert len(case.acquired) == 1


def test_a_send_after_a_release_stays_used(case, monkeypatch):
    fail_holdings(monkeypatch)
    submit(case)
    case.offset[0] += NEXT_SLOT
    assert submit(case)["state"] == "SUBMITTED"
    case.offset[0] += NEXT_SLOT
    third = submit(case)
    assert (third["state"], third["outcome"], third["reason"]) == USED, third
    assert len(case.acquired) == 1
    assert attempts(case) == [1, 2]


def test_a_trigger_that_loses_the_attempt_number_gets_no_action(case, monkeypatch):
    fail_holdings(monkeypatch)
    submit(case)
    case.offset[0] += NEXT_SLOT
    real, rival = ExecutionService.authorize_owner_trigger, []

    def after_the_rival_acts(self, *args, **kwargs):
        if not rival:
            rival.append(None)
            case.offset[0] += NEXT_SLOT
            rival[0] = submit(case)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(ExecutionService, "authorize_owner_trigger", after_the_rival_acts)
    loser = submit(case)
    assert (loser["state"], loser["outcome"], loser["reason"]) == USED, loser
    assert loser["action_id"] is None
    assert rival[0]["state"] == "SUBMITTED", rival[0]
    assert len(case.acquired) == 1
    assert attempts(case) == [1, 2]
    assert len(rows(case, IntentRow)) == 1


def test_two_concurrent_saves_of_one_attempt_number_give_one_decision(execution_service, fresh_owner):
    revision, barrier = frozen_entry_exit(), Barrier(2)

    def save(index):
        barrier.wait()
        return execution_service.authorize_owner_trigger(
            fresh_owner, revision, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK,
            decision_at=DECISION_TIME + index * NEXT_SLOT, release_id="release", binding_sha256="7" * 64, attempt=2)

    with ThreadPoolExecutor(2) as pool:
        saved = list(pool.map(save, range(2)))
    assert sorted(view is None for view in saved) == [False, True]


def test_repeated_failures_never_retry_or_send_by_themselves(case, monkeypatch):
    fail_holdings(monkeypatch, times=3)
    for _ in range(3):
        assert submit(case)["state"] == "UNAVAILABLE"
        case.offset[0] += NEXT_SLOT
    assert case.acquired == []
    assert len(rows(case, EvaluationJobRow)) == 3
    assert submit(case)["state"] == "SUBMITTED"
    assert len(case.acquired) == 1
    assert attempts(case) == [1, 2, 3, 4]


def test_a_later_attempt_keeps_every_saved_row_of_the_released_attempt(case, monkeypatch):
    empty_wallet_once(monkeypatch)
    denied = submit(case)
    decisions, intents, queue = (rows(case, model) for model in (DecisionRow, IntentRow, QueueRow))
    case.offset[0] += NEXT_SLOT
    assert submit(case)["state"] == "SUBMITTED"
    assert decisions[0] in rows(case, DecisionRow)
    assert intents[0] in rows(case, IntentRow)
    assert queue[0] in rows(case, QueueRow)
    assert detail(case, denied)["queue"]["state"] == "ADMISSION_DENIED"
