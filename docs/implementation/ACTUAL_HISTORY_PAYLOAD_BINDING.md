# ACTUAL history payload binding

This implementation adds an ACTUAL-capable recorder and saved-data checker. It activates no release, provider operation,
credential access, market adoption or replay. Synthetic tests do not establish provider authentication, source rights,
P07 qualification or demo readiness.

## Versions and compatibility

The injected `run_attempt` and historical checker keep their `/1` synthetic behavior. The historical checker stays pinned
to SHA256 `1c74d8c9bce020e35bb372dd4a363641f1ed35566263163a9dd18807264fd667`.
Historical artifacts cannot be promoted by changing their labels or attaching a new sidecar.

| Artifact | ACTUAL schema |
|---|---|
| Handoff H | `edge-os.forward-history-handoff/2` |
| Receipts R | `edge-os.forward-history-transport-receipts/1` |
| Provenance P | `edge-os.forward-history-provenance/1` |
| Release anchor A | `edge-os.forward-history-binding/2` |
| Saved-payload report | `edge-os.history-payload-binding/2` |
| Canonical payload | `edge-os.forward-history-payload/1` |

The legacy `edge-os.forward-history-handoff/1` and `edge-os.history-payload-binding/1` cannot bind ACTUAL.
The retained receipts, provenance and payload `/1` schemas remain allowed. There is no suffix-based version rejection.

## Producer and write order

`scripts.forward_history_recorder.run_actual_attempt(raw_input, *, clock, credentials, cancel=None)` validates the frozen
input before credentials. It constructs exactly one `owned_stdlib_transport` internally. It accepts no caller transport.
It reuses `_Attempt`, the append-only journal, `RecordingTransport`, exclusive writes and the historical projection.
Both selected history slots are read through the supplied reader. The call ceiling stays 17 QuickNode and 9 HyperSync.

The separately authorized operator entry is:

```sh
python -m scripts.forward_history_actual_run --input /private/path/frozen-input.json
```

It delegates to the producer and uses the existing `EnvironmentCredentialSource.read`. It neither constructs a second
transport nor reads an entire environment file. Production slot names are `QUICKNODE_API_URL` and `HYPERSYNC_API_KEY`.
The input already contains the attempt and source identity. `plan` and `recover` remain separate, read-only entry points.

Each artifact has one final exclusive 0600 write, using the exact canonical bytes without a trailing newline:

1. Write H to `handoff.json`. H has the complete recorder handoff fields, `/2`, both evidence classes `ACTUAL`, and the
   transport value `{construction, implementation, implementation_sha256}`. It contains no digest of R, P or A.
2. Build R from the exact H digest. Write `transport-receipts.json`. R retains its complete `/1` schema, with ACTUAL
   evidence and the same transport identity.
3. After R succeeds, build P and write `provenance.json`. P has exactly `schema_version`, `attempt_id`, `handoff_sha256`,
   `receipts_sha256`, `recorder_code_sha256`, `transport` and `receipts_json`. The last field retains the exact R text so
   the application can verify the whole graph without an external private-file lookup.
4. The operator later constructs A inside the existing `provider_facts.forward_history_binding` field. Its exact keys
   are `schema_version`, `handoff_json`, `handoff_sha256`, `receipts_sha256`, `provenance_json`, `provenance_sha256`.
   The release hash covers A. A is not written by the recorder.

An H write failure returns `forward_history_handoff_missing`. An R or P write failure returns
`forward_history_provenance_missing`. Partial files and the earlier prefix stay untouched. No later artifact is built
or written after a failed write. No failure retries, resumes or recollects. An existing attempt is refused.
`LOCAL_FIXTURE` and injected, subclassed, wrapped or modified transport constructions are refused for the actual seam.

Construction identity has the existing recorder's process-owner limits. It does not authenticate the remote provider.
The in-memory HTTPS peer used by tests demonstrates that distinction. It does not establish provider data.

## Checker and admission

`scripts/history_payload_binding_v2.py` verifies the complete raw H/R/P graph before comparing saved data. It validates
schemas and bounds, all internal digest and attempt links, identical owned transport identities, the complete per-call
receipt set, request/reply facts, accounting ceilings, P3 receipt references and delivered bucket receipts.
It uses the pinned historical projection directly. It never relabels `/2` bytes as `/1` or changes historical globals.

The offline entry reads bounded files and creates one exclusive report:

```sh
python -m scripts.history_payload_binding_v2 --handoff H --provenance P --export E --expected X --out report.json
```

The expected input retains the trusted owner, dataset, source and release fields from `/1`, plus `receipts_sha256`,
`provenance_sha256`, `recorder_attempt_id`, application `job_id` and application `attempt_id`. A missing expected identity
cannot pass. The export remains `{dataset_id, owner_id, content_sha256, content, raw_records}`.

The application selects the matching checker from the frozen requirement version. It hashes checker bytes on every use
and executes those exact bytes. `/2` also pins its projection, adapter, time helpers and their transitive P02/P07 source
and contract assets. Missing or changed checker/helper bytes produce INCOMPLETE. The accepted identities are the
`CHECKER_SHA256`, `CHECKER_SHA256_V2` and `CHECKER_DEPENDENCIES_V2` constants in the application binding module.
The `/2` checker also checks its helper pins for offline use.

`check_release` reaches `_check_history` and `check_definition` before credential reads. ACTUAL admission requires the
complete `/2` anchor, completed delivery under a trusted clock, and consistent source, chain, pool, base/quote roles,
window, scan and `QUOTE_PER_BASE` orientation. Missing ACTUAL anchors refuse before effects.
Generic code checks the supplied identities. It hardcodes no token market. For the accepted MOE/WMON direction, pool
order remains token0 WMON and token1 MOE, while MOE is BASE and WMON is QUOTE. P02 token order stays `[base, quote]`.
The public release binding view retains exactly the handoff hash and evidence class. Validation prevents malformed
anchors from acquiring an ACTUAL label. Stand-in `/1` and unbound views retain their existing shapes.

## Saved rows and consumers

The attempt and dataset freeze the graph hashes, recorder attempt and exact selected checker identity. The immutable
`HISTORY_PAYLOAD_BOUND` event retains private H and P texts, graph identities, report and checker identity. P retains R.
No current mutable release registry is consulted to reinterpret old saved rows.

`record_binding` flushes and freshly reads the owner-scoped persisted dataset before checking its raw rows. Adoption
and replay call `require_bound`; it selects the immutable attempt/event and freshly reads the same owner-scoped dataset.
The checker recomputes content/raw hashes, projects every saved row against its retained header and scan, compares
owner/source/release/attempt/market/window identities, and checks all four bucket counts, digests and availability times.
Delivery times retain the recorder's conservative whole-second rounding.

A saved PASS or recomputed outer hashes grant nothing. A passing rerun must reproduce the saved report hash exactly.
A saved refusal cannot be refilled. A changed checker identity leaves old bindings INCOMPLETE. Contradictory data stay
MISMATCH; missing evidence stays INCOMPLETE. Neither status changes the saved P07 verdict or permits consumer writes.

`public_event` removes the known private H/P/R text and raw-record fields recursively from binding events, replacing them
with sizes or counts. It preserves public hashes, result, report and lineage. Error codes contain no provider body,
credential, endpoint secret or private artifact path.

## Packaging and verification boundaries

The `/2` checker is admitted by `.dockerignore`, copied by `deploy/docker/api.Dockerfile`, and listed in deployment
`RUNTIME_ASSETS`. Its trusted application/contract helpers already use the image's repository layout. The credential
reader entry and recorder are excluded from the public API image.

Pure tests cover the producer with an in-memory HTTPS peer, internal-link mutations with recomputed outer hashes,
partial file writes, strict nested schemas, actual admission, saved reruns, checker changes, private-event redaction and
public-view compatibility. Legacy recorder/checker tests remain required. The application loopback check, enabled
transport receipt loopback checks, PostgreSQL saved pipeline/restart checks, real Docker context and selected-image
runtime checks require their separate resource grants. An unrun boundary remains required proof.

Job admission rechecks the ACTUAL graph and executed checker before reservation and before worker credentials. It recomputes the release digest and compares it with both the composed and frozen release identities. A different valid graph needs a new declaration. STAND_IN and Nansen-only admission keep their existing behavior.
