# LOCAL Docker rehearsal runbook

Status: **LOCAL fixture profile only.** This packaging runs the accepted Edge OS web, API, PostgreSQL and worker commands on one machine with synthetic owners, a synthetic verification key, authored fixture providers and SYNTHETIC recorded research history. It is not a production deployment. It enables no provider, model, wallet, Privy login, public HTTPS, Contabo host, off-host backup or judge access.

## What runs

| Service | Image | Role | Network | Published |
|---|---|---|---|---|
| `postgres` | `postgres:18.6-trixie` (digest-pinned) | database on the named volume `database` | `private` (internal) | no |
| `migrate` | API image | the one explicit migration step: `alembic upgrade head`, then `alembic check` | `private` | no |
| `api` | API image | `python -m edge_os_api` (refuses a schema that is not head) | `private` | no |
| `web` | web image | `next start` of the bundle built with public values only | `private` | no |
| `entry` | API image | stdlib loopback entry: `/healthz`, `/readyz`, `/v1/...` to `api`, everything else to `web`; refuses bodies above 512 KiB with 413 (bounded discard, see the qualification README) | `private`, `entry` | `127.0.0.1:<port>` only |
| `research-worker` | API image | `edge_os_api.research.investigation_jobs` | `private` | no |
| `execution-worker` | API image | `edge_os_api.execution.worker` | `private` | no |
| `recurring-producer` | API image | `edge_os_api.execution.recurring_producer` | `private` | no |

The `private` network is internal: application, database and worker containers have no route out of the host. The `entry` network exists only so the entry can publish its loopback port. No service mounts a host path or the Docker socket. Application containers run as non-root users (API image uid 10001, web image uid 1000) with a read-only root filesystem, all capabilities dropped and `no-new-privileges`.

Images:

- `deploy/docker/api.Dockerfile`: Python 3.14 (`python:3.14-slim-trixie`, digest-pinned), dependencies from `apps/api/uv.lock` with `uv sync --frozen --no-dev` (uv 0.12.16 in the build stage only), and the runtime assets the application opens through its module paths (`docs/contracts`, `docs/qualification/p07`, two `docs/implementation` profiles, `apps/api/tests/fixtures`, `scripts/hermes_interpretation`, `scripts/hermes_job_support`).
- `apps/web/Dockerfile`: Node 24.13.1 (`node:24.13.1-trixie-slim`, digest-pinned), `npm ci --ignore-scripts` against `apps/web/package-lock.json`, `next build` with `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_PRIVY_APP_ID` as build arguments. The runtime container gets no Edge OS configuration.
- `.dockerignore` is an allow-list. Local `.env` files, virtual environments, `node_modules`, build output, `.git` and private folders never enter a build.

## Configuration

`compose.local.yml` reads six caller variables and no env file:

| Variable | Used by | Meaning |
|---|---|---|
| `EDGE_OS_LOCAL_RUN_ID` | all | run label for image tags and resource labels |
| `EDGE_OS_LOCAL_PUBLIC_PORT` | `entry`, web build, API CORS | the loopback port |
| `EDGE_OS_LOCAL_DB_NAME` | `postgres`, database URL | database created on first start |
| `EDGE_OS_LOCAL_DB_PASSWORD` | `postgres` (`POSTGRES_PASSWORD`), composed `EDGE_OS_DATABASE_URL` only | generated per run |
| `EDGE_OS_LOCAL_VERIFICATION_KEY` | API and workers | synthetic EC P-256 **public** key (newlines as `\n`) |
| `EDGE_OS_LOCAL_BUILD_SHA` | images, `/healthz` | source commit |

The API and worker settings are named one by one in the Compose file (`EDGE_OS_ENV=local`, test app id `edge-os-test-app`, fixture interpreter, wallet and execution modes, recorded research history, the research budget used by the accepted journeys). `EDGE_OS_PRIVY_APP_SECRET` is never set; the application refuses it. Setting `EDGE_OS_ENV=production` on this profile is refused (TLS, fixture modes, test app id, CORS). Do not weaken a rule to make this profile start elsewhere.

Never print or save a resolved `docker compose config`: it contains the database password. Validate with `docker compose -f compose.local.yml config --quiet`.

## Manual order

From the repository root, with the six variables exported (a run-generated password and a synthetic public key):

```bash
C="docker compose -f compose.local.yml -p edge-os-local-$EDGE_OS_LOCAL_RUN_ID"
$C build api web
$C up -d --wait postgres
$C run --rm migrate                    # the one explicit migration step
$C up -d --wait api web entry          # /readyz must answer {"status":"ready","schema_revision":<head>}
$C --profile workers up -d research-worker execution-worker recurring-producer
```

Before the migration the API exits with `database schema revision None does not match migration head` and each worker exits with code 3 before any effect. Health: `curl http://127.0.0.1:$EDGE_OS_LOCAL_PUBLIC_PORT/readyz`.

Stop with `$C --profile migrate --profile workers down`. Add `--volumes` only to delete this project's database and evidence volumes.

## Backup and restore (LOCAL)

- Backup: `$C exec -T postgres pg_dump -U edge_os -d "$EDGE_OS_LOCAL_DB_NAME" -Fc > <private folder>/backup.dump`. Keep it private; it contains every saved record.
- Restore: into a **new** Compose project and a **new, empty** database name. Start only its `postgres`, run `pg_restore --exit-on-error --single-transaction --no-owner --role=edge_os`, then `run --rm migrate python -m alembic check` (no upgrade), then start `api web entry`. Do not start worker roles until the restored state is compared and every action after the backup time is reconciled with its provider record.
- Never restore over the source database, drop a database to make room, downgrade the schema, or reset counters, nonces, permissions or spending records. A restore loses records written after the backup.

## Automated rehearsal

`scripts/deployment_rehearsal/rehearsal_run.py` runs the whole sequence on run-owned resources and removes exactly those resources at the end:

```bash
apps/api/.venv/bin/python scripts/deployment_rehearsal/rehearsal_run.py --evidence-root <private folder>
```

It needs Docker, the qualified `apps/api/.venv`, Node 24 and `tests/p03/node_modules` with Playwright Chromium. It builds fresh images without the layer cache, checks the startup refusals, seeds the accepted research and recurring journeys through the packaged screens and worker roles, replaces the application processes, backs up, restores into a separate project and database, reopens the saved records with GET requests only at 1280px and 390px, compares every saved identity with direct SQL and cleans up. `--cached-build`, `--allow-dirty` and `--keep` are development shortcuts; a run that uses them is not a candidate pass.

Guards without a stack: `cd apps/api && .venv/bin/python -m pytest ../../tests/deployment_rehearsal` (needs the Docker CLI; the build-context test uses the local daemon).

## Not covered

- **Hermes job path.** The accepted pinned-Hermes runner launches job containers from a trusted host-side supervisor and needs the separately owned relay/supervisor interface. This profile runs the `fixture` interpreter. The public API is never given the Docker socket to make a job start.
- Production host qualification, public HTTPS/DNS, actual egress controls, off-host encrypted backup and retention, real Privy sign-in, providers, financial operations, participants, physical phones and screen readers.
