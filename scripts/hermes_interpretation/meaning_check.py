"""Checks a model answer against the user's meaning. Qualification support only.

The strict parser decides whether an answer has the right shape and whether its quotes occur in the request. It does
not decide whether the answer kept the user's meaning. This checker compares the RAW answer with expectations that were
written by hand from the user's own words, using literal values and quotations. It uses no model, no judge and no
similarity score. It returns a list of failures. An empty list is a meaning PASS for that case.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["check_meaning"]


def _items(response: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {item.get("field_name"): item for item in response.get("field_evidence", []) if isinstance(item, Mapping)}


def _in_texts(quote: Any, texts: Sequence[str]) -> bool:
    return isinstance(quote, str) and bool(quote) and any(quote in text for text in texts)


def _field_failures(name: str, item: Mapping[str, Any] | None, want: Mapping[str, Any], literals: Mapping[str, Any],
                    texts: Sequence[str]) -> list[str]:
    state = item.get("state") if item else None
    if "state_in" in want:
        return [] if (state or "MISSING") in want["state_in"] else [f"{name}: state {state!r} is not one of {want['state_in']}"]
    kind = want["state"]
    if kind == "MISSING":
        return [] if state in (None, "MISSING") else [f"{name}: expected missing, found {state}"]
    if kind == "NOT_KNOWN":
        return [] if state != "KNOWN" else [f"{name}: a rule was stated for it, but the user stated none"]
    if kind == "NOT_KNOWN_FROM_USER":
        return [] if not item or item.get("origin") != "USER_STATED" else [f"{name}: attributed to the user"]
    if kind == "KNOWN":
        failures: list[str] = []
        if state != "KNOWN":
            return [f"{name}: expected a known value, found {state}"]
        if item.get("origin") != want["origin"]:
            failures.append(f"{name}: origin {item.get('origin')!r}, expected {want['origin']!r}")
        if item.get("value") != literals[want["value"]]:
            failures.append(f"{name}: value differs from the literal {want['value']}")
        if item.get("source_passage") != want["quote"] or not _in_texts(item.get("source_passage"), texts):
            failures.append(f"{name}: quote is not the user's expected words")
        return failures
    if kind == "CONFLICTING":
        if state != "CONFLICTING":
            return [f"{name}: expected a conflict, found {state}"]
        failures = []
        found = [(c.get("value"), c.get("source_passage")) for c in item.get("conflicts", []) if isinstance(c, Mapping)]
        for alternative in want["alternatives"]:
            if (literals[alternative["value"]], alternative["quote"]) not in found:
                failures.append(f"{name}: conflict is missing the value {alternative['value']} with its quote")
        return failures
    return [f"{name}: unknown expectation {kind!r}"]


def check_meaning(response: Mapping[str, Any], expect: Mapping[str, Any], literals: Mapping[str, Any],
                  texts: Sequence[str]) -> list[str]:
    """Failures of `response` against `expect`. `texts` are the user's words: the request, and a reply when there is one."""
    failures: list[str] = []
    if response.get("meaning_status") != expect["meaning_status"]:
        failures.append(f"meaning_status is {response.get('meaning_status')!r}, expected {expect['meaning_status']!r}")
    capability, needle = response.get("missing_capability"), expect.get("missing_capability_contains")
    if needle is None and capability is not None:
        failures.append(f"missing_capability {capability!r} named for a supported request")
    if needle is not None and not (isinstance(capability, str) and needle.lower() in capability.lower()):
        failures.append(f"missing_capability {capability!r} does not name {needle!r}")
    if "evidence_readiness" in expect and response.get("evidence_readiness") != expect["evidence_readiness"]:
        failures.append(f"evidence_readiness is {response.get('evidence_readiness')!r}, expected {expect['evidence_readiness']!r}")
    items = _items(response)
    for name, want in expect.get("fields", {}).items():
        failures += _field_failures(name, items.get(name), want, literals, texts)
    for name in expect.get("forbid_fields", []):
        if name in items:
            failures.append(f"{name}: evidence was listed where none may be")
    allowed = set(expect.get("user_stated_only", []))
    for name, item in items.items():
        if item.get("origin") == "USER_STATED" and name not in allowed:
            failures.append(f"{name}: attributed to the user, who did not state it")
        for passage in [item.get("source_passage"), *[c.get("source_passage") for c in item.get("conflicts", []) if isinstance(c, Mapping)]]:
            if passage is not None and not _in_texts(passage, texts):
                failures.append(f"{name}: quote is not in the user's words")
    questions = [q for q in response.get("questions", []) if isinstance(q, Mapping)]
    rules = expect.get("questions", {})
    if "at_least" in rules and len(questions) < rules["at_least"]:
        failures.append(f"question count {len(questions)} is below {rules['at_least']}")
    if "at_most" in rules and len(questions) > rules["at_most"]:
        failures.append(f"question count {len(questions)} is above {rules['at_most']}")
    if rules.get("each_ends_with_question_mark") and not all(str(q.get("text", "")).rstrip().endswith("?") for q in questions):
        failures.append("a question does not end with a question mark")
    if any(not str(o.get("label", "")).strip() for q in questions for o in q.get("options", []) if isinstance(o, Mapping)):
        failures.append("a question option has no label")
    return failures
