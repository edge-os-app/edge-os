"""The harness must never remove a resource that this process did not create (P01 isolated-instance rules)."""

from __future__ import annotations

import subprocess

import pytest

import harness


def alive(pg: harness.Postgres) -> bool:
    return pg.psql("select 1") == "1"


def volume_exists(name: str) -> bool:
    return harness.sh(["docker", "volume", "inspect", name], check=False).returncode == 0


def container_exists(name: str) -> bool:
    return harness.sh(["docker", "container", "inspect", name], check=False).returncode == 0


def test_a_second_start_with_the_same_run_id_refuses_and_preserves_the_first():
    run_id = harness.new_run_id()
    first = harness.Postgres(run_id).start()
    try:
        second = harness.Postgres(run_id)
        with pytest.raises(RuntimeError, match="already exists"):
            second.start()
        second.stop_and_remove()  # it created nothing, so it must remove nothing
        assert second.leftovers() == []
        assert alive(first) and volume_exists(first.volume)
    finally:
        first.stop_and_remove()
    assert first.leftovers() == [] and not container_exists(first.container) and not volume_exists(first.volume)


def test_a_foreign_container_with_the_same_name_is_never_removed():
    run_id = harness.new_run_id()
    name = harness.Postgres(run_id).container
    harness.sh(["docker", "run", "-d", "--name", name, "--entrypoint", "sleep", harness.POSTGRES_IMAGE, "600"])
    try:
        pg = harness.Postgres(run_id)
        with pytest.raises(RuntimeError, match="already exists"):
            pg.start()
        pg.stop_and_remove()
        with pytest.raises(RuntimeError):
            harness.remove_orphan(run_id)  # no edge-os labels and still running
        assert container_exists(name) and harness.sh(["docker", "inspect", "-f", "{{.State.Running}}", name]).stdout.strip() == "true"
    finally:
        harness.sh(["docker", "rm", "-f", "-v", name], check=False)


def test_orphan_removal_refuses_a_running_labelled_instance():
    pg = harness.Postgres(harness.new_run_id()).start()
    try:
        with pytest.raises(RuntimeError, match="running"):
            harness.remove_orphan(pg.run_id)
        assert alive(pg)
    finally:
        pg.stop_and_remove()


def test_the_verification_cli_refuses_an_existing_run_id_and_changes_nothing(tmp_path):
    pg = harness.Postgres(harness.new_run_id()).start()
    try:
        evidence_root = tmp_path / "evidence"
        result = subprocess.run([harness.api_python(), str(harness.REPO / "scripts" / "p03" / "verify_run.py"),
                                 "--run-id", pg.run_id, "--evidence-root", str(evidence_root)],
                                capture_output=True, text=True, timeout=120, env=harness.base_env())
        assert result.returncode == 2, result.stdout + result.stderr
        assert "already exists" in (result.stdout + result.stderr)
        assert alive(pg) and volume_exists(pg.volume)
        assert not evidence_root.exists()  # nothing was written for the refused run
    finally:
        pg.stop_and_remove()


def test_the_verification_cli_refuses_existing_evidence_and_build_output(tmp_path):
    run_id = harness.new_run_id()
    evidence_root = tmp_path / "evidence"
    (evidence_root / run_id).mkdir(parents=True)
    (evidence_root / run_id / "keep.txt").write_text("earlier run")
    result = subprocess.run([harness.api_python(), str(harness.REPO / "scripts" / "p03" / "verify_run.py"),
                             "--run-id", run_id, "--evidence-root", str(evidence_root)],
                            capture_output=True, text=True, timeout=120, env=harness.base_env())
    assert result.returncode == 2 and "already exists" in (result.stdout + result.stderr)
    assert (evidence_root / run_id / "keep.txt").read_text() == "earlier run"
    assert harness.Postgres(run_id).leftovers() == []


def test_the_cli_refuses_an_existing_web_build_folder_and_tsconfig_copy():
    for kind in ("build", "tsconfig"):
        run_id = harness.new_run_id()
        target = harness.WEB_DIR / (f".next-{run_id}" if kind == "build" else harness.web_tsconfig(f".next-{run_id}"))
        target.mkdir() if kind == "build" else target.write_text("{}")
        try:
            result = subprocess.run([harness.api_python(), str(harness.REPO / "scripts" / "p03" / "verify_run.py"),
                                     "--run-id", run_id, "--evidence-root", str(harness.REPO / ".scratch" / "p03" / "evidence" / "pytest-refusal")],
                                    capture_output=True, text=True, timeout=120, env=harness.base_env())
            assert result.returncode == 2 and "already exists" in result.stdout
            assert target.exists(), "the refused run must not delete what it did not create"
        finally:
            (target.rmdir() if kind == "build" else target.unlink())


def test_a_foreign_volume_without_a_container_is_never_removed():
    run_id = harness.new_run_id()
    name = harness.Postgres(run_id).volume
    harness.sh(["docker", "volume", "create", name])  # no edge-os labels: someone else's
    try:
        pg = harness.Postgres(run_id)
        with pytest.raises(RuntimeError, match="already exists"):
            pg.start()
        pg.stop_and_remove()
        assert volume_exists(name) and pg.leftovers() == []
    finally:
        harness.sh(["docker", "volume", "rm", name], check=False)


def test_a_start_that_fails_after_the_volume_exists_removes_only_what_it_created(monkeypatch):
    monkeypatch.setattr(harness, "POSTGRES_IMAGE", "postgres:0.0-this-tag-does-not-exist")
    pg = harness.Postgres(harness.new_run_id())
    with pytest.raises(Exception):
        pg.start()
    assert pg.created_volume and not pg.created_container
    pg.stop_and_remove()
    assert pg.leftovers() == [] and not volume_exists(pg.volume) and not container_exists(pg.container)


def test_resource_comparison_ignores_other_runs_and_flags_unlabelled_changes():
    import verify_run
    mine = harness.Postgres(harness.new_run_id())
    other = harness.Postgres(harness.new_run_id()).start()  # a parallel run belonging to someone else
    stray = f"edge-os-unlabelled-{harness.new_run_id()}"
    try:
        before = verify_run.docker_resources(mine.run_id)
        assert other.container not in before["containers"] and other.volume not in before["volumes"]
        harness.sh(["docker", "volume", "create", stray])
        assert stray in verify_run.docker_resources(mine.run_id)["volumes"]  # unrelated unlabelled change is visible
    finally:
        harness.sh(["docker", "volume", "rm", stray], check=False)
        other.stop_and_remove()
