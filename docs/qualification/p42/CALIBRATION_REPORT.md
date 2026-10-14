# P42 bounded calibration result

Status: **UNRESOLVED.** This is a proposal-only authored-synthetic calibration
record. It is not market evidence, a STAT-Q01 qualification, operational
admission, or trading authority.

## Exact source, evidence repair, and command

The first frozen-profile run used source candidate
`7e99be8912a03e3224f298532d1b5f8676d8f3f8` on branch
`quant/p42-statistical-preparation`, rebased on
`c4bc2a405f872ad284639a8de84712f7bc569b0f`. It returned `UNRESOLVED` and
produced raw-run artifact SHA-256
`709ca468a9a50d2aaf8cdef85ccd84808fbff8696870ccc6d74a4841e1cff044`.

A later local repeat exposed a reporting defect: that artifact's sorted JSON
also contained elapsed time and `tracemalloc` peak allocations, so its raw
SHA-256 changed despite identical numerical records. The first artifact remains
historical failed-run evidence at that source commit; it is not relabelled as
byte-for-byte reproducible.

Source candidate `530c09a3811db8b12124c1d45b3f899a16e15526` repairs only that
evidence identity boundary. It emits schema `/2` with a
`calculation_sha256` over deterministic calculation content and retains raw
interpreter/platform, elapsed-time, and peak-allocation telemetry separately.
It does **not** alter the frozen profile, plan, seeds, generator, method,
criteria, resource limits, or the `UNRESOLVED` outcome. The candidate profile
remains `edge-os.stat-q01-qprep/2026-10-14.2`.

Run from `apps/api` on 2026-10-14:

```sh
uv run --frozen python -m edge_os_api.research.statistical_calibration \
  --plan ../../docs/qualification/p42/CALIBRATION_PLAN.md \
  --output ../../docs/qualification/p42/CALIBRATION_RESULT.json
```

The repaired run returned `{"status":"UNRESOLVED"}` after
26.967971041915007 seconds. Its raw-run artifact is
[`CALIBRATION_RESULT.json`](CALIBRATION_RESULT.json), SHA-256
`9cfc18d0f162924048dbc257d117cbcafef432a4cf19ec59002619c909f05703`.
Its deterministic calculation fingerprint is
`72755af0c24b79e3f5de2cc1386c50043f9b9806cf87fca63ae3e5b3f94ba673`.

An independent repeat from the same `530c09a` source candidate returned the
same `UNRESOLVED` status and exactly the same calculation fingerprint. Its raw
JSON differed only in elapsed time and traced-allocation peak telemetry, as
expected; it did not change history hashes, selections, intervals, fixtures,
assessments, or the suitability result.

| Recorded input | SHA-256 |
|---|---|
| Candidate profile | `0e15049d4b71ebed8bedf71d40d91faf4082c8c9bf3eade399a03ba5e09be564` |
| Frozen plan | `745832d584b101135250c48f8fd0eaef803423e49437c7126f691bc74e225df4` |
| Failure-fixture manifest | `bde51e822e4c95bc6518348f82fbd5faee3a4acdf0bdc26a09e47fed4c295b3a` |

The runner used one process and worker; 51,962,880 planned bootstrap slot
visits; a 180-second per-experiment limit; a 540-second total limit; and a
256 MiB traced-allocation limit. All three experiments completed without a
termination reason. This run's traced peaks were 1,608,464, 1,492,339, and
1,091,461 bytes for dependent null, known effect, and nonstationary cases.

## Results against the frozen criteria

| Experiment | Retained result | Frozen criterion outcome |
|---|---|---|
| Dependent null | 0/64 joint false finalists; one-sided 95% Wilson upper `0.040559499465846941946678343418878102667010757751140`; joint coverage 534/576 with Wilson interval `[0.90290312403902876638461335246572215886531779710767, 0.94560467497322232778286077146381087549714894448853]`. IID had 0/64 false finalists and coverage 174/192. | False-finalist and interval checks passed, but the dependence discriminator failed: IID had neither two more false finalists nor coverage at least 0.05 lower than joint. |
| Known effect | `positive` selected 64/64; one-sided 95% Wilson lower `0.95944050053415305805332165658112189733298924224886`; `negative` selected 0 times; coverage 552/576; all 64 sensitivity-stable. | Passed its frozen preliminary checks. This does not offset another experiment's failure or constitute support. |
| Nonstationary | 0 finalists; 13/32 `UNRESOLVED_SELECTOR_RULE`; 19/32 plain `UNRESOLVED_NO_FINALIST`. | Failed: only 13/32 (40.625%) were unresolved through the required selector/sensitivity/family-rule path, below the frozen 80% criterion. A bare no-finalist result is intentionally not counted as a qualifying nonstationarity safeguard. |
| Failure fixtures | All 15 retained their exact expected status, including missing-versus-zero, lower/upper partition bounds, pre-label access, failed confirmation, wrong finalist, runner-up denial, revision mismatch, and re-access denial. | Passed. |

Because every applicable criterion must pass, the result remains `UNRESOLVED`.
No tolerance, seed list, profile setting, threshold, or method was altered after
observing these results.

## Checks on the source candidate

The following completed before the calibration run:

```sh
cd apps/api
uv run --frozen pytest -q tests/test_effect_comparison.py \
  tests/test_statistical_preparation.py tests/test_statistical_partition.py \
  tests/test_statistical_calibration.py
uv run --frozen python -m compileall -q src tests
python3 ../../docs/contracts/p02/check_contract.py
git diff --check origin/main...HEAD
```

Results: 47 tests passed; compilation passed; the P02 checker passed 39
fixtures and 10 record examples. Pytest emitted one existing Starlette/httpx
deprecation warning. The P02 check remains in-memory only and does not verify
server, storage, concurrency, provider, or production-cost behavior.

## Remaining boundaries

- The data are authored synthetic histories only; no market/provider/model or
  protected-market holdout was read.
- The proposed profile and pure holdout ledger are not adopted runtime behavior.
  Durable one-shot enforcement needs a transactional, persisted append-only
  ledger and independently verified source lineage.
- ST-10 operational admission, application wiring, calibration-method adoption,
  and any support/trading claim remain unrun and unauthorized.
- This source candidate still needs the two original independent exact-candidate
  reviews and the separately arranged gate. Pre-calibration adversarial audits
  guided repairs but are not those formal reviews.
- Raw artifact hashes identify a particular bounded execution, while
  `calculation_sha256` identifies its deterministic numerical content. Neither
  hash is formal support or a substitute for independent review.
