# Admission local verification recipe

P22 local stage. Run from the assigned worktree root. This recipe proves the
local admission and reservation domain. It does not prove live admission, API
wiring, UI, migration or provider enforcement.

## Preflight

```bash
cd apps/api && uv sync --frozen
```

Requires Python 3.14 and a working Docker engine for the run-labelled
PostgreSQL 18 container.

## Checks

```bash
# Offline contracts (from the worktree root)
python3 -B docs/contracts/p15/check_contract.py
python3 -B docs/contracts/p02/check_contract.py

# Focused admission suite
(cd apps/api && uv run --frozen pytest tests/admission)

# Full suite
(cd apps/api && uv run --frozen pytest)

# Compile check (the supported type/compile tool in this repository)
(cd apps/api && uv run --frozen python -m compileall -q src/edge_os_api/admission tests/admission)

# Whitespace and conflict-marker check
git diff --check
```

## What the admission suite covers

- Typed amount and intent validation (canonical amounts; no owner in a payload;
  supported networks; quote asset consistency).
- Admitted entry with saved decision and four reservation atoms; direct SQL
  cross-check of the rows.
- Denials saved with reasons: inactive or expired approval, policy mismatch,
  cross-wallet binding, unsupported action, stale quote, missing exit
  valuation, unexplained external holdings, existing or missing position.
- Allowance exhaustion and the rule that a deposit does not enlarge authority.
- Idempotent identity (same action and review hash returns the same decision)
  and stale input (changed review hash for the same action raises).
- Owner-scoped retrieval; balances recompute `remaining = approved - consumed -
  reserved`.
- Cancel releases reservations; only pre-submission actions cancel.
- Reconcile: confirmed entry consumes quote and attributes inventory; confirmed
  exit consumes base and reduces inventory; addition grows the position; revert
  releases input and consumes gas; pre-broadcast denial consumes neither;
  submission-unknown retains reservations and blocks a second economic action.
- Contention: two separate sessions cannot double-reserve the same capital or
  inventory.
- Attempt budget and effects: one attempt per action; confirmed and reverted
  consume it, a proved pre-broadcast denial releases it.
- Capacity isolation: reservations and balances are scoped to the owner's exact
  wallet; another wallet of the same owner is unaffected.
- Terminal reconcile guard: a late receipt cannot replace a confirmed, reverted,
  denied or cancelled outcome.
- Consumption caps: a reconciled actual that would exceed the approved cap fails
  closed with no mutation; a mismatched reconciled quantity fails closed.
- Durability: committed records survive a fresh engine (process restart); a
  rolled-back transaction leaves no partial rows; owned tables never touch the
  migrated `public` schema.

## Isolated resources

The suite reuses the shared `tests/conftest.py` run-labelled PostgreSQL 18
instance (labels `edge-os.test=1`, `edge-os.test.run=<run_id>`). The owned
fixture creates the `admission_local` schema in that run-labelled database,
creates the owned tables there, and drops the schema at the end. The migrated
`public` schema is untouched. No production migration is released.

If a run is killed, list and remove only its own labelled resources:

```bash
python3 scripts/p03/harness.py orphans
python3 scripts/p03/harness.py remove-orphan <run_id>
```

## Last recorded run

- Full suite: 464 passed (377 existing + 87 admission), ~95 s.
- Admission suite: 87 passed.
- P15 and P02 contract checks: PASS.
- `git diff --check`: clean.

## Gate-repair coverage (verdict 1/3)

Additional focused regressions for the first gate review: concurrent
reconciliation settles once under two sessions; a receipt with a mismatched
action identity is denied without mutation; a cross-wallet or stale position
snapshot is denied; changed-approval-content reuse is denied while an adopted
successor cap applies; reconciled actual gas respects other outstanding
reservations; large-integer accounting stays exact and decimal drift is denied;
an acquisition cannot exceed the remaining sell ceiling; a favorable reconciled
over-fill or over-allocation fails closed and rolls back; scoped stops and
unqualified required controls fail closed; reconcile and admission serialize on
the wallet lock; and confirmed acquisitions/exits require reconciled actuals and
update weighted cost basis and realized result.

## Gate-repair coverage (verdict 2/3, candidate 8f07e22 -> d671884)

Additional regressions for the second gate review: an addition cannot target
another wallet's position; an exit output with the wrong quote asset or decimals
fails closed; a changed attempt budget or other approval term under the same
approval identity is denied; an exit actual cannot consume inventory promised to
another reserved exit; an acquisition is denied when its intended exit cannot be
covered (attempt/gas); a breach records durable evidence and blocks new work; an
entry is denied without cost-model qualification; a concurrent identical
admission returns the same saved decision; and each verified receipt is
persisted and retrievable.

## Controller continuation coverage (Q1-Q4)

Additional regressions for the focused continuation: entry-confirm-exit at the
minimal attempt/gas budget (the exit uses the retained hold); a competing
acquisition cannot take gas promised to an existing position's exit; the breach
transition keeps the wallet lock (a competing admission is denied); a
pre-broadcast denial cannot clear a recorded breach; and an altered quote binding
for an existing position is denied at admission with the inventory and basis
unchanged.

## Not covered

Live admission, API routes, UI, browser checks, production migration, provider
enforcement and any real wallet, signing or provider action. These remain
unresolved and are not proven by this recipe.
