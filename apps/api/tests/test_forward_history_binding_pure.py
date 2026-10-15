"""Pure checks of saved-history payload binding (SAVED-HISTORY-BINDING-L2). No database, socket or provider.

A bound stand-in release is collected in process through the accepted P07 release path; its dataset content is built by
the application's own `dataset_content`, then bound with the accepted checker. Literal digests below were computed once
from the frozen four-bucket recording and are constants, never recomputed by the code under test. Everything is
SYNTHETIC.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

import forward_history_stand_in as bound
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.research import history_dataset, history_payload_binding as binding, investigation_tools
from edge_os_api.research.history_dataset import HistoryDatasetRow
from edge_os_api.research.investigation_jobs import release_http_clients
from edge_os_api.core.research.released_source_runtime import forward_history_binding, prepare_history
from edge_os_api.research_history.qualification_engine import raw_sha256

OWNER, FOREIGN = uuid.UUID(int=1), uuid.UUID(int=2)
SETTINGS = SimpleNamespace(env="test")
# The four buckets' payload digests of the frozen recording (one Swap log per bucket); block 505's log is in the scan but
# after the window, so the scan holds five. Computed independently of the checker (contract field rules, plain
# `json.dumps(sort_keys=True, separators=(",", ":"))`, `hashlib.sha256`) and equal to the checker's projection.
BUCKET_SHA256 = ("d969a97aa6965fbcbe3c5b25223d7fbddb6af67c4c70dc3cfce6854717689715",
                 "120afba59b218f0ab26c788383f72ba111602b747e417d580a7f1bd6b8bd6677",
                 "a5ba48b802409d650c0423ff29e7c3ae4866f7a0c324aca21237b4db76557a77",
                 "014738ad0a0cd9caa2ae29c090a904646c422608fd29e34f707f4d704f17a2bb")
# The frozen stand-in handoff's canonical bytes. A change to the stand-in handoff changes this literal on purpose.
HANDOFF_SHA256 = "73f2ff003e7fdb989b47b81037a0867c8a1ef5dc3225fbf705b6218d68c8e19a"


def _collected(release: Any = None) -> tuple[Any, dict[str, Any], list[Any]]:
    runtime, *_ = bound.recording_runtime(SETTINGS, release=release)
    source = history_dataset.served_sources(runtime)[bound.SOURCE_ID]
    limits = source["release"]["history"]["limits"]
    later = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    result, collection, normalized, transport = investigation_tools.collect_recorded_history(
        source, limits, "2030-01-01T00:00:00Z", lambda: False, lambda: "2026-10-15T00:00:00Z",
        http_clients=release_http_clients(prepare_history(runtime), later,
                                          lambda: dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)))
    assert result.outcome == "COMPLETE"
    return runtime, source, [collection, normalized, transport]


@pytest.fixture(scope="module")
def saved() -> dict[str, Any]:
    """One collected, bound dataset: the stored row, the attempt's started-event content and the saved event."""
    runtime, source, (collection, normalized, transport) = _collected()
    ids = {name: uuid.uuid4() for name in ("dataset_id", "declaration_id", "job_id", "attempt_id")}
    definition = forward_history_binding(runtime)
    release = {"operating_release": {"release_id": runtime.release.release_id, "sha256": runtime.release_sha256,
                                     "kind": runtime.release.kind},
               "evidence_class": source["evidence_class"], "transport_kind": runtime.transport_kind,
               binding.REQUIREMENT_KEY: binding.requirement(definition)}
    started = {"tool": investigation_tools.COLLECT_TOOL, "input": {"source_id": source["source_id"]}, **release}
    content = history_dataset.dataset_content(
        owner_id=OWNER, source=source, collection=collection, normalized=normalized, transport=transport,
        release={**release, "application_collection_time": {"basis": "APPLICATION_CLOCK"}}, **ids)
    row = _row(content, normalized["raw_records"])
    expected = binding._expected(OWNER, row.dataset_id, started)
    report, result, reason = binding.run_checker(definition["handoff_json"], row, expected)
    event = {"schema_version": binding.EVENT_VERSION, "dataset_id": str(row.dataset_id), "result": result,
             "reason": reason, "handoff_json": definition["handoff_json"],
             "handoff_sha256": definition["handoff_sha256"], "expected": expected,
             "checker": binding.checker_identity(), "report": report, "report_sha256": record_contract.sha256_hex(report)}
    return {"row": row, "started": started, "event": event, "definition": definition, "report": report}


def _row(content: dict[str, Any], raw: list[Any]) -> HistoryDatasetRow:
    return HistoryDatasetRow(dataset_id=uuid.UUID(content["dataset_id"]), owner_id=uuid.UUID(content["owner_id"]),
                             declaration_id=uuid.UUID(content["declaration_id"]), job_id=uuid.UUID(content["job_id"]),
                             attempt_id=uuid.UUID(content["attempt_id"]), content_sha256=record_contract.sha256_hex(content),
                             content=content, raw_records=raw)


def _evaluate(saved: dict[str, Any], *, row: HistoryDatasetRow | None = None, started: Any = "SAME",
              event: Any = "SAME", owner: uuid.UUID = OWNER) -> dict[str, Any]:
    row = saved["row"] if row is None else row
    return binding.evaluate(row.content, row.dataset_id, owner, saved["started"] if started == "SAME" else started,
                            saved["event"] if event == "SAME" else event, row)


def _rewritten(saved: dict[str, Any], raw: list[Any]) -> HistoryDatasetRow:
    """A row whose raw records AND both stored hashes were rewritten consistently, as an attacker with write access
    would: only the recorder handoff can expose it."""
    content = copy.deepcopy(saved["row"].content)
    content["raw_evidence"] = {**content["raw_evidence"], "sha256": raw_sha256(raw), "record_count": len(raw)}
    return _row(content, raw)


# --------------------------------------------------------------------------------------------- literal digests

def test_the_frozen_handoff_has_literal_bucket_digests_and_its_own_digest() -> None:
    handoff = bound.handoff()
    assert [bucket["payload_sha256"] for bucket in handoff["buckets"]] == list(BUCKET_SHA256)
    assert [bucket["record_count"] for bucket in handoff["buckets"]] == [1, 1, 1, 1]
    assert handoff["scan_log_count"] == 5
    assert bound.definition()["handoff_sha256"] == HANDOFF_SHA256
    assert hashlib.sha256(bound.definition()["handoff_json"].encode()).hexdigest() == HANDOFF_SHA256


def test_the_saved_dataset_binds_and_passes_every_bucket(saved: dict[str, Any]) -> None:
    report = saved["report"]
    assert report["overall"] == "PASS" and saved["event"]["result"] == "PASS" and saved["event"]["reason"] is None
    assert [bucket["saved_sha256"] for bucket in report["buckets"]] == list(BUCKET_SHA256)
    assert report["handoff_sha256"] == HANDOFF_SHA256
    assert report["content_sha256"] == saved["row"].content_sha256
    assert saved["row"].content["verdict"]["overall"] == "QUALIFIED"
    assert saved["row"].content[binding.REQUIREMENT_KEY] == {"basis": "RELEASE_FORWARD_HISTORY_BINDING",
                                                             "handoff_sha256": HANDOFF_SHA256}
    assert "handoff_json" not in str(saved["row"].content)  # only the requirement identity enters the content


def test_a_rerun_on_unchanged_saved_data_reproduces_the_saved_report(saved: dict[str, Any]) -> None:
    state = _evaluate(saved)
    assert state["status"] == "PASS" and state["required_by"] == "RELEASE_BINDING"
    assert state["report_sha256"] == saved["event"]["report_sha256"]
    assert state["evidence_class"] == "SYNTHETIC" and state["checker_sha256"] == binding.CHECKER_SHA256
    assert binding.lineage(state) == {"status": "PASS", "required_by": "RELEASE_BINDING", "evidence_class": "SYNTHETIC",
                                      "handoff_sha256": HANDOFF_SHA256, "report_sha256": state["report_sha256"],
                                      "checker_sha256": binding.CHECKER_SHA256}


# --------------------------------------------------------------------------------------------- raw mutation

def test_a_raw_mutation_without_rehash_is_a_mismatch(saved: dict[str, Any]) -> None:
    raw = copy.deepcopy(saved["row"].raw_records)
    raw[0]["data"] = raw[0]["data"][:-1] + ("1" if raw[0]["data"][-1] != "1" else "2")
    row = _row(copy.deepcopy(saved["row"].content), raw)
    state = _evaluate(saved, row=row)
    assert (state["status"], state["reason"]) == ("MISMATCH", "RAW_SHA256:VALUE_DIFFERS")


def test_a_consistently_rehashed_amount_change_is_a_payload_mismatch(saved: dict[str, Any]) -> None:
    raw = copy.deepcopy(saved["row"].raw_records)
    raw[1]["data"] = raw[1]["data"][:-1] + ("1" if raw[1]["data"][-1] != "1" else "2")
    state = _evaluate(saved, row=_rewritten(saved, raw))
    assert (state["status"], state["reason"]) == ("MISMATCH", "BUCKET_1:PAYLOAD_DIFFERS")


def test_a_dropped_record_is_a_count_mismatch(saved: dict[str, Any]) -> None:
    raw = copy.deepcopy(saved["row"].raw_records)[1:]
    _report, result, reason = binding.run_checker(saved["definition"]["handoff_json"], _rewritten(saved, raw),
                                                  saved["event"]["expected"])
    assert (result, reason) == ("MISMATCH", "SCAN_LOG_COUNT:VALUE_DIFFERS")


# --------------------------------------------------------------------------------------------- absent and null topics

def test_explicit_null_topic3_differs_from_the_absent_topic3_the_recorder_saw(saved: dict[str, Any]) -> None:
    raw = copy.deepcopy(saved["row"].raw_records)
    assert "topic3" not in raw[2]
    raw[2]["topic3"] = None
    _report, result, reason = binding.run_checker(saved["definition"]["handoff_json"], _rewritten(saved, raw),
                                                  saved["event"]["expected"])
    assert (result, reason) == ("MISMATCH", "BUCKET_2:PAYLOAD_DIFFERS")


def test_a_saved_record_without_its_block_time_is_incomplete(saved: dict[str, Any]) -> None:
    raw = copy.deepcopy(saved["row"].raw_records)
    del raw[0]["block_timestamp"]
    _report, result, reason = binding.run_checker(saved["definition"]["handoff_json"], _rewritten(saved, raw),
                                                  saved["event"]["expected"])
    assert (result, reason) == ("INCOMPLETE", "RAW_RECORD_TIMESTAMP:SAVED_TIMESTAMP_MISSING")


# --------------------------------------------------------------------------------------------- forged PASS

def test_a_forged_saved_pass_over_changed_data_grants_nothing(saved: dict[str, Any]) -> None:
    raw = copy.deepcopy(saved["row"].raw_records)
    raw[3]["data"] = raw[3]["data"][:-1] + ("1" if raw[3]["data"][-1] != "1" else "2")
    state = _evaluate(saved, row=_rewritten(saved, raw))  # the saved event still says PASS
    assert saved["event"]["result"] == "PASS"
    assert (state["status"], state["reason"]) == ("MISMATCH", "BUCKET_3:PAYLOAD_DIFFERS")


def test_a_forged_report_with_a_recomputed_hash_must_still_reproduce(saved: dict[str, Any]) -> None:
    forged = copy.deepcopy(saved["event"])
    forged["report"]["buckets"][0]["expected_count"] = 9
    forged["report_sha256"] = record_contract.sha256_hex(forged["report"])
    state = _evaluate(saved, event=forged)
    assert (state["status"], state["reason"]) == ("MISMATCH", "SAVED_REPORT_DIFFERS")


def test_a_saved_report_that_does_not_match_its_hash_is_a_mismatch(saved: dict[str, Any]) -> None:
    forged = copy.deepcopy(saved["event"])
    forged["report"]["overall"] = "PASS"
    forged["report"]["owner_id"] = str(FOREIGN)
    state = _evaluate(saved, event=forged)
    assert (state["status"], state["reason"]) == ("MISMATCH", "SAVED_REPORT_HASH_DIFFERS")


@pytest.mark.parametrize("field,value,reason", [
    ("dataset_id", str(uuid.UUID(int=9)), "BINDING_EVENT_IDENTITY_DIFFERS"),
    ("expected", {"owner_id": str(FOREIGN)}, "BINDING_EVENT_IDENTITY_DIFFERS"),
    ("handoff_sha256", "0" * 64, "HANDOFF_DIFFERS"),
    ("handoff_json", "{}", "HANDOFF_DIFFERS"),
])
def test_an_event_with_another_identity_or_handoff_is_a_mismatch(saved: dict[str, Any], field: str, value: Any,
                                                                  reason: str) -> None:
    state = _evaluate(saved, event={**saved["event"], field: value})
    assert (state["status"], state["reason"]) == ("MISMATCH", reason)


def test_a_foreign_owner_never_matches_the_saved_identities(saved: dict[str, Any]) -> None:
    state = _evaluate(saved, owner=FOREIGN)
    assert (state["status"], state["reason"]) == ("MISMATCH", "BINDING_EVENT_IDENTITY_DIFFERS")


# --------------------------------------------------------------------------------------------- missing evidence

def test_a_missing_event_is_incomplete(saved: dict[str, Any]) -> None:
    state = _evaluate(saved, event=None)
    assert (state["status"], state["reason"]) == ("INCOMPLETE", "BINDING_EVENT_MISSING")


def test_a_saved_refusal_is_not_upgraded_by_a_later_passing_rerun(saved: dict[str, Any]) -> None:
    refused = {**saved["event"], "report": None, "report_sha256": None, "result": "INCOMPLETE",
               "reason": "CHECKER_MISSING", "checker": None}
    state = _evaluate(saved, event=refused)
    assert (state["status"], state["reason"]) == ("INCOMPLETE", "SAVED_CHECKER_MISSING")


def test_a_missing_attempt_requirement_is_incomplete(saved: dict[str, Any]) -> None:
    started = {key: value for key, value in saved["started"].items() if key != binding.REQUIREMENT_KEY}
    state = _evaluate(saved, started=started)
    assert (state["status"], state["reason"]) == ("INCOMPLETE", "BINDING_REQUIREMENT_MISSING")


def test_a_content_requirement_that_differs_from_the_attempt_is_a_mismatch(saved: dict[str, Any]) -> None:
    content = copy.deepcopy(saved["row"].content)
    content[binding.REQUIREMENT_KEY]["handoff_sha256"] = "1" * 64
    state = _evaluate(saved, row=_row(content, saved["row"].raw_records))
    assert (state["status"], state["reason"]) == ("MISMATCH", "REQUIREMENT_DIFFERS")


def test_an_unavailable_checker_is_incomplete_never_pass(saved: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    binding.checker.cache_clear()
    monkeypatch.setattr(binding, "CHECKER_SHA256", "0" * 64)
    try:
        assert binding.run_checker(saved["definition"]["handoff_json"], saved["row"], saved["event"]["expected"])[1:] \
            == ("INCOMPLETE", "CHECKER_CHANGED")
        state = _evaluate(saved)
        assert (state["status"], state["reason"]) == ("INCOMPLETE", "CHECKER_IDENTITY_DIFFERS")
    finally:
        binding.checker.cache_clear()


def test_the_in_process_caller_enforces_the_cli_export_ceiling(saved: dict[str, Any],
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binding.checker(), "MAX_EXPORT_BYTES", 1024)
    assert binding.run_checker(saved["definition"]["handoff_json"], saved["row"], saved["event"]["expected"])[1:] \
        == ("INCOMPLETE", "EXPORT_TOO_LARGE")


def test_unbound_synthetic_datasets_are_not_required_and_keep_no_lineage(saved: dict[str, Any]) -> None:
    content = {key: value for key, value in saved["row"].content.items() if key != binding.REQUIREMENT_KEY}
    started = {key: value for key, value in saved["started"].items() if key != binding.REQUIREMENT_KEY}
    state = binding.evaluate(content, saved["row"].dataset_id, OWNER, started, None, None)
    assert state["status"] == "NOT_REQUIRED" and binding.lineage(state) is None


# --------------------------------------------------------------------------------------------- synthetic and actual

def test_every_actual_dataset_requires_binding_and_an_unbound_one_is_incomplete(saved: dict[str, Any]) -> None:
    content = {key: value for key, value in saved["row"].content.items() if key != binding.REQUIREMENT_KEY}
    content["evidence_class"] = content["profile_evidence_class"] = "PROVIDER_ACTUAL"
    started = {key: value for key, value in saved["started"].items() if key != binding.REQUIREMENT_KEY}
    state = binding.evaluate(content, saved["row"].dataset_id, OWNER, started, None, None)
    assert (state["status"], state["required_by"], state["reason"]) == (
        "INCOMPLETE", "PROVIDER_ACTUAL", "BINDING_REQUIREMENT_MISSING")


def test_a_synthetic_handoff_never_binds_an_actual_dataset(saved: dict[str, Any]) -> None:
    content = copy.deepcopy(saved["row"].content)
    content["evidence_class"] = "PROVIDER_ACTUAL"
    row = _row(content, saved["row"].raw_records)
    _report, result, reason = binding.run_checker(saved["definition"]["handoff_json"], row, saved["event"]["expected"])
    assert (result, reason) == ("MISMATCH", "EVIDENCE_CLASS:VALUE_DIFFERS")
    assert content["evidence_class"] == "PROVIDER_ACTUAL"  # never relabelled


def test_the_owner_event_view_hides_the_handoff_text(saved: dict[str, Any]) -> None:
    shown = binding.public_event(binding.EVENT_KIND, saved["event"])
    assert "handoff_json" not in shown and shown["handoff_bytes"] == len(saved["definition"]["handoff_json"])
    assert shown["report_sha256"] == saved["event"]["report_sha256"]
    other = {"handoff_json": "kept"}
    assert binding.public_event("ATTEMPT_STARTED", other) is other


def test_p07_still_qualifies_the_bound_source_and_ignores_the_binding_fact() -> None:
    _runtime, _source, (collection, normalized, _transport) = _collected()
    _r, _s, (unbound_collection, unbound_normalized, _t) = _collected(bound.bound_release(binding=None))
    assert normalized["overall"] == "QUALIFIED" and collection["status"] == "COMPLETE"
    assert normalized["normalized_sha256"] == unbound_normalized["normalized_sha256"]
    assert collection["collection_sha256"] == unbound_collection["collection_sha256"]
