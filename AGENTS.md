# Edge OS agent instructions

## Start here

This checkout is the shared application repository. Its specifications, contracts and implementation rules are authoritative for team work. The surrounding `monad-hack` workspace is the builder's private research and controller workspace, not another repository.

For each task:

1. Read `docs/CONTROLLER_HANDOFF.md` for current state and approved next work.
2. Read the assigned issue and its linked specification and decisions.
3. Read only the additional documents required by that task.

All required implementation inputs must be available in this checkout or the assigned issue. Material marked `BUILDER-ONLY REFERENCE` is not included in a teammate's clone. Follow the reference rules in `docs/agents/domain.md`; request the required verified extract instead of guessing or searching the builder's filesystem.

The builder owns product decisions and all prototyping. Agents and contributors implement explicitly assigned accepted tickets. Read [current team ownership](docs/EDGE_OS_COMPASS_WORKFLOW.md#9-team-ownership) before assigning or changing an owner.

The Hackathon Winning Compass controls the project through `docs/EDGE_OS_COMPASS_WORKFLOW.md`. The retired Idea Funnel does not control current work.

A draft specification, proposed experiment, or successful component test is not approval to implement or deploy.

## Work boundaries

Keep changes within the assigned task. Preserve unrelated changes.

Work in an assigned isolated worktree on a task branch. Return required checks and original independent reviews to the controller for technical acceptance and local integration under recorded authority. Publication and merging to `main` require recorded builder authorization. The builder may authorize the controller to execute a specific merge. Do not push directly to `main`.

The builder authorized a one-time documentation-only initial commit and push to `main` on 2026-10-02 to establish the empty repository's baseline. This does not authorize later direct pushes, application implementation or prototype execution.

The builder selected a manual merge gate on 2026-10-02. GitHub-enforced approvals, sole-code-owner review and branch protection are not required by this policy. Contributors leave integration to the controller and `main` authorization to the builder. This does not waive task verification, independent code reviews or financial authorization.

Paid services, wallet changes, delegation and financial transactions require explicit task-level authorization. Keep credentials outside source control and model inputs.

For implementation and review, follow `playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md`. For isolated lanes and exact-candidate handoffs, follow `docs/agents/controller-workflow.md`. Use actual repository scripts for verification. Report checks that could not run.

For pane coordination, use `coordinating-parallel-workers` and Smux under the messaging rules in `docs/agents/controller-workflow.md`. Requests and replies must reach their recorded panes. After sending, await an incoming Smux reply rather than polling panes, branches or background thread status. Every assignment names its reply destination; unavailable delivery requires an explicit alternative route.

For current library, framework, SDK, API, CLI and cloud-service documentation, use Context7. Resolve the library ID first, then query documentation with the complete technical question.

## Agent skills

### Issue tracker

Work is tracked in GitHub Issues for `edge-os-app/edge-os`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five approved default labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use one root domain context and `docs/adr/`. See `docs/agents/domain.md`.
