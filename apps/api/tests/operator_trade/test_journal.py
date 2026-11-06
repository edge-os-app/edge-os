"""Journal: created new, append-only, fsynced before send, and never resent after an unknown outcome."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operator_trade.errors import OperatorError
from scripts.operator_trade.journal import Journal


def test_create_refuses_a_non_empty_store(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "something.txt").write_text("x", encoding="utf-8")
    with pytest.raises(OperatorError) as caught:
        Journal.create(store)
    assert caught.value.code == "STORE_NOT_EMPTY"


def test_create_refuses_an_existing_journal(tmp_path: Path) -> None:
    store = tmp_path / "store"
    Journal.create(store)
    with pytest.raises(OperatorError) as caught:
        Journal.create(store)
    assert caught.value.code == "STORE_NOT_EMPTY"


def test_records_survive_reopen_in_order(tmp_path: Path) -> None:
    store = tmp_path / "store"
    journal = Journal.create(store)
    journal.append({"event": "prepared", "step": "wrap", "nonce": 7, "request_hash": "aa"})
    journal.append({"event": "before_send", "step": "wrap", "nonce": 7, "tx_hash": "bb"})
    lines = (store / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["prepared", "before_send"]
    assert (store / "journal.jsonl").stat().st_mode & 0o777 == 0o600


def test_append_writes_one_complete_line_per_record(tmp_path: Path) -> None:
    journal = Journal.create(tmp_path / "store")
    journal.append({"event": "one"})
    journal.append({"event": "two"})
    raw = (tmp_path / "store" / "journal.jsonl").read_bytes()
    assert raw.endswith(b"\n")
    assert len(raw.splitlines()) == 2


def test_open_for_resume_refuses(tmp_path: Path) -> None:
    journal = Journal.create(tmp_path / "store")
    journal.append({"event": "unknown", "step": "swap", "liability": "UNKNOWN"})
    with pytest.raises(OperatorError) as caught:
        Journal.create(tmp_path / "store")
    assert caught.value.code == "STORE_NOT_EMPTY"
