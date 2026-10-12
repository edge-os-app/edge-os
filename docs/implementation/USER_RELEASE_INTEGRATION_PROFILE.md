# User-release integration profile (#58 Stage 1 local milestone)

Status: **frozen interfaces for the local connected fixture journey; candidate under review.** Issue [#58](https://github.com/edge-os-app/edge-os/issues/58), task `RELEASE-E2E-L2-20261012-S1`, base `c119e40`. This profile records how the accepted financial packages are composed into the application. It qualifies no real provider, wallet, chain, model, host or user. A fixture pass here proves application wiring only.

## Responsibility

Compose the accepted funding (P18), admission (P22), execution (P23), recovery (P24), scoped stops (P25), inactive consent (P26) and removal (P30) services behind authenticated owner-scoped routes, forward migrations, a durable bounded worker and the existing screens. Domain algorithms are reused unchanged except where this profile names a change.

## Files

| File | Responsibility |
|---|---|
| `apps/api/migrations/versions/0008_financial_state.py`, `migrations/env.py` | Create the seven `*_local` schemas, their accepted tables and the evaluation jobs table. `alembic check` covers every metadata. |
| `core/settings.py` | `execution_mode` (`fixture`/`unavailable`, production refuses `fixture`) and `fixture_effects_path`. |
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

`SubmissionControls` answers the single `StopReader` that admission (`admit_and_reserve`, `acquire_submission`) and execution revalidation already consult inside their transaction. Admission and `acquire_submission` run under the shared P22 per-wallet advisory lock, which is the serialization point with a new stop or removal; revalidation runs under the separate P23 execution lock and is an earlier, additional check. It returns durable stop reasons for the operation plus every removal reason for the wallet. Removal now denies from `REQUESTED` (`REMOVAL_REQUESTED`), because the request is saved before any provider effect (gap G14); `FAILED` and absent records do not deny. `request_removal` and `request_stop` take the same lock, so either the control commits first and the transition is denied, or ownership commits first and the original action continues and stays recoverable. A stop or removal never releases reservations, cancels a submitted action, liquidates or withdraws.

## RG interfaces frozen for Task 6 (definitions only; not implemented in this milestone)

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

## Decisions for the builder

0. One open position per agent and revision at a time is enforced by the strategy (`max_open_positions: 1`) and the worker (an exit uses the open position); repeated entry/exit cycles are now possible because each entry has its own position id.

1. G05: limited real-data representation in P02, or a dataset that qualifies the existing binding.
2. G17/IC08: independent opaque-program bounds and native MON treatment for the selected route.
3. Removal `FAILED` keeps submission open, as accepted. Confirm or change.

## Evidence classification and limits

Local fixture only. NOT_RUN: real Privy login, real wallet creation or lookup, real deposits, quotes, observations, signing, broadcast, receipts, removal, model and hosted multi-process operation. The worker is bounded and manual or loop-driven; no always-on trading claim follows. RG01–RG06 and the live parts of IC01–IC08 remain open.
