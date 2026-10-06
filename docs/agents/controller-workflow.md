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

The controller schedules and integrates. The worker implements and commits. Reviewers remain read-only. The builder retains acceptance and main-branch merge control. A controller cannot supply the independent approval for its own change.

1. The worker produces a clean candidate commit and records checks and limits.
2. Pause the worker while reviewers inspect its worktree. Alternatively use a separate read-only checkout of the exact commit.
3. Confirm candidate ancestry and scope against the assigned base.
4. Run two independent reviewer contexts using the project's Sol/high policy. Give both the same base, candidate and acceptance packet.
5. Keep their initial findings hidden from each other. Use General Review Protocol for evidenced defects and task-relevant domain checks.
6. Return verified blockers to the worker in one batch. A fix requires a replacement commit and both reviewers' assessment of the changed behavior and affected invariants.
7. Record each verdict with the exact candidate SHA. An earlier PASS never approves later edits.

Use at most three review/fix cycles for a dispatched unit unless the builder approves another budget. At the limit, report unresolved blockers and choose a scoped escalation, proposed narrowing or deferral. The builder must approve a product-scope change. A cycle limit cannot turn a failure into a PASS.

The gate pane can coordinate the two reviews. One pane, one model or two sequential passes in the same context cannot replace two independent contexts. Do not repeat release-wide review for every small replacement.

## Messaging, integration and handoff

Read the destination pane before messaging. Preserve drafts and active commands. Send the packet, read once to confirm arrival, submit it, then stop polling. A gate waits for the exact candidate packet. It does not inspect a worker's changing tree or wake repeatedly to ask for status.

Integrate accepted candidates serially under the project's authorization. Run the affected integration checks after each change. Reassess waiting assignments against the new base. Do not mark a task integrated from an issue status alone. No automatic main merge is authorized.

The live ledger records the integration SHA, ticket and owner, path/branch/base, candidate SHA, checks, both reviews, integration status, blocker and next action. Keep its current summary short and dated. Preserve prior evidence below it. Before ending a session, leave enough information for a fresh controller to resume without conversation history.

GitHub remains the shared task tracker. Local proposals and idle branches are not implementation assignments. Publish required extracts and the accepted handoff before a teammate depends on them. Never send private courses, credentials or raw prototype archives as shared task inputs.
