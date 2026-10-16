# Nansen native HTTP transport checks

Task `NANSEN-HTTP-L4-20261014-LOCAL-v1`, issues #58/#51. LOCAL only. `NansenHttpTransport` in
`apps/api/src/edge_os_api/nansen_research/http_transport.py` is the concrete `NansenTransport` for the
native Nansen API. It is not mounted in the application. The contract is `CONTRACT.md`.

## Proposed verdicts

- Local adapter: `LOCAL_TESTED`.
- Actual provider request: `NOT_RUN`. No key, account or provider response was used.
- Application mount, save and reopen: `NOT_STARTED` (lane 2 composition lease).

## Run

```sh
cd apps/api
uv run --frozen pytest tests/nansen_http_transport tests/nansen_research tests/research_history/http_clients -v
```

## Reuse of the existing HTTP seam

The adapter adds no HTTP stack, retry, quota ledger or authentication system. It calls the existing
`research_history.http_clients.http_transport.HttpTransport` protocol. Production injects
`StdlibHttpTransport`, which keeps its socket, streaming byte cap, deadline watchdog, cancellation
between reads, redirect non-follow and `finally` cleanup unchanged. `NansenClient` keeps its body
pinning, reservations, status mapping and retained headers. The loopback tests run the real
`StdlibHttpTransport` with an injected connector that points the fixed `https://api.nansen.ai` origin at
an owned `127.0.0.1` listener.

## Current source evidence (public documentation, rechecked 2026-10-14)

Context7 `/websites/nansen_ai`, resolved first, then one query per concept. Context7 still cites
`getting-started/api-structure-and-base-url`, but that page now returns "Page Not Found", so it is no
longer cited here. Current first-party pages, read directly as Markdown:

- https://docs.nansen.ai/api/token-god-mode/holders.md — the embedded OpenAPI 3.1 document names the
  server `https://api.nansen.ai`, an `apiKey`-type security scheme in header `apikey`, and
  `POST /api/v1/tgm/holders` with a JSON body.
- https://docs.nansen.ai/getting-started/authentication.md — every request carries the key in the
  `apikey` header; the page states lowercase `apikey` is the canonical form. The adapter sends `apikey`.
- https://docs.nansen.ai/api/token-god-mode/flows — the Context7 summary of this page shows a `GET`
  heading with "no request body"; the accepted pinned source (`SOURCE_EVIDENCE.md`, the page's embedded
  OpenAPI) and the accepted client both use `POST /api/v1/tgm/flows` with a JSON body. The adapter keeps
  the accepted `POST`. This summary conflict is recorded, not resolved by a provider call.

No `/flow-intelligence` route is admitted. Account plan, per-call pricing, coverage and data-use rights
remain unresolved; documentation does not qualify them.

## What a pass shows

- Only the two pinned routes reach the wire, with the literal path, headers and canonical body.
- Missing or unsafe keys and bounds are refused at construction; nothing reads the environment.
- A passed deadline or a set cancel flag makes zero attempts; an oversized or non-finite body is not sent.
- One admitted request makes one attempt. Redirects, oversized or malformed replies and key echoes are
  refused, including a key that standard JSON decoding reconstructs from `\u` escapes in any string
  value or member name. A reply inside the byte cap but nested deeper than the standard JSON decoder
  accepts is refused as `MALFORMED_PROVIDER_RESPONSE`, so an earlier result stays a partial report. Timeout, cancellation, network and framing failures become the existing sanitized Nansen
  errors with no chained source text, so the collector keeps a partial report. An unrecognized HTTP-layer
  error code is replaced by `UNRECOGNIZED_HTTP_FAILURE`, so injected text never reaches a saved field.
- `NansenClient` and `run_research` work unchanged over the adapter, including 401/402/403/429/5xx,
  request/credit caps and conservative reservations after an unknown outcome.
- Each loopback socket is closed after success and failure.

## What a pass does not show

- Any Nansen behavior, account access, pricing, coverage or rights.
- Exact-deadline behavior during DNS resolution or the initial TCP connect: the existing
  `StdlibHttpTransport` residual stands. Provider-only egress is not enforced by the host.
- Detection of a key hidden by an encoding other than standard JSON escapes (for example base64 or URL
  encoding) or split across values.
- Removal of the key from Python traceback frame locals in process memory.
