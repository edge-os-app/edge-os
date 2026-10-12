# P07 research history source transport profile

Status: local library for P07 review (issue #10), task `P07-SOURCE-L3-20261012-01`. It adds an injected
actual-source transport and an injected independent corroboration to the accepted history adapter. It makes no
provider call, reads no credential and qualifies no real pool. It holds no wallet, model, deployment or
main-branch authority.

## Change, preserved behavior, proof

- Change: add `apps/api/src/edge_os_api/research_history/source_transport.py` (the injected Envio HyperSync
  source), `apps/api/src/edge_os_api/research_history/quicknode_corroboration.py` (the injected QuickNode
  corroboration), their public exports and tests under `apps/api/tests/research_history/`. Add this profile, the
  collection packet and the #58 integration note under `docs/qualification/research-history/`.
- Preserved: the accepted adapter public semantics (`collect`, `normalize`, `project_binding`, the manifest, the
  `ResponseSource` protocol and `RecordedResponseSource`), the P07 module, the P02 contract, the fixtures and the
  closed allowances. `#58` still owns all application wiring.
- Proof: `cd apps/api && uv run --frozen pytest tests/research_history -v` passes (88 tests);
  `cd docs/qualification/p07 && python3 -B -m unittest -v test_p07` passes (73 tests);
  `python3 -B docs/contracts/p02/check_contract.py` passes. Exact outputs are kept under the evidence folder and
  are not part of the commit.

## Boundary

Both modules are libraries. Each takes an injected client and never reads a credential, an environment variable
or a file, and never opens a socket. The one live path a caller can wire is the injected client it supplies. The
transport and corroboration ship no default client.

## Injected Envio source transport

`EnvioHypersyncSource(client, *, context=SourceContext(), clock=utc_now)` implements the accepted
`ResponseSource`. `client` implements `EnvioQueryClient.query(request) -> native response | None`; it owns the
endpoint and the bearer token. The transport makes exactly one client call per `next_response` and never retries.
`context` fixes the served network, chain id, provider, provider version and endpoint.

### Native response mapping (pinned 2026-10-12)

The client returns a native Envio HyperSync `QueryResponse`. The transport maps:

| Native | Adapter field |
|---|---|
| `data.logs[]` (`address`,`topic0`..`topic3`,`data`,`block_number`,`block_hash`,`transaction_hash`,`transaction_index`,`log_index`,`removed`) | `events[]` (same keys) |
| `data.blocks[].timestamp` joined on `log.block_number` | `event.block_timestamp` (raw integer text) |
| `next_block` | `page.next_block` and `cursor.after` |
| request `cursor_after` (else `from_block`) | `page.from_block` and `cursor.before` |
| `rollback_guard.timestamp` (else the last block's timestamp) | `page.last_block_timestamp` |
| the first block's timestamp | `page.first_block_timestamp` |
| `rollback_guard.first_parent_hash` | `page.first_parent_hash` (when present) |
| `rollback_guard.hash` | `page.last_block_hash` (when present) |
| content hash of `{from_block,next_block,logs}` | `page.sha256` (becomes the dataset revision input) |
| `next_block >= to_block_exclusive` | `complete` |

The request/topic/range echo is rebuilt from the `HistoryRequest`, so the accepted collector's `QUERY_MISMATCH`
check still applies. The provider, provider version and served time come from `context` and the injected clock.

### Recorded transport facts

`transport_record()` reports what the accepted collector does not keep: `attempted_requests` (counted before the
client call, so a raising call counts), `pages_framed`, `records_framed`, `content_sha256[]`, `network_echo`
(`ABSENT`/`PRESENT`), `ordering` (the accepted three order fields), `units` (`RAW_INTEGER_WORD`), and
`missingness` (`order_field`, `identity_field`, `time_field`) counts. A record with a missing order, identity or
time field is passed through unchanged and counted; the reused decoder refuses it with its own stable code.

### Refusals

`SourceContractError` subclasses the accepted `SourceFailure`, so the collector records a partial
`PROVIDER_ERROR` with no retained page, row or byte. Codes: `WRONG_NETWORK` (the response names a different
network or chain id), `MALFORMED_PROVIDER_RESPONSE` (not an object, no `data`, `logs` not a list, `next_block` not
a positive integer), `PAGE_FACTS_INCOMPLETE` (the response cannot prove the page edge timestamps, or they fall)
and `NON_JSON_PROVIDER_VALUE`. A client `SourceFailure`/`SourceTimeout`/`SourceCancelled`/`OSError` becomes the
accepted partial result with the attempted count kept and no retry; any other exception propagates.

## Injected QuickNode corroboration

`corroborate_records(client, records, *, population_size=None, sample_size=8, chain_id=None, clock=utc_now)`
compares a deterministic spread of retained records against `eth_getTransactionReceipt` through an injected
`QuickNodeRpcClient.call(method, params)`. One call per sample, no retry. It returns the accepted
`evidence["corroboration"]` shape plus portable entries:

| Field | Meaning |
|---|---|
| `class` | `COMPLETE` (every record compared), `SAMPLED` (part), `NONE` (no records). |
| `provider` | `QUICKNODE_JSON_RPC` — the independent corroborating source. |
| `sample_size`, `population_size`, `mismatches` | Counts the reused `qualify` reads. |
| `records[]` | Per sample: `index`, `identity`, `matched`, `reason`. |

A mismatch reason is `RECORD_NOT_IDENTIFIABLE`, `RECORD_NOT_PRESENT`, `RECEIPT_MISSING`, `RECEIPT_MALFORMED`,
`LOG_NOT_FOUND`, `BLOCK_MISMATCH` or `RPC_FAILED`. Any of them counts toward `mismatches`; none is repaired.
`read_chain_id(client)` reads `eth_chainId` (one call) and classifies the served network.

A full-window QuickNode `eth_getLogs` scan is not proposed: the first-party Monad JSON-RPC page lists a
100-block range limit for `rpc.monad.xyz`, so a multi-day window is not feasible. Corroboration is by sample.

## Provider times and availability

The transport never writes a provider time as an availability fact. `served_utc` is the injected collection
clock, recorded as collection time only. The accepted profile keeps availability a model (`ASSUMED_DELAY`,
`OBSERVED_DELIVERY` or `UNKNOWN`); an observed-delivery claim needs a source delivery record, which this
milestone cannot produce. Consequence: `POINT_IN_TIME_AVAILABILITY` stays `LIMITED` at best here.

## Not verified

Any real Envio, QuickNode or Monad behavior; the actual native response shapes; that HyperSync preserves every
order field for Monad at every page; provider cost beyond published text; provider terms for retaining raw
responses; historical state reads. The modules are written against the pinned schema and tested only with
authored offline responses. No fresh history is qualified; `P07-HISTORY-L3` and the #58 actual-data requirement
stay open until actual evidence.
