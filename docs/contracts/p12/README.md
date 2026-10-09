# P12 spot replay profile — decision draft

Status: proposed profile; not complete. Builder adoption is required before this can be used as a production simulation contract. The private `ADOPTION_REQUEST_R3.md` is the current request. It corrects the P02 status and limits the recommendation to the accepted one-position strategy shape. P12 does not qualify a market dataset or a realistic execution route.

This draft keeps three evidence states separate:

- Accepted: P02 is locally integrated at `8706aa2679ed184adf479b5be426d7a48d7ddfde`; its one-position, fixed-quote, no-add/no-partial strategy shape is the current consumer contract. The P02 file's earlier "pending builder acceptance" status is historical. P06 supplies five-minute UTC decisions, typed units, decimal-50 half-even arithmetic, complete-expression validation, scheduled history, and reasoned `UNKNOWN` values. P07 supplies a research-history profile, but no real pool history is qualified.
- Proposed: replay time, fill proxy, reservation order, reporting marks, and a narrow sizing subset below. These terms remain unadopted.
- Synthetic: the worked cases use invented prices, capital and a fee rate to check arithmetic only.

The saved strategy revision, P07 dataset revision, replay configuration and this profile version must be recorded by identity. A profile cannot make an unqualified dataset or unsupported strategy eligible.

## Recommended narrow option

The recommended terms and alternatives are in the private `ADOPTION_REQUEST_R3.md` returned with this candidate. The accepted P02 strategy shape has one position per instance, fixed quote sizing, no additions and no partial exits. The recommendation reuses that shape and keeps partial-exit and competing-reservation arithmetic as clearly labeled conformance cases outside runtime support. This does not prove the current P12 acceptance is satisfied. If those cases must describe production behavior, the builder must authorize a strategy/portfolio extension and P08 coordination.

Every value that affects user choice must be adopted before a run. Example fees and example capital in `docs/qualification/p12/WORKED_CASES.md` are not defaults. The partial-exit and competing-reservation cases are arithmetic illustrations until the corresponding strategy and portfolio behavior is adopted and implemented. This draft does not satisfy those P12 acceptance items.

## Proposed replay rules

1. Bind one immutable strategy revision to one exact P07 dataset revision, market identity, half-open UTC window, warm-up range, quote asset and profile version. Require complete qualified coverage for all inputs needed by every scheduled decision and the next-bucket fill/mark points. P07's current real-data status remains unqualified, so no real replay is eligible today.
2. Evaluate the saved P06 expression at its scheduled bucket end only if every required input is qualified and `available_at <= decision_at`. Preserve all missing reasons. Future, late, incomplete, unqualified or absent inputs make the opportunity unavailable; they do not trigger, interpolate or carry forward.
3. At each bucket end, first settle any order decided at the prior bucket end. Then value the account. Then evaluate the current bucket's signal. An order decided at time `t` cannot use that signal bucket's close as its fill. The proposed fill proxy is the last qualified close of the next five-minute bucket, known at that bucket's end. This is a declared price proxy, not a claim of executable liquidity, latency, capacity or Kuru fills. If that close is unavailable, record no fill, release its reservation, and do not carry the old signal forward. A decision without a fully covered next bucket receives `NO_NEXT_BUCKET` and cannot fill.
4. While a position is open, evaluate its exit first. If the exit condition is true, reserve the full attributed base amount for an exit and do not also create an entry from that decision. When flat, evaluate entry and reserve quote notional plus fee from free cash. Reservations do not change account value until fill. Never reserve the same cash or base twice. A reservation that cannot be fully funded is rejected as `INSUFFICIENT_CASH`; no smaller order is inferred. This one-instance profile has no production multi-position tie-break. WC-02's stable slot-ID ordering is a separate hypothetical conformance example, not a supported portfolio model.
5. The accepted P02 subset is a fixed positive quote amount per entry, one open position per strategy instance, full exit only, `additions=false`, and `partial_exits=false`. Preserve that exact meaning. Requests for another action return an explicit unavailable/unsupported result before replay; the engine must not rewrite the strategy. The separate partial-exit arithmetic case does not add support.
6. The account denomination is the declared quote asset. Prices are quote/base, trade size and cash are quote units, holdings are base units, and fees are quote units. A buy debits quote notional plus fee and acquires `quote_notional / fill_price` base. A sell credits `base_sold * fill_price - fee`. Fees are deducted from cash and included once in net account value. This draft does not convert to USD or include unqualified gas, spread, routing, price impact or capacity.
7. At each scheduled valuation point, account value is `cash_quote + open_base * qualified_mark_quote_per_base`. The proposed mark is that valuation bucket's own qualified close. No earlier mark is carried into a later time. If a required mark is missing, keep cash and inventory, set account value to unavailable with its reason, and suppress total gain/loss and drawdown that depend on the gap. An unknown fee model makes the run unavailable; it is never treated as zero.
8. Record initial capital as the starting account value. This profile has no deposits or withdrawals. Gain/loss is final account value minus initial capital, in quote units. Trade count counts completed entry/exit pairs. Largest drawdown is the maximum peak-to-later-trough fall in the sampled account-value series, an absolute quote amount; missing account values make that metric unavailable. No percentage return or annualization is proposed.
9. Preserve open end inventory. Show its base quantity, acquisition basis, last mark and mark time separately. Do not call an unknown mark zero or realized profit. Keep proposed orders, rejections, fills, fees, quote/base reservations, cash, holdings, marks and reasons in chronological records.

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

See [`../qualification/p12/WORKED_CASES.md`](../qualification/p12/WORKED_CASES.md) for independent literals and [`../implementation/P12_SPOT_REPLAY_PROFILE.md`](../implementation/P12_SPOT_REPLAY_PROFILE.md) for the current status and repeatable local checks.
