# Demo and pitch scripts

Task OC-P41-PREP-20261010-01, issue #48. Prepared 2026-10-10.

Scope: preparation only. The timings are planned, not rehearsed. Every live segment is conditional until its acceptance condition passes. A recording cannot replace an unbuilt mechanic.

## 1. Technical demo, at most 2:55

Total planned: 175 seconds. The contest cap is 3:00 (180 seconds), so the plan keeps a 5-second margin.

Screens come from the [feature map](../../../.agents/skills/verify-edge-os/feature-map.md). Evidence paths come from [verify-edge-os](../../../.agents/skills/verify-edge-os/SKILL.md) and the [release journey checks](../release-journey/RELEASE_JOURNEY_CHECKS.md).

| # | Segment | Time | Screen or source | Shows | State |
|---|---|---|---|---|---|
| 1 | Hook: the trader's job | 0:00 to 0:10 (10s) | Title card | Onchain traders hold the idea but not the pipeline | ready |
| 2 | Saved Research | 0:10 to 0:40 (30s) | ResearchHome, RequestPage (`POST /v1/research/requests`, `GET /v1/research/requests/{id}`) | Request, clarification, saved result | implemented |
| 3 | Exact rules | 0:40 to 1:05 (25s) | RulesReview (`GET /v1/strategies/{id}/revisions/{revision_id}`) | Exact thresholds, groupings, content hash, provenance | implemented |
| 4 | Labelled replay | 1:05 to 1:30 (25s) | ReplayResult, SpotReplayPanel (`tests/p03/reopen.spec.mjs`) | Saved synthetic replay loads without recompute | implemented, labelled synthetic |
| 5 | Bounded permission | 1:30 to 1:55 (25s) | AccountViews, Agents (`GET /v1/account-views`) | Immutable permission snapshots; evidence separate from permission | implemented as authored records |
| 6 | Application action | 1:55 to 2:25 (30s) | Live app action | One controlled action through the application | CONDITIONAL, not built |
| 7 | Receipt and effects | 2:25 to 2:45 (20s) | Live receipt view | Transaction receipt, decoded effects, actual holdings | CONDITIONAL, not built |
| 8 | Recovery and revocation | 2:45 to 2:55 (10s) | Live recovery and removal views | Interrupted reconciliation; owner removal; residual holdings | CONDITIONAL, not built |

### Segment notes

- Segments 2 to 5 exist today on synthetic fixtures. The demo writes them on screen with a visible synthetic label.
- Segments 6 to 8 need accepted P20/P22/P23/P24/P25/P30 release portions, an exact live packet and a deployed host. Until then they stay off the recording or appear only as labelled planned steps.
- The demo must not substitute an external swap, a fixture receipt or a signing-only proof for the integrated application action. The release cut says those cannot replace the core mechanic.
- Segment 5 separates five things: evidence, permission, local stop, signer removal and residual exposure. In the current build, only evidence and permission snapshots exist. The other three stay labelled not implemented.

### Demo evidence pointers

- Browser records: `.scratch/p03/evidence/<run_id>/ui/ui-results.json` and `ui/screenshots/`.
- Stored rows: `.scratch/p03/evidence/<run_id>/sql-inspection.json`.
- Ownership: `.scratch/p03/evidence/<run_id>/ownership-drive.json`.

### Fallback if the live portion stays unproved

If the integrated live path does not qualify, the demo ends at segment 5 and labels the live portion unproved. A research-only delivery needs a new builder decision and may not satisfy the onchain track. The recording must not present execution as optional while claiming the full product is delivered.

## 2. Pitch script, at most 2:00

Total planned: 120 seconds. Lead with the trader's job and the assembly cost.

### Positioning (from the release cut)

Use this sentence as the fixed claim: "Edge OS gives onchain traders a structured path from a market hypothesis to exact strategy rules and bounded execution, and it preserves the evidence and decision history throughout."

### Script

| Time | Beat | Content |
|---|---|---|
| 0:00 to 0:20 | The job and the cost | An onchain trader has an idea about a market. To act on it, the trader assembles a data pipeline, a research notebook, a simulator and a trading runtime, then writes permissions by hand. That assembly is slow and easy to get wrong. |
| 0:20 to 0:45 | What Edge OS does | Edge OS takes the idea. It asks for the missing meaning, compiles exact rules, keeps the evidence and its contradictions, and separates a finding from permission to trade. |
| 0:45 to 1:10 | Evidence lineage | Every step keeps its record. The saved result, the exact strategy revision and the decision history stay inspectable. A favourable study still does not grant permission. |
| 1:10 to 1:30 | Exact permission and recovery | The user approves a bounded mandate for one wallet and one revision. The worker reconciles an interrupted action instead of repeating it. The owner can revoke the agent, and revocation keeps owner access. |
| 1:30 to 1:50 | What is proved, what is not | Say plainly: the research-to-replay path works on labelled fixtures. The live path is the intended demonstration and is not yet proved. |
| 1:50 to 2:00 | Close | The next step is the qualified live path and the first trader sessions. |

### Claims to keep conditional

State these as intended where they are unproved:

- The live Monad/Kuru swap and its receipt.
- Wallet creation, funding and removal in the application.
- Participant comprehension and demand.

Do not claim profitable strategies, comparative safety, validated demand, exactly-once execution or general autonomous operation. Omit competitor comparisons unless a source verifies them.

### Retained pitch-video requirements

The pitch video is at most 2 minutes. It introduces the team, the problem and the reason to build. It is separate from the 3-minute technical demo.

## 3. Recording prerequisites

- A deployed live product for the technical demo segment 6 and later.
- A frozen release claim from the 12 October checkpoint.
- Approved logo and screens for both videos.
- The exact revision recorded when the demo runs.

No recording, contact or submission happens in this preparation stage.
