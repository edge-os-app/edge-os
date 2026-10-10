# P40 release journey checks

Task OC-P40-PREP-20261010-01, issue #47. Prepared 2026-10-10, base `a90d8b7f1a7ab500024e076194f2b5d6cbc83f11`.

Scope: preparation only. The cases below map accepted behavior to repository routes, views, records, tests and evidence. No check in this file was run for this package. Existing green tests and evidence are cited as coverage pointers, not as a fresh runtime result. Full P40 issue #47 stays OPEN.

## 1. Purpose and boundary

This map answers one question for each accepted journey behavior: where does the behavior live in the repository, what proves it today, and what is still missing? It separates:

- implemented and tested behavior (mapped once),
- synthetic fixture evidence (labelled, never treated as live proof),
- future qualification and pending P05 or live behavior (explicitly blocked),
- unrun checks and participant absence (kept UNRESOLVED).

Reference sources: [release cut](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md), [hackathon design](../../superpowers/specs/2026-09-29-edge-os-hackathon-design.md), [feature map](../../../.agents/skills/verify-edge-os/feature-map.md), the surface components and the tests under `tests/p03/` and `apps/`. Each case cites its exact source.

## 2. How to read a journey case

Each case is a table row with the same fields:

| Field | Meaning |
|---|---|
| Case id | Stable identifier for repairs and gate reference |
| Requirement | Story or acceptance-check source |
| Accepted behavior | The observable result the release requires |
| Surface | UI component and route where the behavior lives |
| API route | Backend endpoint that backs it |
| Saved record | Durable row the behavior reads or writes |
| Existing check | Green test or executed evidence that covers it today |
| Exact steps | Concrete actions a fresh operator would take |
| Expected observation | What the steps must show |
| Missing proof | What is absent or still unrun, and its blocker |

## 3. Journey case map

| Case | Requirement | Accepted behavior | Surface | API route | Saved record | Existing check |
|---|---|---|---|---|---|---|
| J01 result-first | Story 80 | Result and current primary action lead the page | RequestPage, RulesReview, InvestigationReview, ReplayResult | `GET /v1/research/requests/{id}`; `GET /v1/strategies/{id}/revisions/{revision_id}` | `Outcome`, `StrategyDraft`, `PublicationResult`, `strategy_revisions` | e2e thesis/quote-volume/nested/tiny-threshold; reopen exact review text; quality smoke |
| J02 labelled controls | Story 79 | Controls carry visible labels usable without a desktop mouse | Shell, ResearchHome, AccountViews, Conversation, dialog sheet | all authenticated routes | none dedicated | quality 44px, contrast, focus-ring, axe; e2e keyboard hunch |
| J03 narrow layout | Story 79 | 390px layout without losing the primary action | Shell compact nav, AccountViews, Conversation sheet | all | none dedicated | Playwright mobile-390 project; quality no-horizontal-scroll; reopen mobile |
| J04 pending, empty, failure | Issue acceptance check 1 | Loading, empty, failed and pending states explain themselves and keep focus | ResearchHome, RequestPage, AccountViews, Conversation | authenticated GET/POST behind them | unaffected | quality pending/failed/stale/lost-reply; e2e empty and error states |
| J05 saved, reopened, restarted | Issue acceptance check 2 | Saved records survive reopen and an API restart read-only | RequestPage, SpotReplayPanel, AccountViews, AgentContext | GET-only reopen routes | all listed records | reopen.spec.mjs full path; e2e reopen |
| J06 owner denial | Release-cut retention of cross-owner denial and wallet-isolation checks | Another owner cannot read, answer or publish | all surfaces | owner-scoped GET/POST routes | no row changes | e2e another-owner test; ownership-drive.json; test_live, test_ownership |
| J07 exact rule meaning | Story 79/80, P06 profile | Exact thresholds, boundaries and groupings survive save and reopen | RulesReview | `GET /v1/strategies/{id}/revisions/{revision_id}` | `strategy_revisions` with canonical hashes | e2e exact negative/right-nested; provenance both signs; reopen |
| J08 evidence vs confidence | Issue acceptance check 5 | Unresolved outcomes and synthetic fixtures stay distinct from supported claims | InvestigationReview, EffectComparisonPanel, SpotReplayPanel, AccountViews notices | investigation/effect/replay/account-view routes | P08/09/replay/account records | e2e no-thesis and declaration; reopen report without rerun; README status |
| J09 permission meaning | Issue acceptance check 5 | Owners can tell evidence, permission, local stop, signer removal and residual exposure apart | AccountViews permission snapshots, Shell build-scope notice | `/v1/account-views` | `PERMISSION_SNAPSHOT` records | quality P19 permission histories; e2e P19 account views; docs/contracts/account-views |
| J10 future qualification | Release cut P40 row | Unimplemented journey segments show explicit blocked prerequisites (story 86 and 87 mapping below) | none (not built) | none | none | release-cut and knowledge docs only; no green check |

Story to case mapping: stories 79 and 80 apply to the implemented surfaces in J01 to J03. Story 86 (qualified deployment and recorded operation) applies to the future qualification in J10 and section 13; the current repository has no deployment or recorded-operation evidence. Story 87 (a fresh agent runs the accepted path and inspects saved records from portable fixtures) applies to the fresh-operator steps in sections 5, 7 and 12; the portable fixture inputs exist (`tests/p03/fixture-auth.mjs` and the account-view fixtures, [feature map](../../../.agents/skills/verify-edge-os/feature-map.md)), but a fresh-agent run on another machine is UNRUN for this package.

Case execution type and per-run evidence: the fallback states in J04, J05, J06 and J08 are created by the named automated browser tests below, not by ordinary page controls. The conductor reproduces each one from the named injection procedure when verifying, or runs the named test and reads its recorded evidence. Participant tasks T1 to T5 in TRADER_TASK_GUIDE are manual observations by the builder using the evidence run's record IDs. Future controls in J10 and section 13 require a later authorized run and have no current evidence field. Per-run record IDs for the seeded saved surfaces live in `ui-results.json` and `p19-fixtures.json` under `.scratch/p03/evidence/<run_id>/`.

## 4. Result-first and current primary action

Requirement: stories 79 and 80 and the accepted release subset require the current result and the next primary action to lead. Sources: [design surface and acceptance](../../superpowers/specs/2026-09-29-edge-os-hackathon-design.md) sections 14 and 17; prototype findings [frontend interaction result](../../prototypes/EDGE_OS_FRONTEND_INTERACTION_RESULT.md) that record hierarchical presentation as the accepted direction.

Applied surfaces and checks (mapped once, not re-opened):

| Surface | Behavior in the repository | Existing green evidence |
|---|---|---|
| ResearchHome | Saved request list leads; the form and its examples follow; errors show beside the action | `tests/p03/e2e.spec.mjs` empty/error/thesis; `apps/web/tests/research-home.test.tsx` |
| RequestPage | Loaded request leads with outcome and review; reviewer details expand | e2e thesis and reopen tests |
| RulesReview | Rule meaning and hash lead over technical detail | e2e and reopen exact review text |
| InvestigationReview | Declaration state and saved identity lead; provider/study controls are absent | e2e P08 tests; quality P08 |
| ReplayResult | Replay result and saved settings lead; no recompute on reopen | `tests/p03/reopen.spec.mjs` |
| AccountViews | Account heading and synthetic notice lead; view selector follows | e2e P19; quality P19 |

Missing proof: no fresh render assertion was produced for this package. The listed tests cover these surfaces; a P40 runtime pass would re-drive them on the chosen release revision.

## 5. Narrow layout and labeled controls

Requirement: story 79 and issue acceptance check 1. A usable narrow layout, labeled controls and predictable keyboard focus must work without a desktop mouse.

Repository viewport coverage: Playwright runs two projects, `desktop` at 1280x800 and `mobile-390` at 390x844 with touch, in `tests/p03/playwright.config.mjs`. `scripts/p03/verify_run.py` drives the mapped path at 1280px and 390px.

Existing green checks (one place each):

- 44px minimum on every control in the main states, at desktop and 390px: `tests/p03/quality.spec.mjs` `accepted 44px minimum...`.
- Text and placeholder contrast 4.5:1, 3:1 for large text: `quality.spec.mjs` `text and placeholder contrast...`.
- Focus-ring contrast at least 3:1 on every surface: `quality.spec.mjs` `the keyboard focus ring...`.
- No horizontal scroll with long unbroken text at any width: `quality.spec.mjs` `no horizontal scroll...`.
- Word-split check and no mid-word split: `quality.spec.mjs`.
- axe-core WCAG 2.2 AA: no serious or critical violations in main states: `quality.spec.mjs` `axe: ...`.
- P19 account surfaces 44px, axe and contrast at desktop and 390px: `quality.spec.mjs` `P19 account surface...`.
- P19 expanded permission histories keep every saved value inside the viewport: `quality.spec.mjs` `P19 expanded permission histories...`.
- P08 investigation review controls and accessibility: `quality.spec.mjs` `P08 investigation review controls...`.

Exact steps for a target qualifier: sign in with a fixture owner, open Research then Agents, Positions and Funds, run Tab through the full page at desktop and at 390x844, and confirm every control has visible focus and a label.

Expected observation: no control below 44px, no contrast failure, focus ring visible, no document overflow, no split words.

Missing proof: axe, contrast, 44px and overflow checks are browser assertions. They are not a physical-phone touch test and not a screen-reader session. See section 12.

## 6. Pending, empty and failure states

Requirement: issue acceptance check 1. Affected pending, empty and failure states work at desktop and 390px and keep focus or a retry.

Existing green checks (mapped once):

| State | Surface | Existing green evidence |
|---|---|---|
| Empty saved list | ResearchHome | e2e `empty state for an owner with no requests`; `apps/web/tests/research-home.test.tsx` failed-retry case |
| Failed saved-list load with retry | ResearchHome | e2e `error state when saved requests cannot load`; quality failed-load |
| Failed request load with retry | RequestPage | quality `a failed load of a saved request keeps the retry button...` |
| Failed first submit keeps focus | ResearchHome | quality `a failed first submit keeps focus...` |
| Failed answer in main/side/sheet | Conversation | quality failed-answer tests and stale-answer tests per surface |
| Lost reply on first submit | ResearchHome | quality `a lost reply on the first submit...` |
| Stale answer and reload failure | Conversation | quality `a stale answer...` for every surface |
| Pending action shows working | RequestPage | quality `a pending action shows that it is working` |
| Restriction typed but not added | ResearchHome | quality `a restriction that was typed but not added is kept...` |
| Rejected or unavailable session | App/Shell | e2e `signed-out and rejected sessions...`; quality session-rejected |
| Account load failure with retry | AccountViews | e2e P19 first failure then Try again; quality P19 |

Exact steps: state-condition injection is automated, not ordinary page controls. With fixture sign-in, submit nothing and open an empty owner to see the empty list (`e2e.spec.mjs` `empty state for an owner with no requests`). To force the saved-list failure and its retry, reproduce the HTTP-503 route interception in `quality.spec.mjs` `a failed load of a saved request keeps the retry button, focus and a visible error` (the `page.route("**/v1/research/requests/*")` fulfillment). To force a stale answer and a reload failure, reproduce `answerOutOfBand` and the `page.route("**/v1/research/requests/*")` abort/fulfill in the `quality.spec.mjs` stale-answer tests. Submit the thesis fixture (`THESIS` constant) and let the fixture answer, then reload and check the draft survives (`quality.spec.mjs` `an unsent draft survives a reload...`).

Expected observation: each failure shows its error beside the action, keeps focus, offers the correct recovery, and never pretends a pending action completed.

Missing proof: these are executed browser tests recorded in the repository; this package did not rerun them.

## 7. Saved, reopened and restarted records

Requirement: issue acceptance check 2. Saved records reopen and survive an application restart; fixture and real-provider inputs stay distinct.

Existing green checks:

| Record | Reopen after restart | Never recomputed on reopen |
|---|---|---|
| P06 saved rules (thesis, volume, grouped, grouped-right, tiny, tiny-positive) | `tests/p03/reopen.spec.mjs` | reopen asserts revision id, original request and `Read back from the database` |
| P08 investigation declaration | reopen | `No study started`, `DECLARATION_SAVED` |
| P09 saved effect report | `tests/p03/reopen.spec.mjs` | `Reopen saved report without rerunning`; no POST |
| P13 spot replay and unavailable cases | reopen | `Loaded the exact saved result. The replay did not run again.`; POST count zero |
| P19 account records and sources | reopen P19 section | GET-only reopen, zero writes; context versions `[1,2,3,4,5]` and final `CLEARED` |
| P19 long monitoring record at both widths | reopen and quality | wrapped fields fit the viewport |

SQL and identity evidence: `scripts/p03/verify_run.py` compares every `to_jsonb(records)` row to the exact post-seed snapshot before and after the API restart, recomputes `content_sha256` and checks strategy manifest hashes. Evidence names `sql-inspection.json`, `ui-reopen.log` and `ui-results.json`.

Exact steps: run the mapped path, restart the API process on the same database, open each saved record in a new browser context, and confirm the exact saved identity renders without a write.

Expected observation: identical saved text/IDs after restart, no recompute and no new row.

Missing proof: a restart run is a browser plus database operation. This package mapped it only.

## 8. Owner denial and permission meaning

Requirement: release-cut retention of cross-owner denial and wallet-isolation checks (see the release-cut scope precedence); issue acceptance check 5 for the permission-meaning part. Another owner must not read, answer or publish another owner's records.

Existing green checks (mapped once):

- e2e `another owner cannot open the record`: foreign read, answer and publish return `not found`; no row change.
- `scripts/p03/verify_run.py` writes `ownership-drive.json` after driving the cross-owner cases per surface.
- `apps/api/tests/test_publication.py::test_database_rejects_cross_owner_parent_reference` covers the database cross-owner parent reference; `test_live.py` covers owner denial after restart and publication-route 409 conflicts (`apps/api/tests/test_live.py`).
- `apps/api/tests/test_ownership.py` covers owner-scoped read/list denial.
- e2e P19 account views: foreign `GET /v1/account-views/{record_id}` returns 404 and owner B list is empty.

Exact steps: run two fixture owners A and B; open A records under B and B records under A; answer and publish as the wrong owner; confirm 404 and unchanged rows.

Expected observation: no foreign row is readable or writable; denial is `not found`, not a permission detail leak.

Missing proof: application-level privacy is covered by these tests. Real authentication through Privy and production database isolation are P01/P05 pending work, blocked separately.

## 9. Exact rule meaning and provenance

Requirement: story 79/80 and P06 compiler profile. Exact thresholds, boundaries and groupings survive save and reopen, and provenance stays readable for both signs.

Existing green checks:

- e2e `exact negative tiny threshold remains visible through save`.
- e2e `nested Boolean groups retain their review meaning through save` and `a right-nested Boolean group stays distinct through save`.
- e2e `quote-volume rule: review, save and reopen the scheduled baseline`.
- `tests/p03/provenance.spec.mjs` `saved tiny-threshold provenance stays readable for both signs`, with `provenance-layout.mjs` measuring that exact rows fit at desktop and 390px.
- reopen asserts the exact revision and original request text for all six saved rules after restart.

Record identity: `apps/api/src/edge_os_api/` compiles and stores the exact rule with content and manifest SHA-256. `docs/implementation/P06_COMPILER_PROFILE.md` and `docs/contracts/p06/` define the versioned deterministic compiler. `apps/api/tests/test_strategy_compiler.py` and `test_strategy_compilation_api.py` cover the machine form.

Exact steps: the fixture interpreter matches normalized request text, requested job and input class exactly. Use the existing accepted constants from the tests, not arbitrary prose:
- tiny negative threshold: `TINY_RULE` and `TINY_THRESHOLD` in `tests/p03/e2e.spec.mjs` (`-0.` followed by 399 zeros and `1`); `Group specific rule or thesis` as input class; fixture scenario `tiny-threshold` in `apps/api/src/edge_os_api/research/fixture_interpreter.py`.
- nested left group: `GROUPED_RULE`; right group: `GROUPED_RIGHT_RULE` (same file). Provenance for both signs reuses the negative `TINY_RULE` record and the positive `TINY_POSITIVE_RULE` with `TINY_POSITIVE_THRESHOLD` from `tests/p03/provenance.spec.mjs`.
Type the exact text, select the `Specific rule or thesis` input class (CONCRETE_THESIS), add the accepted `no leverage` restriction, prepare, adopt the suggested settings, save, close, reopen in a fresh context and after an API restart; read the provenance rows for positive and negative signs.

Expected observation: the exact decimal and tree shape renders identically each time with the same content hash.

Missing proof: P06 compilation is a software fixture. It does not qualify a market, provider data or a research result.

## 10. Descriptive evidence versus edge confidence

Requirement: issue acceptance check 5 and release-cut claim rules. Unresolved results and synthetic fixtures must stay distinct from supported claims.

Existing green checks (mapped once):

- e2e `no thesis stays an investigation and shows no study progress`.
- e2e P08 declaration tests assert `DECLARATION_SAVED`, zero provider queries and no study start in the saved access event.
- e2e P09 report reopen asserts `statistical_status: UNRESOLVED` and `Reopen saved report without rerunning`.
- P13 spot replay reopening keeps `synthetic:adopted-cost-profile` and the fixture notice; unavailable reasons stay UNKNOWN rather than zero.
- P19 surfaces show `SYNTHETIC_AUTHORED` evidence class and the build-scope notice: account views are authored synthetic records, not live wallet data; saving a rule grants no permission.
- README `Current status` separates implemented Replay, Research and account paths from live qualification.

Exact steps for a qualifier: open a saved no-thesis request, an adopted P08 declaration, a saved P09 report and a P13 replay, and say which row is a supported result and which is a fixture with an unresolved outcome.

Expected observation: the interface labels synthetic data, keeps unknown values unknown and makes no profitability, financial or live-permission claim.

Missing proof: participant comprehension of this distinction is not established by any repository test. That is participant evidence, handled in TRADER_TASK_GUIDE.

## 11. Evidence, permission, local stop, signer removal and residual exposure

Requirement: issue acceptance check 5. Owners must be able to tell these five things apart: evidence, permission, a local stop, signer removal and residual exposure.

Current mapping (what exists and where):

| Concept | Repository location | State |
|---|---|---|
| Evidence | P08/P09/P13 saved records with `SYNTHETIC_AUTHORED` or `UNRESOLVED` states | implemented and tested |
| Permission | `PERMISSION_SNAPSHOT` account records: `ACTIVE`/`ENDED`/`NEVER_ACTIVE`, `CHANGE_PENDING`/`FAILED`/`CANCELLED`/`REMOVED`, immutable terms hash, signer and policy bindings | implemented in authored records; `docs/contracts/account-views/README.md` and `ACCOUNT_VIEWS_PROFILE.md` define the meaning |
| Local stop | P25 scoped stop behavior | NOT IMPLEMENTED; blocked on accepted P19/P23/P24 release portions |
| Signer removal | P16 one-owner sign-only evidence | implemented in P16 qualification scope only; app-level removal output is pending P16 unfinished criteria |
| Residual exposure | P30 revocation and pending/unknown holdings | NOT IMPLEMENTED; blocked on local P24/P25 and inactive P26 preparation, plus applicable P16 evidence |

Existing green checks: quality P19 permission-history test verifies `CURRENT`, `CHANGE_PENDING`, `FAILED` and `CANCELLED` snapshots render every saved value inside the viewport; e2e P19 verifies wallet-level actions appear only under their exact flow and permission snapshots stay immutable. `docs/qualification/p16/PROVIDER_SIGNING_RESULT_2026-10-08.md` records the sign-only removal scope and its limits.

Exact steps for the implemented portion: open an agent's permission history, expand the snapshots, and confirm each snapshot states its approval identity, terms hash, signer binding, policy binding and activation state without implying current authority.

Expected observation: immutable, dated snapshots that change provider permission nowhere; the agent summary is visibly a separate current state.

Missing proof: exact meaning is documented and the snapshot rendering is tested, but no live permission, stop, removal or residual-exposure behavior exists yet. Each future control lists its blocked prerequisite in section 13.

## 12. Required browser, phone and screen-reader checks and their limits

Requirement: issue acceptance check 4 and the design rule to record unperformed physical-phone, screen-reader and full keyboard checks. Sources: [design testing decisions](../../superpowers/specs/2026-09-29-edge-os-hackathon-design.md) (record unperformed physical-phone, screen-reader and full keyboard checks) and the [frontend interaction result](../../prototypes/EDGE_OS_FRONTEND_INTERACTION_RESULT.md) (physical-phone, screen-reader and full-keyboard limits remain unchecked).

| Required check | Actual coverage in this repository | Status |
|---|---|---|
| Desktop browser (1280px) | Playwright `desktop` project; quality, e2e, reopen, provenance specifications | MAPPED, executed historically |
| Narrow layout (390px) | Playwright `mobile-390` (390x844, touch); quality and e2e at both widths | MAPPED, executed historically |
| Keyboard focus and labels | quality focus-ring, 44px, labels via roles and accessibility name assertions; e2e keyboard hunch and Escape/Tab containment | MAPPED, executed historically |
| Complete keyboard-only traversal | Not a dedicated test; Safari default Tab in the prototype history skipped some controls | NOT RUN, recorded limit |
| Physical phone touch and virtual keyboard | No device test exists in this repository | NOT RUN, unavailable |
| Screen-reader behavior | No screen-reader session exists in this repository | NOT RUN, unavailable |
| axe-core accessibility | quality axe runs `wcag2a/2aa/21a/21aa/22aa` on five states and P19 surfaces | MAPPED, executed historically |
| Contrast, 44px, overflow | quality contrast, small-control and no-overflow checks | MAPPED, executed historically |

Owner and date commitments from the [release cut](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md): the builder recruits and conducts participant sessions and owns product closure; the controller prepares task guides and collates evidence. Feasibility check 11 October 18:00; sessions start with existing Research by 11 October; findings collated by 12 October 18:00. No external action was scheduled by this package.

Limits stay as recorded: a 390px browser viewport is not a physical phone; axe cannot replace a screen reader; a maintained keyboard test cannot replace a full traversal. Participant absence stays UNRESOLVED and never becomes demand validation or a PASS.

## 13. Future qualification and blocked prerequisites

The release journey continues with bounded permission, a controlled Kuru receipt, and restart/revocation. Those are not implemented here. Each future control names its explicit blocked prerequisite so no claim or task assumes it runs today.

| Future segment | Blocked prerequisite (release cut) | State |
|---|---|---|
| Bounded permission and admission (P22) | Accepted P06/P15/P19; fixture work may proceed independently | NOT IMPLEMENTED |
| Exact revision intake and exclusive claim (P23) | Accepted P22 release portion | WAITS on P22 |
| Original-action recovery (P24) | Accepted P23 | WAITS on P23 |
| Scoped stop (P25) | Accepted P19/P23/P24 | WAITS on P24 |
| Consent and removal preparation (P26/P30) | Local P24/P25 and inactive P26 preparation; applicable P16 evidence | WAITS on P24/P25 |
| Controlled Kuru receipt (P20) | Preparation package `docs/qualification/kuru-flow/` plus exact live packet approval | NOT RUN; live approval blocked |
| Real-provider authentication and shared wiring (P01/P05) | P05 existing continuation and shared-wiring lease | PENDING, lease reserved |

Future controls therefore have explicit blocked prerequisites. No green test covers them. No percentage, threshold, live participant result or profitability claim appears in this package.

## 14. Suspected defects for controller evidence

No application defect was found during this document preparation. The verifier and feature map are coverage inputs, not a fresh PASS. If a reviewer or a later runtime run finds a suspected defect, it goes to controller evidence and the recorded repair policy, not to an unauthorized fix here.

## 15. Coverage check summary

| Required scope | Mapped | Existing green evidence | Unrun or missing |
|---|---|---|---|
| Desktop and 390px layouts | yes | Playwright both projects, quality | no fresh runtime in this package |
| Keyboard, focus, labels | yes | quality, e2e | full keyboard traversal |
| Pending, empty, failure | yes | quality, e2e | no fresh runtime |
| Saved, reopened, restarted | yes | reopen.spec, verify_run SQL | no fresh runtime |
| Owner denial | yes | e2e, ownership-drive, test_ownership, test_live | real Privy auth pending |
| Exact rule meaning | yes | e2e, provenance, P06 tests | market/provider qualification |
| Evidence vs confidence | yes | no-thesis, DECLARATION_SAVED, UNRESOLVED | participant evidence |
| Permission / stop / removal / exposure | documented and partly tested | P19 snapshots, P16 signing | P22-P30 not implemented |
| Physical phone and screen reader | limits recorded | none exist | NOT RUN |
| Participant comprehension | task guide prepared | none exist | NOT RUN, builder-conducted |