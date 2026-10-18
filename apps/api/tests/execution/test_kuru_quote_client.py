"""Synthetic K2 wire examples. No response is a provider capture."""

import datetime as dt
import json
import socket
import pytest
from edge_os_api.execution.kuru_quote_client import KuruQuoteClient
from edge_os_api.execution.original_transaction import RpcError
from edge_os_api.research_history.http_clients.http_transport import HttpResponse




ADDRESS = "0x" + "1" * 40
BUY = "0x" + "2" * 40
USER = "0x" + "3" * 40
REQUEST = {"chain_id": 143, "sell_token": ADDRESS, "buy_token": BUY, "amount": "200", "user": USER}
NOW = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
REPLY = {"type": "quote", "status": "success", "output": "300", "minOut": "290",
         "transaction": {"to": ADDRESS, "calldata": "12345678", "value": "0"},
         "gasPrices": {"slow": "1", "standard": "2", "fast": "3", "rapid": "4", "extreme": "5"}}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


class Http:
    def __init__(self, reply=REPLY):
        self.reply, self.calls = reply, []
    def request(self, **request):
        self.calls.append(request)
        return HttpResponse(200, {}, json.dumps(self.reply).encode())


def client(http, request=None):
    return KuruQuoteClient(endpoint="https://quote.invalid/api/quote", bearer_token="synthetic-token-canary",
        accepted_request=request or REQUEST, slippage_bps=50, http=http, deadline_monotonic=20,
        connect_timeout_seconds=2, max_request_bytes=4096, max_response_bytes=4096,
        monotonic=lambda: 10, wall_clock=lambda: NOW, evidence_class="SYNTHETIC_FIXTURE")


def test_quote_binds_literal_wire_and_reports_local_availability_separately():
    http = Http()
    quote = client(http)
    assert http.calls == []
    assert quote.quote(REQUEST) == REPLY
    assert len(http.calls) == 1
    assert json.loads(http.calls[0]["body"]) == {
        "userAddress": USER, "tokenIn": ADDRESS, "tokenOut": BUY, "amount": "200", "slippageTolerance": 50}
    assert http.calls[0]["headers"]["authorization"] == "Bearer synthetic-token-canary"
    assert quote.observation.requested_at == NOW and quote.observation.received_at == NOW
    assert quote.observation.evidence_class == "SYNTHETIC_FIXTURE"
    assert quote.observation.provider_created_at is None
    assert "synthetic-token-canary" not in repr(quote)
    with pytest.raises(RpcError):
        quote.quote(REQUEST)
    assert len(http.calls) == 1


@pytest.mark.parametrize("change", [
    lambda r: r.update(buildResponse={}), lambda r: r.update(path=[]), lambda r: r.update(unrecognized="value"),
    lambda r: r.pop("output"), lambda r: r.update(output=True), lambda r: r.update(minOut="0300"),
    lambda r: r.update(minOut="301"), lambda r: r.update(status="error"),
    lambda r: r["transaction"].update(data="0x12345678"), lambda r: r["transaction"].update(value="1"),
    lambda r: r["transaction"].update(calldata="secret-canary"),
    lambda r: r["gasPrices"].update(standard=1.5), lambda r: r.update(type="synthetic-token-canary"),
])
def test_unsupported_or_contradictory_quote_never_gets_availability(change):
    reply = json.loads(json.dumps(REPLY))
    change(reply)
    http = Http(reply)
    quote = client(http)
    with pytest.raises(RpcError) as error:
        quote.quote(REQUEST)
    assert quote.observation is None
    assert "canary" not in repr(error.value)
    assert error.value.__context__ is None and error.value.__cause__ is None
    assert len(http.calls) == 1


@pytest.mark.parametrize("raw", [
    b'{"status":"success","status":"success"}', b'{"transaction":{"value":"0","value":"1"}}',
    b'"synthetic-token-canary"', b'\xff', b'[]', b'{' + b' ' * 4096 + b'}',
])
def test_malformed_quote_body_is_sanitized(raw):
    http = Http()
    def send(**request):
        http.calls.append(request)
        return HttpResponse(200, {}, raw)
    http.request = send
    with pytest.raises(RpcError) as error:
        client(http).quote(REQUEST)
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert "canary" not in repr(error.value)
    assert len(http.calls) == 1


def test_changed_request_cannot_send_and_original_mapping_is_owned():
    request = dict(REQUEST)
    http = Http()
    quote = client(http, request)
    request["amount"] = "201"
    with pytest.raises(RpcError):
        quote.quote(request)
    assert http.calls == []


@pytest.mark.parametrize("amount", [True, 200, 2.0, "0200", "-1", "0", None])
def test_request_amount_is_canonical_before_transport(amount):
    http = Http()
    with pytest.raises(ValueError):
        client(http, {**REQUEST, "amount": amount})
    assert http.calls == []
