# Host decision packet (proposal only; nothing selected, purchased or deployed)

Task RELEASE-HOST-PREP-L4-20261012-01, issue edge-os-app/edge-os#48. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`, tree `31e71d47b63cf14686470d46e5469de59565d3f9`. Prepared 2026-10-12 in the `release-host-prep-worker` worktree.

Status: **proposal for a builder decision.** No host, plan, region, account or domain was selected. Nothing was created, purchased, configured or deployed. No provider was contacted. Every price below is a **first-party list price observed on 2026-10-12** and must be re-checked at purchase. Every capability marked UNKNOWN or NOT RUN is not claimed.

This packet reconciles the earlier [hosting proposal](../public-runtime/HOSTING_PROPOSAL.md) (Render candidate, Fly/Vercel alternatives) and the earlier [hosting and access assessment](../release-preparation/HOSTING_AND_ACCESS_ASSESSMENT.md) (Fly/Vercel arrangements) against the accepted code at the assigned base and against current first-party facts. It does not overwrite those documents; it corrects their stale or unconfirmed claims and adds the exact unmet decision gates.

## 1. Method and source dates

- Accepted code facts come from inspection of the assigned worktree at base `3e7ff8bd` (class: inspected source).
- Host prices and capabilities come from first-party pages fetched 2026-10-12: `render.com/pricing`, `render.com/docs/postgresql-creating-connecting`, `render.com/docs/free`, `render.com/docs/python-version`, `render.com/docs/node-version`, `fly.io/docs/about/pricing`, `fly.io/docs/postgres`, `vercel.com/pricing`. Context7 resolved `/websites/render` and `/websites/fly_io` first; the pages above then controlled.
- A price or capability that a first-party page did not state stays **UNKNOWN**. No third-party estimate is used as a first-party fact.
- **Correction to the earlier proposal:** Render's internal PostgreSQL connections **do** support TLS. The first-party page says internal connections "optionally support TLS using self-signed certificates" and that `sslmode=require` is the supported mode (`verify-ca` and `verify-full` are not supported for internal connections). The earlier "not confirmed" statement is superseded by this first-party fact. PostgreSQL 18 is a supported major version (13–18 available).

## 2. What the application needs (inspected source at base `3e7ff8bd`)

| Component | Inspected fact | Source |
|---|---|---|
| Web | Next.js 16.3.8, React 19.3.0, Node engines `>=24 <25` | `apps/web/package.json` |
| API | Python `>=3.14,<3.15`; FastAPI 0.142.2; Uvicorn 0.54.0 | `apps/api/pyproject.toml` |
| Persistence | PostgreSQL 18; SQLAlchemy 2.0.54 (sync); psycopg 3.3.6; Alembic 1.20.0; migration head `0010` | `apps/api/pyproject.toml`; `apps/api/migrations/versions/` |
| Auth | Privy access token (ES256), `Authorization: Bearer`, EC P-256 verification key; no cookie | `apps/api/src/edge_os_api/core/settings.py`; `main.py` |
| Health | `GET /healthz` (process, build SHA, started-at); `GET /readyz` (database + schema revision + keys + quota caps) | `apps/api/src/edge_os_api/main.py` |
| Migrations | `alembic upgrade head` and `alembic check`; forward-only; API refuses to start on a revision mismatch | `apps/api/migrations/env.py`; `core/database.py` |
| Database URL | `EDGE_OS_DATABASE_URL` must start `postgresql+psycopg://`; production needs `sslmode=require` or stricter and a non-loopback host | `core/settings.py` |
| Build identity | `EDGE_OS_BUILD_SHA` required in production; API sets `--host 0.0.0.0 --port $PORT` | `core/settings.py`; [HOSTING_PROPOSAL](../public-runtime/HOSTING_PROPOSAL.md) |
| Background worker | `python -m edge_os_api.execution.worker` — bounded loop, no port; `--once`/`--interval`; stops with exit code 3 on schema drift | `apps/api/src/edge_os_api/execution/worker.py` |
| Research worker | `python -m edge_os_api.research.investigation_jobs` — same bounded-loop contract | `apps/api/src/edge_os_api/research/investigation_jobs.py` |
| Browser API routing | The web calls `${NEXT_PUBLIC_API_BASE_URL}${path}`; no rewrite or proxy exists in `next.config.ts` | `apps/web/lib/api.ts` |
| Repository root | The API imports read `docs/contracts/p02` and `docs/contracts/p06` from the repository root at import; the uv lock is `apps/api/uv.lock` (not root) | `main.py`; `apps/api/uv.lock` |
| Production refusals | fixture/recorded/hermes_local interpreter modes; fixture wallet/execution; fixture effects; wildcard or non-HTTPS CORS; test Privy app id; missing build SHA; loopback database; missing `sslmode` | `core/settings.py` |
| Runtime limits | body cap 256 KiB; write rate default 600/owner/minute; research active-job cap default 10; SQL statement timeout default 30 s; job deadline ≤ 3600 s | `main.py`; `core/settings.py`; `RUNTIME_GUARDS.md` |

Two structural consequences:

1. The database holds durable state, so the host must keep data across deploys and restarts.
2. The two workers are long-running processes, not request-scoped functions. A function-only host does not fit them.

A third consequence applies to the browser path: the web reaches the API only through `NEXT_PUBLIC_API_BASE_URL`. A shared origin needs a routing layer the current application does not have; otherwise the API needs its own origin and the production CORS allow-list.

A fourth consequence applies to the qualified Hermes research runtime. The accepted architecture keeps bounded Hermes work in whole-process isolation (see §6, gate H2). This is a runtime control the platform must permit, not only an application setting.

## 3. Candidate reconciliation

| Candidate | Earlier claim | Current status at base `3e7ff8bd` |
|---|---|---|
| Render Blueprint | "One Blueprint file covers web services, background workers and PostgreSQL 18; managed backups/PITR; private-only database; **no provider-only outbound control**" | Still the smallest single-vendor fit. Internal DB TLS now confirmed (`sslmode=require`). Paying for 4 services + Postgres. Still **no enforced provider-only egress**. |
| Fly.io split/single container host | "Long-running containers, `[processes]` groups, managed Postgres with pooled and direct URLs" | Still valid. Fly has **no free tier**; Managed Postgres starts at $38/mo. Static egress IPs exist but are outbound address control, not an egress firewall. |
| Vercel web tier | "Vercel serves Next.js; functions are bounded-duration, not a persistent worker" | Still valid as a web tier only. Vercel has no always-on worker and no managed Postgres, so the API/workers/database need another vendor. |
| Static egress / provider allowlisting | Treated as a possible egress control | **Incorrect for a restriction.** Render dedicated outbound IPs, Fly static egress IPs and Vercel static IPs give a provider a stable address to allowlist. None of them restrict where the deployment may connect. They do not satisfy provider-only egress. |

## 4. Recommended smallest topology (proposal, not a selection)

Recommend a **single managed-PaaS topology on Render** with four compute services and one managed PostgreSQL 18, in one region, as the smallest documented arrangement that meets the accepted process list:

- `edge-os-api` — Python web service, repository root build, `uvicorn --factory edge_os_api.main:create_app`, health check `/readyz`.
- `edge-os-web` — Node web service, `rootDir: apps/web`, `npm ci && npm run build`, `npm start`.
- `edge-os-execution-worker` — Python background worker, `python -m edge_os_api.execution.worker`.
- `edge-os-research-worker` — Python background worker, `python -m edge_os_api.research.investigation_jobs`.
- `edge-os-db` — managed PostgreSQL 18, private network only (`ipAllowList: []`).

Proposed region: **Frankfurt (`fra`)**, because it is the region closest to the builder's current operating timezone among Render's five regions (Oregon, Ohio, Virginia, Frankfurt, Singapore). This is a proposal: choose another region before creation if most users are elsewhere. The region cannot change after creation.

Routing proposal: give the API its own HTTPS origin and set `NEXT_PUBLIC_API_BASE_URL` to it, then set `EDGE_OS_CORS_ALLOWED_ORIGINS` to the web origin. Do not rely on same-origin routing, because `apps/web/next.config.ts` has no rewrite or proxy.

Database connection proposal: use Render's **internal** URL, rewritten to the `postgresql+psycopg://` form with `?sslmode=require`. Use a **direct** (non-pooled) endpoint for migrations, because the migrations run session-scoped DDL. The API sets `statement_timeout` through the PostgreSQL startup `options`; some transaction-mode poolers refuse startup options, so a pooler needs its own check.

The Fly.io alternative (bounded, only where decisive): a single Fly app with `[processes]` for web/api/workers plus **Fly Managed Postgres**. This is reasonable when the builder wants regional Machines close to users and accepts a higher database baseline ($38/mo) and a separate unmanaged-versus-managed Postgres distinction. It is not cheaper than the Render proposal at this scale. Do not use unmanaged Fly Postgres for a release candidate: Fly's own documentation calls it "not a managed database".

## 5. Cost separation (first-party list prices, 2026-10-12)

All figures are **monthly USD, before tax**, and must be re-checked at purchase. Model, data, provider-request and backup costs are separated because the application caps requests and compute, not money at a provider.

### 5a. Recommended Render proposal (smallest usable sizes)

| Cost class | Item | Plan (proposal) | USD/month |
|---|---|---|---|
| Infrastructure | `edge-os-api` web service | `0.5c-512mb` | 7 |
| Infrastructure | `edge-os-web` web service | `0.5c-512mb` | 7 |
| Infrastructure | `edge-os-execution-worker` | `0.5c-512mb` | 7 |
| Infrastructure | `edge-os-research-worker` | `0.5c-512mb` | 7 |
| Infrastructure | Render Postgres 18 | `0.5c-1g` (1 GB included) | 19 |
| Storage (database) | Postgres storage beyond 1 GB | `$0.30/GB` | per GB |
| Storage (disk) | persistent disk, only if required | `$0.25/GB` | per GB |
| Bandwidth | outbound beyond workspace allowance | Hobby 5 GB incl., then `$0.15/GB` | per GB |
| Workspace | Render workspace plan | Hobby `$0` (Pro `$25`, Scale `$499`) | 0 |
| Backup | PITR window | Hobby 3 days; paid 7 days | included |
| **Infrastructure subtotal** | 4 services + Postgres | | **~47** |
| Model / data / provider requests | inference, Envio/QuickNode/Nansen | not stated by the application; provider-priced | **UNKNOWN** |
| Provider money limits | a hard spend cap at each provider | not offered by the host | **UNKNOWN / decision** |

Notes: `0.5c-512mb` gives 0.5 CPU and 512 MB per service. The research/execution workers and the API may need more than 1 GB Postgres RAM or larger compute under load; the correct sizes are a **REQUIRED_DECISION** after a hosted load check. Hobby lacks network-isolated environments and inbound IP rules for services (both need Pro); it also lacks horizontal autoscaling.

### 5b. Minimal Fly alternative (bounded comparison only)

| Cost class | Item | Plan (proposal) | USD/month |
|---|---|---|---|
| Infrastructure | web + api Machines | `shared-cpu-1x` 512 MB ×2 | ~7.4 |
| Infrastructure | execution + research worker Machines | `shared-cpu-1x` 256 MB ×2 | ~4.4 |
| Infrastructure | Fly Managed Postgres | Basic (1 GB RAM) | 38 |
| Storage | volume 10 GB | `$0.15/GB` | ~1.5 |
| Storage | MPG storage | `$0.28/GB` | per GB |
| Bandwidth | egress | `$0.02/GB` NA/EU | per GB |
| Backup | MPG backups | included | — |
| **Infrastructure subtotal** | | | **~51** |

Unmanaged Fly Postgres would lower the database line but is unsupported by Fly and is not proposed.

### 5c. Vercel (web tier only, if the builder wants a managed frontend)

Vercel Pro is `$20/mo` plus usage (Fluid compute, bandwidth, build minutes). Vercel cannot host the API, the two workers or the database, so a Vercel web tier always adds a second vendor and a second secret store.

## 6. Exact unmet decision gates

Each gate below is **blocked**, not "solved" by an application allow-list. A platform that lacks a required control stays blocked for the release claim.

| Gate | Required control | Status on the proposal | Minimal information to decide |
|---|---|---|---|
| H1 Provider-only egress | An enforced egress firewall or network policy that permits only named provider hosts | **UNAVAILABLE** on Render, Fly and Vercel. They offer outbound/static IP addresses (address control), not connection restriction. | Decide one: (a) a host with an enforced egress firewall (for example a cloud VPC with egress rules, needing its own first-party check); (b) an allowlisting forward proxy as a private service plus one application HTTP client that refuses non-provider hosts (weaker: code that ignores the proxy is not blocked by the platform); or (c) accept unrestricted egress for a named provider set as a recorded risk decision. |
| H2 Qualified isolated Hermes job runtime | Whole-process isolation for bounded Hermes work: one fresh process per job, an owned output/evidence directory, no shared mutable memory, no signing credentials, no host Docker socket, no privileged database connection | **NOT RUN / NOT AVAILABLE.** The accepted architecture requires it (Hermes deployment notes), and lane-1 Hermes job support is still active and unaccepted at this base. Production currently accepts only the fixture interpreter. | Confirm the qualified Hermes job-service output, its process-isolation mechanism and its resource supervision. Decide whether the host must run containers (a Docker-capable host) or whether a Python-process-per-job isolation is sufficient for the accepted profile. |
| H3 Owned supervision and cleanup | Bounded job timeout, cancellation, cleanup after each job, and no cross-tenant state reuse | **NOT RUN.** The application has a bounded worker loop and job deadlines; the Hermes job runtime supervision is unqualified (lane 1). | The lane-1 Hermes support design, its cleanup timing and its fault fixtures. |
| H4 Storage and locks | Durable per-owner storage; advisory-lock behavior under the host's connection model | **NOT RUN on host.** Locally, jobs take advisory locks and a fixed quota lock order. Poolers can change session semantics. | Confirm the host's connection model (direct vs pooled) and that advisory locks and session-scoped DDL work through it. The proposal uses a direct connection. |
| H5 Database TLS / pooler | `sslmode=require` or stricter; session-scoped DDL for migrations; startup `options` reach the server | **RENDER: CONFIRMED for internal TLS** (`sslmode=require`, self-signed). Direct-versus-pooled migration path is **UNRESOLVED**; a pooler that drops startup `options` would break the statement timeout. | Confirm the internal URL supports `sslmode=require` (done), and choose direct for migrations. If a pooler is used, verify startup `options` pass through. |
| H6 Startup versions | Host offers Python `3.14.x` in `>=3.14,<3.15` and Node `24.x` in `>=24 <25` | Render default Python `3.14.3` (any released version from 3.7.3 settable); default Node `24.21.0`. The proposal pins `PYTHON_VERSION=3.14.4` and `NODE_VERSION=24.13.1`. | Confirm `3.14.4` and `24.13.1` are offered at creation time, or pin the nearest offered patch in the same minor line and re-run the checks. |
| H7 Resource and job concurrency | Correct per-service CPU/RAM and worker concurrency for the accepted load | **NOT RUN.** No hosted load check exists. | A hosted load check after the exact sizes are chosen. |
| H8 Provider money limits | A hard spending cap at each external provider | **NOT provided by the host.** Application quotas cap requests and compute, not money at a provider. | The builder sets provider-side billing limits (for example at the model and data providers) and records them. |
| H9 Abuse protection in front of the API | Bot/IP limits before authentication | Render Free/paid offer DDoS mitigation; service inbound IP rules need a Scale/Pro workspace. The application rate limit is per signed-in owner only. | Decide whether the public launch needs an inbound IP rule or a WAF, and on which workspace plan. |
| H10 Backup restore rehearsal on the host | A hosted backup and point-in-time restore rehearsal | **NOT RUN.** Only the local rehearsal exists (`RESTORE_ROLLBACK_RUNBOOK.md`). | Run the restore rehearsal on the chosen host before public use. |
| H11 Log retention and access | Host log retention matching `RETENTION_DELETION_SUPPORT.md` | Render Hobby retains logs 7 days; Pro 14; Scale 30. | Confirm the retention choice matches the public retention statement. |
| H12 Dependency advisories | Resolve the wallet-SDK advisories before public exposure | `ADVISORY_ASSESSMENT.md`: 25 advisories, all transitive through the wallet SDK; no lockfile change made. | Controller disposition of the advisory recommendations. |

## 7. Bounded recommendation

For a local/staged release candidate with no real provider enabled, the Render proposal above is the smallest documented topology and the least operative surface. It fits the four-process list, gives managed PostgreSQL 18 with confirmed internal TLS and PITR, and needs one secret store.

The proposal is **not sufficient for the full public release claim**, for one decisive reason: no candidate host offers enforced provider-only egress (H1), and the qualified Hermes job runtime (H2) is not yet available. Do not present H1 or H2 as solved.

When the release enables a real provider, one of the H1 decisions must be recorded first. If it selects a cloud VPC with egress rules, the topology changes to that provider and this packet needs an update with its own first-party check.

New product or architecture choices (a different enforcement route, a different provider, an egress acceptance decision, or a Hermes isolation mechanism) are builder decisions. This packet selects none of them.

## 8. Sources

- Render: `https://render.com/pricing`, `https://render.com/docs/postgresql-creating-connecting`, `https://render.com/docs/free`, `https://render.com/docs/python-version`, `https://render.com/docs/node-version` — accessed 2026-10-12.
- Fly.io: `https://fly.io/docs/about/pricing`, `https://fly.io/docs/postgres` — accessed 2026-10-12.
- Vercel: `https://vercel.com/pricing` — accessed 2026-10-12.
- Context7: `/websites/render`, `/websites/fly_io` — resolved and queried 2026-10-12.
- Accepted code and prior documents: the assigned worktree at base `3e7ff8bd`; `docs/qualification/public-runtime/HOSTING_PROPOSAL.md`; `docs/qualification/release-preparation/HOSTING_AND_ACCESS_ASSESSMENT.md`; `docs/research/HERMES_DEPLOYMENT_AND_USER_TENANCY_2026-10-02.md`; `docs/research/HERMES_AGENTOS_DEPLOYMENT_RESEARCH_2026-10-12.md`.

## 9. Evidence classification

- **Inspected source:** the component, health, migration, URL, routing and limit rows in §2, and the production refusals.
- **First-party host documentation:** §3, §4 and the prices in §5, observed 2026-10-12.
- **UNKNOWN / REQUIRED_DECISION:** H1–H12 in §6.
- **NOT RUN:** every hosted check in §6 (no host exists).
