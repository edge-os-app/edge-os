# P02 first-slice records and publication contract

Status: scoped proposal for P02, pending builder acceptance. This freezes one portable contract for downstream work. It does not amend the accepted product specification or qualify a provider, database, compiler, or trading path.

## Record flow

`IntakeRequest` keeps the submitted text and restrictions. `PromptInterpretation` records named input class and requested job separately, plus field evidence and clarification history. Routing returns one explicit outcome. A `StrategyDraft` keeps source and findings under a draft ID. Only valid, supported, adopted meaning can produce a `StrategySpec`. Publication stores immutable content and returns the exact revision identity in the write response.

```text
IntakeRequest -> PromptInterpretation -> Outcome
                                      -> StrategyDraft -> StrategySpec -> PublicationResult
```

Persisted records use an envelope with `schema_version`, `record_type`, `record_id`, `owner_id`, `operation_id`, `created_at`, and `content`. `content` follows the named record schema. The envelope is not included in content hashes. `StrategySpec` is canonical content and has no operation, timestamp, or owner fields. API request bodies contain only the listed request fields; the server rejects a caller-supplied `owner_id`. The owner comes from verified server authentication. Owner and record IDs are UUID strings, and `created_at` is RFC 3339 UTC. A path to another owner's record returns the same `404 not_found` shape as an unknown record. `contract.json` lists required and optional fields, types, enum values, and closed-object policy for every first-slice record. Unknown schema versions and extra fields return `422 validation_error`.

## Intake and interpretation

`IntakeRequest` content contains exact `original_request`, an ordered `restrictions` list, optional declared market, `requested_job`, and `input_class`. The server assigns the envelope `record_id`. The input class is one of `CONCRETE_THESIS`, `LOOSE_INTUITION`, or `BOUNDED_NO_THESIS`. `requested_job` is one of `COMPARE`, `INVESTIGATE_EFFECT`, `CREATE_STRATEGY`, `SIMULATE`, `OBSERVE_FORWARD`, or `REQUEST_LIVE`. This intake slice records request intent and input class. Research mode, operating purpose, evidence status, and execution permission stay in their owning records.

Each interpreted `field_evidence` item contains `field_name`, `state`, `origin`, `source_ref`, `interpretation_revision`, `evidence_status`, and optional `value`, `unit`, `uncertainty`, `adoption`, and `conflicts`. A `KNOWN` item must contain a value. `MISSING` and `CONFLICTING` items must omit it. `CONFLICTING` requires at least two conflict entries with source references. `AGENT_PROPOSED` or `APPLICATION_CONFIGURED` values that affect user choice require `adoption`; a consequential `PENDING` value blocks compilation. `USER_STATED` and `USER_CONFIRMED` values do not need an adoption marker. `PromptInterpretation` links its fields and clarification history to one intake and one immutable interpretation revision. A client cannot set `owner_id` in either request.

| Meaning | Encoding |
|---|---|
| Not assessed | No item for that field |
| Assessed, no value | `state: MISSING`. Omit `value`. |
| Known value | `state: KNOWN`. Include `value`. |
| Competing meanings | `state: CONFLICTING`. Omit `value`. Keep `conflicts` and source references. |
| Runtime value unavailable or unqualified | Return evaluator result `UNKNOWN` with one or more reason IDs. Never invent a default. |

Origins are `USER_STATED`, `USER_CONFIRMED`, `APPLICATION_CONFIGURED`, and `AGENT_PROPOSED`. An application or agent value that affects the user's choice needs `adoption: ADOPTED` before compilation. Otherwise, set adoption to `PENDING`. Evidence labels such as `VERIFIED_FACT`, `INFERENCE`, `HYPOTHESIS`, and `UNKNOWN` describe support. They do not describe origin or permission. A normalized value retains the source and the normalized value in its unit.

Clarifications append a new immutable interpretation revision. They carry `previous_revision_id`, `question_id`, `question`, `answer_ref`, `changed_fields`, and `preserved_restrictions`. Earlier restrictions cannot be removed by a clarification. An unresolved conflict remains `CONFLICTING` until the user resolves it.

## Outcome and draft

The deterministic router returns one of:

| Outcome | Condition and required detail |
|---|---|
| `NEEDS_CLARIFICATION` | Required meaning is missing or conflicting. Include field names and specific questions. Include no guessed value. |
| `UNSUPPORTED` | Meaning is clear but outside supported data, grammar, or action scope. Retain `original_request` and name `missing_capability`. |
| `UNRESOLVED` | Essential evidence or timing is unavailable. Name the claim and `missing_dependency`. Preserve adopted research configuration. Leave the signal and strategy absent when required. |
| `INVALID_INPUT` | The representation is malformed or violates a supported type, unit, parameter, or structural rule. Include a stable finding code and JSON Pointer. Do not recast a malformed supported rule as an unsupported idea. |
| `COMPILED` | Supported meaning is complete, adopted where required, and passes whole-tree validation. This is reviewable syntax, not evidence support, readiness, or permission. |
| `CONFLICTED` | A publication parent or idempotency key conflicts with an existing immutable record. Return HTTP 409 and the stable conflict code. |

`StrategyDraft` stores `draft_id`, original request, current interpretation revision, source syntax, validation findings, and optional proposed fields. It also stores the immutable `strategy_id` and `base_revision_id` selected when the draft starts. It has `state: DRAFT` and no published revision identity. A draft cannot set validation eligibility, paper/live readiness, or an execution mandate.

## Minimum supported strategy proposal

The P02 subset is spot-only and binds one research pool and quote asset. Its research binding records network, chain, underlying venue, pool address, token addresses and order, base/quote orientation, and asset decimals. It also records event-schema version, amount-conversion version, and data-route identity. The intended execution adapter and route identity use separate fields with explicit qualification state. An unknown deployment or route identity blocks execution. A research-pool identity does not qualify a Kuru Flow route. The strategy uses five-minute UTC decision buckets. A complete rule contains `domain`, `market`, `data_inputs`, `entry`, `exit`, `invalidation`, `sizing`, `additions`, `partial_exits`, `cost_assumptions`, `risk_limits`, `action_scope`, `execution_permission`, `warmup_buckets`, and `semantic_manifest`.

The initial rule permits a supported Boolean entry condition and a supported Boolean exit condition. Both use the accepted registry. `invalidation` is either a Boolean rule or `{state: NOT_REQUESTED, source_ref: ...}`. It is never silently absent. `sizing` is a fixed positive quote-asset amount. The minimum subset has `additions: false` and `partial_exits: false`. It permits one open position per strategy instance and a full exit from attributable inventory. Unsupported restrictions or actions return `UNSUPPORTED`. The compiler never drops them to make a rule compile. A sampling or observation period configures research. It does not become an exit condition.

`action_scope` describes the rule's domain actions and limits. It grants no execution authority. `execution_permission` in this proposal is always `NOT_GRANTED`. Live permission requires a separately approved `ExecutionMandate`. The mandate binds to the exact published revision, wallet, network, actions, limits, expiry, and signer/policy binding. The sample market values are synthetic fixture identifiers. ADR 0006 and the accepted specification leave the exact network, Flow deployment, ABI, transport, and selected route for qualification.

The accepted expression subset is `constant`, `price`, `quote_volume`, `price_return`, `lag`, `sum`, `mean`, `gt`, `gte`, `lt`, `lte`, `and`, `or`, and `not`. Use the accepted typed signatures. `lag`, `sum`, and `mean` accept numeric values only. Check every node before simplification. Price is quote/base. Quote volume uses the declared quote asset. Returns are dimensionless. Decimal literals are strings. JSON floating-point numbers are invalid. Lookbacks count scheduled five-minute buckets. Returns need qualified endpoint prices and retain intermediate gaps. Rolling windows need every scheduled value. Missing evidence returns `UNKNOWN` with all reason IDs. Boolean values use the accepted three-valued truth table. An invalid hidden branch rejects the entire expression. `warmup_buckets` equals the greatest scheduled history offset required by entry, exit, or requested invalidation. `price_return(n)` needs `n`; `lag(x,n)` needs `history(x)+n`; `sum(x,n)` and `mean(x,n)` need `history(x)+n-1`. Operators that combine rules need the maximum child requirement. A `NOT_REQUESTED` invalidation contributes zero. A derived requirement above 288 is invalid.

The contract limits input to 64 KiB, expressions to 2,048 nodes and depth 64, lookbacks to 288 scheduled buckets, and manifests to 256 entries. These are deterministic input bounds. They are not measured runtime or production cost limits. A compiler implementation must reject invalid input before data access or effects. P06 measures its runtime profile.

## Semantic identity and canonical bytes

The strategy content hash is SHA-256 of canonical UTF-8 JSON bytes for the complete `StrategySpec`. `revision_id`, `created_at`, `operation_id`, and `publication_id` are publication metadata. They are not `StrategySpec` fields. The canonical profile `p02-json-decimal-string/1` requires:

- Encode UTF-8 without a BOM. Strings must use Unicode NFC and contain no surrogate code points.
- Sort object keys by Unicode code-point order. Keep array order.
- No insignificant whitespace, no ASCII escaping for ordinary Unicode, and only JSON's required quote, backslash, and control-character escapes.
- Integers are JSON integers. All decimal quantities are finite canonical decimal strings with no exponent, leading zero, trailing fractional zero, or negative zero. JSON floats, NaN, and infinities are rejected.
- Duplicate object keys are rejected before canonicalization.

The immutable semantic manifest lists used components and their exact versions. P02 freezes `language=edge-strategy/1`, `operator_registry=edge-operators/1`, `history=scheduled-5m-no-fill/1`, `boolean=kleene-whole-tree/1`, `numeric=decimal-50-half-even/1`, `serialization=p02-json-decimal-string/1`, and `compiler=edge-compiler/1`. The manifest identity is SHA-256 of its canonical bytes. The numerical context has 50 significant digits and half-even rounding. A material rule change alters the content hash. A used-component meaning change alters the manifest hash. Both require a new immutable revision, fresh applicable validation, and mandate approval.

## Publication and retries

`POST /v1/strategies/{strategy_id}/revisions` accepts `operation_id`, `idempotency_key`, a required nullable `expected_parent_revision_id`, `draft_id`, and `strategy`. The body strategy ID must equal the path ID. The strategy carries its locked `semantic_manifest`. Authentication supplies the owner. A successful response returns `operation_id`, `publication_id`, `revision_id`, `content_sha256`, `manifest_sha256`, `created_at`, and `outcome: PUBLISHED`. Consumers use the returned identity tuple. They fetch the exact `revision_id`. A later read of `latest` cannot bind the write.

The server atomically inserts the immutable revision and an idempotency record. The key is `(owner_id, method, path, idempotency_key)`. A retry with the same key and canonical request returns the original response identity. A reused key with a different request fingerprint returns `409 idempotency_key_reused`. Independent concurrent keys create independent revision IDs, even for equal bytes. Concurrent children of one parent remain siblings. A mismatched `expected_parent_revision_id` returns `409 parent_revision_conflict`. It does not overwrite either revision. A timeout or lost acknowledgement leaves publication `UNKNOWN` to the client. The client retries the same key or queries its operation. It does not create a new key before reconciliation. Unknown, unreadable, or mismatched identity blocks promotion and new execution.

| HTTP | Stable code | Meaning |
|---|---|---|
| 401 | `auth_required`, `auth_invalid`, `auth_expired` | Request lacks a valid authenticated principal |
| 503 | `auth_unavailable`, `service_unavailable` | Identity verification or required service is unavailable |
| 422 | `validation_error` | Malformed request or invalid supported record |
| 404 | `not_found` | Record absent or owned by another principal |
| 409 | `idempotency_key_reused`, `parent_revision_conflict` | Mutation cannot be replayed as requested |

The HTTP error body uses `operation_id`, `stage`, `outcome`, `code`, `findings`, and `retry`. An absent record and a record owned by another principal both return the same `404` body with `outcome: NOT_FOUND` and `code: not_found`. It does not expose the stored owner or record state. The fixture compares both responses.

Every `Outcome` contains `operation_id`, `stage`, `outcome`, `code`, `findings`, and `retry`. `PublicationResult` also uses this common result shape and adds publication identity fields. Its outcome is `PUBLISHED` on a successful write. Non-success publication results use the matching terminal outcome. `code` is stable, `findings` is a list of `{code, path, detail}` objects, and `retry` is `SAFE_SAME_KEY`, `RECONCILE`, or `NOT_RETRYABLE`. Only a successful result carries `publication_id`, `revision_id`, and hashes. Results contain no raw credentials or provider payload. These owner/error choices satisfy P01 Q8 as a P02 proposal only. P01 remains unaccepted and unchanged.

The immutable `expected_parent_revision_id` names the exact parent of a new child and must equal the draft's stored `base_revision_id`. A null parent is allowed only for a strategy's first revision. A non-null parent must exist and belong to the authenticated owner and the same strategy. The draft must bind to that owner and strategy. Publication does not require the parent to remain the latest revision: concurrent children of the same immutable parent are siblings and both may succeed. A retry is matched by `(owner_id, method, path, idempotency_key)` before revalidating the draft or parent. The request fingerprint covers owner, method, path, parent, draft ID, and canonical strategy bytes. The same key and fingerprint replays the stored result. A different fingerprint returns `409 idempotency_key_reused`. A missing, foreign, or draft-mismatched parent on a new key returns `409 parent_revision_conflict` without writing. The result has `stage: PUBLICATION`, `outcome: CONFLICTED`, and `retry: NOT_RETRYABLE`. A different fingerprint under an already-used key returns `409 idempotency_key_reused` with the same stage and outcome.

## Evidence boundary

The checker tests serialization, sample records, fixture semantics, and rejection mutations in memory. It does not test authenticated server ownership, atomic storage, unique constraints, transaction isolation, concurrent writes, retry persistence, provider behavior, runtime limits, or live execution. P03 verifies a running application. P06 owns broader compiler checks. P02 made no provider or model calls.

Run from the repository root:

```sh
python3 docs/contracts/p02/check_contract.py
```
