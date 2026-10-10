# One Codex execution coordinator

Profile: `native-batch`. Prepared 2026-10-08 as a selectable alternative, not an activated batch. Read [workflow selection](execution-workflows.md) and the common [controller rules](controller-workflow.md). Existing pane assignments keep their owners and evidence.

## What changes

One Codex coordinator creates ticket worktrees, starts isolated workers, routes the two internal reviews and separate gate, and integrates approved candidates. Native results return to it without typing into worker/gate panes. The coordinator keeps one actual Goal for the named approved batch. Fresh children do not inherit that Goal, and this profile does not require competing Goals in every child.

Use Matt's `implement-spec` to schedule only that batch's dependency graph. Use selected pstack verification principles for executable success/failure checks; do not add a second scheduler. Both are adaptations under Edge OS rules, not claims that their unmodified workflows ran.

## Select a model route

| Route | Implementer | Internal reviewers | Independent gate | Return path |
|---|---|---|---|---|
| Codex | Luna, assigned effort | Two separate Sol contexts, assigned effort | Fresh Sol context | Native collaboration |
| OpenCode (headless route, requires qualification) | Explicitly approved DeepSeek Flash selection | Two separate GLM-5.3 Flash contexts | Separate Codex gate under the approved model policy | Headless processes with retained task/result files |

Codex remains coordinator for both routes. Keep existing pane settings unchanged. Exact OpenCode provider/model IDs, access, internal-reviewer selections and return behavior must be qualified before that route starts. These names are preferences, not installed configuration. Do not treat an external OpenCode model as a Codex native child or infer provider access from a model name.

## Prepare a batch and worktrees

1. Freeze an approved batch packet naming eligible tickets, specification/input versions, authority, selected route, owner, integration checkout and exact accepted base. Check active assignments to prevent duplicate dispatch. The controller owns these setup steps; the builder does not manually create each worktree.
2. Reuse `integration/edge-os-mvp`; do not create a competing integration owner. Recheck its current SHA and state rather than reuse a date-stamped example. Map shared migrations, contracts, registration files and lockfiles before parallel work.
3. Check that the proposed task branch and path are unused and belong to the intended repository. Create one ticket-named worker worktree from that accepted SHA. The form below is illustrative, not a runnable dispatch:

   ```sh
   git -C <repository-path> \
     worktree add -b ticket/<ticket>-native \
     <worker-worktree-path> \
     <verified-accepted-integration-sha>
   ```

4. Give each worker a frozen packet containing profile/route, exact base/path/branch, required research/skills, ownership, checks, result path and parent return identity. Preserve private evidence outside shared candidates.
   Apply [implementation names and skill selection](implementation-standards.md) to the required skill list and application filenames. Native dispatch does not waive those common implementation rules.
5. Pause the implementer during review. Reviewers may use its exact checkout or separate detached worktrees at the candidate. Tests need isolated ports, databases and output paths; a worktree does not isolate provider accounts or shared services.

Retain worktrees and evidence until integration and preservation are verified. Never use a hard reset, automatic rebase or forced cleanup to make an unexpected worktree fit. [Git worktree documentation](https://git-scm.com/docs/git-worktree).

## Activate the coordinator

The execution coordinator starts with a bounded handoff containing the approved batch, current state and next action. Preserve the planning/controller history; do not `/clear` the coordinator between tickets. A separate fresh execution thread is optional at the builder's direction, with exact workspace/model verification. A terminal coordinator using any retained pane transport must satisfy that transport's identity checks.

Use the supported Goal tool or native `/goal` to create the objective below after batch approval. Verify actual Goal state; a prompt alone is insufficient. Set a numeric Goal budget only when requested. Fresh child contexts replace pane `/clear` for this selected batch, not for unrelated legacy assignments.

```text
Complete only the approved tickets in <batch packet> using native-batch-workflow.md and the recorded model route. Delegate isolated implementation, obtain two independent internal PASS assessments on the initial gate candidate, route subsequent gate repairs under controller-workflow.md#gate-stage-repair-review and any active-batch amendment, obtain a separate gate PASS on the exact final candidate, integrate serially into integration/edge-os-mvp, and run required integration/final batch checks. Continue eligible named work and ordinary repairs without routine permission questions. Preserve active legacy assignments, evidence, original candidate identities, counters and scope. Finish only after <batch result> proves all assigned outcomes; report genuine blockers without claiming completion. No unapproved provider, wallet, spending, publication, deployment or main-merge operations.

Before every implementation, repair or review dispatch, inspect the current full skill catalog and select skills for that task under implementation-standards.md. Include explicitly requested applicable skills. Put each selected skill's exact instruction path, applicability reason, required references and checks in the packet. Read selected instructions before preparing guidance that depends on them. Require each agent to read its selected instructions before use and identify skills actually applied, adaptations and unavailable checks in its original result. Reuse the existing review assignments; skill selection creates no extra reviewer pair or gate.
Include Ponytail Lite in future implementation/repair packets under implementation-standards.md#ponytail-lite-in-future-prompts. Include its completeness checks in the existing review briefs. Preserve approved scope, safeguards and required tests.
```

The coordinator's Goal does not directly schedule an external OpenCode process or bypass capacity, permissions or host interruption. Record and recover those separately. [Official Goal behavior](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex).

## Execute one ticket

Apply [upstream defect routing](controller-workflow.md#upstream-defects-found-downstream) through native returns. The coordinator verifies defects and may grant the current worker a bounded repair after authority/lease checks. Child Goals or an earlier upstream PASS do not expand ownership or approve changed code.

Follow the shared [verification cadence](controller-workflow.md#verification-cadence) when preparing worker, replacement-review and gate packets. It controls when the task's verification skill runs; this profile changes transport, not that rule. Keep active frozen packets and in-flight checks intact.

1. Select a ready, incomplete ticket in the batch. Use fresh bounded native implementation context or the selected OpenCode process in its assigned worktree. Read the named sources before implementation choices. TDD and actual behavior verification remain required.
2. The implementer saves the candidate, commands, evidence and limitations in the frozen result and returns its pointer/hash. The coordinator verifies the returned artifact and exact commit; a tool/process exit alone is not completion.
3. Launch exactly two independent internal reviewer contexts. Give each the same base/candidate and accepted criteria without the other reviewer's findings. Apply the existing Matt checklist adaptation and evidence-verification stack. Save both original assessments, not implementer-written summaries.
4. Batch verified findings back to the implementation owner. Obtain a replacement commit and required candidate-bound reviews after repair. Internal rounds are uncapped.
5. When both PASS, launch the independent gate context on that exact candidate. It must be separate from the implementer and internal reviewers. Retain its verdict history across child/host replacement; at most three verdicts per assigned gate task.
6. Route gate findings to the implementation owner through [gate-stage repair review](controller-workflow.md#gate-stage-repair-review). Classify the actual returned diff and record the baseline pair/repair chain before a narrow direct return; sensitive or broader repairs retain replacement internal reviews. Apply standing controller technical acceptance only after exact-final-candidate gate PASS and own evidence inspection. Integrate serially and run affected checks. No unchanged passed candidate needs another routine builder acceptance.
7. Record the integration result and notify the worker through the selected return path. Start another eligible named ticket. After the batch, perform the required final integration-range review for cross-ticket behavior and record the result before marking the coordinator Goal complete.

If review capacity is full, finish/release the active implementation turn before starting the pair or queue reviewers. Do not create extra contexts to bypass capacity. Native completion notifications and supported child-result waiting are permitted for this selected batch. They do not authorize monitoring unrelated panes or moving branches.

## OpenCode returns

OpenCode documents `run` for non-interactive work, explicit `--agent`/`--model`, attached `--file` input and `--format json`. Confirm the installed version's syntax before use. Its model configuration is independent of Codex. [Official CLI](https://opencode.ai/docs/cli/#run), [agent configuration](https://opencode.ai/docs/agents/).

The coordinator records process/session identity, worktree, packet hash, exit status and the frozen result. Keep credentials and private account records outside prompts and shared logs. JSON output alone does not prove tests, candidate creation or review independence. Pilot the actual invocation/return path before allowing autonomous OpenCode batches; no such run is qualified by this document.

## Matt adaptation and switching

The installed `implement-spec` schedules the whole spec, updates worker bases, uses a merger child, performs final review and cleans up worktrees. Here the approved batch bounds dispatch; a single coordinator owns integration; required base updates happen before final candidate reviews; the initial pair and final gate precede every merge, with gate-stage repairs following the shared rule; and cleanup requires preserved evidence and exact authority. Installed skills stay unchanged.

Use the [switching procedure](execution-workflows.md#switch-without-losing-work) at a ticket boundary, or an authorized capacity handoff. Keep one writer per worktree. Changing from Luna/Sol to DeepSeek/GLM does not reset budgets or gate history. Do not migrate an active assignment merely to test this profile.

## Qualification record

Before expanding, retain a complete approved ticket's native/headless return, actual coordinator Goal continuation, original pair, separate gate, local integration and required final checks. Record human interventions and limits. The earlier private execution plan is a historical pilot proposal; this file supplies the reusable procedure, while the batch packet supplies live identities and authority.

[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) provide fresh contexts and configured models. The project requires a successful pilot; documentation and installed skills do not establish unattended reliability or OpenCode hook protection.
