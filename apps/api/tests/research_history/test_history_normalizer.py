"""Public-seam tests for the history normalizer and its qualifier output."""

from __future__ import annotations

import copy
from typing import Any

import pytest

import _support as support
from edge_os_api.research_history import (
    AdapterInputError,
    CollectionLimits,
    RecordedResponseSource,
    collect,
    normalize,
    project_binding,
)
from edge_os_api.research_history.qualification_engine import (
    BindingNotEmittable,
    canonical_sha256,
    profile_problems,
)

HIGH_PRECISION = 10 ** 50 + 25
HIGH_PRECISION_PRICE = "100000000000000000000000000000000000000000000000020"


def _history(profile: dict[str, Any] | None = None, responses: list[Any] | None = None,
             evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    prof = profile if profile is not None else support.profile()
    supplied = support.standard_responses() if responses is None else responses
    facts = support.evidence_facts() if evidence is None else evidence
    collection = collect(prof, RecordedResponseSource(supplied), support.SCAN,
                         CollectionLimits(**support.limits()), {"recorded_by": "test"})
    return normalize(prof, collection, facts)


def _verdicts(history: dict[str, Any]) -> dict[str, str]:
    return {name: view["verdict"] for name, view in history["qualification"]["claims"].items()}


def test_qualified_history_matches_hand_calculated_amounts() -> None:
    history = _history()
    assert history["overall"] == "QUALIFIED"
    assert set(_verdicts(history).values()) == {"QUALIFIED"}
    assert history["decimals"] == {"base": 18, "quote": 6}
    trades = {trade["identity"]: trade for trade in history["trades"]}
    assert trades["999001:101:0:0"]["price"] == "2"
    assert trades["999001:101:0:0"]["quote_amount"] == "2"
    assert trades["999001:106:0:1"]["price"] == "3"
    assert trades["999001:106:0:1"]["quote_amount"] == "3"
    assert history["observations"]["bucket_status_counts"] == {
        "COMPLETE_OCCUPIED": 2, "COMPLETE_EMPTY": 2, "INCOMPLETE": 0, "UNQUALIFIED": 0}
    assert history["observations"]["feasibility"]["status"] == "FEASIBLE"
    assert history["gaps"] == []
    assert profile_problems(history["bound_profile"]) == []


def test_both_pool_sides_are_seen_and_token_order_is_the_p02_order() -> None:
    history = _history()
    assert {trade["pool_side"] for trade in history["trades"]} == {"QUOTE_IN_BASE_OUT", "BASE_IN_QUOTE_OUT"}
    # P02 token_order is [base, quote], the opposite of the pool order kept in the profile.
    assert history["binding_view"]["token_order"] == [support.BASE, support.QUOTE]
    assert [token["role"] for token in history["bound_profile"]["pool_tokens"]] == ["QUOTE", "BASE"]


def test_supplied_record_order_does_not_change_the_result() -> None:
    forward = _history(responses=support.standard_responses())
    reversed_events = support.responses_with([], [copy.deepcopy(support.EVENT_BASE_IN),
                                                 copy.deepcopy(support.EVENT_QUOTE_IN)])
    backward = _history(responses=reversed_events)
    assert backward["overall"] == forward["overall"]
    assert sorted(t["identity"] for t in backward["trades"]) == sorted(t["identity"] for t in forward["trades"])
    assert backward["observations"]["bucket_status_counts"] == forward["observations"]["bucket_status_counts"]


@pytest.mark.parametrize(
    ("mutate", "expected_code", "counter"),
    [
        (lambda e: {**e, "block_number": 101.0}, "FIELD_NOT_UINT", "rejected"),
        (lambda e: {**e, "removed": 1}, "FIELD_NOT_BOOL", "rejected"),
        (lambda e: {**e, "topic0": "0x" + "00" * 32}, "TOPIC0_MISMATCH", "rejected"),
        (lambda e: {**e, "topic1": "0x12"}, "TOPIC_FORMAT", "rejected"),
        (lambda e: {k: v for k, v in e.items() if k != "topic2"}, "TOPIC_COUNT", "rejected"),
        (lambda e: {**e, "data": "0x12"}, "DATA_LENGTH", "rejected"),
        (lambda e: {**e, "address": "0x" + "99" * 20}, "WRONG_POOL", "foreign"),
        (lambda e: {**e, "removed": True}, "REMOVED_BY_REORG", "removed"),
    ],
)
def test_provider_records_are_refused_with_stable_codes(mutate: Any, expected_code: str, counter: str) -> None:
    bad = mutate(copy.deepcopy(support.EVENT_QUOTE_IN))
    history = _history(responses=support.single_page([bad]))
    summary = history["observations"]["ingest"]
    if counter == "rejected":
        assert summary["rejected_codes"].get(expected_code) == 1
    elif counter == "foreign":
        assert summary["foreign"] == 1
    else:
        assert summary["removed"] == 1


def test_non_object_record_is_rejected_and_the_batch_continues() -> None:
    history = _history(responses=support.single_page(["not-an-object", copy.deepcopy(support.EVENT_QUOTE_IN)]))
    summary = history["observations"]["ingest"]
    assert summary["rejected_codes"].get("NOT_AN_OBJECT") == 1
    assert summary["trades"] == 1


def test_exact_duplicate_copies_count_once() -> None:
    events = [copy.deepcopy(support.EVENT_QUOTE_IN), copy.deepcopy(support.EVENT_BASE_IN),
              copy.deepcopy(support.EVENT_QUOTE_IN)]
    history = _history(responses=support.single_page(events))
    summary = history["observations"]["ingest"]
    assert summary["trades"] == 2
    assert summary["duplicate_copies"] == 1
    assert history["overall"] == "QUALIFIED"


def test_conflicting_position_blocks_a_complete_verdict() -> None:
    variant = {**copy.deepcopy(support.EVENT_QUOTE_IN), "data": "0x" + "00" * 128}
    history = _history(responses=support.single_page([copy.deepcopy(support.EVENT_QUOTE_IN), variant]))
    assert history["observations"]["ingest"]["conflicts"] == 1
    assert history["overall"] == "UNRESOLVED"
    assert any(gap["code"] == "INGEST_CONFLICTS" for gap in history["gaps"])


def test_conflicting_page_hashes_break_the_segment() -> None:
    pages = support.standard_responses()
    reorged = support.build_page("rh-p2", 104, 111, support.P2_FIRST_TS, support.P2_LAST_TS,
                                 first_parent_hash="0x" + "44" * 32, last_block_hash=support.HASH_110)
    responses = support.responses_with([copy.deepcopy(support.EVENT_QUOTE_IN)],
                                       [copy.deepcopy(support.EVENT_BASE_IN)], page2=reorged)
    history = _history(responses=responses)
    assert any(gap["code"] == "SEGMENT_REORG_BETWEEN_PAGES" for gap in history["gaps"])
    assert history["overall"] == "UNRESOLVED"
    assert pages  # the standard fixture stays unchanged


def test_complete_empty_and_incomplete_buckets_stay_distinct() -> None:
    profile = support.profile()
    profile["dataset"]["window"] = {"start_utc": "2026-09-25T10:00:00Z", "end_utc": "2026-09-25T10:15:00Z"}
    short_page = support.build_page("rh-short", 100, 106, support.P1_FIRST_TS, support.T0 + 300)
    history = _history(profile=profile, responses=support.single_page([], page=short_page))
    counts = history["observations"]["bucket_status_counts"]
    assert counts == {"COMPLETE_OCCUPIED": 0, "COMPLETE_EMPTY": 1, "INCOMPLETE": 2, "UNQUALIFIED": 0}


def test_high_precision_price_uses_the_50_digit_half_even_context() -> None:
    profile = support.profile(decimals=(0, 0))
    event = {**copy.deepcopy(support.EVENT_QUOTE_IN),
             "data": "0x" + f"{HIGH_PRECISION:064x}" + "0" * 64 + "0" * 64 + f"{1:064x}"}
    history = _history(profile=profile, responses=support.single_page([event]))
    trade = history["trades"][0]
    assert trade["price"] == HIGH_PRECISION_PRICE
    assert trade["quote_raw"] == str(HIGH_PRECISION)
    assert trade["base_amount"] == "1"


def test_sampled_corroboration_limits_the_history_claim() -> None:
    evidence = support.evidence_facts(corroboration={"class": "SAMPLED", "provider": "QUICKNODE_JSON_RPC",
                                                     "sample_size": 1, "population_size": 2, "mismatches": 0})
    history = _history(evidence=evidence)
    assert _verdicts(history)["HISTORY_COMPLETENESS_AND_ORDER"] == "LIMITED"
    assert history["overall"] == "LIMITED"


@pytest.mark.parametrize(
    ("availability", "timing"),
    [
        ({"model": "ASSUMED_DELAY", "delay_seconds": 180}, "LIMITED"),
        ({"model": "UNKNOWN"}, "UNRESOLVED"),
    ],
)
def test_availability_models_limit_or_unresolve_timing(availability: dict[str, Any], timing: str) -> None:
    history = _history(profile=support.profile(availability=availability))
    assert _verdicts(history)["POINT_IN_TIME_AVAILABILITY"] == timing
    assert history["overall"] != "QUALIFIED"


def test_chain_id_source_contradiction_is_unresolved() -> None:
    history = _history(evidence=support.evidence_facts(chain_id_source="DOCUMENTATION"))
    assert history["overall"] == "UNRESOLVED"
    codes = [reason["code"] for reason in history["qualification"]["claims"]["BINDING_IDENTITY"]["reasons"]]
    assert "CHAIN_ID_SOURCE_CONTRADICTION" in codes


def test_limited_real_result_is_refused_by_the_p02_projection() -> None:
    sampled = {"class": "SAMPLED", "provider": "QUICKNODE_JSON_RPC", "sample_size": 1,
               "population_size": 2, "mismatches": 0}
    profile = support.profile(evidence_class="REAL_SOURCE")
    history = _history(profile=profile, evidence=support.evidence_facts(corroboration=sampled))
    assert history["overall"] == "LIMITED"
    with pytest.raises(BindingNotEmittable) as raised:
        project_binding(history["bound_profile"], history["qualification"])
    assert raised.value.code == "VERDICT_LIMITED"


def test_synthetic_result_projects_as_unqualified_not_qualified() -> None:
    history = _history()
    binding = project_binding(history["bound_profile"], history["qualification"])
    assert binding["evidence_class"] == "SYNTHETIC_FIXTURE"
    assert binding["qualification"] == "UNQUALIFIED"


def test_malformed_page_and_missing_evidence_are_input_errors() -> None:
    broken = support.single_page([copy.deepcopy(support.EVENT_QUOTE_IN)])
    broken[0]["page"] = {k: v for k, v in broken[0]["page"].items() if k != "sha256"}
    collection = collect(support.profile(), RecordedResponseSource(broken), support.SCAN,
                         CollectionLimits(**support.limits()), None)
    with pytest.raises(AdapterInputError) as page_error:
        normalize(support.profile(), collection, support.evidence_facts())
    assert page_error.value.code == "BOUND_PROFILE_INVALID"
    with pytest.raises(AdapterInputError) as evidence_error:
        normalize(support.profile(), collection, {"archive_height": 1})
    assert evidence_error.value.code == "EVIDENCE_MALFORMED"


def test_observations_label_supplied_and_derived_facts() -> None:
    history = _history()
    provenance = history["observations"]["provenance"]
    assert "corroboration" in provenance["supplied_by_caller"]
    assert "ingest" in provenance["derived_by_engine"]
    assert provenance["collection_sha256"] == history["collection"]["collection_sha256"]


def test_buckets_expose_every_window_bucket_with_consumer_fields() -> None:
    history = _history()
    buckets = history["buckets"]
    assert [bucket["bucket_start"] for bucket in buckets] == [
        "2026-09-25T10:00:00Z", "2026-09-25T10:05:00Z", "2026-09-25T10:10:00Z", "2026-09-25T10:15:00Z"]
    first = buckets[0]
    assert set(first) == {"bucket_start", "bucket_end", "status", "close", "quote_volume", "available_at",
                          "availability_basis", "reasons"}
    assert first["status"] == "COMPLETE_OCCUPIED" and first["close"] == "2" and first["quote_volume"] == "2"
    assert first["availability_basis"] == "OBSERVED_DELIVERY" and first["available_at"] == "2026-09-25T10:05:30Z"
    empty = buckets[2]
    assert empty["status"] == "COMPLETE_EMPTY" and empty["close"] is None and empty["quote_volume"] == "0"


def test_incomplete_buckets_never_become_complete_or_zero() -> None:
    profile = support.profile()
    profile["dataset"]["window"] = {"start_utc": "2026-09-25T10:00:00Z", "end_utc": "2026-09-25T10:15:00Z"}
    short_page = support.build_page("rh-short", 100, 106, support.P1_FIRST_TS, support.T0 + 300)
    history = _history(profile=profile, responses=support.single_page([], page=short_page))
    buckets = {bucket["bucket_start"]: bucket for bucket in history["buckets"]}
    assert buckets["2026-09-25T10:00:00Z"]["status"] == "COMPLETE_EMPTY"
    assert buckets["2026-09-25T10:00:00Z"]["quote_volume"] == "0"
    for start in ("2026-09-25T10:05:00Z", "2026-09-25T10:10:00Z"):
        assert buckets[start]["status"] == "INCOMPLETE"
        assert buckets[start]["close"] is None and buckets[start]["quote_volume"] is None


def test_assumed_delay_and_missing_delivery_change_only_availability() -> None:
    assumed = _history(profile=support.profile(availability={"model": "ASSUMED_DELAY", "delay_seconds": 180}))
    assert assumed["buckets"][0]["availability_basis"] == "ASSUMED_DELAY"
    assert assumed["buckets"][0]["available_at"] == "2026-09-25T10:08:00Z"
    no_record = _history(evidence=support.evidence_facts(delivery_records={}))
    assert no_record["buckets"][0]["availability_basis"] == "UNKNOWN"
    assert no_record["buckets"][0]["available_at"] is None
    assert "DELIVERY_NOT_RECORDED" in no_record["buckets"][0]["reasons"]


def test_normalized_sha256_is_repeatable_binds_the_payload_and_changes() -> None:
    first = _history()
    second = _history()
    assert first["normalized_sha256"] == second["normalized_sha256"]
    payload = {key: value for key, value in first.items() if key != "normalized_sha256"}
    assert canonical_sha256(payload) == first["normalized_sha256"]
    tampered = copy.deepcopy(payload)
    tampered["overall"] = "QUALIFIED_CHANGED"
    assert canonical_sha256(tampered) != first["normalized_sha256"]
    other = _history(profile=support.profile(decimals=(0, 0)), responses=support.single_page([]))
    assert other["normalized_sha256"] != first["normalized_sha256"]
