# Execution, evaluation and queue profile (local stage)

Owned package: `apps/api/src/edge_os_api/execution/`. This profile records the
local evaluation, exclusive queue and fixture submission domain for P23 #29. It
is the approved 2026-10-10 release portion only. It is not API/UI wiring, not a
production migration, not live operation and not a recurring service.

## Responsibility

The package evaluates one immutable compiled revision on a controlled clock and
data at a declared decision time, saves the signal/no-signal/ineligible decision
and its lineage before any intent, links one exact immutable intent to that
decision, admits it through the accepted P22 `AdmissionService`, holds one
durable exclusive claim per wallet and network, revalidates immediately before a
labelled local fixture call, and records immutable outcome evidence and status.

It reuses the actual P06 compiler and the P22 admission service through their
public interfaces. It reimplements no compiler, no accounting and no reservation.

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Strict typed models: inputs, frozen revision, decision, intent terms/plan, queue/status views, revalidation and fixture evidence. |
| `evaluator.py` | Pure evaluation of the revision with `compiler.evaluate_expression`. No database access. |
| `transport.py` | The labelled local fixture transport and its acknowledgement-loss marker. |
| `models.py` | Owned SQLAlchemy tables on `ExecutionBase`, in the `execution_local` schema. |
| `service.py` | `ExecutionService`: decide, enqueue, tick, retrieve and status. |

Application names describe responsibility. The ticket number is not a module
name.

## Verified-owner rule

Every `ExecutionService` call receives `verified_owner_id` from the caller's
verified identity. An intent payload never carries an owner. Saved rows bind only
the verified owner; retrieval is owner-scoped. Another owner sees nothing.

## Revision identity

`freeze_revision(strategy)` reuses `compiler.validate_strategy`, then freezes the
strategy's canonical content hash, its manifest hash, its market-binding hash and
its required warm-up. A malformed or unsupported revision raises the compiler's
`CompilerError` before any identity is accepted. A changed rule is a new content
identity. The frozen revision stores the canonical strategy bytes; every
`strategy` access returns a fresh parse of those bytes. A caller cannot change
the revision meaning after freezing, and the evaluator re-verifies the content
hash of the bytes it evaluates before any rule runs.

## Evaluation semantics

- The evaluator runs the revision's entry, exit and invalidation rules on the
  exact scheduled five-minute UTC positions supplied in `EvaluationInputs`.
- A flat position uses the entry rule. An open position uses the exit rule and,
  when requested, the invalidation rule. An unrequested invalidation is ignored
  for the open-position outcome, so a determinate `FALSE` exit is a `NO_SIGNAL`
  and not an `INELIGIBLE`.
- `TRUE` yields a `SIGNAL` with its exact operation. A determinate `FALSE` yields
  `NO_SIGNAL`. An `UNKNOWN` required rule yields `INELIGIBLE` with its reasons. A
  missing or future required observation is `INELIGIBLE`, never a false signal or
  a zero.
- The evaluator keeps every missing-input reason even where a Kleene sibling
  decides the value. It fills, aligns and gaps nothing, and it never executes
  generated Python.
- The saved decision binds the strategy, revision, content hash, manifest hash,
  market-binding hash, the input identity (`inputs_hash`), the full inputs, the
  per-rule states and reasons, the decision time and the creation time. The
  decision is saved before any intent is created.

## Exact intent identity and replay safety

`enqueue` builds one deterministic action identity from the decision and the
operation. The action id and intent id are functions of the decision id, so a
replay of the same decision reuses the same identity. The review hash binds the
decision, operation, position, agent/wallet/network/revision/mandate binding and
the exact amounts. Consequences:

- Replaying the same decision never creates another economic action. The P22
  admission is idempotent on the action identity and review hash.
- Replaying under changed approved meaning is refused, not silently replaced.
  The stored payload is preserved unchanged.
- A changed amount, policy or revision produces a distinct review hash and a
  distinct historical record.

`enqueue` admits the intent through `AdmissionService.admit_and_reserve` with the
caller's authored approval and holdings context. A denial saves its exact reason
and is not submitted.

## Queue, exclusive claim and priority

- One durable submission/reconciliation queue exists per agent wallet and
  network, across its positions.
- Exactly one active claim may exist per agent wallet and network. A partial
  unique index on `execution_claims` and an advisory lock enforce it, so two
  processes cannot submit one action, or two distinct competing actions
  simultaneously.
- Eligible `EXIT` actions precede unsubmitted `ENTRY` actions. Within a priority
  class the order is `(enqueued_at, queue_id)`, which is deterministic.
- An unresolved outcome in A's wallet retains A's claim and blocks A's next
  submission. B's separate wallet is independent and can proceed.
- Exit priority cannot preempt a broadcast or an unknown submission. A retained
  claim is checked before a next action is selected.
- Multiple positions and their monitoring remain represented in the queue and
  status, even though the accepted P06 subset admits one open position per
  strategy.

## Revalidation before submission

Immediately before the fixture call, the service rechecks, for the exact payload:

- the current revision content hash and revision identity;
- the policy binding, the approval state and expiry, and the submission time
  against the decision time;
- submission-time freshness: the intent is valid only before the next scheduled
  decision (a local five-minute bound), and the submission-time context snapshot
  must be current (a local five-minute bound). A context that only predates the
  old decision, or the stored `FRESH` flag, cannot prove current freshness; a
  stale context or an expired intent is denied with no transport call;
- qualified submission-time observations for the exact revision and market: the
  service re-evaluates the rules with the current inputs and requires the same
  eligible operation. A newer `NO_SIGNAL`, a changed or missing quote, or an
  unqualified observation denies with `INPUTS_CHANGED` and no transport call,
  covering changes before the next-decision boundary as well as at it;
- the pure P22 admission proposal (approval, scoped stops, quote freshness,
  asset/decimal identity and position existence);
- the saved P22 admission state, which must still be `ADMITTED`; a cancelled,
  denied, reconciled or breached action is refused;
- the durable reservation ledger and the current approval caps, so a lowered
  successor limit or a released reservation is refused; and
- the current holdings against the live reservations for the assets the action
  spends from the wallet.

The recorded revalidation identity includes the current revision hash, approval
hash, policy binding, market-binding hash, validation identity and submission
time. A failed revalidation saves the denial and blocking reason and preserves
the exact prior intent payload. No queued eligibility is reused. A denied
revalidation leaves the admitted reservations in place; it does not silently
free or alter them.

## Submission ownership and cancellation coordination

After revalidation, before any fixture call, the service makes one durable
submission-ownership transition on the exact action: it reconciles the action to
the accepted P22 `SUBMISSION_UNKNOWN` state. That state is not cancellable, blocks
a competing admission, and retains the action's reservations.

- If the transition succeeds, the action is submission-owned. A concurrent P22
  `cancel` is refused (`NOT_CANCELLABLE_AFTER_SUBMISSION`) and a competing
  admission is denied (`UNRESOLVED_PRIOR_ACTION`). The original capital is not
  reusable while the effect may be in flight.
- If a cancellation already won before the transition, the transition returns a
  non-`SUBMISSION_UNKNOWN` status and the service makes no fixture call. The
  queue records `SUBMISSION_NOT_OWNED` and the attempt is recorded definitely
  unsent.
- A proved definitely-unsent result releases the ownership and its reservations
  through `AdmissionService.reconcile` with `PREBROADCAST_DENIED`; a confirmed or
  reverted result settles from the owned state. A submission-possible result
  retains the ownership.
- `RECONCILE_MISMATCH` remains a defensive backstop for any residual interleaving.

The P23 claim is committed before this transition, so a crash between them leaves
the durable claim blocking a repeat. A crash after the transition leaves the
action submission-owned (capacity retained, cancellation and competing admission
blocked) with the claim held. No transaction is held across the fixture call and
no replacement or retry path is added.

This coordination uses one minimal addition in the leased P22 path:
`SUBMISSION_UNKNOWN` is added to the pre-broadcast clearable set so a proved
definite-unsent can release a submission-owned action. No new state, table, model
or migration is added, and existing accounting, owner isolation and default
behavior are unchanged.

## Labelled local fixture submission

`LocalFixtureTransport` is a local fixture. It is not a Kuru, Privy or RPC
transport and it never signs, broadcasts or calls a provider. Authored outcomes
are:

- `DENY`: a definitely-unsent pre-broadcast denial.
- `UNKNOWN`: a submission-possible/unknown result.
- `ACCEPT`: a confirmed swap at the planned amounts.
- `REVERT`: a confirmed revert that consumes gas.
- `lose_acknowledgement=True`: the fixture applied a possible effect and lost the
  reply; the service records it as submission-possible/unknown.

The service maps the fixture result to the accepted P22 receipt outcomes
(`PREBROADCAST_DENIED`, `SUBMISSION_UNKNOWN`, `CONFIRMED`, `REVERTED`) and
reconciles through `AdmissionService.reconcile`. A confirmed acquisition or exit
uses the fixture's actuals, or the planned amounts when the fixture reports none.
The service reads the reconciliation result and requires it to match the
transport outcome:

- A rejected settlement that P22 records as `BREACHED` is retained as queue
  state `BREACHED` with its reason. The claim is held and a next economic action
  is blocked until explicit recovery. A transport confirmation is never reported
  as a successful action.
- When P22 returns any other status that does not match the transport outcome,
  the queue records `RECONCILE_MISMATCH` with the status and reason, and the claim
  is held. This is a defensive backstop; the submission-ownership transition above
  prevents the ordinary cancellation interleaving.

## Crash and restart boundaries

- The saved decision and its inputs are persisted before any intent is written.
  The exact intent payload is prepared before admission; the admitted action is
  written before the claim and the attempt.
- The claim and an `IN_FLIGHT` submission attempt are persisted in one
  transaction before the fixture call. A crash before the call leaves them
  durable.
- The submission-ownership transition is durable. A crash before the transition
  leaves the claim blocking a repeat; a crash after the transition leaves the
  action submission-owned with its capacity retained and cancellation and
  competing admission blocked. A fresh process reconciles the unresolved original
  action before any new one.
- A fresh process that finds an active claim returns `BLOCKED_UNKNOWN` and
  creates no second attempt. No timeout, lease expiry or unacknowledged worker
  death creates a duplicate or replacement action.
- The attempt evidence distinguishes `DEFINITELY_UNSENT` from
  `SUBMISSION_POSSIBLE`. Only a terminal outcome other than submission-possible
  releases the claim; a submission-possible outcome retains it.
- Fuller original-action recovery is deferred to P24. This stage preserves safe
  no-duplicate state only.

## Status and health

`retrieve_decisions`, `retrieve_queue` and `status` are owner-scoped. The queue
view exposes the action, position, operation, state, blocking reason, enqueue
time, waiting time and a delayed-exit marker. `status` exposes the last attempt
time, last completion time, last input time, the next scheduled local work and
the current blocking reason. This is local module retrieval, not a UI. A
heartbeat or a prepared-intent consumer alone is not this proof.

## Accounting and timing boundary

The evaluation inputs, approvals, holdings and fixture outcomes are authored
local fixtures. Timing, contention and recovery delays are local observations,
not a qualified live service-level objective. No live path suitability or
end-to-end exactly-once execution is asserted. Fixture amounts and delays are
local assumptions, never qualified live thresholds.

## Boundaries

- Local fixture work only. Live execution stays closed until P20/P21 and the
  operational gates pass.
- No API route, UI, browser check or shared migration is added here.
- No signing path, provider call, wallet action, credential or policy wrapper.
- The shared `public` schema is unchanged. Owned tables live in the
  `execution_local` schema of the run-labelled test database. The P22
  `admission_local` schema stays separate.
- P05 keeps its shared-wiring lease. Shared files stay read-only.
- The cancellation/submission guard uses one bounded addition in the leased P22
  path: `SUBMISSION_UNKNOWN` is added to the pre-broadcast clearable set in
  `edge_os_api/admission/service.py`, with focused regressions under
  `apps/api/tests/admission/`. This is the only P22 source change; no other
  admission path, type, model, contract, migration or shared file changed.

## Evidence classification

Evaluation, queue and submission behavior here is local application behavior
under authored synthetic approvals, holdings and fixtures. It is not provider
enforcement, live wallet state or a real transport result. Direct SQL inspection
of saved rows is part of the evidence. See `docs/qualification/execution/`.
