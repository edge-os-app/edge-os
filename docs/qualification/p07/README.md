# P07 offline qualification checks

These checks exercise the P07 pool and history profile with synthetic fixtures and one retained-report profile. They use the Python standard library. They make no network call, read no credential or environment file, and run no downloaded code. The accepted P02 checker is loaded from `docs/contracts/p02/check_contract.py` and is not modified.

Run from the repository root:

```sh
cd docs/qualification/p07
python3 -B -m unittest -v test_p07
cd ../../..
python3 -B docs/contracts/p02/check_contract.py
```

Files:

| File | Role |
|---|---|
| `qualification.py` | Decode, convert, ingest, coverage, buckets, reference windows, availability, schedule feasibility, profile validation, binding comparison, per-claim verdicts and the P02 projection. |
| `fixtures.json` | Synthetic profiles, logs and hand-written expectations. The `retained_report` entry copies figures from the Probe A report and nothing else. |
| `test_p07.py` | Tests at the public seams. |

Fixtures are labeled synthetic: addresses, hashes and amounts are invented. The retained-report entry is separate and contains no raw amounts, page hashes or private data. Fixture expectations were written by hand. They were not produced by the code under test.

What a pass shows: the contract rules behave as the specification and the accepted calculation conventions say, for the cases covered. What it does not show: the behavior of Envio, QuickNode or Monad, the completeness of any real window, historical delivery or finality, token mechanics of any real pool, execution attainability, fills, costs or profit. `qualify()` always lists those as not assessed.

Using it later: call `history_observations(profile, logs, window)` on retained pages and logs, add the evidence facts that only a provider read can give (chain id source, pool token reads, decimals reads, corroboration, finality), and call `qualify(profile, observations)`. A missing fact gives `UNRESOLVED`. Keep the profile and the result together. P02 cannot carry a limited binding.

`pytest`, `mypy` and `ruff` are not installed here. Nothing was installed. `python3 -B -m py_compile` was run on both Python files.
