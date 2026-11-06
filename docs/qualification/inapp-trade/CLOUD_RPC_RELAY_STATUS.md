# CLOUD-RPC-RELAY status

Task `CLOUD-RPC-RELAY` (keyless `/rpc` relay), builder-approved normal cloud session, 2026-10-23.
Base `origin/integration/edge-os-mvp` at `3a495cd355262b712afbc966ea49932e19dea575`. Branch `cloud/rpc-relay` (normal
pushes only; no PR, no merge, main and integration untouched). No network, provider, credential, key, VPS or DNS was
used.

## Result

**Final reviewed SHA: `1d94faca17d640c96d4e32909df461efd3ce7fa9`. Both reviews PASS on that same commit.** This status
file is the only later commit; it changes no reviewed file.

| Review (new independent subagent) | Commit | Verdict |
| --- | --- | --- |
| Spec | `1d94fac` | **PASS**, no blocking findings |
| Standards (key never reaches a response, log or client; disallowed methods and batch abuse refused) | `1d94fac` | **PASS**, no blocking findings |

Earlier rounds and what they fixed:

| Commit | Spec | Standards | Blocking finding fixed in the next commit |
| --- | --- | --- | --- |
| `7af9553` | FAIL | FAIL | flaky connection-cap test; connection slot leaked on thread-start failure under `pids_limit` |
| `4e54ede` | FAIL | PASS | worker path through docker-proxy (Docker's default userland proxy) dropped by INPUT |
| `7a48a13` | FAIL | PASS | Traefik's source address can be the gateway of any network `coolify-proxy` joins; allowlist now covers all of them |
| `1d94fac` | PASS | PASS | none |

RED first: `455c1da` adds only the tests; the relay module did not exist there.

## Files (owned)

- `deploy/rpc-relay/rpc_relay.py`: the relay (standard library), `Dockerfile`, `.dockerignore`, `compose.rpc-relay.yml`
  (its own Coolify Compose resource with Traefik labels)
- `deploy/host/edge-os-egress-firewall.sh`: relay rule for the worker (`EDGE_OS_EGRESS_RELAY_HOSTS`), docker-proxy and
  DNAT paths
- `docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md` §4: worker egress hosts are `api.privy.io` plus the
  relay names; the provider host is no longer listed
- `docs/qualification/inapp-trade/RPC_RELAY.md`: design, method table, limits, fill values, DNS records, deploy steps,
  hosted checks, accepted risks
- `tests/rpc_relay/`: fakes only; HTTP tests bind to `127.0.0.1`

Not touched: worker, quote client, release files, settings, `compose.coolify.yml`.

## Values for the controller

- Release fill: `"quote_endpoint": "https://rpc-a.edgeos.fun/rpc"`, `"observer_endpoint": "https://rpc-a.edgeos.fun/rpc"`,
  `"broadcast_endpoint": "https://rpc-b.edgeos.fun/rpc"`. Worker `EDGE_OS_EXECUTION_MONAD_RPC_URL=https://rpc-a.edgeos.fun/rpc`.
- DNS: `A rpc-a.edgeos.fun` and `A rpc-b.edgeos.fun` to the VPS IPv4, TTL 300, no `AAAA`, no CDN proxy.
- Deploy steps and hosted checks: `RPC_RELAY.md` "Deploy" and "Checks".

## Test commands and counts (on `1d94fac`)

```sh
cd apps/api && uv run --frozen pytest ../../tests/rpc_relay tests/deploy -q -p no:cacheprovider
```

391 passed (266 relay + 125 deploy), 3 consecutive runs, plus reviewer runs (6 runs of the relay suite, one under full
CPU load; no flakes). `sh -n` passes on the firewall script.

Not run: the full `apps/api` suite needs a Docker daemon for PostgreSQL, which this session lacks
(`docker volume create` fails at the first database test). No API code changed. Nothing hosted was run; every hosted
check in `RPC_RELAY.md` is NOT RUN.

## Open non-blocking findings (from the final reviews; not fixed, for a later change)

1. `RPC_RELAY.md` hosted check 5: a non-proxy peer is closed at accept, so the expected output is "connection closed, no
   reply", not `403`.
2. `RPC_RELAY.md` deploy step 3: filter IPv6 gateways (or use `/128`) when building the allowlist.
3. The `coolify-proxy` lookup runs on the accept thread without a time bound; move it to a background refresh.
4. `credential_slot` for broadcast and observer is required non-empty by `operating_release.py`; the release lane must
   name a placeholder (the relay needs no caller credential).
5. Add a regression test that drives the worker's own client wire bytes through `RelayCore` into `post_json` (verified
   by the spec reviewer by hand).
6. A `Transfer-Encoding` header with a space before the colon is ignored (Traefik rejects it first); refuse it anyway.
7. A failing stdout write in `verify_request` ends the serve loop (the process then exits 3 and restarts); guard it.
8. Hosted check 4 types the provider host name into the host shell; take it from inside the relay container.
9. Accepted risks stay as documented: relay egress not host-filtered, shared gateway allowlist and `coolify-proxy`
   alias, worker reaches every name Traefik serves, provider-transformed key encodings.
10. Stale comment in `compose.coolify.yml` (not owned): the `egress` network still says "the Monad RPC endpoint".
