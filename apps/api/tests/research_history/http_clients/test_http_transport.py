"""Owned-loopback and fake-connection tests for the bounded HTTP transport.

These exercise the shipped ``StdlibHttpTransport`` over a real ``127.0.0.1`` socket
for the socket-bound cases (timeout, oversized body, redirect) and over a fake
connection for the deterministic clock/cancellation cases. No external host,
credential or provider is touched.
"""

from __future__ import annotations

import time

import pytest

import _http_support as http

from edge_os_api.research_history.http_clients import (
    ClientConfigError,
    HttpProviderError,
    StdlibHttpTransport,
)
from edge_os_api.research_history.provider_transport import SourceCancelled, SourceTimeout


def _request(transport: StdlibHttpTransport, url: str, *, deadline: float | None = None,
             timeout: float = 2.0, max_response_bytes: int = 4096, cancel=None):
    if deadline is None:
        deadline = time.monotonic() + 30.0
    return transport.request(method="POST", url=url, headers={"accept": "application/json"},
                             body=b"{}", timeout=timeout, deadline=deadline,
                             max_response_bytes=max_response_bytes, cancel=cancel)


def test_transport_returns_a_reply_over_loopback() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(body=b'{"next_block":104}')) as server:
        transport = StdlibHttpTransport()
        response = _request(transport, server.base_url + "/query")
    assert response.status == 200
    assert response.body == b'{"next_block":104}'


def test_transport_refuses_an_oversized_reply() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(body=b"x" * 5000)) as server:
        transport = StdlibHttpTransport()
        with pytest.raises(HttpProviderError) as raised:
            _request(transport, server.base_url + "/query", max_response_bytes=100)
    assert raised.value.code == "OVERSIZED_RESPONSE"


def test_transport_does_not_follow_a_redirect() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(status=302, headers={"Location": "http://example.test/"})) as server:
        transport = StdlibHttpTransport()
        response = _request(transport, server.base_url + "/query")
    assert response.status == 302


def test_transport_times_out_on_a_slow_reply() -> None:
    with http.LoopbackServer(lambda *_: http.Reply(body=b"{}", delay_before_headers=0.5)) as server:
        transport = StdlibHttpTransport()
        with pytest.raises(SourceTimeout):
            _request(transport, server.base_url + "/query", timeout=0.15)


def test_transport_cancels_before_opening_a_socket() -> None:
    called = {"connect": False}

    def connect(*_args):
        called["connect"] = True
        raise AssertionError("connect must not run when already cancelled")

    transport = StdlibHttpTransport(connect=connect)
    with pytest.raises(SourceCancelled):
        _request(transport, "http://127.0.0.1:1/query", cancel=lambda: True)
    assert called["connect"] is False


def test_transport_cancels_during_a_stream() -> None:
    state = {"cancel": False}

    def hook(_response: http.FakeResponse) -> None:
        state["cancel"] = True

    connection = http.FakeConnection(http.FakeResponse(body=b"x" * 10, read_hook=hook))
    transport = StdlibHttpTransport(connect=lambda *_args: connection, clock=lambda: 0.0)
    with pytest.raises(SourceCancelled):
        _request(transport, "http://127.0.0.1:1/query", cancel=lambda: state["cancel"])
    assert connection.closed == 1


def test_transport_enforces_the_deadline_between_reads() -> None:
    state = {"now": 0.0}

    def hook(_response: http.FakeResponse) -> None:
        state["now"] = 2.0

    connection = http.FakeConnection(http.FakeResponse(body=b"x" * 10, read_hook=hook))
    transport = StdlibHttpTransport(connect=lambda *_args: connection, clock=lambda: state["now"])
    with pytest.raises(SourceTimeout):
        _request(transport, "http://127.0.0.1:1/query", deadline=1.0)


def test_transport_closes_the_connection_on_success_and_failure() -> None:
    good = http.FakeConnection(http.FakeResponse(body=b"ok"))
    transport = StdlibHttpTransport(connect=lambda *_args: good, clock=lambda: 0.0)
    assert _request(transport, "http://127.0.0.1:1/query").body == b"ok"
    assert good.closed == 1

    big = http.FakeConnection(http.FakeResponse(body=b"x" * 50))
    transport = StdlibHttpTransport(connect=lambda *_args: big, clock=lambda: 0.0)
    with pytest.raises(HttpProviderError):
        _request(transport, "http://127.0.0.1:1/query", max_response_bytes=1)
    assert big.closed == 1


def test_transport_refuses_an_unsafe_url_and_scheme() -> None:
    transport = StdlibHttpTransport()
    with pytest.raises(ClientConfigError):
        _request(transport, "ftp://example.test/query")
