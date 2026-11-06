"""Dry run: read-only, ordered eth_call simulation with state overrides, and no signer or send."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operator_trade.dry_run import _allowance_slot, _balance_slot, build_unsigned, simulate
from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.plan import plan_trade
from scripts.operator_trade.preflight import read_preflight
from scripts.operator_trade.run import main
from scripts.operator_trade.trade_file import load_trade_file

from ._support import ENTRYPOINT, INPUT, MOE, WALLET, WMON, FakeRpc, FakeTransport, trade_dict


def _setup(tmp_path: Path, rpc: FakeRpc):
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    trade = load_trade_file(path)
    preflight = read_preflight(rpc, trade)
    plan = plan_trade(trade, base_fee=preflight.base_fee, priority_fee=preflight.priority_fee,
               reserve_wmon=preflight.reserve_wmon, reserve_moe=preflight.reserve_moe)
    return trade, preflight, plan


def test_builds_the_four_unsigned_transactions_with_sequential_nonces(tmp_path: Path) -> None:
    rpc = FakeRpc()
    trade, preflight, plan = _setup(tmp_path, rpc)
    unsigned = build_unsigned(trade, plan, preflight)
    assert [item.step for item in unsigned] == ["wrap", "approve", "swap", "revoke"]
    assert [item.nonce for item in unsigned] == [7, 8, 9, 10]
    assert unsigned[2].value == 0
    assert unsigned[2].to.lower() == ENTRYPOINT.lower()


def test_simulates_in_order_and_returns_the_swap_output(tmp_path: Path) -> None:
    rpc = FakeRpc()
    trade, preflight, plan = _setup(tmp_path, rpc)
    results = simulate(rpc, trade, plan, preflight)
    assert [item.step for item in results] == ["wrap", "approve", "swap", "revoke"]
    assert results[2].output_raw == rpc.simulation_output
    assert all(item.ok for item in results)
    simulated = [params[0]["data"][:10].lower() for method, params in rpc.calls if method == "eth_call"]
    assert simulated[-4:] == ["0xd0e30db0", "0x095ea7b3", "0xce1e7030", "0x095ea7b3"]


def test_swap_simulation_carries_state_overrides_for_balance_and_allowance(tmp_path: Path) -> None:
    rpc = FakeRpc()
    trade, preflight, plan = _setup(tmp_path, rpc)
    simulate(rpc, trade, plan, preflight)
    swap_call = [params for method, params in rpc.calls
                 if method == "eth_call" and params[0]["data"].startswith("0xce1e7030")][0]
    overrides = swap_call[2]
    assert WMON in overrides
    diff = overrides[WMON]["stateDiff"]
    assert len(diff) == 2
    assert _allowance_slot(WALLET, ENTRYPOINT) in diff
    assert _balance_slot(WALLET) in diff
    assert all(value.startswith("0x") and len(value) == 66 for value in diff.values())


def test_override_slots_match_the_verified_live_check() -> None:
    # Values from LIVE_QUOTE_CHECK1.json / live_quote_check.py, verified on chain on 2026-10-22.
    assert _balance_slot("0x91BB52A63c91986813288965e4681FF111De1b63") == (
        "0x512122ff3a68042a10b19b8f2998bb3d97fcfce5adceffb9a46b9d83ad080440"
    )
    assert _allowance_slot("0x91BB52A63c91986813288965e4681FF111De1b63", ENTRYPOINT) == (
        "0x796909ea87f663ee5354b522fe6b6c9de2d7ef93623767cfb826d05606973b87"
    )


def test_refuses_a_reverting_swap_simulation(tmp_path: Path) -> None:
    rpc = FakeRpc(reverting_swap=True)
    trade, preflight, plan = _setup(tmp_path, rpc)
    with pytest.raises(OperatorError) as caught:
        simulate(rpc, trade, plan, preflight)
    assert caught.value.code == "SIMULATION_FAILED"


def test_dry_run_never_signs_sends_or_writes_a_store(tmp_path: Path) -> None:
    rpc = FakeRpc()
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    code = main(["--trade-file", str(path)], environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"},
                rpc=rpc)
    assert code == 0
    assert not rpc.sent
    assert "eth_sendRawTransaction" not in [method for method, _ in rpc.calls]
    assert list(tmp_path.glob("store")) == []


def test_dry_run_output_has_the_plan_and_no_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rpc = FakeRpc()
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    secret_url = "https://rpc.invalid/key-secret-path"
    code = main(["--trade-file", str(path)],
                environ={"EDGE_OS_OPERATOR_RPC_URL": secret_url, "EDGE_OS_PRIVY_APP_SECRET": "app-secret"},
                rpc=rpc)
    output = capsys.readouterr().out
    assert code == 0
    assert '"expected_raw"' in output
    assert '"minimum_raw"' in output
    assert '"worst_case_usd"' in output
    assert "key-secret-path" not in output
    assert "app-secret" not in output


def test_dry_run_reports_the_signer_quantity_gap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rpc = FakeRpc()
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    code = main(["--trade-file", str(path)], environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"}, rpc=rpc)
    output = capsys.readouterr().out
    assert code == 0
    assert "2**53-1" in output


def test_dry_run_refuses_without_the_rpc_environment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    code = main(["--trade-file", str(path)], environ={}, transport=FakeTransport())
    assert code == 1
    assert "ENV_MISSING" in capsys.readouterr().out


def test_dry_run_does_not_touch_the_live_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.operator_trade.run as run_module

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the dry run touched the live path")

    monkeypatch.setattr(run_module, "load_live_environment", refuse)
    monkeypatch.setattr(run_module, "build_signer_factory", refuse)
    monkeypatch.setattr(run_module, "execute", refuse)
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    code = main(["--trade-file", str(path)], environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"},
                rpc=FakeRpc())
    assert code == 0


def test_a_refusal_never_echoes_the_rpc_url(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rpc = FakeRpc()
    rpc.fail_methods = {"eth_chainId"}
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    secret_url = "https://rpc.invalid/key-secret-path"
    code = main(["--trade-file", str(path)], environ={"EDGE_OS_OPERATOR_RPC_URL": secret_url}, rpc=rpc)
    output = capsys.readouterr().out
    assert code == 1
    assert "key-secret-path" not in output


def test_dry_run_completes_through_the_real_rpc_client(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.operator_trade.rpc import OperatorRpc

    from ._support import RpcTransport

    fake = FakeRpc()
    rpc = OperatorRpc(transport=RpcTransport(fake), endpoint="https://rpc.invalid/key")
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    code = main(["--trade-file", str(path)], environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"}, rpc=rpc)
    output = capsys.readouterr().out
    assert code == 0, output
    assert '"mode": "DRY_RUN"' in output
    assert '"simulations"' in output
    assert fake.sent == []
