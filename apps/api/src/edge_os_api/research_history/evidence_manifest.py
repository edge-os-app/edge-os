"""Deterministic evidence manifest save, readback and hash identity.

The manifest is the portable record of one collection. Saving writes the P02
canonical bytes, so the same evidence always gives the same file and the same
SHA-256. Reading it back returns the identical object. ``verify_manifest``
recomputes the page digest and the counts so a tampered page, hash or count fails.

Files are caller-provided run-owned paths. No network or environment access.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from edge_os_api.research_history.errors import ManifestTampered
from edge_os_api.research_history.qualification_engine import (
    canonical_bytes,
    canonical_sha256,
    dataset_revision,
    engine_hashes,
)

MANIFEST_SCHEMA = "p07.research_history_manifest/1"
TASK_ID = "P07-HISTORY-L3-20261012-01"


def build_manifest(history: Mapping[str, Any]) -> dict[str, Any]:
    """Build the portable manifest from a normalized history result."""
    bound = history["bound_profile"]
    collection = history["collection"]
    qualification = history["qualification"]
    return {
        "manifest_schema": MANIFEST_SCHEMA,
        "task": TASK_ID,
        "profile_id": bound["profile_id"],
        "input_profile_sha256": history["input_profile_sha256"],
        "bound_profile_sha256": history["bound_profile_sha256"],
        "query": collection["query"],
        "window": history["window"],
        "provider": collection["provider"],
        "collection": {
            "status": collection["status"],
            "stop_reason": collection["stop_reason"],
            "page_count": collection["page_count"],
            "row_count": collection["row_count"],
            "bytes": collection["bytes"],
            "requests": collection["requests"],
            "gaps": collection["gaps"],
            "source_invocations": collection["source_invocations"],
            "coverage": collection["coverage"],
        },
        "pages": history["pages"],
        "buckets": history["buckets"],
        "dataset_revision": bound["dataset"]["dataset_revision"],
        "collection_sha256": collection["collection_sha256"],
        "observations_sha256": history["observations_sha256"],
        "result_sha256": history["result_sha256"],
        "normalized_sha256": history["normalized_sha256"],
        "qualification": {
            "overall": qualification["overall"],
            "claims": {name: view["verdict"] for name, view in qualification["claims"].items()},
        },
        "engine": engine_hashes(),
    }


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return canonical_sha256(manifest)


def save_manifest(manifest: Mapping[str, Any], path: Path | str) -> str:
    """Write canonical manifest bytes and return their SHA-256."""
    body = canonical_bytes(manifest)
    Path(path).write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def load_manifest(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_manifest(manifest: Mapping[str, Any], expected_sha256: str | None = None) -> bool:
    """Recompute the manifest identity. Raise ``ManifestTampered`` on any mismatch."""
    if expected_sha256 is not None and manifest_sha256(manifest) != expected_sha256:
        raise ManifestTampered("MANIFEST_HASH_MISMATCH", "manifest bytes do not match the expected hash")
    pages = manifest["pages"]
    revision = manifest["dataset_revision"]
    if revision.get("basis") != "PAGE_DIGESTS":
        raise ManifestTampered("PAGE_REVISION_MISMATCH", "a portable manifest must use PAGE_DIGESTS")
    if dataset_revision(pages) != revision.get("manifest_sha256"):
        raise ManifestTampered("PAGE_REVISION_MISMATCH", "page digest differs from the declared digest")
    if revision.get("page_count") != len(pages) or manifest["collection"]["page_count"] != len(pages):
        raise ManifestTampered("PAGE_COUNT_MISMATCH", "page count differs from the pages present")
    if revision.get("row_count") != manifest["collection"]["row_count"]:
        raise ManifestTampered("ROW_COUNT_MISMATCH", "row count differs from the declared rows")
    return True
