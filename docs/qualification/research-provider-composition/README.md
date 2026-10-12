# Research provider composition (RESEARCH-PORTS-LOCAL)

Status: **LOCAL application composition only.** Milestone `RELEASE-E2E-L2-20261012-RESEARCH-PORTS-LOCAL-v1`, issue #58. Every provider reply in this milestone is AUTHORED and served by an application-owned transport inside the API process. No network, credential, account, model, payment, wallet or provider was used. This note proves application wiring, not actual data, provider behavior, demo readiness or bounty readiness.

The frozen caller contract, settlement rules and fault matrix are in `docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md`, section "RESEARCH-PORTS-LOCAL". The separately approvable actual run is proposed in [ACTUAL_APPLICATION_COLLECTION_PACKET.md](ACTUAL_APPLICATION_COLLECTION_PACKET.md); nothing in it ran.

## What the application now composes

| Path | Accepted library code it calls | Application transport | Evidence class saved |
|---|---|---|---|
| History source `native-http-qualified/1` | P07 `HttpEnvioQueryClient` and `HttpQuickNodeRpcClient` (classes and `HttpTransport` protocol unchanged), `EnvioHypersyncSource`, collection, corroboration and qualification | `AuthoredHttpTransport` in `apps/api/src/edge_os_api/core/research/provider_composition.py`, answering the recorded native pages and JSON-RPC results at `.invalid` endpoints | `AUTHORED_HTTP_RESPONSE`, content label `SYNTHETIC_FIXTURE` |
| Nansen token report | `nansen_research.run_research` (request, evidence and report contracts `/1`, unchanged) | `AuthoredNansenTransport` over `apps/api/tests/fixtures/nansen_research_authored/nansen_authored_v1.json`, behind `GuardedNansenTransport` (cancel and deadline before every request) | `AUTHORED_FIXTURE` |

Both are selected only by explicit local settings (`EDGE_OS_RESEARCH_SOURCE_CLIENTS=authored_http`, `EDGE_OS_NANSEN_RESEARCH_MODE=authored_fixture`). Production settings refuse both. No setting, request body or header can supply an endpoint, a token or a transport. A saved job whose composition was later removed ends `UNAVAILABLE` before any client or transport exists.

## What a user can do locally

1. Declare an investigation on the HTTP-client source, start one keyed job, and reopen the saved dataset. The job view labels the client classes and says "Authored HTTP responses … no network. Not provider data".
2. Adopt that dataset's market into a new strategy draft and save a replay on it. The replay lineage keeps `AUTHORED_HTTP_RESPONSE` and "simulated fills".
3. On the same saved request, save one keyed Nansen token report (token, symbol, window, holders and/or flows, credit limit). After the worker runs, open the saved report: the exact request text as the question, findings with verdicts and source counts, what the report cannot answer, coverage (holder rows are address records, not people or amounts), unknowns and recomputed hashes. Reopening never calls the transport again.

## Accounting

- Owner and global quotas reserve `provider_requests`, `compute_seconds` and, for Nansen jobs only, `nansen_credits` before any effect. History jobs never create Nansen credit rows.
- HTTP usage is `MEASURED_CLIENT_CALLS` only when every client call completed; any client `unknown_liability` keeps the whole request reservation unknown.
- Nansen settlement counts the requests actually handed to the transport. A refusal before sending (the package's request, credit or deadline limit, or the job's cancel/deadline guard) is not a made call and leaves nothing unknown. Credits settle KNOWN only when nothing was lost and every reply reported a valid deducted-credit header; otherwise the whole credit reservation stays unknown liability (never zero). A lost reply keeps requests and credits unknown. A killed worker or a failed report save reconciles to `OUTCOME_UNKNOWN` and never runs again.
- Migration 0011 refuses to downgrade while any Nansen job or nonzero credit liability exists, so a rollback cannot erase a saved report or credit liability.

## Proof in this candidate

- API: `apps/api/tests/test_research_ports_journey.py` (fault matrix rows, adoption and replay, restart reopen, other owner, production refusal, worker-time refusal, forward observation).
- Web: `apps/web/tests/research-nansen-report.test.tsx`, `apps/web/tests/investigation-review.test.tsx`.
- Mapped verifier: `tests/p03/research-ports-journey.spec.mjs`, `research-ports-report.spec.mjs`, the ports test in `research-history-restart.spec.mjs`, and `inspect_ports` in `scripts/p03/research_phase.py` (direct SQL over `research_local.nansen_requests`, `nansen_reports`, `investigation_jobs.kind` and `usage_local` credit allocations, before and after a restart). Desktop 1280 and mobile 390 screenshots are named `*-rg-p1…p5-*.png`.

## Retained limits

- DNS and connect containment of the P07 HTTP clients stays as the P07 note records: **not exercised**, because the authored transport opens no socket. It is not waived by this mount.
- The authored HTTP responses are a copy of the SOURCE-LOCAL synthetic native recording. They do not show provider shapes beyond those recordings.
- The Nansen fixture uses the accepted package's authored shapes and credit headers. It shows no account, rights, real coverage or real cost.
- P27 forward observation is a type contract only (`research/forward_observation.py`); every current source returns `UNAVAILABLE` with its reason. No polling or scheduler exists.
- Nansen facts never enter a P07 dataset, a market adoption, a rule revision or a replay.
