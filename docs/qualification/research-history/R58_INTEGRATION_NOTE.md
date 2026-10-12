# P07 → #58 integration note

Status: PROPOSAL to `#58` (owner of all application wiring) from task `P07-SOURCE-L3-20261012-01`. It defines the
stable library interface, the provenance/dataset surface and the error codes, and lists the prerequisites for a
real-source run. It grants no application wiring, credential, provider, wallet or publication authority.

## Stable public interface (import from `edge_os_api.research_history`)

| Call | Signature | Returns |
|---|---|---|
| `EnvioHypersyncSource(client, *, context=SourceContext(), clock=utc_now)` | injected `EnvioQueryClient` | a `ResponseSource` |
| `collect(profile, source, scan, limits, provenance=None, clock=utc_now)` | unchanged accepted seam | a `CollectionResult` dict |
| `corroborate_records(client, records, *, population_size=None, sample_size=8, chain_id=None, clock=utc_now)` | injected `QuickNodeRpcClient` | `evidence["corroboration"]`-shaped dict |
| `read_chain_id(client)` | injected `QuickNodeRpcClient` | `{method, chain_id, network, attempts}` |
| `normalize(profile, collection, evidence)` | unchanged accepted seam | a `NormalizedHistory` dict |
| `save_manifest(build_manifest(history), path)` / `verify_manifest` | unchanged accepted seam | sha256 / bool |

`#58` mounts these. P07 owns the package and tests; it does not wire routes, jobs, storage, a verifier or UI.

## Request interface

A run builds the accepted `HistoryRequest` from the profile: `provider="ENVIO_HYPERSYNC"`, `address` = profile
pool, `topic0` = profile topic0, `from_block`/`to_block_exclusive` = the scan, `cursor_after=None` on the first
call and the accepted cursor after. The transport rebuilds the response query echo from the request, so the
collector's `QUERY_MISMATCH`, `PROVIDER_MISMATCH` and coverage checks are unchanged.

## Dataset and provenance surface

The transport adds no dataset field. It fills the accepted collector result, which the normalizer materializes
into the bound profile:

- `collection.pages[]` — `page_id`, `from_block`, `next_block`, `sha256` (page content hash), edge timestamps and
  optional edge hashes. `sha256` feeds the accepted `dataset_revision` (`PAGE_DIGESTS`).
- `collection.requests[]` — per step: the request view, `cursor_before`, `cursor_after`, `complete`, `rows`,
  `bytes`.
- `collection.provenance` — provider, provider version, `data_route`, first/last `served_utc`, and the
  measurement label (`measured_local_attempts` exact; `provider_requests` `SUPPLIED_EVIDENCE` or `UNKNOWN`).
- `transport_record()` — the transport's own facts (`attempted_requests`, `pages_framed`, `records_framed`,
  `content_sha256[]`, `network_echo`, `ordering`, `units`, `missingness`). `#58` may save it beside the manifest.
- `evidence["corroboration"]` — the independent QuickNode sample result described above.
- `manifest` — the accepted portable record (`build_manifest`).

`served_utc` is the collection clock, never an availability fact. Availability stays the profile model.

## Error interface

| Type | Codes | Meaning |
|---|---|---|
| `AdapterInputError` (`InvalidInput`) | `PROFILE_INVALID`, `SCAN_MALFORMED`, `INVALID_LIMIT`, `EVIDENCE_MALFORMED`, `BOUND_PROFILE_INVALID`, ... | caller error, before any source call |
| `SourceContractError` (`SourceFailure`) | `WRONG_NETWORK`, `MALFORMED_PROVIDER_RESPONSE`, `PAGE_FACTS_INCOMPLETE`, `NON_JSON_PROVIDER_VALUE`, `CONTEXT_INVALID` | provider response refused; collector records `PROVIDER_ERROR` partial, no row/byte kept |
| `SourceTimeout` / `SourceCancelled` | — | collector `TIMEOUT` / `CANCELLED` partial |
| collector `stop_reason` | `COMPLETE`, `SOURCE_EXHAUSTED`, `LIMIT_*`, `DEADLINE`, `CURSOR_CYCLE`, `REPEATED_PAGE`, `COVERAGE_INCOMPLETE`, `PROVIDER_ERROR`, `CANCELLED`, `TIMEOUT` | terminal status |

A provider `complete` flag alone is not coverage. A cap stop or any gap is `PARTIAL` and never `COMPLETE`.

## Actual versus hypothetical replay (preserve this distinction)

- **Actual run:** `source.provenance.origin` and the collection `served_utc` come from a real injected client; the
  manifest records real page hashes and a real `collection_sha256`.
- **Hypothetical/offline replay:** authored responses reproduce the same code path but prove no provider behavior.
  The `profile.evidence_class` and the collection provenance label keep the two apart. A consumer must not
  present an offline replay as an actual observation on a real pool.

## Real-source enablement prerequisites

1. An actual `EnvioQueryClient` and a QuickNode client that own their credentials host-side, pace, hash each
   response and never pass a credential to the dataset, logs or a model. Not part of this milestone.
2. Approved bounds from the collection packet (chain id, pool, orientation, window, availability, request/cost
   ceilings).
3. A `#58` job reservation and owner budget holding the request counts before the source runs.
4. The reused P07 normalization/qualification unchanged; `LIMITED`/`UNRESOLVED` stays unbound (`BindingNotEmittable`).
5. No consumer change to the accepted adapter semantics; coordinate any proposal with `%0` and `#58` first.

## Open items for `#58` / builder

- Quote/base orientation for MOE/WMON, and the declared decision schedule/floors for `SCHEDULE_FEASIBILITY`.
- How a `LIMITED` real binding is represented (accepted P02 has no limited state).
- Whether `#58` saves `transport_record()` beside the manifest for run auditing.
