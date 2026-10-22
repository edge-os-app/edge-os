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
- Production settings refuse a database host named `postgres` (`database_url: the host is Coolify's own database
  alias; use edge-os-postgres`). A deploy that still carries the old URL fails at start, before any query.

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
Worker signing settings belong to the execution lanes; activating them is a later reviewed change.

The worker alone joins `egress`: a bridge with the fixed name `edgeos-egress` and subnet `10.203.0.0/28`. It is
intended for `https://api.privy.io` and the Monad RPC endpoint only.

**Docker cannot restrict by host name.** The network alone allows every destination. The host firewall or an egress
gateway enforces the two destinations. Do not set controlled execution before this rule is installed and its checks
pass.

### 4.1 The exact host rule (iptables backend)

`DOCKER-USER` exists with Docker's iptables firewall backend. With the nftables backend, write the same rules in an
nftables `forward` hook chain at a priority before Docker's. The rule allows DNS to the resolver Docker uses and HTTPS
to the resolved addresses of the two host names; it drops everything else from `edgeos-egress`, including traffic to
the host itself.

```sh
RESOLVER=<the upstream resolver IP Docker uses; see /run/systemd/resolve/resolv.conf>
RPC_HOST=<the Monad RPC host name in the approved execution release>

ipset create edgeos-egress-allow hash:ip family inet -exist

iptables -N EDGE_OS_EGRESS 2>/dev/null || iptables -F EDGE_OS_EGRESS
iptables -A EDGE_OS_EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A EDGE_OS_EGRESS -p udp -d "$RESOLVER" --dport 53 -j RETURN
iptables -A EDGE_OS_EGRESS -p tcp -d "$RESOLVER" --dport 53 -j RETURN
iptables -A EDGE_OS_EGRESS -p tcp --dport 443 -m set --match-set edgeos-egress-allow dst -j RETURN
iptables -A EDGE_OS_EGRESS -j DROP
iptables -C DOCKER-USER -i edgeos-egress -j EDGE_OS_EGRESS 2>/dev/null \
  || iptables -I DOCKER-USER -i edgeos-egress -j EDGE_OS_EGRESS
iptables -C DOCKER-USER -i edgeos-hostdb -j DROP 2>/dev/null || iptables -I DOCKER-USER -i edgeos-hostdb -j DROP

# Nothing from the worker bridge to the host itself (SSH, Coolify, the loopback database).
iptables -C INPUT -i edgeos-egress -j DROP 2>/dev/null || iptables -I INPUT -i edgeos-egress -j DROP
iptables -C INPUT -i edgeos-egress -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null \
  || iptables -I INPUT -i edgeos-egress -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Refresh the allowed addresses (CDN addresses change). Run now and from a root systemd timer every 5 minutes.
ipset create edgeos-egress-next hash:ip family inet -exist
ipset flush edgeos-egress-next
for host in api.privy.io "$RPC_HOST"; do
  getent ahostsv4 "$host" | awk '{print $1}' | sort -u | xargs -r -n1 ipset -exist add edgeos-egress-next
done
ipset swap edgeos-egress-next edgeos-egress-allow
ipset destroy edgeos-egress-next
```

Persist the rules with the host's firewall persistence (for example `netfilter-persistent save`) or a root oneshot
unit ordered `After=docker.service`. The networks are IPv4-only; if IPv6 is enabled on Docker, add the same rules with
`ip6tables` and an `inet6` set.

Limit: an address allowlist admits every name that shares a CDN address with `api.privy.io`. A TLS-inspecting or
SNI-allowlisting egress gateway is stricter; if one is used, route `edgeos-egress` through it and keep the final
`DROP`.

Checks (record the output):

```sh
W=$(docker ps --filter label=com.docker.compose.service=execution-worker --format '{{.Names}}' | head -1)
docker exec "$W" python -c "import urllib.request as u; print(u.urlopen('https://api.privy.io', timeout=5).status)"  # any HTTP status
docker exec "$W" python -c "import urllib.request as u; u.urlopen('https://example.com', timeout=5)"   # must time out
docker exec "$W" python -c "import socket; s=socket.create_connection(('10.203.0.1', 22), 3)"       # must fail
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
until docker exec edge-os-restore-drill pg_isready -U postgres -d edge_os_restore; do sleep 1; done
START=$(date +%s)
docker exec -i edge-os-restore-drill pg_restore -U postgres -d edge_os_restore --no-owner --exit-on-error < "$DUMP"
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
2. Recreate the PostgreSQL certificate with the SANs (§3.1).
3. Change `EDGE_OS_DATABASE_URL` in Coolify to host `edge-os-postgres` (§2), deploy the new compose file, and run the
   alias and loopback checks (§2, §3).
4. Install the egress rule and run its checks (§4.1).
5. Record the evidence files, then hand the record v2 for builder approval. Registration of the record and of the
   execution release are separate reviewed code changes. The host research worker stays disabled until the open
   settings item (§3.2) is resolved.
