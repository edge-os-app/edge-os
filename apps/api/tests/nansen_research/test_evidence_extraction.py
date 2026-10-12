"""Public-seam tests for deterministic evidence extraction.

The tests keep raw provider values, nulls, duplicates and incomplete buckets
visible. No value is summed, scaled or turned into zero.
"""

from __future__ import annotations

import pytest

import nansen_fixtures as support
from edge_os_api.nansen_research import (
    NansenClient,
    NansenRequestError,
    classify_availability,
    expected_bucket_starts,
    extract_flow_evidence,
    extract_holder_evidence,
)


def _fetch(operation: str, payload: dict, *, page: int = 1):
    body = support.holder_body(page=page) if operation == "holders" else support.flow_body(page=page)
    transport = support.RecordingTransport([support.response(200, payload)])
    client = NansenClient(transport, support.limits())
    return client.call(operation, body)


def test_holder_rows_keep_raw_text_and_null_and_pagination() -> None:
    page1 = support.holder_payload(
        [support.holder_row("0xaaa", token_amount=1000.5, ownership_percentage=0.5, value_usd=None,
                            address_label="Whale"),
         support.holder_row("0xbbb", token_amount=900, ownership_percentage=None)],
        is_last_page=False,
    )
    evidence = extract_holder_evidence([_fetch("holders", page1)])
    assert evidence.rows[0].token_amount == "1000.5"
    assert evidence.rows[0].value_usd is None
    assert evidence.rows[1].ownership_percentage is None
    assert evidence.pagination_is_last_page is False
    assert evidence.pages == 1


def test_duplicate_addresses_are_recorded_not_double_counted() -> None:
    page1 = support.holder_payload([support.holder_row("0xaaa")], is_last_page=False)
    page2 = support.holder_payload([support.holder_row("0xaaa"), support.holder_row("0xccc")])
    evidence = extract_holder_evidence([_fetch("holders", page1), _fetch("holders", page2, page=2)])
    assert evidence.duplicate_addresses == ("0xaaa",)
    assert len(evidence.rows) == 3


def test_flow_counts_keep_fractional_and_negative_text() -> None:
    bucket = support.flow_bucket("2026-10-06T09:00:00Z", bucket_end="2026-10-06T10:00:00Z",
                                 total_inflows_count=1.5, total_outflows_count=-2)
    evidence = extract_flow_evidence([_fetch("flows", support.flow_payload([bucket]))], support.window())
    assert evidence.buckets[0].total_inflows_count == "1.5"
    assert evidence.buckets[0].total_outflows_count == "-2"


def test_missing_and_incomplete_buckets_are_visible() -> None:
    starts = support.hourly_starts(25)
    assert starts[0] == "2026-10-06T09:00:00Z"
    # Provide every start except the first, and mark the last bucket incomplete.
    buckets = []
    for index, item in enumerate(starts):
        if index == 0:
            continue
        end = starts[index + 1] if index + 1 < len(starts) else None
        buckets.append(support.flow_bucket(item, bucket_end=end, is_complete=(index != len(starts) - 1)))
    evidence = extract_flow_evidence([_fetch("flows", support.flow_payload(buckets))], support.window())
    assert evidence.expected_starts[0] == "2026-10-06T09:00:00Z"
    assert evidence.missing_starts == ("2026-10-06T09:00:00Z",)
    assert len(evidence.incomplete_starts) == 1
    assert evidence.complete_seconds == 23 * 3600


def test_duplicate_bucket_start_is_recorded() -> None:
    repeated = support.flow_bucket("2026-10-06T09:00:00Z", bucket_end="2026-10-06T10:00:00Z")
    evidence = extract_flow_evidence(
        [_fetch("flows", support.flow_payload([repeated, dict(repeated)]))], support.window())
    assert evidence.duplicate_starts == ("2026-10-06T09:00:00Z",)


def test_unknown_completeness_is_not_counted_as_complete() -> None:
    bucket = support.flow_bucket("2026-10-06T09:00:00Z", bucket_end="2026-10-06T10:00:00Z", is_complete=None)
    evidence = extract_flow_evidence([_fetch("flows", support.flow_payload([bucket]))], support.window())
    assert evidence.complete_seconds == 0
    assert any("unknown completeness" in warning for warning in evidence.warnings)


def test_expected_bucket_starts_switch_to_daily_over_seven_days() -> None:
    hourly = expected_bucket_starts(support.window())
    assert len(hourly) == 25
    daily = expected_bucket_starts(support.window("2026-10-01T00:00:00Z", "2026-10-10T00:00:00Z"))
    assert len(daily) == 10
    assert daily[1] == "2026-10-02T00:00:00Z"


def test_availability_classifier_covers_all_states() -> None:
    checked = "2026-01-01T09:00:00Z"
    assert classify_availability(None, checked, 300) == "unknown"
    assert classify_availability("2026-01-01T09:00:00Z", checked, 300) == "within_declared_age"
    assert classify_availability("2026-01-01T08:55:00Z", checked, 300) == "within_declared_age"
    assert classify_availability("2026-01-01T08:54:59Z", checked, 300) == "stale"
    assert classify_availability("2026-01-01T10:00:00Z", checked, 300) == "not_yet_available"
    with pytest.raises(ValueError):
        classify_availability(checked, "2026-01-01T09:00:00", 300)
    with pytest.raises(ValueError):
        classify_availability(checked, checked, -1)


def test_wrong_token_or_network_request_is_refused() -> None:
    with pytest.raises(NansenRequestError):
        support.request(network="ethereum").validate()
    with pytest.raises(NansenRequestError):
        support.request(chain_id=1).validate()
    with pytest.raises(NansenRequestError):
        support.request(question=" ").validate()
