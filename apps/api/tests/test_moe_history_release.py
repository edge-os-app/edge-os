"""The one approved MOE history plus Nansen release and its frozen /2 anchor.

Pure: no database, socket or provider. The definition is code-owned, so these tests read the real registry rather than
replacing it. They pin the release id, its exact SHA-256, the anchored run's window and scan, and the refusals for a
changed run byte or a wrong window. See
`docs/qualification/research-provider-composition/MOE_HISTORY_ACTUAL_RELEASE.md`.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from edge_os_api.core.research import operating_release, released_runtime_bootstrap
from edge_os_api.core.research.operating_release import (
    BINDING_FACT,
    ReleaseRefused,
    check_release,
    release_sha256,
)
from edge_os_api.research import history_payload_binding

RELEASE_ID = "actual-moe-history-nansen-20261022/1"
RELEASE_SHA256 = "2d359daca6f9ca131ee6f90ca1efb97a6f12af4aa285104ebd062366648564c5"
OLD_RELEASE_ID = "actual-moe-nansen-demo-20261018/1"
WINDOW = {"start_utc": "2026-10-22T07:35:00Z", "end_utc": "2026-10-22T07:55:00Z"}
SCAN = {"from_block": 115554031, "to_block_exclusive": 115558007}
EVIDENCE_SHA256 = "5ad3a7c3e11f48e6f32fe2ab9f1edf7bf968962e4854c98d16e70327cfc9e73b"
FIXTURE = Path(__file__).with_name("fixtures") / "moe_history_anchor_20261022.json"


def definition() -> Any:
    return released_runtime_bootstrap.RELEASE_DEFINITIONS[RELEASE_ID]


def history() -> Any:
    part = definition().history
    assert part is not None
    return part


def anchor() -> dict[str, Any]:
    value = history().provider_facts[BINDING_FACT]
    assert isinstance(value, dict)
    return copy.deepcopy(value)


def changed_history(**changes: Any) -> Any:
    return dataclasses.replace(history(), **changes)


def test_the_registries_carry_exactly_the_one_approved_moe_history_release() -> None:
    assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == {RELEASE_ID}
    assert operating_release.APPROVED_RELEASES == {RELEASE_ID: RELEASE_SHA256}
    assert release_sha256(definition()) == RELEASE_SHA256
    assert check_release(definition(), network_transport=True, nansen_network=True) == RELEASE_SHA256


def test_the_old_nansen_only_id_is_refused() -> None:
    assert OLD_RELEASE_ID not in released_runtime_bootstrap.RELEASE_DEFINITIONS
    assert OLD_RELEASE_ID not in operating_release.APPROVED_RELEASES
    with pytest.raises(ReleaseRefused) as refused:
        check_release(dataclasses.replace(definition(), release_id=OLD_RELEASE_ID),
                      network_transport=True, nansen_network=True)
    assert refused.value.code == "operating_release_not_approved"


def test_the_anchor_admits_the_completed_run_and_matches_the_release_window_and_scan() -> None:
    history_payload_binding.check_definition("ACTUAL", history())  # no refusal
    handoff = json.loads(anchor()["handoff_json"])
    assert handoff["status"] == "COMPLETED" and handoff["stop_reason"] is None
    assert handoff["clock"]["trusted"] is True
    assert [bucket["status"] for bucket in handoff["buckets"]] == ["DELIVERED"] * 4
    assert (handoff["window"]["start_utc"], handoff["window"]["end_utc"]) == (
        WINDOW["start_utc"], WINDOW["end_utc"])
    assert handoff["scan"] == SCAN
    assert (history().scan, history().profile["dataset"]["window"]) == (SCAN, WINDOW)


def test_the_frozen_manifest_fixture_matches_the_code_owned_anchor() -> None:
    frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value, handoff = anchor(), json.loads(anchor()["handoff_json"])
    assert frozen["anchor"] == {key: value[key] for key in
                                ("schema_version", "handoff_sha256", "receipts_sha256", "provenance_sha256")}
    assert (frozen["attempt_id"], frozen["source_id"], frozen["status"]) == (
        handoff["attempt_id"], handoff["source_id"], handoff["status"])
    assert frozen["window"] == handoff["window"] and frozen["scan"] == handoff["scan"]
    assert frozen["market"] == handoff["market"] and frozen["network"] == handoff["network"]
    assert frozen["delivery_records"] == history().provider_facts["delivery_records"]
    assert [(b["status"], b["record_count"], b["payload_sha256"], b["reply_body_sha256"], b["received_at_utc"])
            for b in frozen["buckets"]] == [
        (b["status"], b["record_count"], b["payload_sha256"], b["reply_body_sha256"], b["received_at_utc"])
        for b in handoff["buckets"]]


def test_a_changed_run_byte_is_refused_even_after_its_outer_hash_is_recomputed() -> None:
    value = anchor()
    value["handoff_json"] = value["handoff_json"].replace("{", "{ ", 1)  # one added byte, still strict JSON
    value["handoff_sha256"] = hashlib.sha256(value["handoff_json"].encode("utf-8")).hexdigest()
    with pytest.raises(ReleaseRefused) as refused:
        history_payload_binding.check_definition(
            "ACTUAL", changed_history(provider_facts={**history().provider_facts, BINDING_FACT: value}))
    assert refused.value.code == "forward_history_binding_invalid"


def test_a_wrong_release_window_is_refused() -> None:
    profile = copy.deepcopy(history().profile)
    profile["dataset"]["window"] = {"start_utc": "2026-10-22T07:40:00Z", "end_utc": "2026-10-22T08:00:00Z"}
    with pytest.raises(ReleaseRefused) as refused:
        history_payload_binding.check_definition("ACTUAL", changed_history(profile=profile))
    assert refused.value.code == "forward_history_binding_invalid"


def test_a_wrong_scan_is_refused() -> None:
    scan = {"from_block": SCAN["from_block"], "to_block_exclusive": SCAN["to_block_exclusive"] + 1}
    with pytest.raises(ReleaseRefused) as refused:
        history_payload_binding.check_definition("ACTUAL", changed_history(scan=scan))
    assert refused.value.code == "forward_history_binding_invalid"


def test_the_history_limits_are_declarable_and_fit_the_default_owner_caps() -> None:
    from edge_os_api.core.request_schemas import HistoryResourceBounds
    from edge_os_api.core.settings import Settings

    limits = history().limits
    assert HistoryResourceBounds(**limits).model_dump() == limits  # a declaration can carry these exact bounds
    assert limits == {"provider_requests": 13, "compute_seconds": 600, "max_pages": 4, "max_rows": 2000,
                      "max_bytes": 4194304, "deadline_seconds": 600}
    assert history().client_bounds == {"deadline_seconds": 120, "connect_timeout_seconds": 15,
                                       "max_response_bytes": 2097152, "max_request_bytes": 65536,
                                       "max_blocks_per_page": 10000}
    assert history().corroboration_sample_size == 8
    assert limits["max_pages"] + 1 + history().corroboration_sample_size <= limits["provider_requests"]
    nansen = definition().nansen
    assert nansen is not None
    fields = Settings.model_fields
    assert (limits["provider_requests"] + nansen.limits["max_requests"]
            <= fields["research_budget_provider_requests"].default)
    assert (limits["compute_seconds"] + nansen.compute_seconds
            <= fields["research_budget_compute_seconds"].default)


def test_the_declared_demo_floors_are_recorded_with_their_source() -> None:
    partitions = history().provider_facts["feasibility_claim"]["partitions"]
    assert [{"required_triggered": p["required_triggered"], "required_control": p["required_control"]}
            for p in partitions] == [{"required_triggered": 1, "required_control": 1}]


def test_the_release_records_the_observed_token_mechanics_basis_and_never_plain_qualified() -> None:
    facts = history().provider_facts
    assert facts["fee_transfer_semantics"] == "QUALIFIED_BY_OBSERVATION" != "QUALIFIED"
    assert facts["token_mechanics"] == {
        "state": "QUALIFIED_BY_OBSERVATION", "basis": "OBSERVED_BEHAVIOR", "window_seconds": 43200,
        "evidence_sha256": EVIDENCE_SHA256, "source_proof": False}


def test_the_default_composes_the_history_and_nansen_parts_without_a_credential_read(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a socket was opened")

    monkeypatch.setattr("socket.socket", refuse)
    monkeypatch.setattr("socket.create_connection", refuse)
    runtime = released_runtime_bootstrap.server_research_runtime(SimpleNamespace(env="local"))
    assert runtime is not None and runtime.release_sha256 == RELEASE_SHA256
    assert runtime.release.history is not None and runtime.release.nansen is not None
    assert runtime.network_transport is True and runtime.nansen_network is True
