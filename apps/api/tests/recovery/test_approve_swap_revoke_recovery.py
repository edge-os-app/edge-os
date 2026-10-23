"""A crashed or unknown approve -> swap -> revoke action is never resent, keeps liability and shows its allowance."""
from __future__ import annotations

import dataclasses

from edge_os_api.execution.original_transaction import TRANSPORT_ID

from admission._builders import AGENT_A, NETWORK, WALLET_A
from execution._builders import frozen_entry_exit
from execution._support import enqueue_entry, entry_inputs, quote
from execution.test_approve_swap_revoke import Chain, Signer, multi
from recovery._support import active_claim, load_queue


class Crash(BaseException):
    """The process dies here: nothing after this point runs."""


class CrashingChain(Chain):
    def __init__(self, crash_step: str) -> None:
        super().__init__()
        self.crash_step = crash_step

    def call(self, method, params):
        result = super().call(method, params)
        if method == "eth_sendRawTransaction" and self.sent[-1][0] == self.crash_step:
            raise Crash()
        return result


class SavedAction:
    """The worker's multi-step transport for one saved action, built from the prepared submission."""

    transport_id = TRANSPORT_ID

    def __init__(self, tmp_path, signer, chain) -> None:
        self.tmp_path, self.signer, self.chain = tmp_path, signer, chain

    def original_references(self, prepared):
        return {"transport_id": TRANSPORT_ID}

    def submit_original(self, prepared, journal):
        transport, _, _ = multi(self.tmp_path, signer=self.signer, chain=self.chain,
                                owner_id=prepared.owner_id, action_id=prepared.action_id,
                                payload_hash=prepared.payload_hash, wallet_id=prepared.wallet_id,
                                network_id=prepared.network_id)
        transport._context = dataclasses.replace(transport._context, operation=prepared.operation)
        return transport.submit_original(prepared, journal)


def _tick(service, owner, revision, approval, context, action_id, transport):
    return service.tick(owner, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK, approval=approval,
                        context=context, revision=revision, inputs=entry_inputs(),
                        quote=quote(action_id, revision, "110"), transport=transport)


def test_a_crash_after_the_swap_send_never_resends_and_reports_the_allowance_open(
        tmp_path, execution_service, recovery_service, recovery_factory, fresh_owner):
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    signer, chain = Signer(), CrashingChain("swap")
    try:
        _tick(execution_service, fresh_owner, revision, approval, context, action_id,
              SavedAction(tmp_path, signer, chain))
        raise AssertionError("the crash must stop the action")
    except Crash:
        pass
    assert chain.sent == [("approve", 5), ("swap", 6)]

    # After the restart a fresh transport for the same wallet makes no call: the original attempt owns the claim.
    later_signer, later_chain = Signer(), Chain()
    tick = _tick(execution_service, fresh_owner, revision, approval, context, action_id,
                 SavedAction(tmp_path / "later", later_signer, later_chain))
    assert later_signer.calls == [] and later_chain.sent == [] and later_chain.nonce_reads == 0
    assert tick.status != "SUBMITTED_CONFIRMED"
    assert load_queue(recovery_factory, fresh_owner, action_id).state == "CLAIMED"
    assert active_claim(recovery_factory, fresh_owner) is not None

    case = recovery_service.status(fresh_owner, action_id)
    assert case.allowance is not None
    assert case.allowance["state"] == "REVOKE_NOT_SENT" and case.allowance["open"] is True
    assert case.allowance["approve_stage"] == "BROADCAST_RETURNED"


def test_an_unknown_revoke_keeps_the_action_unknown_and_its_allowance_visible(
        tmp_path, execution_service, recovery_service, recovery_factory, fresh_owner):
    revision = frozen_entry_exit()
    _decision, approval, context, result = enqueue_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    signer, chain = Signer(), Chain({"revoke": "lost"})
    tick = _tick(execution_service, fresh_owner, revision, approval, context, action_id,
                 SavedAction(tmp_path, signer, chain))
    assert tick.status == "SUBMITTED_UNKNOWN"
    assert [step for step, _ in chain.sent] == ["approve", "swap", "revoke"]
    again = _tick(execution_service, fresh_owner, revision, approval, context, action_id,
                  SavedAction(tmp_path / "again", Signer(), Chain()))
    assert again.status != "SUBMITTED_CONFIRMED"
    assert [step for step, _ in chain.sent].count("revoke") == 1
    case = recovery_service.status(fresh_owner, action_id)
    assert case.allowance["state"] == "REVOKE_UNKNOWN" and case.allowance["open"] is True
    assert case.decision_status == "SUBMISSION_UNKNOWN"


def test_a_single_swap_case_carries_no_allowance(tmp_path, execution_service, recovery_service, fresh_owner):
    from recovery._support import open_unknown_entry
    revision = frozen_entry_exit()
    _approval, _context, result = open_unknown_entry(execution_service, fresh_owner, revision)
    action_id = result.intent.action_id
    assert recovery_service.status(fresh_owner, action_id).allowance is None
