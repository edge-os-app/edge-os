"""ACTUAL /2 artifact validation and saved-payload comparison. Pure, with no provider or credential access.

The old projection stays pinned and unchanged. This module validates the complete H/R/P graph before using that
projection. Construction receipts prove neither provider authentication nor source rights.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# Load the historical projection from the exact accepted bytes, including when the API image has no scripts package.
_PROJECTION_PATH = Path(__file__).with_name("history_payload_binding.py")
_PROJECTION_SHA256 = "1c74d8c9bce020e35bb372dd4a363641f1ed35566263163a9dd18807264fd667"
_projection_body = _PROJECTION_PATH.read_bytes()
if hashlib.sha256(_projection_body).hexdigest() != _PROJECTION_SHA256:
    raise ValueError("PROJECTION_CHANGED")
_spec = importlib.util.spec_from_file_location("edge_os_history_projection_v1", _PROJECTION_PATH)
_projection = importlib.util.module_from_spec(_spec)
exec(compile(_projection_body, str(_PROJECTION_PATH), "exec", dont_inherit=True), _projection.__dict__)

PayloadError = _projection.PayloadError
strict_json = _projection.strict_json
canonical_bytes = _projection.canonical_bytes
CANONICALIZATION_VERSION = "edge-os.forward-history-payload/1"
HANDOFF_SCHEMA = "edge-os.forward-history-handoff/2"
REPORT_SCHEMA = "edge-os.history-payload-binding/2"
ANCHOR_SCHEMA = "edge-os.forward-history-binding/2"
PROVENANCE_SCHEMA = "edge-os.forward-history-provenance/1"
RECEIPTS_SCHEMA = "edge-os.forward-history-transport-receipts/1"
MAX_HANDOFF_BYTES = _projection.MAX_HANDOFF_BYTES
MAX_EXPORT_BYTES = _projection.MAX_EXPORT_BYTES
MAX_EXPECTED_BYTES = _projection.MAX_EXPECTED_BYTES
MAX_PROVENANCE_BYTES = 2 * 1024 * 1024
MAX_RECEIPTS_BYTES = 1024 * 1024
TRUSTED_DEPENDENCIES = {'scripts/history_payload_binding.py': '1c74d8c9bce020e35bb372dd4a363641f1ed35566263163a9dd18807264fd667',
 'apps/api/src/edge_os_api/records/contract_adapter.py': '092a87ea75384138e4663aea1d48249d9e7a8cc92a23b1d493887bae560e1b0e',
 'apps/api/src/edge_os_api/research_history/qualification_engine.py': '6cd74eefaee6a01ba81bdc7641cdf47e3cfa6edcce1cb98fec1e8ee70fc2b782',
 'docs/contracts/p02/check_contract.py': '06f3820a2ccfcf1445aef8240e5808977f8adc708ab32aecfedf28ef323d8f79',
 'docs/contracts/p02/contract.json': '1ce8a41cc6d6a097f73cf1fbd24cd8fc4d99c685c52ebf25437427a1a7948768',
 'docs/contracts/p02/fixtures/complete-strategy.json': '9ff3ab72c10616aacd37d2381a9a10500789fdbe671f2adb8314ed6a54479771',
 'docs/qualification/p07/qualification.py': '2de443a231d2b5f96090d94d6480386b42bbef6f5e1e1920b0e7903678d84ce7',
 'apps/api/src/edge_os_api/research_history/http_clients/http_transport.py': '89aa0a18442fb1a28a51d31a9a06da2da9fee4f3e2731239e34a00d44c725f0d'}
TRANSPORT = {"construction": "OWNED_STDLIB",
             "implementation": "edge_os_api.research_history.http_clients.http_transport.StdlibHttpTransport",
             "implementation_sha256": "89aa0a18442fb1a28a51d31a9a06da2da9fee4f3e2731239e34a00d44c725f0d"}
ANCHOR_KEYS = {"schema_version", "handoff_json", "handoff_sha256", "receipts_sha256", "provenance_json",
               "provenance_sha256"}
HANDOFF_KEYS = {"schema_version", "canonicalization_version", "input_schema", "predecessor_sha256", "input_sha256",
                "recorder_code_sha256", "decoder", "attempt_id", "source_id", "evidence_class",
                "requested_evidence_class", "evidence_notice", "status", "stop_reason", "network", "market",
                "window", "query", "boundaries", "scan", "scan_log_count", "chain_cursor", "weaker_evidence",
                "headers", "phases", "p3_replies", "facts", "clock", "accounting", "calls", "buckets",
                "delivery_records", "release_frozen", "claim_limit", "transport"}
PROVENANCE_KEYS = {"schema_version", "attempt_id", "handoff_sha256", "receipts_sha256", "recorder_code_sha256",
                   "transport", "receipts_json"}
RECEIPTS_KEYS = {"schema_version", "attempt_id", "handoff_sha256", "recorder_code_sha256", "evidence_class",
                 "transport", "receipts"}
CALL_KEYS = {"call_id", "phase", "slot", "provider", "request_sha256", "request_bytes", "outcome", "status",
             "body_sha256", "body_bytes"}
RECEIPT_KEYS = {"call_id", "transport_binding_sha256", "request_sha256", "outcome", "status", "body_sha256",
                "body_bytes", "received_at_utc_us", "elapsed_us"}
BUCKET_KEYS = {"index", "start_utc", "end_utc", "status", "reply_id", "received_at_utc", "received_at_utc_us",
               "record_count", "payload_sha256", "reply_body_sha256", "reason"}
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise PayloadError(code)


def _keys(value: Any, keys: set[str], code: str) -> None:
    _require(isinstance(value, Mapping) and set(value) == keys, code)


def _integer(value: Any, maximum: int = 2**256 - 1) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 256


def _time(value: Any) -> int:
    _require(isinstance(value, str), "UTC_INVALID")
    try:
        result = _projection.epoch(value)
        _require(_projection.iso_utc(result) == value, "UTC_INVALID")
        return result
    except (ValueError, TypeError, OverflowError):
        raise PayloadError("UTC_INVALID") from None


def _handoff_shape(h: Mapping[str, Any]) -> None:
    _require(isinstance(h, Mapping), "HANDOFF_NOT_OBJECT")
    _require(h.get("schema_version") == HANDOFF_SCHEMA, "forward_history_binding_not_admitted")
    _keys(h, HANDOFF_KEYS, "HANDOFF_KEYS")
    _require(h["evidence_class"] == h["requested_evidence_class"] == "ACTUAL", "ACTUAL_REQUIRED")
    _require(h["canonicalization_version"] == CANONICALIZATION_VERSION, "CANONICALIZATION_INVALID")
    _require(h["input_schema"] == "edge-os.forward-history-input/1" and h["decoder"] == "retained-v2-pair-created/1",
             "HANDOFF_VERSION_INVALID")
    for field in ("predecessor_sha256", "input_sha256", "recorder_code_sha256"):
        _require(_digest(h[field]), "HANDOFF_DIGEST_INVALID")
    for field in ("attempt_id", "source_id", "status", "evidence_notice", "claim_limit"):
        _require(_text(h[field]), "HANDOFF_TEXT_INVALID")
    _require(h["stop_reason"] is None or _text(h["stop_reason"]), "STOP_REASON_INVALID")
    _keys(h["network"], {"chain_id"}, "NETWORK_KEYS")
    _require(h["network"]["chain_id"] == 143 and type(h["network"]["chain_id"]) is int, "CHAIN_INVALID")
    _keys(h["market"], {"pool", "token0", "token1", "base", "quote"}, "MARKET_KEYS")
    m = h["market"]
    for field, value in m.items():
        _require(_projection.hex_value(value, 20, field) == value, "MARKET_INVALID")
    _require(len({m["pool"], m["token0"], m["token1"]}) == 3 and m["base"] != m["quote"]
             and {m["base"], m["quote"]} == {m["token0"], m["token1"]}, "MARKET_INVALID")
    _keys(h["window"], {"start_utc", "end_utc", "bucket_seconds"}, "WINDOW_KEYS")
    start, end = (_time(h["window"][field]) for field in ("start_utc", "end_utc"))
    _require(start % 300 == 0 and end - start == 1200 and type(h["window"]["bucket_seconds"]) is int
             and h["window"]["bucket_seconds"] == 300, "WINDOW_INVALID")
    _keys(h["boundaries"], {"B_ANCHOR", "B_PRE", "B_START", "B_END", "B_POST"}, "BOUNDARY_KEYS")
    _require(all(value is None or _integer(value) for value in h["boundaries"].values()), "BOUNDARIES_INVALID")
    if h["scan"] is not None:
        _keys(h["scan"], {"from_block", "to_block_exclusive"}, "SCAN_KEYS")
        _require(all(_integer(value) for value in h["scan"].values())
                 and h["scan"]["from_block"] < h["scan"]["to_block_exclusive"], "SCAN_INVALID")
        _require(h["scan"]["from_block"] == h["boundaries"]["B_PRE"] and h["boundaries"]["B_POST"] is not None
                 and h["scan"]["to_block_exclusive"] == h["boundaries"]["B_POST"] + 1, "SCAN_BOUNDARIES_DIFFER")
    _require(h["scan_log_count"] is None or _integer(h["scan_log_count"]), "SCAN_COUNT_INVALID")
    _require(h["chain_cursor"] is None or _integer(h["chain_cursor"]), "CURSOR_INVALID")
    _require(type(h["release_frozen"]) is bool and h["release_frozen"] is False, "RELEASE_FROZEN_INVALID")
    _keys(h["clock"], {"trusted"}, "CLOCK_KEYS")
    _require(type(h["clock"]["trusted"]) is bool, "CLOCK_INVALID")
    for name in ("phases", "facts", "query", "delivery_records"):
        _require(isinstance(h[name], Mapping), "HANDOFF_OBJECT_INVALID")
    for name in ("headers", "calls", "buckets", "p3_replies", "weaker_evidence"):
        _require(isinstance(h[name], list), "HANDOFF_LIST_INVALID")
    fact_keys = {"bytecode", "fee_transfer_semantics", "decimals", "finality_at_collection", "archive_height",
                 "finalized", "latest", "pair_count", "creation_block_timestamp"}
    _require(fact_keys <= set(h["facts"]) <= fact_keys | {"pool_tokens_at_start", "archive_height_declarable"}, "FACTS_KEYS")
    _keys(h["query"], {"address", "topic0", "include_all_blocks", "max_num_blocks", "field_selection"}, "QUERY_KEYS")
    _require(h["query"]["address"] == m["pool"] and h["query"]["include_all_blocks"] is True
             and h["query"]["max_num_blocks"] == 10000, "QUERY_INVALID")
    _projection.hex_value(h["query"]["topic0"], 32, "topic0")
    _keys(h["query"]["field_selection"], {"block", "log"}, "QUERY_FIELDS")
    _keys(h["accounting"], {"admitted", "resolved", "unknown_liability", "reply_bytes", "ceilings"}, "ACCOUNTING_KEYS")
    _require(h["accounting"]["ceilings"] == {"quicknode": 17, "hypersync": 9}, "ACCOUNTING_CEILINGS")
    for header in h["headers"]:
        _keys(header, {"number", "timestamp", "hash"}, "HEADER_KEYS")
        _require(_integer(header["number"]) and _integer(header["timestamp"]), "HEADER_INVALID")
        _projection.hex_value(header["hash"], 32, "hash")
    _require(len({head["number"] for head in h["headers"]}) == len(h["headers"]), "DUPLICATE_HEADER")
    _require(len(h["buckets"]) == 4, "BUCKET_SET_INVALID")
    for index, bucket in enumerate(h["buckets"]):
        _keys(bucket, BUCKET_KEYS, "BUCKET_KEYS")
        _require(type(bucket["index"]) is int and bucket["index"] == index
                 and _time(bucket["start_utc"]) == start + index * 300
                 and _time(bucket["end_utc"]) == start + (index + 1) * 300, "BUCKET_INTERVAL_INVALID")
        _require(_text(bucket["status"]), "BUCKET_STATUS_INVALID")
        if bucket["status"] == "DELIVERED":
            _require(_integer(bucket["record_count"]) and _digest(bucket["payload_sha256"])
                     and _digest(bucket["reply_body_sha256"]) and _text(bucket["reply_id"])
                     and _integer(bucket["received_at_utc_us"]), "BUCKET_DELIVERY_INVALID")
            _require(_time(bucket["received_at_utc"]) == (bucket["received_at_utc_us"] + 999999) // 1_000_000,
                     "BUCKET_TIME_DIFFERS")


def _details_shape(h: Mapping[str, Any]) -> None:
    """Recorder-specific nested schemas. Optional fields describe honest partial attempts, never default facts."""
    q = h["query"]
    _require(q["topic0"] == "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
             and q["field_selection"] == {
                 "block": ["number", "timestamp", "hash"],
                 "log": ["address", "topic0", "topic1", "topic2", "topic3", "data", "block_number", "block_hash",
                         "transaction_hash", "transaction_index", "log_index", "removed"]}, "QUERY_FIELDS")
    facts = h["facts"]
    _require(isinstance(facts["bytecode"], Mapping) and set(facts["bytecode"]) <= {"pool", "token0", "token1"},
             "BYTECODE_KEYS")
    for value in facts["bytecode"].values():
        if value is not None:
            _keys(value, {"bytes", "sha256"}, "BYTECODE_KEYS")
            _require(_integer(value["bytes"], 2097152) and _digest(value["sha256"]), "BYTECODE_INVALID")
    _keys(facts["decimals"], {"window_start", "window_end", "current"}, "DECIMALS_KEYS")
    for stage in facts["decimals"].values():
        _require(isinstance(stage, Mapping) and set(stage) <= {"token0", "token1"}, "DECIMALS_KEYS")
        _require(all(_integer(value, 77) or _text(value) for value in stage.values()), "DECIMALS_INVALID")
    for name in ("pair_count", "creation_block_timestamp", "archive_height"):
        _require(facts[name] is None or _integer(facts[name]), "FACT_NUMBER_INVALID")
    for name in ("fee_transfer_semantics", "finality_at_collection"):
        _require(_text(facts[name]), "FACT_TEXT_INVALID")
    for name in ("finalized", "latest"):
        value = facts[name]
        if value is not None and not isinstance(value, str):
            _keys(value, {"number", "timestamp", "observed_utc_us"}, "FINALITY_KEYS")
            _require(all(_integer(item) for item in value.values()), "FINALITY_INVALID")
        elif value is not None:
            _require(_text(value), "FINALITY_INVALID")
    if "pool_tokens_at_start" in facts:
        _keys(facts["pool_tokens_at_start"], {"token0", "token1"}, "POOL_TOKENS_KEYS")
        _require(all(_text(value) for value in facts["pool_tokens_at_start"].values()), "POOL_TOKENS_INVALID")
    if "archive_height_declarable" in facts:
        _require(type(facts["archive_height_declarable"]) is bool, "ARCHIVE_DECLARABLE_INVALID")
    _require(set(h["phases"]) <= {"P1", "P2", "P3", "P4", "P5"}, "PHASES_KEYS")
    for name, phase in h["phases"].items():
        keys = {"outcome", "reads"} if name == "P3" else {"outcome"}
        if name == "P2" and isinstance(phase, Mapping) and phase.get("outcome") == "COMPLETED":
            keys |= {"number", "timestamp", "hash", "observed_utc_us"}
        _keys(phase, keys, "PHASE_KEYS")
        _require(_text(phase["outcome"]), "PHASE_OUTCOME_INVALID")
        if name == "P2" and phase["outcome"] == "COMPLETED":
            _require(all(_integer(phase[key]) for key in ("number", "timestamp", "observed_utc_us")), "PHASE_HEADER_INVALID")
            _projection.hex_value(phase["hash"], 32, "hash")
        if name == "P3":
            _require(isinstance(phase["reads"], list) and len(phase["reads"]) <= 8, "PHASE_READ_INVALID")
            for read in phase["reads"]:
                _keys(read, {"bucket", "read", "outcome"}, "PHASE_READ_KEYS")
                _require(_integer(read["bucket"], 3) and read["read"] in ("first", "second") and _text(read["outcome"]),
                         "PHASE_READ_INVALID")
    _require(len(h["p3_replies"]) <= 8, "P3_REPLY_LIMIT")
    for reply in h["p3_replies"]:
        _keys(reply, {"archive_height", "call_id", "from_block", "log_count", "next_block", "received_utc_us"},
              "P3_REPLY_KEYS")
        _require(_text(reply["call_id"]) and all(_integer(value) for key, value in reply.items() if key != "call_id"),
                 "P3_REPLY_INVALID")
    _require(all(_text(item) for item in h["weaker_evidence"]), "WEAKER_EVIDENCE_INVALID")
    a = h["accounting"]
    _keys(a["admitted"], {"quicknode", "hypersync"}, "ADMITTED_KEYS")
    _require(all(_integer(a["admitted"][provider], limit) for provider, limit in (("quicknode", 17), ("hypersync", 9))),
             "ADMITTED_INVALID")
    _require(all(_integer(a[key], cap) for key, cap in (("resolved", 26), ("unknown_liability", 26),
                                                      ("reply_bytes", 67108864))), "ACCOUNTING_INVALID")


def check_artifacts(handoff_bytes: bytes, provenance_bytes: bytes, expected: Mapping[str, Any]) -> Mapping[str, Any]:
    """Verify exact raw bytes and complete internal links. Never trust outer hashes instead of schema validation."""
    _require(isinstance(handoff_bytes, bytes) and len(handoff_bytes) <= MAX_HANDOFF_BYTES, "HANDOFF_TOO_LARGE")
    _require(isinstance(provenance_bytes, bytes) and len(provenance_bytes) <= MAX_PROVENANCE_BYTES,
             "PROVENANCE_TOO_LARGE")
    root = Path(__file__).resolve().parents[1]
    try:
        for relative, pin in TRUSTED_DEPENDENCIES.items():
            _require(hashlib.sha256((root / relative).read_bytes()).hexdigest() == pin, "CHECKER_DEPENDENCY_CHANGED")
    except OSError:
        raise PayloadError("CHECKER_DEPENDENCY_MISSING") from None
    h = strict_json(handoff_bytes, "HANDOFF_NOT_STRICT_JSON")
    p = strict_json(provenance_bytes, "PROVENANCE_NOT_STRICT_JSON")
    _handoff_shape(h)
    _details_shape(h)
    _keys(p, PROVENANCE_KEYS, "PROVENANCE_KEYS")
    _require(p["schema_version"] == PROVENANCE_SCHEMA, "PROVENANCE_SCHEMA")
    h_sha, p_sha = (hashlib.sha256(body).hexdigest() for body in (handoff_bytes, provenance_bytes))
    _require(h_sha == expected.get("handoff_sha256"), "HANDOFF_SHA256_DIFFERS")
    _require(p_sha == expected.get("provenance_sha256"), "PROVENANCE_SHA256_DIFFERS")
    _require(p["handoff_sha256"] == h_sha, "PROVENANCE_LINK_H")
    _require(isinstance(p["receipts_json"], str), "RECEIPTS_TEXT_INVALID")
    r_bytes = p["receipts_json"].encode("utf-8")
    _require(len(r_bytes) <= MAX_RECEIPTS_BYTES, "RECEIPTS_TOO_LARGE")
    r = strict_json(r_bytes, "RECEIPTS_NOT_STRICT_JSON")
    _keys(r, RECEIPTS_KEYS, "RECEIPTS_KEYS")
    _require(r["schema_version"] == RECEIPTS_SCHEMA and r["evidence_class"] == "ACTUAL", "RECEIPTS_SCHEMA")
    _require(r["handoff_sha256"] == h_sha, "RECEIPTS_LINK_H")
    _require(p["receipts_sha256"] == expected.get("receipts_sha256") == hashlib.sha256(r_bytes).hexdigest(),
             "PROVENANCE_LINK_R")
    _require(r["attempt_id"] == p["attempt_id"] == h["attempt_id"] == expected.get("recorder_attempt_id"),
             "RECORDER_ATTEMPT_DIFFERS")
    _require(r["recorder_code_sha256"] == p["recorder_code_sha256"] == h["recorder_code_sha256"], "RECORDER_DIFFERS")
    for artifact in (h, r, p):
        transport = artifact["transport"]
        _keys(transport, set(TRANSPORT), "TRANSPORT_KEYS")
        _require(transport["construction"] != "LOCAL_FIXTURE", "forward_history_provenance_fixture")
        _require(transport == TRANSPORT, "forward_history_provenance_injected")
    _require(isinstance(r["receipts"], list) and len(r["receipts"]) <= 26 and len(h["calls"]) <= 26,
             "RECEIPTS_INVALID")
    for call in h["calls"]:
        _keys(call, CALL_KEYS, "CALL_KEYS")
        _require(_text(call["call_id"]) and _text(call["slot"]) and _text(call["phase"])
                 and _text(call["provider"]) and _digest(call["request_sha256"])
                 and _integer(call["request_bytes"], 65536), "CALL_INVALID")
    for receipt in r["receipts"]:
        _keys(receipt, RECEIPT_KEYS, "RECEIPT_KEYS")
        _require(_text(receipt["call_id"]), "RECEIPT_ID_INVALID")
    calls, receipts = ({item["call_id"]: item for item in entries} for entries in (h["calls"], r["receipts"]))
    _require(len(calls) == len(h["calls"]) and len(receipts) == len(r["receipts"]) and calls.keys() == receipts.keys(),
             "RECEIPTS_CALL_SET")
    binding_sha = hashlib.sha256(canonical_bytes(TRANSPORT)).hexdigest()
    for call_id, call in calls.items():
        receipt = receipts[call_id]
        _require(receipt["transport_binding_sha256"] == binding_sha, "RECEIPT_TRANSPORT_DIFFERS")
        _require(all(receipt[key] == call[key] for key in ("request_sha256", "outcome", "status", "body_sha256",
                                                          "body_bytes")), "RECEIPT_CALL_DIFFERS")
        _require(call["outcome"] == "REPLY_RECEIVED" and type(call["status"]) is int
                 and 200 <= call["status"] < 300 and _digest(call["body_sha256"])
                 and _integer(call["body_bytes"], 2097152) and _integer(receipt["received_at_utc_us"])
                 and _integer(receipt["elapsed_us"], 120000000), "RECEIPT_INCOMPLETE")
    counts = Counter(call["provider"] for call in calls.values())
    phases = Counter((call["phase"], call["provider"]) for call in calls.values())
    limits = {("P1", "quicknode"): 6, ("P1", "hypersync"): 1, ("P2", "quicknode"): 1,
              ("P3", "hypersync"): 8, ("P4", "quicknode"): 4, ("P5", "quicknode"): 6}
    _require(all(key in limits and count <= limits[key] for key, count in phases.items()), "CALL_CEILING")
    a = h["accounting"]
    _require(a["admitted"] == dict(counts) and a["resolved"] == len(calls) and a["unknown_liability"] == 0
             and a["reply_bytes"] == sum(call["body_bytes"] for call in calls.values()), "ACCOUNTING_DIFFERS")
    p3 = {}
    for reply in h["p3_replies"]:
        call_id = reply["call_id"]
        receipt, call = receipts.get(call_id), calls.get(call_id)
        _require(call_id not in p3 and receipt is not None and call["phase"] == "P3"
                 and call["provider"] == "hypersync" and reply["received_utc_us"] == receipt["received_at_utc_us"]
                 and reply["from_block"] < reply["next_block"], "P3_RECEIPT_DIFFERS")
        p3[call_id] = reply
    delivered = {}
    for bucket in h["buckets"]:
        if bucket["status"] != "DELIVERED":
            continue
        receipt = receipts.get(bucket["reply_id"])
        call = calls.get(bucket["reply_id"])
        _require(receipt is not None and bucket["reply_id"] in p3
                 and call["phase"] == "P3" and call["provider"] == "hypersync",
                 "BUCKET_RECEIPT_MISSING")
        _require(bucket["reply_body_sha256"] == receipt["body_sha256"]
                 and bucket["received_at_utc_us"] == receipt["received_at_utc_us"], "BUCKET_RECEIPT_DIFFERS")
        delivered[bucket["start_utc"]] = bucket["received_at_utc"]
    _require(delivered == h["delivery_records"], "DELIVERY_RECORDS_DIFFER")
    return h


def check_saved_export(handoff_bytes: bytes, export: Mapping[str, Any], expected: Mapping[str, Any], *,
                       provenance_bytes: bytes) -> dict[str, Any]:
    """Rerun the retained canonical projection on the same persisted owner-scoped raw rows, after graph validation."""
    _projection._require_expected(expected)
    _require(expected["release"]["kind"] == "ACTUAL", "ACTUAL_RELEASE_REQUIRED")
    h = check_artifacts(handoff_bytes, provenance_bytes, expected)
    report = _projection._Report()
    content = export.get("content") if isinstance(export, Mapping) else None
    raw = export.get("raw_records") if isinstance(export, Mapping) else None
    if not isinstance(content, Mapping) or not isinstance(raw, list):
        report.add("EXPORT_SHAPE", "INCOMPLETE", "CONTENT_OR_RAW_MISSING")
        projected = None
    else:
        content_ok = report.same("CONTENT_SHA256", _projection.sha256_hex(content), export.get("content_sha256"))
        raw_ok = report.same("RAW_SHA256", _projection.raw_sha256(raw), _projection._get(content, "raw_evidence", "sha256"))
        report.same("RAW_COUNT", len(raw), _projection._get(content, "raw_evidence", "record_count"))
        _projection._check_identity(report, h, export, expected)
        for key in ("job_id", "attempt_id"):
            report.same(key.upper(), content.get(key), expected.get(key))
        if h["status"] != "COMPLETED" or h["clock"]["trusted"] is not True:
            report.add("ATTEMPT_COMPLETE", "INCOMPLETE", "ATTEMPT_NOT_COMPLETE")
        projected = _projection._project_saved(report, h, raw) if content_ok and raw_ok else None
    buckets = _projection._check_buckets(h, _projection._get(content, "buckets"), projected)
    overall = _projection._overall([item["result"] for item in report.checks] + [item["result"] for item in buckets])
    return {"schema_version": REPORT_SCHEMA, "canonicalization_version": CANONICALIZATION_VERSION,
            "dataset_id": _projection._get(export, "dataset_id"), "owner_id": _projection._get(export, "owner_id"),
            "content_sha256": _projection._get(export, "content_sha256"),
            "raw_sha256": _projection.raw_sha256(raw) if isinstance(raw, list) else None,
            **{key: expected[key] for key in ("handoff_sha256", "receipts_sha256", "provenance_sha256")},
            "release": expected["release"], "overall": overall, "global_checks": report.checks, "buckets": buckets,
            "claim_limit": "Payload and construction binding only; not provider authentication, rights or qualification."}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ACTUAL /2 artifacts against a saved history export.")
    for name in ("--handoff", "--provenance", "--export", "--expected", "--out"):
        parser.add_argument(name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = check_saved_export(_projection.read_bounded(args.handoff, MAX_HANDOFF_BYTES),
            strict_json(_projection.read_bounded(args.export, MAX_EXPORT_BYTES), "EXPORT_NOT_STRICT_JSON"),
            strict_json(_projection.read_bounded(args.expected, MAX_EXPECTED_BYTES), "EXPECTED_NOT_STRICT_JSON"),
            provenance_bytes=_projection.read_bounded(args.provenance, MAX_PROVENANCE_BYTES))
        body = canonical_bytes(report)
        _projection.write_exclusive(args.out, body)
    except PayloadError as error:
        print(json.dumps({"status": "REFUSED", "code": error.code}))
        return 2
    except OSError as error:
        print(json.dumps({"status": "REFUSED", "code": "FILE_ERROR", "errno": error.errno}))
        return 2
    print(json.dumps({"status": report["overall"], "report_sha256": hashlib.sha256(body).hexdigest()}))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
