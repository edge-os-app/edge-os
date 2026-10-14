# Operating-release research composition (contract)

Task `RESEARCH-RUNTIME-L2-20261013-LOCAL-v1` (#58). Status: **LOCAL. Written before code** on base `ff1d958c47f2891707b4aa9b5b06541eb5289633`. This note gives no authority. No actual request, credential, account, provider, model, payment or public operation runs in this milestone. Every actual item stays `NOT_RUN`.

The packet named `docs/qualification/research-ports/CONTRACT.md`. No file exists at that path in the worktree, the primary checkout or the workspace. The existing composition note is this folder's `README.md`; this contract sits beside it.

## 1. Sources

- Accepted composition: `core/research/provider_composition.py` (RESEARCH-PORTS-LOCAL) and its frozen profile section in `docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md`.
- Proposed actual values: `ACTUAL_APPLICATION_COLLECTION_PACKET.md` (this folder) and `docs/qualification/research-history-clients/ACTUAL_COLLECTION_PACKET.md` (P07). Every value they mark `REQUIRED_DECISION` stays a decision here.
- Accepted P07 library: `research_history` (collect, corroborate, normalize, HTTP clients, `StdlibHttpTransport`). Accepted Nansen package: `nansen_research` (`run_research`, `NansenTransport`). Neither changes.
- Accepted numerical replay: `replay/` (P13/P14). It accepts only `SYNTHETIC_FIXTURE` profile evidence. It does not change.

## 2. What this milestone adds

An **operating release** is one frozen, server-owned description of one bounded actual run. Without a composed release, nothing in this note is reachable. With a release, the application runs the existing journey unchanged in order:

owner request → saved declaration → original investigation job → owner and global reservation → release admission → credential read → provider clients → P07 qualification and provenance → saved dataset → P09 report → user-adopted rules and replay → reopen and restart.

Only **stand-in** releases execute in this milestone. Their transports are an in-process recording or an owned loopback HTTP server. An **actual** release is defined and admitted by the same code, but no actual release is approved, so it is refused before any credential or provider I/O.

## 3. Release definition (`edge-os.research-operating-release/1`)

New module `core/research/operating_release.py`. Frozen dataclasses, no I/O:

| Field | Meaning |
|---|---|
| `release_id` | Stable name, for example `stand-in-native-qualified/1` |
| `kind` | `STAND_IN` or `ACTUAL` |
| `history` | `HistoryRelease` or null |
| `nansen` | `NansenRelease` or null |

`HistoryRelease`:

| Field | Meaning |
|---|---|
| `source_id` | Catalog id of the release source |
| `envio_endpoint`, `envio_credential_slot` | Server-owned HyperSync base URL; `POST <endpoint>/query` with a bearer token read from the named slot |
| `quicknode_host`, `quicknode_credential_slot` | The slot holds the full QuickNode URL (its key is in the path). Its host must equal `quicknode_host` |
| `rpc_methods` | Exactly `eth_chainId`, `eth_getTransactionReceipt` |
| `source_version` | `envio-hypersync/1` |
| `profile` | The P07 market profile: network and chain id, pool, assets, decimals, units, orientation, window, availability, finality, event |
| `scan` | Block range |
| `corroboration_sample_size` | Receipt sample |
| `provider_facts` | Facts the release declares and P07 does not read; labelled `RELEASE_DECLARATION` |
| `limits` | Fixed `provider_requests`, `compute_seconds`, `max_pages`, `max_rows`, `max_bytes`, `deadline_seconds` |
| `client_bounds` | Fixed per-call `deadline_seconds`, `connect_timeout_seconds`, `max_response_bytes`, `max_request_bytes`, `max_blocks_per_page` |
| `time_basis` | `event_time = BLOCK_TIMESTAMP`; `collection_time = APPLICATION_CLOCK` |
| `required_coverage` | `COMPLETE_SCAN` |

`NansenRelease`: `endpoint`, `credential_slot`, `token_address`, `token_symbol`, `window`, `operations`, `holder_query`, `flow_query`, `limits` (`max_requests`, `max_pages`, `max_bytes`, `max_credits`, `per_page`), `deadline_seconds`, `compute_seconds`.

`release_sha256(release)` is the canonical SHA-256 of the whole definition. `APPROVED_RELEASES: Mapping[str, str]` maps an approved actual release id to its SHA-256. **It is empty in this candidate.** Adding an entry is a reviewed code change with a recorded builder approval. No setting, environment value, file, request body or header can add one.

Validation (`check_release`), before any credential or provider I/O:

- `STAND_IN`: every endpoint host is loopback (`127.0.0.1`, `::1`, `localhost`) or ends in `.invalid`. Refused in production.
- `ACTUAL`: every endpoint is `https` on a non-loopback host, and `APPROVED_RELEASES[release_id] == release_sha256(release)`. The history transport must be the accepted network `StdlibHttpTransport`. No accepted Nansen network transport exists, so an actual Nansen part is refused.
- History limits must cover the pages, one chain read and one receipt per sample; the page limit cannot exceed the request limit.
- Refusal codes: `operating_release_not_approved`, `operating_release_invalid`, `stand_in_endpoint_not_local`, `actual_release_needs_network_transport`, `actual_nansen_transport_missing`.

## 4. Runtime composition and the no-effect default

New module `core/research/released_source_runtime.py`:

```python
class CredentialSource(Protocol):
    def read(self, slot: str) -> str: ...        # raises CredentialUnavailable; no default source exists

@dataclass(frozen=True)
class ReleasedSourceRuntime:
    release: OperatingRelease
    credentials: CredentialSource
    http_transport: Callable[[], HttpTransport] | None      # one fresh transport per job
    nansen_transport: Callable[[NansenRelease, str], NansenTransport] | None

def open_released_runtime(settings, release, *, credentials, http_transport=None, nansen_transport=None) -> ReleasedSourceRuntime
```

`open_released_runtime` runs `check_release` and refuses a stand-in in production. It reads no credential and makes no request.

Composition seams (the only ways to enable a release):

- `create_app(settings, hermes_runner=None, research_runtime=None)`.
- `InvestigationWorker(..., research_runtime=None)`.

The default is no runtime. Then the release source is not listed, a release job start is refused `409 operating_release_unavailable` before any reservation, and a saved release job ends `UNAVAILABLE` at the worker before any credential read. No setting is added. A configured provider key in the environment changes nothing, because no code reads it. `create_app` refuses a runtime with a Nansen part while `nansen_research_mode = authored_fixture` (two Nansen paths would be ambiguous).

## 5. Evidence class comes from the composition, never from a request

| Release kind | Transport | Dataset/report `evidence_class` | Profile `evidence_class` (replay input) | `transport_kind` |
|---|---|---|---|---|
| `STAND_IN` | any in-process transport | `RELEASE_STAND_IN_RESPONSE` | `SYNTHETIC_FIXTURE` | `IN_PROCESS_RECORDING` |
| `STAND_IN` | `StdlibHttpTransport` to loopback | `RELEASE_STAND_IN_RESPONSE` | `SYNTHETIC_FIXTURE` | `LOOPBACK_HTTP` |
| `ACTUAL` (approved) | `StdlibHttpTransport` | `PROVIDER_ACTUAL` | `PROVIDER_ACTUAL` | `PROVIDER_HTTP` |
| `ACTUAL` | anything else | refused | — | — |

A declaration names the served class and the served profile hash. A different class is `422 history_source_class_mismatch`. `PROVIDER_ACTUAL` stays refused (`actual_data_not_authorized`) unless the served source is an approved actual release, which cannot happen in this candidate. The content label of a stand-in dataset stays `SYNTHETIC_FIXTURE`. Its notice says stand-in responses, not provider, chain or market evidence.

An actual dataset would carry profile evidence `PROVIDER_ACTUAL`. The unchanged P13 runtime refuses it with `EVIDENCE_CLASS_UNSUPPORTED`. A replay on such a dataset is therefore saved as an explicit unsupported result, not run.

## 6. Declaration, job and worker rules

Declaration (history): the release source must be served now. Profile hash, market and window must equal it. `resource_bounds` must equal the release `limits` exactly (`422 release_bounds_mismatch`). The user's own rules follow the existing checks. `frozen` adds `operating_release_id` and `operating_release_sha256`. Other sources keep their frozen content byte for byte.

Job start: refused before any reservation when no runtime is composed (`409 operating_release_unavailable`) or when the composed release SHA-256 differs from the frozen one (`409 operating_release_changed`). Then the existing owner-plus-global reservation reserves the release limits. A refusal saves `BUDGET_EXHAUSTED` with nothing reserved. The same key returns the original job; a concurrent start on the same key serializes behind the quota locks.

Worker, in this order, for a `RESERVED` release job:

1. Cancel or deadline: the existing release of everything, no credential read.
2. No runtime → `UNAVAILABLE operating_release_unavailable`. Changed SHA-256 → `UNAVAILABLE operating_release_changed`. Everything released; no credential read.
3. Read credentials. Missing → `UNAVAILABLE operating_release_credential_unavailable`. A QuickNode URL on another host → `UNAVAILABLE operating_release_endpoint_mismatch`. Everything released; no request.
4. Save `ATTEMPT_STARTED` with the release SHA-256, evidence class and transport kind, and commit.
5. Collect through the accepted P07 HTTP clients over the composed transport, wrapped by a hashing transport that keeps each request and reply body SHA-256 and status. The existing request guard checks cancel, deadline and the request budget before every call. Per-call `deadline_seconds` is the smaller of the release client bound and the seconds left before the job deadline.
6. Save the dataset with the additive keys below; settle as today.

Existing rules are unchanged: a killed worker reconciles `OUTCOME_UNKNOWN` and never collects again; a lost reply keeps the whole request reservation unknown; a provider error is `PARTIAL PROVIDER_ERROR` with no retry and no provider text; a cancel or deadline between calls stops before the next call.

Dataset additive keys (release sources only): `operating_release {release_id, sha256, kind}`, `transport_kind`, `transport.request_sha256[]`, `transport.response_sha256[]`, `transport.response_status[]`, `transport.endpoint_hosts`, `application_collection_time {started_at, finished_at, basis: APPLICATION_CLOCK}`, `release_coverage {required, met}`. The P07 query, query hash, window, event times, coverage, gaps, buckets, verdicts and hashes are saved as today. No credential, authorization header, full QuickNode URL or provider text is saved.

Nansen: with a runtime Nansen part, a new report request must equal the release request exactly (token, symbol, window, operations, queries, limits, deadline, compute), else `422 release_request_mismatch`. The saved request adds `operating_release`. The worker repeats steps 1–4 before `run_research`; the report keeps the composed evidence class, transport label and notice. Credit settlement is unchanged.

## 7. Fault matrix (request → effect → timeout/crash → stop → evidence → cleanup → accounting → restart)

| Case | Provider effect | Stop | Evidence | Accounting | Restart |
|---|---|---|---|---|---|
| No runtime composed | none | start 409 / worker UNAVAILABLE | job event `SOURCE_REFUSED` | nothing reserved / all released | no repeat |
| Unapproved actual release | none; no credential read | runtime open refused | refusal code | nothing | — |
| Release changed after declaration | none | start 409 / worker UNAVAILABLE | frozen vs served SHA-256 | released | no repeat |
| Missing credential | none | worker UNAVAILABLE | `operating_release_credential_unavailable` | released | no repeat |
| Budget exhausted | none | `BUDGET_EXHAUSTED` | refused amounts | nothing reserved | — |
| Duplicate start (same key, concurrent) | one job | — | one job, one reservation | one reservation | — |
| Two owners | none for the other owner | 404 | — | per owner | — |
| Happy path | measured calls | REPORTED | dataset, report, hashes | consumed = measured calls | reopen calls nothing |
| Provider error page | one call | PARTIAL `PROVIDER_ERROR` | stable code, no provider text | made calls consumed | — |
| Lost reply | call made | P07 partial | client unknown liability | whole request reservation unknown | — |
| Cancel between calls | calls so far | CANCELLED | partial dataset | made calls consumed, rest released | — |
| Deadline | per-call bound ≤ job time left; next call refused | DEADLINE_EXCEEDED | partial dataset | made calls consumed | — |
| Worker killed after `ATTEMPT_STARTED` | calls already made | UNAVAILABLE `collection_outcome_unknown` | `ATTEMPT_RECONCILED OUTCOME_UNKNOWN` | whole reservation unknown | never collected again; stand-in request count unchanged |
| Sampled corroboration (P07 proposed sample) | measured calls | REPORTED | verdict `LIMITED`, `UNAVAILABLE_LIMITED_DATA`, report `LIMITED_DATA` | measured | — |
| Receipt mismatch | measured calls | REPORTED | mismatch kept, not QUALIFIED | measured | — |
| Restart (API and worker) | none | — | same rows, same hashes | unchanged | reopen in a new context |

## 8. Proof plan

- API: new `apps/api/tests/test_operating_release_research.py` over the session PostgreSQL, through the public routes and the worker, with an in-process recording transport and a loopback stand-in provider that counts requests outside the application. Test support in `apps/api/tests/operating_release_stand_in.py`.
- Web: research-only component tests for the release labels.
- Verifier: an isolated release phase in `scripts/p03/research_phase.py` that runs its own API and worker with a stand-in runtime and a loopback stand-in provider, drives new specs `research-release-journey.spec.mjs` and `research-release-restart.spec.mjs`, inspects SQL directly, compares saved request counts with the stand-in provider's own log, restarts and reopens, and restores the standard API. The default run stays non-spending.

## 9. Required decisions kept open (actual packet)

Owner and global caps for the actual run; orientation; window; availability model; the P07 profile's `collected_at_utc` representation for an actual run; credential delivery (host secret store or file outside the repository); the Nansen network transport; account plans, rights and retention. RG02 and RG05 actual-data evidence stays open until an approved application collection qualifies. A `LIMITED` dataset stays `LIMITED`.

## 10. Amendments recorded during implementation (2026-10-13)

- **Cancel during a call.** The accepted HTTP client checks cancellation again after a reply arrives. A cancel seen then makes that call incomplete (`unknown_liability` 1), so the whole request reservation stays unknown liability and nothing is consumed. The next call is still refused before it is made. The section 7 row "Cancel between calls" therefore settles as UNKNOWN when the cancel lands during a call; this is the accepted library rule (RESEARCH-PORTS-LOCAL retained limits), conservative and never zero. Test: `test_a_cancel_after_the_first_page_stops_before_the_next_request`.
- **Listing shape.** `GET …/nansen-reports` adds `operating_release` only when a release Nansen part is composed, so the response without a release is unchanged. `GET /v1/research/history-sources` always carries `operating_release` (null without a release).
- **Verifier.** The release phase runs after the Stage 2 runtime phase, uses per-job worker processes over its own jobs only, and starts the standard API again at its end.

## 11. Review repair 1 (original pair round 1, controller packet dw-l2-repair1.md)

Both original reviewers returned REVISE on dd1c09f. Each change below closes one recorded finding; the frozen rules above are unchanged and nothing is relaxed.

- **Per-call deadline (A F1 / B B3, blocking).** The bound was computed once at collection start, so a later call could outlive the job deadline by up to one client bound. Now `HashingTransport` bounds every physical request by the original job deadline: it refuses to send after the deadline, passes `min(call deadline, job deadline)` to the inner transport, and treats a reply that arrives after the deadline as incomplete (`SourceTimeout`), so its possible effect stays unknown liability. Section 6 step 5 and the section 7 Deadline row now hold for every call. Tests: `test_every_later_call_is_bounded_by_the_time_the_job_has_left`, `test_a_call_after_the_job_deadline_is_refused_before_it_is_sent` (host) and `test_each_later_call_is_bounded_by_the_time_the_job_has_left` (worker, DB).
- **Release kind (B B1 / A F2, blocking).** `check_release` refuses any kind other than `STAND_IN` or `ACTUAL` (`operating_release_invalid`) before any other check, so a mistyped kind can no longer skip host rules, the approval registry or the production refusal.
- **Runtime trust (B B2).** `ReleasedSourceRuntime` validates itself on construction: the composed parts must exist, the transport class must match `network_transport`, and `release_sha256` must equal the release's own digest. A runtime cannot be built around the validator.
- **Malformed QuickNode URL (B B4).** `prepare_history` applies the accepted client's endpoint rules (no userinfo, no fragment, plaintext http only on loopback) before the attempt is saved; a failure ends the job UNAVAILABLE `operating_release_endpoint_mismatch` with everything released and no request.
- **Credential-source errors (B B6).** Any exception from the credential source becomes `operating_release_credential_unavailable` without its detail, so the job ends at the first read instead of staying RESERVED and reading again each pass.
- **Hash alignment (B B7).** After a request without a reply, `response_sha256` records None at the same index as the None status.
- **Source id collision (B B5).** `history_dataset.check_release_source` refuses a release whose history `source_id` names a recorded source; `create_app` (ConfigError) and `InvestigationWorker` call it at composition.
- **Verifier cleanup isolation (A F3).** `verify_run.comparable_names` keeps this run's own resources whatever other label they carry, skips another test run's and another lane's labelled rehearsal resources, and keeps unlabelled resources. Host test: `test_the_cleanup_comparison_hides_only_other_runs_labelled_resources`.
- **Not changed (B B8 judgement calls).** The predicate and refusal-block duplication smells and the `Any` runtime parameters are left as they are: removing them would be a broader refactor than the findings require.
- **Deadline test oracle (heavy window v2, dw-l2-oracle1.md).** `test_each_later_call_is_bounded_by_the_time_the_job_has_left` first asserted dataset `status == "PARTIAL"` and failed on 74fbf1b (137 passed, 1 failed): `status` is the P07 page-collection status, and both pages finish before the deadline. The test now checks the deadline's actual effects in the saved record: request hashes equal the requests the stand-in received (refused requests are never sent), corroboration `missingness.rpc_failed >= 1`, QuickNode `http_accounting.unknown_liability >= 1`, `provider_requests_state == "UNKNOWN"` with `provider_requests` null, and the whole 27-request reservation held as unknown with none consumed. Every per-call bound assertion is kept. Test-only change; no product code changed.
- **Saved-deadline anchoring (controller dw-l2-clock3.md; review B R2-N2, judged blocking by the controller).** The worker measured the time left once at `started_at` and the clients added that stale duration to the monotonic clock when they were built later, so a setup delay extended the absolute bound (reproduced on dcdb39a: saved deadline 101.0, transport deadline 101.25, a reply at 101.1 accepted). Now `investigation_jobs.release_http_clients` reads the time left from the job's SAVED deadline at client construction, taking the monotonic anchor first so the anchored deadline can only be earlier, never later; `PreparedHistory.clients` accepts that anchor. Same sequence after the fix: transport deadline 101.0 and the late reply refused (`SourceTimeout`, unknown liability). No tolerance is added.
- **Production stand-in refusal at the worker (controller dw-l2-clock3.md; review A N1).** `InvestigationWorker` now refuses a STAND_IN runtime when `settings.env == "production"` (`stand_in_refused_in_production`), the same rule `open_released_runtime` and `create_app` already apply (section 3), before any credential read, request or reservation.

## 12. Successor: Nansen mount, server bootstrap and actual-history replay compatibility (frozen before code)

Task `R58-RESEARCH-MOUNT-L2-20261014-LOCAL-v1` (#58 Task 6 successor). Base `98d89c5f41d48ce5f76051606e5fba0b767a9f3d`, which contains the accepted composition above and the accepted Nansen HTTP adapter `3cc8630` (`docs/qualification/nansen-http-transport/CONTRACT.md`). This section records how the code implements invariants that are already accepted. It is not a new builder approval. Every actual call stays `NOT_RUN`. `APPROVED_RELEASES` stays empty. The Nansen HTTP source, its tests and its contract are read only here.

### 12.1 Release definition

- `NansenRelease` adds `client_bounds`: exactly `connect_timeout_seconds`, `max_request_bytes`, `max_response_bytes`, positive whole numbers, with `max_response_bytes ≤ limits.max_bytes`. Every per-call bound is then inside the release SHA-256. Refusal: `operating_release_invalid`.
- An `ACTUAL` Nansen part must name `https://api.nansen.ai` (the adapter's fixed origin); another origin is refused `operating_release_invalid` while the release is validated, before the approval check. It also needs its exact SHA-256 in `APPROVED_RELEASES` (else `operating_release_not_approved`) and the accepted Nansen network factory (below); without that factory it stays refused with the retained code `actual_nansen_transport_missing`. (Corrected in 12.7; the code and tests did not change.)
- A `STAND_IN` Nansen part composed with the network factory is refused (`stand_in_endpoint_not_local`): a stand-in can never reach the real origin.

### 12.2 Nansen network factory and runtime

`released_source_runtime.NansenHttpFactory` builds one accepted `NansenHttpTransport` per job over `StdlibHttpTransport`. Its optional `connect` is a test connector. Only the factory without a connector is the network factory (`nansen_network`). A loopback proof injects a connector, so it is never `nansen_network` and can never label a report `PROVIDER_ACTUAL`. The runtime records `nansen_network` and validates it on construction, as it already does for history.

Every composed Nansen transport, stand-in or network, is wrapped by `ReleasedNansenTransport`. It refuses to dispatch at or after the job's anchored deadline, treats a reply that returns at or after it as incomplete (`NansenTimeout TIMEOUT`), and keeps the SHA-256 of each accepted reply only. A refused reply (redirect, oversize, credential echo, malformed) gets no hash, as the adapter contract requires.

### 12.3 Deadline, cancellation and accounting mapping

| Item | Rule (source) |
|---|---|
| Deadline source | The job's SAVED `deadline_at` only (start time + declared `deadline_seconds`). |
| Monotonic anchor | Read the monotonic clock first, then the wall clock: `D = anchor + (deadline_at − wall)`. The anchor is taken when the transport is built, so `D` is never later than the saved deadline (section 11, saved-deadline anchoring). |
| Construction time | With the credential read, after admission and before `ATTEMPT_STARTED`. A malformed key is refused there (`operating_release_credential_unavailable`), so nothing is sent and everything is released. |
| Every request | One `D` for the whole job, never reset. `NansenHttpTransport` refuses dispatch at `D`; `StdlibHttpTransport` arms its watchdog for `D − now`; the guard refuses the next request after cancel, the saved wall deadline or `D`. |
| Connect timeout | `min(client_bounds.connect_timeout_seconds, seconds left at construction)`, at least 1 ms; `StdlibHttpTransport` then uses `min(timeout, D − now)` per connect. It never exceeds the remaining original deadline. |
| Byte caps | Request body ≤ `max_request_bytes` (adapter); each reply ≤ `max_response_bytes` (streaming cap and adapter); all replies ≤ `limits.max_bytes` (`NansenClient`). |
| Reservations | Owner and global reservation at start and `NansenClient` request/credit reservations are unchanged. |
| Cancel before credential read | The existing `RESERVED` check: no read, no request, everything released. |
| Cancel during a call | `SourceCancelled` → `NansenCancelled`: the call was handed over without a reply, so requests and credits stay UNKNOWN (whole reservation unknown liability). |
| Cancel after a reply | The reply is kept; the next request is refused before it is sent and is not counted. |
| Late reply (at or after `D`) | Incomplete: requests and credits UNKNOWN. |
| Missing reply (reset, DNS, refused) | `NETWORK_ERROR`, run stops, no retry, UNKNOWN. |
| Auth / payment / rate / redirect / unknown reply | The adapter and `NansenClient` map it once to a stable code; no retry. A refusal that keeps a received status is a made call (request count KNOWN); one without a status is UNKNOWN. Credits are KNOWN only when every made call reported a valid deducted charge (`nansen_reports.settlement`). |
| Crash after `ATTEMPT_STARTED` | Existing reconciliation: `OUTCOME_UNKNOWN`, never run again, all UNKNOWN. |
| Duplicate start, last slot | Existing quota locks: one job, one reservation. |
| Terminal state | Stop `DEADLINE`, or stop `TIMEOUT` when the saved deadline has passed, ends `DEADLINE_EXCEEDED`; stop `CANCELLED` ends `CANCELLED`. |

A race between the guard and the adapter's own pre-dispatch check counts a request that never left as sent. That is UNKNOWN, never zero (conservative).

### 12.4 Server bootstrap

New module `core/research/released_runtime_bootstrap.py`. `server_research_runtime(settings, *, credentials=None)` is the one composition the API (`create_app`, when no runtime is passed) and the worker (`investigation_jobs.main`) both call. It reads the code-owned `RELEASE_DEFINITIONS` (empty) and keeps only definitions whose exact SHA-256 is in `APPROVED_RELEASES` (empty). With none, it returns no runtime: no release, no credential read, no socket. With one, it composes the history part over `StdlibHttpTransport` and the Nansen part over the network factory. A missing credential source refuses startup; credential delivery stays `REQUIRED_DECISION`. More than one approved definition is refused. Both processes then hold the same immutable runtime and the same release SHA-256, and the existing admission check refuses a job whose frozen SHA-256 differs before any effect.

### 12.5 Actual-history replay compatibility (RG05)

- The P13 runtime admits profile evidence `SYNTHETIC_FIXTURE` (unchanged) and `PROVIDER_ACTUAL`. Every other class stays `EVIDENCE_CLASS_UNSUPPORTED`. Its other admission rules are unchanged: overall `QUALIFIED`, proven coverage, exact market binding, UTC five-minute window, timing and availability. The class is in the repeatability identity already, so equal buckets give equal numbers and a different identity.
- The adapter passes `PROVIDER_ACTUAL` only from a hash-verified owner dataset whose source class is also `PROVIDER_ACTUAL` and whose saved release kind is `ACTUAL`. Any other dataset that claims it is refused `409 evidence_class_inconsistent` before a replay is saved.
- Preserved: source class and profile hash, revision, market binding, timing and availability, gaps, coverage and verdict, protected partitions, provenance, Decimal arithmetic, P12 literal results and the `simulated fills` label. A provider-history replay states hypothetical simulated fills and claims no statistical support, profitability or trading permission. A `LIMITED` dataset stays refused (`DATASET_COVERAGE_UNPROVEN`).
- Not changed: P14/P42, numerical methods, source fetching, protected-data reads, P09 comparison.

### 12.6 Not in this candidate

Hermes mount (waits for the accepted online L1 contract and its own lease; no interface prepared). A test that starts release Nansen jobs simultaneously (see 12.7). Any actual key, provider, account, payment or public operation, and any actual release definition or approval. The verifier journey and the local PostgreSQL, full-suite and browser runs are now part of this candidate; `MOUNT_SUCCESSOR_EVIDENCE.md` records them.

### 12.7 Amendments recorded during implementation and review (2026-10-14)

- **Replay test binding (`9089cd8`, test only).** The first H1 PostgreSQL run on `65d269b` had 165 passed and 1 failed: `test_actual_provider_history_passes_through_with_unchanged_numbers` built its run with another run-configuration ID than its saved descriptor, so the unchanged runtime refused it at the identity check before the evidence class mattered. The test now reuses the saved run's identities and window. No assertion was removed; the H1 set then passed (166).
- **Verifier journey (`55a6314`).** The verifier's release phase now also composes a Nansen part served by a loopback Nansen stand-in through the accepted `NansenHttpTransport` and a test connector, with browser reports, a killed worker, a worker past the saved deadline, a missing key, SQL checks against the stand-in's own log, restart and reopen. The release processes turn the authored Nansen mode off; the standard API keeps it.
- **Upstream selector repair (`1028d55`, lease amendment for `scripts/p03/runtime_phase.py` and one `tests/p03` regression).** The H2 verifier on `55a6314` ended 99 PASS, 1 FAIL: the runtime phase passed the file filter `runtime.spec.mjs`, which Playwright reads as a case-insensitive regular expression over the whole path, so it also selected `agent-health-runtime.spec.mjs`, whose tests need their own runner. The phase now passes `(^|/)runtime\.spec\.mjs$`. `tests/p03/test_runtime_spec_selector.py` drives the real phase and failed on the old argument before the repair. Playwright `--list` then gave 12 tests for the old filter, 6 for the new one and 6 for the P31 filter, and the H3 verifier passed 100 of 100.
- **Refusal codes (12.1).** The frozen text said a wrong ACTUAL Nansen origin is refused `actual_nansen_transport_missing`. The code and its test refuse it `operating_release_invalid`; `actual_nansen_transport_missing` is the code for an approved ACTUAL part without the network factory. 12.1 now states the code's behavior. Both refuse before any credential read.
- **Duplicate start, last slot (12.3).** The rule is unchanged: `start_nansen_job` was not modified and keeps the quota locks, the key re-check and the integrity fallback. The release concurrency tests start history jobs; Nansen has a sequential repeated-key test on the authored path. A simultaneous start of release Nansen jobs is not tested.
