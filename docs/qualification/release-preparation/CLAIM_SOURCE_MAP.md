# Claim and artifact source map

Task OC-P41-PREP-20261010-01, issue #48. Prepared 2026-10-10. Base `5689e1d6e71edc956941f33e61488c5d03d37808`.

Scope: preparation only. This map ties every proposed claim and artifact to its accepted source and its pending acceptance condition. A preparation PASS does not mean any listed condition passed.

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
