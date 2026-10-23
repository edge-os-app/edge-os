# H1 provider-only egress (HOSTED_RECORD_V2_RUNBOOK §4.1)

Status: **NOT RUN**. The controller runs these checks on the VPS and records the output. This file is a template; no
check below ran for this file.

Operator: `<name>`. Date: `<UTC>`. Host: VPS `vmi3674409`. Firewall script: `deploy/host/edge-os-egress-firewall.sh`.

## Preconditions

- `§1a` ran first and printed `READY=1`.
- `PROJECT`, `W` (execution worker), `PG` (postgres) and `GW` hold the values that `§1a` selected.
- The `edge-os-egress-firewall` unit is enabled and its last `apply` succeeded.

## Exact checks (§4.1)

```sh
# §1a first; READY must be 1.
ip link show edgeos-egress && ip link show edgeos-hostdb && ip link show edgeos-private  # the fixed bridge names
iptables -S DOCKER-USER | head -3; iptables -S INPUT | head -3; ipset list edgeos-egress-allow | head
# Coolify must not have attached another network (one with NAT would bypass these rules).
docker inspect "$W" --format '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} {{end}}'   # exactly <PROJECT>_private <PROJECT>_egress
docker inspect "$PG" --format '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} {{end}}'  # exactly <PROJECT>_private <PROJECT>_hostdb
running "$W" && docker exec "$W" python -c "
import urllib.error as e, urllib.request as u
try: print(u.urlopen('https://api.privy.io', timeout=5).status)
except e.HTTPError as error: print(error.code)"                                                       # any HTTP status
GW=$(docker network inspect "${PROJECT}_private" --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}')
must_fail "$W" python -c "$PY_PROBE" example.com 443       # the internet beyond the allowlist
must_fail "$W" python -c "$PY_PROBE" 10.203.0.1 22         # the host, through the egress gateway
[ -z "$GW" ] || must_fail "$W" python -c "$PY_PROBE" "$GW" 22   # the host, through the private gateway, if any
must_fail "$PG" bash -c "$SH_PROBE" 10.203.0.17 22         # the host, through the hostdb gateway
must_fail "$PG" bash -c "$SH_PROBE" 1.1.1.1 443            # the internet, from PostgreSQL
```

## Results

Every `must_fail` line passes only when it prints `pass: blocked`. Any `FAIL` line is a failed check. A refused
connection (`FAIL: not proven blocked (1)`) means the packet reached its target.

| # | Check | Expected observation | Result |
|---|---|---|---|
| 1 | Fixed bridge names | `edgeos-egress`, `edgeos-hostdb` and `edgeos-private` exist | NOT RUN |
| 2 | Host chains | `DOCKER-USER` and `INPUT` start with the edge-os chains; `edgeos-egress-allow` is populated | NOT RUN |
| 3 | Worker networks | exactly `<PROJECT>_private` and `<PROJECT>_egress` | NOT RUN |
| 4 | PostgreSQL networks | exactly `<PROJECT>_private` and `<PROJECT>_hostdb` | NOT RUN |
| 5 | Allowed provider | `https://api.privy.io` answers with any HTTP status | NOT RUN |
| 6 | Internet beyond allowlist | blocked from the worker | NOT RUN |
| 7 | Host through the egress gateway | blocked from the worker | NOT RUN |
| 8 | Host through the private gateway | blocked from the worker, when a gateway exists | NOT RUN |
| 9 | Host through the hostdb gateway | blocked from PostgreSQL | NOT RUN |
| 10 | Internet from PostgreSQL | blocked | NOT RUN |

## Accepted limits (§4.1)

- The address allowlist admits every name that shares a CDN address with `api.privy.io` or the Monad RPC host.
- DNS to the upstream resolvers allows any query, so DNS tunnelling remains possible from the worker.
- A rotating CDN name can answer with an address the host has not seen; that connection is dropped until the next
  refresh (at most 5 minutes). This fails closed.

## Recorded evidence

Operator fills: the literal command output, the date, and any deviation. Do not record a `FAIL` line as blocked.
