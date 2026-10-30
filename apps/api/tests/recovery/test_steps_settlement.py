"""Step-aware settlement: every sent step needs a bound, final, chain-143 receipt before the action settles.

The receipts and observers are authored doubles. No client signs, sends or reaches a network.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from edge_os_api.core.provider_ports import ControlledRuntime, build_provider_ports
from edge_os_api.execution.original_transaction import read_original_receipt
from edge_os_api.execution.worker import ConnectedExecution
from edge_os_api.recovery.allowance import allowance_status

from execution.test_approve_swap_revoke import Chain, Signer, bound_steps, bound_transport, envelope, multi, run, steps
from execution.test_privy_signer import ENTRY_NONCE0_HASH, NOW

BLOCK = "0x" + "ab" * 32
FINAL = "0x" + "cd" * 32
SWAP_GAS = 300_000 * 2_000_000_000
STEP_GAS = 70_000 * 2_000_000_000
ALL_GAS = SWAP_GAS + 2 * STEP_GAS


def forbidden(*_args, **_kwargs):
    raise AssertionError("execution capability acquired during recovery")


def bound_envelope(tmp_path, *, chain: Chain | None = None, signer: Signer | None = None):
    signer, chain = signer or Signer(), chain or Chain()
    base, recordings, _ = multi(tmp_path, signer=signer, chain=chain)
    binding, approvals = bound_steps(base)
    transport = bound_transport(base, binding, approvals, plan=steps())
    stages: list = []
    outcome = run(transport, stages)
    return envelope(stages), binding, approvals, recordings, chain, outcome


def step_receipt(transaction_hash: str, wallet: str, token: str) -> dict:
    return {"transactionHash": transaction_hash, "from": wallet.lower(), "to": token.lower(), "status": "0x1",
            "blockNumber": "0x10", "blockHash": BLOCK, "gasUsed": "0x5208",
            "effectiveGasPrice": "0x77359400", "transactionIndex": "0x0", "logs": []}


def swap_receipt(saved: dict, recordings) -> dict:
    receipt = copy.deepcopy(recordings.data["receipts"][ENTRY_NONCE0_HASH])
    receipt["transactionHash"] = saved["transaction_hash"]
    receipt["from"] = saved["wallet_address"].lower()
    receipt["to"] = saved["candidate"]["to"].lower()
    receipt["blockHash"] = BLOCK
    receipt["transactionIndex"] = "0x0"
    receipt["logs"] = [{**log, "blockNumber": receipt["blockNumber"], "blockHash": BLOCK,
                        "transactionHash": saved["transaction_hash"], "transactionIndex": "0x0",
                        "logIndex": hex(index), "removed": False}
                       for index, log in enumerate(receipt["logs"])]
    return receipt


class Observer:
    def __init__(self, receipts: dict[str, dict], *, chain_id: str = "0x8f", final_number: str = "0x1e8482",
                 final_hash: str = FINAL, canonical_hash: str = BLOCK) -> None:
        self.receipts, self.chain_id, self.final_number = receipts, chain_id, final_number
        self.final_hash, self.canonical_hash = final_hash, canonical_hash
        self.calls: list[tuple[str, list]] = []

    def call(self, method: str, params: list):
        self.calls.append((method, params))
        if method == "eth_chainId":
            return self.chain_id
        if method == "eth_getTransactionReceipt":
            return self.receipts.get(str(params[0]).lower())
        assert method == "eth_getBlockByNumber"
        if params == ["finalized", False]:
            return {"number": self.final_number, "hash": self.final_hash}
        return {"number": params[0], "hash": self.canonical_hash, "baseFeePerGas": "0x3b9aca00"}


def receipts_for(saved: dict, recordings) -> dict[str, dict]:
    return {saved["approve"]["transaction_hash"]: step_receipt(
                saved["approve"]["transaction_hash"], saved["wallet_address"], saved["approve"]["token"]),
            saved["revoke"]["transaction_hash"]: step_receipt(
                saved["revoke"]["transaction_hash"], saved["wallet_address"], saved["revoke"]["token"]),
            saved["transaction_hash"]: swap_receipt(saved, recordings)}


def worker_for(saved: dict, binding, approvals, observer):
    runtime = ControlledRuntime(binding=binding, http=forbidden, clock=lambda: NOW, synthetic_bindings=approvals)
    ports = build_provider_ports("controlled", forbidden, role="api", controlled={"agent-1": runtime})
    ports.original_observer = lambda _agent: observer
    services = SimpleNamespace(recovery=SimpleNamespace(status=lambda *_args: SimpleNamespace(
        state="UNKNOWN", decision_status="SUBMISSION_UNKNOWN")))
    connected = ConnectedExecution(forbidden, services, ports, qualification="controlled")
    connected._apply = lambda _owner, _action, evidence, _outcome: evidence
    connected._save_allowance_proof = lambda *_args: None
    return connected


def saved_intent(saved: dict) -> SimpleNamespace:
    return SimpleNamespace(
        owner_id=saved["owner_id"], agent_id=saved["agent_id"], action_id=saved["action_id"],
        operation=saved["operation"],
        revision_id="execution-a", policy_binding="policy-a", payload_hash="sha256:" + "a" * 64,
        payload={"binding": {"agent_id": saved["agent_id"], "wallet_id": saved["wallet_id"],
                             "network_id": saved["network_id"], "strategy_revision": "execution-a",
                             "mandate_id": "consent-a"}})


def test_settlement_charges_every_sent_step_and_uses_the_swap_effects(tmp_path):
    saved, binding, approvals, recordings, _, outcome = bound_envelope(tmp_path)
    observer = Observer(receipts_for(saved, recordings))
    connected = worker_for(saved, binding, approvals, observer)

    result = connected._reconcile_original(saved["owner_id"], saved_intent(saved), saved)

    assert result.outcome == "CONFIRMED", result
    assert result.actual_input.raw == "100000000"
    assert result.actual_gas.raw == str(ALL_GAS)
    assert {method for method, _ in observer.calls} == {"eth_chainId", "eth_getTransactionReceipt",
                                                        "eth_getBlockByNumber"}


def test_a_missing_revoke_receipt_keeps_the_action_unknown_and_the_allowance_open(tmp_path):
    saved, binding, approvals, recordings, chain, _ = bound_envelope(
        tmp_path, chain=Chain({"revoke": "lost"}))
    receipts = receipts_for(saved, recordings)
    receipts.pop(saved["revoke"]["transaction_hash"])
    observer = Observer(receipts)
    connected = worker_for(saved, binding, approvals, observer)

    result = connected._reconcile_original(saved["owner_id"], saved_intent(saved), saved)

    assert result.outcome == "SUBMISSION_UNKNOWN"
    assert result.actual_gas is None
    assert allowance_status(saved)["open"] is True
    # Reconcile never signs or sends: the one revoke send is all that happened.
    assert [step for step, _ in chain.sent] == ["approve", "swap", "revoke"]


@pytest.mark.parametrize("change", [
    {"chain_id": "0x8e"}, {"final_number": "0x1"}, {"final_hash": "0x" + "ef" * 32,
                                                       "canonical_hash": "0x" + "ef" * 32},
])
def test_a_wrong_chain_or_unfinal_receipt_keeps_the_action_unknown(tmp_path, change):
    saved, binding, approvals, recordings, _, outcome = bound_envelope(tmp_path)
    observer = Observer(receipts_for(saved, recordings), **change)
    connected = worker_for(saved, binding, approvals, observer)

    result = connected._reconcile_original(saved["owner_id"], saved_intent(saved), saved)

    assert result.outcome == "SUBMISSION_UNKNOWN"
    assert result.actual_gas is None


def test_a_step_action_stays_in_flight_while_its_attempt_is_in_flight(tmp_path):
    saved, binding, approvals, recordings, _, outcome = bound_envelope(tmp_path)
    saved["in_flight"] = True
    observer = Observer(receipts_for(saved, recordings))
    connected = worker_for(saved, binding, approvals, observer)

    result = connected._reconcile_original(saved["owner_id"], saved_intent(saved), saved)

    assert result.receipt_outcome == "NOT_OBSERVED"
    assert result.detail == "ORIGINAL_IN_FLIGHT"
    assert observer.calls == []


def test_the_step_reader_needs_the_bound_release_and_never_uses_the_swap_receipt_alone(tmp_path):
    saved, binding, approvals, recordings, _, outcome = bound_envelope(tmp_path)
    observer = Observer(receipts_for(saved, recordings))

    reading = read_original_receipt(saved, observer, binding=binding, synthetic_bindings=approvals)
    assert reading.outcome == "CONFIRMED" and reading.verdict.actual_gas.raw == str(ALL_GAS)

    unbound = read_original_receipt(saved, observer)
    assert unbound.outcome == "SUBMISSION_UNKNOWN"
