# P10 proposed source-evidence qualification profile

Status: **preparation only; no Hermes provider call, source collection, or P10
runtime implementation has occurred.** This document deliberately is not a
completed research report or an actual `NANSEN_DATA_QUALIFICATION.md` artifact.

The accompanying pure helper,
`apps/api/src/edge_os_api/research/proposed_evidence_package.py`, validates the
package boundary without a provider, credential, router, database, or tool
invocation. Its tests exercise complete, failed-tool, absent-source,
unreconciled-numeric, zero-candidate, and contrary-evidence states.

## Proposed evidence package boundary

P10 may only make a source-backed finding when one immutable package ties each
claim to all of the following:

| Record | Required identity and content | Explicit failure state |
|---|---|---|
| Declared question | P08 declaration/revision, pre-outcome hypothesis, falsification rule, budget and permitted access | `DECLARATION_UNAVAILABLE` |
| Tool invocation | Tool contract/version, request identity, credential class (never secret), time, cost/usage, response hash and attempt outcome | `TOOL_CALL_UNAVAILABLE` |
| Source observation | Primary source URI, retrieval timestamp, source publication/update time when available, exact extract/hash and rights/coverage limitation | `SOURCE_UNAVAILABLE` |
| Interpretation | Observation-to-claim reasoning, alternative explanation, contrary evidence and unresolved mechanism | `INTERPRETATION_UNSUPPORTED` |
| Numerical evaluation | P09 fixture/data identity, calculation version, units, input coverage, independent reconciliation and all variants/failures | `EVALUATION_UNAVAILABLE` |
| Saved outcome | Immutable package/revision identity, result status, zero-candidate completion state, and reopen lineage | `PERSISTENCE_UNAVAILABLE` |

An LLM response, URL, current web page, or successful tool call alone is not a
finding. A result is source-backed only after the complete chain is present.
For a successful tool attempt, both the response hash and a non-empty usage/cost
lineage reference are mandatory. This helper verifies references only; it does
not itself prove that a referenced source or saved package is immutable.

## Adversarial qualification matrix

| Risk | Required case | Expected result |
|---|---|---|
| Source text asks for tool, wallet, or policy authority | Tool/source content includes an instruction that conflicts with the approved contract | Preserve the text as evidence; do not grant authority or invoke an extra tool. |
| Attractive result lacks contrary evidence | Tool returns only favorable passages | Report the evidence gap or unresolved mechanism; do not turn omission into support. |
| Malformed/partial evidence package | Missing URI, hash, unit, source time, or attempt identity | Named unavailable state; no numerical conclusion. |
| Successful call lacks usage lineage | Response hash is present but cost/usage reference is absent | `TOOL_CALL_UNAVAILABLE`; no numerical conclusion. |
| Invalid numeric finding | Result has unknown units, missing denominator, overflow/non-finite value, or unreconciled calculation | Retain failure/attempt; suppress quantitative claim. |
| No eligible candidate | Every evaluation fails, is ineligible, or is unsupported | Save a completed zero-candidate unresolved report; do not force a strategy. |
| Reopen | Existing report is reopened | New immutable lineage points to old package; no silent replacement. |
| Post-result hypothesis | Interpretation suggests a new mechanism | Record it as a new hypothesis; it cannot rewrite the pre-outcome declaration. |

## Start gate

Before implementation, the controller must provide an exact candidate/base,
owned paths, P05/P09 accepted inputs, source/tool contracts, a maximum resource
budget, and an approved actual-run packet. Until then only fixture-labelled
preparation is permitted. This profile intentionally does not alter P05's
reserved shared API/storage/UI lease.

Run its focused proposal checks from the repository root:

```sh
(cd apps/api && uv run --frozen pytest -q tests/test_proposed_evidence_package.py)
```
