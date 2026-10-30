# H2 qualified isolated runner (HOST_QUALIFICATION_RUNBOOK §5.4, §5.5, §5.7)

Status: **PARTIAL**. Pre-registration rows pass for credential isolation, the public API's lack of a Docker socket, the
route stand-in and the forward-code tests. The remaining rows are `PENDING (post-registration; see decision N5)`. The
controller decision below is part of this record.

Operator: controller over SSH. Date 2026-10-30. Host: VPS `vmi3674409`.

## Exact checks from the runbook

Runbook row 5.4, Hermes whole-process isolation:

> The accepted LOCAL helper `dbd95668` runs pinned Hermes in a no-network, read-only job container (512 MB, 1 CPU,
> 64 processes, no capabilities, no socket, no host workspace) and refuses the actual route. The credential file is
> mounted read-only, but the job, transport and Hermes share one process, so the credential copy is readable by Hermes
> code; credential isolation needs a separately decided host-held relay. **The public API/model process must not mount
> the host Docker socket.**

Runbook row 5.5, cleanup after a job:

> A completed, cancelled or timed-out job cleans up its process and temporary files.

Runbook row 5.7, trusted runner boundary:

> The accepted LOCAL helper `dbd95668` provides the runner (`build_transport_job`, `TransportJob.runner`,
> `recover_pending(C)`), but it is not mounted and the durable shared ledger and host supervisor remain proposals. A
> helper present in a plan is not an accepted runner.

The current host design is the host relay: the provider key is held only by the relay, and the job reaches the model
only through the relay channel (`docs/qualification/hermes-actual-operation/README.md`, `deploy/coolify/RUNBOOK.md` §6).

## Runner and credential rows

| # | Check | Expected observation | Result |
|---|---|---|---|
| 1 | Job container isolation | pinned Hermes runs in a no-network, read-only job container | PENDING (post-registration; see N5) |
| 2 | Resource bounds | 512 MB memory, 1 CPU, 64 processes | PENDING (post-registration; see N5) |
| 3 | Capability and socket bounds | no added capabilities, no Docker socket, no host workspace | PENDING (post-registration; see N5) |
| 4 | Relay-channel route | the job reaches the model only through the relay channel and holds no provider credential | PENDING (post-registration; see N5) |
| 5 | Credential mount | the job container mounts only its turn folder and read-only job code; no provider key, admission key, grants or state | PENDING (post-registration; see N5) |
| 6 | Credential isolation (host relay) | the provider key is held only by the relay; the research side cannot read it; a third user is denied | PASS |
| 7 | API/model process has no Docker socket | no public-stack container mounts the Docker socket | PASS |
| 8 | Runner presence | `build_transport_job`, `TransportJob.runner` and `recover_pending(C)` are mounted and reachable | PENDING (post-registration; see N5) |
| 9 | Owned supervision (host relay) | the relay supervisor owns the relay lifecycle; the host units enforce the bounds and the durable shared ledger is accepted | PENDING (post-registration; see N5) |
| 10 | Cleanup | a completed, cancelled and timed-out job cleans its process and temporary files | PENDING (post-registration; see N5) |

### Row 6 evidence (PASS)

Source: `.scratch/vps-live-20261026/RELAY-START-EVIDENCE.md` SHA-256
`bdb833c1cfa9920705754b2c6330811a73a3e2d7ba89e6f02d79549f3f9cc2f4`, section HOST-SHARE-L4.

Each value is the exit code of one `test` access attempt: `0` means allowed, `1` means denied. As
`edge-os-research` with the share group, the deployed identity gives:

| Item | Value | Meaning | Expected |
|---|---|---|---|
| provider key `/etc/edge-os/relay/provider-key` read | 1 | denied | denied |
| relay config read | 1 | denied | denied |
| provider config read | 1 | denied | denied |
| relay state write | 1 | denied | denied |
| admission key read | 0 | allowed | allowed |
| grants write | 0 | allowed | allowed |
| `/etc/edge-os/relay/relay.json` read (extra) | 1 | denied | denied |
| handoff read (extra) | 0 | allowed | allowed |

A third user (`nobody`) is denied: `admission read=1` (denied), `grants write=1` (denied). The relay container runs as
user `995:985`, with a read-only root, `cap_drop ALL`, and `network none`. The relay unit holds the provider key; the
research side cannot read the relay config, provider config or provider key under `/etc/edge-os/relay`.

### Row 7 evidence (PASS)

Source: `.scratch/vps-live-20261027/ROUTE-PROBE.md` SHA-256
`3c5c62a8e82aa6168a698206a47d6d91ccb3b1d01c3f75d5f5b0cb6b50fb746f`, last section.

`docker inspect` mounts: `api` none; `web` none; `recurring-producer` none; `execution-worker` only
`/etc/edge-os/execution`. No container of the public stack mounts the Docker socket.

## Public Hermes route (§6.3)

The host application serves exactly these six paths and methods, plus `GET /healthz` and `GET /readyz`. Every other
path is `404`.

```text
GET  /v1/interpreter
POST /v1/research/requests
GET  /v1/research/requests
GET  /v1/research/requests/{intake_id}
POST /v1/research/requests/{intake_id}/clarifications
POST /v1/research/requests/{intake_id}/interpretation-retries
```

Forward settings: the `api` forwards exactly those six paths and methods and keeps every other path. The forward
requires the Privy principal and the write limit before it sends a byte. It forwards only `Authorization`,
`Content-Type` and `Accept`; it returns only `Content-Type` and `Retry-After`; it adds no owner header. It never follows
a redirect and never reads `HTTP_PROXY` or `NO_PROXY`. A connect failure is `503 interpreter_unavailable`, a read
timeout is `504 interpreter_timeout`, and any other transport failure is `502 interpreter_route_failed`. With
`EDGE_OS_HERMES_APP_URL` empty in production, the six paths return `503 interpreter_unavailable`.

| # | Route check | Expected observation | Result |
|---|---|---|---|
| R1 | Bind address | the application binds one IPv4 private address only, never `0.0.0.0` or `[::]` | PASS (stand-in: `10.0.1.1:8011` only) |
| R2 | Firewall rule | one INPUT rule allows TCP 8011 from the `coolify` subnet to the gateway only; default deny incoming and routed; no IPv6 rule | PASS |
| R3 | Reachable from `api` on `coolify` | HTTP 200 from the `api` container | PASS (stand-in) |
| R4 | Not reachable off `coolify` | connect fails from `execution-worker` | PASS (stand-in; errno 11, 5 s timeout) |
| R5 | Not reachable from the internet | `nc` from outside times out | PASS (stand-in; `Operation timed out`) |
| R6 | Auth and write limit before the forward | unauthenticated, over-size and over-limit requests are refused before the upstream; only allowlisted headers are forwarded; the upstream URL is not taken from a client header | PASS (code) |
| R7 | Real application guard | the real application binds only the gateway and answers `/healthz`, `/readyz` and 404 elsewhere | PENDING (post-registration; see N5) |
| R8 | Public API principal | the six paths through the public API need a Privy principal | PENDING (post-registration; see N5) |

### Route evidence

Source: `.scratch/vps-live-20261027/ROUTE-PROBE.md` SHA-256
`3c5c62a8e82aa6168a698206a47d6d91ccb3b1d01c3f75d5f5b0cb6b50fb746f`.

- `coolify` bridge `br-8585338b6fd5`, IPv4 `10.0.1.0/24`, gateway `10.0.1.1`.
- Firewall: `ufw allow in on br-8585338b6fd5 from 10.0.1.0/24 to 10.0.1.1 port 8011 proto tcp comment "edge-os hermes app from coolify"`.
  Numbered rule: `[ 4] 10.0.1.1 8011/tcp on br-8585338b6fd5 ALLOW IN 10.0.1.0/24`.
  `ufw-user-input`: `-A ufw-user-input -s 10.0.1.0/24 -d 10.0.1.1/32 -i br-8585338b6fd5 -p tcp -m tcp --dport 8011 -j ACCEPT`.
- `ss -ltn`: `LISTEN 10.0.1.1:8011` only.
- From the `api` container (on `coolify`): HTTP 200.
- From the `execution-worker` container (off `coolify`): connect failed (errno 11, 5 s timeout).
- From the controller Mac to the public address: `Operation timed out`.
- Cleanup: listener stopped; no 8011 listener left; temporary folder removed.

### R6 tests (code, integration `275b399`)

`apps/api/tests/test_hermes_proxy.py`:
`test_an_unauthenticated_request_is_refused_before_the_upstream`,
`test_the_write_limit_runs_before_the_forward`,
`test_an_over_size_request_body_is_refused_before_the_upstream`,
`test_only_the_allowlisted_request_headers_are_forwarded`,
`test_the_upstream_url_is_not_taken_from_a_client_header`.

## Stop condition

A missing isolation control keeps real-model and hosted research unavailable. Do not run a real Hermes job without the
accepted isolation and a recorded inference budget.

> Controller decision 2026-10-30 (gate note N5). The host application refuses to start in production until a hosted
> record is registered, so the rows marked PENDING cannot run before registration. The record is registered with this
> file as it stands. The public route stays closed until every PENDING row passes: the controller does not set
> `EDGE_OS_HERMES_APP_URL` on the public API and does not deploy the new API image before that. Without that value the
> six paths return `503 interpreter_unavailable`. The controller records the post-registration results in a separate
> evidence file outside this record; this file is not edited after registration. A failed PENDING row stops the public
> route and needs a new record.

## Recorded evidence

- Relay start and credential isolation: `.scratch/vps-live-20261026/RELAY-START-EVIDENCE.md` SHA-256
  `bdb833c1cfa9920705754b2c6330811a73a3e2d7ba89e6f02d79549f3f9cc2f4`.
- Route probe and Docker-socket check: `.scratch/vps-live-20261027/ROUTE-PROBE.md` SHA-256
  `3c5c62a8e82aa6168a698206a47d6d91ccb3b1d01c3f75d5f5b0cb6b50fb746f`.
- Forward code and tests: integration `275b399`, `apps/api/tests/test_hermes_proxy.py`.
