# P42 bounded calibration result — 2026-10-16.1

Status: **UNRESOLVED.** This is proposal-only, authored-synthetic calibration
evidence. It is not market evidence, STAT-Q01 qualification, operational
admission, a formal-support claim, or trading authority.

## Frozen inputs and execution

This run executes profile `edge-os.stat-q01-qprep/2026-10-16.1` and the frozen
plan in [`CALIBRATION_PLAN.md`](CALIBRATION_PLAN.md). Its exact source candidate
is `dee4aeeaa6aeda64c9559aae517d4affb390ffeb`; the evidence-only child commit
adds this report and result without changing that source, profile, or plan. The
calculation intentionally has no network, provider, model, wallet, market-data,
or protected-holdout input.

Run from `apps/api` on 2026-10-16:

```sh
uv run --frozen python -m edge_os_api.research.statistical_calibration \
  --plan ../../docs/qualification/p42/CALIBRATION_PLAN.md \
  --output ../../docs/qualification/p42/CALIBRATION_RESULT.json
```

| Recorded input or output | SHA-256 |
|---|---|
| Candidate profile | `b98534ab3ea2560966989b2213ad13721f1d6a105eab8c7c45670d93274ba3ae` |
| Frozen plan | `25c0b731b32f77dd6c7aa7bc919914ca92fdc35e05ca08115590c9f831d442cd` |
| Failure-fixture manifest | `1fade7eaf617e2ba9e96c92da3f2cf63caeb6f4379cd0832d8856019d06a58a1` |
| Deterministic calculation fingerprint | `b409a87571c91145ab137e8ac27d2848310d240c77eb81595aca922469e6db8e` |
| Raw result artifact | `3151f4a9826c1285cc165750444e2d596cf3ec395e2050c3df5dcf7f55fe4d21` |

All three experiments completed. The run took `28.19010312499995` seconds.
Peak traced allocations were 1,643,989 bytes (dependent null), 1,520,803 bytes
(known effect), and 1,105,561 bytes (nonstationary), below the 256 MiB cap.
The predeclared execution shape stayed one process/worker, 199 draws, the listed
64/64/32 seed sets, 51,962,880 planned bootstrap slot-visits, 180 seconds per
experiment, and 540 seconds total.

## Method repair and preserved history

The earlier `/2` run treated 576 pointwise intervals as independent in a single
pooled Wilson interval. That is not valid: each history contributes nine
dependent `comparison × sensitivity` outcomes. Its failed plan, report, and raw
artifact remain unchanged as
[`CALIBRATION_REPORT_2026-10-14.2.md`](CALIBRATION_REPORT_2026-10-14.2.md)
and
[`CALIBRATION_RESULT_2026-10-14.2.json`](CALIBRATION_RESULT_2026-10-14.2.json).
They are historical failed evidence, not re-scored evidence.

This `/3` run uses one Bernoulli coverage observation per declared series per
generated history. Thus each Wilson interval has denominator 64, never 576.
The pooled count remains descriptive only. A missing interval, truth, series, or
history leaves coverage incomplete and the relevant check unresolved. The IID
diagnostic is compared only against the corresponding joint `NOMINAL` series.
The outer scenario seeds are unchanged, but the new profile identity is part of
the SHA-derived bootstrap/IID seed namespace, so this is a separately identified
experiment rather than a relabelled rerun.

The same revision also binds a selected finalist to the canonical SHA-256 of
its complete frozen family. Cross-family selection, including a reused
comparison ID or a copied family hash, is denied before holdout access. Finalist
ordering now compares exact Decimal contrasts directly and is stable at caller
Decimal precision 28 and 50.

## Results against the frozen criteria

| Experiment | Retained result | Criterion outcome |
|---|---|---|
| Dependent null | 0/64 joint false finalists; one-sided 95% Wilson upper `0.040559499465846941946678343418878102667010757751140`. Every joint series was complete. `DOUBLE` coverage was 58/64 (0.90625; Wilson `[0.81017120400354403636200009892716497253654236990532, 0.95632174741480162905887843138313529781997201923690]`); every `HALF` and `NOMINAL` series was 61/64 (0.953125; Wilson `[0.87100346259906314243624496681606505282677828758673, 0.98393098321370702284088877853003909487856468491805]`). Descriptive pooled coverage was 540/576 only. | The false-finalist and corrected per-series coverage checks passed. The dependence discriminator failed: IID had 0/64 false finalists and each matching IID rate was 60/64 (0.9375) versus joint-NOMINAL 61/64 (0.953125), a 0.015625 difference below 0.05. |
| Known effect | `positive` selected 64/64; one-sided 95% Wilson lower `0.95944050053415305805332165658112189733298924224886`; `negative` selected 0 times; all 64 decisions were sensitivity-stable. Every `DOUBLE` series was 60/64 (0.9375); every `HALF`/`NOMINAL` series was 63/64 (0.984375); pooled descriptive coverage was 558/576. | Passed the frozen preliminary checks. It does not compensate for another failed experiment or establish support. |
| Nonstationary | 0 finalists; 13/32 `UNRESOLVED_SELECTOR_RULE`; 19/32 `UNRESOLVED_NO_FINALIST`. | Failed: 13/32 (40.625%) is below the required 80% rule-based unresolved rate. A bare no-finalist is intentionally not counted as the safeguard. |
| Failure fixtures | All 18 fixtures returned their exact expected status, including missing-versus-zero, lower/upper partition boundaries, one-shot access, runner-up/revision/re-access denials, and different-ID, reused-ID, and copied-hash cross-family finalist denials. | Passed. |

Because every applicable criterion must pass, the result is `UNRESOLVED`. No
tolerance, seed, profile setting, generator, or finite resource limit was
changed after this result.

## Checks and remaining boundaries

Before the run, the candidate passed:

```sh
cd apps/api
uv run --frozen pytest -q tests/test_effect_comparison.py \
  tests/test_statistical_preparation.py tests/test_statistical_partition.py \
  tests/test_statistical_calibration.py
uv run --frozen ruff check src/edge_os_api/research/statistical_preparation.py \
  src/edge_os_api/research/statistical_partition.py \
  src/edge_os_api/research/statistical_calibration.py \
  tests/test_statistical_preparation.py tests/test_statistical_partition.py \
  tests/test_statistical_calibration.py
uv run --frozen python -m compileall -q src tests
```

The focused command reported 52 passed with one existing Starlette/httpx
deprecation warning. Final candidate checks additionally include the P02
contract checker and diff/ancestry checks.

- The input histories are authored synthetic data only. No market/provider/model
  data or protected market holdout was read.
- The numerical profile and pure holdout ledger are not adopted runtime behavior.
  Durable one-shot enforcement needs transactional persistence and independently
  verified source lineage.
- ST-10 operational admission, application wiring, method adoption, and any
  support/trading claim remain unrun and unauthorized.
- This exact final commit still requires two independent candidate-bound reviews
  and a separate controller-arranged gate before acceptance or integration.
