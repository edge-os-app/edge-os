# Feature map

Rows were exercised by `scripts/p03/verify_run.py` unless the Evidence column names a pytest file; those rows are covered by `uv run --frozen pytest`, not by the mapped path. Evidence paths are relative to `.scratch/p03/evidence/<run_id>/`. Sample requests are scripted fixtures (`apps/api/src/edge_os_api/interpreter.py`); the fixture interpreter answers only those texts.

## First Research path (P03)

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| Signed-out and rejected session | "Sign in to start" page, no data | `GET /v1/me` returns 401 | none | `ui/screenshots/*-signed-out.png`, `steps.json` |
| Submit a request | Research form, "Prepare request" | `POST /v1/research/requests` | `IntakeRequest`, `PromptInterpretation`, `Outcome` | `ui/ui-results.json`, `sql-inspection.json` |
| Specific thesis | Fixture "Specific thesis", adopt, review, save | `POST …/clarifications`, `POST /v1/strategies/{id}/revisions` | `Clarification`, `StrategyDraft`, `PublicationResult`, `strategy_revisions` | screenshots `01`–`04` |
| Rough hunch | Keyboard choice (arrow keys, Enter) then adopt | `POST …/clarifications` twice | two `Clarification` rows, entry origin `USER_CONFIRMED` | screenshot `05` |
| Bounded no-thesis | Investigation stays an investigation, outcome Unresolved, no save button | `POST /v1/research/requests` | `Outcome` `UNRESOLVED`, no `StrategyDraft` | screenshot `06` |
| Unsupported meaning or restriction | Outcome "Not supported yet", words and restrictions kept | same | `Outcome` `UNSUPPORTED` | screenshot `07` |
| Unscripted text | Outcome "Could not be interpreted", not a verdict on the idea | same | `Outcome` `INVALID_INPUT` | `ui-e2e.log` |
| Contextual conversation | Desktop side panel; 390px sheet with Escape, Tab wrap, focus return | same records as the page | none | screenshot `08` |
| Reopen | Open from the list or a link in a new browser context | `GET /v1/research/requests/{id}` | read only | screenshot `09`, `ui-reopen.log` |
| Restart | API process stopped and started on the same database | `GET /readyz` | unchanged | `steps.json`, `sql-inspection.json` |
| Cross-owner denial | Other owner sees "not found" | read, answer and publish as owner B return 404 | no row changes | `ownership-drive.json`. A foreign parent reference is covered by `apps/api/tests/test_publication.py::test_database_rejects_cross_owner_parent_reference` and the 409 conflict test |
| Publication retry | Same operation and key return the same identity | `POST …/revisions` | one `strategy_revisions` row | `apps/api/tests/test_publication.py`, `test_live.py` |
| Interface quality | 44px control minimum, text and placeholder contrast (home, needs-answer, review, saved, unresolved and the mobile sheet), focus-ring contrast, no mid-word splits, no sideways scroll with long text, a failed first submit, a failed answer (main page, desktop side panel and the modal sheet) and a failed save each keep focus on the pressed button, show the error inside the surface that acted (announced once) and scroll it into view; a busy button reads "Saving…" and is dimmed, no console or network errors, axe-core on five states, focus stays in the answering surface and lands on the new state after a save | none | none | `ui/quality/controls-*.json`, `contrast-*.json`, `focus-ring-*.json`, `split-words-*.json`, `failure-recovery-*.png`, `conversation-failure-*.png`, `intake-failure-*.png`, `overflow-*.json`, `smoke-*.json`, `axe-*.json` |
| Cleanup | none | none | none | `resources-before.json`, `resources-after.json`; refusal of a repeated run ID: `apps/api/tests/test_harness_isolation.py` |

Not covered: real Privy login (`R1`–`R4` of the P01 profile), real model output, research execution, Agents, Positions, Funds, wallets, funding, signing.

## SQL checks

Run through the `psql` command printed by `HOLD`. Replace the placeholders with IDs from `ui/ui-results.json`.

```sql
select record_type, count(*) from records group by 1 order by 1;
select content->>'original_request', content->'restrictions' from records where record_type = 'IntakeRequest';
select revision_id, strategy_id, parent_revision_id, content_sha256, manifest_sha256, created_at from strategy_revisions;
select content->>'question', content->'changed_fields' from records where record_type = 'Clarification' order by seq;
select count(*) from users;  -- one row per signed-in owner, nothing else created by login
```

The hash check: `strategy_canonical` from `strategy_revisions` hashes (SHA-256) to `content_sha256`.

## Failure injection (covered by `apps/api/tests/test_live.py`)

Unmigrated database stops startup. Schema drift and a database that refuses connections turn `/readyz` into 503 and map principal lookup to `service_unavailable`. The harness blocks connections with `ALTER DATABASE … ALLOW_CONNECTIONS false` and restores them.

## Resources and cleanup

Every container and volume is `edge-os-test-pg-<run_id>` with labels `edge-os.test=1` and `edge-os.test.run=<run_id>`. The web build lands in `apps/web/.next-<run_id>` and is removed. Processes stop through the handles the run holds. The run never touches another container, port or database.
