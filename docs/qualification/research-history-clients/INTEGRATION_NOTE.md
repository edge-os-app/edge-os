# P07 → #58 HTTP client integration note

Status: LOCAL library for P07 review (issue #10), task `P07-HTTP-L3-20261012-01 v2`. It adds the two
actual injected clients the accepted `EnvioHypersyncSource` and corroboration expect. It makes no
provider call, reads no credential and qualifies no real pool. It grants no wiring, credential,
provider, wallet, deployment or main-branch authority.

This note closes prerequisites 1 and 2 of `docs/qualification/research-history/COLLECTION_PACKET.md`
and retains prerequisite 3 (`#58` job reservation and owner budget) and the approval of the packet
bounds. All actual statuses remain `NOT_RUN`.

## Change, preserved behavior, proof

- Change: add `apps/api/src/edge_os_api/research_history/http_clients/` (`client_config.py`,
  `http_transport.py`, `envio_query_client.py`, `quicknode_rpc_client.py`, `__init__.py`), tests under
  `apps/api/tests/research_history/http_clients/` and the two documents in this folder.
- Preserved: the accepted adapter, `EnvioHypersyncSource`, `corroborate_records`, `read_chain_id`, the
  P07 module, the P02 contract and the package `__init__.py` are unchanged. The clients plug into the
  accepted protocols; they are imported explicitly and are not added to the top-level package
  namespace.
- Proof: `cd apps/api && uv run --frozen pytest tests/research_history/http_clients -v` passes (47
  tests); the affected `tests/research_history` suite passes (166 tests); `python3 -B -m unittest -v
  test_p07` passes (73 tests); `python3 -B docs/contracts/p02/check_contract.py` passes. Exact outputs
  are kept under the assigned evidence folder and are not part of the commit.

## Boundary

The subpackage is a library. It performs no I/O at import or construction, opens no socket itself and
reads no environment variable or credential file. `StdlibHttpTransport` is the one shipped live
transport; it is used only when a caller injects it with an explicit endpoint. The clients ship no
default endpoint, token or client, and nothing activates them automatically. The accepted top-level
modules remain offline; the accepted isolation check (`test_package_has_no_live_transport_or_
environment_discovery`) inspects only the top-level `*.py` files, so this additive subpackage does not
weaken it.

## Construction interface

| Class | Signature |
|---|---|
| `HttpEnvioQueryClient` | `HttpEnvioQueryClient(*, endpoint, bearer_token, transport, bounds, clock=time.monotonic, cancel=None)` |
| `HttpQuickNodeRpcClient` | `HttpQuickNodeRpcClient(*, endpoint, transport, bounds, headers=None, allowed_methods=READ_ONLY_METHODS, clock=time.monotonic, cancel=None)` |
| `ClientBounds` | `ClientBounds(deadline_seconds, connect_timeout_seconds, max_response_bytes, max_request_bytes, max_blocks_per_page)` |
| `StdlibHttpTransport` | `StdlibHttpTransport(connect=_default_connect, clock=time.monotonic)` |

`HttpEnvioQueryClient` implements the accepted `EnvioQueryClient.query(request)`. `HttpQuickNodeRpcClient`
implements the accepted `QuickNodeRpcClient.call(method, params)`. Both satisfy their accepted protocols
(asserted in tests).

## Call interface

- `HttpEnvioQueryClient.query(request: HistoryRequest) -> Mapping[str, Any] | None`. It turns the
  request into one Envio HyperSync `POST <endpoint>/query` and returns the parsed native response.
  `endpoint` must be the host base without a path; the token is the `Authorization: Bearer` header.
  `from_block` is `request.cursor_after` when set, else `request.from_block`. The page span is bounded
  to `max_blocks_per_page` blocks and the log count to `request.max_rows`, and `include_all_blocks` is
  requested so the accepted framing can prove the page-edge block facts. The client returns the native
  mapping; the framing owns the `complete`/cursor decision.
- `HttpQuickNodeRpcClient.call(method: str, params: Sequence[Any]) -> Any`. It sends one JSON-RPC 2.0
  request and returns the envelope's `result`. It only allows a caller-narrowed subset of the documented
  read-only methods (`READ_ONLY_METHODS`); no signing, broadcast, account or state-changing method can
  be enabled.

Pinned wire (public first-party documentation, read 2026-10-12): HyperSync body fields `from_block`,
`to_block`, `logs[]`, `field_selection`, `include_all_blocks`, `max_num_logs`, `max_num_blocks`; the
response carries `archive_height`, `next_block`, `total_execution_time`, `data` (`blocks`, `logs`) and
an optional `rollback_guard`. Monad QuickNode is standard JSON-RPC 2.0. Monad coverage and the exact
served shape are `NOT_VERIFIED` until a separately authorized run.

## Accounting and liability

Each call increments an attempt **before sending**, so a call that raises still counts. `accounting()`
returns `{"attempted_requests", "completed_requests", "unknown_liability"}`. `completed_requests` counts
replies that returned a valid payload; `unknown_liability` is the remainder and may still have been
served and consumed by the provider. This is a local count only. It grants no quota and starts no
second durable counter: request limits and local usage feed lane2's existing owner/run quota engine.

## Cancellation and bounds

- `deadline_seconds` bounds the whole call: the socket wait (connect and response-header phase) is set
  to the remaining deadline and the deadline is re-checked between body reads;
  `connect_timeout_seconds` caps each socket wait below the deadline; `max_response_bytes` bounds the
  retained reply body while streaming; `max_request_bytes` bounds the request body;
  `max_blocks_per_page` bounds one HyperSync page's block span.
- `cancel` is an injected `() -> bool` flag. It is checked before the socket opens and between body
  reads, so a cancellation takes effect before and during the operation. A set flag raises
  `SourceCancelled`; the accepted collector records `CANCELLED`.

## Errors

| Type | Meaning |
|---|---|
| `ClientConfigError(ValueError)` | A caller/programmer defect: unsafe endpoint, missing credential, bad bounds, malformed request, non-read-only method, oversized request. Raised before send and propagated (never mistaken for a provider failure). |
| `HttpProviderError(SourceFailure)` | A refused provider reply. Codes: `AUTH_DENIED`, `PAYMENT_REQUIRED`, `RATE_LIMITED`, `REDIRECT_REFUSED`, `HTTP_STATUS`, `UNSUPPORTED_CONTENT_ENCODING`, `OVERSIZED_RESPONSE`, `MALFORMED_PROVIDER_RESPONSE`, `PROVIDER_ERROR`. |
| `SourceTimeout` | A time bound: socket timeout or the absolute deadline between reads. |
| `SourceCancelled` | The caller's cancel flag was set. |
| `OSError` | A genuine transport failure (for example a refused connection). |

A redirect is never followed; a non-identity `Content-Encoding` is refused; a malformed HTTP framing
reply (a bad status line, oversized headers, or a short body against `Content-Length`) is refused as
`MALFORMED_PROVIDER_RESPONSE`; the connection is always closed; there is no retry and no fallback
endpoint. No provider-controlled text is copied into a message: the endpoint path, query and
credentials never appear in an error (`safe_endpoint` drops them), the `Content-Encoding` value is not
reproduced, and a JSON-RPC error is reported with at most its non-boolean integer code, never its
provider-controlled message.

## Safe ownership

`#58` owns all wiring: it provides the endpoint, the host-side credential, request pacing, response
hashing, the injected `ClientBounds`, the `cancel` flag and the job reservation/owner budget. The
credential stays host-side and never reaches the dataset, logs, evidence or a model. No real run is
authorized by this milestone; a run needs the separately authorized packet in this folder.

## Not verified

Any real Envio, QuickNode or Monad behavior, the actual native response shape, provider fees, coverage
or rights, and provider cost. The clients are written against the pinned 2026-10-12 wire and tested
only with owned loopback servers and authored replies. `P07-HISTORY-L3` and the #58 actual-data
requirement stay open until actual evidence.
