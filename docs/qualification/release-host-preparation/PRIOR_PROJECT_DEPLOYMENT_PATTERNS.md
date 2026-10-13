# Portable prior-project deployment patterns (Contabo VPS)

Task RELEASE-HOST-PREP-L4-20261012-01, issue edge-os-app/edge-os#48. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`. Prepared 2026-10-12. Amendment A2 names these references for the builder-selected existing Contabo VPS.

Status: **read-only inspection only.** No reference project was changed; no script or test was executed; no credential or session archive was read. The patterns below are independently written, not copied implementation. They are lessons, not adopted code and not an installation authorization.

The A2 amendment names these references and this file records only portable lessons. It copies no private file, no environment value and no reference-project instruction.

## Reference identities (verified 2026-10-12)

| Project | Path | HEAD | Selected files (SHA-256) |
|---|---|---|---|
| Veridex Arena | `/Users/degencodebeast/Projects/personal/tx-odds-hack/veridex-arena` (branch `post2d-sdd`) | `8274245d971d9805c4e9bde295018bc5616dc0a2` | `compose.coolify.yml` `5a3c70db…`; `Dockerfile.api` `0f839837…`; `apps/web/Dockerfile` `5cce2738…`; `Dockerfile.agent` `0453fdbe…`; `deploy/coolify/backup-restore.md` `7004d062…`; `deploy/coolify/runbook.md` `713d8576…`; `tests/test_d1_compose_deploy.py` `791cad5c…` |
| Assensus | `/Users/degencodebeast/Projects/personal/okx-ai-hack/assensus` (branch `main`) | `20eb03c9be51da120a306ba5446de05fac98e982` | `docker-compose.coolify.yml` `a48e56fa…`; `services/api/Dockerfile` `28323015…`; `apps/web/Dockerfile` `2d6309d2…`; `docs/deployment/README.md` `28307ee4…`; `services/api/tests/test_coolify_topology.py` `c9947e43…`; `scripts/verify-stack.sh` `f6f2cb92…` |

Contabo reference identity receipt: `.scratch/contabo-reference-identities-20261012.json`, SHA256 `b44da435…`. Research note: `docs/research/EDGE_OS_CONTABO_DEPLOYMENT_RESEARCH_2026-10-12.md`, SHA256 `84531688…`.

## Veridex Arena — useful patterns

- **Fail-closed configuration.** Required secrets use `${VAR:?message}` in Compose, so a missing value aborts `docker compose config`/`up` instead of falling back to a local or in-memory default. Edge OS already refuses an incomplete production configuration; the Compose layer should match it.
- **Readiness deeper than liveness.** A `/readyz` health check gates on durable dependencies (database plus durable spools), separately from a shallow `/healthz`. Edge OS already has this split (`/healthz` vs `/readyz`).
- **Separate durable volumes.** Postgres, an event spool and captured replay artifacts each use their own named volume that survives container replacement. The comment warns not to use `tmpfs`.
- **Restore drill.** The backup guide schedules a `pg_dump -Fc` and a restore into a **fresh** database, then reads a known row back. A restart with no actual process replacement proves nothing.
- **Build-time public values.** The web image inlines public API/auth identifiers at build time and runs the production server directly, with no package manager downloaded at startup.

### Veridex limits (do not copy)

- Its Compose file **publishes** API and web host ports; Edge OS should adopt Assensus's private-services pattern instead.
- Its API image runs as **root**, and its base tags and dependency install are not fully immutable.
- AgentOS runs inside its API service. That single-process-tree architecture does **not** meet Edge OS's distinct worker/isolation contract by reuse.
- Its agent Dockerfile exists but is not a service in the inspected Compose file.
- Its local scripts and documentation are not proof of an actual Contabo deployment; no live deployment receipt was inspected.

## Assensus — useful patterns

- **No published host ports.** The production Compose file maps no host `ports`; the proxy fronts web and API, and PostgreSQL stays private. Services reach each other by service name on the internal bridge network.
- **Scoped secret ownership.** Postgres role credentials exist only on the postgres service. The API receives the composed `DATABASE_URL`, never the raw password variable. The web service receives no database or session secret.
- **Public vs private API address.** The browser API origin is a public **build-time** value (`NEXT_PUBLIC_*`); server-side SSR reaches the API over a private runtime address (`http://api:8000`). Edge OS's `NEXT_PUBLIC_API_BASE_URL` is the public build-time value.
- **Immutable, non-root images.** The API image uses a pinned `uv` builder stage, a pinned slim runtime, `uv sync --locked`, a non-root user (`uid 10001`) and an explicit `alembic upgrade head && uvicorn` command.
- **Startup ordering and restart verification.** Health dependencies order startup; restart verification checks the same instance through HTTP and its operation through SQL.

### Assensus limits (do not copy)

- Its stack embeds AgentOS and has **no separate worker**; Edge OS needs separate execution/research workers and a future P27 producer.
- Its web probe checks only a TCP connect and its API probe only a listing route; these do not prove every Edge OS dependency or recurring health.
- Its API runs migrations on **each** startup; Edge OS should use an explicit serialized migration step plus its existing readiness schema check.
- Its deployment README's signer-qualification statement is dated and is not current wallet authority.

## Current primary documentation (Context7 resolve-first; official fallback)

- Docker: production Compose, deliberate restart policy, immutable image digests (`docker compose config --resolve-image-digests` / `--lock-image-digests`), `no-new-privileges`. Mounting the host Docker socket into a container gives it full host-daemon access and must not be exposed to the public API or model process.
- Docker firewall behavior: published container ports can bypass UFW; verify exposure externally rather than trusting an OS firewall rule.
- Coolify self-hosting: published minimum 2 cores / 2 GB / 10 GB for Coolify itself; colocated builds can exhaust the serving host.
- Next.js self-hosting: use a reverse proxy; public env values are baked into the build; `next start` or standalone output are both supported.
- Contabo: snapshots are **not** backups; separately stored VPS auto-backup exists on eligible plans, but plan availability and database recoverability remain unverified.

## How these lessons map to the Edge OS proposal

| Lesson | Edge OS target |
|---|---|
| Fail-closed config | Keep the application's production refusals; make the Compose/migration layer fail closed too (no fixture/local fallback). |
| Private services | Only the HTTPS proxy publishes traffic; PostgreSQL, workers and the runner have no public inbound port. |
| Scoped secrets | Postgres credentials only on the database service; web gets no DB/session secret; API gets `EDGE_OS_DATABASE_URL`; secrets live in the host secret store, never in image layers or the browser bundle. |
| Build-time vs runtime API address | `NEXT_PUBLIC_API_BASE_URL` at build time; a private runtime API origin for SSR if used. |
| Immutable, non-root images | Pinned base digests and `uv sync --frozen` / `npm ci`; non-root runtime user. |
| Fresh-database restore drill | Off-VPS `pg_dump -Fc` plus a restore into a fresh database that reads a known record back. |
| No Docker socket in public services | The trusted runner that manages job containers is a separate, narrowly scoped, separately qualified boundary. |

These are proposals. None is installed, configured or executed by this package.
