# Edge OS on Coolify: deployment runbook (files only; NOT RUN)

Status: **preparation only.** This file and the files it names were written on 2026-10-22 for the builder's Contabo
VPS. Nothing was installed, started, pushed or deployed. Every host result is `NOT RUN`. The builder or controller owns
the VPS, DNS, secrets, the hosted-deployment record approval and every push.

This candidate does not approve a hosted deployment. `core/hosted_deployment.APPROVED_HOSTED_DEPLOYMENTS` stays empty.
Do not add an entry and do not present a deployment as approved because this runbook exists.

## 0. Names and variables

| Variable | Meaning | Example (not a secret) |
|---|---|---|
| `WEB_ORIGIN` | Public web origin | `https://app.edgeos.fun` |
| `API_ORIGIN` | Public API origin | `https://api.edgeos.fun` |
| `EDGE_OS_API_IMAGE` | API image by digest | `ghcr.io/edge-os-app/edge-os-api@sha256:<64 hex>` |
| `EDGE_OS_WEB_IMAGE` | Web image by digest | `ghcr.io/edge-os-app/edge-os-web@sha256:<64 hex>` |
| `EDGE_OS_POSTGRES_IMAGE` | PostgreSQL image by digest | `postgres:18.6-trixie@sha256:<64 hex>` |
| (literal path) | Host folder with the PostgreSQL certificate and key | `/etc/edge-os/postgres-tls` |
| `COOLIFY_NETWORK` | Coolify's Traefik network name | `coolify` |

The builder chooses the final host names. If the web uses the apex, set `WEB_ORIGIN=https://edgeos.fun` and adjust the
DNS and CORS value; the code needs one exact HTTPS origin, not a wildcard.

## 1. DNS records for edgeos.fun

| Name | Type | Value | Purpose |
|---|---|---|---|
| `edgeos.fun` | `A` and/or `AAAA` | VPS IPv4 and/or IPv6 | Apex (only if the web uses it) |
| `app.edgeos.fun` | `CNAME` to `edgeos.fun`, or `A`/`AAAA` | VPS address | Web |
| `api.edgeos.fun` | `A` and/or `AAAA` | VPS address | API |

Open inbound TCP 80 and 443 only. Coolify's Traefik terminates TLS with a certificate for both names. Do not publish
5432, 8000 or 3000. Published container ports can bypass a host firewall, so verify the public exposure externally.

## 2. Coolify resource setup

1. Open the Coolify dashboard and the chosen project and environment.
2. Select **New Resource** -> **Application** -> the GitHub repository `edge-os-app/edge-os`.
3. Select the release branch or commit the builder approved. Do not use an unapproved branch.
4. Select **Docker Compose** as the build pack.
5. Set **Base Directory** to `/`.
6. Set **Docker Compose Location** to `compose.coolify.yml`.
7. Do not set a custom build command or a custom start command.
8. Assign domains only to these services:

| Service | Domain field | Container port |
|---|---|---|
| `api` | `https://api.edgeos.fun:8000` | `8000` |
| `web` | `https://app.edgeos.fun:3000` | `3000` |

The `:8000` and `:3000` suffixes select the internal container port. The public URL does not use those ports.
Do not assign a domain to `postgres`, `migrate`, `execution-worker` or `recurring-producer`.
Coolify adds its Traefik labels; this file adds none.

9. Confirm the named volume `database` is mapped to `/var/lib/postgresql` (PostgreSQL 18 layout).
10. Set the environment values in section 3, then deploy.

## 3. Build Variables and runtime environment (names only)

The images are built by `.github/workflows/images.yml`, not by Coolify. The `NEXT_PUBLIC_*` values are **build-time**
values for that workflow. They are public and are inlined into the browser bundle. Changing one needs a new workflow
run and a new image digest.

| Name | Where | Owner services | Secret? |
|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | GitHub Actions repository variable | web build | No |
| `NEXT_PUBLIC_PRIVY_APP_ID` | GitHub Actions repository variable | web build | No |
| `POSTGRES_USER` | Coolify runtime | `postgres` | No |
| `POSTGRES_PASSWORD` | Coolify runtime | `postgres` | **Yes** |
| `POSTGRES_DB` | Coolify runtime | `postgres` | No |
| `EDGE_OS_DATABASE_URL` | Coolify runtime | `migrate`, `api`, both workers | **Yes** (contains the password) |
| `EDGE_OS_PRIVY_APP_ID` | Coolify runtime | `api`, both workers | No |
| `EDGE_OS_PRIVY_VERIFICATION_KEY` | Coolify runtime | `api`, both workers | No (EC P-256 public key) |
| `EDGE_OS_CORS_ALLOWED_ORIGINS` | Coolify runtime | `api`, both workers | No |
| `EDGE_OS_BUILD_SHA` | Coolify runtime | `api`, both workers | No |
| `EDGE_OS_RESEARCH_BUDGET_*` | Coolify runtime (optional, defaults in the file) | `api`, `recurring-producer` | No |
| `EDGE_OS_USAGE_GLOBAL_*` | Coolify runtime (optional, defaults in the file) | `api`, `recurring-producer` | No |
| `EDGE_OS_WRITE_RATE_PER_MINUTE` | Coolify runtime (optional) | `api`, `recurring-producer` | No |
| `EDGE_OS_RESEARCH_MAX_ACTIVE_JOBS` | Coolify runtime (optional) | `api`, `recurring-producer` | No |
| `EDGE_OS_DATABASE_STATEMENT_TIMEOUT_MS` | Coolify runtime (optional) | `api`, both workers | No |

The execution worker has its own environment block, not the API block: it receives only the names it needs (see
`docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md` §4).

Set the runtime values:

```text
POSTGRES_USER=edge_os
POSTGRES_PASSWORD=<generated, stored only in Coolify>
POSTGRES_DB=edge_os
EDGE_OS_DATABASE_URL=postgresql+psycopg://edge_os:<same password>@edge-os-postgres:5432/edge_os?sslmode=require
EDGE_OS_PRIVY_APP_ID=<public app id>
EDGE_OS_PRIVY_VERIFICATION_KEY=<public key PEM; newlines may be written as \n>
EDGE_OS_CORS_ALLOWED_ORIGINS=https://app.edgeos.fun
EDGE_OS_BUILD_SHA=<40-character deployed source commit>
```

`POSTGRES_DB` and the database name in the `EDGE_OS_DATABASE_URL` path must be the same. The examples use `edge_os`.

**Alias collision warning.** The URL host is `edge-os-postgres`, never `postgres`. The API joins Coolify's `coolify`
network, where Coolify's own database answers to `postgres`; a URL naming `postgres` reached Coolify's database in
the live deployment. Production settings now refuse that host. See
`docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md` §2.

Rules and refusals:

- Do not set `EDGE_OS_PRIVY_APP_SECRET`, `EDGE_OS_AUTH_DISABLED` or `EDGE_OS_DEV_AUTH_BYPASS`. Startup refuses them.
- `EDGE_OS_CORS_ALLOWED_ORIGINS` must be one or more exact `https://` origins. No `*`, no `http://`.
- The database host must not be loopback, `postgres` or `coolify-db`, and the URL must carry `sslmode=require` or
  stricter. The one exception is the host research worker's `127.0.0.1`, admitted only with a registered hosted
  deployment record whose TLS mode is the URL's `sslmode` (see `HOSTED_RECORD_V2_RUNBOOK.md` §3.2).
- `EDGE_OS_BUILD_SHA` must be the exact deployed commit.
- The test app id `edge-os-test-app` is refused.
- Provider modes stay `unavailable`; the interpreter stays `fixture` until an approved hosted deployment exists.

The image variables are also runtime values:

```text
EDGE_OS_API_IMAGE=ghcr.io/edge-os-app/edge-os-api@sha256:<digest from the workflow artifact>
EDGE_OS_WEB_IMAGE=ghcr.io/edge-os-app/edge-os-web@sha256:<digest from the workflow artifact>
EDGE_OS_POSTGRES_IMAGE=postgres:18.6-trixie@sha256:<digest pinned in compose.local.yml or a reviewed newer pin>
```

Never deploy by a floating tag. The workflow artifact `image-digests` holds `api.digest`, `web.digest` and
`image-digests.json`.

### Coolify 4.4.7 does not substitute the image variables

Coolify 4.4.7 does not list or substitute the `${EDGE_OS_*_IMAGE:?}` variables from the environment page. The file
keeps those required variables so a local `docker compose config` still refuses a missing or floating image. Write the
three digests literally into the deployed compose file.

Exact step: in the Coolify Compose editor, replace each `image:` line with the digest literal. Do not paste secrets.

```text
api:      image: ghcr.io/edge-os-app/edge-os-api@sha256:<api.digest from image-digests.json>
web:      image: ghcr.io/edge-os-app/edge-os-web@sha256:<web.digest from image-digests.json>
postgres: image: postgres:18.6-trixie@sha256:<pinned postgres digest>
```

Check that every `image:` line ends with `@sha256:<64 hex>` and that no `image:` line still holds `${`. The PostgreSQL
TLS mount already uses the literal host path `/etc/edge-os/postgres-tls`; Coolify 4.4.7 refuses a volume source that
contains `${`. Keep the edited file as `compose.deployed.yml` outside the repository and paste it into Coolify. Do not
commit it.

## 4. PostgreSQL TLS certificate

Create the certificate on the host. PostgreSQL runs as uid/gid 999 in the official image, and `compose.coolify.yml`
sets `user: "999:999"` so the entrypoint starts without root capabilities. The key must be owned by `999:999` and
readable by its owner only. The file is mounted read-only; it is not in the image or this repository.

```sh
install -d -m 0750 -o 999 -g 999 /etc/edge-os/postgres-tls
cd /etc/edge-os/postgres-tls
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 825 \
  -keyout server.key -out server.crt -subj "/CN=edge-os-postgres" \
  -addext "subjectAltName=DNS:edge-os-postgres,IP:127.0.0.1" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"
chown 999:999 server.crt server.key
chmod 0644 server.crt
chmod 0600 server.key
```

The Compose file starts PostgreSQL with `ssl=on`, `ssl_cert_file=/etc/edge-os/postgres-tls/server.crt` and
`ssl_key_file=/etc/edge-os/postgres-tls/server.key`. Its health check runs `pg_isready` and requires `show ssl` to
return `on`.

Limit: `sslmode=require` encrypts the connection but does not verify the server certificate. For `verify-full`, create
a CA, sign the server certificate, mount the CA into the API, and change the URL to
`sslmode=verify-full&sslrootcert=<container path>`. That stricter mode is **not** configured here.

## 5. Migration step

`compose.coolify.yml` defines one `migrate` service. It runs `python -m alembic upgrade head && python -m alembic
check`, exits 0 and does not restart. The API and both workers use
`depends_on: migrate: {condition: service_completed_successfully}`. No API start runs a migration.

If a Coolify version does not start one-shot Compose services, run the same command once from the resource terminal:

```sh
docker compose -f <coolify compose path> run --rm migrate
```

Run it exactly once per deploy, before the API takes traffic. Never add an automatic migration to the API command.

If Coolify marks the exited one-shot `migrate` service as degraded, set Coolify's `exclude_from_hc` option for that
service, or use the terminal command above. This is an install-time check; no unverified Compose key is added here.

## 6. Host services outside Coolify

Two host services run outside Coolify: the research worker with the guarded Hermes runner, and the Hermes provider
relay with its supervisor. Neither is enabled in this candidate. Both use their own Docker socket proxy; the proxies
are the only new processes that read `/var/run/docker.sock`. No Coolify service mounts it.

### 6.1 Users, groups and folders

Create one service group and one proxy user per role. The service user must **not** be in the `docker` group.
Neither the service user nor the proxy user needs host Docker group membership: the proxy container receives the
socket's group with Compose `group_add`, because a numeric container `user:` does not inherit host groups.

```sh
groupadd --system edge-os-research
useradd --system --no-create-home --shell /usr/sbin/nologin --gid edge-os-research edge-os-research
useradd --system --no-create-home --shell /usr/sbin/nologin --gid edge-os-research edge-os-proxy-research

groupadd --system edge-os-relay
useradd --system --no-create-home --shell /usr/sbin/nologin --gid edge-os-relay edge-os-relay
useradd --system --no-create-home --shell /usr/sbin/nologin --gid edge-os-relay edge-os-proxy-relay

# The Hermes application (edge-os-research) and the relay (edge-os-relay) share only the relay files they must
# exchange. Neither user joins the other's group, so the research side never reads /etc/edge-os/relay.
groupadd --system edge-os-relay-share

stat -c '%g' /var/run/docker.sock   # set EDGE_OS_DOCKER_GID to this number

install -d -m 0750 -o edge-os-proxy-research -g edge-os-research /run/edge-os/research
install -d -m 2750 -o edge-os-research -g edge-os-research /var/lib/edge-os/research /var/lib/edge-os/research/tmp
install -d -m 0700 -o edge-os-research -g edge-os-research /var/lib/edge-os/research/docker-config
install -d -m 0750 -o edge-os-proxy-relay -g edge-os-relay /run/edge-os/relay
install -d -m 0750 -o edge-os-relay -g edge-os-relay-share /var/lib/edge-os/relay
install -d -m 0700 -o edge-os-relay -g edge-os-relay /var/lib/edge-os/relay/docker-config
install -d -m 0750 -o edge-os-relay -g edge-os-relay /etc/edge-os/relay
install -d -m 2770 -o root -g edge-os-relay-share /var/lib/edge-os/channel
```

The research root and its `tmp` keep the setgid bit (`2750`), so files the application writes there stay in the
`edge-os-research` group and the relay cannot read research evidence. The shared channel root (`/var/lib/edge-os/channel`,
`2770`) is the only place the job, the application and the relay all write. The operator configuration's
`channel.path` must name a new child folder under it, for example `/var/lib/edge-os/channel/hermes-channel-1`; the
operator refuses a channel folder that already exists, and the root itself is never a channel path. The relay run root is `0750` with group
`edge-os-relay-share`, so the application can traverse it to read `handoff.json`; the relay's configs, `tls/`, `provider/`,
`gateway/` and `secrets/` stay owner-only. `grants/` and `revocations/` are `0770`, `state/` is `0750` (the relay is its
only writer). Both units keep `RestrictSUIDSGID=yes`, which denies a `chmod`/`mkdir` mode argument with S_ISGID; every
writer already has primary gid `edge-os-relay-share`, so no code requests the setgid bit. Only the root-made channel
root above keeps `2770` (its `install` runs outside the unit). The socket proxies' docker-config folders stay `0700` for
their own user.

The proxy writes its socket at `/run/edge-os/<role>/docker.sock` with mode `0660`. The socket file belongs to the
proxy uid and the role group, so the service can use it and cannot read the real Docker socket. Each unit keeps its own
group as `SupplementaryGroups=` (`edge-os-research` or `edge-os-relay`) for this access, and sets
`Group=edge-os-relay-share` as its primary group for the shared folder.

### 6.2 Code and Python environment

```sh
git -C /opt/edge-os fetch --all --tags
git -C /opt/edge-os checkout <approved commit>
cd /opt/edge-os/apps/api && uv sync --frozen
```

The host service uses the repository checkout at `/opt/edge-os`. It is not the Coolify API image.

### 6.3 Environment files

`/etc/edge-os/socket-proxy.env` (mode `0600`, owner `root:root`):

```text
EDGE_OS_SOCKET_PROXY_IMAGE=<wollomatic/socket-proxy digest>
EDGE_OS_PROXY_RESEARCH_UID=<numeric uid of edge-os-proxy-research>
EDGE_OS_RESEARCH_GID=<numeric gid of edge-os-research>
EDGE_OS_PROXY_RELAY_UID=<numeric uid of edge-os-proxy-relay>
EDGE_OS_RELAY_GID=<numeric gid of edge-os-relay>
EDGE_OS_DOCKER_GID=<numeric group of /var/run/docker.sock>
```

The socket-proxy image must be `wollomatic/socket-proxy` v1.12 or newer. This file uses repeated `-allow*` flags, which
that version introduced; v1.13 also hardens the bind-mount check. An older digest fails closed and breaks the runner.

`/etc/edge-os/research-worker.env` (mode `0600`, owner `root:edge-os-research`) holds the same `EDGE_OS_*` names as the
API service, plus `DOCKER_HOST=unix:///run/edge-os/research/docker.sock` and
`TMPDIR=/var/lib/edge-os/research/tmp`. No value is committed.

**Database route for the host research worker (builder decision B2 option a, 2026-10-22).** PostgreSQL publishes
`127.0.0.1:5432` only, from the `hostdb` bridge, and its certificate carries `IP:127.0.0.1`. The worker URL uses host
`127.0.0.1`. Production settings admit that loopback host only with a registered hosted deployment record whose TLS
mode is the URL's `sslmode` (builder decision, option A, 2026-10-23). The registry is empty, so the unit stays
**NOT READY** and must not be enabled before the record is registered. See
`docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md` §3.2.

`/etc/edge-os/hermes-relay.env` holds `DOCKER_HOST=unix:///run/edge-os/relay/docker.sock` and the relay's non-secret
paths. The relay operator configuration `/etc/edge-os/relay.json` is described by
`scripts/hermes_provider_relay/relay_operator.py`; it names the release, image id, run root, channel and provider key
path. The provider key is a host-held file at `/etc/edge-os/relay/provider-key`, mode `0600`, readable by
`edge-os-relay` only.

Every host unit sets `DOCKER_CONFIG` in its own unit file, because `ProtectHome=yes` hides `~/.docker/config.json`:
`/var/lib/edge-os/relay/docker-config` for the relay and `/var/lib/edge-os/research/docker-config` for the research
worker and the application. Without it the Docker CLI prints a permission warning and the operator reads every
answer as `unknown`.

`/etc/edge-os/hermes-app.env` (mode `0640`, owner `root:edge-os-research`) holds the application's names:

```text
EDGE_OS_HANDOFF_PATH=/var/lib/edge-os/relay/run-1/handoff.json
EDGE_OS_HANDOFF_SHA256=<the sha256 the operator printed at start>
EDGE_OS_RUN_ID=vps-hermes-app-1
EDGE_OS_INTERPRETER=hermes_local
EDGE_OS_APP_BIND_HOST=127.0.0.1
# plus the research worker's EDGE_OS_* names: database URL, hosted deployment id and record path, Privy, CORS, build SHA
```

The two handoff values are the operator's printed line, written by the controller. The application reads them from this
root-owned file; the handoff itself is not trusted to name its own hash. The application listens on `127.0.0.1:8011` by
default.

**Public Hermes route (HERMES-ROUTE-L4).** The Coolify `api` service gets its own variable
`EDGE_OS_HERMES_APP_URL=http://<coolify-gateway>:8011`. Derive the address on the host with
`docker network inspect coolify --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'` (today `10.0.1.1`); do not commit
it as a code fact. The launcher accepts only an IPv4 loopback or RFC 1918 literal and refuses IPv6, `0.0.0.0`, names and
public addresses. The unit starts after `docker.service`, because the bridge address exists only after Docker creates
the bridge.

The API forwards exactly these six paths and methods, and every other API path stays on the `api`:

```text
GET  /v1/interpreter
POST /v1/research/requests
GET  /v1/research/requests
GET  /v1/research/requests/{intake_id}
POST /v1/research/requests/{intake_id}/clarifications
POST /v1/research/requests/{intake_id}/interpretation-retries
```

The forward requires the Privy principal and the write limit before it sends a byte. It forwards only `Authorization`,
`Content-Type` and `Accept`; it returns only `Content-Type` and `Retry-After`; it adds no owner header. It never follows
a redirect and never reads `HTTP_PROXY` or `NO_PROXY`. A connect failure is `503 interpreter_unavailable`, a read
timeout is `504 interpreter_timeout`, and any other transport failure is `502 interpreter_route_failed`. The host
application serves only the six paths plus `GET /healthz` and `GET /readyz`; everything else is 404.

Rollout: the controller deploys the new API image only after the host application is READY and the public checks pass.
Until then the running API image stays. With `EDGE_OS_HERMES_APP_URL` empty in production, the six paths return
`503 interpreter_unavailable`; local and test runs keep the fixture behaviour.

Host firewall and public-port checks, run by the controller only:

```sh
ufw status numbered
iptables -S INPUT   # or: nft list ruleset
ss -ltnp | grep ':8011'   # only <coolify-gateway>:8011, never 0.0.0.0:8011 or [::]:8011
nc -vz <VPS public IP> 8011   # must fail from another machine
```

One INPUT rule allows TCP 8011 from the `coolify` subnet (today `10.0.1.0/24`) to the gateway only. The default policy
stays deny.

The `host_gates.h2_runner_isolation` evidence file must hold: the six paths and methods; the bind address; the `ss`
output; the outside `nc` failure; the firewall rule; the forward settings; the 503 state when the URL is empty; the host
guard 404 for an outside path; and the tests that prove authentication and the write limit run before the forward.

`/etc/edge-os/relay/provider-ca.pem` is `root:edge-os-relay-share` mode `0640` (a public CA bundle), because the relay
container runs with the shared group:

```sh
chown root:edge-os-relay-share /etc/edge-os/relay/provider-ca.pem
chmod 0640 /etc/edge-os/relay/provider-ca.pem
```

The release record under `/opt/edge-os` is a tracked file with git mode `0644`,
so the relay container reads it unchanged. `/etc/edge-os/relay/relay.json` and `provider-key` stay `edge-os-relay` only.

### 6.4 Docker API calls and the derived allow-list

| Source | Docker CLI call | HTTP endpoint |
|---|---|---|
| `guarded_docker_runner.py` | `docker run --rm ...` | `POST /containers/create`, `POST /containers/{id}/start`, `POST /containers/{id}/attach`, `POST /containers/{id}/wait`, `GET /images/{name}/json` |
| `guarded_docker_runner.py` | `docker inspect <name>` | `GET /containers/{id}/json` |
| `guarded_docker_runner.py` | `docker kill <name>` | `POST /containers/{id}/kill` |
| `guarded_docker_runner.py` | `docker ps -a --filter ...` | `GET /containers/json` |
| `guarded_docker_runner.py` | Docker CLI basics | `GET /_ping`, `HEAD /_ping`, `GET /version`, `GET /info` (read-only negotiation) |
| `guarded_docker_runner.py` | observability only | `GET /containers/{id}/logs` (the runner captures the job's stdout by pipe; the packet names logs) |
| `relay_supervisor.py` | `docker run -d ...` | `POST /containers/create`, `POST /containers/{id}/start` |
| `relay_supervisor.py` | `docker inspect`, `docker logs` | `GET /containers/{id}/json`, `GET /containers/{id}/logs` |
| `relay_supervisor.py` | `docker kill`, `docker rm -f` | `POST /containers/{id}/kill`, `DELETE /containers/{id}` (only a `relay-*` name or a full Docker id) |
| `relay_supervisor.py` | `docker ps`, `docker exec` | `GET /containers/json`, `POST /containers/relay-*/exec`, `POST /exec/{id}/start`, `GET /exec/{id}/json` |
| `relay_supervisor.py` | `docker network create/rm/ls` | `POST /networks/create`, `DELETE /networks/{id}`, `GET /networks` (only a `relay-egress-*` name or a full Docker id) |
| `relay_supervisor.py` | `docker volume create/rm/ls` | `POST /volumes/create`, `DELETE /volumes/{name}`, `GET /volumes` (only a `relay-egress-*` name) |
| `relay_operator.py` | `docker inspect --type ...`, `docker image inspect` | `GET /containers/{id}/json`, `GET /networks/{id}`, `GET /volumes/{name}`, `GET /images/{name}/json` |

`docker_turn_runner.py` is qualification and test support. Its `PinnedHermesImage` calls `docker build`, `docker image
inspect`, `docker rmi`, `docker run`, `docker inspect`, `docker kill` and `docker ps`. The production guarded runner
never builds an image: it receives a pre-pulled pinned image from the release composition. Both proxies therefore deny
`POST /build` and `DELETE /images/{name}`; the production path must never call them. The static test asserts that
`guarded_docker_runner.py` does not reference `PinnedHermesImage`.

`deploy/host/docker-socket-proxy.yml` implements this list with `wollomatic/socket-proxy` method-and-path regular
expressions. It denies image pull, image build, image removal, container update, commit, export, archive,
secret/config, swarm, service, node, plugin and system endpoints. The relay proxy allows `exec` only under a
`relay-*` container path; the research proxy allows no `exec` at all. Both proxies limit bind-mount sources with
`-allowbindmountfrom`:

- research: `/opt/edge-os` and `/var/lib/edge-os/research` (evidence, input, output and the credential temporary
  directory; `TMPDIR` keeps that directory on a host-visible path);
- relay: `/opt/edge-os`, `/var/lib/edge-os` and `/etc/edge-os/relay`.

The hosted research release must use `/var/lib/edge-os/research` as its evidence root and its job `TMPDIR`. The proxy
denies any other bind source, so a different root fails closed instead of widening the proxy.

The proxy image is pinned by digest through `EDGE_OS_SOCKET_PROXY_IMAGE`. The client uses a Unix socket, so no TCP
listener is exposed. `network_mode: none` is intentional.

Residual limits: a bind-mount filter is a request filter, not a sandbox. A client that can create containers can still
choose a privileged container unless the daemon or an external policy stops it. The proxies deny `POST /images/create`,
but `POST /containers/create` can make the daemon pull a missing image internally; pre-pull every pinned image and
treat a missing image as a failed deploy. The proxies and the allow-lists reduce the API surface; they do not make the
research worker or the relay untrusted-safe. Keep the service users out of the `docker` group and keep the socket proxy
off every public network.

### 6.5 Install the units

```sh
install -m 0644 /opt/edge-os/deploy/host/edge-os-socket-proxy.service /etc/systemd/system/
install -m 0644 /opt/edge-os/deploy/host/edge-os-research-worker.service /etc/systemd/system/
install -m 0644 /opt/edge-os/deploy/host/edge-os-hermes-relay.service /etc/systemd/system/
install -m 0644 /opt/edge-os/deploy/host/edge-os-hermes-app.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now edge-os-socket-proxy.service
```

Pre-pull every pinned image as the operator, because the proxies deny pulls:

```sh
docker pull python:3.14-slim-trixie@sha256:<pinned digest>
docker pull <pinned hermes image>@sha256:<digest>
docker pull <pinned relay image>@sha256:<digest>
```

The research worker, relay and application units have `ConditionPathExists=/etc/edge-os/research-worker.enabled`,
`/etc/edge-os/hermes-relay.enabled` and `/etc/edge-os/hermes-app.enabled`. Do not create those marker files until the
builder approves the exact hosted deployment and the provider release. This candidate creates none.

### 6.6 Relay application start order

The operator owns the relay's start and writes the handoff once. The application may start only after that:

1. Start the relay: `systemctl start edge-os-hermes-relay.service`. The operator prints
   `handoff <path> sha256 <hex>` to the journal.
2. Copy its printed handoff line into `/etc/edge-os/hermes-app.env`: the path as `EDGE_OS_HANDOFF_PATH` and the hash as
   `EDGE_OS_HANDOFF_SHA256`. Copy its printed handoff first; never type a hash from another start.
3. Start the application: `systemctl start edge-os-hermes-app.service`. It listens on `127.0.0.1:8011` only. A new
   operation changes the path and the hash, so repeat steps 1-2 and restart the unit.

The application never stops, restarts or removes relay resources. Its `ReadWritePaths=/var/lib/edge-os/relay` is a stable
path because the run root changes per operation; DAC still limits it to `grants/` and `revocations/` (state `0750`,
configs `0600`, private folders `0700`, run root `0750`). Run `relay_operator stop` then `start` after a host reboot,
then repeat steps 1-3.

These read-only commands record H2 item 6 (the research side cannot read the provider key) and the shared layout. Run
them as the operator and record the output:

```sh
# Run every check as the deployed identity: the unit's primary group `edge-os-relay-share`. The plain user is denied
# at the 0750 relay root, so it cannot detect a config that became group-readable or a state folder that became
# group-writable.
sudo -g edge-os-relay-share -u edge-os-research test -r /etc/edge-os/relay/provider-key; echo "key_read=$?"      # must print key_read=1
sudo -g edge-os-relay-share -u edge-os-research test -r /var/lib/edge-os/relay/run-1/relay/relay-config.json; echo "config_read=$?"
sudo -g edge-os-relay-share -u edge-os-research test -r /var/lib/edge-os/relay/run-1/relay/provider-config.json; echo "provider_read=$?"
sudo -g edge-os-relay-share -u edge-os-research test -w /var/lib/edge-os/relay/run-1/relay/state; echo "state_write=$?"          # must be 1
sudo -g edge-os-relay-share -u edge-os-research test -r /var/lib/edge-os/relay/run-1/relay/secrets/admission-key; echo "admission_read=$?"
sudo -g edge-os-relay-share -u edge-os-research test -w /var/lib/edge-os/relay/run-1/relay/grants; echo "grants_write=$?"
stat -c '%U:%G %a %n' /var/lib/edge-os/relay /var/lib/edge-os/relay/run-1/relay /var/lib/edge-os/relay/run-1/relay/grants /var/lib/edge-os/relay/run-1/relay/state /var/lib/edge-os/relay/run-1/relay/relay-config.json /var/lib/edge-os/relay/run-1/relay/provider-config.json /var/lib/edge-os/relay/run-1/relay/secrets/admission-key /var/lib/edge-os/channel
```

Expected: `key_read=1`, `config_read=1`, `provider_read=1`, `state_write=1`, `admission_read=0`, `grants_write=0`;
the shared paths show the owners, groups and modes in §6.1. If the host's sudoers `Runas_Spec` does not allow an
arbitrary runas group, use `sudo -u root runuser -g edge-os-relay-share -u edge-os-research ...`; the expected values
do not change. The Hermes job container mounts only its own turn folder (under the channel) and the read-only job
code; it never mounts the admission key, `grants/`, `revocations/`, `state/` or the provider key, and the research
proxy's bind prefixes exclude `/var/lib/edge-os/relay`.

After a host reboot, the relay containers are stopped. Run the operator `stop` then `start` (or `restart` for a
complete, unchanged operation) before expecting relay health; a blind `start` refuses an existing run root by design.

## 7. Smoke tests

Run from a trusted host after the deploy:

```sh
WEB_ORIGIN=https://app.edgeos.fun \
API_ORIGIN=https://api.edgeos.fun \
NEXT_PUBLIC_PRIVY_APP_ID=<public app id> \
deploy/coolify/smoke_public.sh
```

The script checks:

- `GET $API_ORIGIN/healthz` is 200 with `status: ok` and a non-empty build SHA;
- `GET $API_ORIGIN/readyz` is 200 with `status: ready` and a schema revision;
- `GET $WEB_ORIGIN/` is 200 and serves the Next.js application;
- an `OPTIONS` preflight from `$WEB_ORIGIN` to `$API_ORIGIN/v1/me` returns
  `Access-Control-Allow-Origin: $WEB_ORIGIN`;
- the Privy app id appears in a built JavaScript asset (when the app id is supplied).

Manual check: add `$WEB_ORIGIN` to the Privy dashboard's allowed origins. The script cannot change the dashboard.

## 8. Backup and restore drill

A snapshot is not a backup. Keep the dump off the VPS and encrypted. The adopted plan (Contabo snapshots, an on-VPS
`pg_dump` and a restore drill into a scratch container) is `docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md`
§5.

```sh
docker compose -f <coolify compose path> exec -T postgres \
  pg_dump -Fc -U edge_os edge_os > /secure/off-vps/edge_os-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Restore rehearsal:

1. Create a fresh database `edge_os_restore` on a separate PostgreSQL instance or a separate host.
2. `pg_restore -d edge_os_restore <dump>`.
3. Point a throwaway API at the fresh database with `sslmode=require`.
4. Run `alembic check`; it must report no difference.
5. Request `/readyz`; it must report `status: ready` and the expected schema revision.
6. Read one known row (for example a saved budget or job) and compare it with the pre-backup value.
7. Record the recovery point (backup timestamp) and recovery time (measured).
8. Delete the throwaway stack and database after the check.

Do not copy a reference project's retention. Use the reviewed retention choice.

## 9. Rollback by digest

1. Read the previous `api.digest` and `web.digest` from the workflow artifact history.
2. Set `EDGE_OS_API_IMAGE` and `EDGE_OS_WEB_IMAGE` to those digests in Coolify.
3. Redeploy. Do not rebuild on the serving host.
4. Confirm `/readyz` and the smoke script on the previous version.

The previous image must be compatible with the current database schema. Migrations are forward-only. A schema
downgrade is a last resort and loses the usage event history, overrun amounts, reservation rows, request windows and
GLOBAL allocations described in `HOST_QUALIFICATION_RUNBOOK.md` 6.7. Prefer restoring the backup.

## 10. Hosted-deployment record fields the builder must approve

The record format is frozen in `apps/api/src/edge_os_api/core/hosted_deployment.py`. A record is admitted only after a
reviewed code change adds its id and canonical SHA-256 to `APPROVED_HOSTED_DEPLOYMENTS`. This candidate adds no entry.

| Field | Constraint |
|---|---|
| `schema_version` | `edge-os.hosted-deployment/1`, or `edge-os.hosted-deployment/2` with `execution_release` |
| `deployment_id` | 1-64 characters, `[A-Za-z0-9][A-Za-z0-9._:-]*` |
| `public_origins` | 1-20 unique HTTPS origins, no wildcard, no path/query/fragment/userinfo |
| `cors_origins` | 1-20 unique HTTPS origins, each also in `public_origins` |
| `database_tls_mode` | `require`, `verify-ca` or `verify-full` |
| `hermes_relay` | Exactly `release_id` and `record_sha256` (lowercase 64-hex) |
| `research_release` | Exactly `release_id` and `sha256` (lowercase 64-hex) |
| `execution_release` | Version 2 only, required there: exactly `release_id` and `sha256` (lowercase 64-hex). Production admits `EDGE_OS_EXECUTION_MODE=controlled` only when this equals the code-owned `APPROVED_ACTUAL_RELEASES` entry. A version 1 record grants no execution. |
| `host_gates` | Exactly `h1_egress`, `h2_runner_isolation`, `h8_provider_spend_cap`, `h10_backup_restore`; each has a `docs/qualification/...` path and a 64-hex SHA-256 |
| `image_digests` | 1-20 entries; lowercase image name -> `sha256:<64 hex>` |
| `valid_from`, `valid_until` | UTC whole seconds `YYYY-MM-DDTHH:MM:SSZ`; `valid_until` after `valid_from` |

The running API must set `EDGE_OS_HOSTED_DEPLOYMENT_ID` and `EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH` together, and the
running CORS origins and TLS mode must equal the record. The builder approves the exact record; the controller records
the approval. Do not add the entry in this task.

## 11. Limits

- No VPS access, SSH, DNS change, secret read, registry login, workflow run, push or deployment happened for this file.
- Local tests and the Compose model are the only evidence here. All host results stay `NOT RUN`.
- The memory limits are proposals for the 12 GB VPS. The hosted load check (H7) stays `NOT RUN`.
- The relay and research worker units are prepared but disabled. Do not enable them before an approved hosted
  deployment and provider release.
- The host research worker's loopback route (`127.0.0.1:5432`, §6.3) is admitted only with a registered hosted
  deployment record whose TLS mode is the URL's `sslmode`. The registry is empty, so the unit is NOT READY and stays
  disabled until the record is registered.
  The Coolify API and both workers in the Coolify stack use `edge-os-postgres:5432` on `private`.
