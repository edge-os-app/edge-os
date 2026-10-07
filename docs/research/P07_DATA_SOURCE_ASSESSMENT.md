# P07 data source and evidence assessment

Status: candidate assessment for P07 review (issue #10). It separates what the accepted record already shows, what this task checked offline, and what nobody has run. Documentation lookups were made on 2026-10-07 with Context7 and Exa. They grant no provider-account use. No credential or environment file was read, no provider was called, no paid service was used, and no downloaded sample was run.

## Sources and the lesson each gave

| Source | Version at lookup | Rights | Lesson used |
|---|---|---|---|
| Uniswap `v2-core`, `UniswapV2Pair.sol` and `IUniswapV2Pair.sol`, <https://github.com/Uniswap/v2-core> | master `6a9e7c97860676e0992f22a49665760444c1cdf5`, 2026-04-02 | GPL-3.0 (GitHub). No source text copied. The event signature and field meaning are the only inputs. | `Swap(address indexed sender, uint amount0In, uint amount1In, uint amount0Out, uint amount1Out, address indexed to)`. Input amounts are balance differences, so both input legs can be nonzero and a swap can move one token both ways. That is why the profile rejects `BOTH_INPUTS`, `BOTH_OUTPUTS` and `SAME_TOKEN_IN_OUT`. The 0.3% fee sits inside the input amount, so amounts are gross. It says nothing about the nad.fun fork. |
| Envio HyperSync query and reorg pages, <https://docs.envio.dev/docs/HyperSync/hypersync-query> and <https://docs.envio.dev/docs/HyperIndex/reorgs-support.md>; Context7 `/enviodev/docs` | live pages 2026-10-07, no version string | Documentation. No text copied. Repository license not checked. | A response has `archive_height`, `next_block` (the block after the last one served) and an optional `rollback_guard` (`first_parent_hash`, `hash`, last block time). The guard exists only near the chain tip. One response is internally consistent. Data fetched earlier can go stale, and the next response's `first_parent_hash` must equal the previous `hash`. The profile stores page ranges, hashes and first/last block times, drops pages too near the tip, and checks the hash chain only where both hashes exist. |
| `enviodev/hypersync-client-python`, <https://github.com/enviodev/hypersync-client-python> | default branch `main`, last push 2026-09-08. Commit not pinned. | MPL-2.0 | A query is address plus topics plus an explicit field selection (block number, log index, transaction index, address, data, topics). It needs a bearer token (`ENVIO_API_TOKEN`). Probe A lost a field once (`topic3`), so every order and identity field is required and a record without one is rejected with a code. Not run. |
| QuickNode `eth_getLogs`, <https://www.quicknode.com/docs/monad/eth_getLogs>; Context7 `/websites/quicknode` | live page 2026-10-07 | Documentation | Block range is capped at 5 blocks on the free trial and 10,000 on paid plans. A log carries `removed` (reorged away), `blockHash`, `blockNumber`, `transactionIndex`, `logIndex`. The page also lists fields from another chain (`l1BatchNumber`), so treat the limit as a template value. A Monad-specific limit is not confirmed. |
| Monad documentation: network information (<https://docs.monad.xyz/developer-essentials/network-information>), summary, block states (<https://docs.monad.xyz/monad-arch/consensus/block-states>) and historical data (<https://docs.monad.xyz/developer-essentials/historical-data>) | live pages 2026-10-07. The network page names `v0.15.2` / `MONAD_NINE`. | Documentation | Mainnet chain id is `143`. `TIMESTAMP` has one-second resolution and several blocks share a second. A block is final after two blocks. Full nodes keep state for about 40,000 blocks, and "no RPC provider is currently offering access to arbitrarily-far-back historical state". `rpc.monad.xyz` is a QuickNode endpoint rated 25 requests per second. |
| Accepted repository inputs | pinned hashes in the implementation document | Repository documents | Operator, calculation, binding, readiness and timing rules. P02 ResearchBinding and canonical bytes are reused unchanged. |

No GitHub example was executed or copied. The Monad state limit is consistent with the four Probe A start-boundary `eth_call` failures. Evicted state would produce that result. The report does not name the endpoint, so this is not confirmed. Decimals at a window start can only be read for a recent window or from an endpoint that keeps older state.

## What is real, what this task ran, what nobody ran

| Item | Status | Evidence and limit |
|---|---|---|
| MOE/WMON pool, token order, 18 decimals at the window end and now | Real, retained | Probe A report. Not re-read here. Chain id `143` is from documentation. |
| 26 pages, 26,146 two-sided V2-compatible swaps, no duplicate, extra or missing identity | Real, retained | Probe A report. The page table is private and is not in this checkout. |
| Four full samples match between Envio and QuickNode | Real, retained, sampled | Four of 26,146 records. This is not complete corroboration. |
| Start-boundary decimals | Real failure, retained | Four calls returned historical-state errors. Immutability stays an assumption. |
| Original delivery time and finality | Unknown | Collection was later than the window. |
| Fork fee and reflection mechanics | Unqualified | Published nad.fun documentation describes V3 and does not fix this fork. |
| Decode, both directions, decimals, tie rounding | Run offline | 47 synthetic tests. Hand-computed expectations. |
| Order, duplicates, conflicts, reorg signatures | Run offline | Synthetic fixtures. |
| Complete-empty versus incomplete, boundaries, close, volume | Run offline | Synthetic fixtures. |
| Availability, late input, schedule and floor feasibility | Run offline | Synthetic fixtures. |
| Profile validation, binding comparison, per-claim verdicts, P02 projection | Run offline | Synthetic fixtures and the retained-report profile. `python3 -B docs/contracts/p02/check_contract.py` still passes. |
| Both pool sides present in the real sample, counts of non-ordinary swaps | Not run | Needs a sanitized extract. |
| Page continuity, hash chain and finality depth on the real pages | Not run | Needs the page table. |
| Complete independent corroboration of the window | Not run | Needs collection. |
| Any execution, fill, cost or profit claim | Not run, out of scope | Separate gates. |

## Sanitized extract that would move the verdicts

Ask the controller for these, in this order. None holds a credential or a raw amount table.

1. The 26-row page table: page id, `from_block`, `next_block`, SHA-256, first and last block timestamps, parent and last block hashes if stored. Add the archive height at collection and the query definition. This moves `HISTORY_COMPLETENESS_AND_ORDER` from unresolved toward limited, because `assemble_segments()` can then test tiling, finality depth and the hash chain.
2. A count of swaps by shape for the window (ordinary one-in one-out, anything else) and the split by pool side. This moves `EVENT_AND_AMOUNT_MEANING` and the unsupported-event gap.
3. The four sampled raw logs. They are public chain data. They give a direction check on real records.
4. The endpoint name used for the window-end decimals reads and the exact error text of the four failed reads.

Rights: the page table and counts are derived from public chain data. Provider terms for keeping or sharing raw responses were not checked. Keep the extract to ids, ranges, hashes, counts and four logs. Confirm before adding more.

## Later real qualification: access and budget to approve

This is a request for a builder decision. It authorizes nothing. The Probe A allowance is closed. No model call, wallet, signing or trade is part of it.

| Access | Purpose | Cap | Basis |
|---|---|---|---|
| Envio HyperSync token already held | Re-query one declared window | 60 requests | Probe A kept 26 pages for this window. Probe A saw an Envio rate of about 15 requests per minute, so 60 requests take about 4 minutes. |
| QuickNode on the current plan, identity reads | `eth_chainId`, pool `token0`/`token1`, token `decimals` at window start, window end and latest | 20 calls | 1 + 2 + 6 reads plus retries. Start reads may fail by design. |
| QuickNode, sampled tier | Full-log comparison on chosen blocks, as Probe A did | 40 calls | Probe A compared four samples. The report does not give its call count, so 40 is a cap, not a measurement. |
| QuickNode, complete tier | `eth_getLogs` over the whole window in ranges of at most 10,000 blocks | 260 calls | The Probe A window is 605,700 s. At the documented 300 ms block time that is about 2.02 million blocks, so 202 calls. At 400 ms it is 152. The cap adds retries. On a 5-block limit the tier needs about 404,000 calls and is not feasible. |
| Time | One session | 2 hours wall clock | Rate limits dominate. |
| Spend | None above the current plans | 0 | Stop if a plan upgrade is needed. |

The sampled tier can only reach `LIMITED`. A complete verdict needs the complete tier or an independent archive count.

## Decisions left open, with reasons

| Decision | Reason it stays open |
|---|---|
| Exact pool | MOE has retained evidence but was picked from one volume snapshot after the fact, so it carries hindsight and survivorship limits. Reuse is proposed for P07 only. |
| Exact period | Window-start decimals can only be read within the node's state retention. A recent window allows that read. The Probe A window cannot. Probe A's holdout stays sealed either way. |
| Decision schedule and floors | The builder declares them before outcomes. The table below is arithmetic on assumed full coverage, not evidence. |
| Endpoint identity and cost | The plan limits of the QuickNode endpoint behind `rpc.monad.xyz` and of the Envio plan are not known to this task. |
| Rights to retain raw responses | Provider terms were not checked. |
| Qualified availability coverage | Historical Envio queries carry no delivery record. Observed availability needs a forward collection that records delivery times, which is a separate task. Until then only assumed delay is possible. |

Schedule arithmetic for one two-day partition, 30-minute outcome horizon, 60-second reference windows, 3 warm-up buckets, floors of 30 triggered and 30 control (`.scratch/p07/evidence/candidate_schedule_arithmetic.txt`, produced by `feasibility()`):

| Decision period | Slots | Usable | Needed | Result |
|---|---|---|---|---|
| 3600 s | 48 | 48 | 60 | short by 12 |
| 1800 s | 96 | 95 | 60 | feasible |
| 900 s | 192 | 190 | 60 | feasible |

A 30-minute period with a 30-minute horizon makes consecutive outcome windows touch. Dependence between them is a STAT-Q01 matter and is not settled here.

## Claim declarations

The verdict is per claim, never for the whole of P07. The offline fixtures pass. That shows the contract is testable. It does not qualify any real pool.

| Claim | Retained MOE/WMON result | Next evidence |
|---|---|---|
| `BINDING_IDENTITY` | LIMITED | A provider `eth_chainId` read, a second read of pool tokens, a second source for the venue. |
| `EVENT_AND_AMOUNT_MEANING` | UNRESOLVED | Extract items 2 and 3. A start-of-window decimals read on a recent window. A fork mechanics decision. |
| `HISTORY_COMPLETENESS_AND_ORDER` | UNRESOLVED | Extract item 1 and item 2. Complete-tier corroboration for `QUALIFIED`. |
| `POINT_IN_TIME_AVAILABILITY` | LIMITED | Forward collection with delivery records, for observed availability. |
| `SCHEDULE_FEASIBILITY` | UNRESOLVED | A declared schedule and floors. |

Execution attainability, trader-net fills, profit and validation are not assessed. This task does not promote profitability, validation or execution gates, and a passing offline check does not call P07 complete.
