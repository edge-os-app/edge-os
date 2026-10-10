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
leading-zero raw values are rejected.

## Accounting rules

- The ledger key is `(owner, agent, wallet, network, asset)`. Different wallets
  of one owner keep separate allowances and reservations.
- For each key the ledger keeps `approved` (from the caller-supplied approval
  snapshot) and `consumed`.
- `remaining = approved - consumed - reserved`. `reserved` is the sum of live
  `RESERVED` reservation rows. `consumed + reserved <= approved` is enforced.
- A position holds attributed inventory. An action binds to one position.
- Attempts are separate. Every action reserves one attempt atom against a
  per-wallet attempt budget. Confirmed and reverted actions consume it; a proved
  pre-broadcast denial releases it; an unknown outcome retains it.
- Approved amounts always come from the authored approval snapshot. The service
  invents no threshold. A large wallet balance never enlarges authority.
- Reconciled holdings must cover the asset the action actually spends (buy input
  or sell input) and gas. A base sell-capacity reservation is a permission
  against the allowance, not a spend of held base.

## Reservation plan by operation

- `ENTRY`: reserve quote buy input, base sell capacity for the resulting
  inventory, base inventory attribution, one per-action gas amount, and one
  attempt. Create the position at inventory zero.
- `ADDITION`: same, for an existing position.
- `EXIT`: reserve base sell input, base inventory attribution, gas and one
  attempt. Require a known exit valuation mark; a missing or unknown mark denies
  admission.

## Atomicity

`admit_and_reserve` runs in one transaction:

1. It returns the saved decision when the same action identity and review hash
   already exist (idempotent original identity). A changed review hash for the
   same action identity raises `StaleInput` (no silent replacement).
2. It takes a per-wallet PostgreSQL advisory transaction lock keyed on owner,
   agent, wallet and network.
3. Under the lock it locks the allowance rows, computes reserved sums, and
   checks coverage. Only then does it write reservations and the decision.

Two separate sessions cannot reserve the same funds or inventory. Unique
constraints on the reservation atom and on `(owner, action_id)` are a backstop.

## Fail-closed denials

A denial is saved with its reason. Reasons include: inactive or expired
approval, policy-binding mismatch, cross-wallet binding, unsupported action,
stale quote, missing exit valuation, unexplained external holdings, existing or
missing position, allowance or inventory shortfall, holdings shortfall, and an
unresolved prior action in the same wallet and network.

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

Consumption is capped. A reconciled actual that would push `consumed` past
`approved` fails closed with `CONSUMED_EXCEEDS_APPROVED`; the transaction rolls
back and the decision keeps its prior state. A supplied reconciled actual
quantity must match the reserved input; a mismatch fails closed.

Only demonstrated unused reservations are released. Consumed allowance stays
consumed.

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
