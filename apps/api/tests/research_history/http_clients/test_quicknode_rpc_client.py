"""Tests for the concrete injected QuickNode JSON-RPC client.

Most cases drive the client over the deterministic ``FakeTransport``; the accepted
corroboration consumers are proven end-to-end over the real transport and an owned
loopback server. No external host, credential or provider is touched.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

import _http_support as http
import _support as support

from edge_os_api.research_history import QuickNodeRpcClient, corroborate_records, read_chain_id
from edge_os_api.research_history.http_clients import (
    ClientBounds,
    ClientConfigError,
    HttpProviderError,
    HttpQuickNodeRpcClient,
    READ_ONLY_METHODS,
    StdlibHttpTransport,
    safe_endpoint,
)
from edge_os_api.research_history.provider_transport import SourceCancelled

ENDPOINT = "https://example.monad-mainnet.quiknode.pro/SECRET-KEY/"
KEY = "SECRET-KEY"


def _bounds(**overrides):
    values = {"deadline_seconds": 5.0, "connect_timeout_seconds": 2.0, "max_response_bytes": 4096,
              "max_request_bytes": 4096, "max_blocks_per_page": 1000}
    values.update(overrides)
    return ClientBounds(**values)


def _client(transport, **overrides):
    kwargs = {"endpoint": overrides.pop("endpoint", ENDPOINT), "transport": transport,
              "bounds": overrides.pop("bounds", _bounds()),
              "clock": overrides.pop("clock", lambda: 100.0)}
    if "allowed_methods" in overrides:
        kwargs["allowed_methods"] = overrides.pop("allowed_methods")
    if "cancel" in overrides:
        kwargs["cancel"] = overrides.pop("cancel")
    return HttpQuickNodeRpcClient(**kwargs)


def _envelope(call_id: int, *, result: object = None, error: object = None) -> dict:
    frame = {"jsonrpc": "2.0", "id": call_id}
    if result is not None or error is None:
        frame["result"] = result
    if error is not None:
        frame["error"] = error
    return frame


def _receipt_for(event: Mapping[str, object], *, removed: bool = False) -> dict:
    return {
        "transactionHash": event["transaction_hash"],
        "transactionIndex": hex(event["transaction_index"]),
        "blockNumber": hex(event["block_number"]),
        "blockHash": event["block_hash"],
        "logs": [{
            "address": event["address"],
            "topics": [event["topic0"], event["topic1"], event["topic2"]],
            "data": event["data"],
            "logIndex": hex(event["log_index"]),
            "transactionHash": event["transaction_hash"],
            "transactionIndex": hex(event["transaction_index"]),
            "blockNumber": hex(event["block_number"]),
            "blockHash": event["block_hash"],
            "removed": removed,
        }],
    }


def _record(event: Mapping[str, object]) -> dict:
    return {key: event[key] for key in ("address", "topic0", "topic1", "topic2", "data", "block_number",
                                        "block_hash", "transaction_hash", "transaction_index", "log_index")}


def _quicknode_router(_method: str, _path: str, _headers: Mapping[str, str], body: bytes) -> http.Reply:
    request = json.loads(body.decode("utf-8"))
    raw_method, call_id = request["method"], request["id"]
    if raw_method == "eth_chainId":
        result = "0x8f"
    elif raw_method == "eth_getTransactionReceipt":
        by_hash = {support.EVENT_QUOTE_IN["transaction_hash"]: _receipt_for(support.EVENT_QUOTE_IN),
                   support.EVENT_BASE_IN["transaction_hash"]: _receipt_for(support.EVENT_BASE_IN)}
        result = by_hash.get(request["params"][0])
    else:
        return http.Reply(body=json.dumps({"jsonrpc": "2.0", "id": call_id,
                                           "error": {"code": -32601, "message": "method not found"}}).encode())
    return http.Reply(body=json.dumps({"jsonrpc": "2.0", "id": call_id, "result": result}).encode())


def test_client_satisfies_the_accepted_protocol() -> None:
    assert isinstance(_client(http.FakeTransport([])), QuickNodeRpcClient)


def test_construction_performs_no_io_and_requires_a_transport() -> None:
    transport = http.FakeTransport([])
    _client(transport)
    assert transport.calls == []
    with pytest.raises(TypeError):
        HttpQuickNodeRpcClient(endpoint=ENDPOINT, bounds=_bounds())  # type: ignore[call-arg]


def test_call_returns_the_result_and_sends_a_jsonrpc_envelope() -> None:
    transport = http.FakeTransport([http.response(body=_envelope(1, result="0x8f"))])
    client = _client(transport)
    assert client.call("eth_chainId", []) == "0x8f"
    sent = json.loads(transport.calls[0]["body"])
    assert sent == {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}
    assert client.accounting() == {"attempted_requests": 1, "completed_requests": 1, "unknown_liability": 0}
    assert len(transport.calls) == 1


def test_ids_increment_per_call() -> None:
    transport = http.FakeTransport([http.response(body=_envelope(1, result="0x1")),
                                    http.response(body=_envelope(2, result="0x2"))])
    client = _client(transport)
    assert client.call("eth_blockNumber", []) == "0x1"
    assert client.call("eth_blockNumber", []) == "0x2"


def test_malformed_envelopes_are_refused() -> None:
    frames = [
        {"jsonrpc": "2.0", "id": 2, "result": "0x1"},          # wrong id
        {"jsonrpc": "2.0", "id": True, "result": "0x1"},       # boolean id equals 1 in Python
        {"jsonrpc": "2.0", "id": "1", "result": "0x1"},        # string id
        {"id": 1, "result": "0x1"},                            # missing jsonrpc
        {"jsonrpc": "2.0", "id": 1},                           # neither result nor error
        {"jsonrpc": "2.0", "id": 1, "result": "0x1", "error": {"code": -1, "message": "x"}},  # both
        [],
    ]
    for frame in frames:
        with pytest.raises(HttpProviderError) as raised:
            _client(http.FakeTransport([http.response(body=frame)])).call("eth_chainId", [])
        assert raised.value.code == "MALFORMED_PROVIDER_RESPONSE"


def test_empty_and_encoded_replies_are_refused_at_the_client_boundary() -> None:
    for body, headers, code in ((b"", None, "MALFORMED_PROVIDER_RESPONSE"),
                                (b"\x1f\x8b", {"Content-Encoding": "gzip"}, "UNSUPPORTED_CONTENT_ENCODING")):
        with pytest.raises(HttpProviderError) as raised:
            _client(http.FakeTransport([http.response(body=body, headers=headers)])).call("eth_chainId", [])
        assert raised.value.code == code


def test_provider_error_becomes_a_refused_reply() -> None:
    frame = _envelope(1, error={"code": -32000, "message": "boom"})
    with pytest.raises(HttpProviderError) as raised:
        _client(http.FakeTransport([http.response(body=frame)])).call("eth_chainId", [])
    assert raised.value.code == "PROVIDER_ERROR"
    assert "-32000" in str(raised.value)
    assert "boom" not in str(raised.value)


def test_provider_error_never_copies_provider_text() -> None:
    # A provider can put anything, including an echoed key, in code or message.
    frame = _envelope(1, error={"code": KEY, "message": KEY})
    with pytest.raises(HttpProviderError) as raised:
        _client(http.FakeTransport([http.response(body=frame)])).call("eth_chainId", [])
    assert raised.value.code == "PROVIDER_ERROR"
    assert KEY not in str(raised.value)

    frame = _envelope(1, error={"code": -32000, "message": "boom-" + KEY})
    with pytest.raises(HttpProviderError) as raised:
        _client(http.FakeTransport([http.response(body=frame)])).call("eth_chainId", [])
    assert KEY not in str(raised.value)
    assert "boom" not in str(raised.value)


def test_only_read_only_methods_are_allowed() -> None:
    client = _client(http.FakeTransport([]))
    for method in ("eth_sendRawTransaction", "personal_sign", "eth_accounts", "debug_traceCall"):
        with pytest.raises(ClientConfigError):
            client.call(method, [])
    with pytest.raises(ClientConfigError):
        _client(http.FakeTransport([]), allowed_methods={"eth_chainId", "eth_sendTransaction"})
    narrowed = _client(http.FakeTransport([http.response(body=_envelope(1, result="0x8f"))]),
                       allowed_methods={"eth_chainId"})
    assert narrowed.allowed_methods == frozenset({"eth_chainId"})
    assert narrowed.call("eth_chainId", []) == "0x8f"
    with pytest.raises(ClientConfigError):
        narrowed.call("eth_getCode", [support.POOL])


def test_params_must_be_a_json_array_and_requests_respect_the_byte_bound() -> None:
    client = _client(http.FakeTransport([http.response(body=_envelope(1, result="0x1"))]))
    with pytest.raises(ClientConfigError):
        client.call("eth_chainId", "not a list")  # type: ignore[arg-type]
    small = _client(http.FakeTransport([http.response(body=_envelope(1, result="0x1"))]),
                    bounds=_bounds(max_request_bytes=8))
    with pytest.raises(ClientConfigError):
        small.call("eth_chainId", [])


def test_provider_status_codes_are_refused() -> None:
    for status, code in ((401, "AUTH_DENIED"), (429, "RATE_LIMITED"), (402, "PAYMENT_REQUIRED"),
                         (307, "REDIRECT_REFUSED"), (500, "HTTP_STATUS")):
        with pytest.raises(HttpProviderError) as raised:
            _client(http.FakeTransport([http.response(status=status)])).call("eth_chainId", [])
        assert raised.value.code == code


def test_cancel_before_send_never_calls_the_transport() -> None:
    transport = http.FakeTransport([http.response(body=_envelope(1, result="0x1"))])
    client = HttpQuickNodeRpcClient(endpoint=ENDPOINT, transport=transport, bounds=_bounds(),
                                    cancel=lambda: True)
    with pytest.raises(SourceCancelled):
        client.call("eth_chainId", [])
    assert transport.calls == []
    assert client.accounting()["attempted_requests"] == 0


def test_the_path_key_never_leaks_into_a_safe_endpoint_or_error() -> None:
    assert KEY not in safe_endpoint(ENDPOINT)
    assert safe_endpoint(ENDPOINT) == "https://example.monad-mainnet.quiknode.pro"
    with pytest.raises(HttpProviderError) as raised:
        _client(http.FakeTransport([http.response(status=401)])).call("eth_chainId", [])
    assert KEY not in str(raised.value)


def test_unsafe_endpoints_are_refused() -> None:
    for endpoint in ("http://example.monad-mainnet.quiknode.pro/KEY/", "https://user:pw@host/KEY/",
                     "ftp://host/KEY/", ""):
        with pytest.raises(ClientConfigError):
            HttpQuickNodeRpcClient(endpoint=endpoint, transport=http.FakeTransport([]), bounds=_bounds())


def test_loopback_corroboration_completes_through_the_accepted_consumer() -> None:
    with http.LoopbackServer(_quicknode_router) as server:
        client = HttpQuickNodeRpcClient(endpoint=server.base_url + "/KEY/", transport=StdlibHttpTransport(),
                                        bounds=_bounds())
        chain = read_chain_id(client)
        records = [_record(support.EVENT_QUOTE_IN), _record(support.EVENT_BASE_IN)]
        result = corroborate_records(client, records, sample_size=8, chain_id=chain["chain_id"])
    assert chain["chain_id"] == 143 and chain["network"] == "MONAD"
    assert result["class"] == "COMPLETE" and result["mismatches"] == 0
    assert client.accounting()["attempted_requests"] == 3
