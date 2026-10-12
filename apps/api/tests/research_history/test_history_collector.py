"""Public-seam tests for the bounded history collector."""

from __future__ import annotations

from typing import Any, Mapping

import pytest

import _support as support
from edge_os_api.research_history import (
    AdapterInputError,
    CollectionLimits,
    HistoryRequest,
    InvalidLimits,
    RecordedResponseSource,
    SourceCancelled,
    SourceTimeout,
    collect,
)


def _limits(**overrides: Any) -> CollectionLimits:
    return CollectionLimits(**support.limits(**overrides))


def _collect(responses: list[Any], **overrides: Any) -> dict[str, Any]:
    return collect(support.profile(), RecordedResponseSource(responses), support.SCAN, _limits(**overrides),
                   {"recorded_by": "test"})


class _RaisingSource:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    def next_response(self, request: HistoryRequest) -> Mapping[str, Any] | None:
        self.calls += 1
        raise self._error


def test_complete_collection_keeps_exact_pages_and_trace() -> None:
    pages = support.standard_responses()
    result = _collect(pages)
    assert result["status"] == "COMPLETE"
    assert result["stop_reason"] == "COMPLETE"
    assert result["page_count"] == 2 and result["row_count"] == 2
    assert [page["page_id"] for page in result["pages"]] == ["rh-p1", "rh-p2"]
    assert result["pages"][0]["sha256"] == pages[0]["page"]["sha256"]
    assert result["query"]["identity_sha256"] and result["query"]["definition"]["address"] == support.POOL
    assert [step["cursor_after"] for step in result["requests"]] == [104, None]
    assert result["gaps"] == []
    assert result["provenance"]["provider_version"] == "envio-hypersync/1"
    assert result["collection_sha256"]


def test_source_exhausted_without_complete_flag_is_partial() -> None:
    pages = support.standard_responses()
    pages[-1] = {**pages[-1], "complete": False}
    result = _collect(pages)
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "SOURCE_EXHAUSTED"


@pytest.mark.parametrize(
    ("overrides", "reason", "page_count"),
    [
        ({"max_pages": 1}, "LIMIT_PAGES", 1),
        ({"max_rows": 1}, "LIMIT_ROWS", 1),
        ({"max_bytes": 1}, "LIMIT_BYTES", 1),
    ],
)
def test_finite_limits_stop_the_loop(overrides: dict[str, Any], reason: str, page_count: int) -> None:
    result = _collect(support.standard_responses(), **overrides)
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == reason
    assert result["page_count"] == page_count


def test_deadline_uses_the_injected_clock() -> None:
    result = collect(support.profile(), RecordedResponseSource(support.standard_responses()), support.SCAN,
                     _limits(deadline_utc="2026-09-25T10:00:00Z"), {"recorded_by": "test"},
                     clock=lambda: "2026-09-25T10:00:01Z")
    assert result["stop_reason"] == "DEADLINE"
    assert result["page_count"] == 0


def test_cancel_and_timeout_are_retained_as_partial() -> None:
    cancelled = collect(support.profile(), _RaisingSource(SourceCancelled("stop")), support.SCAN, _limits(),
                        None)
    timed_out = collect(support.profile(), _RaisingSource(SourceTimeout("slow")), support.SCAN, _limits(), None)
    assert cancelled["stop_reason"] == "CANCELLED"
    assert timed_out["stop_reason"] == "TIMEOUT"
    assert cancelled["status"] == timed_out["status"] == "PARTIAL"


def test_cursor_cycle_stops_before_a_duplicate_page() -> None:
    pages = support.standard_responses()
    first, second = pages
    third = {**second, "page": {**second["page"], "page_id": "rh-p3", "from_block": 111, "next_block": 120,
                                "sha256": "b" * 64}, "cursor": {"before": 108, "after": 104}}
    result = _collect([first, {**second, "cursor": {"before": 104, "after": 108}, "complete": False}, third])
    assert result["stop_reason"] == "CURSOR_CYCLE"
    assert result["page_count"] == 2
    assert any(gap["code"] == "CURSOR_CYCLE" for gap in result["gaps"])


def test_repeated_page_is_detected() -> None:
    first, second = support.standard_responses()
    repeated = {**first, "cursor": {"before": None, "after": 999}}
    result = _collect([first, repeated])
    assert result["stop_reason"] == "REPEATED_PAGE"
    assert result["page_count"] == 1
    assert any(gap["code"] == "REPEATED_PAGE" for gap in result["gaps"])


def test_block_discontinuity_is_recorded_and_collection_continues() -> None:
    first, second = support.standard_responses()
    gapped = {**second, "page": {**second["page"], "from_block": 108, "first_parent_hash": None}}
    result = _collect([first, gapped])
    assert result["stop_reason"] == "COMPLETE"
    assert any(gap["code"] == "BLOCK_DISCONTINUITY" for gap in result["gaps"])


def test_provider_mismatch_and_malformed_events_are_provider_errors() -> None:
    wrong_provider = _collect([{**support.standard_responses()[0], "provider": "OTHER"}])
    malformed = _collect([{**support.standard_responses()[0], "events": "not-a-list"}])
    assert wrong_provider["stop_reason"] == "PROVIDER_ERROR"
    assert any(gap["code"] == "PROVIDER_MISMATCH" for gap in wrong_provider["gaps"])
    assert any(gap["code"] == "PROVIDER_MALFORMED_EVENTS" for gap in malformed["gaps"])


def test_response_for_another_pool_or_range_is_refused() -> None:
    first = support.standard_responses()[0]
    wrong_pool = _collect([{**first, "query": {**first["query"], "address": "0x" + "77" * 20}}])
    wrong_range = _collect([{**first, "query": {**first["query"], "from_block": 500}}])
    for result in (wrong_pool, wrong_range):
        assert result["stop_reason"] == "PROVIDER_ERROR"
        assert any(gap["code"] == "QUERY_MISMATCH" for gap in result["gaps"])


def test_invalid_limits_are_refused_before_any_fetch() -> None:
    for bad in ({"max_pages": 0}, {"max_rows": -1}, {"max_bytes": 0}):
        with pytest.raises(InvalidLimits):
            collect(support.profile(), RecordedResponseSource([]), support.SCAN, CollectionLimits(**{**support.limits(), **bad}), None)


def test_source_invocations_are_measured_and_provider_requests_stay_unknown() -> None:
    result = _collect(support.standard_responses())
    assert result["source_invocations"] == {"measured_local_attempts": 2, "provider_requests": None}
    assert result["provenance"]["measurement"]["provider_requests"] == "UNKNOWN"


def test_evidenced_provider_requests_are_labelled() -> None:
    result = collect(support.profile(), RecordedResponseSource(support.standard_responses()), support.SCAN,
                     _limits(), {"provider_requests": {"ENVIO_HYPERSYNC": 5}})
    assert result["source_invocations"]["provider_requests"] == {"ENVIO_HYPERSYNC": 5}
    assert result["provenance"]["measurement"]["provider_requests"] == "SUPPLIED_EVIDENCE"


def test_cancel_retains_the_attempted_invocation() -> None:
    result = collect(support.profile(), _RaisingSource(SourceCancelled("stop")), support.SCAN, _limits(), None)
    assert result["source_invocations"]["measured_local_attempts"] == 1
    assert result["source_invocations"]["provider_requests"] is None


def test_malformed_profile_is_refused_before_any_invocation() -> None:
    broken = support.profile()
    del broken["venue"]
    source = RecordedResponseSource(support.standard_responses())
    with pytest.raises(AdapterInputError) as raised:
        collect(broken, source, support.SCAN, _limits(), None)
    assert raised.value.code == "PROFILE_INVALID"
    assert source.remaining == 2


def test_coverage_evidence_records_whether_the_pages_tile_the_scan() -> None:
    complete = _collect(support.standard_responses())
    first, second = support.standard_responses()
    gapped = _collect([first, {**second, "page": {**second["page"], "from_block": 108, "first_parent_hash": None}}])
    assert complete["coverage"]["covers_requested_scan"] is True
    assert gapped["coverage"]["covers_requested_scan"] is False
