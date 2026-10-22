"""Direct V2 program quote source: release pins, one reserves read, local calldata.

Every reply is synthetic. Nothing here signs, sends, reads a credential or uses a network.
"""
from __future__ import annotations

import json
import socket

import pytest

from edge_os_api.execution.direct_route_quote_client import (
    DIRECT_QUOTE_SOURCE,
    RESERVES_SELECTOR,
    DirectRoutePins,
    DirectRouteQuoteClient,
    build_calldata_hex,
    build_program_hex,
)
from edge_os_api.execution.operating_release import OperatingRelease, ReleaseRefused
from edge_os_api.kuru_flow.flow_calldata import decode_flow_call
from edge_os_api.research_history.http_clients.http_transport import HttpResponse

from execution.test_operating_release import definition

INPUT = "0x" + "2" * 40
OUTPUT = "0x" + "3" * 40
POOL = "0x" + "9" * 40
ENTRYPOINT = "0x" + "5" * 40
USER = "0x" + "1" * 40
AMOUNT = 200
MINIMUM = 100
FEE_PPM = 16000
WMON = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"
MOE = "0xd8e004acba279417c04c0633cb5a21ceca207777"
NAD_POOL = "0x97199b34564911936bc850ac45ede785892b5aad"

EXAMPLE_CALLDATA = (
    "0xce1e7030"
    "000000000000000000000000d8e004acba279417c04c0633cb5a21ceca207777"
    "0000000000000000000000000000000000000000000000000000000000000001"
    "0000000000000000000000003bd359c1119da7da1d913d1c4d2b7c461115433a"
    "000000000000000000000000000000000000000000000002b5e3af16b1880000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000140"
    "0000000000000000000000000000000000000000000000000000000000000031"
    "023bd359c1119da7da1d913d1c4d2b7c461115433a01ffff0097199b34564911936bc850ac45ede785892b5aad00003e80"
    "000000000000000000000000000000"
)


def independent_program(input_token: str, pool: str, direction: int, fee_ppm: int) -> str:
    raw = (bytes([0x02]) + bytes.fromhex(input_token[2:]) + bytes([0x01])
           + (0xFFFF).to_bytes(2, "big") + bytes([0x00]) + bytes.fromhex(pool[2:])
           + bytes([direction]) + fee_ppm.to_bytes(3, "big"))
    return "0x" + raw.hex()


def direct_definition() -> dict:
    source = definition()
    source["route"]["selector"] = "0xce1e7030"
    source["route"]["approved_program_hex"] = independent_program(INPUT, POOL, 0, FEE_PPM)
    source["route"]["approved_min_output_raw"] = str(MINIMUM)
    source["quote"] = {
        "source": DIRECT_QUOTE_SOURCE, "endpoint": "https://quote.invalid/rpc", "slippage_bps": 500,
        "pool_address": POOL, "token0_address": INPUT, "token1_address": OUTPUT,
        "direction": 0, "program_fee_ppm": FEE_PPM,
    }
    return source


def direct_pins(**changes) -> DirectRoutePins:
    values = dict(
        endpoint="https://quote.invalid/rpc", pool_address=POOL, token0_address=INPUT, token1_address=OUTPUT,
        direction=0, program_fee_ppm=FEE_PPM,
        approved_program_hex=independent_program(INPUT, POOL, 0, FEE_PPM),
        approved_input_raw=str(AMOUNT), approved_min_output_raw=str(MINIMUM),
        entrypoint_address=ENTRYPOINT, input_token=INPUT, output_token=OUTPUT)
    values.update(changes)
    return DirectRoutePins(**values)


def word(value: int) -> str:
    return format(value, "064x")


def reserves_reply(reserve0: int, reserve1: int) -> str:
    return "0x" + word(reserve0) + word(reserve1) + word(1_700_000_000)


class Http:
    def __init__(self, result: str = reserves_reply(10**18, 10**18), *, body: bytes | None = None, reply_id: int = 1):
        self.result, self.body, self.reply_id = result, body, reply_id
        self.calls = []

    def request(self, **request):
        self.calls.append(request)
        body = self.body
        if body is None:
            body = json.dumps({"jsonrpc": "2.0", "id": self.reply_id, "result": self.result}).encode()
        return HttpResponse(200, {}, body)


def client(http: Http, pins: DirectRoutePins | None = None, **changes) -> DirectRouteQuoteClient:
    values = dict(deadline_monotonic=40.0, connect_timeout_seconds=2, max_request_bytes=4096,
                  max_response_bytes=4096, evidence_class="SYNTHETIC_FIXTURE",
                  monotonic=lambda: 10.0)
    values.update(changes)
    return DirectRouteQuoteClient(pins or direct_pins(), accepted_request={
        "chain_id": 143, "sell_token": INPUT, "buy_token": OUTPUT, "amount": str(AMOUNT), "user": USER,
    }, slippage_bps=500, http=http, **values)


def expected_output(reserve0: int, reserve1: int, amount: int = AMOUNT, fee: int = FEE_PPM, direction: int = 0) -> int:
    r_in, r_out = (reserve0, reserve1) if direction == 0 else (reserve1, reserve0)
    return amount * (10**6 - fee) * r_out // (r_in * 10**6 + amount * (10**6 - fee))


def request() -> dict:
    return {"chain_id": 143, "sell_token": INPUT, "buy_token": OUTPUT, "amount": str(AMOUNT), "user": USER}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


def test_direct_release_accepts_only_the_pinned_program():
    release = OperatingRelease(direct_definition())
    assert release.content()["quote"]["source"] == DIRECT_QUOTE_SOURCE


@pytest.mark.parametrize("change", [
    lambda d: d["route"].update(approved_program_hex="0x" + "00" * 32),
    lambda d: d["quote"].update(pool_address="0x" + "8" * 40),
    lambda d: d["quote"].update(program_fee_ppm=3000),
    lambda d: d["quote"].update(program_fee_ppm=10**6),
    lambda d: d["quote"].update(direction=1),
    lambda d: d["quote"].update(token0_address=OUTPUT, token1_address=INPUT),
    lambda d: d["quote"].update(token0_address=OUTPUT),
    lambda d: d["quote"].update(extra="value"),
    lambda d: d["quote"].pop("pool_address"),
    lambda d: d["quote"].update(slippage_bps=0),
    lambda d: d["quote"].update(endpoint="https://quote.invalid/api/quote"),
    lambda d: d["quote"].update(program_fee_ppm=True),
    lambda d: d["quote"].update(source="DIRECT_UNKNOWN"),
    lambda d: d["route"].update(selector="0x12345678"),
    lambda d: d["route"].update(method="EXECUTE_SWAP_WITH_RECEIVER"),
])
def test_direct_release_refuses_drift(change):
    source = direct_definition()
    change(source)
    with pytest.raises(ReleaseRefused):
        OperatingRelease(source)


def test_the_existing_kuru_api_release_stays_valid():
    release = OperatingRelease(definition())
    assert "source" not in release.content()["quote"]


def test_calldata_matches_the_independent_evidence_example_byte_for_byte():
    pins = DirectRoutePins(
        endpoint="https://quote.invalid/rpc", pool_address=NAD_POOL, token0_address=WMON, token1_address=MOE,
        direction=0, program_fee_ppm=16000,
        approved_program_hex=independent_program(WMON, NAD_POOL, 0, 16000),
        approved_input_raw=str(50 * 10**18), approved_min_output_raw="1",
        entrypoint_address=ENTRYPOINT, input_token=WMON, output_token=MOE)
    assert build_program_hex(input_token=WMON, pool_address=NAD_POOL, direction=0, fee_ppm=16000) == (
        "0x023bd359c1119da7da1d913d1c4d2b7c461115433a01ffff0097199b34564911936bc850ac45ede785892b5aad00003e80")
    assert build_calldata_hex(pins) == EXAMPLE_CALLDATA


def test_local_calldata_round_trips_every_release_field():
    pins = direct_pins()
    data = build_calldata_hex(pins)
    call = decode_flow_call(data_hex=data, method="EXECUTE_SWAP")
    assert call.selector == "0xce1e7030"
    assert call.program_hex == pins.approved_program_hex
    assert call.intent.token_user_buys.lower() == OUTPUT
    assert call.intent.token_user_sells.lower() == INPUT
    assert call.intent.min_amount_user_buys == str(MINIMUM)
    assert call.intent.amount_user_sells == str(AMOUNT)
    assert call.fees.model_dump(mode="json") == {
        "fee_collector_address": "0x" + "0" * 40, "fee_bps": 0,
        "referrer_address": "0x" + "0" * 40, "referrer_fee_bps": 0, "is_in_token_fee": False}


def test_one_reserves_read_computes_output_and_keeps_the_approved_minimum():
    http = Http()
    quote = client(http)
    reply = quote.quote(request())
    assert len(http.calls) == 1
    sent = json.loads(http.calls[0]["body"])
    assert sent == {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                    "params": [{"to": POOL, "data": RESERVES_SELECTOR}, "latest"]}
    assert "authorization" not in http.calls[0]["headers"]
    assert reply["output"] == str(expected_output(10**18, 10**18))
    assert reply["minOut"] == str(MINIMUM)
    assert reply["transaction"]["to"] == ENTRYPOINT
    assert reply["transaction"]["value"] == "0"
    assert reply["transaction"]["calldata"] == build_calldata_hex(direct_pins())
    assert quote.observation.evidence_class == "SYNTHETIC_FIXTURE"
    with pytest.raises(Exception):
        quote.quote(request())
    assert len(http.calls) == 1


def test_direction_one_reads_the_orders_in_reverse():
    pins = direct_pins(direction=1, token0_address=OUTPUT, token1_address=INPUT,
                       approved_program_hex=independent_program(INPUT, POOL, 1, FEE_PPM))
    http = Http(reserves_reply(10**18, 10**18))
    reply = client(http, pins).quote(request())
    assert reply["output"] == str(expected_output(10**18, 10**18, direction=1))


@pytest.mark.parametrize("result", [
    "0x" + word(1) + word(1),
    "00" + word(1) + word(1) + word(1),
    "0x" + "zz" * 96,
    "0x",
])
def test_malformed_reserves_are_refused_without_an_observation(result):
    quote = client(Http(result))
    with pytest.raises(Exception):
        quote.quote(request())
    assert quote.observation is None


def test_zero_reserves_are_refused():
    quote = client(Http(reserves_reply(0, 10**18)))
    with pytest.raises(Exception):
        quote.quote(request())
    assert quote.observation is None


def test_slippage_refusal_never_returns_calldata_or_an_observation():
    source = direct_pins(approved_min_output_raw="500")
    quote = DirectRouteQuoteClient(source, accepted_request=request(), slippage_bps=500, http=Http(),
                                   deadline_monotonic=40.0, connect_timeout_seconds=2, max_request_bytes=4096,
                                   max_response_bytes=4096, evidence_class="SYNTHETIC_FIXTURE",
                                   monotonic=lambda: 10.0)
    with pytest.raises(Exception) as error:
        quote.quote(request())
    assert "SLIPPAGE" in str(error.value)
    assert quote.observation is None


def test_a_wrong_accepted_request_costs_no_read():
    http = Http()
    quote = client(http)
    wrong = {**request(), "amount": "201"}
    with pytest.raises(Exception):
        quote.quote(wrong)
    assert http.calls == []
    assert quote.observation is None


def test_stop_before_send_and_after_reply_are_both_refused():
    before = client(Http(), cancel=lambda: True)
    with pytest.raises(Exception):
        before.quote(request())
    assert before.observation is None

    ticks = iter([10.0, 41.0, 41.0, 41.0])
    after = client(Http(), monotonic=lambda: next(ticks))
    with pytest.raises(Exception):
        after.quote(request())
    assert after.observation is None


def test_oversized_or_mismatched_replies_are_refused():
    quote = client(Http(body=b"x" * 5000))
    with pytest.raises(Exception):
        quote.quote(request())
    quote = client(Http(reply_id=2))
    with pytest.raises(Exception):
        quote.quote(request())


@pytest.mark.parametrize("change", [
    lambda p: p.update(direction=2),
    lambda p: p.update(direction=1),
    lambda p: p.update(token0_address=OUTPUT, token1_address=INPUT),
    lambda p: p.update(program_fee_ppm=0),
    lambda p: p.update(program_fee_ppm=10**6),
    lambda p: p.update(program_fee_ppm=0x1000000),
    lambda p: p.update(approved_program_hex="0xdeadbeef"),
    lambda p: p.update(endpoint="https://quote.invalid/api/quote"),
    lambda p: p.update(approved_min_output_raw="0"),
    lambda p: p.update(input_token=OUTPUT),
])
def test_direct_pins_refuse_inconsistent_values(change):
    values = dict(endpoint="https://quote.invalid/rpc", pool_address=POOL, token0_address=INPUT,
                  token1_address=OUTPUT, direction=0, program_fee_ppm=FEE_PPM,
                  approved_program_hex=independent_program(INPUT, POOL, 0, FEE_PPM),
                  approved_input_raw=str(AMOUNT), approved_min_output_raw=str(MINIMUM),
                  entrypoint_address=ENTRYPOINT, input_token=INPUT, output_token=OUTPUT)
    change(values)
    with pytest.raises(ValueError):
        DirectRoutePins(**values)
