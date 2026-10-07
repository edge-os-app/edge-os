# P07 research pool and history profile

Status: candidate contract for P07 review (issue #10). It defines one versioned profile for a research pool and its price-volume history, and a per-claim verdict. It qualifies no real pool. Every real figure here comes from the accepted Probe A report. No collection, provider call, credential, wallet or paid service was used. The whole of P07 is not complete.

Pinned inputs: specification SHA-256 `16d2a92afb0d3173a1b0f73b51fba811bd77e4f93ceb487f01d1e26ce548eeb9`, build brief `536bb82ae1011f88cb0e6ad60be93dd27675d561987630e4561b19529fbb9aaa`, P02 narrative `06ab895dbd8e2a8fa8646e309ee5cc927ac7d2e65c544d805eb6318ba3ec32f6`, Probe A report `d9ef658cec3b0ed29f034efb255497c1462c433c13c7af2e542ab8870f707d7d`. Base commit `ca9f7d6701a78d84a99b7022df123e7e8ef29a62`.

## Change, preserved behavior, proof

- Change: add the profile contract, trade and bucket rules, availability and schedule checks, and a verdict per claim. Code and fixtures are in `docs/qualification/p07/`.
- Preserved: P02 contract, fixtures and checker are unchanged and reused. Probe A results, holdout and closed allowances are unchanged. P03's `verify-edge-os` is not touched.
- Proof: `cd docs/qualification/p07 && python3 -B -m unittest -v test_p07` passes, and `python3 -B docs/contracts/p02/check_contract.py` still passes. Exact outputs are kept under `.scratch/p07/evidence/` in the assigned worktree. That folder is not part of the commit.

## Profile

`p07.market_dataset_profile/1` is a closed JSON object. Unknown keys, missing keys and floats are rejected. Hash it with the P02 canonical bytes (`p02-json-decimal-string/1`). `profile_problems()` returns every violation in one pass. A valid profile is well formed, not qualified.

| Section | Holds | Rule |
|---|---|---|
| `network` | `MONAD`, `chain_id`, `chain_id_source` | `chain_id` is null only with source `UNKNOWN`. Source is `PROVIDER_READ`, `DOCUMENTATION` or `UNKNOWN`. |
| `venue` | underlying venue, pool family, pool address | One V2-compatible pool. Lowercase 40-digit hex. The pool cannot be a token. |
| `pool_tokens` | token0 then token1 in pool order: address, label, kind, decimals, role | One `BASE`, one `QUOTE`. Decimals 0 to 255. Kind `ERC20` or `WRAPPED_NATIVE_ERC20`. Kind `NATIVE` is refused. WMON is not native MON. Labels are never compared. |
| `orientation` | `QUOTE_PER_BASE` | Price is quote per base. |
| `event` | schema `uniswap-v2-swap/1`, signature, `topic0` | `topic0` must equal Keccak-256 of the signature. The module computes it. |
| `conversion` | `v2-swap-quote-per-base-pool-gross/1`, `decimal-50-half-even/1`, `POOL_GROSS` | Amounts are pool-gross. No trader-net field exists. |
| `resolution`, `ordering` | five-minute UTC buckets `[start,end)`; order by block number, transaction index, log index | Fixed by the accepted conventions. |
| `source` | Envio HyperSync history, QuickNode JSON-RPC corroboration, route `ENVIO_QUICKNODE_CORROBORATED` | Fixed by the accepted data route. |
| `availability` | `ASSUMED_DELAY` with `delay_seconds`, `OBSERVED_DELIVERY` with a source delivery record, or `UNKNOWN` | Collection time is refused as delivery evidence. |
| `finality` | documented depth in blocks and its basis | Used to drop pages near the tip at collection. |
| `execution_route` | the P02 unqualified Flow placeholder, nothing else | Research qualification never moves into the route. |
| `unmodeled_effects` | transfer or reflection, wrapping, routing, gas, price impact, capacity | Stated, not measured. |
| `dataset` | window, collection time and archive height, query definition and its hash, page records, dataset revision | Revision is `PAGE_DIGESTS` (hash of page identities), `PRIVATE_NOT_PORTABLE` or `NONE`. A digest must match the pages present. Collection cannot precede the window end. |

Event time is the block timestamp. Collection time is stored on the dataset. Availability is a model, never a field copied from collection time.

## Trade meaning and conversion

The event is the Uniswap V2 pair `Swap(address indexed sender, uint amount0In, uint amount1In, uint amount0Out, uint amount1Out, address indexed to)`. The decoder takes three topics and four 32-byte words. It supports one shape: exactly one input leg, exactly one output leg, on opposite tokens, both nonzero. Every other shape raises `Unsupported` with a stable code: `BOTH_INPUTS`, `BOTH_OUTPUTS`, `ZERO_INPUT`, `ZERO_OUTPUT`, `SAME_TOKEN_IN_OUT`, `TOPIC0_MISMATCH`, `TOPIC_COUNT`, `TOPIC_FORMAT`, `DATA_LENGTH`, `WRONG_POOL`, `REMOVED_BY_REORG`, `ORDER_FIELD_MISSING`, `IDENTITY_FIELD_MISSING`, `TIME_FIELD_MISSING`, `FIELD_NOT_UINT`, `FIELD_NOT_BOOL`. A missing or malformed address is `IDENTITY_FIELD_MISSING`, never `WRONG_POOL`. `removed` must be a real boolean. Nothing is guessed or repaired.

- Pool side is `QUOTE_IN_BASE_OUT` or `BASE_IN_QUOTE_OUT`. It describes the pool, not a trader.
- `quote_raw` and `base_raw` are exact integers from the quote and base legs. Amount text is exact (`2^256-1` keeps 78 digits).
- `price = quote_raw·10^base_decimals / (base_raw·10^quote_decimals)`, one division in a 50-digit half-even context. No 20-digit ingestion step. Ties go to the even digit (`10^50+25` gives `10^50+20`).
- The same swap gives the same price in either pool order and either direction.
- Quote volume counts the quote leg once per trade. The two legs are never added.
- Numbers may be integers, decimal text or `0x` hex. Floats and booleans are refused.

Amounts and prices are gross pool values. They are not wallet-net fills, proceeds or profit. Token mechanics of the MOE fork remain unqualified.

## Identity, order, duplicates, conflicts

Trade identity is `chain:block:transaction_index:log_index`. Hashes are kept. Order is the identity's three numbers, never provider row order and never timestamp. Monad block timestamps have one-second resolution and several blocks share one second, so timestamps cannot order trades.

`ingest()` collects, it does not stop:

- Exact duplicate copies count once. The copy count is kept.
- Same position with different content is a conflict (`POSITION_PAYLOAD`). That includes different sender or recipient topics, and a readable trade that shares its position with an unreadable record. No version is used.
- One block number with two hashes or times, or one block hash on two block numbers (`BLOCK_FACTS`), one transaction hash at two positions, and one transaction index with two hashes (`TX_POSITION`) are conflicts.
- Block times never fall as block numbers rise. Any trade that is part of an inversion with any other trade, adjacent or not, is a `TIMESTAMP_ORDER` conflict. Involved trades are held out. A held-out trade or unreadable record whose time falls outside what its qualified neighbours allow (or whose copies claim different times) has no reliable time. A qualified trade in the same block fixes the record's time exactly. Otherwise the nearest qualified trades in lower and higher blocks bound it. When it has no block number it cannot be placed, and every bucket in the window is unreliable. Its real time can lie anywhere between those neighbours, so every bucket in that interval is spoiled, not only the buckets its claimed time names. A claimed time that sits inside the neighbours' range spoils its own bucket only. A wrong time that stays inside that range cannot be found by ordering. The page record and corroboration are the only defenses.
- Removed (reorged) logs, foreign-pool logs and unsupported shapes are counted by code. A rejected record without a timestamp is counted as unlocated. A row that is not an object is rejected as `NOT_AN_OBJECT` and the batch continues.

## Buckets, coverage and the close

Coverage comes from retained query pages. `assemble_segments()` first drops every page that contradicts other pages, then keeps pages that tile a contiguous block range, are at least the documented finality depth below the archive height at collection, and do not overlap.

Each page makes claims about the blocks at its edges: the time of its first and last block, the hash of its last block, and the parent hash of its first block (the hash of the block before it). A block with two different claimed hashes or two different claimed times is contradicted. One hash that names two different blocks is contradicted too. Every page that speaks about that block is dropped, including pages that repeat one side. Claimed times must also never fall as block numbers rise across all pages, so a page whose time contradicts any other page is dropped together with the pages it contradicts. A page whose parent hash is the last hash of a dropped page is dropped too (`CHAINED_TO_DROPPED_PAGE`), and so on along the chain. The result depends on the page facts only. It does not depend on page ids or page order. Interior blocks of a page are not claimed, so a contradiction that only shows between interior blocks cannot be found. A page that repeats another page's boundary facts exactly is a repeat fetch and is only set aside (`OVERLAP`). Adjacent pages that carry no hashes merge on range and finality depth alone. Break codes are `REORG_BETWEEN_PAGES` (hash contradiction), `TIMESTAMP_ORDER`, `CHAINED_TO_DROPPED_PAGE`, `NOT_FINAL_AT_COLLECTION`, `OVERLAP`, `BLOCK_GAP` and `OUTSIDE_REQUEST`.

A bucket `[s,e)` is covered when one segment has `first_ts < s` and `e <= last_ts`. Reason: block timestamps never fall with block number, so unscanned blocks before the segment are at or below `first_ts` and unscanned blocks after it are at or above `last_ts`. The strict start is deliberate because blocks share seconds.

| Status | Meaning | Close | Quote volume |
|---|---|---|---|
| `COMPLETE_OCCUPIED` | covered, at least one qualified trade | last trade by chain order, with identity, size and time | exact sum of quote legs |
| `COMPLETE_EMPTY` | covered, no trade | none. No carry, no interpolation | `0` |
| `INCOMPLETE` | coverage not proven | none | unknown |
| `UNQUALIFIED` | covered, but a conflict, an unsupported event, an unlocated record or a page disagreement touches it | none | unknown |

A trade must also agree with the page record. A trade from a block no segment scanned spoils the bucket of its timestamp (`TRADE_OUTSIDE_SCANNED_BLOCKS`). A trade whose block hash or time differs from what the pages state for that same block spoils the whole segment (`TRADE_CONTRADICTS_PAGE_HASH`, `TRADE_CONTRADICTS_PAGE_TIMES`). The pages state the hash and time of their edge blocks and the hash of the block before them, and each segment carries those edge facts. A trade inside a segment whose time falls outside that segment's first and last block times spoils every bucket the segment covers (`TRADE_CONTRADICTS_PAGE_TIMES`). Reference windows apply the same rule.

The close is the last qualified trade. It is not VWAP and not a promised fill. A tiny last trade can set it, so its size is kept.

## Availability and time

`bucket_available_at()` gives the earliest use time. Assumed delay gives `bucket end + delay` with basis `ASSUMED_DELAY`. Observed delivery needs a source delivery record and gives `max(bucket end, delivery)`. Unknown gives no time. An incomplete or unqualified bucket is never available. `opportunity_eligibility()` checks each required series at the declared decision time, keeps every reason, and never moves the decision. Reasons: `LATE_INPUT`, `COVERAGE_NOT_PROVEN`, `UNQUALIFIED_RECORDS`, `EMPTY_BUCKET_NO_CLOSE`, `AVAILABILITY_UNKNOWN`, `DELIVERY_NOT_RECORDED`, `BUCKET_NOT_IN_WINDOW`. An empty bucket has zero volume but no price.

Reconstructed availability is an assumption. It limits the claim and does not become observed delivery or finality.

## Schedule, warm-up and feasibility

A decision schedule is an anchor, a period and the offset between a decision and the end of its feature bucket. All three must sit on the five-minute grid. `feasibility(claim, segments, availability)` counts, per partition, the slots that can still produce an opportunity before any outcome is read. It excludes a slot when its outcome windows would pass the partition end, when a reference window is not covered, when the feature bucket is not available by the decision (assumed delay longer than the offset, or unknown model), or when the warm-up buckets are not covered (a lookback of `n` needs `n+1` buckets). The caller declares the floors for triggered and control groups as integers of at least 1. Partitions must be ordered and must not overlap. There is no default floor. With none declared the result is `UNDECLARED`. The count is an upper bound on opportunities. It does not look at unqualified buckets, treats observed delivery as ready at bucket end, and does not discount overlapping outcome windows. With a period equal to the horizon, one opportunity's end reference window is the next one's start window, so dependence is high. STAT-Q01 owns that. Reference lookups (`reference_trade()`) take the first qualified trade by chain order in `[start,end)` and return a missing outcome with a reason (`COMPLETE_EMPTY_WINDOW`, `COVERAGE_NOT_PROVEN`, `UNQUALIFIED_RECORDS`). They never widen the window.

## Claims and verdicts

`qualify(profile, observations)` returns one verdict per claim and an overall verdict. `QUALIFIED` needs direct evidence. `LIMITED` names an assumption or limit. `UNRESOLVED` names a failed check or missing evidence. A missing, malformed or unknown fact never passes. Counts must be real non-negative integers. The overall verdict is the worst claim. `qualify()` trusts the observation values it is given. It checks types, consistency between the counts, and agreement with the profile: the chain id source, the window, the pages (it recomputes how many buckets the retained pages prove and rejects a larger claim), the archive height and the corroborating provider. It binds the result to the profile and observations by hash and names the window it counted (`history_window`). Counting only part of the profile window gives `LIMITED` (`SUBWINDOW_ONLY`). `to_p02_binding()` accepts only a complete result: right schema and scope, all five claims, and an overall verdict that is the worst claim. For a retained-pages profile the count of records seen must equal the manifest `row_count`. Rows that disappear block a complete verdict even when both pool sides and every bucket still show. The check needs every log, even when only part of the window is counted. A subset of logs gives UNRESOLVED, not LIMITED. The count of records seen must also match the counts that account for it: trades, exact duplicate copies, rejected, removed and foreign records, with held-out conflicts as the only allowed excess. Exact duplicate copies stay in the count. A FEASIBLE claim must carry named rows with unique names, each with integer `usable`, `required_total` and `shortfall`, where `shortfall` equals `max(0, required_total - usable)` and is zero, and any slot and exclusion counts must add up. `qualify()` has no copy of the declared claim, so it cannot know how many partitions exist or what floors were declared. The records-seen check stops silent omission. It does not stop omission hidden by repeated copies, because the counts and the corroboration population are self-reported. It cannot check where a value came from. For a real or retained profile it also requires the pages and their revision to travel with the profile. The result states `scope: OFFLINE_CONTRACT_ONLY` and lists what it does not assess.

| Claim | Qualified needs | Limited when | Unresolved when |
|---|---|---|---|
| `BINDING_IDENTITY` | valid profile, chain id read from a provider, pool tokens and venue corroborated | chain id from documentation only, tokens or venue from one read or source, a retained report | profile invalid, chain id unknown, tokens or venue unverified, profile and observation name different chain id sources |
| `EVENT_AND_AMOUNT_MEANING` | events decoded, both pool sides seen, decimals read at the window start, token mechanics qualified | decimals read only later, one pool side, mechanics unqualified | no event sample, no pool side reported, decimals never read |
| `HISTORY_COMPLETENESS_AND_ORDER` | no conflict, no unsupported event, every bucket proven, complete corroboration (every record compared, at least as many records as trades, no mismatch) | unsupported events, foreign or removed rows, bucket gaps, sampled corroboration, a retained report | conflict, missing order or identity fields, unlocated records, any mismatch, no corroboration, no coverage proof, no portable pages for a real or retained profile, inconsistent counts or an inconsistent "complete" claim |
| `POINT_IN_TIME_AVAILABILITY` | observed delivery and observed finality | assumed delay, finality inferred at collection | model unknown, observed delivery without finality |
| `SCHEDULE_FEASIBILITY` | declared floors fit the schedule's upper-bound count | none | floors undeclared or not met, or the rows are missing, malformed or contradictory |

Not assessed: `EXECUTION_ATTAINABILITY`, `TRADER_NET_FILL_OR_PROFIT`, `PROFITABILITY_OR_VALIDATION`. The result binds to the profile hash and the observations hash.

## Relation to P02

P02 is reused, not changed. Two findings need an owner decision:

1. P02 `token_order` is `[base, quote]`. It is not the pool's token0/token1 order. For MOE the pool order is `[WMON, MOE]` while P02 requires `[MOE, WMON]`. This profile keeps pool order in `pool_tokens` and derives P02 `token_order` in `research_binding_view()`. The P02 field name invites a swap error in any consumer that reads `token_order` as the pool order.
2. P02 `ResearchBinding.evidence_class` is `SYNTHETIC_FIXTURE` or `QUALIFIED_SOURCE`, and `qualification` is `QUALIFIED` or `UNQUALIFIED`. There is no state for a real source that is only limited. `to_p02_binding()` therefore projects a fixture as unqualified, projects a real profile only when the overall verdict is `QUALIFIED`, and raises `BindingNotEmittable` (`VERDICT_LIMITED`, `VERDICT_UNRESOLVED`) otherwise. A consumer must carry the P07 result beside any binding. Whether P02 gains a limited state is a builder decision.

## Retained MOE/WMON profile

`fixtures.json` holds the Probe A pool as a profile of class `RETAINED_REPORT`. It uses only published report figures: pool `0x97199b34…5aad`, token0 WMON `0x3bd359c1…433a` (quote), token1 MOE `0xd8e004ac…7777` (base), 18 decimals each, 26 pages, 26,146 swaps, four full samples matched against QuickNode, assumed delay 180 seconds, private manifest `b8f5cb33…261a`. Chain id 143 comes from Monad documentation, not from the report. A conflict count of 0 is inferred from "no duplicate, extra or missing identities". The report states no such count. The verdicts are in the table below. They are limits of what the portable record shows, not findings about the market.

| Claim | Verdict | Why |
|---|---|---|
| `BINDING_IDENTITY` | LIMITED | chain id from documentation, token order and venue label counted as single reads because the report gives no read count |
| `EVENT_AND_AMOUNT_MEANING` | UNRESOLVED | the report does not state that both pool sides were observed. Decimals not readable at the window start. Fork mechanics unqualified |
| `HISTORY_COMPLETENESS_AND_ORDER` | UNRESOLVED | no portable page table or coverage proof, no count of unsupported events. Corroboration is four samples of 26,146 |
| `POINT_IN_TIME_AVAILABILITY` | LIMITED | assumed 180-second delay. Original delivery and finality unknown |
| `SCHEDULE_FEASIBILITY` | UNRESOLVED | pool, period and decision schedule are not declared |

Reusing MOE for the first real qualification is a proposal. It is not a selection for production investigations. See the assessment for the sanitized extract that would move the first three claims.

## Verification and limits

Run from `docs/qualification/p07`: `python3 -B -m unittest -v test_p07`. The README lists the recipe. The evidence is kept in the assigned worktree and is not part of the commit. Seams under test: decode and convert, ingest, coverage assembly, bucketize, reference windows, availability and eligibility, schedule and feasibility, profile validation, binding comparison, qualification, and P02 projection. Fixtures were authored by `author_fixtures.py`, which does not import the module and writes hand-computed literals. Synthetic profiles use the invented chain id 999001, not a real one. A mutation script breaks 128 rules one at a time. All 128 break a test. Two seeded differential tests corrupt records and pages and check that no bucket reported complete holds a wrong trade count, that kept pages never contradict each other, and that relabeling pages changes nothing. Most internal review rounds and the first gate review found defects in earlier candidates. The repairs and their tests are in the evidence folder.

Not verified: any real provider behavior, the retained pages, the type checker (`mypy`, `ruff` and `pytest` are not installed and nothing was installed), Python versions other than 3.14.4, runtime cost, and anything about execution or profit.

## Decisions for the builder

1. Accept or change the profile shape, in particular `pool_tokens` in pool order and the claim list.
2. Decide how P02 should carry a limited real binding (finding 2 above) and rename or document `token_order` (finding 1).
3. Choose the pool, period and decision schedule for the first real qualification. MOE is the only pool with retained evidence.
4. Approve or refuse the access and request budget in the assessment. This document grants none.
