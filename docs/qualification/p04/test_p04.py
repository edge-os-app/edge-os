import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from qualification import (
    IdempotencyConflict,
    JobRegistry,
    MemoryStore,
    ProviderTimeout,
    TaskIdentity,
    TaskWorkspace,
    UsageLedger,
    run_with_workspace,
    safe_error,
    validate_outcome,
)


def outcome(status: str, *, intake_record_id: str | None = None) -> str:
    return json.dumps(
        {
            "operation_id": "op-1",
            "intake_record_id": intake_record_id,
            "stage": "INTERPRETATION",
            "outcome": status,
            "code": status.lower(),
            "findings": (
                [{"code": "fixture", "path": "/", "detail": "fixture finding"}]
                if status in {"NEEDS_CLARIFICATION", "UNSUPPORTED", "UNRESOLVED", "INVALID_INPUT", "CONFLICTED"}
                else []
            ),
            "retry": "NOT_RETRYABLE",
        }
    )


def dummy_provider(_: str) -> str:
    return outcome("COMPILED")


def denied_network_request(_: str) -> None:
    raise PermissionError("network disabled by fixture")


class MemoryScopeTests(unittest.TestCase):
    def test_task_identity_requires_all_trusted_ids(self) -> None:
        with self.assertRaises(ValueError):
            TaskIdentity("owner-a", "agent-a", " ")

    def test_same_owner_agents_are_separate_and_other_owner_is_denied(self) -> None:
        store = MemoryStore()
        store.correct("owner-a", "agent-a", "prefers concise reports", ["https://source.test/a"])

        self.assertEqual(store.retrieve("owner-a", "agent-a").version, 1)
        self.assertIsNone(store.retrieve("owner-a", "agent-b"))
        with self.assertRaises(PermissionError):
            store.retrieve("owner-b", "agent-a")

    def test_task_snapshot_records_memory_version_and_suggestions_need_adoption(self) -> None:
        store = MemoryStore()
        suggestion_id = store.suggest("owner-a", "agent-a", "try a shorter lookback", ["https://source.test/b"])
        self.assertIsNone(store.retrieve("owner-a", "agent-a"))

        store.adopt_suggestion("owner-a", "agent-a", suggestion_id)
        snapshot = store.task_snapshot("owner-a", "agent-a")
        self.assertEqual(snapshot.version, 1)
        self.assertEqual(snapshot.entries[0].text, "try a shorter lookback")
        self.assertFalse(hasattr(snapshot, "financial_authority"))

    def test_disable_and_clear_stop_future_retrieval(self) -> None:
        store = MemoryStore()
        store.correct("owner-a", "agent-a", "prefers short reports", [])
        first = store.task_snapshot("owner-a", "agent-a")
        store.correct("owner-a", "agent-a", "wants source links", ["https://source.test/c"])
        second = store.task_snapshot("owner-a", "agent-a")
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertEqual([item.version for item in store.history("owner-a", "agent-a")], [1, 2])
        store.disable("owner-a", "agent-a")
        self.assertIsNone(store.task_snapshot("owner-a", "agent-a"))
        store.enable("owner-a", "agent-a")
        self.assertEqual(store.task_snapshot("owner-a", "agent-a").version, 2)
        store.clear("owner-a", "agent-a")
        self.assertIsNone(store.task_snapshot("owner-a", "agent-a"))
        self.assertEqual([(item.version, item.entries) for item in store.history("owner-a", "agent-a")], [(3, ())])


class JobAndWorkspaceTests(unittest.TestCase):
    def test_idempotent_duplicate_returns_same_job_and_conflict_is_rejected(self) -> None:
        jobs = JobRegistry()
        first = jobs.submit("owner-a", "agent-a", "request-1", "sha256:a")
        self.assertEqual(jobs.submit("owner-a", "agent-a", "request-1", "sha256:a"), first)
        self.assertNotEqual(jobs.submit("owner-b", "agent-a", "request-1", "sha256:a"), first)
        with self.assertRaises(IdempotencyConflict):
            jobs.submit("owner-a", "agent-a", "request-1", "sha256:b")

    def test_workspace_rejects_escape_and_keeps_job_paths_separate(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            one = TaskWorkspace(base / "job-one")
            two = TaskWorkspace(base / "job-two")
            one.write_text("input.json", "one")
            two.write_text("input.json", "two")

            self.assertEqual(one.read_text("input.json"), "one")
            self.assertEqual(two.read_text("input.json"), "two")
            with self.assertRaises(PermissionError):
                one.path("../job-two/input.json")

    def test_workspace_is_removed_after_timeout_or_failure(self) -> None:
        async def never(_: TaskWorkspace) -> str:
            await asyncio.sleep(10)
            return "unused"

        async def run(root: str) -> None:
            await run_with_workspace(root, "job-timeout", never, timeout=0.01)

        with tempfile.TemporaryDirectory() as root:
            workspaces: list[Path] = []

            async def capture(workspace: TaskWorkspace) -> str:
                workspaces.append(workspace.root)
                return await never(workspace)

            with self.assertRaises(ProviderTimeout):
                asyncio.run(run_with_workspace(root, "job-timeout", capture, timeout=0.01))
            self.assertEqual(len(workspaces), 1)
            self.assertFalse(workspaces[0].exists())

            async def fail(workspace: TaskWorkspace) -> str:
                workspaces.append(workspace.root)
                raise RuntimeError("fixture failure")

            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                asyncio.run(run_with_workspace(root, "job-failure", fail, timeout=1))
            self.assertFalse(workspaces[1].exists())

    def test_cancelled_task_cleans_workspace_and_propagates_cancellation(self) -> None:
        async def exercise(root: str) -> tuple[asyncio.Event, list[Path]]:
            started = asyncio.Event()
            cleaned = asyncio.Event()
            workspaces: list[Path] = []

            async def wait(workspace: TaskWorkspace) -> str:
                workspaces.append(workspace.root)
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()

            task = asyncio.create_task(run_with_workspace(root, "job-cancel", wait, timeout=5))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            return cleaned, workspaces

        with tempfile.TemporaryDirectory() as root:
            cleaned, workspaces = asyncio.run(exercise(root))
            self.assertTrue(cleaned.is_set())
            self.assertEqual(len(workspaces), 1)
            self.assertFalse(workspaces[0].exists())


class UsageAndOutputTests(unittest.TestCase):
    def test_dummy_provider_output_is_valid_and_network_denial_is_a_fixture(self) -> None:
        self.assertEqual(validate_outcome(dummy_provider("fixture prompt"))["outcome"], "COMPILED")
        with self.assertRaisesRegex(PermissionError, "network disabled by fixture"):
            denied_network_request("https://provider.invalid")

    def test_unknown_usage_keeps_reservation_until_reconciled(self) -> None:
        ledger = UsageLedger()
        ledger.reserve("job-1", 1.00)
        unknown = ledger.settle("job-1", actual_usd=None, actual_tokens=None)
        self.assertEqual(unknown.status, "UNKNOWN")
        self.assertEqual(ledger.reserved_usd, 1.00)
        settled = ledger.reconcile("job-1", actual_usd=0.24, actual_tokens=12)
        self.assertEqual(settled.status, "SETTLED")
        self.assertEqual(ledger.reserved_usd, 0)

    def test_outcome_contract_preserves_each_p02_status(self) -> None:
        for status, intake_id in (
            ("NEEDS_CLARIFICATION", "intake-1"),
            ("UNSUPPORTED", "intake-1"),
            ("UNRESOLVED", "intake-1"),
            ("INVALID_INPUT", None),
            ("COMPILED", None),
            ("CONFLICTED", None),
        ):
            self.assertEqual(validate_outcome(outcome(status, intake_record_id=intake_id))["outcome"], status)

    def test_malformed_truncated_and_untyped_outputs_are_rejected(self) -> None:
        for payload in (
            "{\"outcome\":",
            "not json",
            outcome("MADE_UP"),
            outcome("NEEDS_CLARIFICATION"),
            json.dumps({**json.loads(outcome("COMPILED")), "extra": True}),
            json.dumps({**json.loads(outcome("COMPILED")), "outcome": []}),
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_outcome(payload)

    def test_provider_errors_are_recorded_without_untrusted_detail(self) -> None:
        safe = safe_error("PROVIDER_FAILURE", "Authorization failed: sk-test-secret")
        self.assertEqual(safe, {"code": "PROVIDER_FAILURE", "message": "Provider request failed."})
        self.assertNotIn("sk-test-secret", json.dumps(safe))


if __name__ == "__main__":
    unittest.main()
