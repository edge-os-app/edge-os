# Nansen research integration note

For lane 2. This note describes how the authenticated investigation path mounts the local `edge_os_api.nansen_research` package. This package adds no route, storage table, scheduler or dashboard. A serialized round-trip in this package is not durable storage.

## Mounting steps

1. Build a `NansenRequest` from the authenticated investigation. Take the owner from the authenticated identity, never from caller input.
2. Inject a real `NansenTransport`. The transport owns the endpoint and the credential. The package ships no live transport and reads no credential.
3. Call `run_research(request, transport, clock=...)`. It returns a `NansenRun` with `evidence` and `report`.
4. Persist the report and the frozen evidence by their hashes under the existing record contract. Keep the evidence package after any cleanup so a later review can rebuild the report.
5. Save and reopen the report through the existing job and record paths. The report keeps its `request_sha256`, `source_hashes` and `engine` identities on reopen.

## Stable interface

| Symbol | Kind | Meaning |
|---|---|---|
| `NansenRequest` | input | The versioned question, token, network, window, queries and limits |
| `NansenTransport` | protocol | The injected provider path |
| `run_research` | function | Collect and build; returns `NansenRun` |
| `NansenRun` | value | `evidence`, `report`, `outcomes` |
| `NansenReport` | output | Deterministic findings, `answer_state`, `limitations` and coverage |
| `NansenEvidence` | output | The immutable evidence package |

Schemas: `nansen-research-request/1`, `nansen-research-evidence/1`, `nansen-research-report/1`.

## Input errors a caller fixes

| Code | When |
|---|---|
| `REQUEST_SCHEMA_INVALID` | Wrong request schema string |
| `QUESTION_INVALID`, `TOKEN_INVALID` | Empty question or token |
| `WRONG_NETWORK` | Network other than `monad` or chain other than `143` |
| `WINDOW_INVALID` | Window start not before end |
| `HOLDER_LABEL_INVALID`, `HOLDER_ORDER_INVALID`, `HOLDER_FILTER_INVALID` | Bad holder query |
| `FLOW_LABEL_INVALID` | Bad flow label |
| `OPERATIONS_EMPTY`, `OPERATIONS_DUPLICATE`, `OPERATION_NOT_ALLOWED` | No operation, a repeated operation, or an unknown operation |
| `BODY_NOT_ALLOWED`, `PREMIUM_NOT_ALLOWED`, `BODY_INVALID` | A body the allowlist does not permit |
| `REQUEST_LIMIT`, `CREDIT_LIMIT` (`NansenBudgetExhausted`) | A finite cap is reached |
| `DEADLINE` (`NansenTimeout`) | The local deadline passed |
| `INVALID_LIMIT` (`NansenLimitError`) | A limit is missing, negative or not an integer |

## Provider failures the collector records without retry

These are expected provider or transport failures. The run records the attempted call and keeps a partial result.

| Code | Meaning |
|---|---|
| `UNAUTHENTICATED` (401) | The provider refused access |
| `PAYMENT_REQUIRED` (402) | The provider asked for payment; no payment path is taken |
| `RATE_LIMITED` (429) | The provider rate limit rejected the request; `retry_after` is kept only when it is a number |
| a 403 | The provider `code` (for example `insufficient_credits`, `forbidden`, `plan_upgrade_required`) or `HTTP_403` |
| `MALFORMED_PROVIDER_RESPONSE`, `OVERSIZED_RESPONSE` | The response violates the contract; no row is retained |
| `WRONG_NETWORK`, `WRONG_TOKEN`, `WRONG_OPERATION`, `NO_RECORDED_RESPONSE` | The response contradicts the request or the transport is exhausted |
| any other provider `code`, or `HTTP_<status>` | Any other provider error. Only a bounded documented provider code is used; instruction-like text is not reflected. |

Error text is sanitized. A caller sees a stable code; no response body, header or credential is exposed.

## Owner and run accounting

- Set `owner_id` from authenticated identity, never from the request.
- Record the run id, the attempt count, the committed, quoted and deducted credits, and the request/response hashes. The committed total uses the settled charge when the provider reported one, else the conservative reservation.
- A caps breach, a terminal provider failure, a cancellation or a deadline stops the run before the next operation and keeps the partial result. It never increases the cap or retries.
- A received provider failure keeps its status, allowlisted headers and response hash on the failure record. A pre-dispatch denial keeps those fields null.
- `answer_state` reads the claims the question names (inventory, concentration, flows, buying, amount) and reports `SUPPORTED_OBSERVATIONS`, `PARTIAL` or `UNAVAILABLE`. The `amount` claim is assigned at clause level: a returned-inventory count clause (inventory noun, count cue, retrieval cue) is a supported count, while a token amount/value/supply or a count with no returned-inventory clause is the unresolved `amount` claim. `limitations` names each unresolved named claim (concentration, whole_token_flows, buying, amount) plus `question_coverage` when the question is not fully covered. A claim with no collected evidence gets an explicit finding (`FLOW_RECORDS` when flows were not requested, `HOLDER_INVENTORY` or `BUYING` for a question the run did not collect). The question text is preserved and never relabelled.

## Actual versus fixture labels

- A run over `RecordedNansenTransport` is an authored fixture run. Label it `AUTHORED_FIXTURE`.
- A run over a real transport is an actual provider run. Label it `ACTUAL_PROVIDER` and attach the provider request ids and credit headers.
- Never present a fixture result as provider qualification or bounty evidence.

## What lane 2 must still prove

Actual auth, job wiring, durable save and reopen, and the real transport. Those are outside this local lease.
