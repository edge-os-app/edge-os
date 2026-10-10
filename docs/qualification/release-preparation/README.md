# P41 release preparation

Task OC-P41-PREP-20261010-01, issue [edge-os-app/edge-os#48](https://github.com/edge-os-app/edge-os/issues/48). Base `5689e1d6e71edc956941f33e61488c5d03d37808`. Prepared 2026-10-10 in the `p41-opencode-worker` worktree.

Stage: **documentation and preparation only.** This package freezes the release evidence plan, the deployment and access handoff, the technical and pitch scripts, and the submission checklist. It does not deploy, publish, submit, record, contact a judge, or claim any unrun qualification.

## Proposed verdicts

- **DOCUMENTATION / PREPARATION coverage: PASS within the scope below.** Each document names its accepted source, separates inspected source from platform documentation from UNTESTED support, and leaves unproved capability conditional.
- **Deployment, hosting and judge access: NOT RUN.** No host, account, plan or live URL exists. Hosting stays `UNSELECTED` under the [release cut](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md).
- **Live product claim: UNPROVED.** The live portion of the demonstration depends on accepted P20/P22/P23/P24/P25/P30 release portions and on the exact host and deployment authority.
- **Final release, deployment and submission: INCOMPLETE.** Full issue #48 stays OPEN.

## Documents

- [HOSTING_AND_ACCESS_ASSESSMENT.md](HOSTING_AND_ACCESS_ASSESSMENT.md): the actual web, API, PostgreSQL and future bounded-worker topology, two practical arrangements against current official platform documentation, and the production concerns that each must satisfy. Every arrangement is UNTESTED for this application.
- [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md): the accountable roles, the cut decision dates, the required artifacts, the asset inventory, and the exact unmet conditions.
- [DEMO_AND_PITCH_SCRIPTS.md](DEMO_AND_PITCH_SCRIPTS.md): the technical demo sequence with planned timing at most 2:55, and the pitch script within 2:00.
- [CLAIM_SOURCE_MAP.md](CLAIM_SOURCE_MAP.md): each proposed claim and artifact mapped to its exact accepted source and its pending acceptance condition.

## Accepted sources

- [Release cut](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md), builder-approved 2026-10-10.
- [Hackathon brief](../../research/00_HACKATHON_BRIEF.md), with public pages rechecked 2026-10-10.
- [P01 application, authentication and storage profile](../../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md).
- [Backend package layout](../../implementation/BACKEND_PACKAGE_LAYOUT.md).
- [P40 release journey preparation](../release-journey/README.md), [checks](../release-journey/RELEASE_JOURNEY_CHECKS.md) and [trader task guide](../release-journey/TRADER_TASK_GUIDE.md).
- [Kuru Flow preparation package](../kuru-flow/README.md) and [Probe B plan](../kuru-flow/INTEGRATED_PROBE_B_PLAN.md).
- [P16 signing result](../p16/PROVIDER_SIGNING_RESULT_2026-10-08.md).
- [Build brief](../../EDGE_OS_BUILD_BRIEF.md), [README](../../../README.md) and [verify-edge-os skill](../../../.agents/skills/verify-edge-os/SKILL.md).

## Scope and exclusions

Owned new path: `docs/qualification/release-preparation/` only. This package changes no application code, shared document, contract, migration, script, lockfile or verifier entry. It generates no artwork, installs nothing, and runs no application recipe. Source inspection and public documentation checks supply the facts.

## Authority limits

The builder owns product decisions, account access, deployment and every submission action. The controller prepares evidence and scripts and integrates accepted output. This package grants no spending, signing, funding, broadcast, deployment, publication, tracker or recording authority. It selects no vendor and purchases nothing.
