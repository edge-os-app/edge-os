# Controller delivery and Stop guards

These helpers keep pane delivery and session stopping tied to one explicit session. They use Python's standard library and the installed tmux-bridge. They do not call a model.

## Checked send

Use preflight first. It reads the destination pane through tmux-bridge and prints the sender pane, destination pane ID, capture hash, and capture. The capture can contain private text. Inspect it locally. Do not save or forward it.

~~~sh
python3 scripts/controller_guard.py preflight edge-os-worker-lane-1
~~~

Only continue when the capture shows the expected idle Codex or Claude input with no draft or active task. Copy its sender, destination_id, and capture_sha256 into one send request. Set both confirm_idle and confirm_no_draft to true only after inspection. The helper reads the pane again and requires the hash to match before it types.

~~~json
{
  "task_id": "P01",
  "event_id": "dispatch-2026-10-07-01",
  "candidate": "0123456789abcdef",
  "sender": "%1",
  "destination": "%2",
  "destination_name": "edge-os-worker-lane-1",
  "destination_id": "%2",
  "text": "Implement the accepted task. Reply to pane %1.",
  "preflight_sha256": "<capture_sha256 from preflight>",
  "confirm_idle": true,
  "confirm_no_draft": true
}
~~~

Pass that object on standard input to python3 scripts/controller_guard.py send. The helper verifies the active sender pane and destination identity. It types one normal Smux message, checks the exact active input, sends one Enter, and reads once after Enter. A fixed 0.18-second settle delay is the only wait.

The durable record key is (task_id, event_id, candidate, sender pane, destination pane). The record stores the delivery status, capture hashes, and a SHA-256 message fingerprint. It never stores the message body or captured pane text. A repeated event cannot send again. TYPED can resume only if the same exact message is still the active draft. The helper writes UNCONFIRMED before it attempts Enter. If Enter may have been sent, do not retry that event.

The helper requires operator preflight confirmation because terminal captures do not identify an idle Codex or Claude prompt with enough certainty across versions. If the capture is unknown, partial, busy, or contains any draft, do not confirm it. This is not unattended sending.

## Stop guard binding

The hook does nothing for a session with no binding. Register each session explicitly. The binding must include the host, provider session ID, derived agent ID, actual sender pane ID, exact working directory, lifecycle status, required report paths, and approved work. The helper gets pane_id from tmux-bridge id when omitted. Codex can use CODEX_SESSION_ID when session_id is omitted. Claude requires the session ID in the input object. cwd defaults to the current directory, but pass it explicitly when the session uses another checkout.

~~~json
{
  "host": "codex",
  "session_id": "session-id",
  "cwd": "/path/to/project",
  "status": "ACTIVE",
  "required_reports": ["reports/dispatch.md"],
  "approved_work": [{"id": "P01", "status": "pending"}]
}
~~~

Register with python3 scripts/controller_guard.py bind codex and the object on standard input. Use update to revise obligations or status. Updates cannot change the bound session or working directory. The helper derives agent_id as codex:<session_id> or claude:<session_id>.

State lives in CONTROLLER_GUARD_STATE_ROOT when set. Otherwise, it lives under the user's XDG state directory, isolated by the script's project path. The binding file is bindings.json; delivery state is in delivery.sqlite3. A private workspace can set CONTROLLER_GUARD_STATE_ROOT in its local hook command. Pass the same value to bind and send with the environment or the --state-root option. The environment override is a trusted local configuration value. The hook never uses a path from event JSON to select state.

The following explicit statuses allow Stop, even when obligations remain: AWAITING_EVENT, BLOCKED, BUDGET_EXHAUSTED, APPROVAL_REQUIRED, INTERRUPTED, RUN_LIMIT, and COMPLETE. Other statuses can block once for a durable reason identity. stop_hook_active always allows the continuation call. The guard can block a missing required report, an unfinished delivery, or approved work with status eligible, pending, or in_progress.

An empty obligation list means that this binding has no tracked obligation. It does not prove that a review or task is complete. Do not register an empty list as a completion record. Missing bindings allow Stop by design. A malformed binding file blocks once with a repair instruction. A mismatched session, agent, or cwd also blocks once. Reason identities are hashes, limited to the most recent 64 per session.

The hook does not call a model itself, press Enter, inspect or poll panes, create a batch, extend a budget, or approve a merge or financial action. A block asks the host to continue once with the reason.

## Hook setup and limits

The committed Codex template resolves the script from the Git root. Codex runs the command in the session cwd. The Claude template uses CLAUDE_PROJECT_DIR. The templates do not bypass project trust or Codex hook trust. The user must trust the project and the exact hook through the host's normal controls.

For a private workspace whose session cwd is outside the application repository, configure a local hook command to point at the preserved tooling worktree and set CONTROLLER_GUARD_STATE_ROOT to the private workspace's local state directory. Pass that same root to bind and send. Do not add that machine-specific path to committed configuration. No global hook or restart is needed.

Current references:

- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)

Directly invoking the helper does not prove that the host loaded or trusted a hook. Confirm the hook in the host's own hook UI or trusted configuration. The fixture tests exercise tmux-bridge in an isolated non-agent tmux session. They do not prove behavior in a live Codex or Claude TUI.
