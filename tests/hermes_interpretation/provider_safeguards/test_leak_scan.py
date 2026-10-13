"""The secret scanner must find a secret in the forms a writer could produce, or the leak tests prove nothing."""

from __future__ import annotations

import base64
import urllib.parse
from pathlib import Path

import pytest

from leak_scan import find_leaks

SECRET = "sk-test-DUMMY-SENTINEL-0123456789abcdef"


@pytest.mark.parametrize("written", [
    SECRET, urllib.parse.quote(SECRET, safe=""), base64.b64encode(SECRET.encode()).decode(),
    base64.b64encode(f"Bearer {SECRET}".encode()).decode(), SECRET[::-1], SECRET.upper(), SECRET.lower(),
    SECRET.encode().hex(), SECRET.encode().hex().upper(), base64.b64encode(b"xx" + SECRET.encode()).decode()[3:-2],
    base64.b64encode(b"x" + SECRET.encode()).decode()[2:-2], SECRET.replace("-", "\\u002d")])
def test_a_secret_written_in_any_known_form_is_found(tmp_path: Path, written: str) -> None:
    (tmp_path / "deep" / "er").mkdir(parents=True)
    (tmp_path / "deep" / "er" / "log.txt").write_text(f"line before {written} line after")

    assert find_leaks(tmp_path, SECRET) == ["deep/er/log.txt"]


def test_a_clean_tree_reports_nothing_and_the_source_file_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "private-credential"
    source.write_text(SECRET)
    (tmp_path / "evidence.json").write_text('{"ok": true}')

    assert find_leaks(tmp_path, SECRET, exclude=[source]) == []
    assert find_leaks(tmp_path, SECRET) == ["private-credential"]
