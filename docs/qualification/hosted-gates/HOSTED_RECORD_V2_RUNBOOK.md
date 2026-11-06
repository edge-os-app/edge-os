# Hosted record v2: the execution release, worker egress, database route, backups and caps (NOT RUN)

Status: **files only.** No VPS access, SSH, firewall change, provider call, credential, key or deployment happened
for this file. Every host result below is `NOT RUN` until the operator records it.

This candidate registers no hosted deployment: `APPROVED_HOSTED_DEPLOYMENTS` and `APPROVED_ACTUAL_RELEASES` stay
empty, so production still refuses controlled execution.

Builder decisions (2026-10-22) this file implements:

- Plan A: builder-only in-app trading on the public site.
- B2 option a: the host research worker reaches PostgreSQL over loopback `127.0.0.1:5432`.
- Option A for that route (2026-10-23): production settings admit `127.0.0.1` only with a registered hosted
  deployment record whose TLS mode equals the URL's `sslmode`.
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

## 1a. Selecting this stack's containers (every host command below)

Coolify's own database is also a Compose service named `postgres` (container `coolify-db`), so a container chosen by
the service label alone can be Coolify's. The block below finds this stack's Compose project from the unique bridge
`edgeos-hostdb` and requires exactly one running container per service. It sets `READY=1` only when every selection
succeeded. If it prints `STOP`, do not run or record any check below.

A negative check (`must_fail`) passes only when the probe ran inside a selected, running container and exited with
its own code 42, which each probe returns only when the connection timed out (the packet was dropped). Every other
result fails: an empty or stopped container, any Docker CLI error (it exits 1, like many probe errors), a refused
connection (the packet reached its target), a DNS error, or a missing command.

```sh
READY=0
PROJECT=$(docker network ls -q --filter driver=bridge | xargs docker network inspect --format \
  '{{index .Options "com.docker.network.bridge.name"}} {{index .Labels "com.docker.compose.project"}}' \
  | awk '$1 == "edgeos-hostdb" {print $2}')
one() {  # one <compose service>: the single container of this stack for that service, or a failure
  ids=$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.service=$1")
  [ "$(printf '%s\n' "$ids" | grep -c .)" -eq 1 ] || { echo "STOP: expected one $1 in '$PROJECT'" >&2; return 1; }
  echo "$ids"
}
[ -n "$PROJECT" ] && API=$(one api) && W=$(one execution-worker) && PG=$(one postgres) && READY=1
[ "$READY" = 1 ] || echo "STOP: selection failed; do not run or record any check below"
running() {  # running <container>: selected and running now
  [ "$READY" = 1 ] && [ -n "$1" ] && [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ]
}
must_fail() {  # must_fail <container> <probe...>: pass only on the probe's own exit code 42 (connection timed out)
  c=$1; shift
  running "$c" || { echo "FAIL: check did not run (container not selected or not running)"; return 1; }
  docker exec "$c" "$@"; rc=$?
  if [ "$rc" -eq 42 ]; then echo "pass: blocked"; else echo "FAIL: not proven blocked ($rc)"; return 1; fi
}
# The probes. Python (worker): resolve first (a DNS failure is not a block), then exit 42 only on a timeout.
PY_PROBE='import socket, sys
addr = socket.gethostbyname(sys.argv[1])
try: socket.create_connection((addr, int(sys.argv[2])), 5)
except TimeoutError: sys.exit(42)'
# Bash (postgres image, which has no python): exit 42 only when `timeout` stopped the connect (code 124).
SH_PROBE='timeout 5 bash -c "exec 3<>/dev/tcp/$0/$1" 2>/dev/null; [ $? -eq 124 ] && exit 42; exit 1'
```

The stack is one per host: the bridge names and subnets are fixed, so a second copy (for example a Coolify preview
deployment) cannot create its networks. Do not enable previews for this resource.

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
# §1a first; READY must be 1.
running "$API" && docker exec "$API" python -c "import socket; print(socket.gethostbyname('edge-os-postgres'))"
docker inspect "$PG" --format '{{(index .NetworkSettings.Networks "'"$PROJECT"'_private").IPAddress}}'  # must be equal
# No container on Coolify's network may carry the name or alias edge-os-postgres. The check fails closed: a failed
# inspect or an empty member list is a FAIL, not a pass.
NET=${COOLIFY_NETWORK:-coolify}
if ! members=$(docker network inspect "$NET" --format '{{range $id, $e := .Containers}}{{$id}} {{end}}') \
    || [ -z "$(printf '%s' "$members" | tr -d ' ')" ]; then
  echo "FAIL: cannot list $NET"
elif for c in $members; do docker inspect "$c" --format \
    '{{.Name}} {{range .NetworkSettings.Networks}}{{.Aliases}} {{.DNSNames}} {{end}}' || echo "inspect-error"; done \
    | grep -iE 'edge-os-postgres|inspect-error'; then
  echo "FAIL: collision or inspect error on $NET"
else
  echo "pass: no edge-os-postgres on $NET"
fi
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
openssl x509 -in server.crt -noout -ext subjectAltName   # DNS:edge-os-postgres, IP Address:127.0.0.1
```

PostgreSQL reads the new certificate on its next restart (redeploy the stack, or `docker restart "$PG"` after §1a).

`DNS:edge-os-postgres` serves the Coolify services; `IP:127.0.0.1` serves the host research worker. With
`sslmode=require` the connection is encrypted but the name is not verified; the SANs make a later `verify-full`
possible. Every process that names the hosted record must use the record's one `database_tls_mode`.

### 3.2 The host research worker URL and the production loopback rule

```text
EDGE_OS_DATABASE_URL=postgresql+psycopg://edge_os:<URL-encoded password>@127.0.0.1:5432/edge_os?sslmode=<record TLS mode>
EDGE_OS_HOSTED_DEPLOYMENT_ID=<the registered deployment id>
EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=<absolute path of that record>
```

Builder decision, option A (2026-10-23). In production, `core/settings.py` admits a loopback database host only when
**all** of these hold:

- the host is exactly `127.0.0.1`;
- the configuration names a hosted deployment record that is registered in `APPROVED_HOSTED_DEPLOYMENTS` and passes
  every record check (hash, origins, TLS mode, validity window);
- the URL's `sslmode` equals the record's `database_tls_mode`.

Every other case keeps the refusal `database_url: production needs a hosted database, not a loopback host`. That
includes no named record, an unregistered or refused record, and an `sslmode` that differs from the record. Without
any DNS lookup, production also refuses these hosts with that reason, record or not:

- a URL with no host (a Unix socket) and a multi-host list such as `127.0.0.1,db.example`;
- `localhost` and any `*.localhost` name in any letter case, with or without a trailing dot;
- every other loopback address: the rest of `127.0.0.0/8`, `127.0.0.1.`, short and legacy IPv4 spellings
  (`127.1`, `2130706433`, `0x7f000001`), `[::1]` in any spelling or with a zone, and IPv4-mapped forms such as
  `[::ffff:127.0.0.1]`;
- the unspecified addresses `0.0.0.0` and `[::]`, including their mapped and short spellings.

Non-loopback hosts and non-production environments are unchanged. The check reads only the URL, so a name that only a
hosts file maps to loopback (for example `ip6-localhost`) is not detected. A version 1 or version 2 record admits the
route; neither changes anything else, and a version 1 record still grants no execution.

The registry is empty in this candidate, so production still refuses the route today. Keep
`/etc/edge-os/research-worker.enabled` absent until the builder's record is registered. The record's one TLS mode
also binds the Coolify services, so they use the same `sslmode` on `edge-os-postgres`.

**Public Hermes route (HERMES-ROUTE-L4).** The Coolify `api` forwards the six paths listed in
`deploy/coolify/RUNBOOK.md` §6.3 to `EDGE_OS_HERMES_APP_URL`. The host application binds `EDGE_OS_APP_BIND_HOST`
(default `127.0.0.1`; the hosted value is the IPv4 `coolify` bridge gateway) and serves only those six paths plus
`GET /healthz` and `GET /readyz`. The record's `host_gates.h2_runner_isolation` evidence file must hold the route, bind,
firewall and public-port checks listed in §6.3. The record's `hermes_relay` field still binds only the release id and
record hash; the route is bound by the H2 evidence hash. Lane 2 writes the evidence file and the record.

## 4. Execution worker environment and egress

The execution worker has its own environment block (`x-worker-environment`), not the API block. It holds only
`EDGE_OS_ENV`, `EDGE_OS_DATABASE_URL`, `EDGE_OS_PRIVY_APP_ID`, `EDGE_OS_PRIVY_VERIFICATION_KEY`,
`EDGE_OS_CORS_ALLOWED_ORIGINS`, `EDGE_OS_BUILD_SHA`, `EDGE_OS_EXECUTION_MODE` (a variable whose default is
`unavailable`), the five worker-only signing settings, `EDGE_OS_DATABASE_STATEMENT_TIMEOUT_MS`, plus the three masked
`POSTGRES_*` names. The five signing settings are:

| Setting | Compose value |
|---|---|
| `EDGE_OS_EXECUTION_PRIVY_APP_ID` | `${EDGE_OS_EXECUTION_PRIVY_APP_ID:-}` |
| `EDGE_OS_EXECUTION_PRIVY_APP_SECRET` | `${EDGE_OS_EXECUTION_PRIVY_APP_SECRET:-}` |
| `EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH` | `${EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH:-/etc/edge-os/execution/agent-authorization.pem}` |
| `EDGE_OS_EXECUTION_SERVER_WALLET_ID` | `${EDGE_OS_EXECUTION_SERVER_WALLET_ID:-}` |
| `EDGE_OS_EXECUTION_MONAD_RPC_URL` | `${EDGE_OS_EXECUTION_MONAD_RPC_URL:-}` |

With `EDGE_OS_EXECUTION_MODE=controlled`, an empty value is refused by
`released_execution_bootstrap.read_worker_execution_settings` at startup, so the worker trades nothing until §4.2 sets
all five. With `unavailable`, the worker starts as today and reads none of them. The API block and the API service name
none of them. `load_settings()` also refuses the unprefixed `EDGE_OS_PRIVY_APP_SECRET` in every process. This guarantee
covers the Compose file. If Coolify writes every variable into one shared runtime file, optional non-secret names such
as `EDGE_OS_RESEARCH_BUDGET_*` can still reach the worker; the worker does not read them, and they cannot be masked
with a placeholder because the settings parse them as integers.

The worker alone joins `egress`: a bridge with the fixed name `edgeos-egress` and subnet `10.203.0.0/28`. It is
intended for `https://api.privy.io` and the Monad RPC endpoint only. The Monad RPC endpoint is the keyless `/rpc` relay
(`https://rpc-a.edgeos.fun/rpc` and `https://rpc-b.edgeos.fun/rpc`, see
[`RPC_RELAY.md`](../inapp-trade/RPC_RELAY.md)). The provider host and its key are never in the worker's allowlist; only
the relay reaches the provider.

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
| `EDGE_OS_FWD_A/B` (first rule of `DOCKER-USER`) | `-i edgeos-hostdb`, `-o edgeos-hostdb`, `-s 10.203.0.16/28` and `-d 10.203.0.16/28` `-j DROP`; `! -i edgeos-egress ! -s 10.203.0.0/28 -j RETURN`; `ESTABLISHED,RELATED -j RETURN`; UDP and TCP 53 to each upstream resolver `-j RETURN`; TCP to `EDGE_OS_EGRESS_PORTS` (default 443) with `--match-set edgeos-egress-allow dst -j RETURN`; `-j DROP` |
| `EDGE_OS_RELAY_MARK_A/B` (first rule of mangle `PREROUTING`) | `-i edgeos-egress -s 10.203.0.0/28 -p tcp --dport 443 --match-set edgeos-egress-relay dst --ctstate NEW -j CONNMARK --set-mark 0x2031` |
| `EDGE_OS_FWD_A/B`, relay rules (after the hostdb drops) | `-o edgeos-egress -d 10.203.0.0/28` and `-i edgeos-egress -s 10.203.0.0/28` with `--mark 0x2031 --ctstate ESTABLISHED,RELATED -j ACCEPT`; `-i edgeos-egress -s 10.203.0.0/28 -p tcp --mark 0x2031 --ctstate DNAT --ctorigdstport 443 -j ACCEPT` |
| `EDGE_OS_IN_A/B` (first rule of `INPUT`) | `! -i edgeos-egress ! -s 10.203.0.0/28 -j RETURN`; `ESTABLISHED,RELATED -j ACCEPT`; `-i edgeos-egress -s 10.203.0.0/28 -p tcp --dport 443 --match-set edgeos-egress-relay dst --dst-type LOCAL --ctstate NEW -j ACCEPT` (the relay through docker-proxy); `-j DROP` |
| `EDGE_OS_IN_DB_A/B` (first rule of `INPUT`) | `! -i edgeos-hostdb ! -s 10.203.0.16/28 -j RETURN`; `ESTABLISHED,RELATED -j ACCEPT`; `-j DROP` |
| `EDGE_OS_IN_PRIVATE_A/B` (first rule of `INPUT`) | `! -i edgeos-private ! -s 10.203.0.64/26 -j RETURN`; `ESTABLISHED,RELATED -j ACCEPT`; `-j DROP` |
| `EDGE_OS_BYPASS_A/B` (first rule of `DOCKER-USER`, `refresh` only) | `-s <address>` and `-d <address>` `-j DROP` for each address the worker and PostgreSQL hold on a network they do not declare |
| `EDGE_OS_BYPASS_IN_A/B` (first rule of `INPUT`, `refresh` only) | for each such address: `-s <address>` `ESTABLISHED,RELATED -j ACCEPT`; `-s <address>` `-j DROP` |

- The upstream resolvers are every IPv4 `nameserver` in the file Docker uses (below), without loopback stubs.
  Docker's embedded resolver forwards from the container's namespace, so these queries cross `edgeos-egress`.
- The relay names (`EDGE_OS_EGRESS_RELAY_HOSTS`) resolve to this host's own public address, where Coolify's Traefik
  publishes port 443. They fill their own set, `edgeos-egress-relay`, never `edgeos-egress-allow`. Docker delivers a
  worker connection there one of two ways, and the rule admits both for TCP 443 only:
  - With Docker's default `userland-proxy: true`, Docker's per-bridge "skip DNAT" rule leaves it un-DNATed; it
    reaches `docker-proxy` through `INPUT`, where `EDGE_OS_IN` accepts new TCP 443 to a local relay address.
  - With `userland-proxy: false`, Docker DNATs it to Traefik on another bridge. It is marked in mangle `PREROUTING`
    while its destination is still a relay address; only that marked, DNATed flow from original port 443 is accepted,
    in both directions, ahead of Docker's inter-bridge isolation.

  Either way Traefik sees a host bridge gateway as the source (docker-proxy's connection or Docker's masquerade): the
  gateway of the network that carries Traefik's published port, which the relay's `ipallowlist` lists with every
  other network `coolify-proxy` joins (see `RPC_RELAY.md`, deploy step 3). A relay name that stops resolving to this host is dropped.
- `edgeos-egress-allow` is a `hash:ip` set with a 900-second entry timeout. `refresh` resolves
  `EDGE_OS_EGRESS_HOSTS` on the host and only adds addresses; an empty answer never clears the set, and an address
  the providers stop using expires. A missing address fails closed (dropped), never open.
- Each re-run builds the idle `_A`/`_B` chain, hooks it first and only then removes the old one, so no hook is ever
  left pointing at an empty chain.
- Every rule matches the bridge name or its fixed subnet, so a bridge that loses its fixed name is still filtered.
- After `apply`, conntrack entries from both subnets are deleted, so a connection opened before the rules does not
  survive on the `ESTABLISHED` allowance. `conntrack` is required; a failed flush fails `apply`.
- `apply` holds a lock (`flock`), so two runs never build the same idle chain at once.
- Both networks set `enable_ipv6: false`, so the IPv4 rules cover them.
- Docker Engine 29 prints an unset endpoint address as the text `invalid IP`; `refresh` reads that text and an empty
  field as no address, and refuses any IPv4 field that is not a dotted quad.
- `apply` and `refresh` load `br_netfilter` and set `net.bridge.bridge-nf-call-iptables=1` and
  `net.bridge.bridge-nf-call-ip6tables=1` before the address rules, then read both values back. A missing module or
  a value other than `1` fails the unit (so Docker does not start) or the refresh, with a named message. Docker's
  per-bridge `DOCKER-FORWARD` acceptance keeps ordinary same-bridge traffic on the API/web and Coolify bridges
  working; the `EDGE_OS_BYPASS` rules above then also drop worker and PostgreSQL frames switched inside the injected
  bridge. `apply` runs before Docker at every boot and `refresh` re-asserts the setting every five minutes.
- The `INPUT` chains keep all three bridges (`edgeos-egress`, `edgeos-hostdb`, `edgeos-private`) off host services
  (SSH, Coolify, the loopback database). Replies to the loopback publish still arrive (`ESTABLISHED`).
- The upstream resolvers follow Docker's rule: `/run/systemd/resolve/resolv.conf` only when `/etc/resolv.conf` names
  loopback stubs only; otherwise `/etc/resolv.conf`.
- Coolify also attaches its own resource network (named the resource UUID, 10.0.x.0/24, NAT) to every container.
  The Compose file sets `gw_priority: 1000` on the worker's `egress` and PostgreSQL's `hostdb`. Docker Compose maps
  `gw_priority` to the engine's `GwPriority`; the engine selects the default gateway from the highest value. The
  generic `priority` field only orders network attachment and does **not** select the default route on the tested
  engine. Before a deploy, render `compose.deployed.yml` with the host's `docker compose config`: a rejected
  `gw_priority` stops the deploy. After the deploy, `docker inspect` must show `GwPriority=1000` on `egress` and
  `hostdb` (checks below). Because `apply` runs before Docker, only `refresh` inspects containers. It derives the
  Compose project from the `edgeos-hostdb` bridge label, exactly as §1a does: Coolify starts a Service with
  `--project-name <service uuid>`, so the Compose file name is not the project name. It then finds `execution-worker`
  and `postgres` by that project and their `com.docker.compose.service` labels, reads the address each holds on every
  network it does not declare, and installs the `EDGE_OS_BYPASS` rules. The idle no-op happens only when no fixed
  bridges and no `execution-worker` or `postgres` service container exist (before the first deploy). On a fresh
  Coolify host, Coolify's own `coolify-db` is a Compose service named `postgres`, so the pre-deploy refresh fails
  closed and logs until this stack's fixed bridges exist; that is expected, and the timer retries. A fixed bridge without a project label, a missing or duplicate
  container, a container not on its declared networks, an optional `EDGE_OS_COMPOSE_PROJECT` that differs from the
  bridge label, an unreachable daemon or an IPv6 address on the extra network fails `refresh`; it never passes
  silently or reports success with empty rules.
- A residual window remains after a fresh deploy: the address rules exist once the next `refresh` runs (the timer
  runs every five minutes, or `systemctl start edge-os-egress-refresh` runs it now). No reliable host-side event
  hook exists without a Docker event watcher, so none is added. Until the rules exist the worker's `egress` default
  route and the route guard below keep the internet off the extra network; the §4.1 checks are the gate before
  controlled execution is enabled.

Install (before the first deploy that puts the worker on `egress`):

```sh
apt-get install -y ipset conntrack
install -d -m 0755 -o root -g root /etc/edge-os
install -m 0600 -o root -g root /dev/null /etc/edge-os/egress.env
cat > /etc/edge-os/egress.env <<'ENV'
EDGE_OS_EGRESS_HOSTS="api.privy.io"
EDGE_OS_EGRESS_RELAY_HOSTS="rpc-a.edgeos.fun rpc-b.edgeos.fun"
EDGE_OS_EGRESS_PORTS="443"
# Optional cross-check. Leave it unset: refresh derives the project from the edgeos-hostdb bridge label (§1a).
# If set, it must equal that label, or refresh fails. Do not set the Compose file name `edge-os` as a guess.
# EDGE_OS_COMPOSE_PROJECT="<the com.docker.compose.project label from §1a>"
ENV
# Root-owned copy: the unit never runs a script from the git checkout, which other steps switch between commits.
install -m 0755 -o root -g root /opt/edge-os/deploy/host/edge-os-egress-firewall.sh /usr/local/sbin/edge-os-egress-firewall
install -m 0644 /opt/edge-os/deploy/host/edge-os-egress-firewall.service \
  /opt/edge-os/deploy/host/edge-os-egress-refresh.service \
  /opt/edge-os/deploy/host/edge-os-egress-refresh.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now edge-os-egress-firewall.service edge-os-egress-refresh.timer
```

The relay is served on 443 only; `EDGE_OS_EGRESS_PORTS` does not apply to the relay rule. The firewall unit runs before
`docker.service` and is `RequiredBy` it, so after a reboot no container starts before the rules exist. If `apply`
fails (for example, no upstream resolver found), Docker and therefore Coolify do not start; this is deliberate
fail-closed behavior. Fix the cause and run `systemctl start edge-os-egress-firewall docker`. No `ipset` or iptables
persistence package is needed; the unit rebuilds both at every boot. The unit has no `Condition*` line on purpose: a
failed condition would skip it as a success and let Docker start without rules.

To re-apply after editing `egress.env`, run `systemctl reload edge-os-egress-firewall` (it runs `apply` without
touching Docker). Do not `restart` the unit: `RequiredBy=docker.service` also restarts Docker and every container. A
host removed from `EDGE_OS_EGRESS_HOSTS` keeps its addresses allowed until their 900-second entries expire; to cut it
off at once, `ipset flush edgeos-egress-allow` and then `systemctl start edge-os-egress-refresh`. Every `apply`
(including `reload`) deletes the conntrack entries of both subnets, so the worker's open connections, allowed ones
included, are cut and reconnect; the loopback database sessions recover on their next packet. After changing the
script in the repository, install it again to `/usr/local/sbin/edge-os-egress-firewall` and reload.

Limits:

- An address allowlist admits every name that shares a CDN address with `api.privy.io`. The relay rule admits every
  name Traefik serves on this host (for example `api.edgeos.fun`); only the relay routes check the worker's source. A
  TLS-inspecting or SNI-allowlisting egress gateway is stricter; if one is used, route `edgeos-egress` through it and
  keep the final `DROP`.
- The set holds what the host resolves. A rotating CDN name can answer the worker's resolver with an address the
  host has not seen yet; that connection is dropped until the next refresh (at most 5 minutes). This fails closed.
- DNS to the upstream resolvers allows any query, so DNS tunnelling remains possible from the worker. This is an
  accepted limit. A filtering resolver that answers only for the allowed names would remove it.

Checks (record the output; repeat after a reboot):

```sh
# §1a first; READY must be 1.
ip link show edgeos-egress && ip link show edgeos-hostdb && ip link show edgeos-private  # the fixed bridge names
iptables -S DOCKER-USER | head -3; iptables -S INPUT | head -3; ipset list edgeos-egress-allow | head
# Coolify may also attach its resource network. Prove that it carries no route instead of removing it.
# The timer does this every 5 minutes. A failed oneshot makes `systemctl start` fail; a successful oneshot is
# inactive (dead), so check its recorded Result, not is-active.
systemctl start edge-os-egress-refresh || echo "STOP: refresh failed; read its journal"
[ "$(systemctl show -p Result --value edge-os-egress-refresh)" = success ] \
  || echo "STOP: refresh did not record success"
# `refresh` must record success only after it found the stack by the edgeos-hostdb label and installed the rules.
docker inspect "$W" --format '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} {{end}}'   # <PROJECT>_private <PROJECT>_egress, plus the resource network when attached
docker inspect "$PG" --format '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} {{end}}'  # <PROJECT>_private <PROJECT>_hostdb, plus the resource network when attached
iptables -S EDGE_OS_BYPASS; iptables -S EDGE_OS_BYPASS_IN   # one DROP pair and one INPUT pair per injected address
docker inspect "$W" --format '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} GwPriority={{$e.GwPriority}}{{"\n"}}{{end}}'   # egress 1000
docker inspect "$PG" --format '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} GwPriority={{$e.GwPriority}}{{"\n"}}{{end}}'  # hostdb 1000
docker exec "$W" cat /proc/net/route    # one default route: gateway 0100CB0A (10.203.0.1)
docker exec "$PG" cat /proc/net/route   # one default route: gateway 1100CB0A (10.203.0.17)
INJECTED=$(docker inspect "$W" --format '{{range $n, $_ := .NetworkSettings.Networks}}{{$n}}{{"\n"}}{{end}}' \
  | grep -v -x -e "${PROJECT}_private" -e "${PROJECT}_egress")
for net in $INJECTED; do must_fail "$W" python -c "$PY_PROBE" \
  "$(docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}')" 22; done
# Same-bridge: with br_netfilter (§4.1) the worker must not reach Coolify's proxy on the injected network.
STACK_NET=$(printf '%s\n' $INJECTED | awk 'NR == 1')
PROXY_IP=$(docker inspect coolify-proxy --format '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} {{$e.IPAddress}}{{"\n"}}{{end}}' \
  | awk -v n="$STACK_NET" '$1 == n {print $2}')
if [ -n "$PROXY_IP" ]; then must_fail "$W" python -c "$PY_PROBE" "$PROXY_IP" 80
else echo "FAIL: coolify-proxy has no address on $STACK_NET"; fi
running "$W" && docker exec "$W" python -c "
import urllib.error as e, urllib.request as u
try: print(u.urlopen('https://api.privy.io', timeout=5).status)
except e.HTTPError as error: print(error.code)"                                                       # any HTTP status
GW=$(docker network inspect "${PROJECT}_private" --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}')
running "$W" && docker exec "$W" python -c "
import json, urllib.request as u
r = u.Request('https://rpc-a.edgeos.fun/rpc', data=b'{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"eth_chainId\",\"params\":[]}',
              headers={'Content-Type': 'application/json'})
print(json.load(u.urlopen(r, timeout=10))['result'])"                                                # 0x8f (chain 143), RPC_RELAY.md
must_fail "$W" python -c "$PY_PROBE" example.com 443       # the internet beyond the allowlist
must_fail "$W" python -c "$PY_PROBE" 10.203.0.1 22         # the host, through the egress gateway
[ -z "$GW" ] || must_fail "$W" python -c "$PY_PROBE" "$GW" 22   # the host, through the private gateway, if any
must_fail "$PG" bash -c "$SH_PROBE" 10.203.0.17 22         # the host, through the hostdb gateway
must_fail "$PG" bash -c "$SH_PROBE" 1.1.1.1 443            # the internet, from PostgreSQL
```

Every `must_fail` line must print `pass: blocked`. Any `FAIL` line is a failed check: fix the cause, never record it
as blocked. A refused connection (`FAIL: not proven blocked (1)`) means the packet reached its target.

The route tables are the proof for the Coolify resource network: no default route may name anything except `0100CB0A`
in the worker and `1100CB0A` in PostgreSQL. The worker refuses `EDGE_OS_EXECUTION_MODE=controlled` with
`EXECUTION_BOOTSTRAP_ROUTE_UNEXPECTED` (or `EXECUTION_BOOTSTRAP_ROUTE_UNREADABLE`) otherwise, before it reads a key.
Both healthchecks fail the same way on an extra default route. This depends on the host's Compose accepting
`gw_priority` and mapping it to the engine's `GwPriority`, and on Coolify 4.4.7 preserving it. The `GwPriority=1000`
lines above are the direct evidence; if a deploy shows `GwPriority=0`, an extra default route or a rejected key, do
not enable controlled execution and report it before a repair. The route guard and these checks read the IPv4
`/proc/net/route`; the declared networks set `enable_ipv6: false`, and `refresh` fails loudly on an IPv6 address on
an extra network. If Docker's IPv6 is enabled, add the `ip6tables` rules named at the top of §4.1. The extra network
is never removed by hand: a redeploy re-attaches it, and these checks must pass with no manual detach step.

### 4.2 Turning on controlled execution

Do the steps in this order. Execution stays off while `EDGE_OS_EXECUTION_MODE` is `unavailable`: the worker starts
as today and reads no key. After step 3 sets `controlled`, a missing or invalid value refuses with a named
`EXECUTION_BOOTSTRAP_*` code and the worker sends nothing.

**Precondition, before any redeploy of this commit.** Create the empty root-owned directory that the worker mounts
read-only. The key file is not needed for a deploy with execution off:

```sh
install -d -m 0755 -o root -g root /etc/edge-os/execution
stat -c '%F %U %G %a' /etc/edge-os/execution    # must print: directory root root 755
```

The Compose mount source is this directory, never the key file. A deploy with no key file starts the worker and leaves
the key path absent. Docker creates a missing directory source as an empty directory; run the command above so the
ownership and mode are explicit. Do not mount the key file directly.

1. Register the v2 record.
2. Install the key file.
3. Set the Coolify variables.
4. Redeploy the stack.
5. Check the result.

**1. Register the v2 record.** Write the record with `execution_release` set to the exact release id and SHA-256 of
the one execution release, then add its canonical SHA-256 to `APPROVED_HOSTED_DEPLOYMENTS` and the release to
`APPROVED_ACTUAL_RELEASES` in a reviewed code change. §1 lists the three conditions. Until this step, production
refuses `EDGE_OS_EXECUTION_MODE=controlled`.

**2. Install the key file.** Put the P-256 authorization key on the host. The API image runs as uid `10001`, so that
user owns the file, the directory stays root-owned, and the file has mode `0600`:

```sh
test ! -d /etc/edge-os/execution/agent-authorization.pem
install -m 0600 -o 10001 -g 10001 /root/agent-authorization.pem /etc/edge-os/execution/agent-authorization.pem
chown 10001:10001 /etc/edge-os/execution/agent-authorization.pem
chmod 0600 /etc/edge-os/execution/agent-authorization.pem
stat -c '%F %u %g %a' /etc/edge-os/execution/agent-authorization.pem   # must print: regular file 10001 10001 600
```

The host path is `/etc/edge-os/execution/agent-authorization.pem`; it is the value of
`EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH` and it lives inside the read-only directory mount. A directory at that
path is refused by the guard and by the bootstrap. The bootstrap checks the file the path resolves to: it refuses a
non-regular file, a foreign owner or any group/other permission bit. It does not reject a symlink that resolves to a
compliant file, so the `%F` check above (`regular file`) is the symlink guard. Do not use a symlink. Do not keep a
copy in the checkout.

**3. Set the Coolify variables.** Add these values to the execution worker only. Never add them to the API service:

| Variable | Value |
|---|---|
| `EDGE_OS_EXECUTION_MODE` | `controlled` |
| `EDGE_OS_EXECUTION_PRIVY_APP_ID` | the execution app id |
| `EDGE_OS_EXECUTION_PRIVY_APP_SECRET` | the execution app secret |
| `EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH` | `/etc/edge-os/execution/agent-authorization.pem` |
| `EDGE_OS_EXECUTION_SERVER_WALLET_ID` | the server wallet id the record binds |
| `EDGE_OS_EXECUTION_MONAD_RPC_URL` | the `https` RPC URL the record binds |

Coolify must scope these six values to the execution worker. Do not put them in a shared runtime file that also
reaches the API service. The Compose file cannot control what Coolify injects at run time.

**4. Redeploy the stack.** Redeploy from the reviewed commit. The API and worker start under the same record; only the
worker receives the signing values and the key directory mount.

**5. Check the result.**

```sh
# §1a first; READY must be 1.
running "$W" && docker inspect "$W" --format '{{.Config.User}} {{range .Mounts}}{{.Source}}->{{.Destination}} {{.RW}}{{end}}'
# The user is 10001:10001; the source is /etc/edge-os/execution (a directory) and RW is false.
running "$W" && docker exec "$W" printenv EDGE_OS_EXECUTION_MODE     # controlled
running "$W" && docker exec "$W" stat -c '%F %u %g %a' /etc/edge-os/execution/agent-authorization.pem
# must print: regular file 10001 10001 600
if running "$W" && docker logs --tail 100 "$W" > /tmp/edge-os-worker.log 2>&1; then
  grep EXECUTION_BOOTSTRAP_ /tmp/edge-os-worker.log || echo "no bootstrap refusal"
else
  echo "FAIL: cannot read the worker log"
fi
```

A healthy worker with no `EXECUTION_BOOTSTRAP_*` line means admission passed. Any refusal line names the failed
condition; fix that condition and redeploy. A `FAIL` line is a failed check, never a pass. The API service keeps its
own pinned `EDGE_OS_EXECUTION_MODE=unavailable` and must show none of the five signing names:

```sh
if running "$API" && docker inspect "$API" --format '{{range .Config.Env}}{{println .}}{{end}}' > /tmp/edge-os-api.env; then
  grep -E '^EDGE_OS_EXECUTION_(PRIVY_APP_ID|PRIVY_APP_SECRET|AUTHORIZATION_KEY_PATH|SERVER_WALLET_ID|MONAD_RPC_URL)=' \
    /tmp/edge-os-api.env || echo "API holds no signing setting"
else
  echo "FAIL: cannot read the API environment"
fi
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
# §1a first; READY must be 1.
install -d -m 0700 -o root -g root /var/backups/edge-os
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP=/var/backups/edge-os/edge_os-$STAMP.dump
if running "$PG" && (umask 077; docker exec "$PG" pg_dump -Fc -U edge_os -d edge_os > "$DUMP") \
    && docker exec -i "$PG" pg_restore -l < "$DUMP" > /dev/null; then
  echo "pass: dump readable"; sha256sum "$DUMP"
else
  echo "FAIL: no usable dump"; rm -f "$DUMP"
fi
```

The dump sits on the VPS disk, so the next Contabo snapshot carries it. An encrypted copy off the VPS
(deploy/coolify/RUNBOOK.md §8) remains recommended.

### 5.3 Restore drill into a scratch container

The scratch container has no network and no published port. It uses the same PostgreSQL image digest.

```sh
IMAGE=<the deployed postgres image, by digest>
DUMP=/var/backups/edge-os/edge_os-<STAMP>.dump   # and §1a first (PG)
docker rm -fv edge-os-restore-drill 2>/dev/null   # never restore into a stale drill container
docker run -d --name edge-os-restore-drill --network none \
  -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" -e POSTGRES_DB=edge_os_restore "$IMAGE"
# Over TCP: the image's temporary init server listens on the Unix socket only, so this waits for the real server.
# Bounded: stop after 120 seconds (a wrong image or a crash would otherwise wait forever).
for _ in $(seq 120); do
  docker exec edge-os-restore-drill pg_isready -h 127.0.0.1 -U postgres -d edge_os_restore && break; sleep 1
done
START=$(date +%s)
docker exec -i edge-os-restore-drill pg_restore -h 127.0.0.1 -U postgres -d edge_os_restore --no-owner --exit-on-error < "$DUMP"
echo "restore seconds: $(( $(date +%s) - START ))"
docker exec edge-os-restore-drill psql -U postgres -d edge_os_restore -tAc 'select version_num from alembic_version'
docker exec "$PG" psql -U edge_os -d edge_os -tAc 'select version_num from alembic_version'
docker exec edge-os-restore-drill psql -U postgres -d edge_os_restore -tAc \
  "select relname, n_live_tup from pg_stat_user_tables order by relname"
docker rm -fv edge-os-restore-drill   # -v also removes the anonymous data volume holding the restored copy
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
   execution release are separate reviewed code changes. The host research worker stays disabled until that record
   is registered and its URL meets §3.2.

## 8. Fill, hash and register one record

This section builds the version 1 (research-only) record. A version 2 record that also binds execution uses the same
steps, but this tool refuses `execution_release` on purpose.

### 8.1 Fill the values file

Copy this object and replace every placeholder. The tool sets `schema_version` itself, so the values file omits it and
must not carry `execution_release`.

```json
{
  "deployment_id": "edgeos-fun-vps1",
  "public_origins": ["https://app.edgeos.fun"],
  "cors_origins": ["https://app.edgeos.fun"],
  "database_tls_mode": "require",
  "hermes_relay": {"release_id": "hermes-first-call-1", "record_sha256": "<64 hex>"},
  "research_release": {"release_id": "actual-moe-history2h-nansen-20261022/1", "sha256": "<64 hex>"},
  "host_gates": {
    "h1_egress": {"path": "docs/qualification/hosted-gates/evidence/h1_egress.md", "sha256": "<64 hex>"},
    "h2_runner_isolation": {"path": "docs/qualification/hosted-gates/evidence/h2_runner_isolation.md", "sha256": "<64 hex>"},
    "h8_provider_spend_cap": {"path": "docs/qualification/hosted-gates/evidence/h8_provider_spend_cap.md", "sha256": "<64 hex>"},
    "h10_backup_restore": {"path": "docs/qualification/hosted-gates/evidence/h10_backup_restore.md", "sha256": "<64 hex>"}
  },
  "image_digests": {"postgres": "sha256:<64 hex>"},
  "valid_from": "2026-10-23T00:00:00Z",
  "valid_until": "2026-11-23T00:00:00Z"
}
```

The four gate paths must stay under `docs/qualification/`. Each declared `sha256` is the SHA-256 of the exact file
bytes, so fill the evidence files first and never edit them after the record is registered.

### 8.2 Hash and validate

From `apps/api`, with the repository root as `--root`:

```sh
uv run --frozen python -m edge_os_api.core.hosted_record_tool \
  --values ../../docs/qualification/hosted-gates/records/edgeos-fun-vps1.values.json --root ../..
```

The tool writes nothing and uses no network. It:

1. refuses a values file that is not one strict JSON object, that carries a version 2 field, or that does not hold
   exactly the version 1 fields;
2. reads each gate file inside the root and refuses a missing file, a path that leaves the root, or bytes whose hash
   differs from the declared hash;
3. builds the canonical record and validates it with the production parser in `core.hosted_deployment`;
4. prints three lines: the canonical record JSON, `sha256 <64 hex>`, and the exact registry line.

An exit code of 1 is a refusal. The message names the code and never a field value. The tool reads at most 64 KiB for
the values file and 1 MiB for each gate file, and refuses a larger file.

### 8.3 Register

1. Save the printed record line (no trailing newline) as
   `docs/qualification/hosted-gates/records/<deployment_id>.json` and copy it to the absolute path the runtime reads.
2. Set `EDGE_OS_HOSTED_DEPLOYMENT_ID` and `EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH` together.
3. Replace the empty registry in `apps/api/src/edge_os_api/core/hosted_deployment.py` with the printed line, keeping
   the module's annotation:
   `APPROVED_HOSTED_DEPLOYMENTS: Mapping[str, str] = {"edgeos-fun-vps1": "<64 hex>"}`.
4. Add a test that pins the exact deployment id and hash, so any edit fails.
5. Run the full API suite before the candidate is reviewed.

A record is immutable once approved. Any change to a field, a gate file or an evidence byte changes the canonical
hash and needs a new reviewed registry entry. Never hand-edit the hash: rerun the tool.

### 8.4 What `image_digests` pins

The registry line is source code, so every image built from the registered source tree carries the record hash and its
image id depends on that hash. The record cannot name such an image, because the hash would then depend on the image id
that depends on the hash. Pin only images that do not carry the registry hash, for example the PostgreSQL image id the
VPS runs, and a host relay job image only when its build context does not contain
`apps/api/src/edge_os_api/core/hosted_deployment.py`. Omit `api`, `execution-worker` and every other source-built
image. The parser still requires at least one entry.

## 9. Replace the record and switch the host to Orbio

Status: **files only, NOT RUN.** The controller runs these steps after the gate PASS. Builder decision, 2026-11-06:
skip OpenRouter on the server, go straight to a hosted Orbio record, and copy the Orbio key to the server when the record
passes. The first real Orbio study still runs locally.

### 9.1 The replacement record

`records/edgeos-fun-vps1-orbio.json`, canonical SHA-256
`c0c0f07c9787c7487a823951954afdf5979e71d13e9cfde09a340502b65062dd`, replaces `edgeos-fun-vps1` in
`APPROVED_HOSTED_DEPLOYMENTS`. The id is new because §8.3 names the file after the id, and the old file stays frozen.
The old record files are unchanged history. They admit nothing after this build.

| Field | Old record | New record |
|---|---|---|
| `deployment_id` | `edgeos-fun-vps1` | `edgeos-fun-vps1-orbio` |
| `hermes_relay` | `hermes-first-call-1`, `3fa94dd7…` | `orbio-first-call-1`, `041f588d…` |
| `host_gates.h8_provider_spend_cap` | `h8_provider_spend_cap.md` | `h8_provider_spend_cap_orbio.md` |
| `valid_from` | `2026-10-30T00:00:00Z` | `2026-11-06T00:00:00Z` |

Every other field is the same, which includes `research_release`, `image_digests` and `valid_until`. `valid_until` stays
`2026-11-27T00:00:00Z`, before the snapshot's auto-deletion on 2026-11-29 (H10). The `hermes-relay-job` id is the amd64 id
in `_PINNED_IMAGES`, which both releases use. The `postgres` id is the one in the compose file deployed on 2026-11-06.

The Coolify services name no record, because `compose.coolify.yml` does not pass the two record settings. Only the host
application and the host research worker read this record. The switch therefore needs no new API image.

### 9.2 Host gates against Orbio

| Gate | File | Specific to OpenRouter? | Result |
|---|---|---|---|
| H1 | `h1_egress.md`, unchanged | No. It names neither OpenRouter nor Orbio. It tests the execution worker and PostgreSQL only. | Still true for what it tests. It never tested the relay's route to a provider, for either release. That route runs on the relay's own `relay-egress-*` network, and only the gateway code limits it to the record's host. §9.3 step 1 shows that the host reaches `api.orbio.so` from Docker's default bridge; the relay's own path first runs on a paid call. The H1 run predates the redeploy of 2026-11-06. |
| H2 | `h2_runner_isolation.md`, unchanged | Partly. Row 6 tests `/etc/edge-os/relay/provider-key` and the `run-2` paths. | Row 6 does not cover the Orbio key file or the new run root. §9.3 step 8 repeats it on those paths. The rows marked PENDING stay PENDING, and decision N5 still applies (§9.4). |
| H8 | `h8_provider_spend_cap_orbio.md`, new | The old file names no model provider at all. | The new file adds Orbio and states the limits. The prepaid balance is not a proven hard stop. |
| H10 | `h10_backup_restore.md`, unchanged | No. | Unchanged. The drill ran on schema `0013`; the live schema is now `0015`. |

No gate needs new host evidence before registration. The host application cannot start under a record until that record
is registered, so the host results of §9.3 go to a separate evidence file outside the record, as N5 requires. Do not edit
a bound file after registration.

### 9.3 Switch steps

Preconditions: the controller accepted the candidate, the builder approved this exact record hash, and the commit is on
the remote. `EDGE_OS_HERMES_APP_URL` stays empty for every step here, so the six public paths keep returning 503. No step
below prints the key. Do not use `set -x`, and do not `cat` the key file.

**1. Check TLS from the host.** Nothing has changed yet, so a failure here costs nothing. Use the command in
`ORBIO_RELEASE_DRAFT.md` §8 with the amd64 image id, from `/opt/edge-os`. It must exit 0.

**2. Stop the old services.** Stop the relay while `/etc/edge-os/relay.json` still names the old operation, because the
unit's stop command reads that file.

```sh
systemctl stop edge-os-hermes-app.service edge-os-research-worker.service
systemctl stop edge-os-hermes-relay.service
docker ps --filter name=relay- --format '{{.Names}}'   # must print nothing
```

If a `relay-*` container remains, the operation did not start from the unit. Run the unit's `ExecStop` command as
`edge-os-relay`, with the unit's environment, before you continue.

**3. Move the code.** Use §6.2 of `deploy/coolify/RUNBOOK.md` with the approved commit. Then confirm the registry:

```sh
grep -c '"edgeos-fun-vps1-orbio": "c0c0f07c9787c7487a823951954afdf5979e71d13e9cfde09a340502b65062dd"' \
  /opt/edge-os/apps/api/src/edge_os_api/core/hosted_deployment.py   # must print 1
```

**4. Install the record.** Keep the old file. The new file takes the old file's owner and mode. A repeat of this step is
safe: it never replaces a backup, and it reads the old path from the backup. The block stops at its first failure.

```sh
(
  set -eu
  for f in /etc/edge-os/hermes-app.env /etc/edge-os/research-worker.env; do
    [ -e "$f.bak-before-orbio" ] || cp -p "$f" "$f.bak-before-orbio"
  done
  OLD=$(sed -n 's/^EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=//p' /etc/edge-os/hermes-app.env.bak-before-orbio)
  NEW=/etc/edge-os/hosted/edgeos-fun-vps1-orbio.json
  SRC=/opt/edge-os/docs/qualification/hosted-gates/records/edgeos-fun-vps1-orbio.json
  install -m "$(stat -c %a "$OLD")" -o "$(stat -c %U "$OLD")" -g "$(stat -c %G "$OLD")" "$SRC" "$NEW"
  cmp "$SRC" "$NEW"
  for f in /etc/edge-os/hermes-app.env /etc/edge-os/research-worker.env; do
    sed -i -e 's/^EDGE_OS_HOSTED_DEPLOYMENT_ID=.*/EDGE_OS_HOSTED_DEPLOYMENT_ID=edgeos-fun-vps1-orbio/' \
           -e "s|^EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=.*|EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=$NEW|" "$f"
    [ "$(grep -c '^EDGE_OS_HOSTED_DEPLOYMENT_' "$f")" = 2 ]
  done
  echo "record installed"
)   # must print: record installed
```

**5. Copy the key.** Run this from the machine that holds the key. It uses a new file, so it overwrites no key on the
host. The key travels on standard input and appears in no argument and no output.

```sh
KEY=$HOME/.edge-os/orbio.key
HOST=<operator ssh target>
ssh "$HOST" 'set -eu; D=/etc/edge-os/relay/orbio-provider-key; test ! -e "$D"
  T=$(mktemp /etc/edge-os/relay/.orbio-key.XXXXXX); trap "rm -f \"\$T\"" EXIT; cat > "$T"
  chown edge-os-relay:edge-os-relay "$T"; chmod 0600 "$T"; mv "$T" "$D"' < "$KEY"
ssh "$HOST" 'stat -c "%F %U %G %a" /etc/edge-os/relay/orbio-provider-key'
# must print: regular file edge-os-relay edge-os-relay 600
HERE=$(shasum -a 256 < "$KEY" | cut -d' ' -f1)
THERE=$(ssh "$HOST" 'sha256sum < /etc/edge-os/relay/orbio-provider-key | cut -d" " -f1')
[ "${#HERE}" -eq 64 ] && [ "$HERE" = "$THERE" ] && echo same || echo different   # must print: same
```

**6. Hand the relay to the Orbio release.** Keep a copy of the old configuration, then change its content only, so the
file keeps its owner and mode. The CA bundle is the tracked file, so the host needs no CA copy. `RUN` is 1 on the first
try. A used run root or channel folder cannot start again, so raise `RUN` on each repeat and use the same value in step 8.

```sh
RUN=1
[ -e /etc/edge-os/relay.json.bak-before-orbio ] || cp -p /etc/edge-os/relay.json /etc/edge-os/relay.json.bak-before-orbio
RUN=$RUN python3 - <<'PY'
import json, os
run = os.environ["RUN"]
path = "/etc/edge-os/relay.json"
config = json.load(open(path))
folder = "/opt/edge-os/docs/qualification/orbio-release"
config.update({
    "operation_id": f"orbio-hosted-{run}",
    "release_record": {"path": f"{folder}/orbio_first_call_record.json",
                       "sha256": "041f588d3b9564fd605d00d2204083cbfc4e4cd3307906656345a73118ac563f"},
    "ca_bundle": {"path": f"{folder}/orbio_ca_isrg_root_x1.pem",
                  "sha256": "22b557a27055b33606b6559f37703928d3e4ad79f110b407d04986e1843543d1"},
    "run_root": f"/var/lib/edge-os/relay/run-orbio-{run}",
    "channel": {"name": "edge-os-research", "path": f"/var/lib/edge-os/channel/orbio-channel-{run}"},
    "provider_key_file": "/etc/edge-os/relay/orbio-provider-key",
})
with open(path, "w") as out:
    json.dump(config, out, indent=2)
PY
systemctl start edge-os-hermes-relay.service
journalctl -u edge-os-hermes-relay.service -n 20 --no-pager | grep 'handoff '
```

`format`, `kind`, `release`, `image` and `shutdown_owner` stay as they were, because both releases use the same pinned
image. Copy the printed path and hash into `EDGE_OS_HANDOFF_PATH` and `EDGE_OS_HANDOFF_SHA256` in
`/etc/edge-os/hermes-app.env`. Never type a hash from another start.

**7. Start the application and the research worker.**

```sh
systemctl start edge-os-hermes-app.service edge-os-research-worker.service
```

**8. Run the checks.** Save the output in a new file outside the record.

```sh
journalctl -u edge-os-hermes-app.service -n 50 --no-pager | grep serving   # must name orbio-first-call-1
GW=$(sed -n 's/^EDGE_OS_APP_BIND_HOST=//p' /etc/edge-os/hermes-app.env)    # one IPv4 address
curl -sS "http://$GW:8011/healthz"; curl -sS "http://$GW:8011/readyz"      # the second must report ready
curl -sS -o /dev/null -w '%{http_code}\n' "http://$GW:8011/outside"         # must print 404 (H2 row R7)
journalctl -u edge-os-hermes-app.service -u edge-os-research-worker.service -n 100 --no-pager \
  | grep -E 'hosted_deployment_|invalid configuration' || echo "no record refusal"
ss -ltn | grep ':8011'                                                     # only $GW:8011
R=/var/lib/edge-os/relay/run-orbio-$RUN/relay
A='sudo -g edge-os-relay-share -u edge-os-research'
$A test -r /etc/edge-os/relay/orbio-provider-key; echo "key_read=$?"       # must print key_read=1
$A test -r "$R/relay-config.json"; echo "config_read=$?"                   # must print config_read=1
$A test -r "$R/provider-config.json"; echo "provider_read=$?"              # must print provider_read=1
$A test -w "$R/state"; echo "state_write=$?"                               # must print state_write=1
$A test -r "$R/secrets/admission-key"; echo "admission_read=$?"            # must print admission_read=0
$A test -w "$R/grants"; echo "grants_write=$?"                             # must print grants_write=0
sudo -u nobody test -r "$R/secrets/admission-key"; echo "third_read=$?"    # must print third_read=1
sudo -u nobody test -w "$R/grants"; echo "third_write=$?"                  # must print third_write=1
grep -h '^EDGE_OS_USAGE_GLOBAL_\(PROVIDER_REQUESTS\|NANSEN_CREDITS\)=' \
  /etc/edge-os/hermes-app.env /etc/edge-os/research-worker.env             # 60 and 50 in both files
grep -rlF -f /etc/edge-os/relay/orbio-provider-key \
  "/var/lib/edge-os/relay/run-orbio-$RUN" "/var/lib/edge-os/channel/orbio-channel-$RUN"; RC=$?
[ "$RC" -eq 1 ] && echo "no key copy" || echo "FAIL: key scan ($RC)"       # must print: no key copy
```

The scan prints file names only, never a match. Exit code 1 means it read everything and found nothing. A missing usage line means the
host process uses its default limit, so add the value and restart before you continue.

**9. Open the public route last.** Rollout rule: the host application is READY and §9.3 step 8 passes before any API image
or Coolify value that needs it. Also finish §9.4. Then set `EDGE_OS_HERMES_APP_URL=http://<coolify-gateway>:8011` in
Coolify and restart the stack. Do not deploy an API image first. The running image already forwards the six paths.

### 9.4 Open items before step 9

- N5 keeps the public route closed until every PENDING row of `h2_runner_isolation.md` passes. A decision made for the old
  record does not bind the new one by itself, so the controller records that N5 carries over.
- R7 runs in §9.3 step 8. Its result needs the bind address, `/healthz`, `/readyz` and the 404.
- Rows 1 to 5 and 8 to 10 need a real job. With this record, a real job is a paid Orbio call. It needs the builder's
  approval, and the local first study comes first.
- R8 tests the public path, so it needs `EDGE_OS_HERMES_APP_URL` set, while N5 wants that value empty until R8 passes. The
  controller decides this order. One safe order: run every other row, set the value, and at once send requests with no
  token. Any answer other than an authentication refusal means clear the value.
- The Orbio approval packet says at most one first model request and that production stays refused. The packet is
  hash-bound, so it stays as it is. The builder decision of 2026-11-06 changes that scope for the host. The controller
  records this before step 9.
- The ledger caps stay at USD 2.00, so the live site cannot spend the whole USD 5 balance. A higher cap needs a builder
  decision and a reviewed change (`h8_provider_spend_cap_orbio.md`).
- The hosted and local ledgers do not see each other. Together they can admit USD 4.00, above the shared USD 2.00 ceiling.
  The controller records that the builder accepts this, or holds one route's spend to zero.

### 9.5 Failure steps

Stop at the first failure. Do not run a later step. Do not resend a request that left the host, because an UNKNOWN attempt
keeps its liability.

| Failure | Meaning | Action |
|---|---|---|
| Step 1 exits with any code but 0 | The host cannot reach Orbio, the chain no longer ends at ISRG Root X1, or Docker refused the command | Stop. Nothing changed. A new chain needs a new release record, not a host edit. |
| `hosted_deployment_not_approved` | An env file or the checkout still has the old state | Repeat step 3 or step 4. |
| `hosted_deployment_hash_mismatch` | The installed record differs | Install it again in step 4. Never edit it by hand. |
| `hosted_deployment_outside_window` | The window ended on 2026-11-27 | Stop. A new record needs a new reviewed change. |
| Step 5 stops at `test ! -e`, or prints `different` | A key file is already there, or the copy is not the builder's file | Stop. Nothing was overwritten. Ask the builder before you replace the file: remove it with `shred -u`, then repeat step 5. |
| `refused: the relay refused the provider key file` | The key is wrong for this release. There is no handoff, and nothing can be sent. | Read `<run root>/relay/state/provider-key-refused.json`, which holds a fixed reason and no key. Stop the failed operation with the unit. The builder corrects the source file. Replace the host file as in the step 5 row, then repeat step 6 with the next `RUN`. |
| `start` refuses an existing run root or channel | That operation already ran | Repeat step 6 with the next `RUN`. |
| A refused `restart` | The old handoff stays and no relay runs (`ORBIO_RELEASE_DRAFT.md` §8) | Keep the public route closed. Correct the cause and run `restart` again. |
| A check in step 8 fails | The host is not READY | Keep `EDGE_OS_HERMES_APP_URL` empty. Stop the application and the relay. The public paths keep returning 503. |
| A failure after step 9 | The public route is not safe | Clear `EDGE_OS_HERMES_APP_URL` and restart the stack first. Then stop the application and the relay. |

To return the host to its earlier state:

1. Stop the application, the research worker and the relay, in the step 2 order, while `relay.json` still names the Orbio
   operation.
2. Restore the three `*.bak-before-orbio` files. The earlier steps never replace them.
3. Check out the earlier commit, which holds the old registry entry, and run `uv sync --frozen`.
4. Start the research worker only.

The old relay operation has ended, and the builder chose no OpenRouter on the server, so do not start the relay or the
application. The public paths keep returning 503. The key file stays in place, mode `0600`, until the builder decides.
