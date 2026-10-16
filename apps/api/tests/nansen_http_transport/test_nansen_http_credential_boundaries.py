"""Credential boundaries the gate reproduced (D1 F1/F2).

F1: a reply whose standard JSON decoding reconstructs the key must be refused before
it reaches the client, the evidence or the report. F2: an expected-error code from
the HTTP layer reaches public errors and saved fields only when it is a known stable
code. Synthetic key and data only; the loopback case uses the owned 127.0.0.1 listener.
"""

from __future__ import annotations

import json
import traceback
from decimal import Decimal

import pytest

import nansen_http_support as support
from edge_os_api.nansen_research import (
    NansenClient,
    NansenContractError,
    NansenProviderError,
    run_research,
)
from edge_os_api.nansen_research.serialization import to_plain
from edge_os_api.research_history.http_clients.client_config import HttpProviderError
from edge_os_api.research_history.http_clients.http_transport import StdlibHttpTransport

KEY = support.SYNTHETIC_KEY  # "synthetic-nansen-key-7f3a9c"
# The same key as JSON text, with its first "s" written as a standard \u escape.
ESCAPED_KEY = b"\\u0073ynthetic-nansen-key-7f3a9c"
# Every character escaped.
FULLY_ESCAPED_KEY = b"".join(b"\\u%04x" % ord(character) for character in KEY)
HOLDER_ROW = b'{"address": "0xaaa", "token_amount": 1000, "ownership_percentage": 0.5, ' \
             b'"value_usd": null, "address_label": null}'
PAGINATION = b'"pagination": {"page": 1, "per_page": 100, "is_last_page": true}'


def _holders_with_warning(warning: bytes) -> bytes:
    return b'{"data": [' + HOLDER_ROW + b'], ' + PAGINATION + b', "warnings": ["' + warning + b'"]}'


def _visible(*values: object) -> str:
    return " ".join(repr(value) + str(value) for value in values)


@pytest.mark.parametrize("body", [
    _holders_with_warning(b"note " + ESCAPED_KEY),
    _holders_with_warning(FULLY_ESCAPED_KEY),
    _holders_with_warning(ESCAPED_KEY.upper().replace(b"\\U0073", b"\\u0053")),
    b'{"data": [], ' + PAGINATION + b', "debug": {"nested": [{"k": "' + ESCAPED_KEY + b'"}]}}',
    b'{"data": [], ' + PAGINATION + b', "' + ESCAPED_KEY + b'": 1}',
    b'{"code": "unauthenticated", "message": "bad key ' + ESCAPED_KEY + b'"}',
])
def test_a_json_escaped_key_echo_is_refused_before_the_client_sees_it(body: bytes) -> None:
    http = support.AuthoredHttp(support.reply(200, body))
    client = NansenClient(support.adapter(http), support.nansen.limits())
    with pytest.raises(NansenContractError) as caught:
        client.call("holders", support.nansen.holder_body())
    error = caught.value
    assert error.code == "CREDENTIAL_ECHO"
    assert (error.response_sha256, error.request_id) == (None, None)
    assert client.fetches == () and client.bytes_read == 0
    assert len(http.calls) == 1


def test_a_reply_that_only_resembles_the_key_keeps_its_original_bytes() -> None:
    body = _holders_with_warning(b"\\u0073ynthetic-nansen-key-0000")
    http = support.AuthoredHttp(support.reply(200, body))
    response = support.adapter(http).request("holders", "/api/v1/tgm/holders", support.nansen.holder_body())
    assert response.body == body


def test_the_first_consumer_keeps_no_escaped_key_in_evidence_report_or_hash() -> None:
    body = _holders_with_warning(b"note " + ESCAPED_KEY)
    http = support.AuthoredHttp(support.reply(200, body, {"x-request-id": "req-echo"}))
    run = run_research(support.nansen.request(operations=("holders",)), support.adapter(http),
                       clock=lambda: support.nansen.COLLECTED_AT)
    evidence = run.evidence
    assert evidence.holder is None
    assert evidence.stop_reason == "CREDENTIAL_ECHO"
    assert [(source.failure, source.response_sha256, source.request_id) for source in evidence.sources] == [
        ("CREDENTIAL_ECHO", None, None)]
    assert (evidence.attempts, evidence.pages, evidence.reserved_credits) == (1, 0, "5")
    saved = json.dumps(to_plain(evidence)) + json.dumps(to_plain(run.report))
    assert KEY not in saved and KEY not in _visible(evidence, run.report)
    assert len(http.calls) == 1


def test_a_real_loopback_reply_with_a_json_escape_is_refused_and_its_socket_closed() -> None:
    received: list[str] = []

    def listener(_method: str, path: str, _headers: dict, _body: bytes):
        received.append(path)
        return support.http_support.Reply(body=_holders_with_warning(b"note " + ESCAPED_KEY))

    with support.http_support.LoopbackServer(listener) as server:
        connector = support.LoopbackConnector(server)
        adapter = support.adapter(StdlibHttpTransport(connect=connector))
        run = run_research(support.nansen.request(operations=("holders",)), adapter,
                           clock=lambda: support.nansen.COLLECTED_AT)
    assert run.evidence.stop_reason == "CREDENTIAL_ECHO"
    assert run.evidence.holder is None
    assert [source.response_sha256 for source in run.evidence.sources] == [None]
    assert KEY not in json.dumps(to_plain(run.evidence)) + json.dumps(to_plain(run.report))
    assert received == ["/api/v1/tgm/holders"]
    assert len(connector.sockets) == 1 and connector.sockets[0].fileno() == -1


@pytest.mark.parametrize("code", [KEY, f"X_{KEY}", 7, None])
def test_an_unknown_http_error_code_is_replaced_by_a_fixed_code(code: object) -> None:
    raised = HttpProviderError("PLACEHOLDER", f"detail {KEY}")
    raised.code = code  # an injected transport may set any value here
    http = support.AuthoredHttp(raised)
    run = run_research(support.nansen.request(operations=("holders",)), support.adapter(http),
                       clock=lambda: support.nansen.COLLECTED_AT)
    evidence = run.evidence
    assert evidence.stop_reason == "UNRECOGNIZED_HTTP_FAILURE"
    assert [(source.failure, source.status, source.request_id) for source in evidence.sources] == [
        ("UNRECOGNIZED_HTTP_FAILURE", None, None)]
    assert (evidence.attempts, evidence.reserved_credits) == (1, "5")
    saved = json.dumps(to_plain(evidence)) + json.dumps(to_plain(run.report))
    assert KEY not in saved and KEY not in _visible(evidence, run.report)
    assert len(http.calls) == 1


def test_an_unknown_code_error_text_and_chain_never_carry_the_marker() -> None:
    raised = HttpProviderError(f"CODE_{KEY}", f"detail {KEY}")
    client = NansenClient(support.adapter(support.AuthoredHttp(raised)), support.nansen.limits())
    with pytest.raises(NansenProviderError) as caught:
        client.call("holders", support.nansen.holder_body())
    error = caught.value
    formatted = "".join(traceback.format_exception(error))
    assert error.code == "UNRECOGNIZED_HTTP_FAILURE"
    assert KEY not in _visible(error) and KEY not in error.detail and KEY not in formatted
    assert error.__cause__ is None and error.__context__ is None
    assert client.reserved_credits == Decimal("5")


@pytest.mark.parametrize("code, error_type", [
    ("OVERSIZED_RESPONSE", NansenContractError),
    ("MALFORMED_PROVIDER_RESPONSE", NansenContractError),
    ("UNSUPPORTED_CONTENT_ENCODING", NansenProviderError),
    ("REDIRECT_REFUSED", NansenProviderError),
    ("AUTH_DENIED", NansenProviderError),
    ("PAYMENT_REQUIRED", NansenProviderError),
    ("RATE_LIMITED", NansenProviderError),
    ("HTTP_STATUS", NansenProviderError),
])
def test_a_known_http_error_code_keeps_its_classification(code: str, error_type: type) -> None:
    http = support.AuthoredHttp(HttpProviderError(code, f"detail {KEY}"))
    with pytest.raises(error_type) as caught:
        support.adapter(http).request("holders", "/api/v1/tgm/holders", support.nansen.holder_body())
    assert type(caught.value) is error_type and caught.value.code == code
    assert KEY not in _visible(caught.value)
