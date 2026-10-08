from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess
from threading import Barrier
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from docs.qualification.p04 import container_probe

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

    def test_same_owner_agents_retrieve_only_their_own_files(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "qualification.sqlite3"
            store = FixtureStore(database)
            store.create_agent("owner-a", "agent-a")
            store.create_agent("owner-a", "agent-b")
            try:
                store.add_file("owner-a", "agent-a", "file-a", "A-only file evidence")
                store.add_file("owner-a", "agent-b", "file-b", "B-only file evidence")
            except AttributeError:
                self.fail("fixture file snapshots are not available to task contexts")

            restarted = FixtureStore(database)
            task_a = restarted.task_context("owner-a", "agent-a")
            task_b = restarted.task_context("owner-a", "agent-b")
            self.assertEqual(task_a["files"], [{"file_id": "file-a", "content": "A-only file evidence"}])
            self.assertEqual(task_b["files"], [{"file_id": "file-b", "content": "B-only file evidence"}])
            with self.assertRaises(PermissionError):
                restarted.add_file("owner-b", "agent-a", "file-x", "cross-owner file")

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


class CancellationLifecycleRegressionTests(unittest.TestCase):
    @staticmethod
    def _owned_inspection(run_id, name, *, running=True):
        return json.dumps({
            "Id": "fixture-container-id", "Name": f"/{name}",
            "Config": {"Labels": {"edge-os.test.run": run_id}},
            "State": {"Running": running},
        })

    def test_docker_no_such_object_error_is_verified_absence_case_insensitively(self):
        from docs.qualification.p04 import native_runner

        missing = subprocess.CalledProcessError(
            1, ["docker", "inspect"], stderr="error: no such object: task-name",
        )
        with patch.object(native_runner, "_docker", side_effect=missing):
            result = native_runner._inspect_owned_container("task-name", "p04-run")

        self.assertEqual(result["status"], "absent")
        self.assertEqual(result["ownership"], "verified_by_exact_name")

    def test_absent_container_still_reaps_running_docker_client(self):
        from docs.qualification.p04 import native_runner

        class FakeProcess:
            returncode = 0
            communicate_calls = 0

            def communicate(self, timeout=None):
                self.communicate_calls += 1
                return "docker client output", None

        process = FakeProcess()
        missing = subprocess.CalledProcessError(
            1, ["docker", "inspect"], stderr="error: no such object: task-name",
        )
        with patch.object(native_runner, "_docker", side_effect=missing):
            result = native_runner._cleanup_owned_container("task-name", "p04-run", process)

        self.assertEqual(result["container_cleanup_status"], "verified_absent")
        self.assertEqual(result["process_cleanup_status"], "reaped")
        self.assertEqual(process.communicate_calls, 1)

    def test_inspection_failure_reaps_runner_and_recovers_reserved_attempt_as_unknown(self):
        from docs.qualification.p04 import native_runner

        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            output = evidence / "task-cancel" / "output"

            class FakeProcess:
                returncode = None
                killed = False

                def poll(self):
                    return self.returncode

                def kill(self):
                    self.killed = True
                    self.returncode = -9

                def communicate(self, timeout=None):
                    if self.returncode is None:
                        raise subprocess.TimeoutExpired(["docker", "run"], timeout)
                    return "", None

            process = FakeProcess()

            def start_process(*_args, **_kwargs):
                output.joinpath("provider-started.marker").write_text("started\n", encoding="utf-8")
                return process

            with (
                patch.object(native_runner.subprocess, "Popen", side_effect=start_process),
                patch.object(
                    native_runner, "_docker",
                    side_effect=subprocess.CalledProcessError(1, ["docker", "inspect"], stderr="daemon unavailable"),
                ),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    native_runner._run_cancellation(
                        policy=DockerPolicy("p04-test-inspection"), image="p04-test:image",
                        context={"memory": {"version": 1, "enabled": True, "entries": []}, "sources": [], "files": []},
                        evidence=evidence, run_id="p04-test-inspection",
                    )

            ledger = QualificationLedger(output.parent / "restart.sqlite3", total_budget_usd="2.00")
            connection = ledger._connect()
            try:
                job_id = connection.execute(
                    "SELECT job_id FROM attempts WHERE request_key='request-cancel'"
                ).fetchone()["job_id"]
            finally:
                connection.close()
            self.assertTrue(process.killed, "the Docker runner process was not reaped after inspection failed")
            self.assertEqual(ledger.state(job_id), AttemptState.INTERRUPTED)
            self.assertEqual(ledger.usage_state(job_id), "UNKNOWN")
            self.assertEqual(ledger.dispatch_count(job_id), 1)
            self.assertEqual(ledger.reserved_usd, "2.00")
            lifecycle = json.loads((output.parent / "cancellation-lifecycle.json").read_text(encoding="utf-8"))
            self.assertEqual(lifecycle["container_cleanup_status"], "unknown_pending_verification")
            self.assertEqual(lifecycle["original_error_class"], "CalledProcessError")

    def test_wrong_owner_label_and_malformed_inspection_never_kill_a_container(self):
        from docs.qualification.p04 import native_runner

        cases = (
            ("wrong-name", json.dumps({
                "Name": "/different-container", "Config": {"Labels": {"edge-os.test.run": "p04-test-owner"}},
                "State": {"Running": True},
            })),
            ("wrong-label", json.dumps({
                "Name": "/p04-test-owner-cancel", "Config": {"Labels": {"edge-os.test.run": "other-run"}},
                "State": {"Running": True},
            })),
            ("malformed-json", "not-json"),
        )
        for run_id, inspect_result in cases:
            with self.subTest(run_id=run_id), tempfile.TemporaryDirectory() as directory:
                evidence = Path(directory)
                output = evidence / "task-cancel" / "output"

                class FakeProcess:
                    returncode = None

                    def poll(self):
                        return self.returncode

                    def kill(self):
                        self.returncode = -9

                    def communicate(self, timeout=None):
                        if self.returncode is None:
                            raise subprocess.TimeoutExpired(["docker", "run"], timeout)
                        return "", None

                process = FakeProcess()

                def start_process(*_args, **_kwargs):
                    output.joinpath("provider-started.marker").write_text("started\n", encoding="utf-8")
                    return process

                policy = DockerPolicy(run_id)
                name = f"p04-{run_id}-cancel"
                with (
                    patch.object(native_runner.subprocess, "Popen", side_effect=start_process),
                    patch.object(native_runner, "_docker", return_value=inspect_result),
                    patch.object(native_runner.subprocess, "run") as docker_run,
                ):
                    with self.assertRaises((AssertionError, ValueError)):
                        native_runner._run_cancellation(
                            policy=policy, image="p04-test:image",
                            context={"memory": {"version": 1, "enabled": True, "entries": []}, "sources": [], "files": []},
                            evidence=evidence, run_id=run_id,
                        )

                docker_run.assert_not_called()
                lifecycle = json.loads((output.parent / "cancellation-lifecycle.json").read_text(encoding="utf-8"))
                self.assertEqual(lifecycle["container_cleanup_status"], "unknown_pending_verification")
                self.assertTrue(lifecycle["attempt_recovered_interrupted_unknown"])

    def test_marker_timeout_kills_verified_container_and_recovers_attempt(self):
        from docs.qualification.p04 import native_runner

        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            output = evidence / "task-cancel" / "output"
            run_id = "p04-marker-timeout"
            name = f"p04-{run_id}-cancel"

            class FakeProcess:
                returncode = None

                def poll(self):
                    return self.returncode

                def kill(self):
                    self.returncode = -9

                def communicate(self, timeout=None):
                    if self.returncode is None:
                        raise subprocess.TimeoutExpired(["docker", "run"], timeout)
                    return "fixture killed\n", None

            process = FakeProcess()
            inspect = self._owned_inspection(run_id, name)
            absent = subprocess.CalledProcessError(1, ["docker", "inspect"], stderr="No such object")
            ticks = iter((0, 31, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49))

            def set_process_exit(*_args, **_kwargs):
                process.returncode = 137
                return subprocess.CompletedProcess(["docker", "kill"], 0, stdout="", stderr="")

            with (
                patch.object(
                    native_runner.subprocess, "Popen", return_value=process,
                ),
                patch.object(native_runner, "_docker", side_effect=(inspect, inspect, absent)),
                patch.object(native_runner.subprocess, "run", side_effect=set_process_exit),
                patch.object(native_runner.time, "monotonic", side_effect=lambda: next(ticks)),
                patch.object(native_runner.time, "sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, "marker did not appear"):
                    native_runner._run_cancellation(
                        policy=DockerPolicy(run_id), image="p04-test:image",
                        context={"memory": {"version": 1, "enabled": True, "entries": []}, "sources": [], "files": []},
                        evidence=evidence, run_id=run_id,
                    )

            lifecycle = json.loads((output.parent / "cancellation-lifecycle.json").read_text(encoding="utf-8"))
            self.assertEqual(lifecycle["container_cleanup_status"], "verified_absent")
            self.assertEqual(lifecycle["process_cleanup_status"], "reaped")
            self.assertEqual(lifecycle["original_error_class"], "RuntimeError")
            self.assertTrue(lifecycle["attempt_recovered_interrupted_unknown"])

    def test_kill_and_process_wait_failures_remain_unknown_and_recover_without_replay(self):
        from docs.qualification.p04 import native_runner

        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            output = evidence / "task-cancel" / "output"
            run_id = "p04-kill-failure"
            name = f"p04-{run_id}-cancel"

            class FakeProcess:
                returncode = None

                def poll(self):
                    return self.returncode

                def kill(self):
                    raise OSError("fixture process kill failed")

                def communicate(self, timeout=None):
                    raise subprocess.TimeoutExpired(["docker", "run"], timeout)

            process = FakeProcess()
            inspect = self._owned_inspection(run_id, name)
            ticks = [0]

            def advance_clock():
                ticks[0] += 6
                return ticks[0]

            with (
                patch.object(
                    native_runner.subprocess, "Popen",
                    side_effect=lambda *_args, **_kwargs: (
                        output.joinpath("provider-started.marker").write_text("started\n", encoding="utf-8"),
                        process,
                    )[1],
                ),
                patch.object(native_runner, "_docker", return_value=inspect),
                patch.object(native_runner.subprocess, "run", side_effect=subprocess.TimeoutExpired(["docker", "kill"], 10)),
                patch.object(native_runner.time, "monotonic", side_effect=advance_clock),
                patch.object(native_runner.time, "sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, "cleanup is unresolved"):
                    native_runner._run_cancellation(
                        policy=DockerPolicy(run_id), image="p04-test:image",
                        context={"memory": {"version": 1, "enabled": True, "entries": []}, "sources": [], "files": []},
                        evidence=evidence, run_id=run_id,
                    )

            lifecycle = json.loads((output.parent / "cancellation-lifecycle.json").read_text(encoding="utf-8"))
            self.assertEqual(lifecycle["container_cleanup_status"], "unknown_pending_verification")
            self.assertEqual(lifecycle["kill_error_class"], "TimeoutExpired")
            self.assertEqual(lifecycle["process_cleanup_status"], "unknown_pending_reap")
            self.assertTrue(lifecycle["attempt_recovered_interrupted_unknown"])
            ledger = QualificationLedger(output.parent / "restart.sqlite3", total_budget_usd="2.00")
            self.assertEqual(ledger.reserved_usd, "2.00")
            self.assertEqual(ledger.dispatch_count_by_owner("owner-a"), 1)


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


class NormalProcessLifecycleRegressionTests(unittest.TestCase):
    def test_normal_job_timeout_does_not_kill_unverified_container_and_reaps_docker_client(self):
        from docs.qualification.p04 import native_runner

        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)

            class FakeProcess:
                returncode = None
                killed = False

                def communicate(self, timeout=None):
                    if self.returncode is None:
                        raise subprocess.TimeoutExpired(["docker", "run"], timeout)
                    return "fixture reaped\n", None

                def kill(self):
                    self.killed = True
                    self.returncode = -9

            process = FakeProcess()
            inspection_error = subprocess.CalledProcessError(
                1, ["docker", "inspect"], stderr="daemon unavailable",
            )
            with (
                patch.object(native_runner.subprocess, "Popen", return_value=process),
                patch.object(native_runner, "_docker", side_effect=inspection_error),
                patch.object(native_runner.subprocess, "run") as docker_run,
            ):
                with self.assertRaisesRegex(TimeoutError, "unknown_pending_verification"):
                    native_runner._run_normal(
                        policy=DockerPolicy("p04-normal-timeout"), image="p04-test:image",
                        owner_id="owner-a", agent_id="agent-a",
                        context={"memory": {"version": 1, "enabled": True, "entries": []}, "sources": [], "files": []},
                        evidence=evidence, run_id="p04-normal-timeout", ordinal="1",
                    )

            self.assertTrue(process.killed)
            docker_run.assert_not_called()
            lifecycle = json.loads(
                (evidence / "task-1" / "container-lifecycle.json").read_text(encoding="utf-8")
            )
            self.assertEqual(lifecycle["container_cleanup_status"], "unknown_pending_verification")
            self.assertEqual(lifecycle["process_cleanup_status"], "reaped_after_local_kill")


class ProviderBoundaryRegressionTests(unittest.TestCase):
    def _run_normal_consumer(self, context, *, mutate_sent=None, observed_receipts=None):
        import sys

        from docs.qualification.p04 import native_runner

        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = lambda status_code, *, json, request: SimpleNamespace(
            status_code=status_code, json=lambda: json, request=request,
        )
        result_fixture = (
            native_runner.WORKSPACE / "docs/qualification/p04/evidence/p04-dad145eebf8f/"
            "task-1-owner-a/output/container-result.json"
        )

        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)

            def start_fake_container(argv, **kwargs):
                task_dir = evidence / "task-1"
                task = json.loads((task_dir / "input.json").read_text(encoding="utf-8"))
                sent = json.loads(json.dumps({
                    key: task[key]
                    for key in ("owner_id", "agent_id", "job_id", "memory", "sources", "files")
                }))
                if mutate_sent is not None:
                    mutate_sent(sent)
                request = SimpleNamespace(
                    content=json.dumps({
                        "model": "fixture-model",
                        "messages": [{"role": "user", "content": json.dumps(sent)}],
                        "max_tokens": 128,
                    }).encode(),
                    url="https://fake-provider.invalid/v1/chat/completions",
                    headers={"authorization": "Bearer fixture-not-a-secret"},
                )
                with patch.object(container_probe, "OUTPUT", task_dir / "output"), patch.dict(
                    "sys.modules", {"httpx": fake_httpx}
                ):
                    receipt, _ = container_probe._record_request(request, "normal", task)
                if observed_receipts is not None:
                    observed_receipts.append(receipt)

                result = json.loads(result_fixture.read_text(encoding="utf-8"))
                result.update(job_id=task["job_id"], owner_id=task["owner_id"], agent_id=task["agent_id"])
                (task_dir / "output" / "container-result.json").write_text(
                    json.dumps(result), encoding="utf-8",
                )
                return SimpleNamespace(returncode=0, communicate=lambda **_: ("fixture output\n", None))

            qualification_path = str(native_runner.WORKSPACE / "docs/qualification/p04")
            with patch.object(native_runner.subprocess, "Popen", side_effect=start_fake_container), patch.object(
                sys, "path", [qualification_path, *sys.path]
            ):
                return native_runner._run_normal(
                    policy=DockerPolicy("p04-consumer-test"), image="p04-test:image",
                    owner_id="owner-a", agent_id="agent-a", context=context,
                    evidence=evidence, run_id="p04-consumer-test", ordinal="1",
                )

    def test_normal_result_consumer_rejects_identity_and_snapshot_mismatches(self):
        empty_context = {
            "memory": {"version": 2, "enabled": False, "entries": []},
            "sources": [], "files": [],
        }
        mutations = {
            "owner": lambda payload: payload.update(owner_id="owner-z"),
            "agent": lambda payload: payload.update(agent_id="agent-z"),
            "cleared_memory": lambda payload: payload["memory"].update(enabled=True),
            "empty_sources": lambda payload: payload.update(sources=[{"source_id": "unexpected-source"}]),
            "empty_files": lambda payload: payload.update(files=[{"file_id": "unexpected-file", "content": "foreign"}]),
        }
        for name, mutation in mutations.items():
            with self.subTest(mismatch=name), self.assertRaises(AssertionError):
                self._run_normal_consumer(empty_context, mutate_sent=mutation)

    def test_normal_result_consumer_accepts_exact_populated_and_empty_snapshots(self):
        contexts = (
            {
                "memory": {"version": 1, "enabled": True, "entries": ["authorized memory"]},
                "sources": [{"source_id": "source-a", "content": "authorized source"}],
                "files": [{"file_id": "file-a", "content": "authorized file"}],
            },
            {
                "memory": {"version": 2, "enabled": False, "entries": []},
                "sources": [], "files": [],
            },
        )
        for context in contexts:
            with self.subTest(context=context):
                result = self._run_normal_consumer(context)
                self.assertEqual(result["provider_receipt"]["owner_fixture_present"], True)
                self.assertEqual(result["provider_receipt"]["agent_fixture_present"], True)
                for snapshot in ("memory", "source", "file"):
                    self.assertTrue(result["provider_receipt"][f"{snapshot}_snapshot_matches"])

    def test_normal_consumer_rejects_json_type_and_required_snapshot_presence_mismatches(self):
        empty_context = {
            "memory": {"version": 2, "enabled": False, "entries": []},
            "sources": [], "files": [],
        }
        populated_context = {
            "memory": {"version": 1, "enabled": True, "entries": ["authorized memory"]},
            "sources": [{"source_id": "source-a", "content": "authorized source"}],
            "files": [{"file_id": "file-a", "content": "authorized file"}],
        }
        cases = (
            (
                "cleared_memory_false_to_zero",
                empty_context,
                lambda sent: sent["memory"].update(enabled=0),
                ("memory_snapshot_matches",),
            ),
            (
                "populated_memory_true_to_one",
                populated_context,
                lambda sent: sent["memory"].update(enabled=1),
                ("memory_snapshot_matches",),
            ),
            (
                "memory_version_integer_to_boolean",
                populated_context,
                lambda sent: sent["memory"].update(version=True),
                ("memory_version_present", "memory_snapshot_matches"),
            ),
            (
                "missing_empty_memory_field",
                empty_context,
                lambda sent: sent.pop("memory"),
                ("memory_snapshot_matches",),
            ),
            (
                "missing_empty_sources_field",
                empty_context,
                lambda sent: sent.pop("sources"),
                ("source_snapshot_matches",),
            ),
            (
                "missing_empty_files_field",
                empty_context,
                lambda sent: sent.pop("files"),
                ("file_snapshot_matches",),
            ),
        )
        for name, context, mutation, false_receipt_fields in cases:
            with self.subTest(mismatch=name):
                observed_receipts = []
                with self.assertRaises(AssertionError):
                    self._run_normal_consumer(
                        context, mutate_sent=mutation, observed_receipts=observed_receipts,
                    )
                self.assertEqual(len(observed_receipts), 1)
                for field in false_receipt_fields:
                    self.assertFalse(observed_receipts[0][field], field)
                if name.startswith("missing_empty_"):
                    snapshot = name.removeprefix("missing_empty_").removesuffix("_field")
                    empty_field = {
                        "memory": "memory_snapshot_empty",
                        "sources": "source_snapshot_empty",
                        "files": "file_snapshot_empty",
                    }[snapshot]
                    self.assertFalse(observed_receipts[0][empty_field])

    def test_disjoint_identity_controls_exclude_shared_owner_but_keep_other_agent(self):
        from docs.qualification.p04.native_runner import _forbidden_identity_values

        self.assertEqual(
            _forbidden_identity_values("owner-a", "agent-a", "owner-a", "agent-b"),
            {"owner_id": "", "agent_id": "agent-b"},
        )
        self.assertEqual(
            _forbidden_identity_values("owner-a", "agent-a", "owner-b", "agent-d"),
            {"owner_id": "owner-b", "agent_id": "agent-d"},
        )

    def test_cleared_memory_and_empty_sources_are_recorded_at_the_provider_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            task = {
                "owner_id": "owner-a", "agent_id": "agent-b", "job_id": "job-cleared",
                "memory": {"version": 2, "enabled": False, "entries": []}, "sources": [],
            }
            request = SimpleNamespace(
                content=json.dumps({"model": "fixture-model", "messages": [], "max_tokens": 128}).encode(),
                url="https://fake-provider.invalid/v1/chat/completions",
                headers={"authorization": "Bearer fixture-not-a-secret"},
            )
            with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict("sys.modules", {"httpx": ModuleType("httpx")}):
                try:
                    receipt, _ = container_probe._record_request(request, "normal", task)
                except Exception as exc:
                    self.fail(f"valid empty memory snapshot was rejected: {type(exc).__name__}")

            self.assertFalse(receipt["only_expected_memory_present"])
            self.assertFalse(receipt["only_expected_source_present"])
            self.assertEqual(len((Path(directory) / "fake-provider-requests.jsonl").read_text().splitlines()), 1)

    def test_truncation_fixture_returns_length_termination_instead_of_a_valid_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            task = {
                "owner_id": "owner-a", "agent_id": "agent-a", "job_id": "job-truncated",
                "memory": {"version": 1, "enabled": True, "entries": ["fixture memory"]},
                "sources": [{"source_id": "source-a"}],
            }
            request = SimpleNamespace(
                content=json.dumps({"model": "fixture-model", "messages": [], "max_tokens": 128}).encode(),
                url="https://fake-provider.invalid/v1/chat/completions",
                headers={"authorization": "Bearer fixture-not-a-secret"},
            )
            with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict("sys.modules", {"httpx": ModuleType("httpx")}):
                _, response = container_probe._record_request(request, "truncated", task)

            self.assertEqual(response["choices"][0]["finish_reason"], "length")
            self.assertNotIn('"outcome"', response["choices"][0]["message"]["content"])

    def test_forbidden_source_and_file_ids_use_exact_context_not_substrings(self):
        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = lambda status_code, *, json, request: SimpleNamespace(
            status_code=status_code, json=lambda: json, request=request,
        )
        task = {
            "owner_id": "owner-a", "agent_id": "agent-b", "job_id": "job-prefixes",
            "memory": {"version": 1, "enabled": True, "entries": ["memory-b"]},
            "sources": [{"source_id": "source-a-b"}],
            "files": [{"file_id": "file-a-b", "content": "file B"}],
            "probe_forbidden": {"memory": "memory-a", "source_id": "source-a", "file_id": "file-a"},
        }
        payload = {key: task[key] for key in ("owner_id", "agent_id", "job_id", "memory", "sources", "files")}
        request = SimpleNamespace(
            content=json.dumps({"model": "fixture-model", "messages": [{"role": "user", "content": json.dumps(payload)}], "max_tokens": 128}).encode(),
            url="https://fake-provider.invalid/v1/chat/completions",
            headers={"authorization": "Bearer fixture-not-a-secret"},
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict("sys.modules", {"httpx": fake_httpx}):
                receipt, _ = container_probe._record_request(request, "normal", task)

        self.assertTrue(receipt["forbidden_source_absent"])
        self.assertTrue(receipt["forbidden_file_absent"])

    def test_forbidden_context_in_additional_outgoing_json_message_is_recorded_as_present(self):
        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = lambda status_code, *, json, request: SimpleNamespace(
            status_code=status_code, json=lambda: json, request=request,
        )
        task = {
            "owner_id": "owner-a", "agent_id": "agent-a", "job_id": "job-extra-context",
            "memory": {"version": 1, "enabled": True, "entries": ["memory-a"]},
            "sources": [{"source_id": "source-a"}],
            "files": [{"file_id": "file-a", "content": "private file A"}],
            "probe_forbidden": {
                "owner_id": "owner-b", "agent_id": "agent-b", "memory": "memory-b",
                "source_id": "source-b", "file_id": "file-b",
            },
        }
        authorized = {key: task[key] for key in ("owner_id", "agent_id", "job_id", "memory", "sources", "files")}
        request = SimpleNamespace(
            content=json.dumps({"model": "fixture-model", "messages": [
                {"role": "user", "content": json.dumps(authorized)},
                {"role": "system", "content": json.dumps({
                    "owner_id": "owner-b", "agent_id": "agent-b", "memory": ["memory-b"],
                    "sources": [{"source_id": "source-b"}],
                    "files": [{"file_id": "file-b", "content": "private file B"}],
                })},
            ], "max_tokens": 128}).encode(),
            url="https://fake-provider.invalid/v1/chat/completions",
            headers={"authorization": "Bearer fixture-not-a-secret"},
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict("sys.modules", {"httpx": fake_httpx}):
                receipt, _ = container_probe._record_request(request, "normal", task)

        self.assertFalse(receipt["forbidden_owner_absent"])
        self.assertFalse(receipt["forbidden_agent_absent"])
        self.assertFalse(receipt["forbidden_memory_absent"])
        self.assertFalse(receipt["forbidden_source_absent"])
        self.assertFalse(receipt["forbidden_file_absent"])
        sent_messages = json.loads(request.content)["messages"]
        self.assertEqual(
            receipt["outgoing_messages_sha256"],
            hashlib.sha256(json.dumps(sent_messages, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        )

    def test_forbidden_memory_is_detected_after_decoding_json_string_escapes(self):
        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = lambda status_code, *, json, request: SimpleNamespace(
            status_code=status_code, json=lambda: json, request=request,
        )
        task = {
            "owner_id": "owner-a", "agent_id": "agent-a", "job_id": "job-json-memory",
            "memory": {"version": 1, "enabled": True, "entries": ["authorized memory"]},
            "sources": [], "files": [],
            "probe_forbidden": {"memory": "other memory"},
        }
        authorized = {key: task[key] for key in ("owner_id", "agent_id", "job_id", "memory", "sources", "files")}
        extra_json_values = (
            '{"memory":{"entries":["other memory"]}}',
            r'{"memory":{"entries":["\u006fther memory"]}}',
        )

        for index, extra_content in enumerate(extra_json_values):
            request = SimpleNamespace(
                content=json.dumps({"model": "fixture-model", "messages": [
                    {"role": "user", "content": json.dumps(authorized)},
                    {"role": "system", "content": extra_content},
                ], "max_tokens": 128}).encode(),
                url="https://fake-provider.invalid/v1/chat/completions",
                headers={"authorization": "Bearer fixture-not-a-secret"},
            )
            with self.subTest(extra_content=extra_content), tempfile.TemporaryDirectory() as directory:
                with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict("sys.modules", {"httpx": fake_httpx}):
                    receipt, _ = container_probe._record_request(request, "normal", task)

                self.assertFalse(receipt["forbidden_memory_absent"], f"JSON memory case {index} was missed")

    def test_forbidden_identifiers_are_detected_in_decoded_json_at_each_message_placement(self):
        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = lambda status_code, *, json, request: SimpleNamespace(
            status_code=status_code, json=lambda: json, request=request,
        )
        task = {
            "owner_id": "owner-a", "agent_id": "agent-a", "job_id": "job-json-identifiers",
            "memory": {"version": 1, "enabled": True, "entries": ["authorized memory"]},
            "sources": [{"source_id": "source-a", "content": "authorized source"}],
            "files": [{"file_id": "file-a", "content": "authorized file"}],
            "probe_forbidden": {
                "owner_id": "owner-b", "agent_id": "agent-b",
                "memory": "other memory", "source_id": "other-source", "file_id": "other-file",
            },
        }
        authorized = {key: task[key] for key in ("owner_id", "agent_id", "job_id", "memory", "sources", "files")}
        encoded_identifiers = r'{"notes":["\u006fwner-b","\u0061gent-b","\u006fther-source","\u006fther-file"]}'
        placements = {
            "system_content": {"role": "system", "content": encoded_identifiers},
            "multipart_text": {"role": "system", "content": [{"type": "text", "text": encoded_identifiers}]},
            "tool_arguments": {
                "role": "assistant", "content": None,
                "tool_calls": [{"type": "function", "function": {
                    "name": "fixture_tool", "arguments": encoded_identifiers,
                }}],
            },
        }

        for placement, extra_message in placements.items():
            request = SimpleNamespace(
                content=json.dumps({"model": "fixture-model", "messages": [
                    {"role": "user", "content": json.dumps(authorized)}, extra_message,
                ], "max_tokens": 128}).encode(),
                url="https://fake-provider.invalid/v1/chat/completions",
                headers={"authorization": "Bearer fixture-not-a-secret"},
            )
            with self.subTest(placement=placement), tempfile.TemporaryDirectory() as directory:
                with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict(
                    "sys.modules", {"httpx": fake_httpx}
                ):
                    receipt, _ = container_probe._record_request(request, "normal", task)

                for identity in ("owner", "agent", "source", "file"):
                    self.assertFalse(
                        receipt[f"forbidden_{identity}_absent"],
                        f"decoded {identity} was missed in {placement}",
                    )

    def test_decoded_identifier_suffixes_do_not_match_forbidden_ids(self):
        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = lambda status_code, *, json, request: SimpleNamespace(
            status_code=status_code, json=lambda: json, request=request,
        )
        task = {
            "owner_id": "owner-a", "agent_id": "agent-a", "job_id": "job-identifier-prefixes",
            "memory": {"version": 1, "enabled": True, "entries": ["authorized memory"]},
            "sources": [{"source_id": "source-a-b", "content": "authorized source"}],
            "files": [{"file_id": "file-a-b", "content": "authorized file"}],
            "probe_forbidden": {
                "owner_id": "owner-b", "agent_id": "agent-b",
                "memory": "other memory", "source_id": "source-a", "file_id": "file-a",
            },
        }
        authorized = {key: task[key] for key in ("owner_id", "agent_id", "job_id", "memory", "sources", "files")}
        suffixes = r'{"notes":["owner-b-suffix","agent-b-suffix","source-a-suffix","file-a-suffix"]}'
        request = SimpleNamespace(
            content=json.dumps({"model": "fixture-model", "messages": [
                {"role": "user", "content": json.dumps(authorized)},
                {"role": "system", "content": suffixes},
            ], "max_tokens": 128}).encode(),
            url="https://fake-provider.invalid/v1/chat/completions",
            headers={"authorization": "Bearer fixture-not-a-secret"},
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict(
                "sys.modules", {"httpx": fake_httpx}
            ):
                receipt, _ = container_probe._record_request(request, "normal", task)

        for identity in ("owner", "agent", "source", "file"):
            self.assertTrue(receipt[f"forbidden_{identity}_absent"])

    def test_forbidden_context_in_structured_text_parts_is_detected_without_id_prefix_false_positive(self):
        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = lambda status_code, *, json, request: SimpleNamespace(
            status_code=status_code, json=lambda: json, request=request,
        )
        task = {
            "owner_id": "owner-a", "agent_id": "agent-a", "job_id": "job-structured-context",
            "memory": {"version": 1, "enabled": True, "entries": ["memory-a"]},
            "sources": [{"source_id": "source-a-b"}],
            "files": [{"file_id": "file-a-b", "content": "private file AB"}],
            "probe_forbidden": {
                "owner_id": "owner-b", "agent_id": "agent-b", "memory": "memory-b",
                "source_id": "source-a", "file_id": "file-a",
            },
        }
        authorized = {key: task[key] for key in ("owner_id", "agent_id", "job_id", "memory", "sources", "files")}
        request = SimpleNamespace(
            content=json.dumps({"model": "fixture-model", "messages": [
                {"role": "user", "content": json.dumps(authorized)},
                {"role": "system", "content": [
                    {"type": "text", "text": "Other agent memory-b and file-a."},
                    {"type": "text", "text": "The authorized source is source-a-b."},
                ]},
                {"role": "assistant", "content": None, "tool_calls": [{
                    "type": "function", "function": {
                        "name": "fixture_tool", "arguments": json.dumps({
                            "owner_id": "owner-b", "agent_id": "agent-b",
                        }),
                    },
                }]},
            ], "max_tokens": 128}).encode(),
            url="https://fake-provider.invalid/v1/chat/completions",
            headers={"authorization": "Bearer fixture-not-a-secret"},
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict("sys.modules", {"httpx": fake_httpx}):
                receipt, _ = container_probe._record_request(request, "normal", task)

        self.assertTrue(receipt["forbidden_source_absent"])
        self.assertFalse(receipt["forbidden_owner_absent"])
        self.assertFalse(receipt["forbidden_agent_absent"])
        self.assertFalse(receipt["forbidden_memory_absent"])
        self.assertFalse(receipt["forbidden_file_absent"])

    def test_same_sized_second_request_is_rejected_before_fake_provider_work(self):
        class FakeResponse:
            def __init__(self, status_code, *, json, request):
                self.status_code = status_code
                self._json = json
                self.request = request

            def json(self):
                return self._json

        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = FakeResponse
        request = SimpleNamespace(
            content=json.dumps({"model": "fixture-model", "messages": [], "max_tokens": 128}).encode(),
            url="https://fake-provider.invalid/v1/chat/completions",
            headers={"authorization": "Bearer fixture-not-a-secret"},
        )
        task = {
            "owner_id": "owner-a", "agent_id": "agent-a", "job_id": "job-count-bound",
            "memory": {"version": 1, "enabled": True, "entries": ["fixture memory"]},
            "sources": [{"source_id": "source-a"}], "files": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict("sys.modules", {"httpx": fake_httpx}):
                guard = container_probe.ProviderRequestGuard(task, "normal", Path(directory))
                first = guard(request)
                second = guard(request)

            self.assertEqual((first.status_code, second.status_code), (200, 429))
            self.assertEqual(guard.provider_work_count, 1)
            self.assertEqual(guard.rejections[0]["rejection_reason"], "physical_request_count_exceeded")
            self.assertFalse(guard.rejections[0]["provider_work_performed"])

    def test_boolean_output_limit_is_not_accepted_as_a_numeric_token_ceiling(self):
        class FakeResponse:
            def __init__(self, status_code, *, json, request):
                self.status_code = status_code
                self._json = json
                self.request = request

        fake_httpx = ModuleType("httpx")
        fake_httpx.Response = FakeResponse
        request = SimpleNamespace(
            content=json.dumps({"model": "fixture-model", "messages": [], "max_tokens": True}).encode(),
            url="https://fake-provider.invalid/v1/chat/completions",
            headers={"authorization": "Bearer fixture-not-a-secret"},
        )
        task = {
            "owner_id": "owner-a", "agent_id": "agent-a", "job_id": "job-token-bound",
            "memory": {"version": 1, "enabled": True, "entries": ["fixture memory"]},
            "sources": [{"source_id": "source-a"}], "files": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(container_probe, "OUTPUT", Path(directory)), patch.dict("sys.modules", {"httpx": fake_httpx}):
                guard = container_probe.ProviderRequestGuard(task, "normal", Path(directory))
                response = guard(request)

            self.assertEqual(response.status_code, 429)
            self.assertEqual(guard.provider_work_count, 0)
            self.assertEqual(guard.rejections[0]["rejection_reason"], "output_request_limit_exceeded")


class BootstrapRecoveryTests(unittest.TestCase):
    def _run_with_docker_fault(
        self, directory: str, *, build_fails: bool, cleanup_fails: bool = False
    ) -> tuple[Path, list[list[str]]]:
        from docs.qualification.p04 import native_runner

        calls: list[list[str]] = []
        source_identity = {
            "commit": "54bc5e509c985f37265c3d416bd2c64b10fc77ba", "clean": True,
            "pyproject_sha256": "fixture", "uv_lock_sha256": "fixture", "container_base": "fixture",
        }

        def run(argv, **kwargs):
            args = list(argv)
            calls.append(args)
            if args[0] == "uv":
                return subprocess.CompletedProcess(args, 0, stdout="uv 0.12.16", stderr="")
            if args[:2] == ["docker", "build"] and build_fails:
                raise subprocess.CalledProcessError(1, args, output="fixture build failed", stderr="daemon detail")
            if args[:2] == ["docker", "build"]:
                return subprocess.CompletedProcess(args, 0, stdout="built", stderr="")
            if cleanup_fails and args[:3] in (["docker", "image", "rm"], ["docker", "image", "inspect"]):
                raise subprocess.TimeoutExpired(args, timeout=1)
            if args[:3] == ["docker", "image", "rm"]:
                return subprocess.CompletedProcess(args, 0, stdout="removed", stderr="")
            if args[:3] == ["docker", "image", "inspect"] and "--format" not in args:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="No such image")
            self.fail(f"unexpected subprocess call: {args}")

        def docker(*args, **kwargs):
            if args == ("info", "--format", "{{.CgroupDriver}} {{.CgroupVersion}} {{.Architecture}}"):
                return "fixture 2 arm64"
            if args[:2] == ("image", "inspect") and "--format" in args:
                raise subprocess.CalledProcessError(1, args, stderr="inspection unavailable")
            raise AssertionError(f"unexpected Docker operation: {args}")

        with (
            patch.object(native_runner, "_source_identity", return_value=source_identity),
            patch.object(native_runner, "_docker_resources", return_value=[]),
            patch.object(native_runner, "_docker", side_effect=docker),
            patch.object(native_runner, "_build_context"),
            patch.object(native_runner.subprocess, "run", side_effect=run),
            patch.object(native_runner.uuid, "uuid4", return_value=SimpleNamespace(hex="a1b2c3d4e5f6")),
        ):
            try:
                evidence = native_runner.run_qualification(source=Path(directory), evidence_root=Path(directory) / "evidence")
            except Exception:
                evidence = Path(directory) / "evidence" / "p04-a1b2c3d4e5f6"
        return evidence, calls

    def test_successful_build_then_failed_inspection_records_failure_and_removes_owned_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence, calls = self._run_with_docker_fault(directory, build_fails=False)

            self.assertTrue((evidence / "run-failure.json").is_file(), "inspection failure was not retained")
            failure = json.loads((evidence / "run-failure.json").read_text())
            self.assertTrue((evidence / "image_cleanup.json").is_file(), "owned image cleanup was not retained")
            cleanup = json.loads((evidence / "image_cleanup.json").read_text())
            self.assertEqual(failure["stage"], "image_inspection")
            self.assertEqual(cleanup["image_tag"], "p04-hermes:p04-a1b2c3d4e5f6")
            self.assertTrue(cleanup["tag_absent_after_cleanup"])
            self.assertTrue(any(args[:3] == ["docker", "image", "rm"] for args in calls))

    def test_image_build_failure_is_recorded_and_attempts_exact_owned_tag_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence, calls = self._run_with_docker_fault(directory, build_fails=True)

            self.assertTrue((evidence / "run-failure.json").is_file(), "build failure was not retained")
            failure = json.loads((evidence / "run-failure.json").read_text())
            self.assertTrue((evidence / "image_cleanup.json").is_file(), "owned image cleanup was not retained")
            cleanup = json.loads((evidence / "image_cleanup.json").read_text())
            self.assertEqual(failure["stage"], "image_build")
            self.assertEqual(cleanup["image_tag"], "p04-hermes:p04-a1b2c3d4e5f6")
            self.assertTrue(any(args[:3] == ["docker", "image", "rm"] for args in calls))

    def test_cleanup_verification_failure_is_unknown_without_masking_build_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence, _ = self._run_with_docker_fault(directory, build_fails=True, cleanup_fails=True)

            failure = json.loads((evidence / "run-failure.json").read_text())
            cleanup = json.loads((evidence / "image_cleanup.json").read_text())
            self.assertEqual(failure["stage"], "image_build")
            self.assertEqual(failure["error_class"], "CalledProcessError")
            self.assertEqual(failure["cleanup_status"], "unknown_pending_verification")
            self.assertEqual(cleanup["status"], "unknown_pending_verification")


if __name__ == "__main__":
    unittest.main()
