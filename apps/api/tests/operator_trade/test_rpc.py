"""The RPC boundary: allowlist, exact replies, redacted endpoint and a single raw send."""

from __future__ import annotations

import pytest

from edge_os_api.research_history.http_clients.http_transport import HttpResponse

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.rpc import OperatorRpc

from ._support import ENTRYPOINT, FakeTransport, signed_for

ENDPOINT = "https://rpc.invalid/key-secret-path"


class ReplyTransport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requests = 0

    def request(self, *, method: str, url: str, headers: dict[str, str], body: bytes,
                timeout: float, deadline: float, max_response_bytes: int,
                cancel=None) -> HttpResponse:
        self.requests += 1
        return HttpResponse(status=200, headers={"content-type": "application/json"}, body=self.payload)


def _rpc(payload: bytes) -> OperatorRpc:
    return OperatorRpc(transport=ReplyTransport(payload), endpoint=ENDPOINT)


def test_repr_redacts_the_endpoint() -> None:
    assert "key-secret-path" not in repr(_rpc(b"{}"))


def test_call_cannot_send_a_raw_transaction() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b"{}").call("eth_sendRawTransaction", ["0x01"])
    assert caught.value.code == "RPC_METHOD_NOT_ALLOWED"


def test_an_unknown_method_is_refused() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b"{}").call("eth_accounts", [])
    assert caught.value.code == "RPC_METHOD_NOT_ALLOWED"


def test_a_malformed_envelope_is_refused() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b'{"jsonrpc":"2.0","id":1,"result":"0x8f","extra":1}').call("eth_chainId", [])
    assert caught.value.code == "RPC_REPLY_UNRECOGNIZED"


def test_a_non_canonical_quantity_is_refused() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b'{"jsonrpc":"2.0","id":1,"result":"0x08F"}').call("eth_chainId", [])
    assert caught.value.code == "RPC_QUANTITY_INVALID"


def test_a_provider_error_is_refused_without_provider_text() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"see https://rpc.invalid/key-secret-path"}}'
             ).call("eth_chainId", [])
    assert caught.value.code == "RPC_REFUSED"
    assert "key-secret-path" not in str(caught.value)


def test_send_raw_returns_only_the_matching_hash(tmp_path) -> None:
    from eth_utils import keccak

    signed = signed_for("wrap")
    tx_hash = "0x" + keccak(bytes.fromhex(signed[2:])).hex()
    payload = ('{"jsonrpc":"2.0","id":1,"result":"' + tx_hash + '"}').encode()
    assert _rpc(payload).send_raw(signed) == tx_hash


def test_send_raw_refuses_a_different_hash() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b'{"jsonrpc":"2.0","id":1,"result":"0x' + b"1" * 64 + b'"}').send_raw(signed_for("wrap"))
    assert caught.value.code == "RPC_HASH_INVALID"


def test_a_receipt_without_required_fields_is_refused() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b'{"jsonrpc":"2.0","id":1,"result":{"status":"0x1"}}').call(
            "eth_getTransactionReceipt", ["0x" + "1" * 64])
    assert caught.value.code == "RPC_RECEIPT_INVALID"


def test_get_code_accepts_empty_code_and_rejects_bad_hex() -> None:
    rpc = _rpc(b'{"jsonrpc":"2.0","id":1,"result":"0x"}')
    assert rpc.call("eth_getCode", [ENTRYPOINT, "latest"]) == "0x"
    with pytest.raises(OperatorError):
        _rpc(b'{"jsonrpc":"2.0","id":1,"result":"0xzz"}').call("eth_getCode", [ENTRYPOINT, "latest"])


def test_the_simulation_call_shape_is_accepted() -> None:
    slot = "0x" + "1" * 64
    payload = b'{"jsonrpc":"2.0","id":1,"result":"0x' + b"0" * 64 + b'"}'
    rpc = _rpc(payload)
    call = {"from": ENTRYPOINT, "to": ENTRYPOINT, "value": "0x0", "data": "0x"}
    result = rpc.call("eth_call", [call, "0x10", {ENTRYPOINT: {"stateDiff": {slot: slot}}}])
    assert result.startswith("0x")


def test_an_unknown_call_key_is_refused() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b"{}").call("eth_call", [{"to": ENTRYPOINT, "data": "0x", "gas": "0x1"}, "latest"])
    assert caught.value.code == "RPC_CALL_INVALID"


def test_a_malformed_state_override_is_refused() -> None:
    with pytest.raises(OperatorError) as caught:
        _rpc(b"{}").call("eth_call", [{"to": ENTRYPOINT, "data": "0x"}, "latest", {ENTRYPOINT: {"state": {}}}])
    assert caught.value.code == "RPC_CALL_INVALID"


def test_the_endpoint_is_not_in_an_invalid_endpoint_error() -> None:
    with pytest.raises(OperatorError) as caught:
        OperatorRpc(transport=FakeTransport(), endpoint="not-a-url/key-secret-path")
    assert caught.value.code == "RPC_ENDPOINT_INVALID"
    assert "key-secret-path" not in str(caught.value)
