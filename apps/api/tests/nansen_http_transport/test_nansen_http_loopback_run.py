"""The adapter over the REAL StdlibHttpTransport and an owned 127.0.0.1 listener.

The production origin stays fixed; only the injected connector points the socket at
the owned loopback port. The listener records each request so the tests can prove
the literal path, headers and body it received, and that a failure made one attempt
and closed its socket. Synthetic key and data only.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal

import pytest

import nansen_http_support as support
from edge_os_api.nansen_research import (
    NansenAuthError,
    NansenCancelled,
    NansenClient,
    NansenContractError,
    NansenTimeout,
    run_research,
)
from edge_os_api.research_history.http_clients.http_transport import StdlibHttpTransport

Reply = support.http_support.Reply
KEY = support.SYNTHETIC_KEY

HOLDER_BYTES = (
    b'{"aggregate_by_entity":false,"chain":"monad","label_type":"all_holders",'
    b'"order_by":[{"direction":"DESC","field":"token_amount"}],"pagination":{"page":1,"per_page":100},'
    b'"premium_labels":false,"token_address":"0xd8e004acba279417c04c0633cb5a21ceca207777"}'
)
FLOW_BYTES = (
    b'{"chain":"monad","date":{"from":"2026-10-06T09:44:14Z","to":"2026-10-07T09:44:14Z"},'
    b'"label":"top_100_holders","order_by":[{"direction":"ASC","field":"date"}],'
    b'"pagination":{"page":1,"per_page":100},"token_address":"0xd8e004acba279417c04c0633cb5a21ceca207777"}'
)


class Listener:
    """Records every request and answers from a script keyed by path."""

    def __init__(self, replies: dict[str, Reply]) -> None:
        self._replies = replies
        self.received: list[tuple[str, str, dict[str, str], bytes]] = []

    def __call__(self, method: str, path: str, headers: dict[str, str], body: bytes) -> Reply:
        self.received.append((method, path, {name.lower(): value for name, value in headers.items()}, body))
        return self._replies[path]


def _stdlib_adapter(server: support.http_support.LoopbackServer, **overrides):
    connector = support.LoopbackConnector(server)
    adapter = support.adapter(StdlibHttpTransport(connect=connector), **overrides)
    return adapter, connector


def _assert_closed(connector: support.LoopbackConnector, count: int) -> None:
    assert len(connector.sockets) == count
    assert all(sock.fileno() == -1 for sock in connector.sockets)
    assert connector.targets == [("https", "api.nansen.ai", None)] * count


def _json(payload) -> bytes:
    return json.dumps(payload).encode()


def test_a_complete_run_reaches_the_listener_with_the_literal_wire_request() -> None:
    holders = support.nansen.holder_payload([support.nansen.holder_row("0xaaa", token_amount=1000)])
    flows = support.nansen.flow_payload([support.nansen.flow_bucket("2026-10-06T09:00:00Z",
                                                                    bucket_end="2026-10-06T10:00:00Z")])
    listener = Listener({
        "/api/v1/tgm/holders": Reply(body=_json(holders), headers={"x-request-id": "req-h", "x-nansen-credits-used": "5"}),
        "/api/v1/tgm/flows": Reply(body=_json(flows), headers={"x-request-id": "req-f", "x-nansen-credits-used": "1"}),
    })
    with support.http_support.LoopbackServer(listener) as server:
        adapter, connector = _stdlib_adapter(server)
        run = run_research(support.nansen.request(), adapter, clock=lambda: support.nansen.COLLECTED_AT)

    assert [(method, path, body) for method, path, _headers, body in listener.received] == [
        ("POST", "/api/v1/tgm/holders", HOLDER_BYTES),
        ("POST", "/api/v1/tgm/flows", FLOW_BYTES),
    ]
    for _method, _path, headers, body in listener.received:
        assert headers["apikey"] == KEY
        assert headers["content-type"] == "application/json"
        assert headers["accept"] == "application/json"
        assert headers["content-length"] == str(len(body))
        assert "authorization" not in headers and "x-payment" not in headers
    evidence = run.evidence
    assert evidence.stop_reason is None
    assert (evidence.attempts, evidence.pages, evidence.reserved_credits) == (2, 2, "6")
    assert [source.request_id for source in evidence.sources] == ["req-h", "req-f"]
    assert evidence.holder.rows[0].address == "0xaaa"
    _assert_closed(connector, 2)


def test_an_http_error_over_the_socket_is_mapped_once_and_the_run_stops() -> None:
    listener = Listener({"/api/v1/tgm/holders": Reply(status=401, body=b'{"code": "unauthenticated"}',
                                                      headers={"x-request-id": "req-401"})})
    with support.http_support.LoopbackServer(listener) as server:
        adapter, connector = _stdlib_adapter(server)
        run = run_research(support.nansen.request(), adapter, clock=lambda: support.nansen.COLLECTED_AT)
    assert run.evidence.stop_reason == "UNAUTHENTICATED"
    assert [(source.failure, source.status, source.request_id) for source in run.evidence.sources] == [
        ("UNAUTHENTICATED", 401, "req-401")]
    assert len(listener.received) == 1
    _assert_closed(connector, 1)


def test_a_redirect_over_the_socket_is_refused_and_not_followed() -> None:
    listener = Listener({"/api/v1/tgm/holders": Reply(status=302, headers={"location": "/api/v1/tgm/flows"})})
    with support.http_support.LoopbackServer(listener) as server:
        adapter, connector = _stdlib_adapter(server)
        with pytest.raises(NansenContractError) as caught:
            NansenClient(adapter, support.nansen.limits()).call("holders", support.nansen.holder_body())
    assert (caught.value.code, caught.value.status) == ("REDIRECT_REFUSED", 302)
    assert [path for _method, path, _headers, _body in listener.received] == ["/api/v1/tgm/holders"]
    _assert_closed(connector, 1)


def test_an_oversized_stream_is_stopped_while_reading() -> None:
    listener = Listener({"/api/v1/tgm/holders": Reply(chunks=[b"a" * 70_000, b"b" * 70_000])})
    with support.http_support.LoopbackServer(listener) as server:
        adapter, connector = _stdlib_adapter(server, max_response_bytes=100_000)
        client = NansenClient(adapter, support.nansen.limits())
        with pytest.raises(NansenContractError) as caught:
            client.call("holders", support.nansen.holder_body())
    assert caught.value.code == "OVERSIZED_RESPONSE"
    assert caught.value.response_sha256 is None
    assert client.attempts == 1 and client.bytes_read == 0
    assert len(listener.received) == 1
    _assert_closed(connector, 1)


def test_malformed_framing_is_a_contract_failure() -> None:
    listener = Listener({"/api/v1/tgm/holders": Reply(raw_http=b"NOT-HTTP garbage\r\n\r\n")})
    with support.http_support.LoopbackServer(listener) as server:
        adapter, connector = _stdlib_adapter(server)
        with pytest.raises(NansenContractError) as caught:
            adapter.request("holders", "/api/v1/tgm/holders", support.nansen.holder_body())
    assert caught.value.code == "MALFORMED_PROVIDER_RESPONSE"
    _assert_closed(connector, 1)


def test_a_stalled_reply_is_stopped_at_the_absolute_deadline() -> None:
    listener = Listener({"/api/v1/tgm/holders": Reply(body=b"{}", delay_before_headers=2.0)})
    with support.http_support.LoopbackServer(listener) as server:
        started = time.monotonic()
        adapter, connector = _stdlib_adapter(server, deadline_monotonic=started + 0.3, connect_timeout_seconds=5.0)
        client = NansenClient(adapter, support.nansen.limits())
        with pytest.raises(NansenTimeout) as caught:
            client.call("holders", support.nansen.holder_body())
        elapsed = time.monotonic() - started
        # The next request under the same job deadline makes no attempt.
        with pytest.raises(NansenTimeout) as again:
            adapter.request("flows", "/api/v1/tgm/flows", support.nansen.flow_body())
    assert caught.value.code == "TIMEOUT"
    assert again.value.code == "DEADLINE"
    assert 0.25 <= elapsed < 1.5
    assert (caught.value.status, caught.value.request_id) == (None, None)
    assert client.reserved_credits == Decimal("5")
    assert len(listener.received) == 1
    _assert_closed(connector, 1)


def test_an_in_flight_cancellation_stops_a_paced_body() -> None:
    listener = Listener({"/api/v1/tgm/holders": Reply(chunks=[b"{", b'"data"', b":[]", b"}"],
                                                      pause_between_chunks=0.2)})
    flag = {"cancel": False}
    with support.http_support.LoopbackServer(listener) as server:
        # The flag turns on once the socket is open, so only the in-flight checks can see it.
        connector = support.LoopbackConnector(server, on_connect=lambda: flag.update(cancel=True))
        adapter = support.adapter(StdlibHttpTransport(connect=connector), cancel=lambda: flag["cancel"])
        client = NansenClient(adapter, support.nansen.limits())
        started = time.monotonic()
        with pytest.raises(NansenCancelled) as caught:
            client.call("holders", support.nansen.holder_body())
        elapsed = time.monotonic() - started
    assert caught.value.code == "CANCELLED"
    assert elapsed < 0.6
    assert len(listener.received) == 1
    _assert_closed(connector, 1)


def test_a_too_deep_flows_reply_over_the_socket_keeps_the_holder_result() -> None:
    holders = support.nansen.holder_payload([support.nansen.holder_row("0xaaa")])
    # 120,021 bytes, inside the 150,000-byte adapter cap and the client's 200,000-byte cap.
    too_deep = b'{"data":[],"extra":' + b"[" * 60_000 + b"0" + b"]" * 60_000 + b"}"
    listener = Listener({
        "/api/v1/tgm/holders": Reply(body=_json(holders)),
        "/api/v1/tgm/flows": Reply(body=too_deep),
    })
    with support.http_support.LoopbackServer(listener) as server:
        adapter, connector = _stdlib_adapter(server, max_response_bytes=150_000)
        run = run_research(support.nansen.request(), adapter, clock=lambda: support.nansen.COLLECTED_AT)
    evidence = run.evidence
    assert evidence.holder is not None and evidence.flows is None
    assert evidence.stop_reason == "MALFORMED_PROVIDER_RESPONSE"
    assert (evidence.attempts, evidence.pages, evidence.reserved_credits) == (2, 1, "6")
    assert [source.failure for source in evidence.sources] == [None, "MALFORMED_PROVIDER_RESPONSE"]
    assert evidence.sources[1].response_sha256 is None
    assert [path for _method, path, _headers, _body in listener.received] == [
        "/api/v1/tgm/holders", "/api/v1/tgm/flows"]
    _assert_closed(connector, 2)
