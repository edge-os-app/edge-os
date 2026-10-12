# Nansen research local interface freeze

Task `NANSEN-REPORT-L4-20261012-01` v1, issue #51 scoped LOCAL slice. Package root `apps/api/src/edge_os_api/nansen_research/`. This document freezes the local interface and the resource/fault matrix before implementation. It is a local interface proposal. It is not provider qualification, a production schema or bounty readiness.

## Status of each statement

- **Accepted requirement**: from the frozen D01 profile `nansen-descriptive-reviewed/1` (`docs/qualification/nansen/D01_DESCRIPTIVE_INPUT_PROFILE.md`) and its checker, or from the worker packet.
- **Proposed consumer interface**: authored here for the later lane-2 mount. A material cross-owner change routes to controller `%0`.
- **Routine choice**: small local decision that needs no approval.

## Version identities

| Identity | Value | Status |
|---|---|---|
| Request schema | `nansen-research-request/1` | Proposed |
| Evidence schema | `nansen-research-evidence/1` | Proposed |
| Report schema | `nansen-research-report/1` | Proposed |
| Provider API schema | `1.0.0` (OpenAPI `info.version`) | Accepted (source-pinned) |
| Input profile | `nansen-descriptive-reviewed/1` | Accepted |
| Calculation conventions | `d01-conventions/1` | Accepted |
| Provider | `NANSEN_TGM` | Accepted |
| Provider version | `nansen-tgm/1` | Proposed |
| Endpoint origin | `https://api.nansen.ai` | Accepted (source-pinned) |
| Network | `monad` | Accepted |
| Chain ID | `143` | Accepted |

## Pinned operations

Only these operations are allowed. Any other method or path is refused before any transport call.

| Operation | Method | Path | Quoted reservation (credits) |
|---|---|---|---|
| `holders` | POST | `/api/v1/tgm/holders` | 5 |
| `flows` | POST | `/api/v1/tgm/flows` | 1 |

The reservation values are the D01 captured basic-label costs. A quoted cost from the response header replaces the reservation only when the settlement is known. `premium_labels` stays `false` and is never set. The x402 and MPP payment headers are never sent.

## Frozen request interface

`NansenRequest` carries the fields D01 requires before a call:

| Field | Meaning |
|---|---|
| `request_schema` | `nansen-research-request/1` |
| `question` | The exact user research question |
| `token_address` | Contract address (lowercase kept as given) |
| `token_symbol` | Display symbol |
| `network`, `chain_id` | `monad`, `143` |
| `window` | `ObservationWindow(start_utc, end_utc)`; `end_utc` is the inclusive flow cutoff |
| `holder_query` | `HolderQuery(label_type, aggregate_by_entity, order_field, value_usd_min)` |
| `flow_query` | `FlowQuery(label)` |
| `operations` | Ordered subset of `holders`, `flows` |
| `profile_version`, `conventions_version` | Accepted profile identities |
| `limits` | `NansenLimits` (see below) |

`value_usd_min` is `None` by default. `None` means "send no `value_usd` filter", so the provider default applies. `0` means "send `value_usd.min = 0`". The empty and min-zero holder results stay distinct.

`premium_labels` is absent from the request model. The client pins it to `false` in the body.

## Frozen resource limits

`NansenLimits` is finite and caller-supplied. It is a local test parameter, not a provider allowance.

| Field | Rule |
|---|---|
| `max_requests` | Positive integer. Counted before each transport call. |
| `max_pages` | Positive integer. Counted per collected page. |
| `max_bytes` | Positive integer. Counted across every retained response body, before framing. |
| `max_credits` | Positive decimal. The cap check uses, for each attempt, the settled charge when the provider reported one, else the conservative reservation. |
| `deadline_utc` | ISO-8601 UTC string or `None`. Checked before each call. |
| `per_page` | Integer in 1..1000. |

No retry, no upgrade, no alternate paid route, no x402 payment path exists.

## Frozen evidence interface

`NansenEvidence` retains the D01 portable record groups. Raw provider text is data, never an instruction.

| Group | Retained fields |
|---|---|
| Identity | `evidence_schema`, `profile_version`, `conventions_version`, provider/version, endpoint, network, chain_id, package/run identity, parent lineage |
| Source/request | operation, method, path, request body hash, provider `X-Request-Id`, response content hash, collection time |
| Costs | attempted requests, reserved credits, quoted credits, deducted credits, remaining credits (when sent), cap state |
| Holder rows | `address`, raw `token_amount` text, raw `ownership_percentage` text, raw `value_usd` text or null, `address_label`, pagination `is_last_page` |
| Flow buckets | `date`, `bucket_end`, `is_complete`, raw `price_usd`, `token_amount`, `value_usd`, `holders_count`, `total_inflows_count`, `total_outflows_count`, raw DEX/CEX fields |
| Timing/quality | requested window, bucket start/end, completeness, missing and duplicate starts, warnings, returned and uncollected coverage, availability (recorded as `unknown` when the provider sends none) |
| Field meaning | unit verdict per field, null meaning, label tier, classification limits |

Raw numeric text: the client parses response JSON with `parse_float=str` and keeps the exact decimal text. It never divides by `10^18`, never converts a null to zero and never sums fractional or negative count fields.

## Frozen report interface

`NansenReport` contains: `report_schema`, `request_sha256`, `question` (preserved), `answer_state`, `findings[]`, `limitations[]`, `coverage`, `unknowns[]`, `source_hashes[]`, `engine` identities.

Each `Finding` carries: `code`, `verdict`, `statement`, `source_refs[]`, `limitations[]`.

Verdicts: `SUPPORTED`, `LIMITED`, `UNRESOLVED`, `UNAVAILABLE`, `UNKNOWN`.

Finding codes and permitted verdicts:

| Code | Verdict | Statement rule |
|---|---|---|
| `HOLDER_INVENTORY` | `SUPPORTED` | "N address records returned in provider descending balance order." Addresses are contracts or accounts, not people. |
| `HOLDER_PAGINATION` | `LIMITED` | Reflects `is_last_page`. A non-last page never becomes 100%. |
| `HOLDER_LABELS` | `LIMITED` | Provider address classifications. Do not add overlapping categories as disjoint groups. |
| `HOLDER_OWNERSHIP_PERCENTAGE` | `UNRESOLVED` | Raw text retained; denominator and scaling unqualified. |
| `HOLDER_TOKEN_AMOUNT_UNITS` | `UNRESOLVED` | Raw text retained; no scaling applied. |
| `HOLDER_VALUE_USD` | `UNAVAILABLE` or `LIMITED` | `UNAVAILABLE` when every value is null. Preserve null. |
| `FLOW_CATEGORY` | `LIMITED` | Selected provider category, not all holders. |
| `FLOW_BUCKET_COVERAGE` | `LIMITED` | Expected starts, returned starts, missing and incomplete lists, and complete seconds. Complete seconds only count unique valid intervals inside the window; conflicting intervals make the total unavailable (`null`). |
| `FLOW_COUNTS` | `UNRESOLVED` | Fractional or negative values present; not event or amount counts. |
| `FLOW_DEX_CEX` | `UNAVAILABLE` | Every field null for a non-exchange label. Never zero. |
| `FLOW_PRICE` | `UNRESOLVED` | Daily median or current-day spot; not an hourly price. |
| `FLOW_RECORDS` | `UNAVAILABLE` | The question asks for flow records but the run did not request them. |
| `BUYING` | `UNRESOLVED` | The question asks about buying; flows and transfers do not evidence a purchase. |
| `CONCENTRATION` | `UNRESOLVED` | Needs a documented supply and qualified units. |

`answer_state` is computed from the claims the question names, by a small documented keyword map (`inventory`, `concentration`, `flows`, `buying`), and from whether the whole question is covered. The package checks that every question token is either neutral or part of a recognized claim; a leftover token marks the question uncovered. `SUPPORTED_OBSERVATIONS` means the whole question is covered, every named claim has a supported or limited finding and no stop; `PARTIAL` means a claim is unresolved or unavailable, the question is not fully covered, or a stop occurred; `UNAVAILABLE` means no named claim is supported and the run did not stop. An unmatched or mixed question is never labelled supported, and a generic `question_coverage` limitation is added when the question is not fully covered. A claim whose operation was requested but produced no usable evidence because the run stopped gets a stop-aware finding (with the stable stop code), never a "not requested" statement; a "not requested" statement appears only when the operation is absent from the request. `limitations[]` names each unresolved named claim (`concentration`, `whole_token_flows`, `buying`) with its missing dependency. The question text is preserved exactly and is never used as a claim label. This supersedes the initial draft, which mislabelled an unrelated supported question.

## Local resource/fault matrix (frozen)

| Case | Required behavior |
|---|---|
| Allowlisted operation | Call the injected transport exactly once per operation. |
| Non-allowlisted operation or path | Raise `NansenContractError` before any transport call. |
| Default construction | Perform no I/O. There is no default transport. |
| Auth | The client sets no `apikey`. The injected transport owns any credential. |
| Request budget reached | Raise `NansenBudgetExhausted` before the call. |
| Byte budget exceeded by one response | Refuse before framing; record the attempted call. |
| Credit cap reached by committed cost | Raise `NansenBudgetExhausted` before the call. A settled charge replaces its reservation; an unknown settlement keeps the reservation. A quote above the reservation constrains the next call. |
| Terminal failure or stop | A failed or stopped operation stops the run before the next operation. |
| Deadline passed | Raise `NansenTimeout` before the call. |
| Injected timeout | Record a partial result; no retry. |
| Injected cancellation | Record a partial result; no retry. |
| HTTP 401 | `NansenAuthError`, sanitized, no body or headers leaked. |
| HTTP 429 | `NansenRateLimited`, sanitized, `retry_after` retained only as a number. |
| HTTP 402 | `NansenPaymentRequired`, sanitized, no payment path taken. |
| HTTP 4xx/5xx other | `NansenProviderError` with a bounded documented provider `code` only; otherwise a local `HTTP_<status>` code. Instruction-like text is never reflected. |
| Received provider failure | The failure record keeps the received status, the allowlisted headers (request id, quoted/deducted/remaining credits, retry-after) and the response hash. A pre-dispatch denial keeps them `null`. |
| Oversized or malformed reply | `NansenContractError`; no row retained. |
| Wrong token or network echo | `NansenContractError`; refuse the response. |
| Fractional or negative count field | Keep the raw text; mark `FLOW_COUNTS` unresolved; never sum. |
| Null amount or value field | Keep null; never zero. |
| Partial page (`is_last_page=false`) | Record limited pagination; uncollected rows unknown. |
| Duplicate bucket or row | Record a duplicate; never double count. Complete seconds count each unique interval once. |
| Duplicate operation | Refuse at input validation; do not attach a discarded response to a finding. |
| Overlapping or reversed intervals | Complete seconds become unavailable (`null`) rather than a wrong total. This covers two complete buckets that share a start but have different ends. |
| Malformed credit header | Never trust the malformed text. Keep the other valid header facts and the response hash; the malformed value stays `null`. A credit is a finite nonnegative decimal; `NaN`, a signaling NaN, a positive or negative infinity, a negative finite value or malformed text is `null` in every credit field on success and on received failure. |
| Missing expected bucket | Record the missing start; coverage stays limited. |
| Incomplete bucket | Keep visible; exclude from complete totals. |
| Stale or future evidence | Classify with the D01 awareness rule; never silently fresh. |
| Provider warning text | Retain as data; never execute it. |
| Report build | Deterministic: same evidence gives the same report hash. |
| JSON round-trip | `from_dict(to_dict(x))` equals `x` for request, evidence and report. |

## Integration interface (proposed for lane 2)

Lane 2 mounts the package into the existing authenticated investigation path. This package does not add storage, a scheduler, a dashboard or a route.

1. Build a `NansenRequest` from the authenticated investigation, owner taken from identity, never caller input.
2. Inject a real `NansenTransport` that owns the credential. This package ships no live transport.
3. Call `run_research(request, transport, clock)` to get `(evidence, report)`.
4. Persist the report and the frozen evidence by their hashes under the existing record contract.
5. Save and reopen through the existing job and record paths. A serialized round-trip here is not durable storage.

A material change to this interface needs controller `%0` approval before a consumer changes.
