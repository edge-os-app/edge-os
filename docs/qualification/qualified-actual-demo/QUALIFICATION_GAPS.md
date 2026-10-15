# Qualified actual demo: qualification gaps (PROPOSED)

Task `QUALIFIED-DATA-PACKET-L4-20261015-LOCAL-v1` (#58, approved reduced demo connection work). Written on base `c34bd3959e51696193c1a031652a62fa67829e28`. Status: **PROPOSED. This document authorizes no operation.** No credential, provider, RPC, account, model or payment request was made to write it. Every actual item is `NOT_RUN`.

This document answers one question: what evidence would let the accepted P07 qualifier return `QUALIFIED` for an actual MOE/WMON dataset, so that the approved hypothetical replay can run? The [source-fact packet](SOURCE_FACT_PACKET.json), the [operating packet](OPERATING_PACKET.md) and the [demo evidence map](DEMO_EVIDENCE.md) build on it. The earlier [actual research operating packet](../actual-research-demo/OPERATING_PACKET.md) stays unchanged as history.

## 1. Status words

| Word | Meaning |
|---|---|
| `FIXED_BY_CODE` | The accepted code at `c34bd39` enforces it. |
| `RETAINED` | A dated fact from accepted Probe A evidence. It is valid only for its own date and scope. |
| `PUBLIC_DOC` | Current public documentation, read 2026-10-15. It describes a provider, not this account or this run. |
| `INFERENCE` | This document's reasoning. It is not evidence. |
| `SOURCE_FACT` | A fact only an actual read can give. The [source-fact packet](SOURCE_FACT_PACKET.json) names the read. |
| `NEW_CAPABILITY` | Needs code or a tool that does not exist at `c34bd39`. It needs a separately scoped implementation packet. |
| `NEEDS_APPROVAL` | A product or operation decision for the builder. |
| `NOT_RUN` | No actual run produced this evidence. |

## 2. Answer

Neither the existing one-hour MOE window nor any smaller window of past MOE history can reach `QUALIFIED` under the accepted rules. The first reason below blocks every retrospective window by itself. The second makes a past window-start read unreliable:

1. `POINT_IN_TIME_AVAILABILITY` is `QUALIFIED` only with observed delivery (`OBSERVED_DELIVERY`, basis `SOURCE_DELIVERY_RECORD`) and observed finality (`OBSERVED_FINAL`). Nobody recorded when a past bucket was first delivered. Collection time is refused as delivery evidence (`check_availability_model`, `COLLECTION_TIME_IS_NOT_DELIVERY`).
2. `EVENT_AND_AMOUNT_MEANING` needs a decimals read at the window start. QuickNode documents its Monad mainnet endpoint as "Archive: Yes" with "Over 40,000 recent blocks available" (`PUBLIC_DOC`, [QuickNode Monad](https://www.quicknode.com/docs/monad), read 2026-10-15). At 300 ms per block, 40,000 blocks is about 3.3 hours, and "over" makes this a lower bound (`INFERENCE`). Probe A's start-boundary calls for Sep 24 returned historical-state-unavailable errors, while its reads at the Oct 2 window end succeeded later (`RETAINED`; the exact age of that state is not recorded). The real horizon is therefore unknown. The forward route schedules every state read within one hour of its block.

The smallest credible route is a **forward window**: choose a 20-minute MOE/WMON window before it starts, observe its facts while it happens, then collect it through the application. This route also needs MOE token mechanics to qualify, a larger owner request cap, and several builder decisions. Even then, the accepted replay engine cannot fill an order on a dataset whose delivery is observed after bucket end (section 5.5). Section 6 lists the exact missing proofs. Nothing here marks the demo ready.

## 3. What `QUALIFIED` requires in code

`qualify` (`docs/qualification/p07/qualification.py`) gives the overall verdict of the worst claim. Every claim must be `QUALIFIED`.

| Claim | Needed for `QUALIFIED` | Weaker result and its code |
|---|---|---|
| `BINDING_IDENTITY` | Chain id source `PROVIDER_READ`; `pool_tokens` `CORROBORATED_READ`; `pool_venue` `CORROBORATED`; evidence class not `RETAINED_REPORT` (lines 1293-1299) | `SINGLE_READ`, `SINGLE_SOURCE`: `LIMIT`. Anything else: `MISSING_EVIDENCE` |
| `EVENT_AND_AMOUNT_MEANING` | At least one trade; both pool sides seen; decimals `window_start` `READ` for base and quote; `fee_transfer_semantics` `QUALIFIED` | One side: `LIMIT ONE_POOL_SIDE_ONLY` (line 1311). Only later reads: `ASSUMPTION DECIMALS_IMMUTABILITY_ASSUMED` (line 1318). No read: `MISSING_EVIDENCE`. Mechanics: `LIMIT TOKEN_MECHANICS_UNQUALIFIED` (line 1322) |
| `HISTORY_COMPLETENESS_AND_ORDER` | Zero conflicts, unsupported, removed, foreign and unlocated records; `PAGE_DIGESTS` revision; every bucket `COMPLETE_*`; corroboration `COMPLETE` with sample = population ≥ trades and zero mismatches | Bucket gaps `LIMIT BUCKET_GAPS` (line 1378). Sample: `LIMIT CORROBORATION_SAMPLED_ONLY` (line 1396) |
| `POINT_IN_TIME_AVAILABILITY` | Model `OBSERVED_DELIVERY` with `SOURCE_DELIVERY_RECORD`, and finality `OBSERVED_FINAL` | `ASSUMED_DELAY`: `ASSUMPTION` (line 1408). `FINALIZED_BY_DEPTH`: `ASSUMPTION` (line 1412) |
| `SCHEDULE_FEASIBILITY` | Declared floors and status `FEASIBLE` with consistent rows and zero shortfall | No floors: `MISSING_EVIDENCE SCHEDULE_OR_SAMPLE_FLOOR_UNDECLARED` (line 1428) |

`qualify` decides `POINT_IN_TIME_AVAILABILITY` from the profile's availability model and `finality_at_collection` only (lines 1398-1417). It never reads `delivery_records`. Those records only set each bucket's `available_at` (`history_normalizer._bucket_views`); a missing record gives `available_at` null with `DELIVERY_NOT_RECORDED`, and the verdict is unchanged. So a profile that declares `OBSERVED_DELIVERY` with a missing record can still be `QUALIFIED`. The [source-fact packet](SOURCE_FACT_PACKET.json) therefore allows `OBSERVED_DELIVERY` only when every bucket has a record.

The application passes release `provider_facts` into `normalize` unchanged and labels them `RELEASE_DECLARATION` (`research/native_history_collection.py`, `core/research/released_source_runtime.py`). Nothing in the code checks a declaration. A false declaration gives a false `QUALIFIED`. Only review of the release definition, with the evidence named below, prevents that. `market_adoption` (line 90) and the replay simulator (`replay/simulator.py` line 190) admit only an overall `QUALIFIED`, complete dataset.

## 4. Requirement matrix for MOE/WMON

Pool `0x97199b34564911936bc850ac45ede785892b5aad` (token0 WMON `0x3bd359c1119da7da1d913d1c4d2b7c461115433a`, token1 MOE `0xd8e004acba279417c04c0633cb5a21ceca207777`), chain 143. The "Settled now" column says what public documentation or retained evidence already settles. The "Missing" column names the exact proof still needed.

| Fact | Needed proof | Settled now | Missing | Kind |
|---|---|---|---|---|
| Chain id | `eth_chainId` = 143 from the corroboration provider during the run | Code reads it in every run (`read_chain_id`) | Nothing before the run | `FIXED_BY_CODE` |
| Pool tokens | Two independent sources agree on token0 and token1 | Probe A RPC `token0`/`token1` reads, dated (`RETAINED`, one source) | A second, independent source. Proposed: the venue's pool-creation log from HyperSync, compared with a QuickNode `token0`/`token1` read | `SOURCE_FACT` |
| Pool venue | Two independent sources agree that the pool belongs to the venue | Probe A registry, creation receipt and Kuru index match, dated (`RETAINED`) | A current pair of reads: the creation receipt (QuickNode) and the creation log (HyperSync). The builder decides whether the dated pair suffices | `SOURCE_FACT`, `NEEDS_APPROVAL` |
| Orientation | `QUOTE_PER_BASE`, WMON per MOE | Proposed earlier | Builder approval | `NEEDS_APPROVAL` |
| Decimals at window start | `decimals()` `READ` for MOE and WMON at the window's first block | Probe A read 18 at its own window end and current time (`RETAINED`). Its start-boundary reads failed | `eth_call` at the window-start block, within one hour of that block (the real pruning horizon is unknown, section 2). The existing release allowlist refuses `eth_call` (`RPC_METHODS`) | `SOURCE_FACT` |
| Decimals at window end and current | Two more `READ` values | Same as above | Two reads per token after the window | `SOURCE_FACT` |
| Fee and transfer mechanics | `fee_transfer_semantics` `QUALIFIED` | MOE has a reflection-reward design (project site, `RETAINED`). Fork fees unqualified | (a) MOE bytecode hash; (b) verified source that matches it; (c) a written mechanics finding, for example whether the pair is excluded from reflection; (d) a builder-approved definition of `QUALIFIED` mechanics. Reflection credited to the pair can enter V2 `Swap` input amounts. That is an `INFERENCE` to check, not a finding | `SOURCE_FACT`, `NEEDS_APPROVAL` |
| Both pool sides | At least one `QUOTE_IN_BASE_OUT` and one `BASE_IN_QUOTE_OUT` trade in the window | Probe A saw two-sided swaps across its period (`RETAINED`) | Observed in the run itself. If one side is missing, the run is `LIMITED` and replay is refused | Run outcome |
| Event decoding | V2 `Swap` topic0 `0xd78ad95f…d822`; zero unsupported shapes | Probe A corrected V2 signature (`RETAINED`) | Observed in the run | Run outcome |
| Completeness and order | Pages tile the scan; zero conflicts; every bucket proven | Code computes it (`assemble_segments`, `bucketize`) | Scan block range that starts before the window and ends after it | `SOURCE_FACT` |
| Corroboration | `COMPLETE`: one receipt per record, zero mismatches | Code: `_sample_indices` returns every record when `sample_size ≥ population` | Records ≤ 61 in the whole scan, and the request budget in section 5 | Run outcome plus approval |
| Availability | `OBSERVED_DELIVERY`, declared only when every bucket has a delivery time (the code does not check this) | None. No past MOE bucket has a delivery record | A forward recorder that reads HyperSync after each bucket closes and keeps the time of the first covering reply it received. That time is an upper bound on when the data became available. A contract reading that this time is a `SOURCE_DELIVERY_RECORD` and not collection time | `NEW_CAPABILITY`, `NEEDS_APPROVAL` |
| Finality | `OBSERVED_FINAL` | Monad maps the `finalized` RPC tag to MonadBFT `Finalized` blocks, which "cannot be reverted without a hard fork" (`PUBLIC_DOC`, [block states](https://docs.monad.xyz/monad-arch/consensus/block-states), read 2026-10-15) | One `eth_getBlockByNumber("finalized")` read after the window. Its number must be at least the window's last block plus 2 (`depth_blocks`). Carrying that observation forward to the later collection is an `INFERENCE` from irreversibility | `SOURCE_FACT`, `NEEDS_APPROVAL` |
| Archive height and collection time | Declared before the run; the height is at least the last scanned block plus 2; collection time is not before the window end | Contract section 9 keeps `collected_at_utc` open | The same post-window reads. The builder decides which observed time is declared | `SOURCE_FACT`, `NEEDS_APPROVAL` |
| Feasibility | Floors declared; `FEASIBLE` | `feasibility()` computes slots from the claim | Floors are a builder decision. Section 5.3 shows a schedule that fits | `NEEDS_APPROVAL` |

## 5. Options compared

### 5.1 Activity counts used for sizing

The figures below are sanitized aggregates of the retained Probe A identity metadata (metadata SHA-256 `492cb7795392c63049e7bb726f4201ffa2fc83f28ad4cc9e697899407764891a`). They use identities and timestamps for Sep 25 only. No amount, price or return was read. The read stopped before Sep 26 records, so the sealed validation (Sep 28 to Sep 30) and holdout (Sep 30 to Oct 2) partitions stayed unread.

| Window length on Sep 25 | Windows checked | Fewest records | Median | 90th percentile | Most | Windows with ≤ 61 records |
|---|---:|---:|---:|---:|---:|---:|
| 15 min | 286 | 11 | 22 | 35 | 51 | 286 |
| 20 min | 285 | 16 | 30 | 47 | 72 | 283 |
| 30 min | 283 | 26 | 45 | 70 | 95 | 231 |
| 60 min | 277 | 56 | 90 | 143 | 163 | 3 |

Sep 25 had 2,348 swaps and no empty five-minute bucket. The proposed hour `12:00` to `13:00` held 93 swaps. Current MOE activity is unknown. These counts size a proposal. They do not predict a future window.

### 5.2 The request ceiling

`HistoryResourceBounds.provider_requests` allows at most 64. `_check_history` needs `max_pages + 1 + corroboration_sample_size ≤ provider_requests`. With `max_pages` 2, the largest sample is 64 − 2 − 1 = 61. A window with more than 61 records cannot get `COMPLETE` corroboration. The one-hour window needs at least 93 + 1 + 1 = 95 requests, so it cannot.

### 5.3 Options

| Option | Binding | Event meaning | Completeness | Availability | Feasibility | Best overall |
|---|---|---|---|---|---|---|
| A0. Existing hour, Sep 25 12:00-13:00, existing allowlist | `LIMITED` | `UNRESOLVED` (no decimals read) | `LIMITED` (8 of 93 sampled) | `LIMITED` | `UNRESOLVED` | `UNRESOLVED` |
| A1. MOE, Sep 25, 20 or 30 minutes, 61 receipts, any source-fact packet | `QUALIFIED` possible with corroborated reads | `LIMITED` at best: Sep 25 is far outside the documented pruning horizon, so a window-start decimals read is expected to fail as in Probe A; mechanics open | `QUALIFIED` possible when records ≤ 61 | `LIMITED`: no delivery record exists | `FEASIBLE` possible with floors | `LIMITED` |
| **B. MOE forward 20-minute window (recommended)** | `QUALIFIED` possible | `QUALIFIED` only if mechanics qualify and both sides appear | `QUALIFIED` possible when records ≤ 61 | `QUALIFIED` possible with a recorder and an accepted contract reading | `FEASIBLE` with floors 1 and 1 | `QUALIFIED` possible; `LIMITED` if mechanics stay open |
| C. CHOG/WMON pool `0x116e7d070f1888b81e1e0324f56d6746b2d7d8f1` (retained alternative) | Not assessed | Refused: its Swap topic0 `0xc42079f9…ca67` is the V3 `Swap` shape. The P07 decoder supports `uniswap-v2-swap/1` only | Not assessed | Same as A or B | Not assessed | Not admissible without a new decoder (`NEW_CAPABILITY`) |
| D. Kuru CLOB markets (retained) | Not assessed | Refused: Kuru `Trade` events are not V2 `Swap` | Three trades in Sep 18 to Oct 2 | Not assessed | Not reachable | Not admissible |

Option C facts come from `C2-activity-selection-02` (`RETAINED`): 4,649 swap-topic events from Sep 18 to Oct 1, 1,332 occupied and 2,703 missing five-minute buckets, about 181 events on Sep 25. Its lower activity would suit complete corroboration, but the decoder refuses its events. The CHOG validation and holdout counts were never used here.

**Recommended window shape for option B (`PROPOSED`).** 20 minutes, `[T0, T0 + 1,200 s)`, with `T0` on the five-minute grid and chosen before it starts. Four buckets. Feasibility claim: schedule anchor `T0`, period 300 s, feature offset 0 s, horizon 300 s, reference window 300 s, warm-up 0 buckets, one `DESCRIPTIVE` partition `[T0, T0 + 1,200 s)`. The scan starts at the last block before `T0`. `feasibility()` then gives 4 slots. The slot at `T0` fails warm-up coverage, because `[T0 − 300 s, T0)` is not scanned. The slot at `T0 + 900 s` fails the outcome window (900 + 300 + 300 > 1,200). Two slots are usable. Floors of 1 triggered and 1 control give `required_total` 2, shortfall 0 and status `FEASIBLE`. A 30-minute window gives 4 usable slots. A scan that starts 301 s before `T0` adds one usable slot but also adds the records of those 5 minutes to the corroboration population. The same claim under `ASSUMED_DELAY` 180 s gives 0 usable slots, because the delay exceeds the 0 s feature offset (line 780). These counts come from running the accepted `feasibility()` locally on a synthetic segment, with no provider data. They depend on actual page coverage in the run.

Floors of 1 and 1 give no statistical support. They only make the schedule declarable. The replay that follows is a labelled hypothetical demonstration, not evidence of an edge.

### 5.4 Capacity for option B

| Resource | Value | Basis |
|---|---|---|
| Blocks in 20 minutes | 3,000 to 4,000 | 300 ms minimum block time, 400 ms before MIP-12 (`PUBLIC_DOC`, retained in [EVIDENCE_MAP.md](../actual-research-demo/EVIDENCE_MAP.md) section 5) |
| HyperSync pages | 1 expected, `max_pages` 2 | `max_blocks_per_page` 10,000 |
| Reply bytes | About 0.5 MB: 4,000 headers at about 120 B plus 61 logs at about 700 B | `INFERENCE`, same per-item sizes as the earlier packet. A larger wire size stops at the byte cap |
| Provider requests | 2 + 1 + 61 = 64 | Schema ceiling 64 |
| Owner request cap | 64 history + 2 Nansen = 66 needed; default is 16 | `core/settings.py` line 71. Caps freeze at first use. Raising it is a settings change outside this lease (`NEEDS_APPROVAL`) |
| Compute and deadline | 600 s history + 300 s Nansen = 900 s, equal to the default owner cap | `HistoryResourceBounds` |
| QuickNode credits | Run: 62 calls × 30 = 1,860. Source facts: at most 18 × 30 = 540 | 30 credits per Monad method (`PUBLIC_DOC`, [QuickNode credits](https://www.quicknode.com/api-credits/monad)) |

### 5.5 Replay timing on an observed-delivery dataset

The replay engine evaluates each decision at `moment = bucket_end` (`replay/simulator.py` line 492). A pending order fills at that bucket's close, and `_account_mark` refuses a mark whose `available_at` is later than the moment (`LATE_INPUT`, lines 363-364). Under `OBSERVED_DELIVERY`, `available_at` is `max(bucket end, delivery time)` (`bucket_available_at`, `qualification.py` lines 676-680). The recorder sees a bucket at the earliest 30 s after its end. Every mark is then late, every pending order is saved as `FILL_UNAVAILABLE`, and a replay on a `QUALIFIED` option-B dataset saves no fill (`INFERENCE` from reading the code; the replay was not run). The same holds for `ASSUMED_DELAY` with any positive delay.

`feasibility()` hides this, because it treats observed delivery as ready at bucket end (docstring, lines 743-744). The 2 usable slots in section 5.3 count opportunities, not fillable orders.

This is not a defect report: refusing a close that was not yet available is the conservative choice. A replay that fills needs a design change outside this lease, for example filling at a later mark that was available by the moment. That change is a `NEW_CAPABILITY` for the replay owner and a builder decision. This document proposes no change to the engine.

## 6. Exact missing proofs and the smallest next proposal

For option B to reach `QUALIFIED`, all of these are needed. None exists today.

1. **Forward recorder (`NEW_CAPABILITY`).** A separately scoped, reviewed tool that runs the [source-fact packet](SOURCE_FACT_PACKET.json) phases P1 to P6 on a fixed schedule, enforces its stop rules and saves hashed results without credentials. The existing application cannot do it: the release allowlist refuses `eth_call` and `eth_getBlockByNumber`, and release facts freeze before a run.
2. **Delivery-record reading (`NEEDS_APPROVAL`).** The builder and the P07 contract owner confirm that "the first HyperSync reply that covers a bucket, received by the recorder" is a `SOURCE_DELIVERY_RECORD`, and that all 4 buckets need one. If they refuse, availability stays `LIMITED` and the demo cannot be `QUALIFIED` on any route in this document.
3. **Decimals and identity reads (`SOURCE_FACT`).** Phases P1, P4 and P5 of the source-fact packet.
4. **Finality read (`SOURCE_FACT`).** Phase P5. The builder accepts the irreversibility inference.
5. **MOE mechanics (`SOURCE_FACT`, `NEEDS_APPROVAL`).** Phase P6 and a written finding. If MOE mechanics cannot qualify, the next proposal is a builder decision on another V2-compatible pool with plain ERC-20 tokens. Probe A excluded major and stablecoin pairs. No retained alternative fits the V2 decoder.
6. **Run outcomes.** At most 61 records, both pool sides, zero conflicts, unsupported events and mismatches. These are unknown until the run.
7. **Owner request cap ≥ 66 (`NEEDS_APPROVAL`).**
8. **Feasibility floors and schedule (`NEEDS_APPROVAL`).**
9. **Replay fills (`NEW_CAPABILITY`, `NEEDS_APPROVAL`).** Section 5.5. Without a replay design change, the approved replay runs but saves no fill. The builder decides whether a saved replay with only `FILL_UNAVAILABLE` events meets the demo goal.

If any of items 1 to 6 fails as an evidence outcome of the source-fact packet, the honest result is a saved `LIMITED` or `UNRESOLVED` dataset and a saved replay refusal. A missing delivery record, for example, leads to `ASSUMED_DELAY` 180 s and `UNRESOLVED` through `INFEASIBLE_BEFORE_OUTCOMES`. A safety stop gives no dataset at all. That is valid evidence but does not meet the approved demo scope. The builder then decides between that evidence and further work. This document proposes no change to a verdict rule.

## 7. Builder decisions, once facts exist

1. Approve option B, or keep option A0 and accept `UNRESOLVED`.
2. Approve the forward recorder as a separately scoped implementation, with its own review.
3. Accept or refuse the delivery-record reading (section 6, item 2).
4. Approve the source-fact packet as an operation, with its call ceilings.
5. Define what qualifies MOE token mechanics, after phase P6 evidence exists.
6. Approve orientation `QUOTE_PER_BASE`, the 20-minute window shape, the floors and the owner cap.
7. Approve publishing the scan block numbers, the pool-creation transaction and the QuickNode host. The release makes them public in `release_view`.
8. Decide how to treat replay fills (section 5.5).

[OPERATING_PACKET.md section 9](OPERATING_PACKET.md#9-decisions-the-builder-makes-once-facts-exist) gives these decisions the ids D1 to D11.
