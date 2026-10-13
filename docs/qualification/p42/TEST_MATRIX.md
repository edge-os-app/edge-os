# P42 proposed qualification matrix

Status: proposal-level component evidence only. Passing these tests is not
STAT-Q01 qualification and cannot enable a formal support claim.

| Contract risk | Focused test/protection | Remaining qualification requirement |
|---|---|---|
| Hidden statistical defaults | Every profile field is caller-supplied and validated | Approve exact selector/version, resamples, seed, quantiles, tolerances and compute budget. |
| Lost common timing | One seeded circular index stream is applied to all contrasts | ST-02/04/06 need dependent simulated histories and calibration evidence. |
| Missing converted to zero | `None` remains unavailable; coverage and usable count are reported | Freeze observed-outcome/missingness population and sparse-resample policy. |
| Family cherry-picking | Holm sees every declared p-value; any invalid member leaves the family unavailable | ST-05 needs independent Holm reference and failed-valid-comparison cases. |
| Favorable block choice | Nominal/half/double sensitivity must agree or return unresolved | Freeze block selector, overlap conversion and sensitivity acceptance rule. |
| Ambient Decimal precision | The same family evaluates identically at 28- and 50-digit caller precision | Freeze the numeric context with the adopted profile. |
| Terminology inflation | Outputs use `CANDIDATE_*` or `UNRESOLVED_*`, never `QUALIFIED` | Complete ST-01–ST-10 with approved generators and thresholds. |

Run from the repository root:

```sh
(cd apps/api && uv run --frozen pytest -q tests/test_proposed_statistical_qualification.py)
```
