"""Real uvicorn processes: restart, concurrency, startup failure and health (T2, T3, T11, M3)."""

from __future__ import annotations

import uuid

import httpx

import harness
from conftest import LiveApi, run_threads
from flows import HUNCH, THESIS, RESTRICTIONS, publication_body


def auth(signer, did):
    return {"Authorization": f"Bearer {signer.token(did)}"}


def new_did(prefix="live"):
    return f"did:privy:{prefix}-{uuid.uuid4().hex}"


def http(api, method, path, headers, **kwargs):
    return httpx.request(method, api.url + path, headers=headers, timeout=30, **kwargs)


def thesis_body():
    return {"original_request": THESIS, "restrictions": RESTRICTIONS, "requested_job": "CREATE_STRATEGY",
            "input_class": "CONCRETE_THESIS"}


def compiled(api, headers):
    bundle = http(api, "POST", "/v1/research/requests", headers, json=thesis_body()).json()
    return http(api, "POST", f"/v1/research/requests/{bundle['intake']['record_id']}/clarifications", headers, json={
        "previous_revision_id": bundle["head"]["interpretation_revision_id"],
        "question_id": "adopt-suggested-settings", "choice_id": "adopt"}).json()


def test_t3_concurrent_first_requests_create_one_user(live_api, signer, pg):
    for _ in range(20):
        did = new_did("race")
        headers = auth(signer, did)
        results = run_threads(8, lambda _i: http(live_api, "GET", "/v1/me", headers))
        assert {r.status_code for r in results} == {200}
        assert len({r.json()["user_id"] for r in results}) == 1
        assert pg.psql(f"select count(*) from users where privy_did = '{did}'") == "1"


def test_t2_restart_reopens_the_same_record(live_api, signer, pg):
    headers = auth(signer, new_did("restart"))
    done = compiled(live_api, headers)
    body = publication_body(done)
    published = http(live_api, "POST", f"/v1/strategies/{body['strategy']['strategy_id']}/revisions", headers,
                     json=body).json()
    live_api.stop()
    live_api.start()
    sid = body["strategy"]["strategy_id"]
    reopened = http(live_api, "GET", f"/v1/research/requests/{done['intake']['record_id']}", headers).json()
    assert reopened["intake"] == done["intake"]
    assert reopened["revisions"][0]["revision_id"] == published["revision_id"]
    revision = http(live_api, "GET", f"/v1/strategies/{sid}/revisions/{published['revision_id']}", headers).json()
    assert revision["content_sha256"] == published["content_sha256"]
    # retry after restart still returns the original identity
    replay = http(live_api, "POST", f"/v1/strategies/{sid}/revisions", headers, json=body)
    assert replay.status_code == 200 and replay.json() == published
    # another owner is still denied after restart
    assert http(live_api, "GET", f"/v1/research/requests/{done['intake']['record_id']}",
                auth(signer, new_did("other"))).status_code == 404


def test_concurrent_same_key_publication_returns_one_identity(live_api, signer, pg):
    headers = auth(signer, new_did("pubrace"))
    done = compiled(live_api, headers)
    body = publication_body(done, key="race-key")
    sid = body["strategy"]["strategy_id"]
    results = run_threads(8, lambda _i: http(live_api, "POST", f"/v1/strategies/{sid}/revisions", headers, json=body))
    assert {r.status_code for r in results} <= {200, 201}
    assert sum(r.status_code == 201 for r in results) == 1
    assert len({r.json()["revision_id"] for r in results}) == 1
    assert pg.psql(f"select count(*) from strategy_revisions where strategy_id = '{sid}'") == "1"


def test_concurrent_root_publications_with_different_keys_have_one_winner(live_api, signer, pg):
    headers = auth(signer, new_did("rootrace"))
    done = compiled(live_api, headers)
    sid = done["head"]["strategy_id"]
    bodies = [publication_body(done) for _ in range(8)]
    results = run_threads(8, lambda i: http(live_api, "POST", f"/v1/strategies/{sid}/revisions", headers, json=bodies[i]))
    codes = sorted(r.status_code for r in results)
    assert codes == [201] + [409] * 7, codes
    assert {r.json()["code"] for r in results if r.status_code == 409} == {"parent_revision_conflict"}
    assert pg.psql(f"select count(*) from strategy_revisions where strategy_id = '{sid}'") == "1"
    assert pg.psql(f"select count(*) from idempotency_records where path = '/v1/strategies/{sid}/revisions'") == "1"


def test_concurrent_clarifications_fork_nothing(live_api, signer, pg):
    headers = auth(signer, new_did("answerrace"))
    bundle = http(live_api, "POST", "/v1/research/requests", headers, json={
        "original_request": HUNCH, "restrictions": [], "requested_job": "CREATE_STRATEGY",
        "input_class": "LOOSE_INTUITION"}).json()
    path = f"/v1/research/requests/{bundle['intake']['record_id']}/clarifications"
    payload = {"previous_revision_id": bundle["head"]["interpretation_revision_id"], "question_id": "choose-entry",
               "choice_id": "g3-1pct"}
    results = run_threads(8, lambda _i: http(live_api, "POST", path, headers, json=payload))
    assert sorted(r.status_code for r in results) == [201] + [409] * 7
    count = pg.psql("select count(*) from records where record_type = 'PromptInterpretation' and "
                    f"intake_record_id = '{bundle['intake']['record_id']}'")
    assert count == "2"


def block_database(pg):
    """Make the test database refuse connections and drop live ones (a stopped database, without a port change)."""
    pg.psql(f"alter database {pg.database} allow_connections false", db="postgres")
    pg.psql(f"select pg_terminate_backend(pid) from pg_stat_activity where datname = '{pg.database}'", db="postgres")


def unblock_database(pg):
    pg.psql(f"alter database {pg.database} allow_connections true", db="postgres")


def test_t11_health_and_readiness(env, migrated, pg, tmp_path):
    api = LiveApi(env, tmp_path).start()
    try:
        health = httpx.get(api.url + "/healthz").json()
        assert set(health) == {"status", "build_sha", "started_at"}
        text = httpx.get(api.url + "/healthz").text + httpx.get(api.url + "/readyz").text
        for forbidden in ("postgres", "edge-os-test-app", pg.password, "BEGIN"):
            assert forbidden not in text
        ready = httpx.get(api.url + "/readyz")
        assert ready.status_code == 200 and ready.json()["schema_revision"] == "0009"
        pg.psql("update alembic_version set version_num = '9999'")
        drift = httpx.get(api.url + "/readyz")
        assert drift.status_code == 503 and httpx.get(api.url + "/healthz").status_code == 200
        pg.psql("update alembic_version set version_num = '0009'")
        assert httpx.get(api.url + "/readyz").status_code == 200
        block_database(pg)
        try:
            down = httpx.get(api.url + "/readyz", timeout=60)
            assert down.status_code == 503
            assert httpx.get(api.url + "/healthz").status_code == 200  # liveness never touches the database
        finally:
            unblock_database(pg)
        assert httpx.get(api.url + "/readyz").status_code == 200
    finally:
        api.stop()


def test_a14_database_down_during_principal_lookup(env, migrated, signer, pg, tmp_path):
    api = LiveApi(env, tmp_path).start()
    try:
        headers = auth(signer, new_did("dbdown"))
        assert http(api, "GET", "/v1/me", headers).status_code == 200
        block_database(pg)
        try:
            response = httpx.get(api.url + "/v1/me", headers=auth(signer, new_did("dbdown2")), timeout=60)
            assert response.status_code == 503 and response.json()["code"] == "service_unavailable"
        finally:
            unblock_database(pg)
        assert http(api, "GET", "/v1/me", headers).status_code == 200
    finally:
        api.stop()


def test_m3_unmigrated_database_stops_startup(signer, tmp_path):
    other = harness.Postgres(harness.new_run_id()).start()
    try:
        env = harness.api_env(database_url=other.url, public_pem=signer.public_pem, previous_pem=None,
                              cors=["http://127.0.0.1:3999"])
        port = harness.free_port()
        process = harness.start_api(env, port, tmp_path, name="unmigrated")
        try:
            assert process.popen.wait(timeout=60) != 0
        finally:
            process.stop()
        log = (tmp_path / "unmigrated.log").read_text()
        assert "does not match migration head" in log
        assert other.password not in log
    finally:
        other.stop_and_remove()
        assert other.leftovers() == []
