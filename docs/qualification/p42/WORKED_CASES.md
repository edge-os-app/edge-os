# P42 proposed worked cases

Status: independently calculated examples for the proposal, not calibration
evidence and not a formal-support result.

## WC-01: Missing observation remains missing

One signed contrast is observed at four scheduled opportunities:

`(1, 3, None, 5)`

The usable conditional mean is `(1 + 3 + 5) / 3 = 3`. Coverage is `3 / 4 =
0.75`; usable observations are `3`, not `4`. Replacing the missing observation
with zero would produce `2.25`, a different statistic and population. The
proposal therefore preserves `None`, reports coverage, and requires the caller's
frozen minimum-coverage policy before evaluating the contrast.

## WC-02: Complete-family Holm calculation

For a frozen three-comparison family with directional p-values `(A=.01, B=.03,
C=.04)` and family alpha `.05`, sort ascending and apply Holm:

| Step | Comparison | Threshold | p-value | Reject? |
|---|---:|---:|---:|---|
| 1 | A | `.05 / 3 = .016666…` | `.01` | yes |
| 2 | B | `.05 / 2 = .025` | `.03` | no; stop |
| 3 | C | — | `.04` | no |

Only A is rejected. If C has no valid p-value, the proposal returns no family
decision for A or B either; it does not shrink the family to make A look more
significant.

## WC-03: Block-sensitivity denial

Assume an adopted selector yields nominal block length `4` and overlap floor
`2`. The proposal checks lengths `(2, 4, 8)`. If the nominal run produces a
candidate family decision but any applicable sensitivity produces the opposite
decision or cannot evaluate a sparse sample, the displayed result is
`UNRESOLVED_SENSITIVITY`. Selecting the favorable length after inspecting output
is not allowed.

The focused test suite verifies component determinism and failure states. It
does not claim ST-02 false-support calibration, interval coverage, or ST-01–10
completion.
