"""Strict whole-response parser for generated interpretations.

A generated response is accepted whole or rejected whole. The parser never selects a fragment, repairs text or
fills a missing value. Meaning that the user did not state stays a proposal that needs adoption.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from edge_os_api.records import contract_adapter as record_contract

__all__ = ["ADOPT_QUESTION_ID", "ClarificationAnswer", "OfferedOption", "OfferedQuestion", "ParsedInterpretation", "Rejection",
           "parse_follow_up_response", "parse_interpretation_response"]

REQUEST_SOURCE = "intake:original_request"
RESTRICTIONS_SOURCE = "intake:restrictions"
AGENT_PROPOSAL_SOURCE = "agent:proposal"
TOP_LEVEL_FIELDS = ("meaning_status", "missing_capability", "evidence_readiness", "field_evidence", "questions")
ITEM_FIELDS = frozenset({"field_name", "state", "origin", "source_passage", "value", "adoption", "conflicts"})
QUESTION_FIELDS = frozenset({"question_id", "field_name", "text", "options"})
OPTION_FIELDS = frozenset({"id", "label", "value"})
CONFLICT_FIELDS = frozenset({"value", "source_passage"})
ADOPT_QUESTION_ID = "adopt-suggested-settings"
RESERVED_QUESTION_IDS = frozenset({ADOPT_QUESTION_ID})
DECLARED_MARKET_SOURCE = "intake:declared_market"
SYNTHETIC_MARKET_SOURCE = "application:synthetic-fixture-market"
INTERVAL_SOURCE = "application:five-minute-buckets"
APPLICATION_OWNED_FIELDS = frozenset({"restrictions", "market", "decision_interval_seconds"})
CAPABILITY_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
MEANING_STATUSES = ("SUPPORTED", "UNSUPPORTED")
EVIDENCE_READINESS = ("READY", "UNRESOLVED")


@dataclass(frozen=True)
class Rejection:
    """The whole generated response is unusable. This is a malformed-output outcome, not a verdict on the idea."""

    reason_code: str
    path: str
    detail: str


@dataclass(frozen=True)
class ClarificationAnswer:
    """The user's free-text reply. `answer_ref` is the application's stable name for it, used in source references."""

    answer_ref: str
    text: str


@dataclass(frozen=True)
class OfferedOption:
    id: str
    label: str
    value: Any


@dataclass(frozen=True)
class OfferedQuestion:
    question_id: str
    field_name: str
    text: str
    options: tuple[OfferedOption, ...]


@dataclass(frozen=True)
class ParsedInterpretation:
    meaning_status: str
    missing_capability: str | None
    evidence_readiness: str
    field_evidence: tuple[dict[str, Any], ...]
    questions: tuple[OfferedQuestion, ...]
    response_sha256: str


AMOUNT_KEYS = frozenset({"amount", "fee_rate", "slippage_rate", "max_quote_notional"})
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
                "forty": 40, "fifty": 50, "sixty": 60, "hundred": 100, "twice": 2, "double": 2, "triple": 3}
NUMBER_PATTERN = re.compile(
    r"(?P<neg>(?<![\w.])[-\u2212]|\b(?:minus|negative)\s+)?"
    r"(?:(?P<digits>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)|\b(?P<word>" + "|".join(NUMBER_WORDS) + r")\b)",
    re.IGNORECASE)
SCALE_PATTERN = re.compile(r"\s*(?P<scale>%|percent\b|per cent\b|bps\b|basis points?\b)", re.IGNORECASE)


def _numbers_in(text: str) -> set[Decimal]:
    """Every number that these words state. A number followed by %, percent or bps states only its scaled form."""
    found = {Decimal(0)}
    for match in NUMBER_PATTERN.finditer(text):
        raw = match.group("digits")
        number = Decimal(raw.replace(",", "")) if raw is not None else Decimal(NUMBER_WORDS[match.group("word").lower()])
        scale = SCALE_PATTERN.match(text, match.end())
        if scale is not None:
            number = number.scaleb(-4 if scale.group("scale").lower().startswith(("bps", "basis")) else -2)
        # A sign counts only when the words show it ("-2%", "minus 2%"). Without it a negative value stays ungrounded.
        found.add(-number if match.group("neg") else number)
    return found


def _decimals_in(value: Any) -> list[Decimal]:
    """Decimal quantities that a value states: constants, sizing amounts, cost rates and notional limits."""
    quantities: list[Decimal] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if (key in AMOUNT_KEYS or (key == "value" and value.get("op") == "constant")) and isinstance(child, str):
                try:
                    quantity = Decimal(child)
                except InvalidOperation:
                    continue  # not a decimal; the compile checks reject it when the field is complete
                # NaN and infinity are never a stated number, and hashing a signaling NaN raises.
                quantities.append(quantity if quantity.is_finite() else Decimal("Infinity"))
            else:
                quantities.extend(_decimals_in(child))
    elif isinstance(value, list):
        for child in value:
            quantities.extend(_decimals_in(child))
    return quantities


def _ungrounded(value: Any, words: str) -> bool:
    stated = _numbers_in(words)
    return any(not quantity.is_finite() or quantity not in stated for quantity in _decimals_in(value))



def _decode_single_object(text: str) -> dict[str, Any] | Rejection:
    """Decode exactly one JSON object with the P02 strict rules (no duplicate keys, no floats, no NaN)."""
    try:
        value = record_contract.strict_loads(text)
    except json.JSONDecodeError as error:
        if error.msg == "Extra data":
            if text[error.pos:].lstrip().startswith("{"):
                return Rejection("multiple_objects", "", "The response holds more than one JSON object.")
            return Rejection("trailing_content", "", "The response has text after the JSON object.")
        return Rejection("invalid_json", "", "The response is not valid JSON. It may be cut off.")
    except record_contract.Invalid as error:
        if "duplicate object key" in str(error):
            return Rejection("duplicate_key", "", "A JSON object repeats a key.")
        return Rejection("invalid_number", "", "The response uses a JSON number form that the contract forbids.")
    if not isinstance(value, dict):
        return Rejection("not_an_object", "", "The response is not one JSON object.")
    return value


def _check_top_level(response: Mapping[str, Any]) -> Rejection | None:
    for key in response:
        if key not in TOP_LEVEL_FIELDS:
            return Rejection("unaccepted_field", f"/{key}", "The response has a field that is not accepted.")
    for key in TOP_LEVEL_FIELDS:
        if key not in response:
            return Rejection("missing_field", f"/{key}", "The response lacks a required field.")
    if response["meaning_status"] not in MEANING_STATUSES:
        return Rejection("invalid_value", "/meaning_status", "The meaning status is not one the contract defines.")
    if response["evidence_readiness"] not in EVIDENCE_READINESS:
        return Rejection("invalid_value", "/evidence_readiness", "The readiness is not one the contract defines.")
    for key in ("field_evidence", "questions"):
        if not isinstance(response[key], list):
            return Rejection("invalid_value", f"/{key}", "This field must be a list.")
    capability = response["missing_capability"]
    if response["meaning_status"] == "UNSUPPORTED":
        if not isinstance(capability, str) or not capability:
            return Rejection("missing_capability_required", "/missing_capability",
                             "Unsupported meaning must name the missing capability.")
        if not CAPABILITY_NAME.fullmatch(capability):
            return Rejection("invalid_value", "/missing_capability", "The capability must be a short snake_case name.")
    elif capability is not None:
        return Rejection("missing_capability_not_allowed", "/missing_capability",
                         "Supported meaning names no missing capability.")
    return None


Source = tuple[str, str]  # (reference prefix, exact text) that a quoted passage may come from


def _locate(passage: Any, sources: Sequence[Source]) -> str | None:
    """Source reference of the first text that holds this exact passage. An empty passage is never grounding."""
    if not isinstance(passage, str) or not passage:
        return None
    for prefix, text in sources:
        start = text.find(passage)
        if start >= 0:
            return f"{prefix}#c{start}-{start + len(passage)}"
    return None


def _reject(code: str, path: str, detail: str) -> Rejection:
    return Rejection(code, path, detail)


def _model_owned_fields(job: str) -> frozenset[str]:
    """Fields the model may report. The application owns the restrictions, the market and the decision interval."""
    if job == "CREATE_STRATEGY":
        return frozenset(name for name in record_contract.CREATE_STRATEGY_FIELDS if name not in APPLICATION_OWNED_FIELDS)
    return frozenset()


def _missing_item(item: Mapping[str, Any], at: str) -> dict[str, Any] | Rejection:
    for key in ("value", "origin", "source_passage", "adoption", "conflicts"):
        if key in item:
            return _reject("not_allowed_for_state", f"{at}/{key}", "A missing field carries no content.")
    return {"field_name": item["field_name"], "state": "MISSING", "origin": "USER_STATED",
            "source_ref": REQUEST_SOURCE, "interpretation_revision": "", "evidence_status": "UNKNOWN"}


def _conflicting_item(item: Mapping[str, Any], at: str, sources: Sequence[Source],
                      minimum: int = 2) -> dict[str, Any] | Rejection:
    for key in ("value", "origin", "source_passage", "adoption"):
        if key in item:
            return _reject("not_allowed_for_state", f"{at}/{key}", "A conflicting field has no single value.")
    if "conflicts" not in item:
        return _reject("missing_field", f"{at}/conflicts", "A conflicting field needs its alternatives.")
    alternatives = item["conflicts"]
    if not isinstance(alternatives, list) or len(alternatives) < minimum:
        return _reject("conflict_needs_two_alternatives", f"{at}/conflicts", "A conflict needs two alternatives.")
    conflicts: list[dict[str, Any]] = []
    for index, alternative in enumerate(alternatives):
        where = f"{at}/conflicts/{index}"
        if not isinstance(alternative, dict):
            return _reject("invalid_value", where, "An alternative must be an object.")
        for key in alternative:
            if key not in CONFLICT_FIELDS:
                return _reject("unaccepted_field", f"{where}/{key}", "An alternative has a field that is not accepted.")
        if alternative.get("value") is None:
            return _reject("missing_field", f"{where}/value", "An alternative needs a value.")
        passage = alternative.get("source_passage")
        source_ref = _locate(passage, sources)
        if source_ref is None:
            return _reject("source_passage_not_in_request", f"{where}/source_passage",
                           "The quoted words are not an exact part of the original request.")
        if _ungrounded(alternative["value"], passage):
            return _reject("ungrounded_number", f"{where}/value", "A number in the value is not stated in the quoted words.")
        if any(known["source_ref"] == source_ref for known in conflicts):
            return _reject("conflict_alternatives_not_distinct", f"{where}/source_passage",
                           "Each alternative must come from different words.")
        conflicts.append({"value": copy.deepcopy(alternative["value"]), "source_ref": source_ref})
    return {"field_name": item["field_name"], "state": "CONFLICTING", "origin": "USER_STATED",
            "source_ref": REQUEST_SOURCE, "interpretation_revision": "", "evidence_status": "UNKNOWN",
            "conflicts": conflicts}


def _application_market_item(intake: Mapping[str, Any]) -> dict[str, Any]:
    declared = intake.get("declared_market")
    if declared is None:
        # The user declared no market. The application proposes the labelled synthetic fixture market, which waits for
        # adoption (D1). It is never a question the user must answer in words, because the model cannot set this field.
        binding = record_contract.FIXTURE_STRATEGY["market"]
        return {"field_name": "market", "state": "KNOWN", "origin": "APPLICATION_CONFIGURED",
                "source_ref": SYNTHETIC_MARKET_SOURCE, "interpretation_revision": "", "evidence_status": "HYPOTHESIS",
                "adoption": "PENDING", "value": {"network": binding["network"],
                                                 "base_asset": binding["research_binding"]["base_asset"],
                                                 "quote_asset": binding["research_binding"]["quote_asset"]}}
    return {"field_name": "market", "state": "KNOWN", "origin": "USER_STATED", "source_ref": DECLARED_MARKET_SOURCE,
            "interpretation_revision": "", "evidence_status": "HYPOTHESIS", "value": copy.deepcopy(declared)}


def _parse_questions(raw: list[Any], evidence: list[dict[str, Any]],
                     reported: frozenset[str]) -> tuple[OfferedQuestion, ...] | Rejection:
    state_of = {item["field_name"]: item["state"] for item in evidence}
    seen_ids: set[str] = set()
    questions: list[OfferedQuestion] = []
    for index, question in enumerate(raw):
        at = f"/questions/{index}"
        if not isinstance(question, dict):
            return _reject("invalid_value", at, "A question must be an object.")
        for key in question:
            if key not in QUESTION_FIELDS:
                return _reject("unaccepted_field", f"{at}/{key}", "A question has a field that is not accepted.")
        for key in QUESTION_FIELDS:
            if key not in question:
                return _reject("missing_field", f"{at}/{key}", "A question lacks a required field.")
        question_id, name, text = question["question_id"], question["field_name"], question["text"]
        if not isinstance(question_id, str) or not question_id:
            return _reject("invalid_value", f"{at}/question_id", "A question needs an identifier.")
        if not isinstance(name, str):
            return _reject("invalid_value", f"{at}/field_name", "The field name must be text.")
        if question_id in RESERVED_QUESTION_IDS:
            return _reject("reserved_question_id", f"{at}/question_id", "This identifier belongs to the application.")
        if question_id in seen_ids:
            return _reject("duplicate_question", f"{at}/question_id", "The response repeats a question identifier.")
        seen_ids.add(question_id)
        if name not in reported:
            return _reject("question_for_unreported_field", f"{at}/field_name",
                           "A question must ask about a field that the response reports.")
        if state_of[name] == "KNOWN":
            return _reject("question_for_settled_field", f"{at}/field_name",
                           "A question cannot ask about a field that is already known.")
        if not isinstance(text, str) or not text.strip().endswith("?"):
            return _reject("question_text_invalid", f"{at}/text", "A question must be text that ends with a question mark.")
        options = _parse_options(question["options"], at)
        if isinstance(options, Rejection):
            return options
        questions.append(OfferedQuestion(question_id, name, text, options))
    return tuple(questions)


def _parse_options(raw: Any, at: str) -> tuple[OfferedOption, ...] | Rejection:
    if not isinstance(raw, list) or not raw:
        return _reject("question_needs_options", f"{at}/options", "A question needs at least one option.")
    seen: set[str] = set()
    options: list[OfferedOption] = []
    for index, option in enumerate(raw):
        where = f"{at}/options/{index}"
        if not isinstance(option, dict):
            return _reject("invalid_value", where, "An option must be an object.")
        for key in option:
            if key not in OPTION_FIELDS:
                return _reject("unaccepted_field", f"{where}/{key}", "An option has a field that is not accepted.")
        if option.get("value") is None:
            return _reject("missing_field", f"{where}/value", "An option needs a value.")
        option_id, label = option.get("id"), option.get("label")
        if not isinstance(option_id, str) or not option_id:
            return _reject("invalid_value", f"{where}/id", "An option needs an identifier.")
        if not isinstance(label, str) or not label:
            return _reject("invalid_value", f"{where}/label", "An option needs a label.")
        if _ungrounded(option["value"], label):
            return _reject("option_label_omits_value", f"{where}/label",
                           "The label must state every number that the option value carries.")
        if option_id in seen:
            return _reject("duplicate_option", f"{where}/id", "The question repeats an option identifier.")
        seen.add(option_id)
        options.append(OfferedOption(option_id, label, copy.deepcopy(option["value"])))
    return tuple(options)


def _grounded_item(item: Mapping[str, Any], at: str, sources: Sequence[Source]) -> dict[str, Any] | Rejection:
    """Build the P02 evidence item for one KNOWN field, or reject the whole response."""
    origin = item.get("origin")
    if origin is None:
        return _reject("missing_field", f"{at}/origin", "A known field needs an origin.")
    if origin in ("USER_CONFIRMED", "APPLICATION_CONFIGURED"):
        return _reject("origin_not_allowed", f"{at}/origin", "Only the application can record this origin.")
    if origin not in ("USER_STATED", "AGENT_PROPOSED"):
        return _reject("invalid_value", f"{at}/origin", "The origin is not one the contract defines.")
    if item.get("value") is None:
        return _reject("missing_field", f"{at}/value", "A known field needs a value.")
    built: dict[str, Any] = {"field_name": item["field_name"], "state": "KNOWN", "origin": origin,
                             "interpretation_revision": "", "evidence_status": "HYPOTHESIS",
                             "value": copy.deepcopy(item["value"])}
    if origin == "USER_STATED":
        if "adoption" in item:
            return _reject("adoption_not_allowed", f"{at}/adoption", "Words the user stated need no adoption.")
        if "source_passage" not in item:
            return _reject("missing_field", f"{at}/source_passage", "A user-stated field needs the user's words.")
        passage = item["source_passage"]
        source_ref = _locate(passage, sources)
        if source_ref is None:
            return _reject("source_passage_not_in_request", f"{at}/source_passage",
                           "The quoted words are not an exact part of the original request.")
        if _ungrounded(item["value"], passage):
            return _reject("ungrounded_number", f"{at}/value", "A number in the value is not stated in the quoted words.")
        built["source_ref"] = source_ref
        return built
    if "source_passage" in item:
        return _reject("source_passage_not_allowed", f"{at}/source_passage", "A proposal has no user words to quote.")
    if item.get("adoption") != "PENDING":
        return _reject("proposal_must_stay_pending", f"{at}/adoption", "Only the user can adopt a proposal.")
    built.update(source_ref=AGENT_PROPOSAL_SOURCE, adoption="PENDING")
    return built


def _model_items(items: list[Any], intake: Mapping[str, Any], sources: Sequence[Source],
                 single_alternative_ok: frozenset[str] = frozenset()) -> list[dict[str, Any]] | Rejection:
    """Validate and build the evidence items that the model reported. The application adds its own items later."""
    allowed = _model_owned_fields(intake["requested_job"])
    seen: set[str] = set()
    built_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        at = f"/field_evidence/{index}"
        if not isinstance(item, dict):
            return _reject("invalid_value", at, "An evidence item must be an object.")
        for key in item:
            if key not in ITEM_FIELDS:
                return _reject("unaccepted_field", f"{at}/{key}", "An evidence item has a field that is not accepted.")
        name = item.get("field_name")
        if not isinstance(name, str):
            return _reject("invalid_value", f"{at}/field_name", "The field name must be text.")
        if name in APPLICATION_OWNED_FIELDS:
            return _reject("reserved_field", f"{at}/field_name", "The application records this field.")
        if name not in allowed:
            return _reject("unknown_field_name", f"{at}/field_name", "This field is not part of the requested job.")
        if name in seen:
            return _reject("duplicate_field", f"{at}/field_name", "The response reports this field twice.")
        seen.add(name)
        state = item.get("state")
        if state not in record_contract.CONTRACT["field_states"]:
            return _reject("invalid_value", f"{at}/state", "The state is not one the contract defines.")
        if state == "MISSING":
            built = _missing_item(item, at)
        elif state == "CONFLICTING":
            built = _conflicting_item(item, at, sources, 1 if name in single_alternative_ok else 2)
        else:
            built = _grounded_item(item, at, sources)
        if isinstance(built, Rejection):
            return built
        built_items.append(built)
    return built_items


def _application_items(intake: Mapping[str, Any], meaning_status: str) -> list[dict[str, Any]]:
    """Evidence the application owns. Its proposals wait for adoption and are made only for supported meaning."""
    items: list[dict[str, Any]] = []
    if intake["requested_job"] != "CREATE_STRATEGY":
        items.append(_application_market_item(intake))
    elif meaning_status == "SUPPORTED":
        # The market binding stays the labelled synthetic fixture binding until a qualified market source exists.
        items.append({"field_name": "market", "state": "KNOWN", "origin": "APPLICATION_CONFIGURED",
                      "source_ref": SYNTHETIC_MARKET_SOURCE, "interpretation_revision": "",
                      "evidence_status": "HYPOTHESIS", "adoption": "PENDING",
                      "value": copy.deepcopy(record_contract.FIXTURE_STRATEGY["market"])})
        items.append({"field_name": "decision_interval_seconds", "state": "KNOWN", "origin": "APPLICATION_CONFIGURED",
                      "source_ref": INTERVAL_SOURCE, "interpretation_revision": "", "evidence_status": "HYPOTHESIS",
                      "adoption": "PENDING", "value": 300})
    items.append({"field_name": "restrictions", "state": "KNOWN", "origin": "USER_STATED",
                  "source_ref": RESTRICTIONS_SOURCE, "interpretation_revision": "", "evidence_status": "VERIFIED_FACT",
                  "value": list(intake["restrictions"])})
    return items


def _never_raises(parse: Any) -> Any:
    """Model output is an untrusted claim. Whatever it holds, a parser answers with a rejection and never an exception."""
    @functools.wraps(parse)
    def guarded(*args: Any, **kwargs: Any) -> ParsedInterpretation | Rejection:
        try:
            return parse(*args, **kwargs)
        except (RecursionError, ArithmeticError, TypeError, ValueError, KeyError, AttributeError, IndexError):
            return Rejection("unparseable_response", "", "The answer could not be read, so none of it was used.")
    return guarded


@_never_raises
def parse_interpretation_response(text: str, intake: Mapping[str, Any]) -> ParsedInterpretation | Rejection:
    response = _decode_single_object(text)
    if isinstance(response, Rejection):
        return response
    rejected = _check_top_level(response)
    if rejected is not None:
        return rejected
    sources = [(REQUEST_SOURCE, intake["original_request"])]
    model_items = _model_items(response["field_evidence"], intake, sources)
    if isinstance(model_items, Rejection):
        return model_items
    evidence = model_items + _application_items(intake, response["meaning_status"])
    reported = frozenset(item["field_name"] for item in model_items)
    questions = _parse_questions(response["questions"], evidence, reported)
    if isinstance(questions, Rejection):
        return questions
    return _parsed(response, evidence, questions, text)


def _parsed(response: Mapping[str, Any], evidence: list[dict[str, Any]], questions: tuple[OfferedQuestion, ...],
            text: str) -> ParsedInterpretation:
    return ParsedInterpretation(
        meaning_status=response["meaning_status"], missing_capability=response["missing_capability"],
        evidence_readiness=response["evidence_readiness"], field_evidence=tuple(evidence), questions=questions,
        response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())


def _meaning(evidence: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Evidence by field, without the revision it was saved in."""
    return {item["field_name"]: {key: value for key, value in item.items() if key != "interpretation_revision"}
            for item in evidence}


def _is_protected(previous: Mapping[str, Any]) -> bool:
    """Meaning the user stated, chose or adopted, or that the application configured. The model may not replace it."""
    return previous["state"] == "KNOWN" and (previous["origin"] != "AGENT_PROPOSED"
                                             or previous.get("adoption") == "ADOPTED")


def _reconcile(item: dict[str, Any], previous: Mapping[str, Any] | None, at: str) -> dict[str, Any] | Rejection:
    """The evidence a field has after a reply, or a rejection when the model would overwrite stated meaning."""
    if previous is None or previous["state"] == "MISSING":
        return item
    if _is_protected(previous):
        if item["state"] == "KNOWN" and item.get("value") == previous["value"]:
            return copy.deepcopy(previous)  # a restatement of the same meaning keeps the first statement
        if item["state"] != "CONFLICTING":
            return _reject("silent_overwrite", at, "The reply cannot replace meaning that is already stated.")
        for index, alternative in enumerate(item["conflicts"]):
            if alternative["value"] == previous["value"]:
                return _reject("not_a_conflict", f"{at}/conflicts/{index}/value",
                               "This alternative repeats the value that is already stated.")
            if alternative["source_ref"] == previous["source_ref"]:
                return _reject("conflict_alternatives_not_distinct", f"{at}/conflicts/{index}/source_passage",
                               "Each alternative must come from different words.")
        item["conflicts"] = [{"value": copy.deepcopy(previous["value"]), "source_ref": previous["source_ref"]},
                             *item["conflicts"]]
        return item
    if previous["state"] == "CONFLICTING" and not (
            item["state"] == "CONFLICTING" or (item["state"] == "KNOWN" and item["origin"] == "USER_STATED")):
        return _reject("silent_overwrite", at, "Only the user can settle a conflict.")
    return item


@_never_raises
def parse_follow_up_response(text: str, intake: Mapping[str, Any], previous_evidence: Sequence[Mapping[str, Any]],
                             answer: ClarificationAnswer) -> ParsedInterpretation | Rejection:
    """Parse the reply to a clarification. The response lists only the fields that change; the rest carry forward."""
    response = _decode_single_object(text)
    if isinstance(response, Rejection):
        return response
    rejected = _check_top_level(response)
    if rejected is not None:
        return rejected
    previous = {item["field_name"]: item for item in previous_evidence}
    sources = [(answer.answer_ref, answer.text), (REQUEST_SOURCE, intake["original_request"])]
    single_ok = frozenset(name for name, item in previous.items() if _is_protected(item))
    model_items = _model_items(response["field_evidence"], intake, sources, single_ok)
    if isinstance(model_items, Rejection):
        return model_items
    merged: dict[str, dict[str, Any]] = {name: copy.deepcopy(dict(item)) for name, item in previous.items()}
    for index, item in enumerate(model_items):
        name = item["field_name"]
        settled = _reconcile(item, previous.get(name), f"/field_evidence/{index}")
        if isinstance(settled, Rejection):
            return settled
        merged[name] = settled
    for item in merged.values():
        item["interpretation_revision"] = ""
    evidence = list(merged.values())
    if _meaning(evidence) == _meaning(previous_evidence):
        # P02 needs a clarification to name at least one changed field, so a reply that changes nothing cannot be saved.
        return _reject("reply_changed_nothing", "/field_evidence", "The reply changed no field.")
    reported = frozenset(name for name in merged if name in _model_owned_fields(intake["requested_job"]))
    questions = _parse_questions(response["questions"], evidence, reported)
    if isinstance(questions, Rejection):
        return questions
    return _parsed(response, evidence, questions, text)
