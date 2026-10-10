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

- Full suite: 422 passed (377 existing + 45 admission), ~84 s.
- Admission suite: 45 passed.
- P15 and P02 contract checks: PASS.
- `git diff --check`: clean.

## Not covered

Live admission, API routes, UI, browser checks, production migration, provider
enforcement and any real wallet, signing or provider action. These remain
unresolved and are not proven by this recipe.
