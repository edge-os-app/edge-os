# P42 bounded calibration plan

Status: **FROZEN PROPOSAL BEFORE EXPERIMENTS.** No result appears in this file.
The plan tests `edge-os.stat-q01-qprep/2026-10-16.1` from
[`STAT_Q01_CANDIDATE_PREPARATION_PROFILE_2026-10-16.1.md`](../../implementation/STAT_Q01_CANDIDATE_PREPARATION_PROFILE_2026-10-16.1.md).
It is authored synthetic simulation, not market history, provider evidence, or
formal statistical support.

The prior `2026-10-14.2` plan/result used a pooled 576-interval Wilson
denominator even though the nine pointwise outcomes within one generated history
are dependent. Its plan, failed result, and report remain historical evidence;
this new identity does not reclassify them. This replacement plan is frozen
before its own experiment. It preserves the outer scenario seed lists,
generator, methods, finite limits, and acceptance thresholds except the
corrected uncertainty unit below. Because the profile identity is an input to
the derived bootstrap/IID seed hash, the new identity intentionally creates a
new deterministic resampling seed namespace; this is a new experiment, not a
relabelled rerun.

## Exact experiments

Each synthetic family has 160 scheduled slots, three comparisons, a five-minute
decision interval, a 30-minute target horizon, a 60-second reference window,
and therefore a schedule-derived block floor of 7 slots. Every run uses 199
bootstrap draws, a 5% pointwise interval, a 5% whole-family Holm procedure,
and the profile's floor/selected/double sensitivity policy.

For one repetition, CPython 3.14 `random.Random(seed)` (MT19937) first draws
166 `normalvariate(0, 0.10)` innovations, then 160 independent group draws
(`random() < 0.5` means `TRIGGERED`, otherwise `CONTROL`), then 160 independent
missingness draws (`random() < 0.10` means missing). The latent sequence is
`x[t]=0.60*x[t-1]+innovation[t]`, starting at zero. An observed response is
the Decimal-50 mean of `x[t:t+7]`, giving adjacent scheduled rows overlapping
outcomes. Floats enter Decimal only as `Decimal(str(value))`; mean construction
and triggered-effect addition both use the repository's Decimal-50, half-even
context, so the generated family and its digest do not depend on caller ambient
Decimal precision. Missing rows
retain their original group and `SYNTHETIC_MISSING` reason. The three named
comparisons are always present in the family. A treatment effect is added only
to an observed triggered response; the declared truth remains the injected
treatment effect across repeated randomized histories.

The runner also applies one deliberately independence-assuming diagnostic on
the same dependent-null histories: `iid-slot-bootstrap/1` resamples individual
scheduled slots with replacement, jointly across the three comparisons, then
uses the same centered contrast, 199 draws, Holm family, and finalist rule. It
has no block sensitivity and is never a support method. Its purpose is to make
the calibration capable of exposing loss of serial-dependence handling.

| Experiment | Generator change | Repetitions/seeds | Predeclared purpose |
|---|---|---|---|
| `dependent-null-v1` | All group effects are 0.00; run both joint stationary and `iid-slot-bootstrap/1`. | 64, seeds 1101–1164 | ST-02 false-support, pointwise coverage, and dependence-discriminator behavior with overlap. |
| `known-effect-v1` | Effects are `+0.35`, `0.00`, and `-0.35` for IDs `positive`, `null`, and `negative`. | 64, seeds 2101–2164 | ST-01/ST-03 directional detection, contrast, full-family selection, and coverage behavior. |
| `nonstationary-v1` | The positive comparison is `+0.35` in the first half and `-0.35` in the second; other comparisons are 0.00. | 32, seeds 3101–3132 | ST-03/ST-04 adverse regime behavior. A favorable result is a calibration failure, not evidence. |
| `failure-fixtures-v1` | Canonical authored short, sparse, all-missing, zero-versus-missing, invalid-p, tie, selector-bandwidth, lower/upper partition-boundary, holdout-start/failure/wrong-finalist/runner-up/revision-mismatch/re-access, and different/reused-ID or copied-hash cross-family-finalist fixtures. Its canonical input/expected-status manifest is SHA-256 digested in the result. | one deterministic fixture each | ST-03/ST-05/ST-07/ST-08/ST-09 failure/governance behavior. |

The run code derives each bootstrap seed from the experiment seed and the
frozen profile identity; no result-dependent reseeding, retry, or selection is
allowed. Before each result is emitted it records a SHA-256 of the canonical
generated history, the canonical failure-fixture payload, and the plan/profile
files. The calibration report must preserve every repetition, including a
resource-limited partial result.

## Predeclared preliminary criteria

These are suitability checks for further review, not criteria for a formal
support claim. The report is `UNRESOLVED` unless every applicable check below
passes, and it remains proposal-only even if they do.

| Check | Frozen criterion |
|---|---|
| Dependent null false support | The one-sided 95% Wilson upper bound for family-wise false finalist selection across 64 repetitions is at most 0.15. |
| Dependent null interval behavior | For every declared joint `comparison × sensitivity` series, use its 64 generated histories as the Bernoulli trials. The observed coverage is at least 0.85 and that series' two-sided 95% Wilson interval intersects [0.90, 1.00]. Missing truth/interval/history makes the criterion `UNRESOLVED`. The pooled 576-interval count is descriptive only and receives no Wilson interval. |
| Known effect detection | The one-sided 95% Wilson lower bound for selecting `positive` is at least 0.50; no negative-direction comparison is selected. |
| Known effect interval behavior | Every declared joint `comparison × sensitivity` series has observed coverage at least 0.85 across its 64 histories. A missing truth/interval/history is `UNRESOLVED`; pooled coverage cannot hide a failed series. |
| Sensitivity stability | At least 80% of valid known-effect repetitions make the same candidate decision at all frozen sensitivities. |
| Nonstationary adverse case | No repetition may return a candidate finalist. At least 80% must be unresolved because of a frozen selector/sensitivity/family rule; otherwise the profile is insufficient. |
| Dependence discriminator | On dependent nulls, the report must retain the IID comparator. The candidate is insufficient unless IID has either at least two more false finalists than the joint method or, for at least one matching comparison ID, IID coverage is at least 0.05 lower than the joint `NOMINAL` coverage. Indistinguishable bounded evidence is `UNRESOLVED`, not a pass. |
| Failure fixtures | Every fixture must preserve `None` separately from zero, retain all family members, bind the finalist to its exact canonical family, and return its frozen unresolved/governance status. |

Wilson bounds use the uncorrected score interval with Decimal-50 arithmetic:
`z=1.6448536269514722` for one-sided 95% bounds and
`z=1.959963984540054` for two-sided 95% bounds. The Wilson intervals quantify
simulation error across independent generated histories; they do not convert a
limited 64-repetition experiment into a universal calibration. A stopped run,
unavailable family member, inapplicable selector, missing declared series, any
failed criterion, or insufficient precision is reported unchanged as
`UNRESOLVED`. No threshold is relaxed after seeing this plan's result.

## Finite resources and termination

| Limit | Frozen bound |
|---|---:|
| Processes / workers | 1 / 1 |
| Scheduled slots per family | 160 |
| Comparisons per family | 3 |
| Bootstrap draws per sensitivity | 199 |
| Sensitivities | 3 |
| Outer repetitions | 64, 64, and 32 as listed above |
| Maximum bootstrap slot-visits per full experiment | 24,453,120 for dependent null (`64*3*199*4*160`, including IID); 18,339,840 for known effect; 9,169,920 for nonstationary; 51,962,880 total, checked before any experiment starts |
| Maximum wall clock per experiment | 180 seconds |
| Maximum total wall clock | 540 seconds |
| Peak traced Python allocation | 256 MiB |

The runner checks static work before it starts, uses a monotonic deadline during
evaluation, samples traced peak allocation between repetitions, and writes a
partial report with the completed repetitions and a resource reason if it must
stop. It uses no provider, network, paid compute, multiprocessing, or protected
market data.

## Reproduction command

After the code and this plan are committed to the draft PR, run from `apps/api`:

```sh
uv run --frozen python -m edge_os_api.research.statistical_calibration \
  --plan ../../docs/qualification/p42/CALIBRATION_PLAN_2026-10-16.1.md \
  --output ../../docs/qualification/p42/CALIBRATION_RESULT_2026-10-16.1.json
```

The committed Markdown report will name the exact source commit, profile/plan
SHA-256 values, runtime, peak allocation, command, Python version, all
experiment statuses, and the resulting suitability verdict. It will not claim
ST-10 operational admission, formal support, or market evidence.
