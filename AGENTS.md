# Edge OS agent instructions

## Start here

This checkout is the shared application repository. Its specifications, contracts and implementation rules are authoritative for team work. The surrounding `monad-hack` workspace is the builder's private research and controller workspace, not another repository.

For each task:

1. Read `docs/CONTROLLER_HANDOFF.md` for current state and approved next work.
2. Read the assigned issue and its linked specification and decisions.
3. Read only the additional documents required by that task.

All required implementation inputs must be available in this checkout or the assigned issue. Material marked `BUILDER-ONLY REFERENCE` is not included in a teammate's clone. Follow the reference rules in `docs/agents/domain.md`. On the builder's host, use [read-only prior-project discovery](docs/agents/controller-workflow.md#read-only-prior-project-discovery) for reusable patterns in the builder-authorized local reference roots. Teammates without those folders request a necessary verified extract instead of guessing. Optional local discovery is not a clone prerequisite.

If a linked worktree lacks a referenced document or needs newer context, first use [read-only shared-checkout context](docs/agents/controller-workflow.md#read-only-shared-checkout-context). Inspect the primary checkout before reporting a missing-context blocker. Keep the assigned implementation base unchanged. Uncommitted documents are context, not accepted product requirements.

The builder owns product decisions, prototypes and the hackathon release candidate. The quant contributor may implement separately assigned, accepted quantitative/backend work outside that release. The former frontend/tokenization teammate split is superseded; see [current ownership](docs/EDGE_OS_COMPASS_WORKFLOW.md#9-team-ownership). Start with [the contributor workflow](docs/agents/contributor-workflow.md).

The [dated P14 numerical assignment](docs/team/QUANT_CONTRIBUTOR_BRIEF.md#start-with-p14) permits independent PR development of proposed extension semantics and tests. Follow its bounded ownership and record your own base from latest main. This exception removes preliminary proposal/profile waits, while preserving adoption, shared leases, reviews and merge control. Other tickets still require their own assignment.

Follow [evidence-first task context](docs/agents/controller-workflow.md#evidence-first-task-context) before material decisions or missing-context escalation. Read the packet's named prior research. Preserve source limits and distinguish accepted requirements from drafts, inferences and routine implementation choices.

The Hackathon Winning Compass controls the project through `docs/EDGE_OS_COMPASS_WORKFLOW.md`. The retired Idea Funnel does not control current work.

A draft specification, proposed experiment, or successful component test is not approval to implement or deploy.

## Work boundaries

Keep changes within the assigned task. Preserve unrelated changes.

For a defect in an upstream dependency, including already integrated or gate-passed code, follow [upstream defects found downstream](docs/agents/controller-workflow.md#upstream-defects-found-downstream). Investigate and propose the repair. Fix owned paths normally; report outside-scope defects before upstream edits. The controller can assign that same worker after checking authority and leases. Continue independent safe work. An earlier PASS does not waive a newly verified blocker.

Work on a task branch and submit a pull request. The builder accepts and merges changes. Do not push directly to `main`.

Under [controller technical acceptance](docs/agents/controller-workflow.md#controller-technical-acceptance), the controller accepts already authorized, verified ticket outputs and integrates them locally without another builder approval. Workers still leave acceptance and merges to the controller. New product decisions, publication and main merge retain separate authority.

The builder authorized a one-time documentation-only initial commit and push to `main` on 2026-10-02 to establish the empty repository's baseline. This does not authorize later direct pushes, application implementation or prototype execution.

The builder selected a manual merge gate on 2026-10-02. GitHub-enforced approvals, sole-code-owner review and branch protection are not required by this policy. Teammates must still leave merges to the builder. This does not waive task verification, independent code reviews or financial authorization.

Paid services, wallet changes, delegation and financial transactions require explicit task-level authorization. Keep credentials outside source control and model inputs.

For implementation and review, follow `playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md`. For isolated lanes and exact-candidate handoffs, follow `docs/agents/controller-workflow.md`. Use actual repository scripts for verification. Report checks that could not run.

Use the [verification cadence](docs/agents/controller-workflow.md#verification-cadence): focused checks during development and repair, complete required checks on committed submission candidates, independent assigned review checks and affected/final integration checks. Maintain the verifier daily while development is active; this does not mean running the full application suite every few minutes or after every edit. Record full-run timing and rerun reasons without adding another review layer.

Before a new dispatch or authorized workflow switch, read [execution workflow selection](docs/agents/execution-workflows.md). Record one selected profile/version and its activation authority in the packet and ledger. Separate prepared guides cover `tmux-goal` and `native-batch`; documentation alone activates neither. Existing assignments retain their route until a recorded handoff. Pane-specific communication rules below apply to cross-pane work; an explicitly selected native batch uses its documented native/headless returns. Review standards and operation limits remain shared.

Internal reviews use the [adapted Matt procedure](docs/agents/controller-workflow.md#adapted-matt-internal-review). The worker reads `code-review` and applies its checklists within the existing two reviewer assignments. Preserve adversarial checks and the required evidence stack. Do not spawn an additional pair or claim an unmodified Matt invocation.

Internal repair/review rounds continue until both independent reviewers PASS on one exact candidate before the first gate verdict. Later gate repairs follow [gate-stage repair review](docs/agents/controller-workflow.md#gate-stage-repair-review); unamended active tasks retain their route. There is no internal three-round cap. Only the independent gate has a three-verdict limit. Preserve original report/commit identities and stop only for genuine obstructions.

The worker selects the prescribed internal reviewer model at launch. Gates review candidate correctness and original assessments, not model-dispatch receipts or inaccessible serving-model telemetry. Missing model introspection is non-blocking. See the adopted model policy for concrete configuration mismatches.

For pane coordination, use `coordinating-parallel-workers` and Smux under `docs/agents/controller-workflow.md`. Before a new ticket, follow its fresh-session activation procedure, including native `/clear` for the current Claude Code and Codex clients. Use its worker and gate activation packets. Every message requires its single post-Enter submission check. Then await an incoming Smux reply rather than polling panes, branches or background thread status. Follow its internal review routing before escalating worker findings, and its required return-delivery table for gate blockers, PASS, escalation and controller → gate → worker completion. Every assignment names its reply destination; unavailable delivery requires an explicit alternative route.

For substantial assignments, findings, decisions and completion returns, use [file-backed packets](docs/agents/controller-workflow.md#file-backed-packets) and its checked-delivery sequence. Put the full message in a frozen file. Relay one single-line path/hash pointer of at most 220 characters before any bridge-added envelope; shorten the filename or use a frozen index file when necessary. Keep delivery notes outside the hashed file. Correct an agent-owned outdated relay as routine delivery repair; preserve user drafts and uncertain submissions. Verify submission after the specified settling waits.

Controllers use [model-aware dispatch prompts](docs/agents/dispatch-prompt-profiles.md) after confirming the destination host/model. Provider wording does not alter task authority, model selection or review requirements.

Inspect and preserve existing pane model, effort and speed under [preserve pane model selections](docs/agents/controller-workflow.md#preserve-pane-model-selections). Compatible selections require no change. Even a reset-induced mismatch needs explicit builder instruction before changing settings. Fresh internal reviewer launches still follow the prescribed review route.

For an approved autonomous batch, follow `Approved autonomous batches` in that procedure. Continue eligible named tickets without asking whether to continue. Enter native `/clear` through keys and Enter, never `message`. Read the destination before typing, after typing and once after Enter. A typed message alone is not delivered. Recover saved unsent messages only under the safe delivery rule. Batch technical acceptance may be delegated explicitly; main merge, financial operations and unlisted tickets remain outside that authority.

For current library, framework, SDK, API, CLI and cloud-service documentation, use Context7. Resolve the library ID first, then query documentation with the complete technical question.

## Agent skills

Follow [implementation names and skill selection](docs/agents/implementation-standards.md) for every implementation, repair or review dispatch. Inspect the full current available skill catalog and check the common worker/gate template fields against the selected workflow. Name files for their responsibility. Packets specify relevant skills, reasons and instruction paths; agents read them and report actual use. Preserve exact candidates during active review.

### Issue tracker

Work is tracked in GitHub Issues for `edge-os-app/edge-os`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five approved default labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use one root domain context and `docs/adr/`. See `docs/agents/domain.md`.
