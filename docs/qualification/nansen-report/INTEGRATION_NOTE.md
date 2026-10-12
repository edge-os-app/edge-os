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
| `NansenReport` | output | Deterministic, source-linked findings and coverage |
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
| `OPERATIONS_EMPTY`, `OPERATION_NOT_ALLOWED` | No operation or an unknown operation |
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
| any other provider `code`, or `HTTP_<status>` | Any other provider error |

Error text is sanitized. A caller sees a stable code; no response body, header or credential is exposed.

## Owner and run accounting

- Set `owner_id` from authenticated identity, never from the request.
- Record the run id, the attempt count, the reserved, quoted and deducted credits, and the request/response hashes.
- A caps breach stops dispatch and keeps the partial result. It never increases the cap or retries.

## Actual versus fixture labels

- A run over `RecordedNansenTransport` is an authored fixture run. Label it `AUTHORED_FIXTURE`.
- A run over a real transport is an actual provider run. Label it `ACTUAL_PROVIDER` and attach the provider request ids and credit headers.
- Never present a fixture result as provider qualification or bounty evidence.

## What lane 2 must still prove

Actual auth, job wiring, durable save and reopen, and the real transport. Those are outside this local lease.
