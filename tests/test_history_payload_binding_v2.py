"""Complete synthetic recorder graphs. No fixture is evidence of provider authentication."""
from __future__ import annotations

import copy
import hashlib
import http.client
import importlib
import json
import shutil
import time
import uuid
from pathlib import Path

import pytest

from edge_os_api.records.contract_adapter import canonical_bytes, sha256_hex
from edge_os_api.research_history.qualification_engine import raw_sha256
from scripts import forward_history_recorder as recorder
from tests.test_forward_history_provenance import actual_run
from tests.test_forward_history_recorder import (
    Credentials,
    FakeClock,
    SyntheticProviders,
    T0,
    block_hash,
    block_ts,
    recorder_input,
)
from tests.test_forward_history_transport_receipts import FixtureConnection


def digest(body):
    return hashlib.sha256(body).hexdigest()


def graph(tmp_path, monkeypatch):
    _, providers, _, directory = actual_run(tmp_path, monkeypatch)
    h, r, p = [directory.joinpath(name).read_bytes() for name in (
        "handoff.json", "transport-receipts.json", "provenance.json")]
    anchor = {"schema_version": "edge-os.forward-history-binding/2", "handoff_json": h.decode(),
              "handoff_sha256": digest(h), "receipts_sha256": digest(r), "provenance_json": p.decode(),
              "provenance_sha256": digest(p)}
    handoff = json.loads(h)
    raw = [dict(item, block_hash=block_hash(item["block_number"]), block_timestamp=block_ts(item["block_number"]))
           for item in providers.swaps]
    owner, dataset, job, attempt = (str(uuid.UUID(int=n)) for n in (1, 2, 3, 4))
    release = {"release_id": "synthetic-actual/2", "sha256": "a" * 64, "kind": "ACTUAL"}
    expected = {"owner_id": owner, "dataset_id": dataset, "source_id": handoff["source_id"], "release": release,
                "handoff_sha256": digest(h), "receipts_sha256": digest(r), "provenance_sha256": digest(p),
                "recorder_attempt_id": handoff["attempt_id"], "job_id": job, "attempt_id": attempt}
    content = {"dataset_id": dataset, "owner_id": owner, "job_id": job, "attempt_id": attempt,
               "source_id": handoff["source_id"], "operating_release": release, "evidence_class": "PROVIDER_ACTUAL",
               "network": {"chain_id": 143}, "binding_view": {
                   "pool_address": handoff["market"]["pool"], "base_asset": handoff["market"]["base"],
                   "quote_asset": handoff["market"]["quote"],
                   "token_order": [handoff["market"]["base"], handoff["market"]["quote"]]},
               "window_start": handoff["window"]["start_utc"], "window_end": handoff["window"]["end_utc"],
               "query": {**handoff["scan"], "address": handoff["market"]["pool"]},
               "buckets": [{"bucket_start": b["start_utc"], "bucket_end": b["end_utc"],
                            "available_at": b["received_at_utc"]} for b in handoff["buckets"]],
               "raw_evidence": {"sha256": raw_sha256(raw), "record_count": len(raw)}}
    export = {"dataset_id": dataset, "owner_id": owner, "content": content, "content_sha256": sha256_hex(content),
              "raw_records": raw}
    return anchor, export, expected


def module():
    path = Path(__file__).resolve().parents[1] / "scripts/history_payload_binding_v2.py"
    assert path.exists(), "the versioned checker is missing"
    return importlib.import_module("scripts.history_payload_binding_v2")


def check(anchor, export, expected):
    return module().check_saved_export(anchor["handoff_json"].encode(), export, expected,
                                       provenance_bytes=anchor["provenance_json"].encode())


def reanchor(anchor, expected, *, handoff=None, receipts=None, provenance=None):
    anchor, expected = copy.deepcopy(anchor), copy.deepcopy(expected)
    p = json.loads(anchor["provenance_json"]) if provenance is None else provenance
    if handoff is not None:
        anchor["handoff_json"] = canonical_bytes(handoff).decode()
        p["handoff_sha256"] = digest(anchor["handoff_json"].encode())
        if receipts is None:
            receipts = json.loads(p["receipts_json"])
        receipts["handoff_sha256"] = p["handoff_sha256"]
    if receipts is not None:
        r = canonical_bytes(receipts)
        p["receipts_json"] = r.decode()
        anchor["receipts_sha256"] = p["receipts_sha256"] = digest(r)
    anchor["provenance_json"] = canonical_bytes(p).decode()
    anchor["provenance_sha256"] = digest(anchor["provenance_json"].encode())
    anchor["handoff_sha256"] = digest(anchor["handoff_json"].encode())
    expected.update({key: anchor[key] for key in ("handoff_sha256", "receipts_sha256", "provenance_sha256")})
    return anchor, expected


def two_hour_graph(tmp_path, monkeypatch):
    clock = FakeClock(T0 - 600)
    clock.mono = time.monotonic()
    providers = SyntheticProviders(clock)
    monkeypatch.setattr(http.client, "HTTPSConnection", lambda host, port, timeout: FixtureConnection(
        providers, "https", host, port))
    result = recorder.run_actual_attempt(
        recorder_input(tmp_path, evidence_class="ACTUAL", window_seconds=7200), clock=clock,
        credentials=Credentials())
    assert result["status"] == "COMPLETED"
    directory = tmp_path / "attempts" / "synthetic-attempt-1"
    h, r, p = [directory.joinpath(name).read_bytes() for name in (
        "handoff.json", "transport-receipts.json", "provenance.json")]
    anchor = {"schema_version": "edge-os.forward-history-binding/2", "handoff_json": h.decode(),
              "handoff_sha256": digest(h), "receipts_sha256": digest(r), "provenance_json": p.decode(),
              "provenance_sha256": digest(p)}
    expected = {"handoff_sha256": digest(h), "receipts_sha256": digest(r), "provenance_sha256": digest(p),
                "recorder_attempt_id": json.loads(h)["attempt_id"]}
    return anchor, expected


def test_two_hour_handoff_with_24_buckets_is_admitted(tmp_path, monkeypatch):
    anchor, expected = two_hour_graph(tmp_path, monkeypatch)
    admitted = module().check_artifacts(anchor["handoff_json"].encode(), anchor["provenance_json"].encode(),
                                        expected)
    assert len(admitted["buckets"]) == 24
    assert admitted["accounting"]["ceilings"] == {"quicknode": 17, "hypersync": 49}


def test_four_bucket_handoff_still_admits_with_the_original_ceilings(tmp_path, monkeypatch):
    anchor, _, expected = graph(tmp_path, monkeypatch)
    admitted = module().check_artifacts(anchor["handoff_json"].encode(), anchor["provenance_json"].encode(),
                                        expected)
    assert len(admitted["buckets"]) == 4
    assert admitted["accounting"]["ceilings"] == {"quicknode": 17, "hypersync": 9}


def test_two_hour_handoff_with_another_bucket_count_is_refused(tmp_path, monkeypatch):
    anchor, expected = two_hour_graph(tmp_path, monkeypatch)
    handoff = json.loads(anchor["handoff_json"])
    handoff["buckets"] = handoff["buckets"][:-1]
    anchor, expected = reanchor(anchor, expected, handoff=handoff)
    with pytest.raises(module().PayloadError, match="BUCKET_SET_INVALID"):
        module().check_artifacts(anchor["handoff_json"].encode(), anchor["provenance_json"].encode(), expected)


def test_app_checker_refuses_a_v2_file_with_any_other_bytes(tmp_path, monkeypatch):
    from edge_os_api.research import history_payload_binding as binding
    snapshot = tmp_path / "repo"
    for name in [binding.CHECKER_RELATIVE_PATH_V2, *binding.CHECKER_DEPENDENCIES_V2]:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(binding.REPO_ROOT / name, target)
    monkeypatch.setattr(binding, "REPO_ROOT", snapshot)
    binding.checker.cache_clear()
    try:
        assert binding.checker(2)
        checker_file = snapshot / binding.CHECKER_RELATIVE_PATH_V2
        checker_file.write_bytes(checker_file.read_bytes() + b"\n# changed\n")
        with pytest.raises(binding.CheckerUnavailable, match="CHECKER_CHANGED"):
            binding.checker(2)
    finally:
        binding.checker.cache_clear()


def test_complete_actual_graph_binds_exact_saved_payload(tmp_path, monkeypatch):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    report = check(anchor, export, expected)
    assert report["schema_version"] == "edge-os.history-payload-binding/2"
    assert report["overall"] == "PASS"
    assert [b["result"] for b in report["buckets"]] == ["PASS"] * 4
    assert check(anchor, export, expected) == report


@pytest.mark.parametrize("link", ["handoff_sha256", "receipts_sha256"])
def test_rehashed_provenance_with_missing_internal_link_is_refused(tmp_path, monkeypatch, link):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    p = json.loads(anchor["provenance_json"])
    del p[link]
    anchor, expected = reanchor(anchor, expected, provenance=p)
    with pytest.raises(module().PayloadError, match="PROVENANCE_KEYS"):
        check(anchor, export, expected)


@pytest.mark.parametrize("change,code", [("missing-link", "RECEIPTS_KEYS"),
                                         ("contradictory-link", "RECEIPTS_LINK_H"),
                                         ("missing-receipt", "RECEIPTS_CALL_SET"),
                                         ("substituted-body", "RECEIPT_CALL_DIFFERS")])
def test_rehashed_receipts_still_need_complete_internal_evidence(tmp_path, monkeypatch, change, code):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    r = json.loads(json.loads(anchor["provenance_json"])["receipts_json"])
    if change == "missing-link":
        del r["handoff_sha256"]
    elif change == "contradictory-link":
        r["handoff_sha256"] = "f" * 64
    elif change == "missing-receipt":
        r["receipts"].pop()
    else:
        r["receipts"][0]["body_sha256"] = "f" * 64
    anchor, expected = reanchor(anchor, expected, receipts=r)
    with pytest.raises(module().PayloadError, match=code):
        check(anchor, export, expected)


def test_rehashed_saved_amount_change_is_still_mismatch(tmp_path, monkeypatch):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    export["raw_records"][0]["data"] = "0x" + "00" * 128
    export["content"]["raw_evidence"]["sha256"] = raw_sha256(export["raw_records"])
    export["content_sha256"] = sha256_hex(export["content"])
    assert check(anchor, export, expected)["overall"] == "MISMATCH"


@pytest.mark.parametrize("path,value,code", [
    (("query", "field_selection", "block"), [], "QUERY_FIELDS"),
    (("facts", "decimals", "current"), {"token0": -1, "token1": 18}, "DECIMALS_INVALID"),
    (("facts", "bytecode", "pool"), {"bytes": 5, "sha256": "bad"}, "BYTECODE_INVALID"),
    (("phases", "P3", "reads"), [{"bucket": 0, "read": "first", "outcome": []}], "PHASE_READ_INVALID"),
    (("p3_replies",), [{"call_id": "unbound"}], "P3_REPLY_KEYS"),
    (("calls",), [{"call_id": "x", "phase": [], "slot": "x", "provider": [], "request_sha256": "a" * 64,
                     "request_bytes": 1, "outcome": "UNKNOWN", "status": None, "body_sha256": None, "body_bytes": None}], "CALL_INVALID"),
])
def test_malformed_complete_schema_fields_are_refused(tmp_path, monkeypatch, path, value, code):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    h = json.loads(anchor["handoff_json"])
    target = h
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    anchor, expected = reanchor(anchor, expected, handoff=h)
    with pytest.raises(module().PayloadError, match=code):
        check(anchor, export, expected)


def test_missing_saved_raw_timestamp_remains_incomplete(tmp_path, monkeypatch):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    del export["raw_records"][0]["block_timestamp"]
    export["content"]["raw_evidence"]["sha256"] = raw_sha256(export["raw_records"])
    export["content_sha256"] = sha256_hex(export["content"])
    assert check(anchor, export, expected)["overall"] == "INCOMPLETE"


def test_reanchored_p3_reference_must_name_its_actual_receipt(tmp_path, monkeypatch):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    h = json.loads(anchor["handoff_json"])
    h["p3_replies"][0]["call_id"] = "substituted"
    anchor, expected = reanchor(anchor, expected, handoff=h)
    with pytest.raises(module().PayloadError, match="P3_RECEIPT_DIFFERS"):
        check(anchor, export, expected)


def test_legacy_handoff_is_explicitly_refused_for_actual(tmp_path, monkeypatch):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    h = json.loads(anchor["handoff_json"])
    h["schema_version"] = "edge-os.forward-history-handoff/1"
    anchor, expected = reanchor(anchor, expected, handoff=h)
    with pytest.raises(module().PayloadError, match="forward_history_binding_not_admitted"):
        check(anchor, export, expected)


@pytest.mark.parametrize("field,value,check_name", [
    ("owner_id", str(uuid.UUID(int=99)), "INNER_OWNER_ID"),
    ("source_id", "other-source", "SOURCE_ID"),
    ("attempt_id", str(uuid.UUID(int=99)), "ATTEMPT_ID"),
    ("job_id", str(uuid.UUID(int=99)), "JOB_ID"),
    ("window_start", "2027-01-15T08:05:00Z", "WINDOW_START"),
    ("operating_release", {"release_id": "wrong", "sha256": "b" * 64, "kind": "ACTUAL"}, "RELEASE_RELEASE_ID"),
    ("binding_view", {"pool_address": "0x" + "aa" * 20, "base_asset": "0x" + "44" * 20,
                      "quote_asset": "0x" + "33" * 20, "token_order": ["0x" + "44" * 20, "0x" + "33" * 20]}, "POOL"),
    ("evidence_class", "RELEASE_STAND_IN_RESPONSE", "EVIDENCE_CLASS"),
])
def test_actual_saved_identity_mutations_are_mismatch(tmp_path, monkeypatch, field, value, check_name):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    export["content"][field] = value
    export["content_sha256"] = sha256_hex(export["content"])
    report = check(anchor, export, expected)
    assert report["overall"] == "MISMATCH"
    assert {"check": check_name, "result": "MISMATCH", "reason": "VALUE_DIFFERS"} in report["global_checks"]


@pytest.mark.parametrize("artifact", ["handoff_json", "provenance_json"])
def test_single_byte_raw_artifact_mutation_is_refused(tmp_path, monkeypatch, artifact):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    anchor[artifact] += " "
    with pytest.raises(module().PayloadError, match="SHA256_DIFFERS"):
        check(anchor, export, expected)


def test_duplicate_json_keys_are_refused_before_comparison(tmp_path, monkeypatch):
    anchor, export, expected = graph(tmp_path, monkeypatch)
    anchor["handoff_json"] = anchor["handoff_json"].replace('{', '{"schema_version":"duplicate",', 1)
    with pytest.raises(module().PayloadError, match="HANDOFF_NOT_STRICT_JSON"):
        check(anchor, export, expected)
