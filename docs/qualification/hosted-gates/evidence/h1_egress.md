# H1 provider-only egress (HOSTED_RECORD_V2_RUNBOOK §4.1)

Status: **RUN**. The controller ran the checks on the VPS on 2026-10-30T09:00:44Z. Rows 1-10 pass, with two recorded
deviations. D-H1-2 is NOT PROVEN for the Monad RPC host; this record grants no execution, so the worker needs no chain
access for it.

Operator: controller over SSH. Host: VPS `vmi3674409`. Firewall script: `deploy/host/edge-os-egress-firewall.sh`.

## Preconditions

- `§1a` ran first and printed `READY=1 PROJECT=w2d8bizjdeweqxxoaqcjobqo`.
- `PROJECT`, `W` (execution worker), `PG` (postgres) and `GW` held the values that `§1a` selected.
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
| 1 | Fixed bridge names | `edgeos-egress`, `edgeos-hostdb` and `edgeos-private` exist | PASS (`213`, `211`, `256`, state UP) |
| 2 | Host chains | `DOCKER-USER` and `INPUT` start with the edge-os chains; `edgeos-egress-allow` is populated | PASS (chains hooked; ipset 4 members) |
| 3 | Worker networks | `_private` and `_egress` plus the injected resource network | PASS (`w2d8bizjdeweqxxoaqcjobqo`, `_egress`, `_private`) |
| 4 | PostgreSQL networks | `_private` and `_hostdb` plus the injected resource network | PASS (`w2d8bizjdeweqxxoaqcjobqo`, `_hostdb`, `_private`) |
| 5 | Allowed provider | `https://api.privy.io` answers with any HTTP status | PASS (HTTP 404) |
| 6 | Internet beyond allowlist | blocked from the worker | PASS (`pass: blocked`) |
| 7 | Host through the egress gateway | blocked from the worker | PASS (`pass: blocked`) |
| 8 | Host through the private gateway | blocked from the worker, when a gateway exists | PASS (`pass: blocked`) |
| 9 | Host through the hostdb gateway | blocked from PostgreSQL | PASS (`pass: blocked`) |
| 10 | Internet from PostgreSQL | blocked | PASS (`pass: blocked`) |

The output also shows `GwPriority=1000` on `_egress` and `_hostdb`, and one default route each (`0100CB0A` and
`1100CB0A`). The router checks printed 7 `pass: blocked` lines: rows 6-10 plus the injected gateway and the Coolify
proxy.

## Deviations

| # | Deviation | Result |
|---|---|---|
| D-H1-1 | `iptables -S EDGE_OS_BYPASS` and `EDGE_OS_BYPASS_IN` print `Incompatible with this kernel` because the refresh swaps chains with an `_A`/`_B` suffix. The current `EDGE_OS_BYPASS_B` and `EDGE_OS_BYPASS_IN_B` hold one DROP pair and one INPUT pair for each injected address (`10.0.2.4` worker, `10.0.2.2` postgres). The runbook line names the chain without its suffix. | PASS on the suffixed chains |
| D-H1-2 | The Monad RPC check (`https://rpc-a.edgeos.fun/rpc`) did not run to a result: the name has no DNS record (`Name or service not known`). The RPC relay host is not deployed. This record grants no execution, so the worker needs no chain access for it. Execution (record v2) needs this row to PASS first. | NOT PROVEN |

## Recorded evidence

Source script: `.scratch/vps-live-20261030/H1-RUN.sh` SHA-256
`38e8e45f1e776fc792464545c55c431edece01a07981a818cfd1cff9080ea98e` (runbook §1a lines 68-94 plus the §4.1 check
block, verbatim, `set +e`).

Output: `.scratch/vps-live-20261030/H1-RUN.out` SHA-256
`c6579e26271196fd71b12fc15538fdabb0caf506775c320c6c1ab64674871a7e`. The Python traceback body for the RPC check is
omitted; its last line is kept.

```text
2026-10-30T09:00:44Z
213: edgeos-egress: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default
    link/ether ee:0a:d9:64:f3:d0 brd ff:ff:ff:ff:ff:ff
211: edgeos-hostdb: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default
    link/ether 92:e6:23:99:d2:30 brd ff:ff:ff:ff:ff:ff
256: edgeos-private: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default
    link/ether 46:47:41:e0:5f:2e brd ff:ff:ff:ff:ff:ff
-N DOCKER-USER
-A DOCKER-USER -j EDGE_OS_BYPASS_A
-A DOCKER-USER -j EDGE_OS_FWD_B
-P INPUT DROP
-A INPUT -j EDGE_OS_BYPASS_IN_A
-A INPUT -j EDGE_OS_IN_PRIVATE_B
Name: edgeos-egress-allow
Type: hash:ip
Revision: 6
Header: family inet hashsize 1024 maxelem 65536 timeout 900 bucketsize 12 initval 0x44e4116e
Size in memory: 472
References: 1
Number of entries: 4
Members:
104.18.20.237 timeout 837
64.130.47.14 timeout 837
w2d8bizjdeweqxxoaqcjobqo w2d8bizjdeweqxxoaqcjobqo_egress w2d8bizjdeweqxxoaqcjobqo_private
w2d8bizjdeweqxxoaqcjobqo w2d8bizjdeweqxxoaqcjobqo_hostdb w2d8bizjdeweqxxoaqcjobqo_private
iptables: Incompatible with this kernel.
iptables: Incompatible with this kernel.
w2d8bizjdeweqxxoaqcjobqo GwPriority=0
w2d8bizjdeweqxxoaqcjobqo_egress GwPriority=1000
w2d8bizjdeweqxxoaqcjobqo_private GwPriority=0

w2d8bizjdeweqxxoaqcjobqo GwPriority=0
w2d8bizjdeweqxxoaqcjobqo_hostdb GwPriority=1000
w2d8bizjdeweqxxoaqcjobqo_private GwPriority=0

Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask		MTU	Window	IRTT
eth2	00000000	0100CB0A	0003	0	0	0	00000000	0	0	0
eth1	0002000A	00000000	0001	0	0	0	00FFFFFF	0	0	0
eth2	0000CB0A	00000000	0001	0	0	0	F0FFFFFF	0	0	0
eth0	4000CB0A	00000000	0001	0	0	0	C0FFFFFF	0	0	0
Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask		MTU	Window	IRTT
eth1	00000000	1100CB0A	0003	0	0	0	00000000	0	0	0
eth0	0002000A	00000000	0001	0	0	0	00FFFFFF	0	0	0
eth1	1000CB0A	00000000	0001	0	0	0	F0FFFFFF	0	0	0
eth2	4000CB0A	00000000	0001	0	0	0	C0FFFFFF	0	0	0
pass: blocked
pass: blocked
404
urllib.error.URLError: <urlopen error [Errno -2] Name or service not known>
pass: blocked
pass: blocked
pass: blocked
pass: blocked
pass: blocked
READY=1 PROJECT=w2d8bizjdeweqxxoaqcjobqo

# controller follow-up reads, 2026-10-30 ~09:02Z
# iptables -S EDGE_OS_BYPASS / EDGE_OS_BYPASS_IN print "Incompatible with this kernel": the chains carry an A/B suffix
# (the refresh swaps them). Current: EDGE_OS_BYPASS_B, EDGE_OS_BYPASS_IN_B, hooked from DOCKER-USER and INPUT.
-A EDGE_OS_BYPASS_B -s 10.0.2.4/32 -j DROP
-A EDGE_OS_BYPASS_B -d 10.0.2.4/32 -j DROP
-A EDGE_OS_BYPASS_B -s 10.0.2.2/32 -j DROP
-A EDGE_OS_BYPASS_B -d 10.0.2.2/32 -j DROP
-A EDGE_OS_BYPASS_IN_B -s 10.0.2.4/32 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A EDGE_OS_BYPASS_IN_B -s 10.0.2.4/32 -j DROP
-A EDGE_OS_BYPASS_IN_B -s 10.0.2.2/32 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A EDGE_OS_BYPASS_IN_B -s 10.0.2.2/32 -j DROP
# ipset edgeos-egress-allow members: 104.18.20.237, 104.18.21.237, 64.130.47.14, 64.31.29.187
# edge-os-egress-refresh Result=success
# rpc-a.edgeos.fun: no A record (dig from the controller Mac returns nothing). The RPC relay host is not deployed.
```

Earlier context: `.scratch/vps-live-20261026/H1-EVIDENCE.md` SHA-256
`4f49d54a5b267b95976f21e467e3e295170b4c55471b5b79c8587a003b2e2056` (BRIDGE-ISO-L3 install, finding F1 closed).

## Accepted limits (§4.1)

- The address allowlist admits every name that shares a CDN address with `api.privy.io` or the Monad RPC host.
- DNS to the upstream resolvers allows any query, so DNS tunnelling remains possible from the worker.
- A rotating CDN name can answer with an address the host has not seen; that connection is dropped until the next
  refresh (at most 5 minutes). This fails closed.

## Follow-ups outside this task

The runbook §4.1 text names `EDGE_OS_BYPASS` without its `_A`/`_B` suffix and describes the Monad RPC check before the
RPC relay host exists. Both are text corrections for the runbook owner, not changes in this record.
