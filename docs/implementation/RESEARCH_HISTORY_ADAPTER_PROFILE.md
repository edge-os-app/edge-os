# P07 research history adapter profile

Status: local library for P07 review (issue #10), task `P07-HISTORY-L3-20261012-01`. It defines one
transport-injected bounded history collector and normalizer over supplied recorded responses. It qualifies
no real pool and makes no provider call. It holds no credential, wallet, model, deployment or main-branch
authority. The whole of P07 is not complete and no fresh history is qualified.

## Change, preserved behavior, proof

- Change: add a new package `apps/api/src/edge_os_api/research_history/` with a bounded collector, a
  normalizer, an evidence manifest and a small loader over the frozen P07/P02 seams. Add new tests under
  `apps/api/tests/research_history/` and this profile plus `docs/qualification/research-history/`.
- Preserved: `docs/qualification/p07/qualification.py`, the P02 contract, fixtures and checkers, Probe A
  results, the holdout and closed allowances are unchanged. Numeric and qualification logic is reused, not
  copied. P03's verifier, `main.py`, `core/`, existing `research/`, `replay/`, migrations and lockfiles are
  untouched. #58 owns database, API, schema, client, UI, verifier and job composition.
- Proof: `cd apps/api && uv run --frozen pytest tests/research_history -v` passes (62 tests);
  `cd docs/qualification/p07 && python3 -B -m unittest -v test_p07` passes (73 tests);
  `python3 -B docs/contracts/p02/check_contract.py` passes. Exact outputs are kept under the assigned
  evidence folder and are not part of the commit.

## Boundary

The package is a library, not a service. It reads only its caller-supplied response source. It has no live
transport and no database, API, UI or job wiring. It reads no environment variable and no credential file.
The one shipped source, `RecordedResponseSource`, serves an in-memory list of recorded responses. A missing
safe import seam into an unowned file is a proposal to the controller, not a patch.

## Inputs

| Input | Meaning |
|---|---|
| `profile` | A valid P07 `p07.market_dataset_profile/1`. It fixes the pool, tokens, event, source, availability, finality and dataset window. |
| `source` | A `ResponseSource`. The collector calls `next_response(request)`; a recorded response or `None`. |
| `scan` | `{from_block, to_block_exclusive}` for the page requests. |
| `limits` | Finite `CollectionLimits`; see below. |
| `provenance` | Caller metadata echoed into the result. |
| `clock` | Injected `() -> ISO-8601 UTC string`; tests inject a fake. |
| `evidence` | Facts only a provider read gives: `collected_at_utc`, `archive_height`, `chain_id_source`, `pool_tokens` read state, `pool_venue` read state, `decimals` reads, `fee_transfer_semantics`, `corroboration`, `finality_at_collection`, `feasibility_claim`. |

Inputs explicitly name the existing P07 profile, query and window. A valid profile is well formed, not proof
of provider truth. Supplied events stay raw; the reused decoder refuses anything the profile does not define.

## Recorded response format (supplied)

```jsonc
{
  "provider": "ENVIO_HYPERSYNC", "provider_version": "envio-hypersync/1",
  "served_utc": "2026-09-25T10:30:00Z",
  "query": {"address": "<pool>", "topic0": "<topic0>", "from_block": 100, "to_block_exclusive": 111},
  "page": {"page_id": "rh-p1", "from_block": 100, "next_block": 104, "sha256": "<64 hex>",
           "first_block_timestamp": 1790000000, "last_block_timestamp": 1790000060,
           "first_parent_hash": "<hex|absent>", "last_block_hash": "<hex|absent>"},
  "cursor": {"before": null, "after": 104},
  "complete": false,
  "events": [{"address": "<hex40>", "topic0": "<hex>", "topic1": "<hex>", "topic2": "<hex>",
              "data": "<hex256>", "block_number": 101, "block_hash": "<hex>", "block_timestamp": "1790000030",
              "transaction_hash": "<hex>", "transaction_index": 0, "log_index": 0, "removed": false}]
}
```

The normalizer maps each event to the P07 log shape by building `topics = [topic0, topic1, topic2]` from the
present keys and keeping every other raw value. Refusals stay the decoder's job: a missing topic key drops it
from the list (`TOPIC_COUNT`), a malformed word gives `TOPIC_FORMAT`, a wrong pool gives `WRONG_POOL`, a float
or boolean amount gives `FIELD_NOT_UINT`, and a non-object record gives `NOT_AN_OBJECT` while the batch
continues. Nothing is repaired or guessed.

## Outputs

`collect(profile, source, scan, limits, provenance, clock) -> CollectionResult` returns:

- `status` `COMPLETE` only when a page reports `complete` and the retained pages prove the requested scan;
  otherwise `PARTIAL`.
- `stop_reason`: `COMPLETE`, `SOURCE_EXHAUSTED`, `LIMIT_PAGES`, `LIMIT_ROWS`, `LIMIT_BYTES`, `DEADLINE`,
  `CURSOR_CYCLE`, `REPEATED_PAGE`, `COVERAGE_INCOMPLETE`, `PROVIDER_ERROR`, `CANCELLED` or `TIMEOUT`.
- `pages` with exact page identity and hash; `records` in supplied order; `page_count`, `row_count`, `bytes`.
- `query` with the definition and its canonical `identity_sha256`.
- `requests`: the request, cursor-before, cursor-after, completion flag, rows and bytes per step.
- `gaps` and a canonical `collection_sha256`. A partial collection is never reported as complete.

`normalize(profile, collection, evidence) -> NormalizedHistory` returns the bound P07 profile, exact decimals
and units, the ordered decoded trades (`identity`, `price`, `quote_amount`, `base_amount`, `pool_side`), an
ordered bucket view, the reused `history_observations` output, the per-claim `qualify` result, the
`binding_view`, gaps and the hashes that bind the result to the profile, the collection and the observations.
`project_binding(profile, result)` projects to the accepted P02 binding and preserves refusal.

`evidence_manifest` builds a portable manifest, saves it as P02 canonical bytes, reads it back, and
`verify_manifest` recomputes the page digest and the counts. The same evidence always gives the same file and
the same SHA-256.

## Consumer interface (amendment 2026-10-12)

The date controller amendment `r58-r7-a.md` adds four consumer requirements. Exact field paths follow.

### 1. Ordered window buckets

`NormalizedHistory["buckets"]` is one object per existing 300-second UTC window bucket, in time order. It is
built with the accepted `bucketize` and `bucket_available_at` seams unchanged. `history_observations` still
returns only summaries; the buckets are not placed there.

| Field | Meaning |
|---|---|
| `bucket_start`, `bucket_end` | The bucket bounds `[start, end)` as ISO-8601 UTC text. |
| `status` | `COMPLETE_OCCUPIED`, `COMPLETE_EMPTY`, `INCOMPLETE` or `UNQUALIFIED`. |
| `close` | The exact decimal price string of the last qualified trade, or `null`. |
| `quote_volume` | The exact quote volume text, or `null`. A complete-empty bucket keeps `"0"`. |
| `available_at` | Earliest use time from the accepted availability helper, or `null`. |
| `availability_basis` | `ASSUMED_DELAY`, `OBSERVED_DELIVERY` or `UNKNOWN`. |
| `reasons` | The bucket reasons plus any availability reason. |

A complete-empty bucket has a null close and its proved `"0"` volume. An incomplete or unqualified bucket has
a null close and a null volume; it never becomes complete or zero here. There is no interpolation, carrying
or lookahead. Reconstructed delay stays `ASSUMED_DELAY`; an absent delivery record leaves `available_at`
null with basis `UNKNOWN` and reason `DELIVERY_NOT_RECORDED`. The full trade view stays in the raw bucket
under `bucketize`; this view carries only the exact price string. Example bucket:

```json
{"bucket_start": "2026-09-25T10:00:00Z", "bucket_end": "2026-09-25T10:05:00Z",
 "status": "COMPLETE_OCCUPIED", "close": "2", "quote_volume": "2",
 "available_at": "2026-09-25T10:05:30Z", "availability_basis": "OBSERVED_DELIVERY", "reasons": []}
```

`evidence["delivery_records"]` is an optional `{bucket_start: arrival_utc}` mapping used only by the
availability helper. It is not a financial value.

### 2. Measured attempts versus provider requests

`CollectionResult["source_invocations"]` separates the two:

| Field | Meaning |
|---|---|
| `measured_local_attempts` | An exact local count of `next_response` calls, including a call that raised. |
| `provider_requests` | `null` when unknown, or `{provider: count}` when the caller supplies evidence. |

A source error or timeout after an invocation keeps the attempted count; it never reports `0` because no
response arrived. Consuming an archived page is not evidence of a new or original provider request. The
provenance block labels the measurement: `provenance.measurement.provider_requests` is `SUPPLIED_EVIDENCE` or
`UNKNOWN`. `CollectionResult["coverage"]` retains the requested scan, the page ranges and whether the pages
tile the scan. A provider `complete` flag alone is not proof of query or window coverage; the retained pages,
segments, gaps and coverage flag are the evidence. A `complete` flag with pages that do not tile the scan
gives `stop_reason` `COVERAGE_INCOMPLETE` and `PARTIAL`. A response must echo the requested query; a missing
query echo is refused as `QUERY_MISMATCH`. A page whose identity fields are not a non-negative integer range
with a non-empty id and a 64-hex digest is refused as `PROVIDER_MALFORMED_PAGE`. A cursor whose `after` is not
a non-negative integer or null is refused as `PROVIDER_MALFORMED_CURSOR`. Any source exception other than the
two declared ones becomes a `SOURCE_ERROR` gap and a `PROVIDER_ERROR` `PARTIAL` result, with the attempted
count kept and no retry.

### 3. `normalized_sha256` and raw evidence

`NormalizedHistory["normalized_sha256"]` is the P02 canonical SHA-256 of the complete normalized payload with
its own digest field removed. It binds `bound_profile`, `buckets`, `trades`, `observations`, the
qualification, the binding view, the collection summary, the retained page identity and `raw_evidence`.
`collection_sha256`, `input_profile_sha256`, `bound_profile_sha256`, `observations_sha256` and `result_sha256`
are retained beside it. The payload has no JSON floating-point value. Retained measurements use exact unit
text; a clock reading is never a data or financial value.

`NormalizedHistory["raw_records"]` keeps the exact supplied records, and `raw_evidence` holds
`{sha256, record_count}` of them. The raw records may hold a value the canonical encoder refuses, so they are
kept out of the hashed payload and written by `save_raw_artifact(records, path)` to a run-owned file with a
lenient deterministic form. `load_raw_artifact(path)` reads them back. A consumer can replay normalization
from the saved artifact: the same records, profile and evidence reproduce the same `normalized_sha256`, the
same ingest counts and the same `collection_sha256`.

### 4. Input and failure semantics

A malformed caller profile or limit raises the accepted `InvalidInput` before any source invocation. The
adapter error classes subclass it. `deadline_utc` must be a real UTC instant; a non-instant string is refused
before any fetch and the deadline is compared as instants, not text. An ordinary source or provider failure
returns a `PARTIAL` `CollectionResult` with an existing `stop_reason`; it is never `COMPLETE` and never retries
implicitly. Malformed provider input is recorded as refusal or partial evidence; it is never repaired or
dropped as successful coverage. Programmer defects in the adapter and `BaseException` are not swallowed; only
the source call catches an ordinary `Exception`. The finite limits and the qualifier
`InvalidInput`/`Unsupported` meanings are unchanged. Cancellation uses the injected source (a `SourceCancelled`
exception) and the injected clock; the clock is a determinism seam, not a live elapsed-time guarantee. Only an
overall `QUALIFIED` result projects to P02; `LIMITED` stays saved beside the declaration.

## Finite limits

`max_pages`, `max_rows` and `max_bytes` must be positive integers. `deadline_utc` is optional. A limit stop
gives `PARTIAL`, never `COMPLETE`. The caps are checked before each fetch and again after each accepted page,
before any completion claim. A page that alone pushes a counter past its cap ends the run `PARTIAL` with the
matching `LIMIT_*` reason, and the fetched evidence is kept. These are caller-defined local test parameters,
not paid or live allowances. The collector grants no quota.

## Reuse mapping

| Adapter step | Reused seam |
|---|---|
| Observations from bound pages and logs | `history_observations(profile, logs, window)` |
| Per-claim verdict and overall | `qualify(profile, observations)` |
| Page revision digest | `dataset_revision(pages)` |
| Dataset and observation identity | `profile_sha256`, canonical P02 bytes |
| Decode, ingest, coverage, buckets, availability, feasibility | the frozen P07 module, called, not copied |

Facts are labelled: `supplied_by_caller` (provider-read facts), `derived_by_engine` (pages and logs) and
`ingest` account for themselves. The result never claims that a self-reported observation was independently
checked. Reconstructed availability stays an assumption. Unknown is never zero. A limited or unresolved
result is carried beside the profile; `to_p02_binding` still refuses it.

## Required cases and where they are tested

| Required case | Test |
|---|---|
| Supplied transport to complete or partial result | `test_history_collector.py::test_complete_collection_keeps_exact_pages_and_trace`, `..._partial` |
| Finite page, row, byte and deadline limits | `test_finite_limits_stop_the_loop`, `test_deadline_uses_the_injected_clock` |
| Cancel and timeout | `test_cancel_and_timeout_are_retained_as_partial` |
| Cursor cycle and repeated page | `test_cursor_cycle_stops_before_a_duplicate_page`, `test_repeated_page_is_detected` |
| Discontinuity blocks a complete claim | `test_block_discontinuity_blocks_a_complete_claim` |
| Provider mismatch and malformed response | `test_provider_mismatch_and_malformed_events_are_provider_errors` |
| Both directions and token order | `test_both_pool_sides_are_seen_and_token_order_is_the_p02_order` |
| Reordered records | `test_supplied_record_order_does_not_change_the_result` |
| Raw uint, bool, wrong pool, topic, malformed refusals | `test_provider_records_are_refused_with_stable_codes`, `test_non_object_record_is_rejected_and_the_batch_continues` |
| Duplicate copies | `test_exact_duplicate_copies_count_once` |
| Conflict | `test_conflicting_position_blocks_a_complete_verdict` |
| Conflicting page hashes and reorg | `test_conflicting_page_hashes_break_the_segment` |
| Complete empty versus incomplete buckets | `test_complete_empty_and_incomplete_buckets_stay_distinct` |
| Exact raw units and high precision | `test_high_precision_price_uses_the_50_digit_half_even_context` |
| Sampled and full corroboration | `test_sampled_corroboration_limits_the_history_claim` |
| Assumed and unknown availability | `test_availability_models_limit_or_unresolve_timing` |
| Provenance, hash tampering, manifest round-trip | `test_evidence_manifest.py` |
| LIMITED projection refusal | `test_limited_real_result_is_refused_by_the_p02_projection` |
| Ordered window buckets with consumer fields (amendment 1) | `test_buckets_expose_every_window_bucket_with_consumer_fields` |
| Incomplete buckets never become complete or zero (amendment 1) | `test_incomplete_buckets_never_become_complete_or_zero` |
| Assumed delay and missing delivery availability (amendment 1) | `test_assumed_delay_and_missing_delivery_change_only_availability` |
| Measured attempts vs provider requests (amendment 2) | `test_source_invocations_are_measured_and_provider_requests_stay_unknown`, `test_evidenced_provider_requests_are_labelled`, `test_cancel_retains_the_attempted_invocation` |
| Coverage evidence retained (amendment 2) | `test_coverage_evidence_records_whether_the_pages_tile_the_scan` |
| `normalized_sha256` repeatable, change and tamper (amendment 3) | `test_normalized_sha256_is_repeatable_binds_the_payload_and_changes` |
| Malformed profile refused before invocation (amendment 4) | `test_malformed_profile_is_refused_before_any_invocation` |
| Response without a query echo refused | `test_response_without_a_query_echo_is_refused` |
| Malformed page identity refused as provider evidence | `test_malformed_page_identity_is_refused_as_provider_evidence` |
| Caps enforced before a complete claim (gate) | `test_caps_are_enforced_before_a_complete_claim` |
| Invalid deadline refused before invocation (gate) | `test_invalid_deadline_is_refused_before_any_invocation` |
| Ordinary source error becomes a partial result (gate) | `test_ordinary_source_error_becomes_a_partial_result` |
| Malformed cursor refused (gate) | `test_malformed_cursor_is_refused` |
| Raw evidence retained and replay (gate) | `test_manifest_retains_raw_evidence_and_replays` |
| Tampered raw records fail verification (gate) | `test_tampered_raw_records_fail_verification` |
| Manifest consumer metadata | `test_evidence_manifest.py::test_manifest_includes_consumer_metadata` |
| No live transport or environment discovery | `test_package_has_no_live_transport_or_environment_discovery` |

## Proposed feature-map row for #58

| Feature | Provider | Adapter | Notes |
|---|---|---|---|
| Real price-volume history for one pool | `apps/api/src/edge_os_api/research_history/` | `collect` then `normalize` then `save_manifest` | #58 mounts the library, stores the manifest, serves the result and wires the browser journey. This package stores nothing. |

## Not verified

Any real Envio, QuickNode or Monad behavior, the retained pages, the type checker (`mypy`, `ruff` and
`pytest` are not installed globally), Python versions other than 3.14.4, runtime cost, database, API, UI,
job wiring and anything about execution or profit. Public application UI, SQL and browser rows are `NOT_RUN`
for this unmounted library. The verifier is not edited and its full journey is not claimed.
