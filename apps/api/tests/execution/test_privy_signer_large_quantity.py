"""Large-quantity wire form for the Privy sign-only adapter.

The accepted adapter used to refuse every quantity above 2**53 - 1 wei. The
approved policy cap is 70 MON, which is far above that bound. These tests pin the
reviewed replacement: a small quantity stays a JSON number, a quantity above
2**53 - 1 is sent as a canonical lowercase ``0x`` string with no leading zeros,
and the authorization payload carries the exact bytes that are sent.

Network and authorization are injected doubles. No socket, credential or real
wallet is used.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from eth_account import Account

from edge_os_api.execution.original_transaction import validate_signed
from edge_os_api.execution.privy_signer import PrivySignerClient, make_p256_authorizer
from edge_os_api.research_history.http_clients.http_transport import HttpResponse

APP_ID = "app-test-1"
APP_SECRET = "sentinel-secret-AbC123"
SIGNATURE = "c2lnbmF0dXJlLXNlbnRpbmVsLVh5Wg=="
WALLET_ID = "wallet_abc-123"
EXPIRY_MS = 1_790_000_000_000
NOW_MS = 1_789_999_990_000
DEADLINE = 1_000.0
TO = "0x1111111111111111111111111111111111111111"
CAP = 70 * 10**18
MAX_UINT256 = 2**256 - 1


class FakeHttp:
    def __init__(self, reply: HttpResponse) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes, timeout: float,
                deadline: float, max_response_bytes: int, cancel: Callable[[], bool] | None = None) -> HttpResponse:
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        return self.reply


class Authorizer:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: Mapping[str, Any]) -> str:
        self.payloads.append(copy.deepcopy(dict(payload)))
        return SIGNATURE


def signed_reply() -> HttpResponse:
    body = {"method": "eth_signTransaction",
            "data": {"signed_transaction": "0x" + "ab" * 100, "encoding": "rlp"}}
    return HttpResponse(status=200, headers={"content-type": "application/json"},
                        body=json.dumps(body).encode())


def client(http: FakeHttp, authorize: Authorizer) -> PrivySignerClient:
    return PrivySignerClient(
        app_id=APP_ID, app_secret=APP_SECRET, authorize=authorize, request_id="attempt-0001",
        request_expiry_ms=EXPIRY_MS, http=http, connect_timeout_seconds=5.0, deadline_monotonic=DEADLINE,
        max_response_bytes=16_384, wall_clock_ms=lambda: NOW_MS, monotonic=lambda: 10.0,
    )


def transaction(**overrides: Any) -> dict[str, Any]:
    value = {"type": 2, "chain_id": 143, "nonce": 0, "to": TO, "value": 0, "data": "0x",
             "gas_limit": 100_000, "max_fee_per_gas": 100_000_000_000,
             "max_priority_fee_per_gas": 2_000_000_000}
    value.update(overrides)
    return value


def body(**overrides: Any) -> dict[str, Any]:
    return {"method": "eth_signTransaction", "params": {"transaction": transaction(**overrides)}}


@pytest.mark.parametrize("value", [2**53, CAP, CAP + 1, MAX_UINT256])
def test_large_quantity_is_sent_as_canonical_hex(value: int) -> None:
    http, authorize = FakeHttp(signed_reply()), Authorizer()

    result = client(http, authorize).rpc(WALLET_ID, body(value=value))

    assert result == {"data": {"signed_transaction": "0x" + "ab" * 100, "encoding": "rlp"}}
    wire = json.loads(http.calls[0]["body"])
    sent = wire["params"]["transaction"]["value"]
    assert sent == hex(value)
    assert sent.startswith("0x") and sent == sent.lower()
    assert sent[2:] == sent[2:].lstrip("0")
    assert int(sent, 16) == value


@pytest.mark.parametrize("field,value", [
    ("gas_limit", 2**53),
    ("max_fee_per_gas", 2**64),
    ("max_priority_fee_per_gas", MAX_UINT256),
])
def test_large_gas_and_fee_fields_are_canonical_hex(field: str, value: int) -> None:
    http, authorize = FakeHttp(signed_reply()), Authorizer()

    client(http, authorize).rpc(WALLET_ID, body(**{field: value}))

    wire = json.loads(http.calls[0]["body"])
    assert wire["params"]["transaction"][field] == hex(value)


def test_small_quantity_stays_a_json_number() -> None:
    http, authorize = FakeHttp(signed_reply()), Authorizer()

    client(http, authorize).rpc(WALLET_ID, body(value=1))

    wire = json.loads(http.calls[0]["body"])
    assert wire["params"]["transaction"]["value"] == 1
    assert isinstance(wire["params"]["transaction"]["value"], int)


def test_authorization_payload_carries_the_exact_wire_body() -> None:
    http, authorize = FakeHttp(signed_reply()), Authorizer()

    client(http, authorize).rpc(WALLET_ID, body(value=CAP))

    payload = authorize.payloads[0]
    assert json.dumps(payload["body"], sort_keys=True, separators=(",", ":")).encode() == http.calls[0]["body"]
    assert payload["body"]["params"]["transaction"]["value"] == hex(CAP)


def _authorization_payload(value: object) -> dict[str, Any]:
    return {
        "version": 1,
        "method": "POST",
        "url": f"https://api.privy.io/v1/wallets/{WALLET_ID}/rpc",
        "body": body(**{"value": value}),
        "headers": {
            "privy-app-id": APP_ID,
            "privy-idempotency-key": "attempt-0001",
            "privy-request-expiry": str(EXPIRY_MS),
        },
    }


def test_authorizer_refuses_a_large_json_number() -> None:
    authorize = make_p256_authorizer(private_key=ec.generate_private_key(ec.SECP256R1()))

    with pytest.raises(ValueError):
        authorize(_authorization_payload(CAP))


def test_authorizer_signs_a_large_canonical_hex_string() -> None:
    authorize = make_p256_authorizer(private_key=ec.generate_private_key(ec.SECP256R1()))

    signature = authorize(_authorization_payload(hex(CAP)))

    assert isinstance(signature, str) and signature


@pytest.mark.parametrize("chain_id", ["0x8f", 2**53, 2**200, -1, True, 0])
def test_chain_id_stays_a_safe_integer(chain_id: object) -> None:
    http, authorize = FakeHttp(signed_reply()), Authorizer()

    result = client(http, authorize).rpc(WALLET_ID, body(chain_id=chain_id))

    assert result["error"]["code"] == "LOCAL_UNSENT"
    assert http.calls == []
    assert authorize.payloads == []


@pytest.mark.parametrize("value", [-1, True, False, 1.0, "0x1", "0x01", "0X1", "0xzz", "1", MAX_UINT256 + 1])
def test_non_integer_and_out_of_range_quantities_are_refused(value: object) -> None:
    http, authorize = FakeHttp(signed_reply()), Authorizer()

    result = client(http, authorize).rpc(WALLET_ID, body(**{"value": value}))

    assert result["error"]["code"] == "LOCAL_UNSENT"
    assert http.calls == []
    assert authorize.payloads == []


def test_signed_value_one_wei_above_the_unsigned_value_is_a_mismatch() -> None:
    account = Account.create()
    unsigned = {
        "type": 2, "chain_id": 143, "nonce": 0, "to": TO, "value": CAP, "data": "0x",
        "gas_limit": 100_000, "max_fee_per_gas": 100_000_000_000,
        "max_priority_fee_per_gas": 2_000_000_000,
    }
    signed = Account.sign_transaction({
        "type": 2, "chainId": 143, "nonce": 0, "to": TO, "value": CAP + 1, "data": "0x",
        "gas": 100_000, "maxFeePerGas": 100_000_000_000, "maxPriorityFeePerGas": 2_000_000_000,
    }, account.key)

    transaction_hash, reasons = validate_signed("0x" + signed.raw_transaction.hex(), unsigned, account.address)

    assert transaction_hash is None
    assert "SIGNED_VALUE_MISMATCH" in reasons


def test_signed_large_value_exactly_matches_the_unsigned_value() -> None:
    account = Account.create()
    unsigned = {
        "type": 2, "chain_id": 143, "nonce": 0, "to": TO, "value": CAP, "data": "0x",
        "gas_limit": 100_000, "max_fee_per_gas": 100_000_000_000,
        "max_priority_fee_per_gas": 2_000_000_000,
    }
    signed = Account.sign_transaction({
        "type": 2, "chainId": 143, "nonce": 0, "to": TO, "value": CAP, "data": "0x",
        "gas": 100_000, "maxFeePerGas": 100_000_000_000, "maxPriorityFeePerGas": 2_000_000_000,
    }, account.key)

    transaction_hash, reasons = validate_signed("0x" + signed.raw_transaction.hex(), unsigned, account.address)

    assert reasons == []
    assert transaction_hash is not None
