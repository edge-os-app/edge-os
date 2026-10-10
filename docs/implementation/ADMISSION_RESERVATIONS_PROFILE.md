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

- For each `(owner, agent, wallet, network, asset)` the ledger keeps `approved`
  (from the caller-supplied approval snapshot) and `consumed`.
- `remaining = approved - consumed - reserved`. `reserved` is the sum of live
  `RESERVED` reservation rows. `consumed + reserved <= approved` is enforced.
- A position holds attributed inventory. An action binds to one position.
- Approved amounts always come from the authored approval snapshot. The service
  invents no threshold. A large wallet balance never enlarges authority.

## Reservation plan by operation

- `ENTRY`: reserve quote buy input, base sell capacity for the resulting
  inventory, base inventory attribution, and one per-action gas amount. Create
  the position at inventory zero.
- `ADDITION`: same, for an existing position.
- `EXIT`: reserve base sell input, base inventory attribution and gas. Require a
  known exit valuation mark; a missing or unknown mark denies admission.

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

- `CONFIRMED`: consumes the reconciled input. An entry or addition consumes the
  quote input and attributes inventory; the sell-capacity reservation is
  released because attributed inventory now backs it. An exit consumes base
  input and reduces position inventory.
- `REVERTED`: releases trading input and consumes actual gas.
- `SUBMISSION_UNKNOWN`: keeps every reservation and blocks a second economic
  action for the same wallet and network until reconciled.
- `PREBROADCAST_DENIED`: consumes neither an attempt nor trading input; releases
  reservations.
- `CANCELLED`: allowed only before submission. Releases reservations. Cannot
  undo a broadcast transaction.

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
