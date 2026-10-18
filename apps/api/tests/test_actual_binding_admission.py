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
