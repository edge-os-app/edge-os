"""Public P13 regressions for immutable owner-scoped configuration identities."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import harness
from sqlalchemy import MetaData, Table, create_engine, select, text

from conftest import run_threads
from edge_os_api.records import contract_adapter as record_contract
from test_spot_replay_api import _body, _saved_revision


def test_same_owner_configuration_id_rejects_changed_settings_with_a_fresh_key(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    original = _body(strategy, revision, key=f"configuration-original-{uuid.uuid4()}")
    count_before = int(pg.psql("select count(*) from spot_replay_runs"))

    first = client.post("/v1/spot-replays", headers=owner_a, json=original)
    changed = copy.deepcopy(original)
    changed["idempotency_key"] = f"configuration-changed-{uuid.uuid4()}"
    changed["initial_cash_quote"] = "999"
    conflict = client.post("/v1/spot-replays", headers=owner_a, json=changed)
    retry = client.post("/v1/spot-replays", headers=owner_a, json=original)

    assert first.status_code == 201, first.text
    assert conflict.status_code == 409, "same immutable configuration ID accepted changed starting cash"
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert int(pg.psql("select count(*) from spot_replay_runs")) == count_before + 1


def test_identical_configuration_with_a_new_key_and_changed_settings_with_a_new_id_are_allowed(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    original = _body(strategy, revision, key=f"configuration-original-{uuid.uuid4()}")
    first = client.post("/v1/spot-replays", headers=owner_a, json=original)

    same_content = copy.deepcopy(original)
    same_content["idempotency_key"] = f"configuration-repeat-{uuid.uuid4()}"
    repeated = client.post("/v1/spot-replays", headers=owner_a, json=same_content)

    changed_configuration = copy.deepcopy(original)
    changed_configuration["idempotency_key"] = f"configuration-new-id-{uuid.uuid4()}"
    changed_configuration["run_configuration_id"] = f"independent-config-{uuid.uuid4()}"
    changed_configuration["initial_cash_quote"] = "999"
    independent = client.post("/v1/spot-replays", headers=owner_a, json=changed_configuration)

    assert first.status_code == 201, first.text
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["content"]["inputs"] == first.json()["content"]["inputs"]
    assert repeated.json()["content"]["result"] == first.json()["content"]["result"]
    assert independent.status_code == 201, independent.text
    assert independent.json()["content"]["inputs"]["initial_cash_quote"] == "999"
    assert pg.psql(
        "select count(*) from spot_replay_configurations "
        f"where run_configuration_id in ('{original['run_configuration_id']}', "
        f"'{changed_configuration['run_configuration_id']}')") == "2"


@pytest.mark.parametrize(("dimension", "replacement"), [
    ("window_start", "2026-10-01T12:00:00Z"),
    ("window_end", "2026-10-01T12:30:00Z"),
    ("initial_base_amount", "1"),
    ("initial_basis_quote", "12"),
    ("essential_entry", -2),
    ("essential_exit", -2),
], ids=["start", "end", "base", "basis", "entry-descriptor", "exit-descriptor"])
def test_same_configuration_id_rejects_each_changed_input_dimension(client, owner_a, dimension, replacement):
    strategy, revision = _saved_revision(client, owner_a)
    original = _body(strategy, revision, key=f"configuration-original-{uuid.uuid4()}")
    first = client.post("/v1/spot-replays", headers=owner_a, json=original)
    changed = copy.deepcopy(original)
    changed["idempotency_key"] = f"configuration-changed-{uuid.uuid4()}"
    if dimension in {"essential_entry", "essential_exit"}:
        selected = "entry" if dimension == "essential_entry" else "exit"
        changed["essential_fields"][selected]["essential_dependencies"][0]["offset_buckets"] = replacement
    else:
        changed[dimension] = replacement

    conflict = client.post("/v1/spot-replays", headers=owner_a, json=changed)

    assert first.status_code == 201, first.text
    assert conflict.status_code == 409, f"changed {dimension} retained a conflicting configuration ID"


def test_same_configuration_id_cannot_bind_another_saved_strategy_revision(client, owner_a):
    first_strategy, first_revision = _saved_revision(client, owner_a)
    second_strategy, second_revision = _saved_revision(client, owner_a)
    original = _body(first_strategy, first_revision, key=f"configuration-original-{uuid.uuid4()}")
    first = client.post("/v1/spot-replays", headers=owner_a, json=original)
    changed_revision = _body(second_strategy, second_revision, key=f"configuration-revision-{uuid.uuid4()}")
    changed_revision["run_configuration_id"] = original["run_configuration_id"]

    conflict = client.post("/v1/spot-replays", headers=owner_a, json=changed_revision)

    assert first.status_code == 201, first.text
    assert conflict.status_code == 409


def test_configuration_identity_namespace_is_scoped_to_each_owner(client, owner_a, owner_b):
    strategy_a, revision_a = _saved_revision(client, owner_a)
    strategy_b, revision_b = _saved_revision(client, owner_b)
    config_id = f"owner-scoped-config-{uuid.uuid4()}"
    request_a = _body(strategy_a, revision_a, key=f"owner-a-{uuid.uuid4()}")
    request_a["run_configuration_id"] = config_id
    request_b = _body(strategy_b, revision_b, key=f"owner-b-{uuid.uuid4()}")
    request_b["run_configuration_id"] = config_id
    request_b["initial_cash_quote"] = "999"

    saved_a = client.post("/v1/spot-replays", headers=owner_a, json=request_a)
    saved_b = client.post("/v1/spot-replays", headers=owner_b, json=request_b)

    assert saved_a.status_code == 201, saved_a.text
    assert saved_b.status_code == 201, saved_b.text
    assert saved_a.json()["content"]["owner_id"] != saved_b.json()["content"]["owner_id"]


def test_simultaneous_conflicting_configuration_posts_create_only_one_meaning(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    original = _body(strategy, revision, key=f"configuration-race-a-{uuid.uuid4()}")
    conflicting = copy.deepcopy(original)
    conflicting["idempotency_key"] = f"configuration-race-b-{uuid.uuid4()}"
    conflicting["initial_cash_quote"] = "999"
    before = int(pg.psql("select count(*) from spot_replay_runs"))

    responses = run_threads(2, lambda index: client.post(
        "/v1/spot-replays", headers=owner_a, json=(original if index == 0 else conflicting)))

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert int(pg.psql("select count(*) from spot_replay_runs")) == before + 1
    assert pg.psql(
        "select count(*) from spot_replay_configurations "
        f"where run_configuration_id = '{original['run_configuration_id']}'") == "1"


def test_simultaneous_identical_configuration_posts_with_distinct_keys_are_both_saved(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    original = _body(strategy, revision, key=f"configuration-same-a-{uuid.uuid4()}")
    repeated = copy.deepcopy(original)
    repeated["idempotency_key"] = f"configuration-same-b-{uuid.uuid4()}"
    before = int(pg.psql("select count(*) from spot_replay_runs"))

    responses = run_threads(2, lambda index: client.post(
        "/v1/spot-replays", headers=owner_a, json=(original if index == 0 else repeated)))

    assert [response.status_code for response in responses] == [201, 201]
    assert int(pg.psql("select count(*) from spot_replay_runs")) == before + 2
    assert pg.psql(
        "select count(*) from spot_replay_configurations "
        f"where run_configuration_id = '{original['run_configuration_id']}'") == "1"


def test_simultaneous_exact_same_key_posts_recover_one_immutable_response(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"configuration-same-key-{uuid.uuid4()}")
    before = int(pg.psql("select count(*) from spot_replay_runs"))

    responses = run_threads(2, lambda _: client.post("/v1/spot-replays", headers=owner_a, json=body))

    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
    assert int(pg.psql("select count(*) from spot_replay_runs")) == before + 1


def _migration_target(pg, suffix: str) -> tuple[str, dict[str, str]]:
    database_name = f"p13_identity_{suffix}_{uuid.uuid4().hex[:10]}"
    pg.psql(f"CREATE DATABASE {database_name}")
    environment = harness.base_env()
    environment["EDGE_OS_DATABASE_URL"] = f"{pg.url.rsplit('/', 1)[0]}/{database_name}"
    return database_name, environment


def _upgrade_to(environment: dict[str, str], revision: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([harness.api_python(), "-m", "alembic", "upgrade", revision],
                          cwd=harness.API_DIR, env=environment, capture_output=True, text=True, timeout=120)


def _copy_legacy_replay_rows(source_url: str, target_url: str, owner_id: str,
                             revision_id: str, replay_ids: list[str], *, malformed_inputs: bool = False
                             ) -> list[dict[str, Any]]:
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)
    try:
        metadata = MetaData()
        names = ("users", "records", "strategy_revisions", "spot_replay_runs")
        tables = {name: Table(name, metadata, autoload_with=source_engine) for name in names}
        with source_engine.connect() as source:
            user = dict(source.execute(select(tables["users"]).where(
                tables["users"].c.id == uuid.UUID(owner_id))).mappings().one())
            records = [dict(row) for row in source.execute(select(tables["records"]).where(
                tables["records"].c.owner_id == uuid.UUID(owner_id)).order_by(tables["records"].c.seq)).mappings()]
            revision = dict(source.execute(select(tables["strategy_revisions"]).where(
                tables["strategy_revisions"].c.revision_id == uuid.UUID(revision_id))).mappings().one())
            runs = [dict(row) for row in source.execute(select(tables["spot_replay_runs"]).where(
                tables["spot_replay_runs"].c.replay_id.in_(replay_ids)).order_by(
                    tables["spot_replay_runs"].c.created_at)).mappings()]
        if malformed_inputs:
            malformed_content = copy.deepcopy(runs[0]["content"])
            del malformed_content["inputs"]["profile_version"]
            runs[0]["content"] = malformed_content
            runs[0]["content_sha256"] = record_contract.sha256_hex(malformed_content)
        with target_engine.begin() as target:
            target.execute(tables["users"].insert().values(user))
            for record in records:
                record.pop("seq")
                target.execute(tables["records"].insert().values(record))
            target.execute(tables["strategy_revisions"].insert().values(revision))
            for run in runs:
                target.execute(tables["spot_replay_runs"].insert().values(run))
        return runs
    finally:
        source_engine.dispose()
        target_engine.dispose()


def test_migration_backfills_same_meaning_and_refuses_conflicting_legacy_history(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    original = _body(strategy, revision, key=f"legacy-first-{uuid.uuid4()}")
    first = client.post("/v1/spot-replays", headers=owner_a, json=original)
    repeated = copy.deepcopy(original)
    repeated["idempotency_key"] = f"legacy-repeat-{uuid.uuid4()}"
    second = client.post("/v1/spot-replays", headers=owner_a, json=repeated)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    owner_id = first.json()["content"]["owner_id"]
    replay_ids = [first.json()["replay_id"], second.json()["replay_id"]]
    unavailable_records = []
    for name, binding in (("unbound", {"state": "UNBOUND"}),
                          ("bound-null", {"state": "BOUND", "essential_dependencies": None})):
        unavailable_body = copy.deepcopy(original)
        unavailable_body["idempotency_key"] = f"legacy-{name}-{uuid.uuid4()}"
        unavailable_body["run_configuration_id"] = f"legacy-{name}-{uuid.uuid4()}"
        unavailable_body["essential_fields"]["entry"] = binding
        unavailable = client.post("/v1/spot-replays", headers=owner_a, json=unavailable_body)
        assert unavailable.status_code == 201, unavailable.text
        assert unavailable.json()["content"]["result"]["status"] == "UNAVAILABLE"
        unavailable_records.append(unavailable.json())
        replay_ids.append(unavailable.json()["replay_id"])

    valid_name, valid_environment = _migration_target(pg, "valid")
    bad_name, bad_environment = _migration_target(pg, "conflict")
    try:
        assert _upgrade_to(valid_environment, "0004").returncode == 0
        valid_rows = _copy_legacy_replay_rows(pg.url, valid_environment["EDGE_OS_DATABASE_URL"],
                                              owner_id, revision["revision_id"], replay_ids)
        valid_url = valid_environment["EDGE_OS_DATABASE_URL"]
        valid_engine = create_engine(valid_url)
        try:
            with valid_engine.connect() as connection:
                original_rows = [dict(row) for row in connection.execute(text(
                    "SELECT replay_id, content_sha256, content FROM spot_replay_runs ORDER BY created_at")).mappings()]
            assert len(original_rows) == len(valid_rows) == 4
            assert {row["content"]["result"]["status"] for row in original_rows} == {"COMPLETE", "UNAVAILABLE"}
        finally:
            valid_engine.dispose()

        upgraded = _upgrade_to(valid_environment, "head")
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
        valid_engine = create_engine(valid_url)
        try:
            with valid_engine.connect() as connection:
                after_rows = [dict(row) for row in connection.execute(text(
                    "SELECT replay_id, content_sha256, content FROM spot_replay_runs ORDER BY created_at")).mappings()]
                bindings = connection.execute(text(
                    "SELECT run_configuration_id, configuration_sha256 FROM spot_replay_configurations"
                )).mappings().all()
            assert after_rows == original_rows
            assert len(bindings) == 3
            expected_hashes = {
                original["run_configuration_id"]: record_contract.sha256_hex({
                    "schema_version": "p13.spot-replay-run/1", "inputs": first.json()["content"]["inputs"]}),
                **{record["content"]["run_configuration_id"]: record_contract.sha256_hex({
                    "schema_version": "p13.spot-replay-run/1", "inputs": record["content"]["inputs"]})
                   for record in unavailable_records},
            }
            assert {row["run_configuration_id"]: row["configuration_sha256"] for row in bindings} == expected_hashes
        finally:
            valid_engine.dispose()

        assert _upgrade_to(bad_environment, "0004").returncode == 0
        _copy_legacy_replay_rows(pg.url, bad_environment["EDGE_OS_DATABASE_URL"],
                                 owner_id, revision["revision_id"], replay_ids[:1])
        bad_engine = create_engine(bad_environment["EDGE_OS_DATABASE_URL"])
        try:
            metadata = MetaData()
            run_table = Table("spot_replay_runs", metadata, autoload_with=bad_engine)
            conflicting = copy.deepcopy(valid_rows[0])
            conflicting["replay_id"] = uuid.uuid4()
            conflicting["idempotency_key"] = f"legacy-conflict-{uuid.uuid4()}"
            conflicting["created_at"] = datetime.now(timezone.utc)
            conflicting_content = copy.deepcopy(conflicting["content"])
            conflicting_content["replay_id"] = str(conflicting["replay_id"])
            conflicting_content["idempotency"]["key"] = conflicting["idempotency_key"]
            conflicting_content["inputs"]["initial_cash_quote"] = "999"
            conflicting["content"] = conflicting_content
            conflicting["content_sha256"] = record_contract.sha256_hex(conflicting_content)
            conflicting["fingerprint"] = record_contract.sha256_hex({"legacy-conflict": conflicting["idempotency_key"]})
            conflicting_content["idempotency"]["fingerprint"] = conflicting["fingerprint"]
            conflicting["content_sha256"] = record_contract.sha256_hex(conflicting_content)
            with bad_engine.begin() as connection:
                connection.execute(run_table.insert().values(conflicting))
                before_rows = [dict(row) for row in connection.execute(text(
                    "SELECT replay_id, content_sha256, content FROM spot_replay_runs ORDER BY created_at"
                )).mappings()]
        finally:
            bad_engine.dispose()

        rejected = _upgrade_to(bad_environment, "head")
        assert rejected.returncode != 0
        assert "existing owner-scoped history has conflicting inputs" in rejected.stderr
        bad_engine = create_engine(bad_environment["EDGE_OS_DATABASE_URL"])
        try:
            with bad_engine.connect() as connection:
                after_rows = [dict(row) for row in connection.execute(text(
                    "SELECT replay_id, content_sha256, content FROM spot_replay_runs ORDER BY created_at"
                )).mappings()]
                revision_after = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                registry_exists = connection.execute(text(
                    "SELECT to_regclass('public.spot_replay_configurations') IS NOT NULL")).scalar_one()
            assert after_rows == before_rows
            assert revision_after == "0004"
            assert not registry_exists
        finally:
            bad_engine.dispose()
    finally:
        pg.psql(f"DROP DATABASE IF EXISTS {valid_name} WITH (FORCE)")
        pg.psql(f"DROP DATABASE IF EXISTS {bad_name} WITH (FORCE)")


def test_migration_refuses_malformed_legacy_inputs_without_rewriting_saved_rows(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"legacy-malformed-{uuid.uuid4()}")
    saved = client.post("/v1/spot-replays", headers=owner_a, json=body)
    assert saved.status_code == 201, saved.text
    database_name, environment = _migration_target(pg, "malformed")
    try:
        assert _upgrade_to(environment, "0004").returncode == 0
        _copy_legacy_replay_rows(pg.url, environment["EDGE_OS_DATABASE_URL"],
                                 saved.json()["content"]["owner_id"], revision["revision_id"],
                                 [saved.json()["replay_id"]], malformed_inputs=True)
        engine = create_engine(environment["EDGE_OS_DATABASE_URL"])
        try:
            with engine.connect() as connection:
                rows_before = [dict(row) for row in connection.execute(text(
                    "SELECT replay_id, content_sha256, content FROM spot_replay_runs")).mappings()]
            assert len(rows_before) == 1
            assert "profile_version" not in rows_before[0]["content"]["inputs"]
            assert record_contract.sha256_hex(rows_before[0]["content"]) == rows_before[0]["content_sha256"]
        finally:
            engine.dispose()

        rejected = _upgrade_to(environment, "head")
        assert rejected.returncode != 0
        assert "a saved replay identity is malformed" in rejected.stderr
        engine = create_engine(environment["EDGE_OS_DATABASE_URL"])
        try:
            with engine.connect() as connection:
                rows_after = [dict(row) for row in connection.execute(text(
                    "SELECT replay_id, content_sha256, content FROM spot_replay_runs")).mappings()]
                revision_after = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                registry_exists = connection.execute(text(
                    "SELECT to_regclass('public.spot_replay_configurations') IS NOT NULL")).scalar_one()
            assert rows_after == rows_before
            assert revision_after == "0004"
            assert not registry_exists
        finally:
            engine.dispose()
    finally:
        pg.psql(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")


@pytest.mark.parametrize("malformation", [
    "content-replay-id",
    "content-strategy-revision-id",
    "input-strategy-id",
    "descriptor-version",
    "descriptor-fields",
])
def test_migration_refuses_hash_consistent_legacy_identity_and_descriptor_malformations(
        client, owner_a, pg, malformation):
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"legacy-r7-{malformation}-{uuid.uuid4()}")
    saved = client.post("/v1/spot-replays", headers=owner_a, json=body)
    assert saved.status_code == 201, saved.text
    replay_id = saved.json()["replay_id"]
    owner_id = saved.json()["content"]["owner_id"]
    database_name, environment = _migration_target(pg, f"r7_{malformation.replace('-', '_')}")
    try:
        assert _upgrade_to(environment, "0004").returncode == 0
        _copy_legacy_replay_rows(pg.url, environment["EDGE_OS_DATABASE_URL"], owner_id,
                                 revision["revision_id"], [replay_id])
        engine = create_engine(environment["EDGE_OS_DATABASE_URL"])
        try:
            with engine.begin() as connection:
                connection.execute(text(
                    "ALTER TABLE spot_replay_runs DISABLE TRIGGER spot_replay_runs_immutable"))
                run = dict(connection.execute(text(
                    "SELECT * FROM spot_replay_runs WHERE replay_id = :replay_id"),
                    {"replay_id": uuid.UUID(replay_id)}).mappings().one())
                malformed = copy.deepcopy(run["content"])
                if malformation == "content-replay-id":
                    malformed["replay_id"] = str(uuid.uuid4())
                elif malformation == "content-strategy-revision-id":
                    different_revision = str(uuid.uuid4())
                    malformed["strategy_revision_id"] = different_revision
                    malformed["inputs"]["strategy_revision_id"] = different_revision
                    malformed["inputs"]["essential_evidence"]["strategy_revision"] = different_revision
                elif malformation == "input-strategy-id":
                    malformed["inputs"]["strategy_id"] = f"different-{uuid.uuid4()}"
                elif malformation == "descriptor-version":
                    malformed["inputs"]["essential_evidence"]["schema_version"] = (
                        "p12.essential-evidence/999")
                else:
                    malformed["inputs"]["essential_evidence"]["fields"] = "not-an-entry-exit-object"
                connection.execute(text(
                    "UPDATE spot_replay_runs SET content = :content, content_sha256 = :content_sha256 "
                    "WHERE replay_id = :replay_id"), {
                        "content": json.dumps(malformed),
                        "content_sha256": record_contract.sha256_hex(malformed),
                        "replay_id": uuid.UUID(replay_id),
                    })
                connection.execute(text(
                    "ALTER TABLE spot_replay_runs ENABLE TRIGGER spot_replay_runs_immutable"))
                rows_before = [dict(row) for row in connection.execute(text(
                    "SELECT * FROM spot_replay_runs ORDER BY created_at, replay_id")).mappings()]
            assert record_contract.sha256_hex(rows_before[0]["content"]) == rows_before[0]["content_sha256"]
        finally:
            engine.dispose()

        rejected = _upgrade_to(environment, "head")
        engine = create_engine(environment["EDGE_OS_DATABASE_URL"])
        try:
            with engine.connect() as connection:
                rows_after = [dict(row) for row in connection.execute(text(
                    "SELECT * FROM spot_replay_runs ORDER BY created_at, replay_id")).mappings()]
                version_after = connection.execute(text(
                    "SELECT version_num FROM alembic_version")).scalar_one()
                registry_exists = connection.execute(text(
                    "SELECT to_regclass('public.spot_replay_configurations') IS NOT NULL")).scalar_one()
                registry_rows = []
                if registry_exists:
                    registry_rows = [dict(row) for row in connection.execute(text(
                        "SELECT * FROM spot_replay_configurations ORDER BY owner_id, run_configuration_id"
                    )).mappings()]
        finally:
            engine.dispose()

        def json_safe(value: Any) -> Any:
            if isinstance(value, dict):
                return {str(key): json_safe(item) for key, item in value.items()}
            if isinstance(value, list):
                return [json_safe(item) for item in value]
            if isinstance(value, (datetime, uuid.UUID)):
                return value.isoformat() if isinstance(value, datetime) else str(value)
            return value

        record = {
            "malformation": malformation,
            "database": database_name,
            "upgrade_returncode": rejected.returncode,
            "upgrade_stdout": rejected.stdout,
            "upgrade_stderr": rejected.stderr,
            "source_rows_before": json_safe(rows_before),
            "source_rows_after": json_safe(rows_after),
            "revision_after": version_after,
            "registry_exists_after": registry_exists,
            "registry_rows_after": json_safe(registry_rows),
        }
        evidence_dir = os.environ.get("P13_R7_EVIDENCE_DIR")
        if evidence_dir:
            output = Path(evidence_dir)
            output.mkdir(parents=True, exist_ok=True)
            (output / f"red-{malformation}.json").write_text(
                json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")

        assert rejected.returncode != 0, f"migration admitted {malformation}"
        assert "cannot bind P13 configuration IDs" in rejected.stderr
        assert rows_after == rows_before
        assert version_after == "0004"
        assert not registry_exists
        assert not registry_rows
    finally:
        pg.psql(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")


def test_migration_preserves_api_authored_uppercase_strategy_revision_uuid(client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"legacy-uppercase-revision-{uuid.uuid4()}")
    body["strategy_revision_id"] = body["strategy_revision_id"].upper()
    saved_response = client.post("/v1/spot-replays", headers=owner_a, json=body)
    assert saved_response.status_code == 201, saved_response.text
    saved = saved_response.json()
    exact_read = client.get(f"/v1/spot-replays/{saved['replay_id']}", headers=owner_a)
    assert exact_read.status_code == 200 and exact_read.json() == saved

    database_name, environment = _migration_target(pg, "uppercase_revision")
    try:
        assert _upgrade_to(environment, "0004").returncode == 0
        _copy_legacy_replay_rows(pg.url, environment["EDGE_OS_DATABASE_URL"],
                                 saved["content"]["owner_id"], revision["revision_id"],
                                 [saved["replay_id"]])
        engine = create_engine(environment["EDGE_OS_DATABASE_URL"])
        try:
            with engine.connect() as connection:
                rows_before = [dict(row) for row in connection.execute(text(
                    "SELECT * FROM spot_replay_runs ORDER BY created_at, replay_id")).mappings()]
            upgrade = _upgrade_to(environment, "head")
            with engine.connect() as connection:
                rows_after = [dict(row) for row in connection.execute(text(
                    "SELECT * FROM spot_replay_runs ORDER BY created_at, replay_id")).mappings()]
                version_after = connection.execute(text(
                    "SELECT version_num FROM alembic_version")).scalar_one()
                registry_exists = connection.execute(text(
                    "SELECT to_regclass('public.spot_replay_configurations') IS NOT NULL")).scalar_one()
                registry_rows = []
                if registry_exists:
                    registry_rows = [dict(row) for row in connection.execute(text(
                        "SELECT * FROM spot_replay_configurations ORDER BY owner_id, run_configuration_id"
                    )).mappings()]
        finally:
            engine.dispose()

        def json_safe(value: Any) -> Any:
            if isinstance(value, dict):
                return {str(key): json_safe(item) for key, item in value.items()}
            if isinstance(value, list):
                return [json_safe(item) for item in value]
            if isinstance(value, (datetime, uuid.UUID)):
                return value.isoformat() if isinstance(value, datetime) else str(value)
            return value

        proof = {
            "post_status": saved_response.status_code,
            "get_status": exact_read.status_code,
            "exact_get_match": exact_read.json() == saved,
            "api_authored_revision_text": saved["content"]["strategy_revision_id"],
            "parent_revision_text": str(revision["revision_id"]),
            "source_rows_before": json_safe(rows_before),
            "source_rows_after": json_safe(rows_after),
            "upgrade_exit": upgrade.returncode,
            "upgrade_stdout": upgrade.stdout,
            "upgrade_stderr": upgrade.stderr,
            "version_after": version_after,
            "registry_exists_after": registry_exists,
            "registry_rows_after": json_safe(registry_rows),
        }
        evidence_dir = os.environ.get("P13_R8_EVIDENCE_DIR")
        if evidence_dir:
            output = Path(evidence_dir)
            output.mkdir(parents=True, exist_ok=True)
            evidence_kind = os.environ.get("P13_R8_EVIDENCE_KIND", "red")
            (output / f"{evidence_kind}-uppercase-revision.json").write_text(
                json.dumps(proof, sort_keys=True, indent=2) + "\n", encoding="utf-8")

        assert upgrade.returncode == 0, "migration refused valid API-authored uppercase revision UUID history"
        assert rows_after == rows_before
        assert version_after == "0005"
        assert registry_exists and len(registry_rows) == 1
        expected_hash = record_contract.sha256_hex({
            "schema_version": "p13.spot-replay-run/1", "inputs": saved["content"]["inputs"]})
        assert registry_rows[0]["configuration_sha256"] == expected_hash
    finally:
        pg.psql(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")


def _assert_legacy_revision_boundary_refused(client, owner_a, pg, malformation: str) -> None:
    strategy, revision = _saved_revision(client, owner_a)
    body = _body(strategy, revision, key=f"legacy-r9-{malformation}-{uuid.uuid4()}")
    saved_response = client.post("/v1/spot-replays", headers=owner_a, json=body)
    assert saved_response.status_code == 201, saved_response.text
    saved = saved_response.json()
    database_name, environment = _migration_target(pg, f"r9_{malformation.replace('-', '_')}")
    engine = None
    try:
        assert _upgrade_to(environment, "0004").returncode == 0
        _copy_legacy_replay_rows(pg.url, environment["EDGE_OS_DATABASE_URL"],
                                 saved["content"]["owner_id"], revision["revision_id"],
                                 [saved["replay_id"]])
        engine = create_engine(environment["EDGE_OS_DATABASE_URL"])
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE spot_replay_runs DISABLE TRIGGER spot_replay_runs_immutable"))
            replay = dict(connection.execute(text(
                "SELECT * FROM spot_replay_runs WHERE replay_id = :replay_id"),
                {"replay_id": uuid.UUID(saved["replay_id"])}).mappings().one())
            content = copy.deepcopy(replay["content"])
            if malformation == "unsupported-profile":
                content["inputs"]["profile_version"] = "p12.spot-replay/999"
            elif malformation == "unsupported-fixture":
                content["inputs"]["dataset_fixture_id"] = "unsupported-fixture/999"
                content["dataset_fixture_id"] = "unsupported-fixture/999"
            elif malformation == "unsupported-input-fixture-copy":
                content["inputs"]["dataset_fixture_id"] = "unsupported-fixture/999"
            elif malformation == "unsupported-content-fixture-copy":
                content["dataset_fixture_id"] = "unsupported-fixture/999"
            elif malformation == "revision-strategy-mismatch":
                content["inputs"]["strategy"]["cost_assumptions"]["fee_rate"] = "0"
                content["inputs"]["strategy_sha256"] = record_contract.sha256_hex(content["inputs"]["strategy"])
            elif malformation not in {
                    "revision-content-hash", "revision-manifest-hash", "revision-duplicate-key"}:
                raise AssertionError(f"unknown R9 migration fixture: {malformation}")
            if malformation in {
                    "unsupported-profile", "unsupported-fixture", "unsupported-input-fixture-copy",
                    "unsupported-content-fixture-copy", "revision-strategy-mismatch"}:
                connection.execute(text(
                    "UPDATE spot_replay_runs SET content = CAST(:content AS jsonb), content_sha256 = :hash "
                    "WHERE replay_id = :replay_id"), {
                        "content": json.dumps(content),
                        "hash": record_contract.sha256_hex(content),
                        "replay_id": uuid.UUID(saved["replay_id"]),
                    })
            connection.execute(text("ALTER TABLE spot_replay_runs ENABLE TRIGGER spot_replay_runs_immutable"))
            if malformation in {"revision-content-hash", "revision-manifest-hash", "revision-duplicate-key"}:
                column = "content_sha256" if malformation == "revision-content-hash" else "manifest_sha256"
                connection.execute(text("ALTER TABLE strategy_revisions DISABLE TRIGGER strategy_revisions_immutable"))
                if malformation == "revision-duplicate-key":
                    strategy_canonical = connection.execute(text(
                        "SELECT strategy_canonical FROM strategy_revisions WHERE revision_id = :revision_id"), {
                            "revision_id": uuid.UUID(revision["revision_id"]),
                        }).scalar_one()
                    duplicate_key = strategy_canonical[:-1] + ",\"strategy_id\":" + json.dumps(strategy["strategy_id"]) + "}"
                    connection.execute(text(
                        "UPDATE strategy_revisions SET strategy_canonical = :strategy "
                        "WHERE revision_id = :revision_id"), {
                            "strategy": duplicate_key,
                            "revision_id": uuid.UUID(revision["revision_id"]),
                        })
                else:
                    column = "content_sha256" if malformation == "revision-content-hash" else "manifest_sha256"
                    connection.execute(text(
                        f"UPDATE strategy_revisions SET {column} = :hash WHERE revision_id = :revision_id"), {
                            "hash": "0" * 64,
                            "revision_id": uuid.UUID(revision["revision_id"]),
                        })
                connection.execute(text("ALTER TABLE strategy_revisions ENABLE TRIGGER strategy_revisions_immutable"))

        def capture() -> dict[str, Any]:
            with engine.connect() as connection:
                replay_rows = [row[0] for row in connection.execute(text(
                    "SELECT to_jsonb(r) FROM spot_replay_runs AS r ORDER BY created_at, replay_id"))]
                revision_rows = [row[0] for row in connection.execute(text(
                    "SELECT to_jsonb(r) FROM strategy_revisions AS r ORDER BY revision_id"))]
                version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                registry_exists = connection.execute(text(
                    "SELECT to_regclass('public.spot_replay_configurations') IS NOT NULL")).scalar_one()
                registry_rows = []
                if registry_exists:
                    registry_rows = [row[0] for row in connection.execute(text(
                        "SELECT to_jsonb(r) FROM spot_replay_configurations AS r "
                        "ORDER BY owner_id, run_configuration_id"))]
                return {"version": version, "registry_exists": registry_exists,
                        "registry_rows": registry_rows, "replay_rows": replay_rows,
                        "revision_rows": revision_rows}

        before = capture()
        upgraded = _upgrade_to(environment, "head")
        after = capture()
        proof = {
            "case": malformation,
            "api_authored_source": saved,
            "revision_returned_by_api": revision,
            "before": before,
            "upgrade": {"returncode": upgraded.returncode, "stdout": upgraded.stdout,
                        "stderr": upgraded.stderr},
            "after": after,
        }
        evidence_dir = os.environ.get("P13_R9_EVIDENCE_DIR")
        if evidence_dir:
            output = Path(evidence_dir)
            output.mkdir(parents=True, exist_ok=True)
            kind = os.environ.get("P13_R9_EVIDENCE_KIND", "red")
            (output / f"{kind}-{malformation}.json").write_text(
                json.dumps(proof, sort_keys=True, indent=2) + "\n", encoding="utf-8")

        assert upgraded.returncode != 0, f"migration admitted {malformation} legacy history"
        obstruction = {
            "unsupported-profile": "unsupported P12 profile version",
            "unsupported-fixture": "unsupported dataset fixture",
            "unsupported-input-fixture-copy": "a saved replay identity is malformed",
            "unsupported-content-fixture-copy": "a saved replay identity is malformed",
            "revision-strategy-mismatch": "differs from its immutable revision",
            "revision-content-hash": "failed integrity validation",
            "revision-manifest-hash": "failed integrity validation",
            "revision-duplicate-key": "not canonical JSON",
        }[malformation]
        assert obstruction in upgraded.stderr
        assert before["replay_rows"] == after["replay_rows"]
        assert before["revision_rows"] == after["revision_rows"]
        assert after["version"] == "0004"
        assert not after["registry_exists"] and not after["registry_rows"]
    finally:
        if engine is not None:
            engine.dispose()
        pg.psql(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")


def test_migration_refuses_unsupported_legacy_profile_version(client, owner_a, pg):
    _assert_legacy_revision_boundary_refused(client, owner_a, pg, "unsupported-profile")


def test_migration_refuses_self_consistent_unsupported_legacy_fixture(client, owner_a, pg):
    _assert_legacy_revision_boundary_refused(client, owner_a, pg, "unsupported-fixture")


@pytest.mark.parametrize("malformation", ["unsupported-input-fixture-copy", "unsupported-content-fixture-copy"])
def test_migration_refuses_mismatched_saved_fixture_copies(client, owner_a, pg, malformation):
    _assert_legacy_revision_boundary_refused(client, owner_a, pg, malformation)


def test_migration_refuses_hash_consistent_strategy_different_from_saved_revision(client, owner_a, pg):
    _assert_legacy_revision_boundary_refused(client, owner_a, pg, "revision-strategy-mismatch")


@pytest.mark.parametrize("malformation", [
    "revision-content-hash", "revision-manifest-hash", "revision-duplicate-key",
])
def test_migration_refuses_corrupt_referenced_revision_integrity(client, owner_a, pg, malformation):
    _assert_legacy_revision_boundary_refused(client, owner_a, pg, malformation)


def test_migration_preserves_supported_profile_and_revision_spellings_for_complete_and_unavailable_rows(
        client, owner_a, pg):
    strategy, revision = _saved_revision(client, owner_a)
    base_revision_id = revision["revision_id"]
    spellings = {
        "lower": base_revision_id.lower(),
        "upper": base_revision_id.upper(),
        "mixed": "".join(char.upper() if index % 2 else char.lower()
                          for index, char in enumerate(base_revision_id)),
    }
    cases = {}
    for spelling_name, spelling in spellings.items():
        for evidence_name, evidence in (
                ("complete", None),
                ("unbound", {"state": "UNBOUND"}),
                ("bound-null", {"state": "BOUND", "essential_dependencies": None})):
            body = _body(strategy, revision, key=f"legacy-r9-valid-{uuid.uuid4()}")
            body["strategy_revision_id"] = spelling
            if evidence is not None:
                body["essential_fields"]["entry"] = evidence
            saved_response = client.post("/v1/spot-replays", headers=owner_a, json=body)
            assert saved_response.status_code == 201, saved_response.text
            saved = saved_response.json()
            exact_read = client.get(f"/v1/spot-replays/{saved['replay_id']}", headers=owner_a)
            assert exact_read.status_code == 200 and exact_read.json() == saved
            expected_status = "COMPLETE" if evidence_name == "complete" else "UNAVAILABLE"
            assert saved["content"]["result"]["status"] == expected_status
            assert saved["content"]["strategy_revision_id"] == spelling
            cases[f"{spelling_name}-{evidence_name}"] = {"request": body, "saved": saved}

    database_name, environment = _migration_target(pg, "r9_valid_profile_revision_spellings")
    engine = None
    try:
        assert _upgrade_to(environment, "0004").returncode == 0
        _copy_legacy_replay_rows(pg.url, environment["EDGE_OS_DATABASE_URL"],
                                 cases["lower-complete"]["saved"]["content"]["owner_id"],
                                 base_revision_id,
                                 [case["saved"]["replay_id"] for case in cases.values()])
        engine = create_engine(environment["EDGE_OS_DATABASE_URL"])
        with engine.connect() as connection:
            rows_before = [dict(row) for row in connection.execute(text(
                "SELECT * FROM spot_replay_runs ORDER BY created_at, replay_id")).mappings()]
            revisions_before = [dict(row) for row in connection.execute(text(
                "SELECT * FROM strategy_revisions ORDER BY revision_id")).mappings()]
        upgraded = _upgrade_to(environment, "head")
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
        with engine.connect() as connection:
            rows_after = [dict(row) for row in connection.execute(text(
                "SELECT * FROM spot_replay_runs ORDER BY created_at, replay_id")).mappings()]
            revisions_after = [dict(row) for row in connection.execute(text(
                "SELECT * FROM strategy_revisions ORDER BY revision_id")).mappings()]
            version_after = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            registry = [dict(row) for row in connection.execute(text(
                "SELECT * FROM spot_replay_configurations ORDER BY owner_id, run_configuration_id"
            )).mappings()]
        expected_bindings = {
            case["saved"]["content"]["run_configuration_id"]: record_contract.sha256_hex({
                "schema_version": "p13.spot-replay-run/1", "inputs": case["saved"]["content"]["inputs"]})
            for case in cases.values()
        }
        assert rows_after == rows_before
        assert revisions_after == revisions_before
        assert version_after == "0005"
        assert len(rows_after) == len(cases) == len(registry) == 9
        assert {row["run_configuration_id"]: row["configuration_sha256"] for row in registry} == expected_bindings

        def json_safe(value: Any) -> Any:
            if isinstance(value, dict):
                return {str(key): json_safe(item) for key, item in value.items()}
            if isinstance(value, list):
                return [json_safe(item) for item in value]
            if isinstance(value, (datetime, uuid.UUID)):
                return value.isoformat() if isinstance(value, datetime) else str(value)
            return value

        evidence_dir = os.environ.get("P13_R9_EVIDENCE_DIR")
        if evidence_dir:
            output = Path(evidence_dir)
            output.mkdir(parents=True, exist_ok=True)
            kind = os.environ.get("P13_R9_EVIDENCE_KIND", "green")
            proof = {
                "cases": cases,
                "upgrade_returncode": upgraded.returncode,
                "upgrade_stdout": upgraded.stdout,
                "upgrade_stderr": upgraded.stderr,
                "source_replays_before": json_safe(rows_before),
                "source_replays_after": json_safe(rows_after),
                "source_revisions_before": json_safe(revisions_before),
                "source_revisions_after": json_safe(revisions_after),
                "registry_after": json_safe(registry),
                "version_after": version_after,
            }
            (output / f"{kind}-valid-profile-revision-spellings.json").write_text(
                json.dumps(proof, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    finally:
        if engine is not None:
            engine.dispose()
        pg.psql(f"DROP DATABASE IF EXISTS {database_name} WITH (FORCE)")
