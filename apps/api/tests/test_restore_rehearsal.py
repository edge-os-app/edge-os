"""#58 Stage 2 restore and rollback rehearsal on an owned, run-labelled database.

Mirrors `docs/qualification/public-runtime/RESTORE_ROLLBACK_RUNBOOK.md`: dump, restore into a fresh database, check
schema and readiness, compare saved state, then downgrade 0010 → 0009 and upgrade again without losing quota totals.
Everything happens inside this test's own PostgreSQL container.
"""

from __future__ import annotations

import subprocess
import sys
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

import harness
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app
from research_flows import declare, start


def alembic(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=harness.API_DIR, env=env,
                          capture_output=True, text=True, timeout=180)


def test_dump_restore_check_and_rollback_keep_the_saved_state(env, migrated, pg, owner_a):
    research_env = {**env, "EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"}
    with TestClient(create_app(load_settings(research_env))) as client:
        intake_id, declaration_id, _ = declare(client, owner_a)
        job = start(client, owner_a, intake_id, declaration_id).json()
        budget_before = client.get("/v1/research/budget", headers=owner_a).json()
    restored = f"{pg.database}_restore_{uuid.uuid4().hex[:6]}"
    dump = f"/tmp/{restored}.dump"
    harness.sh(["docker", "exec", pg.container_id, "pg_dump", "-U", "postgres", "-Fc", "-f", dump, pg.database])
    pg.psql(f"create database {restored}", db="postgres")
    try:
        harness.sh(["docker", "exec", pg.container_id, "pg_restore", "-U", "postgres", "-d", restored, dump])
        url = make_url(env["EDGE_OS_DATABASE_URL"]).set(database=restored).render_as_string(hide_password=False)
        restored_env = {**research_env, "EDGE_OS_DATABASE_URL": url}
        check = alembic(restored_env, "check")
        assert check.returncode == 0, check.stdout + check.stderr
        with TestClient(create_app(load_settings(restored_env))) as client:
            assert client.get("/readyz").json()["status"] == "ready"
            assert client.get("/v1/research/budget", headers=owner_a).json() == budget_before
            assert client.get(f"/v1/research/investigation-jobs/{job['job_id']}", headers=owner_a).json()["state"] == "RESERVED"
        allocations = lambda: pg.psql(  # noqa: E731 - one inline reader
            "select string_agg(scope || ':' || resource || ':' || reserved || ':' || consumed, ',' order by scope, "
            "resource, owner_key) from usage_local.usage_allocations", db=restored)
        before_rollback = allocations()
        down = alembic(restored_env, "downgrade", "0009")
        assert down.returncode == 0, down.stderr
        assert pg.psql("select count(*) from research_local.research_budgets", db=restored) != "0"
        up = alembic(restored_env, "upgrade", "head")
        assert up.returncode == 0, up.stderr
        owner_rows = lambda text: sorted(item for item in text.split(",") if item.startswith("OWNER"))  # noqa: E731
        assert owner_rows(allocations()) == owner_rows(before_rollback)
    finally:
        harness.sh(["docker", "exec", pg.container_id, "rm", "-f", dump], check=False)
        pg.psql(f"drop database if exists {restored} with (force)", db="postgres")
