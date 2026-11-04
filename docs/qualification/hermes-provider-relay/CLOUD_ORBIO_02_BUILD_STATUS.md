# CLOUD-ORBIO-02-BUILD status

- Task: build parts 2a (display) and 2b (per-call output limit) of the accepted CREDIT design `ORBIO_CREDIT_DESIGN.md` (reviewed PASS at `c62cc3f`). Builder-approved normal cloud session, 2026-11-04.
- Branch: `cloud/orbio-02-build`, created from `origin/integration/edge-os-mvp` (`39e4a06`), then merged with normal merge commits: `origin/cloud/orbio-01-route` (`4e30112`) -> `5738028`, then `origin/cloud/orbio-02-credit-design` (`f959dec`) -> `4be1a4f`. Both merges applied with no conflict. Only normal pushes to `cloud/orbio-02-build`; nothing pushed to main or integration; no force push; no PR.
- **Final candidate SHA: `7f76711db49634416a4b10b0c3ade57aaa3611a5`**. The commit that adds this status file comes after it and changes only this file.
- No key, `.env`, provider or Orbio call, spending, wallet or deploy. Network was used only for package and image installs (see "Environment").
- `min_output_tokens` is `None` by default and no registered release sets a value (open question 1 below). E1-COST1, the USD 2.00 caps, `operating_release.py` and every release file are unchanged. Part 2c (`max_cost`) is not built.

## Commits

| Commit | Content |
|---|---|
| `ed181b0` | 2b: `min_output_tokens` in both ledgers, `Reservation.max_output_tokens`, `reserved_output_tokens`, guarded runner, docker runner policy, relay grant/admission/service, composition pass-through, CONTRACT A9 |
| `4559887` | 2a: `spend_view`, CREDIT fields on `study_model_cost`, `model_budget` in `attempt_state` / `load_bundle` (through an injected `spend_view`), web display, `CONTEXT.md` CREDIT entry |
| `d6d4adf` | regenerated `docs/qualification/hermes-provider/IDENTITIES.json` (pinned support-file hashes) |
| `720f43b` | review round 1 fixes (see "Reviews") |
| `6422d51` | regenerated `IDENTITIES.json` again |
| `7f76711` | review round 2 fixes, including the regenerated `docs/qualification/hermes-job-support/JOB_IDENTITIES.json` (the BLOCKING finding) |

## What was built, and differences from the design

Every 2a/2b row is built as written except these, each stated in code, A9 or a commit message:

- `model_budget` reaches `attempt_state` through a `spend_view` callable injected into `create_app(..., spend_view=...)` and `HermesResearch`, wired in `scripts/hermes_app_mount/serve_relay_application.py`. Reason: `provider_spend_ledger` adds `scripts/` to the import path, and the application factory must not import it. Without an injected view the budget is `None` ("budget not set"). A ledger read that fails gives `{"unit": "CREDIT", "state": "UNKNOWN"}` (neither "not set" nor 0), and the saved result still loads. This is an addition to the design.
- `model_budget` adds `state: "SET"`. Its `available_credit` is shown as `max(0, available)` after an OVERRUN past the cap ("nothing can be reserved"). The web budget text also names the global ceiling, as section 2a asks: "available 1.8 of 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT; 0.17216 CREDIT held by 1 call of unknown cost".
- The web shows CREDIT on two new lines ("Model spend", "Model budget"). The existing USD "Total model cost" line is kept.
- `ActualRelease.body_refusal(..., granted_max_tokens=None)`: the granted limit is optional; without it the release's limit is required, as before.
- The relay service's own guard refuses a body off the granted limit (`guard:output_limit_not_as_configured`) before the record check. `body_max_tokens_mismatch` is shown directly in `test_relay_actual_release.py`, which is where `body_refusal` is tested; the design named `test_relay_admission.py`.
- Never resent after a restart with more headroom: SQLite has no `change_caps`, so the raised-cap case is a PostgreSQL ledger test (`test_a_started_call_reserved_with_a_lowered_limit_is_never_reserved_again_after_more_headroom`). The SQLite relay-runner test re-runs the same attempt with another limit choice. The relay-restart case is in `test_relay_service.py`.
- Additions:
  - `GuardedTurnRunner` releases and refuses a reservation whose returned output limit is unusable (nothing sent).
  - `RelayTurnRunner` also requires the turn's limit to be a whole number from 1 to the policy's.
  - The docker runner also refuses a limit below 1.
  - `bind_release` checks the definition's `min_output_tokens` with the ledgers' rule (`check_smallest_limit`).
- With `None`, the one visible addition is the result's `observed["granted_max_output_tokens"]`, which the design asks for (stated in A9).
- Some existing tests compared `model_cost`, the bundle or the launcher's `create_app` call with exact equality. They were updated for the additive fields. Two pinned-hash files were regenerated with their own scripts (`qualification_identities.py`, `job_identities.py`); only the hashes of `spend_ledger.py`, `guarded_turn_runner.py` and `guarded_docker_runner.py` changed.

## RED and GREEN evidence per test (design section 2d)

Commands ran from `apps/api` with `uv run --frozen pytest <files> -q -p no:cacheprovider` (root tests as `../../tests/...`), and for the web from `apps/web` with `npx vitest run tests/model-cost.test.tsx` under Node 24.22.2. "Root-only" means the 3 pre-existing chmod tests listed under "Pre-existing failures".

| Design row | Tests (file) | RED (before the change) | GREEN |
|---|---|---|---|
| Over budget refused before sending | `test_spend_ledger.py`: `test_a_call_whose_smallest_useful_limit_does_not_fit_is_refused_and_nothing_is_written`, `test_headroom_below_the_input_alone_refuses_the_call`, `test_a_smallest_limit_outside_one_to_the_full_limit_is_refused_and_nothing_is_written[*]` | 12 failed: `TypeError: SpendLedger.reserve() got an unexpected keyword argument 'min_output_tokens'` (and `Reservation` has no `max_output_tokens`) | file: 47 passed, 1 failed (root-only) |
| same | `test_provider_spend_ledger.py` (PostgreSQL): `test_a_call_over_budget_is_refused_before_anything_is_written`, `test_a_postgres_smallest_limit_outside_one_to_the_full_limit_is_refused[*]` | 19 failed. New tests: `TypeError: PostgresSpendLedger.reserve() got an unexpected keyword argument 'min_output_tokens'`. Existing tests failed mid-change (`Reservation.__init__() missing 1 required positional argument: 'max_output_tokens'`) because the shared type gained its field before this ledger filled it | 19 passed |
| same | `test_guarded_turn_runner.py`: `test_a_call_over_budget_is_refused_before_the_boundary_is_called`, `test_a_smallest_limit_outside_one_to_the_policy_limit_is_refused_when_the_runner_is_built[*]`, `test_the_incoming_turn_must_still_carry_the_full_limit` | 9 new failed: `TypeError: GuardedTurnRunner.__init__() got an unexpected keyword argument 'min_output_tokens'` (11 failed total, including 2 root-only) | 32 passed, 2 failed (root-only) |
| Limit lowered, not refused | `test_spend_ledger.py`: `test_a_smaller_output_limit_is_reserved_when_the_full_one_does_not_fit` (design example: 150,000,000 nano-USD -> 1,880 tokens, row column 1,880), `test_the_full_limit_is_kept_when_it_fits`, `test_racing_reservations_for_the_last_headroom_never_commit_more_than_the_cap` (8 threads: 4,096 / 4,096 / 2,448, rest refused, committed == cap) | in the 12 failed above (same TypeError) | in the 47 passed above |
| same | `test_provider_spend_ledger.py`: `test_the_owner_headroom_lowers_the_output_limit_inside_the_reservation` (3,449), `test_the_global_headroom_lowers_the_output_limit_when_it_is_the_smaller` (2,116), `test_two_processes_racing_for_the_last_headroom_with_lowered_limits_never_pass_the_cap` (two OS processes: 4,096 / 4,096 / 2,156, 3 refused, committed 0.149994 <= 0.15) | in the 19 failed above | 19 passed |
| same | `test_guarded_turn_runner.py::test_the_boundary_gets_the_lowered_limit_that_was_reserved` (720) | in the 9 failed above | passed |
| same | `test_guarded_docker_runner.py`: `test_the_job_guard_enforces_the_turns_own_lowered_output_limit`, `test_a_turn_outside_one_to_the_policy_limit_is_refused_before_any_launch[4097, 0, -1]` | 4 failed: the job policy carried 4,096 instead of 1,880; out-of-range turns launched (`UNKNOWN`/container exit instead of `RequestNotAdmitted`). The regression guard `test_a_turn_at_the_policy_limit_gives_the_job_exactly_the_policy` passed | file: 203 passed |
| Relay refuses a raised limit before any start | `test_relay_admission.py`: `test_a_grant_may_carry_a_lowered_output_limit[1, 1880]`, `test_a_grant_whose_output_limit_is_raised_or_not_a_whole_number_is_refused[*]`; `test_relay_actual_release.py`: `test_a_body_at_the_grants_lowered_limit_passes`, `test_a_body_whose_max_tokens_differs_from_the_granted_limit_is_refused[*]` | 9 failed: lowered grants refused `grant_release_mismatch` (equality); `4096.0` admitted; `body_refusal()` had no `granted_max_tokens` | admission + actual release + service + service actual: 136 passed |
| same | `test_relay_service_actual.py`: `test_a_request_at_its_grants_lowered_limit_is_sent_once`, `test_a_body_whose_limit_is_not_the_granted_one_is_refused_before_any_start[*]` (exact reasons, no `started.json`, no send) | the lowered send failed (`not enough values to unpack`: nothing was sent). The refusal cases already passed; they are guards | in the 136 passed |
| Never resent after a restart | `test_relay_service.py::test_a_restart_never_resends_a_started_request_with_a_lowered_limit` (host relay process killed and restarted: `unknown_restart`, then `already_started`, 1 provider receipt) | failed (`not ready in time`: the lowered grant was refused) | passed |
| same | `test_relay_turn_runner_actual.py::test_a_started_call_with_a_lowered_limit_is_never_resent_by_a_restarted_runner_with_another_limit_choice` | 9 failed in the file's new tests: `TypeError: build_relay_job() got an unexpected keyword argument 'min_output_tokens'` | 71 passed (with `test_relay_turn_runner.py`) |
| same | `test_provider_spend_ledger.py::test_a_started_call_reserved_with_a_lowered_limit_is_never_reserved_again_after_more_headroom` (`change_caps` raise -> `ReservationExists`, limit and events unchanged) | in the 19 failed above | 19 passed |
| Grant and job carry the limit; ledger-row check | `test_relay_turn_runner_actual.py`: `test_the_grant_and_the_job_carry_the_lowered_limit_and_an_equal_cost_still_settles`, `test_a_turn_whose_limit_is_not_the_one_reserved_gets_no_grant`, `test_without_a_smallest_limit_the_grant_carries_the_release_limit` | `TypeError` as above; `KeyError: 'granted_max_output_tokens'`; a mismatched turn got a grant (`('RETURNED', 1, None)`) | 71 passed |
| E1-COST1 unchanged | existing cost cases in `test_relay_turn_runner_actual.py` stayed green; new `test_with_a_lowered_limit_any_other_cost_keeps_the_lowered_reservation[0.0012, 0.02, 0.0074284, 0.0074285001, 0.06]` and the equal-cost case above | new cases: the `TypeError` above | 71 passed |
| Composition pass-through | `test_hermes_relay_composition.py`: `test_no_registered_release_sets_a_smallest_output_limit`, `test_a_definition_without_a_smallest_limit_composes_a_runner_that_never_lowers_the_limit`, `test_the_definitions_smallest_limit_reaches_the_guarded_runner`, `test_a_smallest_limit_outside_one_to_the_records_limit_is_refused_at_binding[*]` | 9 failed: `RelayApplicationDefinition` had no `min_output_tokens` | 107 passed |
| UNKNOWN never shown as zero (API) | `test_study_model_cost.py` (CREDIT fields, held lower bound, `SETTLEMENT_NOT_RECORDED`, a budget past its cap); `test_provider_spend_ledger.py` (`spend_view` None with no settings row and no write; held counted as used; smaller headroom); `test_hermes_transport_mount.py::test_the_saved_result_shows_the_owners_shared_budget_in_credit_with_held_liability_as_used`; `test_hermes_research_flow.py::test_an_application_with_no_spend_ledger_shows_no_budget_rather_than_a_zero_one` | collection errors: `ImportError: cannot import name 'model_budget'` / `'spend_view'`; the research-flow test failed (no `model_budget` key) | 136 passed (5 files) |
| UNKNOWN never shown as zero (web) | `apps/web/tests/model-cost.test.tsx`: CREDIT amounts, spend text, budget text, all-unknown renders "unknown" never "0 CREDIT", mixed renders "at least", missing budget renders "budget not set", request page passes the budget | 6 failed (`describeCredit is not a function`, no `model-credit` element), 6 passed | 12 passed; `tsc --noEmit` clean |

Review-round tests (written first, seen failing for the expected reason, then passing):
- `test_guarded_turn_runner.py::test_a_reservation_without_a_usable_output_limit_is_released_and_nothing_is_sent[*]`: 6 failed (the reservation stayed RESERVED), then passed.
- `test_hermes_research_flow.py::test_a_budget_that_cannot_be_read_is_unknown_and_the_saved_result_still_loads` and the `state` field: 3 failed (the create request failed, `KeyError: 'intake'`), then 5 passed.
- `model-cost.test.tsx`, global ceiling wording and `UNKNOWN` budget: 2 failed, then 12 passed.
- The case where the USD and CREDIT strings differ: 1 failed, then 12 passed.
- `test_relay_turn_runner_actual.py::test_a_turn_limit_above_the_policy_or_not_a_number_gets_no_grant_even_when_the_ledger_row_matches[True]`: failed (a bool was accepted), then passed.

Tests written after their code (coverage, not TDD):
- `test_hermes_research_flow.py::test_a_spend_view_without_the_hermes_interpreter_and_its_runner_is_refused`
- `test_provider_spend_ledger.py::test_a_call_over_the_global_headroom_is_refused_against_the_global_cap`
- `test_guarded_turn_runner.py::test_an_unusable_reservation_that_cannot_be_released_stays_liability_and_nothing_is_sent`
- the `[5000]` case of the relay-runner test above
- the `True` case of the docker-runner range test

The never-resent and E1-COST1 tests that existed before this task stayed green in every run below.

## Full test runs on the final candidate `7f76711`

| Command (from `apps/api` unless stated) | Result | Time |
|---|---|---|
| `uv run --frozen pytest tests -q -p no:cacheprovider` | 4578 passed, 1 failed, 1 skipped | 17 min 50 s |
| `uv run --frozen pytest ../../tests -q -p no:cacheprovider` (every root test folder) | 2546 passed, 8 failed, 17 skipped, 130 errors, 129 subtests passed | 4 min 18 s |
| `cd apps/web && npx vitest run` (Node 24.22.2) | 32 files, 385 passed | 30 s |
| `cd apps/web && npx tsc --noEmit` | exit 0 | |

Earlier full runs, for history:
- `4559887`: API 4576 passed, 1 failed (the same Privy test), 1 skipped.
- Scripts subset (`provider_safeguards` + `hermes_provider_relay`): 969 passed, 4 failed, 83 errors. The 4th failure was the stale `IDENTITIES.json`, fixed in `d6d4adf`.
- `720f43b`: scripts subset 976 passed, 4 failed, 83 errors. The 4th failure was `IDENTITIES.json` again, fixed in `6422d51`; web 385 passed.
- Baseline before any change (merged base, scripts subset): 913 passed, 3 failed, 83 errors.

### Pre-existing failures (all fail the same way on the merged base `4be1a4f`; none is in a file this task changed)
- `tests/hermes_interpretation/provider_safeguards/test_spend_ledger.py::test_an_interrupted_settlement_keeps_the_liability`, and in `test_guarded_turn_runner.py`: `test_a_ledger_that_cannot_record_stops_the_request_before_it_starts` and `test_an_interrupted_settlement_still_returns_the_result_and_keeps_the_liability`. These tests make a file read-only with `chmod`, and the container runs as root, which ignores it. A non-root rerun was not possible: the venv's Python lives under `/root`.
- `apps/api/tests/test_privy_wallet_lookup.py::test_ipc_malformed_or_oversized_frames_get_a_code_only[\x00\x00\x10\x01xxxxxxxxxxxxxxxx]`: `ConnectionResetError` in this environment. It fails 3 of 3 runs and also on the base.
- `tests/deployment_rehearsal/test_image_definitions.py`: `test_no_secret_or_runtime_configuration_is_baked_in[api]`, `[web]` and `test_web_image_takes_only_public_build_arguments_and_the_lock` (an `EDGE_OS_PROFILE` build argument the test does not expect). Also `tests/test_controller_guard.py::StopGuardTests::test_bind_update_cli_uses_codex_session_environment_and_keeps_identity` and `tests/test_forward_history_recorder.py::test_body_write_failure_stops_further_sends`. All 5 fail identically on `4be1a4f` (checked by running them on a detached checkout of the base).
- `tests/hermes_provider_relay/test_release_tls_name.py` (Lane 4's file, not edited): **3 of 3 passed** in every run here. `CA_MD_TOO_WEAK` did not occur in this environment.

## NOT RUN (errors, not passes)

130 tests error at fixture setup and are **NOT RUN**. The log shows two causes. Pytest prints a shared fixture's traceback only once, so the exact count per cause is not shown.
- The builder-only pinned Hermes checkout is missing (`/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent`, `git rev-parse HEAD` exit 128).
- No pinned-image receipt is set (`HERMES_APP_IMAGE_RECEIPT` for `test_relay_application_mount.py`, `HERMES_OPERATOR_IMAGE_RECEIPT` for `test_relay_operator.py`): "this test builds no image".

| Test file | Errors |
|---|---|
| `tests/hermes_interpretation/test_pinned_hermes.py` | 15 |
| `tests/hermes_interpretation/test_pinned_hermes_flows.py` | 11 |
| `tests/hermes_interpretation/test_pinned_hermes_http.py` | 6 |
| `tests/hermes_interpretation/provider_safeguards/test_manifest_through_pinned_hermes.py` | 11 |
| `tests/hermes_interpretation/provider_safeguards/test_pinned_hermes_guard.py` | 7 |
| `tests/hermes_job_support/test_transport_job_through_pinned_hermes.py` | 10 |
| `tests/hermes_app_mount/test_transport_mount_through_pinned_hermes.py` | 5 |
| `tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py` | 4 |
| `tests/hermes_provider_relay/test_relay_through_egress_gateway.py` | 32 |
| `tests/hermes_provider_relay/test_relay_through_pinned_hermes.py` | 26 |
| `tests/hermes_provider_relay/test_relay_application_mount.py` | 2 |
| `tests/hermes_provider_relay/test_relay_operator.py` | 1 |

The same set errors on the base. Every Docker test that needs only the Docker daemon and PostgreSQL ran. That includes all API PostgreSQL tests, the two-process ledger race and the docker-runner stub tests.

## Reviews

Each candidate was reviewed by two new independent reviewer subagents, a spec reviewer and a standards reviewer. A third and fourth reviewer were started fresh for the second round and then re-checked the later candidates.

| Round | Reviewer | Candidate | Verdict | Findings and disposition |
|---|---|---|---|---|
| 1 | Spec (new) | `4559887` | PASS | N1-N5 non-blocking: A9 does not mention `granted_max_output_tokens`; open question labelled Q3 instead of design Q2; the global ceiling missing from the budget text; a ledger read error breaks the page; mount docstrings omit `spend_view`. All fixed in `720f43b`. |
| 1 | Standards (new) | `4559887` | PASS | 7 non-blocking: unusable reservation left RESERVED; duplicated range check; weak service-test assertion; test name overclaims; budget error breaks the page; duplicated web logic and unchecked `held_calls`; test placement and gaps. All fixed in `720f43b`. |
| 2 | Standards (new) | `720f43b`, then `6422d51`, then **`7f76711`** | **PASS** at `7f76711` | Non-blocking: private helper imported by three modules; `_credit` shares a name with the Nansen helper; CREDIT spend text read two fields; untested error paths; formatting. Fixed in `7f76711`. Left by choice: the composition wiring tests check a private attribute (behaviour is proved end to end in `test_relay_turn_runner_actual.py`); "budget not set" before the ledger's first use. Last note at `7f76711`: one short reflowed docstring line (cosmetic, left). |
| 2 | Spec (new) | `6422d51` | REVISE | **BLOCKING F1**: `docs/qualification/hermes-job-support/JOB_IDENTITIES.json` still pinned the old hashes, so `tests/hermes_job_support/test_job_support_package.py` failed. Fixed in `7f76711`; the reviewer confirmed no other file pins a hash of a changed file. |
| 2 | Spec (same) | **`7f76711`** | **PASS** | Non-blocking, left: N1 the docker runner's limit check comes before its recovery pass (refusing earlier does nothing at all); N2 and N3 as stated in "What was built"; N5 `available` clamped to 0 after an OVERRUN; N6 the new plain "unknown" text when no attempt has a total has no direct test (it renders nothing with no attempts). |

**Both reviewers PASS the same candidate, `7f76711db49634416a4b10b0c3ade57aaa3611a5`.**

## Environment

- The Docker daemon was started in the container (`dockerd`). Docker Hub returned `429 Too Many Requests`, so `postgres:18.6-trixie` was pulled from `mirror.gcr.io/library/postgres:18.6-trixie` and tagged with the name the harness pins.
- Python 3.14 via `uv sync` in `apps/api`.
- The web app needs Node 24. The container has Node 22, whose npm refused the lock file, so Node 24.22.2 and npm 11 were installed as local packages in the session scratchpad. `npm ci --ignore-scripts` then succeeded against the unchanged lock file.
- The stopped run left two test PostgreSQL containers and their volumes; they were removed.

## Open questions for the builder

1. **The release value of `min_output_tokens`** (design Q2, item 3 of `CLOUD_ORBIO_02_DESIGN_STATUS.md`). The brief called it Q3. Below what output limit is a call not worth making for `hermes-first-call-1`? Setting it means adding `min_output_tokens=<n>` to its `RelayApplicationDefinition`, a reviewed change. Until then every call reserves and grants the full 4,096.
2. **Settlement decision** (design section 3): keep E1-COST1 (option A, unchanged here) or adopt option C after an approved paid observation. Part 2c waits for this and for Orbio's `max_cost` facts (design Q3-Q5).
3. **Per-study cap** (design Q1): the budget shown is the owner's shared cap, limited by the global ceiling. A per-study cap would be a new product limit.
4. **Wording before first use**: before the ledger's settings row exists, the page shows "budget not set" even though caps are configured. This follows the design ("not set, not 0"). Confirm the wording, or ask for the configured caps to be shown instead.
5. **Display after an OVERRUN**: `available` is shown as 0 after a charge passes the cap. Confirm, or show the overrun amount instead.
6. The environment failures listed under "Pre-existing failures" are not caused by this task and were not changed: the root-only chmod tests, the Privy IPC reset, the deployment image definitions, the controller guard and the forward-history recorder.
