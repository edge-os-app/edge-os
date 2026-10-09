# P12 spot replay profile status

The `p12.spot-replay/1` and `p12.essential-evidence/1` decisions were adopted by the builder on 2026-10-09. See [`the replay contract`](../contracts/p12/README.md) for the exact adopted terms and [`the worked cases`](../qualification/p12/WORKED_CASES.md) for independently calculated synthetic traces. Adoption records contract choices only; simulator implementation and qualification remain outstanding.

P12 preserves each saved P06 calculated value and its reasons, then checks action eligibility separately against the adopted `p12.essential-evidence/1` run-configuration descriptor. It does not turn a determinate result into UNKNOWN because of a retained nonessential or operation-unused reason. Whole-tree validation, timing checks, operation inputs, and hypothesis-essential evidence remain distinct. The descriptor binds exact strategy, run-configuration, dataset and market identities; requires explicit entry and exit field bindings; and resolves supported series using scheduled-relative offsets. The actual dependency sets must come from the user's hypothesis. P02 has no P12 binding field; P02/P06 contracts and behavior are unchanged.

The adopted first-release subset is one strategy instance, pool and position; fixed positive quote sizing; full exits only; no additions or partial exits; and explicit `NOT_REQUESTED` invalidation. This narrows P12 release support but does not change or shrink the accepted P02/P06 contracts. Boolean invalidation remains validated and preserved by P02/P06 and is rejected before P12 replay; P12 does not invent its meaning. Partial-exit and competing-reservation examples are separate arithmetic/conformance cases only. There is no production partial-exit behavior or portfolio/slot mechanism in this scope.

Adopted replay choices also include settle-prior-order, value, then evaluate the current signal; full exit before entry while open; a next scheduled five-minute close fill proxy conditional on explicit availability; no retry/interpolation/carry; last scheduled in-window terminal sample; saved fee/slippage rates with the stated exact formulas and no implicit overrides; and quote-denominated gain/loss and absolute drawdown. These are not executable fill evidence or all-in cost estimates. Gas, separate spread, routing, impact outside the declared slippage proxy, and capacity remain excluded.

WC-01 through WC-14 are independently authored synthetic calculations/traces. They include dated windows and a terminal in-window sample, P06 determinate results with missing reasons, late/future/empty inputs, reservation release, `NO_NEXT_BUCKET`, coincident ordering, saved cost mapping, repeatability identities and illustrative adopted descriptor literals. Partial-exit and competing-reservation examples remain arithmetic conformance cases only. They do not prove simulator support. No runtime implementation or actual user-authored essential binding is included in this documentation task.

No real pool history is qualified. A research close does not prove a fill. No simulation, market result, profit, provider behavior, persisted result retrieval, or live permission is claimed.

## Local checks

From repository root:

```sh
python3 -B docs/contracts/p02/check_contract.py
python3 -B docs/contracts/p06/check_contract.py
(cd docs/qualification/p07 && python3 -B -m unittest -q test_p07)
git diff --check
```

These check accepted prerequisites and whitespace only. The WC cases are hand-calculated documentation, not simulator output. Repeatability in WC-10 is a literal comparison, not runtime serialization or storage evidence.

## Limits

Adopted terms do not establish implementation, real-data qualification, executable fills, cost qualification, persisted-result retrieval or financial authority. Synthetic prices, capital, fills and rates are not defaults or qualified observations. No provider, Flow, wallet, transaction, publication or deployment was used. P08 ownership and application/compiler files are outside this P12 documentation task.
