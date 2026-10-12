# Hosting proposal (not selected, not purchased)

Status: proposal for a builder decision. Nothing was bought, created or deployed. No provider account was opened or contacted.

Sources:

- Render's first-party documentation through Context7 (`/websites/render`): Blueprint `render.yaml`, health checks, private networking, `ipAllowList`, `preDeployCommand`, Postgres backups and point-in-time recovery, high availability.
- Prices come from third-party summaries (listed at the end). They are **estimates to confirm on render.com/pricing**. Render's own pricing page did not return figures to the search tool.

## Why Render as the candidate

- One Blueprint file describes web services, background workers and PostgreSQL. This matches the application's processes.
- Managed PostgreSQL with PostgreSQL 18, backups, and point-in-time recovery on paid plans.
- A database can be private-only (`ipAllowList: []`): only services in the same workspace and region reach it.
- A health check path gates each deploy, and a pre-deploy command runs migrations before the new version takes traffic.

Alternatives (Railway, Fly.io, a container platform with a managed database) were not assessed in depth. The same process list and controls apply to them.

## Topology

| Service | Render type | Command | Notes |
|---|---|---|---|
| `edge-os-web` | web service (Node) | `npm ci && npm run build` / `npm start` | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_PRIVY_APP_ID` |
| `edge-os-api` | web service (Python) | `uv sync --frozen` / `uv run uvicorn --factory edge_os_api.main:create_app` | `healthCheckPath: /readyz`; `preDeployCommand: uv run --frozen alembic upgrade head` (needs a paid plan) |
| `edge-os-execution-worker` | background worker | `uv run python -m edge_os_api.execution.worker` | exits 3 on schema drift; the platform restarts it |
| `edge-os-research-worker` | background worker | `uv run python -m edge_os_api.research.investigation_jobs` | same |
| `edge-os-db` | PostgreSQL 18 | — | `ipAllowList: []`, same region as the services |

Shared settings belong in one environment group. Secrets (`EDGE_OS_DATABASE_URL`, `EDGE_OS_PRIVY_VERIFICATION_KEY`) are set as platform secrets, never in the Blueprint file.

## Required production settings

- `EDGE_OS_ENV=production`, `EDGE_OS_BUILD_SHA=<commit>`.
- `EDGE_OS_DATABASE_URL` pointing at the private database with `sslmode=require` or stricter.
- `EDGE_OS_CORS_ALLOWED_ORIGINS=https://<web host>`.
- `EDGE_OS_PRIVY_APP_ID` (not the test id) and `EDGE_OS_PRIVY_VERIFICATION_KEY`.
- `EDGE_OS_EXECUTION_MODE`, `EDGE_OS_WALLET_PROVIDER` and `EDGE_OS_RESEARCH_HISTORY_MODE` stay `unavailable`. The API refuses anything else in production.
- Quota and rate values: `EDGE_OS_RESEARCH_BUDGET_*`, `EDGE_OS_USAGE_GLOBAL_*`, `EDGE_OS_WRITE_RATE_PER_MINUTE`, `EDGE_OS_RESEARCH_MAX_ACTIVE_JOBS`. They are frozen at first use, so choose them before the first owner arrives.

## Estimated monthly cost (to confirm)

| Item | Plan (estimate) | USD / month |
|---|---|---|
| 2 web services | Starter (0.5 CPU, 512 MB) | ~14 |
| 2 background workers | Starter | ~14 |
| PostgreSQL | Basic-1gb (PITR on paid plans) | ~19–20 |
| Storage | ~10 GB at ~0.30/GB | ~3 |
| **Total** | | **~50**, before bandwidth and a workspace plan |

High availability for PostgreSQL needs a higher workspace tier and is not in this estimate.

## Residual controls the platform does not give

- Provider spending limits for any later real provider: the application quotas cap requests and compute, not money at a provider.
- Abuse protection in front of the API (bot or IP limits). The application rate limit is per signed-in owner only.
- A backup restore rehearsal on the platform. Only the local rehearsal exists (`RESTORE_ROLLBACK_RUNBOOK.md`).
- Log retention and access rules on the platform. They must match `RETENTION_DELETION_SUPPORT.md`.
- Alerting for `/readyz` failures, worker exit code 3 and `quota_cap_mismatch`.
- Dependency advisories in the wallet SDK (`ADVISORY_ASSESSMENT.md`).
- Quota throughput under load: every reservation and settlement locks the same two GLOBAL rows (one lock order, no deadlock found), so research starts are serialized. Acceptable at the planned scale; measure in a hosted load check.
- Connection poolers: the API sets `statement_timeout` through the PostgreSQL startup `options`. Some transaction-mode poolers refuse startup options. The proposed topology connects directly to private PostgreSQL; a pooler needs its own check.

## Price sources (third-party, to confirm)

- https://makerkit.dev/pricing-calculator/render
- https://kuberns.com/blogs/render-pricing/
- https://costbench.com/software/developer-tools/render/
- https://servercompass.app/blog/render-pricing-is-it-worth-it
- https://www.kunalganglani.com/blog/render-vs-railway-2026
