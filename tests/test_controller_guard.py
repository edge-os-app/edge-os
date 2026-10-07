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

from scripts.controller_guard import (
    GuardStore, TmuxBridge, _has_active_draft, _has_partial_input, _submitted,
    checked_send, main, preflight, stop_decision,
)


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
        envelope = (
            f"[tmux-bridge from:codex pane:{self.sender} at:work:0.0 — "
            f"load the smux skill to reply] {text}"
        )
        lines = self.capture.splitlines()
        if lines and lines[-1].strip() in {"❯", "›"}:
            lines[-1] = f"{lines[-1].strip()} {envelope}"
            self.capture = "\n".join(lines)
        else:
            self.capture += "\n" + envelope

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
        self.assertEqual(len(settles), 2)
        names = [call[0] for call in self.bridge.calls]
        self.assertEqual(names.count("message"), 1)
        self.assertEqual(names.count("enter"), 1)
        self.assertEqual(names.count("read"), 3)
        self.assertLess(names.index("read"), names.index("message"))
        self.assertLess(names.index("message"), names.index("enter"))
        self.assertLess(names.index("enter"), len(names) - 1 - names[::-1].index("read"))
        self.assertNotIn(self.request["text"].encode(), self.store.path.read_bytes())

    def test_native_empty_placeholder_and_footer_are_idle(self):
        capture = (
            "› Ask Codex to do anything\n"
            "────────────────────────────────────────────────────────────\n"
            "GPT-6.1-Sol high · ~/repo · lane-3 · Main [default]\n"
            "← for agents · ? for shortcuts                       ⚠ 1 warning · f2 to view"
        )
        self.assertFalse(_has_partial_input(capture))
        self.assertFalse(_has_partial_input(
            '❯ Try "edit <filepath> to..."\n'
            "────────────────────────────────────────────────────────────\n"
            "🤖 Sonnet 5.5 (medium) | 💰 $0.00 session / $0.00 today\n"
            "[OMC#4.15.0L] -> 4.15.7 omc update | session:0m\n"
            "⏸ manual mode on · ← for agents"
        ))
        self.assertFalse(_has_partial_input("❯ Try …\n? for shortcuts"))

    def test_observed_claude_fix_lint_placeholder_is_idle_but_added_text_is_partial(self):
        footer = (
            "────────────────────────────────────────────────────────────\n"
            "🤖 Sonnet 5.5 (medium) | 💰 $0.00 session / $0.00 today\n"
            "[OMC#4.15.0L] -> 4.15.7 omc update | session:0m\n"
            "⏸ manual mode on · ← for agents"
        )
        empty = '❯ Try "fix lint errors"\n' + footer
        foreign = '❯ Try "fix lint errors" plus unsent user text\n' + footer
        self.assertFalse(_has_partial_input(empty))
        self.assertTrue(_has_partial_input(foreign))

    def test_native_own_draft_is_found_before_footer(self):
        own = ("[tmux-bridge from:codex pane:%1 at:work:0.0 — "
               "load the smux skill to reply] " + self.request["text"])
        capture = (
            "› " + own + "\n"
            "GPT-6.1-Sol high · ~/repo · lane-3 · Main [default]\n"
            "← for agents · ? for shortcuts\n"
            "+ Show details"
        )
        self.assertTrue(_has_active_draft(capture, "%1", self.request["text"]))

    def test_claude_native_own_draft_is_found_before_footer(self):
        own = ("[tmux-bridge from:codex pane:%1 at:work:0.0 — "
               "load the smux skill to reply] " + self.request["text"])
        capture = (
            "❯ " + own + "\n"
            "────────────────────────────────────────────────────────────\n"
            "🤖 Sonnet 5.5 (medium) | 💰 $0.00 session / $0.00 today\n"
            "[OMC#4.15.0L] -> 4.15.7 omc update | session:0m\n"
            "⏸ manual mode on · ← for agents"
        )
        self.assertTrue(_has_active_draft(capture, "%1", self.request["text"]))

    def test_claude_native_manual_mode_footer_without_hint_preserves_own_draft(self):
        text = "Reply only ACK-20261007-r13. Do not run tools."
        own_header = (
            "[tmux-bridge from:claude pane:%9 at:work:0.1 — "
            "load the smux skill to reply] "
        )
        capture = (
            "❯ " + own_header + "\n"
            "  " + text + "\n"
            "────────────────────────────────────────────────────────────\n"
            "  🤖 Sonnet 5.5 (medium) | 💰 $0.00 session / $0.00 today | "
            "$0.00 block (4h 18m left) | $0.00/hr | 0 (0%)\n"
            "  [OMC#4.15.0L] -> 4.15.7 omc update | 5h:39%(4h38m) "
            "wk:26%(6d10h) extra:0%($0.00/$30.00) | session:0m\n"
            "  ⏸ manual mode on"
        )
        self.assertTrue(_has_active_draft(capture, "%9", text))

    def test_claude_native_split_plugin_quota_footer_and_foreign_input(self):
        text = "Reply only ACK-r14-footer. Do not run tools."
        own_header = (
            "[tmux-bridge from:claude pane:%9 at:work:0.1 — "
            "load the smux skill to reply] "
        )
        separator = "────────────────────────────────────────────────────────────\n"
        update = "  [OMC#4.15.0L] -> 4.15.7 omc update\n"
        quota = "  5h:0%* wk:19%*(~6d10h) extra:0%*($0.00/$30.00) | session:191m\n"
        footer = (
            separator +
            "  🤖 Sonnet 5.5 (medium) | 💰 $0.19 session / $0.00 today / "
            "No active block | 🧠 49,514 (5%)\n" +
            update + quota +
            "  ⏸ manual mode on · ← for agents"
        )
        idle = "❯\n" + footer
        own = "❯ " + own_header + "\n  " + text + "\n" + footer
        foreign = own.replace("\n" + separator, "\n  foreign unsent addition\n" + separator)
        self.assertFalse(_has_partial_input(idle))
        self.assertTrue(_has_active_draft(own, "%9", text))
        self.assertFalse(_has_active_draft(foreign, "%9", text))
        self.assertTrue(_has_partial_input(foreign))
        self.assertTrue(_has_partial_input(idle.replace(quota, quota.rstrip() + " extra\n")))
        self.assertTrue(_has_partial_input(idle.replace(update, update.rstrip() + " extra\n")))

    def test_native_foreign_draft_with_footer_stays_partial(self):
        capture = (
            "❯ [tmux-bridge from:other pane:%9 at:work:0.1 — load the smux skill to reply] foreign text\n"
            "────────────────────────────────────────────────────────────\n"
            "🤖 Sonnet 5.5 (medium) | 💰 $0.00 session / $0.00 today\n"
            "[OMC#4.15.0L] -> 4.15.7 omc update | session:0m\n"
            "⏸ manual mode on · ← for agents"
        )
        self.assertTrue(_has_partial_input(capture))
        self.assertFalse(_has_active_draft(capture, "%1", self.request["text"]))

    def test_native_wrapped_own_draft_is_found_but_collapsed_input_is_not_adopted(self):
        own = ("[tmux-bridge from:codex pane:%1 at:work:0.0 — "
               "load the smux skill to reply] " + self.request["text"])
        header, body = own.split(" review ", 1)
        wrapped = (
            "› " + header + " review\n" + body + "\n"
            "GPT-6.1-Sol high · ~/repo · lane-3 · Main [default]\n"
            "← for agents · ? for shortcuts\n"
            "+ Show details"
        )
        collapsed = "› [pasted text 73 chars]\n" + wrapped.split("\n", 1)[1]
        self.assertTrue(_has_active_draft(wrapped, "%1", self.request["text"]))
        self.assertFalse(_has_active_draft(collapsed, "%1", self.request["text"]))
        self.assertTrue(_has_partial_input(collapsed))

    def test_native_word_wrapped_own_draft_is_reconstructed_without_added_space(self):
        own = ("[tmux-bridge from:codex pane:%1 at:work:0.0 — "
               "load the smux skill to reply] " + self.request["text"])
        offset = own.index("candidate") + len("candi")
        wrapped = "› " + own[:offset] + "\n" + own[offset:] + "\n+ Show details"
        self.assertTrue(_has_active_draft(wrapped, "%1", self.request["text"]))

    def test_native_claude_pointer_capture_reconstructs_mixed_word_wraps(self):
        text = (
            "Packet CTRL-BIND-L3-01/NATIVE-CLAUDE-DELIVERY/9: "
            "/private/tmp/edge-os-controller-bind.PQBi6Z/project/.scratch/"
            "controller-guard-binding/packets/claude-delivery-round9-2026-10-07.md "
            "SHA256 889940979590fb33f66301736cd3e23d220e857e583dea06b1460e2c76fb8940"
        )
        own_header = (
            "[tmux-bridge from:edge-os-worker-lane-3 pane:%5 at:edge-os-lane-3:0.1 — "
            "load the smux skill to reply] "
        )
        capture = (
            "❯ " + own_header + "Packet\n"
            "  CTRL-BIND-L3-01/NATIVE-CLAUDE-DELIVERY/9: /private/tmp/edge-os-controller-bind.PQBi6Z/project/.scratch/controller-gu\n"
            "  ard-binding/packets/claude-delivery-round9-2026-10-07.md SHA256\n"
            "  889940979590fb33f66301736cd3e23d220e857e583dea06b1460e2c76fb8940\n"
            "────────────────────────────────────────────────────────────\n"
            "🤖 Sonnet 5.5 (medium) | 💰 $0.00 session / $0.00 today\n"
            "[OMC#4.15.0L] -> 4.15.7 omc update | session:0m\n"
            "⏸ manual mode on · ← for agents"
        )
        self.assertTrue(_has_active_draft(capture, "%5", text))

    def test_native_submitted_message_and_empty_placeholder_with_footer_confirm(self):
        own = ("[tmux-bridge from:codex pane:%1 at:work:0.0 — "
               "load the smux skill to reply] " + self.request["text"])
        footer = (
            "GPT-6.1-Sol high · ~/repo · lane-3 · Main [default]\n"
            "← for agents · ? for shortcuts\n"
            "+ Show details"
        )
        before = (
            "prior history\n› " + own + "\n"
            "────────────────────────────────────────────────────────────\n" + footer
        )
        after = (
            "prior history\n" + own + "\n"
            "› Ask Codex to do anything\n"
            "────────────────────────────────────────────────────────────\n" + footer
        )
        self.assertTrue(_submitted(after, before, "%1", self.request["text"]))

    def test_native_submission_allows_receiver_output_after_exact_message(self):
        own = ("[tmux-bridge from:codex pane:%1 at:work:0.0 — "
               "load the smux skill to reply] " + self.request["text"])
        before = "❯ " + own
        after = before + "\nRECEIVED " + own + "\n❯ "
        self.assertTrue(_submitted(after, before, "%1", self.request["text"]))
        self.assertFalse(_submitted(after, "❯ unrelated draft", "%1", self.request["text"]))

    def test_native_submission_survives_viewport_padding_shift_but_requires_new_message(self):
        header = "[tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] "
        earlier = header + "Reply only ACK-old-event. Do not run tools."
        fresh = header + "Reply only ACK-current-event. Do not run tools."
        history = [
            ">_ OpenAI Codex (v0.160.1)",
            "permissions: YOLO mode",
            earlier,
            "• ACK-old-event",
            earlier,
            "• ACK-old-event",
        ]
        before = "\n".join(history + ([""] * 8) + ["› " + fresh])
        after = "\n".join(
            history + [fresh, "• Working (0s • esc to interrupt)", "› Ask Codex to do anything"]
        )
        old_history_only = "\n".join(history + ([""] * 8) + ["› Ask Codex to do anything"])
        self.assertTrue(_submitted(after, before, "%1", "Reply only ACK-current-event. Do not run tools."))
        self.assertFalse(_submitted(old_history_only, before, "%1", "Reply only ACK-current-event. Do not run tools."))

    def test_claude_submission_ignores_only_adjacent_update_chrome(self):
        text = "Reply only ACK-current-event. Do not run tools."
        header = "[tmux-bridge from:claude pane:%9 at:work:0.1 — load the smux skill to reply] "
        update_text = "✔ Update installed · Restart to update"
        notice = " " * (120 - len(update_text)) + update_text
        separator = "─" * 120
        history = [
            "Claude Code v2.1.292",
            "Sonnet 5.5 with medium effort · Claude Pro",
            "/repo · /rc",
            update_text,
            "❯ /clear",
            "❯ Reply exactly READY; make no tool calls.",
            "⏺ READY",
            "✻ Worked for 2s · done",
            "❯ Reply exactly READY; make no tool calls.",
            "⏺ READY",
            "✻ Cooked for 2s · done",
        ]
        footer = (
            separator + "\n"
            "🤖 Sonnet 5.5 (medium) | 💰 $0.19 session / $0.00 today / "
            "No active block | 🧠 49,514 (5%)\n"
            "[OMC#4.15.0L] -> 4.15.7 omc update\n"
            "5h:0%* wk:19%*(~6d10h) extra:0%*($0.00/$30.00) | session:191m\n"
            "⏸ manual mode on · ← for agents"
        )
        own = "❯ " + header + "\n  " + text
        before = "\n".join(history + ["", notice, separator, own, footer])
        after = "\n".join(history + [
            header,
            "  " + text,
            "  ⎿ 1 skill available",
            "✶ Working (0s)",
            "  ⎿ Tip: continue",
            notice,
            separator,
            "❯ ",
            footer,
        ])
        old_identical_history_only = "\n".join(
            history + [notice, separator, "❯ ", footer]
        )
        changed_update = before.replace(notice, notice + " (user text)", 1)
        changed_separator = before.replace(separator + "\n" + own,
                                           "─" * 119 + "x\n" + own, 1)
        self.assertTrue(_submitted(after, before, "%9", text))
        self.assertFalse(_submitted(old_identical_history_only, before, "%9", text))
        self.assertFalse(_submitted(after, changed_update, "%9", text))
        self.assertFalse(_submitted(after, changed_separator, "%9", text))

    def test_active_draft_rejects_suffix_after_exact_message(self):
        own = ("[tmux-bridge from:codex pane:%1 at:work:0.0 — "
               "load the smux skill to reply] fixture text")
        capture = "❯ " + own + "\nforeign unsent addition"
        self.assertFalse(_has_active_draft(capture, "%1", "fixture text"))

    def test_checked_send_uses_350ms_settles(self):
        with patch("scripts.controller_guard.time.sleep") as sleep:
            result = checked_send(self.request, self.bridge, self.store)
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual([call.args for call in sleep.call_args_list], [(0.35,), (0.35,)])

    def test_delayed_display_gets_one_safe_recovery_read_before_enter(self):
        class DelayedDisplay(FakeBridge):
            def message(inner, target, text):
                super(DelayedDisplay, inner).message(target, text)
                inner.stale_once = True

            def read(inner, target):
                inner.calls.append(("read", target))
                inner._raise("read")
                if getattr(inner, "stale_once", False):
                    inner.stale_once = False
                    return "❯ "
                return inner.capture

        self.bridge = DelayedDisplay()
        settles = []
        result = checked_send(self.request, self.bridge, self.store,
                              settle=lambda: settles.append(True))
        self.assertEqual(result["status"], "SUBMITTED")
        names = [call[0] for call in self.bridge.calls]
        self.assertEqual(names.count("message"), 1)
        self.assertEqual(names.count("enter"), 1)
        self.assertEqual(names.count("read"), 4)
        self.assertEqual(len(settles), 3)
        self.assertLess(names.index("message"), names.index("enter"))

    def test_duplicate_event_never_sends_twice(self):
        self.send()
        self.bridge.calls.clear()
        result = self.send()
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(self.bridge.calls, [])

    def test_fork_cannot_resend_event_recorded_by_parent_session(self):
        record = {
            **self.request,
            "session_id": "parent-session",
            "agent_id": "codex:parent-session",
            "status": "SUBMITTED",
        }
        self.store.put_record(record)
        result = checked_send(self.request, self.bridge, self.store, settle=lambda: None,
                              inherited_session_ids=["parent-session"])
        self.assertEqual(result, {"status": "SUBMITTED", "duplicate": True})
        self.assertEqual(self.bridge.calls, [])
        self.assertIsNone(self.store.get_record(("codex", "s1", "codex:s1", "T-1", "dispatch-1",
                                                 "abc123", "%1", "%2")))

    def test_different_pane_fork_cannot_resend_parent_terminal_event(self):
        for status in ("SUBMITTED", "UNCONFIRMED"):
            with self.subTest(status=status):
                parent = {
                    **self.request,
                    "session_id": "parent-session",
                    "agent_id": "codex:parent-session",
                    "sender": "%5",
                    "status": status,
                }
                self.store.put_record(parent)
                request = {**self.request, "sender": "%6"}
                bridge = FakeBridge(sender="%6")
                result = checked_send(request, bridge, self.store, settle=lambda: None,
                                      inherited_session_ids=["parent-session"])
                self.assertEqual(result, {"status": status, "duplicate": True})
                self.assertFalse(any(call[0] in {"message", "enter"} for call in bridge.calls))

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

    def test_historical_match_cannot_confirm_missing_or_changed_current_submission(self):
        header = "[tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] "
        history = header + self.request["text"] + "\n❯ "
        for current in ("", header + "unrelated draft ] " + self.request["text"] + "\n"):
            with self.subTest(current=current):
                self.request["event_id"] = "history-" + str(bool(current))
                self.request["preflight_sha256"] = hashlib.sha256(history.encode()).hexdigest()

                class ChangedCurrent(FakeBridge):
                    def enter(inner, target):
                        inner.calls.append(("enter", target))
                        inner.capture = history + "\n" + current + "❯ "

                self.bridge = ChangedCurrent(capture=history)
                self.assertEqual(self.send()["status"], "UNCONFIRMED")
                self.bridge.calls.clear()
                self.assertEqual(self.send()["status"], "UNCONFIRMED")
                self.assertEqual(self.bridge.calls, [])

    def test_current_exact_submission_is_confirmed_despite_identical_history(self):
        header = "[tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] "
        self.bridge.capture = header + self.request["text"] + "\n❯ "
        self.request["preflight_sha256"] = hashlib.sha256(self.bridge.capture.encode()).hexdigest()
        self.assertEqual(self.send()["status"], "SUBMITTED")

    def test_unidentifiable_history_change_remains_unconfirmed(self):
        header = "[tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] "

        class ReflowedHistory(FakeBridge):
            def enter(inner, target):
                inner.calls.append(("enter", target))
                inner.capture = header + self.request["text"] + "\n❯ "

        self.bridge = ReflowedHistory(capture="old context\n❯ ")
        self.request["preflight_sha256"] = hashlib.sha256(self.bridge.capture.encode()).hexdigest()
        self.assertEqual(self.send()["status"], "UNCONFIRMED")

    def test_same_event_recovery_confirms_current_submission_with_history(self):
        class TypedThenLost(FakeBridge):
            def message(inner, target, text):
                FakeBridge.message(inner, target, text)
                raise RuntimeError("response lost after type")

        header = "[tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] "
        self.bridge = TypedThenLost(capture=header + self.request["text"] + "\n❯ ")
        self.request["preflight_sha256"] = hashlib.sha256(self.bridge.capture.encode()).hexdigest()
        self.assertEqual(self.send()["status"], "TYPED")
        self.bridge.calls.clear()
        self.assertEqual(self.send()["status"], "SUBMITTED")
        self.assertFalse(any(call[0] == "message" for call in self.bridge.calls))

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

    def test_historical_false_confirmation_keeps_completed_task_delivery_obligation(self):
        header = "[tmux-bridge from:codex pane:%1 at:work:0.0 — load the smux skill to reply] "
        script = str(Path(__file__).resolve().parents[1] / "scripts/controller_guard.py")
        for host in ("codex", "claude"):
            for changed in (False, True):
                with self.subTest(host=host, changed=changed):
                    cli_root = self.root / f"{host}-history-{changed}"
                    text = "return complete report"
                    history = header + text + "\n❯ "

                    class ChangedCurrent(FakeBridge):
                        def enter(inner, target):
                            inner.calls.append(("enter", target))
                            inner.capture = history + "\n" + (header + "foreign " + text + "\n" if changed else "") + "❯ "

                    request = {
                        "host": host, "session_id": "s1", "agent_id": host + ":s1",
                        "task_id": "T-1", "event_id": "return", "candidate": "abc123",
                        "sender": "%1", "destination": "%2", "destination_id": "%2",
                        "text": text, "preflight_sha256": hashlib.sha256(history.encode()).hexdigest(),
                        "confirm_idle": True, "confirm_no_draft": True,
                    }
                    store = GuardStore(cli_root / "delivery.sqlite3")
                    self.assertEqual(checked_send(request, ChangedCurrent(capture=history), store,
                                                  settle=lambda: None)["status"], "UNCONFIRMED")
                    binding = {**self.binding, "host": host, "agent_id": host + ":s1",
                               "approved_work": [{"id": "T-1", "status": "complete"}]}
                    (cli_root / "bindings.json").write_text(json.dumps({"version": 1, "bindings": [binding]}))
                    output = subprocess.run([sys.executable, script, "--state-root", str(cli_root), "hook", host],
                                            input=json.dumps(self.payload), text=True, capture_output=True, check=False)
                    self.assertEqual(output.returncode, 0, output.stderr)
                    self.assertIn("unfinished-delivery", json.loads(output.stdout).get("reason", ""))

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


class SessionStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_root = self.root / "state"
        self.assignment = {
            "approved": True,
            "assignment_id": "dispatch-1",
            "host": "codex",
            "role": "worker",
            "task_id": "T-1",
            "pane_id": "%5",
            "cwd": str(self.root),
            "required_reports": ["RESULT.md"],
            "approved_work": [{"id": "T-1", "status": "in_progress"}],
        }
        self.event = {
            "hook_event_name": "SessionStart",
            "session_id": "s1",
            "cwd": str(self.root),
            "source": "clear",
            "transcript_path": "/private/transcript.jsonl",
        }

    def run_cli(self, command, host="codex", payload=None, pane="%5", now=None):
        output = io.StringIO()
        patches = [patch("sys.stdin", io.StringIO(json.dumps(payload or {}))),
                   contextlib.redirect_stdout(output)]
        if command == "session-start":
            patches.append(patch("scripts.controller_guard.TmuxBridge.id", return_value=pane))
        if now is not None:
            patches.append(patch("scripts.controller_guard.time.time", return_value=now))
        with contextlib.ExitStack() as stack:
            for context in patches:
                stack.enter_context(context)
            result = main(["--state-root", str(self.state_root), command, host])
        return result, json.loads(output.getvalue()) if output.getvalue() else {}

    def assign(self, assignment=None, now=1000, host="codex"):
        return self.run_cli("assign", host=host, payload=assignment or self.assignment, now=now)

    def start(self, event=None, host="codex", pane="%5", now=1001):
        return self.run_cli("session-start", host=host, payload=event or self.event, pane=pane, now=now)

    def state(self):
        return json.loads((self.state_root / "bindings.json").read_text())

    def receipt(self, host="codex", session_id="s1", assignment_id="dispatch-1"):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--state-root", str(self.state_root), "receipt", host, session_id, assignment_id])
        return code, json.loads(output.getvalue())

    def test_approved_assignment_registers_native_identity_and_matching_receipt(self):
        self.assertEqual(self.assign()[0], 0)
        code, receipt = self.start()
        self.assertEqual(code, 0)
        self.assertIn("hookSpecificOutput", receipt)
        code, receipt = self.receipt()
        self.assertEqual(code, 0)
        self.assertEqual((receipt["host"], receipt["session_id"], receipt["agent_id"]),
                         ("codex", "s1", "codex:s1"))
        self.assertEqual((receipt["pane_id"], receipt["task_id"], receipt["assignment_id"]),
                         ("%5", "T-1", "dispatch-1"))
        self.assertEqual(len(receipt["assignment_sha256"]), 64)
        self.assertNotIn("transcript", json.dumps(receipt))
        self.assertEqual(self.state()["bindings"][0]["status"], "ACTIVE")
        self.assertEqual(self.state()["receipts"][0], receipt)
        self.assertNotIn("transcript_path", json.dumps(self.state()))

    def test_receipt_verification_rejects_identity_or_fingerprint_tampering(self):
        self.assign()
        self.start()
        state_path = self.state_root / "bindings.json"
        original = self.state()
        for field, value in (("role", "gate"), ("assignment_sha256", "0" * 64)):
            with self.subTest(field=field):
                state = json.loads(json.dumps(original))
                state["receipts"][0][field] = value
                state_path.write_text(json.dumps(state))
                code, result = self.receipt()
                self.assertEqual(code, 1)
                self.assertEqual(result, {"registered": False})
        state_path.write_text(json.dumps(original))

    def test_claude_session_start_uses_native_session_identity(self):
        self.assign({**self.assignment, "host": "claude"}, host="claude")
        event = {**self.event, "session_id": "claude-session"}
        code, output = self.start(event, host="claude")
        self.assertEqual(code, 0)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        code, receipt = self.receipt(host="claude", session_id="claude-session")
        self.assertEqual(code, 0)
        self.assertEqual((receipt["host"], receipt["session_id"], receipt["task_id"]),
                         ("claude", "claude-session", "T-1"))

    def test_missing_foreign_and_malformed_assignments_do_not_enroll(self):
        self.assertEqual(self.start()[1], {})
        self.assign()
        foreign_cwd = {**self.event, "cwd": str(self.root / "foreign")}
        self.assertEqual(self.start(foreign_cwd)[1], {})
        self.assertEqual(self.start(pane="%9")[1], {})
        self.assertEqual(self.start(host="claude")[1], {})
        self.assertEqual(self.state()["bindings"], [])
        self.assertEqual(self.assign({**self.assignment, "approved": False})[0], 2)
        self.assertEqual(self.assign({**self.assignment, "task_id": "T-2"})[0], 2)

    def test_assignment_with_foreign_task_obligation_is_rejected(self):
        mixed = {
            **self.assignment,
            "approved_work": [
                {"id": "T-1", "status": "complete"},
                {"id": "T-old", "status": "pending"},
            ],
        }
        self.assertEqual(self.assign(mixed)[0], 2)
        self.assertEqual(self.start()[1], {})
        self.assertFalse((self.state_root / "bindings.json").exists())

    def test_stale_assignment_cannot_register(self):
        self.assign(now=1000)
        self.assertEqual(self.start(now=1901)[1], {})
        self.assertEqual(self.state()["bindings"], [])
        self.assign({**self.assignment, "assignment_id": "dispatch-fresh"}, now=1902)
        self.assertTrue(self.start(now=1903)[1])

    def test_future_assignment_timestamp_cannot_register(self):
        self.assign(now=1000)
        state_path = self.state_root / "bindings.json"
        state = self.state()
        state["assignment"]["issued_at"] = 1002
        state_path.write_text(json.dumps(state))
        self.assertEqual(self.start(now=1001)[1], {})
        self.assertEqual(self.state()["bindings"], [])

    def test_duplicate_start_and_resume_preserve_same_ticket_state(self):
        self.assign()
        self.start()
        _, original = self.receipt()
        state = self.state()
        state["bindings"][0]["status"] = "BLOCKED"
        state["bindings"][0]["approved_work"][0]["status"] = "complete"
        state["bindings"][0]["review_history"] = ["A:REVISE", "B:PASS"]
        state["bindings"][0]["gate_verdicts"] = 2
        (self.state_root / "bindings.json").write_text(json.dumps(state))
        self.start()
        _, duplicate = self.receipt()
        self.assertEqual(duplicate, original)
        for source in ("resume", "compact", "fork"):
            with self.subTest(source=source):
                self.start({**self.event, "source": source})
                _, receipt = self.receipt()
                self.assertEqual(receipt, original)
        after = self.state()
        self.assertEqual(len(after["bindings"]), 1)
        self.assertEqual(after["bindings"][0]["status"], "BLOCKED")
        self.assertEqual(after["bindings"][0]["review_history"], ["A:REVISE", "B:PASS"])
        self.assertEqual(after["bindings"][0]["gate_verdicts"], 2)
        self.assertEqual(len(after["receipts"]), 1)

    def test_fork_with_approved_parent_preserves_task_binding_state(self):
        self.assign()
        self.start()
        state = self.state()
        parent = state["bindings"][0]
        parent.update({"status": "BLOCKED", "review_history": ["A:REVISE"], "gate_verdicts": 2})
        (self.state_root / "bindings.json").write_text(json.dumps(state))
        assignment = {
            **self.assignment,
            "assignment_id": "fork-1",
            "pane_id": "%6",
            "fork_parent_session_id": "s1",
        }
        self.assertEqual(self.assign(assignment, now=1002)[0], 0)
        event = {**self.event, "session_id": "fork-s1", "source": "fork"}
        self.assertTrue(self.start(event, pane="%6", now=1003)[1])
        _, parent_receipt = self.receipt()
        _, child_receipt = self.receipt(session_id="fork-s1", assignment_id="fork-1")
        self.assertEqual(child_receipt["source"], "fork")
        self.assertEqual(child_receipt["task_id"], parent_receipt["task_id"])
        self.assertEqual(child_receipt["pane_id"], "%6")
        state = self.state()
        self.assertEqual(len(state["bindings"]), 2)
        child = next(binding for binding in state["bindings"] if binding["session_id"] == "fork-s1")
        self.assertEqual(child["status"], "BLOCKED")
        self.assertEqual(child["required_reports"], ["RESULT.md"])
        self.assertEqual(child["approved_work"], [{"id": "T-1", "status": "in_progress"}])
        self.assertEqual(child["review_history"], ["A:REVISE"])
        self.assertEqual(child["gate_verdicts"], 2)
        before_duplicate = json.loads(json.dumps(state))
        self.start(event, now=1004)
        self.assertEqual(self.state(), before_duplicate)

    def test_fork_without_matching_parent_assignment_stays_unbound(self):
        self.assign()
        event = {**self.event, "session_id": "fork-s1", "source": "fork"}
        self.assertEqual(self.start(event)[1], {})
        state = self.state()
        self.assertEqual(state["bindings"], [])
        self.assertEqual(state["receipts"], [])
        self.assertNotIn("consumed_by", state["assignment"])

    def test_fork_rejects_unverified_parent_without_changing_existing_binding(self):
        self.assign()
        self.start()
        before = self.state()
        assignment = {
            **self.assignment,
            "assignment_id": "fork-unverified-parent",
            "fork_parent_session_id": "foreign-session",
        }
        self.assertEqual(self.assign(assignment, now=1002)[0], 0)
        event = {**self.event, "session_id": "fork-s1", "source": "fork"}
        self.assertEqual(self.start(event, now=1003)[1], {})
        after = self.state()
        self.assertEqual(after["bindings"], before["bindings"])
        self.assertEqual(after["receipts"], before["receipts"])
        self.assertNotIn("consumed_by", after["assignment"])

    def test_fork_stop_inherits_open_delivery_without_rewriting_record(self):
        self.assign()
        self.start()
        store = GuardStore(self.state_root / "delivery.sqlite3")
        record = {
            "host": "codex", "session_id": "s1", "agent_id": "codex:s1", "task_id": "T-1",
            "event_id": "missed", "candidate": "c1", "sender": "%5", "destination": "%9",
            "status": "UNCONFIRMED",
        }
        store.put_record(record)
        assignment = {
            **self.assignment,
            "assignment_id": "fork-delivery",
            "fork_parent_session_id": "s1",
        }
        self.assertEqual(self.assign(assignment, now=1002)[0], 0)
        event = {**self.event, "session_id": "fork-delivery-session", "source": "fork"}
        self.assertTrue(self.start(event, now=1003)[1])
        state = self.state()
        child = next(binding for binding in state["bindings"] if binding["session_id"] == "fork-delivery-session")
        self.assertEqual(child["inherited_session_ids"], ["s1"])
        result = stop_decision("codex", {"session_id": "fork-delivery-session", "cwd": str(self.root)},
                               self.state_root / "bindings.json", store)
        self.assertEqual(result["decision"], "block")
        self.assertIn("unfinished-delivery", result["reason"])
        self.assertEqual(store.get_record(("codex", "s1", "codex:s1", "T-1", "missed", "c1", "%5", "%9"))["status"], "UNCONFIRMED")

    def test_send_cli_uses_only_verified_binding_fork_lineage(self):
        self.assign()
        self.start()
        assignment = {
            **self.assignment,
            "assignment_id": "fork-send",
            "fork_parent_session_id": "s1",
        }
        self.assign(assignment, now=1002)
        event = {**self.event, "session_id": "fork-send-session", "source": "fork"}
        self.start(event, now=1003)
        request = {
            "host": "codex", "session_id": "fork-send-session", "agent_id": "codex:fork-send-session",
            "task_id": "T-1", "event_id": "e1", "candidate": "c1", "sender": "%5", "destination": "%9",
            "destination_id": "%9", "text": "message", "preflight_sha256": "a" * 64,
        }
        result = io.StringIO()
        with patch("scripts.controller_guard.checked_send",
                   side_effect=lambda request, bridge, store, inherited_session_ids=None:
                   {"inherited_session_ids": inherited_session_ids}):
            with patch("sys.stdin", io.StringIO(json.dumps(request))), contextlib.redirect_stdout(result):
                self.assertEqual(main(["--state-root", str(self.state_root), "send"]), 0)
        self.assertEqual(json.loads(result.getvalue()), {"inherited_session_ids": ["s1"]})

    def test_update_preserves_receipt_and_review_state(self):
        self.assign()
        self.start()
        _, original_receipt = self.receipt()
        state = self.state()
        state["bindings"][0].update({"status": "BLOCKED", "review_history": ["A:REVISE"], "gate_verdicts": 2})
        (self.state_root / "bindings.json").write_text(json.dumps(state))
        store = GuardStore(self.state_root / "delivery.sqlite3")
        record = {
            "host": "codex", "session_id": "s1", "agent_id": "codex:s1", "task_id": "T-1",
            "event_id": "missed", "candidate": "c1", "sender": "%5", "destination": "%9",
            "status": "UNCONFIRMED",
        }
        store.put_record(record)
        update = {
            "host": "codex", "session_id": "s1", "agent_id": "codex:s1", "pane_id": "%5",
            "cwd": str(self.root.resolve()), "status": "AWAITING_EVENT", "required_reports": ["RESULT.md"],
            "approved_work": [{"id": "T-1", "status": "in_progress"}],
        }
        code, _ = self.run_cli("update", payload=update)
        self.assertEqual(code, 0)
        binding = self.state()["bindings"][0]
        self.assertEqual(binding["role"], "worker")
        self.assertEqual(binding["task_id"], "T-1")
        self.assertEqual(binding["assignment_id"], original_receipt["assignment_id"])
        self.assertEqual(binding["assignment_sha256"], original_receipt["assignment_sha256"])
        self.assertEqual(binding["review_history"], ["A:REVISE"])
        self.assertEqual(binding["gate_verdicts"], 2)
        self.assertEqual(binding["status"], "AWAITING_EVENT")
        self.assertEqual(store.get_record(("codex", "s1", "codex:s1", "T-1", "missed", "c1", "%5", "%9"))["status"], "UNCONFIRMED")
        self.assertEqual(self.receipt()[1], original_receipt)

        tampered = {**update, "task_id": "T-2"}
        self.assertEqual(self.run_cli("update", payload=tampered)[0], 2)
        self.assertEqual(self.receipt()[1], original_receipt)
        reset_history = {**update, "review_history": [], "gate_verdicts": 0}
        self.assertEqual(self.run_cli("update", payload=reset_history)[0], 2)
        cross_task = {**update, "approved_work": [{"id": "T-2", "status": "pending"}]}
        self.assertEqual(self.run_cli("update", payload=cross_task)[0], 2)
        empty_work = {**update, "approved_work": []}
        self.assertEqual(self.run_cli("update", payload=empty_work)[0], 2)
        binding = self.state()["bindings"][0]
        self.assertEqual(binding["review_history"], ["A:REVISE"])
        self.assertEqual(binding["gate_verdicts"], 2)

    def test_cli_update_preserves_omitted_status_reports_and_work(self):
        self.assign({**self.assignment, "role": "gate", "required_reports": ["MISSING.md"]})
        self.start()
        state = self.state()
        state["bindings"][0]["status"] = "BLOCKED"
        previous_work = state["bindings"][0]["approved_work"]
        (self.state_root / "bindings.json").write_text(json.dumps(state))

        update = {
            "host": "codex", "session_id": "s1", "agent_id": "codex:s1",
        }
        code, _ = self.run_cli("update", payload=update)
        self.assertEqual(code, 0)
        binding = self.state()["bindings"][0]
        self.assertEqual(binding["status"], "BLOCKED")
        self.assertEqual(binding["required_reports"], ["MISSING.md"])
        self.assertEqual(binding["approved_work"], previous_work)
        self.assertEqual(binding["pane_id"], "%5")
        self.assertEqual(binding["cwd"], str(self.root.resolve()))

    def test_first_gate_counter_update_is_bounded_and_preserves_receipt(self):
        self.assign({**self.assignment, "role": "gate"})
        self.start()
        original = self.state()["bindings"][0]
        _, original_receipt = self.receipt()
        identity = {"host": "codex", "session_id": "s1", "agent_id": "codex:s1"}

        for count in (4, -1):
            with self.subTest(count=count):
                code, _ = self.run_cli("update", payload={**identity, "gate_verdicts": count})
                self.assertEqual(code, 2)
                self.assertEqual(self.state()["bindings"][0], original)
                self.assertEqual(self.receipt()[1], original_receipt)

    def test_update_rejects_malformed_first_or_appended_review_history(self):
        self.assign()
        self.start()
        original = self.state()["bindings"][0]
        _, original_receipt = self.receipt()
        identity = {"host": "codex", "session_id": "s1", "agent_id": "codex:s1"}

        for history in ({}, ["A:PASS", None]):
            with self.subTest(history=history):
                code, _ = self.run_cli("update", payload={**identity, "review_history": history})
                self.assertEqual(code, 2)
                self.assertEqual(self.state()["bindings"][0], original)
                self.assertEqual(self.receipt()[1], original_receipt)

        self.assertEqual(self.run_cli("update", payload={**identity, "review_history": ["A:PASS"]})[0], 0)
        with_history = self.state()["bindings"][0]
        _, with_history_receipt = self.receipt()
        code, _ = self.run_cli("update", payload={**identity, "review_history": ["A:PASS", None]})
        self.assertEqual(code, 2)
        self.assertEqual(self.state()["bindings"][0], with_history)
        self.assertEqual(self.receipt()[1], with_history_receipt)

    def test_clear_with_new_session_registers_new_task_without_old_obligations(self):
        self.assign()
        self.start()
        self.assertEqual(self.start({**self.event, "session_id": "s2"})[1], {})
        next_assignment = {
            **self.assignment,
            "assignment_id": "dispatch-2",
            "task_id": "T-2",
            "required_reports": ["NEXT.md"],
            "approved_work": [{"id": "T-2", "status": "pending"}],
        }
        self.assign(next_assignment, now=1002)
        next_event = {**self.event, "session_id": "s2"}
        self.start(next_event, now=1003)
        _, receipt = self.receipt(session_id="s2", assignment_id="dispatch-2")
        self.assertEqual(receipt["task_id"], "T-2")
        state = self.state()
        self.assertEqual([binding["approved_work"][0]["id"] for binding in state["bindings"]], ["T-1", "T-2"])
        self.assertEqual(state["bindings"][0]["required_reports"], ["RESULT.md"])
        self.assertEqual(state["bindings"][1]["required_reports"], ["NEXT.md"])

    def test_gate_assignment_starts_in_awaiting_event(self):
        self.assign({**self.assignment, "role": "gate", "approved_work": [{"id": "T-1", "status": "pending"}]})
        self.start()
        self.assertEqual(self.state()["bindings"][0]["status"], "AWAITING_EVENT")
        code, output = self.run_cli("hook", payload=self.event)
        self.assertEqual(code, 0)
        self.assertEqual(output, {})

    def test_session_start_receipt_and_stop_hook_share_state_root(self):
        self.assign()
        self.start()
        hook_payload = {"session_id": "s1", "cwd": str(self.root), "stop_hook_active": False}
        code, output = self.run_cli("hook", payload=hook_payload)
        self.assertEqual(code, 0)
        self.assertEqual(output["decision"], "block")
        other_root = self.root / "other-state"
        neutral = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(hook_payload))), contextlib.redirect_stdout(neutral):
            self.assertEqual(main(["--state-root", str(other_root), "hook", "codex"]), 0)
        self.assertEqual(json.loads(neutral.getvalue()), {})


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
                class StaleFirstRead:
                    def __init__(self):
                        self.reads = self.messages = self.enters = 0
                        self.stale_pending = False
                        self.stale_used = False
                        self.last_capture = None

                    def id(inner):
                        return bridge.id()

                    def resolve(inner, destination):
                        return bridge.resolve(destination)

                    def read(inner, pane):
                        inner.reads += 1
                        capture = bridge.read(pane)
                        if inner.stale_pending and not inner.stale_used:
                            inner.stale_used = True
                            return inner.last_capture
                        if not inner.stale_pending:
                            inner.last_capture = capture
                        return capture

                    def message(inner, pane, text):
                        inner.messages += 1
                        bridge.message(pane, text)
                        inner.stale_pending = True

                    def enter(inner, pane):
                        inner.enters += 1
                        bridge.enter(pane)

                delayed = StaleFirstRead()
                self.assertEqual(checked_send(first, delayed, store)["status"], "SUBMITTED")
                self.assertTrue(delayed.stale_used)
                self.assertEqual((delayed.reads, delayed.messages, delayed.enters), (4, 1, 1))
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
