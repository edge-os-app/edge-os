# P12 independent worked cases

These cases are independently hand-calculated from the proposed rules in `docs/contracts/p12/README.md`. They are synthetic accounting examples, not market evidence, user defaults, qualified fills, or profitability claims. Quote asset `Q`, base asset `B`, capital, prices and costs are invented. WC-01 through WC-05 use a synthetic saved fee rate `0.001` (10 bps) and slippage rate `0`; both would be stored in the hypothetical P02 revision with `source_ref: "synthetic-case-input"`. Cost rates are fractions; bps are display only. Values are shown without display rounding; division results are exact where terminating and otherwise shown as fractions.

## WC-01 — next-bucket timing, fees and full exit

Run identity labels (synthetic, not production IDs): strategy `synthetic-strategy-wc01-v1`; immutable run config `synthetic-config-wc01-v1`; dataset `synthetic-dataset-wc01-v1`; market binding `synthetic-market-binding-wc01-v1`. UTC window `[2026-10-01T12:05:00Z,2026-10-01T12:25:00Z)`; scheduled decision/valuation points are12:05/12:10/12:15/12:20; warm-up0; initial state at12:05 is1,000 Q,0 B, no reservations; initial account value1,000 Q. The saved rule is `entry: price() > 7 Q/B`, `exit: price() >= 9 Q/B`, `invalidation: {state: NOT_REQUESTED, source_ref: "synthetic-case-input"}`, `data_inputs=[price]`, `additions=false`, `partial_exits=false`; saved fee `.001`, slippage0, cost `source_ref="synthetic-case-input"`. Its proposed `p12.essential-evidence/1` binding associates all four identity labels above and separately declares `entry: BOUND [price@0]`, `exit: BOUND [price@0]`. Each single-pool close is qualified and `available_at` equals its bucket end:12:05=8,12:10=8,12:15=9,12:20=10 Q/B. Each timestamp has one close used consistently for P06 `price()`, any settlement fill, and mark. There is no pre-window decision at12:00; the window start and schedule state it is outside this run.

| UTC event | P06 observation / order event | Cash Q | Reserved Q | Holdings B | Reserved B | Account value Q |
|---|---|---:|---:|---:|---:|---:|
| 12:05 | Initial state/sample `1,000 Q`; price8 makes entry TRUE; reserve `400 + .4`; no same-bucket fill | 1,000 | 400.4 | 0 | 0 | 1,000 |
| 12:10 | Settle prior buy at the single price8 close; buy `400/8=50 B`, fee `.4`; value at same price8. Entry remains TRUE but is ignored while open; exit price8>=9 is FALSE | 599.6 | 0 | 50 | 0 | 999.6 |
| 12:15 | Same price9 is mark and P06 input; value `599.6+50×9`; exit is TRUE, reserve all `50 B`; no entry while open | 599.6 | 0 | 50 | 50 | 1,049.6 |
| 12:20 | Settle prior sell at the single price10 close; gross500, fee.5; cash1099.1; value at same price10. Flat entry is TRUE, but next close is12:25=`end`, so record `NO_NEXT_BUCKET` before reservation | 1,099.1 | 0 | 0 | 0 | 1,099.1 |
| Window end12:25 (boundary, not a sample) | No decision, fill or mark; no pending order/reservation | 1,099.1 | 0 | 0 | 0 | terminal sample remains12:20 |

The terminal sample is the last scheduled in-window point, 12:20, not the excluded end. Reconciliation: buy cash change `-400.4 Q`; sell cash change `+499.5 Q`; net gain `99.1 Q`; account-value gain `1,099.1 - 1,000 = 99.1 Q`. The 12:05 signal cannot fill at its own close. Close prices are a proposed proxy, not executable fill evidence.

## WC-02 — hypothetical reservation conformance and insufficient cash

This stand-alone accounting conformance case does not create strategy instances, slots, or production shared-capital semantics. It shows the arithmetic needed if a separately adopted shared-capital portfolio were ever supported. On 2026-10-01 UTC, the hypothetical run window is `[12:00,12:10)` with one reservation event at12:00, a next-bucket fill at12:05, and terminal sample at12:05. Initial state is cash500 Q, inventory0 B, no reservations; the synthetic cost source is `synthetic-wc02`, fee `.001`, slippage0. Two independent synthetic reservation requests, `request-a` and `request-b` (not two instances of the same revision), each request300 Q plus0.3 Q fee. Both use the same qualified single-pool12:05 close5 Q/B, available12:05, for settlement/mark.

1. Exit processing has no eligible exits. For this hypothetical conformance calculation only, requests sort by their declared stable request labels, so `request-a` reserves `300.3 Q` first.
2. Free cash becomes `500 - 300.3 = 199.7 Q`. `request-b` requires `300.3 Q`, so it receives `INSUFFICIENT_CASH`; the requested size is not reduced.
3. At12:05, `request-a` buys `300/5 = 60 B`; fee is0.3 Q; cash is199.7 Q; reservations are zero; holdings are60 B; terminal account value at the5 Q/B fill mark is499.7 Q. The12:10 exclusive end has no event.

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

After the WC-01 buy settles at12:10, cash is599.6 Q and inventory is50 B.

- If the qualified own-bucket12:15 mark is9 Q/B, inventory is worth450 Q; that sample's account value is1,049.6 Q. It remains open inventory, not realized proceeds.
- If the 12:15 mark is missing, cash599.6 Q and inventory50 B remain known, but account value at12:15 and full-window drawdown are unavailable with the mark reason. WC-01's terminal account value can still use its separate qualified12:20 terminal sample; do not carry a prior mark into either timestamp. If the required terminal mark itself is missing, WC-09 states the unavailable terminal valuation behavior.
- If the saved fee/slippage model or required `source_ref` is missing or unusable, or the P12 cost rule has not been adopted, the run is unavailable before any simulated action. It does not substitute zero. Gas and other excluded costs cannot be described as included in net performance.

## WC-05 — units and drawdown

Synthetic UTC account-value samples on 2026-10-01, in chronological order at12:00/12:05/12:10/12:15, are1,000/999.6/1,049.6/1,020 Q. The high-water marks are1,000/1,000/1,049.6/1,049.6 Q. The absolute peak-to-trough falls are0/.4/0/29.6 Q; largest drawdown is29.6 Q. This standalone metric check has no strategy, fills, or cost input. It is not a percent return, daily statistic or annualized measure. If any required sample is unavailable, the maximum for the full interval is unavailable.

## WC-06 — compiler result is separate from action eligibility

Frozen synthetic input `eligibility-case/1`: strategy `synthetic-strategy-wc06-or-v1`, run config `synthetic-config-wc06-or-v1`, dataset `synthetic-dataset-wc06-or-v1`, market binding `synthetic-market-binding-wc06-or-v1`; `data_inputs=[price, quote_volume]`. P06-valid entry is `price() > 100 Q/B OR quote_volume() > 0 Q`; exit is `FALSE`; invalidation is `{state: NOT_REQUESTED, source_ref: "eligibility-case/1"}`; warm-up0. The proposed `p12.essential-evidence/1` object binds those four exact labels and declares `entry: BOUND [quote_volume@0]`, `exit: BOUND []`. At12:00, schedule position0 and evaluation position0 refer to the12:00 bucket end. Price is qualified110 Q/B, available12:00; quote volume is absent, with observation reason `MISSING_QUOTE_VOLUME`. P06's calculated value is TRUE with reasons exactly `("MISSING_QUOTE_VOLUME", "MISSING_QUOTE_VOLUME:0")`: supplied source reason then P06 indexed missing-value reason. It is not rewritten to UNKNOWN. The missing bound essential dependency makes the entry ineligible as `ESSENTIAL_EVIDENCE_UNAVAILABLE`; no order/reservation/fill; cash remains1,000 Q, inventory0 B. With no adopted binding, eligibility instead remains `UNRESOLVED_ESSENTIAL_EVIDENCE`; neither essentiality nor emptiness is inferred from the P06 reason or final TRUE.

For a separate fixture, strategy `synthetic-strategy-wc06-return-v1`, run config `synthetic-config-wc06-return-v1`, dataset `synthetic-dataset-wc06-return-v1`, market binding `synthetic-market-binding-wc06-return-v1`; `data_inputs=[price]`. Use `price_return(2) > 0.05`, schedule11:50/11:55/12:00 and evaluation position2 at12:00. Endpoint prices are100 and110 Q/B, qualified/available at their respective times; 11:55 is `COMPLETE_EMPTY`, no close, source reason `EMPTY_BUCKET_NO_CLOSE`, available11:55. P06 calculates return0.1 then TRUE, with exact reasons `("EMPTY_BUCKET_NO_CLOSE", "MISSING_PRICE:1")`. The proposed `p12.essential-evidence/1` binding associates those four identity labels and declares `entry: BOUND [price@0, price@-2]`, `exit: BOUND []`. At position2, the dependencies resolve to schedule positions2 and0; the missing intermediate position1 is not an essential dependency and does not itself block this determinate result. The same unchanged binding at position3 resolves to positions3 and1, not positions2 and0. WC-14 shows the second decision where that position1 is missing essential evidence. If the hypothesis instead binds `price@-1`, the first decision itself has an unavailable essential dependency. With no adopted binding, eligibility is unresolved. Retain P06 value/reasons in every case; this distinguishes essential-input qualification from blanket reason filtering and grants no readiness or permission.

## WC-07 — late, future and proven-empty decision inputs

These are three isolated P06 conformance contexts, not one replay schedule. Strategy expression for each is `price()`, with matching market binding, one schedule position and evaluation index0. The run-level accounting example starts with `1,000 Q`, `0 B`, no orders; no action is inferred from these diagnostic probes.

| Case / evaluation UTC | `scheduled_bucket_ends[0]` | `prices[0].bucket_end`, value/status and `available_at` | Actual P06 value / reasons | P12 consequence proposed |
|---|---|---|---|---|
| Current-slot late delivery / 12:00 | 12:00 | 12:00, qualified `110 Q/B`, available 12:02 | `UNKNOWN`; `FUTURE_INFORMATION:0` | Current input is not usable at decision12:00; no entry/reservation/fill; cash1,000 Q, inventory0 B |
| Future timestamp incorrectly placed in current position / 12:00 | 12:00 | 12:05, qualified `110 Q/B`, available 12:05 | `UNKNOWN`; `SCHEDULE_MISMATCH:0` (timestamp mismatch is checked before future timing) | Malformed/misaligned observation; reject/retain that reason, do not reinterpret it as a future-price operator or current observation |
| Complete-empty current bucket / 12:10 | 12:10 | Price: no close, value null, reason `EMPTY_BUCKET_NO_CLOSE`, available12:10. Quote volume: exact qualified value0, available12:10 | `price()` is `UNKNOWN`; reasons `EMPTY_BUCKET_NO_CLOSE`, `MISSING_PRICE:0`. `quote_volume()` is value0, no reasons | No price-triggered entry; quote volume remains known zero; cash1,000 Q, inventory0 B |

For contrast, an `INCOMPLETE` bucket is not a proved empty interval: P07 reports coverage unproved, and the P12 admission/decision result must retain `COVERAGE_NOT_PROVEN`, not `EMPTY_BUCKET_NO_CLOSE`. If the terminal valuation mark is missing, cash and inventory remain known but the terminal account value is unavailable at its explicit sample time (see WC-09 and the contract). P06 does not supply P07 qualification or action permission.

## WC-08 — late next-bucket close releases reservation

Inputs on 2026-10-01 UTC: strategy `synthetic-strategy-wc08-v1`, run config `synthetic-config-wc08-v1`, dataset `synthetic-dataset-wc08-v1`, market binding `synthetic-market-binding-wc08-v1`; window `[12:00,12:10)`, scheduled points12:00/12:05, one flat strategy, start1,000 Q, fixed entry100 Q, saved fee.001, slippage0, `data_inputs=[price]`, `entry: price() > 4 Q/B` with decision price5 Q/B qualified/available at12:00; `exit: FALSE`; invalidation `{state: NOT_REQUESTED, source_ref: "synthetic-wc08"}`. The proposed `p12.essential-evidence/1` object associates those exact identities and declares `entry: BOUND [price@0]`, `exit: BOUND []`. At12:00 reserve100.1 Q; free cash899.9 Q; inventory0 B. The next bucket close is5 Q/B at12:05 but `available_at=12:07`. At12:05 the prior fill fails `LATE_INPUT`; do not fill/charge fee; release100.1 Q reservation so total cash remains1,000 Q and free cash returns1,000 Q. The same late close cannot be used as the12:05 `price()` decision or terminal mark: P06 returns UNKNOWN with `FUTURE_INFORMATION:0`; the bound price@0 is also unavailable as `ESSENTIAL_EVIDENCE_UNAVAILABLE`, retaining P07 `LATE_INPUT` and P06's reason; entry is not carried to12:07. Terminal sample is12:05 but its required mark is unavailable then, so retain cash1,000 Q/inventory0 B and make terminal value/gain/drawdown unavailable with the late-data reason. At12:10 (exclusive end) there is no event. If12:05 instead were `COMPLETE_EMPTY`, P07 reason would be `EMPTY_BUCKET_NO_CLOSE`; if incomplete/unqualified, preserve that distinct reason.

## WC-09 — NO_NEXT_BUCKET and exclusive run end

Inputs: strategy `synthetic-strategy-wc09-v1`, run config `synthetic-config-wc09-v1`, dataset `synthetic-dataset-wc09-v1`, market binding `synthetic-market-binding-wc09-v1`; window `[2026-10-01T12:00:00Z, 2026-10-01T12:10:00Z)`, scheduled points12:00/12:05, start cash1,000 Q, no inventory, fixed entry100 Q, fee.001, slippage0, `data_inputs=[price]`, `entry: price() > 4 Q/B` with qualified/available12:00 price4 and12:05 price5; exit FALSE; invalidation `{state: NOT_REQUESTED, source_ref: "synthetic-wc09"}`. Proposed `p12.essential-evidence/1` binding: `entry: BOUND [price@0]`, `exit: BOUND []`, associated with the listed identities. At12:05 entry is TRUE. A next-bucket close would occur at12:10 exactly, but that timestamp is the exclusive end. At12:05, settle nothing, value all-cash account at1,000 Q, then evaluate and reject entry with `NO_NEXT_BUCKET` before reserving. This is also the terminal sample. There is no decision/fill/mark at12:10. Final cash1,000 Q, inventory0 B, terminal account value1,000 Q. In a separate open-inventory variant, begin with10 B and known cash; if its own-bucket12:05 terminal mark is absent, preserve cash/base but terminal account value and dependent metrics are unavailable at12:05. Do not use the12:10 exclusive-end close or carry a12:00 mark forward.

## WC-10 — repeated calculation with full window and terminal rejection

Fixture identity tuple (synthetic/documentation-only): strategy revision `synthetic-strategy-wc10-v1`; dataset revision `synthetic-dataset-wc10-v1`; run configuration `synthetic-config-wc10-v1`; market binding `synthetic-market-binding-wc10-v1`; profile `p12.spot-replay/1`. Window is `[2026-10-01T12:05:00Z,2026-10-01T12:25:00Z)`; scheduled positions and evaluation times are exactly12:05/12:10/12:15/12:20 UTC; warmup0; initial state at12:05 is cash1,000 Q, inventory0 B, no reservation; declared initial capital1,000 Q. This is the entire run schedule. There is no12:00 pre-window decision and no decision at exclusive end12:25.

Saved strategy is `entry: price() > 7 Q/B`, `exit: price() >= 9 Q/B`, `invalidation: {state: NOT_REQUESTED, source_ref: "synthetic-wc10"}`, fixed entry400 Q, additions false, partial exits false, fee.001, slippage0, cost source `synthetic-wc10`, `data_inputs=[price]`. Its proposed `p12.essential-evidence/1` object binds the listed identity tuple and separately declares `entry: BOUND [price@0]`, `exit: BOUND [price@0]`. Exact single-pool price observations, each qualified with `available_at` equal to its scheduled end:12:05=8,12:10=8,12:15=9,12:20=10 Q/B. At every timestamp, that one close is used for P06 `price()`, a settlement fill due at that time if any, and the mark. No other input, missing observation or capital flow exists. `COMPLETE_EMPTY` is not involved.

| UTC time | Settlement / signal / reservation | Cash Q | Reserved Q | Inventory B | Reserved B | Account value Q |
|---|---|---:|---:|---:|---:|---:|
| 12:05 | Initial sample1,000; `price=8`: entry TRUE, exit FALSE; reserve400+.4=400.4; next fill12:10 | 1,000 | 400.4 | 0 | 0 | 1,000 |
| 12:10 | Same `price=8` settles buy400/8=50 B, fee.4; value at8; entry TRUE is ignored while open; exit FALSE | 599.6 | 0 | 50 | 0 | 999.6 |
| 12:15 | Same `price=9` mark/value=599.6+50×9=1,049.6; exit TRUE reserves50 B; entry TRUE ignored while open; next fill12:20 | 599.6 | 0 | 50 | 50 | 1,049.6 |
| 12:20 | Same `price=10` settles sell50 B: gross500, fee.5, cash1,099.1; mark/value1,099.1. Flat entry TRUE but next close12:25 is outside window; record `NO_NEXT_BUCKET` before reserving | 1,099.1 | 0 | 0 | 0 | 1,099.1 |
| Window end12:25 (boundary, not a sample) | No observation, decision, fill or mark; final order/reservations are empty | 1,099.1 | 0 | 0 | 0 | terminal sample remains12:20 |

Reconciliation: buy cash change−400.4 Q; sell proceeds+499.5 Q; final minus initial=99.1 Q. The terminal account value is explicitly the last scheduled in-window sample at12:20, not a mark at12:25. Repeat the exact frozen identity tuple and ordered observations twice; P06 reason lists are empty at all four samples, while the terminal order outcome is separately `NO_NEXT_BUCKET`; event rows, balances and metrics must be identical. These are named documentation identities, not hashes or production record IDs; this independent literal repeat is not runtime serialization, persistence or retrieval evidence.

## WC-11 — valid Boolean invalidation is not silently dropped

Synthetic strategy input at `2026-10-01T12:00:00Z`: P06-valid `invalidation = price() < 5 Q/B`, `entry = price() > 100 Q/B`, `exit = FALSE`, fixed quote size `100 Q`, `additions=false`, `partial_exits=false`. At 12:00 the qualified/available price is `4 Q/B`; the Boolean invalidation calculation is `TRUE`. P06 accepts and preserves this rule. The proposed P12/1 subset rejects the exact revision before replay with `UNSUPPORTED_INVALIDATION`, retains the original revision/field/value, and creates no order/reservation/fill. Start cash `1,000 Q`, inventory `0 B` remain known. This is a proposed subset boundary, not a P06 rejection and not a choice that invalidation means an exit or entry stop.

## WC-12 — saved fractional fee and slippage mapping

The synthetic P06-valid strategy stores `fee_rate="0.003"`, `slippage_rate="0.005"`, `source_ref="synthetic-cost-source"`. On 2026-10-01 UTC, strategy `synthetic-strategy-wc12-v1`, run config `synthetic-config-wc12-v1`, dataset `synthetic-dataset-wc12-v1`, market binding `synthetic-market-binding-wc12-v1`; window `[12:00,12:20)`, decision points12:00/12:05/12:10/12:15; initial cash1,000 Q, no inventory, warm-up0. Strategy entry is `price() > 7 Q/B`, exit is `price() >= 9 Q/B`, invalidation is `{state: NOT_REQUESTED, source_ref: "synthetic-cost-source"}`, fixed entry400 Q, no additions/partials, `data_inputs=[price]`. Its proposed `p12.essential-evidence/1` object binds these identities and separately declares `entry: BOUND [price@0]`, `exit: BOUND [price@0]`. Single-pool qualified close/availability pairs are12:00=8,12:05=8,12:10=9,12:15=10 Q/B. Decide a400 Q buy at12:00 and fill at the12:05 next-bucket close8; decide full exit at12:10 and fill at the12:15 next-bucket close10. These are also the same-bucket P06 decision/mark closes. No run override. The exact saved rates are retained. Display-only conversions are30 bps fee and50 bps slippage. At12:15, after sell settlement/value, the flat entry at price10 is TRUE but receives `NO_NEXT_BUCKET` because the only next close is12:20=end, before a new reservation. Final known state is post-buy cash plus exit net proceeds, zero base inventory and no reservations; the numeric balance follows below.

First, the **ideal rational oracle** ignores finite-context rounding: buy fill `8×1.005=8.04`; quantity `400/8.04=10000/201 B`; buy fee `400×.003=1.2 Q`; post-buy cash `598.8 Q`; basis `401.2 Q`; sell fill `10×.995=9.95`; gross `99500/201 Q`; fee `199/134 Q`; net `198403/402 Q`; final cash `2195603/2010 Q`; and both net-minus-basis and final-minus-initial are `185603/2010 Q`. This is the exact algebraic comparison reference, not the P06/P12 Decimal result.

Second, the **ordered Decimal50/half-even result** uses P06's accepted per-operation context. Each next operation consumes the previous rounded result in this order: `buy_factor=1+.005=1.005`; `buy_fill=8×buy_factor=8.040`; `base=400/buy_fill=49.751243781094527363184079601990049751243781094527 B`; `buy_fee=400×.003=1.200 Q`; `cash_after_buy=1000−400−1.2=598.800 Q`; `basis=400+1.2=401.200 Q`; `sell_factor=1−.005=.995`; `sell_fill=10×sell_factor=9.950`; `gross=base×sell_fill=495.02487562189054726368159203980099502487562189054 Q`; `sell_fee=gross×.003=1.4850746268656716417910447761194029850746268656716 Q`; `net=gross−sell_fee=493.53980099502487562189054726368159203980099502487 Q`; `final_cash=598.8+net=1092.3398009950248756218905472636815920398009950249 Q`; `realized=net−401.2=92.33980099502487562189054726368159203980099502487 Q`; `final_minus_initial=final_cash−1000=92.3398009950248756218905472636815920398009950249 Q`. Thus `realized−final_minus_initial=−3E−47 Q` under this operation order. It is a tiny Decimal50 rounding residual; do not force exact equality or alter the accepted precision. Both fees are counted once. Gas, separate spread and other costs are excluded. These synthetic calculations do not estimate venue costs.

## WC-13 — coincident exit/entry while open, then settle before flat decision

Synthetic inputs/config on 2026-10-01 UTC: strategy `synthetic-strategy-wc13-v1`, run config `synthetic-config-wc13-v1`, dataset `synthetic-dataset-wc13-v1`, market binding `synthetic-market-binding-wc13-v1`; window `[12:00,12:15)`, decisions12:00/12:05/12:10, initial state `cash=0 Q`, `inventory=10 B`, weighted basis80 Q; initial mark at12:00 is8 Q/B, so initial account value80 Q. Fee.001, slippage0, cost source `synthetic-wc13`; fixed entry50 Q; `entry: price() > 5 Q/B`, `exit: price() > 5 Q/B`, invalidation `{state: NOT_REQUESTED, source_ref: "synthetic-wc13"}`, `data_inputs=[price]`. Its proposed `p12.essential-evidence/1` object binds those identities and separately declares `entry: BOUND [price@0]`, `exit: BOUND [price@0]`. There is one price close per pool/bucket, qualified and `available_at` equal to its timestamp:12:00=8,12:05=11,12:10=4 Q/B. At12:00, both entry and exit are TRUE while open. Exit-first ordering reserves10 B; it does not create an entry/reserve quote. At12:05, the previous exit settles first at that bucket's single close11 Q/B; the same close is the mark and current P06 `price()`: gross110 Q, fee.11 Q, cash109.89 Q, inventory0 B, reservation0, account value109.89 Q. Current entry and exit are both TRUE while flat; flat-state ordering creates only the entry, reserving50+.05=50.05 Q; no exit can reserve absent inventory. At12:10, the prior buy settles at the same close4 Q/B used for the mark/current signal. Buy50/4=12.5 B, fee.05 Q; cash59.84 Q, inventory12.5 B, reservations0, account value109.84 Q. Current entry/exit are FALSE at price4, so no order is created. At exclusive end12:15 there is no further decision/fill/mark. Terminal sample is12:10, account value109.84 Q. Realized first-trade result is109.89−80=29.89 Q; remaining basis50.05 Q and mark value50 Q give unrealized−.05 Q; total gain29.84 Q. This trace has one consistent close per pool/bucket and covers coincident signals while open/flat and prior settlement before the current signal.

## WC-14 — essential-evidence descriptor literals (proposed)

All IDs below are explicit synthetic equality labels, not hashes or production identities. This standalone fixture binds strategy `synthetic-strategy-wc14-v1`, run config `synthetic-config-wc14-v1`, dataset `synthetic-dataset-wc14-v1`, and market `synthetic-market-binding-wc14-v1`; rule entry is `price_return(2) > 0.05`, exit is `price() < 90 Q/B`, `data_inputs=[price]`. UTC schedule and single-pool price rows are: position0/12:00=100 Q/B qualified and available12:00; position1/12:05 is `COMPLETE_EMPTY`, has no close and source reason `EMPTY_BUCKET_NO_CLOSE`, available12:05; position2/12:10=110 Q/B qualified/available12:10; position3/12:15=115 Q/B qualified/available12:15. Warm-up is2. P06 uses the exact four-position schedule and remains unchanged.

The proposed binding literal is:

```yaml
schema_version: p12.essential-evidence/1
strategy_revision: synthetic-strategy-wc14-v1
run_configuration_id: synthetic-config-wc14-v1
dataset_revision: synthetic-dataset-wc14-v1
market_binding_id: synthetic-market-binding-wc14-v1
fields:
  entry:
    state: BOUND
    essential_dependencies:
      - {series: price, offset_buckets: 0}
      - {series: price, offset_buckets: -2}
  exit:
    state: BOUND
    essential_dependencies: []
```

| Literal / evaluation | Exact resolution and proposed status | Consequence / limit |
|---|---|---|
| Valid entry binding at position2/12:10 | `price@0` resolves schedule[2]=12:10/110; `price@-2` resolves schedule[0]=12:00/100. Both match dataset/market, are qualified and available. P06 calculates `(110/100)-1=0.1`, then TRUE, retaining exact reasons `("EMPTY_BUCKET_NO_CLOSE", "MISSING_PRICE:1")` from unused schedule[1]. Entry essential evidence is satisfied. | Retained unused gap alone does not block this proposed field binding. Actual action still requires adopted profile, P07 admission, valid whole P06 tree/timing, all other action/order/cost conditions. |
| Same immutable binding at position3/12:15 | `price@0` now resolves schedule[3]=12:15/115; `price@-2` resolves schedule[1]=12:05, not the prior decision's absolute positions0/2. That essential point is complete-empty/no close. P06 `price_return(2)` is UNKNOWN with `("EMPTY_BUCKET_NO_CLOSE", "MISSING_PRICE:1")`; the binding status is `ESSENTIAL_EVIDENCE_UNAVAILABLE`, retaining source and P06 reasons. | No entry action. This proves offsets resolve anew at each scheduled decision; gaps are not compressed or remapped. |
| Explicit empty exit set | `exit: {state: BOUND, essential_dependencies: []}` is a positive declaration that the hypothesis has no additional essential evidence for exit. At12:10, the separate P06 `price()<90` operation uses current qualified110 and returns FALSE; at12:15 it uses115 and returns FALSE. | Empty does not skip P06 operation dependencies or turn FALSE into TRUE; no exit. Empty also grants no general readiness/permission. |
| Entire object absent or present but unadopted | No recognized adopted `p12.essential-evidence/1` binding is available for these exact IDs. Status is `UNRESOLVED_ESSENTIAL_EVIDENCE` for both entry and exit; retain any independently computed P06 values/reasons. | No action is eligible. Do not infer empty dependencies from no reasons or all dependencies from any reason. |
| Partial object with entry BOUND but `fields.exit` omitted | Entry can be syntactically described, but exit coverage is not inferred empty. Proposed completeness preflight returns `UNRESOLVED_ESSENTIAL_EVIDENCE` / `ESSENTIAL_BINDING_FIELD_MISSING:exit`; no replay action is admitted. If an isolated later position held inventory and exit P06 were TRUE, that missing exit binding would still leave the exit ineligible/unresolved, not create an exit. | This proposed complete-pair preflight avoids beginning a position with an uncovered exit field. Allowing a run with one action field uncovered would need a separately adopted rule. |
| Malformed or mismatched descriptor | Unknown series `bid_ask`, duplicate dependencies, Boolean/non-integer offset, positive offset `+1`, or unknown field → `INVALID_ESSENTIAL_BINDING`. A syntactically valid descriptor carrying a different dataset or market binding → `ESSENTIAL_BINDING_IDENTITY_MISMATCH`. | Reject before any action; never reinterpret malformed/mismatched metadata as an empty set or attach it to another run. |
| Well-formed bound dependency unavailable | If the valid current `price@0` row at decision12:00 is delivered12:02, P06 gives UNKNOWN/`FUTURE_INFORMATION:0`; P07 says late. Binding reports `ESSENTIAL_EVIDENCE_UNAVAILABLE`, preserves both exact reasons and the source identity. If an essential price@0 instead has a wrong bucket/market, retain P06 `SCHEDULE_MISMATCH:0`/`MARKET_BINDING_MISMATCH:0` plus the source reason. | No action. A data failure is distinct from invalid binding syntax, identity mismatch and unresolved/unadopted essentiality. Never backdate or retry. |

These outcomes are proposed documentation, not an implemented validator. The product has not adopted the descriptor, the complete-pair rule or any actual strategy's essential set.

## Case coverage

| Case | Requirement exercised | Limit |
|---|---|---|
| WC-01 | exact timing, fees, cash, quantity, full exit and units | close-price proxy is proposed, not qualified execution |
| WC-02 | hypothetical competing reservations, deterministic order, insufficient cash and no double spend | accounting conformance only; no production multi-slot support |
| WC-03 | partial-exit arithmetic, allocated acquisition cost and open remainder | accounting conformance only; accepted P02 rejects partial exits |
| WC-04 | open end inventory, missing mark and unknown cost | no missing value is replaced with zero or carried forward |
| WC-05 | sampled account value and absolute drawdown | quote-denominated, non-annualized convention is proposed |
| WC-06 | determinable P06 values/reasons remain separate from proposed strategy-field essential-evidence binding; endpoint return through unused gap | no blanket all-reasons filter; binding and eligibility behavior remain proposed; no permission or runtime behavior |
| WC-07 | late and future information, complete-empty vs unproved coverage | synthetic timing trace only |
| WC-08 | late next fill, reservation release, no retry/carry | no fill qualification |
| WC-09 | NO_NEXT_BUCKET and exclusive end boundary with known balances | no end mark is inferred |
| WC-10 | exact named frozen fixture tuple, complete window/event trace, terminal `NO_NEXT_BUCKET`, and independent repeat calculation | names are documentation IDs, not runtime/cryptographic identities; `NO_NEXT_BUCKET` is an order outcome, not a P06 reason |
| WC-11 | valid Boolean invalidation is preserved by P06 and explicitly rejected by proposed P12 subset | no invalidation behavior is inferred |
| WC-12 | exact P02 fractional fee/slippage mapping, precedence and unit reconciliation | synthetic source/rates; no real cost qualification |
| WC-13 | open/flat coincident entry and exit, previous settlement before current decision, cash/inventory reconciliation | proposed order semantics; no runtime evidence |
| WC-14 | versioned essential-binding identities, explicit empty/missing/partial/malformed/unavailable cases and moving lookback offsets | proposed descriptor and completeness rule only; no P12 validator or adopted user binding |
