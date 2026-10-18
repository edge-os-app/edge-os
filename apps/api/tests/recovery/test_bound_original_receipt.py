"""A release-bound receipt needs canonical finality and the full saved signed original."""
import dataclasses

import pytest

from edge_os_api.execution.original_transaction import OriginalTransactionTransport, read_original_receipt
from execution.test_privy_signer import original, submit, client, FakeHttp, signed_reply, recorded_signature
from execution.test_saved_attempt_signing import bound_original

BLOCK = "0x" + "ab" * 32
FINAL = "0x" + "cd" * 32


def submitted_original(tmp_path):
    transport, recordings, stages = original(tmp_path, client(FakeHttp(signed_reply(recorded_signature("ENTRY", 0)))))
    binding, approvals = bound_original(transport)
    transport = OriginalTransactionTransport(dataclasses.replace(transport._context, identity=binding.identity()),
        transport._clients, transport._profile, controls=lambda: [], clock=transport._clock,
        binding=binding, synthetic_bindings=approvals)
    assert submit(transport, stages).detail == "BROADCAST_RETURNED"
    envelope = {}
    for _, values in stages:
        envelope.update(values)
    receipt = dict(recordings.data["receipts"][envelope["transaction_hash"]])
    receipt["blockHash"] = BLOCK
    receipt["transactionIndex"] = "0x0"
    receipt["logs"] = [{**log, "blockNumber": receipt["blockNumber"], "blockHash": BLOCK,
                        "transactionHash": envelope["transaction_hash"], "transactionIndex": "0x0",
                        "logIndex": hex(i), "removed": False} for i, log in enumerate(receipt["logs"])]
    return envelope, binding, approvals, receipt


class Observer:
    def __init__(self, receipt, *, canonical=BLOCK, final_number="0x1e8482", final_hash=FINAL):
        self.receipt, self.canonical, self.final_number, self.final_hash = receipt, canonical, final_number, final_hash
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "eth_chainId":
            return "0x8f"
        if method == "eth_getTransactionReceipt":
            return self.receipt
        assert method == "eth_getBlockByNumber"
        if params == ["finalized", False]:
            return {"number": self.final_number, "hash": self.final_hash}
        assert params == [self.receipt["blockNumber"], False]
        return {"number": self.receipt["blockNumber"], "hash": self.canonical, "baseFeePerGas": "0x3b9aca00"}


def test_bound_settlement_uses_signed_gas_limit_with_canonical_finality(tmp_path):
    envelope, binding, approvals, receipt = submitted_original(tmp_path)
    observer = Observer(receipt)
    result = read_original_receipt(envelope, observer, binding=binding, synthetic_bindings=approvals)
    assert result.outcome == "CONFIRMED"
    assert result.verdict.actual_gas.raw == "600000000000000"
    assert receipt["gasUsed"] == "0x249f0"
    assert observer.calls == [("eth_chainId", []), ("eth_getTransactionReceipt", [envelope["transaction_hash"]]),
        ("eth_getBlockByNumber", ["finalized", False]), ("eth_getBlockByNumber", [receipt["blockNumber"], False])]


@pytest.mark.parametrize("case", ["canonical", "not-final", "missing-boundary", "removed-log", "wrong-log-block", "missing-signed", "wrong-release", "malformed-data"])
def test_incomplete_or_conflicting_bound_receipt_keeps_unknown(tmp_path, case):
    envelope, binding, approvals, receipt = submitted_original(tmp_path)
    options = {}
    if case == "canonical":
        options["canonical"] = FINAL
    elif case == "not-final":
        options["final_number"] = "0x1"
    elif case == "missing-boundary":
        options["final_hash"] = None
    elif case == "removed-log":
        receipt["logs"][0]["removed"] = True
    elif case == "wrong-log-block":
        receipt["logs"][0]["blockHash"] = FINAL
    elif case == "missing-signed":
        envelope.pop("signed_bytes")
    elif case == "malformed-data":
        envelope["unsigned"]["data"] = "0x"
    elif case == "wrong-release":
        envelope["release_sha256"] = "f" * 64
    result = read_original_receipt(envelope, Observer(receipt, **options), binding=binding, synthetic_bindings=approvals)
    assert result.outcome == "SUBMISSION_UNKNOWN"
    assert result.verdict.actual_gas is None


def test_bound_envelope_cannot_fall_back_to_legacy_receipt_presence(tmp_path):
    envelope, _, _, receipt = submitted_original(tmp_path)
    result = read_original_receipt(envelope, Observer(receipt))
    assert result.outcome == "SUBMISSION_UNKNOWN"


def test_a_valid_signature_for_other_calldata_does_not_bind_to_the_release(tmp_path):
    from eth_account import Account
    from execution.test_privy_signer import PUBLISHED_TEST_KEY
    envelope, binding, approvals, receipt = submitted_original(tmp_path)
    unsigned = envelope["unsigned"]
    unsigned["data"] = "0xdeadbeef" + unsigned["data"][10:]
    signed = Account.sign_transaction({"type": 2, "chainId": 143, "nonce": 0, "to": unsigned["to"], "value": 0,
        "data": unsigned["data"], "gas": unsigned["gas_limit"], "maxFeePerGas": unsigned["max_fee_per_gas"],
        "maxPriorityFeePerGas": unsigned["max_priority_fee_per_gas"]},
        PUBLISHED_TEST_KEY)
    # Use the public recording key only if it matches the fixture signer. Otherwise this would test sender mismatch.
    assert Account.from_key(PUBLISHED_TEST_KEY).address == envelope["wallet_address"]
    envelope["signed_bytes"] = "0x" + signed.raw_transaction.hex()
    envelope["transaction_hash"] = receipt["transactionHash"] = "0x" + signed.hash.hex()
    for log in receipt["logs"]:
        log["transactionHash"] = envelope["transaction_hash"]
    result = read_original_receipt(envelope, Observer(receipt), binding=binding, synthetic_bindings=approvals)
    assert result.outcome == "SUBMISSION_UNKNOWN"


def test_api_recovery_passes_only_saved_release_and_observer_without_execution_clients(tmp_path):
    from types import SimpleNamespace
    from edge_os_api.core.provider_ports import ControlledRuntime, build_provider_ports
    from edge_os_api.execution.worker import ConnectedExecution
    envelope, binding, approvals, receipt = submitted_original(tmp_path)
    def forbidden(*args, **kwargs): raise AssertionError("execution capability acquired during recovery")
    runtime = ControlledRuntime(binding=binding, http=forbidden, quote_token=forbidden, signer_access=forbidden,
        synthetic_bindings=approvals)
    ports = build_provider_ports("controlled", forbidden, role="api", controlled={"agent-1":runtime})
    ports.original_observer = lambda agent: Observer(receipt)
    ports.original_clients = forbidden
    connected = ConnectedExecution(forbidden, SimpleNamespace(), ports, qualification="controlled")
    connected._apply = lambda owner, action, evidence, outcome: evidence
    intent = SimpleNamespace(agent_id="agent-1", action_id="action-1", operation="ENTRY", revision_id="execution-a",
        policy_binding="policy-a", payload_hash="sha256:" + "a" * 64, payload={"binding": {
            "agent_id":"agent-1", "wallet_id":envelope["wallet_id"], "network_id":"monad:143",
            "strategy_revision":"execution-a", "mandate_id":"mandate-a"}})
    result = connected._reconcile_original("owner-1", intent, envelope)
    assert result.outcome == "CONFIRMED" and result.actual_gas.raw == "600000000000000"


@pytest.mark.parametrize("missing", ["transaction_hash", "wallet_address", "chain_id", "candidate_hash"])
def test_missing_saved_identity_stays_unknown_without_observer_io(tmp_path, missing):
    envelope, binding, approvals, _ = submitted_original(tmp_path)
    envelope.pop(missing)
    class NoObserver:
        def call(self, *args):
            pytest.fail("malformed saved identity reached the observer")
    result = read_original_receipt(envelope, NoObserver(), binding=binding, synthetic_bindings=approvals)
    assert result.outcome == "SUBMISSION_UNKNOWN"
