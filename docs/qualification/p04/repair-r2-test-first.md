# P04 repair R2 test-first record

These tests were added on the clean R2 repair start before any implementation edits. They target the original independent findings: outgoing-message receipts that ignore additional content and cancellation inspection failure that skips process reap and durable recovery.

## Outgoing context RED

Command:

```text
python3 -B -m unittest -v tests.p04.test_native_runner.ProviderBoundaryRegressionTests
```

Observed before implementation:

```text
test_boolean_output_limit_is_not_accepted_as_a_numeric_token_ceiling ... ok
test_cleared_memory_and_empty_sources_are_recorded_at_the_provider_boundary ... ok
test_forbidden_context_in_additional_outgoing_json_message_is_recorded_as_present ... ERROR
test_forbidden_context_in_structured_text_parts_is_detected_without_id_prefix_false_positive ... FAIL
test_forbidden_source_and_file_ids_use_exact_context_not_substrings ... ok
test_same_sized_second_request_is_rejected_before_fake_provider_work ... ok
test_truncation_fixture_returns_length_termination_instead_of_a_valid_outcome ... ok

======================================================================
ERROR: test_forbidden_context_in_additional_outgoing_json_message_is_recorded_as_present
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/p04/test_native_runner.py", line 292, in test_forbidden_context_in_additional_outgoing_json_message_is_recorded_as_present
    self.assertFalse(receipt["forbidden_owner_absent"])
                     ~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^
KeyError: 'forbidden_owner_absent'

======================================================================
FAIL: test_forbidden_context_in_structured_text_parts_is_detected_without_id_prefix_false_positive
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/p04/test_native_runner.py", line 330, in test_forbidden_context_in_structured_text_parts_is_detected_without_id_prefix_false_positive
    self.assertFalse(receipt["forbidden_memory_absent"])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

----------------------------------------------------------------------
Ran 7 tests in 0.003s

FAILED (failures=1, errors=1)
```

The first test reached the existing receipt and found no owner/agent evidence fields. The structured-content test demonstrated the false absence flag for an actual forbidden free-text value. The existing exact source-prefix case remained green.

## Cancellation RED

Command:

```text
python3 -B -m unittest -v tests.p04.test_native_runner.CancellationLifecycleRegressionTests.test_inspection_failure_reaps_runner_and_recovers_reserved_attempt_as_unknown
```

Observed before implementation:

```text
test_inspection_failure_reaps_runner_and_recovers_reserved_attempt_as_unknown ... FAIL

======================================================================
FAIL: test_inspection_failure_reaps_runner_and_recovers_reserved_attempt_as_unknown
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/p04/test_native_runner.py", line 218, in test_inspection_failure_reaps_runner_and_recovers_reserved_attempt_as_unknown
    self.assertTrue(process.killed, "the Docker runner process was not reaped after inspection failed")
    ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: False is not true : the Docker runner process was not reaped after inspection failed

----------------------------------------------------------------------
Ran 1 test in 0.007s

FAILED (failures=1)
```

The inspection exception escaped the actual cancellation function before its process or SQLite recovery path. The injected Docker failure created no Docker resource and made no provider request.

## Focused GREEN

Command:

```text
python3 -B -m unittest -v tests.p04.test_native_runner.ProviderBoundaryRegressionTests tests.p04.test_native_runner.CancellationLifecycleRegressionTests tests.p04.test_native_runner.NormalProcessLifecycleRegressionTests
```

Observed after the scoped implementation:

```text
test_boolean_output_limit_is_not_accepted_as_a_numeric_token_ceiling ... ok
test_cleared_memory_and_empty_sources_are_recorded_at_the_provider_boundary ... ok
test_forbidden_context_in_additional_outgoing_json_message_is_recorded_as_present ... ok
test_forbidden_context_in_structured_text_parts_is_detected_without_id_prefix_false_positive ... ok
test_forbidden_source_and_file_ids_use_exact_context_not_substrings ... ok
test_same_sized_second_request_is_rejected_before_fake_provider_work ... ok
test_truncation_fixture_returns_length_termination_instead_of_a_valid_outcome ... ok
test_inspection_failure_reaps_runner_and_recovers_reserved_attempt_as_unknown ... ok
test_kill_and_process_wait_failures_remain_unknown_and_recover_without_replay ... ok
test_marker_timeout_kills_verified_container_and_recovers_attempt ... ok
test_wrong_owner_label_and_malformed_inspection_never_kill_a_container ... ok
test_normal_job_timeout_does_not_kill_unverified_container_and_reaps_docker_client ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.558s

OK
```

The fault matrix injected inspection daemon failure, wrong container name, wrong run label, invalid inspection JSON, missing startup marker, Docker kill timeout, and local runner wait/kill failure. Each cancellation fault kept or recovered the attempt as interrupted/unknown, retained its $2.00 reservation, and did not replay. Unverified ownership never issued a Docker kill. Verified ownership issued the exact-name kill and absence verification. The normal-job timeout now shares those ownership and client-reap checks. All Docker/process faults were mocks; no container resource or provider request was created by this matrix.

## First actual-Hermes rerun and correction

Command:

```text
python3 -B docs/qualification/p04/native_runner.py --evidence-root docs/qualification/p04/evidence
```

The pinned Hermes image built and the labelled local recipe entered normal job 1. The provider request was rejected by the new owner/agent guard because the probe incorrectly marked the same `owner-a` shared by two agents as forbidden. No live provider call occurred. The runner retained `run-failure.json` at `docs/qualification/p04/evidence/p04-1e63fad68e85/` with `stage=normal_job_1_owner-a_agent-a`, `error_class=AssertionError`, and `real_inference_requests=0`. Its unique image cleanup recorded `verified_absent`; a label-filtered Docker check found no remaining containers for `p04-1e63fad68e85`.

Before changing the probe selection, `ProviderBoundaryRegressionTests.test_disjoint_identity_controls_exclude_shared_owner_but_keep_other_agent` failed with `ImportError: cannot import name '_forbidden_identity_values'`. This named the missing behavior, not a test setup error. After adding the scoped selector, that test passed. The actual rerun below is the canonical evidence for the corrected version.

The next actual run reached and terminated the correctly owned cancellation container. Docker then returned `error: no such object: p04-p04-38fb1f8d3c0e-cancel` after `--rm` removed it. The case-sensitive absence matcher classified this verified exact-name absence as unknown. `run-failure.json` retained `stage=cancellation_and_recovery`; `cancellation-lifecycle.json` retained `kill_exit_code=0`, `attempt_recovered_interrupted_unknown=true`, and `container_cleanup_status=unknown_pending_verification`. A label-filtered container check was empty and the unique image was verified absent.

Before the case-insensitive fix, the focused regression failed:

```text
python3 -B -m unittest -v tests.p04.test_native_runner.CancellationLifecycleRegressionTests.test_docker_no_such_object_error_is_verified_absence_case_insensitively

FAIL: expected result["status"] == "absent"; got "unknown"
Ran 1 test
FAILED (failures=1)
```

After changing only the Docker absence comparison to case-insensitive matching, the same command passed:

```text
test_docker_no_such_object_error_is_verified_absence_case_insensitively ... ok
Ran 1 test in 0.000s
OK
```

The next resource-lifecycle regression checked that a Docker client is reaped even when its exact container is already absent. Before the fix, the focused command reported `AssertionError: 'pending' != 'reaped'` for `process_cleanup_status`. After adding bounded client reaping to the verified-absence branch, the same command passed (`Ran 1 test in 0.000s; OK`). This case is distinct from container absence: both outcomes are now recorded separately.

An intermediate corrected actual recipe completed successfully as `p04-4b377eaace67`. A final regression then found that the cleanup helper did not reap the Docker client when inspection already showed the container absent. That code path was fixed test-first and the full actual recipe was rerun on the final code below; use that result as the replacement candidate's canonical runtime evidence.

```text
python3 -B docs/qualification/p04/native_runner.py --evidence-root docs/qualification/p04/evidence
P04 local qualification evidence: docs/qualification/p04/evidence/p04-7a05daed09f1
```


## Coordinator preflight: JSON-escaped memory regression

The coordinator's preflight on committed candidate `8b19633ff480fbf770d2778b13cd8a555c2052cd` supplied a valid extra JSON message whose `\u006f` escape decodes to the forbidden memory fixture `other memory`. The original memory branch returned after scanning serialized text, so the receipt incorrectly kept `forbidden_memory_absent=true`. This is a coordinator preflight finding, not a reviewer or gate verdict. The candidate and the earlier evidence remain unchanged in Git history.

Before changing `container_probe.py`, I added `ProviderBoundaryRegressionTests.test_forbidden_memory_is_detected_after_decoding_json_string_escapes`. It checks both ordinary JSON and the Unicode-escaped JSON form through the actual `_record_request` seam with the local fake response adapter.

RED command:

```text
python3 -B -m unittest -v tests.p04.test_native_runner.ProviderBoundaryRegressionTests.test_forbidden_memory_is_detected_after_decoding_json_string_escapes
```

The ordinary JSON subtest passed; the escaped JSON subtest failed at the receipt assertion:

```text
extra_content='{"memory":{"entries":["\\u006fther memory"]}}' ... FAIL
AssertionError: True is not false : JSON memory case 1 was missed
Ran 1 test
FAILED (failures=1)
```

The narrow fix now scans ordinary string values and, for each valid JSON string representation, decoded string values. Invalid JSON and structured/multipart strings retain the raw-text scan. Exact owner/agent/source/file matching and source-prefix rules are unchanged. No general decoding, dependency, or production-security claim was added.

Focused GREEN command:

```text
python3 -B -m unittest -v tests.p04.test_native_runner.ProviderBoundaryRegressionTests.test_forbidden_memory_is_detected_after_decoding_json_string_escapes tests.p04.test_native_runner.ProviderBoundaryRegressionTests
```

Result: all 10 provider-boundary tests passed, including ordinary/escaped JSON, the authorized snapshot, prior plain/multipart contamination, structured identity detection and source-prefix protection. Full native/offline/P02 results and the new actual pinned-Hermes fake-provider run are recorded below.

The full native runner suite passed 28 tests, the offline suite passed 16, and the P02 checker passed 39 fixtures and 10 examples/rejection mutations. The pinned-Hermes run completed as `p04-dad145eebf8f` with 4 normal jobs, 2 truncation fixtures, 1 HTTP-503 fixture, 1 cancellation, 8 local fake requests and 0 real inference. Its `qualification-result.json` SHA-256 is `dca3c1eb947cd5416ca16f85ba9d65fd361bb41e58df0b386102c0b18168238d`; cancellation evidence SHA-256 is `b9d502b4634d15f74384d7d363bdb987098d33a0657ffdb92bc0c83d4cbcb2b5`; image cleanup SHA-256 is `dd4bd08b8b8582c53f66ad361714af411a3dbdee18c4904561ae594c529cd2fe`. Both the task-labelled container query and exact image inspection confirmed absence. This runtime run confirms pinned-Hermes integration; the exact Unicode-escape behavior is established by the direct `_record_request` regression above.


## R3 combined repair: test-first record

The R3 independent pair found two failures on candidate `f78043b01160d0a0a13a8b1c0af35570932cf2d7`. The normal-job consumer accepted false owner/agent and full-snapshot receipt fields. The identifier scanner also missed forbidden IDs in valid JSON text after Unicode escapes decoded. No reviewer or gate verdict has been consumed on this repair.

Before the production edits, I added consumer regressions and decoded-identifier tests. The consumer regression drives the actual `_record_request` and `_run_normal`; only the external Docker process/output is simulated. It tests wrong owner, wrong agent, changed `enabled` on cleared memory, and extra items in empty source/file snapshots. A healthy populated snapshot and a healthy empty/cleared snapshot must both pass.

The first consumer test attempt exposed two test-harness errors: the test had not added the qualification directory to `sys.path`, and a shallow nested copy let the memory mutation also change the expected task. I corrected the import path and deep-copied the expected JSON before accepting RED evidence. Then, with the R3 consumer code absent, this command failed for the expected behavior:

```text
python3 -B -m unittest -v tests.p04.test_native_runner.ProviderBoundaryRegressionTests.test_normal_result_consumer_rejects_identity_and_snapshot_mismatches
```

Observed: owner, agent, cleared-memory and empty-file subtests each failed with `AssertionError not raised`. The empty-source mismatch was already rejected by the prior explicit empty-source guard.

The identifier regression's exact raw JSON string is `encoded_identifiers` in `tests/p04/test_native_runner.py:777`. The test places it in system content, a multipart text part, and nested tool-call arguments. Before the probe change, the test failed in each placement with `decoded owner was missed`. A separate test checks that decoded suffixes such as `owner-b-suffix`, `agent-b-suffix`, `source-a-suffix` and `file-a-suffix` remain non-matches. The existing escaped-memory, raw text and structured identity tests remain active.

The raw stdout/stderr logs for the R3 RED commands and focused GREEN command were not retained as files. The observations in this section were recorded in the task transcript and summarized here; they do not have independent log-file hashes. The regression tests remain in the committed source, and the post-fix focused and full-suite PASS results are recorded in the candidate-bound result packet.

After adding unconditional identity and full memory/source/file equality checks to `_run_normal` and scanning decoded valid-JSON string values with the existing identifier-boundary pattern, this command passed all 13 provider-boundary tests:

```text
python3 -B -m unittest -v tests.p04.test_native_runner.ProviderBoundaryRegressionTests
```

Full results on the R3 candidate: native runner 32 tests PASS; offline P04 16 PASS; P02 checker 39 fixtures and 10 examples/rejection mutations PASS; AST syntax and `git diff --check` PASS. Actual pinned-Hermes evidence is `p04-c96421621654`, detailed in the R3 result packet and current runtime/research/README follow-up sections. It records four exact normal snapshots, all five forbidden-context flags true, two failed/partial truncation paths, one 503 fixture, cancellation recovery, eight local fake requests and zero real inference.
