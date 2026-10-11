# Action recovery profile (local stage)

Owned package: `apps/api/src/edge_os_api/recovery/`. This profile records the
local original-action recovery domain for P24 #33. It is the approved 2026-10-11
release portion only. It is not API/UI wiring, not a production migration, not
live operation and not a recurring service. It adds no fresh route, no automatic
resend and no replacement economic action.

## Responsibility

Recovery reopens the original saved P23 intent, queue entry, attempt and claim by
owner and exact action, wallet and network, then reconciles controlled, labelled
local outcome evidence for that same action through the accepted P22
`AdmissionService`. It persists a durable per-action case and an append-only
evidence log. Reconciliation is not submission: the recovery interface has no
fresh-route and no economic-submit permission.

Recovery reuses the actual P06 compiler lineage saved by P23 and the P22
admission service through its public interfaces. It reimplements no accounting,
no reservation and no transport.

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Strict typed models: labelled outcome evidence, the owner-scoped case and evidence views, and the recovery result. |
| `models.py` | Owned SQLAlchemy tables on `RecoveryBase`, in the `recovery_local` schema. |
| `service.py` | `RecoveryService`: reopen, reconcile, status and owner-scoped retrieval. |

Application names describe responsibility. The ticket number is not a module
name.

## Verified-owner rule

Every `RecoveryService` call receives `verified_owner_id` from the caller's
verified identity. Saved rows bind only the verified owner; the case lookup and
every retrieval are owner-scoped. Another owner sees nothing. An unknown owner
and action pair fails closed with `RecoveryError`.

## Original action identity

Recovery never infers a new identity. The case copies the frozen references from
the saved P23 intent: action id, agent, wallet, network, operation, revision id,
policy binding and payload hash. Evidence must bind to those references exactly.
An evidence record with a foreign agent, wallet or network is rejected as
`FOREIGN_IDENTITY`. A changed operation, revision, policy binding or payload hash
is rejected as `OPERATION_MISMATCH`, `REVISION_MISMATCH`, `POLICY_MISMATCH` or
`PAYLOAD_MISMATCH`. A rejection is recorded and shown as a discrepancy; it never
reaches the P22 ledger and never releases a reservation or claim.

## Original-attempt binding

Recovery settles only an action that reached a submission-capable original
state. It requires at least one of: a saved P23 submission attempt for the exact
action, the active exclusive claim for the exact action, a submission-owned P22
decision for the exact action, or a submission-owned queue state for the exact
action. Every proof is scoped to the requested action and queue: another action's
claim on the same wallet is not proof. An action that was only admitted or queued,
with no original attempt, has nothing to reconcile. Recovery blocks it with
`NO_SUBMISSION_ATTEMPT` and changes no P22 or P23 row. A proved pre-broadcast
denial for a genuine interrupted original attempt stays available, because that
attempt leaves a saved attempt row or a submission-owned state.

Recovery convergence releases only the claim owned by the action it converges, so
a claim held by another still-unknown action on the same wallet keeps its
exclusivity.

## Controlled outcome evidence

`OutcomeEvidence` is authored local fixture evidence, not a real provider or
chain receipt. It may carry one of four controlled outcomes:

- `CONFIRMED` with the reconciled actual trade input, output and native gas.
- `REVERTED` with the reconciled actual native gas.
- `PREBROADCAST_DENIED` with no actual amounts, because a proved pre-broadcast
  denial has no effect.
- `SUBMISSION_UNKNOWN` with no actual amounts, because unknown stays unknown.

The model rejects actual amounts on the two unproved outcomes, so zero is never
invented for an unknown effect.

## Reconciliation and accounting boundaries

Recovery distinguishes the economic facts kept separate by P22:

- The provider request count, the economic attempts, the trading allowance and
  the capital/proceeds stay separate ledger rows.
- A `CONFIRMED` outcome reconciles the actual trade input, output and native gas
  and consumes the matching reservations.
- A `REVERTED` outcome consumes the actual native gas, releases the trade
  reservations and does not credit the trade.
- A `PREBROADCAST_DENIED` outcome releases the reservations with no consumption.
- A `SUBMISSION_UNKNOWN` outcome retains every applicable reservation and the
  exclusive claim.

A settlement the P22 ledger rejects as a breach is never reported as a
confirmation. Recovery maps a `BREACHED` decision to a blocked case and keeps the
claim, so unknown exposure is not released.

## Unknown, missing and unqualified evidence

A timeout, a clock advance, a restart or an absent receipt cannot prove an action
was definitely unsent. Recovery keeps the exclusive claim and the reservations
in force, exposes the actual blocking reason and shows a delayed exit with its
real reason. An unknown A-wallet action does not block unrelated B-wallet work,
because every case is scoped to its own wallet and network and the P22 wallet
lock is per wallet.

## Idempotency and crash convergence

Recovery is idempotent and crash-safe:

- Each evidence record carries a stable fingerprint of the economic outcome,
  independent of arrival time. A unique `(owner, action, fingerprint)` makes a
  re-delivered outcome a no-op that applies accounting once.
- A per-action transaction advisory lock serializes competing recoverers. The
  loser sees an accepted record and returns a duplicate result.
- The durable case records progress. A crash after the P22 reconciliation commits
  but before the P23 queue converges leaves the action settled in P22; on restart
  recovery detects the settled decision and converges the P23 queue and claim
  without a second reconciliation or a second economic call.
- On that convergence path the saved P22 terminal receipt is authoritative. The
  delivered evidence is compared against the saved receipt's actual input, output
  and gas before the queue converges. A mismatch stays a visible, blocked
  `DISCREPANCY` (`P22_RECEIPT_MISMATCH:actual_input|actual_output|actual_gas`) and
  the queue is not mutated. The owner never sees incompatible actuals for one
  action.
- The same comparison closes a settlement interleaving. A concurrent P22 service
  can commit a terminal settlement between recovery's initial decision read and
  its reconciliation call. Recovery therefore re-checks the authoritative result
  after `AdmissionService.reconcile` returns: when that result is terminal it must
  match the delivered evidence outcome and actuals, or the evidence is blocked as
  a `DISCREPANCY` before acceptance. A genuine breach is not treated as a
  mismatch; it converges to the blocked `BREACHED` state.
- A stale P23 queue after a crash therefore converges to the settled P22 state
  once, with no duplicate fees and no released unknown exposure.

## Authority boundaries

Recovery cannot grant authority and cannot clear a stop. It never calls admission,
proposal, cancellation or any fresh-route method. It settles only evidence for an
action that already exists. When current permission expires or revokes, or a stop
exists, a pending reconciliation is preserved; once the action is conclusively
settled, any future distinct action still needs a current P23 eligibility check.
Recovery is never used to resubmit a stale payload.

## Wiring and out-of-scope

There is no API/UI wiring and no shared migration in this stage. The owned tables
live in the `recovery_local` schema, created by the owned test fixture inside the
run-labelled database only. The accepted P22 `admission_local` and P23
`execution_local` schemas are reused read-mostly; the only P23 write is the
bounded `ExecutionService.converge_reconciled_outcome` convergence step under the
existing execution lease.

Live transport evidence is unqualified and remains `NOT_RUN`. The local fixture
has no real signed bytes or transaction hash, so this stage makes no WAL-Q17
resend qualification claim, implements no automatic resend, and proves no
exactly-once network guarantee. A replacement economic action is never created.
Broader WAL-Q18 additions, partial exits and valuation remain deferred.
