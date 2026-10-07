# Controller and worker lanes

Adopted setup: 2026-10-06. Follow [the Matt workflow](../../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md) for implementation, models, reviews and acceptance. This document supplies the lane procedure. It does not approve a ticket, publication, merge or financial operation.

## Before dispatch

Use the [team handoff](../CONTROLLER_HANDOFF.md), accepted specification revision, linked ADRs and assigned GitHub issue. The private workspace maintains the live lane ledger. Required inputs must also exist in the teammate's checkout or issue.

Dispatch only accepted work whose blockers have passed. Record the integration SHA, branch, absolute worktree path, owner, owned changes, forbidden changes and required checks. A label or message alone is insufficient evidence.

The repository currently contains documentation, not a runnable production application. The first production slice must supply repeatable startup, fixtures, checks, saved-record inspection and cleanup instructions. Do not describe those instructions as implemented before they run.

## Worktree layout

The application repository is `edge-os/` inside the private `monad-hack` workspace. Local worktrees live outside the repository:

| Role | Path relative to the private workspace | Branch |
|---|---|---|
| Integration | `.worktrees/edge-os/integration` | `integration/edge-os-mvp` |
| Worker 1 | `.worktrees/edge-os/lane-1-worker` | Idle initially; controller assigns a ticket branch |
| Worker 2 | `.worktrees/edge-os/lane-2-worker` | Idle initially; controller assigns a ticket branch |
| Worker 3 | `.worktrees/edge-os/lane-3-worker` | Idle initially; controller assigns a ticket branch |

Panes named `edge-os-controller`, `edge-os-controller-gate`, `edge-os-worker-lane-N` and `edge-os-gate-lane-N` are message destinations. Separate panes do not isolate Git changes. Before writing, each worker checks its actual path, branch, HEAD, base ancestry and clean state against the assignment. Repeat this check on resumption and after a branch change.

Only the controller prepares a persistent lane for its next ticket. Check cleanliness and the previous candidate's integration state first. Never reset a lane, remove a worktree or rebase active work as routine cleanup. If its base becomes stale, pause and resolve the integration plan before changing it.

## Fresh-session activation

The controller owns the pre-dispatch reset. The worker and gate do not clear their own sessions after they receive an activation packet.

For CTRL-BIND-L3-01, the controller's recorded fresh activation, exact assignment, base, and task packet are the implementation bootstrap. The receipt produced by this change is acceptance evidence, not a prerequisite for implementing it. This narrow exception does not qualify the active worker session or permit managed task dispatch without a matching receipt. Future managed assignments require that receipt before the task packet is sent.

Before each new ticket, the controller prepares an approved local binding assignment for the exact host, role, pane, worktree, reports, task, and approved work for that task only. Use the same state root as `bind`, `send`, and the Stop hook. The assignment expires after 15 minutes.

The controller then checks that each destination is idle and draft-free, enters native `/clear` through keys, and reads once to confirm the reset. After the SessionStart hook returns, the controller verifies the receipt with `controller_guard.py receipt`. The receipt must match the new host session, pane, worktree, assignment ID, task, and assignment fingerprint. Do not send task activation until this check passes. An absent or mismatched receipt blocks dispatch.

After the reset, confirm each client's actual host, model, effort, and fresh context. Send the complete task packet through Smux, with one pre-send read, one input check, one Enter, and one post-Enter submission check. Record the receipt and delivery evidence in the private lane ledger. A same-ticket repair does not require `/clear` and preserves all task and review state.

## Controller-guard coverage

The checked-send helper and Stop guard passed native checks on Codex CLI 0.160.1 and Claude Code 2.1.292 under normal project trust. That evidence covers those client setups. A hook affects only a trusted project session with a matching binding; an unbound session remains unaffected. This branch adds native SessionStart assignment binding and remains under review. The active worker session is still unqualified until it has its own matching receipt.

These hooks do not wake a stopped client, press Enter, or provide unattended batch authority. Client crashes, host sleep, and exhausted subscriptions remain operational limits. Continue to use checked delivery and the assigned event-driven lane procedure.

## Task and review packets

Each worker receives one accepted ticket, its observable result and exclusions, blockers and evidence, exact base SHA, branch/worktree, owned/shared changes, verification commands, required skills, actual model settings and review budget. Shared schemas, migrations, lockfiles and configuration cannot have concurrent owners. Start fewer workers when those dependencies prevent safe parallel work.

Every pane assignment also names the task identity, controller/reply pane and worker/gate destinations. Carry those destinations into replacement sessions. Use the message envelope's actual sender pane as the reply route unless the packet explicitly assigns another recipient. A missing reply destination is an incomplete handoff.

Include a task-specific required-input list using the [implementation reference map](../research/EDGE_OS_IMPLEMENTATION_REFERENCE_MAP.md), accepted specification/ADRs, contracts, fixture/source versions and runtime-verification recipe. The builder's controller checks relevant private workspace references before dispatch and supplies the permitted verified extracts or independently authored examples. Teammate workers use checkout-relative files or issue attachments; missing private inputs block the affected claim rather than trigger guessing. For Privy/auth work, require current official docs through Context7 and Exa, with the selected key/session assumptions recorded. Avoid assigning every course or unrelated project to every task.

### Worker activation packet

Adapt the inspected OKX/TX Odds input, authority, preflight and proof patterns through this one template. The controller fills every field before dispatch; template placeholders are not a ready assignment.

```text
Implement only accepted ticket <issue> from specification <revision>.
Use the assigned worktree <absolute path>, branch <branch> and base <SHA>.
Read AGENTS.md, the current handoff, linked ADRs and these required inputs: <paths/versions>.
Read the applicable implementation-reference-map rows; missing mandatory input blocks that claim.
State briefly what changes, what stays unchanged and what observable result proves completion.
Use /implement and task-relevant skills <names>; use current Context7 docs and Exa where required.
Verified SessionStart receipt: host <host>, session <session ID>, role <role>, pane <pane ID>, task <task ID>, assignment <SHA-256>.
Owned changes: <surfaces>. Shared/forbidden changes: <surfaces>. Coordinate before crossing them.
Implement the accepted success and failure behavior; use TDD at <agreed seams>.
Run <actual tests and runtime recipe>; inspect <saved records and side effects>.
Retain evidence under <path>, including exact build/fixture identities and unavailable checks.
Update the verification recipe/feature map when the implemented path changes.
Produce a clean candidate and run the two native internal reviews under the approved host policy.
Send <gate pane> the candidate SHA, checks, evidence and limitations. Await acceptance.
Reply through Smux to <controller/reply pane>; blockers go to <assigned recipient>.
Save the report first, relay its path and exact candidate identity, then return to standby.
After submission, await an incoming Smux message. Do not poll panes, branches or background thread status.
Task authority: <explicit allowed operations/budgets>. No main merge or unrelated external action.
```

The controller schedules and integrates. The worker implements and commits. Reviewers remain read-only. The builder retains acceptance and main-branch merge control. A controller cannot supply the independent approval for its own change.

1. The worker produces a clean candidate commit and records checks and limits.
2. Pause the worker while reviewers inspect its worktree. Alternatively use a separate read-only checkout of the exact commit.
3. Confirm candidate ancestry and scope against the assigned base.
4. Run two independent native reviewer contexts under the [worker-host model policy](../../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md#approved-model-policy). Give both the same base, candidate and acceptance packet. Record actual models and effort.
5. Keep their initial findings hidden from each other. Use General Review Protocol for evidenced defects and task-relevant domain checks.
6. Return verified blockers to the worker in one batch. A fix requires a replacement commit and both reviewers' assessment of the changed behavior and affected invariants.
7. Record each verdict with the exact candidate SHA. An earlier PASS never approves later edits.
8. Send the internally reviewed candidate to the separate Codex gate. Record its independent verdict against that same candidate. The builder accepts and merges under the manual policy.

Internal repair and review rounds have no numeric cap. Repeat in-scope repairs and two independent original reviews until both PASS on the same exact candidate. Preserve each round's reports and candidate identity. Ordinary findings stay in this worker loop.

Only independent gate verdicts have a three-review limit. Record the gate counter as `1/3`, `2/3`, or `3/3`. At `1/3` or `2/3`, the gate returns blockers to the worker. At unresolved `3/3`, the gate reports the blockers and next decision to the controller. An internal round count does not consume a gate verdict or justify an extension.

The worker owns its two native internal review contexts. The Codex gate reviews separately after their completion. One pane, one model or two sequential passes in the same context cannot replace two independent contexts. Do not repeat release-wide review for every small replacement.

When switching between Claude and Codex workers, preserve the lane and task state, stop the prior writer, and verify path/branch/base before resuming. Use the new host's approved review route. Keep OMC disabled and use the existing panes; no new coordination layer is required. A subscription limit does not waive a required review or authorize extra paid usage.

## Messaging, integration and handoff

Use Smux and `tmux-bridge` for cross-pane requests and replies. Load the Smux skill and follow this delivery sequence:

1. Read the destination pane before sending.
2. Preserve an unsent draft or active command; do not overwrite it or submit it accidentally.
3. Use `tmux-bridge message` to enter the packet or reply.
4. Read once to confirm the complete message reached the input.
5. Send `Enter` to submit that message.
6. Return to standby or do independent authorized work. Resume on the recipient's incoming Smux reply.

### No polling while another pane works

After dispatch, do not repeatedly read/capture a pane, inspect its changing branch, call background thread status/read/wait APIs, launch watcher subagents or run sleep/retry loops to discover progress or completion. A completion notice comes from the assigned agent through Smux. Do not replace pane delivery with a background-thread message or status-wait loop merely because that tool is available. The pre-send read and one delivery-confirmation read are transport checks, not a progress-monitoring loop.

A gate receiving an advance review packet remains in standby until its worker sends the exact candidate. It must not monitor the worker or wait for the worker's internal reviewers. The gate starts its own assigned review only after candidate delivery. Native internal reviewers may use their host's completion notifications; that is separate from watching another tmux lane. Read an interactive non-agent process only when its assigned task requires that interaction.

### Required return delivery

Every controller, worker and gate relays requests, results and blockers through its assigned pane using the same read/message/read/Enter sequence. Writing a final answer in the sender's own pane or saving a report is not delivery to the recipient.

| Sender and event | Required destination and contents |
|---|---|
| Worker has a reviewed candidate | Assigned gate: task, exact base/candidate, checks, evidence path and limits. |
| Gate finds blockers | Assigned worker: evidenced findings and reviewed candidate; notify the controller of a decision/dependency blocker or exhausted review budget. |
| Gate completes PASS, REVISE or an unresolved review | Recorded controller/reply pane: verdict, exact candidate, report path, checks, blockers and next required decision. |
| Controller accepts or returns direction | Assigned gate/worker panes: exact accepted candidate or scoped next action and authority. |

Resolve and verify actual pane identity before sending; never invent a sender ID or retarget a request silently. If Smux or the recorded pane is unavailable, or its draft prevents safe delivery, preserve the packet/report and report delivery as blocked. Ask for an explicit alternative route. Do not silently switch to background thread APIs or start polling. After a reply arrives, verify its durable record and candidate identity before changing task status; a notification alone is not completion evidence.

Integrate accepted candidates serially under the project's authorization. Run the affected integration checks after each change. Reassess waiting assignments against the new base. Do not mark a task integrated from an issue status alone. No automatic main merge is authorized.

The live ledger records the integration SHA, ticket and owner, path/branch/base, candidate SHA, checks, both reviews, integration status, blocker and next action. Keep its current summary short and dated. Preserve prior evidence below it. Before ending a session, leave enough information for a fresh controller to resume without conversation history.

GitHub remains the shared task tracker. Local proposals and idle branches are not implementation assignments. Publish required extracts and the accepted handoff before a teammate depends on them. Never send private courses, credentials or raw prototype archives as shared task inputs.
