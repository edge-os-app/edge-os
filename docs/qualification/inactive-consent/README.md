# Inactive consent local verification recipe

P26 inactive preparation. Run from the assigned worktree root. This recipe proves
the local inactive-consent domain: an owner-scoped grouped review of one exact
saved revision, wallet and limits; durable clearly INACTIVE owner adoption; exact
identity denials; atomic stale and duplicate races; a true-process reopen; and
that the accepted modules are unchanged. It does not prove API wiring, a UI,
a production migration, a real provider, a signer/policy binding, a live route,
activation or an exactly-once network guarantee.

## Preflight

```bash
cd apps/api && uv sync --frozen
```

Requires Python 3.14 and a working Docker engine for the run-labelled
PostgreSQL 18 container.

## Checks

```bash
# Offline contracts (from the worktree root)
python3 -B docs/contracts/p02/check_contract.py
python3 -B docs/contracts/p06/check_contract.py
python3 -B docs/contracts/p15/check_contract.py

# Focused owned suite (real labelled PostgreSQL, one run-labelled container)
(cd apps/api && uv run --frozen pytest tests/consent)

# Affected accepted suites
(cd apps/api && uv run --frozen pytest tests/admission tests/execution tests/recovery \
  tests/stops tests/funding tests/wallet_setup tests/test_strategy_compiler.py \
  tests/test_strategy_compilation_api.py tests/test_ownership.py tests/test_account_views.py)

# P16 offline qualification tests (actual selectors)
(cd apps/api && uv run --frozen pytest ../../docs/qualification/p16 -q) || true

# Full suite
(cd apps/api && uv run --frozen pytest)

# Compile check (the supported type/compile tool in this repository)
(cd apps/api && uv run --frozen python -m compileall -q \
  src/edge_os_api/consent tests/consent)
```

The owned suite starts one run-labelled PostgreSQL 18 container and asserts no
leftover resources at the end (`tests/conftest.py`, `pg` fixture). It creates the
owned `consent_local` schema plus the accepted modules' schemas inside that
run-labelled database only, and drops the owned schemas at session end.

## What the owned suite proves

- The grouped review groups the exact selected revision's rules, evidence status
  and material limitations, operating purpose, wallet/network, route, allocation,
  per-asset allowances, attempts, gas, expiry and stop effects.
- The wallet balance is shown separately from the adopted allocation.
- Strict typed validation rejects an owner in the body, missing required limits,
  boolean/integer coercion, negative/non-finite values, blank identifiers,
  non-UTC times and unlike-asset combination. An explicit zero stays a value.
- Owner-scoped reads: another owner cannot review, read or adopt the record.
- Fail-closed denials: network mismatch, wrong-network asset, revision/wallet
  mismatch, unconfirmed wallet, changed terms, stale review, expired terms,
  revision drift and wallet drift.
- Adoption is idempotent on an identical repeat, conflicts on a changed reuse,
  and yields exactly one consent under two concurrent adopters, including a
  second OS process adopting the same review.
- A wallet that becomes unconfirmed between the first read and the adoption save
  is denied: the current binding is re-read under the wallet-setup row lock in the
  transaction that saves the consent.
- A genuinely new process reads the same durable consent hash.
- Review and adoption leave the accepted admission, execution, recovery, stops,
  funding, strategy, wallet and user rows byte-identical, including a
  `SUBMISSION_UNKNOWN` pending action and a stopped wallet.

## SQL inspection

The suite inspects saved rows directly. After a run, the durable state is:

```sql
select review_id, agent_id, wallet_id, network_id, terms_hash, review_hash, status
from consent_local.consent_reviews;
select adoption_id, review_id, review_hash, consent_hash, status
from consent_local.consent_adoptions;
select operation, code from consent_local.consent_denials order by created_at;
```

`status` is always `INACTIVE`. No active authority snapshot exists.

## Not run and limits

- API route and UI wiring: **NOT_RUN**. The package has no router and the app
  mounts no consent route.
- Production migration: **NOT_RUN**. The owned tables exist only in the
  run-labelled test schema.
- Real provider, signer or policy binding: **NOT_RUN**. The route and policy are
  authored and explicitly `UNQUALIFIED`.
- Full P26 activation and live operation: **NOT_RUN**. Activation requires the
  later qualified P20/P21/P24/P25 evidence.
