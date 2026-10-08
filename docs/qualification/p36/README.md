# P36 LP model and data qualification

Status: **UNRESOLVED.** This package records the inputs and decisions needed for the bounded LP proof in [issue 12](https://github.com/edge-os-app/edge-os/issues/12). It does not establish an adopted model, qualified history, LP readiness, profitable edge, or execution authority.

## Local check

From the repository root, run:

```sh
python3 -B -m unittest docs/qualification/p36/test_p36.py -v
python3 -B docs/qualification/p36/check_p36.py
python3 -B docs/contracts/p02/check_contract.py
git diff --check
```

The P36 check calculates one authored mechanics example and compares each result with separately written expected literals. The example uses an unadopted constant-product model. It is not pool history or a venue choice. P02 is checked only to preserve its accepted spot contract and its explicit LP rejection; it does not qualify P36.

## Qualification result

The current output is `UNRESOLVED`. The package names required coverage for pool and model identity, position and fee history, timestamped prices, gas and rebalance costs, and a same-allocation comparator. It does not fill missing values with zero or claim coverage that was not observed. Unknown position or fee history leaves the affected claim unresolved.

The accounting separates ending inventory value, collected fees, impermanent-loss diagnostic, gas, rebalance cost, and net benefit. Net benefit uses the comparator once. Do not subtract the inventory loss a second time. Do not add fees to inventory value when they were reinvested.

The declared requirements come from the [accepted LP proof](../../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#15-lp-proof), the [spot-first build brief](../../EDGE_OS_BUILD_BRIEF.md#add-ons-and-the-lp-proof), the [P02 spot-only contract](../../contracts/P02_FIRST_SLICE_RECORDS.md), and [ADRs 0002](../../adr/0002-separate-evidence-and-financial-authority.md) and [0005](../../adr/0005-model-and-execution-authority-boundary.md). The reference case is independently worked and self-contained. No external LP source or real market history was used.

## Open decisions

Before a claim can move beyond this unresolved preparation, the builder must adopt the pool/model and asset universe, period and timing rules, data sources and rights, position and fee-history coverage, comparator and cash-flow convention, cost treatment, and supported LP actions. Add/remove/rebalance/collect semantics must name their position and timing effects. This output does not select those choices.

The package prepares stories 84 and 85 for later qualification. It does not build an LP simulator, adapter, user interface, wallet path, or execution route. P02 remains spot-only, and live LP actions require separate qualification.
