"""Gas check: eth_call with the trade-file limit, eth_estimateGas and the 1.2 margin.

The 2026-10-22 live swap used 400000 of 400000 and status 0 while the estimate was 544967.
The dry run simulated with no gas field, so it could not catch the shortfall. These checks fail when
the estimate is absent, when the gas field is absent, or when the margin is not applied.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.operator_trade.dry_run import simulate
from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.plan import plan_trade
from scripts.operator_trade.preflight import read_preflight
from scripts.operator_trade.run import main
from scripts.operator_trade.trade_file import load_trade_file

from ._support import (
    SMALL_INPUT,
    FakePrivyTransport,
    FakeRpc,
    FakeTransport,
    small_trade_dict,
    signed_for,
    trade_dict,
    write_p256_key,
)

LOW_SWAP_ESTIMATE = {"wrap": 45_000, "approve": 46_000, "swap": 544_967, "revoke": 46_000}


def _setup(tmp_path: Path, rpc: FakeRpc | None = None, **overrides: object):
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict(**overrides)), encoding="utf-8")
    trade = load_trade_file(path)
    rpc = rpc or FakeRpc()
    preflight = read_preflight(rpc, trade)
    plan = plan_trade(trade, base_fee=preflight.base_fee, priority_fee=preflight.priority_fee,
                      reserve_wmon=preflight.reserve_wmon, reserve_moe=preflight.reserve_moe)
    return trade, preflight, plan, rpc


def _live(tmp_path: Path, rpc: FakeRpc, *, signer_factory, privy_transport) -> int:
    raw = json.dumps(small_trade_dict(), sort_keys=True, separators=(",", ":")).encode()
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
    return main(["--live", "--trade-file", str(path), "--store", str(tmp_path / "store"),
                 "--confirm", digest], environ=environment, rpc=rpc, privy_transport=privy_transport,
                signer_factory=signer_factory)


def test_a_gas_limit_below_the_estimate_is_refused_before_the_next_step(tmp_path: Path) -> None:
    rpc = FakeRpc(gas_estimates=dict(LOW_SWAP_ESTIMATE))
    trade, preflight, plan, rpc = _setup(tmp_path, rpc)
    with pytest.raises(OperatorError) as caught:
        simulate(rpc, trade, plan, preflight)
    assert caught.value.code == "GAS_LIMIT_TOO_LOW"
    assert "swap" in caught.value.detail
    assert "544967" in caught.value.detail


def test_live_refuses_a_low_gas_limit_before_any_signer_is_built(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rpc = FakeRpc(wmon_series=[0, SMALL_INPUT, 0], moe_series=[0, 10**18],
                  gas_estimates=dict(LOW_SWAP_ESTIMATE))
    created: list[str] = []

    def factory(step: str, nonce: int):
        created.append(step)
        raise AssertionError("a signer was built before the gas check")

    code = _live(tmp_path, rpc, signer_factory=factory, privy_transport=FakeTransport())
    output = capsys.readouterr().out
    assert code == 1
    assert "GAS_LIMIT_TOO_LOW" in output
    assert created == []
    assert not (tmp_path / "store" / "journal.jsonl").exists()
    assert rpc.sent == []


def test_a_gas_limit_at_the_margin_is_accepted(tmp_path: Path) -> None:
    trade, preflight, plan, rpc = _setup(tmp_path)
    results = simulate(rpc, trade, plan, preflight)
    assert all(item.ok for item in results)


def test_the_call_carries_the_trade_file_gas_limit_and_the_estimate_does_not(tmp_path: Path) -> None:
    trade, preflight, plan, rpc = _setup(tmp_path)
    simulate(rpc, trade, plan, preflight)
    swap_call = [params for method, params in rpc.calls
                 if method == "eth_call" and params[0]["data"].startswith("0xce1e7030")][0]
    assert swap_call[0]["gas"] == hex(400000)
    estimate = [params for method, params in rpc.calls if method == "eth_estimateGas"
                and params[0]["data"].startswith("0xce1e7030")][0]
    assert "gas" not in estimate[0]


def test_the_estimate_uses_the_same_state_overrides_as_the_call(tmp_path: Path) -> None:
    trade, preflight, plan, rpc = _setup(tmp_path)
    simulate(rpc, trade, plan, preflight)
    swap_call = [params for method, params in rpc.calls
                 if method == "eth_call" and params[0]["data"].startswith("0xce1e7030")][0]
    estimate = [params for method, params in rpc.calls if method == "eth_estimateGas"
                and params[0]["data"].startswith("0xce1e7030")][0]
    assert swap_call[2] == estimate[2]


def test_dry_run_reports_the_estimate_for_each_step(tmp_path: Path,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    rpc = FakeRpc()
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    code = main(["--trade-file", str(path)],
                environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"}, rpc=rpc)
    output = capsys.readouterr().out
    assert code == 0
    report = json.loads(output)
    assert [step["gas_estimate"] for step in report["steps"]] == [45_000, 46_000, 300_000, 46_000]
    assert report["gas_estimates"] == {"wrap": 45_000, "approve": 46_000, "swap": 300_000, "revoke": 46_000}


def test_dry_run_reports_the_balance_fit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rpc = FakeRpc()
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    code = main(["--trade-file", str(path)],
                environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"}, rpc=rpc)
    output = capsys.readouterr().out
    assert code == 0
    report = json.loads(output)
    assert report["balance"]["native_balance_wei"] == 10**21
    assert report["balance"]["gas_limit_total"] == 580_000
    assert report["balance"]["required_native_wei"] == report["plan"]["worst_case_wei"]
    assert report["balance"]["remaining_native_wei"] == 10**21 - report["balance"]["required_native_wei"]


def test_live_result_records_the_estimates(tmp_path: Path) -> None:
    raw = json.dumps(small_trade_dict(), sort_keys=True, separators=(",", ":")).encode()
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
    rpc = FakeRpc(wmon_series=[0, SMALL_INPUT, 0], moe_series=[0, 10**18])
    transport = FakePrivyTransport([signed_for(step) for step in ("wrap", "approve", "swap", "revoke")])
    code = main(["--live", "--trade-file", str(path), "--store", str(tmp_path / "store"),
                 "--confirm", digest], environ=environment, rpc=rpc, privy_transport=transport)
    assert code == 0
    result = json.loads((tmp_path / "store" / "result.json").read_text(encoding="utf-8"))
    assert result["gas_estimates"]["swap"] == 300_000
    assert result["start"] == "MON"
