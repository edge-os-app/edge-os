# Hosting proposal (not selected, not purchased)

Status: proposal for a builder decision. Nothing was bought, created or deployed. No provider account was opened or contacted.

Sources:

- Render's first-party documentation through Context7 (`/websites/render`): Blueprint `render.yaml` (regions, `rootDir`, `ipAllowList`, `postgresMajorVersion`), web-service port binding (`0.0.0.0`, `PORT` default 10000), the FastAPI start command, uv detection from `uv.lock`, `PYTHON_VERSION`/`NODE_VERSION`, health checks, private networking, `preDeployCommand`, outbound IP addresses and dedicated IPs, platform features by plan, Postgres backups and point-in-time recovery, high availability. Pages: render.com/docs/web-services, /deploy-fastapi, /blueprint-spec, /regions, /private-network, /monorepo-support, /uv-version, /outbound-ip-addresses, /dedicated-ips, /platform-features-by-plan.
- Prices come from third-party summaries (listed at the end). They are **estimates to confirm on render.com/pricing**. Render's own pricing page did not return figures to the search tool.

## Why Render as the candidate

- One Blueprint file describes web services, background workers and PostgreSQL. This matches the application's processes.
- Managed PostgreSQL with PostgreSQL 18, backups, and point-in-time recovery on paid plans.
- A database can be private-only (`ipAllowList: []`): only services in the same workspace and region reach it.
- Limit: Render has no provider-only outbound control (see "Network controls").
- A health check path gates each deploy, and a pre-deploy command runs migrations before the new version takes traffic.

Alternatives (Railway, Fly.io, a container platform with a managed database) were not assessed in depth. The same process list applies to them; their network controls need their own first-party check.

## Topology

All five resources share one region, **`frankfurt`**. Render requires this for private networking, and the region cannot be changed after creation. The choice is a proposal: choose `oregon`, `ohio`, `virginia` or `singapore` instead before creation if most users are elsewhere.

Blueprint sketch (`render.yaml` at the repository root, for review only; no file is added to the repository and nothing is created):

```yaml
services:
  - type: web
    name: edge-os-api
    runtime: python
    region: frankfurt
    # No rootDir: the API reads repository-root files (docs/contracts/p02, docs/contracts/p06) at import.
    buildCommand: pip install uv==0.12.16 && cd apps/api && uv sync --frozen
    preDeployCommand: cd apps/api && uv run --frozen alembic upgrade head    # paid compute plans only
    startCommand: cd apps/api && EDGE_OS_BUILD_SHA=$RENDER_GIT_COMMIT uv run --frozen uvicorn --factory edge_os_api.main:create_app --host 0.0.0.0 --port $PORT
    healthCheckPath: /readyz
    envVars:
      - key: PYTHON_VERSION
        value: 3.14.4                      # pyproject requires >=3.14,<3.15; local checks ran on 3.14.4
      - fromGroup: edge-os-runtime
  - type: worker
    name: edge-os-execution-worker
    runtime: python
    region: frankfurt
    buildCommand: pip install uv==0.12.16 && cd apps/api && uv sync --frozen
    startCommand: cd apps/api && EDGE_OS_BUILD_SHA=$RENDER_GIT_COMMIT uv run --frozen python -m edge_os_api.execution.worker
    envVars: [{ key: PYTHON_VERSION, value: 3.14.4 }, { fromGroup: edge-os-runtime }]
  - type: worker
    name: edge-os-research-worker
    runtime: python
    region: frankfurt
    buildCommand: pip install uv==0.12.16 && cd apps/api && uv sync --frozen
    startCommand: cd apps/api && EDGE_OS_BUILD_SHA=$RENDER_GIT_COMMIT uv run --frozen python -m edge_os_api.research.investigation_jobs
    envVars: [{ key: PYTHON_VERSION, value: 3.14.4 }, { fromGroup: edge-os-runtime }]
  - type: web
    name: edge-os-web
    runtime: node
    region: frankfurt
    rootDir: apps/web
    buildCommand: npm ci && npm run build  # NEXT_PUBLIC_* values are read at build time
    startCommand: npm start -- --hostname 0.0.0.0 --port $PORT
    envVars:
      - key: NODE_VERSION
        value: 24.13.1                     # package.json engines >=24 <25; local checks ran on 24.13.1
      - key: NEXT_PUBLIC_API_BASE_URL
        sync: false                        # https URL of edge-os-api
      - key: NEXT_PUBLIC_PRIVY_APP_ID
        sync: false
databases:
  - name: edge-os-db
    region: frankfurt
    postgresMajorVersion: "18"
    ipAllowList: []                        # private network only: no public inbound connections
# Put these resources in their own project environment with `networking: isolation: enabled`, so other
# services in the workspace cannot reach them over the private network (the default is disabled).
```

Command check against the repository and Render documentation:

- **Binding:** Render requires every web service to bind to `0.0.0.0` and recommends the `PORT` variable (default 10000). Uvicorn's defaults are `127.0.0.1:8000`, so the API command sets `--host 0.0.0.0 --port $PORT`. `next start` binds to `0.0.0.0` by default and reads `PORT`; the command still states both.
- **Repository root:** the Python services run from the repository root (no `rootDir`) and `cd apps/api` in each command. The API imports read `docs/contracts/p02/check_contract.py` and `docs/contracts/p06` from the root at import time, and Render makes files outside `rootDir` unavailable. The web service may use `rootDir: apps/web`, because it reads nothing outside that folder.
- **uv:** Render adds uv only when the service root holds a `uv.lock`. The repository root has none (the lock is `apps/api/uv.lock`), so the build installs the locally used version, `uv==0.12.16`.
- **Build identity:** production refuses to start without `EDGE_OS_BUILD_SHA`. Each command sets it from Render's `RENDER_GIT_COMMIT`, so it never goes stale after a deploy.
- **Database URL:** Render's internal URL has the form `postgresql://USER:PASSWORD@INTERNAL_HOST:PORT/DATABASE`. The API needs the driver prefix `postgresql+psycopg://` and `?sslmode=require` or stricter, so the value is set by hand, not copied unchanged. Whether Render's internal connections accept TLS is **not confirmed**. If they do not, production refuses to start, and that rule needs a recorded decision.
- **Deploy order:** during a deploy that adds a migration, running workers stop with exit code 3 when the schema head changes, and the old API answers `/readyz` 503 `schema_drift` until the new version takes over. Render restarts the workers, which then run the new code. Plan deploys with a short pause of research and evaluation work.
- **App factory:** `edge_os_api.main:create_app` is the factory that the test harness starts (`scripts/p03/harness.py`, `uvicorn … --factory`).
- **Workers:** both modules accept `--once` and otherwise run a bounded loop. Background workers bind no port.
- **Migrations:** the pre-deploy command runs migrations before a new API version takes traffic. On a free plan, which has no pre-deploy command, run migrations as a one-off job before the deploy.
- **Runtime versions:** `PYTHON_VERSION` and `NODE_VERSION` pin the versions that the local checks used. Confirm before creation that Render offers Python 3.14.4 and Node 24.13.1; if not, use the nearest offered patch release in the same minor line and rerun the checks.
- **Settings:** shared `EDGE_OS_*` settings go in the environment group `edge-os-runtime`; secrets are set in the dashboard, never in the file.

## Network controls

| Direction | Control | Status |
|---|---|---|
| Inbound to PostgreSQL | `ipAllowList: []`: only same-region services on the private network connect | Platform feature (Blueprint spec) |
| Inbound to API and web | public HTTPS through Render; API CORS allows only the web origin; IP allow lists for web services need a Scale workspace | Platform feature; IP rules not proposed |
| Outbound from API and workers (provider-only egress) | **Not available on Render.** The documentation offers outbound IP ranges, dedicated outbound IPs (Pro workspace) and third-party static-IP proxies. These help a provider allowlist this deployment; they do not restrict where the deployment can connect. | **UNAVAILABLE** in this topology |

Current consequence: none. Production refuses every provider mode (`EDGE_OS_EXECUTION_MODE`, `EDGE_OS_WALLET_PROVIDER` and `EDGE_OS_RESEARCH_HISTORY_MODE` must be `unavailable`), so the application makes no provider call.

Before public qualification with any real provider, one of these decisions is required (none is verified here):

1. A host with an enforced egress firewall or network policy, such as a cloud VPC with egress rules. This needs its own first-party documentation check.
2. On Render, an allowlisting forward proxy as a private service, plus one application HTTP client that refuses hosts outside the provider list. This is weaker: code that ignores the proxy is not blocked by the platform.
3. Accept unrestricted egress for a named provider set, as a recorded risk decision.

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

- Provider-only outbound access: not offered by Render (see "Network controls"); a decision is required before any real provider is enabled.
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
