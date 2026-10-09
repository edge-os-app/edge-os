# Feature map

Rows were exercised by `scripts/p03/verify_run.py` unless the Evidence column names a pytest file; those rows are covered by `uv run --frozen pytest`, not by the mapped path. Evidence paths are relative to `.scratch/p03/evidence/<run_id>/`. Sample requests are scripted fixtures (`apps/api/src/edge_os_api/interpreter.py`); the fixture interpreter answers only those texts.

## First Research path (P03)

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| Signed-out and rejected session | "Sign in to start" page, no data | `GET /v1/me` returns 401 | none | `ui/screenshots/*-signed-out.png`, `steps.json` |
| Submit a request | Research form, "Prepare request" | `POST /v1/research/requests` | `IntakeRequest`, `PromptInterpretation`, `Outcome` | `ui/ui-results.json`, `sql-inspection.json` |
| Specific thesis | Fixture "Specific thesis", adopt, review, save | `POST …/clarifications`, `POST /v1/strategies/{id}/revisions` | `Clarification`, `StrategyDraft`, `PublicationResult`, `strategy_revisions` | screenshots `01`–`04` |
| P06 price/quote-volume compiler and review meaning | Scripted quote-volume, both opposite nested Boolean groupings, and exact positive/negative tiny-threshold inputs are typed, adopted, reviewed, saved, reopened, and checked after API restart; the provenance table opens with both exact thresholds at desktop and 390px without document overflow; mapped-only inputs do not appear among home examples; RSI rejection names Entry rule | same clarification/publication routes; `GET /v1/strategies/{id}/revisions/{revision_id}` | P06 StrategySpec schema/manifest, exact `relative_volume(2)` and grouped trees, full decimal thresholds, immutable content/manifest hashes | `ui-results.json` keys `volume-rule-*`, `grouped-rule-*`, `grouped-right-*`, `tiny-threshold-*`, `tiny-threshold-positive-*`; SQL inspection checks saved entry trees against labelled scripted fixtures; `ui-reopen.log` and `*-reopened-after-restart.png` capture post-restart assertions/screens; `apps/api/tests/test_p06_api.py` |
| Rough hunch | Keyboard choice (arrow keys, Enter) then adopt | `POST …/clarifications` twice | two `Clarification` rows | screenshot `05`; the `USER_CONFIRMED` entry origin is asserted by `apps/api/tests/test_research_flow.py`, not by the mapped run |
| Bounded no-thesis | Investigation stays an investigation, outcome Unresolved, no save button | `POST /v1/research/requests` | `Outcome` `UNRESOLVED`, no `StrategyDraft` | screenshot `06` |
| P08 investigation adoption | Version-2 review shows compatible descriptive/predictive controls, positive unit-bearing horizons, explicit UTC partition intervals, and exact trial→evaluation→variant/horizon/partition rows; a failed first save retries with the same strict public keys; a later clarification refresh generates distinct proposal IDs while retaining the reviewed plan/IDs and edits, requiring renewed adoption; a failed explicit replacement keeps replacement intent through repeated proposal retries and then saves one coherent fresh edge/plan, without changing prior saved records; keyboard save focuses the announced saved result; exact record reopens after API restart | `GET …/investigation-proposal`, `POST …/investigations`, owner-scoped `GET` list and exact declaration; clarification uses the same intake-row transaction lock as new saves | append-only `investigation_declarations` and `investigation_access_events`; explicit evaluation rows equal the budgeted count (no Cartesian expansion), period-contained ordered non-overlapping partitions, consistent meaning, user-confirmed plan tied to `investigation-review/2`, pre-outcome/unread/no-provider/no-study, fixture-only/$0 | `ui-results.json` `investigation-*` (including retry key reuse, regenerated-ID clarification refresh, and repeated explicit-replacement retry), `sql-inspection.json` contract/semantic/plan/partition checks, `ownership-drive.json`, `ui-reopen.log`, `*-investigation-saved.png`; `apps/api/tests/test_investigation_adoption.py` real-PostgreSQL stale interleaving, retry-after-clarification, validation and ownership cases |
| P09 descriptive effect comparison | Saved P08 only shows an explicit synthetic P09 adoption. The owner reviews exact P08 evaluation/trial/variant IDs, P06 rules, essential inputs, decision clock and incremental-volume mapping. The UI labels the two authored feature buckets, two missing buckets and expected synthetic +0.2 contrast. A saved P09 access marker is shown separately from P08's declaration-time label snapshot. The browser proves a failed request remains visible, then loses a response only after the server commits the report; refresh selects the exact persisted report and does not compute it again. | `POST …/investigations/{declaration_id}/effect-runs`, `POST …/effect-runs/{run_id}/attempts`, owner-scoped `GET` list and exact run/report | append-only `effect_run_declarations` and `effect_run_events`; one immutable `effect_reports` row; exact P08 binding; only explicit Boolean P06 expressions; same-P08 rebind blocked after access; per-dependency values/reasons/IDs retained; response windows stay within the descriptive partition; PostgreSQL advisory transaction lock serializes attempts; no protected partition access; P07 real-data history remains unresolved | `ui-results.json` `investigation-*` includes run/report IDs, event IDs and hashes; `sql-inspection.json` checks marker, event order, expected group means and report identity; `ui/quality/axe-effect-comparison-*`; screenshots `*-effect-report-saved.png` and `*-effect-report-reopened-after-restart.png`; focused API/UI tests and the mapped desktop/390px browser run |
| Unsupported meaning or restriction | Outcome "Not supported yet", words and restrictions kept | same | `Outcome` `UNSUPPORTED` | screenshot `07` |
| Unscripted text | Outcome "Could not be interpreted", not a verdict on the idea | same | `Outcome` `INVALID_INPUT` | `ui-e2e.log` |
| Contextual conversation | Desktop side panel; 390px sheet with Escape, Tab wrap, focus return | same records as the page | none | screenshot `08` |
| Reopen | Open from the list or a link in a new browser context | `GET /v1/research/requests/{id}` | read only | screenshot `09`, `ui-reopen.log` |
| Restart | API process stopped and started on the same database | `GET /readyz` | unchanged | `steps.json`, `sql-inspection.json` |
| Cross-owner denial | Other owner sees "not found" | read, answer and publish as owner B return 404 | no row changes | `ownership-drive.json`. A foreign parent reference is covered by `apps/api/tests/test_publication.py::test_database_rejects_cross_owner_parent_reference` and the 409 conflict test |
| Publication retry | Same operation and key return the same identity | `POST …/revisions` | one `strategy_revisions` row | `apps/api/tests/test_publication.py`, `test_live.py` |
| Interface quality | Measured per surface in the table below | none | none | `ui/quality/*` (see below) |
| Cleanup | none | none | none | `resources-before.json`, `resources-after.json`; refusal of a repeated run ID: `apps/api/tests/test_harness_isolation.py` |

### Interface checks by surface

| Check | Where it runs | Evidence |
|---|---|---|
| 44px minimum on every control, text and placeholder contrast, focus-ring contrast, no mid-word splits, no sideways scroll with long text, axe-core (five states: home, needs-answer, review, saved, unresolved; not the mobile sheet) | desktop and 390px | `controls-*`, `contrast-*`, `focus-ring-*`, `split-words-*`, `overflow-*`, `axe-*` |
| A failed first submit, a failed answer (main page, desktop side panel, modal sheet) and a failed save keep focus on the pressed button and show the error in that surface only, scrolled into view. A busy button shows a Saving label and is dimmed | desktop and 390px | `failure-recovery-*`, `conversation-failure-*`, `intake-failure-*` |
| A stale answer (another client answered first) shows its notice in the surface that acted, even after the reload removes the question, and moves focus into that surface. When the reload itself fails the message says so | desktop and 390px | `stale-*` |
| A lost reply on the first submit says the request may be saved and refreshes the list. A restriction typed but not yet added is sent with the request. Choosing an example over typed words can be undone (unit test only, not driven in the browser) | desktop and 390px for the lost reply | `lost-reply-*`; `apps/web/tests/research-home.test.tsx` |
| A failed load of the saved list or of one saved request keeps the retry button and a visible error through repeated failures | unit test (list), desktop and 390px (request) | `apps/web/tests/research-home.test.tsx`, `quality.spec.mjs` |
| P08 saved-list success remains visible while proposal generation fails; with no saved rows the proposal has an in-place retry; stale saves, proposal retries, and later clarifications retain a coherent reviewed plan/ID set and edits while requiring renewed adoption; failed explicit replacement retries keep replacement intent and save the fresh proposal edge/plan without altering prior declarations | focused unit tests plus the same-intake desktop/390px mapped adoption journey including a real clarification and two forced replacement 503s followed by a real proposal/save/reopen; API race/failure proof against PostgreSQL | `apps/web/tests/investigation-review.test.tsx`, `tests/p03/e2e.spec.mjs`, `apps/api/tests/test_investigation_adoption.py`, `ui-results.json`, `sql-inspection.json` |
| Sign-out returns to the sign-in heading and clears everything this app stored in the tab. Another person signing in sees an empty form. A rejected session shows a message with focus, keeps the same person's draft and signs in again for real | desktop and 390px (fixture session) | `session-rejected-*` |
| A closed or failed real Privy sign-in window ends in a message. A slow sign-in offers Try again and keeps the window | unit tests with a mocked bridge only | `apps/web/tests/auth.test.tsx` |

Not covered: real Privy login (`R1`–`R4` of the P01 profile), real model output, research execution, Agents, Positions, Funds, wallets, funding, signing.

## SQL checks

Run through the `psql` command printed by `HOLD`. Replace the placeholders with IDs from `ui/ui-results.json`.

```sql
select record_type, count(*) from records group by 1 order by 1;
select content->>'original_request', content->'restrictions' from records where record_type = 'IntakeRequest';
select revision_id, strategy_id, parent_revision_id, content_sha256, manifest_sha256, created_at from strategy_revisions;
select content->>'question', content->'changed_fields' from records where record_type = 'Clarification' order by seq;
select count(*) from users;  -- one row per signed-in owner, nothing else created by login
select d.declaration_id, d.intake_record_id, d.content->>'declaration_state', d.content->>'outcome_labels_read',
       d.content->'configuration'->'permitted_access', d.content->'configuration'->'compute_limit'->>'max_cost_usd',
       e.content->>'event', e.content->>'outcome_labels_read', e.content->>'provider_queries', e.content->>'study_started'
from investigation_declarations d join investigation_access_events e
  on e.owner_id=d.owner_id and e.declaration_id=d.declaration_id;
select r.run_id, r.p08_declaration_id, r.content->>'fixture_sha256' fixture_sha256,
       r.content->>'profile_sha256' profile_sha256, p.report_id,
       p.content->'result'->>'statistical_status' statistical_status
from effect_run_declarations r join effect_reports p using (owner_id, run_id);
select run_id, sequence, content->>'kind' event, content->>'outcome_accessed' outcome_accessed
from effect_run_events order by run_id, sequence;
```

The hash check: `strategy_canonical` from `strategy_revisions` hashes (SHA-256) to `content_sha256`.

## Failure injection (covered by `apps/api/tests/test_live.py`)

Unmigrated database stops startup. Schema drift and a database that refuses connections turn `/readyz` into 503 and map principal lookup to `service_unavailable`. The harness blocks connections with `ALTER DATABASE … ALLOW_CONNECTIONS false` and restores them.

## Resources and cleanup

Every container and volume is `edge-os-test-pg-<run_id>` with labels `edge-os.test=1`, `edge-os.test.run=<run_id>` and a random per-attempt `edge-os.test.claim`. A run removes only what its own claim created, so two starts with one run ID cannot delete each other's instance. The web build lands in `apps/web/.next-<run_id>` and is removed. Processes stop through the handles the run holds. The run never touches another container, port or database.
