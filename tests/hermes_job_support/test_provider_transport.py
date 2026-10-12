"""The transport contract: what may leave, what the host adds, and what may come back. No process, socket or file.

The request below has the exact header names and envelope that pinned Hermes 54bc5e5 sent in the accepted P05 runs.
"""

from __future__ import annotations

import json

import pytest

from provider_transport import (
    HERMES_CLIENT_KEY, HERMES_CLIENT_URL, PhysicalRequest, TransportReply, TransportRoute, host_request,
    physical_refusal, reply_refusal,
)

ROUTE = TransportRoute(route_id="authored-local-1", kind="AUTHORED",
                       endpoint_url="https://authored-transport.invalid/v1/chat/completions", max_reply_bytes=65_536)
BODY = json.dumps({"model": "m", "messages": [{"role": "system", "content": "p"}, {"role": "user", "content": "t"}],
                   "max_tokens": 4096, "session_id": "p05-attempt-7"}).encode()
HEADERS = (("accept", "application/json"), ("accept-encoding", "gzip, deflate"),
           ("authorization", f"Bearer {HERMES_CLIENT_KEY}"), ("connection", "keep-alive"),
           ("content-length", str(len(BODY))), ("content-type", "application/json"), ("host", "fake-provider.invalid"),
           ("user-agent", "OpenAI/Python 2.8.1"), ("x-stainless-arch", "arm64"), ("x-stainless-async", "false"),
           ("x-stainless-lang", "python"), ("x-stainless-os", "Linux"), ("x-stainless-package-version", "2.8.1"),
           ("x-stainless-read-timeout", "3700"), ("x-stainless-retry-count", "0"), ("x-stainless-runtime", "CPython"),
           ("x-stainless-runtime-version", "3.14.0"))
SECRET = "sk-test-DUMMY-SENTINEL-9f3a71c2e8b54d06"


def request(**changes) -> PhysicalRequest:
    values = {"method": "POST", "url": HERMES_CLIENT_URL, "headers": HEADERS, "body": BODY} | changes
    return PhysicalRequest(**values)


def with_header(name: str, value: str | None) -> tuple[tuple[str, str], ...]:
    kept = tuple((key, val) for key, val in HEADERS if key != name)
    return kept if value is None else (*kept, (name, value))


def test_the_request_pinned_hermes_sends_for_this_attempt_is_admitted() -> None:
    assert physical_refusal(request(), "attempt-7", HERMES_CLIENT_URL) is None


@pytest.mark.parametrize("changes, reason", [
    ({"method": "GET"}, "method_not_post"),
    ({"url": HERMES_CLIENT_URL + "?stream=true"}, "url_not_as_configured"),
    ({"url": "https://other.invalid/v1/chat/completions"}, "url_not_as_configured"),
    ({"headers": with_header("accept", "text/event-stream")}, "streaming_not_permitted"),
    ({"headers": with_header("x-stainless-retry-count", "1")}, "sdk_retry_not_permitted"),
    ({"headers": with_header("x-stainless-retry-count", None)}, "sdk_retry_not_permitted"),
    ({"headers": with_header("openai-organization", "org-1")}, "header_not_permitted"),
    ({"headers": with_header("content-type", "text/plain")}, "body_not_json"),
    ({"headers": (*HEADERS, ("accept", "application/json"))}, "header_repeated"),
    ({"body": b"[1]"}, "body_not_a_json_object"),
    ({"body": BODY.replace(b"p05-attempt-7", b"p05-attempt-8")}, "attempt_not_as_configured"),
    ({"body": BODY.replace(b', "session_id": "p05-attempt-7"', b"")}, "attempt_not_as_configured"),
])
def test_a_request_that_differs_from_the_one_intended_physical_request_is_refused(changes, reason) -> None:
    assert physical_refusal(request(**changes), "attempt-7", HERMES_CLIENT_URL) == reason


def test_the_host_sends_its_own_endpoint_and_credential_and_the_exact_admitted_body() -> None:
    sent = host_request(request(), ROUTE, "attempt-7", SECRET)

    assert (sent.url, sent.body, sent.attempt_id, sent.route_id) == (ROUTE.endpoint_url, BODY, "attempt-7", ROUTE.route_id)
    assert dict(sent.headers) == {"accept": "application/json", "content-type": "application/json",
                                  "authorization": f"Bearer {SECRET}"}
    assert HERMES_CLIENT_KEY not in repr(sent.headers)


def test_without_a_host_credential_no_authorization_is_sent() -> None:
    assert "authorization" not in dict(host_request(request(), ROUTE, "attempt-7", None).headers)


@pytest.mark.parametrize("reply, reason", [
    (TransportReply(200, b'{"choices": []}'), None),
    (TransportReply(503, b'{"error": {"message": "busy"}}'), None),
    (TransportReply(200, b"x" * 65_537), "reply_too_large"),
    (TransportReply(200, b"not json"), "reply_not_a_json_object"),
    (TransportReply(200, b"[]"), "reply_not_a_json_object"),
    (TransportReply(99, b"{}"), "reply_status_invalid"),
    (TransportReply(True, b"{}"), "reply_status_invalid"),
])
def test_only_a_bounded_reply_reaches_hermes(reply, reason) -> None:
    assert reply_refusal(reply, ROUTE) == reason


@pytest.mark.parametrize("values", [
    {"kind": "LIVE"}, {"endpoint_url": "http://plain.invalid/v1/chat/completions"},
    {"endpoint_url": "https://user:pw@host.invalid/v1"}, {"endpoint_url": "https://host.invalid/v1?key=1"},
    {"max_reply_bytes": 0}, {"max_reply_bytes": 2 * 1024 * 1024}, {"route_id": "has space"},
])
def test_a_route_that_is_not_exactly_a_bounded_https_endpoint_is_refused(values) -> None:
    fields = {"route_id": "r1", "kind": "AUTHORED", "endpoint_url": "https://a.invalid/v1/chat/completions",
              "max_reply_bytes": 1024} | values
    with pytest.raises(ValueError):
        TransportRoute(**fields)


def test_a_route_round_trips_through_the_job_settings() -> None:
    assert TransportRoute.from_settings(json.loads(json.dumps(ROUTE.settings()))) == ROUTE
