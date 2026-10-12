# P07 research history adapter checks

These checks exercise the local history adapter `apps/api/src/edge_os_api/research_history/` with authored
synthetic fixtures. They use the reused P07 qualification module and the P02 contract checker read-only. They
make no network call, read no credential or environment file and run no downloaded code.

Run from the repository root:

```sh
cd apps/api
uv run --frozen pytest tests/research_history -v
cd ../..
cd docs/qualification/p07
python3 -B -m unittest -v test_p07
cd ../../..
python3 -B docs/contracts/p02/check_contract.py
```

Files:

| File | Role |
|---|---|
| `apps/api/src/edge_os_api/research_history/` | Bounded collector, normalizer, evidence manifest, P07/P02 loader, injected Envio source transport and injected QuickNode corroboration. |
| `apps/api/tests/research_history/` | Public-seam tests and labelled synthetic fixtures. |
| `docs/implementation/RESEARCH_HISTORY_ADAPTER_PROFILE.md` | The accepted adapter interface and limit profile. |
| `docs/implementation/RESEARCH_HISTORY_SOURCE_TRANSPORT_PROFILE.md` | The injected source-transport and corroboration profile (task P07-SOURCE). |
| `docs/qualification/research-history/COLLECTION_PACKET.md` | The finite later-collection proposal. |
| `docs/qualification/research-history/R58_INTEGRATION_NOTE.md` | The #58 interface and enablement note. |

Fixtures are labelled `SYNTHETIC_FIXTURE`. Addresses, hashes and amounts are invented. Expected amounts,
prices and counts were written by hand from the decimal-50 half-even rule. They were not produced by the code
under test.

What a pass shows: the collector and normalizer behave as the profile says for the covered cases, and the
reused P07 and P02 checks still pass. What it does not show: the behavior of Envio, QuickNode or Monad, the
completeness of any real window, historical delivery or finality, token mechanics, execution, fills, costs or
profit. No fresh history is qualified.

## Case map

| Case ID | Required case | Test |
|---|---|---|
| RH-C01 | Supplied transport to complete collection result | `test_history_collector.py::test_complete_collection_keeps_exact_pages_and_trace` |
| RH-C02 | Partial result is never complete | `test_history_collector.py::test_source_exhausted_without_complete_flag_is_partial` |
| RH-C03 | Finite page, row and byte limits | `test_history_collector.py::test_finite_limits_stop_the_loop` |
| RH-C04 | Deadline on the injected clock | `test_history_collector.py::test_deadline_uses_the_injected_clock` |
| RH-C05 | Cancel and timeout | `test_history_collector.py::test_cancel_and_timeout_are_retained_as_partial` |
| RH-C06 | Cursor cycle | `test_history_collector.py::test_cursor_cycle_stops_before_a_duplicate_page` |
| RH-C07 | Repeated page | `test_history_collector.py::test_repeated_page_is_detected` |
| RH-C08 | Block discontinuity | `test_history_collector.py::test_block_discontinuity_is_recorded_and_collection_continues` |
| RH-C09 | Provider mismatch and malformed response | `test_history_collector.py::test_provider_mismatch_and_malformed_events_are_provider_errors` |
| RH-C10 | Invalid limits refused before fetch | `test_history_collector.py::test_invalid_limits_are_refused_before_any_fetch` |
| RH-C33 | Response for another pool or range refused | `test_history_collector.py::test_response_for_another_pool_or_range_is_refused` |
| RH-C11 | Qualified history with hand-calculated amounts | `test_history_normalizer.py::test_qualified_history_matches_hand_calculated_amounts` |
| RH-C12 | Both pool sides and P02 token order | `test_history_normalizer.py::test_both_pool_sides_are_seen_and_token_order_is_the_p02_order` |
| RH-C13 | Record order independence | `test_history_normalizer.py::test_supplied_record_order_does_not_change_the_result` |
| RH-C14 | Raw uint, bool, wrong pool, topic and malformed refusals | `test_history_normalizer.py::test_provider_records_are_refused_with_stable_codes` |
| RH-C15 | Non-object record | `test_history_normalizer.py::test_non_object_record_is_rejected_and_the_batch_continues` |
| RH-C16 | Exact duplicate copies | `test_history_normalizer.py::test_exact_duplicate_copies_count_once` |
| RH-C17 | Position conflict | `test_history_normalizer.py::test_conflicting_position_blocks_a_complete_verdict` |
| RH-C18 | Conflicting page hashes and reorg | `test_history_normalizer.py::test_conflicting_page_hashes_break_the_segment` |
| RH-C19 | Complete empty versus incomplete buckets | `test_history_normalizer.py::test_complete_empty_and_incomplete_buckets_stay_distinct` |
| RH-C20 | Exact raw units and high precision | `test_history_normalizer.py::test_high_precision_price_uses_the_50_digit_half_even_context` |
| RH-C21 | Sampled corroboration limits the claim | `test_history_normalizer.py::test_sampled_corroboration_limits_the_history_claim` |
| RH-C22 | Assumed and unknown availability | `test_history_normalizer.py::test_availability_models_limit_or_unresolve_timing` |
| RH-C23 | Chain-id source contradiction | `test_history_normalizer.py::test_chain_id_source_contradiction_is_unresolved` |
| RH-C24 | LIMITED projection refusal | `test_history_normalizer.py::test_limited_real_result_is_refused_by_the_p02_projection` |
| RH-C25 | Synthetic projects unqualified | `test_history_normalizer.py::test_synthetic_result_projects_as_unqualified_not_qualified` |
| RH-C26 | Malformed page and missing evidence | `test_history_normalizer.py::test_malformed_page_and_missing_evidence_are_input_errors` |
| RH-C27 | Supplied and derived facts are labelled | `test_history_normalizer.py::test_observations_label_supplied_and_derived_facts` |
| RH-C28 | Deterministic manifest round-trip | `test_evidence_manifest.py::test_manifest_round_trip_is_byte_identical` |
| RH-C29 | Tampered page fails verification | `test_evidence_manifest.py::test_tampered_page_fails_verification` |
| RH-C30 | Wrong expected hash fails verification | `test_evidence_manifest.py::test_wrong_expected_hash_fails_verification` |
| RH-C31 | Manifest records boundaries and qualification | `test_evidence_manifest.py::test_manifest_records_the_collection_boundaries_and_qualification` |
| RH-C32 | No live transport or environment discovery | `test_evidence_manifest.py::test_package_has_no_live_transport_or_environment_discovery` |
| RH-C34 | Measured attempts versus provider requests | `test_history_collector.py::test_source_invocations_are_measured_and_provider_requests_stay_unknown` |
| RH-C35 | Evidenced provider requests are labelled | `test_history_collector.py::test_evidenced_provider_requests_are_labelled` |
| RH-C36 | Cancel retains the attempted invocation | `test_history_collector.py::test_cancel_retains_the_attempted_invocation` |
| RH-C37 | Malformed profile refused before any invocation | `test_history_collector.py::test_malformed_profile_is_refused_before_any_invocation` |
| RH-C38 | Coverage evidence records scan tiling | `test_history_collector.py::test_coverage_evidence_records_whether_the_pages_tile_the_scan` |
| RH-C39 | Ordered window buckets with consumer fields | `test_history_normalizer.py::test_buckets_expose_every_window_bucket_with_consumer_fields` |
| RH-C40 | Incomplete buckets never become complete or zero | `test_history_normalizer.py::test_incomplete_buckets_never_become_complete_or_zero` |
| RH-C41 | Assumed delay and missing delivery availability | `test_history_normalizer.py::test_assumed_delay_and_missing_delivery_change_only_availability` |
| RH-C42 | `normalized_sha256` repeatable, change and tamper | `test_history_normalizer.py::test_normalized_sha256_is_repeatable_binds_the_payload_and_changes` |
| RH-C43 | Manifest consumer metadata | `test_evidence_manifest.py::test_manifest_includes_consumer_metadata` |
| RH-C44 | Response without a query echo refused | `test_history_collector.py::test_response_without_a_query_echo_is_refused` |
| RH-C45 | Malformed page identity refused as provider evidence | `test_history_collector.py::test_malformed_page_identity_is_refused_as_provider_evidence` |
| RH-C46 | Complete flag with unproven scan stays partial | `test_history_collector.py::test_block_discontinuity_blocks_a_complete_claim` |
| RH-C47 | Oversized response refused without retaining rows or bytes | `test_history_collector.py::test_oversized_response_is_refused_without_retaining` |
| RH-C48 | Invalid deadline refused before invocation | `test_history_collector.py::test_invalid_deadline_is_refused_before_any_invocation` |
| RH-C49 | Ordinary source error becomes a partial result | `test_history_collector.py::test_ordinary_source_error_becomes_a_partial_result` |
| RH-C50 | Malformed cursor refused | `test_history_collector.py::test_malformed_cursor_is_refused` |
| RH-C51 | Raw evidence retained and replay | `test_evidence_manifest.py::test_manifest_retains_raw_evidence_and_replays` |
| RH-C52 | Tampered raw records fail verification | `test_evidence_manifest.py::test_tampered_raw_records_fail_verification` |
| RH-C53 | Programmer defect from the source propagates | `test_history_collector.py::test_programmer_defect_from_the_source_propagates` |
| RH-C54 | Non-JSON response value refused | `test_history_collector.py::test_non_json_response_value_is_refused` |
| RH-C55 | Injected Envio source frames a complete collection | `test_source_transport.py::test_complete_collection_frames_native_pages` |
| RH-C56 | Page content hash binds the page | `test_source_transport.py::test_page_content_hash_binds_the_page` |
| RH-C57 | Wrong network refused | `test_source_transport.py::test_wrong_network_is_refused` |
| RH-C58 | Network echo recorded when present | `test_source_transport.py::test_matching_network_echo_is_recorded` |
| RH-C59 | Malformed native response is a source failure | `test_source_transport.py::test_malformed_native_response_is_a_source_failure` |
| RH-C60 | Incomplete page facts refused | `test_source_transport.py::test_page_facts_incomplete_is_refused` |
| RH-C61 | Missing fields counted, not repaired | `test_source_transport.py::test_missing_fields_are_counted_not_repaired` |
| RH-C62 | Client failure, timeout and cancel are partial | `test_source_transport.py::{test_client_failure_is_a_partial_result,test_client_timeout_and_cancel_are_partial}` |
| RH-C63 | Rate limit is one attempt, no retry | `test_source_transport.py::test_rate_limit_is_one_attempt_no_retry` |
| RH-C64 | Programmer defect propagates | `test_source_transport.py::test_programmer_defect_from_the_client_propagates` |
| RH-C65 | No hidden retry on exhaustion | `test_source_transport.py::test_no_hidden_retry_when_pages_are_exhausted` |
| RH-C66 | Corroboration parses `eth_chainId` | `test_quicknode_corroboration.py::test_read_chain_id_classifies_monad` |
| RH-C67 | Full corroboration is complete | `test_quicknode_corroboration.py::test_full_corroboration_is_complete` |
| RH-C68 | Sampled corroboration is sampled | `test_quicknode_corroboration.py::test_sampled_corroboration_is_sampled` |
| RH-C69 | Corroboration mismatch is counted, not repaired | `test_quicknode_corroboration.py::{test_corroboration_counts_mismatch_when_log_is_absent,test_corroboration_mismatch_is_not_repaired,test_corroboration_receipt_missing_is_a_mismatch}` |
| RH-C70 | Corroboration RPC failure is unresolved | `test_quicknode_corroboration.py::test_corroboration_rpc_failure_is_unresolved` |
| RH-C71 | Empty corroboration is none | `test_quicknode_corroboration.py::test_empty_corroboration_is_none` |
| RH-C72 | Corroboration makes one call per sample | `test_quicknode_corroboration.py::test_corroboration_makes_one_call_per_identified_sample` |

The existing P07 checks (`docs/qualification/p07`) and the P02 checker remain the controlling regression
suite. The adapter adds cases RH-C01 to RH-C54; task P07-SOURCE adds RH-C55 to RH-C72. Neither changes the
existing cases.
