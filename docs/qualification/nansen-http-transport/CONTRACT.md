# Nansen native HTTP transport contract

Task `NANSEN-HTTP-L4-20261014-LOCAL-v1`, issues #58/#51. Frozen before code on base
`1b36fae3c221e5cfe458ea982e31fc848330b125`. LOCAL adapter only: it is not mounted in the application,
grants no provider use and was exercised with synthetic keys and an owned loopback listener only.

## Module and interface

New module `apps/api/src/edge_os_api/nansen_research/http_transport.py`. It adds one class,
`NansenHttpTransport`, that satisfies the accepted `NansenTransport` protocol:

```python
request(operation: str, path: str, body: Mapping[str, Any]) -> NansenResponse
```

No `__init__.py` export changes. A later consumer imports the module directly.

## Constructor (keyword-only, no defaults except `cancel`)

| Field | Rule | Refusal |
|---|---|---|
| `api_key: str` | Non-empty, printable ASCII without whitespace or control characters. Supplied by the trusted caller. | `NansenInputError("INVALID_CREDENTIAL")`, message never contains the value |
| `http: HttpTransport` | The existing `research_history.http_clients` seam. Production passes `StdlibHttpTransport()`. | `NansenInputError("INVALID_TRANSPORT")` |
| `connect_timeout_seconds: float` | Finite, positive, not bool. Passed as the per-wait socket `timeout`. | `NansenLimitError` (`INVALID_LIMIT`) |
| `deadline_monotonic: float` | Finite, not bool. One absolute `time.monotonic()` instant for the whole job; the same value is passed to every request and is never reset. | `NansenLimitError` |
| `max_request_bytes: int` | Positive integer, not bool. | `NansenLimitError` |
| `max_response_bytes: int` | Positive integer, not bool. | `NansenLimitError` |
| `cancel: Callable[[], bool] \| None = None` | Optional caller cancellation flag. Must be callable when given. | `NansenLimitError` |

Construction reads no environment, file or network and opens no socket. `repr()` shows the origin and
the caps, never the key.

## Responsibility split

- `NansenClient` stays the semantic owner: operation allowlist, body pinning (network, premium labels),
  request/credit reservations, deadline in UTC, byte total, status mapping (401/402/403/429/other),
  retained credit/request-id headers and response hashing. The adapter does not duplicate that ledger.
- The adapter owns the wire: fixed origin `https://api.nansen.ai`, the exact operation/path pair,
  serialization, request size, the `apikey` header, the absolute monotonic deadline, cancellation,
  response size, redirect refusal, credential-echo refusal and the mapping of transport failures to the
  existing Nansen error types.
- `StdlibHttpTransport` owns the socket, streaming byte cap, deadline watchdog, cancellation between
  reads and cleanup. Its DNS/initial-connect interruption residual is unchanged.
- The application keeps owner/global reservation and exact run release before any real credential use.

## Request behavior

1. Admitted pairs only: `holders` → `POST /api/v1/tgm/holders`, `flows` → `POST /api/v1/tgm/flows`.
   Any other operation or path (including a query, fragment, absolute URL, `..` segment or other
   origin) raises `NansenRequestError("ROUTE_NOT_ALLOWED")` before any effect.
2. The body must be a mapping. It is serialized with the package's canonical JSON (`canonical_bytes`:
   sorted keys, no floats, no NaN/Infinity). A nonfinite `Decimal` is also refused. Failure raises
   `NansenRequestError("BODY_NOT_SERIALIZABLE")` with no dispatch.
3. A serialized body longer than `max_request_bytes` raises `NansenRequestError("REQUEST_TOO_LARGE")`
   with no dispatch.
4. A cancelled flag raises `NansenCancelled("CANCELLED")`; a reached deadline
   (`time.monotonic() >= deadline_monotonic`) raises `NansenTimeout("DEADLINE")`. Both make zero
   transport attempts.
5. Exactly one `http.request` call per admitted request: method `POST`, URL origin + path, headers
   `apikey`, `content-type: application/json`, `accept: application/json`, the serialized body,
   `timeout=connect_timeout_seconds`, `deadline=deadline_monotonic`,
   `max_response_bytes=max_response_bytes`, `cancel=cancel`. No retry, redirect follow, pagination,
   premium upgrade or payment header.

## Reply behavior

| Received | Result |
|---|---|
| `HttpResponse` with status 100..599 except 3xx, body within cap, no key echo | `NansenResponse(status, headers, body)` returned unchanged for `NansenClient` (which maps 401/402/403/429/5xx) |
| 3xx status | `NansenContractError("REDIRECT_REFUSED")`, `status` attached, not followed |
| Body longer than `max_response_bytes` (an injected transport that ignored its cap) | `NansenContractError("OVERSIZED_RESPONSE")` |
| Status outside 100..599 or a non-bytes body | `NansenContractError("MALFORMED_PROVIDER_RESPONSE")` |
| Body within the cap but nested deeper than the standard JSON decoder accepts (it raises `RecursionError`, which `NansenClient` does not handle) | `NansenContractError("MALFORMED_PROVIDER_RESPONSE")`, `status` attached, no hash, no chained decoder text; the collector keeps any earlier result as a partial report. A literal key echo in such a body is still reported as `CREDENTIAL_ECHO` |
| Body that is not UTF-8 JSON (ordinary malformed text) | Returned unchanged; `NansenClient` refuses it as `MALFORMED_PROVIDER_RESPONSE` with the original body hash |
| Key text (case-insensitive) in the raw body, in any header name/value, or in any string value or member name that standard JSON decoding (`load_provider_json`, the client's own parser) produces | `NansenContractError("CREDENTIAL_ECHO")`, `status` attached; the response is refused, not redacted, and no hash is claimed. Accepted replies are returned with their original bytes |
| Not an `HttpResponse` | `NansenProtocolError("TRANSPORT_NOT_A_RESPONSE")` (injected-transport defect) |

## Failure mapping

| Raised by `http.request` | Raised by the adapter |
|---|---|
| `SourceTimeout`, `TimeoutError` | `NansenTimeout("TIMEOUT")` |
| `SourceCancelled` | `NansenCancelled("CANCELLED")` |
| `HttpProviderError` `OVERSIZED_RESPONSE` / `MALFORMED_PROVIDER_RESPONSE` | `NansenContractError` with the same code |
| `HttpProviderError` `UNSUPPORTED_CONTENT_ENCODING`, `REDIRECT_REFUSED`, `AUTH_DENIED`, `PAYMENT_REQUIRED`, `RATE_LIMITED`, `HTTP_STATUS` | `NansenProviderError` with that code |
| `HttpProviderError` with any other code (or a non-text code) | `NansenProviderError("UNRECOGNIZED_HTTP_FAILURE")`; the original code is not copied |
| `http.client.HTTPException` | `NansenContractError("MALFORMED_PROVIDER_RESPONSE")` |
| other `SourceFailure` | `NansenTransportError("TRANSPORT_FAILURE")` |
| other `OSError` (refused, reset, DNS) | `NansenTransportError("NETWORK_ERROR")` |
| anything else (`ClientConfigError`, programmer defects) | propagates unchanged |

Mapped errors are raised outside the `except` block, so `__cause__` and `__context__` are `None` and the
original text (which could carry provider or key text) is not retained in the chain. Pre-response
failures keep `status`, `request_id`, credits and `response_sha256` as `None`; nothing is invented.
`NansenClient` keeps its conservative reservation for any failed call. Residual: Python traceback frame
locals still hold the key in process memory; no representation, message or chain exposes it.

## Tests (`apps/api/tests/nansen_http_transport/`)

- `test_nansen_http_request_admission.py`: constructor validation, route allowlist and injection,
  serialization and size refusal, deadline/cancel before dispatch, exact wire call.
- `test_nansen_http_reply_mapping.py`: status pass-through and client mapping (401/402/403/429/5xx),
  redirect, oversized and malformed replies, credential echo, failure mapping, sanitized chains and
  representations, no retry; D2 regressions for a too-deep reply at the adapter and through
  `run_research` (holder result kept, flows failed), and an ordinary non-JSON reply keeping its hash.
- `test_nansen_http_credential_boundaries.py`: D1 regressions — a key reconstructed by JSON escapes in
  values, nested values and member names is refused at the adapter, at `NansenClient`, through
  `run_research` (no evidence, report or hash keeps it) and over a real loopback reply; unknown
  HTTP-layer codes are replaced and known codes keep their classification.
- `test_nansen_http_loopback_run.py`: real `StdlibHttpTransport` with an injected loopback connector,
  `NansenClient` and `run_research` — literal path/header/body received by the owned listener, complete
  and partial runs (including a too-deep flows reply after holder success), oversized stream, timeout and
  in-flight cancellation with cleanup.

Default tests use synthetic keys only. No external listener, key or provider request.
