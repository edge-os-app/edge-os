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

An evaluation job is unique per `(owner, agent, adopted consent, decision slot)` and per `(owner, agent, request_key)`. The decision slot is the latest five-minute UTC grid point at scheduling. Stages are saved before the next stage: `QUEUED` → decision saved (`DECIDED` for a signal, `COMPLETED` with `NO_SIGNAL`/`INELIGIBLE`) → one intent enqueued (`ENQUEUED`, or `COMPLETED ADMISSION_DENIED`) → submission (`COMPLETED` with the terminal queue state, or `SUBMITTED` while the original action needs reconciling). A decision already saved for the same revision and slot is reused; a saved intent for the decision is reused. Observations whose provenance names another market binding, or another decision time, end the job `UNAVAILABLE OBSERVATIONS_WRONG_MARKET` before any decision. A quote is never a rule observation. The worker holds a per-job transaction advisory lock, so concurrent workers skip a held job.

## IC03 holdings

Admission and revalidation read current holdings from the holdings port, plus attributed inventory from the durable admission position. Deposit history (`deposit_balances`) stays separate from `current_holdings`. A request can never supply either.

## IC04 browser wallet completion

`POST …/complete` retains the browser-reported wallet id as an untrusted `RESULT_RETURNED` event, then binds only when an independent provider lookup returns the same id for the verified owner, chain type `ethereum`, and no other agent of the owner holds it. A confirmed setup never changes wallet (a different id records `CONFLICTING_RESULT`); a completion after a proved pre-dispatch cancellation binds nothing (`LATE_RESULT_AFTER_CANCEL`); a lookup miss or foreign owner leaves `UNKNOWN`. A repeated completion is the reconciliation path for a lost lookup reply. No server creation runs on this path; existing prepare/dispatch/resume/cancel are unchanged. Production keeps the unavailable provider.

## IC05 activation

Consent rows stay INACTIVE. `derive_approval` returns an approval only for `qualification == "fixture"` (the server's own mode), terms version `connected-spot/1`, unexpired terms, exactly the allowances `quote_input`, `base_inventory`, `per_action_gas`, `per_exit_gas`, a gas budget, one allocation in the quote asset, and assets that match the revision. The snapshot is labelled `SYNTHETIC_FIXTURE_QUALIFICATION`, `approval_id` and `mandate_id` equal the adoption id, `policy_binding` equals the consent hash. Otherwise the reason is `ACTIVATION_UNAVAILABLE`, `CONSENT_EXPIRED`, `TERMS_VERSION_UNSUPPORTED`, `TERMS_INCOMPLETE` or `TERMS_ASSET_MISMATCH`. Real activation needs the P20/P21 qualification; it is not circular because Probe B consumes this inactive consent plus its own exact packet.

## IC06 original transaction references

Before the transport call, in the same transaction as the `IN_FLIGHT` attempt, a transport that defines `original_references(prepared)` records `edge-os.original-transaction-references/1`: `signing_request_id`, `nonce`, `fee_envelope`, `unsigned_bytes`, `signed_bytes`, `transaction_hash`, `provider_reference`, `evidence_class` and `absent_reason`. The fixture signs nothing, so every chain identity is `null` with `FIXTURE_TRANSPORT_SIGNS_NOTHING`. A live port must fill them before its effect boundary. On uncertainty only `POST /v1/actions/{id}/reconcile` runs; nothing constructs a replacement.

## IC07 receipts

The receipt port answers for the exact action, wallet and network. Absence or ambiguity is `SUBMISSION_UNKNOWN`. Reconciliation passes the receipt to the accepted recovery service: a confirmed receipt without actual gas is a durable P22 breach that keeps every reservation and blocks the wallet; a wrong-tuple receipt proves nothing. Planned amounts are fixture inputs to `FixtureChain`; the connected path never substitutes planned values for missing actuals.

## IC08 and residual exposure

Not implemented here. Independent opaque-program limits, acquired/residual exposure and native MON trading versus gas treatment stay with P21/Stage 3. This milestone keeps native MON as gas only, and the trading asset is the revision's quote token.

## Stop and removal enforcement

`SubmissionControls` answers the single `StopReader` that admission (`admit_and_reserve`, `acquire_submission`) and execution revalidation already consult inside their transaction under the shared per-wallet advisory lock. It returns durable stop reasons for the operation plus every removal reason for the wallet. Removal now denies from `REQUESTED` (`REMOVAL_REQUESTED`), because the request is saved before any provider effect (gap G14); `FAILED` and absent records do not deny. `request_removal` and `request_stop` take the same lock, so either the control commits first and the transition is denied, or ownership commits first and the original action continues and stays recoverable. A stop or removal never releases reservations, cancels a submitted action, liquidates or withdraws.

## RG interfaces consumed later (Task 6, not implemented)

P07 consumption follows controller amendment `r58-r7-a`: the isolated `research_history` library returns `CollectionResult` (status `COMPLETE`/`PARTIAL`, stable `stop_reason`, measured invocation counts separate from evidenced provider request counts, unknown as null) and `NormalizedHistory` with ordered buckets (`bucket_start`, `bucket_end`, `status`, `close` price string or null, `quote_volume`, `available_at`, `availability_basis`, `reasons`) and `normalized_sha256` over the payload without its own digest. Malformed caller input is `InvalidInput` before any source call. Only overall `QUALIFIED` projects to P02; `LIMITED` is stored beside the declaration and keeps real-market rule binding unavailable (G05 open). #58 owns the bucket-to-`InputObservation` mapping, verified-owner persistence, investigation jobs, budgets, HTTP and UI. The investigation job reuses the evaluation-job pattern above: one row per owner/request/declaration identity, reserved budget before effects, original attempt kept on cancellation, deadline or lost reply.

## Decisions for the builder

1. G05: limited real-data representation in P02, or a dataset that qualifies the existing binding.
2. G17/IC08: independent opaque-program bounds and native MON treatment for the selected route.
3. Removal `FAILED` keeps submission open, as accepted. Confirm or change.

## Evidence classification and limits

Local fixture only. NOT_RUN: real Privy login, real wallet creation or lookup, real deposits, quotes, observations, signing, broadcast, receipts, removal, model and hosted multi-process operation. The worker is bounded and manual or loop-driven; no always-on trading claim follows. RG01–RG06 and the live parts of IC01–IC08 remain open.
