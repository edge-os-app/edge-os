"""Deterministic, bounded investigation tools (`edge-os.investigation-tool/1`).

An investigation job may call only the tools in `TOOLS`. Each tool is a pure local calculation over saved inputs or the
declared recorded source. None opens a socket, reads a credential, calls a model or touches a wallet, consent,
admission, execution or funding path; `test_investigation_jobs.py` checks those imports. A real Hermes tool runner
waits for the released P05 safeguards and an approved inference budget; this module proves no Hermes tool isolation.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research import comparison_runs, history_dataset, native_history_collection

TOOL_VERSION = "edge-os.investigation-tool/1"
COLLECT_TOOL = "collect_recorded_history"
COMPARE_TOOL = "compare_declared_effects"


@dataclass(frozen=True)
class ToolResult:
    """One finished tool call. `usage` keeps unknown provider usage as None, never zero; `compute_ms` is measured."""

    tool: str
    outcome: str
    output: dict[str, Any]
    usage: dict[str, Any]
    contrary_findings: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


def _elapsed_ms(started: float) -> int:
    """Measured wall time of one tool call in whole milliseconds (at least 1)."""
    return max(1, math.ceil((time.monotonic() - started) * 1000))


def input_sha256(payload: Mapping[str, Any]) -> str:
    return record_contract.sha256_hex(dict(payload))


def collect_recorded_history(source: Mapping[str, Any], bounds: Mapping[str, Any], deadline_utc: str | None,
                             cancelled: Callable[[], bool], clock: Callable[[], str],
                             http_clients: Callable[..., Any] | None = None) -> tuple[ToolResult, dict[str, Any],
                                                                                      dict[str, Any],
                                                                                      dict[str, Any] | None]:
    """Collect and qualify the one declared recorded source. P07 partial results are outcomes, not errors.

    A `RECORDED_NATIVE_RESPONSE` source runs through the accepted P07 transport and corroboration with recorded
    clients; an `AUTHORED_HTTP_RESPONSE` source runs the same seams through the accepted P07 HTTP clients the caller
    composed. Both return their transport facts; a bundle source returns None for them."""
    started = time.monotonic()
    transport = None
    if source["evidence_class"] in history_dataset.NATIVE_SHAPED:
        base_clients = None
        if source["evidence_class"] == history_dataset.HTTP_CLASS:
            if http_clients is None:
                raise ValueError("the HTTP source needs the application's composed HTTP clients")
            base_clients = http_clients(source, bounds, cancelled)
        collection, normalized, transport = native_history_collection.collect_native(
            source, bounds, deadline_utc, cancelled, clock, base_clients)
        usage_state, usage = history_dataset.measured_usage(transport)
    else:
        collection, normalized = history_dataset.collect_recorded(source, bounds, deadline_utc, cancelled, clock)
        usage_state, usage = history_dataset.provider_usage(source)
    outcome = "COMPLETE" if collection["status"] == "COMPLETE" else f"PARTIAL_{collection['stop_reason']}"
    result = ToolResult(
        tool=COLLECT_TOOL, outcome=outcome,
        output={"status": collection["status"], "stop_reason": collection["stop_reason"],
                "overall": normalized["overall"], "collection_sha256": collection["collection_sha256"],
                "normalized_sha256": normalized["normalized_sha256"]},
        usage={"provider_requests_state": usage_state, "provider_requests": usage,
               "measured_local_attempts": collection["source_invocations"]["measured_local_attempts"],
               "compute_ms": _elapsed_ms(started)},
        provenance={"tool_version": TOOL_VERSION, "source_id": source["source_id"],
                    "evidence_class": source["evidence_class"], "content_label": source["content_label"],
                    "query_sha256": collection["query"]["identity_sha256"]})
    return result, collection, normalized, transport


def compare_declared_effects(declaration: Mapping[str, Any], dataset: Mapping[str, Any]) -> ToolResult:
    """Apply the declaration's exact adopted rules to the saved dataset with the accepted P09 engine."""
    started = time.monotonic()
    report = comparison_runs.compare_history(dict(declaration), dict(dataset))
    return ToolResult(
        tool=COMPARE_TOOL, outcome=report["outcome"], output=report,
        usage={"provider_requests_state": "NONE", "provider_requests": {},
               "compute_ms": _elapsed_ms(started)},
        contrary_findings=list(report["contrary_findings"]),
        provenance={"tool_version": TOOL_VERSION, "engine": "p09.effect-comparison",
                    "dataset_id": dataset["dataset_id"], "normalized_sha256": dataset["normalized_sha256"]})


TOOLS: dict[str, Callable[..., Any]] = {COLLECT_TOOL: collect_recorded_history, COMPARE_TOOL: compare_declared_effects}
