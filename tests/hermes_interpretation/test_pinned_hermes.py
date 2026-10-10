"""Actual pinned Hermes (commit 54bc5e5) in a no-egress container against a LOCAL FAKE provider.

What this proves: the adapter, the attempt ledger and the strict parser work end to end around the real Hermes
runtime for the authored cases. What it does not prove: how any real model interprets a request. The fake provider
returns the authored text for each case. No real provider socket, key or account is used.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from docker_turn_runner import DockerHermesTurnRunner
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research.hermes_interpreter import (
    HermesInterpreter, HermesInterpreterConfig, Interpreted, OutputRejected, apply_choice_answer,
)
from edge_os_api.research.interpretation_attempts import AttemptLedger
from edge_os_api.research.interpretation_response import ParsedInterpretation
from edge_os_api.research.fixture_interpreter import FixtureInterpreter
from edge_os_api.research.outcome_router import route

REPO = Path(__file__).resolve().parents[2]
CASES = {p.stem: json.loads(p.read_text()) for p in sorted(
    (REPO / "apps/api/tests/fixtures/hermes_interpretation/cases").glob("*.json"))}
OWNER, INTAKE = "owner-a-7f3c", "intake-5e21"
CONFIG = HermesInterpreterConfig(model="fixture-model/1", route="local-fake-provider", max_output_tokens=4096)
PINNED_COMMIT = "54bc5e509c985f37265c3d416bd2c64b10fc77ba"


def provider_script(case_provider: dict[str, Any]) -> dict[str, Any]:
    if case_provider["kind"] != "content":
        return dict(case_provider)
    text = json.dumps(case_provider["model_response"]) if "model_response" in case_provider else case_provider["model_text"]
    return {"kind": "content", "content": text, "finish_reason": case_provider["finish_reason"],
            "usage": case_provider["usage"]}


class Session:
    """One request's interpreter, ledger and store over a real pinned-Hermes runner."""

    def __init__(self, image: str, run_id: str, evidence_root: Path, name: str, scripts: list[dict[str, Any]],
                 timeout_seconds: int = 90) -> None:
        from test_interpretation_attempts import MemoryAttemptStore
        self.store = MemoryAttemptStore()
        ids, ticks = itertools.count(1), itertools.count(0)
        self.ledger = AttemptLedger(self.store, new_id=lambda: f"attempt-{next(ids)}",
                                    now=lambda: dt.datetime(2026, 10, 9, 12, tzinfo=dt.timezone.utc)
                                    + dt.timedelta(seconds=next(ticks)))
        queue = list(scripts)
        self.runner = DockerHermesTurnRunner(
            image=image, run_id=run_id, evidence_dir=evidence_root / name, script_for=lambda turn: queue.pop(0),
            forbidden=[OWNER, INTAKE], timeout_seconds=timeout_seconds)
        import time
        self.interpreter = HermesInterpreter(CONFIG, self.runner, self.ledger, monotonic=time.monotonic)


def routed(intake: dict[str, Any], parsed: ParsedInterpretation, evidence: list[dict[str, Any]] | None = None):
    revision = "11111111-1111-4111-8111-111111111111"
    items = [{**item, "interpretation_revision": revision} for item in (evidence or parsed.field_evidence)]
    interp = {"intake_record_id": "22222222-2222-4222-8222-222222222222", "interpretation_revision_id": revision,
              "input_class": intake["input_class"], "requested_job": intake["requested_job"], "field_evidence": items,
              "clarification_history": [], "preserved_restrictions": list(intake["restrictions"]),
              "meaning_status": parsed.meaning_status, "syntax_status": "VALID",
              "evidence_readiness": parsed.evidence_readiness}
    record_contract.validate_record("PromptInterpretation", interp)
    return route(intake, interp, FixtureInterpreter(), parsed.missing_capability, "strategy-test")


def adopt_all(parsed: ParsedInterpretation) -> list[dict[str, Any]]:
    applied = apply_choice_answer(list(parsed.field_evidence), list(parsed.questions), "adopt-suggested-settings", "adopt")
    assert applied is not None
    return applied[0]


@pytest.mark.parametrize("name", sorted(CASES))
def test_authored_case_through_actual_hermes(name: str, pinned_hermes_image: str, run_id: str, evidence_root: Path) -> None:
    case = CASES[name]
    expect = case["expect"]
    timeout = 12 if case["provider"]["kind"] == "hang" else 90
    session = Session(pinned_hermes_image, run_id, evidence_root, name, [provider_script(case["provider"])], timeout)

    result = session.interpreter.interpret(OWNER, INTAKE, case["intake"])

    history = session.ledger.history(OWNER, INTAKE)
    assert type(result).__name__ == expect["result"], result
    assert len(history) == expect.get("attempts", 1)
    settlement = history[0].settlement
    assert settlement is not None
    if "status" in expect:
        assert (history[0].status, history[0].completion) == (expect["status"], expect.get("completion", history[0].completion))
    if "reason_code" in expect:
        reason = result.rejection.reason_code if isinstance(result, OutputRejected) else result.reason_code
        assert reason == expect["reason_code"]
    if "usage" in expect:
        assert (settlement.usage.input_tokens, settlement.usage.output_tokens, settlement.usage.total_tokens,
                settlement.usage.source) == (expect["usage"]["input_tokens"], expect["usage"]["output_tokens"],
                                             expect["usage"]["total_tokens"], "PROVIDER_REPORTED")
    if expect.get("usage_known") is False:
        usage = settlement.usage
        assert (usage.input_tokens, usage.output_tokens, usage.total_tokens, usage.source) == (None, None, None, "UNKNOWN")
    assert settlement.latency_ms is not None and settlement.latency_ms > 0
    if isinstance(result, Interpreted):
        assert settlement.runtime_observed["hermes_source_commit"] == PINNED_COMMIT
        assert history[0].start.identity.config["hermes_commit"] == PINNED_COMMIT
        by_name = {i["field_name"]: i for i in result.parsed.field_evidence}
        for key, field_name in (("entry_value", "entry"), ("exit_value", "exit")):
            if key in expect:
                assert by_name[field_name]["value"] == expect[key]
        for key, field_name in (("entry_source_ref", "entry"), ("exit_source_ref", "exit")):
            if key in expect:
                assert by_name[field_name]["source_ref"] == expect[key]
        if "evidence_names" in expect:
            assert sorted(by_name) == sorted(expect["evidence_names"])
        if "missing_capability" in expect:
            assert result.parsed.missing_capability == expect["missing_capability"]
        outcome = routed(case["intake"], result.parsed)
        if "outcome" in expect:
            assert outcome.outcome == expect["outcome"]
        if "outcome_before_adoption" in expect:
            assert outcome.outcome == expect["outcome_before_adoption"]
            assert [f["path"].rsplit("/", 1)[1] for f in outcome.findings] == expect["pending"]
            assert routed(case["intake"], result.parsed, adopt_all(result.parsed)).outcome == expect["outcome_after_adoption"]
        if "missing" in expect:
            assert [n for n, i in by_name.items() if i["state"] == "MISSING"] == expect["missing"]
            assert [q.question_id for q in result.parsed.questions] == expect["question_ids"]
