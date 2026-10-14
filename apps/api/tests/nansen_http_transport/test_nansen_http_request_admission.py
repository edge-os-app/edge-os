"""Request admission for the Nansen HTTP transport: configuration, route, body and pre-dispatch stops."""

from __future__ import annotations

import math
import time
from decimal import Decimal

import pytest

import nansen_http_support as support
from edge_os_api.nansen_research import (
    NansenCancelled,
    NansenInputError,
    NansenLimitError,
    NansenRequestError,
    NansenTimeout,
    NansenTransport,
)

HOLDER_BYTES = (
    b'{"aggregate_by_entity":false,"chain":"monad","label_type":"all_holders",'
    b'"order_by":[{"direction":"DESC","field":"token_amount"}],"pagination":{"page":1,"per_page":100},'
    b'"token_address":"0xd8e004acba279417c04c0633cb5a21ceca207777"}'
)


def test_holders_request_sends_one_exact_post_to_the_fixed_origin() -> None:
    http = support.AuthoredHttp(support.reply(200, b'{"data": []}', {"x-request-id": "req-1"}))
    deadline = time.monotonic() + 30.0
    transport = support.adapter(http, deadline_monotonic=deadline)

    response = transport.request("holders", "/api/v1/tgm/holders", support.nansen.holder_body())

    assert isinstance(transport, NansenTransport)
    assert (response.status, response.body, dict(response.headers)) == (200, b'{"data": []}', {"x-request-id": "req-1"})
    assert http.calls == [{
        "method": "POST",
        "url": "https://api.nansen.ai/api/v1/tgm/holders",
        "headers": {"apikey": support.SYNTHETIC_KEY, "content-type": "application/json",
                    "accept": "application/json"},
        "body": HOLDER_BYTES,
        "timeout": 2.0,
        "deadline": deadline,
        "max_response_bytes": 65_536,
        "cancel": None,
    }]


def test_flows_request_uses_the_flows_path_and_the_same_absolute_deadline() -> None:
    http = support.AuthoredHttp(support.reply(), support.reply())
    deadline = time.monotonic() + 30.0
    transport = support.adapter(http, deadline_monotonic=deadline)

    transport.request("flows", "/api/v1/tgm/flows", support.nansen.flow_body())
    transport.request("flows", "/api/v1/tgm/flows", support.nansen.flow_body(page=2))

    assert [call["url"] for call in http.calls] == ["https://api.nansen.ai/api/v1/tgm/flows"] * 2
    assert [call["deadline"] for call in http.calls] == [deadline, deadline]


@pytest.mark.parametrize("operation, path", [
    ("holders", "/api/v1/tgm/flows"),
    ("flows", "/api/v1/tgm/holders"),
    ("flow-intelligence", "/api/v1/tgm/flow-intelligence"),
    ("holders", "/api/v1/tgm/holders?page=2"),
    ("holders", "/api/v1/tgm/holders#x"),
    ("holders", "/api/v1/tgm/../tgm/holders"),
    ("holders", "https://evil.example/api/v1/tgm/holders"),
    ("holders", "//evil.example/api/v1/tgm/holders"),
    ("holders", "/api/v1/tgm/holders/"),
    ("holders", " /api/v1/tgm/holders"),
])
def test_a_wrong_or_injected_route_is_refused_before_any_dispatch(operation: str, path: str) -> None:
    http = support.AuthoredHttp()
    with pytest.raises(NansenRequestError) as caught:
        support.adapter(http).request(operation, path, support.nansen.holder_body())
    assert caught.value.code == "ROUTE_NOT_ALLOWED"
    assert http.calls == []


@pytest.mark.parametrize("key", [None, "", "  ", "key with space", "key\nline", "kéy", b"bytes-key", 7])
def test_a_missing_or_unsafe_key_is_refused_without_echo(key: object) -> None:
    with pytest.raises(NansenInputError) as caught:
        support.adapter(support.AuthoredHttp(), api_key=key)
    assert caught.value.code == "INVALID_CREDENTIAL"
    if isinstance(key, str) and key.strip():
        assert key not in str(caught.value)


def test_an_object_that_is_not_an_http_transport_is_refused() -> None:
    with pytest.raises(NansenInputError) as caught:
        support.adapter(object())
    assert caught.value.code == "INVALID_TRANSPORT"


@pytest.mark.parametrize("field, value", [
    ("connect_timeout_seconds", 0), ("connect_timeout_seconds", -1.0), ("connect_timeout_seconds", math.nan),
    ("connect_timeout_seconds", math.inf), ("connect_timeout_seconds", True), ("connect_timeout_seconds", "2"),
    ("connect_timeout_seconds", None),
    ("deadline_monotonic", math.nan), ("deadline_monotonic", math.inf), ("deadline_monotonic", True),
    ("deadline_monotonic", None), ("deadline_monotonic", "10"),
    ("max_request_bytes", 0), ("max_request_bytes", -5), ("max_request_bytes", True),
    ("max_request_bytes", 10.0), ("max_request_bytes", None),
    ("max_response_bytes", 0), ("max_response_bytes", False), ("max_response_bytes", 1.5),
    ("max_response_bytes", None),
    ("cancel", "not-callable"),
])
def test_an_invalid_or_missing_bound_is_refused(field: str, value: object) -> None:
    with pytest.raises(NansenLimitError):
        support.adapter(support.AuthoredHttp(), **{field: value})


def test_construction_has_no_unlimited_default() -> None:
    with pytest.raises(TypeError):
        support.NansenHttpTransport(api_key=support.SYNTHETIC_KEY, http=support.AuthoredHttp())


@pytest.mark.parametrize("body", [
    {"chain": "monad", "filters": {"value_usd": {"min": Decimal("NaN")}}},
    {"chain": "monad", "filters": {"value_usd": {"min": Decimal("Infinity")}}},
    {"chain": "monad", "filters": {"value_usd": {"min": float("nan")}}},
    {"chain": "monad", "filters": {"value_usd": {"min": float("inf")}}},
    {"chain": "monad", "filters": {"value_usd": {"min": 0.5}}},
    {"chain": "monad", "token_address": object()},
    {1: "non-text key"},
])
def test_a_body_that_is_not_canonical_finite_json_is_refused_before_dispatch(body: dict) -> None:
    http = support.AuthoredHttp()
    with pytest.raises(NansenRequestError) as caught:
        support.adapter(http).request("holders", "/api/v1/tgm/holders", body)
    assert caught.value.code == "BODY_NOT_SERIALIZABLE"
    assert http.calls == []


def test_a_body_that_is_not_a_mapping_is_refused_before_dispatch() -> None:
    http = support.AuthoredHttp()
    with pytest.raises(NansenRequestError) as caught:
        support.adapter(http).request("holders", "/api/v1/tgm/holders", ["chain", "monad"])  # type: ignore[arg-type]
    assert caught.value.code == "BODY_NOT_SERIALIZABLE"
    assert http.calls == []


def test_an_oversized_request_is_refused_before_dispatch_and_the_exact_limit_is_admitted() -> None:
    http = support.AuthoredHttp(support.reply())
    with pytest.raises(NansenRequestError) as caught:
        support.adapter(http, max_request_bytes=len(HOLDER_BYTES) - 1).request(
            "holders", "/api/v1/tgm/holders", support.nansen.holder_body())
    assert caught.value.code == "REQUEST_TOO_LARGE"
    assert http.calls == []

    support.adapter(http, max_request_bytes=len(HOLDER_BYTES)).request(
        "holders", "/api/v1/tgm/holders", support.nansen.holder_body())
    assert [call["body"] for call in http.calls] == [HOLDER_BYTES]


def test_an_already_passed_deadline_makes_zero_transport_attempts() -> None:
    http = support.AuthoredHttp(support.reply())
    transport = support.adapter(http, deadline_monotonic=time.monotonic() - 0.001)
    with pytest.raises(NansenTimeout) as caught:
        transport.request("holders", "/api/v1/tgm/holders", support.nansen.holder_body())
    assert caught.value.code == "DEADLINE"
    assert (caught.value.status, caught.value.request_id, caught.value.response_sha256) == (None, None, None)
    assert http.calls == []


def test_a_pre_cancelled_call_makes_zero_transport_attempts() -> None:
    http = support.AuthoredHttp(support.reply())
    transport = support.adapter(http, cancel=lambda: True)
    with pytest.raises(NansenCancelled) as caught:
        transport.request("flows", "/api/v1/tgm/flows", support.nansen.flow_body())
    assert caught.value.code == "CANCELLED"
    assert http.calls == []


def test_the_cancel_flag_is_handed_to_the_http_transport_for_in_flight_checks() -> None:
    flag = {"set": False}

    def cancel() -> bool:
        return flag["set"]

    http = support.AuthoredHttp(support.reply())
    support.adapter(http, cancel=cancel).request("flows", "/api/v1/tgm/flows", support.nansen.flow_body())
    assert http.calls[0]["cancel"] is cancel


def test_construction_and_representation_never_expose_the_key() -> None:
    transport = support.adapter(support.AuthoredHttp())
    assert support.SYNTHETIC_KEY not in repr(transport)
    assert support.SYNTHETIC_KEY not in str(transport)
    assert "https://api.nansen.ai" in repr(transport)
