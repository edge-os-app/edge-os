# P12 spot replay profile — decision draft

Proposed version: `p12.spot-replay/1`. Status: not adopted and not complete. Builder adoption is required before any run can use this profile. P12 does not qualify a market dataset or an execution route.

This draft keeps three evidence states separate:

- Accepted: P02 is locally integrated at `8706aa2679ed184adf479b5be426d7a48d7ddfde`; its one-position, fixed-quote, no-add/no-partial strategy shape is the current consumer contract. The P02 file's earlier "pending builder acceptance" status is historical. P06 supplies five-minute UTC decisions, typed units, decimal-50 half-even arithmetic, complete-expression validation, scheduled history, and reasoned `UNKNOWN` values. P07 supplies a research-history profile, but no real pool history is qualified.
- Proposed: replay time, fill proxy, reservation order, reporting marks, and a narrow sizing subset below. These terms remain unadopted.
- Synthetic: the worked cases use invented prices, capital and a fee rate to check arithmetic only.

The saved strategy revision, P07 dataset revision, replay configuration and this profile version must be recorded by identity. A profile cannot make an unqualified dataset or unsupported strategy eligible.

## Proposed first replay scope

Reuse the accepted P02 shape: one strategy instance, one pool, one open position, fixed positive quote size, full exits only, no additions and no partial exits. Do not add duplicate strategy slots or new portfolio behavior to make a test case pass.

Keep the partial-exit and competing-reservation cases as independent accounting conformance examples. They do not add runtime support. The simulator must reject a strategy that asks for partial exits or multiple positions with a specific unsupported or unavailable result. It must preserve the saved strategy meaning.

This scope is the smallest match to current P02 behavior. Builder confirmation is still required because P12 asks for partial-exit and competing-reservation cases. If those requirements mean runtime support, define a separate strategy or portfolio contract before expanding this profile.

The proposed fill, fee, valuation and missing-data rules below are complete profile terms. Each term requires adoption before a run. The 10 bps fee, capital, prices, fills and marks in `docs/qualification/p12/WORKED_CASES.md` are synthetic examples, not defaults.

## Proposed replay rules

1. Bind one immutable strategy revision to one exact P07 dataset revision, market identity, half-open UTC window, warm-up range, quote asset and profile version. Require complete qualified coverage for all inputs needed by every scheduled decision and the next-bucket fill/mark points. P07's current real-data status remains unqualified, so no real replay is eligible today.
2. Evaluate the saved P06 expression at its scheduled bucket end only if every required input is qualified and `available_at <= decision_at`. Preserve all missing reasons. Future, late, incomplete, unqualified or absent inputs make the opportunity unavailable; they do not trigger, interpolate or carry forward.
3. At each bucket end, first settle any order decided at the prior bucket end. Then value the account. Then evaluate the current bucket's signal. An order decided at time `t` cannot use that signal bucket's close as its fill. The proposed fill proxy is the last qualified close of the next five-minute bucket, known at that bucket's end. This is a declared price proxy, not a claim of executable liquidity, latency, capacity or Kuru fills. If that close is unavailable, record no fill, release its reservation, and do not carry the old signal forward. A decision without a fully covered next bucket receives `NO_NEXT_BUCKET` and cannot fill.
4. While a position is open, evaluate its exit first. If the exit condition is true, reserve the full attributed base amount for an exit and do not also create an entry from that decision. When flat, evaluate entry and reserve quote notional plus fee from free cash. Reservations do not change account value until fill. Never reserve the same cash or base twice. A reservation that cannot be fully funded is rejected as `INSUFFICIENT_CASH`; no smaller order is inferred. This one-instance profile has no production multi-position tie-break. WC-02's stable slot-ID ordering is a separate hypothetical conformance example, not a supported portfolio model.
5. The accepted P02 subset is a fixed positive quote amount per entry, one open position per strategy instance, full exit only, `additions=false`, and `partial_exits=false`. Preserve that exact meaning. Requests for another action return an explicit unavailable/unsupported result before replay; the engine must not rewrite the strategy. The separate partial-exit arithmetic case does not add support.
6. The account denomination is the declared quote asset. Prices are quote/base, trade size and cash are quote units, holdings are base units, and fees are quote units. For an adopted fee of `f` basis points, `fee_quote = quote_notional * f / 10000`. A buy debits quote notional plus fee and acquires `quote_notional / fill_price` base. A sell credits `base_sold * fill_price - fee`. Fees are deducted from cash and included once in net account value. Track weighted-average acquisition cost per position and include entry fees in basis. Allocate basis proportionally on each exit and subtract each exit fee once from proceeds. This draft does not convert to USD or include unqualified gas, spread, routing, price impact or capacity.
7. At each scheduled valuation point, account value is `cash_quote + open_base * qualified_mark_quote_per_base`. The proposed mark is that valuation bucket's own qualified close. No earlier mark is carried into a later time. If a required mark is missing, keep cash and inventory, set account value to unavailable with its reason, and suppress total gain/loss and drawdown that depend on the gap. An unknown fee model makes the run unavailable; it is never treated as zero.
8. Record initial capital as the starting account value. This profile has no deposits or withdrawals. Gain/loss is final account value minus initial capital, in quote units. Trade count counts completed entry/exit pairs. Largest drawdown is the maximum peak-to-later-trough fall in the sampled account-value series, an absolute quote amount; missing account values make that metric unavailable. No percentage return or annualization is proposed.
9. Preserve open end inventory. Show its base quantity, acquisition basis, last mark and mark time separately. Do not call an unknown mark zero or realized profit. Keep proposed orders, rejections, fills, fees, quote/base reservations, cash, holdings, marks and reasons in chronological records.

## Decisions and consequences

| Choice | Proposed term | Alternative and consequence |
|---|---|---|
| Fill timing | Fill at the next five-minute bucket's qualified close after the decision | Same-bucket close can use information from after the signal. Event-level fills need a separate trade-level model. Each choice changes results. |
| Dataset | Bind the exact P07-qualified dataset revision and evaluation window per run. No real pool is selected here. | Pinning a pool now would imply qualification that P07 has not established. Synthetic-only input cannot prove real historical coverage. |
| Fee | Require an adopted quote-denominated fee rate per side. Label output as net of that declared fee only. | A venue schedule needs source evidence. Zero fees would produce gross output, not net output. Gas, spread, routing, impact and capacity stay outside this profile. |
| Mark and metrics | Use the close of each valuation bucket. Report quote-unit account value, gain/loss, trade count and absolute quote drawdown. | A stale mark hides missing data. Percent return and annualization need additional sampling and cash-flow choices. |
| Partial exit and competing reservations | Keep their calculations as conformance examples outside the one-position runtime. Reject unsupported requests. | Runtime support needs an adopted strategy or portfolio contract. The builder must decide whether the examples meet P12's acceptance checks. |
| First replay scope | One P02 strategy instance with fixed quote size, one position, full exit, no additions and no partial exits. | Broader support changes strategy meaning. A smaller scope than P02 or accepted release requires explicit builder approval. |

No term in this table has builder adoption. A change to any term needs a versioned profile update and new independent calculations.

## Acceptance mapping

| Requirement | Draft disposition | Adoption or evidence still needed |
|---|---|---|
| Exact dataset, coverage and version | Bind one immutable P07-qualified dataset and exact window | A real dataset is not qualified; select no real pool or period by inference |
| Schedule and usable signal time | P06 five-minute UTC schedule; use only inputs available by decision time | Adopt next-bucket close fill proxy and availability rule |
| Coincident exits/entries and capital | Exit before a new entry from the same instance; reserve quote plus fee; reject insufficient cash | One supported instance has no competing-position tie-break; WC-02 is hypothetical conformance arithmetic only |
| Sizing, additions and exits | Accepted P02: fixed quote size, one position per strategy, no additions/partial exits | Preserve compiler meaning; builder must confirm whether arithmetic conformance plus explicit unavailable behavior satisfies P12, or authorize broader runtime support |
| Fill, mark and fee model | Next scheduled close for fill; qualified scheduled close for mark; explicit quote fee | Adopt the model and actual per-run fee; synthetic rate is only an example |
| Missing data | No trigger/fill on missing required inputs; no mark carry; unavailable metrics remain unavailable | Ensure persisted result can represent unavailable metrics and reasons |
| Metrics and units | Quote-denominated gain/loss, trade count, account series, absolute drawdown | Adopt calculation identity; do not add return percentage or annualization |
| Partial exits and open end inventory | Partial exit is rejected under recommended subset; open inventory remains marked or unvalued | If partial exits are required, adopt a precise fraction/cost-basis rule before expanding |
| Simulated execution vs Flow | Separate deterministic replay records from live orders, receipts and wallet accounting | No Flow behavior is implied |

See [`../../qualification/p12/WORKED_CASES.md`](../../qualification/p12/WORKED_CASES.md) for independent literals and [`../../implementation/P12_SPOT_REPLAY_PROFILE.md`](../../implementation/P12_SPOT_REPLAY_PROFILE.md) for the current status and repeatable local checks.
