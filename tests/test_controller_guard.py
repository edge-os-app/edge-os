import contextlib
import hashlib
import io
import json
import os
import shutil
import shlex
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
from pathlib import Path

from scripts.controller_guard import GuardStore, TmuxBridge, checked_send, main, preflight, stop_decision


class FakeBridge:
    def __init__(self, capture="idle", sender="%1", target="%2"):
        self.capture = capture
        self.sender = sender
        self.target = target
        self.calls = []
        self.fail = set()

    def id(self):
        self.calls.append(("id",))
        self._raise("id")
        return self.sender

    def resolve(self, destination):
        self.calls.append(("resolve", destination))
        self._raise("resolve")
        return self.target

    def read(self, target):
        self.calls.append(("read", target))
        self._raise("read")
        return self.capture

    def message(self, target, text):
        self.calls.append(("message", target, text))
        self._raise("message")
        self.capture += (
            f"\n[tmux-bridge from:codex pane:{self.sender} at:work:0.0 — "
            f"load the smux skill to reply] {text}"
        )

    def enter(self, target):
        self.calls.append(("enter", target))
        self._raise("enter")
        self.capture += "\n❯ "

    def _raise(self, call):
        if call in self.fail:
            raise RuntimeError(call + " failed")


class CheckedSendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = GuardStore(Path(self.temp.name) / "guard.sqlite3")
        self.bridge = FakeBridge()
        self.request = {
            "task_id": "T-1",
            "event_id": "dispatch-1",
            "candidate": "abc123",
            "sender": "%1",
            "destination": "%2",
            "destination_name": "worker",
            "destination_id": "%2",
            "text": "[tmux-bridge from:codex] review candidate abc123",
            "preflight_sha256": hashlib.sha256(b"idle").hexdigest(),
            "confirm_idle": True,
            "confirm_no_draft": True,
        }

    def send(self):
        return checked_send(self.request, self.bridge, self.store, settle=lambda: None)

    def test_active_foreign_draft_is_blocked_before_type(self):
        self.bridge.capture = "❯ unfinished private draft"
        self.request["preflight_sha256"] = hashlib.sha256(self.bridge.capture.encode()).hexdigest()
        result = self.send()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(any(call[0] == "message" for call in self.bridge.calls))

    def test_foreign_smux_draft_is_preserved(self):
        self.bridge.capture = "❯ [tmux-bridge from:other pane:%9 at:work:0.1] another task"
        self.request["preflight_sha256"] = hashlib.sha256(self.bridge.capture.encode()).hexdigest()
        result = self.send()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(any(call[0] in {"message", "enter"} for call in self.bridge.calls))

    def test_changed_target_is_blocked_before_type(self):
        class ChangedTarget(FakeBridge):
            def resolve(inner, destination):
                inner.calls.append(("resolve", destination))
                inner.target = "%9"
                return "%9"

        self.bridge = ChangedTarget()
        result = self.send()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(any(call[0] == "message" for call in self.bridge.calls))

    def test_success_reads_before_type_checks_input_enters_once_and_reads_after(self):
        settles = []
        result = checked_send(self.request, self.bridge, self.store, settle=lambda: settles.append(True))
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(len(settles), 1)
        names = [call[0] for call in self.bridge.calls]
        self.assertEqual(names.count("message"), 1)
        self.assertEqual(names.count("enter"), 1)
        self.assertEqual(names.count("read"), 3)
        self.assertLess(names.index("read"), names.index("message"))
        self.assertLess(names.index("message"), names.index("enter"))
        self.assertLess(names.index("enter"), len(names) - 1 - names[::-1].index("read"))
        self.assertNotIn(self.request["text"].encode(), self.store.path.read_bytes())

    def test_duplicate_event_never_sends_twice(self):
        self.send()
        self.bridge.calls.clear()
        result = self.send()
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(self.bridge.calls, [])

    def test_prepared_event_cannot_change_its_message(self):
        self.store.put_record({
            **self.request,
            "status": "PREPARED",
            "preflight_sha256": self.request["preflight_sha256"],
        })
        self.request["text"] = "different content under the same event"
        result = self.send()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(any(call[0] in {"message", "enter"} for call in self.bridge.calls))

    def test_lost_enter_is_unconfirmed_and_never_retried(self):
        self.bridge.fail.add("enter")
        result = self.send()
        self.assertEqual(result["status"], "UNCONFIRMED")
        self.bridge.fail.clear()
        self.bridge.calls.clear()
        again = self.send()
        self.assertEqual(again["status"], "UNCONFIRMED")
        self.assertEqual(self.bridge.calls, [])

    def test_crash_after_durable_enter_intent_never_retries_keypress(self):
        class CrashAfterIntent(GuardStore):
            def put_record(inner, record):
                super(CrashAfterIntent, inner).put_record(record)
                if record["status"] == "UNCONFIRMED":
                    raise RuntimeError("simulated process loss before Enter")

        crashing_store = CrashAfterIntent(self.store.path)
        with self.assertRaisesRegex(RuntimeError, "process loss"):
            checked_send(self.request, self.bridge, crashing_store, settle=lambda: None)
        self.bridge.calls.clear()
        result = checked_send(self.request, self.bridge, self.store, settle=lambda: None)
        self.assertEqual(result["status"], "UNCONFIRMED")
        self.assertFalse(any(call[0] == "enter" for call in self.bridge.calls))

    def test_ambiguous_post_read_is_unconfirmed(self):
        class Ambiguous(FakeBridge):
            def enter(inner, target):
                inner.calls.append(("enter", target))
                inner.capture = "❯ [tmux-bridge from:codex] review candidate abc123"

        self.bridge = Ambiguous()
        result = self.send()
        self.assertEqual(result["status"], "UNCONFIRMED")

    def test_bridge_command_error_before_enter_blocks(self):
        self.bridge.fail.add("message")
        result = self.send()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(any(call[0] == "enter" for call in self.bridge.calls))

    def test_typed_own_draft_can_resume_with_same_input(self):
        class TypedThenLost(FakeBridge):
            def message(inner, target, text):
                FakeBridge.message(inner, target, text)
                raise RuntimeError("response lost after type")

        self.bridge = TypedThenLost()
        first = self.send()
        self.assertEqual(first["status"], "TYPED")
        self.bridge.calls.clear()
        result = self.send()
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertFalse(any(call[0] == "message" for call in self.bridge.calls))
        self.assertEqual(sum(call[0] == "enter" for call in self.bridge.calls), 1)

    def test_changed_own_draft_blocks_recovery_without_enter(self):
        class TypedThenLost(FakeBridge):
            def message(inner, target, text):
                FakeBridge.message(inner, target, text)
                raise RuntimeError("response lost after type")

        self.bridge = TypedThenLost()
        self.assertEqual(self.send()["status"], "TYPED")
        self.request["text"] = "replacement message"
        self.bridge.calls.clear()
        result = self.send()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(any(call[0] == "enter" for call in self.bridge.calls))


class StopGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / ".codex" / "controller-guard.json"
        self.state.parent.mkdir()
        self.store = GuardStore(self.state.parent / "controller-guard.sqlite3")
        self.payload = {"session_id": "s1", "cwd": str(self.root), "stop_hook_active": False}
        self.binding = {
            "host": "codex",
            "session_id": "s1",
            "agent_id": "codex:s1",
            "pane_id": "%1",
            "cwd": str(self.root),
            "status": "ACTIVE",
            "required_reports": [],
            "approved_work": [],
        }

    def write_state(self, bindings):
        self.state.write_text(json.dumps({"version": 1, "bindings": bindings}))

    def test_no_registration_allows_stop(self):
        self.write_state([])
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")

    def test_missing_registration_allows_without_creating_state(self):
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")
        self.assertFalse(self.state.exists())

    def test_required_report_missing_blocks_then_durable_reason_allows_repeat(self):
        self.binding["required_reports"] = ["reports/final.md"]
        self.write_state([self.binding])
        first = stop_decision("codex", self.payload, self.state, self.store)
        second = stop_decision("codex", self.payload, self.state, self.store)
        self.assertEqual(first["decision"], "block")
        self.assertEqual(second["decision"], "allow")

    def test_eligible_approved_work_blocks(self):
        self.binding["approved_work"] = [{"id": "T-1", "status": "pending"}]
        self.write_state([self.binding])
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "block")

    def test_legitimate_terminal_or_wait_states_allow(self):
        for status in ("AWAITING_EVENT", "BLOCKED", "BUDGET_EXHAUSTED", "APPROVAL_REQUIRED", "INTERRUPTED", "RUN_LIMIT", "COMPLETE"):
            with self.subTest(status=status):
                self.binding["status"] = status
                self.write_state([self.binding])
                self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")

    def test_unfinished_delivery_blocks_and_other_session_does_not_inherit(self):
        self.store.put_record({
            "task_id": "T-1", "event_id": "e1", "candidate": "abc123",
            "sender": "%1", "destination": "%2", "status": "TYPED",
        })
        self.write_state([self.binding])
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "block")
        self.payload["session_id"] = "other"
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")

    def test_malformed_state_and_bad_identity_fail_closed_for_registered_session(self):
        self.state.write_text("{")
        result = stop_decision("codex", self.payload, self.state, self.store)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")
        self.write_state([{**self.binding, "cwd": str(self.root / "wrong")}])
        result = stop_decision("codex", self.payload, self.state, self.store)
        self.assertEqual(result["decision"], "block")

    def test_malformed_registered_binding_blocks_once(self):
        self.write_state([{**self.binding, "status": "UNKNOWN"}])
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "block")
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")

    def test_stop_hook_active_always_allows_without_second_block(self):
        self.binding["required_reports"] = ["reports/final.md"]
        self.write_state([self.binding])
        self.payload["stop_hook_active"] = True
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")

    def test_hook_cli_emits_valid_codex_block_json(self):
        self.binding["required_reports"] = ["reports/final.md"]
        cli_root = self.root / "cli-state"
        cli_root.mkdir()
        (cli_root / "bindings.json").write_text(json.dumps({"version": 1, "bindings": [self.binding]}))
        out = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(self.payload))), contextlib.redirect_stdout(out):
            self.assertEqual(main(["--state-root", str(cli_root), "hook", "codex"]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["decision"], "block")
        self.assertIn("missing-report", result["reason"])

    def test_hook_cli_emits_valid_allow_json_for_claude_without_binding(self):
        out = io.StringIO()
        payload = {"session_id": "claude-session", "cwd": str(self.root), "stop_hook_active": False}
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(out):
            self.assertEqual(main(["--state-root", str(self.root / "none"), "hook", "claude"]), 0)
        self.assertEqual(json.loads(out.getvalue()), {"continue": False})

    def test_binding_registration_rejects_report_path_escape(self):
        from scripts.controller_guard import save_binding

        with self.assertRaises(ValueError):
            save_binding(self.state, {**self.binding, "required_reports": ["../private.txt"]})

    def test_bind_update_cli_uses_codex_session_environment_and_keeps_identity(self):
        root = self.root / "cli-bind"
        source = {"host": "codex", "cwd": str(self.root), "required_reports": [], "approved_work": []}
        output = io.StringIO()
        with patch.dict(os.environ, {"CODEX_SESSION_ID": "s1", "TMUX_PANE": "%1"}):
            with patch("sys.stdin", io.StringIO(json.dumps(source))), contextlib.redirect_stdout(output):
                self.assertEqual(main(["--state-root", str(root), "bind", "codex"]), 0)
            self.assertTrue(json.loads(output.getvalue())["registered"])
            binding = json.loads((root / "bindings.json").read_text())["bindings"][0]
            self.assertEqual((binding["session_id"], binding["agent_id"], binding["pane_id"]), ("s1", "codex:s1", "%1"))
            binding["status"] = "BLOCKED"
            output = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(binding))), contextlib.redirect_stdout(output):
                self.assertEqual(main(["--state-root", str(root), "update", "codex"]), 0)
            updated = json.loads((root / "bindings.json").read_text())["bindings"][0]
            self.assertEqual(updated["status"], "BLOCKED")
            self.assertEqual(updated["cwd"], str(self.root))


@unittest.skipUnless(os.environ.get("RUN_LIVE_TMUX") == "1", "set RUN_LIVE_TMUX=1 to create an isolated tmux fixture")
class LiveBridgeTests(unittest.TestCase):
    def test_actual_bridge_submission_duplicate_and_draft_preservation(self):
        tmux = shutil.which("tmux")
        bridge_bin = shutil.which("tmux-bridge")
        if not tmux or not bridge_bin:
            self.skipTest("tmux or the installed tmux-bridge is unavailable")
        session = "controller-guard-test-" + uuid.uuid4().hex[:8]
        old_pane = os.environ.get("TMUX_PANE")
        sender = target = None
        try:
            subprocess.run([tmux, "new-session", "-d", "-s", session, "-x", "120", "-y", "35",
                            "python3", "-u", "-c", "import time; time.sleep(300)"], check=True)
            code = "import sys;print('❯ ',end='',flush=True);exec(\"for line in sys.stdin:\\n print('RECEIVED '+line.strip(),flush=True)\\n print('❯ ',end='',flush=True)\")"
            subprocess.run([tmux, "split-window", "-h", "-t", session + ":0",
                            "python3 -u -c " + shlex.quote(code)], check=True)
            # The second pane is the only process that receives fixture input.
            time.sleep(0.25)
            sender = subprocess.run([tmux, "display-message", "-t", session + ":0.0", "-p", "#{pane_id}"],
                                    check=True, text=True, capture_output=True).stdout.strip()
            target = subprocess.run([tmux, "display-message", "-t", session + ":0.1", "-p", "#{pane_id}"],
                                    check=True, text=True, capture_output=True).stdout.strip()
            os.environ["TMUX_PANE"] = sender
            bridge = TmuxBridge(bridge_bin)
            with tempfile.TemporaryDirectory() as directory:
                store = GuardStore(Path(directory) / "guard.sqlite3")
                check = preflight(target, bridge)
                first = {
                    "task_id": "fixture", "event_id": "send-once", "candidate": "fixture-sha",
                    "sender": sender, "destination": target, "destination_id": target,
                    "destination_name": target, "text": "fixture transport check",
                    "preflight_sha256": check["capture_sha256"], "confirm_idle": True, "confirm_no_draft": True,
                }
                self.assertEqual(checked_send(first, bridge, store)["status"], "SUBMITTED")
                self.assertEqual(checked_send(first, bridge, store)["status"], "SUBMITTED")
                capture_after_duplicate = bridge.read(target)
                self.assertEqual(capture_after_duplicate.count("RECEIVED "), 1)

                bridge.read(target)
                bridge._run("type", target, "user draft")
                draft_check = preflight(target, bridge)
                second = {**first, "event_id": "preserve-draft", "text": "must not overwrite draft",
                          "preflight_sha256": draft_check["capture_sha256"]}
                result = checked_send(second, bridge, store)
                self.assertEqual(result["status"], "BLOCKED")
                final_capture = bridge.read(target)
                self.assertIn("user draft", final_capture)
                self.assertNotIn("must not overwrite draft", final_capture)
        finally:
            if old_pane is None:
                os.environ.pop("TMUX_PANE", None)
            else:
                os.environ["TMUX_PANE"] = old_pane
            if session:
                subprocess.run([tmux, "kill-session", "-t", session], check=False)


if __name__ == "__main__":
    unittest.main()
