# P42 bounded calibration plan

Status: **FROZEN PROPOSAL BEFORE EXPERIMENTS.** No result appears in this file.
The plan tests `edge-os.stat-q01-qprep/2026-10-13.1` from
[`STAT_Q01_CANDIDATE_PREPARATION_PROFILE.md`](../../implementation/STAT_Q01_CANDIDATE_PREPARATION_PROFILE.md).
It is authored synthetic simulation, not market history, provider evidence, or
formal statistical support.

## Exact experiments

Each synthetic family has 160 scheduled slots, three comparisons, a five-minute
decision interval, a 30-minute target horizon, a 60-second reference window,
and therefore a schedule-derived block floor of 7 slots. Every run uses 199
bootstrap draws, a 5% pointwise interval, a 5% whole-family Holm procedure,
and the profile's floor/selected/double sensitivity policy.

The generator starts with a seeded Gaussian innovation sequence and an AR(1)
latent process with `rho=0.60`. An observed response is the mean of the next
seven latent values, giving adjacent scheduled rows overlapping outcomes.
Groups are generated before outcomes from a seeded balanced Bernoulli process.
`None` responses follow a seeded 10% missingness process and retain their
original group and `SYNTHETIC_MISSING` reason. The three named comparisons are
always present in the family.

| Experiment | Generator change | Repetitions/seeds | Predeclared purpose |
|---|---|---|---|
| `dependent-null-v1` | All group effects are 0.00. | 64, seeds 1101–1164 | ST-02 false-support and pointwise-coverage behavior with dependence and overlap. |
| `known-effect-v1` | Effects are `+0.35`, `0.00`, and `-0.35` for IDs `positive`, `null`, and `negative`. | 64, seeds 2101–2164 | ST-01/ST-03 directional detection, contrast, full-family selection, and coverage behavior. |
| `nonstationary-v1` | The positive comparison is `+0.35` in the first half and `-0.35` in the second; other comparisons are 0.00. | 32, seeds 3101–3132 | ST-03/ST-04 adverse regime behavior. A favorable result is a calibration failure, not evidence. |
| `failure-fixtures-v1` | Authored short, sparse, all-missing, invalid-p, tie, selector-bandwidth, and holdout-failure fixtures. | one deterministic fixture each | ST-03/ST-05/ST-07/ST-08/ST-09 failure/governance behavior. |

The run code derives each bootstrap seed from the experiment seed and the
frozen profile identity; no result-dependent reseeding, retry, or selection is
allowed. The calibration report must preserve every repetition, including a
resource-limited partial result.

## Predeclared preliminary criteria

These are suitability checks for further review, not criteria for a formal
support claim. The report is `UNRESOLVED` unless every applicable check below
passes, and it remains proposal-only even if they do.

| Check | Frozen criterion |
|---|---|
| Dependent null false support | The one-sided 95% Wilson upper bound for family-wise false finalist selection across 64 repetitions is at most 0.15. |
| Dependent null interval behavior | Across all valid pointwise intervals, the two-sided 95% Wilson interval for empirical coverage intersects the target band [0.90, 1.00], and the observed coverage is at least 0.85. |
| Known effect detection | The one-sided 95% Wilson lower bound for selecting `positive` is at least 0.50; no negative-direction comparison is selected. |
| Known effect interval behavior | Observed pointwise coverage for the declared true contrasts is at least 0.85. |
| Sensitivity stability | At least 80% of valid known-effect repetitions make the same candidate decision at all frozen sensitivities. |
| Nonstationary adverse case | No repetition may return a candidate finalist. At least 80% must be unresolved because of a frozen selector/sensitivity/family rule; otherwise the profile is insufficient. |
| Failure fixtures | Every fixture must preserve `None` separately from zero, retain all family members, and return its frozen unresolved/governance status. |

The Wilson intervals quantify simulation error; they do not convert a limited
64-repetition experiment into a universal calibration. A stopped run, an
inapplicable selector, any failed criterion, or insufficient precision is
reported unchanged as `UNRESOLVED`. No threshold is relaxed after seeing a
result.

## Finite resources and termination

| Limit | Frozen bound |
|---|---:|
| Processes / workers | 1 / 1 |
| Scheduled slots per family | 160 |
| Comparisons per family | 3 |
| Bootstrap draws per sensitivity | 199 |
| Sensitivities | 3 |
| Outer repetitions | 64, 64, and 32 as listed above |
| Maximum bootstrap slot-visits per full experiment | 18,339,840 (`64*3*199*3*160`); 9,169,920 for the 32-repetition case |
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
  --plan docs/qualification/p42/CALIBRATION_PLAN.md \
  --output ../../docs/qualification/p42/CALIBRATION_RESULT.json
```

The committed Markdown report will name the exact source commit, profile/plan
SHA-256 values, runtime, peak allocation, command, Python version, all
experiment statuses, and the resulting suitability verdict. It will not claim
ST-10 operational admission, formal support, or market evidence.
