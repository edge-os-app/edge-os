"""Synthetic observations, including the documented Monad gas-limit charge."""

import datetime as dt
import socket
import pytest
from eth_account import Account
from edge_os_api.execution.provider_observations import observe_monad_charge
from edge_os_api.core.provider_ports import ProviderUnavailable
from edge_os_api.execution.current_holdings import HoldingsUnavailable
from edge_os_api.execution.provider_observations import RpcHoldingsObserver, UnqualifiedDepositObserver, UnqualifiedRemovalObserver
from edge_os_api.funding.observation import ObservationUnavailable




NOW = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
BLOCK_HASH = "0x" + "2" * 64
TARGET = "0x" + "3" * 40


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


def original():
    # Published repeated-byte test key, used only for an offline synthetic envelope.
    key = "0x" + "46" * 32
    signed = Account.sign_transaction({"type": 2, "chainId": 143, "nonce": 0, "to": TARGET, "value": 0,
        "data": "0x12345678", "gas": 200000, "maxFeePerGas": 10, "maxPriorityFeePerGas": 2}, key)
    return {"wallet_address": Account.from_key(key).address, "chain_id": 143,
        "transaction_hash": "0x" + signed.hash.hex(), "signed_bytes": "0x" + signed.raw_transaction.hex(),
        "unsigned": {"type": 2, "chain_id": 143, "nonce": 0, "to": TARGET, "value": 0, "data": "0x12345678",
                     "gas_limit": 200000, "max_fee_per_gas": 10, "max_priority_fee_per_gas": 2}}


def receipt(envelope):
    return {"transactionHash": envelope["transaction_hash"], "from": envelope["wallet_address"], "to": TARGET,
            "blockHash": BLOCK_HASH, "blockNumber": "0x9", "status": "0x1", "gasUsed": "0x186a0", "effectiveGasPrice": "0x7"}


def charge(envelope=None, observed=None, **overrides):
    envelope = original() if envelope is None else envelope
    values = dict(original=envelope, receipt=receipt(envelope) if observed is None else observed,
        canonical_block={"number": "0x9", "hash": BLOCK_HASH, "baseFeePerGas": "0x5"},
        finalized_block={"number": "0xa", "hash": "0x" + "4" * 64},
        evidence_class="SYNTHETIC_FIXTURE", finality_qualified=True)
    return observe_monad_charge(**(values | overrides))


def test_monad_charges_original_signed_gas_limit_not_gas_used():
    result = charge()
    assert result.state == "OBSERVED" and result.raw == "1400000"
    assert result.gas_limit == 200000 and result.gas_used == 100000 and result.price_per_gas == 7
    assert result.evidence_class == "SYNTHETIC_FIXTURE"



@pytest.mark.parametrize("field,value", [("effectiveGasPrice", "0x8"), ("effectiveGasPrice", "0xb"),
    ("gasUsed", "0x30d41"), ("gasUsed", True), ("blockHash", "0x" + "5" * 64),
    ("transactionHash", "0x" + "6" * 64), ("from", TARGET), ("blockNumber", "0xb"), ("status", "0x2")])
def test_missing_or_conflicting_receipt_cannot_release_gas(field, value):
    envelope = original()
    observed = receipt(envelope)
    observed[field] = value
    result = charge(envelope, observed)
    assert result.state == "UNAVAILABLE" and result.raw is None


@pytest.mark.parametrize("change", [
    lambda e: e["unsigned"].pop("gas_limit"), lambda e: e["unsigned"].update(gas_limit=True),
    lambda e: e["unsigned"].update(gas_limit=100000), lambda e: e.update(signed_bytes="0xdeadbeef"),
    lambda e: e.update(chain_id=10143),
])
def test_charge_uses_original_signed_envelope_and_never_fills_missing_limit(change):
    envelope = original()
    change(envelope)
    result = charge(envelope)
    assert result.state == "UNAVAILABLE" and result.raw is None


def test_absent_or_unqualified_finality_does_not_settle_receipt():
    for overrides in ({"finality_qualified": False}, {"finalized_block": {}}, {"canonical_block": {}},
                      {"evidence_class": "PROVIDER_UNQUALIFIED"}, {"evidence_class": "ACTUAL"}):
        assert charge(**overrides).raw is None


def test_missing_deposit_and_signer_contracts_never_become_confirmed():
    with pytest.raises(ObservationUnavailable, match="ORIGINAL_REFERENCE_SCHEMA_UNQUALIFIED"):
        UnqualifiedDepositObserver().observe("wallet-a", 143)
    with pytest.raises(ProviderUnavailable, match="OWNER_WALLET_SIGNER_SCHEMA_UNQUALIFIED"):
        UnqualifiedRemovalObserver().observe(agent_id="agent-a", wallet_id="wallet-a", network_id="monad:143")


class Rpc:
    def __init__(self, *, chain="0x8f", decimals=6, balance=123, timestamp=None):
        self.calls, self.chain, self.decimals, self.balance = [], chain, decimals, balance
        self.timestamp = int(NOW.timestamp()) if timestamp is None else timestamp
    def call(self, method, params):
        self.calls.append((method, params))
        if method == "eth_chainId":
            return self.chain
        if method == "eth_getBlockByNumber":
            return {"number": "0x9", "timestamp": hex(self.timestamp), "hash": BLOCK_HASH}
        if method == "eth_call":
            value = self.decimals if len(params[0]["data"]) == 10 else self.balance
            return None if value is None else "0x" + format(value, "064x")
        raise AssertionError("unplanned read")


def holdings(rpc, **kwargs):
    return RpcHoldingsObserver(observer=rpc, wallet_address=TARGET, chain_id=143,
        assets=[("monad:143/0x" + "5" * 40, 6)], source="synthetic-observer", evidence_class="SYNTHETIC_FIXTURE",
        clock=lambda: NOW, finality_qualified=kwargs.get("finality_qualified", True))


def test_holdings_reuses_exact_finalized_raw_units_and_identity():
    rpc = Rpc()
    observed = holdings(rpc).read()
    assert observed.wallet_address == TARGET and observed.chain_id == 143 and observed.block_number == 9
    assert observed.observed_at == NOW and observed.finality == "FINALIZED"
    assert list(observed.assets.values())[0].raw == "123" and list(observed.assets.values())[0].decimals == 6
    assert rpc.calls[1] == ("eth_getBlockByNumber", ["finalized", False])
    assert all(params[-1] == "0x9" for method, params in rpc.calls if method == "eth_call")


@pytest.mark.parametrize("values", [{"chain": "0x279f"}, {"decimals": 18}, {"balance": None},
    {"timestamp": int(NOW.timestamp()) - 301}, {"timestamp": int(NOW.timestamp()) + 1}])
def test_partial_wrong_chain_decimal_stale_or_future_holdings_are_unavailable(values):
    with pytest.raises(HoldingsUnavailable):
        holdings(Rpc(**values)).read()


def test_unqualified_finality_makes_zero_holdings_calls():
    rpc = Rpc()
    with pytest.raises(HoldingsUnavailable):
        holdings(rpc, finality_qualified=False).read()
    assert rpc.calls == []


def test_holdings_owns_nested_asset_binding_before_read():
    asset = ["monad:143/0x" + "5" * 40, 6]
    assets = [asset]
    rpc = Rpc()
    observer = RpcHoldingsObserver(observer=rpc, wallet_address=TARGET, chain_id=143,
        assets=assets, source="synthetic-observer", evidence_class="SYNTHETIC_FIXTURE", clock=lambda: NOW,
        finality_qualified=True)
    asset[0] = "monad:143/0x" + "6" * 40
    observed = observer.read()
    assert list(observed.assets) == ["monad:143/0x" + "5" * 40]


def test_holdings_composes_the_role_bound_rpc_wire_client():
    import json
    from edge_os_api.execution.transaction_rpc_client import TransactionRpcClient
    from edge_os_api.execution.original_transaction import BALANCE_OF_SELECTOR, DECIMALS_SELECTOR
    from edge_os_api.research_history.http_clients.http_transport import HttpResponse
    token = "0x" + "5" * 40
    calls = []
    class Http:
        def request(self, **request):
            payload = json.loads(request["body"])
            calls.append(payload)
            results = ["0x8f", {"number": "0x9", "timestamp": hex(int(NOW.timestamp())), "hash": BLOCK_HASH},
                       "0x" + "0" * 63 + "6", "0x" + "0" * 62 + "7b"]
            return HttpResponse(200, {}, json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": results[payload["id"] - 1]}).encode())
    client = TransactionRpcClient(role="observer", destination_id="observer-a", endpoint="https://rpc.invalid/rpc",
        plan=[("eth_chainId", []), ("eth_getBlockByNumber", ["finalized", False]),
              ("eth_call", [{"to": token, "data": DECIMALS_SELECTOR}, "0x9"]),
              ("eth_call", [{"to": token, "data": BALANCE_OF_SELECTOR + "0" * 24 + TARGET[2:]}, "0x9"])],
        http=Http(), deadline_monotonic=20, connect_timeout_seconds=2, max_request_bytes=4096,
        max_response_bytes=4096, monotonic=lambda: 10)
    assert holdings(client).read().assets["monad:143/" + token].raw == "123"
    assert len(calls) == 4


@pytest.mark.parametrize("field,value", [("nonce", False), ("value", False), ("type", True), ("type", 4),
    ("authorization_list", [])])
def test_original_envelope_rejects_type_drift_even_when_python_values_compare_equal(field, value):
    envelope = original()
    envelope["unsigned"][field] = value
    result = charge(envelope)
    assert result.state == "UNAVAILABLE" and result.raw is None


@pytest.mark.parametrize("data", [305419896, b"\x12\x34\x56\x78", "12345678", "0x1234567", None])
def test_original_calldata_requires_an_even_length_prefixed_hex_string(data):
    envelope = original()
    envelope["unsigned"]["data"] = data
    result = charge(envelope)
    assert result.state == "UNAVAILABLE" and result.raw is None


def test_holdings_finality_is_bound_to_release_proof_and_block_hash(tmp_path):
    from execution.test_privy_signer import original as transport_fixture
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = transport_fixture(tmp_path, None)
    binding, approvals = bound_original(transport)
    rpc = Rpc(timestamp=int(transport._clock().timestamp()))
    reader = RpcHoldingsObserver(observer=rpc, wallet_address=transport._context.wallet_address, chain_id=143,
        assets=[(transport._context.sell.asset_id, 6)], source="observer-a", evidence_class="SYNTHETIC_FIXTURE",
        clock=transport._clock, binding=binding, synthetic_bindings=approvals)
    observed = reader.read()
    assert observed.source == "observer-a:" + BLOCK_HASH
    assert observed.assets[transport._context.sell.asset_id].raw == "123"
    reader = RpcHoldingsObserver(observer=rpc, wallet_address=transport._context.wallet_address, chain_id=143,
        assets=[(transport._context.sell.asset_id, 6)], source="observer-a", evidence_class="SYNTHETIC_FIXTURE",
        clock=transport._clock, binding=binding, synthetic_bindings={})
    before = len(rpc.calls)
    with pytest.raises(HoldingsUnavailable):
        reader.read()
    assert len(rpc.calls) == before
