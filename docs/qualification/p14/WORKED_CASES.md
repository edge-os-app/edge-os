# P14 proposed accounting worked cases

Status: **proposal-only synthetic arithmetic**. These cases use the P12 Decimal
50/half-even calculation context, a quote asset `Q`, base asset `B`, fee rate
`0.001`, zero slippage, and source `synthetic-p14`. They are independent of
P12/1 runtime support and do not imply qualified fills, data, profitability, or
financial permission.

## Add, partial exit, add again, full exit

Start with `1,000 Q`, zero inventory, and position `position-a`. All table
values are quote units except inventory. Fees are cumulative; realized result is
cumulative; an em dash means no basis was allocated by that event.

| Event | Calculation | Cash Q | Inventory B | Allocated basis Q | Cumulative fees Q | Cumulative realized Q | Remaining basis Q |
|---|---|---:|---:|---:|---:|---:|---:|
| Buy 400 Q at 8 | acquire `400 / 8 = 50`; entry fee `.4` | 599.600 | 50 | — | .400 | 0 | 400.400 |
| Add 200 Q at 10 | acquire `200 / 10 = 20`; entry fee `.2` | 399.400 | 70 | — | .600 | 0 | 600.600 |
| Partial exit 28 B at 12 | gross `336`; exit fee `.336`; net `335.664`; allocate `600.6 × 28 / 70 = 240.240` | 735.064 | 42 | 240.240 | .936 | 95.424 | 360.360 |
| Add 100 Q at 9 | acquire `100 / 9 = 11.111111111111111111111111111111111111111111111111`; fee `.1` | 634.964 | 53.111111111111111111111111111111111111111111111111 | — | 1.036 | 95.424 | 460.460 |
| Full exit all inventory at 11 | gross `5258 / 9`; fee `2629 / 4500`; net `583.638`; allocate remaining `460.460` | 1218.602 | 0 | 460.460 | 1.6202222222222222222222222222222222222222222222222 | 218.602 | 0 |

The last exit contributes `123.178 Q` realized result; the final cumulative
result is `95.424 + 123.178 = 218.602 Q`. Final cash minus initial cash also
equals `218.602 Q`. Entry fees appear exactly once in basis; each exit fee is
subtracted exactly once from sale proceeds.

## Competing shared-cash requests

Start with shared cash `500 Q` and no inventory. At the same proposed decision,
two positions request `300 Q` entries. Each needs `300 + .3 = 300.3 Q`.
Ordering is the proposed stable ASCII tuple `(position_id, request_id)`.

| Proposed order | Request | Outcome | Cash Q | Reserved Q | Free cash Q | Fee charged |
|---:|---|---|---:|---:|---:|---:|
| 1 | `(position-a, request-a)` | `RESERVED` | 500 | 300.3 | 199.7 | 0 |
| 2 | `(position-b, request-b)` | `INSUFFICIENT_CASH` (not resized) | 500 | 300.3 | 199.7 | 0 |
| Settlement at 5 Q/B | `request-a` | acquire 60 B, fee `.3` | 199.7 | 0 | 199.7 | .3 |

`request-b` creates neither a reservation nor a fill nor a fee. Swapping the
identifiers changes the winner by design; that dependency is visible and tested.

## Unknowns and retained inventory

- With no usable saved cost tuple, `COST_UNAVAILABLE` leaves cash and inventory
  unchanged; no zero-cost fallback exists.
- A reserved entry whose next fill is unavailable returns `FILL_UNAVAILABLE`,
  releases its full reservation, and charges no fee or inventory.
- An unsold `50 B` position with basis `400.400 Q` and a missing mark retains
  those known quantities, but aggregate account value is `None` with
  `MISSING_MARK:position-a`; it is not cash plus zero inventory value.
