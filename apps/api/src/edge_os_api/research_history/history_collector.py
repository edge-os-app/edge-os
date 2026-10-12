"""Bounded history collector.

The collector pulls pages from a caller-supplied response source until the source
reports completion or a finite limit stops it. It records the exact page identity
and hash, the request and cursor trace, the raw supplied events, provenance,
collection gaps and a canonical collection hash. A partial collection is never
reported as complete.

No live transport exists here. The collector never reads an environment variable
or a credential file and never opens a socket.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from edge_os_api.research_history.errors import AdapterInputError, InvalidLimits
from edge_os_api.research_history.provider_transport import (
    HistoryRequest,
    ResponseSource,
    SourceCancelled,
    SourceTimeout,
)
from edge_os_api.research_history.qualification_engine import canonical_sha256, profile_problems

PAGE_KEYS = (
    "page_id",
    "from_block",
    "next_block",
    "sha256",
    "first_block_timestamp",
    "last_block_timestamp",
    "first_parent_hash",
    "last_block_hash",
)

FIELD_SELECTION = {
    "log": ["address", "data", "topic0", "topic1", "topic2", "block_number", "transaction_index",
            "log_index", "transaction_hash", "removed"],
    "block": ["number", "hash", "timestamp"],
}


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True)
class CollectionLimits:
    """Finite caller-defined bounds. These are local test parameters, not allowances."""

    max_pages: int
    max_rows: int
    max_bytes: int
    deadline_utc: str | None = None

    def validate(self) -> None:
        for name, value in (("max_pages", self.max_pages), ("max_rows", self.max_rows),
                            ("max_bytes", self.max_bytes)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise InvalidLimits(f"{name} must be a positive integer")
        if self.deadline_utc is not None and not isinstance(self.deadline_utc, str):
            raise InvalidLimits("deadline_utc must be an ISO-8601 UTC string or None")


def _gap(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def _raw_bytes(value: Any) -> bytes:
    """Deterministic size bytes for a raw response that may hold a non-canonical value.

    A supplied response can carry a float or other value the P02 canonical encoder
    refuses. Such a value must reach the decoder as a refusal, not stop collection.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str).encode("utf-8")


def _raw_sha256(value: Any) -> str:
    return hashlib.sha256(_raw_bytes(value)).hexdigest()


def _is_nonneg_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _provider_requests(provenance: Any) -> dict[str, int] | None:
    """Evidenced actual provider request counts, or None when unknown.

    Consuming an archived page is not evidence of a new or original provider request.
    """
    if not isinstance(provenance, Mapping):
        return None
    supplied = provenance.get("provider_requests")
    if not isinstance(supplied, Mapping) or not supplied:
        return None
    if not all(isinstance(name, str) and name and _is_nonneg_int(count) for name, count in supplied.items()):
        return None
    return dict(supplied)


def _covers_scan(pages: Sequence[Mapping[str, Any]], scan: Mapping[str, int]) -> bool:
    """Whether the collected pages tile the requested scan with no gap or overlap."""
    if not pages:
        return False
    ranges = []
    for page in pages:
        low, high = page.get("from_block"), page.get("next_block")
        if not _is_nonneg_int(low) or not _is_nonneg_int(high) or high <= low:
            return False
        ranges.append((low, high))
    ranges.sort()
    if ranges[0][0] != scan["from_block"] or ranges[-1][1] != scan["to_block_exclusive"]:
        return False
    return all(nxt[0] == prev[1] for prev, nxt in zip(ranges, ranges[1:]))


def _page_record(page: Mapping[str, Any]) -> dict[str, Any]:
    return {key: page[key] for key in PAGE_KEYS if key in page}


def _query_definition(profile: Mapping[str, Any], scan: Mapping[str, int]) -> dict[str, Any]:
    return {
        "provider": profile["source"]["history_provider"],
        "address": profile["venue"]["pool_address"],
        "topic0": profile["event"]["topic0"],
        "from_block": scan["from_block"],
        "to_block_exclusive": scan["to_block_exclusive"],
        "field_selection": FIELD_SELECTION,
    }


def _scan_request(scan: Mapping[str, Any]) -> dict[str, int]:
    if not isinstance(scan, Mapping) or not {"from_block", "to_block_exclusive"} <= set(scan):
        raise AdapterInputError("SCAN_MALFORMED", "scan needs from_block and to_block_exclusive")
    low, high = scan["from_block"], scan["to_block_exclusive"]
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (low, high)):
        raise AdapterInputError("SCAN_MALFORMED", "scan bounds must be integers")
    if low >= high:
        raise AdapterInputError("SCAN_MALFORMED", "from_block must be below to_block_exclusive")
    return {"from_block": low, "to_block_exclusive": high}


def collect(profile: Mapping[str, Any], source: ResponseSource, scan: Mapping[str, Any],
            limits: CollectionLimits, provenance: Mapping[str, Any] | None = None,
            clock: Callable[[], str] = _utc_now) -> dict[str, Any]:
    """Collect bounded history pages from a supplied recorded response source.

    ``source`` is the only provider path. ``limits`` are finite and caller-defined.
    ``clock`` returns an ISO-8601 UTC string and is injected so tests stay deterministic.
    """
    limits.validate()
    problems = profile_problems(profile)
    if problems:
        raise AdapterInputError("PROFILE_INVALID",
                                "; ".join(f"{item['code']}@{item['path']}" for item in problems))
    request_scan = _scan_request(scan)
    provider_name = profile["source"]["history_provider"]
    definition = _query_definition(profile, request_scan)
    query = {
        "address": definition["address"],
        "topic0": definition["topic0"],
        "from_block": request_scan["from_block"],
        "to_block_exclusive": request_scan["to_block_exclusive"],
        "identity_sha256": canonical_sha256(definition),
        "definition": definition,
    }
    request = HistoryRequest(provider=provider_name, address=definition["address"],
                             topic0=definition["topic0"], from_block=request_scan["from_block"],
                             to_block_exclusive=request_scan["to_block_exclusive"],
                             cursor_after=None, max_rows=limits.max_rows)

    pages: list[dict[str, Any]] = []
    records: list[Any] = []
    steps: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    page_signatures: set[tuple[Any, ...]] = set()
    seen_cursors: set[int] = set()
    bytes_used = 0
    invocations = 0
    provider_version: str | None = None
    first_served: str | None = None
    last_served: str | None = None
    stop_reason = "SOURCE_EXHAUSTED"

    while True:
        if limits.deadline_utc is not None and clock() >= limits.deadline_utc:
            stop_reason = "DEADLINE"
            break
        if len(pages) >= limits.max_pages:
            stop_reason = "LIMIT_PAGES"
            break
        if len(records) >= limits.max_rows:
            stop_reason = "LIMIT_ROWS"
            break
        if bytes_used >= limits.max_bytes:
            stop_reason = "LIMIT_BYTES"
            break
        try:
            invocations += 1
            response = source.next_response(request)
        except SourceCancelled:
            stop_reason = "CANCELLED"
            break
        except SourceTimeout:
            stop_reason = "TIMEOUT"
            break
        if response is None:
            stop_reason = "SOURCE_EXHAUSTED"
            break
        if not isinstance(response, Mapping):
            gaps.append(_gap("PROVIDER_MALFORMED_RESPONSE", "response is not an object"))
            stop_reason = "PROVIDER_ERROR"
            break

        bytes_used += len(_raw_bytes(response))
        if response.get("provider") != provider_name:
            gaps.append(_gap("PROVIDER_MISMATCH", f"expected {provider_name}"))
            stop_reason = "PROVIDER_ERROR"
            break
        version = response.get("provider_version")
        if not isinstance(version, str) or not version:
            gaps.append(_gap("PROVIDER_MALFORMED_RESPONSE", "provider_version is absent"))
            stop_reason = "PROVIDER_ERROR"
            break
        if provider_version is None:
            provider_version = version
        elif version != provider_version:
            gaps.append(_gap("VERSION_CHANGED", f"{provider_version} then {version}"))
            stop_reason = "PROVIDER_ERROR"
            break
        if not _query_matches(response.get("query"), definition):
            gaps.append(_gap("QUERY_MISMATCH", "response query does not match the request"))
            stop_reason = "PROVIDER_ERROR"
            break

        page = response.get("page")
        if not isinstance(page, Mapping):
            gaps.append(_gap("PROVIDER_MALFORMED_PAGE", "page is not an object"))
            stop_reason = "PROVIDER_ERROR"
            break
        events = response.get("events", [])
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            gaps.append(_gap("PROVIDER_MALFORMED_EVENTS", "events is not a list"))
            stop_reason = "PROVIDER_ERROR"
            break

        cursor = response.get("cursor")
        after = cursor.get("after") if isinstance(cursor, Mapping) else None
        signature = (page.get("page_id"), page.get("from_block"), page.get("next_block"), page.get("sha256"))
        if signature in page_signatures:
            gaps.append(_gap("REPEATED_PAGE", f"page {page.get('page_id')} was already served"))
            stop_reason = "REPEATED_PAGE"
            break
        if after is not None and after in seen_cursors:
            gaps.append(_gap("CURSOR_CYCLE", f"cursor {after} repeats"))
            stop_reason = "CURSOR_CYCLE"
            break
        if pages and page.get("from_block") != pages[-1].get("next_block"):
            gaps.append(_gap("BLOCK_DISCONTINUITY",
                             f"page starts at {page.get('from_block')} after {pages[-1].get('next_block')}"))

        pages.append(_page_record(page))
        page_signatures.add(signature)
        records.extend(events)
        if after is not None:
            seen_cursors.add(after)
        served = response.get("served_utc")
        if isinstance(served, str):
            first_served = first_served or served
            last_served = served
        steps.append({
            "step": len(steps),
            "request": request.as_view(),
            "cursor_before": cursor.get("before") if isinstance(cursor, Mapping) else None,
            "cursor_after": after,
            "complete": response.get("complete") is True,
            "rows": len(events),
            "bytes": len(_raw_bytes(response)),
        })

        if response.get("complete") is True:
            stop_reason = "COMPLETE"
            break
        if after is None:
            stop_reason = "SOURCE_EXHAUSTED"
            break
        request = HistoryRequest(provider=provider_name, address=definition["address"],
                                 topic0=definition["topic0"], from_block=request_scan["from_block"],
                                 to_block_exclusive=request_scan["to_block_exclusive"],
                                 cursor_after=after, max_rows=limits.max_rows)

    status = "COMPLETE" if stop_reason == "COMPLETE" else "PARTIAL"
    provider_requests = _provider_requests(provenance)
    provenance_block = {
        "history_provider": provider_name,
        "data_route": profile["source"]["data_route"],
        "provider_version": provider_version,
        "first_served_utc": first_served,
        "last_served_utc": last_served,
        "origin": dict(provenance) if provenance is not None else {},
        "measurement": {
            "measured_local_attempts": "EXACT_LOCAL_COUNT",
            "provider_requests": "SUPPLIED_EVIDENCE" if provider_requests is not None else "UNKNOWN",
        },
    }
    collection = {
        "status": status,
        "stop_reason": stop_reason,
        "provider": {"history_provider": provider_name, "provider_version": provider_version,
                     "data_route": profile["source"]["data_route"]},
        "query": query,
        "requested_scan": dict(request_scan),
        "window": dict(profile["dataset"]["window"]),
        "pages": pages,
        "records": records,
        "page_count": len(pages),
        "row_count": len(records),
        "bytes": bytes_used,
        "requests": steps,
        "gaps": gaps,
        "source_invocations": {"measured_local_attempts": invocations, "provider_requests": provider_requests},
        "coverage": {"requested_scan": dict(request_scan),
                     "page_ranges": [[page.get("from_block"), page.get("next_block")] for page in pages],
                     "covers_requested_scan": _covers_scan(pages, request_scan)},
        "provenance": provenance_block,
    }
    collection["collection_sha256"] = _raw_sha256(
        {"query": query, "pages": pages, "records": records})
    return collection


def _query_matches(query: Any, definition: Mapping[str, Any]) -> bool:
    if query is None:
        return True
    if not isinstance(query, Mapping):
        return False
    return all(query.get(key) == definition[key]
               for key in ("address", "topic0", "from_block", "to_block_exclusive"))
