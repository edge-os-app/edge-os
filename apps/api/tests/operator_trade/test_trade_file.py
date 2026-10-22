"""The frozen operator trade file: strict fields, pins and refusals."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.trade_file import load_trade_file

from ._support import INPUT, trade_dict


def _write(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_loads_and_hashes_the_frozen_bytes(tmp_path: Path) -> None:
    path = _write(tmp_path / "trade.json", trade_dict())
    trade = load_trade_file(path)
    assert trade.input_raw == INPUT
    assert trade.slippage_bps == 100
    assert trade.usd_ceiling == Decimal("2.00")
    assert trade.gas_limits.swap == 400000
    assert len(trade.file_sha256) == 64


def test_unknown_field_is_refused(tmp_path: Path) -> None:
    value = trade_dict()
    value["unreviewed_extra"] = 1
    with pytest.raises(OperatorError) as caught:
        load_trade_file(_write(tmp_path / "trade.json", value))
    assert caught.value.code == "TRADE_FILE_INVALID"


@pytest.mark.parametrize(
    "overrides",
    [
        {"chain_id": 1},
        {"wallet_address": "0x1234"},
        {"input_raw": "0"},
        {"input_raw": "7" * 30},
        {"input_raw": str(70 * 10**18 + 1)},
        {"slippage_bps": -1},
        {"slippage_bps": 10001},
        {"usd_ceiling": "2.01"},
        {"mon_usd_price": "0"},
        {"direction": 2},
        {"direction": 1},
        {"program_fee_ppm": 15000},
        {"wallet_address": "0x" + "1" * 40},
        {"wallet_id": "other-wallet"},
        {"pool": "0x" + "9" * 40},
        {"entrypoint": "0x" + "9" * 40},
        {"wmon": "0x" + "9" * 40, "token0": "0x" + "9" * 40, "token1": "0x" + "8" * 40, "moe": "0x" + "8" * 40},
        {"program_fee_ppm": 0},
        {"token0": "0x" + "2" * 40},
        {"entrypoint": "0x" + "0" * 40},
        {"gas_limits": {"wrap": 0, "approve": 60000, "swap": 400000, "revoke": 60000}},
        {"gas_limits": {"wrap": 60000, "approve": 60000, "swap": 400000}},
        {"code_sha256": {"entrypoint": "zz", "wmon": "0" * 64, "pool": "0" * 64}},
        {"receipt_timeout_seconds": 0},
        {"receipt_poll_seconds": 0},
    ],
)
def test_invalid_field_is_refused(tmp_path: Path, overrides: dict[str, object]) -> None:
    with pytest.raises(OperatorError) as caught:
        load_trade_file(_write(tmp_path / "trade.json", trade_dict(**overrides)))
    assert caught.value.code == "TRADE_FILE_INVALID"


def test_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(OperatorError) as caught:
        load_trade_file(tmp_path / "absent.json")
    assert caught.value.code == "TRADE_FILE_UNREADABLE"


def test_non_json_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "trade.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(OperatorError) as caught:
        load_trade_file(path)
    assert caught.value.code == "TRADE_FILE_INVALID"


def test_duplicate_json_key_is_refused(tmp_path: Path) -> None:
    body = json.dumps(trade_dict())[:-1] + ', "chain_id": 1}'
    path = tmp_path / "trade.json"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(OperatorError) as caught:
        load_trade_file(path)
    assert caught.value.code == "TRADE_FILE_INVALID"
