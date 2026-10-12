# Demo and judge-access plan (preparation only; no recording, no submission)

Task RELEASE-HOST-PREP-L4-20261012-01, issue edge-os-app/edge-os#48. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`, tree `31e71d47b63cf14686470d46e5469de59565d3f9`. Prepared 2026-10-12.

Status: **preparation only.** No recording, account UI, login, submission or participant contact happened. The timings are planned, not rehearsed. Every live segment is conditional until its acceptance condition passes. A recording cannot replace an unbuilt mechanic.

This plan reuses the accepted [demo and pitch scripts](../release-preparation/DEMO_AND_PITCH_SCRIPTS.md) and the [release journey checks](../release-journey/RELEASE_JOURNEY_CHECKS.md), and refreshes them for the expanded release. It does not overwrite them.

## 1. Evidence-led technical demo (planned ≤ 2:55; contest cap 3:00)

The technical demo shows the connected research-to-bounded-execution flow. Each segment states what exists and what is conditional.

| # | Segment | Time | Screen / source | Shows | State at base `3e7ff8bd` |
|---|---|---|---|---|---|
| 1 | Hook: the trader's job | 0:00–0:10 | Title card | An onchain trader holds the idea, not the pipeline | ready |
| 2 | Saved research + actual-history investigation | 0:10–0:35 | ResearchHome, RequestPage, InvestigationReview | Request, clarification, exact hypothesis/rule mapping, a source-linked result | recorded-response LOCAL; actual history CONDITIONAL |
| 3 | Exact rules | 0:35–0:55 | RulesReview | Exact thresholds, groupings, content hash, provenance | implemented |
| 4 | Labelled hypothetical replay | 0:55–1:15 | ReplayResult | Saved replay opens without recompute; "simulated fills" | implemented (synthetic); actual-history replay CONDITIONAL |
| 5 | Hermes bounded interpretation | 1:15–1:30 | Interpretation attempts/usage | Bounded attempt, honest unknown usage | local fake-provider; real model CONDITIONAL |
| 6 | Nansen report in the Research journey | 1:30–1:50 | Nansen report view | Source-linked findings, coverage/uncertainty, supported vs unsupported | local package accepted; core mount MISSING |
| 7 | Evidence vs permission | 1:50–2:05 | AccountViews, permission snapshots | Immutable permission snapshots; evidence separate from permission | implemented (authored records) |
| 8 | Bounded action + receipt | 2:05–2:30 | Agent action + receipt view | One controlled action; transaction receipt; actual holdings | CONDITIONAL, not built |
| 9 | Recovery, stop, removal, residual | 2:30–2:45 | Recovery/stop/removal views | Original-action reconciliation; scoped stop; removal; residual holdings | CONDITIONAL, not built |
| 10 | Recurring health | 2:45–2:55 | Deployment health view | Last attempt/completion, next work, wait/fault reason | CONDITIONAL (P27 not built) |

### Displayed evidence limits (keep on screen)

- Segments 2–7 exist today on labelled synthetic/recorded fixtures. Write the synthetic label on screen.
- Segments 5 (real model), 6 (Nansen mount), 8, 9 and 10 need their accepted portions, an exact live packet and a deployed host. Until then they stay off the recording or appear only as labelled planned steps.
- Keep five things distinct on screen: **evidence, permission, a local stop, signer removal and residual exposure**. In the current build only evidence and permission snapshots exist.
- Do not substitute an external swap, a fixture receipt or a signing-only proof for the integrated application action.
- If the live portion stays unproved, end the demo at segment 7 and label the live portion unproved. A research-only delivery needs a new builder decision.

## 2. Pitch script (planned ≤ 2:00)

Reuse the accepted pitch from [DEMO_AND_PITCH_SCRIPTS.md](../release-preparation/DEMO_AND_PITCH_SCRIPTS.md) section 2. Keep these claims conditional: the live Monad/Kuru swap and receipt; wallet creation/funding/removal in the application; participant comprehension and demand. Do not claim profitable strategies, comparative safety, validated demand, exactly-once execution or general autonomous operation.

Add one beat for the expanded release: the actual-data research path and the Nansen integration. It stays labelled intended until RG02/RG05 and the Nansen mount are qualified.

## 3. Interactive checks (prepare; do not invent PASS)

Prepare these checks with observed-versus-assisted results. Use the existing [trader task guide](../release-journey/TRADER_TASK_GUIDE.md). No five-user PASS is invented.

| Check | Method | Evidence rule |
|---|---|---|
| Desktop 1280px | Playwright `desktop` project; mapped verifier | Executed historically; re-drive on the release revision |
| Narrow 390px | Playwright `mobile-390` (390×844, touch) | Executed historically; a 390px viewport is not a physical phone |
| Keyboard + focus + labels | quality focus-ring/44px/label checks; `runtime.spec.mjs` | MAPPED; full keyboard traversal NOT RUN |
| Physical phone touch | No device test exists | NOT RUN, unavailable |
| Screen reader | No screen-reader session exists | NOT RUN, unavailable |
| Trader tasks T1–T5 | Builder conducts; first answer recorded verbatim | Participant absence stays UNRESOLVED |

Session prerequisites: a candidate revision, a supported authorized manual-session setup (the default verifier tears its run down), the surfaces listed in the guide, and available participants. The manual-session prerequisite remains **BLOCKED** in the preparation package until the controller or builder supplies one.

## 4. Judge and public access proof inventory

| Item | Requirement | Status at preparation |
|---|---|---|
| Working product | Live product on Monad mainnet or testnet | MISSING |
| Live link + access instructions | Live URL plus instructions and any test credentials | MISSING |
| Public GitHub repository | Fully accessible to the judge address | NOT DONE; repository is PRIVATE |
| Project logo/graphic | JPG/JPEG/PNG/WEBP ≤ 3 MB | MISSING |
| Technical demo video | ≤ 3 min on YouTube/Loom/Vimeo; shows the live product | MISSING |
| Pitch video | ≤ 2 min; team, problem, reason to build | MISSING |
| Written description | Short project description | NOT PREPARED |
| Event-period work evidence | Dated commits and accepted release record | PARTIAL |
| Primary track + bounties | One track and selected sponsors | SELECTED (confirmed); bounty cards need a fresh check |

## 5. Deadlines (accepted schedule; recheck the official page)

| Event | Value | Africa/Kinshasa (UTC+1) |
|---|---|---|
| Submission deadline | 2026-10-14 03:59 UTC | 2026-10-14 04:59 |
| Judging | 2026-10-14 to 2026-11-03 23:59 UTC | 2026-10-14 04:59 to 2026-11-04 00:59 |
| Winners announced | 2026-11-04 17:00 UTC | 2026-11-04 18:00 |
| Internal cutoff | builder decision | 2026-10-13 23:59 |

Source: `docs/research/00_HACKATHON_BRIEF.md` section 4, with public pages rechecked 2026-10-10. The authenticated timeline `S29` controls the local plan; the public page `S1` disagrees on two entries. Before submission, recheck the official rules and submission form fields from the current official source and record the source URL and date.

## 6. Official-rule check (allowed: public lookup only)

- Allowed now: read public official pages for the timeline, tracks and submission fields.
- Not allowed: account UI, login, submission, judge contact or recording.
- If a current detailed card is inaccessible, retain the dated/screenshot criteria and mark the fields unchecked; continue preparation.
- Confirm before submission: the current rubric, the exact bounty terms for each selected bounty, the submission form fields, and eligibility/KYC/tax/terms.

## 7. Recording prerequisites

- A deployed live product for segments 8–10.
- A frozen release claim from the current checkpoint.
- Approved logo and screens.
- The exact revision recorded when the demo runs.
- A replayable local proof in case the live network fails (a replay is not live evidence).

## 8. Builder decisions required

- A revised smaller release/claim needs an explicit builder decision; do not silently fall back to a fixture demo.
- The exact claim freeze, host, judge access and repository visibility are builder decisions.
