# P07 collection and qualification packet (proposal)

Status: PROPOSAL FOR CONTROLLER/BUILDER BOUNDS. Task `P07-SOURCE-L3-20261012-01`. Nothing here is approved and
no collection ran. It freezes the exact source, pool, units, window, request/cost/data-use bounds and the
collection/qualification commands for a later, separately authorized run. Public facts are chosen here; the
builder decides the quote/base orientation and the availability model.

## 1. Source, route and network

| Item | Value | Basis |
|---|---|---|
| Network | Monad mainnet, chain id 143 | docs.monad.xyz; docs.envio.dev |
| History provider | Envio HyperSync, `https://monad.hypersync.xyz` | docs.envio.dev supported-networks |
| Corroboration provider | QuickNode Monad JSON-RPC (`eth_getTransactionReceipt` sampling only) | docs.monad.xyz; quicknode.com |
| Data route label | `ENVIO_QUICKNODE_CORROBORATED` | accepted P07 profile |
| Credential | bearer token / endpoint key: runtime input for the injected client only; never in dataset, logs, evidence, model input or source | global constraints |

## 2. Pool, assets and units

| Item | Value | Basis |
|---|---|---|
| Pool | nad.fun MOE/WMON `0x97199b34564911936bc850ac45ede785892b5aad`, Uniswap-V2-compatible `Swap` | Probe A report |
| token0 | WMON `0x3bd359c1119da7da1d913d1c4d2b7c461115433a`, 18 decimals | Probe A report |
| token1 | MOE `0xd8e004acba279417c04c0633cb5a21ceca207777`, 18 decimals | Probe A report |
| Orientation | builder to choose QUOTE and BASE; WMON as quote proposed | open decision |
| Measurement | pool-gross amounts; transfer/reflection, wrapping, routing, gas, price impact, capacity unmodeled | accepted profile |

## 3. Window and coverage

- Proposed window: `2026-09-25T00:00:00Z` to `2026-09-27T00:00:00Z` (two days; about 6,500 swaps expected).
  It avoids the sealed Probe A holdout (2026-09-30 to 2026-10-02).
- Desired coverage: every five-minute bucket in the window proven from retained pages that tile the scan;
  the dataset revision is `PAGE_DIGESTS`.
- Expected limitation: `HISTORY_COMPLETENESS_AND_ORDER` reaches `LIMITED` at best, because corroboration is a
  sample and a full-window QuickNode log scan is infeasible (100-block `eth_getLogs` limit on `rpc.monad.xyz`).
- Availability: builder must state the model. Proposed `ASSUMED_DELAY` 180 s, with delivery not observed.

## 4. Finite request/cost/data-use bounds

| Bound | Value |
|---|---|
| `max_pages` / `max_rows` / `max_bytes` | 16 / 10,000 / 4,194,304 |
| `deadline_utc` | collection start + 1,800 s |
| HyperSync page requests | ≤16, paced ≤10/min, no retry |
| QuickNode receipt samples | ≤8 (predetermined positions) |
| QuickNode decimals `eth_call` | ≤6 (record state-unavailable as such) |
| QuickNode `eth_chainId` + `eth_getCode` | 2 |
| Total provider requests | ≤36 |
| Spend above existing plans | USD 0.00; stop on any quota message |

## 5. Corroboration sample

`sample_size = 8` over the retained records; positions are the deterministic spread the corroboration module
computes. Class is `SAMPLED` unless the window holds ≤8 records, in which case `COMPLETE`. Any mismatch stays a
`LIMITED`/`UNRESOLVED` history claim; it is never repaired.

## 6. Enablement prerequisites (all required before any request)

1. An actual-data `EnvioQueryClient` that owns the token host-side, paces requests and records each response hash.
   Not implemented here; `EnvioHypersyncSource` is the framing seam it plugs into.
2. An actual-data QuickNode client for `corroborate_records`, with the same credential rules.
3. A `#58` job reservation holding the section 4 counts before the source runs; usage saved as evidence.
4. The reused P07 normalization and qualification unchanged; `LIMITED`/`UNRESOLVED` stays unbound.
5. Builder bounds for this packet recorded (chain id, pool, orientation, window, availability model, spend).

## 7. Collection and qualification commands (later run)

```sh
# 1. Collect (injected clients; token is a runtime input, never logged)
python3 -m edge_os_api.research_history.collect_run --window 2026-09-25T00:00:00Z 2026-09-27T00:00:00Z \
  --scan-from <from_block> --scan-to-exclusive <to_block_exclusive> --out .scratch/p07-source/run
# 2. Normalize + qualify (reused seams)
python3 -m edge_os_api.research_history.qualify_run --manifest .scratch/p07-source/run/manifest.json
# 3. Verify the manifest identity
python3 -c "from edge_os_api.research_history import load_manifest, verify_manifest; \
m=load_manifest('.scratch/p07-source/run/manifest.json'); print(verify_manifest(m))"
```

Commands 1-2 are placeholders for a small run driver `#58` owns; the library seams they call
(`EnvioHypersyncSource`, `collect`, `corroborate_records`, `normalize`, `save_manifest`) exist and are tested
offline. The run driver is not created here.

## 8. Stop conditions

Stop and report on: any request beyond a ceiling; any HTTP error or quota message; a chain id other than 143; a
pool code hash or token decimals different from section 2; a page that does not tile the scan; any credential in
an output; any read after the window end; wall time over 1,800 s; any mismatch in a sampled corroboration.
