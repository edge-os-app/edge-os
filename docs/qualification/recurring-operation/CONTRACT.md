# Recurring operation LOCAL contract (P27, frozen before implementation)

Task `RELEASE-E2E-L2-20261013-P27-LOCAL-v1`, issue #41 under #58 (AUT01–AUT08). Base `ed228f7`. Status: **LOCAL composition only.** Every observation, quote, holding, transport and receipt is an authored fixture (`SYNTHETIC_FIXTURE`) served by the configured fixture ports. Production keeps the `unavailable` ports, so no deployment can activate and no occurrence can decide. Nothing here is a production operating profile, timing qualification, actual forward feed or financial permission.

## 1. Reused engine (no second engine)

- Occurrences are ordinary `execution_evaluation_jobs` rows. `ConnectedExecution.run_job/run_pending` advance them through the accepted stages: decide → enqueue (admission) → submit (claim, revalidation, transport) → settle. `reconcile_action` settles an original action from an independent receipt only.
- Existing uniqueness stays: one job per `(owner, agent, request_key)` and per `(owner, agent, consent_adoption_id, decision_slot)`. A recurring occurrence also carries `deployment_id`. A manual job and a recurring occurrence for the same consent and slot are the same job (the insert does nothing on conflict), so one slot never has two decisions or two actions.
- Admission keeps its persistent per-mandate counters (quote, base, gas, attempt budget). They are not per tick, and a new deployment, restart, top-up or returned proceeds does not replenish them.
- Stops and removal keep their accepted enforcement at admission and again before submission ownership.

## 2. Deployment (explicit authenticated recurring authorization)

`POST /v1/agents/{agent_id}/deployment` with `{request_key, expected_consent_hash}` activates recurring operation for the agent's current adopted consent:

- The server resolves the owner, confirmed agent wallet/network, publication revision UUID, execution revision, content and manifest hashes, and the latest adopted consent (`resolve_agent`, `adopted_consent`). `expected_consent_hash` must equal the adopted consent hash (409 `deployment_consent_mismatch`), so activation binds what the owner reviewed.
- `derive_approval` must produce an approval now (fixture qualification, unexpired supported terms). Otherwise 503 `activation_unavailable` (production) or 409 with the denial code.
- One deployment per adopted consent, ever. Same `request_key` → the original (200 replay). Another key while that consent's deployment exists → the same deployment (200 replay), never a second one. An ENDED deployment is terminal for its consent: activation for it returns 409 `deployment_ended`. Recurring operation restarts only through a newly reviewed and adopted consent (a new mandate with its own reviewed counters); under the accepted consent rules (one review per agent and revision), that needs a new agent setup.
- At most one ACTIVE deployment per `(owner, agent, wallet, network)`.

`POST /v1/agents/{agent_id}/deployment/end` ends the ACTIVE deployment (`OWNER_ENDED`). Every ended deployment (any reason) authorizes no further work:

- **Serialized with submission ownership.** The end commits under the accepted per-wallet admission lock (`acquire_wallet_lock`). `DeploymentEndControl`, composed into the shared `StopReader` seam, denies the exact ADMITTED action of an ended deployment's occurrence (matched through its saved admission decision, intent and job). Admission reads that seam inside the same lock in `acquire_submission`, and execution reads it again at revalidation. If the end commits first, ownership is refused (`STOPPED_SCOPE`) or revalidation denies, no transport call happens and the unsent action is released through the accepted cancellation. If ownership commits first, the end waits for the lock, and the owned original keeps its liability and receipt-only reconciliation. There is no tolerance window.
- **Worker stages.** The worker also checks the deployment before each stage: a not yet decided occurrence ends `DENIED DEPLOYMENT_ENDED:<reason>`, and an admitted, unsent one is released through the accepted cancellation.
- **Saved intent after a crash.** If the worker stopped after `enqueue` saved the intent and before the job recorded its action, any terminal denial (an ended deployment, changed identity or consent) first reconnects the saved intent through the job's decision and releases it through the guarded cancellation. A submission-owned or possibly sent action is never released. Without a change, the saved intent is reused and sent once (`_enqueue` reuses it before re-deriving authority).
- Ending does not sell or release unknown liability. Manual evaluations and other deployments are not affected by an end.

Activation is also refused (409 `agent_removed`) while a removal is requested or confirmed for the agent wallet. Another owner's activation for an agent gets 409 `agent_not_ready`, the same as an unknown agent and as the existing manual `POST /actions`; reads and `end` get 404.

`GET /v1/agents/{agent_id}/deployment` returns the durable projection (section 6), or `{"deployment": null}`.

A chart visit, a consent adoption or a manual evaluation never activates a deployment.

## 3. Scheduler tick and missed slots (producer)

`RecurringScheduler.tick(now)` runs over ACTIVE deployments, at most `limit` per pass, least recently ticked first (`last_tick_at` NULLS FIRST), so a bounded window rotates through every deployment. Each runs in its own transaction with the deployment row locked (`FOR UPDATE SKIP LOCKED`, so a second producer skips it), and a failure of one deployment is logged by error class and never stops the others:

1. Re-resolve identity and authority. A changed agent/revision → `ENDED IDENTITY_CHANGED`; a different or no adopted consent → `ENDED CONSENT_CHANGED`; no approval now → `ENDED` with the approval denial (`CONSENT_EXPIRED`, `ACTIVATION_UNAVAILABLE`, `TERMS_*`); a requested or confirmed removal → `ENDED REMOVAL_REQUESTED`. An ended deployment creates nothing.
2. `due = decision_slot(now)` on the UTC five-minute grid. If the saved cursor equals `due`, nothing is created.
3. The first owed slot is the slot after the saved cursor or, before any tick, the slot in which the owner activated. Every owed slot before `due` is **missed**: the count is added to `missed_slots` and one interval `{from, to, count, reason: "PRODUCER_ABSENT", recorded_at}` is appended to `missed_intervals`, which keeps the latest 20 intervals. No job is created for a missed slot; no stale trade is replayed, and no old observation or decision time is invented.
4. One occurrence job is inserted for `due` (`request_key = recurring:<deployment_id>:<slot>`), the cursor advances to `due`, and `last_tick_at` is saved, all in one transaction.

A restarted producer resumes from the saved cursor; a failed tick commits nothing (cursor, tick time and counts unchanged). Two producers on one deployment create one job per slot (row lock, then the existing unique slot constraint).

After the tick, the producer pass reconciles `SUBMITTED` occurrences of ACTIVE or ENDED deployments through `reconcile_action` (receipt only; idempotent; `receipt_unavailable` leaves it waiting), least recently tried first: each try updates the job's `updated_at`, so an original that never settles cannot hold the window for another action or owner, and a failure of one is isolated. Then it runs one bounded worker pass over runnable occurrence jobs (manual evaluations stay with the existing bounded worker process; either process may advance an occurrence, and the per-job advisory lock lets only one hold it).

## 4. Observations and the saved evaluation outcome

`MarketObservationRequest`/`MarketObservationPort.observe` and `EvaluationInputs` stay the interface. Before any decision, the worker requires (LOCAL policy):

| Check | Denial reason (no decision, no intent) |
|---|---|
| Port answers | `OBSERVATIONS_UNAVAILABLE` |
| `market_binding_id` equals the revision's | `OBSERVATIONS_WRONG_MARKET` |
| `inputs.observed_at()` equals the decision slot | `OBSERVATIONS_WRONG_TIME` |
| Provenance has `evidence_class`, `market_binding_id`, `collected_at`, `availability_basis`, `finality` | `OBSERVATIONS_PROVENANCE_INCOMPLETE` |
| `evidence_class` is a forward class allowed by the mode (fixture: `SYNTHETIC_FIXTURE` only; historical/recorded/Nansen/quote classes never) | `OBSERVATIONS_NOT_FORWARD` |
| `slot ≤ collected_at ≤ now` and `now − collected_at < SLOT` | `OBSERVATIONS_STALE` |

Warm-up and missingness stay inside `EvaluationInputs`; a missing essential bucket evaluates `INELIGIBLE` through the accepted evaluator.

The observations read again at submission meet the same boundary (exact market and slot, complete provenance, a forward class, collection inside the current slot) before any effect. A saved decision never qualifies a degraded later reading. A failure leaves the action saved and unsent with `WAITING:SUBMISSION_<reason>` and a `submission_observations` record in the job provenance; the saved decision and outcome stay. A later pass in the slot may read again; at the next slot the intent expires and is released through the accepted cancellation.

Every evaluation (recurring or manual) saves one row in `execution_evaluation_outcomes` before any intent: `outcome ∈ {SIGNAL, NO_SIGNAL, INELIGIBLE, UNAVAILABLE}`, `reason`, `decision_id` (null for UNAVAILABLE), `inputs_observed_at` (the decision input time), `inputs_collected_at` (the provenance collection time), `evaluated_at` (the worker's time), and the observation provenance. `execution_decisions` keeps its three statuses and all existing consumers. An UNAVAILABLE outcome creates no decision and no intent; its outcome row and the job's end commit in one transaction, and a saved UNAVAILABLE outcome stays final on a retry. If the worker stops after the decision and before the outcome row, the restart writes the row from the saved decision: `evaluated_at` is the decision's own time, an unsaved collection time stays null, and the provenance says `recovered_after_restart`.

The current-slot rule applies to manual evaluations too: a manual job evaluated after its slot now ends `UNAVAILABLE OBSERVATIONS_STALE` with no decision row (before, it saved a decision and later expired at enqueue or submission). No effect was possible either way.

## 5. Actions, limits and recovery

- ENTRY is sized from the revision; EXIT is the full attributed position; re-entry is a later ENTRY after the position closed (the fixture market rises when flat and falls when a position is open). Additions, partial exits, withdrawals and liquidation stay unavailable.
- Cumulative limits are the admission counters; exhaustion is `ADMISSION_DENIED` with the accepted reason.
- An unknown original action keeps its claim and reservations. Later occurrences still save their evaluation, and the accepted claim keeps any new submission for that wallet waiting; nothing is re-signed, repriced, rebroadcast or replaced. The producer's reconciliation pass settles the original from its receipt; repeated settlement is idempotent. Another owner's wallet has its own claim and is not blocked.

## 6. Durable projection (`GET …/deployment`)

`deployment`: id, state, end reason, activated/ended times, exact identity (agent, wallet, network, strategy, publication revision, execution revision, content/manifest hashes, consent adoption and hash).
`producer`: `last_tick_at`, `cursor_slot`, `producer_silent` (no tick within two slots), `next_due_slot` (cursor + SLOT, only while ACTIVE and a producer is seen; otherwise null with `no_next_reason` = the end reason or `PRODUCER_NOT_SEEN`), `missed_slots`, `missed_intervals`.
`occurrences` (latest 20): slot, job state/outcome/reason, evaluation runs and times (`created_at`, `updated_at`, `runs`), the saved evaluation outcome with `inputs_observed_at`, `inputs_collected_at`, `evaluated_at`, and the submission attempt (`started_at`, `completed_at`, outcome) when one exists.
`pending_reconciliation`: action ids whose queue state is unsettled.
`wait_reason`: the first that applies — `ENDED:<reason>`, `REMOVAL:<state>`, `WAITING_RECONCILIATION`, `STOPPED:<modes>`, `PRODUCER_NOT_SEEN` (no tick within two slots), else null.

The direct account view reads this projection. P31 may read the same projection only after its own accepted assignment; this task does not consume lane 3.

## 7. Producer process

`python -m edge_os_api.execution.recurring_producer` runs passes (tick → reconcile → bounded occurrence worker pass): `--once`, or `--interval S` (positive) with optional `--max-passes N` (at least 1). It checks the migration head before each pass (schema drift exits 3, as the worker loop does; a `--once` pass skipped because the database is unavailable exits 4) and finishes the current pass on SIGTERM/SIGINT. `--clock-offset-minutes M` exists for LOCAL verification only. It is refused unless the execution mode is `fixture` and the environment is not production, and it never changes a saved decision time.

## 8. Migration 0012

Adds `execution_recurring_deployments`, `execution_evaluation_outcomes` and `execution_evaluation_jobs.deployment_id`. The downgrade refuses while any deployment exists, because removing it would lose durable recurring work and its occurrence lineage. Without deployments, it drops the outcome rows of manual evaluations (their saved input and evaluation times); each job keeps its own outcome and reason, and no liability is held there.

Manual evaluation keys must not start with the reserved `recurring:` prefix (422), so an owner cannot occupy an occurrence key.

## 9. Not proved here

Actual forward observations, provider timing, hosted operation, live permission, actual signing/broadcast, and P31 chat health are outside this LOCAL contract. AUT08 is NOT_RUN. See `HOSTED_RECURRING_PACKET.md` (PROPOSED).
