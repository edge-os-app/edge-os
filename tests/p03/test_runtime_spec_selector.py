"""Regression: the verifier's runtime phase selects only `runtime.spec.mjs` (R58 L2 upstream selector repair).

The phase passed the bare file filter `runtime.spec.mjs`, which Playwright also matched to `agent-health-runtime.spec.mjs`
(P31), whose tests need their own runner's owners and agents. This test runs the real `runtime_phase.drive` with its
server, SQL and process checks replaced, captures the Playwright file arguments it passes, and matches them against the
real spec files in this folder the way the installed Playwright 1.64.0 CLI does (`lib/common/index.js`:
`parseLocationArg`, then `forceRegExp` with flags "gi", tested against the absolute spec path).

Pure host check: no Playwright, browser, server, database or network runs. Run from `apps/api`:
`uv run --frozen pytest -p no:cacheprovider ../../tests/p03/test_runtime_spec_selector.py`
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts" / "p03"))

import runtime_phase  # noqa: E402


def playwright_file_regex(arg: str) -> re.Pattern[str]:
    """One CLI file argument as Playwright 1.64.0 compiles it: a trailing `:line[:column]` is not part of the file
    filter; `/source/flags` is a regex literal; anything else is a case-insensitive regex."""
    location = re.match(r"^(.*?):(\d+):?(\d+)?$", arg)
    pattern = location.group(1) if location else arg
    literal = re.match(r"^/(.*)/([gi]*)$", pattern)
    if literal:
        return re.compile(literal.group(1), re.IGNORECASE if "i" in literal.group(2) else 0)
    return re.compile(pattern, re.IGNORECASE)


def selected(args: list[str]) -> list[str]:
    """The spec files in this folder that the given file arguments select."""
    assert not any(arg.startswith("-") for arg in args), "only file arguments are modelled here"
    matchers = [playwright_file_regex(arg) for arg in args]
    return sorted(spec.name for spec in HERE.glob("*.spec.mjs")
                  if any(matcher.search(str(spec)) for matcher in matchers))


class Recorder:
    def write(self, name: str, value: Any) -> None:
        pass

    def step(self, name: str, ok: bool, detail: Any = None) -> bool:
        return ok


def phase_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every `run_playwright` file-argument list the real runtime phase passes."""
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "financial-results.json").write_text(json.dumps({"main-desktop": {"agentId": "agent"}}))
    for check in ("projection_checks", "quota_checks", "second_process_checks", "drift_checks"):
        monkeypatch.setattr(runtime_phase, check, lambda *args, **kwargs: {"checks": {}})
    calls: list[list[str]] = []

    def run_playwright(specs: list[str], env: dict[str, str], log: Path) -> int:
        calls.append(list(specs))
        return 0

    ui_env = {"P03_API_URL": "http://127.0.0.1:9", "P03_TOKEN_A": "a", "P03_TOKEN_B": "b"}
    assert runtime_phase.drive(Recorder(), None, {}, tmp_path, ui_env, run_playwright, [], None) is True
    return calls


def test_the_bare_file_name_also_selects_the_p31_health_spec():
    """The matcher reproduces the H2 verifier log: the old argument selected both files."""
    assert selected(["runtime.spec.mjs"]) == ["agent-health-runtime.spec.mjs", "runtime.spec.mjs"]


def test_the_runtime_phase_selects_exactly_the_runtime_spec(tmp_path, monkeypatch):
    calls = phase_arguments(tmp_path, monkeypatch)
    assert len(calls) == 1
    assert selected(calls[0]) == ["runtime.spec.mjs"]
