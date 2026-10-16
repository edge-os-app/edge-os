# Hermes provider relay: the host-held credential boundary (contract)

Task `HERMES-RELAY-L1-20261013-LOCAL-v1` (#58 support). Status: LOCAL, synthetic credential, AUTHORED provider only. Written before code on base `ff1d958c47f2891707b4aa9b5b06541eb5289633`. This note gives no authority: no actual provider, model, network, credential, spending, deployment or public operation. Every ACTUAL route stays refused.

Adopted design: `.scratch/hermes-relay-adoption-20261013.md` (builder adoption of the host-held relay, LOCAL only), with the boundaries of `.scratch/hermes-relay-decision-20261013.md` and the endpoint/credential/owner restrictions of `.scratch/hermes-relay-guidance-20261013.md`.

## 1. What changes, what does not

The accepted transport job (`scripts/hermes_job_support/`) puts the transport and a credential copy inside the Hermes job process. The relay moves both out:

```
Hermes job container  (--network=none, no credential mount, accepted GuardedDockerTurnRunner and JobEntry)
  physical admission + accepted guard (unchanged, in the job)
  -> job channel: one request file in the job's own output folder           (no socket, no host shell)
Relay container       (internal Docker network shared ONLY with the authored provider; holds the synthetic key)
  -> grant check: signed host grant for exactly this owner/request/job/attempt/route/release, open, unexpired
  -> accepted guard again, on the exact bytes, with the grant's policy and logical request
  -> durable start record (exclusive create) BEFORE the one HTTPS request
  -> one HTTPS POST to the fixed destination: fixed path, fixed headers, relay key, admitted body byte for byte
  -> bounded reply back into the job channel; finish record
Authored provider container (same internal network): scripted reply per attempt, its own receipt log
```

Unchanged and read-only: `scripts/hermes_job_support/*`, `scripts/hermes_interpretation/*`, `apps/api/**` (including `hermes_transport_mount.py`, `provider_spend_ledger.py`, settings, schema, usage, worker, verifier, web). Reused as they are: `GuardedDockerTurnRunner` + `JobEntry`, `GuardedTurnRunner`, `TransportTurnRunner`, `provider_guard`, `provider_transport` (`physical_refusal`, `host_request`, `reply_refusal`, `TransportRoute`), `SpendLedger` / `PostgresSpendLedger`. No second job engine, ledger, scheduler or auth system. Root dependencies and lockfiles unchanged. Containers use the pinned Hermes image already built by the accepted tests; relay and provider code is standard library only.

## 2. Files (all new)

| Path | Responsibility |
|---|---|
| `scripts/hermes_provider_relay/relay_admission.py` | Shared, standard library, no I/O: `RelayRelease`, `ProviderDestination`, `RelayGrant`, grant signing and checking, the channel message shapes and `channel_refusal`. |
| `scripts/hermes_provider_relay/relay_transport.py` | The one HTTPS send: `send_once(destination, key, body, timeout, max_reply_bytes)`. `http.client`, TLS verified against the configured CA, no redirect, no retry, no streaming, a fresh connection per attempt, reads at most `max_reply_bytes + 1`. |
| `scripts/hermes_provider_relay/relay_service.py` | The relay process (container entrypoint). Reads its fixed configuration, key and admission key once; serves channels; records starts, finishes and closes; restart recovery; egress self-probe; heartbeat. |
| `scripts/hermes_provider_relay/relay_job_channel.py` | The job side of the channel: `ChannelTransport` (a `ProviderTransport`) that writes one request file and waits for the reply file. |
| `scripts/hermes_provider_relay/relay_turn_job.py` | The job container entrypoint: the accepted `hermes_turn_job` plus physical admission and guard, then `ChannelTransport`. No credential. |
| `scripts/hermes_provider_relay/relay_turn_runner.py` | Host side: `RelayEndpoint`, `RelayTurnRunner`, `RelayJob`, `build_relay_job`, `relay_job_entry`. |
| `scripts/hermes_provider_relay/relay_supervisor.py` | Host side, explicit effects only: `RelaySupervisor.start/stop/restart/kill_relay/status` for the internal network, the relay container and the authored provider container, every Docker call bounded. |
| `scripts/hermes_provider_relay/authored_provider.py` | The AUTHORED provider process (container entrypoint): HTTPS on the internal network, scripted reply per attempt, receipt log. Test support. |
| `tests/hermes_provider_relay/` | Unit tests (no Docker) and pinned-Hermes, relay, PostgreSQL and application tests (Docker). |
| `docs/qualification/hermes-provider-relay/` | This contract and the results/how-to-check README. |

## 3. Frozen interfaces

### 3.1 Constructor composition (backwards compatible)

```python
build_relay_job(route: TransportRoute, *, release: RelayRelease, endpoint: RelayEndpoint,
                subject_for: Callable[[HermesTurn], RelaySubject],
                policy: GuardPolicy, ledger: SpendLedger, scope_for: Callable[[HermesTurn], str], image: str,
                run_id: str, evidence_dir: Path, script_for: Callable[[HermesTurn], Mapping[str, Any]],
                forbidden: Sequence[str] = (), timeout_seconds: float = 90, run_budget_seconds: int = 60,
                seal_grace_seconds: float = 5.0, recovery_budget_seconds: float = 5.0,
                close_budget_seconds: float = 2.0) -> RelayJob

@dataclass(frozen=True)
class RelayJob:
    runner: GuardedTurnRunner             # give this to HermesInterpreter / create_app(settings, hermes_runner=...)
    supervision: GuardedDockerTurnRunner  # accepted: recover_pending, pending_cleanup, retry_exhausted, purge_quarantine
```

Every keyword of the accepted `build_transport_job` keeps its name, meaning and default, except `credential_file`, which does not exist: the job never gets a credential. The added keywords are `release`, `endpoint`, `subject_for` and `close_budget_seconds`. Composition:

```
GuardedTurnRunner (accepted: policy, reservation, settlement)
  -> RelayTurnRunner (grant before the job, close and independent count after it)
    -> TransportTurnRunner (accepted: job report names this attempt and route)
      -> GuardedDockerTurnRunner(job_entry=relay_job_entry(route, release), credential_file=None) (accepted: D, sealing, C)
```

Construction does no I/O: it reads no file, writes nothing, starts nothing and reads no key. Refused before anything is built: a route that is not `AUTHORED` (`ActualProviderUnavailable`, with or without a release), a release whose route, model or output limit differs from the route and policy (`ValueError`), and a non-finite or non-positive `close_budget_seconds`. There is no flag that enables an ACTUAL route or a real credential.

### 3.2 Release and destination

```python
RelayRelease(release_id: str, route_id: str, kind: "AUTHORED", model: str, max_output_tokens: int,
             max_request_bytes: int, max_reply_bytes: int)
ProviderDestination(host: str, port: int, path: str)   # https only; scheme fixed, no user, query or fragment
```

Both are fixed when the relay starts. The relay refuses to start for any kind other than `AUTHORED`. The job sees `release_id` and `route_id`, never the destination or any key.

### 3.3 Admission grant (host -> relay)

`RelayTurnRunner` writes one grant per attempt, after the accepted runner reserved spend and before the job starts:

```
grant = {grant_id, release_id, route_id, run_id, channel_root, owner_id, request_id, attempt_id, scope,
         policy{model, max_output_tokens, max_request_bytes, max_envelope_chars, required_extra},
         logical{system_prompt_sha256, user_message_sha256} + the two texts, issued_at, expires_at, mac}
```

`mac` is HMAC-SHA256 over the canonical JSON of every other field with the admission key, a 32-byte random file made by the supervisor, readable by the host and the relay only. The grant is created exclusively (`grants/<attempt_id>.json`, temporary file and rename, an existing grant refuses). `expires_at = issued_at + timeout_seconds` (wall clock), so no request can start after the job's own timeout. The grants folder, the admission key and the relay state are never mounted into the job.

Before writing a grant, `RelayTurnRunner` requires, and otherwise returns `PROVIDER_FAILED`, request count 0, `guard_admitted` 0 (so the accepted runner releases, as nothing can have been sent):

- `ledger.state(attempt_id) == "RESERVED"` (`RelayReservationMissing`);
- `subject_for(turn)` returns the owner and saved request, and raises when they cannot be proved (`RelaySubjectUnavailable`);
- a relay heartbeat no older than 2 s whose release equals this release (`RelayUnavailable`).

An existing grant for the attempt returns `UNKNOWN`, request count unknown (`RelayGrantExists`): it may belong to a turn that sent.

### 3.4 Job channel (job <-> relay)

Inside the job output folder: `relay-channel/request.json`, written once by temporary file and rename, then `relay-channel/reply.json`, written once by the relay the same way.

```
request = {"attempt_id", "route_id", "release_id", "body_b64"}                       exactly these keys
reply   = {"attempt_id", "outcome": "reply"|"refused"|"lost", "status"?, "body_b64"?, "refusal"?}
```

The relay opens every path component without following links, requires plain files and folders, reads at most `2 * max_request_bytes + 4 KiB`, and refuses (reply `refused`, no start record, no request): a missing, closed, expired or invalid grant; a grant whose MAC fails; a turn folder whose name does not end with the grant's attempt; more than one turn folder for the attempt; any key other than the four; an attempt, route or release other than the grant's; a body that is not base64, is over `max_request_bytes`, or that the accepted guard refuses under the grant's policy and logical request (`guard:<reason>`). The relay builds the request itself: method POST, the release destination path, headers `accept`, `content-type: application/json`, `content-length`, `authorization: Bearer <relay key>`, `host`; nothing from the job except the body bytes.

### 3.5 Relay records (outside the job, the independent count)

`state/<attempt_id>/`: `started.json` (exclusive create and fsync BEFORE the connection opens), `finished.json` (`outcome` `reply` / `refused_reply` / `lost` / `unknown_restart`, status, reply bytes and SHA-256, reported usage, timings), `closed.json` (`started: true|false`, written exactly once). One lock in the relay process orders start and close for an attempt: after `closed.json` exists no start can happen, and a start is never made without its record. `events.jsonl` keeps every channel refusal with its reason (bounded). The authored provider keeps its own `receipts.jsonl` (attempt, body SHA-256, header names, whether the bearer equals its expected synthetic key; never the value).

### 3.6 Close and settlement inputs (`RelayTurnRunner`, after the job)

On every path out of the delegate (result or exception), `RelayTurnRunner` writes `revocations/<attempt_id>.json`, then waits at most `close_budget_seconds` for `closed.json`. This wait is after D, like the accepted ledger commit. Then:

| Relay record | Job report | Result passed to the accepted runner |
|---|---|---|
| closed, not started | count 0 | unchanged: count 0, guard 0 -> RELEASED (zero effect proved outside the job) |
| closed, not started | count 1 or unknown | `UNKNOWN`, count unknown (`RelayCountMismatch`) |
| closed, started, finished `reply` 2xx, usage equal to the job's wire usage | count 1, COMPLETED/TRUNCATED | unchanged -> SETTLED exact |
| closed, started, anything else | any | not COMPLETED/TRUNCATED: unchanged status if already UNKNOWN/PROVIDER_FAILED/TIMED_OUT with count not 0; otherwise `UNKNOWN`, count unknown (`RelayCountMismatch`). Liability kept |
| not closed within the budget, or unreadable | any | `UNKNOWN`, count unknown (`RelayStateUnknown`). Liability kept |

`observed` gains `relay_release_id`, `relay_grant_id`, `relay_started` (true/false/null) and `relay_outcome`. A zero-request release therefore needs the relay's own closed-not-started record; the job's report alone never releases.

## 4. Enforced boundaries

- Job: the accepted runner's `--network=none`, read-only root, no capabilities, no credential mount (`credential_file=None`), no socket, no host workspace. Its only writable path is its output folder.
- Relay: one container on one Docker network created `--internal` with only the authored provider on it; no published port; read-only root; no capabilities; only these mounts: the relay code (ro), the synthetic key (ro), the admission key (ro), the provider CA (ro), the grants folder (ro), `state/` and `revocations/` (rw), and each configured channel root (rw: it writes replies). It records an egress self-probe at start: the provider reachable; 1.1.1.1, the Docker host gateway and `host.docker.internal` unreachable.
- Provider: the same internal network, its scripts (ro), its CA key pair (ro), its receipt folder (rw).
- No component gives the job a URL, host, header, credential, model, budget or retry it can choose.

## 5. Deadlines, supervision, restart

- D: unchanged, the accepted runner's single per-turn deadline. The grant expires at `issued_at + timeout_seconds`; the relay's send timeout is the time left until expiry (never renewed), and it never starts at or after expiry.
- Relay recovery C: on start the relay reads every `started.json` without `finished.json`, writes `finished.json` with `unknown_restart` and replies `lost` into a still-open channel. It never sends for such an attempt again. It closes expired grants (`closed.json`, started as recorded). Bounded by a fixed entry count and its own budget.
- Host restart: the accepted `recover_pending` (C) handles the job container. The dead turn's grant expires and the relay closes it; its reservation stays RESERVED (accepted rule: recovery never touches spend).
- Supervisor: `RelaySupervisor` starts network, provider and relay by exact name and label, waits for a heartbeat within a fixed budget, stops and removes exactly those, and reports leftovers. Every Docker call has a timeout.

## 6. Fault matrix (request -> possible effect -> timeout/crash -> stop -> evidence -> cleanup -> accounting -> restart)

| Fault | Provider requests (relay / provider receipts) | Stop | Evidence | Cleanup | Spend | Restart |
|---|---|---|---|---|---|---|
| ACTUAL route, release mismatch | none: construction refused | - | none | - | nothing | - |
| No reservation, subject unknown, relay down | 0 / 0, no grant, no job | - | none | - | RELEASED or never reserved | - |
| Wrong, cross-owner, stale, altered or unsigned grant; altered route, release, model, header, credential, oversized or malformed channel message | 0 / 0 | job ends (Hermes gets an error) | relay refusal event; sealed job output | accepted | relay closed-not-started -> RELEASED | - |
| Duplicate channel request, recovered request after restart | at most 1 / at most 1 | - | relay refusal `already_started` | - | by the first request | never resent |
| One request, usable usage | 1 / 1 | job ends | relay start, finish, close | accepted | SETTLED exact (relay usage equals job usage) | - |
| Lost reply, oversized reply, redirect, provider error, missing usage | 1 / 1 | job ends | finish `lost`/`refused_reply` | accepted | UNKNOWN, full reservation | held |
| Hung provider | 1 / 1 | relay timeout at grant expiry; job stopped at D | finish `lost` | accepted | UNKNOWN or TIMED_OUT, held | held |
| Cancel/expiry before send | 0 / 0 | grant expired or closed | refusal `grant_expired`/`grant_closed` | - | RELEASED when closed-not-started | - |
| Relay killed after start, before finish | 1 possible / 0 or 1 | relay restart | `unknown_restart` | channel reply `lost` | UNKNOWN, held | never resent |
| Host process killed mid-turn | 0 or 1 | accepted recovery within C; grant expires | relay closes at expiry | accepted | stays RESERVED | accepted |
| Close record not seen in budget | unknown | - | `RelayStateUnknown` | - | UNKNOWN, held | - |

## 7. Pre-agreed test seams

1. Trusted relay admission/request interface: `relay_admission` functions and the relay process through its channel and grant folders.
2. Job-owned bounded channel: `ChannelTransport` against a relay, and hostile job scripts writing raw channel files.
3. Existing `run_turn` and shared reservation: `RelayJob.runner.run_turn` through `HermesInterpreter` and `create_app`, with SQLite `SpendLedger` and `PostgresSpendLedger`.
4. Authored provider request log: provider `receipts.jsonl` and relay records as independent counts.
5. Existing supervision: `RelayJob.supervision.recover_pending` and `RelaySupervisor.restart`/`kill_relay`.

## Amendments

A1 (during implementation, before the first review): corrections and additions, no change of boundary or authority.

- Channel reply (3.4): a refusal reply also carries `before_send` (true: the relay refused before any request; false: the relay sent and refused the reply). The job counts a request only when `before_send` is false or the outcome is `reply`/`lost`.
- Relay refusal of a request the job's own guard admitted (fault matrix row 3): the job guard's count is 1, so the accepted `GuardedTurnRunner` keeps the full reservation as UNKNOWN even though the relay's record proves nothing was sent. The relay does not rewrite the job guard's evidence. RELEASED needs both the relay's closed-not-started record and the job guard's 0 (a physical or guard refusal inside the job, a relay that was down, no reservation, no subject). This is conservative: an honest job never meets a relay refusal.
- A hostile job that writes no `container-result.json` ends UNKNOWN (accepted runner: `ContainerResultUnreadable`) and keeps the reservation.
- Two turn folders for one attempt (`channel_ambiguous`) are not served at all: no reply, no request; the grant closes at revocation or expiry.
- The relay caps the open grants it serves in one pass at 1,024; closed attempts are skipped first (found by self-review; regression test `test_a_new_grant_is_served_however_many_earlier_attempts_are_closed`).
- New owned file `scripts/hermes_provider_relay/relay_application_mount.py`: `open_relay_mount`, the accepted `open_transport_mount` composition (same refusals, PostgreSQL ledger, intake scope, startup recovery) over `build_relay_job`, with `subject_for` reading the saved attempt's owner and saved request and requiring them to equal the reservation row's owner, saved request and scope. Additive; `hermes_transport_mount.py` is unchanged and only imported.
- Known limit: grant times use the host wall clock and the relay's (Docker VM) wall clock, with a 2 s allowance for a grant issued in the relay's future. A relay clock behind the host lets a request start up to that skew after the host's intended expiry; it is still recorded and its liability held.

A2 (internal review round 1 on `0c40297`: Reviewer A REVISE F1/F2 blocking, F3-F5 and N1-N5 non-blocking; Reviewer B PASS with N1-N5 non-blocking). Repairs, each with a regression test that failed before it:

- A-F1: the counted path of section 3.6 now also requires the relay's recorded HTTP status to be 2xx (`relay_turn_runner._limited`). A non-2xx reply, or a finished record without a status, is withheld as UNKNOWN with the full reservation, whatever usage the job reports.
- A-F2: `relay_transport.send_once` keeps ONE total deadline: a watchdog shuts the socket down at the grant expiry, so a provider that drips headers or body cannot hold a request past it (`test_relay_transport.py`).
- A-F3: the relay refuses, before any start record, a body whose `session_id` is not `p05-<grant attempt>` (`body_attempt_mismatch`), the same binding the job's physical admission applies.
- A-F4: wording. Sections 3.1/3.6 "COMPLETED/TRUNCATED" mean the runner statuses `RETURNED`/`TRUNCATED`. Section 4: the AUTHORED provider container also mounts the synthetic key read-only (`/provider/expected-key`) to check the bearer; "only the relay reads the key" is about the Hermes side. Section 5: relay start-up recovery now also has a time budget (`RECOVERY_SECONDS`, 5 s); an attempt it does not reach stays started-without-finished, which the host reads as unknown, and is never resent.
- A-F5: the host accepts a relay heartbeat up to the grant clock allowance (2 s) in its future.
- A-N1: test that `open_relay_mount` refuses production, another interpreter, ACTUAL and a mismatched policy before any engine (`test_relay_application_refusals.py`).
- A-N3 / B-N1: relay records are created by temporary file and `os.link`, which never replaces an existing name, so a start record is exclusive even across processes (the host already did this).
- B-N2: a grant the relay cannot serve (malformed fields, any exception) is reported once as an event and skipped; other attempts are served.
- B-N3: the relay writes no reply into a channel once the host revoked the grant (the job is over and its output sealed); it records `late_reply_not_written`.
- B-N4: the relay's egress self-probe also targets its own internal network's gateway (ports 53 and 80, expected blocked).
- Not changed: A-N4 (the relay mounts each whole channel root read-write; narrowing it needs a per-turn mount the accepted runner does not offer), A-N5/B evidence (resource equality is shown by exact name/label leftovers, not by a host-wide inventory, because other lanes create resources at the same time), B-N5 judgment calls (the relay stays standard library only and separate from host modules).

A3 (internal review round 2 on `f1a2dd6`: Reviewer A REVISE F2b blocking). A reply that closes the connection (`Connection: close` or HTTP/1.0) made `http.client` detach the socket from the connection, so the A2 watchdog found no socket and a dripped body again ran on per-read timeouts. The watchdog now keeps its own reference to the socket taken right after the request is sent, and the send stops if the deadline already passed at that point. New `test_relay_transport.py` cases send the head at once and drip only the body: keep-alive, `Connection: close` and HTTP/1.0 (the last two failed before the repair). Reviewer B round 2 found the same defect (R2-B1) and a third shape, a reply with no length that ends at connection close; a test case covers it too (it also failed before the repair).

Round 2 non-blocking notes: R2-B2, known limit: the host revokes a grant only after the accepted runner returned, which is after it sealed the job output, so a relay reply that lands in that short window still enters the sealed folder (a fixed `lost`/`refused` record or a bounded provider body; never the key, which never enters the channel). Closing it needs a seam inside the accepted runner, outside this lease. R2-B3: `os.link` on the relay's bind-mounted state folder and the own-gateway probe are shown only by the Docker run (the supervisor now skips the gateway probes if Docker reports no gateway, and the Docker test requires them).

A4 (finding R5-B1 on `5e8059b`, Reviewer B round 5, BLOCKING; LOCAL topology adopted by the builder for this repair in `.scratch/hermes-prototype-to-application-20261014/ADOPTION_AND_QUEUE.md`, as proposed in `.scratch/dw-l1-topology-choice1.md`). From an `--internal` network the network's own gateway answered TCP with a refusal: a reply from the Docker host, not a blocked path. The relay's probe recorded every `OSError` as "not reached", so the earlier claim that the probe showed the gateway blocked was false. A4 replaces the relay and provider bullets of section 4, the network lines of the section 1 diagram, and B-N4.

- Topology: the AUTHORED provider runs with `--network none` and listens on `127.0.0.1:8443`. The relay runs with `--network container:<provider id>`, the exact id that `docker run` returned at start. The pair shares one network namespace with loopback only: no other interface up, no IPv4 route, no IPv6 route outside `lo`, no gateway. No port is published. Processes, root filesystems, users and mounts stay separate and unchanged (the provider mounts the synthetic key copy that A2 A-F4 names and never the admission key; the relay mounts no provider TLS key). The provider certificate names `localhost`; the relay's fixed destination is `https://localhost:8443/v1/chat/completions`. The Hermes job is unchanged: `--network none`, no key.
- Fail closed: the relay never joins by name. If the recorded provider is gone or a new container took its name, a relay start or restart fails and no relay runs. A relay whose provider died keeps only its loopback namespace: the provider address then refuses, nothing else exists, and the attempt's liability stays held (`lost`, UNKNOWN). No relay is ever attached to a default or other network.
- Probe outcomes (`relay_service.connect_outcome`): `connected`, `refused`, `unreachable` (ENETUNREACH or EHOSTUNREACH: the kernel has no route), `dns_failure`, `timeout`, `error`. Only `unreachable` says no route exists. `refused` says a host answered. `dns_failure` and `timeout` prove nothing either way. The heartbeat now probes only the provider, as a positive control (`connected`).
- Evidence of the namespace comes from each container's own kernel through `docker exec` (`relay_supervisor.KERNEL_VIEW`): namespace id, interfaces, up interfaces, routes. Docker's `HostConfig.NetworkMode` must be `none` for the provider and `container:<provider id>` for the relay.
- Escape test with positive controls: an owned listener on an owned ordinary bridge (no published port to any interface but host `127.0.0.1`), probed by the same `connect_outcome` code from a control container on that bridge, then from inside the relay, then from the control again. Controlled targets: the listener's address, `host.docker.internal` and the address it resolves to (the Docker Desktop host), each through the port published on host `127.0.0.1` only. Each control must be `connected`. The relay must see `unreachable` for every address (and `dns_failure` or `unreachable` for the name). Bridge gateway addresses are probed and recorded too; without a working control they support no claim. No Internet address is probed.
- Limit: this proves LOCAL isolation for an AUTHORED provider on this Docker host. It is not an egress path to any real provider and not a production isolation qualification; see `ONLINE_CONTINUATION.md`.

A5 (gate finding G1 on `3c1cc24`, gate REVISE 1/3; controller disposition `.scratch/hr-l1-g1-cut2.md`). The gate's strict check (`send_once` returns no later than the fixed grant expiry, with no allowance) failed: a `Connection: close` body drip returned 10.6 ms after expiry. Two causes were measured on this host. `send_once` took the time left before it built the TLS context, so setup time was added after expiry. And a watchdog planned AT expiry cannot return by expiry: its thread woke 1.6 to 5.2 ms late, and the return took 0.2 to 0.6 ms more. These are observations on one host, not a full cause list or a maximum stall.

- `relay_transport.CUT_LEAD` is 0.1 s. The send ends at `expiry - CUT_LEAD`: the watchdog, the socket timeout and the final completeness check all use that time. They are computed after setup, and the watchdog interval is taken when it starts. With less than the lead left (at the call or after setup) the send is refused before any connection is built: `ReplyLost("no time was left for the request")`.
- This replaces "at the grant expiry" in section 5 and A-F2 for the relay's own send. The grant expiry, D, the strict check and every accounting rule are unchanged. The lead only shortens the usable request time. A reply that ends inside the lead is `ReplyLost`: the existing conservative path (finish `lost`, UNKNOWN, full liability, never resent).
- Tests: the six drip cases now assert the return is no later than the fixed expiry itself (no allowance). Fake-clock tests check the watchdog and socket targets after setup, refusal with less than the lead left, and one send with a reply completed inside the lead lost. Each failed before the change.
- Limit: 0.1 s is not a hard real-time guarantee on a general-purpose host. A longer stall can still return late, and the strict checks would show it as a failure. The lead must not be raised after a failure without the measured evidence going back to the controller.

A6 (E1 online continuation, frozen before its code). Authority: builder approval of proposal E1 (`ONLINE_CONTINUATION.md` section 5, SHA256 53d59a0a...), recorded in `.scratch/hr-e1-approved1.md` (2eebfb64...) and START `.scratch/hr-e1-start1.md` (b3d44aae...). Implementation and synthetic tests only: no real key, provider request, account or spending. `ONLINE_CONTINUATION.md` sections 1-7 apply; this amendment fixes the exact values the code must meet. Model, routing, prices and cost bounds stay inputs of a later qualification packet.

- Destination: `openrouter.ai`, port 443, path `/api/v1/chat/completions`, taken only from the release record; never from the job, a setting or the environment.
- Release identity: kind `ACTUAL` exists only as a frozen release record file (section 3 fields). The relay and the host load it by path and SHA256, and both refuse a record whose SHA256 is not in `relay_admission.APPROVED_ACTUAL_RELEASES`. That set is EMPTY in this candidate, so every ACTUAL start fails closed until a later approved packet names an exact record. A record may not name a test resolver; synthetic CA and resolver exist only in AUTHORED online-shaped tests.
- Socket: the gateway listens only on `gateway.sock` in a private host folder (mode 0700, holding nothing else), mounted at `/egress` in the gateway and `/relay/egress` in the relay; socket mode 0600; both containers run as the same non-root user. No TCP listener, published port, host network, `NET_ADMIN` or Docker socket.
- CONNECT protocol (relay to gateway, one per connection): `CONNECT openrouter.ai:443 HTTP/1.1`, `Host: openrouter.ai:443`, `X-Relay-Attempt: <attempt id>`, `X-Relay-Expires: <grant expiry, epoch seconds>`; head at most 1,024 bytes; no byte may follow the head before the gateway answers. Answers: `HTTP/1.1 200 Connection Established` or `HTTP/1.1 403 Forbidden` with `X-Refusal: <reason>`, then close. Refused: another method, name, port or version; an IP literal; a missing or invalid attempt or expiry; an expiry already past or more than 120 s ahead; extra bytes; a second tunnel for an attempt the gateway has receipts for.
- DNS: the gateway resolves the name itself (TCP, port 443). Any answer that is not globally routable (loopback, private, link-local, multicast, reserved, unspecified, shared 100.64/10, IPv4-mapped or Docker ranges) refuses the whole CONNECT. It connects once, to the first answer only; no fallback address, no retry.
- Tunnel: bytes are copied unchanged (TLS stays end to end; the gateway holds no key or CA). It closes at the earlier of the relay's expiry and 120 s, at 4 MiB in either direction, or when either side closes.
- Receipts: one JSON line per gateway connection in `receipts/tunnels.jsonl`, written and fsynced before the gateway answers a refusal and when a tunnel closes: time, attempt, outcome (`tunnel` or `refused`), reason, resolved address, bytes each way, close reason. Counts: relay `started.json`, gateway `tunnel` receipts and provider generation ids are three separate counts per attempt.
- Deadline: unchanged fixed grant expiry; the relay's own send (A5) ends `CUT_LEAD` (0.1 s) before it and covers the gateway socket, the CONNECT exchange, TLS and the reply. The gateway's close at expiry is a backstop only.
- One attempt: `started.json` is still written before the gateway is contacted; any failure after that is `lost` (UNKNOWN, full liability), never resent.
- Request (ACTUAL): before any start record the body must be one JSON object (no repeated key) with only the record's allowed fields; `model`, `stream` false, `max_tokens`, `provider` (canonical JSON), `reasoning` and the `response_format` SHA256 equal to the record; `session_id` equal to `p05-<attempt>`.
- Reply (ACTUAL counted path): 2xx, `application/json`, no `content-encoding`, one choice, `finish_reason` `stop`, the record's model, integer `prompt_tokens`/`completion_tokens`/`total_tokens` and a finite non-negative numeric `cost`. Anything else is recorded `refused_reply` and stays UNKNOWN.
- Settlement gap, reconciled explicitly: section 4 of `ONLINE_CONTINUATION.md` settles at the provider-reported cost. The accepted ledger (read-only for this lane) settles by tokens × its price. This lane therefore counts a result only if the reported cost is at most the attempt's reserved liability (`ledger.liability_usd`), and records the cost; settling at the reported cost needs a later ledger-owner change.

Fault matrix additions (requests leaving the gateway / outcome): gateway down or socket missing 0 / `lost` UNKNOWN; refusal (name, literal, port, extra bytes, repeated attempt, expiry) 0 / `lost` UNKNOWN with a refusal receipt; non-global DNS answer 0 / refusal receipt, UNKNOWN; connect failure 0 / refusal receipt, UNKNOWN; TLS name or CA mismatch 0 bodies / `lost` UNKNOWN; tunnel cut at expiry or byte limit 0 or 1 / `lost` UNKNOWN; encoded, redirect, non-JSON, truncated, wrong model, missing usage or cost 1 / `refused_reply` UNKNOWN; gateway killed during a tunnel 0 or 1 / `lost` UNKNOWN, never resent; relay killed after start 0 or 1 / `unknown_restart`.

A6 clarifications made during its initial implementation (same stage, before any runtime check):

- Socket folder: a labelled tmpfs Docker volume (`relay-egress-<run>`, `uid`/`gid` of the one non-root user both containers run as, mode 0700, 1 MiB), mounted at `/egress` in the gateway and `/relay/egress` in the relay, instead of a host bind mount. It holds only the socket, never exists on the host file system and is removed by `stop()`. A host-folder Unix socket shared by two containers is uncertain on Docker Desktop file sharing; the Docker run must show the chosen form works. `stop()` now also reports `volumes_left`.
- Job side: `relay_turn_job` accepts an ACTUAL route as well as AUTHORED. The job stays keyless with no network either way; only the relay enforces the release.
- Application mount: `relay_application_mount.open_relay_mount` is unchanged and still refuses ACTUAL. ACTUAL app composition stays the later lane-2 successor.
- Test resolution: only the gateway config of an AUTHORED online supervisor has `test_resolution` (the stand-in's bridge address, which must be private and not loopback). An ACTUAL supervisor writes none, and an ACTUAL record cannot contain one.
- ACTUAL construction: `RelayRelease(kind="ACTUAL")` can be built only inside `load_actual_release`; `RelaySupervisor`, `Relay` and `build_relay_job` each take the loaded record, and check the record file, CA bundle hash, route endpoint and policy request shape against it.

A6 test-preparation additions (packet `.scratch/l1-e1-tests1.md`; code and non-network units only; Docker NOT_RUN):

- Gateway count: before its one connect the gateway writes and fsyncs an `opening` receipt, then a `tunnel` receipt when the tunnel closes. The gateway count of an attempt is its `opening` lines, so a gateway killed during a tunnel still leaves its count. A connect failure leaves `opening` then `refused: connect_failed`.
- One gateway budget: the head is read within `HEAD_SECONDS` (5 s; the expiry is unknown before the head). After that the name lookup (abandoned at the budget: `dns_timeout`), the check that time is left (`expired`), the connect (at most the time left, never more than 10 s) and the copy share ONE budget ending at the relay's expiry (at most 120 s). No phase renews it. The receipt fsync is bounded only by the disk (a remaining platform limit).
- Clocks: the relay, the gateway and the stand-in run in one Docker VM and share its wall clock; the host issues grants on its own wall clock (section 5, 2 s allowance). The gateway compares the relay's `X-Relay-Expires` (the grant expiry) with the VM clock. Tests compare host monotonic durations only, never a host time with a VM time. The strict A5 bound (`returned <= expiry`, one clock) is proved by the loopback strict check, not in Docker.
- Docker E1 suite: `test_relay_through_egress_gateway.py` with the session fixture `online_relay` (the default bridge recorded before and after; no change to it). The stand-in gained the reply kind `encoded` (declares `content-encoding: gzip`, never applies it).
- Settlement gap, reproduced (`lane1/checks/e1-tests/settlement-gap.json`): with the candidate's real runner and SQLite ledger, a reported cost of USD 0.02 (above the token charge 0.0074285, within the reservation 0.054848) is counted and the ledger records 0.0074285: USD 0.0125715 LESS than reported. The rule "cost within the reservation" therefore does not prove the charge. ACTUAL stays unreachable (no approved release), so nothing can spend; but this candidate is NOT complete for ACTUAL accounting. Required before any ACTUAL use: either the ledger/outer-runner owner provides settlement at the reported cost, or the lane-1 fail-closed rule below is adopted. Proposed lane-1 rule (not implemented, needs disposition): `build_relay_job` for ACTUAL takes the ledger's `TokenPrice` (the app composition passes the same price it gives the ledger) and counts a result only if the reported cost, rounded up to a nano-USD, is at most the token charge for the reported usage (so the ledger never records less than the provider reported); otherwise UNKNOWN with the full reservation.

A6 E1-COST1 (controller disposition `.scratch/l1-e1-cost1.md`; supersedes the "cost within the reservation" rule and the proposed "cost at most the token charge" rule above, both kept as history):

- `build_relay_job` with an ACTUAL route requires `price`: the accepted `spend_ledger.TokenPrice` the caller gave its ledger. Missing or not a `TokenPrice` refuses construction before any I/O. An AUTHORED route takes no price; AUTHORED behaviour is unchanged.
- A counted ACTUAL result needs, besides the earlier checks (2xx, one start, usage equal to the job's): a finite non-negative numeric provider cost; that cost rounded UP to a whole nano-USD (the ledger's `EXACT` context and `NANO` unit) EQUAL to `price.nano_usd(prompt_tokens, completion_tokens)`; and that charge at most the held reservation (`ledger.liability_usd`). Any difference in either direction, a missing, non-numeric, boolean, non-finite or negative cost, unreadable evidence or a charge above the reservation: UNKNOWN `RelayCostUnverified`, text withheld, no resend, the full reservation held by the accepted outer runner. The generation id and the cost stay in the observed record.
- Proof (non-network): the real `build_relay_job` + `RelayTurnRunner` + accepted `GuardedTurnRunner` + SQLite `SpendLedger`: an equal cost settles at exactly 0.0074285; 0.0012, 0.02, 0.0074284, 0.0074285001 and 0.06 stay UNKNOWN at 0.054848.
- Limits and obligations: this is an interim compatibility check, not settlement at a reported cost. Another provider price, cached-token discounts or other fees give UNKNOWN; settling those needs a later ledger-owner extension. The application successor (lane 2) must pass the SAME TokenPrice it gives its PostgreSQL ledger and prove that price equals the approved price snapshot before any ACTUAL activation; a deliberately different price object is not caught by the type check and stays that owner's obligation. PostgreSQL composition is NOT_RUN here. Every real release stays disabled (no approved record).

A6 R9 (round 8 findings; controller disposition `.scratch/l1-e1-r9prep.md` classifies the first three as qualification gaps to repair before the original reviewers' own runtime; their reports keep their own NON-BLOCKING labels). Finding -> fix -> test (`test_egress_gateway.py`, `test_relay_actual_release.py`, `test_relay_turn_runner_actual.py`; each failed by behaviour on a669b56):

- B R8-B1 -> `address_refusal`: an answer in the RFC 6052 well-known prefix 64:ff9b::/96 is judged by its embedded IPv4 target with the same rule (loopback, private, Docker, shared, link-local, multicast, unspecified refused; a public target stays allowed; one such answer refuses the whole name). Limit: other, network-specific translator prefixes are not recognised.
- B R8-B3 (head) -> `_read_head`: ONE `HEAD_SECONDS` (5 s) budget on the gateway's monotonic clock from the start of the head; each read gets only the time left; past it, `head_timeout` with a receipt before any lookup or connect. Limit: the receipt fsync and thread scheduling after the budget are not bounded by it; a whole-handler 5 s return is not claimed. Real slow-socket proof waits for a runtime grant.
- B R8-B3 (early bytes) -> `_early_bytes`: a non-blocking look (`MSG_PEEK | MSG_DONTWAIT`) after the head and again just before the 200 answer refuses `data_before_tunnel` if client bytes are already queued (a refusal after the connect closes the provider connection unused, after its `opening` receipt). Limit: a byte arriving after the last look and before the answer is not seen; the trusted relay sends nothing before the answer (client contract unchanged).
- A N8-1 / B R8-B2 -> `load_actual_release` bounds `timeout_seconds` to 1..120 (`egress_gateway.MAX_TUNNEL_SECONDS`, imported without a cycle; the job container does not import `relay_admission`); `build_relay_job` with an ACTUAL route requires `timeout_seconds` equal to the record's (a bool or any other value refused before any I/O). AUTHORED unchanged.
- Kept as recorded limits (no change): A N8-2 price-snapshot binding (lane-2 obligation with the TokenPrice/PostgreSQL proof); A N8-3 the test-only approved-record override stays absent from production callers; B R8-B4 attempt marked seen before its first receipt and an abandoned lookup thread after `dns_timeout` (no duplicate provider effect shown: one connect after the opening receipt, no resend); B R6-B1 heartbeat does not see a dead gateway (turns stay UNKNOWN with the full reservation).

A6 peekfix (controller disposition `.scratch/l1-peekfix1.md`; a source-verified regression in R9's `_early_bytes`, found by the controller, my error): CPython waits for readability before any recv on a socket with a POSITIVE timeout, whatever the flags (`MSG_DONTWAIT` does not bypass it). `_read_head` leaves the time left on the socket, so on 35a74a9 a healthy client waiting for the 200 answer made the first look wait the rest of the head budget and raise an uncaught `TimeoutError` (connection closed, no receipt). Fix: the look sets the socket non-blocking (`setblocking(False)`, `recv(1, MSG_PEEK)`), restores the previous timeout in `finally`, and counts any other socket error or a failed restore as early data (refused, never assumed clean). Both callers, the one head budget, receipts and the client contract are unchanged. Unit proof uses a fake that models CPython's positive-timeout wait; real socket-pair tests (`test_egress_gateway_socket.py`: healthy answer without waiting, queued bytes refused with no connect, slow head refused at one shared budget) are written and NOT_RUN until a runtime grant.

A6 peekproof (controller disposition `.scratch/l1-peekproof1.md`): `_early_bytes` now returns the refusal reason: `data_before_tunnel` only when client bytes are actually queued, `socket_state_unknown` when the look or the timeout restore fails, None when nothing is queued. Both callers (after the head; before the 200 answer) record that reason with a receipt before the answer; a refusal before the answer closes the provider connection unused. The earlier record of a failed look as `data_before_tunnel` (5d04b806) claimed bytes that were not seen; it was fail-closed, and no payload or duplicate effect follows. Non-blocking look, timeout restore, the one head budget and all bounds unchanged. The real socket-pair tests were rewritten to be deterministic (the stand-in answers only after the client's bytes; early bytes are queued during the connect so only the second look can see them; owned sockets and threads torn down in `finally`, no owned thread left) and remain NOT_RUN until a runtime grant.

A6 address repair (round 9 finding A N9-1; controller disposition `.scratch/l1-addressrepair1.md`): A6 refuses reserved addresses, but `address_refusal` relied on `is_global`, which Python 3.14.4 sets True for some reserved IPv6 (`::a00:1`, `::7f00:1`, `::c0a8:41fe`, `7000::1`). After the existing NAT64 recursion (which still judges 64:ff9b::/96 by its embedded IPv4, so `64:ff9b::6812:273` stays allowed), any reserved IPv6 answer is now refused `dns_answer_not_global`, and one such answer refuses the whole name. No new decoder or exception; public IPv4 and native public IPv6 stay allowed; mapped, 6to4, Teredo and local-NAT64 forms stay refused. This is a filter repair from a pure computation; no forged DNS answer, real connection or private reachability was tested.

A6 address-class repair (round 10 findings B R10-B1 BLOCKING, A N10-1 and B R10-B2 NON-BLOCKING, joined by the controller into one A6 completeness repair; original labels kept as history). A6 requires a globally routable unicast destination. Python 3.14 calls some non-locator addresses "global": deprecated site-local fec0::/10 (not covered by `is_reserved`), ORCHIDv2 2001:20::/28 (RFC 7343, overlay identifiers, non-routable by design), DET 2001:30::/28 (RFC 9374, non-routable identifiers) and the deprecated 6to4 relay anycast 192.88.99.0/24 (RFC 7526; 192.88.99.2/32 is not globally reachable). After the unchanged NAT64 recursion, `address_refusal` now refuses IPv6 site-local together with reserved, and the fixed named tuple `NOT_LOCATORS` (those three blocks); a NAT64 answer embedding 192.88.99.0/24 inherits the refusal. Public IPv4, native public IPv6, the public NAT64 target and the IANA globally-reachable more-specifics (e.g. 192.0.0.9, 2001:1::1, AS112, AMT) stay allowed. A 95-row address-category matrix (IPv6 Reserved-by-IETF first/interior/last samples, IPv4/IPv6 special-registry classes, the named identifiers, NAT64 embeddings, positive controls) found no other admitted non-global class. Limits: a bounded category matrix, not every address or future registry change; a filter result, with no forged DNS, real connection or reachability test.

A7 (prompt caching off, LOCAL request-shape amendment). Task `HERMES-LIVE-PATH-L1-20261015-LOCAL-v1`, base `19e6063ec72fc676e479a1d9f477c2af3e23020a`. Authority: the builder's answer "turn off caching for the first real call", recorded in `.scratch/demo-finish-20261015/USER_AUTHORITY.md` (2026-10-15), which adopts one exact LOCAL request field. Implementation and synthetic tests only: no record is approved, and no provider request, key, account, ledger reset or spending follows from it.

- Record: one optional field, `prompt_cache_options`. When present its value must be exactly `{"mode": "explicit"}` (canonical JSON), with no breakpoint or other member, and `allowed_fields` must name `prompt_cache_options`; `allowed_fields` may name it only when the record sets it. `prompt_cache_breakpoint` is not an allowed field. A record without the field keeps the A6 shape unchanged, so earlier records and their SHA256 identities still load with `ActualRelease.prompt_cache_options = None`.
- Request (ACTUAL): when the record sets it, the body must carry `prompt_cache_options` equal to the record's value (`body_cache_options_mismatch` otherwise, `body_field_missing` when absent). When the record does not set it, the field is not allowed (`body_field_not_permitted`). Checked with the other A6 body checks before any start record.
- Host: `build_relay_job` requires the guard policy's `required_extra` to hold exactly the record's value (the A6 request-shape check). The application binds and re-checks it (application release contract section 7.2), and the job forwards it through pinned Hermes' `extra_body`.
- Accounting: unchanged. The documented cache setting is a provider-side claim, not proved here. E1-COST1 still counts a result only when the reported cost equals the ledger-price charge; any other cost, including one changed by caching, stays UNKNOWN with the full reservation and is never resent.

Checks: `tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py` (pure: omission, changed mode, extra members, breakpoint, field-list disagreement, runner policy check, post-binding mutation; Docker, under a separate grant: exact wire equality through pinned Hermes and the relay).

