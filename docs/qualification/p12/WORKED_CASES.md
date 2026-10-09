# P12 independent worked cases

These cases are independently hand-calculated from the proposed rules in `docs/contracts/p12/README.md`. They are synthetic accounting examples, not market evidence, user defaults, qualified fills, or profitability claims. Quote asset `Q`, base asset `B`, capital, prices and costs are invented. WC-01 through WC-05 use a synthetic saved fee rate `0.001` (10 bps) and slippage rate `0`; both would be stored in the hypothetical P02 revision with `source_ref: "synthetic-case-input"`. Cost rates are fractions; bps are display only. Values are shown without display rounding; division results are exact where terminating and otherwise shown as fractions.

## WC-01 — next-bucket timing, fees and full exit

Assumptions for this case only on 2026-10-01 UTC: start with `1,000 Q`; fixed entry size `400 Q`; saved fee `0.001`; saved slippage `0`; no deposits or withdrawals. The close and mark observations are synthetic, qualified, and available at the timestamps shown. In particular, the 12:15 valuation mark is `9 Q/B`, its bucket ends at 12:15 UTC, and the fixture's availability model makes it usable at 12:15 UTC.

The saved rule is `entry: price() > 7 Q/B`, `exit: price() >= 9 Q/B`, `invalidation: NOT_REQUESTED`, `additions=false`, `partial_exits=false`. Decision observations are 12:05=`8 Q/B`, available 12:05, and 12:15=`9 Q/B`, available 12:15. Fill closes are 12:10=`8 Q/B`, available 12:10, and 12:20=`10 Q/B`, available 12:20. All times are UTC; the close at 12:15 is both the exit-decision observation and the own-bucket mark.

| UTC event | Known input / action | Cash Q | Reserved Q | Holdings B | Reserved B | Account value Q |
|---|---|---:|---:|---:|---:|---:|
| 12:00 | Initial capital | 1,000 | 0 | 0 | 0 | 1,000 |
| 12:05 | Entry signal is usable at the bucket end; reserve `400 + .4`; no same-bucket fill | 1,000 | 400.4 | 0 | 0 | 1,000 |
| 12:10 | Next-bucket close fill at `8 Q/B`; buy `400/8 = 50 B`; pay `.4 Q` fee | 599.6 | 0 | 50 | 0 | 999.6 |
| 12:15 | Qualified mark `9 Q/B`, available 12:15; exit signal is usable at bucket end; reserve all `50 B`; no same-bucket fill | 599.6 | 0 | 50 | 50 | 1,049.6 |
| 12:20 | Next-bucket close fill at `10 Q/B`; sell all `50 B`; gross `500 Q`; pay `.5 Q` fee | 1,099.1 | 0 | 0 | 0 | 1,099.1 |

Reconciliation: buy cash change `-400.4 Q`; sell cash change `+499.5 Q`; net gain `99.1 Q`; account-value gain `1,099.1 - 1,000 = 99.1 Q`. The 12:05 signal cannot fill at the signal bucket's close. The 10 Q/B fill is an explicit close-price proxy, not an executable fill claim.

## WC-02 — hypothetical reservation conformance and insufficient cash

This stand-alone accounting conformance case does not create strategy instances, slots, or production shared-capital semantics. It shows the arithmetic needed if a separately adopted shared-capital portfolio were ever supported. Start with `500 Q`. Two independent synthetic reservation requests, `request-a` and `request-b` (not two instances of the same revision), each request `300 Q` plus `0.3 Q` fee. Both use the same next-bucket `5 Q/B` close.

1. Exit processing has no eligible exits. For this hypothetical conformance calculation only, requests sort by their declared stable request labels, so `request-a` reserves `300.3 Q` first.
2. Free cash becomes `500 - 300.3 = 199.7 Q`. `request-b` requires `300.3 Q`, so it receives `INSUFFICIENT_CASH`; the requested size is not reduced.
3. At the next bucket close, `request-a` buys `300/5 = 60 B`; fee is `0.3 Q`; cash is `199.7 Q`; reservations are zero; holdings are `60 B`; account value at the `5 Q/B` fill mark is `499.7 Q`.

Reconciliation: reserved and spent quote is `300 + 0.3 = 300.3 Q`; uncommitted cash is `199.7 Q`; no cash is reserved twice; the second request creates no fill or fee. Reversing the request labels changes which hypothetical request wins. This example is not evidence that the current P02 strategy or runtime accepts multiple positions. No P12 production slot mechanism is proposed.

## WC-03 — partial exit arithmetic, explicitly unsupported in the recommended subset

This is an accounting conformance illustration only. Accepted P02 uses `partial_exits: false`, so it does not enable partial exits in the replay profile. A request with partial exits is explicitly unavailable under that contract. Synthetic UTC events: at 2026-10-01 12:00 start with `1,000 Q`; at 12:05 a qualified/available next-bucket close of `8 Q/B` fills a `400 Q` buy with fee `0.4 Q`, acquiring `50 B`; at 12:15 a qualified/available close of `10 Q/B` fills a hypothetical `20 B` partial sale, fee `200 × .001 = 0.2 Q`; at 12:20 a qualified/available `9 Q/B` valuation mark values the remaining `30 B`.

- Cash after buy: `1,000 - 400 - 0.4 = 599.6 Q`.
- Buy basis including entry fee: `400.4 Q`; weighted basis `400.4 / 50 = 8.008 Q/B`.
- Partial sale gross: `20 × 10 = 200 Q`; net proceeds `199.8 Q`.
- Realized result with proportional entry-fee allocation: `199.8 - (20 × 8.008) = 39.64 Q`.
- Remaining basis: `30 × 8.008 = 240.24 Q`; ending marked value: `30 × 9 = 270 Q`; unrealized result: `29.76 Q`.
- Ending cash `799.4 Q`; ending account value `799.4 + 270 = 1,069.4 Q`; gain `69.4 Q = 39.64 + 29.76 Q`.

The example fulfills an independently calculated accounting check only. It does not show that the simulator accepts or executes a partial exit. The proposed one-position profile returns an explicit unsupported/unavailable result for a request with partial exits. If the builder reads P12 acceptance as requiring runtime partial-exit support, that is expanded simulator behavior and needs an explicit strategy/profile decision before implementation; this arithmetic alternative cannot silently stand in for it.

## WC-04 — open inventory, missing mark and missing fee

After the `400 Q` buy in WC-01, cash is `599.6 Q` and inventory is `50 B`.

- If the end mark is qualified at `9 Q/B`, inventory is worth `450 Q`; account value is `1,049.6 Q`. It remains open inventory, not realized proceeds.
- If the required end mark is missing, cash `599.6 Q` and inventory `50 B` remain known, but account value, total gain/loss and drawdown are unavailable with the mark reason. No prior mark is carried forward.
- If the saved fee/slippage model or required `source_ref` is missing or unusable, or the P12 cost rule has not been adopted, the run is unavailable before any simulated action. It does not substitute zero. Gas and other excluded costs cannot be described as included in net performance.

## WC-05 — units and drawdown

One sampled account series in `Q` is `1,000`, `999.6`, `1,049.6`, `1,020`. The high-water marks are `1,000`, `1,000`, `1,049.6`, `1,049.6`. The absolute peak-to-trough falls are `0`, `.4`, `0`, `29.6 Q`; largest drawdown is `29.6 Q`. This is not a percent return, daily statistic or annualized measure. If any required sample is unavailable, the maximum for the full interval is unavailable.

## WC-06 — compiler result is separate from action eligibility

Frozen synthetic input `eligibility-case/1`: strategy is one P06-valid saved revision whose entry is `price() > 100 Q/B OR quote_volume() > 0 Q`; exit is `FALSE`; invalidation is explicit `NOT_REQUESTED`; `warmup_buckets=0`. At `2026-10-01T12:00:00Z`, the scheduled price is qualified `110 Q/B`, available at 12:00; scheduled quote volume is absent with reason `MISSING_QUOTE_VOLUME`. The complete Boolean tree validates. P06 returns calculated `TRUE` and retains `MISSING_QUOTE_VOLUME`; that exact result is not rewritten to `UNKNOWN`. Under the proposed P12 action gate, this opportunity is ineligible because the result carries an unresolved observation reason. No order/reservation/fill occurs. Cash remains `1,000 Q`, inventory `0 B`; mark/account value are `1,000 Q` if the qualified 12:00 mark is available. This gate is proposed P12 behavior and needs adoption; it grants no general readiness.

The same fixture includes `price_return(2)` with scheduled prices at 11:50=`100 Q/B` (qualified/available), 11:55=missing (`COMPLETE_EMPTY`, no close), and 12:00=`110 Q/B` (qualified/available). P06 returns `110/100 - 1 = 0.1` with the 11:55 coverage reason. P12 records that value/reason unchanged; the proposed conservative gate blocks an action while any observation reason remains. This does not convert the accepted endpoint result to UNKNOWN.

## WC-07 — late, future and proven-empty decision inputs

One flat strategy on 2026-10-01 UTC, start `1,000 Q`, entry `price() > 100 Q/B`, exit `FALSE`, invalidation `NOT_REQUESTED`, fixed size `100 Q`, saved fee `0.001`, slippage `0`; no outstanding orders. The bound synthetic dataset has complete coverage status for all rows. Decision times and inputs:

| Decision UTC | Observation | P06 outcome / reason | P12 action / order | Cash Q; inventory B |
|---|---|---|---|---|
| 12:00 | Current price `110`, bucket end 12:00, but source delivery is 12:02 (`available_at=12:02`) | `UNKNOWN`, `FUTURE_INFORMATION` at 12:00; do not relabel delivery as 12:00 | Ineligible; no reserve/fill | 1,000; 0 |
| 12:05 | Rule references the scheduled 12:10 price `110 Q/B`, available 12:10; it is later than this decision | `UNKNOWN`, `FUTURE_INFORMATION`; the later point cannot be relabelled or hidden by a decisive sibling | Ineligible; no order | 1,000; 0 |
| 12:10 | Price bucket is `COMPLETE_EMPTY`; there is no close; volume is proved zero; availability is 12:10 | `price()` is `UNKNOWN`, `EMPTY_BUCKET_NO_CLOSE`; volume expression, if used, returns exact zero | Ineligible; no order | 1,000; 0 |

No close is inferred for the empty price bucket. By contrast, an `INCOMPLETE` 12:10 bucket means coverage is unproved; reject dataset admission if it breaks proof of the requested interval, otherwise block this opportunity with `COVERAGE_NOT_PROVEN`, not `EMPTY_BUCKET_NO_CLOSE`. At 12:10, account value remains 1,000 Q only if that bucket's own mark is independently qualified/available; otherwise retain known cash and set value unavailable.

## WC-08 — late next-bucket close releases reservation

Inputs on 2026-10-01 UTC: `[12:00,12:20)` window, one flat strategy, start `1,000 Q`, fixed entry `100 Q`, saved fee `0.001`, slippage `0`, `entry: price() > 4 Q/B` with decision price `5 Q/B` qualified/available at 12:00; `exit: FALSE`; invalidation `NOT_REQUESTED`. The next bucket ends at 12:05 with close `5 Q/B`, but observed source delivery makes `available_at=12:07`. At 12:00, reserve `100.1 Q`; free cash is `899.9 Q`; inventory is zero. At scheduled fill time 12:05 the required close is late, so no order fills, the result records `LATE_INPUT` with `available_at=12:07`, and reservation is released at 12:05; known cash returns to 1,000 Q and inventory remains zero. The late 5 Q/B value is never backdated. No entry signal is carried into 12:07. A fresh scheduled decision at/after 12:10 would require its own eligible inputs. If 12:05 were `COMPLETE_EMPTY`, reason would be `EMPTY_BUCKET_NO_CLOSE`; if incomplete/unqualified, preserve that distinct reason.

## WC-09 — NO_NEXT_BUCKET and exclusive run end

Inputs: evaluation window `[2026-10-01T12:00:00Z, 2026-10-01T12:10:00Z)`, start cash `1,000 Q`, no inventory, fixed entry `100 Q`, fee `0.001`, slippage `0`, `entry: price() > 4 Q/B` with qualified/available 12:05 decision price `5 Q/B`; exit FALSE; invalidation `NOT_REQUESTED`. A next-bucket close would occur at 12:10 exactly, but that timestamp is the exclusive end. The proposed rule records the entry opportunity and `NO_NEXT_BUCKET` at 12:05 before reserving; no fill, no pending reservation crosses the end. At 12:10 there is no decision, fill or mark in this run. Final known balances are cash `1,000 Q`, inventory `0 B`. If the strategy instead held `10 B` at the end, known cash/base would still be retained but final account value, gain/loss and drawdown would be unavailable absent a qualified in-window valuation mark; do not value at the exclusive-end close or carry the 12:05 mark forward.

## WC-10 — repeat calculation identity and complete reconciliation

Fixture identity tuple (synthetic and documentation-only): strategy revision `synthetic-strategy-wc10-v1`; dataset revision `synthetic-dataset-wc10-v1`; run configuration `synthetic-config-wc10-v1`; calculation profile `p12.spot-replay/1`. The saved strategy rules are `entry: price() > 7 Q/B`, `exit: price() >= 9 Q/B`, `invalidation: NOT_REQUESTED`, fixed entry size `400 Q`, `additions=false`, `partial_exits=false`, saved fee `0.001`, saved slippage `0`, `source_ref="synthetic-wc10"`. Start cash is `1,000 Q`; scheduled decision closes and availability are 12:00=`8 Q/B` available 12:00, 12:05=`8` available 12:05, 12:10=`8` available 12:10, 12:15=`9` available 12:15, 12:20=`10` available 12:20 UTC on 2026-10-01. These are the only required inputs; no quote-volume dependency, capital flow or missing observation exists. Entry at 12:05 and full exit at 12:15 are TRUE and available. Run the same ordered input identities twice. Expected output both times: initial `1000 Q`; reserve `400.4 Q`; buy `50 B`, cash `599.6 Q`, basis `400.4 Q`; 12:15 mark value `1049.6 Q`, exit reservation `50 B`; sell gross `500 Q`, fee `.5 Q`, final cash/value `1099.1 Q`, completed pairs `1`, gain `99.1 Q`. Every record order, reason list (empty), cost source, fill and metric must match. This is an independent arithmetic repeat, not proof of runtime serialization, storage or retrieval. The labels are exact synthetic fixture identities, not cryptographic hashes or production database IDs.

## WC-11 — valid Boolean invalidation is not silently dropped

Synthetic strategy input at `2026-10-01T12:00:00Z`: P06-valid `invalidation = price() < 5 Q/B`, `entry = price() > 100 Q/B`, `exit = FALSE`, fixed quote size `100 Q`, `additions=false`, `partial_exits=false`. At 12:00 the qualified/available price is `4 Q/B`; the Boolean invalidation calculation is `TRUE`. P06 accepts and preserves this rule. The proposed P12/1 subset rejects the exact revision before replay with `UNSUPPORTED_INVALIDATION`, retains the original revision/field/value, and creates no order/reservation/fill. Start cash `1,000 Q`, inventory `0 B` remain known. This is a proposed subset boundary, not a P06 rejection and not a choice that invalidation means an exit or entry stop.

## WC-12 — saved fractional fee and slippage mapping

Synthetic accepted strategy cost fields: `fee_rate="0.003"`, `slippage_rate="0.005"`, `source_ref="synthetic-cost-source"`; on 2026-10-01 UTC start `1,000 Q`, decide a `400 Q` buy at 12:00 and fill at the 12:05 next-bucket close `8 Q/B`; decide a full exit at 12:10 and fill at the 12:15 next-bucket close `10 Q/B`. Both closes are qualified/available at fill time. No run override. The exact saved rates are retained. Display-only conversions are 30 bps fee and 50 bps slippage. Buy fill is `8 × 1.005 = 8.04 Q/B`; acquired base is `400/8.04 = 10000/201 B`; buy fee is `400 × .003 = 1.2 Q`; post-buy cash is `598.8 Q`; basis is `401.2 Q`. Sell fill is `10 × .995 = 9.95 Q/B`; gross is `(10000/201) × 9.95 = 99500/201 Q`; sell fee is gross × `.003 = 298.5/201 Q`; net proceeds are `99201.5/201 Q`; this equals `198403/402 Q`. Realized net over the `401.2 Q` basis is `185603/2010 Q`. Final cash is `598.8 + 198403/402 = 1092.339800995024875621890547... Q`; gain is final cash minus `1,000 Q`, the same `185603/2010 = 92.339800995024875621890547... Q`. This reconciles with both fees and adverse price adjustments; no gas/spread/other costs are included. It is a formula check only, not a venue estimate.

## WC-13 — coincident exit/entry while open, then settle before flat decision

Synthetic inputs on 2026-10-01 UTC: one instance, start `cash=0 Q`, `inventory=10 B`, basis `80 Q`; fee `.001`, slippage `0`; fixed entry size `50 Q`; `entry: price() > 5 Q/B`, `exit: price() > 5 Q/B`, invalidation `NOT_REQUESTED`; decision prices are 12:00=`8 Q/B` and 12:05=`10 Q/B`, qualified and available at each timestamp. Next-bucket closes are 12:05=`11 Q/B` and 12:10=`4 Q/B`, qualified/available at those times. At 12:00, both entry and exit are TRUE while open. Exit-first ordering reserves exactly `10 B`; it does not create an entry/reserve quote. At 12:05, the previous exit settles first at `11 Q/B`: gross `110 Q`, fee `.11 Q`, cash `109.89 Q`, inventory `0 B`, reservation `0`. Then the 12:05 signal is evaluated while flat. Its entry and exit predicates are both TRUE, but the flat-state rule creates only the eligible entry: reserve `50 + .05 = 50.05 Q`; no exit can reserve absent inventory. At 12:10, next close `4 Q/B` is available; buy `50/4=12.5 B`, fee `.05 Q`; cash `59.84 Q`, inventory `12.5 B`, reservations `0`. At the 12:10 close mark, account value is `59.84 + 12.5×4 = 109.84 Q`. Full path starts at `80 Q` (`10 B×8`), ends at `109.84 Q`, with realized first-trade result `109.89-80=29.89 Q` and new open basis `50.05 Q`; remaining unrealized mark result is `50-50.05=-.05 Q`; total gain is `29.84 Q = 29.89-.05`. This case distinguishes open simultaneous signals, prior settlement ordering, and simultaneous predicates while flat.

## Case coverage

| Case | Requirement exercised | Limit |
|---|---|---|
| WC-01 | exact timing, fees, cash, quantity, full exit and units | close-price proxy is proposed, not qualified execution |
| WC-02 | hypothetical competing reservations, deterministic order, insufficient cash and no double spend | accounting conformance only; no production multi-slot support |
| WC-03 | partial-exit arithmetic, allocated acquisition cost and open remainder | accounting conformance only; accepted P02 rejects partial exits |
| WC-04 | open end inventory, missing mark and unknown cost | no missing value is replaced with zero or carried forward |
| WC-05 | sampled account value and absolute drawdown | quote-denominated, non-annualized convention is proposed |
| WC-06 | determinable P06 values and reasons remain separate from P12 eligibility; endpoint return through unused gap | conservative action gate is proposed; no permission or runtime behavior |
| WC-07 | late and future information, complete-empty vs unproved coverage | synthetic timing trace only |
| WC-08 | late next fill, reservation release, no retry/carry | no fill qualification |
| WC-09 | NO_NEXT_BUCKET and exclusive end boundary with known balances | no end mark is inferred |
| WC-10 | exact named frozen fixture tuple and independent repeat calculation | names are documentation IDs, not runtime/cryptographic identities |
| WC-11 | valid Boolean invalidation is preserved by P06 and explicitly rejected by proposed P12 subset | no invalidation behavior is inferred |
| WC-12 | exact P02 fractional fee/slippage mapping, precedence and unit reconciliation | synthetic source/rates; no real cost qualification |
| WC-13 | open/flat coincident entry and exit, previous settlement before current decision, cash/inventory reconciliation | proposed order semantics; no runtime evidence |
