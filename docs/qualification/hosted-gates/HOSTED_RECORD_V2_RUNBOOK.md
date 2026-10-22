# Hosted record v2: the execution release, worker egress, database route, backups and caps (NOT RUN)

Status: **files only.** No VPS access, SSH, firewall change, provider call, credential, key or deployment happened
for this file. Every host result below is `NOT RUN` until the operator records it.

This candidate registers no hosted deployment: `APPROVED_HOSTED_DEPLOYMENTS` and `APPROVED_ACTUAL_RELEASES` stay
empty, so production still refuses controlled execution.

Builder decisions (2026-10-22) this file implements:

- Plan A: builder-only in-app trading on the public site.
- B2 option a: the host research worker reaches PostgreSQL over loopback `127.0.0.1:5432`.
- Backups: Contabo snapshots plus an on-VPS restore drill.
- Provider spend caps (H8): documented as sponsored.

## 1. Record v2 and the production gate

`apps/api/src/edge_os_api/core/hosted_deployment.py` accepts two record versions.

| Version | Fields | Execution |
|---|---|---|
| `edge-os.hosted-deployment/1` | The frozen v1 fields | None. A v1 record still parses and admits the relay, `hermes_local` and the research release exactly as before. It binds no execution release and grants no execution. |
| `edge-os.hosted-deployment/2` | The v1 fields plus `execution_release` | `execution_release` holds exactly `release_id` and `sha256` (64 lower-case hex), next to `research_release`. |

```json
"execution_release": {"release_id": "<operating release id>", "sha256": "<64 hex>"}
```

A v1 record that carries `execution_release`, or a v2 record without it, is refused as `hosted_deployment_invalid`.

`core/settings.py` admits `EDGE_OS_EXECUTION_MODE=controlled` in production only when all of these hold:

1. `EDGE_OS_HOSTED_DEPLOYMENT_ID` and `EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH` name a record whose canonical SHA-256 is
   registered in `APPROVED_HOSTED_DEPLOYMENTS`, and it matches the running origins, TLS mode and validity window.
2. The record is v2 and binds an `execution_release`.
3. That `release_id` is registered in `APPROVED_ACTUAL_RELEASES` (`execution/operating_release.py`) with exactly the
   SHA-256 the record binds.

Every other case keeps the refusal, with a named reason and no value:

| Case | Refusal |
|---|---|
| No named record, or the record is refused | `execution_mode: controlled execution needs an approved hosted deployment` (plus the `hosted_deployment: <code>` reason) |
| A v1 record | `execution_mode: the hosted deployment record binds no execution release` |
| Release id not approved, or approved with another SHA-256 | `execution_mode: the record's execution release is not the approved actual execution release` |
| `fixture` | `execution_mode: only the unavailable execution mode is allowed in production` |

The API process never holds the Privy app secret: `load_settings()` refuses any process environment that contains
`EDGE_OS_PRIVY_APP_SECRET`, in every mode, including controlled execution with an approved record. No setting, file,
environment value or request adds an approval; registering a record or a release is a reviewed code change that cites
the builder's approval of that exact hash.

## 2. Database alias: never `postgres`

In the live Coolify deployment the API joins the `coolify` network. On that network Coolify's own database answers to
the alias `postgres`, and our API resolved `postgres` to it.

- `compose.coolify.yml` gives our PostgreSQL the unique alias `edge-os-postgres` on `private`.
- `EDGE_OS_DATABASE_URL` must name that host:
  `postgresql+psycopg://edge_os:<URL-encoded password>@edge-os-postgres:5432/edge_os?sslmode=require`.
- Production settings refuse a database host named `postgres` or `coolify-db`, case-insensitive and with or without
  a trailing dot (`database_url: the host is Coolify's own database alias; use edge-os-postgres`). A deploy that still
  carries the old URL fails at start, before any query.

Host check after the deploy (expect an address from the `private` network, never Coolify's database):

```sh
API=$(docker ps --filter label=com.docker.compose.service=api --format '{{.Names}}' | head -1)
docker exec "$API" python -c "import socket; print(socket.gethostbyname('edge-os-postgres'))"
docker network inspect coolify --format '{{range .Containers}}{{.Name}} {{end}}' | tr ' ' '\n' | grep -i edge-os-postgres \
  && echo "COLLISION: rename" || echo "no edge-os-postgres on coolify"
```

## 3. Loopback route for the host research worker

PostgreSQL publishes `127.0.0.1:5432:5432` only, never on all interfaces (`0.0.0.0`). Docker does not publish a port
for a container attached only to an `internal` network, so the publish lives on `hostdb`: a bridge (`edgeos-hostdb`,
`10.203.0.16/28`) that only PostgreSQL joins, with masquerade off so the database has no route out.

Requirements and checks:

- Docker Engine 28.0 or newer. Older engines let hosts on the same layer-2 segment reach ports published on
  `127.0.0.1`. Check `docker version --format '{{.Server.Version}}'`.
- Coolify must keep the `ports` entry as written. After the deploy: `ss -ltnp | grep 5432` shows only
  `127.0.0.1:5432`; it must not show `0.0.0.0:5432` or `[::]:5432`.
- From another machine, `nc -vz <VPS public IP> 5432` must fail.

### 3.1 TLS certificate SANs

Recreate the server certificate (deploy/coolify/RUNBOOK.md §4) with both names the clients use:

```sh
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 825 \
  -keyout server.key -out server.crt -subj "/CN=edge-os-postgres" \
  -addext "subjectAltName=DNS:edge-os-postgres,IP:127.0.0.1" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"
openssl x509 -in server.crt -noout -ext subjectAltName   # DNS:edge-os-postgres, IP Address:127.0.0.1
```

`DNS:edge-os-postgres` serves the Coolify services; `IP:127.0.0.1` serves the host research worker. With
`sslmode=require` the connection is encrypted but the name is not verified; the SANs make a later `verify-full`
possible. Every process that names the hosted record must use the record's one `database_tls_mode`.

### 3.2 The host research worker URL, and the open settings item

```text
EDGE_OS_DATABASE_URL=postgresql+psycopg://edge_os:<URL-encoded password>@127.0.0.1:5432/edge_os?sslmode=require
```

**Open item (not changed here):** `core/settings.py` refuses a loopback database host in production
(`database_url: production needs a hosted database, not a loopback host`). The host research worker loads the same
settings, so it still refuses this URL. Keep `/etc/edge-os/research-worker.enabled` absent. Enabling the route needs a
separate reviewed change to that refusal, for example admitting a loopback host in production only when an approved
hosted deployment record is named. The builder must approve that change. This candidate does not widen the refusal.

## 4. Execution worker environment and egress

The execution worker has its own environment block (`x-worker-environment`), not the API block. It holds only
`EDGE_OS_ENV`, `EDGE_OS_DATABASE_URL`, `EDGE_OS_PRIVY_APP_ID`, `EDGE_OS_PRIVY_VERIFICATION_KEY`,
`EDGE_OS_CORS_ALLOWED_ORIGINS`, `EDGE_OS_BUILD_SHA`, `EDGE_OS_EXECUTION_MODE` (pinned `unavailable`) and
`EDGE_OS_DATABASE_STATEMENT_TIMEOUT_MS`, plus the three masked `POSTGRES_*` names. It names no Privy app secret.
This guarantee covers the Compose file. If Coolify writes every variable into one shared runtime file, optional
non-secret names such as `EDGE_OS_RESEARCH_BUDGET_*` can still reach the worker; the worker does not read them, and
they cannot be masked with a placeholder because the settings parse them as integers.
Worker signing settings belong to the execution lanes; activating them is a later reviewed change.

The worker alone joins `egress`: a bridge with the fixed name `edgeos-egress` and subnet `10.203.0.0/28`. It is
intended for `https://api.privy.io` and the Monad RPC endpoint only.

**Docker cannot restrict by host name.** The network alone allows every destination. The host firewall or an egress
gateway enforces the two destinations. Do not set controlled execution before this rule is installed and its checks
pass.

### 4.1 The exact host rule (iptables backend)

The rule is `deploy/host/edge-os-egress-firewall.sh`, run as root. It needs Docker's iptables firewall backend
(`DOCKER-USER`); with the nftables backend, write the same rules in an nftables `forward` and `input` hook chain at a
priority before Docker's. The networks are IPv4-only; if IPv6 is enabled in Docker, add the same rules with
`ip6tables`.

What `apply` installs:

| Chain (hooked from) | Rules, in order |
|---|---|
| `EDGE_OS_FWD_A/B` (first rule of `DOCKER-USER`) | `-i edgeos-hostdb -j DROP`; `! -i edgeos-egress -j RETURN`; `ESTABLISHED,RELATED -j RETURN`; UDP and TCP 53 to each upstream resolver `-j RETURN`; TCP to `EDGE_OS_EGRESS_PORTS` (default 443) with `--match-set edgeos-egress-allow dst -j RETURN`; `-j DROP` |
| `EDGE_OS_IN_A/B` (first rule of `INPUT`) | `! -i edgeos-egress -j RETURN`; `ESTABLISHED,RELATED -j ACCEPT`; `-j DROP` |
| `EDGE_OS_IN_DB_A/B` (first rule of `INPUT`) | `! -i edgeos-hostdb -j RETURN`; `ESTABLISHED,RELATED -j ACCEPT`; `-j DROP` |

- The upstream resolvers are every IPv4 `nameserver` in `/run/systemd/resolve/resolv.conf` (or `/etc/resolv.conf`),
  without loopback stubs. Docker's embedded resolver forwards from the container's namespace, so these queries cross
  `edgeos-egress`.
- `edgeos-egress-allow` is a `hash:ip` set with a 900-second entry timeout. `refresh` resolves
  `EDGE_OS_EGRESS_HOSTS` on the host and only adds addresses; an empty answer never clears the set, and an address
  the providers stop using expires. A missing address fails closed (dropped), never open.
- Each re-run builds the idle `_A`/`_B` chain, hooks it first and only then removes the old one, so no hook is ever
  left pointing at an empty chain.
- After `apply`, conntrack entries from `10.203.0.0/28` are deleted, so a connection opened before the rules does not
  survive on the `ESTABLISHED` allowance.
- The `INPUT` chains keep both bridges off host services (SSH, Coolify, the loopback database). Replies to the
  loopback publish still arrive (`ESTABLISHED`).

Install (before the first deploy that puts the worker on `egress`):

```sh
apt-get install -y ipset conntrack
install -m 0600 -o root -g root /dev/null /etc/edge-os/egress.env
cat > /etc/edge-os/egress.env <<'ENV'
EDGE_OS_EGRESS_HOSTS="api.privy.io <the Monad RPC host name in the approved execution release>"
EDGE_OS_EGRESS_PORTS="443"
ENV
install -m 0644 /opt/edge-os/deploy/host/edge-os-egress-firewall.service \
  /opt/edge-os/deploy/host/edge-os-egress-refresh.service \
  /opt/edge-os/deploy/host/edge-os-egress-refresh.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now edge-os-egress-firewall.service edge-os-egress-refresh.timer
```

If the Monad RPC endpoint is not served on 443, add its port to `EDGE_OS_EGRESS_PORTS`. The firewall unit runs before
`docker.service` and is `RequiredBy` it, so after a reboot no container starts before the rules exist. If `apply`
fails (for example, no upstream resolver found), Docker and therefore Coolify do not start; this is deliberate
fail-closed behavior. Fix the cause and run `systemctl start edge-os-egress-firewall docker`. No `ipset` or iptables
persistence package is needed; the unit rebuilds both at every boot.

Limits:

- An address allowlist admits every name that shares a CDN address with `api.privy.io` or the RPC host. A
  TLS-inspecting or SNI-allowlisting egress gateway is stricter; if one is used, route `edgeos-egress` through it and
  keep the final `DROP`.
- DNS to the upstream resolvers allows any query, so DNS tunnelling remains possible from the worker. This is an
  accepted limit. A filtering resolver that answers only for the allowed names would remove it.

Checks (record the output; repeat after a reboot):

```sh
iptables -S DOCKER-USER | head -3; iptables -S INPUT | head -3; ipset list edgeos-egress-allow | head
W=$(docker ps --filter label=com.docker.compose.service=execution-worker --format '{{.Names}}' | head -1)
docker exec "$W" python -c "import urllib.request as u; print(u.urlopen('https://api.privy.io', timeout=5).status)"  # any HTTP status
docker exec "$W" python -c "import urllib.request as u; u.urlopen('https://example.com', timeout=5)"   # must time out
docker exec "$W" python -c "import socket; socket.create_connection(('10.203.0.1', 22), 3)"         # must fail
PG=$(docker ps --filter label=com.docker.compose.service=postgres --format '{{.Names}}' | head -1)
docker exec "$PG" bash -c 'exec 3<>/dev/tcp/10.203.0.17/22' && echo "OPEN: fix" || echo "host closed to postgres"
docker exec "$PG" bash -c 'timeout 5 bash -c "exec 3<>/dev/tcp/1.1.1.1/443"' && echo "OPEN: fix" || echo "no route out"
```

## 5. Backups and the restore drill

Contabo snapshots plus a logical dump and an on-VPS restore drill. A snapshot alone is crash-consistent and can be
rolled back over; it is not the only copy of the data.

### 5.1 Contabo snapshot

1. In the Contabo customer panel, open the VPS and create a snapshot before each deploy that changes the schema and
   at the reviewed cadence. Name it `edge-os-<UTC timestamp>-<build sha>`.
2. Record the snapshot name, time and the plan's snapshot limit. Contabo keeps a limited number of snapshots per VPS;
   delete the oldest only after the newest restore drill passed.

### 5.2 Logical dump (`pg_dump`)

```sh
install -d -m 0700 -o root -g root /var/backups/edge-os
PG=$(docker ps --filter label=com.docker.compose.service=postgres --format '{{.Names}}' | head -1)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec "$PG" pg_dump -Fc -U edge_os -d edge_os > /var/backups/edge-os/edge_os-$STAMP.dump
chmod 0600 /var/backups/edge-os/edge_os-$STAMP.dump
sha256sum /var/backups/edge-os/edge_os-$STAMP.dump
```

The dump sits on the VPS disk, so the next Contabo snapshot carries it. An encrypted copy off the VPS
(deploy/coolify/RUNBOOK.md §8) remains recommended.

### 5.3 Restore drill into a scratch container

The scratch container has no network and no published port. It uses the same PostgreSQL image digest.

```sh
IMAGE=<the deployed postgres image, by digest>
DUMP=/var/backups/edge-os/edge_os-<STAMP>.dump
docker run -d --name edge-os-restore-drill --network none \
  -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" -e POSTGRES_DB=edge_os_restore "$IMAGE"
# Over TCP: the image's temporary init server listens on the Unix socket only, so this waits for the real server.
until docker exec edge-os-restore-drill pg_isready -h 127.0.0.1 -U postgres -d edge_os_restore; do sleep 1; done
START=$(date +%s)
docker exec -i edge-os-restore-drill pg_restore -h 127.0.0.1 -U postgres -d edge_os_restore --no-owner --exit-on-error < "$DUMP"
echo "restore seconds: $(( $(date +%s) - START ))"
docker exec edge-os-restore-drill psql -U postgres -d edge_os_restore -tAc 'select version_num from alembic_version'
docker exec "$PG" psql -U edge_os -d edge_os -tAc 'select version_num from alembic_version'
docker exec edge-os-restore-drill psql -U postgres -d edge_os_restore -tAc \
  "select relname, n_live_tup from pg_stat_user_tables order by relname"
docker rm -f edge-os-restore-drill
```

Pass: `pg_restore` exits 0, both `alembic_version` values are equal, the expected tables exist, and one known row
(for example a saved budget) equals its pre-dump value. Record the dump SHA-256, the recovery point (dump time) and the
measured restore time. The record's `h10_backup_restore` gate references this evidence by path and SHA-256.

## 6. Provider spend caps: sponsored

The provider accounts this deployment uses run on sponsored allocations. No card-backed spend cap is configured; the
sponsor's allocation is the cap. For each provider, record the sponsor, the allocation and where the remaining balance
is visible, in the evidence file the record's `h8_provider_spend_cap` gate references. The application-side caps
(`EDGE_OS_RESEARCH_BUDGET_*`, `EDGE_OS_USAGE_GLOBAL_*`) still apply.

## 7. Operator order

1. Snapshot (§5.1), dump (§5.2) and pass the restore drill (§5.3).
2. Install and enable the host firewall (§4.1) **before** any deploy that puts the worker on `egress`. iptables
   accepts `-i <bridge>` before the bridge exists, so the rules are in place when Docker creates it.
3. Recreate the PostgreSQL certificate with the SANs (§3.1).
4. Change `EDGE_OS_DATABASE_URL` in Coolify to host `edge-os-postgres` (§2), deploy the new compose file, and run the
   alias, loopback (§2, §3) and firewall (§4.1) checks.
5. Record the evidence files, then hand the record v2 for builder approval. Registration of the record and of the
   execution release are separate reviewed code changes. The host research worker stays disabled until the open
   settings item (§3.2) is resolved.
