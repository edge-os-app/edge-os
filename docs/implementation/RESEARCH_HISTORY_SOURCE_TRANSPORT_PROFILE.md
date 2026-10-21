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
- Proof: `cd apps/api && uv run --frozen pytest tests/research_history -v` passes (119 tests);
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

### Native response mapping (request pinned 2026-10-12; response observed 2026-10-21)

The client returns a native Envio HyperSync `QueryResponse`. The transport maps:

The 2026-10-12 first-party documentation describes `data` as one `ResponseData` object. The served replies
observed on Monad on 2026-10-21 carried `data` as a list of batch objects:

- Recorder run `moe-wmon-fwd20m-actual-20261021b`, call `03-P1-hypersync`, body SHA256
  `b740b4de94e174db9ff341eca43250ea98f8b6ee3600e14c46f5d99e33d3d6d1`.
- Pool census, 9 requests: `v2_pool_census.py` SHA256
  `61b5f8242e59099088dc7de56d8deaa4edbba1f074399219cc177ba68118ae6a`, result `census7.json` SHA256
  `0c0c39dd02d92b9a16c2606fb1abba15c45a0cc5940e0839a6478b286f5d45d3`.
- MOE behavior check, 5 query requests: `moe_behavior_check.py` SHA256
  `b390c38e07f1e8b9f9196d4715739474fb0fa97bf4454247013f78bc5ea34cdf`, result `moe_check1.json` SHA256
  `d8134a021ef3f7b274c9fdcaa4e7796c552d7e75efa27eb4692a5ffe7293318d`.

The transport follows the served replies. This list shape is observed on Monad across those calls; other chains
and response fields remain unverified.

| Native | Adapter field |
|---|---|
| `data[].logs[]` (`address`,`topic0`..`topic3`,`data`,`block_number`,`block_hash`,`transaction_hash`,`transaction_index`,`log_index`,`removed`) | `events[]` (same keys, `block_number` normalised to an integer) |
| `data[].blocks[].timestamp` joined on `log.block_number` | `event.block_timestamp` (raw integer text) |
| `next_block` | `page.next_block` and `cursor.after` |
| request `cursor_after` (else `from_block`) | `page.from_block` and `cursor.before` |
| the block at `next_block - 1` (required; must agree with the guard when both are present) | `page.last_block_timestamp` |
| the block at `from_block` (required for the page start) | `page.first_block_timestamp` |
| `rollback_guard.first_parent_hash` | `page.first_parent_hash` (when present) |
| `rollback_guard.hash` | `page.last_block_hash` (when present) |
| content hash of the page facts and logs | `page.sha256` (becomes the dataset revision input) |
| `next_block >= to_block_exclusive` | `complete` |

### Native quantities and page bounds

A native numeric quantity (block number, timestamp, `next_block`) may arrive as an integer or as a hexadecimal
`0x` quantity string; both are accepted and normalised. The transport validates the served page against the
requested range: `from_block < next_block <= to_block_exclusive`; a present `rollback_guard.first_block_number`
must equal the page start and `rollback_guard.block_number` must equal `next_block - 1`; a rollback guard whose
timestamp or hash contradicts the page-end block fact (`PAGE_FACTS_CONFLICT`) is refused; a block fact outside the
page `[from_block, next_block)` (`OUT_OF_RANGE_BLOCK_FACT`) or a duplicate block fact
that disagrees with itself (`DUPLICATE_BLOCK_FACT`) is refused; the page-start and page-end block facts must be
present;
every `data[]` batch must carry `logs` (absence is not proved
emptiness); a batch may omit `blocks`. The page content hash binds the page bounds, edge hashes and logs, so a source contradiction cannot
become qualified coverage.

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
network or chain id), `MALFORMED_PROVIDER_RESPONSE` (not an object, no `data` list, a batch that is not an object, absent or
non-list batch `logs`, non-list batch `blocks`, a non-object block fact, a non-quantity block number or block timestamp, `next_block` not a
positive quantity, a `rollback_guard` that is not an object, a present guard or chain echo that is not a valid
quantity, or a present block hash or `first_parent_hash` that is not the pinned `0x` + 64-hex block-hash form),
`PAGE_BOUNDS_CONTRADICTED` (an empty or reversed page, a page past the requested end, or a guard block number
that disagrees with the page bounds), `PAGE_FACTS_CONFLICT` (the guard timestamp or hash contradicts the page-end
block fact), `OUT_OF_RANGE_BLOCK_FACT` (a block fact outside `[from_block,
next_block)`), `DUPLICATE_BLOCK_FACT` (one block number claimed twice with different
facts), `PAGE_FACTS_INCOMPLETE` (the response cannot prove the page edge timestamps, or they fall) and
`NON_JSON_PROVIDER_VALUE`. A client `SourceFailure`/`SourceTimeout`/`SourceCancelled`/`OSError` becomes the
accepted partial result with the attempted count kept and no retry; any other exception propagates.

## Injected QuickNode corroboration

`corroborate_records(client, records, *, population_size=None, sample_size=8, chain_id=None, clock=utc_now)`
compares a deterministic spread of retained records against `eth_getTransactionReceipt` through an injected
`QuickNodeRpcClient.call(method, params)`. One call per sample, no retry. It returns the accepted
`evidence["corroboration"]` shape plus portable entries:

| Field | Meaning |
|---|---|
| `class` | `COMPLETE` (every record compared), `SAMPLED` (part), `NONE` (no records or an unverified chain). |
| `provider` | `QUICKNODE_JSON_RPC` — the independent corroborating source. |
| `chain_verified`, `chain_id`, `network` | The independent `read_chain_id` result; `network` is `MONAD` only when the chain is 143. |
| `sample_size`, `population_size`, `mismatches` | Counts the reused `qualify` reads. |
| `records[]` | Per sample: `index`, `identity`, `matched`, `reason`. |

A record is corroborated only when the receipt's transaction hash, transaction index, block number, block hash
and the matching log's own transaction hash, transaction index, block number, block hash, address, topics, data,
log index and a boolean `removed=false` all agree. A `removed` fact that is absent or not a boolean is missing
evidence, never proof that the log is live. A mismatch reason is
`RECORD_NOT_IDENTIFIABLE`, `RECORD_NOT_PRESENT`, `RECEIPT_MISSING`, `RECEIPT_MISSING_FACT`, `RECEIPT_MALFORMED`,
`TRANSACTION_MISMATCH`, `BLOCK_MISMATCH`, `LOG_NOT_FOUND`, `LOG_REMOVED` or `RPC_FAILED`. Any of them counts
toward `mismatches`; none is repaired, and a malformed nested receipt/log shape is a counted mismatch rather than
an escaped exception. `chain_id` is the independent `read_chain_id` observation; a chain that is not 143 yields
`class` `NONE`, `chain_verified` false, `reason` `CHAIN_NOT_MONAD` and no receipt call. `read_chain_id(client)`
reads `eth_chainId` (one call) and classifies the served network.

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
