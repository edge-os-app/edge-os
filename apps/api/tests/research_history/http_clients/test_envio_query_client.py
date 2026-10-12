"""Tests for the concrete injected Envio HyperSync query client.

Most cases drive the client over the deterministic ``FakeTransport``; the accepted
consumer is proven end-to-end over the real transport and an owned loopback server.
No external host, credential or provider is touched.
"""

from __future__ import annotations

import json
import time

import pytest

import _http_support as http
import _support as support

from edge_os_api.research_history import (
    CollectionLimits,
    EnvioHypersyncSource,
    EnvioQueryClient,
    HistoryRequest,
    SourceContext,
    collect,
)
from edge_os_api.research_history.http_clients import (
    ClientBounds,
    ClientConfigError,
    HttpEnvioQueryClient,
    HttpProviderError,
    StdlibHttpTransport,
)
from edge_os_api.research_history.provider_transport import (
    SourceCancelled,
    SourceFailure,
    SourceTimeout,
)

ENDPOINT = "https://monad.hypersync.xyz"
TOKEN = "SECRET-TOKEN-DO-NOT-LEAK"


def _bounds(**overrides):
    values = {"deadline_seconds": 5.0, "connect_timeout_seconds": 2.0, "max_response_bytes": 4096,
              "max_request_bytes": 4096, "max_blocks_per_page": 1000}
    values.update(overrides)
    return ClientBounds(**values)


def _client(transport, **overrides):
    return HttpEnvioQueryClient(endpoint=overrides.pop("endpoint", ENDPOINT), bearer_token=TOKEN,
                                transport=transport, bounds=overrides.pop("bounds", _bounds()),
                                clock=overrides.pop("clock", lambda: 100.0))


def _request(**overrides):
    values = {"provider": "ENVIO_HYPERSYNC", "address": support.POOL, "topic0": support.TOPIC0,
              "from_block": 100, "to_block_exclusive": 111, "cursor_after": None, "max_rows": 64}
    values.update(overrides)
    return HistoryRequest(**values)


def test_client_satisfies_the_accepted_protocol() -> None:
    assert isinstance(_client(http.FakeTransport([])), EnvioQueryClient)


def test_construction_performs_no_io_and_requires_a_transport() -> None:
    transport = http.FakeTransport([])
    _client(transport)
    assert transport.calls == []
    with pytest.raises(TypeError):
        HttpEnvioQueryClient(endpoint=ENDPOINT, bearer_token=TOKEN, bounds=_bounds())  # type: ignore[call-arg]


def test_success_returns_the_native_response_and_accounts_one_attempt() -> None:
    transport = http.FakeTransport([http.response(body=http.page_one())])
    client = _client(transport)
    parsed = client.query(_request())
    assert parsed is not None and parsed["next_block"] == 104
    assert client.accounting() == {"attempted_requests": 1, "completed_requests": 1, "unknown_liability": 0}
    call = transport.calls[0]
    assert call["headers"]["authorization"] == f"Bearer {TOKEN}"
    body = json.loads(call["body"])
    assert body["from_block"] == 100 and body["to_block"] == 111
    assert body["include_all_blocks"] is True
    assert body["logs"] == [{"address": [support.POOL.lower()], "topics": [[support.TOPIC0.lower()]]}]
    assert "topic3" in body["field_selection"]["log"] and "block_hash" in body["field_selection"]["log"]


def test_cursor_after_advances_the_requested_from_block() -> None:
    transport = http.FakeTransport([http.response(body=http.page_two())])
    _client(transport).query(_request(from_block=100, to_block_exclusive=111, cursor_after=104))
    assert json.loads(transport.calls[0]["body"])["from_block"] == 104


def test_page_span_is_bounded_by_max_blocks_per_page() -> None:
    transport = http.FakeTransport([http.response(body=http.page_one())])
    _client(transport, bounds=_bounds(max_blocks_per_page=3)).query(_request())
    assert json.loads(transport.calls[0]["body"])["to_block"] == 103


def test_provider_status_codes_are_refused_with_stable_codes() -> None:
    for status, code in ((401, "AUTH_DENIED"), (403, "AUTH_DENIED"), (402, "PAYMENT_REQUIRED"),
                         (429, "RATE_LIMITED"), (302, "REDIRECT_REFUSED"), (500, "HTTP_STATUS")):
        client = _client(http.FakeTransport([http.response(status=status)]))
        with pytest.raises(HttpProviderError) as raised:
            client.query(_request())
        assert raised.value.code == code


def test_malformed_replies_are_refused() -> None:
    for body in ("not json", "[1,2,3]", ""):
        client = _client(http.FakeTransport([http.response(body=body)]))
        with pytest.raises(HttpProviderError) as raised:
            client.query(_request())
        assert raised.value.code == "MALFORMED_PROVIDER_RESPONSE"


def test_unsupported_content_encoding_is_refused() -> None:
    client = _client(http.FakeTransport([http.response(body=b"\x1f\x8b", headers={"Content-Encoding": "gzip"})]))
    with pytest.raises(HttpProviderError) as raised:
        client.query(_request())
    assert raised.value.code == "UNSUPPORTED_CONTENT_ENCODING"


def test_provider_error_is_one_attempt_with_no_retry() -> None:
    transport = http.FakeTransport([http.response(status=429), http.response(body=http.page_one())])
    client = _client(transport)
    with pytest.raises(HttpProviderError):
        client.query(_request())
    assert len(transport.calls) == 1
    assert client.accounting()["attempted_requests"] == 1


def test_cancel_before_send_never_calls_the_transport() -> None:
    transport = http.FakeTransport([http.response(body=http.page_one())])
    client = HttpEnvioQueryClient(endpoint=ENDPOINT, bearer_token=TOKEN, transport=transport,
                                  bounds=_bounds(), cancel=lambda: True)
    with pytest.raises(SourceCancelled):
        client.query(_request())
    assert transport.calls == []
    assert client.accounting()["attempted_requests"] == 0


def test_transport_failure_propagates_and_counts_unknown_liability() -> None:
    transport = http.FakeTransport([OSError("connection refused")])
    client = _client(transport)
    with pytest.raises(OSError):
        client.query(_request())
    assert client.accounting() == {"attempted_requests": 1, "completed_requests": 0, "unknown_liability": 1}

    for error in (SourceFailure("boom"), SourceTimeout("slow")):
        client = _client(http.FakeTransport([error]))
        with pytest.raises(type(error)):
            client.query(_request())
        assert client.accounting()["attempted_requests"] == 1


def test_the_bearer_token_never_leaks_into_an_error() -> None:
    client = HttpEnvioQueryClient(endpoint=ENDPOINT, bearer_token=TOKEN,
                                  transport=http.FakeTransport([http.response(status=401)]),
                                  bounds=_bounds(), clock=lambda: 0.0)
    with pytest.raises(HttpProviderError) as raised:
        client.query(_request())
    assert TOKEN not in str(raised.value)


def test_unsafe_endpoints_and_malformed_requests_are_refused() -> None:
    for endpoint in ("http://monad.hypersync.xyz", "https://user:pw@host/x", "https://monad.hypersync.xyz/query",
                     "https://monad.hypersync.xyz?token=SECRET", "wss://monad.hypersync.xyz", ""):
        with pytest.raises(ClientConfigError):
            HttpEnvioQueryClient(endpoint=endpoint, bearer_token=TOKEN,
                                 transport=http.FakeTransport([]), bounds=_bounds())
    for bad in (_request(provider="OTHER"), _request(topic0="0x00"), _request(from_block=111),
                _request(max_rows=0)):
        client = _client(http.FakeTransport([http.response(body=http.page_one())]))
        with pytest.raises(ClientConfigError):
            client.query(bad)
    client = _client(http.FakeTransport([http.response(body=http.page_one())]), bounds=_bounds(max_request_bytes=8))
    with pytest.raises(ClientConfigError):
        client.query(_request())


def test_loopback_collection_completes_through_the_accepted_consumer() -> None:
    with http.LoopbackServer(http.envio_router) as server:
        client = HttpEnvioQueryClient(endpoint=server.base_url, bearer_token=TOKEN,
                                      transport=StdlibHttpTransport(), bounds=_bounds())
        source = EnvioHypersyncSource(client, context=SourceContext(endpoint=server.base_url),
                                      clock=lambda: support.COLLECTED_AT)
        result = collect(support.profile(), source, support.SCAN, CollectionLimits(**support.limits()))
    assert result["status"] == "COMPLETE"
    assert result["page_count"] == 2
    assert result["row_count"] == 2
    assert client.accounting() == {"attempted_requests": 2, "completed_requests": 2, "unknown_liability": 0}


def test_byte_bound_at_the_real_client_boundary() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(body=b"x" * 5000)) as server:
        client = HttpEnvioQueryClient(endpoint=server.base_url, bearer_token=TOKEN,
                                      transport=StdlibHttpTransport(), bounds=_bounds(max_response_bytes=64))
        with pytest.raises(HttpProviderError) as raised:
            client.query(_request())
    assert raised.value.code == "OVERSIZED_RESPONSE"


def test_slow_reply_at_the_real_client_boundary_is_a_timeout() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(body=b"{}", delay_before_headers=0.5)) as server:
        client = HttpEnvioQueryClient(endpoint=server.base_url, bearer_token=TOKEN,
                                      transport=StdlibHttpTransport(), bounds=_bounds(connect_timeout_seconds=0.15))
        with pytest.raises(SourceTimeout):
            client.query(_request())


def test_header_stall_respects_the_whole_call_deadline() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(body=b"{}", delay_before_headers=0.3)) as server:
        client = HttpEnvioQueryClient(endpoint=server.base_url, bearer_token=TOKEN,
                                      transport=StdlibHttpTransport(),
                                      bounds=_bounds(deadline_seconds=0.05, connect_timeout_seconds=1.0))
        start = time.monotonic()
        with pytest.raises(SourceTimeout):
            client.query(_request())
        assert time.monotonic() - start < 0.25


def test_slow_stream_respects_the_whole_call_deadline() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(chunks=[b"a", b"b"], pause_between_chunks=0.3)) as server:
        client = HttpEnvioQueryClient(endpoint=server.base_url, bearer_token=TOKEN,
                                      transport=StdlibHttpTransport(),
                                      bounds=_bounds(deadline_seconds=0.05, connect_timeout_seconds=1.0))
        start = time.monotonic()
        with pytest.raises(SourceTimeout):
            client.query(_request())
        assert time.monotonic() - start < 0.4


def test_envio_endpoint_with_a_query_is_refused() -> None:
    with pytest.raises(ClientConfigError):
        HttpEnvioQueryClient(endpoint="https://monad.hypersync.xyz?token=SECRET", bearer_token=TOKEN,
                             transport=http.FakeTransport([]), bounds=_bounds())


def test_envio_targets_the_query_route() -> None:
    seen: dict[str, str] = {}

    def responder(method: str, path: str, _headers, _body: bytes) -> http.Reply:
        seen["method"], seen["path"] = method, path
        return http.Reply(body=json.dumps(http.page_one()).encode("utf-8"))

    with http.LoopbackServer(responder) as server:
        client = HttpEnvioQueryClient(endpoint=server.base_url, bearer_token=TOKEN,
                                      transport=StdlibHttpTransport(), bounds=_bounds())
        client.query(_request())
    assert seen["method"] == "POST"
    assert seen["path"] == "/query"


def test_content_encoding_value_never_leaks() -> None:
    client = _client(http.FakeTransport([http.response(body=b"x", headers={"Content-Encoding": TOKEN})]))
    with pytest.raises(HttpProviderError) as raised:
        client.query(_request())
    assert raised.value.code == "UNSUPPORTED_CONTENT_ENCODING"
    assert TOKEN not in str(raised.value)


def test_paced_body_drip_respects_the_whole_call_deadline() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(chunks=[b"a"] * 100, pause_between_chunks=0.01)) as server:
        client = HttpEnvioQueryClient(endpoint=server.base_url, bearer_token=TOKEN,
                                      transport=StdlibHttpTransport(),
                                      bounds=_bounds(deadline_seconds=0.05, connect_timeout_seconds=1.0))
        start = time.monotonic()
        with pytest.raises(SourceTimeout):
            client.query(_request())
        assert time.monotonic() - start < 0.4


def test_paced_drip_is_a_timeout_through_the_accepted_collector() -> None:
    raw = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    seen = {"requests": 0}

    def responder(*_args: object) -> http.Reply:
        seen["requests"] += 1
        return http.Reply(raw_http=raw, pause_between_chunks=0.01)

    with http.LoopbackServer(responder) as server:
        client = HttpEnvioQueryClient(endpoint=server.base_url, bearer_token=TOKEN,
                                      transport=StdlibHttpTransport(),
                                      bounds=_bounds(deadline_seconds=0.05, connect_timeout_seconds=1.0))
        source = EnvioHypersyncSource(client, context=SourceContext(endpoint=server.base_url),
                                      clock=lambda: support.COLLECTED_AT)
        result = collect(support.profile(), source, support.SCAN, CollectionLimits(**support.limits()))
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "TIMEOUT"
    assert client.accounting() == {"attempted_requests": 1, "completed_requests": 0, "unknown_liability": 1}
    assert seen["requests"] == 1  # one physical attempt, no hidden retry
