# Hosting and access assessment

Task OC-P41-PREP-20261010-01, issue #48. Prepared 2026-10-10 against base `5689e1d6e71edc956941f33e61488c5d03d37808`. Repaired 2026-10-10 after gate review 1/3 (findings B1 and B2).

Scope: assessment only. This document recommends an arrangement. It selects nothing, buys nothing, deploys nothing and configures no account. Every arrangement below is **UNTESTED** for this application.

## 1. What the application actually needs

The facts below come from the inspected repository at the accepted base. They are class **inspected source**, not platform documentation.

| Component | Inspected fact | Source |
|---|---|---|
| Web | Next.js 16.3.8, React 19.3.0, Node `>=24 <25` | `apps/web/package.json` |
| API | Python `>=3.14,<3.15`, FastAPI 0.142.2, Uvicorn 0.54.0 | `apps/api/pyproject.toml` |
| Persistence | PostgreSQL 18.6 (`postgres:18.6-trixie`), SQLAlchemy 2.0.54 (sync), psycopg 3.3.6, Alembic 1.20.0 | `apps/api/pyproject.toml`; [P01 profile](../../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md) |
| Auth | Privy access token (ES256), `Authorization: Bearer` header, no cookie | [P01 profile](../../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md) |
| Health | `GET /healthz` (process only), `GET /readyz` (database plus schema revision plus key) | [P01 profile](../../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md) |
| Migrations | `alembic upgrade head` runs as a separate step before the API. The API refuses to start on a revision mismatch. Forward-only. | [P01 profile](../../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md); `apps/api/migrations/env.py` |
| Worker | A future persistent worker. It shares the database and holds its own service credentials. Its lifecycle is not decided. | [P01 profile](../../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md); [build brief](../../EDGE_OS_BUILD_BRIEF.md) |
| Browser API routing | The web calls `${NEXT_PUBLIC_API_BASE_URL}${path}`. When that variable is empty, `/v1` paths go to the frontend origin. No rewrite, proxy or gateway exists in `next.config.ts`. | `apps/web/lib/api.ts` lines 19 and 32; `apps/web/next.config.ts` |
| Database URL form | The API and the migrations read `EDGE_OS_DATABASE_URL` and require the `postgresql+psycopg://` form. | `apps/api/migrations/env.py` lines 17 to 21; `apps/api/src/edge_os_api/core/settings.py` lines 72 to 81 |
| Test recipe | `scripts/p03/verify_run.py` starts and removes its own PostgreSQL container. It needs Docker, Python 3.14, `uv` and Node 24. It is a local verification recipe, not a deployment. | [verify-edge-os skill](../../../.agents/skills/verify-edge-os/SKILL.md) |

Two consequences shape every arrangement:

1. The database holds durable state, so the host must keep its data across deploys and restarts.
2. The future worker is a long-running process, not a request-scoped function.

A third consequence applies to the browser path: the web reaches the API only through `NEXT_PUBLIC_API_BASE_URL`. Same-origin API access needs a routing layer that the current application does not have.

## 2. Production concerns to satisfy

| Concern | Requirement | Status |
|---|---|---|
| Persistent state | A durable PostgreSQL 18 instance that survives redeploys and restarts | NOT RUN |
| Migrations | A controlled `alembic upgrade head` step before each API start, with no auto-migrate, over a connection suitable for session-scoped DDL | NOT RUN |
| Application database connection | The API connects through a pooled endpoint through `EDGE_OS_DATABASE_URL` in the `postgresql+psycopg://` form | NOT RUN |
| Migration database connection | The migration step uses the direct (non-pooled) endpoint. A host-injected plain `DATABASE_URL` does not satisfy the application configuration. | NOT RUN |
| Production auth and owner isolation | Real Privy app ID and Dashboard verification key; every owner-scoped query derives `owner_id` from the verified principal; CORS allow-list with no `*` and `https://` origins in production | NOT RUN; the code path exists, but no real-provider check (R1) has run |
| API routing | The web reaches the API through `NEXT_PUBLIC_API_BASE_URL`. Same-origin access needs a separately qualified reverse proxy or application rewrite/gateway. | NOT RUN and NOT CONFIGURED |
| Secrets | `EDGE_OS_DATABASE_URL`, `EDGE_OS_PRIVY_VERIFICATION_KEY` and the other `EDGE_OS_*` values live in the host secret store, never in source or model input | NOT RUN |
| TLS | Privy requires HTTPS for token transit. Production CORS origins must be `https://`. | NOT RUN |
| Health and restart | The host probes `/readyz`; a failing database or a schema mismatch returns 503 | NOT RUN |
| External-service limits | In-memory, no outbound provider, wallet or RPC call at this stage | Inspected: the current app calls no provider |
| Judge access | A public live URL on Monad mainnet or testnet, plus access instructions and any judge test credentials | NOT RUN |

The current application depends on no external service at runtime. That removes one hosting risk but does not change the live-product requirement, which needs a deployed Monad-connected product.

## 3. Two practical arrangements

Both arrangements come from current official platform documentation. Neither is configured or tested for this application. Exact official source URLs are in section 7.

### Arrangement A: split managed (web on Vercel, API and worker on a container host)

The Next.js web runs on Vercel. The FastAPI API and the future worker run as containers on a container host. PostgreSQL runs as a managed database.

| Item | Official-doc fact | Source |
|---|---|---|
| Web | Vercel serves Next.js 16 App Router projects and sets environment variables per environment | Vercel environment variables |
| Request functions | Vercel functions carry a bounded `maxDuration`; they suit request work, not a persistent worker | Vercel functions |
| API and worker | A container host runs long-lived processes | Fly.io process groups |
| Worker | `[processes]` in `fly.toml` separates process groups; each group scales on its own | Fly.io process groups |
| Database | A managed PostgreSQL attaches to the app with a pooled connection URL and also exposes a direct URL | Fly.io Managed Postgres client configuration |

Fit: the web tier is static and request-scoped, so a managed frontend platform fits it. The API and worker need a long-running container host. The cost is two platforms and two secret stores.

Routing: `NEXT_PUBLIC_API_BASE_URL` names the API origin on the second platform. Cross-origin calls then depend on the API CORS allow-list. This arrangement does not use same-origin routing.

### Arrangement B: single container host

Web, API and worker run as separate process groups on one container host. PostgreSQL runs as a managed database.

| Item | Official-doc fact | Source |
|---|---|---|
| Web, API, worker | One `fly.toml` carries separate process groups | Fly.io process groups |
| Database | Managed PostgreSQL attaches with a pooled connection URL; a direct URL exists for migrations and session-scoped work | Fly.io Managed Postgres client configuration |
| State | Persistent volumes are available for stateful processes | Fly.io Managed Postgres; Fly.io process groups |

Fit: one platform, one secret store, and one place to run the migration step.

Routing: separate process groups are separate Machines with their own service ports. Fly Proxy balances Machines that expose the requested port. It does not select a process by HTTP path. Sharing one host therefore does **not** by itself give the web and API a shared origin. Same-origin access needs a separately qualified reverse proxy or an application rewrite/gateway, neither of which exists in `apps/web/next.config.ts`. The alternative is a distinct API origin with the production CORS allow-list. Routing and the multiple-image or multiple-app boundary are **UNTESTED and UNSELECTED**.

## 4. Comparison

| Concern | Arrangement A (split) | Arrangement B (single host) |
|---|---|---|
| Persistent state | Managed PostgreSQL | Managed PostgreSQL |
| Migrations | Direct endpoint, run in the API or worker pipeline | Direct endpoint, run as a release step on the one host |
| Application connection | Pooled endpoint via `EDGE_OS_DATABASE_URL` | Pooled endpoint via `EDGE_OS_DATABASE_URL` |
| Worker | Container process group | Container process group |
| API routing | Distinct API origin via `NEXT_PUBLIC_API_BASE_URL`; CORS allow-list required | Same origin needs a reverse proxy or app rewrite/gateway; otherwise distinct origin plus CORS |
| Secrets | Two stores | One store |
| Operational surface | Two platforms | One platform |
| Cost driver | Two platform bills | One platform bill |

## 5. Recommendation

Recommend **Arrangement B** (one container host with separate web and worker process groups, plus a managed PostgreSQL), for three reasons:

1. The future worker is a long-running process, so the host must run containers anyway. Arrangement A needs that host regardless.
2. One host gives one migration step and one secret store, which reduces the startup-failure surface that `P01` describes.
3. One host can host a reverse proxy or application gateway that gives the web and API a shared origin, subject to a separate routing qualification. Until that routing is qualified or configured, use a distinct API origin with the CORS allow-list.

Arrangement A is the reasonable alternative when the builder wants a managed frontend platform and accepts the second platform and cross-origin calls.

This recommendation selects no vendor, plan, region or price. The builder approves the host, the cost and the exact deployment. `P01` question Q10 records host selection for the API, web, database and worker as a builder decision.

## 6. Evidence classes and limits

- **Inspected source:** stack pins, env names, health endpoints, migration rule, database URL form, browser API routing and the worker boundary.
- **Platform documentation:** process groups, managed Postgres pooled and direct endpoints, and persistent volumes (Fly.io); environment variables and bounded function duration (Vercel).
- **UNTESTED:** every arrangement for this application. No container was built, no route proxied, no database migrated, no secret stored, no probe configured, no deploy performed.

Unresolved items before any deployment:

- Exact host, plan, region and cost. The builder decides.
- The API-routing choice: a reverse proxy or application gateway for same-origin access, or a distinct API origin with the CORS allow-list. UNTESTED and UNSELECTED.
- Managed-service PostgreSQL 18 compatibility. Current platform documentation does not establish it. UNRESOLVED.
- The migration connection: the operator supplies the direct endpoint through `EDGE_OS_DATABASE_URL` in the `postgresql+psycopg://` form. The exact endpoint choice is UNTESTED.
- Session-dependent future worker operations. They need explicit connection and pool qualification. NOT RUN.
- The production Privy app, its Dashboard verification key and the real-token check (R1). The builder authorizes.
- The worker lifecycle and its service credentials. A later ticket decides.
- Whether the repository becomes public, and the exact judge access path.

## 7. Sources

- [P01 application, authentication and storage profile](../../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md), accessed 2026-10-10.
- [Backend package layout](../../implementation/BACKEND_PACKAGE_LAYOUT.md), accessed 2026-10-10.
- `apps/api/pyproject.toml`, `apps/api/migrations/env.py`, `apps/api/src/edge_os_api/core/settings.py`, `apps/web/package.json`, `apps/web/next.config.ts`, `apps/web/lib/api.ts`, `.agents/skills/verify-edge-os/SKILL.md`, accessed 2026-10-10.
- Fly.io process groups: https://docs.fly.io/launch/processes
- Fly.io Managed Postgres client configuration (pooled and direct endpoints): https://docs.fly.io/postgres/client-configuration
- Fly.io Managed Postgres overview: https://docs.fly.io/postgres
- Vercel functions (bounded duration): https://vercel.com/docs/functions
- Vercel environment variables: https://vercel.com/docs/environment-variables
