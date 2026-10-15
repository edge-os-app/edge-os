"""The interpreter's strict response format: its exact identity, the provider's strict subset, the authored fixtures it
must admit, the structure it refuses, the meaning it leaves to the parser, and its binding through `bind_release`.

Pure: no database, Docker or network. The schema shapes model generation only; every accepted case still goes through
`interpretation_response`, which stays the authority for meaning.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research import interpretation_response
from edge_os_api.research.interpretation_response import Rejection, parse_interpretation_response
from edge_os_api.research.interpreter_output_schema import conforms, interpretation_response_format
from test_hermes_relay_composition import approve, canonical, definition  # noqa: F401 - `approve` is a fixture
from test_interpretation_response import SIZING_PROPOSAL, SPOT_SCOPE, THESIS_INTAKE, thesis_response, with_item

FIXTURES = Path(__file__).parent / "fixtures" / "hermes_interpretation"
# The canonical bytes `bind_release` hashes (sorted keys, no spaces). A change to the schema must change this literal.
FORMAT_SHA256 = "cdffe6fd07f14b796cae3f97268148f6ad8893100b8080e1bc652c7d3e9cbc60"
FORMAT_BYTES = 7182
PROVIDER_KEYWORDS = {"type", "properties", "required", "additionalProperties", "items", "anyOf", "enum", "$ref",
                     "$defs", "minItems", "maxItems"}


def walk(node: Any) -> list[dict[str, Any]]:
    """Every schema object inside a schema value."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for key, child in node.items():
            if key in ("properties", "$defs"):
                for sub in child.values():
                    found.extend(walk(sub))
            elif key in ("items",):
                found.extend(walk(child))
            elif key == "anyOf":
                for sub in child:
                    found.extend(walk(sub))
    return found


def authored() -> list[tuple[str, dict[str, Any]]]:
    cases = []
    for path in sorted((FIXTURES / "cases").glob("*.json")) + sorted((FIXTURES / "follow_ups").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if "model_response" in case["provider"]:
            cases.append((f"{path.parent.name}/{path.stem}", case))
    return cases


# --- The format and its identity -------------------------------------------------------------------------------------


def test_the_format_is_the_strict_json_schema_wrapper_around_the_five_key_answer() -> None:
    response_format = interpretation_response_format()
    assert set(response_format) == {"type", "json_schema"} and response_format["type"] == "json_schema"
    assert set(response_format["json_schema"]) == {"name", "strict", "schema"}
    assert response_format["json_schema"]["name"] == "edge_os_interpretation"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["type"] == "object" and "anyOf" not in schema  # the provider's root must be one object
    assert list(schema["properties"]) == list(interpretation_response.TOP_LEVEL_FIELDS) == schema["required"]
    assert schema["properties"]["missing_capability"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_the_canonical_bytes_and_hash_are_frozen_and_stable() -> None:
    raw = canonical(interpretation_response_format())
    assert raw == canonical(interpretation_response_format())
    assert len(raw) == FORMAT_BYTES
    assert hashlib.sha256(raw).hexdigest() == FORMAT_SHA256


def test_each_call_returns_its_own_copy() -> None:
    first = interpretation_response_format()
    first["json_schema"]["schema"]["properties"]["questions"]["items"] = {}
    first["json_schema"]["schema"]["$defs"].clear()
    assert hashlib.sha256(canonical(interpretation_response_format())).hexdigest() == FORMAT_SHA256


def test_every_object_is_closed_and_requires_all_its_keys_using_only_the_provider_subset() -> None:
    schema = interpretation_response_format()["json_schema"]["schema"]
    nodes = walk(schema)
    objects = [node for node in nodes if node.get("type") == "object"]
    assert len(objects) == 1 + len(schema["$defs"])  # the root and every definition is an object
    for node in objects:
        assert node["additionalProperties"] is False, node
        assert node["required"] == list(node["properties"]), node
    for node in nodes:
        assert set(node) <= PROVIDER_KEYWORDS, set(node) - PROVIDER_KEYWORDS
        assert "enum" not in node or node["type"] == "string"


# The accepted grammar, written out by hand: the model-owned P02 CREATE_STRATEGY fields, the prompt's item branches and
# the P02 operator signatures. The emitted schema must say exactly this, whatever the generator does.
MODEL_FIELD_NAMES = ["data_inputs", "entry", "exit", "invalidation", "sizing", "additions", "partial_exits",
                     "cost_assumptions", "risk_limits", "action_scope"]
ITEM_BRANCHES = {"Stated": {"state": ["KNOWN"], "origin": ["USER_STATED"]},
                 "Proposed": {"state": ["KNOWN"], "origin": ["AGENT_PROPOSED"], "adoption": ["PENDING"]},
                 "Missing": {"state": ["MISSING"]},
                 "Conflicting": {"state": ["CONFLICTING"]}}
OPERATOR_BRANCHES = {"Constant": ["constant"], "Series": ["price", "quote_volume"], "PriceReturn": ["price_return"],
                     "Window": ["lag", "sum", "mean"], "Pair": ["gt", "gte", "lt", "lte", "and", "or"],
                     "Negation": ["not"]}
NODE_REFS = [{"$ref": f"#/$defs/{name}"} for name in OPERATOR_BRANCHES]


def assert_emitted_grammar(response_format: dict[str, Any]) -> None:
    """The emitted schema states the accepted grammar literally: field names, item branches, operators, `args` size."""
    schema = response_format["json_schema"]["schema"]
    defs = schema["$defs"]
    assert schema["properties"]["meaning_status"]["enum"] == ["SUPPORTED", "UNSUPPORTED"]
    assert schema["properties"]["evidence_readiness"]["enum"] == ["READY", "UNRESOLVED"]
    assert schema["properties"]["field_evidence"]["items"] == {"anyOf": [{"$ref": f"#/$defs/{name}"}
                                                                         for name in ITEM_BRANCHES]}
    for name, tokens in ITEM_BRANCHES.items():
        properties = defs[name]["properties"]
        assert properties["field_name"] == {"type": "string", "enum": MODEL_FIELD_NAMES}, name
        for key, enum in tokens.items():
            assert properties[key] == {"type": "string", "enum": enum}, (name, key)
    assert defs["Question"]["properties"]["field_name"]["enum"] == MODEL_FIELD_NAMES
    for name, ops in OPERATOR_BRANCHES.items():
        assert defs[name]["properties"]["op"] == {"type": "string", "enum": ops}, name
    assert sorted(op for ops in OPERATOR_BRANCHES.values() for op in ops) == sorted(
        ["constant", "price", "quote_volume", "price_return", "lag", "sum", "mean", "gt", "gte", "lt", "lte", "and",
         "or", "not"])
    assert defs["Pair"]["properties"]["args"] == {"type": "array", "items": {"anyOf": NODE_REFS},
                                                  "minItems": 2, "maxItems": 2}
    for name in ("Window", "Negation"):
        assert defs[name]["properties"]["value"] == {"anyOf": NODE_REFS}, name


def test_the_emitted_schema_states_the_accepted_grammar_literally() -> None:
    assert_emitted_grammar(interpretation_response_format())


# --- Admits the authored fixtures ------------------------------------------------------------------------------------


# Authored answers that use a token outside the prompt's grammar. The parser rejects them for the same reason.
OUTSIDE_THE_GRAMMAR = {"cases/self-adopted-proposal": "proposal_must_stay_pending"}


@pytest.mark.parametrize(("name", "case"), authored(), ids=[name for name, _ in authored()])
def test_every_authored_answer_in_the_prompt_grammar_conforms(name: str, case: dict[str, Any]) -> None:
    answer = case["provider"]["model_response"]
    if name in OUTSIDE_THE_GRAMMAR:
        assert not conforms(answer)
        assert case["expect"]["reason_code"] == OUTSIDE_THE_GRAMMAR[name]
        return
    assert conforms(answer)
    if name.startswith("cases/") and case["expect"]["result"] == "Interpreted":
        assert not isinstance(parse_interpretation_response(json.dumps(answer), case["intake"]), Rejection)


def test_the_authored_set_covers_first_and_follow_up_answers_of_every_item_state() -> None:
    states, origins, statuses = set(), set(), set()
    for _, case in authored():
        answer = case["provider"]["model_response"]
        statuses.add(answer["meaning_status"])
        for item in answer["field_evidence"]:
            states.add(item["state"])
            origins.add(item.get("origin"))
    assert states == {"KNOWN", "MISSING", "CONFLICTING"} and {"USER_STATED", "AGENT_PROPOSED"} <= origins
    assert statuses == {"SUPPORTED", "UNSUPPORTED"}
    assert sum(name.startswith("follow_ups/") for name, _ in authored()) == 3


@pytest.mark.parametrize("item", [
    {"field_name": "sizing", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
     "value": SIZING_PROPOSAL},
    {"field_name": "action_scope", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
     "value": SPOT_SCOPE},
    {"field_name": "additions", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING", "value": False},
    {"field_name": "risk_limits", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
     "value": {"max_quote_notional": "100", "max_open_positions": 1}},
    {"field_name": "cost_assumptions", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
     "value": {"fee_rate": "0.003", "slippage_rate": "0.005", "source_ref": "agent:proposal"}},
    {"field_name": "invalidation", "state": "KNOWN", "origin": "AGENT_PROPOSED", "adoption": "PENDING",
     "value": {"state": "NOT_REQUESTED", "source_ref": "agent:proposal"}},
    {"field_name": "invalidation", "state": "MISSING"},
    {"field_name": "entry", "state": "CONFLICTING", "conflicts": [
        {"value": {"op": "gt", "args": [{"op": "price_return", "lookback_buckets": 3},
                                        {"op": "constant", "value": "0.01", "unit": "DIMENSIONLESS"}]},
         "source_passage": "above 1%"}]},
    {"field_name": "entry", "state": "KNOWN", "origin": "USER_STATED", "source_passage": "s", "value": {
        "op": "and", "args": [{"op": "not", "value": {"op": "lt", "args": [{"op": "price"}, {"op": "quote_volume"}]}},
                              {"op": "gte", "args": [{"op": "mean", "value": {"op": "price"}, "buckets": 3},
                                                     {"op": "lag", "value": {"op": "sum", "value": {"op": "price"},
                                                                             "buckets": 2}, "buckets": 1}]}]}},
])
def test_each_item_state_and_value_shape_conforms(item: dict[str, Any]) -> None:
    assert conforms(with_item(item))


def test_unsupported_and_no_thesis_answers_and_question_options_conform() -> None:
    unsupported = {"meaning_status": "UNSUPPORTED", "missing_capability": "token_launch_age_filter",
                   "evidence_readiness": "UNRESOLVED", "field_evidence": [], "questions": []}
    asked = thesis_response()
    asked["field_evidence"].append({"field_name": "sizing", "state": "MISSING"})
    asked["questions"] = [{"question_id": "choose-size", "field_name": "sizing", "text": "Which size?",
                           "options": [{"id": "a", "label": "100 quote", "value": SIZING_PROPOSAL}]}]
    assert conforms(unsupported) and conforms(asked) and conforms(thesis_response())


# --- Refuses structure outside the grammar ---------------------------------------------------------------------------


def changed(change: Any) -> dict[str, Any]:
    answer = thesis_response()
    change(answer)
    return answer


@pytest.mark.parametrize("answer", [
    changed(lambda a: a.update(extra=1)),
    changed(lambda a: a.pop("questions")),
    changed(lambda a: a.update(meaning_status="MAYBE")),
    changed(lambda a: a.update(evidence_readiness="DONE")),
    changed(lambda a: a.update(missing_capability=1)),
    changed(lambda a: a.update(field_evidence={})),
    changed(lambda a: a["field_evidence"].append({"field_name": "market", "state": "MISSING"})),  # application-owned
    changed(lambda a: a["field_evidence"].append({"field_name": "restrictions", "state": "MISSING"})),
    changed(lambda a: a["field_evidence"].append({"field_name": "sizing", "state": "UNKNOWN"})),
    changed(lambda a: a["field_evidence"].append({"field_name": "sizing", "state": "MISSING", "value": None})),
    changed(lambda a: a["field_evidence"].append({"field_name": "sizing", "state": "MISSING", "origin": None})),
    changed(lambda a: a["field_evidence"][0].update(origin="USER_CONFIRMED")),
    changed(lambda a: a["field_evidence"][0].update(origin="APPLICATION_CONFIGURED")),
    changed(lambda a: a["field_evidence"][0].update(value=None)),
    changed(lambda a: a["field_evidence"][0].update(value=1.5)),  # the provider could emit it; P02 forbids floats
    changed(lambda a: a["field_evidence"][0].update(value={"op": "gt", "args": [{"op": "price"}]})),
    changed(lambda a: a["field_evidence"][0].update(value={"op": "between", "args": []})),
    changed(lambda a: a["field_evidence"][0].update(value={"kind": "FIXED_QUOTE_AMOUNT", "amount": "1"})),
    changed(lambda a: a["field_evidence"][0].update(value={"anything": "goes"})),
    changed(lambda a: a["field_evidence"][0].update(adoption="PENDING")),  # a stated field takes no adoption key
    changed(lambda a: a.update(questions=[{"question_id": "q", "field_name": "entry", "text": "?", "options": [],
                                           "hint": "x"}])),
])
def test_structure_outside_the_grammar_does_not_conform(answer: dict[str, Any]) -> None:
    assert not conforms(answer)


def test_conformance_is_strict_and_never_coerces() -> None:
    answer = thesis_response()
    answer["field_evidence"][0]["value"] = copy.deepcopy(answer["field_evidence"][0]["value"])
    answer["field_evidence"][0]["value"]["args"][0]["lookback_buckets"] = "3"  # a string where the shape has a count
    assert not conforms(answer)
    answer["field_evidence"][0]["value"]["args"][0]["lookback_buckets"] = True
    assert not conforms(answer)


# --- Leaves meaning to the parser ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("answer", "reason"), [
    (changed(lambda a: a["field_evidence"][0]["value"]["args"][1].update(value="-0.02")), "ungrounded_number"),
    (changed(lambda a: a["field_evidence"][0]["value"]["args"][0].update(lookback_buckets=-3)), None),
    (changed(lambda a: a["field_evidence"][0].update(source_passage="words the user never wrote")),
     "source_passage_not_in_request"),
    (changed(lambda a: a.update(meaning_status="UNSUPPORTED")), "missing_capability_required"),
    (changed(lambda a: a.update(missing_capability="x")), "missing_capability_not_allowed"),
    (changed(lambda a: a["field_evidence"].append(dict(a["field_evidence"][0]))), "duplicate_field"),
    (changed(lambda a: a["field_evidence"].append({"field_name": "sizing", "state": "CONFLICTING", "conflicts": [
        {"value": SIZING_PROPOSAL, "source_passage": "Buy"}]})), "conflict_needs_two_alternatives"),
    (changed(lambda a: a.update(questions=[{"question_id": "ask-entry", "field_name": "entry", "text": "Which?",
                                            "options": [{"id": "a", "label": "x", "value": "x"}]}])),
     "reserved_question_id"),
    (changed(lambda a: a.update(questions=[{"question_id": "q", "field_name": "entry", "text": "Which?",
                                            "options": []}])), "question_for_settled_field"),
])
def test_structurally_valid_answers_with_wrong_meaning_conform_and_the_parser_rejects_them(
        answer: dict[str, Any], reason: str | None) -> None:
    assert conforms(answer)
    result = parse_interpretation_response(json.dumps(answer), THESIS_INTAKE)
    if reason is None:  # a negative count is a compile-time question; the parser stores it as the model's claim
        assert not isinstance(result, Rejection)
    else:
        assert isinstance(result, Rejection) and result.reason_code == reason, result


# --- Binds through the release ---------------------------------------------------------------------------------------


def bound_definition(**record_fields: Any) -> Any:
    response_format = interpretation_response_format()
    return definition(response_format=response_format, record_fields={
        "response_format_sha256": hashlib.sha256(canonical(response_format)).hexdigest(), **record_fields})


def test_the_release_binds_exactly_this_format_and_refuses_it_changed_after_binding(approve, tmp_path: Path) -> None:
    from edge_os_api.research.hermes_relay_composition import bind_release, compose_application
    from edge_os_api.research.hermes_transport_mount import MountRefused
    from test_hermes_relay_composition import endpoint, lazy_engine

    [given] = approve(bound_definition())
    release = bind_release(given)
    assert release.policy.required_extra["response_format"] == interpretation_response_format()
    assert release.unchanged()
    given.response_format["json_schema"]["strict"] = False  # type: ignore[index] - the definition's object, not the copy
    assert release.policy.required_extra["response_format"]["json_schema"]["strict"] is True and release.unchanged()
    release.policy.required_extra["response_format"]["json_schema"]["schema"]["required"].pop()
    assert not release.unchanged()
    with pytest.raises(MountRefused, match="changed"):
        compose_application(release, lazy_engine(), endpoint=endpoint(tmp_path / "relay"), run_id="schema-unit",
                            evidence_dir=tmp_path / "jobs")


def test_a_record_naming_another_schema_hash_refuses_this_format(approve) -> None:
    from edge_os_api.research.hermes_relay_composition import bind_release
    from edge_os_api.research.hermes_transport_mount import MountRefused

    [given] = approve(bound_definition(response_format_sha256="c" * 64))
    with pytest.raises(MountRefused, match="output schema"):
        bind_release(given)


def test_the_ordinary_registries_stay_empty() -> None:
    import relay_admission

    from edge_os_api.research import hermes_relay_composition

    assert hermes_relay_composition.RELEASE_DEFINITIONS == () and relay_admission.APPROVED_ACTUAL_RELEASES == frozenset()
