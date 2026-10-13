# Hosting assessment for the Hermes interpretation job

Status: assessment from documents. NOT_RUN. It selects no vendor, buys nothing and deploys nothing. It is not authority. No live request was made and no account was queried. It builds on the earlier [hosting and access assessment](../release-preparation/HOSTING_AND_ACCESS_ASSESSMENT.md) (P41, 2026-10-10). Read that file for the web, API and database arrangement. This file adds only what the Hermes job changes.

Documentation checked 2026-10-11 through Context7: Fly.io (`/websites/fly_io`) and OpenRouter (`/openrouterteam/docs`). Public documentation access is not provider inference or account access.

## 1. What changed since P41

| P41 fact | Change for the Hermes job |
|---|---|
| "No outbound provider call at this stage" | A live interpretation sends one request per attempt to a provider. Egress is now a requirement. |
| Worker lifecycle undecided | Each model turn is an isolated job. Locally it is a disposable container with no network. |
| Secrets live in the host secret store | The provider credential needs a narrower route: a file in the job only, never an argument or a log line. |
| Durable state is PostgreSQL | The spend ledger must also be durable and shared by all API processes. The local ledger is SQLite for tests. |

## 2. Requirements and gaps

| Need | Local state | Production gap |
|---|---|---|
| Runtime pins | Hermes commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba`, `uv.lock` SHA-256 `de17d70b…ce63c01`, `python:3.14-slim-trixie` by digest, `uv` 0.12.16 | An image built and stored by the host. Not built. |
| Isolated job per turn | `docker run --rm`, read-only root, 512 MB, 1 CPU, 64 processes, all capabilities dropped, one input file, one output folder | A host that can start a one-off job. The API process should not hold a Docker socket. |
| Secret injection | Mounted read-only file, redacted in saved evidence | Fly.io documents `fly machine run --file-secret /path=SECRET` with a base64 secret staged by `fly secrets set --stage`. Not tried. |
| Provider-only egress | None (no network) | The retrieved Fly.io network policy page filters by direction, port and protocol (for example TCP 443). It says nothing about host names, so provider-only egress is **not established**. A name-aware proxy or allow-list is a separate qualification. |
| Resource and deadline limits | Container limits; a 60-second host kill with an ownership check on name and label | Machine `guest` size and a stop with timeout exist in the Machines API. The in-process deadline must still run in the job. Fly.io `kill_timeout` is a drain window with a 300-second maximum, not a job limit. |
| Durable spend ledger | `SpendLedger` on SQLite, one file | One shared PostgreSQL table with the same reserve, settle, release and reconcile rules, and the same atomicity. Not written. |
| Late evidence | Recorded once, never double-counted | A way to receive provider usage after a kill, and a person who decides conflicts. |
| Production refusal | `EDGE_OS_INTERPRETER=hermes_local` is refused in production. The new files are not imported by the application. | Keep it so until a live release exists. |

## 3. Smallest later integration

The application already accepts a runner: `create_app(settings, hermes_runner=...)` in `apps/api/src/edge_os_api/main.py`. The guarded runner has the same `run_turn` interface. A later ticket needs only:

1. a live job image and entrypoint that apply `ProviderRequestGuard` to the real transport;
2. a PostgreSQL implementation of the ledger behind the same methods;
3. a setting that selects the live runner, refused unless a recorded release exists;
4. host wiring for the secret, the egress rule and the stop deadline.

Those paths belong to the shared wiring owner (P17). This continuation edits none of them.

## 4. Limits of the in-process guard

The guard checks each request it can see. It cannot count a socket that other code opens outside the transport. A live host must limit egress to the provider and, if possible, count requests at a proxy. A killed job may leave an upstream request running. Neither the guard nor the ledger proves zero charge after a kill.

## 5. Vendor feasibility

The P41 recommendation stays: Arrangement B (one container host) with a managed PostgreSQL. For the job, Fly.io Machines support one-off runs (`--rm`), file secrets, guest sizing and network policies by port. That fits the shape. It does not prove provider-only egress. Cost, plan, region and PostgreSQL 18 compatibility stay with the builder and stay UNRESOLVED. No plan was selected here.

## 6. Open items

- Provider-only egress mechanism. UNRESOLVED.
- Job launch from the API without a Docker socket. NOT_RUN.
- PostgreSQL ledger and its concurrency test. NOT_RUN.
- Credential route and provider-side ceiling. Decision pending.
- A live job entrypoint with its own reviews. Not written.
