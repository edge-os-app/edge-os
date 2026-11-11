# P42 bounded calibration result — 2026-10-17.1

Status: **UNRESOLVED.** This is proposal-only, authored-synthetic calibration
evidence. It is not market evidence, STAT-Q01 qualification, operational
admission, a formal-support claim, or trading authority.

## Frozen inputs and execution

This run executes profile `edge-os.stat-q01-qprep/2026-10-17.1` and the frozen
plan in [`CALIBRATION_PLAN.md`](CALIBRATION_PLAN.md). Its exact source candidate
is `1192915336806df1e617b2078dfb89a53e2add6e`; the evidence-only child commit
adds this report and result without changing that source, profile, or plan. The
calculation intentionally has no network, provider, model, wallet, market-data,
or protected-holdout input.

Run from `apps/api` on 2026-10-17:

```sh
uv run --frozen python -m edge_os_api.research.statistical_calibration \
  --plan ../../docs/qualification/p42/CALIBRATION_PLAN.md \
  --output ../../docs/qualification/p42/CALIBRATION_RESULT.json
```

| Recorded input or output | SHA-256 |
|---|---|
| Candidate profile | `9c36c82dd29b2e3e6b35886f36db5345d12c75089f35f22cbacec26137806c5b` |
| Frozen plan | `16468130820a1e1725a9cc39fc8911134ea425e7a50af4acb9e5f2f6461175a7` |
| Failure-fixture manifest | `7580d25a03a45e9211ee9edf021f91d168d6ec55d7867c1f2e0851030b909e5e` |
| Deterministic calculation fingerprint | `02ce2833e252451f4a99afe4e922b2b9920287ffe3dd9af3a6f539667c0c8ad2` |
| Raw result artifact | `efdd50f7fd1ef5d7e547f18bcffcad1d478e4f4afc77d33b1b84f263e8700666` |

All three experiments completed. The run took `28.134656041998824` seconds.
Peak traced allocations were 1,643,939 bytes (dependent null), 1,520,703 bytes
(known effect), and 1,105,411 bytes (nonstationary), below the 256 MiB cap.
The predeclared execution shape stayed one process/worker, 199 draws, the listed
64/64/32 seed sets, 51,962,880 planned bootstrap slot-visits, 180 seconds per
experiment, and 540 seconds total.

## Method repair and preserved history

The `/2` profile incorrectly treated 576 pointwise intervals as independent;
its failed plan, report, and raw artifact remain unchanged as
[`CALIBRATION_REPORT_2026-10-14.2.md`](CALIBRATION_REPORT_2026-10-14.2.md)
and
[`CALIBRATION_RESULT_2026-10-14.2.json`](CALIBRATION_RESULT_2026-10-14.2.json).
The prior `/3` run corrected that uncertainty but did not reject a forged
started ledger whose finalist was absent from the retained checked family. Its
frozen profile, plan, report, and raw artifact are separately preserved as
[`STAT_Q01_CANDIDATE_PREPARATION_PROFILE_2026-10-16.1.md`](../../implementation/STAT_Q01_CANDIDATE_PREPARATION_PROFILE_2026-10-16.1.md),
[`CALIBRATION_PLAN_2026-10-16.1.md`](CALIBRATION_PLAN_2026-10-16.1.md),
[`CALIBRATION_REPORT_2026-10-16.1.md`](CALIBRATION_REPORT_2026-10-16.1.md),
and
[`CALIBRATION_RESULT_2026-10-16.1.json`](CALIBRATION_RESULT_2026-10-16.1.json).

This revision checks ledger-finalist membership before either access or
resolution and adds a fixed forged-ledger failure fixture. It retains
per-history, per-series Wilson accounting: each Wilson denominator is 64, never
576, and pooled counts are descriptive only. The outer scenario seeds are
unchanged, but the new profile identity is part of the SHA-derived bootstrap/IID
seed namespace, so this is a separately identified experiment rather than a
relabelled rerun.

## Results against the frozen criteria

| Experiment | Retained result | Criterion outcome |
|---|---|---|
| Dependent null | 0/64 joint false finalists; one-sided 95% Wilson upper `0.040559499465846941946678343418878102667010757751140`. Every joint series was complete and 58/64 (0.90625), with two-sided Wilson `[0.81017120400354403636200009892716497253654236990532, 0.95632174741480162905887843138313529781997201923690]`. Descriptive pooled coverage was 522/576 only. | The false-finalist and corrected per-series coverage checks passed. The dependence discriminator failed: IID had 0/64 false finalists and each matching IID rate was 60/64 (0.9375) versus joint-NOMINAL 58/64 (0.90625), a 0.03125 difference below 0.05. |
| Known effect | `positive` selected 64/64; one-sided 95% Wilson lower `0.95944050053415305805332165658112189733298924224886`; `negative` selected 0 times; all 64 decisions were sensitivity-stable. Every joint series was 61/64 (0.953125); pooled descriptive coverage was 549/576. | Passed the frozen preliminary checks. It does not compensate for another failed experiment or establish support. |
| Nonstationary | 0 finalists; 13/32 `UNRESOLVED_SELECTOR_RULE`; 19/32 `UNRESOLVED_NO_FINALIST`. | Failed: 13/32 (40.625%) is below the required 80% rule-based unresolved rate. A bare no-finalist is intentionally not counted as the safeguard. |
| Failure fixtures | All 19 fixtures returned their exact expected status, including missing-versus-zero, lower/upper partition boundaries, one-shot access, runner-up/revision/re-access denials, different/reused-ID and copied-hash cross-family finalist denials, and a forged started ledger whose finalist is outside its checked family. | Passed. |

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
python3 ../../docs/contracts/p02/check_contract.py
```

The focused command reported 53 passed with one existing Starlette/httpx
deprecation warning. Final candidate checks additionally include clean diff and
ancestry checks.

- The input histories are authored synthetic data only. No market/provider/model
  data or protected market holdout was read.
- The numerical profile and pure holdout ledger are not adopted runtime behavior.
  Durable one-shot enforcement needs transactional persistence and independently
  verified source lineage.
- ST-10 operational admission, application wiring, method adoption, and any
  support/trading claim remain unrun and unauthorized.
- This exact final commit still requires two independent candidate-bound reviews
  and a separate controller-arranged gate before acceptance or integration.
