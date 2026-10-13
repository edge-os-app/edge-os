# P14 proposed replay-accounting extension

Status: **proposal only**, prepared on branch `quant/p14-replay-accounting` from
`abeedad498fc5aaf027938e099962aee41f7cee8` (`origin/main` on 2026-10-11).

This profile is a numerical experiment for P14, not an adoption of runtime
behavior. `p12.spot-replay/1` remains the sole adopted profile and continues to
reject additions, partial exits, and multiple positions. The implementation is
an isolated pure helper (`replay/proposed_accounting.py`) and is intentionally
not reachable from saved runs, API routes, schemas, or records.

## Proposed supported subset

The proposed ledger has a single quote-cash balance and a finite set of explicit
ASCII printable `position_id` values. Each position owns only its base inventory,
fee-inclusive weighted basis, cumulative realized result, and cumulative fees.
The cash balance is shared by every position.

- An entry or addition has an opaque `request_id`, quote notional, and explicit
  saved fractional fee/slippage/source tuple. A valid request reserves
  `quote_notional × (1 + fee_rate)` before a later settlement. That exact cost
  tuple is captured by the reservation; it cannot change between decision and
  fill.
- A buy uses the P12 formula `fill = close × (1 + slippage)`, acquires
  `notional / fill`, debits notional plus fee, and adds both to weighted basis.
- A partial sell specifies a strictly positive base amount at most equal to that
  position's inventory; a full exit records `base_amount=None` and resolves the
  currently free inventory at reservation time. It uses
  `fill = close × (1 - slippage)`, credits gross less fee, allocates basis as
  `basis × sold_base / base_before`, and realizes `net_proceeds - allocated_basis`.
- Simultaneous entry/addition requests are sorted by the stable tuple
  `(position_id, request_id)` in ordinary ASCII order. Each is either fully
  reserved or receives `INSUFFICIENT_CASH`; it is never resized. This is a
  proposal for the multi-position ordering rule, not a P12/1 rule.
- At a proposed scheduled tick, previously reserved exits settle, then prior
  entries settle, the account is marked, and current requests reserve for the
  next tick. Exit reservations take priority over an add for the same position
  (`EXIT_PRIORITY`); different positions then compete for free shared cash.
  Ticks must be contiguous, strictly ordered UTC five-minute boundaries. A
  missing bucket rejects the replay rather than allowing a later tick to settle
  an order silently. The final tick records `NO_NEXT_BUCKET` without reserving
  a new request.
- A missing or unusable cost tuple returns `COST_UNAVAILABLE`; a missing fill
  returns `FILL_UNAVAILABLE` and releases the reservation without a fee. A
  missing mark returns no account value and `MISSING_MARK:<position_id>` while
  retaining cash, inventory, and basis. None of these states is represented as
  zero.

## Proposed market-context, timeframe, and venue-accounting boundary

The original numerical helper has a deliberately narrow, quote-cash spot model.
It must not treat a changing public fee page as a historical fact. The separate
`replay/proposed_market_context.py` proposal establishes the record needed
before a later shared integration can compare venues or run multiple timeframes:

- A **venue instrument** names venue, venue symbol, product/contract kind,
  settlement asset and procedure, leverage, contract multiplier, the execution
  timeframe, every context timeframe, and the historical-data source. Spot
  cannot silently acquire leverage; derivatives cannot omit leverage,
  multiplier, or funding source.
- Every historical candle records its timeframe, UTC close time, retrieved time,
  primary source reference, and content hash. At a decision time the proposal
  accepts only the latest fully closed UTC bar for each requested timeframe. It
  neither uses a future/in-progress bar nor forward-fills a missing close.
- A **fee schedule snapshot** contains venue/instrument/product, effective UTC
  interval, retrieval time, primary source, account-tier reference, fee asset,
  distinct maker and taker rates, and a discount/promotion reference where
  applicable (the explicit value `NONE` means no discount/promotion was
  assumed). Selection must yield exactly one dated schedule; a gap or overlap
  is a named unknown, never zero cost.
- The current cash-ledger adapter accepts only a dated **spot**, quote-fee,
  non-rebate maker/taker rate. A base-token/discount-token fee, maker rebate,
  or any linear/inverse perpetual is explicitly refused rather than mispriced.
  Derivatives require a separate proposal for contract multiplier, margin,
  funding, liquidation, and settlement.

These are proposals, not an assertion that any venue's current published rate
reconstructs an old account fill. For a historical account run, the venue's
actual per-fill fee is preferred when available. Otherwise the run must display
the schedule snapshot, tier, fee asset, discount/promotion assumptions and its
effective period as an estimate.

The helper receives pre-qualified actions and explicitly supplied prices; it
does not evaluate P06 signals or define new evidence eligibility. It also has no
persistence, cross-asset valuation, order routing, capital flows, or permission
semantics. Extending P12/P13 saved inputs would need a versioned
contract/record design and a shared API/storage/UI lease.

## Relationship to accepted P12/P13 behavior

There is a direct boundary, not an ambiguity: P12/1 says additions, partial
exits, and multiple positions are unsupported before replay. Replacing that
rejection would conflict with the adopted profile. This proposal therefore adds
no branch to `run_spot_replay`, leaves `PROFILE_VERSION` unchanged, and cannot
interpret existing saved runs differently.

Before adoption, reviewers must decide at least: timing/availability integration
for multiple pending orders, position identity provenance, cross-position mark
aggregation across markets, and the saved record/profile version. The present
tests establish arithmetic and explicit failure states only.
