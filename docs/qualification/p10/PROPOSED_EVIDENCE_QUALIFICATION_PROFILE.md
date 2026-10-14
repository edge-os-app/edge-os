# P10 proposed source-evidence qualification profile

Status: **preparation only; no Hermes provider call, source collection, or P10
runtime implementation has occurred.** `REFERENCES_PRESENT` is only the pure
helper's local reference-shape result. It is not a completed research report,
an owner-bound immutable package, or an actual `NANSEN_DATA_QUALIFICATION.md`
artifact.

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

## Proposed owner-record mapping — not implemented or adopted

The helper must not become a second research runtime. If a future owner adopts
it, each field must be resolved in one transaction through the existing
owner-scoped records below, with matching `owner_id` and immutable content hash
checks. The rows named here are an integration map, not evidence that the
mapping is already enforced.

| Helper reference | Candidate application record | Required adoption work |
|---|---|---|
| `declaration_ref` and `interpretation_ref` | `InvestigationJobRow.declaration_id` and `intake_record_id` | Bind the selected P08/P09 declaration revision and interpretation lineage to the job's authenticated owner. |
| Tool attempt, response, and `usage_ref` | Append-only `InvestigationEventRow` attempt events, keyed by `owner_id`, `job_id`, and `attempt_id`; the job's frozen `budget` holds resource settlement | Define a stable attempt/usage locator and prove the completed attempt, response hash, and usage settlement describe the same tool effect. |
| Source observation | `HistoryDatasetRow` (`owner_id`, `declaration_id`, `job_id`, `attempt_id`, `content_sha256`, `raw_records`) or an accepted equivalent source record | Bind source URI, retrieval/coverage facts and content hash to the exact saved dataset; never infer a provider observation from a URL string. |
| Numerical finding and reconciliation | `InvestigationReportRow` or a separately accepted P09 result record | Bind calculation inputs, units, coverage, reconciliation evidence and contrary findings to the saved source identity. |
| `report_ref` and reopen lineage | `InvestigationReportRow` / `NansenReportRow`, both scoped by owner, job, report identity and content hash | Define immutable replacement/reopen lineage and owner-authorized retrieval; do not let a later report silently replace an earlier package. |

Until that shared mapping is accepted and tested against durable records, this
module may return only `REFERENCES_PRESENT` or
`ZERO_CANDIDATE_REFERENCE_UNRESOLVED`; neither is a P10 qualification claim.

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
