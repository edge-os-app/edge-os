"""Model-adapter boundary and the deterministic FIXTURE interpreter.

`FixtureInterpreter` makes no model call. It answers only the scripted requests below and reports itself as a
fixture in every response. A real adapter (P04/P05) will implement the same `Interpreter` protocol.
Unscripted text is a system outcome (`interpreter_no_scripted_response`), never an `UNSUPPORTED` verdict on the idea.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import p02

FIXTURE_ID = "p03-fixture-interpreter/1"
ADOPT_QUESTION_ID = "adopt-suggested-settings"
MARKET = p02.FIXTURE_STRATEGY["market"]
DECLARED_MARKET = {"network": MARKET["network"], "base_asset": MARKET["research_binding"]["base_asset"],
                   "quote_asset": MARKET["research_binding"]["quote_asset"]}
MARKET_LABEL = "Synthetic fixture market (not a real pool)"


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    value: Any


@dataclass(frozen=True)
class ChoiceQuestion:
    field_name: str
    question_id: str
    text: str
    options: tuple[Option, ...]


def _gt_return(buckets: int, threshold: str) -> dict[str, Any]:
    return {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": buckets},
                                 {"op": "constant", "value": threshold, "unit": "DIMENSIONLESS"}]}


ENTRY_QUESTION = ChoiceQuestion(
    "entry", "choose-entry", "What should count as a rise for the entry rule?",
    (Option("g3-1pct", "Price up more than 1% over the last 15 minutes", _gt_return(3, "0.01")),
     Option("g3-2pct", "Price up more than 2% over the last 15 minutes", _gt_return(3, "0.02")),
     Option("g6-3pct", "Price up more than 3% over the last 30 minutes", _gt_return(6, "0.03"))))
MARKET_QUESTION = ChoiceQuestion(
    "market", "choose-market", "Which market should this investigation use?",
    (Option("fixture-market", MARKET_LABEL, DECLARED_MARKET),))

# field -> (origin, plain-words label, question about adopting the proposal, summary)
PROPOSALS: dict[str, tuple[str, str, str, str]] = {
    "market": ("AGENT_PROPOSED", "Market", "Adopt the suggested market: the synthetic fixture pool quoted per base asset?",
               MARKET_LABEL),
    "decision_interval_seconds": ("APPLICATION_CONFIGURED", "Decision interval",
                                  "Adopt the suggested decision interval seconds: 300, one five-minute bucket?",
                                  "Decide once per five-minute bucket"),
    "data_inputs": ("APPLICATION_CONFIGURED", "Data inputs", "Adopt the suggested data inputs: price only?",
                    "Price only"),
    "exit": ("AGENT_PROPOSED", "Exit rule",
             "Adopt the suggested exit rule: exit when the one-bucket price return falls below zero?",
             "Exit when the last five-minute price return is below zero"),
    "invalidation": ("AGENT_PROPOSED", "Invalidation", "Adopt the suggested invalidation: no separate invalidation rule?",
                     "No separate invalidation rule"),
    "sizing": ("AGENT_PROPOSED", "Sizing", "Adopt the suggested sizing: a fixed 100 quote units per entry?",
               "Fixed 100 quote units per entry"),
    "additions": ("AGENT_PROPOSED", "Additions", "Adopt the suggested additions setting: no additions?", "No additions"),
    "partial_exits": ("AGENT_PROPOSED", "Partial exits", "Adopt the suggested partial exits setting: no partial exits?",
                      "No partial exits"),
    "cost_assumptions": ("AGENT_PROPOSED", "Cost assumptions",
                         "Adopt the suggested cost assumptions: 0.3% fee and 0.5% slippage?",
                         "0.3% fee and 0.5% slippage (synthetic assumption)"),
    "risk_limits": ("AGENT_PROPOSED", "Risk limits",
                    "Adopt the suggested risk limits: one open position and at most 100 quote units?",
                    "One open position, at most 100 quote units"),
    "action_scope": ("AGENT_PROPOSED", "Action scope",
                     "Adopt the suggested action scope: spot buy and sell all attributable inventory?",
                     "Spot buy and sell all attributable inventory (grants no permission)"),
}
EXIT_RULE = {"op": "lt", "args": [{"op": "price_return", "lookback_buckets": 1},
                                  {"op": "constant", "value": "0", "unit": "DIMENSIONLESS"}]}
THESIS_ENTRY = _gt_return(3, "0.01")
VOLUME_ENTRY = {"op": "gt", "args": [
    {"op": "relative_volume", "lookback_buckets": 2},
    {"op": "constant", "value": "2", "unit": "DIMENSIONLESS"},
]}
PRICE_ABOVE_20 = {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "20", "unit": "PRICE"}]}
PRICE_ABOVE_30 = {"op": "gt", "args": [{"op": "price"}, {"op": "constant", "value": "30", "unit": "PRICE"}]}
GROUPED_ENTRY = {"op": "and", "args": [{"op": "or", "args": [VOLUME_ENTRY, PRICE_ABOVE_20]}, PRICE_ABOVE_30]}
GROUPED_RIGHT_ENTRY = {"op": "or", "args": [VOLUME_ENTRY, {"op": "and", "args": [PRICE_ABOVE_20, PRICE_ABOVE_30]}]}
TINY_NEGATIVE_RETURN_ENTRY = {"op": "gt", "args": [
    {"op": "price_return", "lookback_buckets": 1},
    {"op": "constant", "value": "-0." + ("0" * 399) + "1", "unit": "DIMENSIONLESS"},
]}
TINY_POSITIVE_RETURN_ENTRY = {"op": "gt", "args": [
    {"op": "price_return", "lookback_buckets": 1},
    {"op": "constant", "value": "0." + ("0" * 399) + "1", "unit": "DIMENSIONLESS"},
]}
UNSUPPORTED_ENTRY = {"op": "gt", "args": [
    {"op": "rsi", "lookback_buckets": 14},
    {"op": "constant", "value": "70", "unit": "DIMENSIONLESS"},
]}


def proposal_values() -> dict[str, Any]:
    fixture = p02.FIXTURE_STRATEGY
    values = {name: copy.deepcopy(fixture[name]) for name in
              ("market", "decision_interval_seconds", "sizing", "additions", "partial_exits", "cost_assumptions",
               "risk_limits", "action_scope")}
    values["data_inputs"] = ["price"]
    values["exit"] = copy.deepcopy(EXIT_RULE)
    values["invalidation"] = {"state": "NOT_REQUESTED", "source_ref": "fixture:no-invalidation"}
    return values


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    text: str
    input_class: str
    requested_job: str
    restrictions: tuple[str, ...] = ()
    declared_market: dict[str, str] | None = None
    meaning_status: str = "SUPPORTED"
    evidence_readiness: str = "READY"
    missing_capability: str | None = None
    stated: dict[str, Any] = field(default_factory=dict)
    choices: tuple[ChoiceQuestion, ...] = ()
    proposes_defaults: bool = True
    show_example: bool = True


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("hunch", "Rough hunch", "Recent rises seem to keep running. Is that worth testing?",
             "LOOSE_INTUITION", "CREATE_STRATEGY", ("no leverage", "one open position maximum"),
             choices=(ENTRY_QUESTION,)),
    Scenario("thesis", "Specific thesis",
             "Buy when the 15-minute price return is above 1%, and exit when the 5-minute return turns negative. "
             "Spot only.", "CONCRETE_THESIS", "CREATE_STRATEGY", ("no leverage", "one open position maximum"),
             stated={"entry": THESIS_ENTRY, "exit": EXIT_RULE}),
    Scenario("volume-rule", "Quote volume rule",
             "Enter when current quote volume is above twice its prior 10-minute mean; exit when the 5-minute "
             "price return is below zero.", "CONCRETE_THESIS", "CREATE_STRATEGY", ("no leverage",),
             stated={"entry": VOLUME_ENTRY, "exit": EXIT_RULE, "data_inputs": ["price", "quote_volume"]}),
    Scenario("grouped-rule", "Nested Boolean rule",
             "Enter when (current quote volume is above twice its prior 10-minute mean or price is above 20) and "
             "price is above 30. Exit when the 5-minute price return is below zero.",
             "CONCRETE_THESIS", "CREATE_STRATEGY", ("no leverage",),
             stated={"entry": GROUPED_ENTRY, "exit": EXIT_RULE, "data_inputs": ["price", "quote_volume"]},
             show_example=False),
    Scenario("grouped-rule-right", "Nested Boolean rule with right group",
             "Enter when current quote volume is above twice its prior 10-minute mean or (price is above 20 and "
             "price is above 30). Exit when the 5-minute price return is below zero.",
             "CONCRETE_THESIS", "CREATE_STRATEGY", ("no leverage",),
             stated={"entry": GROUPED_RIGHT_ENTRY, "exit": EXIT_RULE, "data_inputs": ["price", "quote_volume"]},
             show_example=False),
    Scenario("tiny-threshold", "Exact tiny return threshold",
             "Enter when the 5-minute price return is above " + TINY_NEGATIVE_RETURN_ENTRY["args"][1]["value"] +
             ". Exit when the 5-minute price return is below zero.",
             "CONCRETE_THESIS", "CREATE_STRATEGY", ("no leverage",),
             stated={"entry": TINY_NEGATIVE_RETURN_ENTRY, "exit": EXIT_RULE}, show_example=False),
    Scenario("tiny-threshold-positive", "Exact tiny positive return threshold",
             "Enter when the 5-minute price return is above " + TINY_POSITIVE_RETURN_ENTRY["args"][1]["value"] +
             ". Exit when the 5-minute price return is below zero.",
             "CONCRETE_THESIS", "CREATE_STRATEGY", ("no leverage",),
             stated={"entry": TINY_POSITIVE_RETURN_ENTRY, "exit": EXIT_RULE}, show_example=False),
    Scenario("unsupported-indicator", "Unsupported indicator",
             "Enter when the 14-period RSI is above 70; exit when the 5-minute price return is below zero.",
             "CONCRETE_THESIS", "CREATE_STRATEGY", ("no leverage",),
             stated={"entry": UNSUPPORTED_ENTRY, "exit": EXIT_RULE}),
    Scenario("no-thesis", "No thesis, bounded question",
             "I have no view. Look at this market over the last two days and tell me whether anything is worth testing.",
             "BOUNDED_NO_THESIS", "INVESTIGATE_EFFECT", (), declared_market=DECLARED_MARKET,
             evidence_readiness="UNRESOLVED", proposes_defaults=False),
    Scenario("launch-age", "Unsupported meaning",
             "Tokens launched in the last 24 hours seem to keep running after a rise. Is that worth testing?",
             "LOOSE_INTUITION", "CREATE_STRATEGY", ("no leverage",), meaning_status="UNSUPPORTED",
             missing_capability="token_launch_age_filter", proposes_defaults=False),
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def find_scenario(intake: dict[str, Any]) -> Scenario | None:
    wanted = (normalize(intake["original_request"]), intake["requested_job"], intake["input_class"])
    for scenario in SCENARIOS:
        if (normalize(scenario.text), scenario.requested_job, scenario.input_class) == wanted:
            return scenario
    return None


def _item(name: str, state: str, origin: str, source_ref: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"field_name": name, "state": state, "origin": origin, "source_ref": source_ref,
            "interpretation_revision": "", "evidence_status": status, **extra}


def _missing(name: str) -> dict[str, Any]:
    return _item(name, "MISSING", "USER_STATED", "intake:original_request", "UNKNOWN")


class Interpreter(Protocol):
    id: str
    kind: str

    def interpret(self, intake: dict[str, Any]) -> dict[str, Any] | None: ...
    def apply_answer(self, intake: dict[str, Any], evidence: list[dict[str, Any]], question_id: str,
                     choice_id: str) -> tuple[list[dict[str, Any]], str, str] | None: ...


class FixtureInterpreter:
    id = FIXTURE_ID
    kind = "FIXTURE"

    def label(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id,
                "notice": "Scripted fixture responses. No model was called and no research ran."}

    def interpret(self, intake: dict[str, Any]) -> dict[str, Any] | None:
        scenario = find_scenario(intake)
        if scenario is None:
            return None
        evidence: list[dict[str, Any]] = []
        job = intake["requested_job"]
        evidence.append(_item("restrictions", "KNOWN", "USER_STATED", "intake:restrictions", "VERIFIED_FACT",
                              value=list(intake["restrictions"])))
        declared = intake.get("declared_market")
        if job == "CREATE_STRATEGY":
            values = proposal_values()
            for name in p02.CREATE_STRATEGY_FIELDS:
                if name == "restrictions":
                    continue
                if name in scenario.stated:
                    evidence.append(_item(name, "KNOWN", "USER_STATED", "intake:original_request", "HYPOTHESIS",
                                          value=copy.deepcopy(scenario.stated[name])))
                elif any(c.field_name == name for c in scenario.choices):
                    evidence.append(_missing(name))
                elif scenario.proposes_defaults:
                    origin = PROPOSALS[name][0]
                    evidence.append(_item(name, "KNOWN", origin, f"fixture:{name}-proposal", "HYPOTHESIS",
                                          value=values[name], adoption="PENDING"))
        else:
            if declared is not None:
                evidence.append(_item("market", "KNOWN", "USER_STATED", "intake:declared_market", "HYPOTHESIS",
                                      value=copy.deepcopy(declared)))
            else:
                evidence.append(_missing("market"))
        return {"scenario": scenario, "meaning_status": scenario.meaning_status, "syntax_status": "VALID",
                "evidence_readiness": scenario.evidence_readiness, "field_evidence": evidence,
                "missing_capability": scenario.missing_capability}

    def question_for(self, intake: dict[str, Any]) -> list[ChoiceQuestion]:
        scenario = find_scenario(intake)
        if scenario is None:
            return []
        choices = list(scenario.choices)
        if intake["requested_job"] != "CREATE_STRATEGY" and intake.get("declared_market") is None:
            choices.append(MARKET_QUESTION)
        return choices

    def apply_answer(self, intake: dict[str, Any], evidence: list[dict[str, Any]], question_id: str,
                     choice_id: str) -> tuple[list[dict[str, Any]], str, str] | None:
        """Return (new evidence, question text, answer reference) or None when the answer is not offered."""
        updated = copy.deepcopy(evidence)
        by_name = {item["field_name"]: item for item in updated}
        if question_id == ADOPT_QUESTION_ID:
            pending = [name for name, item in by_name.items()
                       if item.get("adoption") == "PENDING" and item["state"] == "KNOWN"]
            if choice_id != "adopt" or not pending:
                return None
            for name in pending:
                by_name[name]["adoption"] = "ADOPTED"
            text = "Adopt the suggested settings: " + ", ".join(name.replace("_", " ") for name in sorted(pending)) + "?"
            return updated, text, f"choice:{question_id}:{choice_id}"
        for question in self.question_for(intake):
            if question.question_id != question_id:
                continue
            target = by_name.get(question.field_name)
            option = next((o for o in question.options if o.id == choice_id), None)
            if target is None or target["state"] != "MISSING" or option is None:
                return None
            answer_ref = f"choice:{question_id}:{choice_id}"
            replacement = _item(question.field_name, "KNOWN", "USER_CONFIRMED", answer_ref, "HYPOTHESIS",
                                value=copy.deepcopy(option.value))
            updated[updated.index(target)] = replacement
            return updated, question.text, answer_ref
        return None


def field_label(name: str) -> str:
    return name.replace("_", " ")


def clarification_text(intake: dict[str, Any], interpreter: FixtureInterpreter, item: dict[str, Any] | None,
                       name: str) -> str:
    """Question that names the field and ends with `?` (P02 NEEDS_CLARIFICATION finding rule)."""
    if item is not None and item["state"] == "MISSING":
        for question in interpreter.question_for(intake):
            if question.field_name == name:
                return question.text
    if item is not None and item.get("adoption") == "PENDING" and name in PROPOSALS:
        return PROPOSALS[name][2]
    return f"What should the {field_label(name)} be?"


def open_questions(intake: dict[str, Any], interpreter: FixtureInterpreter, evidence: list[dict[str, Any]],
                   targets: list[str]) -> list[dict[str, Any]]:
    """UI view of the questions the outcome asks. One entry per choice, one bundled adoption review."""
    by_name = {item["field_name"]: item for item in evidence}
    questions: list[dict[str, Any]] = []
    for choice in interpreter.question_for(intake):
        item = by_name.get(choice.field_name)
        if choice.field_name in targets and item is not None and item["state"] == "MISSING":
            questions.append({"question_id": choice.question_id, "kind": "CHOICE", "field_name": choice.field_name,
                              "text": choice.text,
                              "options": [{"id": o.id, "label": o.label} for o in choice.options]})
    items = []
    for name in targets:
        item = by_name.get(name)
        if item is not None and item.get("adoption") == "PENDING" and name in PROPOSALS:
            origin, label, question, summary = PROPOSALS[name]
            items.append({"field_name": name, "label": label, "summary": summary, "origin": origin,
                          "question": question})
    if items:
        questions.append({"question_id": ADOPT_QUESTION_ID, "kind": "ADOPT",
                          "text": "Review the suggested settings. Adopt them to continue.", "items": items,
                          "options": [{"id": "adopt", "label": "Adopt these settings"}]})
    return questions


def samples() -> list[dict[str, Any]]:
    return [{"scenario_id": s.id, "label": s.label, "text": s.text, "input_class": s.input_class,
             "requested_job": s.requested_job, "restrictions": list(s.restrictions),
             "declared_market": copy.deepcopy(s.declared_market)} for s in SCENARIOS if s.show_example]
