"""Pure canonical payload projection and saved-export binding for forward history deliveries.

The forward history recorder freezes, for each 300-second bucket, the digest of every Swap log it received up to the
first reply that covered that bucket. This module owns the one projection both sides use and the offline comparison
of a saved application dataset export with that recorder handoff. It performs no network or database access.

Canonicalization ``edge-os.forward-history-payload/1`` amends the predecessor ``payload_binding`` rule
(SOURCE_FACT_PACKET.json sha256 c4fc01c4...) only where it was ambiguous: optional ``topic3`` keeps ABSENT distinct
from explicit null through a presence tag, and quantity encodings are strictly defined. See
``docs/qualification/forward-history-recorder/CONTRACT.md``.

A PASS binds payload equality only. It does not authenticate the owner, prove database provenance, grant source
rights, promote P07 qualification or authorize replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from edge_os_api.records.contract_adapter import Invalid, canonical_bytes, sha256_hex, strict_loads
from edge_os_api.research_history.qualification_engine import epoch, iso_utc, raw_sha256

CANONICALIZATION_VERSION = "edge-os.forward-history-payload/1"
HANDOFF_SCHEMA = "edge-os.forward-history-handoff/1"
REPORT_SCHEMA = "edge-os.history-payload-binding/1"
BUCKET_COUNT = 4
BUCKET_SECONDS = 300
MAX_HANDOFF_BYTES = 8 * 1024 * 1024
MAX_EXPORT_BYTES = 64 * 1024 * 1024  # the recorder's aggregate reply ceiling; no export can legitimately exceed it
MAX_EXPECTED_BYTES = 64 * 1024

PROJECTION_FIELDS = ("block_number", "transaction_index", "log_index", "block_hash", "block_timestamp", "address",
                     "topic0", "topic1", "topic2", "topic3", "data", "removed")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
MAX_QUANTITY = 2 ** 256 - 1  # every provider quantity here is at most an unsigned 256-bit word
_MAX_DECIMAL_DIGITS = len(str(MAX_QUANTITY))
_MAX_HEX_DIGITS = 64
# Saved application evidence classes (research/history_dataset.py, core/research/released_source_runtime.py).
SYNTHETIC_DATASET_CLASSES = frozenset({"RECORDED_RESPONSE", "RECORDED_NATIVE_RESPONSE", "AUTHORED_HTTP_RESPONSE",
                                       "RELEASE_STAND_IN_RESPONSE"})
ACTUAL_DATASET_CLASSES = frozenset({"PROVIDER_ACTUAL"})
_SWAP_DATA_BYTES = 128

PASS, MISMATCH, INCOMPLETE = "PASS", "MISMATCH", "INCOMPLETE"


class PayloadError(ValueError):
    """A value cannot be projected or a binding input is malformed. ``code`` is stable; no provider text."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def quantity(value: Any, field: str) -> int:
    """A nonnegative integer from a JSON integer, ASCII decimal digits or ``0x`` hex digits. Nothing else."""
    if isinstance(value, bool):
        raise PayloadError("QUANTITY_INVALID", field)
    if isinstance(value, int):
        if not 0 <= value <= MAX_QUANTITY:
            raise PayloadError("QUANTITY_INVALID", field)
        return value
    if not isinstance(value, str) or not value:
        raise PayloadError("QUANTITY_INVALID", field)
    if value.startswith("0x"):
        digits = value[2:]
        if not digits or len(digits) > _MAX_HEX_DIGITS or not set(digits) <= _HEX_DIGITS:
            raise PayloadError("QUANTITY_INVALID", field)
        return int(digits, 16)
    if len(value) > _MAX_DECIMAL_DIGITS or not value.isascii() or not value.isdigit():
        raise PayloadError("QUANTITY_INVALID", field)
    parsed = int(value, 10)
    if parsed > MAX_QUANTITY:
        raise PayloadError("QUANTITY_INVALID", field)
    return parsed


def hex_value(value: Any, byte_length: int, field: str) -> str:
    """Validate ``0x`` plus exactly ``byte_length`` bytes of hex, then lowercase the digits."""
    if (not isinstance(value, str) or len(value) != 2 + 2 * byte_length or not value.startswith("0x")
            or not set(value[2:]) <= _HEX_DIGITS):
        raise PayloadError("HEX_INVALID", field)
    return "0x" + value[2:].lower()


def project_log(log: Mapping[str, Any], *, block_timestamp: Any) -> dict[str, Any]:
    """The twelve-field canonical projection of one V2 Swap log. Required fields are never filled."""
    if not isinstance(log, Mapping):
        raise PayloadError("RECORD_NOT_OBJECT")
    for field in ("block_number", "transaction_index", "log_index", "block_hash", "address", "topic0", "topic1",
                  "topic2", "data", "removed"):
        if field not in log or log[field] is None:
            raise PayloadError("FIELD_MISSING", field)
    if block_timestamp is None:
        raise PayloadError("FIELD_MISSING", "block_timestamp")
    if not isinstance(log["removed"], bool):
        raise PayloadError("REMOVED_NOT_BOOLEAN")
    if "topic3" not in log:
        topic3 = {"presence": "ABSENT"}
    elif log["topic3"] is None:
        topic3 = {"presence": "NULL"}
    else:
        raise PayloadError("TOPIC3_UNSUPPORTED")
    return {
        "block_number": quantity(log["block_number"], "block_number"),
        "transaction_index": quantity(log["transaction_index"], "transaction_index"),
        "log_index": quantity(log["log_index"], "log_index"),
        "block_hash": hex_value(log["block_hash"], 32, "block_hash"),
        "block_timestamp": quantity(block_timestamp, "block_timestamp"),
        "address": hex_value(log["address"], 20, "address"),
        "topic0": hex_value(log["topic0"], 32, "topic0"),
        "topic1": hex_value(log["topic1"], 32, "topic1"),
        "topic2": hex_value(log["topic2"], 32, "topic2"),
        "topic3": topic3,
        "data": hex_value(log["data"], _SWAP_DATA_BYTES, "data"),
        "removed": log["removed"],
    }


def ordering_key(record: Mapping[str, Any]) -> tuple[int, int, int]:
    return record["block_number"], record["transaction_index"], record["log_index"]


def canonical_payload(records: Iterable[Mapping[str, Any]]) -> bytes:
    """UTF-8 canonical JSON of projected records in numeric chain order. Duplicate identities are refused."""
    ordered = sorted(records, key=ordering_key)
    for previous, current in zip(ordered, ordered[1:]):
        if ordering_key(previous) == ordering_key(current):
            raise PayloadError("DUPLICATE_ORDERING_IDENTITY")
    try:
        return canonical_bytes(ordered)
    except Invalid as error:
        raise PayloadError("NOT_CANONICAL") from error


def payload_sha256(records: Iterable[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_payload(records)).hexdigest()


def bucket_members(records: Iterable[Mapping[str, Any]], start: int, end: int) -> list[Mapping[str, Any]]:
    """Half-open membership ``start <= block_timestamp < end``."""
    return [record for record in records if start <= record["block_timestamp"] < end]


def strict_json(body: bytes, code: str) -> Any:
    """Decode JSON refusing duplicate keys, floats and non-finite constants."""
    try:
        return strict_loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, Invalid) as error:
        raise PayloadError(code) from error


# Saved-export comparison


class _Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, check: str, result: str, reason: str | None = None) -> None:
        self.checks.append({"check": check, "result": result, "reason": reason})

    def same(self, check: str, saved: Any, expected: Any) -> bool:
        """Missing evidence on either side is INCOMPLETE; it never becomes PASS through None == None."""
        if saved is None or expected is None:
            self.add(check, INCOMPLETE, "VALUE_MISSING")
            return False
        ok = saved == expected
        self.add(check, PASS if ok else MISMATCH, None if ok else "VALUE_DIFFERS")
        return ok


def _overall(results: Sequence[str]) -> str:
    if MISMATCH in results:
        return MISMATCH
    if INCOMPLETE in results:
        return INCOMPLETE
    return PASS


def _get(mapping: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(mapping, Mapping) or key not in mapping:
            return None
        mapping = mapping[key]
    return mapping


def _evidence_side(label: Any) -> str | None:
    """The side of a saved application evidence class. Unknown or malformed labels have no side."""
    if label in SYNTHETIC_DATASET_CLASSES:
        return "SYNTHETIC"
    if label in ACTUAL_DATASET_CLASSES:
        return "ACTUAL"
    return None


_EXPECTED_TEXT = ("owner_id", "dataset_id", "source_id", "handoff_sha256")
_RELEASE_FIELDS = ("release_id", "sha256", "kind")


def _require_expected(expected: Any) -> None:
    """The trusted caller's identities are mandatory; an incomplete expectation is refused, never defaulted."""
    def text(value: Any) -> bool:
        return isinstance(value, str) and value != ""
    release = expected.get("release") if isinstance(expected, Mapping) else None
    if (not isinstance(expected, Mapping) or not all(text(expected.get(key)) for key in _EXPECTED_TEXT)
            or not isinstance(release, Mapping) or not all(text(release.get(key)) for key in _RELEASE_FIELDS)):
        raise PayloadError("EXPECTED_INVALID")


def _check_identity(report: _Report, handoff: Mapping[str, Any], export: Mapping[str, Any],
                    expected: Mapping[str, Any]) -> None:
    content = export.get("content")
    for key in ("dataset_id", "owner_id"):
        report.same(f"OUTER_{key.upper()}", export.get(key), expected.get(key))
        report.same(f"INNER_{key.upper()}", _get(content, key), expected.get(key))
    saved_release = _get(content, "operating_release")
    for field in _RELEASE_FIELDS:
        report.same(f"RELEASE_{field.upper()}", _get(saved_release, field), expected["release"][field])
    report.same("SOURCE_ID", _get(content, "source_id"), expected.get("source_id"))
    report.same("HANDOFF_SOURCE_ID", handoff.get("source_id"), expected.get("source_id"))
    handoff_side = handoff.get("evidence_class")
    report.same("EVIDENCE_CLASS", _evidence_side(_get(content, "evidence_class")),
                handoff_side if handoff_side in ("SYNTHETIC", "ACTUAL") else None)
    report.same("CHAIN_ID", _get(content, "network", "chain_id"), _get(handoff, "network", "chain_id"))
    market = handoff.get("market") or {}
    report.same("POOL", _get(content, "binding_view", "pool_address"), market.get("pool"))
    report.same("BASE_ASSET", _get(content, "binding_view", "base_asset"), market.get("base"))
    report.same("QUOTE_ASSET", _get(content, "binding_view", "quote_asset"), market.get("quote"))
    report.same("WINDOW_START", _get(content, "window_start"), _get(handoff, "window", "start_utc"))
    report.same("WINDOW_END", _get(content, "window_end"), _get(handoff, "window", "end_utc"))
    scan = handoff.get("scan")
    if not isinstance(scan, Mapping):
        report.add("SCAN", INCOMPLETE, "HANDOFF_SCAN_MISSING")
    else:
        report.same("SCAN_FROM", _get(content, "query", "from_block"), scan.get("from_block"))
        report.same("SCAN_TO", _get(content, "query", "to_block_exclusive"), scan.get("to_block_exclusive"))
    report.same("QUERY_ADDRESS", _get(content, "query", "address"), market.get("pool"))


def _project_saved(report: _Report, handoff: Mapping[str, Any], raw: Sequence[Any]) -> list[dict[str, Any]] | None:
    """Project every saved raw record; prove its timestamp against the retained header. None when unusable."""
    headers: dict[int, tuple[int, str]] = {}
    for header in handoff.get("headers") or []:
        headers[header["number"]] = (header["timestamp"], header["hash"])
    scan = handoff.get("scan") or {}
    low, high = scan.get("from_block"), scan.get("to_block_exclusive")
    projected: list[dict[str, Any]] = []
    for record in raw:
        if not isinstance(record, Mapping) or record.get("block_timestamp") is None:
            report.add("RAW_RECORD_TIMESTAMP", INCOMPLETE, "SAVED_TIMESTAMP_MISSING")
            return None
        try:
            item = project_log(record, block_timestamp=record["block_timestamp"])
        except PayloadError as error:
            report.add("RAW_RECORD_PROJECTION", MISMATCH, error.code)
            return None
        if low is None or high is None or not low <= item["block_number"] < high:
            report.add("RAW_RECORD_IN_SCAN", MISMATCH, "RECORD_OUTSIDE_SCAN")
            return None
        header = headers.get(item["block_number"])
        if header is None:
            report.add("RAW_RECORD_HEADER", INCOMPLETE, "HANDOFF_HEADER_MISSING")
            return None
        if header != (item["block_timestamp"], item["block_hash"]):
            report.add("RAW_RECORD_HEADER", MISMATCH, "HEADER_FACT_DIFFERS")
            return None
        projected.append(item)
    try:
        canonical_payload(projected)
    except PayloadError as error:
        report.add("RAW_RECORD_IDENTITY", MISMATCH, error.code)
        return None
    report.add("RAW_RECORDS", PASS)
    report.same("SCAN_LOG_COUNT", len(projected), handoff.get("scan_log_count"))
    return projected


def _check_buckets(handoff: Mapping[str, Any], saved: Any, projected: list[dict[str, Any]] | None) -> list[dict]:
    expected_buckets = handoff.get("buckets")
    results = []
    saved_list = saved if isinstance(saved, list) else []
    by_start: dict[Any, list[Any]] = {}
    for bucket in saved_list:
        by_start.setdefault(_get(bucket, "bucket_start"), []).append(bucket)
    if not isinstance(expected_buckets, list) or len(expected_buckets) != BUCKET_COUNT:
        return [{"index": None, "result": INCOMPLETE, "reason": "HANDOFF_BUCKETS_INVALID"}]
    extra = len(saved_list) != BUCKET_COUNT
    for bucket in expected_buckets:
        entry: dict[str, Any] = {"index": bucket["index"], "start_utc": bucket["start_utc"],
                                 "expected_count": bucket["record_count"],
                                 "expected_sha256": bucket["payload_sha256"]}
        matches = by_start.get(bucket["start_utc"], [])
        if extra or len(matches) != 1:
            results.append({**entry, "result": MISMATCH, "reason": "SAVED_BUCKET_SET_DIFFERS"})
            continue
        stored = matches[0]
        if stored.get("bucket_end") != bucket["end_utc"]:
            results.append({**entry, "result": MISMATCH, "reason": "BUCKET_INTERVAL_DIFFERS"})
            continue
        if bucket["status"] != "DELIVERED":
            results.append({**entry, "result": INCOMPLETE, "reason": bucket.get("reason") or "NOT_DELIVERED"})
            continue
        available = iso_utc(max(epoch(bucket["end_utc"]), epoch(bucket["received_at_utc"])))
        if stored.get("available_at") != available:
            results.append({**entry, "result": MISMATCH, "reason": "AVAILABLE_AT_DIFFERS"})
            continue
        if projected is None:
            results.append({**entry, "result": INCOMPLETE, "reason": "SAVED_RECORDS_UNUSABLE"})
            continue
        members = bucket_members(projected, epoch(bucket["start_utc"]), epoch(bucket["end_utc"]))
        digest = payload_sha256(members)
        entry.update(saved_count=len(members), saved_sha256=digest)
        if len(members) != bucket["record_count"]:
            results.append({**entry, "result": MISMATCH, "reason": "COUNT_DIFFERS"})
        elif digest != bucket["payload_sha256"]:
            results.append({**entry, "result": MISMATCH, "reason": "PAYLOAD_DIFFERS"})
        else:
            results.append({**entry, "result": PASS, "reason": None})
    return results


def check_saved_export(handoff_bytes: bytes, export: Mapping[str, Any], expected: Mapping[str, Any]) -> dict:
    """Compare a private saved export with the exact recorder handoff bytes. Returns a new report; mutates nothing."""
    _require_expected(expected)
    handoff = strict_json(handoff_bytes, "HANDOFF_NOT_STRICT_JSON")
    if not isinstance(handoff, Mapping):
        raise PayloadError("HANDOFF_NOT_OBJECT")
    report = _Report()
    handoff_sha = hashlib.sha256(handoff_bytes).hexdigest()
    report.same("HANDOFF_SHA256", handoff_sha, expected.get("handoff_sha256"))
    report.same("HANDOFF_SCHEMA", handoff.get("schema_version"), HANDOFF_SCHEMA)
    report.same("CANONICALIZATION", handoff.get("canonicalization_version"), CANONICALIZATION_VERSION)
    content = export.get("content") if isinstance(export, Mapping) else None
    raw = export.get("raw_records") if isinstance(export, Mapping) else None
    if not isinstance(content, Mapping) or not isinstance(raw, list):
        report.add("EXPORT_SHAPE", INCOMPLETE, "CONTENT_OR_RAW_MISSING")
        projected = None
    else:
        content_ok = report.same("CONTENT_SHA256", sha256_hex(content), export.get("content_sha256"))
        raw_ok = report.same("RAW_SHA256", raw_sha256(raw), _get(content, "raw_evidence", "sha256"))
        report.same("RAW_COUNT", len(raw), _get(content, "raw_evidence", "record_count"))
        _check_identity(report, handoff, export, expected)
        projected = _project_saved(report, handoff, raw) if content_ok and raw_ok else None
    buckets = _check_buckets(handoff, _get(content, "buckets"), projected)
    overall = _overall([check["result"] for check in report.checks] + [bucket["result"] for bucket in buckets])
    return {
        "schema_version": REPORT_SCHEMA, "canonicalization_version": CANONICALIZATION_VERSION,
        "dataset_id": _get(export, "dataset_id"), "owner_id": _get(export, "owner_id"),
        "content_sha256": _get(export, "content_sha256"),
        "raw_sha256": raw_sha256(raw) if isinstance(raw, list) else None,
        "handoff_sha256": handoff_sha, "release": expected.get("release"), "overall": overall,
        "global_checks": report.checks, "buckets": buckets,
        "claim_limit": ("Payload binding only. Not owner authentication, database provenance, source rights, P07 "
                        "qualification, market adoption, replay authority or execution timing."),
    }


# Thin offline CLI


def read_bounded(path: Path, limit: int) -> bytes:
    """Read at most ``limit`` bytes from a regular, non-symlink file; refuse larger files before decoding."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise PayloadError("INPUT_NOT_REGULAR_FILE")
        body = handle.read(limit + 1)
    if len(body) > limit:
        raise PayloadError("INPUT_TOO_LARGE", path.name)
    return body


def write_exclusive(path: Path, body: bytes) -> None:
    """Create a new 0600 file; never follow a symlink or replace an existing file."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bind a saved history export to a forward recorder handoff.")
    for name in ("--handoff", "--export", "--expected", "--out"):
        parser.add_argument(name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        handoff_bytes = read_bounded(args.handoff, MAX_HANDOFF_BYTES)
        export = strict_json(read_bounded(args.export, MAX_EXPORT_BYTES), "EXPORT_NOT_STRICT_JSON")
        expected = strict_json(read_bounded(args.expected, MAX_EXPECTED_BYTES), "EXPECTED_NOT_STRICT_JSON")
        if not isinstance(export, Mapping) or not isinstance(expected, Mapping):
            raise PayloadError("INPUT_NOT_OBJECT")
        report = check_saved_export(handoff_bytes, export, expected)
        body = canonical_bytes(report)
        write_exclusive(args.out, body)
    except PayloadError as error:
        print(json.dumps({"status": "REFUSED", "code": error.code}))
        return 2
    except OSError as error:
        print(json.dumps({"status": "REFUSED", "code": "FILE_ERROR", "errno": error.errno}))
        return 2
    print(json.dumps({"status": report["overall"], "report_sha256": hashlib.sha256(body).hexdigest()}))
    return 0 if report["overall"] == PASS else 1


if __name__ == "__main__":
    sys.exit(main())
