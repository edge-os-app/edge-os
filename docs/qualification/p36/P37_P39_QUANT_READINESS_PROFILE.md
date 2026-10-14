# P36 → P37 → P38 → P39 proposed LP quantitative readiness profile

Status: **proposal only; P36 remains unresolved and P37–P39 are not started.**
The existing P36 mechanics fixture remains illustrative constant-product
arithmetic, not a venue/model selection.

The accompanying pure helper,
`apps/api/src/edge_os_api/replay/proposed_lp_accounting.py`, validates a named
model/evidence gate and computes only the already-declared reporting identity.
It does not reconstruct an AMM position or select a pool. Its tests enforce
unknown-versus-zero treatment, required evidence categories, no IL double count,
and no negative cost/reinvested-fee credit.

## Non-negotiable model-adoption gate

No LP calculation may substitute missing fields with zero or borrow a field from
another pool. Before P37 research or P39 simulation, one adopted profile must
identify:

- chain, venue, native pool ID, model/version, assets/decimals, fee tier, range
  or allocation parameters, and all supported action semantics;
- point-in-time observation/action timing, source versions/rights, coverage,
  finality/freshness boundary, and the applicable price kind for each valuation;
- timestamped position changes, fee accrual/collection/reinvestment, and any
  range/rebalance history;
- same-capital comparator, external cash-flow rule, cost/gas valuation source,
  and quote currency;
- the applicable contract multiplier/settlement/funding rules if the LP model
  embeds a derivative exposure.

Each field has three states: `KNOWN` with source identity, `NOT_APPLICABLE`
because the adopted model makes it irrelevant, or `UNKNOWN`. Only the first two
can enter a calculation. `UNKNOWN` is never zero.

## Proposed P37, P38 and P39 boundaries

| Ticket | Permitted quantitative output after the gate | Must remain separate |
|---|---|---|
| P37 research | Pool-specific observations, fee/inventory/cost findings, contrary evidence and limitations tied to the exact data package | It does not claim an executable LP rule or a profitable edge. |
| P38 rule review | Immutable, model-specific supported/rejected LP language with required data/cost fields and deterministic rejection reasons | It does not infer a simulation result or allow a live action. |
| P39 simulation | Inventory value, gross/accrued/collected fees, gas, rebalance costs, comparator value, net benefit and sensitivity/unknown states | It does not double-count impermanent loss, treat accrued fees as collected, or become execution authority. |

For P39, report both the accounting identity and every component. With a
declared common quote unit:

`net benefit = ending inventory + separately held fees - gas - rebalance cost - comparator ± declared external cash flows`

Impermanent loss is diagnostic only. Do not subtract it again after inventory
and comparator are already used in net benefit. If fees were reinvested, do not
add them both to inventory and a separate fee balance.

## Required adversarial cases before adoption

| Case | Required result |
|---|---|
| Missing position/fee history | The affected inventory/fee/net-benefit claim is `UNKNOWN`; no zero-fill. |
| Collected versus accrued versus reinvested fee | Report distinct values and prevent double count. |
| Partial removal or range change | Preserve old/new position identity, timing, residual inventory and cash flow. |
| Gas or rebalance cost unknown | Show the gross components and a valid cost-independent IL diagnostic, but withhold net benefit. |
| Comparator receives a deposit/withdrawal | Apply the identical declared external cash flow, or mark comparison unavailable. |
| Price/decimal/source mismatch | Refuse valuation until unit conversion and source time are identified. |
| Two model versions share a pool ID | Refuse aggregation; preserve the model/version identity. |
| Nonstationary fee regime or incomplete period | Preserve coverage limit and avoid extrapolating a period result. |

## Current completion condition

This profile is ready only to receive a controller-selected P36 model/data
packet. It does not select a venue, gather history, compile a rule, or run a
simulation. P36 has only an unresolved preparation/reference-case closure;
P37, P38 and P39 remain unstarted. Those choices need a separate assignment
after the adoption gate.

Run its focused proposal checks from the repository root:

```sh
(cd apps/api && uv run --frozen pytest -q tests/test_proposed_lp_accounting.py)
```
