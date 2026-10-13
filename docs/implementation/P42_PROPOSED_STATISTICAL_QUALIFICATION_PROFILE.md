# P42 proposed statistical-qualification profile

Status: **proposal only; no formal support claim**. This is a pure numerical
preparation on the quant branch. It neither changes P09 reports nor opens the
protected holdout.

## Candidate implementation boundary

The helper models the selected candidate from STAT-Q01: a circular stationary
bootstrap over one common scheduled index stream for every frozen contrast. It
requires—not defaults—the block selector reference and selected length, overlap
floor, resample count, seed, quantiles, family alpha, minimum coverage, minimum
usable observations, and sparse-resample policy. Therefore a caller cannot make
an implicit method choice merely by calling a generic `bootstrap` helper.

- Every contrast retains its complete scheduled sequence. A missing observation
  remains `None`; it is never a zero return or a dropped family member.
- Each bootstrap draw applies the same circular indices to every contrast, so
  common timing and overlapping outcomes are not discarded by independent
  resampling.
- Conditional means and denominators recompute in each draw. A draw with no
  usable selected observations becomes `UNRESOLVED_SPARSE_RESAMPLE` under the
  only currently supported sparse policy.
- The helper calculates basic pointwise intervals and one-sided candidate
  p-values for a caller-supplied minimum difference. Holm is applied to the
  whole frozen family; an invalid/missing p-value makes every family decision
  unavailable rather than deleting that comparison.
- Nominal, half, and double block lengths (subject to the overlap floor) must
  agree. Any disagreement or unevaluable sensitivity returns
  `UNRESOLVED_SENSITIVITY`.
- Evaluation pins coverage, resample errors, interval endpoints, thresholds and
  p-values to the repository numeric context, so a caller's ambient Decimal
  precision cannot change a result.

`CANDIDATE_SUPPORT` is deliberately not `QUALIFIED`. ST-01 through ST-10 still
need independently specified generators, tolerances, simulation uncertainty,
selection/holdout controls, and an approved compute budget. The P42 ticket and
STAT-Q01 remain the authoritative adoption boundary.
