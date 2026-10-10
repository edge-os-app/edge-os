# Implementation names and skill selection

Builder instruction, 2026-10-08. These rules apply to pane and native dispatches. They do not change accepted product behavior, ownership, models, operation limits or review counts.

## Name files for their responsibility

Application filenames must describe what their code does. Examples: `strategy_compiler.py`, `record_contract_adapter.py`, `hermes_runner.py` and `test_strategy_compiler.py`. A ticket number alone, such as `p06.py`, does not explain an application's responsibility. Use descriptive Python snake_case and the established conventions for other languages.

Keep ticket numbers in task packets, worktree/branch names, review reports and traceability metadata. Preserve published contract/schema identifiers, migration identifiers, generated/vendor files and framework-required filenames. Those identifiers do not justify ticket-only names for ordinary application modules.

Before a rename, find all imports, callers, tests, scripts, exports and documentation references. Update them within the owning task and run affected checks. Never rename an exact candidate during review or after PASS without a replacement commit and the required candidate-bound reviews. Do not start a repository-wide cleanup in an unrelated ticket.

## Select relevant skills before every dispatch

The controller supplies a required-skill list and a short applicability reason in every implementation packet. Review packets identify applicable domain skills alongside the existing review stack. Agents read selected skills and required references before use. Installing or naming a skill does not prove it ran.

Before each implementation, repair or review dispatch:

1. Inspect the current session's full available skill catalog, using names and descriptions. Check task concerns against that catalog, not only the Python list below or a previous packet. When a named skill is absent, check the documented local fallback and record whether it is usable.
2. Select the skills that cover the actual changes and verification. Include explicitly requested skills. Read each selected skill's complete instructions and required references before preparing instructions that depend on it. Read only relevant references; catalog discovery does not require loading every skill.
3. Record the selected names, exact instruction paths, applicability reasons and required checks in the packet. Record catalog source/date, unavailable requested skills and any project-specific adaptation in the dispatch ledger. Installed files alone do not establish host support.

The table below is a task-routing guide, not the complete skill catalog. Use the current catalog to select additional architecture, frontend, security, testing, runtime, data or documentation skills when the task requires them. Reuse overlapping guidance without adding review agents or new acceptance gates.

| Task concern | Required skill and use |
|---|---|
| Module responsibility, interfaces, organization or testable design | `codebase-design`: clear responsibilities and small interfaces; reuse existing modules before adding another layer. |
| New or changed Python implementation | `python-pro`: relevant type-safety, standard-library, resource and test practices. |
| Python naming, imports, docstrings and repository conventions | `python-code-style`: descriptive names and existing formatting/type-check rules. |
| Python implementation self-check and independent review | `python-anti-patterns`: validation, duplicate retries, resource cleanup, types, async misuse and error-path tests. |
| Python HTTP/API, authentication, database or backend-service changes | `python-backend`: request validation, authorization, transactions and existing backend structure. |
| Validation, external errors, cancellation, cleanup or partial failure | `python-error-handling`: preserve cause and failure state, sanitize private detail and test failures. |
| Performance requirements, numerical/data hot paths, memory/work limits or a demonstrated slowdown | `python-performance-optimization`: measure the relevant path and resource boundary before optimizing. |

Select other relevant skills for non-Python work, including frontend interaction and browser verification. A frontend-only task does not require the entire Python list. A small Python change still needs applicable naming, quality and failure checks.

Accepted criteria, frozen contracts, repository conventions, scope and locked toolchains override conflicting generic skill defaults. Do not introduce dependencies, lint/coverage gates, async rewrites, abstractions or broad formatting changes merely because a skill's example uses them. State adaptations and unavailable checks truthfully. Skills grant no provider calls or extra reviewers.

## Ponytail Lite in future prompts

Builder instruction, 2026-10-10: include `ponytail` at **Lite** level in new implementation and repair packets for Codex, Claude and OpenCode. It supplements Karpathy and task-specific skills. Read the installed skill before use. Resolve the installed instruction path from the contributor's own host catalog. Record its version or source revision; the builder's installation path is not a required input. Record an unavailable skill and apply the constraints below without claiming it loaded.

Use the smallest complete change that satisfies the accepted task. Reuse existing code and dependencies. Preserve responsibility-based modules, affected callers, tests, fixtures, configuration and exports. Name a smaller alternative without silently reducing approved scope. For documentation-only tasks, apply these scope rules without inventing executable checks.

Keep required validation, authorization, accounting, concurrency, recovery, error handling, accessibility and evidence. Project-required checks override the skill's minimum-test suggestion. Internal reviewer briefs and gate packets check completeness as well as unnecessary complexity; a simpler alternative alone is not a blocking defect. Preserve the existing reviewer pair, gate, review history and verification cadence. Ponytail adds no reviewer or acceptance layer and proves no model-specific credit saving.

Apply this default to future packets. Preserve active frozen assignments unless a recorded continuation explicitly adds it. Report actual use, adaptations and unavailable checks in the existing result.

## Packet and return checks

For an upstream repair, include the [defect-routing fields](controller-workflow.md#upstream-defects-found-downstream): exact dependency/reproduction, blocked downstream behavior, authorized path lease, regression/submission checks and candidate-bound review route. A downstream assignment is not permission to patch outside its paths. Existing accepted code can require a new repair; preserve its original approval history.

Before sending, confirm that selected skills match the task's responsibilities and verification. Name the responsibility-based file plan, or state that existing names are unchanged. Include relevant research and prior implementations under the existing evidence-first rules.

Include the [verification cadence](controller-workflow.md#verification-cadence) in implementation, repair and review packets. Identify focused checks, complete committed-candidate submission checks, the reviewer's or gate's own required checks and integration checks. Record full-run timing and rerun reasons in existing evidence. Naming a verification skill does not require its complete recipe after every edit; preserve explicitly required checks and independent review.

For gate-stage repairs, record the [selected review route](controller-workflow.md#gate-stage-repair-review), baseline pair/new candidate identities, actual-diff eligibility and any active-task amendment. Required reviewer skills apply when that route calls for reviewer activation; a skill list alone must not create a redundant pair.

Use the common [worker activation packet](controller-workflow.md#worker-activation-packet) or [gate activation packet](controller-workflow.md#gate-activation-packet) as the field checklist. Record the template reference and any workflow-specific substitutions in the ledger before freezing the packet. Native dispatch replaces pane activation, Smux delivery and pane destinations with its approved fresh-child activation and native return route; it retains task identity, sources, exact worktree/base, authority, ownership, skills, checks, evidence and review history. Mark genuinely inapplicable fields explicitly rather than silently dropping them.

Worker results identify skills actually applied, checks run, unavailable checks and justified naming exceptions. Standards reviewers check new/renamed application filenames and relevant practices against this document. Keep the existing two internal reviews, independent gate and uncapped repairs.

Apply this instruction to new dispatches and the next repair/review launch. Do not interrupt active assignments, alter frozen packets or retroactively claim they loaded new skills. A candidate code change requires preserved original reports and candidate-bound review through [gate-stage repair review](controller-workflow.md#gate-stage-repair-review). Record the selected route and actual-diff eligibility; initial internal-review repairs and sensitive/broad gate repairs retain replacement internal reviews.

Names already fixed in an active candidate are not an automatic rename assignment. Record them for the next authorized implementation change; do not silently invalidate an in-flight review or expand a ticket into broad cleanup.
