# Nansen mount and replay compatibility: local evidence

Task `R58-RESEARCH-MOUNT-L2-20261014-LOCAL-v1`. Frozen rules: `CONTRACT.md` section 12, with its amendments in 12.7. Status: **LOCAL**. Local host, PostgreSQL, full-suite and browser verifier runs are recorded below; one internal review is still open. Every actual call is `NOT_RUN`; `APPROVED_RELEASES` and `RELEASE_DEFINITIONS` are empty. Stand-in keys and owned 127.0.0.1 servers only. Actual-history replay compatibility is local preparation, not a qualification of actual data.

## What changed

| Area | Files | Commit |
|---|---|---|
| Contract frozen before code | `CONTRACT.md` section 12 | `a9bc4bd` |
| Nansen client bounds in the release; network-factory rules | `core/research/operating_release.py` | `65d269b` |
| `NansenHttpFactory`, `ReleasedNansenTransport`, `PreparedNansen` | `core/research/released_source_runtime.py` | `65d269b` |
| One server composition for the API and the worker | `core/research/released_runtime_bootstrap.py`, `main.py`, `research/investigation_jobs.py` (`main`) | `65d269b` |
| Release Nansen job lifecycle: transport built with the credential read, saved-deadline anchor, labels, deadline state | `research/investigation_jobs.py` | `65d269b` |
| `PROVIDER_ACTUAL` replay admission, adapter consistency, notice | `replay/simulator.py`, `replay/history_inputs.py`, `replay/saved_runs.py` | `65d269b` |
| Replay test bound to the saved run's identities (test only) | `apps/api/tests/test_real_history_replay_inputs.py` | `9089cd8` |
| Verifier release phase with a Nansen part over a loopback Nansen stand-in | `scripts/p03/research_phase.py`, `tests/p03/research-release-{journey,report,restart}.spec.mjs`, `apps/api/tests/operating_release_stand_in.py` | `55a6314` |
| Upstream verifier selector repair (lease amendment) | `scripts/p03/runtime_phase.py`, `tests/p03/test_runtime_spec_selector.py` | `1028d55` |

## Recorded runs

All runs used the locked toolchain, synthetic stand-in credentials and owned loopback servers, under a host memory-pressure guard with one fixed deadline per window.

| Run | Candidate | Command or scope | Result |
|---|---|---|---|
| Host focused | `65d269b` | Nansen HTTP tests, release validation, spot replay, `test_nansen_runtime_mount.py` | 227 passed (194 before the change) |
| H1 focused PostgreSQL, first | `65d269b` | release research, real-history replay, investigation jobs, replay identity and API, research ports | 165 passed, 1 failed: the new replay test used another run-configuration ID than its saved descriptor |
| H1 repair | `9089cd8` | the replay test module, then the H1 set again | 11 passed; then 166 passed |
| H2 full API | `55a6314` | `uv run --frozen pytest` | 2234 passed |
| H2 verifier `r58mountl2h2` | `55a6314` | full verifier with browser | 99 PASS, 1 FAIL: the runtime phase's file filter also selected `agent-health-runtime.spec.mjs`; every Nansen and history release step passed |
| Selector regression | `1028d55` | `tests/p03/test_runtime_spec_selector.py` | failed on the old argument (both specs selected), then 2 passed |
| H3 Playwright `--list` | `1028d55` | old filter, new filter, P31 filter | 12, 6 and 6 tests |
| H3 verifier `r58mountl2h3` | `1028d55` | full verifier with browser | 100 PASS, 0 FAIL |
| Original review A, own runs | `1028d55` | focused set (including this note's tests and the selector regression), full API, verifier `r58l2reva1` | 339 passed; 2234 passed; 100 PASS, 0 FAIL |

The verifier runs saved, and checked against each stand-in's own request log: two browser Nansen reports per run (desktop and 390 px) with saved 600 s deadlines, loopback labels, 2 requests and 6 credits KNOWN; a killed Nansen worker ending `nansen_outcome_unknown` with 4 requests and 12 credits unknown and one attempt; a worker past the saved deadline and a missing key ending before any request with everything released; 5 Nansen and 55 history stand-in requests; byte-identical inspections after the API and worker restart; owner B denied; no stand-in key in any saved row, log or browser result.

## Fault matrix → tests

`host` = host test run; `H1` = focused PostgreSQL run; `H2` = full API run; `A` = review A's own focused and full runs; `V` = verifier runs (H3 and A).

| Case | Test (`apps/api/tests/` unless named) | Passed in |
|---|---|---|
| No runtime by default; no key read; no socket | `test_nansen_runtime_mount.py::test_the_default_server_composes_no_release…`, `test_operating_release_research.py::test_without_a_composed_release…`; verifier: the standard API composes no release | host, H1, H2, A, V |
| Unapproved or changed actual release; two releases; no credential source | `test_nansen_runtime_mount.py::test_only_an_exactly_approved_actual_definition…`, `…::test_the_bootstrap_refuses_before_any_read…` | host, H2, A |
| API and worker share one immutable runtime | `…::test_an_approved_definition_gives_one_immutable_runtime…`, `…::test_the_worker_process_uses_the_server_bootstrap`, `…::test_create_app_consults_the_server_bootstrap…` | host, H2, A |
| Actual Nansen needs the fixed origin and the network factory; stand-in never uses it | `…::test_an_actual_nansen_part_needs…`, `…::test_a_stand_in_nansen_part_never_uses…` | host, H2, A |
| Wrong release SHA, missing key | `test_operating_release_research.py::test_a_release_nansen_job_ends_before_any_request_without_its_release_or_credential`; verifier missing-key job | H1, H2, A, V |
| Malformed key: refused before the attempt | `test_nansen_runtime_mount.py::test_a_malformed_key_is_refused_before_any_request`, `test_operating_release_research.py::test_a_release_nansen_job_with_a_malformed_key…` | host, H1, H2, A |
| Saved deadline → one earlier monotonic anchor; connect bound | `test_nansen_runtime_mount.py::test_the_saved_deadline_maps_to_one_earlier_monotonic_anchor…` | host, H2, A |
| Delayed later call; late reply | `…::test_a_late_reply_is_incomplete_and_a_later_request_is_never_sent` | host, H2, A |
| Complete run over the accepted adapter; reopen without a call | `…::test_a_complete_run_crosses_the_accepted_adapter…`, `test_operating_release_research.py::test_a_loopback_release_nansen_report…reopens_without_a_call`; verifier browser reports and restart | host, H1, H2, A, V |
| 401, 402, 429, 302, unknown status, malformed, oversized, dropped reply | `test_nansen_runtime_mount.py::test_a_refused_first_reply_stops_the_run_once_without_retry[*]` | host, H2, A |
| Key echo | `…::test_a_reply_that_echoes_the_key_is_refused_without_a_hash` | host, H2, A |
| Deadline during a call; worker past the saved deadline | `…::test_the_job_deadline_stops_a_slow_call…`, `test_operating_release_research.py::test_a_release_nansen_call_past_the_saved_deadline…`; verifier late worker | host, H1, H2, A, V |
| Cancel during / after a call | `test_nansen_runtime_mount.py::test_a_cancel_during_a_call…`, `…::test_a_cancel_after_a_reply…`, `test_operating_release_research.py::test_a_cancel_during_a_release_nansen_call…` | host, H1, H2, A |
| Crash after the attempt; restart | `test_operating_release_research.py::test_a_worker_killed_during_a_release_nansen_call…`; verifier killed Nansen worker | H1, H2, A, V |
| Duplicate start, last slot | Release concurrency is tested for history jobs only (`test_operating_release_research.py::test_concurrent_starts_keep_one_original_job_per_key…`, `…::test_concurrent_starts_cannot_overspend_the_owner_cap`). For Nansen, a repeated key returns the original job on the authored path (`test_research_ports_journey.py::test_a_repeated_key_returns_the_original_job…`, sequential). `start_nansen_job` was not changed. A simultaneous start of release Nansen jobs is NOT tested. | H1, H2, A (for the tests named) |
| Provider history replays with equal numbers; no upgrade | `test_spot_replay.py::test_qualified_provider_history_replays…` | host, H2, A |
| Relabelled dataset cannot claim provider history; actual labels pass | `test_real_history_replay_inputs.py::test_a_dataset_cannot_claim_provider_history…`, `…::test_actual_provider_history_passes_through…` | H1 (after `9089cd8`), H2, A |
| Runtime phase selects only `runtime.spec.mjs` | `tests/p03/test_runtime_spec_selector.py` (run by path; outside the default `apps/api` test paths) | selector run, A |

## Retained limits

- No actual provider, key, account or payment was used. No actual release is defined or approved.
- The web Nansen panel's top label is a fixed "Authored … replayed" sentence even under a release; the saved notice and evidence class below it are correct. The web component is outside this lease and needs a follow-up before any actual Nansen release.
- `USER_RELEASE_INTEGRATION_PROFILE.md` (RG05 row) still says actual-source replay is blocked; that file is outside this lease.
- A race between the guard and the adapter's own pre-dispatch check counts an unsent request as sent: UNKNOWN, never zero.
- The DNS and initial-connect residual of `StdlibHttpTransport` is unchanged.
- During H3 and the review run, the host's default Docker bridge network got a new ID with the same address range; the cause is unknown and nothing was changed.
- No Hermes interface was prepared; the accepted online L1 contract does not exist yet.
