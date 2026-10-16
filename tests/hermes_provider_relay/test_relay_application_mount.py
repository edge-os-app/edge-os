"""The saved Research path over the relay: create, reopen and owner denial through the real application, with ACTUAL
pinned Hermes in a no-network job, the relay holding the synthetic key, and the shared PostgreSQL spend ledger.

Counts come from SQL, the relay's records and the AUTHORED provider's receipts. Needs Docker.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from authored_cases import load_case, provider_script
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from edge_os_api.research.hermes_transport_mount import AUTHORED_ROUTE, DEFAULT_POLICY
from edge_os_api.research.provider_spend_ledger import SpendLimits, TokenPrice
from leak_scan import find_leaks
from relay_admission import RelayRelease
from relay_application_mount import open_relay_mount
from relay_harness import counts, provider_receipts, relay_record
from relay_supervisor import RelaySupervisor

from conftest import SENTINEL

PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
LIMITS = SpendLimits(Decimal("0.20"), Decimal("0.12"), PRICE)
RESERVATION = Decimal("0.054848")
EXACT_CHARGE = Decimal("0.0074285")
APP_RELEASE = RelayRelease("local-relay-app-1", AUTHORED_ROUTE.route_id, "AUTHORED", DEFAULT_POLICY.model,
                           DEFAULT_POLICY.max_output_tokens, DEFAULT_POLICY.max_request_bytes, AUTHORED_ROUTE.max_reply_bytes)
SPEND_TABLES = "usage_local.provider_spend_events, usage_local.provider_spend_reservations, usage_local.provider_spend_settings"


@pytest.fixture(scope="module")
def app_relay(pinned_hermes_image, run_id, evidence_root, synthetic_key):
    supervisor = RelaySupervisor(evidence_root / "app-relay", APP_RELEASE, pinned_hermes_image, f"{run_id}-app",
                                 synthetic_key, {"app": evidence_root / "app-jobs"})
    try:
        supervisor.start()
        yield supervisor
    finally:
        (evidence_root / "app-relay-logs.txt").write_text(supervisor.logs(), encoding="utf-8")
        cleanup = supervisor.stop()
        (evidence_root / "app-relay-cleanup.json").write_text(json.dumps(cleanup, indent=1) + "\n")
        assert cleanup == {"containers_left": [], "networks_left": [], "volumes_left": []}, cleanup


@pytest.fixture
def spend_reset(pg, migrated):
    pg.psql(f"truncate {SPEND_TABLES}")
    yield
    pg.psql(f"truncate {SPEND_TABLES}")


class App:
    """One application over one relay mount. `script(...)` sets what the AUTHORED provider answers for the next turns."""

    def __init__(self, env: dict[str, str], image: str, run_id: str, relay: RelaySupervisor, evidence: Path) -> None:
        self.relay, self.next_script = relay, provider_script(load_case("concrete-thesis")["provider"])
        self.settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})
        self.mount = open_relay_mount(self.settings, limits=LIMITS, release=APP_RELEASE, endpoint=relay.endpoint("app"),
                                      image=image, run_id=run_id, evidence_dir=evidence, script_for=self.script_for)
        self.client = TestClient(create_app(self.settings, hermes_runner=self.mount.runner))
        self.client.__enter__()

    def script_for(self, turn: Any) -> dict[str, Any]:
        self.relay.path("provider", "scripts", f"{turn.attempt_id}.json").write_text(json.dumps(self.next_script))
        return self.next_script

    def close(self) -> None:
        self.client.__exit__(None, None, None)
        self.mount.close()


@pytest.fixture
def app(env, pinned_hermes_image, run_id, evidence_root, app_relay, spend_reset, request):
    opened: list[App] = []

    def build(name: str) -> App:
        opened.append(App(env, pinned_hermes_image, f"{run_id}-{request.node.name[5:25]}-{name}", app_relay,
                          evidence_root / "app-jobs"))
        return opened[-1]

    yield build
    for each in opened:
        each.close()


def intake() -> dict[str, Any]:
    return dict(load_case("concrete-thesis")["intake"])


def test_a_saved_request_goes_through_the_relay_once_is_charged_exactly_reopens_elsewhere_and_is_denied_to_another_owner(
        app, app_relay, owner_a, owner_b, pg, evidence_root) -> None:
    first = app("first")

    created = first.client.post("/v1/research/requests", json=intake(), headers=owner_a)

    assert created.status_code == 201, created.text
    [attempt] = created.json()["attempts"]
    attempt_id = attempt["attempt_id"]
    assert (attempt["status"], attempt["parse_result"], attempt["request_count"]) == ("COMPLETED", "ACCEPTED", 1)
    assert attempt["spend"] == {"state": "SETTLED", "charge_usd": str(EXACT_CHARGE)}
    observed = json.loads(pg.psql(f"select runtime_observed from interpretation_settlements where attempt_id = '{attempt_id}'"))
    assert (observed["relay_started"], observed["relay_outcome"], observed["relay_release_id"]) == (
        True, "reply", APP_RELEASE.release_id)
    assert observed["transport_request_attempt_ids"] == [attempt_id] and counts(app_relay, attempt_id) == (1, 1)
    owner, intake_id = pg.psql(f"select owner_id || '|' || intake_record_id from interpretation_attempts "
                               f"where attempt_id = '{attempt_id}'").split("|")
    grant = json.loads((app_relay.path("grants") / f"{attempt_id}.json").read_text())
    assert (grant["owner_id"], grant["request_id"], grant["scope"]) == (owner, intake_id, f"intake:{intake_id}")
    assert pg.psql(f"select state || '|' || owner_id from usage_local.provider_spend_reservations "
                   f"where attempt_id = '{attempt_id}'") == f"SETTLED|{owner}"
    assert first.mount.spend.committed_usd() == EXACT_CHARGE
    assert provider_receipts(app_relay, attempt_id)[0]["bearer_matches"] is True

    reopened = app("reopen")  # another application instance serves the reopen
    path = f"/v1/research/requests/{created.json()['intake']['record_id']}"
    again = reopened.client.get(path, headers=owner_a).json()
    assert again["attempts"] == created.json()["attempts"] and again["head"] == created.json()["head"]
    assert reopened.client.get(path, headers=owner_b).status_code == 404
    assert pg.psql("select count(*) from interpretation_attempts") == "1"
    assert pg.psql("select count(*) from usage_local.provider_spend_reservations") == "1"
    assert find_leaks(evidence_root / "app-jobs", SENTINEL) == [] and find_leaks(app_relay.root, SENTINEL) == []


def test_a_lost_reply_through_the_relay_is_never_accepted_and_blocks_its_saved_request(
        app, app_relay, owner_a, pg) -> None:
    first = app("lost")
    first.next_script = {**first.next_script, "kind": "lost_reply"}

    created = first.client.post("/v1/research/requests", json=intake(), headers=owner_a)

    [attempt] = created.json()["attempts"]
    assert attempt["parse_result"] != "ACCEPTED" and attempt["spend"]["state"] == "UNKNOWN"
    assert counts(app_relay, attempt["attempt_id"]) == (1, 1)
    assert relay_record(app_relay, attempt["attempt_id"], "finished")["outcome"] == "lost"
    assert first.mount.spend.committed_usd() == RESERVATION
    retried = first.client.post(f"/v1/research/requests/{created.json()['intake']['record_id']}/interpretation-retries",
                                headers=owner_a, json={"retry_of": attempt["attempt_id"]})
    assert retried.status_code == 409  # uncertain work is never replayed
    assert pg.psql("select count(*) from usage_local.provider_spend_reservations") == "1"
    assert first.mount.spend.committed_usd() == RESERVATION
