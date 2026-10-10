"""Authored interpretation cases as provider scripts for the pinned-Hermes container job, and a queue for processes.

The case files are hand-written under `apps/api/tests/fixtures/hermes_interpretation`. They are not recorded from any
model. `ScriptQueue` lets a test control what a long-running local API process answers, one turn at a time.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "apps" / "api" / "tests" / "fixtures" / "hermes_interpretation"


def load_case(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / "cases" / f"{name}.json").read_text(encoding="utf-8"))


def load_follow_up(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / "follow_ups" / f"{name}.json").read_text(encoding="utf-8"))


def provider_script(provider: Mapping[str, Any]) -> dict[str, Any]:
    """The fake provider's behaviour for one authored case (what the container job is told to do)."""
    if provider["kind"] != "content":
        return dict(provider)
    text = json.dumps(provider["model_response"]) if "model_response" in provider else provider["model_text"]
    return {"kind": "content", "content": text, "finish_reason": provider["finish_reason"], "usage": provider["usage"]}


class ScriptQueue:
    """A JSON list of `{"case": name}`, `{"follow_up": name}` or `{"provider": {...}}` items, consumed one per turn.

    A test appends items to the file before each action. The file lives in a private test folder.
    """

    def __init__(self, path: Path) -> None:
        self.path, self._lock = path, threading.Lock()

    def __call__(self, _turn: object) -> dict[str, Any]:
        with self._lock:
            items = json.loads(self.path.read_text(encoding="utf-8"))
            if not items:
                raise RuntimeError("the script queue is empty")
            item = items.pop(0)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(items), encoding="utf-8")
            os.replace(temporary, self.path)
        if "case" in item:
            return provider_script(load_case(item["case"])["provider"])
        if "follow_up" in item:
            return provider_script(load_follow_up(item["follow_up"])["provider"])
        return provider_script(item["provider"])
