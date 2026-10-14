# Nansen mount and replay compatibility: local evidence

Task `R58-RESEARCH-MOUNT-L2-20261014-LOCAL-v1`. Frozen rules: `CONTRACT.md` section 12. Status: **LOCAL, initial stage**. Every actual call is `NOT_RUN`; `APPROVED_RELEASES` and `RELEASE_DEFINITIONS` are empty. Stand-in keys and an owned 127.0.0.1 server only.

## What changed

| Area | Files |
|---|---|
| Nansen client bounds in the release; network-factory rules | `core/research/operating_release.py` |
| `NansenHttpFactory`, `ReleasedNansenTransport`, `PreparedNansen` | `core/research/released_source_runtime.py` |
| One server composition for the API and the worker | `core/research/released_runtime_bootstrap.py`, `main.py`, `research/investigation_jobs.py` (`main`) |
| Release Nansen job lifecycle: transport built with the credential read, saved-deadline anchor, labels, deadline state | `research/investigation_jobs.py` |
| `PROVIDER_ACTUAL` replay admission, adapter consistency, notice | `replay/simulator.py`, `replay/history_inputs.py`, `replay/saved_runs.py` |

## Fault matrix → tests

| Case | Test (`apps/api/tests/`) | Run |
|---|---|---|
| No runtime by default; no key read; no socket | `test_nansen_runtime_mount.py::test_the_default_server_composes_no_release…`, `test_operating_release_research.py::test_without_a_composed_release…` | host PASS; DB pending |
| Unapproved or changed actual release; two releases; no credential source | `…::test_only_an_exactly_approved_actual_definition…`, `…::test_the_bootstrap_refuses_before_any_read…` | host PASS |
| API and worker share one immutable runtime | `…::test_an_approved_definition_gives_one_immutable_runtime…`, `…::test_the_worker_process_uses_the_server_bootstrap`, `…::test_create_app_consults_the_server_bootstrap…` | host PASS |
| Actual Nansen needs the network factory and fixed origin; stand-in never uses it | `…::test_an_actual_nansen_part_needs…`, `…::test_a_stand_in_nansen_part_never_uses…` | host PASS |
| Wrong release SHA, missing key | existing `test_a_release_nansen_job_ends_before_any_request_without_its_release_or_credential` | DB pending |
| Malformed key: refused before the attempt | `…::test_a_malformed_key_is_refused_before_any_request`, `test_operating_release_research.py::test_a_release_nansen_job_with_a_malformed_key…` | host PASS; DB pending |
| Saved deadline → one earlier monotonic anchor; connect bound | `…::test_the_saved_deadline_maps_to_one_earlier_monotonic_anchor…` | host PASS |
| Delayed later call; late reply | `…::test_a_late_reply_is_incomplete_and_a_later_request_is_never_sent` | host PASS |
| Complete run over the accepted adapter | `…::test_a_complete_run_crosses_the_accepted_adapter…`, `test_operating_release_research.py::test_a_loopback_release_nansen_report…reopens_without_a_call` | host PASS; DB pending |
| 401, 402, 429, 302, unknown status, malformed, oversized, dropped reply | `…::test_a_refused_first_reply_stops_the_run_once_without_retry[*]` | host PASS |
| Key echo | `…::test_a_reply_that_echoes_the_key_is_refused_without_a_hash` | host PASS |
| Deadline during a call | `…::test_the_job_deadline_stops_a_slow_call…`, `test_operating_release_research.py::test_a_release_nansen_call_past_the_saved_deadline…` | host PASS; DB pending |
| Cancel during / after a call | `…::test_a_cancel_during_a_call…`, `…::test_a_cancel_after_a_reply…`, `test_operating_release_research.py::test_a_cancel_during_a_release_nansen_call…` | host PASS; DB pending |
| Crash after the attempt; restart | `test_operating_release_research.py::test_a_worker_killed_during_a_release_nansen_call…` | DB pending |
| Duplicate start, last slot | existing concurrency tests in `test_operating_release_research.py` | DB pending |
| Provider history replays with equal numbers; no upgrade | `test_spot_replay.py::test_qualified_provider_history_replays…` | host PASS |
| Relabelled dataset cannot claim provider history; actual labels pass | `test_real_history_replay_inputs.py::test_a_dataset_cannot_claim_provider_history…`, `…::test_actual_provider_history_passes_through…` | DB pending |

## Retained limits

- No PostgreSQL, Docker, browser, full suite or verifier run in this stage; they wait for a recorded capacity grant.
- The verifier's release phase now also composes a Nansen part over the loopback Nansen stand-in (`scripts/p03/research_phase.py`, `research-release-*.spec.mjs`): one browser report per width, a killed worker, a worker past the saved deadline and a missing key, with SQL, restart and reopen checks against the stand-in's own request log. The web Nansen panel's top label is a fixed "Authored … replayed" sentence even under a release; the saved notice and evidence class below it are correct. The web component is outside this lease.
- A race between the guard and the adapter's own pre-dispatch check counts an unsent request as sent: UNKNOWN, never zero.
- The DNS and initial-connect residual of `StdlibHttpTransport` is unchanged.
- No Hermes interface was prepared; the accepted online L1 contract does not exist yet.
