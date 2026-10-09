# P12 spot replay profile status

P12 is in decision preparation. The proposed profile and independent synthetic calculations are in [`the replay contract`](../contracts/p12/README.md) and [`the worked cases`](../qualification/p12/WORKED_CASES.md).

The profile preserves P06's five-minute UTC schedule, decimal and unit rules, complete-tree checks and missing-input reasons. It preserves accepted P02 strategy meaning and P07's limit. Actual pool history remains unqualified, and a research close does not prove a fill.

The partial-exit and competing-reservation examples are accounting conformance examples. The supported strategy shape has one position and no partial exits. The examples do not establish runtime support or close the related P12 acceptance checks. No real simulation or profit result is claimed.

## Local checks

Run from the repository root:

```sh
python3 docs/contracts/p02/check_contract.py
python3 docs/contracts/p06/check_contract.py
(cd docs/qualification/p07 && python3 -B -m unittest -v test_p07)
git diff --check
```

The P12 worked cases are literal documentation calculations, not simulator output. Their independent reconciliations are in the case file. This ticket changes no application or simulator code. Any change to strategy or portfolio meaning needs explicit scope and ownership.

## Limits

The proposed P12 terms are not adopted. No real dataset is qualified. The 10 bps fee, prices, capital, fills and marks in the worked cases are synthetic. No provider, Flow, wallet, transaction, publication or deployment was used.
