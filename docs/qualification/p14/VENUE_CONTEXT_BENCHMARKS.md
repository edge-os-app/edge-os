# P14 proposed venue, timeframe, and fee-context benchmarks

Status: **proposal and source register only**. This is not a promise that the
listed venues are enabled, that a user is eligible to trade there, or that the
shown public documentation reconstructs historical fees. The current P14
numerical proposal remains an unwired spot-cash helper.

## What a user must be able to inspect

Every later replay result should expose, in a copyable record:

| Field | Requirement | Why it matters |
|---|---|---|
| Venue, native instrument, product/contract kind | Exact exchange-native identifiers; `SPOT`, `LINEAR_PERPETUAL`, or `INVERSE_PERPETUAL` | A ticker string alone does not define the traded instrument. |
| Settlement/margin asset and leverage | Named asset and explicit leverage; unknown is unavailable | A USDT-linear perp and an inverse contract have different P&L and fee units. |
| Execution and context timeframes | UTC durations, decision timestamp, each input candle's completed-at time | Prevents using an unfinished higher-timeframe candle or future data. |
| Historical ticker/mark/index source | Primary URL/API request, bar-end timestamp, source-availability timestamp, retrieval timestamp, response hash, price kind | Separates decision-time availability from later archival retrieval and makes data provenance reproducible. |
| Fee schedule source | Primary URL/API request, retrieval timestamp, effective UTC interval, snapshot hash | A live fee page is not a historical time series. |
| Applied fee facts | Maker/taker outcome, account tier, fee asset, discount token/plan, promotion, quoted rate and actual per-fill fee if available | A published base rate is usually not the account's charged rate. |
| Derivative cash flows | Contract multiplier, funding source/interval, liquidation/insurance/settlement events | They are not spot trading fees and must not disappear from P&L. |

`unknown`, `not retrieved`, and `not applicable` are different display states.
No one may render any of them as `0`, `0%`, or a filled market value.

## Initial official-source register (captured 2026-10-12)

The values below are **public base-rate orientation only**. They are not P14
defaults and should be re-captured into dated snapshots for every replay range.

| Venue | Product orientation | Published fee benchmark | Historical market/context source | Important qualification |
|---|---|---|---|---|
| Binance | Spot and USDⓈ/coin-margined futures | Standard spot VIP-0 is published as 0.10% maker/taker; futures vary by product/tier | [fee schedule](https://www.binance.com/en-GB/fee/trading), [spot fee/API guide](https://www.binance.com/en/academy/articles/how-to-calculate-transaction-fees-on-binance) | Actual account commission, BNB payment, VIP and pair promotions may differ. Binance says historical displays should use the actual reported fee where available. |
| Hyperliquid | USDC-margined linear perpetuals and spot | Perp base tier: 0.015% maker / 0.045% taker | [fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees), [funding/history API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) | Rolling 14-day tier, rebates, HIP-3 deployer fee and the hourly funding transfer all matter. |
| KuCoin | Spot, USDT- and coin-margined futures | VIP-0 spot Class A: 0.10%/0.10%; futures: 0.02%/0.06% | [actual fee-rate API](https://www.kucoin.com/docs-new/3473239e0), [VIP table](https://www.kucoin.com/support/48142946141635) | Pair class, tier, KCS discount and fee asset alter the charged fee; authenticated actual rate is preferred. |
| MEXC | Spot and futures | Do not adopt a universal value: published API-futures fees have changed separately from web/app fees | [spot API historical klines](https://mexcdevelop.github.io/apidocs/spot_v3_en/), [API-futures fee update](https://www.mexc.fm/id-ID/announcements/article/updates-to-api-futures-trading-fees-may-1-2026-17827791535194) | Channel, pair, date, promotion, region and account assumptions need a dated source snapshot. |
| Bitget | Spot, USDT/USDC/coin futures | Public base orientation: spot 0.10%/0.10%; futures 0.02% maker / 0.06% taker | [fee FAQ](https://www.bitget.com/support/articles/12560603892733), [historical candles API](https://www.bitget.com/docs/catalog/market/market-data) | VIP/BGB/pro programs and temporary incentives can override public base rates; candle type must say market, mark, index, or premium. |

## Proposed multi-timeframe mechanics

1. Select one execution timeframe. A decision at `t` can reserve an order only
   for a documented later execution bar; it cannot fill against the same
   decision bar unless a later contract explicitly changes the latency rule.
2. For each context timeframe (for example 5m and 1h), use only the bar whose
   close is the most recent completed boundary at `t`. At `12:05 UTC`, a 5m bar
   may end at `12:05`; a 1h bar must end at `12:00`, not `13:00`.
3. Store the source response hash, source-availability time and retrieval time
   alongside each used bar. A bar first available after the decision is named
   unavailable even if it was retrieved later from an archive; no forward fill,
   backward fill, synthetic zero, or silently substituted venue is allowed.
4. Never aggregate P&L across venues/products until all cash flows are converted
   using an identified FX/mark source at an identified timestamp. This P14
   proposal does not implement cross-venue portfolio valuation.

## Proposed adoption sequence

1. Agree a versioned market-context record and UI/API presentation with the
   shared-contract owners.
2. Add source-specific ingestion with archival storage, checksum and coverage
   validation; do not have replays call live fee pages.
3. Adopt spot fee-asset treatment and actual-fill reconciliation before making
   fee estimates user-facing.
4. Design and qualify linear and inverse perpetual accounting separately,
   including funding, leverage/margin, contract multiplier, liquidation and
   settlement. It is a contract extension, not a parameter to the spot ledger.
