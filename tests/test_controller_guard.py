import contextlib
import hashlib
import io
import json
import os
import shutil
import shlex
import sqlite3
import subprocess
import sys
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
            "host": "codex",
            "session_id": "s1",
            "agent_id": "codex:s1",
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

    def test_fresh_prepared_event_never_adopts_matching_existing_draft(self):
        self.bridge.capture = "❯ [tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] " + self.request["text"]
        self.request["preflight_sha256"] = hashlib.sha256(self.bridge.capture.encode()).hexdigest()
        self.request["confirm_idle"] = False
        self.request["confirm_no_draft"] = False
        result = self.send()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(any(call[0] == "enter" for call in self.bridge.calls))

    def test_prepared_event_cannot_resume_matching_draft_even_if_preflight_confirmed(self):
        self.bridge.capture = "❯ [tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] " + self.request["text"]
        self.request["preflight_sha256"] = hashlib.sha256(self.bridge.capture.encode()).hexdigest()
        self.store.put_record({**self.request, "status": "PREPARED"})
        result = self.send()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(any(call[0] == "enter" for call in self.bridge.calls))

    def test_extra_body_and_concatenated_envelope_are_rejected_on_type_and_recovery(self):
        header = "[tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] "
        for kind, extra in (
            ("extra-body", "unrelated draft ] " + self.request["text"]),
            ("second-envelope", header + self.request["text"]),
        ):
            for lost_response in (False, True):
                with self.subTest(kind=kind, lost_response=lost_response):
                    self.request["event_id"] = f"{kind}-{lost_response}"

                    class MismatchedTyped(FakeBridge):
                        def message(inner, target, text):
                            inner.calls.append(("message", target, text))
                            inner.capture += "\n" + header + extra
                            if lost_response:
                                raise RuntimeError("type response lost")

                    self.bridge = MismatchedTyped()
                    first = self.send()
                    self.assertEqual(first["status"], "BLOCKED")
                    self.assertFalse(any(call[0] == "enter" for call in self.bridge.calls))
                    self.bridge.calls.clear()
                    self.assertEqual(self.send()["status"], "BLOCKED")
                    self.assertEqual(self.bridge.calls, [])

    def test_durable_typed_mismatched_body_cannot_recover(self):
        self.bridge.capture = "❯ [tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] unrelated draft ] " + self.request["text"]
        self.store.put_record({**self.request, "status": "TYPED",
                               "typed_sha256": hashlib.sha256(self.bridge.capture.encode()).hexdigest()})
        self.assertEqual(self.send()["status"], "BLOCKED")
        self.assertFalse(any(call[0] in {"message", "enter"} for call in self.bridge.calls))

    def test_post_enter_confirmation_requires_exact_message_body(self):
        header = "[tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] "

        class ExtraBodyAfterEnter(FakeBridge):
            def enter(inner, target):
                inner.calls.append(("enter", target))
                inner.capture = "\n" + header + "unrelated draft ] " + self.request["text"] + "\n❯ "

        self.bridge = ExtraBodyAfterEnter()
        self.assertEqual(self.send()["status"], "UNCONFIRMED")
        self.assertEqual(sum(call[0] == "enter" for call in self.bridge.calls), 1)

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
            "host": "codex", "session_id": "s1", "agent_id": "codex:s1",
            "sender": "%1", "destination": "%2", "status": "TYPED",
        })
        self.binding["approved_work"] = [{"id": "T-1", "status": "pending"}]
        self.write_state([self.binding])
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "block")
        self.payload["session_id"] = "other"
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")

    def test_registered_session_reusing_pane_does_not_inherit_other_binding_task(self):
        self.store.put_record({
            "task_id": "OLD-TASK", "event_id": "e1", "candidate": "abc123",
            "host": "codex", "session_id": "old-session", "agent_id": "codex:old-session",
            "sender": "%1", "destination": "%2", "status": "TYPED",
        })
        self.write_state([self.binding])
        self.assertEqual(stop_decision("codex", self.payload, self.state, self.store)["decision"], "allow")

    def test_active_binding_checks_unfinished_return_for_completed_task(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                cli_root = self.root / (host + "-completed-delivery-state")
                cli_root.mkdir()
                GuardStore(cli_root / "delivery.sqlite3").put_record({
                    "task_id": "T-1", "event_id": "return-report", "candidate": "abc123",
                    "host": host, "session_id": "s1", "agent_id": host + ":s1",
                    "sender": "%1", "destination": "%2", "status": "TYPED",
                })
                binding = {**self.binding, "host": host, "agent_id": host + ":s1",
                           "approved_work": [{"id": "T-1", "status": "complete"}]}
                (cli_root / "bindings.json").write_text(json.dumps({"version": 1, "bindings": [binding]}))
                command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/controller_guard.py"),
                           "--state-root", str(cli_root), "hook", host]
                output = subprocess.run(command, input=json.dumps(self.payload), text=True, capture_output=True, check=False)
                self.assertEqual(output.returncode, 0, output.stderr)
                result = json.loads(output.stdout)
                self.assertEqual(result.get("decision"), "block")
                self.assertIn("unfinished-delivery", result.get("reason", ""))
                self.assertNotIn("approved-work", result["reason"])
                for status in ("AWAITING_EVENT", "BLOCKED", "BUDGET_EXHAUSTED", "APPROVAL_REQUIRED", "INTERRUPTED", "RUN_LIMIT", "COMPLETE"):
                    binding["status"] = status
                    (cli_root / "bindings.json").write_text(json.dumps({"version": 1, "bindings": [binding]}))
                    output = subprocess.run(command, input=json.dumps(self.payload), text=True, capture_output=True, check=False)
                    self.assertEqual(output.returncode, 0, output.stderr)
                    self.assertEqual(json.loads(output.stdout), {})

    def test_actual_hook_rejects_invalid_path_text_once_for_both_hosts(self):
        script = str(Path(__file__).resolve().parents[1] / "scripts/controller_guard.py")
        for host in ("codex", "claude"):
            for index, malformed in enumerate(("cwd", "report")):
                with self.subTest(host=host, malformed=malformed), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    session_id = f"{host}-{malformed}-{index}"
                    binding = {
                        "host": host, "session_id": session_id, "agent_id": f"{host}:{session_id}",
                        "pane_id": "%1", "cwd": str(root), "status": "ACTIVE",
                        "required_reports": [], "approved_work": [],
                    }
                    if malformed == "cwd":
                        binding["cwd"] = str(root) + "\0bad"
                    else:
                        binding["required_reports"] = ["reports/final\0.md"]
                    (root / "bindings.json").write_text(json.dumps({"version": 1, "bindings": [binding]}))
                    payload = {"session_id": session_id, "cwd": str(root), "stop_hook_active": False}
                    command = [sys.executable, script, "--state-root", str(root), "hook", host]
                    outputs = [subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True, check=False)
                               for _ in range(2)]
                    self.assertEqual(outputs[0].returncode, 0, outputs[0].stderr)
                    self.assertEqual(json.loads(outputs[0].stdout).get("decision"), "block")
                    self.assertEqual(outputs[1].returncode, 0, outputs[1].stderr)
                    self.assertEqual(json.loads(outputs[1].stdout), {})

    def test_hook_path_io_failure_emits_one_repair_block_for_both_hosts(self):
        realpath = os.path.realpath
        for host in ("codex", "claude"):
            for field in ("cwd", "report"):
                with self.subTest(host=host, field=field):
                    cli_root = self.root / f"{host}-{field}-io-state"
                    cli_root.mkdir()
                    session = host + "-" + field
                    report = self.root / "final.md"
                    failing_path = str(self.root) if field == "cwd" else realpath(report)
                    binding = {**self.binding, "host": host, "session_id": session,
                               "agent_id": host + ":" + session, "required_reports": ["final.md"]}
                    (cli_root / "bindings.json").write_text(json.dumps({"version": 1, "bindings": [binding]}))
                    payload = {**self.payload, "session_id": session}

                    def failed_realpath(path, *args, **kwargs):
                        if os.fspath(path) == failing_path:
                            raise OSError("filesystem unavailable")
                        return realpath(path, *args, **kwargs)

                    outputs = []
                    with patch("scripts.controller_guard.os.path.realpath", new=failed_realpath):
                        for _ in range(2):
                            output = io.StringIO()
                            with patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(output):
                                try:
                                    code = main(["--state-root", str(cli_root), "hook", host])
                                except OSError as exc:
                                    self.fail(f"hook raised a filesystem error instead of repair JSON: {exc}")
                                self.assertEqual(code, 0)
                            outputs.append(json.loads(output.getvalue()))
                    self.assertEqual(outputs[0].get("decision"), "block")
                    self.assertIn("Repair", outputs[0].get("reason", ""))
                    self.assertEqual(outputs[1], {})

    def test_binding_cli_rejects_nul_paths_for_both_hosts(self):
        script = str(Path(__file__).resolve().parents[1] / "scripts/controller_guard.py")
        for host in ("codex", "claude"):
            for field in ("cwd", "required_reports"):
                with self.subTest(host=host, field=field), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    binding = {
                        "host": host, "session_id": f"{host}-bind", "agent_id": f"{host}:{host}-bind",
                        "pane_id": "%1", "cwd": str(root), "status": "ACTIVE",
                        "required_reports": [], "approved_work": [],
                    }
                    if field == "cwd":
                        binding["cwd"] += "\0bad"
                    else:
                        binding["required_reports"] = ["reports\0/final.md"]
                    result = subprocess.run(
                        [sys.executable, script, "--state-root", str(root / "state"), "bind", host],
                        input=json.dumps(binding), text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 2)

    def test_legacy_delivery_rows_migrate_as_unbound_history(self):
        path = self.root / "legacy.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE delivery (task_id TEXT,event_id TEXT,candidate TEXT,sender TEXT,destination TEXT,status TEXT NOT NULL,preflight_sha256 TEXT,typed_sha256 TEXT,text_sha256 TEXT,updated_at REAL NOT NULL,PRIMARY KEY(task_id,event_id,candidate,sender,destination))")
            db.execute("INSERT INTO delivery VALUES ('T-old','e1','c1','%1','%2','TYPED',NULL,NULL,NULL,1)")
            db.execute("CREATE TABLE stop_seen (session_id TEXT NOT NULL,reason_id TEXT NOT NULL,updated_at REAL NOT NULL,PRIMARY KEY(session_id,reason_id))")
            db.execute("INSERT INTO stop_seen VALUES ('old-session','old-reason',1)")
        migrated = GuardStore(path)
        with sqlite3.connect(path) as db:
            row = db.execute("SELECT host,session_id,agent_id,task_id FROM delivery").fetchone()
            self.assertEqual(row, ("", "", "", "T-old"))
            self.assertEqual(db.execute("SELECT host,session_id,reason_id FROM stop_seen").fetchone(), ("", "old-session", "old-reason"))
        self.assertEqual(migrated.open_for_binding("codex", "new-session", "codex:new-session", ["T-old"]), [])

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

    def test_actual_hook_cli_malformed_identity_and_type_block_once(self):
        cli_root = self.root / "malformed-state"
        cli_root.mkdir()
        for malformed in (
            {k: v for k, v in self.binding.items() if k != "pane_id"},
            {**self.binding, "session_id": "s2", "agent_id": "codex:s2", "status": {"unexpected": "object"}},
        ):
            payload = {**self.payload, "session_id": malformed["session_id"]}
            with self.subTest(malformed=malformed):
                (cli_root / "bindings.json").write_text(json.dumps({"version": 1, "bindings": [malformed]}))
                outputs = []
                for _ in range(2):
                    out = io.StringIO()
                    with patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(out):
                        self.assertEqual(main(["--state-root", str(cli_root), "hook", "codex"]), 0)
                    outputs.append(json.loads(out.getvalue()))
                self.assertEqual(outputs[0].get("decision"), "block")
                self.assertIn("malformed", outputs[0].get("reason", ""))
                self.assertEqual(outputs[1], {})

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
        self.assertEqual(json.loads(out.getvalue()), {})

    def test_allowed_hook_paths_emit_neutral_json(self):
        cli_root = self.root / "allowed-state"
        cli_root.mkdir()
        self.write_state([self.binding])
        for status in ("AWAITING_EVENT", "BLOCKED", "BUDGET_EXHAUSTED", "APPROVAL_REQUIRED", "INTERRUPTED", "RUN_LIMIT", "COMPLETE"):
            self.binding["status"] = status
            (cli_root / "bindings.json").write_text(json.dumps({"version": 1, "bindings": [self.binding]}))
            out = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(self.payload))), contextlib.redirect_stdout(out):
                self.assertEqual(main(["--state-root", str(cli_root), "hook", "codex"]), 0)
            self.assertEqual(json.loads(out.getvalue()), {})

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

    def test_explicit_pane_id_does_not_query_bridge_identity(self):
        root = self.root / "explicit-pane"
        source = {**self.binding, "pane_id": "%7"}
        output = io.StringIO()
        with patch("scripts.controller_guard.TmuxBridge.id", side_effect=RuntimeError("bridge unavailable")):
            with patch("sys.stdin", io.StringIO(json.dumps(source))), contextlib.redirect_stdout(output):
                self.assertEqual(main(["--state-root", str(root), "bind", "codex"]), 0)
        registered = json.loads((root / "bindings.json").read_text())["bindings"][0]
        self.assertEqual(registered["pane_id"], "%7")


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
                    "task_id": "fixture", "host": "codex", "session_id": "fixture-session",
                    "agent_id": "codex:fixture-session", "event_id": "send-once", "candidate": "fixture-sha",
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

    def test_actual_bridge_uncertainty_and_same_event_typed_recovery(self):
        tmux = shutil.which("tmux")
        bridge_bin = shutil.which("tmux-bridge")
        if not tmux or not bridge_bin:
            self.skipTest("tmux or the installed tmux-bridge is unavailable")
        session = "controller-guard-fault-" + uuid.uuid4().hex[:8]
        old_pane = os.environ.get("TMUX_PANE")
        try:
            subprocess.run([tmux, "new-session", "-d", "-s", session, "-x", "120", "-y", "35",
                            "python3", "-u", "-c", "import time; time.sleep(300)"], check=True)
            code = "import sys;print('❯ ',end='',flush=True);exec(\"for line in sys.stdin:\\n print('RECEIVED '+line.strip(),flush=True)\\n print('❯ ',end='',flush=True)\")"
            subprocess.run([tmux, "split-window", "-h", "-t", session + ":0",
                            "python3 -u -c " + shlex.quote(code)], check=True)
            time.sleep(0.25)
            sender = subprocess.run([tmux, "display-message", "-t", session + ":0.0", "-p", "#{pane_id}"],
                                    check=True, text=True, capture_output=True).stdout.strip()
            target = subprocess.run([tmux, "display-message", "-t", session + ":0.1", "-p", "#{pane_id}"],
                                    check=True, text=True, capture_output=True).stdout.strip()
            exit_code = "import sys;print('❯ ',end='',flush=True);exec(\"for line in sys.stdin:\\n print('EXITING '+line.strip(),flush=True)\\n sys.exit(0)\")"
            subprocess.run([tmux, "split-window", "-v", "-t", target,
                            "python3 -u -c " + shlex.quote(exit_code)], check=True)
            time.sleep(0.2)
            ambiguous_target = subprocess.run([tmux, "display-message", "-t", session + ":0.2", "-p", "#{pane_id}"],
                                              check=True, text=True, capture_output=True).stdout.strip()
            os.environ["TMUX_PANE"] = sender
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                wrapper = path / "bridge-fault-injector"
                wrapper.write_text(
                    "#!/usr/bin/env python3\nimport os, subprocess, sys\n"
                    f"real = {bridge_bin!r}\nargs = sys.argv[1:]\n"
                    "fault = os.environ.get('CONTROLLER_GUARD_FAULT')\n"
                    "if fault == 'enter-missed' and args[:1] == ['keys'] and 'Enter' in args: sys.exit(0)\n"
                    "result = subprocess.run([real, *args], text=True, capture_output=True)\n"
                    "sys.stdout.write(result.stdout); sys.stderr.write(result.stderr)\n"
                    "if result.returncode: sys.exit(result.returncode)\n"
                    "if (fault == 'message-lost' and args[:1] == ['message']) or (fault == 'enter-lost' and args[:1] == ['keys'] and 'Enter' in args): sys.exit(17)\n"
                    "sys.exit(0)\n", encoding="utf-8")
                wrapper.chmod(0o700)
                store = GuardStore(path / "guard.sqlite3")
                real_bridge = TmuxBridge(bridge_bin)
                check = preflight(target, real_bridge)
                base = {
                    "task_id": "fixture-task", "host": "codex", "session_id": "fixture-session",
                    "agent_id": "codex:fixture-session", "event_id": "typed-recovery",
                    "candidate": "fixture-sha",
                    "sender": sender, "destination": target, "destination_id": target,
                    "destination_name": target, "text": "fixture uncertain transport",
                    "preflight_sha256": check["capture_sha256"], "confirm_idle": True, "confirm_no_draft": True,
                }
                os.environ["CONTROLLER_GUARD_FAULT"] = "message-lost"
                typed = checked_send(base, TmuxBridge(str(wrapper)), store)
                self.assertEqual(typed["status"], "TYPED")
                os.environ.pop("CONTROLLER_GUARD_FAULT", None)
                recovered = checked_send(base, real_bridge, store)
                self.assertEqual(recovered["status"], "SUBMITTED")
                recovery_capture = real_bridge.read(target)
                self.assertEqual(recovery_capture.count("RECEIVED "), 1)

                check = preflight(target, real_bridge)
                lost = {**base, "event_id": "lost-enter", "text": "fixture lost enter response",
                        "preflight_sha256": check["capture_sha256"]}
                os.environ["CONTROLLER_GUARD_FAULT"] = "enter-lost"
                uncertain = checked_send(lost, TmuxBridge(str(wrapper)), store)
                self.assertEqual(uncertain["status"], "UNCONFIRMED")
                os.environ.pop("CONTROLLER_GUARD_FAULT", None)
                calls_before = real_bridge.read(target).count("RECEIVED ")
                duplicate = checked_send(lost, real_bridge, store)
                self.assertEqual(duplicate["status"], "UNCONFIRMED")
                self.assertEqual(real_bridge.read(target).count("RECEIVED "), calls_before)

                check = preflight(target, real_bridge)
                missed = {**base, "event_id": "missed-enter", "text": "fixture physically missed enter",
                          "preflight_sha256": check["capture_sha256"]}
                os.environ["CONTROLLER_GUARD_FAULT"] = "enter-missed"
                missed_result = checked_send(missed, TmuxBridge(str(wrapper)), store)
                self.assertEqual(missed_result["status"], "UNCONFIRMED")
                os.environ.pop("CONTROLLER_GUARD_FAULT", None)
                capture_before_duplicate = real_bridge.read(target)
                self.assertTrue(capture_before_duplicate.rstrip().endswith(missed["text"]))
                self.assertNotIn("RECEIVED fixture physically missed enter", capture_before_duplicate)
                self.assertEqual(checked_send(missed, real_bridge, store)["status"], "UNCONFIRMED")
                self.assertEqual(real_bridge.read(target), capture_before_duplicate)

                check = preflight(ambiguous_target, real_bridge)
                ambiguous = {**base, "event_id": "ambiguous-post-read", "destination": ambiguous_target,
                             "destination_id": ambiguous_target, "destination_name": ambiguous_target,
                             "text": "fixture ambiguous submission", "preflight_sha256": check["capture_sha256"]}
                result = checked_send(ambiguous, real_bridge, store)
                self.assertEqual(result["status"], "UNCONFIRMED")
                self.assertEqual(checked_send(ambiguous, real_bridge, store)["status"], "UNCONFIRMED")
        finally:
            os.environ.pop("CONTROLLER_GUARD_FAULT", None)
            if old_pane is None:
                os.environ.pop("TMUX_PANE", None)
            else:
                os.environ["TMUX_PANE"] = old_pane
            subprocess.run([tmux, "kill-session", "-t", session], check=False)


if __name__ == "__main__":
    unittest.main()
