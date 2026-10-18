"""Pure admission and saved evaluation of synthetic /2 artifacts. No DB, socket or provider."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

import forward_history_stand_in as stand_in
from edge_os_api.core.research.operating_release import BINDING_FACT, ReleaseRefused, _check_history
from edge_os_api.records.contract_adapter import sha256_hex
from edge_os_api.research import history_payload_binding as binding
from tests.test_history_payload_binding_v2 import graph, reanchor


def history_for(anchor):
    h = json.loads(anchor["handoff_json"])
    base = stand_in.bound_release(nansen=False).history
    profile = copy.deepcopy(base.profile)
    profile["dataset"]["window"] = {key: h["window"][key] for key in ("start_utc", "end_utc")}
    profile["network"]["chain_id"] = h["network"]["chain_id"]
    profile["venue"]["pool_address"] = h["market"]["pool"]
    for token in profile["pool_tokens"]:
        token["address"] = h["market"][token["role"].lower()]
    return replace(base, source_id=h["source_id"], envio_endpoint="https://hypersync.example.com",
                   quicknode_host="quicknode.example.com", profile=profile, scan=h["scan"],
                   provider_facts={**base.provider_facts, BINDING_FACT: anchor})


def saved_actual(tmp_path, monkeypatch):
    anchor, export, _ = graph(tmp_path, monkeypatch)
    req = binding.requirement(anchor)
    content = export["content"]
    content[binding.REQUIREMENT_KEY] = req
    row = SimpleNamespace(dataset_id=uuid.UUID(export["dataset_id"]), owner_id=uuid.UUID(export["owner_id"]),
                          content=content, raw_records=export["raw_records"], content_sha256=sha256_hex(content))
    started = {"operating_release": content["operating_release"], "input": {"source_id": content["source_id"]},
               binding.REQUIREMENT_KEY: req}
    expected = binding._expected(row.owner_id, row.dataset_id, started,
                                 job_id=content["job_id"], attempt_id=content["attempt_id"])
    report, result, reason = binding.run_checker(anchor["handoff_json"], row, expected,
                                                provenance_text=anchor["provenance_json"])
    event = {**anchor, "schema_version": binding.EVENT_VERSION, "dataset_id": str(row.dataset_id),
             "result": result, "reason": reason, "expected": expected, "checker": binding.checker_identity(2),
             "report": report, "report_sha256": sha256_hex(report)}
    return anchor, row, started, event


def evaluate(row, started, event):
    return binding.evaluate(row.content, row.dataset_id, row.owner_id, started, event, row)


def test_actual_admitted_through_operating_release_history_check(tmp_path, monkeypatch):
    anchor, _, _ = graph(tmp_path, monkeypatch)
    _check_history("ACTUAL", history_for(anchor))


@pytest.mark.parametrize("contradiction", ["release-profile", "reanchored-handoff"])
def test_actual_admission_refuses_contradictory_pool_token_order(tmp_path, monkeypatch, contradiction):
    anchor, _, expected = graph(tmp_path, monkeypatch)
    history = history_for(anchor)
    if contradiction == "release-profile":
        profile = copy.deepcopy(history.profile)
        profile["pool_tokens"].reverse()
        history = replace(history, profile=profile)
    else:
        handoff = json.loads(anchor["handoff_json"])
        handoff["market"]["token0"], handoff["market"]["token1"] = (
            handoff["market"]["token1"], handoff["market"]["token0"])
        anchor, _ = reanchor(anchor, expected, handoff=handoff)
        history = replace(history, provider_facts={**history.provider_facts, BINDING_FACT: anchor})
    handoff = json.loads(anchor["handoff_json"])
    binding.checker(2).check_artifacts(anchor["handoff_json"].encode(), anchor["provenance_json"].encode(),
                                     {**anchor, "recorder_attempt_id": handoff["attempt_id"]})
    with pytest.raises(ReleaseRefused) as caught:
        _check_history("ACTUAL", history)
    assert caught.value.code == "forward_history_binding_invalid"


@pytest.mark.parametrize("reverse_pool", [False, True])
def test_actual_admission_preserves_generic_pool_order_and_base_quote_roles(tmp_path, monkeypatch, reverse_pool):
    from edge_os_api.research_history import qualification_engine as engine

    anchor, _, expected = graph(tmp_path, monkeypatch)
    if reverse_pool:
        handoff = json.loads(anchor["handoff_json"])
        handoff["market"]["token0"], handoff["market"]["token1"] = (
            handoff["market"]["token1"], handoff["market"]["token0"])
        anchor, _ = reanchor(anchor, expected, handoff=handoff)
    history = history_for(anchor)
    if reverse_pool:
        history.profile["pool_tokens"].reverse()
    _check_history("ACTUAL", history)
    market = json.loads(anchor["handoff_json"])["market"]
    assert [token["address"] for token in history.profile["pool_tokens"]] == [market["token0"], market["token1"]]
    assert engine._P07["research_binding_view"](history.profile)["token_order"] == [market["base"], market["quote"]]


@pytest.mark.parametrize("field", ["schema_version", "provenance_sha256", "receipts_sha256"])
def test_incomplete_versioned_anchor_refused(tmp_path, monkeypatch, field):
    anchor, _, _ = graph(tmp_path, monkeypatch)
    del anchor[field]
    with pytest.raises(ReleaseRefused) as caught:
        _check_history("ACTUAL", history_for(anchor))
    assert caught.value.code == "forward_history_binding_invalid"


def test_reanchored_provenance_without_internal_link_is_not_admitted(tmp_path, monkeypatch):
    anchor, _, expected = graph(tmp_path, monkeypatch)
    provenance = json.loads(anchor["provenance_json"])
    del provenance["receipts_sha256"]
    anchor, _ = reanchor(anchor, expected, provenance=provenance)
    with pytest.raises(ReleaseRefused) as caught:
        _check_history("ACTUAL", history_for(anchor))
    assert caught.value.code == "forward_history_binding_invalid"


def test_saved_actual_pass_is_reproduced_from_raw_rows(tmp_path, monkeypatch):
    _, row, started, event = saved_actual(tmp_path, monkeypatch)
    assert event["result"] == "PASS"
    state = evaluate(row, started, event)
    assert state["status"] == "PASS" and state["report_sha256"] == event["report_sha256"]
    assert state["evidence_class"] == "ACTUAL"


def test_actual_saved_refusal_never_refills(tmp_path, monkeypatch):
    _, row, started, event = saved_actual(tmp_path, monkeypatch)
    event.update(result="INCOMPLETE", report=None, report_sha256=None, reason="CHECKER_MISSING")
    assert evaluate(row, started, event)["status"] == "INCOMPLETE"


def test_actual_private_texts_are_removed_recursively_on_event_view(tmp_path, monkeypatch):
    _, row, started, event = saved_actual(tmp_path, monkeypatch)
    event["details"] = [{"provenance_json": "private-provenance", "receipts_json": "private-receipts",
                          "handoff_json": "private-handoff", "raw_records": [{"data": "private-data"}]}]
    view = binding.public_event(binding.EVENT_KIND, event)
    text = json.dumps(view)
    assert "private-" not in text and "receipts_json" not in text and "provenance_json" not in text
    assert view["provenance_bytes"] > 0 and view["report_sha256"] == event["report_sha256"]


def test_legacy_requirement_cannot_execute_actual_with_relabelled_handoff(tmp_path, monkeypatch):
    _, row, started, event = saved_actual(tmp_path, monkeypatch)
    h = json.loads(event["handoff_json"])
    h["schema_version"] = "edge-os.forward-history-handoff/1"
    body = json.dumps(h)
    legacy_expected = {key: value for key, value in event["expected"].items()
                       if key not in {"schema_version", "provenance_sha256", "receipts_sha256", "recorder_attempt_id", "checker"}}
    legacy_expected["handoff_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    result = binding.run_checker(body, row, legacy_expected)
    assert result[1:] == ("INCOMPLETE", "forward_history_binding_not_admitted")


@pytest.mark.parametrize("dependency", ["scripts/history_payload_binding.py",
                                        "apps/api/src/edge_os_api/research_history/qualification_engine.py",
                                        "docs/contracts/p02/check_contract.py"])
def test_cached_actual_checker_rechecks_missing_or_changed_helpers(tmp_path, monkeypatch, dependency):
    import shutil
    anchor, row, started, event = saved_actual(tmp_path, monkeypatch)
    assert evaluate(row, started, event)["status"] == "PASS"
    snapshot = tmp_path / "checker-snapshot"
    for name in [binding.CHECKER_RELATIVE_PATH_V2, *binding.CHECKER_DEPENDENCIES_V2]:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(binding.REPO_ROOT / name, target)
    monkeypatch.setattr(binding, "REPO_ROOT", snapshot)
    changed = snapshot / dependency
    changed.write_bytes(changed.read_bytes() + b"\n# changed\n")
    assert evaluate(row, started, event)["status"] == "INCOMPLETE"
    changed.unlink()
    assert evaluate(row, started, event)["status"] == "INCOMPLETE"


@pytest.mark.parametrize("field", ["provenance_json", "receipts_sha256", "provenance_sha256"])
def test_saved_actual_artifact_mutation_refuses_before_consumer(tmp_path, monkeypatch, field):
    _, row, started, event = saved_actual(tmp_path, monkeypatch)
    event[field] = "{}" if field.endswith("json") else "b" * 64
    assert evaluate(row, started, event)["status"] in {"MISMATCH", "INCOMPLETE"}


def test_saved_legacy_report_cannot_be_used_for_actual(tmp_path, monkeypatch):
    _, row, started, event = saved_actual(tmp_path, monkeypatch)
    event["report"]["schema_version"] = "edge-os.history-payload-binding/1"
    event["report_sha256"] = sha256_hex(event["report"])
    assert evaluate(row, started, event)["status"] != "PASS"


def test_changed_actual_pin_leaves_old_binding_incomplete(tmp_path, monkeypatch):
    _, row, started, event = saved_actual(tmp_path, monkeypatch)
    monkeypatch.setattr(binding, "CHECKER_SHA256_V2", "b" * 64)
    state = evaluate(row, started, event)
    assert state["status"] == "INCOMPLETE" and state["reason"] == "CHECKER_IDENTITY_DIFFERS"


def test_current_registry_is_not_read_to_reinterpret_saved_actual(tmp_path, monkeypatch):
    from edge_os_api.core.research import released_runtime_bootstrap
    _, row, started, event = saved_actual(tmp_path, monkeypatch)
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", {})
    assert evaluate(row, started, event)["status"] == "PASS"


def actual_runtime(anchor, monkeypatch):
    from edge_os_api.core.research import operating_release
    from edge_os_api.core.research.released_source_runtime import open_released_runtime
    from edge_os_api.research_history.http_clients import StdlibHttpTransport
    release = operating_release.OperatingRelease("synthetic-public-actual/2", "ACTUAL", history=history_for(anchor))
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES", {release.release_id: operating_release.release_sha256(release)})

    class NoCredentials:
        def read(self, slot):
            raise AssertionError("public admission must never read credentials")

    return open_released_runtime(SimpleNamespace(env="test"), release, credentials=NoCredentials(),
                                 http_transport=StdlibHttpTransport)


def test_admitted_actual_runtime_public_source_view_reports_actual(tmp_path, monkeypatch):
    from edge_os_api.core.research.released_source_runtime import history_source
    anchor, _, _ = graph(tmp_path, monkeypatch)
    source = history_source(actual_runtime(anchor, monkeypatch))
    assert source["release"]["history"]["payload_binding"] == {
        "handoff_sha256": anchor["handoff_sha256"], "evidence_class": "ACTUAL"}
    # The public catalog is the actual consumer of the private source description.
    from edge_os_api.research.history_dataset import catalog
    shown = catalog(runtime=actual_runtime(anchor, monkeypatch))
    assert anchor["handoff_json"] not in json.dumps(shown) and anchor["provenance_json"] not in json.dumps(shown)


def test_stand_in_and_unbound_public_binding_views_keep_their_shape():
    from edge_os_api.core.research.released_source_runtime import release_view
    runtime, *_ = stand_in.recording_runtime(SimpleNamespace(env="test"), release=stand_in.bound_release(nansen=False))
    assert release_view(runtime)["history"]["payload_binding"] == {
        "handoff_sha256": stand_in.definition()["handoff_sha256"], "evidence_class": "SYNTHETIC"}
    unbound, *_ = stand_in.recording_runtime(SimpleNamespace(env="test"),
                                            release=stand_in.bound_release(nansen=False, binding=None))
    assert "payload_binding" not in release_view(unbound)["history"]


@pytest.mark.parametrize("mutation", ["legacy", "missing-link", "contradiction"])
def test_invalid_public_runtime_never_promotes_actual(tmp_path, monkeypatch, mutation):
    from edge_os_api.core.research.released_source_runtime import release_view
    anchor, _, expected = graph(tmp_path, monkeypatch)
    runtime = actual_runtime(anchor, monkeypatch)
    invalid = copy.deepcopy(anchor)
    if mutation == "legacy":
        invalid = stand_in.definition()
    elif mutation == "missing-link":
        del invalid["receipts_sha256"]
    else:
        p = json.loads(invalid["provenance_json"])
        p["handoff_sha256"] = "b" * 64
        invalid, _ = reanchor(invalid, expected, provenance=p)
    monkeypatch.setitem(runtime.release.history.provider_facts, BINDING_FACT, invalid)
    with pytest.raises(ReleaseRefused):
        release_view(runtime)


def test_actual_without_binding_is_refused_before_runtime_effects(tmp_path, monkeypatch):
    anchor, _, _ = graph(tmp_path, monkeypatch)
    history = history_for(anchor)
    history = replace(history, provider_facts={key: value for key, value in history.provider_facts.items()
                                              if key != BINDING_FACT})
    with pytest.raises(ReleaseRefused, match="forward_history_binding_not_admitted"):
        _check_history("ACTUAL", history)


def test_untrusted_actual_clock_is_refused_at_admission(tmp_path, monkeypatch):
    anchor, _, expected = graph(tmp_path, monkeypatch)
    h = json.loads(anchor["handoff_json"])
    h["clock"]["trusted"] = False
    anchor, _ = reanchor(anchor, expected, handoff=h)
    with pytest.raises(ReleaseRefused, match="forward_history_binding_invalid"):
        _check_history("ACTUAL", history_for(anchor))


def authored_actual_history(history):
    """Side-effect-free AUTHORED TEST /2 graph for composition fixtures. No recorder, slot, socket or process runs.

    These literals describe the wire shape only. Their OWNED_STDLIB label is authored, not provider provenance.
    The producer tests separately exercise real recorder construction and receipts with an in-memory peer.
    """
    from edge_os_api.records.contract_adapter import canonical_bytes
    from edge_os_api.research_history.qualification_engine import epoch, iso_utc

    profile = copy.deepcopy(history.profile)
    start = epoch(profile["dataset"]["window"]["start_utc"])
    profile["dataset"]["window"] = {"start_utc": iso_utc(start), "end_utc": iso_utc(start + 1200)}
    tokens = profile["pool_tokens"]
    roles = {token["role"]: token["address"] for token in tokens}
    low, high = history.scan["from_block"], history.scan["to_block_exclusive"]
    assert high - low >= 4
    transport = {"construction": "OWNED_STDLIB",
                 "implementation": "edge_os_api.research_history.http_clients.http_transport.StdlibHttpTransport",
                 "implementation_sha256": "89aa0a18442fb1a28a51d31a9a06da2da9fee4f3e2731239e34a00d44c725f0d"}
    binding_sha = hashlib.sha256(canonical_bytes(transport)).hexdigest()
    calls, receipts, p3 = [], [], []
    counts = {"quicknode": 0, "hypersync": 0}
    plan = [("P1", "quicknode", 6), ("P1", "hypersync", 1), ("P2", "quicknode", 1),
            ("P3", "hypersync", 4), ("P4", "quicknode", 4), ("P5", "quicknode", 6)]
    for phase, provider, count in plan:
        for index in range(count):
            call_id = f"{len(calls)+1:02d}-{phase}-{provider}"
            request = canonical_bytes({"authored_test_call": call_id})
            reply = canonical_bytes({"authored_test_reply": call_id})
            received = start + (index + 1) * 300 + 30 if phase == "P3" else start - 120 if phase == "P2" else (
                start - 600 + len(calls) if phase == "P1" else start + 1321 + len(calls))
            call = {"call_id": call_id, "phase": phase, "slot": str(index), "provider": provider,
                    "request_sha256": hashlib.sha256(request).hexdigest(), "request_bytes": len(request),
                    "outcome": "REPLY_RECEIVED", "status": 200, "body_sha256": hashlib.sha256(reply).hexdigest(),
                    "body_bytes": len(reply)}
            calls.append(call)
            counts[provider] += 1
            receipts.append({key: call[key] for key in ("call_id", "request_sha256", "outcome", "status", "body_sha256",
                                                       "body_bytes")} | {"transport_binding_sha256": binding_sha,
                    "received_at_utc_us": received * 1000000, "elapsed_us": 1})
            if phase == "P3":
                p3.append({"call_id": call_id, "from_block": low + (high-low) * index // 4,
                           "next_block": low + (high-low) * (index+1) // 4, "archive_height": high + 3,
                           "log_count": 0, "received_utc_us": received * 1000000})
    buckets = [{"index": index, "start_utc": iso_utc(start + index * 300), "end_utc": iso_utc(start+(index+1)*300),
                "status": "DELIVERED", "reply_id": reply["call_id"],
                "received_at_utc": iso_utc(reply["received_utc_us"] // 1000000),
                "received_at_utc_us": reply["received_utc_us"], "record_count": 0,
                "payload_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
                "reply_body_sha256": next(call["body_sha256"] for call in calls if call["call_id"] == reply["call_id"]),
                "reason": None} for index, reply in enumerate(p3)]
    boundaries = {"B_ANCHOR": low, "B_PRE": low, "B_START": low+1, "B_END": high-2, "B_POST": high-1}
    headers = [{"number": number, "timestamp": timestamp, "hash": "0x" + f"{number:064x}"}
               for number, timestamp in ((low, start-1), (low+1, start), (high-2, start+1199), (high-1, start+1200))]
    h = {"schema_version": "edge-os.forward-history-handoff/2", "canonicalization_version": "edge-os.forward-history-payload/1",
         "input_schema": "edge-os.forward-history-input/1", "predecessor_sha256":
         "c4fc01c4d498742cd9a904606135fdb2b27fea448bb254462a79a9f67824312f",
         "input_sha256": "a" * 64, "recorder_code_sha256": "b" * 64, "decoder": "retained-v2-pair-created/1",
         "attempt_id": "authored-composition-attempt", "source_id": history.source_id, "evidence_class": "ACTUAL",
         "requested_evidence_class": "ACTUAL", "evidence_notice": "AUTHORED TEST graph, not provider provenance.",
         "claim_limit": "AUTHORED TEST wire shape only.", "status": "COMPLETED", "stop_reason": None,
         "network": {"chain_id": profile["network"]["chain_id"]}, "transport": transport,
         "market": {"pool": profile["venue"]["pool_address"], "token0": tokens[0]["address"],
                    "token1": tokens[1]["address"], "base": roles["BASE"], "quote": roles["QUOTE"]},
         "window": {**profile["dataset"]["window"], "bucket_seconds": 300},
         "query": {"address": profile["venue"]["pool_address"],
                   "topic0": "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822",
                   "include_all_blocks": True, "max_num_blocks": 10000, "field_selection": {
                       "block": ["number", "timestamp", "hash"],
                       "log": ["address", "topic0", "topic1", "topic2", "topic3", "data", "block_number", "block_hash",
                               "transaction_hash", "transaction_index", "log_index", "removed"]}},
         "boundaries": boundaries, "scan": dict(history.scan), "scan_log_count": 0, "chain_cursor": high,
         "weaker_evidence": [], "headers": headers, "phases": {
             "P1": {"outcome": "COMPLETED"}, "P2": {"outcome": "COMPLETED", "number": low, "timestamp": start-1,
                 "hash": headers[0]["hash"], "observed_utc_us": (start-120)*1000000},
             "P3": {"outcome": "COMPLETED", "reads": [{"bucket": i, "read": "first", "outcome": "COVERED"} for i in range(4)]},
             "P4": {"outcome": "COMPLETED"}, "P5": {"outcome": "COMPLETED"}},
         "p3_replies": p3, "facts": {"bytecode": {role: {"bytes": 1, "sha256": "c" * 64}
                      for role in ("pool", "token0", "token1")}, "fee_transfer_semantics": "EXTERNAL_EVIDENCE_REQUIRED",
             "decimals": {stage: {"token0": tokens[0]["decimals"], "token1": tokens[1]["decimals"]}
                          for stage in ("window_start", "window_end", "current")},
             "finality_at_collection": "OBSERVED_FINAL", "archive_height": high+3,
             "finalized": {"number": high+3, "timestamp": start+1300, "observed_utc_us": (start+1340)*1000000},
             "latest": {"number": high+4, "timestamp": start+1301, "observed_utc_us": (start+1341)*1000000},
             "pair_count": 1, "creation_block_timestamp": start-1000,
             "pool_tokens_at_start": {"token0": "READ", "token1": "READ"}, "archive_height_declarable": True},
         "clock": {"trusted": True}, "accounting": {"admitted": counts, "resolved": len(calls), "unknown_liability": 0,
             "reply_bytes": sum(call["body_bytes"] for call in calls), "ceilings": {"quicknode": 17, "hypersync": 9}},
         "calls": calls, "buckets": buckets, "delivery_records": {b["start_utc"]: b["received_at_utc"] for b in buckets},
         "release_frozen": False}
    h_body = canonical_bytes(h)
    r_body = canonical_bytes({"schema_version": "edge-os.forward-history-transport-receipts/1",
             "attempt_id": h["attempt_id"], "handoff_sha256": hashlib.sha256(h_body).hexdigest(),
             "recorder_code_sha256": h["recorder_code_sha256"], "evidence_class": "ACTUAL", "transport": transport,
             "receipts": receipts})
    p_body = canonical_bytes({"schema_version": "edge-os.forward-history-provenance/1", "attempt_id": h["attempt_id"],
             "handoff_sha256": hashlib.sha256(h_body).hexdigest(), "receipts_sha256": hashlib.sha256(r_body).hexdigest(),
             "recorder_code_sha256": h["recorder_code_sha256"], "transport": transport, "receipts_json": r_body.decode()})
    anchor = {"schema_version": "edge-os.forward-history-binding/2", "handoff_json": h_body.decode(),
              "handoff_sha256": hashlib.sha256(h_body).hexdigest(), "receipts_sha256": hashlib.sha256(r_body).hexdigest(),
              "provenance_json": p_body.decode(), "provenance_sha256": hashlib.sha256(p_body).hexdigest()}
    return replace(history, profile=profile, provider_facts={**history.provider_facts,
                   "delivery_records": h["delivery_records"], BINDING_FACT: anchor})


@pytest.mark.parametrize("mutation", ["missing-anchor", "changed-checker", "replacement-graph"])
def test_job_admission_rechecks_actual_graph_before_reservation_or_credentials(tmp_path, monkeypatch, mutation):
    from edge_os_api.research.investigation_jobs import release_refusal
    anchor, _, _ = graph(tmp_path, monkeypatch)
    runtime = actual_runtime(anchor, monkeypatch)
    assert release_refusal(runtime, runtime.release_sha256) is None
    if mutation == "missing-anchor":
        monkeypatch.delitem(runtime.release.history.provider_facts, BINDING_FACT)
    elif mutation == "changed-checker":
        monkeypatch.setattr(binding, "CHECKER_SHA256_V2", "b" * 64)
    else:
        h = json.loads(anchor["handoff_json"])
        h["evidence_notice"] = "Different complete AUTHORED TEST graph"
        replacement, _ = reanchor(anchor, {}, handoff=h)
        monkeypatch.setitem(runtime.release.history.provider_facts, BINDING_FACT, replacement)
        _check_history("ACTUAL", runtime.release.history)  # independently valid, different release identity
    refusal = release_refusal(runtime, runtime.release_sha256)
    assert refusal is not None
    assert refusal[0] in {"forward_history_binding_not_admitted", "forward_history_checker_unavailable",
                          "operating_release_changed"}


def test_stand_in_public_view_preserves_unavailable_checker_collection_path(monkeypatch):
    from edge_os_api.core.research.released_source_runtime import release_view
    runtime, *_ = stand_in.recording_runtime(SimpleNamespace(env="test"), release=stand_in.bound_release(nansen=False))
    expected_sha = runtime.release.history.provider_facts[BINDING_FACT]["handoff_sha256"]
    monkeypatch.setattr(binding, "CHECKER_SHA256", "0" * 64)
    assert release_view(runtime)["history"]["payload_binding"] == {
        "handoff_sha256": expected_sha, "evidence_class": "SYNTHETIC"}
