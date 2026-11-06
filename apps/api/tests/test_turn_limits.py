"""The per-owner and global interpretation turn limits.

The shared database and the real HTTP application are used. Only the Hermes process boundary is scripted. A refused
turn must write no attempt row and no spend reservation.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from hermes_cases import CaseRunner, case, intake_body, turn_result

from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app


def rows(client: TestClient, statement: str, **params: Any) -> list[Any]:
    with client.app.state.engine.begin() as connection:
        return list(connection.execute(text(statement), params))


@pytest.fixture
def make_client(env, migrated):
    opened: list[TestClient] = []

    def build(runner: Any) -> TestClient:
        client = TestClient(create_app(load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"}),
                                       hermes_runner=runner))
        client.__enter__()
        opened.append(client)
        return client

    yield build
    for client in opened:
        client.__exit__(None, None, None)


class Holding:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.entered: list[str] = []
        self.release = threading.Event()
        self.lock = threading.Lock()

    def run_turn(self, turn: Any) -> Any:
        with self.lock:
            self.entered.append(turn.attempt_id)
        self.release.wait(timeout=30)
        return self.result


def start(client: TestClient, headers: dict[str, str], name: str = "concrete-thesis") -> int:
    return client.post("/v1/research/requests", json=intake_body(name), headers=headers).status_code


def wait_for(items: list[Any], count: int, timeout: float = 20.0) -> None:
    limit = threading.Event()
    for _ in range(int(timeout / 0.05)):
        if len(items) >= count:
            return
        limit.wait(0.05)
    raise AssertionError(f"only {len(items)} of {count} turns started")


def test_one_unsettled_attempt_per_owner(env, migrated, owner_a, make_client) -> None:
    runner = Holding(turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)
    owner = client.get("/v1/me", headers=owner_a).json()["user_id"]
    results: list[int] = []

    first = threading.Thread(target=lambda: results.append(start(client, owner_a)))
    first.start()
    wait_for(runner.entered, 1)
    refused = client.post("/v1/research/requests", json=intake_body("concrete-thesis"), headers=owner_a)
    runner.release.set()
    first.join(timeout=60)

    assert results == [201]
    assert refused.status_code == 429 and refused.json()["code"] == "turn_in_flight"
    assert rows(client, "select count(*) from interpretation_attempts where owner_id = :o", o=uuid.UUID(owner))[0][0] == 1


def test_at_most_two_unsettled_attempts_across_owners(env, migrated, owner_a, owner_b, signer, make_client) -> None:
    runner = Holding(turn_result(case("concrete-thesis")["provider"]))
    client = make_client(runner)
    owner_c = {"Authorization": f"Bearer {signer.token(f'did:privy:test-owner-c-{uuid.uuid4().hex[:8]}')}"}
    results: list[int] = []

    threads = [threading.Thread(target=lambda headers=headers: results.append(start(client, headers)))
               for headers in (owner_a, owner_b)]
    for thread in threads:
        thread.start()
    wait_for(runner.entered, 2)
    refused = client.post("/v1/research/requests", json=intake_body("concrete-thesis"), headers=owner_c)
    runner.release.set()
    for thread in threads:
        thread.join(timeout=60)

    assert sorted(results) == [201, 201]
    assert refused.status_code == 429 and refused.json()["code"] == "turn_capacity_full"
    assert rows(client, "select count(*) from interpretation_attempts")[0][0] >= 2


def test_ten_starts_per_rolling_hour_for_one_owner(env, migrated, owner_a, make_client) -> None:
    runner = CaseRunner(*[turn_result(case("concrete-thesis")["provider"]) for _ in range(10)])
    client = make_client(runner)
    owner = client.get("/v1/me", headers=owner_a).json()["user_id"]

    assert [start(client, owner_a) for _ in range(10)] == [201] * 10
    refused = client.post("/v1/research/requests", json=intake_body("concrete-thesis"), headers=owner_a)
    assert refused.status_code == 429 and refused.json()["code"] == "turn_limit_reached"
    assert rows(client, "select count(*) from interpretation_attempts where owner_id = :o", o=uuid.UUID(owner))[0][0] == 10


def test_another_owner_has_their_own_window(env, migrated, owner_a, owner_b, make_client) -> None:
    runner = CaseRunner(*[turn_result(case("concrete-thesis")["provider"]) for _ in range(11)])
    client = make_client(runner)

    assert [start(client, owner_a) for _ in range(10)] == [201] * 10
    assert start(client, owner_b) == 201
