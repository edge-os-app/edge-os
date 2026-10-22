"""The operator CLI: dry run is the default; live needs a hash confirmation, a new store and environment credentials."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.operator_trade.run import main

from ._support import (
    SMALL_INPUT,
    FakePrivyTransport,
    FakeRpc,
    small_trade_dict,
    signed_for,
    write_p256_key,
)


def _trade(tmp_path: Path, **overrides: object) -> tuple[Path, str]:
    raw = json.dumps(small_trade_dict(**overrides), sort_keys=True, separators=(",", ":")).encode()
    path = tmp_path / "trade.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    key_path = tmp_path / "agent-key.pem"
    write_p256_key(key_path)
    value = {
        "EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key-secret-path",
        "EDGE_OS_PRIVY_APP_ID": "app-id",
        "EDGE_OS_PRIVY_APP_SECRET": "app-secret",
        "EDGE_OS_PRIVY_AGENT_KEY_FILE": str(key_path),
    }
    value.update(overrides)
    return value


def _rpc() -> FakeRpc:
    return FakeRpc(wmon_series=[0, SMALL_INPUT, 0], moe_series=[0, 10**18])


def test_live_requires_a_confirmation_hash(tmp_path: Path) -> None:
    path, _ = _trade(tmp_path)
    code = main(["--live", "--trade-file", str(path), "--store", str(tmp_path / "store")],
                environ=_env(tmp_path), rpc=_rpc(), privy_transport=FakePrivyTransport([]))
    assert code == 1


def test_live_refuses_a_wrong_confirmation_hash(tmp_path: Path) -> None:
    path, _ = _trade(tmp_path)
    code = main(["--live", "--trade-file", str(path), "--store", str(tmp_path / "store"),
                 "--confirm", "0" * 64], environ=_env(tmp_path), rpc=_rpc(),
                privy_transport=FakePrivyTransport([]))
    assert code == 1


def test_live_refuses_a_non_empty_store(tmp_path: Path) -> None:
    path, digest = _trade(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    (store / "journal.jsonl").write_text("", encoding="utf-8")
    code = main(["--live", "--trade-file", str(path), "--store", str(store), "--confirm", digest],
                environ=_env(tmp_path), rpc=_rpc(), privy_transport=FakePrivyTransport([]))
    assert code == 1


def test_live_refuses_without_the_privy_environment(tmp_path: Path) -> None:
    path, digest = _trade(tmp_path)
    code = main(["--live", "--trade-file", str(path), "--store", str(tmp_path / "store"), "--confirm", digest],
                environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"}, rpc=_rpc(),
                privy_transport=FakePrivyTransport([]))
    assert code == 1


def test_live_reads_a_missing_key_file_as_a_refusal(tmp_path: Path) -> None:
    path, digest = _trade(tmp_path)
    env = _env(tmp_path)
    env["EDGE_OS_PRIVY_AGENT_KEY_FILE"] = str(tmp_path / "absent.pem")
    code = main(["--live", "--trade-file", str(path), "--store", str(tmp_path / "store"), "--confirm", digest],
                environ=env, rpc=_rpc(), privy_transport=FakePrivyTransport([]))
    assert code == 1


def test_store_is_only_valid_with_live(tmp_path: Path) -> None:
    path, _ = _trade(tmp_path)
    code = main(["--dry-run", "--trade-file", str(path), "--store", str(tmp_path / "store")],
                environ={"EDGE_OS_OPERATOR_RPC_URL": "https://rpc.invalid/key"}, rpc=_rpc())
    assert code == 1


def test_live_run_writes_the_journal_and_result_without_secrets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path, digest = _trade(tmp_path)
    store = tmp_path / "store"
    rpc = _rpc()
    transport = FakePrivyTransport([signed_for(step) for step in ("wrap", "approve", "swap", "revoke")])
    code = main(["--live", "--trade-file", str(path), "--store", str(store), "--confirm", digest],
                environ=_env(tmp_path), rpc=rpc, privy_transport=transport)
    output = capsys.readouterr().out
    assert code == 0
    assert len(rpc.sent) == 4
    assert len(transport.urls) == 4
    result = json.loads((store / "result.json").read_text(encoding="utf-8"))
    assert result["outcome"] == "SUCCESS"
    assert [step["step"] for step in result["steps"]] == ["wrap", "approve", "swap", "revoke"]
    assert all(step["tx_hash"].startswith("0x") and len(step["tx_hash"]) == 66 for step in result["steps"])
    assert all(step["receipt_block"] is not None for step in result["steps"])
    assert result["post_checks"]["allowance_zero"] is True
    assert result["post_checks"]["moe_increase_at_least_minimum"] is True
    assert result["post_checks"]["wmon_decrease_exactly_input"] is True
    assert result["post_checks"]["entrypoint_code_unchanged"] is True
    evidence = (store / "journal.jsonl").read_text(encoding="utf-8") + (store / "result.json").read_text(encoding="utf-8")
    for secret in ("app-secret", "key-secret-path", str(tmp_path / "agent-key.pem")):
        assert secret not in evidence
        assert secret not in output


def test_a_second_live_run_refuses_the_existing_journal(tmp_path: Path) -> None:
    path, digest = _trade(tmp_path)
    store = tmp_path / "store"
    transport = FakePrivyTransport([signed_for(step) for step in ("wrap", "approve", "swap", "revoke")])
    first = main(["--live", "--trade-file", str(path), "--store", str(store), "--confirm", digest],
                 environ=_env(tmp_path), rpc=_rpc(), privy_transport=transport)
    assert first == 0
    second_rpc = _rpc()
    second = main(["--live", "--trade-file", str(path), "--store", str(store), "--confirm", digest],
                  environ=_env(tmp_path), rpc=second_rpc, privy_transport=FakePrivyTransport([]))
    assert second == 1
    assert second_rpc.sent == []


def test_a_failed_post_check_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path, digest = _trade(tmp_path)
    store = tmp_path / "store"
    rpc = _rpc()
    rpc.moe_series = []
    rpc.moe_balance = 0
    transport = FakePrivyTransport([signed_for(step) for step in ("wrap", "approve", "swap", "revoke")])
    code = main(["--live", "--trade-file", str(path), "--store", str(store), "--confirm", digest],
                environ=_env(tmp_path), rpc=rpc, privy_transport=transport)
    assert code == 1
    result = json.loads((store / "result.json").read_text(encoding="utf-8"))
    assert result["post_checks"]["moe_increase_at_least_minimum"] is False


def test_live_run_completes_through_the_real_rpc_client(tmp_path: Path) -> None:
    from scripts.operator_trade.rpc import OperatorRpc

    from ._support import RpcTransport

    path, digest = _trade(tmp_path)
    fake = _rpc()
    rpc = OperatorRpc(transport=RpcTransport(fake), endpoint="https://rpc.invalid/key")
    transport = FakePrivyTransport([signed_for(step) for step in ("wrap", "approve", "swap", "revoke")])
    code = main(["--live", "--trade-file", str(path), "--store", str(tmp_path / "store"), "--confirm", digest],
                environ=_env(tmp_path), rpc=rpc, privy_transport=transport)
    assert code == 0
    assert len(fake.sent) == 4
