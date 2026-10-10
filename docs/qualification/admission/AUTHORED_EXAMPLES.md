# Authored examples for the admission local stage

Every number here is authored and synthetic. Identifiers and amounts are
invented for local determinism. They do not describe a live account, token,
route, provider response or production limit.

## Approval snapshot (authored)

| Field | Value |
|---|---|
| identity | owner, `agent-a`, `wallet-a`, `monad:143`, `strategy-a-v3`, `mandate-a-v1` |
| policy binding | `policy-a-v1` |
| state | `ACTIVE` |
| quote allowance (USDC, 0 decimals) | 500 |
| base allowance (MOE, 0 decimals) | 1000 |
| gas allowance (native, 0 decimals) | 50 |
| per-action gas | 2 |
| fixture label | `SYNTHETIC_AUTHORED` |

## Holdout holdings snapshot (authored)

Reconciled balances: USDC 5000, MOE 40, native 20. These large balances do not
raise authority; the approval governs.

## Worked examples

Entry: quantity 10 base, quote input 110. Reservations are quote capital 110,
base sell capacity 10, base inventory 10, gas 2. After admission the remaining
allowances are quote 390, base 990, gas 48. This matches `remaining = approved -
consumed - reserved`.

Confirmed entry: quote consumed becomes 110; base sell capacity and inventory
reservation settle; the position holds inventory 10; gas consumed is the
reconciled actual gas.

Exit: quantity 5 base against a position that holds 10. Reservations are base
sell input 5, base inventory 5, gas 2. A confirmed exit consumes base 5 and
leaves position inventory 5. An exit without a known mark is denied.

Overdraw: with approved quote 500, two entries of quote input 300 each admit
one and deny the second. A second entry at quote input 300 has remaining 200
available, so it fails closed with `CAPACITY_UNAVAILABLE`.

## Cross-check

The admission tests compute these expected values as literals, not by calling
the code under test. Direct SQL reads the saved decision and reservation rows.
