"""#58 Stage 2 runtime guards: shared write rate, active research jobs, statement timeout and worker schema drift."""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from edge_os_api.core import worker_loop
from edge_os_api.core.database import SchemaMismatch, make_engine
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from research_flows import declare, start


def app(env, **overrides):
    return TestClient(create_app(load_settings({**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded", **overrides})))


def test_writes_over_the_owner_window_get_429_and_reads_continue(env, migrated, owner_a, owner_b):
    with app(env, EDGE_OS_WRITE_RATE_PER_MINUTE="3") as client:
        body = {"original_request": "x", "restrictions": [], "requested_job": "COMPARE", "input_class": "LOOSE_INTUITION"}
        statuses = [client.post("/v1/research/requests", headers=owner_a, json=body).status_code for _ in range(4)]
        assert statuses == [201, 201, 201, 429]
        refused = client.post("/v1/research/requests", headers=owner_a, json=body)
        assert refused.status_code == 429 and refused.json()["code"] == "rate_limited"
        assert 1 <= int(refused.headers["Retry-After"]) <= 61
        assert client.get("/v1/research/requests", headers=owner_a).status_code == 200  # reads are not limited
        assert client.post("/v1/research/requests", headers=owner_b, json=body).status_code == 201  # other owner


def test_write_window_is_shared_by_separate_application_processes(env, migrated, owner_a):
    body = {"original_request": "x", "restrictions": [], "requested_job": "COMPARE", "input_class": "LOOSE_INTUITION"}
    with app(env, EDGE_OS_WRITE_RATE_PER_MINUTE="2") as first, app(env, EDGE_OS_WRITE_RATE_PER_MINUTE="2") as second:
        assert first.post("/v1/research/requests", headers=owner_a, json=body).status_code == 201
        assert second.post("/v1/research/requests", headers=owner_a, json=body).status_code == 201
        assert first.post("/v1/research/requests", headers=owner_a, json=body).status_code == 429


def test_active_research_jobs_per_owner_are_bounded(env, migrated, owner_a):
    with app(env, EDGE_OS_RESEARCH_MAX_ACTIVE_JOBS="2") as client:
        intake_id, declaration_id, _ = declare(client, owner_a)
        assert start(client, owner_a, intake_id, declaration_id).status_code == 201
        assert start(client, owner_a, intake_id, declaration_id).status_code == 201
        refused = start(client, owner_a, intake_id, declaration_id)
        assert refused.status_code == 409 and refused.json()["code"] == "too_many_active_jobs"
        budget = client.get("/v1/research/budget", headers=owner_a).json()
        assert budget["reserved"]["provider_requests"] == 4  # the refused start reserved nothing


def test_statement_timeout_bounds_a_slow_statement(settings):
    engine = make_engine(settings.database_url, 1000)
    with engine.connect() as connection, pytest.raises(OperationalError):
        connection.execute(text("select pg_sleep(3)"))
    engine.dispose()


def test_worker_loop_stops_before_any_effect_on_schema_drift(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(worker_loop, "require_head", lambda engine: (_ for _ in ()).throw(
        SchemaMismatch("database schema revision '0009' does not match migration head '0010'")))
    with caplog.at_level(logging.ERROR):
        code = worker_loop.run("worker", object(), lambda: calls.append(1) or [], once=False, interval=0,
                               log=logging.getLogger("t"), sleep=lambda _: None)
    assert code == worker_loop.DRIFT_EXIT_CODE and calls == []
    assert "stopped before any effect: schema drift" in caplog.text


def test_worker_loop_skips_a_pass_when_the_database_is_unreachable(monkeypatch, caplog):
    calls, passes = [], iter([OperationalError("x", {}, Exception("down")), None])

    def head(engine):
        error = next(passes)
        if error is not None:
            raise error

    monkeypatch.setattr(worker_loop, "require_head", head)
    sleeps = []
    with caplog.at_level(logging.ERROR):
        # First pass: unreachable, step skipped. Then `once` is false, so run a second pass and stop via sleep.
        def sleep(_):
            sleeps.append(1)
            if len(sleeps) == 2:
                raise KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt):
            worker_loop.run("worker", object(), lambda: calls.append(1) or [], once=False, interval=0,
                            log=logging.getLogger("t"), sleep=sleep)
    assert calls == [1] and "database unavailable" in caplog.text


def test_drifted_workers_exit_with_code_3(env, migrated, pg):
    import subprocess
    import sys

    import harness

    pg.psql("update alembic_version set version_num = '0009'")
    try:
        for module in ("edge_os_api.execution.worker", "edge_os_api.research.investigation_jobs"):
            result = subprocess.run([sys.executable, "-m", module, "--once"], cwd=harness.API_DIR, env=env,
                                    capture_output=True, text=True, timeout=120)
            assert result.returncode == 3, (module, result.stderr[-500:])
            assert "schema drift" in result.stderr
    finally:
        pg.psql("update alembic_version set version_num = '0010'")
