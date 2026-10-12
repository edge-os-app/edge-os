# P14 proposed replay qualification matrix

Status: numerical proposal verification only. This matrix does not adopt the
extension, qualify a dataset/fill/cost source, or establish a saved runtime.

| Risk or invariant | Focused evidence | Expected protection |
|---|---|---|
| Accepted runtime regression | `test_spot_replay.py` keeps `additions` and `partial_exits` rejected under P12/1 | Existing saved runs retain full-exit/default meaning. |
| Fee-inclusive weighted basis | Buy → add → partial exit → add → full exit worked trace | Entry fees appear once in basis; partial-sale basis is proportional; exit fees appear once in net proceeds. |
| Cost drift after an action decision | Reservation stores the cost tuple and settlement has no replacement cost parameter | A later caller cannot silently substitute fee/slippage/source values. |
| Adverse slippage and both-side fees | Buy at `close × (1 + slippage)`, then full sell at `close × (1 - slippage)` | Fill price, basis, realized result, and cash use the saved directional formulas. |
| Invalid or unknown costs | `None`, blank source, negative/excessive fee/slippage | `COST_UNAVAILABLE`; no reservation, fill, fee, or implicit zero-cost fallback. |
| Shared-cash double spend | Same-tick two-position requests need more than available cash | Stable `(position_id, request_id)` order; the loser is `INSUFFICIENT_CASH`, never resized. |
| Inventory double sale | Full exit reserves all free base; second exit fails; unavailable fill releases it | Inventory cannot be reserved twice and a failed fill remains fee-free/retry-free. |
| Request identity collision | The same identifier is submitted for an exit and an entry | `DUPLICATE_REQUEST`; order state is not overwritten. |
| Invalid fills | Zero, negative, and non-finite buy and sell prices | `NON_POSITIVE_FILL`; no cash, inventory, basis, or fee mutation. |
| Unknown valuation | One of two open positions has no mark | Cash/inventory/basis stay known; aggregate value is unavailable with the named missing-mark reason. |
| Timing/order | Scheduled driver test | Prior exits settle, then prior entries settle, mark, reserve current actions; same-position exit wins over add. |
| Terminal boundary | Terminal entry request | `NO_NEXT_BUCKET`; no new reservation or fill. |
| Schedule integrity | Empty, naïve, non-UTC, off-grid, and non-increasing ticks | The proposal refuses them before replay. |
| Determinism | Run identical proposed inputs twice | Samples, events, and positions compare identically. |
| Starting capital | Negative initial cash | Replay construction rejects it. |
| Multi-timeframe context | 5m and 1h source-stamped bars at one decision time | Only fully completed UTC bars are accepted; missing/future/in-progress context cannot become a price. |
| Venue/product facts | Spot versus linear/inverse declaration | Settlement procedure/asset, contract kind, multiplier, funding source and derivative leverage are explicit; an unknown cannot inherit a spot default. |
| Fee provenance | Dated schedule selection | Exactly one applicable source/tier/fee-asset schedule is required; gaps and overlaps have named failures. |
| Fee role/asset/contract boundary | Maker versus taker, quote asset versus other fee asset, spot versus derivative | The spot ledger refuses an unsupported fee unit, rebate, or contract instead of emitting false P&L. |

Run the numerical regression set from the repository root:

```sh
(cd apps/api && uv run --frozen pytest -q \
  tests/test_proposed_replay_accounting.py \
  tests/test_proposed_replay_accounting_edges.py \
  tests/test_proposed_market_context.py \
  tests/test_spot_replay.py)
```

The matrix intentionally excludes API/database/UI persistence, P06 action
evaluation, P07 data qualification, real execution capacity, real costs, and
wallet authority. Those require an adopted profile and the later shared lease.
