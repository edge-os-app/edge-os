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


def test_a_start_that_fails_after_the_container_exists_is_cleaned_up_by_its_own_object(monkeypatch):
    def never_ready(self, timeout=90.0):
        raise RuntimeError("postgres did not become ready")
    monkeypatch.setattr(harness.Postgres, "_wait_ready", never_ready)
    pg = harness.Postgres(harness.new_run_id())
    with pytest.raises(RuntimeError, match="did not become ready"):
        pg.start()
    assert pg.created_container and pg.created_volume
    pg.stop_and_remove()
    assert pg.leftovers() == [] and not container_exists(pg.container) and not volume_exists(pg.volume)


def test_a_failed_web_build_still_ends_with_the_final_json_line_and_cleans_up(monkeypatch, tmp_path, capsys):
    """The skill waits for HOLD or the final line. A failed build must end in the final line, not in silence."""
    import json
    import subprocess as sp
    import sys

    import verify_run

    monkeypatch.setattr(harness, "build_web", lambda **_k: sp.CompletedProcess([], 1, "", "boom"))
    run_id = harness.new_run_id()
    monkeypatch.setattr(sys, "argv", ["verify_run.py", "--run-id", run_id, "--evidence-root", str(tmp_path), "--skip-ui"])
    code = verify_run.main()
    out = capsys.readouterr().out
    final = json.loads(out.strip().splitlines()[-1])
    assert code == 1 and final["ok"] is False and final["run_id"] == run_id
    assert harness.Postgres(run_id).existing_resources() == []


def test_the_skill_wait_loop_ends_on_a_refused_or_failed_run():
    import re
    import subprocess as sp
    skill = (harness.REPO / ".agents" / "skills" / "verify-edge-os" / "SKILL.md").read_text()
    pattern = re.search(r"grep -qE '([^']+)'", skill)
    assert pattern, "the skill must wait for HOLD, REFUSED or the final line"
    for log in ('HOLD {"web": "http://127.0.0.1:1"}', "REFUSED run x: container y already exists.", '{"run_id": "x", "evidence": "e", "ok": false}'):
        assert sp.run(["grep", "-qE", pattern.group(1)], input=log, text=True).returncode == 0, log
    assert sp.run(["grep", "-qE", pattern.group(1)], input="PASS postgres started", text=True).returncode != 0


def test_a_losing_concurrent_start_never_removes_the_winning_live_instance(monkeypatch):
    """Both callers pass the absence check before either creates anything (the gate's interleaving).

    The first finishes starting. The second then reaches Docker and loses the name. Its cleanup must leave the
    winner's container and volume alone.
    """
    run_id = harness.new_run_id()
    winner = harness.Postgres(run_id)
    loser = harness.Postgres(run_id)
    absent = lambda self: []  # noqa: E731 - both absence checks answered "nothing exists" before any creation
    monkeypatch.setattr(harness.Postgres, "existing_resources", absent)
    try:
        winner.start()
        with pytest.raises(RuntimeError):
            loser.start()
        assert not loser.created_container and not loser.created_volume, "a lost claim must not become ownership"
        loser.stop_and_remove()
        assert loser.leftovers() == []
        assert alive(winner) and volume_exists(winner.volume), "the winner must survive the loser's cleanup"
    finally:
        monkeypatch.undo()
        winner.stop_and_remove()
    assert winner.leftovers() == [] and not container_exists(winner.container) and not volume_exists(winner.volume)


def test_real_concurrent_starts_leave_exactly_one_owner_and_preserve_it(monkeypatch):
    import concurrent.futures
    import threading
    run_id = harness.new_run_id()
    instances = [harness.Postgres(run_id), harness.Postgres(run_id)]
    gate = threading.Barrier(2)
    real = harness.Postgres.existing_resources

    def synchronized(self):
        found = real(self)
        gate.wait(timeout=30)  # both absence checks finish before either caller creates anything
        return found
    monkeypatch.setattr(harness.Postgres, "existing_resources", synchronized)

    def attempt(instance):
        try:
            instance.start()
            return True
        except Exception:  # noqa: BLE001
            return False
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, instances))
        monkeypatch.undo()
        assert outcomes.count(True) == 1, outcomes
        winner = instances[outcomes.index(True)]
        loser = instances[outcomes.index(False)]
        assert not loser.created_container
        loser.stop_and_remove()
        assert alive(winner) and volume_exists(winner.volume)
    finally:
        monkeypatch.undo()
        for instance in instances:
            instance.stop_and_remove()
    assert all(i.leftovers() == [] for i in instances) and not container_exists(instances[0].container)


def test_explicit_orphan_removal_never_force_removes_a_container_that_started_again():
    pg = harness.Postgres(harness.new_run_id()).start()
    try:
        with pytest.raises(RuntimeError, match="running"):
            harness.remove_orphan(pg.run_id)
        assert alive(pg)
    finally:
        pg.stop_and_remove()


@pytest.mark.parametrize("kind", ["build", "tsconfig"])
def test_a_run_that_loses_the_race_for_the_build_paths_removes_nothing_it_did_not_create(monkeypatch, tmp_path, capsys, kind):
    """Another caller with the same run ID created its build folder after this call's preflight.

    The preflight is stubbed to answer "nothing exists", as it would for two callers that check at the same moment.
    The claim must still fail, and the other caller's files must survive this call's cleanup.
    """
    import sys

    import verify_run

    run_id = harness.new_run_id()
    dist = harness.WEB_DIR / f".next-{run_id}"
    tsconfig = harness.WEB_DIR / harness.web_tsconfig(f".next-{run_id}")
    foreign = dist if kind == "build" else tsconfig
    foreign.mkdir() if kind == "build" else foreign.write_text("{}")
    monkeypatch.setattr(verify_run, "preflight_present", lambda *_a, **_k: [])
    monkeypatch.setattr(sys, "argv", ["verify_run.py", "--run-id", run_id, "--evidence-root", str(tmp_path)])
    try:
        code = verify_run.main()
        out = capsys.readouterr().out
        assert code == 2 and "REFUSED" in out and "already exists" in out
        assert foreign.exists(), "the losing run deleted the other caller's path"
        assert harness.Postgres(run_id).existing_resources() == [], "the losing run must not start a database"
    finally:
        (foreign.rmdir() if kind == "build" else foreign.unlink(missing_ok=True))
        other = dist if kind == "tsconfig" else tsconfig
        if other.exists():
            (other.rmdir() if other.is_dir() else other.unlink())


def test_orphan_removal_refuses_a_container_that_is_created_but_not_yet_started():
    run_id = harness.new_run_id()
    pg = harness.Postgres(run_id)
    cid = harness.sh(["docker", "create", "--name", pg.container, *pg.labels(), harness.POSTGRES_IMAGE]).stdout.strip()
    try:
        with pytest.raises(RuntimeError, match="created"):
            harness.remove_orphan(run_id)
        assert container_exists(cid)
    finally:
        harness.sh(["docker", "rm", "-f", "-v", cid], check=False)
