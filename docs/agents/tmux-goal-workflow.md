# Existing lanes with ticket Goals

Profile: `tmux-goal`. Prepared 2026-10-08 for a new, explicitly assigned pilot. No session, Goal, model or hook configuration is activated by this document. Existing assignments keep their recorded procedure until a scoped handoff is authorized.

Read [workflow selection](execution-workflows.md) and the shared [controller procedure](controller-workflow.md). This profile keeps the controller, implementation worker and independent gate panes. The two internal reviewers use built-in subagents, not additional tmux panes.

## Roles and model selection

Use [upstream defect routing](controller-workflow.md#upstream-defects-found-downstream) for bugs in accepted dependencies. Report exact evidence to the controller, preserve ownership and continue independent work. A worker Goal does not authorize upstream edits before a repair continuation grants those paths.

The controller chooses ready approved work, prepares worktrees and packets, handles genuine blockers and integrates proved candidates. The worker implements, verifies and repairs. The gate waits for an exact internally reviewed candidate, then performs its independent review. The builder does not carry routine messages between them.

Use [event-driven continuation](controller-workflow.md#event-driven-continuation) for the controller. After a gate return, integrate and dispatch the next authorized, eligible ticket in the same turn. Worker Goals remain ticket-scoped; the controller and gates need no polling Goals. Verify safe release before a new lane reset. If nothing is ready, remain idle until the next checked message. Record the named queue and its dispatch authorization in the existing ledger. This does not alter `native-batch`'s coordinator Goal.

For newly assigned Codex work, the recorded route is Luna implementation and Sol reviews/gate under the adopted model policy. Inspect existing pane settings and preserve them. An incompatible setting requires the builder's direction; dispatch does not authorize a model change. Verify the host can launch the prescribed built-in reviewer models before selecting this profile. If unavailable, report that limitation rather than silently create reviewer panes or substitute a model.

This profile does not give Claude a Codex Goal. A Claude worker requires its own explicitly qualified continuation setup. Preserve active Claude assignments.

## Activate one ticket

1. Confirm accepted prerequisites, assignment authority, ownership and an inactive previous task. Preserve its evidence and private worktree state.
2. Establish Codex worker/gate tools through `codex --no-daemon` launched inside their actual panes. Resume an active ticket by its exact session ID after the previous writer releases it; use fresh-session activation only for a new ticket. A working directory inside a worktree does not prove pane identity.
3. Have each agent run `tmux-bridge id` through its own command tool. Compare the result to its assigned pane. Never export a guessed `TMUX_PANE`. A controller shell check does not prove the agent's environment.
4. Use the integrated guard guide's approved assignment and SessionStart sequence. Verify native hook loading/trust, actual session/task/pane/worktree receipt and the same state directory for binding, Stop and checked-send. The guide is currently available in the reviewed integration checkout as `docs/agents/controller-guards.md`; use shared-context lookup if absent locally. Handle the helper's one-use pending assignments in order. Do not hand-edit receipts or reset an active lane to repair identity.
5. Deliver the frozen worker and gate packets with the existing short pointer/hash procedure. The worker packet includes its Goal objective and activation instruction. After reading it, the worker creates the actual Goal using its supported Goal tool, or the controller enters the supported native `/goal` command after a safe input check. Verify actual Goal state before implementation; a sentence in Markdown is not activation. Record the session, objective and observed state in task evidence. Do not add a numeric Goal budget unless the builder requests one.
6. Keep the gate in `AWAITING_EVENT`. Do not create a gate Goal that repeatedly polls or issues another verdict. Verify expected native Stop behavior with a harmless task-owned check before claiming protection, reusing retained qualification where applicable without disturbing active work.

Completion of activation requires both actual identity/binding evidence and an active worker Goal with the assigned objective. An unavailable check remains an explicit gap.

## Goal objective and completion

Fill this objective from the accepted task, with exact packet and evidence paths:

```text
Complete only <ticket/task> under <frozen packet>. Implement and verify its accepted success and failure behavior. Obtain both original independent internal PASS assessments on one committed candidate before first submission to <gate>. Route authorized gate repairs under controller-workflow.md#gate-stage-repair-review and any active-task amendment; obtain gate approval of the exact final candidate. Preserve scope, models, original candidate identities, gate history and operation limits. Investigate uncertainty using named sources and safe diagnostics. Return a precise genuine blocker to <controller> when authority, capacity or safe transport prevents further work. Finish only after accepted integration outcome is received and recorded in <result>; otherwise retain unfinished work and actual state.
```

The Goal covers this worker's ticket, including gate repairs; it grants no acceptance or merge authority to the worker. Do not mark it complete merely because a report was saved or a candidate was typed into another pane. Record a genuine blocker without turning it into completion. Apply the host's actual blocked-state rules, including the repeated-obstruction threshold when its Goal tool requires one. Legitimate waiting is not a defect to bypass with repeated checks. The controller resumes affected work only after the missing condition is resolved.

Goals are thread-scoped. A controller Goal does not activate Goals in separate worker panes. They cannot bypass provider limits, permissions, exhausted capacity or a stopped host. [Official Goal behavior](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex).

## Investigation and internal reviews

Follow the shared [verification cadence](controller-workflow.md#verification-cadence) for focused work, committed-candidate submission, assigned independent review and integration checks. Include it in the next task or repair/review packet; preserve active packets and in-flight checks.

Before escalation, read the named requirements/research, use shared-context lookup and relevant prior-project discovery, and run safe local diagnostics. Repair ordinary test/review defects within scope. If blocked, save the exact failed operation, checked sources, evidence, remaining safe work and required next decision. Confusion or an internal round count alone is not a blocker. Do not replace a failed provider operation with repeated unauthorized retries.

The worker reads Matt's `code-review` and launches exactly two independent built-in reviewer subagents under the [adapted Matt procedure](controller-workflow.md#adapted-matt-internal-review). They receive bounded pointers to the same base/candidate, not a full history clone containing peer findings. A checks specification and correctness; B checks standards, maintainability, failure, permissions and recovery. Both apply the required verification skills and preserve original candidate-bound assessments.

Use native completion events for these internal reviewer returns. Keep the worker paused while they inspect its checkout; use detached exact-candidate checkouts when tests create artifacts. Respect actual concurrency capacity and queue work without adding another pair. The worker repairs findings and obtains replacement assessments until both PASS. Existing reviewer panes/reports remain historical; do not interrupt or redo them to apply this profile.

After the first gate verdict, use [gate-stage repair review](controller-workflow.md#gate-stage-repair-review). Record the controller's actual-diff eligibility and amendment before a narrow direct return to the SAME gate. Preserve baseline pair identities; sensitive/broad repairs require the replacement pair. Existing unamended assignments keep their instructions and in-flight checks.

## Delivery and recovery

Use the existing [file-backed packets](controller-workflow.md#file-backed-packets) and [checked delivery](controller-workflow.md#checked-delivery) for worker/gate/controller messages. Full status belongs in the packet; the relay remains one line of at most 220 characters before the bridge envelope. Use the bound checked-send helper when verified, with its recorded state directory. Retain the specified settling waits and one post-Enter check.

A busy agent with an empty message composer can receive a checked send under the canonical empty-composer clarification. Preserve drafts and verify the submitted transcript or accepted queue. The current helper's idle confirmation cannot be set for a busy target; use the explicitly authorized checked Smux route and record its guard-coverage limit.

Goals do not fix missing pane identity, a foreign draft or uncertain submission. Preserve the frozen report and use the controller's explicitly authorized alternative when native delivery is unavailable. Do not fabricate a sender, blindly resend or stop independent authorized work solely because another pane is waiting.

## First-ticket proof

Record actual Goal activation and an automatic continuation while safe work remains; both built-in reviewer returns; candidate delivery; gate PASS; and controller integration checks. Also record a legitimate wait and any human intervention. Keep provider evidence separate from fixtures. This document creates no new hook, watcher, provider allowance or cleanup permission.

[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) describe separate contexts and model configuration. The [daemon environment contract](https://github.com/openai/codex/blob/main/codex-rs/app-server-daemon/README.md#platform-support) explains why pane-based clients use `--no-daemon`. Neither source proves activation in an existing lane.
