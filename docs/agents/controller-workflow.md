# Controller and worker lanes

Adopted setup: 2026-10-06. Follow [the Matt workflow](../../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md) for implementation, models, reviews and acceptance. This document supplies the lane procedure. It does not approve a ticket, publication, merge or financial operation.

## Execution profile

Before preparing a new assignment or an authorized workflow handoff, read [execution-workflows.md](execution-workflows.md). It separates the prepared `tmux-goal` and `native-batch` procedures. Record the selected profile/version and activation authority in the packet and ledger. The new documents do not activate either profile or change an existing assignment.

This file remains the shared policy source for prerequisites, evidence, ownership, reviews, technical acceptance and integration. Its pane activation, Smux transport and return table govern existing lanes and `tmux-goal`. An explicitly selected native batch uses its documented fresh-child contexts and native/headless return path instead of those pane-specific steps. Built-in internal reviewer completion events are permitted in a selected profile; that exception does not authorize watching another lane or silently changing transport.

A selected Codex lane assignment must record its actual worker Goal and built-in reviewer route under [tmux-goal-workflow.md](tmux-goal-workflow.md), not assume that earlier native reviewer panes implement that proposal. Gates remain event-driven. Keep active packets and model settings intact until a recorded transition.

## Portable contributor use

Start with [contributor-workflow.md](contributor-workflow.md). A contributor uses their own clone or an assigned isolated worktree. They do not need the builder's private workspace, pane names, Goal-state files or subscriptions. Worker and gate templates are below; the [internal-review template](templates/internal-review.md) supplies the existing pair.

Record one return transport in the assignment. For a contributor without panes, use the assigned PR and original report attachments/files, with a controller-arranged separate gate. Substitute these destinations for pane fields and mark pane activation/Smux checks inapplicable. A native batch uses native returns; a Smux lane uses checked delivery. Do not silently switch an active assignment. These substitutions change transport, not accepted scope, review independence, exact-commit approval or authority.

The [dated P14 numerical assignment](../team/QUANT_CONTRIBUTOR_BRIEF.md#start-with-p14) permits the contributor to branch from latest main and record the actual base SHA himself. It permits proposed profile choices, independent calculations, code and tests in one bounded PR. No preliminary proposal return, controller-created checkout or separate profile approval is required for that PR development. Adopted defaults and saved-run compatibility remain intact. Shared wiring needs a later lease. Runtime adoption, full-ticket acceptance and main merge remain separate. Other tickets and active lanes retain their recorded procedure.

## Before dispatch

Use the [team handoff](../CONTROLLER_HANDOFF.md), accepted specification revision, linked ADRs and assigned GitHub issue. The private workspace maintains the live lane ledger. Required inputs must also exist in the teammate's checkout or issue.

Dispatch only accepted work whose blockers have passed. Record the integration SHA, branch, absolute worktree path, owner, owned changes, forbidden changes and required checks. A label or message alone is insufficient evidence.

### Controller technical acceptance

Builder clarification, 2026-10-07: for an already authorized ticket, the controller decides technical acceptance and local integration. Do not request another builder approval merely because implementation and reviews completed. This includes contract/documentation tickets that carry forward accepted requirements.

Verify the exact candidate, original internal PASS pair, independent gate PASS, scope and required checks. For a changed gate-stage candidate, verify either its replacement PASS pair or the recorded baseline pair plus authorized narrow-repair evidence under [gate-stage repair review](#gate-stage-repair-review). Inspect the implementation against the ticket. If no verified blocker remains, accept the bounded output and integrate it serially into `integration/edge-os-mvp`. Run affected integration checks and record the result. Treat that accepted output as a prerequisite only within its proved scope.

Escalate an unresolved product/architecture decision, missing required evidence, conflicts or a genuinely unauthorized operation. Gate PASS cannot settle an unapproved product choice. This standing authority does not dispatch unassigned tickets, publish local artifacts, merge main, buy services, deploy or grant financial permission. No extra controller-gate review is required for unchanged gate-passed integration.

The repository contains a runnable fixture-backed application. See the [README](../../README.md#current-status) for its dated implementation status and qualification limits. Repeatable startup, checks, saved-record inspection and cleanup are required for the assigned behavior. Local fixture passes do not prove live providers, signing, funded execution or production readiness.

### Upstream defects found downstream

Builder-approved clarification, 2026-10-10. This applies when a worker or reviewer discovers a defect in a dependency, including code already gate-passed, integrated or published. An earlier PASS records the reviewed candidate and evidence. It does not override a newly verified blocker.

1. Investigate before escalation. Check accepted requirements, exact dependency commit, affected callers and the downstream assumption. Reproduce with existing authorized local checks or isolated fixtures. Keep provider, wallet and financial limits unchanged. Distinguish a product defect from a verifier failure, unsupported input or mistaken expectation.
2. Fix defects within the current assignment's owned paths through its normal repair/review process. For an upstream path outside that ownership, preserve the upstream bytes. Propose the smallest repair without applying it there. Continue unrelated safe work.
3. Send the controller a frozen defect packet through the selected transport. Include task/defect identity, upstream and downstream SHAs, affected paths, expected versus actual behavior, reproduction command/input/result, affected requirement, downstream impact and proposed repair. Label an unreproduced concern as unverified. Name the blocked action and independent work that remains safe. Use the normal short path/hash pointer and checked delivery for Smux.
4. The controller verifies the finding and records affected prerequisite/acceptance status. A demonstrated blocker prevents the affected merge, qualification or release claim. Preserve earlier reports as history with a linked defect notice. Do not reopen every unrelated ticket or repeat unaffected checks.
5. Before source repair, the controller checks authority, active writers, leases and shared-path conflicts. It may assign the same downstream worker when safe. A separate worker is not automatic. Issue a versioned repair assignment or continuation with exact base/worktree/branch, owned paths, unchanged behavior, selected skills, regression/submission checks, review route and return identity. Coordinate an existing owner's release before overlapping writes. Existing batch authority must cover the repair; new product choices, unsupported scope or financial operations require builder direction.
6. Add a regression check that reproduces the verified defect before the fix when executable behavior is involved. Preserve validation, error handling, contracts and recovery semantics. Verify the repair and affected unchanged callers. An already-integrated upstream defect normally receives two independent internal PASS assessments and a separate gate on its exact repair candidate. The narrow gate-stage shortcut applies only to an eligible repair requested by an active gate under its recorded amendment. Prior upstream PASS reports alone cannot approve a new fix.
7. Preserve review identities and counters. A distinct regression discovered after completed acceptance can have its own bounded repair identity and fresh gate history. Do not rename the same unresolved finding, reset an exhausted gate or use a new task to evade its three-verdict limit. A gate still handling the same task retains its history.
8. Integrate the approved repair serially. Run affected integration checks and record the resulting SHA. Send an explicit downstream continuation naming the corrected dependency and any base reconciliation. Do not silently rebase or change an active candidate. Changed downstream commits require the applicable candidate-bound checks/reviews. Resume the affected path only after its blocker is resolved.

This rule permits investigation and explicit repair routing, not edits outside an assignment. It grants no rollback, destructive Git operation, publication, deployment or financial authority. Apply it in new packets and the next necessary continuation. Preserve active frozen packets, reviews and in-flight work until a recorded amendment is delivered. Reviewers remain read-only.

### Verification cadence

Builder-approved, 2026-10-09. This rule applies to both execution profiles and the task's verification skill, including `verify-edge-os` when present. Match checks to meaningful changes and submission boundaries, rather than a timer or every edit. Preserve all accepted criteria, two original independent internal assessments, the separate gate, uncapped internal repairs and the gate's three-verdict limit.

| Stage | Required verification |
|---|---|
| Implementation | Use behavioral RED/GREEN and focused checks for each meaningful change and its affected callers, invariants and failure paths. Debug a test selector or assertion with the smallest relevant test/browser drive before repeating the complete startup/build/database/restart recipe. |
| Candidate submission | Run the complete task-required recipe on the clean committed candidate before submitting it for internal review. Inspect actual saved records, rendered behavior, restart, scans and cleanup where the task requires them. Preserve exact candidate, configuration, fixture and input identities. |
| Independent review and repair | Each reviewer and gate independently inspects the candidate and verifies the assigned behavior. Reproduce findings and check affected behavior during repair; run the complete task-required recipe on the repaired committed candidate before resubmission, not after every intermediate edit. Execute checks explicitly assigned to that reviewer or gate; supplied evidence inspection must not be described as their own execution. |
| Integration | Run affected integration checks on the resulting commit. Run the required combined batch/release verification and final review at their assigned boundary. Candidate evidence alone does not prove cross-ticket integration behavior. |
| Verifier maintenance | While development is active, check the feature map and executable recipe at least daily and whenever a relevant application path changes. Correct stale routes, fixtures, assertions or instructions and validate the affected checks. Daily maintenance does not require a full application run when nothing relevant changed, and authorizes no new scheduler, provider call or financial operation. |

Reuse intact evidence for an unchanged candidate and unchanged tested inputs/configuration by inspecting its coverage and identities. Do not repeat identical commands solely to obtain another copy of the same result. A changed commit needs candidate-bound review through the route in [gate-stage repair review](#gate-stage-repair-review); previous PASS reports never approve later edits. Changed code, fixtures, configuration or test logic needs fresh evidence for affected behavior, plus the complete submission checks above. Review independence and any explicitly assigned own execution remain required.

When a broad run fails in its verifier, preserve the failed run and diagnose the verifier through a focused reproduction before restarting the broad run. Keep instrumentation errors separate from product failures. Do not remove a failing assertion, narrow acceptance, hide a known blocker or substitute a component check for required mounted persistence/browser proof. If isolation cannot reproduce the boundary, document why a broader run is needed. Cleanup of each run's exact owned resources remains required even when its checks fail.

Record start/end or elapsed time, command/run identity, exit status, phase and reason for each full run or rerun in existing evidence. Use the recipe's own timing output when available; no new monitoring service or reporting layer is needed. The controller distinguishes necessary independent/submission proof from avoidable setup, assertion and administrative repetition.

Apply this cadence in new packets and the next repair/review dispatch. Preserve frozen packets, completed runs and original verdicts. Do not interrupt an active run, change its recorded required checks or claim retroactive compliance. This amendment changes verification scheduling, not task scope, models, authority, acceptance criteria or review layers.

### Gate-stage repair review

Builder-approved, 2026-10-10. Before the FIRST gate verdict, obtain both original independent internal PASS assessments on one clean committed candidate. Internal-review repairs continue through the same pair until both PASS; this rule changes only the route AFTER a gate requests repairs.

| Gate-requested repair | Required route |
|---|---|
| Narrow layout, wording or isolated implementation fix within already accepted behavior | Worker repairs and runs required checks; the SAME gate reviews the complete repair diff, affected behavior and resulting exact candidate. Replacement internal assessments are not automatic. |
| Authentication, authorization, permissions, signing, financial/accounting behavior, migrations, shared contracts or security controls | BOTH independent replacement internal assessments on the repaired candidate, then the SAME gate. A small diff does not make a sensitive change eligible for the narrow route. |
| Broad repair, changed requirements or invalidated baseline review assumptions | Controller reassesses affected scope and authority; obtain the required independent replacement reviews before the SAME gate. Resolve new product choices through the builder. |

The controller records eligibility from the ACTUAL completed diff, not the proposed fix or file count. A narrow repair must address the gate's named findings, preserve accepted behavior/interfaces and contain no unrelated changes. Regression fixture/test/map edits qualify only when they preserve accepted inputs and expectations and add coverage; changing an oracle, weakening an assertion or redefining acceptance requires wider review. Inspect affected unchanged callers and interactions when the diff could alter them. Repeated findings that expose a broader missed defect class require wider review. Gate-authored implementation changes require independent replacement review; a gate cannot approve its own edits.

For the narrow route, retain the original pair's baseline SHA/tree, original reports/hashes, gate findings, full repair range/new SHA/tree, finding-to-fix mapping, affected tests, complete required committed-candidate submission evidence and the controller's eligibility decision. The gate checks eligibility independently, closure of every finding, regressions in changed behavior and affected invariants, and gives PASS only for the exact resulting candidate. Earlier PASS reports remain baseline evidence, never rewritten as approvals of later commits. Missing eligibility, changed scope or insufficient evidence returns the work to the wider route; it cannot become a waiver.

Keep the SAME gate and its existing three-verdict counter. No new gate layer, reset, model change, internal-round cap, test waiver, integration shortcut or financial authority follows. Required affected integration checks and distinct final combined review remain. Apply through new packets or a recorded continuation/addendum for an active task; preserve old frozen packets/reports and in-flight checks. An active batch's exact-candidate-pair completion wording must explicitly record this amendment before using baseline-pair plus final-gate proof. Unamended active assignments keep their recorded route.

## Approved autonomous batches

The builder requested autonomous execution on 2026-10-07. Use this procedure instead of asking whether to continue after every routine step. A batch must identify its accepted tickets and authority before it starts. Approval of the ticket graph alone does not assign all 43 tickets.

Record one batch entry in the live controller ledger with:

- Batch identity, named tickets or bounded stages, queue priority, accepted specification and required inputs. Record the builder's dispatch authorization separately from scope approval or a proposed queue.
- Exact integration branch/worktree and starting SHA.
- Maximum active lanes, disjoint ownership and dependency rules.
- Allowed local operations, publication/tracker permissions, host-switch permission and any bounded controller-handoff permission.
- Record the standing controller technical-acceptance rule and any explicit batch exceptions. New product decisions still need builder approval.
- Internal review history without a numeric round cap, the separate three-verdict gate limit, any explicitly approved batch end time or run limit, and stop/report conditions.

Missing authority blocks only the affected action. Continue other eligible work in the approved batch. Do not infer paid-provider, wallet, trading, deployment, publication or main-merge permission from general autonomy.

### Event-driven continuation

Builder-approved clarification, 2026-10-10: for the Smux lane route, the running controller handles incoming gate returns without a polling Goal. Worker Goals continue their assigned work; gates remain event-driven. This does not replace the coordinator Goal in a selected `native-batch` route.

1. Select an eligible, incomplete ticket from the approved batch. Check the ledger so completed or active work is not assigned twice.
2. Prepare its isolated worktree and fresh worker/gate contexts under the activation procedure below.
3. Run implementation and repeat independent internal reviews until both PASS on one exact candidate before the first gate verdict. Route later gate repairs under [gate-stage repair review](#gate-stage-repair-review). Internal rounds have no numeric cap; the separate gate retains its three-verdict limit.
4. On a gate PASS, verify the exact candidate and required evidence. Apply only the batch's recorded technical-acceptance authority.
5. Integrate authorized candidates serially into the named integration branch. Run the affected integration checks and record the resulting SHA.
6. Return the outcome through gate to worker using checked delivery. Record delivery separately from the worker's completion and safe task release.
7. In the same event-handling turn, check the authorized queue, accepted prerequisites, active ownership and shared-file leases. Prepare and dispatch the next eligible ticket without another routine builder approval. Do not end after integration while safe, authorized dispatch work remains.
8. Before reusing a lane, verify that its former task is inactive and its checkpoint, evidence, outbound delivery and actual Goal state are preserved. Use fresh-session activation for the new worker and gate. On OpenCode use the verified native `/new`; on current Codex/Claude lane clients use native `/clear`. Preserve model settings, worktrees and this controller conversation. Verify the new task's actual activation before claiming it is running.

If previous-task release, required authority, capacity or safe delivery is unresolved, save the pending next action and await the relevant event. Do not reset the active task to free its lane. A duplicate return must not repeat integration, dispatch or financial effects; verify its recorded identity and continue only unfinished authorized coordination.

When no authorized ticket is ready, leave the controller and unused gates in standby. A checked incoming message starts the next coordination turn while the controller client and host remain available. Skills describe the procedure; they are not a background scheduler and cannot wake an exited client. Do not add recurring pane checks, status prompts or an always-active Goal merely to wait. Useful dispatch and review turns still consume usage; this policy promises no measured credit saving.

Leave a waiting lane in event-driven standby. When a ticket is blocked, preserve its candidate and evidence and continue independent eligible tickets. Stop the batch when it completes, its limit is reached, the builder interrupts, or no authorized path remains. Report the specific blocked action and decision needed, not routine progress pings. An explicitly approved run/provider limit or exhausted capacity can block affected work; internal repair rounds have no numeric cap.

Controller technical acceptance is not a fabricated builder review or human-comprehension pass. Main remains behind the manual merge policy unless the builder separately changes it. Do not add another controller-gate round for unchanged, already gate-passed integration. New edits require candidate-bound approval through [gate-stage repair review](#gate-stage-repair-review) when eligible; other changes require independent replacement review.

### Delivery completion and recovery

Save the report and outbound message identity before notification. Each outbound ledger entry names the task/event, candidate, sender, destination, exact message or its saved path, and delivery state. Use PREPARED, TYPED, SUBMITTED, UNCONFIRMED or BLOCKED. Record recipient completion separately from message submission.

A typed message is unfinished work. Complete its verified Enter/submission sequence before ending the sender turn. On resumption, a saved TYPED entry permits one safe recovery check. Submit only if the visible input exactly matches that agent's saved unsent message and submission was never attempted. Preserve a different draft or uncertain submission and report the obstruction. Never blindly resend a message, overwrite user input or duplicate work from a repeated notification.

Every controller, worker and gate must read the destination before typing, after typing and once after Enter. These are delivery checks, not permission to monitor progress. Confirm the exact destination and message at each stage under the procedure below.

### Safeguard qualification

Documentation alone cannot wake a stopped client or guarantee that an agent presses Enter. Automatic SessionStart binding, checked delivery and Stop tooling are accepted at candidate `ce7453a813cbbfe93e51aa2c9d014ecdbd086b06`, integrated locally at `68cde4d1500c2c0aacdbb75639c4213f40b83092` on 2026-10-08. This does not establish a trusted binding or delivery protection for existing running lanes. Use the published [controller guard instructions](controller-guards.md) for future managed activation, with exact receipt and shared-state verification before dispatch. Clipped or collapsed input remains a delivery obstruction; native fork and compaction remain unqualified. Record actual session receipts and checks before claiming protection. No active lane is reset by this status update.

Later bounded native proof and parser repairs were accepted and integrated at `556b43e2dded8a7a197fe96b9abf788ffbe6a65d` on 2026-10-08. Both original internal reviews and gate PASS1/3 were verified; guard96 and affected integration checks passed. Reviewed Codex/Claude controls include missing-evidence Stop correction, recorded missed-Enter recovery, bounded delayed-display checks, duplicate zero-action and foreign-draft preservation. The installed workspace commands already reference the integration helper, whose bytes changed with integration; fresh native invocation of that replacement and all running lane bindings remain unverified. OpenCode protection is unqualified. Preserve proof-time hook/CLI hash distinctions rather than treating file deployment as runtime evidence.

If a delivery-completion guard is implemented, reuse the ledger and the verified Smux procedure. It must check for missing required reports, a TYPED-but-unsent message, or eligible authorized work abandoned without a reason. Permit legitimate waiting for an incoming event, blocked input, exhausted authority/budgets, run limits and user interruption. A guard must not repeatedly wake a model while another pane works.

Before enabling a guard, test normal delivery, a forgotten Enter, a different user draft, ambiguous submission, a duplicate event, legitimate standby and an exhausted budget. Use current official host-hook documentation during implementation. Do not claim unattended operation until the guard and batch continuation are exercised. Client crashes, host sleep and subscription exhaustion remain operational limits. A skill is a procedure, not a persistent scheduler.

Borrow fresh task contexts, durable progress and continuous execution of approved work from Superpowers. Keep Edge OS's separate worktrees, two original internal reviews, gate, model policy and gate limit. Do not import automatic stronger-model escalation, extra gate rounds, scratch deletion or a second review/orchestration stack. Pin the inspected source version before adopting executable skill behavior.

## Worktree layout

The table illustrates the builder's local layout; it is not a required contributor directory structure. An independent clone has its own absolute paths. The assignment records the actual repository and worktree. Local worktrees should be kept outside the application checkout:

| Role | Path relative to the private workspace | Branch |
|---|---|---|
| Integration | `.worktrees/edge-os/integration` | `integration/edge-os-mvp` |
| Worker 1 | `.worktrees/edge-os/lane-1-worker` | Idle initially; controller assigns a ticket branch |
| Worker 2 | `.worktrees/edge-os/lane-2-worker` | Idle initially; controller assigns a ticket branch |
| Worker 3 | `.worktrees/edge-os/lane-3-worker` | Idle initially; controller assigns a ticket branch |

Panes named `edge-os-controller`, `edge-os-controller-gate`, `edge-os-worker-lane-N` and `edge-os-gate-lane-N` are message destinations. Separate panes do not isolate Git changes. Before writing, each worker checks its actual path, branch, HEAD, base ancestry and clean state against the assignment. Repeat this check on resumption and after a branch change.

Only the controller prepares a persistent lane for its next ticket. Check cleanliness and the previous candidate's integration state first. Never reset a lane, remove a worktree or rebase active work as routine cleanup. If its base becomes stale, pause and resolve the integration plan before changing it.

### Read-only shared-checkout context

When a referenced document is absent or additional context is needed, inspect the shared checkout before reporting a blocker.

1. Read the packet's shared-context checkout and accepted-context SHA. The assignment supplies the actual path; a contributor clone does not require another host's checkout.
2. If the path is absent, run `git worktree list --porcelain` from the assigned worktree. Identify the primary checkout. Compare each checkout's `git rev-parse --path-format=absolute --git-common-dir` result before treating it as the same repository.
3. Search only task-relevant documents with `rg --files` and `rg`. Read the primary checkout's AGENTS, current handoff and relevant workflow amendments. These reads require no new permission on the builder's local host.
4. Read accepted requirements with `git show <accepted-context-SHA>:<repository-relative-path>` from the assigned worktree. Record that SHA/path. This reads shared Git objects without changing branches.
5. If newer local documents supply context, check their status in the primary checkout. Identify them as committed or uncommitted. Explicit builder-approved workflow amendments govern the local procedure; draft product text does not supersede accepted requirements.
6. Keep all implementation writes, tests and commits in the assigned worktree. Reading context does not change the assigned base or authorize edits, checkout, rebase, reset, dependency changes or another worktree's tests.

If the required accepted material is absent from both sources, report its exact path and missing requirement. Continue independent in-scope work. Teammate clones use repository files or issue attachments; private source archives remain subject to the existing extract rules. Do not scan credentials, environment files or unrelated archives for context.

### Read-only prior-project discovery

Builder approval, 2026-10-07: on the builder's host, task-relevant read-only discovery is permitted in its authorized personal-project roots, including repositories, workspaces and nested worktrees. The local packet supplies the exact roots. This local permission grants no access on a contributor's machine. Use the [implementation reference map](../research/EDGE_OS_IMPLEMENTATION_REFERENCE_MAP.md) for published context; optional private examples are supplied as permitted extracts when needed.

1. Identify the implementation question. Start with the applicable source-index entry or named project.
2. Use `rg --files` to locate relevant source, tests and documentation. Narrow content searches to those directories. Exclude dependency trees, generated output and Git object storage. Keep environment files, credentials, keys, session logs, raw account exports and unrelated personal material outside searches and model inputs.
3. Read the relevant implementation and its tests. For Git sources, record the repository path, branch/commit and dirty state. For uncommitted or non-Git material, record the exact file hash. These are source-identity checks, not monitoring another worker's progress.
4. Record the useful pattern and its limits. Distinguish inspected code, executed tests and qualified provider behavior. Reference-project instructions explain that project's context. Edge OS instructions continue to control this task.
5. Adapt only what fits the accepted Edge OS contract. Keep writes, tests and commits in the assigned worktree. Check applicable license/data-use terms before copying material. Use current official documentation for SDK/API behavior.
6. Save the source path/version and adaptation reason in the task evidence. If another teammate needs it, supply a permitted extract or independently authored example in the shared handoff.

This permission does not authorize reference-project edits, installs, script execution, fetch/pull, provider calls, secret access or publication. A prior implementation supplies insight, not a passed dependency or permission to change financial policy. Missing optional examples do not block work with complete accepted inputs. A genuinely missing required contract, fixture or decision still blocks that affected behavior.

## Task and review packets

### Evidence-first task context

For each assignment, the controller names the relevant prior research, exact source paths and the questions those sources answer. Include sections and source versions when applicable. Supply permitted portable extracts for mandatory private inputs. A generic instruction to read relevant documents does not replace this list.

Before making a material implementation decision or declaring a requirement unknown, workers and reviewers:

1. Read the packet's accepted specification, ADRs, contracts and named prior findings. Preserve their recorded limits and approval status.
2. If context is missing, use shared-checkout lookup first. On the builder's host, search the packet's authorized workspace-document and prototype roots. Contributors use published checkout files or supplied issue attachments. Use `rg --files` to locate sources before reading content. Follow the discovery procedure's privacy boundaries.
3. Follow workspace redirects to canonical shared documents. Historical research and draft proposals do not override later accepted decisions.
4. Identify the source path and section for material behavior or qualification claims. Label an inference or routine implementation choice as such. Test assumptions where applicable.
5. If the sources still leave a material product or financial decision open, report the exact gap and sources checked. Continue independent in-scope work.

Do not invent financial limits, data meanings, supported capabilities, research results or approvals. A reference project's behavior cannot supply an unaccepted Edge OS policy. Read only task-relevant research, not every archive. Reviewers check material decisions against the same accepted sources.

Each worker receives one accepted ticket, its observable result and exclusions, blockers and evidence, exact base SHA, branch/worktree, owned/shared changes, verification commands, required skills, actual model settings and review budget. Shared schemas, migrations, lockfiles and configuration cannot have concurrent owners. Start fewer workers when those dependencies prevent safe parallel work.

Select and explain required skills under [implementation names and skill selection](implementation-standards.md). Include responsibility-based application filenames and relevant design/language/domain checks in worker and review packets. Read selected skills before use; preserve the review layers and operation limits.

Every pane assignment also names the task identity, controller/reply pane and worker/gate destinations. Carry those destinations into replacement sessions. Use the message envelope's actual sender pane as the reply route unless the packet explicitly assigns another recipient. A missing reply destination is an incomplete handoff.

For batch work, include the batch identity and ledger path, remaining run/review limits and exact acceptance/integration authority in each worker/gate packet. Otherwise record single-ticket authority. A fresh session must recover authority from this packet, not the prior conversation.

Include a task-specific required-input list using the [implementation reference map](../research/EDGE_OS_IMPLEMENTATION_REFERENCE_MAP.md), accepted specification/ADRs, contracts, fixture/source versions and runtime-verification recipe. The builder's controller checks relevant private workspace references before dispatch and supplies the permitted verified extracts or independently authored examples. Teammate workers use checkout-relative files or issue attachments; missing private inputs block the affected claim rather than trigger guessing. For Privy/auth work, require current official docs through Context7 and Exa, with the selected key/session assumptions recorded. Avoid assigning every course or unrelated project to every task.

Include the shared-context checkout and accepted-context SHA in each local packet. A missing worktree copy triggers read-only context lookup above, not immediate escalation.

Local packets also point to read-only prior-project discovery and the source index. Workers may find relevant examples without another controller request. Keep required portable inputs distinct from these optional local references.

### Fresh-session activation

Start each new ticket in fresh worker and gate sessions. The controller performs this procedure before sending either activation packet:

Prepare the wording under [model-aware dispatch prompts](dispatch-prompt-profiles.md). Select guidance from the observed host/model, then finalize the packet after the post-reset model check. Record the selected profile and source date. Lane numbers do not select providers. Keep task/review authority unchanged.

#### Preserve pane model selections

Builder correction, 2026-10-07: inspect existing worker/gate model, effort and speed. Preserve the builder's selections. When they already match the assigned role, proceed without opening a model picker or changing settings.

Recheck after native reset. If the client changes the selection, record the before/after values and report that specific activation mismatch. Change pane settings only when the builder explicitly requests that change. Dispatch permission, operating defaults and a reset mismatch do not authorize automatic correction. Keep independent permitted preparation moving while the mismatch is resolved.

This restriction covers existing pane settings, including session-only changes. It does not remove the worker's obligation to launch fresh internal reviewers with the prescribed model. Preserve current task packets and evidence. Do not interrupt or reset an active task merely to enforce this amendment retroactively.

#### Activation sequence

1. Confirm the previous task is inactive and its state is saved. Preserve its candidate, reports and unresolved work.
2. Verify the assigned worktree, branch, base and pane identities. Read each destination before interaction.
3. Confirm the pane has no unsent draft, active command or unfinished agent task. Preserve any such input. Report blocked activation.
4. For the current Claude Code and Codex lane clients, run native `/clear` before each new ticket's activation packet. P01 verified this command in both clients. Confirm support in the actual client and record its source in the dispatch ledger. A different host requires its verified native equivalent, not a guessed `/clear` or `/new`.
5. Enter native `/clear` through key input, never `tmux-bridge message`. After the pre-send read, use `tmux-bridge keys <pane> / c l e a r`. Read the pane to confirm that its input is exactly `/clear`. Then use `tmux-bridge keys <pane> Enter`. Read once to confirm execution. The message envelope must never be part of a native slash command.
6. Confirm the fresh context and actual host/model/effort before packet delivery. Preserve pane settings under the rule above. Record unavailable settings or a reset-induced mismatch. Pause affected delivery if required identity, fresh context or role compatibility is unresolved, without silently changing the model.
7. Deliver the complete activation packet through the Smux procedure below. The gate then remains in standby for the worker's exact candidate.

Record the activation evidence in the ledger. These are pre-dispatch checks, not progress polling. A fresh session changes neither Git state nor review budgets. Do not clear an active task to repair transport. A same-ticket context replacement instead needs a saved handoff and resumption checks.

The controller performs `/clear` before sending the task. The worker and gate verify the recorded activation; they do not repeat `/clear` from inside the active assignment. A refusal while working does not invalidate a controller-verified reset that already occurred.

When explicitly assigned to build or repair activation tooling itself, the task packet must identify its bootstrap preconditions. A receipt that the task is implementing cannot be required before that implementation exists. This is a named tooling-task exception only, not permission to claim an unbound session is protected or to skip receipt/native-trust verification for later ordinary assignments.

Apply this reset to both worker and gate before every new ticket, including consecutive tickets in an autonomous batch. Recheck actual model/effort after the reset because it can change the client's selection. Same-ticket repair rounds do not receive a routine `/clear`.

### Worker activation packet

Adapt the inspected OKX/TX Odds input, authority, preflight and proof patterns through this one template. The controller fills every field before dispatch; template placeholders are not a ready assignment.

Apply [skill discovery and packet checks](implementation-standards.md#select-relevant-skills-before-every-dispatch) before filling either template. The ledger records the current catalog source/date, template reference and selected-workflow substitutions. Use the approved native profile for transport-specific fields when applicable.

```text
Implement only accepted ticket <issue> from specification <revision>.
Packet identity/version: <task/event/version>. Read the complete saved packet and verify the SHA256 supplied in its relay before acting.
Execution profile/version and activation authority: <existing lane procedure or explicitly selected profile/document revision>.
Authorized batch/queue and task-release evidence: <ledger identity and dispatch authority, or standalone assignment>. Controller schedules subsequent tickets under event-driven continuation; the worker does not self-dispatch.
Continuation owner/mode: <this Codex worker Goal for tmux-goal; parent coordinator Goal for native-batch; recorded existing setup otherwise>.
Goal objective, finish criteria and state evidence path: <filled from the selected profile, or explicitly not applicable>. Actual Goal activation is required when assigned; prose alone is insufficient. No new numeric budget unless requested.
Internal reviewer transport: <two built-in independent subagents for a selected new profile; existing assigned route otherwise>. Preserve both original reports and the separate gate.
Observed host/model/effort: <confirmed configuration>. Prompt profile and guidance date: <matching profile/date>.
Preserve existing pane model/effort/speed. Change them only on explicit builder instruction. Select prescribed models only for newly launched internal reviewers.
Use the assigned worktree <absolute path>, branch <branch> and base <SHA>.
Read AGENTS.md, the current handoff, linked ADRs and these required inputs: <paths/versions>.
Relevant prior research: <exact paths, sections/versions, questions answered and retained limits>. Follow evidence-first task context before declaring a requirement unknown.
Shared context checkout: <absolute path>. Accepted context: <SHA>. Read missing/newer context under the read-only lookup procedure.
Read the applicable implementation-reference-map rows; missing mandatory input blocks that claim.
For prior implementation patterns on the builder's host, use read-only prior-project discovery and its source index. Keep required teammate inputs portable.
State briefly what changes, what stays unchanged and what observable result proves completion.
Use /implement and task-relevant skills <names>; use current Context7 docs and Exa where required.
Use Ponytail Lite under implementation-standards.md#ponytail-lite-in-future-prompts alongside Karpathy and task-specific skills. Record its current instruction path and actual use. Deliver the smallest complete change without reducing scope, required checks or safeguards.
Required-skill applicability: <selected skill names/instruction paths, task concerns, required references/checks and project-specific adaptations under implementation-standards.md; catalog audit recorded in ledger>.
Application module/file responsibilities: <descriptive filenames or justified existing/framework/contract names>. Update affected references for any rename; preserve exact reviewed candidates.
Owned changes: <surfaces>. Shared/forbidden changes: <surfaces>. Coordinate before crossing them.
Upstream-defect route: follow controller-workflow.md#upstream-defects-found-downstream. Investigate and propose out-of-scope repairs, report exact reproduction/impact to <controller>, continue independent work and wait for explicit path ownership before upstream edits.
Implement the accepted success and failure behavior; use TDD at <agreed seams>.
Run <actual tests and runtime recipe>; inspect <saved records and side effects>.
Verification cadence: follow controller-workflow.md#verification-cadence. Name focused development/repair checks, complete committed-candidate submission checks and required independent review/integration checks; avoid full runs for each intermediate edit.
Gate-stage repair route: follow controller-workflow.md#gate-stage-repair-review. Record baseline pair, current gate counter and authorized amendment for an active task; controller classifies the completed diff before narrow direct return.
Retain evidence under <path>, including exact build/fixture identities and unavailable checks.
Record full-run timing, phase and rerun reason in existing evidence; separate instrumentation failures from product failures.
Update the verification recipe/feature map when the implemented path changes.
Produce a clean candidate. Before first gate submission, read Matt's code-review and use the adapted Matt internal review procedure below for exactly two native reviewers under the approved host policy. Later gate repairs follow the recorded gate-stage repair route.
Retain both original reviewer assessments under the original-reviewer-reports procedure below.
Send <gate pane> the candidate SHA, checks, evidence and limitations. Await acceptance.
Send replacement candidates directly to <gate pane>. Follow the required return-delivery table for controller escalation.
Keep ordinary internal-review findings in the worker's uncapped repair loop. First gate submission requires both original internal PASS assessments on that candidate; later gate repairs follow the recorded gate-stage repair route. Before escalation, read named sources, use shared-context/prior-project lookup and run safe diagnostics; save the exact failed operation, checked evidence, remaining safe work and required decision. Escalate a genuine authority, capacity, external-budget, approved run-limit or unsafe-delivery obstruction; confusion or an internal round count alone is not an obstruction.
Freeze the full report first. Send one single-line path/hash pointer, at most 220 characters before the bridge envelope. Put candidate, findings and limits in the file, not the composer. Keep delivery notes in a separate file.
Confirm submission with its one post-Enter read, then await an incoming Smux message. Do not poll for progress.
After controller acceptance returns through the gate, save the final checkpoint, integration evidence, actual Goal state and task-release status at <path>. Complete the assigned Goal only when its criteria and lifecycle permit. Preserve closed/cancelled history; do not create or resume a Goal merely to wait. The controller resets a safely released lane only for a new authorized ticket.
Task authority: <explicit allowed operations/budgets>. No main merge or unrelated external action.
```

### Gate activation packet

Send the gate a filled review packet after fresh-session activation. The gate's own review must apply the required stack; checking the worker's reports alone is insufficient.

```text
You are the independent Edge OS gate for <task/issue>.
Packet identity/version: <task/event/version>. Read the complete saved packet and verify the SHA256 supplied in its relay before acting.
Execution profile/version, activation authority and return transport: <filled for this assignment>. Remain event-driven; no gate Goal that polls or repeats verdicts.
Authorized batch/queue and previous-task release: <ledger identity and verified release evidence, or standalone assignment>. A new ticket gets fresh activation; the SAME ticket retains its gate history. The controller owns next-ticket scheduling.
Observed gate host/model/effort: <confirmed configuration>. Prompt profile and guidance date: <gate's matching profile/date>.
Preserve existing gate model/effort/speed. A reset mismatch is reported, not automatically corrected.
Use general-review-protocol, then review-verification-protocol, code-reviewer and code-review-excellence.
Load task-relevant review skills <names/instruction paths and applicability reasons, selected from the current catalog>. Keep reviewers read-only.
Apply implementation-standards.md to naming and relevant domain checks; record actual skills and adaptations without adding reviewers or scope.
Apply its Ponytail Lite completeness and minimality checks. Preserve required safeguards and checks; a simpler alternative alone is not a blocking defect.
Read AGENTS.md, this lane procedure, the accepted ticket/specification/ADRs and <required inputs/versions>.
Read named prior findings <paths/sections/versions>. Check material decisions against those sources under evidence-first task context.
Assigned base: <SHA>. Review checkout: <absolute path>. Owned scope: <surfaces>.
Worker destination: <verified pane>. Controller/reply destination: <verified pane>.
Acceptance criteria: <observable results>. Required checks: <commands and evidence>.
Verification cadence: follow controller-workflow.md#verification-cadence. Name the gate's own checks and supplied evidence to inspect; preserve required independent execution without automatically duplicating every worker command.
Gate-stage repair route: follow controller-workflow.md#gate-stage-repair-review. On a narrow repair, verify original baseline pair, amendment/eligibility, complete repair range and required new evidence; approve only the resulting exact candidate.
Review policy: uncapped internal repair/review rounds; independent gate at most three verdicts. Retained history: <internal rounds completed and gate counter>.
After initial activation, remain in standby until the worker delivers an exact committed candidate and both original internal PASS assessments. A same-task repair continuation follows its recorded gate-stage repair route without resetting the gate.
Do not inspect a moving worker branch or monitor its internal reviewers.
On candidate receipt, verify ancestry, scope and both original assessments' candidate binding. For an authorized narrow gate repair, those assessments bind the recorded baseline; verify the complete repair chain and eligibility separately.
Independently inspect the candidate and run the assigned checks. Record supplied model configuration, applied skills and unavailable checks. Do not audit model receipts or block on unavailable introspection.
An upstream defect follows controller-workflow.md#upstream-defects-found-downstream. Preserve read-only review, report exact evidence and affected dependency to <controller>; do not patch upstream or treat old PASS as overriding a verified blocker.
Save the candidate-bound gate assessment at <report path> before delivery.
Within budget, send 1/3 or 2/3 blockers directly to <worker pane>, without routine controller copies.
Send PASS or unresolved 3/3 blockers to <controller pane>. Escalate authority, budget or unsafe-delivery obstructions earlier.
Use the canonical Smux procedure with one single-line path/hash pointer, at most 220 characters before the bridge envelope. Freeze evidence before hashing; save delivery notes separately. Include the single post-Enter submission check, then return to standby.
PASS approves only the reviewed candidate. It grants no publication, merge, dispatch, provider or financial authority.
On controller acceptance/integration return, relay the outcome once to <worker pane> with checked delivery. Record the relay and remain in standby. Do not reset the lane or assign the next ticket yourself.
```

The controller schedules, technically accepts authorized outputs and integrates under the standing rule above. The worker implements and commits. Reviewers remain read-only. The builder retains new product decisions and main-branch merge control. A controller cannot supply the independent approval for its own change.

1. The worker produces a clean candidate commit and records checks and limits.
2. Pause the worker while reviewers inspect its worktree. Alternatively use a separate read-only checkout of the exact commit.
3. Confirm candidate ancestry and scope against the assigned base.
4. Run two independent native reviewer contexts under the [worker-host model policy](../../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md#approved-model-policy). Explicitly select the prescribed model and effort at launch. Give both the same base, candidate and acceptance packet. Record the configured selection.
5. Use the adapted Matt internal review procedure below. Keep initial findings hidden from each other. Both reviewers load General Review Protocol, then Review Verification Protocol, Code Reviewer and Code Review Excellence. Add only applicable domain skills.
6. Return verified blockers to the worker in one batch. A fix requires a replacement commit and both reviewers' assessment of the changed behavior and affected invariants.
7. Record each verdict with the exact candidate SHA. An earlier PASS never approves later edits.
8. Send the internally reviewed candidate and both original assessments to the separate Codex gate. The gate checks the review evidence before issuing PASS. Route subsequent gate-requested repairs under [gate-stage repair review](#gate-stage-repair-review). Record its independent verdict against the exact resulting candidate. Apply the recorded builder or batch technical-acceptance authority. Main merge follows the manual policy.

### Adapted Matt internal review

Builder approved this clarification on 2026-10-07. The worker reads Matt's `code-review` skill before preparing internal reviews. Use its specification and standards checklists within the existing two assignments. This is the project's adapted Matt review procedure, not an unmodified invocation of the upstream skill.

- Reviewer A owns specification compliance, correctness, scope, tests and integration.
- Reviewer B owns repository standards and maintainability, while retaining assumption, failure, ownership/permission, recovery and relevant statistical-validity checks.

Give both reviewers the exact base/candidate, accepted requirements, relevant repository standards and verification evidence. Standards take precedence over generic code-smell heuristics. Distinguish documented violations from judgment calls. Either reviewer may report a verified defect outside its primary assignment.

General Review Protocol remains each reviewer's entry point. Apply its required stack and task-relevant domain checks. Verify defects against actual code, surrounding behavior and relevant callers. Report severity, consequence, file/line evidence, performed checks and unavailable proof. Keep each original assessment and verdict separate.

The assignment owner launches exactly two independent reviewer contexts. In a selected new profile, use built-in reviewer subagents on the Codex route; the native-batch coordinator may launch them for the worker. Existing assignments retain their recorded native contexts, including reviewer panes. The configured OpenCode route must first qualify its two independent review contexts. Neither reviewer invokes `code-review` to spawn another pair. An executor's built-in review does not add another review layer: map it to this existing pair. The separate gate does not spawn a Matt pair either. Retain the approved host/model policy, exact-candidate replacement reviews, uncapped internal repairs and three-verdict gate limit.

Record the worker's loaded Matt skill path and the adaptation in its result. Apply this clarification at the next internal reviewer launch without interrupting active reviews. Preserve prior assessments and their original requirements. This documentation clarification alone does not invalidate an earlier PASS, restart a task, reset counters or require a duplicate review.

### Original reviewer reports

Retain the original assessment from each independent native reviewer context. The worker may save the returned assessment unchanged with its source identity. It must not replace the assessment with its own PASS summary or write a review on another reviewer's behalf. Preserve earlier assessments as historical evidence after replacement reviews.

Each assessment must identify:

- Task, reviewer assignment and native context identity.
- Exact base and candidate SHA.
- Assigned host/model and effort. Distinguish configured selection from unavailable serving telemetry. Missing introspection is non-blocking.
- Required skills actually applied. Name any missing skill or unavailable instruction source.
- Checks performed, results and evidence paths. Distinguish reviewer-run checks from worker evidence inspected.
- Findings, limitations and explicit PASS or REVISE verdict.

The worker supplies both assessment paths and identities with the gate packet. If an assessment arrives only through a native completion tool, retain that original response and its context identifier. Both assessments must cover the same candidate for initial submission or the wider replacement route. A later authorized narrow gate fix retains them as baseline evidence and requires candidate-bound gate review under [gate-stage repair review](#gate-stage-repair-review).

The gate verifies both original assessments against their recorded candidate and the selected route. Missing required skills, missing original assessments or unexplained candidate mismatches block PASS. A documented baseline-to-repair chain is permitted only under [gate-stage repair review](#gate-stage-repair-review). Model-dispatch receipt collection and runtime introspection are not gate prerequisites. Apply the builder's model-selection clarification in the adopted playbook; reported concrete substitutions remain distinct from unavailable telemetry. The gate's own review cannot replace incomplete INITIAL internal reviews or required sensitive-change replacement reviews. Keep private reports and sensitive logs outside shared candidates unless their publication is explicitly authorized.

### Review budgets and host changes

Builder correction, 2026-10-07: internal repair/review rounds have no numeric cap. Collect both original independent assessments, repair verified blocking findings, run affected checks, commit a replacement and repeat the required independent reviews until both PASS on the same exact candidate. Do not stop at internal round three or request a round-count extension. Ordinary review findings are work for the implementer, not a new builder decision.

Record the full internal history as rounds completed, not `n/3`. Preserve old reports and earlier cap/extension records as historical evidence. This correction supersedes internal-cap wording in existing task packets, without rewriting their hashes or resetting review history.

Only independent gate verdicts have the three-review limit. Identify them as `1/3`, `2/3` or `3/3`. Internal rounds never consume gate verdicts. Unresolved gate blockers at `3/3` require controller/builder direction; the internal loop cannot bypass that boundary or manufacture PASS.

Continue while safe in-scope repairs are possible. A missing product decision, unavailable model/subscription capacity, unsafe delivery, exhausted provider/spending authority, an explicitly approved batch run limit or user interruption can still stop affected work. These conditions are separate from an internal round count. Review repetition grants no additional spending, model switch, task scope, deployment, merge or financial authority.

### Internal review routing

An ordinary internal-review REVISE is work for the assigned worker, not a controller obstruction. Collect both independent reviews, batch verified findings, repair and obtain both candidate-bound replacement assessments. Repeat until both PASS on one candidate, without an internal round cap. Keep routine findings, pending-review status and repair progress in the evidence record. Send neither controller progress pings nor a failed internal candidate to the gate.

The worker first submits to the assigned gate only after both original internal assessments PASS the candidate. Later submissions follow [gate-stage repair review](#gate-stage-repair-review). Earlier controller escalation is permitted only when a specific decision outside task authority, exhausted approved budget or unsafe delivery prevents the loop. State that obstruction, the recorded cycle count and the exact decision needed. Finding a defect alone does not satisfy this exception. An activation acknowledgment is sent only when requested.

Within the approved budget, gate blockers at `1/3` and `2/3` return directly to the worker. The worker repairs, verifies and commits a replacement; the recorded [gate-stage repair route](#gate-stage-repair-review) determines whether independent replacement reviews precede return to the SAME gate. The controller receives PASS or unresolved blockers at `3/3`. A decision outside task authority, blocked delivery or an exhausted approved budget needs earlier escalation. At a budget limit, the builder approves any extension or product-scope change. A cycle limit cannot turn a failure into a PASS.

The worker owns its two native internal review contexts. The Codex gate reviews separately after their completion. One pane, one model or two sequential passes in the same context cannot replace two independent contexts. Do not repeat release-wide review for every small replacement.

When switching between Claude and Codex workers, preserve the lane and task state, stop the prior writer, and verify path/branch/base before resuming. Use the new host's approved review route. Keep OMC disabled and use the existing panes; no new coordination layer is required. A subscription limit does not waive a required review or authorize extra paid usage.

## Messaging, integration and handoff

### File-backed packets

Save substantial assignments, review findings, scoped decisions, resumption instructions and completion returns in a file before delivery. Use the existing task and review templates. Keep brief acknowledgments inline when they contain no new instructions.

Each packet names its task/event/version, sender, recipient and reply panes. Include applicable base/candidate identities, accepted sources, scope, authority, required skills, checks and evidence paths. Separate accepted requirements from routing and process metadata. A packet cannot grant authority absent from the accepted task.

Freeze the bytes before calculating SHA256. Store the expected hash in the relay and ledger, outside the hashed file. Preserve an earlier packet when instructions change. Save a versioned replacement that identifies what it supersedes and what remains unchanged.

Builder correction, 2026-10-08: every substantial relay body is one line of at most 220 characters before the bridge-added envelope. Put task status, candidate, findings, limits, original report pointers and recovery instructions in the packet. Type only `Read <path> SHA256 <hash>` with an optional short task label. Check the body length before typing. If paths or multiple reports do not fit, use a short-named frozen index packet; do not type a report excerpt or split the report into several messages. The length bound is a preflight rule, not a guarantee that a client will render or submit correctly.

Complete a report before freezing and hashing it. Record typing, submission and delivery failures in a separate ledger or receipt. A later report change gets a preserved, versioned replacement and a new hash. Fixing a sender's own stale hash or oversized relay is routine delivery repair, not a new builder decision or gate verdict. A receiver routes a repairable packet mismatch back to its sender rather than asking the builder to approve report bookkeeping.

On the builder's host, use an exact readable path, absolute when worktree-relative paths are ambiguous. Required teammate inputs use checkout files or issue attachments. Keep private packets and secrets outside shared candidates.

The receiver verifies the supplied hash, reads the complete file and checks its task, recipient and candidate before acting. A mismatch blocks that packet, not independent authorized work. TX Odds' durable briefs and immutable review packets supply this pattern. Edge OS retains its own review and authority rules.

### Checked delivery

Use Smux and `tmux-bridge` for cross-pane requests and replies. Load the Smux skill and follow this delivery sequence:

Builder-approved clarification, 2026-10-10: an agent working is not a delivery obstruction when its message composer is empty. Send without waiting for its turn to finish. Preserve the active turn and verify the submitted transcript or accepted input queue. This applies to controller, worker and gate returns. Previously accepted queued messages are submitted input, not foreign composer drafts. An empty shell prompt, permission dialog or command menu is not an agent message composer. Preserve foreign drafts and ambiguous submissions.

1. Read the destination pane before sending.
2. Confirm that the agent message composer is empty. Preserve any unsent draft or ambiguous input; do not overwrite it or submit it accidentally.
   A cursor, input focus or the client's empty-input placeholder is not a draft. Keep submitted transcript text separate from input text. A busy indicator alone does not block delivery. Recheck the composer before recovery because an earlier draft may already be submitted. Preserve the active turn without Escape, Ctrl+C or reset.
3. Use `tmux-bridge message` to enter the prechecked single-line pointer/hash body of at most 220 characters, or a brief inline reply. Explicitly authorized external relays use `type` with a truthful short origin label and the same bound.
   Keep full instructions in the saved packet. If the client collapses an agent-owned relay or its hash is stale, preserve the original text and delivery state separately and replace it with a current short pointer using a supported input-editing action. This routine correction needs no further builder permission when ownership and non-submission are established. An ambiguous submission or user/foreign draft still requires safe recovery; a paste marker alone does not identify the composer contents. Never submit a known-outdated hash.
4. Wait 350 ms for the screen to settle. Read once to confirm the complete message reached the input.
5. Send `Enter` to submit that message. `message` and `type` insert text only. Neither completes delivery.
6. Wait 350 ms after `Enter`. Read the destination once. Confirm the exact message appears in its submitted transcript or accepted queue, not only its input.
7. Record the destination, message identity and observed submission status in the task evidence. Return to standby or independent authorized work.

Typing and a successful Enter command alone do not prove delivery. If the post-Enter read does not confirm submission, record `DELIVERY UNCONFIRMED`. Preserve the message and observed state. Do not blindly resend, press Enter again or repeat reads. Use the blocked-delivery route below to request safe recovery. A submitted message does not prove the recipient started or completed the task.

The builder explicitly requires this one post-Enter confirmation for every controller, worker and gate message. It supplements Smux's default sequence. It does not permit reading for a reply.

The fixed settling waits are transport checks, not progress polling. Start native qualification at 350 ms. A tested client may use 400 ms, recorded with its evidence. Neither interval guarantees delivery. Reserve longer waits for controlled tests with unavoidable large input. Do not add a five-second default or an automatic second Enter.

When the checked-send helper and native hook binding are verified for the session, use that helper with the binding's state directory. It records the outbound event for the Stop guard. Raw bridge calls and Markdown delivery notes alone do not create guarded delivery events. Do not claim an unbound pane is protected. The accepted tooling and its tested-client limits are recorded under Safeguard qualification above; other clients/layouts need their own evidence.

The current helper requires `confirm_idle`; it is not qualified for busy-recipient queues. Keep that confirmation truthful. For a busy agent with an empty composer, this amendment authorizes the checked Smux sequence above on a verified queue-capable client. Record its accepted queue separately; this route does not create a guarded helper delivery event. If the client cannot accept input without interrupting work, preserve the report and record the actual transport obstruction. A bounded builder-host pilot accepted a queued pointer while its controller was working. That private receipt does not qualify another host/version; retain an actual local delivery receipt before claiming this behavior.

### No polling while another pane works

After dispatch, do not repeatedly read/capture a pane, inspect its changing branch, call background thread status/read/wait APIs, launch watcher subagents or run sleep/retry loops to discover progress or completion. A completion notice comes from the assigned agent through Smux. Do not replace pane delivery with a background-thread message or status-wait loop merely because that tool is available. The pre-send, pre-Enter and single post-Enter reads are transport checks, not a progress-monitoring loop.

A gate receiving an advance review packet remains in standby until its worker sends the exact candidate. It must not monitor the worker or wait for the worker's internal reviewers. The gate starts its own assigned review only after candidate delivery. Native internal reviewers may use their host's completion notifications; that is separate from watching another tmux lane. Read an interactive non-agent process only when its assigned task requires that interaction.

### Required return delivery

Every controller, worker and gate uses the messaging procedure above, including the single post-Enter submission check. Writing a final answer in the sender's own pane or saving a report is not delivery to the recipient.

| Sender and event | Required destination and contents |
|---|---|
| Worker receives ordinary internal-review findings | No cross-pane status message. Worker repeats the uncapped repair/review loop until both original assessments PASS on one candidate. |
| Worker has a candidate with both original internal PASS assessments | Assigned gate: task, exact base/candidate, both original assessments, checks, evidence path and limits. |
| Worker has an authorized narrow gate-stage repair | SAME gate through the recorded route: baseline pair/candidate, controller eligibility, complete repair range/new candidate, findings, required checks/evidence and unchanged gate counter. |
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

1. Verify the builder's authority and the exact gate-passed candidate. Keep publication, integration-branch changes and main merge separate. A changed candidate needs new candidate-bound approval. Use [gate-stage repair review](#gate-stage-repair-review) only for an eligible recorded gate repair; other changes require independent replacement review.
2. Integrate only that candidate into the authorized target, one candidate at a time. Preserve active workers' recorded bases.
3. Run the affected integration checks against the resulting commit. If they fail, record the failure and leave integration incomplete.
4. Update the live ledger and applicable tracker state with the reviewed candidate, actual resulting commit, checks and limits. Reassess waiting assignments against that base.
5. Send the recorded outcome through controller → gate → worker under the return-delivery table. If delivery is unsafe, preserve the outcome and use the obstruction route.
6. If an approved batch authorizes another eligible ticket, perform fresh-session activation and continue. Otherwise leave the lane in standby. Batch authority replaces repeated assignment questions, not prerequisite checks.

Gate PASS, controller technical acceptance, builder product decisions, publication and verified integration are distinct states. Do not mark a task integrated from an issue status alone. No automatic main merge is authorized.

The live ledger records the integration SHA, ticket and owner, path/branch/base, candidate SHA, checks, both reviews, integration status, blocker and next action. Keep its current summary short and dated. Preserve prior evidence below it. Before ending a session, leave enough information for a fresh controller to resume without conversation history.

GitHub remains the shared task tracker. Local proposals and idle branches are not implementation assignments. Publish required extracts and the accepted handoff before a teammate depends on them. Never send private courses, credentials or raw prototype archives as shared task inputs.
