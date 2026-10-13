"""Rehearsal driver guards: run naming, restore targets, identity comparison, resource ownership and scoped env."""

from __future__ import annotations

import pytest

import identity_snapshot
import local_stack
import restore_drill


@pytest.mark.parametrize("run_id", ["l4ab12", "abcd", "a" * 20])
def test_accepts_plain_lowercase_run_ids(run_id: str) -> None:
    assert local_stack.check_run_id(run_id) == run_id


@pytest.mark.parametrize("run_id", ["", "abc", "A1234", "ab-cd", "ab_cd", "a" * 21, "l4 x", "../x"])
def test_refuses_run_ids_that_could_reach_other_resources(run_id: str) -> None:
    with pytest.raises(ValueError):
        local_stack.check_run_id(run_id)


def test_primary_and_restore_projects_have_distinct_owned_names() -> None:
    primary, restored = local_stack.StackNames.primary("l4ab12"), local_stack.StackNames.restored("l4ab12")
    assert primary.project == "edge-os-local-l4ab12" and restored.project == "edge-os-local-l4ab12r"
    assert primary.database == "edge_os_local_l4ab12" and restored.database == "edge_os_restore_l4ab12"
    assert primary.images == restored.images == ("edge-os-local-api:l4ab12", "edge-os-local-web:l4ab12")


def test_compose_environment_is_built_from_scratch_and_holds_only_named_values(monkeypatch) -> None:
    monkeypatch.setenv("EDGE_OS_PRIVY_APP_SECRET", "ambient")
    monkeypatch.setenv("EDGE_OS_DATABASE_URL", "postgresql+psycopg://ambient")
    monkeypatch.setenv("POSTGRES_PASSWORD", "ambient")
    env = local_stack.compose_environment(local_stack.StackNames.primary("l4ab12"), port=18000, db_password="pw",
                                          verification_key="KEY\\nX", build_sha="f" * 40)
    assert {key for key in env if key.startswith(("EDGE_OS", "POSTGRES"))} == {
        "EDGE_OS_LOCAL_RUN_ID", "EDGE_OS_LOCAL_PUBLIC_PORT", "EDGE_OS_LOCAL_DB_NAME", "EDGE_OS_LOCAL_DB_PASSWORD",
        "EDGE_OS_LOCAL_VERIFICATION_KEY", "EDGE_OS_LOCAL_BUILD_SHA"}
    assert "ambient" not in env.values()
    assert env["EDGE_OS_LOCAL_DB_NAME"] == "edge_os_local_l4ab12" and env["EDGE_OS_LOCAL_PUBLIC_PORT"] == "18000"


def test_restore_target_must_be_fresh_unique_and_not_the_source() -> None:
    restore_drill.check_restore_target("edge_os_restore_l4ab12", source="edge_os_local_l4ab12", existing_tables=[])
    with pytest.raises(restore_drill.RestoreRefused, match="source"):
        restore_drill.check_restore_target("edge_os_local_l4ab12", source="edge_os_local_l4ab12", existing_tables=[])
    with pytest.raises(restore_drill.RestoreRefused, match="not empty"):
        restore_drill.check_restore_target("edge_os_restore_l4ab12", source="edge_os_local_l4ab12",
                                           existing_tables=["public.alembic_version"])
    with pytest.raises(restore_drill.RestoreRefused, match="name"):
        restore_drill.check_restore_target("postgres", source="edge_os_local_l4ab12", existing_tables=[])


def test_identity_comparison_reports_every_changed_missing_and_added_value() -> None:
    before = {"schema_head": "0015", "tables": {"a.t": {"rows": 2, "md5": "x"}, "a.u": {"rows": 1, "md5": "y"}},
              "named": {"jobs": [["j1", "REPORTED"]]}}
    assert identity_snapshot.differences(before, before) == []
    after = {"schema_head": "0015", "tables": {"a.t": {"rows": 3, "md5": "z"}, "a.v": {"rows": 0, "md5": None}},
             "named": {"jobs": [["j1", "UNAVAILABLE"]]}}
    assert identity_snapshot.differences(before, after) == [
        "named.jobs: [['j1', 'REPORTED']] -> [['j1', 'UNAVAILABLE']]",
        "tables.a.t.md5: 'x' -> 'z'",
        "tables.a.t.rows: 2 -> 3",
        "tables.a.u: missing after",
        "tables.a.v: added after",
    ]


def test_resource_difference_ignores_other_runs_but_reports_any_change_to_unlabelled_resources() -> None:
    before = {"containers": {"c1": {"run": ""}, "c2": {"run": "other"}}, "volumes": {"v1": {"run": ""}},
              "networks": {}, "images": {"i1": {"run": ""}}}
    after = {"containers": {"c1": {"run": ""}, "c3": {"run": "other2"}, "c4": {"run": "l4ab12"}},
             "volumes": {"v1": {"run": ""}}, "networks": {}, "images": {"i1": {"run": ""}}}
    assert local_stack.foreign_changes(before, after, run_id="l4ab12") == []
    assert local_stack.leftovers(after, run_id="l4ab12") == ["containers:c4"]
    gone = {**after, "volumes": {}}
    assert local_stack.foreign_changes(before, gone, run_id="l4ab12") == ["volumes:v1 disappeared"]
    extra = {**after, "images": {"i1": {"run": ""}, "i9": {"run": ""}}}
    assert local_stack.foreign_changes(before, extra, run_id="l4ab12") == ["images:i9 appeared"]
