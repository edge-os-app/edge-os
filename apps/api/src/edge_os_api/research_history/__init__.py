"""Local research-history adapter package.

This package collects price-volume history from a caller-supplied recorded
response source and normalizes it into the existing P07 qualification evidence.
It is a library only. It has no live transport and reads no credential or
environment value. #58 mounts and stores its output later.
"""

from __future__ import annotations

from edge_os_api.research_history.errors import AdapterInputError, InvalidLimits
from edge_os_api.research_history.evidence_manifest import (
    MANIFEST_SCHEMA,
    build_manifest,
    load_manifest,
    load_raw_artifact,
    manifest_sha256,
    save_manifest,
    save_raw_artifact,
    verify_manifest,
)
from edge_os_api.research_history.history_collector import (
    CollectionLimits,
    collect,
)
from edge_os_api.research_history.history_normalizer import normalize, project_binding
from edge_os_api.research_history.provider_transport import (
    HistoryRequest,
    RecordedResponseSource,
    ResponseSource,
    SourceCancelled,
    SourceFailure,
    SourceTimeout,
)

__all__ = [
    "AdapterInputError",
    "CollectionLimits",
    "HistoryRequest",
    "InvalidLimits",
    "MANIFEST_SCHEMA",
    "RecordedResponseSource",
    "ResponseSource",
    "SourceCancelled",
    "SourceFailure",
    "SourceTimeout",
    "build_manifest",
    "collect",
    "load_manifest",
    "load_raw_artifact",
    "manifest_sha256",
    "normalize",
    "project_binding",
    "save_manifest",
    "save_raw_artifact",
    "verify_manifest",
]
