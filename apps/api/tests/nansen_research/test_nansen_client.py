"""Public-seam tests for the bounded read-only Nansen client.

Everything is injected and offline: an authored transport and authored JSON
bodies. No network, credential or provider is touched.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

import nansen_fixtures as support
from edge_os_api.nansen_research import (
    NansenAuthError,
    NansenBudgetExhausted,
    NansenClient,
    NansenContext,
    NansenContractError,
    NansenPaymentRequired,
    NansenProviderError,
    NansenRateLimited,
    NansenRequestError,
    NansenLimitError,
    NansenResponse,
    NansenTimeout,
    NansenTransportError,
    RecordedNansenTransport,
)

SECRET = "apikey-should-never-leak-123"


def _holder_ok(headers: dict[str, str] | None = None) -> NansenResponse:
    return support.response(200, support.holder_payload([support.holder_row("0xaaa")]),
                            headers or {"X-Request-Id": "rid-1", "X-Nansen-Credits-Cost": "5",
                                        "X-Nansen-Credits-Used": "5"})


def test_unknown_operation_is_refused_before_any_call() -> None:
    transport = support.RecordingTransport([_holder_ok()])
    client = NansenClient(transport, support.limits())
    with pytest.raises(NansenRequestError) as info:
        client.call("balances", support.holder_body())
    assert info.value.code == "OPERATION_NOT_ALLOWED"
    assert transport.calls == []


def test_body_refuses_extra_field_and_wrong_chain() -> None:
    client = NansenClient(support.RecordingTransport([]), support.limits())
    with pytest.raises(NansenRequestError) as info:
        client.call("holders", {**support.holder_body(), "extra": 1})
    assert info.value.code == "BODY_NOT_ALLOWED"
    with pytest.raises(NansenRequestError) as info:
        client.call("holders", {**support.holder_body(), "chain": "ethereum"})
    assert info.value.code == "WRONG_NETWORK"


def test_premium_labels_are_never_allowed_and_pinned_false() -> None:
    client = NansenClient(support.RecordingTransport([]), support.limits())
    with pytest.raises(NansenRequestError) as info:
        client.call("holders", {**support.holder_body(), "premium_labels": True})
    assert info.value.code == "PREMIUM_NOT_ALLOWED"

    transport = support.RecordingTransport([_holder_ok()])
    client = NansenClient(transport, support.limits())
    client.call("holders", support.holder_body())
    assert transport.calls[0][2]["premium_labels"] is False


def test_request_cap_stops_before_dispatch() -> None:
    transport = support.RecordingTransport([_holder_ok(), _holder_ok()])
    client = NansenClient(transport, support.limits(max_requests=1))
    client.call("holders", support.holder_body())
    with pytest.raises(NansenBudgetExhausted) as info:
        client.call("holders", support.holder_body(page=2))
    assert info.value.code == "REQUEST_LIMIT"
    assert len(transport.calls) == 1


def test_credit_cap_stops_before_dispatch() -> None:
    transport = support.RecordingTransport([_holder_ok()])
    client = NansenClient(transport, support.limits(max_credits=Decimal("4")))
    with pytest.raises(NansenBudgetExhausted) as info:
        client.call("holders", support.holder_body())
    assert info.value.code == "CREDIT_LIMIT"
    assert transport.calls == []


def test_deadline_stops_before_dispatch() -> None:
    transport = support.RecordingTransport([_holder_ok()])
    client = NansenClient(transport, support.limits(deadline_utc="2026-10-07T09:00:00Z"),
                          clock=lambda: "2026-10-07T09:50:00Z")
    with pytest.raises(NansenTimeout) as info:
        client.call("holders", support.holder_body())
    assert info.value.code == "DEADLINE"
    assert transport.calls == []


def test_attempt_is_counted_before_a_raising_transport() -> None:
    transport = support.RecordingTransport([NansenProviderError("upstream_unavailable", "boom")])
    client = NansenClient(transport, support.limits())
    with pytest.raises(NansenTransportError):
        client.call("holders", support.holder_body())
    assert client.attempts == 1


def test_request_exhaustion_records_one_non_retried_call() -> None:
    transport = RecordedNansenTransport([])
    client = NansenClient(transport, support.limits())
    with pytest.raises(NansenTransportError) as info:
        client.call("holders", support.holder_body())
    assert info.value.code == "NO_RECORDED_RESPONSE"
    assert transport.remaining == 0


def test_status_errors_are_typed_and_sanitized() -> None:
    cases = [
        (401, NansenAuthError, "{\"code\":\"unauthenticated\"}"),
        (402, NansenPaymentRequired, "{\"code\":\"payment_required\"}"),
        (429, NansenRateLimited, "{\"code\":\"rate_limit_exceeded\"}"),
        (500, NansenProviderError, "{\"code\":\"internal_error\"}"),
    ]
    for status, expected, body in cases:
        secret_body = body.replace("{", "{\"secret\":\"" + SECRET + "\",")
        transport = support.RecordingTransport([
            support.raw_response(status, secret_body.encode(), {"X-Nansen-Credits-Cost": "5", "Set-Cookie": SECRET}),
        ])
        client = NansenClient(transport, support.limits())
        with pytest.raises(expected) as info:
            client.call("holders", support.holder_body())
        assert SECRET not in str(info.value)
    provider = None
    try:
        NansenClient(support.RecordingTransport([support.response(500, {"code": "internal_error"})]),
                     support.limits()).call("holders", support.holder_body())
    except NansenProviderError as error:
        provider = error
    assert provider is not None and provider.code == "internal_error"


def test_a_programmer_defect_is_not_mistaken_for_a_provider_failure() -> None:
    transport = support.RecordingTransport([ValueError("a real defect")])
    client = NansenClient(transport, support.limits())
    with pytest.raises(ValueError):
        client.call("holders", support.holder_body())


def test_oversized_response_is_refused_before_framing() -> None:
    transport = support.RecordingTransport([support.response(200, support.holder_payload([support.holder_row("0xaaa")]))])
    client = NansenClient(transport, support.limits(max_bytes=10))
    with pytest.raises(NansenContractError) as info:
        client.call("holders", support.holder_body())
    assert info.value.code == "OVERSIZED_RESPONSE"
    assert client.pages == 0


def test_malformed_and_non_object_responses_are_refused() -> None:
    for body in (b"not json", b"[1, 2, 3]"):
        client = NansenClient(support.RecordingTransport([support.raw_response(200, body)]), support.limits())
        with pytest.raises(NansenContractError) as info:
            client.call("holders", support.holder_body())
        assert info.value.code == "MALFORMED_PROVIDER_RESPONSE"


def test_a_non_response_transport_value_is_a_protocol_error() -> None:
    class BadTransport:
        def request(self, operation: str, path: str, body: dict) -> object:
            return {"not": "a response"}

    client = NansenClient(BadTransport(), support.limits())
    with pytest.raises(Exception) as info:
        client.call("holders", support.holder_body())
    assert getattr(info.value, "code", None) == "TRANSPORT_NOT_A_RESPONSE"


def test_credits_are_recorded_and_unallowlisted_headers_are_dropped() -> None:
    headers = {"X-Request-Id": "rid-9", "X-Nansen-Credits-Cost": "5", "X-Nansen-Credits-Used": "5",
               "X-Nansen-Credits-Remaining": "95", "Set-Cookie": SECRET, "Authorization": SECRET}
    transport = support.RecordingTransport([support.response(200, support.holder_payload([]), headers)])
    client = NansenClient(transport, support.limits())
    fetch = client.call("holders", support.holder_body())
    assert fetch.request_id == "rid-9"
    assert fetch.quoted_credits == "5"
    assert fetch.deducted_credits == "5"
    assert fetch.remaining_credits == "95"
    assert SECRET not in repr(fetch)


def test_context_rejects_a_wrong_network() -> None:
    with pytest.raises(NansenRequestError):
        NansenContext(network="ethereum").validate()


@pytest.mark.parametrize("overrides", [
    {"max_requests": 0}, {"max_pages": -1}, {"max_bytes": True}, {"per_page": 0},
    {"per_page": 1001}, {"max_credits": Decimal("0")}, {"max_credits": Decimal("NaN")},
    {"deadline_utc": 12345},
])
def test_invalid_limits_raise_the_documented_limit_error(overrides: dict) -> None:
    with pytest.raises(NansenLimitError) as info:
        NansenClient(support.RecordingTransport([]), support.limits(**overrides))
    assert info.value.code == "INVALID_LIMIT"


def test_offset_deadline_is_parsed_not_compared_as_text() -> None:
    transport = support.RecordingTransport([_holder_ok()])
    client = NansenClient(transport, support.limits(deadline_utc="2026-10-07T11:00:00+02:00"),
                          clock=lambda: "2026-10-07T09:50:00Z")
    with pytest.raises(NansenTimeout) as info:
        client.call("holders", support.holder_body())
    assert info.value.code == "DEADLINE"
    assert transport.calls == []


def test_rate_limit_retains_only_a_numeric_retry_after() -> None:
    for header, expected in (({"Retry-After": "12"}, "12"), ({"Retry-After": "soon"}, None)):
        transport = support.RecordingTransport([support.raw_response(429, b'{"code": "rate_limit_exceeded"}', header)])
        client = NansenClient(transport, support.limits())
        with pytest.raises(NansenRateLimited) as info:
            client.call("holders", support.holder_body())
        assert info.value.retry_after == expected


def test_from_dict_refuses_an_unexpected_field() -> None:
    model = support.request()
    poisoned = model.to_dict()
    poisoned["per_page"] = 50
    with pytest.raises(ValueError):
        type(model).from_dict(poisoned)
