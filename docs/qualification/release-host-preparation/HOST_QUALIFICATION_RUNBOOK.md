# Host qualification runbook (future ordered checks; nothing executed)

Task RELEASE-HOST-PREP-L4-20261012-01, issue edge-os-app/edge-os#48. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`, tree `31e71d47b63cf14686470d46e5469de59565d3f9`. Prepared 2026-10-12.

Status: **preparation only.** Every host result in this runbook is `NOT RUN`. No host, account, secret, migration, deployment or provider call exists. The commands below come from the accepted repository at the assigned base. They are for a future operator under an explicit approval packet; running them here is outside this task's authority.

Read [HOST_DECISION_PACKET.md](HOST_DECISION_PACKET.md) first. The host, plan, region and every `REQUIRED_DECISION` value are unresolved. **Fail closed:** if a required control or value is missing, stop that stage and record the blocker. Do not substitute a default, an allow-list or a fixture for a missing control.

## Classes used below

- **REVERSIBLE OPERATOR SETUP** — provisioning, configuration and data checks that can be undone without an external effect.
- **EXTERNAL EFFECT (needs explicit packet authority)** — real authentication, real model/data/provider calls, wallet, signing, broadcast, funding or money. Each needs its own approved packet with named bounds.
- **NOT RUN** — not executed.

## Stage 0 — Preconditions and approvals (all NOT RUN)

| # | Check | Done when | Class |
|---|---|---|---|
| 0.1 | An approval packet names the host, plan, region, workspace tier, exact repositories/branches, and the maximum monthly spend. | The packet exists and the builder accepted it. | approval |
| 0.2 | Each `REQUIRED_DECISION` in the host packet is recorded (region; service sizes; provider-only-egress decision H1; Hermes isolation H2; quota/rate values). | Every value is recorded or the stage stops. | approval |
| 0.3 | A separate packet authorizes each external effect that will run (real Privy app, real model, real data providers, wallet/signing, funding). | Each effect is separately authorized; otherwise it stays NOT RUN. | approval |
| 0.4 | The repository is at a frozen candidate. No candidate moves after this point without a recorded replacement. | `git rev-parse HEAD` equals the frozen candidate. | check |

Stop trigger: any missing approval or decision stops the affected stage. Missing external authority blocks only the corresponding external effect; reversible setup may continue if the operator chooses.

## Stage 1 — Fresh checkout and build (REVERSIBLE OPERATOR SETUP)

Goal: a clean build from the frozen candidate produces the exact artifacts, with no secret in source.

```bash
git clone <public-or-authorized-repo> edge-os
cd edge-os
git fetch --all
git checkout <frozen-candidate-sha>
git rev-parse HEAD                      # must equal the frozen candidate
git status --porcelain                  # must be empty
cd apps/api && uv sync --frozen
cd ../web && npm ci
```

| # | Expected observation | Class |
|---|---|---|
| 1.1 | `uv sync --frozen` completes without a lockfile change; `apps/api/uv.lock` is unchanged. | check |
| 1.2 | `npm ci` completes; `apps/web/package-lock.json` is unchanged. | check |
| 1.3 | Production build succeeds. The web build reads `NEXT_PUBLIC_*` at build time. | check |
| 1.4 | No secret appears in the web bundle. The repository's own bundle scan (`bundle-scan.json` logic) finds no fixture-provider label and no private-key block. | check |

Artifact identities to record: candidate SHA, `uv.lock` SHA-256, `package-lock.json` SHA-256, web build output ID, runtime versions (`python --version`, `node --version`).

Fail closed: a lockfile change or a secret in the bundle stops the deploy.

## Stage 2 — Secrets provisioning by the operator (REVERSIBLE OPERATOR SETUP; secret values never enter source or model input)

Set these in the host secret store only. The application reads them through `EDGE_OS_*` names. Never commit a value.

| Name | Purpose | Required production value |
|---|---|---|
| `EDGE_OS_ENV` | environment | `production` |
| `EDGE_OS_DATABASE_URL` | database | internal Postgres URL in `postgresql+psycopg://` form with `?sslmode=require` |
| `EDGE_OS_PRIVY_APP_ID` | auth | the real Privy app id (not the test id) |
| `EDGE_OS_PRIVY_VERIFICATION_KEY` | auth | the real EC P-256 public key |
| `EDGE_OS_CORS_ALLOWED_ORIGINS` | CORS | the exact web origin, `https://…`, no wildcard |
| `EDGE_OS_BUILD_SHA` | identity | the frozen candidate SHA (or the host commit variable) |
| `EDGE_OS_EXECUTION_MODE` | provider mode | `unavailable` |
| `EDGE_OS_WALLET_PROVIDER` | wallet mode | `unavailable` |
| `EDGE_OS_RESEARCH_HISTORY_MODE` | research mode | `unavailable` |
| `EDGE_OS_RESEARCH_BUDGET_*`, `EDGE_OS_USAGE_GLOBAL_*`, `EDGE_OS_WRITE_RATE_PER_MINUTE`, `EDGE_OS_RESEARCH_MAX_ACTIVE_JOBS` | quotas/limits | chosen **before the first owner**; they freeze at first use |

| # | Check | Done when | Class |
|---|---|---|---|
| 2.1 | No forbidden name is present (`EDGE_OS_PRIVY_APP_SECRET`, `EDGE_OS_AUTH_DISABLED`, `EDGE_OS_DEV_AUTH_BYPASS`). | The startup check does not raise `unsupported configuration present`. | check |
| 2.2 | Every production rule passes: non-loopback database; `sslmode=require`; no wildcard/non-HTTPS CORS; build SHA present; not the test app id; provider modes `unavailable`. | Startup does not raise `ConfigError`. | check |
| 2.3 | Quota/rate values are frozen before the first owner arrives. | Values are recorded; nothing resets them later without `set-cap`. | check |

Fail closed: a production-rule failure stops startup by design. Do not relax the rule to make startup pass.

## Stage 3 — Migrations and start (REVERSIBLE OPERATOR SETUP)

```bash
# Migration connection: use the DIRECT (non-pooled) endpoint, session-scoped DDL.
cd apps/api
EDGE_OS_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@INTERNAL_HOST:PORT/DATABASE?sslmode=require' \
  uv run --frozen alembic upgrade head
EDGE_OS_DATABASE_URL='...' uv run --frozen alembic check    # must report no difference
```

Start the API (web service) with the repository-root context:

```bash
EDGE_OS_BUILD_SHA=<candidate> uv run --frozen uvicorn --factory edge_os_api.main:create_app --host 0.0.0.0 --port $PORT
```

Start the workers:

```bash
uv run --frozen python -m edge_os_api.execution.worker
uv run --frozen python -m edge_os_api.research.investigation_jobs
```

| # | Check | Expected observation | Class |
|---|---|---|---|
| 3.1 | Fresh migration | `upgrade head` succeeds from empty; head is `0010`; `alembic check` reports no difference. | check |
| 3.2 | `/healthz` | `{"status":"ok","build_sha":<candidate>,"started_at":…}`. | check |
| 3.3 | `/readyz` | `{"status":"ready","schema_revision":"0010"}`. | check |
| 3.4 | Readiness failure codes | A wrong schema gives 503 `schema_drift`; a missing key gives 503 `verification_keys_missing`; a changed GLOBAL cap gives 503 `quota_cap_mismatch`; an unreachable database gives 503 `database_unavailable`. | check |
| 3.5 | Workers start | Both worker processes run a bounded loop; neither binds a port. | check |
| 3.6 | Worker schema-drift stop | On a database at revision `0009`, each worker stops with **exit code 3** and writes no row. | check |
| 3.7 | Repository root | The API starts with the repository root as its working tree (the import reads `docs/contracts/p02` and `docs/contracts/p06`). | check |

Stop trigger: any 503 other than the expected test condition stops the stage. Record the exact reason code.

## Stage 4 — Real authentication and two owners (EXTERNAL EFFECT — needs auth packet authority)

Prerequisite: the real Privy app exists and the operator can complete a real sign-in.

| # | Check | Expected observation | Class |
|---|---|---|---|
| 4.1 | Real login | A real Privy access token is accepted; `GET /v1/me` returns the verified `user_id`. | external |
| 4.2 | Rejected/expired session | A missing or wrong-key token is `401`; an expired token is `401` with `auth_expired`. | check |
| 4.3 | Sign-out and owner change | Signing out and returning as another owner yields a different `user_id`; no prior data is visible. | external |
| 4.4 | Two-owner isolation | Owner B cannot read, answer, publish, fund, adopt, submit, recover, stop or remove owner A's records, including with guessed IDs. Denials are `404`, change no protected row and make zero provider calls. | check + external |
| 4.5 | Database row counts | `select count(*) from users;` matches the number of signed-in owners; login creates nothing else. | check |

Fail closed: browser test injection must never supply production authorization (PU01). If sign-in cannot run, this stage stays NOT RUN.

## Stage 5 — Jobs, runtime isolation and private output (external effects need their packets)

This stage covers the bounded research/execution job lifecycle and the qualified Hermes job runtime. The Hermes runtime is **not available** at the base (gate H2). Until lane-1 output is accepted, run only the parts that do not need a real model or provider.

| # | Check | Expected observation | Class |
|---|---|---|---|
| 5.1 | Research job | A declared investigation starts a job; a reservation is saved before any adapter effect; the job reaches `REPORTED` or an honest terminal state. | external (recorded mode) / check |
| 5.2 | Provider-only network check | The deployment cannot reach a host outside the approved provider set. **Cannot pass on the proposal host.** | blocked (H1) |
| 5.3 | Private output directory | Each job writes only its own approved output/evidence directory; no cross-job or cross-owner file is readable. | check |
| 5.4 | Hermes whole-process isolation | One fresh isolated process per bounded Hermes job; no shared mutable memory; no signing credential, host workspace or Docker socket inside the job. | blocked (H2) |
| 5.5 | Cleanup after a job | A completed, cancelled or timed-out job cleans up its process and temporary files. | check |
| 5.6 | Secrets isolation | No credential appears in browser bundles, prompts, logs or evidence. | check |

Fail closed: a missing isolation control keeps real-model/research capability unavailable. Do not run a real Hermes job without the accepted isolation and a recorded inference budget.

## Stage 6 — Persistence, restart, restore and rollback (REVERSIBLE OPERATOR SETUP)

| # | Check | Expected observation | Class |
|---|---|---|---|
| 6.1 | Restart survives data | Restart the API and workers on the same database; saved requests, revisions, replays, account records, quotas and jobs are unchanged. | check |
| 6.2 | Reopen after restart | A saved revision reopens in a new browser context with the same text, hash and IDs; no recompute and no new row. | check |
| 6.3 | Backup | `pg_dump -Fc -f <file> <database>` produces a backup. | check |
| 6.4 | Restore rehearsal on the host | `pg_restore` into a new database; point `EDGE_OS_DATABASE_URL` at it; `alembic check` passes; `/readyz` is ready; a known budget and job match their pre-backup values. | check |
| 6.5 | Schema downgrade (last resort) | `alembic downgrade 0009` then `upgrade head` keeps owner totals; the runbook records the data a downgrade loses. | check |
| 6.6 | Rollback build | The host rolls back to the previous deploy; the previous version answers `/readyz`. | check |

Stop trigger: a failed restore or a `/readyz` mismatch stops the stage. **No automatic migration rollback, deletion or counter reset.** A restore or downgrade is an operator action with a recorded reason. A restore loses records written after the backup, including financial records that may already have reached a provider; read the provider record of every action after the backup time before allowing new work.

## Stage 7 — Original action, revocation and recurring checks (EXTERNAL EFFECT — needs financial/recurring packet authority)

Prerequisite: a separately approved live packet. **Do not run any of this without it.**

| # | Check | Expected observation | Class |
|---|---|---|---|
| 7.1 | One controlled action (entry) | One approved fixed-input action runs through the application while the owner is offline; decision, revision, mandate, intent, reservation, original bytes/hash, transaction and receipt are saved; actual effects are observed independently. | external |
| 7.2 | Original-action recovery | On an interrupted/unknown submission, the application reconciles the original action and makes no second economic action. | external |
| 7.3 | Full exit | One approved full exit runs; no additions or partial exits. | external |
| 7.4 | Independent denial | A stop or removal denies new work at admission and immediately before submission; denials make no provider call. | external |
| 7.5 | Revocation and owner access | Removing the agent stops new work; the owner keeps access; residual holdings are shown; no automatic liquidation or withdrawal. | external |
| 7.6 | Recurring operation (P27) | Repeated scheduled occurrences run under standing bounded permission, with duplicate ticks and restart creating no duplicate occurrence; missed slots and catch-up follow the adopted policy. | external |
| 7.7 | Provider counters | The independent provider/chain counters match the saved action counts. | external |

Bound rules: pin the network, route/contracts, wallet, assets, raw input, minimum output, fees/gas, expiry, request/attempt/gas ceilings and stop conditions. Never trade to manufacture a signal or repeat a swap for recording aesthetics.

Fail closed: an unresolved control (for example the opaque-program restriction in IC08) keeps funded execution unavailable.

## Stage 8 — Judge access (REVERSIBLE OPERATOR SETUP; publication is separate authority)

| # | Check | Expected observation | Class |
|---|---|---|---|
| 8.1 | Public live URL | A public HTTPS URL serves the web app and the API. | check |
| 8.2 | Judge owner or test account | A disclosed, bounded owner account exists; synthetic fixtures stay separated from live account state in the copy. | check |
| 8.3 | Repository access | The judge can read the repository (default: a public repo). | check |
| 8.4 | Access instructions | Instructions name the URL, the sign-in method and any test credentials. | check |

Publication and repository visibility are builder decisions, not operator setup.

## Stage 9 — Stop triggers and fail-closed rules (summary)

Stop and record the blocker when any of these is true:

- a required approval or `REQUIRED_DECISION` value is missing;
- a production startup rule fails (do not relax it);
- a secret appears in source, a bundle, a log or evidence;
- `/readyz` reports a reason other than an expected test condition;
- a worker exits on schema drift for a reason other than the tested drift;
- a required isolation or egress control is absent;
- a restore or rollback does not reproduce the pre-backup values;
- an external effect has no separate packet.

Every live or host result in this runbook is currently **NOT RUN**.
