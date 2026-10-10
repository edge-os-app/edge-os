# P40 release journey preparation

Task OC-P40-PREP-20261010-01, issue edge-os-app/edge-os#47. Base `a90d8b7f1a7ab500024e076194f2b5d6cbc83f11`. Prepared 2026-10-10 in the `p40-opencode-worker` worktree.

Stage: **documentation and preparation only.** This package maps the accepted P40 release journey to the routes, views, records, tests and evidence that exist in the repository. It does not run the application, execute the browser, contact a participant, or assert a fresh runtime or full P40 PASS.

## Proposed verdicts

- **DOCUMENTATION / PREPARATION coverage: PASS within the scope below.** Each journey case names its prerequisites, sources, exact steps and expected observations, and separates implemented evidence from unrun checks and future qualification.
- **Application journey runtime verification: UNRUN.** No application process, browser drive, saved-record inspection or restart run was executed for this package. The mapped checks are repository evidence and test coverage pointers.
- **Participant evidence: NOT RUN / UNRESOLVED.** No trader observation exists in this package. Historical assisted prototype feedback is not new evidence.
- **Full P40 issue #47: OPEN.** No release verdict, deployment, participant result, profitability claim or live qualification is asserted.

## What the release journey covers

The [release cut](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) defines the P40 portion as verifying the selected application journey and collecting honest accessibility and comprehension evidence. The currently accepted and integrated application path is:

Research request and classification to exact compiled rules, then authored synthetic account views. This path exists in the repository today. The remaining journey segments (bounded permission, controlled Kuru receipt, restart/revocation) stay future qualification and are explicitly blocked until their accepted prerequisites pass.

Each case in [RELEASE_JOURNEY_CHECKS.md](RELEASE_JOURNEY_CHECKS.md) maps one observable behavior to its UI route, API route, saved records, covering tests and evidence files. Uncoached participant tasks and an observation form are in [TRADER_TASK_GUIDE.md](TRADER_TASK_GUIDE.md).

## Documents

- [RELEASE_JOURNEY_CHECKS.md](RELEASE_JOURNEY_CHECKS.md): the journey map, per-case prerequisites, sources, steps, expected observations, missing proof, and the required desktop, 390px, keyboard, phone and screen-reader checks with their actual limits.
- [TRADER_TASK_GUIDE.md](TRADER_TASK_GUIDE.md): uncoached target-trader tasks separated from expected answers, plus an observation form naming the exact revision, participants, assisted or unassisted conditions, failures and permitted feedback.

## Scope and exclusions

Owned new path: `docs/qualification/release-journey/` only. No application code, shared documentation, contracts, migrations, scripts, lockfiles or new helper or probe program. The verifier and feature map are coverage inputs read for this preparation, not edited and not rerun.

No entity is contacted. Settings and correctness are stated from the accepted sources listed in each case, not from a fresh application run. Suspected implementation defects are noted for controller evidence, not repaired.

## Authority limits

The builder recruits and conducts participant sessions and owns product closure. The controller prepares tasks, collates evidence and integrates accepted output. This package grants no spending, signing, funding, broadcast, deployment, publication, tracker or personal-data authority. Concurrent provider or model calls are outside this task.