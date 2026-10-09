# P12 independent worked cases

These cases are independently hand-calculated from the proposed rules in `docs/contracts/p12/README.md`. They are synthetic accounting examples, not market evidence, user defaults, qualified fills, or profitability claims. Quote asset `Q`, base asset `B`, capital, prices and fee rate are invented. For the arithmetic cases, the proposed fee is 10 basis points (0.001) of quote notional per side. Values are shown without display rounding; division results are exact where terminating and otherwise shown as fractions.

## WC-01 — next-bucket timing, fees and full exit

Assumptions for this case only: start with `1,000 Q`; fixed entry size `400 Q`; fee `0.001`; no deposits or withdrawals.

| UTC event | Known input / action | Cash Q | Reserved Q | Holdings B | Reserved B | Account value Q |
|---|---|---:|---:|---:|---:|---:|
| 12:00 | Initial capital | 1,000 | 0 | 0 | 0 | 1,000 |
| 12:05 | Entry signal is usable at the bucket end; reserve `400 + .4`; no same-bucket fill | 1,000 | 400.4 | 0 | 0 | 1,000 |
| 12:10 | Next-bucket close fill at `8 Q/B`; buy `400/8 = 50 B`; pay `.4 Q` fee | 599.6 | 0 | 50 | 0 | 999.6 |
| 12:15 | Exit signal is usable at the bucket end; reserve all `50 B`; no same-bucket fill | 599.6 | 0 | 50 | 50 | 1,049.6 |
| 12:20 | Next-bucket close fill at `10 Q/B`; sell all `50 B`; gross `500 Q`; pay `.5 Q` fee | 1,099.1 | 0 | 0 | 0 | 1,099.1 |

Reconciliation: buy cash change `-400.4 Q`; sell cash change `+499.5 Q`; net gain `99.1 Q`; account-value gain `1,099.1 - 1,000 = 99.1 Q`. The 12:05 signal cannot fill at the signal bucket's close. The 10 Q/B fill is an explicit close-price proxy, not an executable fill claim.

## WC-02 — hypothetical reservation conformance and insufficient cash

This stand-alone accounting conformance case does not add position slots to the supported one-position strategy profile. It shows how a future shared-capital portfolio must avoid double reservation. Start with `500 Q`. Two synthetic reservation requests, `slot-a` and `slot-b`, each request `300 Q` plus `0.3 Q` fee. Both use the same next-bucket `5 Q/B` close.

1. Exit processing has no eligible exits. Entries sort by stable slot ID, so `slot-a` reserves `300.3 Q` first.
2. Free cash becomes `500 - 300.3 = 199.7 Q`. `slot-b` requires `300.3 Q`, so it receives `INSUFFICIENT_CASH`; the requested size is not reduced.
3. At the next bucket close, `slot-a` buys `300/5 = 60 B`; fee is `0.3 Q`; cash is `199.7 Q`; reservations are zero; holdings are `60 B`; account value at the `5 Q/B` fill mark is `499.7 Q`.

Reconciliation: reserved and spent quote is `300 + 0.3 = 300.3 Q`; uncommitted cash is `199.7 Q`; no cash is reserved twice; the second candidate creates no fill or fee. Reversing the stable slot order would change which request wins, so a product that supports multiple positions must adopt a tie-break. This example is not evidence that the current P02 strategy or runtime accepts multiple positions.

## WC-03 — partial exit arithmetic, explicitly unsupported in the recommended subset

This is an accounting conformance illustration only. Accepted P02 uses `partial_exits: false`, so it does not enable partial exits in the replay profile. A request with partial exits is explicitly unavailable under that contract. Start with `1,000 Q`; buy `400 Q` at `8 Q/B`, fee `0.4 Q`, acquiring `50 B`. Later sell `20 B` at `10 Q/B`, fee `200 × .001 = 0.2 Q`; retain `30 B`; end mark is `9 Q/B`.

- Cash after buy: `1,000 - 400 - 0.4 = 599.6 Q`.
- Buy basis including entry fee: `400.4 Q`; weighted basis `400.4 / 50 = 8.008 Q/B`.
- Partial sale gross: `20 × 10 = 200 Q`; net proceeds `199.8 Q`.
- Realized result with proportional entry-fee allocation: `199.8 - (20 × 8.008) = 39.64 Q`.
- Remaining basis: `30 × 8.008 = 240.24 Q`; ending marked value: `30 × 9 = 270 Q`; unrealized result: `29.76 Q`.
- Ending cash `799.4 Q`; ending account value `799.4 + 270 = 1,069.4 Q`; gain `69.4 Q = 39.64 + 29.76 Q`.

The example makes cost allocation visible. The current accepted rule returns an explicit unsupported/unavailable result for this partial-exit rule. If P12's check requires actual runtime partial exits, a separate strategy field and simulator scope need adoption first.

## WC-04 — open inventory, missing mark and missing fee

After the `400 Q` buy in WC-01, cash is `599.6 Q` and inventory is `50 B`.

- If the end mark is qualified at `9 Q/B`, inventory is worth `450 Q`; account value is `1,049.6 Q`. It remains open inventory, not realized proceeds.
- If the required end mark is missing, cash `599.6 Q` and inventory `50 B` remain known, but account value, total gain/loss and drawdown are unavailable with the mark reason. No prior mark is carried forward.
- If the fee rate is not adopted before the run, the run is unavailable before any simulated action. It does not substitute a zero fee. If only an unrelated fee component is unknown, the profile must name it as excluded and cannot claim all-in net performance.

## WC-05 — units and drawdown

One sampled account series in `Q` is `1,000`, `999.6`, `1,049.6`, `1,020`. The high-water marks are `1,000`, `1,000`, `1,049.6`, `1,049.6`. The absolute peak-to-trough falls are `0`, `.4`, `0`, `29.6 Q`; largest drawdown is `29.6 Q`. This is not a percent return, daily statistic or annualized measure. If any required sample is unavailable, the maximum for the full interval is unavailable.

## Case coverage

| Case | Requirement exercised | Limit |
|---|---|---|
| WC-01 | exact timing, fees, cash, quantity, full exit and units | close-price proxy is proposed, not qualified execution |
| WC-02 | hypothetical competing reservations, deterministic order, insufficient cash and no double spend | accounting conformance only; no production multi-slot support |
| WC-03 | partial-exit arithmetic, allocated acquisition cost and open remainder | accounting conformance only; accepted P02 rejects partial exits |
| WC-04 | open end inventory, missing mark and unknown cost | no missing value is replaced with zero or carried forward |
| WC-05 | sampled account value and absolute drawdown | quote-denominated, non-annualized convention is proposed |
