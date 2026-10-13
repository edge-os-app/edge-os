# P07 actual-collection qualification packet (proposal)

Status: PROPOSAL FOR CONTROLLER/BUILDER BOUNDS. Task `P07-HTTP-L3-20261012-01 v2`, issue #10. Nothing here
is approved and no collection ran. Every actual status in this packet is `NOT_RUN`. This packet requests
later bounds; it consumes no earlier probe budget and enables no actual data now.

It extends `docs/qualification/research-history/COLLECTION_PACKET.md` with the concrete client bounds.
With the two clients now present, the only remaining prerequisites are the approved packet bounds and a
`#58` job reservation/owner budget.

## 1. Source, route and network

| Item | Value | Basis |
|---|---|---|
| Network | Monad mainnet, chain id 143 | docs.monad.xyz; docs.envio.dev |
| History provider | Envio HyperSync, `https://monad.hypersync.xyz` (`POST /query`, `Authorization: Bearer`) | docs.envio.dev; Context7 `/enviodev/docs` 2026-10-12 |
| Corroboration provider | QuickNode Monad JSON-RPC (`eth_chainId`, `eth_getTransactionReceipt`) | docs.monad.xyz; quicknode.com |
| Data route label | `ENVIO_QUICKNODE_CORROBORATED` | accepted P07 profile |
| Credential | Bearer token / endpoint key: a runtime input for the injected client only; never in dataset, logs, evidence, model input or source | global constraints |

## 2. Pool, assets and units

| Item | Value | Basis |
|---|---|---|
| Pool | nad.fun MOE/WMON `0x97199b34564911936bc850ac45ede785892b5aad`, Uniswap-V2-compatible `Swap` | Probe A report |
| token0 | WMON `0x3bd359c1119da7da1d913d1c4d2b7c461115433a`, 18 decimals | Probe A report |
| token1 | MOE `0xd8e004acba279417c04c0633cb5a21ceca207777`, 18 decimals | Probe A report |
| Orientation | builder to choose QUOTE and BASE; WMON as quote proposed | open decision |
| Measurement | pool-gross amounts; transfer/reflection, wrapping, routing, gas, price impact, capacity unmodeled | accepted profile |

## 3. Window and coverage

- Proposed window: `2026-09-25T00:00:00Z` to `2026-09-27T00:00:00Z` (two days). It avoids the sealed
  Probe A holdout (`2026-09-30` to `2026-10-02`).
- Desired coverage: every five-minute bucket proven from retained pages that tile the scan; dataset
  revision `PAGE_DIGESTS`.
- Expected limitation: `HISTORY_COMPLETENESS_AND_ORDER` reaches `LIMITED` at best, because corroboration
  is a sample and a full-window QuickNode log scan is infeasible (100-block `eth_getLogs` limit on
  `rpc.monad.xyz`).
- Availability: builder must state the model. Proposed `ASSUMED_DELAY` 180 s, delivery not observed.

## 4. Finite request, byte and time bounds

Collection limits (accepted `CollectionLimits`): `max_pages` 16, `max_rows` 10,000, `max_bytes` 4,194,304,
`deadline_utc` collection start + 1,800 s.

New client bounds (injected `ClientBounds`):

| Bound | Proposed value | Meaning |
|---|---|---|
| `deadline_seconds` | 120 | Whole-call wall budget per provider request |
| `connect_timeout_seconds` | 15 | Per-socket wait |
| `max_response_bytes` | 8,388,608 | Retained reply body cap per HyperSync page |
| `max_request_bytes` | 65,536 | Request body cap |
| `max_blocks_per_page` | 10,000 | HyperSync page block-span cap |

| Bound | Value |
|---|---|
| HyperSync page requests | <=16, paced <=10/min, no retry |
| QuickNode receipt samples | <=8 (predetermined positions) |
| QuickNode decimals `eth_call` | <=6 (record state-unavailable as such) |
| QuickNode `eth_chainId` + `eth_getCode` | 2 |
| Total provider requests | <=36 |
| Spend above existing plans | USD 0.00; stop on any quota message |

## 5. Corroboration sample

`sample_size = 8` over the retained records; positions are the deterministic spread the accepted
corroboration module computes. Class is `SAMPLED` unless the window holds <=8 records, in which case
`COMPLETE`. Any mismatch stays a `LIMITED`/`UNRESOLVED` history claim; it is never repaired.

## 6. Enablement prerequisites (all required before any request)

1. Builder bounds for this packet recorded (chain id, pool, orientation, window, availability model,
   spend) and the values in sections 3-5 approved.
2. A `#58` job reservation and owner/run budget holding the section 4 counts before the source runs;
   usage saved as evidence.
3. Host-side credentials: an Envio HyperSync bearer token and a QuickNode Monad endpoint key, injected
   only into the clients, never persisted to the dataset, logs, evidence or a model.
4. The reused P07 normalization/qualification unchanged; a `LIMITED`/`UNRESOLVED` result stays unbound.

## 7. Exact commands, evidence and cleanup

Offline proof of the clients and the accepted seams (run now; already passing):

```sh
cd apps/api && uv run --frozen pytest tests/research_history -q
cd docs/qualification/p07 && python3 -B -m unittest test_p07
python3 -B docs/contracts/p02/check_contract.py
```

A future actual run reuses the accepted recipe over the two new clients. It is `NOT_RUN` and is not
authorized by this packet:

```python
from edge_os_api.research_history import (
    CollectionLimits, EnvioHypersyncSource, SourceContext, build_manifest, collect,
    corroborate_records, normalize, read_chain_id, save_manifest)
from edge_os_api.research_history.http_clients import (
    ClientBounds, HttpEnvioQueryClient, HttpQuickNodeRpcClient, StdlibHttpTransport)

bounds = ClientBounds(120.0, 15.0, 8_388_608, 65_536, 10_000)
transport = StdlibHttpTransport()
envio = HttpEnvioQueryClient(endpoint="https://monad.hypersync.xyz", bearer_token=token,
                             transport=transport, bounds=bounds)
quicknode = HttpQuickNodeRpcClient(endpoint=quicknode_endpoint, transport=transport, bounds=bounds)
source = EnvioHypersyncSource(envio, context=SourceContext())
chain = read_chain_id(quicknode)
collection = collect(profile, source, scan, CollectionLimits(max_pages=16, max_rows=10_000,
                                                             max_bytes=4_194_304, deadline_utc=deadline),
                     provenance={"provider_requests": {"ENVIO_HYPERSYNC": envio.accounting()["attempted_requests"]}})
corroboration = corroborate_records(quicknode, collection["records"],
                                    population_size=collection["row_count"], sample_size=8,
                                    chain_id=chain["chain_id"])
history = normalize(profile, collection, {**provider_facts, "corroboration": corroboration})
save_manifest(build_manifest(history), manifest_path)
```

Evidence to retain: each response SHA-256, `envio.accounting()` and `quicknode.accounting()` (attempts,
completed, unknown liability), the `#58` reserved/consumed request counts, `transport_record()`, the
manifest, and the exact command lines and durations.

Cleanup: close connections (the transport does this per request), delete any temporary raw artifacts that
are not required evidence, and retain no credential in any output. Stop and report on any deviation.

## 8. Unknown fees, coverage and rights

- Provider cost beyond published text: unknown. The Envio plan and the QuickNode plan limits behind the
  endpoints are not known to this task.
- Monad coverage on HyperSync and the exact served wire shape: `NOT_VERIFIED`; a run must confirm both.
- Provider terms for retaining or sharing raw responses: not checked. Keep evidence to ids, ranges,
  hashes, counts and the approved sample.
- Historical-state reads (window-start decimals): may fail inside the node's state retention; record
  failures as such.

## 9. Stop conditions

Stop and report on: any request beyond a ceiling; any HTTP error or quota message; a chain id other than
143; a pool code hash or token decimals different from section 2; a page that does not tile the scan; any
credential in an output; any read after the window end; wall time over 1,800 s; any mismatch in a sampled
corroboration.

## Status of every actual item

| Item | Status |
|---|---|
| Envio HyperSync actual query | NOT_RUN |
| QuickNode actual JSON-RPC | NOT_RUN |
| Actual collection of the window | NOT_RUN |
| Actual corroboration | NOT_RUN |
| Actual qualification verdict | NOT_RUN |
| Provider fee/coverage/rights confirmation | NOT_RUN |
