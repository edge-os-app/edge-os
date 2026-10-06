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

## Task and review packets

Each worker receives one accepted ticket, its observable result and exclusions, blockers and evidence, exact base SHA, branch/worktree, owned/shared changes, verification commands, required skills, actual model settings and review budget. Shared schemas, migrations, lockfiles and configuration cannot have concurrent owners. Start fewer workers when those dependencies prevent safe parallel work.

Every pane assignment also names the task identity, controller/reply pane and worker/gate destinations. Carry those destinations into replacement sessions. Use the message envelope's actual sender pane as the reply route unless the packet explicitly assigns another recipient. A missing reply destination is an incomplete handoff.

Include a task-specific required-input list using the [implementation reference map](../research/EDGE_OS_IMPLEMENTATION_REFERENCE_MAP.md), accepted specification/ADRs, contracts, fixture/source versions and runtime-verification recipe. The builder's controller checks relevant private workspace references before dispatch and supplies the permitted verified extracts or independently authored examples. Teammate workers use checkout-relative files or issue attachments; missing private inputs block the affected claim rather than trigger guessing. For Privy/auth work, require current official docs through Context7 and Exa, with the selected key/session assumptions recorded. Avoid assigning every course or unrelated project to every task.

### Fresh-session activation

Start each new ticket in fresh worker and gate sessions. The controller performs this procedure before sending either activation packet:

1. Confirm the previous task is inactive and its state is saved. Preserve its candidate, reports and unresolved work.
2. Verify the assigned worktree, branch, base and pane identities. Read each destination before interaction.
3. Confirm the pane has no unsent draft, active command or unfinished agent task. Preserve any such input. Report blocked activation.
4. For the current Claude Code and Codex lane clients, run native `/clear` before each new ticket's activation packet. P01 verified this command in both clients. Confirm support in the actual client and record its source in the dispatch ledger. A different host requires its verified native equivalent, not a guessed `/clear` or `/new`.
5. Enter the native command with `tmux-bridge type`, not `message`. Read the pane to confirm the exact command. Send `Enter` only after confirmation.
6. Confirm the fresh context and actual host/model/effort before packet delivery. Record an unavailable setting explicitly. Stop if required identity or fresh-context confirmation is unavailable.
7. Deliver the complete activation packet through the Smux procedure below. The gate then remains in standby for the worker's exact candidate.

Record the activation evidence in the ledger. These are pre-dispatch checks, not progress polling. A fresh session changes neither Git state nor review budgets. Do not clear an active task to repair transport. A same-ticket context replacement instead needs a saved handoff and resumption checks.

### Worker activation packet

Adapt the inspected OKX/TX Odds input, authority, preflight and proof patterns through this one template. The controller fills every field before dispatch; template placeholders are not a ready assignment.

```text
Implement only accepted ticket <issue> from specification <revision>.
Use the assigned worktree <absolute path>, branch <branch> and base <SHA>.
Read AGENTS.md, the current handoff, linked ADRs and these required inputs: <paths/versions>.
Read the applicable implementation-reference-map rows; missing mandatory input blocks that claim.
State briefly what changes, what stays unchanged and what observable result proves completion.
Use /implement and task-relevant skills <names>; use current Context7 docs and Exa where required.
Owned changes: <surfaces>. Shared/forbidden changes: <surfaces>. Coordinate before crossing them.
Implement the accepted success and failure behavior; use TDD at <agreed seams>.
Run <actual tests and runtime recipe>; inspect <saved records and side effects>.
Retain evidence under <path>, including exact build/fixture identities and unavailable checks.
Update the verification recipe/feature map when the implemented path changes.
Produce a clean candidate and run the two native internal reviews under the approved host policy.
Retain both original reviewer assessments under the original-reviewer-reports procedure below.
Send <gate pane> the candidate SHA, checks, evidence and limitations. Await acceptance.
Send replacement candidates directly to <gate pane>. Follow the required return-delivery table for controller escalation.
Save the report first, relay its path and exact candidate identity using the messaging procedure below.
Confirm submission with its one post-Enter read, then await an incoming Smux message. Do not poll for progress.
Task authority: <explicit allowed operations/budgets>. No main merge or unrelated external action.
```

### Gate activation packet

Send the gate a filled review packet after fresh-session activation. The gate's own review must apply the required stack; checking the worker's reports alone is insufficient.

```text
You are the independent Edge OS gate for <task/issue>.
Use general-review-protocol, then review-verification-protocol, code-reviewer and code-review-excellence.
Load task-relevant review skills <names>. Keep reviewers read-only.
Read AGENTS.md, this lane procedure, the accepted ticket/specification/ADRs and <required inputs/versions>.
Assigned base: <SHA>. Review checkout: <absolute path>. Owned scope: <surfaces>.
Worker destination: <verified pane>. Controller/reply destination: <verified pane>.
Acceptance criteria: <observable results>. Required checks: <commands and evidence>.
Review budget: <approved internal/gate limits and existing counters>.
After activation, remain in standby until the worker delivers an exact committed candidate and both original internal PASS assessments.
Do not inspect a moving worker branch or monitor its internal reviewers.
On candidate receipt, verify ancestry, scope, both original assessments and their candidate binding.
Independently inspect the candidate and run the assigned checks. Record actual models/effort, applied skills and unavailable checks.
Save the candidate-bound gate assessment at <report path> before delivery.
Within budget, send 1/3 or 2/3 blockers directly to <worker pane>, without routine controller copies.
Send PASS or unresolved 3/3 blockers to <controller pane>. Escalate authority, budget or unsafe-delivery obstructions earlier.
Use the canonical Smux procedure, including its single post-Enter submission check. Then return to standby.
PASS approves only the reviewed candidate. It grants no publication, merge, dispatch, provider or financial authority.
```

The controller schedules and integrates. The worker implements and commits. Reviewers remain read-only. The builder retains acceptance and main-branch merge control. A controller cannot supply the independent approval for its own change.

1. The worker produces a clean candidate commit and records checks and limits.
2. Pause the worker while reviewers inspect its worktree. Alternatively use a separate read-only checkout of the exact commit.
3. Confirm candidate ancestry and scope against the assigned base.
4. Run two independent native reviewer contexts under the [worker-host model policy](../../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md#approved-model-policy). Give both the same base, candidate and acceptance packet. Record actual models and effort.
5. Keep their initial findings hidden from each other. Both reviewers load General Review Protocol, then Review Verification Protocol, Code Reviewer and Code Review Excellence. Add only applicable domain skills.
6. Return verified blockers to the worker in one batch. A fix requires a replacement commit and both reviewers' assessment of the changed behavior and affected invariants.
7. Record each verdict with the exact candidate SHA. An earlier PASS never approves later edits.
8. Send the internally reviewed candidate and both original assessments to the separate Codex gate. The gate checks the review evidence before issuing PASS. Record its independent verdict against that same candidate. The builder accepts and merges under the manual policy.

### Original reviewer reports

Retain the original assessment from each independent native reviewer context. The worker may save the returned assessment unchanged with its source identity. It must not replace the assessment with its own PASS summary or write a review on another reviewer's behalf. Preserve earlier assessments as historical evidence after replacement reviews.

Each assessment must identify:

- Task, reviewer assignment and native context identity.
- Exact base and candidate SHA.
- Actual host/model and effort, or the specific unavailable-setting limitation permitted by the model policy.
- Required skills actually applied. Name any missing skill or unavailable instruction source.
- Checks performed, results and evidence paths. Distinguish reviewer-run checks from worker evidence inspected.
- Findings, limitations and explicit PASS or REVISE verdict.

The worker supplies both assessment paths and identities with the gate packet. If an assessment arrives only through a native completion tool, retain that original response and its context identifier. Both assessments must cover the same candidate. A later fix requires candidate-bound replacement assessments for the changed scope and affected invariants.

The gate verifies both original assessments against the packet and candidate. Missing required skills, missing original assessments or candidate mismatches block PASS. A recorded unavailable setting must meet the existing model policy; it is not an automatic waiver. The gate's own review cannot replace incomplete internal reviews. Keep private reports and sensitive logs outside shared candidates unless their publication is explicitly authorized.

### Review budgets and host changes

Record native internal-review cycles and independent gate cycles separately. Identify every gate verdict as `1/3`, `2/3` or `3/3`. Internal repairs do not count as completed gate reviews. Preserve the assignment's approved repair budget. Neither a new counter nor a routing correction resets an exhausted budget.

Within the approved budget, gate blockers at `1/3` and `2/3` return directly to the worker. The worker repairs them, completes the required internal reviews, commits a replacement and returns it to the gate. The controller receives PASS or unresolved blockers at `3/3`. A decision outside task authority, blocked delivery or an exhausted approved budget needs earlier escalation. At a budget limit, the builder approves any extension or product-scope change. A cycle limit cannot turn a failure into a PASS.

The worker owns its two native internal review contexts. The Codex gate reviews separately after their completion. One pane, one model or two sequential passes in the same context cannot replace two independent contexts. Do not repeat release-wide review for every small replacement.

When switching between Claude and Codex workers, preserve the lane and task state, stop the prior writer, and verify path/branch/base before resuming. Use the new host's approved review route. Keep OMC disabled and use the existing panes; no new coordination layer is required. A subscription limit does not waive a required review or authorize extra paid usage.

## Messaging, integration and handoff

Use Smux and `tmux-bridge` for cross-pane requests and replies. Load the Smux skill and follow this delivery sequence:

1. Read the destination pane before sending.
2. Preserve an unsent draft or active command; do not overwrite it or submit it accidentally.
3. Use `tmux-bridge message` to enter the packet or reply.
4. Read once to confirm the complete message reached the input.
5. Send `Enter` to submit that message.
6. Read the destination once after `Enter`. Confirm the exact message appears in its submitted transcript or accepted queue, not only its input.
7. Record the destination, message identity and observed submission status in the task evidence. Return to standby or independent authorized work.

Typing and a successful Enter command alone do not prove delivery. If the post-Enter read does not confirm submission, record `DELIVERY UNCONFIRMED`. Preserve the message and observed state. Do not blindly resend, press Enter again or repeat reads. Use the blocked-delivery route below to request safe recovery. A submitted message does not prove the recipient started or completed the task.

The builder explicitly requires this one post-Enter confirmation for every controller, worker and gate message. It supplements Smux's default sequence. It does not permit reading for a reply.

### No polling while another pane works

After dispatch, do not repeatedly read/capture a pane, inspect its changing branch, call background thread status/read/wait APIs, launch watcher subagents or run sleep/retry loops to discover progress or completion. A completion notice comes from the assigned agent through Smux. Do not replace pane delivery with a background-thread message or status-wait loop merely because that tool is available. The pre-send, pre-Enter and single post-Enter reads are transport checks, not a progress-monitoring loop.

A gate receiving an advance review packet remains in standby until its worker sends the exact candidate. It must not monitor the worker or wait for the worker's internal reviewers. The gate starts its own assigned review only after candidate delivery. Native internal reviewers may use their host's completion notifications; that is separate from watching another tmux lane. Read an interactive non-agent process only when its assigned task requires that interaction.

### Required return delivery

Every controller, worker and gate uses the messaging procedure above, including the single post-Enter submission check. Writing a final answer in the sender's own pane or saving a report is not delivery to the recipient.

| Sender and event | Required destination and contents |
|---|---|
| Worker has a reviewed candidate | Assigned gate: task, exact base/candidate, checks, evidence path and limits. |
| Gate finds blockers at `1/3` or `2/3`, within budget | Assigned worker only: evidenced blockers, exact candidate, cycle count, report path and required replacement checks. No routine controller copy. |
| Gate completes PASS | Recorded controller/reply pane: exact candidate, report path, checks and remaining limits. |
| Gate has unresolved blockers at `3/3` | Recorded controller/reply pane: exact candidate, report path, blockers, dependency risks and proposed next decision. |
| A decision, exhausted approved budget or unsafe delivery prevents the loop | Controller/reply pane: only the specific obstruction and decision needed. Preserve drafts and saved findings. |
| Controller returns a decision after escalation | Assigned gate: scoped direction and authority. The gate relays it to the worker. |
| Controller records builder acceptance, publication or integration outcome | Assigned gate: task, reviewed candidate, distinct acceptance/publication/integration states, resulting commit and checks when applicable, and authorized next action or standby. The gate relays that outcome once to the assigned worker. |

Write routine review status in durable reports without sending controller progress pings. An activation acknowledgment requested by the packet is separate from a candidate verdict. Send each request or result from the assigned sender pane. The bridge envelope's reply route does not override the event destination above.

Resolve and verify actual pane identity before sending; never invent a sender ID or retarget a request silently. If Smux or the recorded pane is unavailable, or its draft prevents safe delivery, preserve the packet/report and report delivery as blocked. Ask for an explicit alternative route. Do not silently switch to background thread APIs or start polling. After a reply arrives, verify its durable record and candidate identity before changing task status; a notification alone is not completion evidence.

### Serial integration and task closure

For each accepted candidate:

1. Verify the builder's authority and the exact gate-passed candidate. Keep publication, integration-branch changes and main merge separate. A changed candidate needs replacement review.
2. Integrate only that candidate into the authorized target, one candidate at a time. Preserve active workers' recorded bases.
3. Run the affected integration checks against the resulting commit. If they fail, record the failure and leave integration incomplete.
4. Update the live ledger and applicable tracker state with the reviewed candidate, actual resulting commit, checks and limits. Reassess waiting assignments against that base.
5. Send the recorded outcome through controller → gate → worker under the return-delivery table. If delivery is unsafe, preserve the outcome and use the obstruction route.
6. Leave the lane in standby. Assign another ticket only under separate accepted authority and fresh-session activation.

Gate PASS, builder acceptance, publication and verified integration are distinct states. Do not mark a task integrated from an issue status alone. No automatic main merge is authorized.

The live ledger records the integration SHA, ticket and owner, path/branch/base, candidate SHA, checks, both reviews, integration status, blocker and next action. Keep its current summary short and dated. Preserve prior evidence below it. Before ending a session, leave enough information for a fresh controller to resume without conversation history.

GitHub remains the shared task tracker. Local proposals and idle branches are not implementation assignments. Publish required extracts and the accepted handoff before a teammate depends on them. Never send private courses, credentials or raw prototype archives as shared task inputs.
