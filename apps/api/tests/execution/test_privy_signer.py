"""The Privy sign-only HTTP adapter at the existing `SignerClient` seam (#58 Stage 3, LOCAL).

Network and authorization are injected doubles; nothing here opens a socket or reads a credential. Expected request
bytes, headers and the authorization payload are hand-written literals in `fixtures/privy_signer/`. The positive,
tampered and lost-reply paths run through the real `OriginalTransactionTransport` over the authored recordings.
These tests prove request shaping, refusal, bounds and redaction in this process only: not Privy acceptance, the
authorization signer's cryptography or any independent P21 enforcement.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import http.client
import json
import shutil
import sys
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from eth_account import Account

from edge_os_api.execution.original_recordings import RECORDINGS_FILE, OriginalRecordings
from edge_os_api.execution.original_transaction import (
    Leg,
    OriginalContext,
    OriginalTransactionTransport,
    ReplyLost,
    RpcError,
    is_signer_refusal,
)
from edge_os_api.execution.privy_signer import PrivySignerClient
from edge_os_api.execution.transport import PreparedSubmission
from edge_os_api.research_history.http_clients.client_config import HttpProviderError
from edge_os_api.research_history.http_clients.http_transport import HttpResponse, StdlibHttpTransport
from edge_os_api.research_history.provider_transport import SourceCancelled, SourceTimeout

# The accepted owned-loopback helpers live in a sibling test folder (shared server and recording connector).
_LOOPBACK_HELPERS = str(Path(__file__).resolve().parent.parent / "nansen_http_transport")
if _LOOPBACK_HELPERS not in sys.path:
    sys.path.insert(0, _LOOPBACK_HELPERS)

import nansen_http_support as loopback  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures"
EXPECTED = json.loads((FIXTURES / "privy_signer" / "expected_request.json").read_text())
RECORDINGS = FIXTURES / "original_transaction" / RECORDINGS_FILE

APP_ID = "app-test-1"
APP_SECRET = "sentinel-secret-AbC123"
BASIC_TOKEN = "YXBwLXRlc3QtMTpzZW50aW5lbC1zZWNyZXQtQWJDMTIz"
SIGNATURE = "c2lnbmF0dXJlLXNlbnRpbmVsLVh5Wg=="
SECRETS = (APP_SECRET, BASIC_TOKEN, SIGNATURE)
WALLET_ID = "wallet_abc-123"
NOW_MS = 1_789_999_990_000
EXPIRY_MS = 1_790_000_000_000
DEADLINE = 1_000.0

# The authored recording's public eth-account documentation key and wallet. Never a real wallet.
PUBLISHED_TEST_KEY = "0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"
PUBLISHED_WALLET = "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23"
OTHER_TEST_KEY = "0x" + "11" * 32
SELL_TOKEN = "0x2222222222222222222222222222222222222222"
BUY_TOKEN = "0x1111111111111111111111111111111111111111"
ENTRYPOINT = "0x00000000000000000000000000000000000f1007"
NOW = dt.datetime(2026, 1, 1, 0, 16, tzinfo=dt.timezone.utc)


class FakeHttp:
    """An `HttpTransport` double: records every request and answers with one scripted reply or exception."""

    def __init__(self, reply: Any = None, *, raises: BaseException | None = None,
                 during: Callable[[], None] | None = None) -> None:
        self.reply, self.raises, self.during = reply, raises, during
        self.calls: list[dict[str, Any]] = []

    def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes, timeout: float,
                deadline: float, max_response_bytes: int, cancel: Callable[[], bool] | None = None) -> HttpResponse:
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body, "timeout": timeout,
                           "deadline": deadline, "max_response_bytes": max_response_bytes, "cancel": cancel})
        if self.during is not None:
            self.during()
        if self.raises is not None:
            raise self.raises
        return self.reply


class Authorizer:
    """The injected authorization signer double: records each payload it receives and returns a sentinel."""

    def __init__(self, result: Any = SIGNATURE, *, raises: BaseException | None = None,
                 during: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.result, self.raises, self.during = result, raises, during
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: Mapping[str, Any]) -> Any:
        self.payloads.append(copy.deepcopy(dict(payload)))
        if self.during is not None:
            self.during(payload)  # type: ignore[arg-type]
        if self.raises is not None:
            raise self.raises
        return self.result


def reply(payload: Any, status: int = 200, headers: Mapping[str, str] | None = None) -> HttpResponse:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return HttpResponse(status=status, headers=dict(headers or {"content-type": "application/json"}), body=body)


def signed_reply(signed_hex: str, encoding: str = "rlp") -> HttpResponse:
    return reply({"method": "eth_signTransaction", "data": {"signed_transaction": signed_hex, "encoding": encoding}})


# The documented eth_signTransaction example reply (docs.privy.io), not a recording of any request.
SHORT_SIGNED = ("0x02f870830138de80830f4240830f437480940b81418147df37155d643b5cb65ba6c8cb7aba7687200000000000048"
                "0c080a05c11a2166ec56189d993dec477477d962ce0d4c466ab7ed8982110621ec87a57a003c796590c0c62eac30acd4"
                "12f2aa0e8ad740c4ded86fb64d3326ee4c0ea804c")


def client(http: Any, authorize: Any = None, *, cancel: Callable[[], bool] | None = None,
           wall_clock_ms: Callable[[], int] = lambda: NOW_MS, monotonic: Callable[[], float] = lambda: 10.0,
           **overrides: Any) -> PrivySignerClient:
    values: dict[str, Any] = dict(
        app_id=APP_ID, app_secret=APP_SECRET, authorize=authorize if authorize is not None else Authorizer(),
        request_id="attempt-0001", request_expiry_ms=EXPIRY_MS, http=http, connect_timeout_seconds=5.0,
        deadline_monotonic=DEADLINE, max_response_bytes=16_384, cancel=cancel, wall_clock_ms=wall_clock_ms,
        monotonic=monotonic)
    values.update(overrides)
    return PrivySignerClient(**values)


def body() -> dict[str, Any]:
    return copy.deepcopy(EXPECTED["body"])


def chain(error: BaseException) -> list[BaseException]:
    """The exception, its cause and context, recursively."""
    seen: list[BaseException] = []
    pending: list[BaseException | None] = [error]
    while pending:
        item = pending.pop()
        if item is None or any(item is known for known in seen):
            continue
        seen.append(item)
        pending.extend([item.__cause__, item.__context__])
    return seen


def assert_no_secret(error: BaseException) -> None:
    for item in chain(error):
        text = " ".join([str(item), repr(item), repr(item.args), repr(getattr(item, "__notes__", ""))])
        for secret in SECRETS:
            assert secret not in text


def local_unsent(reason: str) -> dict[str, Any]:
    return {"error": {"code": "LOCAL_UNSENT", "reason": reason}}


# ------------------------------------------------------------------------------------------- request shape


def test_one_post_carries_the_exact_literal_request_and_returns_the_signed_envelope():
    http, authorize = FakeHttp(signed_reply(SHORT_SIGNED)), Authorizer()
    caller_body = body()

    result = client(http, authorize).rpc(WALLET_ID, caller_body)

    assert result == {"data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}}
    assert len(http.calls) == 1
    call = http.calls[0]
    assert (call["method"], call["url"]) == ("POST", EXPECTED["url"])
    assert call["body"] == EXPECTED["wire_body"].encode()
    assert call["headers"] == EXPECTED["headers"]
    assert (call["timeout"], call["deadline"], call["max_response_bytes"]) == (5.0, DEADLINE, 16_384)
    assert authorize.payloads == [EXPECTED["authorization_payload"]]
    assert caller_body == EXPECTED["body"]


def test_the_cancellation_flag_reaches_the_transport_so_it_can_stop_between_reads():
    http, flag = FakeHttp(signed_reply(SHORT_SIGNED)), (lambda: False)
    client(http, cancel=flag).rpc(WALLET_ID, body())
    assert http.calls[0]["cancel"] is flag


def test_a_second_call_on_one_adapter_sends_nothing_and_stays_unknown():
    http = FakeHttp(signed_reply(SHORT_SIGNED))
    signer = client(http)
    signer.rpc(WALLET_ID, body())

    with pytest.raises(RpcError):
        signer.rpc(WALLET_ID, body())
    assert len(http.calls) == 1


def test_a_second_call_after_a_lost_reply_is_never_a_definite_refusal():
    http = FakeHttp(raises=SourceTimeout("slow"))
    signer = client(http)
    with pytest.raises(ReplyLost):
        signer.rpc(WALLET_ID, body())

    with pytest.raises(RpcError):
        signer.rpc(WALLET_ID, body())
    assert len(http.calls) == 1


# ------------------------------------------------------------------------------------------- local refusals


def with_transaction(**changes: Any) -> dict[str, Any]:
    value = body()
    transaction = value["params"]["transaction"]
    for name, item in changes.items():
        if item is DELETE:
            del transaction[name]
        else:
            transaction[name] = item
    return value


DELETE = object()


@pytest.mark.parametrize("wallet_id", [
    "", "../wallets/other", "wallet/../x", "a/b", "a?b=1", "a#b", "a%2Fb", "a b", "a\nb", "w" * 129, "wallet.1"])
def test_a_wallet_id_that_could_change_the_path_is_refused_before_authorization(wallet_id):
    http, authorize = FakeHttp(signed_reply(SHORT_SIGNED)), Authorizer()
    result = client(http, authorize).rpc(wallet_id, body())
    assert result == local_unsent("WALLET_ID_INVALID")
    assert is_signer_refusal(result)
    assert (http.calls, authorize.payloads) == ([], [])


@pytest.mark.parametrize("request_body,reason", [
    ("not a mapping", "BODY_INVALID"),
    ({"method": "eth_sendTransaction", "params": body()["params"]}, "METHOD_UNSUPPORTED"),
    ({"method": "personal_sign", "params": body()["params"]}, "METHOD_UNSUPPORTED"),
    ({**body(), "caip2": "eip155:143"}, "FIELD_UNSUPPORTED"),
    ({**body(), "chain_type": "ethereum"}, "FIELD_UNSUPPORTED"),
    ({"method": "eth_signTransaction"}, "FIELD_MISSING"),
    ({"method": "eth_signTransaction", "params": {"transaction": body()["params"]["transaction"], "x": 1}},
     "FIELD_UNSUPPORTED"),
    ({"method": "eth_signTransaction", "params": []}, "BODY_INVALID"),
    ({"method": "eth_signTransaction", "params": {"transaction": "0x02"}}, "BODY_INVALID"),
    (with_transaction(nonce=DELETE), "FIELD_MISSING"),
    (with_transaction(type=DELETE), "FIELD_MISSING"),
    (with_transaction(**{"from": PUBLISHED_WALLET}), "FIELD_UNSUPPORTED"),
    (with_transaction(gas_price=1), "FIELD_UNSUPPORTED"),
    (with_transaction(authorization_list=[]), "DELEGATION_UNSUPPORTED"),
    (with_transaction(authorization_list=[{"contract": ENTRYPOINT, "chain_id": 143, "nonce": 0}]),
     "DELEGATION_UNSUPPORTED"),
    (with_transaction(type=0), "TRANSACTION_TYPE_UNSUPPORTED"),
    (with_transaction(type=1), "TRANSACTION_TYPE_UNSUPPORTED"),
    (with_transaction(type=4), "TRANSACTION_TYPE_UNSUPPORTED"),
    (with_transaction(type="0x2"), "TRANSACTION_TYPE_UNSUPPORTED"),
    (with_transaction(type=True), "TRANSACTION_TYPE_UNSUPPORTED"),
    (with_transaction(nonce=True), "QUANTITY_UNSUPPORTED"),
    (with_transaction(nonce=7.0), "QUANTITY_UNSUPPORTED"),
    (with_transaction(nonce="0x7"), "QUANTITY_UNSUPPORTED"),
    (with_transaction(nonce=-1), "QUANTITY_UNSUPPORTED"),
    (with_transaction(value=2**53), "QUANTITY_UNSUPPORTED"),
    (with_transaction(gas_limit=2**53), "QUANTITY_UNSUPPORTED"),
    (with_transaction(max_fee_per_gas=2**64), "QUANTITY_UNSUPPORTED"),
    (with_transaction(max_priority_fee_per_gas=None), "QUANTITY_UNSUPPORTED"),
    (with_transaction(chain_id=0), "QUANTITY_UNSUPPORTED"),
    (with_transaction(to="0x1234"), "ADDRESS_INVALID"),
    (with_transaction(to="00000000000000000000000000000000000f1007ab"), "ADDRESS_INVALID"),
    (with_transaction(to=None), "ADDRESS_INVALID"),
    (with_transaction(data="0x123"), "DATA_INVALID"),
    (with_transaction(data="0xzz"), "DATA_INVALID"),
    (with_transaction(data="12345678"), "DATA_INVALID"),
    (with_transaction(data="0x" + "ab" * 40_000), "REQUEST_TOO_LARGE"),
])
def test_an_unsupported_request_is_refused_before_authorization_and_http(request_body, reason):
    http, authorize = FakeHttp(signed_reply(SHORT_SIGNED)), Authorizer()
    before = copy.deepcopy(request_body)

    result = client(http, authorize).rpc(WALLET_ID, request_body)

    assert result == local_unsent(reason)
    assert is_signer_refusal(result)
    assert (http.calls, authorize.payloads) == ([], [])
    assert request_body == before


def test_the_largest_safe_integer_quantity_is_accepted_unchanged():
    http = FakeHttp(signed_reply(SHORT_SIGNED))
    client(http).rpc(WALLET_ID, with_transaction(gas_limit=2**53 - 1))
    assert b'"gas_limit":9007199254740991,' in http.calls[0]["body"]


def test_an_unsupported_first_call_still_uses_up_the_adapter():
    http = FakeHttp(signed_reply(SHORT_SIGNED))
    signer = client(http)
    assert signer.rpc(WALLET_ID, with_transaction(type=4)) == local_unsent("TRANSACTION_TYPE_UNSUPPORTED")
    with pytest.raises(RpcError):
        signer.rpc(WALLET_ID, body())
    assert http.calls == []


@pytest.mark.parametrize("state,reason", [
    ({"cancel": lambda: True}, "CANCELLED"),
    ({"monotonic": lambda: DEADLINE}, "DEADLINE_PASSED"),
    ({"monotonic": lambda: DEADLINE + 1}, "DEADLINE_PASSED"),
    ({"wall_clock_ms": lambda: EXPIRY_MS}, "REQUEST_EXPIRED"),
    ({"wall_clock_ms": lambda: EXPIRY_MS + 1}, "REQUEST_EXPIRED"),
])
def test_a_stop_before_authorization_sends_nothing(state, reason):
    http, authorize = FakeHttp(signed_reply(SHORT_SIGNED)), Authorizer()
    result = client(http, authorize, **state).rpc(WALLET_ID, body())
    assert result == local_unsent(reason)
    assert (http.calls, authorize.payloads) == ([], [])


@pytest.mark.parametrize("flip,reason", [("cancel", "CANCELLED"), ("deadline", "DEADLINE_PASSED"),
                                         ("expiry", "REQUEST_EXPIRED")])
def test_a_stop_that_arrives_during_authorization_sends_nothing(flip, reason):
    moment = {"cancel": False, "monotonic": 10.0, "wall": NOW_MS}

    def arrive(_payload: dict[str, Any]) -> None:
        moment.update({"cancel": {"cancel": True}, "deadline": {"monotonic": DEADLINE},
                       "expiry": {"wall": EXPIRY_MS}}[flip])

    http, authorize = FakeHttp(signed_reply(SHORT_SIGNED)), Authorizer(during=arrive)
    result = client(http, authorize, cancel=lambda: moment["cancel"], monotonic=lambda: moment["monotonic"],
                    wall_clock_ms=lambda: moment["wall"]).rpc(WALLET_ID, body())

    assert result == local_unsent(reason)
    assert len(authorize.payloads) == 1
    assert http.calls == []


@pytest.mark.parametrize("authorize,reason", [
    (Authorizer(raises=RuntimeError(f"key store unavailable {APP_SECRET}")), "AUTHORIZATION_FAILED"),
    (Authorizer(raises=KeyboardInterrupt()), None),
    (Authorizer(result=None), "AUTHORIZATION_INVALID"),
    (Authorizer(result=b"c2lnbmF0dXJl"), "AUTHORIZATION_INVALID"),
    (Authorizer(result=""), "AUTHORIZATION_INVALID"),
    (Authorizer(result="c2ln\r\nX-Injected: 1"), "AUTHORIZATION_INVALID"),
    (Authorizer(result="sig nature"), "AUTHORIZATION_INVALID"),
    (Authorizer(result="A" * 4097), "AUTHORIZATION_INVALID"),
])
def test_an_authorization_failure_sends_nothing(authorize, reason):
    http = FakeHttp(signed_reply(SHORT_SIGNED))
    signer = client(http, authorize)
    if reason is None:
        with pytest.raises(KeyboardInterrupt):
            signer.rpc(WALLET_ID, body())
    else:
        assert signer.rpc(WALLET_ID, body()) == local_unsent(reason)
    assert http.calls == []


def test_several_comma_separated_signatures_are_sent_as_given():
    http = FakeHttp(signed_reply(SHORT_SIGNED))
    client(http, Authorizer(result="c2ln,c2lnMg==")).rpc(WALLET_ID, body())
    assert http.calls[0]["headers"]["privy-authorization-signature"] == "c2ln,c2lnMg=="


@pytest.mark.parametrize("drift", [
    lambda payload: payload["body"]["params"]["transaction"].__setitem__("nonce", 8),
    lambda payload: payload["headers"].__setitem__("privy-request-expiry", "1790000600000"),
    lambda payload: payload.__setitem__("url", "https://api.privy.io/v1/wallets/other/rpc"),
    lambda payload: payload["body"]["params"]["transaction"].__setitem__("authorization_list", []),
])
def test_a_callback_that_changes_its_payload_is_refused_before_send(drift):
    http = FakeHttp(signed_reply(SHORT_SIGNED))
    caller_body = body()
    result = client(http, Authorizer(during=drift)).rpc(WALLET_ID, caller_body)
    assert result == local_unsent("AUTHORIZATION_PAYLOAD_CHANGED")
    assert http.calls == []
    assert caller_body == EXPECTED["body"]


# ------------------------------------------------------------------------------------------- unknown replies


ERROR_BODY = {"error": {"code": "policy_violation", "message": "denied"}}


@pytest.mark.parametrize("response", [
    reply(ERROR_BODY, 400), reply(ERROR_BODY, 401), reply(ERROR_BODY, 403), reply(ERROR_BODY, 404),
    reply({"error": "request_expired"}, 400), reply({"error": "zero_correct_authorization_signatures"}, 401),
    reply(ERROR_BODY, 409), reply(ERROR_BODY, 429), reply(ERROR_BODY, 500), reply(ERROR_BODY, 502),
    reply(ERROR_BODY, 200), reply({"error": {"code": "x"}, "method": "eth_signTransaction"}, 200),
    reply(b"<html><body>Attention Required! | Cloudflare</body></html>", 403, {"content-type": "text/html"}),
    reply(b"<html>ok</html>", 200, {"content-type": "text/html"}),
    reply({"method": "eth_signTransaction", "data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}}, 301),
    reply({"method": "eth_signTransaction", "data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}}, 202),
])
def test_an_error_or_unrecognized_status_is_unknown_never_a_refusal(response):
    with pytest.raises(RpcError) as raised:
        client(FakeHttp(response)).rpc(WALLET_ID, body())
    assert_no_secret(raised.value)


@pytest.mark.parametrize("payload", [
    b"not json", b"\xff\xfe", b"[1, 2]", b'"text"', b"", b"[" * 100_000 + b"]" * 100_000,
    {"method": "eth_signTransaction"},
    {"data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}},
    {"method": "eth_sendTransaction", "data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}},
    {"method": "eth_signTransaction", "data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}, "error": None},
    {"method": "eth_signTransaction", "data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}, "extra": 1},
    {"method": "eth_signTransaction", "data": {"signed_transaction": SHORT_SIGNED}},
    {"method": "eth_signTransaction", "data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp", "hash": "0x"}},
    {"method": "eth_signTransaction", "data": {"signed_transaction": SHORT_SIGNED, "encoding": "hex"}},
    {"method": "eth_signTransaction", "data": {"signed_transaction": "0x", "encoding": "rlp"}},
    {"method": "eth_signTransaction", "data": {"signed_transaction": "0x0", "encoding": "rlp"}},
    {"method": "eth_signTransaction", "data": {"signed_transaction": "02f870", "encoding": "rlp"}},
    {"method": "eth_signTransaction", "data": {"signed_transaction": 2, "encoding": "rlp"}},
    {"method": "eth_signTransaction", "data": {"signed_transaction": "0x" + "ab" * 8193, "encoding": "rlp"}},
    {"method": "eth_signTransaction", "data": [SHORT_SIGNED]},
])
def test_a_malformed_or_contradictory_success_reply_is_unknown(payload):
    signer = client(FakeHttp(reply(payload)), max_response_bytes=1_000_000)
    with pytest.raises(RpcError) as raised:
        signer.rpc(WALLET_ID, body())
    assert_no_secret(raised.value)


def test_a_reply_larger_than_the_bound_is_unknown_even_if_the_transport_returned_it():
    response = signed_reply(SHORT_SIGNED)
    with pytest.raises(RpcError):
        client(FakeHttp(response), max_response_bytes=len(response.body) - 1).rpc(WALLET_ID, body())


@pytest.mark.parametrize("response", [
    HttpResponse(status=200, headers={"content-encoding": "gzip"}, body=signed_reply(SHORT_SIGNED).body),
    HttpResponse(status=True, headers={}, body=signed_reply(SHORT_SIGNED).body),
    HttpResponse(status=200, headers={}, body="text"),  # type: ignore[arg-type]
    {"status": 200, "body": b"{}"},
    None,
])
def test_a_reply_that_is_not_a_bounded_http_response_is_unknown(response):
    with pytest.raises(RpcError):
        client(FakeHttp(response)).rpc(WALLET_ID, body())


@pytest.mark.parametrize("echo", [
    {"body": json.dumps({"error": {"message": f"bad secret {APP_SECRET}"}}).encode(), "status": 401},
    {"body": json.dumps({"error": {"message": f"Basic {BASIC_TOKEN}"}}).encode(), "status": 400},
    {"body": json.dumps({"error": {"signature": SIGNATURE}}).encode(), "status": 401},
    {"body": json.dumps({"method": "eth_signTransaction", "data": {"signed_transaction": SHORT_SIGNED,
                                                                   "encoding": "rlp"}, "note": SIGNATURE}).encode(),
     "status": 200},
    {"body": ('{"error": "' + "".join(f"\\u{ord(c):04x}" for c in APP_SECRET) + '"}').encode(), "status": 500},
    {"body": json.dumps({"error": APP_SECRET.upper()}).encode(), "status": 500},
    {"body": signed_reply(SHORT_SIGNED).body, "status": 200, "headers": {"x-debug": SIGNATURE}},
    {"body": signed_reply(SHORT_SIGNED).body, "status": 200, "headers": {f"x-{APP_SECRET}": "1"}},
])
def test_a_reply_that_echoes_a_credential_or_signature_is_unknown_and_never_repeats_it(echo):
    response = HttpResponse(status=echo["status"], headers=echo.get("headers", {}), body=echo["body"])
    with pytest.raises(RpcError) as raised:
        client(FakeHttp(response)).rpc(WALLET_ID, body())
    assert_no_secret(raised.value)


def nested_failure() -> OSError:
    try:
        try:
            raise ValueError(f"inner {APP_SECRET} {SIGNATURE}")
        except ValueError as inner:
            raise OSError(f"Connection reset; Authorization: Basic {BASIC_TOKEN}") from inner
    except OSError as outer:
        return outer


@pytest.mark.parametrize("failure", [
    SourceTimeout("the HTTP request exceeded its time bound"), TimeoutError("timed out"),
    SourceCancelled("the caller cancelled the request"), ConnectionResetError("reset"),
    http.client.RemoteDisconnected("Remote end closed connection without response"),
    http.client.IncompleteRead(b"partial"), nested_failure(), RuntimeError(f"unexpected {APP_SECRET}"),
])
def test_a_transport_failure_after_dispatch_is_a_lost_reply_without_secret_context(failure):
    http = FakeHttp(raises=failure)
    with pytest.raises(ReplyLost) as raised:
        client(http).rpc(WALLET_ID, body())
    assert len(http.calls) == 1
    assert_no_secret(raised.value)


@pytest.mark.parametrize("code", ["OVERSIZED_RESPONSE", "MALFORMED_PROVIDER_RESPONSE", "REDIRECT_REFUSED",
                                  "UNSUPPORTED_CONTENT_ENCODING", f"X-{APP_SECRET}"])
def test_a_refused_http_reply_from_the_shared_transport_is_unknown(code):
    http = FakeHttp(raises=HttpProviderError(code, f"provider said {SIGNATURE}"))
    with pytest.raises(RpcError) as raised:
        client(http).rpc(WALLET_ID, body())
    assert_no_secret(raised.value)


# ------------------------------------------------------------------------------------------- construction


def test_construction_makes_no_call_and_repr_holds_no_credential():
    http, authorize = FakeHttp(signed_reply(SHORT_SIGNED)), Authorizer()
    signer = client(http, authorize)
    assert (http.calls, authorize.payloads) == ([], [])
    for secret in SECRETS:
        assert secret not in repr(signer)
        assert secret not in str(signer)


@pytest.mark.parametrize("overrides", [
    {"app_id": ""}, {"app_id": "app/../x"}, {"app_secret": ""}, {"app_secret": "has space"},
    {"app_secret": "line\nbreak"}, {"app_secret": 123}, {"authorize": "not callable"},
    {"request_id": ""}, {"request_id": "a b"}, {"request_id": "x" * 257},
    {"request_expiry_ms": 0}, {"request_expiry_ms": True}, {"request_expiry_ms": 1.79e12},
    {"request_expiry_ms": "1790000000000"},
    {"http": object()}, {"connect_timeout_seconds": 0}, {"connect_timeout_seconds": float("inf")},
    {"deadline_monotonic": float("nan")}, {"max_response_bytes": 0}, {"max_response_bytes": True},
    {"cancel": "yes"},
])
def test_invalid_construction_is_refused_without_repeating_the_secret(overrides):
    overrides = {"http": FakeHttp(None), **overrides}
    with pytest.raises(ValueError) as raised:
        client(**overrides)
    assert_no_secret(raised.value)


# ------------------------------------------------------------------------------------------- through the caller


def original(tmp_path: Path, signer: Any) -> tuple[OriginalTransactionTransport, OriginalRecordings,
                                                     list[tuple[str, dict[str, Any]]]]:
    shutil.copy(RECORDINGS, tmp_path / RECORDINGS_FILE)
    recordings = OriginalRecordings.load(tmp_path)
    clients = dataclasses.replace(recordings.clients(lambda: NOW), signer=signer)
    context = OriginalContext(
        owner_id="owner-1", agent_id="agent-1", wallet_id=WALLET_ID, wallet_address=PUBLISHED_WALLET,
        network_id="monad:143", chain_id=143, identity={}, action_id="action-1", payload_hash="sha256:payload",
        operation="ENTRY", sell=Leg(asset_id=f"monad:143/{SELL_TOKEN}", token=SELL_TOKEN, decimals=6, raw=100_000_000),
        buy=Leg(asset_id=f"monad:143/{BUY_TOKEN}", token=BUY_TOKEN, decimals=18, raw=50 * 10**18),
        gas_asset_id="monad:143/native", gas_cap_raw=10**18, allowance_raw=100_000_000,
        decision_slot=NOW - dt.timedelta(minutes=1), intent_expires_at=NOW + dt.timedelta(minutes=5),
        mandate_expires_at="2026-01-01T01:00:00+00:00")
    transport = OriginalTransactionTransport(context, clients, recordings.profile, controls=lambda: [],
                                             clock=lambda: NOW)
    return transport, recordings, []


def submit(transport: OriginalTransactionTransport, stages: list[tuple[str, dict[str, Any]]]):
    prepared = PreparedSubmission(action_id="action-1", owner_id="owner-1", wallet_id=WALLET_ID,
                                  network_id="monad:143", operation="ENTRY", payload_hash="sha256:payload",
                                  attempt_id="attempt-0001")
    return transport.submit_original(prepared, lambda stage, values: stages.append((stage, values)))


def recorded_signature(operation: str, nonce: int) -> str:
    data = json.loads(RECORDINGS.read_text())
    return next(item["response"]["data"]["signed_transaction"] for item in data["signatures"]
                if item["operation"] == operation and item["nonce"] == nonce)


ENTRY_NONCE0_HASH = "0x7067b4c886f172b32b1c2839bcd70a45186817e3ade5648bb34fc0d6ea7aa28d"


def broadcasts(recordings: OriginalRecordings) -> int:
    return recordings.call_counts().get("broadcast.eth_sendRawTransaction", 0)


def test_the_caller_signs_through_the_adapter_validates_and_broadcasts_once(tmp_path):
    http = FakeHttp(signed_reply(recorded_signature("ENTRY", 0)))
    transport, recordings, stages = original(tmp_path, client(http))

    outcome = submit(transport, stages)

    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", "BROADCAST_RETURNED")
    assert len(http.calls) == 1
    sent = json.loads(http.calls[0]["body"])["params"]["transaction"]
    prepared = dict(stages)["PREPARED"]
    assert sent == prepared["unsigned"] == prepared["signing_request"]["body"]["params"]["transaction"]
    assert http.calls[0]["headers"]["privy-idempotency-key"] == "attempt-0001"
    assert dict(stages)["SIGNED"]["transaction_hash"] == ENTRY_NONCE0_HASH
    assert broadcasts(recordings) == 1


def resigned(key: str, **changes: Any) -> str:
    """The recorded ENTRY nonce-0 transaction, with field changes, signed by a public test key."""
    calldata = "0x" + next(route["response"]["transaction"]["calldata"]
                           for route in json.loads(RECORDINGS.read_text())["routes"]
                           if route["request"]["amount"] == "100000000")
    fields = {"type": 2, "chainId": 143, "nonce": 0, "to": ENTRYPOINT, "value": 0, "data": calldata, "gas": 300_000,
              "maxFeePerGas": 3_000_000_000, "maxPriorityFeePerGas": 1_000_000_000, "accessList": []}
    fields.update(changes)
    return "0x" + bytes(Account.sign_transaction(fields, key).raw_transaction).hex()


@pytest.mark.parametrize("signed,reasons", [
    (lambda: recorded_signature("ENTRY", 1), ["SIGNED_NONCE_MISMATCH"]),
    (lambda: resigned(OTHER_TEST_KEY), ["SIGNED_SENDER_MISMATCH"]),
    (lambda: resigned(PUBLISHED_TEST_KEY, value=1), ["SIGNED_VALUE_MISMATCH"]),
    (lambda: resigned(PUBLISHED_TEST_KEY, data="0x12345678"), ["SIGNED_DATA_MISMATCH"]),
    (lambda: resigned(PUBLISHED_TEST_KEY, maxFeePerGas=3_000_000_001), ["SIGNED_MAXFEEPERGAS_MISMATCH"]),
    (lambda: resigned(PUBLISHED_TEST_KEY, maxPriorityFeePerGas=1), ["SIGNED_MAXPRIORITYFEEPERGAS_MISMATCH"]),
    (lambda: resigned(PUBLISHED_TEST_KEY, gas=300_001), ["SIGNED_GAS_MISMATCH"]),
])
def test_signed_bytes_that_differ_from_the_original_are_refused_before_broadcast(tmp_path, signed, reasons):
    transport, recordings, stages = original(tmp_path, client(FakeHttp(signed_reply(signed()))))

    outcome = submit(transport, stages)

    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", "SIGNED_RESPONSE_REJECTED")
    assert dict(stages)["SIGNED_RESPONSE_REJECTED"]["reasons"] == reasons
    assert broadcasts(recordings) == 0


def test_a_signed_reply_in_another_encoding_never_reaches_broadcast(tmp_path):
    transport, recordings, stages = original(
        tmp_path, client(FakeHttp(signed_reply(recorded_signature("ENTRY", 0), encoding="hex"))))

    outcome = submit(transport, stages)

    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", "SIGNING_UNKNOWN")
    assert broadcasts(recordings) == 0


@pytest.mark.parametrize("failure", [SourceTimeout("lost"), ConnectionResetError("reset")])
def test_a_lost_signer_reply_is_signing_unknown_with_one_call_and_no_broadcast(tmp_path, failure):
    http, authorize = FakeHttp(raises=failure), Authorizer()
    transport, recordings, stages = original(tmp_path, client(http, authorize))

    outcome = submit(transport, stages)

    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", "SIGNING_UNKNOWN")
    assert (len(http.calls), len(authorize.payloads)) == (1, 1)
    assert broadcasts(recordings) == 0
    assert [stage for stage, _ in stages] == ["PREPARED", "SIGN_REQUESTED", "SIGNING_UNKNOWN"]


def test_a_provider_error_reply_is_signing_unknown_not_signer_refused(tmp_path):
    http = FakeHttp(reply(ERROR_BODY, 403))
    transport, recordings, stages = original(tmp_path, client(http))

    outcome = submit(transport, stages)

    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", "SIGNING_UNKNOWN")
    assert broadcasts(recordings) == 0


def test_a_local_refusal_reaches_the_caller_as_definitely_unsent(tmp_path):
    http, authorize = FakeHttp(signed_reply(recorded_signature("ENTRY", 0))), Authorizer()
    transport, recordings, stages = original(tmp_path, client(http, authorize, cancel=lambda: True))

    outcome = submit(transport, stages)

    assert (outcome.outcome, outcome.detail) == ("DEFINITELY_UNSENT", "SIGNER_REFUSED")
    assert (http.calls, authorize.payloads) == ([], [])
    assert broadcasts(recordings) == 0


# ------------------------------------------------------------------------------------------- owned loopback
#
# The shipped `StdlibHttpTransport` over an owned 127.0.0.1 listener, reusing the accepted Nansen loopback helpers.
# The client keeps its literal `https://api.privy.io/...` URL and authorization payload; only the injected connector
# points the socket at the owned port and records the requested target. This proves the shipped socket/HTTP handling
# (framing, bounds, redirect refusal, deadline, cancellation, close) in this process. It does not prove public DNS,
# TLS or Privy acceptance. Credentials and signatures are synthetic. Every test here opens sockets: run them only in a
# granted loopback window (`-k loopback`); the pure selection is `-k "not loopback"`.

Reply = loopback.http_support.Reply
LoopbackServer = loopback.http_support.LoopbackServer
RPC_PATH = "/v1/wallets/wallet_abc-123/rpc"


class Listener:
    """Records every request the owned server receives and answers with one scripted reply."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.received: list[tuple[str, str, dict[str, str], bytes]] = []

    def __call__(self, method: str, path: str, headers: Mapping[str, str], body: bytes) -> Any:
        self.received.append((method, path, {name.lower(): value for name, value in headers.items()}, body))
        return self.answer


def live_timers() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if isinstance(thread, threading.Timer) and thread.is_alive()]


def over_loopback(server: Any, authorize: Any = None, *, on_connect: Callable[[], None] | None = None,
                  **overrides: Any) -> tuple[PrivySignerClient, Any]:
    connector = loopback.LoopbackConnector(server, on_connect=on_connect)
    values: dict[str, Any] = dict(monotonic=time.monotonic, deadline_monotonic=time.monotonic() + 30.0,
                                  connect_timeout_seconds=2.0)
    values.update(overrides)
    return client(StdlibHttpTransport(connect=connector), authorize, **values), connector


def assert_one_closed_attempt(connector: Any, listener: Listener) -> None:
    assert connector.targets == [("https", "api.privy.io", None)]
    assert len(connector.sockets) == 1 and connector.sockets[0].fileno() == -1
    assert len(listener.received) == 1
    assert live_timers() == []


def json_reply(payload: Any, status: int = 200, headers: Mapping[str, str] | None = None) -> Any:
    return Reply(status=status, body=json.dumps(payload).encode(),
                 headers=dict(headers or {"content-type": "application/json"}))


def test_loopback_one_post_carries_the_literal_request_and_returns_the_signed_envelope():
    listener = Listener(json_reply({"method": "eth_signTransaction",
                                    "data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}}))
    with LoopbackServer(listener) as server:
        signer, connector = over_loopback(server)
        result = signer.rpc(WALLET_ID, body())

    assert result == {"data": {"signed_transaction": SHORT_SIGNED, "encoding": "rlp"}}
    assert_one_closed_attempt(connector, listener)
    method, path, headers, sent = listener.received[0]
    assert (method, path, sent) == ("POST", RPC_PATH, EXPECTED["wire_body"].encode())
    assert {name: headers[name] for name in EXPECTED["headers"]} == EXPECTED["headers"]
    assert headers["content-length"] == str(len(EXPECTED["wire_body"]))


def test_loopback_the_caller_validates_and_broadcasts_the_signed_reply_once(tmp_path):
    listener = Listener(json_reply({"method": "eth_signTransaction",
                                    "data": {"signed_transaction": recorded_signature("ENTRY", 0),
                                             "encoding": "rlp"}}))
    with LoopbackServer(listener) as server:
        signer, connector = over_loopback(server)
        transport, recordings, stages = original(tmp_path, signer)
        outcome = submit(transport, stages)

    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", "BROADCAST_RETURNED")
    assert dict(stages)["SIGNED"]["transaction_hash"] == ENTRY_NONCE0_HASH
    assert broadcasts(recordings) == 1
    assert_one_closed_attempt(connector, listener)


@pytest.mark.parametrize("answer", [
    json_reply({"error": {"code": "policy_violation"}}, 403),
    json_reply({"error": "request_expired"}, 400),
    json_reply({"error": "internal"}, 500),
    Reply(status=403, body=b"<html>Attention Required! | Cloudflare</html>", headers={"content-type": "text/html"}),
    Reply(status=302, body=b"", headers={"location": "https://api.privy.io/v1/wallets/other/rpc"}),
    Reply(status=200, body=b"{not json", headers={"content-type": "application/json"}),
    Reply(status=200, body=b"x" * 20_000, headers={"content-type": "application/json"}),
    Reply(raw_http=b"HTTP/1.1 abc\r\n\r\n"),
])
def test_loopback_an_error_redirect_malformed_or_oversized_reply_is_unknown_after_one_attempt(answer, caplog):
    listener = Listener(answer)
    with LoopbackServer(listener) as server:
        signer, connector = over_loopback(server)
        with pytest.raises(RpcError) as raised:
            signer.rpc(WALLET_ID, body())

    assert_one_closed_attempt(connector, listener)
    assert_no_secret(raised.value)
    assert all(secret not in caplog.text for secret in SECRETS)


@pytest.mark.parametrize("answer", [
    Reply(raw_http=b""),
    Reply(raw_http=b"HTTP/1.1 200 OK\r\ncontent-length: 400\r\n\r\n{\"method\""),
])
def test_loopback_an_empty_or_truncated_reply_after_dispatch_stays_unknown_after_one_attempt(answer):
    # The keep-alive listener sends nothing or a short body and holds the socket: the 2 s socket timeout ends it.
    listener = Listener(answer)
    with LoopbackServer(listener) as server:
        signer, connector = over_loopback(server)
        with pytest.raises((RpcError, ReplyLost)) as raised:  # both are SIGNING_UNKNOWN to the caller
            signer.rpc(WALLET_ID, body())

    assert_one_closed_attempt(connector, listener)
    assert_no_secret(raised.value)


def test_loopback_a_slow_reply_past_the_deadline_is_a_lost_reply_after_one_attempt():
    listener = Listener(Reply(status=200, body=b"{}", delay_before_headers=1.5))
    with LoopbackServer(listener) as server:
        signer, connector = over_loopback(server, deadline_monotonic=time.monotonic() + 0.5)
        started = time.monotonic()
        with pytest.raises(ReplyLost):
            signer.rpc(WALLET_ID, body())
        elapsed = time.monotonic() - started

    assert elapsed < 1.4
    assert_one_closed_attempt(connector, listener)


def test_loopback_an_in_flight_cancellation_stops_a_paced_body_as_a_lost_reply():
    listener = Listener(Reply(chunks=[b"{", b'"method"', b':"eth_signTransaction"', b"}"], pause_between_chunks=0.2))
    flag = {"cancel": False}
    with LoopbackServer(listener) as server:
        # The flag turns on once the socket is open, so only the in-flight checks can see it.
        signer, connector = over_loopback(server, on_connect=lambda: flag.update(cancel=True),
                                          cancel=lambda: flag["cancel"])
        started = time.monotonic()
        with pytest.raises(ReplyLost):
            signer.rpc(WALLET_ID, body())
        elapsed = time.monotonic() - started

    assert elapsed < 0.6
    assert_one_closed_attempt(connector, listener)


def test_loopback_a_reply_that_echoes_the_credential_is_unknown_and_never_repeats_it():
    listener = Listener(json_reply({"error": {"message": f"bad {APP_SECRET} {SIGNATURE}"}}, 401))
    with LoopbackServer(listener) as server:
        signer, connector = over_loopback(server)
        with pytest.raises(RpcError) as raised:
            signer.rpc(WALLET_ID, body())

    assert_one_closed_attempt(connector, listener)
    assert_no_secret(raised.value)
