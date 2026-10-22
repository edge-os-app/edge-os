"""The four-transaction sequence: ordering, journal-before-send, no resend, revoke after a failed swap."""

from __future__ import annotations

import json
from pathlib import Path

from eth_utils import keccak

from edge_os_api.execution.original_transaction import ReplyLost, RpcError

from scripts.operator_trade.calldata import approve_calldata, deposit_calldata, swap_calldata
from scripts.operator_trade.journal import Journal
from scripts.operator_trade.plan import plan_trade
from scripts.operator_trade.preflight import read_preflight
from scripts.operator_trade.sequence import execute
from scripts.operator_trade.trade_file import load_trade_file

from ._support import ENTRYPOINT, INPUT, WMON, FakeRpc, FakeSigner, RefusingSigner, clock_pair, signed_for, trade_dict

CODES = ("0x1", "0x1", "0x1", "0x1")


def _setup(tmp_path: Path, rpc: FakeRpc, **overrides: object):
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict(**overrides)), encoding="utf-8")
    trade = load_trade_file(path)
    preflight = read_preflight(rpc, trade)
    plan = plan_trade(trade, base_fee=preflight.base_fee, priority_fee=preflight.priority_fee,
               reserve_wmon=preflight.reserve_wmon, reserve_moe=preflight.reserve_moe)
    journal = Journal.create(tmp_path / "store")
    created: dict[str, FakeSigner] = {}

    def factory(step: str, nonce: int) -> FakeSigner:
        signer = FakeSigner(signed_for(step))
        created[step] = signer
        return signer

    return trade, preflight, plan, journal, created, factory


def _run(tmp_path: Path, rpc: FakeRpc, **overrides: object):
    trade, preflight, plan, journal, created, factory = _setup(tmp_path, rpc, **overrides)
    now, sleep = clock_pair()
    outcome = execute(rpc=rpc, trade=trade, plan=plan, preflight=preflight, signer_factory=factory,
                      journal=journal, now=now, sleep=sleep)
    return outcome, trade, plan, journal, created


def test_four_steps_in_order_with_sequential_nonces(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT])
    outcome, trade, plan, journal, created = _run(tmp_path, rpc)
    assert outcome.ok is True
    assert [step.step for step in outcome.steps] == ["wrap", "approve", "swap", "revoke"]
    assert [step.nonce for step in outcome.steps] == [7, 8, 9, 10]
    wrap = created["wrap"].calls[0][1]["params"]["transaction"]
    approve = created["approve"].calls[0][1]["params"]["transaction"]
    swap = created["swap"].calls[0][1]["params"]["transaction"]
    revoke = created["revoke"].calls[0][1]["params"]["transaction"]
    assert wrap["to"].lower() == WMON.lower()
    assert wrap["value"] == plan.input_raw
    assert wrap["data"] == deposit_calldata()
    assert approve["to"].lower() == WMON.lower()
    assert approve["value"] == 0
    assert approve["data"] == approve_calldata(ENTRYPOINT, plan.input_raw)
    assert swap["to"].lower() == ENTRYPOINT.lower()
    assert swap["value"] == 0
    assert swap["data"] == swap_calldata(trade, plan.input_raw, plan.minimum_raw)
    assert revoke["data"] == approve_calldata(ENTRYPOINT, 0)
    for body in (wrap, approve, swap, revoke):
        assert body["type"] == 2
        assert body["chain_id"] == 143
        assert body["max_priority_fee_per_gas"] == plan.max_priority_fee_per_gas
        assert body["max_fee_per_gas"] == plan.max_fee_per_gas
    assert outcome.wmon_after_wrap == INPUT


def test_journal_is_fsynced_before_each_send(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT])
    trade, preflight, plan, journal, created, factory = _setup(tmp_path, rpc)
    seen: list[list[dict[str, object]]] = []

    def before_send(signed: str) -> None:
        seen.append([json.loads(line) for line in (tmp_path / "store" / "journal.jsonl").read_text().splitlines()])

    rpc.on_send = before_send
    now, sleep = clock_pair()
    outcome = execute(rpc=rpc, trade=trade, plan=plan, preflight=preflight, signer_factory=factory,
                      journal=journal, now=now, sleep=sleep)
    assert outcome.ok is True
    assert len(seen) == 4
    for index, step in enumerate(("wrap", "approve", "swap", "revoke")):
        records = seen[index]
        before = [record for record in records if record["event"] == "before_send" and record["step"] == step]
        assert before, f"{step} was sent before its before_send journal record"
        assert before[-1]["tx_hash"] == "0x" + keccak(bytes.fromhex(signed_for(step)[2:])).hex()


def test_unknown_broadcast_is_never_resent_and_stops_the_sequence(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT], send_errors={0: ReplyLost("CLIENT_REPLY_LOST")})
    outcome, trade, plan, journal, created = _run(tmp_path, rpc)
    assert outcome.ok is False
    assert outcome.error_code == "BROADCAST_UNKNOWN"
    assert len(rpc.sent) == 1
    assert "approve" not in created
    records = [json.loads(line) for line in (tmp_path / "store" / "journal.jsonl").read_text().splitlines()]
    assert records[-1]["event"] == "unknown"
    assert records[-1]["liability"] == "UNKNOWN"


def test_a_reverted_wrap_stops_before_approve(tmp_path: Path) -> None:
    rpc = FakeRpc(receipt_statuses=["0x0"])
    outcome, trade, plan, journal, created = _run(tmp_path, rpc)
    assert outcome.ok is False
    assert outcome.failed_step == "wrap"
    assert outcome.error_code == "RECEIPT_STATUS_FAILED"
    assert len(rpc.sent) == 1
    assert "approve" not in created


def test_revoke_is_attempted_once_after_a_reverted_swap(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT], receipt_statuses=["0x1", "0x1", "0x0", "0x1"])
    outcome, trade, plan, journal, created = _run(tmp_path, rpc)
    assert outcome.ok is False
    assert outcome.failed_step == "swap"
    assert outcome.revoke_attempted is True
    assert outcome.revoke_ok is True
    assert len(rpc.sent) == 4
    assert created["revoke"].calls[0][1]["params"]["transaction"]["data"] == approve_calldata(ENTRYPOINT, 0)


def test_revoke_is_attempted_once_after_an_unknown_swap_broadcast(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT], send_errors={2: RpcError("CLIENT_REPLY_REFUSED")})
    outcome, trade, plan, journal, created = _run(tmp_path, rpc)
    assert outcome.ok is False
    assert outcome.failed_step == "swap"
    assert outcome.revoke_attempted is True
    assert len(rpc.sent) == 4
    assert "revoke" in created


def test_revoke_is_attempted_once_after_a_swap_receipt_timeout(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT], receipt_timeout_at={2})
    outcome, trade, plan, journal, created = _run(tmp_path, rpc)
    assert outcome.ok is False
    assert outcome.failed_step == "swap"
    assert outcome.error_code == "RECEIPT_TIMEOUT"
    assert outcome.revoke_attempted is True
    assert len(rpc.sent) == 4


def test_a_refused_signature_stops_before_send(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT])
    trade, preflight, plan, journal, _created, _factory = _setup(tmp_path, rpc)

    def refusing_factory(step: str, nonce: int):
        return RefusingSigner()

    now, sleep = clock_pair()
    outcome = execute(rpc=rpc, trade=trade, plan=plan, preflight=preflight,
                      signer_factory=refusing_factory, journal=journal, now=now, sleep=sleep)
    assert outcome.ok is False
    assert outcome.error_code == "SIGNER_REFUSED"
    assert outcome.steps == ()


def test_a_reverted_approve_stops_before_the_swap(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT], receipt_statuses=["0x1", "0x0"])
    outcome, trade, plan, journal, created = _run(tmp_path, rpc)
    assert outcome.ok is False
    assert outcome.failed_step == "approve"
    assert len(rpc.sent) == 2
    assert "swap" not in created
    assert "revoke" not in created


def test_a_failed_revoke_is_reported_and_not_retried(tmp_path: Path) -> None:
    rpc = FakeRpc(wmon_series=[0, INPUT], receipt_statuses=["0x1", "0x1", "0x1", "0x0"])
    outcome, trade, plan, journal, created = _run(tmp_path, rpc)
    assert outcome.ok is False
    assert outcome.failed_step == "revoke"
    assert len(rpc.sent) == 4
    assert "revoke" in created
    assert [step.step for step in outcome.steps] == ["wrap", "approve", "swap", "revoke"]
    assert outcome.steps[-1].status == 0
