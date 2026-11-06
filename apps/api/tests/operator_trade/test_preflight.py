"""Preflight reads and refusals: pins, code hashes, allowance and balance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.preflight import read_preflight
from scripts.operator_trade.trade_file import load_trade_file

from ._support import INPUT, POOL, WMON, FakeRpc, trade_dict


def _trade(tmp_path: Path, **overrides: object):
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict(**overrides)), encoding="utf-8")
    return load_trade_file(path)


def test_reads_all_required_values(tmp_path: Path) -> None:
    reads = read_preflight(FakeRpc(), _trade(tmp_path))
    assert reads.chain_id == 143
    assert reads.block_number == 16
    assert reads.native_balance == 10**21
    assert reads.wmon_balance == 0
    assert reads.allowance == 0
    assert reads.token0.lower() == WMON.lower()
    assert reads.nonce == 7
    assert reads.base_fee == 10**9
    assert reads.priority_fee == 10**9
    assert reads.reserve_wmon == 862430562121790033386323


def test_refuses_a_wrong_chain(tmp_path: Path) -> None:
    rpc = FakeRpc()
    rpc.call = lambda method, params: "0x1" if method == "eth_chainId" else FakeRpc.call(rpc, method, params)
    with pytest.raises(OperatorError) as caught:
        read_preflight(rpc, _trade(tmp_path))
    assert caught.value.code == "CHAIN_ID_MISMATCH"


def test_refuses_a_nonzero_start_allowance(tmp_path: Path) -> None:
    with pytest.raises(OperatorError) as caught:
        read_preflight(FakeRpc(allowance=1), _trade(tmp_path))
    assert caught.value.code == "ALLOWANCE_NOT_ZERO"


def test_refuses_a_changed_entrypoint_code_hash(tmp_path: Path) -> None:
    rpc = FakeRpc(code={**_code(), "entrypoint": "0x6009"})
    with pytest.raises(OperatorError) as caught:
        read_preflight(rpc, _trade(tmp_path))
    assert caught.value.code == "CODE_HASH_MISMATCH"
    assert "entrypoint" in str(caught.value.detail)


def test_refuses_a_changed_wmon_code_hash(tmp_path: Path) -> None:
    rpc = FakeRpc(code={**_code(), "wmon": "0x6009"})
    with pytest.raises(OperatorError) as caught:
        read_preflight(rpc, _trade(tmp_path))
    assert caught.value.code == "CODE_HASH_MISMATCH"


def test_refuses_a_changed_pool_code_hash(tmp_path: Path) -> None:
    rpc = FakeRpc(code={**_code(), "pool": "0x6009"})
    with pytest.raises(OperatorError) as caught:
        read_preflight(rpc, _trade(tmp_path))
    assert caught.value.code == "CODE_HASH_MISMATCH"


def test_refuses_wrong_token_order(tmp_path: Path) -> None:
    rpc = FakeRpc()
    original = rpc.call

    def swapped(method: str, params):
        if method == "eth_call" and params[0]["data"] == "0x0dfe1681":
            return "0x" + "0" * 24 + "d8e004acba279417c04c0633cb5a21ceca207777"
        return original(method, params)

    rpc.call = swapped
    with pytest.raises(OperatorError) as caught:
        read_preflight(rpc, _trade(tmp_path))
    assert caught.value.code == "TOKEN_ORDER_MISMATCH"


def test_refuses_a_native_balance_below_value_plus_gas(tmp_path: Path) -> None:
    with pytest.raises(OperatorError) as caught:
        read_preflight(FakeRpc(native_balance=INPUT), _trade(tmp_path))
    assert caught.value.code == "INSUFFICIENT_NATIVE_BALANCE"


def test_reads_the_code_of_all_three_pinned_addresses(tmp_path: Path) -> None:
    rpc = FakeRpc()
    read_preflight(rpc, _trade(tmp_path))
    code_reads = [params[0].lower() for method, params in rpc.calls if method == "eth_getCode"]
    assert code_reads.count(POOL.lower()) == 1
    assert code_reads.count(WMON.lower()) == 1
    assert len(code_reads) == 3


def _code() -> dict[str, str]:
    from ._support import FAKE_CODE

    return dict(FAKE_CODE)
