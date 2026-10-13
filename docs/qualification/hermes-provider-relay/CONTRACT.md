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
