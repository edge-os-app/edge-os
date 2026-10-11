"""Authored interpretation cases as scripted Hermes turn results, for tests that stand in for the provider.

The case files hold what a provider returned for each authored request. They are hand-written, not recorded from any
model. `CaseRunner` replays them at the Hermes process boundary; the actual-Hermes tests replay the same files through
the pinned container instead.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import Usage

CASES_DIR = Path(__file__).parent / "fixtures" / "hermes_interpretation" / "cases"
OBSERVED_OK = {"tools_effective": [], "fallback_count": 0, "streaming_disabled": True, "skip_memory_effective": True,
               "api_max_retries": 1, "wire_system_contains_prompt": True, "wire_user_message_verbatim": True,
               "wire_request_sha256": "e" * 64}


def case(name: str) -> dict[str, Any]:
    return json.loads((CASES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def intake_body(name: str) -> dict[str, Any]:
    return dict(case(name)["intake"])


def provider_text(provider: dict[str, Any]) -> str:
    return json.dumps(provider["model_response"]) if "model_response" in provider else provider["model_text"]


def turn_result(provider: dict[str, Any]) -> HermesTurnResult:
    """What the pinned Hermes boundary reports for one authored provider behaviour."""
    kind = provider["kind"]
    if kind == "http_error":
        return HermesTurnResult("PROVIDER_FAILED", None, Usage(), 1, OBSERVED_OK, "ProviderHTTPError")
    if kind == "hang":
        return HermesTurnResult("TIMED_OUT", None, Usage(), None, {}, "TimeoutExpired")
    usage = provider.get("usage")
    reported = Usage(usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"],
                     "PROVIDER_REPORTED") if usage else Usage()
    status = "TRUNCATED" if provider["finish_reason"] == "length" else "RETURNED"
    return HermesTurnResult(status, provider_text(provider), reported, 1, OBSERVED_OK, None)


def reply(model_response: dict[str, Any], usage: Usage | None = None, **changes: Any) -> HermesTurnResult:
    """A returned turn for a response the test builds itself (follow-ups, conflicts)."""
    base = dict(status="RETURNED", text=json.dumps(model_response), usage=usage or Usage(900, 120, 1020, "PROVIDER_REPORTED"),
                request_count=1, observed=OBSERVED_OK, error_class=None)
    return HermesTurnResult(**{**base, **changes})


class CaseRunner:
    """Returns the next scripted result and keeps every turn it was given. A script item may be a callable."""

    def __init__(self, *script: HermesTurnResult | BaseException | Callable[[HermesTurn], HermesTurnResult]) -> None:
        self.script = list(script)
        self.turns: list[HermesTurn] = []
        self._lock = threading.Lock()

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        with self._lock:
            self.turns.append(turn)
            item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item(turn) if callable(item) else item
