# Local revocation verification recipe

P30 local preparation. Run from the assigned worktree root. This recipe proves the
local removal domain: an owner-scoped removal request persisted before any
controlled effect; separate owner request, provider-style observation and derived
state; exact-matched fixture confirmation; durable pending and unknown status; a
NEW local P30 denial check; owner access, pending actions and residual holdings
retained across the accepted modules; atomic binding/observation ordering; a true
process reopen; and a cross-process request race. It does not prove API wiring, a
UI, a production migration, a real provider, real signer removal, a live route,
independent Privy enforcement or any onchain effect.

## Preflight

```bash
cd apps/api && uv sync --frozen
```

Requires Python 3.14 and a working Docker engine for the run-labelled PostgreSQL
18 container.

## Checks

```bash
# Offline contracts (from the worktree root)
python3 -B docs/contracts/p02/check_contract.py
python3 -B docs/contracts/p06/check_contract.py
python3 -B docs/contracts/p15/check_contract.py

# Focused owned suite (real labelled PostgreSQL, one run-labelled container)
(cd apps/api && uv run --frozen pytest tests/revocation)

# Affected accepted suites
(cd apps/api && uv run --frozen pytest tests/admission tests/execution tests/recovery \
  tests/stops tests/funding tests/consent tests/wallet_setup \
  tests/test_strategy_compiler.py tests/test_strategy_compilation_api.py \
  tests/test_ownership.py tests/test_account_views.py)

# P16 offline qualification tests (actual selectors)
(cd apps/api && uv run --frozen pytest ../../docs/qualification/p16 -q)

# Full suite
(cd apps/api && uv run --frozen pytest)

# Compile check (the supported type/compile tool in this repository)
(cd apps/api && uv run --frozen python -m compileall -q \
  src/edge_os_api/revocation tests/revocation)
```

The owned suite starts one run-labelled PostgreSQL 18 container and asserts no
leftover resources at the end (`tests/conftest.py`, `pg` fixture). It creates the
owned `revocation_local` schema plus the accepted `admission_local`, `stops_local`,
`funding_local` and `consent_local` schemas inside that run-labelled database only,
and drops the owned schemas at session end.

## What the owned suite proves

- Strict typed validation: an owner in the body, a blank or malformed agent, an
  unsupported network, a blank signer/policy, a non-UTC time and a non-UUID
  request are all refused at the boundary. `not_requested` is not an observation
  outcome.
- The request resolves the actual saved wallet binding and refuses a missing
  binding or a mismatched `expected_wallet_id`. The durable request is written
  before any controlled effect and read back through direct SQL.
- An exact repeated request is idempotent and writes one row; a changed request
  key, signer, policy or reason for the same identity is refused. Another owner
  sees only their own records.
- Matched observations derive `PENDING`, `UNKNOWN`, `FAILED` or `CONFIRMED`. A
  `CONFIRMED` observation with no signer or policy evidence stays `UNKNOWN`.
  Wrong-wallet, wrong-signer, wrong-network, stale and stale-binding observations
  are refused with their codes and never change the state. An exact repeated
  observation key is idempotent; a changed reuse of the same key is refused. A
  later observation that contradicts a confirmed removal, or that would replace the
  confirmed signer, is retained as contradictory and changes nothing.
- The removal transaction takes the accepted wallet-setup `FOR UPDATE` row lock on
  the binding and holds it through commit. A real cross-session race shows a
  concurrent binding update is blocked while the removal transaction holds the
  lock, so a stale binding cannot be confirmed.
- The local P30 check denies `PENDING`, `UNKNOWN` and `CONFIRMED`, and does not
  deny `REQUESTED` or `FAILED`. The denial holds while a real authored action is
  `ADMITTED` on usable allowances with no stop, so an exhausted counter or an old
  stop cannot be the cause.
- Owner-positive and B-positive controls: after a confirmed removal the owner still
  reads their binding and admits a new owner-reviewed action, and the other
  wallet's permission and admission are unchanged.
- A direct controlled provider-style submission refusal for removed A is exercised
  through an authored fixture transport, separate from the local P30 check and with
  a distinct token. It is labelled `SYNTHETIC_AUTHORED`; it is not live Privy
  enforcement.
- Preservation: `request_removal` and `reconcile` leave every accepted
  `admission_local`, `stops_local`, `funding_local`, `consent_local` and public
  wallet-setup row byte-identical, including a `SUBMISSION_UNKNOWN` pending action
  and its reservations and a recorded stop.
- Durability: a separate Python process reads `REMOVAL_CONFIRMED` from the same
  database; a restart re-request is idempotent and creates no new identity; two
  concurrent separate processes requesting the same identity serialize to exactly
  one request row.

## SQL inspection

The suite inspects saved rows directly. After a run, the durable state is:

```sql
select request_id, agent_id, wallet_id, network_id, request_key, signer_identity
from revocation_local.removal_requests;
select observation_key, observed_state, matched, contradictory, denial_code
from revocation_local.removal_observations order by sequence;
select state, reason, evidenced_signer, contradictory
from revocation_local.removal_states;
```

The derived `state` is one of the accepted P15 removal states. `matched = false`
rows carry a denial code; a `contradictory = true` row never restores permission.

## Last recorded run

Candidate commit recorded in the P30 candidate receipt. Numbers from the assigned
worktree, base `9210bc1d054f1d5623693f787737a7b80563185a`.

- Full suite: 1153 passed, 12 warnings, 147.68 s.
- Focused revocation suite: 54 passed.
- Affected accepted suites (admission, execution, recovery, stops, funding,
  consent, wallet setup, compiler, compilation API, ownership, account views):
  387 passed.
- P16 offline qualification: 12 passed, 10 subtests passed.
- P02, P06 and P15 contract scripts: PASS.
- `compileall` on the owned revocation source/tests: PASS.

## Not run and limits

- API route and UI wiring: **NOT_RUN**. The package has no router and the app
  mounts no removal route.
- Production migration: **NOT_RUN**. The owned tables exist only in the
  run-labelled test schema.
- Real provider signer removal and independent Privy enforcement: **NOT_RUN**. The
  observations are authored `SYNTHETIC_AUTHORED` fixtures; they never prove real
  provider behavior.
- The local P30 wiring into P22 admission or P23 execution: **NOT_RUN**. The check
  is prepared and unmounted.
- Final P30 acceptance and any onchain effect: **NOT_RUN**. They require the later
  qualified P20 and P26 release evidence.
