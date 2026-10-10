"""Authenticated immutable spot-replay API behavior."""

from __future__ import annotations

import subprocess
import uuid

import pytest

from flows import compiled_thesis, publication_body


def _saved_revision(client, owner_a):
    bundle = compiled_thesis(client, owner_a)
    body = publication_body(bundle)
    response = client.post(
        f"/v1/strategies/{body['strategy']['strategy_id']}/revisions",
        json=body,
        headers=owner_a,
    )
    assert response.status_code == 201, response.text
    return body["strategy"], response.json()


def _body(strategy, revision, *, key: str = "replay-key"):
    return {
        "idempotency_key": key,
        "strategy_id": strategy["strategy_id"],
        "strategy_revision_id": revision["revision_id"],
        "dataset_fixture_id": "p13.wc01/1",
        "run_configuration_id": f"synthetic-config-{uuid.uuid4()}",
        "window_start": "2026-10-01T12:05:00Z",
        "window_end": "2026-10-01T12:35:00Z",
        "initial_cash_quote": "1000",
        "initial_base_amount": "0",
        "initial_basis_quote": "0",
        "essential_fields": {
            "entry": {"state": "BOUND", "essential_dependencies": [
                {"series": "price", "offset_buckets": 0},
                {"series": "price", "offset_buckets": -3},
            ]},
            "exit": {"state": "BOUND", "essential_dependencies": [
                {"series": "price", "offset_buckets": 0},
                {"series": "price", "offset_buckets": -1},
            ]},
        },
    }


def test_saved_strategy_replay_is_idempotent_and_retrievable_for_its_owner(client, owner_a):
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision)

    created = client.post("/v1/spot-replays", json=body, headers=owner_a)

    assert created.status_code == 201, created.text
    saved = created.json()
    assert saved["content"]["strategy_revision_id"] == revision["revision_id"]
    assert saved["content"]["dataset_fixture_id"] == "p13.wc01/1"
    assert saved["content"]["result"]["evidence_class"] == "SYNTHETIC_FIXTURE"
    assert saved["content"]["result"]["status"] == "COMPLETE", saved["content"]["result"]
    assert saved["content"]["result"]["samples"][0]["at"] == "2026-10-01T12:05:00.000000Z"
    assert [event["status"] for event in saved["content"]["result"]["events"]
            if event.get("kind") == "ORDER" and event.get("status") in {"BUY_FILLED", "SELL_FILLED"}] == [
                "BUY_FILLED", "SELL_FILLED"]
    assert saved["content"]["result"]["metrics"]["completed_trade_pairs"] == 1
    assert saved["content"]["result"]["metrics"]["gain_loss_quote"] == (
        "-9.48867661691542288557213930348258706467661691542")
    assert saved["content"]["result"]["samples"][-1]["cash_quote"] == (
        "990.51132338308457711442786069651741293532338308458")
    fills = [event["fill_price"] for event in saved["content"]["result"]["events"]
             if event.get("kind") == "ORDER" and event.get("status") in {"BUY_FILLED", "SELL_FILLED"}]
    assert fills == ["10.050", "9.1540"]

    replay = client.post("/v1/spot-replays", json=body, headers=owner_a)
    assert replay.status_code == 200
    assert replay.headers["idempotent-replay"] == "true"
    assert replay.json() == saved

    reopened = client.get(f"/v1/spot-replays/{saved['replay_id']}", headers=owner_a)
    assert reopened.status_code == 200
    assert reopened.json() == saved


def test_saved_strategy_replay_is_not_visible_to_another_owner(client, owner_a, owner_b):
    strategy, revision = _saved_revision(client, owner_a)
    created = client.post("/v1/spot-replays", json=_body(strategy, revision), headers=owner_a)
    assert created.status_code == 201, created.text

    foreign = client.get(f"/v1/spot-replays/{created.json()['replay_id']}", headers=owner_b)

    assert foreign.status_code == 404


def test_reusing_a_replay_key_with_changed_inputs_conflicts_without_a_second_row(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision)
    before = pg.psql("select count(*) from spot_replay_runs")
    first = client.post("/v1/spot-replays", json=body, headers=owner_a)
    assert first.status_code == 201, first.text
    changed = {**body, "initial_cash_quote": "999"}

    conflict = client.post("/v1/spot-replays", json=changed, headers=owner_a)

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_key_reused"
    assert pg.psql("select count(*) from spot_replay_runs") == str(int(before) + 1)


def test_another_owner_cannot_run_a_foreign_saved_revision(client, owner_a, owner_b, pg):
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key="foreign-revision")
    before = pg.psql("select count(*) from spot_replay_runs")

    response = client.post("/v1/spot-replays", json=body, headers=owner_b)

    assert response.status_code == 404
    assert pg.psql("select count(*) from spot_replay_runs") == before


def test_failed_replay_insert_rolls_back_without_a_partial_saved_result(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key="atomic-failure")
    before = pg.psql("select count(*) from spot_replay_runs")
    configuration_before = pg.psql("select count(*) from spot_replay_configurations")
    pg.psql("CREATE FUNCTION p13_test_reject_spot_replay() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'p13_test_reject_spot_replay'; END $$")
    pg.psql("CREATE TRIGGER p13_test_reject_spot_replay BEFORE INSERT ON spot_replay_runs "
            "FOR EACH ROW EXECUTE FUNCTION p13_test_reject_spot_replay()")
    try:
        response = client.post("/v1/spot-replays", json=body, headers=owner_a)
        assert response.status_code == 500
        assert pg.psql("select count(*) from spot_replay_runs") == before
        assert pg.psql("select count(*) from spot_replay_configurations") == configuration_before
    finally:
        pg.psql("DROP TRIGGER p13_test_reject_spot_replay ON spot_replay_runs")
        pg.psql("DROP FUNCTION p13_test_reject_spot_replay()")


def test_saved_replay_rows_reject_update_and_delete(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    created = client.post("/v1/spot-replays", json=_body(strategy, revision), headers=owner_a)
    assert created.status_code == 201, created.text
    replay_id = created.json()["replay_id"]

    with pytest.raises(subprocess.CalledProcessError) as update_error:
        pg.psql(f"update spot_replay_runs set content_sha256 = repeat('0', 64) where replay_id = '{replay_id}'")
    assert "edge-os: spot_replay_runs rows are immutable" in update_error.value.stderr
    with pytest.raises(subprocess.CalledProcessError) as delete_error:
        pg.psql(f"delete from spot_replay_runs where replay_id = '{replay_id}'")
    assert "edge-os: spot_replay_runs rows are immutable" in delete_error.value.stderr
    assert pg.psql(f"select count(*) from spot_replay_runs where replay_id = '{replay_id}'") == "1"
    configuration_id = created.json()["content"]["run_configuration_id"]
    with pytest.raises(subprocess.CalledProcessError) as configuration_update_error:
        pg.psql("update spot_replay_configurations set configuration_sha256 = repeat('0', 64) "
                f"where run_configuration_id = '{configuration_id}'")
    assert "edge-os: spot_replay_configurations rows are immutable" in configuration_update_error.value.stderr
    with pytest.raises(subprocess.CalledProcessError) as configuration_delete_error:
        pg.psql(f"delete from spot_replay_configurations where run_configuration_id = '{configuration_id}'")
    assert "edge-os: spot_replay_configurations rows are immutable" in configuration_delete_error.value.stderr
    assert pg.psql(
        f"select count(*) from spot_replay_configurations where run_configuration_id = '{configuration_id}'") == "1"


def test_spot_replay_requires_an_authenticated_owner(client):
    response = client.post("/v1/spot-replays", json={})

    assert response.status_code == 401
