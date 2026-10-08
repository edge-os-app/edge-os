from concurrent.futures import ThreadPoolExecutor
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


class ProviderBoundaryRegressionTests(unittest.TestCase):
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
