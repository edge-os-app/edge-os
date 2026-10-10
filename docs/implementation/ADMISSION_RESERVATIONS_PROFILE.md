# Admission and reservations profile (local stage)

Owned package: `apps/api/src/edge_os_api/admission/`. This profile records the
local, deterministic admission and reservation domain for P22 #24. It is a
local stage. It is not API/UI wiring, not a production migration and not live
admission.

## Responsibility

The package decides whether one exactly proposed action may use an agent
wallet's finite capital and position inventory, saves the admission or denial,
and holds durable reservations. It also reconciles a saved action against a
provider-independent receipt and cancels an unsubmitted action.

The package enforces application accounting. It is not independent wallet
enforcement. It does not read, sign for or restrict a real wallet.

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Strict typed models: amounts, identity binding, intent, approval snapshot, holdings snapshot, receipt, results. |
| `accounting.py` | Pure admission decisions and reservation planning. No database access. |
| `models.py` | Owned SQLAlchemy tables on `AdmissionBase`, in the `admission_local` schema. |
| `service.py` | `AdmissionService`: atomic reserve, retrieval, cancel and reconcile. |

Application names describe responsibility. The ticket number is not a module name.

## Verified-owner rule

`AdmissionService` always receives `verified_owner_id` from the caller's
verified identity. An `ActionIntent` has no owner field and rejects an extra
`owner_id` at construction. Saved rows bind only the verified owner. Retrieval
is owner-scoped; another owner's identity sees nothing.

## Amounts

An amount is `asset_id`, canonical unsigned base-10 `raw` string, and
`decimals`. Amounts with different `asset_id` values are never added. Native
MON gas has its own asset and budget. Boolean, float, negative and
leading-zero raw values are rejected. The raw value is bounded to 78 digits
(the owned ledger storage bound). Decimals and asset identity must agree across
the intent, the approval caps and the reconciled holdings before reserving or
settling.

## Accounting rules

- The ledger key is `(owner, agent, wallet, network, asset)`. Different wallets
  of one owner keep separate allowances and reservations.
- For each key the ledger keeps `approved` (from the caller-supplied approval
  snapshot) and `consumed`.
- `remaining = approved - consumed - reserved`. `reserved` is the sum of live
  `RESERVED` reservation rows. `consumed + reserved <= approved` is enforced for
  every transition, including reconciliation actuals.
- A position holds attributed inventory and weighted-average cost basis. An
  action binds to one position. The durable position is authoritative; a
  conflicting or stale caller snapshot is denied.
- Attempts are separate. Every action reserves one attempt atom against a
  per-wallet attempt budget. Confirmed and reverted actions consume it; a proved
  pre-broadcast denial releases it; an unknown outcome retains it.
- Sell coverage is derived from attributed inventory plus pending acquisition
  reservations. An acquisition must fit the remaining finite sell ceiling; its
  coverage is not released on confirmation.
- A scoped stop, a required-control qualification and the adopted allocation are
  enforced from the authored approval. Missing or unknown controls fail closed.
- Approved amounts always come from the authored approval snapshot. The service
  invents no threshold. The exact approval identity is bound to each allowance;
  a changed-content reuse is denied, while an explicit successor may raise the
  cap without erasing commitments.
- Reconciled holdings must cover the asset the action actually spends (buy input
  or sell input) and gas. A large wallet balance never enlarges authority.

## Reservation plan by operation

- `ENTRY` / `ADDITION`: reserve quote buy input, base inventory attribution,
  entry gas plus the intended-exit gas, and two attempt atoms (entry and its
  exit). Create the position at inventory zero.
- On confirmation, the acquisition consumes only its actual entry gas and one
  attempt. The retained exit gas is created as a durable per-position hold before
  the entry gas is charged, so the charge counts the retained coverage and an
  over-cap actual entry fails closed with a breach.
- `EXIT`: draw the exit gas and one attempt from the position exit hold. Any
  shortfall is funded from the wallet's approved gas and attempt budget, so a
  partial exit never strands the remaining inventory. Reserve no new gas beyond
  the exit's own need. Require a known exit valuation mark and the full durable
  quote binding; a missing or mismatched control denies admission.
- A competing acquisition cannot take gas or attempts promised to an existing
  position's exit.
- Every verified actual gas effect is accounted, including an exit with zero
  planned exit gas (charged directly and failing closed when over cap).
- The internal exit-hold action ids use a reserved `exit-hold:` namespace; a
  caller action id in that namespace is denied, and reservations are matched to
  the action's own operation so a hold is never consumed under another action.

## Atomicity

`admit_and_reserve`, `cancel` and `reconcile` serialize on the same per-wallet
PostgreSQL advisory transaction lock, in one order. A reconcile also locks the
decision row and its reservations and revalidates the terminal state under the
lock, so a duplicate receipt cannot settle an action twice.

1. Admission returns the saved decision when the same action identity and review
   hash already exist (idempotent original identity). A changed review hash for
   the same action identity raises `StaleInput` (no silent replacement).
2. Under the lock it locks the allowance rows and the durable position, computes
   reserved and coverage sums, and checks coverage. Only then does it write
   reservations and the decision.

Two separate sessions cannot reserve the same funds or inventory. Unique
constraints on the reservation atom and on `(owner, action_id)` are a backstop.

## Fail-closed denials

A denial is saved with its reason. Reasons include: inactive or expired
approval, policy-binding mismatch, cross-wallet binding, unsupported action,
stale quote, missing or unqualified exit valuation, scoped stop (new entries or
halt-all), unqualified exit capacity or cost model, allocation exceeded, decimal
or asset drift, unexplained external holdings, existing, missing, mismatched or
stale position, allowance, sell-capacity, allocation, inventory or holdings
shortfall, attempt-budget exhaustion, approval-content reuse, renewal that would
erase commitments, and an unresolved prior action in the same wallet and network.

## Reconciliation

- `CONFIRMED`: consumes the reconciled input and one attempt. An entry or
  addition consumes the quote input and attributes inventory; the sell-capacity
  reservation is released because attributed inventory now backs it. An exit
  consumes base input and reduces position inventory.
- `REVERTED`: releases trading input, consumes actual gas and one attempt.
- `SUBMISSION_UNKNOWN`: keeps every reservation and blocks a second economic
  action for the same wallet and network until reconciled.
- `PREBROADCAST_DENIED`: consumes neither an attempt nor trading input; releases
  reservations.
- `CANCELLED`: allowed only before submission. Releases reservations. Cannot
  undo a broadcast transaction.

A terminal outcome cannot be replaced. A later receipt for a confirmed,
reverted, denied or cancelled action returns `RECONCILIATION_TERMINAL_STATE` and
changes nothing.

A receipt must match the saved action identity: action id, strategy revision,
mandate, agent, wallet and network. A mismatch fails closed with
`ACTION_IDENTITY_MISMATCH`.

Confirmed acquisitions and exits require reconciled actual input and output.
Missing or mismatched actuals fail closed rather than substituting the planned
values. At settlement the reconciled actual is authoritative and must stay
within the adopted sell coverage and allocation; a favorable over-fill or an
over-allocation fails closed and rolls back. An acquisition attributes the
reconciled output and adds the reconciled input to the position cost basis. An
exit removes the weighted-average basis for the exited quantity and records
realized consideration. Unknown gas, input or output stays unknown.

Consumption is capped. A reconciled actual that would push `consumed` past
`approved`, or invalidate another live reservation, fails closed with
`CONSUMED_EXCEEDS_APPROVED`; the transaction rolls back and the decision keeps
its prior state.

Only demonstrated unused reservations are released. Consumed allowance stays
consumed.

## Receipts, breach state and identity bindings

- Every verified receipt is persisted with its action, revision, position,
  operation and actual asset effects, so a fresh session can read the original
  evidence and planned reservations stay distinguishable from reconciled
  consumption.
- A verified receipt that cannot fit the adopted bounds (sell coverage,
  allocation, cap, or another reserved exit) fails closed and records a durable
  breach. The breach transition commits under the same per-wallet advisory lock
  as the settlement, so no admission can slip in between the rollback and the
  breach record. The decision becomes `BREACHED`, and new affected admissions for
  that wallet and network are blocked until reconciled. A contradictory
  pre-broadcast denial cannot clear a recorded confirmed or reverted breach; it
  is refused with `CONTRADICTORY_RECOVERY`.
- The durable position quote asset and decimals are validated at admission for
  additions and exits, before any reservation, so an altered quote binding is a
  saved denial rather than a settlement-time failure.
- A receipt must match the saved action identity (action id, strategy revision,
  mandate, agent, wallet, network). A mismatch is denied without mutation.
- The adopted approval is bound by its full content hash; a changed budget,
  stop, allocation or qualification under the same approval identity is denied.
- Each position records its adopted quote asset and decimals. Exit marks,
  expected quotes, and reconciled outputs must match that identity; unlike raw
  cost amounts are never aggregated.
- An acquisition reserves its intended-exit gas and attempt capacity before the
  exposure exists. Attempts, trading input and gas stay separate.

## Boundaries

- Local fixture work only. Live admission stays closed until P21 and the
  operational gates pass.
- No API route, UI, browser check or shared migration is added here.
- No signing path, provider call, wallet action or policy wrapper.
- The shared `public` schema is unchanged. Owned tables live in the
  `admission_local` schema of the run-labelled test database.
- P05 keeps its shared-wiring lease. Shared files stay read-only.

## Evidence classification

Admission and reservation behavior here is application accounting under
authored synthetic approvals and holdings. It is not provider enforcement and
not live wallet inventory. Direct SQL inspection of saved rows is part of the
evidence. See `docs/qualification/admission/`.
