"""WMON start: skip the wrap, keep approve exact, swap and revoke, and fit the native balance.

The 2026-10-22 run left 50 WMON and 0.14084 MON in the wallet. A WMON start must spend no MON value
and must still require a zero start allowance and write the exact approve amount.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operator_trade.calldata import approve_calldata
from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.journal import Journal
from scripts.operator_trade.plan import plan_trade
from scripts.operator_trade.preflight import read_preflight
from scripts.operator_trade.run import main, run_post_checks
from scripts.operator_trade.sequence import execute
from scripts.operator_trade.transactions import build_unsigned
from scripts.operator_trade.trade_file import load_trade_file

from ._support import (
    ENTRYPOINT,
    INPUT,
    WMON,
    FakeRpc,
    FakeSigner,
    clock_pair,
    signed_for,
    trade_dict,
)

NATIVE_AFTER_THE_LIVE_RUN = 140_840_000_000_000_000


def _trade(tmp_path: Path, **overrides: object):
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict(**overrides)), encoding="utf-8")
    return load_trade_file(path)


def _setup(tmp_path: Path, rpc: FakeRpc, **overrides: object):
    trade = _trade(tmp_path, **overrides)
    preflight = read_preflight(rpc, trade)
    plan = plan_trade(trade, base_fee=preflight.base_fee, priority_fee=preflight.priority_fee,
                      reserve_wmon=preflight.reserve_wmon, reserve_moe=preflight.reserve_moe)
    return trade, preflight, plan


def _execute(tmp_path: Path, rpc: FakeRpc, **overrides: object):
    trade, preflight, plan = _setup(tmp_path, rpc, **overrides)
    journal = Journal.create(tmp_path / "store")
    created: dict[str, FakeSigner] = {}

    def factory(step: str, nonce: int) -> FakeSigner:
        signer = FakeSigner(signed_for(step))
        created[step] = signer
        return signer

    now, sleep = clock_pair()
    outcome = execute(rpc=rpc, trade=trade, plan=plan, preflight=preflight, signer_factory=factory,
                      journal=journal, now=now, sleep=sleep)
    return outcome, trade, plan, preflight, created


def test_wmon_start_fits_the_balance_and_needs_no_mon_value(tmp_path: Path) -> None:
    rpc = FakeRpc(native_balance=NATIVE_AFTER_THE_LIVE_RUN, wmon_balance=INPUT)
    trade, preflight, plan = _setup(tmp_path, rpc, start="WMON")
    assert preflight.required_native_wei == 520_000 * plan.max_fee_per_gas
    assert preflight.remaining_native_wei == NATIVE_AFTER_THE_LIVE_RUN - preflight.required_native_wei
    assert plan.worst_case_wei == INPUT + 520_000 * plan.max_fee_per_gas


def test_wmon_start_builds_three_steps_and_skips_the_wrap(tmp_path: Path) -> None:
    rpc = FakeRpc(native_balance=NATIVE_AFTER_THE_LIVE_RUN, wmon_balance=INPUT)
    trade, preflight, plan = _setup(tmp_path, rpc, start="WMON")
    unsigned = build_unsigned(trade, plan, preflight)
    assert [item.step for item in unsigned] == ["approve", "swap", "revoke"]
    assert [item.nonce for item in unsigned] == [7, 8, 9]
    assert unsigned[0].value == 0
    assert unsigned[1].value == 0
    assert unsigned[2].value == 0


def test_mon_start_still_needs_the_input_value(tmp_path: Path) -> None:
    gas_only = 580_000 * 3_000_000_000
    with pytest.raises(OperatorError) as caught:
        _setup(tmp_path, FakeRpc(native_balance=gas_only), start="MON")
    assert caught.value.code == "INSUFFICIENT_NATIVE_BALANCE"


def test_mon_start_is_unchanged(tmp_path: Path) -> None:
    rpc = FakeRpc()
    trade, preflight, plan = _setup(tmp_path, rpc)
    unsigned = build_unsigned(trade, plan, preflight)
    assert [item.step for item in unsigned] == ["wrap", "approve", "swap", "revoke"]
    assert [item.nonce for item in unsigned] == [7, 8, 9, 10]
    assert unsigned[0].value == INPUT
    assert preflight.required_native_wei == INPUT + 580_000 * plan.max_fee_per_gas


def test_wmon_start_refuses_an_insufficient_wmon_balance(tmp_path: Path) -> None:
    with pytest.raises(OperatorError) as caught:
        _setup(tmp_path, FakeRpc(native_balance=NATIVE_AFTER_THE_LIVE_RUN, wmon_balance=INPUT - 1),
               start="WMON")
    assert caught.value.code == "INSUFFICIENT_WMON_BALANCE"


def test_wmon_start_refuses_a_nonzero_allowance(tmp_path: Path) -> None:
    with pytest.raises(OperatorError) as caught:
        _setup(tmp_path, FakeRpc(native_balance=NATIVE_AFTER_THE_LIVE_RUN, wmon_balance=INPUT, allowance=1),
               start="WMON")
    assert caught.value.code == "ALLOWANCE_NOT_ZERO"


def test_wmon_start_keeps_approve_exact_and_revoke_zero(tmp_path: Path) -> None:
    rpc = FakeRpc(native_balance=NATIVE_AFTER_THE_LIVE_RUN, wmon_balance=INPUT)
    outcome, trade, plan, preflight, created = _execute(tmp_path, rpc, start="WMON")
    assert outcome.ok is True
    assert [step.step for step in outcome.steps] == ["approve", "swap", "revoke"]
    assert outcome.wmon_after_wrap == INPUT
    approve = created["approve"].calls[0][1]["params"]["transaction"]
    revoke = created["revoke"].calls[0][1]["params"]["transaction"]
    assert approve["to"].lower() == WMON.lower()
    assert approve["data"] == approve_calldata(ENTRYPOINT, plan.input_raw)
    assert approve["value"] == 0
    assert revoke["data"] == approve_calldata(ENTRYPOINT, 0)
    assert approve["gas_limit"] == trade.gas_limits.approve
    assert revoke["gas_limit"] == trade.gas_limits.revoke


def test_wmon_start_passes_the_post_checks(tmp_path: Path) -> None:
    rpc = FakeRpc(native_balance=NATIVE_AFTER_THE_LIVE_RUN, wmon_balance=INPUT,
                  wmon_series=[INPUT, 0], moe_series=[0, 10**22])
    outcome, trade, plan, preflight, _created = _execute(tmp_path, rpc, start="WMON")
    post = run_post_checks(rpc=rpc, trade=trade, plan=plan, preflight=preflight, outcome=outcome)
    assert post.all_true() is True


def test_the_live_shape_refuses_before_the_allowance_step_when_gas_is_short(tmp_path: Path) -> None:
    rpc = FakeRpc(native_balance=0, wmon_balance=INPUT)
    with pytest.raises(OperatorError) as caught:
        _setup(tmp_path, rpc, start="WMON")
    assert caught.value.code == "INSUFFICIENT_NATIVE_BALANCE"


def test_a_dry_run_shows_the_three_step_wmon_start(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:

    rpc = FakeRpc(native_balance=NATIVE_AFTER_THE_LIVE_RUN, wmon_balance=INPUT)
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict(start="WMON")), encoding="utf-8")
    code = main(["--trade-file", str(path)],
                environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"}, rpc=rpc)
    output = capsys.readouterr().out
    assert code == 0
    report = json.loads(output)
    assert report["start"] == "WMON"
    assert [step["step"] for step in report["steps"]] == ["approve", "swap", "revoke"]
    assert report["balance"]["gas_limit_total"] == 520_000
    assert report["plan"]["worst_case_wei"] == INPUT + 520_000 * 3_000_000_000


def test_a_live_wmon_start_sends_three_steps_and_records_the_estimates(
        tmp_path: Path) -> None:
    import hashlib

    from ._support import FakePrivyTransport, write_p256_key

    raw = json.dumps(trade_dict(start="WMON"), sort_keys=True, separators=(",", ":")).encode()
    path = tmp_path / "trade.json"
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    key_path = tmp_path / "agent-key.pem"
    write_p256_key(key_path)
    environment = {
        "EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key-secret-path",
        "EDGE_OS_PRIVY_APP_ID": "app-id",
        "EDGE_OS_PRIVY_APP_SECRET": "app-secret",
        "EDGE_OS_PRIVY_AGENT_KEY_FILE": str(key_path),
    }
    rpc = FakeRpc(native_balance=NATIVE_AFTER_THE_LIVE_RUN, wmon_balance=INPUT,
                  wmon_series=[INPUT, 0], moe_series=[0, 10**22])
    transport = FakePrivyTransport([signed_for(step) for step in ("approve", "swap", "revoke")])
    code = main(["--live", "--trade-file", str(path), "--store", str(tmp_path / "store"),
                 "--confirm", digest], environ=environment, rpc=rpc, privy_transport=transport)
    assert code == 0
    assert len(rpc.sent) == 3
    result = json.loads((tmp_path / "store" / "result.json").read_text(encoding="utf-8"))
    assert result["outcome"] == "SUCCESS"
    assert result["start"] == "WMON"
    assert [step["step"] for step in result["steps"]] == ["approve", "swap", "revoke"]
    assert result["balance"]["active_steps"] == ["approve", "swap", "revoke"]
    assert result["balance"]["gas_limit_total"] == 520_000
    assert result["gas_estimates"] == {"approve": 46_000, "swap": 300_000, "revoke": 46_000}
    assert result["post_checks"]["wmon_decrease_exactly_input"] is True
