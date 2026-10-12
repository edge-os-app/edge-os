# Host decision packet (Contabo VPS target; proposal only; nothing installed or deployed)

Task RELEASE-HOST-PREP-L4-20261012-01, issue edge-os-app/edge-os#48. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`, tree `31e71d47b63cf14686470d46e5469de59565d3f9`. Prepared 2026-10-12. Amendment A2 (`.scratch/rhp-a2.md` SHA256 `769e8269…`) supersedes the earlier Render/Fly/Vercel host-choice recommendation: the builder selected an **existing Contabo VPS** as the hosting target for preparation.

Status: **proposal for a builder decision.** Nothing was installed, configured, purchased or deployed. No SSH, account, API, server, DNS, credential or paid add-on action happened. Every price or fact that a first-party page did not state stays `UNKNOWN`.

The Render/Fly/Vercel comparison from the earlier revision is retained only as dated context in §7; it is no longer an unresolved target selection.

## 1. Method and source dates

- Accepted code facts come from inspection of the assigned worktree at base `3e7ff8bd` (class: inspected source).
- The Contabo target and the portable prior-project lessons come from the frozen inputs named by the A2 index: `.scratch/rhp-a2.md` (`769e8269…`), `docs/research/EDGE_OS_CONTABO_DEPLOYMENT_RESEARCH_2026-10-12.md` (`84531688…`), `.scratch/contabo-reference-identities-20261012.json` (`b44da435…`). All three hashes verified.
- Prior-project lessons are recorded in [PRIOR_PROJECT_DEPLOYMENT_PATTERNS.md](PRIOR_PROJECT_DEPLOYMENT_PATTERNS.md), with the exact reference HEADs and file hashes.
- Current primary documentation was kept through Context7 resolve-first with official fallback (Docker production Compose, Docker daemon security, Docker firewall behavior, Coolify self-hosting, Next.js self-hosting, Contabo snapshots/auto-backup).

## 2. What the application needs (inspected source at base `3e7ff8bd`)

| Component | Inspected fact | Source |
|---|---|---|
| Web | Next.js 16.3.8, React 19.3.0, Node engines `>=24 <25` | `apps/web/package.json` |
| API | Python `>=3.14,<3.15`; FastAPI 0.142.2; Uvicorn 0.54.0 | `apps/api/pyproject.toml` |
| Persistence | PostgreSQL 18; SQLAlchemy 2.0.54 (sync); psycopg 3.3.6; Alembic 1.20.0; migration head `0010` | `apps/api/pyproject.toml`; `apps/api/migrations/versions/` |
| Auth | Privy access token (ES256), `Authorization: Bearer`, EC P-256 verification key; no cookie | `core/settings.py`; `main.py` |
| Health | `GET /healthz` (process, build SHA, started-at); `GET /readyz` (database + schema revision + keys + quota caps) | `main.py` |
| Migrations | `alembic upgrade head` and `alembic check`; forward-only; API refuses to start on a revision mismatch | `apps/api/migrations/env.py`; `core/database.py` |
| Database URL | `EDGE_OS_DATABASE_URL` must start `postgresql+psycopg://`; production needs `sslmode=require` or stricter and a non-loopback host | `core/settings.py` |
| Build identity | `EDGE_OS_BUILD_SHA` required in production; the container is started with `--host 0.0.0.0 --port $PORT` (an operator start command in the Compose proposal, not a code setting) | `core/settings.py`; HOST_QUALIFICATION_RUNBOOK Stage 3 |
| Background worker | `python -m edge_os_api.execution.worker` — bounded loop, no port; `--once`/`--interval`; stops with exit code 3 on schema drift | `execution/worker.py` |
| Research worker | `python -m edge_os_api.research.investigation_jobs` — same bounded-loop contract | `research/investigation_jobs.py` |
| Browser API routing | The web calls `${NEXT_PUBLIC_API_BASE_URL}${path}` at build time; no rewrite or proxy exists in `next.config.ts` | `apps/web/lib/api.ts` |
| Production refusals | fixture/recorded/hermes_local interpreter modes; fixture wallet/execution; fixture effects; wildcard or non-HTTPS CORS; test Privy app id; missing build SHA; loopback database; missing `sslmode` | `core/settings.py` |
| Runtime limits | body cap 256 KiB; write rate default 600/owner/minute; research active-job cap default 10; SQL statement timeout default 30 s; job deadline ≤ 3600 s | `main.py`; `core/settings.py`; `core/request_schemas.py` |

Two structural consequences:

1. The database holds durable state, so the host must keep data across deploys and restarts.
2. The two workers are long-running processes, not request-scoped functions.

A third consequence applies to the browser path: the web reaches the API only through `NEXT_PUBLIC_API_BASE_URL`; a shared origin needs a routing layer the application does not have, so the API needs its own HTTPS origin and the production CORS allow-list.

A fourth consequence applies to the qualified Hermes research runtime: the accepted architecture keeps bounded Hermes work in whole-process isolation (§6, gate H2). The host must permit that control.

## 3. Host target and topology (proposal, not a selection of plan/resources)

Target: the builder's **existing Contabo VPS**. Its CPU, RAM, disk, OS, installed services and domain are **unknown** and stay unknown until the builder supplies them or a separately authorized inspection runs (gate H13).

Proposed orchestration: **Docker Compose** on the VPS.

- If **Coolify already runs** on the VPS, use its Compose deployment and TLS proxy; do not install or reconfigure Coolify as part of this preparation.
- Otherwise, **plain Compose plus a reverse proxy** is the smaller starting option.
- Neither requires an AgentOS migration.

The topology is separate managed processes (containers), one responsibility each:

| Service | Image | Public inbound | Notes |
|---|---|---|---|
| `proxy` | reverse proxy with TLS (only service that publishes traffic) | 443 (and 80 for redirect) | Fronts only `web` and `api` |
| `api` | FastAPI/Uvicorn | via `proxy` only | Owns the DB connection and provider ports |
| `web` | Next.js `next start` | via `proxy` only | Build-time public values |
| `execution-worker` | Python worker | none | Bounded loop, no port |
| `research-worker` | Python worker | none | Bounded loop, no port |
| `postgres` | PostgreSQL 18 | none | Private network only |
| `runner` (future) | trusted job runner | none | Whole-process isolation boundary (§6); not yet available |

The future **P27 recurring-evaluation producer** is an additional required process, distinct from the saved-job workers. It is **not proved** by the current worker loop and is not specified here.

A single VPS is a possible bounded topology subject to actual isolation and capacity checks. It remains a shared failure domain for API, data and agents. For funded public users, consider separating the Hermes runner from the application/database host if the required containment cannot be proved on one VPS.

## 4. Proposed services, ports, volumes and secret ownership

Frozen proposal (not installed):

| Concern | Proposal |
|---|---|
| Published ports | Only the proxy publishes 443 (and 80→443 redirect). `api`, `web`, `postgres`, both workers and the runner publish **no** host port. |
| Internal network | One user-defined bridge network; services reach each other by service name. |
| Volumes | `postgres-data` (database); `job-evidence` (durable private job/evidence output); optionally `web-cache`. Separate volumes, distinct retention and access rules. Never `tmpfs` for durable state. |
| Secret ownership | Postgres role credentials exist only on the `postgres` service. The API receives the composed `EDGE_OS_DATABASE_URL` and never the raw `POSTGRES_PASSWORD`. The web service receives **no** database or session secret. Privy keys live only in the API environment. All values come from the host secret store, never image layers or the browser bundle. |
| Build-time vs runtime API address | `NEXT_PUBLIC_API_BASE_URL` is a public **build-time** value (the API's HTTPS origin). A private runtime API origin (`http://api:8000`) is used only if SSR needs it. |
| Images | Pinned base digests; `uv sync --frozen` and `npm ci`; a non-root runtime user; no package manager downloaded at startup. |
| Application DB TLS | The API still requires `sslmode=require` or stricter on `EDGE_OS_DATABASE_URL`. A plain private-network PostgreSQL connection copied from a reference project would **not** meet this contract. Prepare PostgreSQL certificates/trust and verify the accepted connection behavior. Do not disable validation and do not use local/fixture mode to make a public deployment start. |
| Migrations | A single explicit serialized `alembic upgrade head` step before the API takes traffic (not auto-migrate on each API start). |
| Healthchecks | Order startup by dependency: `postgres` healthy before `api`; `api` `/readyz` healthy before `web`. Use `/readyz` (durable dependencies) for readiness, not only `/healthz`. |

## 5. In-image contract and qualification asset inventory

The API reads repository files at import or first use. A package that contains only Python source can fail to start. Every deployed image must include at least:

| Asset | When read | Missing-file behavior |
|---|---|---|
| `docs/contracts/p02/check_contract.py` | import | import failure |
| `docs/contracts/p06/contract.json` | import | import failure |
| `docs/qualification/p07/qualification.py` | import | `EngineUnavailable`; API cannot start |
| `docs/implementation/EFFECT_COMPARISON_PROFILE.md` | first use | feature failure |
| `docs/implementation/SPOT_REPLAY_RUNTIME_PROFILE.md` | first use | feature failure |

The repository root is derived from the module file path (`parents[5]`), so the working directory is not the constraint; the files must be on disk in the image. Record exact source/tree, Python/Node/toolchain versions and all runtime assets in the image build. Later accepted Hermes/Nansen dependencies must be verified separately.

## 6. Trusted runner, isolation, egress and private output

- **No host Docker socket in the public API or model process.** Mounting the host Docker socket gives full host-daemon access. The public API and any model process must not receive it.
- **Trusted runner boundary.** The process that manages bounded job containers needs a narrowly scoped, separately qualified control boundary. It must run fresh isolated processes per bounded job, own each job's output/evidence directory, share no mutable memory across jobs, hold no signing credential and no privileged database connection, and clean up after each job. Retain all P05 cleanup and unknown-liability requirements. A helper included in a plan is **not** an accepted runner.
- **Accepted LOCAL helper (available, not mounted).** Lane-1 Hermes job transport support is accepted LOCAL and integrated at `dbd95668` (candidate `fa8d52f2`), safely released. It runs pinned Hermes in a no-network, read-only job container and adds an injected provider-transport seam; the actual provider route is refused (`ActualProviderUnavailable`) and **no application consumer mounts it**. Boundaries to keep: authored transport only; the SQLite spend ledger is LOCAL-only (shared durable storage is a proposal); the credential file is mounted read-only into the job container, but the job, transport and Hermes share one process, so **the credential copy is readable by Hermes code** — credential isolation needs a separately decided host-held relay; supervision is `recover_pending(C)`; the foreground deadline D is the job timeout plus seal grace and is never renewed; measured timing overruns keep their UNKNOWN cause. Read-only context: `docs/qualification/hermes-job-support/README.md`, `ACTUAL_QUALIFICATION_PACKET.md`, `JOB_IDENTITIES.json` (at integration `dbd95668`). The helper is available; the hosted H2/H3 qualification stays NOT RUN.
- **Egress (gate H1).** The application's quotas cap requests and compute, not money at a provider. A VPS firewall is not sufficient evidence: published container ports can bypass UFW, so verify exposure externally. Prepare an explicit provider-only egress decision (an enforced egress rule, an allowlisting forward proxy, or a recorded risk acceptance for a named provider set).
- **Private output.** Each job writes only its approved private directory; no cross-job or cross-owner file is readable. Private job/evidence storage persists on its own volume with its own retention and access rules.

## 7. Cost and dated-alternative separation

Contabo VPS cost depends on the existing plan/add-ons, which are **unknown** (gate H13). Do not estimate an Edge OS cost from the existing VPS without the builder's plan facts. The research note records two Contabo facts to confirm: snapshots are **not** backups, and separately stored VPS auto-backup exists on eligible plans but plan availability and database recoverability remain unverified.

The earlier Render/Fly/Vercel first-party prices (observed 2026-10-12) are retained here only as **dated context**, no longer as a target selection:

| Alternative | Smallest relevant monthly list price | Status |
|---|---|---|
| Render managed PaaS | ~$47/mo (4 services + Postgres 18) + storage/bandwidth | dated context; not selected |
| Fly.io | ~$51/mo (Machines + Managed Postgres) | dated context; not selected |
| Vercel | $20/mo web tier only (no API/worker/DB) | dated context; not selected |
| Contabo existing VPS | unknown (existing plan) | **selected target for preparation** |

Separate cost classes remain: infrastructure, model/inference, data/provider requests, bandwidth, storage and backup. Model/data/provider costs are provider-priced and unknown here.

## 8. Exact unmet decision gates

| Gate | Required control | Status | Minimal information to decide |
|---|---|---|---|
| H13 VPS facts | CPU, RAM, disk, OS, installed services (incl. Coolify), domain | **UNKNOWN** | Builder supplies the facts or authorizes a read-only inspection. No routine CPU/RAM/disk estimate is made. |
| H1 Provider-only egress | An enforced egress rule or an accepted risk/proxy decision | **NOT RUN** | Choose (a) an enforced egress rule, (b) an allowlisting forward proxy, or (c) a recorded risk acceptance for a named provider set. Verify externally; do not trust an OS firewall alone. |
| H2 Qualified isolated Hermes job runtime | Whole-process isolation, owned supervision, no host Docker socket | **NOT RUN** (accepted LOCAL helper `dbd95668`, not mounted; actual route refused) | The helper provides the no-network/read-only job container and runner; decide the host-held credential relay and the actual qualification packet. Do not label hosted H2 PASS. |
| H3 Owned supervision and cleanup | Bounded timeout, cancellation, cleanup, no cross-job reuse | **NOT RUN** (helper `recover_pending(C)` accepted LOCAL; hosted proof unrun) | The helper's fault fixtures and the host supervisor decision. Retain D and finite C; measured overruns keep their UNKNOWN cause. |
| H4 Storage and locks | Durable per-owner storage; advisory locks and session-scoped DDL under the chosen connection | **NOT RUN** | Confirm the connection model; the proposal uses a private direct connection. |
| H5 Database TLS | `sslmode=require` or stricter; session-scoped DDL for migrations | **REQUIRED**; not configured on the VPS | Prepare certificates/trust and verify the accepted connection; do not disable validation. |
| H6 Startup versions | Python `3.14.x` and Node `24.x` in-image | **NOT RUN** | Pin the exact image digests/versions at build. |
| H7 Resource / job concurrency | Correct container sizes and worker concurrency | **NOT RUN** | A hosted load check after sizes are chosen. |
| H8 Provider money limits | A hard spending cap at each external provider | **NOT provided by the host** | Builder sets provider-side billing limits and records them. |
| H9 Abuse protection in front of the API | Bot/IP limits before authentication | **NOT RUN** | Decide whether the launch needs a WAF/proxy IP rule; the application rate limit is per signed-in owner only. |
| H10 Off-VPS backup and restore rehearsal | Off-VPS application backups; fresh-database restore rehearsal; verified actual process replacement; schema-compatible rollback; recovery point/time bounds | **NOT RUN** | Backups stored off the VPS; a restore drill that reads a known record from a fresh database; a rollback rehearsal that replaces the running process. |
| H11 Log retention and access | Retention matching `RETENTION_DELETION_SUPPORT.md` | **NOT RUN** | Confirm the retention choice matches the public statement. |
| H12 Dependency advisories | Resolve the wallet-SDK advisories before public exposure | `ADVISORY_ASSESSMENT.md`: 25 advisories through the wallet SDK; no lockfile change | Controller disposition. |

## 9. Bounded recommendation

For a bounded staging/demo on the existing Contabo VPS, use Docker Compose with only the proxy publishing traffic, PostgreSQL and the workers private, images built off the serving VPS and deployed as immutable digests, and a single explicit migration step. If Coolify already runs, use its Compose deployment and proxy; otherwise use plain Compose with a reverse proxy. This selects no plan, resource size or paid add-on.

The proposal is **not sufficient for the full public release claim**: provider-only egress (H1) and the qualified isolated Hermes runner (H2) remain blocked, and off-VPS backup/restore (H10) is unrun. Do not present any of these as solved. A funded public deployment should prefer separating the runner from the application/database host if H2 containment cannot be proved on one VPS.

## 10. Sources

- Contabo research: `docs/research/EDGE_OS_CONTABO_DEPLOYMENT_RESEARCH_2026-10-12.md`; reference identities `.scratch/contabo-reference-identities-20261012.json`.
- Prior projects: see [PRIOR_PROJECT_DEPLOYMENT_PATTERNS.md](PRIOR_PROJECT_DEPLOYMENT_PATTERNS.md).
- Docker production Compose, Docker engine security (daemon socket), Docker packet-filtering/firewall behavior; Coolify self-hosting; Next.js self-hosting; Contabo snapshots/auto-backup — via Context7 resolve-first and official pages, 2026-10-12.
- Accepted code and prior documents: the assigned worktree at base `3e7ff8bd`.

## 11. Evidence classification

- **Inspected source:** the component, health, migration, URL, routing, limit and asset rows in §2 and §5.
- **First-party/field documentation:** Docker, Coolify, Next.js and Contabo facts in §9's sources; the reference-project identities in the patterns file.
- **Read-only prior-project patterns:** the patterns file; independently written, not copied.
- **UNKNOWN / REQUIRED_DECISION:** H13 and H1–H12 in §8.
- **NOT RUN:** every hosted check (no host configuration exists).
