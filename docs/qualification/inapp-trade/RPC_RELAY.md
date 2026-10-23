# Keyless `/rpc` relay for the in-app trade release (`CLOUD-RPC-RELAY`)

Task `CLOUD-RPC-RELAY`, builder-approved normal cloud session, 2026-10-23. Base
`3a495cd355262b712afbc966ea49932e19dea575` (`integration/edge-os-mvp`). Status: **authored, tested with fakes, not
deployed.** No network, provider, credential, key, VPS or DNS was used to write it. This document grants no trade
authority and changes no release hash.

The relay is the `/rpc` relay named in [`INAPP_TRADE_RELEASE.md`](INAPP_TRADE_RELEASE.md) (step 4 fill and "What else
must exist"). It holds the QuickNode Monad mainnet URL (chain id 143), whose path holds the key, in its own server-side
configuration only. The execution worker sees two keyless `https://<host>/rpc` URLs.

## Files

| File | Role |
| --- | --- |
| [`deploy/rpc-relay/rpc_relay.py`](../../../deploy/rpc-relay/rpc_relay.py) | The relay. Python standard library only. |
| [`deploy/rpc-relay/Dockerfile`](../../../deploy/rpc-relay/Dockerfile) and `.dockerignore` | The image: the pinned base of `deploy/docker/api.Dockerfile` plus `rpc_relay.py`, non-root `10001:10001`. |
| [`deploy/rpc-relay/compose.rpc-relay.yml`](../../../deploy/rpc-relay/compose.rpc-relay.yml) | The relay's own Coolify Docker Compose resource, with its Traefik routing labels. |
| [`deploy/host/edge-os-egress-firewall.sh`](../../../deploy/host/edge-os-egress-firewall.sh) | The worker's egress rule, extended with the relay rule (`EDGE_OS_EGRESS_RELAY_HOSTS`). |
| [`HOSTED_RECORD_V2_RUNBOOK.md`](../hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md) §4 | The worker's egress host list: `api.privy.io` plus the two relay names; the provider host is no longer listed. |
| [`tests/rpc_relay/`](../../../tests/rpc_relay/) | The tests. Fakes only; the HTTP tests bind to `127.0.0.1`. |

## Design

```text
execution worker (edgeos-egress, 10.203.0.0/28)
  │ https://rpc-a.edgeos.fun/rpc  or  https://rpc-b.edgeos.fun/rpc   (keyless; no credential header)
  │ DNS -> this VPS's public IPv4 :443; Docker hands it to Traefik via docker-proxy (default) or DNAT;
  │ the host rule admits only TCP 443 to the relay addresses, on either path
  ▼
Coolify Traefik (coolify-proxy, network `coolify`)  TLS: Let's Encrypt (`letsencrypt`), entrypoint `https`
  │ router per host: Host(..) && Path(`/rpc`) && Method(`POST`)
  │ middlewares: ipallowlist (EDGE_OS_RPC_RELAY_ALLOWED_SOURCES), buffering (32768-byte body)
  ├── rpc-a -> rpc-relay:8545  role observer
  └── rpc-b -> rpc-relay:8546  role broadcast
        │ relay admits the socket peer only if it is coolify-proxy's current address
        │ one call, method table, params shape, limits; re-serialized; no caller header forwarded
        ▼
QuickNode https://<account host>/<key>/   (EDGE_OS_RPC_RELAY_UPSTREAM_URL, relay environment only)
```

**Two endpoints, one container.** The release requires different broadcast and observer endpoints
(`operating_release.py`: `broadcast.endpoint != observer.endpoint`). `rpc-a.edgeos.fun` is the read endpoint (quote,
observer, dry-run reads); `rpc-b.edgeos.fun` is the broadcast endpoint. Traefik sends each name to its own port, so the
role is fixed by the listening socket. No caller header, path or body can choose it. The observer port cannot broadcast,
and the broadcast port serves only the two reads the broadcast plan needs.

**Separate Coolify resource.** The relay is not a service of `compose.coolify.yml`. Coolify can put every variable of a
resource into one shared runtime file, so a separate resource keeps the provider URL out of the application stack and
out of the worker's environment. The relay joins only the `coolify` network; Traefik reaches it there and it reaches
the provider through that network's NAT.

**Who may call.** Three gates, all required:

1. The host egress rule lets the worker open TCP 443 to the relay addresses only, on this host. With Docker's default
   `userland-proxy: true` the connection is not DNATed and reaches `docker-proxy` through `INPUT`; with
   `userland-proxy: false` Docker DNATs it to Traefik. The rule admits each path for TCP 443 to a relay address and
   nothing else. The provider host is not in the worker's allowlist, so the worker cannot reach the provider directly.
2. Traefik's `ipallowlist` admits only `EDGE_OS_RPC_RELAY_ALLOWED_SOURCES`. The worker's connection reaches Traefik from
   the `coolify` bridge gateway on both paths (docker-proxy connects from it; Docker's masquerade rewrites to it), so
   the range is that gateway as a `/32` (read it in deploy step 3). Internet callers keep their own address and are refused with `403 Forbidden` by Traefik.
3. The relay admits a socket peer only when it is the current address of `coolify-proxy` (resolved on the shared
   network, cached 30 s, a failed lookup cached for 2 s, the lookup runs outside the request lock). The check runs at
   accept, before a thread or connection slot is spent: any other peer is closed at once (outcome `peer_refused`).
   Loopback is accepted for the container's own `GET /healthz`, and `POST /rpc` checks the proxy again (`403`). Another
   container on the `coolify` network, such as the API or web container, cannot call port 8545 or 8546 directly.

HTTPS is kept end to end for the worker: it verifies a Let's Encrypt certificate for each name. Traefik to the relay is
plain HTTP on the host's own `coolify` bridge.

**Requests.** `POST /rpc` only, exactly that target (no query or fragment), `Content-Type: application/json`, one
`Content-Length` of at most 32768 bytes, no `Transfer-Encoding`. The body is one JSON-RPC 2.0 call object with exactly
the keys `jsonrpc`, `id`, `method` and optional `params`. Batches are refused whatever they hold: the worker never sends
one (`transaction_rpc_client.py` and `direct_route_quote_client.py` send one object per POST). Notifications, a `null`,
boolean, fractional or out-of-range id, duplicate JSON keys and `NaN`/`Infinity` are refused. The method must be in the
role's table and the params must match the method's shape (below). The relay re-serializes the call and POSTs it once.
It sends only `Content-Type`, `Accept`, `Accept-Encoding: identity` and `User-Agent`; it never forwards a caller header,
never follows a redirect and never retries.

**Replies.** A provider reply passes through only when it is one JSON-RPC object for the same id, with either `result`
(HTTP 200) or a provider `error` object (`code`, `message`, optional `data`; HTTP 200 or the provider's 4xx/5xx status).
It is answered with exact framing (`Content-Length`, no `Content-Encoding`, `Cache-Control: no-store`), as the worker's
`post_json` requires. Anything else becomes a fixed relay error. Before sending, both the raw provider body and the
re-serialized reply are searched, case-insensitively and after JSON unescaping, for the configured URL, the provider
host, the key path, each path segment of 8 or more characters, every 16-character piece of such a segment and the
segment's hex encoding, the base64 of the URL and of each segment, and the host's account-specific first label; each
text is also checked after repeated percent-decoding. Any match withholds the reply (`502`,
`upstream reply withheld`). An echo split into pieces shorter than 16 characters is not caught; this needs the
provider itself to echo key material. A provider exception is dropped without its text.

**Key containment.** The key exists only in `EDGE_OS_RPC_RELAY_UPSTREAM_URL` in the relay resource's Coolify
environment. The configuration objects redact it in `repr`/`str`. A configuration refusal prints only its code. No
reply, error message or log line carries it. The worker's release fields and `EDGE_OS_EXECUTION_MONAD_RPC_URL` hold
only the keyless names. The worker's `credential_slot` fields stay unused for these endpoints: the relay needs no
caller credential.

**Logs.** One JSON line per request on stdout: `at`, `role`, `method` (an allowlisted name or `-`, never the caller's
string), `outcome`, `status`, `upstream_status`, `ms`, `bytes_in`, `bytes_out`. No URL, host, path, param, body, header
or exception text is logged. `http.server`'s request and traceback logging is replaced.

## Method table

| Method | Observer `rpc-a` (8545) | Broadcast `rpc-b` (8546) | Params accepted | Used by |
| --- | --- | --- | --- | --- |
| `eth_chainId` | yes | yes | `[]` (or omitted) | worker observer, startup checks |
| `eth_blockNumber` | yes | no | `[]` | dry run, checks |
| `eth_gasPrice` | yes | no | `[]` | dry run (fees) |
| `eth_maxPriorityFeePerGas` | yes | no | `[]` | dry run (fees) |
| `eth_feeHistory` | yes | no | `[count, tag]` or `[count, tag, percentiles]`; count 1-1024; at most 100 non-decreasing percentiles in 0-100 | dry run (fees) |
| `eth_call` | yes | no | `[call, tag]`; no third (state override) argument | quote (`getReserves`), observer (`decimals`, `balanceOf`) |
| `eth_estimateGas` | yes | no | `[call]` or `[call, tag]` | dry run (approve, swap, revoke estimates) |
| `eth_getBalance` | yes | no | `[address, tag]` | observer |
| `eth_getCode` | yes | no | `[address, tag]` | deployment proof reads |
| `eth_getTransactionCount` | yes | yes | `[address, tag]` | broadcast plan (`pending` nonce) |
| `eth_getBlockByNumber` | yes | no | `[tag, false]`; full transaction bodies refused | observer (finality) |
| `eth_getTransactionReceipt` | yes | no | `[hash]` | observer |
| `eth_getTransactionByHash` | yes | no | `[hash]` | observer, recovery |
| `eth_sendRawTransaction` | **no** | yes | `[data]`, 0x-prefixed even hex, 3-16386 characters (the worker's bound) | broadcast |

A `call` object has at least one of `from`, `to`, `gas`, `gasPrice`, `maxFeePerGas`, `maxPriorityFeePerGas`, `value`,
`data`, `input`, `nonce`, `type`, `chainId` and nothing else; each value is an address, a quantity or even hex data as
fits. A `tag` is `latest`, `pending`, `safe`, `finalized`, `earliest` or a canonical quantity. Addresses are 20 bytes and
hashes 32 bytes of hex. Every other method is refused on both endpoints (`403`, JSON-RPC `-32601`), among them
`eth_sendTransaction`, `eth_sign*`, `eth_accounts`, `eth_getLogs`, filters and subscriptions, `debug_*`, `trace_*`,
`admin_*`, `personal_*`, `txpool_*`, `qn_*`, `net_*` and `web3_*`. Method names are matched exactly (case and spaces
included).

## Limits

| Limit | Value |
| --- | --- |
| Request body | 32768 bytes (Traefik `buffering.maxRequestBodyBytes` and the relay) |
| Provider reply | 2 MiB read at most; larger is refused |
| Rate, observer | 20 requests/s, burst 60 (token bucket, all callers; only calls that would reach the provider spend it) |
| Rate, broadcast | 2 requests/s, burst 10 |
| Concurrent provider calls | observer 8, broadcast 2 |
| Open connections | 32 per port, each one thread; more are closed at once (`pids_limit: 128` covers both ports) |
| Caller request | head and body within 10 s of accept (then the socket is cut, outcome `read_timeout`); 10 s per read |
| Provider call | 10 s connect; every later socket operation gets only the time left in a 15 s budget |

| Outcome | HTTP | JSON-RPC code | Message |
| --- | --- | --- | --- |
| `rate_limited`, `busy` | 429 | -32005 | rate limit exceeded / too many concurrent requests |
| `body_too_large` | 413 | -32005 | request body too large |
| `parse_error` | 400 | -32700 | parse error |
| `batch_refused` | 400 | -32600 | batch requests are not accepted |
| `invalid_request` | 400 | -32600 | invalid request |
| `method_not_allowed` | 403 | -32601 | method not allowed on this endpoint |
| `invalid_params` | 400 | -32602 | invalid params for this method |
| `peer_refused` | 403 | -32600 | caller not admitted |
| `not_found`, `method_refused` | 404, 405 | -32600 | not found / method not allowed |
| `length_required`, `bad_length`, `unsupported_type`, `body_incomplete` | 411, 400, 415, 400 | -32600 | fixed text |
| `upstream_unreachable`, `upstream_reply_invalid`, `upstream_reply_withheld` | 502 | -32603 | upstream unavailable / reply invalid / reply withheld |
| `forwarded` | 200 or the provider's 4xx/5xx with its own error | provider's | provider's |

The worker refuses every reply that is not HTTP 200 in `post_json` (`CLIENT_REPLY_REFUSED`) and every `error` reply
with HTTP 200 in `TransactionRpcClient.call` (`RPC_REPLY_UNRECOGNIZED`) or the quote client
(`QUOTE_RESERVES_UNSUPPORTED`), so a relay or provider error never becomes a result.

## Release fill values

Put these exact values in `docs/qualification/inapp-trade/release.fill.json` (step 4 of `INAPP_TRADE_RELEASE.md`):

```json
"quote_endpoint": "https://rpc-a.edgeos.fun/rpc",
"broadcast_endpoint": "https://rpc-b.edgeos.fun/rpc",
"observer_endpoint": "https://rpc-a.edgeos.fun/rpc"
```

They satisfy `DirectRoutePins` (https, path exactly `/rpc`, no query or fragment) and `operating_release.py` (keyless
`https`, path `/rpc`, not `.invalid` for an actual release, broadcast endpoint different from the observer endpoint).
The quote shares the read endpoint: it uses only `eth_call`, and the release requires only broadcast and observer to
differ.

The worker setting `EDGE_OS_EXECUTION_MONAD_RPC_URL` (validated at startup, not written into a request) is
`https://rpc-a.edgeos.fun/rpc`.

## DNS records

The controller adds, in the `edgeos.fun` zone:

| Name | Type | Value | TTL |
| --- | --- | --- | --- |
| `rpc-a.edgeos.fun` | `A` | the Contabo VPS public IPv4 (the same address as `api.edgeos.fun`) | 300 |
| `rpc-b.edgeos.fun` | `A` | the same IPv4 | 300 |

Add no `AAAA` record: the egress rule and both Docker networks are IPv4 only, and `getent ahostsv4` fills the relay
set. Serve both names directly (no CDN proxy), so Let's Encrypt's HTTP-01 challenge reaches Traefik on port 80 and the
worker's connection is DNATed on this host.

## Deploy

Controller steps, in order. Nothing here was run.

1. **DNS.** Add both records above. Wait until `getent ahostsv4 rpc-a.edgeos.fun` and `rpc-b.edgeos.fun` on the VPS
   return the VPS address.
2. **Coolify resource.** New resource, Docker Compose build pack, this repository at the exact reviewed commit. Base
   Directory `/deploy/rpc-relay`, Docker Compose location `/compose.rpc-relay.yml`. Leave the service's Domains field
   empty: the file's labels define both routers, and a Coolify domain would add a third router without the
   allowlist. Do not enable previews.
3. **Allowed source.** On the VPS, read the `coolify` network gateway:
   `docker network inspect coolify --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'`. The range is that address as
   `/32`, for example `10.0.1.1/32`.
4. **Environment.** In the relay resource only:
   - `EDGE_OS_RPC_RELAY_UPSTREAM_URL`: the QuickNode Monad mainnet HTTPS URL, marked secret (locked) in Coolify and
     **not** a Build Variable (a build variable can be passed as a `--build-arg` and appear in build logs). It must
     be `https`, a host name, a non-root path (the key), no user-info, query or fragment; anything else stops the relay
     with `RELAY_UPSTREAM_URL_INVALID`.
   - `EDGE_OS_RPC_RELAY_SOURCE_COMMIT`: the deployed commit (tags the built image and its revision label).
   - `EDGE_OS_RPC_RELAY_ALLOWED_SOURCES`: the range from step 3.

   Coolify 4.4.7 does not substitute every `${...}` variable (see `deploy/coolify/RUNBOOK.md`). If the deployed labels
   or image tag still show `${`, write the commit and the source range literally in the Coolify Compose editor; both
   are public values. Never write the provider URL into the Compose file.
5. **Deploy** the resource and wait for `healthy`. Confirm the relay container is on the `coolify` network only
   (hosted check 1). If Coolify attached its own per-resource network as well, calls still work (the gate admits every
   address `coolify-proxy` resolves to), but the relay then shares a network with more peers. Remove the extra network
   (Coolify's "Connect to Predefined Network" for this resource, or delete the network from the deployed file) and
   redeploy.
6. **Egress rule.** Update `/etc/edge-os/egress.env` as in `HOSTED_RECORD_V2_RUNBOOK.md` §4.1:

   ```sh
   EDGE_OS_EGRESS_HOSTS="api.privy.io"
   EDGE_OS_EGRESS_RELAY_HOSTS="rpc-a.edgeos.fun rpc-b.edgeos.fun"
   EDGE_OS_EGRESS_PORTS="443"
   ```

   Install the script again to `/usr/local/sbin/edge-os-egress-firewall` and run
   `systemctl reload edge-os-egress-firewall`. Record which path Docker uses (both are admitted):
   `docker info --format '{{json .}}' | grep -o '"userland-proxy[^,]*' ; iptables -t nat -S DOCKER | grep -- '-i edgeos-egress -j RETURN'`
   (a line from the second command means the docker-proxy path).
7. **Worker and release.** Set `EDGE_OS_EXECUTION_MONAD_RPC_URL=https://rpc-a.edgeos.fun/rpc` when the execution lane
   activates the worker settings, and use the fill values above. Both belong to other lanes.

## Checks

Local (no network, run on this candidate):

```sh
cd apps/api && uv run --frozen pytest ../../tests/rpc_relay -q -p no:cacheprovider
cd apps/api && uv run --frozen pytest tests/deploy -q -p no:cacheprovider
```

Hosted (controller, after deploy; record the output). Select containers as in `HOSTED_RECORD_V2_RUNBOOK.md` §1a; `$W`
is the execution worker, `$API` the API container and `$R` the relay container
(`label=com.docker.compose.project=<relay project>`).

```sh
# 1. Relay state: healthy, only the coolify network, only its two settings.
docker inspect "$R" --format '{{.State.Health.Status}}'                                          # healthy
docker inspect "$R" --format '{{range $n, $e := .NetworkSettings.Networks}}{{$n}} {{end}}'       # coolify
docker inspect "$R" --format '{{range .Config.Env}}{{println .}}{{end}}' | cut -d= -f1 | grep EDGE_OS_
#   EDGE_OS_RPC_RELAY_TRUSTED_PROXY and EDGE_OS_RPC_RELAY_UPSTREAM_URL (names, never values); Coolify may also inject
#   the public EDGE_OS_RPC_RELAY_SOURCE_COMMIT and EDGE_OS_RPC_RELAY_ALLOWED_SOURCES. No other EDGE_OS_ name.
# The provider URL is in no other resource: on the worker and API this prints nothing.
docker inspect "$W" "$API" --format '{{range .Config.Env}}{{println .}}{{end}}' | cut -d= -f1 | grep RPC_RELAY_UPSTREAM

# 2. From the worker: both names answer chain 143 (0x8f) over verified HTTPS.
PY_RPC='import sys, urllib.error as e, urllib.request as u
r = u.Request(sys.argv[1], data=sys.argv[2].encode(), headers={"Content-Type": "application/json"})
try:
    with u.urlopen(r, timeout=10) as reply: print(reply.status, reply.read().decode())
except e.HTTPError as x: print(x.code, x.read().decode())'
CHAIN='{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}'
docker exec "$W" python -c "$PY_RPC" https://rpc-a.edgeos.fun/rpc "$CHAIN"   # 200 ... "result":"0x8f"
docker exec "$W" python -c "$PY_RPC" https://rpc-b.edgeos.fun/rpc "$CHAIN"   # 200 ... "result":"0x8f"

# 3. Method tables and batch refusal, from the worker.
docker exec "$W" python -c "$PY_RPC" https://rpc-a.edgeos.fun/rpc \
  '{"jsonrpc":"2.0","id":2,"method":"eth_sendRawTransaction","params":["0x00"]}'              # 403 ... -32601
docker exec "$W" python -c "$PY_RPC" https://rpc-b.edgeos.fun/rpc \
  '{"jsonrpc":"2.0","id":3,"method":"eth_call","params":[{"to":"0x0000000000000000000000000000000000000000","data":"0x"},"latest"]}'  # 403 ... -32601
docker exec "$W" python -c "$PY_RPC" https://rpc-a.edgeos.fun/rpc "[$CHAIN]"                 # 400 ... -32600
docker exec "$W" python -c "$PY_RPC" https://rpc-a.edgeos.fun/rpc \
  '{"jsonrpc":"2.0","id":4,"method":"eth_getLogs","params":[{}]}'                              # 403 ... -32601

# 4. The worker cannot reach the provider host directly (the name from the relay setting, not the key).
must_fail "$W" python -c "$PY_PROBE" <provider host name> 443                                  # pass: blocked

# 5. Another container on the coolify network cannot bypass Traefik (the API container has python).
RIP=$(docker inspect "$R" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
docker exec "$API" python -c "$PY_RPC" "http://$RIP:8545/rpc" "$CHAIN"                         # 403 ... caller not admitted

# 6. From outside the VPS (the builder's machine): Traefik refuses the source; other paths do not route.
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Content-Type: application/json' -d "$CHAIN" https://rpc-a.edgeos.fun/rpc  # 403
curl -sS -o /dev/null -w '%{http_code}\n' https://rpc-a.edgeos.fun/healthz                                            # 404
curl -sS -o /dev/null -w '%{http_code}\n' http://rpc-a.edgeos.fun/rpc     # a redirect or 404, never a relay reply

# 7. The relay's logs name neither the provider host nor any key segment (prints counts only).
docker exec "$R" python -I -c 'import os, urllib.parse as p
u = p.urlsplit(os.environ["EDGE_OS_RPC_RELAY_UPSTREAM_URL"])
print("\n".join([u.hostname] + [s for s in u.path.split("/") if len(s) >= 8]))' > /tmp/relay-needles
docker logs "$R" 2>&1 | grep -ciF -f /tmp/relay-needles; shred -u /tmp/relay-needles          # 0
```

Every expected value must match. A `200` in check 6 from outside, a reply from check 5, or a non-zero count in check 7
is a failed check: stop and fix before the release fill. The file in check 7 holds key material for the moment of the
count; it stays in root's `/tmp` on the VPS and is shredded at once.

## Limits and accepted risks

- **Relay egress is not host-filtered.** The relay reaches the provider through the `coolify` network's NAT, which also
  allows other destinations. The code connects only to the configured host with certificate verification and no
  redirects. A dedicated relay bridge with its own host rule would remove this; it is not part of this task.
- **The allowlisted source is shared.** Docker masquerades every container that reaches this host's public address
  from another bridge to the `coolify` gateway, so other Coolify applications on this VPS pass the `ipallowlist` too.
  They can only make the allowlisted calls within the rate limits; they cannot read the key, sign, or choose a role.
  Internet callers are refused. Likewise a container on the `coolify` network can give itself the network alias
  `coolify-proxy` and pass the relay's peer gate without Traefik; it gains the same allowlisted calls, nothing more.
- **Shared Traefik.** The worker's relay rule admits any name Traefik serves on this host (for example
  `api.edgeos.fun`); only the relay routes check the source.
- **Global rate limits.** All callers arrive through Traefik, so the limits are per role, not per caller. A caller
  that passes the gates can exhaust the bucket with valid calls and delay the worker; refused requests do not spend it.
  It cannot raise the provider spend above the limits.
- **Provider errors pass through.** A provider `error` object (code, message, data) reaches the worker unless it names
  the key, the host or the URL.
- **Image provenance.** Coolify builds the image on the VPS from the reviewed commit; the base is digest-pinned and
  nothing is installed. Building it in `.github/workflows/images.yml` and deploying by digest is a possible follow-up
  that changes the workflow and its tests.
- **Traefik version.** The labels use Traefik v3 names (`ipallowlist`). On Traefik v2 the middleware is `ipwhitelist`.
  Check 6 proves the allowlist is active.
- **Plain HTTP inside the host.** Traefik reaches the relay over the host-local `coolify` bridge without TLS.
