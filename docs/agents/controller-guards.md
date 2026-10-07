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
  "host": "codex",
  "session_id": "session-id",
  "agent_id": "codex:session-id",
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

Submission requires an empty prompt and the exact current message in the position occupied by the saved pre-Enter draft. The earlier non-empty history lines must still match. An older identical message cannot confirm this attempt. Missing or changed current input, truncated history, or a layout change leaves UNCONFIRMED. This conservative check can leave a successful delivery unconfirmed; it never permits another Enter for that event.

The durable record key is (host, session_id, agent_id, task_id, event_id, candidate, sender pane, destination pane). These fields identify the originating host session and task. Stop checks records with the exact registered host/session/agent and every task ID in that binding's approved-work list. A completed task can still owe a return delivery. Work eligibility is checked separately. Reusing a pane for a new session does not transfer old delivery obligations. Legacy records without a session binding are retained as unbound history and are not assigned to a new session.

The record stores delivery status, capture hashes, and a SHA-256 message fingerprint. It never stores the message body or captured pane text. A repeated event cannot send again. A fresh PREPARED event cannot claim a matching draft. Recovery is allowed only when the durable record was already TYPED for that same event and the exact recorded capture, sender, and message are still present. The helper writes UNCONFIRMED before it attempts Enter. If Enter may have been sent, do not retry that event.

The helper requires operator preflight confirmation because terminal captures do not identify an idle Codex or Claude prompt with enough certainty across versions. If the capture is unknown, partial, busy, or contains any draft, do not confirm it. This is not unattended sending.

## SessionStart binding

The controller prepares one approved assignment in the same private state root used by `bind`, `send`, and the Stop hook. The assignment names the host, role, task, exact pane and worktree, required reports, and approved work. It expires after 15 minutes and cannot enroll a second session after use.

~~~json
{
  "approved": true,
  "assignment_id": "dispatch-2026-10-07-01",
  "host": "codex",
  "role": "worker",
  "task_id": "CTRL-BIND-L3-01",
  "pane_id": "%5",
  "cwd": "/path/to/assigned/worktree",
  "required_reports": [".scratch/controller-guard-binding/RESULT.md"],
  "approved_work": [{"id": "CTRL-BIND-L3-01", "status": "in_progress"}]
}
~~~

Prepare it before the controller clears the selected worker or gate session:

~~~sh
python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" assign codex < assignment.json
~~~

For CTRL-BIND-L3-01, the controller's recorded fresh activation, exact assignment, base, and task packet are the implementation bootstrap. The receipt produced by this SessionStart adapter is acceptance evidence; requiring it before implementing the adapter would block the task on its own output. This exception does not qualify the worker's current session or permit ordinary managed dispatch without a matching receipt. Once this tooling is accepted and enabled, future managed assignments require a verified receipt before their task packet is sent.

The native `SessionStart` hook reads the host's actual `session_id`, `cwd`, and lifecycle `source`. It gets the pane ID from `tmux-bridge id`. It registers only a fresh `startup` or `clear` event that matches the approved host, pane, and worktree. A worker starts `ACTIVE`. A gate starts `AWAITING_EVENT`.

Resume, compaction, fork, and duplicate events return the existing receipt and leave task status, reports, review history, gate counts, and delivery records unchanged. A session with no approved assignment stays unbound. A mismatched, expired, consumed, or malformed assignment produces no receipt and cannot replace an existing binding.

The hook writes a receipt to `bindings.json` and returns a small native SessionStart result. The controller must verify the receipt before it sends task activation:

~~~sh
python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" receipt codex SESSION_ID ASSIGNMENT_ID
~~~

Check that the result matches the host, session, role, task, pane, worktree, assignment ID, and assignment SHA-256. A missing or mismatched receipt blocks dispatch. The hook grants no task, merge, provider, or financial authority.

The committed Codex and Claude hook commands use the helper's project-scoped default state root. If you set `CONTROLLER_GUARD_STATE_ROOT`, use the same value for SessionStart, `bind`, `send`, `assign`, `receipt`, and Stop. Do not commit a machine-specific state path.

## Native lane checklist

- Trust the project and hook through the client's normal controls. Confirm the command in `/hooks`.
- For Claude, start from the repository root and confirm `/hooks` lists the project's SessionStart and Stop commands. A subdirectory session that shows only plugin hooks has not loaded these project hooks.
- Set `GUARD_STATE_ROOT` to a private temporary directory and use it for every command in the check. Prepare a complete assignment, then run `python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" assign codex < assignment.json` (use `claude` for Claude). The command must return an assignment fingerprint.
- In the selected trusted native session, enter `/clear` through the host UI. The SessionStart hook must report the host's new session and assignment fingerprint. Verify with `python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" receipt codex SESSION_ID ASSIGNMENT_ID`. The receipt must match task, role, pane, worktree, and fingerprint before activation. Workers start `ACTIVE`; gates start `AWAITING_EVENT`.
- For a missed-delivery check, set `HOST`, `SESSION_ID`, `PANE_ID`, and `TASK_ID` from the verified receipt, then add one synthetic row. This writes no message and presses no key:

~~~sh
python3 -c 'import os; from pathlib import Path; from scripts.controller_guard import GuardStore; host=os.environ["HOST"]; session=os.environ["SESSION_ID"]; pane=os.environ["PANE_ID"]; GuardStore(Path(os.environ["GUARD_STATE_ROOT"])/"delivery.sqlite3").put_record({"host":host,"session_id":session,"agent_id":host+":"+session,"task_id":os.environ["TASK_ID"],"event_id":"synthetic-missed","candidate":"fixture","sender":pane,"destination":pane,"status":"UNCONFIRMED"})'
~~~

The next inert native prompt must produce one continuation. Set the same binding to `AWAITING_EVENT` and update it with `python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" update "$HOST" < gate-waiting.json`; the next Stop must return `{}`.
- Prepare a second assignment with a new task and assignment ID, then repeat native `/clear` and receipt verification. The new session must have only the new task's obligations; the first session keeps its reports and delivery rows.
- Resume or compact the second session. The receipt, status, reports, review history, and gate count must remain unchanged.
- Repeat on Codex and Claude. Both use `session-start` and the same SessionStart result shape. Codex emits `additionalContext`; Claude must show the project's SessionStart and Stop commands in `/hooks`. Do not use trust-bypass flags. An unavailable client, trust prompt, or native input is a gap, not a pass.

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

The following explicit statuses allow Stop, even when obligations remain: AWAITING_EVENT, BLOCKED, BUDGET_EXHAUSTED, APPROVAL_REQUIRED, INTERRUPTED, RUN_LIMIT, and COMPLETE. Other statuses can block once for a durable reason identity. stop_hook_active always allows the continuation call. The guard can block a missing required report, an unfinished delivery for a task in this binding, or approved work with status eligible, pending, or in_progress. Allowed and unregistered hook results are `{}` so this guard does not override another Stop hook. Its own block uses the host's `decision:block` output.

An empty obligation list means that this binding has no tracked obligation. It does not prove that a review or task is complete. Do not register an empty list as a completion record. Missing bindings allow Stop by design. Registration rejects NUL characters in cwd and report paths. A malformed registered binding, including invalid paths or pane/session identity, blocks once with a repair instruction. Exceptions from path resolution or file checks use the same repair result. A mismatched session, agent, or cwd also blocks once. Reason identities are hashes, limited to the most recent 64 per host/session.

The hook does not call a model itself, press Enter, inspect or poll panes, create a batch, extend a budget, or approve a merge or financial action. A block asks the host to continue once with the reason.

## Hook setup and limits

The committed Codex template resolves the script from the Git root. Codex runs the command in the session cwd. The Claude template uses CLAUDE_PROJECT_DIR. The templates do not bypass project trust or Codex hook trust. The user must trust the project and the exact hook through the host's normal controls.

For a private workspace whose session cwd is outside the application repository, configure a local hook command to point at the preserved tooling worktree and set CONTROLLER_GUARD_STATE_ROOT to the private workspace's local state directory. Pass that same root to bind and send. Do not add that machine-specific path to committed configuration. No global hook or restart is needed.

Current references:

- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)

Directly invoking the helper does not prove that the host loaded or trusted a hook. Confirm the hook in the host's own hook UI or trusted configuration. The fixture tests exercise tmux-bridge in an isolated non-agent tmux session. They do not prove behavior in a live Codex or Claude TUI.
