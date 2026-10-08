from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import tempfile
import unittest
from pathlib import Path

from docs.qualification.p04.native_runner import (
    AttemptState,
    DockerPolicy,
    FixtureStore,
    QualificationLedger,
)


class DurableFixtureTests(unittest.TestCase):
    def test_owner_agent_memory_and_source_refs_survive_restart_without_cross_scope_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "qualification.sqlite3"
            first = FixtureStore(database)
            first.create_agent("owner-a", "agent-a")
            first.create_agent("owner-b", "agent-b")
            first.add_source("owner-a", "agent-a", "src-a", "fixture://a", "A-source")
            first.add_source("owner-b", "agent-b", "src-b", "fixture://b", "B-source")
            first.set_memory("owner-a", "agent-a", ["short reports"], ["src-a"])
            first.set_memory("owner-b", "agent-b", ["long reports"], ["src-b"])

            restarted = FixtureStore(database)
            task_a = restarted.task_context("owner-a", "agent-a")
            task_b = restarted.task_context("owner-b", "agent-b")
            self.assertEqual(task_a["memory"]["entries"], ["short reports"])
            self.assertEqual(task_a["sources"][0]["source_id"], "src-a")
            self.assertEqual(task_b["memory"]["entries"], ["long reports"])
            self.assertEqual(task_b["sources"][0]["source_id"], "src-b")
            with self.assertRaises(PermissionError):
                restarted.task_context("owner-b", "agent-a")
            with self.assertRaises(PermissionError):
                restarted.add_source("owner-b", "agent-a", "src-x", "fixture://x", "X")

    def test_stream_chunks_are_job_owner_and_agent_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "qualification.sqlite3"
            store = FixtureStore(database)
            store.create_agent("owner-a", "agent-a")
            store.create_agent("owner-b", "agent-b")
            store.append_stream_chunk("owner-a", "agent-a", "job-a", 0, "A:partial")
            store.append_stream_chunk("owner-b", "agent-b", "job-b", 0, "B:partial")
            restarted = FixtureStore(database)
            self.assertEqual(restarted.read_stream("owner-a", "agent-a", "job-a"), ["A:partial"])
            self.assertEqual(restarted.read_stream("owner-b", "agent-b", "job-b"), ["B:partial"])
            with self.assertRaises(PermissionError):
                restarted.read_stream("owner-b", "agent-b", "job-a")
            with self.assertRaises(PermissionError):
                restarted.read_stream("owner-b", "agent-a", "job-a")

    def test_cleared_memory_is_a_new_empty_tombstone_version(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FixtureStore(Path(directory) / "qualification.sqlite3")
            store.create_agent("owner-a", "agent-a")
            self.assertEqual(store.set_memory("owner-a", "agent-a", ["old"], []), 1)
            self.assertEqual(store.clear_memory("owner-a", "agent-a"), 2)
            task = store.task_context("owner-a", "agent-a")
            self.assertEqual(task["memory"], {"version": 2, "enabled": False, "entries": []})

    def test_memory_and_source_reference_bounds_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FixtureStore(Path(directory) / "qualification.sqlite3")
            store.create_agent("owner-a", "agent-a")
            store.add_source("owner-a", "agent-a", "src-a", "fixture://a", "source")
            with self.assertRaises(ValueError):
                store.set_memory("owner-a", "agent-a", ["x" * 2049], [])
            with self.assertRaises(ValueError):
                store.set_memory("owner-a", "agent-a", ["ok"], ["src-a"] * 9)
            with self.assertRaises(PermissionError):
                store.set_memory("owner-a", "agent-a", ["ok"], ["other-owner-source"])


class RecoveryTests(unittest.TestCase):
    def test_restart_marks_running_attempt_interrupted_and_unknown_without_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "qualification.sqlite3"
            first = QualificationLedger(database, total_budget_usd="2.00")
            job_id, created = first.reserve_and_start(
                owner_id="owner-a", agent_id="agent-a", request_key="request-a",
                prompt_sha256="sha256:prompt-a", reserve_usd="2.00",
            )
            self.assertTrue(created)
            self.assertEqual(first.state(job_id), AttemptState.RUNNING)

            after_restart = QualificationLedger(database, total_budget_usd="2.00")
            self.assertEqual(after_restart.recover_running(), [(job_id, AttemptState.INTERRUPTED)])
            self.assertEqual(after_restart.state(job_id), AttemptState.INTERRUPTED)
            self.assertEqual(after_restart.usage_state(job_id), "UNKNOWN")
            same_job, created_again = after_restart.reserve_and_start(
                owner_id="owner-a", agent_id="agent-a", request_key="request-a",
                prompt_sha256="sha256:prompt-a", reserve_usd="2.00",
            )
            self.assertEqual(same_job, job_id)
            self.assertFalse(created_again)
            self.assertEqual(after_restart.dispatch_count(job_id), 1)
            self.assertEqual(after_restart.reserved_usd, "2.00")

    def test_idempotency_key_conflict_and_budget_overflow_are_denied_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = QualificationLedger(Path(directory) / "qualification.sqlite3", total_budget_usd="2.00")
            ledger.reserve_and_start(
                owner_id="owner-a", agent_id="agent-a", request_key="request-a",
                prompt_sha256="sha256:prompt-a", reserve_usd="1.25",
            )
            with self.assertRaises(ValueError):
                ledger.reserve_and_start(
                    owner_id="owner-a", agent_id="agent-a", request_key="request-a",
                    prompt_sha256="sha256:prompt-b", reserve_usd="0.25",
                )
            with self.assertRaises(ValueError):
                ledger.reserve_and_start(
                    owner_id="owner-b", agent_id="agent-b", request_key="request-b",
                    prompt_sha256="sha256:prompt-b", reserve_usd="0.76",
                )
            self.assertEqual(ledger.dispatch_count_by_owner("owner-b"), 0)

    def test_concurrent_reservations_cannot_exceed_the_task_ceiling(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = QualificationLedger(Path(directory) / "qualification.sqlite3", total_budget_usd="2.00")
            start = Barrier(2)

            def reserve(owner: str):
                start.wait(timeout=3)
                return ledger.reserve_and_start(
                    owner_id=owner, agent_id=f"agent-{owner}", request_key="request",
                    prompt_sha256=f"sha256:{owner}", reserve_usd="1.25",
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(reserve, "owner-a"), pool.submit(reserve, "owner-b")]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except ValueError:
                    outcomes.append("rejected")
            self.assertEqual(sum(isinstance(item, tuple) for item in outcomes), 1)
            self.assertEqual(outcomes.count("rejected"), 1)
            self.assertEqual(ledger.reserved_usd, "1.25")


class SandboxPolicyTests(unittest.TestCase):
    def test_container_policy_is_labeled_bounded_read_only_and_egress_denied(self):
        policy = DockerPolicy(run_id="p04-test-run-unique")
        argv = policy.run_argv(
            image="p04-hermes:test", name="p04-test-run-unique-job-a",
            input_path="/tmp/input.json", output_path="/tmp/out-a",
        )
        self.assertIn("--network=none", argv)
        self.assertIn("--read-only", argv)
        self.assertIn("--memory=512m", argv)
        self.assertIn("--cpus=1", argv)
        self.assertIn("--pids-limit=64", argv)
        self.assertIn("--cap-drop=ALL", argv)
        self.assertIn("--user", argv)
        self.assertIn("--security-opt=no-new-privileges", argv)
        self.assertIn("edge-os.test.run=p04-test-run-unique", argv)
        self.assertIn("type=bind,src=/tmp/input.json,dst=/qualification/input.json,readonly", argv)
        self.assertIn("type=bind,src=/tmp/out-a,dst=/qualification/output", argv)
        self.assertIn("HOME=/tmp/p04-test-run-unique-job-a/home", argv)
        self.assertIn("XDG_CACHE_HOME=/tmp/p04-test-run-unique-job-a/cache", argv)
        self.assertNotIn("/Users", " ".join(argv))


if __name__ == "__main__":
    unittest.main()
