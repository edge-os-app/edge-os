# Choose an execution workflow

Documentation updated 2026-10-08 at the builder's request. The two profiles below are documented for selection and verification, not activated by this edit. Active tasks retain their existing packets, hosts, models, Goals and review histories.

| Profile | Procedure | Who continues the work | Transport |
|---|---|---|---|
| `tmux-goal` | [Existing lanes with worker Goals](tmux-goal-workflow.md) | Each Codex worker has its own ticket Goal; the controller handles dispatch and integration | Short file pointers between worker, gate and controller; built-in subagents for the two internal reviews |
| `native-batch` | [One Codex execution coordinator](native-batch-workflow.md) | One coordinator Goal covers an approved named batch | Native subagent returns, or recorded headless OpenCode results; no worker/gate pane typing |

Unamended active lane assignments continue under [controller-workflow.md](controller-workflow.md). A task without a recorded profile keeps that existing procedure. Do not silently convert it to either new profile. A new assignment must name its profile, document version, selected model route, continuation owner and actual activation evidence.

## Shared rules

[Upstream defects found downstream](controller-workflow.md#upstream-defects-found-downstream) applies to both profiles, including accepted integrated code. Preserve ownership, investigate/report exact evidence and obtain an explicit repair assignment before outside-scope edits. The selected transport changes delivery, not that boundary.

[Controller workflow](controller-workflow.md) remains authoritative for accepted prerequisites, evidence-first context, task ownership, TDD, original independent reviews, gate verdicts, technical acceptance, serial integration and authority. The selected profile changes context creation, continuation and transport only.

Exactly two independent internal assessments must PASS one committed candidate before the FIRST separate gate verdict. Subsequent repairs follow [gate-stage repair review](controller-workflow.md#gate-stage-repair-review), with an explicit amendment for an active task. Internal repairs have no numeric cap. Gate history retains its three-verdict limit across resumption or host changes. Keep one integration owner. Publication, main merge, provider operations, wallet access and spending retain their recorded authority boundaries.

Full instructions and results remain frozen file-backed packets in both profiles. The delivery mechanism depends on the profile. Pane-specific `/clear`, Smux and no-pane-polling requirements apply to tmux delivery; an explicitly selected native batch uses fresh child contexts and native completion events instead. Built-in internal reviewer returns are not cross-pane Smux messages. Neither profile adds another reviewer pair or scheduler.

Each frozen task packet records the ticket/specification, accepted base, branch/worktree, implementation owner, required research, owned/shared paths, checks, original report locations, gate counter, continuation objective and finish conditions. Keep transport identities and receipts outside the hashed report. The private controller ledger records live assignments; GitHub remains the shared ticket tracker under its publication permissions.

## Switch without losing work

Prefer a ticket boundary. Select the next ticket's profile in its packet and ledger, then verify that profile's prerequisites. The builder chooses the workflow; the controller performs the setup and routine coordination. One request to use a workflow is not permission to dispatch every ticket.

A capacity-driven change within a ticket requires a recorded, authorized handoff:

1. Save the candidate, dirty-state inventory, original reports, unfinished work, request counters, gate history and current Goal state.
2. Ensure the former implementer is no longer writing before another implementer uses its worktree. Ending a response alone does not stop an active Goal.
3. Preserve the same task scope and reviewed identities. A new host must prove its own context, model configuration and return path. Preserve existing pane model settings; newly launched agents use the assigned route.
4. Record which saved packet the new owner reads, the return destination, and how the prior owner will remain inactive using supported controls. Do not fabricate a completed Goal to suppress it.
5. Resume from the recorded next action. Host changes do not reset gate counts, provider budgets or failed evidence.

Do not switch because a report is awkward to paste. Repair the short pointer under the existing delivery procedure. If transport is broken, preserve the report and use an explicitly authorized truthful controller relay; never invent `TMUX_PANE` or silently change routes.

## Qualification before wider use

Run one approved ticket through the selected profile. Record actual continuation, original reviewer returns, gate delivery, integration checks and human interventions. A feature flag, installed skill or written procedure is not proof that the workflow works unattended.

The integrated hook pilot proves bounded Codex/Claude behavior, not every running lane or OpenCode. The headless native OpenCode route still needs its own qualification. A qualified Smux assignment does not prove the headless route. Preserve all active assignments, their verified local configuration and retained limits.
