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
