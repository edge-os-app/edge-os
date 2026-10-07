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

Pass that object on standard input to python3 scripts/controller_guard.py send. The helper verifies the active sender pane and destination identity. It types one normal Smux message and waits 0.35 seconds before reading. If that capture is empty or stale, it waits another 0.35 seconds and makes one recovery read. It sends one Enter only after either read confirms the exact active input, then waits 0.35 seconds and reads once after Enter. It never polls or repeats Enter.

Submission requires an empty prompt and the exact current message in the position occupied by the saved pre-Enter draft. The earlier non-empty history lines must still match. An older identical message cannot confirm this attempt. Missing or changed current input, truncated history, or a layout change leaves UNCONFIRMED. This conservative check can leave a successful delivery unconfirmed; it never permits another Enter for that event.

If neither pre-Enter capture verifies the exact message, the event is BLOCKED and the helper leaves the pane input unchanged. A stale capture alone does not prove the type failed. The one recovery read is the limit; an unresolved or foreign draft stays untouched for operator inspection.

The durable record key is (host, session_id, agent_id, task_id, event_id, candidate, sender pane, destination pane). These fields identify the originating host session and task. Stop checks records with the exact registered host/session/agent and every task ID in that binding's approved-work list. A completed task can still owe a return delivery. Work eligibility is checked separately. Reusing a pane for a new session does not transfer old delivery obligations. Legacy records without a session binding are retained as unbound history and are not assigned to a new session.

The record stores delivery status, capture hashes, and a SHA-256 message fingerprint. It never stores the message body or captured pane text. A repeated event cannot send again. A fresh PREPARED event cannot claim a matching draft. Recovery is allowed only when the durable record was already TYPED for that same event and the exact recorded capture, sender, and message are still present. The helper writes UNCONFIRMED before it attempts Enter. If Enter may have been sent, do not retry that event.

The helper requires operator preflight confirmation because terminal captures do not identify an idle Codex or Claude prompt with enough certainty across versions. If the capture is unknown, partial, busy, or contains any draft, do not confirm it. This is not unattended sending.

The tested Codex CLI 0.160.1 and Claude Code captures render their empty composers as `› Ask Codex to do anything`, `❯ Try "edit <filepath> to..."`, and `❯ Try "fix lint errors"` (Claude Code 2.1.293). The helper recognizes these observed empty placeholders, the prior Claude `❯ Try …` rendering, and known native separator/footer rows. It checks the prompt before the footer, accepts wrapped own input only when it reconstructs the exact message, and leaves collapsed or unknown input blocked. This is layout recognition, not proof that a native send or Enter succeeded; verify disposable native delivery separately.

## SessionStart binding

The controller prepares one approved assignment in the same private state root used by `bind`, `send`, and the Stop hook. The assignment names the host, role, task, exact pane and worktree, required reports, and approved work for that task only. It expires after 15 minutes and cannot enroll a second session after use.

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

The native `SessionStart` hook reads the host's actual `session_id`, `cwd`, and lifecycle `source`. It gets the pane ID from `tmux-bridge id`. It registers a fresh `startup` or `clear` event that matches the approved host, pane, and worktree. A worker starts `ACTIVE`. A gate starts `AWAITING_EVENT`.

Resume and duplicate events on the same native session return the existing receipt and leave task status, reports, review history, gate counts, and delivery records unchanged. A fork has a new native session ID. To bind it, the controller must prepare a one-use same-task assignment with `fork_parent_session_id` set to the parent session from its verified receipt. The hook verifies the parent receipt, the fork's exact assigned pane, and the same worktree/task/reports/approved-work, then carries the current binding state and delivery lineage to the new ID. A missing or mismatched parent assignment leaves the fork unbound. A mismatched, expired, consumed, or malformed assignment produces no receipt and cannot replace an existing binding.

An ordinary `update` changes status, reports, or approved work while retaining the verified assignment identity and any omitted binding state. It cannot change the task assignment, remove prior review history, or lower the gate-verdict count.

The hook writes a receipt to `bindings.json` and returns a small native SessionStart result. The controller must verify the receipt before it sends task activation:

~~~sh
python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" receipt codex SESSION_ID ASSIGNMENT_ID
~~~

Check that the result matches the host, session, role, task, pane, worktree, assignment ID, and assignment SHA-256. A missing or mismatched receipt blocks dispatch. The hook grants no task, merge, provider, or financial authority.

The committed Codex and Claude hook commands use the helper's project-scoped default state root. If you set `CONTROLLER_GUARD_STATE_ROOT`, export it before launching both clients and use that same value for SessionStart, `bind`, `send`, `assign`, `receipt`, and Stop. Do not commit a machine-specific state path.

### Codex CLI 0.160.1 launch environment

Launch each managed native Codex session with `codex --no-daemon` from its assigned pane. Codex clients that attach to the shared app-server use the environment from daemon startup. A terminal export does not give an attached client a private environment ([Codex daemon environment contract](https://github.com/openai/codex/blob/rust-v0.160.1/codex-rs/app-server-daemon/README.md#platform-support)). Codex runs hook commands from the session environment snapshot ([hook command runner](https://github.com/openai/codex/blob/rust-v0.160.1/codex-rs/hooks/src/engine/command_runner.rs)).

Do not hardcode `TMUX_PANE` or treat the assignment's pane ID as runtime proof. The hook must read the actual pane from `tmux-bridge id` and the same `CONTROLLER_GUARD_STATE_ROOT` used by the controller. A missing or mismatched receipt blocks dispatch.

A disposable, normally trusted Codex CLI 0.160.1 fixture produced and verified matching `startup` and `clear` receipts with the exact, unwrapped project hook config when launched with `--no-daemon`. A shared-daemon control lacked both environment values and produced no receipt. Idle startup and idle post-clear state each produced no observed event during a 30-second wait. One initialization-only inert prompt produced the startup event; after a separate such prompt, native `/clear` produced the `clear` event and a verified receipt. For this installed Codex path, allow one initialization-only probe before task activation when idle hook startup has not produced a receipt. The probe must request no tools or assigned task work. It grants no task authority; verify the exact receipt before sending the task packet, and block dispatch if it is absent or mismatched.

Under normal project trust, fixture sessions on Codex CLI 0.160.1 and Claude Code 2.1.293 produced verified startup and clear receipts. Native Stop blocked once for a missing required report plus a synthetic `UNCONFIRMED` delivery. `AWAITING_EVENT` then allowed standby with those obligations open. Exact-ID resume on each host preserved the receipt, binding, task state, reports, history, gate counter, and delivery row. Codex resumed with `codex --no-daemon resume SESSION_ID`. Claude Code resumed with `claude --resume SESSION_ID`. Native compaction and fork remain untested. These fixture results do not qualify the current worker or other running lanes, and they do not prove protection across all lanes.

## Native lane checklist

- Trust the project and hook through the client's normal controls. Confirm the command in `/hooks`.
- For Claude, start from the repository root and confirm `/hooks` lists the project's SessionStart and Stop commands. A subdirectory session that shows only plugin hooks has not loaded these project hooks.
- In a shell that will launch both native clients, set the shared private state root using the variable the hooks read, then use its alias for every CLI command:

  ~~~sh
  export CONTROLLER_GUARD_STATE_ROOT="$(mktemp -d)"
  export GUARD_STATE_ROOT="$CONTROLLER_GUARD_STATE_ROOT"
  ~~~

  Prepare a complete assignment, then run `python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" assign codex < assignment.json` (use `claude` for Claude). The command must return an assignment fingerprint.
- Launch each managed native Codex session from its assigned pane with `codex --no-daemon`. Do not assume that shell exports reach a shared app-server daemon. Keep Claude's normal launch path unchanged.
- In the selected trusted native session, enter `/clear` through the host UI. If installed Codex 0.160.1 remains idle without a receipt, send one initialization-only probe that requests no tools or assigned task work; then check for the SessionStart receipt. Verify with `python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" receipt codex SESSION_ID ASSIGNMENT_ID`. The receipt must match task, role, pane, worktree, and fingerprint before activation. Workers start `ACTIVE`; gates start `AWAITING_EVENT`. If the receipt is absent or mismatched, block task-packet delivery. This probe only initializes the hook and grants no task authority.
- For a missed-delivery check, set `HOST`, `SESSION_ID`, `PANE_ID`, and `TASK_ID` from the verified receipt, then add one synthetic row. This writes no message and presses no key:

~~~sh
python3 -c 'import os; from pathlib import Path; from scripts.controller_guard import GuardStore; host=os.environ["HOST"]; session=os.environ["SESSION_ID"]; pane=os.environ["PANE_ID"]; GuardStore(Path(os.environ["GUARD_STATE_ROOT"])/"delivery.sqlite3").put_record({"host":host,"session_id":session,"agent_id":host+":"+session,"task_id":os.environ["TASK_ID"],"event_id":"synthetic-missed","candidate":"fixture","sender":pane,"destination":pane,"status":"UNCONFIRMED"})'
~~~

The next inert native prompt must produce one continuation. Set the same binding to `AWAITING_EVENT` and update it with `python3 scripts/controller_guard.py --state-root "$GUARD_STATE_ROOT" update "$HOST" < gate-waiting.json`; the next Stop must return `{}`.
- Prepare a second assignment with a new task and assignment ID, then repeat native `/clear` and receipt verification. The new session must have only the new task's obligations; the first session keeps its reports and delivery rows.
- Resume by exact ID. Use `codex --no-daemon resume SESSION_ID` for Codex and `claude --resume SESSION_ID` for Claude Code. Use the session ID from the verified receipt. Send only a tiny inert probe after resume. Confirm that the receipt, status, reports, review history, and gate count remain unchanged.
- Native compaction and fork are not qualified by the fixture tests. Test them separately before claiming native coverage.
- Before a native fork, prepare an assignment for the same role, task, reports, and approved work as the verified parent receipt, with a fresh assignment ID and `fork_parent_session_id` set to that parent session ID. The fork must receive a new receipt while preserving the current status, review history, gate count, and pending delivery checks. Without the matching assignment, it stays unbound.
- Repeat on Codex and Claude. Both use `session-start` and the same SessionStart result shape. Codex emits `additionalContext`; Claude must show the project's SessionStart and Stop commands in `/hooks`. Do not use trust-bypass flags. An unavailable client, trust prompt, or native input is a gap, not a pass.

## Delivery timing and Stop recovery checks

Use disposable native Codex and Claude panes in the already trusted fixture project. Keep their receipt, event, and state identities separate. Use only unique inert markers. Do not use a model switch, quota bypass, or external send path.

- Run the guard unit test `python3 -m unittest tests.test_controller_guard.CheckedSendTests.test_delayed_display_gets_one_safe_recovery_read_before_enter`. Its deterministic bridge returns the old empty prompt once after a successful type, then the exact draft. Expect one message, one extra read, one Enter, and `SUBMITTED`. The ordinary success test remains the immediate-display control.
- On each native client pane, preflight the exact pane and inspect the capture locally. Run one checked send with a fresh event ID and the matching sender/session/task identities. The helper waits 0.35 seconds before the pre-Enter capture, permits only one additional 0.35-second recovery settle/read when that capture is stale, and waits 0.35 seconds before its single post-Enter capture. Confirm a fresh event and exactly one Enter. Record whether the native client actually showed delayed rendering. A controlled stale-read result does not prove a native race occurred.
- The exact known empty composer placeholders above count as empty input; unknown prompt content remains blocked before `message` or `Enter`. Preserve uncertain input and record when the native race could not be exercised on that client. Do not change the empty-prompt assertion to force a send.
- For missed Enter, use the exact native SessionStart receipt and shared state root. In disposable panes only, create a fresh checked-send request, type its exact Smux envelope with `tmux-bridge message`, read and verify that exact draft, then record that capture as `TYPED` in `GuardStore`. Do not press Enter. Allow the bound native Stop hook to observe the open record and request one continuation. Complete that same event with `scripts/controller_guard.py send` using the unchanged request and pane identities; the helper, not the builder, presses Enter. Verify the exact marker appears once and the input is empty. Then run Stop once more to confirm no second continuation is required. Never use this fixture setup on a user or active agent draft.

The disposable `TYPED` fixture setup below rechecks the preflight hash, types once, confirms the exact draft, and stores only fingerprints:

~~~sh
TMUX_PANE="$SENDER_PANE" CONTROLLER_GUARD_STATE_ROOT="$STATE_ROOT" REQUEST_JSON="$REQUEST_JSON" python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
from scripts.controller_guard import GuardStore, TmuxBridge, _has_active_draft, _has_partial_input

request = json.loads(Path(os.environ["REQUEST_JSON"]).read_text())
bridge = TmuxBridge()
if bridge.id() != request["sender"]:
    raise SystemExit("sender pane changed")
before = bridge.read(request["destination_id"])
if (hashlib.sha256(before.encode()).hexdigest() != request["preflight_sha256"]
        or not request.get("confirm_idle") or not request.get("confirm_no_draft")
        or _has_partial_input(before)):
    raise SystemExit("destination is not the confirmed idle fixture pane")
bridge.message(request["destination_id"], request["text"])
typed = bridge.read(request["destination_id"])
if not _has_active_draft(typed, request["sender"], request["text"]):
    raise SystemExit("exact fixture draft was not visible; do not press Enter")
GuardStore(Path(os.environ["CONTROLLER_GUARD_STATE_ROOT"]) / "delivery.sqlite3").put_record(
    {**request, "status": "TYPED", "typed_sha256": hashlib.sha256(typed.encode()).hexdigest()}
)
PY
~~~

After the native Stop continuation is observed, submit the unchanged request through the helper:

~~~sh
TMUX_PANE="$SENDER_PANE" CONTROLLER_GUARD_STATE_ROOT="$STATE_ROOT" \
  python3 scripts/controller_guard.py --state-root "$STATE_ROOT" send < "$REQUEST_JSON"
~~~

Do not copy the fixture draft into another pane.
- Set the same disposable binding to `AWAITING_EVENT` and invoke one native Stop check. Expect `{}` with no continuation. Keep user interruption, unverifiable/collapsed input, and foreign drafts separate; none is delivery success.
- Save only sanitized identities, hashes, command results, actor and observed timing. Do not save pane captures or message bodies. Clean up only the disposable sessions and state created for this check; retain the sanitized result and do not alter an active worker or gate pane.

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
