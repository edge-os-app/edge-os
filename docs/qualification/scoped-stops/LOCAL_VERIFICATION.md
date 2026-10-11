# Scoped stops local verification recipe

P25 local stage. Run from the assigned worktree root. This recipe proves the
local durable scoped-stop domain: owner-scoped records, real admission and
submission enforcement, atomic stop/ownership ordering, retention of pending work
and monitoring, and survival across a true process restart. It does not prove
live execution, API wiring, UI, migration, a real transport, a real provider,
signer removal or an exactly-once network guarantee.

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

# Focused owned suite
(cd apps/api && uv run --frozen pytest tests/stops)

# Affected accepted suites
(cd apps/api && uv run --frozen pytest tests/admission tests/execution tests/recovery \
  tests/test_strategy_compiler.py tests/test_ownership.py tests/test_account_views.py)

# Full suite
(cd apps/api && uv run --frozen pytest)

# Compile check (the supported type/compile tool in this repository)
(cd apps/api && uv run --frozen python -m compileall -q \
  src/edge_os_api/stops src/edge_os_api/admission src/edge_os_api/execution src/edge_os_api/recovery tests/stops)

# Whitespace and conflict-marker check against the accepted base
git diff --check c217ab7a1f425130182a58e1f68cf9c5a1daa103..HEAD
```

## What the scoped-stop suite covers

- Owner-scoped records: `request_stop` saves a durable row binding the verified
  owner, the exact agent, wallet and network, the scope, the mode, the trigger and
  the exact position. Another owner reads nothing; direct SQL on
  `stops_local.scoped_stops` confirms the saved row.
- Idempotent history with preserved triggers: an identical repeated request
  returns the same record and writes no second row; a different trigger, mode or
  target is a distinct adopted stop and accumulates as durable history. A `USER`
  stop followed by a `TRIAL` stop on the same wallet, position and mode yields two
  records with both triggers visible in owner readback and in direct SQL.
- Wallet isolation: an agent-wallet-network stop on wallet A leaves wallet B and
  other agents unchanged. A position-filtered lookup needs the exact agent, wallet
  and network scope and returns only that wallet's position stop plus that wallet's
  covering wallet stops; a stop on wallet B is never reported as covering A's
  position. A position filter without the exact scope is refused. Broad owner
  history retrieval still returns both wallets.
- Scope refusal: a `POSITION` stop without a position, an `AGENT_WALLET_NETWORK`
  stop that names a position, a wider deployment scope and an unknown trigger are
  all refused explicitly.
- Admission denial: `admit_and_reserve` denies a scoped entry and a scoped
  addition with `STOPPED_NEW_ENTRIES`, and a scoped exit with
  `STOPPED_HALT_ALL_SWAPS`. The saved decision is `DENIED` with the reason, and
  the immutable approval snapshot is byte-identical and still carries no authored
  stop.
- Entry before a position: an agent-wallet stop denies an entry for a position
  that does not exist yet.
- Owner isolation at admission: a stop recorded by another owner denies nothing.
- Exit continuation: with a `STOP_NEW_ENTRIES` stop recorded after a position is
  opened, a real exit admission for that position is `ADMITTED` under the ordinary
  inventory, capacity, freshness and valuation checks.
- Authority precedence: an expired or revoked authority still denies the exit
  under either mode (`APPROVAL_STATE:REVOKED`, `APPROVAL_EXPIRED`).
- Queued action cannot bypass: an action already admitted and queued, then stopped,
  is denied at submission revalidation with a `STOPPED_NEW_ENTRIES` reason, makes
  zero transport calls, records no submission attempt and leaves its reservations
  in place.
- Submission-ownership guard: `acquire_submission` returns `STOPPED_SCOPE`,
  takes no ownership and leaves the action `ADMITTED` when a stop committed first.
- Ordering is atomic: a barrier runs one stop and one submission concurrently for
  several fresh owners. In every run the stop is durable and either it won before
  submission eligibility (zero transport calls) or the action was already
  submission-owned and completed its own single call.
- A stop never undoes an owned action: a submission-unknown (lost-acknowledgement)
  action stays visible with its claim, its `SUBMISSION_UNKNOWN` blocking reason and
  its retained reservations. Recovery reconciles the original reference to
  `CONFIRMED`; the stop is preserved and recovery never relabels the action unsent.
- Successor approval does not clear a stop: a higher-cap successor approval is
  still denied by a recorded stop.
- Monitoring and reservations stay: after a stop, the queue and status still show
  the pending delay, `recovery.status` and `recovery.list_cases` remain available,
  and the unknown reservations are retained.
- Breach stays blocked: a recorded breach remains `BREACHED` after a stop, and a
  later confirmation is blocked rather than applied.
- True process restart: a separate Python process (`sys.executable` over the same
  run-labelled database) reopens the stop, denies the scoped entry across the real
  process boundary, and returns `STOPPED_SCOPE` for the submission-ownership guard.

## Isolated resources

The suite reuses the shared `tests/conftest.py` run-labelled PostgreSQL 18
instance (labels `edge-os.test=1`, `edge-os.test.run=<run_id>`). The owned stop
fixture creates the `stops_local` schema plus the accepted `admission_local`,
`execution_local` and `recovery_local` schemas in that run-labelled database,
creates the owned tables there, and drops exactly those schemas at the end. The
migrated `public` schema is untouched. No production migration is released.

If a run is killed, list and remove only its own labelled resources:

```bash
python3 scripts/p03/harness.py orphans
python3 scripts/p03/harness.py remove-orphan <run_id>
```

## Last recorded run

Candidate commit recorded in the P25 candidate receipt. Numbers from the assigned
worktree.

- Full suite: 1002 passed, 2 known warnings, 222.92 s.
- Scoped-stop suite: 22 passed.
- Affected accepted suites (admission, execution, recovery, compiler, ownership,
  account views): 228 passed.
- P15, P02 and P06 contract scripts: PASS.
- `compileall` on the owned stop source/tests and the leased admission/execution
  source: PASS.
- `git diff --check` against the accepted base `c217ab7a`: clean.

## Not covered

Live execution, API routes, UI, browser checks, production migration, real
transport, provider enforcement, wallet signing, real signed bytes or a real
transaction hash, automatic resend, an exactly-once network guarantee, signer
removal and any real capital action. Real transport evidence is `NOT_RUN`. Timing
and contention numbers here are local observations, not a qualified live
service-level objective. The shared `feature-map.md` and `SKILL.md` stay reserved;
the owned proposal is not applied.
