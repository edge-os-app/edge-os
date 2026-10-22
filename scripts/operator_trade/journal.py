"""Append-only, fsynced journal for one operator run.

The journal is written before every external effect. A new run refuses an existing journal, so an
unknown outcome is never repaired by sending the same step again. Each record is one JSON line,
written and fsynced before the caller may sign or send.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scripts.operator_trade.errors import OperatorError

JOURNAL_NAME = "journal.jsonl"


class Journal:
    def __init__(self, store: Path, descriptor: int) -> None:
        self.store = store
        self.path = store / JOURNAL_NAME
        self._descriptor = descriptor

    @classmethod
    def create(cls, store: Path) -> "Journal":
        store = Path(store)
        if store.exists():
            if not store.is_dir() or any(store.iterdir()):
                raise OperatorError("STORE_NOT_EMPTY", store.name)
        else:
            try:
                store.mkdir(parents=True, mode=0o700)
            except OSError as error:
                raise OperatorError("STORE_UNAVAILABLE", store.name) from error
        try:
            descriptor = os.open(store / JOURNAL_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise OperatorError("STORE_NOT_EMPTY", store.name) from error
        except OSError as error:
            raise OperatorError("STORE_UNAVAILABLE", store.name) from error
        _fsync_directory(store)
        return cls(store, descriptor)

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        try:
            os.write(self._descriptor, line.encode("utf-8"))
            os.fsync(self._descriptor)
        except OSError as error:
            raise OperatorError("JOURNAL_WRITE_FAILED") from error

    def records(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_result(store: Path, result: dict[str, Any]) -> None:
    """Write the final result durably as one JSON object, then fsync the directory."""
    store = Path(store)
    temporary = store / "result.json.tmp"
    final = store / "result.json"
    encoded = json.dumps(result, indent=1, sort_keys=True, ensure_ascii=True).encode("utf-8") + b"\n"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, final)
    _fsync_directory(store)
