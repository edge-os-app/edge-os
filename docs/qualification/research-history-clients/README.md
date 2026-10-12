# P07 HTTP source-client checks

These checks exercise the local HTTP source clients
`apps/api/src/edge_os_api/research_history/http_clients/` with authored replies and an owned
`127.0.0.1` HTTP server. They make no external call, read no credential or environment file and run no
downloaded code. The reused P07 qualification module and the P02 contract checker are used read-only.

Run from the repository root:

```sh
cd apps/api
uv run --frozen pytest tests/research_history/http_clients -v
uv run --frozen pytest tests/research_history -q
cd ../..
cd docs/qualification/p07 && python3 -B -m unittest -v test_p07
cd ../../..
python3 -B docs/contracts/p02/check_contract.py
```

Files:

| File | Role |
|---|---|
| `apps/api/src/edge_os_api/research_history/http_clients/` | Bounded HTTP transport, the Envio HyperSync query client and the QuickNode read-only JSON-RPC client, plus shared bounds and errors. |
| `apps/api/tests/research_history/http_clients/` | Public-seam tests, the owned-loopback server and the accepted labelled synthetic fixtures. |
| `docs/qualification/research-history-clients/INTEGRATION_NOTE.md` | The client interface, accounting/error/cancellation contract and safe ownership. |
| `docs/qualification/research-history-clients/ACTUAL_COLLECTION_PACKET.md` | The finite later-collection proposal. All actual statuses are `NOT_RUN`. |

Fixtures are labelled `SYNTHETIC_FIXTURE`. Addresses, hashes and amounts are invented. The native
HyperSync pages the loopback server replays are built from the accepted synthetic fixtures; they are not
provider or chain evidence.

What a pass shows: the clients satisfy the accepted protocols; the transport enforces its byte, deadline
and cancellation bounds over a real loopback socket; refused statuses, malformed/oversized replies,
redirects, content encodings, wrong RPC envelopes and non-read-only methods are refused with stable
codes; no credential leaks; and the accepted `collect` and `corroborate_records` consumers run end to end
over the real client boundary. What it does not show: the behavior of Envio, QuickNode or Monad, the
completeness of any real window, provider fees/coverage/rights, delivery or finality. No fresh history is
qualified.

## Case map

| Case ID | Required case | Test |
|---|---|---|
| RH-HTTP-C01 | Envio client satisfies the accepted protocol | `test_envio_query_client.py::test_client_satisfies_the_accepted_protocol` |
| RH-HTTP-C02 | Construction performs no I/O; a transport is required | `test_envio_query_client.py::test_construction_performs_no_io_and_requires_a_transport` |
| RH-HTTP-C03 | Success returns the native response and counts one attempt | `test_envio_query_client.py::test_success_returns_the_native_response_and_accounts_one_attempt` |
| RH-HTTP-C04 | The cursor advances the requested from-block | `test_envio_query_client.py::test_cursor_after_advances_the_requested_from_block` |
| RH-HTTP-C05 | The page span is bounded by `max_blocks_per_page` | `test_envio_query_client.py::test_page_span_is_bounded_by_max_blocks_per_page` |
| RH-HTTP-C06 | Provider statuses map to stable codes | `test_envio_query_client.py::test_provider_status_codes_are_refused_with_stable_codes` |
| RH-HTTP-C07 | Malformed replies are refused | `test_envio_query_client.py::test_malformed_replies_are_refused` |
| RH-HTTP-C08 | A non-identity content encoding is refused | `test_envio_query_client.py::test_unsupported_content_encoding_is_refused` |
| RH-HTTP-C09 | A provider error is one attempt with no retry | `test_envio_query_client.py::test_provider_error_is_one_attempt_with_no_retry` |
| RH-HTTP-C10 | Cancel before send never calls the transport | `test_envio_query_client.py::test_cancel_before_send_never_calls_the_transport` |
| RH-HTTP-C11 | A transport failure propagates and counts unknown liability | `test_envio_query_client.py::test_transport_failure_propagates_and_counts_unknown_liability` |
| RH-HTTP-C12 | The bearer token never leaks into an error | `test_envio_query_client.py::test_the_bearer_token_never_leaks_into_an_error` |
| RH-HTTP-C13 | Unsafe endpoints and malformed requests are refused | `test_envio_query_client.py::test_unsafe_endpoints_and_malformed_requests_are_refused` |
| RH-HTTP-C14 | A loopback collection completes through the accepted consumer | `test_envio_query_client.py::test_loopback_collection_completes_through_the_accepted_consumer` |
| RH-HTTP-C15 | The byte bound holds at the real client boundary | `test_envio_query_client.py::test_byte_bound_at_the_real_client_boundary` |
| RH-HTTP-C16 | A slow reply is a timeout at the real client boundary | `test_envio_query_client.py::test_slow_reply_at_the_real_client_boundary_is_a_timeout` |
| RH-HTTP-C17 | The transport returns a bounded reply over loopback | `test_http_transport.py::test_transport_returns_a_reply_over_loopback` |
| RH-HTTP-C18 | The transport refuses an oversized reply | `test_http_transport.py::test_transport_refuses_an_oversized_reply` |
| RH-HTTP-C19 | The transport does not follow a redirect | `test_http_transport.py::test_transport_does_not_follow_a_redirect` |
| RH-HTTP-C20 | The transport times out on a slow reply | `test_http_transport.py::test_transport_times_out_on_a_slow_reply` |
| RH-HTTP-C21 | The transport cancels before opening a socket | `test_http_transport.py::test_transport_cancels_before_opening_a_socket` |
| RH-HTTP-C22 | The transport cancels during a stream | `test_http_transport.py::test_transport_cancels_during_a_stream` |
| RH-HTTP-C23 | The transport enforces the deadline between reads | `test_http_transport.py::test_transport_enforces_the_deadline_between_reads` |
| RH-HTTP-C24 | The transport closes the connection on success and failure | `test_http_transport.py::test_transport_closes_the_connection_on_success_and_failure` |
| RH-HTTP-C25 | The transport refuses an unsafe URL or scheme | `test_http_transport.py::test_transport_refuses_an_unsafe_url_and_scheme` |
| RH-HTTP-C26 | QuickNode client satisfies the accepted protocol | `test_quicknode_rpc_client.py::test_client_satisfies_the_accepted_protocol` |
| RH-HTTP-C27 | Construction performs no I/O; a transport is required | `test_quicknode_rpc_client.py::test_construction_performs_no_io_and_requires_a_transport` |
| RH-HTTP-C28 | A call returns the result and sends a JSON-RPC envelope | `test_quicknode_rpc_client.py::test_call_returns_the_result_and_sends_a_jsonrpc_envelope` |
| RH-HTTP-C29 | Ids increment per call | `test_quicknode_rpc_client.py::test_ids_increment_per_call` |
| RH-HTTP-C30 | Malformed envelopes (wrong id, missing jsonrpc, neither/both) are refused | `test_quicknode_rpc_client.py::test_malformed_envelopes_are_refused` |
| RH-HTTP-C31 | A provider error becomes a refused reply | `test_quicknode_rpc_client.py::test_provider_error_becomes_a_refused_reply` |
| RH-HTTP-C32 | Only read-only methods are allowed | `test_quicknode_rpc_client.py::test_only_read_only_methods_are_allowed` |
| RH-HTTP-C33 | Params must be a JSON array; the request byte bound holds | `test_quicknode_rpc_client.py::test_params_must_be_a_json_array_and_requests_respect_the_byte_bound` |
| RH-HTTP-C34 | Provider statuses map to stable codes | `test_quicknode_rpc_client.py::test_provider_status_codes_are_refused` |
| RH-HTTP-C35 | Cancel before send never calls the transport | `test_quicknode_rpc_client.py::test_cancel_before_send_never_calls_the_transport` |
| RH-HTTP-C36 | The path key never leaks into a safe endpoint or error | `test_quicknode_rpc_client.py::test_the_path_key_never_leaks_into_a_safe_endpoint_or_error` |
| RH-HTTP-C37 | Unsafe endpoints are refused | `test_quicknode_rpc_client.py::test_unsafe_endpoints_are_refused` |
| RH-HTTP-C38 | A loopback corroboration completes through the accepted consumer | `test_quicknode_rpc_client.py::test_loopback_corroboration_completes_through_the_accepted_consumer` |

The existing P07 checks (`docs/qualification/p07`) and the P02 checker remain the controlling regression
suite. The accepted adapter adds RH-C01 to RH-C54; task P07-SOURCE adds RH-C55 to RH-C102; this task adds
RH-HTTP-C01 to RH-HTTP-C38 and changes no existing case.
