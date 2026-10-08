# P04-NATIVE-02 repair round 1 test evidence

This records test-first checkpoints for the repair. RED entries are outcomes observed before their matching code change. The prior reviewers' challenge evidence is not counted as worker RED. Failures in the actual Docker recipe are retained as separate `run-failure.json` files and are not treated as passes.

## RED observations

- The first regression run of `python3 -B -m unittest -v tests.p04.test_native_runner.ProviderBoundaryRegressionTests tests.p04.test_native_runner.BootstrapRecoveryTests` exposed four existing defects: valid cleared memory raised `IndexError` at the fake-provider receipt; the truncation fixture returned `finish_reason="stop"` instead of `"length"`; and build/inspection fault cases produced no `run-failure.json`.
- After adding a numeric-token edge case, `python3 -B -m unittest -v tests.p04.test_native_runner.ProviderBoundaryRegressionTests.test_boolean_output_limit_is_not_accepted_as_a_numeric_token_ceiling` failed with HTTP status 200 instead of rejecting JSON `true` as a token value. The guard now requires an exact positive integer.
- Actual pinned-Hermes run `p04-86f48f6cbf1e` stopped at the second same-owner task because test sentinels `source-a` and `source-a-b` overlapped under substring matching. The fixture IDs were made disjoint. Actual pinned-Hermes run `p04-a4fc402d8fa3` showed `iteration_summary` rejection but not `truncation_continuation` in the same test configuration; the recipe was split into two actual-Hermes cases with iteration limits 2 and 1.

## GREEN observations

- The empty/cleared-memory and incomplete-length-response provider-boundary tests passed after the receipt and truncation fixture changes.
- The exact provider request-count test admitted one 128-token request and rejected a second same-sized request with `physical_request_count_exceeded`, without provider work. The boolean token-limit test passed after validation was tightened.
- Bootstrap tests passed for successful build plus failed inspection, build failure, and cleanup timeout. They preserved the original `CalledProcessError` and `image_build` stage, recorded the exact run-specific tag, and marked cleanup `unknown_pending_verification` when cleanup could not be checked.
- Full actual pinned-Hermes recipe passed as run `p04-60b7244fc4dc`. It recorded one accepted local request followed by rejection of a 256-token continuation in one case, and a 256-token iteration-summary attempt in another. Both actual Hermes returns are `TRUNCATED_PARTIAL`, failed, and not P02-validated. No second fake-provider work occurred.
- Actual Hermes received owner A/agent A corrected memory version 2; owner A/agent C's cleared disabled version 2 with empty memory and sources; a different owner A agent snapshot; and owner B/agent D's MEM-Q04 authority-challenging note. Receipts confirmed the scoped memory/source/file snapshots, no tools and max_tokens 128. The authoritative local fixture digest matched before and after; its file was not mounted into containers. This is structural fake-provider evidence, not a real-model safety result.
- `python3 -B -m unittest -v test_p04`: 16 passed.
- `python3 -B -m unittest -v tests.p04.test_native_runner`: 16 passed.
- `python3 -B docs/contracts/p02/check_contract.py`: PASS, 39 fixtures and 10 record examples.
- Canonical actual-run cleanup: image tag verified absent; `after_labeled_containers` is empty; cancellation recovery remains `INTERRUPTED`/`UNKNOWN` with its USD 2.00 local reservation retained and no replay. Real inference count is zero.

The hosted application, authenticated storage/routing, live provider, upstream cancellation, actual provider billing, Hermes streaming, and resistance of a real model to authority-changing memory remain unqualified.
