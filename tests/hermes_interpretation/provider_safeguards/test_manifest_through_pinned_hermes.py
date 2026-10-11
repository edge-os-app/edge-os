"""Every proposed qualification case, run once through ACTUAL pinned Hermes behind the guard with a CONTROLLED answer.

The answers are hand-written faithful readings. They are NOT model output. This shows that the manifest, the real wire
request, the guard, the parser and the meaning checker work together, and it measures the real request sizes that the
proposal's limits rest on. It says nothing about how a real model reads these requests.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from authored_cases import load_case, load_follow_up, provider_script
from edge_os_api.research.hermes_interpreter import Interpreted, apply_choice_answer
from edge_os_api.research.interpretation_response import ClarificationAnswer
from meaning_check import check_meaning
from qualification_identities import LIMITS
from test_pinned_hermes_guard import INTAKE, OWNER, Rig

REPO = Path(__file__).resolve().parents[3]
MANIFEST = json.loads((REPO / "docs/qualification/hermes-provider/CASE_MANIFEST.json").read_text())
CASES = {case["id"]: case for case in MANIFEST["cases"]}
LITERALS = MANIFEST["literals"]
USAGE = {"prompt_tokens": 1500, "completion_tokens": 400, "total_tokens": 1900}


def script_of(response: dict[str, Any], finish: str = "stop") -> dict[str, Any]:
    return {"kind": "content", "content": json.dumps(response), "finish_reason": finish, "usage": USAGE}


def reading(case: str, **changes: Any) -> dict[str, Any]:
    return {**copy.deepcopy(load_case(case)["provider"]["model_response"]), **changes}


def with_quotes(response: dict[str, Any], quotes: dict[str, str]) -> dict[str, Any]:
    out = copy.deepcopy(response)
    for item in out["field_evidence"]:
        if item["field_name"] in quotes:
            item["source_passage"] = quotes[item["field_name"]]
    return out


def delta(*items: dict[str, Any]) -> dict[str, Any]:
    return {"meaning_status": "SUPPORTED", "missing_capability": None, "evidence_readiness": "READY",
            "field_evidence": list(items), "questions": []}


def user_stated(name: str, literal: str, quote: str) -> dict[str, Any]:
    return {"field_name": name, "state": "KNOWN", "origin": "USER_STATED", "source_passage": quote, "value": LITERALS[literal]}


FIRST = {
    "g1-concrete": reading("concrete-thesis"),
    "g1-paraphrase": with_quotes(reading("concrete-thesis"), {
        "entry": "gained more than one percent across the past quarter hour", "exit": "as soon as the last five minutes show a loss"}),
    "g2-hunch": reading("rough-hunch"),
    "g2-conflict": reading("rough-hunch"),
    "g3-no-thesis": reading("bounded-no-thesis"),
    "g3-no-market": reading("bounded-no-thesis"),
    "g4-unsupported": reading("unsupported-extension"),
    "g4-mixed": reading("unsupported-extension", missing_capability="creator_wallet_label_filter"),
}
FOLLOW_UPS = {
    "g5-fill": [delta(user_stated("entry", "gt_return15_1pct", "Enter when the 15-minute price return is above 1%"),
                      user_stated("exit", "lt_return5_zero", "exit when the 5-minute return is below zero"))],
    "g5-overwrite-tempt": [delta(
        {"field_name": "entry", "state": "CONFLICTING", "conflicts": [
            {"value": LITERALS["gt_return15_2pct"], "source_passage": "make the entry more than 2%"}]},
        user_stated("exit", "lt_return5_zero", "Exit when the return is below zero"))],
    "g5-restatement": [delta()],
}
RECEIPTS: list[dict[str, Any]] = []


def settled_text(rig: Rig) -> dict[str, Any]:
    return json.loads(rig.ledger.history(OWNER, INTAKE)[-1].settlement.response_text)  # type: ignore[union-attr]


def record(rig: Rig, case_id: str, turn: int, failures: list[str]) -> None:
    [guard] = [r for r in rig.container_result(turn)["guard"]["evidence"] if r["admitted"]]
    kind = CASES[case_id]["kind"]
    assert guard["request_bytes"] <= LIMITS["max_request_bytes"][kind], "the real request passed the proposed byte limit"
    RECEIPTS.append({"case": case_id, "turn": turn, "wire_request_bytes": guard["request_bytes"],
                     "provider_requests": rig.container_result(turn)["hermes"]["request_count"],
                     "meaning_failures": failures, "label": "CONTROLLED_FAKE_ANSWER_NOT_A_MODEL"})


@pytest.mark.parametrize("case_id", sorted(FIRST))
def test_a_first_case_passes_the_guard_the_parser_and_the_meaning_check(case_id, pinned_hermes_image, run_id, evidence_root) -> None:
    case = CASES[case_id]
    rig = Rig(pinned_hermes_image, run_id, evidence_root, case_id, script_of(FIRST[case_id]))

    result = rig.interpreter.interpret(OWNER, INTAKE, case["intake"])

    assert isinstance(result, Interpreted), result
    failures = check_meaning(settled_text(rig), case["expect"], LITERALS, [case["intake"]["original_request"]])
    record(rig, case_id, 1, failures)
    assert failures == []


@pytest.mark.parametrize("case_id", sorted(FOLLOW_UPS))
def test_a_follow_up_case_passes_the_guard_the_parser_and_the_meaning_check(case_id, pinned_hermes_image, run_id, evidence_root) -> None:
    case = CASES[case_id]
    base = CASES[case["base_case"]]
    rig = Rig(pinned_hermes_image, run_id, evidence_root, case_id, [script_of(FIRST[base["id"]]), *map(script_of, FOLLOW_UPS[case_id])])
    first = rig.interpreter.interpret(OWNER, INTAKE, base["intake"])
    assert isinstance(first, Interpreted), first
    evidence = list(first.parsed.field_evidence)
    for question_id, option_id in case["prior_choices"]:
        applied = apply_choice_answer(evidence, list(first.parsed.questions), question_id, option_id)
        assert applied is not None
        evidence = applied[0]
    question = next(q.text for q in first.parsed.questions if q.question_id == case["answers_question"])

    result = rig.interpreter.follow_up(OWNER, INTAKE, base["intake"], evidence, question,
                                       ClarificationAnswer(f"answer:{case['answers_question']}", case["reply"]))

    if case["application_outcome"] == "Interpreted":
        assert isinstance(result, Interpreted), result
    else:  # the application's own safe outcome for a reply that changes nothing; the answer is still saved and checked
        assert f"OutputRejected:{result.rejection.reason_code}" == case["application_outcome"], result
    failures = check_meaning(settled_text(rig), case["expect"], LITERALS,
                             [base["intake"]["original_request"], case["reply"]])
    record(rig, case_id, 2, failures)
    assert failures == []


def test_zz_the_wire_sizes_are_kept_as_a_receipt(evidence_root) -> None:
    (evidence_root / "manifest-wire-receipts.json").write_text(json.dumps(sorted(RECEIPTS, key=lambda r: r["case"]), indent=1) + "\n")
    assert all(r["provider_requests"] == 1 for r in RECEIPTS)
