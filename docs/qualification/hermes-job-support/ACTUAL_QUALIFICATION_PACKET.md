# Actual-provider qualification packet for the Hermes transport job

Status: PROPOSED. Label: NOT_RUN. This packet is not authority, not a budget and not a model choice. It makes no live request, reads no credential and spends nothing. It describes what a later, separately approved run must do. Every value marked PENDING is the builder's or controller's decision. Every value marked STALE must be read again on the day of the run.

It extends `docs/qualification/hermes-provider/QUALIFICATION_PROPOSAL.md` and `LIVE_RELEASE_CHECKLIST.md`. Those stay in force; this packet adds what the transport seam changes. Where they disagree, the older accepted file wins until a recorded decision changes it.

## 1. What a run would qualify, and what it would not

| Claim | Would this run show it? |
|---|---|
| An actual provider accepts the exact admitted request and returns a reply the bounds allow | Yes, for the cases run |
| Reported usage and the provider's own cost match the local settlement | Yes, for the cases run, if the provider reports them |
| The transport sends one request per attempt, no retry, no redirect, no stream | Only with an independent HTTP request count or the provider's own request records (section 6). Otherwise UNPROVED: the claim rests on the guard only |
| A real model keeps the user's meaning | Only through the accepted proposal's manifest and meaning check, as a separate result |
| Production hosting, supervision, storage and egress | No. Separate production qualification |
| Provider billing stops at a local cap | No. Only a provider-side limit can do that (section 5) |

## 2. Proposed identities (all PENDING)

| Item | Proposal | Source and status |
|---|---|---|
| Candidate | The commit that holds the reviewed ACTUAL transport (section 3). Not this commit | Not written |
| Base for this packet | `c9a6ac83dbb686dd744ca093c05f6932639df54c`; job files in `JOB_IDENTITIES.json` | This task |
| Hermes | commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba`, `uv.lock` SHA-256 `de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01` | Fixed |
| Provider and endpoint | OpenRouter, `https://openrouter.ai/api/v1/chat/completions` as `TransportRoute(kind="ACTUAL")` | Accepted proposal section 3: PENDING |
| Model | `openai/gpt-6.1-sol` | Accepted proposal: PENDING. No model is selected here |
| Routing fields | `provider.allow_fallbacks=false`, `require_parameters=true`, `data_collection="deny"`, `max_price` | Accepted proposal: PENDING. They need `GuardPolicy.required_extra` values and a guard check |
| Output limit | `max_tokens` 4,096 including reasoning | Accepted proposal: PENDING |
| Request bytes | first 8,448, follow-up 10,240 | Accepted proposal |
| Reply bound | `max_reply_bytes` PENDING; must be measured on authored replies of the chosen shape first. 65,536 is the local test value only | Not decided |
| Job timeout and grace | proposal asks 60 s job, 5 s grace; recovery budget C 5 s | Accepted proposal: PENDING |

## 3. Code that must exist before any request

None of this exists. Each item is a separate reviewed change.

1. An ACTUAL `ProviderTransport`: one HTTPS POST to the route endpoint, TLS verified, no redirect, no retry, no streaming, no connection reuse across attempts; a total timeout no larger than the turn's remaining job time; reads at most `max_reply_bytes + 1` bytes; raises `TransportLost` on any error after the request may have left. It must live where the network is, not in a no-network container. Where the transport runs (in the job with provider-only egress, or in a host-side relay that the job reaches without a socket to the host) is an open design decision.
2. `build_transport_job` accepting an ACTUAL route only together with a recorded release identity, still refused by default. No fixture flag.
3. The guard policy carrying the routing fields above as `required_extra`, with tests.
4. The spend ledger on durable shared storage with the same reserve, settle, release and reconcile rules (accepted hosting assessment).
5. A recorded decision path that resolves an UNKNOWN reservation without late evidence (accepted proposal 9a).
6. A release that does not trust the job alone. Locally, a reservation is released when the job reports zero requests and the guard's own count is 0; both are written inside the Hermes process. For an ACTUAL route, a release must also need independent evidence that nothing reached the provider: zero connections to the provider host at the egress control during that attempt's own window (from its reservation to its settlement, with no other attempt running on the run's key), or the provider's own records showing no request for that attempt (section 6).

## 4. Secure credential handoff (PENDING)

- A dedicated provider key for this run only, with a provider-side credit limit set by a person (section 5). No shared or personal key.
- The key reaches the host as a file only (never an argument, environment variable of the API process, log line or prompt). The accepted runner reads it once per turn and mounts a private read-only copy for the transport only. Hermes' client keeps the placeholder key.
- The key value never enters a task packet, review, evidence file, saved attempt or ledger. Sealing and the leak scan check evidence after every attempt.
- Rollback: revoke or zero the key, turn the live setting off, keep the ledger.
- Who creates, stores, injects and revokes the key: PENDING (accepted checklist line 6).

## 5. Money: units, ceilings, reservations, unknown liability

- Units: the ledger stores integer nano-USD (10^-9 USD) and exact decimal token prices. No float.
- Prices: STALE. The accepted proposal's prompt USD 2.00 and completion USD 7.50 per million tokens are Probe A's old ceilings. Read the provider's public price list on the run day, record URL and date, and recompute.
- Reservation per attempt: `(max_request_bytes + 64) x prompt price + max_tokens x completion price`, held before the request. With stale prices: USD 0.047744 (first reading), USD 0.051328 (follow-up). Reasoning tokens count as completion tokens.
- Cumulative cap, retry slots, per-run allowance: PENDING (accepted proposal proposes USD 0.75, not decided).
- Provider-side ceiling: OpenRouter documents a per-key credit limit; a key at its limit fails with 403 before reaching a provider (Context7 `/openrouterteam/docs`, checked 2026-10-12). Without such a limit, close the run as UNRESOLVED or record an explicit acceptance of local accounting only.
- Unknown liability: a lost reply, an oversized reply, a crash, missing usage, a timeout or an identity mismatch keeps the full reservation as UNKNOWN and blocks the scope. OpenRouter documents that a non-streaming request is not cancelled by a client disconnect and is billed for the complete response (Context7, checked 2026-10-12). So a kill must never release a reservation.
- Reconciliation: after the run, compare each attempt with the provider's own record (usage `cost`, generation record) through a read-only account view that a person opens. Record it with `SpendLedger.reconcile`, never by editing rows. A disagreement keeps the higher charge until a person decides.

## 6. Request, response and control cases

Run in this order. L1-L4 are a local preflight: they need no network and must give their expected outcome on the release candidate before any network case. N1-N3 are the only network cases.

| Case | What | Expected |
|---|---|---|
| L1 | Physical refusal (wrong client URL in the job settings), authored transport | Nothing sent; reservation released |
| L2 | Guard refusal (policy output limit 2,048), authored transport | Nothing sent; released |
| L3 | ACTUAL route with no release identity | `ActualProviderUnavailable` before anything is built |
| L4 | Authored lost reply, oversized reply, crash and hang | UNKNOWN, full reservation, nothing published |
| N1 | One manifest case (`g1-concrete`) | Exactly one HTTP request for the attempt by the independent request count or the provider's records; with neither, the one-request claim is labelled UNPROVED and network stop 4 (connections) still applies; exact settle from reported usage; reply within bound; identities equal the attempt |
| N2 | The remaining manifest cases, one request each, only after N1 passes with its request count proved (independent HTTP count or provider records) and a person reviews it. With N1's count UNPROVED, N2 does not run unless the builder records an acceptance of guard-only counting for N2 | As N1, plus the accepted meaning check reported separately |
| N3 | A provider error case, only if the provider offers a safe way to cause one, under the same proved-count condition as N2. It runs last | Exactly one HTTP request (no retry) by the independent request count or the provider's records; with neither (N3 then runs only under the recorded guard-only acceptance), the one-request claim is labelled UNPROVED and network stop 4 (connections) still applies; UNKNOWN, full reservation. This expected provider error and unknown usage meet the accepted stop rules for a provider error and for unknown usage, so the batch ends after N3 by design; N3 passes only when nothing else in the stop list below occurred |

Two separate controls, both independent of the job:

- **Request count.** One TCP or TLS connection can carry more than one HTTP request, and a packet counter cannot see requests inside HTTPS. So the one-request claim needs either an HTTP-level count by a component that sees each request (for example a host-side relay or a proxy that terminates TLS for this run only), or the provider's own per-request records (generation or request identifiers) for the run's key, read by a person. With neither, the run labels the one-request claim UNPROVED and keeps the guard-only limit.
- **Egress evidence.** An egress proxy or packet counter (accepted hosting assessment section 4) records connections and destinations: connections only to the provider host and none elsewhere. This is egress evidence, not a request count. Zero connections to the provider host does show that nothing reached it.

## 7. Deadlines, egress, storage, supervision, recovery

- D: one per turn, from the admitted settings, never renewed. The transport timeout comes out of the remaining job time.
- C: one budget per recovery pass. Recovery never changes the ledger.
- Egress: provider host only, TCP 443. The accepted hosting assessment found no documented host-name filter on the checked platform; this is UNRESOLVED and blocks N1.
- Storage: evidence folder private, per run; quarantine purged between turns; retention bound PENDING.
- Supervisor: who calls `recover_pending` on the host, how often, and who handles exhausted records: PENDING.
- Restart: a crashed host's pending record must be recovered before new work, and its reservation reconciled by a person.

## 8. Stop conditions

**Local preflight (L1-L4).** Each case passes when it gives exactly its expected outcome in section 6: L1-L3 send zero requests, and L4's lost, oversized, crash and hang cases end UNKNOWN with the full reservation and nothing published. These refusals and lost replies are the expected results there, not stop events. The preflight stops, and no network case starts, on any unexpected local outcome: a request reaching the authored transport in L1 or L2, anything built in L3, a released reservation or published text in L4, a credential form in evidence, or a leftover container.

**Network cases (N1-N3).** The accepted proposal's frozen stop rules apply (section 8 there). Add:

1. any transport refusal of a reply (`reply_too_large`, `reply_not_a_json_object`, `reply_status_invalid`);
2. any `TransportLost` or `TransportIdentityMismatch`;
3. a request count for an attempt, by the independent HTTP count or by the provider's records, other than the expected one per attempt (whichever source shows it first), or a connection to any host other than the provider;
4. other than exactly one provider connection for an attempt that sent a request, or any provider connection for an attempt that sent none (a possible hidden retry or stray request, even when the request count is UNPROVED);
5. any credential form found in evidence by sealing or the leak scan;
6. a provider 403 for a key limit (the ceiling worked: stop and report).

Stop the whole batch, send nothing more, report to the controller.

## 9. Evidence to keep

Per attempt: the attempt rows, the ledger events, the guard and transport evidence (hashes, sizes, header names only), the wire body hash and size, the reply status and size, reported usage and the provider's cost field, the independent request count (or the provider's request records, or the UNPROVED label), the egress connection and destination record, the container lifecycle, D and C timings, and any overrun with its measured value. Keep real-provider evidence in its own private folder and label, separate from authored runs.

## 10. Decisions required from the builder

1. Provider, endpoint, model, routing fields, reasoning level.
2. Where the ACTUAL transport runs and how it gets provider-only egress.
3. The key, its provider-side limit, and who handles it.
4. Prices read on the run day; cumulative cap; retry slots; per-run allowance.
5. Reply bound, timeouts, recovery budget and supervisor.
6. Whether the run is a separate ticket with its own reviews (recommended by the accepted proposal).
7. Only if N1's request count stays UNPROVED: whether to accept guard-only counting for N2 and N3, recorded before either runs (section 6).

## 11. Missing or unknown

- Current prices and model availability: not read.
- Whether `max_price` rejects or reroutes in every case: not established.
- Provider behavior on a lost connection beyond the documented non-streaming billing: not tested.
- Exact reply sizes of the chosen model: not measured.
- Provider-only egress on any host: not established.
