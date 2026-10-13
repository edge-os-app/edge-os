"""The Hermes transport mount behind the saved Research path: refusals, composition, intake scope and the spend view.

Seam: `open_transport_mount` and `create_app(settings, hermes_runner=mount.runner)` over authenticated HTTP and the
migrated PostgreSQL database. The composition is the real one (accepted guard runner, accepted transport identity check,
PostgreSQL spend ledger); only the container job is replaced by a controlled stand-in, so no Docker runs here. The
pinned-Hermes tests under `tests/hermes_app_mount/` run the same mount with the real job. No provider, key or network.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.research import hermes_transport_mount as mount_module
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.hermes_transport_mount import AUTHORED_ROUTE, DEFAULT_POLICY, open_transport_mount
from edge_os_api.research.provider_spend_ledger import SpendLimits, TokenPrice
from hermes_cases import case, intake_body, turn_result
from test_hermes_research_flow import create, retry, rows
from test_provider_spend_ledger import empty_spend_ledger

PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
LIMITS = SpendLimits(global_cap_usd=Decimal("0.20"), owner_cap_usd=Decimal("0.12"), price=PRICE)
RESERVATION = Decimal("0.054848")  # (12,000 + 64) x 2.00 / 1e6 + 4,096 x 7.50 / 1e6
EXACT_CHARGE = Decimal("0.0074285")  # concrete-thesis reports 1,423 prompt and 611 completion tokens


def job_report(result: HermesTurnResult, *, sent: int = 1, attempt: str | None = None, route: str | None = None):
    """What the transport job reports for one turn: the attempt and route it served and the requests it sent."""
    def report(turn: HermesTurn) -> HermesTurnResult:
        named = attempt or turn.attempt_id
        return replace(result, observed={**result.observed, "guard_admitted": sent, "transport_attempt_id": named,
                                         "transport_route_id": route or AUTHORED_ROUTE.route_id, "transport_sent": sent,
                                         "transport_request_attempt_ids": [named] * sent})
    return report


class Boundary:
    """Stands in for the container job behind the accepted transport identity check. Keeps every turn it was given."""

    def __init__(self, *script: Any) -> None:
        self.script, self.turns = list(script), []

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        self.turns.append(turn)
        item = self.script.pop(0)
        return item(turn) if callable(item) else item


@pytest.fixture
def mounted(env, migrated, client, tmp_path: Path):
    """`build(boundary)` opens a mount whose job is the stand-in, and an application over it."""
    empty_spend_ledger(client.app.state.session_factory)
    opened: list[tuple[Any, TestClient]] = []

    def build(boundary: Boundary, limits: SpendLimits = LIMITS) -> tuple[Any, TestClient]:
        settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})
        mount = open_transport_mount(settings, limits=limits, image="unused:stand-in", run_id="mount-unit",
                                     evidence_dir=tmp_path / "turns", script_for=lambda turn: {})
        mount.supervision.run_turn = boundary.run_turn  # the job only; guard, identity check and ledger stay real
        app_client = TestClient(create_app(settings, hermes_runner=mount.runner))
        app_client.__enter__()
        opened.append((mount, app_client))
        return mount, app_client

    yield build
    for mount, app_client in opened:
        app_client.__exit__(None, None, None)
        mount.close()
    empty_spend_ledger(client.app.state.session_factory)


def test_production_an_actual_route_another_interpreter_or_a_foreign_policy_are_refused_before_any_effect(
        env, migrated, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from edge_os_api.research.hermes_transport_mount import MountRefused
    from provider_transport import ActualProviderUnavailable, TransportRoute
    engines: list[str] = []
    monkeypatch.setattr(mount_module, "make_engine", lambda *a, **k: engines.append("engine") or pytest.fail("effect"))
    local = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})
    actual = TransportRoute("actual-1", "ACTUAL", "https://provider.invalid/v1/chat/completions", 65_536)
    cases = [
        (local.model_copy(update={"env": "production"}), {}, MountRefused),
        (load_settings(env), {}, MountRefused),  # the fixture interpreter
        (local, {"route": actual}, ActualProviderUnavailable),
        (local, {"policy": replace(DEFAULT_POLICY, model="another-model/1")}, MountRefused),
        (local, {"policy": replace(DEFAULT_POLICY, max_output_tokens=2048)}, MountRefused),
    ]
    for settings, changes, refusal in cases:
        with pytest.raises(refusal):
            open_transport_mount(settings, limits=LIMITS, image="unused", run_id="refused",
                                 evidence_dir=tmp_path / "never", script_for=lambda turn: {}, **changes)
    assert engines == [] and not (tmp_path / "never").exists()


def test_a_saved_request_is_interpreted_charged_exactly_and_reopens_with_its_spend_in_a_new_application(
        mounted, owner_a, owner_b) -> None:
    boundary = Boundary(job_report(turn_result(case("concrete-thesis")["provider"])))
    mount, app_client = mounted(boundary)

    created = create(app_client, owner_a, "concrete-thesis")

    assert created.status_code == 201, created.text
    [attempt] = created.json()["attempts"]
    assert (attempt["status"], attempt["parse_result"], attempt["request_count"]) == ("COMPLETED", "ACCEPTED", 1)
    assert attempt["spend"] == {"state": "SETTLED", "charge_usd": str(EXACT_CHARGE)}
    assert [turn.attempt_id for turn in boundary.turns] == [attempt["attempt_id"]]
    assert mount.spend.state(attempt["attempt_id"]) == "SETTLED" and mount.spend.committed_usd() == EXACT_CHARGE

    _again, reopened_client = mounted(Boundary())  # the browser closed; a new application process serves the reopen
    path = f"/v1/research/requests/{created.json()['intake']['record_id']}"
    reopened = reopened_client.get(path, headers=owner_a)
    assert reopened.status_code == 200 and reopened.json()["attempts"] == created.json()["attempts"]
    assert reopened.json()["head"] == created.json()["head"]
    assert reopened_client.get(path, headers=owner_b).status_code == 404


def test_a_lost_reply_keeps_the_whole_reservation_is_never_accepted_and_is_not_retried(mounted, owner_a) -> None:
    returned = turn_result(case("concrete-thesis")["provider"])
    lost = HermesTurnResult("UNKNOWN", None, returned.usage, None, returned.observed, "TransportLost")
    boundary = Boundary(job_report(lost), job_report(returned))
    mount, app_client = mounted(boundary)

    first = create(app_client, owner_a, "concrete-thesis").json()
    [unknown] = first["attempts"]
    assert (unknown["status"], unknown["parse_result"], unknown["revision_id"]) == ("UNKNOWN", "NOT_PARSED", None)
    assert first["head"]["interpretation_revision_id"] is None  # nothing from it became the saved meaning
    assert unknown["spend"] == {"state": "UNKNOWN", "charge_usd": str(RESERVATION)}
    assert retry(app_client, owner_a, first, unknown["attempt_id"]).status_code == 409 and len(boundary.turns) == 1

    other = create(app_client, owner_a, "concrete-thesis").json()  # another saved request is its own scope
    assert other["attempts"][0]["spend"]["state"] == "SETTLED" and len(boundary.turns) == 2
    assert mount.spend.committed_usd() == RESERVATION + EXACT_CHARGE


def attempts_of(app_client: TestClient, headers: dict[str, str], bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return app_client.get(f"/v1/research/requests/{bundle['intake']['record_id']}", headers=headers).json()["attempts"]


def test_a_retry_is_a_new_attempt_that_held_liability_refuses_and_an_unsent_attempt_lets_run_once(mounted, owner_a) -> None:
    returned = turn_result(case("concrete-thesis")["provider"])
    failed = turn_result({"kind": "http_error"})  # the provider answered with an error: one request, usage unknown
    unsent = HermesTurnResult("PROVIDER_FAILED", None, returned.usage.__class__(), 0, {}, "CleanupPending")
    boundary = Boundary(job_report(failed), job_report(unsent, sent=0), job_report(returned))
    mount, app_client = mounted(boundary)

    held = create(app_client, owner_a, "concrete-thesis").json()
    [first] = held["attempts"]
    assert (first["status"], first["spend"]["state"]) == ("PROVIDER_FAILED", "UNKNOWN")
    retry(app_client, owner_a, held, first["attempt_id"])
    [_, blocked] = attempts_of(app_client, owner_a, held)
    assert (blocked["retry_of"], blocked["error_class"], blocked["request_count"]) == (
        first["attempt_id"], "SpendScopeBlocked", 0)
    assert blocked["spend"] == {"state": None, "charge_usd": None} and len(boundary.turns) == 1  # no second job

    free = create(app_client, owner_a, "concrete-thesis").json()
    [released] = free["attempts"]
    assert (released["status"], released["spend"]["state"]) == ("PROVIDER_FAILED", "RELEASED")
    retry(app_client, owner_a, free, released["attempt_id"])
    [_, again] = attempts_of(app_client, owner_a, free)
    assert (again["retry_of"], again["status"], again["spend"]["state"]) == (released["attempt_id"], "COMPLETED", "SETTLED")
    assert [t.attempt_id for t in boundary.turns] == [first["attempt_id"], released["attempt_id"], again["attempt_id"]]
    assert mount.spend.state(blocked["attempt_id"]) is None and mount.spend.committed_usd() == RESERVATION + EXACT_CHARGE


def test_a_report_for_another_attempt_is_withheld_and_a_job_that_sent_nothing_frees_its_reservation(
        mounted, owner_a) -> None:
    returned = turn_result(case("concrete-thesis")["provider"])
    nothing = HermesTurnResult("PROVIDER_FAILED", None, returned.usage.__class__(), 0, {}, "CleanupPending")
    boundary = Boundary(job_report(returned, attempt="00000000-0000-4000-8000-00000000dead"),
                        job_report(nothing, sent=0))
    mount, app_client = mounted(boundary)

    mismatched = create(app_client, owner_a, "concrete-thesis").json()["attempts"][0]
    assert (mismatched["status"], mismatched["error_class"], mismatched["parse_result"]) == (
        "UNKNOWN", "TransportIdentityMismatch", "NOT_PARSED")
    assert mount.spend.state(mismatched["attempt_id"]) == "UNKNOWN"

    unsent = create(app_client, owner_a, "concrete-thesis").json()["attempts"][0]
    assert (unsent["status"], unsent["request_count"]) == ("PROVIDER_FAILED", 0)
    assert mount.spend.state(unsent["attempt_id"]) == "RELEASED" and unsent["spend"]["state"] == "RELEASED"
    assert mount.spend.committed_usd() == RESERVATION


def test_an_exhausted_owner_cap_saves_a_refused_attempt_and_never_reaches_the_job(mounted, owner_a, owner_b) -> None:
    hang = HermesTurnResult("TIMED_OUT", None, turn_result(case("concrete-thesis")["provider"]).usage.__class__(), None, {},
                            "TimeoutExpired")
    boundary = Boundary(job_report(hang, sent=1), job_report(hang, sent=1),
                        job_report(turn_result(case("concrete-thesis")["provider"])))
    mount, app_client = mounted(boundary, SpendLimits(Decimal("0.20"), Decimal("0.11"), PRICE))

    for _ in range(2):  # two timed-out attempts keep 0.109696 of owner A's 0.11 as liability
        assert create(app_client, owner_a, "concrete-thesis").json()["attempts"][0]["spend"]["state"] == "UNKNOWN"
    refused = create(app_client, owner_a, "concrete-thesis").json()["attempts"][0]
    assert (refused["status"], refused["error_class"], refused["request_count"]) == ("PROVIDER_FAILED", "SpendCapReached", 0)
    assert len(boundary.turns) == 2

    other_owner = create(app_client, owner_b, "concrete-thesis").json()["attempts"][0]
    assert other_owner["spend"]["state"] == "SETTLED" and len(boundary.turns) == 3
    assert [r[0] for r in rows(app_client, "select count(*) from usage_local.provider_spend_reservations")] == [3]
