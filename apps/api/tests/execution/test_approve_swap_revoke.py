"""One approved in-app action runs the release's approve -> swap -> revoke steps, each sent once (CLOUD-A6).

The clients are local test doubles. The signer signs with the published test key; nothing reaches a provider.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from eth_account import Account
from eth_utils import keccak

from edge_os_api.execution.original_transaction import (
    APPROVE_SELECTOR,
    JournalError,
    OriginalTransactionTransport,
    ReplyLost,
    RpcError,
    SignerPolicyDenied,
    TradeSteps,
    owner_projection,
)
from edge_os_api.execution.transport import PreparedSubmission
from edge_os_api.recovery.allowance import allowance_status, read_revoke_receipt
from execution.test_privy_signer import NOW, PUBLISHED_TEST_KEY, PUBLISHED_WALLET, original

AUTHORED = Path(__file__).resolve().parents[4] / "docs" / "qualification" / "inapp-trade" / "release.authored.json"
BASE_NONCE = 5


def steps(**changes: Any) -> TradeSteps:
    values: dict[str, Any] = dict(gas_limits={"wrap": 60000, "approve": 70000, "swap": 300000, "revoke": 70000},
                                  usd_ceiling=Decimal("2.00"), mon_usd_price=Decimal("0.02"))
    values.update(changes)
    return TradeSteps(**values)


def step_of(transaction: dict[str, Any]) -> str:
    data = transaction["data"]
    if not data.startswith(APPROVE_SELECTOR):
        return "swap"
    return "revoke" if int(data[-64:], 16) == 0 else "approve"


class Signer:
    """Signs with the published test key; `faults` names a step and how its signer call ends."""

    def __init__(self, faults: dict[str, str] | None = None) -> None:
        self.faults, self.calls = dict(faults or {}), []

    def rpc(self, wallet_id: str, body: dict[str, Any]) -> dict[str, Any]:
        transaction = body["params"]["transaction"]
        step = step_of(transaction)
        self.calls.append((step, transaction["nonce"]))
        fault = self.faults.get(step)
        if fault == "policy":
            raise SignerPolicyDenied("PRIVY_POLICY_VIOLATION")
        if fault == "refused":
            return {"error": {"code": "invalid_request"}}
        signed = Account.sign_transaction({
            "type": 2, "chainId": transaction["chain_id"], "nonce": transaction["nonce"], "to": transaction["to"],
            "value": transaction["value"], "data": transaction["data"], "gas": transaction["gas_limit"],
            "maxFeePerGas": transaction["max_fee_per_gas"],
            "maxPriorityFeePerGas": transaction["max_priority_fee_per_gas"]}, PUBLISHED_TEST_KEY)
        if fault == "lost":
            raise ReplyLost("signed, reply lost")
        return {"method": "eth_signTransaction",
                "data": {"signed_transaction": "0x" + bytes(signed.raw_transaction).hex(), "encoding": "rlp"}}


class Chain:
    """`eth_getTransactionCount` and `eth_sendRawTransaction`; `faults` names a step and how its send ends."""

    def __init__(self, faults: dict[str, str] | None = None) -> None:
        self.faults, self.sent, self.nonce_reads = dict(faults or {}), [], 0

    def call(self, method: str, params: list[Any]) -> Any:
        if method == "eth_getTransactionCount":
            self.nonce_reads += 1
            return hex(BASE_NONCE)
        assert method == "eth_sendRawTransaction"
        raw = bytes.fromhex(params[0][2:])
        decoded = Account.recover_transaction(raw)
        assert decoded.lower() == PUBLISHED_WALLET.lower()
        from eth_account.typed_transactions import TypedTransaction
        fields = TypedTransaction.from_bytes(raw).as_dict()
        step = step_of({"data": "0x" + bytes(fields["data"]).hex()})
        self.sent.append((step, fields["nonce"]))
        fault = self.faults.get(step)
        if fault == "lost":
            raise ReplyLost("sent, reply lost")
        if fault == "error":
            raise RpcError("node error")
        return "0x" + keccak(raw).hex()


def multi(tmp_path, *, signer: Signer | None = None, chain: Chain | None = None, plan: TradeSteps | None = None,
          **context_changes: Any):
    transport, recordings, stages = original(tmp_path, signer or Signer())
    context = dataclasses.replace(transport._context, **context_changes)
    clients = dataclasses.replace(transport._clients, broadcast=chain or Chain())
    built = OriginalTransactionTransport(context, clients, transport._profile, controls=lambda: [],
                                         clock=lambda: NOW, steps=plan or steps())
    return built, recordings, stages


def run(transport: OriginalTransactionTransport, stages: list, journal=None):
    prepared = PreparedSubmission(action_id="action-1", owner_id="owner-1", wallet_id=transport._context.wallet_id,
                                  network_id="monad:143", operation="ENTRY", payload_hash="sha256:payload",
                                  attempt_id="attempt-0001")
    return transport.submit_original(prepared, journal or (lambda stage, values: stages.append((stage, values))))


def envelope(stages: list) -> dict[str, Any]:
    """What the attempt journal saves: a shallow merge of every stage's values."""
    saved: dict[str, Any] = {}
    for stage, values in stages:
        saved.update(values)
        saved["stage"] = stage
    return saved


# ------------------------------------------------------------------------------------------- the release's steps

def test_the_release_names_approve_swap_revoke_with_its_fixed_gas_and_ceiling():
    plan = TradeSteps.from_authored(json.loads(AUTHORED.read_text(encoding="utf-8")))
    assert plan.order == ("approve", "swap", "revoke")
    assert dict(plan.gas_limits) == {"wrap": 60000, "approve": 70000, "swap": 700000, "revoke": 70000}
    assert (plan.usd_ceiling, plan.mon_usd_price) == (Decimal("2.00"), Decimal("0.02"))


def test_an_authored_file_with_other_steps_is_refused():
    authored = json.loads(AUTHORED.read_text(encoding="utf-8"))
    authored["facts"]["active_steps"] = ["swap"]
    with pytest.raises(ValueError):
        TradeSteps.from_authored(authored)


# ------------------------------------------------------------------------------------------- the happy path

def test_one_action_runs_approve_swap_revoke_in_order_each_signed_and_sent_once(tmp_path):
    signer, chain = Signer(), Chain()
    transport, recordings, stages = multi(tmp_path, signer=signer, chain=chain)
    outcome = run(transport, stages)

    assert outcome.outcome == "SUBMISSION_POSSIBLE"
    assert outcome.detail == "BROADCAST_RETURNED;REVOKE:BROADCAST_RETURNED"
    assert signer.calls == [("approve", 5), ("swap", 6), ("revoke", 7)]
    assert chain.sent == [("approve", 5), ("swap", 6), ("revoke", 7)]
    assert chain.nonce_reads == 1
    assert recordings.call_counts()["route.quote"] == 1
    assert [stage for stage, _ in stages] == [
        "PREPARED", "APPROVE_PREPARED",
        "APPROVE_SIGN_REQUESTED", "APPROVE_SIGNED", "APPROVE_BROADCAST_REQUESTED", "APPROVE_BROADCAST_RETURNED",
        "SIGN_REQUESTED", "SIGNED", "BROADCAST_REQUESTED", "BROADCAST_RETURNED",
        "REVOKE_PREPARED", "REVOKE_SIGN_REQUESTED", "REVOKE_SIGNED", "REVOKE_BROADCAST_REQUESTED",
        "REVOKE_BROADCAST_RETURNED"]

    saved = envelope(stages)
    context, profile = transport._context, transport._profile
    approve, revoke = saved["approve"], saved["revoke"]
    spender_word = "0" * 24 + profile.entrypoint[2:].lower()
    assert approve["unsigned"] == {"type": 2, "chain_id": 143, "nonce": 5, "to": context.sell.token, "value": 0,
        "data": APPROVE_SELECTOR + spender_word + f"{context.sell.raw:064x}", "gas_limit": 70000,
        "max_fee_per_gas": profile.max_fee_per_gas, "max_priority_fee_per_gas": profile.max_priority_fee_per_gas}
    assert revoke["unsigned"]["data"] == APPROVE_SELECTOR + spender_word + "0" * 64
    assert (revoke["unsigned"]["nonce"], revoke["unsigned"]["gas_limit"]) == (7, 70000)
    assert (approve["spender"], approve["amount_raw"], revoke["amount_raw"]) == (profile.entrypoint, str(context.sell.raw), "0")
    # The swap keeps the single-swap envelope at the top level, so its receipt reconciliation is unchanged.
    assert saved["unsigned"]["nonce"] == 6 and saved["unsigned"]["to"] == profile.entrypoint
    assert saved["steps"] == ["approve", "swap", "revoke"]
    assert saved["swap"]["stage"] == "BROADCAST_RETURNED"
    hashes = {approve["transaction_hash"], saved["transaction_hash"], revoke["transaction_hash"]}
    assert len(hashes) == 3
    request_ids = {approve["signing_request"]["request_id"], saved["signing_request"]["request_id"],
                   revoke["signing_request"]["request_id"]}
    assert request_ids == {"attempt-0001:approve", "attempt-0001", "attempt-0001:revoke"}
    status = allowance_status(saved)
    assert status["state"] == "REVOKE_UNCONFIRMED" and status["open"] is True


def test_the_transport_is_used_once_and_never_resends_a_step(tmp_path):
    signer, chain = Signer(), Chain()
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)
    run(transport, stages)
    again = run(transport, [])
    assert again.outcome == "SUBMISSION_POSSIBLE" and again.detail == "ACTION_ALREADY_STARTED"
    assert len(signer.calls) == 3 and len(chain.sent) == 3


# ------------------------------------------------------------------------------------------- ceiling before step 1

def test_total_step_gas_beyond_the_gas_reservation_is_refused_before_any_call(tmp_path):
    signer, chain = Signer(), Chain()
    profile_fee = 3_000_000_000
    # Enough for the swap alone (300000) but not for approve + swap + revoke (440000).
    transport, recordings, stages = multi(tmp_path, signer=signer, chain=chain, gas_cap_raw=400000 * profile_fee)
    outcome = run(transport, stages)
    assert (outcome.outcome, outcome.detail) == ("DEFINITELY_UNSENT", "FEE_EXCEEDS_GAS_RESERVATION")
    assert signer.calls == [] and chain.sent == [] and chain.nonce_reads == 0
    assert recordings.call_counts() == {}


def test_a_worst_case_above_the_usd_ceiling_is_refused_before_any_call(tmp_path):
    signer, chain = Signer(), Chain()
    # 100 input units at 18 decimals would be 1e-10 MON; a price this high still exceeds USD 2.00 with gas.
    plan = steps(mon_usd_price=Decimal("10000"))
    transport, recordings, stages = multi(tmp_path, signer=signer, chain=chain, plan=plan)
    outcome = run(transport, stages)
    assert (outcome.outcome, outcome.detail) == ("DEFINITELY_UNSENT", "USD_CEILING_EXCEEDED")
    assert signer.calls == [] and chain.sent == [] and recordings.call_counts() == {}


def test_the_ceiling_counts_every_release_gas_limit_including_the_wrap(tmp_path):
    # (60000 + 70000 + 300000 + 70000) * 3 gwei = 0.0015 MON; 100000000 raw input = 1e-10 MON.
    worst = Decimal(500000 * 3_000_000_000 + 100_000_000) / Decimal(10**18)
    price = Decimal("2.00") / worst
    passing, _, stages = multi(tmp_path / "a", plan=steps(mon_usd_price=price))
    assert run(passing, stages).detail == "BROADCAST_RETURNED;REVOKE:BROADCAST_RETURNED"
    refused, _, stages = multi(tmp_path / "b", plan=steps(mon_usd_price=price * Decimal("1.0001")))
    assert run(refused, stages).detail == "USD_CEILING_EXCEEDED"


def test_a_step_plan_whose_swap_gas_differs_from_the_route_is_refused_before_any_call(tmp_path):
    signer = Signer()
    transport, recordings, stages = multi(tmp_path, signer=signer, plan=steps(
        gas_limits={"wrap": 60000, "approve": 70000, "swap": 700000, "revoke": 70000}))
    outcome = run(transport, stages)
    assert (outcome.outcome, outcome.detail) == ("DEFINITELY_UNSENT", "STEP_GAS_MISMATCH")
    assert signer.calls == [] and recordings.call_counts() == {}


def test_existing_refusals_still_precede_the_steps(tmp_path):
    signer = Signer()
    transport, _, stages = multi(tmp_path, signer=signer, intent_expires_at=NOW)
    assert run(transport, stages).detail == "INTENT_EXPIRED"
    transport, _, stages = multi(tmp_path, signer=signer)
    transport._controls = lambda: ["STOPPED_HALT_ALL_SWAPS"]
    outcome = run(transport, stages)
    assert (outcome.outcome, outcome.detail) == ("DEFINITELY_UNSENT", "STOPPED_HALT_ALL_SWAPS")
    assert signer.calls == []


# ------------------------------------------------------------------------------------------- approve outcomes

def test_a_policy_denied_approve_sends_nothing_and_opens_no_allowance(tmp_path):
    signer, chain = Signer({"approve": "policy"}), Chain()
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)
    outcome = run(transport, stages)
    assert (outcome.outcome, outcome.detail) == ("DEFINITELY_UNSENT", "APPROVE:WALLET_POLICY_REFUSED")
    assert signer.calls == [("approve", 5)] and chain.sent == []
    saved = envelope(stages)
    assert saved["stage"] == "REFUSED_UNSENT"
    assert allowance_status(saved) == {"state": "NOT_APPROVED", "open": False, "token": transport._context.sell.token,
        "spender": transport._profile.entrypoint, "approved_raw": str(transport._context.sell.raw),
        "approve_stage": "REFUSED_UNSENT", "revoke_stage": None, "reason": "APPROVE:WALLET_POLICY_REFUSED"}


@pytest.mark.parametrize("signer_fault,chain_fault,detail", [
    ("lost", None, "APPROVE:SIGNING_UNKNOWN"),
    (None, "lost", "APPROVE:BROADCAST_UNKNOWN"),
    (None, "error", "APPROVE:BROADCAST_ERROR"),
])
def test_an_unknown_approve_keeps_liability_and_stops_without_swap_or_revoke(tmp_path, signer_fault, chain_fault,
                                                                              detail):
    signer = Signer({"approve": signer_fault} if signer_fault else {})
    chain = Chain({"approve": chain_fault} if chain_fault else {})
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)
    outcome = run(transport, stages)
    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", detail)
    assert [step for step, _ in signer.calls] == ["approve"]
    assert [step for step, _ in chain.sent] in ([], ["approve"])
    saved = envelope(stages)
    status = allowance_status(saved)
    assert status["state"] == "APPROVE_UNKNOWN" and status["open"] is True
    assert saved["revoke"]["stage"] == "NOT_ATTEMPTED"


# ------------------------------------------------------------------------------------------- swap outcomes

@pytest.mark.parametrize("fault,detail", [
    ("policy", "SWAP:WALLET_POLICY_REFUSED"),
    ("refused", "SWAP:SIGNER_REFUSED"),
])
def test_a_definitely_refused_swap_is_followed_by_one_revoke_at_the_unused_swap_nonce(tmp_path, fault, detail):
    signer, chain = Signer({"swap": fault}), Chain()
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)
    outcome = run(transport, stages)
    # The approve was sent, so its liability stays even though the swap never was.
    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", f"{detail};REVOKE:BROADCAST_RETURNED")
    assert signer.calls == [("approve", 5), ("swap", 6), ("revoke", 6)]
    assert chain.sent == [("approve", 5), ("revoke", 6)]
    saved = envelope(stages)
    assert saved["swap"]["stage"] == "REFUSED_UNSENT"
    assert "REFUSED_UNSENT" not in [stage for stage, _ in stages]


def test_a_stop_after_the_approve_refuses_the_swap_and_still_revokes(tmp_path):
    signer, chain = Signer(), Chain()
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)
    calls = {"count": 0}

    def controls():
        calls["count"] += 1
        # prepare, approve sign recheck, approve send recheck pass; the swap's sign recheck sees the stop.
        return ["STOPPED_HALT_ALL_SWAPS"] if calls["count"] == 4 else []

    transport._controls = controls
    outcome = run(transport, stages)
    assert outcome.detail == "SWAP:STOPPED_HALT_ALL_SWAPS;REVOKE:BROADCAST_RETURNED"
    assert chain.sent == [("approve", 5), ("revoke", 6)]


@pytest.mark.parametrize("signer_fault,chain_fault,detail", [
    ("lost", None, "SIGNING_UNKNOWN"),
    (None, "lost", "BROADCAST_UNKNOWN"),
    (None, "error", "BROADCAST_ERROR"),
])
def test_an_unknown_swap_keeps_liability_and_reports_the_allowance_open_without_a_revoke(
        tmp_path, signer_fault, chain_fault, detail):
    signer = Signer({"swap": signer_fault} if signer_fault else {})
    chain = Chain({"swap": chain_fault} if chain_fault else {})
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)
    outcome = run(transport, stages)
    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", f"{detail};REVOKE:NOT_ATTEMPTED")
    assert [step for step, _ in signer.calls] == ["approve", "swap"]
    assert "revoke" not in [step for step, _ in chain.sent]
    saved = envelope(stages)
    assert saved["revoke"] == {"step": "revoke", "stage": "NOT_ATTEMPTED", "reason": "SWAP_OUTCOME_UNKNOWN"}
    status = allowance_status(saved)
    assert status["state"] == "REVOKE_NOT_SENT" and status["open"] is True


def test_a_swap_signed_but_not_sent_is_unknown_and_never_revoked_at_its_nonce(tmp_path):
    signer, chain = Signer(), Chain()
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)
    calls = {"count": 0}

    def controls():
        calls["count"] += 1
        return ["STOPPED_HALT_ALL_SWAPS"] if calls["count"] == 5 else []  # the swap's pre-send recheck

    transport._controls = controls
    outcome = run(transport, stages)
    assert outcome.detail == "STOPPED_AFTER_SIGNING:STOPPED_HALT_ALL_SWAPS;REVOKE:NOT_ATTEMPTED"
    assert chain.sent == [("approve", 5)]


# ------------------------------------------------------------------------------------------- revoke outcomes

@pytest.mark.parametrize("signer_fault,chain_fault,state,detail", [
    ("lost", None, "REVOKE_UNKNOWN", "REVOKE:SIGNING_UNKNOWN"),
    (None, "lost", "REVOKE_UNKNOWN", "REVOKE:BROADCAST_UNKNOWN"),
    (None, "error", "REVOKE_UNKNOWN", "REVOKE:BROADCAST_ERROR"),
    ("policy", None, "REVOKE_NOT_SENT", "REVOKE:WALLET_POLICY_REFUSED"),
])
def test_an_unknown_or_refused_revoke_is_reported_as_an_open_allowance_and_never_resent(
        tmp_path, signer_fault, chain_fault, state, detail):
    signer = Signer({"revoke": signer_fault} if signer_fault else {})
    chain = Chain({"revoke": chain_fault} if chain_fault else {})
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)
    outcome = run(transport, stages)
    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", f"BROADCAST_RETURNED;{detail}")
    assert [step for step, _ in signer.calls].count("revoke") == 1
    assert [step for step, _ in chain.sent].count("revoke") <= 1
    saved = envelope(stages)
    status = allowance_status(saved)
    assert status["state"] == state and status["open"] is True
    view = owner_projection(saved)
    assert view["allowance"] == status
    assert "signed_bytes" not in json.dumps(view["revoke"]) and "body" not in view["revoke"].get("signing_request", {})


def test_a_failed_save_before_the_revoke_signature_leaves_it_unsent_and_reported(tmp_path):
    signer, chain = Signer(), Chain()
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)

    def journal(stage, values):
        if stage == "REVOKE_SIGN_REQUESTED":
            raise JournalError("save failed")
        stages.append((stage, values))

    outcome = run(transport, stages, journal)
    assert outcome.detail == "BROADCAST_RETURNED;REVOKE:PERSISTENCE_FAILED_BEFORE_SIGNING"
    assert [step for step, _ in signer.calls] == ["approve", "swap"]
    assert allowance_status(envelope(stages))["open"] is True


def test_a_failed_save_after_the_approve_signature_never_broadcasts_it(tmp_path):
    signer, chain = Signer(), Chain()
    transport, _, stages = multi(tmp_path, signer=signer, chain=chain)

    def journal(stage, values):
        if stage == "APPROVE_SIGNED":
            raise JournalError("save failed")
        stages.append((stage, values))

    outcome = run(transport, stages, journal)
    assert (outcome.outcome, outcome.detail) == ("SUBMISSION_POSSIBLE", "APPROVE:PERSISTENCE_FAILED_AFTER_SIGNING")
    assert chain.sent == [] and [step for step, _ in signer.calls] == ["approve"]


def test_a_failed_save_before_the_approve_signature_is_definitely_unsent(tmp_path):
    signer = Signer()
    transport, _, stages = multi(tmp_path, signer=signer)

    def journal(stage, values):
        if stage == "APPROVE_PREPARED":
            raise JournalError("save failed")
        stages.append((stage, values))

    outcome = run(transport, stages, journal)
    assert (outcome.outcome, outcome.detail) == ("DEFINITELY_UNSENT", "PERSISTENCE_FAILED_BEFORE_SIGNING")
    assert signer.calls == []


# ------------------------------------------------------------------------------------------- recovery reads

def test_a_revoke_receipt_closes_the_allowance_only_when_bound_and_successful(tmp_path):
    transport, _, stages = multi(tmp_path)
    run(transport, stages)
    saved = envelope(stages)
    revoke = saved["revoke"]

    class Observer:
        def __init__(self, receipt):
            self.receipt, self.calls = receipt, []

        def call(self, method, params):
            self.calls.append((method, params))
            return self.receipt

    good = {"transactionHash": revoke["transaction_hash"], "from": PUBLISHED_WALLET.lower(),
            "to": transport._context.sell.token.lower(), "status": "0x1"}
    assert read_revoke_receipt(saved, Observer(good))["state"] == "CLOSED"
    assert read_revoke_receipt(saved, Observer({**good, "status": "0x0"}))["state"] == "REVOKE_REVERTED"
    assert read_revoke_receipt(saved, Observer({**good, "to": PUBLISHED_WALLET}))["open"] is True
    assert read_revoke_receipt(saved, Observer(None))["state"] == "REVOKE_UNCONFIRMED"

    class Down:
        def call(self, method, params):
            raise ReplyLost("down")

    assert read_revoke_receipt(saved, Down())["open"] is True


def test_a_single_swap_envelope_has_no_allowance_record(tmp_path):
    from execution.test_privy_signer import FakeHttp, client, recorded_signature, signed_reply, submit
    transport, recordings, stages = original(tmp_path, client(FakeHttp(signed_reply(recorded_signature("ENTRY", 0)))))
    outcome = submit(transport, stages)
    assert outcome.detail == "BROADCAST_RETURNED"
    assert recordings.call_counts()["broadcast.eth_sendRawTransaction"] == 1
    saved = envelope(stages)
    assert "steps" not in saved and allowance_status(saved) is None
    assert "allowance" not in owner_projection(saved)
