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
- Proof: `cd apps/api && uv run --frozen pytest tests/research_history -v` passes (43 tests);
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

- `status` `COMPLETE` only when a page reports `complete`; otherwise `PARTIAL`.
- `stop_reason`: `COMPLETE`, `SOURCE_EXHAUSTED`, `LIMIT_PAGES`, `LIMIT_ROWS`, `LIMIT_BYTES`, `DEADLINE`,
  `CURSOR_CYCLE`, `REPEATED_PAGE`, `PROVIDER_ERROR`, `CANCELLED` or `TIMEOUT`.
- `pages` with exact page identity and hash; `records` in supplied order; `page_count`, `row_count`, `bytes`.
- `query` with the definition and its canonical `identity_sha256`.
- `requests`: the request, cursor-before, cursor-after, completion flag, rows and bytes per step.
- `gaps` and a canonical `collection_sha256`. A partial collection is never reported as complete.

`normalize(profile, collection, evidence) -> NormalizedHistory` returns the bound P07 profile, exact decimals
and units, the ordered decoded trades (`identity`, `price`, `quote_amount`, `base_amount`, `pool_side`), the
reused `history_observations` output, the per-claim `qualify` result, the `binding_view`, gaps and the hashes
that bind the result to the profile, the collection and the observations. `project_binding(profile, result)`
projects to the accepted P02 binding and preserves refusal.

`evidence_manifest` builds a portable manifest, saves it as P02 canonical bytes, reads it back, and
`verify_manifest` recomputes the page digest and the counts. The same evidence always gives the same file and
the same SHA-256.

## Finite limits

`max_pages`, `max_rows` and `max_bytes` must be positive integers. `deadline_utc` is optional. A limit stop
gives `PARTIAL`, never `COMPLETE`. These are caller-defined local test parameters, not paid or live
allowances. The collector grants no quota.

## Reuse mapping

| Adapter step | Reused seam |
|---|---|
| Observations from bound pages and logs | `history_observations(profile, logs, window)` |
| Per-claim verdict and overall | `qualify(profile, observations)` |
| Page revision digest | `dataset_revision(pages)` |
| Dataset and observation identity | `profile_sha256`, canonical P02 bytes and `validate_record` |
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
| Discontinuity | `test_block_discontinuity_is_recorded_and_collection_continues` |
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
