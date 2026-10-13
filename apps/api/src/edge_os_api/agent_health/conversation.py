"""Read-only agent health conversation: answers a question from one dated snapshot (P31 LOCAL).

The answer is built only from the snapshot that the same request reads, so the conversation and the direct view
quote the same values, sources, unknowns, `as_of` and `snapshot_digest`. There is no model or provider call, no write
and no financial tool: a question cannot start, stop, end or change anything. Controls stay on the direct page.
"""

from __future__ import annotations

from typing import Any

EXPLANATION_VERSION = "edge-os.agent-health-explanation/1"
QUESTION_LIMIT = 500
# Ordered: the first topic whose words appear in the question answers it. No match gives the summary.
TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reconciliation", ("reconcil", "pending", "unknown outcome", "unsettled")),
    ("controls", ("stop", "removal", "remove", "ended", "end ", "halt", "pause")),
    ("waiting", ("wait", "fault", "blocked", "silent", "stuck")),
    ("inventory", ("inventory", "holding", "position", "residual", "left")),
    ("identity", ("revision", "identity", "changed", "version")),
    ("next", ("next", "when", "schedule", "due")),
    ("last", ("last", "did", "latest", "recent", "evaluat", "trade", "attempt")),
    ("unknowns", ("missing", "unknown", "gas", "qualif", "edge")),
)
DIRECT_CONTROLS = ("Stop new entries or halt all swaps: Positions view, stops.",
                   "Request removal: Agents view, removal.",
                   "End recurring operation: Positions view, recurring operation.")


def topic_for(question: str) -> str:
    text = question.lower()
    for topic, words in TOPICS:
        if any(word in text for word in words):
            return topic
    return "summary"


def _value(field: dict[str, Any]) -> str:
    return str(field["value"]) if field["state"] == "KNOWN" else f"UNKNOWN ({field['reason']})"


def _line(text: str, *fields: str) -> dict[str, Any]:
    return {"text": text, "fields": list(fields)}


def _last(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    lines = []
    evaluation = snapshot["last_evaluation"]
    if evaluation["state"] == "KNOWN":
        item = evaluation["value"]
        saved = item["evaluation"]
        lines.append(_line(
            f"Last saved evaluation: slot {item['decision_slot']}, outcome {saved['outcome']}"
            f"{' (' + saved['reason'] + ')' if saved['reason'] else ''}. Inputs observed "
            f"{_value(saved['inputs_observed_at'])}, collected {_value(saved['inputs_collected_at'])}, evaluated "
            f"{_value(saved['evaluated_at'])}. An evaluation is not a trade.", "last_evaluation"))
    else:
        lines.append(_line(f"Last evaluation: UNKNOWN ({evaluation['reason']}).", "last_evaluation"))
    attempt = snapshot["last_trade_attempt"]
    if attempt["state"] == "KNOWN":
        item = attempt["value"]
        submission = item["submission"]
        lines.append(_line(
            f"Last trade attempt: action {item['action_id']}, attempt {submission['state']}"
            f"{' ' + submission['outcome'] if submission['outcome'] else ''}, "
            f"started {_value(submission['started_at'])}, "
            f"completed {_value(submission['completed_at'])}; job outcome {item['job_outcome']}.",
            "last_trade_attempt"))
    else:
        lines.append(_line(f"Last trade attempt: UNKNOWN ({attempt['reason']}).", "last_trade_attempt"))
    return lines


def _next(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    producer = snapshot["producer"]
    return [_line(f"Next due slot from the producer: {_value(producer['next_due_slot'])}, as read at "
                  f"{snapshot['read_at']}. Last scheduler pass {_value(producer['last_tick_at'])}.",
                  "producer.next_due_slot", "producer.last_tick_at")]


def _waiting(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    wait = snapshot["wait_reason"]
    text = ("No wait reason" if wait["state"] == "KNOWN" and wait["value"] is None else f"Wait reason {_value(wait)}")
    silent = snapshot["producer"]["producer_silent"]
    return [_line(f"{text} at {snapshot['read_at']}; producer silent: {_value(silent)}.", "wait_reason",
                  "producer.producer_silent")]


def _reconciliation(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    pending = snapshot["pending_reconciliation"]
    canonical = pending["canonical"]
    lines = [_line("Pending reconciliation (producer unsettled queue): "
                   + (", ".join(canonical["action_ids"]) or "none") if "action_ids" in canonical
                   else f"Pending reconciliation: UNKNOWN ({canonical['reason']}).",
                   "pending_reconciliation.canonical")]
    recovery, monitoring = pending["warnings"]
    lines.append(_line("Separate warnings: account recovery open or unknown for "
                       f"{', '.join(recovery['action_ids']) or 'no action'}; monitoring SUBMITTED_UNKNOWN "
                       f"{'present' if monitoring['pending'] else 'not present'}. They are not merged into one status.",
                       "pending_reconciliation.warnings"))
    return lines


def _controls(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    controls, deployment = snapshot["controls"], snapshot["deployment"]
    stops = "; ".join(f"{s['mode']} on {s['scope']} since {s['created_at']}" for s in controls["stops"]) or "none"
    removals = "; ".join(f"{r['state']} (requested {r['requested_at']}, updated {r['updated_at']})"
                         for r in controls["removals"]) or "none"
    state = "no deployment" if deployment is None else (
        f"{deployment['state']}" + (f" ({deployment['end_reason']}, {deployment['ended_at']})"
                                    if deployment["end_reason"] else ""))
    return [_line(f"Recurring operation: {state}. Stops: {stops}. Removal: {removals}.", "deployment",
                  "controls.stops", "controls.removals"),
            _line("This conversation changes nothing. Use the direct controls: " + " ".join(DIRECT_CONTROLS),
                  "controls")]


def _inventory(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    held = snapshot["residual_inventory"]
    if not held:
        return [_line("No saved position for this agent wallet.", "residual_inventory")]
    return [_line(f"Position {p['position_id']} ({p['position_state']}): {p['quantity']['raw']} raw units of "
                  f"{p['quantity']['asset_id']}, last saved {_value(p['updated_at'])}.", "residual_inventory")
            for p in held]


def _identity(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    identity = snapshot["identity"]
    saved, current = identity["saved_deployment"], identity["current_resolution"]
    now = current["value"]["execution_revision_id"] if current["state"] == "KNOWN" else f"UNKNOWN ({current['reason']})"
    return [_line(f"Saved deployment execution revision: {saved['execution_revision_id'] if saved else 'none'}. "
                  f"Current resolution: {now}. Changed: {_value(identity['changed'])}. Historical occurrences keep "
                  "their saved revision.", "identity")]


def _unknowns(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [_line(f"{item['field']}: UNKNOWN ({item['reason']}).", "unknown_inputs")
            for item in snapshot["unknown_inputs"]]


ANSWERS = {"last": _last, "next": _next, "waiting": _waiting, "reconciliation": _reconciliation,
           "controls": _controls, "inventory": _inventory, "identity": _identity, "unknowns": _unknowns}


def explain(snapshot: dict[str, Any], question: str) -> dict[str, Any]:
    topic = topic_for(question)
    if topic == "summary":
        lines = _last(snapshot) + _next(snapshot) + _waiting(snapshot) + _reconciliation(snapshot)[:1]
    else:
        lines = ANSWERS[topic](snapshot)
    return {"schema_version": EXPLANATION_VERSION, "question": question, "topic": topic,
            "record_id": snapshot["record_id"], "snapshot_digest": snapshot["snapshot_digest"],
            "as_of": snapshot["as_of"], "read_at": snapshot["read_at"], "answer": lines,
            "notice": "Read-only answer from saved records. It writes nothing, calls no provider and grants no "
                      "permission.",
            "snapshot": snapshot}
