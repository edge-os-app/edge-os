"""Reply and failure mapping for the Nansen HTTP transport, through NansenClient and run_research."""

from __future__ import annotations

import http.client
import json
import socket
from decimal import Decimal

import pytest

import nansen_http_support as support
from edge_os_api.nansen_research import (
    NansenAuthError,
    NansenCancelled,
    NansenClient,
    NansenContractError,
    NansenPaymentRequired,
    NansenProtocolError,
    NansenProviderError,
    NansenRateLimited,
    NansenTimeout,
    NansenTransportError,
    run_research,
)
from edge_os_api.research_history.http_clients.client_config import ClientConfigError, HttpProviderError
from edge_os_api.research_history.provider_transport import SourceCancelled, SourceFailure, SourceTimeout

KEY = support.SYNTHETIC_KEY
HOLDERS = ("holders", "/api/v1/tgm/holders")


def _client(http: support.AuthoredHttp, **limits) -> NansenClient:
    return NansenClient(support.adapter(http), support.nansen.limits(**limits))


def _holders_page(is_last_page: bool = True) -> bytes:
    return json.dumps(support.nansen.holder_payload([support.nansen.holder_row("0xaaa")],
                                                    is_last_page=is_last_page)).encode()


def test_a_success_reply_reaches_the_client_with_its_retained_headers() -> None:
    http = support.AuthoredHttp(support.reply(200, _holders_page(), {
        "x-request-id": "req-ok", "x-nansen-credits-cost": "5", "x-nansen-credits-used": "5",
        "x-nansen-credits-remaining": "995"}))
    client = _client(http)
    fetch = client.call("holders", support.nansen.holder_body())
    assert (fetch.status, fetch.request_id, fetch.deducted_credits, fetch.remaining_credits) == (200, "req-ok", "5", "995")
    assert fetch.payload["data"][0]["address"] == "0xaaa"
    assert client.attempts == 1 and len(http.calls) == 1


@pytest.mark.parametrize("status, body, headers, error_type, code, retry_after", [
    (401, b'{"code": "unauthenticated"}', {}, NansenAuthError, "UNAUTHENTICATED", None),
    (402, b'{"code": "insufficient_credits"}', {}, NansenPaymentRequired, "PAYMENT_REQUIRED", None),
    (403, b'{"code": "insufficient_credits"}', {}, NansenProviderError, "insufficient_credits", None),
    (429, b'{"code": "rate_limit_exceeded"}', {"retry-after": "7"}, NansenRateLimited, "RATE_LIMITED", "7"),
    (503, b'{"code": "upstream_unavailable"}', {}, NansenProviderError, "upstream_unavailable", None),
    (500, b"<html>oops</html>", {}, NansenProviderError, "HTTP_500", None),
])
def test_an_http_error_is_returned_once_for_the_client_to_map_without_retry(
        status, body, headers, error_type, code, retry_after) -> None:
    http = support.AuthoredHttp(support.reply(status, body, {"x-request-id": f"req-{status}",
                                                             "x-nansen-credits-used": "0", **headers}))
    client = _client(http)
    with pytest.raises(error_type) as caught:
        client.call("holders", support.nansen.holder_body())
    assert (caught.value.code, caught.value.status, caught.value.request_id) == (code, status, f"req-{status}")
    assert caught.value.deducted_credits == "0"
    assert caught.value.retry_after == retry_after
    assert len(http.calls) == 1
    assert client.attempts == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_a_redirect_is_refused_and_never_followed(status: int) -> None:
    http = support.AuthoredHttp(support.reply(status, b"", {"location": "https://evil.example/x"}))
    client = _client(http)
    with pytest.raises(NansenContractError) as caught:
        client.call("holders", support.nansen.holder_body())
    assert (caught.value.code, caught.value.status) == ("REDIRECT_REFUSED", status)
    assert caught.value.request_id is None and caught.value.response_sha256 is None
    assert len(http.calls) == 1
    assert client.reserved_credits == Decimal("5")


def test_a_reply_over_the_response_cap_is_refused_and_the_exact_cap_is_returned() -> None:
    http = support.AuthoredHttp(support.reply(200, b"x" * 101), support.reply(200, b"y" * 100))
    transport = support.adapter(http, max_response_bytes=100)
    with pytest.raises(NansenContractError) as caught:
        transport.request(*HOLDERS, support.nansen.holder_body())
    assert caught.value.code == "OVERSIZED_RESPONSE"
    assert caught.value.status is None
    assert transport.request(*HOLDERS, support.nansen.holder_body()).body == b"y" * 100


@pytest.mark.parametrize("bad", [
    support.reply(600, b"{}"), support.reply(99, b"{}"),
    support.http_support.HttpResponse(status=200, headers={}, body="text"),  # type: ignore[arg-type]
    support.http_support.HttpResponse(status=True, headers={}, body=b"{}"),  # type: ignore[arg-type]
    support.http_support.HttpResponse(status=200, headers=[("a", "b")], body=b"{}"),  # type: ignore[arg-type]
])
def test_a_malformed_reply_is_a_contract_failure(bad) -> None:
    with pytest.raises(NansenContractError) as caught:
        support.adapter(support.AuthoredHttp(bad)).request(*HOLDERS, support.nansen.holder_body())
    assert caught.value.code == "MALFORMED_PROVIDER_RESPONSE"


def test_a_non_response_from_the_http_transport_is_a_protocol_defect() -> None:
    with pytest.raises(NansenProtocolError) as caught:
        support.adapter(support.AuthoredHttp({"status": 200})).request(*HOLDERS, support.nansen.holder_body())
    assert caught.value.code == "TRANSPORT_NOT_A_RESPONSE"


@pytest.mark.parametrize("echo", [
    support.reply(200, b'{"data": [], "debug": "' + KEY.encode() + b'"}'),
    support.reply(401, b'{"message": "bad key ' + KEY.encode() + b'"}'),
    support.reply(200, b"{}", {"x-echo": f"apikey={KEY}"}),
    support.reply(200, b"{}", {f"x-{KEY}": "1"}),
    support.reply(200, b"{}", {"x-echo": KEY.upper()}),
    support.reply(200, b'{"k": "' + KEY.upper().encode() + b'"}'),
])
def test_a_reply_that_echoes_the_key_is_refused_without_a_hash(echo) -> None:
    http = support.AuthoredHttp(echo)
    with pytest.raises(NansenContractError) as caught:
        _client(http).call("holders", support.nansen.holder_body())
    error = caught.value
    assert error.code == "CREDENTIAL_ECHO"
    assert error.response_sha256 is None and error.request_id is None
    assert KEY not in str(error) and KEY not in repr(error)
    assert len(http.calls) == 1


@pytest.mark.parametrize("raised, error_type, code", [
    (SourceTimeout(f"timed out {KEY}"), NansenTimeout, "TIMEOUT"),
    (TimeoutError(f"socket {KEY}"), NansenTimeout, "TIMEOUT"),
    (SourceCancelled(f"cancelled {KEY}"), NansenCancelled, "CANCELLED"),
    (HttpProviderError("OVERSIZED_RESPONSE", f"too big {KEY}"), NansenContractError, "OVERSIZED_RESPONSE"),
    (HttpProviderError("MALFORMED_PROVIDER_RESPONSE", f"bad {KEY}"), NansenContractError,
     "MALFORMED_PROVIDER_RESPONSE"),
    (HttpProviderError("UNSUPPORTED_CONTENT_ENCODING", f"gzip {KEY}"), NansenProviderError,
     "UNSUPPORTED_CONTENT_ENCODING"),
    (http.client.BadStatusLine(f"HTTP/9 {KEY}"), NansenContractError, "MALFORMED_PROVIDER_RESPONSE"),
    (ConnectionRefusedError(61, f"refused {KEY}"), NansenTransportError, "NETWORK_ERROR"),
    (ConnectionResetError(54, f"reset {KEY}"), NansenTransportError, "NETWORK_ERROR"),
    (socket.gaierror(8, f"dns {KEY}"), NansenTransportError, "NETWORK_ERROR"),
    (SourceFailure(f"other {KEY}"), NansenTransportError, "TRANSPORT_FAILURE"),
])
def test_an_expected_transport_failure_maps_to_a_sanitized_nansen_error(raised, error_type, code) -> None:
    http = support.AuthoredHttp(raised)
    client = _client(http)
    with pytest.raises(NansenTransportError) as caught:
        client.call("holders", support.nansen.holder_body())
    error = caught.value
    assert type(error) is error_type
    assert error.code == code
    assert error.__cause__ is None and error.__context__ is None
    assert KEY not in str(error) and KEY not in repr(error) and KEY not in error.detail
    assert (error.status, error.request_id, error.quoted_credits, error.deducted_credits,
            error.response_sha256) == (None, None, None, None, None)
    assert len(http.calls) == 1
    # An unknown outcome keeps the client's conservative reservation.
    assert client.attempts == 1 and client.reserved_credits == Decimal("5")


@pytest.mark.parametrize("defect", [ClientConfigError("bad url"), RuntimeError("bug"), KeyError("k")])
def test_a_programmer_defect_propagates_unchanged(defect) -> None:
    with pytest.raises(type(defect)) as caught:
        support.adapter(support.AuthoredHttp(defect)).request(*HOLDERS, support.nansen.holder_body())
    assert caught.value is defect


def test_a_failure_after_a_success_yields_a_partial_report_with_no_duplicate_call() -> None:
    flows_body = support.nansen.flow_body()
    http = support.AuthoredHttp(support.reply(200, _holders_page()), SourceTimeout("lost reply"))
    run = run_research(support.nansen.request(), support.adapter(http),
                       clock=lambda: support.nansen.COLLECTED_AT)
    evidence = run.evidence
    assert evidence.holder is not None and evidence.flows is None
    assert evidence.stop_reason == "TIMEOUT"
    assert (evidence.attempts, evidence.pages, evidence.reserved_credits) == (2, 1, "6")
    assert [source.failure for source in evidence.sources] == [None, "TIMEOUT"]
    assert evidence.sources[1].request_body == flows_body and evidence.sources[1].request_id is None
    assert [call["url"] for call in http.calls] == ["https://api.nansen.ai/api/v1/tgm/holders",
                                                     "https://api.nansen.ai/api/v1/tgm/flows"]
    assert run.report.coverage.stop_reason == "TIMEOUT"


def test_the_client_request_cap_stops_dispatch_before_the_adapter() -> None:
    http = support.AuthoredHttp(support.reply(200, _holders_page(is_last_page=False)))
    run = run_research(support.nansen.request(operations=("holders",), limits=support.nansen.limits(max_requests=1)),
                       support.adapter(http), clock=lambda: support.nansen.COLLECTED_AT)
    assert run.evidence.stop_reason == "REQUEST_LIMIT"
    assert len(http.calls) == 1


def test_the_client_credit_cap_stops_dispatch_before_the_adapter() -> None:
    http = support.AuthoredHttp()
    run = run_research(support.nansen.request(operations=("holders",),
                                              limits=support.nansen.limits(max_credits=Decimal("4"))),
                       support.adapter(http), clock=lambda: support.nansen.COLLECTED_AT)
    assert run.evidence.stop_reason == "CREDIT_LIMIT"
    assert http.calls == []


# 19 + 120,000 + 2 = 120,021 bytes: inside both caps used below, but deeper than the
# standard JSON decoder accepts (it raises RecursionError, which the client does not catch).
TOO_DEEP_BODY = b'{"data":[],"extra":' + b"[" * 60_000 + b"0" + b"]" * 60_000 + b"}"


def test_a_reply_deeper_than_the_json_decoder_accepts_is_a_stable_contract_failure() -> None:
    assert len(TOO_DEEP_BODY) == 120_021
    http = support.AuthoredHttp(support.reply(200, TOO_DEEP_BODY, {"x-request-id": "req-deep"}))
    with pytest.raises(NansenContractError) as caught:
        support.adapter(http, max_response_bytes=150_000).request(*HOLDERS, support.nansen.holder_body())
    error = caught.value
    assert (error.code, error.status, error.response_sha256, error.request_id) == (
        "MALFORMED_PROVIDER_RESPONSE", 200, None, None)
    assert error.__cause__ is None and error.__context__ is None
    assert len(http.calls) == 1


def test_a_too_deep_flows_reply_after_holder_success_keeps_the_partial_report() -> None:
    http = support.AuthoredHttp(support.reply(200, _holders_page()), support.reply(200, TOO_DEEP_BODY))
    run = run_research(support.nansen.request(), support.adapter(http, max_response_bytes=150_000),
                       clock=lambda: support.nansen.COLLECTED_AT)
    evidence = run.evidence
    assert evidence.holder is not None and evidence.holder.rows[0].address == "0xaaa"
    assert evidence.flows is None
    assert evidence.stop_reason == "MALFORMED_PROVIDER_RESPONSE"
    assert (evidence.attempts, evidence.pages, evidence.reserved_credits) == (2, 1, "6")
    assert [(source.failure, source.response_sha256, source.request_id) for source in evidence.sources][1] == (
        "MALFORMED_PROVIDER_RESPONSE", None, None)
    assert [call["url"] for call in http.calls] == ["https://api.nansen.ai/api/v1/tgm/holders",
                                                     "https://api.nansen.ai/api/v1/tgm/flows"]
    assert run.report.coverage.stop_reason == "MALFORMED_PROVIDER_RESPONSE"


def test_an_ordinary_non_json_reply_still_reaches_the_client_with_its_original_hash() -> None:
    body = b"<html>not json</html>"
    http = support.AuthoredHttp(support.reply(200, body))
    client = _client(http)
    with pytest.raises(NansenContractError) as caught:
        client.call("holders", support.nansen.holder_body())
    assert caught.value.code == "MALFORMED_PROVIDER_RESPONSE"
    # sha256 of the literal bytes above, computed independently of the adapter and client.
    assert caught.value.response_sha256 == "0f33cce081ffd7bfbfbdbfe47c2a92cda157cb8bfc9a41bae2b59ff9855e742d"


def test_a_literal_key_echo_in_a_too_deep_reply_is_still_reported_as_an_echo() -> None:
    body = TOO_DEEP_BODY[:-1] + b', "debug": "' + KEY.encode() + b'"}'
    with pytest.raises(NansenContractError) as caught:
        support.adapter(support.AuthoredHttp(support.reply(200, body)), max_response_bytes=150_000).request(
            *HOLDERS, support.nansen.holder_body())
    assert caught.value.code == "CREDENTIAL_ECHO"
