# STAT-Q01 candidate preparation profile

Status: **PROPOSED numerical-preparation profile; not adopted and not a
formal-support method.**

Identity: `edge-os.stat-q01-qprep/2026-10-14.2`
Assignment: `P42-QPREP-20261013-01` / issue #28
Scope: isolated calculation and authored calibration only. It does not read a
market holdout, alter P09, create a research job, call a provider, or make an
operational or financial claim.

This profile freezes the candidate choices used by the accompanying bounded
calibration plan. Revisions `2026-10-13.1` and `2026-10-14.1` were never
evaluated. This identity adds the complete-family schedule binding, append-only
pre-label holdout ledger, exact lineage hashes, total static-work cap, and
ambient-Decimal-independent generator requirements identified before any
experiment. A later revision must receive a new identity, plan, and evidence;
calibration criteria are not changed after inspecting a result.

## Claim and input boundary

For each frozen comparison, the primary statistic is the P09-consistent
observed-outcome contrast

`mean(response | qualified TRIGGERED, observed) - mean(response | qualified CONTROL, observed)`.

The direction is positive and the candidate minimum relevant difference is
`0.10` response units. An incremental price-held-constant comparison is a
separate named comparison, not a substitute general control. Every comparison
uses the same ordered scheduled slots in one validation partition. A slot keeps
its eligibility group (`TRIGGERED`, `CONTROL`, or `EXCLUDED`), its response
(`Decimal` or `None`), and its missing/ineligibility reason. `None` is never a
zero response or a dropped slot.

The estimand is explicitly conditional on observed responses in each eligible
group. The method preserves missingness and reports it; it does not assume that
selective missingness is repaired by bootstrap resampling. A prospective caller
must retain the complete scheduled history and name its dataset, configuration,
comparison-family, and partition identities outside this pure module.

## Feasibility and partition policy

The numerical module accepts one contiguous non-holdout partition at a time.
Circular continuation wraps only inside that supplied partition. It refuses a
family unless every comparison has exactly the same ordered slot identities and
the following proposed feasibility settings hold:

| Setting | Frozen candidate value | Reason |
|---|---:|---|
| Scheduled slots | 128–512 | Below 128 the selector/calibration has too little time structure; above 512 exceeds this bounded preparation profile. |
| Comparisons in a frozen family | 1–3 | The numerical profile makes the family size explicit; the calibration exercises all three slots rather than silently accepting an unbounded family. |
| Observed responses per eligible group | at least 16 | Avoid a contrast or resample being dominated by one or a few records. |
| Observed coverage per eligible group | at least 10% of scheduled slots | Makes the observed-outcome restriction visible and rejects extremely sparse groups. |
| Per-draw group observations | at least 2 | A bootstrap draw with fewer is unresolved, not a zero mean or fabricated p-value. |
| Non-finite response | forbidden | It is a validation error, never a missing-value synonym. |

Before construction/evaluation, a pure chronological guard derives its slot
sequence from the complete frozen comparison family, retains a status for every
such slot, and requires an identified outcome window wholly within the
validation partition: `validation_start <= outcome_start < outcome_end <=
protected_holdout_start`. A missing window, unknown revision identity, or a
window crossing either bound makes the validation family unresolved. The guard
receives window metadata, not protected labels; it does not accept a
display-filtered slot list.

The schedule-derived lower block floor is

`ceil((maximum target horizon seconds + 60-second reference window) / decision interval seconds)`.

It reflects the longest P09 response span that can overlap a neighboring
decision. The family uses the largest selected block length across its frozen
comparisons, then applies this floor. If a selected, half, or double sensitivity
length is longer than the partition, the family is `UNRESOLVED`; it is not
silently capped.

## Contrast influence and corrected PPW selector

For selector input only, let `N` be all scheduled slots, `nT`/`nC` be observed
qualified triggered/control counts, `pT=nT/N`, `pC=nC/N`, and `yT`/`yC` their
observed means. At every slot `t`, the influence series is

`psi[t] = I(T,t) * (y[t] - yT) / pT - I(C,t) * (y[t] - yC) / pC`.

Excluded and missing slots contribute a **zero influence contribution**, not a
zero response; their original records remain in the retained history and their
positions still affect time dependence. This is the influence series for the
declared conditional contrast, not an imputation model.

Selector identity: `PPW-SB-2009-corrected-flat-top/1`.

1. Compute biased, mean-centred autocovariances
   `Rhat(k)=N^-1 sum_{t=1}^{N-k}(psi[t]-mean(psi))(psi[t+k]-mean(psi))`.
2. Let `L=min(floor(N/4), 32)`, `K=max(5, floor(sqrt(log10(N))))`, and
   `tau=2*sqrt(log10(N)/N)`. Choose the smallest `m >= 1` with `m+K <= L`
   for which the next `K` absolute sample autocorrelations are all strictly
   below `tau`; otherwise return `UNRESOLVED_SELECTOR_BANDWIDTH`.
3. Set `M=2m` and use the symmetric trapezoidal flat-top lag window:
   `lambda(x)=1` for `|x|<=1/2`, `2*(1-|x|)` for `1/2<|x|<=1`, else `0`.
   Compute `Ghat=sum(lambda(k/M)*abs(k)*Rhat(k), k=-M..M)` and
   `ghat0=sum(lambda(k/M)*Rhat(k), k=-M..M)`.
4. Use the **Patton–Politis–White 2009 correction** for the stationary
   bootstrap variance constant: `DhatSB=2*ghat0^2`. The raw expected block
   length is `(2*Ghat^2/DhatSB)^(1/3)*N^(1/3)`. Round it to the nearest integer
   with the repository's half-even decimal convention, require at least one,
   and then apply the schedule-derived floor.

`ghat0 <= 0`, an undefined autocorrelation, an unfindable bandwidth, or a
non-finite/out-of-partition block length leaves the relevant comparison and
family unresolved. The source correction changes the stationary-bootstrap
constant; this profile deliberately does not reuse the pre-correction form.

## Joint stationary bootstrap and inference

For each frozen length (floor-constrained half, selected, and double selected),
draw 199 stationary-bootstrap index streams of partition length `N`. A stream
starts uniformly at a slot; after each sampled slot it restarts uniformly with
probability `1/b`, otherwise advances one slot circularly. The same stream is
applied to every comparison in the family, preserving shared schedule and
missingness structure. Randomness is CPython 3.14 `random.Random` (MT19937),
with a seed derived from the profile identity, partition identity, block length,
and declared seed by SHA-256; no ambient process hash is used.

Each draw recomputes conditional group means and denominators. A draw that
cannot meet the per-draw group minimum makes that comparison unresolved for the
length. Let `dhat` be the observed contrast and `e*=dhat* - dhat` each centred
draw error. The directional p-value for `H0: d <= 0.10` is

`(1 + count(e* >= dhat - 0.10)) / (1 + 199)`.

The pointwise 95% basic interval is
`[dhat-q0.975(e*), dhat-q0.025(e*)]`, where `qp` is the order statistic at
one-based rank `max(1, ceil(p*B))`. The interval is not simultaneous and is
not itself a support decision.

All calculations use the accepted versioned 50-significant-digit Decimal
context with half-even rounding. The caller's ambient Decimal context must not
alter values, selectors, p-values, or status.

## Family, sensitivity, selection, and holdout policy

Holm is applied at nominal family-wise `alpha=0.05` over every frozen comparison
with its actual family size. A missing, invalid, or unavailable p-value remains
in the output with its reason and makes the whole family
`UNRESOLVED_FAMILY_INCOMPLETE`; it is never omitted or replaced with a favorable
number. Valid failed comparisons remain in the family.

A comparison is only candidate-eligible when it is directionally favorable,
Holm-rejected at all three frozen sensitivities, and every family member is
valid. The single validation finalist is the eligible comparison with the
largest observed primary contrast; an exact tie is broken by ascending frozen
comparison ID. This rule is fixed before calibration outcomes. There is no
runner-up substitution.

One protected holdout confirmation may be recorded only for that exact finalist,
using the same direction and the frozen `alpha=0.05`. Before any outcome
label/p-value is passed to the pure calculator, an immutable `ACCESS_STARTED`
event checks and binds canonical SHA-256 profile, plan, family, and
outcome/control/test identities; protected partition and finalist revision
identities; and a successful schedule-boundary validation. Resolution appends a
second event rather than replacing the start. A failed, missing, insufficient,
or lineage-mismatched confirmation consumes that attempt as `UNRESOLVED`; it
cannot expose a runner-up or relabelled revision to the same holdout. The pure
value-state is a fixture for later persistence, not proof of durable one-shot
enforcement; an adopted runtime must persist the transition before reading the
label and independently verify its source lineage.

## Boundaries and sources

This is a candidate profile, not a conclusion about any market regime. It is
inapplicable under selective missingness, insufficient coverage, substantial
nonstationarity, or failure of its calibration criteria. In those cases the
required output is descriptive evidence and `UNRESOLVED` support.

Method context: [Politis–White automatic selector](https://www.math.ucsd.edu/~politis/SBblock-revER.pdf),
[Patton–Politis–White correction](https://public.econ.duke.edu/~ap172/Patton_Politis_White_2009.pdf),
and [R's Holm reference](https://search.r-project.org/R/refmans/stats/html/p.adjust.html).
The accepted Edge OS contracts, rather than these sources, control the product
boundary and status vocabulary.
