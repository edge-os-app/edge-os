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
