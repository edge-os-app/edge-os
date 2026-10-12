# Release evidence map (RC/PU/RG/IC/AUT trace; preparation only)

Task RELEASE-HOST-PREP-L4-20261012-01, issue edge-os-app/edge-os#48. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`, tree `31e71d47b63cf14686470d46e5469de59565d3f9`. Prepared 2026-10-12.

Status: **traceability only.** This map ties every release criterion to its owner, exact accepted source, existing evidence or missing proof, prerequisite, proposed test and required approval. A preparation PASS is not a criterion PASS. No criterion below is marked PASS. Every live, hosted, provider or participant result is `NOT_RUN`.

Sources of the criterion IDs:

- `docs/planning/EDGE_OS_USER_RELEASE_TICKET_2026-10-12.md` (RG01–RG06, IC01–IC08, AUT01–AUT08).
- `docs/planning/EDGE_OS_RELEASE_ACCEPTANCE_CHECKLIST_2026-10-12.md` (RC01–RC20 and PU01–PU08, with detail).
- `.scratch/release-host-prep/ISSUE47.json` and `ISSUE48.json` (P40/P41 retained criteria).
- `docs/research/METROPOLIS_BOUNTY_REQUIREMENTS_RECHECK_2026-10-07.md` and `docs/research/NANSEN_BOUNTY_PICKUP_RECHECK_2026-10-12.md` (selected sponsor criteria).

## Evidence classes

- **LOCAL** — local fixture or local component evidence;
- **COMPONENT** — an accepted package/module at its own scope;
- **PUBLICATION** — main-branch publication or repository visibility;
- **ACTUAL** — real provider/chain/model/data evidence;
- **HOSTED** — real host, network, database or multi-process evidence;
- **PARTICIPANT** — human comprehension or accessibility evidence;
- **MISSING_CONNECTION** — required application composition is absent at the inspected base;
- **NOT_RUN** — the final check did not run.

## Retention rules

- Every full ticket stays **OPEN** until its complete retained requirements pass, or the builder approves an explicit follow-up transfer.
- The accepted local integration `3e7ff8bd` differs from published main `3292bb784cf00a22dd4b9e943c0df585e5ef41e5`. A future publication reconcile, its reviews and a manual approval are required before main can reproduce the release.
- No fixture PASS is promoted to actual or hosted evidence.
- No new scope exclusion is created here. RG02/RG05 actual-history qualification, IC08 restrictions, AUT01–AUT08 and P27 remain required.
- **P31 remains a P27 dependency.** Its matching direct/chat health evidence is not independently dispatched here.
- The Nansen core mount, its durable application save/reopen and its actual qualification remain **missing**.

## Owner keys

| Key | Owner |
|---|---|
| L2 | Lane 2, Claude, #58 shared composition and connected journey |
| L1 | Lane 1, Hermes job support and P05 provider safeguards |
| L3 | Lane 3, P21/P20 enforcement preparation and (later) P31 |
| L4 | Lane 4 (this task), P40/P41 host/demo preparation |
| QUANT | Quant contributor, P14 numerical replay |
| BUILDER | Builder (product, accounts, authority) |

## 1. RC01–RC20

| ID | Requirement (short) | Owner | Accepted source | Existing evidence / class | Missing proof | Prerequisite | Proposed test | Approval |
|---|---|---|---|---|---|---|---|---|
| RC01 | Finish released real-model interpretation on frozen cases; no hidden retry | L1 | P05 #15; `hermes-provider/`; Hermes helper `dbd95668`; ticket | Local fake-provider path accepted; accepted LOCAL Hermes job transport support integrated `dbd95668` (authored transport only; actual route refused; not mounted) | Real model cases (thesis/hunch/no-thesis/unsupported/follow-up), paraphrase/conflict/truncation; exact text/config/attempt/revision/latency/usage | Released P05 safeguards + lane-1 support (accepted `dbd95668`; application mount pending); inference budget | Frozen semantic cases on the released runtime; inspect attempts/settlements SQL | Model/inference packet |
| RC02 | Owner-linked wallet creation; lost-response/restart; two owners | L2/L3 | P16 #14; ticket | Sign-only one-owner testnet evidence, COMPONENT | Selected creation route, tuple isolation, owner access on the actual backend | Real Privy app; P20/P21 | Two-owner tuple-change tests; distinct local vs provider denial | Auth + provider packet |
| RC03 | Connect qualified actual creation and exact identity lookup | L2 | P17 #22; `wallet_setup/` | Local fixture setup, LOCAL | Actual creation, cancellation, lost reply, restart readback, cross-owner refusal | Real provider | Browser + API + SQL cross-owner/restart checks | Provider packet |
| RC04 | Migrated owner-scoped funding API + Funds controls; reconcile observations once | L2 | P18 #26; `funding/` | Funding module LOCAL; routes mounted at base | Actual deposit observation; amount credited once; allowance/expiry/stop | Real provider; migration already at `0008` | Confirmed/pending/failed/unknown/duplicate reconciliation checks | Provider packet |
| RC05 | Prove selected restrictions, raw units, capacity, exposure | L3 | P21 #20; `route-restrictions/`; `docs/qualification/independent-enforcement/` | Authored restriction package, COMPONENT; independent-enforcement prep accepted LOCAL and integrated `f84ef415` (boundary-only feasibility) | Opaque-program `program` byte equality, tuple-calldata paths, deployed `143` bytecode identity, native MON treatment; independent control; residual exposure | P20/P21 enforcement | Control-to-enforcer evidence; independent denial | Design decision + live packet |
| RC06 | Migrate and connect admission to saved identity; atomic reservation under contention | L2 | P22 #24; `admission/` | Durable admission/reservations, LOCAL | Contention durability on host; unknown required cost denies | Host + qualified controls | Concurrent reservation test; unavailable-control denial | Host packet |
| RC07 | Bounded background evaluation; save decisions before intent; exclusive claims | L2 | P23 #29; `execution/worker.py` | Worker + decision flow LOCAL | Real forward observation; waiting/blocking UI; revalidate before submit | IC02 observation port | Signal/no-signal/ineligible; restart creates no second intent | Provider packet |
| RC08 | Connect receipt/status/recovery to original intent/attempt/reference | L2 | P24 #33; `execution/service.py`, `recovery/`; ORIGINAL-LOCAL `8a1d65dd` → `795682bf` | Local recovery LOCAL; ORIGINAL-LOCAL accepted/integrated `795682bf` and safely released (LOCAL authored recovery, not actual signing/provider/chain) | Actual receipts/fees/gas; confirmed/reverted/denied/unknown | Real chain | Interruption before/after broadcast; byte-identical resend check | Live packet |
| RC09 | Durable scoped-stop API/UI; denial at admission and submission | L2 | P25 #35; `stops/` | `SubmissionControls` LOCAL; REQUESTED denies | Hosted/restart-sticky stop history; unaffected B; residual holdings | Host | Stop vs claim; restart-sticky stop | Host packet |
| RC10 | Exact grouped INACTIVE consent review and idempotent adoption; deny drift | L2 | P26 #38; `consent/` | Grouped review + adoption LOCAL | Real approval/policy/deployment identities; saved INACTIVE stays inactive | P20/P21 qualification | Drift/unknown/stale/wrong-wallet denial; idempotent adopt | Live packet |
| RC11 | Integrated Probe B: one approved Kuru action while owner offline | L2/L3 | P20 #19; ticket; `kuru-flow-adapter/` | Offline adapter COMPONENT | Frozen live packet; actual action, receipt/effects, independent denial, removal | Builder live packet; P21 | One approved action end-to-end; helper transaction does not count | Live packet |
| RC12 | Removal denial at admission/submission under correct lock | L2 | P30 #40; `revocation/` | Local removal/reconciliation LOCAL | Provider operation; in-flight removal cannot allow new work | Real provider | Post-removal A denied, B unchanged, owner access retained | Live packet |
| RC13 | Re-drive the release journey; accessibility + participant evidence | L2/L4 | P40 #47; `release-journey/` | Preparation accepted; runtime UNRUN | Desktop/390px, keyboard/phone/screen-reader, unfamiliar-trader tasks | Running revision; participants | Journey drive + observation forms | Participant availability |
| RC14 | Fresh-checkout host start; hosted persistence/auth/health; judge access; demo/assets | L4 | P41 #48; this package | Preparation accepted; host UNRUN (target: builder-selected Contabo VPS) | Fresh-checkout image build/migrate/start, hosted persistence/auth, exact judge access, recordings | Host facts (H13) + deployment authority | Runbook Stage 1–8 on the Contabo VPS | Deployment/publication authority |
| RC15 | Retain accepted P02/P03/P06/P08/P09/P12/P13/P19 behavior after wiring | L2 | Ticket; feature-map | Accepted regressions LOCAL | Final combined verifier on the release candidate | Integrated candidate | Affected tests + full mapped verifier | none (check) |
| RC16 | P04 actual provider-only egress, hosting resources, deadlines, spending | L2/L4 | Prior P04; host packet H1 | Local recipe accepted; host NOT_RUN | Enforced egress; resource/deadline/spend behavior | H1 decision; provider packet | Host network + spending checks | Egress + provider packet |
| RC17 | Keep synthetic replay labelled; add RG02/RG05 actual-history replay | L2 | Ticket RG02/RG05; `replay/` | Synthetic replay LOCAL | Actual-history qualification and labelled historical replay | RG02 (actual dataset) | Replay on actual history with simulated fills | Data packet |
| RC18 | Reuse P43 Organic shell/design; audit remaining rendered evidence | L2/L4 | P43 #8; `docs/design/p43/` | Initial slice approved; export EXISTS | Remaining rendered-direction/handoff evidence | Running revision | Rendered audit | none (check) |
| RC19 | Publish accepted local continuations before claiming main contains them | BUILDER | Ticket; handoff | Main `3292bb` lags `3e7ff8bd` | Publication, its reviews and manual approval | Builder authorization | Ancestry check on published main | Publication authority |
| RC20 | Refresh P40/P41 claim/source and journey maps | L4 | P41; this package | This package refreshes current status; prior history retained | Publish refreshed maps under tracker authority | Tracker authority | Review refreshed maps | Tracker authority |

## 2. PU01–PU08

| ID | Requirement (short) | Owner | Accepted source | Existing evidence / class | Missing proof | Prerequisite | Proposed test | Approval |
|---|---|---|---|---|---|---|---|---|
| PU01 | Real production Privy login, session rejection, sign-out, owner change | L2 | Ticket; `core/authentication.py` | Code path exists, LOCAL | Real hosted login/session behavior | Real Privy app + host | Hosted browser login matrix | Auth packet |
| PU02 | Two consenting owners across every connected operation | L2 | Ticket | Local two-owner denial LOCAL | Hosted cross-owner tests with guessed IDs | Host + two owners | Cross-owner/cross-wallet/position matrix | Auth packet |
| PU03 | Shared durable quotas/caps across processes/restarts; unknown stays liable | L2 | `usage/quota.py`; ticket | Local multi-process evidence (runtime_phase), LOCAL | Hosted multi-process load; provider-side caps | Host | Reserved-before-call; killed process; duplicate settlement | Host packet |
| PU04 | Real model turns isolate content/state; no credentials in logs/evidence | L1/L2 | Ticket; P05; Hermes helper `dbd95668` | Fake-provider isolation only; accepted LOCAL helper runs a no-network/read-only job container but the credential copy is shared with the Hermes job process (host-held relay decision needed) | Hosted runtime network restriction, cleanup, deadlines | Released P05 safeguards; host-held credential relay decision | Isolation + cleanup checks | Model/host packet |
| PU05 | Forward-migrated financial state; bounded-job startup/recovery; HTTPS/CORS; backup/restore/rollback | L2/L4 | Ticket; `RESTORE_ROLLBACK_RUNBOOK.md` | Local rehearsal LOCAL | Hosted migrate/start/restore/rollback | Host | Runbook Stage 3/6 | Host packet |
| PU06 | Independent owner-linked wallet/policy lifecycle before public funded use | L2/L3 | Ticket | One-wallet evidence only | Multiple independent owners' wallet/policy lifecycle | Real provider | Lifecycle tests with two owners | Provider packet |
| PU07 | Accurate data/retention/deletion/support explanation | L2/L4 | `RETENTION_DELETION_SUPPORT.md` | Proposal from implemented facts | Match to implemented behavior + provider obligations | Implemented behavior | Copy review against code | Builder decision |
| PU08 | Freeze enabled public capabilities, host/build, budgets; builder approves launch | BUILDER | Ticket | NOT_RUN | Enabled-capability freeze; public launch approval | All above | Final freeze review | Builder launch authority |

## 3. RG01–RG06

| ID | Requirement (short) | Owner | Accepted source | Existing evidence / class | Missing proof | Prerequisite | Proposed test | Approval |
|---|---|---|---|---|---|---|---|---|
| RG01 | Real-source/window/variants/controls/access/budget adopted before outcomes | L2 | `USER_RELEASE_INTEGRATION_PROFILE.md` RG01; `research/investigation_adoption.py` | Local recorded-response implementation, LOCAL | Real-source adoption without changing fixture bytes | Task 6 lease | Declaration saved before collection; new hypothesis cannot reuse an example rule | Local (done) / data packet |
| RG02 | Connect P07 Envio + QuickNode corroboration to durable datasets; record provenance | L2 | RG02; `research/history_dataset.py`; P07 library | SOURCE-LOCAL recorded-native evidence, LOCAL | Actual client/credentials/pacing/approved bounds; dataset qualification | P07 + data packet | Dataset passes its applicable qualification; missing stays missing | Data/access packet |
| RG03 | Bounded P10/P11 tool/job/report lifecycle with reserve-before-effect | L2 | RG03; `research/investigation_jobs.py` | Local job lifecycle, LOCAL | Real Hermes tools wait for released safeguards + inference bounds | P05 safeguards | Crash/lost-reply/cancel/deadline/exhausted-budget cases | Model packet |
| RG04 | Run adopted comparison; save/reopen report; honest outcomes | L2 | RG04; `research/comparison_runs.py` | Local descriptive reports, LOCAL | Real-market binding on actual dataset | RG02 | Insufficient/unsupported/contradictory/rejected saved and reopened | Data packet |
| RG05 | Replace synthetic-only replay binding; actual history with hypothetical fills | L2/QUANT | RG05; `replay/history_inputs.py` | Local recorded-native replay, LOCAL | Actual-history replay qualification (runtime evidence-class check) | RG02 | Warm-up/gaps/truncated/lookahead; label "simulated fills" | Data packet |
| RG06 | Fixture regression + opted-in actual-data acceptance in `verify-edge-os` | L2 | RG06; `scripts/p03/`, verify-edge-os | `--actual-data` refuses; default spends nothing, LOCAL | Actual-data acceptance path and adapter | RG01–RG05 | Default credential-free; opt-in with approved packet | Data packet |

## 4. IC01–IC08

| ID | Requirement (short) | Owner | Accepted source | Existing evidence / class | Missing proof | Prerequisite | Proposed test | Approval |
|---|---|---|---|---|---|---|---|---|
| IC01 | Publication UUID/canonical/hash execution identity through consent→receipt; forged/stale deny | L2 | `USER_RELEASE_INTEGRATION_PROFILE.md` IC01; `execution/connected_identity.py` | Resolver LOCAL | Hosted identity resolution | Host | Forged/stale/mismatched identity denial | Host packet |
| IC02 | Trusted market observations with provenance/warm-up/gaps/freshness; stable job identity | L2 | IC02; `core/provider_ports.py` | Fixture observations LOCAL | Real forward-decision feed; wrong-market/time denial | Real provider | Repeated scheduling/restart; stale/wrong-market denial | Provider packet |
| IC03 | Current holdings distinct from deposits; reconciled attribution/reservations | L2 | IC03; `accounts/service_projection.py` | Service projection LOCAL | Real holdings/marks/effects after swaps | Real provider | Holdings vs deposits after swap/external movement | Provider packet |
| IC04 | Owner-linked browser wallet completion + durable server recovery; exact tuple | L2 | IC04; `wallet_setup/service.py` | Local browser completion, LOCAL | Actual creation/lookup; late results; two owners | Real provider | Late-result/two-owner binding tests | Provider packet |
| IC05 | Server-owned activation; fixture activation isolated | L2 | IC05; `execution/worker.py` | Fixture qualification LOCAL | Real activation from P20/P21 qualification | P20/P21 | Activation drift/unsupported-terms denial | Live packet |
| IC06 | Persist original signing/nonce/bytes/hash/reference before/after effect | L2 | IC06; `execution/service.py`; `execution/transport.py`; ORIGINAL-LOCAL `8a1d65dd` → `795682bf` | Fixture records references only when named, LOCAL; ORIGINAL-LOCAL accepted LOCAL: journaled unsigned/signing/nonce/fee/signed-byte/hash lifecycle and no replacement/re-sign on unknown (authored LOCAL, not actual chain) | Fill the references before the effect for every non-fixture transport; real signed bytes/hash, broadcast and chain evidence | P20/P21 | Uncertain-broadcast reconciliation; no replacement | Live packet |
| IC07 | Independently observed receipts/effects; missing actuals stay unknown | L2 | IC07; `recovery/` | Fixture receipts LOCAL | Real receipt/effect observation; wrong-tuple/revert/unknown | Real chain | Missing actuals/gas; wrong tuple; restart convergence | Live packet |
| IC08 | Independent opaque-program limits; acquired/residual exposure; MON treatment | L3 | IC08; route-restrictions; `docs/qualification/independent-enforcement/` | NOT IMPLEMENTED; independent-enforcement prep accepted LOCAL and integrated `f84ef415` (boundary-only feasibility; actual enforcement NOT_RUN) | Full independent enforcement + exposure; MON trading/gas profile | P21 design decision | Control-to-enforcer evidence; exposure proof | Design decision + live packet |

## 5. AUT01–AUT08

| ID | Requirement (short) | Owner | Accepted source | Existing evidence / class | Missing proof | Prerequisite | Proposed test | Approval |
|---|---|---|---|---|---|---|---|---|
| AUT01 | Persistent scheduler; durable occurrences; duplicate ticks/restart create no duplicate | L2 | Ticket AUT01; Task 7 | `schedule`/`run_pending` LOCAL; scheduler NOT IMPLEMENTED | Scheduler with occurrence uniqueness across processes | P27 LOCAL lease | Multi-process duplicate-tick + restart test | Local (lease) |
| AUT02 | Fresh qualified observations with availability/warm-up/missingness; save decision before intent | L2 | AUT02; `execution/worker.py` | Decision flow LOCAL | Real forward feed; quote cannot substitute for rule observations | IC02 | Stale/missing input denies trading | Provider packet |
| AUT03 | Standing permission bounds assets/amounts/cumulative/expiry/stop; no counter reset | L2/L3 | AUT03 | Inactive consent LOCAL | Cumulative counters; no revive after stop/removal/expiry | P20/P21 | Cumulative exhaustion; no reset on repeat | Live packet |
| AUT04 | Reuse admission/claims/reservations/recovery; reconcile before new action | L2 | AUT04 | Original-action recovery LOCAL | Uncertain-original recovery before next action; per-owner independence | Live packet | Duplicate occurrence → one effect; recovery-first ordering | Live packet |
| AUT05 | Qualify entry/full-exit/re-entry; preserve full-exit semantics; exclude additions/partial exits | L2/QUANT | AUT05 | Full-exit LOCAL | Re-entry qualification | P14 boundary | Entry/full-exit/re-entry lifecycle | Live packet |
| AUT06 | Direct health + P31 conversation read the same durable health; restart-sticky stop/removal | L2/L3 | AUT06 | Context controls LOCAL | Matching health projection; P31 conversation | P31 dependency | Health-view agreement; restart-sticky removal | P31 assignment |
| AUT07 | Extend `verify-edge-os` for repeated-slot/contention/failure/restart/two-owner/stop | L2 | AUT07 | Default verifier LOCAL | Recurring-operation journey checks | P27 LOCAL | Contention, expiry, interrupted submission, two-owner checks | Local (lease) |
| AUT08 | Hosted/live repeated automatic evaluations, permitted actions, denials, recovery, revocation | BUILDER/L2 | AUT08 | NOT_RUN | Live recurring-operation packet and results | All above | Bounded operating-window live run | Recurring live packet |

## 6. P40/P41 retained criteria (issue snapshots)

| Criterion | Owner | Accepted source | Existing evidence / class | Missing proof | Prerequisite | Proposed test | Approval |
|---|---|---|---|---|---|---|---|
| P40 journey runtime verification | L2/L4 | `ISSUE47.json`; `release-journey/` | Preparation accepted; runtime UNRUN | Fresh runtime run of the chosen revision | Running release revision | Journey drive on the release candidate | Participant/host availability |
| P40 participant evidence | BUILDER/L4 | `ISSUE47.json`; `TRADER_TASK_GUIDE.md` | NOT_RUN | Unfamiliar-trader tasks and observation forms | Participant availability | Builder-conducted sessions | Participant availability |
| P40 accessibility (phone, screen reader, full keyboard) | L2/L4 | `release-journey/` §12 | Keyboard pass partial | Phone, screen-reader, full-traversal limits recorded | Device availability; authorized session setup | Manual checks or exact NOT_RUN limits | Device availability |
| P41 hosting/access assessment | L4 | `ISSUE48.json`; this package | Preparation accepted; target: builder-selected Contabo VPS | VPS facts (H13) and hosted checks | VPS facts (H13) | Runbook stages | Deployment authority |
| P41 submission checklist and assets | L4 | `ISSUE48.json`; `SUBMISSION_CHECKLIST.md` | Preparation accepted; assets MISSING | Logo/graphic, videos, public repo, live link | Builder assets | Asset and submission checks | Builder assets + publication authority |
| P41 final release evidence | L2/L4 | `ISSUE48.json` | NOT_RUN | Combined final evidence on the release candidate | All above criteria | Final combined check | Builder launch authority |

## 7. Selected sponsor criteria (current accepted sources)

| Bounty | Owner | Accepted source | Existing evidence / class | Missing proof | Prerequisite | Proposed test | Approval |
|---|---|---|---|---|---|---|---|
| Nansen, Best use of Nansen | L2 | `NANSEN_BOUNTY_PICKUP_RECHECK_2026-10-12.md` | Local package accepted and integrated `3e7ff8bd`; see `nansen-report/` | Core mount into the Research journey; durable save/reopen; actual endpoint/data/credit/rights qualification; working demo | Actual-data packet + app mount | Mount + save/reopen an actual report | Actual-data packet; optional ≤2-min video is optional |
| Envio, Best Use of Envio | L2 | `METROPOLIS_BOUNTY_REQUIREMENTS_RECHECK_2026-10-07.md` | Recorded-native P07 transport LOCAL | Deployed/working Envio pipeline with real Monad data; consuming product; public code; end-to-end demo | Deploy/access + data packet | Working Envio pipeline in the consuming product | Deploy/access + data packet |
| Kuru consumer trading | L2/L3 | `METROPOLIS_BOUNTY_REQUIREMENTS_RECHECK_2026-10-07.md` | Adapter COMPONENT | Working spot product through Kuru; target-user/demand/retention answers | Live packet + qualified P20/P21 controls | One approved Kuru consumer-trading action | Live packet + product decision |
| Privy | L2 | Same recheck | Login path LOCAL | Visible functionality beyond login | Real-auth + feature packet | Visible beyond-login functionality | Real-auth + feature packet |
| Monad, Best Community Team Project | BUILDER/L2 | `NANSEN_BOUNTY_PICKUP_RECHECK_2026-10-12.md`; `METROPOLIS_BOUNTY_REQUIREMENTS_RECHECK_2026-10-07.md` | SELECTED (confirmed); no separate product evidence yet | An onboarded community supporter represented; that group selected in the profile; standard submission | A recorded onboarded community-supporter identity | Represent the supporter and select the group in the profile | Builder product decision + submission authority |

Sponsor selection was confirmed by the builder (five selected bounties: Best Community Team Project, Best Use of Envio, Kuru consumer trading, Privy, Nansen). This map does not change selection or claim qualification. A dated public-rule recheck is required before submission.

## 8. Summary counts

| Group | Total | LOCAL/COMPONENT | NOT_RUN or MISSING |
|---|---|---|---|
| RC01–RC20 | 20 | 14 have local/component portions | all final hosted/actual/participant checks |
| PU01–PU08 | 8 | 0 final | 8 |
| RG01–RG06 | 6 | 6 local recorded-response | actual-data qualification |
| IC01–IC08 | 8 | 7 local interfaces; IC08 not implemented | actual-provider qualification |
| AUT01–AUT08 | 8 | 3 local decision flow | scheduler + hosted/live recurring |
| P40/P41 | 6 | preparation accepted | runtime/host/participant/assets |
| Sponsor | 5 | 1 local package (Nansen) | mounts + actual + demo; community-supporter evidence |

Counts are indicative of criteria that have any accepted local/component portion at this base under the defined evidence classes; they are not a claim that any criterion passes. For example RC16 and RC18 have local portions but their final hosted/rendered checks stay unrun.

No criterion in this map is PASS. Full tickets and umbrella #58 stay OPEN.
