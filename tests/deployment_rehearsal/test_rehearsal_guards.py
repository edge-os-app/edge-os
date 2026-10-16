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


RUN = local_stack.RUN_LABEL
TEST = "edge-os.test.run"
RELAY = "edge-os.hermes-relay"


def item(name: str = "") -> dict:
    """An unlabelled resource."""
    return {"name": name, "owners": {}}


def inv(**kinds: dict) -> dict:
    return {kind: kinds.get(kind, {}) for kind in ("containers", "volumes", "networks", "images")}


def test_owner_labels_are_read_only_from_the_recognized_run_labels_with_a_value() -> None:
    assert local_stack.owner_labels({RUN: "l4ab12", "com.docker.compose.project": "x"}) == {RUN: "l4ab12"}
    assert local_stack.owner_labels({TEST: "p03abcd", RELAY: ""}) == {TEST: "p03abcd"}
    assert local_stack.owner_labels({RELAY: "relayrun1"}) == {RELAY: "relayrun1"}
    assert local_stack.owner_labels({"edge-os.other.run": "x", "edge-os.test": "1"}) == {}
    assert local_stack.owner_labels(None) == {}


def test_resource_difference_ignores_other_runs_but_reports_any_change_to_unlabelled_resources() -> None:
    before = inv(containers={"c1": item(), "c2": {"name": "", "owners": {TEST: "other"}}}, volumes={"v1": item()},
                 images={"i1": item()})
    after = inv(containers={"c1": item(), "c3": {"name": "", "owners": {TEST: "other2"}},
                            "c4": {"name": "", "owners": {RUN: "l4ab12"}}}, volumes={"v1": item()}, images={"i1": item()})
    assert local_stack.foreign_changes(before, after, run_id="l4ab12") == []
    assert local_stack.leftovers(after, run_id="l4ab12") == ["containers:c4"]
    gone = {**after, "volumes": {}}
    assert local_stack.foreign_changes(before, gone, run_id="l4ab12") == ["volumes:v1 disappeared"]
    extra = {**after, "images": {"i1": item(), "i9": item()}}
    assert local_stack.foreign_changes(before, extra, run_id="l4ab12") == ["images:i9 appeared"]


def test_an_independent_relay_run_is_accounted_to_that_run_not_hidden_or_failed() -> None:
    """The controller's counterexample: lane 1's relay network (edge-os.hermes-relay=<run>) is removed during our run."""
    relay = {"name": "lane1-relay", "owners": {RELAY: "relayrun1"}}
    before, after = inv(networks={"independent-relay-network": relay}), inv()
    assert local_stack.foreign_changes(before, after, run_id="l4ab12") == []
    assert local_stack.other_run_changes(before, after, run_id="l4ab12") == [
        "networks:independent-relay-network disappeared (lane1-relay) [edge-os.hermes-relay=relayrun1]"]
    created = inv(containers={"r1": {"name": "relay", "owners": {RELAY: "relayrun2"}}})
    assert local_stack.foreign_changes(inv(), created, run_id="l4ab12") == []
    assert local_stack.other_run_changes(inv(), created, run_id="l4ab12") == [
        "containers:r1 appeared (relay) [edge-os.hermes-relay=relayrun2]"]
    assert local_stack.leftovers(created, run_id="l4ab12") == []


def test_unrecognized_labels_stay_unlabelled_and_are_detected() -> None:
    stray = inv(networks={"n9": {"name": "stray", "owners": local_stack.owner_labels({"edge-os.other.run": "x"})}})
    assert local_stack.foreign_changes(inv(), stray, run_id="l4ab12") == ["networks:n9 appeared (stray)"]


def test_conflicting_run_labels_are_never_hidden() -> None:
    both = inv(containers={"c7": {"name": "mixed", "owners": {RUN: "l4ab12", RELAY: "relayrun1"}}})
    assert local_stack.foreign_changes(inv(), both, run_id="l4ab12") == [
        "containers:c7 appeared (mixed) [conflicting run labels: edge-os.hermes-relay=relayrun1, "
        "edge-os.rehearsal.run=l4ab12]"]
    assert local_stack.leftovers(both, run_id="l4ab12") == ["containers:c7"]
    others = inv(volumes={"v7": {"name": "", "owners": {TEST: "p03x", RELAY: "relayrun1"}}})
    assert local_stack.foreign_changes(others, inv(), run_id="l4ab12") == [
        "volumes:v7 disappeared [conflicting run labels: edge-os.hermes-relay=relayrun1, edge-os.test.run=p03x]"]
    assert local_stack.other_run_changes(others, inv(), run_id="l4ab12") == []


def test_another_rehearsal_run_is_other_but_this_run_id_is_own() -> None:
    mine_and_theirs = inv(networks={"n1": {"name": "", "owners": {RUN: "l4ab12"}},
                                    "n2": {"name": "", "owners": {RUN: "l4zz99"}}})
    assert local_stack.leftovers(mine_and_theirs, run_id="l4ab12") == ["networks:n1"]
    assert local_stack.foreign_changes(inv(), mine_and_theirs, run_id="l4ab12") == []
    assert local_stack.other_run_changes(inv(), mine_and_theirs, run_id="l4ab12") == [
        "networks:n2 appeared [edge-os.rehearsal.run=l4zz99]"]
