"""Literal canonical payload bytes and saved-export binding for the forward history recorder.

All values are authored synthetic fixtures. Expected digests are literal constants computed outside the code under
test (the frozen scope oracle), never by the projection being tested.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.records.contract_adapter import sha256_hex
from edge_os_api.research_history.qualification_engine import raw_sha256
from scripts.history_payload_binding import (
    PayloadError,
    canonical_payload,
    check_saved_export,
    main,
    project_log,
)

SWAP_TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
POOL = "0x" + "22" * 20
QUOTE = "0x" + "33" * 20
BASE = "0x" + "44" * 20
BLOCK_HASH = "0x" + "11" * 32
ZERO_WORD = "0x" + "00" * 32
DATA_1002 = "0x" + "%064x" % 1 + "%064x" % 0 + "%064x" % 0 + "%064x" % 2
ORACLE_ABSENT_SHA = "c7032fb27b3a0b2103c49ab792a402dc9e5c99795b948dab1f3ff297d7fbcccf"
ORACLE_NULL_SHA = "925cef405e3ad73335776bc6ce117a8eacc4ef5d3d9cc547dbe478e04ac3cb82"
EMPTY_SHA = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
T0 = 1_800_000_000


def _log(**changes: Any) -> dict[str, Any]:
    log = {"block_number": 1, "transaction_index": 0, "log_index": 0, "block_hash": BLOCK_HASH,
           "address": POOL, "topic0": SWAP_TOPIC0, "topic1": ZERO_WORD, "topic2": ZERO_WORD, "data": DATA_1002,
           "removed": False, "transaction_hash": "0x" + "aa" * 32}
    log.update(changes)
    return log


def _projected(**changes: Any) -> dict[str, Any]:
    timestamp = changes.pop("block_timestamp", T0)
    return project_log(_log(**changes), block_timestamp=timestamp)


# Projection and literal canonical bytes


def test_oracle_record_with_absent_topic3_has_literal_bytes_and_digest() -> None:
    body = canonical_payload([_projected()])
    assert len(body) == 771
    assert hashlib.sha256(body).hexdigest() == ORACLE_ABSENT_SHA


def test_explicit_null_topic3_hashes_differently_from_absent() -> None:
    body = canonical_payload([_projected(topic3=None)])
    assert len(body) == 769
    assert hashlib.sha256(body).hexdigest() == ORACLE_NULL_SHA


def test_empty_bucket_digest_is_the_empty_list_digest() -> None:
    assert canonical_payload([]) == b"[]"
    assert hashlib.sha256(canonical_payload([])).hexdigest() == EMPTY_SHA


@pytest.mark.parametrize("encoded", [1, "1", "01", "0x1", "0x01", "0x0001"])
def test_integer_decimal_and_hex_quantities_project_to_the_oracle(encoded: Any) -> None:
    body = canonical_payload([_projected(block_number=encoded, block_timestamp=hex(T0))])
    assert hashlib.sha256(body).hexdigest() == ORACLE_ABSENT_SHA


def test_uppercase_hex_digits_normalize_but_prefix_stays_literal() -> None:
    upper = _projected(address="0x" + "AB" * 20, block_timestamp="0x6B49D200")
    assert upper["address"] == "0x" + "ab" * 20
    assert upper["block_timestamp"] == 0x6B49D200
    with pytest.raises(PayloadError):
        _projected(address="0X" + "ab" * 20)
    with pytest.raises(PayloadError):
        _projected(block_number="0X1")


@pytest.mark.parametrize("bad", [True, False, 1.0, -1, "-1", "+1", " 1", "1 ", "", "0x", "1.0", "0xg1", None, [1]])
def test_malformed_quantities_are_refused(bad: Any) -> None:
    with pytest.raises(PayloadError):
        _projected(log_index=bad)


@pytest.mark.parametrize("field,value", [
    ("address", "0x" + "22" * 19), ("block_hash", "0x" + "11" * 31), ("topic1", "0x" + "00" * 33),
    ("topic0", "22" * 32), ("data", DATA_1002[:-2]), ("data", "0x" + "00" * 160), ("address", "0x" + "zz" * 20),
])
def test_malformed_hex_values_are_refused(field: str, value: str) -> None:
    with pytest.raises(PayloadError):
        _projected(**{field: value})


@pytest.mark.parametrize("field", ["block_number", "transaction_index", "log_index", "block_hash", "address",
                                   "topic0", "topic1", "topic2", "data", "removed"])
def test_missing_required_field_is_refused_never_filled(field: str) -> None:
    log = _log()
    del log[field]
    with pytest.raises(PayloadError):
        project_log(log, block_timestamp=T0)


@pytest.mark.parametrize("field,value", [("removed", None), ("removed", 0), ("removed", "false"),
                                         ("topic0", None), ("topic3", "0x" + "00" * 32)])
def test_null_required_values_bad_flags_and_a_fourth_topic_are_refused(field: str, value: Any) -> None:
    with pytest.raises(PayloadError):
        _projected(**{field: value})


def test_missing_block_timestamp_is_refused() -> None:
    with pytest.raises(PayloadError):
        project_log(_log(), block_timestamp=None)


@pytest.mark.parametrize("change", [{"data": "0x" + "%064x" % 2 + "00" * 96}, {"topic1": "0x" + "01" * 32},
                                    {"address": "0x" + "23" * 20}, {"block_hash": "0x" + "12" * 32},
                                    {"removed": True}, {"block_timestamp": T0 + 1}])
def test_any_changed_projection_field_changes_the_digest(change: dict[str, Any]) -> None:
    body = canonical_payload([_projected(**change)])
    assert hashlib.sha256(body).hexdigest() != ORACLE_ABSENT_SHA


def test_records_sort_by_numeric_ordering_identity() -> None:
    first = _projected(block_number=9, log_index=2)
    second = _projected(block_number=10, log_index=0)
    third = _projected(block_number=10, log_index=1)
    body = canonical_payload([third, first, second])
    numbers = [(item["block_number"], item["log_index"]) for item in json.loads(body)]
    assert numbers == [(9, 2), (10, 0), (10, 1)]


def test_duplicate_ordering_identity_is_refused_even_for_identical_records() -> None:
    with pytest.raises(PayloadError):
        canonical_payload([_projected(), _projected()])


# Saved-export checker

QUERY = {"address": POOL, "topic0": SWAP_TOPIC0, "from_block": 0, "to_block_exclusive": 3}
RELEASE = {"release_id": "release-synthetic-1", "sha256": "ab" * 32, "kind": "SYNTHETIC_FIXTURE"}


def _iso(seconds: int) -> str:
    return {T0: "2027-01-15T08:00:00Z", T0 + 300: "2027-01-15T08:05:00Z", T0 + 600: "2027-01-15T08:10:00Z",
            T0 + 900: "2027-01-15T08:15:00Z", T0 + 1200: "2027-01-15T08:20:00Z"}[seconds]


def _handoff() -> dict[str, Any]:
    received = ["2027-01-15T08:05:31Z", "2027-01-15T08:10:31Z", "2027-01-15T08:15:31Z", "2027-01-15T08:20:31Z"]
    buckets = []
    for index in range(4):
        buckets.append({"index": index, "start_utc": _iso(T0 + 300 * index), "end_utc": _iso(T0 + 300 * index + 300),
                        "status": "DELIVERED", "reply_id": f"P3-b{index}-first", "received_at_utc": received[index],
                        "record_count": 1 if index == 0 else 0,
                        "payload_sha256": ORACLE_ABSENT_SHA if index == 0 else EMPTY_SHA, "reason": None})
    return {"schema_version": "edge-os.forward-history-handoff/1",
            "canonicalization_version": "edge-os.forward-history-payload/1",
            "attempt_id": "synthetic-attempt-1", "source_id": "forward-synthetic-1", "evidence_class": "SYNTHETIC",
            "network": {"chain_id": 143},
            "market": {"pool": POOL, "token0": QUOTE, "token1": BASE, "base": BASE, "quote": QUOTE},
            "window": {"start_utc": _iso(T0), "end_utc": _iso(T0 + 1200), "bucket_seconds": 300},
            "scan": {"from_block": 0, "to_block_exclusive": 3}, "scan_log_count": 1,
            "headers": [{"number": 0, "timestamp": T0 - 10, "hash": "0x" + "10" * 32},
                        {"number": 1, "timestamp": T0, "hash": BLOCK_HASH},
                        {"number": 2, "timestamp": T0 + 1200, "hash": "0x" + "12" * 32}],
            "buckets": buckets}


def _raw_record() -> dict[str, Any]:
    record = _log(block_number=1, transaction_index="0x0")
    record["block_timestamp"] = str(T0)
    return record


def _export(raw: list[Any] | None = None, handoff: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = [_raw_record()] if raw is None else raw
    handoff = _handoff() if handoff is None else handoff
    buckets = []
    for bucket in handoff["buckets"]:
        buckets.append({"bucket_start": bucket["start_utc"], "bucket_end": bucket["end_utc"],
                        "status": "COMPLETE_OCCUPIED" if bucket["record_count"] else "COMPLETE_EMPTY",
                        "available_at": bucket["received_at_utc"], "availability_basis": "OBSERVED_DELIVERY"})
    content = {"dataset_id": "dataset-1", "owner_id": "owner-1", "source_id": "forward-synthetic-1",
               "evidence_class": "SYNTHETIC_FIXTURE", "network": {"network": "MONAD", "chain_id": 143},
               "binding_view": {"chain_id": 143, "pool_address": POOL, "base_asset": BASE, "quote_asset": QUOTE,
                                "token_order": [BASE, QUOTE]},
               "window_start": _iso(T0), "window_end": _iso(T0 + 1200), "query": dict(QUERY),
               "raw_evidence": {"sha256": raw_sha256(raw), "record_count": len(raw)},
               "operating_release": dict(RELEASE), "buckets": buckets}
    return {"dataset_id": "dataset-1", "owner_id": "owner-1", "content_sha256": sha256_hex(content),
            "content": content, "raw_records": raw}


def _rehash(export: dict[str, Any]) -> dict[str, Any]:
    export["content"]["raw_evidence"] = {"sha256": raw_sha256(export["raw_records"]),
                                         "record_count": len(export["raw_records"])}
    export["content_sha256"] = sha256_hex(export["content"])
    return export


def _bytes(handoff: dict[str, Any]) -> bytes:
    return json.dumps(handoff, sort_keys=True, separators=(",", ":")).encode()


def _expected(handoff_bytes: bytes, **changes: Any) -> dict[str, Any]:
    expected = {"owner_id": "owner-1", "dataset_id": "dataset-1", "release": dict(RELEASE),
                "source_id": "forward-synthetic-1", "handoff_sha256": hashlib.sha256(handoff_bytes).hexdigest()}
    expected.update(changes)
    return expected


def _check(export: dict[str, Any], handoff: dict[str, Any] | None = None, **expected: Any) -> dict[str, Any]:
    body = _bytes(_handoff() if handoff is None else handoff)
    return check_saved_export(body, export, _expected(body, **expected))


def test_equal_saved_export_passes_every_bucket() -> None:
    report = _check(_export())
    assert report["overall"] == "PASS"
    assert [bucket["result"] for bucket in report["buckets"]] == ["PASS"] * 4
    assert report["buckets"][0]["saved_sha256"] == ORACLE_ABSENT_SHA
    assert report["content_sha256"] == _export()["content_sha256"]
    assert report["handoff_sha256"] == hashlib.sha256(_bytes(_handoff())).hexdigest()
    assert report["release"] == RELEASE


def test_hex_and_decimal_saved_quantities_still_bind() -> None:
    record = _raw_record()
    record.update(block_number="0x1", log_index="0", block_timestamp=hex(T0))
    assert _check(_rehash(_export(raw=[record])))["overall"] == "PASS"


def _mutated(path: str, value: Any) -> dict[str, Any]:
    export = _export()
    target: Any = export
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[int(key)] if key.isdigit() else target[key]
    target[keys[-1]] = value
    return _rehash(export) if path.startswith("content.") or path.startswith("raw_records.") else export


@pytest.mark.parametrize("path,value", [
    ("dataset_id", "dataset-2"), ("owner_id", "owner-2"), ("content.dataset_id", "dataset-2"),
    ("content.owner_id", "owner-2"), ("content.source_id", "other-source"),
    ("content.operating_release", {**RELEASE, "sha256": "cd" * 32}), ("content.network.chain_id", 10143),
    ("content.binding_view.pool_address", "0x" + "55" * 20), ("content.binding_view.base_asset", QUOTE),
    ("content.binding_view.quote_asset", BASE), ("content.window_start", _iso(T0 + 300)),
    ("content.query.from_block", 1), ("content.query.to_block_exclusive", 4),
    ("content.evidence_class", "PROVIDER_ACTUAL"), ("content.buckets.1.available_at", "2027-01-15T08:10:00Z"),
    ("content.buckets.2.bucket_end", _iso(T0 + 1200)),
    ("raw_records.0.data", "0x" + "%064x" % 2 + "00" * 96),
])
def test_contradicting_identity_or_payload_is_a_mismatch(path: str, value: Any) -> None:
    report = _check(_mutated(path, value))
    assert report["overall"] == "MISMATCH"


def test_altered_content_hash_is_a_mismatch_before_payload_comparison() -> None:
    export = _export()
    export["content_sha256"] = "00" * 32
    report = _check(export)
    assert report["overall"] == "MISMATCH"
    assert "CONTENT_SHA256" in [check["check"] for check in report["global_checks"] if check["result"] != "PASS"]


def test_altered_raw_records_without_rehash_is_a_mismatch() -> None:
    export = _export()
    export["raw_records"][0]["log_index"] = 7
    report = _check(export)
    assert report["overall"] == "MISMATCH"
    assert "RAW_SHA256" in [check["check"] for check in report["global_checks"] if check["result"] != "PASS"]


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate"])
def test_missing_extra_or_duplicate_saved_bucket_cannot_pass(change: str) -> None:
    export = _export()
    buckets = export["content"]["buckets"]
    if change == "missing":
        buckets.pop()
    elif change == "extra":
        buckets.append(dict(buckets[-1], bucket_start=_iso(T0 + 1200)))
    else:
        buckets[1] = dict(buckets[0])
    assert _check(_rehash(export))["overall"] != "PASS"


def test_extra_raw_record_in_an_empty_bucket_changes_count_and_digest() -> None:
    extra = _raw_record()
    extra.update(log_index=1, block_number=1)
    report = _check(_rehash(_export(raw=[_raw_record(), extra])))
    assert report["overall"] == "MISMATCH"
    assert report["buckets"][0]["result"] == "MISMATCH"


def test_raw_record_outside_the_scan_is_refused_not_dropped() -> None:
    outside = _raw_record()
    outside.update(block_number=3, block_hash="0x" + "13" * 32, block_timestamp=str(T0 + 1300))
    assert _check(_rehash(_export(raw=[_raw_record(), outside])))["overall"] == "MISMATCH"


def test_saved_timestamp_contradicting_the_handoff_header_is_a_mismatch() -> None:
    record = _raw_record()
    record["block_timestamp"] = str(T0 + 1)
    assert _check(_rehash(_export(raw=[record])))["overall"] == "MISMATCH"


def test_missing_saved_timestamp_is_incomplete_not_filled_from_the_handoff() -> None:
    record = _raw_record()
    del record["block_timestamp"]
    report = _check(_rehash(_export(raw=[record])))
    assert report["overall"] == "INCOMPLETE"


def test_incomplete_handoff_bucket_keeps_the_overall_binding_incomplete() -> None:
    handoff = _handoff()
    handoff["buckets"][3].update(status="INCOMPLETE", reply_id=None, received_at_utc=None, record_count=None,
                                 payload_sha256=None, reason="NOT_COVERED_AFTER_SECOND_READ")
    export = _export()
    export["content"]["buckets"][3].update(available_at=None, status="INCOMPLETE")
    report = _check(_rehash(export), handoff=handoff)
    assert report["overall"] == "INCOMPLETE"
    assert report["buckets"][3]["result"] == "INCOMPLETE"


def test_wrong_handoff_file_hash_is_a_mismatch() -> None:
    report = _check(_export(), handoff_sha256="00" * 32)
    assert report["overall"] == "MISMATCH"


def test_synthetic_handoff_cannot_bind_an_actual_dataset_label() -> None:
    handoff = _handoff()
    handoff["evidence_class"] = "ACTUAL"
    assert _check(_export(), handoff=handoff)["overall"] == "MISMATCH"


@pytest.mark.parametrize("body", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1.5}'])
def test_duplicate_keys_and_nonfinite_or_float_handoff_values_are_refused(body: bytes) -> None:
    with pytest.raises(PayloadError):
        check_saved_export(body, _export(), _expected(body))


# Offline CLI


def _write(path: Path, value: Any) -> Path:
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    return path


def test_cli_writes_one_immutable_report_bound_to_its_inputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    handoff_bytes = _bytes(_handoff())
    handoff = _write(tmp_path / "handoff.json", handoff_bytes)
    export = _write(tmp_path / "export.json", _export())
    expected = _write(tmp_path / "expected.json", _expected(handoff_bytes))
    report_path = tmp_path / "report.json"
    argv = ["--handoff", str(handoff), "--export", str(export), "--expected", str(expected), "--out", str(report_path)]
    assert main(argv) == 0
    report = json.loads(report_path.read_bytes())
    assert report["overall"] == "PASS"
    assert report["handoff_sha256"] == hashlib.sha256(handoff_bytes).hexdigest()
    assert oct(report_path.stat().st_mode & 0o777) == "0o600"
    printed = capsys.readouterr().out
    assert hashlib.sha256(report_path.read_bytes()).hexdigest() in printed
    original = report_path.read_bytes()
    assert main(argv) != 0
    assert report_path.read_bytes() == original


def test_cli_refuses_an_oversized_input_before_decoding(tmp_path: Path) -> None:
    handoff_bytes = _bytes(_handoff())
    handoff = _write(tmp_path / "handoff.json", handoff_bytes + b" " * (8 * 1024 * 1024))
    export = _write(tmp_path / "export.json", _export())
    expected = _write(tmp_path / "expected.json", _expected(handoff_bytes))
    out = tmp_path / "report.json"
    assert main(["--handoff", str(handoff), "--export", str(export), "--expected", str(expected),
                 "--out", str(out)]) != 0
    assert not out.exists()


def test_cli_refuses_a_symlinked_report_path(tmp_path: Path) -> None:
    handoff_bytes = _bytes(_handoff())
    handoff = _write(tmp_path / "handoff.json", handoff_bytes)
    export = _write(tmp_path / "export.json", _export())
    expected = _write(tmp_path / "expected.json", _expected(handoff_bytes))
    victim = _write(tmp_path / "victim.txt", b"keep")
    link = tmp_path / "report.json"
    link.symlink_to(victim)
    assert main(["--handoff", str(handoff), "--export", str(export), "--expected", str(expected),
                 "--out", str(link)]) != 0
    assert victim.read_bytes() == b"keep"


def test_checker_does_not_modify_its_inputs() -> None:
    export = _export()
    before = copy.deepcopy(export)
    _check(export)
    assert export == before


def test_actual_handoff_binds_only_an_actual_dataset_label() -> None:
    handoff = _handoff()
    handoff["evidence_class"] = "ACTUAL"
    export = _export(handoff=handoff)
    export["content"]["evidence_class"] = "PROVIDER_ACTUAL"
    assert _check(_rehash(export), handoff=handoff)["overall"] == "PASS"
    synthetic = _export(handoff=handoff)
    assert _check(synthetic, handoff=handoff)["overall"] == "MISMATCH"
