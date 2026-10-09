# P12 spot replay profile status

P12 remains in decision preparation. The proposed contract is in [`the replay contract`](../contracts/p12/README.md); independently calculated synthetic traces are in [`the worked cases`](../qualification/p12/WORKED_CASES.md).

The draft preserves P06 calculated values/reasons and proposes a separate run-config binding for hypothesis-essential evidence by strategy field. It does not filter every retained reason: whole-tree validation, timing checks, operation inputs and essential evidence remain distinct. P02 has no such P12 binding today, so without an adopted binding eligibility is unresolved. The draft also names a proposed `NOT_REQUESTED`-only invalidation subset, maps saved fractional fee/slippage assumptions without implicit overrides, and declares dataset-admission, availability, terminal-sample and half-open-window behavior. None is an adopted product rule. The invalidation boundary may reduce P12 release scope and needs explicit builder adoption or a different adopted behavior. P06/P02 are unchanged.

WC-01 through WC-13 are independently authored synthetic calculations/traces. They include dated windows and a terminal in-window sample, P06 determinate results with missing reasons, late/future/empty inputs, reservation release, `NO_NEXT_BUCKET`, coincident ordering, saved cost mapping and repeatability identities. Partial-exit and competing-reservation examples remain arithmetic conformance cases only. They do not prove simulator support. The P12 issue/build brief must be interpreted explicitly if production partial-exit behavior is required; no runtime expansion is authorized here.

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

All replay terms remain proposed pending builder choice. Synthetic prices, capital, fills and rates are not defaults or qualified observations. No provider, Flow, wallet, transaction, publication or deployment was used. P08 ownership and application/compiler files are outside this P12 documentation task.
