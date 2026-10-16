# Hermes provider relay: online continuation contract (proposed, frozen for the next lane-1 stage)

Task `HERMES-RELAY-L1-20261013-LOCAL-v1` (#58/P05), stage A2. Status: PROPOSED IMPLEMENTATION CONTRACT. It is not a live release and gives no authority: no credential, provider request, account, spending, deployment or host change. Online code starts only after the controller's exact START. Section 5 names one choice that needs a builder decision before that START.

Inputs: `CONTRACT.md` (A1-A4), `PROBE_A_PROVIDER_REUSE.md`, `.scratch/hermes-prototype-to-application-20261014/REVIEW.md`, the adopted host-held relay decision, and accepted `docs/qualification/hermes-job-support`, `hermes-provider` and `hermes-app-mount` documents. Current Docker and OpenRouter documentation was read through Context7 on 2026-10-14 (`/docker/docs`, `/openrouterteam/docs`). Documentation is not provider proof.

## 1. What stays the same

The online relay is the LOCAL relay with a real destination. Nothing below weakens a LOCAL rule.

- The Hermes job stays keyless, `--network none`, under the accepted `GuardedDockerTurnRunner` (deadline D, sealing, recovery C). Its one request leaves only as a channel file.
- Grants: one host-signed grant per attempt, bound to owner, saved request, run, attempt, route, release, policy and logical request (`relay_admission`). No grant without a recorded reservation and a proved owner (`RelayTurnRunner`, `relay_application_mount.subject_for`).
- Relay records: exclusive `started.json` before the send, then `finished.json` and `closed.json`; never a second request for one attempt; restart recovery marks `unknown_restart` and never resends.
- Settlement: only a closed-not-started record releases. A counted result needs a 2xx status and usage equal to the job's. Everything else stays UNKNOWN with the full reservation in `PostgresSpendLedger`.
- `send_once`: one connection, one total deadline (the grant expiry), no retry, no redirect, no streaming, no connection reuse, reply bound `max_reply_bytes + 1`.

## 2. Mapping to the application runner

| Piece | Today (LOCAL, exact files) | Online change (owner) |
|---|---|---|
| Release | `relay_admission.RelayRelease`, `RELEASE_KINDS = ("AUTHORED",)` | Add kind `ACTUAL`, constructible only from a frozen release record file whose SHA256 the relay and host both check (lane 1) |
| Destination | `ProviderDestination("localhost", 8443, "/v1/chat/completions")` from `relay_supervisor` | Fixed `openrouter.ai`, 443, `/api/v1/chat/completions` from the release record; never from the job or settings (lane 1) |
| Transport | `relay_transport.send_once` to the destination by TCP | `send_once` reaches the destination only through the egress gateway of section 5; TLS end to end, verified for `openrouter.ai` against a frozen CA bundle file named by hash in the release (lane 1) |
| Relay process | `relay_service.Relay`, AUTHORED only | Serves the one ACTUAL release it was started with; refuses any grant of another release (lane 1) |
| Supervisor | `relay_supervisor.RelaySupervisor`, AUTHORED only | `RelaySupervisor` gains the gateway container and the ACTUAL key-file mount; still LOCAL host process with explicit `start/stop` (lane 1) |
| Job side | `relay_job_channel.ChannelTransport`, `relay_turn_job` | Unchanged (lane 1) |
| Host runner | `relay_turn_runner.build_relay_job`, `RelayTurnRunner`; refuses non-AUTHORED routes | Accepts an ACTUAL route only with an ACTUAL release whose record hash matches (lane 1) |
| App composition | `relay_application_mount.open_relay_mount` (lane 1, additive), `hermes_transport_mount.py` refuses ACTUAL (lane 2) | Settings, startup, mount enablement, the owner/attempt identity mapping into the saved Research path: lane 2's separately scoped successor. Lane 1 exposes the accepted relay interfaces and does not edit `apps/**` |

Tests stay in `tests/hermes_provider_relay/`; docs in this folder. New owned files: `scripts/hermes_provider_relay/egress_gateway.py` (section 5) and its tests.

## 3. Release identity (frozen record, one per qualification)

A release record is a frozen JSON file outside the repository, hashed into every grant through `release_id`. Fields:

- `release_id`, `route_id`, `kind: ACTUAL`, approval packet path and SHA256.
- Destination: `https://openrouter.ai:443/api/v1/chat/completions`; CA bundle file SHA256.
- Model: exact id (Probe A used `openai/gpt-6.1-sol`; the application's model is set by the later qualification packet).
- Routing object, compared byte-equal after canonical JSON: `provider = {only: [<one slug>], allow_fallbacks: false, require_parameters: true, data_collection: "deny", max_price: {prompt, completion}}`. `data_collection: "deny"` is proposed; the qualification packet confirms it.
- `max_tokens` (Probe A: 4096), reasoning object, `response_format` schema SHA256, `stream: false`.
- Allowed body fields: `model`, `messages`, `stream`, `response_format`, `provider`, `reasoning`, `max_tokens`, `session_id`. Pinned Hermes adds `session_id`; OpenRouter documents it as sticky routing; the relay already binds it to `p05-<attempt>`.
- Bounds: `max_request_bytes` (Probe A requests about 34 KB: proposed 65,536), `max_reply_bytes` (Probe A decoded replies up to about 17 KB: proposed 262,144), `timeout_seconds` (Probe A calls 24-38 s; proposed 90 = grant life = D budget).
- Price snapshot SHA256 and the reservation formula: (request bytes + 2,048) × highest prompt/cache rate + `max_tokens` × completion rate, as in Probe A.

The relay refuses before any start record if the admitted body differs from the release on any of these, using the accepted guard plus an exact routing/schema check.

## 4. Reply, usage and unknown charge

- No `Accept-Encoding` is sent. A reply with any `content-encoding` is refused as a counted request (liability held), never decoded on trust.
- The counted path needs: 2xx, `application/json`, one choice, `finish_reason` `stop`, the release's model, usage with integer token counts and a numeric `cost`. `finish_reason` `length` is refused (Probe A truncation rule).
- Settlement amount: the provider-reported `usage.cost`, if it is at or under the reservation. A missing or larger cost keeps UNKNOWN with the full reservation.
- The relay records the response `id` (generation id). Reconciling an UNKNOWN charge by `GET /api/v1/generation?id=` is a separate host-held operation that needs its own approval; it is not part of the relay.

## 5. Provider-only network: one proposal, needs a builder decision

URL validation alone is not enforcement. The relay must have no path except the one to the provider.

Proposal E1 (smallest that keeps the A4 isolation):

- Relay: unchanged A4 shape, `--network none` (own namespace, loopback only). No AUTHORED provider sidecar in the ACTUAL release.
- Egress gateway: a new authored standard-library container (`egress_gateway.py`) with no key. It listens ONLY on a Unix socket in a private folder bind-mounted into the relay and the gateway (the folder holds only that socket). It is on one dedicated ordinary bridge network with no published port.
- Gateway rules: accept `CONNECT openrouter.ai:443` only; refuse any other name, any IP literal, any other port, and a second CONNECT on a connection. It resolves the name itself and refuses loopback, private, link-local, multicast and Docker-range answers. One tunnel per relay connection, closed at the grant expiry. TLS stays end to end; the gateway sees only ciphertext.
- Independent destination evidence: the gateway appends an fsynced receipt per tunnel (time, attempt from the relay's tunnel header, resolved address, bytes each way, close reason). Relay start records, gateway receipts and provider generation ids are three separate counts.
- Hardening for both: read-only root, `--cap-drop=ALL`, no-new-privileges, memory/CPU/PID limits, non-root user, no Docker socket, no host network.
- Deployment layer (a later packet, not this lane): a host firewall rule that lets the gateway's bridge reach only DNS and TCP 443. On Docker Desktop this layer does not exist; LOCAL proof covers the relay and gateway rules only.

Why a decision is needed: E1 adds a service (the gateway), a new bridge network for it, and a Unix-socket bind mount between two containers. The adopted rule requires a builder decision for a changed service topology or a host socket before implementation. No new capability is added.

Rejected options:

- Relay on an `--internal` network with the gateway as its only peer: R5-B1 showed that the Docker host answers on that network's gateway address.
- A firewall inside the relay namespace: needs `NET_ADMIN` in the key holder.
- A destination IP allowlist alone: OpenRouter is served from shared, changing addresses; the name check with end-to-end TLS is stronger.

## 6. Failure, supervision, recovery and cleanup

| Fault | Requests | Outcome |
|---|---|---|
| Gateway down or socket missing before CONNECT | 0 leave the relay, but a start record exists | `lost`, UNKNOWN held (conservative; a zero-effect release would need the gateway receipt log proving no tunnel, which is a later refinement) |
| Gateway refuses the CONNECT | 0 | `lost`, UNKNOWN held, gateway refusal receipt |
| DNS answer private/loopback | 0 | gateway refusal, UNKNOWN held |
| TLS name or CA mismatch | 0 bodies sent | `ReplyLost`, UNKNOWN held |
| Provider 3xx, 4xx, 5xx, encoded, oversized, truncated reply | 1 | refused reply, UNKNOWN held |
| Relay killed after start | 0 or 1 | `unknown_restart`, never resent |
| Host killed mid-turn | 0 or 1 | accepted recovery C; reservation stays |

Supervisor authority: a LOCAL host process only. It reads the key from a host-held file (mode 0400, outside the repository, never an environment variable) and mounts it read-only into the relay only. It starts the gateway, then the relay, by exact name and label, waits for both heartbeats, and removes exactly what it started. A gateway restart never changes relay records. Cleanup is checked by label as in the LOCAL suite.

## 7. Independent LOCAL test plan for E1 (no real provider)

- An AUTHORED TLS stand-in for `openrouter.ai` on the gateway's bridge, reached through a test-only resolver override that the ACTUAL release refuses. The stand-in uses a test CA; the ACTUAL release refuses that CA.
- Positive: one admitted attempt gives exactly one relay start, one gateway tunnel receipt and one stand-in receipt, with the relay's bearer.
- Negative, before any byte: CONNECT to another name, an IP literal, port 80, a second CONNECT, a name resolving to a private address; the relay's namespace has `lo` only and no route (A4 kernel view and controlled probes reused); the gateway holds no key (leak scan); the job holds no key and no network.
- Faults: gateway killed before and during a tunnel; hung stand-in cut at the grant expiry; relay killed after start; duplicate channel request; encoded and redirect replies.
- Counts: relay records, gateway receipts and stand-in receipts agree for every attempt; spend matches section 4.
- Cleanup: every labelled container, network and socket folder removed.

Online qualification itself (one real request through the application within the recorded USD 2 combined model/data ceiling, current price and routing proof, save and reopen) belongs to a later exact packet.
