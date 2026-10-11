# Action recovery local verification recipe

P24 local stage. Run from the assigned worktree root. This recipe proves the
local original-action recovery domain: durable reopen, controlled reconciliation,
idempotency and crash convergence. It does not prove live execution, API wiring,
UI, migration, a real transport, a real provider or an exactly-once network
guarantee.

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
python3 -B docs/contracts/p06/check_contract.py

# Focused suite
(cd apps/api && uv run --frozen pytest tests/recovery tests/execution tests/admission)

# Full suite
(cd apps/api && uv run --frozen pytest)

# Compile check (the supported type/compile tool in this repository)
(cd apps/api && uv run --frozen python -m compileall -q \
  src/edge_os_api/recovery src/edge_os_api/execution tests/recovery)

# Whitespace and conflict-marker check against the accepted base
git diff --check 545434d06c3cdae9d1deff78d77ff28147719fdd..HEAD
```

## What the recovery suite covers

- Durable reopen: after a fresh engine and a fresh service over the same
  run-labelled database, `status` returns the original action, binding, revision
  and payload hash with the saved `SUBMITTED_UNKNOWN` state and the retained
  exclusive claim. A status read changes no queue row and releases no claim.
- Confirmed settlement: `CONFIRMED` evidence reconciles into P22 once, consumes
  the actual quote capital and native gas, converges the queue to
  `SUBMITTED_CONFIRMED` and releases the claim. Re-delivering the same evidence
  is a duplicate no-op that consumes nothing again.
- Proved pre-broadcast denial: `PREBROADCAST_DENIED` evidence releases the
  reservations with no consumption, sets the P22 decision to `DENIED`, converges
  the queue to `DENIED_UNSENT` and releases the claim.
- Unknown evidence: `SUBMISSION_UNKNOWN` evidence sets the case to `UNKNOWN`,
  keeps the decision at `SUBMISSION_UNKNOWN`, converges the queue to
  `SUBMITTED_UNKNOWN` and retains both the reservations and the exclusive claim.
- Foreign and altered evidence: a foreign wallet binding is rejected as
  `FOREIGN_IDENTITY`; a changed payload hash is rejected as `PAYLOAD_MISMATCH`.
  Both stay a visible `DISCREPANCY`, never reach the P22 ledger and release
  nothing.
- Contradictory terminal evidence: a new outcome that conflicts with a settled
  P22 decision is blocked as `P22_SETTLED_MISMATCH`, not reported as a
  confirmation.
- Crash convergence: after a P22 reconciliation commits but the P23 queue is
  stale, a re-delivered evidence record converges the queue without a second
  reconciliation and without duplicate consumption.
- Competing recoverers: two concurrent recoverers on one action apply the
  accounting once; exactly one is applied and one is a duplicate.
- Wallet isolation: an unknown A-wallet action does not block a B-wallet status
  or recovery.
- Authority: the recovery service exposes no submission, routing, admission or
  cancellation method; an unknown owner and action pair fails closed.

## Isolated resources

The suite reuses the shared `tests/conftest.py` run-labelled PostgreSQL 18
instance (labels `edge-os.test=1`, `edge-os.test.run=<run_id>`). The owned
recovery fixture creates the `recovery_local` schema plus the accepted
`admission_local` and P23 `execution_local` schemas in that run-labelled
database, creates the owned tables there, and drops exactly those schemas at the
end. The migrated `public` schema is untouched. No production migration is
released.

If a run is killed, list and remove only its own labelled resources:

```bash
python3 scripts/p03/harness.py orphans
python3 scripts/p03/harness.py remove-orphan <run_id>
```

## Last recorded run

- Full suite: 566 passed, ~95 s, 2 known warnings.
- Recovery suite: 13 passed. Execution suite: 46 passed. Admission suite: 100 passed.
- P15, P02 and P06 contract scripts: PASS.
- `compileall` on the owned recovery and leased execution source/tests: PASS.
- `git diff --check` against the accepted base `545434d0`: clean.

## Not covered

Live execution, API routes, UI, browser checks, production migration, real
transport, provider enforcement, wallet signing, real signed bytes or a real
transaction hash, automatic resend, an exactly-once network guarantee and any
real capital action. Real transport evidence is `NOT_RUN`. Timing and contention
numbers here are local observations, not a qualified live service-level
objective.
