# User-release integration profile (#58 Stage 1 local milestone)

Status: **frozen interfaces for the local connected fixture journey; candidate under review.** Issue [#58](https://github.com/edge-os-app/edge-os/issues/58), task `RELEASE-E2E-L2-20261012-S1`, base `c119e40`. This profile records how the accepted financial packages are composed into the application. It qualifies no real provider, wallet, chain, model, host or user. A fixture pass here proves application wiring only.

## Responsibility

Compose the accepted funding (P18), admission (P22), execution (P23), recovery (P24), scoped stops (P25), inactive consent (P26) and removal (P30) services behind authenticated owner-scoped routes, forward migrations, a durable bounded worker and the existing screens. Domain algorithms are reused unchanged except where this profile names a change.

## Files

| File | Responsibility |
|---|---|
| `apps/api/migrations/versions/0008_financial_state.py`, `migrations/env.py` | Create the seven `*_local` schemas, their accepted tables and the evaluation jobs table. `alembic check` covers every metadata. |
| `core/settings.py` | `execution_mode` (`fixture`/`unavailable`, production refuses `fixture`) and `fixture_effects_path`; Stage 2 quota, rate, job and timeout settings and production startup checks. |
| `core/provider_ports.py` | Trusted provider ports and their fixture/unavailable adapters. |
| `core/financial_services.py` | One composition of the services over the app's session factory. |
| `execution/connected_identity.py` | IC01 revision resolver, consent lookup and IC05 approval derivation. |
| `execution/worker.py` | Durable evaluation jobs; `python -m edge_os_api.execution.worker` bounded loop. |
| `*/routes.py` in funding, consent, execution, recovery, stops, revocation | Thin owner-scoped HTTP calls. |
| `revocation/enforcement.py`, `revocation/types.py` | `SubmissionControls` (stops + removal) and REQUESTED as a denying removal state. |
| `execution/service.py` | Records original transaction references in the attempt before the transport call. |
| `wallet_setup/service.py`, `wallet_setup/router.py` | IC04 browser completion (lease amendment `r58-r7-a`). |

## Frozen HTTP interface

All routes require a verified Privy principal. The owner is never read from a body. Every body model forbids extra fields, so an `owner_id`, balance, outcome, state or qualification field is a `422`. A foreign or absent agent, action, review or removal is a `404` (consent adoption of a foreign review is a `404`; scheduling for an agent the caller does not hold is `409 agent_not_ready`).

| Method and path | Body | Result |
|---|---|---|
| `GET /v1/agents/{agent_id}/funding` | — | `declaration`, reviewed `flows`, `deposit_balances` (credited and pending deposits per class), `current_holdings` (`OBSERVED`/`UNAVAILABLE`, separate from deposits), admission `allowances`, `provider_mode` |
| `POST …/funding/declaration` | none | Declares the revision's quote asset as trading capital and native MON (18 decimals) as gas. Idempotent. |
| `POST …/funding/flows` | `{asset_class: TRADING\|NATIVE_GAS, raw, reference}` | One reviewed deposit, `PENDING`. Same reference and content is idempotent; changed content is `409`. |
| `POST …/funding/reconcile` | none | Reads the server deposit port. Only `CONFIRMED` observations credit, once per event identity. Unavailable port records `OBSERVATION_UNAVAILABLE` and credits nothing. |
| `POST …/consent/review` | `{terms: ReviewedTerms}` | Grouped review of the agent's saved revision and wallet. Strategy, revision and network come from the setup. |
| `POST …/consent/adopt` | `{review_id, expected_review_hash}` | INACTIVE consent plus `activation`. |
| `GET …/consent` | — | Adoptions, reviews and `activation` (`FIXTURE_QUALIFIED` or `UNAVAILABLE` with a reason). |
| `POST …/actions` | `{request_key}` | Saves one evaluation job. `201` new, `200` + `Idempotent-Replay` existing. Does not evaluate or submit. |
| `GET …/actions` | — | Identity, jobs, decisions, queue, positions, blocking reason. |
| `GET /v1/actions/{action_id}` | — | Intent payload, decision, queue, admission decision, reservations (all states), receipts, attempts (with `original_references`), recovery case. |
| `POST /v1/actions/{action_id}/reconcile` | none | Reads the server receipt port and settles through recovery. Unavailable port is `503 receipt_unavailable`. |
| `POST/GET …/stops` | `{mode, scope, position_id?}` | Durable USER stop for the bound wallet. |
| `POST/GET …/removal` | `{request_key, reason}` | Durable removal request; `REQUESTED` denies at once. |
| `POST …/removal/reconcile` | none | Reads the server removal port; unavailable is `503`. |
| `GET /v1/financial/provider` | — | `{mode, evidence_class, fixture_effects}`. |
| `POST /v1/wallet-setup/agents/{agent_id}/complete` | `{wallet_id}` | IC04 browser completion. |

## Provider ports and modes

`ProviderPorts` holds `market`, `quotes`, `holdings`, `receipts`, `deposits`, `removals` and a transport factory. `execution_mode=unavailable` (the default and the only production value) raises `ProviderUnavailable` from every port: deposits stay pending, holdings show `UNAVAILABLE`, jobs end `UNAVAILABLE` with the missing input named, and no transport exists. `execution_mode=fixture` uses authored adapters labelled `SYNTHETIC_FIXTURE`:

- market: authored five-minute observations for the exact market binding and decision slot (rising by default);
- quotes: one authored constant price, 2 quote per base;
- holdings: confirmed deposit credits plus the fixture effect record, never admission state;
- transport and receipts: `FixtureChain`, an append-only effect record outside the database (`fixture_effects_path`, else process memory). The receipt for an action is proved only by exactly one record for that action, wallet and network;
- deposits: each reviewed `PENDING` flow is observed `CONFIRMED` at its reviewed amount;
- removal: `CONFIRMED` with a fixture signer identity.

Reserved agent-id markers select fixture scenarios only: `fx-nosignal`, `fx-ineligible`, `fx-falling`, `fx-lost-ack`, `fx-unknown`, `fx-revert`, `fx-deny`, `fx-deposit-pending`, `fx-removal-pending`. A real port must replace each adapter; none of these values is evidence.

## IC01 revision identity

`resolve_agent(session, owner_id, agent_id)` returns a `ConnectedAgent` only when the wallet setup is `CONFIRMED`, the owner-scoped `StrategyRevision` for the setup's strategy and publication UUID exists with the same content and manifest digests, the saved canonical bytes freeze through the accepted compiler, and the frozen execution content hash equals `sha256:` + the saved content digest. The execution revision id is the accepted `"{strategy_id}:{content_hash[7:23]}"`. Every job binds `publication_revision_id`, `execution_revision_id`, content and manifest hashes and the consent; a later change in any of them ends the job `DENIED` (`IDENTITY_CHANGED`, `IDENTITY_UNAVAILABLE` or `CONSENT_CHANGED`) without an effect. Asset ids are `{network prefix}/{lowercase address}` for the revision's quote and base assets and `{network prefix}/native` (18 decimals) for gas.

## IC02 observations and the bounded job

An evaluation job is unique per `(owner, agent, adopted consent, decision slot)` and per `(owner, agent, request_key)`. The decision slot is the latest five-minute UTC grid point at scheduling. Stages are saved before the next stage: `QUEUED` → decision saved (`DECIDED` for a signal, `COMPLETED` with `NO_SIGNAL`/`INELIGIBLE`) → one intent enqueued (`ENQUEUED`, or `COMPLETED ADMISSION_DENIED`) → submission (`COMPLETED` with the terminal queue state, or `SUBMITTED` while the original action needs reconciling). A decision already saved for the same revision and slot is reused; a saved intent for the decision is reused. Observations whose provenance names another market binding end the job `UNAVAILABLE OBSERVATIONS_WRONG_MARKET`, and observations for another decision time end it `OBSERVATIONS_WRONG_TIME`, both before any decision.

Unsent actions never hold capacity indefinitely. When a queued action is provably unsent and can no longer be submitted (revalidation denied, submission ownership refused, authority gone, or the intent past the next decision slot), the worker releases it through the accepted `AdmissionService.cancel`, which refuses anything already submission-owned. A provider outage at the submission stage keeps the job `ENQUEUED` with reason `WAITING:<PORT>_UNAVAILABLE`, so a later pass ticks the same saved action. Each entry opens its own position (`{agent}:{execution revision}:{decision id}`); an exit uses the agent's open position for the revision, so a closed or cancelled position never blocks a later entry. Entry size is the revision's `FIXED_QUOTE_AMOUNT` scaled exactly to quote base units; a size finer than the quote decimals is refused `SIZING_NOT_REPRESENTABLE`. The worker loop isolates each job: an unexpected error is logged with the job id, recorded as `WORKER_ERROR:<class>` on that job only, and the next job runs. A quote is never a rule observation. The worker holds a per-job transaction advisory lock, so concurrent workers skip a held job.

## IC03 holdings

Admission and revalidation read current holdings from the holdings port, plus attributed inventory from the durable admission position. Deposit history (`deposit_balances`) stays separate from `current_holdings`. A request can never supply either.

## IC04 browser wallet completion

`POST …/complete` retains the browser-reported wallet id as an untrusted `RESULT_RETURNED` event (`trusted: false`, no address), then binds only when an independent provider lookup returns the same id for the verified owner, chain type `ethereum`, and no other agent of the owner holds it. A confirmed setup never changes wallet (a different id records `CONFLICTING_RESULT`); a completion after a proved pre-dispatch cancellation binds nothing (`LATE_RESULT_AFTER_CANCEL`); a lookup miss or foreign owner leaves `UNKNOWN`. A repeated completion is the reconciliation path for a lost lookup reply; `resume` cannot bind a browser claim because it carries no provider address. No server creation runs on this path; existing prepare/dispatch/resume/cancel are unchanged. Production keeps the unavailable provider.

## IC05 activation

Consent rows stay INACTIVE. `derive_approval` returns an approval only for `qualification == "fixture"` (the server's own mode), terms version `connected-spot/1`, unexpired terms, exactly the allowances `quote_input`, `base_inventory`, `per_action_gas`, `per_exit_gas`, a gas budget, one allocation in the quote asset, and assets that match the revision. The snapshot is labelled `SYNTHETIC_FIXTURE_QUALIFICATION`, `approval_id` and `mandate_id` equal the adoption id, `policy_binding` equals the consent hash. Otherwise the reason is `ACTIVATION_UNAVAILABLE`, `CONSENT_EXPIRED`, `TERMS_VERSION_UNSUPPORTED`, `TERMS_INCOMPLETE` or `TERMS_ASSET_MISMATCH`. Real activation needs the P20/P21 qualification; it is not circular because Probe B consumes this inactive consent plus its own exact packet.

## IC06 original transaction references

Before the transport call, in the same transaction as the `IN_FLIGHT` attempt, a transport that defines `original_references(prepared)` records `edge-os.original-transaction-references/1`: `signing_request_id`, `nonce`, `fee_envelope`, `unsigned_bytes`, `signed_bytes`, `transaction_hash`, `provider_reference`, `evidence_class` and `absent_reason`. The fixture signs nothing, so every chain identity is `null` with `FIXTURE_TRANSPORT_SIGNS_NOTHING`. A live port must fill them before its effect boundary. On uncertainty only `POST /v1/actions/{id}/reconcile` runs; nothing constructs a replacement.

## IC07 receipts

The receipt port answers for the exact action, wallet and network. Absence or ambiguity is `SUBMISSION_UNKNOWN`. Reconciliation passes the receipt to the accepted recovery service: a confirmed receipt without actual gas is a durable P22 breach that keeps every reservation and blocks the wallet; a wrong-tuple receipt proves nothing. Planned amounts are fixture inputs to `FixtureChain`; the connected path never substitutes planned values for missing actuals.

## IC08 and residual exposure

Not implemented here. Independent opaque-program limits, acquired/residual exposure and native MON trading versus gas treatment stay with P21/Stage 3. This milestone keeps native MON as gas only, and the trading asset is the revision's quote token.

## Stop and removal enforcement

`SubmissionControls` answers the single `StopReader` that admission (`admit_and_reserve`, `acquire_submission`) and execution revalidation already consult inside their transaction. Admission and `acquire_submission` run under the shared P22 per-wallet advisory lock, which is the serialization point with a new stop or removal; revalidation runs under the separate P23 execution lock and is an earlier, additional check. It returns durable stop reasons for the operation plus every removal reason for the wallet. Removal now denies from `REQUESTED` (`REMOVAL_REQUESTED`), because the request is saved before any provider effect (gap G14); `FAILED` and absent records do not deny. `request_removal` and `request_stop` take the same lock, so either the control commits first and the transition is denied, or ownership commits first and the original action continues and stays recoverable. A stop or removal itself never releases reservations, cancels a submitted action, liquidates or withdraws. When one of these controls denies a provably unsent admitted action at revalidation, the worker (not the stop) releases that action through the accepted pre-submission cancellation and retires its queue entry as `DENIED_UNSENT`.

The same seam carries `OnePositionPerWallet` (`execution/position_limit.py`): an ENTRY or ADDITION is denied `POSITION_ALREADY_OPEN` while another position of the agent wallet holds inventory or has an unresolved entry/addition. It enforces the revision's `max_open_positions = 1` atomically at P22 admission and submission ownership, so a decision saved while an earlier entry was unresolved cannot open a second position. `acquire_submission` reports any such denial with the accepted status `STOPPED_SCOPE`.

## RG interfaces frozen for Task 6 (definitions; the local implementation follows below)

These are the frozen definitions Task 6 implements under its own lease. Versions are new; nothing here changes the accepted P02/P07/P08/P09 contracts or fixture bytes.

| ID | Interface (version) | Files (owner) | Depends on | Test cases Task 6 must add |
|---|---|---|---|---|
| RG01 | Real-source adoption `p08.investigation-declaration/3`, hypothesis-to-rule mapping `edge-os.hypothesis-rule-map/1` | `core/request_schemas.py`, `research/investigation_adoption.py` (main #58) | accepted P08 v2 | declaration saved before any collection; fixture v2 bytes unchanged; a new hypothesis cannot reuse the example rule; foreign request 404 |
| RG02 | Dataset record `edge-os.history-dataset/1` | `research/history_dataset.py` (main #58); `research_history/` library (P07 lane) | P07 consumer rules below | QUALIFIED/LIMITED/UNRESOLVED stored verbatim; LIMITED never projects to P02; missing buckets stay missing; source hashes recompute |
| RG03 | Investigation job `edge-os.investigation-job/1`, tools `edge-os.investigation-tool/1` | `research/investigation_jobs.py`, `research/investigation_tools.py` (main #58) | RG01, RG02 | original identity on duplicate start; budget reserved before effect; crash/lost reply resumes the original attempt; cancellation and deadline keep partial attempts; exhausted budget refuses |
| RG04 | Report binding `edge-os.investigation-report/1` | `research/comparison_runs.py` caller (main #58) | accepted P09 | insufficient data, unsupported, contradictory and rejected outcomes saved and reopened; no significance or capital claim |
| RG05 | History replay input `edge-os.history-replay-input/1` | `replay/history_inputs.py` (main #58, new file only) | RG02, accepted P13 runtime | warm-up unavailable, gaps, truncated window, lookahead refusal, exact rule/revision lineage, label "simulated fills" |
| RG06 | Verifier opt-in `--actual-data` (default off) | `scripts/p03/`, `.agents/skills/verify-edge-os/` (main #58) | RG01–RG05 | default run spends nothing; opt-in needs an approved packet |

**Dataset record (`edge-os.history-dataset/1`).** Owner-scoped row: `dataset_id`, `owner_id` (from `Principal`), `declaration_id`, `profile` (`p07.market_dataset_profile/1`) and `profile_sha256`, `collection_sha256`, `normalized_sha256`, `observations_sha256`, `window_start`/`window_end` (UTC, 300 s grid), `collected_at`, `archive_height`, `query_sha256`, `status` (`COMPLETE`/`PARTIAL`) and `stop_reason` from P07, per-claim and overall verdict (`QUALIFIED`/`LIMITED`/`UNRESOLVED`), `buckets` (P07 ordered bucket list, below), `provider_requests` (evidenced counts per provider; unknown is null), `invocations_measured` (local count, labelled), `evidence_class` (`RECORDED_RESPONSE` or `PROVIDER_ACTUAL`). A bucket maps to the compiler `InputObservation` as `value=close` (null when `close` is null), `bucket_end`, `qualified = status in {COMPLETE_OCCUPIED, COMPLETE_EMPTY}`, `available_at`, `reasons`; `COMPLETE_EMPTY` has no price. Unavailable states: `SOURCE_UNAVAILABLE`, `PARTIAL_COVERAGE`, `VERDICT_LIMITED`, `VERDICT_UNRESOLVED`.

**Hypothesis-to-rule mapping (`edge-os.hypothesis-rule-map/1`).** Binds `declaration_id`, the user's exact hypothesis text and `edge_id`, each adopted evaluation id, and the exact P06 rule expression per variant and control, with `rule_source` (`USER_ADOPTED` only; an example fixture rule is refused for a new user hypothesis). Real-market binding uses the P07 `to_p02_binding()` only for overall `QUALIFIED`; otherwise `binding_state = UNAVAILABLE_LIMITED_DATA` (G05 open).

**Investigation job (`edge-os.investigation-job/1`).** Unique per `(owner, declaration_id, request_key)`; states `QUEUED → RESERVED → COLLECTING → EVALUATING → REPORTED` with terminal `CANCELLED`, `DEADLINE_EXCEEDED`, `BUDGET_EXHAUSTED`, `UNAVAILABLE`, `FAILED`. Fields: `budget` (`{provider_requests:int, compute_seconds:int}` reserved before any effect; consumed and unknown-liability amounts kept separately; unknown never 0), `deadline_at`, `cancel_requested_at`, `attempts` (append-only: tool, input hash, outcome, provenance, contrary findings), `dataset_id`, `report_id`. Restart resumes the saved stage; a lost reply reconciles the original attempt, never a second collection. Real Hermes tools wait for released P05 safeguards and an approved inference budget.

### Accepted P07 consumer interface (controller acceptance `r7-done`, integration `1755e3c`)

The P07 library was accepted on integration commit `1755e3c` (candidate `cc58e28`, profile `docs/implementation/RESEARCH_HISTORY_ADAPTER_PROFILE.md` SHA-256 `3bf8130c…f1a1`). This candidate stays on base `c119e40` and does not import it; Task 6 consumes it after a controller base reconciliation. Frozen field paths:

- Calls: `collect(profile, source, scan, limits, provenance, clock) -> CollectionResult`; `normalize(profile, collection, evidence) -> NormalizedHistory`; `save_manifest`/`load_manifest`/`verify_manifest`; `save_raw_artifact`/`load_raw_artifact`; `project_binding(profile, result)`.
- `CollectionResult`: `status` (`COMPLETE` only with a complete page that tiles the scan, else `PARTIAL`), `stop_reason` (`COMPLETE`, `SOURCE_EXHAUSTED`, `LIMIT_PAGES`, `LIMIT_ROWS`, `LIMIT_BYTES`, `DEADLINE`, `CURSOR_CYCLE`, `REPEATED_PAGE`, `COVERAGE_INCOMPLETE`, `PROVIDER_ERROR`, `CANCELLED`, `TIMEOUT`), `pages`, `records`, `page_count`, `row_count`, `bytes`, `query.identity_sha256`, `requests`, `gaps`, `coverage`, `collection_sha256`, `source_invocations.measured_local_attempts` (exact local count, kept after errors) and `source_invocations.provider_requests` (`null` or `{provider: count}`; `provenance.measurement.provider_requests` is `SUPPLIED_EVIDENCE` or `UNKNOWN`).
- `NormalizedHistory`: `buckets[]` with `bucket_start`, `bucket_end`, `status`, `close` (exact price string or null), `quote_volume` (`"0"` only for `COMPLETE_EMPTY`; null when incomplete or unqualified), `available_at`, `availability_basis` (`ASSUMED_DELAY`, `OBSERVED_DELIVERY`, `UNKNOWN`), `reasons`; plus `trades`, `observations`, the `qualify` result, `binding_view`, `raw_records`, `raw_evidence {sha256, record_count}`, `normalized_sha256` (P02 canonical, own field removed), `collection_sha256`, `input_profile_sha256`, `bound_profile_sha256`, `observations_sha256`, `result_sha256`.
- Failures: malformed profile, limits or deadline raise `InvalidInput` before any source call; `SourceFailure`, `OSError`, `SourceTimeout`, `SourceCancelled` become `PARTIAL` results with no retry; any other exception propagates. The #58 job must therefore catch only the documented partial results and treat a propagated exception as a job failure, never as coverage.
- Retained limits: no fresh history is qualified; only overall `QUALIFIED` projects to P02 (G05 open); provider request counts are supplied evidence or unknown; archived pages are not fresh requests; source memory allocation is not bounded by the collector.

### P07 consumer rules

P07 consumption follows controller amendment `r58-r7-a`: the isolated `research_history` library returns `CollectionResult` (status `COMPLETE`/`PARTIAL`, stable `stop_reason`, measured invocation counts separate from evidenced provider request counts, unknown as null) and `NormalizedHistory` with ordered buckets (`bucket_start`, `bucket_end`, `status`, `close` price string or null, `quote_volume`, `available_at`, `availability_basis`, `reasons`) and `normalized_sha256` over the payload without its own digest. Malformed caller input is `InvalidInput` before any source call. Only overall `QUALIFIED` projects to P02; `LIMITED` is stored beside the declaration and keeps real-market rule binding unavailable (G05 open). #58 owns the bucket-to-`InputObservation` mapping, verified-owner persistence, investigation jobs, budgets, HTTP and UI. The investigation job reuses the evaluation-job pattern above: one row per owner/request/declaration identity, reserved budget before effects, original attempt kept on cancellation, deadline or lost reply.

## Task 6 local implementation (recorded responses only)

Milestone `RELEASE-E2E-L2-20261012-RG-LOCAL`. Every history source is the authored SYNTHETIC recorded-response bundle `apps/api/tests/fixtures/research_history_recorded/recorded_history_v1.json`, written only by `apps/api/tests/history_recordings.py`. The API serves it only with `EDGE_OS_RESEARCH_HISTORY_MODE=recorded`; production refuses that mode. No provider, model, credential or network call is made.

| ID | Implemented as | Main files | Status |
|---|---|---|---|
| RG01 | `POST/GET /v1/research/requests/{id}/history-investigations[/{declaration}]` save `p08.investigation-declaration/3` before any collection with frozen configuration, rule-map and source-profile hashes; the hypothesis rule map `edge-os.hypothesis-rule-map/1` accepts only `USER_ADOPTED` rules and refuses the worked-example rules (fixture strategy entry/exit, fixture interpreter choices, P09 example); `PROVIDER_ACTUAL` access is refused (`actual_data_not_authorized`). v2 reads and the P09 fixture run ignore v3 declarations. | `core/request_schemas.py`, `research/investigation_adoption.py` | Local PASS candidate |
| RG02 | `edge-os.history-dataset/1` rows in `research_local.history_datasets`, saved verbatim from P07 `collect`/`normalize` with raw records, recomputable hashes, verdicts, measured invocations, evidenced or unknown provider usage, binding state and unavailable states. Only overall QUALIFIED and complete data project to a market binding. | `research/history_dataset.py`, migration `0009` | Local recorded PASS candidate; actual data NOT RUN |
| RG03 | `edge-os.investigation-job/1` jobs, append-only `investigation_events`, per-owner `research_budgets` (moved to `usage_local` shared quotas by Stage 2 migration 0010); reservation before any adapter effect; duplicate start, last-slot competition, cancel, deadline, killed worker (OUTCOME_UNKNOWN, never collected again), lost reply after a saved result, missing/invalid usage, provider failure, budget exhaustion and restart. Tools `edge-os.investigation-tool/1` are deterministic and import no financial or network module. Worker: `python -m edge_os_api.research.investigation_jobs`. | `research/investigation_jobs.py`, `research/investigation_tools.py` | Local PASS candidate; no Hermes tool isolation is proved |
| RG04 | `edge-os.investigation-report/1` reports from the accepted P09 engine on the saved dataset: DESCRIBED, CONTRADICTORY, INSUFFICIENT_DATA, UNSUPPORTED, SOURCE_LOSS, LIMITED_DATA; validation and holdout partitions are never read; no significance, capital or execution claim. | `research/comparison_runs.py` `compare_history` | Local PASS candidate |
| RG05 | `edge-os.history-replay-input/1`: `POST /v1/spot-replays` with `history_dataset_id` feeds the unchanged P13 runtime; buckets, availability and verdicts pass through unchanged; lineage, both market binding ids and "simulated fills" are saved. A strategy reaches the dataset market only through pre-publication adoption (`POST /v1/research/requests/{id}/market-adoptions`, amendment RG05-MARKET-ADOPTION-v1): a NEW interpretation, clarification, outcome and draft built from the owner's hash-verified QUALIFIED dataset; the entry becomes exactly one `USER_ADOPTED` rule of that dataset's own declaration (price and volume conditions joined by `and`), the exit is restated by the owner and refused when it is a worked-example rule, and amounts are restated in the new quote unit; replays record whether the entry is that declared rule; earlier drafts and revisions never change and the fixture revision still fails `MARKET_BINDING_MISMATCH`. | `replay/history_inputs.py`, `replay/saved_runs.py`, `research/market_adoption.py` | Local recorded PASS candidate; actual-source replay blocked by the runtime evidence-class check (proposal recorded, simulator unchanged) |
| RG06 | Verifier research phase (`scripts/p03/research_phase.py`, three specs `research-history-*.spec.mjs`); `--actual-data PACKET` refuses without a recorded approval and, even with one, until an actual adapter exists. | `scripts/p03/`, `.agents/skills/verify-edge-os/` | Default run spends nothing |

Retained limits: the recorded bundle is synthetic; actual collection, inference and actual-history replay need the separate authorization packet and the runtime change; LIMITED representation (G05) stays open; a local fake runner proves no real Hermes tool isolation.

### Pre-public and live follow-ups (tracked; Stage 2 status in the next section)

| ID | Follow-up | Proposed repair (summary) |
|---|---|---|
| F1 | Account views read authored P19 rows, not the connected financial schemas | Read-only service projection from `funding_local`/`execution_local`/`recovery_local`/`revocation_local`, labelled by source |
| F2 | A failed read-back after a successful mutation re-enables writes over a stale view (`AgentActions`, `AgentFunding`, `AgentAuthority`) | Keep controls disabled and withdraw the success claim until a read succeeds |
| F3 | `original_references` are saved before the effect only when a transport names them | Require them for every non-fixture transport; refuse submission otherwise |
| F4 | Hosted schema drift and recovery | Workers re-check the schema head each pass; host runbook for migrate, restore and rollback with rehearsals |
| F5 | Manual accessibility | Keyboard-only and screen-reader pass over the new research, adoption and replay surfaces |
| F6 | Dependency advisories and runtime reachability | Read-only advisory review with reachability per advisory; upgrades as separate leased changes |

## Stage 2 local public-runtime preparation

Milestone `RELEASE-E2E-L2-20261012-RUNTIME-LOCAL`, base `6fab6f2`. Local only: no host, provider, credential, deployment or financial action. Details and proposals: `docs/qualification/public-runtime/`.

| Area | Implementation | Files | Status |
|---|---|---|---|
| Shared quotas | Owner and GLOBAL allocations per resource with frozen caps, one reservation per original subject (locks GLOBAL then OWNER, both caps checked before any adapter call), idempotent KNOWN/UNKNOWN settlement with overrun, append-only events, operator-only `set-cap`. Migration 0010 moves `research_budgets` into OWNER allocations. | `usage/quota.py`, `migrations/versions/0010_shared_usage_quotas.py`, `research/investigation_jobs.py` | Local PASS candidate |
| G-N2, N4, G-N1 | Interrupted compute stays unknown liability; compute is measured in milliseconds and settled as whole seconds with overrun booked; corrected actual-data bounds recorded. | `research/investigation_jobs.py`, `research/investigation_tools.py`, `RUNTIME_GUARDS.md` | Local PASS candidate |
| Runtime guards | Production startup refusals (names only), `/readyz` reason codes including `quota_cap_mismatch`, shared per-owner write rate (429 + `Retry-After`), active research job limit, SQL statement timeout. | `core/settings.py`, `core/database.py`, `main.py`, `usage/rate_limit.py` | Local PASS candidate |
| F1 | Read-only `GET /v1/account-views/service[?agent_id=]` projects the owner's funding, admission, execution, recovery and removal rows as `evidence_class = SERVICE_PROJECTION` through `AccountViewContent`; unknown marks and unrealized results stay UNKNOWN; deposits are flows, not results. Shown in the "Saved connected state" panel. | `accounts/service_projection.py`, `accounts/views.py`, `components/ServiceAccountState.tsx`, `lib/account-views.ts` | Local PASS candidate |
| F2 | A saved change whose read-back fails keeps the last view marked unconfirmed and every change control paused until a read succeeds; no success notice. | `AgentActions.tsx`, `AgentFunding.tsx`, `AgentAuthority.tsx` | Local PASS candidate |
| F3 | Not changed. The signing/adapter seam is reserved for Stage 3. | — | Open (Stage 3) |
| F4 | Workers check the schema head before every pass and stop with exit code 3 before any effect; runbook rehearsed locally (dump, restore, check, downgrade/upgrade). | `core/worker_loop.py`, `execution/worker.py`, `tests/test_restore_rehearsal.py`, `RESTORE_ROLLBACK_RUNBOOK.md` | Local PASS candidate; hosted rehearsal open |
| F5 | Keyboard-only pass over the owned connected-agent, funding and projection surfaces at desktop and 390px (`runtime.spec.mjs`). Screen reader: NOT_RUN. | `tests/p03/runtime.spec.mjs`, `KEYBOARD_QA.md` | Partial |
| F6 | Read-only advisory and reachability record; no lockfile change. | `ADVISORY_ASSESSMENT.md` | Needs controller disposition |

## SOURCE-LOCAL: accepted P07 transport in the application (frozen interfaces)

Milestone `RELEASE-E2E-L2-20261012-SOURCE-LOCAL`, base `a7864a7`. Local only. Every source is a SYNTHETIC recording, no client reaches a network, and RG02/RG05 actual-data evidence stays NOT_RUN.

**Evidence class `RECORDED_NATIVE_RESPONSE` (additive).**
- What it is: native-shaped Envio HyperSync `QueryResponse` pages and QuickNode JSON-RPC results. Offline recorded clients replay them through the accepted P07 seams, unchanged:
  - `EnvioHypersyncSource` → `collect`;
  - `read_chain_id` → `corroborate_records`;
  - `normalize` → `project_binding`.
- Labels: `content_label` and the profile `evidence_class` stay `SYNTHETIC_FIXTURE`.
- Other classes: `RECORDED_RESPONSE` keeps its meaning. `PROVIDER_ACTUAL` is still refused (`actual_data_not_authorized`).

**Catalog.**
- Source: `tests/fixtures/research_history_native/native_history_v1.json` (`edge-os.recorded-native-bundle/1`). Its only writer is `tests/native_history_recordings.py`.
- Market: the pool and assets are 0xd1…/0xd2…/0xd3…, so the source has its own market, apart from the sample bundle.
- Response: `GET /v1/research/history-sources` lists both bundles. Each entry adds `transport` (null for bundle sources): provider, version, corroboration provider, `corroboration_sample_size` and `provider_requests_needed` (pages + 1 chain read + 1 receipt per sample). The response also adds `native_label`.

**Declaration.**
- `configuration.source.evidence_class` and `permitted_access` accept `RECORDED_NATIVE_RESPONSE`. The class must equal the listed source's class (`history_source_class_mismatch`).
- `resource_bounds.provider_requests` must cover the pages, the chain read and the receipts (`resource_bounds_too_small` at `/configuration/resource_bounds/provider_requests`).
- The user's own rules, market unit and adoption rules are unchanged.

**Collection** (`research/native_history_collection.py`). One `RequestBudget` equal to the declared `provider_requests` guards every injected client call:
- Before each call it checks cancellation, the job deadline and the remaining requests.
- A refused call is never made or counted. A made call counts even when it fails. Nothing is retried.
- The guard sits in `GuardedEnvioClient` and `GuardedQuickNodeClient`, which wrap any client. A refused Envio call becomes the accepted P07 stop (`CANCELLED`, `TIMEOUT` or `PROVIDER_ERROR`).
- A refused RPC call raises the application-owned `Refused`, which P07 does not catch. Corroboration then ends as `NONE`, `STOPPED_CANCELLED`, `STOPPED_DEADLINE` or `STOPPED_REQUEST_BUDGET_EXHAUSTED`, with `receipts_fetched`. No refused call is ever recorded as a mismatch.
- Corroboration samples min(declared, remaining requests) records. It is skipped as `NONE` when no record was kept (`NO_RECORDS`), fewer than 2 requests remain (`REQUEST_BUDGET_EXHAUSTED`) or the chain read failed (`CHAIN_READ_FAILED`).
- `chain_id_source` is `PROVIDER_READ` only when the recorded RPC answered 143, else `UNKNOWN`.
- `provider_facts` (decimals, pool tokens, venue, fee semantics, finality, delivery records, feasibility claim) are recorded declarations, labelled `RECORDED_DECLARATION` in `evidence_basis`.

**Usage.**
- The tool name stays `collect_recorded_history`.
- Native usage is `provider_requests_state = MEASURED_CLIENT_CALLS` with `{ENVIO_HYPERSYNC: n, QUICKNODE_JSON_RPC: m}`. It is known only while the total stays within the job's reservation; otherwise it is `INVALID` and stays liability.
- Settlement consumes the measured calls and releases the rest. A killed collection keeps unknown liability and is never collected again (Stage 2 rules unchanged).

**Dataset** (`edge-os.history-dataset/1`, additive keys on native datasets only).
- `transport`:
  - `envio`: P07 `transport_record()`;
  - `chain_read`;
  - `corroboration`: full entries with reasons;
  - `client_calls`;
  - `request_budget`;
  - `clients`.
- `evidence_basis` and a native `notice`: chain id and receipts were checked against recorded responses, not a network.
- Bundle-source content and saved hashes are unchanged.
- The job view adds `dataset.transport` (null for bundle sources): pages framed, calls, chain id/network, corroboration counts and reason, recorded declarations.

**Web.**
- `InvestigationReview` declares with the chosen source's class.
- Choosing a native source sets the reserved provider requests to its needed count and explains the count.
- Jobs show the computed transport facts apart from the recorded declarations.

**Unchanged.**
- The P07 library, P12/P14 numerical replay, P02 contracts and saved-run semantics.
- A LIMITED/UNRESOLVED native dataset stays unbound (`dataset_not_qualified`).
- Replay labels stay `SYNTHETIC_FIXTURE` and "simulated fills".

| Fault (native recording) | Result | Test |
|---|---|---|
| Page omits its end block fact | PARTIAL `PROVIDER_ERROR`, page 1 kept, report `SOURCE_LOSS` | `test_a_page_without_its_end_block_fact…` |
| Response echoes another chain | nothing kept, corroboration `NO_RECORDS` | `test_a_response_echoing_another_chain…` |
| Provider failure on page 2 | failed call counted, no retry | `test_a_provider_failure_counts…` |
| Receipt names another block / RPC failure | mismatch counted, no binding | `test_a_corroboration_mismatch…` |
| RPC reports another chain | `CHAIN_NOT_MONAD`, no receipt call | `test_another_chain_from_the_rpc…` |
| Sampled corroboration | `LIMITED`, unbound | `test_sampled_corroboration…` |
| Too few requests declared | 422 before any job | `test_a_declaration_without_requests…` |
| Cancellation after page 1 | later calls refused, 1 consumed, 26 released | `test_cancellation_after_the_first_page…` |
| Cancellation / deadline during receipts | corroboration `NONE` `STOPPED_*`, 4 receipts fetched, 0 mismatches, 7 consumed | `test_cancellation_during_receipts…`, `test_a_deadline_during_receipts…` |
| Deadline before / after the pages | no call / chain read refused | `test_a_passed_deadline…`, `test_a_deadline_passing_after…` |
| Worker killed in collection | unknown liability, never collected again | `test_a_worker_killed_during_collection…` |
| Other owner | 404, no client call | `test_another_owner_cannot_start…` |

## ORIGINAL-LOCAL: original transaction identity, receipts and current holdings (frozen interfaces)

Milestone `RELEASE-E2E-L2-20261012-ORIGINAL-LOCAL-v1`, base `70ca3bd`. Local only. Every provider response is an AUTHORED native-shaped recording replayed by an offline client; nothing here signs with a real key, broadcasts, reads a balance or reaches a network. Production keeps `execution_mode=unavailable`.

**Selection.** The original-transaction path is used only when the server is in `fixture` mode with a local `original_recordings_path` (refused in production) and the agent id carries the reserved marker `fx-original`. Every other fixture agent keeps the `FixtureChain` transport unchanged. No caller field selects it.

**Authored test signer (amendment A1).** The fixture wallet provider (`wallet_setup/adapter.py`, refused in production) returns the AUTHORED public test-signer address `0x2c7536E3605D9C16a7a3D7b1898e529396a65c23` for a fixture wallet whose agent id contains the reserved marker `fx-original`; every other fixture wallet keeps its SHA-256 placeholder address. The address is the eth-account documentation example key's sender. The application holds the address only, never a key; the signed bytes are frozen AUTHORED fixtures from the single offline writer `tests/original_transaction_recordings.py`. One public test address is not evidence of separate user wallets (PU06).

**Original envelope** (`edge-os.original-transaction/1`), saved privately in the attempt `content.original_transaction` and advanced only forward:

| Field | Source |
|---|---|
| `owner_id`, `agent_id`, `wallet_id`, `wallet_address`, `network_id`, `chain_id` | Verified owner, confirmed wallet setup and its provider evidence address, `NETWORK_NAMES`. |
| `strategy_id`, `publication_revision_id`, `execution_revision_id`, `content_hash`, `consent_adoption_id`, `consent_hash`, `policy_binding` | The saved evaluation job and intent. |
| `action_id`, `payload_hash`, `operation`, `attempt_id`, `claim` (the existing ACTIVE claim), reservations | The saved intent, queue claim and P22 decision. |
| `candidate` (`candidate_hash`, to, value, data, selector, intent, fees, program) | P20 `prepare_unsigned_transaction` over the recorded route response and a server-built `ApprovedAdapterConfiguration` (input = the saved intent input, minimum output from the saved expected output). |
| `nonce` | One recorded `eth_getTransactionCount(wallet_address, "pending")`. |
| `fee_envelope` (`gas_limit`, `max_fee_per_gas`, `max_priority_fee_per_gas`) | The recorded route profile. `gas_limit × max_fee_per_gas` must not exceed the reserved per-action (entry) or per-exit gas cap. |
| `unsigned` (EIP-1559 type 2 fields) | Built from the candidate, nonce, fee envelope and `chain_id`. |
| `signing_request` (`request_id`, Privy `POST /v1/wallets/{wallet_id}/rpc`, `eth_signTransaction` body) | Built by the server; `request_id` = attempt id. |
| `signed_bytes` (private), `transaction_hash` | `data.signed_transaction` of the signer reply; hash = Keccak-256 of the entire signed serialization (`eth_utils.keccak`). Never `TypedTransaction.hash()` (signing preimage), never SHA-256. |
| `broadcast` | One `eth_sendRawTransaction`; the returned hash must equal `transaction_hash`. |
| `stage` | `PREPARED` → `SIGN_REQUESTED` → `SIGNED` → `BROADCAST_REQUESTED` → `BROADCAST_RETURNED`, or a terminal refusal stage. |

Three identities stay distinct: `candidate_hash` (application SHA-256), `transaction_hash` (Keccak of the signed bytes) and `provider_reference` (the signer request id and broadcast reply).

**Order.** IN_FLIGHT attempt commit → P22 `acquire_submission` → route quote + nonce read (no SQL lock held) → `PREPARED` saved → durable stop/removal recheck → signer call → signed bytes validated → `SIGNED` saved with bytes and hash → stop/removal and deadline recheck → `BROADCAST_REQUESTED` saved → one broadcast → `BROADCAST_RETURNED` saved. A save that fails stops the sequence: no later call is made.

**Signed-byte validation.** Only type 2 (EIP-1559) is supported; any other type is refused. The decoded `chainId`, `nonce`, `to`, `value`, `data`, `gas`, `maxFeePerGas`, `maxPriorityFeePerGas` and an empty access list must equal the frozen unsigned transaction, and the recovered sender must equal `wallet_address`. Size limit 8 KiB.

**Outcomes** (transport vocabulary reused; nothing is retried, re-quoted, re-nonced, re-fee'd or re-signed, and no second action exists):

| Event | Outcome | Liability |
|---|---|---|
| Unsupported network/route/asset, quote blocked or unknown, fee over the gas reservation, stop/removal or deadline before signing, persistence failure before signing | `DEFINITELY_UNSENT` | Released by the accepted P22 path. |
| Signer refusal: an explicit error envelope (`error` object, no `data`) | `DEFINITELY_UNSENT` | Released. |
| Signer reply without usable `data.signed_transaction` that is not an explicit refusal (another spelling, field missing, not an object), or a JSON-RPC error | `SUBMISSION_POSSIBLE` (`SIGNED_RESPONSE_REJECTED`: `SIGNER_REPLY_UNRECOGNIZED`, or `SIGNING_UNKNOWN`); never broadcast | Kept: a signature may exist outside the application. |
| Signer reply lost or timed out | `SUBMISSION_POSSIBLE` (`SIGNING_UNKNOWN`) | Kept. |
| Signed bytes malformed, wrong type, field or sender mismatch | `SUBMISSION_POSSIBLE` (`SIGNED_RESPONSE_REJECTED`); never broadcast | Kept: a signature may exist outside the application. |
| Stop/removal, deadline or persistence failure after signing | `SUBMISSION_POSSIBLE`; never broadcast | Kept. |
| Broadcast reply lost, error or hash mismatch | `SUBMISSION_POSSIBLE` | Kept. |
| Broadcast returned the same hash | `SUBMISSION_POSSIBLE` (`BROADCAST_RETURNED`) | Kept until an independent receipt reconciles. |

Byte-identical resend is disabled in this milestone. A restart finds the IN_FLIGHT attempt or the retained claim and makes no second call.

**Receipts.** `POST /v1/actions/{id}/reconcile` reads one recorded `eth_getTransactionReceipt(transaction_hash)` from an observation client separate from the broadcast client, and passes it through P20 `normalize_observation` with the saved `candidate_hash`, `chain_id`, `wallet_address` and `transaction_hash`. The candidate identity is supplied only when the receipt's `transactionHash`, `from` and `to` equal the saved values. Actual input and output come only from ERC-20 `Transfer` logs of the saved sell and buy tokens to or from the wallet, whose `data` is read as one exact 32-byte ABI word (JSON-RPC `DATA`; a `QUANTITY`-form value is not read); gas is `gasUsed × effectiveGasPrice` in native MON. A missing value stays `null`. Mapping: proven `CONFIRMED` → `CONFIRMED` with all actuals; `CONFIRMED` without all actuals → `CONFIRMED` with the missing values `null`, which the accepted P22 settlement records as a `BREACHED` `MISSING_RECONCILED_*` case keeping every reservation; `REVERTED` → `REVERTED` (missing gas: same breach); `PENDING`, `TIMEOUT`, `SUBMISSION_UNKNOWN`, `ACKNOWLEDGEMENT_LOST` → `SUBMISSION_UNKNOWN`; `REJECTED` (wrong hash, wallet, chain or binding) → nothing applied, reasons returned. Recovery fingerprints keep a repeat a no-op and changed evidence a discrepancy. A reconcile while the attempt is still in flight without a saved hash, or on an original refused before signing, adds no evidence (`NOT_OBSERVED`, `ORIGINAL_IN_FLIGHT` / `ORIGINAL_REFUSED_UNSENT`); a late submission reply never rewrites an attempt a reconciliation already settled. Planned amounts are never substituted: the generic settlement no longer falls back to them; the labelled `FixtureChain`/`LocalFixtureTransport` adapters supply their authored amounts explicitly.

**Current holdings** (`edge-os.current-holdings/1`). The holdings port returns, per requested asset, `raw`, `decimals`, and for the observation `wallet_address`, `chain_id`, `block_number`, `observed_at` (the block time), `finality`, `source`, `evidence_class` and `missing` assets. Admission and revalidation use `observed_at` as `checked_at`, so a stale observation is refused by the existing freshness check (`STALE_CONTEXT`); the current clock is never stamped onto supplied holdings. `eth_call` results (`balanceOf`, `decimals()`) are read as exact 32-byte ABI words; `eth_getBalance` and block fields as `QUANTITY`. An unreadable `eth_chainId` refuses the whole observation. A wrong wallet or chain, an unknown or mismatched decimals value, a missing asset or a future/stale time is `HOLDINGS_UNAVAILABLE` with the reason, and no action is admitted. Native MON is gas only; a native trading asset is refused. Limit: the recorded holdings client reads at the saved wallet address, so `HOLDINGS_WRONG_WALLET` can only fire for a port that reports another address; it is a guard for future ports, not a proven check here. Funding shows these fields apart from deposit history, attributed positions and reservations. The fixture holdings adapter stays authored: it is computed at the caller's read, so it carries `observed_at: null` and `finality: AUTHORED`, and admission uses that step's own time.

**Owner projection.** `GET /v1/actions/{id}` shows `original_transaction` without `signed_bytes`, unsigned bytes or the signing request body: stage, `candidate_hash`, `transaction_hash`, `nonce`, fee envelope, `signing_request_id`, `signed_bytes_sha256`, `signed_bytes_length`, broadcast result and `evidence_class`. Another owner gets `404` and no client call.

**Worked fixture** (AUTHORED, `tests/fixtures/original_transaction/original_transaction_v1.json`, writer `tests/original_transaction_recordings.py`): ENTRY selling `100000000` of `0x2222…2222` (6 decimals) for `50000000000000000000` of `0x1111…1111`, minimum output 99 % (`49500000000000000000`), chain `143`, nonce `0`, `to` `0x00000000000000000000000000000000000f1007` (authored), value `0`, gas limit `300000`, max fee `3000000000`, priority fee `1000000000`, empty access list, sender `0x2c7536E3605D9C16a7a3D7b1898e529396a65c23`. Transaction hash (Keccak-256 of the full signed bytes) `0x7067b4c886f172b32b1c2839bcd70a45186817e3ade5648bb34fc0d6ea7aa28d`; the EXIT at nonce `1` is `0x55b5277b4b8fcd0c3f23b2f05b23f78bc0c37934a7bcbf509e1805872045dcc7`. The authored receipt moves the sell amount out and the expected output in, `gasUsed 150000 × effectiveGasPrice 2000000000` = `300000000000000` native.

**Time limits.** Each injected client is called at most once per stage, and the stage rechecks (stop, removal, intent expiry) run before signing and before sending. A per-call timeout for a real signer or RPC client is not set by the recorded clients; it is a required property of any actual adapter (`docs/qualification/original-transaction/ACTUAL_ORIGINAL_TRANSACTION_QUALIFICATION_PACKET.md`). The worker's per-job advisory transaction stays open across the calls; it blocks no stop, admission or other owner.

**Fault matrix** (each row names its test in `apps/api/tests/test_original_transaction_journey.py` unless stated; SQL is independent evidence, the public route is the assertion):

| Case | Expected | Test |
|---|---|---|
| Happy path, then reconcile a proven receipt | 1 quote, 1 nonce, 1 sign, 1 broadcast; hash equals the worked literal; CONFIRMED once; repeat is a no-op | `test_the_original_transaction_is_saved_before_each_effect_and_settles_once` |
| Exit after entry | next nonce `1`, its own hash | `test_the_exit_is_one_more_original_transaction_with_the_next_nonce` |
| Explicit signer refusal | 0 broadcast; DEFINITELY_UNSENT; reservations released | `test_a_signer_refusal_sends_nothing_and_releases_the_reservations` |
| Unrecognized signer reply (another spelling, field missing, not an object) | 0 broadcast; `SIGNER_REPLY_UNRECOGNIZED`; reservations kept | `test_an_unrecognized_signer_reply_keeps_the_liability_and_is_never_sent` |
| Signer reply lost | 0 broadcast; unknown kept; rerun makes no call | `test_a_lost_signer_reply_keeps_the_liability_and_a_restart_makes_no_second_call` |
| Signed bytes: wrong type, malformed, oversize; another nonce | 0 broadcast; `SIGNED_RESPONSE_REJECTED` with the reason | `test_rejected_signed_bytes_are_never_broadcast_and_keep_the_liability`, `test_signed_bytes_for_another_nonce_are_rejected` |
| Signed bytes: each field, another signer, tampered byte; public vectors | refused with the field reason | `tests/execution/test_original_signed_bytes.py` |
| Unmarked placeholder wallet on the original path (A1) | `SIGNED_SENDER_MISMATCH`; 0 broadcast; reservations kept | `test_an_unmarked_placeholder_wallet_is_refused_as_another_signer_and_never_sent` |
| Save failure at `PREPARED`, `SIGN_REQUESTED` / `SIGNED`, `BROADCAST_REQUESTED` | 0 sign / 0 broadcast | `test_a_failed_save_stops_before_the_next_effect` |
| Broadcast reply lost; another hash returned | unknown kept; 1 broadcast; the lost one reconciles CONFIRMED | `test_a_lost_broadcast_reply_reconciles_the_original_from_its_receipt`, `test_a_broadcast_reply_with_another_hash_is_kept_unknown` |
| Stop or removal after signing | 0 broadcast; unknown kept | `test_a_stop_recorded_after_signing_prevents_the_broadcast`, `test_a_removal_recorded_after_signing_prevents_the_broadcast` |
| Crash before sending, then restart | no second quote, sign or send | `test_a_crash_after_signing_leaves_one_original_that_a_restart_never_resends` |
| Duplicate and concurrent runs of one job | 1 sign, 1 send | `test_concurrent_runs_of_one_job_sign_and_send_once` |
| Reconcile during signing; reconcile of a refused original | no evidence added; the original continues | `test_a_reconcile_during_signing_observes_nothing_and_never_interrupts_the_original`, `test_reconciling_a_refused_original_adds_no_evidence` |
| Receipt wrong hash, wallet or chain | nothing applied | `test_a_receipt_for_another_transaction_or_wallet_applies_nothing`, `test_a_receipt_on_another_chain_applies_nothing` |
| CONFIRMED missing output, input or gas; REVERTED missing gas; `QUANTITY`-form log data | BREACHED `MISSING_RECONCILED_*`; reservations kept | `test_a_receipt_without_every_actual_never_releases_the_liability` |
| Changed evidence after settlement | discrepancy; original truth unchanged | `test_changed_evidence_after_settlement_cannot_rewrite_the_original_outcome` |
| Holdings stale, wrong decimals, missing asset, `QUANTITY`-form balance, another chain, unreadable chain | admission denied; funding shows the reason | `test_unusable_holdings_admit_nothing_and_show_unavailable`, `test_holdings_observed_on_another_chain_admit_nothing`, `test_holdings_whose_chain_cannot_be_read_admit_nothing` |
| Route the recording does not hold | `ROUTE_BLOCKED` before signing | `test_a_route_the_recording_does_not_hold_is_blocked_before_signing` |
| Two owners | 404; 0 injected calls | `test_another_owner_cannot_read_or_reconcile_and_makes_no_call` |
| Holdings identity shown apart from deposits | block, time, finality, wallet, source | `test_recorded_holdings_carry_their_observation_identity_apart_from_deposits` |

## Decisions for the builder

0. One open position per agent and revision at a time is enforced by the strategy (`max_open_positions: 1`) and the worker (an exit uses the open position); repeated entry/exit cycles are now possible because each entry has its own position id.

1. G05: limited real-data representation in P02, or a dataset that qualifies the existing binding.
2. G17/IC08: independent opaque-program bounds and native MON treatment for the selected route.
3. Removal `FAILED` keeps submission open, as accepted. Confirm or change.

## Evidence classification and limits

Local fixture only. NOT_RUN: real Privy login, real wallet creation or lookup, real deposits, quotes, observations, signing, broadcast, receipts, removal, model and hosted multi-process operation. The worker is bounded and manual or loop-driven; no always-on trading claim follows. Actual-data RG02/RG05 and the live parts of IC01–IC08 remain open; RG01–RG06 have a local recorded-response implementation (section above).
