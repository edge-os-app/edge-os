# Claim and artifact source map

Task OC-P41-PREP-20261010-01, issue #48. Prepared 2026-10-10. Base `5689e1d6e71edc956941f33e61488c5d03d37808`.

Scope: preparation only. This map ties every proposed claim and artifact to its accepted source and its pending acceptance condition. A preparation PASS does not mean any listed condition passed.

## Current status, #58 Stage 1, Task 6 and Stage 2 local milestones (2026-10-12)

This section supersedes the current-status cells below for P22–P26/P30; those rows remain as preparation history. Evidence class: local fixture only (`EDGE_OS_EXECUTION_MODE=fixture`, refused in production). Source: `docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md` and the `verify-edge-os` feature-map sections "Connected financial journey", "Recorded-history research journey" and "Public-runtime preparation"; Stage 2 records in `docs/qualification/public-runtime/`.

| Capability | Current status | Evidence class | Still missing |
|---|---|---|---|
| Wallet setup for an exact revision; browser completion after independent lookup | Connected (routes, screens, verifier) | Local fixture | Real Privy creation/lookup (P16/P17, Stage 3) |
| Funding declaration, reviewed deposits, once-only credit, holdings apart from deposits | Connected | Local fixture ports | Real deposit/holdings observation (Stage 3) |
| Exact review and INACTIVE adoption; server activation verdict | Connected | Local fixture qualification | Real activation after P20/P21 qualification |
| Bounded evaluation, decision before intent, admission, exclusive submission | Connected with a durable worker | Local fixture market, quote and transport | Real observations, quote, signing, broadcast (Stage 3); no continuing trading |
| Original-action recovery after lost acknowledgement or process death | Connected | Local fixture receipts | Real receipts and chain identities (Stage 3) |
| Scoped stop; removal denying from REQUESTED | Connected at admission and submission | Local fixture removal observation | Real signer removal (Stage 3) |
| Recorded-history declaration, original jobs, dataset, report, market adoption and labelled replay (RG01–RG06) | Connected for recorded responses (Task 6 local milestone) | SYNTHETIC recorded responses | Actual collection and inference (approval packet pending); actual-history replay (P13 evidence-class change pending); G05 LIMITED representation |
| F1 service-backed account projections (read-only, unknown stays unknown) | Connected (Stage 2 local candidate) | Local fixture ports | Real provider data (Stage 3) |
| F2 failed read-back keeps change controls paused | Repaired (Stage 2 local candidate) | Local browser and unit tests | — |
| F3 original references before effect for every real transport | TRACKED, NOT REPAIRED | — | Stage 3 adapter seam |
| F4 worker schema-drift stop; restore/rollback runbook | Repaired locally; runbook rehearsed on a local database | Local | Hosted rehearsal |
| F5 manual accessibility | Keyboard pass on owned connected-agent, funding and projection surfaces | Local browser | Screen reader NOT_RUN; research, adoption and replay surfaces |
| F6 dependency advisory reachability | Assessed read-only (25 advisories, all through the wallet SDK) | Build inspection | Controller disposition; no lockfile change |
| Shared owner/global quotas, write rate, job and timeout limits, production startup and readiness checks | Implemented (Stage 2 local candidate) | Local PostgreSQL, separate processes | Hosted multi-process load; provider spending caps |
| Hosted multi-user, real login (PU01–PU08); host selection | NOT RUN; hosting proposal only (not selected or bought) | — | Builder decision and Stage 3 |

## 1. Proposed claims

| Claim | Exact accepted source | Current status | Pending acceptance condition |
|---|---|---|---|
| A trader submits a request and receives a saved result | [README current status](../../../README.md); [feature map](../../../.agents/skills/verify-edge-os/feature-map.md); [release-journey J01 to J08](../release-journey/RELEASE_JOURNEY_CHECKS.md) | Implemented with fixtures | Real provider interpretation is P05; it stays unwired |
| Rules compile to an exact immutable revision with a content hash | [P06 compiler profile](../../implementation/P06_COMPILER_PROFILE.md); [feature map](../../../.agents/skills/verify-edge-os/feature-map.md) | Implemented, price and volume subset | Market and provider qualification remain open |
| A saved synthetic replay reopens without recompute | [feature map](../../../.agents/skills/verify-edge-os/feature-map.md); [release-journey J05](../release-journey/RELEASE_JOURNEY_CHECKS.md) | Implemented, labelled synthetic | Real history is P07 |
| Account views show permission snapshots, separate from evidence | [account views profile](../../implementation/ACCOUNT_VIEWS_PROFILE.md); [release-journey J09 and section 11](../release-journey/RELEASE_JOURNEY_CHECKS.md) | Implemented as authored synthetic records | Live wallet state and production auth are P01/P05 |
| Another owner cannot read, answer or publish a record | [release-journey J06](../release-journey/RELEASE_JOURNEY_CHECKS.md); `apps/api/tests/test_ownership.py`, `test_live.py` | Tested at application level with fixtures | Real Privy auth and the cross-user backend check are P16 and P01 |
| One controlled Kuru swap runs through the application | [release cut: P20 row](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md); [Probe B plan](../kuru-flow/INTEGRATED_PROBE_B_PLAN.md) | NOT RUN | P22 to P25 and P30 release portions, an exact live packet, host and funding authority |
| Bounded permission and deterministic admission | [release cut: P22 row](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) | NOT IMPLEMENTED | Accepted P06/P15/P19 inputs; P21 profile. P22's gate is at 3/3 with a worker hold and no builder extension |
| Exclusive wallet and network claim, no duplicate action | [release cut: P23 row](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) | WAITS on P22 | Accepted P22 release portion |
| Original-action recovery after acknowledgement loss | [release cut: P24 row](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) | WAITS on P23 | Accepted P23 portion; live transport through P20 |
| Scoped stop that denies unsent work | [release cut: P25 row](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) | NOT IMPLEMENTED | Accepted P19/P23/P24 portions |
| Owner revocation that keeps owner access and residual holdings | [release cut: P30 row](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) | NOT IMPLEMENTED | Final P20 and P26 evidence |
| Signer removal refuses the removed signer | [P16 signing result](../p16/PROVIDER_SIGNING_RESULT_2026-10-08.md) | Sign-only, one owner, testnet 10143 | Application-level removal output, creation/recovery and cross-user checks stay open |
| A live product is deployed on Monad | [release cut: P41 row](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) | NOT DONE | Host and deployment authority plus every claimed capability |
| Participant comprehension evidence exists | [trader task guide](../release-journey/TRADER_TASK_GUIDE.md) | NOT RUN | Participant availability; the manual-session prerequisite is BLOCKED |
| The P40 journey runs at runtime | [release-journey checks](../release-journey/RELEASE_JOURNEY_CHECKS.md) | UNRUN, mapped only | A fresh runtime run on the chosen revision |

## 2. Proposed artifacts

| Artifact | Exact accepted source | Current status | Pending acceptance condition |
|---|---|---|---|
| Hosting and access assessment | This package, [HOSTING_AND_ACCESS_ASSESSMENT.md](HOSTING_AND_ACCESS_ASSESSMENT.md) | Drafted; arrangements UNTESTED | Builder host, plan and cost decision |
| Submission checklist | This package, [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) | Drafted | Builder confirms the frozen claim and artifacts |
| Demo and pitch scripts | This package, [DEMO_AND_PITCH_SCRIPTS.md](DEMO_AND_PITCH_SCRIPTS.md) | Drafted; live segments conditional | Live qualification and a frozen claim |
| Logo or graphic | [hackathon brief section 10](../../research/00_HACKATHON_BRIEF.md) | MISSING | Builder approves the asset |
| Technical and pitch videos | [hackathon brief section 10](../../research/00_HACKATHON_BRIEF.md) | MISSING | A deployed live product and the scripts |
| Public repository access for the judge | [hackathon brief section 10](../../research/00_HACKATHON_BRIEF.md) | NOT DONE | Builder changes repository visibility |

## 3. Concepts that stay distinct

Keep these apart in every claim and screen:

- **Fixture or research evidence** versus a live result. Synthetic fixtures and authored account records are not live proof.
- **Evidence** versus **authority**. A favourable study grants no permission; a compilation grants no permission.
- **A local stop** versus **revocation** versus **signer removal** versus **remaining holdings**. A local halt is not signer removal or liquidation. Revocation stops new submissions but does not undo a broadcast transaction or remove remaining holdings.

## 4. Open gaps carried forward

- P05: the Hermes adapter is staged outside the published tree and is not wired into Research. Real interpretation waits on P05 and a separately approved real-model run.
- P22 hold: the P22 gate is exhausted at 3/3 and the worker hold has no builder extension. Local P23, P24 and P25 stay blocked.
- P40: participant evidence and the runtime journey are unrun.
- Host and access: host, plan, cost, judge access and repository visibility are unresolved.
- P16: application-level creation, lost-response, restart and cross-user checks remain open.

## 5. Authority

The builder owns product decisions, account access, deployment, recording and submission. The controller prepares evidence and integrates accepted output. This map grants no spending, signing, funding, broadcast, deployment, publication or submission authority. Full issue #48 stays OPEN.
