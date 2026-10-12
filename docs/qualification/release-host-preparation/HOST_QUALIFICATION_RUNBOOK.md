# Host qualification runbook (Contabo VPS; future ordered checks; nothing executed)

Task RELEASE-HOST-PREP-L4-20261012-01, issue edge-os-app/edge-os#48. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`. Prepared 2026-10-12. Amendment A2 sets the target to the builder's **existing Contabo VPS**.

Status: **preparation only.** Every host result in this runbook is `NOT RUN`. No SSH, account, API, server, DNS, credential, install or deployment happened. The commands are for a future operator under an explicit packet; running them here is outside this task's authority.

Read [HOST_DECISION_PACKET.md](HOST_DECISION_PACKET.md) first. The VPS facts (CPU/RAM/disk/OS/services/domain), the plan/resources and every `REQUIRED_DECISION` are unresolved. **Fail closed:** a missing control or value stops that stage.

The repository at this base has **no production Compose file or application Dockerfiles**; the only Dockerfiles are scoped Hermes/P04 qualification artifacts. The image and Compose definitions are a **later assigned local implementation scope** (lane 2 owns shared application configuration). This runbook states the commands and observations the later definitions must satisfy.

## Classes

- **REVERSIBLE OPERATOR SETUP** — build, configuration and data checks that can be undone without an external effect.
- **EXTERNAL EFFECT (needs explicit packet authority)** — real authentication, model/data/provider calls, wallet, signing, broadcast, funding or money.
- **NOT RUN** — not executed.

## Stage 0 — Preconditions and approvals (all NOT RUN)

| # | Check | Done when | Class |
|---|---|---|---|
| 0.1 | VPS facts recorded: CPU, RAM, disk, OS, installed services (incl. Coolify), domain; or a separately authorized read-only inspection ran. | Gate H13 has an answer. | approval |
| 0.2 | Each `REQUIRED_DECISION` is recorded (orchestration choice, egress H1, runner isolation H2, DB TLS H5, sizes H7, provider money limits H8). | Every value recorded or the stage stops. | approval |
| 0.3 | A separate packet authorizes each external effect that will run. | Each effect separately authorized. | approval |
| 0.4 | The repository is at a frozen candidate. | `git rev-parse HEAD` equals the frozen candidate. | check |

Stop trigger: a missing host fact, decision or approval stops the affected stage.

## Stage 1 — Build images off the serving VPS (REVERSIBLE OPERATOR SETUP)

Build the images outside the serving VPS and deploy immutable digests; a build on the serving machine competes with the database and jobs.

| # | Check | Expected observation | Class |
|---|---|---|---|
| 1.1 | Frozen source | `git rev-parse HEAD` equals the frozen candidate; `git status --porcelain` is empty. | check |
| 1.2 | API image | A pinned Python `3.14.x` image with `uv sync --frozen` against `apps/api/uv.lock`; a non-root runtime user; no package manager downloaded at startup. | check |
| 1.3 | Web image | A pinned Node `24.x` image with `npm ci` against `apps/web/package-lock.json`; `NEXT_PUBLIC_*` values passed as build args; `next start`. | check |
| 1.4 | Contract/qualification assets in the image | The image contains at minimum `docs/contracts/p02/check_contract.py`, `docs/contracts/p06/contract.json`, `docs/qualification/p07/qualification.py`, `docs/implementation/EFFECT_COMPARISON_PROFILE.md`, `docs/implementation/SPOT_REPLAY_RUNTIME_PROFILE.md`. A package with only Python source fails to start (`EngineUnavailable` for P07). | check |
| 1.5 | Digest identity | Images are referenced by digest. `docker compose config --lock-image-digests` produces an **override** file (image entries only) that must be layered on the base production file; the build record names source/tree, Python/Node/toolchain versions and all runtime assets. | check |
| 1.6 | No secret in the image | No secret, key or token appears in any image layer, and no fixture label appears in the web bundle (the repository's own bundle scan logic). | check |

Fail closed: a floating tag, a root runtime user, or a missing asset stops the deploy.

## Stage 2 — Secrets provisioning by the operator (REVERSIBLE OPERATOR SETUP; secret values never enter source, image or model input)

Set the application names in the host secret store / Compose environment. Keep scoped ownership:

| Owner | Values |
|---|---|
| `postgres` service only | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| `api` service | `EDGE_OS_ENV=production`, `EDGE_OS_DATABASE_URL` (composed, `postgresql+psycopg://…?sslmode=require`), `EDGE_OS_PRIVY_APP_ID`, `EDGE_OS_PRIVY_VERIFICATION_KEY`, `EDGE_OS_CORS_ALLOWED_ORIGINS`, `EDGE_OS_BUILD_SHA`, the `EDGE_OS_*` quota/rate values, and the provider modes `unavailable` |
| `web` service | `NEXT_PUBLIC_API_BASE_URL` (build time), `NEXT_PUBLIC_PRIVY_APP_ID` (build time). **No database or session secret.** |

The API's `EDGE_OS_DATABASE_URL` necessarily contains the database credential; not sending a separate `POSTGRES_PASSWORD` variable to the API is not itself a security boundary. The boundary is that only the `postgres` service holds the raw `POSTGRES_*` variables and the credential is passed to the API only inside its composed connection URL.

| # | Check | Done when | Class |
|---|---|---|---|
| 2.1 | No forbidden name present (`EDGE_OS_PRIVY_APP_SECRET`, `EDGE_OS_AUTH_DISABLED`, `EDGE_OS_DEV_AUTH_BYPASS`). | Startup does not raise `unsupported configuration present`. | check |
| 2.2 | Production rules pass: non-loopback database; `sslmode=require`; no wildcard/non-HTTPS CORS; build SHA present; not the test app id; provider modes `unavailable`. | Startup does not raise `ConfigError`. | check |
| 2.3 | Quota/rate values frozen before the first owner. | Values recorded. | check |
| 2.4 | DB TLS | PostgreSQL accepts the `sslmode=require` (or stricter) connection from the API. A plain private-network connection copied from a reference project would fail this contract. | check |

Fail closed: a production-rule failure stops startup by design. Do not relax the rule or use local/fixture mode to make a deployment start.

## Stage 3 — Compose up, migrate, and prove readiness (REVERSIBLE OPERATOR SETUP)

Run a single explicit **serialized** migration step before the API takes traffic (not auto-migrate on each API start).

The lock file is an **override**, not a complete Compose file: `--lock-image-digests` writes image entries only. Always pass the base production file first, then the lock override, for `up`, `run` and every related check, and inspect the merged config for the intended ports, networks, volumes, secrets, healthchecks and commands before deploying.

```bash
# Build the web bundle with the public API origin baked in, then deploy by digest.
docker compose -f compose.production.yml config --lock-image-digests > compose.locked.yml
# Inspect the MERGED model (base first, then the override) before deploying.
docker compose -f compose.production.yml -f compose.locked.yml config > /tmp/edge-os-merged.yml
# Confirm ports, networks, volumes, secret env, healthchecks and commands, then:
docker compose -f compose.production.yml -f compose.locked.yml up -d postgres
# One explicit migration step against the direct (non-pooled) database:
docker compose -f compose.production.yml -f compose.locked.yml run --rm api uv run --frozen alembic upgrade head
docker compose -f compose.production.yml -f compose.locked.yml run --rm api uv run --frozen alembic check   # must report no difference
docker compose -f compose.production.yml -f compose.locked.yml up -d api web execution-worker research-worker
```

Do not commit a resolved config that contains secret values. A single `-f compose.locked.yml` would drop the base service model; do not use it.

| # | Check | Expected observation | Class |
|---|---|---|---|
| 3.1 | Fresh migration | `upgrade head` succeeds from empty; head is `0010`; `alembic check` reports no difference. | check |
| 3.2 | Migration is serialized | No container auto-migrates on start; exactly one migration step ran. | check |
| 3.3 | `/healthz` | `{"status":"ok","build_sha":<candidate>,"started_at":…}` via the proxy origin. | check |
| 3.4 | `/readyz` | `{"status":"ready","schema_revision":"0010"}`. Reason codes: `database_unavailable`, `schema_drift`, `verification_keys_missing`, `quota_cap_mismatch` (GLOBAL). | check |
| 3.5 | Workers start | Both worker containers run a bounded loop; neither publishes a port. | check |
| 3.6 | Worker schema-drift stop | On a database at revision `0009`, each worker stops with **exit code 3** and writes no row. | check |
| 3.7 | Repository files on disk | The deployed images contain the files listed in Stage 1.4. The root is derived from the module file path (`parents[5]`); the working directory is not the constraint. | check |
| 3.8 | Private services | Only the proxy publishes 443. `postgres`, `api`, `web`, both workers and the runner publish no host port. Verify externally (published container ports can bypass an OS firewall). | check |

Stop trigger: any unexpected 503 stops the stage. Record the exact reason code.

## Stage 4 — Real authentication and two owners (EXTERNAL EFFECT — needs auth packet authority)

| # | Check | Expected observation | Class |
|---|---|---|---|
| 4.1 | Real login | A real Privy token is accepted; `GET /v1/me` returns the verified `user_id`. | external |
| 4.2 | Rejected/expired session | A missing or wrong-key token is `401`; an expired token is `401` `auth_expired`. | check |
| 4.3 | Sign-out and owner change | A different owner yields a different `user_id`; no prior data is visible. | external |
| 4.4 | Two-owner isolation | Owner B cannot read, answer, publish, fund, adopt, submit, recover, stop or remove owner A's records, including with guessed IDs. Denials are `404`, change no protected row and make zero provider calls. | check + external |
| 4.5 | Row counts | `select count(*) from users;` matches the number of signed-in owners. | check |

Fail closed: browser test injection must never supply production authorization. If sign-in cannot run, this stage stays `NOT RUN`.

## Stage 5 — Jobs, runtime isolation and private output (external effects need their packets)

The Hermes runtime is **not available** at this base (gate H2). Until lane-1 output is accepted, run only the parts that need no real model or provider.

| # | Check | Expected observation | Class |
|---|---|---|---|
| 5.1 | Research job | A declared investigation starts a job; a reservation is saved before any adapter effect; the job reaches `REPORTED` or an honest terminal state. | external (recorded mode) / check |
| 5.2 | Provider-only network check | The deployment cannot reach a host outside the approved provider set. Verify externally; **cannot pass until H1 is decided**. | blocked (H1) |
| 5.3 | Private output directory | Each job writes only its own approved private directory; no cross-job or cross-owner file is readable. | check |
| 5.4 | Hermes whole-process isolation | One fresh isolated process per bounded Hermes job; no shared mutable memory; no signing credential, host workspace or Docker socket inside the job. **The public API/model process must not mount the host Docker socket.** | blocked (H2) |
| 5.5 | Cleanup after a job | A completed, cancelled or timed-out job cleans up its process and temporary files. | check |
| 5.6 | Secrets isolation | No credential appears in the browser bundle, prompts, logs or evidence. | check |
| 5.7 | Trusted runner boundary | The job-container runner is separately qualified; a helper present in a plan is not an accepted runner. | blocked (H2) |

Fail closed: a missing isolation control keeps real-model/research capability unavailable. Do not run a real Hermes job without the accepted isolation and a recorded inference budget.

## Stage 6 — Persistence, restart, off-VPS backup, restore and rollback (mixed: 6.1–6.6 reversible; 6.7 destructive, last-resort)

| # | Check | Expected observation | Class |
|---|---|---|---|
| 6.1 | Restart survives data | Restart the API and workers on the same database; saved requests, revisions, replays, account records, quotas and jobs are unchanged. | check |
| 6.2 | Actual process replacement | A restart replaces the running process (not only a container health flip); a claimed restart without actual process replacement proves nothing. | check |
| 6.3 | Reopen after restart | A saved revision reopens in a new browser context with the same text, hash and IDs; no recompute and no new row. | check |
| 6.4 | Off-VPS backup | `pg_dump -Fc` runs and the dump is stored **off the VPS** with a recorded frequency and encrypted storage. Snapshots are not backups. | check |
| 6.5 | Fresh-database restore rehearsal | `pg_restore` into a **fresh** database; point `EDGE_OS_DATABASE_URL` at it; `alembic check` passes; `/readyz` is ready; a known budget and job match their pre-backup values. Record the recovery point/time bounds. | check |
| 6.6 | Schema-compatible artifact rollback | The host rolls back to the previous deploy; the previous version answers `/readyz`; the database schema stays compatible with the rolled-back artifact. | check |
| 6.7 | Schema downgrade (**last resort only**) | `alembic downgrade 0009` then `upgrade head` keeps OWNER totals, but the downgrade **drops** data that `0009` cannot hold: the usage event history (`usage_local.usage_events`, including `CAP_CHANGED`), overrun amounts, `usage_local.usage_reservations` rows, `usage_local.request_windows`, and every GLOBAL allocation. A later `upgrade head` recreates GLOBAL allocations from OWNER totals at the **default** caps, so any operator-set GLOBAL cap is lost; it does not restore the dropped event, reservation or window rows. Do not read the OWNER-total result as proof that a downgrade is safe. Prefer restore (6.5). Use a downgrade only after a recorded preservation/reconciliation decision that accepts these losses, and never as a routine rollback. | check |

Stop trigger: a failed restore or a `/readyz` mismatch stops the stage. **No automatic migration rollback, deletion or counter reset.** A restore or downgrade is an operator action with a recorded reason. A restore loses records written after the backup, including financial records that may already have reached a provider; read the provider record of every action after the backup time before allowing new work. A downgrade additionally erases the usage audit trail listed in 6.7. A snapshot, a restart or a healthy container does not qualify data restore, external transaction recovery or recurring operation. Do not copy a reference project's daily/7-day retention as approved financial bounds.

## Stage 7 — Original action, revocation and recurring checks (EXTERNAL EFFECT — needs financial/recurring packet authority)

Prerequisite: a separately approved live packet. **Do not run any of this without it.**

| # | Check | Expected observation | Class |
|---|---|---|---|
| 7.1 | One controlled action (entry) | One approved fixed-input action runs through the application while the owner is offline; decision, revision, mandate, intent, reservation, original bytes/hash, transaction and receipt are saved; actual effects are observed independently. | external |
| 7.2 | Original-action recovery | On an interrupted/unknown submission the application reconciles the original action and makes no second economic action. | external |
| 7.3 | Full exit | One approved full exit runs; no additions or partial exits. | external |
| 7.4 | Independent denial | A stop or removal denies new work at admission and immediately before submission; denials make no provider call. | external |
| 7.5 | Revocation and owner access | Removing the agent stops new work; the owner keeps access; residual holdings are shown; no automatic liquidation or withdrawal. | external |
| 7.6 | Recurring operation (P27) | Repeated scheduled occurrences run under standing bounded permission; duplicate ticks and restart create no duplicate occurrence; missed slots and catch-up follow the adopted policy. The recurring-evaluation producer is distinct from the saved-job workers. | external |
| 7.7 | Provider counters | Independent provider/chain counters match the saved action counts. | external |

Bound rules: pin the network, route/contracts, wallet, assets, raw input, minimum output, fees/gas, expiry, request/attempt/gas ceilings and stop conditions. Never trade to manufacture a signal or repeat a swap for recording aesthetics. **Before resumption, reconcile external effects and liability; do not reset nonce, permission or spending records by restoring or downgrading.**

## Stage 8 — Judge access (REVERSIBLE OPERATOR SETUP; publication is separate authority)

| # | Check | Expected observation | Class |
|---|---|---|---|
| 8.1 | Public HTTPS URL | The proxy serves the web app and the API over HTTPS. | check |
| 8.2 | Judge owner/test account | A disclosed bounded owner account exists; synthetic fixtures stay separated from live account state in the copy. | check |
| 8.3 | Repository access | The judge can read the repository (default: a public repo). | check |
| 8.4 | Access instructions | Instructions name the URL, the sign-in method and any test credentials. | check |

## Stage 9 — Stop triggers and fail-closed rules (summary)

Stop and record the blocker when any of these is true:

- a required approval, VPS fact or `REQUIRED_DECISION` value is missing;
- a production startup rule fails (do not relax it or use local/fixture mode);
- a secret appears in an image layer, a bundle, a log or evidence;
- `/readyz` reports a reason other than an expected test condition;
- a worker exits on schema drift for a reason other than the tested drift;
- a required isolation or egress control is absent, or the host Docker socket is mounted into the public API/model;
- a restore or rollback does not reproduce the pre-backup values;
- an external effect has no separate packet.

Every live or host result in this runbook is currently **NOT RUN**.
