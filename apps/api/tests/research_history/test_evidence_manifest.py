"""Public-seam tests for the evidence manifest and the package isolation guarantees."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

import _support as support
from edge_os_api.research_history import (
    CollectionLimits,
    RecordedResponseSource,
    build_manifest,
    collect,
    load_manifest,
    load_raw_artifact,
    manifest_sha256,
    normalize,
    save_manifest,
    save_raw_artifact,
    verify_manifest,
)
from edge_os_api.research_history.errors import ManifestTampered

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "edge_os_api" / "research_history"


def _history() -> dict:
    profile = support.profile()
    collection = collect(profile, RecordedResponseSource(support.standard_responses()), support.SCAN,
                         CollectionLimits(**support.limits()), {"recorded_by": "test"})
    return normalize(profile, collection, support.evidence_facts())


def test_manifest_round_trip_is_byte_identical(tmp_path: Path) -> None:
    manifest = build_manifest(_history())
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    digest = save_manifest(manifest, first)
    save_manifest(manifest, second)
    assert first.read_bytes() == second.read_bytes()
    assert manifest_sha256(load_manifest(first)) == digest
    assert load_manifest(first) == manifest
    assert verify_manifest(load_manifest(first), digest) is True


def test_tampered_page_fails_verification(tmp_path: Path) -> None:
    manifest = build_manifest(_history())
    tampered = copy.deepcopy(manifest)
    tampered["pages"][0]["sha256"] = "f" * 64
    with pytest.raises(ManifestTampered) as raised:
        verify_manifest(tampered)
    assert raised.value.code == "PAGE_REVISION_MISMATCH"


def test_wrong_expected_hash_fails_verification() -> None:
    manifest = build_manifest(_history())
    with pytest.raises(ManifestTampered) as raised:
        verify_manifest(manifest, "0" * 64)
    assert raised.value.code == "MANIFEST_HASH_MISMATCH"


def test_manifest_records_the_collection_boundaries_and_qualification() -> None:
    manifest = build_manifest(_history())
    assert manifest["manifest_schema"] == "p07.research_history_manifest/1"
    assert manifest["collection"]["status"] == "COMPLETE"
    assert [step["cursor_after"] for step in manifest["collection"]["requests"]] == [104, None]
    assert manifest["qualification"]["overall"] == "QUALIFIED"
    assert manifest["dataset_revision"]["basis"] == "PAGE_DIGESTS"
    assert manifest["engine"]["p07_qualification"] and manifest["engine"]["p02_checker"]


def test_manifest_includes_consumer_metadata() -> None:
    manifest = build_manifest(_history())
    assert manifest["normalized_sha256"]
    assert len(manifest["buckets"]) == 4
    assert manifest["collection"]["coverage"]["covers_requested_scan"] is True
    assert manifest["collection"]["source_invocations"] == {"measured_local_attempts": 2,
                                                             "provider_requests": None}
    assert manifest["raw_evidence"]["record_count"] == 2


def test_manifest_retains_raw_evidence_and_replays(tmp_path: Path) -> None:
    profile = support.profile()
    collection = collect(profile, RecordedResponseSource(support.standard_responses()), support.SCAN,
                         CollectionLimits(**support.limits()), {"recorded_by": "test"})
    history = normalize(profile, collection, support.evidence_facts())
    manifest_path, artifact_path = tmp_path / "manifest.json", tmp_path / "raw.json"
    digest = save_manifest(build_manifest(history), manifest_path)
    loaded = load_manifest(manifest_path)
    artifact_digest = save_raw_artifact(history["raw_records"], artifact_path)
    assert artifact_digest == loaded["raw_evidence"]["sha256"]
    assert loaded["raw_evidence"]["record_count"] == 2
    verify_manifest(loaded, digest, raw_records=load_raw_artifact(artifact_path))
    replayed = normalize(profile, {**collection, "records": load_raw_artifact(artifact_path)},
                         support.evidence_facts())
    assert replayed["normalized_sha256"] == history["normalized_sha256"]
    assert replayed["observations"]["ingest"] == history["observations"]["ingest"]


def test_tampered_raw_records_fail_verification() -> None:
    manifest = build_manifest(_history())
    records = list(_history()["raw_records"])
    records[0] = {**records[0], "block_hash": "0x" + "00" * 32}
    with pytest.raises(ManifestTampered) as raised:
        verify_manifest(manifest, raw_records=records)
    assert raised.value.code == "RAW_EVIDENCE_MISMATCH"


def test_package_has_no_live_transport_or_environment_discovery() -> None:
    forbidden = ("os.environ", "getenv", "import socket", "import httpx", "import requests",
                 "urllib.request", "subprocess", "api_key", "Authorization")
    modules = sorted(PACKAGE.glob("*.py"))
    assert modules, "the package modules must exist"
    for module in modules:
        text = module.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{module.name} contains forbidden token {token!r}"
