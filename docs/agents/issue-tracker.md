# Issue tracker

Repository: `edge-os-app/edge-os`.
Tracker: GitHub Issues.
Tool: GitHub CLI.

Before a tracker operation, confirm that it targets this repository. Use an explicit repository target when working outside its checkout. If authentication or access is unavailable, report the blocker.

Create or modify issues only within the assigned authorization.

## Sources of truth

GitHub Issues record assignments, blockers, task status and acceptance evidence.

The accepted specification remains a version-controlled repository document. Tickets link to its exact path and revision. A specification issue may index that document without maintaining a second editable copy.

Required task inputs must be available in this repository or the issue. The builder supplies relevant verified extracts from private research when a ticket depends on them. Do not assign a teammate a task that requires an unavailable private archive.

Keep proposed behavior, approved behavior and implementation evidence distinct.

## Task conventions

Each implementation issue records:

- Approved specification revision.
- Observable result.
- Scope and exclusions.
- Blocking issues.
- Acceptance checks.
- Required verification and evidence.
- Assigned owner.

An implementation ticket is ready only after its behavior is accepted and its blockers are resolved.

A closed issue alone is not proof that a dependency passed. Check its acceptance evidence.

## Pull requests

PRs as a request surface: no.

Implementation uses pull requests. This flag only excludes external PRs from feature-request triage.

The builder selected a manual merge gate on 2026-10-02. Teammates submit PRs and leave the merge to the builder. The workflow does not require a GitHub approving review, sole-code-owner approval or branch protection. The builder may accept their own PR after the applicable implementation checks and independent reviews. GitHub self-approval is not used. Repository settings have not been changed or verified by this local documentation update.

## Wayfinder

Use Wayfinder only when the builder selects it.

Keep one map issue with linked decision tickets. Use available GitHub sub-issues and dependencies. If unavailable, use linked task lists and explicit blocking references.

Record the decision and its evidence before resolving a decision ticket.
