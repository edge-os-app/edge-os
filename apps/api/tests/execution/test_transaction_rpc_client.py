"""Literal synthetic RPC responses through the caller interface."""

import json
from edge_os_api.execution.transaction_rpc_client import TransactionRpcClient
from edge_os_api.research_history.http_clients.http_transport import HttpResponse
import pytest
import socket
from edge_os_api.execution.original_transaction import ReplyLost, RpcError




def test_observer_freezes_one_rpc_request_and_returns_quantity():
    calls = []
    class Http:
        def request(self, **request):
            calls.append(request)
            return HttpResponse(200, {}, b'{"jsonrpc":"2.0","id":1,"result":"0x8f"}')
    client = TransactionRpcClient(role="observer", destination_id="observer-a", endpoint="https://observer.invalid/rpc",
        plan=[("eth_chainId", [])], http=Http(), deadline_monotonic=20, connect_timeout_seconds=2,
        max_request_bytes=4096, max_response_bytes=4096, monotonic=lambda: 10)
    assert calls == []
    assert client.call("eth_chainId", []) == "0x8f"
    assert len(calls) == 1
    assert calls[0]["body"] == b'{"id":1,"jsonrpc":"2.0","method":"eth_chainId","params":[]}'
    assert calls[0]["url"] == "https://observer.invalid/rpc"
    assert calls[0]["deadline"] == 20



WALLET = "0x" + "1" * 40
TX = "0x" + "ab" * 100
HASH = "0x" + "2" * 64


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


class RecordingHttp:
    def __init__(self, response=None, failure=None, hook=None):
        self.response, self.failure, self.hook, self.calls = response, failure, hook, []

    def request(self, **request):
        self.calls.append(request)
        if self.hook:
            self.hook()
        if self.failure:
            raise self.failure
        return self.response


def rpc(http, *, role="observer", plan=None, **kwargs):
    return TransactionRpcClient(role=role, destination_id="destination-a", endpoint="https://rpc.invalid/credential-canary",
        plan=plan or [("eth_chainId", [])], http=http, deadline_monotonic=20, connect_timeout_seconds=2,
        max_request_bytes=4096, max_response_bytes=4096, monotonic=kwargs.pop("monotonic", lambda: 10), **kwargs)


@pytest.mark.parametrize("raw", [
    b'{"jsonrpc":"2.0","id":true,"result":"0x8f"}',
    b'{"jsonrpc":"2.0","id":1.0,"result":"0x8f"}',
    b'{"jsonrpc":"1.0","id":1,"result":"0x8f"}',
    b'{"jsonrpc":"2.0","id":2,"result":"0x8f"}',
    b'{"jsonrpc":"2.0","id":1,"result":"0x8f","error":{}}',
    b'{"jsonrpc":"2.0","id":1,"id":1,"result":"0x8f"}',
    b'{"jsonrpc":"2.0","id":1,"result":"0x08f"}',
    b'{"jsonrpc":"2.0","id":1,"result":143}',
    b'{"jsonrpc":"2.0","id":1,"result":true}',
    b'{"jsonrpc":"2.0","id":1,"result":"0x8F"}', b'[]', b'null', b'not-json',
])
def test_unrecognized_reply_is_consumed_without_retry(raw):
    http = RecordingHttp(HttpResponse(200, {}, raw))
    client = rpc(http)
    with pytest.raises(RpcError):
        client.call("eth_chainId", [])
    with pytest.raises(RpcError):
        client.call("eth_chainId", [])
    assert len(http.calls) == 1


@pytest.mark.parametrize("status", [301, 302, 307, 402, 403, 429, 500, 503])
def test_broadcast_status_never_proves_unsent_or_resends(status):
    http = RecordingHttp(HttpResponse(status, {"location": "credential-canary"}, b'credential-canary'))
    client = rpc(http, role="broadcast", plan=[("eth_sendRawTransaction", [TX])])
    with pytest.raises(RpcError) as error:
        client.call("eth_sendRawTransaction", [TX])
    assert error.value.__context__ is None and error.value.__cause__ is None
    assert "credential-canary" not in str(error.value)
    with pytest.raises(RpcError):
        client.call("eth_sendRawTransaction", [TX])
    assert len(http.calls) == 1


@pytest.mark.parametrize("failure", [TimeoutError("secret-canary"), OSError(TX), RuntimeError("credential-canary")])
def test_lost_response_has_no_external_exception_context(failure):
    http = RecordingHttp(failure=failure)
    client = rpc(http, role="broadcast", plan=[("eth_sendRawTransaction", [TX])])
    with pytest.raises(ReplyLost) as error:
        client.call("eth_sendRawTransaction", [TX])
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert "canary" not in repr(error.value) and TX not in repr(error.value)
    assert len(http.calls) == 1


@pytest.mark.parametrize("role,plan", [
    ("observer", [("eth_sendRawTransaction", [TX])]),
    ("observer", [("personal_sign", [])]),
    ("broadcast", [("eth_chainId", [])]),
    ("broadcast", [("eth_sendRawTransaction", [TX]), ("eth_sendRawTransaction", [TX])]),
    ("observer", [("eth_call", [{"to": WALLET, "data": "0x095ea7b3"}, "finalized"])]),
])
def test_role_or_operation_refused_before_transport(role, plan):
    http = RecordingHttp()
    with pytest.raises(ValueError):
        rpc(http, role=role, plan=plan)
    assert http.calls == []


def test_nested_plan_mutation_and_wrong_call_send_nothing():
    params = [WALLET, "pending"]
    http = RecordingHttp(HttpResponse(200, {}, b'{"jsonrpc":"2.0","id":1,"result":"0x0"}'))
    client = rpc(http, role="broadcast", plan=[("eth_getTransactionCount", params)])
    params[0] = "0x" + "3" * 40
    with pytest.raises(RpcError):
        client.call("eth_getTransactionCount", params)
    assert http.calls == []
    assert client.call("eth_getTransactionCount", [WALLET, "pending"]) == "0x0"
    assert "credential-canary" not in repr(client)


def test_cancel_before_send_and_deadline_after_response():
    http = RecordingHttp()
    with pytest.raises(RpcError):
        rpc(http, cancel=lambda: True).call("eth_chainId", [])
    assert http.calls == []
    times = iter([10, 20])
    http = RecordingHttp(HttpResponse(200, {}, b'{"jsonrpc":"2.0","id":1,"result":"0x8f"}'))
    with pytest.raises(ReplyLost):
        rpc(http, monotonic=lambda: next(times)).call("eth_chainId", [])
    assert len(http.calls) == 1


@pytest.mark.parametrize("result", [
    {"number": "0x1", "timestamp": "0x1", "hash": HASH, "secret": "credential-canary"},
    {"number": "0x1", "timestamp": "0x1", "hash": "credential-canary"},
    {"number": "0x01", "timestamp": "0x1", "hash": HASH},
])
def test_block_schema_cannot_return_unknown_or_malformed_fields(result):
    http = RecordingHttp(HttpResponse(200, {}, json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()))
    with pytest.raises(RpcError):
        rpc(http, plan=[("eth_getBlockByNumber", ["finalized", False])]).call("eth_getBlockByNumber", ["finalized", False])


def test_truncated_framing_is_not_a_valid_rpc_reply():
    http = RecordingHttp(HttpResponse(200, {"content-length": "10000"}, b'{"jsonrpc":"2.0","id":1,"result":"0x8f"}'))
    with pytest.raises(RpcError):
        rpc(http).call("eth_chainId", [])


def test_broadcast_reply_hash_must_name_the_frozen_raw_bytes():
    http = RecordingHttp(HttpResponse(200, {}, json.dumps({"jsonrpc": "2.0", "id": 1, "result": HASH}).encode()))
    with pytest.raises(RpcError):
        rpc(http, role="broadcast", plan=[("eth_sendRawTransaction", [TX])]).call("eth_sendRawTransaction", [TX])
    assert len(http.calls) == 1


def test_saved_original_is_loaded_only_after_nonce_and_consumed_on_lost_send():
    saved, reads = {}, []
    def original_bytes():
        reads.append("saved-original")
        return saved["signed_bytes"]
    http = RecordingHttp(HttpResponse(200, {}, b'{"jsonrpc":"2.0","id":1,"result":"0x0"}'))
    client = rpc(http, role="broadcast", plan=[("eth_getTransactionCount", [WALLET, "pending"]),
                                            ("eth_sendRawTransaction", None)], original_bytes=original_bytes)
    assert reads == []
    assert client.call("eth_getTransactionCount", [WALLET, "pending"]) == "0x0"
    saved["signed_bytes"] = TX
    http.failure = TimeoutError("signed-canary")
    with pytest.raises(ReplyLost):
        client.call("eth_sendRawTransaction", [TX])
    saved["signed_bytes"] = "0xdeadbeef"
    with pytest.raises(RpcError):
        client.call("eth_sendRawTransaction", [TX])
    assert reads == ["saved-original"] and len(http.calls) == 2
    assert json.loads(http.calls[1]["body"])["params"] == [TX]


def test_concurrent_broadcast_claims_still_send_exactly_once():
    import threading
    from eth_utils import keccak
    expected_hash = "0x" + keccak(bytes.fromhex(TX[2:])).hex()
    http = RecordingHttp(HttpResponse(200, {}, json.dumps({"jsonrpc": "2.0", "id": 1, "result": expected_hash}).encode()))
    client = rpc(http, role="broadcast", plan=[("eth_sendRawTransaction", [TX])])
    barrier, outcomes = threading.Barrier(2), []
    def call():
        barrier.wait(timeout=1)
        try:
            outcomes.append(client.call("eth_sendRawTransaction", [TX]))
        except RpcError:
            outcomes.append("REFUSED")
    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=1)
        assert not thread.is_alive()
    assert sorted(outcomes) == sorted([expected_hash, "REFUSED"])
    assert len(http.calls) == 1
