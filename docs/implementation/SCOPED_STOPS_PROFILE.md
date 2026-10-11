# Scoped stops profile (local stage)

Owned package: `apps/api/src/edge_os_api/stops/`. This profile records the local
durable scoped-stop domain for P25 #35. It is the approved 2026-10-10 release
portion only. It is not API/UI wiring, not a production migration, not live
operation and not signer removal.

## Responsibility

The package records owner-authored scoped stops durably and exposes a read-only
enforcement lookup. The accepted P22 admission path and the accepted P23
execution path consult that lookup so a saved stop denies the affected unsent
work after a restart, and so a queued action cannot bypass a newly recorded stop.
It also preserves pending reconciliation and residual exposure: a stop never
labels an uncertain or in-flight action as definitely unsent and never claims
that all holdings are closed.

It reuses the actual P22 `AdmissionService` and P23 `ExecutionService` through
their public interfaces and one bounded leased helper. It reimplements no
accounting, no reservation and no recovery.

## Modes and scope

Two modes come from the accepted builder decision Q24 A:

- `STOP_NEW_ENTRIES` denies scoped entries and additions. It allows only
  existing, explicitly preapproved exit rules under current authority and all
  ordinary inventory, capacity, freshness and risk checks. It requests no
  immediate sale.
- `HALT_ALL_SWAPS` denies every scoped swap, including exits.

Scopes are `POSITION` and `AGENT_WALLET_NETWORK`. A position stop covers its
exact position, including an entry that intends that position before it exists. A
wallet-network stop covers every position in that agent's wallet and leaves other
agents and other wallets unchanged. A wider deployment or all-agent scope needs
its real adopted mapping and every affected wallet; it is refused explicitly
rather than widened into an implicit wallet-global action.

The `trigger` field records the adopted trigger (`USER`, `TRIAL`,
`POSITION_LOSS`, `WALLET_LOSS`). It is preserved verbatim. No loss, trial or
threshold economy is computed from it, and no stop-clear, resume or renewal
action exists in this stage.

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Strict typed request and view models, the accepted mode denial rule and the stable reason tokens. |
| `models.py` | The owned `scoped_stops` table on `StopBase`, in the `stops_local` schema. |
| `service.py` | `StopService`: durable request, owner-scoped retrieval and the read-only `denial_reasons` lookup. |

Application names describe responsibility. The ticket number is not a module
name.

## Verified-owner rule

Every `StopService` call receives `verified_owner_id` from the caller's verified
identity. A stop request carries no owner. Saved rows bind only the verified
owner; retrieval is owner-scoped. A foreign owner reads nothing and changes
nothing.

## Durability and idempotency

One durable row exists per owner, agent, wallet, network, scope, target and mode.
An identical repeated request is idempotent: the same record is returned and no
second row is written. Different modes, scopes or targets accumulate, so the
table is the durable stop history. Stop records survive a fresh engine and a true
process restart, and they are never cleared.

## Enforcement points

The enforcement read takes a caller session, runs inside the caller's
transaction, and reads only the persisted rows. It never writes and never
consults a caller-supplied omission or the old approval snapshot.

- `AdmissionService.admit_and_reserve`, under the per-wallet advisory lock, reads
  the persisted stops before any ledgers or denial reasons. A denying stop saves a
  `DENIED` decision with the stable reason and reserves nothing. The immutable
  approval snapshot is never rewritten.
- `AdmissionService.acquire_submission`, under the same lock, reads the persisted
  stops before it takes submission ownership. If a stop committed first, it
  returns `STOPPED_SCOPE`, takes no ownership and moves no state. If ownership
  committed first, the action is already submission-owned and a later stop never
  undoes it.
- `ExecutionService` revalidation reads the persisted stops inside the submission
  transaction, so a queued action cannot bypass a newly recorded stop by replay,
  restart, stale input or another process. A denied revalidation makes no
  transport call and leaves the admitted reservations in place.

The stable reasons reuse the accepted vocabulary: `STOPPED_NEW_ENTRIES` and
`STOPPED_HALT_ALL_SWAPS`.

## Atomic ordering between a committed stop and submission ownership

`StopService.request_stop` takes the same per-wallet advisory lock the accepted
P22 admission and submission-ownership transitions use. That single lock defines
the atomic ordering for one owner, agent, wallet and network:

- If the stop commits first, the submission-ownership transition reads the stop
  and refuses ownership. The caller makes zero transport calls.
- If ownership commits first, the action is already submission-owned or
  broadcast-possible. The stop does not undo it. The action stays visible, keeps
  its claim and reconciles its original durable reference.
- A stop never relabels a claimed or uncertain action as definitely unsent, and
  it never removes a reservation. Pending reconciliation, residual inventory,
  delayed exits and consumed allowance are preserved.

## Preserved behavior and narrower data

Recovery conformance, breach preservation, unknown-outcome retention, owner
isolation, reservation accounting, the exclusive claim, quote and freshness
checks and the immutable approval hash are unchanged. A stop does not clear an
adopted trial or loss stop, an expired mandate, an exhausted limit or a
revocation. Recovery, a funding top-up, a renewal-like current permission or a
successor approval with higher caps cannot clear a durable stop. No new stop
economics are assigned.

## Boundaries

- Local fixture work only. No API route, UI, browser check or shared migration is
  added here.
- No signing path, provider call, wallet action, credential or policy wrapper. A
  local stop is not proof of Privy revocation and is not liquidation.
- The shared `public` schema is unchanged. Owned tables live in the `stops_local`
  schema of the run-labelled test database. The P22 `admission_local`, P23
  `execution_local` and P24 `recovery_local` schemas stay separate.
- The bounded shared lease adds durable-stop reads and the submission-ownership
  guard in `edge_os_api/admission/service.py` and the revalidation read in
  `edge_os_api/execution/service.py`. The `acquire_wallet_lock` public helper and
  the `StopReader` protocol are the only new admission symbols. No other admission
  or execution path, type, model, contract, migration or shared file changed.
- Shared wiring stays with its owners. `AdmissionService` and `ExecutionService`
  enforce durable stops when they are constructed with a `StopService`
  collaborator. Mounting the routes, the production migration and the UI remain
  P17 and P18 work.

## Evidence classification

Stop records and enforcement here are local application behavior under authored
synthetic approvals, holdings and fixtures. They are not provider enforcement,
live wallet state, a real transport result or an exactly-once network guarantee.
Direct SQL inspection of saved rows is part of the evidence. See
`docs/qualification/scoped-stops/`.
