# Execution local verification recipe

P23 local stage. Run from the assigned worktree root. This recipe proves the
local evaluation, exclusive queue, revalidation and fixture-submission domain.
It does not prove live execution, API wiring, UI, migration, a real transport or
provider enforcement.

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
(cd apps/api && uv run --frozen pytest tests/execution tests/admission \
  tests/test_strategy_compiler.py tests/test_strategy_compilation_api.py)

# Full suite
(cd apps/api && uv run --frozen pytest)

# Compile check (the supported type/compile tool in this repository)
(cd apps/api && uv run --frozen python -m compileall -q src/edge_os_api/execution tests/execution)

# Whitespace and conflict-marker check against the accepted base
git diff --check 8d38d691e7be3d0bfd12f3e16cfdc13564c4c652..HEAD
```

## What the execution suite covers

- Evaluation of the actual compiled revision: a `SIGNAL` decision with its exact
  operation, a determinate `FALSE` as `NO_SIGNAL`, and a missing or unknown
  required observation as `INELIGIBLE` (never a false signal or a zero). Future
  observations, invalidation-triggered exits and a false exit with an unrequested
  invalidation are covered.
- Decision lineage: saved strategy, revision, content hash, manifest hash,
  market-binding hash, input identity, full inputs, per-rule states and reasons,
  decision and creation timestamps; owner-scoped retrieval.
- Immutable revision: a returned strategy mapping cannot change the frozen
  meaning or its declared content hash after freezing.
- Exact intent linkage: an admitted intent links to its saved decision, and the
  P22 admission decision is saved. A replay of the same decision reuses the same
  action identity and creates no second economic action. A replay under changed
  meaning is refused with the stored payload preserved.
- Exclusive claim and priority: an eligible exit is selected before an
  unsubmitted entry with a deterministic tie order; an unknown outcome in A's
  wallet blocks only A work and B proceeds; two concurrent ticks submit one
  action once.
- Revalidation: an expired or revoked approval, a changed policy binding, a
  changed revision, a scoped stop, an expired intent, a stale submission
  context, empty holdings, a lowered successor limit and a cancelled saved action
  each deny submission with no transport call, record the reason and preserve the
  prior intent payload.
- Fixture submission: a confirmed swap reconciles into P22 and releases the
  claim; a definitely-unsent denial consumes no attempt and releases the claim;
  an unknown outcome retains the claim and blocks status; a lost acknowledgement
  is recorded as submission-possible; a persisted in-flight attempt after a
  simulated crash blocks a duplicate; a settlement breach is retained as
  `BREACHED` and blocks a next action; an external cancellation that lands after
  the claim commit is retained as `RECONCILE_MISMATCH` (never reported as a
  confirmation) and blocks the next action.
- Status: last attempt/completion/input time, next scheduled local work, the
  queue with waiting time, delayed-exit marker and blocking reason.
- Durability and isolation: records survive a fresh engine; the `execution_local`
  tables never touch the migrated `public` schema or the `admission_local`
  schema.

## Isolated resources

The suite reuses the shared `tests/conftest.py` run-labelled PostgreSQL 18
instance (labels `edge-os.test=1`, `edge-os.test.run=<run_id>`). The owned
fixture creates the `execution_local` schema (and the accepted `admission_local`
schema) in that run-labelled database, creates the owned tables there, and drops
both schemas at the end. The migrated `public` schema is untouched. No production
migration is released.

If a run is killed, list and remove only its own labelled resources:

```bash
python3 scripts/p03/harness.py orphans
python3 scripts/p03/harness.py remove-orphan <run_id>
```

## Last recorded run

- Full suite: 504 passed (472 existing + 32 execution), ~75 s, 2 known warnings.
- Execution suite: 32 passed.
- Focused suite (execution + admission + compiler tests): 178 passed.
- P15, P02 and P06 contract scripts: PASS.
- `compileall` on owned source/tests: PASS.
- `git diff --check` against the base: clean.
- Gate-owned reproduction of the repaired candidate (separate PostgreSQL 18.6,
  local fixture transport): the verdict-1/3 findings still deny/block, the
  verdict-2/3 findings now deny/block (an aged intent and a stale context deny
  with zero transport calls; an external cancellation after the claim commit is
  retained as `RECONCILE_MISMATCH` with the claim held), and all positive
  controls still pass.

## Not covered

Live execution, API routes, UI, browser checks, production migration, real
transport, provider enforcement, wallet signing and any real capital action.
These remain unresolved and are not proven by this recipe. Timing and contention
numbers here are local observations, not a qualified live service-level
objective.
