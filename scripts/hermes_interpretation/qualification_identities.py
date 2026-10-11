"""Computes the identities that the real-model qualification proposal pins. Support code, makes no request.

`python qualification_identities.py` prints them as JSON. `docs/qualification/hermes-provider/IDENTITIES.json` is the
committed copy, and a test fails when the two differ. Run it from `apps/api` with the API's Python so the application
modules import.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research import hermes_interpreter as hermes
from edge_os_api.research.hermes_interpreter import HermesInterpreter, HermesInterpreterConfig, HermesTurn, HermesTurnResult
from edge_os_api.research.interpretation_attempts import AttemptLedger, Usage
from edge_os_api.research.interpretation_response import ClarificationAnswer

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PACKAGE = REPO / "docs" / "qualification" / "hermes-provider"
BASE_COMMIT = "3ab45e7240910433f4bdcd84eae86833dd9f406c"
SUPPORT_FILES = ["Dockerfile", "hermes_turn_job.py", "docker_turn_runner.py", "guarded_turn_job.py", "guarded_docker_runner.py",
                 "provider_guard.py", "spend_ledger.py", "guarded_turn_runner.py", "meaning_check.py", "leak_scan.py"]
# Largest wire request seen in the controlled pinned-Hermes run of all 11 cases: 7,754 bytes (first turn), 9,510 (follow-up).
LIMITS = {"max_request_bytes": {"first": 8448, "follow_up": 10240}, "max_envelope_chars": 2500, "input_token_margin": 64,
          "max_output_tokens": 4096, "whole_process_deadline_seconds": 60, "retry_slots": 4, "cumulative_cap_usd": "0.75"}
# Probe A's last recorded ceilings. They are NOT current prices. Read the provider's public price list at release time.
STALE_PRICES_USD_PER_MILLION = {"prompt": "2.00", "completion": "7.50"}
PROPOSED = {"model": "openai/gpt-6.1-sol", "route": "openrouter-openai-flex", "max_output_tokens": 4096}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Capture:
    """Stands in for the process boundary and keeps the turn that the interpreter built. It answers nothing."""

    def __init__(self) -> None:
        self.turn: HermesTurn | None = None

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        self.turn = turn
        return HermesTurnResult("UNKNOWN", None, Usage(), None, {}, "Captured")


def _interpreter(capture: Capture) -> HermesInterpreter:
    from itertools import count

    sys.path.insert(0, str(REPO / "apps" / "api" / "tests"))  # the append-only MemoryAttemptStore of the unit tests
    from test_interpretation_attempts import MemoryAttemptStore
    ids = count(1)
    ledger = AttemptLedger(MemoryAttemptStore(), new_id=lambda: f"attempt-{next(ids)}",
                           now=lambda: dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc))
    return HermesInterpreter(HermesInterpreterConfig(**PROPOSED), capture, ledger, monotonic=lambda: 0.0)


def case_identities(manifest: dict[str, Any]) -> dict[str, Any]:
    from authored_cases import load_case
    from edge_os_api.research.hermes_interpreter import apply_choice_answer
    from edge_os_api.research.interpretation_response import parse_interpretation_response

    out: dict[str, Any] = {}
    for case in manifest["cases"]:
        capture = Capture()
        interpreter = _interpreter(capture)
        if case["kind"] == "first":
            interpreter.interpret("owner", "intake", case["intake"])
            text = case["intake"]["original_request"]
        else:
            base = next(c for c in manifest["cases"] if c["id"] == case["base_case"])
            parsed = parse_interpretation_response(json.dumps(load_case("rough-hunch")["provider"]["model_response"]), base["intake"])
            evidence = list(parsed.field_evidence)
            for question_id, option_id in case["prior_choices"]:
                evidence = apply_choice_answer(evidence, list(parsed.questions), question_id, option_id)[0]  # type: ignore[index]
            question = next(q.text for q in parsed.questions if q.question_id == case["answers_question"])
            interpreter.follow_up("owner", "intake", base["intake"], evidence, question,
                                  ClarificationAnswer(f"answer:{case['answers_question']}", case["reply"]), question_id=case["answers_question"])
            text = case["reply"]
        turn = capture.turn
        assert turn is not None
        out[case["id"]] = {
            "kind": case["kind"], "group": case["group"], "text_sha256": sha256(text.encode()),
            "task_sha256": sha256(turn.user_message.encode()),
            "logical_request_bytes": len(turn.system_prompt.encode()) + len(turn.user_message.encode())}
    return out


def reservations() -> dict[str, Any]:
    """Worst-case reservation per request kind and the batch totals, at the STALE prices above."""
    from decimal import Decimal
    from spend_ledger import TokenPrice

    price = TokenPrice(Decimal(STALE_PRICES_USD_PER_MILLION["prompt"]), Decimal(STALE_PRICES_USD_PER_MILLION["completion"]))
    per = {kind: price.nano_usd(limit + LIMITS["input_token_margin"], LIMITS["max_output_tokens"])
           for kind, limit in LIMITS["max_request_bytes"].items()}
    base = 8 * per["first"] + 3 * per["follow_up"]
    worst = base + LIMITS["retry_slots"] * max(per.values())
    usd = lambda nano: str(Decimal(nano) / Decimal(10) ** 9)  # noqa: E731
    return {"label": "STALE_PRICES_NOT_CURRENT", "per_request_usd": {k: usd(v) for k, v in per.items()},
            "base_batch_11_requests_usd": usd(base), "with_four_retry_slots_usd": usd(worst)}


def compute() -> dict[str, Any]:
    manifest_bytes = (PACKAGE / "CASE_MANIFEST.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    config = HermesInterpreterConfig(**PROPOSED, runtime_label="LIVE", live_release=None).identity()
    return {
        "label": "PROPOSED_NOT_RELEASED",
        "base_commit": BASE_COMMIT,
        "prompt_version": hermes.PROMPT_VERSION,
        "system_prompt_sha256": sha256(hermes.SYSTEM_PROMPT.encode()),
        "system_prompt_chars": len(hermes.SYSTEM_PROMPT),
        "response_shape_sha256": sha256(hermes.RESPONSE_SHAPE.encode()),
        "p02_manifest_sha256": record_contract.manifest_sha256(),
        "hermes_commit": hermes.PINNED_HERMES_COMMIT,
        "hermes_uv_lock_sha256": hermes.PINNED_HERMES_LOCK_SHA256,
        "proposed_limits": LIMITS, "stale_prices_usd_per_million": STALE_PRICES_USD_PER_MILLION, "reservations": reservations(),
        "proposed_config": {**PROPOSED, "attempt_configuration_sha256": sha256(json.dumps(config, sort_keys=True).encode())},
        "support_files_sha256": {name: sha256((HERE / name).read_bytes()) for name in SUPPORT_FILES},
        "case_manifest_sha256": sha256(manifest_bytes),
        "cases": case_identities(manifest),
    }


if __name__ == "__main__":
    print(json.dumps(compute(), indent=1, sort_keys=True))
